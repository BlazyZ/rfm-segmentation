"""Profile the downloaded domestic retail teaching-data copy; preserve raw files."""
from pathlib import Path
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/raw/cumcm2018c/cumcm2018c2.csv"

def main():
    df = pd.read_csv(SOURCE, encoding="utf-8-sig", dtype=str)
    times = pd.to_datetime(df["dtime"], format="mixed", errors="coerce")
    amount = pd.to_numeric(df["je"], errors="coerce")
    quantity = pd.to_numeric(df["sl"], errors="coerce")
    price = pd.to_numeric(df["sj"], errors="coerce")
    has_customer = df["kh"].notna() & df["kh"].str.strip().ne("")
    valid = has_customer & times.notna() & amount.gt(0) & quantity.gt(0)
    purchases = df.loc[valid].copy()
    purchases["purchase_time"] = times.loc[valid]
    purchases["amount"] = amount.loc[valid]
    purchases["date"] = purchases["purchase_time"].dt.strftime("%Y-%m-%d")
    key = ["kh", "date", "syjh", "djh"]
    key_complete = purchases[key].notna().all(axis=1)
    orders = purchases.loc[key_complete, key].drop_duplicates()
    frequency = orders.groupby("kh").size()
    years = {}
    for year, part in purchases.groupby(purchases["purchase_time"].dt.year):
        years[str(year)] = {
            "positive_member_lines": len(part),
            "customers": int(part["kh"].nunique()),
            "amount": round(float(part["amount"].sum()), 2),
            "first_time": str(part["purchase_time"].min()),
            "last_time": str(part["purchase_time"].max()),
        }
    # A short receipt identifier may be reused. Measure before defining F.
    receipts = orders.groupby("djh").size()
    same_day_register = orders.groupby(["date", "syjh", "djh"])["kh"].nunique()
    order_times = purchases.loc[key_complete].groupby(key)["purchase_time"].agg(["min", "max"])
    long_duration = (order_times["max"] - order_times["min"]).gt(pd.Timedelta(minutes=30))
    result = {
        "source_file": str(SOURCE.relative_to(ROOT)),
        "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "bytes": SOURCE.stat().st_size,
        "rows": len(df),
        "columns": list(df.columns),
        "missing_by_column": {k: int(v) for k, v in df.isna().sum().items()},
        "time_start": str(times.min()), "time_end": str(times.max()),
        "invalid_times": int(times.isna().sum()),
        "known_customers_raw": int(df["kh"].nunique()),
        "nonpositive_amount_lines": int(amount.le(0).sum()),
        "invalid_amount_lines": int(amount.isna().sum()),
        "nonpositive_quantity_lines": int(quantity.le(0).sum()),
        "invalid_quantity_lines": int(quantity.isna().sum()),
        "exact_duplicate_candidates_after_first": int(df.duplicated().sum()),
        "amount_differs_from_quantity_times_price_lines": int((amount-quantity*price).abs().gt(0.011).sum()),
        "positive_member_purchase_lines": len(purchases),
        "positive_member_customers": int(purchases["kh"].nunique()),
        "positive_member_amount": round(float(purchases["amount"].sum()), 2),
        "provisional_order_key": key,
        "purchase_lines_missing_order_key": int((~key_complete).sum()),
        "provisional_orders": len(orders),
        "customers_with_two_or_more_provisional_orders": int(frequency.ge(2).sum()),
        "receipt_ids_used_in_multiple_provisional_orders": int(receipts.gt(1).sum()),
        "date_register_receipt_groups_with_multiple_customers": int(same_day_register.gt(1).sum()),
        "provisional_orders_spanning_over_30_minutes": int(long_duration.sum()),
        "yearly_positive_member_purchases": years,
        "note": "Counts are a preliminary quality check, not a finalized cleaning or RFM result. No duplicate rows removed."
    }
    # Conservative starter subset: quarantine malformed identifiers rather than
    # guessing how scientific-notation conversions damaged the originals.
    well_formed = df["kh"].str.fullmatch(r"[0-9a-fA-F]{8}", na=False)
    well_formed &= df["djh"].str.fullmatch(r"[0-9a-fA-F]{4}", na=False)
    in_2017 = times.ge("2017-01-01") & times.lt("2018-01-01")
    starter = df.loc[valid & well_formed & in_2017].copy()
    timestamp_key = ["kh", "dtime", "syjh", "djh"]
    starter_orders = starter[timestamp_key].drop_duplicates()
    starter_frequency = starter_orders.groupby("kh").size()
    starter_path = ROOT / "data/processed/retail_2017_starter.csv"
    starter_path.parent.mkdir(parents=True, exist_ok=True)
    starter.to_csv(starter_path, index=False, encoding="utf-8-sig")
    result["conservative_2017_starter"] = {
        "file": str(starter_path.relative_to(ROOT)),
        "lines": len(starter),
        "customers": int(starter["kh"].nunique()),
        "provisional_timestamp_orders": len(starter_orders),
        "customers_with_at_least_two_timestamp_orders": int(starter_frequency.ge(2).sum()),
        "days_with_purchases": int(pd.to_datetime(starter["dtime"], format="mixed").dt.normalize().nunique()),
        "order_key": timestamp_key,
        "analysis_reference_date": "2018-01-01",
        "rules": "2017 only; nonmissing customer; valid timestamp; quantity>0; amount>0; customer ID exactly 8 hex characters; receipt ID exactly 4 hex characters. No claim of recovering damaged IDs. No duplicate rows removed.",
    }
    out = ROOT / "research/domestic_retail_profile.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    main()

