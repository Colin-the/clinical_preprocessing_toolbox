#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-regen-filtered
#SBATCH --array=0-44%8
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=1:00:00
#SBATCH --output=rerun/logs/k_filtered_%A_%a.log

# Keep `set` below the #SBATCH block — sbatch stops reading directives at the
# first non-comment line, so moving this up silently voids every request above.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

# 45 tasks = 9 vitals-dependent arms x 5 aggregations; the task id indexes
# _common.arm_agg_from_task_id. Throttled to 8 concurrent (%8): this is a shared
# cluster and each task is ~5-7 min against a 4.4 GB working set, so there is
# nothing to gain from taking 45 slots at once.
.venv_centroid_recompute/bin/python rerun/regen_filtered_datasets.py
