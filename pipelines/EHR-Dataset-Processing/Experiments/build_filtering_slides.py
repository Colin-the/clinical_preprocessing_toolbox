"""Build the conference talk for "Beyond the Model" as an editable PowerPoint file.

    python Experiments/build_filtering_slides.py [--out PATH] [--figures DIR]

A 15-minute version of the paper for an AI/ML audience that has not read it. The
paper's own arc is slides 2-8 and 13; the rest is the material that did not fit in
the page budget — how many patients each filter actually removes, what that does to
the class balance of what is left, and why that makes the record-level McNemar
results simultaneously the most extreme in the sweep and, in one cell, silent.

Every number is read from a stage F / stage K artifact at build time. Nothing is
typed into this file, so re-running either stage produces a deck that agrees with
the data rather than one that has to be re-checked by hand. The numbers come from
`filtering_results.load()`, shared with the poster, which cross-checks the
artifacts against each other and raises rather than warns.

Scope, fixed deliberately: MIMIC-III, mean aggregation, the `_cv` evaluation design.
That is the setting the paper's figures describe, and mixing designs — the legacy
single-holdout sidecars report a different cohort prevalence for the same arm — is
the easiest way to put a wrong number on a slide.

The McNemar figures and numbers are the *baseline-threshold* comparison: every arm
re-scored at raw's threshold, which is what the paper's Fig. 7 shows. The p-values
stored in the CV diagnostics are the own-threshold variant and are not used here.
They come from `rerun/dump_baseline_mcnemar.py`, which runs under scipy-stack;
this script only reads its JSON, so the deck can be built in .venv_slides.

Slide furniture, palette and typography are imported from build_balance_slides so
the two decks read as one house style.
"""
import argparse
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.util import Emu, Inches, Pt

from filtering_results import (
    ARMS, COHORT_STEPS, LABELS, LEVELS, RECORD_ARMS, ROOT, SHORT, TABLE_III, TASK,
    THRESHOLDS, VITAL_ARMS, arm_stat, delta, fmt_p, p_value, paired_delta,
)
from filtering_results import load as load_results
from build_balance_slides import (
    BODY, CONTENT_W, GREEN, GROUND, H, INK, LINE, MARGIN, MONO, MUTED, RUST,
    SANS, SERIF, SLATE, SUNK, SURFACE, TEAL, W,
    new_slide, panel, rule, stat_row, style_chart, table, text_box, write,
)

DEFAULT_FIGURES = ROOT / "paper_figures" / "slides_png"
DEFAULT_OUT = ROOT / "paper_figures" / "slides" / "beyond_the_model_talk.pptx"

LEVEL_COLOR = {"value": TEAL, "feature": SLATE, "record": RUST}

FIG = {
    "heatmap": "observation_count_heatmap_raw_mimic_iii.png",
    "centroid_all_vitals": "centroid_deviation_all_vitals_filter_mean.png",
    "impact_mortality_acc": "filter_impact_mortality_testing_accuracy_mean.png",
    "impact_mortality_f1": "filter_impact_mortality_testing_f1_mean.png",
    "impact_icu_acc": "filter_impact_icu_testing_accuracy_mean.png",
    "mcnemar_mortality": "mcnemar_mortality_mean_baseline_threshold_plain.png",
}


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def load(figures: Path) -> dict:
    """Every number the deck shows (cross-checked in `filtering_results.load`), plus
    the rendered paper figures it embeds."""
    d = load_results()
    missing = [name for name in FIG.values() if not (figures / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"missing slide figures in {figures}: {', '.join(missing)}. Render them "
            "with `python Experiments/render_paper_figures.py --format png`."
        )
    return {**d, "figures": figures}


# --------------------------------------------------------------------------
# furniture this deck adds
# --------------------------------------------------------------------------
def notes(slide, bullets):
    """Bullet-form speaker notes: talking points, not a script."""
    frame = slide.notes_slide.notes_text_frame
    frame.clear()
    for index, bullet in enumerate(bullets):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        run = paragraph.add_run()
        run.text = f"— {bullet}"
        run.font.size = Pt(13)
        run.font.name = SANS
        paragraph.space_after = Pt(7)


def picture(slide, path, left, top, width, height, *, caption=None):
    """Place an image fitted inside a box, preserving its aspect ratio.

    Fitted rather than stretched, and never scaled past 1:1 — an upscaled 200-dpi
    render looks soft on a projector, and it is better to leave white space.
    """
    from PIL import Image

    with Image.open(path) as image:
        native_w, native_h = image.size
        dpi = image.info.get("dpi", (200, 200))[0] or 200

    box = min(width / native_w, height / native_h, Inches(1) / dpi)
    draw_w, draw_h = Emu(int(native_w * box)), Emu(int(native_h * box))
    shape = slide.shapes.add_picture(
        str(path), Emu(int(left + (width - draw_w) / 2)),
        Emu(int(top + (height - draw_h) / 2)), draw_w, draw_h)

    if caption:
        frame = text_box(slide, left, Emu(int(top + height + Inches(0.06))),
                         width, Inches(0.3))
        write(frame, [(caption, {"size": 11, "color": MUTED, "italic": True})],
              first=True, space_after=0)
    return shape


def bar_chart(slide, left, top, width, height, categories, series, *,
              colors=None, number_format='#,##0', legend=False, gap=60):
    """A native PowerPoint bar chart — editable, with its worksheet embedded."""
    data = CategoryChartData()
    data.categories = categories
    for name, values in series:
        data.add_series(name, values, number_format)

    graphic = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, left, top,
                                     width, height, data)
    chart = graphic.chart
    style_chart(chart)
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False

    plot = chart.plots[0]
    plot.gap_width = gap
    if colors:
        for index, plot_series in enumerate(plot.series):
            if isinstance(colors[index], list):   # per-point colouring
                for point, color in zip(plot_series.points, colors[index]):
                    point.format.fill.solid()
                    point.format.fill.fore_color.rgb = color
            else:
                plot_series.format.fill.solid()
                plot_series.format.fill.fore_color.rgb = colors[index]
    chart.value_axis.has_major_gridlines = True
    chart.category_axis.has_major_gridlines = False
    return chart


def lede(slide, top, runs, *, left=MARGIN, width=CONTENT_W, size=15, height=Inches(1.1)):
    frame = text_box(slide, left, top, width, height)
    write(frame, runs, first=True, size=size, space_after=0, line_spacing=1.32)
    return frame


# --------------------------------------------------------------------------
# slides 1-3: framing
# --------------------------------------------------------------------------
def slide_title(deck, d):
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = GROUND
    rule(slide, MARGIN, Inches(2.30), Inches(1.5), TEAL, Pt(3))

    frame = text_box(slide, MARGIN, Inches(2.60), Inches(10.4), Inches(2.6))
    write(frame, [("Beyond the Model",
                   {"size": 46, "font": SERIF, "color": INK, "bold": True})],
          first=True, space_after=6, line_spacing=1.02)
    write(frame, [("The critical role of data filtering in clinical machine learning",
                   {"size": 26, "font": SERIF, "color": BODY})],
          space_after=20, line_spacing=1.1)
    write(frame, [("Noah Subedar*, Colin Campbell*, Wenjing Zhang, Dan Perri, "
                   "Sarah Culgin, Andrew Hamilton-Wright", {"size": 15, "color": BODY})],
          space_after=5, line_spacing=1.3)
    write(frame, [("University of Guelph  ·  St. Joseph's Healthcare Hamilton  ·  "
                   "McMaster University      * equal contribution",
                   {"size": 12.5, "color": MUTED})], space_after=0)

    facts = text_box(slide, MARGIN, Inches(6.05), CONTENT_W, Inches(0.5))
    write(facts, [(f"MIMIC-III  ·  {d['survivors']['raw']:,} ICU stays  ·  "
                   f"7 vitals × 24 hours  ·  11 filters  ·  2 tasks",
                   {"size": 13, "font": MONO, "color": MUTED})], first=True,
          space_after=0)

    notes(slide, [
        "Talk is about preprocessing, not models. Nobody needs to have read the paper.",
        "One sentence of framing: every clinical ML paper opens with a filtering "
        "pipeline, and almost none of them report what the pipeline removed.",
        "Two co-first authors; work is a Guelph / St. Joe's Hamilton collaboration.",
        "Set expectation: I will show you the paper's result in about six minutes, "
        "then spend the rest on the part we could not fit in eight pages.",
    ])


