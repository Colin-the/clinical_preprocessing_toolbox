#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-regen-fillmissing
#SBATCH --array=0-4
#SBATCH --cpus-per-task=4
#SBATCH --mem=100G
#SBATCH --time=6:00:00
#SBATCH --output=rerun/logs/a_fill_missing_%A_%a.log

# Keep `set` below the #SBATCH block — sbatch stops reading directives at the
# first non-comment line, so moving this up silently voids every request above.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

# One array task per aggregation method; the task id indexes AGGREGATIONS.
.venv_centroid_recompute/bin/python rerun/regen_fill_missing.py
