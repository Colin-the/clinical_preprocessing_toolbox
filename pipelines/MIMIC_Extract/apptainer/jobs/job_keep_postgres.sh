#!/bin/bash
#SBATCH --job-name=mimic-pg
#SBATCH --mem=120G
#SBATCH --cpus-per-task=8
#SBATCH --time=96:00:00
#SBATCH --output=mimic_keep_postgres_%j.log

set -euo pipefail

# Keep Postgres running (no data load). Use when extraction jobs need more time than setup.
# Requires existing data from setup. Use same POSTGRES_DATA_DIR and PG_SOCKET_DIR.
#
# Submit from project root (use same node as extraction jobs):
#   NODELIST=c64 POSTGRES_DATA_DIR=$SCRATCH/mimic_postgres PG_SOCKET_DIR=$SCRATCH/mimic_pg_socket sbatch apptainer/jobs/job_keep_postgres.sh
#
# To switch from setup to keep-postgres: cancel setup, submit this, wait for it to start, then run extraction jobs.

module load postgresql 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SLURM_SUBMIT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
POSTGRES_DATA="${POSTGRES_DATA_DIR:-$PROJECT_ROOT/data/postgres_data}"
PG_SOCKET="${PG_SOCKET_DIR:-$PROJECT_ROOT/data/pg_socket}"

cd "$PROJECT_ROOT"
mkdir -p "$PG_SOCKET"

if [ ! -f "$POSTGRES_DATA/PG_VERSION" ]; then
  echo "ERROR: No existing Postgres data at $POSTGRES_DATA. Run setup first."
  exit 1
fi

echo "Starting Postgres (existing data at $POSTGRES_DATA)..."
pg_ctl -D "$POSTGRES_DATA" -l "$POSTGRES_DATA/logfile" \
  -o "-c unix_socket_directories=$PG_SOCKET -c autovacuum=off -c max_parallel_workers=0 -c max_parallel_workers_per_gather=0" start

sleep 10
until psql -h "$PG_SOCKET" -U "$USER" -d postgres -c '\q' 2>/dev/null; do
  echo "Waiting for Postgres..."
  sleep 5
done
echo "Postgres ready. Keeping running for 96h."
echo "To run extraction jobs: NODELIST=$(hostname) PGHOST=$PG_SOCKET PG_SOCKET_DIR=$PG_SOCKET bash apptainer/jobs/submit_all.sh"

while kill -0 $(head -1 "$POSTGRES_DATA/postmaster.pid" 2>/dev/null) 2>/dev/null; do sleep 60; done
