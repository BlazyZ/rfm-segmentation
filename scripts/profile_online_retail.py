"""Read-only checks of the original UCI Online Retail transaction workbook."""
from pathlib import Path
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'data/raw/Online Retail.xlsx'
df = pd.read_excel(source, engine='openpyxl')
cancelled = df['InvoiceNo'].astype(str).str.upper().str.startswith('C')
eligible = df['CustomerID'].notna() & df['Quantity'].gt(0) & df['UnitPrice'].gt(0) & ~cancelled
purchases = df.loc[eligible].copy()
dedup = purchases.drop_duplicates().copy()
dedup['LineAmount'] = dedup['Quantity'] * dedup['UnitPrice']
reference_date = df['InvoiceDate'].max().normalize() + pd.Timedelta(days=1)
rfm = dedup.groupby('CustomerID').agg(
    last_purchase=('InvoiceDate', 'max'),
    frequency=('InvoiceNo', 'nunique'),
    monetary=('LineAmount', 'sum'),
)
rfm['recency'] = (reference_date - rfm['last_purchase'].dt.normalize()).dt.days
report = {
    'source_url': 'https://archive.ics.uci.edu/dataset/352/online+retail',
    'download_url': 'https://archive.ics.uci.edu/static/public/352/online+retail.zip',
    'xlsx_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'rows': len(df), 'columns': list(df.columns),
    'date_min': str(df['InvoiceDate'].min()), 'date_max': str(df['InvoiceDate'].max()),
    'missing_counts': df.isna().sum().astype(int).to_dict(),
    'missing_percent': (df.isna().mean()*100).round(4).to_dict(),
    'exact_duplicate_rows_beyond_first': int(df.duplicated().sum()),
    'distinct_known_customers': int(df['CustomerID'].nunique()),
    'distinct_invoice_identifiers_including_cancellations': int(df['InvoiceNo'].nunique()),
    'countries': int(df['Country'].nunique()),
    'cancellation_lines': int(cancelled.sum()),
    'nonpositive_quantity_lines': int(df['Quantity'].le(0).sum()),
    'nonpositive_unit_price_lines': int(df['UnitPrice'].le(0).sum()),
    'rfm_purchase_scope': 'CustomerID present, Quantity > 0, UnitPrice > 0, InvoiceNo does not start C. Excludes returns from purchase RFM; not a net-sales definition.',
    'eligible_purchase_lines_before_deduplication': len(purchases),
    'eligible_purchase_lines_after_exact_deduplication': len(dedup),
    'deduplication_caveat': 'Exact duplicates are candidate duplicates; removing them is a provisional policy that needs to be documented, since the source has no unique line ID.',
    'eligible_distinct_purchase_invoices': int(dedup['InvoiceNo'].nunique()),
    'rfm_customers': len(rfm),
    'customers_with_at_least_two_purchase_invoices': int(rfm['frequency'].ge(2).sum()),
    'rfm_reference_date': str(reference_date.date()),
    'raw_monthly_line_counts': {str(k):int(v) for k,v in df.groupby(df['InvoiceDate'].dt.to_period('M')).size().items()},
    'notes': [
        'Rows are transaction lines, not independent orders.',
        'UK retailer, historical data; prices are GBP. Final December is incomplete.',
        'Missing customer identifiers cannot be invented for segmentation.',
        'No age, gender, marketing channel, cost or profit fields.',
        'RFM frequency counts distinct invoices, not lines; recency uses dataset endpoint, not current date.',
        'This report checks internal data usability, not an independent audit of real business transactions.',
    ],
}
out = ROOT / 'research'
out.mkdir(exist_ok=True)
(out/'online_retail_profile.json').write_text(json.dumps(report, indent=2, ensure_ascii=False),encoding='utf-8')
print(json.dumps(report, indent=2, ensure_ascii=False))
