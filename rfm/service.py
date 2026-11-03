from datetime import datetime
import json
import logging
from pathlib import Path
import threading
import time
import uuid

from . import db
from .analysis import clean_file, compute_rfm, build_summary, file_sha256, validate_period

log = logging.getLogger(__name__)

class BusyError(ValueError):
    pass

def get_batch(batch_id=None):
    if batch_id:
        batch = db.query('SELECT * FROM analysis_batches WHERE id=%s', (batch_id,), one=True)
    else:
        batch = db.query('SELECT b.* FROM analysis_batches b JOIN app_state s ON b.id=s.active_batch_id WHERE s.id=1', one=True)
    if batch and batch['summary']:
        batch['summary'] = json.loads(batch['summary'])
    return batch

def acquire_lock():
    conn = db.connect()
    with conn.cursor() as cur:
        cur.execute("SELECT GET_LOCK('retail_rfm_analysis',0) AS acquired")
        if not cur.fetchone()['acquired']:
            conn.close()
            raise BusyError('已有分析任务正在运行，请等待完成后再导入。')
    return conn

def release_lock(conn):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT RELEASE_LOCK('retail_rfm_analysis')")
    finally:
        conn.close()

def recover_interrupted():
    try:
        conn = acquire_lock()
    except BusyError:
        return
    try:
        db.execute("UPDATE analysis_batches SET status='failed',error='上次进程退出导致任务中断，请重新导入；原成功批次保留。',progress='任务中断',completed_at=NOW() WHERE status IN ('queued','running')")
    finally:
        release_lock(conn)

def submit(source, filename, start, end, reference):
    validate_period(start, end, reference)
    sha = file_sha256(source)
    lock = acquire_lock()
    try:
        duplicate = db.query("SELECT id FROM analysis_batches WHERE source_sha=%s AND window_start=%s AND window_end=%s AND reference_date=%s AND rules_version='rfm-v1' AND status='succeeded' ORDER BY completed_at DESC LIMIT 1",
                             (sha, start, end, reference), one=True)
        if duplicate:
            db.execute('UPDATE app_state SET active_batch_id=%s WHERE id=1', (duplicate['id'],))
            release_lock(lock)
            return duplicate['id'], True
        batch_id = uuid.uuid4().hex
        # Preserve the exact imported source; built-in raw data already lives in an immutable project location.
        db.execute("INSERT INTO analysis_batches(id,filename,source_path,source_sha,window_start,window_end,reference_date,status,progress) VALUES(%s,%s,%s,%s,%s,%s,%s,'queued','等待分析')",
                   (batch_id, filename[:255], str(Path(source).resolve()), sha, start, end, reference))
        thread = threading.Thread(target=run_batch, args=(batch_id, lock), name=f'analysis-{batch_id[:8]}', daemon=True)
        thread.start()
        return batch_id, False
    except Exception:
        release_lock(lock)
        raise

