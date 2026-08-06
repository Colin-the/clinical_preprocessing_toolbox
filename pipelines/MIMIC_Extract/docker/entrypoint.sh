#!/bin/bash
# Container entrypoint: get a database ready, then run the extractor.
#
# This is the whole pipeline in one script — load MIMIC-III if it isn't loaded,
# build the derived concept tables if they don't exist, then extract. Each stage
# is idempotent (it checks whether its output already exists), which is what lets
# the same image be used both for first-time setup and for the per-scenario runs
# that just want to extract against an already-populated database.
#
# Everything is configured by environment variable rather than argument, because
# it's an ENTRYPOINT and the caller only gets to set env vars. The block of
# `${VAR:-default}` assignments below is therefore the real interface — see
# run_all_scenarios.sh for how the scenarios drive it.
#
# The DuckDB branch (DB_PATH set) skips the load and concept steps entirely: a
# DuckDB file is already-extracted data in a single file, with no server and no
# socket, which sidesteps the whole same-node problem on the HPC path.
set -e

export USER=${USER:-mimic}
export MIMIC_CODE_DIR=${MIMIC_CODE_DIR:-/opt/mimic-code}
export MIMIC_EXTRACT_CODE_DIR=${MIMIC_EXTRACT_CODE_DIR:-/opt/mimic-extract}
export MIMIC_EXTRACT_OUTPUT_DIR=${MIMIC_EXTRACT_OUTPUT_DIR:-/opt/mimic-extract/data/curated}
export MIMIC_DATA_DIR=${MIMIC_DATA_DIR:-/mimic_data}
export PGHOST=${PGHOST:-postgres}
export PGPORT=${PGPORT:-5432}
export PGDATABASE=${PGDATABASE:-mimic}
export PGUSER=${PGUSER:-mimic}
export PGPASSWORD=${PGPASSWORD:-mimic}
export POP_SIZE=${POP_SIZE:-0}
export NUMERICS_BATCH_SIZE=${NUMERICS_BATCH_SIZE:-0}
export EXTRACT_POP=${EXTRACT_POP:-2}
export EXTRACT_NUMERICS=${EXTRACT_NUMERICS:-2}
export EXTRACT_OUTCOMES=${EXTRACT_OUTCOMES:-2}
export MIN_AGE=${MIN_AGE:-15}
export MAX_AGE=${MAX_AGE:-999}
export MIN_DURATION=${MIN_DURATION:-12}
export MAX_DURATION=${MAX_DURATION:-240}
export MIN_PERCENT=${MIN_PERCENT:-0}
export EXTRACT_ALL_NUMERICS=${EXTRACT_ALL_NUMERICS:-0}

export CONNSTR="-h $PGHOST -p $PGPORT -U $PGUSER -d $PGDATABASE"
export PGPASSWORD

# The concept-building SQL emits thousands of NOTICEs about tables it's dropping.
# Without this the useful output is impossible to find in the job log.
export PGOPTIONS="-c client_min_messages=warning"

echo "=== MIMIC-Extract Docker Pipeline ==="
echo "PGHOST=$PGHOST PGDATABASE=$PGDATABASE POP_SIZE=$POP_SIZE NUMERICS_BATCH_SIZE=$NUMERICS_BATCH_SIZE EXTRACT_ALL_NUMERICS=$EXTRACT_ALL_NUMERICS"
echo "EXTRACT_POP=$EXTRACT_POP EXTRACT_NUMERICS=$EXTRACT_NUMERICS EXTRACT_OUTCOMES=$EXTRACT_OUTCOMES"
echo "MIN_AGE=$MIN_AGE MAX_AGE=$MAX_AGE MIN_DURATION=$MIN_DURATION MAX_DURATION=$MAX_DURATION MIN_PERCENT=$MIN_PERCENT"
echo ""

if [ -n "${DB_PATH:-}" ] && [ -f "${DB_PATH}" ]; then
  echo "Using DuckDB mode: $DB_PATH"
  echo "Skipping PostgreSQL wait and data load steps."
  echo ""
else
  # Poll rather than sleep — Postgres and this container start together under
  # compose, and how long the database takes to accept connections varies with
  # how much recovery it has to do. Loops forever on purpose: a wrong PGHOST
  # hangs here visibly instead of failing further down with a confusing error.
  echo "Waiting for PostgreSQL..."
  until PGPASSWORD=$PGPASSWORD psql $CONNSTR -c '\q' 2>/dev/null; do
    echo "  PostgreSQL is unavailable - sleeping"
    sleep 2
  done
  echo "PostgreSQL is ready."
  echo ""
