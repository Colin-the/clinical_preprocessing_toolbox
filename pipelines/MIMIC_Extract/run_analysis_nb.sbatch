#!/bin/bash
#SBATCH --job-name=mimic_analysis_nb
#SBATCH --output=/home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/MIMIC_Extract/logs/mimic_analysis_nb_%j.out
#SBATCH --error=/home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/MIMIC_Extract/logs/mimic_analysis_nb_%j.err
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G

set -euo pipefail

source "/home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/MIMIC_Extract/.venv_stats/bin/activate"

jupyter nbconvert \
    --to notebook \
    --execute \
    --inplace \
    --ExecutePreprocessor.timeout=7200 \
    "/home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/MIMIC_Extract/notebooks/mimic_extract_analysis.ipynb"
