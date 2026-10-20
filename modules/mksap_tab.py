"""Program data → MKSAP: question-bank progress by class, and how MKSAP use relates to the next ITE."""

from __future__ import annotations

from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from ite_core import mksap, stats

from . import plots
from .common import fmt_num, how_to_read, message
from .program_tabs import NEED_DATA

NEED_MKSAP = "Add your MKSAP Digital detail export on the Upload & Align tab to see this tab."
OUTCOMES = {"pct": "ITE % correct", "ile": "Percentile"}


def _p(p):
    return "p < .001" if p < 0.001 else f"p = {p:.3f}"


@module.ui
def mksap_ui():
    return ui.div(
        ui.output_ui("empty"),
        ui.card(
            ui.card_header("MKSAP progress by class"),
            ui.output_ui("progress"),
            ui.layout_columns(
                ui.div(ui.h6("Questions answered"), output_widget("strip")),
                ui.div(ui.h6("How many residents in each range"), ui.output_ui("bins")),
                col_widths=(7, 5),
            ),
            ui.h6("Share of each MKSAP section attempted, and accuracy"),
            ui.p(
                "“Attempted” = questions answered ÷ (section size × residents in the class). Darker = more of the "
                "section done. Section names are inferred from MKSAP's two-letter codes.",
                class_="hint",
            ),
            ui.output_ui("sections"),
            class_="results-card",
        ),
        ui.card(
            ui.card_header("MKSAP and the next ITE (PGY-2 and PGY-3)"),
            ui.input_radio_buttons("outcome", None, OUTCOMES, inline=True),
            ui.output_ui("headline"),
            ui.layout_columns(
                ui.div(ui.h6("ITE change by MKSAP volume"), output_widget("thirds")),
                ui.div(ui.h6("Each resident"), output_widget("scatter")),
                col_widths=(6, 6),
            ),
            ui.output_ui("correlations"),
            ui.div(
                ui.strong("Read with care. "),
                "This is an association in one program, not proof that MKSAP causes higher scores — motivated "
                "residents may do more of everything. The MKSAP export is a snapshot that may post-date the ITE, "
                "MKSAP editions reset question counts, and the numbers of residents are small.",
                class_="msg msg-warning",
            ),
            class_="results-card",
        ),
        how_to_read(),
    )