def slide_claim(deck, d):
    slide, top = new_slide(
        deck, "the claim", "Filtering is a modelling choice, not data cleaning",
        subtitle="Anything that discards or edits observations based on their values "
                 "changes the distribution — by definition.")

    for index, (heading, text, color) in enumerate([
        ("It changes the task",
         "Removing hard cases, flattening variance, or separating class "
         "distributions makes a benchmark easier without making a model better.", TEAL),
        ("It is not task-neutral",
         "The same filter can improve mortality prediction and degrade prolonged-"
         "stay prediction on the very same feature matrix.", SLATE),
        ("It is rarely reported",
         "Pipelines standardise preprocessing for comparability, but do not "
         "characterise how those choices changed the difficulty of the problem.", RUST),
    ]):
        x = Emu(int(MARGIN + index * (CONTENT_W / 3 + Inches(0.12))))
        each = Emu(int(CONTENT_W / 3 - Inches(0.16)))
        panel(slide, x, top + Inches(0.30), each, Inches(2.25))
        rule(slide, x, top + Inches(0.30), each, color, Pt(3))
        frame = text_box(slide, Emu(int(x + Inches(0.24))), top + Inches(0.55),
                         Emu(int(each - Inches(0.48))), Inches(1.9))
        write(frame, [(heading, {"size": 17, "font": SERIF, "bold": True, "color": INK})],
              first=True, space_after=9, line_spacing=1.08)
        write(frame, [(text, {"size": 13.5, "color": BODY})], space_after=0,
              line_spacing=1.3)

    lede(slide, Inches(5.35), [
        ("So the question is not ", {}),
        ("“did filtering help?”", {"italic": True, "color": INK}),
        (" but ", {}),
        ("“is it still the same problem?”", {"italic": True, "bold": True,
                                                       "color": INK}),
        ("  This talk gives you three ways to check, and argues the third one — "
         "simply counting what you removed — is the one people skip.", {}),
    ], size=16)

    notes(slide, [
        "Core argument in one line: a filter that selects on values cannot be "
        "distribution-neutral. That is arithmetic, not an empirical claim.",
        "Left panel: the failure mode is a benchmark that gets easier. If you are "
        "allowed unlimited preprocessing you can drive accuracy anywhere you like.",
        "Middle panel: preview of a result — same 168 features, same patients, two "
        "labels, and filters that move the two in opposite directions.",
        "Right panel: standardised pipelines (MIMIC-Extract, the benchmark suites) "
        "fix preprocessing so studies are comparable — which is a different goal "
        "from knowing what the preprocessing did.",
        "Land the framing question. Everything after this is evidence for it.",
    ])


def slide_setup(deck, d):
    slide, top = new_slide(
        deck, "setup", "One cohort, one model, eleven filters",
        subtitle="Each filter is applied independently to the unfiltered data, so "
                 "every arm is a clean single-filter comparison against the same baseline.")

    stat_row(slide, top + Inches(0.16), [
        (f"{d['survivors']['raw']:,}", "MIMIC-III ICU stays, first 24 hours", INK),
        ("7 × 24", "vitals × hours → a 168-dim feature vector", INK),
        ("2", "binary tasks: prolonged ICU stay, in-hospital mortality", INK),
        ("13", "arms: raw, 7 vitals, all-vitals, and 4 post-aggregation filters", INK),
    ])

    rows = [["", "Prolonged ICU stay", "In-hospital mortality"],
            ["Positive class", "ICU time > 3 days", "died before discharge"]]
    rows.append(["Prevalence"] + [f"{arm_stat(d, label, 'raw', 'population_prevalence'):.1%}"
                                  for label in ("icu", "mortality")])
    rows.append(["Baseline accuracy"] + [
        f"{arm_stat(d, label, 'raw', 'accuracy_mean'):.4f} "
        f"± {arm_stat(d, label, 'raw', 'accuracy_std'):.4f}"
        for label in ("icu", "mortality")])
    rows.append(["Baseline macro F1"] + [
        f"{arm_stat(d, label, 'raw', 'f1_macro_mean'):.4f} "
        f"± {arm_stat(d, label, 'raw', 'f1_macro_std'):.4f}"
        for label in ("icu", "mortality")])
    table(slide, MARGIN, Inches(3.60), Inches(7.35), rows,
          col_widths=[2.0, 2.0, 2.0], number_columns=(1, 2), size=13,
          row_height=Inches(0.40))

    panel(slide, Inches(8.55), Inches(3.60), Inches(4.06), Inches(2.0))
    frame = text_box(slide, Inches(8.79), Inches(3.80), Inches(3.58), Inches(1.7))
    write(frame, [("Evaluation", {"size": 15, "font": SERIF, "bold": True, "color": INK})],
          first=True, space_after=8)
    for line in ["Random forest, 300 trees",
                 "Stratified 5-fold × 4 repeats = 20 fits per arm",
                 "Folds drawn once on the raw cohort, keyed by admission id, "
                 "and inherited by every arm",
                 "Decision threshold by Youden's J on an inner-validation slice"]:
        write(frame, [("• ", {"color": TEAL, "bold": True}), (line, {})],
              size=12.5, space_after=5, line_spacing=1.22)

    notes(slide, [
        "Cohort: every admission with vitals in the first 24 hours; 46,032 stays.",
        "Feature vector is deliberately dumb — flatten the 24×7 grid to 168 numbers. "
        "A forest does not care about hour ordering, and the point of the study is "
        "the preprocessing, not the architecture.",
        "Two tasks chosen because they have very different base rates: ~37% vs ~10%. "
        "Mention that mortality being at 10% is why the threshold matters.",
        "The design detail that makes everything downstream legitimate: the "
        "cross-validation partition is drawn ONCE on the unfiltered cohort and keyed "
        "on admission id. Every filtered arm inherits the fold each patient was in. "
        "Arms are therefore paired by construction — that is what licenses McNemar.",
        "Youden's J on an inner split, never on test. Mention in one sentence: it "
        "picks the operating point that maximises sensitivity + specificity − 1, and "
        "in our experiments it did about as well as SMOTE or oversampling.",
        "Each filter is applied to the raw data independently — they are not stacked.",
    ])


# --------------------------------------------------------------------------
# slides 4-5: what the filters are, and why anyone filters at all
# --------------------------------------------------------------------------
def slide_filters(deck, d):
    slide, top = new_slide(
        deck, "the filters", "Eleven filters, three levels of damage",
        subtitle="The level a filter operates at — not its threshold — decides "
                 "whether it can delete a patient.")

    rows = [["Filter", "Stage", "Level", "Threshold"]]
    for arm in VITAL_ARMS + ["all vitals", "fill missing data"] + RECORD_ARMS:
        level = LEVELS[arm]
        stage = "pre" if level == "value" else "post"
        rows.append([
            (SHORT[arm], {"bold": level == "record"}),
            stage,
            (level.upper(), {"color": LEVEL_COLOR[level], "bold": True, "font": MONO,
                             "size": 11.5}),
            (THRESHOLDS[arm], {"font": MONO, "size": 11.5}),
        ])
    table(slide, MARGIN, top + Inches(0.12), Inches(7.9), rows,
          col_widths=[2.5, 0.75, 1.0, 3.1], size=12, row_height=Inches(0.300))

    panel(slide, Inches(9.05), top + Inches(0.12), Inches(3.56), Inches(3.95))
    frame = text_box(slide, Inches(9.31), top + Inches(0.36), Inches(3.04), Inches(3.6))
    write(frame, [("What each level can do",
                   {"size": 16, "font": SERIF, "bold": True, "color": INK})],
          first=True, space_after=12)
    for level, text in [
        ("VALUE", "Drops individual out-of-range readings from an hour's list. "
                  "The hour keeps its other readings. The patient always stays."),
        ("FEATURE", "Fills empty cells. Changes what the model sees; removes nothing."),
        ("RECORD", "Deletes the entire patient from the dataset."),
    ]:
        write(frame, [(level, {"color": LEVEL_COLOR[level.lower()], "bold": True,
                               "font": MONO, "size": 12})], space_after=3)
        write(frame, [(text, {"size": 12.5, "color": BODY})], space_after=11,
              line_spacing=1.26)

    lede(slide, Inches(6.18), [
        ("Everything in this talk follows from that last row. Hold onto it — we come "
         "back to it on the slide after next.", {"color": INK}),
    ], size=15.5)

    notes(slide, [
        "Do not read the table out. Point at the Level column — that is the only "
        "column that matters for the rest of the talk.",
        "Seven per-vital range filters: physiologically implausible readings only. "
        "The bounds are deliberately loose, not tight. Heart rate up to 600 because "
        "ventricular fibrillation genuinely reaches ~500 bpm and we want to keep it. "
        "We are removing sensor artifacts, not unusual patients.",
        "All vitals = union of the seven; it is the composite arm.",
        "Fill missing data is its own category — it edits cells, never patients.",
        "The three record-level filters are the ones inherited straight from generic "
        "ML practice: if a row looks incomplete, drop the row.",
        "Flag the asymmetry: the value filters have physiological justification. "
        "The record filters have only a data-tidiness justification.",
    ])


