#!/bin/bash
#SBATCH --account=def-wzhang25
#SBATCH --job-name=ehr-talk-slides
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=0:30:00
#SBATCH --output=rerun/logs/l_slides_%j.log

# Keep `set` below the #SBATCH block — see job_a_fill_missing.sh.

set -euo pipefail

cd /home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing

# Stage L — the conference deck. Three renders, two interpreters.
#
# No model is fitted; every input already exists on disk. This is a job rather
# than a login-node command for the same reason stage J is: the observation-count
# heatmap unpickles the 286 MB processed_record_ehr.pkl and maps over all 46,032
# records. 16G is roughly 3x the peak that needs. Skip that one figure with
# `--only` and the rest comfortably fits in a shell.
#
# The split between the two environments is not incidental. scipy-stack has
# matplotlib and no python-pptx; .venv_slides has python-pptx and no matplotlib.
# So the figures and the baseline-threshold McNemar are produced under the module,
# left on disk, and the deck is assembled from those artifacts under the venv.

FIGURES=paper_figures/slides_png
OUT=paper_figures/slides/beyond_the_model_talk.pptx

# `sbatch rerun/job_l_slides.sh --deck-only` reassembles the deck from figures and
# a McNemar JSON that are already on disk. Iterating on slide text does not need
# the 286 MB unpickle, and skipping it takes the job from minutes to seconds.
DECK_ONLY=${1:-}

# `module` is a shell function that /etc/profile.d/z-00-computecanada.sh installs
# from CVMFS. sbatch runs this script with `#!/bin/bash`, a non-login shell, so
# profile.d is never sourced and the function does not exist — which is how the
# first attempt at this job died. Source it directly, and say so plainly if CVMFS
# is not mounted on this node rather than failing twenty lines later.
PROFILE=/cvmfs/soft.computecanada.ca/config/profile/bash.sh
if [[ ! -r "$PROFILE" ]]; then
    echo "ERROR: $PROFILE is unreadable — CVMFS is not mounted on $(hostname)." >&2
    echo "       Nothing here can run without it: scipy-stack comes from CVMFS, and" >&2
    echo "       so does the interpreter .venv_slides was built against." >&2
    exit 1
fi
# `set -u` off across the source: the CVMFS profile tests $SKIP_CC_CVMFS without a
# default, so under `set -euo pipefail` sourcing it is itself fatal.
set +u
# shellcheck disable=SC1090
source "$PROFILE"
set -u

module load scipy-stack/2026a
export MPLBACKEND=Agg

# 1. The paper's own figures, as PNG — PowerPoint cannot embed PDF. Same renderer
#    and same defaults as stage J, so these are the published figures, not
#    lookalikes. centroid_density and ecdf are not in the deck, so are not rendered.
if [[ "$DECK_ONLY" != "--deck-only" ]]; then
    python3 Experiments/render_paper_figures.py \
        --format png --dpi 200 --out "$FIGURES" \
        --only heatmap,centroid_deviation,filter_impact

    # 2. The McNemar panel at the baseline threshold, in the paper's plain style.
    python3 Experiments/render_paper_figures.py \
        --format png --dpi 200 --out "$FIGURES" --only mcnemar \
        --mcnemar-threshold baseline --mcnemar-style significance

    # 3. The same comparison as numbers, for the tables on slides 14 and 15.
    python3 rerun/dump_baseline_mcnemar.py
else
    echo "--deck-only: reusing $FIGURES and the stored baseline-threshold McNemar"
fi

# 4. The deck itself. No `module purge` — .venv_slides is built against a CVMFS
#    interpreter and purging can pull the toolchain out from under it. Unsetting
#    the two variables scipy-stack exports is enough to stop the module's
#    site-packages shadowing the venv's.
env -u PYTHONPATH -u PYTHONHOME \
    ./.venv_slides/bin/python Experiments/build_filtering_slides.py \
    --out "$OUT" --figures "$FIGURES"

echo "deck: $(pwd)/$OUT"
