# Do not reuse — deprecated paths

Written 2026-08-12, from the second-pass audit of `rerun/bug_register.py`.

This file exists because deprecated code kept getting consulted as if it were current. Several
first-pass bug reports turned out to describe hazards that live only in the files below, or in
prior-art repositories that were never part of this pipeline — most memorably **I-04**, a
Critical "wrong-patient id mapping" that was a note transplanted verbatim from
`hour_scaling_experiment/v3/`, describing code that has never existed here.

Before filing a defect against a file, check it against this table. If the mechanism you found
lives only in a path listed here, it is **stale**, not open.

`_deprecated/MANIFEST.md` remains the detailed catalogue of *what* was set aside and why; this
file is the short do-not-reuse ledger on top of it.

---

## Deprecated paths

| Path | Classification | Why | Use instead | Authority |
|---|---|---|---|---|
| `_deprecated/**` (toolbox root) | Archived artifacts | Pre-fix pickles, superseded notebooks, stale manifests, deliberately set aside | The live tree | `_deprecated/MANIFEST.md` |
| `_deprecated/pre_bugfix_snapshot_2026-08-05/Data/` | Superseded data | Pre `fill_missing_data_filter` / training-F1 / sklearn-estimator fixes | `Data/<dataset>/<agg>/` in the live tree | MANIFEST §2 |
| `_deprecated/pre_split_fix_2026-08-10/{Data,paper_figures}/` | Superseded data + figures | Validation split was merged into test before 2026-08-10 | Live `Data/` and `paper_figures/` | MANIFEST §8 |
| `_deprecated/pre_cv_figures_2026-08-26/paper_figures/` | Superseded figures | Rendered from the legacy single-holdout pickles; the live set reads `_cv` | Live `paper_figures/` | MANIFEST §9 |
| `_deprecated/pre_spo2_fix_2026-08-30/` + `$SCRATCH/ehr_pre_spo2_fix_2026-08-30/` | Superseded data + figures | Built with the old vital ranges, which deleted 29.4% of all SpO2 readings. Nine of thirteen arms invalid | Live `Data/`, `Logs/`, `paper_figures/` | MANIFEST §10 |
| `_deprecated/superseded_notebooks/MIMIC_Extract/` | Superseded notebooks | Four earlier links in the Mar 19 → Apr 01 → Apr 24 → May 11 lineage | `notebooks/curated_mimic_iii_analysis_executed copy 2.ipynb` | MANIFEST §3 |
| `_deprecated/stale_manifests/graphs_manifest_backup.json` | Stale manifest | 888 records, 45 superseded | `gallery/graphs_manifest.json` | MANIFEST §4 |
| `rerun/regen_fill_missing.py` | Superseded stage script | Stage A, hardcoded to the single `fill missing data` arm. Kept as the record of the 2026-08-05 rerun | `rerun/regen_filtered_datasets.py` (stage K), which does any arm | Audit guardrail 8; MANIFEST §10 |
| `_recompute_centroids_cpu.py` (repo root) | Superseded one-off | CPU centroid recompute; also carries a 7th stale copy of the `FILTERS` table | `Managers/evaluation_manager.py` centroid functions | Audit guardrail 8; R-32 |
| `~/work/fix_zeros_patch.py` | Abandoned patch | Never integrated; predates the consolidated toolbox | Nothing — the zero-handling question is live as **R-21** | Audit guardrail 8 |
| `~/work/pipeline_comparison copy.ipynb` | Stray copy | Ad-hoc duplicate outside the toolbox | `comparison/pipeline_comparison.ipynb` | Audit guardrail 8 |
| `~/work/pipeline_comparison.ipynb.bak_20260514_160227` | Stray backup | Ad-hoc backup outside the toolbox | `comparison/pipeline_comparison.ipynb` | Audit guardrail 8 |
| `~/work/run_comparison_nb.sbatch`, `~/work/run_pipeline_comparison.sbatch` | Stray job scripts | Submit the stray notebook copies | Job scripts under `rerun/` | Audit guardrail 8 |
| `~/work/hour_scaling_experiment/` | **Prior art — different experiment** | Separate hours-of-history study. Its findings do **not** transfer | Read for context only; never cite as a defect in this pipeline | Audit guardrail 8; I-04, E-12 |

### The prior-art trap

`hour_scaling_experiment/` is the single most dangerous entry in this table, because its code
*resembles* this pipeline and its `POSTMORTEM.md` reads like a list of bugs. Two first-pass
entries were reclassified because of it:

- **I-04** (ARTIFACT) — the `searchsorted` wrong-patient hazard is described in
  `hour_scaling_experiment/v3/extract_duckdb.py:134-140` and `v3/build_features.py:151-161`,
  where it was designed out and asserted against. This pipeline has no `searchsorted` in
  `Processing/` at all; its only live use is `Managers/partition_manager.py:126`, which is
  bounds- and value-checked and regression-tested.
- **E-12** (INTENTIONAL) — the POSTMORTEM's "no outlier filtering on the raw data" finding
  concerns an experiment where unfiltered data was the sole *training substrate*. Here the
  unfiltered `raw` arm is the deliberate experimental **control**, and the outlier-clean
  counterpart already exists as the `all vitals` treatment arm.

