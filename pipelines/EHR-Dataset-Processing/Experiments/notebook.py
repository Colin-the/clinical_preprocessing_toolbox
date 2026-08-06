import marimo

__generated_with = "0.23.1"
app = marimo.App(width="full")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # EHR Filter Impact Analysis

    The main entry point for this pipeline. Pick a dataset at the top and
    everything below re-runs against it — that's Marimo's reactive execution, and
    it's why this replaced the old per-dataset Jupyter notebooks: one file
    instead of three that drifted apart.

    The argument the notebook builds, section by section:

    1. **Length analysis** — how unevenly the vitals are actually charted. Heart
       rate is near-continuous, temperature is every few hours. This is the
       problem everything downstream is reacting to.
    2. **Filtered datasets** — apply each of the 11 filters independently, so
       every filter's effect can be attributed to that filter alone.
    3. **Filter impact** — accuracy, F1 and McNemar for each, per label.
    4. **Centroid shift** — did the filter clean the data, or just quietly change
       which patients are in it? A big accuracy gain paired with a big centroid
       shift usually means the hard cases got thrown out.

    Run with `marimo edit Experiments/notebook.py`.

    Before you start: `Experiments/apply_dataset_filter.py` must have been run
    for this dataset and each aggregation method you care about. The cells below
    load cached datasets and will build them on the spot if they're missing,
    which on a full cohort takes a very long time inside an interactive session.
    """)
    return


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Dataset Selection
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    dataset_selection = mo.ui.dropdown(
        options = ['mimic-iii', 'mimic-iv', 'eicu'],
        value = 'mimic-iii',
        label = 'Select a dataset'
    )
    return (dataset_selection,)


@app.cell
def _(dataset_selection):
    dataset_selection
    return


@app.cell
def _(dataset_selection):
    DATASET_NAME = dataset_selection.value
    return (DATASET_NAME,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Notebook Settings
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    plot_theme_selection = mo.ui.dropdown(
        options=['light', 'dark'],
        value = 'light',
        label= 'Select a plot theme'
    )
    return (plot_theme_selection,)


@app.cell
def _(plot_theme_selection):
    plot_theme_selection
    return


@app.cell
def _(plot_theme_selection):
    PLOT_THEME = '#191a1c' if plot_theme_selection.value == 'dark' else '#ffffff'
    return (PLOT_THEME,)


@app.cell(hide_code=True)
def _(mo):
    lazy_loading_selection = mo.ui.dropdown(
        options=['on', 'off'],
        value = 'off',
        label= 'Set lazy loading'
    )
    return (lazy_loading_selection,)


@app.cell
def _(lazy_loading_selection):
    lazy_loading_selection
    return


@app.cell
def _(lazy_loading_selection, mo):
    LAZY_LOADING = True if lazy_loading_selection.value == 'on' else False

    def lazy_loader(fn):
        return mo.lazy(fn) if LAZY_LOADING else fn()

    return (lazy_loader,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Imports
    """)
    return


@app.cell
def _():
    import sys
    from pathlib import Path
    sys.path.append(str(Path().resolve().parent))

    # from concurrent.futures import ThreadPoolExecutor, as_completed
    # from concurrent.futures import ProcessPoolExecutor, as_completed
    import numpy as np
    import pandas as pd

    from collections import defaultdict
    from pathlib import Path

    return Path, defaultdict, np, pd


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Project Root
    """)
    return


@app.cell
def _():
    from Managers.path_manager import get_project_root 
    PROJECT_ROOT = get_project_root()
    return (PROJECT_ROOT,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Aggregation Methods

    Five ways of collapsing an hour's worth of readings into one number. Mean and
    median describe the *level*; the three deviation measures describe how much
    the vital moved within the hour, which for something like heart rate
    variability may carry more signal than the level does.

    Which one you pick is itself a preprocessing choice, so every experiment below
    is repeated across all five rather than committing to one. MIMIC_Extract
    implements the same five — change this list and you have to change it there
    too, or the cross-pipeline comparison stops being like-for-like.
    """)
    return


