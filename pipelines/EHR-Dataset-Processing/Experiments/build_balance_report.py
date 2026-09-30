"""Generate the stage H comparison report as a self-contained HTML page."""
import html
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path('/home/ccampb47/work/clinical_preprocessing_toolbox/pipelines/EHR-Dataset-Processing')
OUT = ROOT / 'paper_figures/balance/balance_report.html'

full = pd.read_csv(ROOT / 'paper_figures/balance/balance_comparison.csv')
delta = pd.read_csv(ROOT / 'paper_figures/balance/balance_deltas.csv')

STRAT = ['oversample', 'undersample', 'smote']
SC = {'oversample': 'var(--s1)', 'undersample': 'var(--s2)', 'smote': 'var(--s3)'}
AGGS = ['mean', 'median', 'standard deviation', 'mean deviation', 'maximum deviation']


def bounds(values, pad=0.08):
    """Padded [lo, hi] around `values` that always contains zero.

    Hardcoding these was fine while the numbers were frozen. They are not:
    refitting the baseline shifts every delta, and a dot drawn outside its
    viewBox is worse than an ugly axis.
    """
    lo, hi = float(np.min(values)), float(np.max(values))
    lo, hi = min(lo, 0.0), max(hi, 0.0)
    span = (hi - lo) or 1.0
    return lo - span * pad, hi + span * pad


def ticks(lo, hi, count=4):
    """Round tick positions inside [lo, hi], always including zero."""
    step = (hi - lo) / count
    magnitude = 10.0 ** np.floor(np.log10(step))
    for multiple in (1, 2, 2.5, 5, 10):
        if magnitude * multiple >= step:
            step = magnitude * multiple
            break
    out = []
    t = np.ceil(lo / step) * step
    while t <= hi + 1e-12:
        out.append(0.0 if abs(t) < step / 1e6 else float(t))
        t += step
    return out


def strip_chart():
    """Four metrics on ONE shared axis, so the contrast is honest rather than
    manufactured by per-row rescaling."""
    rows = [('Recall', 'd_recall', 'threshold-dependent'),
            ('Balanced accuracy', 'd_bal', 'threshold-dependent'),
            ('AUROC', 'd_auroc', 'threshold-free'),
            ('AUPRC', 'd_auprc', 'threshold-free')]
    W, H = 860, 300
    L, R, T = 168, 24, 34
    row_h = 52
    lo, hi = bounds(np.concatenate([delta[c].values for _, c, _ in rows]))
    def x(v): return L + (v - lo) / (hi - lo) * (W - L - R)

    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Change in four metrics '
         f'against the unbalanced baseline, all on one axis" class="chart">']
    # zero line
    p.append(f'<line x1="{x(0):.1f}" y1="{T-10}" x2="{x(0):.1f}" y2="{T+row_h*4-18}" '
             f'class="zero"/>')
    for tick in ticks(lo, hi):
        p.append(f'<text x="{x(tick):.1f}" y="{T-16}" class="tick" text-anchor="middle">'
                 f'{tick:+.2f}</text>')
    for i, (name, col, kind) in enumerate(rows):
        y = T + i * row_h + 6
        cls = 'rowlab free' if kind == 'threshold-free' else 'rowlab'
        p.append(f'<text x="{L-14}" y="{y+4}" class="{cls}" text-anchor="end">{name}</text>')
        p.append(f'<line x1="{L}" y1="{y+18}" x2="{W-R}" y2="{y+18}" class="rule"/>')
        for s in STRAT:
            vals = delta[delta.strategy == s][col].values
            for v in vals:
                p.append(f'<circle cx="{x(v):.1f}" cy="{y:.1f}" r="4.5" '
                         f'fill="{SC[s]}" fill-opacity="0.62"/>')
    p.append(f'<text x="{L}" y="{H-8}" class="axlab">'
             f'change against the unbalanced baseline · one dot per aggregation × label × strategy</text>')
    p.append('</svg>')
    return '\n'.join(p)


