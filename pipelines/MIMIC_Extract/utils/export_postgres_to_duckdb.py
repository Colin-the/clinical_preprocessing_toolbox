#!/usr/bin/env python3
"""
Dump the loaded MIMIC Postgres database into a single DuckDB file.

This exists to kill the node-pinning problem. On Compute Canada the extractor
reaches Postgres over a Unix socket, so every extraction job has to be scheduled
onto the same node as the job holding the database open — which is why
apptainer/jobs/submit_all.sh needs a NODELIST and why a job landing elsewhere
fails with an unhelpful connection error. DuckDB is a file rather than a server:
once you have one, jobs run anywhere, in parallel, with no coordination at all.

The trade is that this export is slow and the result is large. Worth it if you're
going to re-run extractions repeatedly; not worth it for a single sweep.

Run once, while Postgres is still up. Afterwards, set DB_PATH and
docker/entrypoint.sh takes the DuckDB route.

  PGHOST=/path/to/socket PGPASSWORD=mimic \\
      python utils/export_postgres_to_duckdb.py --output $SCRATCH/mimic_data.duckdb

Needs psycopg2 and duckdb. See apptainer/jobs/job_export_duckdb.sh for the SLURM
version.
"""

import argparse
import os
import re
import sys

def get_tables(conn):
    """Everything in both schemas — raw MIMIC lives in mimiciii, the derived
    concept tables land in public, and the extractor reads from both.

    Views are included as well as tables, since several concepts are defined as
    views and would otherwise be missing from the export.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ('public', 'mimiciii')
        AND table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY table_schema, table_name
    """)
    return cur.fetchall()

def get_table_row_count(pg_conn, schema, table):
    """Get approximate row count for a table."""
    cur = pg_conn.cursor()
    full_name = f'"{schema}"."{table}"'
    cur.execute(f'SELECT COUNT(*) FROM {full_name}')
    return cur.fetchone()[0]

def export_table(pg_conn, duck_conn, schema, table, chunk_size=500000):
    """Export a single table from Postgres to DuckDB."""
    import pandas as pd
    import uuid
    
    full_name = f'"{schema}"."{table}"'
    qual_name = f'"{schema}"."{table}"' if schema else f'"{table}"'
    
    # Get row count to decide chunking strategy
    try:
        row_count = get_table_row_count(pg_conn, schema, table)
    except Exception as e:
        print(f"    Warning: Could not get row count: {e}", flush=True)
        row_count = 0
    
    print(f"  Exporting {schema}.{table} (~{row_count:,} rows)...", flush=True)
    
    duck_conn.execute(f'DROP TABLE IF EXISTS {qual_name}')
    
    # For large tables (>1M rows), use chunked reading with server-side cursor
    if row_count > 1000000:
        print(f"    Using chunked export (chunk_size={chunk_size:,})...", flush=True)
        
        # Create a unique server-side cursor name
        cursor_name = f'export_cur_{uuid.uuid4().hex[:12]}'
        
        # Use server-side cursor via raw SQL
        cur = pg_conn.cursor()
        try:
            # Declare server-side cursor
            cur.execute(f'DECLARE {cursor_name} CURSOR FOR SELECT * FROM {full_name}')
            
            # Get column names from a sample query
            sample_cur = pg_conn.cursor()
            sample_cur.execute(f'SELECT * FROM {full_name} LIMIT 0')
            columns = [desc[0] for desc in sample_cur.description]
            sample_cur.close()
            
            first_chunk = True
            chunk_num = 0
            
            while True:
                # Fetch chunk from server-side cursor
                cur.execute(f'FETCH {chunk_size} FROM {cursor_name}')
                rows = cur.fetchall()
                
                if not rows:
                    break
                
                chunk_num += 1
                df = pd.DataFrame(rows, columns=columns)
                
                if first_chunk:
                    duck_conn.execute(f'CREATE TABLE {qual_name} AS SELECT * FROM df')
                    first_chunk = False
                    print(f"      Created table, chunk {chunk_num} ({len(df):,} rows)", flush=True)
                else:
                    duck_conn.execute(f'INSERT INTO {qual_name} SELECT * FROM df')
                    if chunk_num % 5 == 0:  # Print every 5 chunks to reduce output
                        print(f"      Chunk {chunk_num} ({len(df):,} rows)", flush=True)
            
            print(f"    Completed {chunk_num} chunks, ~{chunk_num * chunk_size:,} rows", flush=True)
            
            # Close the cursor
            cur.execute(f'CLOSE {cursor_name}')
        except Exception as e:
            # Try to close cursor on error
            try:
                cur.execute(f'CLOSE {cursor_name}')
            except:
                pass
            raise e
        finally:
            cur.close()
    else:
        # Small table, load all at once
        df = pd.read_sql_query(f'SELECT * FROM {full_name}', pg_conn)
        duck_conn.execute(f'CREATE TABLE {qual_name} AS SELECT * FROM df')


