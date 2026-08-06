import duckdb
import re

con = duckdb.connect('/scratch/ccampb47/mimic_data.duckdb')

with open('utils/niv-durations.sql', 'r') as f:
    sql = f.read()

# Remove SET SEARCH_PATH
sql = re.sub(r'SET SEARCH_PATH.*?;', '', sql, flags=re.IGNORECASE)

# Change MATERIALIZED VIEW to TABLE
sql = re.sub(r'DROP\s+MATERIALIZED\s+VIEW\s+IF\s+EXISTS\s+nivdurations\s+CASCADE;', 'DROP TABLE IF EXISTS public.nivdurations;', sql, flags=re.IGNORECASE)
sql = re.sub(r'create\s+MATERIALIZED\s+VIEW\s+nivdurations\s+as', 'CREATE TABLE public.nivdurations AS', sql, flags=re.IGNORECASE)

# Fix extract epoch for interval in DuckDB
sql = re.sub(r'extract\(epoch from max\(charttime\)-min\(charttime\)\)', "date_diff('second', min(charttime), max(charttime))", sql, flags=re.IGNORECASE)

# Add schema
sql = sql.replace('from chartevents ce', 'from public.chartevents ce')

# Run it
print("Running query to create nivdurations...")
con.execute(sql)
print("Done!")
