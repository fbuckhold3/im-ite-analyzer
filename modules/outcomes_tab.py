"""Program analysis → Board outcomes: ABIM certification results against what the ITE predicted.

Takers are linked to residents by name (ite_core.abim). Predicted = the estimated pass probability from each
graduate's last ITE before graduating (PGY-3 when available). Observational, small numbers: descriptive only.
The anonymous table shows no names; names appear only in the linking list, which only this program sees.
"""

from __future__ import annotations

import math

import pandas as pd
from htmltools import Tag, tags
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from ite_core import abim
from ite_core.nomogram import DEFAULT_CUTOFFS

from . import plots
from .common import citation, fmt_prob, message, tier_badge

NEED = (
    "Add your ABIM exam results (Examination Results report or Program Data Report, PDF) on Upload & Align, with "
    "the ACP rosters from your graduates' PGY-3 year."
)
NOT_OURS = "__not_ours__"


def _pct(x) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{round(100 * x):.0f}%"


def year_cards(summary: pd.DataFrame) -> Tag:
    """One card per exam year: predicted vs observed (linked takers), all takers, ABIM-reported rates."""
    cards = []
    for r in summary.itertuples():
        abim_line = (
            f"ABIM report: your program {int(r.program_rate)}% · all programs {int(r.all_rate)}%"
            if "program_rate" in summary and r.program_rate == r.program_rate and r.program_rate is not None
            else None
        )
        cards.append(
            tags.div(
                tags.div(f"{r.exam_year} ABIM exam", class_="oc-year"),
                tags.div(
                    tags.div(
                        tags.div(fmt_prob(r.predicted), class_="oc-num"),
                        tags.div("Predicted from the ITE", class_="oc-lab"),
                        class_="oc-cell",
                    ),
                    tags.div(
                        tags.div(_pct(r.observed_linked), class_="oc-num oc-obs"),
                        tags.div("Actually passed", class_="oc-lab"),
                        class_="oc-cell",
                    ),
                    class_="oc-pair",
                ),
                tags.p(
                    f"Among {r.linked} of {r.takers} takers linked to an ITE record. All takers: {r.passes} of "
                    f"{r.takers} passed ({_pct(r.observed)}).",
                    class_="oc-note",
                ),
                tags.p(abim_line, class_="oc-note") if abim_line else None,
                class_="oc-card",
            )
        )
    return tags.div(*cards, class_="oc-cards")


def tier_table(bt: pd.DataFrame) -> Tag:
    head = ["Predicted from last ITE", "Graduates", "Passed", "Pass rate", "Average estimate"]
    rows = [
        tags.tr(
            tags.td(tier_badge(r.tier)),
            tags.td(str(r.n), class_="num"),
            tags.td(str(r.passed) if r.n else "—", class_="num"),
            tags.td(_pct(r.observed), class_="num"),
            tags.td(fmt_prob(r.predicted), class_="num"),
        )
        for r in bt.itertuples()
    ]
    return tags.table(
        tags.thead(tags.tr(*[tags.th(h, scope="col") for h in head])),
        tags.tbody(*rows),
        class_="table table-sm data-table oc-tiers",
    )


def anon_table(t: pd.DataFrame) -> Tag:
    """Linked takers without names, highest estimate first within each exam year."""
    d = t[t.predicted.notna()]
    has_mk = d.mk_answered.notna().any()
    has_score = d.score.notna().any() or d.withheld.any()
    head = ["Exam", "Last ITE", "% correct", "Percentile", "Estimated pass"]
    head += ["MKSAP questions", "MKSAP accuracy"] if has_mk else []
    head += ["ABIM result"] + (["ABIM score"] if has_score else [])
    rows = []
    for r in d.itertuples():
        cells = [
            str(r.exam_year),
            f"PGY-{int(r.ite_pgy)} ({int(r.ite_year)})",
            f"{r.ite_pct:.0f}%",
            "—" if r.ite_ile != r.ite_ile else f"{r.ite_ile:.0f}",
            fmt_prob(r.predicted),
        ]
        if has_mk:
            cells += [
                "—" if r.mk_answered != r.mk_answered else f"{r.mk_answered:,.0f}",
                "—" if r.mk_pct_correct != r.mk_pct_correct else f"{r.mk_pct_correct:.0f}%",
            ]
        result = tags.span("Pass" if r.passed else "Did not pass", class_=f"oc-res oc-{'pass' if r.passed else 'fail'}")
        cells.append(result)
        if has_score:
            cells.append("withheld" if r.withheld else ("—" if r.score != r.score else f"{r.score:.0f}"))
        rows.append(tags.tr(*[tags.td(c, class_=None if i in (0, 1) else "num") for i, c in enumerate(cells)]))
    return tags.div(
        tags.table(
            tags.thead(tags.tr(*[tags.th(h, scope="col") for h in head])),
            tags.tbody(*rows),
            class_="table table-sm data-table oc-anon",
        ),
        class_="items-scroll",
    )