One factual correction to the catalogue, from **R-34**: `_deprecated/MANIFEST.md` §8 says the
sibling split fix landed "a year earlier". Git dates it to commit `70787f6`, 2026-08-05 —
**five days** before the toolbox fix, and the sibling repository has no history before
2026-08-05 at all.

---

## Explicitly NOT deprecated

Things that have been mistaken for dead code:

| Path | Status |
|---|---|
| `Experiments/apply_dataset_filter.py` | **Live and required.** The documented prerequisite that builds the cached filtered datasets. See R-32 for its one real gap: it imports the 11-entry `FILTERS` and so does not build the `all vitals` arm. |
| `Managers/visualization_manager_v2.py` | **The only** visualization manager. There is no v1 in this repo — do not go looking for one. |
| `comparison/pipeline_comparison.ipynb` | Live cross-pipeline comparison notebook. |
| `comparison/_gen_comparison_nb.py`, `pipelines/MIMIC_Extract/_patch_copy2.py` | **Provenance, not deprecated.** They generate/patch the live notebook. A defect present only in a generator is a latent regression that returns on regeneration — real, but not currently rendered. |
| `Managers/evaluation_manager.py` legacy `evaluate_filter_impact` | **Live by design**, alongside `evaluate_filter_impact_cv`. Both paths coexist. Since 2026-08-26 `paper_figures/` consumes `_cv`, but `notebook.py`'s `IMPACT_SUFFIX` still defaults to `''`, so the two now show different designs from the same directory. A fix in only one path is *partial*. |
| `Managers/evaluation_manager.py` `evaluate_balance_impact_cv` (stage H, 2026-08-20) | **A third path, live by design.** Answers a different question — does balancing the *training data* beat moving the threshold — so it deliberately does not call `pick_threshold` or `inner_split` and scores at a fixed 0.5. Its numbers are **not** comparable to either path above and are written to `<label>_balance_impact_cv.pkl`. Fixing a shared helper still has to land on all three. |
| `_deprecated/MANIFEST.md` | Deprecated *code* catalogue, but a **live documentation source**. A false statement inside it is an open defect (see R-34). |
| `rerun/regen_centroids.py` | **Live again as of 2026-08-30.** It was a one-off pinned to `fill missing data`; it now takes `--arms` (`all` = the nine vitals-dependent arms) and is stage C of any rerun. Its default is still the single old arm, so pre-2026-08-30 invocations behave unchanged. |
| `rerun/regen_filtered_datasets.py`, `rerun/job_k_filtered_datasets.sh` | **Live.** Stage K — the generalised form of stage A, rebuilding any (arm, aggregation) cell. Added for the 2026-08-30 vital-range rerun. |

---

## Current entry points

```bash
# 1. ingest: DB -> Data/<dataset>/processed_record_ehr.pkl
python Processing/mimic-iii-processing.py

# 2. build + cache the filtered arms, per aggregation method
python Experiments/apply_dataset_filter.py mimic-iii mean

# 3. the analysis
marimo edit Experiments/notebook.py

# 4. paper figures
sbatch rerun/job_j_figures.sh          # renders from the _cv artifacts;
                                      # --impact-suffix '' for the legacy design
```

Live `rerun/` stage scripts: `_common.py`, `_cpu_backend.py`, `regen_filter_impact.py` (stage B),
`regen_centroids.py` (C), `regen_admission_ids.py` (E), `regen_filter_impact_cv.py` (F),
`verify_cv.py` (G), `regen_balance_cv.py` (H), `verify_balance.py` (I),
`regen_filtered_datasets.py` (K), `measure_boundary_counts.py`,
`quarantine_pre_spo2_fix.py`, `sweep_stale_figures.py`, `test_vital_bounds.py`,
`confusion_matrices_mean_raw.py`, `export_confusion_workbook.py`, and `bug_register.py`
(`python rerun/bug_register.py` rewrites `rerun/logs/bug_register.html`).

Note on `verify_cv.py`: a green `rerun/logs/g_verify_cv_*.log` is **weak evidence**. The
verifier has known holes (N-07, N-11, N-13, N-14), and only mean-family logs exist. Never
close a finding on that log alone.

---

## Register entries reclassified by the second pass

The audit re-derived all 88 entries from the working tree with blind verification agents. Four
were reclassified as not-a-live-defect; none of the 88 turned out to be true only of deprecated
code, so there are **no `STALE` entries** in the register today.

| Id | New status | Why |
|---|---|---|
| I-04 | Not a bug (audit artifact) | Mechanism does not exist here; transplanted from prior art |
| N-18 | Not a bug (audit artifact) | Unweighted mean over repeats is exact — coverage is uniform by construction (verified across all 130 arm entries) |
| E-12 | Intentional design | The unfiltered `raw` arm is the experimental control |
| B-03 | Intentional design | `asnumpy=np.asarray` aliasing is documented at `rerun/_cpu_backend.py:41-42`, and real `cupy.asnumpy` takes the same no-copy branch for host arrays |

Do not reopen these without new evidence. Each carries an `audit` block in the register with the
verdict, the mode of verification, and the reasoning. Raw audit material, including every
agent's evidence and files-read manifest, is in `~/work/.claude/audit-second-pass/`.
