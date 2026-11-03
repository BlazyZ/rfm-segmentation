"""Reproducible positive-purchase RFM analysis. Money is stored as integer cents."""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import pandas as pd

FIELDS = ['kh', 'dtime', 'spbm', 'sl', 'sj', 'je', 'spmc', 'jf', 'syjh', 'djh', 'gzbm', 'gzmc']
EVENT_KEY = ['kh', 'dtime', 'syjh', 'djh']
SEGMENTS = {
    '111': '重要价值客户', '101': '重要发展客户', '011': '重要保持客户', '001': '重要挽留客户',
    '110': '一般价值客户', '100': '一般发展客户', '010': '一般保持客户', '000': '一般挽留客户',
}
REASONS = {
    'invalid_time': '无效交易时间', 'outside_window': '观察窗口外', 'missing_customer': '缺少客户标识',
    'invalid_customer': '客户标识不符8位十六进制', 'invalid_receipt': '单据标识不符4位十六进制',
    'missing_register': '缺少收银机标识', 'invalid_quantity': '数量无效或非正',
    'invalid_amount': '金额无效、非正、超过范围或小数超过两位',
}

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def validate_period(start, end, reference):
    try:
        dates = [pd.Timestamp(x) for x in (start, end, reference)]
        if any(x.tzinfo is not None or x != x.normalize() for x in dates):
            raise ValueError()
        if not dates[0] < dates[1] <= dates[2]:
            raise ValueError()
        if (dates[2] - dates[0]).days > 36525:
            raise ValueError()
    except Exception as exc:
        raise ValueError('日期须为有效日期，且开始日 < 结束日 ≤ 基准日，跨度不超过100年。') from exc
    return dates

def read_chunks(path):
    if Path(path).suffix.lower() == '.csv':
        # Strict decoding and parsing; a malformed row must never disappear silently.
        for encoding in ('utf-8-sig', 'gb18030'):
            try:
                with open(path, encoding=encoding) as f:
                    for block in iter(lambda: f.read(1024 * 1024), ''):
                        pass
                break
            except UnicodeDecodeError:
                if encoding == 'gb18030':
                    raise ValueError('CSV编码无法识别，请另存为UTF-8 CSV。')
        yield from pd.read_csv(path, dtype=str, encoding=encoding, keep_default_na=False, chunksize=100000)
    else:
        with pd.ExcelFile(path, engine='openpyxl') as book:
            matching = [name for name in book.sheet_names
                        if set(FIELDS).issubset(pd.read_excel(book, sheet_name=name, nrows=0).columns)]
            if len(matching) != 1:
                raise ValueError('Excel必须恰有一张包含12个交易字段的工作表；会员信息表不能作为交易表导入。')
            yield pd.read_excel(book, sheet_name=matching[0], dtype=str, keep_default_na=False)

