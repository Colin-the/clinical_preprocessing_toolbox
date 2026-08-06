# Clinical Preprocessing Toolbox

Does a published academic ICU-EHR preprocessing pipeline (`MIMIC_Extract`) or an in-house one (`EHR-Dataset-Processing`) produce a better downstream classifier signal for ICU length-of-stay and mortality prediction? This repo holds both pipelines, the notebook that puts them head to head, and a viewer for the ~2000 figures produced along the way.

For that question to mean anything the two have to be doing the same job, so both are pinned to the same seven bedside vitals (heart rate, systolic / diastolic / mean blood pressure, respiratory rate, temperature, oxygen saturation), the same first-24-hours window, and the same MIMIC-III cohort. Past that alignment they're genuinely independent codebases — no shared code, no shared build, no shared environment. Treat them as two projects that happen to live in one directory.

One gap in the alignment to know about before reading any result: **the two disagree on when hour 0 starts.** MIMIC_Extract anchors on ICU admission, EHR-Dataset-Processing on hospital admission. For a patient who spent time on a ward first, the two "first 24 hours" cover different periods.

## Repository layout

| Folder | Purpose |
|---|---|
| [`pipelines/MIMIC_Extract/`](pipelines/MIMIC_Extract/README.md) | Fork of the MIT MIMIC-Extract paper pipeline, ported from Docker/Python 3.6 to Apptainer/Python 3.9 so it runs on Compute Canada. |
| [`pipelines/EHR-Dataset-Processing/`](pipelines/EHR-Dataset-Processing/README.md) | In-house pipeline. GPU-bound (cuDF/cuML), and covers MIMIC-IV and eICU as well as MIMIC-III. |
| [`comparison/`](comparison/) | The notebook that joins both pipelines' output on the shared cohort and runs the actual comparison. |
| [`gallery/`](gallery/README.md) | Flask app for browsing everything in `figures/`, with side-by-side comparison. |
| `figures/` | ~2000 PNG/SVG files (~845MB), checked in. These are the product, not build noise. |

Each folder has its own README with the detail; the sections below are the orientation.

## `pipelines/MIMIC_Extract/`

Python 3.9 under Apptainer, driven by SLURM jobs in `apptainer/jobs/`. Sweeps 13 cohort scenarios — a no-filter baseline, three single-knob variants, and nine age bands (centres 35/45/55 × widths ±5/±10/±15) — emitting `data/curated/{scenario}/all_hourly_data.h5` for each. The age grid separates "which age group" from "how narrow a group", since tightening the band buys homogeneity at the cost of sample size.

The awkward part of running it is that Compute Canada blocks `--network host`, so Postgres is reached over a Unix socket — which means **every extraction job has to be scheduled onto the same node as the setup job that holds the database open.** [`apptainer/README.md`](pipelines/MIMIC_Extract/apptainer/README.md) covers the sequence and the failure modes.

## `pipelines/EHR-Dataset-Processing/`

Python 3.12 (`uv`) on CUDA 13, with cuDF/cuML/PyTorch doing the work. On `master`, which superseded `optimization_refactor` as of 2026-05-08.

Pulls the same seven vitals per dataset (`Processing/{mimic-iii,mimic-iv,eicu}-processing.py`), then applies 11 filters **one at a time rather than stacked** (`Managers/ehr_filter_manager.py`) — with filters chained you can't attribute an accuracy change to any one of them. Aggregates under the same 5 methods MIMIC_Extract uses. Main interface is the Marimo notebook at `Experiments/notebook.py`.

Two traps: the filter `OrderedDict` is order-sensitive (the first seven run before aggregation, the rest after, and the boundary is a *position*), and nothing invalidates the caches under `Data/<dataset>/<aggregation>/` — change a filter and you have to delete them by hand.

## `comparison/`

`pipeline_comparison.ipynb` — the payoff. Identical logistic regressions on matched feature sets from both pipelines, over ~27,000 shared MIMIC-III admissions, across all 5 aggregation methods.

The notebook deliberately re-implements aggregation itself rather than using each pipeline's own, so that a difference in results can't be an aggregation difference in disguise. Both sides go through the identical path from 24×7 matrix to 7 features; the only thing left varying is what the pipelines did beforehand. Logistic regression rather than something stronger, for the same reason — a simple model is more sensitive to feature quality, where a random forest would paper over the differences.

```bash
sbatch comparison/run_pipeline_comparison.sbatch     # logs → comparison/logs/
```

