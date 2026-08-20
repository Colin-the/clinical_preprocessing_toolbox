#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-verify-cv
#SBATCH --cpus-per-task=16
#SBATCH --mem=100G
#SBATCH --time=2:00:00
#SBATCH --output=rerun/logs/g_verify_cv_%j.log

# Keep `set` below the #SBATCH block — see job_a_fill_missing.sh.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

# --with-model turns on the shuffled-label leakage probe, which trains forests
# and so does not belong on a login node.
.venv_centroid_recompute/bin/python rerun/verify_cv.py --with-model "$@"
