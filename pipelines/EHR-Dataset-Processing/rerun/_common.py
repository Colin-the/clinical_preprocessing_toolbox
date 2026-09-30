"""Shared setup for the post-bugfix rerun scripts.

Importing this installs the CPU backend and puts the repo on sys.path, so it has
to come before any `Managers.*` import. It also carries the FILTERS table and
VITALS ranges copied from Experiments/notebook.py — the rerun has to reproduce
exactly the arms the cached pickles were built with, and the notebook is the
definition of record for that (Managers.ehr_filter_manager.FILTERS omits
'all vitals' and carries no pre_aggregate flags).
"""
import os
import sys
from pathlib import Path

EHR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EHR_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# torch first — it introspects its own submodules at import time and gets
# confused if a stub is already sitting in sys.modules. Same ordering constraint
# as _recompute_centroids_cpu.py.
import torch  # noqa: E402,F401

import _cpu_backend  # noqa: E402

_cpu_backend.set_threads(int(os.environ.get("SLURM_CPUS_PER_TASK", "8")))

from Managers.ehr_filter_manager import (  # noqa: E402
    heart_rate_filter, systolic_blood_pressure_filter, diastolic_blood_pressure_filter,
    mean_blood_pressure_filter, respiration_rate_filter, temperature_filter,
    oxygen_saturation_filter, fill_missing_data_filter, long_missing_segment_filter,
    long_gap_filter, high_invalid_data_filter, all_vitals_filter,
)

DATASET_NAME = "mimic-iii"

AGGREGATIONS = ["mean", "median", "standard deviation", "mean deviation", "maximum deviation"]
LABELS = ["icu", "mortality"]

# Same four seeds as the notebook and the cross-pipeline comparison. Changing
# them makes the rerun incomparable to the run it replaces.
RANDOM_SEEDS = [22, 985, 439, 81]

# Hard physiological ranges for the seven vitals, keyed by the repo-wide lowercase
# names. `_remove_outliers` tests these as a CLOSED interval (`lo <= v <= hi`), so
# the upper bound is a value the filter keeps, not the first one it rejects. Until
# 2026-08-30 every table here sat one unit low (SpO2 99, so a perfectly normal — and
# modal — reading of 100% was deleted as a charting error); see bug register F-02.
#
# Six copies of this table exist and they must stay literally identical. Drift
# between them is what produced register entry R-30:
#   Experiments/apply_dataset_filter.py     Experiments/notebook.py
#   rerun/_common.py                        gallery/render_marimo_mimic_iii.py
#   Experiments/fill_missing_data_analysis.py
#   Experiments/render_paper_figures.py     (names/units only; ranges inert there)
VITALS = {
    'heart rate': [(1, 600), 'bpm'],
    'systolic blood pressure': [(1, 400), 'mmHg'],
    'diastolic blood pressure': [(1, 300), 'mmHg'],
    'mean blood pressure': [(1, 300), 'mmHg'],
    'respiration rate': [(1, 70), 'breaths/min'],
    'temperature': [(21, 50), 'C'],
    'oxygen saturation': [(1, 100), '%'],
}

# name → (function, pre_aggregate). Order is load-bearing: filter_impact results
# are read positionally by the plots and by the comparison notebook.
FILTERS = {
    'heart rate': (heart_rate_filter, True),
    'systolic blood pressure': (systolic_blood_pressure_filter, True),
    'diastolic blood pressure': (diastolic_blood_pressure_filter, True),
    'mean blood pressure': (mean_blood_pressure_filter, True),
    'respiration rate': (respiration_rate_filter, True),
    'temperature': (temperature_filter, True),
    'oxygen saturation': (oxygen_saturation_filter, True),
    'fill missing data': (fill_missing_data_filter, False),
    'long missing segment': (long_missing_segment_filter, False),
    'long gap': (long_gap_filter, False),
    'high invalid data': (high_invalid_data_filter, False),
    'all vitals': (all_vitals_filter, True),
}

DATA_ROOT = EHR_ROOT / "Data" / DATASET_NAME

# The nine arms whose cached datasets depend on the VITALS ranges: the seven per-vital
# outlier filters (each reads only its own bound), 'all vitals' (which chains all seven),
# and 'fill missing data' (whose ">= 2 known values" guard tests every range —
# ehr_filter_manager.py:129-130 — which is how the bounds reach an arm that does no
# outlier removal of its own).
#
# The other four arms are deliberately NOT here. 'raw' never sees `vitals`; the three
# structural filters accept it and ignore it, and create_filter_dataset builds them from
# the RAW aggregated records rather than from an outlier-filtered chain
# (dataset_manager.py:96), so a change to the ranges cannot reach them. That is what
# makes them the control group for the 2026-08-30 rerun: if any of raw / long missing
# segment / long gap / high invalid data moves, something was rebuilt that should not
# have been.
VITALS_DEPENDENT_ARMS = [
    'heart rate',
    'systolic blood pressure',
    'diastolic blood pressure',
    'mean blood pressure',
    'respiration rate',
    'temperature',
    'oxygen saturation',
    'fill missing data',
    'all vitals',
]

VITALS_INDEPENDENT_ARMS = ['raw', 'long missing segment', 'long gap', 'high invalid data']


def agg_from_task_id(task_id: int) -> str:
    return AGGREGATIONS[task_id]


def agg_label_from_task_id(task_id: int):
    """Array index → (aggregation, label). 10 tasks: 5 aggregations × 2 labels."""
    return AGGREGATIONS[task_id // len(LABELS)], LABELS[task_id % len(LABELS)]


def arm_agg_from_task_id(task_id: int):
    """Array index → (arm, aggregation) over VITALS_DEPENDENT_ARMS × AGGREGATIONS.

    9 arms × 5 aggregations = 45 tasks. Arm-major, so consecutive task ids share an
    arm — which is what you want when the array is throttled and you would rather
    finish one arm across all aggregations than half of every arm.
    """
    n = len(AGGREGATIONS)
    return VITALS_DEPENDENT_ARMS[task_id // n], AGGREGATIONS[task_id % n]
