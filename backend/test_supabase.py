import psycopg2
from psycopg2.extras import RealDictCursor

project_ref = "vdtdizltnesotxbbdjpq"
password = "AIEngineeringPOC2026"
pooler_host = "aws-0-eu-central-1.pooler.supabase.com"
pooler_user = f"postgres.{project_ref}"

# Prova porta 6543 (session pooler)
conn_string = f"postgresql://{pooler_user}:{password}@{pooler_host}:6543/postgres"
print(f"Trying port 6543: {pooler_host} as {pooler_user}")

try:
    conn = psycopg2.connect(conn_string, cursor_factory=RealDictCursor)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT version()")
    print(f"Connected! Version: {cur.fetchone()}")
    conn.close()
except Exception as e:
    print(f"Error port 6543: {e}")
