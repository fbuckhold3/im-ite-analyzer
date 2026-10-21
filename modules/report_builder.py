"""Downloadable reports: identified PD report and de-identified program summary (self-contained HTML).

Pure functions (no Shiny server): build_report(dataset, program, deidentified) -> bytes.
Charts are Plotly with plotly.js embedded once, so files open offline and stay interactive (~5 MB).

De-identified rules: no names or IDs; no per-person tiers (counts only); scatter points unlabeled;
any count of 1-4 and any group mean from fewer than 5 residents shown as "<5" / suppressed.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.offline
from htmltools import HTML, Tag, tags

from ite_core import board, history, mksap, pdf_reports, stats
from ite_core.history import SMALL_N
from ite_core.nomogram import DEFAULT_CUTOFFS

from . import plots
from .common import DOI, ORCID, REPO

CSS = """
:root{--ink:#1f2328;--soft:#57606a;--line:#d8dee4;--page:#f4f6f8;--card:#fff;--primary:#0b5cad;--navy:#0d2a47;
--high:#b3261e;--high-bg:#fde7e5;--mid:#8a5a00;--mid-bg:#fcf0d6;--low:#0b6e4f;--low-bg:#dcf3ea;color-scheme:light}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);background:var(--page);margin:0;
line-height:1.5;font-size:15px}
.wrap{max-width:1200px;margin:0 auto;padding:0 24px 32px}
.hero{background:var(--navy);color:#fff;padding:28px 0 26px}
.hero .wrap{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;justify-content:space-between;padding-bottom:0}
.hero h1{font-size:2rem;line-height:1.15;margin:0 0 .35rem;font-weight:700;text-wrap:balance}
.hero p{margin:0;color:#c9d6e3;font-size:1rem}
.print-btn{font:inherit;font-size:.9rem;font-weight:600;padding:.5rem 1rem;border:1px solid #fff;color:var(--navy);
background:#fff;border-radius:6px;cursor:pointer;min-height:40px}
.print-btn:hover{background:#e8eef5} .print-btn:focus-visible{outline:3px solid #8cc4ff;outline-offset:2px}
.notice{display:flex;gap:.6rem;align-items:baseline;flex-wrap:wrap;margin:20px 0 0;padding:.7rem 1rem;
border-radius:8px;border:1px solid}
.notice strong{white-space:nowrap}
.confidential{background:var(--high-bg);border-color:#f2b8b2;color:#6e1610}
.public{background:var(--low-bg);border-color:#a9dcc7;color:#084a35}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.kpi-value{font-size:2rem;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.kpi-label{font-weight:600;margin-top:.3rem} .kpi-context{color:var(--soft);font-size:.85rem;margin-top:.15rem}
.tone-high{color:var(--high)} .tone-low{color:var(--low)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:22px 24px;margin:20px 0 0}
.card h2{font-size:1.35rem;margin:0;line-height:1.25}
.takeaway{font-size:1.08rem;margin:.4rem 0 1rem;color:var(--ink);max-width:75ch}
h3{font-size:1rem;margin:1.4rem 0 .4rem}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr));gap:20px;align-items:start}
.scroll{overflow-x:auto}
table{border-collapse:collapse;margin:.5rem 0 1rem;font-variant-numeric:tabular-nums;width:100%}
th,td{border-bottom:1px solid var(--line);padding:.45rem .6rem;text-align:left;vertical-align:top}
th{color:var(--soft);font-weight:600;font-size:.9rem;background:#f6f8fa}
td.num,th.num{text-align:right;white-space:nowrap} td:first-child,th:first-child{white-space:nowrap}
.narrow-chart{max-width:760px}
.note{color:var(--soft);font-size:.9rem;max-width:80ch}
.box{background:#f6f8fa;border:1px solid var(--line);border-radius:10px;padding:.8rem 1rem;margin:20px 0 0;
max-width:none}
.badge{display:inline-block;padding:.1rem .55rem;border-radius:999px;font-size:.82rem;font-weight:600;
white-space:nowrap}
.b-High,.b-red{background:var(--high-bg);color:var(--high)} .b-Intermediate,.b-yellow{background:var(--mid-bg);
color:var(--mid)} .b-Low{background:var(--low-bg);color:var(--low)}
.gap-bad{color:var(--high);font-weight:600}
.tierbar{display:flex;height:14px;min-width:90px;border-radius:4px;overflow:hidden;background:#eef1f4}
.tierbar span{display:block;height:100%} .seg-High{background:#d55e00} .seg-Intermediate{background:#e69f00}
.seg-Low{background:#009e73}
footer{margin-top:28px;color:var(--soft);font-size:.85rem}
a{color:var(--primary)} .print-footer{display:none}
@media (max-width:600px){.wrap{padding:0 16px 24px}.hero h1{font-size:1.6rem}.card{padding:18px 16px}
.kpi-value{font-size:1.7rem}}
@page{size:letter;margin:0.6in 0.6in 0.7in}
@media print{body{background:#fff;font-size:10.5pt}.wrap{max-width:none;padding:0}
*{-webkit-print-color-adjust:exact;print-color-adjust:exact}
.hero{padding:0 0 10pt;background:none;color:var(--ink);border-bottom:2pt solid var(--navy)}
.hero p{color:var(--soft)} .hero h1{font-size:20pt}
.print-btn,.modebar,.modebar-container{display:none!important}
.card{border:none;padding:0;margin:0;border-radius:0;break-before:page}
.kpis{grid-template-columns:repeat(3,1fr)} .grid2{display:block}
table,.plotly-graph-div,.box,.kpi,.notice{break-inside:avoid}
.plotly-graph-div{max-width:100%!important} .print-footer{display:block;position:fixed;bottom:0;left:0;
right:0;font-size:7.5pt;color:var(--soft);border-top:1px solid var(--line);padding-top:2pt}}
"""


# ----------------------------------------------------------------------------------------- helpers
def _fig(fig) -> HTML:
    f = go.Figure(fig)  # copy: the builders' figures are shared with the app
    f.update_layout(font_size=14, legend_font_size=13, autosize=True, width=None)
    return HTML(
        f.to_html(
            full_html=False,
            include_plotlyjs=False,
            default_width="100%",
            config={"displaylogo": False, "showSendToCloud": False, "responsive": True},
        )
    )


def _num(x, digits=0, suffix=""):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{digits}f}{suffix}"


def sup_count(k) -> str:
    """Small-cell suppression for counts in de-identified output."""
    k = int(k)
    return "<5" if 0 < k < SMALL_N else str(k)


def _table(head, rows, num=(), **attrs) -> Tag:
    """num: column indexes to right-align (numbers)."""

    def cls(i):
        return "num" if i in num else None

    return tags.div(
        tags.table(
            tags.thead(tags.tr(*[tags.th(h, class_=cls(i)) for i, h in enumerate(head)])),
            tags.tbody(*[tags.tr(*[tags.td(c, class_=cls(i)) for i, c in enumerate(r)]) for r in rows]),
            **attrs,
        ),
        class_="scroll",
    )


def _badge(text, kind) -> Tag:
    return tags.span(text, class_=f"badge b-{kind}")


def _tier_bar(counts: dict) -> Tag:
    """Stacked High / Intermediate / Low bar (identified report only: widths reveal exact counts)."""
    n = sum(counts.values()) or 1
    return tags.div(
        *[tags.span(class_=f"seg-{k}", style=f"width:{100 * v / n:.1f}%") for k, v in counts.items() if v],
        class_="tierbar",
        aria_hidden="true",
    )


def _card(sid, title, takeaway, *body) -> Tag:
    return tags.section(
        tags.h2(title, id=sid),
        tags.p(takeaway, class_="takeaway") if takeaway else None,
        *body,
        class_="card",
        aria_labelledby=sid,
    )


def _kpi(value, label, context="", tone="") -> Tag:
    return tags.div(
        tags.div(value, class_=f"kpi-value {tone}".strip()),
        tags.div(label, class_="kpi-label"),
        tags.div(context, class_="kpi-context") if context else None,
        class_="kpi",
    )


def _suppress_small(df: pd.DataFrame, cols) -> pd.DataFrame:
    out = df.copy()
    out.loc[out.small_n, cols] = np.nan
    return out


def _how_to_read() -> Tag:
    return tags.div(
        tags.strong("How to read these numbers. "),
        "Percent correct is the share of questions answered correctly; it depends on that year's exam and rises with "
        "training (nationally about 60/67/70% for PGY-1/2/3 in 2026) and drives the ABIM estimate. Percentile ranks a "
        "score against same-PGY U.S. residents that year (50 = middle) and is the better number for comparing years "
        "and classes.",
        class_="box",
    )


# ---------------------------------------------------------------------------------------- sections
def _senior_low(bt) -> tuple[int, int]:
    """(PGY-2/3 residents with a current-year estimate, how many of them are in Low risk)."""
    cy = bt.attrs["current_year"]
    s = bt[bt.PGY.isin([2, 3]) & bt[f"Prob_{cy}"].notna()]
    return len(s), int((s.Tier == "Low").sum())


def _paired(w, deid) -> list[dict]:
    """Year-over-year change per current PGY level (2, 3); groups under 5 dropped when de-identified."""
    out = []
    for p in (2, 3):
        c = stats.paired_change(w, p)
        if c["n"] and not (deid and c["n"] < SMALL_N):
            out.append(c)
    return out


def _pooled_change(cs) -> tuple[float, int] | None:
    n = sum(c["n"] for c in cs)
    if not n:
        return None
    return sum(c["d_ile"] * c["n"] for c in cs) / n, n


def _kpis(ds, program, cutoffs, deid) -> Tag | None:
    tiles = []
    if ds is not None and ds.wide is not None:
        bt = board.board_table(ds.wide, cutoffs)
        cy = bt.attrs["current_year"]
        tested = int(bt[f"Pct_{cy}"].notna().sum())
        tiles.append(_kpi(sup_count(tested) if deid else str(tested), "Residents tested", f"{cy} ITE, all levels"))
        n, low = _senior_low(bt)
        below = n - low
        if n and not (deid and n < SMALL_N):
            share = (
                f"≥{math.floor(100 * (n - (SMALL_N - 1)) / n)}%"
                if deid and 0 < below < SMALL_N
                else f"{math.floor(100 * low / n)}%"
            )
            tiles.append(
                _kpi(share, "PGY-2/3 in Low risk", f"Pass estimate ≥ {int(cutoffs[1] * 100)}% (n = {n})", "tone-low")
            )
            if deid:
                tiles.append(
                    _kpi(
                        sup_count(below),
                        "PGY-2/3 below Low risk",
                        "Counts of 1–4 shown as <5",
                        "tone-high" * bool(below),
                    )
                )
        if not deid:
            k = len(board.watch_list(bt))
            tiles.append(_kpi(str(k), "On the watch list", "PGY-2/3 below Low risk or worsened", "tone-high" * bool(k)))
        pooled = _pooled_change(_paired(ds.wide, deid))
        if pooled:
            tiles.append(
                _kpi(
                    f"{pooled[0]:+.1f}",
                    "Mean percentile change",
                    f"Same residents, last year → this year (n = {pooled[1]})",
                )
            )
        if ds.mksap is not None and "mk_answered" in ds.wide:
            m = stats.mksap_models(ds.wide)
            if m["ok"]:
                clear = "adjusted for last year's ITE" if m["p_vol"] < 0.05 else "not statistically clear"
                tiles.append(_kpi(f"{m['dbl']:+.1f}", "ITE points per MKSAP doubling", f"% correct, {clear}"))
    if program is not None:
        s = pdf_reports.items_summary(program["items"])
        tiles.append(
            _kpi(
                str(s["red"]), "Red-flag items", f"of {s['n']} items (All-PGY gap ≤ −10)", "tone-high" * bool(s["red"])
            )
        )
    return tags.div(*tiles, class_="kpis") if tiles else None


def _how_to_read() -> Tag:
    return tags.div(
        tags.strong("How to read these numbers. "),
        "Percent correct is the share of questions answered correctly; it depends on that year's exam and rises with "
        "training (nationally about 60/67/70% for PGY-1/2/3 in 2026) and drives the ABIM estimate. Percentile ranks a "
        "score against same-PGY U.S. residents that year (50 = middle) and is the better number for comparing years "
        "and classes.",
        class_="box note",
    )


def _board(ds, cutoffs, deid) -> Tag | None:
    if ds is None or ds.wide is None:
        return None
    bt = board.board_table(ds.wide, cutoffs)
    ts = board.tier_summary(bt)
    ch = board.change_summary(bt)
    n, low = _senior_low(bt)
    intro = tags.p(
        f"Low risk = estimated pass probability ≥ {int(cutoffs[1] * 100)}%; High risk < 50%. Estimates "
        "approximate McDonald et al. 2020 (see Methods).",
        class_="note",
    )
    title = "Estimated ABIM pass probability"
    if deid:
        # Complementary suppression: group sizes are known, so a lone "<5" could be recovered by subtraction.
        # Collapse to Below-Low vs Low and show Low as a range whenever Below-Low is suppressed.
        rows = []
        for p in ts.index:
            tot = int(ts.loc[p].sum())
            below = int(ts.loc[p, "High"] + ts.loc[p, "Intermediate"])
            small = 0 < below < SMALL_N
            rows.append(
                [
                    "All" if p == "All" else f"PGY-{p}",
                    "<5" if small else str(below),
                    f"≥{tot - (SMALL_N - 1)}" if small else str(int(ts.loc[p, "Low"])),
                ]
            )
        changes = (
            tags.p("Tier since last year: " + " · ".join(f"{v} {k.lower()}" for k, v in ch.items()), class_="note")
            if not any(0 < v < SMALL_N for v in ch.values())
            else tags.p("Tier changes since last year are omitted because some counts are under 5.", class_="note")
        )
        if n < SMALL_N:
            take = None
        elif 0 < n - low < SMALL_N:
            take = f"At least {n - (SMALL_N - 1)} of {n} PGY-2 and PGY-3 residents are in Low risk."
        else:
            take = f"{low} of {n} PGY-2 and PGY-3 residents are in Low risk."
        head = ["", _badge("Below Low risk", "High"), _badge("Low risk", "Low")]
        return _card("board", title, take, intro, _table(head, rows, num=(1, 2)), changes)

    rows = [
        [
            "All" if p == "All" else f"PGY-{p}",
            *[str(int(ts.loc[p, k])) for k in board.TIERS],
            _tier_bar({k: int(ts.loc[p, k]) for k in board.TIERS}),
        ]
        for p in ts.index
    ]
    head = ["", *[_badge(f"{k} risk", k) for k in board.TIERS], "Distribution"]
    cy = bt.attrs["current_year"]
    wl = board.watch_list(bt)
    take = (
        f"{low} of {n} PGY-2 and PGY-3 residents are in Low risk; {len(wl)} "
        f"{'is' if len(wl) == 1 else 'are'} on the watch list."
        if n
        else None
    )
    watch = (
        _table(
            [
                "Resident",
                "Level",
                "% correct",
                "Percentile",
                "Estimate",
                "Tier",
                "Tier since last year",
                "Points from Low",
            ],
            [
                [
                    r.Name,
                    f"PGY-{int(r.PGY)}",
                    _num(r[f"Pct_{cy}"], 0, "%"),
                    _num(r[f"Ile_{cy}"]),
                    f"{math.floor(100 * r[f'Prob_{cy}'])}%",
                    _badge(r.Tier, r.Tier),
                    r.Tier_change.lower(),
                    _num(r.Gap_Low, 1),
                ]
                for _, r in wl.iterrows()
            ],
            num=(2, 3, 4, 7),
        )
        if len(wl)
        else tags.p("No PGY-2 or PGY-3 resident is below Low risk or has a worsened tier.")
    )
    return _card(
        "board",
        title,
        take,
        tags.div(
            tags.div(
                intro,
                _table(head, rows, num=(1, 2, 3)),
                tags.p("Tier since last year: " + " · ".join(f"{v} {k.lower()}" for k, v in ch.items()), class_="note"),
            ),
            tags.div(_fig(plots.program_nomogram(bt, cutoffs))),
            class_="grid2",
        ),
        tags.h3(f"Watch list (PGY-2 and PGY-3): {len(wl)}"),
        watch,
    )


def _trends(ds, deid) -> Tag | None:
    if ds is None or ds.rosters.long.empty:
        return None
    long = ds.rosters.long
    lv = history.by_level(long)
    shown = _suppress_small(lv, ["ile", "med", "ge50", "lt35", "pc", "pp_low"]) if deid else lv
    years = sorted(lv.Exam_Year.unique())
    rows = []
    for p in sorted(lv.PGY.unique()):
        d = shown[shown.PGY == p].set_index("Exam_Year")
        rows.append(
            [f"PGY-{p}"]
            + [
                (
                    "<5"
                    if deid and d.loc[y, "small_n"]
                    else f"{_num(d.loc[y, 'ile'])} (n={sup_count(d.loc[y, 'n']) if deid else int(d.loc[y, 'n'])})"
                )
                if y in d.index
                else "—"
                for y in years
            ]
        )
    latest = shown[(shown.Exam_Year == years[-1]) & shown.ile.notna()].sort_values("PGY")
    take = (
        f"{years[-1]} mean national percentile: "
        + ", ".join(f"PGY-{int(r.PGY)} {r.ile:.0f}" for r in latest.itertuples())
        + " (50 = national middle)."
        if len(latest)
        else None
    )
    tr = history.class_trajectories(long)
    if deid:
        tr = _suppress_small(tr, ["value", "ile", "pc"])
    mrows = []
    for gc in dict.fromkeys(tr.Grad_Class):
        d = tr[tr.Grad_Class == gc].set_index("PGY")
        cells = []
        for p in (1, 2, 3):
            if p not in d.index:
                cells.append("—")
            elif deid and d.loc[p, "small_n"]:
                cells.append("<5")
            else:
                cells.append(f"{_num(d.loc[p, 'value'])} ({int(d.loc[p, 'n'])}, {int(d.loc[p, 'Exam_Year'])})")
        mrows.append([f"Class of {gc}" + ("" if d.status.iloc[0] == "current" else " (graduated)"), *cells])
    return _card(
        "trends",
        "ITE results over time",
        take,
        tags.h3("Each PGY level across exam years (mean national percentile)"),
        tags.p("Different residents sit in each bar.", class_="note"),
        _fig(plots.level_small_multiples(shown, "ile")),
        _table(["Mean percentile", *[str(y) for y in years]], rows, num=tuple(range(1, len(years) + 1))),
        tags.h3("Each graduating class, PGY-1 → PGY-3"),
        _fig(plots.class_trajectories_figure(tr.dropna(subset=["value"]))),
        _table(["Class", "PGY-1", "PGY-2", "PGY-3"], mrows, num=(1, 2, 3)),
        tags.p("Cells: mean percentile (n, exam year).", class_="note"),
    )


def _yoy(ds, deid) -> Tag | None:
    if ds is None or ds.wide is None:
        return None
    pts = stats.paired_points(ds.wide)
    if pts.empty:
        return None
    cs = _paired(ds.wide, deid)
    rows = []
    for c in cs:
        verdict = "no clear change" if not (c["p"] == c["p"]) or c["p"] >= 0.05 else "likely a real change"
        rows.append(
            [
                f"Now PGY-{c['pgy']}",
                str(c["n"]),
                f"{c['d_ile']:+.1f}",
                f"{c['d_pc']:+.1f}",
                f"{verdict} (p = {c['p']:.3f})",
            ]
        )
    pooled = _pooled_change(cs)
    take = (
        f"Residents tested in both years moved {pooled[0]:+.1f} national percentile points on average "
        f"(n = {pooled[1]})."
        if pooled
        else None
    )
    table = (
        _table(["Group", "n", "Mean percentile change", "Mean % correct change", "Wilcoxon test"], rows, num=(1, 2, 3))
        if rows
        else tags.p("Groups under 5 residents are omitted.", class_="note")
    )
    return _card(
        "yoy",
        "Same residents: last year → this year",
        take,
        table,
        tags.div(_fig(plots.yoy_scatter(pts, "percentile", labels=not deid)), class_="narrow-chart"),
        tags.p(
            "Points above the diagonal improved their percentile." + (" Points are unlabeled." if deid else ""),
            class_="note",
        ),
    )


def _mksap(ds, deid) -> Tag | None:
    if ds is None or ds.mksap is None or ds.wide is None or "mk_answered" not in ds.wide:
        return None
    w = ds.wide
    pr = mksap.progress_by_pgy(w)
    prow = [
        [
            f"PGY-{int(r.PGY)}",
            str(r.n),
            f"{r.med:,.0f} ({r.q1:,.0f}–{r.q3:,.0f})",
            f"{_num(r.bank_pct, 1)}%",
            f"{_num(r.acc, 1)}%",
        ]
        if not (deid and r.n < SMALL_N)
        else [f"PGY-{int(r.PGY)}", "<5", "—", "—", "—"]
        for r in pr.itertuples()
    ]
    m = stats.mksap_models(w)
    body = [
        tags.p(
            f"From the {mksap.KIND_LABEL[ds.mksap.kind]} export (bank of {ds.mksap.bank:,} questions).", class_="note"
        ),
        _table(["Class", "n", "Median questions (IQR)", "% of bank", "Accuracy"], prow, num=(1, 2, 3, 4)),
    ]
    take = None
    if m["ok"]:
        clear = "" if m["p_vol"] < 0.05 else " This association was not statistically clear."
        p_txt = "p < .001" if m["p_vol"] < 0.001 else f"p = {m['p_vol']:.3f}"
        take = (
            f"Each doubling of MKSAP questions went with about {m['dbl']:+.1f} points of ITE percent correct, "
            "after accounting for last year's ITE and PGY level."
        )
        body.append(
            tags.p(
                f"{p_txt}; variance explained {m['r2_base']:.2f} → {m['r2_vol']:.2f} (n = {m['n']}).{clear}",
                class_="note",
            )
        )
        by_pgy, pooled = stats.mksap_thirds(w)
        if deid:
            by_pgy, pooled = by_pgy[by_pgy.n >= SMALL_N], pooled[pooled.n >= SMALL_N]
        body.append(
            tags.div(
                tags.div(_fig(plots.thirds_bar(by_pgy, pooled, "pct"))),
                tags.div(_fig(plots.mksap_scatter(stats.mksap_points(w), "pct", labels=not deid))),
                class_="grid2",
            )
        )
    else:
        body.append(tags.p(m["reason"], class_="note"))
    body.append(
        tags.p(
            "Observational, not causal; the MKSAP export may post-date the ITE; MKSAP editions reset.", class_="note"
        )
    )
    return _card("mksap", "MKSAP", take, *body)


def _gap(v) -> Tag | str:
    return tags.span(f"{v:+d}", class_="gap-bad") if v <= -10 else f"{v:+d}"


def _items(program) -> Tag | None:
    if program is None:
        return None
    it = program["items"]
    s = pdf_reports.items_summary(it)
    flagged = it[it.flag.notna()].assign(_o=lambda d: d.flag.map({"red": 0, "yellow": 1})).sort_values(["_o", "gapA"])
    top = s["by_area"].iloc[0] if len(s["by_area"]) else None
    take = f"{s['red']} red and {s['yellow']} yellow items out of {s['n']}" + (
        f"; the most flagged content area is {top.area}." if top is not None and top.red + top.yellow else "."
    )
    return _card(
        "items",
        "Item-level gaps (ACP Program Performance Report)",
        take,
        tags.p(
            "Red = All-PGY gap ≤ −10 points; yellow = any single-PGY gap ≤ −20. One resident ≈ 4 points at a single "
            "PGY level in a group of ~25: prompts for review, not findings.",
            class_="note",
        ),
        _fig(plots.area_ranks_figure(pdf_reports.area_ranks(program["areas"]))),
        _table(
            ["Flag", "Area", "Objective", "PGY-1 gap", "PGY-2 gap", "PGY-3 gap", "All gap"],
            [
                [
                    _badge(r.flag, r.flag),
                    r.area,
                    r.objective + (" (HVC)" if r.hvc else ""),
                    _gap(r.gap1),
                    _gap(r.gap2),
                    _gap(r.gap3),
                    _gap(r.gapA),
                ]
                for r in flagged.itertuples()
            ],
            num=(3, 4, 5, 6),
        ),
    )


def _methods(deid) -> Tag:
    return _card(
        "methods",
        "Methods and sources",
        None,
        tags.p(
            "ABIM pass estimates are a logistic approximation of the curves in McDonald FS, et al. Correlations "
            "Between the USMLE Step Examinations, American College of Physicians In-Training Examination, and ABIM "
            "Internal Medicine Certification Examination. Acad Med. 2020;95(9):1388–1395. ",
            tags.a("doi:10.1097/ACM.0000000000003382", href=DOI),
            ". Educational use only — not for promotion, remediation or employment decisions.",
        ),
        tags.p(
            "Full methods: ",
            tags.a(f"{REPO}/blob/main/docs/METHODS.md", href=f"{REPO}/blob/main/docs/METHODS.md"),
            class_="note",
        ),
        tags.p(
            "De-identified: no names or IDs; counts of 1–4 and groups under 5 suppressed; points unlabeled.",
            class_="note",
        )
        if deid
        else None,
    )


# ------------------------------------------------------------------------------------------- build
def included_sections(ds, program) -> list[str]:
    out = []
    if ds is not None and ds.wide is not None:
        out += ["ABIM pass estimates", "ITE results over time"]
        if not stats.paired_points(ds.wide).empty:
            out.append("Year over year")
        if ds.mksap is not None and "mk_answered" in ds.wide:
            out.append("MKSAP")
    if program is not None:
        out.append("Item-level gaps")
    return out


def _program_name(ds, program) -> str:
    if program and program.get("program_name"):
        return program["program_name"].title()
    if ds is not None and "Program_Name" in ds.rosters.long:
        names = ds.rosters.long.Program_Name.dropna()
        if len(names):
            return str(names.iloc[0]).title()
    return "Internal Medicine Residency Program"


def build_report(ds, program, deidentified: bool, cutoffs=DEFAULT_CUTOFFS) -> bytes:
    year = (ds.rosters.current_year if ds is not None else None) or (program or {}).get("exam_year") or ""
    title = f"{year} ITE {'Program Summary' if deidentified else 'Program Report'}".strip()
    today = dt.date.today().isoformat()
    notice = (
        tags.div(
            tags.strong("De-identified summary."),
            tags.span("Aggregates only — safe to share within your institution."),
            class_="notice public",
        )
        if deidentified
        else tags.div(
            tags.strong("Confidential."),
            tags.span("Contains resident-identifiable education records. Do not forward."),
            class_="notice confidential",
            role="note",
        )
    )
    sections = [
        _board(ds, cutoffs, deidentified),
        _trends(ds, deidentified),
        _yoy(ds, deidentified),
        _mksap(ds, deidentified),
        _items(program),
    ]
    print_footer = tags.div(
        (
            "De-identified program summary — aggregates only"
            if deidentified
            else "CONFIDENTIAL — contains resident-identifiable education records"
        )
        + f" · {title} · im-ite-analyzer",
        class_="print-footer",
    )
    body = tags.body(
        print_footer,
        tags.header(
            tags.div(
                tags.div(tags.h1(_program_name(ds, program)), tags.p(f"{title} · Generated {today}")),
                tags.button("Print / Save as PDF", class_="print-btn", type="button", onclick="window.print()"),
                class_="wrap",
            ),
            class_="hero",
        ),
        tags.main(
            notice,
            _kpis(ds, program, cutoffs, deidentified),
            _how_to_read(),
            *[s for s in sections if s is not None],
            _methods(deidentified),
            tags.footer(
                f"Generated {today} with im-ite-analyzer · Created by Fred Buckhold (",
                tags.a("ORCID", href=ORCID),
                ") · ",
                tags.a("Source", href=REPO),
                " · IM-ITE® and MKSAP® are registered trademarks of the American College of Physicians; not "
                "affiliated with or endorsed by ACP, ABIM or NBME.",
            ),
            class_="wrap",
        ),
    )
    head = tags.head(
        tags.meta(charset="utf-8"),
        tags.meta(name="viewport", content="width=device-width, initial-scale=1"),
        tags.title(f"{title} — {_program_name(ds, program)}"),
        tags.style(HTML(CSS)),
        tags.script(HTML(plotly.offline.get_plotlyjs())),
    )
    html = "<!doctype html>\n" + str(tags.html(head, body, lang="en"))
    return html.encode("utf-8")


def content_without_library(html: str) -> str:
    """The report minus the embedded plotly.js source (for privacy checks: the library has name-like substrings)."""
    return html.replace(plotly.offline.get_plotlyjs(), "")
