"""One-shot patch script for `curated_mimic_iii_analysis_executed copy 2.ipynb`.

**Already applied — don't run this again.** It rewrites specific cells by
matching on their current content, so a second run against the patched notebook
either no-ops or clobbers later hand edits. It's kept as the record of what
changed and why, since several of these fixes altered published numbers. There's
a `.prepatch` backup beside the notebook if you need the before state.

Applies fixes for the eight issues identified in the code review:
  1. McNemar uses ground truth (correctness, not raw predictions).
  2. McNemar p-value pooled across seeds (no min-p).
  3. baseline_nofilters_fast guarded out of VARIANT_OBJS.
  4. All five aggregation methods are run (not just the first).
  5. Per-variant table reports baseline performance on the same intersection.
  6. Centroid shift uses globally-shared columns (no NaN->0 phantoms).
  7. ICU/mortality labels disambiguated in display titles.
  8. MultiIndex round-trip through train_test_split is normalized.
"""

import json
import shutil
from pathlib import Path

NB_PATH = Path(__file__).resolve().parent / "curated_mimic_iii_analysis_executed copy 2.ipynb"
BACKUP = NB_PATH.with_suffix(NB_PATH.suffix + ".prepatch")


# --- New cell sources ----------------------------------------------------

VARIANT_LOADER_SRC = '''def _pick_datafile(scenario_dir):
    candidates = ['all_hourly_data.h5', 'all_hourly_data_5000.h5', 'all_hourly_data_2000.h5']
    for c in candidates:
        fp = scenario_dir / c
        if fp.exists():
            return fp
    raise FileNotFoundError(f'No all_hourly_data*.h5 found in {scenario_dir}')

def load_curated_scenario(scenario_name, data_root=CURATED_ROOT, load_X=True):
    scenario_dir = data_root / scenario_name
    datafile = _pick_datafile(scenario_dir)

    X = None
    if load_X:
        X = pd.read_hdf(str(datafile), 'vitals_labs')

    patients = pd.read_hdf(str(datafile), 'patients')

    try:
        interventions = pd.read_hdf(str(datafile), 'interventions')
    except Exception:
        interventions = None

    return {
        'name': scenario_name,
        'X': X,
        'patients': patients,
        'interventions': interventions,
        'datafile': datafile,
    }

def maybe_sample_record_ids(patients_df, max_records):
    if max_records is None:
        return patients_df
    if len(patients_df) <= max_records:
        return patients_df
    return patients_df.sample(max_records, random_state=0)

def subset_X_by_patients(X, patients_df):
    """Return only time-series rows whose record-id tuple is in patients_df.

    `vitals_labs` is stored in fixed format so we cannot row-filter on read;
    we subset after read.
    """
    time_level = _get_time_level_name(X.index)
    rec_index = X.index.droplevel(time_level)
    keep = rec_index.isin(patients_df.index)
    return X[keep]

# Mirrors the convention used by Experiment_Statistics.ipynb: the "_fast"
# duplicate of baseline_nofilters must never appear as a variant being
# compared against the actual baseline.
EXCLUDED_EXPERIMENTS = {'baseline_nofilters_fast'}

VARIANT_OBJS = []
for s in SCENARIOS:
    if s in EXCLUDED_EXPERIMENTS:
        continue
    print('Loading patients only:', s)
    obj = load_curated_scenario(s, load_X=False)
    obj['patients'] = maybe_sample_record_ids(obj['patients'], MAX_RECORDS_PER_SCENARIO)
    VARIANT_OBJS.append(obj)

assert all(v['name'] not in EXCLUDED_EXPERIMENTS for v in VARIANT_OBJS)
print('Effective variants:', len(VARIANT_OBJS))
print('Loaded variants:', [v['name'] for v in VARIANT_OBJS])
'''


