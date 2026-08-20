"""Stage E — emit the admission_id vector for every arm of one aggregation.

`RecordEHR.admission_id` is dropped at `to_tensor()` (ehr_record.py:47), so a
cached `*_dataset_ehr.pkl` is an anonymous `list[(Tensor, Tensor)]` whose records
are identified only by list position. That makes it impossible to pair two arms
by patient, which is what both the k-fold rework and a correct McNemar need. This
recovers the ids from `processed_record_ehr.pkl` — the only surviving source —
and writes them alongside each cached dataset as

    Data/<dataset>/<aggregation>/<arm>_admission_ids.npy

an int64 vector in the same order as that arm's `DatasetEHR.data`.

Deliberately does NOT go through `create_filter_dataset`: that would rewrite the
cached `*_dataset_ehr.pkl` files, and the whole point of this stage is to leave
them untouched. The `pre_aggregate` branching below is copied from
`Managers/dataset_manager.create_filter_dataset:92-97` — if that changes, change
this too.

**The shortcut, and why it is safe.** Only three arms drop records, and all three
are post-aggregate, so the expensive `aggregate_filter` pass runs once rather than
thirteen times. Every other arm emits one output record per input record in input
order, so its id vector is just the raw one. That is an assumption, not a given,
so every arm is validated against its cached pickle on both length and the full
`[icu, mortality]` label vector before anything is written. A mismatch is a hard
failure: it means the cached tensors and the current filter code disagree, which
is worth stopping for rather than papering over.

    python regen_admission_ids.py "<aggregation method>"
"""
import os
import sys
import time

import numpy as np
import torch

from _common import (  # noqa: F401
    AGGREGATIONS, DATA_ROOT, DATASET_NAME, FILTERS, VITALS, agg_from_task_id,
)
from Managers.ehr_filter_manager import aggregate_filter
from Managers.serialization_manager import load_data

# The three arms that drop whole records. Verified against the filter bodies
# (ehr_filter_manager.py long_missing_segment_filter / long_gap_filter /
# high_invalid_data_filter all build a `kept_records` list) and against the
# cached diagnostics sidecars, which report 31,029 / 20,323 / 1,369 records for
# `mean` against the raw cohort's 46,032.
RECORD_DROPPING = ("long missing segment", "long gap", "high invalid data")


def arm_slug(arm: str) -> str:
    """Match the on-disk naming from dataset_manager (`.replace(' ', '_').lower()`)."""
    return arm.replace(" ", "_").lower()


def cached_dataset_path(aggregation: str, arm: str):
    if arm == "raw":
        return DATA_ROOT / aggregation / "raw_dataset_ehr.pkl"
    return DATA_ROOT / aggregation / f"{arm_slug(arm)}_filtered_dataset_ehr.pkl"


def cached_labels(path) -> np.ndarray:
    """The (n, 2) [icu, mortality] label matrix out of a cached dataset pickle.

    weights_only=False because these are tuples of tensors rather than a bare
    state dict; torch 2.12 defaults the flag to True and would refuse.
    """
    data = torch.load(path, map_location="cpu", weights_only=False)
    if not data:
        return np.zeros((0, 2), dtype=np.int64)
    return np.stack([entry[1].numpy().astype(np.int64) for entry in data])


def validate(arm: str, ids: np.ndarray, labels: np.ndarray, path) -> None:
    """Hard-fail unless the replayed ids line up with the cached tensors."""
    cached = cached_labels(path)

    if len(ids) != len(cached):
        raise SystemExit(
            f"[FAIL] {arm}: replayed {len(ids):,} records but the cached pickle "
            f"holds {len(cached):,}. The cache and the current filter code disagree."
        )
    if len(ids) and not np.array_equal(labels, cached):
        differing = int(np.sum(np.any(labels != cached, axis=1)))
        raise SystemExit(
            f"[FAIL] {arm}: label vectors differ on {differing:,} of {len(ids):,} "
            f"records. The replay is not in the same order as the cached pickle."
        )
    if len(np.unique(ids)) != len(ids):
        raise SystemExit(f"[FAIL] {arm}: admission ids are not unique.")


def main() -> None:
    if len(sys.argv) > 1:
        aggregation = sys.argv[1]
    else:
        aggregation = agg_from_task_id(int(os.environ["SLURM_ARRAY_TASK_ID"]))

    if aggregation not in AGGREGATIONS:
        raise SystemExit(f"unknown aggregation {aggregation!r}; expected one of {AGGREGATIONS}")

    out_dir = DATA_ROOT / aggregation
    if not out_dir.is_dir():
        raise SystemExit(f"no cached data directory at {out_dir}")

    print(f"[{aggregation}] loading processed records ...", flush=True)
    t0 = time.time()
    records = load_data(str(DATA_ROOT / "processed_record_ehr.pkl"))
    print(f"[{aggregation}] {len(records):,} records in {time.time() - t0:.1f}s", flush=True)

    raw_ids = np.array([record.admission_id for record in records], dtype=np.int64)
    raw_labels = np.array([[record.icu, record.mortality] for record in records], dtype=np.int64)

    # One aggregation pass, shared by the three record-dropping arms. They append
    # the record objects they keep without mutating them, so reusing the list is
    # safe -- asserted below rather than assumed.
    print(f"[{aggregation}] aggregating once for the record-dropping arms ...", flush=True)
    t0 = time.time()
    aggregated = aggregate_filter(records, aggregation)
    print(f"[{aggregation}] aggregated in {time.time() - t0:.1f}s", flush=True)

    written = {}

    for arm in ["raw", *FILTERS.keys()]:
        path = cached_dataset_path(aggregation, arm)
        if not path.exists():
            print(f"[{aggregation}] {arm}: no cached pickle, skipping", flush=True)
            continue

        t0 = time.time()
        if arm in RECORD_DROPPING:
            filter_function, pre_aggregate = FILTERS[arm]
            if pre_aggregate:
                raise SystemExit(
                    f"[FAIL] {arm} is marked pre_aggregate but is in RECORD_DROPPING; "
                    "the one-pass shortcut in this script assumes otherwise."
                )
            before = len(aggregated)
            kept, _ = filter_function(aggregated, VITALS)
            if len(aggregated) != before:
                raise SystemExit(f"[FAIL] {arm} mutated the shared aggregated list.")
            ids = np.array([record.admission_id for record in kept], dtype=np.int64)
            labels = np.array([[r.icu, r.mortality] for r in kept], dtype=np.int64).reshape(-1, 2)
        else:
            # One output per input, in input order -- so the raw id vector applies
            # verbatim. validate() is what actually holds this claim up.
            ids, labels = raw_ids, raw_labels

        validate(arm, ids, labels, path)

        out_path = out_dir / f"{arm_slug(arm)}_admission_ids.npy"
        np.save(out_path, ids)
        written[arm] = len(ids)
        print(f"[{aggregation}] {arm}: {len(ids):,} ids -> {out_path.name} "
              f"({time.time() - t0:.1f}s)", flush=True)

    print(f"\n[{aggregation}] wrote {len(written)} id vectors, all validated "
          f"against their cached pickles.", flush=True)


if __name__ == "__main__":
    main()
