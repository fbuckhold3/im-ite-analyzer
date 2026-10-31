"""Static (PNG) versions of the resident charts for PDFs, drawn with matplotlib.

Uses the object API (Figure + FigureCanvasAgg), never pyplot: pyplot keeps global state, which is unsafe
when several visitors build PDFs at once. Colours and markers match modules/plots.py.
"""

from __future__ import annotations

import io

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from ite_core import nomogram
from ite_core.individual import BAND_LABEL

from .plots import PGY_COLOR, STANDING_COLOR

MARKER = {"Strength": "^", "Typical": "o", "Focus": "v"}
BAND = {"High": "#fbe3d6", "Intermediate": "#fcf0d6", "Low": "#dff1e8"}
INK, SOFT = "#1f2328", "#57606a"


def _png(fig: Figure, dpi: int = 200) -> bytes:
    buf = io.BytesIO()
    FigureCanvasAgg(fig)
    fig.savefig(buf, format="png", dpi=dpi)
    return buf.getvalue()


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=SOFT, labelsize=8)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c8ccd1")


def area_percentile_png(areas, strength_at: int = 60, focus_below: int = 35, width_in: float = 7.0) -> bytes:
    """Content areas (rows) by national percentile, Strength / Typical / Focus markers, guide lines."""
    d = areas.sort_values("percentile")
    fig = Figure(figsize=(width_in, 0.25 * len(d) + 0.8))
    ax = fig.add_subplot()
    y = np.arange(len(d))
    for standing in ("Focus", "Typical", "Strength"):
        m = (d.standing == standing).to_numpy()
        if m.any():
            ax.scatter(
                d.percentile[m],
                y[m],
                s=55,
                marker=MARKER[standing],
                color=STANDING_COLOR[standing],
                edgecolor=INK,
                linewidth=0.5,
                label=BAND_LABEL[standing],
                zorder=3,
            )
    for x, v in zip(d.percentile, y, strict=True):
        ax.annotate(f"{int(x)}", (x, v), xytext=(6, -3), textcoords="offset points", fontsize=7.5, color=INK)
    for x, ls in ((focus_below, "--"), (50, ":"), (strength_at, "--")):
        ax.axvline(x, color="#9aa0a6", linestyle=ls, linewidth=0.8, zorder=1)
    ax.set_yticks(y, d.area, fontsize=8)
    ax.set_xlim(0, 104)
    ax.set_xlabel("National percentile (same PGY level)", fontsize=8, color=SOFT)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), fontsize=7.5, frameon=False, ncol=3)
    _style(ax)
    fig.tight_layout()
    return _png(fig)


def nomogram_png(points, cutoffs=nomogram.DEFAULT_CUTOFFS, width_in: float = 6.0, targets=()) -> bytes:
    """The three PGY curves with tier bands and the resident's points. points: iterable of (pgy, pct, prob)."""
    fig = Figure(figsize=(width_in, 3.2))
    ax = fig.add_subplot()
    hi, lo = cutoffs
    for tier, a, b in (("High", 0, hi), ("Intermediate", hi, lo), ("Low", lo, 1.02)):
        ax.axhspan(a, b, color=BAND[tier], zorder=0)
        x, ha = (31, "left") if tier == "Low" else (94, "right")  # keep clear of the curves, as in plots.set_bands
        ax.text(x, (a + min(b, 1)) / 2, f"{tier} risk", fontsize=7, color=SOFT, va="center", ha=ha)
    c = nomogram.curves(step=0.5, lo=30, hi=95)
    for p in (1, 2, 3):
        s = c[c.PGY == p]
        ax.plot(s.Pct_Correct, s.Pass_Prob, color=PGY_COLOR[p], linewidth=2, label=f"PGY-{p}", zorder=2)
    for pgy, pct, prob in points:
        if pct is None or prob is None or prob != prob:
            continue
        ax.scatter([pct], [prob], s=60, color=PGY_COLOR[min(3, max(1, int(pgy)))], edgecolor=INK, linewidth=1, zorder=4)
    for i, (pgy, pct) in enumerate(targets):  # where each later PGY curve reaches the Low-risk cutoff
        ax.scatter([pct], [lo], s=150, marker="*", color=PGY_COLOR[pgy], edgecolor=INK, linewidth=0.8, zorder=5)
        last = i == len(targets) - 1  # targets sit ~5 points apart: earlier labels left of the star, as in plots
        ax.annotate(
            f"PGY-{pgy}: ~{pct:.0f}%",
            (pct, lo),
            xytext=(6 if last else -6, -12),
            textcoords="offset points",
            ha="left" if last else "right",
            fontsize=8,
            color=INK,
            fontweight="bold",
        )
    if targets:
        ax.axhline(lo, color="#0b6e4f", linestyle=":", linewidth=1, zorder=1)
    ax.set_xlim(30, 95)
    ax.set_ylim(0, 1.02)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.set_xlabel("ITE percent correct", fontsize=8, color=SOFT)
    ax.set_ylabel("Estimated probability of passing ABIM", fontsize=8, color=SOFT)
    ax.legend(loc="lower right", fontsize=7.5, frameon=False, ncol=3)  # as in plots.nomogram_figure
    _style(ax)
    fig.tight_layout()
    return _png(fig)
