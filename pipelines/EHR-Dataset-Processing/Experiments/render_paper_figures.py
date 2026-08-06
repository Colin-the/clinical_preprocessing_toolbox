#!/usr/bin/env python3
"""
Paper-ready figure renderer for the EHR-Dataset-Processing pipeline (mimic-iii, mean aggregation).

Regenerates a fixed set of figures as scalable PDFs styled for inclusion in a paper:
white background, black text, no chart titles, slightly larger axis labels, and filenames
that describe each chart.

Reuses the plotting functions in Managers.visualization_manager_v2 (called exactly as the
notebook / gallery renderer does) and post-processes the returned matplotlib Figures for the
paper style. The McNemar plot is built fresh here because it needs structural changes
(two labeled thresholds, tiered bar colours, no legend).

Reads only the existing caches under Data/mimic-iii/ — no GPU, DB, or Marimo server needed.

Usage:
    MPLBACKEND=Agg python Experiments/render_paper_figures.py
"""

import os
import pickle
import sys
from pathlib import Path
from types import ModuleType

# ── Paths ─────────────────────────────────────────────────────────────────────
EHR_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = EHR_ROOT / "Data" / "mimic-iii"
OUT_DIR = EHR_ROOT / "paper_figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Matplotlib must be Agg before any other import ───────────────────────────
os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ── Stubs for GPU/torch deps so RecordEHR can be unpickled ───────────────────
def _make_stub(name: str) -> ModuleType:
    m = ModuleType(name)
    m.__spec__ = None

    class _Anything:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return self
        def __getattr__(self, n): return _Anything()
        def __iter__(self): return iter([])
        def __len__(self): return 0

    m._Anything = _Anything
    sys.modules[name] = m

    class _StubMod(ModuleType):
        def __getattr__(self, n):
            return _Anything()
    m.__class__ = _StubMod
    return m


for _stub in ("torch", "torch.nn", "torch.optim", "torch.utils", "torch.utils.data",
              "cupy", "cudf", "cuml", "cuml.ensemble", "cuml.model_selection",
              "cuml.metrics", "cugraph"):
    if _stub not in sys.modules:
        _make_stub(_stub)

# ── Add EHR project to sys.path and import viz functions ─────────────────────
if str(EHR_ROOT) not in sys.path:
    sys.path.insert(0, str(EHR_ROOT))

from Managers.visualization_manager_v2 import (  # noqa: E402
    centroid_plot, heatmap, centroid_shift_plot, filter_impact_plot,
)

# ── Constants mirrored from notebook.py ───────────────────────────────────────
WHITE = "#ffffff"
AGG = "mean"

VITALS = {
    "heart rate":               [(1, 600), "bpm"],
    "systolic blood pressure":  [(1, 400), "mmHg"],
    "diastolic blood pressure": [(1, 300), "mmHg"],
    "mean blood pressure":      [(1, 300), "mmHg"],
    "respiration rate":         [(1, 70),  "breaths/min"],
    "temperature":              [(21, 50), "C"],
    "oxygen saturation":        [(1, 100),  "%"],
}
VITAL_NAMES = list(VITALS.keys())
VITAL_UNITS = [v[-1] for v in VITALS.values()]

LABELS = ["icu", "mortality"]
FILTER_NAMES = [
    "heart rate", "systolic blood pressure", "diastolic blood pressure",
    "mean blood pressure", "respiration rate", "temperature", "oxygen saturation",
    "fill missing data", "long missing segment", "long gap", "high invalid data",
    "all vitals",
]
LENGTH_METHODS = ["mean", "median", "std", "max", "min"]


