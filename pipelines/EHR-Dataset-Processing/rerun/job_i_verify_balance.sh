#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-verify-balance
#SBATCH --cpus-per-task=16
#SBATCH --mem=100G
#SBATCH --time=2:00:00
#SBATCH --output=rerun/logs/i_verify_balance_%j.log

# Keep `set` below the #SBATCH block — see job_a_fill_missing.sh.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

# --with-model turns on the shuffled-label leakage probe, which trains forests
# for each strategy and so does not belong on a login node. Same reasoning as
# job_g_verify.sh.
.venv_centroid_recompute/bin/python rerun/verify_balance.py --with-model "$@"
