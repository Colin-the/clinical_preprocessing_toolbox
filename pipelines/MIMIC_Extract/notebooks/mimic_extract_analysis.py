import marimo

__generated_with = "0.23.6"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # MIMIC_Extract Analysis

    Scenario-based pipeline evaluation with Aurora visual style.
    """)
    return


@app.cell
def _():
    import warnings
    import pickle
    from pathlib import Path
    from typing import List, Tuple

    from IPython.display import display

    import numpy as np
    import pandas as pd
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D   # noqa: F401  needed for 3-D projection
    from scipy.interpolate import griddata
    from scipy.stats import binom
    from sklearn.model_selection import train_test_split
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    from tabulate import tabulate
    from tqdm.notebook import tqdm

    warnings.filterwarnings('ignore')
    # '%matplotlib inline' command supported automatically in marimo
    plt.rcParams.update({
        'figure.facecolor': '#191a1c',
        'axes.facecolor':   '#191a1c',
        'text.color':       'white',
        'axes.labelcolor':  'white',
        'xtick.color':      'white',
        'ytick.color':      'white',
    })
    return (
        List,
        LogisticRegression,
        PCA,
        Path,
        StandardScaler,
        Tuple,
        accuracy_score,
        binom,
        f1_score,
        griddata,
        mcolors,
        np,
        pd,
        pickle,
        plt,
        tabulate,
        tqdm,
        train_test_split,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Setup
    """)
    return


@app.cell
def _(Path):
    CURATED_ROOT        = Path('..') / 'data' / 'curated'
    ANALYSIS_CACHE_DIR  = Path('..') / 'data' / 'scenario_analysis'

    SCENARIOS = [
        'age35_range5',  'age35_range10',  'age35_range15',
        'age45_range5',  'age45_range10',  'age45_range15',
        'age55_range5',  'age55_range10',  'age55_range15',
        'min48hr', 'min18age', 'minperc5',
    ]

    AGG_METHODS = [
        'mean', 'median', 'standard deviation', 'mean deviation', 'maximum deviation'
    ]

    LABELS     = ['icu_los', 'mortality']
    SEEDS      = [22, 985, 439, 81]
    TEST_SIZE  = 0.2
    MAX_RECORDS_PER_SCENARIO = None
    MODEL_KWARGS = dict(max_iter=500, solver='liblinear', random_state=0)
    FALLBACK_BASELINE_SCENARIO = 'baseline_nofilters'
    EXCLUDED_EXPERIMENTS       = {'baseline_nofilters_fast'}

    VITAL_NAMES = [
        'Heart Rate',
        'Systolic blood pressure',
        'Diastolic blood pressure',
        'Mean blood pressure',
        'Respiratory rate',
        'Temperature',
        'Oxygen saturation',
    ]

    LABEL_DISPLAY = {
        'icu_los':   'icu_los (ICU stay > 3 days)',
        'mortality': 'mort_hosp / hospital_expire_flag  (hospital mortality)',
    }

    ANALYSIS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print('Curated root:', CURATED_ROOT.resolve())
    print('Variants    :', len(SCENARIOS))
    return (
        AGG_METHODS,
        ANALYSIS_CACHE_DIR,
        CURATED_ROOT,
        EXCLUDED_EXPERIMENTS,
        FALLBACK_BASELINE_SCENARIO,
        LABELS,
        LABEL_DISPLAY,
        MAX_RECORDS_PER_SCENARIO,
        MODEL_KWARGS,
        SCENARIOS,
        SEEDS,
        TEST_SIZE,
        VITAL_NAMES,
    )


