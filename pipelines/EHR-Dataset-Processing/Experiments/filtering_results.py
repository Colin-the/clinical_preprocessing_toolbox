"""The numbers behind the "Beyond the Model" talk and poster, with no rendering deps.

    from filtering_results import load
    d = load()

Shared by `build_filtering_slides.py` (python-pptx, in .venv_slides) and
`render_poster_figures.py` (matplotlib, under scipy-stack). Neither environment has
the other's renderer, so the data layer lives here, importing only numpy and json.
Both outputs therefore read the same artifacts through the same cross-checks.

Scope, fixed deliberately: MIMIC-III, mean aggregation, the `_cv` evaluation design.
That is the setting the paper's figures describe, and mixing designs — the legacy
single-holdout sidecars report a different cohort prevalence for the same arm — is
the easiest way to print a wrong number.

McNemar numbers are the *baseline-threshold* comparison: every arm re-scored at
raw's threshold, which is what the paper's Fig. 7 shows. The p-values stored in the
CV diagnostics are the own-threshold variant and are not used. They come from
`rerun/dump_baseline_mcnemar.py`, which runs under scipy-stack.
"""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MEAN = ROOT / "Data" / "mimic-iii" / "mean"
LOGS = ROOT / "Logs" / "mimic-iii" / "mean"

LABELS = ("mortality", "icu")
TASK = {"mortality": "In-hospital mortality", "icu": "Prolonged ICU stay"}

VITAL_ARMS = ["heart rate", "systolic blood pressure", "diastolic blood pressure",
              "mean blood pressure", "respiration rate", "temperature",
              "oxygen saturation"]
RECORD_ARMS = ["long missing segment", "long gap", "high invalid data"]
ARMS = ["raw"] + VITAL_ARMS + ["all vitals", "fill missing data"] + RECORD_ARMS

SHORT = {"raw": "raw (no filter)", "heart rate": "heart rate",
         "systolic blood pressure": "systolic BP",
         "diastolic blood pressure": "diastolic BP",
         "mean blood pressure": "mean BP", "respiration rate": "respiration rate",
         "temperature": "temperature", "oxygen saturation": "oxygen saturation",
         "all vitals": "all vitals", "fill missing data": "fill missing data",
         "long missing segment": "long missing segment", "long gap": "long gap",
         "high invalid data": "high invalid data"}

# Paper Table II, verbatim: the level each filter operates at and its threshold.
# Value-level filters edit measurements, feature-level filters edit cells, and only
# record-level filters can delete a patient. This is the distinction the talk turns on.
LEVELS = {**{v: "value" for v in VITAL_ARMS}, "all vitals": "value",
          "fill missing data": "feature",
          **{r: "record" for r in RECORD_ARMS}}

THRESHOLDS = {"heart rate": "[1, 600] bpm", "systolic blood pressure": "[1, 400] mmHg",
              "diastolic blood pressure": "[1, 300] mmHg",
              "mean blood pressure": "[1, 300] mmHg",
              "respiration rate": "[1, 70] breaths/min", "temperature": "[21, 50] °C",
              "oxygen saturation": "[1, 100] %", "all vitals": "union of the seven",
              "fill missing data": "k = 3, ≥ 2 known points",
              "long missing segment": "≥ 10 consecutive missing/zero hours",
              "long gap": "≥ 2 consecutive all-blank hours",
              "high invalid data": "> 10% of the 168 cells invalid"}

# Paper Table III. Published, so it is quoted rather than recomputed.
TABLE_III = [
    ("(a) raw measurements", "1,158,296", "9,999,999", "98.6", "86", "9,291.5"),
    ("(b) after the heart-rate range", "1,157,789", "459", "90.0", "86", "24.4"),
    ("(c) mean-aggregated, before", "45,985", "555,652", "105.3", "87.1", "2,590.9"),
    ("(d) mean-aggregated, after", "45,989", "251.5", "93.2", "87.1", "25.5"),
]

# The four distinct cohort sizes: every value- and feature-level arm keeps the raw
# cohort, so raw stands in for all ten of them.
COHORT_STEPS = ["raw", "long missing segment", "long gap", "high invalid data"]