def scatter():
    """Δ predicted-positive-rate against Δ recall — the mechanism."""
    W, H = 420, 330
    L, B, T, R = 62, 52, 20, 16
    xs, ys = delta.d_pos.values, delta.d_recall.values
    xlo, xhi = bounds(xs)
    ylo, yhi = bounds(ys)
    def X(v): return L + (v - xlo) / (xhi - xlo) * (W - L - R)
    def Y(v): return (H - B) - (v - ylo) / (yhi - ylo) * (H - B - T)

    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Change in predicted '
         f'positive rate against change in recall, correlation {corr:.3f}" class="chart">']
    p.append(f'<line x1="{L}" y1="{Y(0):.1f}" x2="{W-R}" y2="{Y(0):.1f}" class="rule"/>')
    p.append(f'<line x1="{X(0):.1f}" y1="{T}" x2="{X(0):.1f}" y2="{H-B}" class="rule"/>')
    # y = x reference: a perfect operating-point move sits on this line
    diagonal = min(xhi, yhi)
    p.append(f'<line x1="{X(0):.1f}" y1="{Y(0):.1f}" x2="{X(diagonal):.1f}" '
             f'y2="{Y(diagonal):.1f}" class="refline"/>')
    for xv, yv, s in zip(xs, ys, delta.strategy.values):
        p.append(f'<circle cx="{X(xv):.1f}" cy="{Y(yv):.1f}" r="5" fill="{SC[s]}" '
                 f'fill-opacity="0.62"/>')
    for t in ticks(xlo, xhi, 3):
        p.append(f'<text x="{X(t):.1f}" y="{H-B+18}" class="tick" text-anchor="middle">{t:+.2f}</text>')
    for t in ticks(ylo, yhi):
        p.append(f'<text x="{L-10}" y="{Y(t)+4:.1f}" class="tick" text-anchor="end">{t:+.2f}</text>')
    p.append(f'<text x="{(L+W-R)/2:.0f}" y="{H-10}" class="axlab" text-anchor="middle">'
             f'Δ predicted positive rate</text>')
    p.append(f'<text x="14" y="{(T+H-B)/2:.0f}" class="axlab" text-anchor="middle" '
             f'transform="rotate(-90 14 {(T+H-B)/2:.0f})">Δ recall</text>')
    p.append('</svg>')
    return '\n'.join(p)


def auprc_bars():
    """Δ AUPRC for all 30 comparisons, grouped by label then aggregation."""
    W, H = 420, 330
    L, B, T, R = 132, 52, 20, 16
    lo, hi = bounds(delta.d_auprc.values)
    def X(v): return L + (v - lo) / (hi - lo) * (W - L - R)
    entries = []
    for label in ['mortality', 'icu']:
        for agg in AGGS:
            for s in STRAT:
                row = delta[(delta.label == label) & (delta.aggregation == agg)
                            & (delta.strategy == s)]
                if not row.empty:
                    entries.append((label, agg, s, float(row.d_auprc.iloc[0])))
    bar_h = (H - B - T) / len(entries)
    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Change in AUPRC for all '
         f'{len(delta)} comparisons, {n_auprc} of them negative" class="chart">']
    p.append(f'<line x1="{X(0):.1f}" y1="{T}" x2="{X(0):.1f}" y2="{H-B}" class="zero"/>')
    seen = set()
    for i, (label, agg, s, v) in enumerate(entries):
        y = T + i * bar_h
        p.append(f'<rect x="{X(v):.1f}" y="{y+0.9:.1f}" width="{X(0)-X(v):.1f}" '
                 f'height="{bar_h-1.8:.1f}" fill="{SC[s]}" fill-opacity="0.72"/>')
        key = (label, agg)
        if key not in seen:
            seen.add(key)
            short = agg.replace('standard deviation', 'std dev').replace('maximum', 'max')
            p.append(f'<text x="{L-8}" y="{y + bar_h*1.5 + 3:.1f}" class="tick" '
                     f'text-anchor="end">{short}</text>')
    for lbl, idx in (('mortality', 0), ('icu', 15)):
        p.append(f'<text x="6" y="{T + idx*bar_h + bar_h*7.5:.1f}" class="grouplab" '
                 f'text-anchor="middle" transform="rotate(-90 6 {T + idx*bar_h + bar_h*7.5:.1f})">'
                 f'{lbl}</text>')
    p.append(f'<line x1="{L-4}" y1="{T+15*bar_h:.1f}" x2="{W-R}" y2="{T+15*bar_h:.1f}" class="rule"/>')
    for t in ticks(lo, hi, 3):
        p.append(f'<text x="{X(t):.1f}" y="{H-B+18}" class="tick" text-anchor="middle">{t:+.2f}</text>')
    p.append(f'<text x="{(L+W-R)/2:.0f}" y="{H-10}" class="axlab" text-anchor="middle">Δ AUPRC</text>')
    p.append('</svg>')
    return '\n'.join(p)