Needs 64GB: `vitals_labs` is stored in HDF fixed format and can't be row-filtered on read, so it loads whole and gets subset in memory.

`_gen_comparison_nb.py` generated the notebook originally and is kept only as a record of its structure. **Don't run it** — it overwrites the notebook, and the live one has been hand-patched well past what that script produces.

## `gallery/`

Finding one figure among 2000 by digging through `figures/` is miserable, so this is a filterable browser over them — and, more usefully, a side-by-side view, which is what you actually want when the entire project is a comparison. It also suggests cross-pipeline counterparts for whatever you're currently looking at.

**Not standalone**: it reads the sibling `figures/` directory, so it only works from inside a full checkout.

```bash
cd gallery && docker compose up --build   # or ./run.sh without Docker
```

Then http://localhost:8000. After a pipeline changes, regenerate in this order — `build_manifest.py` merges fragments the other two write, and won't complain if one is missing or stale:

```bash
python gallery/extract_notebook_graphs.py
python gallery/render_marimo_mimic_iii.py
python gallery/build_manifest.py
```

Figure titles are keyed on each figure's *position* in its notebook, because notebook outputs carry no stable identity of their own. Insert a plot and every title after it shifts onto the wrong image, silently. Run `extract_notebook_graphs.py --check` after editing a notebook.

## `figures/`

~2000 PNG/SVG files (~845MB), one subfolder per pipeline plus `Comparison/`. Checked into git deliberately: they're the output of runs that take days and a loaded MIMIC-III database to reproduce, not build artifacts.

Those subfolder names are baked into the `"pipeline"` field of every record in `gallery/graphs_manifest.json`, so renaming one silently empties that slice of the gallery.

## Environment / nibi setup

Three environments, none interchangeable. Don't go looking for the one venv that runs everything; it doesn't exist, and the Python versions alone (3.11 / 3.12) rule it out.

- `pipelines/MIMIC_Extract/.venv_stats/` — Python 3.11 with jupyter/nbformat/matplotlib/pandas/scipy. Does double duty as the environment for the gallery and the comparison notebook, which is why `run_pipeline_comparison.sbatch` sources it directly.
- `pipelines/EHR-Dataset-Processing/` — Python 3.12 via `uv`, GPU stack (cuDF/cuML/cuPy/PyTorch). **`pip install -r requirements.txt` does not give you a working environment** — that file only lists the CPU-side database and dataframe deps. The GPU wheels are in `Docker/Dockerfile`; use it or replicate it.
- `gallery/` — plain Flask. `run.sh` builds a local `.venv/` on an ordinary machine and falls back to `.venv_stats` on nibi, because `python -m venv` against a CVMFS interpreter produces a venv that looks fine and then can't import anything.

`module load postgresql apptainer` before anything on the MIMIC_Extract Apptainer path.

A recurring workaround worth knowing: several scripts (`gallery/render_marimo_mimic_iii.py`, `_recompute_centroids_cpu.py`) stub out `torch`/`cupy`/`cuml` in `sys.modules` so pickles written on a GPU box can be unpickled on a CPU node. That's why plotting and centroid work can run without a GPU at all.

## Data inputs

Both pipelines want their own Postgres, and neither ships the data — MIMIC-III and eICU are credentialed PhysioNet datasets you have to obtain yourself.

- **MIMIC_Extract** needs one Postgres loaded with MIMIC-III. The load is 50–80GB, which is more than a Compute Canada home directory holds, so point `POSTGRES_DATA_DIR` at scratch. See `pipelines/MIMIC_Extract/apptainer/README.md`. Raw and curated data lives in `pipelines/MIMIC_Extract/data/` (~20GB, gitignored).
- **EHR-Dataset-Processing** needs one container *per dataset*, each on its own port — see `Docker/initialize_*.sh`. Credentials go in `Secrets/<dataset>.env`; `eicu.env` is checked in, the two MIMIC ones you create locally with the same four keys. Processed records land in `Data/` (~3.8GB, gitignored).

## History

This repo consolidates four previously-separate projects as of 2026-07-01, with fresh git history (the old repos' commit history was not carried forward into this repo). For historical reference, the originals are:

- `MIMIC_Extract` — https://github.com/Colin-the/MIMIC_Extract
- `EHR-Dataset-Processing` — https://github.com/noahsub/EHR-Dataset-Processing (upstream; `optimization_refactor` branch there has a handful of per-dataset analysis notebooks not present in this repo's copy — see `CLAUDE.md`)
- `graph-gallery` — https://github.com/Colin-the/graph-gallery