@app.cell
def _():
    AGGREGATION_METHODS = ['mean', 'median', 'standard deviation', 'mean deviation', 'maximum deviation']
    return (AGGREGATION_METHODS,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Vitals

    The seven vitals and the range each one is allowed to take. These bounds drive
    the per-vital outlier filters — anything outside gets dropped as a charting
    error.

    They're deliberately generous, not clinical normals. A heart rate of 250 is
    alarming but real; 900 is a typo. The filters are meant to catch data-entry
    mistakes, not unusual patients, and tightening these towards "normal" would
    quietly delete exactly the sick patients we're trying to predict.

    Temperature's floor of 21 °C is the one to watch: it exists to catch
    unconverted Fahrenheit readings that slipped past the processing scripts.
    """)
    return


@app.cell
def _(mo, pd):
    VITALS = {
        'heart rate': [(1, 599), 'bpm'],
        'systolic blood pressure': [(1, 399), 'mmHg'],
        'diastolic blood pressure': [(1, 299), 'mmHg'],
        'mean blood pressure': [(1, 299), 'mmHg'],
        'respiration rate': [(1, 69), 'breaths/min'],
        'temperature': [(21, 49), 'C'],
        'oxygen saturation': [(1, 99), '%']
    }

    mo.ui.table(pd.DataFrame.from_dict(VITALS, orient="index", columns=["range", "unit"]), selection=None)
    return (VITALS,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Raw Datasets
    ### Load Processed EHR Data
    The database data is not directly suitable for analysis, so it has been transformed into a structured timeseries format. Each patient record is organized into a 24 hour window with 7 vital sign features. For each hour and each vital sign, there are N observations, since the number of measurements per hours is variable.
    """)
    return


@app.cell
def _(DATASET_NAME, PROJECT_ROOT, Path):
    from Managers.serialization_manager import load_data
    TRANSFORMED_EHR_DATA = load_data(Path(str(PROJECT_ROOT / 'Data' / DATASET_NAME / 'processed_record_ehr.pkl')))
    return (TRANSFORMED_EHR_DATA,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Length of Cells Across All Timeseries

    Before touching the values, look at how *many* of them there are. Counting the
    measurements in each (hour, vital) cell across the whole cohort gives the
    charting-density picture, and it's uneven by a lot: continuously-monitored
    vitals have an order of magnitude more readings per hour than intermittently
    charted ones.

    This is the motivation for everything that follows. "Missing data" here mostly
    isn't missing — it's a vital that was never going to be charted that often in
    the first place, which is a very different thing to impute around.
    """)
    return


@app.cell
def _(PLOT_THEME, TRANSFORMED_EHR_DATA, lazy_loader, mo, np, pd):
    from Managers.visualization_manager_v2 import surface_plot, heatmap

    # Counting list lengths, not summarising values — this measures observation
    # density. Handles both ndarray and list cells because older pickles stored
    # one and newer ones the other.
    transformed_ehr_data_lengths = [record.timeseries.map(lambda x: x.size if isinstance(x, np.ndarray) else len(x) if isinstance(x, list) else 0) for record in TRANSFORMED_EHR_DATA]

    # Note these are stats over *counts*, unrelated to AGGREGATION_METHODS above —
    # 'std' here means the spread in how often a vital was charted.
    length_statistic_methods = ['mean', 'median', 'std', 'max', 'min']
    transformed_ehr_data_aggregated_lengths = {length_statistic_method: pd.concat(transformed_ehr_data_lengths).groupby(level=0).agg(length_statistic_method) for length_statistic_method in length_statistic_methods}

    # Accordion + lazy_loader so only the expanded panel renders. Drawing all ten
    # figures eagerly makes the notebook painful to open.
    mo.accordion({
        length_statistic_method.title(): lazy_loader(lambda length_statistic_method=length_statistic_method:
            mo.hstack([
                surface_plot(transformed_ehr_data_aggregated_lengths[length_statistic_method], title=f'{length_statistic_method.capitalize()} 3D Surface', y_title='Hour', z_title=f'{length_statistic_method.capitalize()} Length', background_colour=PLOT_THEME),
                heatmap(transformed_ehr_data_aggregated_lengths[length_statistic_method], title=f'{length_statistic_method.capitalize()} Heatmap', y_title='Hour', background_colour=PLOT_THEME)
            ], justify='center', gap=3)
            )
            for length_statistic_method, dataframe in transformed_ehr_data_aggregated_lengths.items()
    })
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Aggregate Data

    Collapse each cell's list of readings to a single number, giving the 24×7
    matrix the models actually train on. This is the "raw" baseline everything
    later gets compared against — raw meaning *unfiltered*, not unaggregated,
    since nothing can be tensorised until the lists are gone.

    Cached per aggregation method, so this is fast on a re-run and slow the first
    time.
    """)
    return


