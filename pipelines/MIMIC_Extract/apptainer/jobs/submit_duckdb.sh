#!/bin/bash
# Submit all scenario jobs using DuckDB (no Postgres, no NODELIST).
# Each job runs on any available node.
#
# Prerequisites:
#   1. Setup completed (Postgres loaded with MIMIC-III)
#   2. Export completed: job_export_duckdb.sh produced the .duckdb file
#
# Usage:
#   DB_PATH=$SCRATCH/mimic_data.duckdb bash apptainer/jobs/submit_duckdb.sh
#
# Or from project root:
#   cd /path/to/MIMIC_Extract
#   DB_PATH=$SCRATCH/mimic_data.duckdb bash apptainer/jobs/submit_duckdb.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SLURM_SUBMIT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
cd "$PROJECT_ROOT"

DB_PATH="${DB_PATH:-}"
if [ -z "$DB_PATH" ] || [ ! -f "$DB_PATH" ]; then
  echo "ERROR: DB_PATH must be set and point to an existing .duckdb file"
  echo "  Example: DB_PATH=\$SCRATCH/mimic_data.duckdb bash apptainer/jobs/submit_duckdb.sh"
  exit 1
fi

SBATCH_EXPORT="ALL,DB_PATH=$DB_PATH,SLURM_SUBMIT_DIR=$PROJECT_ROOT"
SBATCH_ARGS="--export=$SBATCH_EXPORT"

echo "Submitting DuckDB scenario jobs (any node)..."
echo "  DB_PATH=$DB_PATH"
for f in "$SCRIPT_DIR"/job_*.sh; do
  fname=$(basename "$f")
  [ "$fname" = "job_setup_postgres.sh" ] && continue
  [ "$fname" = "job_keep_postgres.sh" ] && continue
  [ "$fname" = "job_export_duckdb.sh" ] && continue
  [ "$fname" = "job_curated_mimic_iii_analysis.sh" ] && continue
  [ "$fname" = "job_pop5000.sh" ] && continue
  EXTRA_ARGS="--time=96:00:00 --cpus-per-task=8 --mem=100G"
  if [ "$fname" = "job_baseline_nofilters.sh" ]; then
    EXTRA_ARGS="--time=96:00:00 --cpus-per-task=8 --mem=128G"
  elif [ "$fname" = "job_baseline_nofilters_fast.sh" ]; then
    EXTRA_ARGS="--time=96:00:00 --cpus-per-task=16 --mem=192G"
  elif [ "$fname" = "job_min48hr.sh" ]; then
    EXTRA_ARGS="--time=96:00:00 --cpus-per-task=8 --mem=128G"
  fi
  echo "  sbatch $SBATCH_ARGS $EXTRA_ARGS $f"
  sbatch $SBATCH_ARGS $EXTRA_ARGS "$f"
done
echo "Done. Check squeue for status."
