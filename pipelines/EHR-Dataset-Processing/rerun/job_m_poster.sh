#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-poster
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=0:15:00
#SBATCH --output=rerun/logs/m_poster_%j.log

# Keep `set` below the #SBATCH block — see job_a_fill_missing.sh.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

# Stage M — the A0 conference poster. Same inputs as stage L's deck, one interpreter.
#
# Everything runs under scipy-stack: matplotlib for the figures, lualatex and
# pdftoppm from the CVMFS gentoo layer. No model is fitted, and unlike stage L the
# poster does not use the observation-count heatmap (at A0 column width its ticks
# print at 11pt), so nothing here touches the 286 MB records pickle. The largest
# input is ~67 MB of centroid caches; 4G is generous.
#
#   sbatch rerun/job_m_poster.sh              full build
#   sbatch rerun/job_m_poster.sh --tex-only   re-typeset from figures already on disk

POSTER=paper_figures/poster
FIGURES=$POSTER/figures
TEX=Experiments/poster/beyond_the_model_poster.tex
MODE=${1:-}

# `module` comes from CVMFS profile.d, which a non-login sbatch shell never sources.
# See job_l_slides.sh for why this is sourced directly and why `set -u` is dropped
# around it.
PROFILE=/cvmfs/soft.computecanada.ca/config/profile/bash.sh
if [[ ! -r "$PROFILE" ]]; then
    echo "ERROR: $PROFILE is unreadable — CVMFS is not mounted on $(hostname)." >&2
    exit 1
fi
set +u
# shellcheck disable=SC1090
source "$PROFILE"
set -u

module load scipy-stack/2026a
export MPLBACKEND=Agg
mkdir -p "$FIGURES"

if [[ "$MODE" != "--tex-only" ]]; then
    # 1. The published centroid figure, as vector PDF. It is placed at about half
    #    its natural width, so its type is scaled up to print at ~20pt.
    python3 Experiments/render_paper_figures.py \
        --format pdf --font-scale 1.5 --out "$FIGURES" --only centroid_deviation

    # 2. The poster's own figures, and the number macros the text quotes.
    python3 Experiments/render_poster_figures.py --out "$POSTER"
else
    echo "--tex-only: reusing $FIGURES and $POSTER/numbers.tex"
fi

# 3. Typeset. Twice, so the tcolorbox raster settles; run from the repo root, which
#    is what every path in the .tex is relative to.
for pass in 1 2; do
    lualatex -interaction=nonstopmode -halt-on-error \
        -output-directory="$POSTER" "$TEX" > "$POSTER/lualatex_pass$pass.out"
done
grep -E "Overfull|Underfull|LaTeX Warning|Missing logo" "$POSTER/beyond_the_model_poster.log" || true

# 4. A small preview for checking the layout by eye.
pdftoppm -r 24 -png -singlefile "$POSTER/beyond_the_model_poster.pdf" "$POSTER/preview"

echo "poster: $(pwd)/$POSTER/beyond_the_model_poster.pdf"
