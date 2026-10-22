"""Program data → Item gaps: per-item program vs national % correct from the ACP Program Performance Report."""

from __future__ import annotations

import io

import pandas as pd
from htmltools import Tag, tags
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


def ordered(items: pd.DataFrame) -> pd.DataFrame:
    """Flagged first (red, yellow), then the largest All-PGY gap."""
    return items.assign(order=items.flag.map({"red": 0, "yellow": 1}).fillna(2)).sort_values(["order", "gapA"])


def gap_class(v) -> str:
    if v is None or v != v:
        return "gap-na"
    if v <= -20:
        return "gap-sev"
    if v <= -10:
        return "gap-neg"
    if v >= 10:
        return "gap-pos"
    return "gap-0"


def _gap(v) -> Tag:
    return tags.span("—" if v is None or v != v else f"{int(v):+d}", class_=f"gap-chip {gap_class(v)}")


def _vs_national(ours, nat) -> Tag:
    """Program vs national % correct (All PGYs) as a small dumbbell on a 0–100 track."""
    if ours != ours or nat != nat:
        return tags.span("—")
    lo, hi = sorted((float(ours), float(nat)))
    tone = "below" if ours < nat else "above"
    return tags.div(
        tags.div(
            tags.span(class_=f"db-span db-{tone}", style=f"left:{lo}%;width:{hi - lo}%"),
            tags.span(class_="db-nat", style=f"left:{float(nat)}%"),
            tags.span(class_=f"db-ours db-{tone}", style=f"left:{float(ours)}%"),
            class_="db-track",
            aria_hidden="true",
        ),
        tags.span(f"{int(ours)}% vs {int(nat)}%", class_="db-label"),
        class_="db",
        title=f"Program {int(ours)}% correct vs national {int(nat)}% (all PGYs)",
    )


def items_table(items: pd.DataFrame) -> Tag:
    """Formatted item table (app and PD report): flag badge, area, objective, program vs national, gap chips."""
    head = ["Flag", "Content area", "Objective", "Program vs national (all PGYs)", "PGY-1", "PGY-2", "PGY-3", "All"]
    rows = [
        tags.tr(
            tags.td(tags.span(r.flag, class_=f"flag-badge flag-{r.flag}") if isinstance(r.flag, str) else ""),
            tags.td(r.area, class_="it-area"),
            tags.td(r.objective, tags.span("HVC", class_="hvc-tag") if r.hvc else None, class_="it-obj"),
            tags.td(_vs_national(r.ourA, r.allA)),
            *[
                tags.td(_gap(g), class_="it-gap", data_label=lab)
                for g, lab in zip((r.gap1, r.gap2, r.gap3, r.gapA), ("PGY-1", "PGY-2", "PGY-3", "All"), strict=True)
            ],
            class_=f"it-row it-{r.flag}" if isinstance(r.flag, str) else "it-row",
        )
        for r in ordered(items).itertuples()
    ]
    return tags.div(
        tags.table(
            tags.thead(
                tags.tr(
                    *[tags.th(h, scope="col", class_="it-gap" if h.startswith(("PGY", "All")) else None) for h in head]
                )
            ),
            tags.tbody(*rows),
            class_="items-table",
        ),
        class_="items-scroll",
    )


def gap_legend() -> Tag:
    return tags.p(
        "Gap = program minus national % correct, in points: ",
        tags.span("−20 or lower", class_="gap-chip gap-sev"),
        " ",
        tags.span("−10 to −19", class_="gap-chip gap-neg"),
        " ",
        tags.span("−9 to +9", class_="gap-chip gap-0"),
        " ",
        tags.span("+10 or higher", class_="gap-chip gap-pos"),
        class_="gap-legend",
    )


def rank_legend() -> Tag:
    return tags.p(
        "Each cell is the program's percentile rank among all programs for that content area and PGY group — ",
        tags.strong("50 is the middle program"),
        ". Orange cells are below the middle, blue above. Areas are sorted with the lowest All-PGY rank first.",
        class_="hint",
    )