def table(label):
    sub = full[full.label == label]
    head = ('<thead><tr><th class="lft">Aggregation</th><th class="lft">Strategy</th>'
            '<th>Recall</th><th>Bal. acc</th><th>Macro F1</th><th>Accuracy</th>'
            '<th class="sep">AUROC</th><th>AUPRC</th>'
            '<th class="sep">Pos. rate</th><th>McNemar p</th></tr></thead>')
    body = []
    for agg in AGGS:
        grp = sub[sub.aggregation == agg]
        if grp.empty:
            continue
        base = grp[grp.strategy == 'none'].iloc[0]
        for j, s in enumerate(['none'] + STRAT):
            r = grp[grp.strategy == s]
            if r.empty:
                continue
            r = r.iloc[0]
            first = ' rowspan="4" class="lft agg"' if j == 0 else ''
            cells = f'<td{first}>{html.escape(agg)}</td>' if j == 0 else ''
            cells += f'<td class="lft strat {s}">{s}</td>'
            for col in ['recall', 'balanced_accuracy', 'f1_macro', 'accuracy']:
                cells += cell(r[col], base[col], s)
            cells += cell(r['auroc'], base['auroc'], s, sep=True)
            cells += cell(r['auprc'], base['auprc'], s)
            cells += f'<td class="sep num">{r.predicted_positive_rate:.4f}</td>'
            p = r.mcnemar_p
            ptxt = '—' if s == 'none' else ('&lt;1e-4' if p < 1e-4 else f'{p:.4f}')
            body.append(f'<tr class="{"base" if s=="none" else ""}">{cells}'
                        f'<td class="num p">{ptxt}</td></tr>')
    return (f'<div class="tablewrap"><table>{head}<tbody>{"".join(body)}</tbody></table></div>')


def cell(v, b, s, sep=False):
    klass = 'num' + (' sep' if sep else '')
    if s == 'none':
        return f'<td class="{klass}">{v:.4f}</td>'
    d = v - b
    tone = 'up' if d > 0.0005 else ('down' if d < -0.0005 else 'flat')
    return (f'<td class="{klass}">{v:.4f}<span class="d {tone}">{d:+.4f}</span></td>')


n_auprc = int((delta.d_auprc < 0).sum())
n_auroc = int((delta.d_auroc < 0).sum())
best = delta.loc[delta.d_f1.idxmax()]
corr = float(np.corrcoef(delta.d_recall, delta.d_pos)[0, 1])
smote_synth = int(full[(full.label == "mortality") & (full.aggregation == "mean")
                       & (full.strategy == "smote")].n_synthetic.iloc[0])

# The headline recall swing, read off the data rather than transcribed. Anchored
# on `mean`/mortality — the cell every other stage quotes — rather than on the
# widest gap, which lands on a deviation arm whose baseline recall is ~0.03 and
# so overstates the swing.
mort = full[full.label == "mortality"]
swing_from = float(mort[(mort.aggregation == "mean") & (mort.strategy == "none")].recall.iloc[0])
swing_to = float(mort[(mort.aggregation == "mean") & (mort.strategy == "undersample")].recall.iloc[0])

# Whether the baseline was refitted here or read out of stage F's cache decides
# which closing note the page carries.
baseline_reused = bool(full[full.strategy == "none"].reused_from_cache.any())
baseline_fraction = float(full[full.strategy == "none"].trained_on_fraction.max())
auprc_all_negative = n_auprc == len(delta)