@app.cell
def _(AGGREGATION_METHODS, DATASET_NAME, TRANSFORMED_EHR_DATA, mo):
    from Managers.dataset_manager import create_raw_dataset, load_raw_dataset, raw_dataset_exists

    def generate_raw_datasets():
        raw_datasets = dict()
        for aggregation_method in mo.status.progress_bar(AGGREGATION_METHODS, title='Flattening raw data', completion_title='Flattened raw data'):
            if raw_dataset_exists(DATASET_NAME, aggregation_method):
                raw_datasets[aggregation_method] = load_raw_dataset(DATASET_NAME, aggregation_method)
            else:
                raw_datasets[aggregation_method] = create_raw_dataset(DATASET_NAME, TRANSFORMED_EHR_DATA, aggregation_method)
        return raw_datasets

    RAW_DATASETS = generate_raw_datasets()
    return (RAW_DATASETS,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Filtered Datasets

    Each filter is applied to the raw data **independently**, never stacked. That's
    the design decision this whole section rests on: with filters chained, an
    accuracy change tells you nothing about which filter caused it. One at a time
    costs 12 datasets per aggregation method but every number below is
    attributable.

    The boolean beside each filter is `pre_aggregate` — whether it runs before or
    after the lists collapse to scalars. The seven per-vital outlier filters need
    the raw lists; the four structural ones need scalars to test with `isna()`.
    Get it backwards and nothing errors, the filter just stops doing anything, so
    the flag is stored explicitly here rather than inferred from position.
    """)
    return


@app.cell
def _():
    from Managers.ehr_filter_manager import heart_rate_filter, systolic_blood_pressure_filter, diastolic_blood_pressure_filter, mean_blood_pressure_filter, respiration_rate_filter, temperature_filter, oxygen_saturation_filter, fill_missing_data_filter, long_missing_segment_filter, long_gap_filter, high_invalid_data_filter, aggregate, aggregate_filter, all_vitals_filter

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
        'all vitals': (all_vitals_filter, True)
    }
    return (
        FILTERS,
        all_vitals_filter,
        fill_missing_data_filter,
        high_invalid_data_filter,
        long_gap_filter,
        long_missing_segment_filter,
    )


@app.cell(hide_code=True)
def _(FILTERS, mo):
    mo.ui.table(
        [
            {
                "Filter": filter_name.title(),
                "Pre-aggregate": flag
            }
            for filter_name, (_, flag) in FILTERS.items()
        ],
        pagination=False,
        selection=None,
    )
    return


@app.cell
def _(
    AGGREGATION_METHODS,
    DATASET_NAME,
    FILTERS,
    TRANSFORMED_EHR_DATA,
    VITALS,
    mo,
):
    from Managers.dataset_manager import create_filter_dataset, filtered_dataset_exists, load_filter_dataset

    def generate_filtered_datasets():
        filtered_datasets = {aggregation_method: dict() for aggregation_method in AGGREGATION_METHODS}

        for aggregation_method in mo.status.progress_bar(AGGREGATION_METHODS, title="Applying filters"):
            for filter_name, (filter_function, pre_aggregate) in FILTERS.items():
                if filtered_dataset_exists(DATASET_NAME, aggregation_method, filter_name):
                    filtered_datasets[aggregation_method][filter_name] = load_filter_dataset(DATASET_NAME, aggregation_method, filter_name)
                else:
                    filtered_datasets[aggregation_method][filter_name] = create_filter_dataset(DATASET_NAME, TRANSFORMED_EHR_DATA, aggregation_method, filter_name, filter_function, VITALS, pre_aggregate)

        return filtered_datasets


    # FILTERED_DATASETS[aggregation][filter] is a 3-tuple and you almost always
    # want [1], the dataset itself. Note [2] (the change tracker) comes back None
    # from create_filter_dataset but populated from load_filter_dataset — so
    # whether it's usable depends on whether this was a cache hit.
    FILTERED_DATASETS = generate_filtered_datasets()
    return (FILTERED_DATASETS,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Combination Filters

    The one place filters do get stacked: clean every vital's outliers first, then
    apply one structural filter. It's the realistic ordering — you'd want to
    remove impossible readings before deciding a record is too sparse to keep,
    since an outlier that gets dropped becomes a gap.

    Currently defined but not generated — the cell that builds them is commented
    out, because it's another 20 datasets per aggregation method and the
    single-filter results haven't been exhausted yet. Uncomment when they have.
    """)
    return


