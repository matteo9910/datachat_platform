import psycopg2
conn = psycopg2.connect('postgresql://datachat_user:AIEngineeringPOC@localhost:5432/datachat_db')
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'poc_metadata'")
print([r[0] for r in cur.fetchall()])
conn.close()