# ── Helpers ───────────────────────────────────────────────────────────────────
def load_pkl(path: Path):
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def finalize(fig, stem: str, *, label_size: int = 16, tick_size: int = 12,
             strip_titles: bool = True, text_color: str = "black", title_size: int = None,
             legend_size: int = None, annot_size: int = None,
             xtick_size: int = None, ytick_size: int = None):
    """Restyle a screen figure for print and save it as PDF.

    Post-processing the returned Figure rather than adding a "paper mode" to
    every plotting function — that keeps the paper style in one place and means
    the notebook's plots can't drift away from the published ones.

    Why the changes are what they are: titles come off because the caption
    carries that in a paper; text scales up because these get printed at a
    fraction of screen size; PDF because reviewers zoom.

    `text_color` is separate from the rest because in-axes annotations sometimes
    need to stay white — heatmap cell labels sit on dark Aurora cells even after
    the figure background goes white. Axis furniture is always black.
    """
    if fig is None:
        print(f"    [skip] {stem}: figure is None")
        return

    fig.set_facecolor(WHITE)

    for ax in fig.axes:
        ax.set_facecolor(WHITE)

        if strip_titles:
            ax.set_title("")
        elif title_size is not None:
            ax.title.set_size(title_size)

        ax.xaxis.label.set_color("black")
        ax.yaxis.label.set_color("black")
        ax.xaxis.label.set_size(label_size)
        ax.yaxis.label.set_size(label_size)

        # Per-axis overrides exist because some figures need one axis larger than
        # the other — the heatmap's 24 hourly y-ticks overlap if grown to match
        # its seven x-ticks.
        ax.tick_params(colors="black", labelsize=tick_size)
        for lbl in ax.get_xticklabels():
            lbl.set_color("black")
            if xtick_size is not None:
                lbl.set_size(xtick_size)
        for lbl in ax.get_yticklabels():
            lbl.set_color("black")
            if ytick_size is not None:
                lbl.set_size(ytick_size)

        # Only recolour spines that are already shown — the plotting functions
        # deliberately hide top/right, and forcing a colour would resurrect them.
        for spine in ax.spines.values():
            if spine.get_visible():
                spine.set_color("black")

        for txt in ax.texts:
            txt.set_color(text_color)
            if annot_size is not None:
                txt.set_size(annot_size)

        # Legends come in two flavours (per-axis and figure-level) and matplotlib
        # keeps them in different places, so both get handled — here and below.
        if legend_size is not None and ax.get_legend() is not None:
            lg = ax.get_legend()
            for t in lg.get_texts():
                t.set_size(legend_size)
            if lg.get_title() is not None:
                lg.get_title().set_size(legend_size)

    if legend_size is not None:
        for lg in fig.legends:
            for t in lg.get_texts():
                t.set_size(legend_size)
            if lg.get_title() is not None:
                lg.get_title().set_size(legend_size)

    out = OUT_DIR / f"{stem}.pdf"
    fig.savefig(str(out), bbox_inches="tight", facecolor=WHITE)
    plt.close(fig)
    print(f"    saved {out.name}")


# ─────────────────────────────────────────────────────────────────────────────
# Centroid cache loading (mean aggregation only)
# ─────────────────────────────────────────────────────────────────────────────
def load_centroids():
    """Return centroids[label][filter][sign] and points[label][filter][sign] for AGG."""
    centroids, points = {}, {}
    cent_dir = DATA_ROOT / AGG / "centroids"
    for label in LABELS:
        centroids[label], points[label] = {}, {}
        for filter_name in ["raw"] + FILTER_NAMES:
            centroids[label][filter_name], points[label][filter_name] = {}, {}
            for sign in ["pos", "neg"]:
                data = load_pkl(cent_dir / f"{label}_{filter_name}_{sign}.pkl")
                if data is not None:
                    c, p = data
                    centroids[label][filter_name][sign] = c
                    points[label][filter_name][sign] = p
    return centroids, points


