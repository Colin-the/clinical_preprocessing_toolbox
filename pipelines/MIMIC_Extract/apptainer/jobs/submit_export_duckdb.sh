#!/bin/bash
# Wrapper to submit export job on the same node as Postgres.
# Usage:
#   PG_JOB_ID=10398505 PGHOST=/scratch/$USER/mimic_pg_socket DB_PATH=$SCRATCH/mimic_data.duckdb bash apptainer/jobs/submit_export_duckdb.sh

if [ -z "${PG_JOB_ID:-}" ]; then
  echo "ERROR: PG_JOB_ID required (Postgres job ID from squeue)"
  echo "Usage: PG_JOB_ID=<jobid> PGHOST=... DB_PATH=... bash apptainer/jobs/submit_export_duckdb.sh"
  exit 1
fi

NODE=$(squeue -j "$PG_JOB_ID" -o "%N" -h 2>/dev/null | tr -d ' ')

if [ -z "$NODE" ]; then
  echo "ERROR: Job $PG_JOB_ID not found or not running. Check squeue."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SLURM_SUBMIT_DIR:-$SCRIPT_DIR/../..}"

echo "Submitting export job to node $NODE (letting Slurm choose partition for 128GB)"

# Forward PGHOST, DB_PATH, etc. to the job (sbatch does not forward env by default)
# Don't specify partition - let Slurm pick the right one for memory requirements
sbatch --nodelist="$NODE" --export=ALL "$SCRIPT_DIR/job_export_duckdb.sh"
