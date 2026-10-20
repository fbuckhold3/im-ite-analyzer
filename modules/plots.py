"""Plotly figure builders. Figures are created once, then updated in place via shinywidgets (no flicker)."""

from __future__ import annotations

import plotly.graph_objects as go

from ite_core import nomogram

# Okabe-Ito colours: distinguishable with common colour-vision deficiencies
PGY_COLOR = {1: "#0072B2", 2: "#E69F00", 3: "#009E73"}
BAND = {"High": "rgba(213, 94, 0, 0.10)", "Intermediate": "rgba(230, 159, 0, 0.10)", "Low": "rgba(0, 158, 115, 0.08)"}
POINTS_TRACE = 3  # index of the "your scores" trace


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
        xaxis=dict(title="ITE percent correct", range=[30, 95], dtick=10, ticksuffix="%"),
        yaxis=dict(title="Estimated probability of passing ABIM", range=[0, 1.02], tickformat=".0%"),
        legend=dict(orientation="h", yanchor="bottom", y=0.02, xanchor="right", x=0.99),
        hovermode="closest",
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=13),
    )
    set_bands(fig, cutoffs)
    return fig


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
                name=standing,
                text=[f"{int(v)}" for v in s.percentile],
                textposition="middle right",
                marker=dict(
                    size=14,
                    color=STANDING_COLOR[standing],
                    line=dict(color="#1a1a1a", width=1),
                    symbol={"Focus": "triangle-down", "Typical": "circle", "Strength": "triangle-up"}[standing],
                ),
                customdata=s[["pct_correct", "national_mean"]].values,
                hovertemplate="%{y}: %{x}th percentile<br>You %{customdata[0]}% vs national mean "
                "%{customdata[1]}%<extra></extra>",
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
        xaxis=dict(title="Your national percentile (same PGY level)", range=[0, 104], dtick=10),
        yaxis=dict(title=None, automargin=True),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1),
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=13),
    )
    return fig
