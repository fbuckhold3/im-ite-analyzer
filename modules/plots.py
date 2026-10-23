"""Plotly figure builders. Figures are created once, then updated in place via shinywidgets (no flicker)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from ite_core import nomogram
from ite_core.individual import BAND_LABEL

# Okabe-Ito colours: distinguishable with common colour-vision deficiencies
PGY_COLOR = {1: "#0072B2", 2: "#E69F00", 3: "#009E73"}
BAND = {"High": "rgba(213, 94, 0, 0.10)", "Intermediate": "rgba(230, 159, 0, 0.10)", "Low": "rgba(0, 158, 115, 0.08)"}
POINTS_TRACE = 3  # index of the "your scores" trace
# Vertical toolbar on the right edge, so it never covers titles (it is always visible on touch screens)
# Privacy: never offer Plotly's cloud "Share chart" / "Edit in Chart Studio" buttons — they upload chart data
# (resident names and scores) to a third-party service.
MODEBAR = dict(
    orientation="v",
    bgcolor="rgba(255,255,255,0.7)",
    remove=["sendChartToCloud", "sendDataToCloud", "editInChartStudio", "lasso2d", "select2d"],
)


def widget_safe(fig):
    """Replace NaN/inf with None in every trace array. shinywidgets serializes with strict JSON, and a single NaN
    raises inside the session and disconnects the visitor."""
    import math

    import numpy as np

    def clean(v):
        if isinstance(v, (list, tuple, np.ndarray)):
            return [clean(x) for x in v]
        if isinstance(v, (float, np.floating)) and not math.isfinite(float(v)):
            return None
        return v.item() if isinstance(v, np.generic) else v

    fig.layout.modebar.remove = MODEBAR["remove"]  # privacy backstop: no cloud-share buttons on any chart
    for tr in fig.data:
        for attr in ("x", "y", "customdata", "text"):
            val = getattr(tr, attr, None)
            if val is not None and not isinstance(val, str):
                setattr(tr, attr, clean(val))
    return fig


def nomogram_figure(cutoffs=nomogram.DEFAULT_CUTOFFS) -> go.Figure:
    c = nomogram.curves(step=0.5, lo=30, hi=95)
    fig = go.Figure()
    for p in (1, 2, 3):
        d = c[c.PGY == p]
        fig.add_trace(
            go.Scatter(
                x=d.Pct_Correct,
                y=d.Pass_Prob,
                mode="lines",
                name=f"PGY-{p}",
                line=dict(color=PGY_COLOR[p], width=2.5),
                hovertemplate=f"PGY-{p}: %{{x:.0f}}% correct → %{{y:.1%}}<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=[],
            y=[],
            mode="markers",
            name="Your scores",
            text=[],
            marker=dict(size=13, color=[], line=dict(color="#1a1a1a", width=1.5)),
            hovertemplate="%{text}: %{x:.0f}% correct → %{y:.1%}<extra></extra>",
            showlegend=False,
        )
    )
    fig.update_layout(
        margin=dict(l=55, r=20, t=10, b=50),
        height=380,
        template="plotly_white",
        modebar=MODEBAR,
        xaxis=dict(title="ITE percent correct", range=[30, 95], dtick=10, ticksuffix="%"),
        yaxis=dict(title="Estimated probability of passing ABIM", range=[0, 1.02], tickformat=".0%"),
        legend=dict(orientation="h", yanchor="bottom", y=0.02, xanchor="right", x=0.99),
        hovermode="closest",
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=13),
    )
    set_bands(fig, cutoffs)
    return widget_safe(fig)


def set_bands(fig, cutoffs) -> None:
    hi, lo = cutoffs
    spans = [("High", 0, hi), ("Intermediate", hi, lo), ("Low", lo, 1.02)]
    fig.layout.shapes = [
        dict(type="rect", xref="paper", x0=0, x1=1, y0=a, y1=b, fillcolor=BAND[t], line_width=0, layer="below")
        for t, a, b in spans
    ]
    fig.layout.annotations = [
        dict(
            xref="paper",
            x=0.01,
            y=(a + min(b, 1)) / 2,
            text=f"{t} risk",
            showarrow=False,
            xanchor="left",
            font=dict(size=11, color="#555"),
        )
        for t, a, b in spans
    ]


def set_points(fig, rows) -> None:
    """rows: iterable of (pgy, pct_correct, prob)."""
    rows = [r for r in rows if r[1] is not None]
    t = fig.data[POINTS_TRACE]
    t.x = [r[1] for r in rows]
    t.y = [r[2] for r in rows]
    t.text = [f"PGY-{r[0]}" for r in rows]
    t.marker.color = [PGY_COLOR[min(3, max(1, int(r[0])))] for r in rows]


STANDING_COLOR = {"Strength": "#009E73", "Typical": "#7a7f87", "Focus": "#D55E00"}


def area_percentile_figure(areas, strength_at: int = 60, focus_below: int = 35) -> go.Figure:
    """Dot chart: one row per content area, x = the resident's national percentile (0-100)."""
    d = areas.sort_values("percentile")  # plotly draws the first row at the bottom
    fig = go.Figure()
    for standing in ("Focus", "Typical", "Strength"):
        s = d[d.standing == standing]
        if s.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=s.percentile,
                y=s.area,
                mode="markers+text",
                name=BAND_LABEL[standing],
                text=[f"{int(v)}" for v in s.percentile],
                textposition="middle right",
                marker=dict(
                    size=14,
                    color=STANDING_COLOR[standing],
                    line=dict(color="#1a1a1a", width=1),
                    symbol={"Focus": "triangle-down", "Typical": "circle", "Strength": "triangle-up"}[standing],
                ),
                customdata=s[["pct_correct", "national_mean"]].values,
                hovertemplate=(
                    "%{y}: %{x}th percentile<br>You %{customdata[0]}% vs national mean %{customdata[1]}%<extra></extra>"
                    if s.national_mean.notna().any()
                    else "%{y}: %{x}th percentile<br>You %{customdata[0]}% correct<extra></extra>"
                ),
            )
        )
    for x, label in ((focus_below, f"{focus_below}th"), (50, "50th"), (strength_at, f"{strength_at}th")):
        fig.add_vline(
            x=x,
            line=dict(color="#9aa0a6", width=1, dash="dot" if x == 50 else "dash"),
            annotation_text=label,
            annotation_position="top",
            annotation_font_size=11,
        )
    fig.update_layout(
        height=60 + 34 * len(d),
        margin=dict(l=10, r=30, t=44, b=45),
        template="plotly_white",
        modebar=MODEBAR,
        xaxis=dict(title="Your national percentile (same PGY level)", range=[0, 104], dtick=10),
        yaxis=dict(title=None, automargin=True),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1),
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=13),
    )
    return widget_safe(fig)


