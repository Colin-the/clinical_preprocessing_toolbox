#!/bin/bash
# run MIMIC-Extract pipeline for all scenarios

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

cd "$PROJECT_ROOT"
COMPOSE_ARG="-f $SCRIPT_DIR/docker-compose.yml"

# make output directory
mkdir -p data/curated

# start Postgres 
echo "starting Postgres..."
docker compose $COMPOSE_ARG up -d postgres

# wait for Postgres
echo "waiting for Postgres..."
sleep 5
until docker compose $COMPOSE_ARG exec -T postgres pg_isready -U mimic -d mimic 2>/dev/null; do
  echo "  Postgres not ready, waiting..."
  sleep 3
done
echo "Postgres is ready."
echo ""

run_scenario() {
  local name="$1"
  local out_subdir="$2"
  shift 2
  local extra_args=("$@")

  echo "scenario: $name"
  echo "output: data/curated/$out_subdir/"

  export MIMIC_EXTRACT_OUTPUT_DIR="/opt/mimic-extract/data/curated/$out_subdir"
  export POP_SIZE="${POP_SIZE:-0}"
  export NUMERICS_BATCH_SIZE="${NUMERICS_BATCH_SIZE:-0}"
  export MIN_AGE="${MIN_AGE:-15}"
  export MAX_AGE="${MAX_AGE:-999}"
  export MIN_DURATION="${MIN_DURATION:-12}"
  export MAX_DURATION="${MAX_DURATION:-240}"
  export MIN_PERCENT="${MIN_PERCENT:-0}"

  for arg in "${extra_args[@]}"; do
    case "$arg" in
      POP_SIZE=*) export POP_SIZE="${arg#*=}" ;;
      MIN_AGE=*) export MIN_AGE="${arg#*=}" ;;
      MAX_AGE=*) export MAX_AGE="${arg#*=}" ;;
      MIN_DURATION=*) export MIN_DURATION="${arg#*=}" ;;
      MAX_DURATION=*) export MAX_DURATION="${arg#*=}" ;;
      MIN_PERCENT=*) export MIN_PERCENT="${arg#*=}" ;;
    esac
  done

  docker compose $COMPOSE_ARG run --rm \
    -e MIMIC_EXTRACT_OUTPUT_DIR \
    -e POP_SIZE \
    -e NUMERICS_BATCH_SIZE \
    -e MIN_AGE \
    -e MAX_AGE \
    -e MIN_DURATION \
    -e MAX_DURATION \
    -e MIN_PERCENT \
    mimic-extract

  echo ""
  echo "completed scenario: $name"
  echo ""
}

# reset defaults before each scenario
reset_defaults() {
  export POP_SIZE=0
  export NUMERICS_BATCH_SIZE=0
  export MIN_AGE=15
  export MAX_AGE=999
  export MIN_DURATION=12
  export MAX_DURATION=240
  export MIN_PERCENT=0
}

# 1. Medium cohort: 5000 ICU stays
reset_defaults
run_scenario "pop5000 (medium cohort)" "pop5000" "POP_SIZE=5000"

# 2. long stays only: min 48 hours
reset_defaults
run_scenario "min48hr (long stays only)" "min48hr" "MIN_DURATION=48"

# 3. adults only: min age 18
reset_defaults
run_scenario "min18age (adults only)" "min18age" "MIN_AGE=18"

# 4. stricter missingness: drop cols with >95% missing
reset_defaults
run_scenario "minperc5 (stricter missingness)" "minperc5" "MIN_PERCENT=5"

# target ages 35, 45, 55 with ranges 5, 10, 15 years
reset_defaults
run_scenario "age35_range5 (ages 33-37)" "age35_range5" "MIN_AGE=33" "MAX_AGE=37"
reset_defaults
run_scenario "age35_range10 (ages 30-40)" "age35_range10" "MIN_AGE=30" "MAX_AGE=40"
reset_defaults
run_scenario "age35_range15 (ages 28-42)" "age35_range15" "MIN_AGE=28" "MAX_AGE=42"
reset_defaults
run_scenario "age45_range5 (ages 43-47)" "age45_range5" "MIN_AGE=43" "MAX_AGE=47"
reset_defaults
run_scenario "age45_range10 (ages 40-50)" "age45_range10" "MIN_AGE=40" "MAX_AGE=50"
reset_defaults
run_scenario "age45_range15 (ages 38-52)" "age45_range15" "MIN_AGE=38" "MAX_AGE=52"
reset_defaults
run_scenario "age55_range5 (ages 53-57)" "age55_range5" "MIN_AGE=53" "MAX_AGE=57"
reset_defaults
run_scenario "age55_range10 (ages 50-60)" "age55_range10" "MIN_AGE=50" "MAX_AGE=60"
reset_defaults
run_scenario "age55_range15 (ages 48-62)" "age55_range15" "MIN_AGE=48" "MAX_AGE=62"

echo "All scenarios complete!"

