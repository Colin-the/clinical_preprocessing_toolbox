"""Stage A — rebuild the 'fill missing data' filtered dataset for one aggregation.

This is the only cached filter dataset the bugfixes changed. The known_indices
fix in fill_missing_data_filter compares readings against the vital's value range
instead of comparing array positions against it, which moves the >= 2 known
values guard for a large fraction of records — measured at ~11% of
(record, vital) decisions overall, and ~70% for temperature, whose old behaviour
only ever counted hours 21-23.

The other eleven arms (seven outlier filters, three structural, all vitals) are
untouched by the fixes and are deliberately not rebuilt.

    python regen_fill_missing.py "<aggregation method>"
"""
import sys
import time

from _common import DATASET_NAME, FILTERS, VITALS, AGGREGATIONS, agg_from_task_id  # noqa: F401
from Managers.dataset_manager import create_filter_dataset
from Managers.serialization_manager import load_data
from Managers.path_manager import get_project_root

FILTER_NAME = "fill missing data"


def main() -> None:
    if len(sys.argv) > 1:
        aggregation = sys.argv[1]
    else:
        import os
        aggregation = agg_from_task_id(int(os.environ["SLURM_ARRAY_TASK_ID"]))

    if aggregation not in AGGREGATIONS:
        raise SystemExit(f"unknown aggregation {aggregation!r}; expected one of {AGGREGATIONS}")

    root = get_project_root()
    print(f"[{aggregation}] loading processed records ...", flush=True)
    t0 = time.time()
    records = load_data(str(root / "Data" / DATASET_NAME / "processed_record_ehr.pkl"))
    print(f"[{aggregation}] {len(records):,} records in {time.time() - t0:.1f}s", flush=True)

    filter_function, pre_aggregate = FILTERS[FILTER_NAME]
    print(f"[{aggregation}] applying '{FILTER_NAME}' (pre_aggregate={pre_aggregate}) ...", flush=True)
    t0 = time.time()
    name, dataset, _ = create_filter_dataset(
        DATASET_NAME, records, aggregation, FILTER_NAME,
        filter_function, VITALS, pre_aggregate,
    )
    print(f"[{aggregation}] wrote {name} ({len(dataset.data):,} records) "
          f"in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
