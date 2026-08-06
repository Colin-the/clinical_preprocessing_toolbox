#!/bin/bash
# Start PostgreSQL in Apptainer for MIMIC-Extract (runs in foreground; run in background with nohup or screen)
#
# Usage:
#   nohup bash apptainer/start_postgres_apptainer.sh > postgres.log 2>&1 &
#   # or in a screen/tmux session
#
# Then run: bash apptainer/run_all_scenarios_apptainer.sh
#
# Requires: module load apptainer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
POSTGRES_DATA="${POSTGRES_DATA_DIR:-$PROJECT_ROOT/data/postgres_data}"
PG_SOCKET="${PG_SOCKET_DIR:-$PROJECT_ROOT/data/pg_socket}"
POSTGRES_SIF="${POSTGRES_SIF:-$SCRIPT_DIR/postgres.sif}"

mkdir -p "$POSTGRES_DATA" "$PG_SOCKET"

# Build Postgres SIF if missing (avoids "Transport endpoint is not connected")
if [ ! -f "$POSTGRES_SIF" ]; then
  echo "Building Postgres SIF (one-time)..."
  apptainer build "$POSTGRES_SIF" docker://postgres:15
fi

# Use Unix socket (--network host not allowed on Compute Canada)
export APPTAINERENV_POSTGRES_USER=mimic
export APPTAINERENV_POSTGRES_PASSWORD=mimic
export APPTAINERENV_POSTGRES_DB=mimic

echo "Starting PostgreSQL (Apptainer)..."
echo "  Data dir: $POSTGRES_DATA"
echo "  Socket: $PG_SOCKET (set PGHOST=$PG_SOCKET for clients)"
echo ""

apptainer run \
    --bind "$POSTGRES_DATA:/var/lib/postgresql/data" \
    --bind "$PG_SOCKET:/tmp/pg_socket" \
    "$POSTGRES_SIF" postgres -c unix_socket_directories=/tmp/pg_socket -c autovacuum=off
