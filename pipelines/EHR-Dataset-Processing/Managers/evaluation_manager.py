"""Training and scoring for the filter-impact experiments.

Everything here runs on GPU via cuML — a filter sweep is 12 filters × 5
aggregations × 2 labels × several seeds, which is a lot of random forests. cuML's
API deliberately mirrors sklearn's, so this reads like sklearn code, but the
arrays are cupy and have to be moved back with cp.asnumpy() before anything
sklearn- or scipy-based touches them. That's the one recurring gotcha in this file.
"""

import math

import cupy as cp
import numpy as np
import torch
from typing import Any, Dict, List, Tuple
from cuml.ensemble import RandomForestClassifier
from cuml.metrics import accuracy_score
from cuml.model_selection import KFold
from scipy.stats import mode
from sklearn.metrics import f1_score
from statsmodels.stats.contingency_tables import mcnemar
from tqdm.notebook import tqdm
from tabulate import tabulate
from Entities.ehr_dataset import DatasetEHR
from Managers.dataset_manager import flatten_subset_to_cupy



def cross_validate_model(timeseries: cp.ndarray, labels: cp.ndarray, seed: int, splits: int = 4) -> float:
    """K-fold accuracy on the training split, averaged over folds.

    Empty folds score 0.0 rather than NaN or an exception. That's a compromise:
    aggressive filters can shrink a dataset enough that a fold comes out empty,
    and a 0 drags the mean down in a visible way instead of poisoning it with
    NaN. Worth remembering when reading a suspiciously low CV score — it may mean
    "folds were empty", not "the model is bad".
    """
    k_fold = KFold(n_splits=splits, shuffle=True, random_state=seed)
    fold_scores = []

    for training_index, validation_index in k_fold.split(timeseries):
        x_train = timeseries[training_index]
        x_validation = timeseries[validation_index]
        y_train = labels[training_index]
        y_validation = labels[validation_index]

        if x_train.size == 0 or x_validation.size == 0:
            fold_scores.append(0.0)
            continue

        model = RandomForestClassifier(n_estimators=300, random_state=seed)
        model.fit(x_train, y_train)
        predictions = model.predict(x_validation)
        fold_scores.append(accuracy_score(y_validation, predictions))

    return float(cp.mean(cp.array(fold_scores)))


