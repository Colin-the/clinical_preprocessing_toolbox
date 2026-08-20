#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-impact-cv
#SBATCH --array=0-9
#SBATCH --cpus-per-task=16
#SBATCH --mem=100G
#SBATCH --time=6:00:00
#SBATCH --output=rerun/logs/f_filter_impact_cv_%A_%a.log

# Keep `set` below the #SBATCH block — see job_a_fill_missing.sh.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

# 10 tasks = 5 aggregations x 2 labels, same shape as stage B. 16 cores because
# the CPU backend hands n_jobs to sklearn's forest. 100G rather than stage B's
# 64G: the CV path flattens each arm's full feature matrix once and holds it for
# the duration instead of rebuilding a slice per fit.
#
# Budget: 13 arms x 5 folds x 4 repeats = 260 fits, the same count stage B ran
# (13 x 4 seeds x 5 fits), so the 6h ask has the same headroom it did there.
.venv_centroid_recompute/bin/python rerun/regen_filter_impact_cv.py
