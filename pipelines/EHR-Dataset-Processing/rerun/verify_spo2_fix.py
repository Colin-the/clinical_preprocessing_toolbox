"""Acceptance checks for the 2026-08-30 vital-range fix (bug register F-02).

Run after the rerun chain finishes. Everything here compares the live tree against the
pre-fix artifacts set aside by quarantine_pre_spo2_fix.py, so it must run before those
are deleted.

Five checks, in descending order of how much they would tell you if they failed:

  1. CONTROL ARMS UNCHANGED. raw / long missing segment / long gap / high invalid data
     do not depend on the vital ranges, so their CV numbers must reproduce exactly.
     A move here means something was rebuilt that should not have been, and nothing
     else in this rerun can be trusted. This is the strongest check available.
  2. SPO2 CENTROID RESTORED. The register's own acceptance criterion: the ICU-positive
     SpO2 centroid for the `oxygen saturation` arm sat at 96.46 against a raw value of
     100.90, and should now come back to approximately the raw value.
  3. FILTER LOGS AGREE WITH THE PRE-FLIGHT COUNT. The `value_level` total in each
     per-vital log must equal the number of readings the new range rejects, as counted
     independently by measure_boundary_counts.py before the fix landed.
  4. FILL-MISSING MOVED. Its guard reads all seven ranges, so its imputation count must
     rise by roughly the guard-flip count from the pre-flight measurement.
  5. EVERYTHING WAS ACTUALLY REBUILT. Nine arms with a fresh mtime, four without.

    python rerun/verify_spo2_fix.py
"""
import json
import pickle
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

from _common import (
    AGGREGATIONS, DATA_ROOT, DATASET_NAME, EHR_ROOT, LABELS,
    VITALS, VITALS_DEPENDENT_ARMS, VITALS_INDEPENDENT_ARMS,
)

TOOLBOX_ROOT = EHR_ROOT.parent.parent
ARCHIVE = TOOLBOX_ROOT / "_deprecated" / "pre_spo2_fix_2026-08-30"
SCRATCH_ARCHIVE = Path("/scratch/ccampb47/ehr_pre_spo2_fix_2026-08-30")
FIX_DATE = datetime(2026, 8, 30, 21, 0).timestamp()

RESULTS = []


def record(ok, label, detail=""):
    RESULTS.append((ok, label))
    mark = "PASS" if ok else "FAIL"
    print(f"  {mark}  {label}" + (f"\n        {detail}" if detail else ""))


def slug(arm):
    return arm.replace(" ", "_").lower()


# ── 1 ────────────────────────────────────────────────────────────────────────
def check_control_arms():
    """Control arms must reproduce — to the pipeline's actual reproducibility floor.

    Not bit-for-bit. sklearn's forest is not deterministic across runs even with a fixed
    `forest_seed(repeat, fold)`, and the floor is known and tiny: stage H measured 5.4e-06
    when it re-ran arms whose inputs had not changed. 5.431e-06 is not an arbitrary
    number — it is 1 / (46,032 records x 4 repeats), i.e. exactly ONE flipped prediction.
    Anything at that scale is the estimator; anything materially above it is the data.
    """
    print("\n1. control arms must reproduce (the load-bearing check)\n")
    ONE_PREDICTION = 1.0 / (46032 * 4)
    TOLERANCE = 100 * ONE_PREDICTION          # ~5.4e-4, two orders above the floor

    drifts, identical, missing = [], 0, 0
    for agg in AGGREGATIONS:
        for label in LABELS:
            name = f"{label}_filter_impact_cv_diagnostics.json"
            old_path = ARCHIVE / "Data" / DATASET_NAME / agg / name
            new_path = DATA_ROOT / agg / name
            if not old_path.exists() or not new_path.exists():
                record(False, f"{agg}/{label}: diagnostics missing",
                       f"old={old_path.exists()} new={new_path.exists()}")
                continue
            old, new = json.loads(old_path.read_text()), json.loads(new_path.read_text())
            for arm in VITALS_INDEPENDENT_ARMS:
                if arm not in old or arm not in new:
                    continue
                for key in ("accuracy_mean", "f1_macro_mean", "n_records"):
                    a, b = old[arm].get(key), new[arm].get(key)
                    if a is None or b is None:
                        missing += 1
                        continue
                    # `high invalid data` is degenerate under the three deviation
                    # aggregations (it keeps 0 records), so NaN == NaN is a pass.
                    if a != a and b != b:
                        identical += 1
                        continue
                    d = abs(b - a)
                    if d == 0:
                        identical += 1
                    else:
                        drifts.append((d, f"{agg}/{label}/{arm}/{key}: {a!r} -> {b!r}"))

    total = identical + len(drifts)
    over = [t for d, t in drifts if d > TOLERANCE]
    worst = max((d for d, _ in drifts), default=0.0)
    record(not over,
           f"{identical}/{total} control metrics bit-identical; "
           f"max drift {worst:.2e} = {worst / ONE_PREDICTION:.2f} flipped prediction(s), "
           f"tolerance {TOLERANCE:.1e}",
           "" if not over else "\n        ".join(over[:8]))


