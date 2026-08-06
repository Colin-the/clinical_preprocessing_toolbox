#!/bin/bash
#SBATCH --job-name=mimic-setup
#SBATCH --mem=120G
#SBATCH --cpus-per-task=8
#SBATCH --time=24:00:00
#SBATCH --output=mimic_setup_%j.log

set -euo pipefail

# One-time setup, and the job everything else depends on: brings up Postgres,
# loads MIMIC-III, builds the derived concept tables, then deliberately *stays
# alive* so the per-scenario extraction jobs have a database to talk to. It does
# not exit when the work is done — it blocks until the walltime runs out, and
# that's intentional.
#
# Note it loads the data by running the pop5000 extraction rather than by any
# dedicated import step. That's not a shortcut for its own sake: the loading and
# concept-building live inside the extractor, so running the cheapest scenario is
# the shortest path to a populated database. You get pop5000's output for free.
#
#   cd /path/to/MIMIC_Extract
#   module load postgresql apptainer
#   sbatch apptainer/jobs/job_setup_postgres.sh
#
# "Disk quota exceeded" — the database is 50-80GB, more than a home directory:
#   POSTGRES_DATA_DIR=$SCRATCH/mimic_postgres sbatch apptainer/jobs/job_setup_postgres.sh
#
# "Transport endpoint is not connected" — CVMFS dropped the container's FUSE
# mount. Fall back to Postgres from the module, no container involved. Wipe the
# data directory first; the two paths don't share a layout:
#   rm -rf $SCRATCH/mimic_postgres $SCRATCH/mimic_pg_socket
#   USE_NATIVE_POSTGRES=1 POSTGRES_DATA_DIR=$SCRATCH/mimic_postgres PG_SOCKET_DIR=$SCRATCH/mimic_pg_socket sbatch apptainer/jobs/job_setup_postgres.sh

module load apptainer
module load postgresql 2>/dev/null || true

# Prefer SLURM_SUBMIT_DIR over the script's own location, because sbatch may copy
# the script somewhere else entirely before running it — deriving the project
# root from BASH_SOURCE then points at a temp directory. Falls back to the
# script path for interactive runs.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SLURM_SUBMIT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
POSTGRES_DATA="${POSTGRES_DATA_DIR:-$PROJECT_ROOT/data/postgres_data}"
PG_SOCKET="${PG_SOCKET_DIR:-$PROJECT_ROOT/data/pg_socket}"
SIF_PATH="${MIMEXTRACT_SIF:-$PROJECT_ROOT/apptainer/mimextract.sif}"
POSTGRES_SIF="${POSTGRES_SIF:-$PROJECT_ROOT/apptainer/postgres.sif}"
MIMIC_DATA="${MIMIC_DATA_PATH:-$PROJECT_ROOT/data/mimiciii/1.4}"
CURATED_OUT="${CURATED_OUTPUT:-$PROJECT_ROOT/data/curated}"

cd "$PROJECT_ROOT"
mkdir -p "$POSTGRES_DATA" "$PG_SOCKET" "$CURATED_OUT"

# Socket, not TCP — Compute Canada won't grant --network host to an unprivileged
# container. Everything downstream inherits this choice.
export PGHOST="$PG_SOCKET"
export PGPORT=5432
export PGDATABASE=mimic
export PGUSER=mimic
export PGPASSWORD=mimic