def load() -> dict:
    """Read every number the talk and poster show, and check the artifacts against
    each other.

    Three cross-checks, all fatal. The survivor counts have two independent sources
    (the admission-id sidecars stage E writes, and `n_records` in the stage F
    diagnostics) and they must agree, because the cohort-size argument rests on
    them. The seven per-vital filter logs must sum to the `all vitals` log, which is
    the only end-to-end check that the value-level accounting is complete. And `raw`
    must pair against itself with zero discordance, which is the sanity check that
    the McNemar pairing is keyed on admission_id at all.
    """
    diagnostics = {
        label: json.loads((MEAN / f"{label}_filter_impact_cv_diagnostics.json").read_text())
        for label in LABELS
    }

    survivors = {arm: int(np.load(MEAN / f"{arm.replace(' ', '_')}_admission_ids.npy").shape[0])
                 for arm in ARMS}
    for label in LABELS:
        for arm in ARMS:
            recorded = int(diagnostics[label][arm]["n_records"])
            if recorded != survivors[arm]:
                raise AssertionError(
                    f"{label}/{arm}: the admission-id sidecar holds {survivors[arm]} "
                    f"records but the stage F diagnostics recorded {recorded}. "
                    "One of the two is stale; re-run stages E and F before building."
                )
        m = diagnostics[label]["raw"]["mcnemar"]
        if (m["n01"], m["n10"]) != (0, 0):
            raise AssertionError(
                f"{label}: raw pairs against itself with n01/n10 = "
                f"({m['n01']}, {m['n10']}) rather than (0, 0). The McNemar pairing "
                "is not keyed on admission_id."
            )

    value_level = {}
    for arm in VITAL_ARMS + ["all vitals"]:
        entries = json.loads((LOGS / f"{arm.replace(' ', '_')}_filter_log.json").read_text())
        value_level[arm] = sum(int(e["value_level"]) for e in entries)
    per_vital_total = sum(value_level[v] for v in VITAL_ARMS)
    if per_vital_total != value_level["all vitals"]:
        raise AssertionError(
            f"the seven per-vital filter logs sum to {per_vital_total} altered "
            f"readings but the all-vitals log records {value_level['all vitals']}. "
            "The value-level accounting is incomplete; re-run stage K."
        )

    # The filter logs test `not (lo <= v <= hi)`, which is True for NaN, so they count
    # in-cell NaN as implausible readings. The NaN audit splits each log count into
    # NaN / below / above; it must reproduce the log exactly to be trusted.
    audit = json.loads((ROOT / "rerun" / "logs" / "value_filter_nan_counts.json")
                       .read_text())["per_vital"]
    value_level_genuine = {}
    for arm in VITAL_ARMS:
        if audit[arm]["removed_all"] != value_level[arm]:
            raise AssertionError(
                f"{arm}: the NaN audit counts {audit[arm]['removed_all']} out-of-range "
                f"entries but the filter log records {value_level[arm]}. The audit is "
                "stale; re-run /scratch/ccampb47/nan_audit/job.sh."
            )
        value_level_genuine[arm] = audit[arm]["removed_non_nan"]
    value_level_genuine["all vitals"] = sum(value_level_genuine[v] for v in VITAL_ARMS)

    boundary = json.loads((ROOT / "rerun" / "logs" / "boundary_counts.json").read_text())
    readings = sum(int(v["total"]) for v in boundary["per_vital"].values())

    mcnemar = {}
    for label in LABELS:
        path = MEAN / f"{label}_mcnemar_baseline_threshold.json"
        if not path.exists():
            raise FileNotFoundError(
                f"{path.name} not found. The baseline-threshold McNemar (the paper's "
                "Fig. 7) is derived from the stored out-of-fold scores — run "
                "`rerun/dump_baseline_mcnemar.py` under scipy-stack first."
            )
        mcnemar[label] = json.loads(path.read_text())

    return {"diagnostics": diagnostics, "survivors": survivors,
            "value_level": value_level, "value_level_genuine": value_level_genuine,
            "readings": readings, "mcnemar": mcnemar}


def arm_stat(d, label, arm, key):
    return float(d["diagnostics"][label][arm][key])


def delta(d, label, arm, key):
    return arm_stat(d, label, arm, key) - arm_stat(d, label, "raw", key)


def p_value(d, label, arm):
    return float(d["mcnemar"][label][arm]["p"])


def fmt_p(p):
    """Compact p for a slide. The record-level arms reach 1e-147, so this has to
    survive the denormal end of the range without turning into `0.0e-320`."""
    if p >= 0.01:
        return f"{p:.3f}"
    if p <= 0.0:
        return "<1e-308"
    # Let the float formatter do the decomposition. Computing the mantissa as
    # p * 10**-exponent overflows for the smallest p in this sweep (1e-147 is fine,
    # but the reciprocal of a denormal is not), and this cannot.
    mantissa, exponent = f"{p:.1e}".split("e")
    return f"{mantissa}e{int(exponent)}"


def paired_delta(d, label, arm):
    """The filter's effect measured against the baseline on the arm's own survivors.

    Both sides come from the same stored consensus prediction vector, so this is a
    like-for-like comparison on an identical record set. It is a different estimator
    from the one the bar charts plot — that one scores the baseline on the whole
    cohort — and the gap between the two estimators is the point of the caveat.
    """
    m = d["diagnostics"][label][arm]["mcnemar"]
    return m["arm_accuracy_on_paired"] - m["baseline_accuracy_on_paired"]
