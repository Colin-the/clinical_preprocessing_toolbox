"""Unit check for the 2026-08-30 vital-range fix (bug register F-02).

Asserts each per-vital filter now KEEPS its documented ceiling and still REJECTS
one unit above it, and that the `fill missing data` guard counts an all-ceiling
trace as known. Runs in seconds on a login node — no cluster job needed.

    python rerun/test_vital_bounds.py
"""
import numpy as np
import pandas as pd

from _common import VITALS, FILTERS
from Entities.ehr_record import RecordEHR
from Managers.ehr_filter_manager import aggregate_filter

COLUMNS = list(VITALS.keys())
FAILURES = []


def check(condition, message):
    print(f"  {'PASS' if condition else 'FAIL'}  {message}")
    if not condition:
        FAILURES.append(message)


def make_record(column, values):
    """A 24x7 record where `column` carries `values` every hour and the rest are empty."""
    data = {c: [list(values) if c == column else [] for _ in range(24)] for c in COLUMNS}
    return RecordEHR(admission_id=1, timeseries=pd.DataFrame(data, index=range(24)),
                     icu=0, mortality=0)


print("1. every filter keeps its own ceiling and rejects one above\n")
for column in COLUMNS:
    lo, hi = VITALS[column][0]
    filter_function, _ = FILTERS[column]

    kept, _ = filter_function([make_record(column, [float(hi)])], VITALS)
    survived = kept[0].timeseries[column].iloc[0]
    check(list(survived) == [float(hi)],
          f"{column:28s} keeps {hi} (got {list(survived)})")

    kept, _ = filter_function([make_record(column, [float(hi) + 1])], VITALS)
    survived = kept[0].timeseries[column].iloc[0]
    check(list(survived) == [],
          f"{column:28s} rejects {hi + 1} (got {list(survived)})")

    kept, _ = filter_function([make_record(column, [float(lo) - 1])], VITALS)
    survived = kept[0].timeseries[column].iloc[0]
    check(list(survived) == [],
          f"{column:28s} rejects {lo - 1} (got {list(survived)})")

print("\n2. the regression that started this: an all-100% SpO2 trace\n")
record = make_record('oxygen saturation', [100.0, 100.0])
kept, changes = FILTERS['oxygen saturation'][0]([record], VITALS)
n_kept = sum(len(c) for c in kept[0].timeseries['oxygen saturation'])
check(n_kept == 48, f"all 48 SpO2 readings of 100% survive (got {n_kept})")
check(sum(c.value_level for c in changes) == 0,
      f"nothing charged to value_level (got {sum(c.value_level for c in changes)})")

print("\n3. the fill-missing guard now counts an all-ceiling trace as known\n")
# Ten charted hours at 100%, fourteen empty — previously zero "known" values, so
# the >= 2 guard skipped the trace entirely and it was never imputed.
data = {c: [] for c in COLUMNS}
for c in COLUMNS:
    data[c] = [[100.0] if (c == 'oxygen saturation' and h < 10) else [] for h in range(24)]
sparse = RecordEHR(1, pd.DataFrame(data, index=range(24)), 0, 0)
aggregated = aggregate_filter([sparse], "mean")
before = aggregated[0].timeseries['oxygen saturation'].isna().sum()
filled, _ = FILTERS['fill missing data'][0](aggregated, VITALS)
after = filled[0].timeseries['oxygen saturation'].isna().sum()
check(before == 14 and after == 0,
      f"14 missing SpO2 hours imputed (before={before}, after={after})")
check(np.isclose(filled[0].timeseries['oxygen saturation'].iloc[20], 100.0),
      f"imputed value is 100.0 (got {filled[0].timeseries['oxygen saturation'].iloc[20]})")

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("all checks passed")
