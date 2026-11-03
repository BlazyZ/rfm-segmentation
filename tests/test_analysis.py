from pathlib import Path
import pandas as pd
import pytest
from rfm.analysis import FIELDS, clean_file, compute_rfm, validate_period

def row(**updates):
    record = dict(zip(FIELDS, ['00000001','2017-12-31 23:59:59.123','sku','1','99','10.10','测试商品','','1','abcd','','']))
    record.update(updates)
    return record

def clean(tmp_path, rows):
    path = tmp_path/'sample.csv'
    pd.DataFrame(rows).to_csv(path,index=False,encoding='utf-8-sig')
    return clean_file(path,tmp_path/'out')

def test_events_not_lines_receipts_or_dates(tmp_path):
    records = [row(),row(je='20.20'),row(dtime='2017-12-31 23:59:59.124'),
               row(dtime='2017-12-30',syjh='2'),row(kh='00000002',dtime='2017-01-01',je='0.01')]
    df,q = clean(tmp_path,records)
    r,rules,audit = compute_rfm(df)
    a = r.set_index('kh').loc['00000001']
    assert (a.r,a.f,a.m_cents,a.detail_count)==(1,3,5050,4)
    b = r.set_index('kh').loc['00000002']
    assert (b.r,b.f,b.m_cents)==(365,1,1)
    assert audit['purchase_events']==4
    assert audit['distinct_receipt_ids']==1
    assert audit['groups_with_multiple_timestamps']==1

def test_overlap_audit_and_window_edges(tmp_path):
    df,q = clean(tmp_path,[row(dtime='2017-01-01'),row(dtime='2018-01-01'),
        row(kh='',je='-1',sl='0'),row(kh='123',djh='1'),row(dtime='broken'),
        row(syjh=''),row(je='0.001'),row(sl='inf'),row(je='nan')])
    assert len(df)==1
    assert q['total_rows']==9 and q['excluded_rows']==8
    assert sum(q['primary_reasons'].values())==q['excluded_rows']
    assert sum(q['reasons'].values())>q['excluded_rows']
    excluded=pd.read_csv(tmp_path/'out/excluded.csv')
    assert len(excluded)==8
    assert excluded['source_row'].min()==3

def test_duplicates_retained_and_je_used(tmp_path):
    df,q=clean(tmp_path,[row(),row()])
    assert q['exact_duplicate_candidates']==1
    assert len(df)==2
    r,_,_=compute_rfm(df)
    assert (r.iloc[0].m_cents,r.iloc[0].f)==(2020,1)

def test_score_directions_ties_and_coverage(tmp_path):
    rows=[]
    for n in range(1,11):
        for day in range(1,n+1):
            rows.append(row(kh=f'{n:08x}',dtime=f'2017-12-{day:02}',je=str(n)))
    df,_=clean(tmp_path,rows)
    r,rules,_=compute_rfm(df)
    r=r.sort_values('f')
    assert r.f_score.is_monotonic_increasing
    assert r.m_score.is_monotonic_increasing
    assert r.r_score.is_monotonic_increasing  # later date has smaller R
    assert r.segment.notna().all()
    tied=pd.concat([df,df.assign(kh='000000ff')],ignore_index=True)
    rr,_,_=compute_rfm(tied)
    for metric in ['r','f','m_cents']:
        score=metric[0]+'_score'
        assert rr.groupby(metric)[score].nunique().max()==1
    for metric in ['r','f','m_cents']:
        bounds=rules['boundaries'][metric]
        for _,item in r.iterrows():
            interval=sum(item[metric]>b for b in bounds)
            assert item[metric[0]+'_score']==(5-interval if metric=='r' else 1+interval)

def test_missing_fields_and_empty_result(tmp_path):
    bad=tmp_path/'missing.csv';bad.write_text('kh,je\n00000001,1\n',encoding='utf-8')
    with pytest.raises(ValueError,match='缺少必要字段'):
        clean_file(bad,tmp_path/'out')
    with pytest.raises(ValueError,match='没有有效'):
        clean(tmp_path,[row(je='0')])

@pytest.mark.parametrize('dates',[('2018-01-01','2017-01-01','2018-01-01'),('x','2018-01-01','2018-01-01'),('2017-01-01','2018-01-01','2017-12-31'),('2017-01-01 01:00','2018-01-01','2018-01-01'),('2017-01-01','2018-01-01',None),('2017-01-01Z','2018-01-01','2018-01-01')])
def test_invalid_period(dates):
    with pytest.raises(ValueError):validate_period(*dates)

def test_excel_identifiers_and_multiple_sheet_rejection(tmp_path):
    path=tmp_path/'sample.xlsx'
    with pd.ExcelWriter(path,engine='openpyxl') as w:
        pd.DataFrame({'note':['这是合成测试文件']}).to_excel(w,sheet_name='说明',index=False)
        pd.DataFrame([row()]).to_excel(w,sheet_name='交易',index=False)
    df,_=clean_file(path,tmp_path/'out')
    assert df.kh.iloc[0]=='00000001'
    with pd.ExcelWriter(path,engine='openpyxl') as w:
        for sheet in ['一','二']:pd.DataFrame([row()]).to_excel(w,sheet_name=sheet,index=False)
    with pytest.raises(ValueError,match='恰有一张'):clean_file(path,tmp_path/'out2')