@app.cell
def _(CURATED_ROOT, StandardScaler, binom, np, pd):
    # ── index helpers ──────────────────────────────────────────────────────────────
    def _get_time_level_name(x_index):
        _names = list(x_index.names)
        for _c in ['hours_in', 'time', 'hour', 'Hour']:
            if _c in _names:
                return _c
        return _names[-1]

    def _record_id_levels(x_index):
        t = _get_time_level_name(x_index)
        return [_n for _n in x_index.names if _n != t]

    def _select_pos_label(patients_df, target_label):
        if target_label == 'icu_los':
            return (patients_df['los_icu'] > 3).astype(int)
        if target_label == 'mortality':
            for col in ('mort_hosp', 'hospital_expire_flag'):
                if col in patients_df.columns:
                    return patients_df[col].astype(int)
            raise KeyError('No mortality column found in patients_df')
        raise ValueError(f'Unknown target label: {target_label}')

    def _ensure_multiindex(arr, names):
        if isinstance(arr, pd.MultiIndex):
            return arr
        return pd.MultiIndex.from_tuples([tuple(t) for t in arr], names=_names)

    def _pick_datafile(scenario_dir):
    # ── I/O helpers ────────────────────────────────────────────────────────────────
        for _c in ('all_hourly_data.h5', 'all_hourly_data_5000.h5', 'all_hourly_data_2000.h5'):
            fp = scenario_dir / _c
            if fp.exists():
                return fp
        raise FileNotFoundError(f'No all_hourly_data*.h5 found in {scenario_dir}')

    def load_curated_scenario(scenario_name, data_root=CURATED_ROOT, load_X=True):
        scenario_dir = data_root / scenario_name
        datafile = _pick_datafile(scenario_dir)
        X = pd.read_hdf(str(datafile), 'vitals_labs') if load_X else None
        patients = pd.read_hdf(str(datafile), 'patients')
        try:
            interventions = pd.read_hdf(str(datafile), 'interventions')
        except Exception:
            interventions = None
        return {'name': scenario_name, 'X': X, 'patients': patients, 'interventions': interventions, 'datafile': datafile}

    def maybe_sample_record_ids(patients_df, max_records):
        if max_records is None or len(patients_df) <= max_records:
            return patients_df
        return patients_df.sample(max_records, random_state=0)

    def subset_X_by_patients(X, patients_df):
        time_level = _get_time_level_name(X.index)
        rec_index = X.index.droplevel(time_level)
        return X[rec_index.isin(patients_df.index)]

    def build_record_aggregated_features(X, method):
        rec_levels = _record_id_levels(X.index)
        g = X.groupby(level=rec_levels)
    # ── aggregation ────────────────────────────────────────────────────────────────
        if method == 'mean':
            return g.mean()
        if method == 'median':
            return g.median()
        if method == 'standard deviation':
            return g.std(ddof=1)
        if method == 'mean deviation':

            def _mean_dev(df):
                return df.sub(df.mean(axis=0), axis=1).abs().mean(axis=0)
            return g.apply(_mean_dev)
        if method == 'maximum deviation':

            def _max_dev(df):
                return df.sub(df.mean(axis=0), axis=1).abs().max(axis=0)
            return g.apply(_max_dev)
        raise ValueError(f'Unknown method: {method}')

    def _find_feature_name(feature_map, target_name):
        key = target_name.lower()
    # ── lens-plot helpers ──────────────────────────────────────────────────────────
        if key in feature_map:
            return feature_map[key]
        aliases = {'Heart Rate': ['heart rate', 'heartrate', 'pulse'], 'Systolic blood pressure': ['systolic blood pressure', 'sbp'], 'Diastolic blood pressure': ['diastolic blood pressure', 'dbp'], 'Mean blood pressure': ['mean blood pressure', 'map'], 'Respiratory rate': ['respiratory rate', 'resp rate', 'rr'], 'Temperature': ['temperature', 'temp'], 'Oxygen saturation': ['oxygen saturation', 'spo2', 'o2 saturation']}.get(target_name, [target_name.lower()])
        for alias in aliases:
            if alias in feature_map:
                return feature_map[alias]
        return None

    def _aggregate_series_by_hour(series, hour_values, method):
        s = pd.Series(series.values, index=hour_values)
        if method == 'mean':
            return s.groupby(level=0).mean()
        if method == 'median':
            return s.groupby(level=0).median()
        if method == 'standard deviation':
            return s.groupby(level=0).std(ddof=1)
        if method == 'mean deviation':
            return s.groupby(level=0).apply(lambda x: (x - x.mean()).abs().mean())
        if method == 'maximum deviation':
            return s.groupby(level=0).apply(lambda x: (x - x.mean()).abs().max())
        raise ValueError(f'Unknown method: {method}')

    def build_lens_method_hour_matrix(X, requested_feature, requested_methods):
        if not isinstance(X.columns, pd.MultiIndex):
            raise ValueError('Expected MultiIndex columns in vitals_labs.')
        time_level = _get_time_level_name(X.index)
        hour_values = X.index.get_level_values(time_level)
        all_hours = np.sort(np.asarray(pd.Index(hour_values).unique(), dtype=int))
        mean_cols = [_c for _c in X.columns if str(_c[1]).lower() == 'mean']
        feature_map = {str(_c[0]).lower(): str(_c[0]) for _c in mean_cols}
        actual = _find_feature_name(feature_map, requested_feature)
        if actual is None:
            matrix = pd.DataFrame(np.nan, index=requested_methods, columns=all_hours)
            matrix.columns.name = 'Hour'
            matrix.index.name = 'Aggregation'
            return (matrix, True)
        col = next((_c for _c in mean_cols if str(_c[0]) == actual))
        _rows = []
        for method in requested_methods:
            agg = _aggregate_series_by_hour(X[col], hour_values, method).reindex(all_hours)
            _rows.append(pd.Series(agg.values, index=all_hours, name=method))
        matrix = pd.DataFrame(_rows, index=requested_methods)
        matrix.columns.name = 'Hour'
        matrix.index.name = 'Aggregation'
        return (matrix, False)

    def impute_and_scale(X):
        X = X.replace([np.inf, -np.inf], np.nan)
        col_means = X.mean(axis=0, skipna=True).fillna(0.0)
        X = X.fillna(col_means).fillna(0.0)
        scaler = StandardScaler()
        return (scaler.fit_transform(X.values), scaler, col_means)

    def mcnemar_counts(y_true, pred_a, pred_b):
        y = np.asarray(y_true).astype(int)
        a_c = np.asarray(pred_a).astype(int) == y
        b_c = np.asarray(pred_b).astype(int) == y
    # ── evaluation helpers ─────────────────────────────────────────────────────────
        return (int(np.sum(~a_c & b_c)), int(np.sum(a_c & ~b_c)))

    def mcnemar_pooled(n01, n10):
        _n = n01 + n10
        if _n == 0:
            return (0.0, 1.0)
        stat = (abs(n01 - n10) - 1.0) ** 2 / _n
        p_one = binom.cdf(min(n01, n10), _n, 0.5)
        return (float(stat), float(min(1.0, 2.0 * p_one)))

    def compute_centroid(X_agg, patients_df, target_label):
        y = _select_pos_label(patients_df, target_label)
        y = y.loc[X_agg.index]
        sel = y.values == 1
        if sel.sum() == 0:
            return None
        block = X_agg.loc[y.index[sel]]
        col_means = block.mean(axis=0, skipna=True)
        vec = block.fillna(col_means).mean(axis=0, skipna=True).values
        return np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)

    def extract_vital_centroid(X_agg, patients_df, target_label, vital_names, polarity='pos'):
        y = _select_pos_label(patients_df, target_label)
        y = y.loc[X_agg.index]
        sel = y.values == 1 if polarity == 'pos' else y.values == 0
        if sel.sum() == 0:
            return np.zeros(len(vital_names))
        vital_cols = []
        for vn in vital_names:
            cands = [_c for _c in X_agg.columns if isinstance(_c, tuple) and _c[0].lower() == vn.lower() and (str(_c[1]).lower() == 'mean')]
            if cands:
                vital_cols.append(cands[0])
            else:
                vital_cols.append(None)
        vals = []
        for col in vital_cols:
            if col is None or col not in X_agg.columns:
                vals.append(0.0)
            else:
                s = X_agg.loc[y.index[sel], col]
                vals.append(float(s.mean(skipna=True)) if not s.isna().all() else 0.0)
        return np.array(vals)

    def results_dict_to_impact_tuple(results_dict):
        _names = ['raw'] + [_n for _n in results_dict.keys() if _n != 'raw']
        train_accs, test_accs, train_f1s, test_f1s, mcnemar_results = ([], [], [], [], [])
        for _n in _names:
            r = results_dict[_n]
            train_accs.append(r['train_acc'])
            test_accs.append(r['test_acc'])
            train_f1s.append(r['train_f1'])
            test_f1s.append(r['test_f1'])
            if _n == 'raw' or r['mcnemar'] is None:
                mcnemar_results.append((np.nan, np.nan))
            else:
                stat, p, _, _ = r['mcnemar']
                mcnemar_results.append((stat, p))
        return (train_accs, test_accs, train_f1s, test_f1s, mcnemar_results)

    def build_vital_hour_length_matrix(X, vital_names):
        """
        Returns {method: DataFrame(index=hours, columns=vitals)} where values
        are the per-method aggregate of raw observation counts across patients.
        Uses the 'count' statistic column if present; falls back to notna() indicator.
        Methods match EHR Dataset Processing: mean, median, std, max, min.
        """
        time_level = _get_time_level_name(X.index)
        hour_vals = X.index.get_level_values(time_level)
        all_hours = np.sort(pd.Index(hour_vals).unique().astype(int))
        vital_series = {}
        for vital in vital_names:
            vital_lower = vital.lower()
            count_col = next((_c for _c in X.columns if str(_c[0]).lower() == vital_lower and str(_c[1]).lower() == 'count'), None)
            if count_col is not None:
                raw = X[count_col]
            else:
                mean_col = next((_c for _c in X.columns if str(_c[0]).lower() == vital_lower), None)
                if mean_col is None:
                    continue
                raw = X[mean_col].notna().astype(float)
            vital_series[vital] = pd.Series(raw.values, index=hour_vals)
        length_methods = ['mean', 'median', 'std', 'max', 'min']
        result = {}
        for method in length_methods:
            _rows = {vital: s.groupby(level=0).agg(method).reindex(all_hours) for vital, s in vital_series.items()}
            df = pd.DataFrame(_rows, index=all_hours)
            df.index.name = 'Hour'
            result[method] = df
        return result

    return (
        build_record_aggregated_features,
        build_vital_hour_length_matrix,
        compute_centroid,
        extract_vital_centroid,
        impute_and_scale,
        load_curated_scenario,
        maybe_sample_record_ids,
        mcnemar_counts,
        mcnemar_pooled,
        results_dict_to_impact_tuple,
        subset_X_by_patients,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Aurora Visualization Helpers

    All plots use the Aurora dark theme (background `#191a1c`, gradient `#191a1c → #724ed5 → #4ED595`).
    Functions are copied from `EHR-Dataset-Processing/Managers/visualization_manager.py` and adapted
    for the scenario-based MIMIC_Extract data.
    """)
    return


@app.cell
def _(List, Tuple, VITAL_NAMES, griddata, mcolors, np, pd, plt):
    def generate_hex_gradient(colours: List[str], gradient_length: int) -> List[str]:
        if len(colours) < 2:
            raise ValueError('At least two colors required.')
        if gradient_length == 1:
            return [colours[0]]
        rgb_colors = np.array([mcolors.to_rgb(_c) for _c in colours])
        segments = len(colours) - 1
        gradient = []
        for _i in range(gradient_length):
            pos = _i / (gradient_length - 1)
            seg = min(int(pos * segments), segments - 1)
            seg_pos = (pos - seg / segments) * segments
            interp = rgb_colors[seg] + (rgb_colors[seg + 1] - rgb_colors[seg]) * seg_pos
            gradient.append(mcolors.to_hex(interp))
        return gradient
    _AURORA = ['#191a1c', '#724ed5', '#4ED595']
    _BG = '#191a1c'

    def _aurora_cmap():
        g = generate_hex_gradient(_AURORA, 20)
        return mcolors.LinearSegmentedColormap.from_list('aurora', g, N=20)

    def generate_3d_plot(df: pd.DataFrame, title: str='3D Surface', x_title: str='', y_title: str='', z_title: str='', background_colour: str=_BG):
        if not np.issubdtype(df.values.dtype, np.number):
            raise ValueError('DataFrame must be numeric.')
        _rows, cols = df.shape
        X, Y = np.meshgrid(np.arange(cols), np.arange(_rows))
        Z = df.values.astype(float)
        X_s = np.linspace(0, cols - 1, cols * 10)
        Y_s = np.linspace(0, _rows - 1, _rows * 10)
        Xg, Yg = np.meshgrid(X_s, Y_s)
        Zg = griddata(np.column_stack((X.flatten(), Y.flatten())), Z.flatten(), (Xg, Yg), method='cubic')
        cmap = _aurora_cmap()
        _fig = plt.figure(figsize=(12, 6), facecolor=background_colour)
        _ax = _fig.add_subplot(111, projection='3d', facecolor=background_colour)
        surf = _ax.plot_surface(Xg, Yg, Zg, cmap=cmap, edgecolor='none')
        _ax.set_xlabel(x_title)
        _ax.set_ylabel(y_title)
        _ax.set_zlabel(z_title)
        _ax.set_xticks(np.arange(cols))
        _ax.set_xticklabels(df.columns, rotation=45, ha='right')
        for pane in (_ax.xaxis, _ax.yaxis, _ax.zaxis):
            pane.pane.fill = False
            pane._axinfo['grid']['color'] = '#3a3b3d'
            pane._axinfo['grid']['linewidth'] = 0.5
            pane._axinfo['grid']['linestyle'] = ':'
            pane._axinfo['edgecolor'] = '#3a3b3d'
        cbar = _fig.colorbar(surf, ax=_ax, shrink=0.6, pad=0.1)
        cbar.outline.set_visible(False)
        _ax.set_title(title, color='white')
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter('ignore', UserWarning)
            plt.tight_layout()
        plt.show()

    def generate_heatmap(df: pd.DataFrame, title: str='Heatmap', x_title: str='', y_title: str='', annotate: bool=True):
        if not np.issubdtype(df.values.dtype, np.number):
            raise ValueError('DataFrame must be numeric.')
        nr, nc = df.shape
        cmap = _aurora_cmap()
        _fig, _ax = plt.subplots(figsize=(10, 7), facecolor=_BG)
        hm = _ax.imshow(df.values, cmap=cmap, aspect='auto', origin='lower')
        _ax.set_xticks(np.arange(nc))
        if nc <= 50:
            _ax.set_xticklabels(df.columns, rotation=45, ha='right', color='white')
        else:
            step = max(1, nc // 24)
            shown = np.arange(0, nc, step)
            _ax.set_xticks(shown)
            _ax.set_xticklabels([list(df.columns)[_i] for _i in shown], rotation=45, ha='right', color='white')
        _ax.set_yticks(np.arange(nr))
        _ax.set_yticklabels(df.index, color='white')
        _ax.set_xlabel(x_title, color='white')
        _ax.set_ylabel(y_title, color='white')
        _ax.set_title(title, color='white')
        _ax.set_xticks(np.arange(-0.5, nc, 1), minor=True)
        _ax.set_yticks(np.arange(-0.5, nr, 1), minor=True)
        _ax.grid(which='minor', color='#3a3b3d', linestyle=':', linewidth=0.5)
        _ax.tick_params(which='minor', bottom=False, left=False)
        if annotate:
            for _i in range(nr):
                for j in range(nc):
                    _v = df.values[_i, j]
                    if not np.isnan(_v):
                        _ax.text(j, _i, f'{_v:.1f}', ha='center', va='center', color='white', fontsize=8)
        for sp in _ax.spines.values():
            sp.set_visible(False)
        _ax.set_frame_on(False)
        cbar = _fig.colorbar(hm, ax=_ax, shrink=0.7)
        cbar.outline.set_visible(False)
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter('ignore', UserWarning)
            plt.tight_layout()
        plt.show()

    def visualize_scenario_impact(scores: List[float], scenario_names: List[str], label: str, metric: str, aggregation_method: str, epsilon: float=0.001, min_range: float=0.005):
        reference = scores[0]
        scores_to_plot = np.array(scores[1:])
        deviations = scores_to_plot - reference
        indices = np.arange(len(scores_to_plot))
        bar_colors = np.where(deviations > epsilon, '#3b8465', np.where(deviations < -epsilon, '#bd3140', '#a0a0a0'))
        _fig, _ax = plt.subplots(figsize=(14, 8), facecolor=_BG)
        _ax.bar(indices, deviations, color=bar_colors, width=0.8, zorder=3)
        for _i, dev in enumerate(deviations):
            va = 'bottom' if dev >= 0 else 'top'
            offset = 0.0005 if dev >= 0 else -0.0005
            _ax.text(_i, dev + offset, f'{dev:+.4f}', ha='center', va=va, color='#a0a0a0', fontsize=9, fontweight='bold')
        for idx in indices[deviations > epsilon]:
            _ax.axvline(x=idx, color='#3b8465', linestyle='-', linewidth=0.5, alpha=0.3)
        for idx in indices[deviations < -epsilon]:
            _ax.axvline(x=idx, color='#bd3140', linestyle='-', linewidth=0.5, alpha=0.3)
        _ax.set_xticks(indices)
        _ax.set_xticklabels(scenario_names, rotation=45, ha='right', fontsize=10)
        dev_range = deviations.max() - deviations.min()
        if dev_range < min_range:
            _ax.set_ylim(-min_range * 1.2, min_range * 1.2)
        else:
            m = dev_range * 0.25
            _ax.set_ylim(deviations.min() - m, deviations.max() + m)
        _ax.patch.set_facecolor(_BG)
        _ax.set_facecolor(_BG)
        _ax.grid(color='gray', linestyle='--', linewidth=0.5, alpha=0.2, zorder=0)
        for sp in ('bottom', 'left'):
            _ax.spines[sp].set_color('#ffffff')
        _ax.tick_params(colors='#ffffff')
        _ax.xaxis.label.set_color('#ffffff')
        _ax.yaxis.label.set_color('#ffffff')
        _ax.set_xlabel('Scenario')
        _ax.set_ylabel(f'{metric} Deviation from Baseline')
        _ax.set_title(f'{label.upper()} Scenario Impact ({aggregation_method.capitalize()} {metric})', color='#ffffff')
        _ax.axhline(0, color='white', linewidth=0.8, alpha=0.5)
        plt.tight_layout()
        plt.show()

    def visualize_mcnemar_significance(p_values: List[float], scenario_names: List[str], label: str, title: str=None):
        p_values = [max(float(p) if p == p else 1.0, 1e-20) for p in p_values]
        neg_log_p = -np.log10(p_values)
        indices = np.arange(len(scenario_names))
        colors = ['#f39c12' if p < 0.05 else '#a0a0a0' for p in p_values]
        _fig, _ax = plt.subplots(figsize=(14, 7), facecolor=_BG)
        _ax.set_facecolor(_BG)
        bars = _ax.bar(indices, neg_log_p, color=colors, alpha=0.85, zorder=3)
        _ax.axhline(y=-np.log10(0.05), color='#bd3140', linestyle='--', linewidth=1.5, label='p = 0.05 Threshold', zorder=4)
        _ax.set_xticks(indices)
        _ax.set_xticklabels(scenario_names, rotation=45, ha='right', color='#ffffff')
        _ax.tick_params(axis='y', colors='#ffffff')
        _ax.set_ylabel('$-\\log_{10}(p\\text{-value})$', color='#ffffff', fontsize=12)
        _ax.set_xlabel('Scenario', color='#ffffff', fontsize=12)
        _title = title or f'{label.upper()} McNemar Significance'
        _ax.set_title(_title, color='#ffffff', fontsize=16, pad=20)
        for bar, p in zip(bars, p_values):
            h = bar.get_height()
            disp = f'{p:.3f}' if p > 0.001 else f'{p:.1e}'
            _ax.text(bar.get_x() + bar.get_width() / 2.0, h + 0.1, disp, ha='center', va='bottom', color='#a0a0a0', fontsize=9)
        _ax.grid(axis='y', color='gray', linestyle='--', linewidth=0.5, alpha=0.2, zorder=0)
        for sp in _ax.spines.values():
            sp.set_color('#444444')
        _ax.legend(facecolor=_BG, framealpha=0.8, edgecolor='white', labelcolor='white')
        plt.tight_layout()
        plt.show()

    def visualize_centroid_shift_v2(shift_tuples: List[Tuple[List[float], List[float]]], titles: List[str], scenario_name: str, vital_names: List[str]=None, epsilon: float=0.001, min_range: float=0.005):
        _vnames = vital_names if vital_names else VITAL_NAMES
        hatches = ['', '//', '..', 'xx', '\\\\', '++', 'OO', '--']
        _fig, _ax = plt.subplots(figsize=(20, 8), facecolor=_BG)
        n_groups = len(shift_tuples)
        indices = np.arange(len(shift_tuples[0][0]))
        bar_w = 0.8 / n_groups
        for g, ((baseline, scores), title_suffix) in enumerate(zip(shift_tuples, titles)):
            baseline = np.array(baseline)
            scores = np.array(scores)
            deviations = scores - baseline
            pos = indices + (g - n_groups / 2) * bar_w + bar_w / 2
            colors = ['#3b8465' if d > epsilon else '#bd3140' if d < -epsilon else '#a0a0a0' for d in deviations]
            _ax.bar(pos, deviations, color=colors, width=bar_w, edgecolor='white', linewidth=0.5, hatch=hatches[g % len(hatches)], label=title_suffix, zorder=3)
            for _i, dev in enumerate(deviations):
                va = 'bottom' if dev >= 0 else 'top'
                offset = 0.0005 if dev >= 0 else -0.0005
                _ax.text(pos[_i], dev + offset, f'{dev:+.4f}', ha='center', va=va, color='#a0a0a0', fontsize=8, fontweight='bold')
        _ax.set_xticks(indices)
        _ax.set_xticklabels([_v.title() for _v in _vnames], rotation=45, ha='right', fontsize=10)
        _ax.patch.set_facecolor(_BG)
        _ax.set_facecolor(_BG)
        _ax.grid(color='gray', linestyle='--', linewidth=0.5, alpha=0.2, zorder=0)
        for sp in _ax.spines.values():
            sp.set_color('#ffffff')
        _ax.tick_params(colors='#ffffff')
        _ax.xaxis.label.set_color('#ffffff')
        _ax.yaxis.label.set_color('#ffffff')
        _ax.set_xlabel('Vital Sign')
        _ax.set_ylabel('Deviation from Baseline Centroid')
        _ax.set_title(f'Centroid Deviations — {scenario_name} | Hatches Identify Groups', color='#ffffff')
        _ax.axhline(0, color='white', linewidth=0.8, alpha=0.5)
        _ax.legend(facecolor=_BG, labelcolor='white')
        plt.tight_layout()
        plt.show()

    return (
        generate_3d_plot,
        generate_heatmap,
        generate_hex_gradient,
        visualize_centroid_shift_v2,
        visualize_mcnemar_significance,
        visualize_scenario_impact,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Load Raw Data
    """)
    return