def centroid_pairs(centroids, filter_name):
    return [
        (centroids["icu"]["raw"]["pos"],       centroids["icu"][filter_name]["pos"]),
        (centroids["icu"]["raw"]["neg"],       centroids["icu"][filter_name]["neg"]),
        (centroids["mortality"]["raw"]["pos"], centroids["mortality"][filter_name]["pos"]),
        (centroids["mortality"]["raw"]["neg"], centroids["mortality"][filter_name]["neg"]),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Figure 1: Centroid density of the raw dataset (95th percentile, mean agg)
# ─────────────────────────────────────────────────────────────────────────────
def fig_centroid_density_raw(centroids, points, *, use_percentile=True,
                             stem="centroid_density_raw_mimic_iii"):
    print(f"  {stem} ...", flush=True)
    try:
        raw_c = [
            centroids["icu"]["raw"]["pos"], centroids["icu"]["raw"]["neg"],
            centroids["mortality"]["raw"]["pos"], centroids["mortality"]["raw"]["neg"],
        ]
        raw_p = [
            points["icu"]["raw"]["pos"], points["icu"]["raw"]["neg"],
            points["mortality"]["raw"]["pos"], points["mortality"]["raw"]["neg"],
        ]
    except KeyError as e:
        print(f"    [SKIP] missing raw centroid data: {e}")
        return
    cats = ["Raw ICU Pos", "Raw ICU Neg", "Raw Mort Pos", "Raw Mort Neg"]
    fig = centroid_plot(raw_c, raw_p, VITAL_NAMES, VITAL_UNITS, cats,
                        use_percentile=use_percentile, background="white")

    # Move the legend off the top of the figure and into the empty (2,4) grid cell
    # (centroid_plot leaves the 8th panel blank for 7 vitals), and size its labels to
    # match the rest of the graph.
    handles, labels = fig.axes[0].get_legend_handles_labels()
    for lg in list(fig.legends):   # drop centroid_plot's top figure-level legend
        lg.remove()
    legend_ax = fig.axes[-1]       # the blank (2,4) panel, added last by centroid_plot
    legend_ax.axis("off")
    legend_ax.legend(handles, labels, loc="center", facecolor=WHITE, edgecolor="black",
                     labelcolor="black", fontsize=26, framealpha=1.0,
                     title="Subpopulation", title_fontsize=30)

    # Keep the per-vital panel labels (subplot titles); enlarge the vital names, the
    # y-axis numbers, and the axis labels significantly for readability at small sizes.
    finalize(fig, stem, strip_titles=False, title_size=36, tick_size=27, label_size=28)


# ─────────────────────────────────────────────────────────────────────────────
# Figure 2: Heatmap of mean per-hour observation counts per vital (raw)
# ─────────────────────────────────────────────────────────────────────────────
def fig_observation_count_heatmap():
    print("  observation_count_heatmap_raw_mimic_iii ...", flush=True)
    records = load_pkl(DATA_ROOT / "processed_record_ehr.pkl")
    if records is None:
        print("    [SKIP] processed_record_ehr.pkl not found")
        return

    length_dfs = []
    for rec in records:
        try:
            ldf = rec.timeseries.map(
                lambda x: x.size if hasattr(x, "size") else (len(x) if isinstance(x, list) else 0)
            )
            length_dfs.append(ldf)
        except Exception:
            pass
    if not length_dfs:
        print("    [SKIP] no length DataFrames built")
        return

    combined = pd.concat(length_dfs)
    mean_lengths = combined.groupby(level=0).agg("mean")

    fig = heatmap(mean_lengths, y_title="Hour", background_colour=WHITE, value_format=".3f")
    # Cell value annotations white (readable on the dark aurora cells); axes/ticks stay black.
    # The 24 hourly y-ticks cap how large the y-ticks can grow before overlapping
    # vertically, so they stay modest while the "Hour" label and vital-name x-ticks grow.
    finalize(fig, "observation_count_heatmap_raw_mimic_iii", text_color="white",
             label_size=26, xtick_size=11.33, ytick_size=12, annot_size=10)


# ─────────────────────────────────────────────────────────────────────────────
# Figures 3 & 6: Centroid deviation from baseline for a given filter (mean agg)
# ─────────────────────────────────────────────────────────────────────────────
def fig_centroid_deviation(centroids, filter_name, stem):
    print(f"  {stem} ...", flush=True)
    try:
        cp = centroid_pairs(centroids, filter_name)
    except KeyError as e:
        print(f"    [SKIP] missing centroid data for '{filter_name}': {e}")
        return
    cats = ["icu pos", "icu neg", "mortality pos", "mortality neg"]
    fig = centroid_shift_plot(cp, cats, filter_name, VITAL_NAMES, background=WHITE)
    finalize(fig, stem, label_size=28, tick_size=24, legend_size=22)


# ─────────────────────────────────────────────────────────────────────────────
# Figures 4,5,8,9: Filter impact (Testing accuracy / F1) per label (mean agg)
# ─────────────────────────────────────────────────────────────────────────────
def fig_filter_impact(label):
    impact = load_pkl(DATA_ROOT / AGG / f"{label}_filter_impact.pkl")
    if impact is None:
        print(f"  [SKIP] {label}_filter_impact.pkl not found")
        return
    test_acc, test_f1 = impact[1], impact[3]

    print(f"  filter_impact_{label}_testing_accuracy_mean ...", flush=True)
    fig = filter_impact_plot(test_acc, list(FILTER_NAMES), label.upper(),
                             "Testing Accuracy", AGG, background=WHITE)
    finalize(fig, f"filter_impact_{label}_testing_accuracy_mean",
             label_size=22, tick_size=18)

    print(f"  filter_impact_{label}_testing_f1_mean ...", flush=True)
    fig = filter_impact_plot(test_f1, list(FILTER_NAMES), label.upper(),
                             "Testing F1", AGG, background=WHITE)
    finalize(fig, f"filter_impact_{label}_testing_f1_mean",
             label_size=22, tick_size=18)


# ─────────────────────────────────────────────────────────────────────────────
# Figure 7: McNemar significance, ICU (mean agg) — paper variant
# ─────────────────────────────────────────────────────────────────────────────
def paper_mcnemar_plot(p_values, filter_names, label_size=26, tick_size=18,
                       figsize=(14, 7)):
    """White bg, black text, no title, two labeled thresholds, tiered bar colours, no legend."""
    p_values = [max(p, 1e-20) for p in p_values]
    neg_log_p = -np.log10(p_values)
    indices = np.arange(len(p_values))
    filter_names = filter_names[:len(p_values)]

    t1, t2 = 0.05, 0.0001          # significance thresholds
    y1, y2 = -np.log10(t1), -np.log10(t2)

    gray, orange, strong = "#a0a0a0", "#f39c12", "#bd3140"
    colors = [strong if p < t2 else (orange if p < t1 else gray) for p in p_values]

    fig, ax = plt.subplots(figsize=figsize, facecolor=WHITE)
    ax.set_facecolor(WHITE)
    bars = ax.bar(indices, neg_log_p, color=colors, alpha=0.9, zorder=3)

    # Two dashed reference lines, labeled inline on the chart (right edge).
    for y, txt in ((y1, r"$p=0.05$"), (y2, r"$p=0.0001$")):
        ax.axhline(y=y, color=strong, linestyle="--", linewidth=1.5, zorder=4)
        ax.text(0.995, y, txt, transform=ax.get_yaxis_transform(),
                ha="right", va="bottom", color="black", fontsize=tick_size)

    # p-value annotation above each bar.
    for bar, p in zip(bars, p_values):
        h = bar.get_height()
        disp = f"{p:.3f}" if p > 0.001 else f"{p:.1e}"
        ax.text(bar.get_x() + bar.get_width() / 2., h + 0.1, disp,
                ha="center", va="bottom", color="black", fontsize=14)

    ax.set_xticks(indices)
    ax.set_xticklabels(filter_names, rotation=45, ha="right", color="black", fontsize=tick_size)
    ax.tick_params(colors="black", labelsize=tick_size)
    ax.set_ylabel(r"$-\log_{10}(p\text{-value})$", color="black", fontsize=label_size)
    ax.set_xlabel("Filter Name", color="black", fontsize=label_size)

    ax.grid(axis="y", color="gray", linestyle="--", linewidth=0.5, alpha=0.2, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("black")
    ax.spines["left"].set_color("black")

    plt.tight_layout()
    return fig


def fig_mcnemar_icu():
    print("  mcnemar_icu_mean ...", flush=True)
    impact = load_pkl(DATA_ROOT / AGG / "icu_filter_impact.pkl")
    if impact is None:
        print("    [SKIP] icu_filter_impact.pkl not found")
        return
    p_values = [x[1] for x in impact[-1]][1:]  # drop raw baseline
    fig = paper_mcnemar_plot(p_values, list(FILTER_NAMES))
    # finalize would re-strip; this figure is already paper-styled, just save.
    fig.savefig(str(OUT_DIR / "mcnemar_icu_mean.pdf"), bbox_inches="tight", facecolor=WHITE)
    plt.close(fig)
    print("    saved mcnemar_icu_mean.pdf")


# ─────────────────────────────────────────────────────────────────────────────
# ECDF grid: raw vs filtered per-vital centroid distributions (fill missing data, mean)
# ─────────────────────────────────────────────────────────────────────────────
# 4 vitals × {raw, filtered}; one panel each, four subpopulation curves per panel.
ECDF_FILTER = "fill missing data"
ECDF_VITALS = [  # (name, unit, index into the centroid vector)
    ("heart rate", "bpm", 0),
    ("mean blood pressure", "mmHg", 3),
    ("temperature", "C", 5),
    ("oxygen saturation", "%", 6),
]
ECDF_SUBPOPS = [("icu", "pos"), ("icu", "neg"), ("mortality", "pos"), ("mortality", "neg")]
ECDF_SUBPOP_LABELS = {("icu", "pos"): "ICU+", ("icu", "neg"): "ICU−",
                      ("mortality", "pos"): "Mort+", ("mortality", "neg"): "Mort−"}
ECDF_COLORS = {("icu", "pos"): "#1b9e77", ("icu", "neg"): "#7570b3",
               ("mortality", "pos"): "#d95f02", ("mortality", "neg"): "#e7298a"}


def _ecdf(values):
    v = np.sort(values[~np.isnan(values)])
    if v.size == 0:
        return v, v
    return v, np.arange(1, len(v) + 1) / len(v)


def _p95_clip(values, center):
    d = np.abs(values - center)
    lim = np.nanpercentile(d, 95)
    return values[d <= lim]


def fig_ecdf_grid(layout="4x2"):
    """Render the raw-vs-filtered ECDF grid in either a 4x2 or 2x4 panel arrangement.

    layout="4x2": one vital per row (raw col 0, filtered col 1).
    layout="2x4": two vitals per row, each as a raw/filtered pair of adjacent columns.
    """
    stem = f"ecdf_fill_missing_data_mean_{layout}"
    print(f"  {stem} ...", flush=True)
    cent_dir = DATA_ROOT / AGG / "centroids"

    def load(condition, label, pol):
        data = load_pkl(cent_dir / f"{label}_{condition}_{pol}.pkl")
        if data is None:
            return None, None
        c, pts = data
        return c, np.asarray(pts)

    if layout == "4x2":
        nrows, ncols, figsize = 4, 2, (12, 18)
        # vital i → raw at (i, 0), filtered at (i, 1)
        placement = [((i, 0), (i, 1)) for i in range(len(ECDF_VITALS))]
    elif layout == "2x4":
        nrows, ncols, figsize = 2, 4, (22, 9)
        # vital i → raw/filtered pair of adjacent columns, two vitals per row
        placement = [((i // 2, (i % 2) * 2), (i // 2, (i % 2) * 2 + 1))
                     for i in range(len(ECDF_VITALS))]
    else:
        raise ValueError(f"unknown layout {layout!r}")

    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, facecolor=WHITE)

    def draw_panel(ax, name, unit, vital_idx, condition, nice):
        ax.set_facecolor(WHITE)
        for (label, pol) in ECDF_SUBPOPS:
            c, pts = load(condition, label, pol)
            if c is None:
                continue
            x, y = _ecdf(_p95_clip(pts[:, vital_idx], c[vital_idx]))
            if x.size == 0:
                continue
            ax.plot(x, y, color=ECDF_COLORS[(label, pol)], linewidth=1.8,
                    label=ECDF_SUBPOP_LABELS[(label, pol)])
        ax.set_title(f"{name} — {nice}", color="black", fontsize=18)
        ax.set_xlabel(unit, color="black", fontsize=17)
        ax.set_ylabel("cumulative fraction", color="black", fontsize=17)
        ax.tick_params(colors="black", labelsize=14)
        for s in ax.spines.values():
            s.set_color("black")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(color="gray", linestyle="--", linewidth=0.4, alpha=0.4)
        ax.set_ylim(0, 1.02)

    first_ax = None
    for (name, unit, vital_idx), (raw_cell, filt_cell) in zip(ECDF_VITALS, placement):
        raw_ax = axes[raw_cell]
        draw_panel(raw_ax, name, unit, vital_idx, "raw", "raw")
        draw_panel(axes[filt_cell], name, unit, vital_idx, ECDF_FILTER, "filtered")
        if first_ax is None:
            first_ax = raw_ax

    # Legend incorporated into the graph: placed in the empty lower-right region of the
    # first panel (an ECDF leaves that corner clear).
    handles, labels = first_ax.get_legend_handles_labels()
    first_ax.legend(handles, labels, loc="lower right", facecolor=WHITE,
                    edgecolor="black", labelcolor="black", fontsize=15,
                    framealpha=1.0, title="Subpopulation", title_fontsize=16)

    fig.tight_layout()
    out = OUT_DIR / f"{stem}.pdf"
    fig.savefig(str(out), bbox_inches="tight", facecolor=WHITE)
    plt.close(fig)
    print(f"    saved {out.name}")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    print(f"Output dir: {OUT_DIR}")
    centroids, points = load_centroids()

    print("\n=== Centroid density (raw) ===")
    fig_centroid_density_raw(centroids, points)  # 95th-percentile clipped (default)
    fig_centroid_density_raw(centroids, points, use_percentile=False,
                             stem="centroid_density_raw_mimic_iii_full_range")

    print("\n=== Observation-count heatmap ===")
    fig_observation_count_heatmap()

    print("\n=== Centroid deviations ===")
    fig_centroid_deviation(centroids, "all vitals", "centroid_deviation_all_vitals_filter_mean")
    fig_centroid_deviation(centroids, "high invalid data",
                           "centroid_deviation_high_invalid_data_filter_mean")

    print("\n=== Filter impact ===")
    fig_filter_impact("mortality")
    fig_filter_impact("icu")

    print("\n=== McNemar (ICU) ===")
    fig_mcnemar_icu()

    print("\n=== ECDF grid (fill missing data) ===")
    fig_ecdf_grid(layout="4x2")
    fig_ecdf_grid(layout="2x4")

    print("\nDone.")


if __name__ == "__main__":
    main()
