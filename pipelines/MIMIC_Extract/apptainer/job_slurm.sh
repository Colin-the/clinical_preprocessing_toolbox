#!/bin/bash
#SBATCH --job-name=mimic-extract
#SBATCH --mem=100G
#SBATCH --cpus-per-task=8
#SBATCH --time=72:00:00
#SBATCH --output=mimic_extract_%j.log

# Adjust partition/account for your cluster
# #SBATCH --partition=standard
# #SBATCH --account=your_account

module load apptainer

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SLURM_SUBMIT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PG_SOCKET="${PG_SOCKET_DIR:-$PROJECT_ROOT/data/pg_socket}"
POSTGRES_SIF="${POSTGRES_SIF:-$PROJECT_ROOT/apptainer/postgres.sif}"
cd "$PROJECT_ROOT"
mkdir -p "$PG_SOCKET"

# Build Postgres SIF if missing (avoids "Transport endpoint is not connected")
[ -f "$POSTGRES_SIF" ] || { echo "Building Postgres SIF..."; apptainer build "$POSTGRES_SIF" docker://postgres:15; }

# Start Postgres in background (uses Unix socket, no --network host)
bash apptainer/start_postgres_apptainer.sh &
PGPID=$!
sleep 30

export PGHOST="$PG_SOCKET"
until apptainer exec --bind "$PG_SOCKET:/tmp/pg_socket" "$POSTGRES_SIF" \
    psql "host=/tmp/pg_socket user=mimic dbname=postgres" -c '\q' 2>/dev/null; do
  echo "Waiting for Postgres..."
  sleep 5
done
echo "Postgres is ready."
apptainer exec --bind "$PG_SOCKET:/tmp/pg_socket" "$POSTGRES_SIF" \
  psql "host=/tmp/pg_socket user=mimic dbname=postgres" -tc "SELECT 1 FROM pg_database WHERE datname='mimic'" 2>/dev/null | grep -q 1 || \
apptainer exec --bind "$PG_SOCKET:/tmp/pg_socket" "$POSTGRES_SIF" \
  psql "host=/tmp/pg_socket user=mimic dbname=postgres" -c "CREATE DATABASE mimic"

# Run all scenarios
bash apptainer/run_all_scenarios_apptainer.sh

# Stop Postgres
kill $PGPID 2>/dev/null || true
echo "Done."