@app.cell
def _(
    all_vitals_filter,
    fill_missing_data_filter,
    high_invalid_data_filter,
    long_gap_filter,
    long_missing_segment_filter,
):
    from Managers.ehr_filter_manager import combination_filter

    COMBINATION_FILTERS = {
        'all vitals fill missing data': (all_vitals_filter, fill_missing_data_filter),
        'all vitals long missing segment': (all_vitals_filter, long_missing_segment_filter),
        'all vitals long gap': (all_vitals_filter, long_gap_filter),
        'all vitals high invalid data': (all_vitals_filter, high_invalid_data_filter),
    }
    return (COMBINATION_FILTERS,)


@app.cell
def _(COMBINATION_FILTERS, mo):
    mo.ui.table(
        [
            {
                "Combination Filter": filter_name.title(),
                "Filter 1": filter_function[0],
                "Filter 2": filter_function[1]
            }
            for filter_name, filter_function in COMBINATION_FILTERS.items()
        ],
        pagination=False,
        selection=None,
    )
    return


@app.cell
def _():
    # TODO: Uncomment and run for combination filters

    # from Managers.dataset_manager import create_combination_filter_dataset

    # def generate_combined_filtered_datasets():
    #     filtered_datasets = {aggregation_method: dict() for aggregation_method in AGGREGATION_METHODS}

    #     for aggregation_method in mo.status.progress_bar(AGGREGATION_METHODS, title="Applying filters"):
    #         for filter_name, filter_function in COMBINATION_FILTERS.items():
    #             if filtered_dataset_exists(DATASET_NAME, aggregation_method, filter_name):
    #                 filtered_datasets[aggregation_method][filter_name] = load_filter_dataset(DATASET_NAME, aggregation_method, filter_name)
    #             else:
    #                 filtered_datasets[aggregation_method][filter_name] = create_combination_filter_dataset(DATASET_NAME, TRANSFORMED_EHR_DATA, aggregation_method, filter_name, filter_function, VITALS)

    #     return filtered_datasets

    # combined_filtered_datasets = generate_combined_filtered_datasets()
    # for x in combined_filtered_datasets:
    #     FILTERED_DATASETS[x].update(combined_filtered_datasets[x])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Filter Impact Analysis

    The core result. For each filter, train a random forest and ask whether it
    beats the unfiltered baseline — and whether any difference is real or just
    seed noise.

    Everything is repeated over four fixed seeds, with the same seed driving the
    train/test split for every dataset in a given round. That's what makes the
    comparison fair: differences come from the filter rather than from which
    patients happened to land in the test set.

    Read accuracy and McNemar together and neither alone. Accuracy says which is
    better, McNemar says whether "better" survived the noise, and with 11 filters
    on an uncorrected p=0.05 threshold you should expect roughly one spurious
    significant result per chart.
    """)
    return


@app.cell
def _():
    LABELS = ['icu', 'mortality']
    return (LABELS,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Computing Filter Impact Scores
    """)
    return


@app.cell
def _(
    AGGREGATION_METHODS,
    DATASET_NAME,
    FILTERED_DATASETS,
    PROJECT_ROOT,
    Path,
    RAW_DATASETS,
):
    from Managers.serialization_manager import save_object, load_object
    from Managers.evaluation_manager import evaluate_filter_impact

    # Arbitrary but *fixed* — the point is reproducibility across runs, and these
    # same four seeds are used by the cross-pipeline comparison notebook so the
    # two sides see identical splits. Don't change them casually; the cached
    # *_filter_impact.pkl files were computed with these and nothing checks.
    RANDOM_SEEDS = [22, 985, 439, 81]

    def get_filter_impact(label: str):
        results_dict = dict()

        for aggregation_method in AGGREGATION_METHODS:
            file_path = Path(f'{PROJECT_ROOT}/Data/{DATASET_NAME}/{aggregation_method}/{label}_filter_impact.pkl')

            if file_path.exists():
                filter_impact_results = load_object(str(file_path))
            else:
                filter_impact_results = evaluate_filter_impact(
                    raw_dataset=RAW_DATASETS[aggregation_method],
                    filtered_datasets={name: data[1] for name, data in FILTERED_DATASETS[aggregation_method].items()},
                    target_label=label,
                    seeds = RANDOM_SEEDS
                )
                save_object(filter_impact_results, str(file_path))

            results_dict[aggregation_method] = filter_impact_results
        return results_dict

    return get_filter_impact, load_object, save_object


