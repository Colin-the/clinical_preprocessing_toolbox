#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-boundary-counts
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=0:30:00
#SBATCH --output=rerun/logs/pre_boundary_counts_%j.log

# Keep `set` below the #SBATCH block — sbatch stops reading directives at the
# first non-comment line, so moving this up silently voids every request above.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

# Must run BEFORE the vital ranges are widened — this is the "before" measurement.
.venv_centroid_recompute/bin/python rerun/measure_boundary_counts.py
