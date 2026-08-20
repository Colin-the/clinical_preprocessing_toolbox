#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-admission-ids
#SBATCH --array=0-4
#SBATCH --cpus-per-task=4
#SBATCH --mem=100G
#SBATCH --time=6:00:00
#SBATCH --output=rerun/logs/e_admission_ids_%A_%a.log

# Keep `set` below the #SBATCH block — see job_a_fill_missing.sh.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

# Same shape as stage A: one task per aggregation, 100G because holding the
# 46k raw records plus an aggregated copy is the memory high-water mark.
.venv_centroid_recompute/bin/python rerun/regen_admission_ids.py
