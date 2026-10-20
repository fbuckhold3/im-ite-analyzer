"""Program data sub-tabs that read the session dataset from Upload & Align:
Trends by level · Classes · Year over year. One Shiny module per sub-tab."""

from __future__ import annotations

import math

from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from ite_core import history, stats

from . import plots
from .common import fmt_num, how_to_read, message

NEED_DATA = "Load your ACP rosters (or the demo data) on the Upload & Align tab first."


def _long(dataset):
    ds = dataset()
    return None if ds is None or ds.rosters.long.empty else ds.rosters.long


def _cell(value, n, small, suffix=""):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ui.tags.td("—")
    return ui.tags.td(
        f"{value:.0f}{suffix}",
        ui.span(f" ({int(n)})", class_="n"),
        ui.span(" small group", class_="small-flag") if small else None,
        class_="small" if small else None,
    )


# ------------------------------------------------------------------ Trends by level
@module.ui
def trends_ui():
    return ui.card(
        ui.card_header("How each PGY level has done, by exam year"),
        ui.p(
            "Each panel compares the residents at one PGY level across exam years — different people sit in each bar.",
            class_="hint",
        ),
        ui.input_radio_buttons(
            "metric", None, {k: v[0] for k, v in plots.LEVEL_METRICS.items()}, selected="ile", inline=True
        ),
        ui.output_ui("empty"),
        output_widget("plot"),
        ui.output_ui("table"),
        ui.p(
            "Hatched, faded bars and “small group” cells have fewer than 5 residents — read them with care.",
            class_="hint",
        ),
        how_to_read(),
    )


@module.server
def trends_server(input, output, session, dataset):
    @reactive.calc
    def lv():
        long = _long(dataset)
        return None if long is None else history.by_level(long)

    @render.ui
    def empty():
        return message(NEED_DATA) if lv() is None else None

    @render_plotly
    def plot():
        t = lv()
        return None if t is None else plots.level_small_multiples(t, input.metric())

    @render.ui
    def table():
        t = lv()
        if t is None:
            return None
        m = input.metric()
        label, suffix, _ = plots.LEVEL_METRICS[m]
        years = sorted(t.Exam_Year.unique())
        rows = []
        for p in sorted(t.PGY.unique()):
            d = t[t.PGY == p].set_index("Exam_Year")
            cells = [
                _cell(d.loc[y, m], d.loc[y, "n"], bool(d.loc[y, "small_n"]), suffix)
                if y in d.index
                else ui.tags.td("—")
                for y in years
            ]
            vals = d[m].dropna()
            lo, hi = (f"{vals.min():.0f}", f"{vals.max():.0f}") if len(vals) else ("", "")
            rng = "—" if len(vals) < 2 else (f"{lo}{suffix}" if lo == hi else f"{lo}–{hi}{suffix}")
            rows.append(ui.tags.tr(ui.tags.th(f"PGY-{p}", scope="row"), *cells, ui.tags.td(rng)))
        head = ui.tags.tr(
            ui.tags.th(label, scope="col"),
            *[ui.tags.th(str(y), scope="col") for y in years],
            ui.tags.th("Range", scope="col"),
        )
        return ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="table table-sm data-table")


# ------------------------------------------------------------------------ Classes
@module.ui
def classes_ui():
    return ui.card(
        ui.card_header("Each graduating class, PGY-1 → PGY-3"),
        ui.input_radio_buttons("value", None, {"ile": "Mean percentile", "pc": "Mean percent correct"}, inline=True),
        ui.output_ui("empty"),
        output_widget("plot"),
        ui.h6("Class matrix"),
        ui.p(
            "Read across a row to follow one class; read down a column to compare classes at the same stage. "
            "(n, exam year) in each cell. Class membership can shift a little from year to year.",
            class_="hint",
        ),
        ui.output_ui("matrix"),
        how_to_read(),
    )