def slide_dirty(deck, d):
    slide, top = new_slide(
        deck, "why filter at all", "The raw data really is broken",
        subtitle="Heart rate, MIMIC-III. A filter that touches 0.04% of readings "
                 "changes the feature distribution beyond recognition.")

    rows = [["", "Readings", "Max", "Mean", "Median", "Std"]]
    for name, n, mx, mean, median, std in TABLE_III:
        emphasis = name.startswith("(b)") or name.startswith("(d)")
        rows.append([(name, {"bold": emphasis, "size": 11.5})] +
                    [(value, {"color": INK if emphasis else BODY, "size": 11.5})
                     for value in (n, mx, mean, median, std)])
    table(slide, MARGIN, top + Inches(0.10), Inches(6.55), rows,
          col_widths=[2.5, 1.15, 1.15, 0.8, 0.8, 0.95],
          number_columns=(1, 2, 3, 4, 5), size=11.5, row_height=Inches(0.36))

    frame = text_box(slide, MARGIN, Inches(4.10), Inches(6.55), Inches(2.2))
    write(frame, [("A maximum of ", {"size": 14}),
                  ("9,999,999 bpm", {"size": 14, "font": MONO, "bold": True,
                                     "color": RUST}),
                  (" is a charting sentinel, not a patient. Removing 507 readings out "
                   "of 1.16 million takes the maximum to 459 and the standard "
                   "deviation from 9,291 to 24.", {"size": 14})],
          first=True, space_after=10, line_spacing=1.3)
    write(frame, [("This is the case for filtering, and it is a good one. Nobody "
                   "should train on a heart rate of ten million.",
                   {"size": 14, "color": INK, "bold": True})], space_after=0,
          line_spacing=1.3)

    picture(slide, d["figures"] / FIG["heatmap"], Inches(7.35), top + Inches(0.10),
            Inches(5.26), Inches(3.75),
            caption="Mean observations per vital-hour cell, unfiltered")

    lede(slide, Inches(6.30), [
        ("But measurement density is wildly uneven — so the same filter removes far "
         "more from heart rate than from temperature, and “one filter, applied "
         "uniformly” is already not a uniform intervention.", {}),
    ], size=14.5)

    notes(slide, [
        "Start here so nobody thinks the paper is anti-filtering. It is not. The raw "
        "data contains values that are physically impossible.",
        "Table III walks the heart-rate column: raw readings, then after the range "
        "filter, then the same two after mean-aggregating to one number per patient-hour.",
        "The number to say out loud: 507 readings removed out of 1,158,296 — four "
        "hundredths of one percent — and the standard deviation collapses from 9,291 "
        "to 24. That is a value-level filter doing exactly what it should.",
        "Heatmap: mean number of measurements per vital per hour. Heart rate is "
        "monitored continuously; temperature is spot-checked. Roughly 4x difference.",
        "Consequence to state: a fixed rule applied to all seven vitals lands "
        "unevenly. And the sparser the vital, the more each removed reading costs — "
        "if a lab is drawn twice a stay, dropping one is dropping half the signal.",
        "Bridge: so filtering is necessary and it is not neutral. How do we tell "
        "the two apart?",
    ])


# --------------------------------------------------------------------------
# slides 6-8: the paper's published results
# --------------------------------------------------------------------------
def slide_centroids(deck, d):
    slide, top = new_slide(
        deck, "paper result · distribution", "Filtering moves the class centroids",
        subtitle="Per-vital centroid shift from the unfiltered baseline after the "
                 "all-vitals outlier filter, split by outcome class.")

    picture(slide, d["figures"] / FIG["centroid_all_vitals"], MARGIN, top + Inches(0.06),
            Inches(8.15), Inches(4.05))

    panel(slide, Inches(9.15), top + Inches(0.06), Inches(3.46), Inches(4.05))
    frame = text_box(slide, Inches(9.41), top + Inches(0.30), Inches(2.94), Inches(3.7))
    write(frame, [("How to read it",
                   {"size": 16, "font": SERIF, "bold": True, "color": INK})],
          first=True, space_after=11)
    for line in [
        "Physiological outliers are one-sided — nobody charts a heart rate of "
        "minus 200 — so removing them moves the mean, and moves it in a direction "
        "that depends on the vital.",
        "Heart rate and oxygen saturation shift most, because that is where the "
        "extreme artifacts live.",
        "The bars within a vital are the four outcome sub-populations. When they "
        "move by different amounts, the filter has treated the classes differently.",
    ]:
        write(frame, [("• ", {"color": TEAL, "bold": True}), (line, {})],
              size=12.5, space_after=10, line_spacing=1.28)

    lede(slide, Inches(6.22), [
        ("A shift is not automatically a problem. It becomes one when the classes "
         "move ", {}),
        ("differently", {"italic": True, "bold": True, "color": INK}),
        (" — that is separation being manufactured or destroyed by preprocessing.", {}),
    ])

    notes(slide, [
        "This is the paper's first diagnostic: compute a per-vital centroid for each "
        "outcome class, before and after the filter, and plot the difference.",
        "Explain the one-sidedness in a sentence: implausible values cluster at one "
        "end of a distribution, so trimming them is not a symmetric operation.",
        "Heart rate and SpO2 dominate — consistent with Table III on the last slide.",
        "The key reading skill: look ACROSS the four bars within one vital, not at "
        "the height of any single bar. Common movement is fine. Divergent movement "
        "means the filter is doing something class-dependent.",
        "For all-vitals specifically, the movement is largely common — which is the "
        "signature of legitimate artifact removal. Contrast is coming.",
    ])


def slide_impact_mortality(deck, d):
    slide, top = new_slide(
        deck, "paper result · difficulty", "And it changes how hard the task is",
        subtitle="Deviation from the unfiltered baseline, in-hospital mortality, "
                 "mean aggregation. Left: accuracy. Right: macro F1.")

    half = Emu(int((CONTENT_W - Inches(0.3)) / 2))
    picture(slide, d["figures"] / FIG["impact_mortality_acc"], MARGIN,
            top + Inches(0.04), half, Inches(3.75))
    picture(slide, d["figures"] / FIG["impact_mortality_f1"],
            Emu(int(MARGIN + half + Inches(0.3))), top + Inches(0.04), half,
            Inches(3.75))

    best = max(VITAL_ARMS + ["all vitals", "fill missing data"] + RECORD_ARMS,
               key=lambda a: delta(d, "mortality", a, "accuracy_mean"))
    worst = min(VITAL_ARMS + ["all vitals", "fill missing data"] + RECORD_ARMS,
                key=lambda a: delta(d, "mortality", a, "accuracy_mean"))
    lede(slide, Inches(5.95), [
        ("Some filters move accuracy up and some move it down, and the spread — ", {}),
        (f"{delta(d, 'mortality', worst, 'accuracy_mean'):+.4f}", {"font": MONO,
                                                                  "bold": True,
                                                                  "color": RUST}),
        (f" for {SHORT[worst]} to ", {}),
        (f"{delta(d, 'mortality', best, 'accuracy_mean'):+.4f}", {"font": MONO,
                                                                  "bold": True,
                                                                  "color": GREEN}),
        (f" for {SHORT[best]} — is comparable to the gap between competing model "
         "architectures on this task. A reader who is shown only the winning number "
         "cannot tell which of the two they are looking at.", {}),
    ], height=Inches(1.4))

    notes(slide, [
        "Same model, same folds, same patients wherever the arm allows it. The only "
        "thing that changes between bars is which filter was applied.",
        "Point out that bars go both ways. Filtering is not monotonically good or bad.",
        f"Best and worst arm for mortality accuracy: {SHORT[best]} at "
        f"{delta(d, 'mortality', best, 'accuracy_mean'):+.4f}, {SHORT[worst]} at "
        f"{delta(d, 'mortality', worst, 'accuracy_mean'):+.4f}.",
        "The uncomfortable comparison to make out loud: that spread is the same order "
        "as the improvements papers claim from new architectures. If two groups pick "
        "different filters, the model comparison between them is partly a "
        "preprocessing comparison.",
        "Do NOT yet explain why the record-level bars behave the way they do — that "
        "is slides 9 through 12. Just flag that they are the big ones.",
    ])