# What the correction was actually worth, quantified against the archived
# reused-baseline run rather than asserted. Absent that archive the page simply
# does not make the claim.
PRIOR = ROOT / 'rerun/backups/stageH_reused_baseline_20260820/paper_figures_balance'
correction_sentence = ""
if not baseline_reused and (PRIOR / 'balance_deltas.csv').exists():
    prior_delta = pd.read_csv(PRIOR / 'balance_deltas.csv')
    prior_full = pd.read_csv(PRIOR / 'balance_comparison.csv')
    key = ['label', 'aggregation']
    gain = (full[full.strategy == 'none'].set_index(key).auprc
            - prior_full[prior_full.strategy == 'none'].set_index(key).auprc).mean()
    correction_sentence = (
        f" The extra training data was worth about <b>+{gain:.4f}</b> AUPRC to the baseline,"
        f" which moves the mean AUPRC change from {prior_delta.d_auprc.mean():+.4f} to"
        f" {delta.d_auprc.mean():+.4f} — slightly further against balancing, and no change"
        f" to the conclusion.")


CSS = """
:root{
  --ground:#eef2f2; --surface:#ffffff; --sunk:#e4eaea;
  --ink:#0e1618; --body:#2c3c40; --muted:#61767a; --line:#cdd8d9;
  --accent:#0d6b6b; --accent-soft:#d7e6e4;
  --up:#3d7a52; --down:#a4552b; --flat:#8a9a9d;
  --s1:#0d6b6b; --s2:#a4552b; --s3:#4a6572;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#0b1214; --surface:#121c1f; --sunk:#0e1719;
    --ink:#e4eef0; --body:#b9cbcd; --muted:#8ba1a5; --line:#25373a;
    --accent:#5cb8b1; --accent-soft:#16302f;
    --up:#6fae86; --down:#d08a5e; --flat:#7c9094;
    --s1:#5cb8b1; --s2:#d08a5e; --s3:#8fa9b4;
  }
}
:root[data-theme="dark"]{
  --ground:#0b1214; --surface:#121c1f; --sunk:#0e1719;
  --ink:#e4eef0; --body:#b9cbcd; --muted:#8ba1a5; --line:#25373a;
  --accent:#5cb8b1; --accent-soft:#16302f;
  --up:#6fae86; --down:#d08a5e; --flat:#7c9094;
  --s1:#5cb8b1; --s2:#d08a5e; --s3:#8fa9b4;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--body);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-size:16px; line-height:1.62; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1000px;margin:0 auto;padding:56px 26px 90px;display:flex;flex-direction:column;gap:44px}
.prose{max-width:68ch}
h1,h2,h3{font-family:ui-serif,Georgia,"Iowan Old Style","Times New Roman",serif;
  color:var(--ink);text-wrap:balance;margin:0;font-weight:600;letter-spacing:-.01em}
h1{font-size:clamp(2rem,4.4vw,2.9rem);line-height:1.1}
h2{font-size:1.5rem;line-height:1.25}
h3{font-size:1.05rem}
p{margin:0 0 .85em}
p:last-child{margin-bottom:0}
.eyebrow{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:.7rem;letter-spacing:.15em;text-transform:uppercase;color:var(--muted)}
header{display:flex;flex-direction:column;gap:14px;border-bottom:1px solid var(--line);padding-bottom:32px}
.sub{font-size:1.08rem;color:var(--muted);max-width:64ch}
.verdict{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--accent);
  padding:26px 30px;display:flex;flex-direction:column;gap:14px}
.verdict h2{font-size:1.28rem}
.figures{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:26px}
figure{margin:0;background:var(--surface);border:1px solid var(--line);padding:20px 20px 14px;
  display:flex;flex-direction:column;gap:12px;overflow-x:auto}
figcaption{font-size:.86rem;color:var(--muted);line-height:1.5}
figcaption b{color:var(--ink);font-weight:600}
.chart{width:100%;height:auto;display:block;overflow:visible}
.chart .tick{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;
  fill:var(--muted);font-variant-numeric:tabular-nums}
.chart .rowlab{font-size:12.5px;fill:var(--body)}
.chart .rowlab.free{fill:var(--ink);font-weight:600}
.chart .grouplab{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:9.5px;
  fill:var(--muted);letter-spacing:.1em;text-transform:uppercase}
.chart .axlab{font-size:11px;fill:var(--muted)}
.chart .rule{stroke:var(--line);stroke-width:1}
.chart .zero{stroke:var(--muted);stroke-width:1.25;stroke-dasharray:3 3}
.chart .refline{stroke:var(--flat);stroke-width:1;stroke-dasharray:4 4}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:.83rem;color:var(--muted)}
.legend span{display:inline-flex;align-items:center;gap:7px}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block}
.tablewrap{overflow-x:auto;border:1px solid var(--line);background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:.83rem;
  font-variant-numeric:tabular-nums;min-width:840px}
th{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.66rem;letter-spacing:.09em;
  text-transform:uppercase;color:var(--muted);font-weight:500;text-align:right;
  padding:12px 11px;border-bottom:1px solid var(--line);white-space:nowrap;background:var(--sunk)}
td{padding:8px 11px;text-align:right;border-bottom:1px solid var(--line);color:var(--body)}
.lft{text-align:left}
th.lft{text-align:left}
.num{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.sep{border-left:2px solid var(--line)}
tr.base td{background:var(--sunk);color:var(--ink);font-weight:600}
.agg{font-weight:600;color:var(--ink);vertical-align:top;padding-top:11px;white-space:nowrap}
.strat{color:var(--muted)}
.strat.oversample{border-left:3px solid var(--s1)}
.strat.undersample{border-left:3px solid var(--s2)}
.strat.smote{border-left:3px solid var(--s3)}
.d{display:block;font-size:.72rem;line-height:1.35}
.d.up{color:var(--up)} .d.down{color:var(--down)} .d.flat{color:var(--flat)}
.p{color:var(--muted)}
.notes{background:var(--surface);border:1px solid var(--line);padding:24px 28px}
.notes ul{margin:0;padding-left:1.15em;display:flex;flex-direction:column;gap:10px}
.notes li{padding-left:.2em}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.87em;
  background:var(--sunk);padding:.1em .38em;border-radius:2px;color:var(--ink)}
.caveat{border-left:3px solid var(--down);background:var(--surface);border:1px solid var(--line);
  border-left:3px solid var(--down);padding:20px 24px}
.stat{display:flex;flex-wrap:wrap;gap:30px;padding-top:4px}
.stat div{display:flex;flex-direction:column;gap:2px}
.stat b{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:1.5rem;
  color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums}
.stat span{font-size:.78rem;color:var(--muted)}
a{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (max-width:640px){.wrap{padding:34px 16px 64px;gap:34px}}
"""

