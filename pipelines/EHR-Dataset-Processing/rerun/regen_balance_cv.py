"""Stage H — class-balanced cross-validation for one (aggregation, label) pair.

Sweeps the balancing strategies (`none`, `oversample`, `undersample`, `smote`)
over one or more arms, at a fixed 0.5 decision threshold with no inner-validation
split. This is the training-data half of bug_register.py E-11; the threshold half
already lives in stages B and F.

Writes alongside the stage F artifacts rather than over them:

    Data/<dataset>/<agg>/<label>_balance_impact_cv.pkl
    Data/<dataset>/<agg>/<label>_balance_impact_cv_diagnostics.json
    Data/<dataset>/<agg>/<label>_balance_oof_scores_cv.npz

The `none` arm is not refitted by default. Stage F already wrote every record's
out-of-fold score to `<label>_oof_scores_cv.npz`, and scores are independent of
the operating point, so the unbalanced baseline is re-read at 0.5 for free. Pass
`--refit-baseline` to fit it properly instead — see the caveat below.

Requires stage E (`regen_admission_ids.py`) and stage F
(`regen_filter_impact_cv.py`) to have run for this aggregation and label.

    python regen_balance_cv.py "<aggregation method>" <icu|mortality>
                               [--all-arms] [--refit-baseline]

Caveat worth reading before quoting a number: without `--refit-baseline` the
baseline forests were fitted on 7/8 of the 80% training fold (stage F carved off
an inner-validation slice) while the balanced arms train on the full 80%. The
baseline is fitted on ~12% less data, which tilts the comparison toward the
balancing strategies. `baseline_trained_on_fraction` in the sidecar records which
of the two you are looking at.
"""
import json
import os
import sys
import time

import numpy as np

from _common import (  # noqa: F401
    DATA_ROOT, DATASET_NAME, FILTERS, LABELS, AGGREGATIONS, agg_label_from_task_id,
)
from regen_filter_impact_cv import jsonable, load_arm
from Managers.balancing_manager import STRATEGIES
from Managers.evaluation_manager import evaluate_balance_impact_cv
from Managers.serialization_manager import save_object


def main() -> None:
    arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}

    unknown_flags = flags - {"--all-arms", "--refit-baseline"}
    if unknown_flags:
        raise SystemExit(f"unknown flags: {sorted(unknown_flags)}")

    if len(arguments) > 1:
        aggregation, label = arguments[0], arguments[1]
    else:
        aggregation, label = agg_label_from_task_id(int(os.environ["SLURM_ARRAY_TASK_ID"]))

    if aggregation not in AGGREGATIONS or label not in LABELS:
        raise SystemExit(f"bad args: {aggregation!r} {label!r}")

    all_arms = "--all-arms" in flags
    refit_baseline = "--refit-baseline" in flags
    arm_names = ["raw"] + list(FILTERS) if all_arms else ["raw"]

    directory = DATA_ROOT / aggregation
    baseline_npz = directory / f"{label}_oof_scores_cv.npz"

    if not refit_baseline and not baseline_npz.exists():
        raise SystemExit(
            f"{baseline_npz} not found. The reused baseline comes from stage F "
            f"(rerun/job_f_filter_impact_cv.sh); run that first, or pass "
            f"--refit-baseline to fit the 'none' arm here instead."
        )

    print(f"[{aggregation}/{label}] loading {len(arm_names)} arm(s) ...", flush=True)
    t0 = time.time()
    raw_dataset = load_arm(aggregation, "raw")
    datasets = {name: (raw_dataset if name == "raw" else load_arm(aggregation, name))
                for name in arm_names}
    print(f"[{aggregation}/{label}] loaded in {time.time() - t0:.1f}s "
          f"(raw {len(raw_dataset.data):,} records)", flush=True)

    fits = len(arm_names) * (len(STRATEGIES) - (0 if refit_baseline else 1)) * 20
    print(f"[{aggregation}/{label}] strategies={list(STRATEGIES)} "
          f"baseline={'refit' if refit_baseline else 'reused from stage F'} "
          f"~{fits} forest fits", flush=True)

    t0 = time.time()
    *results, diagnostics = evaluate_balance_impact_cv(
        raw_dataset=raw_dataset,
        datasets=datasets,
        target_label=label,
        strategies=STRATEGIES,
        baseline_npz_path=str(baseline_npz),
        refit_baseline=refit_baseline,
        return_diagnostics=True,
        oof_output_path=str(directory / f"{label}_balance_oof_scores_cv.npz"),
    )
    results = tuple(results)
    print(f"[{aggregation}/{label}] evaluated in {(time.time() - t0) / 60:.1f} min", flush=True)

    pickle_path = directory / f"{label}_balance_impact_cv.pkl"
    save_object(results, str(pickle_path))

    sidecar_path = directory / f"{label}_balance_impact_cv_diagnostics.json"
    sidecar_path.write_text(json.dumps(jsonable(diagnostics), indent=1, sort_keys=True))
    print(f"[{aggregation}/{label}] wrote {pickle_path.name} and {sidecar_path.name}", flush=True)

    # The comparison this stage exists to make. Accuracy alone cannot show it —
    # the unbalanced baseline wins on accuracy at 0.5 precisely by refusing to
    # predict the minority class — so recall and AUPRC are printed alongside.
    header = (f"    {'arm / strategy':34s} {'acc':>7s} {'f1':>7s} {'bal_acc':>8s} "
              f"{'recall':>7s} {'auroc':>7s} {'auprc':>7s} {'pos_rate':>9s} {'synth':>8s}")
    print(header, flush=True)
    for name, detail in diagnostics.items():
        flag = "  <-- DEGENERATE" if detail["degenerate"] else ""
        if detail["smote_fallback_folds"]:
            flag += f"  ({detail['smote_fallback_folds']} SMOTE fallback folds)"
        print(f"    {name:34s} {detail['accuracy_mean']:7.4f} {detail['f1_macro_mean']:7.4f} "
              f"{detail['balanced_accuracy_mean']:8.4f} {detail['recall_mean']:7.4f} "
              f"{detail['auroc_mean']:7.4f} {detail['auprc_mean']:7.4f} "
              f"{detail['predicted_positive_rate']:9.4f} "
              f"{detail['n_synthetic_total']:8,}{flag}", flush=True)

    print(f"[{aggregation}/{label}] baseline trained on "
          f"{diagnostics[list(diagnostics)[0]]['baseline_trained_on_fraction']:.2f} of the cohort "
          f"vs {1 - 1 / 5:.2f} for the balanced arms", flush=True)


if __name__ == "__main__":
    main()
