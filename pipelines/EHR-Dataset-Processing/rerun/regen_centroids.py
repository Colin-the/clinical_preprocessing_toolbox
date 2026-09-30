"""Stage C — refresh the centroid caches for the arms a rerun changed.

Output format matches _recompute_centroids_cpu.py exactly, which is what
render_marimo_mimic_iii.py and render_paper_figures.py read.

Which arms to rebuild is a property of the rerun, not of this script, so it is a
flag. The default is the single 'fill missing data' arm, which is what the
2026-08-05 bugfix rerun needed and what job_c has always passed implicitly —
keeping it means an old invocation still does the old thing. The 2026-08-30
vital-range rerun (bug register F-02) touches nine arms and passes them
explicitly; `--arms all` is shorthand for _common.VITALS_DEPENDENT_ARMS.

Recomputing an arm whose dataset did not change is wasteful but not harmful —
the centroid is a pure function of the pickle on disk.

    python regen_centroids.py "<aggregation method>"
    python regen_centroids.py "mean" --arms "oxygen saturation" "all vitals"
    python regen_centroids.py "mean" --arms all
"""
import os
import pickle
import sys
import time

from _common import (  # noqa: F401
    DATA_ROOT, AGGREGATIONS, VITALS_DEPENDENT_ARMS, agg_from_task_id,
)
from Managers.evaluation_manager import compute_dataset_centroid

import torch

DEFAULT_ARMS = ["fill missing data"]
LABELS = ["icu", "mortality"]
POLARITIES = ["pos", "neg"]
LABEL_INDEX_MAP = {"icu": 0, "mortality": 1}


class _DatasetShim:
    """`compute_dataset_centroid` only reads .data and .label_index_map."""

    def __init__(self, data):
        self.data = data
        self.label_index_map = LABEL_INDEX_MAP


def parse_args(argv):
    """Positional aggregation (optional, else from SLURM), then an optional --arms list."""
    arms = list(DEFAULT_ARMS)
    if "--arms" in argv:
        cut = argv.index("--arms")
        arms, argv = argv[cut + 1:], argv[:cut]
        if arms == ["all"]:
            arms = list(VITALS_DEPENDENT_ARMS)
        if not arms:
            raise SystemExit("--arms given with no arm names")

    aggregation = argv[0] if argv else agg_from_task_id(int(os.environ["SLURM_ARRAY_TASK_ID"]))
    return aggregation, arms


def main() -> None:
    aggregation, arms = parse_args(sys.argv[1:])

    if aggregation not in AGGREGATIONS:
        raise SystemExit(f"unknown aggregation {aggregation!r}; expected one of {AGGREGATIONS}")

    agg_dir = DATA_ROOT / aggregation
    out_dir = agg_dir / "centroids"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{aggregation}] {len(arms)} arm(s): {', '.join(arms)}", flush=True)

    # Check every input up front. A missing pickle means the dataset stage did not run
    # for this arm, and finding that out after twenty minutes of centroids is worse
    # than finding it out now.
    paths = {}
    for arm in arms:
        # Same slug rule as create_filter_dataset (dataset_manager.py:85).
        slug = arm.replace(" ", "_").lower()
        name = "raw_dataset_ehr.pkl" if arm == "raw" else f"{slug}_filtered_dataset_ehr.pkl"
        path = agg_dir / name
        if not path.exists():
            raise SystemExit(f"missing {path} — the dataset stage (job_k / job_a) must run first")
        paths[arm] = path

    for arm in arms:
        print(f"[{aggregation}/{arm}] loading {paths[arm].name} ...", flush=True)
        t0 = time.time()
        raw = torch.load(paths[arm], map_location="cpu", weights_only=False)
        print(f"[{aggregation}/{arm}] loaded in {time.time() - t0:.1f}s", flush=True)

        shim = _DatasetShim(raw)
        for label in LABELS:
            for polarity in POLARITIES:
                centroids, points = compute_dataset_centroid(shim, label, polarity)
                out_path = out_dir / f"{label}_{arm}_{polarity}.pkl"
                with open(out_path, "wb") as f:
                    pickle.dump((centroids, points), f)
                print(f"[{aggregation}/{arm}] wrote {out_path.name} "
                      f"({len(points):,} points)", flush=True)

        del raw, shim


if __name__ == "__main__":
    main()
