#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-regen-centroids
#SBATCH --array=0-4
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=1:00:00
#SBATCH --output=rerun/logs/c_centroids_%A_%a.log

# Keep `set` below the #SBATCH block — sbatch stops reading directives at the
# first non-comment line, so moving this up silently voids every request above.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

# One array task per aggregation; the task id indexes AGGREGATIONS. Arms are passed
# explicitly rather than left to regen_centroids.py's default, which is still the
# single 'fill missing data' arm from the 2026-08-05 rerun. `all` expands to
# _common.VITALS_DEPENDENT_ARMS — the nine arms the vital-range fix invalidates.
#
# Pass your own list after --arms to override; anything given on the command line
# wins, so `sbatch rerun/job_c_centroids.sh` alone still rebuilds all nine.
if [ "$#" -gt 0 ]; then
    .venv_centroid_recompute/bin/python rerun/regen_centroids.py "$@"
else
    .venv_centroid_recompute/bin/python rerun/regen_centroids.py --arms all
fi