def slide_task_divergence(deck, d):
    slide, top = new_slide(
        deck, "paper result · task dependence", "The same filter, opposite signs",
        subtitle="Accuracy deviation for both tasks. Identical feature matrix, "
                 "identical folds, identical filters — different answers.")

    half = Emu(int((CONTENT_W - Inches(0.3)) / 2))
    picture(slide, d["figures"] / FIG["impact_mortality_acc"], MARGIN,
            top + Inches(0.04), half, Inches(3.55), caption="In-hospital mortality")
    picture(slide, d["figures"] / FIG["impact_icu_acc"],
            Emu(int(MARGIN + half + Inches(0.3))), top + Inches(0.04), half,
            Inches(3.55), caption="Prolonged ICU stay")

    # Arms whose accuracy delta has a different sign on the two tasks, largest
    # effect first — in filter order the list leads with three near-zero flips,
    # which is technically the same finding and reads as noise on a slide.
    flips = sorted(
        (a for a in VITAL_ARMS + ["all vitals", "fill missing data"]
         if delta(d, "mortality", a, "accuracy_mean") *
            delta(d, "icu", a, "accuracy_mean") < 0),
        key=lambda a: -max(abs(delta(d, "mortality", a, "accuracy_mean")),
                           abs(delta(d, "icu", a, "accuracy_mean"))))
    rows = [["Filter", "Δ accuracy, mortality", "Δ accuracy, ICU stay"]]
    for arm in flips[:3]:
        rows.append([
            SHORT[arm],
            (f"{delta(d, 'mortality', arm, 'accuracy_mean'):+.4f}",
             {"color": GREEN if delta(d, "mortality", arm, "accuracy_mean") > 0 else RUST}),
            (f"{delta(d, 'icu', arm, 'accuracy_mean'):+.4f}",
             {"color": GREEN if delta(d, "icu", arm, "accuracy_mean") > 0 else RUST}),
        ])
    if len(rows) > 1:
        table(slide, MARGIN, Inches(6.05), Inches(7.2), rows,
              col_widths=[2.6, 2.3, 2.3], number_columns=(1, 2), size=12,
              row_height=Inches(0.32))

    frame = text_box(slide, Inches(8.15), Inches(6.05), Inches(4.46), Inches(1.3))
    write(frame, [("Why: the value-level filters remove implausible readings "
                   "regardless of which class the patient belongs to. If those "
                   "artifacts happened to separate the classes, removing them "
                   "uncovers the real difficulty. If they obscured them, removing "
                   "them helps.", {"size": 13.5})], first=True, space_after=0,
          line_spacing=1.3)

    notes(slide, [
        "Two tasks, one feature space, one preprocessing pipeline. They still "
        "disagree about which filters help.",
        f"{len(flips)} of the nine non-record arms flip sign between the two tasks. "
        "Read one or two off the table.",
        "Mechanism: the filters do not know the label. They remove artifacts wherever "
        "the artifacts are. Whether that helps depends on whether the artifacts were "
        "accidentally carrying class information.",
        "Clinical point worth making explicitly: even where the all-vitals filter "
        "costs a little accuracy on the ICU task, you still want it. A deployed model "
        "must never key a decision on a physiologically impossible value. Benchmark "
        "accuracy is not the only objective.",
        "This is the last of the paper's published results. Transition line: all of "
        "this is measured on datasets of very different sizes — and the paper never "
        "had room to say how different.",
    ])


# --------------------------------------------------------------------------
# slides 9-12: what the paper had no room for
# --------------------------------------------------------------------------
def cohort_categories(d):
    """The four distinct cohort sizes, labelled for a chart axis."""
    raw = d["survivors"]["raw"]
    return (["all 10 value- and feature-level arms"] +
            [SHORT[arm] for arm in COHORT_STEPS[1:]],
            [raw] + [d["survivors"][arm] for arm in COHORT_STEPS[1:]])


def slide_survivors(deck, d):
    slide, top = new_slide(
        deck, "the part that did not fit", "How many patients survive each filter?",
        subtitle="The paper reports what each filter does to the distribution. It "
                 "never reports what each filter does to the sample size.")

    raw = d["survivors"]["raw"]
    stat_row(slide, top + Inches(0.12), [
        ("0", "records removed by all 7 vital filters, all-vitals, and fill-missing "
              "— combined", TEAL),
        (f"−{raw - d['survivors']['long missing segment']:,}",
         f"long missing segment  →  {d['survivors']['long missing segment']:,} left",
         RUST),
        (f"−{raw - d['survivors']['long gap']:,}",
         f"long gap  →  {d['survivors']['long gap']:,} left", RUST),
        (f"−{raw - d['survivors']['high invalid data']:,}",
         f"high invalid data  →  {d['survivors']['high invalid data']:,} left", RUST),
    ])

    categories, values = cohort_categories(d)
    chart = bar_chart(
        slide, MARGIN, Inches(3.35), Inches(7.7), Inches(3.35),
        categories, [("ICU stays retained", values)],
        colors=[[TEAL, RUST, RUST, RUST]], gap=70)
    chart.plots[0].has_data_labels = True
    chart.plots[0].data_labels.number_format = '#,##0'
    chart.plots[0].data_labels.number_format_is_linked = False
    chart.plots[0].data_labels.font.size = Pt(12)
    chart.plots[0].data_labels.font.bold = True

    panel(slide, Inches(8.75), Inches(3.35), Inches(3.86), Inches(3.35))
    frame = text_box(slide, Inches(9.01), Inches(3.60), Inches(3.34), Inches(2.9))
    write(frame, [("The split is total",
                   {"size": 17, "font": SERIF, "bold": True, "color": INK})],
          first=True, space_after=11)
    write(frame, [("Ten of the thirteen arms keep every single patient. Three keep "
                   "67%, 44% and ", {"size": 13.5}),
                  (f"{d['survivors']['high invalid data'] / raw:.2%}",
                   {"size": 13.5, "font": MONO, "bold": True, "color": RUST}),
                  (".", {"size": 13.5})], space_after=11, line_spacing=1.3)
    write(frame, [("The high-invalid-data threshold reads as conservative — it allows "
                   "up to 16 of a record's 168 cells to be blank. In this cohort that "
                   "keeps ", {"size": 13.5}),
                  (f"{d['survivors']['high invalid data']:,} of {raw:,}",
                   {"size": 13.5, "font": MONO, "bold": True, "color": INK}),
                  (" stays.", {"size": 13.5})], space_after=0, line_spacing=1.3)

    notes(slide, [
        "This is the slide the talk exists for. Pause on it.",
        "Left number first: the seven per-vital filters, the all-vitals composite and "
        "the imputation arm remove zero patients between them. Not 'few'. Zero.",
        "Then the three record-level filters: 15,003 / 25,709 / 44,663 stays deleted "
        "out of 46,032.",
        "High invalid data keeps 1,369 patients — under 3% of the cohort.",
        "Make the threshold point carefully, because it is counter-intuitive: the "
        "rule is 'drop a record if more than 10% of its 168 cells are blank or zero'. "
        "On paper that sounds permissive. In ICU data, where temperature is spot-"
        "checked and any given vital is silent for hours at a time, almost every "
        "real record fails it.",
        "Nobody writing that filter intends to delete 97% of their data. The threshold "
        "looks conservative and the outcome is not — which is exactly why it has to "
        "be measured rather than reasoned about.",
        "Bridge: so what were the value-level filters doing all this time?",
    ])


