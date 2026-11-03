"""Real HTTP/MySQL/export checks, independent CSV/Decimal RFM reconciliation.
Synthetic files here are exclusively labelled tests, never final analysis results.
"""
from pathlib import Path
import csv
from decimal import Decimal
from datetime import datetime
import io
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import requests
import pandas as pd
from openpyxl import load_workbook
from rfm import db
from rfm.analysis import FIELDS, file_sha256

BASE='http://127.0.0.1:5000'
checks=[]

def check(name,condition,detail=None):
    if not condition:raise AssertionError(name+': '+str(detail))
    checks.append({'check':name,'passed':True,'detail':detail})
    print('PASS',name,flush=True)

def get(path,**kwargs):
    r=requests.get(BASE+path,timeout=120,**kwargs);r.raise_for_status();return r.json()

def wait_batch(batch_id):
    deadline=time.monotonic()+300
    while time.monotonic()<deadline:
        b=get('/api/batches/'+batch_id)
        if b['status'] not in ('queued','running'):return b
        time.sleep(.5)
    raise RuntimeError('analysis timeout')

def main():
    started=time.perf_counter()
    main_batch=get('/api/summary')['batch']
    if not main_batch:raise RuntimeError('先完成内置原始文件分析')
    batch_id=main_batch['id']
    params={'batch_id':batch_id}
    s=get('/api/summary',params=params)['summary']
    check('原始文件SHA-256符合已有核查',main_batch['source_sha']=='758252f38ed4141b21bc3a1dc6dcb7fd89a03dc9b51b7a3b62ceaaf09c598f42')
    check('原始文件未修改',file_sha256(ROOT/'data/raw/cumcm2018c/cumcm2018c2.csv')==main_batch['source_sha'])
    check('清洗规模与历史核查一致',(s['quality']['total_rows'],s['detail_count'],s['customer_count'],s['event_count'])==(1893532,356346,47597,186971))
    check('排除行数与互斥原因守恒',s['quality']['total_rows']==s['quality']['accepted_rows']+s['quality']['excluded_rows'] and sum(s['quality']['primary_reasons'].values())==s['quality']['excluded_rows'])
    # Independent reference: Python csv, exact Decimal money, native tuple sets and datetime.
    customers={}; total_cents=0
    with (ROOT/'data/runs'/batch_id/'cleaned.csv').open(encoding='utf-8-sig',newline='') as f:
        for line in csv.DictReader(f):
            kh=line['kh']; t=datetime.fromisoformat(line['dtime']); cents=int(Decimal(line['je'])*100)
            c=customers.setdefault(kh,{'last':t,'events':set(),'cents':0,'lines':0})
            c['last']=max(c['last'],t);c['events'].add((kh,t,line['syjh'],line['djh']));c['cents']+=cents;c['lines']+=1;total_cents+=cents
    actual=db.query('SELECT kh,last_purchase,r,f,m_cents,detail_count,r_score,f_score,m_score,segment_code FROM customer_rfm WHERE batch_id=%s',(batch_id,))
    mismatches=[]
    for r in actual:
        c=customers[r['kh']]
        expected=((datetime(2018,1,1).date()-c['last'].date()).days,len(c['events']),c['cents'],c['lines'],c['last'])
        if (r['r'],r['f'],r['m_cents'],r['detail_count'],r['last_purchase'])!=expected:mismatches.append(r['kh'])
        score=[]
        for metric in ['r','f','m_cents']:
            interval=sum(r[metric]>v for v in s['rules']['boundaries'][metric])
            score.append(5-interval if metric=='r' else 1+interval)
        if tuple(score)!=(r['r_score'],r['f_score'],r['m_score']):mismatches.append('score:'+r['kh'])
        if ''.join('1' if v>=4 else '0' for v in score)!=r['segment_code']:mismatches.append('segment:'+r['kh'])
    check('全部47597名客户独立复算R/F/M及评分分群',not mismatches,{'compared':len(actual),'mismatches':mismatches[:10]})
    check('精确je总额与批次汇总一致',total_cents==s['amount_cents'],{'amount_cents':total_cents})
    sales=get('/api/sales',params=params)
    check('销售接口与分析汇总一致',all(int(sales['totals'][k])==s[k] for k in ['detail_count','customer_count','event_count','amount_cents']))
    check('月度与分群金额人数守恒',sum(int(x['amount_cents']) for x in sales['monthly'])==total_cents and sum(x['amount_cents'] for x in s['segments'])==total_cents and sum(x['customers'] for x in s['segments'])==len(customers))
    exported=requests.get(BASE+'/api/export',params=params,timeout=120);exported.raise_for_status()
    exported_rows=list(csv.DictReader(io.StringIO(exported.content.decode('utf-8-sig'))))
    check('全量CSV导出与数据库逐客户一致',len(exported_rows)==len(customers) and all(int(Decimal(x['M_正向购买金额_元'])*100)==customers[x['客户标识']]['cents'] and int(x['F_购买事件数'])==len(customers[x['客户标识']]['events']) and x['分析批次']==batch_id for x in exported_rows))
    out=ROOT/'docs/验证输出';out.mkdir(exist_ok=True)
    (out/'客户RFM_完整导出.csv').write_bytes(exported.content)
    group=get('/api/customers',params={**params,'segment':'111','page_size':100})
    subset=requests.get(BASE+'/api/export',params={**params,'segment':'111','format':'xlsx'},timeout=120);subset.raise_for_status()
    workbook=load_workbook(io.BytesIO(subset.content),read_only=True)
    sheet=list(workbook.active.values);head=sheet[0];rows=sheet[1:]
    check('Excel导出与群体筛选一致',len(rows)==group['total'] and all(x[head.index('分群编码')]=='111' for x in rows))
    (out/'重要价值客户_筛选导出.xlsx').write_bytes(subset.content)
    # Five representative customers selected from actual results, documented for later defence.
    ordered=sorted(actual,key=lambda x:x['m_cents'])
    candidates=[ordered[0],ordered[-1],min(actual,key=lambda x:x['r']),max(actual,key=lambda x:x['r']),max(actual,key=lambda x:x['f']),ordered[len(ordered)//2]]
    sample_rows=list({row['kh']:row for row in candidates}.values())[:5]
    examples=[]
    for r in sample_rows:
        detail=get('/api/customers/'+r['kh'],params=params)
        check('真实客户详情核对 '+r['kh'],detail['customer']['m_cents']==r['m_cents'] and detail['customer']['detail_count']==customers[r['kh']]['lines'])
        examples.append({**r,'last_purchase':str(r['last_purchase']),'independent_event_count':len(customers[r['kh']]['events'])})
    (out/'五名客户核对.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2),encoding='utf-8')
    empty=get('/api/sales',params={**params,'start':'2017-01-01','end':'2017-01-02'})
    check('日期筛选仅查询规定窗口',empty['totals']['detail_count']>0 and empty['totals']['detail_count']<s['detail_count'])
    check('非法分页拒绝',requests.get(BASE+'/api/customers',params={**params,'page_size':10000},timeout=20).status_code==400)
    check('非法ID查询拒绝',requests.get(BASE+'/api/customers',params={**params,'kh':"' OR 1=1"},timeout=20).status_code==400)
    check('无结果查询返回空列表',get('/api/customers',params={**params,'kh':'ffffffff'})['items']==[])
    check('非法日期拒绝',requests.post(BASE+'/api/import',json={'source':'builtin','start':'broken'},timeout=20).status_code==400)
    check('跨站写入拒绝',requests.post(BASE+'/api/import',json={'source':'builtin'},headers={'Origin':'https://example.invalid'},timeout=20).status_code==403)
    reused=requests.post(BASE+'/api/import',json={'source':'builtin'},timeout=30).json()
    check('重复导入复用批次',reused.get('reused') and reused.get('id')==batch_id)
    try:
        # Missing fields must fail and leave the successful batch active.
        bad=requests.post(BASE+'/api/import',files={'file':('测试_缺字段.csv',b'kh,je\n00000001,1\n','text/csv')},timeout=30).json()
        bad_status=wait_batch(bad['id'])
        check('缺字段导入失败且上一成功结果保留',bad_status['status']=='failed' and get('/api/summary')['batch']['id']==batch_id)
        # Exercise actual multipart CSV import using the existing teaching-data subset.
        with (ROOT/'data/processed/retail_2017_starter.csv').open('rb') as f:
            uploaded=requests.post(BASE+'/api/import',files={'file':('retail_2017_starter.csv',f,'text/csv')},timeout=120)
        uploaded.raise_for_status();u=uploaded.json();status=wait_batch(u['id'])
        check('现有教学CSV上传到数据库完整流程',status['status']=='succeeded',{'duration_seconds':status['duration_seconds']})
        us=get('/api/summary',params={'batch_id':u['id']})['summary']
        check('CSV上传与全量原始分析结果一致',all(us[k]==s[k] for k in ['detail_count','event_count','customer_count','amount_cents']))
        # Explicit synthetic fixture for Excel, not claimed as research data.
        fixture=dict(zip(FIELDS,['00000001','2017-12-31 12:00:00','sku','1','100','12.34','合成测试商品','','1','abcd','','']))
        buffer=io.BytesIO();pd.DataFrame([fixture]).to_excel(buffer,index=False,engine='openpyxl');buffer.seek(0)
        x=requests.post(BASE+'/api/import',files={'file':('合成测试_Excel流程.xlsx',buffer.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},timeout=30).json()
        xs=wait_batch(x['id']);summary=get('/api/summary',params={'batch_id':x['id']})['summary']
        check('Excel上传清洗计算保存流程_合成测试',xs['status']=='succeeded' and (summary['detail_count'],summary['event_count'],summary['amount_cents'])==(1,1,1234))
        # Valid file but an empty time window is a failed batch, not a fake successful analysis.
        no=requests.post(BASE+'/api/import',json={'source_batch':x['id'],'start':'2016-01-01','end':'2017-01-01','reference':'2017-01-01'},timeout=30).json()
        ns=wait_batch(no['id'])
        check('清洗后空数据失败且有效结果保留',ns['status']=='failed' and get('/api/summary')['batch']['id']==x['id'])
    finally:
        requests.post(BASE+'/api/batches/'+batch_id+'/activate',timeout=20).raise_for_status()
    result={'checked_at':datetime.now().isoformat(timespec='seconds'),'batch_id':batch_id,'elapsed_seconds':round(time.perf_counter()-started,3),
            'counts':{k:s[k] for k in ['detail_count','event_count','customer_count','amount_cents']},'checks':checks}
    (ROOT/'docs/系统验证结果.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('All',len(checks),'checks passed',flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
