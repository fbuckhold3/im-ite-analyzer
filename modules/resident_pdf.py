"""Resident ITE report as a PDF (reportlab + static matplotlib charts). Built in memory; no files written.

Two sources, one layout:
  from_examinee(reports, program=None)  a resident's own ACP Examinee Performance Report(s); with the program's
                                        Performance Report, missed questions are ranked against national results
  from_roster(ds, rid, ...)             the program's roster data (PD view) — no missed objectives or national means

Layout: estimate → board-pass curve with next-year targets → content areas in three colour bands →
biggest misses / notable wins (when available) → all missed objectives by area.
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
from ite_core.nomogram import DEFAULT_CUTOFFS, prob_label

from . import static_charts

INK, SOFT, RULE = colors.HexColor("#1f2328"), colors.HexColor("#57606a"), colors.HexColor("#d8dee4")
TIER_COLOR = {"High": "#b3261e", "Intermediate": "#8a5a00", "Low": "#0b6e4f"}
BAND_INK = {"Strength": "#0b6e4f", "Typical": "#8a5a00", "Focus": "#b3261e"}
BAND_BG = {"Strength": "#dcf3ea", "Typical": "#fff3d6", "Focus": "#fde7e5"}

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_ss["Heading1"], fontSize=17, spaceAfter=2, textColor=INK)
H2 = ParagraphStyle("h2", parent=_ss["Heading2"], fontSize=12.5, spaceBefore=10, spaceAfter=4, textColor=INK)
H3 = ParagraphStyle("h3", parent=_ss["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=2, textColor=INK)
BODY = ParagraphStyle("body", parent=_ss["BodyText"], fontSize=9.5, leading=13, textColor=INK, alignment=TA_LEFT)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8.5, leading=11)
NOTE = ParagraphStyle("note", parent=BODY, fontSize=8, leading=10.5, textColor=SOFT)
BIG = ParagraphStyle("big", parent=BODY, fontSize=26, leading=30, textColor=INK)


def _f(x, digits=0, suffix=""):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:.{digits}f}{suffix}"


def _prob(p):
    return prob_label(p)


def _p(text, style=BODY):
    return Paragraph(text, style)


def _table(rows, widths=None, header=True):
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
def from_examinee(reports: list[dict], cutoffs=DEFAULT_CUTOFFS, program: dict | None = None) -> dict:
    """One resident's parsed Examinee Performance Report(s), oldest first; optional program report for ranking."""
    a = individual.analyze_examinee(reports[-1], cutoffs)
    q = individual.rank_questions(reports[-1], program) if program is not None else None
    return dict(
        summary=a,
        areas=a["areas"],
        history=individual.history(reports, cutoffs),
        missed=a["missed"],
        ranking=q,
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
    summary = dict(
        name=r.Name,
        exam_year=cy,
        pgy=pgy,
        pct_correct=r[f"Pct_{cy}"],
        percentile=r[f"Ile_{cy}"],
        pass_prob=r[f"Prob_{cy}"],
        risk_tier=r.Tier,
        pct_needed_low_now=r.Needed_Low,
        pgy_note=None,
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
        ranking=None,
        source="program ITE rosters",
        prepared_by_program=True,
        mksap=mk,
    )


# ------------------------------------------------------------------------------------- sections
def _bands(areas, width):
    """Three colour bands (50th+, 25th-49th, below 25th), each area with percentile and % correct."""
    keys = ("Strength", "Typical", "Focus")
    cells = []
    for key in keys:
        d = areas[areas.standing == key].sort_values("percentile", ascending=False)
        lines = [f'<font color="{BAND_INK[key]}"><b>{individual.BAND_LABEL[key]}</b></font>']
        for r in d.itertuples():
            n_missed = getattr(r, "n_missed", None)
            extra = f" · {int(n_missed)} missed" if n_missed is not None and pd.notna(n_missed) and n_missed else ""
            lines.append(
                f"<b>{escape(r.area)}</b><br/><font size=8 color='#57606a'>{_f(r.percentile)}th percentile · "
                f"{_f(r.pct_correct)}% correct{extra}</font>"
            )
        if len(lines) == 1:
            lines.append("<font color='#57606a'>None</font>")
        cells.append([_p(x, SMALL) for x in lines])
    t = Table([cells], colWidths=[width / 3] * 3)
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                *[("BACKGROUND", (i, 0), (i, 0), colors.HexColor(BAND_BG[k])) for i, k in enumerate(keys)],
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEAFTER", (0, 0), (1, 0), 3, colors.white),
            ]
        )
    )
    return t


def _ranked(q, width):
    def rows(df, ink):
        out = [["", "Objective", "Content area", f"National ({q['pgy_label']})"]]
        for i, r in enumerate(df.itertuples(), 1):
            hvc = " <font color='#0b5cad'>(HVC)</font>" if r.hvc else ""
            out.append(
                [
                    str(i),
                    _p(escape(r.objective) + hvc, SMALL),
                    _p(f"<font size=7.5 color='#57606a'>{escape(r.area)}</font>", SMALL),
                    _p(f'<font color="{ink}"><b>{int(r.national)}%</b></font> got it right', SMALL),
                ]
            )
        t = _table(out, widths=[0.25 * inch, width * 0.55, width * 0.22, width * 0.23 - 0.25 * inch])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    return [
        _p("Your questions compared with national results", H2),
        _p(
            f"Biggest misses ({len(q['misses'])}) — questions you missed that most residents at your level got "
            "right; usually the most fixable gaps.",
            H3,
        ),
        rows(q["misses"], "#b3261e"),
        Spacer(1, 4),
        _p(f"Notable wins ({len(q['wins'])}) — the hardest questions you got right.", H3),
        rows(q["wins"], "#0b6e4f"),
        _p(
            f"Matched {q['matched']} of {q['missed_total']} missed objectives to the program's Performance Report.",
            NOTE,
        ),
    ]


