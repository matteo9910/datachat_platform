import psycopg2
conn = psycopg2.connect('postgresql://datachat_user:AIEngineeringPOC@localhost:5432/datachat_db')
cur = conn.cursor()
cur.execute('SELECT nl_query, llm_provider, success, execution_time_ms, result_rows FROM poc_metadata.query_history ORDER BY created_at DESC LIMIT 5')
for row in cur.fetchall():
    print(f'Query: {row[0][:50]}... | Provider: {row[1]} | Success: {row[2]} | Time: {row[3]}ms | Rows: {row[4]}')
conn.close()
