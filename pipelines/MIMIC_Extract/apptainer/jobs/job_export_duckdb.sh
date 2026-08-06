#!/bin/bash
#SBATCH --job-name=mimic-export
#SBATCH --mem=64G
#SBATCH --cpus-per-task=4
#SBATCH --time=4:00:00
#SBATCH --output=mimic_export_%j.log

set -euo pipefail

# Export Postgres MIMIC database to DuckDB for standalone extraction.
# Run AFTER setup completes. Must run on SAME NODE as Postgres.
#
# Usage (recommended - uses Postgres job's node automatically):
#   PG_JOB_ID=10398505 PGHOST=/scratch/$USER/mimic_pg_socket DB_PATH=$SCRATCH/mimic_data.duckdb bash apptainer/jobs/submit_export_duckdb.sh
#
# Then run extractions with DB_PATH (no NODELIST needed):
#   DB_PATH=$SCRATCH/mimic_data.duckdb bash apptainer/jobs/submit_duckdb.sh

module load apptainer

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SLURM_SUBMIT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
SIF_PATH="${MIMEXTRACT_SIF:-$PROJECT_ROOT/apptainer/mimextract.sif}"
PG_SOCKET="${PG_SOCKET_DIR:-$PGHOST}"
DB_OUTPUT="${DB_PATH:-$PROJECT_ROOT/data/mimic_data.duckdb}"

# Ensure output dir exists
DB_DIR=$(dirname "$DB_OUTPUT")
mkdir -p "$DB_DIR"

export PGHOST="${PGHOST:-$PG_SOCKET}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-mimic}"
export PGUSER="${PGUSER:-mimic}"
export PGPASSWORD="${PGPASSWORD:-mimic}"

# Path inside container (we bind mount the DB dir)
DB_BASENAME=$(basename "$DB_OUTPUT")
CONTAINER_DB_PATH="/data/duckdb/$DB_BASENAME"

echo "Exporting Postgres to DuckDB..."
echo "  PGHOST=$PGHOST"
echo "  Output: $DB_OUTPUT"

BIND_ARGS="--bind $DB_DIR:/data/duckdb"
[[ "$PGHOST" == /* ]] && BIND_ARGS="$BIND_ARGS --bind $PGHOST:/tmp/pg_socket" && export APPTAINERENV_PGHOST=/tmp/pg_socket

apptainer exec $BIND_ARGS "$SIF_PATH" \
  /opt/conda/envs/mimic_data_extraction/bin/python -u /opt/mimic-extract/utils/export_postgres_to_duckdb.py \
  --output "$CONTAINER_DB_PATH" \
  --host "${APPTAINERENV_PGHOST:-$PGHOST}"

echo "Done. DuckDB saved to $DB_OUTPUT"
echo "Run extractions with: DB_PATH=$DB_OUTPUT bash apptainer/jobs/submit_duckdb.sh"
