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
import plotly.offline
from htmltools import HTML, Tag, TagList, tags

from ite_core import board, history, mksap, pdf_reports, stats
from ite_core.history import SMALL_N
from ite_core.nomogram import DEFAULT_CUTOFFS

from . import plots
from .common import DOI, ORCID, REPO

CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#1f2328;max-width:1100px;margin:0 auto;padding:24px;}
h1{font-size:1.6rem;margin-bottom:.2rem} h2{font-size:1.25rem;margin-top:2rem;border-bottom:2px solid #d8dee4;
padding-bottom:.3rem} h3{font-size:1rem;margin-top:1.2rem} .sub{color:#57606a} .banner{padding:.6rem .9rem;
border-radius:6px;margin:1rem 0;font-weight:600} .confidential{background:#fde7e5;border-left:4px solid #b3261e}
.public{background:#dcf3ea;border-left:4px solid #0b6e4f} table{border-collapse:collapse;margin:.5rem 0 1rem;
font-variant-numeric:tabular-nums} th,td{border-bottom:1px solid #d8dee4;padding:.3rem .6rem;text-align:left}
th{color:#57606a;font-weight:600} .note{color:#57606a;font-size:.9rem} .box{border:1px solid #d8dee4;
border-radius:6px;padding:.6rem .9rem;margin:.8rem 0} footer{margin-top:2.5rem;border-top:1px solid #d8dee4;
padding-top:.8rem;color:#57606a;font-size:.85rem}
.print-btn{float:right;font:inherit;font-size:.9rem;padding:.35rem .8rem;border:1px solid #0b5cad;
color:#0b5cad;background:#fff;border-radius:6px;cursor:pointer} .print-footer{display:none}
@page{size:letter;margin:0.6in 0.6in 0.7in}
@media print{body{max-width:none;padding:0;font-size:10.5pt}
.print-btn,.modebar,.modebar-container{display:none!important} h2{break-before:page;margin-top:0}
h2:first-of-type{break-before:auto} table,.plotly-graph-div,.box{break-inside:avoid}
.plotly-graph-div{max-width:100%!important} .print-footer{display:block;position:fixed;bottom:0;left:0;
right:0;font-size:7.5pt;color:#57606a;border-top:1px solid #d8dee4;padding-top:2pt}}

"""


# ----------------------------------------------------------------------------------------- helpers
def _fig(fig) -> HTML:
    return HTML(
        fig.to_html(
            full_html=False,
            include_plotlyjs=False,
            config={"displaylogo": False, "showSendToCloud": False},
        )
    )


def _num(x, digits=0, suffix=""):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{digits}f}{suffix}"


def sup_count(k) -> str:
    """Small-cell suppression for counts in de-identified output."""
    k = int(k)
    return "<5" if 0 < k < SMALL_N else str(k)


def _table(head, rows, **attrs) -> Tag:
    return tags.table(
        tags.thead(tags.tr(*[tags.th(h) for h in head])),
        tags.tbody(*[tags.tr(*[tags.td(c) for c in r]) for r in rows]),
        **attrs,
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
def _board(ds, cutoffs, deid) -> TagList | None:
    if ds is None or ds.wide is None:
        return None
    bt = board.board_table(ds.wide, cutoffs)
    ts = board.tier_summary(bt)
    ch = board.change_summary(bt)
    intro = tags.p(
        f"Low risk = estimated pass probability ≥ {int(cutoffs[1] * 100)}%; High risk < 50%. Estimates "
        "approximate McDonald et al. 2020 (see Methods).",
        class_="note",
    )
    if deid:
        # Complementary suppression: group sizes are known, so a lone "<5" could be recovered by subtraction.
        # Collapse to Below-Low vs Low and show Low as a range whenever Below-Low is suppressed.
        rows = []
        for p in ts.index:
            n = int(ts.loc[p].sum())
            below = int(ts.loc[p, "High"] + ts.loc[p, "Intermediate"])
            low = int(ts.loc[p, "Low"])
            small = 0 < below < SMALL_N
            rows.append(
                [
                    "All" if p == "All" else f"PGY-{p}",
                    "<5" if small else str(below),
                    f"≥{n - (SMALL_N - 1)}" if small else str(low),
                ]
            )
        changes = (
            tags.p("Tier since last year: " + " · ".join(f"{v} {k.lower()}" for k, v in ch.items()), class_="note")
            if not any(0 < v < SMALL_N for v in ch.values())
            else tags.p("Tier changes since last year are omitted because some counts are under 5.", class_="note")
        )
        parts = [
            tags.h2("Estimated ABIM pass probability"),
            intro,
            _table(["", "Below Low risk", "Low risk"], rows),
            changes,
        ]
    else:
        rows = [["All" if p == "All" else f"PGY-{p}", *[str(int(ts.loc[p, k])) for k in board.TIERS]] for p in ts.index]
        parts = [
            tags.h2("Estimated ABIM pass probability"),
            intro,
            _table(["", "High risk", "Intermediate risk", "Low risk"], rows),
            tags.p("Tier since last year: " + " · ".join(f"{v} {k.lower()}" for k, v in ch.items()), class_="note"),
        ]
    if not deid:
        cy = bt.attrs["current_year"]
        wl = board.watch_list(bt)
        parts += [_fig(plots.program_nomogram(bt, cutoffs)), tags.h3(f"Watch list (PGY-2 and PGY-3): {len(wl)}")]
        parts.append(
            _table(
                [
                    "Resident",
                    "Level",
                    "% correct",
                    "Percentile",
                    "Estimate",
                    "Tier",
                    "Tier since last year",
                    "Points from Low risk",
                ],
                [
                    [
                        r.Name,
                        f"PGY-{int(r.PGY)}",
                        _num(r[f"Pct_{cy}"], 0, "%"),
                        _num(r[f"Ile_{cy}"]),
                        f"{math.floor(100 * r[f'Prob_{cy}'])}%",
                        r.Tier,
                        r.Tier_change.lower(),
                        _num(r.Gap_Low, 1),
                    ]
                    for _, r in wl.iterrows()
                ],
            )
            if len(wl)
            else tags.p("No PGY-2 or PGY-3 resident is below Low risk or has a worsened tier.")
        )
    return TagList(*parts)


def _trends(ds, deid) -> TagList | None:
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
    return TagList(
        tags.h2("ITE results over time"),
        tags.h3("Each PGY level across exam years (mean national percentile)"),
        tags.p("Different residents sit in each bar.", class_="note"),
        _fig(plots.level_small_multiples(shown, "ile")),
        _table(["Mean percentile", *[str(y) for y in years]], rows),
        tags.h3("Each graduating class, PGY-1 → PGY-3"),
        _fig(plots.class_trajectories_figure(tr.dropna(subset=["value"]))),
        _table(["Class", "PGY-1", "PGY-2", "PGY-3"], mrows),
        tags.p("Cells: mean percentile (n, exam year).", class_="note"),
    )


def _yoy(ds, deid) -> TagList | None:
    if ds is None or ds.wide is None:
        return None
    pts = stats.paired_points(ds.wide)
    if pts.empty:
        return None
    rows = []
    for p in (2, 3):
        c = stats.paired_change(ds.wide, p)
        if c["n"] == 0 or (deid and c["n"] < SMALL_N):
            continue
        verdict = "no clear change" if not (c["p"] == c["p"]) or c["p"] >= 0.05 else "likely a real change"
        rows.append(
            [f"Now PGY-{p}", str(c["n"]), f"{c['d_ile']:+.1f}", f"{c['d_pc']:+.1f}", f"{verdict} (p = {c['p']:.3f})"]
        )
    return TagList(
        tags.h2("Same residents: last year → this year"),
        _table(["Group", "n", "Mean percentile change", "Mean % correct change", "Wilcoxon test"], rows),
        _fig(plots.yoy_scatter(pts, "percentile", labels=not deid)),
        tags.p(
            "Points above the diagonal improved their percentile." + (" Points are unlabeled." if deid else ""),
            class_="note",
        ),
    )


def _mksap(ds, deid) -> TagList | None:
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
    parts = [
        tags.h2("MKSAP"),
        tags.p(
            f"From the {mksap.KIND_LABEL[ds.mksap.kind]} export (bank of {ds.mksap.bank:,} questions).", class_="note"
        ),
        _table(["Class", "n", "Median questions (IQR)", "% of bank", "Accuracy"], prow),
    ]
    if m["ok"]:
        clear = "" if m["p_vol"] < 0.05 else " This association was not statistically clear."
        p_txt = "p < .001" if m["p_vol"] < 0.001 else f"p = {m['p_vol']:.3f}"
        parts.append(
            tags.p(
                f"After accounting for last year's ITE and PGY level, each doubling of MKSAP questions went with about "
                f"{m['dbl']:+.1f} points of ITE percent correct ({p_txt}); variance explained {m['r2_base']:.2f} → "
                f"{m['r2_vol']:.2f} (n = {m['n']}).{clear}"
            )
        )
        by_pgy, pooled = stats.mksap_thirds(w)
        if deid:
            by_pgy, pooled = by_pgy[by_pgy.n >= SMALL_N], pooled[pooled.n >= SMALL_N]
        parts += [
            _fig(plots.thirds_bar(by_pgy, pooled, "pct")),
            _fig(plots.mksap_scatter(stats.mksap_points(w), "pct", labels=not deid)),
        ]
    else:
        parts.append(tags.p(m["reason"], class_="note"))
    parts.append(
        tags.p(
            "Observational, not causal; the MKSAP export may post-date the ITE; MKSAP editions reset.", class_="note"
        )
    )
    return TagList(*parts)


def _items(program) -> TagList | None:
    if program is None:
        return None
    it = program["items"]
    s = pdf_reports.items_summary(it)
    flagged = it[it.flag.notna()].assign(_o=lambda d: d.flag.map({"red": 0, "yellow": 1})).sort_values(["_o", "gapA"])
    return TagList(
        tags.h2("Item-level gaps (ACP Program Performance Report)"),
        tags.p(
            f"{s['red']} red (All-PGY gap ≤ −10 points) and {s['yellow']} yellow (any single-PGY gap ≤ −20) of "
            f"{s['n']} items. One resident ≈ 4 points at a single PGY level in a group of ~25: prompts for review, "
            "not findings."
        ),
        _fig(plots.area_ranks_figure(pdf_reports.area_ranks(program["areas"]))),
        _table(
            ["Flag", "Area", "Objective", "PGY-1 gap", "PGY-2 gap", "PGY-3 gap", "All gap"],
            [
                [
                    r.flag,
                    r.area,
                    r.objective + (" (HVC)" if r.hvc else ""),
                    f"{r.gap1:+d}",
                    f"{r.gap2:+d}",
                    f"{r.gap3:+d}",
                    f"{r.gapA:+d}",
                ]
                for r in flagged.itertuples()
            ],
        ),
    )


def _methods(deid) -> Tag:
    return tags.div(
        tags.h2("Methods and sources"),
        tags.p(
            "ABIM pass estimates are a logistic approximation of the curves in McDonald FS, et al. Correlations "
            "Between the USMLE Step Examinations, American College of Physicians In-Training Examination, and ABIM "
            "Internal Medicine Certification Examination. Acad Med. 2020;95(9):1388–1395. ",
            tags.a("doi:10.1097/ACM.0000000000003382", href=DOI),
            ". Educational use only — not for promotion, remediation or employment decisions.",
        ),
        tags.p(f"Full methods: {REPO}/blob/main/docs/METHODS.md", class_="note"),
        tags.p(
            "De-identified: no names or IDs; counts of 1–4 and groups under 5 suppressed; points unlabeled."
            if deid
            else "",
            class_="note",
        ),
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
    banner = (
        tags.div(
            "De-identified program summary — aggregates only, safe to share within your institution.",
            class_="banner public",
        )
        if deidentified
        else tags.div(
            "Confidential: contains resident-identifiable education records. Do not forward.",
            class_="banner confidential",
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
        tags.button("Print / Save as PDF", class_="print-btn", onclick="window.print()"),
        tags.h1(title),
        tags.p(_program_name(ds, program), class_="sub"),
        banner,
        _how_to_read(),
        *[s for s in sections if s is not None],
        _methods(deidentified),
        tags.footer(
            f"Generated {dt.date.today().isoformat()} with im-ite-analyzer · Created by Fred Buckhold (",
            tags.a("ORCID", href=ORCID),
            ") · ",
            tags.a("Source", href=REPO),
            " · IM-ITE® and MKSAP® are registered trademarks of the American College of Physicians; not affiliated "
            "with or endorsed by ACP, ABIM or NBME.",
        ),
    )
    head = tags.head(
        tags.meta(charset="utf-8"),
        tags.meta(name="viewport", content="width=device-width, initial-scale=1"),
        tags.title(title),
        tags.style(HTML(CSS)),
        tags.script(HTML(plotly.offline.get_plotlyjs())),
    )
    html = "<!doctype html>\n" + str(tags.html(head, body, lang="en"))
    return html.encode("utf-8")


def content_without_library(html: str) -> str:
    """The report minus the embedded plotly.js source (for privacy checks: the library has name-like substrings)."""
    return html.replace(plotly.offline.get_plotlyjs(), "")
