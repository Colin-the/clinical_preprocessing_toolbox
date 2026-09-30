"""Is an arm's McNemar shift caused by the filter, or by its threshold pick?

Written to settle the `heart rate` / icu / mean result, which reads as a large,
highly significant degradation (n01=753 vs n10=1041, p=1.2e-11) even though the
filter alters 0.0047% of the feature matrix.

The CV design thresholds each arm's consensus scores at *that arm's own* mean of
20 Youden's-J picks (evaluation_manager.evaluate_dataset_label_cv:498). Two arms
with near-identical scores but thresholds a hair apart therefore disagree on
every record sitting in the gap — and at n=46k McNemar calls that disagreement
significant. This script separates the two explanations.

Needs numpy/scipy only:  module load scipy-stack/2026a
Section K additionally needs torch, for the feature matrices:
    .venv_centroid_recompute/bin/python rerun/verify_threshold_artifact.py --with-data

    python rerun/verify_threshold_artifact.py [--agg mean] [--label icu] [--arm "heart rate"]
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
N_SPLITS = 5


def slug(arm):
    return arm.replace(" ", "_").lower()


def auc(y, s):
    """Mann-Whitney AUC — sklearn is not in the scipy-stack module."""
    r = stats.rankdata(s)
    n1 = int((y == 1).sum())
    n0 = len(y) - n1
    return float("nan") if not n1 or not n0 else (r[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def mcnemar(baseline_correct, arm_correct):
    """n01 = arm fixed it, n10 = arm broke it. chi2 with continuity correction,
    matching Managers.evaluation_manager.calculate_mcnemar_paired."""
    n01 = int((~baseline_correct & arm_correct).sum())
    n10 = int((baseline_correct & ~arm_correct).sum())
    nd = n01 + n10
    p = 1.0 if nd == 0 else float(stats.chi2.sf((abs(n01 - n10) - 1) ** 2 / nd, 1))
    return n01, n10, p


def per_repeat_predictions(scores, thresholds, fold_assignment):
    """Rebuild the per-repeat OOF label vectors. Only the *consensus* predictions
    are stored in the npz, but the per-fold thresholds survive in the diagnostics
    JSON, so the per-repeat vectors are recoverable exactly."""
    out = np.full(scores.shape, -1, np.int8)
    for repeat in range(scores.shape[0]):
        for fold in range(N_SPLITS):
            key = f"r{repeat}f{fold}"
            if key not in thresholds:
                continue
            mask = fold_assignment[repeat] == fold
            out[repeat, mask] = (scores[repeat, mask] >= thresholds[key]).astype(np.int8)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agg", default="mean")
    ap.add_argument("--label", default="icu")
    ap.add_argument("--arm", default="heart rate")
    ap.add_argument("--dataset", default="mimic-iii")
    ap.add_argument("--with-data", action="store_true",
                    help="section K: needs torch, loads the two feature matrices")
    args = ap.parse_args()

    d = ROOT / "Data" / args.dataset / args.agg
    z = np.load(d / f"{args.label}_oof_scores_cv.npz", allow_pickle=True)
    diag = json.loads((d / f"{args.label}_filter_impact_cv_diagnostics.json").read_text())

    arm = args.arm
    y = z["raw_labels"]
    fold_assignment = z["fold_assignment"]
    raw_folds = z["raw__oof_scores"].astype(np.float64)
    arm_folds = z[f"{slug(arm)}__oof_scores"].astype(np.float64)
    if not np.array_equal(z["raw__admission_ids"], z[f"{slug(arm)}__admission_ids"]):
        raise SystemExit(f"{arm!r} is not on the raw cohort — this script only "
                         "separates threshold effects, not cohort effects")

    raw_s, arm_s = raw_folds.mean(0), arm_folds.mean(0)
    t_raw = diag["raw"]["mean_threshold"]
    t_arm = diag[arm]["mean_threshold"]
    thr_raw, thr_arm = diag["raw"]["thresholds"], diag[arm]["thresholds"]

    print(f"=== {arm} / {args.label} / {args.agg} ===\n")

    print("A. as shipped (each arm at its own mean threshold)")
    rc = z["raw__consensus_predictions"] == y
    ac = z[f"{slug(arm)}__consensus_predictions"] == y
    n01, n10, p = mcnemar(rc, ac)
    print(f"   raw {rc.mean():.4f}  {arm} {ac.mean():.4f}  delta {ac.mean()-rc.mean():+.4f}")
    print(f"   n01={n01} n10={n10} p={p:.3e}   thresholds {t_raw:.4f} vs {t_arm:.4f} ({t_arm-t_raw:+.4f})")

    print("\nB. threshold-free — is there any discriminative difference at all?")
    a_raw, a_arm = auc(y, raw_s), auc(y, arm_s)
    rng = np.random.default_rng(0)
    boot = np.array([auc(y[b], arm_s[b]) - auc(y[b], raw_s[b])
                     for b in (rng.integers(0, len(y), len(y)) for _ in range(2000))])
    print(f"   AUC raw {a_raw:.5f}  {arm} {a_arm:.5f}  delta {a_arm-a_raw:+.5f}"
          f"  95% CI [{np.percentile(boot,2.5):+.5f}, {np.percentile(boot,97.5):+.5f}]")
    print(f"   score corr {np.corrcoef(raw_s, arm_s)[0,1]:.5f}   "
          f"KS {stats.ks_2samp(raw_s, arm_s).statistic:.5f}")

    print("\nC. both arms at a COMMON threshold — does the imbalance survive?")
    for name, t in (("raw thr", t_raw), ("arm thr", t_arm), ("pooled", (t_raw + t_arm) / 2)):
        n01, n10, p = mcnemar((raw_s >= t).astype(int) == y, (arm_s >= t).astype(int) == y)
        acc_r = float((((raw_s >= t).astype(int)) == y).mean())
        acc_a = float((((arm_s >= t).astype(int)) == y).mean())
        print(f"   {name:8s} t={t:.4f}  raw {acc_r:.4f}  {arm} {acc_a:.4f}"
              f"  d={acc_a-acc_r:+.4f}  n01={n01:5d} n10={n10:5d}  p={p:.3e}")

    print("\nD. the same threshold nudge applied to raw ALONE (no filtering whatsoever)")
    base = (raw_s >= t_raw).astype(int) == y
    for shift in (t_arm - t_raw, -(t_arm - t_raw)):
        moved = (raw_s >= t_raw + shift).astype(int) == y
        n01, n10, p = mcnemar(base, moved)
        print(f"   raw @ thr{shift:+.4f}: acc {moved.mean():.4f} (d={moved.mean()-base.mean():+.4f})"
              f"  n01={n01:5d} n10={n10:5d}  p={p:.3e}")

    print("\nE. per-repeat — is the direction consistent across the 4 partitions?")
    pr = per_repeat_predictions(raw_folds, thr_raw, fold_assignment)
    pa_own = per_repeat_predictions(arm_folds, thr_arm, fold_assignment)
    pa_raw = per_repeat_predictions(arm_folds, thr_raw, fold_assignment)
    for tag, pa in (("own thresholds", pa_own), ("raw thresholds", pa_raw)):
        line = []
        for r in range(pr.shape[0]):
            n01, n10, p = mcnemar(pr[r] == y, pa[r] == y)
            line.append(f"r{r} d={(pa[r]==y).mean()-(pr[r]==y).mean():+.4f} p={p:.1e}")
        print(f"   {tag:15s} " + "  ".join(line))

    print("\nF. noise floor — raw vs raw, split by repeat halves (identical data)")
    for a, b in ((( 0, 1), (2, 3)), ((0, 2), (1, 3)), ((0, 3), (1, 2))):
        def half(reps):
            t = np.mean([thr_raw[f"r{r}f{f}"] for r in reps for f in range(N_SPLITS)
                         if f"r{r}f{f}" in thr_raw])
            return (raw_folds[list(reps)].mean(0) >= t).astype(int) == y, t
        ca, ta = half(a)
        cb, tb = half(b)
        n01, n10, p = mcnemar(ca, cb)
        print(f"   raw{list(a)} vs raw{list(b)}: d={cb.mean()-ca.mean():+.4f}"
              f"  thr {ta:.4f}/{tb:.4f}  n01={n01:5d} n10={n10:5d}  p={p:.2e}")

    print("\nG. is the threshold gap itself distinguishable from noise? (20 paired folds)")
    keys = sorted(thr_raw)
    gap = np.array([thr_arm[k] - thr_raw[k] for k in keys])
    t, p = stats.ttest_rel([thr_arm[k] for k in keys], [thr_raw[k] for k in keys])
    n_lower = int((gap < 0).sum())
    print(f"   mean gap {gap.mean():+.5f}  sd {gap.std(ddof=1):.5f}  SE {gap.std(ddof=1)/np.sqrt(len(gap)):.5f}")
    print(f"   paired t p={p:.4f}   sign test {n_lower}/{len(gap)} "
          f"p={stats.binomtest(n_lower, len(gap)).pvalue:.4f}")

    print("\nH. across every full-cohort arm — does the threshold pick predict the McNemar direction?")
    gaps, dirs, names = [], [], []
    for name in diag:
        if name == "raw" or diag[name]["n_records"] != diag["raw"]["n_records"]:
            continue
        ta = diag[name]["thresholds"]
        if len(ta) < len(thr_raw):
            continue
        m = diag[name]["mcnemar"]
        if m["n01"] + m["n10"] == 0:
            continue
        names.append(name)
        gaps.append(np.mean([ta[k] - thr_raw[k] for k in keys]))
        dirs.append((m["n01"] - m["n10"]) / (m["n01"] + m["n10"]))
    r, p = stats.pearsonr(gaps, dirs)
    for n, g, e in sorted(zip(names, gaps, dirs), key=lambda t: t[1]):
        print(f"   {n:26s} thr gap {g:+.5f}   (n01-n10)/nd {e:+.4f}")
    print(f"   Pearson r={r:.4f} p={p:.5f} over {len(names)} arms")

    if args.with_data:
        import torch  # noqa: PLC0415 — optional, keeps the numpy-only path importable
        print("\nK. does the discordance land on records the filter actually touched?")

        def matrix(path):
            return torch.stack([rec[0].float().flatten()
                                for rec in torch.load(d / path)]).numpy()

        X = matrix("raw_dataset_ehr.pkl")
        Y = matrix(f"{slug(arm)}_filtered_dataset_ehr.pkl")
        changed = ~np.isclose(X, Y, equal_nan=True)
        touched = changed.any(1)
        disc = rc != ac
        print(f"   cells changed by the filter : {changed.sum():,} / {changed.size:,}"
              f" = {changed.mean()*100:.4f}%")
        print(f"   records touched             : {touched.sum():,}")
        print(f"   records discordant          : {disc.sum():,}")
        print(f"   discordant AND untouched    : {(disc & ~touched).sum():,}"
              f"  ({(disc & ~touched).sum()/max(disc.sum(),1)*100:.1f}%)")
        n01, n10, p = mcnemar(rc[~touched], ac[~touched])
        print(f"   UNTOUCHED only: n01={n01} n10={n10} p={p:.3e}  <-- the filter cannot have caused these")
        n01, n10, p = mcnemar(rc[touched], ac[touched])
        print(f"   TOUCHED   only: n01={n01} n10={n10} p={p:.3f}")


if __name__ == "__main__":
    main()