def create_nivdurations_if_possible(duck_conn, project_root):
    """Build public.nivdurations in DuckDB from utils/niv-durations.sql."""
    sql_path = os.path.join(project_root, 'utils', 'niv-durations.sql')
    if not os.path.isfile(sql_path):
        print(f"WARNING: niv-durations.sql not found at {sql_path}; skipping nivdurations build.", flush=True)
        return

    with open(sql_path, 'r') as f:
        sql = f.read()

    # Postgres -> DuckDB adaptations
    sql = re.sub(r'SET\s+SEARCH_PATH.*?;', '', sql, flags=re.IGNORECASE)
    sql = re.sub(
        r'DROP\s+MATERIALIZED\s+VIEW\s+IF\s+EXISTS\s+nivdurations\s+CASCADE;',
        'DROP TABLE IF EXISTS public.nivdurations;',
        sql,
        flags=re.IGNORECASE,
    )
    sql = re.sub(
        r'create\s+MATERIALIZED\s+VIEW\s+nivdurations\s+as',
        'CREATE TABLE public.nivdurations AS',
        sql,
        flags=re.IGNORECASE,
    )
    sql = re.sub(
        r'extract\(epoch from max\(charttime\)-min\(charttime\)\)',
        "date_diff('second', min(charttime), max(charttime))",
        sql,
        flags=re.IGNORECASE,
    )
    sql = sql.replace('from chartevents ce', 'from public.chartevents ce')

    print("Building public.nivdurations in DuckDB...", flush=True)
    duck_conn.execute(sql)
    print("Built public.nivdurations.", flush=True)

def main():
    parser = argparse.ArgumentParser(description='Export Postgres MIMIC to DuckDB')
    parser.add_argument('--output', '-o', required=True, help='Output DuckDB file path')
    parser.add_argument('--host', default=os.environ.get('PGHOST', 'localhost'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('PGPORT', 5432)))
    parser.add_argument('--user', default=os.environ.get('PGUSER', 'mimic'))
    parser.add_argument('--password', default=os.environ.get('PGPASSWORD', 'mimic'))
    parser.add_argument('--dbname', default=os.environ.get('PGDATABASE', 'mimic'))
    args = parser.parse_args()

    try:
        import psycopg2
        import duckdb
    except ImportError as e:
        print(f"Error: {e}. Install psycopg2 and duckdb.", file=sys.stderr)
        sys.exit(1)

    pg_kwargs = dict(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        dbname=args.dbname,
    )
    if os.path.isabs(args.host) or (args.host and not args.host.startswith('.')):
        # Unix socket
        pg_kwargs['host'] = args.host

    print(f"Connecting to Postgres...", flush=True)
    pg_conn = psycopg2.connect(**pg_kwargs)
    pg_conn.set_session(autocommit=False, readonly=True)  # Read-only, explicit transactions

    print(f"Creating DuckDB at {args.output}...", flush=True)
    duck_conn = duckdb.connect(args.output)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    # Set up schemas
    duck_conn.execute("CREATE SCHEMA IF NOT EXISTS mimiciii")
    duck_conn.execute("CREATE SCHEMA IF NOT EXISTS public")

    tables = get_tables(pg_conn)
    print(f"Exporting {len(tables)} tables...", flush=True)

    for schema, table in tables:
        try:
            export_table(pg_conn, duck_conn, schema, table)
            pg_conn.commit()  # Commit after successful export
        except Exception as e:
            print(f"  WARNING: Failed {schema}.{table}: {e}", flush=True)
            pg_conn.rollback()  # Rollback to clear transaction state

    try:
        create_nivdurations_if_possible(duck_conn, project_root)
    except Exception as e:
        print(f"WARNING: Failed to build public.nivdurations: {e}", flush=True)

    pg_conn.close()
    duck_conn.close()
    print(f"Done. DuckDB saved to {args.output}", flush=True)

if __name__ == '__main__':
    main()
