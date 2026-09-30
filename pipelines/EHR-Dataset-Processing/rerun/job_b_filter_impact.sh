#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-regen-impact
#SBATCH --array=0-9
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=2:00:00
#SBATCH --output=rerun/logs/b_filter_impact_%A_%a.log

# Keep `set` below the #SBATCH block — see job_a_fill_missing.sh.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

# 10 tasks = 5 aggregations x 2 labels. 16 cores because the CPU backend hands
# n_jobs to sklearn's forest; one measured (arm, seed) evaluation is ~43s on 8.
.venv_centroid_recompute/bin/python rerun/regen_filter_impact.py