@app.cell
def _(
    EXCLUDED_EXPERIMENTS,
    MAX_RECORDS_PER_SCENARIO,
    SCENARIOS,
    load_curated_scenario,
    maybe_sample_record_ids,
):
    VARIANT_OBJS = []
    for s in SCENARIOS:
        if s in EXCLUDED_EXPERIMENTS:
            continue
        print('Loading patients only:', s)
        obj = load_curated_scenario(s, load_X=False)
        obj['patients'] = maybe_sample_record_ids(obj['patients'], MAX_RECORDS_PER_SCENARIO)
        VARIANT_OBJS.append(obj)
    print('\nEffective variants:', len(VARIANT_OBJS))
    print('Variants:', [_v['name'] for _v in VARIANT_OBJS])
    return (VARIANT_OBJS,)


@app.cell
def _(
    FALLBACK_BASELINE_SCENARIO,
    MAX_RECORDS_PER_SCENARIO,
    load_curated_scenario,
    maybe_sample_record_ids,
):
    BASELINE = load_curated_scenario(FALLBACK_BASELINE_SCENARIO, load_X=True)
    BASELINE['patients'] = maybe_sample_record_ids(BASELINE['patients'], MAX_RECORDS_PER_SCENARIO)
    print('Baseline :', BASELINE['name'])
    print('X shape  :', BASELINE['X'].shape)
    print('Patients :', BASELINE['patients'].shape)
    return (BASELINE,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Scenario Overview

    Summary of each cohort variant vs. the baseline.
    """)
    return


@app.cell
def _(BASELINE, VARIANT_OBJS, tabulate):
    _rows = []
    base_n = len(BASELINE['patients'])
    for _v in [BASELINE] + VARIANT_OBJS:
        _n = len(_v['patients'])
        icu_prev = float(_select_pos_label(_v['patients'], 'icu_los').mean())
        mort_prev = float(_select_pos_label(_v['patients'], 'mortality').mean())
        _rows.append({'Scenario': _v['name'], 'Records': _n, 'Δ vs Baseline': _n - base_n, 'ICU LOS prev (>3d)': f'{icu_prev:.3f}', 'Hosp mort prev': f'{mort_prev:.3f}'})
    print(tabulate(_rows, headers='keys', tablefmt='github'))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Timeseries Feature × Hour Analysis

    For each aggregation method, visualise how each vital sign changes across the 24-hour window using Aurora-style 3D surface and heatmap plots.
    """)
    return