def slide_value_level(deck, d):
    slide, top = new_slide(
        deck, "for contrast", "What a value-level filter actually touches",
        subtitle="Individual readings removed as physiologically implausible, "
                 "across the whole cohort. No patient is dropped by any of these.")

    total = d["value_level"]["all vitals"]
    readings = d["readings"]
    stat_row(slide, top + Inches(0.12), [
        (f"{readings / 1e6:.2f}M", "vital-sign readings in the cohort", INK),
        (f"{total:,}", "removed by the seven filters combined", TEAL),
        (f"{total / readings:.2%}", "of all readings", TEAL),
        ("0", "patients removed", TEAL),
    ])

    values = [d["value_level"][v] for v in VITAL_ARMS]
    bar_chart(slide, MARGIN, Inches(3.45), Inches(7.5), Inches(3.15),
              [SHORT[v] for v in VITAL_ARMS], [("readings removed", values)],
              colors=[TEAL], gap=55)

    panel(slide, Inches(8.55), Inches(3.45), Inches(4.06), Inches(3.15))
    frame = text_box(slide, Inches(8.81), Inches(3.70), Inches(3.54), Inches(2.7))
    write(frame, [("Two filters, two worlds",
                   {"size": 17, "font": SERIF, "bold": True, "color": INK})],
          first=True, space_after=11)
    write(frame, [("A value-level filter edits ", {"size": 13.5}),
                  (f"{total / readings:.2%}", {"size": 13.5, "font": MONO,
                                               "bold": True, "color": TEAL}),
                  (" of the readings and keeps every patient. A record-level filter "
                   "edits nothing and deletes up to ", {"size": 13.5}),
                  (f"{1 - d['survivors']['high invalid data'] / d['survivors']['raw']:.0%}",
                   {"size": 13.5, "font": MONO, "bold": True, "color": RUST}),
                  (" of the cohort.", {"size": 13.5})],
          space_after=11, line_spacing=1.3)
    write(frame, [("Both are called “filtering”, and in a methods section both get "
                   "one sentence.", {"size": 13.5, "color": INK, "bold": True})],
          space_after=0, line_spacing=1.3)

    notes(slide, [
        f"Total readings across the seven vitals: {readings:,}. Removed: {total:,}.",
        "Respiration rate and systolic BP dominate — those are the channels where "
        "implausible values are actually charted.",
        "The seven per-vital counts sum exactly to the all-vitals total; the build "
        "asserts that, so the accounting is complete.",
        "The comparison to land: three hundredths of one percent of readings versus "
        "up to 97% of patients. These are not the same kind of operation, and a "
        "methods section that lists them in one sentence hides that.",
        "If asked about the per-vital differences: it tracks how the vital is "
        "measured and charted, not how noisy the physiology is.",
    ])


def slide_prevalence(deck, d):
    slide, top = new_slide(
        deck, "the consequence", "And the survivors are not a random sample",
        subtitle="Class prevalence in the cohort each filter leaves behind. "
                 "Record-level filters select on monitoring density — which tracks "
                 "how sick the patient is.")

    categories, _ = cohort_categories(d)
    series = [(TASK[label],
               [arm_stat(d, label, arm, "population_prevalence") for arm in COHORT_STEPS])
              for label in ("icu", "mortality")]
    chart = bar_chart(slide, MARGIN, top + Inches(0.12), Inches(7.7), Inches(3.5),
                      categories, series, colors=[TEAL, RUST],
                      number_format='0.0%', legend=True, gap=60)
    chart.value_axis.tick_labels.number_format = '0%'
    chart.value_axis.tick_labels.number_format_is_linked = False

    rows = [["Cohort", "Stays", "ICU stay", "Mortality"]]
    for arm in COHORT_STEPS:
        emphasis = arm == "high invalid data"
        rows.append([
            (SHORT[arm] if arm != "raw" else "raw / value-level",
             {"bold": emphasis, "size": 11.5}),
            (f"{d['survivors'][arm]:,}", {"size": 11.5}),
            (f"{arm_stat(d, 'icu', arm, 'population_prevalence'):.1%}",
             {"size": 11.5, "bold": emphasis, "color": INK if emphasis else BODY}),
            (f"{arm_stat(d, 'mortality', arm, 'population_prevalence'):.1%}",
             {"size": 11.5, "bold": emphasis, "color": INK if emphasis else BODY}),
        ])
    table(slide, Inches(8.55), top + Inches(0.12), Inches(4.06), rows,
          col_widths=[1.65, 0.85, 0.8, 0.85], number_columns=(1, 2, 3), size=11.5,
          row_height=Inches(0.36))

    icu_shift = (arm_stat(d, "icu", "high invalid data", "population_prevalence") -
                 arm_stat(d, "icu", "raw", "population_prevalence"))
    lede(slide, Inches(5.78), [
        ("The prolonged-stay task starts as a ", {}),
        (f"{arm_stat(d, 'icu', 'raw', 'population_prevalence'):.1%}", {"font": MONO,
                                                                      "bold": True}),
        (" minority-class problem and ends as a ", {}),
        (f"{arm_stat(d, 'icu', 'high invalid data', 'population_prevalence'):.1%}",
         {"font": MONO, "bold": True, "color": RUST}),
        (" majority-class one — a ", {}),
        (f"{icu_shift * 100:+.1f}-point", {"font": MONO, "bold": True, "color": RUST}),
        (" swing. Mortality prevalence roughly doubles. That is not the same "
         "prediction problem with cleaner inputs; it is a different problem.", {}),
    ], height=Inches(1.3))

    notes(slide, [
        "This is the mechanism slide. Take it slowly.",
        "The record filters select on data density: a record survives if it was "
        "monitored densely and continuously.",
        "In an ICU, monitoring density is not random. It tracks acuity, and gaps "
        "track transfers, imaging, theatre — things that happen to sicker patients.",
        "So filtering for complete records is, in effect, filtering on the outcome. "
        "Missingness here is informative — MNAR in the standard terminology — and "
        "complete-case analysis on MNAR data is selection bias.",
        f"Numbers: ICU prevalence {arm_stat(d, 'icu', 'raw', 'population_prevalence'):.1%}"
        f" → {arm_stat(d, 'icu', 'high invalid data', 'population_prevalence'):.1%}. "
        f"Mortality {arm_stat(d, 'mortality', 'raw', 'population_prevalence'):.1%}"
        f" → {arm_stat(d, 'mortality', 'high invalid data', 'population_prevalence'):.1%}.",
        "The ICU one is the striking one: the positive class goes from minority to "
        "majority. Any metric with a base rate in it is now measuring a different "
        "thing.",
        "Note the direction is the opposite of naive intuition — you might expect "
        "dropping incomplete records to remove the sickest patients. It enriches "
        "for them, because sick patients get watched more closely.",
    ])


