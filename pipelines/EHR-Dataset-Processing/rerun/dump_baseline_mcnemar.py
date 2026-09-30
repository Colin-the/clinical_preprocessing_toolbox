"""Write the baseline-threshold McNemar comparison to JSON, one file per label.

    python rerun/dump_baseline_mcnemar.py     # needs scipy-stack (numpy + scipy)

`Experiments/build_filtering_slides.py` reports the McNemar comparison the paper's
Fig. 7 shows — every arm re-scored at raw's mean Youden threshold, so the test
isolates the filter rather than the operating point that moved with it. That
comparison is computed by `mcnemar_at_baseline_threshold`, which lives in
`render_paper_figures.py` and therefore drags in matplotlib.

The deck is built in `.venv_slides`, which has python-pptx and no matplotlib, so the
two cannot run in one interpreter. This script is the seam: it runs under
scipy-stack alongside the figure render and leaves the numbers on disk as

    Data/mimic-iii/mean/<label>_mcnemar_baseline_threshold.json
    { "<arm>": {"p": float, "n01": int, "n10": int, "n_paired": int}, ... }

`n_paired` is read from the stage F diagnostics rather than recomputed: it is the
size of the arm/baseline intersection, which does not depend on where the scores
are thresholded. The p-values and discordance counts do, and those are the ones
`mcnemar_at_baseline_threshold` recomputes — it self-checks against the stored
sidecar before returning, so a stale artifact raises here rather than reaching a slide.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Experiments"))

from render_paper_figures import (  # noqa: E402
    AGG, DATA_ROOT, FILTER_NAMES, mcnemar_at_baseline_threshold,
)

LABELS = ("mortality", "icu")


def main() -> None:
    for label in LABELS:
        p_values, directions = mcnemar_at_baseline_threshold(label)
        diagnostics = json.loads(
            (DATA_ROOT / AGG / f"{label}_filter_impact_cv_diagnostics.json").read_text()
        )

        payload = {}
        for arm, p in zip(FILTER_NAMES, p_values):
            n01, n10 = directions[arm]
            payload[arm] = {
                "p": float(p),
                "n01": int(n01),
                "n10": int(n10),
                "n_paired": int(diagnostics[arm]["mcnemar"]["n_paired"]),
            }

        out = DATA_ROOT / AGG / f"{label}_mcnemar_baseline_threshold.json"
        out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
        print(f"wrote {out}")
        for arm in FILTER_NAMES:
            entry = payload[arm]
            print(f"    {arm:26s} n={entry['n_paired']:6,d}  "
                  f"n01={entry['n01']:5,d} n10={entry['n10']:5,d}  "
                  f"p={entry['p']:.4g}")


if __name__ == "__main__":
    main()