@module.server
def classes_server(input, output, session, dataset):
    @reactive.calc
    def traj():
        long = _long(dataset)
        return None if long is None else history.class_trajectories(long, input.value())

    @render.ui
    def empty():
        return message(NEED_DATA) if traj() is None else None

    @render_plotly
    def plot():
        t = traj()
        label = "Mean percentile" if input.value() == "ile" else "Mean percent correct (%)"
        return None if t is None else plots.class_trajectories_figure(t, label)

    @render.ui
    def matrix():
        t = traj()
        if t is None:
            return None
        suffix = "" if input.value() == "ile" else "%"
        rows = []
        for gc in dict.fromkeys(t.Grad_Class):
            d = t[t.Grad_Class == gc].set_index("PGY")
            cells = []
            for p in (1, 2, 3):
                if p in d.index:
                    r = d.loc[p]
                    cells.append(
                        ui.tags.td(
                            f"{r.value:.0f}{suffix}",
                            ui.span(f" ({int(r.n)}, {int(r.Exam_Year)})", class_="n"),
                            ui.span(" small group", class_="small-flag") if r.small_n else None,
                            class_="small" if r.small_n else None,
                        )
                    )
                else:
                    cells.append(ui.tags.td("—"))
            ch = d.value.iloc[-1] - d.value.iloc[0] if len(d) > 1 else None
            ch_txt = "—" if ch is None else f"{ch:+.0f}"
            status = "" if d.status.iloc[0] == "current" else " (graduated)"
            rows.append(ui.tags.tr(ui.tags.th(f"Class of {gc}{status}", scope="row"), *cells, ui.tags.td(ch_txt)))
        head = ui.tags.tr(
            *[ui.tags.th(h, scope="col") for h in ("Class", "PGY-1", "PGY-2", "PGY-3", "Change, first → latest ITE")]
        )
        return ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="table table-sm data-table")


# -------------------------------------------------------------------- Year over year
@module.ui
def yoy_ui():
    return ui.card(
        ui.card_header("Same residents: last year → this year"),
        ui.input_radio_buttons(
            "outcome", None, {"percentile": "Percentile", "pct_correct": "Percent correct"}, inline=True
        ),
        ui.output_ui("empty"),
        ui.output_ui("summary"),
        output_widget("plot"),
        ui.p(
            "Points above the diagonal improved. Dotted lines mark the 20th and 35th percentiles. Percent correct "
            "rises each year for nearly everyone (later PGY levels score higher nationally), so percentile is the "
            "fairer comparison.",
            class_="hint",
        ),
        how_to_read(),
    )


def _verdict(p, outcome="percentile"):
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "too few residents to test"
    if outcome != "percentile":  # % correct rises with training by design — significance is unsurprising
        return f"expected rise with training (p = {p:.3f}); compare percentiles for program effect"
    return f"likely a real change (p = {p:.3f})" if p < 0.05 else f"no clear change (p = {p:.2f})"


@module.server
def yoy_server(input, output, session, dataset):
    @reactive.calc
    def w():
        ds = dataset()
        return None if ds is None else ds.wide

    @reactive.calc
    def pts():
        x = w()
        return None if x is None else stats.paired_points(x)

    @render.ui
    def empty():
        if w() is None:
            return message(NEED_DATA)
        if pts().empty:
            return message("Upload at least two consecutive exam years to compare the same residents.", "warning")
        return None

    @render.ui
    def summary():
        x, pp = w(), pts()
        if x is None or pp.empty:
            return None
        unit = "percentile points" if input.outcome() == "percentile" else "points of percent correct"
        cards = []
        for p in (2, 3):
            c = stats.paired_change(x, p, outcome=input.outcome())
            if c["n"] == 0:
                continue
            cards.append(
                ui.div(
                    ui.h6(f"Now PGY-{p} (n = {c['n']})"),
                    ui.div(f"{c['d_mean']:+.1f}", class_="big-number"),
                    ui.p(f"mean change in {unit}; median {fmt_num(c['d_med'], 0)}", class_="hint"),
                    ui.p(f"{c['up']} rose and {c['down']} fell by 10 or more · {_verdict(c['p'], input.outcome())}"),
                    class_="yoy-card",
                )
            )
        return ui.layout_columns(*cards, col_widths=[6] * len(cards)) if cards else None

    @render_plotly
    def plot():
        pp = pts()
        return None if pp is None or pp.empty else plots.yoy_scatter(pp, input.outcome())
