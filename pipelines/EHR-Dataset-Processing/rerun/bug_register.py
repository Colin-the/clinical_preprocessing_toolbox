"""Single source of truth for the toolbox bug register, plus its HTML renderer.

The register is defined once, here, and both views of it — the summary table and
the per-bug detail cards — are generated from the same list. That is the whole
point of the file: a register maintained as two hand-written documents drifts,
and a drifting bug register is worse than none.

Findings came from three sources on 2026-08-11: a full ingest-to-figure data-flow
trace, a statistical audit of the evaluation layer, and a sweep of the documented
history in `_deprecated/MANIFEST.md` plus `hour_scaling_experiment/POSTMORTEM.md`.
Entries carrying `verified=True` were re-checked directly against artifacts on
disk; the rest are reported as found and should be confirmed before being acted
on.

Second pass 2026-08-12: every entry was independently re-verified by blind
sub-agents that re-derived each finding from the working tree without seeing
the original prose. Per-entry outcomes live in the `audit` field; statuses
ARTIFACT / INTENTIONAL / STALE mark entries the second pass reclassified.
Raw audit material: ~/work/.claude/audit-second-pass/.

    python rerun/bug_register.py           # writes rerun/logs/bug_register.html
"""
from pathlib import Path
import html
import json

OUT = Path(__file__).resolve().parent / "logs" / "bug_register.html"

CRITICAL, HIGH, MEDIUM, LOW = "Critical", "High", "Medium", "Low"
RESOLVED = "Fully resolved"
PARTIAL = "Partially resolved"
OPEN = "Not attempted"
WONTFIX = "Won't fix"
INTRODUCED = "Introduced 2026-08-11"
NEEDS_CHECK = "Needs verification"
ARTIFACT = "Not a bug (audit artifact)"
INTENTIONAL = "Intentional design"
STALE = "Stale — deprecated code only"

INGEST, FILTER, EVAL, BACKEND, REPORT = (
    "Ingest", "Filter / aggregate", "Evaluation", "CPU backend", "Reporting",
)

# ─────────────────────────────────────────────────────────────────────────────
# The register. Field contract:
#   id, name, overview, severity, status, stage, affects, recompute,
#   technical, fix, verification, found, verified
# ─────────────────────────────────────────────────────────────────────────────

BUGS = [

# ── Ingest ────────────────────────────────────────────────────────────────────
dict(
    id='I-01', stage=INGEST, severity=CRITICAL, status=OPEN, verified=True,
    name='Deaths and discharges inside the 24-hour window are not excluded',
    overview=('A patient who dies six hours into the window has the remaining '
                'eighteen hours zero-filled, so the outcome is legible directly from '
                'the feature vector.'),
    affects=('All ICU and mortality accuracy/F1 numbers in '
               'Data/mimic-iii/*/{icu,mortality}_filter_impact.pkl and '
               '*_filter_impact_cv.pkl and their diagnostics JSONs (raw arm: ICU '
               'accuracy_mean 0.6936, mortality accuracy_mean 0.6868 at prevalence '
               '0.09656), plus every figure derived from them: '
               'paper_figures/filter_impact_{icu,mortality}_testing_{accuracy,f1}_mean'
               '.pdf and mcnemar_icu_mean.pdf. The centroid figures are also '
               'affected, since post-discharge zeros are masked by '
               'compute_tensor_centroid but shrink the per-vital denominators '
               'asymmetrically between early- and late-ending stays.'),
    recompute=('Everything downstream of ingest: re-run '
                 'Processing/mimic-iii-processing.py, then '
                 'Experiments/apply_dataset_filter.py for all five aggregations, '
                 'then rerun/regen_admission_ids.py, '
                 'rerun/regen_filter_impact_cv.py, rerun/regen_filter_impact.py, '
                 'rerun/regen_centroids.py-equivalents, and '
                 'Experiments/render_paper_figures.py. Cohort size (currently '
                 '46,032) and both prevalences will change.'),
    technical=('`fetch_all_timeseries` computes `hour` from `admittime` and keeps '
                 '`0 <= hour < 24` (mimic-iii-processing.py:79-80). No query in the '
                 'file selects `dischtime`, and `deathtime` is read only in '
                 '`get_mortality_labels` (line 172) to set a binary label with no '
                 'timing condition (line 177) — grep for `dischtime` over the whole '
                 'pipeline returns nothing. `build_vitals_timeseries` reindexes '
                 'every record to a full 24 rows with `fill_value=[]` (line 116), so '
                 'hours after the stay ended are structurally indistinguishable from '
                 'hours the patient was present but uncharted. `aggregate` maps a '
                 'zero-length cell to `np.nan` (ehr_filter_manager.py:383-384), and '
                 '`RecordEHR.to_tensor` maps NaN to 0.0 (ehr_record.py:42). The '
                 'prior-art measurement in '
                 '/home/ccampb47/work/hour_scaling_experiment/POSTMORTEM.md:130-132 '
                 'confirms the outcome empirically on these exact cached tensors: '
                 '"38.99% of all cells are exactly zero and none are NaN". One arm '
                 'makes it worse rather than better: `fill_missing_data_filter` '
                 '(ehr_filter_manager.py:104-140) KNN-imputes the NaN hours from the '
                 'patient\'s own earlier hours, so the "fill missing data" arm '
                 'fabricates vitals for hours after the patient died.\n'
                 '\n'
                 "First-pass measurements retained: The model can read 'trace stops "
                 "at hour 6' straight off the 168-vector. This is also the mechanism "
                 'behind the prevalence shifts: high invalid data moves mortality '
                 'prevalence 0.097 -> 0.194 and ICU 0.375 -> 0.606.'),
    fix=('In `fetch_all_timeseries`, join `a.dischtime` and `a.deathtime` '
           'alongside `a.admittime`, and (a) exclude any admission whose '
           '`min(dischtime, deathtime) - admittime < 24h` from the cohort entirely, '
           'or (b) keep them but carry an explicit per-record observation-length '
           'mask so hours after stay end are distinguishable from uncharted hours. '
           'Option (a) is the defensible one for a filter-impact study, since (b) '
           'leaves the same signature in the tensor. Separately, stop encoding '
           'missingness as 0.0 — add a companion mask channel rather than relying on '
           'out-of-range zeros.'),
    verification=('Re-query the DB for `count(*) from admissions where '
                    "least(coalesce(deathtime,'infinity'), dischtime) - admittime < "
                    "interval '24 hours'` and confirm that count no longer appears "
                    'in raw_admission_ids.npy. Then check, on the rebuilt `mean` '
                    'tensors, that the correlation between "number of all-zero '
                    'trailing hours" and each label drops to what within-window '
                    'sparsity alone explains; and that mortality macro-F1 does not '
                    'rise when the trailing-zero count is added as an explicit '
                    'feature.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C1',
        note=('Agent adds honesty caveat: effect bounded by fraction of stays ending '
             'inside 24h; raw mortality numbers not leak-dominated.'),
    ),
),
dict(
    id='I-02', stage=INGEST, severity=CRITICAL, status=OPEN, verified=True,
    name='No patient-level grouping — the same subject appears in train and test',
    overview=('Splits are stratified by label but grouped by nothing, so a '
                "readmitted patient's admissions land on both sides of the split."),
    affects=('Every held-out number for both targets and both evaluation paths: '
               'Data/mimic-iii/*/{icu,mortality}_filter_impact_cv_diagnostics.json '
               '(raw ICU accuracy_mean 0.6936 ± 0.0025, raw mortality accuracy_mean '
               '0.6868), the corresponding *_filter_impact*.pkl, and '
               'paper_figures/filter_impact_*.pdf and mcnemar_icu_mean.pdf. The '
               'McNemar tests are also affected: leakage is not uniform across arms, '
               'since the record-dropping arms (31,029 / 20,323 / 1,369 of 46,032) '
               'thin readmission clusters unevenly.'),
    recompute=('Cannot be fixed in-tree from existing artifacts — '
                 '`processed_record_ehr.pkl` carries no `subject_id`, so the DB must '
                 'be re-queried. After that: rebuild the id sidecars, then re-run '
                 'the whole CV sweep (rerun/regen_filter_impact_cv.py for all '
                 'aggregations and both labels) and re-render paper_figures. The '
                 'legacy `evaluate_filter_impact` path needs the same treatment or '
                 'must be retired.'),
    technical=('`build_fold_assignment` (partition_manager.py:68-105) is the '
                 'single partition authority for the CV path; line 99 is '
                 '`splitter.split(admission_ids, labels)` — `StratifiedKFold.split` '
                 'accepts a third `groups` parameter which is ignored by that class, '
                 'and no grouped variant (`GroupKFold`, `StratifiedGroupKFold`) '
                 'appears anywhere in the toolbox. The module docstring at lines '
                 '20-21 states the stratification rationale and is silent on '
                 'grouping, so this is an omission rather than a documented '
                 'trade-off. The legacy path is worse: `evaluate_dataset_label` '
                 'calls `dataset.split(0.8, 0.1, 0.1)` (evaluation_manager.py:149), '
                 'which draws `torch.randperm(len(self))` (ehr_dataset.py:76) — '
                 'record-level, unseeded, ungrouped. The root cause is upstream: '
                 '`get_admission_ids` selects `DISTINCT hadm_id` only '
                 '(mimic-iii-processing.py:123), `RecordEHR` stores `admission_id` '
                 'alone (ehr_record.py:18-27), and a repo-wide grep for `subject_id` '
                 'excluding _deprecated returns hits only in the sibling '
                 'MIMIC_Extract pipeline and comparison/pipeline_comparison.ipynb — '
                 'nothing in EHR-Dataset-Processing. rerun/verify_cv.py checks id '
                 'uniqueness, ordered-subsequence structure, fold inheritance, '
                 'out-of-fold coverage, McNemar pairing, degenerate arms and a '
                 'shuffled-label probe, but has no check that a patient appears in '
                 'only one fold, so a green g_verify log says nothing about this.\n'
                 '\n'
                 'First-pass measurements retained: MIMIC-III holds ~46k admissions '
                 'across ~38k subjects, so roughly 7,500 admissions belong to '
                 'multi-admission patients.'),
    fix=('Add `a.subject_id` to the `get_admission_ids`/`get_mortality_labels` '
           "queries, carry it on `RecordEHR` and through `to_tensor`'s sidecar (the "
           'same way `regen_admission_ids.py` recovers `admission_id`), and switch '
           '`build_fold_assignment` to `StratifiedGroupKFold(n_splits, shuffle=True, '
           'random_state=PARTITION_SEED + repeat).split(admission_ids, labels, '
           'groups=subject_ids)`. `project_to_arm` needs no change, since arms '
           'inherit fold labels by id. Add a `verify_cv` check asserting '
           '`len(set(subject_ids[test]) & set(subject_ids[train])) == 0` for every '
           'fold of every repeat.'),
    verification=('Assert zero subject overlap between train and test for all 20 '
                    'folds, in verify_cv. Then quantify the old bias: score the raw '
                    'arm under both grouped and ungrouped partitions of the '
                    'identical cohort and report the accuracy delta; MIMIC-III has '
                    'roughly 59k admissions over 46.5k patients, so a non-trivial '
                    'drop is expected and its size is the number that belongs in the '
                    'paper.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C1',
        note=('Distinct from E-10 WONTFIX (that covers seeding/stratification, not '
             'grouping). Effect size unmeasured.'),
    ),
),
dict(
    id='I-03', stage=INGEST, severity=CRITICAL, status=OPEN, verified=True,
    name='The 24-hour window is anchored on hospital admission, not ICU admission',
    overview=('`hour` is computed as `charttime - admittime`, so hour 0 is '
                'hospital admission and a patient who spends 18 hours in the ED or '
                'on a ward before ICU transfer spends 18 of the 24 window hours '
                'before any ICU charting exists. Because MIMIC-III `chartevents` is '
                'sourced from the ICU information systems, those pre-ICU hours are '
                'not filled with ward data — they are empty, and the zero-fill in '
                '`to_tensor` turns them into 0.0. README.md:35 nonetheless describes '
                'the cohort as "the first 24 hours of each ICU stay", so the figures '
                'and the paper narrative describe a window the code does not produce.'),
    affects=('The observation-count heatmap '
               'paper_figures/observation_count_heatmap_raw_mimic_iii.pdf, whose '
               '"Hour" axis (render_paper_figures.py:288) is hospital-admission '
               'hours presented as an ICU trace; every accuracy/F1 number, because '
               'roughly the first two hours of features are mostly the zero '
               'sentinel; and any comparison against MIMIC_Extract in '
               'comparison/pipeline_comparison.ipynb, whose hour 0 is ICU `intime`.'),
    recompute=('Only if the anchor is changed. Doing so means re-running '
                 'Processing/mimic-iii-processing.py and the entire downstream chain '
                 '(filters, id sidecars, CV sweep, centroids, figures). If instead '
                 'only the documentation is corrected: nothing to recompute.'),
    technical=('The anchor is `a.admittime`, selected at '
                 'mimic-iii-processing.py:56 and differenced at line 79; '
                 '`icustays.intime` is read only inside `get_icu_labels` (line 140) '
                 'for the label and never used for windowing. The consequence is '
                 'measurable and was measured in the sibling experiment on these '
                 'same cached tensors: POSTMORTEM.md:131-132 reports the zero '
                 'fraction by hour as "0.709 at hour 0, 0.538 at hour 1, settling to '
                 '~0.34 mid-window", i.e. hour 0 is roughly twice as empty as a '
                 'mid-window hour. Combined with the zero-fill at ehr_record.py:42, '
                 'that gives a systematically degraded, regime-shifted prefix. The '
                 'code comment at lines 71-74 flags the choice honestly and '
                 'README.md:39 agrees with it ("the MIMIC scripts key on hospital '
                 'admission"), but README.md:35 — the file\'s headline description of '
                 'what the pipeline does — contradicts both. Correction to the claim '
                 'as filed: nothing in the window is "ward charting". `chartevents` '
                 'in MIMIC-III comes from CareVue and MetaVision, both ICU systems '
                 "(documented in this file's own comment at lines 27-29), so the "
                 'pre-ICU hours are empty rather than contaminated. The defect is a '
                 'sparse, mislabelled prefix, not the injection of non-ICU '
                 'measurements.\n'
                 '\n'
                 'First-pass measurements retained: Measured consequence, from '
                 'POSTMORTEM.md 2.5: 38.99% of all cells are exactly zero, rising to '
                 '0.709 at hour 0 — the window opens long before ICU monitoring '
                 'starts.'),
    fix=('Decide and make it consistent. Either join `icustays.intime` and anchor '
           '`hour` on the first ICU `intime` per admission (matching README.md:35 '
           'and MIMIC_Extract), or keep `admittime` and correct README.md:35 to say '
           '"the first 24 hours of each hospital admission", and relabel the heatmap '
           'axis in render_paper_figures.py:288 as "Hour since hospital admission". '
           'The first is the better science, since it is what makes the trace an ICU '
           'trace and removes the sparsest hours.'),
    verification=('If re-anchored: confirm the per-hour zero fraction is flat '
                    'rather than 0.709 at hour 0, and confirm hour-0 observation '
                    'counts in the rebuilt heatmap are comparable to mid-window '
                    'hours. Either way, grep README.md, notebook markdown and figure '
                    'captions for "ICU stay" and confirm each surviving use matches '
                    'the implemented anchor.'),
    found='POSTMORTEM.md 2.5, confirmed live 2026-08-11',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C1',
        note=('Correction: pre-ICU hours are EMPTY, not ward-contaminated '
             '(chartevents is ICU-sourced); defect is a mislabelled sparse prefix. '
             'Severity suggestion: High-not-Critical standalone.'),
    ),
),
dict(
    id='I-04', stage=INGEST, severity=CRITICAL, status=ARTIFACT, verified=True,
    name=('Claimed wrong-patient searchsorted id mapping in MIMIC-III processing '
            'does not exist'),
    overview=('The cited file contains no `np.searchsorted` and no '
                'index-arithmetic id lookup at all; it joins vitals to labels with '
                'exact pandas equality masks whose miss path is `IndexError`, which '
                'drops the admission rather than attributing it to a neighbour. The '
                'single `searchsorted` in the live tree (partition_manager.py:126) '
                'maps arms to pre-drawn fold labels, not readings to patients, and '
                'is explicitly guarded and regression-tested. No number, figure, or '
                'artifact is affected.'),
    affects=('Nothing. Data/mimic-iii/processed_record_ehr.pkl, the per-arm '
               '`*_admission_ids.npy` sidecars, the CV fold projections and all '
               'paper_figures/ are unaffected by this claim.'),
    recompute='Nothing',
    technical=('Exhaustive grep for `searchsorted` over '
                 '/home/ccampb47/work/clinical_preprocessing_toolbox (all '
                 '.py/.ipynb) yields exactly one live hit, '
                 'Managers/partition_manager.py:126; '
                 'Processing/mimic-iii-processing.py, '
                 'Processing/mimic-iv-processing.py and '
                 'Processing/eicu-processing.py have zero. `git log --all -S '
                 '"searchsorted"` over the repo returns no commits, so the construct '
                 'has never existed in any tracked revision either '
                 '(partition_manager.py is untracked and new). The actual '
                 'reading-to-patient join in Processing is per-admission-file: '
                 'mimic-iii-processing.py:243 parses `admission_id` from the feather '
                 "filename and :247-248 selects with `icu_labels['hadm_id'] == "
                 "admission_id` / `mortality_labels['hadm_id'] == admission_id`; an "
                 'absent id yields an empty frame, `.values[0]` raises IndexError, '
                 'and :250-251 routes the admission to `incomplete_data` — a drop, '
                 'never a neighbouring label. mimic-iv-processing.py:173-177 and '
                 'eicu-processing.py:183-187 are the same pattern. At '
                 'partition_manager.py:126 an absent arm id would indeed return an '
                 'insertion point, but :128-136 rejects it: every position is '
                 'bounds-checked (`np.any(position >= len(sorted_ids))`) and '
                 'value-checked against `sorted_ids[np.clip(...)] == '
                 'arm_admission_ids` before line 138 uses `raw_assignment[:, '
                 'order[position]]`, so a wrong-but-valid index can never be '
                 'consumed. The duplicate-raw-id case that could make the value '
                 'check pass on the wrong row is unreachable in the live flow: '
                 'evaluation_manager.py:667 calls `build_fold_assignment(raw_ids, '
                 'raw_labels)`, which raises at partition_manager.py:90-91 (`if '
                 'len(np.unique(admission_ids)) != len(admission_ids)`) before '
                 'evaluation_manager.py:675 passes the same `raw_ids` to '
                 '`project_to_arm`. The remaining id joins in the live tree are '
                 'dict/set based, not positional: evaluation_manager.py:570 pairs '
                 'arms via `np.intersect1d` plus `baseline_lookup`/`arm_lookup` '
                 'dicts, and ehr_dataset.py:130-134 length-checks the `.npy` id '
                 'sidecar against the dataset before attaching it.\n'
                 '\n'
                 'First-pass measurements retained: Found in hour_scaling_experiment '
                 'v3 (git 92e52d1): build_direct mapped ids with np.searchsorted, '
                 'which returns where a value *would* be inserted rather than '
                 'raising on absence. 7,047 readings whose hadm_id had no icustays '
                 'row would have been attributed to neighbouring patients.'),
    fix=('None required. If defensive hardening is wanted at all, the only '
           'candidate is adding a uniqueness assertion on `raw_admission_ids` inside '
           '`project_to_arm` itself so the guard does not depend on '
           '`build_fold_assignment` having been called on the same array — but that '
           'is redundant on every current call path.'),
    verification=('`grep -rn searchsorted` over the live tree returns only '
                    'partition_manager.py:126; `python '
                    'Managers/partition_manager.py` self-check prints PASS for '
                    '"projection rejects unknown ids" '
                    '(partition_manager.py:250-254); and a single-record probe of '
                    'mimic-iii-processing.py:247 with an id absent from icu_labels '
                    'raises IndexError rather than returning a value.'),
    found='2026-08-11 history sweep',
    audit=dict(
        date='2026-08-12', verdict='ARTIFACT', mode='cluster C1 + solo tie-breaker',
        note=('Escalated and independently confirmed ARTIFACT by a solo tie-breaker. '
             '`searchsorted` appears exactly once in the live toolbox '
             '(Managers/partition_manager.py:126), maps arms to fold labels rather '
             'than readings to patients, is bounds- and value-checked at :128-136 '
             'before use, and is regression-tested at :250-254; `git log --all -S '
             'searchsorted` finds no commit, so it never existed in Processing/. The '
             'real join in Processing/mimic-iii-processing.py:247 is an exact pandas '
             'equality mask whose miss path is IndexError -> `incomplete_data` (a '
             'drop, never a neighbour). Origin of the false claim identified: the '
             'wording is near-verbatim from the prior-art repo '
             '/home/ccampb47/work/hour_scaling_experiment/v3/{extract_duckdb.py:134-14'
             '0,build_features.py:151-161}, where the hazard was designed out and '
             'asserted against — the first pass transplanted that note onto a file '
             'that has no such code. Reclassification confirmed by an independent '
             'solo tie-breaker agent.'),
    ),
),
dict(
    id='I-05', stage=INGEST, severity=HIGH, status=OPEN, verified=True,
    name='Non-ICU admissions silently dropped; the icu label is not what it claims',
    overview=('`get_icu_labels` builds label rows only by grouping `icustays`, so '
                'an admission that never reached an ICU has no row; the label '
                "lookup's `.values[0]` then raises `IndexError` and the record is "
                'discarded into `incomplete_data`, which is never printed or '
                'persisted. The cohort is therefore conditioned on ICU admission, '
                'and the `icu` label separates long from short ICU stays *within* '
                'ICU patients rather than ICU from non-ICU care — which is not what '
                'README.md:37 advertises. The artifacts bear this out: all 46,032 '
                'records in raw_admission_ids.npy carry an ICU label, at 37.52% '
                'positive prevalence.'),
    affects=('The interpretation of every `icu`-target number rather than its '
               'arithmetic: Data/mimic-iii/*/icu_filter_impact_cv_diagnostics.json '
               '(raw accuracy_mean 0.6936, population_prevalence 0.3752), '
               'icu_filter_impact*.pkl, '
               'paper_figures/filter_impact_icu_testing_{accuracy,f1}_mean.pdf and '
               "mcnemar_icu_mean.pdf. It also affects the mortality target's "
               'generalisability claim, since 9.656% is in-hospital mortality among '
               'ICU admissions, not among all admissions. No cohort-size or '
               'exclusion count is reported anywhere on disk, so the drop is '
               'invisible to a reader.'),
    recompute=('Nothing, if the fix is to report the exclusion and rename the '
                 'target. If the intent was genuinely to include non-ICU admissions, '
                 'the whole chain must be re-run from '
                 'Processing/mimic-iii-processing.py.'),
    technical=("`get_icu_labels` iterates `icu_data.groupby('hadm_id')` over the "
                 'result of `SELECT hadm_id, intime, outtime FROM icustays` (lines '
                 '140-148) and appends exactly one row per `hadm_id` present there '
                 '(line 161), so non-ICU admissions are absent from `icu_labels` by '
                 'construction — never labelled 0. At lines 247-248 both labels are '
                 'fetched with `.values[0][1]`, which raises `IndexError` when the '
                 'mask matches nothing; the handler at 250-251 appends to '
                 '`incomplete_data`, and grep shows `incomplete_data` is written at '
                 'line 241 and 251 and read nowhere — no count, no print, no '
                 'sidecar. Corrections to the claim as filed: (1) it is not a bare '
                 '`except` — it is a narrowly typed `except IndexError`, which is '
                 'better practice than the claim implies, and the defect is the '
                 'silence, not the breadth; (2) the same handler also swallows a '
                 'missing *mortality* row, conflating two different exclusions under '
                 'one counter; (3) the practical magnitude is much smaller than '
                 '"every admission that never reached an ICU", because MIMIC-III '
                 '`chartevents` is sourced from the two ICU charting systems (this '
                 "file's own comment, lines 27-29), so few non-ICU admissions have "
                 'any of these seven vitals to begin with and thus few reach the '
                 'loop — the cohort would be near-ICU-only even with a correct outer '
                 'join; (4) the drop itself is documented at lines 237-239, which '
                 'explicitly names "absent from icustays". What is not documented is '
                 'the consequence for label semantics, and README.md:37 still calls '
                 'the target "ICU stay > 3 days" unqualified.'),
    fix=('Two changes, both small. In `get_icu_labels`, left-join against the full '
           'admission list and label non-ICU admissions `0` explicitly (or, if '
           'ICU-only is the intended cohort, filter on `icustays` up front and say '
           'so). In `__main__`, print and persist `len(incomplete_data)` split by '
           'which lookup failed, so the exclusion appears in the run log. Then '
           'rename the target in README.md:37 and the figure titles to "ICU stay > 3 '
           'days (among ICU admissions)".'),
    verification=('Compare `len(records)` against the number of '
                    '`timeseries/*.feather` files and against `SELECT count(distinct '
                    'hadm_id) FROM admissions`; assert the three agree up to the '
                    'reported, non-zero exclusion count. Confirm the printed '
                    'exclusion count matches `count(distinct ce.hadm_id) FROM '
                    'chartevents ce LEFT JOIN icustays i USING (hadm_id) WHERE '
                    'i.hadm_id IS NULL` for the seven item-ID sets.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C1',
        note=('Corrections: except is typed IndexError (defect is the silence); drop '
             'documented at :237-239 but label semantics not; magnitude smaller than '
             'claimed (chartevents is ICU-sourced). Severity suggestion: Medium.'),
    ),
),
dict(
    id='I-06', stage=INGEST, severity=HIGH, status=OPEN, verified=True,
    name='No age filter — neonates are in the cohort',
    overview=('`fetch_all_timeseries` joins only `chartevents` to `admissions`; '
                'the `patients` table is never touched, so no age is ever computed '
                'and no age predicate can exist. Every hospital admission with at '
                'least one of the seven vitals charted in hours 0-23 becomes a '
                'record, including neonatal (NICU) admissions and admissions with no '
                'ICU stay at all, and the plausible-range bounds are so wide (HR '
                '1-599, RR 1-69) that neonatal physiology passes untouched. The '
                'result is a mixed-physiology cohort of 44,087 records analysed as '
                'if it were one population.'),
    affects=('`Data/mimic-iii/processed_record_ehr.pkl` (44,087 records) and every '
               'artifact derived from it: '
               '`Data/mimic-iii/<aggregation>/*_filtered_dataset_ehr.pkl`, the '
               'centroid caches under `Data/mimic-iii/mean/centroids/`, '
               '`icu_filter_impact*.pkl`, and the centroid/ECDF/observation-count '
               'figures in `paper_figures/` (e.g. '
               '`centroid_density_raw_mimic_iii.pdf`, '
               '`ecdf_fill_missing_data_mean_*.pdf`). Centroid-shift interpretation '
               'is the most damaged output: a filter that preferentially removes '
               'sparsely-charted neonates moves the centroid for a demographic '
               'reason that the plots read as "the hard cases got thrown out". Any '
               'comparison against MIMIC_Extract '
               '(`comparison/pipeline_comparison.ipynb`) is cohort-mismatched, since '
               'MIMIC_Extract defaults to `min_age=15`.'),
    recompute=("Everything. `Processing/mimic-iii-processing.py` (it rmtree's "
                 '`Data/mimic-iii`), then `Experiments/apply_dataset_filter.py` per '
                 'aggregation, then filter impact (legacy and CV), centroids, '
                 'confusion matrices, and all `paper_figures/`.'),
    technical=('The cohort is defined implicitly in two places, neither of which '
                 'can express an age constraint. First the query at '
                 '`Processing/mimic-iii-processing.py:55-61` selects rows for the '
                 'seven vital item sets with only `error IS NULL OR error = 0`; '
                 'second, records are enumerated from the filesystem at '
                 '`Processing/mimic-iii-processing.py:242` (`for item in '
                 "tqdm(os.listdir(... 'timeseries'))`), and the only exclusion "
                 'applied is the `except IndexError` at `:250-251`, which drops '
                 'admissions with no row in `icustays`/`admissions` — note that this '
                 'does *not* drop non-ICU admissions, because `get_mortality_labels` '
                 'covers all admissions and the ICU lookup at `:247` succeeds for '
                 'any hadm present in `icu_labels`. Downstream, `_remove_outliers` '
                 '(`Managers/ehr_filter_manager.py:32-77`) prunes values, not '
                 'records, using the bounds in '
                 '`Experiments/apply_dataset_filter.py:26-34`; neonatal HR (120-180) '
                 'and BP are inside those bounds, so no value-level filter removes a '
                 'neonate. The sample-level filters described at '
                 '`/home/ccampb47/work/noahNotes.md:428` (10+ consecutive missing '
                 'cells in any column) will drop many sparsely-charted neonates, but '
                 'only in those arms — so cohort composition differs between arms '
                 'that are being compared to each other.\n'
                 '\n'
                 'First-pass measurements retained: The patients table is never '
                 'joined, so roughly 7,800 neonatal admissions sit in the cohort '
                 'with vitals no filter removes. Neonatal vitals (HR 120-160, RR '
                 '40-60, SBP 60-70) sit comfortably inside every VITALS range, so no '
                 'outlier filter removes them, and they are overwhelmingly icu=0 / '
                 'mortality=0.'),
    fix=('Join `patients` on `subject_id` in the query (or a second query), '
           "compute admission age as `admittime - dob` with MIMIC-III's date-shift "
           'caveat for ages >89, and filter to a stated range (`>= 15` to match '
           'MIMIC_Extract, or `>= 18`); restrict the cohort to admissions present in '
           '`icustays` if the README\'s "each ICU stay" framing is the intent. Record '
           'the chosen bounds in the module docstring and README so the cohort claim '
           'is checkable.'),
    verification=('After the re-run, `len(records)` should drop by the number of '
                    'excluded admissions; assert `min(age) >= threshold` over the '
                    'cohort before pickling, and cross-check the count of removed '
                    'hadm_ids against `SELECT count(DISTINCT hadm_id) FROM '
                    "admissions WHERE admission_type = 'NEWBORN'`. Then confirm the "
                    'raw-cohort respiration-rate/heart-rate density in '
                    '`centroid_density_raw_mimic_iii_full_range.pdf` loses its '
                    'high-rate mode.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C2',
        note=('~7,800 neonatal count unverifiable from disk (treat as estimate); '
             'cohort also includes never-ICU admissions.'),
    ),
),
dict(
    id='I-07', stage=INGEST, severity=HIGH, status=OPEN, verified=True,
    name='A NULL ICU outtime silently produces a negative label',
    overview=('If any ICU stay has an unknown discharge time the summed duration '
                'becomes NaN, and NaN > 3 is False — so the longest stays are '
                'labelled short.'),
    affects=('The `icu_label` column of `Data/mimic-iii/icu_labels.feather` and '
               'the `icu` field of every `RecordEHR` in '
               '`Data/mimic-iii/processed_record_ehr.pkl`; from there every '
               'ICU-target result — `Data/mimic-iii/<agg>/icu_filter_impact.pkl`, '
               '`icu_filter_impact_cv.pkl`, `icu_oof_scores_cv.npz`, and '
               '`paper_figures/filter_impact_icu_testing_accuracy_mean.pdf`, '
               '`filter_impact_icu_testing_f1_mean.pdf`, `mcnemar_icu_mean.pdf`. The '
               'errors are one-directional (true positives flipped to negatives), so '
               'they depress ICU recall and shift the ICU-positive centroid toward '
               'the short-stay population.'),
    recompute=('If any NULL `outtime` rows exist: re-run '
                 '`Processing/mimic-iii-processing.py` and everything downstream '
                 '(filtered datasets, filter impact legacy + CV, centroids, ICU '
                 'figures). If the DB has zero NULL `outtime` rows, nothing needs '
                 'recomputing and the fix is purely defensive.'),
    technical=('`Processing/mimic-iii-processing.py:140-144` reads `hadm_id, '
                 'intime, outtime` and coerces both timestamps with '
                 '`pd.to_datetime`, which maps SQL NULL to `NaT`. In the '
                 'per-admission merge walk, `current_end` is seeded from row 0 at '
                 "`:151`; if that row's `outtime` is NaT, the overlap test at `:154` "
                 '(`start <= current_end`) is False for every subsequent stay, so '
                 'control always takes the `else` branch at `:157`, which adds `(NaT '
                 '- current_start).total_seconds()/(24*3600)` — I verified '
                 '`pd.NaT.total_seconds()` returns `nan`, so `total_days` becomes '
                 '`nan` and stays `nan` through all further additions including the '
                 'final one at `:159`. The label expression at `:161`, '
                 '`int(total_days > 3)`, evaluates `nan > 3` as False and emits 0. '
                 'Nothing logs or counts these admissions, and the docstring at '
                 '`:127-139` documents the merge and the 3-day summed threshold but '
                 'never mentions missing timestamps. The MIMIC-IV sibling at '
                 '`Processing/mimic-iv-processing.py:98` uses `.sum()`, whose '
                 'default `skipna=True` drops the NaN term instead of propagating it '
                 '— so the same input produces label 1 there and label 0 here, which '
                 'is an unintended cross-dataset inconsistency on top of the wrong '
                 'label.'),
    fix=('Before the loop, partition the group: drop (and count) rows with '
           "`outtime` or `intime` null, or impute `outtime` with the admission's "
           '`dischtime`. If any rows are dropped, emit them to a sidecar count '
           'rather than silently; and guard the final label so an all-null admission '
           'yields `None`/excluded rather than 0 — e.g. `if pd.isna(total_days): '
           'continue` with the hadm_id recorded, letting the existing `except '
           'IndexError` at `:250` drop the record.'),
    verification=('Run `SELECT count(*) FROM mimiciii.icustays WHERE outtime IS '
                    'NULL OR intime IS NULL;` to establish incidence. Add an '
                    "assertion that `icu_labels['icu_label']` is computed from a "
                    'non-NaN `total_days` for every row, and diff the new '
                    '`icu_labels.feather` against the current one — every changed '
                    'row should belong to an admission containing a null-timestamp '
                    'stay. Unit-test the two-stay case above and assert label 1.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C2',
        note=('Mechanism reproduced in-memory (NaT.total_seconds()=nan; '
             'int(nan>3)=0); incidence unverified without DB. MIMIC-IV sibling uses '
             '.sum(skipna=True) so labels diverge cross-dataset.'),
    ),
),
dict(
    id='I-08', stage=INGEST, severity=HIGH, status=OPEN, verified=True,
    name='NULL valuenum rows are pulled for MIMIC-III but filtered for MIMIC-IV',
    overview=('The MIMIC-III query has no `valuenum IS NOT NULL` predicate, so '
                'rows whose charted `value` is non-numeric text are pulled with a '
                'NULL `valuenum`; psycopg2 returns `None`, but the DataFrame '
                'constructor types the column `float64` and converts it to `nan`, so '
                "the per-hour list built by `.agg(list)` contains NaN. `aggregate`'s "
                'guard at `ehr_filter_manager.py:381` tests `v is not None`, which '
                'NaN passes, so `np.mean` over that hour returns NaN and one '
                'non-numeric row erases every real measurement charted in that hour. '
                'Worse, the seven value-level range filters *do* strip NaN (`not (1 '
                '<= nan <= 599)` is True), so the NaN contamination exists in the '
                'baseline arm but is silently cleaned in the filter arms it is '
                'compared against.'),
    affects=('The raw/unfiltered MIMIC-III arm and therefore the measured impact '
               'of every per-vital filter: '
               '`Data/mimic-iii/mean/*_filtered_dataset_ehr.pkl` and the raw dataset '
               'cache, `icu_filter_impact*.pkl` / `mortality_filter_impact*.pkl` '
               '(both legacy and CV), and `paper_figures/filter_impact_*`, '
               '`mcnemar_*`, `centroid_deviation_*`, `ecdf_fill_missing_data_*`. '
               "Part of each range filter's apparent accuracy gain and centroid "
               'shift is NULL removal rather than outlier removal — the filter under '
               'test is confounded with the ingest defect. Counts reported by `fill '
               'missing data` (which sees NaN as missing) and by `high invalid data` '
               '(which counts NaN as invalid, and can drop whole records) are '
               'inflated for the baseline. MIMIC-IV is unaffected; eICU shares the '
               'defect.'),
    recompute=('`Processing/mimic-iii-processing.py` (adding the predicate changes '
                 'the pickle), then all `Experiments/apply_dataset_filter.py` '
                 'caches, filter impact legacy + CV, centroids, confusion matrices, '
                 'and every affected figure.'),
    technical=('`Processing/mimic-iii-processing.py:55-61` filters only on '
                 '`itemid` and the `error` column; MIMIC-III `chartevents` rows with '
                 'text values (e.g. an unobtainable BP) carry a populated `value` '
                 'and NULL `valuenum`. At `:67` `pd.DataFrame(rows, columns=[...])` '
                 'infers `float64` for the mixed float/None column, mapping None to '
                 'NaN — I verified this and the surviving-NaN path in pandas 3.0.0. '
                 "`:79-80` keeps the row (hour arithmetic is unaffected), `:92`'s "
                 "Fahrenheit conversion propagates NaN, and `:107`'s "
                 '`groupby(...).agg(list)` embeds it in the cell list. I confirmed '
                 'the list-with-NaN survives `matrix.reindex(index=range(24), '
                 'columns=..., fill_value=[])` at `:116` intact, so it reaches the '
                 'feather at `:217` and the pickle at `:262`. In '
                 '`Managers/ehr_filter_manager.py:378-382`, the '
                 '`isinstance(cell_value, list)` branch is taken, `len(cell_value) > '
                 '0` is True, the `is not None` filter at `:381` retains the NaN, '
                 'and `float(np.mean([80.0, nan]))` is NaN — the hour is lost, not '
                 'just the bad reading. Meanwhile `_remove_outliers` at `:58-62` '
                 'pops the NaN because `not (inclusive_range[0] <= nan <= '
                 'inclusive_range[1])` is True, and it charges the removal to that '
                 "filter's `value_level` change counter at `:63/:74`, so the change "
                 'tracker attributes NULL cleanup to the range filter.'),
    fix=('Two changes. (1) Add `AND ce.valuenum IS NOT NULL` to the MIMIC-III '
           'query at `Processing/mimic-iii-processing.py:59-60` (keeping the `error` '
           "clause) and the equivalent to `Processing/eicu-processing.py`'s "
           '`vitalperiodic` select, so all three datasets share the step. (2) '
           'Independently harden `Managers/ehr_filter_manager.py:381` to `[v for v '
           'in cell_value if v is not None and not (isinstance(v, float) and '
           'math.isnan(v))]` — equivalently `np.isfinite` — so a future NaN cannot '
           'erase an hour. Note the cache is not invalidated automatically '
           '(`README.md:79`), so `Data/mimic-iii/` must be deleted by hand.'),
    verification=('After re-running ingest, assert no cell list in '
                    '`processed_record_ehr.pkl` contains a non-finite value, and '
                    'record the row count difference the new predicate causes. '
                    'Compare per-arm NaN density in the aggregated raw dataset '
                    "before/after: the baseline's NaN count should fall to the level "
                    "of the range-filter arms, and each range filter's reported "
                    '`value_level` change count should drop by the number of NULL '
                    'rows it had been removing. Then re-diff `filter_impact_*` '
                    'accuracy against the current values — any range filter whose '
                    'apparent gain disappears was measuring NULL removal.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C2',
        note=('Correction: NULLs arrive as float NaN (not None), which is exactly why '
             'the `is not None` guard misses them; eICU shares the defect, only '
             'MIMIC-IV filters. noahNotes:296 flags cross-dataset consistency as '
             'VERY IMPORTANT.'),
    ),
),
dict(
    id='I-09', stage=INGEST, severity=LOW, status=OPEN, verified=True,
    name='A NULL charttime crashes the last step of the extraction',
    overview=('`fetch_all_timeseries` computes the hour bin as `(charttime - '
                'admittime).dt.total_seconds() // 3600` and casts straight to `int`, '
                'with no `dropna`/`notna` guard and no filtering of NULL `charttime` '
                'in the SQL. A single NULL `charttime` (or NULL `admittime`) yields '
                'NaT, hence NaN, and pandas 2.3.3 raises `IntCastingNaNError: Cannot '
                'convert non-finite values (NA or inf) to integer`, so the cast '
                'takes down the entire extraction rather than dropping the one '
                'unusable row. The out-of-range filter on the next line would have '
                'discarded such rows harmlessly had the cast been deferred.'),
    affects=('No current artifact is wrong. '
               '`Data/mimic-iii/processed_record_ehr.pkl`, `icu_labels.feather` and '
               '`mortality_labels.feather` (all dated Feb 17) exist, so the '
               'extraction completed against the local MIMIC-III instance — i.e. '
               'that instance contained no NULL `charttime` among the queried '
               'itemids. This is a latent robustness/portability defect: it would '
               'abort a re-extraction against a MIMIC build or a MIMIC-IV/derivative '
               'source that permits NULL `charttime`, and it aborts *before* '
               'anything is written, so nothing partial is salvageable.'),
    recompute=('Nothing. No downstream number depends on the fix; only re-run '
                 '`Processing/mimic-iii-processing.py` (and '
                 '`mimic-iv-processing.py`) if a full re-extraction is being done '
                 'anyway — and note that script deletes `Data/mimic-iii/` wholesale '
                 '(lines 211-212), destroying the cached aggregations and centroids.'),
    technical=('`Processing/mimic-iii-processing.py:55-61` selects `ce.charttime` '
                 'with no NULL predicate — the only WHERE clause is on `itemid` and '
                 'the `error` column. `:68-69` coerce both columns with '
                 '`pd.to_datetime`, which maps NULL to NaT rather than raising. At '
                 '`:79` the timedelta subtraction propagates NaT, '
                 '`.dt.total_seconds()` turns it into NaN, `NaN // 3600` stays NaN, '
                 'and `.astype(int)` on a float64 Series containing NaN raises under '
                 'pandas 2.x (`requirements.txt:4` pins `pandas==2.3.3`). The '
                 'subsequent range mask at `:80` (`hour >= 0 & hour < 24`) would '
                 'have silently excluded the NaN row, so the cast is simply ordered '
                 'wrongly. Two corrections to the claim as filed: (a) the failure is '
                 'not in "the last step of the extraction" — '
                 '`fetch_all_timeseries()` is the *first* thing `__main__` calls '
                 '(`:189`), before labels, feather writes or pickling, so the crash '
                 'discards the entire ~330M-row query result; (b) the identical '
                 'unguarded cast exists at `Processing/mimic-iv-processing.py:60`, '
                 'which the claim does not cite, and that query (`:43-49`) also has '
                 'no `charttime IS NOT NULL` predicate even though it does filter '
                 '`valuenum IS NOT NULL`. `Processing/eicu-processing.py:69` uses '
                 '`(observationoffset // 60).astype(int)` and is exposed to the same '
                 'failure mode from a NULL offset. I could not verify from anything '
                 'on disk whether the mimic-code Postgres DDL used by '
                 '`Docker/initialize_mimic-iii.sh:4` declares `chartevents.charttime '
                 'NOT NULL`; if it does, the crash is unreachable for this specific '
                 'source, which is why I rate this latent rather than active.'),
    fix=('Do the arithmetic in float, filter, then cast: compute `hours = '
           "(dataframe['charttime'] - dataframe['admittime']).dt.total_seconds() // "
           '3600`, apply `dataframe = dataframe[hours.between(0, 23)]` (NaN is '
           'excluded automatically since NaN comparisons are False), and only then '
           '`.astype(int)`. Equivalently add `AND ce.charttime IS NOT NULL` to the '
           'SQL at `mimic-iii-processing.py:59` / `mimic-iv-processing.py:47`. Apply '
           'the same reordering at `mimic-iv-processing.py:60` and '
           '`eicu-processing.py:69`, and log the dropped-row count so a silently '
           'NULL-heavy source is visible rather than invisible.'),
    verification=('In a scratch session, build a small DataFrame with one NaT '
                    '`charttime` row plus normal rows and run the current expression '
                    '— it should raise `IntCastingNaNError` — then run the reordered '
                    'expression and confirm it returns the normal rows with the NaT '
                    'row dropped and dtype `int64`. Against the database, `SELECT '
                    'count(*) FROM mimiciii.chartevents WHERE charttime IS NULL AND '
                    'itemid IN (...)` establishes whether the trigger is reachable '
                    'at all for this build; a non-zero count would upgrade this from '
                    'latent to active.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='solo pilot',
        note=('Corrections: crash is in the FIRST step of extraction '
             '(fetch_all_timeseries), not the last; same unguarded cast in '
             'mimic-iv-processing.py:60 and eICU equivalent.'),
    ),
),
dict(
    id='I-10', stage=INGEST, severity=LOW, status=OPEN, verified=True,
    name='get_admission_ids() is dead code implying the wrong cohort source',
    overview=('A function that looks like it defines the cohort is never called; '
                'os.listdir on the timeseries directory actually does.'),
    affects=('No numbers or figures are wrong from this alone. It affects '
               'documentation accuracy and audit cost: `README.md:47` points '
               'newcomers at this file as the authoritative record of "every '
               'cohort/label decision baked into it", and this dead function '
               'actively misdescribes that decision. It is also the reason '
               'cohort-scope defects like I-06 are easy to miss.'),
    recompute='Nothing.',
    technical=('The function is defined at '
                 '`Processing/mimic-iii-processing.py:122-124`, between '
                 '`build_vitals_timeseries` and `get_icu_labels`, with no docstring; '
                 'the `__main__` block at `:180-273` calls `fetch_all_timeseries`, '
                 '`build_vitals_timeseries`, `get_icu_labels` and '
                 '`get_mortality_labels` only. Cohort membership is instead set by '
                 'two side effects: which `hadm_id` keys survive '
                 '`build_vitals_timeseries` (i.e. appear in the filtered query '
                 'result at `:80`, `hour >= 0 and hour < 24`) and are written as '
                 'feathers at `:216-217`, and then the directory scan at `:242` '
                 'combined with the `except IndexError: '
                 'incomplete_data.append(admission_id)` fallback at `:250-251`. '
                 'Because the enumeration is a directory listing rather than a '
                 'query, a stale file in `Data/mimic-iii/timeseries` would silently '
                 'rejoin the cohort — the `shutil.rmtree` at `:211-212` is the only '
                 'thing preventing that, and its comment at `:206-210` shows the '
                 'author was aware of the coupling. The identical structure in the '
                 'MIMIC-IV script contains a related no-op: the `valid_stays` '
                 'restriction at `mimic-iv-processing.py:149-150` filters the '
                 'in-memory `timeseries` dict *after* the feathers were already '
                 'written at `:143-144`, and records are then rebuilt from '
                 '`os.listdir` at `:168`, so the restriction only affects the '
                 'example printout at `:196` — the same "cohort is the directory" '
                 'confusion in a form that looks like a real filter.'),
    fix=('Delete `get_admission_ids()` from `Processing/mimic-iii-processing.py`. '
           'If an explicit cohort source is wanted instead, make it real: build the '
           'record loop from an explicit `sorted(timeseries.keys())` (or a queried '
           'id list intersected with the label tables) rather than `os.listdir`, and '
           'log `len(incomplete_data)`, which is currently collected at `:251` and '
           'never reported. Either way state the actual cohort rule in the module '
           'docstring.'),
    verification=('`grep -rn get_admission_ids` should return only the eICU '
                    'definition and its two call sites. If the loop is changed to an '
                    'explicit id list, a re-run must produce exactly the same record '
                    'count (44,087) and the same set of `admission_id`s as the '
                    'current pickle, proving the refactor is behaviour-preserving; '
                    '`len(incomplete_data)` should be printed and expected to be 0 '
                    'for a clean run.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C2',
        note=('MIMIC-IV valid_stays restriction is a related no-op (filters after '
             'feathers written).'),
    ),
),

# ── Filter / aggregate ────────────────────────────────────────────────────────
dict(
    id='F-01', stage=FILTER, severity=CRITICAL, status=OPEN, verified=True,
    name='Zero-as-missing collides with the deviation aggregations',
    overview=('`aggregate` (ehr_filter_manager.py:361-368) produces exactly 0.0 '
                'for any hour whose readings have no spread — a single charted '
                'reading, or several identical ones — under all three deviation '
                'aggregations, and 0.0 is the *correct* answer there. The three '
                'post-aggregate structural filters then treat any 0 as a gap '
                '(`df.isna() | (df == 0)`, lines 189/238/277), so those legitimate '
                'cells are counted as missing. Under `standard deviation` / `mean '
                'deviation` / `maximum deviation` this drives `high invalid data` to '
                'zero surviving records and the two gap filters to well under 1% of '
                'the cohort.'),
    affects=('The nine cached artifacts `Data/mimic-iii/{standard deviation,mean '
               'deviation,maximum '
               'deviation}/{high_invalid_data,long_gap,long_missing_segment}_filtered_'
               'dataset_ehr.pkl` (+ the matching `_admission_ids.npy` and '
               '`Logs/.../*_filter_log.json`) hold near-empty cohorts: against a raw '
               'cohort of 46,032 (`.../mean/fill_missing_data_admission_ids.npy` → '
               '`shape: (46032,)`), the deviation arms retain 0 / 251 / 367 records '
               'where `mean` retains 1,369 / 20,323 / 31,029. Every downstream '
               'number for those arms is therefore wrong or absent: the `high '
               'invalid data` entry in all four deviation-aggregation '
               '`icu_filter_impact_cv_diagnostics.json` files is `NaN` with '
               '`"coverage": 0.0`, and `long gap` / `long missing segment` '
               'accuracies there (0.568, 0.598 for std-dev ICU) are computed on 251 '
               'and 367 patients — noise, not a filter-impact measurement. '
               '`paper_figures/` is not currently contaminated: every file there is '
               '`_mean` or `_raw`, so the published figures use the two aggregations '
               'where the collision does not fire.'),
    recompute=('Delete and rebuild `Data/mimic-iii/{standard deviation,mean '
                 'deviation,maximum '
                 'deviation}/{high_invalid_data,long_gap,long_missing_segment}_filtere'
                 'd_dataset_ehr.pkl` plus their `_admission_ids.npy` and `Logs/` '
                 'JSONs (`Experiments/apply_dataset_filter.py mimic-iii '
                 '"<aggregation>"` after removing the stale caches — README:79 notes '
                 'nothing invalidates them), then re-run filter impact for those '
                 'three aggregations on both evaluation paths and any centroid '
                 'artifacts under those directories. Nothing needs recomputing for '
                 '`mean` or `median`, and no current `paper_figures/` output changes.'),
    technical=('`aggregate_filter` is called with the aggregation method before '
                 'the structural filters run (`Managers/dataset_manager.py:96-97`: '
                 '`filtered_records = aggregate_filter(records, aggregation_method)` '
                 'then `filter_function(filtered_records, vitals)`), with the '
                 'pre/post boundary set positionally by `pre_aggregate = True if k < '
                 '7 else False` (`Experiments/apply_dataset_filter.py`). So filters '
                 '9-11 always see scalars produced by the ops dict at '
                 '`ehr_filter_manager.py:361-367`. For a cell list of length 1, '
                 '`np.std([v]) == 0.0` and both deviation lambdas reduce to `|v - v| '
                 '== 0.0`; the same holds for any constant list. '
                 '`long_missing_segment_filter:189`, `long_gap_filter:238` and '
                 '`high_invalid_data_filter:277` OR that 0.0 into their missingness '
                 'mask, so a densely charted hour with one reading per vital looks '
                 'like a blank hour. With a 24x7 grid and a 10% threshold '
                 '(`high_invalid_data_filter`, ~17 cells), essentially every record '
                 'trips it: the cached `high_invalid_data_admission_ids.npy` for all '
                 'three deviation aggregations has `shape: (0,)` and the CV '
                 'diagnostics record `"n_records": 0, "n_folds_fitted": 0, '
                 '"degenerate": true`. Note filter 8, `fill_missing_data_filter`, is '
                 '*not* affected — it masks with `np.isnan` only (lines 129/132) — '
                 'and indeed its cache is byte-identical in size (368,384 = 46,032 '
                 'int64 ids) across all five aggregations. The docstring at :165-168 '
                 '("Zero counts as missing throughout. Not strictly true … but a '
                 'charted 0 in this data is overwhelmingly a placeholder") documents '
                 'the convention only for raw charted values; it says nothing about '
                 "aggregation-produced zeros, and the module docstring's claim that "
                 'the structural filters "only make sense on an already-aggregated '
                 'record" (:8-10) is exactly the configuration in which the '
                 'convention breaks. Adjacent, same convention, separate site: '
                 '`Managers/evaluation_manager.py:737` `invalid = '
                 'torch.isnan(tensor) | (tensor == 0)` in `compute_tensor_centroid`, '
                 'which would likewise drop true zero-deviation hours from centroids '
                 'under these aggregations (`Data/mimic-iii/*/centroids/` exists for '
                 'all five).\n'
                 '\n'
                 'First-pass measurements retained: Measured record counts (verified '
                 'from the diagnostics sidecars):\n'
                 '  long missing segment   mean 31,029  median 31,028  deviations 367\n'
                 '  long gap               mean 20,323  median 20,323  deviations 251\n'
                 '  high invalid data      mean  1,369  median  1,365  deviations   0'),
    fix=('Stop inferring missingness from the value. Make the aggregation step '
           'emit an explicit validity mask (or keep the per-cell observation count '
           'already visualised by the N-distribution work) and have '
           '`long_missing_segment_filter`, `long_gap_filter` and '
           '`high_invalid_data_filter` test that mask instead of `== 0`. Minimal '
           'alternative if a mask is too invasive: give the three filters a '
           '`zero_is_missing: bool` parameter defaulted from the aggregation method '
           '— `True` for `mean`/`median`, `False` for the three deviation methods — '
           'and thread the aggregation name through `create_filter_dataset`. Either '
           'way the caches for the deviation aggregations must be deleted, since '
           'nothing invalidates them.'),
    verification=('After the fix, rebuild the three deviation-aggregation caches '
                    'and assert the surviving record counts are within a plausible '
                    'band of the `mean` arm rather than collapsed — concretely, '
                    '`high_invalid_data_admission_ids.npy` shape must be nonzero '
                    "(order 10^3, comparable to `mean`'s 1,369), and `long_gap` / "
                    '`long_missing_segment` order 10^4 rather than 251 / 367. Then '
                    'confirm no `"degenerate": true` / `"coverage": 0.0` / `NaN` '
                    'entries remain for `high invalid data` in '
                    '`Data/mimic-iii/{standard deviation,mean deviation,maximum '
                    'deviation}/*_filter_impact*_diagnostics.json`. A targeted unit '
                    'check is also cheap: build a record whose every cell is a '
                    'one-element list, aggregate with `"standard deviation"`, and '
                    'assert `high_invalid_data_filter` keeps it.'),
    found='2026-08-11 session; counts verified from the sidecars',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='solo pilot',
        note=('Counts re-verified independently from npy headers/diagnostics: '
             'deviations keep 0 / 251 / 367 of 46,032. fill_missing_data_filter is '
             'NOT affected (isnan-only). Trigger includes identical-readings hours, '
             'not just single-reading.'),
    ),
),
dict(
    id='F-02', stage=FILTER, severity=HIGH, status=OPEN, verified=True,
    name='Every SpO2 reading of 100% is deleted as an outlier',
    overview=('`_remove_outliers` keeps a value only when `lo <= v <= hi`, and the '
                'live VITALS tables give oxygen saturation an upper bound of 99, so '
                'a perfectly normal (and in MIMIC, modal) SpO2 of 100 is discarded '
                'as a charting error. The same off-by-one applies to all seven '
                'vitals (599/399/299/299/69/49 against a documented '
                '600/400/300/300/70/100 and a 60 °C temperature ceiling), so each '
                'filter also silently rejects its own documented maximum. Deleting '
                'the most common SpO2 value removes real measurements and empties '
                'hours, which then cascades into the structural filters and the '
                'zero-fill in `to_tensor`.'),
    affects=('The `oxygen saturation` and `all vitals` arms in every aggregation: '
               'Data/mimic-iii/*/oxygen_saturation_filtered_dataset_ehr.pkl, '
               'all_vitals_filtered_dataset_ehr.pkl, their centroids under '
               'Data/mimic-iii/*/centroids/, and the CV/legacy filter-impact results '
               '(icu/mortality accuracy_mean 0.6855/0.6828 for oxygen saturation vs '
               '0.6936/0.6868 raw). Figure-side: '
               'paper_figures/filter_impact_*_mean.pdf, mcnemar_icu_mean.pdf, '
               'centroid_deviation_all_vitals_filter_mean.pdf, and the gallery '
               'render (render_marimo_mimic_iii.py:115 carries the same 99). The '
               'centroid evidence quantifies it: SpO2 centroid falls 4.4 points for '
               'the ICU-positive cohort while no other vital moves.'),
    recompute=('Everything downstream of the vital ranges: re-run '
                 'Experiments/apply_dataset_filter.py per aggregation after deleting '
                 'the cached oxygen_saturation/all_vitals pickles (nothing '
                 'invalidates the cache — README.md:79), then centroids, '
                 'admission-id sidecars, filter-impact (legacy and CV) and all paper '
                 'figures/gallery.'),
    technical=('Managers/ehr_filter_manager.py:61 uses a closed interval, and '
                 "Managers/ehr_filter_manager.py:102 passes `vitals['oxygen "
                 "saturation'][0]`. The live suppliers of that tuple are "
                 'Experiments/apply_dataset_filter.py:33, '
                 'Experiments/notebook.py:225, rerun/_common.py:50 and '
                 'gallery/render_marimo_mimic_iii.py:115 — all `(1, 99)`. '
                 'noahNotes.md:400-407 documents min 1 / max 100 (and temperature '
                 'max 60), so code and documented intent disagree. The bound also '
                 "propagates into fill_missing_data_filter's validity guard "
                 '(ehr_filter_manager.py:130), where an all-100% SpO2 trace '
                 'contributes zero "known" values and is skipped. Two of the cited '
                 'files do not exhibit the bug: '
                 'Experiments/fill_missing_data_analysis.py:150 and '
                 'Experiments/render_paper_figures.py:88 both use `(1, 100)`; in '
                 'render_paper_figures VITALS is only consumed for names/units '
                 '(lines 90-91), so its ranges are inert.'),
    fix=('Raise the seven upper bounds to the documented values (100 for SpO2, '
           '600/400/300/300/70, and settle temperature at 50 or 60) in '
           'apply_dataset_filter.py:26-34, notebook.py:219-226, '
           'rerun/_common.py:43-51 and gallery/render_marimo_mimic_iii.py:108-115 — '
           'or switch line 61 to a half-open test `lo <= v < hi` and keep the round '
           'numbers. Pick one convention and make the four tables literally '
           'identical.'),
    verification=('After the fix, assert `100 in` the kept values for a synthetic '
                    'record and that the oxygen-saturation `value_level` count in '
                    'Logs/mimic-iii/<agg>/oxygen_saturation_filter_log.json drops by '
                    'the number of exact-100 readings; the ICU-positive SpO2 '
                    'centroid for the `oxygen saturation` arm should return to ~the '
                    'raw value (within the effect of genuinely out-of-range '
                    'readings) instead of 96.46.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C3',
        note=('Correction: fill_missing_data_analysis.py and render_paper_figures.py '
             'already use (1,100) — the whole-table off-by-one lives in the four '
             'live copies. Centroid evidence: ICU-pos SpO2 100.90->96.46.'),
    ),
),
dict(
    id='F-03', stage=FILTER, severity=HIGH, status=OPEN, verified=True,
    name=('fill missing data is mean imputation, not KNN, and imputes from values '
            'it rejected'),
    overview=('Reshaping to a single column makes sklearn fall back to the column '
                'mean, so the k-nearest-neighbour behaviour the docstring describes '
                'never executes.'),
    affects=('The `fill missing data` arm in all five aggregations: '
               'Data/mimic-iii/*/fill_missing_data_filtered_dataset_ehr.pkl (mean '
               'rebuilt 2026-08-05), its centroids (icu_fill missing data_*.pkl, '
               '2026-08-05), the CV and legacy filter-impact entries (mean agg: icu '
               '0.6817 vs raw 0.6936; mortality 0.7330 vs 0.6868 — the largest '
               'single-arm effect in the sweep), and '
               'paper_figures/ecdf_fill_missing_data_mean_{2x4,4x2}.pdf, whose '
               "per-vital ECDFs contain a synthetic step at each patient's column "
               'mean. 1.83M cells (≈24% of the 46k×168 grid) carry these values.'),
    recompute=('The fill-missing filtered datasets for all five aggregations, '
                 'their centroids and admission-id sidecars, both filter-impact '
                 'paths (legacy and CV), the McNemar tables that pair against them, '
                 'and both ECDF figures.'),
    technical=('Managers/ehr_filter_manager.py:126 casts the column to float; '
                 'lines 129-130 build `known_indices` restricted to `valid_range`; '
                 'line 134 gates on `len(known_indices) >= 2`. But line 140 reshapes '
                 'the *unfiltered* `column_data` to (24,1) and line 141 fits on it, '
                 'so (a) out-of-range and zero entries are donors even though they '
                 'were excluded from the guard, and (b) with n_features=1 '
                 '`nan_euclidean_distances` between a receiver (NaN in its only '
                 "coordinate) and any donor is NaN, hitting sklearn's "
                 '`all_nan_receivers_idx` branch (sklearn/impute/_knn.py:339-346) '
                 'that assigns the masked column mean. n_neighbors=3 is never used. '
                 'Line 142 writes the whole column back; known values are preserved, '
                 'so the only effect is that gaps become a constant. The docstring '
                 'at lines 105-117 and the paper trail at '
                 'Experiments/fill_missing_data_analysis.py:19-36 both assert KNN '
                 'behaviour ("KNN can only ever produce values interpolated between '
                 'observations it actually saw"), and noahNotes.md:424 describes the '
                 'filter as "KNN imputation" with a TODO about tuning k — documented '
                 "intent contradicts the code. The debug notebook's "
                 '`fill_missing_data_filter_v2` (lines 167-215) is claimed to be '
                 '"the same code" as the shipped filter but supplies `(1, 100)` for '
                 'SpO2 (line 150) where the shipped path supplies `(1, 99)`, so the '
                 'two are not identical.\n'
                 '\n'
                 'First-pass measurements retained: (b) Line :130 restricts '
                 "known_indices to in-range values for the '>= 2 known' guard only. "
                 'fit_transform at :141 is fit on the full unfiltered column, so a '
                 'record with one HR of 9999 has its gaps filled from a mean '
                 'contaminated by 9999 — an attenuated form of the exact symptom the '
                 'spline-to-KNN swap was meant to fix.'),
    fix=('Impute over a feature matrix that gives KNNImputer something to measure '
           'distance on — e.g. stack the hour index (or the other six vitals, if '
           'cross-vital leakage is acceptable) as extra columns — or, for a '
           'per-column time series, use an explicit interpolation '
           "(`pd.Series.interpolate(limit_area='inside')`) and rename the filter "
           'honestly. Independently, fit on the guard-filtered data: mask '
           'out-of-range and zero entries to NaN before `fit_transform` so rejected '
           'values cannot become donors.'),
    verification=('On a synthetic 24-row column with values only at hours 0 and '
                    '23, a real interpolator must produce a monotone ramp; current '
                    'code returns the identical two-value mean at all 22 gaps. '
                    'Assert `len(set(filled[missing_indices])) > 1` for such a '
                    'trace, and assert that a column containing a 23,000 outlier '
                    'plus two valid readings never yields an imputed value above '
                    '`valid_range[1]`. Then compare the ECDF figures: the vertical '
                    'step should disappear.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C3',
        note=('Independently re-derived from code by a blind verification agent; '
             'description updated where the re-derivation was more precise.'),
    ),
),
dict(
    id='F-04', stage=FILTER, severity=HIGH, status=OPEN, verified=True,
    name='Deviation aggregations encode monitoring intensity, not physiology',
    overview=('Under the three deviation methods a cell is 0 for a one-reading '
                'hour and 0 for a no-reading hour, so the feature vector largely '
                'encodes whether the patient was measured twice.'),
    affects=('The three deviation dataset families entirely — '
               'Data/mimic-iii/{standard deviation,mean deviation,maximum '
               'deviation}/**, their centroids, and their filter-impact results. '
               'Most visibly, `high invalid data` (which counts `== 0` as invalid '
               'over the 24×7 grid) keeps 0 of 46,032 records in all three families '
               'versus 1,369 under `mean`, so that arm is reported as degenerate/NaN '
               'rather than as a result. Any table or claim that presents the '
               'deviation aggregations as five comparable "aggregation methods" '
               '(noahNotes.md:355-361) overstates what three of them contain. '
               'paper_figures/ are all `mean`, so the published figures are not '
               'directly wrong.'),
    recompute=('Nothing needs recomputation to make current mean/median numbers '
                 'right. If the encoding is fixed (e.g. emitting NaN for <2 readings '
                 'and carrying an explicit observation-count channel), all three '
                 'deviation families must be rebuilt from processed_record_ehr.pkl: '
                 'raw + 11 filtered datasets × 3 aggregations, centroids, admission '
                 'ids, filter impact, and any table reporting deviation arms.'),
    technical=('Managers/ehr_filter_manager.py:361-367 defines the ops; for a '
                 'one-element list `np.std([x]) == 0.0` and both deviation lambdas '
                 'reduce to `|x - x| == 0.0`. Lines 379-384 map an empty/None cell '
                 'to `np.nan`, and Entities/ehr_record.py:41-42 zero-fills NaN '
                 'before tensorisation, erasing the distinction. The consequence is '
                 'measured in this repo: high_invalid_data_filter (lines 277-282) '
                 'treats `isna() | (df == 0)` as invalid at a 10% threshold and '
                 'keeps nothing under the deviation aggregations — the cached '
                 'artifacts are 1,511-byte empty datasets versus ~1.78 MB under '
                 'mean/median — which means essentially every record has >17 of 168 '
                 'zero cells. rerun/verify_cv.py:173-179 acknowledges this as a fact '
                 'of life and only guards the crash it caused. Independently '
                 'measured on tensors rebuilt from the same '
                 'processed_record_ehr.pkl, '
                 '/home/ccampb47/work/hour_scaling_experiment/POSTMORTEM.md:148-153 '
                 'reports "`mean` and `median` 38.9%; `standard deviation`, `mean '
                 'deviation` and `maximum deviation` all **89.9%**" zero cells and '
                 'the same one-reading mechanism. The zero-fill rationale in '
                 'ehr_record.py:38-41 ("the vitals are all strictly positive in '
                 'practice, so 0 is out-of-range enough to act as its own signal") '
                 'is true for mean/median and false for the deviation arms, where 0 '
                 'is the modal legitimate value.\n'
                 '\n'
                 'First-pass measurements retained: It is why standard deviation '
                 '(0.6972 raw mortality OOF) stays competitive with mean (0.6868) '
                 'while carrying almost no level information. POSTMORTEM.md 2.6 '
                 'reached the same conclusion and demoted these three to a lower '
                 'tier; the toolbox still gives all five equal billing.'),
    fix=('Make "no reading" distinguishable: return NaN (not 0) from the deviation '
           'ops when `len(numeric_values) < 2`, stop blanket `nan_to_num` in '
           '`to_tensor` in favour of an explicit imputation plus a companion '
           'observation-count/missingness channel, and have high_invalid_data_filter '
           'test NaN rather than `== 0` so it stops treating a legitimate zero '
           'deviation as a hole.'),
    verification=('Recompute the exact-zero fraction of each cached tensor family '
                    '— the deviation arms should fall from ~90% toward the mean '
                    "arm's missingness rate — and confirm `high invalid data` under "
                    'the deviation aggregations keeps a nonzero, plausible record '
                    'count instead of reporting `degenerate: true`. Add an assertion '
                    'that a cell built from one reading is NaN, not 0.'),
    found='POSTMORTEM.md 2.6, re-derived 2026-08-11',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C3',
        note=('Independently re-derived from code by a blind verification agent; '
             'description updated where the re-derivation was more precise.'),
    ),
),
dict(
    id='F-05', stage=FILTER, severity=HIGH, status=OPEN, verified=True,
    name='aggregate() hardcodes a 24-row output frame',
    overview=('The output frame is created with `index=range(24)` regardless of '
                "the input's length, and cells are written by label "
                '(`new_dataframe.at[row_label, ...]`), with the enumeration counter '
                '`i` never used. A shorter input therefore leaves trailing all-NaN '
                'hours that are indistinguishable from real missingness, and an '
                "input whose labels fall outside 0..23 does not truncate — pandas' "
                '`_set_value` falls back to `.loc` and enlarges the index — so a '
                '30-hour record yields a 30-row frame and a 1-based index yields 25 '
                'rows with a phantom NaN hour 0. Either way the window length is '
                'decided by the index labels rather than validated.'),
    affects=('Nothing currently published. Processing/mimic-iii-processing.py:80 '
               'clips to `hour < 24` and line 116 reindexes to exactly `range(24)`, '
               'so every record in Data/mimic-iii/processed_record_ehr.pkl is a '
               'clean 24-row 0-based frame and aggregate() is a no-op reshaper '
               'today. The exposure is forward-looking: any variable-window reuse '
               '(the kind of hour-scaling sweep in '
               '/home/ccampb47/work/hour_scaling_experiment) gets silent NaN→0 '
               'padding via ehr_record.py:41-42, and Entities/ehr_dataset.py:35 '
               'hardcodes `self.num_rows = 24` so nothing downstream would object.'),
    recompute='Nothing.',
    technical=('Managers/ehr_filter_manager.py:359 hardcodes the row count; '
                 '370-387 iterate `enumerate(dataframe.index)` but address the '
                 'destination with `row_label`, so `i`/`j` are dead and positional '
                 'correspondence is never enforced. If `row_label` is absent from '
                 '`range(24)`, DataFrame._set_value (pandas/core/frame.py:4904-4922) '
                 'catches the KeyError and re-dispatches to `self.loc[index, col] = '
                 'value`, which appends a new row — so the claim\'s "silently '
                 'truncated" is incorrect; the failure mode is index enlargement '
                 'plus retained all-NaN rows. The claim\'s "shorter ones NaN-padded" '
                 'is correct: a 10-row input yields rows 10-23 as NaN, which '
                 '`to_tensor` (Entities/ehr_record.py:41-42) turns into zeros. '
                 'Verified against the pandas source available on disk (3.0.0 in '
                 '.venv_centroid_recompute); requirements.txt pins pandas==2.3.3, '
                 'where `_set_value` has the same enlargement fallback, so I mark '
                 'confidence medium rather than high because I did not execute '
                 'either version.'),
    fix=("Build the output from the input's own index (`pd.DataFrame(np.nan, "
           'index=dataframe.index, columns=dataframe.columns)`) and write '
           'positionally with `.iat[i, j]`, or take the window length as a parameter '
           'and assert `len(dataframe) == expected` up front so a non-conforming '
           'record raises instead of being padded.'),
    verification=('Call aggregate() on a 12-row frame and on a frame indexed 1..24 '
                    "and assert the result has the input's shape and index; assert "
                    'no all-NaN row is introduced. Confirm the 24-row production '
                    'path is byte-identical before/after by re-aggregating a sample '
                    'of processed_record_ehr.pkl records and comparing tensors.'),
    found='hour_scaling_experiment git 92e52d1, applies here',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C3',
        note=('Correction: out-of-range labels ENLARGE the index via .loc fallback '
             'rather than truncate; short inputs NaN-pad. Latent (ingest guarantees '
             '24 rows). Severity suggestion: Low.'),
    ),
),
dict(
    id='F-06', stage=FILTER, severity=MEDIUM, status=OPEN, verified=True,
    name="high_invalid_data_filter's comparison contradicts its docstring",
    overview=('The keep test is `invalid_ratio < threshold`, so a record whose '
                'invalid fraction equals 0.10 exactly is dropped, whereas the '
                'docstring promises only records strictly above 10% are dropped. '
                'Because every frame is 24×7 = 168 cells, the achievable ratios are '
                'k/168 and 0.10·168 = 16.8, so no record can ever land on the '
                'boundary: k=16 gives 0.0952 (kept) and k=17 gives 0.1012 (dropped). '
                'The discrepancy is therefore a wording defect with no reachable '
                'behavioural consequence at the current grid size.'),
    affects=('Nothing. Every cached `high_invalid_data_filtered_dataset_ehr.pkl` '
               "and every filter-impact number for that arm is what the docstring's "
               'own worked example ("10% of 168 cells is about 17") predicts. It '
               'would begin to matter only if `threshold` or the grid changed to a '
               'combination where threshold·df.size is an integer (e.g. a 20×7 = '
               '140-cell frame at 10%, where 14 cells is exactly the boundary).'),
    recompute='Nothing.',
    technical=('Managers/ehr_filter_manager.py:272-288: `total_cells = df.size` '
                 '(168), `invalid_cells` counts `isna() | (df == 0)`, and the keep '
                 'branch at line 282 is `invalid_ratio < threshold` with `threshold: '
                 'float = 0.10` from the signature at line 256. Drop condition is '
                 'thus ratio >= 0.10; the docstring at line 257 says "more than '
                 '10%". The two differ only at equality, which k/168 cannot produce. '
                 'The more substantive gap in the same docstring is vocabulary '
                 'rather than comparison: it says "empty" and "counts holes", while '
                 'line 277 also treats a charted 0 as invalid — the repo-wide '
                 'convention stated explicitly in the neighbouring '
                 'long_missing_segment docstring (lines 165-167) but not here, and '
                 'the mechanism that makes this filter keep zero records under the '
                 'deviation aggregations (see F-04).'),
    fix=('Either change line 282 to `if invalid_ratio <= threshold:` or reword '
           'line 257 to "at least 10% invalid", and add "invalid = NaN or a charted '
           '0" to the docstring so the zero convention is stated where it is '
           'applied. Prefer the docstring change plus an explicit `>=` drop test for '
           'readability.'),
    verification=('Parameterised test asserting the keep/drop decision at k=16 and '
                    'k=17 invalid cells out of 168 is unchanged, plus a case with '
                    '`threshold=0.10` on a 140-cell frame at exactly 14 invalid '
                    'cells that pins whichever convention is chosen.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C3',
        note=('Correction: the 10% boundary is unreachable on a 168-cell grid (16.8 '
             'not integral), so the docstring/code disagreement has no behavioural '
             'consequence today. Severity suggestion: Low/cosmetic.'),
    ),
),
dict(
    id='F-07', stage=FILTER, severity=MEDIUM, status=OPEN, verified=True,
    name='aggregate() falls back to mean silently, and a caller depends on it',
    overview=('`combination_filter` takes a `method` parameter and never passes it '
                'on — line 329 calls `aggregate_filter(records1)`, which defaults to '
                "mean — while `create_combination_filter_dataset` forwards the run's "
                '`aggregation_method` in good faith and then saves the result under '
                '`Data/<dataset>/<aggregation_method>/`. A "median" or "maximum '
                'deviation" combination arm would therefore be mean-aggregated data '
                'filed under the wrong name, with no error. Separately, `aggregate` '
                'resolves its method with `ops.get(method, np.mean)`, so a typo in '
                'an aggregation name also becomes a silent mean run rather than an '
                'exception.'),
    affects=('Nothing published. The only caller is commented out '
               '(Experiments/notebook.py:479-502), no combination-filter artifacts '
               'exist on disk (no `all_vitals_*_*` / combination pickles under '
               'Data/mimic-iii/*/), and the CV diagnostics contain only the 11 '
               'single filters plus `all vitals` and `raw`. The live single-filter '
               'path is correct: dataset_manager.py:94 and 96 pass '
               '`aggregation_method` into `aggregate_filter`, and the five '
               'aggregation names match the `ops` keys exactly, so the mean fallback '
               'is not reachable from the current sweep.'),
    recompute=('Nothing now. If the combination arms are ever enabled, everything '
                 'under Data/<dataset>/<agg>/ for those arms must be built after the '
                 'fix, since a pre-fix run would have produced four mislabelled '
                 'datasets per non-mean aggregation.'),
    technical=('Managers/ehr_filter_manager.py:318 declares `method: str = '
                 "'mean'`; line 329 drops it; `aggregate_filter` (line 391) then "
                 'uses its own default and `aggregate` (line 338) is called with '
                 '"mean". Managers/dataset_manager.py:112-130 passes '
                 '`aggregation_method` positionally as that ignored fifth argument '
                 "and writes to `PROJECT_ROOT / 'Data' / dataset_name / "
                 'aggregation_method` (line 114), so the directory name would be the '
                 'only record of an aggregation that never happened. Both behaviours '
                 "are flagged in the code's own docstrings — lines 325-326 "
                 '("`method` is accepted but never used") and 356-357 ("An '
                 'unrecognised method silently falls back to mean rather than '
                 'raising") — but a warning in prose does not make the signature '
                 'honest: the parameter exists, a caller supplies it, and the output '
                 'path is named after it.'),
    fix=('Forward the argument (`aggregate_filter(records1, method)`) or delete '
           'the parameter from `combination_filter` and make '
           '`create_combination_filter_dataset` refuse any non-mean aggregation. '
           'Independently, replace `ops.get(method, np.mean)` with a lookup that '
           'raises `ValueError(f"unknown aggregation {method!r}")`, and keep the '
           'mean default only in the signature.'),
    verification=("Call `combination_filter(..., method='maximum deviation')` on a "
                    'record whose cells hold multiple readings and assert the result '
                    'differs from the mean-aggregated version; assert `aggregate(df, '
                    "'meen')` raises. Then, before enabling the notebook cell, check "
                    'that the tensors written under `Data/mimic-iii/median/` for a '
                    'combination arm differ from those under `Data/mimic-iii/mean/`.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C3',
        note=('Correction: mean fallback is documented in docstrings and unreachable '
             'from the live sweep; combination path has no live caller. Severity '
             'suggestion: Low, latent.'),
    ),
),
dict(
    id='F-08', stage=FILTER, severity=LOW, status=OPEN, verified=True,
    name='_remove_outliers mixes label-based and position-based indexing',
    overview=('It iterates index labels and writes back by position, which '
                'coincide only while the index is a clean 0..23 range.'),
    affects=('Nothing today. Processing/mimic-iii-processing.py:116 reindexes '
               'every record to exactly `range(24)`, so labels equal positions for '
               'all data in Data/mimic-iii/processed_record_ehr.pkl and all seven '
               'per-vital filters (plus `all vitals`) behave as intended. The risk '
               'is that any future record subsetting, hour-window change, or '
               'timestamp-indexed frame silently shifts every pruned hour by the '
               'index offset — a corruption that would not raise and would not '
               'change record counts, so no existing check would catch it.'),
    recompute='Nothing.',
    technical=('Managers/ehr_filter_manager.py:48 takes `timeseries.iloc[:, '
                 'column_index].copy()` (positional column select — correct); line '
                 '51 iterates label/value pairs; lines 55-63 rebuild the cell list; '
                 'line 65 stores it with `column_values.iloc[index]`. For a 1-based '
                 'hour index, label 24 would raise IndexError at line 65; for a '
                 'DatetimeIndex, `iloc` with a Timestamp raises TypeError; for a '
                 'gap-filtered integer index (e.g. labels 0,2,5) the write lands on '
                 'the wrong hour with no error. This is the same label-vs-position '
                 "confusion as F-05's `new_dataframe.at[row_label, ...]` at line "
                 '370-387, so the two failure modes would appear together. Line 67 '
                 'then assigns the Series back into the column, which for a '
                 'differently-labelled Series would also align by label rather than '
                 'position — a second reason the invariant "index is 0..n-1" is '
                 'load-bearing here.'),
    fix=('Iterate positionally and write positionally: `for pos, cell in '
           'enumerate(column_values.to_numpy())` with `column_values.iloc[pos] = '
           'cell`, or keep `.items()` and write with `column_values.at[index] = '
           'cell`. Whichever is chosen, add an assertion (or normalise with '
           "`reset_index(drop=True)`) that the frame's index is a 0-based RangeIndex "
           'on entry to `_remove_outliers`.'),
    verification=('Run one per-vital filter on a record whose timeseries index is '
                    '1..24 (and again on a DatetimeIndex) and assert the pruned '
                    'values land in the correct hours instead of raising or '
                    'shifting; assert the 0..23 production case produces '
                    'byte-identical tensors to the current code for a sample of '
                    'records.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C3',
        note=('Independently re-derived from code by a blind verification agent; '
             'description updated where the re-derivation was more precise.'),
    ),
),

# ── Evaluation ────────────────────────────────────────────────────────────────
dict(
    id='E-01', stage=EVAL, severity=HIGH, status=RESOLVED, verified=True,
    name='Validation set concatenated onto test',
    overview=('`evaluate_dataset_label_impact` used to concatenate the 10% '
                'validation subset onto the 10% test subset and score the union with '
                "`.predict()`'s implicit 0.5, so an effective 80/20 split had no "
                'validation set at all. The working tree keeps all three subsets '
                'disjoint: validation is used only by `pick_threshold` '
                '(evaluation_manager.py:178-179) and test is a true held-out 10%.'),
    affects=('Nothing current. It affected every pre-2026-08-10 '
               '`*_filter_impact.pkl` (test n≈9207 instead of 4604) and the figures '
               'built from them. The regenerated '
               '`Data/mimic-iii/*/[icu|mortality]_filter_impact*.pkl` (2026-08-10 '
               '21:38) and `paper_figures/*` (2026-08-10 22:14) already reflect the '
               'disjoint split.'),
    recompute=('Nothing — stage B (`rerun/regen_filter_impact.py`) and '
                 '`paper_figures/` were both regenerated after the fix.'),
    technical=('The pre-fix path merged the two subsets before scoring; the '
                 'surviving quantitative trace is '
                 '`rerun/logs/confusion_matrices_mean_raw.json`, whose `old` regime '
                 'cells sum to 9207 (100+13+793+8301, mortality seed 22) while `new` '
                 'sums to 4604 — exactly `n_validation` + `n_test` versus `n_test` '
                 'from the diagnostics sidecar. The current code takes three subsets '
                 'at evaluation_manager.py:149, flattens each separately (151-153), '
                 'selects the threshold on validation only (178-179), and applies it '
                 'to test and train (184-185). The CV path is independently clean: '
                 '`partition_manager.inner_split` (partition_manager.py:141-171) '
                 "carves a stratified 1/8 inner-validation slice out of each fold's "
                 'training set, and `evaluate_dataset_label_cv` thresholds the '
                 'held-out fold with it (evaluation_manager.py:447-457).\n'
                 '\n'
                 'First-pass measurements retained: Done — job 19487956 on '
                 '2026-08-10. Measured effect on raw/mean mortality: accuracy 0.9125 '
                 '-> 0.7410. 97.5% of that drop is the threshold moving off 0.5, not '
                 'the smaller test set — isolated with a control arm in '
                 'rerun/logs/confusion_matrices_mean_raw.json. Type II error fell '
                 '0.886 -> 0.352; the old classifier caught 101 of 893 deaths.'),
    fix=('Already applied. The one loose end is documentation: '
           '`/home/ccampb47/work/noahNotes.md:448` still states "the validation '
           '(10%) set and the testing (10%) set are merged in this case", which now '
           'describes behaviour the code no longer has.'),
    verification=('`Data/mimic-iii/*/*_filter_impact_diagnostics.json` must report '
                    '`n_validation` and `n_test` as separate ~10% numbers summing to '
                    '20% of `n_train`/0.8 (it does: 36825/4603/4604 = 46032), and '
                    '`n_test` must never equal `n_validation + n_test` of the old '
                    "run. For the CV path, `verify_cv.py`'s section 4 coverage check "
                    "plus a manual assertion that `inner_split`'s two outputs are "
                    'disjoint from the scored fold.'),
    found='2026-08-10',
    fixed='2026-08-10',
    audit=dict(
        date='2026-08-12', verdict='FIXED-IN-WORKING-TREE', mode='cluster C4',
        note=('Independently re-derived from code by a blind verification agent; '
             'description updated where the re-derivation was more precise.'),
    ),
),
dict(
    id='E-02', stage=EVAL, severity=HIGH, status=PARTIAL, verified=True,
    name='Reported metrics were a single holdout, not cross-validated',
    overview=('In the legacy path the sole cross-validation is '
                '`cross_validate_model`, a 4-fold cuML KFold over the *training* '
                'slice whose mean accuracy is reported as tuple position 0 — it '
                'tunes nothing and never touches the scored data. Position 1, the '
                'number every figure plots, is a single fit scored on one 10% slice, '
                'and because `DatasetEHR.split` caches (see E-03) it is the *same* '
                'slice for all four seeds. A genuinely cross-validated path now '
                'exists but is not what the notebook or the figures read.'),
    affects=('`Data/mimic-iii/*/[icu|mortality]_filter_impact.pkl` positions 0-4, '
               'and every figure derived from them: '
               '`paper_figures/filter_impact_{icu,mortality}_testing_{accuracy,f1}_mea'
               'n.pdf` and `paper_figures/mcnemar_icu_mean.pdf` '
               '(render_paper_figures.py:315, 386). Also the "±" spread anywhere it '
               'is read off the four seeds — that is forest variance only. Position '
               '0 and position 1 additionally describe different classifiers (0.5 vs '
               'the Youden threshold), so the two columns are not comparable to each '
               'other.'),
    recompute=('Nothing for the CV design — `*_filter_impact_cv.pkl`, '
                 '`*_filter_impact_cv_diagnostics.json` and `*_oof_scores_cv.npz` '
                 'already exist for all five aggregations × both labels (2026-08-11 '
                 '15:24-15:35). To make the *paper* cross-validated, re-render '
                 '`paper_figures/` against the `_cv` pickles and re-run '
                 '`render_paper_figures.py` / the notebook plots with `IMPACT_SUFFIX '
                 "= '_cv'`."),
    technical=('`cross_validate_model` (evaluation_manager.py:33-60) splits '
                 '`x_train` only, fits 300-tree forests per fold, and returns the '
                 "fold-mean accuracy at `.predict()`'s implicit 0.5; the value is "
                 'consumed at evaluation_manager.py:173 and surfaced as '
                 '`training_averages` (292). No hyperparameter, threshold, or model '
                 'choice depends on it — `final_model` at 175 is fit on the whole '
                 'training slice regardless. Test metrics come from `test_sub` of '
                 'one `dataset.split(0.8, 0.1, 0.1)` (149). The replacement, '
                 '`evaluate_filter_impact_cv` (617-723), predicts every record '
                 'out-of-fold under 4 independent stratified 5-fold partitions '
                 '(partition_manager.py:34-105) and reports per-repeat spread; its '
                 'artifacts show honest error bars (raw, mean/icu: `accuracy_mean` '
                 '0.6936, `accuracy_std` 0.00245 across four *partitions*). But '
                 "`IMPACT_SUFFIX = ''` (notebook.py:566) and "
                 'render_paper_figures.py:315/386 read the legacy pickle, so nothing '
                 'published is cross-validated. Legacy vs CV disagree materially: '
                 'legacy `high invalid data` icu accuracy 0.663 with McNemar '
                 'p=5.06e-05, CV 0.616 with p=0.964.\n'
                 '\n'
                 'First-pass measurements retained: Replaced by '
                 'evaluate_dataset_label_cv: 5 folds x 4 repeats, every one of the '
                 '46,032 records predicted out-of-fold per repeat, at the same fit '
                 'budget because the inert inner CV was removed. '
                 'rerun/logs/g_verify_cv_19580847.log — coverage 1.000, 20/20 folds '
                 'fitted for every non-empty arm.'),
    fix=('Point the figure/table code at the `_cv` artifacts (`IMPACT_SUFFIX = '
           "'_cv'` in notebook.py:566 and the equivalent path in "
           'render_paper_figures.py:315/386), and either delete '
           '`cross_validate_model` from the reported tuple or relabel position 0 so '
           'it is not read as a validated estimate. Run stage F for any aggregation '
           'still missing `_cv` artifacts.'),
    verification=('Confirm `*_filter_impact_cv_diagnostics.json` reports `coverage '
                    '== 1.0` and four `per_repeat` entries per arm for every '
                    'aggregation (it does for `mean`), then confirm the regenerated '
                    "figures' values match `[1]`/`[3]` of the `_cv` pickle rather "
                    'than the legacy one. `rerun/verify_cv.py` section 4 covers the '
                    'coverage claim but not the figure wiring.'),
    found='2026-08-11',
    fixed='2026-08-11',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C4',
        note=('First pass marked RESOLVED; blind audit found the fix exists only in '
             "the CV path while IMPACT_SUFFIX='' and paper_figures still consume the "
             "legacy single-holdout pickles — PARTIAL per the register's own "
             'guardrail (same rule as E-05/E-06).'),
    ),
),
dict(
    id='E-03', stage=EVAL, severity=HIGH, status=PARTIAL, verified=True,
    name='The four seeds were one partition',
    overview=('`DatasetEHR.split` only shuffles when the requested weights differ '
                'from `self.split_weights`, so after the first seed populates the '
                'cache every later `torch.manual_seed(seed)` has no effect on which '
                'patients land in test. The four seeds therefore vary only '
                '`RandomForestClassifier(random_state=seed)`, and the spread '
                'reported across them is forest randomness, not sampling variability.'),
    affects=('Any spread/error bar read off the four seeds in '
               '`Data/mimic-iii/*/[icu|mortality]_filter_impact.pkl` and the figures '
               'built from them (`paper_figures/filter_impact_*`), plus the '
               '`thresholds` dicts in `*_filter_impact_diagnostics.json`, which are '
               'four thresholds chosen on one identical validation set. It does not '
               'affect the `_cv` artifacts.'),
    recompute=('To fix the legacy design, the whole legacy sweep '
                 '(`rerun/regen_filter_impact.py`, 10 tasks) plus every figure. '
                 'Alternatively nothing, if the legacy tuple is retired in favour of '
                 'the `_cv` artifacts, which already carry four genuinely '
                 'independent partitions.'),
    technical=('The cache guard is ehr_dataset.py:74; `randperm` (75) executes '
                 'only on the first call per dataset object, and `split_weights` is '
                 'set at 95. `evaluate_filter_impact` calls '
                 '`torch.manual_seed(seed)` at 277 then '
                 '`evaluate_dataset_label_impact` → `dataset.split(0.8, 0.1, 0.1)` '
                 'at 149 for each of the four seeds on the *same* dataset objects, '
                 'so calls 2-4 return the cached subsets. The code comment at '
                 '271-274 states this explicitly, and '
                 '`rerun/confusion_matrices_mean_raw.py:78-81` reproduces it '
                 'deliberately. Empirically: the `old` regime confusion cells in '
                 '`rerun/logs/confusion_matrices_mean_raw.json` move by ≤2 records '
                 'across the four seeds (tp 100/102/102/102, tn 8301/8303/8300/8298 '
                 'on n=9207) — consistent with one fixed test set and four forests, '
                 'not four draws. The CV path replaces this properly: '
                 '`PARTITION_SEED` drives the partition and `forest_seed(repeat, '
                 'fold)` drives the estimator (partition_manager.py:34, 58-65), with '
                 'a regression assertion that repeats are distinct partitions '
                 '(pairwise agreement < 0.35, partition_manager.py:227-238).\n'
                 '\n'
                 'First-pass measurements retained: Entities/ehr_dataset.py:69 keys '
                 'its cache on split_weights, ignoring the seed, so seeds 985/439/81 '
                 "reused seed 22's partition; torch.manual_seed at "
                 'evaluation_manager.py:273 was effectively dead after the first '
                 'iteration. Pairwise fold agreement between repeats is 0.203 (about '
                 '1/5, i.e. independent). The old design would score 1.0.'),
    fix=('Give `DatasetEHR.split` an explicit `seed` parameter (or a `force` flag) '
           'and key the cache on `(weights, seed)` rather than weights alone; or '
           'migrate all reported numbers to `evaluate_filter_impact_cv`, whose '
           'partition is drawn once per repeat by construction.'),
    verification=('With a fix, `n_test` can stay constant but the test-set '
                    '*membership* must change per seed — assert the four per-seed '
                    '`test_prevalence`/`validation_prevalence` values differ, or '
                    'hash the test index list per seed and assert four distinct '
                    'hashes. `Managers/partition_manager.py:227-238` is the model '
                    'for the assertion.'),
    found='2026-08-11',
    fixed='2026-08-11',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C4',
        note=('Downgraded RESOLVED->PARTIAL: partition_manager fixes the CV path; '
             "DatasetEHR.split's weight-keyed cache is untouched in the legacy path "
             'that produced the published figures.'),
    ),
),
dict(
    id='E-04', stage=EVAL, severity=CRITICAL, status=OPEN, verified=True,
    name='In the legacy path each arm draws a different split',
    overview=('`torch.manual_seed(seed)` is called once, then thirteen distinct '
                '`DatasetEHR` objects each call `split()` and each draws its own '
                '`torch.randperm` from the progressively advanced RNG stream — so '
                "arm *k*'s partition comes from a different state than arm *k-1*'s. "
                "Nothing makes the arms' test sets the same patients, and "
                '`calculate_mcnemar_test` then pairs them by list position, so the '
                '"paired" test compares arbitrary patient *k* of raw against '
                'arbitrary patient *k* of the filtered arm.'),
    affects=('All `mcnemar_results` (position 4) in '
               '`Data/mimic-iii/*/[icu|mortality]_filter_impact.pkl` and '
               '`paper_figures/mcnemar_icu_mean.pdf`. Also makes filter-vs-raw '
               'accuracy deltas partly a measurement of which patients landed in '
               "each arm's test set: for `mean`/icu the arms' `test_prevalence` "
               'ranges 0.360-0.395 at identical n=4604, a ~3.5-point swing in class '
               'balance from shuffling alone.'),
    recompute=('The whole legacy sweep plus the McNemar figure, or retire them in '
                 'favour of the `_cv` artifacts (already computed for 5 aggregations '
                 '× 2 labels), whose McNemar is paired on admission_id.'),
    technical=('Each arm is a separate object with its own `split_weights == '
                 '(0,0,0)`, so on the first seed all thirteen take the `randperm` '
                 'branch at ehr_dataset.py:75 in sequence, consuming one draw each '
                 'from the shared global torch RNG. The decisive proof is in the '
                 'artifact rather than the code: `regen_admission_ids.py` validates '
                 'that the ten record-preserving arms carry byte-identical `[icu, '
                 'mortality]` label matrices to raw in the same order '
                 '(regen_admission_ids.py:84-89, and `[mean] wrote 13 id vectors, '
                 'all validated against their cached pickles` in '
                 '`rerun/logs/e_admission_ids_19573270_0.log`). Identical labels in '
                 'identical order plus an identical split would force identical '
                 '`test_prevalence`; instead raw is 0.37772, `heart rate` 0.36990, '
                 '`fill missing data` 0.36056 — so the partitions genuinely differ. '
                 'Separately, the three record-dropping arms (n=31029/20323/1369) '
                 "could not share raw's partition under any RNG discipline. The "
                 "comment at 267-269 and `calculate_mcnemar_test`'s docstring at "
                 '219-221 both assert the opposite of what the code does, which per '
                 'guardrail 10 confirms the defect. The CV path removes it: one '
                 'partition is drawn on the raw cohort and inherited via '
                 '`project_to_arm` (evaluation_manager.py:667, 675), and all 13 arms '
                 'in `Data/mimic-iii/mean/icu_filter_impact_cv_diagnostics.json` '
                 'report the same `partition_fingerprint` `b1f2ba53d873430e`.\n'
                 '\n'
                 'First-pass measurements retained: These arms all hold the '
                 'identical 46,032 records, yet their validation prevalences differ:\n'
                 '  raw 0.37302 | heart rate 0.37584 | systolic 0.38171 | '
                 'temperature 0.36715 | oxygen saturation 0.38757\n'
                 'A shared split would give identical values; the spread is what '
                 'independent draws look like. Sharper still: comparing mean against '
                 'maximum deviation, every arm *before* the record-dropping arms in '
                 "FILTERS order has byte-identical prevalences, while 'all vitals' — "
                 'which comes after them, and whose randperm sizes differ by '
                 'aggregation — does not (0.37693 vs 0.36628).'),
    fix=('Do not let arms draw their own partitions. Either pass an explicit '
           'partition (admission_id → fold/split) into '
           '`evaluate_dataset_label_impact`, or route the legacy sweep through '
           '`partition_manager.build_fold_assignment` + `project_to_arm` — i.e. use '
           '`evaluate_filter_impact_cv` and delete the legacy path once the figures '
           'are migrated.'),
    verification=('Assert that for every record-preserving arm the test-set '
                    "admission_id vector equals raw's, and that `test_prevalence` is "
                    'byte-identical across those arms; for dropping arms assert the '
                    "arm's test ids are a subset of raw's. "
                    '`rerun/verify_cv.py:121-130` ("inherits raw\'s folds exactly") '
                    'and the single-fingerprint check at 242-244 are the CV-path '
                    'equivalents.\n'
                    'fix-note: n/a'),
    found='2026-08-11 pipeline trace; verified from the diagnostics',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C4',
        note=('Correction: RNG-stream divergence happens only on the first seed '
             '(cache freezes it after); test_prevalence spread 0.360-0.395 at equal '
             'n proves unrelated partitions.'),
    ),
),
dict(
    id='E-05', stage=EVAL, severity=CRITICAL, status=PARTIAL, verified=True,
    name='McNemar zipped unequal-length prediction vectors',
    overview=('`calculate_mcnemar_test` builds its 2×2 table by `zip`-ing the '
                "baseline's majority-vote vector against the arm's, so for a "
                'record-dropping arm the table contains only as many rows as the '
                'smaller arm holds — and those rows pair positionally, i.e. '
                'different patients. The result is a contingency table built from a '
                'truncated, mis-paired sample, and the table tabulates '
                'prediction-vs-prediction rather than correctness, so it cannot say '
                'which arm was right.'),
    affects=('`mcnemar_results` (position 4) of every legacy `*_filter_impact.pkl` '
               'for the three record-dropping arms — `long missing segment` (n_test '
               '3104), `long gap` (2033), `high invalid data` (138) — and '
               '`paper_figures/mcnemar_icu_mean.pdf`, whose bars for those filters '
               "are computed on 3%-67% of the baseline's test rows. Concretely, "
               '`mean`/icu `high invalid data` reads p=5.06e-05 (significant) from '
               '138 truncated rows where the paired CV computation over 1369 records '
               'gives p=0.964 (no evidence of a difference) — the published '
               'conclusion for that filter is inverted.'),
    recompute=('The legacy McNemar column and '
                 '`paper_figures/mcnemar_icu_mean.pdf`, or migrate the figure to the '
                 '`_cv` pickles, which already carry the paired statistic for all 5 '
                 'aggregations × 2 labels.'),
    technical=('`np.stack` at 223-224 succeeds because the four seeds of one arm '
                 'are all the same length (the split is cached, E-03). The '
                 'truncation happens at 230: `zip(base_majority, filter_majority)` '
                 'yields `min(4604, 138) = 138` pairs for `high invalid data`, and '
                 '`mcnemar(table, exact=True)` at 233 then reports a statistic of 19 '
                 '— consistent with a 138-row table, not a 4604-row one. Because of '
                 'E-04 the pairing is wrong even where lengths match. The '
                 'replacement, `calculate_mcnemar_paired` (531-614), intersects the '
                 "two arms' admission_id vectors (570), raises rather than truncates "
                 'on length disagreement (584-588), and tabulates correctness '
                 'against `labels_by_id` (590-606); '
                 '`Data/mimic-iii/mean/icu_filter_impact_cv_diagnostics.json` shows '
                 "`n_paired` exactly equal to each arm's `n_records` (1369 for `high "
                 'invalid data`, 20323 for `long gap`).\n'
                 '\n'
                 'First-pass measurements retained: For high invalid data that is '
                 "138 predictions against raw's 4,604, truncated without a word — "
                 'and the positions index different patients (see E-04). '
                 'calculate_mcnemar_paired now aligns on admission_id and raises on '
                 'mismatch. verify_cv.py asserts high invalid data pairs 1,369 of '
                 '1,369 rather than truncating.'),
    fix=('Delete `calculate_mcnemar_test` and call `calculate_mcnemar_paired` from '
           '`evaluate_filter_impact`; at minimum, raise on `len(base_majority) != '
           'len(filter_majority)` instead of zipping. Pairing requires the '
           'admission_id sidecars, which now exist for all five aggregations.'),
    verification=('`rerun/verify_cv.py:158-171` is the regression test — it '
                    'asserts `n_paired == number of predictions the shrunken arm '
                    'holds` rather than the truncated count. Add the negative case: '
                    'feed `calculate_mcnemar_test`-shaped unequal vectors and assert '
                    'it raises. Note guardrail 7: a green `g_verify_cv_*.log` alone '
                    'is not proof; the `n_paired == n_records` values in the `_cv` '
                    'diagnostics sidecar are.'),
    found='2026-08-11',
    fixed='2026-08-11 (new path only)',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C4',
        note=('Correction: truncation is half the defect — the table is also '
             'prediction-vs-prediction (E-06). Legacy p=5.06e-05 vs paired CV '
             'p=0.964 for high invalid data inverts the published conclusion.'),
    ),
),
dict(
    id='E-06', stage=EVAL, severity=HIGH, status=PARTIAL, verified=True,
    name='McNemar tabulated agreement, not correctness',
    overview=('`calculate_mcnemar_test` builds its 2x2 table from '
                '`table[baseline_prediction, filter_prediction]`, never touching '
                "`y_test`, so the exact binomial test is applied to the two models' "
                '*disagreement* cells (a test of marginal predicted-positive rate), '
                'not to their correctness cells. The resulting p-value is '
                'significant whenever a filter shifts how often the forest predicts '
                'positive — in either direction — and is reported by the notebook, '
                '`visualization_manager_v2.mcnemar_plot` and the paper figure as the '
                '"significance" of the filter\'s improvement. The CV path added '
                '2026-08-11 (`calculate_mcnemar_paired`) computes the '
                'correctness-based table, so this is a partial fix: the legacy path '
                'that produced every published number is still label-free.'),
    affects=('/home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Datas'
               'et-Processing/paper_figures/mcnemar_icu_mean.pdf (2026-08-10 22:14) '
               'and position [4] of '
               'Data/mimic-iii/*/{icu,mortality}_filter_impact.pkl (legacy, '
               '2026-08-10 21:38); the "McNemar Statistic/P-Value (Delta)" columns '
               'emitted by visualization_manager_v2.py:219-230 and the in-notebook '
               "`mcnemar_plot` charts (notebook.py:648, 689) while IMPACT_SUFFIX=''. "
               'The magnitude is material: legacy icu p-values are (arm order after '
               "'raw') 0.0019, 0.2067, 0.3370, 0.0719, 0.0, 0.0601, 0.7382, 0.0696, "
               '0.7994, 0.2896, 0.0001, 0.0035, whereas the correctness-paired CV '
               'pickle gives 0.0, 0.2052, 0.0036, 0.6997, 0.0051, 0.9225, 0.0, 0.0, '
               '0.0, 0.0, 0.9635, 0.0 — several arms flip from "not significant" to '
               'p≈0 and the arm with legacy p=1e-4 becomes p=0.96. (Those two '
               'pickles also differ in evaluation design, so the flip is not '
               'attributable to the label bug alone.)'),
    recompute=('If the legacy path is repaired, re-run '
                 'rerun/regen_filter_impact.py for both labels and all aggregations, '
                 'then Experiments/render_paper_figures.py fig_mcnemar_icu (and any '
                 'in-notebook mcnemar_plot cells). Nothing else needs recomputation '
                 '— accuracy/F1 positions are unaffected. If instead the project '
                 "migrates to IMPACT_SUFFIX='_cv', only the figure render needs "
                 're-running.'),
    technical=('evaluation_manager.py:223-227 stacks per-seed prediction vectors '
                 'and majority-votes each arm; :229-231 then increments '
                 '`table[baseline_prediction, filter_prediction]`, so the diagonal '
                 'is "both predict 0"/"both predict 1" and the off-diagonal cells '
                 'are the two disagreement directions. `mcnemar(table, exact=True)` '
                 'at :233 tests marginal homogeneity of that table, i.e. whether the '
                 'filtered model predicts positive at a different rate than the '
                 'baseline. Ground truth is available in the caller '
                 '(evaluate_filter_impact passes `[t[2] for t in trials]` at '
                 ':304-305 and ignores `t[3]`, the `y_test_host` returned at :198) '
                 "but is never forwarded. The function's own docstring at :215-217 "
                 'concedes "Note this compares predictions against each other, not '
                 'against ground truth — it detects that the two models disagree, '
                 'not which one is right", yet notebook.py:515-516 and '
                 '/home/ccampb47/work/noahNotes.md:448-460 present the same numbers '
                 "as the significance of a filter's improvement, and "
                 'visualization_manager_v2.py:311-320 renders them as "taller bars '
                 'mean more significant", so the code and the documented '
                 'interpretation disagree. The corrected formulation exists in the '
                 'CV path: evaluation_manager.py:590-606 computes '
                 '`baseline_correct`/`arm_correct` against `labels_by_id` and builds '
                 '`[[n_both_correct, n10], [n01, n_both_wrong]]`; '
                 'evaluate_filter_impact_cv calls it at :693-697. Prior art '
                 'describing the identical defect is '
                 '/home/ccampb47/work/hour_scaling_experiment/v2/metrics.py:189-217 '
                 '("v1 tabulated `table[y_pred_baseline, y_pred_variant]` ... ground '
                 'truth never entered the function"), which is the cited location — '
                 'that file is reference-only and not the live implementation. The '
                 'paper figure consumes the legacy pickle unconditionally at '
                 'render_paper_figures.py:386, so it is unaffected by the CV rework.\n'
                 '\n'
                 'First-pass measurements retained: Directional results now visible: '
                 'fill missing data n01=4,778 vs n10=2,740 (helps); respiration rate '
                 'n01=610 vs n10=1,031 (hurts).'),
    fix=('Give `calculate_mcnemar_test` the labels and tabulate correctness: '
           'change the signature to accept `y_true` (available as `t[3]`), compute '
           '`base_ok = base_majority == y_true` and `filter_ok = filter_majority == '
           'y_true`, and build `[[sum(base_ok & filter_ok), sum(base_ok & '
           '~filter_ok)], [sum(~base_ok & filter_ok), sum(~base_ok & ~filter_ok)]]` '
           'before `mcnemar(..., exact=True)`; guard the `n01 + n10 == 0` degenerate '
           'case as the CV path does at :608-611. This changes only pickle position '
           '[4] values, not the frozen 5-tuple shape (guardrail 4). Alternatively, '
           "retire the legacy McNemar entirely and switch IMPACT_SUFFIX to '_cv' — "
           'but then the docstring/notebook wording must stop calling the legacy '
           'numbers a significance test of improvement.'),
    verification=('Construct two synthetic majority-vote vectors that disagree on '
                    'many records while having identical accuracy against `y_true` '
                    '(a helpful and a harmful swap in equal number): the current '
                    'code returns a small p-value, the fixed code must return p≈1. '
                    'Conversely, make the filtered arm strictly better on a subset '
                    'of records it currently gets right, leaving all other '
                    'predictions equal, and the fixed test must return a small '
                    'p-value while the current code returns the same value either '
                    'way. Then confirm the regenerated legacy `mcnemar_results` '
                    'sign/ordering agrees with the `test_acc` deltas at position [1] '
                    'of the same pickle, and that `pickle.load` still unpacks '
                    'exactly five elements for comparison/pipeline_comparison.ipynb.'),
    found='POSTMORTEM.md 2.3',
    fixed='2026-08-11 (new path only)',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='solo pilot',
        note=('Fix boundary pinned: calculate_mcnemar_paired (CV) tabulates '
             'correctness; legacy calculate_mcnemar_test still label-free and feeds '
             'render_paper_figures.py:386 unconditionally.'),
    ),
),
dict(
    id='E-07', stage=EVAL, severity=HIGH, status=PARTIAL, verified=True,
    name='admission_id destroyed at tensorisation',
    overview=('`RecordEHR.to_tensor()` returns `(timeseries, labels)` and nothing '
                'else, and `create_raw_dataset`/`create_filter_dataset` store '
                'exactly that, so every `*_dataset_ehr.pkl` is an anonymous '
                '`list[(Tensor, Tensor)]`. Position is not a stable identity across '
                'arms because three filters drop records, which is why nothing '
                'downstream could pair two arms by patient. '
                '`rerun/regen_admission_ids.py` now reconstructs the id vectors into '
                '`*_admission_ids.npy` sidecars and `DatasetEHR.load_admission_ids` '
                'attaches them, but only the CV path reads them.'),
    affects=('Every cached `Data/mimic-iii/*/{raw,*_filtered}_dataset_ehr.pkl` '
               'remains id-less. Consequentially it affected the legacy McNemar '
               '(E-04, E-05), which is still the source of '
               '`paper_figures/mcnemar_icu_mean.pdf` and position 4 of '
               '`*_filter_impact.pkl`. It no longer affects the `_cv` artifacts.'),
    recompute=('Nothing outstanding for the sidecars — 13 ids × 5 aggregations '
                 'exist (`mean`, `median`, `standard deviation`, `mean deviation`, '
                 '`maximum deviation`, all 2026-08-11 14:44-14:46). Any *new* '
                 'aggregation, or any regeneration of a `*_dataset_ehr.pkl`, needs '
                 '`rerun/regen_admission_ids.py` re-run for it, and the sidecar will '
                 'otherwise be silently stale.'),
    technical=('The identity is discarded at ehr_record.py:41-48 (`to_tensor` '
                 'builds only a features tensor and a 2-element label tensor) and '
                 'the loss becomes permanent at dataset_manager.py:43, where the '
                 'record objects are replaced by their tensor tuples. '
                 '`DatasetEHR.save/load` round-trip only `self.data` '
                 '(ehr_dataset.py:105-108), so nothing is recoverable from the '
                 'pickle. The recovery path replays `processed_record_ehr.pkl` '
                 'through one shared `aggregate_filter` pass, re-runs only the three '
                 'record-dropping filters (regen_admission_ids.py:49, 132-144), and '
                 'hard-fails unless the replayed length *and* the full `[icu, '
                 'mortality]` matrix match the cached pickle (75-91) — which is what '
                 'makes the ids trustworthy rather than assumed. '
                 '`load_admission_ids` additionally rejects a length mismatch '
                 '(ehr_dataset.py:130-134). `evaluate_filter_impact_cv` requires the '
                 'ids and raises without them (evaluation_manager.py:657-662); '
                 '`evaluate_filter_impact` never mentions them. The sidecar design '
                 'is deliberate: `torch.save` writes a bare tensor list and torch '
                 '2.12 loads `weights_only=True`, so adding a field would break '
                 'existing readers (ehr_dataset.py:113-117).'),
    fix=('For the legacy path, load the sidecar in `evaluate_filter_impact` and '
           'pair on ids (or migrate the path away, per E-05). Longer-term, make '
           'identity intrinsic: have `to_tensor()` return the id, or have '
           '`DatasetEHR.save` write the `.npy` sidecar automatically alongside the '
           'pickle so it cannot go missing or stale.'),
    verification=('`rerun/verify_cv.py:96-114` checks id uniqueness, expected '
                    "per-arm counts (46032/31029/20323/1369), that each arm's ids "
                    "are an ordered subsequence of raw's, and that id count equals "
                    'tensor count. Add a check that every `*_dataset_ehr.pkl` has a '
                    'sidecar at least as new as it (currently the pickles are '
                    'Mar/Apr/Aug and the sidecars 2026-08-11, so this holds — but '
                    'nothing enforces it).'),
    found='2026-08-11',
    fixed='2026-08-11',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C4',
        note=('Downgraded RESOLVED->PARTIAL: admission_id recovery is an opt-in '
             'sidecar consumed only by the CV path; every cached pickle remains '
             'id-less and the legacy path never loads the sidecar.'),
    ),
),
dict(
    id='E-08', stage=EVAL, severity=MEDIUM, status=RESOLVED, verified=True,
    name='Even seed count biased the consensus toward the negative class',
    overview=('`calculate_mcnemar_test` collapses the per-seed prediction matrix '
                'with `scipy.stats.mode` over an even number of trials (four fixed '
                'seeds), and scipy resolves a modal tie by returning the smallest '
                'value — so every record where two seeds said 1 and two said 0 '
                'becomes a 0 in both consensus vectors. On a label whose prevalence '
                'is 9.66% the ties are concentrated in exactly the borderline '
                'positives the Youden threshold was introduced to recover, so the '
                'consensus vectors are systematically more negative than any of the '
                'forests that produced them.'),
    affects=('The McNemar statistic and p-value (position 4) in all ten legacy '
               '`Data/mimic-iii/<agg>/<label>_filter_impact.pkl` files, and '
               'therefore `paper_figures/mcnemar_icu_mean.pdf` (rendered from '
               '`icu_filter_impact.pkl` at `render_paper_figures.py:386`) plus the '
               'McNemar columns of every `filter_impact_table`. Accuracy and F1 '
               '(positions 0-3) are per-seed means and are untouched. Direction: tie '
               'records are forced concordant `(0,0)`, which deflates both '
               'off-diagonal cells of the 2×2 table and biases the exact binomial '
               'p-value toward non-significance.'),
    recompute=('`rerun/job_b_filter_impact.sh` (all five aggregations × two '
                 'labels) and `Experiments/render_paper_figures.py` for '
                 '`mcnemar_icu_mean.pdf`, if the legacy path is to be corrected '
                 'rather than retired.'),
    technical=('`evaluate_filter_impact` builds `current_preds = [t[2] for t in '
                 'trials]` (`evaluation_manager.py:304`) with one entry per seed '
                 'from `RANDOM_SEEDS` — four entries. `calculate_mcnemar_test` '
                 'stacks them (`:223-224`) and reduces along axis 0 with '
                 "`mode(...).mode[0]` (`:226-227`). scipy's `mode` returns the "
                 'smallest of the tied modal values; I reproduced this on scipy '
                 '1.17.0, the same major line the environment carries. The table is '
                 'then filled from those consensus labels at `:230-231`. Because '
                 'both `base_majority` and `filter_majority` are biased the same '
                 'way, the error is correlated rather than cancelling: records where '
                 'both arms were split 2-2 land in `table[0,0]`. The docstring at '
                 '`:206-209` states the vote was chosen deliberately over pooling, '
                 "but it does not mention the even-count tie; the CV path's "
                 'docstring (`:394-397`) names it explicitly as a bias it exists to '
                 'remove.'),
    fix=('In `calculate_mcnemar_test`, replace the label vote with a '
           'mean-of-scores consensus (as `evaluate_dataset_label_cv` does at '
           '`:485-497`), or, keeping the vote, break ties upward: `base_majority = '
           '(baseline_predictions.mean(axis=0) > 0.5).astype(int)` is still biased, '
           'so use `>= 0.5`, or simply use an odd number of seeds. Least invasive '
           'genuine fix: have `evaluate_dataset_label_impact` return the '
           'positive-class scores alongside the labels and average those.'),
    verification=('Count tie columns directly — for one arm, assert '
                    '`np.sum(np.sum(np.stack(preds),axis=0) == 2) == 0` after the '
                    'fix, or compare the old and new `n01`/`n10` counts on `mean` '
                    'ICU; with five seeds instead of four the p-value for at least '
                    'one arm should move. A regression test on a hand-built '
                    '`[[1,1,0,0]]` column asserting consensus `1` (or a documented '
                    'rule) pins the behaviour.'),
    found='2026-08-11',
    fixed='2026-08-11',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C5',
        note=('Independently re-derived from code by a blind verification agent; '
             'description updated where the re-derivation was more precise.'),
    ),
),
dict(
    id='E-09', stage=EVAL, severity=HIGH, status=OPEN, verified=True,
    name='Degenerate arms report 0.0 accuracy and plot as real bars',
    overview=('When a filter empties a dataset, `evaluate_dataset_label_impact` '
                'returns hard-coded `0.0` scores instead of NaN, and '
                '`evaluate_filter_impact` averages those into the five result lists; '
                '`filter_impact_plot` then subtracts the ~0.67-0.72 raw baseline and '
                'renders a red bar near −0.7 labelled `-0.6744`, indistinguishable '
                'from a filter that genuinely destroyed the model. Because the '
                'y-limits are derived from `deviations.min()/max()` '
                '(`visualization_manager_v2.py:277-284`), that one phantom bar '
                'expands the axis by two orders of magnitude and flattens the eleven '
                'real bars — which are all within ±0.03 — into invisible slivers.'),
    affects=('`high invalid data` in the three deviation aggregations (`standard '
               'deviation`, `mean deviation`, `maximum deviation`), both labels — '
               'six cached legacy pickles carry 0.0 at position 11, and the notebook '
               'gallery\'s "Filter Impact Results", the delta table '
               '(`filter_impact_table`, which computes `results[1][i] - '
               'results[1][0]` at `:216`) and the accuracy/F1 deviation charts for '
               'those aggregations are all wrong. The published '
               '`paper_figures/*_mean.pdf` are NOT affected: '
               '`render_paper_figures.py` reads only the `mean` aggregation, where '
               '`high invalid data` keeps 1,369 records (`n_train: 1095, n_test: '
               '138`).'),
    recompute=('Nothing must be recomputed to fix the reporting — the degenerate '
                 'arm is genuinely empty, so only the reducers and the plot need '
                 'changing, then re-render the affected notebook charts/tables. If '
                 'the sentinel is changed to NaN in the pickles, re-run '
                 '`rerun/job_b_filter_impact.sh` for the three deviation '
                 'aggregations.'),
    technical=('`high_invalid_data_filter` drops any record with >10% invalid '
                 'cells; under the deviation aggregations ~90% of cells are exactly '
                 '0, so the arm retains nothing — `Data/mimic-iii/mean '
                 'deviation/high_invalid_data_admission_ids.npy` is 128 bytes (a '
                 'bare .npy header, zero ids) versus 368,384 bytes for `raw`. '
                 '`evaluate_dataset_label_impact` catches this at `:167` and returns '
                 '`(0.0, 0.0, ...)` at `:170-171`; `evaluate_filter_impact` means '
                 'them into `training_averages`/`testing_averages` at `:292-293`, '
                 'and the F1 branches at `:297-300` append `0.0` because '
                 '`train_f1_list`/`test_f1_list` are empty. There is no `degenerate` '
                 'flag in the legacy 5-tuple and none of the plot or table helpers '
                 'checks `n_test`, so the value is consumed as data. In '
                 '`filter_impact_plot`, `deviations` at `:252` is `0.0 - 0.6744`; '
                 '`np.where(deviations < -epsilon, ...)` at `:254` colours it red '
                 'like any real regression, `:263` prints the number as a label, and '
                 '`:277-284` scale the axis to it.'),
    fix=("Return `float('nan')` rather than `0.0` from the `:167` branch (and from "
           'the empty-F1 fallbacks at `:299-300`), then have `filter_impact_table` '
           'render NaN as "n/a" and `filter_impact_plot` mask non-finite deviations '
           'out of both the bars and the `min/max` used for `set_ylim` — e.g. '
           '`finite = np.isfinite(deviations)` before `:277`, annotating excluded '
           'arms in the title or as a hatched zero-height bar. Note the plot needs '
           'this mask regardless of the sentinel: the `_cv` pickles already store '
           'NaN at position 11, and `deviations.min()` on a NaN array yields NaN, '
           'which `set_ylim` at `:284` cannot accept.'),
    verification=('Load `Data/mimic-iii/mean deviation/icu_filter_impact.pkl` and '
                    'assert position 11 is non-finite; then render '
                    '`filter_impact_plot` on it and assert the resulting '
                    '`ax.get_ylim()` spans less than 0.1 and that eleven (not '
                    'twelve) bars have finite heights. Cross-check against '
                    '`icu_filter_impact_cv_diagnostics.json`, which already reports '
                    '`"degenerate": true, "coverage": 0.0, "n_folds_fitted": 0` for '
                    'that arm.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C5',
        note=('Correction: published mean-aggregation PDFs unaffected (legacy 0.0 '
             'sentinel lives in deviation aggregations); CV pickles already store '
             'NaN, which the plot cannot handle either. Severity suggestion: Medium '
             'for paper.'),
    ),
),
dict(
    id='E-10', stage=EVAL, severity=MEDIUM, status=WONTFIX, verified=True,
    name=('`DatasetEHR.split` draws an unseeded, unstratified `randperm` and '
            'caches it on the weight tuple alone'),
    overview=('The split is only reproducible because callers happen to call '
                '`torch.manual_seed(seed)` immediately before it '
                '(`evaluation_manager.py:277`, '
                '`rerun/confusion_matrices_mean_raw.py:82`); nothing in `split` '
                "itself pins the RNG. It is also unstratified, so a small arm's 10% "
                'validation slice can be wildly off-prevalence, and because the '
                'cache key is `split_weights` only, the second through fourth '
                '"seeds" reuse the first seed\'s partition — the four-seed spread '
                'measures forest randomness, not sampling variability.'),
    affects=('All ten legacy `*_filter_impact.pkl` files and their diagnostics '
               'sidecars: the reported seed-to-seed variation is forest-only '
               '(visible as identical `n_train/n_validation/n_test` across seeds in '
               'every sidecar), and per-arm thresholds are all chosen on one fixed '
               'validation draw. Small arms are the worst hit — `standard '
               'deviation`/`mean deviation`/`maximum deviation` ICU `long gap` picks '
               'its threshold on 25 records that are 80% positive. '
               '`paper_figures/filter_impact_*_mean.pdf` inherit this.'),
    recompute=('Nothing — settled WONTFIX; the CV path '
                 '(`evaluate_filter_impact_cv`) is the supported route for anyone '
                 'who needs seeded, stratified, per-repeat-independent partitions.'),
    technical=('`split` (`ehr_dataset.py:56-97`) computes '
                 '`torch.randperm(len(self))` under `if self.split_weights != '
                 '(...)`, so (a) the permutation depends on ambient torch RNG state, '
                 '(b) index slicing at `:83-85` is positional with no class '
                 'balancing, and (c) any later call with the same `(0.8, 0.1, 0.1)` '
                 'returns the memoised `Subset`s. `evaluate_filter_impact` loops '
                 'seeds outer / arms inner (`:276-280`) with '
                 '`torch.manual_seed(seed)` at `:277`, which is what makes the arms '
                 'mutually comparable within a seed — but since each `DatasetEHR` '
                 'object caches after the first seed, seeds 985/439/81 re-serve seed '
                 "22's partition. `len(self)` differs per arm, so a single "
                 '`manual_seed` still yields different permutations per arm; the '
                 'arms are comparable only in the weak sense of "same RNG state '
                 'consumed", not "same patients". I confirmed the consequence in the '
                 'artifacts: no cached arm hit `validation_prevalence == 0` (so '
                 "`pick_threshold`'s documented 0.5 fallback at `:81-85` never fired "
                 'in the current results), but n=25 slices at 0.28 and 0.80 '
                 'prevalence are present.'),
    fix=('None for the legacy path, by decision. `Managers/partition_manager.py` '
           'is the replacement — `PARTITION_SEED = 20260811` (`:35`), '
           '`StratifiedKFold` per repeat, `project_to_arm` so every arm inherits the '
           "raw cohort's fold labels, and `fold_prevalences` reporting drift (raw's "
           '`max_fold_drift` is 6.3e-06 versus the legacy 0.42 excursion above).'),
    verification=('`python Managers/partition_manager.py` runs the module '
                    '`self_check`. For the legacy path, the invariant to assert if '
                    'it is ever revisited is that `split` takes an explicit `seed` '
                    'argument and that the cache key includes it.'),
    found='2026-08-10',
    audit=dict(
        date='2026-08-12', verdict='INTENTIONAL', mode='cluster C5',
        note=('Verdict INTENTIONAL (docstring and caller comments document the '
             "behaviour) but the register's WONTFIX predates the audit and already "
             'records the decision; keeping WONTFIX.'),
    ),
),
dict(
    id='E-11', stage=EVAL, severity=HIGH, status=OPEN, verified=True,
    name='No class weighting anywhere on a 10%-prevalence problem',
    overview=('Every forest in the repository is constructed as '
                '`RandomForestClassifier(n_estimators=300, random_state=seed)` with '
                'no `class_weight`, and there is no resampling or `sample_weight` '
                'call anywhere under `pipelines/EHR-Dataset-Processing/`. The trees '
                'are therefore grown to minimise unweighted impurity on a cohort '
                'that is 90.3% negative for mortality, so the minority class '
                'contributes almost nothing to any split decision; the imbalance is '
                'addressed only after the fact, by moving the decision threshold.'),
    affects=('Every mortality number in the repo — all ten legacy pickles, all ten '
               '`_cv` pickles, and '
               '`paper_figures/filter_impact_mortality_testing_{accuracy,f1}_mean.pdf`'
               '. The consequence is a low-ceiling minority-class model: mortality '
               'macro F1 sits at 0.52-0.59 across arms even at the Youden threshold, '
               'and the reported `test_positive_rate` (e.g. 0.288 for `mean` raw '
               'against a true prevalence of 0.0997) shows the threshold is being '
               'dragged far off 0.5 to compensate for a classifier that was never '
               'trained to care about positives. ICU (~37.7% prevalence) is much '
               'less affected.'),
    recompute=('Everything downstream of model fitting if adopted: '
                 '`rerun/job_f_filter_impact_cv.sh` (and `job_b` for the legacy '
                 'path), the confusion workbook '
                 '(`rerun/export_confusion_workbook.py`), and the mortality panels '
                 'of `Experiments/render_paper_figures.py`. Absolute scores would '
                 'move, so pre- and post-fix results are not comparable.'),
    technical=('The three fit sites are `cross_validate_model` (`:55`), the legacy '
                 'final model (`:175`) and the CV fold model (`:444`); all three '
                 'pass only `n_estimators` and `random_state`. The repo-wide grep '
                 'confirms no weighting or resampling anywhere in this pipeline. The '
                 'mitigation that does exist is decision-level: `pick_threshold` '
                 "(`:63-96`) maximises Youden's J on a validation slice never used "
                 "for scoring, and every reported F1 is `average='macro'` (`:193`, "
                 '`:298`, `:463`, with the rationale at `:294-296`). That is a real '
                 'and deliberate half of the standard fix — the POSTMORTEM bundles '
                 '"no class weighting **and** no threshold selection" as one cause, '
                 'and only the second half has been addressed here. It is not a '
                 'substitute: thresholding reweights a fixed score function, it does '
                 'not change what the trees learned to split on. Feasibility note: '
                 'through `rerun/_cpu_backend.py:66-79` — which is the backend all '
                 'current artifacts were produced with, since nibi has no cuML — '
                 "`RandomForestClassifier` forwards `**kwargs` to sklearn's, so "
                 "`class_weight='balanced'` would work today; cuML's own forest has "
                 'no such parameter, so the GPU path would need resampling or a '
                 'balanced-subsample equivalent instead.\n'
                 '\n'
                 'First-pass measurements retained: POSTMORTEM.md 2.4 flagged this '
                 'for v1; grep confirms it is still absent.'),
    fix=("Add `class_weight='balanced_subsample'` to the three constructors "
           '(guarded so the cuML path degrades to explicit minority oversampling of '
           'the fit split), and report PR-AUC / recall at fixed precision alongside '
           'accuracy so the minority class is visible in the outputs rather than '
           'only in the threshold.'),
    verification=('Re-fit one arm with and without weighting on the same fold and '
                    "compare mortality recall and macro F1 at the fold's own "
                    'threshold; the weighted model should reach comparable macro F1 '
                    'at a threshold much closer to 0.5. Check that `mean_threshold` '
                    'in the `_cv` diagnostics moves toward 0.5 — currently 0.112 for '
                    '`mean deviation` raw mortality — which is the direct signature '
                    'of the classifier, not the threshold, doing the balancing.'),
    found='POSTMORTEM.md 2.4, still live',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C5',
        note=('Corrections: threshold half of the POSTMORTEM complaint IS fixed '
             '(pick_threshold, both paths); cpu backend forwards class_weight so the '
             'fix is feasible today. Severity suggestion: Medium.'),
    ),
),
dict(
    id='E-12', stage=EVAL, severity=MEDIUM, status=INTENTIONAL, verified=True,
    name=("Raw arm carries unfiltered vitals because it is the experiment's "
            'control, not a clean baseline'),
    overview=('In the live filter-impact experiment the `raw` dataset is built by '
                'aggregation only (`create_raw_dataset`, no filter call), so it does '
                'retain out-of-range vital readings. That is the intended '
                "construction: the experiment's entire question is what the seven "
                'per-vital outlier filters and the `all vitals` combined arm buy you '
                '*relative to* an unfiltered control, so outlier-free raw data would '
                'erase the contrast being measured. No number or figure is wrong as '
                'a result.'),
    affects=('Nothing is wrong. `Data/mimic-iii/<agg>/raw_dataset_ehr.pkl` and the '
               'index-0 `raw` entries in `*_filter_impact.pkl` / '
               '`*_filter_impact_cv.pkl`, and `centroids/<label>_raw_<sign>.pkl`, '
               'are all unfiltered by design and are consumed only as the "before" '
               'side of a delta (Experiments/render_paper_figures.py:216-219, :390 '
               '`p_values = [x[1] for x in impact[-1]][1:]  # drop raw baseline`). '
               "The one thing a reader must not do is quote the raw arm's mean "
               'centroid as a descriptive statistic of the cohort — '
               '`compute_dataset_centroid` (Managers/evaluation_manager.py:745) '
               'averages per-patient centroids, so extreme values do move it; that '
               'is the shift the filtered arms are supposed to reveal.'),
    recompute='Nothing.',
    technical=('`create_raw_dataset` (Managers/dataset_manager.py:28-45) calls '
                 'only `aggregate_filter(records, aggregation_method)` then '
                 '`to_tensor()`; no member of `FILTERS` touches it, and its '
                 'docstring states that explicitly at :29-33. The seven range '
                 'filters do exist and do work — `_remove_outliers` '
                 '(Managers/ehr_filter_manager.py:32-49) prunes values outside '
                 '`vitals[name][0]` at the reading level, and '
                 '`apply_dataset_filter.py:61` routes the first seven `FILTERS` '
                 'entries pre-aggregation — but they are applied to build the '
                 '*filtered* arms only (Experiments/apply_dataset_filter.py:66, '
                 'Experiments/notebook.py:407-411). `evaluate_filter_impact` '
                 '(Managers/evaluation_manager.py:239-243, :264-265) and '
                 '`evaluate_filter_impact_cv` (:645-655) both construct '
                 "`ordered_names = ['raw'] + list(filtered_datasets.keys())` and "
                 'describe `raw` as "the unfiltered baseline" that plotting slices '
                 '`[1:]` to drop. The disk state matches: `Data/mimic-iii/mean/` '
                 'holds `raw_dataset_ehr.pkl` alongside `heart_rate_…`, '
                 '`temperature_…` and `all_vitals_filtered_dataset_ehr.pkl`, i.e. '
                 'control plus per-vital and combined outlier-filtered treatment '
                 'arms. Documentation agrees with the code on every point: '
                 'notebook.py:301-303 ("raw meaning *unfiltered*"), '
                 'notebook.py:506-508 ("For each filter, train a random forest and '
                 'ask whether it beats the unfiltered baseline"), and '
                 'noahNotes.md:440/:452 ("the scores from its filter impact analysis '
                 'are compared to the raw dataset\'s scores"). The cited source of '
                 'the claim, '
                 '/home/ccampb47/work/hour_scaling_experiment/POSTMORTEM.md:161-163, '
                 'is about a different experiment where the unfiltered dataset was '
                 'the sole *training substrate* for an hours-of-history sweep rather '
                 'than a control arm — there the outliers corrupted the quantity '
                 'under study, which is why v2 added filtering (POSTMORTEM.md:222). '
                 'That directory is prior-art-only per guardrail 8, and its finding '
                 'does not transfer to the live design.\n'
                 '\n'
                 'First-pass measurements retained: POSTMORTEM.md 2.7b recorded '
                 'observed maxima of 23,353 (mean) and 69,802 (maximum deviation) on '
                 'the unfiltered arm.'),
    fix=('No code change. If anything is worth changing it is documentation, not '
           'behaviour: add a line to REPO/README.md "Things that will bite you" '
           '(currently :79-83) stating that `raw` is the deliberately unfiltered '
           'control, that the `all vitals` arm is the outlier-clean counterpart, and '
           'that raw-arm centroids/means are therefore outlier-influenced by '
           'construction and must never be quoted as cohort descriptive statistics.'),
    verification=('Not applicable — nothing to fix. To re-confirm the design at '
                    'any time: check that `create_raw_dataset` still calls no member '
                    "of `FILTERS`, that `ordered_names[0] == 'raw'` in both "
                    'evaluation paths, and that '
                    '`all_vitals_filtered_dataset_ehr.pkl` is present in each '
                    '`Data/<dataset>/<agg>/` so the outlier-clean contrast arm '
                    'exists.'),
    found='POSTMORTEM.md 2.7b',
    audit=dict(
        date='2026-08-12', verdict='INTENTIONAL', mode='cluster C5 + solo tie-breaker',
        note=('Escalated and independently confirmed INTENTIONAL by a solo '
             'tie-breaker. The `raw` arm is built by `create_raw_dataset` '
             '(Managers/dataset_manager.py:28-45), which calls no member of FILTERS '
             "by design; it is the experiment's control, and the outlier-clean "
             'counterpart already exists as the `all vitals` treatment arm '
             '(ehr_filter_manager.py:292-317, wired in at notebook.py:364). Code and '
             'documentation agree throughout — notebook.py:301-303 and :506-508, '
             'dataset_manager.py:29-33, evaluation_manager.py:239-243 and :645-646, '
             'noahNotes.md:440/:452 — so guardrail 10 is satisfied. The POSTMORTEM '
             'finding it was drawn from concerns a different experiment where the '
             'unfiltered data was the sole training substrate, not a control arm. '
             'Documentation-only follow-up suggested: state in REPO/README.md that '
             'raw-arm centroids are outlier-influenced by construction and must not '
             'be quoted as cohort descriptives. Reclassification confirmed by an '
             'independent solo tie-breaker agent.'),
    ),
),
dict(
    id='E-13', stage=EVAL, severity=LOW, status=OPEN, verified=True,
    name='Legacy cross_validate_model guards an unreachable case',
    overview=('Its empty-fold branch cannot fire, while the hazard that can — a '
                'single-class fold — is unguarded.'),
    affects=('Position 0 of every legacy pickle (`training_averages`, i.e. the '
               '4-fold CV score) for small arms — `long gap` and `long missing '
               'segment` under the deviation aggregations have `n_train` of 200 and '
               '293 respectively. Nothing is provably wrong in the current '
               'artifacts: at 9.7% mortality prevalence a 150-row fold-training set '
               'still expects ~15 positives, so I found no evidence the single-class '
               "case actually fired. The dead branch also makes the docstring's "
               'advice ("a suspiciously low CV score … may mean \'folds were empty\'") '
               'misleading — it cannot mean that.'),
    recompute=('Nothing. This is a latent robustness gap plus a documentation '
                 'contradiction, not a wrong number in the cached results.'),
    technical=('`cross_validate_model` (`:33-60`) splits with '
                 '`cuml.model_selection.KFold(n_splits=4, shuffle=True, '
                 'random_state=seed)` and tests `x_train.size == 0 or '
                 'x_validation.size == 0` at `:51`. `size` on a `(n, 168)` array is '
                 '`n*168`, so it is zero only for a completely empty fold. The sole '
                 'caller, `evaluate_dataset_label_impact`, returns at `:167-171` '
                 'whenever `x_train.size == 0`, so `cross_validate_model` is never '
                 'reached with an empty dataset; for `n >= 4` KFold folds are all '
                 'non-empty, and for `1 <= n < 4` KFold raises before any guard can '
                 'run — I confirmed both with the sklearn `KFold` that '
                 "`rerun/_cpu_backend.py:92` substitutes for cuML's on the machine "
                 'every cached result was produced on. The unguarded hazard is at '
                 '`:55-58`: `RandomForestClassifier(...).fit(x_train, y_train)` with '
                 'single-class `y_train` produces a constant predictor, and '
                 '`accuracy_score` happily returns the validation majority fraction, '
                 'so the fold contributes a meaningless number instead of being '
                 'skipped. That the hazard is understood is clear from two places '
                 'that *do* guard it: `_positive_scores` handles a single-class '
                 '`classes_` at `:116-118`, and the CV path skips such folds '
                 'outright at `:438-442` (`if fit_positions.size == 0 or '
                 'len(np.unique(y_fit)) < 2: continue`). It is also unstratified '
                 '`KFold` rather than `StratifiedKFold`, which is what makes a '
                 'single-class fold reachable at all.\n'
                 '\n'
                 'First-pass measurements retained: evaluation_manager.py:51-53 '
                 'handles empty folds, but KFold raises rather than yielding them, '
                 "so the 0.0 path is dead and the docstring's advice ('a "
                 "suspiciously low CV score may mean folds were empty') misleads."),
    fix=('Replace the dead branch with the real one — `y_fold = '
           'labels[training_index]; if len(cp.unique(y_fold)) < 2: continue` (skip, '
           'and return NaN if no fold survived) — and switch to `StratifiedKFold`, '
           'or drop `cross_validate_model` entirely, since position 0 of the legacy '
           'tuple is already known to be a mislabelled column and the CV path has '
           'superseded it.'),
    verification=('Call `cross_validate_model` on a hand-built single-class 10-row '
                    'arm and assert it returns NaN (or raises) rather than a '
                    'plausible-looking accuracy; assert the empty-fold branch is '
                    'unreachable by covering the function and confirming lines 52-53 '
                    'never execute across a full sweep.'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C5',
        note=('Empty-fold branch proven unreachable (caller returns early; KFold '
             'raises for n<4); real hazard is single-class fold, guarded only in the '
             'CV path.'),
    ),
),
dict(
    id='N-01', stage=EVAL, severity=CRITICAL, status=INTRODUCED, verified=True,
    name='Plotted accuracy and F1 compare arms on different cohorts',
    overview=("Each arm's accuracy is measured over the records it kept, so "
                "subtracting raw's accuracy measures cohort difficulty. Every "
                "record-dropping arm's bar has the wrong sign."),
    affects=('`Data/mimic-iii/*/{icu,mortality}_filter_impact_cv.pkl` positions '
               '[1] and [3], and the legacy `*_filter_impact.pkl` (legacy is worse: '
               '`high invalid data` scores 138 test records at prevalence 0.2101 '
               "against raw's 4,604 at 0.0997). "
               '`paper_figures/filter_impact_{icu,mortality}_testing_{accuracy,f1}_mea'
               'n.pdf` and the "Testing Accuracy/F1 Delta" columns of '
               '`filter_impact_table`. Concretely, in '
               '`Data/mimic-iii/mean/mortality_filter_impact_cv_diagnostics.json`: '
               '`long gap` plots −0.0305 but its paired delta is +0.0302; `long '
               'missing segment` plots −0.0359, paired +0.0384; `high invalid data` '
               'plots +0.0009, paired +0.1980. Across the 24 record-dropping arm '
               'cells in the ten CV sidecars, 19 flip sign and 2 more are wrong by '
               '25×–220×.'),
    recompute=('Re-derive positions [1]/[3] from the shared-record intersection '
                 'with raw, then regenerate all ten CV pickles/sidecars (or '
                 'recompute from the existing `*_oof_scores_cv.npz`, no refitting '
                 'needed) and re-render the four `filter_impact_*` figures plus both '
                 'impact tables. The legacy pickles cannot be salvaged this way — '
                 'they have no paired predictions on disk — so the legacy sweep '
                 'needs a rerun or the figures need to be sourced from CV.'),
    technical=('`evaluate_dataset_label_cv` builds `oof_predictions` over the '
                 "arm's own record list (evaluation_manager.py:413-414, 456-457). "
                 "The per-repeat reducer at 468-480 masks to `covered` — the arm's "
                 'retained records — and computes `accuracy`/`f1_macro` there; '
                 '`_mean_of_finite` folds those into '
                 "`diagnostics['accuracy_mean']`/`['f1_macro_mean']` (504, 506). "
                 '`evaluate_filter_impact_cv` appends those straight into positions '
                 '[1] and [3] (689, 691). `filter_impact_plot` then does `deviations '
                 '= filtered_scores - baseline_scores` with `baseline_scores = '
                 'scores[0]` (visualization_manager_v2.py:247, 252), i.e. arm-cohort '
                 'accuracy minus raw-cohort accuracy. `calculate_mcnemar_paired` '
                 'does align the two arms on `np.intersect1d` of admission ids (570) '
                 "and records both arms' accuracy on that intersection (599-600), "
                 'but those keys only reach the JSON sidecar via line 700-706; a '
                 'repo-wide grep shows `accuracy_on_paired` is referenced nowhere '
                 'outside evaluation_manager.py. The same confound is structural in '
                 'the legacy path, where each arm calls `dataset.split(0.8, 0.1, '
                 '0.1)` on its own dataset (149) so the test sets are different '
                 'sizes and different patients entirely '
                 '(`mortality_filter_impact_diagnostics.json`: n_test 138 / 2033 / '
                 '3104 / 4604 with test prevalence 0.2101 / 0.1136 / 0.1118 / '
                 '0.0997). `rerun/verify_cv.py` checks fold inheritance, coverage '
                 'and McNemar pairing but has no check at all that the reported '
                 'accuracy/F1 columns are computed on a common record set.\n'
                 '\n'
                 'First-pass measurements retained: The retained cohorts are not '
                 'exchangeable: high invalid data has mortality prevalence 0.194 '
                 "against the population's 0.097; long gap under maximum deviation "
                 'has 0.323. Verified from the sidecars (mortality):\n'
                 '  mean / long missing segment   plotted -0.0359   paired +0.0384   '
                 'SIGN FLIP\n'
                 '  mean / long gap               plotted -0.0305   paired +0.0302   '
                 'SIGN FLIP\n'
                 '  mean / high invalid data      plotted +0.0009   paired +0.1980   '
                 '218x\n'
                 '  std  / long missing segment   plotted -0.0392   paired +0.3052   '
                 'SIGN FLIP\n'
                 '  std  / long gap               plotted -0.1195   paired +0.2669   '
                 'SIGN FLIP\n'
                 '  max  / long missing segment   plotted -0.0553   paired +0.2888   '
                 'SIGN FLIP\n'
                 '  max  / long gap               plotted -0.1019   paired +0.2709   '
                 "SIGN FLIP The reader sees 'accuracy -0.036, p=1.3e-147' — a large, "
                 'significant harm — beside a correctly paired McNemar saying the '
                 'filter helped.'),
    fix=('In `evaluate_filter_impact_cv`, compute positions [1] and [3] on the '
           "intersection of the arm's covered records with raw's covered records — "
           'the same index set `calculate_mcnemar_paired` already builds — and '
           'report the raw baseline restricted to that same set alongside it (a '
           "per-arm baseline, not one global scalar). Keep the arm's own-cohort "
           'accuracy in diagnostics under a distinct key. `filter_impact_plot` must '
           'then take a per-arm baseline vector rather than `scores[0]`, or receive '
           'pre-computed deltas.'),
    verification=('For every arm assert `accuracy_delta == '
                    "diagnostics[arm]['mcnemar']['arm_accuracy_on_paired'] - "
                    "diagnostics[arm]['mcnemar']['baseline_accuracy_on_paired']` to "
                    'within float tolerance; assert the delta for `raw` is exactly '
                    '0; recompute both quantities independently from '
                    '`*_oof_scores_cv.npz` for `mean/mortality` and check that `long '
                    'gap` and `long missing segment` come out positive. Add that '
                    'assertion to verify_cv.py section 6.'),
    found='2026-08-11, two agents independently; verified from the sidecars',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C6',
        note=('19 of 24 record-dropping arm cells flip sign when properly paired; '
             'correctly-paired quantities already computed in the mcnemar detail '
             'dict but unread.'),
    ),
),
dict(
    id='N-02', stage=EVAL, severity=HIGH, status=INTRODUCED, verified=True,
    name=('The accuracy column and the McNemar column describe different '
            'classifiers'),
    overview=('Accuracy comes from per-fold thresholded predictions; McNemar comes '
                'from averaged scores at an averaged threshold. On identical records '
                'they differ by more than most of the effects being claimed.'),
    affects=('Position [4] of all ten `*_filter_impact_cv.pkl`, '
               "`diagnostics[arm]['mcnemar']` in all ten "
               '`*_filter_impact_cv_diagnostics.json`, and the McNemar plot / '
               '"McNemar Statistic" and "McNemar P-Value" table columns whenever '
               "`IMPACT_SUFFIX='_cv'` is used. Restricting to arm cells where the "
               "McNemar pairing covers the arm's entire record set (so the record "
               'set is identical by construction), `arm_accuracy_on_paired − '
               'accuracy_mean` has median magnitude 0.0060 and reaches +0.0940 '
               '(`standard deviation/mortality`, `long missing segment`) — and '
               "exceeds the arm's own plotted effect size in 68 of 124 cells. For "
               '`mean/mortality` raw: `accuracy_mean` 0.6868 vs '
               '`baseline_accuracy_on_paired` 0.6945 on the same 46,032 records.'),
    recompute=('Nothing needs refitting — both prediction rules are derivable from '
                 '`*_oof_scores_cv.npz`. Pick one rule, recompute positions [1]/[3] '
                 'and [4] consistently, and rewrite the ten CV pickles/sidecars.'),
    technical=('Inside `evaluate_dataset_label_cv`, the out-of-fold label for a '
                 'record in repeat r is `(test_scores >= threshold)` where '
                 "`threshold` is that fold's own `pick_threshold` result (451, 457). "
                 'Those are what the per-repeat reducer scores (470-479) and what '
                 'becomes `accuracy_mean`/`f1_macro_mean` (504, 506) → positions '
                 '[1]/[3] (689, 691). Separately, lines 485-497 average the '
                 'per-repeat scores into `consensus_scores` and threshold them once '
                 'at `mean_threshold = np.mean(list(thresholds.values()))` (492) to '
                 'make `consensus_predictions`; that is the only vector '
                 '`calculate_mcnemar_paired` ever sees (693-696), and '
                 '`n01`/`n10`/the p-value are computed from it against ground truth '
                 '(590-606). Two independent sources of divergence: score averaging '
                 'across repeats (a variance-reduced classifier) and thresholding at '
                 'an averaged threshold rather than per-fold thresholds. The '
                 'empirical size of the divergence is directly visible in the '
                 'sidecars because `mcnemar.arm_accuracy_on_paired` and '
                 '`accuracy_mean` are computed on the same records for every '
                 'full-cohort arm — see the numbers under "affects". The docstring '
                 'at 636-643 asserts "Positions 0 and 1 now describe one classifier '
                 'at one operating point", which is true of [0] vs [1] but says '
                 'nothing about [4]; the mismatch it fixed for [0]/[1] was '
                 'reintroduced between [1] and [4].\n'
                 '\n'
                 'First-pass measurements retained: Measured on raw/mean, the same '
                 '46,032 records:\n'
                 '  accuracy_mean                = 0.6868\n'
                 '  baseline_accuracy_on_paired  = 0.6945\n'
                 'a 0.0077 gap, larger than 8 of the 12 filter effects.'),
    fix=('Derive both the reported accuracy/F1 and the McNemar table from one '
           'prediction vector. The cleanest option is to make '
           '`consensus_predictions` the single reported classifier — report its '
           'accuracy/F1 (with a bootstrap or per-repeat CI) and keep the per-repeat '
           'vectors only as a stability diagnostic. Alternatively run McNemar per '
           'repeat on `oof_predictions[repeat]` and combine, but that loses the '
           'paired-consensus simplicity.'),
    verification=('Assert '
                    "`abs(diagnostics[arm]['mcnemar']['arm_accuracy_on_paired'] - "
                    'reported_accuracy[arm]) < 1e-9` for every arm whose `n_paired '
                    '== n_records`; add that assertion to verify_cv.py section 6, '
                    'where it currently fails on 124/124 such cells.'),
    found='2026-08-11 statistical audit; verified from the sidecars',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C6',
        note=('Divergence measured: median 0.0060, max +0.0940, exceeds the plotted '
             'effect in 68 of 124 cells.'),
    ),
),
dict(
    id='N-03', stage=EVAL, severity=HIGH, status=INTRODUCED, verified=True,
    name='accuracy_std is threshold-selection noise presented as an error bar',
    overview=('Every repeat predicts the *same* record set out-of-fold (coverage '
                '1.0 in all ten sidecars), so the spread across the four per-repeat '
                'accuracies contains zero sampling variability — it is driven almost '
                "entirely by how each repeat's 5 Youden thresholds happened to land. "
                'Presented as "+/- across repeats" it reads as an error bar on the '
                'accuracy, so a reader will discount effects against a number that '
                'measures threshold instability instead.'),
    affects=('`accuracy_std` and `f1_macro_std` in all ten '
               '`Data/mimic-iii/*/*_filter_impact_cv_diagnostics.json`, and the '
               '`+/-` figure printed for the raw arm in every stage-F job log. No '
               'plotted figure consumes it (grep: `accuracy_std` appears only at '
               'evaluation_manager.py:505 and regen_filter_impact_cv.py:112), so '
               'this misleads readers of the sidecar/log rather than corrupting a '
               'published number.'),
    recompute=('Nothing needs refitting. A correct interval (bootstrap over '
                 'records, or a binomial SE) is derivable from '
                 '`*_oof_scores_cv.npz`; recomputing the two `*_std` keys in the ten '
                 'sidecars is enough.'),
    technical=("`per_repeat[r]['accuracy']` is `np.mean(y_pred == y_true)` over "
                 '`covered = oof_predictions[repeat] >= 0` (470-479). Because the '
                 'partition inherited from `build_fold_assignment` covers every '
                 'record in every repeat (partition_manager.py:99-103, and '
                 '`n_folds_fitted == 20`, `coverage == 1.0` in all non-degenerate '
                 'arms), `covered` is identical for r = 0..3 and `n` is identical in '
                 'every `per_repeat` entry — e.g. `mean/mortality` raw records n = '
                 '46032 four times. So `_std_of_finite` (505) is a spread over four '
                 'estimates of the same population quantity on the same sample: it '
                 'can only reflect model and threshold variation. That the threshold '
                 'dominates is directly measurable in the sidecars: grouping '
                 "`thresholds['r{r}f{f}']` by repeat and correlating each repeat's "
                 "mean threshold with that repeat's accuracy gives r = 1.000 for "
                 '`mean/mortality` raw (thresholds 0.110/0.137/0.106/0.118 against '
                 'accuracies 0.6665/0.7364/0.6563/0.6881), 0.997 for `fill missing '
                 'data`, 0.999 for `heart rate`, and 0.95–0.999 for the icu arms. '
                 'Corrections to the claim: the "fifteen times the sampling standard '
                 'error" figure is specific to `mean/mortality` (raw 0.0308 against '
                 'a binomial SE of 0.00216 = 14.3×) and does not generalise — across '
                 'the ten aggregation/label cells the ratio runs 1.1×–14.3×, median '
                 '3.5×, with all five ICU cells at 1.1×–1.7×. Likewise "larger than '
                 'eleven of the twelve effects" is 10 of 12 in `mean/mortality` and '
                 'as low as 1 of 12 in `median/icu`. The mechanism (wrong quantity, '
                 'zero sampling content) holds in all ten cells regardless of '
                 'magnitude. The comment at 465-467 calling this "the honest error '
                 'bar" contradicts what the code computes.\n'
                 '\n'
                 'First-pass measurements retained: Raw/mean reports 0.6868 +/- '
                 '0.0308. Every repeat scores all 46,032 records out-of-fold, so '
                 'cohort sampling contributes nothing to the spread. The binomial SE '
                 'at n=46,032, p=0.69 is 0.0021 — the observed value is ~15x that, '
                 'and it is threshold-selection noise (see N-04), not partition '
                 'noise. Four further problems in the same number: _std_of_finite '
                 'uses ddof=0 on n=4 (biased ~13% low); it is an SD but printed as '
                 "'+/-' next to a mean; it excludes cohort sampling variance "
                 "entirely, which is the dominant uncertainty for a claim like 'this "
                 "filter improves accuracy by 0.003'; and it silently computes from "
                 '1 or 2 values if repeats degenerate, without saying so.'),
    fix=('Replace `accuracy_std`/`f1_macro_std` with a record-level uncertainty — '
           'a stratified bootstrap over admission ids on the consensus predictions, '
           'or at minimum the binomial SE — and rename the per-repeat spread to '
           'something explicit like `accuracy_repeat_spread`, documenting it as '
           'threshold/model stability. Correct the 465-467 comment and the `+/-` '
           'label at regen_filter_impact_cv.py:112.'),
    verification=("Assert `len({r['n'] for r in per_repeat}) == 1` and then that "
                    'the emitted uncertainty scales as 1/sqrt(n) when the arm is '
                    'subsampled (the current statistic does not); check that the '
                    'recomputed raw interval for `mean/mortality` is ~0.002 rather '
                    'than 0.031, and that shuffling only the fold thresholds while '
                    'holding the forests fixed leaves the new interval unchanged.'),
    found='2026-08-11 statistical audit; verified from the sidecars',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C6',
        note=('Magnitude corrections: 15x sampling-SE ratio is mean/mortality only '
             '(range 1.1-14.3x, median 3.5x); threshold-accuracy correlation '
             'r=0.95-1.000. Severity suggestion: Medium (nothing plotted consumes '
             'accuracy_std).'),
    ),
),
dict(
    id='N-04', stage=EVAL, severity=HIGH, status=INTRODUCED, verified=True,
    name='The inner-split guard protects the wrong quantity',
    overview=('It checks class counts in the outer training fold, not in the '
                "validation slice it carves out — so its real guarantee is 'at least "
                "one positive', and thresholds swing wildly on small arms."),
    affects=("Every threshold in `diagnostics[arm]['thresholds']` and "
               '`mean_threshold` in all ten `*_filter_impact_cv_diagnostics.json`, '
               'hence positions [1]/[3] (per-fold thresholded OOF predictions) and '
               '[4] (consensus at the mean threshold) of all ten '
               '`*_filter_impact_cv.pkl`. Worst observed: `maximum '
               'deviation/mortality`, `long missing segment` (367 records, '
               'prevalence 0.0899) — the outer training fold holds ~26 positives so '
               'the guard passes, the inner-validation slice gets ~37 records with '
               '~3 positives, and the 20 fold thresholds span 0.007–0.303, a 43× '
               'range, with `accuracy_std` 0.0929. `standard deviation/icu`, `long '
               'gap` (251 records): thresholds 0.370–0.810. The same guard is used '
               'by the legacy path only indirectly (legacy uses a fixed 10% '
               'validation split), so this is CV-path-specific.'),
    recompute=('Fixing the guard changes the thresholds, hence every prediction — '
                 'all ten stage-F tasks must be refit '
                 '(`rerun/job_f_filter_impact_cv.sh`), and the CV pickles, sidecars '
                 'and `*_oof_scores_cv.npz` regenerated. The `.npz` cannot be reused '
                 'because the fit/validation partition itself changes.'),
    technical=('`inner_split` computes `fold_labels = labels[training_positions]` '
                 'and tests `positives`/`negatives` in *that* set against `minimum = '
                 'max(2, ceil(1/INNER_VALIDATION_SHARE)) = 8` '
                 '(partition_manager.py:156-163). It then calls '
                 '`train_test_split(..., test_size=1/8, stratify=fold_labels)` '
                 '(165-170), so the validation slice receives 1/8 of each class: '
                 'with the guard exactly satisfied the slice contains 1 positive and '
                 '1 negative, and the guard never inspects the slice at all. '
                 '`evaluate_dataset_label_cv` passes the slice to `pick_threshold` '
                 '(evaluation_manager.py:447-451), whose own guard only rejects the '
                 'empty and fully-single-class cases (81-85), so a 1-positive slice '
                 "sails through: `roc_curve` on one positive makes Youden's J "
                 'maximal at whatever score that single record received, and '
                 '`thresholds[f"r{repeat}f{fold}"]` is that score. Because the '
                 'threshold is the near-sole determinant of accuracy at these '
                 'prevalences (per-repeat mean threshold vs per-repeat accuracy '
                 'correlates at r = 0.95–1.000 across the arms I checked, see N-03), '
                 'the noise propagates straight into positions [1] and [3]. The '
                 'docstring at 149-153 claims the fallback path is what protects '
                 'small arms ("Falls back to using the training set itself when it '
                 'is too small"), but the fallback triggers on the training fold\'s '
                 'counts, so the actual small-slice case is exactly the one it does '
                 'not catch. `partition_manager.self_check` (256-265) only tests the '
                 'inner split on the full 46k raw cohort, where the guard is never '
                 'near binding.\n'
                 '\n'
                 'First-pass measurements retained: Observed threshold spread across '
                 'the 20 folds of one arm (mortality):\n'
                 '  mean / raw                 n~46,032  val~4,600  [0.093, 0.118, '
                 '0.153]\n'
                 '  mean / high invalid data   n~1,369   val~137    [0.150, 0.250, '
                 '0.393]\n'
                 '  max  / long gap            n~251     val~25     [0.243, 0.398, '
                 '0.557]\n'
                 '  max  / long missing seg    n~367     val~37     [0.007, 0.116, '
                 '0.303]\n'
                 'A 43x range within a single arm.'),
    fix=('Derive the requirement from the slice, not the fold: compute '
           '`n_validation = ceil(len(training_positions) * INNER_VALIDATION_SHARE)` '
           'and require the stratified slice to contain at least some minimum count '
           'per class (e.g. 10), falling back to the whole training fold — or, '
           'better, to a repeated/CV threshold selection over the training fold — '
           'when it cannot. Equivalently, set `test_size` to a count rather than a '
           'fraction so the slice size has a floor, and have `pick_threshold` refuse '
           '(return 0.5, or a prevalence-matched quantile) below that count.'),
    verification=('Add a self_check case with a synthetic arm of ~360 records at '
                    '9% prevalence and assert the returned validation slice holds at '
                    'least the minimum positives per class, or that the fallback '
                    'fired; then re-run stage F for `maximum deviation/mortality` '
                    'and assert the `long missing segment` threshold range collapses '
                    'from 0.007–0.303 to something narrow, and that `accuracy_std` '
                    'for that arm drops well below 0.09.'),
    found='2026-08-11 statistical audit; verified from the sidecars',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C6',
        note=('Guard passes at 8 positives in the fold -> slice guaranteed only 1; '
             'thresholds span 43x on small arms; docstring contradicts code '
             '(guardrail 10).'),
    ),
),
dict(
    id='N-05', stage=EVAL, severity=HIGH, status=INTRODUCED, verified=True,
    name='macro F1 returns 1.0 for a single-class arm',
    overview=("None of the five `f1_score(..., average='macro')` calls in "
                'evaluation_manager.py pass `labels=[0, 1]`, so sklearn averages '
                'only over the classes present in `y_true ∪ y_pred`; a slice '
                'containing one class and predicted entirely as that class averages '
                'a single perfect per-class F1 and returns 1.0. At the cited line '
                '463 this cannot happen — line 438 skips any fold whose fit split is '
                'not two-class before the model is even built — so the exposed calls '
                'are the out-of-fold reducer at 478, the legacy pair at 297-298, and '
                'the legacy validation diagnostic at 193. In the current data every '
                'non-empty arm fits all 20 folds and covers a two-class record set, '
                'so the failure is latent, not realised.'),
    affects=('Nothing in the current artifacts. I scanned all twenty '
               '`*_filter_impact*.pkl` for F1 values at 1.0: the exact 1.0s are '
               'training F1s (position [2]) for `long missing segment` and `long '
               'gap`, which are legitimate random-forest memorisation — the same '
               'aggregation/label cells show ~0.9996 for the full-cohort arms too, '
               'and `mean/mortality` has none at all. Zero-record arms return NaN in '
               'the CV path and 0.0 in the legacy path, never 1.0. The exposure is '
               'to future runs: a filter or dataset that leaves an arm with a '
               'one-class evaluation slice would publish a perfect F1 and, via the '
               'delta plot, a large spurious positive bar.'),
    recompute='Nothing.',
    technical=('In the CV path, `evaluate_dataset_label_cv` guards the training F1 '
                 'at 438-442 (`len(np.unique(y_fit)) < 2` → `continue`), so `y_fit` '
                 'at 463 always holds both classes and macro averaging spans ≥2 '
                 'labels — the cited defect is not reachable at the cited line. The '
                 'unguarded call is line 478, where `y_true = labels[covered]` '
                 '(473); `covered` non-empty implies at least one fold was fitted on '
                 'a two-class split, which makes a single-class `covered` set '
                 'improbable but not impossible for an arm where only some folds '
                 'fit. In the ten sidecars every non-degenerate arm reports '
                 '`n_folds_fitted = 20` and `coverage = 1.0`, so `covered` is the '
                 'whole arm and is two-class everywhere — hence no realised 1.0. The '
                 'legacy path is weaker: lines 297-298 guard only on non-empty '
                 'vectors, and `evaluate_dataset_label_impact` will happily train on '
                 'a single-class split (`_positive_scores` explicitly handles `1 not '
                 'in classes` by returning zeros, 116-118), so a single-class arm '
                 'there yields all-zero predictions against all-zero labels and '
                 'macro F1 = 1.0 with accuracy 1.0. That path is not reached today '
                 'only because the one zero-retention arm (`high invalid data` under '
                 'the three deviation aggregations) short-circuits at 167-171 with '
                 'empty vectors, which the `len(...) > 0` filters then drop to 0.0.\n'
                 '\n'
                 'First-pass measurements retained: Verified: f1_score(zeros(100), '
                 "zeros(100), average='macro') == 1.0, because unique_labels infers "
                 'a single-label set. Not currently triggered — the smallest live '
                 'arm is 251 records at prevalence 0.32 — but the guard rail is '
                 "absent by design decision (see BUG N-10's sibling, the removal of "
                 'the early return).'),
    fix=('Pass `labels=[0, 1]` (and `zero_division=0`) to all five `f1_score` '
           'calls — evaluation_manager.py:193, 297, 298, 463, 478 — so macro '
           'averaging always spans both classes. Additionally raise or emit NaN '
           'rather than a metric when `len(np.unique(y_true)) < 2` at 478 and '
           '297-298, and drop the 0.0 fallbacks at 299-300 in favour of NaN so a '
           'degenerate arm cannot be plotted as a large negative delta.'),
    verification=('Unit-check `f1_score(np.zeros(10, int), np.zeros(10, int), '
                    "average='macro', labels=[0, 1])` returns 0.5, not 1.0; then "
                    'feed `evaluate_dataset_label_cv` a synthetic single-class arm '
                    'and assert every reported F1 is NaN and `degenerate` is True '
                    '(verify_cv.py section 4b already builds a zero-record arm — '
                    'extend it to a one-class arm, which it currently does not '
                    'cover).'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C6',
        note=('Correction: cited line 463 is guarded (line 438 skips single-class '
             'fits); reachable calls are 478 and legacy 297-298/193. Latent — no '
             'current artifact shows an inflated F1. Severity suggestion: Low.'),
    ),
),
dict(
    id='N-06', stage=EVAL, severity=HIGH, status=OPEN, verified=True,
    name=('Arms are compared at arm-specific operating points, and AUC is never '
            'reported'),
    overview=('Every arm re-selects its decision threshold on its own '
                'inner-validation split (evaluation_manager.py:451, legacy '
                'equivalent at :179), so the accuracy and macro-F1 that the tables '
                'and bar charts compare are sampled at different points on different '
                'ROC curves. A filter-vs-raw delta therefore mixes "the filter '
                'changed the ranking of patients" with "the filter moved the '
                'operating point"; the threshold-free quantity that would separate '
                'these (ROC-AUC / average precision) is fully computable from the '
                'stored per-repeat scores and is never computed for any reported '
                'number.'),
    affects=('Positions [1] and [3] of every `*_filter_impact_cv.pkl` and '
               '`*_filter_impact.pkl`, `accuracy_mean` / `f1_macro_mean` / '
               '`accuracy_std` / `f1_macro_std` in every '
               '`*_filter_impact_cv_diagnostics.json`, and the four figures '
               '`paper_figures/filter_impact_{icu,mortality}_testing_{accuracy,f1}_mea'
               'n.pdf` plus the delta tables built by `filter_impact_table` / '
               '`filter_impact_plot` in Experiments/notebook.py:638-686. The '
               'confound is quantitatively real in the shipped artifacts: for '
               '`mortality`/`maximum deviation`, mean thresholds are raw 0.1226, '
               'systolic 0.1262, respiration 0.1150, long missing segment 0.1013, '
               'long gap 0.3858 — the long-gap arm is compared to raw across a 3x '
               'threshold gap.'),
    recompute=('Nothing needs re-running to *add* the metric: AUC/AP can be '
                 'derived offline from the existing '
                 '`Data/mimic-iii/*/[label]_oof_scores_cv.npz` (per-repeat scores) '
                 'joined to `raw_labels` on `raw_admission_ids`. Adding AUC to the '
                 'pickles/diagnostics/figures requires re-running '
                 'rerun/regen_filter_impact_cv.py per aggregation and label and '
                 'regenerating the four filter_impact figures. The legacy path '
                 'stores no scores, so adding AUC there requires refitting.'),
    technical=('`evaluate_dataset_label_cv` fits one forest per (repeat, fold), '
                 'picks the threshold on the inner-validation slice '
                 '(evaluation_manager.py:435-451) and thresholds the held-out fold '
                 'at that arm-and-fold-specific value (:457). Per-repeat accuracy/F1 '
                 '(:474-480) and the reported means (:504-507) are all functions of '
                 'those thresholded labels; nothing threshold-free is ever produced, '
                 'and `consensus_scores` (:487-491) is written to the npz (:716) but '
                 "never scored. `pick_threshold` (:63-96) maximises Youden's J on "
                 "validation, so the operating point tracks each arm's own "
                 'validation prevalence and score distribution — which is legitimate '
                 'per arm and illegitimate as a basis for cross-arm subtraction. The '
                 'legacy path has the same structure (:178-184). The artifact spread '
                 'of `mean_threshold` above proves the arms are not co-located. A '
                 'second, verified symptom of the same operating-point looseness: '
                 'within one arm the reported table accuracy and the McNemar '
                 'accuracy come from different operating points — e.g. `long missing '
                 'segment` has `accuracy_mean=0.6342` (per-fold thresholds) versus '
                 '`arm_accuracy_on_paired=0.7248` (consensus at `mean_threshold`) in '
                 'the same JSON block.\n'
                 '\n'
                 'First-pass measurements retained: mean_threshold differs per arm: '
                 'raw 0.118, high invalid data 0.250, long gap under maximum '
                 'deviation 0.398. Accuracy at a Youden point is also '
                 "anti-informative here — prevalence is 0.0966 and every arm's "
                 'predicted-positive rate is 0.29-0.40, so every reported accuracy '
                 '(0.59-0.74) is worse than the trivial all-negative classifier '
                 '(0.9034). AUC for raw/mean mortality should land near 0.75-0.80 '
                 'given the observed sensitivity/specificity trade.'),
    fix=('In `evaluate_dataset_label_cv`, add per-repeat '
           '`roc_auc_score(labels[covered], oof_scores[repeat][covered])` and '
           '`average_precision_score` alongside accuracy/F1, reduce them with '
           '`_mean_of_finite`/`_std_of_finite` into `diagnostics` as '
           '`auc_mean`/`auc_std`/`ap_mean`/`ap_std` (guardrail 4 keeps them out of '
           'the 5-tuple; the JSON sidecar is the right home), and add an AUC panel '
           'to the filter-impact figures. Where accuracy must be compared across '
           "arms, either fix one shared threshold (e.g. the raw arm's) for all arms "
           'or report accuracy at matched predicted-positive rate.'),
    verification=('Recompute AUC per arm directly from the existing npz + '
                    '`raw_labels` join and confirm it reproduces the new `auc_mean` '
                    'to ~1e-6; then check that arms whose accuracy delta vs raw is '
                    'significant but whose AUC delta is ~0 are flagged, and that '
                    '`high invalid data` (zero records under three aggregations) '
                    'yields NaN rather than 0.5.'),
    found='2026-08-11 statistical audit; thresholds verified from the sidecars',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C9',
        note=('Independently re-derived from code by a blind verification agent; '
             'description updated where the re-derivation was more precise.'),
    ),
),
dict(
    id='N-07', stage=EVAL, severity=MEDIUM, status=INTRODUCED, verified=True,
    name='The admission-id validation is a multiset check, not an identity check',
    overview=('`validate()` proves the replayed id vector has the same length as '
                'the cached pickle and that the two `[icu, mortality]` label '
                'matrices are element-wise equal, but with two binary labels there '
                'are only four distinct rows, so any reordering that happens to be '
                'label-correlated (positives grouped, sort by class, '
                'class-stratified caching) leaves both checks green while the ids '
                'are attached to the wrong tensors. The consequence is that the id '
                'sidecars — the sole basis for pairing arms and inheriting folds — '
                'are certified by a check whose equivalence class is "permutations '
                'within a label group", not "the same records in the same order".'),
    affects=('`Data/mimic-iii/<agg>/*_admission_ids.npy` for all 5 aggregations × '
               '13 arms; downstream, every '
               '`<label>_filter_impact_cv_diagnostics.json` `mcnemar` block and '
               '`<label>_oof_scores_cv.npz` id column, because '
               '`calculate_mcnemar_paired` (evaluation_manager.py:570-582) and '
               '`project_to_arm` (partition_manager.py:124-138) both key on those '
               'ids. Nothing is currently known to be wrong — the check is weaker '
               'than advertised, not demonstrably violated.'),
    recompute=('Nothing, if a strengthened check passes. If a strengthened check '
                 'fails, stage E, then stage F (`regen_filter_impact_cv.py`, 10 '
                 'tasks) for the affected aggregation.'),
    technical=('`cached_labels` (regen_admission_ids.py:63-72) loads `entry[1]` '
                 'from each cached record, giving an (n,2) int matrix whose only '
                 'possible rows are (0,0),(0,1),(1,0),(1,1) per `label_index_map` '
                 '(ehr_dataset.py:26). `validate` (regen_admission_ids.py:75-91) '
                 'then applies exactly three tests: length equality (79), '
                 '`np.array_equal(labels, cached)` (84) — positional, but over that '
                 '4-symbol alphabet — and id uniqueness (90). For the ten arms not '
                 'in `RECORD_DROPPING` the script does not replay the filter at all; '
                 'it asserts `ids, labels = raw_ids, raw_labels` (148) on the '
                 'documented assumption of "one output per input, in input order", '
                 'and the comment at 147 says "validate() is what actually holds '
                 'this claim up". It cannot: for the raw/pass-through arms the check '
                 'reduces to "the cached pickle\'s label column agrees with '
                 '`processed_record_ehr.pkl`\'s label column position by position", '
                 'which any label-preserving permutation satisfies. Correction to '
                 'the claim: `np.array_equal` is a positional comparison, not a '
                 'multiset comparison; the vacuity comes from label cardinality, not '
                 'from an unordered comparison. Partial mitigation I verified: '
                 "verify_cv.py:104-110 additionally requires each arm's ids to be an "
                 "*ordered subsequence* of raw's, which would catch a non-monotone "
                 "permutation of an arm's own vector — but it derives `raw_position` "
                 'from `raw_ids` itself (verify_cv.py:103), so it cannot detect a '
                 'mis-association of the raw vector against the raw pickle, and it '
                 'is satisfied by any order-preserving mis-association.\n'
                 '\n'
                 'First-pass measurements retained: With 46,032 records and four '
                 'possible label pairs, a permutation within a group is undetectable.'),
    fix=('Add a content-based check to `validate`: hash a fixed sample of the '
           'feature tensor rather than the label vector. For the three '
           '`RECORD_DROPPING` arms the `kept` record objects are already in hand at '
           'regen_admission_ids.py:140, so `record.to_tensor()`/the aggregated '
           'tensor can be compared against `torch.load(path)[i][0]` for, say, 500 '
           'random positions plus the first and last. For the pass-through arms, do '
           'the same against `aggregated` for the subset of arms whose filter is '
           'post-aggregate, and for the pre-aggregate arms replay the filter on a '
           'sampled subset of records only. Fail loudly on any tensor mismatch.'),
    verification=('Re-run stage E per aggregation and confirm the new '
                    'tensor-sample check passes on all 13 arms; then '
                    'negative-control it by monkeypatching a label-preserving '
                    'permutation of `records` (e.g. stable sort by '
                    '`record.mortality`) and confirming `validate` now raises where '
                    'today it exits 0.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C8',
        note=('Correction: np.array_equal is positional, not multiset — the vacuity '
             "comes from the 4-symbol label alphabet. verify_cv's "
             'ordered-subsequence check partially mitigates. Severity suggestion: '
             'Low-Medium.'),
    ),
),
dict(
    id='N-08', stage=EVAL, severity=MEDIUM, status=INTRODUCED, verified=True,
    name='Stratification is exact on raw but only inherited by arms',
    overview=('`build_fold_assignment` stratifies exactly on the 46,032-record raw '
                'cohort, and every arm inherits those fold labels through '
                '`project_to_arm`, so an arm that drops records keeps whatever '
                'balance survives. The drift is computed and written per arm, but '
                'the only threshold assertion in the tree (`drift < 0.005`) runs '
                'inside `partition_manager.self_check` against a synthetic '
                "uniformly-sampled cohort, and `verify_cv.py`'s stage-F section "
                'checks only arm presence, fingerprint equality and `n_paired <= '
                'n_records` — so real drifts of 0.05-0.165 pass with no warning in '
                'any log.'),
    affects=('`Data/mimic-iii/{standard deviation,mean deviation,maximum '
               'deviation}/{icu,mortality}_filter_impact_cv_diagnostics.json` for '
               '`long gap` (n=251, drift 0.160 icu / 0.165 mortality) and `long '
               'missing segment` (n=367, drift 0.096 icu / 0.053 mortality); '
               '`Data/mimic-iii/mean/icu_...json` `high invalid data` (n=1,369, '
               'drift 0.055). For those arms, positions [1] and [3] of '
               '`<label>_filter_impact_cv.pkl` (`accuracy_mean`, `f1_macro_mean`) '
               'and their `accuracy_std`/`f1_macro_std` error bars are averages over '
               "folds whose prevalence differs from the arm's own by up to half its "
               'base rate, so the cross-repeat spread understates the real '
               'uncertainty and the arm-vs-raw delta is partly fold-composition, not '
               'filter effect. The `mean`/`median` aggregations are unaffected in '
               'practice (max arm drift 0.013).'),
    recompute=('Nothing, if the response is to add a check/warning. If the '
                 'response is to re-stratify the small arms (i.e. break '
                 'inheritance), that would forfeit pairing and require rerunning '
                 'stage F for all 10 (aggregation, label) tasks and regenerating '
                 'anything derived from the CV pickles — I would not do that.'),
    technical=('`build_fold_assignment` (partition_manager.py:95-100) runs '
                 '`StratifiedKFold(..., random_state=PARTITION_SEED + repeat)` over '
                 'the raw ids and raw labels only. `project_to_arm` '
                 '(partition_manager.py:138) returns `raw_assignment[:, '
                 'order[position]]` — a pure gather, with no rebalancing, which is '
                 'the intended design (partition_manager.py:11-18). '
                 "`evaluate_dataset_label_cv` then folds the arm's own drift into "
                 'diagnostics at evaluation_manager.py:514 '
                 '(`diagnostics.update(fold_prevalences(fold_assignment, labels))`), '
                 'and `evaluate_filter_impact_cv` copies it into the sidecar at '
                 'evaluation_manager.py:700-706. A recursive grep for '
                 '`max_fold_drift` over the working tree returns only its two '
                 'definitions in partition_manager.py:183/193 and the synthetic '
                 'assertion at 224 — no consumer, no threshold, no print in '
                 '`regen_filter_impact_cv.py` (whose per-arm log lines at '
                 'regen_filter_impact_cv.py:118-123 report only McNemar counts). '
                 '`verify_cv.py:234-251` never reads the key. Correction to the '
                 'claim: it is not true that the degradation is unrecorded — it is '
                 'recorded per arm; what is missing is any assertion, warning or log '
                 'surface, so the value is dark data. Reading the artifacts confirms '
                 'the degradation is real and material, not hypothetical.\n'
                 '\n'
                 'First-pass measurements retained: Measured max_fold_drift '
                 '(mortality):\n'
                 '  46,032-record arms          6.3e-06  (exact)\n'
                 '  long missing segment / mean   0.0048\n'
                 '  high invalid data / mean      0.038\n'
                 '  long missing segment / maxdev 0.053\n'
                 '  long gap / maxdev             0.165   (folds range ~0.16-0.49)'),
    fix=('In `verify_cv.py` section 6, after loading the sidecar, add '
           '`check(f"{arm}: fold drift within tolerance", '
           "diagnostics[arm]['max_fold_drift'] <= max(0.01, 3 * "
           "diagnostics['raw']['max_fold_drift']) or np.isnan(...), ...)` — or more "
           'usefully a relative tolerance against `population_prevalence` — and in '
           "`regen_filter_impact_cv.py`'s per-arm log line print `max_fold_drift` "
           'with a `<-- DRIFT` marker in the same style as the existing `<-- '
           'DEGENERATE` flag (regen_filter_impact_cv.py:120).'),
    verification=('Re-run `rerun/verify_cv.py --aggregation "maximum deviation"` '
                    'and confirm the new check FAILS on `long gap`/`long missing '
                    'segment` (drift 0.16/0.05) while passing for `mean`; that '
                    'failure is the proof the check has teeth. Then confirm the '
                    'stage-F log for a deviation aggregation shows the drift marker.'),
    found='2026-08-11 statistical audit; verified from the sidecars',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C8',
        note=('Correction: drift IS recorded per arm (max_fold_drift) — defect is '
             'that nothing asserts/warns on it; drifts up to 0.165 pass silently; '
             'the green self-check line is synthetic-cohort only.'),
    ),
),
dict(
    id='N-09', stage=EVAL, severity=MEDIUM, status=INTRODUCED, verified=True,
    name=('The inner-split fallback changes training size and operating point '
            'together'),
    overview=('When the guard fires, that fold trains on 80% at threshold 0.5 '
                'while its siblings train on 70% at a Youden threshold — and they '
                'are then averaged as if identical.'),
    affects=('`accuracy_mean`/`f1_macro_mean` and hence positions [1] and [3] of '
               '`<label>_filter_impact_cv.pkl`, plus `mean_threshold`, '
               '`train_accuracy`, `train_f1_macro` and `consensus_predictions` in '
               '`<label>_filter_impact_cv_diagnostics.json` / '
               '`<label>_oof_scores_cv.npz`, for any arm small or imbalanced enough '
               'to trip the guard. In the currently shipped artifacts under '
               'Data/mimic-iii/*/ the guard did not fire (see NOTES), so no '
               'published number is presently wrong — the exposure is to the next '
               'arm/label that is smaller or rarer.'),
    recompute=('Nothing for the current artifacts. If a future arm trips the '
                 'guard, stage F (rerun/regen_filter_impact_cv.py) must be re-run '
                 'for that (aggregation, label).'),
    technical=('The threshold is chosen on `validation_positions` only when '
                 '`validation_positions.size` is truthy '
                 '(evaluation_manager.py:447-451); the fallback branch at 452-453 '
                 'hardcodes 0.5. The same `fit_positions` that the fallback widened '
                 'to the full training set is what the forest is fitted on (line '
                 '445) and what `train_accuracies`/`train_f1s` are measured on '
                 '(lines 460-463), so a fallback fold contributes both a '
                 'differently-sized training estimate and a different operating '
                 'point to the same means. Downstream there is no per-fold record of '
                 'which regime produced which number: '
                 '`thresholds[f"r{repeat}f{fold}"]` (line 458) stores 0.5 '
                 'indistinguishably from a genuine Youden 0.5, and `n_folds_fitted` '
                 "(line 502) counts both alike. `inner_split`'s own docstring "
                 '(partition_manager.py:151-153) documents the degradation to 0.5 '
                 'but not the fit-size change that accompanies it; the minimum is '
                 '`max(2, ceil(1/INNER_VALIDATION_SHARE))` = 8 '
                 '(partition_manager.py:160, 42).\n'
                 '\n'
                 'First-pass measurements retained: So two things move at once, '
                 'train_accuracies and per_repeat average across them homogeneously, '
                 'and the only trace is a 0.500 entry in the thresholds dict. '
                 'n_folds_fitted still counts the fold.'),
    fix=('Record the regime and stop mixing it into pooled statistics. Concretely: '
           'have `inner_split` return a third value (or have the caller detect '
           "`validation_positions.size == 0`), store `{'threshold': t, 'fallback': "
           "True, 'n_fit': fit_positions.size}` per fold, exclude fallback folds "
           'from `mean_threshold`, and either (a) skip such folds entirely, leaving '
           'those records uncovered exactly as the single-class guard at lines '
           '438-442 already does, or (b) keep them but hold the fit size constant by '
           'still carving off a 1/8 unstratified slice, and surface a '
           '`n_folds_fallback` counter in diagnostics so a reader can see it.'),
    verification=('Construct a synthetic arm with 7 positives so the guard fires, '
                    'call `evaluate_dataset_label_cv`, and assert that `diagnostics` '
                    'reports the fallback count non-zero and that `mean_threshold` '
                    'no longer contains a 0.5 contributed by an unvalidated fold; on '
                    'the real cohort assert `n_folds_fallback == 0` for all 13 arms '
                    "× 5 aggregations × 2 labels, which reproduces today's artifacts "
                    'unchanged.'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C7',
        note=('Latent: guard never fired in shipped artifacts (smallest arm has ~26 '
             'minority per fold vs threshold 8); fallback 0.5 indistinguishable from '
             'genuine Youden 0.5 in artifacts.'),
    ),
),
dict(
    id='N-10', stage=EVAL, severity=MEDIUM, status=INTRODUCED, verified=True,
    name='mean_threshold 0.5 is emitted for an arm that fitted zero folds',
    overview=('`mean_threshold` falls back to the literal 0.5 when `thresholds` is '
                'empty (evaluation_manager.py:492), i.e. when not one fold was ever '
                'fitted, and that value is then written straight into the '
                'diagnostics sidecar (line 503). Six of the ten shipped '
                '`*_filter_impact_cv_diagnostics.json` files consequently carry '
                '`"mean_threshold": 0.5` for the `high invalid data` arm alongside '
                '`n_records: 0`, `n_folds_fitted: 0` and `accuracy_mean: NaN`, so a '
                'reader or a downstream script that keys on the threshold sees a '
                'plausible operating point for a model that was never trained.'),
    affects=('`Data/mimic-iii/{maximum deviation,mean deviation,standard '
               'deviation}/{icu,mortality}_filter_impact_cv_diagnostics.json`, the '
               '`high invalid data` entry only. No pickle position, figure, or '
               'notebook number is affected — `mean_threshold` is consumed only at '
               'evaluation_manager.py:496, where `consensus_covered` is all-False '
               'for that arm, so it changes no prediction. It is a reporting defect, '
               'not a numeric one.'),
    recompute=('Nothing. The value can be corrected in place by re-emitting the '
                 'sidecar, and no scored quantity changes.'),
    technical=('For the deviation aggregations `high invalid data` retains zero '
                 'records, so `n_records == 0`, `fold_assignment` has width 0, every '
                 '`test_positions` is empty and the loop `continue`s at line 431, '
                 "leaving `thresholds` empty. Line 492's `if thresholds else 0.5` "
                 "then substitutes the pipeline's generic no-information default. "
                 'Every genuinely metric-shaped reducer in the same dict does '
                 'degrade to NaN for this arm — `accuracy_mean`/`f1_macro_mean` via '
                 '`_mean_of_finite` (lines 345-352, 504-507) and '
                 '`predicted_positive_rate` via its own guard (508-511) — and the '
                 'dict does carry two correct signals, `n_folds_fitted: 0` (502) and '
                 '`degenerate: not bool(thresholds)` (512). Correction to the claim: '
                 'not *every* other field is NaN — `coverage` is 0.0 (line 501) and '
                 '`n_records` is 0, both of which are the right answers, so '
                 '`mean_threshold` is the single field that reports a fabricated '
                 'value rather than an absent one.'),
    fix=('`mean_threshold = float(np.mean(list(thresholds.values()))) if '
           "thresholds else float('nan')`, and at line 495-497 gate the consensus "
           'thresholding on `thresholds` being non-empty (already implied by '
           '`consensus_covered.any()` being False, so no behaviour change) so the '
           'NaN cannot propagate into a comparison.'),
    verification=('Re-run `python rerun/verify_cv.py` for one deviation '
                    'aggregation and add an assertion in the 4b degenerate-arm '
                    'section that '
                    "`np.isnan(degenerate['diagnostics']['mean_threshold'])`; then "
                    'confirm the six sidecars show `"mean_threshold": NaN` for `high '
                    "invalid data` while every non-degenerate arm's value is "
                    "byte-identical to today's."),
    found='2026-08-11 statistical audit; verified from the sidecars',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C7',
        note=('Correction: coverage=0.0 and n_records=0 are correct answers in the '
             'same dict; mean_threshold is the single fabricated value. Severity '
             'suggestion: Low.'),
    ),
),
dict(
    id='N-11', stage=EVAL, severity=MEDIUM, status=INTRODUCED, verified=True,
    name=('Fold count is hardcoded while repeat count is inferred, and width is '
            'unchecked'),
    overview=('Line 410 reads `n_repeats` off `fold_assignment.shape[0]` while '
                'line 427 iterates `range(N_SPLITS)` from the module constant, so an '
                'assignment built with `build_fold_assignment(..., n_splits=k)` for '
                'k > 5 has folds 5..k-1 skipped entirely — those records are never '
                'held out, the folds that do run train on more than 80%, and nothing '
                'raises. Separately, the only shape check in the function (lines '
                '405-408) compares `n_records` against `len(admission_ids)` and '
                'never against `fold_assignment.shape[1]`, so an assignment narrower '
                'than the record list silently scores only its first `shape[1]` '
                'records.'),
    affects=('Nothing in the shipped artifacts — the only production caller, '
               '`evaluate_filter_impact_cv` at evaluation_manager.py:667, uses '
               '`build_fold_assignment(raw_ids, raw_labels)` with both defaults, and '
               'all ten sidecars report `n_folds_fitted: 20` and `coverage: 1.000` '
               'for every non-degenerate arm, i.e. 4 repeats × 5 folds with full '
               'out-of-fold coverage. The defect is a latent trap for the next '
               'caller that varies the partition shape, which the codebase already '
               'does for repeats (rerun/verify_cv.py:213 passes `n_repeats=2`).'),
    recompute='Nothing.',
    technical=('`N_SPLITS` is imported at evaluation_manager.py:26-29 and used '
                 'only at line 427; `n_splits` is a real parameter of '
                 '`build_fold_assignment` (partition_manager.py:71), so the two can '
                 'legitimately disagree and there is no assertion that '
                 '`fold_assignment.max() + 1 == N_SPLITS`. The asymmetry is not '
                 'hypothetical in spirit: `rerun/verify_cv.py:213` builds '
                 '`build_fold_assignment(probe_ids, shuffled, n_repeats=2)` and the '
                 'function adapts correctly, which is exactly the parameterisation '
                 'the fold axis lacks. Two corrections to the claim. First, I could '
                 'not locate `fold_assignment.sh` anywhere under /home/ccampb47/work '
                 "(`find -name 'fold_assignment*'` returns nothing); the fold-count "
                 'constant lives in partition_manager.py, and the stage-F driver is '
                 'rerun/job_f_filter_impact_cv.sh, so that citation is wrong. '
                 'Second, a too-short assignment does not produce a *misaligned* '
                 'scoring — positions from `np.where` are all < `shape[1]` and index '
                 'correctly into `features`/`labels` — it produces a *truncated* '
                 'one: records past `shape[1]` stay at `oof_predictions == -1` and '
                 'are dropped from every metric, which does show up as `coverage < '
                 '1.0` in the diagnostics (line 501) even though nothing raises. The '
                 'reverse case, an assignment wider than the record list, does '
                 'raise, but only incidentally and late, through numpy '
                 'bounds-checking at `labels[training_positions]` '
                 '(partition_manager.py:156). A third internal inconsistency '
                 'corroborates the hardcode: `fold_prevalences` '
                 '(partition_manager.py:187-192) iterates '
                 '`np.unique(assignment[repeat])`, so the diagnostics would report '
                 'drift over folds the training loop never visited.'),
    fix=('Replace line 427 with a fold list derived from the data — `for fold in '
           'range(int(fold_assignment.max()) + 1):` — and extend the guard at '
           '405-408 to `if fold_assignment.shape[1] != n_records: raise '
           'ValueError(...)`, so a shape disagreement fails loudly at entry rather '
           'than as reduced coverage.'),
    verification=('Call `evaluate_dataset_label_cv` with '
                    '`build_fold_assignment(ids, labels, n_splits=10)` and assert '
                    '`n_folds_fitted == 2 * 10` and `coverage == 1.0`; call it with '
                    'an assignment sliced to `[:, :n-1]` and assert it raises; then '
                    're-run stage F for one (aggregation, label) and confirm '
                    '`n_folds_fitted: 20`, `coverage: 1.000` and the pickle values '
                    'are unchanged.'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C7',
        note=('Corrections: fold_assignment.sh does not exist (citation wrong); '
             'too-short assignment truncates (visible as coverage<1) rather than '
             "misaligns; verify_cv's n_folds_fitted check is tautological w.r.t. "
             'this.'),
    ),
),
dict(
    id='N-12', stage=EVAL, severity=MEDIUM, status=INTRODUCED, verified=True,
    name='The verifier fails spuriously on four of five aggregations',
    overview=('`EXPECTED_COUNTS` (verify_cv.py:32-37) is a single flat dict of '
                "arm→count copied from the mean family's diagnostics, but the script "
                'takes `--aggregation` as a free-form argument (line 70) and its own '
                'docstring advertises `--aggregation median` (line 9). The three '
                'post-aggregation arms legitimately keep different numbers of '
                'records under each aggregation, so the count check at lines 98-101 '
                'fails on those arms for four of the five families, `FAILURES` is '
                'populated, and `main()` returns 1 (lines 254-256), turning a '
                'healthy run into a red verification.'),
    affects=('No scientific numbers, figures, or pickles are wrong — this is a '
               "self-check tool only. What is wrong is the verifier's own verdict "
               'for the median, standard deviation, mean deviation and maximum '
               'deviation families under '
               '/home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Datas'
               'et-Processing/Data/mimic-iii/, and the exit status of '
               '/home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Datas'
               'et-Processing/rerun/job_g_verify.sh when invoked with a non-mean '
               '`--aggregation`. Because only the mean family can currently pass, '
               'the CV path for the other four families is effectively unverified: '
               'the only two green logs on disk '
               '(rerun/logs/g_verify_cv_19576026.log, g_verify_cv_19580847.log) both '
               "begin `verify_cv — aggregation='mean' label='mortality'`."),
    recompute=('Nothing. No artifact is derived from the verifier; only re-running '
                 'rerun/verify_cv.py for each of the five aggregations is needed '
                 'once the guard is keyed correctly.'),
    technical=('verify_cv.py:70 declares `parser.add_argument("--aggregation", '
                 'default="mean")` with no `choices=`, and `load_arm` (lines 54-61) '
                 'resolves pickles and id sidecars under `DATA_ROOT / aggregation`, '
                 'so every aggregation is a supported input path. The count guard, '
                 'however, is aggregation-blind: lines 98-101 iterate the '
                 'module-level `EXPECTED_COUNTS` and compare `len(ids[arm])` against '
                 'constants whose provenance is documented at lines 30-31 as "From '
                 'the cached diagnostics sidecars". Those constants match only the '
                 'mean family. Reading `n_records` out of the on-disk CV diagnostics '
                 'sidecars shows the true counts: median drops `long missing '
                 'segment` to 31028 and `high invalid data` to 1365 (2 false '
                 'failures); standard deviation, mean deviation and maximum '
                 'deviation drop `long missing segment` to 367, `long gap` to 251 '
                 'and `high invalid data` to 0 (3 false failures each). `raw` is '
                 '46032 in all five families, so that entry never misfires. This is '
                 'expected behaviour of the data, not drift: these three filters '
                 'carry `pre_aggregate=False` in rerun/_common.py:63-66, i.e. they '
                 'are applied to the aggregated matrix and so their yield is a '
                 'function of the aggregation. Each mismatch calls `check(..., '
                 'False, ...)` (lines 42-47), which appends to `FAILURES`, and lines '
                 '254-256 then print `FAILED (...)` and `return 1`. '
                 'job_g_verify.sh:11 sets `set -euo pipefail` and line 17 forwards '
                 '`"$@"` to the script, so the nonzero exit marks the SLURM task '
                 'failed. Two corrections to the claim as stated: (a) the count is '
                 'three false failures only for the three deviation aggregations — '
                 'median produces two; (b) job_g_verify.sh does not itself sweep '
                 'aggregations, so the failure is triggered by an operator passing '
                 "`--aggregation`, not by the job script's default invocation; the "
                 "script's contribution is only that it propagates the exit status. "
                 'Guardrail 10 applies: the docstring at line 9 documents non-mean '
                 'use, and the code contradicts it, which confirms rather than '
                 'excuses the defect. Guardrail 7 also applies — the two green logs '
                 'prove nothing about the other four families, since both ran the '
                 'mean default.\n'
                 '\n'
                 'First-pass measurements retained: rerun/verify_cv.py:32-37 '
                 'hardcodes long missing segment 31,029, long gap 20,323, high '
                 'invalid data 1,369.'),
    fix=("Key the expectations by aggregation, e.g. `EXPECTED_COUNTS = {'mean': "
           "{...}, 'median': {...}, 'standard deviation': {...}, ...}` and select "
           '`EXPECTED_COUNTS[aggregation]` inside `main()` after parsing, erroring '
           'out if the aggregation is unknown. Cheaper and self-maintaining '
           'alternative: drop the literals and assert `len(ids[arm])` against the '
           "`n_records` field already present in that aggregation's "
           '`{label}_filter_impact_cv_diagnostics.json` (already loaded in section '
           '6, lines 235-251), falling back to SKIP when the sidecar is absent. '
           'Either way add `choices=AGGREGATIONS` to the `--aggregation` argument so '
           'a typo cannot silently be read as a missing directory.'),
    verification=('Run `python rerun/verify_cv.py --aggregation X` for all five '
                    'values of X (structural checks only, no `--with-model`) and '
                    'confirm every run ends `OK — all checks passed` with the '
                    '`record count` lines echoing the per-family numbers above (e.g. '
                    '`high invalid data: record count — 0 vs expected 0` under '
                    'standard deviation). Then confirm the guard has not been '
                    'neutered by temporarily perturbing one expected value and '
                    'checking that exactly that arm reports FAIL and the process '
                    'exits 1.'),
    found='2026-08-11 statistical audit; counts verified',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='solo pilot',
        note=('Correction: median = 2 false failures, not 3 (deviations = 3 each); '
             'only mean-family green logs exist, so 4 of 5 families are effectively '
             'unverified.'),
    ),
),
dict(
    id='N-13', stage=EVAL, severity=MEDIUM, status=INTRODUCED, verified=True,
    name='The partition fingerprint check cannot fail',
    overview=('One fingerprint string is copied into all thirteen arm records, so '
                'asserting they are all equal is true by construction.'),
    affects=('The credibility of `rerun/logs/g_verify_cv_*.log` line "all arms '
               'share one partition fingerprint". No numeric result is wrong: '
               '`partition_fingerprint` in the twelve '
               '`Data/mimic-iii/*/**_filter_impact_cv_diagnostics.json` files is a '
               'correct digest of the raw cohort, just uninformative per arm. I '
               'verified it is `b1f2ba53d873430e` for every icu sidecar and '
               '`875f52d304c6248e` for every mortality sidecar, across all five '
               'aggregations.'),
    recompute='Nothing. This is a verification defect only.',
    technical=('At evaluation_manager.py:669 the digest is taken from '
                 '`raw_ids`/`raw_labels` before the arm loop at 672-678. Inside the '
                 'reporting loop, evaluation_manager.py:705 writes the identical '
                 'object into `diagnostics[name]`. Nothing per-arm enters it, so '
                 "`{d['partition_fingerprint'] for d in diagnostics.values()}` "
                 '(verify_cv.py:242) is a 1-element set for any sidecar written by a '
                 "single call, regardless of whether any arm's partition is actually "
                 'consistent. The check that would have teeth — comparing the '
                 "sidecar's fingerprint to one recomputed from the ids on disk — is "
                 'never done, even though `verify_cv.py` has already loaded '
                 '`raw_ids` (verify_cv.py:95) and imported nothing else it would '
                 'need; `fingerprint` is not imported there at all '
                 '(verify_cv.py:25-28 imports `calculate_mcnemar_paired, '
                 'evaluate_dataset_label_cv, _flatten_whole_dataset` and '
                 '`build_fold_assignment, project_to_arm`). Corollary I verified '
                 'from the artifacts: because `fingerprint` '
                 '(partition_manager.py:45-55) hashes only ids and labels, and the '
                 "raw cohort's ids/labels are aggregation-independent, the same "
                 'digest appears in all five aggregation directories — so it cannot '
                 'distinguish an `icu` sidecar built on `mean` tensors from one '
                 'built on `maximum deviation` tensors.'),
    fix=('Two changes. (1) In `evaluate_filter_impact_cv`, store a per-arm digest '
           '— `fingerprint(arm_ids, raw_labels[positions])` or `fingerprint(arm_ids, '
           'arm_assignment.tobytes())` — alongside the cohort-level one, so the '
           'sidecar records what each arm was actually scored on. (2) In '
           '`verify_cv.py` section 6, import `fingerprint` and assert '
           "`diagnostics['raw']['partition_fingerprint'] == fingerprint(raw_ids, "
           'raw_labels)` against the ids/labels loaded from disk in section 2, and '
           "assert each arm's per-arm digest matches one recomputed from `ids[arm]`. "
           'Optionally extend the cohort digest to include the aggregation name so '
           'cross-aggregation mixups are detectable.'),
    verification=('Confirm the new check fails when pointed at a sidecar from a '
                    'different label or a hand-edited id sidecar, and passes on the '
                    "current twelve. As a direct tautology test, edit one arm's "
                    '`partition_fingerprint` in a scratch copy of the JSON — the '
                    'current check catches that (set size 2), but the current check '
                    'still cannot catch the case that matters, a sidecar whose whole '
                    'fingerprint is stale; the recompute-based assertion must catch '
                    'that one.'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C8',
        note=('Corroborated: fingerprint also aggregation-independent, so it cannot '
             'catch cross-aggregation mixups. Severity suggestion: Low-Medium.'),
    ),
),
dict(
    id='N-14', stage=EVAL, severity=MEDIUM, status=INTRODUCED, verified=True,
    name='The leakage probe cannot detect the leak it claims to',
    overview=('It measures AUC, which is threshold-invariant, while advertising '
                'itself as the test that would catch a threshold leak.'),
    affects=('The stated coverage of `rerun/verify_cv.py` and the `PASS '
               'shuffled-label AUC collapses to chance` line in both '
               '`rerun/logs/g_verify_cv_19576026.log` and `..._19580847.log`. No '
               'published number is wrong as a result; the gap is in what the suite '
               'proves about `accuracy_mean`, `f1_macro_mean` and the McNemar counts '
               'in the CV artifacts, all of which are threshold-dependent while the '
               'probe is not.'),
    recompute='Nothing.',
    technical=('The probe (verify_cv.py:201-229) shuffles labels, writes them back '
                 'into the tensors (218-223) so the forest trains on noise, runs '
                 '`evaluate_dataset_label_cv`, and then evaluates only '
                 "`roc_auc_score(result['y'][covered], "
                 "result['consensus_scores'][covered])`. `consensus_scores` "
                 '(evaluation_manager.py:487-491) is the mean out-of-fold '
                 'probability, computed before any thresholding; the threshold '
                 'enters only at evaluation_manager.py:494-497. AUC is computed from '
                 'the ranking of those probabilities, so it is numerically unchanged '
                 'by any choice of threshold — which makes the "threshold leak" half '
                 'of the docstring claim unachievable by construction. The probe '
                 'does validly cover fold leakage: with permuted labels, a '
                 'train/test contamination would let the forest memorise and lift '
                 'OOF AUC above 0.5, and the observed 0.5090 is consistent with '
                 'none. There is a concrete threshold-hygiene question this '
                 'blindness leaves untested, which I verified exists in the code: '
                 "per-fold thresholds are chosen on `inner_split`'s validation slice "
                 "drawn from that fold's training positions "
                 '(partition_manager.py:165-170), which is clean for the fold being '
                 'scored, but `mean_threshold` at evaluation_manager.py:492 averages '
                 "all 20 fold thresholds and is then applied to *every* record's "
                 "consensus score — so record i's own label, via its membership in "
                 "some other fold's inner-validation slice, contributes to the "
                 'threshold applied to record i. That contamination shows up in '
                 '`consensus_predictions`, hence in every `mcnemar` block in the '
                 'sidecars, and an AUC-only probe cannot see it.\n'
                 '\n'
                 'First-pass measurements retained: Additionally n_repeats=2 and '
                 'probe_size=8000 give a null AUC SE of ~0.011, so the abs(auc-0.5) '
                 '< 0.05 band is ~4.7 SE and would pass a substantial partial leak.'),
    fix=('Either (a) narrow the docstring at verify_cv.py:12-14 to say the probe '
           'catches fold leakage only, or (b) add a threshold-sensitive assertion to '
           'the probe: on shuffled labels, assert `accuracy` and `f1_macro` from '
           "`result['per_repeat']` sit at the chance values implied by the shuffled "
           'prevalence, and assert '
           "`result['diagnostics']['predicted_positive_rate']` is not systematically "
           'pulled toward the shuffled prevalence. Do (b), plus a direct test that '
           "no record's consensus threshold depends on its own label — e.g. "
           'recompute `consensus_predictions` with a leave-one-out mean threshold '
           'and assert the flip count is zero or negligible.'),
    verification=('Negative control: temporarily change `inner_split` to return '
                    'the outer test fold as the validation slice, re-run '
                    '`rerun/verify_cv.py --with-model`, and confirm the new '
                    'accuracy/F1 assertions fail while the existing AUC assertion '
                    'still passes at ~0.5 — that difference is the proof the old '
                    'check was blind.'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C8',
        note=('Real untested contamination found: mean_threshold averages all 20 fold '
             "thresholds, so record i's label leaks into the threshold applied to "
             'record i (consensus path only). Severity suggestion: Low as assurance '
             'defect.'),
    ),
),
dict(
    id='N-15', stage=EVAL, severity=MEDIUM, status=OPEN, verified=True,
    name=("pick_threshold's non-finite fallback picks the all-negative operating "
            'point'),
    overview=('`np.argmax(youden)` selects index 0 — whose threshold is `+inf` — '
                "whenever no operating point beats chance, because Youden's J is "
                'exactly 0 at that corner and `argmax` returns the first maximum. '
                'The guard at lines 92-94 then replaces `+inf` not with the '
                'documented 0.5 default but with `finite.max()`, the largest finite '
                'threshold, which is the maximum validation score; applying it to '
                'the held-out data predicts positive for essentially nothing, so the '
                'fold reports majority-class accuracy and a collapsed macro F1 '
                'rather than falling back to the neutral 0.5 the docstring describes '
                'for every other degenerate case.'),
    affects=('Potentially positions [1] and [3] of both '
               '`<label>_filter_impact.pkl` (legacy) and '
               '`<label>_filter_impact_cv.pkl`, plus `test_positive_rate` / '
               '`predicted_positive_rate` and `threshold` / `mean_threshold` in the '
               'sidecars, for any fold whose validation ROC lies on or below the '
               'diagonal. I found no evidence it has fired: CV thresholds across all '
               "ten sidecars span 0.0067 to 0.8100 with none near a forest's maximum "
               'probability, and the legacy '
               '`rerun/logs/confusion_matrices_mean_raw.json` thresholds are '
               '0.1133-0.1833 (mortality) and 0.3733-0.4100 (icu). So no shipped '
               'number is presently believed wrong.'),
    recompute=('Nothing now. If the guard is changed and a re-run shows any fold '
                 'hitting it, stage B (rerun/regen_filter_impact.py) and/or stage F '
                 'must be re-run for the affected (aggregation, label).'),
    technical=('With scikit-learn 1.8.0 (requirements.txt:8) `roc_curve` returns '
                 '`thresholds[0] = np.inf` and thresholds in decreasing order; '
                 '`tpr[0] = fpr[0] = 0`, so `youden[0] = 0`. The last point is `tpr '
                 '= fpr = 1`, also J = 0, so the maximum of `youden` is never '
                 'negative and index 0 wins whenever `max(J) == 0` — a classifier no '
                 "better than chance at every cut. The fallback's `finite.max()` is "
                 '`thresholds[1]`, which equals the largest validation score, and '
                 'the prediction rule at evaluation_manager.py:184-185 (legacy) and '
                 '457 (CV) is `scores >= threshold`; on validation that keeps '
                 'exactly the top-scoring record(s) positive, and on the held-out '
                 'fold, whose scores are drawn from the same distribution and are '
                 'usually all strictly below the validation maximum, it typically '
                 'predicts all-negative. Correction to the claim: the operating '
                 'point selected is the *near*-all-negative one, not literally '
                 'all-negative — J = 0 there too, so it is no worse than the inf '
                 'point in Youden terms, but it is a maximally conservative choice '
                 'on a 10%-prevalence problem where the entire stated purpose of the '
                 'function (lines 66-70) is to avoid handing the decision to the '
                 'majority class. The identical logic is duplicated in the live '
                 'one-off `rerun/confusion_matrices_mean_raw.py:49-52`, and prior '
                 'art at '
                 '/home/ccampb47/work/hour_scaling_experiment/v2/metrics.py:100-103 '
                 'shares it, so a fix must touch at least the two in-repo copies. No '
                 'documentation states the max-finite choice is intended; '
                 'README.md\'s "Things that will bite you" (line 77 onward) and '
                 '/home/ccampb47/work/noahNotes.md say nothing about thresholds.'),
    fix=('In the non-finite branch return 0.5, matching the empty/single-class '
           'fallbacks at lines 81-85 — `if not np.isfinite(threshold): threshold = '
           '0.5` — or, if a data-driven point is wanted, pick the highest-J index '
           'rather than the first (`int(np.argmax(youden[1:])) + 1`) and only fall '
           'back to 0.5 when that too yields J <= 0. Record which branch fired in '
           'the diagnostics either way, since today a fallback threshold is '
           'indistinguishable from a chosen one.'),
    verification=('Unit-test `pick_threshold` on a deliberately anti-correlated '
                    'validation set (`y = [0,1,0,1,0,1]`, `scores = '
                    '[0.9,0.1,0.8,0.2,0.7,0.3]`), where `max(J) == 0`, and assert '
                    'the return is 0.5 rather than `max(scores)`; then re-run stage '
                    'F for one aggregation and confirm every `thresholds` entry and '
                    'every metric is unchanged, proving the branch is not exercised '
                    'on real data.\n'
                    'CONFIDENCE note is folded into the verdict: medium rather than '
                    'high because I could not execute `roc_curve` in this '
                    'environment (no numpy/sklearn on the login-node interpreter), '
                    'so the `thresholds[0] = inf` and decreasing-order properties '
                    "rest on the sklearn 1.8.0 pin plus the code's own comment at "
                    'line 91 rather than on a run I performed.'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C7',
        note=('Affects BOTH paths + confusion_matrices_mean_raw.py (shared '
             'pick_threshold); no shipped threshold consistent with the branch '
             'having fired. Realised risk Low.'),
    ),
),
dict(
    id='N-16', stage=EVAL, severity=LOW, status=INTRODUCED, verified=True,
    name='The OOF npz cannot reproduce the reported metrics',
    overview=('`evaluate_filter_impact_cv` persists per-repeat scores, ids and '
                'consensus labels but not `oof_predictions` or `thresholds` '
                '(evaluation_manager.py:713-717), even though both exist in the '
                'in-memory result dict (:520,:524). Since every reported accuracy/F1 '
                'is a function of the 20 per-fold thresholds, the npz alone cannot '
                'regenerate any published number; reproduction requires the separate '
                '`*_filter_impact_cv_diagnostics.json`, which the docstring at '
                ':649-650 does not mention.'),
    affects=('No published number is wrong. What is wrong is the reproducibility '
               'contract of `Data/mimic-iii/*/[label]_oof_scores_cv.npz` (13 arms x '
               '5 aggregations x 2 labels): anyone handed only the npz can compute '
               'new threshold-free metrics but cannot recover '
               '`accuracy_mean`/`f1_macro_mean` in the pickles or the four '
               'filter_impact figures.'),
    recompute=('Nothing. The missing arrays are derivable from the existing npz '
                 'plus the JSON sidecar (`fold_assignment` + '
                 "`thresholds['r{r}f{f}']`), so this is a "
                 'serialization/documentation fix, not a refit.'),
    technical=('In-memory, `evaluate_dataset_label_cv` returns `oof_predictions` '
                 '(:520), `thresholds` (:524), `y` (:518) and `per_repeat` (:523). '
                 'The writer at :710-718 keeps only `admission_ids`, `oof_scores` '
                 '(downcast to float32) and `consensus_predictions` per arm, plus '
                 '`raw_admission_ids`, `raw_labels`, `fold_assignment`. Reported '
                 'accuracy comes from `oof_predictions` (:474-480) which is '
                 '`oof_scores[r] >= threshold[r, fold]` (:457) — so the threshold '
                 'table is load-bearing and absent. Corrections to the claim: (a) '
                 'per-fold *scores* are present, since `oof_scores` is shaped '
                 '(n_repeats, n_records) (:413) and `fold_assignment` identifies '
                 "each record's fold, so only the *predictions* are missing and they "
                 'are recomputable once thresholds are supplied; (b) per-arm labels '
                 'are recoverable rather than lost — `raw_admission_ids` is unique '
                 "(verified: 46,032 ids, 46,032 distinct) and every arm's ids are a "
                 'subset, so an id join against `raw_labels` reconstitutes each '
                 "arm's `y`; (c) the thresholds do survive, in "
                 '`Data/mimic-iii/*/[label]_filter_impact_cv_diagnostics.json` under '
                 '`thresholds`. One residual exactness caveat: `oof_scores` is '
                 'stored float32 while thresholds are float64 decimals, and float32 '
                 'rounds *below* the exact float64 value for 144 of the 301 possible '
                 'k/300 vote fractions, so a record scoring exactly at its fold '
                 'threshold can flip on replay — bit-exact reproduction of '
                 '`oof_predictions` is not guaranteed even with the JSON.'),
    fix=("Add `payload[f'{slug}__oof_predictions']`, `payload[f'{slug}__y']` and a "
           'flattened threshold table (e.g. a (n_repeats, n_splits) float64 array '
           'plus a NaN for unfitted folds) to the payload at :713-717, keep '
           '`oof_scores` in float64 or document the float32 downcast, and amend the '
           'docstring at :649-650 to state exactly which artifacts are needed to '
           'reproduce which metrics.'),
    verification=('Load only the npz and recompute `accuracy_mean`/`f1_macro_mean` '
                    'per arm; they must match every value in the corresponding '
                    '`*_filter_impact_cv_diagnostics.json` and positions [1]/[3] of '
                    '`*_filter_impact_cv.pkl` exactly, with `high invalid data` '
                    'reproducing NaN.'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C9',
        note=('Corrections: per-fold scores recoverable via fold_assignment; labels '
             'recoverable via id join; thresholds survive in the JSON sidecar — '
             'residue is the undocumented npz+JSON coupling and a float32 downcast '
             'that can flip boundary records.'),
    ),
),
dict(
    id='N-17', stage=EVAL, severity=LOW, status=INTRODUCED, verified=True,
    name='Records covered once are weighted like records covered four times',
    overview=("`consensus_scores` divides each record's summed OOF scores by that "
                "record's own coverage count (:489-491), then thresholds every "
                'record at the single scalar `mean_threshold`, the mean of the 20 '
                "per-fold Youden thresholds (:492-497). Averaging four forests' "
                'scores shrinks the score distribution toward its centre while the '
                'threshold was chosen against unaveraged single-forest scores, so '
                'the consensus operating point is not the operating point any '
                'threshold was selected for; and if any fold failed to fit, records '
                'covered once and records covered four times — different variance — '
                'would be thresholded identically.'),
    affects=('Only the consensus-derived outputs: `mcnemar` details (`n01`, `n10`, '
               '`n_both_correct`, `n_both_wrong`, `*_accuracy_on_paired`) and '
               '`predicted_positive_rate` in every '
               '`*_filter_impact_cv_diagnostics.json`, plus position [4] (statistic, '
               'p-value) of every `*_filter_impact_cv.pkl` and '
               '`paper_figures/mcnemar_icu_mean.pdf` if regenerated from CV results. '
               'The table/figure accuracy and F1 are unaffected — they come from '
               'per-fold `oof_predictions`, which is why the two disagree in the '
               'artifacts (raw 0.6895 vs 0.6960; long missing segment 0.6342 vs '
               '0.7248, a 9-point gap on n=367).'),
    recompute=('If fixed, re-run rerun/regen_filter_impact_cv.py for all 5 '
                 'aggregations x 2 labels (McNemar statistics and p-values change) '
                 'and regenerate any McNemar figure sourced from the CV pickles. '
                 'Accuracy/F1 figures need no change.'),
    technical=("Per fold, the threshold is chosen on that fold's inner-validation "
                 "scores from that fold's forest (:451) and correctly applied to "
                 "that fold's single-forest test scores (:457). The consensus path "
                 'then builds a *different* statistic — a per-record mean over up to '
                 '`N_REPEATS` independent forests (:489-491) — and compares it to '
                 'the arithmetic mean of thresholds (:492). Var(mean of k scores) < '
                 'Var(single score), so the same threshold yields a different '
                 'sensitivity/specificity trade-off on consensus scores than on '
                 'per-fold scores; the artifact gap between `accuracy_mean` and '
                 '`*_accuracy_on_paired` above is the measurable footprint. The '
                 'claimed *mixing* of 1-draw and 4-draw records is latent only: '
                 '`covered_count` is per-record (:486) and would legitimately vary, '
                 'but I checked all 10 `*_filter_impact_cv_diagnostics.json` files '
                 'and every non-degenerate arm reports `n_folds_fitted: 20` with '
                 '`coverage: 1.0`, so in the shipped artifacts every covered record '
                 'is an average of exactly 4 draws and no unequal-variance mixing '
                 "occurred. The mixing path becomes live the moment one fold's fit "
                 'split goes single-class (:438-442) or one fold is empty '
                 '(:431-432), which is exactly what happens on aggressive arms '
                 '(`high invalid data` already hits `n_folds_fitted: 0` under three '
                 'aggregations).\n'
                 '\n'
                 'First-pass measurements retained: Coverage is 1.000 everywhere '
                 'today; assert it.'),
    fix=('Stop thresholding averaged scores at a mean of single-model thresholds. '
           'Either (a) derive `consensus_predictions` by majority/mean of the '
           'per-fold `oof_predictions` (each already at its own calibrated '
           'threshold, no re-thresholding), or (b) keep averaging scores but '
           're-select one consensus threshold on held-out consensus scores; and in '
           'either case record `covered_count` in the diagnostics and exclude or '
           'flag records whose coverage is below `N_REPEATS` rather than silently '
           'averaging fewer draws.'),
    verification=('With a synthetic arm forced to drop one fold, assert '
                    '`covered_count` heterogeneity is surfaced in diagnostics and '
                    'that no record with coverage < N_REPEATS is thresholded against '
                    'a full-coverage-calibrated threshold. Then confirm that the '
                    "arm's reported `accuracy_mean` and the McNemar "
                    '`*_accuracy_on_paired` agree to within Monte-Carlo noise '
                    'instead of the current systematic 0.5-1 point (9 points for '
                    'long missing segment) offset.'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C9',
        note=('Claimed mixing (1-draw vs 4-draw) is latent (coverage=1.0 everywhere); '
             'verified adjacent defect: variance-shrunk consensus scores thresholded '
             'at single-model-calibrated mean threshold — the source of the 0.5-9pt '
             'accuracy_mean vs accuracy_on_paired gap.'),
    ),
),
dict(
    id='N-18', stage=EVAL, severity=LOW, status=ARTIFACT, verified=True,
    name=('Per-repeat `n` is a coverage diagnostic, not an unused weight — the '
            'unweighted mean over repeats is exact here, not an approximation'),
    overview=('`evaluate_dataset_label_cv` records `n = covered.sum()` per repeat '
                '(:479) and reduces the repeats with the unweighted '
                '`_mean_of_finite` (:504-507). This is not a weighting error: every '
                "repeat's out-of-fold vector covers the arm's entire cohort by "
                'construction (`build_fold_assignment` assigns every record a fold '
                'in every repeat, partition_manager.py:93-105, and `project_to_arm` '
                'preserves that), so all finite-metric repeats within an arm carry '
                'an identical `n` and a weighted mean would return bit-identical '
                'values. Verified on disk: across all 130 arm entries in the ten '
                '`*_filter_impact_cv_diagnostics.json` sidecars, zero arms have more '
                "than one distinct `per_repeat['n']`, and recomputing the unweighted "
                'mean of the per-repeat accuracies reproduces the stored '
                '`accuracy_mean` to within 1e-12 for every arm.'),
    affects=("Nothing. `diagnostics['accuracy_mean']`/`f1_macro_mean` (:504,:506) "
               'feed positions [1] and [3] of the `evaluate_filter_impact_cv` tuple '
               '(:689,:691) and thence the `_cv.pkl` files and any figure built from '
               'them, but their values are unchanged by weighting because the '
               'weights are uniform in every shipped artifact.'),
    recompute='Nothing.',
    technical=('Each repeat is a full out-of-fold pass: the loop at :426-458 '
                 'writes `oof_predictions[repeat, test_positions]` for every fold, '
                 'and the partition itself is complete (`assignment` starts at -1 '
                 'and partition_manager.py:102-103 raises if any record stays '
                 'unassigned). So `covered = oof_predictions[repeat] >= 0` (:470) is '
                 'the whole arm unless a fold is skipped by the guards at :431-432 '
                 '(empty test/train side) or :438-442 (single-class fit split). '
                 'Empirically that never happens partially: across the ten sidecars '
                 'every arm reports either `n_folds_fitted: 20, coverage: 1.0` (124 '
                 'arms) or `n_folds_fitted: 0, coverage: 0.0` (6 arms) — no arm sits '
                 "between. The fully-degenerate case appends `{'accuracy': nan, "
                 "'f1_macro': nan, 'n': 0}` (:472), and `_mean_of_finite` (:345-352) "
                 'filters non-finite entries first, so a zero-`n` repeat cannot '
                 'enter the mean with a spurious equal weight either — e.g. `maximum '
                 'deviation/mortality`, arm `high invalid data`: four repeats of '
                 '`(n=0, accuracy=nan)`, `accuracy_mean = nan`. Concrete equal-`n` '
                 'examples from `mean/mortality_filter_impact_cv_diagnostics.json`: '
                 '`raw` n = [46032]×4, `long gap` n = [20323]×4, `high invalid data` '
                 'n = [1369]×4. Fold *sizes* within a repeat do differ by one record '
                 '(46032 is not divisible by N_SPLITS = 5, partition_manager.py:36), '
                 'but the per-repeat metric is computed over the union of that '
                 "repeat's folds, so intra-repeat fold size has no bearing on `n`. "
                 'On consumption: a grep of the pipeline (excluding `_deprecated/`, '
                 '`rerun/logs/`, `bug_register.py`) finds `per_repeat` only at '
                 'evaluation_manager.py:468/472/476/504-507/523 and :702, where it '
                 'is copied into the per-arm diagnostics dict and serialized to '
                 '`Data/mimic-iii/*/[label]_filter_impact_cv_diagnostics.json`; '
                 'nothing in `rerun/`, `Experiments/`, or `comparison/` reads it. It '
                 'is therefore a published diagnostic, and a useful one — it is the '
                 'field that makes the equal-coverage invariant auditable after the '
                 'fact, and a repeat with partial fold coverage would show up there '
                 'first.\n'
                 '\n'
                 'First-pass measurements retained: Coverage is 1.000 everywhere so '
                 'mean-of-repeats equals pooled OOF for accuracy today. For macro-F1 '
                 'they differ even at equal n, though the measured gap is negligible '
                 '(0.69772 vs 0.69774).'),
    fix=('None required. If the residual theoretical exposure (one repeat losing '
           'some but not all folds on a tiny arm, which would then enter the '
           'unweighted mean with equal weight while covering fewer records) is to be '
           'closed, the right response is a guard, not a weight: raise or flag when '
           "`len({r['n'] for r in per_repeat if np.isfinite(r['accuracy'])}) > 1`, "
           'since size-weighting replicates that estimate *different* subpopulations '
           'blends rather than reports the coverage loss. Optionally add one line to '
           'the comment at :465-467 recording that `n` is a coverage check and '
           'equal-by-construction, so the next reader does not mistake it for an '
           'omitted weight.'),
    verification=("Assert `len({r['n'] for r in per_repeat if "
                    "np.isfinite(r['accuracy'])}) <= 1` for every arm of every "
                    '`*_filter_impact_cv_diagnostics.json` — it holds for all 130 '
                    'arm entries today — and separately assert `abs(mean(finite '
                    'accuracies) - accuracy_mean) < 1e-12`, which also holds for all '
                    '130. Any future failure of the first assertion means a fold '
                    'silently failed to fit, which is the real defect that would '
                    'need attention.'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='ARTIFACT', mode='cluster C9 + solo tie-breaker',
        note=('Escalated; the two independent agents agreed there is no defect but '
             'labelled it differently — cluster C9 said INTENTIONAL, the solo '
             'tie-breaker said ARTIFACT. Adjudicated as ARTIFACT: the taxonomy '
             'reserves INTENTIONAL for a documented, internally consistent decision, '
             'and nothing in noahNotes.md, either README or notebook.py documents '
             'the averaging choice either way, so it falls to be judged on the '
             'statistics — where the unweighted mean is not an approximation but '
             "exact. Every repeat's out-of-fold vector covers the whole arm by "
             'construction (partition_manager.py:93-105 raises if any record is left '
             'unassigned), so the weights are uniform: across all 130 arm entries in '
             'the ten *_filter_impact_cv_diagnostics.json sidecars, zero arms have '
             'more than one distinct per-repeat `n`, and the stored accuracy_mean '
             'reproduces the unweighted mean to within 1e-12. The recorded `n` is a '
             'serialized coverage diagnostic, not an omitted weight. Suggested guard '
             'instead of a weight: assert the finite-metric repeats within an arm '
             'share one `n`, which would surface a partially-failed fold rather than '
             'blending it away. Reclassification confirmed by an independent solo '
             'tie-breaker agent.'),
    ),
),
dict(
    id='N-19', stage=EVAL, severity=LOW, status=OPEN, verified=True,
    name='Youden ties break toward the lowest-sensitivity threshold',
    overview=('np.argmax returns the first maximum, which on a ROC curve is the '
                'highest threshold among tied operating points.'),
    affects=('The selected `threshold` for any fold with tied J, and through it '
               '`testing_averages`/`testing_f1s` (positions [1] and [3]) and the '
               'positive-rate diagnostics of both `<label>_filter_impact.pkl` and '
               '`<label>_filter_impact_cv.pkl`, plus '
               '`rerun/logs/confusion_matrices_mean_raw.json`. I could not quantify '
               'how often ties occur, so I cannot attribute any specific published '
               'number to it.'),
    recompute=('If the tie-break is changed, stage B and stage F for every '
                 '(aggregation, label) — thresholds shift, so out-of-fold '
                 'predictions and every derived accuracy/F1 shift with them. Only '
                 'worth doing if a measurement shows ties are common.'),
    technical=("`roc_curve`'s documented contract is decreasing thresholds; `tpr` "
                 'and `fpr` are cumulative and non-decreasing, so index order runs '
                 'from the strictest cut (0,0) to the loosest (1,1). Ties in `tpr - '
                 'fpr` arise whenever consecutive cut-points add positives and '
                 'negatives in proportion, and they are made likelier here by score '
                 'quantisation: the forests use `n_estimators=300` (lines 175, 444), '
                 'so `predict_proba` outputs are multiples of 1/300 — consistent '
                 'with the shipped thresholds, which are all k/300 values (0.4633, '
                 '0.3967, 0.2500, 0.5000, 0.8000, ...) — and the small arms select '
                 'on inner-validation sets of only a few dozen records, where many '
                 'distinct cuts can share the same J. Because `argmax` takes the '
                 'first, the chosen point is the one furthest toward the (0,0) '
                 'corner, i.e. minimum sensitivity among the tied set. The same '
                 'construct is duplicated at '
                 'rerun/confusion_matrices_mean_raw.py:49. Nothing in README.md, '
                 '/home/ccampb47/work/noahNotes.md, or the docstring states a '
                 'preference between tied points, so this is an unexamined '
                 'consequence of `argmax` rather than a chosen rule.\n'
                 '\n'
                 'First-pass measurements retained: On a 9.7% prevalence problem '
                 'with many tied J values, the first maximum is the most '
                 'conservative operating point.'),
    fix=('Break ties explicitly and document the choice. E.g. `best = '
           'int(np.flatnonzero(youden == youden.max())[-1])` to prefer the most '
           'sensitive tied point, or select the tied index closest to the ROC '
           'top-left corner (`argmin((1-tpr)**2 + fpr**2)` restricted to the tied '
           'set). Whichever is chosen, apply it in both `pick_threshold` and '
           '`youden_threshold` so the one-off script keeps matching, as its '
           'docstring at rerun/confusion_matrices_mean_raw.py:42 promises.'),
    verification=('First measure the exposure: from '
                    '`Data/mimic-iii/<agg>/<label>_oof_scores_cv.npz` recompute each '
                    "fold's validation ROC and count folds where `argmax` is not "
                    'unique. Then unit-test `pick_threshold` on a hand-built tie '
                    '(two cut-points with equal J) and assert the returned threshold '
                    'is the lower one; and re-run stage F for one aggregation to see '
                    'how many thresholds and metrics actually move.\n'
                    'CONFIDENCE note: medium — the mechanism follows from '
                    "`roc_curve`'s documented ordering and is unambiguous in the "
                    'code, but I could not run numpy/sklearn here to demonstrate a '
                    'tie on real validation scores, so the frequency (and hence '
                    'whether any current figure is affected) is unverified.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C7',
        note=('n_estimators=300 quantisation (all shipped thresholds are k/300) makes '
             'ties likelier; frequency unmeasured. Same argmax interacts with N-15.'),
    ),
),
dict(
    id='N-20', stage=EVAL, severity=LOW, status=RESOLVED, verified=True,
    name='Zero-record arm returned a diagnostics dict with the wrong key set',
    overview=('`evaluate_dataset_label_cv` used to short-circuit when an arm held '
                'no records and return a diagnostics dict whose key set differed '
                "from the normal path's; `evaluate_filter_impact_cv` then indexed "
                "`result['diagnostics']['accuracy_mean']` unconditionally and raised "
                '`KeyError`. This killed exactly the six of ten stage-F array tasks '
                'whose aggregation leaves `high invalid data` with zero records (the '
                'three deviation aggregations × two labels). The current working '
                'tree removes the early return entirely so the empty arm walks the '
                'same reducers, and a regression test plus reproduced artifacts '
                'confirm it.'),
    affects=('Was: `Data/mimic-iii/{standard deviation,mean deviation,maximum '
               'deviation}/{icu,mortality}_filter_impact_cv*.{pkl,json,npz}` were '
               'never written by job 19578196. All twelve sidecars now exist (job '
               '19580846, 2026-08-11 15:24-15:35) with `high invalid data` carrying '
               '`n_records: 0, degenerate: true, accuracy_mean: NaN`. Nothing is '
               'currently wrong.'),
    recompute=('Nothing — stage F has already been re-run successfully for all 10 '
                 'tasks (rerun/logs/f_filter_impact_cv_19580846_*.log).'),
    technical=('The failure is reproduced verbatim in the logs: `grep -c KeyError` '
                 'over `f_filter_impact_cv_19578196_*.log` returns 0 for tasks 0-3 '
                 'and 1 for tasks 4-9, i.e. six of ten, and task indexing via '
                 '`agg_label_from_task_id` (rerun/_common.py) maps 4-9 to standard '
                 'deviation / mean deviation / maximum deviation × {icu, mortality} '
                 '— the aggregations whose stage-E log records `high invalid data: 0 '
                 'ids` (rerun/logs/e_admission_ids_19573270_4.log). The traceback '
                 'lands on evaluation_manager.py:693 in the 19578196 run; in the '
                 'current file the equivalent statement is at '
                 'evaluation_manager.py:689 '
                 "(`testing_averages.append(result['diagnostics']['accuracy_mean'])`) "
                 'and is still unguarded — which is fine, because the callee now '
                 'always builds the full dict. In the working tree there is no early '
                 'return in `evaluate_dataset_label_cv`; the comment at 419-424 '
                 'stands in its place, the fold loops at 426-463 no-op for '
                 '`n_records == 0`, the per-repeat reducer short-circuits to NaN at '
                 '471-473, and `diagnostics` is assembled unconditionally at 499-514 '
                 'with `degenerate: not bool(thresholds)` (512) and '
                 '`fold_prevalences` returning its two NaN keys for empty labels '
                 '(partition_manager.py:182-183). `verify_cv.py` section 4b '
                 '(179-198) exercises this against a synthetic '
                 '`DatasetEHR().create([])` and asserts both top-level and '
                 'diagnostics key-set equality against the raw arm; '
                 '`rerun/logs/g_verify_cv_19580847.log` shows those four checks '
                 'passing. The legacy path was never affected: its empty-split early '
                 'return (evaluation_manager.py:167-171) updates diagnostics with '
                 'the same four keys the normal path adds at 189-196.\n'
                 '\n'
                 'First-pass measurements retained: Listed despite being resolved '
                 'because it exposed a real gap in the verification: verify_cv.py '
                 'ran only on the mean aggregation, where that arm has 1,369 '
                 'records, so the degenerate path was never exercised.'),
    fix=('Already applied — the special-cased empty-arm return was deleted from '
           '`evaluate_dataset_label_cv`. If any further hardening is wanted, make '
           'the guarantee explicit rather than incidental by extracting the '
           'diagnostics-dict construction into a helper with a fixed key list, so a '
           'future early return cannot drift from it.'),
    verification=('Already verified three ways: (1) `rerun/verify_cv.py` section '
                    '4b passes on a synthetic empty arm regardless of aggregation, '
                    '(2) all ten stage-F tasks completed in job 19580846 where six '
                    'failed in 19578196, (3) the deviation-aggregation sidecars on '
                    'disk contain a well-formed `high invalid data` record with the '
                    'full key set and `degenerate: true`.'),
    found='2026-08-11',
    fixed='2026-08-11',
    audit=dict(
        date='2026-08-12', verdict='FIXED-IN-WORKING-TREE', mode='cluster C8',
        note=('Independently re-derived from code by a blind verification agent; '
             'description updated where the re-derivation was more precise.'),
    ),
),

# ── CPU backend ───────────────────────────────────────────────────────────────
dict(
    id='B-01', stage=BACKEND, severity=MEDIUM, status=OPEN, verified=True,
    name='max_depth is not reconciled between cuML and sklearn',
    overview=("cuML's forest defaults to depth 16, sklearn's to unlimited, so the "
                'CPU forests are far higher capacity and the in-sample columns are '
                'pure memorisation.'),
    affects=('Everything produced by a training job through this shim: '
               '`Data/mimic-iii/<agg>/{icu,mortality}_filter_impact.pkl` + '
               '`_diagnostics.json` (2026-08-10 21:38), `..._filter_impact_cv.pkl`, '
               '`..._oof_scores_cv.npz`, `..._filter_impact_cv_diagnostics.json` '
               '(2026-08-11 15:35), '
               '`paper_figures/filter_impact_*_{accuracy,f1}_mean.pdf`, and '
               '`rerun/logs/{classifier_performance_mean_raw.xlsx,confusion_matrices_m'
               'ean_raw.json}`. Train-side columns are the worst hit: '
               '`train_f1=0.9996` for mean/icu raw is essentially memorisation of '
               'the fit split, which a depth-capped forest could not reach. '
               'Within-run filter-vs-raw deltas and McNemar counts are still '
               'internally consistent (every arm shares the estimator) but are '
               "deltas of a different model than the GPU run's."),
    recompute=('Every training job and its downstream artifacts: '
                 '`job_b_filter_impact.sh`, `job_f_filter_impact_cv.sh`, '
                 "`job_d_confusion.sh`, then the notebook's figure export "
                 '(`paper_figures/filter_impact_*`) and '
                 '`export_confusion_workbook.py`.'),
    technical=('`rerun/_cpu_backend.py:63-77` defines `class '
                 'RandomForestClassifier(_SkRF)` and forwards `**kwargs` after '
                 'popping the two cuML-only arguments and setting `n_jobs`; there is '
                 'no `kwargs.setdefault("max_depth", ...)` in the file (verified by '
                 'grep for `max_depth` across the repo — the only hits are in the '
                 'vendored sklearn source, none in `rerun/` or `Managers/`). The '
                 'class is registered as `cuml.ensemble.RandomForestClassifier` at '
                 '`rerun/_cpu_backend.py:92`, and '
                 '`Managers/evaluation_manager.py:16` imports it from there. All '
                 'three construction sites — `:55` (`cross_validate_model`), `:175` '
                 '(legacy `evaluate_dataset_label_impact`), `:444` (CV '
                 '`evaluate_dataset_label_cv`) — pass only `n_estimators=300, '
                 'random_state=seed`, so the depth default is what governs. '
                 "sklearn's default is `max_depth=None` (vendored "
                 '`_forest.py:1516`). The observable fingerprint is in '
                 '`rerun/logs/b_filter_impact_19487956_0.log:18`, `train_f1=0.9996` '
                 'against `test_f1=0.6911`; the same field ranges 0.89–0.96 in the '
                 'other nine array tasks, so the memorisation is strongest where the '
                 'feature vectors are most distinctive rather than uniform. Note '
                 '`rerun/confusion_matrices_mean_raw.py:93-94` builds the forest '
                 'from sklearn directly with the same three arguments, so it shares '
                 'the divergence (internally consistent with the shim, but equally '
                 'unlike cuML).\n'
                 '\n'
                 'First-pass measurements retained: Confirmed in the artifacts: '
                 'train_acc ~0.97 and train_f1 ~0.93, essentially constant across '
                 'all 13 arms.'),
    fix=('In `rerun/_cpu_backend.py.__init__`, add `kwargs.setdefault("max_depth", '
           '16)` to match the cuML default, and translate rather than drop '
           "`split_criterion` (`0 -> criterion='gini'`, `1 -> 'entropy'`) so a "
           'future caller cannot silently lose it. Mirror the same default in '
           '`rerun/confusion_matrices_mean_raw.py:93-94`, and record the effective '
           "forest hyperparameters in the diagnostics JSON sidecars so a run's "
           'capacity is recoverable from its artifacts.'),
    verification=('After the change, assert `max(est.tree_.max_depth for est in '
                    'model.estimators_) <= 16` on a fitted arm, and confirm the '
                    'recorded hyperparameters appear in the new `_diagnostics.json`. '
                    'Then re-run one array task and check `train_f1` falls '
                    'materially below the current 0.9996 while the out-of-fold '
                    'accuracy is re-derived from scratch; the old and new pickles '
                    'must not be mixed in any figure.'),
    found='2026-08-11 statistical audit; verified from the sidecars',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C10',
        note=('cuML default depth 16 not verifiable on disk (cuML not installed); '
             'sklearn unlimited-depth half verified in vendored source. train_f1 '
             '0.9996 fingerprint in logs.'),
    ),
),
dict(
    id='B-02', stage=BACKEND, severity=MEDIUM, status=OPEN, verified=True,
    name='The accuracy shim discards kwargs and truncates rather than rounds',
    overview=("The shim's `accuracy_score` accepts `**kw` and never forwards it to "
                'sklearn, and it coerces both arguments with `.astype(int)` '
                '(truncation, not rounding). Neither behaviour alters a reported '
                'number in the current tree: the single call site passes two '
                'positional arrays, labels are integer-typed all the way from '
                "`to_tensor`, and the shim's own `predict` already returns ints. It "
                'is a silent-wrong-answer trap for any future caller, not an active '
                'defect.'),
    affects=('Nothing measurable. The only consumer is the legacy `cv` column via '
               '`cross_validate_model` (`Managers/evaluation_manager.py:33-60`, '
               'called at `:173`), which feeds '
               '`Data/mimic-iii/<agg>/*_filter_impact.pkl` element 0; with integer '
               'labels and integer predictions the casts are identity, so those '
               'numbers are unaffected. The CV path never calls it.'),
    recompute='Nothing.',
    technical=('`rerun/_cpu_backend.py:86-88` defines `accuracy_score(y_true, '
                 'y_pred, **kw)` and drops `kw` on the floor before delegating to '
                 '`sklearn.metrics.accuracy_score`; it is installed as '
                 '`cuml.metrics.accuracy_score` at `:94` and imported at '
                 '`Managers/evaluation_manager.py:17`. A repo-wide grep for '
                 '`accuracy_score(` finds exactly one live call, '
                 '`Managers/evaluation_manager.py:58`, with two positional arguments '
                 'and no keywords — so nothing is being ignored in practice. On the '
                 'truncation half: `Entities/ehr_record.py:47` builds labels as '
                 '`dtype=torch.long`, `Managers/dataset_manager.py:186` materialises '
                 "them with `.item()` into an integer array, and the shim's "
                 '`predict` (`rerun/_cpu_backend.py:83`) already applies '
                 '`.astype(int)`, so both operands are integral and `astype(int)` '
                 'cannot truncate anything today. The kwargs framing also needs '
                 'correcting: the sklearn signature is `accuracy_score(y_true, '
                 'y_pred, *, normalize=True, sample_weight=None)` (vendored '
                 '`sklearn/metrics/_classification.py:346`), but this function '
                 'stands in for `cuml.metrics.accuracy_score`, whose public '
                 'signature does not offer `normalize`/`sample_weight` at all — so '
                 "the divergence is against sklearn's API, not against the API being "
                 'shimmed. Real risk is asymmetric: a caller writing '
                 '`accuracy_score(y, p, normalize=False)` gets a fraction back with '
                 'no error, and any future float-valued or probability-valued '
                 'argument would be floored (0.87 -> 0) instead of rounded.\n'
                 '\n'
                 'First-pass measurements retained: Separately .astype(int) '
                 'truncates: if probabilities were ever passed as predictions, every '
                 '0<p<1 becomes 0 and accuracy comes back as about 1 - prevalence = '
                 '0.90, which looks entirely plausible.'),
    fix=('Give the shim the API it impersonates and fail loudly otherwise: accept '
           'only `(y_true, y_pred, handle=None, convert_dtype=True)` and raise '
           '`TypeError` on anything else, or forward `**kw` verbatim to '
           '`_sk_accuracy` so `normalize`/`sample_weight` work as written. Replace '
           '`.astype(int)` with `np.rint(...).astype(int)` and assert the inputs are '
           'within tolerance of integers before casting.'),
    verification=('Add an assertion-style check that `accuracy_score(y, p, '
                    'normalize=False)` either returns a count or raises, never a '
                    'silently-normalised fraction; and that '
                    '`accuracy_score([1,1],[0.6,0.6])` no longer scores 0.0 by '
                    'flooring. Re-running the legacy sweep should reproduce the '
                    'current `cv` values bit-for-bit, since the casts are identity '
                    'on integer input.'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C10',
        note=('Corrections: latent — single call site passes no kwargs, labels are '
             "torch.long so casts are identity; shim impersonates cuML's API (which "
             'lacks normalize/sample_weight). Severity suggestion: Low. Shim '
             "docstring's float-labels claim contradicts ehr_record.py:47."),
    ),
),
dict(
    id='B-03', stage=BACKEND, severity=LOW, status=INTENTIONAL, verified=True,
    name=('CPU backend maps cp.asnumpy to np.asarray, which aliases instead of '
            'copying — documented, and harmless at every current call site'),
    overview=('The CPU shim registers `asnumpy=np.asarray` (_cpu_backend.py:48), '
                'so `cp.asnumpy(x)` returns `x` itself for any ndarray input rather '
                'than an independent host buffer. Real `cupy.asnumpy` only '
                'guarantees a copy when handed a *device* array; for a host ndarray '
                'it falls back to `numpy.asarray` and also returns the same object, '
                'and under this backend no device array can ever exist. The comment '
                'two lines above the registration states the choice and its '
                'rationale explicitly, and all six live call sites either copy '
                'immediately via `.astype(int)` or consume a freshly allocated '
                'temporary, so no number, pickle, or figure is affected.'),
    affects=('Nothing. No metric, pickle, JSON sidecar, or figure differs because '
               'of this. The only theoretical exposure is '
               '`evaluation_manager.py:114`, the single site whose argument is '
               'persistent state (`model.classes_`), and it is protected by '
               '`.astype(int)` before use.'),
    recompute='Nothing.',
    technical=('(a) Reference semantics — `cupy.asnumpy(a)` returns `a.get(...)`, '
                 'a newly allocated host buffer, when `a` is a `cupy.ndarray`; for a '
                 'host input it returns `numpy.asarray(a, order=order)`, i.e. no '
                 'copy. The shim installs `asnumpy=np.asarray` (_cpu_backend.py:48) '
                 'alongside `ndarray=np.ndarray`, `asarray=np.asarray`, '
                 '`array=np.array` (lines 45-47), so under the backend every array '
                 'is already a host ndarray and `np.asarray` is precisely the branch '
                 'real cupy would take. The divergence is therefore not against '
                 'cupy-given-these-inputs; it is against the historical GPU '
                 'deployment, where the same call sites received device arrays and '
                 'got copies.\n'
                 '(b) Call-site walk, all six live sites (the only `asnumpy` '
                 'consumers in the toolbox outside `_deprecated/`):\n'
                 '1. evaluation_manager.py:113 `probabilities = '
                 'np.asarray(cp.asnumpy(model.predict_proba(features)))` — argument '
                 'is a fresh per-call sklearn allocation with no other reference; '
                 'result is only read (column slice at :119, `>=` comparisons at '
                 ':171-173, `roc_curve`/`f1_score`). No mutation of result or source.\n'
                 '2. evaluation_manager.py:114 `classes = '
                 'np.asarray(cp.asnumpy(model.classes_)).astype(int).tolist()` — the '
                 'one site aliasing persistent estimator state, but `.astype(int)` '
                 '(numpy default `copy=True`) allocates before `.tolist()`, so '
                 '`model.classes_` is never written. No mutation.\n'
                 '3-5. evaluation_manager.py:155-157 `y_train_host = '
                 'cp.asnumpy(y_train).astype(int) ...` (and `y_test`, '
                 '`y_validation`) — `.astype(int)` copies, so the `*_host` vectors '
                 'that go into the returned 5-tuple are independent of the arrays '
                 "later handed to `final_model.fit(x_train, y_train)`; the shim's "
                 'own `fit` re-copies via `np.asarray(y).astype(int)` '
                 '(_cpu_backend.py:80). No mutation.\n'
                 '6. evaluation_manager.py:372 `return features, '
                 'cp.asnumpy(labels).astype(int)` in `_flatten_whole_dataset` — '
                 '`.astype(int)` copies, and the source `labels` is itself a fresh '
                 '`cp.array([...])` built from a Python list '
                 '(dataset_manager.py:186). Downstream in the CV path the resulting '
                 '`labels` is only fancy/boolean-indexed (`labels[fit_positions]` '
                 ':437, `labels[validation_positions]` :450, `labels[covered]` '
                 ':474), all of which copy.\n'
                 'The only in-place writes in the file target locally allocated '
                 'buffers: `oof_scores`/`oof_predictions` created by `np.full` at '
                 ':412-413 and written at :456-457, '
                 '`consensus_scores`/`consensus_predictions` created at :487/:494 '
                 'and written at :489/:495, and the McNemar `table = np.zeros((2, '
                 '2), dtype=int)` at :229 written at :231. None of them is a shim '
                 'return value.\n'
                 '(c) The shim documents the divergence at _cpu_backend.py:41-42, '
                 'naming `asnumpy` and stating it "is the identity here". The module '
                 'docstring (lines 10-14) separately flags the one divergence that '
                 'does change numbers — cuML vs sklearn forests — showing the author '
                 'distinguishes faithful from unfaithful stand-ins deliberately.'),
    fix=('None required for correctness. If belt-and-braces is wanted, the copy is '
           'cheap here (only label vectors and n x 2 probability matrices, well '
           'under 1 MB at ~46k records): register `asnumpy=lambda a, *_, **__: '
           'np.array(a, copy=True)` at _cpu_backend.py:48. Cheaper and equally '
           'sufficient: extend the comment at :41-42 to state the contract '
           'explicitly — "returns the same buffer, not a copy; do not mutate the '
           'result or the source in place" — so a future in-place edit at a call '
           'site is not silently aliased.'),
    verification=('Temporarily register `asnumpy` as a copying variant and re-run '
                    'one arm of `rerun/regen_filter_impact_cv.py`; the resulting '
                    'pickle and JSON sidecar must be byte-identical to the current '
                    'output, proving no call site depends on aliasing. Statically, '
                    're-grep `Managers/` and `rerun/` for in-place operators (`+=`, '
                    '`[...] =`, `.fill(`, `.sort(`, `out=`) applied to any name '
                    'assigned from `cp.asnumpy(...)` — currently zero hits.'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='INTENTIONAL', mode='cluster C10 + solo tie-breaker',
        note=('Escalated and independently confirmed INTENTIONAL by a solo '
             'tie-breaker. Cited line has drifted: the registration is '
             '`asnumpy=np.asarray` at rerun/_cpu_backend.py:48, not :52. Two grounds '
             'for INTENTIONAL: the divergence is documented at :41-42, which names '
             '`asnumpy` and states it is the identity with the rationale (guardrail '
             '10 satisfied); and for the host arrays this backend can actually '
             'produce, real `cupy.asnumpy` takes the same `numpy.asarray` no-copy '
             'branch, so "cupy would copy" holds only against the historical GPU '
             'deployment. All six live call sites were walked individually and each '
             'either copies immediately via `.astype(int)` or consumes a fresh '
             'temporary; the only site aliasing persistent state '
             '(evaluation_manager.py:114, `model.classes_`) is protected by that '
             'copy. Residual latent trap recorded honestly: the comment justifies '
             'skipping the transfer but does not state the aliasing contract, so the '
             'safety rests on `.astype(int)` happening to copy — worth strengthening '
             'the comment. `asarray=np.asarray` (:47) carries the same divergence '
             'with a stronger claim against it and is harmless for the same reason. '
             'Severity suggestion: Informational rather than Low. Reclassification '
             'confirmed by an independent solo tie-breaker agent.'),
    ),
),

# ── Reporting ─────────────────────────────────────────────────────────────────
dict(
    id='R-01', stage=REPORT, severity=CRITICAL, status=OPEN, verified=True,
    name=('The comparison notebook substitutes a different model on a different '
            'cohort'),
    overview=('After fitting both pipelines honestly, one cell overwrites the EHR '
                'results with numbers from a different model trained on a different '
                'cohort — so the head-to-head is not comparing preprocessing.'),
    affects=("Cell 16's summary table (all five EHR rows: 0.9124/0.9120/0.5719 "
               'etc.), cell 18\'s three-panel bar chart and the "EHR − MIMIC" '
               "deviation heatmap, cell 33's summary dashboard, and the extracted "
               'PNGs under '
               '/home/ccampb47/work/clinical_preprocessing_toolbox/figures/Comparison/'
               'pipeline_comparison/. It also makes the notebook internally '
               "inconsistent: cell 20's McNemar test still uses `ehr_res['preds']`, "
               'which the override does not touch, so the significance test compares '
               'LR-vs-LR predictions while the bars compare LR-vs-RF scores. The ± '
               'values become 0.0000 for EHR because the override collapses four '
               'seeds into a one-element list.'),
    recompute=('Re-execute comparison/pipeline_comparison.ipynb '
                 '(comparison/run_pipeline_comparison.sbatch) and re-run '
                 'gallery/extract_notebook_graphs.py + build_manifest.py to refresh '
                 'figures/Comparison/pipeline_comparison/.'),
    technical=('pipeline_comparison.ipynb cell 16 (JSON lines ~975-1005) loops '
                 'over `SEEDS` with a single `StratifiedShuffleSplit` per seed, and '
                 'for both `X_mimic` and `X_ehr` fits '
                 '`LogisticRegression(**MODEL_KWARGS)` (cell 4, JSON:10 — '
                 "`max_iter=500, solver='liblinear'`), recording acc/f1/auc/preds "
                 'per seed. Lines 1008-1014 then discard the EHR half of that work. '
                 '`EHR_FILTER_IMPACT` is built in cell 10 (JSON:665) from '
                 '`../pipelines/EHR-Dataset-Processing/Data/mimic-iii/<agg>/mortality_'
                 'filter_impact.pkl`, produced by `evaluate_filter_impact` in '
                 'pipelines/EHR-Dataset-Processing/Managers/evaluation_manager.py:237,'
                 ' whose docstring (lines 260-262) states the test metrics use "a '
                 'threshold chosen on the validation split, not the implicit 0.5" '
                 'and that absolute scores are not comparable across runs. That '
                 'pipeline runs on the whole EHR cohort with a forest, so nothing '
                 'about index 0 is on the shared 27,295-admission join. The '
                 'justification in the override comment ("The in-notebook EHR '
                 'feature extractor produces NaN") is contradicted by the notebook\'s '
                 'own cell 14 output, which reports EHR missingness of 0.1–1.6%, and '
                 'by `impute_and_scale` (cell 8, JSON:~440) which mean-fills and '
                 'then `.fillna(0.0)` — so the honest EHR fit cannot yield NaN '
                 'metrics.\n'
                 '\n'
                 'First-pass measurements retained: After it, the EHR column is a '
                 '300-tree random forest on the full 46,032-record cohort, '
                 'unstratified 80/10/10, at a Youden threshold, on 168 flattened '
                 'features rather than 7 aggregated ones.'),
    fix=("Delete the override block (JSON lines 1008-1015) and let the seed loop's "
           'own EHR results stand; if the in-notebook EHR extractor genuinely '
           'produces degenerate features, fix the extractor (cell 8 '
           '`ehr_record_to_hourly_matrix` / cell 12) rather than substituting '
           'foreign numbers. If a cross-pipeline RF reference is wanted, plot it as '
           'a separately labelled series, never as the EHR arm of the head-to-head.'),
    verification=('After removal, EHR rows in the cell 16 table must show non-zero '
                    '± std across the four seeds, and EHR accuracy must equal a '
                    "value recomputable from `EVAL_RESULTS[m]['ehr']['preds']` and "
                    "`y_test_list` (i.e. `accuracy_score` on the notebook's own "
                    "arrays); assert `EVAL_RESULTS[m]['ehr']['acc'] != "
                    "[EHR_FILTER_IMPACT[m]['acc'][0]]` and that "
                    "`len(EVAL_RESULTS[m]['ehr']['acc']) == len(SEEDS)`."),
    found='2026-08-11 reporting audit; verified in the notebook',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C11',
        note=('Documented intent (comparison notebook markdown cell 0, toolbox README '
             '`comparison/` section) promises identical logistic regressions on '
             'matched features and explains why a random forest was deliberately '
             'avoided — guardrail 10 makes that contradiction confirm the bug. '
             'Override is cell 16, over the 27,295 shared admissions.'),
    ),
),
dict(
    id='R-02', stage=REPORT, severity=CRITICAL, status=OPEN, verified=True,
    name='Scenario accuracy deltas subtract an unpaired baseline',
    overview=('Each MIMIC_Extract scenario is a different cohort, but the delta is '
                'taken against the full-cohort baseline — so it measures cohort '
                'difficulty. The correctly paired number is already in the same '
                'pickle, unused.'),
    affects=('The heatmap "MIMIC_Extract — Test Accuracy Δ vs Baseline by Scenario '
               '& Aggregation (% points)" (cell 25) and the left panel of all five '
               '"Cross-pipeline deviation" bar charts (cell 31), plus their '
               'extracted PNGs in figures/Comparison/pipeline_comparison/. '
               'Magnitudes are wrong by roughly an order of magnitude and can flip '
               'sign: for aggregation `mean`, scenario `age35_range5` the notebook '
               'reports +4.98 pp (0.96842 − 0.91864) where the paired figure is '
               '+0.18 pp (0.96842 − 0.96665); `min48hr` is reported as −2.70 pp '
               "where the paired figure is −0.13 pp. The notebook's own markdown for "
               'cell 30 claims this view "isolates the preprocessing effect from '
               'cohort-size effects", which it does not.'),
    recompute=('Nothing needs re-fitting — `baseline_acc_on_var_test` is already '
                 'in every '
                 '`data/scenario_analysis/<agg>/mortality_scenario_impact.pkl`. Only '
                 'the notebook cells must be re-executed and the figures '
                 're-extracted.'),
    technical=('`MIMIC_SCENARIO_IMPACT` is loaded in cell 10 (JSON:~672-674) from '
                 '`data/scenario_analysis/<agg>/mortality_scenario_impact.pkl`. '
                 'Those pickles are produced by the `evaluate_for_method` code in '
                 'notebooks/_patch_copy2.py:164-321 (mirrored in '
                 'notebooks/mimic_extract_analysis.py:848). There, the baseline '
                 "arm's per-seed split is stored (`raw_preds_by_seed`, line 213) and "
                 'each variant is evaluated only on `test_ids_v = '
                 'v_pat.index.intersection(base_test_ids)` (line 247), while '
                 "`results['raw']['test_acc']` (line 219) is the mean over the "
                 '*full* baseline test split. Lines 281-288 deliberately replay the '
                 'baseline model, scaler and column means on `test_ids_v` and store '
                 'the result as `baseline_acc_on_var_test` (line 305), and the '
                 'module docstring lists this as review fix 5: "Per-variant table '
                 'reports baseline performance on the same intersection" '
                 '(_patch_copy2.py:14). The comparison notebook ignores that key: '
                 'cell 25 (JSON:1478) and cell 31 (JSON:1741) both difference '
                 "against `['raw']['test_acc']`. A grep for "
                 '`baseline_acc_on_var_test` across the live tree finds it only in '
                 'the producer files, never in comparison/.\n'
                 '\n'
                 'First-pass measurements retained: Verified on mean/mortality:\n'
                 '  age35_range5    plotted +0.0498   paired +0.0018   28x\n'
                 '  age35_range10   plotted +0.0423   paired +0.0018   24x\n'
                 '  age45_range15   plotted +0.0343   paired -0.0000   SIGN FLIP\n'
                 '  age55_range10   plotted +0.0246   paired -0.0023   SIGN FLIP\n'
                 '  age55_range15   plotted +0.0209   paired -0.0021   SIGN FLIP\n'
                 '  min48hr         plotted -0.0270   paired -0.0013   20x The '
                 "cell's own comment notes the values 'cluster around 0.04-0.05' — "
                 'the author noticed they were implausibly large and treated it as a '
                 'formatting problem. Deltas should collapse to the 0.00x range and '
                 'three should change sign.'),
    fix=("In cell 25 and cell 31 compute `MIMIC_SCENARIO_IMPACT[m][sc]['test_acc'] "
           "- MIMIC_SCENARIO_IMPACT[m][sc]['baseline_acc_on_var_test']` per scenario "
           "(falling back to NaN when the key is missing/NaN, as it is for `'raw'`), "
           'and update the titles/markdown to say "vs baseline model on the same '
           'test patients".'),
    verification=('For each (method, scenario) assert the plotted Δ equals '
                    '`test_acc − baseline_acc_on_var_test` from the pickle, and that '
                    'the paired Δ has the same sign as the stored McNemar direction '
                    '(e.g. `mean`/`min48hr` has `mcnemar=(4.25, 0.0385, n01=25, '
                    'n10=43)`, i.e. the variant is worse on the shared patients, '
                    'which the paired Δ of −0.13 pp reproduces and the unpaired '
                    '−2.70 pp exaggerates).'),
    found='2026-08-11 reporting audit; verified from the pickle',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C11',
        note=('Correction: the `_patch_copy2.py` citation is provenance only — that '
             'file computes the CORRECT paired number (`baseline_acc_on_var_test`); '
             "the defect is entirely in the live notebook's consumption at cells 25 "
             'and 31. Deltas are wrong by roughly 25x.'),
    ),
),
dict(
    id='R-03', stage=REPORT, severity=CRITICAL, status=OPEN, verified=True,
    name=('The impact tuple is unpacked under three wrong names, and there is no '
            'AUC'),
    overview=('What the comparison notebook labels Accuracy, F1 and AUC-ROC are '
                'really CV accuracy, test accuracy and training F1 — and no AUC is '
                'computed anywhere in the pipeline.'),
    affects=('Cell 16\'s summary table columns "F1" and "AUC-ROC" for all five EHR '
               "rows; cell 18's F1 and AUC-ROC panels and the corresponding rows of "
               'the EHR−MIMIC deviation heatmap; cell 28\'s lower panel "EHR Pipeline '
               '— AUC-ROC Across Filter Steps"; cell 29\'s "EHR AUC heatmap"; cell '
               "33's F1 dashboard; and the extracted figures in "
               'figures/Comparison/pipeline_comparison/. With the current '
               '(2026-08-11) pickles the mislabelling is also numerically loud: '
               '`mean` gives "Accuracy" 0.912 (CV) beside a real test accuracy of '
               '0.741, and "AUC-ROC" 0.956 which is a train F1 against a real test '
               'F1 of 0.587.'),
    recompute=('Nothing, for option (a) — positions 1 and 3 are already in every '
                 '`Data/mimic-iii/<agg>/mortality_filter_impact.pkl`; only the '
                 'notebook and figures need regenerating. A real AUC (option b) '
                 'requires re-running stage B for all 13 arms × 5 aggregations × 2 '
                 'labels.'),
    technical=('pipelines/EHR-Dataset-Processing/Managers/evaluation_manager.py:295-'
                 '309 builds the tuple in the order `training_averages` (mean of '
                 '`t[0]`, documented at line 252 as the cross-validation score), '
                 '`testing_averages` (`t[1]`), `training_f1s` (`f1_score(t[5], t[4], '
                 "average='macro')`, i.e. train predictions vs train labels), "
                 '`testing_f1s` (`f1_score(t[3], t[2])`), `mcnemar_results` '
                 '(`calculate_mcnemar_test`, statsmodels `mcnemar(table, '
                 'exact=True)` at line 233-234). The docstring at lines 245-248 '
                 'records that the shape is frozen because the comparison notebook '
                 'uses `_acc, _f1, _auc, _, _mnm`, which is exactly the line at '
                 "pipeline_comparison.ipynb:665; cell 10 then stores it as `{'acc': "
                 "_acc, 'f1': _f1, 'auc': _auc, 'mcnemar': _mnm}`. Loading "
                 '`Data/mimic-iii/mean/mortality_filter_impact.pkl` confirms a '
                 '5-element tuple whose position 2 (~0.93-0.96) is far above '
                 'position 3 (~0.56-0.59), consistent with a '
                 'memorised-training-split F1 and inconsistent with any ROC AUC of '
                 'these accuracies. `evaluate_filter_impact_cv` '
                 '(evaluation_manager.py:617) keeps the same five positions and '
                 'documents them at lines 634-638 as train accuracy / OOF accuracy / '
                 'train macro F1 / OOF macro F1 / paired McNemar — so the CV path '
                 'does not introduce an AUC either; the consumer-side naming is '
                 'unchanged.\n'
                 '\n'
                 'First-pass measurements retained: The tell is in the stored '
                 "output: EHR 'Accuracy' 0.9124 and 'F1' 0.9120 for mean — two "
                 'supposedly different metrics agreeing to four decimals. It is now '
                 "~0.9997, so re-running the notebook would flatten every EHR 'AUC' "
                 'trace to 1.0.'),
    fix=('This is the open human decision recorded in _deprecated/MANIFEST.md §7, '
           'which lists three options: (a) relabel — unpack all five positions with '
           'truthful names, plot position 3 (test macro F1) as F1 and drop the AUC '
           'framing entirely; (b) add a real AUC inside '
           '`evaluate_dataset_label_impact` (which already calls `predict_proba`) '
           'and surface it without growing the 5-tuple, e.g. through the existing '
           '`return_diagnostics` sidecar, then rerun stage B; (c) leave it and '
           'accept ~1.0 "AUC" traces. I am not resolving it here — but note that '
           'under the current pickles option (c) is no longer merely cosmetic, '
           'because the notebook\'s "Accuracy" column is a CV score sitting beside a '
           '"F1" column that is really a held-out accuracy at the Youden threshold, '
           'so two adjacent columns describe different operating points of different '
           'evaluations.'),
    verification=('Whichever option is chosen, assert at load time that the '
                    'unpacked names match the producer, e.g. `cv_acc, test_acc, '
                    'train_f1, test_f1, mcnemar = pickle.load(...)` plus a sanity '
                    'check `train_f1 >= test_f1` and `abs(test_acc - cv_acc) > 0.05` '
                    'for the deviation methods; then confirm no figure title or '
                    'table column in comparison/ contains the string "AUC" while '
                    '`grep -rn "roc_auc" pipelines/EHR-Dataset-Processing/Managers` '
                    'returns nothing.'),
    found='MANIFEST section 7; verified 2026-08-11',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C11',
        note=('Left OPEN deliberately per guardrail 6 (_deprecated/MANIFEST.md §7 is '
             'an open human decision). Mechanism independently re-verified: '
             'discarded position 3 is the only genuine test F1, and no AUC is '
             'computed anywhere in the EHR pipeline. The frozen 5-tuple contract '
             'itself is intentional (guardrail 4) — the defect is consumer-side '
             'naming.'),
    ),
),
dict(
    id='R-04', stage=REPORT, severity=HIGH, status=OPEN, verified=True,
    name='Every published figure still renders from the broken McNemar',
    overview=('`calculate_mcnemar_test` (evaluation_manager.py:202-234) builds its '
                '2x2 table by positionally zipping two consensus prediction vectors '
                'and tabulating prediction-vs-prediction agreement rather than '
                'correctness-vs-truth; for record-dropping arms the two vectors are '
                'different lengths and different patients, so `zip` silently '
                'truncates to the shorter one. The paired, truth-based replacement '
                '`calculate_mcnemar_paired` exists and its output is on disk as '
                '`<label>_filter_impact_cv.pkl`, but no renderer can read it: both '
                '`render_paper_figures.py` and `gallery/render_marimo_mimic_iii.py` '
                'hardcode the legacy filename with no suffix option. The published '
                '`paper_figures/mcnemar_icu_mean.pdf` therefore reports p-values '
                'from a test that is invalid for exactly the arms the paper is about.'),
    affects=('`paper_figures/mcnemar_icu_mean.pdf` (Aug 10 22:14) — all 12 '
               'annotated p-values, and 6 of 12 significance calls at α=0.05 flip '
               'against the corrected CV pickle for ICU/mean: diastolic BP '
               '0.337→3.6e-03, oxygen saturation 0.738→1.0e-15, fill missing data '
               '0.070→9.7e-11, long missing segment 0.799→4.0e-10, long gap '
               '0.290→9.2e-19 (all ns→significant), and `high invalid data` '
               '5.1e-05→0.964 (significant→ns). Also affects every gallery McNemar '
               'figure (`mcnemar_{label}_{agg}` for both labels and all '
               'aggregations, render_marimo_mimic_iii.py:371-374). The four '
               '`filter_impact_*_testing_{accuracy,f1}_mean.pdf` come from the same '
               'legacy pickle but plot accuracy/F1, not p-values, so they are '
               "legacy-design (guardrail 3) rather than McNemar-broken — the claim's "
               '"every published figure" is an overstatement.'),
    recompute=('`Experiments/render_paper_figures.py` (`fig_mcnemar_icu`, and '
                 '`fig_filter_impact` if the whole reporting stage is moved to the '
                 'CV design) and the gallery impact section. The underlying CV '
                 'pickles already exist for `mean` and `maximum deviation`; other '
                 'aggregations would need `rerun/job_f_filter_impact_cv.sh` first. '
                 'No model retraining is required for mean/maximum deviation.'),
    technical=('The legacy path is reached because `render_paper_figures.py:315` '
                 'and `:386` interpolate no suffix (`f"{label}_filter_impact.pkl"`), '
                 "and neither renderer exposes any switch — the gallery's only CLI "
                 'argument is `--section` (render_marimo_mimic_iii.py:629-632). The '
                 "defect in that pickle's fifth element originates at "
                 'evaluation_manager.py:305 (`stat, p_val = '
                 'calculate_mcnemar_test(baseline_preds, current_preds)`), whose '
                 "table (lines 229-233) is indexed by the two arms' predictions, and "
                 'whose `zip` truncates. Legacy diagnostics confirm the arms are '
                 'unequal: `Data/mimic-iii/mean/icu_filter_impact_diagnostics.json` '
                 'gives `n_test` 4604 for raw but 138 (`high invalid data`), 2033 '
                 '(`long gap`), 3104 (`long missing segment`), so those three arms '
                 'are compared over 138/2033/3104 positionally-misaligned pairs; the '
                 "legacy pickle's statistic of 19.0 for `high invalid data` is "
                 'consistent with a 138-row table, versus `n_paired: 1369` in '
                 '`icu_filter_impact_cv_diagnostics.json`. The corrected function '
                 'aligns on `np.intersect1d` of admission ids and tabulates '
                 '`baseline_correct`/`arm_correct` (evaluation_manager.py:570-606), '
                 'raising instead of truncating on a length mismatch. '
                 '`Data/mimic-iii/mean/icu_filter_impact_cv.pkl` (Aug 11 15:35) '
                 'postdates `icu_filter_impact.pkl` (Aug 10 21:38), which itself '
                 'predates the figure (Aug 10 22:14), so the published PDF does '
                 'reflect the current legacy pickle and not the corrected one.\n'
                 '\n'
                 'First-pass measurements retained: Other reversals in the same '
                 'figure: long gap 0.799 -> 0.000; long missing segment 0.070 -> '
                 '0.000; temperature 0.060 -> 0.005.'),
    fix=('Add an impact-suffix knob to the two renderers (e.g. module-level '
           "`IMPACT_SUFFIX` plus `--impact-suffix {'', '_cv'}` on the gallery CLI) "
           'feeding `f"{label}_filter_impact{IMPACT_SUFFIX}.pkl"` at '
           'render_paper_figures.py:315/386 and render_marimo_mimic_iii.py:319, then '
           're-render the paper McNemar figure with `_cv` and stamp the design into '
           'the caption/manifest description so a legacy and a CV figure can never '
           'be confused. Optionally make `fig_mcnemar_icu` prefer `_cv.pkl` when '
           'present, since only the paired test answers the question the figure '
           'claims to answer.'),
    verification=('Re-run `render_paper_figures.py` with the `_cv` suffix and '
                    'check the regenerated `mcnemar_icu_mean.pdf` bar annotations '
                    'against `icu_filter_impact_cv.pkl[-1][1:]`; specifically that '
                    '`high invalid data` now falls below the p=0.05 line (0.964) '
                    'while `long gap` and `oxygen saturation` rise above the '
                    "p=0.0001 line. Cross-check each bar's p-value against the "
                    '`mcnemar` block (`n_paired`, `n01`, `n10`) in '
                    '`icu_filter_impact_cv_diagnostics.json`, and confirm `n_paired` '
                    'equals 46032 for non-dropping arms and 1369 for `high invalid '
                    'data` rather than 4604/138.'),
    found='2026-08-11 reporting audit; verified from both pickles',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='solo pilot',
        note=("Corrections: 'every published figure' overstated — only "
             'mcnemar_icu_mean.pdf renders p-values; notebook.py:566 has a '
             'documented opt-in switch (not the bug); the genuine gap is that '
             'render_paper_figures.py and the gallery renderer have NO suffix '
             'switch. 6 of 12 significance calls flip against the CV pickle.'),
    ),
),
dict(
    id='R-05', stage=REPORT, severity=HIGH, status=OPEN, verified=True,
    name='Scaler and imputer are fitted on train and test together',
    overview=('`impute_and_scale` returns `(X_scaled, scaler, col_means)` '
                'precisely so a caller can fit on train and transform test, and the '
                "comparison notebook's evaluation loop calls it on the full feature "
                'matrix and throws both fitted objects away (`X_sc, _, _`) before '
                'slicing train/test indices out of the already-transformed array. '
                'Test-set rows therefore contribute to the column means used to fill '
                'their own missing values and to the mean/variance used to '
                "standardise them, so both pipelines' reported accuracies are "
                'optimistically biased and the bias is not guaranteed equal across '
                'arms.'),
    affects=("Every metric produced by cell 16's seed loop — i.e. the "
               'MIMIC_Extract rows of the cell 16 table, the MIMIC series in cell 18 '
               'and cell 33, the McNemar counts in cell 20, and (before the R-01 '
               'override) the EHR series too. The leak is modest in expectation here '
               '(7 dense columns, 0.1-1.6% missing, 27,295 rows, 20% test) but it is '
               'real and it applies to the only genuinely head-to-head numbers left '
               'in the notebook.'),
    recompute=('Re-execute comparison/pipeline_comparison.ipynb and re-extract '
                 'figures/Comparison/pipeline_comparison/. No upstream pipeline '
                 'rerun is needed.'),
    technical=('comparison/pipeline_comparison.ipynb cell 8 (JSON lines ~437-443) '
                 'defines `impute_and_scale` returning '
                 '`scaler.fit_transform(X.values), scaler, col_means`. Cell 16 '
                 '(JSON:985-995) does `sss = StratifiedShuffleSplit(...)`, '
                 '`train_idx, test_idx = next(sss.split(X_mimic, y_arr))`, then for '
                 'each arm `X_sc, _, _ = impute_and_scale(X_raw)` followed by `Xtr, '
                 'Xte = X_sc[train_idx], X_sc[test_idx]` — the scaler is fitted on '
                 'all 27,295 rows, and `col_means` is computed over all rows, before '
                 'the split is applied. The generator that produced this cell '
                 'contains the same code at comparison/_gen_comparison_nb.py:344-349 '
                 '(definition) and :614 (`X_sc, _, _ = impute_and_scale(X_raw)`). '
                 "Cell 22's centroid helper does the same whole-cohort imputation, "
                 'but it is descriptive rather than predictive so it is not a leak. '
                 "Correction to the claim's citations: "
                 'pipelines/MIMIC_Extract/notebooks/_patch_copy2.py does NOT leak — '
                 'its `impute_and_scale` (lines 145-151) is fitted on `X_tr` only '
                 'and the test block is filled with the train `col_means` and '
                 'transformed with the train `scaler` (lines 198-201, repeated for '
                 'variants at 262-265, and the baseline replay at 281-285 reuses the '
                 'stored `base_scaler`/`base_col_means`). The cited range 167-172 in '
                 'that file is the baseline feature-matrix construction, not '
                 'scaling. So the defect is confined to comparison/ (live notebook + '
                 'generator).'),
    fix=('In cell 16, split first and fit second: `X_tr_raw, X_te_raw = '
           'X_raw.iloc[train_idx], X_raw.iloc[test_idx]`; `Xtr, scaler, col_means = '
           'impute_and_scale(X_tr_raw)`; `Xte = '
           'scaler.transform(X_te_raw.replace([np.inf,-np.inf], '
           'np.nan).fillna(col_means).fillna(0.0).values)` — i.e. adopt the pattern '
           'already used in _patch_copy2.py:198-201. Mirror the change in '
           '_gen_comparison_nb.py:614 for provenance, without re-running it (toolbox '
           'README: "Don\'t run it").'),
    verification=("Assert the fitted scaler's `n_samples_seen_` equals "
                    '`len(train_idx)` (not the cohort size) and that `col_means` '
                    'recomputed on the train slice alone matches the values used for '
                    'the test fill; then confirm reported accuracies move by a '
                    'small, non-zero amount relative to the current run for at least '
                    'one aggregation method.'),
    found='2026-08-11, both agents; verified in the notebook',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C11',
        note=('Correction: the `_patch_copy2.py:167-172` citation is wrong; the exact '
             'site is `_gen_comparison_nb.py:344-349` (`X_sc, _, _ = '
             'impute_and_scale(...)` before the train/test slice). Magnitude is '
             'small given dense features; severity stays High because this is the '
             'one remaining honest comparison in the notebook.'),
    ),
),
dict(
    id='R-06', stage=REPORT, severity=HIGH, status=OPEN, verified=True,
    name='The degenerate arm dominates the figure and rescales the axis',
    overview=('`filter_impact_plot` receives only a list of scores and names — '
                'never the per-arm test-set size — so the "high invalid data" arm, '
                'whose held-out set is 138 records against 4,604 for the '
                'non-dropping arms, is drawn as an ordinary bar and, being the '
                'extreme value, defines `set_ylim` via '
                '`min_deviation`/`max_deviation` at '
                'visualization_manager_v2.py:277-284. In the mortality '
                'testing-accuracy figure its deviation is -0.2482 while every other '
                'arm lies in [-0.1062, +0.0456], so the axis spans ~0.44 and the '
                'twelve informative bars are squeezed into roughly a third of it. '
                'Nothing on the figure tells a reader that one bar rests on 3% of '
                'the sample of its neighbours.'),
    affects=('paper_figures/filter_impact_mortality_testing_accuracy_mean.pdf '
               '(axis driven by -0.2482), '
               'filter_impact_mortality_testing_f1_mean.pdf (-0.1089 vs next-largest '
               '-0.0616) and filter_impact_icu_testing_f1_mean.pdf (-0.0888 vs '
               '-0.0504) — all rendered 2026-08-10 22:14 from '
               'Data/mimic-iii/mean/{label}_filter_impact.pkl (2026-08-10 21:38). '
               'Correction to the claim: filter_impact_icu_testing_accuracy_mean.pdf '
               'is NOT affected (high invalid data = -0.0345, extreme is long '
               'missing segment -0.0510), and no figure is compressed "to a flat '
               'line" — measured compression on the worst figure is ~2.9x, not '
               'obliteration. The same defect is live in the notebook path '
               '(Experiments/notebook.py:642, 645, 683, 686).'),
    recompute=('Nothing needs re-fitting — the pickles and diagnostics already '
                 'hold everything required. Only re-run `MPLBACKEND=Agg python '
                 'Experiments/render_paper_figures.py` after the plot change.'),
    technical=('`fig_filter_impact` (render_paper_figures.py:314-331) unpickles '
                 'the 5-tuple and passes `impact[1]`/`impact[3]` straight to '
                 '`filter_impact_plot` (line 319, 322-323, 328-329); it never reads '
                 'the sibling `*_filter_impact_diagnostics.json`, which is the only '
                 'place `n_test` per arm lives (icu/mortality diagnostics line 67: '
                 '138 for "high invalid data" versus 4,604 for full-cohort arms — '
                 'consistent with high_invalid_data_admission_ids.npy holding 1,369 '
                 "ids against raw's 46,032). `filter_impact_plot`'s signature "
                 '(visualization_manager_v2.py:235) has no N argument, so the '
                 'function cannot hatch, grey, footnote or exclude a low-N bar; '
                 '`bar()` at line 258 treats all arms identically and lines 277-284 '
                 'compute the limits from the unweighted min/max of `deviations`. '
                 'Measured from Data/mimic-iii/mean/mortality_filter_impact.pkl: '
                 'baseline test accuracy 0.7410, high invalid data delta -0.2482, '
                 'all other deltas within [-0.1062, +0.0456]; with the 25% margin '
                 'the axis becomes ≈(-0.3216, +0.1190), leaving the second-largest '
                 'bar at 24% of axis height. The arm is documented as legitimately '
                 'tiny (evaluation_manager.py:77 "an aggressive arm like \'high '
                 "invalid data' keeps a small enough fraction of records that its "
                 '10% validation subset can contain no positives at all") but no '
                 'documentation sanctions plotting it at full weight — I found no '
                 'intent statement covering the figure treatment in README.md '
                 '"Things that will bite you", noahNotes.md, or notebook.py markdown.\n'
                 '\n'
                 'First-pass measurements retained: '
                 'visualization_manager_v2.py:277-284 then scales ylim to the '
                 'deviation range +/- 25%, so a +/-0.25 range compresses the other '
                 'eleven bars — which live within +/-0.02 — into a flat line at zero.'),
    fix=('Thread the per-arm `n_test` (already serialised in the diagnostics JSON) '
           'into `filter_impact_plot` and use it: annotate each bar with its N, draw '
           'arms below a size threshold with a distinct hatch/alpha, and compute '
           '`min_deviation`/`max_deviation` from the full-cohort arms only, clipping '
           'any out-of-range low-N bar with a break marker. Minimal alternative: in '
           '`fig_filter_impact`, drop record-dropping arms into a separate panel.'),
    verification=('Re-render and confirm (a) each bar carries its N, (b) the '
                    'mortality-accuracy y-limits are ≈(-0.13, +0.07) i.e. set by '
                    '`long gap`/`fill missing data`, not by `high invalid data`, and '
                    '(c) the ICU-accuracy figure is unchanged, since its extremes '
                    'never came from the degenerate arm.'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C14',
        note=("Correction: the original overview overstates the visual effect ('flat "
             "line') and over-generalises to 'every other bar' and to all four "
             'filter-impact figures. The deeper problem — a 138-record and a '
             '4,604-record test arm sharing one axis — is documented for McNemar '
             '(`evaluation_manager.py:539-546`) but not for these bars.'),
    ),
),
dict(
    id='R-07', stage=REPORT, severity=HIGH, status=OPEN, verified=True,
    name='EHR error bars are exactly zero',
    overview=('Cell 16 of the live comparison notebook replaces the four-seed EHR '
                'metric lists with single-element lists taken from index 0 of the '
                'pre-computed GPU pickles, then formats every row of the summary '
                'table as `mean ± np.std(...)`. For the EHR rows the standard '
                'deviation of a one-element list is 0.0, so the published table '
                'reports `± 0.0000` for accuracy, F1 and AUC-ROC on the EHR side '
                'while the MIMIC side shows genuine seed spread. The number is not a '
                'measurement of anything; it is an artifact of list length.'),
    affects=('The "Matched Classifier Evaluation" markdown table in '
               'comparison/pipeline_comparison.ipynb (cell 16, stored output of '
               'execution 8): all five EHR rows report `± 0.0000` for Accuracy, F1 '
               'and AUC-ROC, inviting the reading that the EHR pipeline is perfectly '
               'reproducible while MIMIC_Extract is noisy (e.g. `0.6748 ± 0.0148` vs '
               '`0.5719 ± 0.0000`). The MIMIC rows are unaffected. The '
               'summary-dashboard bars in cell 33 are no longer affected — `ehr_stds '
               '= None` there already suppresses the whiskers.'),
    recompute=('Re-execute cells 16 onward of comparison/pipeline_comparison.ipynb '
                 '(loads cached pickles only, no GPU). Do not regenerate the '
                 'notebook from _gen_comparison_nb.py — the live notebook is '
                 'hand-patched past it.'),
    technical=('pipeline_comparison.ipynb:1011-1013 (cell 16, source lines 36-39) '
                 "overwrites `EVAL_RESULTS[m]['ehr'][{'acc','f1','auc'}]` with "
                 '`[EHR_FILTER_IMPACT[m][k][0]]` — a one-element list per metric. '
                 'The table builder at pipeline_comparison.ipynb:1025-1027 then '
                 'applies the same `f"{np.mean(...)} ± {np.std(...)}"` template to '
                 'both pipelines, so `np.std` over one element yields exactly 0.0; '
                 'the AUC column uses `np.nanstd`, same result. The identical '
                 'mechanism was recognised and repaired at only one of the two '
                 'consumer sites: cell 33 (pipeline_comparison.ipynb:1823-1825) '
                 'carries the comment "so np.std = 0. Suppress error whiskers '
                 'instead of rendering a misleading zero-width bar" and sets '
                 '`ehr_stds = None`, and cell 18 uses means only. The stored table '
                 'output confirms the defect is live in the artifact, not merely '
                 'latent.\n'
                 '\n'
                 'First-pass measurements retained: Confirmed in the stored output: '
                 'every EHR row reads +/- 0.0000, every MIMIC row +/- 0.0010 to '
                 '0.0171.'),
    fix=('In cell 16, build the EHR row without a spread term — e.g. emit '
           '`f"{value:.4f}"` plus a footnote "single GPU run, no seed spread" for '
           'the EHR rows, or carry the per-seed/per-repeat spread through. The CV '
           'evaluator already exposes real dispersion '
           "(`evaluation_manager.py:506-507` `'f1_macro_std'`, `'accuracy'`/`f1` "
           'per-repeat lists), so the honest fix is to write those into the sidecar '
           'and read them here instead of fabricating a zero.'),
    verification=('Re-run cell 16 and confirm no EHR row prints `± 0.0000`; grep '
                    'the executed notebook for `± 0.0000` and expect zero hits. '
                    "Assert in the cell that `len(EVAL_RESULTS[m]['ehr']['acc']) > "
                    '1` before any `np.std` is applied to it.'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C12',
        note=('Correction: the cited `_gen_comparison_nb.py:760-761` yerr site is '
             'already fixed in the live notebook (`ehr_stds = None`, '
             'pipeline_comparison.ipynb:1825). The surviving rendered instance is '
             'the summary table at pipeline_comparison.ipynb:1026. Severity '
             'suggestion: Medium-High (misleads about reproducibility rather than '
             'corrupting a point estimate).'),
    ),
),
dict(
    id='R-08', stage=REPORT, severity=HIGH, status=OPEN, verified=True,
    name='The observation-count heatmap over-counts and mislabels its axis',
    overview=('The heatmap counts `len()`/`.size` of each hour×vital cell, and for '
                'MIMIC-III those lists still contain rows whose `valuenum` was SQL '
                'NULL because the extraction query filters only on `itemid` and '
                '`error` (mimic-iii-processing.py:55-61), unlike the MIMIC-IV query '
                'which adds `valuenum IS NOT NULL`. The aggregation path strips '
                'those entries before averaging (ehr_filter_manager.py:381), so '
                '"observation density" in the figure is counted on a looser '
                'definition of "measurement" than every downstream number uses. '
                'Separately, hour 0 is hospital admittime '
                '(mimic-iii-processing.py:79), but the gallery captions call the '
                'records "mimic-iii ICU stays".'),
    affects=('The gallery figures `length_{mean,median,std,max,min}_heatmap` / '
               '`_surface` and their captions (render_marimo_mimic_iii.py:275-304, '
               'descriptions at :284 and :288), plus '
               'paper_figures/observation_count_heatmap_raw_mimic_iii.pdf '
               '(render_paper_figures.py:265-293). Cell values are inflated by '
               'however many NULL-valuenum chart events exist per hour/vital; the '
               'axis label misattributes the time origin, which matters most when '
               'the figure is read next to MIMIC_Extract plots, whose hour 0 is ICU '
               'intime (toolbox README.md:7).'),
    recompute=('The heatmap/surface figures only (gallery Section A and paper '
                 'Figure 2) if the fix is at render time. If the fix is made in the '
                 'SQL, `Data/mimic-iii/processed_record_ehr.pkl` and everything '
                 'cached beneath `Data/mimic-iii/<aggregation>/` must be '
                 "regenerated, because mimic-iii-processing.py:212 rmtree's the "
                 'whole dataset directory.'),
    technical=('mimic-iii-processing.py:55-61 selects `ce.valuenum` with `WHERE '
                 'ce.itemid IN (...) AND (ce.error IS NULL OR ce.error = 0)`; there '
                 'is no null-value predicate, whereas mimic-iv-processing.py:48 has '
                 "one. `groupby(['hadm_id','hour','vital'])['valuenum'].agg(list)` "
                 '(mimic-iii-processing.py:107) therefore preserves None entries '
                 'inside the per-hour lists. The counting lambda in both renderers — '
                 'render_marimo_mimic_iii.py:253-255 and '
                 'render_paper_figures.py:275-277, `lambda x: x.size if hasattr(x, '
                 '"size") else (len(x) if isinstance(x, list) else 0)` — counts '
                 'every element, Nones included, while `aggregate()` at '
                 'ehr_filter_manager.py:381 drops `v is not None` before applying '
                 'the summary function. Note also a renderer/notebook divergence: '
                 'notebook.py:274 uses `isinstance(x, np.ndarray)` where both '
                 'renderers use `hasattr(x, "size")`; the latter also matches numpy '
                 '*scalars*, so any numpy-scalar NaN cell would count as one '
                 'observation in the renderers and zero in the notebook. Empty cells '
                 'are `[]` by construction (mimic-iii-processing.py:116 '
                 '`reindex(..., fill_value=[])`), and the published artifact '
                 'supports that the bulk of missing cells are not counted: pdftotext '
                 'of paper_figures/observation_count_heatmap_raw_mimic_iii.pdf gives '
                 'temperature ≈0.20-0.32 per hour against heart rate ≈0.74-1.13, '
                 'i.e. missing temperature hours are contributing 0, not 1. For the '
                 'axis: mimic-iii-processing.py:71-74 states "Hours are measured '
                 'from hospital admission, not ICU admission", records are keyed on '
                 '`hadm_id`, and ICU membership is only a label (get_icu_labels, '
                 ':126-163) — yet render_marimo_mimic_iii.py:284/:288 caption the '
                 'cohort as "ICU stays", and REPO/README.md:35 says "the first 24 '
                 'hours of each ICU stay" while README.md:39 admits the MIMIC '
                 'scripts key on hospital admission.'),
    fix=('Add `AND ce.valuenum IS NOT NULL` to the MIMIC-III query '
           '(mimic-iii-processing.py:59-60) to match MIMIC-IV, or — to avoid a full '
           're-extract — make the count lambda skip nulls, e.g. `sum(1 for v in x if '
           'v is not None and v == v)`, in render_marimo_mimic_iii.py:253-255, '
           'render_paper_figures.py:275-277 and notebook.py:274 (and align all three '
           'on one predicate). Change the captions at '
           'render_marimo_mimic_iii.py:284/:288 to "hospital admissions, hours since '
           'admittime" and fix REPO/README.md:35; label the paper figure\'s y-axis '
           '"Hour since hospital admission".'),
    verification=('Re-render Section A and diff cell values against '
                    'paper_figures/observation_count_heatmap_raw_mimic_iii.pdf — any '
                    'cell that drops proves NULL entries were being counted, and if '
                    'nothing drops the count defect is nil for this cache. '
                    'Independently, `SELECT count(*) FROM chartevents WHERE itemid '
                    'IN (<vital ids>) AND (error IS NULL OR error=0) AND valuenum IS '
                    'NULL;` quantifies the inflation directly. For the caption, '
                    'confirm no `icustays` join exists in the record-construction '
                    'path.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C15',
        note=('Corrections: null-valued chart *elements* are counted, but absent '
             "cells are not (`[]` -> 0), so 'counts NULL entries as observations' "
             'needs that narrowing; the axis is a hospital-admission clock captioned '
             'as an ICU clock. Over-count magnitude is UNMEASURED — the login node '
             'has no pandas/numpy/pyarrow, so '
             '`Data/mimic-iii/processed_record_ehr.pkl` could not be opened. '
             'Severity suggestion: Medium.'),
    ),
),
dict(
    id='R-09', stage=REPORT, severity=HIGH, status=OPEN, verified=True,
    name=("'standard deviation' means a different statistic on each side of the "
            'comparison'),
    overview=('One side takes the spread across 24 hourly means; the other takes '
                'the spread within each hour. Different axis, different feature '
                'count, presented as the same row.'),
    affects=('Every "standard deviation" (and, by the same argument, "mean '
               'deviation" / "maximum deviation") entry in '
               'comparison/pipeline_comparison.ipynb: the summary table rows in cell '
               '16, the three bar panels and the EHR−MIMIC deviation heatmap in cell '
               '18, the centroid-shift figures in cell 22, and the summary dashboard '
               'in cell 33. The `mean` and `median` rows are far less affected (a '
               'mean of hourly means differs from a pooled mean only by per-hour '
               'count weighting), which makes the deviation rows the ones that '
               'cannot be read as pipeline effects at all.'),
    recompute=('Nothing can be salvaged by re-running as-is. Either re-run the EHR '
                 "filter-impact sweep with an aggregator matching the notebook's "
                 "axis, or re-run the notebook's MIMIC side with per-cell "
                 'aggregation followed by a 168-feature flatten. Then re-execute the '
                 'comparison notebook from cell 12 onward.'),
    technical=('EHR path: `ehr_filter_manager.aggregate` (line 338) builds '
                 '`new_dataframe` of shape 24x7 and, per cell, applies `func = '
                 'ops.get(method, np.mean)` (line 368) to `numeric_values`, i.e. the '
                 'measurements recorded in that single hour — `"standard deviation": '
                 'np.std` at line 364, `np.std` default ddof=0. '
                 '`dataset_manager.flatten_subset_to_cupy` (line 169-186) then '
                 'flattens each 24x7 matrix to a 168-vector for cuML, and '
                 '`evaluation_manager.evaluate_filter_impact` scores that '
                 '168-feature model; those scores are what the notebook injects at '
                 'pipeline_comparison.ipynb:1011-1013. Notebook/MIMIC path: '
                 '`ehr_record_to_hourly_matrix` / `mimic_record_to_hourly_matrix` '
                 '(cell 8) reduce each hour to a mean, then '
                 "`aggregate_hourly_matrix(..., 'standard deviation')` returns "
                 '`matrix_24x7.std(axis=0, ddof=1)` — 7 features, spread across '
                 'hours, sample ddof; cell 12 line 86 confirms the vectorised MIMIC '
                 'equivalent `X_agg = _grp.std(ddof=1)`. So the two sides differ in '
                 'reduction axis, in ddof, and in feature count. Documented intent '
                 "supports the EHR reading, not the notebook's: "
                 '/home/ccampb47/work/noahNotes.md:357 describes aggregation as the '
                 'step that flattens the "24 x 7 x N" cube by collapsing N. The '
                 '`aggregate` docstring at ehr_filter_manager.py:350-354 '
                 'acknowledges only the ddof half of the mismatch and calls that '
                 'alone "not quite apples-to-apples", so the documentation is aware '
                 'of the smaller discrepancy and silent about the larger one.'),
    fix=('Pick one definition and make both sides use it. Cheapest correct option: '
           'in the notebook, replace `aggregate_hourly_matrix` with a per-cell '
           'aggregation mirroring `ehr_filter_manager.aggregate` (including `np.std` '
           'ddof=0) and feed the resulting 24x7 flattened 168-vector to the '
           'classifier, so both pipelines answer the same question. Until then, '
           'rename the notebook\'s rows (e.g. "std across hours (7 feat.)" vs "std '
           'within hour (168 feat.)") so the table stops implying a like-for-like '
           'comparison.'),
    verification=('On a handful of shared `hadm_id`s, compute both definitions and '
                    'assert the feature-vector lengths and values now agree between '
                    'the notebook path and `ehr_filter_manager.aggregate` + '
                    '`flatten_subset_to_cupy`. A useful sanity check: after the fix '
                    'the `mean` row should shift only slightly while the `standard '
                    'deviation` row shifts substantially — if the std row does not '
                    'move, the fix did not take.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C12',
        note=('Cited `ehr_filter_manager.py:363` has drifted one line — the operative '
             "line is 364. The two 'standard deviation' statistics differ in "
             'reduction axis, feature count (168 within-hour vs 7 across-hour) and '
             'ddof.'),
    ),
),
dict(
    id='R-10', stage=REPORT, severity=HIGH, status=OPEN, verified=True,
    name='250 uncorrected significance tests, and a caption claiming otherwise',
    overview=('Every McNemar p-value in the project is compared against a bare '
                'α=0.05 with no family-wise or FDR adjustment anywhere in the '
                'toolbox; a repo-wide grep for '
                '`bonferroni|holm|fdr_bh|multipletests|benjamini|p_adjust` returns '
                'nothing outside the audit register. Across the EHR marimo notebook '
                '(2 labels × 5 aggregations × 12 filters = 120), the MIMIC_Extract '
                "marimo notebook (2 × 5 × 12 = 120) and the comparison notebook's "
                'pooled panel (5), 245 distinct tests are reported at that '
                'threshold, so roughly a dozen "significant" bars are expected from '
                'noise alone. The notebook generator additionally asserts that '
                'pooling across seeds "avoids ... the multiple-comparisons problem", '
                'which conflates within-seed replication with the across-arm '
                'multiplicity that actually exists.'),
    affects=('Every orange bar and every `p < 0.05` claim in the EHR McNemar '
               'charts (`Experiments/notebook.py` cells at lines 648 and 689), the '
               'MIMIC_Extract McNemar charts, `paper_figures/mcnemar_icu_mean.pdf`, '
               'and `comparison/pipeline_comparison.ipynb` cells 20 and 26. Any '
               'sentence of the form "filter X significantly changed the classifier" '
               'inherits an uncontrolled false-discovery rate. The '
               '`_gen_comparison_nb.py` caption is wrong on the statistics and would '
               'be re-emitted into the live notebook on any regeneration.'),
    recompute=('Nothing needs recomputing — the p-values themselves are valid. '
                 'Only the thresholds/colour rules and captions change, so the plots '
                 'must be re-rendered (`Experiments/render_paper_figures.py`, the '
                 'two marimo notebooks, and a re-execution of '
                 '`pipeline_comparison.ipynb` cells 20/26).'),
    technical=('`visualization_manager_v2.mcnemar_plot` hard-codes `threshold = '
                 "0.05` (line 342) and colours bars with `colors = ['#f39c12' if p < "
                 "0.05 else '#a0a0a0' for p in p_values]` (line 339); "
                 '`render_paper_figures.paper_mcnemar_plot` hard-codes `t1, t2 = '
                 '0.05, 0.0001` (line 345); '
                 '`mimic_extract_analysis.visualize_mcnemar_significance` repeats '
                 "the same `p < 0.05` rule (line 547); the comparison notebook's "
                 '`visualize_mcnemar_significance` repeats it again '
                 '(pipeline_comparison.ipynb:260). Call-site multiplicities: '
                 '`Experiments/notebook.py:648` and `:689` each plot `[x[1] for x in '
                 '...[-1]][1:]` — 12 p-values, once per aggregation method '
                 "(`AGGREGATION_METHODS`, 5, line 192) per label (`LABELS = ['icu', "
                 "'mortality']`, line 525) = 120; "
                 '`mimic_extract_analysis.py:964-968` loops `LABELS` (2, line 104) × '
                 '`AGG_METHODS` (5, line 100) over 12 `SCENARIOS` (line 93-98) = '
                 '120; `pipeline_comparison.ipynb` cell 20 adds 5. '
                 '`pipeline_comparison.ipynb` cell 26 and '
                 '`render_paper_figures.fig_mcnemar_icu` re-display subsets of '
                 'those, taking the number of *displayed* p-values above 300. Two '
                 'in-repo comments do acknowledge the problem partially — '
                 '`visualization_manager_v2.py:323-325` and '
                 '`Experiments/notebook.py:516-518` ("with 11 filters on an '
                 'uncorrected p=0.05 threshold you should expect roughly one '
                 'spurious significant result per chart") — but both undercount the '
                 'filters (12, not 11, per `FILTERS` at '
                 '`Experiments/notebook.py:522-535`) and both scope the warning to a '
                 'single chart rather than the 245-test family. The generator '
                 'caption at `_gen_comparison_nb.py:673-675` contradicts them '
                 'outright.\n'
                 '\n'
                 'First-pass measurements retained: The toolbox runs 12 filter arms '
                 'x 5 aggregations x 2 labels = 120 McNemar tests; the MIMIC_Extract '
                 'side runs 13 variants x 5 x 2 = 130 more. grep for '
                 'bonferroni|multipletests|fdr_bh|holm across the whole tree returns '
                 'nothing. A Bonferroni threshold would be 4.17e-04.'),
    fix=('Compute adjusted p-values once per declared family (e.g. '
           "`statsmodels.stats.multitest.multipletests(..., method='holm')` over the "
           '12 arms within a (label, aggregation) chart, and separately over the 5 '
           'aggregation methods in the comparison panel), colour bars by the '
           'adjusted value, and draw the adjusted threshold line alongside the '
           'nominal one. Delete the "avoids ... the multiple-comparisons problem" '
           'clause from `_gen_comparison_nb.py:673-675` and replace it with the '
           'correct statement (pooling removes *seed* multiplicity only), and '
           'correct "11 filters" to 12 in `visualization_manager_v2.py:324` and '
           '`Experiments/notebook.py:516`.'),
    verification=('Re-render one McNemar chart and check that the printed '
                    'annotation shows both raw and adjusted p, that the bar count '
                    'matches `len(FILTERS)` = 12, and that the number of orange bars '
                    'drops for at least one (label, aggregation) pair whose raw p '
                    'sits in (0.05/12, 0.05). Grep the regenerated notebook markdown '
                    'to confirm the false claim is gone.'),
    found='2026-08-11; counts verified directly',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C13',
        note=('Corrections: (a) the family is 245 unique tests, not 250 — 120 EHR + '
             '120 MIMIC_Extract + 5 comparison, counted from the three loop nests; '
             '(b) the misleading caption exists only in `_gen_comparison_nb.py:674` '
             'and is NOT currently rendered (the live notebook markdown says merely '
             "'Discordant counts pooled across 4 seeds'), so it is a latent "
             "regression that returns on regeneration; (c) 'nothing in the repo "
             "mentions multiplicity' is too strong — "
             '`visualization_manager_v2.py:323-325` and '
             '`Experiments/notebook.py:516-518` both flag the threshold as '
             'uncorrected.'),
    ),
),
dict(
    id='R-11', stage=REPORT, severity=HIGH, status=OPEN, verified=True,
    name='Seven units share one axis, with a significance band that can never fire',
    overview=('Degrees Celsius, mmHg, bpm and percent are plotted on one linear '
                "scale, and the grey 'no change' band is borrowed from accuracy "
                'plots where 0.001 is a sensible floor.'),
    affects=('`paper_figures/centroid_deviation_all_vitals_filter_mean.pdf` and '
               '`paper_figures/centroid_deviation_high_invalid_data_filter_mean.pdf` '
               '(both 2026-08-10 22:14), and the equivalent accordion panels in the '
               'EHR marimo notebook for all 5 aggregations × 13 arms. In the '
               'published all-vitals figure the axis spans roughly −32 to +0.5, so '
               'the temperature and oxygen-saturation groups (|Δ| ≈ 0.012–0.11) '
               'render as flat lines while the annotation still reports four '
               'decimals — the reader cannot see which vitals moved. No colour in '
               'either figure is grey, so "the filter did not meaningfully move this '
               'vital" is a statement the plot is structurally unable to make.'),
    recompute=('Nothing — the centroid pickles under '
                 '`Data/<dataset>/mean/centroids/` are unaffected. Only '
                 '`Experiments/render_paper_figures.py` (`fig_centroid_deviation`) '
                 'needs re-running to regenerate the two PDFs.'),
    technical=('`centroid_shift_plot` (`visualization_manager_v2.py:379-454`) '
                 'computes `deviations = scores - baseline` (line 408) in the '
                 "vitals' native units, colours with `colors = [green_base if dev > "
                 'epsilon else red_base if dev < -epsilon else gray_base for dev in '
                 'deviations]` (line 413) using the default `epsilon = 1e-3` (line '
                 "379), and labels the axis `axes.set_ylabel('Deviation From "
                 "Baseline')` (line 444) — no unit string, no normalisation, no "
                 'per-vital subplot, and no `twinx`/faceting. The caller '
                 '`render_paper_figures.fig_centroid_deviation` (lines 299-308) '
                 'passes `VITAL_NAMES` derived from `VITALS` (lines 81-87), whose '
                 'units are bpm, mmHg×3, breaths/min, C and % — a '
                 '~4-order-of-magnitude spread in plausible shift size. `pdftotext '
                 '-layout` on the published '
                 '`centroid_deviation_all_vitals_filter_mean.pdf` recovers the bar '
                 'annotations, whose extremes are `-32.2025` and `-13.3771` '
                 'alongside `+0.0119`, `+0.0138`, `+0.0194` and `+0.0274`: the '
                 'minimum |deviation| actually plotted is 0.0119, i.e. an order of '
                 'magnitude above `epsilon`, confirming the grey branch is '
                 'unreachable in practice. Documented intent does not cover this: '
                 '`/home/ccampb47/work/noahNotes.md:456` introduces the 1e-3 grey '
                 'threshold only for the *filter-impact delta* bar chart ("Grey bars '
                 'indicate that there was no meaningful change according to a set '
                 'threshold of 1e-3"), while the centroid-plot section '
                 '(`noahNotes.md:474`) describes the baseline-comparison plot with '
                 'no threshold at all. The live comparison notebook already solved '
                 'the same problem a different way — `visualize_centroid_shift_v2` '
                 'gained a `relative` flag that converts to percent and rescales the '
                 'band (`pipeline_comparison.ipynb:297-306`, called with `relative = '
                 'True` at cell 22) — which '
                 '`visualization_manager_v2.centroid_shift_plot` never received.\n'
                 '\n'
                 'First-pass measurements retained: '
                 "visualization_manager_v2.py:379-454 labels the axis 'Deviation "
                 "From Baseline' across heart rate (~85 bpm), three pressures "
                 '(~120/60/80 mmHg), respiration (~18/min), temperature (~37 C) and '
                 'SpO2 (~97%). A clinically large 1.5 C shift is a tenth the height '
                 'of a trivial 15 mmHg one.'),
    fix=('Either (a) facet — one small subplot per vital with its own y-axis and '
           'unit label, reusing the 2×4 grid pattern from `centroid_plot`; or (b) '
           "port the comparison notebook's `relative=True` mode into "
           '`centroid_shift_plot` so deviations become percent-of-baseline with a '
           'percentage-scaled epsilon; and in both cases replace the scalar '
           "`epsilon` with a per-vital tolerance (a fraction of that vital's "
           'baseline, or of its cohort SD) so the grey category is meaningful. Add '
           'the unit to the axis or panel label.'),
    verification=('Re-render `centroid_deviation_all_vitals_filter_mean.pdf` and '
                    "confirm (i) each vital's bars occupy a visible fraction of "
                    'their own panel/axis, (ii) at least one arm/vital pair now '
                    'renders grey (check against the per-vital tolerance you chose), '
                    'and (iii) `pdftotext` shows a unit string on every y-axis '
                    'label. A cheap regression guard: assert that '
                    '`centroid_shift_plot` raises if handed vitals with '
                    'heterogeneous units and no `relative`/facet flag.'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C13',
        note=('`noahNotes.md:456` scopes the 1e-3 grey band to the accuracy-delta '
             'chart, and the docstring at `visualization_manager_v2.py:387-388` '
             "frames the reuse as a carried-over 'convention' — per guardrail 10 "
             "that is the bug, not a justification. The comparison notebook's "
             '`relative=True` path shows the units problem was already recognised '
             'elsewhere in the toolbox.'),
    ),
),
dict(
    id='R-12', stage=REPORT, severity=HIGH, status=OPEN, verified=True,
    name=('The McNemar panel tests a different model pair and pools overlapping '
            'test sets'),
    overview=('It reads the predictions the override left untouched, so it '
                'compares two logistic regressions while every other panel reports a '
                'random forest.'),
    affects=("`pipeline_comparison.ipynb` cell 20's printed table (`n01`/`n10`/`p` "
               'for all 5 aggregation methods, e.g. `mean n01=21 n10=92 p=0.0000`) '
               'and the McNemar bar figure it renders, plus the markdown at '
               '`pipeline_comparison.ipynb:1144` that frames it as testing "the two '
               'pipelines". Four of five methods are reported as p≈0.0000; those '
               'p-values describe neither the reported EHR model nor an independent '
               'sample. The two defects push in the same direction for reporting '
               'purposes: the wrong-model substitution makes the comparison one '
               'between two models nobody reports, and the pooling makes whatever '
               'difference exists look more significant than the data support. The '
               'summary tables in cells 16 and 33 are *not* affected — they read the '
               'overridden `acc`/`f1`/`auc`.'),
    recompute=('`pipeline_comparison.ipynb` cells 16 and 20 must be re-executed '
                 'after the fix (cell 16 to persist RF predictions or to make the '
                 'mismatch fail loudly, cell 20 to recompute the tests). If the fix '
                 'keeps pooling, nothing upstream changes; if the EHR arm switches '
                 'to the GPU RandomForest predictions, those per-record predictions '
                 'must be exported from the EHR pipeline first — '
                 '`Data/<dataset>/<agg>/*_oof_scores_cv.npz` already carries '
                 '`*__consensus_predictions` and `*__admission_ids`, which is the '
                 'natural source.'),
    technical=('In cell 16 the per-seed loop (`pipeline_comparison.ipynb` cell 16) '
                 'fits `LogisticRegression(**MODEL_KWARGS)` separately on `X_mimic` '
                 'and `X_ehr` and appends `pred`, `prob`, `yte` into '
                 '`res_m`/`res_e`. The override block that follows (JSON lines '
                 '1008-1017) reassigns exactly three keys per method — '
                 "`EVAL_RESULTS[_method]['ehr']['acc']`, `['f1']`, `['auc']` — from "
                 '`EHR_FILTER_IMPACT[_method][...][0]`, i.e. index 0 (the '
                 'raw/no-filter arm) of the cuML RandomForest pickles loaded at cell '
                 "10 from `EHR_DATA_ROOT / _m / 'mortality_filter_impact.pkl'`. "
                 '`preds` and `y_test_list` are left untouched, and its own comment '
                 'concedes the reason for the override ("The in-notebook EHR feature '
                 'extractor produces NaN; the filter_impact.pkl files contain the '
                 'real cuML RandomForest results"), so the notebook knowingly '
                 'distrusts the LR-on-EHR arm for scoring while still using it for '
                 'inference. Cell 20 then reads `pred_e = '
                 "ehr_res['preds'][seed_idx]` — the LR predictions — and `pred_m = "
                 "mimic_res['preds'][seed_idx]`. That the override took effect is "
                 'visible in the stored output of cell 16: every EHR row reports `± '
                 '0.0000` (a one-element list), while the MIMIC rows retain 4-seed '
                 'spread. Independence: `SEEDS = [22, 985, 439, 81]` with `TEST_SIZE '
                 '= 0.2` and `n_splits=1` per seed means four *separate* random 20% '
                 'draws, not a partition; with 27,295 shared records (cell 12 '
                 'output) each pair of seeds shares ≈0.04·N ≈ 1,090 patients in '
                 'expectation, and `total_n01`/`total_n10` accumulate over all four '
                 'without any per-patient deduplication or cluster adjustment before '
                 '`mcnemar_pooled(total_n01, total_n10)` computes '
                 '`binom.cdf(min(n01, n10), n, 0.5)` on the summed counts. The '
                 '`mcnemar_counts` helper itself is correct (it scores both models '
                 'against truth), so the defect is entirely in what is fed to it and '
                 'how the counts are combined.'),
    fix=('(1) Make the override total or explicit — either also replace '
           '`preds`/`y_test_list` with the GPU RandomForest per-record predictions '
           'aligned on `admission_id` (available in `*_oof_scores_cv.npz`), or '
           'delete `preds`/`y_test_list` in the override block so cell 20 raises '
           '`KeyError` instead of quietly testing the wrong pair; add an assertion '
           'that the arm whose accuracy is reported is the arm whose predictions are '
           'tested. (2) Replace count-summing with a design that respects '
           'independence: either run McNemar on a single fixed split and report the '
           'other seeds as a sensitivity check, or use disjoint folds (a '
           '`StratifiedKFold` partition) so each patient appears in exactly one test '
           'set, or keep the four overlapping draws and combine per-seed p-values '
           'with a method that tolerates dependence. (3) Update the markdown at line '
           '1144 to name the models actually being compared.'),
    verification=("After the fix, assert `len(EVAL_RESULTS[m]['ehr']['preds']) == "
                    "len(EVAL_RESULTS[m]['ehr']['acc'])` and that the EHR arm's "
                    'accuracy recomputed from `preds`/`y_test_list` reproduces the '
                    'reported `acc` to within rounding — under the current code that '
                    'check fails (LR accuracy vs 0.9124 RF accuracy). For the '
                    'pooling fix, verify `sum(n01) + sum(n10)` is computed over a '
                    'number of patients no larger than the cohort, and confirm the '
                    'p-values move (the current `p=0.0000` entries should soften '
                    'once each patient is counted once).'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C13',
        note=("Guardrail 4's frozen 5-tuple is what forces the positional read of the "
             'pickle, but it does not require leaving `preds` stale — the '
             'un-overridden predictions are an independent oversight in the override '
             'block, not a consequence of the contract.'),
    ),
),
dict(
    id='R-13', stage=REPORT, severity=HIGH, status=OPEN, verified=True,
    name='Sibling significance heatmaps autoscale independently',
    overview=('Ten heatmaps rendered without a shared colour scale, so one whose '
                'largest value is p=0.04 looks identical to one whose largest is '
                'p=1e-300.'),
    affects=('The 10 "McNemar Significance Heatmap — {LABEL} / {AGG}" figures '
               'catalogued at extract_notebook_graphs.py:105-113 (category "McNemar '
               'Significance", plot_type "heatmap") and their in-notebook outputs in '
               'curated_mimic_iii_analysis_executed copy 2.ipynb cell 14. Only the '
               'colour encoding is wrong; the underlying p-values and the printed '
               'tables from `show_results` are unaffected.'),
    recompute=("Nothing numerically. Re-execute cell 14's plotting loop (or re-run "
                 "the notebook's display step) and re-run "
                 'gallery/extract_notebook_graphs.py to re-harvest the images.'),
    technical=('In the live notebook cell 14 (identical to the MCNEMAR_SRC block '
                 'in _patch_copy2.py:354-375), the p-values are turned into '
                 '`-np.log10(max(fp, 1e-300))` (_patch_copy2.py:367), so the '
                 'possible value range spans 0 to 300 across figures; the frame is '
                 'one row wide, `pd.DataFrame([vals], columns=filter_names, '
                 "index=['-log10(p)'])`. `sns.heatmap` is then called with only "
                 "`cmap='magma'` — no `vmin`, `vmax`, or `norm` — so matplotlib's "
                 'default `Normalize` autoscales per figure. The driver at the end '
                 'of the cell iterates `AGG_METHODS` (5 methods, defined cell 3) × '
                 "`LABELS` (`['icu_los','mortality']`, cell 3), producing 10 "
                 'independently scaled figures, and each gets its own colorbar whose '
                 'ticks are the only clue to the scale. The gallery then indexes all '
                 'ten under one category (extract_notebook_graphs.py:110) so they '
                 'are browsed adjacently. The `raw` baseline column is NaN by '
                 'construction (_patch_copy2.py:358-359), which additionally leaves '
                 'a blank first cell in every row.\n'
                 '\n'
                 'First-pass measurements retained: _patch_copy2.py:344-361 calls '
                 'sns.heatmap with no vmin/vmax, no annot=True, and no p=0.05 '
                 'reference.'),
    fix=('Compute all ten value rows first, then render with a shared '
           'normalisation — pass `vmin=0, vmax=<global max>` (or a fixed `vmax` such '
           'as 20 with `norm=matplotlib.colors.Normalize(0, 20)`) into `sns.heatmap` '
           "in cell 14's `visualize_mcnemar_significance`, and mirror the change in "
           '_patch_copy2.py:372 so the patcher stays a faithful record. Annotating '
           "the cells (`annot=True, fmt='.1f'`) would make the figures readable even "
           'if the scale changes again.'),
    verification=('Re-render and confirm the colorbar limits are identical across '
                    'all ten images, and that a cell known to be p≈0.04 is visibly '
                    'darker than one at p≈1e-300; cross-check the annotated numbers '
                    'against the `McNemar (Stat, p, n01, n10)` column printed by '
                    '`show_results` for the same (label, aggregation).'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C15',
        note=('Cited `_patch_copy2.py:344-361` is off by ~10 lines; the offending '
             'call is :370-373 inside `visualize_mcnemar_significance` (:354-375). '
             'Verified in the live notebook cell as well as in the patcher, so '
             "guardrail 8's provenance caveat does not downgrade it. "
             '`extract_notebook_graphs.py:109-111` is metadata only — evidence the '
             'ten figures are published as a comparable set, not the cause.'),
    ),
),
dict(
    id='R-14', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name='A chi-square statistic is reported beside an exact binomial p-value',
    overview=('The printed statistic and the printed p-value come from two '
                'different tests.'),
    affects=('The "McNemar (Stat, p, n01, n10)" column of the per-variant tables '
               'in the live notebook '
               'pipelines/MIMIC_Extract/notebooks/curated_mimic_iii_analysis_executed '
               'copy 2.ipynb (cell `12a0e285`), and element 0 of the `mcnemar` '
               'tuples stored in '
               'data/scenario_analysis/<agg>/mortality_scenario_impact.pkl (e.g. '
               '`mean`/`min48hr` → `(4.25, 0.0385, 25, 43)`, where chi2=4.25 gives '
               'p≈0.039 only coincidentally close to the exact 0.0385, while '
               '`age35_range5` → `(0.0, 1.0, 4, 3)` where chi2 = 0 is the '
               'corrected-statistic floor rather than a real result). No *decision* '
               'in the live comparison notebook is affected, because cell 20 '
               'discards the statistic (`_, p = mcnemar_pooled(...)`, JSON:~1315) '
               'and cell 26 reads only `mnm[1]` (JSON:1528).'),
    recompute=('Nothing numerically required if the statistic is simply relabelled '
                 'or dropped — the p-values already published are the exact binomial '
                 'ones and remain valid. If the statistic is changed, only the '
                 "display cells / a re-execution of the curated notebook's table are "
                 'needed.'),
    technical=('notebooks/_patch_copy2.py:125-142 defines `mcnemar_pooled`; its '
                 'own docstring (lines 128-131) says it "Uses the '
                 'continuity-corrected statistic and an exact two-sided binomial '
                 'p-value", so the mismatch is explicit but the two are still '
                 'reported as one test result. Line 296 packs them as `mcnemar_entry '
                 "= (stat_pool, p_pool, n01_total, n10_total)` into every variant's "
                 'results dict (line 313), which is what gets pickled to '
                 'data/scenario_analysis/. `show_results` (line 333) renders both in '
                 'one string; that patched source is live in '
                 'curated_mimic_iii_analysis_executed copy 2.ipynb cell `12a0e285` '
                 '(per _deprecated/MANIFEST.md §3, "Despite the name, `copy 2` is '
                 'the live one"). The same helper was copied into the comparison '
                 'notebook via _gen_comparison_nb.py:357-363 → '
                 'pipeline_comparison.ipynb:458-459, where the statistic is computed '
                 'and then discarded. Note the EHR pipeline does this correctly: '
                 'Managers/evaluation_manager.py:233-234 uses `mcnemar(table, '
                 'exact=True)` and returns `result.statistic, result.pvalue` from '
                 'the same test object.'),
    fix=('Report one test. Either (a) drop `stat` from the return value and the '
           "display and report only `p`, `n01`, `n10` (the exact test's natural "
           'statistic is `min(n01,n10)`), or (b) keep the chi-square statistic and '
           'pair it with `1 - chi2.cdf(stat, 1)`. Option (a) preserves the published '
           'p-values; option (b) would change them for small discordant counts, '
           'which is exactly the regime the docstring says the approximation '
           'misbehaves in.'),
    verification=('For a set of (n01,n10) pairs including small ones (e.g. (4,3), '
                    '(25,43), (806, ...)), assert the reported p equals the p '
                    'implied by the reported statistic under the reported test to '
                    'within floating point — currently this assertion fails for '
                    '(4,3) (stat 0.0 → chi2 p = 1.0 vs exact p = 1.0 passes by luck, '
                    'but (2,8) gives stat 2.5 → chi2 p = 0.114 vs exact p = 0.109). '
                    'Cross-check against '
                    '`statsmodels.stats.contingency_tables.mcnemar` with matching '
                    '`exact=`.'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C11',
        note=('Severity suggestion: Low-Medium. The p-values that drive every '
             'conclusion and heatmap are the exact binomial ones and are correct; '
             'the chi-square/exact mismatch is a reporting inconsistency in one '
             'displayed column and never changes a significance call.'),
    ),
),
dict(
    id='R-15', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name='The ECDF is normalised after clipping, and clipped per curve',
    overview=('It reaches 1.0 at the 95th percentile of an already-truncated '
                'subset, and each of the four curves in a panel is normalised over a '
                'different subset.'),
    affects=('paper_figures/ecdf_fill_missing_data_mean_4x2.pdf and '
               'paper_figures/ecdf_fill_missing_data_mean_2x4.pdf (both 2026-08-10 '
               '22:14). Measured on the heart-rate panel (mean agg, vital index 0): '
               'the ICU+ curve is clipped to [62.4, 183.2] and loses ~861 of 17,251 '
               'points almost entirely from the *lower* tail, so it starts at y≈0 '
               'where the true CDF is already 0.050; the ICU− curve is clipped to '
               '[39.0, 144.0] and loses its *upper* tail, reaching y=1.0 at 144 bpm '
               'where the true CDF is 0.952. Mort+ reaches 1.0 at 127.5 (true CDF '
               '0.962), Mort− at 155.0 (true CDF 0.980). Every quantile read off '
               'these panels, and every visual ICU+/ICU−/Mort+/Mort− separation, is '
               'distorted; the underlying centroid pickles are fine.'),
    recompute=('Re-run only the ECDF section of '
                 'Experiments/render_paper_figures.py (`fig_ecdf_grid("4x2")` and '
                 '`("2x4")`). No model retraining, no centroid recomputation — the '
                 'inputs under Data/mimic-iii/mean/centroids/ are unchanged.'),
    technical=('render_paper_figures.py:466 composes the two helpers. `_p95_clip` '
                 '(423-426) is a two-sided window on |x − c| with c = that '
                 "subpopulation's centroid component and the limit taken from that "
                 "subpopulation's own deviation distribution, so both the window "
                 'position and the window width differ per curve. `_ecdf` (416-420) '
                 'drops NaNs and returns `np.arange(1, len(v)+1)/len(v)` over '
                 'whatever survived, i.e. the denominator is 0.95·N of that curve, '
                 'not N. Because the deviation distribution is asymmetric, the 5% '
                 'that gets removed is not split evenly between tails and the split '
                 'direction differs per curve (verified above: ICU+ loses the low '
                 'tail, ICU− the high tail). The identical clip in '
                 'visualization_manager_v2.centroid_plot:509-516 is harmless because '
                 'that plot normalises each histogram to its own maximum and exposes '
                 'a `use_percentile=False` variant that the gallery also renders '
                 '(463-468, and render_paper_figures.py:510-511 renders both '
                 '`centroid_density_raw_mimic_iii.pdf` and `..._full_range.pdf`); '
                 'the ECDF grid has no such variant and no note in the axis label '
                 '`"cumulative fraction"` (473) or the section header (398-401). No '
                 'documentation of ECDF clipping exists anywhere — grep for "ecdf" '
                 'in README.md, the toolbox README, notebook.py and noahNotes.md '
                 'returns nothing.'),
    fix=('Compute the ECDF on the full non-NaN vector and clip the *view* instead: '
           '`x, y = _ecdf(pts[:, vital_idx])` followed by `ax.set_xlim(c[vital_idx] '
           '- lim, c[vital_idx] + lim)` with a shared `lim` across the four curves '
           'of a panel (e.g. the max of the four per-curve p95s), so the denominator '
           'is the true subpopulation size and the curves are directly comparable. '
           'If truncation must stay, plot y as `rank/N_full` rather than '
           '`rank/N_kept` and label the axis as a partial ECDF.'),
    verification=('After re-rendering, no curve should terminate at y=1.0 inside '
                    'the data range: for heart rate the ICU− curve must pass through '
                    'y≈0.952 at 144 bpm and the ICU+ curve must start at y≈0.050 at '
                    "62.4 bpm. A quick check is that each curve's final y equals "
                    '(points within the drawn x-limits)/(total non-NaN points for '
                    'that subpopulation) — for ICU+ that is 16388/17251 = 0.950, not '
                    '1.000.'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C16',
        note=('Intent citation checked and found not to cover this figure: '
             "noahNotes.md:474 documents the 95th-percentile clip 'for better "
             "visualization' of the density/violin plot, and no source mentions the "
             'ECDF — a clip is defensible on a scatter of points but not on a figure '
             'whose y-axis is itself an estimate of the distribution. Measured on '
             'the heart-rate panel (mean agg): ICU+ is clipped to [62.4, 183.2] and '
             'loses ~861 of 17,251 points almost entirely from the LOWER tail, so it '
             'starts at y~0 where the true CDF is already 0.050; ICU- reaches y=1.0 '
             'at 144 bpm where the true CDF is 0.952. The same clip in '
             'visualization_manager_v2.centroid_plot:509-516 is harmless because '
             'that plot normalises to its own maximum and ships a '
             '`use_percentile=False` twin; the ECDF grid has neither.'),
    ),
),
dict(
    id='R-16', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name='Missing scenarios are rendered as a perfect null',
    overview=('The scenario McNemar heatmap substitutes `1.0` whenever a scenario '
                'key or its p-value is absent, then plots `-log10(p)`, so a missing '
                'experiment renders as exactly 0.0 — visually identical to a real '
                '"no significant difference" cell. The neighbouring '
                'accuracy-deviation heatmap in the same section uses `np.nan` for '
                'the same condition, which renders as a blank, so the notebook '
                'applies two different missing-data conventions to the same scenario '
                'list. With the pickles currently on disk no scenario is actually '
                'missing, so the defect is latent in the rendered figures but live '
                'in the code.'),
    affects=('comparison/pipeline_comparison.ipynb cell 26 ("MIMIC_Extract — '
               'McNemar −log₁₀(p) vs Baseline") and the cross-pipeline McNemar '
               'figure in cell 20 via `visualize_mcnemar_significance` (notebook '
               'line 325), which coerces NaN p-values to 1.0 the same way. No '
               'currently rendered cell is numerically wrong, because all five '
               'scenario pickles contain all 13 keys with non-None McNemar tuples; '
               'the risk is that any future re-run with a crashed or skipped '
               'scenario will publish that scenario as a confident null. A '
               'secondary, already-live confusion: genuine `(0.0, 1.0, 0, 0)` '
               'results (minperc5 in all five methods — zero discordant pairs, i.e. '
               'identical predictions) also map to 0.0 on the same colour scale as '
               '"no data would have".'),
    recompute=('Nothing — no current figure changes numerically. Re-execute cell '
                 '26 only if the fallback is changed to NaN so the (identical) '
                 'figure is regenerated under the corrected code.'),
    technical=('Cell 26 builds `_pvals[method]` with `mnm[1] if (mnm and mnm[1] is '
                 'not None) else 1.0` (pipeline_comparison.ipynb:1528), where `mnm = '
                 "MIMIC_SCENARIO_IMPACT[method].get(sc, {}).get('mcnemar')`; the two "
                 "`.get` calls mean a missing scenario key, a missing `'mcnemar'` "
                 'field, and a `None` p-value all collapse to the same `1.0`. '
                 '`df_logp = -np.log10(df_pval.clip(lower=1e-10))` then maps that to '
                 '0.0, the minimum of the colour scale, and `annotate=False` means '
                 'no numeric text distinguishes it. Cell 25, twelve lines earlier '
                 "over the identical `_sc_list`, uses `.get('test_acc', np.nan)` "
                 '(pipeline_comparison.ipynb:1480), and cell 31 (line 1740) does the '
                 "same and explicitly greys NaN bars (`'#a0a0a0' if not "
                 'np.isfinite(d)`), so the NaN convention is the established one in '
                 'this notebook. I confirmed against the artifacts that `raw` is the '
                 "only entry with `'mcnemar': None` and `raw` is excluded by "
                 "`_sc_list = [s for s in MIMIC_SCENARIO_LABELS if s != 'raw']`, "
                 'hence the fallback is currently unreachable.'),
    fix=('Use `np.nan` instead of `1.0` in cell 26 (and make '
           '`visualize_mcnemar_significance` at notebook line 325 propagate NaN '
           'rather than mapping it to 1.0), so unavailable comparisons render blank '
           'like every other missing value in the notebook. Optionally annotate '
           'cells whose discordant counts are zero, since that is a real result that '
           'deserves a different mark from "absent".'),
    verification=('Temporarily drop one scenario key from a copy of the loaded '
                    'dict and confirm the corresponding heatmap cell renders blank '
                    'rather than as a 0.0 tile; assert '
                    "`set(MIMIC_SCENARIO_IMPACT[m]) >= set(_sc_list) | {'raw'}` for "
                    'all methods at load time so a genuinely missing arm fails '
                    'loudly.'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C12',
        note=('Correction: no scenario is currently missing — all 12 non-raw '
             'scenarios are present with valid p-values in all five '
             '`mortality_scenario_impact.pkl` files — so the defect is latent in the '
             'rendered figures while live in code. The two missing-data conventions '
             '(1.0 here, np.nan in the adjacent heatmap) are genuinely inconsistent. '
             'Severity suggestion: Low.'),
    ),
),
dict(
    id='R-17', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name='Signed quantities plotted on a sequential colormap',
    overview=('Three diverging heatmaps use a monotonic ramp with no midpoint, so '
                'the sign of a cell is unreadable without squinting at the '
                'annotation.'),
    affects=('`pipeline_comparison.ipynb` cell 18\'s "Score Deviation (EHR − MIMIC, '
               'in % points)" heatmap, cell 24\'s "Mean Vital (z-score within vital) '
               'by Scenario" heatmap, and cell 25\'s "Test Accuracy Δ vs Baseline by '
               'Scenario & Aggregation (% points)" heatmap — all three have stored '
               '`image/png` outputs, so the rendered figures in the committed '
               'notebook are wrong. Colour-encoded direction is unreadable in all '
               'three: whether a preprocessing choice helped or hurt, and whether a '
               "scenario's vital mean sits above or below the scenario mean, cannot "
               'be read off the colour field. The two genuinely sequential heatmaps '
               '(cell 26, −log₁₀ p; cell 29, AUC-ROC) are correctly served by this '
               'colormap and are not affected.'),
    recompute=('Nothing. Purely a rendering change — re-execute '
                 '`pipeline_comparison.ipynb` cells 18, 24 and 25.'),
    technical=('`generate_heatmap` (`pipeline_comparison.ipynb` cell 6, JSON lines '
                 '~245-252) does `cmap = _aurora_cmap()` then `hm = '
                 "ax.imshow(df.values, cmap=cmap, aspect='auto', origin='lower')` — "
                 'no `norm=`, no `vcenter`, no symmetric limit derivation — and '
                 '`_aurora_cmap()` (line 202) builds a 20-step '
                 "`LinearSegmentedColormap` from `_AURORA = ['#191a1c', '#724ed5', "
                 "'#4ED595']` (line 131), a strictly increasing-luminance ramp. The "
                 'three signed callers: cell 18 builds `df_dev` from '
                 '`(_ehr_scores[key][i] - _mimic_scores[key][i]) * 100`, a '
                 'difference in percentage points that straddles zero (the stored '
                 'cell 16 table has EHR ahead on mean/median and behind on the three '
                 'deviation methods, so the matrix genuinely contains both signs); '
                 'cell 24 builds `df_mimic_vit_z = (df_mimic_vit - '
                 'df_mimic_vit.mean()) / _col_std` (line 1440), z-scores centred on '
                 'zero by construction; cell 25 builds `df_mimic_dev_pp = '
                 'df_mimic_dev * 100.0` from '
                 "`MIMIC_SCENARIO_IMPACT[method][sc]['test_acc'] - _base`, a signed "
                 "delta. The annotation formats do preserve sign (`'{v:+.2f}'` for "
                 "cell 24, `'{v:+.1f}'` for cell 25, and the default `'{v:.1f}'` for "
                 'cell 18 shows a leading minus on negatives), which is exactly the '
                 '"squint at the annotation" fallback the claim describes. '
                 'Documented intent contradicts the usage rather than excusing it: '
                 "the colormap's own definition comment "
                 '(`visualization_manager_v2.py:21`) states the ramp is chosen '
                 'because it "doesn\'t imply a midpoint the data doesn\'t have" — the '
                 'data in these three cells *does* have a midpoint, so the stated '
                 'rationale for the colormap is the reason it should not have been '
                 "used here (guardrail 10). Note the same file's `heatmap()` (line "
                 '149) has the identical unconditional `cmap=` call, so the defect '
                 'is structural to the shared helper, though its EHR-side callers '
                 '(observation counts, AUC) are all non-negative.'),
    fix=('Give `generate_heatmap` (and `visualization_manager_v2.heatmap`) a '
           '`diverging: bool = False` or `center: float | None = None` parameter; '
           'when set, build a symmetric diverging colormap around the centre (e.g. a '
           'red↔grey↔green ramp consistent with the `#bd3140` / `#a0a0a0` / '
           '`#3b8465` triple already used by the bar plots) and pass '
           '`norm=mcolors.TwoSlopeNorm(vcenter=0, vmin=-M, vmax=+M)` with `M = '
           'np.nanmax(np.abs(values))`. Set it at the three call sites (cells 18, '
           '24, 25) and leave cells 26/29 sequential. Add a zero tick to the '
           'colorbar.'),
    verification=('Re-run the three cells and confirm (a) the colorbar is '
                    'symmetric about 0 with a visible zero tick, (b) cells whose '
                    'annotation carries a `-` render on the opposite side of the '
                    "ramp's centre from `+` cells, and (c) a synthetic input of "
                    '`[[-1, 0, +1]]` produces three visually distinct colours with '
                    'the middle one at the neutral midpoint. Cells 26 and 29 should '
                    'be byte-comparable to their current output.'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C13',
        note=('Not intentional: the only relevant documented rationale '
             '(`visualization_manager_v2.py:20-21`) argues against using the '
             'sequential Aurora ramp for signed data. Annotations keep the true '
             'values recoverable, so no number changes.'),
    ),
),
dict(
    id='R-18', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name='Three incompatible definitions of F1 under one header',
    overview=('The repository computes F1 three incompatible ways — weighted in '
                "the comparison notebook's MIMIC path, sklearn-default binary in the "
                'MIMIC_Extract scenario sweep, and macro in the EHR evaluator (both '
                'the legacy and CV paths) — and every one of them is stored or '
                'displayed under the bare name `f1` / `test_f1` / "F1". Worse, in '
                'the live comparison notebook the EHR pkl is unpacked positionally '
                'as `_acc, _f1, _auc, ...` against a tuple that is actually '
                '`(train_acc, test_acc, train_f1, test_f1, mcnemar)`, so the value '
                'plotted in the "F1 Score" panel for EHR is a test *accuracy* and '
                'the macro F1 lands in the "AUC-ROC" panel. The F1 comparison '
                'therefore has no shared definition on either axis.'),
    affects=('comparison/pipeline_comparison.ipynb — the `F1` column of the '
               'summary table (cell 16), the "F1 Score" panel and its row in the '
               'EHR−MIMIC deviation heatmap (cell 18), and the "F1" panel of the '
               'summary dashboard (cell 33). Concretely, in the executed table the '
               'EHR "F1" reads 0.9120 next to EHR accuracy 0.9124 (they are '
               'near-duplicates because both come from accuracy-valued positions), '
               'while MIMIC\'s weighted F1 reads 0.8696 — the ~4-point "EHR advantage '
               'in F1" is an artifact of comparing a weighted F1 against an '
               'accuracy. The macro F1 values (0.5719, 0.5736, 0.4804, 0.4801, '
               '0.4815) appear under "AUC-ROC". Separately, MIMIC_Extract\'s stored '
               'binary `test_f1` (e.g. 0.3836 for raw/maximum_deviation in '
               'data/scenario_analysis/*/mortality_scenario_impact.pkl) is on a '
               'completely different scale from either and would be nonsense if '
               'plotted next to them; it is currently loaded but not plotted, and '
               'paper_figures/filter_impact_mortality_testing_f1_mean.pdf labels the '
               'EHR macro value simply as F1.'),
    recompute=('No model retraining is needed for the labelling half — re-execute '
                 'comparison/pipeline_comparison.ipynb from cell 10 onward once the '
                 'unpacking and labels are corrected. Making the F1s genuinely '
                 "comparable does require re-scoring: recompute MIMIC's F1 with "
                 "`average='macro'` (a metrics-only re-run of the notebook's "
                 'classifier loop and, if the scenario F1s are to be used, of '
                 "_patch_copy2's sweep)."),
    technical=('Definition 1 — pipeline_comparison.ipynb:1000 (generator '
                 "provenance _gen_comparison_nb.py:622) uses `average='weighted'`, "
                 'which on ~9% mortality prevalence is dominated by the survival '
                 'class; the cell 15 markdown states "F1 (weighted)". Definition 2 — '
                 '_patch_copy2.py:210-211 and 274-275 call `f1_score(...)` with no '
                 "`average`, i.e. sklearn's `'binary'` default (positive-class F1), "
                 'stored as `train_f1`/`test_f1` in `mortality_scenario_impact.pkl`. '
                 'Definition 3 — evaluation_manager.py:297-298 uses '
                 '`average=\'macro\'` with the in-code justification "mortality '
                 'prevalence is low enough that weighted F1 would mostly be '
                 'reporting how well we predict survival"; the CV path repeats macro '
                 'at lines 463 (`train_f1s.append(float(f1_score(y_fit, '
                 "fit_predictions, average='macro')))`) and 478 (`'f1_macro'`), and "
                 'its docstring at lines 636-637 documents positions [2]/[3] as '
                 '"mean in-fold training macro F1" and "out-of-fold macro F1". The '
                 'routing error is at pipeline_comparison.ipynb:665, which names the '
                 '5-tuple `_acc, _f1, _auc, _, _mnm` while evaluation_manager.py:308 '
                 'returns `(training_averages, testing_averages, training_f1s, '
                 'testing_f1s, mcnemar_results)`; cell 16 '
                 '(pipeline_comparison.ipynb:1011-1013) then feeds `_f1` into '
                 "`EVAL_RESULTS[m]['ehr']['f1']` and `_auc` into `['auc']`. I "
                 'verified the consequence in the stored output: EHR "F1" ≈ EHR '
                 '"Accuracy" to three decimals for all five methods, and the '
                 '"AUC-ROC" values sit in the 0.48-0.57 band characteristic of the '
                 'macro F1 numbers, not of an AUC.\n'
                 '\n'
                 'First-pass measurements retained: The binary values (0.32, 0.25) '
                 'and the macro values (0.55-0.62) are not on the same scale, yet '
                 'cells 25 and 31 place them in adjacent panels.'),
    fix=('Standardise on macro F1 (the choice the EHR evaluator already argues '
           "for) — change pipeline_comparison.ipynb:1000 to `average='macro'` and "
           "_patch_copy2's calls to `average='macro'` — and make every axis label "
           'and column header state the averaging explicitly ("Macro F1"). '
           'Independently, replace the positional unpack at '
           'pipeline_comparison.ipynb:665 with names matching '
           'evaluation_manager.py:308 (`_train_acc, _test_acc, _train_f1, _test_f1, '
           '_mnm`) and route `_test_f1` into the F1 slot; drop the fabricated '
           '"AUC-ROC" panel for the EHR side, since the pickle contains no AUC at '
           'all.'),
    verification=('Assert at load time that the EHR "F1" series is not numerically '
                    '~equal to the EHR accuracy series (`not np.allclose(f1, acc, '
                    'atol=1e-3)`), and that no panel labelled AUC contains a value '
                    'below 0.5 by construction. After standardising, recompute one '
                    "method's MIMIC F1 both ways and confirm the weighted value is "
                    'materially higher than the macro value (weighted ≈ 0.87 vs '
                    'macro ≈ 0.5-0.6 at this prevalence) — if the plotted number '
                    'does not drop, the label is still lying.'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C12',
        note=('Corrections: (a) the binary-F1 variant from `_patch_copy2.py` is '
             'loaded into `MIMIC_SCENARIO_IMPACT` but never plotted; (b) the macro '
             "F1 does not appear under the 'F1' panel at all — it lands under "
             "'AUC-ROC' via the positional unpack at pipeline_comparison.ipynb:665, "
             "and the 'F1' panel shows a test accuracy. The naming question itself "
             'is left to MANIFEST §7 (guardrail 6). Severity suggestion: High.'),
    ),
),
dict(
    id='R-19', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name="'icu' means two different targets across the two pipelines",
    overview=('Both pipelines actually predict "ICU length of stay > 3 days", but '
                'by different definitions — EHR-Dataset-Processing sums and merges '
                'all ICU stays of an admission (mimic-iii-processing.py:148-161) '
                'while the MIMIC_Extract notebook thresholds the per-stay `los_icu` '
                'column (cell 4) — and _patch_copy2.py:100-105 asserts a third, '
                'wrong story (ICU mortality on the MIMIC side, ICU admission on the '
                'EHR side). Because the gallery tags MIMIC records `icu_los` and EHR '
                "records `icu`, build_manifest's pairing keys never match them, so "
                "the two pipelines' ICU figures silently fail to cross-reference "
                'each other.'),
    affects=('Provenance comments and display strings: _patch_copy2.py:99-106 '
               '(wrong for both pipelines); the gallery cross-pipeline suggestion '
               'index (build_manifest.py:37-55 `_key_cross_pipeline` includes '
               '`label`) and the label-flip index (build_manifest.py:118-126 '
               'hard-codes the literal `"icu"`), so the 10 MIMIC McNemar heatmaps '
               'tagged `label="icu_los"` (extract_notebook_graphs.py:103,111) get '
               'neither an EHR twin nor a mortality twin. No plotted number is wrong.'),
    recompute=('Nothing numerically. Re-run gallery/build_manifest.py after the '
                 "label vocabulary is reconciled so graphs_manifest.json's "
                 'suggestion map is rebuilt.'),
    technical=('EHR side: `get_icu_labels()` (mimic-iii-processing.py:126-163) '
                 'merges overlapping/adjacent `icustays` intervals and sets '
                 '`icu_label = int(total_days > 3)`; its own docstring at :136-138 '
                 'warns "The threshold is 3 days, on *summed* time across all stays '
                 '— not longest single stay, and not the ICU-LOS definition '
                 'MIMIC_Extract uses." REPO/README.md:37 states the two targets as '
                 '"(ICU stay > 3 days, in-hospital mortality)". MIMIC side: the live '
                 "notebook's `_select_pos_label` (cell 4) supports only `'icu_los'` "
                 "(`los_icu > 3`) and `'mortality'` and raises `ValueError('Unknown "
                 "target label')` otherwise; `LABELS = ['icu_los','mortality']` "
                 '(cell 3); the executed cell 14 renders `LABEL_DISPLAY = '
                 "{'icu_los': 'icu_los (ICU stay > 3 days)', ...}`. So neither side "
                 'computes ICU mortality (`mort_icu`) or ICU admission anywhere I '
                 "could find, and _patch_copy2.py's `LABEL_DISPLAY` keyed on `'icu'` "
                 "would in fact `KeyError` against the notebook's `LABELS` if the "
                 'patch block were re-applied as written (_patch_copy2.py:348 and '
                 ':373 index `LABEL_DISPLAY[target_label]`). Gallery: '
                 'render_marimo_mimic_iii.py:121 `LABELS = ["icu", "mortality"]` and '
                 'its metadata dicts emit `"label": label`; '
                 'extract_notebook_graphs.py:103 emits `label="icu_los"` for the '
                 'MIMIC notebook. `_key_cross_pipeline` (build_manifest.py:48-55) '
                 'puts `label` in the key, so `icu` ≠ `icu_los` blocks the MIMIC↔EHR '
                 'pairing, and `_key_cross_label` consumers at :120-122 test for the '
                 'literal `"icu"`, so `icu_los` records are excluded from label '
                 'flipping.'),
    fix=("Correct _patch_copy2.py:99-106 to match the notebook (`'icu_los': "
           "'icu_los (ICU stay > 3 days, per-stay los_icu)'`) and drop the false "
           'claim about EHR meaning "admission". Pick one vocabulary for the gallery '
           '— either rename the EHR facet to `icu_los` in '
           'render_marimo_mimic_iii.py:121 and render_paper_figures.py:93-context '
           'metadata, or normalise `icu_los`→`icu` in build_manifest.py — and in the '
           'same pass make build_manifest.py:118-126 label-agnostic (compare the set '
           'of labels present rather than hard-coding `"icu"`). Record the '
           'summed-vs-per-stay definitional difference in a caption or in the '
           'toolbox README next to the existing hour-0 warning (README.md:7) so '
           'cross-pipeline ICU comparisons are not read as like-for-like.'),
    verification=('After rebuilding graphs_manifest.json, assert that an EHR ICU '
                    "record's suggestion list contains a MIMIC_Extract ICU peer and "
                    'its mortality twin, and that no record carries both '
                    'vocabularies. Grep for the string `mort_icu` across both '
                    'pipelines and confirm zero live uses, which is what makes '
                    "_patch_copy2.py's comment provably wrong."),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C15',
        note=('Corrections: (1) neither side is ICU mortality and neither is ICU '
             'admission — both are ICU-LOS>3, computed two different ways; (2) the '
             'gallery does not merge them under one label, it fails to pair them '
             "because the labels differ (`icu` vs `icu_los`). The false 'ICU "
             "mortality / admission' framing lives in `_patch_copy2.py`, and per "
             'guardrail 10 that contradiction confirms a real labelling defect — '
             'just not the one described. `render_marimo_mimic_iii.py:404` is '
             'docstring text, not a label site.'),
    ),
),
dict(
    id='R-20', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name="NaN results render as invisible 'not significant' bars",
    overview=('The CV path produces NaN for a degenerate arm where the legacy path '
                'never did, and the plotting code turns that into a grey bar of '
                'height nothing.'),
    affects=('The McNemar chart for the `high invalid data` arm under the three '
               'deviation-based aggregations (`standard deviation`, `mean '
               'deviation`, `maximum deviation`) for both labels — 6 of the 120 EHR '
               "McNemar bars — whenever `Experiments/notebook.py`'s `IMPACT_SUFFIX` "
               "is set to `'_cv'`. The CV artifacts containing those NaNs already "
               'exist on disk (`*_filter_impact_cv.pkl`, 2026-08-11 15:30/15:35). '
               "Under the current default `IMPACT_SUFFIX = ''` the NaN never reaches "
               'the plot, so no *published* figure is wrong today — but the switch '
               'is documented as safe for exactly this plot, so the first person who '
               'flips it gets a silent misreport: "the test could not be computed" '
               'is rendered as "the filter made no significant difference". The '
               'companion `filter_impact_plot` is worse under the same input: '
               '`deviations.min()`/`.max()` propagate NaN into `axes.set_ylim`, '
               'which matplotlib rejects for non-finite limits.'),
    recompute=('Nothing needs recomputing — the CV pickles and their JSON sidecars '
                 'are correct and already record `degenerate: true`, `n_paired: 0`, '
                 '`coverage: 0.0`. Only the plotting functions change, and any '
                 'CV-based figures already rendered would need re-rendering.'),
    technical=('In `evaluation_manager.calculate_mcnemar_paired` the guard at '
                 "lines 572-575 returns `float('nan'), float('nan')` with "
                 "`detail['degenerate'] = True` when `np.intersect1d` of the two "
                 "arms' covered admission ids is empty — the docstring at line "
                 '561-562 states this deliberately ("A pair count of zero yields '
                 '`(nan, nan)` and a flag rather than the old silent all-zero '
                 'table"). `evaluate_filter_impact_cv` appends that pair '
                 'unconditionally (`mcnemar_results.append((statistic, p_value))`, '
                 'line 698) and also appends '
                 "`result['diagnostics']['accuracy_mean']` — likewise NaN via "
                 '`_safe_mean` (lines 346-352) — into `testing_averages` (line 687). '
                 'The legacy `calculate_mcnemar_test` (lines 200-233) has no such '
                 'branch: it builds `table = np.zeros((2, 2), dtype=int)` and calls '
                 '`mcnemar(table, exact=True)`, and the module docstring at line 36 '
                 'records the design ("Empty folds score 0.0 rather than NaN or an '
                 'exception"), which is why the legacy `standard '
                 'deviation/mortality_filter_impact_diagnostics.json` shows `n_test: '
                 '0` for `high invalid data` without any NaN in the tuple. Consumer '
                 'side: `Experiments/notebook.py:648` and `:689` pass `[x[1] for x '
                 "in RESULTS[agg][-1]][1:]` into `mcnemar_plot`, where line 327's "
                 "`max(p, 1e-20)` leaves NaN intact (Python's `max` keeps the first "
                 'element when the comparison `1e-20 > nan` is False), line 329 '
                 "yields `nan` height, line 339's `nan < 0.05` is False so the bar "
                 "takes `'#a0a0a0'`, and the per-bar annotation at lines 357-361 is "
                 'placed at `height + 0.1 == nan` so it is not drawn either — the '
                 'bar and its label both vanish while the legend still advertises '
                 'grey as the below-threshold colour. '
                 '`render_paper_figures.paper_mcnemar_plot` has the identical '
                 '`max(p, 1e-20)` at line 340. By contrast the two notebook-local '
                 'copies were already hardened: `pipeline_comparison.ipynb:257` and '
                 '`mimic_extract_analysis.py:544` both use `max(float(p) if p == p '
                 'else 1.0, 1e-20)`, so the fix pattern exists in the repo and '
                 'simply was not back-ported to `visualization_manager_v2`. The '
                 'documented claim that "Both files carry the same five positions so '
                 'the plots below work either way" '
                 '(`Experiments/notebook.py:561-562`) is therefore false for '
                 '`mcnemar_plot` and `filter_impact_plot`, which is the '
                 'contradiction that confirms the defect.'),
    fix=('In `visualization_manager_v2.mcnemar_plot` (and '
           '`render_paper_figures.paper_mcnemar_plot`), detect NaN explicitly '
           'instead of coercing it: keep a `is_missing = [p != p for p in p_values]` '
           'mask, plot those arms with a visually distinct hatched/outlined marker '
           'spanning the axis (or a zero-height bar annotated "n/a — degenerate '
           'arm") in a colour that is *not* the grey used for p ≥ 0.05, and exclude '
           "them from the legend's significance categories. Do not follow the "
           "notebook copies' `else 1.0` substitution — that silently asserts p=1. "
           'Give `filter_impact_plot` the same treatment and switch its axis logic '
           'to `np.nanmin`/`np.nanmax` with a fallback so `set_ylim` never receives '
           'NaN.'),
    verification=("Set `IMPACT_SUFFIX = '_cv'` and render the `standard deviation` "
                    'McNemar and filter-impact charts for `mortality`: '
                    '`filter_impact_plot` must complete without a non-finite-limits '
                    'error, and the `high invalid data` bar must be visually and '
                    'legend-distinguishable from the other grey bars. Cross-check '
                    'against `Data/mimic-iii/standard '
                    'deviation/mortality_filter_impact_cv_diagnostics.json`, where '
                    '`["high invalid data"]["mcnemar"]["n_paired"] == 0` and '
                    "`coverage == 0.0`. Re-render with `IMPACT_SUFFIX = ''` and "
                    'confirm the legacy charts are unchanged.'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C13',
        note=("Not a guardrail-2 'partially fixed' case: the NaN-safe guard exists "
             'only in two standalone notebook copies serving different data, while '
             'the shared plotting modules (`visualization_manager_v2.py:327`, '
             '`render_paper_figures.py:340`) both still use the NaN-transparent '
             "`max(p, 1e-20)`. Latent today only because `IMPACT_SUFFIX=''` "
             '(guardrail 3), which is why severity stays Medium.'),
    ),
),
dict(
    id='R-21', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name='Centroid computation masks legitimate zeros under deviation aggregations',
    overview=('Zero is treated as missing, but under the deviation methods it is '
                'the correct value for a single-reading hour.'),
    affects=('All 52 centroid pickles in each of Data/mimic-iii/standard '
               'deviation/centroids/, .../mean deviation/centroids/ and .../maximum '
               'deviation/centroids/, and every notebook centroid-shift bar/violin '
               'rendered from them for those three aggregations. Measured on '
               'Data/mimic-iii/*/centroids/icu_raw_pos.pkl (17,272 patients): '
               'per-vital NaN fraction is [0.001, 0.173, 0.173, 0.172, 0.172, 0.186, '
               '0.172] under mean/median but [0.166, 0.276, 0.276, 0.278, 0.244, '
               '0.834, 0.362] under all three deviation methods — the temperature '
               'centroid for ICU+ is computed from 16.6% of the class instead of '
               '81.4%. Not one exact-zero value survives in any of the 7 vitals of '
               'any deviation-aggregation points array. The paper_figures/ outputs '
               'use AGG="mean" only and are unaffected.'),
    recompute=('Delete Data/mimic-iii/{standard deviation,mean deviation,maximum '
                 "deviation}/centroids/*.pkl and recompute them (notebook.py's "
                 '`get_centroids` cell). mean/median artifacts need no recompute '
                 '(they contain no zeros to recover), and no model retraining or '
                 'figure re-render is required for paper_figures/.'),
    technical=('ehr_filter_manager.aggregate (ehr_filter_manager.py:358-388) '
                 'writes `float(func(numeric_values))` per hour-cell; for a '
                 'one-element list, np.std → 0.0, mean-deviation → 0.0, '
                 'max-deviation → 0.0, so a legitimate "no variability observed" is '
                 'encoded as 0.0 while an empty cell becomes NaN (line 378/382-383). '
                 'RecordEHR.to_tensor (ehr_record.py:41-42) then collapses that '
                 'distinction: `np.nan_to_num(timeseries_array, nan=0.0)`. '
                 'compute_tensor_centroid (evaluation_manager.py:737-743) cannot '
                 'tell them apart and masks both, so the per-patient value becomes '
                 'the mean over multi-reading hours only, and a patient with no '
                 'multi-reading hour for a vital yields NaN, which '
                 'compute_dataset_centroid:786-788 then excludes from the class sum '
                 'and count. Magnitude is set by the observation density: the mean '
                 'per-hour observation counts annotated in '
                 'paper_figures/observation_count_heatmap_raw_mimic_iii.pdf span '
                 '0.202 to 1.125 across all 168 (hour, vital) cells, i.e. '
                 'essentially every non-empty hour has exactly one reading. The '
                 'docstring at 729-731 justifies the mask by "RecordEHR.to_tensor() '
                 'zero-fills NaNs" and to_tensor\'s own comment (38-40) by "vitals '
                 'are all strictly positive in practice" — a precondition that holds '
                 'for the level aggregations and fails for the dispersion ones, '
                 'which notebook.py:746 nevertheless feeds through the same function.'),
    fix=('Thread the aggregation semantics into the mask: give '
           '`compute_tensor_centroid(tensor, treat_zero_as_missing=True)` and '
           '`compute_dataset_centroid(..., treat_zero_as_missing=True)` the flag, '
           "and pass False from notebook.py's `get_centroids` loop whenever "
           '`aggregation_method` is one of the three deviation methods (then '
           '`invalid = torch.isnan(tensor)` only). The robust alternative is to stop '
           'inferring missingness from the tensor at all — carry a NaN-preserving '
           'copy (or a boolean observed-mask) from RecordEHR.timeseries into the '
           "centroid path — leaving to_tensor's zero-fill untouched for the model "
           'input.'),
    verification=('Recompute Data/mimic-iii/standard '
                    'deviation/centroids/icu_raw_pos.pkl and check that (a) the '
                    'per-vital NaN fraction falls back to the mean-aggregation level '
                    '(temperature from 0.834 to ≈0.186), (b) the points array now '
                    'contains exact 0.0 entries, and (c) every deviation centroid '
                    'component decreases (temperature std currently 0.432, heart '
                    'rate 3.526). Cross-check one patient by hand: a record whose '
                    'temperature row has 24 single-reading hours must yield a '
                    'temperature centroid of 0.0, not NaN.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C16',
        note=('Measured per-vital NaN fractions in `icu_raw_pos.pkl` (17,272 '
             'patients): [0.001, 0.173, 0.173, 0.172, 0.172, 0.186, 0.172] under '
             'mean/median but [0.166, 0.276, 0.276, 0.278, 0.244, 0.834, 0.362] '
             'under all three deviation methods — the ICU+ temperature centroid is '
             'computed from 16.6% of the class instead of 81.4%, and not one exact '
             'zero survives in any deviation-aggregation points array. Root cause '
             'chain: `aggregate` writes 0.0 for a single-reading hour, `to_tensor` '
             'zero-fills NaN, and `compute_tensor_centroid` can no longer tell the '
             'two apart. The precondition the code states for the mask '
             "(ehr_record.py:38-40, 'vitals are all strictly positive') holds for "
             'the level aggregations and fails for the dispersion ones — guardrail '
             '10. paper_figures/ uses mean only and is unaffected; recompute scope '
             'is the centroids of the three deviation aggregations only.'),
    ),
),
dict(
    id='R-22', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name='The centroid marker is unclipped but the density behind it is clipped',
    overview=('The X sits at the mean of all points while the violin is drawn from '
                'the central 95%, so the marker appears off-centre.'),
    affects=('paper_figures/centroid_density_raw_mimic_iii.pdf (the p95 variant, '
               'rendered 2026-08-10 22:13 via render_paper_figures.py:242-243) — '
               'visibly wrong on the ICU-positive oxygen-saturation and heart-rate '
               'panels; also every `use_percentile=True` centroid_plot panel in the '
               'notebook (Experiments/notebook.py:837+) and gallery. '
               'centroid_density_raw_mimic_iii_full_range.pdf is unaffected because '
               '`use_percentile=False` makes `limit = nanmax(distances)` and drops '
               'nothing.'),
    recompute=('Nothing (no model refit, no centroid recompute). Re-render the '
                 'paper figures only.'),
    technical=('`centroid_plot` reads `center = group_centroids[i]` '
                 '(visualization_manager_v2.py:511), builds `distances`/`limit` and '
                 'filters `values` (514-516), histograms only the survivors '
                 '(522-525) and fills the band from them (531-537), then plots the '
                 'marker at the unfiltered `center` (539-543). The centroid itself '
                 'comes from `compute_dataset_centroid` '
                 '(evaluation_manager.py:745-798), a plain per-vital mean over all '
                 'non-NaN patient centroids, and the raw dataset has no per-vital '
                 'range filtering (POSTMORTEM.md:161-163 records raw maxima of '
                 '23,353 for mean aggregation), so the mean is outlier-dominated on '
                 'skewed vitals. Recomputed from the shipped artifact '
                 'icu_raw_pos.pkl (17,272 points): oxygen saturation center 100.903, '
                 'mean of the clipped subset 97.687, clipped span [93.80, 100.00] → '
                 'marker outside the density; heart rate center 128.467, clipped '
                 'mean 98.318 (863 points dropped), marker at 0.55 of span but ~30 '
                 'bpm above the bulk. mortality_raw_pos oxygen saturation: center '
                 '95.897 sits at 0.69 of the [86.67, 100.00] span. Because the '
                 'marker also participates in autoscaling, its position widens the '
                 "panel's y-limits beyond the density. The docstring (456-469) "
                 'documents the clipping as presentational and offers '
                 '`use_percentile` as the escape hatch, but says nothing about the '
                 'marker being computed on a different sample — so there is no '
                 'intent statement making this consistent.'),
    fix=('Either draw the marker from the same sample as the density (recompute '
           'the mean of the retained `values`, or plot the clipped-sample median) '
           'and add a second, visually distinct marker for the unclipped centroid, '
           'or annotate the panel when `center` falls outside `[values.min(), '
           'values.max()]`. Preferably also record the number of clipped points per '
           'group so the caption can state what was hidden.'),
    verification=('Re-render `centroid_density_raw_mimic_iii.pdf` and check the '
                    'ICU-positive oxygen-saturation panel: the X must lie inside the '
                    "filled band, and the panel's upper y-limit must no longer reach "
                    '~101 for a %-unit vital. Assert in a check script that for '
                    'every group/vital, `values.min() <= plotted_marker <= '
                    'values.max()`.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C14',
        note=('Compounded by the raw arm carrying no per-vital range filtering, which '
             'is what lets the unclipped centroid mean exceed 100% saturation in the '
             'first place.'),
    ),
),
dict(
    id='R-23', stage=REPORT, severity=MEDIUM, status=INTRODUCED, verified=True,
    name='The effect-decomposition workbook names sampling noise as a cause',
    overview=("A row labelled 'Reduced Test Set Size' attributes a causal effect "
                'to something that has no expected effect on a rate.'),
    affects=('`rerun/logs/classifier_performance_mean_raw.xlsx`, sheet "Effect '
               'Decomposition" — the "Reduced Test Set Size" row and its share '
               'column for both labels. Recomputing the sheet inputs from '
               '`rerun/logs/confusion_matrices_mean_raw.json` with the same '
               'seed-averaging as `summarise()` gives mortality old = 0.91257, '
               'new@.5 = 0.90829 → size_effect = -0.00428, credited as 2.5% of the '
               '-0.17158 total; ICU old = 0.71671, new@.5 = 0.71579 → size_effect = '
               '-0.00092, credited as 4.8% of the -0.01916 total. Both are within '
               "about one binomial standard error of zero at n≈4,604. The sheet's "
               "intro text at line 256-258 and the source docstring's phrase "
               '"set-size effect" (`confusion_matrices_mean_raw.py:14-16`) carry the '
               'same framing.'),
    recompute=('Nothing. This is a labelling/presentation change in the exporter; '
                 're-running `python rerun/export_confusion_workbook.py` over the '
                 'existing JSON regenerates the workbook.'),
    technical=('`confusion_matrices_mean_raw.py:96` fits on `x_train` only, so '
                 '`x_val` and `x_test` are both untouched by fitting; `:110-118` '
                 'builds `old` from `y_merged = concat(y_test, y_val)` at `>= 0.5` '
                 'and `new@.5` from `y_test` alone at `>= 0.5`. Under the '
                 'unstratified `torch.randperm` split (`Entities/ehr_dataset.py:75`) '
                 'the validation and test index blocks are exchangeable draws from '
                 'one permutation, so E[acc(val)] = E[acc(test)] and E[size_effect] '
                 '= 0. `export_confusion_workbook.py:281-283` computes `size_effect '
                 '= control - original`, and `:286-287` names it "Reduced Test Set '
                 'Size" with a causal description; `:299-301` divides it by the '
                 'total to print a share, which turns a noise term into an '
                 'attributed percentage. Nothing in the workbook flags it as noise — '
                 'the only variability caveat in the file is at `:322-325`, and it '
                 'is about the four seeds sharing one partition, not about this row.\n'
                 '\n'
                 'First-pass measurements retained: The share at :297 is also '
                 'unguarded: value / total exceeds 100% or goes negative whenever '
                 'the two effects have opposite signs.'),
    fix=('Rename the row to something non-causal (e.g. "Change of Evaluation Set '
           '(no expected effect; sampling difference only)"), drop or blank its '
           '"Share of Total Change" cell, and replace the description with one '
           'stating the two regimes share model and threshold so the difference '
           'measures only which held-out records were scored. Reword `:256-258` and '
           'the `confusion_matrices_mean_raw.py:14-16` docstring accordingly. '
           'Optionally add a per-seed spread column so the reader can see the term '
           'is inside its own noise band.'),
    verification=('Re-run `python rerun/export_confusion_workbook.py` and confirm '
                    'the row no longer asserts a cause and carries no share '
                    'percentage. As a numeric check, compute the per-seed `new@.5 - '
                    'old` values from `rerun/logs/confusion_matrices_mean_raw.json` '
                    'and confirm they straddle zero / are within a binomial SE of '
                    'it, which is what the new wording claims.'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C17',
        note=('Guardrail 5 does not cover this: it excuses the halved test set as a '
             'documented consequence, not the claim that halving it CAUSED an '
             'accuracy change. The two regimes share the fitted forest and the 0.500 '
             'threshold and differ only in whether the never-fitted-on validation '
             'records are appended, so the term has expectation zero. Recomputed '
             'from the JSON: mortality size_effect -0.00428 credited as 2.5% of the '
             '-0.17158 total; ICU -0.00092 credited as 4.8% of -0.01916 — both '
             'within about one binomial SE of zero at n~4,604. Aggravating factor: '
             'the workbook is explicitly written to be handed outside the repository '
             '(export_confusion_workbook.py:4-5).'),
    ),
),
dict(
    id='R-24', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name='Mortality accuracy is below the majority-class baseline on every arm',
    overview=('Mortality prevalence is 9.66% (4,445 of 46,032 records, measured '
                'from the raw label tensors), so a constant "survives" predictor '
                'scores 0.9034. Every mortality accuracy the pipeline reports — '
                '0.4928–0.7865 in the legacy single-holdout artifacts, 0.6510–0.7330 '
                "in the CV artifacts — is below the corresponding arm's "
                'majority-class rate, because the operating point is chosen by '
                "Youden's J on validation and pushes the predicted-positive rate to "
                '0.23–0.41. The figures plot only deviation from the raw arm and the '
                'tables print only raw accuracy, so nothing shows a reader that the '
                'whole column sits under the no-skill line.'),
    affects=('paper_figures/filter_impact_mortality_testing_accuracy_mean.pdf (and '
               'its ICU twin, which is fine), the notebook\'s Mortality "Testing '
               'Accuracy"/"Testing Accuracy Delta" tables, '
               'rerun/logs/classifier_performance_mean_raw.xlsx, and index [1] of '
               'Data/mimic-iii/mean/mortality_filter_impact.pkl and '
               'mortality_filter_impact_cv.pkl. The numbers themselves are correctly '
               'computed; what is wrong is that they are presented as a quality '
               'metric and compared filter-to-filter without the 0.9034 reference '
               '(0.8057 for the "high invalid data" arm, whose prevalence is 0.1943; '
               '0.8910 for "long gap"; 0.8983 for "long missing segment"). ICU is '
               'unaffected — its accuracies (0.616–0.696) exceed its 0.6248 majority '
               'rate on every arm.'),
    recompute=('Nothing needs retraining. Re-render the mortality filter-impact '
                 'figures and regenerate the tables/xlsx after adding the reference; '
                 'the prevalence needed is already in the diagnostics sidecars.'),
    technical=("Prevalence measured independently of the pipeline's own "
                 'diagnostics by counting the class point sets in '
                 'Data/mimic-iii/mean/centroids/mortality_raw_{pos,neg}.pkl: 4,445 '
                 'positive / 41,587 negative = 0.0966, matching '
                 '`population_prevalence` in the CV sidecar. Legacy testing '
                 'accuracies from Data/mimic-iii/mean/mortality_filter_impact.pkl '
                 'index [1], in order raw + FILTER_NAMES '
                 '(render_paper_figures.py:94-99): 0.7410, 0.6820, 0.7023, 0.6681, '
                 '0.7036, 0.6595, 0.6868, 0.6924, 0.7865, 0.6687, 0.6348, 0.4928, '
                 "0.6883 — all below their arm's per-arm `test_prevalence`-implied "
                 'baseline (0.893–0.906; 0.790 for "high invalid data"). CV '
                 'accuracies from mortality_filter_impact_cv.pkl index [1]: 0.6868, '
                 '0.6862, 0.6900, 0.7021, 0.6888, 0.6784, 0.6823, 0.6828, 0.7330, '
                 '0.6510, 0.6563, 0.6877, 0.6872 — all below 0.9034 (0.8057 / 0.8910 '
                 '/ 0.8983 for the three reduced arms). Mechanism: pick_threshold '
                 "(evaluation_manager.py:63-96) maximises Youden's J, "
                 'evaluation_manager.py:184-186 scores accuracy at that threshold, '
                 'and the resulting `test_positive_rate` is 0.288 on raw against a '
                 '0.0997 prevalence. The plotting path never has the absolute scale: '
                 'filter_impact_plot subtracts `scores[0]` '
                 '(visualization_manager_v2.py:252) and labels the axis "Deviation '
                 'from Baseline" with only `axhline(0)`; '
                 'render_paper_figures.fig_filter_impact:314-329 calls that same '
                 'function. Correction to the claim: the accuracy level itself is '
                 'documented and deliberate (visualization_manager_v2.py:196-201, '
                 'evaluation_manager.py:66-71), and the models are not skill-less — '
                 'reported macro-F1 for raw mortality is 0.5542 against 0.4746 for '
                 'the always-negative predictor, so the defect is that an '
                 'uninformative metric is reported without its reference, not that '
                 'the classifiers are worthless.\n'
                 '\n'
                 "First-pass measurements retained: Every arm's CV accuracy is "
                 '0.59-0.74.'),
    fix=('Carry the majority-class rate into the reporting layer. Concretely: add '
           '`majority_rate = 1 - prevalence` to the diagnostics dicts already built '
           'at evaluation_manager.py:159-165 and 514, add a "Majority Baseline" '
           'column (and a "beats baseline" flag) to filter_impact_table, and in '
           'filter_impact_plot draw a labelled dashed line at `majority_rate - '
           'baseline_scores[0]` when the metric is an accuracy, so the deviation '
           'chart shows where the no-skill level falls. Promote macro-F1 or balanced '
           'accuracy to the headline metric for mortality.'),
    verification=('On the mean-aggregation mortality figures the new reference '
                    'line must appear at +0.2166 relative to the raw CV baseline '
                    '(0.9034 − 0.6868) and at +0.1624 for the legacy artifacts '
                    "(0.9003 − 0.7410), i.e. above every bar; the table's new column "
                    'must read 0.9034 for the twelve full-size arms, 0.8057 for '
                    '"high invalid data", and the ICU version of the same table must '
                    'show every arm above its 0.6248 baseline.'),
    found='2026-08-11; prevalence verified from the sidecars',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C16',
        note=('Correction: the classifiers are NOT skill-less and the accuracy level '
             'itself is documented and deliberate '
             '(visualization_manager_v2.py:196-201, evaluation_manager.py:66-71) — '
             'raw mortality macro-F1 is 0.5542 against 0.4746 for the '
             'always-negative predictor. The reportable defect is narrower than the '
             'claim: an accuracy column that lies entirely below the 0.9034 '
             'majority-class rate is tabulated and plotted as the primary comparison '
             'with no reference line anywhere, and `filter_impact_plot` only ever '
             'shows deviation from the raw arm. Guardrail 5 is respected — the '
             'accuracy DROP is not treated as a regression. ICU is unaffected '
             '(0.616-0.696 vs a 0.6248 majority rate). Per-arm baselines differ '
             "where the arm drops records: 0.8057 for 'high invalid data', 0.8910 "
             "'long gap', 0.8983 'long missing segment'."),
    ),
),
dict(
    id='R-25', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name='Truncated bar axis exaggerates ratios',
    overview=('Bars encode magnitude by length, but the axis starts just below the '
                'minimum value.'),
    affects=('The three bar panels ("Accuracy", "F1 Score", "AUC-ROC") in cell 18 '
               "of comparison/pipeline_comparison.ipynb, i.e. the notebook's "
               'headline figure. Accuracy: MIMIC 0.9086 vs EHR 0.9124 on a `(0.8586, '
               '1.0)` axis renders as bar lengths 0.0500 vs 0.0538 — a 7.6% length '
               'ratio for a 0.4% score difference. AUC-ROC is worst, because its '
               'minimum (~0.48) sets a different, much lower baseline, so the same '
               'visual bar length means a different score in each panel and panels '
               'cannot be compared with each other. The summary dashboard in cell 33 '
               'is not affected (no `set_ylim`, so it starts at 0), which makes the '
               'two figures visually contradict each other.'),
    recompute=('Re-execute cell 18 of comparison/pipeline_comparison.ipynb. No '
                 'upstream recomputation.'),
    technical=('Cell 18 computes `_ymin = min(min(_mimic_scores[key]), '
                 'min(_ehr_scores[key]))` and applies `ax.set_ylim(max(0, _ymin - '
                 '0.05), 1.0)` (pipeline_comparison.ipynb:1119) inside the loop, so '
                 'each of the three axes gets its own truncated baseline; `max(0, '
                 '...)` only protects against negative limits, it does not anchor at '
                 'zero for any real score in this notebook. Because the marks are '
                 '`ax.bar` rectangles, the encoding channel is length from the axis '
                 'floor, and a non-zero floor breaks the proportionality the reader '
                 "assumes. The per-bar value labels (`ax.text(..., f'{h:.3f}')`, "
                 'cell 18 source line 29-30) mitigate this for a careful reader but '
                 'do not change the visual encoding, and the deviation heatmap '
                 'generated immediately below from the same '
                 '`_mimic_scores`/`_ehr_scores` (in % points) is the unaffected '
                 'quantitative view.\n'
                 '\n'
                 'First-pass measurements retained: For the AUC panel with values '
                 '0.4801-0.7045 the axis starts at 0.4301, making a 0.10 AUC gap '
                 'look like a 3x difference.'),
    fix=('Either anchor the bars at zero (`ax.set_ylim(0, 1.0)`) or switch the '
           'mark to a dot/dumbbell plot, which legitimately supports a truncated, '
           'zoomed axis. If a zoomed view is wanted, keep the zoom for a dot plot '
           'and leave the bar chart at zero.'),
    verification=('Re-run cell 18 and confirm each axis reports `ax.get_ylim()[0] '
                    '== 0` (or that the marks are no longer rectangles), and that '
                    'the visual height ratio between the MIMIC and EHR accuracy bars '
                    'matches 0.9086/0.9124 ≈ 0.996.'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C12',
        note=('No documentation anywhere claims the truncated axis is intended; the '
             'section markdown reads as if the bars are proportional. Severity '
             'suggestion: Low-Medium given the printed value labels and the correct '
             'accompanying heatmap.'),
    ),
),
dict(
    id='R-26', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name=('The cosmetic y-axis clamp the postmortem flagged is still in the paper '
            'path'),
    overview=('`filter_impact_plot` keeps its `min_range = 0.005` axis floor '
                'verbatim, and `render_paper_figures.fig_filter_impact` calls it '
                'without overriding it, so the construct POSTMORTEM.md §2.1 named as '
                'self-concealing is unchanged and live in the published path. What '
                'has not changed is the thing the postmortem actually asked for: '
                'nothing in the figure diagnoses a saturated metric — no '
                'majority-class rate, no threshold-free metric, no annotation when '
                "the whole spread is inside noise. The claim's mechanism is "
                'backwards, though: the clamp widens a would-be-tiny axis so small '
                'deltas look small, and on the current data it never even fires.'),
    affects=('All four paper_figures/filter_impact_*.pdf and the same plots in the '
               'notebook — not because the clamp fired (it did not; measured '
               'deviation ranges are 0.059 for both ICU metrics, 0.139 for mortality '
               'F1 and 0.294 for mortality accuracy, all far above 0.005, so the '
               '`else` branch at 282-284 ran) but because none of them carries a '
               'base-rate or effect-size reference, so a reader cannot tell a real '
               'filter effect from metric saturation. No cached number is wrong.'),
    recompute='Nothing — this is a plotting/annotation change only.',
    technical=('The floor lives in the signature default '
                 '(visualization_manager_v2.py:235) and the branch at 280-281, with '
                 'the rationale in the comment at 273-276 ("Without it, a run where '
                 'every filter does essentially nothing gets autoscaled down to a '
                 '±0.0001 range and the noise looks like a dramatic effect"), and '
                 'the phrase POSTMORTEM.md quotes is still in the docstring at '
                 "240-242. So the postmortem's target is textually intact and "
                 'reachable from `Experiments/render_paper_figures.py:314-331`, '
                 'which passes no `min_range`. Two corrections to the claim: (1) '
                 'direction — clamping to ±0.006 shrinks apparent bar height, it '
                 'does not flatten a real effect; the honest complaint is that '
                 'flatness is absorbed cosmetically rather than surfaced; (2) it is '
                 "currently inert — I computed every arm's deviation from "
                 'Data/mimic-iii/mean/{icu,mortality}_filter_impact.pkl and no '
                 "metric's range is below 0.005, so the clamp branch is dead for the "
                 'shipped figures. Partial mitigation already exists: `epsilon = '
                 '1e-3` greys bars inside noise (line 254). What is genuinely absent '
                 "is any of POSTMORTEM.md §2.1's remedies (majority-class line, "
                 'AUROC/AUPRC, prevalence caption) in this plot.'),
    fix=('Keep the floor but make it self-declaring: when `deviation_range < '
           'min_range`, stamp the axis with a note that the axis was clamped and the '
           'spread is within noise; and add a majority-class / no-effect reference '
           'annotation (prevalence is already in the `*_diagnostics.json` sidecars) '
           'to the filter-impact figures so accuracy deltas can be read against the '
           'base rate.'),
    verification=('Re-render with a synthetic all-zero-deviation score vector and '
                    'confirm the clamp note appears; re-render the real figures and '
                    'confirm the annotation shows test prevalence from the '
                    'diagnostics JSON and that the y-limits are unchanged (proving '
                    'the clamp is inert on this data).'),
    found='POSTMORTEM.md 2.1b, still live',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C14',
        note=('Correction: the clamp itself is internally consistent with its own '
             'comment (`render_paper_figures.py:273-276`), so guardrail 10 does not '
             'apply to the clamp; the open defect is the missing saturation '
             'diagnostic the postmortem asked for. The code is unchanged and '
             'reachable but cannot currently distort a published figure. Severity '
             'suggestion: Low.'),
    ),
),
dict(
    id='R-27', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name='A comment asserts split identity that is false three ways',
    overview=('It claims the two pipelines see identical splits because they share '
                'seed values.'),
    affects=('No stored number is wrong; the defect is the comment itself and any '
               'cross-notebook comparison a reader builds on it. It is adjacent to '
               "(but distinct from) the comparison notebook's own internal claim at "
               '`comparison/_gen_comparison_nb.py:34-36` — "Same classifier, same '
               'seeds, same splits" — which is true *within* that notebook, since '
               '`train_idx/test_idx` is drawn once per seed from `X_mimic` and '
               'reused for both arms.'),
    recompute='Nothing.',
    technical=('Three independent failures of the identity claim. (1) Different '
                 'splitter and RNG: the EHR path calls `torch.manual_seed(seed)` '
                 'then `DatasetEHR.split(0.8, 0.1, 0.1)`, which draws '
                 '`torch.randperm(len(self))` unstratified '
                 '(`Entities/ehr_dataset.py:75`, '
                 '`Managers/evaluation_manager.py:276-277`); the comparison path '
                 'calls `StratifiedShuffleSplit(n_splits=1, test_size=TEST_SIZE, '
                 "random_state=seed)` on numpy's RNG, stratified on `y_arr` "
                 '(`_gen_comparison_nb.py:610-611`). The same integer cannot yield '
                 'the same permutation across torch and numpy, and one is stratified '
                 'while the other is documented as not (`ehr_dataset.py:65-68`). (2) '
                 'Different geometry: 80/10/10 three-way with a strictly held-out '
                 'validation split versus a two-way 80/20 with `TEST_SIZE = 0.2` and '
                 'no validation split at all (`_gen_comparison_nb.py:98`). (3) '
                 'Different cohort and row space: the comparison notebook restricts '
                 'to the intersection with MIMIC_Extract — `"The two pipelines are '
                 'aligned on cohort (the ~27k hospital admissions both\\n"` '
                 '(`_gen_comparison_nb.py:34`) and `"ehr_records_shared = [r for r '
                 'in ehr_records if r.admission_id in shared_hadm_ids]\\n"` (`:487`) '
                 "— while the EHR pipeline's raw arm carries 46,032 records "
                 '(`rerun/verify_cv.py:34`), so index *i* is not the same admission '
                 'on the two sides. A fourth, weaker point: because `split` caches '
                 'on `split_weights` (`ehr_dataset.py:74`), seeds 985/439/81 reuse '
                 'seed 22\'s partition on the EHR side, so "these same four seeds" '
                 'produce one split there and four on the comparison side.\n'
                 '\n'
                 'First-pass measurements retained: The values match '
                 '_gen_comparison_nb.py:97, and nothing else does: here they feed '
                 "torch.manual_seed -> DatasetEHR.split's unseeded randperm over "
                 '46,032 records; there they feed '
                 'StratifiedShuffleSplit(random_state=seed) over 27,295.'),
    fix=('Replace the middle clause of the comment with what is actually true — '
           'the seeds are shared for bookkeeping only; the two pipelines split with '
           'different libraries, different geometry and different cohorts, so their '
           'per-record predictions are not paired and only within-pipeline deltas '
           'are comparable. Keep the "don\'t change them casually" sentence, which is '
           'accurate for cache compatibility.'),
    verification=('Read-only check that closes it: run each splitter on the same '
                    'length-N index and confirm the index sets differ '
                    '(`torch.manual_seed(22); torch.randperm(N)` vs '
                    '`StratifiedShuffleSplit(1, test_size=0.2, random_state=22)`), '
                    'and confirm `len(raw_dataset.data) == 46032` against the '
                    "comparison notebook's `len(shared_hadm_list)`. No job "
                    'submission is needed.'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C17',
        note=('Comment-only defect — no stored number is wrong. Distinct from the '
             "comparison notebook's own internal 'same classifier, same seeds, same "
             "splits' claim, which is TRUE within that notebook. Three independent "
             'failures of the cross-pipeline identity claim (different RNG+splitter, '
             '80/10/10 vs 80/20 geometry, and a ~27k intersected cohort vs 46,032 '
             'records), plus a fourth: because `split` caches on `split_weights`, '
             "seeds 985/439/81 reuse seed 22's partition on the EHR side, so the "
             'four seeds produce one split there and four on the comparison side. '
             'Not the guardrail-6 settled item.'),
    ),
),
dict(
    id='R-28', stage=REPORT, severity=MEDIUM, status=OPEN, verified=True,
    name='icustay_id is used as a recency key',
    overview=('The join step sorts on `icustay_id` and keeps the last row per '
                '`hadm_id`, and both the live notebook markdown and the generator '
                'gloss this as "the most recent stay". `icustay_id` is a MIMIC-III '
                'ETL surrogate key with no guaranteed chronological ordering — '
                '`intime` is the only recency field in the table — so the label is '
                'wrong; the correction is that on the artifact the notebook actually '
                'loads, `baseline_nofilters/all_hourly_data.h5`, no `hadm_id` has '
                'more than one `icustay_id`, so the line is a no-op and no published '
                'number depends on it.'),
    affects=('No numbers. The claim "most recent stay" in the Load & Join Data '
               'markdown (JSON:540) is unsupported documentation. The latent risk is '
               'real for any future scenario HDF whose extractor keeps multiple ICU '
               "stays per admission, and for the toolbox README's separate, "
               'correctly documented caveat that the two pipelines anchor hour 0 '
               'differently (ICU admission vs hospital admission) — under multi-stay '
               "admissions the arbitrary pick would silently decide which stay's 24 "
               'hours the MIMIC side describes.'),
    recompute='Nothing.',
    technical=('comparison/pipeline_comparison.ipynb cell 4 (JSON:~600) sets '
                 '`MIMIC_HDF = '
                 "Path('../pipelines/MIMIC_Extract/data/curated/baseline_nofilters/all"
                 "_hourly_data.h5')`; cell 10 (JSON:634-636) builds `mimic_idx` from "
                 '`mimic_patients.index.to_frame(index=False)`, filters to '
                 '`shared_hadm_ids`, then '
                 "`sort_values('icustay_id').drop_duplicates('hadm_id', "
                 "keep='last')`. Reading key `patients` from that HDF with the "
                 "repo's own .venv_stats interpreter gives 34,472 rows on index "
                 "`['subject_id','hadm_id','icustay_id']` and zero `hadm_id`s "
                 'appearing more than once, so `drop_duplicates` removes nothing and '
                 'the icustay ordering is never exercised; the table does carry '
                 '`intime`/`outtime` columns, which is what a genuine recency key '
                 "would use. The generator's markdown "
                 '(comparison/_gen_comparison_nb.py:442-444) is more honest than the '
                 'live notebook\'s — it says "Arbitrary but consistent" and warns '
                 'that for readmitted patients the pipelines would describe '
                 'different stays — but it still asserts "i.e. the most recent '
                 'stay", so the wrong equivalence is documented in both places.'),
    fix=('Two lines of hardening, both cheap: sort on `intime` (available in '
           '`patients`) rather than `icustay_id` if a specific stay is wanted, or '
           'make the arbitrariness explicit and loud — keep the deterministic '
           '`icustay_id` pick but assert/report the number of collapsed rows '
           "(`n_multi = idx['hadm_id'].duplicated().sum()`) so a future scenario "
           'file that does contain multi-stay admissions cannot pass silently. '
           'Correct the markdown at JSON:540 to drop "most recent stay".'),
    verification=('Print `n_multi` in cell 10 and confirm it is 0 for '
                    '`baseline_nofilters`; on a synthetic or scenario file where it '
                    'is non-zero, assert that the retained `icustay_id` is the one '
                    'with the maximum `intime` (which the current code does not '
                    'guarantee) and that the printed cohort size is unchanged for '
                    "the current artifact (27,295 records, per cell 10's stored "
                    'output "Final aligned cohort").'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C11',
        note=('Correction: on the artifact the notebook actually loads '
             '(`baseline_nofilters/all_hourly_data.h5`) no `hadm_id` has more than '
             'one `icustay_id`, so the dedup line is a no-op — 0 of 34,472 rows '
             'affected and no published number depends on it. Not an artifact: the '
             'misdescribed key is live in code and markdown. Severity suggestion: '
             'Low.'),
    ),
),
dict(
    id='R-29', stage=REPORT, severity=LOW, status=OPEN, verified=True,
    name='Legend is built from the first panel only',
    overview=('`centroid_plot` attaches a legend label only on the first panel '
                '(`label=categories[g] if i == 0`) and builds the figure legend '
                'purely from `axes[0]`, while the per-group `values.size == 0: '
                'continue` guard can skip a group on that panel alone. A group whose '
                'first vital is entirely NaN is then drawn in the remaining six '
                'panels with no legend entry and no colour key. '
                '`render_paper_figures.fig_centroid_density_raw` inherits the flaw '
                'exactly, since it re-harvests handles from `fig.axes[0]` before '
                'rebuilding the legend in the blank panel.'),
    affects=('Nothing currently published. Correction to the claim: I checked '
               'every centroids/*.pkl under Data/mimic-iii/{mean,median,standard '
               'deviation,mean deviation,maximum deviation} and no group has an '
               'all-NaN vital column, so no shipped figure is missing a legend entry '
               '— the four-group paper figure '
               '(paper_figures/centroid_density_raw_mimic_iii*.pdf) is complete. The '
               "defect is latent and would bite the notebook's eight-group "
               'raw-vs-filtered panels (Experiments/notebook.py:825-845) first.'),
    recompute='Nothing.',
    technical=('In the group loop, `values = group_points[:, i]`, then '
                 '`distances`/`limit`, then `values = values[distances <= limit]` '
                 '(visualization_manager_v2.py:508-516); `np.nanpercentile` of an '
                 'all-NaN column returns NaN, every `distances <= NaN` comparison is '
                 'False, so `values.size == 0` and line 519 `continue`s before both '
                 '`fill_betweenx` (531) and the labelled marker (539-543). Because '
                 'the label is only requested when `i == 0` (543) and the figure '
                 'legend is assembled from `axes[0]` alone (555-559), a group '
                 'skipped on panel 0 has no artist carrying its label anywhere, yet '
                 'it is drawn normally for `i >= 1`. render_paper_figures.py:248-255 '
                 "removes centroid_plot's figure legend and rebuilds it from the "
                 'same `fig.axes[0]` handles, so the paper path has the identical '
                 'single-panel dependency. Two things I verified that bound the '
                 'claim: (a) no current artifact triggers it — the only degenerate '
                 'groups on disk are fully empty point lists (`standard deviation`, '
                 '`mean deviation`, `maximum deviation` × `*_high invalid '
                 'data_{pos,neg}.pkl`), and an empty list is `np.asarray([])` with '
                 'ndim 1, so `group_points[:, i]` raises IndexError rather than '
                 'skipping a panel, i.e. that case crashes the figure instead of '
                 'silently dropping a legend entry; (b) the `continue` also skips '
                 'the per-panel cosmetic block (545-553), so a panel where every '
                 'group were skipped would keep default ticks and no title.'),
    fix=('Collect handles/labels across all panels (or register one proxy artist '
           'per group before the panel loop, independent of data availability) and '
           'build the figure legend from that union; in the paper renderer, harvest '
           'handles from all `fig.axes` rather than `fig.axes[0]`. Separately, guard '
           '`np.asarray(points[g])` for the empty-group case so a zero-record arm '
           'degrades to a skipped group instead of an IndexError.'),
    verification=("Force a group's first vital to all-NaN in a scratch call and "
                    'confirm the legend still lists every category with the right '
                    "colour and that the group's markers appear in later panels; "
                    'separately pass an empty points list and confirm it renders '
                    'with that group omitted rather than raising.'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C14',
        note=('Latent: the mechanism is real in current code but unreachable with the '
             'data on disk, so no published figure is wrong. The related empty-arm '
             "IndexError (deviation aggregations x 'high invalid data') is a "
             'distinct issue, masked in the notebook by its `attempt(...)` wrapper.'),
    ),
),
dict(
    id='R-30', stage=REPORT, severity=LOW, status=OPEN, verified=True,
    name='Vital ranges in the paper renderer diverge from the pipeline',
    overview=('render_paper_figures.py:77 announces "Constants mirrored from '
                'notebook.py", yet its ranges are '
                '(1,600)/(1,400)/(1,300)/(1,300)/(1,70)/(21,50)/(1,100) where '
                'notebook.py:219-224 and the gallery renderer both use '
                '(1,599)/(1,399)/(1,299)/(1,299)/(1,69)/(21,49)/(1,99). The bounds '
                'are inert in the paper renderer — only `VITAL_NAMES` and '
                '`VITAL_UNITS` are consumed — so no published figure is currently '
                'wrong, but the file is a trap: the same dict in notebook.py is the '
                'actual valid-range argument to the vital range filters.'),
    affects=('Nothing rendered today. render_paper_figures.py reads only '
               '`VITAL_NAMES`/`VITAL_UNITS` (built at :90-91, used at :242 and '
               ':307), so paper_figures/*.pdf are unaffected. The risk is latent: '
               'any future use of `VITALS[...][0]` in this file — e.g. drawing range '
               'cut-offs onto the ECDF or centroid panels — would apply seven bounds '
               "one unit wider than the pipeline's."),
    recompute='Nothing.',
    technical=('notebook.py:218-226 defines `VITALS` with inclusive upper bounds '
                 'one below the round number and passes the whole dict into '
                 '`create_filter_dataset(...)` at notebook.py:411, so those numbers '
                 'are load-bearing for the per-vital "high invalid data"/range '
                 'filters. gallery/render_marimo_mimic_iii.py:108-116 copies them '
                 'exactly and documents the copy-drift risk at :13-15 ("The '
                 'constants below (VITALS, FILTER_NAMES, AGGREGATION_METHODS) are '
                 'copied from notebook.py ... and drift the same way"). '
                 'render_paper_figures.py:81-89 has the same seven keys and units '
                 'but every upper bound raised by one, under a header asserting it '
                 'mirrors notebook.py. I grepped render_paper_figures.py for '
                 '`VITALS`: the only hits are the definition (:81) and the two '
                 'derived name/unit lists (:90-91), consumed at :242 '
                 '(`centroid_plot(..., VITAL_NAMES, VITAL_UNITS, ...)`) and :307 '
                 '(`centroid_shift_plot(cp, cats, filter_name, VITAL_NAMES, ...)`), '
                 'plus a separate hard-coded `ECDF_VITALS` list at :403 that carries '
                 'its own names/units and indices. So the divergence is currently '
                 'dead code. The `FILTER_NAMES` and `LENGTH_METHODS` constants in '
                 'the same block do match notebook.py.'),
    fix=('Either replace the ranges in render_paper_figures.py:81-89 with '
           "notebook.py's values, or delete the range element entirely and keep "
           '`VITALS = {name: unit}` since only units are used — the latter removes '
           'the drift surface. Best: import the dict from one shared module so '
           'notebook.py, render_marimo_mimic_iii.py and render_paper_figures.py '
           'cannot disagree.'),
    verification=('`diff` the three VITALS blocks (or assert equality in a '
                    'one-line check that imports both) and confirm the paper figures '
                    'are byte-identical before and after the change, proving the '
                    'bounds were unused.'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C15',
        note=('Correction: the divergent ranges are never read, so no number in '
             "`paper_figures/` changes — this is latent drift plus a false 'mirrors "
             "notebook.py' comment. The two files otherwise differ only in "
             'whitespace, so the one-unit shift is the sole substantive difference.'),
    ),
),
dict(
    id='R-31', stage=REPORT, severity=LOW, status=OPEN, verified=True,
    name='Unlabelled colorbar over a varying denominator',
    overview=('`heatmap()` attaches a bare colorbar '
                '(visualization_manager_v2.py:181, no `label=` and none added by '
                "`finalize`), so the paper figure's magnitude scale carries no units "
                'even though the quantity is "mean number of charted measurements '
                'per record per hour". The per-hour mean is taken over every record '
                'in the pickle (`groupby(level=0).agg("mean")`, '
                'render_paper_figures.py:286) — including admissions discharged or '
                'deceased before hour 23, which contribute rows of zeros because '
                "every record is reindexed to all 24 hours — so hour 23's value is "
                "not comparable to hour 0's without stating the at-risk population."),
    affects=('paper_figures/observation_count_heatmap_raw_mimic_iii.pdf and the '
               'equivalent gallery figures (render_marimo_mimic_iii.py:300-304). '
               'pdftotext of the PDF shows a colorbar with bare ticks '
               '0.4/0.6/0.8/1.0 and cell values like heart rate 0.744 at hour 0 '
               'rising to 1.125 at hour 6-7 and falling to 0.975 at hour 23; a '
               'reader cannot tell those are measurements per admission per hour, '
               'nor that the hour-23 figure averages over admissions that were no '
               'longer being charted.'),
    recompute=('Just this figure '
                 '(render_paper_figures.fig_observation_count_heatmap) and gallery '
                 'Section A; no cached results or model numbers depend on it.'),
    technical=('render_paper_figures.py:272-286 builds one 24×7 count frame per '
                 'record and averages by hour index; because '
                 'mimic-iii-processing.py:116 reindexes every record to `range(24)` '
                 'with `fill_value=[]`, all records contribute all 24 rows, so the '
                 'denominator is constant (the number of successfully mapped '
                 'records) rather than shrinking. What varies is the composition of '
                 'the numerator: a patient discharged at hour 8 contributes zeros '
                 'for hours 9-23, so later-hour means mix "charted rarely" with "no '
                 'longer present". The `.map` in the same block silently drops any '
                 'record that raises (`except Exception: pass`, :279-280), so the '
                 'denominator is also not necessarily the full cohort and is never '
                 'printed. On the colour scale, `heatmap()` '
                 '(visualization_manager_v2.py:132-183) creates the colorbar at :181 '
                 'with no `label`, and render_paper_figures.py:292-293 passes only '
                 'text/size options to `finalize`, so nothing later supplies units; '
                 'the y-axis is likewise just `"Hour"` with no anchor event (which '
                 'ties into the hospital-admission-vs-ICU-stay issue in R-08). '
                 'Values are annotated per cell at `value_format=".3f"`, which '
                 'mitigates but does not remove the ambiguity.'),
    fix=('Pass a colorbar label through `heatmap()` (add a `colour_bar_label` '
           'argument used at visualization_manager_v2.py:181, e.g. "mean '
           'measurements per admission per hour") and set it from '
           'render_paper_figures.py:288; label the y-axis "Hour since hospital '
           'admission"; and either restrict the mean to records still present in '
           'that hour (dividing by an at-risk count) or state the constant '
           'denominator N in the caption and note that discharged admissions '
           'contribute zeros. Also count and report the records skipped by the bare '
           '`except` at :279-280 instead of discarding them silently.'),
    verification=('Re-render and confirm the colorbar has a units label and the '
                    'caption states N; compute the per-hour at-risk count alongside '
                    'the current mean and confirm the two curves diverge in the '
                    'later hours (which is the quantitative statement of the '
                    'dilution), and check that the reported N equals `len(records)` '
                    'minus the newly logged skip count.'),
    found='2026-08-11 reporting audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C15',
        note=('Corrections: the denominator does not shrink and the record set is not '
             're-selected per hour — reindexing to all 24 hours '
             '(`mimic-iii-processing.py:116`) makes it constant. The real defect is '
             'that the constant denominator includes records that had already ended, '
             'plus the silently dropped records at '
             '`render_paper_figures.py:279-280`. The unlabelled colorbar is '
             'confirmed outright, in the shared plotting function. Dilution '
             'magnitude is inferred from the code path, not measured (no pandas on '
             'the node).'),
    ),
),
dict(
    id='R-32', stage=REPORT, severity=LOW, status=OPEN, verified=True,
    name='The FILTERS table exists in four copies and one is incomplete',
    overview=('The filter roster is duplicated in several places and the one in '
                "`Managers/ehr_filter_manager.py` — the copy the README's "
                "prerequisite script imports — has 11 entries and no `'all vitals'`. "
                '`rerun/regen_filter_impact_cv.py:88` iterates the 12-entry '
                '`_common.FILTERS` and calls `DatasetEHR.load`, which raises on a '
                'missing file, so on any dataset/aggregation built solely by the '
                'documented path stage F dies on the all-vitals arm. Worse, naively '
                "appending `'all vitals'` to the canonical table would not fix it, "
                'because `apply_dataset_filter.py:61` decides `pre_aggregate` by '
                'position (`k < 7`), giving the 12th entry `False` where the '
                'notebook has `True`.'),
    affects=('Nothing currently on disk is wrong — I checked all five aggregation '
               'directories under `Data/mimic-iii/` and each holds 12 '
               '`*_filtered_dataset_ehr.pkl` files including '
               '`all_vitals_filtered_dataset_ehr.pkl` (built 2026-03-30/04-21, i.e. '
               'by the notebook cell at `Experiments/notebook.py:401-411`, which '
               'iterates its own 12-entry table). The defect is latent: it bites on '
               "a new dataset, a new aggregation, or any rebuild after the README's "
               '"delete the directory by hand" cache-invalidation advice. The prose '
               'is also inconsistent — `README.md` says "Eleven filters" and "the '
               'first seven entries run before aggregation while the last four run '
               'after", while `/home/ccampb47/work/noahNotes.md:420` documents an '
               'eighth value-level filter, `All vitals`.'),
    recompute=('Nothing today. If a rebuild is ever triggered, the all-vitals arm '
                 'for the affected aggregation must be regenerated before '
                 '`rerun/job_f_filter_impact_cv.sh` and before '
                 '`rerun/regen_admission_ids.py` for that arm.'),
    technical=('Live in-repo copies of the roster that I read: '
                 '`Managers/ehr_filter_manager.py:405-417` (11 entries, '
                 'name→function, no flags), `Experiments/notebook.py:352-365` (12 '
                 "entries, name→(function, pre_aggregate), `'all vitals': "
                 '(all_vitals_filter, True)`), `rerun/_common.py:55-68` (12 entries, '
                 'flagged, self-described at `:6-8` as copied from the notebook '
                 'because `ehr_filter_manager.FILTERS` "omits \'all vitals\' and '
                 'carries no pre_aggregate flags"), and '
                 '`Experiments/render_paper_figures.py:94-99` (`FILTER_NAMES`, 12 '
                 'names). Consumers: `apply_dataset_filter.py:15` imports the '
                 '11-entry one and loops it at `:50`; `regen_filter_impact_cv.py:88` '
                 'and `:118` iterate the 12-entry one and `load_arm` (`:51-53`) '
                 'calls `DatasetEHR.load`, which raises `FileNotFoundError(f"Dataset '
                 'file \'{file_path}\' not found.")` '
                 '(`Entities/ehr_dataset.py:102-103`). `README.md` prescribes '
                 '`python Experiments/apply_dataset_filter.py mimic-iii mean` as the '
                 'build step. The positional `pre_aggregate` rule is documented as a '
                 'known hazard in `README.md` ("the boundary is a *position*, not a '
                 'property of the filter") and in `apply_dataset_filter.py:56-60`, '
                 'and `notebook.py` stores the flag explicitly for exactly this '
                 'reason.'),
    fix=('Move the flagged 12-entry table into `Managers/ehr_filter_manager.py` as '
           'the single definition (`name -> (function, pre_aggregate)`), have '
           '`notebook.py`, `_common.py`, `render_paper_figures.py` and '
           '`apply_dataset_filter.py` import it, and replace '
           "`apply_dataset_filter.py:61`'s `k < 7` with the table's flag so position "
           'stops being load-bearing. Correct `README.md`\'s "Eleven filters"/"last '
           'four" wording to twelve/five-plus-all-vitals.'),
    verification=('With the shared table in place, assert `set(_common.FILTERS) == '
                    'set(ehr_filter_manager.FILTERS) == set(notebook FILTERS)` and '
                    'that every flag matches. End to end: for one aggregation, '
                    'delete only `all_vitals_filtered_dataset_ehr.pkl` into a '
                    'scratch location, re-run `apply_dataset_filter.py` for that '
                    'aggregation, and confirm it is rebuilt with '
                    '`pre_aggregate=True` and that its record count matches the '
                    'existing artifact (46,032 for a non-record-dropping arm, per '
                    '`rerun/verify_cv.py:33-37`).'),
    found='2026-08-11 pipeline trace',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C17',
        note=("Corrections: (a) 'four copies' is a floor for live code, not an exact "
             'count — four in-repo plus '
             '`gallery/scripts/assign_ehr_metadata.py:45-57` and '
             '`gallery/render_marimo_mimic_iii.py:130`, with one more in the '
             'deprecated `_recompute_centroids_cpu.py:73` that guardrail 8 excludes; '
             '(b) present impact is nil — all five aggregation directories already '
             'hold 12 filtered pickles including '
             '`all_vitals_filtered_dataset_ehr.pkl`, so the shipped CV run was not '
             'affected; the defect bites on a new dataset/aggregation or after the '
             "README's 'delete the directory by hand' advice; (c) an addition to the "
             'claim — the obvious one-line fix is wrong, because '
             '`apply_dataset_filter.py:61` decides `pre_aggregate` by position (`k < '
             "7`), so appending 'all vitals' as the 12th entry would build it with "
             'the wrong flag.'),
    ),
),
dict(
    id='R-33', stage=REPORT, severity=LOW, status=OPEN, verified=True,
    name='Loaders return None instead of raising',
    overview=('`load_data` returns `None` for any extension that is not '
                '`.pkl`/`.feather`, `save_data` silently no-ops on the same '
                'condition, and `load_object` returns `None` for a missing path. In '
                'the notebook the same fail-soft posture appears as an `if '
                'file_path.exists(): load ... else: compute` cache gate, so a typo '
                'anywhere in the dataset name, aggregation name or filename is read '
                'as a cache miss and triggers a full `evaluate_filter_impact` sweep '
                'whose output is then written back under the mistyped name. The '
                'failure is indistinguishable from a legitimate first run.'),
    affects=('No published number. The risk is wasted compute plus orphan '
               'artifacts under wrong filenames in `Data/<dataset>/<aggregation>/` '
               "and `.../centroids/`, and — via `save_data`'s silent no-op — a "
               '"successful" run that wrote nothing.'),
    recompute='Nothing.',
    technical=('`serialization_manager.py:22-30` dispatches on `file_path.suffix` '
                 'and falls through to `return None`; its own docstring at `:17-18` '
                 'calls this "a trap". `save_data:39-44` has no `else`, so an '
                 'unknown suffix writes nothing and returns `None` normally. '
                 '`load_object:52-57` returns `None` when the path is absent. In '
                 '`Experiments/notebook.py`, `get_filter_impact` builds `file_path` '
                 'by f-string from `PROJECT_ROOT`, `DATASET_NAME`, '
                 '`aggregation_method`, `label` and `IMPACT_SUFFIX` (`:573`), tests '
                 '`.exists()` (`:574`), and on a miss with the legacy `IMPACT_SUFFIX '
                 "= ''` runs `evaluate_filter_impact` over every arm and every seed "
                 '(`:586-592`) and then `save_object`s the result to the mistyped '
                 'path. `get_centroids` repeats the pattern at `:753-762`. '
                 "Correction to the claim's causal chain: at both `load_object` call "
                 'sites (`:575`, `:755`) the `None` return is unreachable because '
                 '`.exists()` is checked first — the silent recompute comes from the '
                 '`.exists()` gate, not from the `None`. Likewise `load_data` raises '
                 '`FileNotFoundError` from `open()` for a missing `.pkl`; only an '
                 '*extension* typo returns `None` (e.g. `notebook.py:245`, '
                 '`apply_dataset_filter.py:36`), and there the `None` propagates '
                 'until something unrelated fails. Note the notebook already '
                 'demonstrates the right shape for this: `:576-581` raises '
                 '`FileNotFoundError` rather than recomputing when `IMPACT_SUFFIX` '
                 'is non-empty, precisely because a silent fallback there "would be '
                 'invisible afterwards".'),
    fix=('Make the helpers raise: `load_data` should `raise '
           'ValueError(f"unsupported extension {suffix}")`, `save_data` likewise, '
           'and `load_object` should let `open()` raise (or take an explicit '
           '`default=` / `missing_ok=` parameter for callers that genuinely want a '
           'miss). For the cache gates, log the resolved path on a miss and gate the '
           'fallback compute behind an explicit `ALLOW_RECOMPUTE` flag, mirroring '
           'the guard already at `notebook.py:576-581`.'),
    verification=("Call `load_data('x.pkl2')` and `save_data(df, 'x.pkl2')` and "
                    'confirm both raise instead of returning `None`/no-op. Then set '
                    '`DATASET_NAME` to a deliberate typo in a scratch copy of the '
                    'notebook cell and confirm `get_filter_impact` raises '
                    'immediately rather than beginning a sweep — and that `Data/` '
                    'gains no new directory.'),
    found='2026-08-11 statistical audit',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED-WITH-CORRECTIONS', mode='cluster C17',
        note=('Correction to the causal chain: at both `load_object` call sites '
             '(notebook.py:575, :755) the None return is UNREACHABLE because '
             '`.exists()` is checked first — the silent recompute comes from the '
             '`.exists()` cache gate, not from the None. `load_data` raises '
             'FileNotFoundError for a missing .pkl; only an *extension* typo returns '
             'None. So these are two separate fail-soft sites, not one chain. Not '
             'INTENTIONAL under guardrail 10: serialization_manager.py:17-18 calls '
             "the behaviour 'a trap', and notebook.py:576-581 already raises rather "
             'than recomputing when IMPACT_SUFFIX is non-empty, which is the right '
             'shape argued against the rest.'),
    ),
),
dict(
    id='R-34', stage=REPORT, severity=LOW, status=OPEN, verified=True,
    name='The deprecation manifest misdates the sibling fix',
    overview=("It says the same bug was fixed 'a year earlier' in the sibling "
                'experiment; git says five days.'),
    affects=('`/home/ccampb47/work/clinical_preprocessing_toolbox/_deprecated/MANIFE'
               'ST.md` §8 ("Pre-split-fix artifacts — `pre_split_fix_2026-08-10/`"), '
               'line 201-202. No code or number depends on it; the defect is the '
               'documentation record itself.'),
    recompute='Nothing.',
    technical=('The substantive part of the claim checks out — '
                 '`hour_scaling_experiment/cpu_eval.py:65-73` is the v1 code with '
                 '`train_sub, val_sub, test_sub = dataset.split(0.8, 0.1, 0.1)` '
                 'followed by `x_test = np.vstack([x_test_part, '
                 'x_validation_part])`, the same shape as the block MANIFEST quotes '
                 'at `:189-192`; `v2/splits.py:26-31` is the fix, giving `val 10% '
                 'decision-threshold selection only (never touched by fitting)` and '
                 "naming v1's concatenation as the thing corrected. Only the date is "
                 'wrong. `v2/splits.py` first appears in `70787f6`, authored '
                 "2026-08-05 13:34:12 -0400, and the file's mtime on disk is "
                 '2026-08-05 12:39; `git log` for the whole '
                 '`hour_scaling_experiment` repository lists seven commits, all '
                 'dated 2026-08-05 or 2026-08-06, so no fix in that tree can be a '
                 'year old. MANIFEST itself dates the toolbox fix to 2026-08-10 '
                 '(`:198`) and its rerun job `19487956` to the same day '
                 '(`:204-205`), making the true interval five days. For context, the '
                 'consolidated toolbox repo has a single commit, `2d26d3b` dated '
                 '2026-08-06.'),
    fix=('Change "fixed a year earlier" to "fixed five days earlier (commit '
           '`70787f6`, 2026-08-05)" and keep the "the toolbox copy simply never '
           'received it" clause, which remains accurate for that window.'),
    verification=('`git -C /home/ccampb47/work/hour_scaling_experiment log '
                    "--date=iso --format='%h %ad %s' -- v2/splits.py` should agree "
                    'with whatever date the corrected sentence states; `git log '
                    '--reverse --date=short` confirms no earlier history exists to '
                    'support any larger gap.'),
    found='2026-08-11; verified against git',
    audit=dict(
        date='2026-08-12', verdict='CONFIRMED', mode='cluster C17',
        note=('Dated from git (permitted for a history question): `v2/splits.py` '
             'first appears in commit 70787f6, 2026-08-05 13:34:12 -0400, and the '
             'entire hour_scaling_experiment repository history spans only '
             '2026-08-05 to 2026-08-06 across 7 commits — so no fix there can be a '
             'year old. MANIFEST dates the toolbox fix to 2026-08-10, making the '
             'true interval five days. The substantive claim around it checks out '
             '(cpu_eval.py:65-73 is the v1 concatenation, v2/splits.py:26-31 the '
             'fix); only the date is wrong. Live documentation defect, not stale: '
             'guardrail 8 deprecates the code under `_deprecated/`, while guardrail '
             '9 makes MANIFEST.md an intent source.'),
    ),
),

]

# ─────────────────────────────────────────────────────────────────────────────
# Renderer
# ─────────────────────────────────────────────────────────────────────────────

SEV_ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3}
STAGE_ORDER = [INGEST, FILTER, EVAL, BACKEND, REPORT]

SEV_KEY = {CRITICAL: "crit", HIGH: "high", MEDIUM: "med", LOW: "low"}
STATUS_KEY = {
    RESOLVED: "resolved", PARTIAL: "partial", OPEN: "open",
    WONTFIX: "wontfix", INTRODUCED: "introduced", NEEDS_CHECK: "check",
    ARTIFACT: "artifact", INTENTIONAL: "intentional", STALE: "stale",
}


def esc(text: str) -> str:
    return html.escape(str(text))


def para(text: str) -> str:
    """Preformatted blocks stay preformatted; prose becomes paragraphs."""
    chunks = [c for c in str(text).split("\n\n") if c.strip()]
    out = []
    for chunk in chunks:
        if "\n" in chunk and any(
            line.startswith("  ") or "  " in line for line in chunk.split("\n")
        ):
            out.append(f"<pre>{esc(chunk)}</pre>")
        else:
            out.append(f"<p>{esc(chunk)}</p>")
    return "\n".join(out)


def build() -> str:
    bugs = sorted(BUGS, key=lambda b: (STAGE_ORDER.index(b["stage"]), SEV_ORDER[b["severity"]], b["id"]))

    counts = {}
    for b in BUGS:
        counts[b["severity"]] = counts.get(b["severity"], 0) + 1
    status_counts = {}
    for b in BUGS:
        status_counts[b["status"]] = status_counts.get(b["status"], 0) + 1

    rows = []
    for b in bugs:
        rows.append(f"""
      <tr class="row" data-sev="{SEV_KEY[b['severity']]}" data-status="{STATUS_KEY[b['status']]}"
          data-stage="{esc(b['stage'])}" data-text="{esc((b['id'] + ' ' + b['name'] + ' ' + b['overview']).lower())}">
        <td class="c-id"><a href="#{b['id']}">{b['id']}</a></td>
        <td class="c-name">{esc(b['name'])}
          {'<span class="vflag" title="Re-verified against artifacts on disk">verified</span>' if b.get('verified') else ''}
        </td>
        <td class="c-stage">{esc(b['stage'])}</td>
        <td><span class="sev sev-{SEV_KEY[b['severity']]}">{esc(b['severity'])}</span></td>
        <td><span class="st st-{STATUS_KEY[b['status']]}">{esc(b['status'])}</span></td>
      </tr>""")

    cards = []
    for b in bugs:
        meta = []
        if b.get("found"):
            meta.append(f"<div><dt>Found</dt><dd>{esc(b['found'])}</dd></div>")
        if b.get("fixed"):
            meta.append(f"<div><dt>Fixed</dt><dd>{esc(b['fixed'])}</dd></div>")
        if b.get("audit"):
            a = b["audit"]
            meta.append(
                f"<div><dt>Second pass</dt><dd>{esc(a['date'])} — "
                f"{esc(a['verdict'])} ({esc(a['mode'])}). {esc(a.get('note', ''))}</dd></div>"
            )
        cards.append(f"""
    <article class="card sevbar-{SEV_KEY[b['severity']]}" id="{b['id']}"
             data-sev="{SEV_KEY[b['severity']]}" data-status="{STATUS_KEY[b['status']]}"
             data-stage="{esc(b['stage'])}"
             data-text="{esc((b['id'] + ' ' + b['name'] + ' ' + b['overview']).lower())}">
      <header class="card-head">
        <div class="card-id">{b['id']}</div>
        <h3>{esc(b['name'])}</h3>
        <div class="chips">
          <span class="sev sev-{SEV_KEY[b['severity']]}">{esc(b['severity'])}</span>
          <span class="st st-{STATUS_KEY[b['status']]}">{esc(b['status'])}</span>
          <span class="stage-chip">{esc(b['stage'])}</span>
          {'<span class="vflag">verified on disk</span>' if b.get('verified') else '<span class="vflag vflag-off">reported, unverified</span>'}
        </div>
      </header>
      <p class="lede">{esc(b['overview'])}</p>
      <div class="grid2">
        <section><h4>Affects</h4>{para(b['affects'])}</section>
        <section><h4>Recompute</h4>{para(b['recompute'])}</section>
      </div>
      <section><h4>Technical detail</h4>{para(b['technical'])}</section>
      <div class="grid2">
        <section><h4>Fix</h4>{para(b['fix'])}</section>
        <section><h4>Verification</h4>{para(b['verification'])}</section>
      </div>
      <dl class="meta">{''.join(meta)}</dl>
    </article>""")

    stat = lambda label, n, cls: (
        f'<div class="stat {cls}"><span class="n">{n}</span><span class="l">{label}</span></div>'
    )

    return f"""<title>Bug register — clinical preprocessing toolbox</title>
<style>
:root {{
  --ground:#f6f8fa; --surface:#ffffff; --surface-2:#eef1f5;
  --ink:#141920; --ink-2:#3d4757; --muted:#5c6675; --rule:#dce2e9;
  --accent:#1f6f8b; --accent-soft:#e4eef2;
  --crit:#b0261c; --high:#a8580c; --med:#7e6b1c; --low:#586274;
  --crit-bg:#fbeceb; --high-bg:#fbf1e6; --med-bg:#f7f4e6; --low-bg:#eef0f3;
  --resolved:#2c6a4e; --resolved-bg:#e7f1eb;
  --introduced:#5a4b8c; --introduced-bg:#eeebf6;
  --open-c:#8c2f28; --open-bg:#f9ecea;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --ground:#0f1319; --surface:#161c24; --surface-2:#1d242e;
    --ink:#e7ecf2; --ink-2:#c0c9d4; --muted:#8b96a5; --rule:#2a323d;
    --accent:#6fb6cf; --accent-soft:#17313b;
    --crit:#f08b80; --high:#e0a86a; --med:#ccbb66; --low:#9aa5b4;
    --crit-bg:#2e1a18; --high-bg:#2c2318; --med-bg:#282417; --low-bg:#1e242c;
    --resolved:#7dc9a2; --resolved-bg:#16281f;
    --introduced:#b3a4e0; --introduced-bg:#221d33;
    --open-c:#e59289; --open-bg:#2c1a18;
  }}
}}
:root[data-theme="dark"] {{
  --ground:#0f1319; --surface:#161c24; --surface-2:#1d242e;
  --ink:#e7ecf2; --ink-2:#c0c9d4; --muted:#8b96a5; --rule:#2a323d;
  --accent:#6fb6cf; --accent-soft:#17313b;
  --crit:#f08b80; --high:#e0a86a; --med:#ccbb66; --low:#9aa5b4;
  --crit-bg:#2e1a18; --high-bg:#2c2318; --med-bg:#282417; --low-bg:#1e242c;
  --resolved:#7dc9a2; --resolved-bg:#16281f;
  --introduced:#b3a4e0; --introduced-bg:#221d33;
  --open-c:#e59289; --open-bg:#2c1a18;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
  font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1180px;margin:0 auto;padding:48px 24px 96px;display:flex;flex-direction:column;gap:40px}}
header.top{{display:flex;flex-direction:column;gap:14px;border-bottom:2px solid var(--ink);padding-bottom:24px}}
.eyebrow{{font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}}
h1{{margin:0;font-size:clamp(30px,4vw,44px);line-height:1.1;letter-spacing:-.02em;text-wrap:balance;font-weight:640}}
.sub{{margin:0;color:var(--muted);max-width:66ch}}
.stats{{display:flex;flex-wrap:wrap;gap:10px;margin-top:6px}}
.stat{{display:flex;align-items:baseline;gap:8px;padding:8px 14px;border:1px solid var(--rule);
  background:var(--surface);border-radius:2px}}
.stat .n{{font-family:var(--mono);font-size:19px;font-weight:600;font-variant-numeric:tabular-nums}}
.stat .l{{font-size:12.5px;color:var(--muted);letter-spacing:.03em}}
.stat.s-crit .n{{color:var(--crit)}} .stat.s-high .n{{color:var(--high)}}
.stat.s-res .n{{color:var(--resolved)}} .stat.s-int .n{{color:var(--introduced)}}
.callout{{background:var(--surface);border:1px solid var(--rule);border-left:4px solid var(--crit);
  padding:24px 26px;display:flex;flex-direction:column;gap:12px}}
.callout h2{{margin:0;font-size:20px;letter-spacing:-.01em}}
.callout p{{margin:0;max-width:74ch}}
.tblwrap{{overflow-x:auto;border:1px solid var(--rule);background:var(--surface)}}
table{{border-collapse:collapse;width:100%;min-width:820px;font-size:14.5px}}
thead th{{position:sticky;top:0;background:var(--surface-2);text-align:left;padding:11px 14px;
  font-size:11.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);
  border-bottom:1px solid var(--rule);z-index:2}}
tbody td{{padding:11px 14px;border-bottom:1px solid var(--rule);vertical-align:top}}
tbody tr:hover{{background:var(--surface-2)}}
.c-id{{font-family:var(--mono);font-size:13px;white-space:nowrap}}
.c-id a{{color:var(--accent);text-decoration:none;font-weight:600}}
.c-id a:hover,.c-id a:focus{{text-decoration:underline}}
.c-name{{max-width:52ch}}
.c-stage{{color:var(--muted);font-size:13px;white-space:nowrap}}
.sev,.st,.stage-chip,.vflag{{display:inline-block;font-family:var(--mono);font-size:11px;
  letter-spacing:.05em;padding:2px 8px;border-radius:2px;white-space:nowrap}}
.sev-crit{{background:var(--crit-bg);color:var(--crit)}} .sev-high{{background:var(--high-bg);color:var(--high)}}
.sev-med{{background:var(--med-bg);color:var(--med)}} .sev-low{{background:var(--low-bg);color:var(--low)}}
.st-resolved{{background:var(--resolved-bg);color:var(--resolved)}}
.st-introduced{{background:var(--introduced-bg);color:var(--introduced)}}
.st-open,.st-check{{background:var(--open-bg);color:var(--open-c)}}
.st-partial{{background:var(--high-bg);color:var(--high)}}
.st-wontfix{{background:var(--low-bg);color:var(--low)}}
.st-artifact,.st-stale{{background:var(--low-bg);color:var(--low)}}
.st-intentional{{background:var(--accent-soft);color:var(--accent)}}
.stage-chip{{background:var(--accent-soft);color:var(--accent)}}
.vflag{{background:transparent;border:1px solid var(--rule);color:var(--muted);font-size:10px}}
.vflag-off{{opacity:.65}}
.controls{{display:flex;flex-wrap:wrap;gap:10px;align-items:center}}
.controls input[type=search]{{flex:1;min-width:200px;padding:9px 12px;border:1px solid var(--rule);
  background:var(--surface);color:var(--ink);font-family:var(--sans);font-size:14px;border-radius:2px}}
.controls input:focus-visible,.fbtn:focus-visible,.c-id a:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
.fbtn{{font-family:var(--mono);font-size:12px;padding:7px 12px;border:1px solid var(--rule);
  background:var(--surface);color:var(--ink-2);cursor:pointer;border-radius:2px}}
.fbtn[aria-pressed="true"]{{background:var(--ink);color:var(--ground);border-color:var(--ink)}}
h2.section{{margin:16px 0 0;font-size:22px;letter-spacing:-.01em;padding-bottom:8px;border-bottom:1px solid var(--rule)}}
.cards{{display:flex;flex-direction:column;gap:20px}}
.card{{background:var(--surface);border:1px solid var(--rule);border-left:4px solid var(--rule);
  padding:24px 26px;display:flex;flex-direction:column;gap:16px;scroll-margin-top:20px}}
.sevbar-crit{{border-left-color:var(--crit)}} .sevbar-high{{border-left-color:var(--high)}}
.sevbar-med{{border-left-color:var(--med)}} .sevbar-low{{border-left-color:var(--low)}}
.card-head{{display:flex;flex-direction:column;gap:9px}}
.card-id{{font-family:var(--mono);font-size:12px;color:var(--muted);letter-spacing:.08em}}
.card h3{{margin:0;font-size:20px;line-height:1.25;letter-spacing:-.01em;text-wrap:balance}}
.chips{{display:flex;flex-wrap:wrap;gap:6px}}
.lede{{margin:0;font-size:16.5px;color:var(--ink-2);max-width:74ch}}
.card h4{{margin:0 0 6px;font-family:var(--mono);font-size:11px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--accent)}}
.card p{{margin:0 0 8px;max-width:78ch}}
.card p:last-child{{margin-bottom:0}}
.grid2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}}
pre{{margin:0 0 8px;background:var(--surface-2);border:1px solid var(--rule);padding:12px 14px;
  overflow-x:auto;font-family:var(--mono);font-size:12.5px;line-height:1.5;white-space:pre}}
dl.meta{{display:flex;flex-wrap:wrap;gap:20px;margin:0;padding-top:12px;border-top:1px solid var(--rule)}}
dl.meta div{{display:flex;gap:8px;align-items:baseline}}
dl.meta dt{{font-family:var(--mono);font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted)}}
dl.meta dd{{margin:0;font-size:13px;color:var(--ink-2)}}
.hidden{{display:none !important}}
footer{{color:var(--muted);font-size:13px;border-top:1px solid var(--rule);padding-top:20px;max-width:74ch}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important;transition:none!important}}}}
</style>

<div class="wrap">
  <header class="top">
    <div class="eyebrow">Clinical preprocessing toolbox · 2026-08-11</div>
    <h1>Bug register</h1>
    <p class="sub">Every defect found across four rounds of review, from the SQL extraction
    through to the published figures. Entries marked <em>verified on disk</em> were re-checked
    against artifacts rather than taken from a report.</p>
    <div class="stats">
      {stat("total", len(BUGS), "")}
      {stat("critical", counts.get(CRITICAL, 0), "s-crit")}
      {stat("high", counts.get(HIGH, 0), "s-high")}
      {stat("resolved", status_counts.get(RESOLVED, 0), "s-res")}
      {stat("introduced 2026-08-11", status_counts.get(INTRODUCED, 0), "s-int")}
    </div>
  </header>

  <div class="callout">
    <h2>Start here: the plotted result has the wrong sign</h2>
    <p>Each arm's accuracy is measured over the records that arm kept, so subtracting the
    baseline measures cohort difficulty rather than filter effect. Every record-dropping arm's
    bar points the wrong way — and sits beside a correctly paired significance test that says
    the opposite. The correct paired figures are already computed and written to the
    diagnostics sidecars; they were never surfaced into the tuple that gets plotted.
    See <a href="#N-01">N-01</a>, and <a href="#R-02">R-02</a> for the same mistake on the
    MIMIC_Extract side.</p>
  </div>

  <div class="controls">
    <input type="search" id="q" placeholder="Search the register…" aria-label="Search bugs">
    <button class="fbtn" data-f="sev" data-v="crit" aria-pressed="false">Critical</button>
    <button class="fbtn" data-f="sev" data-v="high" aria-pressed="false">High</button>
    <button class="fbtn" data-f="status" data-v="open" aria-pressed="false">Open</button>
    <button class="fbtn" data-f="status" data-v="introduced" aria-pressed="false">Introduced today</button>
    <button class="fbtn" data-f="status" data-v="resolved" aria-pressed="false">Resolved</button>
    <button class="fbtn" data-f="status" data-v="artifact" aria-pressed="false">Not a bug</button>
    <button class="fbtn" data-f="status" data-v="intentional" aria-pressed="false">Intentional</button>
    <button class="fbtn" data-f="status" data-v="stale" aria-pressed="false">Stale</button>
    <button class="fbtn" id="clear">Clear</button>
  </div>

  <div class="tblwrap">
    <table>
      <thead><tr><th>ID</th><th>Bug</th><th>Stage</th><th>Severity</th><th>Status</th></tr></thead>
      <tbody id="tbody">{''.join(rows)}</tbody>
    </table>
  </div>

  <h2 class="section">Detail</h2>
  <div class="cards" id="cards">{''.join(cards)}</div>

  <footer>Generated from <code>rerun/bug_register.py</code>, which is the single source for
  both the table and the detail cards. Regenerate rather than editing this page by hand.</footer>
</div>

<script>
(function () {{
  var filters = {{sev: null, status: null}};
  var q = document.getElementById('q');
  var items = Array.prototype.slice.call(document.querySelectorAll('.row, .card'));

  function apply() {{
    var term = (q.value || '').trim().toLowerCase();
    items.forEach(function (el) {{
      var ok = true;
      if (filters.sev && el.dataset.sev !== filters.sev) ok = false;
      if (filters.status && el.dataset.status !== filters.status) ok = false;
      if (ok && term && el.dataset.text.indexOf(term) === -1) ok = false;
      el.classList.toggle('hidden', !ok);
    }});
  }}

  document.querySelectorAll('.fbtn[data-f]').forEach(function (btn) {{
    btn.addEventListener('click', function () {{
      var f = btn.dataset.f, v = btn.dataset.v;
      var on = filters[f] === v;
      filters[f] = on ? null : v;
      document.querySelectorAll('.fbtn[data-f="' + f + '"]').forEach(function (b) {{
        b.setAttribute('aria-pressed', String(!on && b.dataset.v === v));
      }});
      apply();
    }});
  }});

  document.getElementById('clear').addEventListener('click', function () {{
    filters.sev = null; filters.status = null; q.value = '';
    document.querySelectorAll('.fbtn[data-f]').forEach(function (b) {{
      b.setAttribute('aria-pressed', 'false');
    }});
    apply();
  }});

  q.addEventListener('input', apply);
}})();
</script>
"""


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(build())
    print(f"wrote {OUT}  ({len(BUGS)} bugs)")
