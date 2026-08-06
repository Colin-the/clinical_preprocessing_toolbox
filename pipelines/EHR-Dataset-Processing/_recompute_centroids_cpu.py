"""CPU-only regeneration of the per-(agg, filter, label, polarity) centroid cache pickles.

Standalone helper run on a non-GPU node to backfill the centroid caches deleted as part of
the centroid-plot bugfix. Calls the same `compute_dataset_centroid` function that the
marimo notebook would use, so the output format is identical to what `render_marimo_mimic_iii.py`
already knows how to read.

Run with:
    .venv_centroid_recompute/bin/python _recompute_centroids_cpu.py
"""

import os
import pickle
import sys
from pathlib import Path
from types import ModuleType

# Order matters: real torch has to be imported before the stubs go in, because
# torch does its own introspection at import time and gets very confused if it
# finds a stub sitting in sys.modules where it expects a submodule of itself.
import torch  # noqa: E402

# Same stubbing trick as gallery/render_marimo_mimic_iii.py — Managers.
# evaluation_manager imports cupy and cuml at module level, and neither installs
# on a CPU node. We only call the pure-torch centroid functions, so fake modules
# are enough to get the import through.

class _Anything:
    def __init__(self, *a, **kw): pass
    def __call__(self, *a, **kw): return self
    def __getattr__(self, n): return _Anything()
    def __iter__(self): return iter([])
    def __len__(self): return 0


def _make_stub(name: str) -> None:
    m = ModuleType(name)
    m.__file__ = "<stub>"
    m.__path__ = []
    m.__spec__ = None
    m.__loader__ = None

    class _StubMod(ModuleType):
        def __getattr__(self, n):
            if n.startswith("__"):
                raise AttributeError(n)
            return _Anything()

    m.__class__ = _StubMod
    sys.modules[name] = m


for _s in (
    "cupy",
    "cudf",
    "cuml", "cuml.ensemble", "cuml.model_selection", "cuml.metrics",
    "cugraph",
):
    _make_stub(_s)

EHR_ROOT = Path("/home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing")
sys.path.insert(0, str(EHR_ROOT))

from Managers.evaluation_manager import compute_dataset_centroid  # noqa: E402

DATASET = "mimic-iii"
DATA_ROOT = EHR_ROOT / "Data" / DATASET

AGGREGATIONS = ["mean", "median", "standard deviation", "mean deviation", "maximum deviation"]
FILTER_NAMES = [
    "heart rate", "systolic blood pressure", "diastolic blood pressure",
    "mean blood pressure", "respiration rate", "temperature", "oxygen saturation",
    "fill missing data", "long missing segment", "long gap", "high invalid data",
    "all vitals",
]
LABELS = ["icu", "mortality"]
POLARITIES = ["pos", "neg"]

LABEL_INDEX_MAP = {"icu": 0, "mortality": 1}


class _DatasetShim:
    """Minimal stand-in for DatasetEHR — exposes only `.data` and `.label_index_map`,
    which is everything `compute_dataset_centroid` reads."""

    def __init__(self, data):
        self.data = data
        self.label_index_map = LABEL_INDEX_MAP


def _filter_to_filename(filter_name: str) -> str:
    """Map a filter display name to its cached dataset filename."""
    if filter_name == "raw":
        return "raw_dataset_ehr.pkl"
    slug = filter_name.replace(" ", "_")
    return f"{slug}_filtered_dataset_ehr.pkl"


def main() -> None:
    total_written = 0
    total_skipped = 0
    for agg in AGGREGATIONS:
        agg_dir = DATA_ROOT / agg
        out_dir = agg_dir / "centroids"
        out_dir.mkdir(parents=True, exist_ok=True)

        for filter_name in ["raw"] + FILTER_NAMES:
            ds_path = agg_dir / _filter_to_filename(filter_name)
            if not ds_path.exists():
                print(f"  [SKIP] missing dataset pkl: {ds_path}")
                total_skipped += 1
                continue

            print(f"  loading {agg}/{filter_name} ...", flush=True)
            raw = torch.load(ds_path, map_location="cpu", weights_only=False)
            shim = _DatasetShim(raw)

            for label in LABELS:
                for polarity in POLARITIES:
                    centroids, points = compute_dataset_centroid(shim, label, polarity)
                    out_path = out_dir / f"{label}_{filter_name}_{polarity}.pkl"
                    with open(out_path, "wb") as f:
                        pickle.dump((centroids, points), f)
                    total_written += 1
            print(f"    wrote 4 caches for {agg}/{filter_name}")

    print(f"\nDone. {total_written} centroid pkl files written, {total_skipped} dataset pkls skipped.")


if __name__ == "__main__":
    main()
