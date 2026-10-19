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