@module.ui
def items_ui():
    return ui.div(
        ui.output_ui("empty"),
        ui.output_ui("stats"),
        ui.card(
            ui.card_header("How the program ranks, by content area"),
            rank_legend(),
            ui.div(output_widget("ranks"), class_="heatmap-wrap"),
            class_="results-card",
        ),
        ui.card(
            ui.card_header("Questions furthest below national"),
            ui.div(
                ui.input_select("area", "Content area", {"": "All content areas"}),
                ui.input_radio_buttons("show", "Show", SHOW, inline=True),
                class_="filter-row",
            ),
            ui.tags.details(
                ui.tags.summary("Flag thresholds"),
                ui.layout_columns(
                    ui.input_numeric("red", "Red: All-PGY gap at or below", value=-10, min=-50, max=0, step=1),
                    ui.input_numeric(
                        "yellow", "Yellow: any single-PGY gap at or below", value=-20, min=-60, max=0, step=1
                    ),
                    col_widths=(6, 6),
                ),
                class_="explainer",
            ),
            gap_legend(),
            ui.output_ui("table"),
            ui.div(
                ui.download_button("dl_csv", "Flagged items (.csv)", class_="btn-sm"),
                ui.download_button("dl_xlsx", "All items with gaps (.xlsx)", class_="btn-sm btn-outline-primary"),
                class_="button-row",
            ),
            ui.div(
                ui.strong("Read with care. "),
                "In a group of about 25 residents, one person moves a single-PGY percentage by about 4 points, so "
                "flags are prompts for curriculum review, not findings. HVC = the item also counts toward High Value "
                "Care.",
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

    @reactive.effect
    def _areas():
        r = rep()
        areas = sorted(r["items"].area.unique()) if r is not None else []
        ui.update_select("area", choices={"": "All content areas", **{a: a for a in areas}})

    @render.ui
    def empty():
        return message(NEED_PDF) if rep() is None else None

    @render.ui
    def stats():
        it = items()
        if it is None:
            return None
        s = pdf_reports.items_summary(it)
        n = pdf_reports.residents_per_group(rep()["areas"])
        ranks = pdf_reports.area_ranks(rep()["areas"])
        total = ranks[ranks.area == "Total Test"]
        tiles = [
            (str(s["red"]), "Red items", "All-PGY gap at or below the red threshold", "tone-high"),
            (str(s["yellow"]), "Yellow items", "One PGY level far below national", "tone-mid"),
            (
                str(s["n"]),
                "Items on the exam",
                f"{rep().get('exam_year') or ''} Program Performance Report".strip(),
                "",
            ),
        ]
        if len(total) and total.rankA.iloc[0] == total.rankA.iloc[0]:
            tiles.append((f"{total.rankA.iloc[0]:.0f}", "Overall rank", "Total test, all PGYs (50 = middle)", ""))
        if n:
            tiles.append(
                (
                    str(n.get("A", "—")),
                    "Residents tested",
                    ", ".join(f"{PGY_GAP[k]} {v}" for k, v in n.items() if k != "A"),
                    "",
                )
            )
        return ui.div(
            *[
                ui.div(
                    ui.div(v, class_=f"stat-value {tone}"),
                    ui.div(label, class_="stat-name"),
                    ui.div(sub, class_="stat-sub"),
                    class_="stat-tile",
                )
                for v, label, sub, tone in tiles
            ],
            class_="stat-tiles",
        )

    @render_plotly
    def ranks():
        r = rep()
        return None if r is None else plots.area_ranks_heatmap(pdf_reports.area_ranks(r["areas"]))

    @reactive.calc
    def shown():
        it = items()
        if it is None:
            return None
        if input.area():
            it = it[it.area == input.area()]
        return it[it.flag.notna()] if input.show() == "flagged" else it

    @render.ui
    def table():
        d = shown()
        if d is None:
            return None
        if d.empty:
            return message("No items match — try “All items” or another content area.")
        return ui.div(ui.p(f"{len(d)} item(s)", class_="hint"), items_table(d))

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
