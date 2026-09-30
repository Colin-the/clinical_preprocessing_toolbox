"""Stage I — verification for the class-balanced sweep (stage H).

    python rerun/verify_balance.py                    # structural checks only
    python rerun/verify_balance.py --with-model       # adds the leakage probe (slow)
    python rerun/verify_balance.py --aggregation median --label icu

The structural checks replay every fold's resampling against the real cohort and
the real partition, without fitting anything, and assert that no held-out record
and no generated point can reach evaluation. `--with-model` additionally trains
forests on shuffled labels, once per strategy — the one test that would actually
catch a leak rather than a bookkeeping error, because a synthetic point that had
found its way into a test fold would push the shuffled-label AUC above chance.

Note `DEPRECATED.md`: a green log from a verifier is weak evidence on its own.
This one is deliberately narrow — it checks that balancing cannot contaminate the
held-out fold. It says nothing about whether balancing helped.
"""
import argparse
import json
import sys

import numpy as np

from _common import DATA_ROOT, FILTERS, LABELS  # noqa: F401
from Entities.ehr_dataset import DatasetEHR
from Managers import balancing_manager
from Managers.balancing_manager import (
    STRATEGIES, assert_no_leakage, balance_training_fold,
)
from Managers.evaluation_manager import (
    _flatten_whole_dataset, evaluate_dataset_label_cv_balanced,
)
from Managers.partition_manager import N_SPLITS, build_fold_assignment, project_to_arm
from regen_filter_impact_cv import load_arm

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  {status}  {name}{' — ' + detail if detail else ''}", flush=True)
    if not condition:
        FAILURES.append(name)
    return condition


def section(title: str) -> None:
    print(f"\n── {title} " + "─" * max(0, 66 - len(title)), flush=True)