@app.cell
def _(
    BASELINE,
    MAX_RECORDS_PER_SCENARIO,
    VITAL_NAMES,
    build_vital_hour_length_matrix,
    generate_3d_plot,
    generate_heatmap,
    maybe_sample_record_ids,
    subset_X_by_patients,
):
    _base_pat = maybe_sample_record_ids(BASELINE['patients'], MAX_RECORDS_PER_SCENARIO)
    X_base_full_ts = subset_X_by_patients(BASELINE['X'], _base_pat)
    _time_level = _get_time_level_name(X_base_full_ts.index)
    _hour_vals = X_base_full_ts.index.get_level_values(_time_level)
    X_base_24h = X_base_full_ts[_hour_vals <= 23]
    print(f'Full timeseries: hours {int(_hour_vals.min())}–{int(_hour_vals.max())} ({_hour_vals.nunique()} unique)')
    print(f'24-hour subset : {len(X_base_24h):,} rows  |  Full: {len(X_base_full_ts):,} rows')
    lengths_24h = build_vital_hour_length_matrix(X_base_24h, VITAL_NAMES)
    lengths_full = build_vital_hour_length_matrix(X_base_full_ts, VITAL_NAMES)
    LENGTH_METHODS = ['mean', 'median', 'std', 'max', 'min']
    for method in LENGTH_METHODS:
        print(f'\n=== {method.upper()} ===')
        df_24 = lengths_24h[method].fillna(0.0)
        generate_3d_plot(df_24, title=f'{method.capitalize()} Observation Count — First 24 h', x_title='Vital', y_title='Hour (0–23)', z_title=f'{method.capitalize()} Count')
        generate_heatmap(df_24, title=f'{method.capitalize()} Observation Count Heatmap — First 24 h', x_title='Vital', y_title='Hour (0–23)', annotate=False)
        df_full = lengths_full[method].fillna(0.0)
        generate_3d_plot(df_full, title=f'{method.capitalize()} Observation Count — Full Timeseries', x_title='Vital', y_title='Hour (0–239)', z_title=f'{method.capitalize()} Count')
        generate_heatmap(df_full, title=f'{method.capitalize()} Observation Count Heatmap — Full Timeseries', x_title='Vital', y_title='Hour (0–239)', annotate=False)  # ── 24-hour plots ──────────────────────────────────────────────────────────────────────  # ── Full-timeseries plots ────────────────────────────────────────────────────────────────────────────────────
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Evaluating Scenario Impact for ICU and Mortality Tasks

    For each `(aggregation_method, target_label)` pair:
    1. Aggregate baseline records → train logistic regression (4 seeds).
    2. For each variant, re-train and replay the baseline classifier on shared test patients.
    3. Pool McNemar discordant counts across seeds to test statistical significance.

    Results are cached under `data/scenario_analysis/`.
    """)
    return


@app.cell
def _(
    AGG_METHODS,
    ANALYSIS_CACHE_DIR,
    BASELINE,
    LABELS,
    LABEL_DISPLAY,
    LogisticRegression,
    MAX_RECORDS_PER_SCENARIO,
    MODEL_KWARGS,
    SEEDS,
    TEST_SIZE,
    VARIANT_OBJS,
    accuracy_score,
    build_record_aggregated_features,
    f1_score,
    impute_and_scale,
    maybe_sample_record_ids,
    mcnemar_counts,
    mcnemar_pooled,
    np,
    pd,
    pickle,
    subset_X_by_patients,
    tabulate,
    tqdm,
    train_test_split,
):
    def evaluate_for_method(method, target_label, max_variants=None):
        cache_dir = ANALYSIS_CACHE_DIR / method.replace(' ', '_')
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f'{target_label}_scenario_impact.pkl'
        if cache_file.exists():
            print(f'Loading cached results: {cache_file}')
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        _base_pat = maybe_sample_record_ids(BASELINE['patients'], MAX_RECORDS_PER_SCENARIO)
        y_base = _select_pos_label(_base_pat, target_label)
        X_base_full = BASELINE['X']
        _X_base_sm = subset_X_by_patients(X_base_full, _base_pat)
        _X_base_agg = build_record_aggregated_features(_X_base_sm, method).loc[_base_pat.index]
        base_cols = _X_base_agg.columns
        raw_metrics = {'train_acc': [], 'test_acc': [], 'train_f1': [], 'test_f1': []}
        raw_preds_by_seed = {}
        raw_models_by_seed = {}
        idx = _X_base_agg.index
        for seed in SEEDS:
            train_ids, test_ids = train_test_split(idx, test_size=TEST_SIZE, random_state=seed, stratify=y_base.loc[idx].values)
            train_ids = _ensure_multiindex(train_ids, idx.names)
            test_ids = _ensure_multiindex(test_ids, idx.names)
            X_tr, X_te = (_X_base_agg.loc[train_ids], _X_base_agg.loc[test_ids])
            y_tr, y_te = (y_base.loc[train_ids].values, y_base.loc[test_ids].values)
            if len(np.unique(y_tr)) < 2:
                continue
            X_trs, scaler, col_means = impute_and_scale(X_tr)
            X_te_f = X_te.replace([np.inf, -np.inf], np.nan).fillna(col_means).fillna(0.0)
            X_tes = scaler.transform(X_te_f.values)
            clf = LogisticRegression(**MODEL_KWARGS)
            clf.fit(X_trs, y_tr)
            raw_metrics['train_acc'].append(accuracy_score(y_tr, clf.predict(X_trs)))
            raw_metrics['test_acc'].append(accuracy_score(y_te, clf.predict(X_tes)))
            raw_metrics['train_f1'].append(f1_score(y_tr, clf.predict(X_trs), zero_division=0))
            raw_metrics['test_f1'].append(f1_score(y_te, clf.predict(X_tes), zero_division=0))
            raw_preds_by_seed[seed] = (test_ids, clf.predict(X_tes), y_te)
            raw_models_by_seed[seed] = (clf, scaler, col_means, base_cols)
        results = {'raw': {'train_acc': float(np.mean(raw_metrics['train_acc'])), 'test_acc': float(np.mean(raw_metrics['test_acc'])), 'train_f1': float(np.mean(raw_metrics['train_f1'])), 'test_f1': float(np.mean(raw_metrics['test_f1'])), 'mcnemar': None}}
        variants = VARIANT_OBJS if max_variants is None else VARIANT_OBJS[:max_variants]
        for _v in tqdm(variants, desc=f'{method}/{target_label}'):
            _v_pat = maybe_sample_record_ids(_v['patients'], MAX_RECORDS_PER_SCENARIO)
            y_v = _select_pos_label(_v_pat, target_label)
            _X_vf = _v.get('X') or pd.read_hdf(str(_v['datafile']), 'vitals_labs')
            _X_vsm = subset_X_by_patients(_X_vf, _v_pat)
            _X_vagg = build_record_aggregated_features(_X_vsm, method).loc[_v_pat.index]
            metrics = {'train_acc': [], 'test_acc': [], 'train_f1': [], 'test_f1': []}
            base_int = {'acc': [], 'f1': []}
            n01_tot = n10_tot = 0
            for seed in SEEDS:
                base_test_ids, _, _ = raw_preds_by_seed[seed]
                tids = _v_pat.index.intersection(base_test_ids)
                if len(tids) < 10:
                    continue
                trids = _v_pat.index.difference(tids)
                if len(trids) < 10:
                    continue
                X_tr, X_te = (_X_vagg.loc[trids], _X_vagg.loc[tids])
                y_tr, y_te = (y_v.loc[trids].values, y_v.loc[tids].values)
                if len(np.unique(y_tr)) < 2:
                    continue
                X_trs, scaler, cm = impute_and_scale(X_tr)
                X_tef = X_te.replace([np.inf, -np.inf], np.nan).fillna(cm).fillna(0.0)
                X_tes = scaler.transform(X_tef.values)
                clf = LogisticRegression(**MODEL_KWARGS)
                clf.fit(X_trs, y_tr)
                pred_te_var = clf.predict(X_tes)
                metrics['train_acc'].append(accuracy_score(y_tr, clf.predict(X_trs)))
                metrics['test_acc'].append(accuracy_score(y_te, pred_te_var))
                metrics['train_f1'].append(f1_score(y_tr, clf.predict(X_trs), zero_division=0))
                metrics['test_f1'].append(f1_score(y_te, pred_te_var, zero_division=0))
                base_clf, base_sc, base_cm, bsc = raw_models_by_seed[seed]
                X_teb = _X_base_agg.loc[tids, bsc]
                X_tebf = X_teb.replace([np.inf, -np.inf], np.nan).fillna(base_cm).fillna(0.0)
                bp = base_clf.predict(base_sc.transform(X_tebf.values))
                base_int['acc'].append(accuracy_score(y_te, bp))
                base_int['f1'].append(f1_score(y_te, bp, zero_division=0))
                n01, n10 = mcnemar_counts(y_te, bp, pred_te_var)
                n01_tot += n01
                n10_tot += n10
            mc = mcnemar_pooled(n01_tot, n10_tot) + (n01_tot, n10_tot) if metrics['test_acc'] else (np.nan, np.nan, 0, 0)
            results[_v['name']] = {'train_acc': float(np.mean(metrics['train_acc'])) if metrics['train_acc'] else np.nan, 'test_acc': float(np.mean(metrics['test_acc'])) if metrics['test_acc'] else np.nan, 'train_f1': float(np.mean(metrics['train_f1'])) if metrics['train_f1'] else np.nan, 'test_f1': float(np.mean(metrics['test_f1'])) if metrics['test_f1'] else np.nan, 'baseline_acc_on_var_test': float(np.mean(base_int['acc'])) if base_int['acc'] else np.nan, 'baseline_f1_on_var_test': float(np.mean(base_int['f1'])) if base_int['f1'] else np.nan, 'mcnemar': mc}
            try:
                del _X_vf, _X_vsm, _X_vagg
            except Exception:
                pass
        with open(cache_file, 'wb') as f:
            pickle.dump(results, f)
        print(f'Saved cache: {cache_file}')
        return results
    SCENARIO_IMPACT_RESULTS = {}
    for _label in LABELS:
        SCENARIO_IMPACT_RESULTS[_label] = {}
        for _method in AGG_METHODS:
            _res = evaluate_for_method(_method, _label)
            SCENARIO_IMPACT_RESULTS[_label][_method] = _res
            _names = ['raw'] + [_n for _n in _res.keys() if _n != 'raw']
            _rows = []
            for _n in _names:
                r = _res[_n]
                if _n == 'raw' or r['mcnemar'] is None:
                    mc_str = 'baseline reference'
                else:
                    stat, p, n01, n10 = r['mcnemar']
                    mc_str = f'{stat:.1f} (p={p:.3e}, n01={n01}, n10={n10})'
                _rows.append([_n, r['train_acc'], r['test_acc'], r['train_f1'], r['test_f1'], mc_str])
            print(f'\n{LABEL_DISPLAY[_label]} — {_method.capitalize()} aggregation')
    # ── run full sweep ─────────────────────────────────────────────────────────────
            print(tabulate(_rows, headers=['Scenario', 'Tr Acc', 'Te Acc', 'Tr F1', 'Te F1', 'McNemar'], tablefmt='github', floatfmt='.4f'))
    return (SCENARIO_IMPACT_RESULTS,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Scenario Impact Ranking

    Rank each variant by accuracy Δ, F1 Δ, and McNemar p-value across all aggregation methods and labels.
    """)
    return


