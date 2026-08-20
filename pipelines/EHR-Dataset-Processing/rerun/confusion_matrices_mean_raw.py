"""One-off: Type I / Type II tables for the raw arm, mean aggregation, both labels.

The filter-impact pickles store only aggregated scores, never predictions, so the
confusion matrices behind the 2026-08-10 accuracy drop cannot be recovered from
them and have to be recomputed. This reproduces the exact pipeline
`evaluate_dataset_label_impact` runs (same seeds, same cached split, same
sklearn forest) and reports three regimes per label:

  old    - validation concatenated onto test (n~9207), threshold 0.5, which is
           what .predict() did before the fix
  new    - test alone (n~4604), threshold from Youden's J on validation
  new@.5 - test alone, threshold 0.5

`new@.5` is the control: it shares its test set with `new` and its threshold with
`old`, so differencing isolates the operating-point effect from the set-size
effect. Without it the two changes are confounded.

Writes JSON to rerun/logs/confusion_matrices_mean_raw.json.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cpu_backend  # noqa: F401  — must precede any Managers import

import numpy as np
import torch
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_curve

from _common import DATA_ROOT, RANDOM_SEEDS
from Entities.ehr_dataset import DatasetEHR
from Managers.dataset_manager import flatten_subset_to_cupy

AGGREGATION = "mean"
N_JOBS = int(os.environ.get("SLURM_CPUS_PER_TASK", "8"))


def youden_threshold(y_val, scores_val):
    """Same rule as Managers.evaluation_manager.pick_threshold."""
    if y_val.size == 0:
        return 0.5
    positives = int(y_val.sum())
    if positives == 0 or positives == y_val.size:
        return 0.5
    fpr, tpr, thresholds = roc_curve(y_val, scores_val)
    threshold = thresholds[int(np.argmax(tpr - fpr))]
    if not np.isfinite(threshold):
        finite = thresholds[np.isfinite(thresholds)]
        threshold = float(finite.max()) if finite.size else 0.5
    return float(threshold)


def confusion(y_true, y_pred):
    y_true = y_true.astype(int)
    y_pred = y_pred.astype(int)
    return {
        "tp": int(np.sum((y_true == 1) & (y_pred == 1))),
        "fp": int(np.sum((y_true == 0) & (y_pred == 1))),  # Type I
        "fn": int(np.sum((y_true == 1) & (y_pred == 0))),  # Type II
        "tn": int(np.sum((y_true == 0) & (y_pred == 0))),
    }


def main():
    dataset = DatasetEHR()
    dataset.load(str(DATA_ROOT / AGGREGATION / "raw_dataset_ehr.pkl"))

    results = {}
    for label in ["mortality", "icu"]:
        label_index = dataset.label_index_map[label]
        per_seed = []

        for seed in RANDOM_SEEDS:
            # Mirrors evaluate_filter_impact: manual_seed before the split. The
            # split caches on split_weights, so only the first seed actually
            # draws a partition and every later seed reuses it -- reproducing
            # that here rather than working around it, since it is what the
            # cached pickles reflect.
            torch.manual_seed(seed)
            train_sub, val_sub, test_sub = dataset.split(0.8, 0.1, 0.1)

            x_train, y_train = flatten_subset_to_cupy(train_sub, label_index)
            x_val, y_val = flatten_subset_to_cupy(val_sub, label_index)
            x_test, y_test = flatten_subset_to_cupy(test_sub, label_index)

            y_train = np.asarray(y_train).astype(int)
            y_val = np.asarray(y_val).astype(int)
            y_test = np.asarray(y_test).astype(int)

            model = RandomForestClassifier(
                n_estimators=300, random_state=seed, n_jobs=N_JOBS
            )
            model.fit(np.asarray(x_train), y_train)

            classes = model.classes_.astype(int).tolist()
            col = classes.index(1) if 1 in classes else None

            def scores(x):
                if col is None:
                    return np.zeros(x.shape[0])
                return model.predict_proba(np.asarray(x))[:, col]

            s_val, s_test = scores(x_val), scores(x_test)
            threshold = youden_threshold(y_val, s_val)

            # old: validation folded back into test, thresholded at 0.5
            s_merged = np.concatenate([s_test, s_val])
            y_merged = np.concatenate([y_test, y_val])

            per_seed.append({
                "seed": seed,
                "threshold": threshold,
                "old": confusion(y_merged, s_merged >= 0.5),
                "new": confusion(y_test, s_test >= threshold),
                "new@.5": confusion(y_test, s_test >= 0.5),
            })
            print(f"{label} seed={seed} thr={threshold:.4f} done", flush=True)

        results[label] = per_seed

    out = Path(__file__).resolve().parent / "logs" / "confusion_matrices_mean_raw.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
