#!/bin/bash
#SBATCH --job-name=refresh_mimic_nb
#SBATCH --output=/home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/MIMIC_Extract/logs/refresh_mimic_nb_%j.out
#SBATCH --error=/home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/MIMIC_Extract/logs/refresh_mimic_nb_%j.err
#SBATCH --time=10:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G

set -euo pipefail

source "/home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/MIMIC_Extract/.venv_stats/bin/activate"

jupyter nbconvert --to notebook --execute --inplace "/home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/MIMIC_Extract/notebooks/curated_mimic_iii_analysis_executed copy 2.ipynb"