def run_batch(batch_id, lock):
    started = time.perf_counter()
    batch = get_batch(batch_id)
    outdir = db.ROOT / 'data/runs' / batch_id
    def progress(message):
        db.execute('UPDATE analysis_batches SET progress=%s WHERE id=%s', (message, batch_id))
    try:
        db.execute("UPDATE analysis_batches SET status='running',progress='开始校验和清洗' WHERE id=%s", (batch_id,))
        start, end, reference = (str(batch[k]) for k in ('window_start', 'window_end', 'reference_date'))
        df, quality = clean_file(batch['source_path'], outdir, start, end, reference, progress)
        progress('计算客户RFM、评分与分群')
        result, rules, audit = compute_rfm(df, reference)
        quality['event_audit'] = audit
        summary = build_summary(df, result, rules, quality, start, end, reference)
        result.to_csv(outdir / 'rfm.csv', index=False, encoding='utf-8-sig')
        (outdir / 'report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        progress('正在写入MySQL；全部完成前保留上一成功批次')
        with db.connect(autocommit=False) as conn:
            try:
                with conn.cursor() as cur:
                    cols = ['source_row','kh','dtime','syjh','djh','spbm','spmc','sl','sj','je','jf','gzbm','gzmc','amount_cents']
                    for offset in range(0, len(df), 3000):
                        chunk = df.iloc[offset:offset+3000][cols].copy()
                        chunk['dtime'] = chunk.dtime.dt.strftime('%Y-%m-%d %H:%M:%S.%f')
                        rows = [(batch_id, *row) for row in chunk.itertuples(index=False, name=None)]
                        cur.executemany('INSERT INTO transaction_lines(batch_id,' + ','.join(cols) + ') VALUES(' + ','.join(['%s'] * 15) + ')', rows)
                    cols = ['kh','last_purchase','r','f','m_cents','detail_count','r_score','f_score','m_score','segment_code','segment']
                    for offset in range(0, len(result), 3000):
                        chunk = result.iloc[offset:offset+3000][cols].copy()
                        chunk['last_purchase'] = chunk.last_purchase.dt.strftime('%Y-%m-%d %H:%M:%S.%f')
                        cur.executemany('INSERT INTO customer_rfm(batch_id,' + ','.join(cols) + ') VALUES(' + ','.join(['%s'] * 12) + ')',
                                        [(batch_id, *row) for row in chunk.itertuples(index=False, name=None)])
                    cur.execute('SELECT COUNT(*) AS detail_count, SUM(amount_cents) AS cents FROM transaction_lines WHERE batch_id=%s', (batch_id,))
                    saved = cur.fetchone()
                    cur.execute('SELECT COUNT(*) AS customers,SUM(f) AS events,SUM(m_cents) AS cents,SUM(detail_count) AS detail_count FROM customer_rfm WHERE batch_id=%s', (batch_id,))
                    saved_rfm = cur.fetchone()
                    if (saved['detail_count'], int(saved['cents'])) != (summary['detail_count'], summary['amount_cents']):
                        raise RuntimeError('数据库明细一致性核对失败。')
                    if tuple(int(saved_rfm[k]) for k in ('customers','events','cents','detail_count')) != tuple(summary[k] for k in ('customer_count','event_count','amount_cents','detail_count')):
                        raise RuntimeError('数据库RFM一致性核对失败。')
                    cur.execute("UPDATE analysis_batches SET status='succeeded',progress='分析完成，数据库一致性检查通过',summary=%s,completed_at=NOW(),duration_seconds=%s WHERE id=%s",
                                (json.dumps(summary, ensure_ascii=False), round(time.perf_counter()-started, 3), batch_id))
                    cur.execute('UPDATE app_state SET active_batch_id=%s WHERE id=1', (batch_id,))
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
    except Exception as exc:
        log.exception('Analysis failed: %s', batch_id)
        message = str(exc) if isinstance(exc, ValueError) else '分析未完成，请查看 runtime/app.log；上一次成功结果保留。'
        db.execute("UPDATE analysis_batches SET status='failed',progress='分析失败',error=%s,completed_at=NOW(),duration_seconds=%s WHERE id=%s",
                   (message[:2000], round(time.perf_counter()-started,3), batch_id))
    finally:
        release_lock(lock)

def customer_filter(args, batch_id):
    where = ['batch_id=%s']
    params = [batch_id]
    kh = args.get('kh', '').strip()
    if kh:
        import re
        if not re.fullmatch(r'[0-9a-fA-F]{1,8}', kh):
            raise ValueError('客户标识请输入1—8位十六进制字符。')
        where.append('kh LIKE %s')
        params.append('%' + kh + '%')
    segment = args.get('segment', '')
    if segment:
        from .analysis import SEGMENTS
        if segment not in SEGMENTS:
            raise ValueError('分群参数无效。')
        where.append('segment_code=%s')
        params.append(segment)
    sorts = {'m': 'm_cents DESC, kh ASC', 'f': 'f DESC, kh ASC', 'r': 'r ASC, kh ASC', 'kh': 'kh ASC'}
    sort = args.get('sort', 'm')
    if sort not in sorts:
        raise ValueError('排序参数无效。')
    return ' AND '.join(where), params, sorts[sort]
