"""Quick calculator: % correct + PGY (or several years) -> ABIM pass estimate. No uploads."""

from __future__ import annotations

import math

from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from ite_core import nomogram

from . import plots
from .common import citation, fmt_num, fmt_prob, how_to_read, message, tier_badge, trajectory_table

LOW_CUTOFFS = {"0.90": "90% (default)", "0.80": "80%", "0.75": "75%"}


def _pct_input(id_, label):
    return ui.input_numeric(id_, label, value=None, min=0, max=100, step=1)


@module.ui
def calculator_ui():
    return ui.layout_columns(
        ui.card(
            ui.card_header("Your ITE score"),
            ui.input_radio_buttons(
                "mode", None, {"one": "One exam", "years": "All my years"}, selected="one", inline=True
            ),
            ui.panel_conditional(
                "input.mode === 'one'",
                ui.input_select("pgy", "PGY level when you took the exam", {"1": "PGY-1", "2": "PGY-2", "3": "PGY-3"}),
                _pct_input("pct", "Total test percent correct (%)"),
            ),
            ui.panel_conditional(
                "input.mode === 'years'",
                ui.p("Enter the years you have; leave the others blank.", class_="hint"),
                _pct_input("pct1", "PGY-1 percent correct (%)"),
                _pct_input("pct2", "PGY-2 percent correct (%)"),
                _pct_input("pct3", "PGY-3 percent correct (%)"),
            ),
            ui.accordion(
                ui.accordion_panel(
                    "Settings",
                    ui.input_select("low_cut", "“Low risk” starts at an estimated pass probability of", LOW_CUTOFFS),
                    ui.p("High risk is always below 50%.", class_="hint"),
                ),
                open=False,
            ),
            ui.p("Use the total test percent correct from your ACP Examinee Performance Report.", class_="hint"),
        ),
        ui.card(
            ui.card_header("Estimated probability of passing ABIM on the first attempt"),
            ui.output_ui("result"),
            output_widget("plot"),
            ui.output_ui("trajectory"),
            how_to_read(),
            ui.div(
                citation(),
                ui.p(
                    "These coefficients are a logistic fit to the curves published by McDonald et al., not values "
                    "published by the authors. The study cohort took the ITE in 2014–2015; the estimate uses percent "
                    "correct only and is a population-level association, not a prediction for any one person.",
                    class_="hint",
                ),
                class_="source-box",
            ),
        ),
        col_widths=(4, 8),
    )


@module.server
def calculator_server(input, output, session):
    @reactive.calc
    def cutoffs():
        return (0.50, float(input.low_cut()))

    @reactive.calc
    def scores() -> tuple[dict, str | None]:
        """{pgy: pct} plus a validation message (None when inputs are usable)."""
        raw = (
            {int(input.pgy()): input.pct()}
            if input.mode() == "one"
            else {1: input.pct1(), 2: input.pct2(), 3: input.pct3()}
        )
        vals = {}
        for pgy, v in raw.items():
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            if not 0 <= v <= 100:
                return {}, f"PGY-{pgy}: percent correct must be between 0 and 100."
            vals[pgy] = float(v)
        if not vals:
            return {}, None  # nothing entered yet
        return vals, None

    @reactive.calc
    def table():
        vals, err = scores()
        return None if err or not vals else nomogram.trajectory(vals, cutoffs())

    @render.ui
    def result():
        vals, err = scores()
        if err:
            return message(err, "error")
        if not vals:
            return message("Enter a percent correct to see your estimate.")
        t = table()
        last = t.iloc[-1]
        nxt = int(last.PGY) + 1
        needed_next = round(nomogram.pct_for_prob(cutoffs()[1], nxt), 1) if nxt <= 3 else None
        lines = [
            ui.div(fmt_prob(last.Pass_Prob), class_="big-number"),
            ui.div(tier_badge(last.Risk_Tier), f" at PGY-{int(last.PGY)} with {fmt_num(last.Pct_Correct)}% correct"),
            ui.p(
                f"Low risk at PGY-{int(last.PGY)} starts at about {fmt_num(last.Pct_Needed_Low, 1)}% correct.",
                *([f" Next year (PGY-{nxt}) it takes about {fmt_num(needed_next, 1)}%."] if needed_next else []),
                class_="hint",
            ),
        ]
        return ui.div(*lines, class_="result-card", aria_live="polite")

    @render_plotly
    def plot():
        return plots.nomogram_figure()  # built once; the effects below update it in place

    @reactive.effect
    def _update_points():
        t = table()
        rows = [] if t is None else list(zip(t.PGY, t.Pct_Correct, t.Pass_Prob, strict=True))
        fig = plot.widget
        if fig is None:
            return
        with fig.batch_update():
            plots.set_points(fig, rows)
            plots.set_bands(fig, cutoffs())

    @render.ui
    def trajectory():
        return trajectory_table(table())