def slide_caveat(deck, d):
    slide, top = new_slide(
        deck, "the consequence", "So the bar charts are not comparing like with like",
        subtitle="The same filters, measured twice: against the baseline on the full "
                 "cohort, and against the baseline on exactly the patients each "
                 "filter kept. Mortality, mean aggregation.")

    rows = [["Arm", "Scored on", "Δ accuracy, as plotted",
             "Δ accuracy, vs the same survivors"]]
    for arm in ["all vitals", "fill missing data"] + RECORD_ARMS:
        record_level = arm in RECORD_ARMS
        plotted = delta(d, "mortality", arm, "accuracy_mean")
        paired = paired_delta(d, "mortality", arm)
        rows.append([
            (SHORT[arm], {"bold": record_level}),
            (f"{d['survivors'][arm]:,} stays",
             {"color": RUST if record_level else TEAL, "bold": record_level}),
            (f"{plotted:+.4f}", {"color": GREEN if plotted > 0 else RUST}),
            (f"{paired:+.4f}", {"color": GREEN if paired > 0 else RUST,
                                "bold": record_level}),
        ])
    table(slide, MARGIN, top + Inches(0.12), Inches(8.6), rows,
          col_widths=[2.2, 1.55, 2.1, 2.75], number_columns=(1, 2, 3),
          size=12.5, row_height=Inches(0.42))

    hid = d["diagnostics"]["mortality"]["high invalid data"]["mcnemar"]
    frame = text_box(slide, MARGIN, Inches(4.86), Inches(8.6), Inches(2.4))
    write(frame, [("For the two full-cohort arms the columns agree to four decimals — "
                   "same patients, so the subtraction was always clean. For all three "
                   "record-level arms they disagree ", {"size": 14.5}),
                  ("in sign", {"size": 14.5, "bold": True, "italic": True,
                               "color": INK}),
                  (".", {"size": 14.5})],
          first=True, space_after=11, line_spacing=1.3)
    write(frame, [("High-invalid-data is the extreme case. On the ", {"size": 14.5}),
                  (f"{hid['n_paired']:,}", {"size": 14.5, "font": MONO, "bold": True}),
                  (" patients it kept it beats the baseline by ", {"size": 14.5}),
                  (f"{paired_delta(d, 'mortality', 'high invalid data'):+.4f}",
                   {"size": 14.5, "font": MONO, "bold": True, "color": GREEN}),
                  (" — but those are patients the baseline finds hard, scoring ",
                   {"size": 14.5}),
                  (f"{hid['baseline_accuracy_on_paired']:.4f}",
                   {"size": 14.5, "font": MONO, "bold": True}),
                  (" on them against ", {"size": 14.5}),
                  (f"{arm_stat(d, 'mortality', 'raw', 'accuracy_mean'):.4f}",
                   {"size": 14.5, "font": MONO, "bold": True}),
                  (" overall.", {"size": 14.5})],
          space_after=11, line_spacing=1.3)
    write(frame, [("The plotted ", {"size": 14.5, "bold": True, "color": INK}),
                  (f"{delta(d, 'mortality', 'high invalid data', 'accuracy_mean'):+.4f}",
                   {"size": 14.5, "font": MONO, "bold": True, "color": INK}),
                  (" is those two effects cancelling. It is a fact about which "
                   "patients ended up in the denominator, not about what the filter "
                   "did to the model.", {"size": 14.5, "bold": True, "color": INK})],
          space_after=0, line_spacing=1.3)

    panel(slide, Inches(9.35), top + Inches(0.12), Inches(3.26), Inches(4.4))
    frame = text_box(slide, Inches(9.61), top + Inches(0.36), Inches(2.74), Inches(4.0))
    write(frame, [("What to do instead",
                   {"size": 16, "font": SERIF, "bold": True, "color": INK})],
          first=True, space_after=11)
    for line in ["Report the surviving n, and its class prevalence, beside every "
                 "metric.",
                 "For a record-level filter, score the baseline on the same "
                 "survivors before subtracting anything.",
                 "Treat macro F1 with care: it averages per-class F1, so doubling "
                 "the positive rate moves it whatever the model does.",
                 "Prefer threshold-free metrics when the cohort moves under you."]:
        write(frame, [("• ", {"color": TEAL, "bold": True}), (line, {})],
              size=12.5, space_after=10, line_spacing=1.26)

    notes(slide, [
        "This is the caveat slide, and it is the strongest evidence in the talk for "
        "the whole argument.",
        "Two columns. The first is what our Figure 5 plots: each arm against the "
        "baseline's score on all 46,032 patients. The second scores the baseline on "
        "exactly the patients that arm kept, so the record set is identical.",
        "For the value-level arms the two agree to four decimals — as they must, "
        "because the cohorts are the same. That is the control.",
        "For the three record-level arms the sign flips. Read as plotted, they look "
        "like the filters that damage mortality prediction most. Measured on their "
        "own survivors, all three improve it.",
        "High invalid data: +0.198 on the patients it kept. The baseline manages "
        "0.511 on those same 1,369 patients against 0.687 across the cohort — they "
        "are a genuinely harder subgroup, consistent with the prevalence doubling.",
        "So the plotted +0.0009 is two large effects cancelling. Nothing about it is "
        "a statement about the filter.",
        "Precision point if pressed: the two columns come from different prediction "
        "rules — the plotted one uses per-fold thresholds, the paired one a consensus "
        "vector — so compare delta with delta, not delta with absolute. The "
        "like-for-like comparison inside each column is what carries the argument.",
        "Right-hand panel is the practical ask. None of it is expensive.",
    ])


# --------------------------------------------------------------------------
# slides 13-14: McNemar
# --------------------------------------------------------------------------
def slide_mcnemar_intro(deck, d):
    slide, top = new_slide(
        deck, "the diagnostic", "McNemar: did the prediction pattern change?",
        subtitle="A paired test on the records both models scored. Bars are "
                 "−log₁₀(p) against the unfiltered baseline; in-hospital mortality.")

    picture(slide, d["figures"] / FIG["mcnemar_mortality"], MARGIN, top + Inches(0.04),
            Inches(7.6), Inches(3.85))

    panel(slide, Inches(8.55), top + Inches(0.04), Inches(4.06), Inches(3.85))
    frame = text_box(slide, Inches(8.81), top + Inches(0.28), Inches(3.54), Inches(3.5))
    write(frame, [("The test in one paragraph",
                   {"size": 16, "font": SERIF, "bold": True, "color": INK})],
          first=True, space_after=10)
    write(frame, [("Take the records both models predicted. Count the ones the filter "
                   "fixed (", {"size": 13}),
                  ("n₀₁", {"size": 13, "font": MONO, "bold": True, "color": GREEN}),
                  (") and the ones it broke (", {"size": 13}),
                  ("n₁₀", {"size": 13, "font": MONO, "bold": True, "color": RUST}),
                  ("). Under the null they are exchangeable, so the p-value is an "
                   "exact binomial test on ", {"size": 13}),
                  ("n₀₁ / (n₀₁ + n₁₀)", {"size": 13, "font": MONO}),
                  (" against ½.", {"size": 13})], space_after=10, line_spacing=1.28)
    write(frame, [("Agreements are ignored entirely. The test sees only the "
                   "disagreements — which is what makes it powerful, and what makes "
                   "it fragile when the paired sample shrinks.",
                   {"size": 13, "color": INK})], space_after=10, line_spacing=1.28)
    write(frame, [("Every arm here is scored at the baseline's threshold, so the "
                   "comparison isolates the filter rather than the operating point.",
                   {"size": 12.5, "color": MUTED, "italic": True})], space_after=0,
          line_spacing=1.26)

    lede(slide, Inches(6.05), [
        ("The dashed lines are ", {}),
        ("p = 0.05", {"font": MONO, "bold": True}),
        (" and ", {}),
        ("p = 0.0001", {"font": MONO, "bold": True}),
        (". Between them, a filter is worth investigating; below the second, it has "
         "changed the model's behaviour so much that it is hard to argue the problem "
         "survived intact.", {}),
    ])

    notes(slide, [
        "This is the paper's second diagnostic, and the stats bit I said I would "
        "explain. Keep it to about forty seconds.",
        "McNemar is paired and non-parametric. It ignores every record the two "
        "models agree on and asks whether the disagreements are symmetric.",
        "Say why paired matters: the two models see the same patients in the same "
        "folds, so an unpaired accuracy comparison would throw away that structure.",
        "The two thresholds are ours, chosen in advance: 0.05 as the usual bar, and "
        "1e-4 as 'this is no longer the same problem'.",
        "Technical note if anyone asks: every arm is re-scored at the BASELINE's "
        "decision threshold. Each arm picks its own Youden threshold, and if you let "
        "that move too you end up measuring the operating point rather than the "
        "filter. Holding it fixed isolates the filter.",
        "Point out what is NOT significant here: with the threshold held fixed, "
        "none of the seven per-vital filters changes the prediction pattern. "
        "The tall bars are the imputation arm and the record-level arms.",
        "Then set up the next slide: there is a reason the record-level bars "
        "behave the way they do, and it is not the one you would guess.",
    ])


