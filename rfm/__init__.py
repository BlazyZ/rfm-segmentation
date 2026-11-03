import csv
from datetime import date, datetime
from decimal import Decimal
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import uuid

from flask import Flask, jsonify, request, render_template, send_file, Response, stream_with_context
from flask.json.provider import DefaultJSONProvider
import pymysql
from werkzeug.exceptions import HTTPException

from . import db, service
from .analysis import SEGMENTS, validate_period

class JSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(obj):
        if isinstance(obj, datetime):
            return obj.isoformat(sep=' ', timespec='microseconds').rstrip('0').rstrip('.')
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return int(obj) if obj == int(obj) else float(obj)
        return DefaultJSONProvider.default(obj)

def create_app(test_config=None):
    app = Flask(__name__)
    app.json = JSONProvider(app)
    app.json.ensure_ascii = False
    app.config.update(MAX_CONTENT_LENGTH=int(os.getenv('MAX_UPLOAD_MB', '300')) * 1024 * 1024,
                      MAX_FORM_MEMORY_SIZE=1024 * 1024)
    if test_config:
        app.config.update(test_config)
    runtime = db.ROOT / 'runtime'
    runtime.mkdir(exist_ok=True)
    handler = RotatingFileHandler(runtime / 'app.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    logging.getLogger('rfm').addHandler(handler)
    logging.getLogger('rfm').setLevel(logging.INFO)

    @app.before_request
    def local_mutation_only():
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            # This app is local and has no login. Block browser writes initiated by other sites.
            origin = request.headers.get('Origin')
            if origin and origin != request.host_url.rstrip('/'):
                return jsonify(error='不接受来自其他站点的写入请求。'), 403
            if request.headers.get('Sec-Fetch-Site') == 'cross-site':
                return jsonify(error='不接受跨站写入请求。'), 403

    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(Exception)
    def errors(exc):
        if isinstance(exc, service.BusyError):
            return jsonify(error=str(exc)), 409
        if isinstance(exc, ValueError):
            return jsonify(error=str(exc)), 400
        if isinstance(exc, HTTPException):
            messages = {404:'请求的页面或资源不存在。',413:'文件过大，最大支持300MB。',405:'请求方法不支持。'}
            return jsonify(error=messages.get(exc.code, exc.description)), exc.code
        app.logger.exception('Request failed')
        if isinstance(exc, pymysql.MySQLError):
            return jsonify(error='数据库暂不可用，请运行启动脚本并检查MySQL配置；详情见runtime/app.log。'), 503
        return jsonify(error='请求未完成，详情已记录到runtime/app.log。'), 500

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/api/health')
    def health():
        version = db.query('SELECT VERSION() AS version', one=True)['version']
        return jsonify(status='ok', database='MySQL', version=version)

    def successful_batch():
        batch = service.get_batch(request.args.get('batch_id'))
        if not batch or batch['status'] != 'succeeded':
            return None
        return batch

    @app.get('/api/summary')
    def summary():
        batch = successful_batch()
        if not batch:
            return jsonify(batch=None, summary=None)
        return jsonify(batch={k: batch[k] for k in ('id','filename','source_sha','created_at','completed_at','duration_seconds')}, summary=batch['summary'])

    @app.get('/api/batches')
    def batches():
        rows = db.query('SELECT id,filename,source_sha,window_start,window_end,reference_date,status,progress,error,created_at,completed_at,duration_seconds FROM analysis_batches ORDER BY created_at DESC,id DESC LIMIT 50')
        active = db.query('SELECT active_batch_id FROM app_state WHERE id=1', one=True)
        return jsonify(items=rows, active_batch_id=active['active_batch_id'])

    @app.get('/api/batches/<batch_id>')
    def batch_status(batch_id):
        batch = service.get_batch(batch_id)
        if not batch:
            return jsonify(error='分析批次不存在。'), 404
        return jsonify({k: v for k,v in batch.items() if k not in ('source_path','summary')})

    @app.post('/api/batches/<batch_id>/activate')
    def activate(batch_id):
        batch = service.get_batch(batch_id)
        if not batch or batch['status'] != 'succeeded':
            raise ValueError('只能切换到已成功的批次。')
        db.execute('UPDATE app_state SET active_batch_id=%s WHERE id=1', (batch_id,))
        return jsonify(id=batch_id)

    @app.post('/api/import')
    def import_data():
        data = request.form if request.mimetype == 'multipart/form-data' else (request.get_json(silent=True) or {})
        if not isinstance(data, dict) and request.mimetype != 'multipart/form-data':
            raise ValueError('请求数据必须为对象。')
        start, end, reference = (data.get(k, default) for k, default in [('start','2017-01-01'),('end','2018-01-01'),('reference','2018-01-01')])
        validate_period(start, end, reference)
        upload = request.files.get('file')
        if upload:
            suffix = Path(upload.filename or '').suffix.lower()
            if suffix not in ('.csv', '.xlsx'):
                raise ValueError('仅支持.csv和.xlsx交易文件。')
            folder = db.ROOT / 'data/uploads'
            folder.mkdir(parents=True, exist_ok=True)
            source = folder / (uuid.uuid4().hex + suffix)
            upload.save(source)
            filename = (upload.filename or '上传交易文件').replace('\\','/').split('/')[-1]
        elif data.get('source') == 'builtin':
            source = db.ROOT / 'data/raw/cumcm2018c/cumcm2018c2.csv'
            filename = 'cumcm2018c2.csv'
        elif data.get('source_batch'):
            previous = service.get_batch(data['source_batch'])
            if not previous:
                raise ValueError('原分析批次不存在。')
            source = Path(previous['source_path'])
            filename = previous['filename']
        else:
            raise ValueError('请选择交易文件或使用内置原始数据。')
        if not source.is_file():
            raise ValueError('原始文件不存在，请检查data/raw目录或重新上传。')
        batch_id, reused = service.submit(source, filename, start, end, reference)
        return jsonify(id=batch_id, reused=reused, message='相同文件及规则已分析，已切换至已有结果。' if reused else '导入任务已创建，正在后台分析。'), 200 if reused else 202

    @app.get('/api/customers')
    def customers():
        batch = successful_batch()
        if not batch:
            return jsonify(items=[], total=0, page=1, page_size=20)
        where, params, order = service.customer_filter(request.args, batch['id'])
        page, page_size = int(request.args.get('page', 1)), int(request.args.get('page_size',20))
        if not (1 <= page <= 1000000 and 1 <= page_size <= 100):
            raise ValueError('页码须大于0，每页条数为1—100。')
        total = db.query('SELECT COUNT(*) AS n FROM customer_rfm WHERE ' + where, params, one=True)['n']
        rows = db.query('SELECT kh,last_purchase,r,f,m_cents,detail_count,r_score,f_score,m_score,segment,segment_code FROM customer_rfm WHERE ' + where + ' ORDER BY ' + order + ' LIMIT %s OFFSET %s', params+[page_size,(page-1)*page_size])
        return jsonify(items=rows, total=total, page=page, page_size=page_size, batch_id=batch['id'])

    @app.get('/api/customers/<kh>')
    def customer_detail(kh):
        batch = successful_batch()
        if not batch:
            return jsonify(error='请先导入并完成分析。'), 404
        row = db.query('SELECT * FROM customer_rfm WHERE batch_id=%s AND kh=%s', (batch['id'],kh), one=True)
        if not row:
            return jsonify(error='该批次未找到此客户。'), 404
        page = int(request.args.get('page', 1))
        if page < 1 or page > 1000000:
            raise ValueError('明细页码无效。')
        lines = db.query('SELECT source_row,dtime,syjh,djh,spbm,spmc,sl,je,amount_cents FROM transaction_lines WHERE batch_id=%s AND kh=%s ORDER BY dtime DESC,source_row LIMIT 20 OFFSET %s', (batch['id'],kh,(page-1)*20))
        return jsonify(customer=row, lines=lines, page=page, page_size=20, reference=str(batch['reference_date']))

    @app.get('/api/sales')
    def sales():
        batch = successful_batch()
        if not batch:
            return jsonify(totals=None, monthly=[], products=[], counters=[])
        start = request.args.get('start',str(batch['window_start']))
        end = request.args.get('end',str(batch['window_end']))
        validate_period(start,end,str(batch['reference_date']))
        if start < str(batch['window_start']) or end > str(batch['window_end']):
            raise ValueError('筛选日期须位于当前批次的观察窗口内。')
        where = 'batch_id=%s AND dtime>=%s AND dtime<%s'
        params = (batch['id'], start, end)
        totals = db.query('SELECT COUNT(*) AS detail_count,COUNT(DISTINCT kh) AS customer_count,COALESCE(SUM(amount_cents),0) AS amount_cents,COUNT(DISTINCT kh,dtime,syjh,djh) AS event_count FROM transaction_lines WHERE ' + where, params, one=True)
        monthly = db.query("SELECT DATE_FORMAT(dtime,'%%Y-%%m') AS month,SUM(amount_cents) AS amount_cents,COUNT(DISTINCT kh,dtime,syjh,djh) AS events,COUNT(*) AS details FROM transaction_lines WHERE " + where + " GROUP BY month ORDER BY month", params)
        products = db.query('SELECT spbm AS name,MAX(spmc) AS label,SUM(amount_cents) AS amount_cents,COUNT(*) AS details FROM transaction_lines WHERE ' + where + ' GROUP BY spbm ORDER BY amount_cents DESC,spbm LIMIT 10', params)
        counters = db.query("SELECT COALESCE(NULLIF(gzmc,''),'未提供') AS name,SUM(amount_cents) AS amount_cents,COUNT(*) AS details FROM transaction_lines WHERE " + where + ' GROUP BY name ORDER BY amount_cents DESC,name LIMIT 10',params)
        return jsonify(totals=totals, monthly=monthly, products=products,counters=counters,start=start,end=end,batch_id=batch['id'])

    @app.get('/api/export')
    def export_customers():
        batch = successful_batch()
        if not batch:
            raise ValueError('请先完成数据分析。')
        where, params, order = service.customer_filter(request.args, batch['id'])
        export_format = request.args.get('format','csv')
        if export_format not in ('csv','xlsx'):
            raise ValueError('导出格式仅支持csv或xlsx。')
        headings = ['客户标识','最近购买时间','R_天','F_购买事件数','M_正向购买金额_元','商品明细数','R评分','F评分','M评分','客户分群','分群编码','分析批次','窗口开始_含','窗口结束_不含','分析基准日','规则版本']
        def records():
            with db.connect(cursorclass=pymysql.cursors.SSDictCursor) as conn, conn.cursor() as cur:
                cur.execute('SELECT * FROM customer_rfm WHERE ' + where + ' ORDER BY ' + order, params)
                for row in cur:
                    yield [row['kh'],str(row['last_purchase']),row['r'],row['f'],format(Decimal(row['m_cents'])/100,'.2f'),row['detail_count'],
                           row['r_score'],row['f_score'],row['m_score'],row['segment'],row['segment_code'],batch['id'],str(batch['window_start']),str(batch['window_end']),str(batch['reference_date']),batch['rules_version']]
        filename = f'rfm_{batch["id"][:8]}.{export_format}'
        if export_format == 'xlsx':
            from openpyxl import Workbook
            book = Workbook(write_only=True)
            sheet = book.create_sheet('客户RFM结果')
            sheet.append(headings)
            for row in records():
                sheet.append(row)
            buffer = io.BytesIO()
            book.save(buffer)
            buffer.seek(0)
            return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        def stream():
            yield '\ufeff'
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            for row in [headings]:
                writer.writerow(row)
                yield buffer.getvalue()
                buffer.seek(0); buffer.truncate(0)
            for row in records():
                # Prevent spreadsheet formula execution in text cells.
                row = ["'" + v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v for v in row]
                writer.writerow(row)
                yield buffer.getvalue()
                buffer.seek(0); buffer.truncate(0)
        return Response(stream_with_context(stream()), mimetype='text/csv; charset=utf-8', headers={'Content-Disposition':f'attachment; filename="{filename}"'})

    @app.get('/api/batches/<batch_id>/artifacts/<kind>')
    def artifacts(batch_id, kind):
        batch = service.get_batch(batch_id)
        if not batch or batch['status'] != 'succeeded':
            return jsonify(error='成功批次不存在。'), 404
        files = {'quality':'report.json', 'cleaned':'cleaned.csv', 'excluded':'excluded.csv'}
        if kind not in files:
            return jsonify(error='下载类型不存在。'), 404
        return send_file(db.ROOT / 'data/runs' / batch['id'] / files[kind], as_attachment=True, download_name=files[kind])

    return app
