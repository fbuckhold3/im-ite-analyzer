"""Program data → Board pass: every current resident's ABIM pass estimate, tier, change and watch list."""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from ite_core import board

from . import plots, resident_pdf
from .common import citation, fmt_num, fmt_prob, how_to_read, message, tier_badge, trajectory_table
from .program_tabs import NEED_DATA

LOW_CUTOFFS = {"0.90": "90% (default)", "0.80": "80%", "0.75": "75%"}
FILTERS = {"all": "All", "1": "PGY-1", "2": "PGY-2", "3": "PGY-3", "below": "Below Low risk"}
CHANGE_LABEL = {
    "Worsened": "worsened",
    "Improved": "improved",
    "Stable": "stayed the same",
    "No prior": "no prior year",
}


def _num(x, digits=0, suffix=""):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{digits}f}{suffix}"


@module.ui
def board_ui():
    return ui.div(
        ui.output_ui("class_rates"),
        ui.card(
            ui.card_header("Estimated ABIM pass probability — current residents"),
            ui.layout_columns(
                ui.input_select("low_cut", "“Low risk” starts at", LOW_CUTOFFS),
                ui.p(
                    "High risk is below 50%. The estimate uses percent correct and the PGY-level curve.", class_="hint"
                ),
                col_widths=(4, 8),
            ),
            ui.output_ui("empty"),
            ui.output_ui("summary"),
            ui.layout_columns(
                output_widget("plot"),
                ui.div(
                    ui.output_ui("picker"),
                    ui.p("Click a dot on the chart, or choose a resident here.", class_="hint"),
                ),
                col_widths=(9, 3),
            ),
        ),
        ui.output_ui("detail"),
        ui.output_ui("watch"),
        ui.card(
            ui.card_header("All current residents"),
            ui.input_radio_buttons("filter", None, FILTERS, inline=True),
            ui.output_data_frame("table"),
            ui.div(ui.download_button("download", "Download table (.csv)", class_="btn-sm"), class_="button-row"),
        ),
        ui.div(
            how_to_read(),
            citation(),
            ui.p(
                "A tier can worsen with an unchanged score: each PGY curve is steeper than the last, so the same "
                "percent correct counts for less later in training. Check percentile alongside.",
                class_="hint",
            ),
            class_="source-box",
        ),
    )