fi

# Check if using DuckDB mode
if [ -n "${DB_PATH:-}" ] && [ -f "${DB_PATH}" ]; then
  echo "Skipping data load and concept building (DuckDB mode)"
else
  # create schema and load MIMIC-III data 
  if [ -d "$MIMIC_DATA_DIR" ] && [ "$(ls -A $MIMIC_DATA_DIR/*.csv.gz 2>/dev/null || ls -A $MIMIC_DATA_DIR/*.csv 2>/dev/null)" ]; then
    echo "loading MIMIC-III data into PostgreSQL"
  
  # Existence of the mimiciii schema is the "already loaded" check. Coarse — a
  # load that died halfway leaves the schema behind and gets skipped — so if the
  # data looks incomplete, drop the schema and let it reload.
  if ! PGPASSWORD=$PGPASSWORD psql $CONNSTR -tAc "SELECT 1 FROM information_schema.schemata WHERE schema_name='mimiciii'" | grep -q 1; then
    echo "Creating schema and tables..."

    # mimic-code reorganised its directory layout at some point; try the new
    # path, fall back to the old.
    POSTGRES_DIR=$MIMIC_CODE_DIR/buildmimic/postgres
    [ ! -d "$POSTGRES_DIR" ] && POSTGRES_DIR=$MIMIC_CODE_DIR/mimic-iii/buildmimic/postgres
    # Same idea for the schema SQL: the pg10 variant where it exists, otherwise
    # the generic one.
    PGPASSWORD=$PGPASSWORD psql $CONNSTR -f $POSTGRES_DIR/postgres_create_tables_pg10.sql 2>/dev/null || \
    PGPASSWORD=$PGPASSWORD psql $CONNSTR -f $POSTGRES_DIR/postgres_create_tables.sql
    

    cd $MIMIC_DATA_DIR
    if ls *.csv.gz 1> /dev/null 2>&1; then
      echo "Loading from .csv.gz files..."
      PGPASSWORD=$PGPASSWORD psql $CONNSTR -v mimic_data_dir=$MIMIC_DATA_DIR -f $POSTGRES_DIR/postgres_load_data_gz.sql
    else
      echo "Loading from .csv files..."
      PGPASSWORD=$PGPASSWORD psql $CONNSTR -v mimic_data_dir=$MIMIC_DATA_DIR -f $POSTGRES_DIR/postgres_load_data.sql
    fi
    cd -
    

    # After the load, not before — indexing 330M rows of chartevents as they
    # arrive turns a long COPY into an unbearable one.
    echo "Adding constraints and indexes..."
    PGPASSWORD=$PGPASSWORD psql $CONNSTR -f $POSTGRES_DIR/postgres_add_constraints.sql
    PGPASSWORD=$PGPASSWORD psql $CONNSTR -f $POSTGRES_DIR/postgres_add_indexes.sql
    echo "MIMIC-III data loaded."
  else
    echo "MIMIC-III schema already exists - skipping data load."
  fi
  echo ""
else
  echo "=== Step 1: Skipping data load (no MIMIC-III files in $MIMIC_DATA_DIR) ==="
  echo "Mount MIMIC-III CSV files to /mimic_data to load from scratch."
  echo ""
fi

# build mimic-code concepts 
if [ -n "${DB_PATH:-}" ] && [ -f "${DB_PATH}" ]; then
  echo "Skipping concept building (DuckDB mode - concepts already in database)"
