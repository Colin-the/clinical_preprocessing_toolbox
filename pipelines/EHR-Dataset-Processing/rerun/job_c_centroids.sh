#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-regen-centroids
#SBATCH --array=0-4
#SBATCH --cpus-per-task=2
#SBATCH --mem=48G
#SBATCH --time=2:00:00
#SBATCH --output=rerun/logs/c_centroids_%A_%a.log

# Keep `set` below the #SBATCH block — see job_a_fill_missing.sh.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

.venv_centroid_recompute/bin/python rerun/regen_centroids.py
