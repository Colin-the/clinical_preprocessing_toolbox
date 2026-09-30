"""Tabulate stage H — the four balancing strategies, side by side.

    python Experiments/render_balance_comparison.py [--out DIR]

Reads only the `<label>_balance_impact_cv_diagnostics.json` sidecars, so it needs
neither the GPU shims nor the dataset pickles and runs anywhere. Writes a tidy
CSV plus markdown tables to `paper_figures/balance/`.

Why the columns are ordered the way they are: accuracy is deliberately *not*
first-among-equals. At 9.7% mortality prevalence the unbalanced baseline scores
~0.91 by predicting almost nothing positive, so accuracy rewards exactly the
behaviour this experiment is trying to fix. Recall and balanced accuracy show the
trade being made; AUROC and AUPRC are computed from the scores rather than the
0.5 cut and are the only columns that answer "did the model actually get better
at ranking patients", as opposed to "did it relabel more of them positive".
"""
import argparse
import json
import pickle
import sys
from pathlib import Path

import pandas as pd

# Same bootstrap as render_paper_figures.py:70 — run as a script, sys.path[0] is
# Experiments/, not the repo root.
EHR_ROOT = Path(__file__).resolve().parent.parent
if str(EHR_ROOT) not in sys.path:
    sys.path.insert(0, str(EHR_ROOT))

from Managers.path_manager import get_project_root  # noqa: E402

PROJECT_ROOT = Path(get_project_root())
DATASET_NAME = "mimic-iii"
AGGREGATIONS = ["mean", "median", "standard deviation", "mean deviation", "maximum deviation"]
LABELS = ["icu", "mortality"]
STRATEGY_ORDER = ["none", "oversample", "undersample", "smote"]

METRICS = [
    ("recall", "Recall"),
    ("balanced_accuracy", "Balanced Acc"),
    ("auprc", "AUPRC"),
    ("auroc", "AUROC"),
    ("f1_macro", "Macro F1"),
    ("accuracy", "Accuracy"),
]


def mcnemar_pvalues(directory: Path, label: str, arms: list) -> dict:
    """Pull the McNemar p-values out of the pickle, keyed by arm name.

    They are not in the JSON sidecar: `calculate_mcnemar_paired` puts only the
    discordant counts into the per-arm `mcnemar` detail dict, while the statistic
    and p-value are returned separately and land in position [4] of the results
    tuple. That list is ordered by `evaluate_balance_impact_cv`'s `ordered_pairs`
    (arms outermost, STRATEGY_ORDER within), which is *not* the sidecar's key
    order — the sidecar is written with sort_keys=True and so comes back
    alphabetical. Zipping the two directly would silently mislabel every p-value,
    swapping `smote` and `undersample`. Hence rebuilding the order here rather
    than trusting the JSON.
    """
    pickle_path = directory / f"{label}_balance_impact_cv.pkl"
    if not pickle_path.exists():
        return {}

    with pickle_path.open("rb") as handle:
        results = pickle.load(handle)

    ordered = [f"{arm} / {strategy}" for arm in arms for strategy in STRATEGY_ORDER]
    if len(ordered) != len(results[4]):
        return {}
    return {name: float(p) for name, (_stat, p) in zip(ordered, results[4])}


def collect() -> pd.DataFrame:
    """One row per (label, aggregation, arm, strategy).

    A missing sidecar is skipped rather than fatal — the sweep may legitimately
    have run for only some aggregations, and a partial table is more useful than
    an exception.
    """
    rows = []
    for label in LABELS:
        for aggregation in AGGREGATIONS:
            directory = PROJECT_ROOT / "Data" / DATASET_NAME / aggregation
            sidecar = directory / f"{label}_balance_impact_cv_diagnostics.json"
            if not sidecar.exists():
                continue

            diagnostics = json.loads(sidecar.read_text())
            arms = sorted({d.get("arm", n.split(" / ")[0])
                           for n, d in diagnostics.items()},
                          key=lambda a: (a != "raw", a))
            pvalues = mcnemar_pvalues(directory, label, arms)

            for name, detail in diagnostics.items():
                row = {
                    "label": label,
                    "aggregation": aggregation,
                    "arm": detail.get("arm", name.split(" / ")[0]),
                    "strategy": detail["strategy"],
                    "n_records": detail["n_records"],
                    "prevalence": detail.get("population_prevalence"),
                    "predicted_positive_rate": detail["predicted_positive_rate"],
                    "n_synthetic": detail["n_synthetic_total"],
                    "mean_train_rows": detail["mean_train_rows"],
                    "smote_fallback_folds": detail["smote_fallback_folds"],
                    "trained_on_fraction": detail["baseline_trained_on_fraction"],
                    "reused_from_cache": bool(detail.get("reused_from_cache", False)),
                    "mcnemar_p": pvalues.get(name),
                    "mcnemar_n01": detail["mcnemar"]["n01"],
                    "mcnemar_n10": detail["mcnemar"]["n10"],
                    "degenerate": detail["degenerate"],
                }
                for key, _ in METRICS:
                    row[key] = detail[f"{key}_mean"]
                    row[f"{key}_std"] = detail[f"{key}_std"]
                rows.append(row)

    if not rows:
        raise SystemExit(
            "no stage H sidecars found — run rerun/job_h_balance_cv.sh first"
        )

    frame = pd.DataFrame(rows)
    frame["strategy"] = pd.Categorical(frame["strategy"], STRATEGY_ORDER, ordered=True)
    return frame.sort_values(["label", "aggregation", "arm", "strategy"]).reset_index(drop=True)


