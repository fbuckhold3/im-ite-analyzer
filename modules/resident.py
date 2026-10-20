"""My ITE report: a resident uploads their ACP Examinee Performance Report(s). ITE only — MKSAP exports are
program-level, so MKSAP analysis lives under Program data."""

from __future__ import annotations

from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from ite_core import demo, individual
from ite_core.limits import MAX_FILE_MB, PDF_EXT, UploadError, check_file
from ite_core.pdf_reports import parse_examinee_pdf

from . import plots, resident_pdf
from .common import citation, fmt_num, fmt_prob, how_to_read, message, privacy_note, tier_badge, trajectory_table
from .upload_align import _take

STANDING_ORDER = {"Focus": 0, "Typical": 1, "Strength": 2}


@module.ui
def resident_ui():
    return ui.div(
        ui.layout_columns(
            ui.card(
                ui.card_header("Your ITE report"),
                privacy_note(),
                ui.input_file(
                    "reports",
                    "ACP Examinee Performance Report (PDF) — add earlier years too",
                    multiple=True,
                    accept=[".pdf"],
                    button_label="Choose PDF…",
                ),
                ui.p(
                    f"Up to {MAX_FILE_MB} MB per file. MKSAP analysis is available to programs under Program data.",
                    class_="hint",
                ),
                ui.div(
                    ui.input_action_button("sample", "Try a sample report", class_="btn-outline-primary btn-sm"),
                    ui.input_action_button("clear", "Clear", class_="btn-outline-secondary btn-sm"),
                    class_="button-row no-print",
                ),
                ui.output_ui("load_messages"),
                ui.output_ui("picker"),
                class_="no-print",
            ),
            ui.card(
                ui.card_header("Board-pass estimate"),
                ui.output_ui("estimate"),
                how_to_read(),
            ),
            col_widths=(4, 8),
        ),
        ui.output_ui("areas_section"),
        ui.output_ui("missed_section"),
        ui.output_ui("history_section"),
        ui.div(
            citation(),
            ui.p(
                "Pass estimates are a logistic fit to the McDonald et al. curves (2014–2015 cohorts), use percent "
                "correct only, and describe groups of residents — not a prediction for any one person. Educational "
                "use only.",
                class_="hint",
            ),
            ui.div(
                ui.output_ui("pdf_button"),
                ui.tags.button("Print page", class_="btn btn-outline-secondary btn-sm", onclick="window.print()"),
                class_="button-row no-print",
            ),
            class_="source-box",
        ),
        class_="resident-page",
    )


