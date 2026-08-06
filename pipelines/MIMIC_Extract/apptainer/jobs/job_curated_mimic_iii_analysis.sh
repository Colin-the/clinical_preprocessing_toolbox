#!/bin/bash
#SBATCH --job-name=mimic-curated-analysis
#SBATCH --mem=180G
#SBATCH --cpus-per-task=8
#SBATCH --time=96:00:00
#SBATCH --output=%x_%j.log

set -euo pipefail

module load apptainer >/dev/null 2>&1 || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SLURM_SUBMIT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

cd "$PROJECT_ROOT/notebooks"

NB_IN="curated_mimic_iii_analysis.ipynb"
NB_OUT="curated_mimic_iii_analysis_executed.ipynb"

VENV_PY="$PROJECT_ROOT/.venv_stats/bin/jupyter-nbconvert"
if [ ! -x "$VENV_PY" ]; then
  echo "Missing jupyter-nbconvert at: $VENV_PY" >&2
  exit 1
fi

echo "Executing notebook:"
echo "  input : $PROJECT_ROOT/notebooks/$NB_IN"
echo "  output: $PROJECT_ROOT/notebooks/$NB_OUT"

"$VENV_PY" \
  --to notebook \
  --execute \
  --output "$NB_OUT" \
  --ExecutePreprocessor.timeout=7200 \
  "$NB_IN"

echo "Done."