@app.cell
def _(
    AGG_METHODS,
    LABELS,
    LABEL_DISPLAY,
    SCENARIO_IMPACT_RESULTS,
    VARIANT_OBJS,
    np,
    results_dict_to_impact_tuple,
    tabulate,
):
    SCENARIO_NAMES = [_v['name'] for _v in VARIANT_OBJS]
    for _label in LABELS:
        for _method in AGG_METHODS:
            _res = SCENARIO_IMPACT_RESULTS[_label][_method]
            _tup = results_dict_to_impact_tuple(_res)
            acc_d = np.array([x - _tup[1][0] for x in _tup[1][1:]])
            f1_d = np.array([x - _tup[3][0] for x in _tup[3][1:]])  # deltas from baseline (index 0)
            _pvals = [t[1] for t in _tup[4][1:]]
            safe_p = [p if p == p else 1.0 for p in _pvals]
            acc_rk = (np.argsort(np.argsort(-acc_d)) + 1).tolist()
            f1_rk = (np.argsort(np.argsort(-f1_d)) + 1).tolist()
            p_rk = (np.argsort(np.argsort(safe_p)) + 1).tolist()
            _rows = [[SCENARIO_NAMES[_i], f'{acc_d[_i]:+.4f}', f'{f1_d[_i]:+.4f}', f'{safe_p[_i]:.3e}', acc_rk[_i], f1_rk[_i], p_rk[_i]] for _i in range(len(SCENARIO_NAMES))]
            print(f'\n### {LABEL_DISPLAY[_label]} — {_method.capitalize()} Aggregation')
            print(tabulate(_rows, headers=['Scenario', 'Acc Δ', 'F1 Δ', 'P-Value', 'Acc Rank', 'F1 Rank', 'P Rank'], tablefmt='github'))
    return (SCENARIO_NAMES,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Scenario Impact Visualization

    Aurora bar charts showing each scenario's accuracy / F1 deviation from the `baseline_nofilters` reference.
    """)
    return


@app.cell
def _(
    AGG_METHODS,
    LABELS,
    SCENARIO_IMPACT_RESULTS,
    SCENARIO_NAMES,
    results_dict_to_impact_tuple,
    visualize_scenario_impact,
):
    for _label in LABELS:
        for _method in AGG_METHODS:
            _tup = results_dict_to_impact_tuple(SCENARIO_IMPACT_RESULTS[_label][_method])
            for metric, scores in [('Accuracy', _tup[1]), ('F1', _tup[3])]:
                visualize_scenario_impact(scores, SCENARIO_NAMES, _label, metric, _method)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # McNemar Significance Visualization

    Aurora bar charts of $-\\log_{10}(p)$ from McNemar's test (orange = significant at p < 0.05).
    """)
    return


