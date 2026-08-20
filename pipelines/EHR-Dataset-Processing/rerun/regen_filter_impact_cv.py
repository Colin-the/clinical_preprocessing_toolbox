"""Stage F — cross-validated filter impact for one (aggregation, label) pair.

Writes alongside the legacy artifacts rather than over them:

    Data/<dataset>/<agg>/<label>_filter_impact_cv.pkl
    Data/<dataset>/<agg>/<label>_filter_impact_cv_diagnostics.json
    Data/<dataset>/<agg>/<label>_oof_scores_cv.npz

The legacy `<label>_filter_impact.pkl` is left untouched, so the current figures
and the cross-pipeline comparison notebook keep reproducing, and the two
evaluation designs can be read side by side.

Requires stage E (`regen_admission_ids.py`) to have run for this aggregation —
every arm needs its `*_admission_ids.npy` sidecar before it can be paired.

    python regen_filter_impact_cv.py "<aggregation method>" <icu|mortality>
"""
import json
import os
import sys
import time

import numpy as np

from _common import (  # noqa: F401
    DATA_ROOT, DATASET_NAME, FILTERS, LABELS, AGGREGATIONS, agg_label_from_task_id,
)
from Entities.ehr_dataset import DatasetEHR
from Managers.evaluation_manager import evaluate_filter_impact_cv
from Managers.serialization_manager import save_object


def arm_slug(arm: str) -> str:
    return arm.replace(" ", "_").lower()


def load_arm(aggregation: str, arm: str) -> DatasetEHR:
    """Load one arm's tensors plus its admission-id sidecar.

    Deliberately not Managers.dataset_manager.load_filter_dataset — that also
    reads the filter's JSON change log, and Logs/ was not carried into the
    consolidated toolbox, so it raises FileNotFoundError for every arm. Same
    reason as regen_filter_impact.py:31.
    """
    directory = DATA_ROOT / aggregation
    if arm == "raw":
        dataset_path = directory / "raw_dataset_ehr.pkl"
    else:
        dataset_path = directory / f"{arm_slug(arm)}_filtered_dataset_ehr.pkl"

    dataset = DatasetEHR()
    dataset.load(str(dataset_path))
    dataset.load_admission_ids(str(directory / f"{arm_slug(arm)}_admission_ids.npy"))
    return dataset


def jsonable(value):
    """numpy scalars and arrays are not JSON-serialisable; coerce them."""
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def main() -> None:
    if len(sys.argv) > 2:
        aggregation, label = sys.argv[1], sys.argv[2]
    else:
        aggregation, label = agg_label_from_task_id(int(os.environ["SLURM_ARRAY_TASK_ID"]))

    if aggregation not in AGGREGATIONS or label not in LABELS:
        raise SystemExit(f"bad args: {aggregation!r} {label!r}")

    directory = DATA_ROOT / aggregation
    print(f"[{aggregation}/{label}] loading 13 arms ...", flush=True)
    t0 = time.time()

    raw_dataset = load_arm(aggregation, "raw")
    filtered = {name: load_arm(aggregation, name) for name in FILTERS}
    print(f"[{aggregation}/{label}] loaded in {time.time() - t0:.1f}s "
          f"(raw {len(raw_dataset.data):,} records)", flush=True)

    t0 = time.time()
    *results, diagnostics = evaluate_filter_impact_cv(
        raw_dataset=raw_dataset,
        filtered_datasets=filtered,
        target_label=label,
        return_diagnostics=True,
        oof_output_path=str(directory / f"{label}_oof_scores_cv.npz"),
    )
    results = tuple(results)
    print(f"[{aggregation}/{label}] evaluated in {(time.time() - t0) / 60:.1f} min", flush=True)

    pickle_path = directory / f"{label}_filter_impact_cv.pkl"
    save_object(results, str(pickle_path))

    sidecar_path = directory / f"{label}_filter_impact_cv_diagnostics.json"
    sidecar_path.write_text(json.dumps(jsonable(diagnostics), indent=1, sort_keys=True))

    cv_train_acc, oof_acc, train_f1, oof_f1, mcnemar_results = results
    print(f"[{aggregation}/{label}] wrote {pickle_path.name} and {sidecar_path.name}", flush=True)
    print(f"[{aggregation}/{label}] raw: oof_acc={oof_acc[0]:.4f} "
          f"(+/-{diagnostics['raw']['accuracy_std']:.4f} across repeats) "
          f"oof_f1={oof_f1[0]:.4f} n={diagnostics['raw']['n_records']:,} "
          f"coverage={diagnostics['raw']['coverage']:.3f}", flush=True)

    # The whole reason this rework exists — surface it rather than burying it in
    # the sidecar, so a failed pairing is obvious in the job log.
    for name in ['raw', *FILTERS]:
        detail = diagnostics[name]['mcnemar']
        flag = "  <-- DEGENERATE" if detail['degenerate'] else ""
        print(f"    {name:26s} n_paired={detail['n_paired']:6,} "
              f"n01={detail['n01']:5,} n10={detail['n10']:5,}{flag}", flush=True)


if __name__ == "__main__":
    main()