@module.server
def resident_server(input, output, session):
    reports = reactive.value([])
    notes = reactive.value([])
    is_sample = reactive.value(False)

    @reactive.effect
    @reactive.event(input.reports)
    def _reports():
        found, msgs = [], []
        for f in input.reports() or []:
            up = _take(f)
            try:
                check_file(up.name, len(up.data), PDF_EXT, "PDF")
                found.extend(parse_examinee_pdf(up.data, name=up.name))
            except UploadError as e:
                msgs.append(str(e))
            except Exception:
                msgs.append(f"“{up.name}” could not be processed.")
        reports.set(found)
        notes.set(msgs)
        is_sample.set(False)

    @reactive.effect
    @reactive.event(input.sample)
    def _sample():
        reports.set(demo.sample_examinee_reports())
        notes.set([])
        is_sample.set(True)

    @reactive.effect
    @reactive.event(input.clear)
    def _clear():
        reports.set([])
        notes.set([])
        is_sample.set(False)

    @reactive.calc
    def groups():
        return individual.group_by_resident(reports.get())

    @render.ui
    def picker():
        g = groups()
        if len(g) < 2:
            return None
        choices = {
            cid: f"{rs[-1]['name']} (PGY-{rs[-1]['pgy']})"
            for cid, rs in sorted(g.items(), key=lambda kv: kv[1][-1]["name"] or "")
        }
        return ui.input_selectize("who", f"This file has {len(g)} residents — choose one", choices)

    @render.ui
    def pdf_button():
        if not mine():
            return None
        return ui.download_button("pdf", "Download PDF", class_="btn-primary btn-sm")

    @render.download_button(
        filename=lambda: resident_pdf.pdf_filename(resident_pdf.from_examinee(mine())), media_type="application/pdf"
    )
    def pdf():
        rs = mine()
        if rs:
            yield resident_pdf.resident_pdf(resident_pdf.from_examinee(rs))

    @reactive.calc
    def mine():
        g = groups()
        if not g:
            return None
        cid = next(iter(g)) if len(g) == 1 else (input.who() if "who" in input else None)
        return g.get(cid)

    @reactive.calc
    def analysis():
        rs = mine()
        if not rs:
            return None
        return individual.analyze_examinee(rs[-1])

    @render.ui
    def load_messages():
        items = [message(m, "error") for m in notes.get()]
        if is_sample.get():
            items.insert(0, message("Showing an invented sample resident.", "info"))
        return ui.div(*items) if items else None

    # ---------------------------------------------------------------- results
    @render.ui
    def estimate():
        a = analysis()
        if a is None:
            return message("Upload your ACP Examinee Performance Report (PDF), or try the sample report.")
        nxt = (
            f" Next year (PGY-{a['pgy'] + 1}) it takes about {fmt_num(a['pct_needed_low_next'], 1)}%."
            if a["pct_needed_low_next"]
            else ""
        )
        return ui.div(
            ui.p(ui.strong(a["name"] or "Resident"), f" · {a['exam_year']} ITE · PGY-{a['pgy']}", class_="who"),
            ui.div(fmt_prob(a["pass_prob"]), class_="big-number"),
            ui.div("estimated chance of passing ABIM on the first attempt", class_="hint"),
            ui.div(tier_badge(a["risk_tier"])),
            ui.div(
                ui.div(ui.span("Percent correct", class_="stat-label"), ui.span(f"{fmt_num(a['pct_correct'])}%")),
                ui.div(ui.span("National percentile", class_="stat-label"), ui.span(fmt_num(a["percentile"]))),
                class_="stat-row",
            ),
            ui.p(
                f"Low risk at PGY-{min(a['pgy'], 3)} starts at about "
                f"{fmt_num(a['pct_needed_low_now'], 1)}% correct.{nxt}",
                class_="hint",
            ),
            message(a["pgy_note"], "warning") if a["pgy_note"] else None,
            class_="result-card",
            aria_live="polite",
        )

    @render.ui
    def areas_section():
        a = analysis()
        if a is None:
            return None
        s, f = a["strengths"], a["focus_areas"]
        return ui.card(
            ui.card_header("Content areas: your national percentile"),
            ui.p(
                ui.strong("Strengths: "),
                ", ".join(s) if s else "none above the 60th percentile this year",
                ui.br(),
                ui.strong("Focus areas: "),
                ", ".join(f),
                class_="summary-line",
            ),
            output_widget("areas_plot"),
            ui.output_ui("areas_table"),
        )

    @render_plotly
    def areas_plot():
        a = analysis()
        return None if a is None else plots.area_percentile_figure(a["areas"])

    @render.ui
    def areas_table():
        a = analysis()
        if a is None:
            return None
        t = a["areas"]
        head = ["Content area", "You", "National mean", "SD", "Percentile", "Standing", "Missed"]
        rows = []
        for r in t.itertuples():
            cells = [
                r.area,
                f"{r.pct_correct}%",
                f"{r.national_mean}%",
                str(r.national_sd),
                str(r.percentile),
                ui.span(r.standing, class_=f"standing standing-{r.standing.lower()}"),
                str(r.n_missed),
            ]
            rows.append(ui.tags.tr(*[ui.tags.td(c) for c in cells]))
        hvc = a["hvc"][0] if a["hvc"] else None
        return ui.div(
            ui.tags.table(
                ui.tags.thead(ui.tags.tr(*[ui.tags.th(h, scope="col") for h in head])),
                ui.tags.tbody(*rows),
                class_="table table-sm data-table",
            ),
            ui.p(
                f"High Value Care (overlaps the areas above): {hvc['pct_correct']}% correct, "
                f"{hvc['percentile']}th percentile."
                if hvc
                else "",
                " Strength = 60th percentile or above; Focus = below the 35th (or your two lowest areas).",
                class_="hint",
            ),
        )

    @render.ui
    def missed_section():
        a = analysis()
        if a is None:
            return None
        m = a["missed"]
        if m.empty:
            return ui.card(ui.card_header("Missed objectives"), message("No missed objectives were listed."))
        standing = a["areas"].set_index("area").standing
        areas = sorted(m.area.unique(), key=lambda x: (STANDING_ORDER.get(standing.get(x), 1), x))
        panels = []
        for area in areas:
            g = m[m.area == area]
            items = [
                ui.tags.li(o, ui.span(" HVC", class_="hvc-tag") if h else None)
                for o, h in zip(g.objective, g.hvc, strict=True)
            ]
            st = standing.get(area)
            title = f"{area} — {len(g)} missed" + (f" · {st}" if st and st != "Typical" else "")
            panels.append(ui.accordion_panel(title, ui.tags.ul(*items, class_="objectives"), value=area))
        open_ = [p for p in areas if standing.get(p) == "Focus"]
        return ui.card(
            ui.card_header(f"Missed objectives ({len(m)})"),
            ui.p(
                "ACP lists the learning objective behind each item you missed — not the question itself. "
                "Focus areas are listed first. HVC = also counts toward High Value Care.",
                class_="hint",
            ),
            ui.accordion(*panels, open=open_ or False, multiple=True),
        )

    @reactive.calc
    def hist():
        rs = mine()
        return individual.history(rs) if rs else None

    @render.ui
    def history_section():
        h = hist()
        if h is None or h.empty:
            return None
        title = "Over time" if len(h) > 1 else "Your score on the board-pass curves"
        tip = None if len(h) > 1 else ui.p("Add earlier years' reports to see your trajectory.", class_="hint")
        return ui.card(ui.card_header(title), output_widget("history_plot"), trajectory_table(h), tip)

    @render_plotly
    def history_plot():
        h = hist()
        if h is None:
            return None
        fig = plots.nomogram_figure()
        plots.set_points(fig, list(zip(h.PGY, h.Pct_Correct, h.Pass_Prob, strict=True)))
        return fig
