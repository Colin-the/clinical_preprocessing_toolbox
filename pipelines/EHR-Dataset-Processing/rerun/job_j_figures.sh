#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-paper-figures
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=0:30:00
#SBATCH --output=rerun/logs/j_figures_%j.log

# Keep `set` below the #SBATCH block — see job_a_fill_missing.sh.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

# No model is fitted here — every input already exists on disk. The reason this
# is a job rather than a login-node command is the observation-count heatmap:
# it unpickles the 286 MB processed_record_ehr.pkl and maps over all 46,032
# records. 16G is roughly 3x the peak that needs; the render itself is seconds.
# Skip that one figure with `--only` and this comfortably fits in a shell.
#
# scipy-stack rather than a venv: the renderer needs matplotlib/numpy/pandas/scipy
# and nothing else. Its GPU and marimo imports are stubbed in the script itself,
# so .venv_centroid_recompute (which has torch but no matplotlib) buys nothing.
#
# Extra flags are forwarded, so the legacy-design control run is
#   sbatch rerun/job_j_figures.sh --impact-suffix '' --out /tmp/legacy_check
module load scipy-stack/2026a

export MPLBACKEND=Agg
python3 Experiments/render_paper_figures.py "$@"