USE_NATIVE="${USE_NATIVE_POSTGRES:-0}"
if [ "$USE_NATIVE" = "1" ] && command -v pg_ctl >/dev/null 2>&1; then
  echo "Using native Postgres (no container)..."
  if [ ! -f "$POSTGRES_DATA/PG_VERSION" ]; then
    # PG_VERSION's presence is the standard "is this initialised" check. Note a
    # directory left over from the container path will have one, hence the
    # instruction to wipe it when switching modes — the versions rarely match.
    echo "Initializing Postgres data directory..."
    initdb -D "$POSTGRES_DATA" --auth=trust
    # Tuned for a one-shot bulk load, not for serving. autovacuum off because
    # nothing is ever updated or deleted here, and letting it run during a
    # multi-hour COPY of chartevents just competes for I/O. Parallel workers off
    # because they're what tends to blow the memory limit on the big pivots —
    # the queries are slower serially but they finish.
    echo "unix_socket_directories = '$PG_SOCKET'" >> "$POSTGRES_DATA/postgresql.conf"
    echo "autovacuum = off" >> "$POSTGRES_DATA/postgresql.conf"
    echo "max_parallel_workers = 0" >> "$POSTGRES_DATA/postgresql.conf"
    echo "max_parallel_workers_per_gather = 0" >> "$POSTGRES_DATA/postgresql.conf"
  fi
  pg_ctl -D "$POSTGRES_DATA" -l "$POSTGRES_DATA/logfile" -o "-c unix_socket_directories=$PG_SOCKET -c autovacuum=off -c max_parallel_workers=0 -c max_parallel_workers_per_gather=0" start
  PGPID=$(head -1 "$POSTGRES_DATA/postmaster.pid" 2>/dev/null) || PGPID=0
  sleep 10
  until psql -h "$PG_SOCKET" -U "$USER" -d postgres -c '\q' 2>/dev/null; do
    echo "Waiting for Postgres..."
    sleep 5
  done
  psql -h "$PG_SOCKET" -U "$USER" -d postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='mimic'" 2>/dev/null | grep -q 1 || \
    psql -h "$PG_SOCKET" -U "$USER" -d postgres -c "CREATE USER mimic WITH PASSWORD 'mimic' SUPERUSER"
  psql -h "$PG_SOCKET" -U "$USER" -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='mimic'" 2>/dev/null | grep -q 1 || \
    psql -h "$PG_SOCKET" -U "$USER" -d postgres -c "CREATE DATABASE mimic OWNER mimic"
  echo "Postgres ready (native)."
  # Both branches converge on the same in-container socket path, so everything
  # downstream is identical regardless of which Postgres is running.
  APPTAINER_PGHOST="/tmp/pg_socket"
else
  if [ ! -f "$POSTGRES_SIF" ]; then
    echo "Building Postgres SIF (one-time, ~2 min)..."
    apptainer build "$POSTGRES_SIF" docker://postgres:15
  fi
  # Copy the SIFs onto node-local storage before running them. Executing a SIF
  # straight off the shared filesystem is what makes the FUSE mount fragile over
  # a long job — SLURM_TMPDIR is local disk and survives. Falls back to scratch,
  # which is at least not the home filesystem.
  LOCAL_SIF_DIR=""
  if [ -n "${SLURM_TMPDIR:-}" ] && [ -d "$SLURM_TMPDIR" ]; then
    LOCAL_SIF_DIR="$SLURM_TMPDIR"
  elif [ -n "${SCRATCH:-}" ] && [ -n "${SLURM_JOB_ID:-}" ]; then
    LOCAL_SIF_DIR="$SCRATCH/sif_$SLURM_JOB_ID"
    mkdir -p "$LOCAL_SIF_DIR"
  fi
  if [ -n "$LOCAL_SIF_DIR" ]; then
    echo "Copying SIFs to $LOCAL_SIF_DIR..."
    [ -f "$POSTGRES_SIF" ] && cp -f "$POSTGRES_SIF" "$LOCAL_SIF_DIR/postgres.sif" && POSTGRES_SIF="$LOCAL_SIF_DIR/postgres.sif"
    [ -f "$SIF_PATH" ] && cp -f "$SIF_PATH" "$LOCAL_SIF_DIR/mimextract.sif" && SIF_PATH="$LOCAL_SIF_DIR/mimextract.sif"
  fi
  export APPTAINERENV_POSTGRES_USER=mimic
  export APPTAINERENV_POSTGRES_PASSWORD=mimic
  export APPTAINERENV_POSTGRES_DB=mimic
  echo "Starting Postgres (Unix socket at $PG_SOCKET)..."
  apptainer run \
    --bind "$POSTGRES_DATA:/var/lib/postgresql/data" \
    --bind "$PG_SOCKET:/tmp/pg_socket" \
    "$POSTGRES_SIF" postgres \
    -c unix_socket_directories=/tmp/pg_socket \
    -c autovacuum=off \
    -c max_parallel_workers=0 \
    -c max_parallel_workers_per_gather=0 &
  PGPID=$!
  sleep 30
  until apptainer exec --bind "$PG_SOCKET:/tmp/pg_socket" "$POSTGRES_SIF" \
    psql "host=/tmp/pg_socket user=mimic dbname=postgres" -c '\q' 2>/dev/null; do
    echo "Waiting for Postgres..."
    sleep 5
  done
  apptainer exec --bind "$PG_SOCKET:/tmp/pg_socket" "$POSTGRES_SIF" \
    psql "host=/tmp/pg_socket user=mimic dbname=postgres" -tc "SELECT 1 FROM pg_database WHERE datname='mimic'" 2>/dev/null | grep -q 1 || \
  apptainer exec --bind "$PG_SOCKET:/tmp/pg_socket" "$POSTGRES_SIF" \
    psql "host=/tmp/pg_socket user=mimic dbname=postgres" -c "CREATE DATABASE mimic"
  # Deliberate restart, not paranoia. The container's overlay mount goes stale
  # after the CREATE DATABASE round-trip, and the failure shows up hours later
  # mid-load as "Transport endpoint is not connected" — by which point you've
  # burned most of the walltime. Bouncing it here costs 20 seconds.
  echo "Restarting Postgres for fresh mount before data load..."
  kill $PGPID 2>/dev/null || true
  wait $PGPID 2>/dev/null || true
  sleep 3
  apptainer run \
    --bind "$POSTGRES_DATA:/var/lib/postgresql/data" \
    --bind "$PG_SOCKET:/tmp/pg_socket" \
    "$POSTGRES_SIF" postgres \
    -c unix_socket_directories=/tmp/pg_socket \
    -c autovacuum=off \
    -c max_parallel_workers=0 \
    -c max_parallel_workers_per_gather=0 &
  PGPID=$!
  sleep 15
  until apptainer exec --bind "$PG_SOCKET:/tmp/pg_socket" "$POSTGRES_SIF" \
    psql "host=/tmp/pg_socket user=mimic dbname=postgres" -c '\q' 2>/dev/null; do
    echo "Waiting for Postgres..."
    sleep 5
  done
  echo "Postgres ready (container)."
  APPTAINER_PGHOST="/tmp/pg_socket"
