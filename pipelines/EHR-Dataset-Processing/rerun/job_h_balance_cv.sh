#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-balance-cv
#SBATCH --array=0-9
#SBATCH --cpus-per-task=16
#SBATCH --mem=100G
#SBATCH --time=6:00:00
#SBATCH --output=rerun/logs/h_balance_cv_%A_%a.log

# Keep `set` below the #SBATCH block — see job_a_fill_missing.sh.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

# 10 tasks = 5 aggregations x 2 labels, same shape as stages B and F.
#
# Budget: 1 arm (raw) x 3 fitted strategies x 5 folds x 4 repeats = 60 fits. That
# is far fewer than stage F's 260, but each fit is on a bigger matrix: oversample
# and SMOTE both grow the training set to 2 x n_majority, which for mortality is
# ~66k rows against stage F's ~32k. Masked SMOTE also adds a brute-force
# nan_euclidean neighbour search per fold (~10s at 16 cores for the ICU minority,
# ~1s for mortality's). 6h keeps stage F's proven envelope; check the reported
# "evaluated in N min" in the log and trim this if there is obvious headroom.
#
# The 'none' arm costs zero fits — it is re-read from stage F's cached
# <label>_oof_scores_cv.npz and re-thresholded at 0.5. Add --refit-baseline to
# fit it here instead, which adds 20 fits per task and removes the
# training-set-size confound documented in regen_balance_cv.py.
#
# Extending to all 13 arms: pass --all-arms and split the array by strategy
# (--array=0-29) to stay inside this envelope.
# Extra flags are forwarded, so the refit variant is
#   sbatch --time=2:00:00 rerun/job_h_balance_cv.sh --refit-baseline
.venv_centroid_recompute/bin/python rerun/regen_balance_cv.py "$@"
