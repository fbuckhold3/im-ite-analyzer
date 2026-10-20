"""Shared UI pieces: tier badges, explainer box, citation, footer."""

from __future__ import annotations

import math

from shiny import ui

REPO = "https://github.com/fbuckhold3/im-ite-analyzer"
ORCID = "https://orcid.org/0000-0001-9049-3870"
DOI = "https://doi.org/10.1097/ACM.0000000000003382"

TIER_LABEL = {"High": "High risk", "Intermediate": "Intermediate risk", "Low": "Low risk"}


def tier_badge(tier: str | None):
    if not tier:
        return ui.span("—", class_="tier tier-none")
    return ui.span(TIER_LABEL[tier], class_=f"tier tier-{tier.lower()}")


def fmt_prob(p) -> str:
    """Round DOWN so the shown % never contradicts the tier (89.8% must not read as '90%' = Low)."""
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "—"
    return f"{math.floor(100 * p + 1e-9):.0f}%"


def fmt_num(x, digits: int = 0) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:.{digits}f}"


def citation(short: bool = False):
    if short:
        return ui.span(
            "Estimates approximate McDonald et al., ",
            ui.tags.em("Acad Med"),
            " 2020 (",
            ui.a("doi", href=DOI, target="_blank", rel="noopener"),
            ").",
        )
    return ui.p(
        "McDonald FS, Jurich D, Duhigg LM, Paniagua M, Chick D, Wells M, Williams A, Alguire P. "
        "Correlations Between the USMLE Step Examinations, American College of Physicians In-Training "
        "Examination, and ABIM Internal Medicine Certification Examination. ",
        ui.tags.em("Acad Med."),
        " 2020;95(9):1388–1395. ",
        ui.a("doi:10.1097/ACM.0000000000003382", href=DOI, target="_blank", rel="noopener"),
        class_="citation",
    )


def how_to_read():
    return ui.tags.details(
        ui.tags.summary("How to read these numbers"),
        ui.p(
            ui.strong("Percent correct"),
            " is the share of exam questions answered correctly. It depends on how hard that year's exam was "
            "and rises with training (nationally about 60% for PGY-1, 67% for PGY-2 and 70% for PGY-3 in 2026). "
            "The ABIM pass estimate is built on percent correct.",
        ),
        ui.p(
            ui.strong("Percentile"),
            " ranks a score against all U.S. residents at the same PGY level that year (50 = middle). It is the "
            "better number for comparing years and classes. A resident can gain percent correct and still lose "
            "percentile if peers gained more.",
        ),
        class_="explainer",
    )


def privacy_note():
    return ui.div(
        ui.tags.strong("Your files stay private. "),
        "Uploads are processed in memory for this browser session only — never stored, logged or shared — "
        "and are gone when you close the tab. ",
        ui.a("Details", href=f"{REPO}/blob/main/PRIVACY.md", target="_blank", rel="noopener"),
        class_="privacy-note",
        role="note",
    )


def mksap_howto():
    """How a program gets its MKSAP export (kept in step with docs/MKSAP_EXPORT.md)."""
    return ui.tags.details(
        ui.tags.summary("How to get your program's MKSAP export"),
        ui.p(
            "MKSAP exports are available to program administrators, not to individual residents. In the ",
            ui.strong("MKSAP Tracker"),
            ", open the ",
            ui.strong("Members"),
            " page. The export buttons are at the bottom of the page:",
        ),
        ui.tags.ul(
            ui.tags.li(
                ui.strong("Export Overview"),
                " — one row per person (questions completed and correct). "
                "Recommended: small, and enough for every analysis except section coverage.",
            ),
            ui.tags.li(ui.strong("Export Details"), " — one row per person and question. Adds section coverage."),
        ),
        ui.p(
            "Upload the downloaded .csv as is — don't edit or re-save it. Residents who have graduated or left will "
            "appear as unmatched accounts; that's expected.",
            class_="hint",
        ),
        ui.a("Step-by-step guide", href=f"{REPO}/blob/main/docs/MKSAP_EXPORT.md", target="_blank", rel="noopener"),
        class_="explainer",
    )


def message(text: str, kind: str = "info"):
    """Inline status / validation message (kind: info, warning, error)."""
    return ui.div(text, class_=f"msg msg-{kind}", role="alert" if kind == "error" else "status")


def footer():
    return ui.tags.footer(
        ui.div(
            "Created by Fred Buckhold (",
            ui.a("ORCID", href=ORCID, target="_blank", rel="noopener"),
            ") · ",
            ui.a("Source code", href=REPO, target="_blank", rel="noopener"),
            " · Apache-2.0 · ",
            ui.a("Privacy", href=f"{REPO}/blob/main/PRIVACY.md", target="_blank", rel="noopener"),
        ),
        ui.div(citation(short=True)),
        ui.div(
            "Educational use only — not for promotion or remediation decisions. IM-ITE® and MKSAP® are "
            "registered trademarks of the American College of Physicians; this tool is not affiliated with "
            "or endorsed by ACP, ABIM or NBME.",
            class_="fine-print",
        ),
        class_="app-footer",
    )


def trajectory_table(t):
    """Year-by-year table (calculator trajectory or a resident's report history).

    Uses Exam_Year / Percentile / Delta_Percentile columns when present.
    """
    from ite_core.nomogram import tier_change

    if t is None or len(t) < 2:
        return None
    has_year, has_ile = "Exam_Year" in t, "Percentile" in t
    head = ["Year"] if not has_year else ["Exam", "Level"]
    head += ["% correct", "Change"] + (["Percentile", "Change"] if has_ile else [])
    head += ["Pass estimate", "Tier", "Low risk starts at"]
    rows = []
    for r in t.itertuples():
        cells = [f"PGY-{int(r.PGY)}"] if not has_year else [str(int(r.Exam_Year)), f"PGY-{int(r.PGY)}"]
        cells += [f"{fmt_num(r.Pct_Correct)}%", fmt_num(r.Delta_Pct, 0)]
        if has_ile:
            cells += [fmt_num(r.Percentile), fmt_num(r.Delta_Percentile, 0)]
        cells += [fmt_prob(r.Pass_Prob)]
        rows.append(
            ui.tags.tr(
                *[ui.tags.td(c) for c in cells],
                ui.tags.td(tier_badge(r.Risk_Tier)),
                ui.tags.td(f"{fmt_num(r.Pct_Needed_Low, 1)}%"),
            )
        )
    tiers = list(t.Risk_Tier)
    worsened = any(tier_change(a, b) == "Worsened" for a, b in zip(tiers, tiers[1:], strict=False))
    note = (
        ui.p(
            "The tier dropped even though the score may not have: each PGY curve is steeper than the last, so "
            "the same percent correct counts for less later in training. Check the percentile too.",
            class_="hint",
        )
        if worsened
        else None
    )
    return ui.div(
        ui.tags.table(
            ui.tags.thead(ui.tags.tr(*[ui.tags.th(h, scope="col") for h in head])),
            ui.tags.tbody(*rows),
            class_="table table-sm data-table",
        ),
        note,
    )
