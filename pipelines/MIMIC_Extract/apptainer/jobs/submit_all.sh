#!/bin/bash
# Fan the scenario jobs out to SLURM, all at once.
#
# The only real work here is making sure each job can find the Postgres that the
# setup job left running. Since they talk over a Unix socket — a file on one
# node — every job has to be pinned to that same node, and both the socket path
# and the project root have to be forwarded through sbatch's own environment.
# Get all three wrong and the jobs submit fine and then fail on connect.
#
# Find the node with `squeue -u $USER` or from the setup job's log, then:
#   cd /path/to/MIMIC_Extract
#   NODELIST=c263.nibi.sharcnet PGHOST=/scratch/$USER/mimic_pg_socket \
#       bash apptainer/jobs/submit_all.sh
#
# Resources come from each job script's own #SBATCH directives; this script only
# adds the connection plumbing (--export, --nodelist).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SLURM_SUBMIT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
cd "$PROJECT_ROOT"

PG_SOCKET_DEFAULT="${PG_SOCKET_DIR:-$PROJECT_ROOT/data/pg_socket}"
export PGHOST="${PGHOST:-$PG_SOCKET_DEFAULT}"
# The two default to each other so you only have to set one — but if setup used a
# scratch path, whichever you set must match it exactly.
export PG_SOCKET_DIR="${PG_SOCKET_DIR:-$PGHOST}"

# sbatch runs jobs from wherever it was invoked, and the job scripts resolve the
# project root from SLURM_SUBMIT_DIR — so this cd is what makes their relative
# paths land on the SIF and the data.
cd "$PROJECT_ROOT"

# `ALL` inherits the current environment, then the explicit assignments override.
# SLURM_SUBMIT_DIR is passed by hand because SLURM sets it from the submitting
# directory, which isn't reliably the project root when this is sourced.
SBATCH_EXPORT="ALL,PGHOST=$PGHOST,PG_SOCKET_DIR=$PG_SOCKET_DIR,SLURM_SUBMIT_DIR=$PROJECT_ROOT"

SBATCH_ARGS="--export=$SBATCH_EXPORT"
# Without NODELIST the scheduler spreads jobs across the cluster and none of them
# can reach the socket. Optional only because a shared-filesystem socket setup
# would not need it.
[ -n "${NODELIST:-}" ] && SBATCH_ARGS="$SBATCH_ARGS --nodelist=$NODELIST"

echo "Submitting 12 scenario jobs (pop5000 already run during setup)..."
echo "  PGHOST=$PGHOST"
[ -n "${NODELIST:-}" ] && echo "  NODELIST=$NODELIST (same node as setup)"
# Glob-and-exclude rather than an explicit list, so a new job_*.sh scenario gets
# picked up automatically. The three skips: the setup and keep-alive jobs manage
# Postgres rather than extract anything, and pop5000 already ran during setup as
# a side effect of loading the data.
for f in "$SCRIPT_DIR"/job_*.sh; do
  fname=$(basename "$f")
  [ "$fname" = "job_setup_postgres.sh" ] && continue
  [ "$fname" = "job_keep_postgres.sh" ] && continue
  [ "$fname" = "job_pop5000.sh" ] && continue
  echo "  sbatch $SBATCH_ARGS $f"
  sbatch $SBATCH_ARGS "$f"
done
echo "Done. Check squeue for status."