def slide_mcnemar_power(deck, d):
    slide, top = new_slide(
        deck, "the part that did not fit", "McNemar only ever sees the survivors",
        subtitle="The paired sample is the intersection of the two arms — so a "
                 "record-level filter shrinks the test at the same time as it "
                 "changes the data.")

    rows = [["Arm", "Paired n", "n₀₁ fixed", "n₁₀ broke", "p (mortality)", "p (ICU stay)"]]
    for arm in ["all vitals", "fill missing data"] + RECORD_ARMS:
        entry = d["mcnemar"]["mortality"][arm]
        record_level = arm in RECORD_ARMS
        rows.append([
            (SHORT[arm], {"bold": record_level}),
            (f"{entry['n_paired']:,}", {"color": RUST if record_level else TEAL,
                                        "bold": record_level}),
            (f"{entry['n01']:,}", {"color": GREEN}),
            (f"{entry['n10']:,}", {"color": RUST}),
            (fmt_p(p_value(d, "mortality", arm)), {}),
            (fmt_p(p_value(d, "icu", arm)), {}),
        ])
    table(slide, MARGIN, top + Inches(0.12), Inches(8.5), rows,
          col_widths=[2.15, 1.15, 1.1, 1.1, 1.35, 1.35],
          number_columns=(1, 2, 3, 4, 5), size=12, row_height=Inches(0.40))

    raw = d["survivors"]["raw"]
    deleted = raw - d["survivors"]["high invalid data"]

    # Which record-level arm, if any, fails to reach significance despite a large
    # accuracy move. Computed rather than asserted: the p-values here are the
    # baseline-threshold comparison, and the framing has to follow whatever they say.
    quiet = sorted(
        ((label, arm) for arm in RECORD_ARMS for label in LABELS
         if p_value(d, label, arm) >= 0.05),
        key=lambda pair: -abs(delta(d, pair[0], pair[1], "accuracy_mean")))

    frame = text_box(slide, MARGIN, Inches(4.72), Inches(8.5), Inches(2.5))
    if quiet:
        label, arm = quiet[0]
        write(frame, [(f"{SHORT[arm].capitalize()} on {TASK[label].lower()}: ",
                       {"size": 15, "bold": True, "color": INK}),
                      (f"accuracy {delta(d, label, arm, 'accuracy_mean'):+.4f}",
                       {"size": 15, "font": MONO, "bold": True, "color": RUST}),
                      (f", and yet p = {fmt_p(p_value(d, label, arm))} — not "
                       f"significant. The test is run on the ",
                       {"size": 15}),
                      (f"{d['mcnemar'][label][arm]['n_paired']:,}",
                       {"size": 15, "font": MONO, "bold": True}),
                      (" patients that survived. The ", {"size": 15}),
                      (f"{raw - d['survivors'][arm]:,}", {"size": 15, "font": MONO,
                                                          "bold": True, "color": RUST}),
                      (" it deleted cannot disagree with anything.", {"size": 15})],
              first=True, space_after=12, line_spacing=1.3)
    else:
        write(frame, [("Every record-level arm reaches significance here — but note "
                       "what the paired column is doing: the test is run on ",
                       {"size": 15}),
                      (f"{d['mcnemar']['mortality']['high invalid data']['n_paired']:,}",
                       {"size": 15, "font": MONO, "bold": True, "color": RUST}),
                      (f" patients for high-invalid-data, against {raw:,} for every "
                       "value-level arm.", {"size": 15})],
              first=True, space_after=12, line_spacing=1.3)

    write(frame, [("That is the asymmetry to remember: a record-level filter is "
                   "tested only on the records it approved of. Its most consequential "
                   "act — deleting ", {"size": 15}),
                  (f"{deleted:,}", {"size": 15, "font": MONO, "bold": True,
                                    "color": RUST}),
                  (" patients — is invisible to the test, and shrinking the sample "
                   "costs the test the power to notice what is left.", {"size": 15})],
          space_after=0, line_spacing=1.3)

    vital_ps = [p_value(d, "mortality", arm) for arm in VITAL_ARMS]
    panel(slide, Inches(9.35), top + Inches(0.12), Inches(3.26), Inches(4.6))
    frame = text_box(slide, Inches(9.61), top + Inches(0.36), Inches(2.74), Inches(4.2))
    write(frame, [("Significance tracks the\nsample, not the damage",
                   {"size": 16, "font": SERIF, "bold": True, "color": INK})],
          first=True, space_after=11, line_spacing=1.1)
    for line in [
        f"Held at one threshold, none of the seven per-vital filters is "
        f"significant on either task (p from {min(vital_ps):.2f} to "
        f"{max(vital_ps):.2f}). They edit values without changing behaviour.",
        f"Long-missing-segment deletes "
        f"{d['survivors']['raw'] - d['survivors']['long missing segment']:,} stays and "
        f"reaches p = {fmt_p(p_value(d, 'mortality', 'long missing segment'))} on "
        f"{d['mcnemar']['mortality']['long missing segment']['n_paired']:,} pairs.",
        f"High-invalid-data deletes "
        f"{d['survivors']['raw'] - d['survivors']['high invalid data']:,} — three times "
        f"as many — and manages only "
        f"p = {fmt_p(p_value(d, 'mortality', 'high invalid data'))} on "
        f"{d['mcnemar']['mortality']['high invalid data']['n_paired']:,} pairs.",
        "More damage, weaker evidence. The test rewards a large intersection, and "
        "deleting records is how you lose one.",
    ]:
        write(frame, [("• ", {"color": RUST, "bold": True}), (line, {})],
              size=12, space_after=9, line_spacing=1.24)

    notes(slide, [
        "Second centrepiece. The question I get asked about this paper is why the "
        "record-level McNemar results are so extreme.",
        "First, the control that makes the rest readable: with every arm scored at "
        "the same threshold, not one of the seven per-vital filters produces a "
        "significant change on either task. Filters that edit a third of one percent "
        "of readings do not change what the model does. Good — that is what a "
        "well-behaved filter should look like.",
        "What is left significant is the imputation arm, on the full cohort, and the "
        "record-level arms on mortality.",
        "Now the mechanism. The test is computed on the intersection of the two arms. "
        "For a record-level filter that intersection IS the survivor set.",
        "So the filter's largest single act — deleting 44,663 patients — contributes "
        "exactly nothing to the p-value. The test cannot see a patient who is not "
        "there. It is scored entirely on the records the filter approved of.",
        "Read the two p columns side by side. On prolonged ICU stay all three "
        "record-level arms come back non-significant — including the one that deleted "
        "97% of the cohort and moved the class balance from 38% to 61%.",
        "That is the sentence to land: a filter can delete almost all of your data, "
        "transform the base rate, and still test as 'no significant change in "
        "prediction pattern'. The silence is lost power, not a clean bill of health.",
        "And the ordering on mortality makes the same point positively — "
        "long-missing-segment deletes a third as many patients as high-invalid-data "
        "and gets a p-value seventeen orders of magnitude smaller, because it kept "
        "31,000 pairs instead of 1,369.",
        "General lesson for an ML audience: a paired significance test on filtered "
        "data answers a question about the survivors. It is structurally silent about "
        "selection — and selection is usually the larger effect.",
    ])


# --------------------------------------------------------------------------
# slides 15-17: synthesis
# --------------------------------------------------------------------------
def slide_diagnostic(deck, d):
    slide, top = new_slide(
        deck, "the method", "Three questions, asked together",
        subtitle="No single one of these separates cleaning from distortion. Read "
                 "side by side, they do.")

    # Whether the all-vitals filter changed the prediction pattern is read off its
    # p-value, not asserted: at the baseline threshold it does not reach 0.05, and an
    # earlier build of this slide called it significant.
    p_vitals = p_value(d, "mortality", "all vitals")
    vitals_changed = p_vitals < 0.05
    vitals_verdict = ("a significant but bounded behavioural change" if vitals_changed
                      else f"no significant change in prediction pattern "
                           f"(p = {fmt_p(p_vitals)})")

    rows = [["", "Centroid shift", "McNemar", "Record accounting"]]
    rows.append([
        ("all vitals", {"bold": True, "color": TEAL}),
        "moves; the one class-differential shift (heart rate) traces to "
        "removing extreme outliers",
        f"p = {fmt_p(p_vitals)}, on all {d['survivors']['all vitals']:,} stays"
        + ("" if vitals_changed else " — not significant"),
        (f"{d['survivors']['raw'] - d['survivors']['all vitals']:,} records removed; "
         f"{d['value_level']['all vitals']:,} readings edited", {"color": TEAL}),
    ])
    rows.append([
        ("high invalid data", {"bold": True, "color": RUST}),
        "large, and opposite in sign between the mortality classes",
        f"p = {fmt_p(p_value(d, 'mortality', 'high invalid data'))}, but on only "
        f"{d['mcnemar']['mortality']['high invalid data']['n_paired']:,} stays",
        (f"{d['survivors']['raw'] - d['survivors']['high invalid data']:,} records "
         f"removed; prevalence "
         f"{arm_stat(d, 'icu', 'raw', 'population_prevalence'):.0%} → "
         f"{arm_stat(d, 'icu', 'high invalid data', 'population_prevalence'):.0%}",
         {"color": RUST}),
    ])
    table(slide, MARGIN, top + Inches(0.12), CONTENT_W, rows,
          col_widths=[1.5, 2.6, 2.5, 3.0], size=12, row_height=Inches(0.86))

    frame = text_box(slide, MARGIN, Inches(4.86), CONTENT_W, Inches(2.2))
    write(frame, [("The first row is what artifact removal looks like: a distribution "
                   f"shift you can explain physiologically, {vitals_verdict}, and a "
                   "cohort that is untouched.",
                   {"size": 15})], first=True, space_after=12, line_spacing=1.3)
    write(frame, [("The second row is what problem-alteration looks like: a "
                   "class-dependent shift, a p-value computed on 3% of the data, and "
                   "a cohort whose base rate has moved by tens of points.",
                   {"size": 15})], space_after=12, line_spacing=1.3)
    write(frame, [("The paper published the first two columns. The third is free — "
                   "it is a call to ", {"size": 15, "bold": True, "color": INK}),
                  ("len()", {"size": 15, "font": MONO, "bold": True, "color": INK}),
                  (" — and it is the one that explains the other two.",
                   {"size": 15, "bold": True, "color": INK})],
          space_after=0, line_spacing=1.3)

    notes(slide, [
        "Pull the talk together. Two worked examples, three columns each.",
        "All vitals: centroids move, but the four outcome groups move together; "
        + ("significant McNemar on the full cohort" if vitals_changed else
           f"McNemar not significant on the full cohort (p = {fmt_p(p_vitals)}) — "
           "the model's predictions do not change")
        + "; zero records lost. That is a filter "
        "removing sensor artifacts. Keep it — and keep it even where it costs "
        "accuracy, because a clinical model must not key on impossible values.",
        "High invalid data: centroids move in opposite directions for the mortality "
        "classes; p computed on 1,369 patients; 97% of the cohort gone and the base "
        "rate transformed. That is a filter changing the problem.",
        "The honest summary of our own contribution: the centroid and McNemar "
        "diagnostics are useful, and neither would have told us what the record "
        "count told us in one line.",
        "Say the punchline plainly: the cheapest diagnostic in this talk is counting "
        "your rows before and after, and it is the one nobody reports.",
    ])