else
  echo "building mimic-code concepts" 
  PGPASSWORD=$PGPASSWORD psql $CONNSTR -c "CREATE SCHEMA IF NOT EXISTS mimiciii" -q
  PGPASSWORD=$PGPASSWORD psql $CONNSTR -v ON_ERROR_STOP=1 -f $MIMIC_CODE_DIR/concepts/postgres-functions.sql
  cd $MIMIC_CODE_DIR/concepts && PGPASSWORD=$PGPASSWORD bash postgres_make_concepts.sh
  echo "mimic-code concepts built"
  
  # A few concepts MIMIC-Extract needs that mimic-code's own script doesn't build.
  #
  # The two regexes translate BigQuery SQL to Postgres on the fly, because
  # upstream mimic-code writes these for BigQuery: DATETIME_DIFF's third argument
  # needs quoting, and `physionet-data.mimiciii_clinical.foo` backtick-qualified
  # names have to collapse to a bare table name. Piping through sed rather than
  # maintaining forked copies of the SQL means upstream changes come through for
  # free — at the cost of breaking silently if upstream changes its formatting.
  echo "building MIMIC-Extract extended concepts"
  REGEX_DATETIME_DIFF="s/DATETIME_DIFF\((.+?),\s?(.+?),\s?(DAY|MINUTE|SECOND|HOUR|YEAR)\)/DATETIME_DIFF(\1, \2, '\3')/g"
  REGEX_SCHEMA='s/`physionet-data.(mimiciii_clinical|mimiciii_derived|mimiciii_notes).(.+?)`/\2/g'
  echo "  Creating colloid_bolus..."
  { echo "SET search_path TO public,mimiciii; DROP TABLE IF EXISTS colloid_bolus; CREATE TABLE colloid_bolus AS "; cat $MIMIC_CODE_DIR/concepts/fluid_balance/colloid_bolus.sql; } | sed -r -e "${REGEX_DATETIME_DIFF}" | sed -r -e "${REGEX_SCHEMA}" | PGPASSWORD=$PGPASSWORD psql -h $PGHOST -p $PGPORT -U $PGUSER -d $PGDATABASE
  echo "  Creating crystalloid_bolus..."
  { echo "SET search_path TO public,mimiciii; DROP TABLE IF EXISTS crystalloid_bolus; CREATE TABLE crystalloid_bolus AS "; cat $MIMIC_CODE_DIR/concepts/fluid_balance/crystalloid_bolus.sql; } | sed -r -e "${REGEX_DATETIME_DIFF}" | sed -r -e "${REGEX_SCHEMA}" | PGPASSWORD=$PGPASSWORD psql -h $PGHOST -p $PGPORT -U $PGUSER -d $PGDATABASE
  echo "  Creating nivdurations..."
  PGPASSWORD=$PGPASSWORD psql -h $PGHOST -p $PGPORT -U $PGUSER -d $PGDATABASE -f $MIMIC_EXTRACT_CODE_DIR/utils/niv-durations.sql
  echo ""
fi
fi

# run extraction 
echo "running MIMIC-Extract"
mkdir -p $MIMIC_EXTRACT_OUTPUT_DIR
cd $MIMIC_EXTRACT_CODE_DIR

# extract_codes and extract_notes are hardcoded off — this fork only cares about
# the seven bedside vitals, and notes extraction in particular is expensive and
# unused. The 2s for pop/outcomes/numerics mean "extract, using the cached
# intermediate if one exists".
CMD_ARGS="--out_path $MIMIC_EXTRACT_OUTPUT_DIR/ \
  --resource_path $MIMIC_EXTRACT_CODE_DIR/resources/ \
  --extract_pop $EXTRACT_POP \
  --extract_outcomes $EXTRACT_OUTCOMES \
  --extract_codes 0 \
  --extract_numerics $EXTRACT_NUMERICS \
  --extract_notes 0 \
  --exit_after_loading 0 \
  --plot_hist 0 \
  --pop_size $POP_SIZE \
  --numerics_batch_size $NUMERICS_BATCH_SIZE \
  --min_age $MIN_AGE \
  --max_age $MAX_AGE \
  --min_duration $MIN_DURATION \
  --max_duration $MAX_DURATION \
  --min_percent $MIN_PERCENT"

if [ "$EXTRACT_ALL_NUMERICS" = "1" ]; then
  CMD_ARGS="$CMD_ARGS --extract_all_numerics"
fi

# Note only --psql_host is passed, no port — the extractor takes PGPORT from the
# environment. And an absolute PGHOST is read by libpq as a socket directory,
# which is what makes the Apptainer path work through this same script.
if [ -n "${DB_PATH:-}" ] && [ -f "${DB_PATH}" ]; then
  echo "Using DuckDB: $DB_PATH"
  CMD_ARGS="$CMD_ARGS --db_path $DB_PATH"
else
  echo "Using PostgreSQL: $PGHOST:$PGPORT/$PGDATABASE"
  CMD_ARGS="$CMD_ARGS --psql_password $PGPASSWORD --psql_host $PGHOST"
fi

# -u unbuffers stdout so progress actually shows up in a SLURM log rather than
# arriving in one lump hours later. Full interpreter path because the conda env
# isn't activated in a non-interactive shell.
/opt/conda/envs/mimic_data_extraction/bin/python -u mimic_direct_extract.py $CMD_ARGS

echo ""
echo "pipeline complete. Output in $MIMIC_EXTRACT_OUTPUT_DIR"
