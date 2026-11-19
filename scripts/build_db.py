"""Load the cleaned Olist star schema (CSV output of olist-bi-dashboard/scripts/build_model.py) into DuckDB.

Usage: python scripts/build_db.py [--src ../olist-bi-dashboard/data/model]
"""
import argparse
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "olist.duckdb"
TABLES = ["fact_orders", "fact_order_items", "dim_customer", "dim_product", "dim_seller", "dim_date",
          "cohort_retention"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT.parent / "olist-bi-dashboard" / "data" / "model"))
    src = Path(ap.parse_args().src)
    DB.parent.mkdir(exist_ok=True)
    DB.unlink(missing_ok=True)
    con = duckdb.connect(str(DB))
    for t in TABLES:
        con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_csv_auto(?, header=true, sample_size=-1)",
                    [str(src / f"{t}.csv")])
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"{t:18s} {n:>8,} rows")
    # Sanity check carried over from the dashboard project: item-level GMV equals order-level GMV.
    item, order = con.execute("""
        SELECT (SELECT sum(item_gmv) FROM fact_order_items WHERE is_valid),
               (SELECT sum(order_value) FROM fact_orders WHERE is_valid)""").fetchone()
    assert abs(item - order) < 1, (item, order)
    con.close()
    print(f"-> {DB} ({DB.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