# ----------------------------------------------------------------------------------------- build
def resident_pdf(content: dict, cutoffs=DEFAULT_CUTOFFS) -> bytes:
    s, areas, hist, missed = content["summary"], content["areas"], content["history"], content["missed"]
    width = letter[0] - 1.4 * inch
    pgy = int(s["pgy"])
    story = [
        _p(f"{escape(str(s.get('name') or 'Resident'))}", H1),
        _p(
            f"{s.get('exam_year') or ''} ACP Internal Medicine In-Training Examination · PGY-{pgy} · "
            f"from the {escape(content['source'])}",
            NOTE,
        ),
    ]
    if content["prepared_by_program"]:
        story.append(_p("Prepared by the residency program from its ITE roster files.", NOTE))
    story.append(Spacer(1, 6))

    # 1 · Estimate + curve with next-year targets
    tier = s.get("risk_tier")
    tier_txt = f'<font color="{TIER_COLOR.get(tier, "#57606a")}"><b>{tier} risk</b></font>' if tier else "—"
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
                ],
            ]
        ],
        colWidths=[width * 0.5, width * 0.5],
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
    targets = individual.next_year_targets(pgy, cutoffs)
    if targets:
        target_par = _p(individual.target_sentence(s.get("pct_correct"), targets), BODY)
    else:
        target_par = _p(
            f"Low risk at PGY-{min(pgy, 3)} starts at about {_f(s.get('pct_needed_low_now'), 1)}% correct.", BODY
        )
    pts = list(zip(hist.PGY, hist.Pct_Correct, hist.Pass_Prob, strict=True)) if hist is not None else []
    story += [
        _p("Board-pass estimate", H2),
        est,
        Spacer(1, 4),
        target_par,
        Image(
            io.BytesIO(static_charts.nomogram_png(pts, cutoffs, targets=targets)),
            width=width * 0.82,
            height=width * 0.82 * 3.2 / 6.0,
        ),
        _p(
            "Stars mark the score needed at each later PGY level to reach the Low-risk cutoff. Estimates approximate "
            "McDonald FS, et al. <i>Acad Med.</i> 2020;95(9):1388–1395 (doi:10.1097/ACM.0000000000003382): "
            "ITE 2014–15 / ABIM 2015–18 cohorts, percent correct only, a population-level association — not a "
            "prediction for any one person. Estimates are shown rounded down to the nearest 5%. Educational use only.",
            NOTE,
        ),
    ]
    if hist is not None and len(hist) > 1:
        rows = [["Exam", "Level", "% correct", "Percentile", "Pass estimate", "Tier"]]
        rows += [
            [
                str(int(r.Exam_Year)) if pd.notna(r.Exam_Year) else "—",
                f"PGY-{int(r.PGY)}",
                f"{_f(r.Pct_Correct)}%",
                _f(r.Percentile),
                _prob(r.Pass_Prob),
                r.Risk_Tier or "—",
            ]
            for r in hist.itertuples()
        ]
        story.append(_table(rows))
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

    # 2 · Content areas in colour bands
    if areas is not None and len(areas):
        hvc = (s.get("hvc") or [None])[0]
        hvc_txt = (
            f"High Value Care (overlaps the areas above): {hvc['percentile']}th percentile, "
            f"{hvc['pct_correct']}% correct. "
            if hvc
            else ""
        )
        story.append(
            KeepTogether(
                [
                    _p("Content areas: your national percentile", H2),
                    _bands(areas, width),
                    _p(
                        hvc_txt
                        + "Percentile = rank among U.S. residents at the same PGY level that year (50 = middle).",
                        NOTE,
                    ),
                ]
            )
        )
    else:
        story.append(_p("Content-area percentiles are not available from this roster (older ACP layout).", NOTE))

    # 3 · Ranked questions
    if content.get("ranking"):
        story += _ranked(content["ranking"], width)

    # 4 · All missed objectives
    if missed is not None and len(missed):
        band = areas.set_index("area").standing if areas is not None else pd.Series(dtype=str)
        story += [
            _p(f"All missed objectives ({len(missed)})", H2),
            _p(
                "ACP lists the learning objective behind each question you missed — not the question itself. "
                "Weakest areas first. (HVC) = also counts toward High Value Care.",
                NOTE,
            ),
        ]
        order = sorted(missed.area.unique(), key=lambda a: (individual.BAND_ORDER.get(band.get(a), 1), a))
        for area in order:
            g = missed[missed.area == area]
            key = band.get(area)
            items = "".join(
                f"• {escape(o)}{' (HVC)' if h else ''}<br/>" for o, h in zip(g.objective, g.hvc, strict=True)
            )
            head = f"<b>{escape(area)}</b> — {len(g)} missed"
            if key:
                head += f' · <font color="{BAND_INK[key]}">{individual.BAND_LABEL[key]}</font>'
            story.append(KeepTogether([_p(head, BODY), _p(items, SMALL), Spacer(1, 3)]))
    elif content["prepared_by_program"]:
        story.append(
            _p("Missed objectives come from the resident's own ACP score report and are not in the roster files.", NOTE)
        )

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
