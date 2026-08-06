#!/bin/bash
# Sequentially extract all 13 cohort scenarios.
#
# The scenarios exist to answer "how sensitive is the downstream classifier to
# the cohort you pick?" — hence the age bands at three centres × three widths,
# which sweep the trade-off between a tighter, more homogeneous cohort and
# having enough patients left to train on.
#
# Sequential, so budget days rather than hours. apptainer/jobs/submit_all.sh
# runs the same scenarios as parallel SLURM jobs and is what you usually want;
# this script is the fallback for when you can't rely on all the jobs landing
# on the setup node.
#
#   module load apptainer
#   bash apptainer/run_all_scenarios_apptainer.sh    # from the project root
#
# Needs: Postgres already up with MIMIC-III loaded (start_postgres_apptainer.sh),
# the CSVs in data/mimiciii/1.4/, and mimextract.sif built.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SIF_PATH="${MIMEXTRACT_SIF:-$PROJECT_ROOT/apptainer/mimextract.sif}"
MIMIC_DATA="${MIMIC_DATA_PATH:-$PROJECT_ROOT/data/mimiciii/1.4}"
CURATED_OUT="${CURATED_OUTPUT:-$PROJECT_ROOT/data/curated}"
PG_SOCKET="${PG_SOCKET_DIR:-$PROJECT_ROOT/data/pg_socket}"

# PGHOST does double duty: a directory path means "connect over a Unix socket",
# anything else is treated as a hostname. Defaults to the socket because that's
# the only thing that works on Compute Canada.
export PGHOST="${PGHOST:-$PG_SOCKET}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-mimic}"
export PGUSER="${PGUSER:-mimic}"
export PGPASSWORD="${PGPASSWORD:-mimic}"

cd "$PROJECT_ROOT"
mkdir -p "$CURATED_OUT"

if [ ! -f "$SIF_PATH" ]; then
    echo "ERROR: SIF not found at $SIF_PATH"
    echo "Build it with: apptainer build $SIF_PATH apptainer/mimic-extract.def"
    exit 1
fi

echo "=============================================="
echo "MIMIC-Extract (Apptainer): Running all scenarios"
echo "SIF: $SIF_PATH"
echo "PGHOST: $PGHOST"
echo "Output: $CURATED_OUT"
echo "=============================================="

# run_scenario <display name> <output subdir> [KEY=VALUE ...]
#
# The extractor takes no CLI flags — it reads everything from the environment —
# so the KEY=VALUE arguments get parsed here and re-exported rather than passed
# through. Only the six recognised keys survive; a typo'd key is silently
# ignored and you get the default, which is the easiest way to run a scenario
# that isn't the one you thought.
run_scenario() {
    local name="$1"
    local out_subdir="$2"
    shift 2
    local extra_args=("$@")

    echo ""
    echo ">>> Scenario: $name"
    echo ">>> Output: $CURATED_OUT/$out_subdir/"

    # Path *inside* the container — the bind mount below maps it back out to
    # $CURATED_OUT on the host.
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

    # Apptainer doesn't inherit the caller's environment — anything the container
    # needs has to be re-exported with an APPTAINERENV_ prefix, which it strips
    # on the way in. Hence every variable appearing twice.
    export APPTAINERENV_PGHOST="$PGHOST"
    export APPTAINERENV_PGPORT="$PGPORT"
    export APPTAINERENV_PGDATABASE="$PGDATABASE"
    export APPTAINERENV_PGUSER="$PGUSER"
    export APPTAINERENV_PGPASSWORD="$PGPASSWORD"
    export APPTAINERENV_MIMIC_EXTRACT_OUTPUT_DIR="$MIMIC_EXTRACT_OUTPUT_DIR"
    export APPTAINERENV_POP_SIZE="$POP_SIZE"
    export APPTAINERENV_NUMERICS_BATCH_SIZE="$NUMERICS_BATCH_SIZE"
    export APPTAINERENV_MIN_AGE="$MIN_AGE"
    export APPTAINERENV_MAX_AGE="$MAX_AGE"
    export APPTAINERENV_MIN_DURATION="$MIN_DURATION"
    export APPTAINERENV_MAX_DURATION="$MAX_DURATION"
    export APPTAINERENV_MIN_PERCENT="$MIN_PERCENT"
    # Read-only mount for the source CSVs so a bug can't corrupt the raw data.
    BIND_ARGS="--bind $MIMIC_DATA:/mimic_data:ro --bind $CURATED_OUT:/opt/mimic-extract/data/curated"
    # If PGHOST is an absolute path we're on the socket route: bind the socket
    # directory in and rewrite PGHOST to the in-container path, since the host
    # path means nothing inside. This line is what makes the whole no-networking
    # approach work.
    [[ "$PGHOST" == /* ]] && BIND_ARGS="$BIND_ARGS --bind $PGHOST:/tmp/pg_socket" && export APPTAINERENV_PGHOST=/tmp/pg_socket
    apptainer run $BIND_ARGS "$SIF_PATH"

    echo ">>> Completed scenario: $name"
}

# Called before every scenario because run_scenario exports into the shell's own
# environment — without this, MIN_AGE from one scenario leaks into the next and
# you get cohorts nobody asked for. The `${VAR:-default}` guards inside
# run_scenario deliberately do *not* protect against this, since they only apply
# when a variable is unset.
reset_defaults() {
    export POP_SIZE=0
    export NUMERICS_BATCH_SIZE=0
    export MIN_AGE=15
    export MAX_AGE=999
    export MIN_DURATION=12
    export MAX_DURATION=240
    export MIN_PERCENT=0
}

# Each of the first four isolates one cohort knob against the defaults, so its
# effect on the downstream classifier is attributable to that knob alone.
reset_defaults
run_scenario "pop5000 (medium cohort)" "pop5000" "POP_SIZE=5000"

reset_defaults
run_scenario "min48hr (long stays only)" "min48hr" "MIN_DURATION=48"

reset_defaults
run_scenario "min18age (adults only)" "min18age" "MIN_AGE=18"

reset_defaults
run_scenario "minperc5 (stricter missingness)" "minperc5" "MIN_PERCENT=5"

# Nine age bands: centres at 35/45/55, each ±5, ±10, ±15. The grid separates
# "which age group" from "how narrow a group" — a narrow band is more
# homogeneous but leaves far fewer patients, and these scenarios are how we see
# where that trade stops paying.
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

echo ""
echo "=============================================="
echo ">>> All scenarios complete!"
echo ">>> Output: $CURATED_OUT/"
echo "=============================================="
