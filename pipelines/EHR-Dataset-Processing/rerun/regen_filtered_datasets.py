"""Stage K — rebuild one (arm, aggregation) filtered dataset after the vital-range fix.

The generalised form of regen_fill_missing.py (stage A), which is hardcoded to the
single 'fill missing data' arm. The 2026-08-30 fix to the seven vital ceilings (bug
register F-02) invalidates nine of the thirteen arms, so stage A's shape no longer
covers it. regen_fill_missing.py and job_a are left in place as the record of the
2026-08-05 rerun.

Which arms and why: see VITALS_DEPENDENT_ARMS in _common.py. The four omitted arms are
the control group — they must reproduce their pre-fix numbers exactly.

`create_filter_dataset` writes unconditionally (the cache check lives in
Experiments/apply_dataset_filter.py, not in the Manager), so this overwrites whatever
is on disk. It also writes the per-filter JSON change log under
Logs/<dataset>/<aggregation>/, which is the artifact the F-02 verification reads —
those logs did not survive the move into the consolidated toolbox, so this rerun is
the first time most of them exist.

    python rerun/regen_filtered_datasets.py "<aggregation method>" "<arm>"
    python rerun/regen_filtered_datasets.py            # (arm, agg) from SLURM_ARRAY_TASK_ID
"""
import os
import sys
import time

from _common import (  # noqa: F401
    DATASET_NAME, FILTERS, VITALS, AGGREGATIONS, VITALS_DEPENDENT_ARMS, arm_agg_from_task_id,
)
from Managers.dataset_manager import create_filter_dataset
from Managers.serialization_manager import load_data
from Managers.path_manager import get_project_root


def main() -> None:
    if len(sys.argv) > 2:
        aggregation, arm = sys.argv[1], sys.argv[2]
    else:
        arm, aggregation = arm_agg_from_task_id(int(os.environ["SLURM_ARRAY_TASK_ID"]))

    if aggregation not in AGGREGATIONS:
        raise SystemExit(f"unknown aggregation {aggregation!r}; expected one of {AGGREGATIONS}")
    if arm not in FILTERS:
        raise SystemExit(f"unknown arm {arm!r}; expected one of {list(FILTERS)}")
    if arm not in VITALS_DEPENDENT_ARMS:
        # Not a hard error — you may have a reason — but this rerun must not touch the
        # control arms, so make the deviation loud rather than silent.
        print(f"WARNING: {arm!r} does not depend on the vital ranges. Rebuilding it "
              f"destroys the control group for this rerun.", flush=True)

    root = get_project_root()
    print(f"[{aggregation}/{arm}] loading processed records ...", flush=True)
    t0 = time.time()
    records = load_data(str(root / "Data" / DATASET_NAME / "processed_record_ehr.pkl"))
    print(f"[{aggregation}/{arm}] {len(records):,} records in {time.time() - t0:.1f}s", flush=True)

    filter_function, pre_aggregate = FILTERS[arm]
    print(f"[{aggregation}/{arm}] ranges: "
          + ", ".join(f"{k}={v[0]}" for k, v in VITALS.items()), flush=True)
    print(f"[{aggregation}/{arm}] applying (pre_aggregate={pre_aggregate}) ...", flush=True)

    t0 = time.time()
    name, dataset, _ = create_filter_dataset(
        DATASET_NAME, records, aggregation, arm,
        filter_function, VITALS, pre_aggregate,
    )
    print(f"[{aggregation}/{arm}] wrote {name} ({len(dataset.data):,} records) "
          f"in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