@app.cell
def _(
    AGG_METHODS,
    LABELS,
    SCENARIO_IMPACT_RESULTS,
    SCENARIO_NAMES,
    results_dict_to_impact_tuple,
    visualize_mcnemar_significance,
):
    for _label in LABELS:
        for _method in AGG_METHODS:
            _tup = results_dict_to_impact_tuple(SCENARIO_IMPACT_RESULTS[_label][_method])
            _pvals = [t[1] for t in _tup[4][1:]]  # skip baseline (index 0)
            visualize_mcnemar_significance(_pvals, SCENARIO_NAMES, _label, title=f'{_label.upper()} McNemar Significance  ({_method.capitalize()} Aggregation)')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Centroid Shift Analysis

    Two views:
    1. **Per-vital bar chart** (Aurora style) — deviation of each vital's mean centroid between baseline and variant, split by ICU+/ICU−/Mortality+/Mortality−.
    2. **PCA scatter** — 2-D projection of full-feature centroid shift vectors.
    """)
    return


@app.cell
def _(
    AGG_METHODS,
    BASELINE,
    MAX_RECORDS_PER_SCENARIO,
    VARIANT_OBJS,
    VITAL_NAMES,
    build_record_aggregated_features,
    extract_vital_centroid,
    maybe_sample_record_ids,
    pd,
    subset_X_by_patients,
    tqdm,
    visualize_centroid_shift_v2,
):
    for _method in AGG_METHODS:
        print(f'\n=== Centroid shift bars: {_method} ===')
        _base_pat = maybe_sample_record_ids(BASELINE['patients'], MAX_RECORDS_PER_SCENARIO)
        _X_base_sm = subset_X_by_patients(BASELINE['X'], _base_pat)
        _X_base_agg = build_record_aggregated_features(_X_base_sm, _method).loc[_base_pat.index]
        for _v in tqdm(VARIANT_OBJS, desc=f'{_method} centroid bars'):
            _v_pat = maybe_sample_record_ids(_v['patients'], MAX_RECORDS_PER_SCENARIO)
            _X_vf = _v.get('X') or pd.read_hdf(str(_v['datafile']), 'vitals_labs')
            _X_vsm = subset_X_by_patients(_X_vf, _v_pat)
            _X_vagg = build_record_aggregated_features(_X_vsm, _method).loc[_v_pat.index]
            shift_tuples = []
            for _label in ('icu_los', 'mortality'):
                for polarity in ('pos', 'neg'):
                    _cb = extract_vital_centroid(_X_base_agg, _base_pat, _label, VITAL_NAMES, polarity)
                    _cv = extract_vital_centroid(_X_vagg, _v_pat, _label, VITAL_NAMES, polarity)
                    shift_tuples.append((_cb, _cv))
            titles = ['ICU +', 'ICU −', 'Mortality +', 'Mortality −']
            visualize_centroid_shift_v2(shift_tuples, titles, _v['name'], vital_names=VITAL_NAMES)
            try:
                del _X_vf, _X_vsm, _X_vagg
            except Exception:
                pass
    return


@app.cell
def _(
    AGG_METHODS,
    BASELINE,
    LABELS,
    LABEL_DISPLAY,
    MAX_RECORDS_PER_SCENARIO,
    PCA,
    VARIANT_OBJS,
    build_record_aggregated_features,
    compute_centroid,
    generate_hex_gradient,
    maybe_sample_record_ids,
    np,
    pd,
    plt,
    subset_X_by_patients,
):
    for _method in AGG_METHODS:
        _base_pat = maybe_sample_record_ids(BASELINE['patients'], MAX_RECORDS_PER_SCENARIO)
        _X_base_sm = subset_X_by_patients(BASELINE['X'], _base_pat)
        _X_base_agg = build_record_aggregated_features(_X_base_sm, _method).loc[_base_pat.index]
        variant_aggs = []
        for _v in VARIANT_OBJS:
            _v_pat = maybe_sample_record_ids(_v['patients'], MAX_RECORDS_PER_SCENARIO)
            _X_vf = _v.get('X') or pd.read_hdf(str(_v['datafile']), 'vitals_labs')
            _X_vsm = subset_X_by_patients(_X_vf, _v_pat)
            _X_vagg = build_record_aggregated_features(_X_vsm, _method).loc[_v_pat.index]
            variant_aggs.append({'name': _v['name'], 'pat': _v_pat, 'X': _X_vagg, 'cols': _X_vagg.columns})
            try:
                del _X_vf, _X_vsm
            except Exception:
                pass
        global_shared = _X_base_agg.columns
        for va in variant_aggs:
            global_shared = global_shared.intersection(va['cols'])
        Xb_g = _X_base_agg[global_shared]
        cmap_v = generate_hex_gradient(_AURORA, len(VARIANT_OBJS) + 2)[1:-1]
        _fig, axes = plt.subplots(1, 2, figsize=(16, 6), facecolor=_BG)
        for _ax, _label in zip(axes, LABELS):
            _cb = compute_centroid(Xb_g, _base_pat, _label)
            if _cb is None:
                _ax.set_title(f'{LABEL_DISPLAY[_label]} (no baseline centroid)', color='white')
                continue
            shift_vecs, names_pca = ([], [])
            for _i, va in enumerate(variant_aggs):
                _cv = compute_centroid(va['X'][global_shared], va['pat'], _label)
                if _cv is None:
                    continue
                n_drop = len(_X_base_agg.columns) - len(va['cols'])
                lbl = va['name'] + (f' (-{n_drop})' if n_drop else '')
                shift_vecs.append(_cv - _cb)
                names_pca.append(lbl)
            if len(shift_vecs) < 2:
                _ax.set_title(f'{LABEL_DISPLAY[_label]} (insufficient variants)', color='white')
                continue
            Z = PCA(n_components=2, random_state=0).fit_transform(np.vstack(shift_vecs))
            _ax.set_facecolor(_BG)
            _ax.scatter([0], [0], marker='*', s=200, c='#f39c12', zorder=5, label='baseline')
            for _i, (nm, zp) in enumerate(zip(names_pca, Z)):
                _c = cmap_v[_i % len(cmap_v)]
                _ax.scatter([zp[0]], [zp[1]], s=60, color=_c, zorder=4)
                _ax.annotate(nm, (zp[0], zp[1]), fontsize=7, alpha=0.85, color=_c)
                _ax.plot([0, zp[0]], [0, zp[1]], linewidth=0.8, color=_c, alpha=0.4)
            _ax.set_title(f'{LABEL_DISPLAY[_label]}', color='white')
            _ax.set_xlabel('PC1', color='white')
            _ax.set_ylabel('PC2', color='white')
            _ax.grid(color='#3a3b3d', linestyle=':', linewidth=0.5, alpha=0.4)
            _ax.legend(facecolor=_BG, labelcolor='white', fontsize=8)
        plt.suptitle(f'Centroid Shift PCA  (aggregation = {_method})', color='white', fontsize=14)
        plt.tight_layout()
        plt.show()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Extra Visualizations

    Prevalence by scenario and record-length distributions.
    """)
    return