@module.ui
def outcomes_ui():
    return ui.div(
        ui.output_ui("empty"),
        ui.output_ui("body"),
        ui.card(
            ui.card_header("Predicted chance vs actual result"),
            ui.p(
                "Each dot is one graduate linked to an ITE record, placed by the pass estimate from their last ITE "
                "before graduating. No names.",
                class_="hint",
            ),
            output_widget("strip"),
            class_="results-card",
        ),
        ui.output_ui("score_card"),
        ui.output_ui("table_card"),
        ui.output_ui("link_card"),
        ui.div(citation(), class_="source-box"),
    )


@module.server
def outcomes_server(input, output, session, dataset, abim_data):
    overrides: reactive.Value[dict] = reactive.value({})

    @reactive.calc
    def base():
        ds, ab = dataset(), abim_data()
        if ds is None or ab is None:
            return None
        cands, years = ab
        long = ds.rosters.long
        return cands, years, long, abim.link(cands, long), (ds.mksap.people if ds.mksap is not None else None)

    @reactive.calc
    def outcomes():
        b = base()
        if b is None:
            return None
        cands, years, long, links, mk_people = b
        links = abim.apply_links(links, overrides.get())
        t = abim.outcome_table(cands, links, long, mk_people)
        return dict(
            table=t,
            summary=abim.year_summary(t, years),
            tiers=abim.by_predicted_tier(t, DEFAULT_CUTOFFS),
            years=years,
            links=links,
            cands=cands,
            long=long,
        )

    @render.ui
    def empty():
        return message(NEED) if outcomes() is None else None

    @render.ui
    def body():
        o = outcomes()
        if o is None:
            return None
        return ui.card(
            ui.card_header("Board outcomes: predicted vs observed pass rate"),
            year_cards(o["summary"]),
            ui.h6("Outcomes by predicted risk tier", class_="mt-3"),
            tier_table(o["tiers"]),
            ui.p(
                "Predicted = the average estimated chance of passing from each graduate's last ITE before graduating "
                "(an approximation of McDonald et al. 2020). With 20–30 graduates a year, a few results move the rate "
                "by several points: read this as a check on the estimate, not a verdict on the program.",
                class_="hint",
            ),
            class_="results-card",
        )

    @render_plotly
    def strip():
        o = outcomes()
        return None if o is None else plots.outcome_strip(o["table"])

    @render.ui
    def score_card():
        o = outcomes()
        if o is None or not o["table"].score.notna().any():
            return None
        return ui.card(
            ui.card_header("ABIM score vs last ITE"),
            ui.p("Program Data Report years only; scores the candidate withheld are not shown.", class_="hint"),
            output_widget("scores"),
            class_="results-card",
        )

    @render_plotly
    def scores():
        o = outcomes()
        if o is None:
            return None
        ps = o["years"].passing_score.dropna()
        return plots.abim_score_scatter(o["table"], int(ps.iloc[0]) if len(ps) else None)

    @render.ui
    def table_card():
        o = outcomes()
        if o is None or not o["table"].predicted.notna().any():
            return None
        return ui.card(
            ui.card_header("Each graduate: estimate, MKSAP and result (no names)"),
            anon_table(o["table"]),
            ui.p(
                "Last ITE = the most recent ITE before graduating. MKSAP = the graduate's account in your MKSAP "
                "export, matched by name (exact or probable matches only); the export reflects activity up to the "
                "day it was downloaded, which may be after the ABIM exam.",
                class_="hint",
            ),
            class_="results-card",
        )

    @render.ui
    def link_card():
        o = outcomes()
        if o is None:
            return None
        links, cands, long = o["links"], o["cands"], o["long"]
        open_rows = links[links.ID.isna() & (links.tier != "Not ours")]
        manual = links[links.tier.isin(["Manual", "Not ours"])]
        grads = abim.graduates(long, cands.exam_year.unique())
        taken = set(links.ID.dropna())
        free = grads[~grads.ID.isin(taken)].sort_values("Name")
        label = {str(r.ID): f"{r.Name} (class of {int(r.Grad_Class)})" for r in free.itertuples()}
        rows = []
        for r in open_rows.itertuples():
            c = cands[cands.key == r.key].iloc[0]
            suggested = str(r.suggested) if isinstance(r.suggested, str) and str(r.suggested) in label else None
            options = [ui.tags.option("Choose the resident…", value="")] + [
                ui.tags.option(lab, value=rid, selected=rid == suggested) for rid, lab in label.items()
            ]
            options.append(ui.tags.option("Not one of our ITE residents", value=NOT_OURS))
            send = (
                f"Shiny.setInputValue('{session.ns('link_action')}', {{key: {r.key!r}, id: %s, "
                "n: Math.random()}, {priority: 'event'})"
            )
            rows.append(
                ui.div(
                    ui.div(
                        ui.strong(c["name"]),
                        ui.span(f" · {int(c.exam_year)} exam", class_="hint"),
                        ui.span("Suggested match", class_="chip chip-probable oc-sugg") if suggested else None,
                    ),
                    ui.div(
                        ui.tags.select(
                            *options,
                            class_="form-select form-select-sm",
                            onchange=send % "this.value",
                            **{"aria-label": f"Resident for {c['name']}"},
                        ),
                        ui.tags.button(
                            "Confirm",
                            type="button",
                            class_="btn btn-sm btn-success",
                            onclick=send % "this.previousElementSibling.value",
                        )
                        if suggested
                        else None,
                        class_="oc-link-controls",
                    ),
                    class_="oc-link-row",
                )
            )
        n_sugg = int(open_rows.suggested.notna().sum()) if "suggested" in open_rows else 0
        done = len(manual)
        if not rows and not done:
            return None
        return ui.card(
            ui.card_header(f"Link ABIM takers to residents ({len(rows)} to review)"),
            ui.p(
                "Exact name matches are linked automatically. Suggested matches (similar names) and takers with no "
                "match are left out of the outcomes until you confirm or choose the resident — a different first "
                "name, a name change, or a missing PGY-3 roster are the usual reasons. Names stay in this session.",
                class_="hint",
            ),
            ui.input_action_button(
                "confirm_suggested", f"Confirm all suggestions ({n_sugg})", class_="btn-outline-success btn-sm mb-2"
            )
            if n_sugg
            else None,
            *rows,
            ui.p(f"{done} decided by you.", class_="hint") if done else None,
            ui.input_action_button("reset_links", "Undo my links", class_="btn-outline-secondary btn-sm")
            if done
            else None,
            class_="results-card",
        )

    @reactive.effect
    @reactive.event(input.confirm_suggested)
    def _confirm_suggested():
        o = outcomes()
        if o is None:
            return
        links = o["links"]
        sugg = links[links.ID.isna() & links.suggested.notna() & (links.tier == "Probable")]
        d = dict(overrides.get())
        d.update({k: s for k, s in zip(sugg.key, sugg.suggested, strict=True)})
        overrides.set(d)

    @reactive.effect
    @reactive.event(input.link_action)
    def _link():
        a = input.link_action()
        if not a or not a.get("id"):
            return
        d = dict(overrides.get())
        d[a["key"]] = None if a["id"] == NOT_OURS else a["id"]
        overrides.set(d)

    @reactive.effect
    @reactive.event(input.reset_links)
    def _reset():
        overrides.set({})

    return outcomes