# ------------------------------------------------------------------ program trends
FONT = dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=13)
# Okabe-Ito order for classes, newest class = slot 1
CLASS_COLORS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#000000"]

LEVEL_METRICS = {
    "ile": ("Mean percentile", "", True),
    "med": ("Median percentile", "", True),
    "ge50": ("% at or above the 50th percentile", "%", False),
    "lt35": ("% below the 35th percentile", "%", False),
    "pc": ("Mean percent correct", "%", False),
    "pp_low": ("% in the Low-risk tier", "%", False),
}


def level_small_multiples(lv, metric: str = "ile"):
    """PGY-1 / PGY-2 / PGY-3 panels, one bar per exam year. Small groups (n < 5) are faded and hatched."""
    from plotly.subplots import make_subplots

    label, suffix, is_pctile = LEVEL_METRICS[metric]
    pgys = [p for p in (1, 2, 3) if p in set(lv.PGY)]
    years = sorted(lv.Exam_Year.unique())
    fig = make_subplots(
        rows=1, cols=len(pgys), shared_yaxes=True, subplot_titles=[f"PGY-{p}" for p in pgys], horizontal_spacing=0.04
    )
    for i, p in enumerate(pgys, 1):
        d = lv[lv.PGY == p].set_index("Exam_Year").reindex(years)
        small = d.small_n.fillna(False).astype(bool)
        fig.add_trace(
            go.Bar(
                x=[str(y) for y in years],
                y=d[metric],
                showlegend=False,
                marker=dict(
                    color=PGY_COLOR[p],
                    opacity=[0.45 if s else 1 for s in small],
                    pattern=dict(shape=["/" if s else "" for s in small]),
                ),
                text=[("" if v != v else f"{v:.0f}{suffix}") for v in d[metric]],
                textposition="outside",
                customdata=d[["n"]].fillna(0).astype(int).values,
                hovertemplate=f"PGY-{p}, %{{x}}: %{{y:.1f}}{suffix} (n=%{{customdata[0]}})<extra></extra>",
            ),
            row=1,
            col=i,
        )
        if is_pctile:
            fig.add_hline(y=50, line=dict(color="#9aa0a6", dash="dot", width=1), row=1, col=i)
    top = 100 if suffix == "%" and metric != "pc" else (100 if is_pctile else 85)
    fig.update_yaxes(range=[0 if metric != "pc" else 40, top + 8], title_text=label, row=1, col=1)
    fig.update_layout(
        height=340,
        margin=dict(l=55, r=15, t=40, b=35),
        template="plotly_white",
        modebar=MODEBAR,
        font=FONT,
        bargap=0.25,
    )
    return widget_safe(fig)


