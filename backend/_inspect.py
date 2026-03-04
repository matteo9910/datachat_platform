import psycopg2
conn = psycopg2.connect('postgresql://datachat_user:AIEngineeringPOC@localhost:5432/datachat_db')
cur = conn.cursor()
cur.execute("SELECT schemaname, tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2")
for r in cur.fetchall():
    print(r[0] + '.' + r[1])
print('---')
cur.execute("SELECT table_schema, table_name, column_name, data_type FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog','information_schema','poc_metadata') ORDER BY 1,2,ordinal_position")
prev = None
for r in cur.fetchall():
    key = r[0] + '.' + r[1]
    if key != prev:
        print('\n' + key + ':')
        prev = key
    print('  ' + r[2] + ' (' + r[3] + ')')
conn.close()
