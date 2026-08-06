#!/bin/bash
#SBATCH --job-name=pipeline_comparison
#SBATCH --output=/home/ccampb47/work/clinical_preprocessing_toolbox/comparison/logs/pipeline_comparison_%j.out
#SBATCH --error=/home/ccampb47/work/clinical_preprocessing_toolbox/comparison/logs/pipeline_comparison_%j.err
#SBATCH --time=4:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G

# Re-executes the comparison notebook in place, on a compute node.
#
# 64G because the notebook loads MIMIC_Extract's `vitals_labs` table whole —
# it's stored in HDF fixed format, which can't be row-filtered on read, so the
# subsetting happens in memory afterwards. Don't try this on a login node.
#
# Note `set` is deliberately below the #SBATCH block: sbatch stops reading
# directives at the first non-comment line, so putting it above would silently
# void every resource request.

set -euo pipefail

mkdir -p /home/ccampb47/work/clinical_preprocessing_toolbox/comparison/logs

# No display on a compute node; without this matplotlib picks a GUI backend and
# the first plotting cell kills the run.
export MPLBACKEND=Agg

# Borrowing MIMIC_Extract's stats venv rather than maintaining a separate one —
# it's the only environment on nibi with a working jupyter/pandas/scipy stack.
source /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/MIMIC_Extract/.venv_stats/bin/activate

cd /home/ccampb47/work/clinical_preprocessing_toolbox/comparison

# --inplace overwrites the notebook with its executed output, which is what the
# gallery's figure extraction then reads. Two hours of timeout because the
# feature-extraction cell loops over ~27,000 records per aggregation method and
# nbconvert's default would kill it partway.
jupyter nbconvert \
    --to notebook \
    --execute \
    --inplace \
    --ExecutePreprocessor.timeout=7200 \
    pipeline_comparison.ipynb

echo "Notebook execution complete."