@module.server
def mksap_server(input, output, session, dataset):
    @reactive.calc
    def w():
        ds = dataset()
        if ds is None or ds.mksap is None or ds.wide is None or "mk_answered" not in ds.wide:
            return None
        return ds.wide

    @render.ui
    def empty():
        ds = dataset()
        if ds is None:
            return message(NEED_DATA)
        if w() is None:
            return message(NEED_MKSAP)
        return None

    @render.ui
    def progress():
        x = w()
        if x is None:
            return None
        pr = mksap.progress_by_pgy(x)
        items = [
            ui.div(
                ui.h6(f"PGY-{int(r.PGY)} (n = {r.n})"),
                ui.div(f"{r.med:,.0f}", class_="big-number"),
                ui.p(
                    f"median questions (middle half {r.q1:,.0f}–{r.q3:,.0f}) · {fmt_num(r.bank_pct, 1)}% of the bank "
                    f"· {fmt_num(r.acc, 1)}% correct",
                    class_="hint",
                ),
                class_="yoy-card",
            )
            for r in pr.itertuples()
        ]
        bank = int(x.mk_bank.max())
        return ui.div(
            ui.layout_columns(*items, col_widths=[4] * len(items)),
            ui.p(f"Current MKSAP bank: {bank:,} questions.", class_="hint"),
        )

    @render_plotly
    def strip():
        x = w()
        return None if x is None else plots.mksap_strip(x)

    @render.ui
    def bins():
        x = w()
        if x is None:
            return None
        b = mksap.bins_table(x)
        head = ui.tags.tr(
            ui.tags.th("Questions", scope="col"), *[ui.tags.th(f"PGY-{p}", scope="col") for p in b.columns]
        )
        rows = [ui.tags.tr(ui.tags.th(i, scope="row"), *[ui.tags.td(str(v)) for v in r]) for i, r in b.iterrows()]
        return ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="table table-sm data-table")

    @render.ui
    def sections():
        x, ds = w(), dataset()
        if x is None:
            return None
        st = mksap.section_table(ds.mksap.sections, x)
        pgys = sorted(st.PGY.unique())
        head = ui.tags.tr(
            ui.tags.th("Section", scope="col"),
            ui.tags.th("Questions", scope="col"),
            *[ui.tags.th(f"PGY-{p} attempted · accuracy", scope="col") for p in pgys],
        )
        rows = []
        for code in dict.fromkeys(st.Subspecialty):
            s = st[st.Subspecialty == code].set_index("PGY")
            cells = []
            for p in pgys:
                if p not in s.index:
                    cells.append(ui.tags.td("—"))
                    continue
                done, acc = s.loc[p, "done"], s.loc[p, "acc"]
                shade = min(0.85, done / 50)  # 50% attempted = darkest
                cells.append(
                    ui.tags.td(
                        f"{done:.0f}%",
                        ui.span(f" · {fmt_num(acc, 0)}%" if acc == acc else " · —", class_="n"),
                        style=f"background: rgba(11, 92, 173, {shade:.2f}); "
                        f"color: {'#fff' if shade > 0.45 else 'inherit'}",
                    )
                )
            rows.append(
                ui.tags.tr(
                    ui.tags.th(f"{s['name'].iloc[0]} ({code})", scope="row"),
                    ui.tags.td(f"{int(s.bank.iloc[0]):,}"),
                    *cells,
                )
            )
        return ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="table table-sm data-table heat-table")

    @reactive.calc
    def models():
        x = w()
        return None if x is None else stats.mksap_models(x)

    @render.ui
    def headline():
        m = models()
        if m is None:
            return None
        if not m["ok"]:
            return message(m["reason"], "warning")
        if input.outcome() == "pct":
            text = (
                f"After accounting for last year's ITE and PGY level, each doubling of MKSAP questions answered went "
                f"with about {m['dbl']:+.1f} points of ITE percent correct ({_p(m['p_vol'])}); going from 100 to "
                f"800 questions, about {m['eff_100_800']:+.1f} points. Adding MKSAP volume raised the share of "
                f"variation explained from {m['r2_base']:.2f} to {m['r2_vol']:.2f}."
            )
        else:
            text = (
                f"In percentile terms, each doubling of questions went with about {m['dbl_ile']:+.1f} percentile "
                f"points ({_p(m['p_ile'])}), after accounting for last year's percentile and PGY level."
            )
        if m["p_vol" if input.outcome() == "pct" else "p_ile"] >= 0.05:
            text += " This association was not statistically clear in this group — it could be chance."
        return ui.div(
            ui.p(text, class_="summary-line"),
            ui.p(f"Based on {m['n']} residents with both years of ITE and an MKSAP account.", class_="hint"),
        )

    @render_plotly
    def thirds():
        x, m = w(), models()
        if x is None or m is None or not m["ok"]:
            return None
        by_pgy, pooled = stats.mksap_thirds(x)
        return plots.thirds_bar(by_pgy, pooled, input.outcome())

    @render_plotly
    def scatter():
        x, m = w(), models()
        if x is None or m is None or not m["ok"]:
            return None
        return plots.mksap_scatter(stats.mksap_points(x), input.outcome())

    @render.ui
    def correlations():
        m = models()
        if m is None or not m["ok"]:
            return None
        cur, gain, prev = m["rho_q_pc_cur"][0], m["rho_q_dpc"][0], m["rho_q_pc_prev"][0]
        gain_p = m["rho_q_dpc"][1]
        if gain_p >= 0.05:
            reading = (
                "The link between questions answered and the gain was not statistically clear here, so these "
                "data can't separate practice from prior ability."
            )
        elif abs(gain) > abs(prev):
            reading = (
                "Questions answered tracked the gain more than prior ability, so it is not only that stronger "
                "residents do more questions."
            )
        else:
            reading = (
                "Questions answered tracked prior ability at least as much as the gain — stronger residents may "
                "simply do more questions."
            )
        rows = [
            ("this year's ITE % correct", cur),
            ("change since last year", gain),
            ("last year's ITE % correct", prev),
        ]
        return ui.div(
            ui.h6("Is it just the strongest residents doing more questions?"),
            ui.tags.table(
                ui.tags.thead(
                    ui.tags.tr(ui.tags.th("Questions answered vs.", scope="col"), ui.tags.th("Spearman ρ", scope="col"))
                ),
                ui.tags.tbody(*[ui.tags.tr(ui.tags.td(a), ui.tags.td(f"{b:.2f}")) for a, b in rows]),
                class_="table table-sm data-table",
                style="max-width: 28rem",
            ),
            ui.p(reading, class_="hint"),
            ui.p(
                f"MKSAP accuracy: each point of MKSAP % correct went with {m['b_acc']:+.2f} ITE points "
                f"({_p(m['p_acc'])}).",
                class_="hint",
            ),
        )
