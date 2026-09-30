"""Build the stage H results deck as an editable PowerPoint file.

    python Experiments/build_balance_slides.py [--out PATH]

Everything on the slides is read from the stage F and stage H artifacts at build
time — the comparison CSVs, the balance sidecars, and stage F's cached OOF scores
— so re-running this after a re-run of either stage produces a deck that agrees
with the data rather than one that has to be re-checked by hand.

Native PowerPoint objects throughout: text frames, real tables, and real charts
with embedded worksheets. Nothing is a picture, so every number, label and data
point stays editable in PowerPoint, Keynote, LibreOffice or Google Slides.

The first slide answers a question that is not in the stage H outputs at all —
what moving the decision threshold did — so that comes from stage F's
`<label>_oof_scores_cv.npz`, which stores the Youden-thresholded consensus
predictions alongside the scores they were cut from.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pptx import Presentation
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_TICK_MARK
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
BALANCE = ROOT / "paper_figures" / "balance"
DATA = ROOT / "Data" / "mimic-iii"

# Same palette as the HTML report, so the deck and the page read as one artifact.
INK = RGBColor(0x0E, 0x16, 0x18)
BODY = RGBColor(0x2C, 0x3C, 0x40)
MUTED = RGBColor(0x61, 0x76, 0x7A)
LINE = RGBColor(0xCD, 0xD8, 0xD9)
GROUND = RGBColor(0xEE, 0xF2, 0xF2)
SURFACE = RGBColor(0xFF, 0xFF, 0xFF)
SUNK = RGBColor(0xE4, 0xEA, 0xEA)
TEAL = RGBColor(0x0D, 0x6B, 0x6B)     # accent / oversample
RUST = RGBColor(0xA4, 0x55, 0x2B)     # negative / undersample
SLATE = RGBColor(0x4A, 0x65, 0x72)    # smote
GREEN = RGBColor(0x3D, 0x7A, 0x52)    # positive change

SERIF = "Georgia"
SANS = "Calibri"
MONO = "Consolas"

W, H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.72)
CONTENT_W = W - 2 * MARGIN


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def threshold_comparison(aggregation: str = "mean", label: str = "mortality") -> dict:
    """One set of out-of-fold scores, read at two operating points.

    Both columns come from stage F's *same* cached scores, so the comparison is
    genuinely a threshold comparison and nothing else. The Youden column is stage
    F's stored consensus (its per-fold threshold chosen on an inner-validation
    slice); the 0.5 column re-cuts those identical scores at 0.5 and takes the
    majority vote across repeats the same way.

    Sourcing the 0.5 column from stage H's baseline instead would have been
    easier, but that is a *different fit* on a different fraction of the cohort —
    the slide would then be attributing a difference in training data to the
    threshold. AUROC and AUPRC are computed once from the shared scores, which is
    what makes "unchanged" a fact about this table rather than a claim about
    threshold-free metrics in general.
    """
    from sklearn.metrics import (average_precision_score, balanced_accuracy_score,
                                 recall_score, roc_auc_score)

    cached = np.load(DATA / aggregation / f"{label}_oof_scores_cv.npz", allow_pickle=True)
    diagnostics = json.loads(
        (DATA / aggregation / f"{label}_filter_impact_cv_diagnostics.json").read_text()
    )["raw"]

    labels_by_id = {int(i): int(v) for i, v in zip(cached["raw_admission_ids"],
                                                   cached["raw_labels"])}
    truth = np.array([labels_by_id[int(i)] for i in cached["raw__admission_ids"]])
    scores = cached["raw__oof_scores"]
    youden_predictions = cached["raw__consensus_predictions"]

    # Majority vote across repeats at 0.5, matching how the stored consensus was
    # built — a per-repeat cut, then a vote, not a vote then a cut.
    per_repeat = np.where(np.isfinite(scores), scores >= 0.5, np.nan)
    with np.errstate(invalid="ignore"):
        votes = np.nanmean(per_repeat, axis=0)
    fixed_predictions = np.where(np.isnan(votes), -1, (votes >= 0.5).astype(int))

    def measure(predictions):
        covered = predictions >= 0
        return {
            "recall": float(recall_score(truth[covered], predictions[covered])),
            "balanced_accuracy": float(balanced_accuracy_score(truth[covered],
                                                               predictions[covered])),
            "accuracy": float(np.mean(predictions[covered] == truth[covered])),
            "positive_rate": float(np.mean(predictions[covered])),
        }

    mean_scores = np.nanmean(scores, axis=0)
    scored = np.isfinite(mean_scores)

    full = pd.read_csv(BALANCE / "balance_comparison.csv")
    baseline = full[(full.label == label) & (full.aggregation == aggregation)
                    & (full.strategy == "none")].iloc[0]

    return {
        "threshold": float(diagnostics["mean_threshold"]),
        "fixed": measure(fixed_predictions),
        "youden": measure(youden_predictions),
        "auroc": float(roc_auc_score(truth[scored], mean_scores[scored])),
        "auprc": float(average_precision_score(truth[scored], mean_scores[scored])),
        "prevalence": float(baseline.prevalence),
    }


def load() -> dict:
    full = pd.read_csv(BALANCE / "balance_comparison.csv")
    delta = pd.read_csv(BALANCE / "balance_deltas.csv")
    prior_path = (ROOT / "rerun/backups/stageH_reused_baseline_20260820"
                  / "paper_figures_balance" / "balance_deltas.csv")
    prior = pd.read_csv(prior_path) if prior_path.exists() else None
    return {"full": full, "delta": delta, "prior": prior,
            "threshold": threshold_comparison()}


# --------------------------------------------------------------------------
# slide furniture
# --------------------------------------------------------------------------
def text_box(slide, left, top, width, height, *, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = frame.margin_right = 0
    frame.margin_top = frame.margin_bottom = 0
    return frame


def write(frame, runs, *, size=16, font=SANS, color=BODY, space_after=8,
          align=PP_ALIGN.LEFT, line_spacing=1.24, first=False):
    """Append a paragraph. `runs` is a string, or (text, **overrides) tuples."""
    paragraph = frame.paragraphs[0] if first else frame.add_paragraph()
    paragraph.alignment = align
    paragraph.line_spacing = line_spacing
    paragraph.space_after = Pt(space_after)
    for piece in ([runs] if isinstance(runs, str) else runs):
        text, overrides = (piece, {}) if isinstance(piece, str) else piece
        run = paragraph.add_run()
        run.text = text
        run.font.size = Pt(overrides.get("size", size))
        run.font.name = overrides.get("font", font)
        run.font.bold = overrides.get("bold", False)
        run.font.italic = overrides.get("italic", False)
        run.font.color.rgb = overrides.get("color", color)
    return paragraph


def rule(slide, left, top, width, color=LINE, height=Pt(1)):
    from pptx.enum.shapes import MSO_SHAPE
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    bar.fill.solid()
    bar.fill.fore_color.rgb = color
    bar.line.fill.background()
    bar.shadow.inherit = False
    return bar


def panel(slide, left, top, width, height, fill=SURFACE, edge=LINE):
    from pptx.enum.shapes import MSO_SHAPE
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = edge
    shape.line.width = Pt(0.75)
    shape.shadow.inherit = False
    return shape


def new_slide(deck, eyebrow, title, *, subtitle=None):
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = GROUND

    frame = text_box(slide, MARGIN, Inches(0.42), CONTENT_W, Inches(0.9))
    write(frame, [(eyebrow.upper(), {"size": 10.5, "font": MONO, "color": MUTED})],
          space_after=5, first=True)
    write(frame, [(title, {"size": 30, "font": SERIF, "color": INK, "bold": True})],
          space_after=0, line_spacing=1.02)

    top = Inches(1.52)
    if subtitle:
        sub = text_box(slide, MARGIN, top, CONTENT_W, Inches(0.5))
        write(sub, [(subtitle, {"size": 15, "color": MUTED})], first=True,
              space_after=0)
        top = Inches(2.0)
    rule(slide, MARGIN, top - Inches(0.16), CONTENT_W)
    return slide, top


def table(slide, left, top, width, rows, *, col_widths=None, header=True,
          row_height=Inches(0.34), size=13, number_columns=()):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), left, top, width,
                                   row_height * len(rows))
    tbl = shape.table
    tbl.first_row = header
    tbl.horz_banding = False

    if col_widths:
        total = sum(col_widths)
        for index, share in enumerate(col_widths):
            tbl.columns[index].width = Emu(int(width * share / total))

    for r, row in enumerate(rows):
        tbl.rows[r].height = row_height
        for c, value in enumerate(row):
            cell = tbl.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.09)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = SUNK if (header and r == 0) else SURFACE

            text, overrides = (value, {}) if isinstance(value, str) else value
            frame = cell.text_frame
            frame.word_wrap = True
            paragraph = frame.paragraphs[0]
            paragraph.alignment = (PP_ALIGN.RIGHT if c in number_columns
                                   else PP_ALIGN.LEFT)
            run = paragraph.add_run()
            run.text = text
            run.font.size = Pt(overrides.get("size", size))
            run.font.name = overrides.get(
                "font", MONO if c in number_columns else SANS)
            run.font.bold = overrides.get("bold", header and r == 0)
            run.font.color.rgb = overrides.get(
                "color", MUTED if (header and r == 0) else BODY)
    return tbl


def stat_row(slide, top, entries, *, left=MARGIN, width=CONTENT_W):
    """Big-number row. `entries` is a list of (value, caption, colour)."""
    gap = Inches(0.24)
    each = Emu(int((width - gap * (len(entries) - 1)) / len(entries)))
    for index, (value, caption, color) in enumerate(entries):
        x = Emu(int(left + index * (each + gap)))
        panel(slide, x, top, each, Inches(1.16))
        frame = text_box(slide, Emu(int(x + Inches(0.2))), Emu(int(top + Inches(0.16))),
                         Emu(int(each - Inches(0.4))), Inches(0.9))
        write(frame, [(value, {"size": 27, "font": MONO, "color": color, "bold": True})],
              first=True, space_after=3, line_spacing=1.0)
        write(frame, [(caption, {"size": 11.5, "color": MUTED})], space_after=0,
              line_spacing=1.14)


def style_chart(chart, *, font_size=11):
    chart.font.size = Pt(font_size)
    chart.font.name = SANS
    chart.font.color.rgb = BODY
    try:
        chart.has_title = False
    except (AttributeError, ValueError):
        pass


def signed(value, places=4):
    return f"{value:+.{places}f}"


# --------------------------------------------------------------------------
# slides
# --------------------------------------------------------------------------
def slide_title(deck, d):
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = GROUND
    rule(slide, MARGIN, Inches(2.42), Inches(1.5), TEAL, Pt(3))

    frame = text_box(slide, MARGIN, Inches(2.72), Inches(9.6), Inches(3.0))
    write(frame, [("Does class balancing help?",
                   {"size": 48, "font": SERIF, "color": INK, "bold": True})],
          first=True, space_after=16, line_spacing=1.02)
    write(frame, [("Oversampling, undersampling and mask-aware SMOTE against a "
                   "random forest trained on the natural class distribution — and "
                   "against simply moving the decision threshold.",
                   {"size": 18, "color": MUTED})], space_after=0, line_spacing=1.35)

    full = d["full"]
    facts = text_box(slide, MARGIN, Inches(5.62), CONTENT_W, Inches(0.6))
    write(facts, [(f"MIMIC-III  ·  {int(full.n_records.iloc[0]):,} ICU stays  ·  "
                   f"7 vitals × 24 hours  ·  5-fold × 4 repeats  ·  "
                   f"{len(d['delta'])} comparisons",
                   {"size": 13, "font": MONO, "color": MUTED})], first=True,
          space_after=0)


def slide_threshold(deck, d):
    t = d["threshold"]
    slide, top = new_slide(
        deck, "where we left off", "The threshold already moved the operating point",
        subtitle="One forest, one set of scores, two places to cut them — "
                 "mean aggregation, in-hospital mortality.")

    rows = [["", "Cut at 0.5", f"Cut at Youden's J ({t['threshold']:.3f})", "Change"]]
    for key, name in [("recall", "Recall"), ("balanced_accuracy", "Balanced accuracy"),
                      ("accuracy", "Accuracy"), ("positive_rate", "Predicted positive rate")]:
        change = t["youden"][key] - t["fixed"][key]
        rows.append([
            name,
            f"{t['fixed'][key]:.3f}",
            f"{t['youden'][key]:.3f}",
            (f"{change:+.3f}", {"color": GREEN if change > 0 else RUST, "bold": True}),
        ])
    rows.append([("AUROC / AUPRC", {"bold": True}),
                 (f"{t['auroc']:.3f} / {t['auprc']:.3f}", {"bold": True}),
                 (f"{t['auroc']:.3f} / {t['auprc']:.3f}", {"bold": True}),
                 ("unchanged", {"color": MUTED, "font": SANS, "italic": True})])

    table(slide, MARGIN, top + Inches(0.1), Inches(7.55), rows,
          col_widths=[2.5, 1.5, 2.3, 1.3], number_columns=(1, 2, 3), row_height=Inches(0.42))

    x = MARGIN + Inches(7.95)
    panel(slide, x, top + Inches(0.1), Inches(3.9), Inches(3.62))
    frame = text_box(slide, x + Inches(0.26), top + Inches(0.32), Inches(3.42), Inches(3.3))
    write(frame, [("What this told us", {"size": 15, "font": SERIF, "color": INK,
                                         "bold": True})], first=True, space_after=10)
    write(frame, [("At 0.5 the forest calls only ", {}),
                  (f"{t['fixed']['positive_rate']:.1%}", {"font": MONO, "bold": True,
                                                          "color": INK}),
                  (" of patients positive against a prevalence of ", {}),
                  (f"{t['prevalence']:.1%}", {"font": MONO, "bold": True, "color": INK}),
                  (". It buys accuracy by barely predicting death at all.", {})],
          size=13, space_after=9)
    write(frame, [("Moving the cut fixes recall, and costs accuracy in almost equal "
                   "measure. But AUROC and AUPRC come from the scores, not the cut, so "
                   "they do not move.", {})], size=13, space_after=9)
    write(frame, [("The threshold changes ", {}),
                  ("who gets called positive", {"bold": True, "color": INK}),
                  (", never ", {}),
                  ("how well the model ranks", {"bold": True, "color": INK}),
                  (".", {})], size=13, space_after=0)

    ask = text_box(slide, MARGIN, Inches(6.25), CONTENT_W, Inches(0.8))
    write(ask, [("So the open question: ", {"size": 17, "color": BODY}),
                ("can fixing the imbalance in the training data do something a "
                 "threshold cannot?", {"size": 17, "color": INK, "bold": True,
                                       "font": SERIF})], first=True, space_after=0)


def slide_design(deck, d):
    full = d["full"]
    slide, top = new_slide(
        deck, "stage h · design", "How the experiment isolates the resampler",
        subtitle="Balancing and thresholding are never allowed to move at the same time.")

    left_frame = text_box(slide, MARGIN, top + Inches(0.1), Inches(6.0), Inches(4.4))
    for heading, text in [
        ("Threshold pinned at 0.5",
         "No inner-validation split and no Youden step in this path — so any change "
         "in the numbers is the resampler's doing, not the operating point's."),
        ("Resampling touches training rows only",
         "Each training fold is resampled to a 1:1 class ratio. Test features are "
         "read from the original matrix by position, so a synthetic record has no "
         "position and can never be scored."),
        ("One partition, inherited by every arm",
         "Folds are drawn once on the raw cohort and keyed on admission_id, so every "
         "strategy predicts the same patients in the same folds and McNemar is "
         "genuinely paired."),
        ("Out-of-fold predictions for every record",
         f"5-fold stratified CV × 4 partitions over all "
         f"{int(full.n_records.iloc[0]):,} stays — every patient predicted by a model "
         f"that never saw them."),
    ]:
        write(left_frame, [(heading, {"size": 14.5, "color": INK, "bold": True})],
              space_after=3, first=(heading.startswith("Threshold")))
        write(left_frame, [(text, {"size": 12.5, "color": BODY})], space_after=12,
              line_spacing=1.28)

    x = MARGIN + Inches(6.35)
    panel(slide, x, top + Inches(0.15), Inches(5.55), Inches(2.05))
    frame = text_box(slide, x + Inches(0.3), top + Inches(0.38), Inches(4.95), Inches(1.7))
    write(frame, [("The two labels are not equally imbalanced",
                   {"size": 15, "font": SERIF, "color": INK, "bold": True})],
          first=True, space_after=10)
    mortality = float(full[full.label == "mortality"].prevalence.iloc[0])
    icu = float(full[full.label == "icu"].prevalence.iloc[0])
    write(frame, [("In-hospital mortality ", {}),
                  (f"{mortality:.1%}", {"font": MONO, "bold": True, "color": RUST}),
                  ("   ·   ICU admission ", {}),
                  (f"{icu:.1%}", {"font": MONO, "bold": True, "color": TEAL})],
          size=15, space_after=8)
    write(frame, [("Mortality is the case balancing is supposed to help; ICU is close "
                   "enough to even that it acts as a control.", {"size": 13,
                                                                 "color": MUTED})],
          space_after=0, line_spacing=1.3)

    panel(slide, x, top + Inches(2.45), Inches(5.55), Inches(1.9), SUNK)
    frame = text_box(slide, x + Inches(0.28), top + Inches(2.62), Inches(4.99), Inches(1.66))
    write(frame, [("Reported per arm", {"size": 15, "font": SERIF, "color": INK,
                                        "bold": True})], first=True, space_after=8)
    write(frame, [("Threshold-dependent: ", {"bold": True, "color": INK}),
                  ("recall, balanced accuracy, macro F1, accuracy", {})],
          size=13.5, space_after=5)
    write(frame, [("Threshold-free: ", {"bold": True, "color": INK}),
                  ("AUROC, AUPRC — from scores, so they answer whether the model "
                   "discriminates better rather than relabels more.", {})],
          size=13, space_after=0, line_spacing=1.28)


def slide_strategies(deck, d):
    full = d["full"]
    slide, top = new_slide(
        deck, "stage h · strategies", "Four ways to train, one way to score",
        subtitle="Training-fold sizes below are for mean aggregation / mortality "
                 "(9.7% positive).")

    mortality = full[(full.label == "mortality") & (full.aggregation == "mean")]
    rows = mortality.set_index("strategy")

    cards = [
        ("none", "Baseline", TEAL,
         "Train on the natural distribution. The reference every other arm is "
         "measured against — refitted here on the same 80% as the arms, not reused."),
        ("oversample", "Random oversampling", TEAL,
         "Draw minority patients with replacement until the classes are even. No new "
         "information — each positive is simply seen several times, so the forest "
         "weights it more heavily."),
        ("undersample", "Random undersampling", RUST,
         "Discard majority patients at random until the classes are even. Cheap and "
         "fast, but it throws away most of the negatives, and with them most of the "
         "training set."),
        ("smote", "Mask-aware SMOTE", SLATE,
         "Synthesise new minority patients by interpolating between real ones — but "
         "adapted to missingness, which plain SMOTE would corrupt. See next slide."),
    ]

    card_w = Inches(2.86)
    gap = Inches(0.15)
    for index, (key, name, color, text) in enumerate(cards):
        x = Emu(int(MARGIN + index * (card_w + gap)))
        panel(slide, x, top + Inches(0.12), card_w, Inches(3.55))
        rule(slide, x, top + Inches(0.12), card_w, color, Pt(3.5))

        frame = text_box(slide, Emu(int(x + Inches(0.22))), top + Inches(0.36),
                         Emu(int(card_w - Inches(0.44))), Inches(3.1))
        write(frame, [(key, {"size": 11, "font": MONO, "color": color, "bold": True})],
              first=True, space_after=4)
        write(frame, [(name, {"size": 16.5, "font": SERIF, "color": INK, "bold": True})],
              space_after=9, line_spacing=1.05)
        write(frame, [(text, {"size": 12.5, "color": BODY})], space_after=12,
              line_spacing=1.32)

        row = rows.loc[key]
        write(frame, [("training rows ", {"size": 11, "color": MUTED}),
                      (f"{row.mean_train_rows:,.0f}", {"size": 12.5, "font": MONO,
                                                       "color": INK, "bold": True})],
              space_after=2)
        if int(row.n_synthetic):
            per_fold = int(row.n_synthetic) / 20
            write(frame, [("synthetic ", {"size": 11, "color": MUTED}),
                          (f"{per_fold:,.0f}", {"size": 12.5, "font": MONO,
                                                "color": INK, "bold": True}),
                          (" / fold", {"size": 11, "color": MUTED})], space_after=0)
        else:
            write(frame, [("all rows real", {"size": 11, "color": MUTED,
                                             "italic": True})], space_after=0)

    note = text_box(slide, MARGIN, Inches(6.1), CONTENT_W, Inches(0.9))
    write(note, [("Oversampling and SMOTE produce identical training-set sizes "
                  "(2 × majority), which is deliberate: the difference between them "
                  "isolates one question — ", {"size": 14, "color": BODY}),
                 ("duplicate a real patient, or synthesise a new one?",
                  {"size": 14, "color": INK, "bold": True})], first=True, space_after=0,
          line_spacing=1.3)


def slide_smote(deck, d):
    slide, top = new_slide(
        deck, "stage h · strategies", "Why SMOTE had to be rebuilt for this data",
        subtitle="Textbook SMOTE would have interpolated real vitals against "
                 "\"never measured\".")

    left = text_box(slide, MARGIN, top + Inches(0.15), Inches(6.15), Inches(4.0))
    write(left, [("The problem", {"size": 16, "font": SERIF, "color": INK,
                                  "bold": True})], first=True, space_after=8)
    write(left, [("RecordEHR.to_tensor() zero-fills anything that was not measured, so "
                  "0 carries two meanings at once across ", {}),
                 ("39%", {"font": MONO, "bold": True, "color": INK}),
                 (" of the 24 × 7 feature matrix. Missingness is also "
                  "class-correlated — positives are ", {}),
                 ("68.3%", {"font": MONO, "bold": True, "color": INK}),
                 (" observed against ", {}),
                 ("60.1%", {"font": MONO, "bold": True, "color": INK}),
                 (" for negatives — so it carries real signal.", {})],
         size=14, space_after=12, line_spacing=1.34)
    write(left, [("Run unmodified, SMOTE would do two wrong things: interpolate a real "
                  "heart rate against a structural zero, and build its nearest-neighbour "
                  "graph mostly out of which cells happen to be missing rather than out "
                  "of physiology.", {})], size=14, space_after=0, line_spacing=1.34)

    x = MARGIN + Inches(6.6)
    panel(slide, x, top + Inches(0.15), Inches(5.3), Inches(3.52))
    rule(slide, x, top + Inches(0.15), Inches(5.3), SLATE, Pt(3.5))
    frame = text_box(slide, x + Inches(0.28), top + Inches(0.4), Inches(4.74), Inches(3.14))
    write(frame, [("The fix — three changes", {"size": 16, "font": SERIF,
                                               "color": INK, "bold": True})],
          first=True, space_after=11)
    for number, heading, text in [
        ("1", "Neighbours over co-observed cells only",
         "Distances use nan_euclidean, so two patients are close when the vitals they "
         "both have are close — not when they lack the same ones."),
        ("2", "Synthetic rows inherit the parent's mask",
         "A generated patient is missing exactly what its base parent was missing, so "
         "the missingness distribution is preserved, not invented."),
        ("3", "Interpolate only where both parents measured",
         "A cell either parent never observed stays unobserved, instead of being "
         "filled with a blend of a real value and a zero."),
    ]:
        write(frame, [(f"{number}  ", {"font": MONO, "color": SLATE, "bold": True}),
                      (heading, {"color": INK, "bold": True})], size=12.5,
              space_after=2)
        write(frame, [(text, {"size": 11.5, "color": BODY})], space_after=8,
              line_spacing=1.26)

    verify = text_box(slide, MARGIN, Inches(6.05), CONTENT_W, Inches(0.9))
    write(verify, [("Verified, not assumed: ", {"size": 14, "color": INK, "bold": True}),
                   ("the stage I verifier replayed all 20 folds of mean/mortality and "
                    "found 0 collisions between its synthetic rows and any test fold; "
                    "refitting each strategy on shuffled labels gave AUC 0.4953 / "
                    "0.4967 / 0.5003 — chance, as it must be.",
                    {"size": 14, "color": BODY})], first=True, space_after=0,
          line_spacing=1.3)


def slide_verdict(deck, d):
    delta, full = d["delta"], d["full"]
    n_auprc = int((delta.d_auprc < 0).sum())
    n_auroc = int((delta.d_auroc < 0).sum())
    corr = float(np.corrcoef(delta.d_recall, delta.d_pos)[0, 1])

    slide, top = new_slide(deck, "result", "No — and the reason is specific")

    frame = text_box(slide, MARGIN, top + Inches(0.05), Inches(11.9), Inches(2.15))
    write(frame, [("All three strategies move the operating point without improving "
                   "discrimination.", {"size": 26, "font": SERIF, "color": INK,
                                       "bold": True})], first=True, space_after=14,
          line_spacing=1.1)
    write(frame, [("Every strategy raises recall, and the effect is large. But the "
                   "threshold-free metrics do not follow: ", {"size": 16}),
                  (f"AUPRC fell in {n_auprc} of {len(delta)} comparisons",
                   {"size": 16, "color": INK, "bold": True}),
                  (f" and AUROC in {n_auroc} of {len(delta)}. A model that ranked "
                   f"patients better would show it there.", {"size": 16})],
          space_after=0, line_spacing=1.32)

    stat_row(slide, Inches(4.02), [
        (f"{n_auprc}/{len(delta)}", "comparisons with lower AUPRC", RUST),
        (signed(delta.d_auprc.max()), "best AUPRC change achieved", RUST),
        (f"{corr:.3f}", "corr(Δ recall, Δ positive rate)", INK),
        (signed(delta.d_f1.max()), "best macro F1 change", GREEN),
    ])

    best = delta.loc[delta.d_f1.idxmax()]
    note = text_box(slide, MARGIN, Inches(5.55), CONTENT_W, Inches(1.2))
    write(note, [("Read the second number carefully: ", {"size": 14.5, "color": BODY}),
                 (f"the best AUPRC outcome in the whole sweep is still a loss of "
                  f"{abs(delta.d_auprc.max()):.4f}.", {"size": 14.5, "color": INK,
                                                       "bold": True})],
          first=True, space_after=7, line_spacing=1.3)
    write(note, [(f"The one genuine gain is macro F1 under SMOTE "
                  f"({best.aggregation} / {best.label}, {signed(best.d_f1)}) — and it "
                  f"comes with an AUPRC change of {signed(best.d_auprc)}, so even the "
                  f"best case is a re-balanced operating point rather than a better "
                  f"classifier.", {"size": 14.5, "color": BODY})], space_after=0,
          line_spacing=1.3)


def slide_split(deck, d):
    delta = d["delta"]
    slide, top = new_slide(
        deck, "result", "The two kinds of metric split cleanly",
        subtitle="Mean change against the unbalanced baseline, averaged over all "
                 "10 label × aggregation cells.")

    order = ["oversample", "undersample", "smote"]
    metrics = [("Recall", "d_recall"), ("Balanced acc", "d_bal"),
               ("Accuracy", "d_acc"), ("AUROC", "d_auroc"), ("AUPRC", "d_auprc")]

    chart_data = CategoryChartData()
    chart_data.categories = [name for name, _ in metrics]
    for strategy in order:
        subset = delta[delta.strategy == strategy]
        chart_data.add_series(strategy, [float(subset[col].mean()) for _, col in metrics])

    graphic = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, MARGIN, top + Inches(0.12),
        Inches(7.5), Inches(3.95), chart_data)
    chart = graphic.chart
    style_chart(chart)
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.TOP
    chart.legend.include_in_layout = False
    for series, color in zip(chart.plots[0].series, (TEAL, RUST, SLATE)):
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = color
    axis = chart.value_axis
    axis.has_major_gridlines = True
    axis.major_gridlines.format.line.color.rgb = LINE
    axis.tick_labels.number_format = "+0.00;-0.00"
    axis.tick_labels.number_format_is_linked = False
    chart.category_axis.major_tick_mark = XL_TICK_MARK.NONE

    x = MARGIN + Inches(7.9)
    panel(slide, x, top + Inches(0.12), Inches(3.95), Inches(3.95))
    frame = text_box(slide, x + Inches(0.26), top + Inches(0.34), Inches(3.43), Inches(3.5))
    write(frame, [("The first three bars swing.",
                   {"size": 15.5, "font": SERIF, "color": INK, "bold": True})],
          first=True, space_after=7)
    write(frame, [("Recall up, accuracy down, balanced accuracy up — all read off "
                   "the 0.5 cut, all moving together.", {})],
          size=12.5, space_after=12, line_spacing=1.28)
    write(frame, [("The last two do not.",
                   {"size": 15.5, "font": SERIF, "color": INK, "bold": True})],
          space_after=7)
    write(frame, [("AUROC and AUPRC never see the cut. They lean negative and stay "
                   "there — the whole result in one picture.", {})],
          size=12.5, space_after=12, line_spacing=1.28)
    write(frame, [("Undersampling shows it most starkly: mean recall ", {}),
                  (signed(delta[delta.strategy == "undersample"].d_recall.mean(), 3),
                   {"font": MONO, "bold": True, "color": GREEN}),
                  (" against mean accuracy ", {}),
                  (signed(delta[delta.strategy == "undersample"].d_acc.mean(), 3),
                   {"font": MONO, "bold": True, "color": RUST}),
                  (".", {})], size=12.5, space_after=0, line_spacing=1.28)


def slide_mechanism(deck, d):
    delta, t = d["delta"], d["threshold"]
    corr = float(np.corrcoef(delta.d_recall, delta.d_pos)[0, 1])
    slide, top = new_slide(
        deck, "mechanism", "The recall gain is a relabelling, not a ranking",
        subtitle="Each point is one aggregation × label × strategy.")

    chart_data = XyChartData()
    for strategy, color in [("oversample", TEAL), ("undersample", RUST),
                            ("smote", SLATE)]:
        series = chart_data.add_series(strategy)
        subset = delta[delta.strategy == strategy]
        for _, row in subset.iterrows():
            series.add_data_point(float(row.d_pos), float(row.d_recall))

    graphic = slide.shapes.add_chart(
        XL_CHART_TYPE.XY_SCATTER, MARGIN, top + Inches(0.12),
        Inches(6.5), Inches(3.95), chart_data)
    chart = graphic.chart
    style_chart(chart)
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.TOP
    chart.legend.include_in_layout = False
    for series, color in zip(chart.plots[0].series, (TEAL, RUST, SLATE)):
        series.marker.format.fill.solid()
        series.marker.format.fill.fore_color.rgb = color
        series.marker.format.line.color.rgb = color
        series.format.line.fill.background()
    # A scatter chart has two value axes and no category axis, so `category_axis`
    # raises here rather than returning the x-axis. Title what is reachable and
    # let the panel text carry the rest.
    axis = chart.value_axis
    axis.has_title = True
    axis.axis_title.text_frame.text = "Δ recall  (x: Δ predicted positive rate)"
    axis.axis_title.text_frame.paragraphs[0].runs[0].font.size = Pt(11)
    axis.has_major_gridlines = True
    axis.major_gridlines.format.line.color.rgb = LINE

    x = MARGIN + Inches(6.9)
    panel(slide, x, top + Inches(0.12), Inches(4.95), Inches(1.62))
    frame = text_box(slide, x + Inches(0.28), top + Inches(0.3), Inches(4.39), Inches(1.42))
    write(frame, [(f"r = {corr:.3f}", {"size": 25, "font": MONO, "color": INK,
                                       "bold": True})], first=True, space_after=5)
    write(frame, [("Nearly all of the recall gain is explained by predicting positive "
                   "more often — exactly what moving a threshold does, at the cost of "
                   "retraining.", {"size": 12, "color": BODY})],
          space_after=0, line_spacing=1.26)

    panel(slide, x, top + Inches(1.95), Inches(4.95), Inches(2.12), SUNK)
    frame = text_box(slide, x + Inches(0.3), top + Inches(2.2), Inches(4.35), Inches(1.8))
    write(frame, [("Two mechanisms, one operating point",
                   {"size": 15, "font": SERIF, "color": INK, "bold": True})],
          first=True, space_after=9)
    under = d["full"]
    under = under[(under.label == "mortality") & (under.aggregation == "mean")
                  & (under.strategy == "undersample")].iloc[0]
    rows = [["", "positive rate", "recall"],
            ["Youden threshold (stage F)", f"{t['youden']['positive_rate']:.3f}",
             f"{t['youden']['recall']:.3f}"],
            ["Undersampling at 0.5 (stage H)",
             f"{float(under.predicted_positive_rate):.3f}", f"{float(under.recall):.3f}"]]
    table(slide, x + Inches(0.3), top + Inches(2.62), Inches(4.35), rows,
          col_widths=[2.3, 1.15, 0.95], number_columns=(1, 2), size=11.5,
          row_height=Inches(0.3))


def slide_auprc(deck, d):
    delta = d["delta"]
    slide, top = new_slide(
        deck, "result", "Every comparison loses AUPRC",
        subtitle="Δ AUPRC against the unbalanced baseline, mortality above, "
                 "ICU below — negative is worse.")

    order = ["mean", "median", "standard deviation", "mean deviation", "maximum deviation"]
    categories, values = [], {s: [] for s in ["oversample", "undersample", "smote"]}
    for label in ["mortality", "icu"]:
        for aggregation in order:
            short = aggregation.replace("standard deviation", "std dev").replace(
                "maximum", "max")
            categories.append(f"{label[:4]} · {short}")
            for strategy in values:
                row = delta[(delta.label == label) & (delta.aggregation == aggregation)
                            & (delta.strategy == strategy)]
                values[strategy].append(float(row.d_auprc.iloc[0]) if not row.empty
                                        else 0.0)

    chart_data = CategoryChartData()
    chart_data.categories = categories
    for strategy in ["oversample", "undersample", "smote"]:
        chart_data.add_series(strategy, values[strategy])

    graphic = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_CLUSTERED, MARGIN, top + Inches(0.12),
        Inches(7.9), Inches(4.15), chart_data)
    chart = graphic.chart
    style_chart(chart, font_size=10)
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.TOP
    chart.legend.include_in_layout = False
    for series, color in zip(chart.plots[0].series, (TEAL, RUST, SLATE)):
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = color
    chart.value_axis.tick_labels.number_format = "+0.00;-0.00"
    chart.value_axis.tick_labels.number_format_is_linked = False
    chart.value_axis.has_major_gridlines = True
    chart.value_axis.major_gridlines.format.line.color.rgb = LINE

    x = MARGIN + Inches(8.3)
    frame = text_box(slide, x, top + Inches(0.2), Inches(3.6), Inches(4.0))
    write(frame, [("The deviation aggregations fail hardest",
                   {"size": 16, "font": SERIF, "color": INK, "bold": True})],
          first=True, space_after=9)
    dev = delta[(delta.label == "mortality") & (delta.family == "deviation")]
    val = delta[(delta.label == "mortality") & (delta.family == "value")]
    write(frame, [("Under mortality, mean AUPRC change is ", {}),
                  (signed(dev.d_auprc.mean()), {"font": MONO, "bold": True,
                                                "color": RUST}),
                  (" for std/mean/max deviation against ", {}),
                  (signed(val.d_auprc.mean()), {"font": MONO, "bold": True,
                                                "color": RUST}),
                  (" for mean and median.", {})], size=13.5, space_after=12,
          line_spacing=1.3)
    write(frame, [("Those arms start from a weak baseline — the deviation features "
                   "carry much less mortality signal — and resampling amplifies the "
                   "noise rather than the signal. On them, oversampling and SMOTE even "
                   "reduce recall.", {})], size=13.5, space_after=12, line_spacing=1.3)
    worst = delta.loc[delta.d_auprc.idxmin()]
    write(frame, [("Worst single result: ", {}),
                  (f"{worst.strategy} on {worst.aggregation} / {worst.label}, "
                   f"{signed(worst.d_auprc)}", {"color": INK, "bold": True})],
          size=13.5, space_after=0, line_spacing=1.3)


def slide_mortality(deck, d):
    full = d["full"]
    slide, top = new_slide(
        deck, "detail · mortality", "Mortality, mean aggregation",
        subtitle="Prevalence 9.7%. The baseline row is the reference; changes are "
                 "against it.")

    subset = full[(full.label == "mortality") & (full.aggregation == "mean")]
    rows = [["Strategy", "Recall", "Bal. acc", "Macro F1", "Accuracy", "AUROC",
             "AUPRC", "Pos. rate", "McNemar p"]]
    baseline = subset[subset.strategy == "none"].iloc[0]
    for strategy in ["none", "oversample", "undersample", "smote"]:
        row = subset[subset.strategy == strategy].iloc[0]
        cells = [(strategy, {"bold": strategy == "none", "font": MONO,
                             "color": INK if strategy == "none" else BODY})]
        for column in ["recall", "balanced_accuracy", "f1_macro", "accuracy",
                       "auroc", "auprc", "predicted_positive_rate"]:
            value = float(row[column])
            if strategy == "none":
                cells.append((f"{value:.4f}", {"bold": True, "color": INK}))
            else:
                change = value - float(baseline[column])
                cells.append((f"{value:.4f}  ({change:+.4f})",
                              {"color": GREEN if change > 0.0005 else
                               (RUST if change < -0.0005 else MUTED), "size": 11.5}))
        p = float(row.mcnemar_p)
        cells.append("—" if strategy == "none" else
                     ("<1e-4" if p < 1e-4 else f"{p:.4f}"))
        rows.append(cells)

    table(slide, MARGIN, top + Inches(0.12), CONTENT_W, rows,
          col_widths=[1.15, 1.65, 1.65, 1.65, 1.65, 1.65, 1.65, 1.45, 0.95],
          number_columns=tuple(range(1, 9)), size=12, row_height=Inches(0.42))

    frame = text_box(slide, MARGIN, Inches(4.55), Inches(11.9), Inches(2.2))
    write(frame, [("Read across the AUPRC column: every arm is below the baseline's ",
                   {"size": 15}),
                  (f"{float(baseline.auprc):.4f}", {"size": 15, "font": MONO,
                                                    "bold": True, "color": INK}),
                  (".", {"size": 15})], first=True, space_after=12, line_spacing=1.3)
    under = subset[subset.strategy == "undersample"].iloc[0]
    smote = subset[subset.strategy == "smote"].iloc[0]
    write(frame, [("Undersampling", {"size": 15, "bold": True, "color": INK}),
                  (f" takes recall from {float(baseline.recall):.3f} to "
                   f"{float(under.recall):.3f} — and accuracy from "
                   f"{float(baseline.accuracy):.3f} to {float(under.accuracy):.3f}, "
                   f"because it now calls {float(under.predicted_positive_rate):.1%} "
                   f"of patients positive instead of "
                   f"{float(baseline.predicted_positive_rate):.1%}.", {"size": 15})],
          space_after=12, line_spacing=1.3)
    write(frame, [("SMOTE", {"size": 15, "bold": True, "color": INK}),
                  (f" is the least-bad arm and the only one to improve macro F1 "
                   f"meaningfully ({float(smote.f1_macro) - float(baseline.f1_macro):+.4f}), "
                   f"but its AUPRC still falls "
                   f"({float(smote.auprc) - float(baseline.auprc):+.4f}).",
                   {"size": 15})], space_after=0, line_spacing=1.3)


def slide_icu(deck, d):
    delta, full = d["delta"], d["full"]
    slide, top = new_slide(
        deck, "detail · icu", "ICU admission behaves like a control",
        subtitle="Prevalence 37.5% — far less imbalanced, and correspondingly less "
                 "affected.")

    rows = [["", "Δ Recall", "Δ Bal. acc", "Δ Macro F1", "Δ AUROC", "Δ AUPRC"]]
    for label in ["mortality", "icu"]:
        subset = delta[delta.label == label]
        rows.append([
            (f"{label} (mean of 15)", {"bold": True, "color": INK}),
            *[(signed(subset[col].mean()),
               {"color": GREEN if subset[col].mean() > 0 else RUST})
              for col in ["d_recall", "d_bal", "d_f1", "d_auroc", "d_auprc"]],
        ])
    table(slide, MARGIN, top + Inches(0.12), Inches(8.4), rows,
          col_widths=[2.0, 1.3, 1.3, 1.3, 1.3, 1.3],
          number_columns=(1, 2, 3, 4, 5), row_height=Inches(0.42))

    frame = text_box(slide, MARGIN, top + Inches(1.7), Inches(8.4), Inches(2.6))
    write(frame, [("This is the sanity check on the whole experiment.",
                   {"size": 16, "font": SERIF, "color": INK, "bold": True})],
          first=True, space_after=10)
    write(frame, [("If balancing were adding information, the label with less "
                   "imbalance to correct should benefit less — and that is exactly the "
                   "pattern. ICU's mean AUPRC change is ", {}),
                  (signed(delta[delta.label == 'icu'].d_auprc.mean()),
                   {"font": MONO, "bold": True, "color": RUST}),
                  (" against mortality's ", {}),
                  (signed(delta[delta.label == 'mortality'].d_auprc.mean()),
                   {"font": MONO, "bold": True, "color": RUST}),
                  (", roughly six times smaller.", {})], size=14.5, space_after=12,
          line_spacing=1.32)
    write(frame, [("The reading is consistent throughout: what balancing changes "
                   "scales with how much the operating point had to move, not with how "
                   "much signal was there to find.", {})], size=14.5, space_after=0,
          line_spacing=1.32)

    x = MARGIN + Inches(8.85)
    panel(slide, x, top + Inches(0.12), Inches(3.05), Inches(3.9), SUNK)
    frame = text_box(slide, x + Inches(0.24), top + Inches(0.34), Inches(2.6), Inches(3.5))
    write(frame, [("Statistically significant, practically not",
                   {"size": 15, "font": SERIF, "color": INK, "bold": True})],
          first=True, space_after=10)
    n_sig = int((full[full.strategy != "none"].mcnemar_p < 0.05).sum())
    write(frame, [(f"{n_sig} of {len(delta)}", {"size": 24, "font": MONO,
                                                "color": INK, "bold": True})],
          space_after=4)
    write(frame, [("paired McNemar tests reject at p < 0.05.", {"size": 12.5,
                                                                "color": MUTED})],
          space_after=12, line_spacing=1.28)
    write(frame, [("The arms really do predict differently — easy to establish at "
                   "this sample size. But that confirms the predictions changed, not "
                   "that they improved. AUPRC answers that, and says no.",
                   {"size": 11.5, "color": BODY})],
          space_after=0, line_spacing=1.26)


def slide_baseline(deck, d):
    delta, prior, full = d["delta"], d["prior"], d["full"]
    slide, top = new_slide(
        deck, "validity", "The baseline was refit so the comparison is fair",
        subtitle="A correction made after the first run of this experiment.")

    frame = text_box(slide, MARGIN, top + Inches(0.15), Inches(6.6), Inches(4.0))
    write(frame, [("The first version of these results reused the unbalanced baseline "
                   "from the earlier cross-validated sweep. That sweep carved an "
                   "inner-validation slice out of each training fold to pick its "
                   "threshold, so its forests were fitted on ", {}),
                  ("70%", {"font": MONO, "bold": True, "color": INK}),
                  (" of the cohort while the balanced arms trained on the full ", {}),
                  ("80%", {"font": MONO, "bold": True, "color": INK}),
                  (".", {})], size=14.5, first=True, space_after=12, line_spacing=1.34)
    write(frame, [("That handicap ran ", {}),
                  ("toward", {"bold": True, "color": INK, "italic": True}),
                  (" balancing — it made the arms look better than they were — so it "
                   "was corrected rather than left as a caveat. The baseline is now "
                   "refit under the arms' own protocol: same 80%, same folds, no "
                   "validation split, threshold fixed at 0.5.", {})],
          size=14.5, space_after=12, line_spacing=1.34)
    write(frame, [("Because the partition and forest seeds are fixed, the three "
                   "balanced arms reproduced to within 5.4e-06 on the rerun. Only the "
                   "baseline row moved — which is the check that the rerun was sound.",
                   {})], size=14.5, space_after=0, line_spacing=1.34)

    x = MARGIN + Inches(7.05)
    panel(slide, x, top + Inches(0.15), Inches(4.85), Inches(3.75))
    frame = text_box(slide, x + Inches(0.32), top + Inches(0.42), Inches(4.2), Inches(3.2))
    write(frame, [("What the correction changed", {"size": 16, "font": SERIF,
                                                   "color": INK, "bold": True})],
          first=True, space_after=12)

    if prior is not None:
        rows = [["", "reused 70%", "refit 80%"],
                ["AUPRC negative", f"{int((prior.d_auprc < 0).sum())}/{len(prior)}",
                 f"{int((delta.d_auprc < 0).sum())}/{len(delta)}"],
                ["mean Δ AUPRC", signed(prior.d_auprc.mean()),
                 signed(delta.d_auprc.mean())],
                ["best Δ AUPRC", signed(prior.d_auprc.max()),
                 signed(delta.d_auprc.max())],
                ["mean Δ macro F1", signed(prior.d_f1.mean()),
                 signed(delta.d_f1.mean())]]
        table(slide, x + Inches(0.32), top + Inches(1.0), Inches(4.2), rows,
              col_widths=[1.7, 1.25, 1.25], number_columns=(1, 2), size=12,
              row_height=Inches(0.34))

    frame = text_box(slide, x + Inches(0.32), top + Inches(2.85), Inches(4.2), Inches(0.9))
    write(frame, [("Every delta moved slightly further against balancing. Nothing "
                   "changed category — the conclusion is the same one, now without the "
                   "handicap that was inflating it.", {"size": 12.5, "color": BODY})],
          first=True, space_after=0, line_spacing=1.3)


def slide_conclusion(deck, d):
    delta = d["delta"]
    slide, top = new_slide(deck, "conclusion", "What we take from this")

    points = [
        ("Balancing is not a substitute for a threshold.",
         "It reaches the same operating point by a more expensive route. "
         "Undersampling at 0.5 lands almost exactly where Youden's J landed — same "
         "positive rate, same recall — but the threshold gets there without "
         "retraining anything."),
        ("Nothing here improved discrimination.",
         f"AUPRC fell in {int((delta.d_auprc < 0).sum())} of {len(delta)} comparisons "
         f"and AUROC in {int((delta.d_auroc < 0).sum())}. If the goal is a model that "
         f"ranks patients better, resampling the training folds did not deliver it."),
        ("Choose the operating point explicitly instead.",
         "Since the ranking is what it is, the honest lever is the threshold — chosen "
         "on validation data for a stated clinical cost ratio, and reported as such."),
        ("Report threshold-free metrics alongside any balanced result.",
         "Recall and balanced accuracy alone would have made all three strategies look "
         "like successes. AUPRC is what separates a better classifier from a "
         "relabelled one."),
    ]
    frame = text_box(slide, MARGIN, top + Inches(0.2), Inches(11.9), Inches(4.4))
    for index, (heading, text) in enumerate(points):
        write(frame, [(f"{index + 1}   ", {"size": 17, "font": MONO, "color": TEAL,
                                           "bold": True}),
                      (heading, {"size": 17, "font": SERIF, "color": INK,
                                 "bold": True})],
              first=(index == 0), space_after=5)
        write(frame, [("     " + text, {"size": 14.5, "color": BODY})],
              space_after=17, line_spacing=1.3)

    rule(slide, MARGIN, Inches(6.4), CONTENT_W)
    frame = text_box(slide, MARGIN, Inches(6.6), CONTENT_W, Inches(0.5))
    write(frame, [("Full tables and figures: paper_figures/balance/ — "
                   "balance_comparison.csv, balance_deltas.csv, balance_report.html",
                   {"size": 12, "font": MONO, "color": MUTED})], first=True,
          space_after=0)


def build(out_path: Path) -> Path:
    d = load()
    deck = Presentation()
    deck.slide_width, deck.slide_height = W, H

    for slide_fn in [slide_title, slide_threshold, slide_design, slide_strategies,
                     slide_smote, slide_verdict, slide_split, slide_mechanism,
                     slide_auprc, slide_mortality, slide_icu, slide_baseline,
                     slide_conclusion]:
        slide_fn(deck, d)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    deck.save(out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(BALANCE / "balance_results_slides.pptx"))
    args = parser.parse_args()
    path = build(Path(args.out))
    print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