@app.cell
def _(get_filter_impact):
    ICU_FILTER_IMACT_RESULTS = get_filter_impact('icu')
    MORTALITY_FILTER_IMPACT_RESULTS = get_filter_impact('mortality')
    return ICU_FILTER_IMACT_RESULTS, MORTALITY_FILTER_IMPACT_RESULTS


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Visualizing Filter Impact Scores
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### ICU
    """)
    return


@app.cell
def _(
    AGGREGATION_METHODS,
    FILTERS,
    ICU_FILTER_IMACT_RESULTS,
    PLOT_THEME,
    lazy_loader,
    mo,
):
    from Managers.visualization_manager_v2 import filter_impact_table, filter_impact_plot, mcnemar_plot

    mo.accordion({
        aggregation_method.title(): lazy_loader(lambda aggregation_method=aggregation_method: mo.vstack([
            mo.md("**Filter Impact Results**"),
            filter_impact_table(ICU_FILTER_IMACT_RESULTS[aggregation_method], list(FILTERS.keys()), delta=False),
            mo.md("**Filter Impact Results - Deviation From Baseline**"),
            filter_impact_table(ICU_FILTER_IMACT_RESULTS[aggregation_method], list(FILTERS.keys()), delta=True),
            mo.center(
                filter_impact_plot(ICU_FILTER_IMACT_RESULTS[aggregation_method][1], list(FILTERS.keys()), 'ICU', 'Testing Accuracy', aggregation_method, background=PLOT_THEME)
            ),
            mo.center(
                filter_impact_plot(ICU_FILTER_IMACT_RESULTS[aggregation_method][3], list(FILTERS.keys()), 'ICU', 'Testing F1', aggregation_method, background=PLOT_THEME)
            ),
            mo.center(
                mcnemar_plot([x[1] for x in ICU_FILTER_IMACT_RESULTS[aggregation_method][-1]][1:], list(FILTERS.keys()), 'ICU', aggregation_method, background=PLOT_THEME)
            )
        ], gap=2))
        for aggregation_method in AGGREGATION_METHODS
    })
    return filter_impact_plot, filter_impact_table, mcnemar_plot


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### Mortality
    """)
    return


