"""im-ite-analyzer — Shiny app entry point.

Run locally:  .venv/bin/shiny run app.py --reload
"""

from __future__ import annotations

from pathlib import Path

from shiny import App, ui

from modules.calculator import calculator_server, calculator_ui
from modules.common import REPO, citation, footer, how_to_read
from modules.program_tabs import classes_server, classes_ui, trends_server, trends_ui, yoy_server, yoy_ui
from modules.resident import resident_server, resident_ui
from modules.upload_align import upload_server, upload_ui

WWW = Path(__file__).parent / "www"


def about_panel():
    return ui.div(
        ui.h3("About this tool"),
        ui.p(
            "im-ite-analyzer helps internal medicine residents and program directors make sense of ACP "
            "In-Training Examination (IM-ITE®) results and MKSAP® question-bank use."
        ),
        ui.tags.ul(
            ui.tags.li(ui.strong("Calculator"), " — estimated chance of passing ABIM from your percent correct."),
            ui.tags.li(
                ui.strong("My ITE report"),
                " — upload your ACP score report for strengths, focus areas and missed objectives.",
            ),
            ui.tags.li(ui.strong("Program data"), " — upload ACP roster files (and MKSAP) to analyze a whole program."),
        ),
        how_to_read(),
        ui.h4("Source of the pass estimate"),
        citation(),
        ui.p(
            "The paper publishes prediction curves by PGY level; this tool uses a logistic fit to those curves. "
            "Full methods and limitations: ",
            ui.a("docs/METHODS.md", href=f"{REPO}/blob/main/docs/METHODS.md", target="_blank", rel="noopener"),
            ".",
        ),
        ui.h4("Intended use"),
        ui.p(
            "Educational use only: to find knowledge gaps and target support while there is time to act. "
            "Not for promotion, remediation, employment or credentialing decisions."
        ),
        ui.h4("Credit and license"),
        ui.p(
            "Created by Fred Buckhold. Open source under the Apache License 2.0 — reuse must keep the author "
            "credit in the NOTICE file. ",
            ui.a("Source code and citation", href=REPO, target="_blank", rel="noopener"),
            ".",
        ),
        class_="about",
    )


app_ui = ui.page_navbar(
    ui.nav_panel("Calculator", calculator_ui("calc"), value="calc"),
    ui.nav_panel("My ITE report", resident_ui("me"), value="me"),
    ui.nav_panel(
        "Program data",
        ui.navset_underline(
            ui.nav_panel("Upload & Align", upload_ui("upload"), value="upload"),
            ui.nav_panel("Trends by level", trends_ui("trends"), value="trends"),
            ui.nav_panel("Classes", classes_ui("classes"), value="classes"),
            ui.nav_panel("Year over year", yoy_ui("yoy"), value="yoy"),
            id="program_nav",
        ),
        value="program",
    ),
    ui.nav_panel("About", about_panel(), value="about"),
    title="IM-ITE Analyzer",
    id="nav",
    header=ui.include_css(WWW / "app.css"),
    footer=footer(),
    window_title="IM-ITE Analyzer",
    lang="en",
    fillable=False,
)


def server(input, output, session):
    calculator_server("calc")
    resident_server("me")
    dataset = upload_server("upload")  # the session dataset every Program data sub-tab reads
    trends_server("trends", dataset=dataset)
    classes_server("classes", dataset=dataset)
    yoy_server("yoy", dataset=dataset)


app = App(app_ui, server)
# Public app: never show raw Python errors (they can echo file contents) — show a generic message instead.
app.sanitize_errors = True
app.sanitize_error_msg = (
    "Something went wrong displaying this section. Please check your file, or report the problem (without "
    "attaching real data) at github.com/fbuckhold3/im-ite-analyzer/issues."
)