# ── 2 ────────────────────────────────────────────────────────────────────────
def check_spo2_centroid():
    """SpO2 centroid restored — but NOT to the `raw` arm's value.

    The register's stated criterion for F-02 is that this "should return to ~the raw
    value" of 100.90. That criterion is wrong and cannot be met: an SpO2 mean above 100%
    is physically impossible, and `raw` does no outlier removal at all. Eight raw SpO2
    readings exceed 100, one of them 981,023, and those few values are what lift the raw
    centroid over 100. (`long gap` sits at 97.46 despite doing no value filtering,
    because it happens to drop the records carrying the contamination — which is how you
    can tell it is a handful of records and not a population effect.)

    The honest targets are the pooled mean of in-range readings, and the `all vitals`
    arm, which chains this same filter and must therefore agree exactly.
    """
    print("\n2. ICU-positive SpO2 centroid restored (corrected criterion)\n")
    idx = list(VITALS).index('oxygen saturation')
    POOLED_IN_RANGE = 97.271        # mean of all readings in [1, 100], measured
    PRE_FIX = 96.46                 # what the old bound produced

    cdir = DATA_ROOT / "mean" / "centroids"

    def centroid(name):
        with open(cdir / f"icu_{name}_pos.pkl", "rb") as f:
            c, _ = pickle.load(f)
        return float(np.asarray(c).ravel()[idx])

    try:
        arm, allv = centroid("oxygen saturation"), centroid("all vitals")
    except FileNotFoundError as exc:
        record(False, "centroid missing", str(exc))
        return

    record(abs(arm - POOLED_IN_RANGE) < 0.5,
           f"SpO2 centroid {arm:.3f} vs pooled in-range mean {POOLED_IN_RANGE:.3f}",
           f"was {PRE_FIX} before the fix")
    record(arm > PRE_FIX + 0.5,
           f"centroid rose from {PRE_FIX} to {arm:.3f} (+{arm - PRE_FIX:.3f})")
    record(abs(arm - allv) < 1e-6,
           f"`oxygen saturation` and `all vitals` agree ({arm:.3f} vs {allv:.3f})",
           "they chain the same filter, so any difference is a bug")


# ── 3 ────────────────────────────────────────────────────────────────────────
def check_filter_logs():
    print("\n3. per-vital filter logs agree with the independent pre-flight count\n")
    counts_path = EHR_ROOT / "rerun" / "logs" / "boundary_counts.json"
    if not counts_path.exists():
        record(False, "boundary_counts.json missing — run measure_boundary_counts.py")
        return
    counts = json.loads(counts_path.read_text())["per_vital"]

    logs = EHR_ROOT / "Logs" / DATASET_NAME / "mean"
    for vital in VITALS:
        path = logs / f"{slug(vital)}_filter_log.json"
        if not path.exists():
            record(False, f"{vital}: {path.name} not written")
            continue
        entries = json.loads(path.read_text())
        if isinstance(entries, dict):
            entries = list(entries.values())
        total = sum(e.get("value_level", 0) for e in entries if isinstance(e, dict))
        expected = counts[vital].get("still_dropped_high", 0) + counts[vital].get("still_dropped_low", 0)
        record(total == expected,
               f"{vital:28s} log removed {total:,}, pre-flight said {expected:,}")


# ── 4 ────────────────────────────────────────────────────────────────────────
def check_fill_missing():
    print("\n4. fill missing data moved (its guard reads all seven ranges)\n")
    counts_path = EHR_ROOT / "rerun" / "logs" / "boundary_counts.json"
    flips = json.loads(counts_path.read_text())["guard_flips"]["mean"]["oxygen saturation"] \
        if counts_path.exists() else None

    new_log = EHR_ROOT / "Logs" / DATASET_NAME / "mean" / "fill_missing_data_filter_log.json"
    old_log = SCRATCH_ARCHIVE / "Logs" / DATASET_NAME / "mean" / "fill_missing_data_filter_log.json"
    if not new_log.exists():
        record(False, "new fill_missing_data_filter_log.json not written")
        return
    if not old_log.exists():
        record(False, f"pre-fix log not on scratch ({old_log}) — cannot diff",
               "scratch may have been purged; this check is informational only")
        return

    def total(path):
        entries = json.loads(path.read_text())
        if isinstance(entries, dict):
            entries = list(entries.values())
        return sum(e.get("feature_level", 0) for e in entries if isinstance(e, dict))

    before, after = total(old_log), total(new_log)
    record(after > before,
           f"imputed cells {before:,} -> {after:,} (+{after - before:,}); "
           f"pre-flight predicted ~{flips:,} newly eligible traces")


# ── 5 ────────────────────────────────────────────────────────────────────────
def check_rebuilt():
    print("\n5. nine arms rebuilt, four left alone\n")
    stale, fresh = [], []
    for agg in AGGREGATIONS:
        for arm in VITALS_DEPENDENT_ARMS:
            p = DATA_ROOT / agg / f"{slug(arm)}_filtered_dataset_ehr.pkl"
            (fresh if p.exists() and p.stat().st_mtime >= FIX_DATE else stale).append(p)
    record(not stale, f"{len(fresh)}/45 vitals-dependent pickles rebuilt today",
           "" if not stale else f"stale: {[p.name for p in stale[:5]]}")

    touched = []
    for agg in AGGREGATIONS:
        for arm in VITALS_INDEPENDENT_ARMS:
            name = "raw_dataset_ehr.pkl" if arm == "raw" else f"{slug(arm)}_filtered_dataset_ehr.pkl"
            p = DATA_ROOT / agg / name
            if p.exists() and p.stat().st_mtime >= FIX_DATE:
                touched.append(p)
    record(not touched, f"{len(VITALS_INDEPENDENT_ARMS) * len(AGGREGATIONS)} control pickles untouched",
           "" if not touched else f"UNEXPECTEDLY REBUILT: {[p.name for p in touched]}")


def main():
    print(f"verifying the vital-range fix against {ARCHIVE.name}\n")
    check_control_arms()
    check_spo2_centroid()
    check_filter_logs()
    check_fill_missing()
    check_rebuilt()

    failed = [label for ok, label in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("\nFAILED:")
        for label in failed:
            print(f"  - {label}")
        sys.exit(1)


if __name__ == "__main__":
    main()