@module.server
def board_server(input, output, session, dataset):
    selected = reactive.value(None)

    @reactive.calc
    def cutoffs():
        return (0.50, float(input.low_cut()))

    @reactive.calc
    def bt():
        ds = dataset()
        if ds is None or ds.wide is None:
            return None
        return board.board_table(ds.wide, cutoffs())

    @reactive.calc
    def cy():
        return bt().attrs["current_year"]

    @render.ui
    def empty():
        return message(NEED_DATA) if bt() is None else None

    @render.ui
    def summary():
        t = bt()
        if t is None:
            return None
        ts = board.tier_summary(t)
        head = ui.tags.tr(ui.tags.th("", scope="col"), *[ui.tags.th(tier_badge(k), scope="col") for k in board.TIERS])
        rows = [
            ui.tags.tr(
                ui.tags.th("All" if p == "All" else f"PGY-{p}", scope="row"),
                *[ui.tags.td(str(int(ts.loc[p, k]))) for k in board.TIERS],
            )
            for p in ts.index
        ]
        ch = board.change_summary(t)
        changes = " · ".join(f"{v} {CHANGE_LABEL[k]}" for k, v in ch.items() if v)
        return ui.div(
            ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="table table-sm data-table tier-table"),
            ui.p(ui.strong(f"Since {cy() - 1}: "), changes, class_="hint"),
            ui.p(
                "Nearly every PGY-1 lands in Low risk because the PGY-1 curve is shallow; the estimate is most "
                "informative for PGY-2 and PGY-3.",
                class_="hint",
            ),
        )

    @render.ui
    def class_rates():
        t = bt()
        if t is None:
            return None
        cr = board.class_pass_rates(t)
        if cr.empty:
            return None
        tiles = []
        for r in cr.itertuples():
            if r.n == 0:
                continue
            tiles.append(
                ui.div(
                    ui.div(fmt_prob(r.projected), class_="stat-value"),
                    ui.div(f"Class of {r.grad_class}", class_="stat-name"),
                    ui.div(f"Now PGY-{r.PGY} · {r.n} resident{'s' * (r.n != 1)}", class_="stat-sub"),
                    ui.div(f"Likely {r.lo}–{r.hi} of {r.n} pass", class_="stat-range"),
                    ui.div("Least informative: intern ITE", class_="stat-caveat") if r.PGY == 1 else None,
                    class_="stat-tile",
                )
            )
        missing = int(cr.missing.sum())
        return ui.card(
            ui.card_header("Projected ABIM pass rate, by class"),
            ui.div(*tiles, class_="stat-tiles"),
            ui.p(
                "Projected pass rate = the average of each resident's estimated chance of passing — the share of the "
                f"class expected to pass if the estimates hold. “Likely” is the middle {int(100 * cr.attrs['level'])}% "
                "range for the number who pass, by chance alone; it assumes each resident's result is independent and "
                "does not include uncertainty in the estimate itself (an approximation of McDonald et al. 2020).",
                class_="hint",
            ),
            ui.p(f"{missing} resident(s) without a {cy()} score are not included.", class_="hint") if missing else None,
        )

    @render_plotly
    def plot():
        t = bt()
        if t is None:
            return None
        fig = go.FigureWidget(plots.program_nomogram(t, cutoffs()))

        def on_click(trace, points, _state):
            if points.point_inds:
                selected.set(str(trace.customdata[points.point_inds[0]]))

        for tr in fig.data[plots.POINTS_TRACE + 1 :]:
            tr.on_click(on_click)
        return fig

    @render.ui
    def picker():
        t = bt()
        if t is None:
            return None
        order = t.sort_values(["PGY", "Name"], ascending=[False, True])
        choices = {"": "Choose a resident…"} | {
            i: f"{n} (PGY-{p})" for i, n, p in zip(order.ID, order.Name, order.PGY, strict=True)
        }
        with reactive.isolate():
            cur = selected.get()
        return ui.input_selectize("who", "Resident", choices, selected=cur or "")

    @reactive.effect
    @reactive.event(input.who)
    def _picked():
        if input.who():
            selected.set(input.who())

    @reactive.effect
    def _sync_picker():  # a click on the chart updates the picker
        sid = selected.get()
        if sid and "who" in input and input.who() != sid:
            ui.update_selectize("who", selected=sid)

    @render.ui
    def detail():
        t, sid = bt(), selected.get()
        if t is None or not sid or sid not in set(t.ID):
            return None
        r = t[t.ID == sid].iloc[0]
        ds = dataset()
        h = board.resident_history(ds.rosters.long, sid, cutoffs())
        areas = board.resident_areas(ds.rosters.long, sid)
        y = cy()
        return ui.card(
            ui.card_header(
                ui.div(
                    ui.span(f"{r.Name} · PGY-{int(r.PGY)}"),
                    ui.download_button("resident_pdf_dl", "Download resident PDF", class_="btn-sm btn-outline-primary"),
                    class_="d-flex justify-content-between align-items-center gap-2",
                )
            ),
            ui.layout_columns(
                ui.div(
                    ui.div(fmt_prob(r[f"Prob_{y}"]), class_="big-number"),
                    ui.div(tier_badge(r.Tier)),
                    ui.p(
                        f"{_num(r[f'Pct_{y}'])}% correct · percentile {_num(r[f'Ile_{y}'])} · Low risk at this level "
                        f"starts at {fmt_num(r.Needed_Low, 1)}% ({_num(r.Gap_Low, 1)} points "
                        f"{'above' if (r.Gap_Low or 0) >= 0 else 'below'}).",
                        class_="hint",
                    ),
                    trajectory_table(h) if len(h) > 1 else ui.p("Only one exam year on file.", class_="hint"),
                ),
                ui.div(
                    ui.h6(
                        f"Content areas ({areas.attrs['exam_year']} roster)" if areas is not None else "Content areas"
                    ),
                    output_widget("areas")
                    if areas is not None
                    else ui.p("This roster has no content-area percentiles (older ACP layout).", class_="hint"),
                ),
                col_widths=(6, 6),
            ),
        )

    @render.download_button(
        filename=lambda: resident_pdf.pdf_filename(resident_pdf.from_roster(dataset(), selected.get(), cutoffs())),
        media_type="application/pdf",
    )
    def resident_pdf_dl():
        sid = selected.get()
        if sid and bt() is not None and sid in set(bt().ID):
            yield resident_pdf.resident_pdf(resident_pdf.from_roster(dataset(), sid, cutoffs()), cutoffs())

    @render_plotly
    def areas():
        t, sid = bt(), selected.get()
        if t is None or not sid:
            return None
        a = board.resident_areas(dataset().rosters.long, sid)
        return None if a is None else plots.area_percentile_figure(a)

    @render.ui
    def watch():
        t = bt()
        if t is None:
            return None
        wl = board.watch_list(t)
        y = cy()
        if wl.empty:
            return ui.card(
                ui.card_header("Watch list (PGY-2 and PGY-3)"),
                message("No PGY-2 or PGY-3 resident is below Low risk or has a worsened tier."),
            )
        rows = [
            ui.tags.tr(
                ui.tags.td(r.Name),
                ui.tags.td(f"PGY-{int(r.PGY)}"),
                ui.tags.td(f"{_num(r[f'Pct_{y}'])}%"),
                ui.tags.td(_num(r[f"Ile_{y}"])),
                ui.tags.td(fmt_prob(r[f"Prob_{y}"])),
                ui.tags.td(tier_badge(r.Tier)),
                ui.tags.td(CHANGE_LABEL[r.Tier_change]),
                ui.tags.td(_num(r.Gap_Low, 1)),
            )
            for _, r in wl.iterrows()
        ]
        head = ui.tags.tr(
            *[
                ui.tags.th(h, scope="col")
                for h in (
                    "Resident",
                    "Level",
                    "% correct",
                    "Percentile",
                    "Estimate",
                    "Tier",
                    "Tier since last year",
                    "Points from Low risk",
                )
            ]
        )
        return ui.card(
            ui.card_header(f"Watch list (PGY-2 and PGY-3): {len(wl)}"),
            ui.p(
                "Below Low risk, or tier worsened since last year. Negative points = below the Low-risk score.",
                class_="hint",
            ),
            ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="table table-sm data-table"),
        )

    @reactive.calc
    def display():
        t = bt()
        if t is None:
            return None
        f = input.filter()
        if f in ("1", "2", "3"):
            t = t[t.PGY == int(f)]
        elif f == "below":
            t = t[t.Tier != "Low"]
        years = t.attrs["years"]
        out = pd.DataFrame({"Resident": t.Name, "PGY": t.PGY})
        for y in years:
            out[f"% correct {y}"] = t[f"Pct_{y}"]
        out["Δ % correct"] = t.dPct
        for y in years:
            out[f"Percentile {y}"] = t[f"Ile_{y}"]
        out["Δ percentile"] = t.dIle
        for y in years[-2:]:
            out[f"Pass estimate {y} (%)"] = (100 * t[f"Prob_{y}"]).apply(lambda v: math.floor(v) if v == v else v)
        out["Tier"] = t.Tier
        out["Tier change"] = t.Tier_change.map(CHANGE_LABEL)
        out["Points from Low risk"] = t.Gap_Low
        if "mk_answered" in t:
            out["MKSAP questions"] = t.mk_answered
            out["MKSAP % correct"] = t.mk_pct_correct.round(1)
        return out.sort_values(["PGY", "Resident"], ascending=[False, True])

    @render.data_frame
    def table():
        d = display()
        return None if d is None else render.DataGrid(d, filters=False, height="420px", width="100%")

    @render.download_button(filename=lambda: f"ite_board_pass_{cy()}.csv", media_type="text/csv")
    def download():
        d = display()
        if d is not None:
            yield d.to_csv(index=False).encode()
