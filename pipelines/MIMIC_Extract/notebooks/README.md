# Notebooks

Two groups in here, and it's worth knowing which is which: the analysis notebooks below are local work built on this fork's 13-scenario sweep, while everything under "Upstream baselines" ships with the paper and is largely untouched.

## The ones being actively worked on

**`curated_mimic_iii_analysis_executed copy 2.ipynb`** — the model-evaluation notebook, and the one you probably want. Loads each scenario's `all_hourly_data.h5`, aggregates `vitals_labs` five ways, fits a logistic regression per scenario for both labels, then runs McNemar against `baseline_nofilters` and plots PCA centroid shift.

Two things about it that surprise people. `vitals_labs` is stored in HDF *fixed* format, so you can't row-filter on read — the notebook loads everything and subsets afterwards via `subset_X_by_patients`, which is why it's memory-hungry. And `_select_pos_label` exists because the mortality column is called `mort_icu`, `mort_hosp`, or `hospital_expire_flag` depending on which MIMIC vintage produced the file.

Despite the name, this is the current version. `curated_mimic_iii_analysis.ipynb` and `... copy.ipynb` are stale duplicates, and `old/` holds earlier versions — the gallery extracts from them but marks them superseded.

**`Experiment_Statistics.ipynb`** — the descriptive view of the same sweep, reading `../experiment_stats.json` rather than the HDF files. Bar charts, heatmaps and error bars of each vital's mean/median/std across all 13 scenarios. Keep the `EXCLUDED_EXPERIMENTS = {'baseline_nofilters_fast'}` gate; that scenario is a truncated debug run and including it skews every comparison.

Re-run these with `run_notebook_refresh.sbatch` rather than by hand on a login node — it executes them in place via nbconvert from `.venv_stats/`.

## Upstream baselines

Shipped with the paper. Useful as reference for what the extractor's output is meant to support, but not part of the comparison story, and several want TensorFlow 1.x / Keras 2.2 which nothing here has installed.

`Testing mimic_direct_extract.ipynb` has tests for the extractor's processing functions.


* `Baselines for Mortality and LOS prediction - Sklearn.ipynb`

This notebook demonstrates the use of **MIMIC-Extract** output in mortality and long length-of-stay prediction tasks. Logistic regression and random forest models are fitted using Scikit-Learn.

* `Baselines for Mortality and LOS prediction - GRU-D.ipynb`

This notebook demonstrates the use of **MIMIC-Extract** output in mortality and long length-of-stay prediction tasks. GRU-D models are fitted.

* `Baselines for Intervention Prediction - Mechanical Ventilation.ipynb`

This notebook demonstrates the use of **MIMIC-Extract** output in mechanical ventilation prediction task. Logistic regression and random forest models models are fitted using Scikit-Learn. CNN is fitted using Keras 2.2.4. LSTM is fitted using Tensorflow 1.8.0.

* `Baselines for Intervention Prediction - Vasopressor.ipynb`

This notebook demonstrates the use of **MIMIC-Extract** output in vasopressor prediction task. Logistic regression and random forest models models are fitted using Scikit-Learn. CNN is fitted using Keras 2.2.4. LSTM is fitted using Tensorflow 1.8.0.
