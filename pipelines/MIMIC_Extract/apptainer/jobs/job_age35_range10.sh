#!/bin/bash
#SBATCH --job-name=mimic-age35-r10
#SBATCH --mem=100G
#SBATCH --cpus-per-task=8
#SBATCH --time=96:00:00
#SBATCH --output=mimic_age35_range10_%j.log

set -euo pipefail

# Scenario: age35_range10 (ages 30-40)
# Output: data/curated/age35_range10/

module load apptainer

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SLURM_SUBMIT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
SIF_PATH="${MIMEXTRACT_SIF:-$PROJECT_ROOT/apptainer/mimextract.sif}"
MIMIC_DATA="${MIMIC_DATA_PATH:-$PROJECT_ROOT/data/mimiciii/1.4}"
CURATED_OUT="${CURATED_OUTPUT:-$PROJECT_ROOT/data/curated}"
PG_SOCKET="${PG_SOCKET_DIR:-$PROJECT_ROOT/data/pg_socket}"

export PGHOST="${PGHOST:-$PG_SOCKET}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-mimic}"
export PGUSER="${PGUSER:-mimic}"
export PGPASSWORD="${PGPASSWORD:-mimic}"
export MIMIC_EXTRACT_OUTPUT_DIR="/opt/mimic-extract/data/curated/age35_range10"
export POP_SIZE=0
export NUMERICS_BATCH_SIZE=2500
export MIN_AGE=30
export MAX_AGE=40
export MIN_DURATION=12
export MAX_DURATION=240
export MIN_PERCENT=0

cd "$PROJECT_ROOT"
mkdir -p "$CURATED_OUT"

# DuckDB is an alternative to Postgres for the read side -- no server, no
# socket, so no same-node constraint. Set DB_PATH to use it.
if [ -n "${DB_PATH:-}" ] && [ -f "$DB_PATH" ]; then
  echo "Using DuckDB mode: $DB_PATH"
  export APPTAINERENV_DB_PATH="$DB_PATH"
  BIND_ARGS="--bind $PROJECT_ROOT:/opt/mimic-extract --bind $MIMIC_DATA:/mimic_data:ro --bind $DB_PATH:$DB_PATH:ro"
else
  echo "Using Postgres mode: $PGHOST"
  export APPTAINERENV_PGHOST="$PGHOST"
  export APPTAINERENV_PGPORT="$PGPORT"
  export APPTAINERENV_PGDATABASE="$PGDATABASE"
  export APPTAINERENV_PGUSER="$PGUSER"
  export APPTAINERENV_PGPASSWORD="$PGPASSWORD"
  BIND_ARGS="--bind $PROJECT_ROOT:/opt/mimic-extract --bind $MIMIC_DATA:/mimic_data:ro"
  [[ "$PGHOST" == /* ]] && BIND_ARGS="$BIND_ARGS --bind $PGHOST:/tmp/pg_socket" && export APPTAINERENV_PGHOST=/tmp/pg_socket
fi

export APPTAINERENV_MIMIC_EXTRACT_OUTPUT_DIR="$MIMIC_EXTRACT_OUTPUT_DIR"
export APPTAINERENV_POP_SIZE="$POP_SIZE"
export APPTAINERENV_NUMERICS_BATCH_SIZE="$NUMERICS_BATCH_SIZE"
export APPTAINERENV_MIN_AGE="$MIN_AGE"
export APPTAINERENV_MAX_AGE="$MAX_AGE"
export APPTAINERENV_MIN_DURATION="$MIN_DURATION"
export APPTAINERENV_MAX_DURATION="$MAX_DURATION"
export APPTAINERENV_MIN_PERCENT="$MIN_PERCENT"

apptainer run $BIND_ARGS "$SIF_PATH"

echo "Done: age35_range10"
