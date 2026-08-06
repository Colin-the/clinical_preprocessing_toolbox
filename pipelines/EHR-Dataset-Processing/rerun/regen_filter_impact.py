"""Stage B — rebuild <label>_filter_impact.pkl for one (aggregation, label) pair.

Every arm is retrained, not just the changed one. Two reasons: the training-F1
fix changes position 2 of the returned 5-tuple for all 13 arms, and this run uses
sklearn's random forest rather than cuML's (nibi has no GPU stack), so mixing
newly computed rows with rows carried over from the GPU run would produce a table
whose entries came from two different estimators.

That does mean absolute scores here are not comparable to the pre-fix pickles.
Comparisons *within* this run stay valid — same estimator, same seeds, same
splits across every arm — which is what the filter-vs-raw deltas and the McNemar
tests actually rest on.

    python regen_filter_impact.py "<aggregation method>" <icu|mortality>
"""
import os
import sys
import time

from _common import (  # noqa: F401
    DATA_ROOT, DATASET_NAME, FILTERS, LABELS, RANDOM_SEEDS, AGGREGATIONS,
    agg_label_from_task_id,
)
from Entities.ehr_dataset import DatasetEHR
from Managers.dataset_manager import load_raw_dataset
from Managers.evaluation_manager import evaluate_filter_impact
from Managers.serialization_manager import save_object


def _load_filtered(aggregation: str, filter_name: str) -> DatasetEHR:
    """Load one filtered dataset pickle.

    Deliberately not Managers.dataset_manager.load_filter_dataset: that also
    reads the filter's JSON change log, and Logs/ was not carried into the
    consolidated toolbox, so it raises FileNotFoundError for every arm.
    evaluate_filter_impact never looks at the change tracker, so the dataset
    alone is all that's needed here.
    """
    path = DATA_ROOT / aggregation / f"{filter_name.replace(' ', '_')}_filtered_dataset_ehr.pkl"
    dataset = DatasetEHR()
    dataset.load(str(path))
    return dataset


def main() -> None:
    if len(sys.argv) > 2:
        aggregation, label = sys.argv[1], sys.argv[2]
    else:
        aggregation, label = agg_label_from_task_id(int(os.environ["SLURM_ARRAY_TASK_ID"]))

    if aggregation not in AGGREGATIONS or label not in LABELS:
        raise SystemExit(f"bad args: {aggregation!r} {label!r}")

    print(f"[{aggregation}/{label}] loading raw dataset ...", flush=True)
    raw_dataset = load_raw_dataset(DATASET_NAME, aggregation)

    filtered = {}
    for filter_name in FILTERS:
        t0 = time.time()
        filtered[filter_name] = _load_filtered(aggregation, filter_name)
        print(f"[{aggregation}/{label}]   loaded {filter_name} "
              f"({len(filtered[filter_name].data):,} records, {time.time() - t0:.1f}s)", flush=True)

    print(f"[{aggregation}/{label}] training {len(filtered) + 1} arms x "
          f"{len(RANDOM_SEEDS)} seeds ...", flush=True)
    t0 = time.time()
    results = evaluate_filter_impact(
        raw_dataset=raw_dataset,
        filtered_datasets=filtered,
        target_label=label,
        seeds=RANDOM_SEEDS,
    )
    print(f"[{aggregation}/{label}] done in {(time.time() - t0) / 60:.1f} min", flush=True)

    out_path = DATA_ROOT / aggregation / f"{label}_filter_impact.pkl"
    save_object(results, str(out_path))
    print(f"[{aggregation}/{label}] wrote {out_path}", flush=True)

    cv, test_acc, train_f1, test_f1, _ = results
    print(f"[{aggregation}/{label}] raw arm: cv={cv[0]:.4f} test_acc={test_acc[0]:.4f} "
          f"train_f1={train_f1[0]:.4f} test_f1={test_f1[0]:.4f}", flush=True)
    if train_f1 == test_f1:
        print(f"[{aggregation}/{label}] WARNING: train and test F1 identical — "
              f"the fix did not take effect", flush=True)


if __name__ == "__main__":
    main()
