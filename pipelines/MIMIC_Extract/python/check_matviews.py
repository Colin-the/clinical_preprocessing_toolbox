import psycopg2
import os

pg_host = os.environ.get('PGHOST', '/scratch/ccampb47/mimic_pg_socket')
pg_conn = psycopg2.connect(dbname='mimic', user='mimic', password='mimic', host=pg_host)
cur = pg_conn.cursor()
cur.execute("SELECT schemaname, matviewname FROM pg_matviews WHERE schemaname IN ('public', 'mimiciii')")
print(cur.fetchall())