def clean_file(source, output_dir, start='2017-01-01', end='2018-01-01', reference='2018-01-01', progress=None):
    start_dt, end_dt, _ = validate_period(start, end, reference)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    excluded_path = output_dir / 'excluded.csv'
    accepted = []
    report = {'total_rows': 0, 'accepted_rows': 0, 'excluded_rows': 0,
              'reasons': {k: 0 for k in REASONS}, 'primary_reasons': {k: 0 for k in REASONS},
              'reason_labels': REASONS, 'duplicates_removed': 0}
    wrote_excluded = False
    for raw in read_chunks(source):
        missing = set(FIELDS) - set(raw.columns)
        if missing:
            raise ValueError('缺少必要字段：' + '、'.join(sorted(missing)))
        raw = raw[FIELDS].copy()
        row_numbers = np.arange(report['total_rows'] + 2, report['total_rows'] + len(raw) + 2)
        report['total_rows'] += len(raw)
        times = pd.to_datetime(raw.dtime, format='mixed', errors='coerce')
        # Naive local times only. An unexpected timezone is a structural error.
        if not pd.api.types.is_datetime64_any_dtype(times) or getattr(times.dt, 'tz', None) is not None:
            raise ValueError('交易时间必须为不带时区的本地时间。')
        quantity = pd.to_numeric(raw.sl, errors='coerce')
        amount = pd.to_numeric(raw.je, errors='coerce')
        cents = (amount * 100).round()
        masks = {
            'invalid_time': times.isna(),
            'outside_window': times.notna() & ~(times.ge(start_dt) & times.lt(end_dt)),
            'missing_customer': raw.kh.str.strip().eq(''),
            'invalid_customer': raw.kh.str.strip().ne('') & ~raw.kh.str.fullmatch(r'[0-9a-fA-F]{8}'),
            'invalid_receipt': ~raw.djh.str.fullmatch(r'[0-9a-fA-F]{4}'),
            'missing_register': raw.syjh.str.strip().eq(''),
            'invalid_quantity': ~np.isfinite(quantity) | quantity.le(0),
            'invalid_amount': ~np.isfinite(amount) | amount.le(0) | amount.gt(1e10) | (amount * 100 - cents).abs().gt(0.0001),
        }
        reasons = pd.Series('', index=raw.index, dtype='object')
        primary = pd.Series('', index=raw.index, dtype='object')
        for code, mask in masks.items():
            report['reasons'][code] += int(mask.sum())
            first = mask & primary.eq('')
            report['primary_reasons'][code] += int(first.sum())
            primary.loc[first] = code
            reasons.loc[mask] += code + ';'
        valid = reasons.eq('')
        bad = raw.loc[~valid].copy()
        if len(bad):
            bad.insert(0, 'source_row', row_numbers[~valid.to_numpy()])
            bad['primary_reason'] = primary.loc[~valid]
            bad['all_reasons'] = reasons.loc[~valid].str.rstrip(';')
            bad.to_csv(excluded_path, index=False, mode='a' if wrote_excluded else 'w',
                       header=not wrote_excluded, encoding='utf-8-sig' if not wrote_excluded else 'utf-8')
            wrote_excluded = True
        good = raw.loc[valid].copy()
        good.insert(0, 'source_row', row_numbers[valid.to_numpy()])
        good['dtime'] = times.loc[valid]
        good['amount_cents'] = cents.loc[valid].astype('int64')
        accepted.append(good)
        report['accepted_rows'] += len(good)
        report['excluded_rows'] += len(bad)
        if progress:
            progress(f'已核查 {report["total_rows"]:,} 条明细，保留 {report["accepted_rows"]:,} 条')
    if not report['accepted_rows']:
        raise ValueError('清洗后没有有效购买明细，请检查交易字段、日期范围和标识格式。')
    df = pd.concat(accepted, ignore_index=True)
    report['exact_duplicate_candidates'] = int(df[FIELDS].duplicated().sum())
    report['duplicate_policy'] = '保留完全相同行；缺少唯一明细ID，不能证明相同行就是错误。'
    df.to_csv(output_dir / 'cleaned.csv', index=False, encoding='utf-8-sig')
    if not wrote_excluded:
        pd.DataFrame(columns=['source_row', *FIELDS, 'primary_reason', 'all_reasons']).to_csv(excluded_path, index=False, encoding='utf-8-sig')
    return df, report