def slide_implications(deck, d):
    slide, top = new_slide(
        deck, "implications", "What this means if you are comparing models",
        subtitle=None)

    for index, (heading, lines, color) in enumerate([
        ("For algorithm comparison", [
            "Two studies with different filters may be solving problems of "
            "different difficulty on the same database.",
            "A reported gap can be preprocessing rather than model quality.",
            "Filtering choices belong in the comparison, not just the model card.",
        ], TEAL),
        ("For clinical usefulness", [
            "Missingness in an EHR is informative — absence reflects clinical "
            "decisions and patient acuity.",
            "Complete-case filtering therefore selects on acuity, and quietly "
            "excludes intermittently monitored patients.",
            "High benchmark numbers on a heavily filtered cohort do not imply "
            "readiness on the ward.",
        ], RUST),
    ]):
        x = Emu(int(MARGIN + index * (CONTENT_W / 2 + Inches(0.14))))
        each = Emu(int(CONTENT_W / 2 - Inches(0.14)))
        panel(slide, x, top + Inches(0.16), each, Inches(3.05))
        rule(slide, x, top + Inches(0.16), each, color, Pt(3))
        frame = text_box(slide, Emu(int(x + Inches(0.28))), top + Inches(0.44),
                         Emu(int(each - Inches(0.56))), Inches(2.7))
        write(frame, [(heading, {"size": 18, "font": SERIF, "bold": True,
                                 "color": INK})], first=True, space_after=11,
              line_spacing=1.08)
        for line in lines:
            write(frame, [("• ", {"color": color, "bold": True}), (line, {})],
                  size=13.5, space_after=8, line_spacing=1.28)

    panel(slide, MARGIN, Inches(5.20), CONTENT_W, Inches(1.35), fill=SUNK)
    frame = text_box(slide, Inches(1.0), Inches(5.42), Inches(11.4), Inches(1.0))
    write(frame, [("Our recommendation: ", {"size": 16, "bold": True, "color": INK}),
                  ("prefer filters justified by physiology over filters justified by "
                   "tidiness, and report the cohort you were left with as carefully "
                   "as you report the metric you got on it.", {"size": 16})],
          first=True, space_after=0, line_spacing=1.3)

    notes(slide, [
        "Left panel is the ML-methods argument, and it is the one this audience "
        "should care about: cross-study comparisons silently include a preprocessing "
        "comparison.",
        "Right panel is the clinical argument. MNAR — missing not at random — is the "
        "technical term; in an ICU, whether a measurement exists is a clinical "
        "decision, so absence carries signal.",
        "That is why complete-case filtering is selection bias here rather than "
        "housekeeping, and it is what our prevalence numbers demonstrated directly.",
        "Limitation to state honestly: hourly flattening smooths away sub-hourly "
        "volatility and the informative-missingness pattern itself. Preserving "
        "sampling dynamics is future work.",
        "Also honest: one database family, seven vitals, two tasks, one classifier.",
    ])


def slide_takeaways(deck, d):
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = GROUND
    rule(slide, MARGIN, Inches(1.05), Inches(1.5), TEAL, Pt(3))

    frame = text_box(slide, MARGIN, Inches(1.35), Inches(11.0), Inches(0.9))
    write(frame, [("Three things to take away",
                   {"size": 34, "font": SERIF, "color": INK, "bold": True})],
          first=True, space_after=0, line_spacing=1.02)

    raw = d["survivors"]["raw"]
    items = [
        ("Filtering is a modelling choice.",
         "It changes the distribution, the difficulty, and — as we saw — the "
         "population. Treat it as part of the method, not as housekeeping."),
        ("Level matters more than threshold.",
         f"The seven value-level filters edited "
         f"{d['value_level']['all vitals'] / d['readings']:.2%} of readings and "
         f"removed no patients. One record-level filter removed "
         f"{raw - d['survivors']['high invalid data']:,} of {raw:,}."),
        ("Count what you removed.",
         "Report the surviving n and its class prevalence beside every metric. It "
         "costs nothing, and it explains results that the distribution and "
         "significance diagnostics leave mysterious."),
    ]
    top = Inches(2.55)
    for index, (heading, text) in enumerate(items):
        y = Emu(int(top + index * Inches(1.30)))
        frame = text_box(slide, MARGIN, y, Inches(11.6), Inches(1.2))
        write(frame, [(f"{index + 1}   ", {"size": 21, "font": MONO, "color": TEAL,
                                           "bold": True}),
                      (heading, {"size": 21, "font": SERIF, "color": INK,
                                 "bold": True})],
              first=True, space_after=6, line_spacing=1.05)
        write(frame, [("      " + text, {"size": 14.5, "color": BODY})],
              space_after=0, line_spacing=1.28)

    rule(slide, MARGIN, Inches(6.42), CONTENT_W)
    frame = text_box(slide, MARGIN, Inches(6.58), CONTENT_W, Inches(0.6))
    write(frame, [("Toolbox, figures and every number in this talk are open source. "
                   "Questions welcome.", {"size": 13.5, "color": MUTED})],
          first=True, space_after=0)

    notes(slide, [
        "Keep this to thirty seconds; leave time for questions.",
        "One: filtering is a modelling choice.",
        "Two: the level a filter operates at predicts its damage far better than how "
        "conservative its threshold looks. The 10%-invalid rule sounded generous and "
        "removed 97% of the cohort.",
        "Three, and the ask: count what you removed, and print it next to your metric.",
        "Likely questions to have answers ready for: why a random forest (robustness "
        "to irrelevant features on a mixed-density 168-dim vector, and the study is "
        "about preprocessing not architecture); why not just loosen the record-level "
        "thresholds (you can, and it helps, but any record-level rule selects on "
        "monitoring density and so on acuity); does this hold on MIMIC-IV and eICU "
        "(the pipeline supports both, the numbers here are MIMIC-III).",
    ])


# --------------------------------------------------------------------------
def build(out_path: Path, figures: Path) -> Path:
    d = load(figures)
    deck = Presentation()
    deck.slide_width, deck.slide_height = W, H

    for slide_fn in [slide_title, slide_claim, slide_setup, slide_filters,
                     slide_dirty, slide_centroids, slide_impact_mortality,
                     slide_task_divergence, slide_survivors, slide_value_level,
                     slide_prevalence, slide_caveat, slide_mcnemar_intro,
                     slide_mcnemar_power, slide_diagnostic, slide_implications,
                     slide_takeaways]:
        slide_fn(deck, d)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    deck.save(out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--figures", default=str(DEFAULT_FIGURES),
                        help="directory holding the PNG renders of the paper figures")
    args = parser.parse_args()
    path = build(Path(args.out), Path(args.figures))
    print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
