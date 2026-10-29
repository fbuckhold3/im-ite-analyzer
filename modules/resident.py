"""Resident report: a resident (or a PD, one resident at a time) uploads ACP Examinee Performance Report(s).

Optional: the program's Performance Report, which lets each missed question be compared with national results
(biggest misses / notable wins). ITE only — MKSAP exports are program-level (see Program analysis).
"""

from __future__ import annotations

from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from ite_core import demo, individual
from ite_core.limits import MAX_FILE_MB, PDF_EXT, UploadError, check_file
from ite_core.pdf_reports import parse_examinee_pdf, parse_program_pdf

from . import plots, resident_pdf
from .common import citation, fmt_num, fmt_prob, how_to_read, message, privacy_note, tier_badge, trajectory_table
from .upload_align import _take

BAND_CLASS = {"Strength": "band-high", "Typical": "band-mid", "Focus": "band-low"}


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
                ui.input_file(
                    "program_pdf",
                    "Program Performance Report (PDF, optional)",
                    accept=[".pdf"],
                    button_label="Choose PDF…",
                ),
                ui.p(
                    "Adding your program's Performance Report ranks your missed questions against national results. "
                    "It contains only program and national totals — ask your program director for it.",
                    class_="hint",
                ),
                ui.p(f"Up to {MAX_FILE_MB} MB per file. MKSAP analysis is available to programs.", class_="hint"),
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
                ui.output_ui("curve_section"),
                how_to_read(),
            ),
            col_widths=(4, 8),
        ),
        ui.output_ui("areas_section"),
        ui.output_ui("questions_section"),
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
    program = reactive.value(None)
    notes = reactive.value([])
    is_sample = reactive.value(False)

    # ------------------------------------------------------------------ intake
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
    @reactive.event(input.program_pdf)
    def _program():
        files = input.program_pdf() or []
        if not files:
            return
        up = _take(files[0])
        try:
            check_file(up.name, len(up.data), PDF_EXT, "PDF")
            program.set(parse_program_pdf(up.data, name=up.name))
        except UploadError as e:
            program.set(None)
            ui.notification_show(str(e), type="error", duration=10)
        except Exception:
            program.set(None)
            ui.notification_show(f"“{up.name}” could not be processed.", type="error", duration=10)

    @reactive.effect
    @reactive.event(input.sample)
    def _sample():
        reports.set(demo.sample_examinee_reports())
        program.set(demo.sample_resident_program_report())
        notes.set([])
        is_sample.set(True)

    @reactive.effect
    @reactive.event(input.clear)
    def _clear():
        reports.set([])
        program.set(None)
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
        return individual.analyze_examinee(rs[-1]) if rs else None

    @reactive.calc
    def ranking():
        rs = mine()
        return individual.rank_questions(rs[-1], program.get()) if rs and program.get() is not None else None

    @reactive.calc
    def hist():
        rs = mine()
        return individual.history(rs) if rs else None

    @render.ui
    def load_messages():
        items = [message(m, "error") for m in notes.get()]
        if is_sample.get():
            items.insert(
                0, message("Showing an invented sample resident (with a matching sample program report).", "info")
            )
        rs, p = mine(), program.get()
        if rs and p is not None and ranking() is None:
            items.append(
                message(
                    f"The Program Performance Report is for {p.get('exam_year')}, but this score report "
                    f"is for {rs[-1].get('exam_year')} — questions can't be ranked.",
                    "warning",
                )
            )
        elif p is not None and not is_sample.get():
            items.append(message(f"Program Performance Report loaded ({len(p['items'])} questions).", "info"))
        return ui.div(*items) if items else None

    # -------------------------------------------------------------- estimate
    @render.ui
    def estimate():
        a = analysis()
        if a is None:
            return message("Upload your ACP Examinee Performance Report (PDF), or try the sample report.")
        return ui.div(
            ui.p(ui.strong(a["name"] or "Resident"), f" · {a['exam_year']} ITE · PGY-{a['pgy']}", class_="who"),
            ui.div(
                ui.div(
                    ui.div(fmt_prob(a["pass_prob"]), class_="big-number"),
                    ui.div("estimated chance of passing ABIM on the first attempt", class_="hint"),
                    ui.div(tier_badge(a["risk_tier"])),
                ),
                ui.div(
                    ui.div(ui.span("Percent correct", class_="stat-label"), ui.span(f"{fmt_num(a['pct_correct'])}%")),
                    ui.div(ui.span("National percentile", class_="stat-label"), ui.span(fmt_num(a["percentile"]))),
                    class_="stat-row",
                ),
                class_="estimate-row",
            ),
            message(a["pgy_note"], "warning") if a["pgy_note"] else None,
            class_="result-card",
            aria_live="polite",
        )

    @render.ui
    def curve_section():
        a = analysis()
        if a is None:
            return None
        targets = individual.next_year_targets(a["pgy"])
        if targets:
            target_text = ui.p(individual.target_sentence(a["pct_correct"], targets), class_="target-line")
        else:
            target_text = ui.p(
                f"Low risk at PGY-{min(a['pgy'], 3)} starts at about {fmt_num(a['pct_needed_low_now'], 1)}% correct.",
                class_="hint",
            )
        h = hist()
        return ui.div(
            target_text,
            output_widget("curve"),
            ui.p(
                "Stars mark the score needed at each later PGY level to reach 90%. The same percent correct counts "
                "for less each year because each PGY curve is steeper.",
                class_="hint",
            )
            if targets
            else None,
            trajectory_table(h) if h is not None and len(h) > 1 else None,
        )

    @render_plotly
    def curve():
        a, h = analysis(), hist()
        if a is None:
            return None
        fig = plots.nomogram_figure()
        plots.set_points(fig, list(zip(h.PGY, h.Pct_Correct, h.Pass_Prob, strict=True)))
        return plots.add_targets(fig, individual.next_year_targets(a["pgy"]))

    # ------------------------------------------------------------ content areas
    @render.ui
    def areas_section():
        a = analysis()
        if a is None:
            return None
        t = a["areas"]
        columns = []
        for key in ("Strength", "Typical", "Focus"):
            d = t[t.standing == key].sort_values("percentile", ascending=False)
            chips = [
                ui.div(
                    ui.div(r.area, class_="chip-area"),
                    ui.div(
                        ui.span(f"{int(r.percentile)}", class_="chip-pctile"),
                        ui.span("th percentile", class_="chip-unit"),
                        ui.span(f" · {r.pct_correct}% correct", class_="chip-unit"),
                        ui.span(f" · {r.n_missed} missed", class_="chip-unit") if r.n_missed else None,
                    ),
                    class_="area-chip",
                )
                for r in d.itertuples()
            ] or [ui.p("None", class_="hint")]
            columns.append(ui.div(ui.h6(individual.BAND_LABEL[key]), *chips, class_=f"band-col {BAND_CLASS[key]}"))
        hvc = a["hvc"][0] if a["hvc"] else None
        return ui.card(
            ui.card_header("Content areas: your national percentile"),
            ui.div(*columns, class_="band-grid"),
            ui.p(
                (
                    f"High Value Care (overlaps the areas above): {hvc['percentile']}th percentile, "
                    f"{hvc['pct_correct']}% correct. "
                    if hvc
                    else ""
                )
                + "Percentile = your rank among U.S. residents at your PGY level this year (50 = middle).",
                class_="hint",
            ),
        )

    # ---------------------------------------------------------------- questions
    @render.ui
    def questions_section():
        a = analysis()
        if a is None:
            return None
        m = a["missed"]
        q = ranking()
        band = a["areas"].set_index("area").standing
        order = sorted(m.area.unique(), key=lambda x: (individual.BAND_ORDER.get(band.get(x), 1), x))
        panels = []
        for area in order:
            g = m[m.area == area]
            items = [
                ui.tags.li(o, ui.span(" HVC", class_="hvc-tag") if h else None)
                for o, h in zip(g.objective, g.hvc, strict=True)
            ]
            label = individual.BAND_LABEL.get(band.get(area), "")
            panels.append(
                ui.accordion_panel(
                    f"{area} — {len(g)} missed · {label}", ui.tags.ul(*items, class_="objectives"), value=area
                )
            )
        all_missed = ui.accordion(*panels, open=False, multiple=True) if panels else message("No missed objectives.")
        if q is None:
            return ui.card(
                ui.card_header(f"Missed objectives ({len(m)})"),
                ui.p(
                    "ACP lists the learning objective behind each question you missed (not the question itself), "
                    "grouped here with your weakest areas first. Add your program's Performance Report to see which "
                    "misses most residents nationally got right — your most fixable gaps.",
                    class_="hint",
                ),
                ui.accordion(*panels, open=[p for p in order if band.get(p) == "Focus"] or False, multiple=True),
            )

        def qlist(df, cls):
            return ui.tags.ol(
                *[
                    ui.tags.li(
                        ui.div(ui.span(r.objective), ui.span(" HVC", class_="hvc-tag") if r.hvc else None),
                        ui.div(
                            ui.span(r.area, class_="q-area"),
                            ui.span(
                                f"{int(r.national)}% of {q['pgy_label']} residents nationally got this right",
                                class_="q-nat",
                            ),
                        ),
                        ui.div(ui.div(class_="q-bar", style=f"width:{int(r.national)}%"), class_="q-track"),
                    )
                    for r in df.itertuples()
                ],
                class_=f"q-list {cls}",
            )

        return ui.card(
            ui.card_header("Your questions compared with national results"),
            ui.layout_columns(
                ui.div(
                    ui.h5(f"Biggest misses ({len(q['misses'])})"),
                    ui.p(
                        "Questions you missed that most residents at your level got right — usually the most "
                        "fixable gaps.",
                        class_="hint",
                    ),
                    qlist(q["misses"], "q-miss"),
                ),
                ui.div(
                    ui.h5(f"Notable wins ({len(q['wins'])})"),
                    ui.p("The hardest questions you got right — few residents at your level did.", class_="hint"),
                    qlist(q["wins"], "q-win"),
                ),
                col_widths=(7, 5),
            ),
            ui.tags.details(
                ui.tags.summary(f"All missed objectives ({len(m)}), by content area"), all_missed, class_="explainer"
            ),
            ui.p(
                f"Matched {q['matched']} of {q['missed_total']} missed objectives to the program report. ACP lists "
                "the learning objective behind each question, not the question itself.",
                class_="hint",
            ),
        )

    # --------------------------------------------------------------------- PDF
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
            yield resident_pdf.resident_pdf(resident_pdf.from_examinee(rs, program=program.get()))
