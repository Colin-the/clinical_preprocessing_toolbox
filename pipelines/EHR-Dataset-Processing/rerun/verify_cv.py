"""Self-check for the cross-validated evaluation path.

Follows the repo's existing verification idiom — a standalone script that prints
PASS/FAIL lines and exits nonzero — rather than pytest, which this tree has no
setup for anywhere. Same shape as hour_scaling_experiment/v2/splits.py:105.

    python rerun/verify_cv.py                    # structural checks, ~1 min
    python rerun/verify_cv.py --with-model       # adds the leakage probe (slow)
    python rerun/verify_cv.py --aggregation median

The structural checks need only stage E's id sidecars and the cached dataset
pickles. `--with-model` additionally trains forests on a subsample with shuffled
labels, which is the one test that would actually catch a threshold or fold leak
— everything else can only catch bookkeeping errors.
"""
import argparse
import json
import sys

import numpy as np

from _common import DATA_ROOT, FILTERS, LABELS  # noqa: F401
from Entities.ehr_dataset import DatasetEHR
from Managers import partition_manager
from Managers.evaluation_manager import (
    calculate_mcnemar_paired, evaluate_dataset_label_cv, _flatten_whole_dataset,
)
from Managers.partition_manager import build_fold_assignment, project_to_arm

# From the cached diagnostics sidecars — the three arms that drop records, and
# what they should drop to. A change here means a filter's behaviour moved.
EXPECTED_COUNTS = {
    'raw': 46032,
    'long missing segment': 31029,
    'long gap': 20323,
    'high invalid data': 1369,
}

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  {status}  {name}{' — ' + detail if detail else ''}", flush=True)
    if not condition:
        FAILURES.append(name)
    return condition


def arm_slug(arm: str) -> str:
    return arm.replace(" ", "_").lower()


def load_arm(aggregation: str, arm: str) -> DatasetEHR:
    directory = DATA_ROOT / aggregation
    path = (directory / "raw_dataset_ehr.pkl" if arm == "raw"
            else directory / f"{arm_slug(arm)}_filtered_dataset_ehr.pkl")
    dataset = DatasetEHR()
    dataset.load(str(path))
    dataset.load_admission_ids(str(directory / f"{arm_slug(arm)}_admission_ids.npy"))
    return dataset