fi

# pop5000 because it's the cheapest scenario — the data load and concept build
# happen regardless of cohort size, so this is the fastest way to get the
# database populated. Its output in data/curated/pop5000/ is a real result, not
# a throwaway.
echo "Loading MIMIC data and building concepts (via pop5000 extraction)..."
export MIMIC_EXTRACT_OUTPUT_DIR="/opt/mimic-extract/data/curated/pop5000"
export POP_SIZE=5000
export NUMERICS_BATCH_SIZE=0
export MIN_AGE=15
export MAX_AGE=999
export MIN_DURATION=12
export MAX_DURATION=240
export MIN_PERCENT=0

# Use APPTAINERENV_ prefix; PGHOST is socket dir inside container (bind mount)
export APPTAINERENV_PGHOST="${APPTAINER_PGHOST:-/tmp/pg_socket}"
export APPTAINERENV_PGPORT=5432
export APPTAINERENV_PGDATABASE=mimic
export APPTAINERENV_PGUSER=mimic
export APPTAINERENV_PGPASSWORD=mimic
export APPTAINERENV_MIMIC_EXTRACT_OUTPUT_DIR="/opt/mimic-extract/data/curated/pop5000"
export APPTAINERENV_POP_SIZE=5000
export APPTAINERENV_NUMERICS_BATCH_SIZE=0
export APPTAINERENV_MIN_AGE=15
export APPTAINERENV_MAX_AGE=999
export APPTAINERENV_MIN_DURATION=12
export APPTAINERENV_MAX_DURATION=240
export APPTAINERENV_MIN_PERCENT=0
apptainer run \
    --bind "$MIMIC_DATA:/mimic_data:ro" \
    --bind "$CURATED_OUT:/opt/mimic-extract/data/curated" \
    --bind "$PG_SOCKET:/tmp/pg_socket" \
    "$SIF_PATH"

echo ""
echo "Setup complete. Postgres has MIMIC data and concepts."
echo "To run extraction jobs in parallel, use:"
echo "  PGHOST=$PG_SOCKET PG_SOCKET_DIR=$PG_SOCKET bash apptainer/jobs/submit_all.sh"
echo ""
# This is the point of the job. Blocking here keeps Postgres — and therefore the
# socket every extraction job connects through — alive until SLURM kills us.
# Two ways to block because native Postgres daemonises (so there's no child to
# wait on, hence polling the pidfile) while the container runs in the foreground.
#
# When this job dies, every in-flight extraction job dies with it.
echo "Keeping Postgres running for 24h (job time limit)."
if [ "$USE_NATIVE" = "1" ]; then
  while kill -0 $(head -1 "$POSTGRES_DATA/postmaster.pid" 2>/dev/null) 2>/dev/null; do sleep 60; done
else
  wait $PGPID
fi
