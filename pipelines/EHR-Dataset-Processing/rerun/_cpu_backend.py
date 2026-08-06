"""CPU stand-ins for cupy and cuml, so Managers/* can be imported and run on nibi.

nibi has no cupy/cuml/cudf and no RAPIDS module, and Compute Canada's wheel index
doesn't carry them — so the GPU path the Managers were written for cannot run
here at all. `_recompute_centroids_cpu.py` solved this for the centroid functions
with inert stubs, but the filter-impact sweep actually trains models, so inert
stubs won't do: these are working numpy/sklearn implementations registered under
the cupy/cuml module names.

**This changes the numbers.** cuML's random forest and sklearn's are different
implementations, so absolute scores from a run through this backend are not
comparable to scores from the original GPU run. What stays valid is any
comparison *within* a single run — filter-vs-raw deltas, McNemar, the shape of
the curve across filters — because every arm goes through the same estimator.
Import this module before anything under Managers.
"""
import sys
from types import ModuleType

import numpy as np
from sklearn.ensemble import RandomForestClassifier as _SkRF
from sklearn.metrics import accuracy_score as _sk_accuracy
from sklearn.model_selection import KFold as _SkKFold

# How many cores the forest may use. Set from SLURM_CPUS_PER_TASK by the callers.
N_JOBS = -1


def _install(name: str, **attrs) -> ModuleType:
    m = ModuleType(name)
    m.__file__ = "<cpu-backend>"
    m.__path__ = []
    m.__spec__ = None
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


# ── cupy → numpy ─────────────────────────────────────────────────────────────
# Only the handful of entry points Managers actually calls. asnumpy is the
# identity here because arrays never left host memory in the first place.
_install(
    "cupy",
    ndarray=np.ndarray,
    array=np.array,
    asarray=np.asarray,
    asnumpy=np.asarray,
    stack=np.stack,
    vstack=np.vstack,
    concatenate=np.concatenate,
    mean=np.mean,
    zeros=np.zeros,
    float32=np.float32,
    int32=np.int32,
)

_install("cudf")
_install("cugraph")


# ── cuml → sklearn ───────────────────────────────────────────────────────────
class RandomForestClassifier(_SkRF):
    """sklearn's forest wearing cuML's constructor.

    cuML ignores n_jobs (it has a GPU); sklearn needs it or it runs
    single-threaded and the sweep takes days. Labels arrive as floats from
    DatasetEHR tensors — cuML accepts that, and sklearn does too, but it makes
    `classes_` float and the McNemar table indexing downstream assumes 0/1
    integers, so fit() casts.
    """

    def __init__(self, n_estimators=100, random_state=None, **kwargs):
        kwargs.pop("n_streams", None)      # cuML-only knob
        kwargs.pop("split_criterion", None)
        kwargs.setdefault("n_jobs", N_JOBS)
        super().__init__(n_estimators=n_estimators, random_state=random_state, **kwargs)

    def fit(self, X, y, **kw):
        return super().fit(np.asarray(X), np.asarray(y).astype(int), **kw)

    def predict(self, X, **kw):
        return super().predict(np.asarray(X)).astype(int)


def accuracy_score(y_true, y_pred, **kw):
    return float(_sk_accuracy(np.asarray(y_true).astype(int),
                              np.asarray(y_pred).astype(int)))


_install("cuml")
_install("cuml.ensemble", RandomForestClassifier=RandomForestClassifier)
_install("cuml.model_selection", KFold=_SkKFold)
_install("cuml.metrics", accuracy_score=accuracy_score)
sys.modules["cuml"].ensemble = sys.modules["cuml.ensemble"]
sys.modules["cuml"].model_selection = sys.modules["cuml.model_selection"]
sys.modules["cuml"].metrics = sys.modules["cuml.metrics"]


def set_threads(n: int) -> None:
    """Point the forest at the cores SLURM actually gave us."""
    global N_JOBS
    N_JOBS = n