MCNEMAR_SRC = '''# Display labels disambiguating which mortality column drives each "label".
# The 'icu' key here means *ICU mortality* (`mort_icu`), not "was admitted to
# ICU"; the EHR-Dataset-Processing pipeline uses 'icu' for admission. Keep the
# dictionary keys as-is for downstream code, but render the longer name.
LABEL_DISPLAY = {
    'icu':       'mort_icu (ICU mortality)',
    'mortality': 'mort_hosp / hospital_expire_flag (hospital mortality)',
}


def mcnemar_counts(y_true, pred_a, pred_b):
    """Discordant cells of McNemar's classifier-comparison test.

    n01 = examples where classifier A is wrong AND B is correct.
    n10 = examples where classifier A is correct AND B is wrong.
    Concordant cells (both right or both wrong) are not informative under
    McNemar and are not returned.
    """
    y = np.asarray(y_true).astype(int)
    a_correct = np.asarray(pred_a).astype(int) == y
    b_correct = np.asarray(pred_b).astype(int) == y
    n01 = int(np.sum(~a_correct &  b_correct))
    n10 = int(np.sum( a_correct & ~b_correct))
    return n01, n10


def mcnemar_pooled(n01_total, n10_total):
    """Pool discordant counts across folds and return (stat, p).

    Uses the continuity-corrected statistic and an exact two-sided binomial
    p-value over the n01+n10 discordant pairs, which avoids the Type-I
    inflation of taking min-p across seeds.
    """
    n = n01_total + n10_total
    if n == 0:
        return 0.0, 1.0
    stat = (abs(n01_total - n10_total) - 1.0) ** 2 / n
    try:
        from scipy.stats import binom
        p_one = binom.cdf(min(n01_total, n10_total), n, 0.5)
        p = float(min(1.0, 2.0 * p_one))
    except Exception:
        p = float('nan')
    return float(stat), p


def impute_and_scale(X):
    X = X.replace([np.inf, -np.inf], np.nan)
    col_means = X.mean(axis=0, skipna=True).fillna(0.0)
    X = X.fillna(col_means).fillna(0.0)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X.values)
    return Xs, scaler, col_means


def _ensure_multiindex(arr, names):
    """train_test_split on a MultiIndex returns an object array of tuples on
    some pandas versions, which then no longer round-trips through
    `.intersection`. Force back to MultiIndex with the original level names.
    """
    if isinstance(arr, pd.MultiIndex):
        return arr
    return pd.MultiIndex.from_tuples([tuple(t) for t in arr], names=names)


def evaluate_for_method(method, target_label, max_variants=None):
    base_pat = maybe_sample_record_ids(BASELINE['patients'], MAX_RECORDS_PER_SCENARIO)
    y_base = _select_pos_label(base_pat, target_label)

    X_base_full = BASELINE['X']
    X_base_small = subset_X_by_patients(X_base_full, base_pat)
    X_base_agg = build_record_aggregated_features(X_base_small, method).loc[base_pat.index]
    base_cols = X_base_agg.columns

    raw_metrics = {'train_acc': [], 'test_acc': [], 'train_f1': [], 'test_f1': []}
    raw_preds_by_seed = {}
    raw_models_by_seed = {}

    idx = X_base_agg.index
    for seed in SEEDS:
        train_ids, test_ids = train_test_split(
            idx,
            test_size=TEST_SIZE,
            random_state=seed,
            stratify=y_base.loc[idx].values,
        )
        train_ids = _ensure_multiindex(train_ids, idx.names)
        test_ids  = _ensure_multiindex(test_ids,  idx.names)
        assert test_ids.intersection(idx).size == len(test_ids), \\
            'MultiIndex round-trip lost rows'

        X_tr = X_base_agg.loc[train_ids]
        X_te = X_base_agg.loc[test_ids]
        y_tr = y_base.loc[train_ids].values
        y_te = y_base.loc[test_ids].values

        if len(np.unique(y_tr)) < 2:
            continue

        X_trs, scaler, col_means = impute_and_scale(X_tr)
        X_te_filled = (X_te.replace([np.inf, -np.inf], np.nan)
                          .fillna(col_means).fillna(0.0))
        X_tes = scaler.transform(X_te_filled.values)

        clf = LogisticRegression(**MODEL_KWARGS)
        clf.fit(X_trs, y_tr)
        pred_tr = clf.predict(X_trs)
        pred_te = clf.predict(X_tes)

        raw_metrics['train_acc'].append(accuracy_score(y_tr, pred_tr))
        raw_metrics['test_acc'].append(accuracy_score(y_te, pred_te))
        raw_metrics['train_f1'].append(f1_score(y_tr, pred_tr, zero_division=0))
        raw_metrics['test_f1'].append(f1_score(y_te, pred_te, zero_division=0))

        raw_preds_by_seed[seed]  = (test_ids, pred_te, y_te)
        raw_models_by_seed[seed] = (clf, scaler, col_means, base_cols)

    results = {
        'raw': {
            'train_acc': float(np.mean(raw_metrics['train_acc'])),
            'test_acc':  float(np.mean(raw_metrics['test_acc'])),
            'train_f1':  float(np.mean(raw_metrics['train_f1'])),
            'test_f1':   float(np.mean(raw_metrics['test_f1'])),
            'baseline_acc_on_var_test': np.nan,
            'baseline_f1_on_var_test':  np.nan,
            'mcnemar': None,
        }
    }

    variants = VARIANT_OBJS if max_variants is None else VARIANT_OBJS[:max_variants]
    for v in variants:
        print(f'Evaluating variant={v["name"]} target={target_label} method={method}')
        v_pat = maybe_sample_record_ids(v['patients'], MAX_RECORDS_PER_SCENARIO)
        y_v = _select_pos_label(v_pat, target_label)

        X_v_full = v.get('X', None)
        if X_v_full is None:
            X_v_full = pd.read_hdf(str(v['datafile']), 'vitals_labs')
        X_v_small = subset_X_by_patients(X_v_full, v_pat)
        X_v_agg = build_record_aggregated_features(X_v_small, method).loc[v_pat.index]

        metrics = {'train_acc': [], 'test_acc': [], 'train_f1': [], 'test_f1': []}
        base_metrics_intersection = {'acc': [], 'f1': []}
        n01_total = 0
        n10_total = 0

        for seed in SEEDS:
            base_test_ids, _, _ = raw_preds_by_seed[seed]
            test_ids_v = v_pat.index.intersection(base_test_ids)
            if len(test_ids_v) < 10:
                continue
            train_ids_v = v_pat.index.difference(test_ids_v)
            if len(train_ids_v) < 10:
                continue

            X_tr = X_v_agg.loc[train_ids_v]
            X_te = X_v_agg.loc[test_ids_v]
            y_tr = y_v.loc[train_ids_v].values
            y_te = y_v.loc[test_ids_v].values

            if len(np.unique(y_tr)) < 2:
                continue

            X_trs, scaler, col_means = impute_and_scale(X_tr)
            X_te_filled = (X_te.replace([np.inf, -np.inf], np.nan)
                              .fillna(col_means).fillna(0.0))
            X_tes = scaler.transform(X_te_filled.values)

            clf = LogisticRegression(**MODEL_KWARGS)
            clf.fit(X_trs, y_tr)
            pred_tr = clf.predict(X_trs)
            pred_te_var = clf.predict(X_tes)

            metrics['train_acc'].append(accuracy_score(y_tr, pred_tr))
            metrics['test_acc'].append(accuracy_score(y_te, pred_te_var))
            metrics['train_f1'].append(f1_score(y_tr, pred_tr, zero_division=0))
            metrics['test_f1'].append(f1_score(y_te, pred_te_var, zero_division=0))

            # Replay the baseline classifier on the *same* test patients,
            # using baseline's feature schema and scaler. test_ids_v is
            # guaranteed a subset of X_base_agg.index because it was sliced
            # out of the baseline split.
            base_clf, base_scaler, base_col_means, base_schema_cols = raw_models_by_seed[seed]
            X_te_base = X_base_agg.loc[test_ids_v, base_schema_cols]
            X_te_base = (X_te_base.replace([np.inf, -np.inf], np.nan)
                                  .fillna(base_col_means).fillna(0.0))
            base_pred_on_v = base_clf.predict(base_scaler.transform(X_te_base.values))

            base_metrics_intersection['acc'].append(accuracy_score(y_te, base_pred_on_v))
            base_metrics_intersection['f1'].append(f1_score(y_te, base_pred_on_v, zero_division=0))

            n01, n10 = mcnemar_counts(y_te, base_pred_on_v, pred_te_var)
            n01_total += n01
            n10_total += n10

        if metrics['test_acc']:
            stat_pool, p_pool = mcnemar_pooled(n01_total, n10_total)
            mcnemar_entry = (stat_pool, p_pool, n01_total, n10_total)
        else:
            mcnemar_entry = (np.nan, np.nan, 0, 0)

        results[v['name']] = {
            'train_acc': float(np.mean(metrics['train_acc'])) if metrics['train_acc'] else np.nan,
            'test_acc':  float(np.mean(metrics['test_acc']))  if metrics['test_acc']  else np.nan,
            'train_f1':  float(np.mean(metrics['train_f1']))  if metrics['train_f1']  else np.nan,
            'test_f1':   float(np.mean(metrics['test_f1']))   if metrics['test_f1']   else np.nan,
            'baseline_acc_on_var_test': (
                float(np.mean(base_metrics_intersection['acc']))
                if base_metrics_intersection['acc'] else np.nan
            ),
            'baseline_f1_on_var_test': (
                float(np.mean(base_metrics_intersection['f1']))
                if base_metrics_intersection['f1'] else np.nan
            ),
            'mcnemar': mcnemar_entry,
        }

        try:
            del X_v_full, X_v_small, X_v_agg
        except Exception:
            pass

    return results


def show_results(results_dict, target_label, method):
    names = ['raw'] + [n for n in results_dict.keys() if n != 'raw']
    rows = []
    for name in names:
        r = results_dict[name]
        if name == 'raw' or r['mcnemar'] is None:
            m_str = 'baseline reference'
        else:
            stat, p, n01, n10 = r['mcnemar']
            m_str = f'{stat:.1f} (p={p:.3e}, n01={n01}, n10={n10})'
        rows.append([
            name,
            r['train_acc'], r['test_acc'],
            r['train_f1'],  r['test_f1'],
            r.get('baseline_acc_on_var_test', np.nan),
            r.get('baseline_f1_on_var_test',  np.nan),
            m_str,
        ])
    df = pd.DataFrame(rows, columns=[
        'Filter Name', 'Avg Train Acc', 'Avg Test Acc',
        'Avg Train F1', 'Avg Test F1',
        'Baseline Acc (var test)', 'Baseline F1 (var test)',
        'McNemar (Stat, p, n01, n10)',
    ])
    print(f'{LABEL_DISPLAY[target_label]} - McNemar (pooled across seeds), '
          f'{method.capitalize()} aggregation')
    display(df)
    return df


def visualize_mcnemar_significance(results_dict, target_label, method):
    filter_names = ['raw'] + [n for n in results_dict.keys() if n != 'raw']
    pvals = []
    for n in filter_names:
        if n == 'raw' or results_dict[n]['mcnemar'] is None:
            pvals.append(np.nan)
            continue
        _, p, _, _ = results_dict[n]['mcnemar']
        pvals.append(p)
    vals = []
    for p in pvals:
        try:
            fp = float(p)
            vals.append(-np.log10(max(fp, 1e-300)) if fp == fp else np.nan)
        except Exception:
            vals.append(np.nan)
    df = pd.DataFrame([vals], columns=filter_names, index=['-log10(p)'])
    plt.figure(figsize=(14, 2.8))
    sns.heatmap(df, cmap='magma')
    plt.title(f'{LABEL_DISPLAY[target_label]} McNemar significance ({method.capitalize()})')
    plt.tight_layout()
    plt.show()


# Run the full sweep across all five aggregation methods.
for method in AGG_METHODS:
    for target_label in LABELS:
        res = evaluate_for_method(method, target_label)
        show_results(res, target_label=target_label, method=method)
        visualize_mcnemar_significance(res, target_label=target_label, method=method)
'''


