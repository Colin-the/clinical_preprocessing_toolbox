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

VITALS = {
    'heart rate': [(1, 599), 'bpm'],
    'systolic blood pressure': [(1, 399), 'mmHg'],
    'diastolic blood pressure': [(1, 299), 'mmHg'],
    'mean blood pressure': [(1, 299), 'mmHg'],
    'respiration rate': [(1, 69), 'breaths/min'],
    'temperature': [(21, 49), 'C'],
    'oxygen saturation': [(1, 99), '%'],
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


def agg_from_task_id(task_id: int) -> str:
    return AGGREGATIONS[task_id]


def agg_label_from_task_id(task_id: int):
    """Array index → (aggregation, label). 10 tasks: 5 aggregations × 2 labels."""
    return AGGREGATIONS[task_id // len(LABELS)], LABELS[task_id % len(LABELS)]