def evaluate_dataset_label_impact(dataset: Any, label_index: int, seed: int) -> Tuple[float, float, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Train one forest on one dataset and report CV score, test score, and
    predictions on both splits.

    Splits 80/10/10 but then glues validation onto test, giving an effective
    80/20. There's no hyperparameter tuning here — nothing ever looks at the
    validation set on its own — so holding it out separately would just throw
    away 10% of the evaluation sample and make the McNemar comparisons noisier.

    Returns (cv_score, test_score, test_predictions, test_labels,
    train_predictions, train_labels). The training-split predictions exist so
    the caller can compute a training F1; expect them to look overfit — a
    random forest scores near-perfectly on its own training data.

    Predictions come back as numpy because that's what McNemar and sklearn's F1
    need downstream.
    """
    train_sub, val_sub, test_sub = dataset.split(0.8, 0.1, 0.1)

    x_train, y_train = flatten_subset_to_cupy(train_sub, label_index)
    x_test_part, y_test_part = flatten_subset_to_cupy(test_sub, label_index)
    x_validation_part, y_validation_part = flatten_subset_to_cupy(val_sub, label_index)

    if x_test_part.size > 0:
        x_test = cp.vstack([x_test_part, x_validation_part])
        y_test = cp.concatenate([y_test_part, y_validation_part])
    else:
        x_test = x_test_part
        y_test = y_test_part

    if x_train.size == 0 or x_test.size == 0:
        return 0.0, 0.0, np.zeros(len(y_test)), cp.asnumpy(y_test), np.zeros(len(y_train)), cp.asnumpy(y_train)

    cross_validation_score = cross_validate_model(x_train, y_train, seed)

    final_model = RandomForestClassifier(n_estimators=300, random_state=seed)
    final_model.fit(x_train, y_train)
    test_predictions = final_model.predict(x_test)
    test_score = accuracy_score(y_test, test_predictions)
    train_predictions = final_model.predict(x_train)

    return cross_validation_score, test_score, cp.asnumpy(test_predictions), cp.asnumpy(y_test), cp.asnumpy(train_predictions), cp.asnumpy(y_train)


def calculate_mcnemar_test(baseline_predictions: List[np.ndarray], filtered_predictions: List[np.ndarray]) -> Tuple[float, float]:
    """Is the filtered model's disagreement with the baseline more than noise?

    Takes a majority vote across seeds first, then compares the two consensus
    prediction vectors. Voting rather than pooling because a single seed's forest
    is noisy enough that McNemar would mostly be measuring seed variance; the
    majority vote asks the more useful question of whether the *filter* changes
    what the model consistently predicts.

    exact=True runs the binomial test rather than the chi-square approximation.
    Slower, but the discordant counts here are often small enough that the
    approximation misbehaves.

    Note this compares predictions against each other, not against ground truth —
    it detects that the two models disagree, not which one is right. Read it
    alongside the accuracy numbers, never on its own.

    One assumption that will bite you if it's ever violated: both prediction
    vectors have to be the same length and in the same patient order, which holds
    only because every dataset in a sweep is split with the same seed.
    """
    baseline_predictions = np.stack(baseline_predictions, axis=0)
    filter_predictions = np.stack(filtered_predictions, axis=0)

    base_majority = mode(baseline_predictions, axis=0, keepdims=True).mode[0]
    filter_majority = mode(filter_predictions, axis=0, keepdims=True).mode[0]

    table = np.zeros((2, 2), dtype=int)
    for baseline_prediction, filter_prediction in zip(base_majority.astype(int), filter_majority.astype(int)):
        table[baseline_prediction, filter_prediction] += 1

    result = mcnemar(table, exact=True)
    return float(result.statistic), float(result.pvalue)


def evaluate_filter_impact(raw_dataset: DatasetEHR, filtered_datasets: Dict[str, DatasetEHR], target_label: str,
                           seeds: List[int]) -> tuple[list[Any], list[Any], list[Any], list[Any], list[Any]]:
    """Score every filtered dataset against the unfiltered baseline.

    Returns five parallel lists, all indexed the same way with 'raw' at position
    0 — the plotting code relies on that and slices [1:] to drop the
    baseline-vs-itself comparison.

    Careful with the return values: `training_averages` is the cross-validation
    score, not training accuracy. `training_f1s` is scored on the training split
    itself, so expect it near 1.0 — a random forest memorises its training data;
    it's there to show overfit headroom, not model quality.
    """
    label_index = raw_dataset.label_index_map[target_label]

    ordered_names = ['raw'] + list(filtered_datasets.keys())
    all_datasets = {'raw': raw_dataset, **filtered_datasets}

    # Seeding torch per seed *before* the inner loop is what makes the comparison
    # fair: every dataset gets the identical train/test split for a given seed,
    # so differences come from the filter rather than from the shuffle.
    raw_results = {name: [] for name in ordered_names}
    for seed in seeds:
        torch.manual_seed(seed)
        for name in ordered_names:
            dataset = all_datasets[name]
            raw_results[name].append(evaluate_dataset_label_impact(dataset, label_index, seed))

    training_averages = []
    testing_averages = []
    mcnemar_results = []
    training_f1s = []
    testing_f1s = []

    baseline_preds = [t[2] for t in raw_results['raw']]

    for name in ordered_names:
        trials = raw_results[name]
        training_averages.append(float(np.mean([t[0] for t in trials])))
        testing_averages.append(float(np.mean([t[1] for t in trials])))
        # macro averaging so the minority class counts as much as the majority —
        # mortality prevalence is low enough that weighted F1 would mostly be
        # reporting how well we predict survival.
        train_f1_list = [f1_score(t[5], t[4], average='macro') for t in trials if len(t[4]) > 0 and len(t[5]) > 0]
        test_f1_list = [f1_score(t[3], t[2], average='macro') for t in trials if len(t[2]) > 0 and len(t[3]) > 0]
        training_f1s.append(float(np.mean(train_f1_list)) if train_f1_list else 0.0)
        testing_f1s.append(float(np.mean(test_f1_list)) if test_f1_list else 0.0)

        # 'raw' gets compared against itself here, giving p=1 at index 0.
        # Harmless, and it keeps all five lists index-aligned.
        current_preds = [t[2] for t in trials]
        stat, p_val = calculate_mcnemar_test(baseline_preds, current_preds)
        mcnemar_results.append((stat, p_val))

    return training_averages, testing_averages, training_f1s, testing_f1s, mcnemar_results

def compute_tensor_centroid(tensor: torch.Tensor):
    """Per-vital mean for one patient, ignoring hours with no measurement.

    Masked rather than using torch.nanmean because 0 has to count as missing too
    — RecordEHR.to_tensor() zero-fills NaNs, so by the time we see a tensor the
    gaps are zeros and a plain mean would drag every vital toward 0.

    A vital with no valid readings at all divides by zero and yields NaN. That's
    intentional and callers filter it out; substituting 0 would put the patient
    at the origin and skew the dataset centroid.
    """
    invalid = torch.isnan(tensor) | (tensor == 0)
    mask = ~invalid

    column_sums = torch.where(mask, tensor, 0.0).sum(dim=0)
    column_counts = mask.sum(dim=0)

    return (column_sums / column_counts).tolist()

def compute_dataset_centroid(dataset: DatasetEHR, label: str=None, polarity: str='pos'):
    """Average the per-patient centroids over one class, returning both the mean
    and the individual points behind it.

    Both are returned because the plots need both: a bar chart of how far the
    centroid moved, and a violin showing the spread it moved within. A shift
    that's tiny next to the spread isn't interesting, and you can't tell that
    from the centroid alone.

    Passing label=None sets label_index to -1, which the checks below read as
    "no filtering, take everything" — not as "index the last label".

    Careful: `label` gets reassigned inside the loop below, so it no longer holds
    the caller's argument after this point. label_index is captured first, which
    is why that doesn't break anything.
    """
    label_index = dataset.label_index_map[label] if label is not None else -1

    assert polarity in ['pos', 'neg']
    polarity_index = 1 if polarity == 'pos' else 0

    tensor_centroids = []
    tensor_labels = []
    for entry in dataset.data:
        tensor = entry[0]
        label = entry[1]
        tensor_centroids.append(compute_tensor_centroid(tensor))
        tensor_labels.append(label)

    if len(tensor_centroids) == 0:
        return [], []

    num_vitals = len(tensor_centroids[0])
    # Per-vital counters rather than one divisor, since each patient may be NaN
    # for a different subset of vitals — a shared denominator would understate
    # any vital that's usually present.
    dataset_centroid_sums = [0 for _ in range(num_vitals)]
    dataset_centroid_counts = [0 for _ in range(num_vitals)]
    for i in range(len(tensor_centroids)):
        if tensor_labels[i][label_index] == polarity_index or label_index == -1:
            for j in range(num_vitals):
                if not math.isnan(tensor_centroids[i][j]):
                    dataset_centroid_sums[j] += tensor_centroids[i][j]
                    dataset_centroid_counts[j] += 1

    # Same membership test as above, so the violin plot shows exactly the
    # sub-population the centroid was computed from. Note these still include
    # NaNs — the plotting code drops them per-vital.
    filtered_points = [
        tensor_centroids[i]
        for i in range(len(tensor_centroids))
        if tensor_labels[i][label_index] == polarity_index or label_index == -1
    ]
    return [dataset_centroid_sums[i] / dataset_centroid_counts[i] for i in range(num_vitals)], filtered_points