CENTROID_SRC = '''def compute_centroid(X_agg, patients_df, target_label):
    """Mean feature vector across positive-class records, with per-column
    mean imputation for any remaining NaN cells (no zero fill)."""
    y = _select_pos_label(patients_df, target_label)
    y = y.loc[X_agg.index]
    sel = y.values == 1
    if sel.sum() == 0:
        return None
    block = X_agg.loc[y.index[sel]]
    col_means = block.mean(axis=0, skipna=True)
    block_filled = block.fillna(col_means)
    vec = block_filled.mean(axis=0, skipna=True).values
    # Fall back to 0 only for columns that are entirely NaN among positives;
    # other columns reflect actual data via mean imputation above.
    vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
    return vec


def visualize_centroid_shift(method):
    base_pat = maybe_sample_record_ids(BASELINE['patients'], MAX_RECORDS_PER_SCENARIO)
    X_base_full = BASELINE['X']
    X_base_small = subset_X_by_patients(X_base_full, base_pat)
    X_base_agg = build_record_aggregated_features(X_base_small, method).loc[base_pat.index]

    # Aggregate every variant once; remember which baseline columns each one
    # actually kept.
    variant_aggs = []
    for v in VARIANT_OBJS:
        pat = maybe_sample_record_ids(v['patients'], MAX_RECORDS_PER_SCENARIO)
        X_v_full = v.get('X', None)
        if X_v_full is None:
            X_v_full = pd.read_hdf(str(v['datafile']), 'vitals_labs')
        Xv_small = subset_X_by_patients(X_v_full, pat)
        Xv_agg = build_record_aggregated_features(Xv_small, method).loc[pat.index]
        variant_aggs.append({
            'name': v['name'],
            'pat':  pat,
            'X':    Xv_agg,
            'cols': Xv_agg.columns,
        })
        try:
            del X_v_full, Xv_small
        except Exception:
            pass

    # Globally-shared columns: kept by baseline AND by every variant. PCA
    # then operates on equal-length shift vectors. Phantom shifts driven by
    # missing-column zero-fills are no longer possible.
    global_shared = X_base_agg.columns
    for va in variant_aggs:
        global_shared = global_shared.intersection(va['cols'])
    Xb_global = X_base_agg[global_shared]

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    for ax, lab in zip(axes, LABELS):
        cb = compute_centroid(Xb_global, base_pat, lab)
        if cb is None:
            ax.set_title(f'{LABEL_DISPLAY[lab]} (no baseline centroid)')
            ax.grid(True, alpha=0.3)
            continue

        shift_vecs = []
        names = []
        for va in variant_aggs:
            Xv_global = va['X'][global_shared]
            cv = compute_centroid(Xv_global, va['pat'], lab)
            if cv is None:
                continue
            n_dropped_vs_baseline = len(X_base_agg.columns) - len(va['cols'])
            shift_vecs.append(cv - cb)
            label = va['name']
            if n_dropped_vs_baseline:
                label += f' (-{n_dropped_vs_baseline})'
            names.append(label)

        if not shift_vecs:
            ax.set_title(f'{LABEL_DISPLAY[lab]} (no variant centroids)')
            ax.grid(True, alpha=0.3)
            continue

        if len(shift_vecs) < 2:
            ax.scatter([0], [0], marker='*', s=150, c='red')
            ax.scatter([0], [0], s=50)
            ax.annotate(names[0], (0, 0), fontsize=8, alpha=0.8)
            ax.set_title(f'{LABEL_DISPLAY[lab]} (insufficient variants for PCA)')
            ax.grid(True, alpha=0.3)
            continue

        Z = PCA(n_components=2, random_state=0).fit_transform(np.vstack(shift_vecs))
        ax.scatter([0], [0], marker='*', s=150, c='red', label='baseline')
        for i, n in enumerate(names):
            ax.scatter([Z[i, 0]], [Z[i, 1]], s=50)
            ax.annotate(n, (Z[i, 0], Z[i, 1]), fontsize=8, alpha=0.8)
            ax.plot([0, Z[i, 0]], [0, Z[i, 1]], linewidth=1)
        ax.set_title(f'{LABEL_DISPLAY[lab]} centroid shift')
        ax.set_xlabel('PC1')
        ax.set_ylabel('PC2')
        ax.grid(True, alpha=0.3)

    plt.suptitle(f'Centroid Shift (aggregation={method})')
    plt.tight_layout()
    plt.show()


for method in AGG_METHODS:
    visualize_centroid_shift(method)
'''


REPLACEMENTS = {
    "10a2cf8a": VARIANT_LOADER_SRC,
    "12a0e285": MCNEMAR_SRC,
    "93f67645": CENTROID_SRC,
}


def main():
    nb = json.loads(NB_PATH.read_text())

    if not BACKUP.exists():
        shutil.copy2(NB_PATH, BACKUP)
        print(f"Backup written: {BACKUP}")

    seen = {}
    for cell in nb["cells"]:
        cid = cell.get("id")
        if cid in REPLACEMENTS:
            new_src = REPLACEMENTS[cid]
            cell["source"] = new_src.splitlines(keepends=True)
            cell["outputs"] = []
            cell["execution_count"] = None
            seen[cid] = True
            print(f"Patched cell {cid} ({len(new_src.splitlines())} lines)")

    missing = [k for k in REPLACEMENTS if k not in seen]
    if missing:
        raise SystemExit(f"FATAL: cell IDs not found: {missing}")

    NB_PATH.write_text(json.dumps(nb, indent=1, ensure_ascii=False))
    print(f"Wrote: {NB_PATH}")


if __name__ == "__main__":
    main()
