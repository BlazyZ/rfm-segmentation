"""Measure actual sensitivity to the high-score threshold; leave official results intact."""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rfm import db, service
from rfm.analysis import SEGMENTS

def main():
    batch=service.get_batch()
    if not batch:raise RuntimeError('先完成正式数据分析')
    rows=db.query('SELECT kh,r,f,m_cents,r_score,f_score,m_score,segment_code FROM customer_rfm WHERE batch_id=%s',(batch['id'],))
    df=pd.DataFrame(rows)
    studies=[]
    for high in (3,4,5):
        codes=df[['r_score','f_score','m_score']].ge(high).astype(int).astype(str).agg(''.join,axis=1)
        studies.append({'high_score_at_least':high,'changed_customers':int(codes.ne(df.segment_code).sum()),
                        'groups':{SEGMENTS[c]:int(codes.eq(c).sum()) for c in SEGMENTS}})
    # A transparent fixed-interval alternative for comparison, not a validated standard.
    fixed={'r':[30,90,180,270],'f':[1,2,5,10],'m_cents':[100000,300000,500000,1000000]}
    scores=[]
    for metric in ['r','f','m_cents']:
        interval=np.searchsorted(fixed[metric],df[metric].to_numpy(),side='left')
        scores.append(5-interval if metric=='r' else 1+interval)
    fixed_codes=pd.DataFrame(np.array(scores).T>=4).astype(int).astype(str).agg(''.join,axis=1)
    result={'batch_id':batch['id'],'customer_count':len(df),'high_score_sensitivity':studies,
            'fixed_interval_comparison':{'boundaries':fixed,'high_score':4,'changed_customers':int(fixed_codes.ne(df.segment_code).sum()),
                                         'groups':{SEGMENTS[c]:int(fixed_codes.eq(c).sum()) for c in SEGMENTS}},
            'interpretation':'固定区间仅为明确列出的对照方案，无真实价值标签，不能据此计算准确率。正式规则维持经验分位数、高档≥4；阈值变化说明规则依赖，不证明哪套规则营销效果更优。'}
    (ROOT/'docs/规则敏感性结果.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Sensitivity saved. Official batch unchanged.')

if __name__=='__main__':main()
