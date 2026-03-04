"""
Import Kaggle Superstore Sales dataset into PostgreSQL public.orders table.

This script:
  1. Reads Sample-Superstore.csv from database/data/
  2. Creates the public.orders table if it does not exist
  3. Maps CSV columns (with spaces like "Order ID") to snake_case
  4. Converts dates from MM/DD/YYYY format to Python date objects
  5. Imports ~9994 rows using batch insert (page_size=1000)
  6. Creates indexes on key columns for query performance
  7. Verifies the import with row count and category distribution

Usage:
  cd <project_root>
  backend\\venv\\Scripts\\python scripts\\import_kaggle_dataset.py

Requires: psycopg2-binary, pandas, python-dotenv
"""

import os
import sys
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Load .env from project root (one level up from scripts/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

DATABASE_URL = os.getenv("DATABASE_URL")
CSV_PATH = os.path.join(PROJECT_ROOT, "database", "data", "Sample-Superstore.csv")

# ---------------------------------------------------------------------------
# Column mapping: CSV header (with spaces) -> PostgreSQL snake_case
# ---------------------------------------------------------------------------

COLUMN_MAPPING = {
    "Row ID": "row_id",
    "Order ID": "order_id",
    "Order Date": "order_date",
    "Ship Date": "ship_date",
    "Ship Mode": "ship_mode",
    "Customer ID": "customer_id",
    "Customer Name": "customer_name",
    "Segment": "segment",
    "Country": "country",
    "City": "city",
    "State": "state",
    "Postal Code": "postal_code",
    "Region": "region",
    "Product ID": "product_id",
    "Category": "category",
    "Sub-Category": "sub_category",
    "Product Name": "product_name",
    "Sales": "sales",
    "Quantity": "quantity",
    "Discount": "discount",
    "Profit": "profit",
}

# ---------------------------------------------------------------------------
# SQL Statements
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.orders (
    row_id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL,
    order_date DATE NOT NULL,
    ship_date DATE,
    ship_mode VARCHAR(50),
    customer_id VARCHAR(50) NOT NULL,
    customer_name VARCHAR(100),
    segment VARCHAR(50),
    country VARCHAR(50),
    city VARCHAR(100),
    state VARCHAR(50),
    postal_code VARCHAR(20),
    region VARCHAR(50),
    product_id VARCHAR(50) NOT NULL,
    category VARCHAR(50),
    sub_category VARCHAR(50),
    product_name VARCHAR(200),
    sales DECIMAL(10,2) NOT NULL,
    quantity INTEGER NOT NULL,
    discount DECIMAL(5,2),
    profit DECIMAL(10,2)
);
"""

INSERT_SQL = """
INSERT INTO public.orders (
    order_id, order_date, ship_date, ship_mode,
    customer_id, customer_name, segment,
    country, city, state, postal_code, region,
    product_id, category, sub_category, product_name,
    sales, quantity, discount, profit
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
"""

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_orders_order_date ON public.orders(order_date);",
    "CREATE INDEX IF NOT EXISTS idx_orders_category ON public.orders(category);",
    "CREATE INDEX IF NOT EXISTS idx_orders_sub_category ON public.orders(sub_category);",
    "CREATE INDEX IF NOT EXISTS idx_orders_region ON public.orders(region);",
    "CREATE INDEX IF NOT EXISTS idx_orders_state ON public.orders(state);",
    "CREATE INDEX IF NOT EXISTS idx_orders_segment ON public.orders(segment);",
    "CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON public.orders(customer_id);",
    "CREATE INDEX IF NOT EXISTS idx_orders_product_id ON public.orders(product_id);",
]

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------


def create_orders_table(conn):
    """Create the public.orders table if it does not exist."""
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
        conn.commit()
    print("[OK] Table public.orders created (or already exists)")


def create_indexes(conn):
    """Create performance indexes on key columns.

    If datachat_user is not the table owner, index creation may fail.
    In that case, indexes should be created by the table owner (postgres).
    """
    try:
        with conn.cursor() as cur:
            for idx_sql in INDEX_STATEMENTS:
                cur.execute(idx_sql)
            conn.commit()
        print("[OK] Indexes created on key columns")
    except psycopg2.Error as e:
        conn.rollback()
        print(f"[WARN] Could not create indexes (permission issue): {e}")
        print("       Indexes may need to be created by the table owner (postgres user).")
        print("       This is non-blocking -- queries will still work, just slower.")


def import_csv_data(conn, csv_path):
    """Read CSV file and batch-insert rows into public.orders."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    print(f"     Reading CSV: {csv_path}")
    df = pd.read_csv(csv_path, encoding="utf-8")
    print(f"     CSV columns found: {list(df.columns)}")

    # Rename columns from "Order ID" style to "order_id" style
    df.rename(columns=COLUMN_MAPPING, inplace=True)

    # Convert date columns -- the CSV uses DD/MM/YYYY format (dayfirst=True)
    # Using dayfirst=True handles dates like "08/11/2017" as 8-Nov-2017
    df["order_date"] = pd.to_datetime(df["order_date"], dayfirst=True).dt.date
    df["ship_date"] = pd.to_datetime(df["ship_date"], dayfirst=True).dt.date

    # Some CSV variants may not have quantity/discount/profit columns.
    # Add defaults if missing so the INSERT always has all columns.
    if "quantity" not in df.columns:
        df["quantity"] = 1
    if "discount" not in df.columns:
        df["discount"] = 0.0
    if "profit" not in df.columns:
        df["profit"] = 0.0

    # Handle NaN in postal_code (some rows have float NaN)
    df["postal_code"] = df["postal_code"].fillna("").astype(str)
    # Clean up ".0" suffix from float-converted postal codes
    df["postal_code"] = df["postal_code"].apply(
        lambda x: x.replace(".0", "") if x.endswith(".0") else x
    )

    print(f"     Rows to import: {len(df)}")

    # Delete existing data for clean import.
    # Using DELETE instead of TRUNCATE to avoid sequence ownership issues.
    with conn.cursor() as cur:
        cur.execute("DELETE FROM public.orders;")
        conn.commit()
    print("[OK] Table orders cleared (fresh import)")

    # Build list of tuples for batch insert
    data_tuples = []
    for _, row in df.iterrows():
        data_tuples.append(
            (
                row["order_id"],
                row["order_date"],
                row["ship_date"],
                row["ship_mode"],
                row["customer_id"],
                row["customer_name"],
                row["segment"],
                row["country"],
                row["city"],
                row["state"],
                str(row["postal_code"]),
                row["region"],
                row["product_id"],
                row["category"],
                row["sub_category"],
                row["product_name"],
                float(row["sales"]),
                int(row["quantity"]),
                float(row["discount"]),
                float(row["profit"]),
            )
        )

    # Batch insert with page_size=1000 for performance
    with conn.cursor() as cur:
        execute_batch(cur, INSERT_SQL, data_tuples, page_size=1000)
        conn.commit()

    print(f"[OK] {len(data_tuples)} rows imported successfully")


def verify_import(conn):
    """Run verification queries and print results."""
    with conn.cursor() as cur:
        # Total row count
        cur.execute("SELECT COUNT(*) FROM public.orders;")
        count = cur.fetchone()[0]
        print(f"[OK] Verification: {count} rows in public.orders")

        # Category distribution
        cur.execute(
            """
            SELECT category, COUNT(*) as cnt
            FROM public.orders
            GROUP BY category
            ORDER BY category;
            """
        )
        categories = cur.fetchall()
        print("\n     Category distribution:")
        for cat, cnt in categories:
            print(f"       - {cat}: {cnt} rows")

        # Date range
        cur.execute(
            "SELECT MIN(order_date), MAX(order_date) FROM public.orders;"
        )
        min_date, max_date = cur.fetchone()
        print(f"\n     Date range: {min_date} to {max_date}")

        # Region distribution
        cur.execute(
            """
            SELECT region, COUNT(*) as cnt
            FROM public.orders
            GROUP BY region
            ORDER BY cnt DESC;
            """
        )
        regions = cur.fetchall()
        print("\n     Region distribution:")
        for region, cnt in regions:
            print(f"       - {region}: {cnt} rows")

    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not DATABASE_URL:
        print("[ERROR] DATABASE_URL not found in .env file")
        print("        Make sure .env exists in the project root with:")
        print("        DATABASE_URL=postgresql://datachat_user:...@localhost:5432/datachat_db")
        sys.exit(1)

    # Mask password in printed connection string
    display_url = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL

    print("=" * 60)
    print("  IMPORT DATASET: Kaggle Superstore Sales")
    print("=" * 60)
    print()

    try:
        conn = psycopg2.connect(DATABASE_URL)
        print(f"[OK] Connected to database: {display_url}")
        print()

        create_orders_table(conn)
        import_csv_data(conn, CSV_PATH)
        create_indexes(conn)
        print()
        row_count = verify_import(conn)

        conn.close()

        print()
        print("=" * 60)
        if row_count and row_count > 9000:
            print("  IMPORT COMPLETED SUCCESSFULLY")
        else:
            print(f"  WARNING: Only {row_count} rows imported (expected ~9994)")
        print("=" * 60)

    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    except psycopg2.Error as e:
        print(f"[ERROR] Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