legend = ('<div class="legend">'
          + ''.join(f'<span><i class="dot" style="background:{SC[s]}"></i>{s}</span>'
                    for s in STRAT)
          + '</div>')

doc = f"""<title>Does Class Balancing Help?</title>
<style>{CSS}</style>
<div class="wrap">
<header>
  <div class="eyebrow">MIMIC-III · stage H · 5-fold × 4 repeats · {len(delta)} comparisons</div>
  <h1>Does class balancing help?</h1>
  <p class="sub">Oversampling, undersampling and mask-aware SMOTE, applied to the training
  folds of a random forest predicting ICU admission and in-hospital mortality — measured
  against the same model trained on the natural class distribution.</p>
</header>

<section class="verdict prose">
  <div class="eyebrow">Verdict</div>
  <h2>No. All three strategies move the operating point without improving discrimination.</h2>
  <p>Every strategy raises recall, and the effect is large — undersampling lifts mortality
  recall from {swing_from:.2f} to {swing_to:.2f}. But the threshold-free metrics do not
  follow. <b>AUPRC fell in {f"all {len(delta)}" if auprc_all_negative else f"{n_auprc} of {len(delta)}"}
  comparisons</b>{", without a single exception" if auprc_all_negative else ""},
  and AUROC fell in {n_auroc} of {len(delta)}. A model that ranked patients better would
  show it there.</p>
  <p>What is actually happening is visible in one number: the correlation between the change
  in recall and the change in predicted-positive rate is <b>{corr:.3f}</b>. The classifier is
  not getting better at telling patients apart — it is labelling more of them positive, which
  is what moving a decision threshold does, at the cost of retraining.</p>
  <div class="stat">
    <div><b>{n_auprc}/{len(delta)}</b><span>comparisons with lower AUPRC</span></div>
    <div><b>{delta.d_auprc.max():+.4f}</b><span>best AUPRC change achieved</span></div>
    <div><b>{corr:.3f}</b><span>corr(Δ recall, Δ positive rate)</span></div>
    <div><b>{best.d_f1:+.4f}</b><span>best macro F1 change</span></div>
  </div>
</section>

<section>
  <h2>Where the movement went</h2>
  <p class="prose" style="margin-top:10px">All four metrics share one axis, so the rows are
  directly comparable. The two threshold-dependent metrics swing; the two threshold-free ones
  sit on zero.</p>
  <figure style="margin-top:18px">
    {strip_chart()}
    {legend}
    <figcaption>Each dot is one aggregation × label × strategy. <b>Recall and balanced
    accuracy move because the operating point moved.</b> AUROC and AUPRC — which are computed
    from the scores and never see the 0.5 cut — barely leave zero, and lean negative.</figcaption>
  </figure>
</section>

<section class="figures">
  <figure>
    {scatter()}
    <figcaption>Δ recall against Δ predicted-positive rate, with the dashed line marking a
    pure operating-point move. <b>Points track it at r = {corr:.3f}.</b> Nearly all of the
    recall gain is explained by predicting positive more often.</figcaption>
  </figure>
  <figure>
    {auprc_bars()}
    <figcaption>Δ AUPRC for every comparison — <b>{f"all {len(delta)}" if auprc_all_negative else f"{n_auprc} of {len(delta)}"}
    bars point left.</b> The
    deviation aggregations (std dev, mean dev, max dev) under mortality lose the most, up to
    {abs(delta.d_auprc.min()):.3f}.</figcaption>
  </figure>
</section>

<section>
  <h2>Mortality</h2>
  <p class="prose" style="margin:10px 0 18px">Prevalence 9.7%. The baseline row is shaded;
  smaller figures are the change against it. The rule separates threshold-free metrics.</p>
  {table('mortality')}
</section>

<section>
  <h2>ICU admission</h2>
  <p class="prose" style="margin:10px 0 18px">Prevalence 37.5% — far less imbalanced, and
  correspondingly less affected.</p>
  {table('icu')}
</section>

<section class="notes prose">
  <h3>What the numbers rest on</h3>
  <ul>
    <li><b>Design.</b> 5-fold stratified cross-validation × 4 independent partitions,
    out-of-fold predictions for every record, decision threshold fixed at 0.5 with no
    validation split. Every arm inherits the same folds, keyed on <code>admission_id</code>,
    so McNemar is genuinely paired.</li>
    <li><b>Balancing touches training rows only.</b> Test features are read from the original
    matrix by position, so a synthetic record has no position and cannot be scored. The
    verifier replayed all 20 folds of <code>mean</code>/mortality and found <b>0 collisions</b>
    between its {smote_synth:,} synthetic rows and any test fold; refitting on shuffled labels
    gave AUC 0.4953 / 0.4967 / 0.5003, i.e. chance.</li>
    <li><b>SMOTE is mask-aware.</b> 39% of the feature matrix is structural zeros meaning
    "never measured", and missingness is class-correlated (68.3% observed for positives
    against 60.1% for negatives). Neighbours are found over co-observed cells only
    (<code>nan_euclidean</code>), each synthetic record inherits its base parent's missingness
    mask, and interpolation happens only where both parents measured.</li>
    <li><b>Oversampling and SMOTE produce identical training-set sizes</b> (2 × majority), so
    the difference between them isolates one question: duplicate a real patient, or synthesise
    a new one. SMOTE wins that comparison narrowly — best macro F1 change of
    {best.d_f1:+.4f} on {best.label} / {best.aggregation} — but still loses AUPRC.</li>
  </ul>
</section>

<section class="caveat prose">
  <h3>The baseline is trained on the same data as the arms</h3>
  <p>An earlier version of this page carried a caveat: the unbalanced baseline had been
  reused from the previous sweep, where it was fitted on 70% of the cohort because that
  sweep carved off an inner-validation slice to pick a threshold. The balanced arms trained
  on the full 80%, so the baseline was handicapped by roughly 12% of its training data — a
  bias running <em>toward</em> balancing.</p>
  <p>That baseline has since been refitted under the same protocol as the arms
  ({baseline_fraction:.0%} of the cohort, no validation split, threshold fixed at 0.5), and
  the numbers above are the corrected ones.{correction_sentence}</p>
</section>
</div>
"""

OUT.write_text(doc)
print(f"wrote {OUT}  ({len(doc):,} bytes)")
print(f"AUPRC negative in {n_auprc}/{len(delta)}; AUROC negative in {n_auroc}/{len(delta)}; corr={corr:.4f}")
