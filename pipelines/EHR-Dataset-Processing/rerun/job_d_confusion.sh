#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-confusion
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=1:00:00
#SBATCH --output=rerun/logs/d_confusion_%j.log

# Keep `set` below the #SBATCH block — see job_a_fill_missing.sh.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

.venv_centroid_recompute/bin/python rerun/confusion_matrices_mean_raw.py
