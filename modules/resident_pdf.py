"""Resident ITE report as a PDF (reportlab + static matplotlib charts). Built in memory; no files written.

Two sources, one layout:
  from_examinee(reports)      a resident's own ACP Examinee Performance Report(s) — full content
  from_roster(ds, rid, ...)   the program's roster data (PD view) — no missed objectives or national means
"""

from __future__ import annotations

import datetime as dt
import io
import math
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ite_core import board, individual
from ite_core.nomogram import DEFAULT_CUTOFFS, pct_for_prob

from . import static_charts

INK, SOFT, RULE = colors.HexColor("#1f2328"), colors.HexColor("#57606a"), colors.HexColor("#d8dee4")
TIER_COLOR = {"High": "#b3261e", "Intermediate": "#8a5a00", "Low": "#0b6e4f"}
STANDING_COLOR = {"Strength": "#0b6e4f", "Focus": "#b3261e", "Typical": "#57606a"}
STRENGTH_AT, FOCUS_BELOW = individual.STRENGTH_AT, individual.FOCUS_BELOW

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_ss["Heading1"], fontSize=17, spaceAfter=2, textColor=INK)
H2 = ParagraphStyle("h2", parent=_ss["Heading2"], fontSize=12.5, spaceBefore=10, spaceAfter=4, textColor=INK)
BODY = ParagraphStyle("body", parent=_ss["BodyText"], fontSize=9.5, leading=13, textColor=INK, alignment=TA_LEFT)
NOTE = ParagraphStyle("note", parent=BODY, fontSize=8, leading=10.5, textColor=SOFT)
BIG = ParagraphStyle("big", parent=BODY, fontSize=26, leading=30, textColor=INK)


def _f(x, digits=0, suffix=""):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:.{digits}f}{suffix}"


def _prob(p):
    return "—" if p is None or (isinstance(p, float) and math.isnan(p)) else f"{math.floor(100 * p + 1e-9):.0f}%"


def _p(text, style=BODY):
    return Paragraph(text, style)


def _table(rows, widths, header=True, zebra=False):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
    ]
    if header:
        style += [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (-1, 0), SOFT),
            ("LINEBELOW", (0, 0), (-1, 0), 0.9, SOFT),
        ]
    t.setStyle(TableStyle(style))
    return t


# ------------------------------------------------------------------------------------- adapters
def from_examinee(reports: list[dict], cutoffs=DEFAULT_CUTOFFS) -> dict:
    """One resident's parsed Examinee Performance Report(s), oldest first."""
    a = individual.analyze_examinee(reports[-1], cutoffs)
    return dict(
        summary=a,
        areas=a["areas"],
        history=individual.history(reports, cutoffs),
        missed=a["missed"],
        source="ACP Examinee Performance Report",
        prepared_by_program=False,
        mksap=None,
    )


def from_roster(ds, rid: str, cutoffs=DEFAULT_CUTOFFS) -> dict:
    """PD view: built from the program's roster files (and MKSAP export, if loaded)."""
    bt = board.board_table(ds.wide, cutoffs)
    r = bt[bt.ID == rid].iloc[0]
    cy, pgy = bt.attrs["current_year"], int(r.PGY)
    areas = board.resident_areas(ds.rosters.long, rid)
    if areas is not None:
        areas = areas.assign(national_sd=float("nan"))
    strengths = [] if areas is None else areas[areas.standing == "Strength"].area.tolist()
    focus = [] if areas is None else areas[areas.standing == "Focus"].area.tolist()
    if areas is not None and not focus:
        focus = areas.sort_values("percentile").head(2).area.tolist()
    summary = dict(
        name=r.Name,
        exam_year=cy,
        pgy=pgy,
        pct_correct=r[f"Pct_{cy}"],
        percentile=r[f"Ile_{cy}"],
        pass_prob=r[f"Prob_{cy}"],
        risk_tier=r.Tier,
        pct_needed_low_now=r.Needed_Low,
        pct_needed_low_next=round(pct_for_prob(cutoffs[1], pgy + 1), 1) if pgy < 3 else None,
        pgy_note=None,
        strengths=strengths,
        focus_areas=focus,
        hvc=[],
    )
    mk = None
    if "mk_answered" in bt and pd.notna(r.get("mk_answered")):
        mk = dict(answered=int(r.mk_answered), pct_correct=r.mk_pct_correct)
    return dict(
        summary=summary,
        areas=areas,
        history=board.resident_history(ds.rosters.long, rid, cutoffs),
        missed=None,
        source="program ITE rosters",
        prepared_by_program=True,
        mksap=mk,
    )


