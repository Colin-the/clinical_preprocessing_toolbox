"""Step 0 of the vital-range rerun — how much does raising the seven upper bounds move?

`_remove_outliers` keeps a reading only when `lo <= v <= hi`, and every live VITALS
table sets `hi` one unit below the documented maximum (bug register F-02). Raising the
ceilings newly admits every reading in `(old_hi, new_hi]` — for oxygen saturation that
is 100%, the modal SpO2 in MIMIC.

This is the "before" measurement. It has to run before the fix lands, because the
per-vital filter logs from the original run were never carried into the consolidated
toolbox, so there is no other record of what the old bounds discarded.

Reports per vital:
  * total readings, and how many the old/new bounds each keep
  * `newly_kept` — readings in (old_hi, new_hi], the whole effect of the fix
  * `still_dropped_high` / `still_dropped_low` — genuine out-of-range readings
  * `guard_flips` — (record, vital) traces that gain their second in-range hour and so
    newly pass the `>= 2 known values` guard in fill_missing_data_filter, which is how
    the bound reaches an arm that does no outlier removal of its own. Aggregation-
    dependent, so it is computed for mean and median (the two that describe level; the
    three deviation methods collapse toward 0 and interact with the *lower* bound
    instead, which this fix does not touch).

    python rerun/measure_boundary_counts.py            # writes rerun/logs/boundary_counts.json
"""
import json
import time
from collections import defaultdict

import numpy as np

from _common import DATASET_NAME, EHR_ROOT, VITALS  # noqa: F401
from Managers.serialization_manager import load_data

# The bounds this rerun installs. Deliberately written out rather than imported, so
# this script keeps measuring the real before/after even after the fix lands in
# _common.VITALS and the four other tables.
OLD_RANGES = {
    'heart rate': (1, 599),
    'systolic blood pressure': (1, 399),
    'diastolic blood pressure': (1, 299),
    'mean blood pressure': (1, 299),
    'respiration rate': (1, 69),
    'temperature': (21, 49),
    'oxygen saturation': (1, 99),
}
NEW_RANGES = {
    'heart rate': (1, 600),
    'systolic blood pressure': (1, 400),
    'diastolic blood pressure': (1, 300),
    'mean blood pressure': (1, 300),
    'respiration rate': (1, 70),
    'temperature': (21, 50),
    'oxygen saturation': (1, 100),
}

GUARD_METHODS = {"mean": np.mean, "median": np.median}


def main() -> None:
    path = EHR_ROOT / "Data" / DATASET_NAME / "processed_record_ehr.pkl"
    print(f"loading {path} ...", flush=True)
    t0 = time.time()
    records = load_data(str(path))
    print(f"{len(records):,} records in {time.time() - t0:.1f}s", flush=True)

    columns = list(records[0].timeseries.columns)
    print(f"columns: {columns}", flush=True)

    stats = {c: defaultdict(int) for c in columns}
    # guard_flips[method][vital] — traces crossing the >= 2 known values threshold.
    guard = {m: {c: 0 for c in columns} for m in GUARD_METHODS}
    guard_totals = {m: {c: 0 for c in columns} for m in GUARD_METHODS}

    t0 = time.time()
    for n, record in enumerate(records):
        ts = record.timeseries
        for col in columns:
            lo_o, hi_o = OLD_RANGES[col]
            lo_n, hi_n = NEW_RANGES[col]
            s = stats[col]

            # Per-hour aggregates, kept so the guard can be evaluated afterwards.
            hourly = {m: [] for m in GUARD_METHODS}

            for cell in ts[col]:
                if cell is None:
                    continue
                values = [v for v in cell if v is not None]
                if not values:
                    continue
                for v in values:
                    s['total'] += 1
                    if v < lo_o:
                        s['still_dropped_low'] += 1
                    elif v <= hi_o:
                        s['kept_old'] += 1
                        if v == hi_o:
                            s['exactly_at_old_ceiling'] += 1
                    elif v <= hi_n:
                        s['newly_kept'] += 1
                        if v == hi_n:
                            s['exactly_at_new_ceiling'] += 1
                    else:
                        s['still_dropped_high'] += 1
                for m, func in GUARD_METHODS.items():
                    hourly[m].append(float(func(values)))

            # The guard counts *hours whose aggregate is in range*, not raw readings.
            for m in GUARD_METHODS:
                agg = hourly[m]
                known_old = sum(1 for a in agg if lo_o <= a <= hi_o)
                known_new = sum(1 for a in agg if lo_n <= a <= hi_n)
                # A flip only matters where it crosses the >= 2 threshold and there is
                # actually something to impute (fewer than 24 charted hours).
                if len(agg) < 24 and known_old < 2 <= known_new:
                    guard[m][col] += 1
                if len(agg) < 24:
                    guard_totals[m][col] += 1

        if (n + 1) % 5000 == 0:
            print(f"  {n + 1:,}/{len(records):,} ({time.time() - t0:.0f}s)", flush=True)

    out = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": str(path),
        "n_records": len(records),
        "old_ranges": {k: list(v) for k, v in OLD_RANGES.items()},
        "new_ranges": {k: list(v) for k, v in NEW_RANGES.items()},
        "per_vital": {c: dict(stats[c]) for c in columns},
        "guard_flips": {m: guard[m] for m in GUARD_METHODS},
        "guard_eligible_traces": {m: guard_totals[m] for m in GUARD_METHODS},
    }

    log_dir = EHR_ROOT / "rerun" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = log_dir / "boundary_counts.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)

    print()
    print(f"{'vital':28s} {'total':>12s} {'newly kept':>11s} {'at old hi':>10s} "
          f"{'drop hi':>9s} {'drop lo':>9s}")
    print("-" * 84)
    for col in columns:
        s = stats[col]
        print(f"{col:28s} {s['total']:>12,} {s['newly_kept']:>11,} "
              f"{s['exactly_at_old_ceiling']:>10,} {s['still_dropped_high']:>9,} "
              f"{s['still_dropped_low']:>9,}")
    print()
    for m in GUARD_METHODS:
        flips = {c: v for c, v in guard[m].items() if v}
        print(f"fill-missing guard flips ({m}): {flips or 'none'}")
    print(f"\nwrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