def row_set(matrix: np.ndarray) -> set:
    """Rows as hashable bytes, for exact set membership.

    Comparing every synthetic row against every test row pairwise would be
    O(n_synth x n_test x 168). Hashing the raw bytes makes it a set intersection
    instead, which is what lets this run on the full cohort rather than a sample.
    """
    return set(map(bytes, np.ascontiguousarray(matrix)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aggregation", default="mean")
    parser.add_argument("--label", default="mortality", choices=LABELS)
    parser.add_argument("--arm", default="raw")
    parser.add_argument("--with-model", action="store_true")
    parser.add_argument("--probe-size", type=int, default=8000)
    args = parser.parse_args()

    aggregation, label, arm = args.aggregation, args.label, args.arm
    print(f"verify_balance: {aggregation} / {label} / {arm}", flush=True)

    # ── 1. Balancing primitives ──────────────────────────────────────────────
    section("1. balancing primitives")
    check("balancing_manager self-check", balancing_manager.self_check())

    # ── 2. Real cohort, real partition ───────────────────────────────────────
    section("2. per-fold resampling against the real cohort")
    raw_dataset = load_arm(aggregation, "raw")
    dataset = raw_dataset if arm == "raw" else load_arm(aggregation, arm)
    label_index = dataset.label_index_map[label]

    raw_ids = np.asarray(raw_dataset.admission_ids, dtype=np.int64)
    _, raw_labels = _flatten_whole_dataset(raw_dataset, label_index)
    assignment = build_fold_assignment(raw_ids, raw_labels)

    arm_ids = np.asarray(dataset.admission_ids, dtype=np.int64)
    arm_assignment = project_to_arm(arm_ids, raw_ids, assignment)
    features, labels = _flatten_whole_dataset(dataset, label_index)
    features = np.asarray(features)

    print(f"  {arm}: {len(arm_ids):,} records, prevalence {labels.mean():.4f}", flush=True)

    for strategy in STRATEGIES:
        if strategy == "none":
            continue

        leak_free = True
        balanced_ok = True
        synthetic_in_test = 0
        mask_ok = True
        totals = {"real": 0, "synthetic": 0}

        for repeat in range(arm_assignment.shape[0]):
            for fold in range(N_SPLITS):
                test_positions = np.where(arm_assignment[repeat] == fold)[0]
                train_positions = np.where(arm_assignment[repeat] != fold)[0]
                if test_positions.size == 0 or train_positions.size == 0:
                    continue
                if len(np.unique(labels[train_positions])) < 2:
                    continue

                result = balance_training_fold(
                    strategy, features, labels, train_positions, repeat, fold
                )

                try:
                    assert_no_leakage(result, train_positions, test_positions)
                except RuntimeError as error:
                    leak_free = False
                    print(f"    r{repeat}f{fold}: {error}", flush=True)

                counts = result.stats["class_counts_out"]
                if len(set(counts.values())) != 1:
                    balanced_ok = False

                # The direct question, asked of the values rather than the
                # indices: does any row the model trained on appear verbatim in
                # the held-out fold?
                synthetic = result.x[result.provenance == -1]
                if synthetic.size:
                    overlap = row_set(synthetic) & row_set(features[test_positions])
                    synthetic_in_test += len(overlap)

                    base = result.parents[:, 0]
                    if not np.array_equal(synthetic != 0, features[base] != 0):
                        mask_ok = False

                totals["real"] += int(result.stats["n_real"])
                totals["synthetic"] += int(result.stats["n_synthetic"])

        check(f"{strategy}: no held-out record in any training fold", leak_free)
        check(f"{strategy}: every fold reaches a 1:1 class ratio", balanced_ok)
        check(f"{strategy}: no synthetic row appears in a test fold",
              synthetic_in_test == 0, f"{synthetic_in_test} collisions")
        if strategy == "smote":
            check("smote: every synthetic row keeps its base parent's missingness mask", mask_ok)
        print(f"    {strategy}: {totals['real']:,} real rows, "
              f"{totals['synthetic']:,} synthetic across all folds", flush=True)

    # ── 3. Leakage probe ─────────────────────────────────────────────────────
    if args.with_model:
        section("3. leakage probe (shuffled labels, per strategy)")
        import torch
        from sklearn.metrics import roc_auc_score

        rng = np.random.default_rng(12345)
        size = min(args.probe_size, len(arm_ids))
        pick = np.sort(rng.choice(len(arm_ids), size=size, replace=False))

        shuffled = labels[pick].copy()
        rng.shuffle(shuffled)
        probe_ids = arm_ids[pick]
        probe_assignment = build_fold_assignment(probe_ids, shuffled, n_repeats=2)

        probe = DatasetEHR()
        probe.create([
            (dataset.data[i][0], torch.tensor(
                [shuffled[k] if j == label_index else dataset.data[i][1][j].item()
                 for j in range(2)], dtype=torch.long))
            for k, i in enumerate(pick)
        ])
        probe.admission_ids = probe_ids

        for strategy in STRATEGIES:
            if strategy == "none":
                continue
            result = evaluate_dataset_label_cv_balanced(
                probe, probe_ids, label_index, probe_assignment, strategy
            )
            covered = ~np.isnan(result['consensus_scores'])
            auc = roc_auc_score(result['y'][covered], result['consensus_scores'][covered])
            # Balancing changes what the forest is fitted on, so a leak would
            # show up here as skill on labels that carry none.
            check(f"{strategy}: shuffled-label AUC collapses to chance",
                  abs(auc - 0.5) < 0.05, f"auc={auc:.4f}")
    else:
        section("3. leakage probe — skipped (pass --with-model)")

    # ── 4. Stage H artifacts, if they exist ──────────────────────────────────
    section("4. stage H artifacts")
    sidecar = DATA_ROOT / aggregation / f"{label}_balance_impact_cv_diagnostics.json"
    if not sidecar.exists():
        print(f"  SKIP  {sidecar.name} not written yet", flush=True)
    else:
        diagnostics = json.loads(sidecar.read_text())
        fingerprints = {d['partition_fingerprint'] for d in diagnostics.values()}
        check("all arms share one partition fingerprint", len(fingerprints) == 1,
              str(fingerprints))
        check("every strategy present",
              {d['strategy'] for d in diagnostics.values()} == set(STRATEGIES))
        check("every arm scored at 0.5",
              all(d['threshold'] == 0.5 for d in diagnostics.values()))
        check("only smote created synthetic rows",
              all(d['n_synthetic_total'] == 0 for d in diagnostics.values()
                  if d['strategy'] != 'smote'))

        reused = [n for n, d in diagnostics.items() if d.get('reused_from_cache')]
        if reused:
            fraction = diagnostics[reused[0]]['baseline_trained_on_fraction']
            print(f"  NOTE  baseline reused from stage F and trained on "
                  f"{fraction:.2f} of the cohort against 0.80 for the balanced "
                  f"arms; rerun with --refit-baseline to remove the confound",
                  flush=True)

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): " + ", ".join(FAILURES), flush=True)
        return 1
    print("OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