@app.cell
def _(
    AGGREGATION_METHODS,
    FILTERS,
    MORTALITY_FILTER_IMPACT_RESULTS,
    PLOT_THEME,
    filter_impact_plot,
    filter_impact_table,
    lazy_loader,
    mcnemar_plot,
    mo,
):
    mo.accordion({
        aggregation_method.title(): lazy_loader(lambda aggregation_method=aggregation_method: mo.vstack([
            mo.md("**Filter Impact Results**"),
            filter_impact_table(MORTALITY_FILTER_IMPACT_RESULTS[aggregation_method], list(FILTERS.keys()), delta=False),
            mo.md("**Filter Impact Results - Deviation From Baseline**"),
            filter_impact_table(MORTALITY_FILTER_IMPACT_RESULTS[aggregation_method], list(FILTERS.keys()), delta=True),
            mo.center(
                filter_impact_plot(MORTALITY_FILTER_IMPACT_RESULTS[aggregation_method][1], list(FILTERS.keys()), 'Mortality', 'Testing Accuracy', aggregation_method, background=PLOT_THEME)
            ),
            mo.center(
                filter_impact_plot(MORTALITY_FILTER_IMPACT_RESULTS[aggregation_method][3], list(FILTERS.keys()), 'Mortality', 'Testing F1', aggregation_method, background=PLOT_THEME)
            ),
            mo.center(
                mcnemar_plot([x[1] for x in MORTALITY_FILTER_IMPACT_RESULTS[aggregation_method][-1]][1:], list(FILTERS.keys()), 'Mortality', aggregation_method, background=PLOT_THEME)
            )
        ], gap=2))
        for aggregation_method in AGGREGATION_METHODS
    })
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Centroid Shift Analysis

    The sanity check on everything above. Accuracy going up is not automatically
    good news: a filter that discards the ambiguous, hard-to-classify patients
    will improve the score while making the task easier rather than the data
    cleaner, and the accuracy number alone cannot tell those two apart.

    Comparing class centroids before and after can. A filter that removes noise
    should leave the centre of each class roughly where it was; one that removes
    a *kind of patient* moves it. So the combination to be suspicious of is a
    large accuracy gain alongside a large centroid shift.

    Computed per (label, aggregation, filter, positive/negative), which is why
    this section is slow on a first run — but it's all cached under
    `Data/<dataset>/<aggregation>/centroids/` afterwards.

    Read the shift bars next to the density plots. A shift only means something
    relative to how spread out the class was to begin with.
    """)
    return


@app.cell
def _(
    AGGREGATION_METHODS,
    DATASET_NAME,
    FILTERED_DATASETS,
    FILTERS,
    LABELS,
    PROJECT_ROOT,
    Path,
    RAW_DATASETS,
    defaultdict,
    load_object,
    mo,
    save_object,
):
    from Managers.evaluation_manager import compute_dataset_centroid

    def get_centroids():
        num_iterations = len(LABELS) * len(AGGREGATION_METHODS) * (1 + len(FILTERS)) * 2
        centroids = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
        points = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

        with mo.status.progress_bar(total=num_iterations, title='Computing centroids') as progress:
            for label in LABELS:
                for aggregation_method in AGGREGATION_METHODS:
                    for filter in ['raw'] + list(FILTERS.keys()):
                        for sign in ['pos', 'neg']:
                            centroids_dir = PROJECT_ROOT / Path('Data') / DATASET_NAME / aggregation_method / 'centroids'
                            centroids_dir.mkdir(parents=True, exist_ok=True)

                            file_path = centroids_dir / f'{label}_{filter}_{sign}.pkl'

                            if file_path.exists():
                                centroids[label][aggregation_method][filter][sign], points[label][aggregation_method][filter][sign] = load_object(file_path)
                            else:
                                if filter == 'raw':
                                    centroids[label][aggregation_method][filter][sign], points[label][aggregation_method][filter][sign] = compute_dataset_centroid(RAW_DATASETS[aggregation_method], label, sign)
                                else:
                                    centroids[label][aggregation_method][filter][sign], points[label][aggregation_method][filter][sign] = compute_dataset_centroid(FILTERED_DATASETS[aggregation_method][filter][1], label, sign)

                                save_object((centroids[label][aggregation_method][filter][sign], points[label][aggregation_method][filter][sign]), file_path)

                            progress.update(increment=1)

        return centroids, points

    CENTROIDS, POINTS = get_centroids()
    return CENTROIDS, POINTS


@app.cell
def _(
    AGGREGATION_METHODS,
    CENTROIDS,
    FILTERS,
    PLOT_THEME,
    POINTS,
    VITALS,
    lazy_loader,
    mo,
):
    from Managers.visualization_manager_v2 import centroid_shift_plot, centroid_plot

    mo._runtime.context.get_context().marimo_config["runtime"]["output_max_bytes"] = 10000000000

    def get_centroid_pairs(aggregation_method: str, filter: str):
        return [
            (CENTROIDS['icu'][aggregation_method]['raw']['pos'], CENTROIDS['icu'][aggregation_method][filter]['pos']),
            (CENTROIDS['icu'][aggregation_method]['raw']['neg'], CENTROIDS['icu'][aggregation_method][filter]['neg']),
            (CENTROIDS['mortality'][aggregation_method]['raw']['pos'], CENTROIDS['mortality'][aggregation_method][filter]['pos']),
            (CENTROIDS['mortality'][aggregation_method]['raw']['neg'], CENTROIDS['mortality'][aggregation_method][filter]['neg'])
        ]

    def get_point_pairs(aggregation_method: str, filter: str):
        return [
            (POINTS['icu'][aggregation_method]['raw']['pos'], POINTS['icu'][aggregation_method][filter]['pos']),
            (POINTS['icu'][aggregation_method]['raw']['neg'], POINTS['icu'][aggregation_method][filter]['neg']),
            (POINTS['mortality'][aggregation_method]['raw']['pos'], POINTS['mortality'][aggregation_method][filter]['pos']),
            (POINTS['mortality'][aggregation_method]['raw']['neg'], POINTS['mortality'][aggregation_method][filter]['neg'])
        ]

    def attempt(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None

    mo.accordion({
        aggregation_method.title(): mo.accordion({
            filter: lazy_loader(lambda filter=filter, aggregation_method=aggregation_method:
                mo.vstack([
                    mo.center(
                        attempt(
                            centroid_shift_plot,
                            get_centroid_pairs(aggregation_method, filter),
                            ['icu pos', 'icu neg', 'mortality pos', 'mortality neg'],
                            filter,
                            list(VITALS.keys()),
                            background=PLOT_THEME
                        )
                    ),
                    mo.center(
                        attempt(
                            centroid_plot,
                            [pair[0] for pair in get_centroid_pairs(aggregation_method, filter)] + [pair[1] for pair in get_centroid_pairs(aggregation_method, filter)],
                            [pair[0] for pair in get_point_pairs(aggregation_method, filter)] + [pair[1] for pair in get_point_pairs(aggregation_method, filter)],
                            list(VITALS.keys()),
                            [x[-1] for x in VITALS.values()],
                            ["Raw ICU Pos", "Raw ICU Neg", "Raw Mort Pos", "Raw Mort Neg", "Filt ICU Pos", "Filt ICU Neg", "Filt Mort Pos", "Filt Mort Neg"],
                            use_percentile=False,
                            background=PLOT_THEME
                        )
                    ),
                    mo.center(
                        attempt(
                            centroid_plot,
                            [pair[0] for pair in get_centroid_pairs(aggregation_method, filter)] + [pair[1] for pair in get_centroid_pairs(aggregation_method, filter)],
                            [pair[0] for pair in get_point_pairs(aggregation_method, filter)] + [pair[1] for pair in get_point_pairs(aggregation_method, filter)],
                            list(VITALS.keys()),
                            [x[-1] for x in VITALS.values()],
                            ["Raw ICU Pos", "Raw ICU Neg", "Raw Mort Pos", "Raw Mort Neg", "Filt ICU Pos", "Filt ICU Neg", "Filt Mort Pos", "Filt Mort Neg"],
                            use_percentile=True,
                            background=PLOT_THEME
                        )
                    )
                ])
            )
            for filter in FILTERS.keys()
        })
        for aggregation_method in AGGREGATION_METHODS
    }, multiple=True)
    return


@app.cell
def _(
    AGGREGATION_METHODS,
    CENTROIDS,
    PLOT_THEME,
    POINTS,
    VITALS,
    mo,
):
    from Managers.visualization_manager_v2 import centroid_plot as _centroid_plot

    def _attempt(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None

    def _raw_centroids(agg):
        return [
            CENTROIDS['icu'][agg]['raw']['pos'],
            CENTROIDS['icu'][agg]['raw']['neg'],
            CENTROIDS['mortality'][agg]['raw']['pos'],
            CENTROIDS['mortality'][agg]['raw']['neg'],
        ]

    def _raw_points(agg):
        return [
            POINTS['icu'][agg]['raw']['pos'],
            POINTS['icu'][agg]['raw']['neg'],
            POINTS['mortality'][agg]['raw']['pos'],
            POINTS['mortality'][agg]['raw']['neg'],
        ]

    _labels = ["Raw ICU Pos", "Raw ICU Neg", "Raw Mort Pos", "Raw Mort Neg"]
    _vitals  = list(VITALS.keys())
    _units   = [x[-1] for x in VITALS.values()]

    mo.accordion({
        agg.title(): mo.vstack([
            mo.center(_attempt(
                _centroid_plot,
                _raw_centroids(agg), _raw_points(agg),
                _vitals, _units, _labels,
                use_percentile=False, background=PLOT_THEME
            )),
            mo.center(_attempt(
                _centroid_plot,
                _raw_centroids(agg), _raw_points(agg),
                _vitals, _units, _labels,
                use_percentile=True, background=PLOT_THEME
            )),
        ])
        for agg in AGGREGATION_METHODS
    }, multiple=True)
    return


if __name__ == "__main__":
    app.run()
