#!/bin/bash
#SBATCH --job-name=mimic-baseline-fast
#SBATCH --mem=192G
#SBATCH --cpus-per-task=16
#SBATCH --time=96:00:00
#SBATCH --output=mimic_baseline_fast_%j.log

set -euo pipefail

module load apptainer

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SLURM_SUBMIT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
SIF_PATH="${MIMEXTRACT_SIF:-$PROJECT_ROOT/apptainer/mimextract.sif}"
MIMIC_DATA="${MIMIC_DATA_PATH:-$PROJECT_ROOT/data/mimiciii/1.4}"
CURATED_OUT="${CURATED_OUTPUT:-$PROJECT_ROOT/data/curated}"
DB_SOURCE="${DB_PATH:-/scratch/$USER/mimic_data.duckdb}"

if [ ! -f "$DB_SOURCE" ]; then
  echo "ERROR: DuckDB file not found: $DB_SOURCE" >&2
  exit 1
fi

# Use node-local storage to reduce shared filesystem contention.
if [ -n "${SLURM_TMPDIR:-}" ] && [ -d "$SLURM_TMPDIR" ]; then
  LOCAL_DB_DIR="$SLURM_TMPDIR"
else
  LOCAL_DB_DIR="/scratch/$USER/slurm_${SLURM_JOB_ID}"
  mkdir -p "$LOCAL_DB_DIR"
fi
LOCAL_DB_PATH="$LOCAL_DB_DIR/mimic_data.duckdb"

echo "Copying DuckDB to local node storage..."
echo "  source: $DB_SOURCE"
echo "  local : $LOCAL_DB_PATH"
cp -f "$DB_SOURCE" "$LOCAL_DB_PATH"

export APPTAINERENV_MIMIC_EXTRACT_OUTPUT_DIR="/opt/mimic-extract/data/curated/baseline_nofilters_fast"
export APPTAINERENV_DB_PATH="$LOCAL_DB_PATH"

export POP_SIZE=0
# Run numerics in batches to avoid one giant query over all ICU stays.
export NUMERICS_BATCH_SIZE=3000
export MIN_AGE=15
export MAX_AGE=999
export MIN_DURATION=12
export MAX_DURATION=240
export MIN_PERCENT=0

export APPTAINERENV_POP_SIZE="$POP_SIZE"
export APPTAINERENV_NUMERICS_BATCH_SIZE="$NUMERICS_BATCH_SIZE"
export APPTAINERENV_MIN_AGE="$MIN_AGE"
export APPTAINERENV_MAX_AGE="$MAX_AGE"
export APPTAINERENV_MIN_DURATION="$MIN_DURATION"
export APPTAINERENV_MAX_DURATION="$MAX_DURATION"
export APPTAINERENV_MIN_PERCENT="$MIN_PERCENT"

cd "$PROJECT_ROOT"
mkdir -p "$CURATED_OUT/baseline_nofilters_fast"

echo "Running accelerated baseline extraction..."
apptainer run \
  --bind "$PROJECT_ROOT:/opt/mimic-extract" \
  --bind "$MIMIC_DATA:/mimic_data:ro" \
  --bind "$LOCAL_DB_PATH:$LOCAL_DB_PATH:ro" \
  "$SIF_PATH"

echo "Done: baseline_nofilters_fast"
