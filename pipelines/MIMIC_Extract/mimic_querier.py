import copy
import warnings

import pandas as pd
import psycopg2

# Import DuckDB for DuckDB mode
try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False

# TODO(mmd): Where should this go?
# TODO(mmd): Rename
# TODO(mmd): eliminate try/except. Just use conditionals.
def get_values_by_name_from_df_column_or_index(data_df, colname):
    """ Easily get values for named field, whether a column or an index

    Returns
    -------
    values : 1D array
    """
    try:
        values = data_df[colname]
    except KeyError as e:
        if colname in data_df.index.names:
            values = data_df.index.get_level_values(colname)
        else:
            raise e
    return values

# TODO(mmd): Maybe make context manager?
class MIMIC_Querier():
    def __init__(
        self,
        exclusion_criteria_template_vars={},
        query_args={}, # passed wholesale to psycopg2.connect or duckdb path
        schema_name='public,mimiciii',
        db_path=None  # If set, use DuckDB instead of Postgres
    ):
        """ A class to facilitate repeated Queries to a MIMIC psql database or DuckDB """
        self.exclusion_criteria_template_vars = {}
        self.query_args  = query_args
        self.schema_name = schema_name
        self.db_path     = db_path
        self.use_duckdb  = db_path is not None
        self.connected   = False
        self.connection, self.cursor = None, None

    # TODO(mmd): this isn't really doing exclusion criteria. Should maybe also absorb 'WHERE' clause...
    def add_exclusion_criteria_from_df(self, df, columns=[]):
        self.exclusion_criteria_template_vars.update({
            c: "','".join(
                set([str(v) for v in get_values_by_name_from_df_column_or_index(df, c)])
            ) for c in columns
        })

    def clear_exclusion_criteria(self): self.exclusion_criteria_template_vars = {}

    def close(self):
        if not self.connected: return
        self.connection.close()
        if self.cursor is not None:
            self.cursor.close()
        self.connected = False

    def connect(self):
        self.close()
        if self.use_duckdb:
            if not HAS_DUCKDB:
                raise ImportError("DuckDB is not installed. Install with: pip install duckdb")
            self.connection = duckdb.connect(self.db_path, read_only=True)
            self.cursor = None  # DuckDB doesn't need separate cursor
            # Set default schema for DuckDB - use first schema from list
            try:
                default_schema = self.schema_name.split(',')[0].strip()
                self.connection.execute(f"SET search_path = '{default_schema}'")
            except Exception as e:
                # If that doesn't work, try without quotes
                try:
                    self.connection.execute(f"SET schema '{default_schema}'")
                except:
                    pass  # Continue without setting schema
        else:
            self.connection = psycopg2.connect(**self.query_args)
            self.cursor     = self.connection.cursor()
            self.cursor.execute('SET search_path TO %s' % self.schema_name)
        self.connected = True

    def query(self, query_string=None, query_file=None, extra_template_vars={}):
        assert query_string is not None or query_file is not None, "Must pass a query!"
        assert query_string is None or query_file is None, "Must only pass one query!"

        self.connect()

        if query_string is None:
            with open(query_file, mode='r') as f: query_string = f.read()

        template_vars = copy.copy(self.exclusion_criteria_template_vars)
        template_vars.update(extra_template_vars)

        query_string = query_string.format(**template_vars)
        
        # For DuckDB, add schema prefix to unqualified table names
        if self.use_duckdb:
            import re
            # Get default schema (first one in list)
            default_schema = self.schema_name.split(',')[0].strip()
            
            # Simpler approach: match any identifier after FROM/JOIN keywords
            # This works for: FROM table, FROM table alias, FROM table1, table2, etc.
            def qualify_table_name(match):
                prefix = match.group(1)  # FROM or JOIN
                whitespace = match.group(2)
                table_name = match.group(3)
                
                # Skip if already qualified (has dot), is a subquery (starts with paren),
                # is a keyword (SELECT, WITH), or is a number
                if ('.' in table_name or table_name.startswith('(') or 
                    table_name.upper() in ('SELECT', 'WITH', 'VALUES', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'CAST', 'COALESCE', 'AND', 'OR', 'NOT', 'IS', 'NULL') or 
                    table_name.isdigit() or table_name.replace('_', '').isdigit()):
                    return match.group(0)
                
                # Add schema prefix
                return f"{prefix}{whitespace}{default_schema}.{table_name}"
            
            # First, match FROM/JOIN followed by an identifier
            query_string = re.sub(
                r'\b(FROM|JOIN)(\s+)([a-zA-Z_][a-zA-Z0-9_]*)\b(?!\s*\.)',
                qualify_table_name,
                query_string,
                flags=re.IGNORECASE
            )
        
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*SQLAlchemy connectable.*")
            out = pd.read_sql_query(query_string, self.connection)

        self.close()
        return out