# ----------------------------------------------------------------------------------------- build
def resident_pdf(content: dict, cutoffs=DEFAULT_CUTOFFS) -> bytes:
    s, areas, hist, missed = content["summary"], content["areas"], content["history"], content["missed"]
    width = letter[0] - 1.4 * inch
    story = [
        _p(f"{escape(str(s.get('name') or 'Resident'))}", H1),
        _p(
            f"{s.get('exam_year') or ''} ACP Internal Medicine In-Training Examination · PGY-{s['pgy']} · "
            f"from the {escape(content['source'])}",
            NOTE,
        ),
    ]
    if content["prepared_by_program"]:
        story.append(_p("Prepared by the residency program from its ITE roster files.", NOTE))
    story.append(Spacer(1, 8))

    # 1 · Board-pass estimate
    tier = s.get("risk_tier")
    tier_txt = f'<font color="{TIER_COLOR.get(tier, "#57606a")}"><b>{tier} risk</b></font>' if tier else "—"
    nxt = (
        f" Next year (PGY-{s['pgy'] + 1}) it takes about {_f(s['pct_needed_low_next'], 1)}%."
        if s.get("pct_needed_low_next")
        else ""
    )
    est = Table(
        [
            [
                [
                    _p(_prob(s.get("pass_prob")), BIG),
                    _p("estimated chance of passing ABIM on the first attempt", NOTE),
                    _p(tier_txt),
                ],
                [
                    _p(f"<b>{_f(s.get('pct_correct'))}%</b> correct", BODY),
                    _p(f"National percentile <b>{_f(s.get('percentile'))}</b>", BODY),
                    _p(
                        f"Low risk at PGY-{min(s['pgy'], 3)} starts at about "
                        f"{_f(s.get('pct_needed_low_now'), 1)}% correct.{nxt}",
                        NOTE,
                    ),
                ],
            ]
        ],
        colWidths=[width * 0.42, width * 0.58],
    )
    est.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.6, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story += [
        _p("Board-pass estimate", H2),
        est,
        Spacer(1, 3),
        _p(
            "Approximates the curves in McDonald FS, et al. <i>Acad Med.</i> 2020;95(9):1388–1395 "
            "(doi:10.1097/ACM.0000000000003382): 2014–2015 cohorts, percent correct only, a population-level "
            "association — not a prediction for any one person. Educational use only.",
            NOTE,
        ),
    ]
    if s.get("pgy_note"):
        story.append(_p(escape(s["pgy_note"]), NOTE))
    if content.get("mksap"):
        m = content["mksap"]
        story.append(
            _p(
                f"MKSAP (program export): {m['answered']:,} questions answered, {_f(m['pct_correct'], 1)}% correct.",
                NOTE,
            )
        )

    # 2 · Content areas
    if areas is not None and len(areas):
        strengths = ", ".join(s.get("strengths") or []) or f"none at or above the {STRENGTH_AT}th percentile"
        story += [
            _p("Content areas: your national percentile", H2),
            _p(
                f"<b>Strengths:</b> {escape(strengths)}<br/><b>Focus areas:</b> "
                f"{escape(', '.join(s.get('focus_areas') or []))}",
                BODY,
            ),
            Image(
                io.BytesIO(static_charts.area_percentile_png(areas)),
                width=width,
                height=width * (0.25 * len(areas) + 0.8) / 7.0,
            ),
        ]
        has_nat = "national_mean" in areas and areas.national_mean.notna().any()
        head = ["Content area", "You", *(["National mean", "SD"] if has_nat else []), "Percentile", "Standing"]
        if "n_missed" in areas:
            head.append("Missed")
        rows = [head]
        for r in areas.itertuples():
            row = [r.area, f"{_f(r.pct_correct)}%"]
            if has_nat:
                row += [f"{_f(r.national_mean)}%", _f(r.national_sd)]
            row += [_f(r.percentile), r.standing]
            if "n_missed" in areas:
                row.append(str(int(r.n_missed)))
            rows.append(row)
        t = _table(rows, None)
        t.setStyle(
            TableStyle(
                [
                    (
                        "TEXTCOLOR",
                        (head.index("Standing"), i),
                        (head.index("Standing"), i),
                        colors.HexColor(STANDING_COLOR[rows[i][head.index("Standing")]]),
                    )
                    for i in range(1, len(rows))
                ]
            )
        )
        story += [  # the table may continue onto the next page (header row repeats)
            t,
            _p(
                f"Strength = {STRENGTH_AT}th percentile or above; Focus = below the "
                f"{FOCUS_BELOW}th (or the two lowest areas).",
                NOTE,
            ),
        ]
        if s.get("hvc"):
            h = s["hvc"][0]
            story.append(
                _p(
                    f"High Value Care (overlaps the areas above): {h['pct_correct']}% correct, "
                    f"{h['percentile']}th percentile.",
                    NOTE,
                )
            )
    else:
        story.append(_p("Content-area percentiles are not available from this roster (older ACP layout).", NOTE))

    # 3 · Over time
    if hist is not None and len(hist):
        rows = [["Exam", "Level", "% correct", "Percentile", "Pass estimate", "Tier"]]
        for r in hist.itertuples():
            rows.append(
                [
                    str(int(r.Exam_Year)) if pd.notna(r.Exam_Year) else "—",
                    f"PGY-{int(r.PGY)}",
                    f"{_f(r.Pct_Correct)}%",
                    _f(r.Percentile),
                    _prob(r.Pass_Prob),
                    r.Risk_Tier or "—",
                ]
            )
        story.append(
            KeepTogether(
                [
                    _p("Over time" if len(hist) > 1 else "On the board-pass curves", H2),
                    Image(
                        io.BytesIO(
                            static_charts.nomogram_png(
                                list(zip(hist.PGY, hist.Pct_Correct, hist.Pass_Prob, strict=True)), cutoffs
                            )
                        ),
                        width=width * 0.85,
                        height=width * 0.85 * 3.2 / 6.0,
                    ),
                    _table(rows, None),
                ]
            )
        )

    # 4 · Missed objectives
    if missed is not None:
        story += [
            Spacer(1, 6),
            _p(f"Missed objectives ({len(missed)})", H2),
            _p(
                "ACP lists the learning objective behind each item you missed — not the question itself. Focus "
                "areas first. (HVC) = also counts toward High Value Care.",
                NOTE,
            ),
        ]
        standing = areas.set_index("area").standing if areas is not None else pd.Series(dtype=str)
        order = sorted(
            missed.area.unique(), key=lambda a: ({"Focus": 0, "Typical": 1, "Strength": 2}.get(standing.get(a), 1), a)
        )
        for area in order:
            g = missed[missed.area == area]
            items = "".join(
                f"• {escape(o)}{' (HVC)' if h else ''}<br/>" for o, h in zip(g.objective, g.hvc, strict=True)
            )
            story.append(
                KeepTogether(
                    [
                        _p(
                            f"<b>{escape(area)}</b> — {len(g)} missed"
                            + (f" · {standing.get(area)}" if standing.get(area) in ("Focus", "Strength") else ""),
                            BODY,
                        ),
                        _p(items, BODY),
                        Spacer(1, 4),
                    ]
                )
            )
    elif content["prepared_by_program"]:
        story.append(
            _p("Missed objectives come from the resident's own ACP score report and are not in the roster files.", NOTE)
        )

    # Sources
    generated = dt.date.today().isoformat()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(SOFT)
        left = 0.7 * inch
        canvas.drawString(
            left, 0.52 * inch, f"Confidential education record · generated {generated} with im-ite-analyzer"
        )
        canvas.drawString(
            left,
            0.38 * inch,
            "Created by Fred Buckhold · IM-ITE® is a registered trademark of the "
            "American College of Physicians; not affiliated with or endorsed by ACP.",
        )
        canvas.drawRightString(letter[0] - 0.7 * inch, 0.52 * inch, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.75 * inch,
        title=f"ITE report — {s.get('name') or 'Resident'}",
        author="im-ite-analyzer",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def pdf_filename(content: dict) -> str:
    s = content["summary"]
    name = "".join(ch if ch.isalnum() else "_" for ch in str(s.get("name") or "resident")).strip("_")
    return f"ITE{s.get('exam_year') or ''}_{name}.pdf"