def class_trajectories_figure(t, value_label: str = "Mean percentile"):
    """One line per graduating class across PGY-1 -> PGY-3. Current solid, graduated dashed; end labels."""
    fig = go.Figure()
    classes = list(dict.fromkeys(t.Grad_Class))  # newest first
    for k, gc in enumerate(classes):
        d = t[t.Grad_Class == gc].sort_values("PGY")
        current = d.status.iloc[0] == "current"
        color = CLASS_COLORS[k % len(CLASS_COLORS)]
        fig.add_trace(
            go.Scatter(
                x=[f"PGY-{p}" for p in d.PGY],
                y=d.value,
                mode="lines+markers",
                name=f"Class of {gc}",
                line=dict(color=color, width=3 if current else 2, dash="solid" if current else "dash"),
                marker=dict(size=9 if current else 7, color=color),
                customdata=d[["n", "Exam_Year"]].values,
                hovertemplate=(
                    f"Class of {gc}, %{{x}} (%{{customdata[1]}}): %{{y:.1f}} · n=%{{customdata[0]}}<extra></extra>"
                ),
            )
        )
        last = d.iloc[-1]
        if len(d) < 2:
            continue  # single-point classes are identified by the legend (end labels would collide)
        fig.add_annotation(
            x=f"PGY-{int(last.PGY)}",
            y=last.value,
            text=f"  {gc}",
            showarrow=False,
            xanchor="left",
            font=dict(color=color, size=12),
        )
    if "percentile" in value_label.lower():
        fig.add_hline(y=50, line=dict(color="#9aa0a6", dash="dot", width=1))
    fig.update_layout(
        height=380,
        margin=dict(l=55, r=60, t=10, b=40),
        template="plotly_white",
        modebar=MODEBAR,
        font=FONT,
        xaxis=dict(categoryorder="array", categoryarray=["PGY-1", "PGY-2", "PGY-3"]),
        yaxis=dict(title=value_label),
        legend=dict(title="Solid = current, dashed = graduated"),
    )
    return widget_safe(fig)