def delta_table(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    """Each strategy's change against its own aggregation's `none` baseline.

    Deltas rather than absolutes because the five aggregations sit at different
    absolute levels; comparing `smote` under `mean` against `smote` under
    `maximum deviation` directly would mostly be reading the aggregation.
    """
    subset = frame[frame["label"] == label]
    out = []
    for aggregation, group in subset.groupby("aggregation", sort=False):
        baseline = group[group["strategy"] == "none"]
        if baseline.empty:
            continue
        baseline = baseline.iloc[0]
        for _, row in group.iterrows():
            if row["strategy"] == "none":
                continue
            entry = {"aggregation": aggregation, "strategy": row["strategy"]}
            for key, title in METRICS:
                entry[f"Δ {title}"] = row[key] - baseline[key]
            entry["mcnemar_p"] = row["mcnemar_p"]
            out.append(entry)
    return pd.DataFrame(out)


DELTA_COLUMNS = {
    "auprc": "d_auprc", "auroc": "d_auroc", "recall": "d_recall",
    "balanced_accuracy": "d_bal", "f1_macro": "d_f1", "accuracy": "d_acc",
    "predicted_positive_rate": "d_pos",
}

DEVIATION_AGGREGATIONS = {"standard deviation", "mean deviation", "maximum deviation"}


def tidy_deltas(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per (label, aggregation, strategy) delta, long form.

    `delta_table` above is shaped for reading; this is shaped for plotting, and
    is what `Experiments/build_balance_report.py` consumes. It used to be
    produced by hand outside the repo, which meant the report could be rebuilt
    against a stale copy — hence writing it here alongside the other outputs.
    """
    out = []
    for (label, aggregation), group in frame.groupby(["label", "aggregation"], sort=False):
        baseline = group[group["strategy"] == "none"]
        if baseline.empty:
            continue
        baseline = baseline.iloc[0]
        for _, row in group.iterrows():
            if row["strategy"] == "none":
                continue
            entry = {"label": label, "aggregation": aggregation, "strategy": row["strategy"]}
            entry.update({column: row[key] - baseline[key]
                          for key, column in DELTA_COLUMNS.items()})
            entry["family"] = ("deviation" if aggregation in DEVIATION_AGGREGATIONS
                               else "value")
            out.append(entry)
    return pd.DataFrame(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(PROJECT_ROOT / "paper_figures" / "balance"))
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    frame = collect()
    frame.to_csv(out_dir / "balance_comparison.csv", index=False)
    tidy_deltas(frame).to_csv(out_dir / "balance_deltas.csv", index=False)

    lines = ["# Class balancing — strategy comparison", ""]
    covered = frame[["label", "aggregation"]].drop_duplicates()
    lines.append(f"{len(covered)} of {len(LABELS) * len(AGGREGATIONS)} "
                 f"(label, aggregation) cells present.")
    if frame["reused_from_cache"].any():
        fraction = frame.loc[frame["reused_from_cache"], "trained_on_fraction"].iloc[0]
        lines += ["", f"> **Baseline caveat.** The `none` arm was reused from stage F and "
                      f"fitted on {fraction:.2f} of the cohort, against 0.80 for the "
                      f"balanced arms. Improvements are therefore slightly overstated."]

    for label in LABELS:
        subset = frame[frame["label"] == label]
        if subset.empty:
            continue
        lines += ["", f"## {label}", "", "### Absolute", ""]
        display = subset[["aggregation", "strategy"] + [k for k, _ in METRICS]
                         + ["predicted_positive_rate", "n_synthetic", "mcnemar_p"]]
        lines.append(display.to_markdown(index=False, floatfmt=".4f"))

        deltas = delta_table(frame, label)
        if not deltas.empty:
            lines += ["", "### Change against the unbalanced baseline", ""]
            lines.append(deltas.to_markdown(index=False, floatfmt=".4f"))

    (out_dir / "balance_comparison.md").write_text("\n".join(lines) + "\n")

    print("\n".join(lines))
    print(f"\nwrote {out_dir / 'balance_comparison.csv'}")
    print(f"wrote {out_dir / 'balance_comparison.md'}")
    print(f"wrote {out_dir / 'balance_deltas.csv'}")


if __name__ == "__main__":
    main()
