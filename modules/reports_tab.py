"""Program data → Reports: download the identified PD report or the de-identified program summary."""

from __future__ import annotations

from shiny import module, reactive, render, ui

from . import data_export, report_builder
from .common import message

LOW_CUTOFFS = {"0.90": "90% (default)", "0.80": "80%", "0.75": "75%"}


@module.ui
def reports_ui():
    return ui.layout_columns(
        ui.card(
            ui.card_header("Identified PD report"),
            ui.p(
                "Everything in the app for your program, including resident names, the watch list and individual "
                "points on the charts. For the program director and CCC only."
            ),
            ui.div("Confidential: contains resident-identifiable education records.", class_="msg msg-error"),
            ui.download_button("identified", "Download PD report (.html)", class_="btn-primary"),
            ui.hr(),
            ui.p(
                ui.strong("All data (.xlsx)"),
                " — every table the app computes in one workbook (residents, every "
                "exam with content areas, by level, by class, year over year, MKSAP, item gaps, crosswalk) for your "
                "own analysis or records. Also identified.",
                class_="hint",
            ),
            ui.output_ui("sheets"),
            ui.download_button("workbook", "Download all data (.xlsx)", class_="btn-outline-primary"),
        ),
        ui.card(
            ui.card_header("De-identified program summary"),
            ui.p(
                "Aggregates only, for sharing with faculty or leadership: no names or IDs, no individual tiers, "
                "unlabeled points, and any group smaller than 5 suppressed."
            ),
            ui.div(
                "Safe to share within your institution — still review before sending outside it.", class_="msg msg-info"
            ),
            ui.download_button("deidentified", "Download program summary (.html)", class_="btn-outline-primary"),
        ),
        ui.card(
            ui.card_header("What will be included"),
            ui.output_ui("contents"),
            ui.input_select("low_cut", "“Low risk” starts at", LOW_CUTOFFS),
            ui.p(
                "Reports are self-contained HTML files (about 5 MB) that open offline in any browser; charts stay "
                "interactive. Use the browser's Print to save a PDF.",
                class_="hint",
            ),
        ),
        col_widths=(4, 4, 4),
    )


@module.server
def reports_server(input, output, session, dataset, program):
    @reactive.calc
    def cutoffs():
        return (0.50, float(input.low_cut()))

    @reactive.calc
    def sections():
        return report_builder.included_sections(dataset(), program())

    @render.ui
    def contents():
        s = sections()
        if not s:
            return message(
                "Upload rosters, an MKSAP export and/or the Program Performance Report on Upload & Align "
                "(or load the demo data) to build a report."
            )
        return ui.tags.ul(*[ui.tags.li(x) for x in s])

    def _name(kind):
        ds = dataset()
        year = (ds.rosters.current_year if ds is not None else None) or (program() or {}).get("exam_year") or "ITE"
        return f"ITE_{year}_{kind}.html"

    @render.download_button(filename=lambda: _name("PD_report_CONFIDENTIAL"), media_type="text/html")
    def identified():
        if sections():
            yield report_builder.build_report(dataset(), program(), deidentified=False, cutoffs=cutoffs())

    @render.ui
    def sheets():
        s = data_export.included_sheets(dataset(), program())
        return ui.p("Sheets: " + ", ".join(s) + ".", class_="hint") if s else None

    @render.download_button(
        filename=lambda: _name("all_data_CONFIDENTIAL").replace(".html", ".xlsx"),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    def workbook():
        if sections():
            yield data_export.build_workbook(dataset(), program(), cutoffs=cutoffs())

    @render.download_button(filename=lambda: _name("program_summary"), media_type="text/html")
    def deidentified():
        if sections():
            yield report_builder.build_report(dataset(), program(), deidentified=True, cutoffs=cutoffs())