@app.cell
def _(
    BASELINE,
    LABELS,
    Path,
    VARIANT_OBJS,
    generate_hex_gradient,
    np,
    pd,
    plt,
    visualize_scenario_impact,
):
    # ── Prevalence ─────────────────────────────────────────────────────────────────
    prev_rows = []
    for _v in [BASELINE] + VARIANT_OBJS:
        for _label in LABELS:
            y = _select_pos_label(_v['patients'], _label)
            prev_rows.append({'scenario': _v['name'], 'target': _label, 'prev': float(y.mean())})
    df_prev = pd.DataFrame(prev_rows)
    for _label in LABELS:
        sub = df_prev[df_prev['target'] == _label]
        _names = sub['scenario'].tolist()
        prevs = sub['prev'].tolist()
        visualize_scenario_impact(prevs, _names[1:], label=_label, metric='Prevalence', aggregation_method='')
    palette = generate_hex_gradient(_AURORA, len(VARIANT_OBJS) + 3)[1:-1]
    _fig, _ax = plt.subplots(figsize=(12, 7), facecolor=_BG)  # Build as "scores" list with baseline first for visualize_scenario_impact reuse
    _ax.set_facecolor(_BG)
    for _i, _v in enumerate([BASELINE] + VARIANT_OBJS):
        sc_dir = Path(_v['datafile']).parent
        fp_path = sc_dir / 'fenceposts.npy'
        if not fp_path.exists():
            continue
        fp = np.load(str(fp_path))
        lens = fp + 1
    # ── Record-length KDE ──────────────────────────────────────────────────────────
        _c = palette[_i % len(palette)]
        _ax.hist(lens, bins=50, density=True, alpha=0.25, color=_c, label=_v['name'])
        from scipy.stats import gaussian_kde
        try:
            kde = gaussian_kde(lens)
            xs = np.linspace(lens.min(), lens.max(), 300)
            _ax.plot(xs, kde(xs), color=_c, linewidth=1.5)
        except Exception:
            pass
    _ax.set_xlabel('Record length (max hours_in + 1)', color='white')
    _ax.set_ylabel('Density', color='white')
    _ax.set_title('Distribution of Record Lengths by Scenario', color='white')
    _ax.tick_params(colors='white')
    _ax.legend(facecolor=_BG, labelcolor='white', fontsize=8)
    _ax.grid(color='#3a3b3d', linestyle=':', linewidth=0.5, alpha=0.4)  # KDE via simple Gaussian
    plt.tight_layout()
    plt.show()
    return


if __name__ == "__main__":
    app.run()

