"""Fake seaborn, just enough of it to get the notebooks to run on nibi.

Real seaborn isn't in the CVMFS Python on Compute Canada and installing it into
.venv_stats turned into a dependency fight I didn't want to have for four
functions. This file sits at the repo root, so `import seaborn` inside a notebook
picks it up ahead of the real package.

Only `set_style`, `set_context`, `barplot`, `heatmap` and `kdeplot` exist, and
only the argument shapes the notebooks actually use. Everything else raises
AttributeError, so if a notebook grows a new seaborn call the fix is to add it
here. Output won't look identical to real seaborn — no confidence intervals on
barplot, kdeplot is a stepped histogram rather than a kernel estimate — which is
fine for reading a trend and not fine for anything going in a paper.

Deleting this file on a machine with real seaborn installed is harmless and gets
you better-looking plots.
"""

import numpy as np
import matplotlib.pyplot as plt


def set_style(_style):
    return None


def set_context(_context, font_scale=1.0):
    plt.rcParams.update({"font.size": 10 * float(font_scale)})
    return None


def barplot(x=None, y=None, data=None, hue=None, ax=None, **_kwargs):
    """Both seaborn call styles: barplot(data=df, x="col", y="col") and
    barplot(x=array, y=array).

    Note real seaborn aggregates duplicate x values by mean and draws a
    confidence interval; this aggregates the same way but draws no interval, so
    bars here look more certain than seaborn's would.
    """
    if ax is None:
        ax = plt.gca()
    if data is None:
        if x is None or y is None:
            raise ValueError("barplot requires x and y")
        if hue is None:
            ax.bar([str(v) for v in x], y)
            return ax
        raise NotImplementedError("hue is only supported when data is provided")

    if hue is None:
        grouped = data.groupby(x, dropna=False)[y].mean()
        ax.bar(grouped.index.astype(str), grouped.values)
        return ax

    piv = data.pivot_table(index=x, columns=hue, values=y, aggfunc="mean")
    width = 0.8 / max(1, len(piv.columns))
    base = np.arange(len(piv.index))
    bars = []
    for i, col in enumerate(piv.columns):
        vals = piv[col].values
        b = ax.bar(base + i * width, vals, width=width, label=str(col))
        bars.extend(list(b))
    ax.set_xticks(base + width * (len(piv.columns) - 1) / 2)
    ax.set_xticklabels(piv.index.astype(str))
    if len(piv.columns) > 0:
        ax.legend()
    return ax


def heatmap(data, cmap="coolwarm", center=0, cbar_kws=None, ax=None, **_kwargs):
    if ax is None:
        ax = plt.gca()
    arr = np.asarray(data.values if hasattr(data, "values") else data, dtype=float)
    im = ax.imshow(arr, aspect="auto", cmap=cmap)
    # `center` symmetrises the colour scale around a value — matters for the
    # z-scored plots, where the diverging colormap is meaningless unless 0 sits
    # exactly at the midpoint.
    if center is not None:
        vmax = np.nanmax(np.abs(arr - center))
        im.set_clim(center - vmax, center + vmax)
    cbar = plt.colorbar(im, ax=ax)
    if cbar_kws and "label" in cbar_kws:
        cbar.set_label(cbar_kws["label"])
    if hasattr(data, "columns"):
        ax.set_xticks(np.arange(len(data.columns)))
        ax.set_xticklabels([str(c) for c in data.columns], rotation=90)
    if hasattr(data, "index"):
        ax.set_yticks(np.arange(len(data.index)))
        ax.set_yticklabels([str(i) for i in data.index])
    return ax


def kdeplot(x, label=None, warn_singular=False, ax=None, **_kwargs):
    """A stepped histogram wearing a KDE's name.

    No kernel density estimation happens here — that would mean pulling in scipy
    just for this. Close enough to read a distribution's shape from, but the
    curve is jagged where seaborn's would be smooth, and bin choice visibly
    changes what it looks like.
    """
    if ax is None:
        ax = plt.gca()
    vals = np.asarray(x, dtype=float)
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return ax
    # sqrt(n) bins, clamped — a rough Rice-rule stand-in that keeps small samples
    # from turning into three enormous bars.
    bins = min(60, max(10, int(np.sqrt(vals.size))))
    ax.hist(vals, bins=bins, density=True, histtype="step", label=label)
    if label:
        ax.legend()
    return ax

