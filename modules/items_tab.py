"""Program data → Item gaps: per-item program vs national % correct from the ACP Program Performance Report."""

from __future__ import annotations

import io

import pandas as pd
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from ite_core import pdf_reports

from . import plots
from .common import message

NEED_PDF = "Upload your ACP Program Performance Report (PDF) on the Upload & Align tab to see item-level gaps."
SHOW = {"flagged": "Flagged items", "all": "All items"}
PGY_GAP = {"A": "All PGYs", "1": "PGY-1", "2": "PGY-2", "3": "PGY-3"}


def item_frame(items: pd.DataFrame) -> pd.DataFrame:
    """Display / export columns, flagged items first, then largest All-PGY gap."""
    order = {"red": 0, "yellow": 1}
    d = items.assign(_o=items.flag.map(order).fillna(2)).sort_values(["_o", "gapA"])
    return pd.DataFrame(
        {
            "Flag": d.flag.fillna(""),
            "Content area": d.area,
            "Objective": d.objective,
            "HVC": d.hvc.map({True: "HVC", False: ""}),
            "PGY-1 program %": d.our1,
            "PGY-1 national %": d.all1,
            "PGY-1 gap": d.gap1,
            "PGY-2 program %": d.our2,
            "PGY-2 national %": d.all2,
            "PGY-2 gap": d.gap2,
            "PGY-3 program %": d.our3,
            "PGY-3 national %": d.all3,
            "PGY-3 gap": d.gap3,
            "All program %": d.ourA,
            "All national %": d.allA,
            "All gap": d.gapA,
        }
    )


@module.ui
def items_ui():
    return ui.div(
        ui.output_ui("empty"),
        ui.card(
            ui.card_header("Content areas: program rank among all programs"),
            ui.p(
                "Where the program's mean percent correct ranks among all programs' means (50 = middle program), "
                "by PGY group.",
                class_="hint",
            ),
            output_widget("ranks"),
            class_="results-card",
        ),
        ui.card(
            ui.card_header("Items far below national"),
            ui.layout_columns(
                ui.input_numeric("red", "Red: All-PGY gap at or below", value=-10, min=-50, max=0, step=1),
                ui.input_numeric("yellow", "Yellow: any single-PGY gap at or below", value=-20, min=-60, max=0, step=1),
                ui.input_radio_buttons("show", "Show", SHOW, inline=True),
                col_widths=(4, 4, 4),
            ),
            ui.output_ui("summary"),
            ui.output_data_frame("table"),
            ui.div(
                ui.download_button("dl_csv", "Flagged items (.csv)", class_="btn-sm"),
                ui.download_button("dl_xlsx", "All items with gaps (.xlsx)", class_="btn-sm btn-outline-primary"),
                class_="button-row",
            ),
            ui.div(
                ui.strong("Read with care. "),
                "Gap = program % correct minus national % correct for that item. In a group of about 25 residents, one "
                "person moves a single-PGY percentage by about 4 points, so flags are prompts for curriculum review, "
                "not findings. HVC = the item also counts toward High Value Care.",
                class_="msg msg-warning",
            ),
            class_="results-card",
        ),
    )


@module.server
def items_server(input, output, session, program):
    @reactive.calc
    def rep():
        return program()

    @reactive.calc
    def items():
        r = rep()
        if r is None:
            return None
        red = input.red() if input.red() is not None else pdf_reports.RED_GAP
        yellow = input.yellow() if input.yellow() is not None else pdf_reports.YELLOW_GAP
        return pdf_reports.flag_items(r["items"], red=red, yellow=yellow)

    @render.ui
    def empty():
        return message(NEED_PDF) if rep() is None else None

    @render_plotly
    def ranks():
        r = rep()
        return None if r is None else plots.area_ranks_figure(pdf_reports.area_ranks(r["areas"]))

    @render.ui
    def summary():
        it = items()
        if it is None:
            return None
        s = pdf_reports.items_summary(it)
        n = pdf_reports.residents_per_group(rep()["areas"])
        rows = [
            ui.tags.tr(
                ui.tags.td(r.area),
                ui.tags.td(str(r["items"])),
                ui.tags.td(str(int(r.red))),
                ui.tags.td(str(int(r.yellow))),
                ui.tags.td(f"{r.mean_gapA:+.1f}"),
            )
            for _, r in s["by_area"].iterrows()
        ]
        head = ui.tags.tr(
            *[ui.tags.th(h, scope="col") for h in ("Content area", "Items", "Red", "Yellow", "Mean All-PGY gap")]
        )
        group = ", ".join(f"{PGY_GAP[k]} {v}" for k, v in n.items()) if n else ""
        return ui.div(
            ui.p(
                ui.strong(f"{s['red']} red"),
                " (well below national across all PGYs) · ",
                ui.strong(f"{s['yellow']} yellow"),
                f" (below for one PGY level) · of {s['n']} items.",
                class_="summary-line",
            ),
            ui.p(f"Residents tested: {group}." if group else "", class_="hint"),
            ui.tags.details(
                ui.tags.summary("By content area"),
                ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="table table-sm data-table"),
                class_="explainer",
            ),
        )

    @reactive.calc
    def shown():
        it = items()
        if it is None:
            return None
        f = item_frame(it)
        return f[f.Flag != ""] if input.show() == "flagged" else f

    @render.data_frame
    def table():
        d = shown()
        return None if d is None else render.DataGrid(d, filters=True, height="460px", width="100%")

    def _year():
        r = rep()
        return (r or {}).get("exam_year") or "ITE"

    @render.download_button(filename=lambda: f"ite_item_gaps_flagged_{_year()}.csv", media_type="text/csv")
    def dl_csv():
        it = items()
        if it is not None:
            f = item_frame(it)
            yield f[f.Flag != ""].to_csv(index=False).encode()

    @render.download_button(
        filename=lambda: f"ite_item_gaps_{_year()}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    def dl_xlsx():
        it = items()
        if it is None:
            return
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            item_frame(it).to_excel(xw, sheet_name="Items", index=False)
            pdf_reports.area_ranks(rep()["areas"]).to_excel(xw, sheet_name="Area ranks", index=False)
        yield buf.getvalue()