def yoy_scatter(pts, outcome: str = "percentile", labels: bool = True):
    """Last year vs this year for the same residents, coloured by current PGY; diagonal = no change."""
    pre, cur, lab = (
        ("ile_prev", "ile_cur", "percentile") if outcome == "percentile" else ("pc_prev", "pc_cur", "% correct")
    )
    fig = go.Figure()
    for p in (2, 3):
        d = pts[pts.PGY == p]
        if d.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=d[pre],
                y=d[cur],
                mode="markers",
                name=f"Now PGY-{p}",
                marker=dict(
                    size=10,
                    color=PGY_COLOR[p],
                    line=dict(color="#1a1a1a", width=0.8),
                    symbol="circle" if p == 2 else "diamond",
                ),
                text=d.Name if labels else None,
                hovertemplate=("%{text}<br>" if labels else "")
                + f"Last year %{{x:.0f}} → this year %{{y:.0f}} ({lab})<extra></extra>",
            )
        )
    if outcome == "percentile":
        lo, hi = 0, 100
        for g in (20, 35):
            fig.add_hline(y=g, line=dict(color="#d55e00", dash="dot", width=1))
            fig.add_vline(x=g, line=dict(color="#d55e00", dash="dot", width=1))
    else:
        vals = list(pts[pre]) + list(pts[cur])
        lo, hi = (min(vals) - 3, max(vals) + 3) if vals else (40, 90)
    fig.add_trace(
        go.Scatter(
            x=[lo, hi],
            y=[lo, hi],
            mode="lines",
            line=dict(color="#9aa0a6", width=1),
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.update_layout(
        height=420,
        margin=dict(l=55, r=15, t=10, b=50),
        template="plotly_white",
        modebar=MODEBAR,
        font=FONT,
        xaxis=dict(title=f"Last year's {lab}", range=[lo, hi]),
        yaxis=dict(title=f"This year's {lab}", range=[lo, hi]),
        legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="right", x=0.99),
    )
    return widget_safe(fig)


def program_nomogram(bt, cutoffs=nomogram.DEFAULT_CUTOFFS):
    """The three curves plus one dot per current resident (trace per PGY; customdata = resident ID).
    Traces from index POINTS_TRACE + 1 on are resident traces (click targets)."""
    cy = bt.attrs["current_year"]
    fig = nomogram_figure(cutoffs)
    for p in (1, 2, 3):
        d = bt[(bt.PGY == p) & bt[f"Pct_{cy}"].notna()]
        fig.add_trace(
            go.Scatter(
                x=d[f"Pct_{cy}"],
                y=d[f"Prob_{cy}"],
                mode="markers",
                name=f"PGY-{p} residents",
                marker=dict(
                    size=10,
                    color=PGY_COLOR[p],
                    line=dict(color="#1a1a1a", width=0.8),
                    symbol={1: "circle", 2: "square", 3: "diamond"}[p],
                ),
                customdata=d.ID.values,
                text=d.Name,
                hovertemplate="%{text}<br>%{x:.0f}% correct → %{y:.1%}<br><i>click for details</i><extra></extra>",
            )
        )
    fig.update_layout(height=420, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return widget_safe(fig)


# ------------------------------------------------------------------------------ MKSAP
def mksap_strip(w):
    """Questions answered per current PGY: every resident a dot, box = middle half. Log axis (0 shown at 1)."""
    fig = go.Figure()
    d = w[w.mk_answered.notna()]
    for p in (1, 2, 3):
        v = d[d.PGY == p]
        if v.empty:
            continue
        fig.add_trace(
            go.Box(
                y=v.mk_answered.clip(lower=1),
                name=f"PGY-{p}",
                boxpoints="all",
                jitter=0.45,
                pointpos=0,
                marker=dict(color=PGY_COLOR[p], size=7, line=dict(color="#1a1a1a", width=0.5)),
                line=dict(color=PGY_COLOR[p]),
                fillcolor="rgba(0,0,0,0)",
                text=v.Name,
                hovertemplate="%{text}: %{y:,.0f} questions<extra></extra>",
                showlegend=False,
            )
        )
    fig.update_layout(
        height=340,
        margin=dict(l=60, r=15, t=10, b=35),
        template="plotly_white",
        modebar=MODEBAR,
        font=FONT,
        yaxis=dict(title="Questions answered (log scale)", type="log", tickvals=[1, 10, 30, 100, 300, 1000, 3000]),
    )
    return widget_safe(fig)


def thirds_bar(by_pgy, pooled, outcome: str = "pct"):
    """Mean ITE change by MKSAP-volume third (within class): pooled and per PGY."""
    col, label = ("dpc", "Mean change in ITE % correct") if outcome == "pct" else ("dile", "Mean change in percentile")
    fig = go.Figure()
    groups = [("All PGY-2/3", pooled, "#4d4d4d")] + [
        (f"PGY-{p}", by_pgy[by_pgy.PGY == p], PGY_COLOR[p]) for p in (2, 3) if (by_pgy.PGY == p).any()
    ]
    for name, d, color in groups:
        fig.add_trace(
            go.Bar(
                x=d.vol.astype(str),
                y=d[col],
                name=name,
                marker_color=color,
                customdata=d[["n", "q"]].values,
                text=[f"{v:+.1f}" for v in d[col]],
                textposition="outside",
                hovertemplate=f"{name}, %{{x}} third: %{{y:+.1f}} (n=%{{customdata[0]}}, "
                "median %{customdata[1]:.0f} questions)<extra></extra>",
            )
        )
    fig.add_hline(y=0, line=dict(color="#9aa0a6", width=1))
    fig.update_layout(
        barmode="group",
        height=340,
        margin=dict(l=60, r=15, t=30, b=40),
        template="plotly_white",
        modebar=MODEBAR,
        font=FONT,
        yaxis=dict(title=label),
        xaxis=dict(title="Third of MKSAP questions answered (within class)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return widget_safe(fig)


def mksap_scatter(pts, outcome: str = "pct", labels: bool = True):
    """Questions answered (log) vs ITE change, coloured by PGY, with a least-squares trend on log(1 + questions)."""
    from ite_core.stats import trend_line

    col, label = (
        ("dPct_1yr", "Change in ITE % correct") if outcome == "pct" else ("dPctile_1yr", "Change in percentile")
    )
    fig = go.Figure()
    for p in (2, 3):
        d = pts[pts.PGY == p]
        if d.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=d.mk_answered.clip(lower=1),
                y=d[col],
                mode="markers",
                name=f"Now PGY-{p}",
                text=d.Name if labels else None,
                marker=dict(
                    size=10,
                    color=PGY_COLOR[p],
                    line=dict(color="#1a1a1a", width=0.8),
                    symbol="circle" if p == 2 else "diamond",
                ),
                hovertemplate=("%{text}: " if labels else "") + "%{x:,.0f} questions, change %{y:+.0f}<extra></extra>",
            )
        )
    xs, ys = trend_line(pts.mk_answered, pts[col])
    if len(xs):
        fig.add_trace(
            go.Scatter(
                x=xs.clip(min=1),
                y=ys,
                mode="lines",
                name="Trend",
                hoverinfo="skip",
                line=dict(color="#4d4d4d", width=2, dash="dash"),
            )
        )
    fig.add_hline(y=0, line=dict(color="#9aa0a6", width=1))
    fig.update_layout(
        height=380,
        margin=dict(l=60, r=15, t=10, b=50),
        template="plotly_white",
        modebar=MODEBAR,
        font=FONT,
        xaxis=dict(title="MKSAP questions answered (log scale)", type="log", tickvals=[10, 30, 100, 300, 1000, 3000]),
        yaxis=dict(title=label),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return widget_safe(fig)


# ------------------------------------------------------------------ item gaps
def area_ranks_figure(ranks):
    """Program percentile rank among all programs, per content area: one marker per PGY group, All as a diamond."""
    d = ranks[ranks.area != "Total Test"].iloc[::-1]  # first area at the top
    fig = go.Figure()
    groups = [
        ("1", "PGY-1", PGY_COLOR[1], "circle"),
        ("2", "PGY-2", PGY_COLOR[2], "square"),
        ("3", "PGY-3", PGY_COLOR[3], "triangle-up"),
        ("A", "All PGYs", "#1a1a1a", "diamond"),
    ]
    for k, name, color, symbol in groups:
        fig.add_trace(
            go.Scatter(
                x=d[f"rank{k}"],
                y=d.area,
                mode="markers",
                name=name,
                marker=dict(
                    size=13 if k == "A" else 9, color=color, symbol=symbol, line=dict(color="#1a1a1a", width=0.6)
                ),
                customdata=d[[f"our{k}", f"all{k}"]].values,
                hovertemplate=f"%{{y}} · {name}: rank %{{x}} (program %{{customdata[0]}}% vs all %{{customdata[1]}}%)"
                "<extra></extra>",
            )
        )
    fig.add_vline(x=50, line=dict(color="#9aa0a6", dash="dot", width=1))
    fig.update_layout(
        height=70 + 30 * len(d),
        margin=dict(l=10, r=15, t=40, b=45),
        template="plotly_white",
        modebar=MODEBAR,
        font=FONT,
        xaxis=dict(title="Program percentile rank among all programs (50 = middle)", range=[0, 100]),
        yaxis=dict(automargin=True),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return widget_safe(fig)


# Diverging scale for ranks among programs: vermillion (bottom) -> white (middle, 50) -> blue (top). Okabe-Ito ends.
RANK_SCALE = [[0.0, "#c2410c"], [0.25, "#f4a261"], [0.5, "#f7f7f7"], [0.75, "#7fb3d9"], [1.0, "#0b5cad"]]


def area_ranks_heatmap(ranks, total: bool = True):
    """Content areas x PGY groups, each cell the program's percentile rank among all programs (50 = middle).

    Rows sorted by the All-PGY rank, lowest at the top, so the areas to look at first lead. Numbers are printed in
    every cell, so colour is never the only cue.
    """
    d = ranks[ranks.area != "Total Test"].sort_values("rankA", ascending=True, na_position="first")
    if total and (ranks.area == "Total Test").any():
        d = pd.concat([d, ranks[ranks.area == "Total Test"].assign(area="Total test")])  # drawn at the bottom
    cols = [("1", "PGY-1"), ("2", "PGY-2"), ("3", "PGY-3"), ("A", "All PGYs")]
    z = d[[f"rank{k}" for k, _ in cols]].to_numpy(dtype=float)
    our = d[[f"our{k}" for k, _ in cols]].to_numpy()
    nat = d[[f"all{k}" for k, _ in cols]].to_numpy()
    text = [["" if v != v else f"{v:.0f}" for v in row] for row in z]
    custom = [[[o, a] for o, a in zip(orow, arow, strict=True)] for orow, arow in zip(our, nat, strict=True)]
    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=[label for _, label in cols],
            y=d.area.tolist(),
            text=text,
            texttemplate="%{text}",
            textfont=dict(size=13),
            customdata=custom,
            colorscale=RANK_SCALE,
            zmin=0,
            zmax=100,
            xgap=3,
            ygap=3,
            showscale=False,  # the legend text explains the colours and every cell shows its number
            hovertemplate="%{y} · %{x}<br>Rank among programs: %{z:.0f}<br>"
            "Program %{customdata[0]}% vs all programs %{customdata[1]}% correct<extra></extra>",
        )
    )
    fig.update_layout(
        height=90 + 34 * len(d),
        margin=dict(l=10, r=10, t=40, b=10),
        template="plotly_white",
        modebar=MODEBAR,
        font=FONT,
        xaxis=dict(side="top", showgrid=False, tickfont=dict(size=13)),
        yaxis=dict(automargin=True, showgrid=False, autorange="reversed"),
        plot_bgcolor="#fff",
    )
    return widget_safe(fig)


OUTCOME_COLOR = {True: "#0072B2", False: "#D55E00"}  # Okabe-Ito blue (pass) / vermillion (fail)


def outcome_strip(t, low_cut: float = nomogram.DEFAULT_CUTOFFS[1]):
    """Each linked ABIM taker as a dot: x = estimated pass probability from their last ITE, row = actual result.
    Unlabeled on purpose (shown in the app and the PD report without names). A small fixed vertical spread keeps
    overlapping dots visible without randomness."""
    d = t[t.predicted.notna()].reset_index(drop=True)
    rows = {True: 1.0, False: 0.0}
    fig = go.Figure()
    for passed, label in ((True, "Passed"), (False, "Did not pass")):
        s = d[d.passed == passed]
        spread = (((s.index.to_numpy() * 37) % 9) - 4) * 0.035
        fig.add_trace(
            go.Scatter(
                x=100 * s.predicted.to_numpy(),
                y=rows[passed] + spread,
                mode="markers",
                name=label,
                marker=dict(
                    size=12,
                    color=OUTCOME_COLOR[passed],
                    symbol="circle" if passed else "diamond",
                    line=dict(color="#1a1a1a", width=0.8),
                    opacity=0.85,
                ),
                customdata=s[["exam_year", "ite_pct"]].to_numpy(),
                hovertemplate=f"{label} · %{{customdata[0]}} exam<br>last ITE %{{customdata[1]:.0f}}% correct · "
                "estimated %{x:.0f}%<extra></extra>",
                showlegend=False,
            )
        )
    fig.add_vline(x=100 * low_cut, line=dict(color="#0b6e4f", dash="dot", width=1.2))
    fig.add_annotation(
        x=100 * low_cut,
        y=1.0,
        yref="paper",
        yanchor="bottom",
        text=f"Low risk ≥ {int(100 * low_cut)}%",
        showarrow=False,
        font=dict(size=11, color="#0b6e4f"),
        xanchor="right",
    )
    fig.update_layout(
        height=240,
        margin=dict(l=10, r=15, t=30, b=45),
        template="plotly_white",
        modebar=MODEBAR,
        font=FONT,
        xaxis=dict(title="Estimated chance of passing from the last ITE (%)", range=[0, 101]),
        yaxis=dict(
            tickvals=[0, 1], ticktext=["Did not pass", "Passed"], range=[-0.5, 1.5], automargin=True, showgrid=False
        ),
    )
    return widget_safe(fig)


def abim_score_scatter(t, passing_score=None):
    """ABIM standardized score (released scores only) against the last ITE percent correct; passing score line."""
    d = t[t.score.notna() & t.ite_pct.notna()]
    fig = go.Figure()
    for passed, label in ((True, "Passed"), (False, "Did not pass")):
        s = d[d.passed == passed]
        fig.add_trace(
            go.Scatter(
                x=s.ite_pct,
                y=s.score,
                mode="markers",
                name=label,
                marker=dict(
                    size=11,
                    color=OUTCOME_COLOR[passed],
                    symbol="circle" if passed else "diamond",
                    line=dict(color="#1a1a1a", width=0.8),
                ),
                hovertemplate="Last ITE %{x:.0f}% correct · ABIM score %{y:.0f}<extra></extra>",
            )
        )
    if passing_score:
        fig.add_hline(y=passing_score, line=dict(color="#b3261e", dash="dash", width=1.2))
        fig.add_annotation(
            xref="paper",
            x=0.0,
            y=passing_score,
            text=f"Passing score {passing_score}",
            showarrow=False,
            yshift=10,
            xanchor="left",
            font=dict(size=11, color="#b3261e"),
        )
    fig.update_layout(
        height=360,
        margin=dict(l=10, r=15, t=30, b=45),
        template="plotly_white",
        modebar=MODEBAR,
        font=FONT,
        xaxis=dict(title="Last ITE before graduating — % correct"),
        yaxis=dict(title="ABIM standardized score"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return widget_safe(fig)


def add_targets(fig, targets, cutoffs=nomogram.DEFAULT_CUTOFFS):
    """Mark where each later PGY curve reaches the Low-risk cutoff: [(pgy, pct_needed), ...]."""
    if not targets:
        return widget_safe(fig)
    fig.add_trace(
        go.Scatter(
            x=[t[1] for t in targets],
            y=[cutoffs[1]] * len(targets),
            mode="markers+text",
            name="Next-year targets",
            text=[f"PGY-{p}: {pct:.1f}%" for p, pct in targets],
            textposition="bottom right",
            textfont=dict(size=12, color="#1a1a1a"),
            marker=dict(
                size=14, symbol="star", color=[PGY_COLOR[p] for p, _ in targets], line=dict(color="#1a1a1a", width=1)
            ),
            hovertemplate="To reach Low risk at %{text}<extra></extra>",
        )
    )
    fig.add_hline(y=cutoffs[1], line=dict(color="#0b6e4f", dash="dot", width=1))
    return widget_safe(fig)
