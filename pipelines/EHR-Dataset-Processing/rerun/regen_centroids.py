"""Stage C — refresh the centroid caches for the one dataset the fixes changed.

Only 'fill missing data' is rebuilt; the other arms' centroids are still valid,
and recomputing them would churn files for no reason. Output format matches
_recompute_centroids_cpu.py exactly, which is what render_marimo_mimic_iii.py
and render_paper_figures.py read.

    python regen_centroids.py "<aggregation method>"
"""
import os
import pickle
import sys
import time

from _common import DATA_ROOT, AGGREGATIONS, agg_from_task_id  # noqa: F401
from Managers.evaluation_manager import compute_dataset_centroid

import torch

FILTER_NAME = "fill missing data"
LABELS = ["icu", "mortality"]
POLARITIES = ["pos", "neg"]
LABEL_INDEX_MAP = {"icu": 0, "mortality": 1}


class _DatasetShim:
    """`compute_dataset_centroid` only reads .data and .label_index_map."""

    def __init__(self, data):
        self.data = data
        self.label_index_map = LABEL_INDEX_MAP


def main() -> None:
    if len(sys.argv) > 1:
        aggregation = sys.argv[1]
    else:
        aggregation = agg_from_task_id(int(os.environ["SLURM_ARRAY_TASK_ID"]))

    agg_dir = DATA_ROOT / aggregation
    out_dir = agg_dir / "centroids"
    out_dir.mkdir(parents=True, exist_ok=True)

    ds_path = agg_dir / f"{FILTER_NAME.replace(' ', '_')}_filtered_dataset_ehr.pkl"
    if not ds_path.exists():
        raise SystemExit(f"missing {ds_path} — stage A must run first")

    print(f"[{aggregation}] loading {ds_path.name} ...", flush=True)
    t0 = time.time()
    raw = torch.load(ds_path, map_location="cpu", weights_only=False)
    print(f"[{aggregation}] loaded in {time.time() - t0:.1f}s", flush=True)

    shim = _DatasetShim(raw)
    for label in LABELS:
        for polarity in POLARITIES:
            centroids, points = compute_dataset_centroid(shim, label, polarity)
            out_path = out_dir / f"{label}_{FILTER_NAME}_{polarity}.pkl"
            with open(out_path, "wb") as f:
                pickle.dump((centroids, points), f)
            print(f"[{aggregation}] wrote {out_path.name} "
                  f"({len(points):,} points)", flush=True)


if __name__ == "__main__":
    main()