def section(title: str) -> None:
    print(f"\n{title}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aggregation", default="mean")
    parser.add_argument("--label", default="mortality", choices=LABELS)
    parser.add_argument("--with-model", action="store_true")
    parser.add_argument("--probe-size", type=int, default=8000)
    args = parser.parse_args()

    aggregation, label = args.aggregation, args.label
    print(f"verify_cv — aggregation={aggregation!r} label={label!r}")

    # ── 1. Partition primitives ──────────────────────────────────────────────
    section("1. partition primitives")
    check("partition_manager self-check", partition_manager.self_check())

    # ── 2. Record identity ───────────────────────────────────────────────────
    section("2. record identity")
    arms = ['raw', *FILTERS]
    datasets, ids = {}, {}
    for arm in arms:
        try:
            datasets[arm] = load_arm(aggregation, arm)
            ids[arm] = np.asarray(datasets[arm].admission_ids, dtype=np.int64)
        except FileNotFoundError as error:
            check(f"{arm}: sidecar present", False, str(error).split('\n')[0])
            return 1

    raw_ids = ids['raw']
    check("raw ids are unique", len(np.unique(raw_ids)) == len(raw_ids), f"{len(raw_ids):,}")

    for arm, expected in EXPECTED_COUNTS.items():
        if arm in ids:
            check(f"{arm}: record count", len(ids[arm]) == expected,
                  f"{len(ids[arm]):,} vs expected {expected:,}")

    raw_position = {int(i): p for p, i in enumerate(raw_ids)}
    for arm in arms:
        arm_ids = ids[arm]
        subset_ok = all(int(i) in raw_position for i in arm_ids)
        positions = [raw_position[int(i)] for i in arm_ids] if subset_ok else []
        ordered = subset_ok and positions == sorted(positions)
        check(f"{arm}: ids are an ordered subsequence of raw", ordered,
              f"n={len(arm_ids):,}")

    for arm in arms:
        check(f"{arm}: id count matches tensor count",
              len(ids[arm]) == len(datasets[arm].data))

    # ── 3. Fold inheritance ──────────────────────────────────────────────────
    section("3. fold inheritance")
    _, raw_labels = _flatten_whole_dataset(datasets['raw'], datasets['raw'].label_index_map[label])
    assignment = build_fold_assignment(raw_ids, raw_labels)

    for arm in arms:
        projected = project_to_arm(ids[arm], raw_ids, assignment)
        expected_shape = (assignment.shape[0], len(ids[arm]))
        if not check(f"{arm}: projected shape", projected.shape == expected_shape,
                     str(projected.shape)):
            continue
        # Every record must keep the fold the raw cohort gave it.
        positions = np.array([raw_position[int(i)] for i in ids[arm]])
        check(f"{arm}: inherits raw's folds exactly",
              np.array_equal(projected, assignment[:, positions]))

    # ── 4. Out-of-fold coverage and pairing ──────────────────────────────────
    section("4. out-of-fold coverage and pairing (raw arm, real fit)")
    label_index = datasets['raw'].label_index_map[label]
    raw_result = evaluate_dataset_label_cv(datasets['raw'], raw_ids, label_index, assignment)

    coverage = raw_result['diagnostics']['coverage']
    check("every raw record covered out-of-fold", coverage == 1.0, f"coverage={coverage:.4f}")
    check("one prediction per record per repeat",
          bool(np.all(raw_result['oof_predictions'] >= 0)))
    check("folds fitted", raw_result['diagnostics']['n_folds_fitted']
          == partition_manager.N_REPEATS * partition_manager.N_SPLITS,
          str(raw_result['diagnostics']['n_folds_fitted']))

    labels_by_id = {int(i): int(y) for i, y in zip(raw_ids, raw_labels)}
    statistic, p_value, detail = calculate_mcnemar_paired(
        raw_result['consensus_predictions'], raw_ids,
        raw_result['consensus_predictions'], raw_ids, labels_by_id,
    )
    check("raw vs raw: no discordance", detail['n01'] == 0 and detail['n10'] == 0,
          f"n01={detail['n01']} n10={detail['n10']}")
    check("raw vs raw: p = 1", p_value == 1.0, f"p={p_value}")
    check("raw vs raw: pairs the whole cohort", detail['n_paired'] == len(raw_ids),
          f"{detail['n_paired']:,}")

    # The regression test for the McNemar bug: a shrunken arm must pair on its
    # own size, not silently truncate to it.
    shrunk = 'high invalid data'
    if shrunk in ids:
        shrunk_result = evaluate_dataset_label_cv(
            datasets[shrunk], ids[shrunk], label_index,
            project_to_arm(ids[shrunk], raw_ids, assignment),
        )
        _, _, shrunk_detail = calculate_mcnemar_paired(
            raw_result['consensus_predictions'], raw_ids,
            shrunk_result['consensus_predictions'], ids[shrunk], labels_by_id,
        )
        expected_pairs = int(np.sum(shrunk_result['consensus_predictions'] >= 0))
        check(f"{shrunk}: pairs on the intersection, not by truncation",
              shrunk_detail['n_paired'] == expected_pairs,
              f"n_paired={shrunk_detail['n_paired']:,} of {len(ids[shrunk]):,} held")

    # ── 4b. Degenerate arm ───────────────────────────────────────────────────
    # `high invalid data` keeps zero records under the three deviation
    # aggregations. A special-cased return for that shipped a diagnostics dict
    # with a different key set than the normal path, which the caller indexed
    # into and died on — six of ten stage-F tasks. Checked here on a synthetic
    # empty arm so it is caught regardless of which aggregation is being run.
    section("4b. degenerate (zero-record) arm")
    empty = DatasetEHR()
    empty.create([])
    degenerate = evaluate_dataset_label_cv(
        empty, np.array([], dtype=np.int64), label_index,
        np.zeros((partition_manager.N_REPEATS, 0), dtype=np.int8),
    )
    check("empty arm returns the same top-level keys",
          set(degenerate) == set(raw_result))
    missing = set(raw_result['diagnostics']) - set(degenerate['diagnostics'])
    check("empty arm returns the same diagnostics keys", not missing,
          f"missing {sorted(missing)}" if missing else "")
    check("empty arm is flagged degenerate", degenerate['diagnostics']['degenerate'])

    _, _, empty_detail = calculate_mcnemar_paired(
        raw_result['consensus_predictions'], raw_ids,
        degenerate['consensus_predictions'], degenerate['admission_ids'], labels_by_id,
    )
    check("empty arm pairs zero records, flagged rather than silently zero-tabled",
          empty_detail['n_paired'] == 0 and empty_detail['degenerate'])

    # ── 5. Leakage probe ─────────────────────────────────────────────────────
    if args.with_model:
        section("5. leakage probe (shuffled labels)")
        rng = np.random.default_rng(12345)
        size = min(args.probe_size, len(raw_ids))
        pick = np.sort(rng.choice(len(raw_ids), size=size, replace=False))

        probe = DatasetEHR()
        probe.create([datasets['raw'].data[i] for i in pick])
        probe_ids = raw_ids[pick]

        shuffled = raw_labels[pick].copy()
        rng.shuffle(shuffled)
        probe_assignment = build_fold_assignment(probe_ids, shuffled, n_repeats=2)

        # Swap the shuffled labels into the tensors so the model actually trains
        # on noise; the label lives at position `label_index` of entry[1].
        import torch
        probe.data = [
            (entry[0], torch.tensor(
                [shuffled[i] if j == label_index else entry[1][j].item() for j in range(2)],
                dtype=torch.long))
            for i, entry in enumerate(probe.data)
        ]

        result = evaluate_dataset_label_cv(probe, probe_ids, label_index, probe_assignment)
        covered = ~np.isnan(result['consensus_scores'])
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(result['y'][covered], result['consensus_scores'][covered])
        check("shuffled-label AUC collapses to chance", abs(auc - 0.5) < 0.05, f"auc={auc:.4f}")
    else:
        section("5. leakage probe — skipped (pass --with-model)")

    # ── 6. Produced artifacts, if stage F has run ────────────────────────────
    section("6. stage F artifacts")
    sidecar = DATA_ROOT / aggregation / f"{label}_filter_impact_cv_diagnostics.json"
    if not sidecar.exists():
        print(f"  SKIP  {sidecar.name} not written yet", flush=True)
    else:
        diagnostics = json.loads(sidecar.read_text())
        check("every arm present", set(diagnostics) == set(arms),
              f"{len(diagnostics)} arms")
        fingerprints = {d['partition_fingerprint'] for d in diagnostics.values()}
        check("all arms share one partition fingerprint", len(fingerprints) == 1,
              str(fingerprints))
        for arm in arms:
            detail = diagnostics[arm]['mcnemar']
            if arm == 'raw':
                continue
            check(f"{arm}: n_paired <= arm size",
                  detail['n_paired'] <= diagnostics[arm]['n_records'],
                  f"{detail['n_paired']:,} of {diagnostics[arm]['n_records']:,}")

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): " + "; ".join(FAILURES))
        return 1
    print("OK — all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