def compute_rfm(df, reference='2018-01-01'):
    events = df[EVENT_KEY].drop_duplicates()
    groups = df.groupby('kh', sort=True)
    result = groups.agg(last_purchase=('dtime', 'max'), m_cents=('amount_cents', 'sum'), detail_count=('kh', 'size'))
    result['r'] = (pd.Timestamp(reference) - result.last_purchase.dt.normalize()).dt.days
    result['f'] = events.groupby('kh').size()
    rules = {'method': '五档经验分位数；值等于阈值归入数值较低档；同值同分', 'high_score': 4,
             'quantiles': [0.2, 0.4, 0.6, 0.8], 'boundaries': {}, 'event_key': EVENT_KEY,
             'segment_map': SEGMENTS, 'reference_date': reference, 'version': 'rfm-v1'}
    for metric in ('r', 'f', 'm_cents'):
        boundaries = result[metric].quantile(rules['quantiles']).tolist()
        rules['boundaries'][metric] = boundaries
        bins = np.searchsorted(boundaries, result[metric].to_numpy(), side='left')
        result[metric[0] + '_score'] = (5 - bins) if metric == 'r' else (1 + bins)
    bits = (result[['r_score', 'f_score', 'm_score']].ge(4).astype(int).astype(str)).agg(''.join, axis=1)
    result['segment_code'] = bits
    result['segment'] = bits.map(SEGMENTS)
    result = result.reset_index()
    if result.segment.isna().any() or result.kh.duplicated().any():
        raise RuntimeError('客户分群覆盖检查失败。')
    # Event-key audit quantifies the effect of using full timestamps rather than dates.
    event_audit = events.copy()
    event_audit['date'] = event_audit.dtime.dt.normalize()
    receipt_groups = event_audit.groupby(['kh', 'date', 'syjh', 'djh']).size()
    audit = {
        'purchase_events': len(events), 'distinct_receipt_ids': int(events.djh.nunique()),
        'customer_date_register_receipt_groups': len(receipt_groups),
        'groups_with_multiple_timestamps': int(receipt_groups.gt(1).sum()),
        'repeated_receipt_ids': int(events.groupby('djh').size().gt(1).sum()),
        'customers_with_multiple_events': int(result.f.ge(2).sum()),
    }
    return result, rules, audit

def build_summary(df, result, rules, report, start, end, reference):
    def ranking(key, label):
        data = df.groupby(key, dropna=False).agg(amount_cents=('amount_cents', 'sum'), details=('kh', 'size')).reset_index()
        data = data.sort_values(['amount_cents', key], ascending=[False, True]).head(10)
        data = data.rename(columns={key: 'name'})
        data['name'] = data['name'].replace('', '未提供')
        return json.loads(data.to_json(orient='records', force_ascii=False))
    monthly = df.assign(month=df.dtime.dt.strftime('%Y-%m'))
    lines = monthly.groupby('month').agg(amount_cents=('amount_cents', 'sum'), details=('kh', 'size'))
    ev = monthly.drop_duplicates(EVENT_KEY).groupby('month').size()
    lines['events'] = ev
    lines = lines.reindex(pd.period_range(pd.Timestamp(start), pd.Timestamp(end) - pd.Timedelta(days=1), freq='M').astype(str), fill_value=0).rename_axis('month').reset_index()
    segments = []
    for code, name in SEGMENTS.items():
        part = result[result.segment_code.eq(code)]
        segments.append({'code': code, 'name': name, 'customers': len(part), 'amount_cents': int(part.m_cents.sum()),
                         'avg_r': round(float(part.r.mean()), 2) if len(part) else None,
                         'avg_f': round(float(part.f.mean()), 2) if len(part) else None,
                         'avg_m_cents': round(float(part.m_cents.mean()), 2) if len(part) else None})
    return {'start': start, 'end': end, 'reference': reference, 'detail_count': len(df),
            'customer_count': len(result), 'event_count': int(result.f.sum()), 'amount_cents': int(result.m_cents.sum()),
            'days_with_purchases': int(df.dtime.dt.normalize().nunique()),
            'monthly': json.loads(lines.to_json(orient='records')), 'products': ranking('spbm', 'spmc'),
            'counters': ranking('gzmc', 'gzmc'), 'segments': segments,
            'rules': rules, 'quality': report,
            'distribution': {k: {str(q): float(result[k].quantile(q)) for q in [0, .2, .4, .5, .6, .8, 1]} for k in ['r','f','m_cents']}}
