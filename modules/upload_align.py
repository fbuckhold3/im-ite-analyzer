"""Program data → Upload & Align: rosters (+ MKSAP, + saved crosswalk) → reviewed dataset for later tabs.

Privacy: Shiny writes each upload to a temporary file; we read it into memory and delete the file at once.
Nothing here logs or prints data.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import pandas as pd
from shiny import module, reactive, render, ui

from ite_core import abim, demo, detect, names
from ite_core import mksap as mksap_mod
from ite_core import session as S
from ite_core.limits import MAX_FILE_MB, UploadError

from .common import message, mksap_howto, privacy_note

NO_ACCOUNT = "__none__"
TIER_ORDER = {"Ambiguous": 0, "Unmatched": 1, "Probable": 2, "Manual": 3, "Exact": 4}


def _take(fileinfo: dict) -> S.Upload:
    """Read an uploaded temp file into memory, then delete it."""
    path = Path(fileinfo["datapath"])
    try:
        return S.Upload(name=fileinfo["name"], data=path.read_bytes())
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)


ACCEPT = [".xlsx", ".xls", ".csv", ".pdf"]


@module.ui
def upload_ui():
    return ui.div(
        ui.layout_columns(
            ui.card(
                ui.card_header("1 · Add your files"),
                privacy_note(),
                ui.div(
                    ui.input_file(
                        "dropped",
                        "Drop your files here — the app works out what each one is.",
                        multiple=True,
                        accept=ACCEPT,
                        button_label="Add files…",
                        width="100%",
                    ),
                    class_="dropzone",
                ),
                ui.p(
                    f"Add files any time — each drop adds to the files below (a file with the same name replaces "
                    f"the earlier one). Spreadsheets (.xlsx, .xls, .csv) and PDFs, up to {MAX_FILE_MB} MB each.",
                    class_="hint",
                ),
                ui.output_ui("session_files"),
                ui.output_ui("checklist"),
                ui.output_ui("intake_notes"),
                ui.div(
                    ui.input_action_button("demo", "Load demo data", class_="btn-outline-primary btn-sm"),
                    ui.input_action_button("clear", "Start over", class_="btn-outline-secondary btn-sm"),
                    class_="button-row",
                ),
                ui.p("Demo data is invented — no real residents.", class_="hint"),
            ),
            ui.card(
                ui.card_header("2 · What we found"),
                ui.output_ui("files"),
                ui.output_ui("mksap_status"),
                ui.output_ui("program_status"),
                ui.output_ui("coverage"),
            ),
            col_widths=(5, 7),
        ),
        ui.output_ui("match_section"),
    )


@module.server
def upload_server(input, output, session):
    roster_ups: reactive.Value[list[S.Upload]] = reactive.value([])
    mksap_up: reactive.Value[S.Upload | None] = reactive.value(None)
    prior_cw: reactive.Value[pd.DataFrame | None] = reactive.value(None)
    cw_name: reactive.Value[str | None] = reactive.value(None)
    crosswalk: reactive.Value[pd.DataFrame | None] = reactive.value(None)
    is_demo = reactive.value(False)
    program: reactive.Value[dict | None] = reactive.value(None)
    program_err: reactive.Value[str | None] = reactive.value(None)
    abim_reps: reactive.Value[list[dict]] = reactive.value([])  # parsed ABIM reports
    # files that were not loaded: (file name, why)
    skipped: reactive.Value[list[tuple[str, str]]] = reactive.value([])

    # ------------------------------------------------------------------ intake
    def _load_program(up: S.Upload):
        try:
            program.set(S.load_program_report(up))
            program_err.set(None)
        except UploadError as e:
            program.set(None)
            program_err.set(str(e))
        except Exception:
            program.set(None)
            program_err.set(f"“{up.name}” could not be processed.")

    def _load_crosswalk(up: S.Upload) -> str | None:
        try:
            prior_cw.set(S.read_crosswalk(up))
            cw_name.set(up.name)
            ui.notification_show("Crosswalk loaded — your earlier MKSAP decisions were applied.", type="message")
            return None
        except UploadError as e:
            return str(e)

    @reactive.effect
    @reactive.event(input.dropped)
    def _intake():
        """Route each dropped file by what it is. New files add to (or replace same-named) files already here."""
        ups = [_take(f) for f in input.dropped() or []]
        if is_demo.get():
            _reset()
        got = detect.sort_uploads(ups)
        new_names = {u.name for u in got[detect.ROSTER]}
        rosters_now = [r for r in roster_ups.get() if r.name not in new_names] + got[detect.ROSTER]
        if got[detect.MKSAP] is not None:
            mksap_up.set(got[detect.MKSAP])
        if got[detect.PROGRAM] is not None:
            _load_program(got[detect.PROGRAM])
        notes = list(got["skipped"])
        if got[detect.ABIM]:
            reps = {r["file"]: r for r in abim_reps.get()}
            for up in got[detect.ABIM]:
                try:
                    reps[up.name] = abim.parse_abim_pdf(up.data, up.name)
                except UploadError as e:
                    notes.append((up.name, str(e).removeprefix(f"“{up.name}” ")))
                except Exception:
                    notes.append((up.name, "could not be processed."))
            abim_reps.set(list(reps.values()))
        if got[detect.CROSSWALK] is not None:
            err = _load_crosswalk(got[detect.CROSSWALK])
            if err:
                notes.append((got[detect.CROSSWALK].name, err))
        roster_ups.set(rosters_now)
        skipped.set(notes)

    def _reset():
        roster_ups.set([])
        mksap_up.set(None)
        prior_cw.set(None)
        cw_name.set(None)
        crosswalk.set(None)
        program.set(None)
        program_err.set(None)
        skipped.set([])
        abim_reps.set([])
        is_demo.set(False)

    @reactive.effect
    @reactive.event(input.demo)
    def _demo():
        _reset()
        d = demo.make_demo()
        roster_ups.set([S.Upload(n, b) for n, b in d["rosters"]])
        mksap_up.set(S.Upload(*d["mksap"]))
        program.set(demo.sample_program_report())
        abim_reps.set(demo.sample_abim_reports())
        is_demo.set(True)

    @reactive.effect
    @reactive.event(input.clear)
    def _clear():
        _reset()

    # ------------------------------------------------------------- processing
    @reactive.calc
    def rosters() -> S.Rosters | None:
        ups = roster_ups.get()
        if not ups:
            return None
        with_years = []
        for i, u in enumerate(ups):
            key = f"year_{i}"
            yr = input[key]() if key in input else None
            with_years.append(S.Upload(u.name, u.data, int(yr) if yr else None))
        try:
            return S.load_rosters(with_years)
        except UploadError as e:
            ui.notification_show(str(e), type="error", duration=10)
            return None

    @reactive.calc
    def mksap() -> tuple[S.Mksap | None, str | None]:
        up = mksap_up.get()
        if up is None:
            return None, None
        try:
            return S.load_mksap(up), None
        except UploadError as e:
            return None, str(e)
        except Exception:
            return None, f"“{up.name}” could not be processed."

    @reactive.effect
    def _propose():
        r, (mk, _) = rosters(), mksap()
        prior = prior_cw.get()
        if r is None or r.current_year is None or mk is None:
            crosswalk.set(None)
            return
        with reactive.isolate():  # keep decisions already made this session (e.g. after a year fix)
            current = crosswalk.get()
        if current is not None and current.confirmed_by_user.any():
            mine = current[current.confirmed_by_user]
            prior = mine if prior is None else pd.concat([prior, mine]).drop_duplicates("acp_id", keep="last")
        crosswalk.set(S.match(r, mk, prior))

    @reactive.calc
    def dataset() -> S.Dataset | None:
        r = rosters()
        if r is None or r.current_year is None:
            return None
        mk, _ = mksap()
        cw = crosswalk.get()
        return S.Dataset(rosters=r, mksap=mk, crosswalk=cw, wide=S.build_wide(r, mk, cw))

    # ---------------------------------------------------------- session files
    @render.ui
    def session_files():
        """Every file loaded in this session, what it was recognized as, and a ✕ to remove just that one."""
        items = [(detect.ROSTER, u.name) for u in roster_ups.get()]
        if mksap_up.get() is not None:
            items.append((detect.MKSAP, mksap_up.get().name))
        if program.get() is not None:
            items.append((detect.PROGRAM, program.get().get("file") or "Program Performance Report"))
        items += [(detect.ABIM, r["file"]) for r in abim_reps.get()]
        if cw_name.get():
            items.append((detect.CROSSWALK, cw_name.get()))
        if not items:
            return None
        rows = []
        for kind, name in items:
            js = (
                f"Shiny.setInputValue('{session.ns('remove_file')}', {{kind: {kind!r}, name: {name!r}, "
                "n: Math.random()}, {priority: 'event'})"
            )
            rows.append(
                ui.tags.li(
                    ui.span(detect.LABEL[kind], class_=f"sf-kind sf-{kind}"),
                    ui.span(name, class_="sf-name"),
                    ui.tags.button(
                        "✕",
                        type="button",
                        class_="sf-remove",
                        onclick=js,
                        title=f"Remove {name}",
                        **{"aria-label": f"Remove {name}"},
                    ),
                    class_="sf-row",
                )
            )
        return ui.div(
            ui.div(ui.strong(f"Files in this session ({len(items)})"), class_="sf-head"),
            ui.tags.ul(*rows, class_="sf-list"),
            class_="session-files",
        )

    @reactive.effect
    @reactive.event(input.remove_file)
    def _remove_file():
        a = input.remove_file() or {}
        kind, name = a.get("kind"), a.get("name")
        if kind == detect.ROSTER:
            roster_ups.set([u for u in roster_ups.get() if u.name != name])
        elif kind == detect.MKSAP:
            mksap_up.set(None)
        elif kind == detect.PROGRAM:
            program.set(None)
            program_err.set(None)
        elif kind == detect.ABIM:
            abim_reps.set([r for r in abim_reps.get() if r["file"] != name])
        elif kind == detect.CROSSWALK:
            prior_cw.set(None)
            cw_name.set(None)

    # -------------------------------------------------------------- checklist
    def _item(state, title, req, what, where, status, unlocks=None, extra=None):
        """One checklist entry. state: done / todo / suggest / error."""
        icon = {"done": "✓", "todo": "○", "suggest": "+", "error": "!"}[state]
        done = state == "done"
        return ui.tags.li(
            ui.span(icon, class_=f"check-icon check-{state}", aria_hidden="true"),
            ui.div(
                ui.div(
                    ui.strong(title),
                    ui.span(req, class_="file-opt" if req == "optional" else "file-req"),
                    class_="check-title",
                ),
                None if done else ui.p(what, class_="check-what"),
                None if done else ui.p(ui.span("Where: ", class_="check-k"), where, class_="check-where"),
                ui.p(status, class_=f"check-status status-{state}") if status else None,
                ui.p(ui.span("Unlocks: ", class_="check-k"), unlocks, class_="check-unlocks")
                if unlocks and not done
                else None,
                None if done else extra,
                class_="check-body",
            ),
            class_=f"check-item check-item-{state}",
        )

    @render.ui
    def checklist():
        r = rosters()
        mk, mk_err = mksap()
        rep, rep_err = program.get(), program_err.get()
        have_rosters = r is not None and r.current_year is not None
        if have_rosters:
            years = sorted(int(y) for y in r.long.Exam_Year.unique())
            r_state, r_status = "done", f"{len(years)} year(s) loaded: {', '.join(map(str, years))}."
        elif r is not None:
            r_state, r_status = "error", "No roster could be read — see What we found."
        else:
            r_state, r_status = "todo", "Needed for everything on the program pages."

        def optional(obj, err, done_text, missing_text):
            if err:
                return "error", err
            if obj is not None:
                return "done", done_text
            return ("suggest", missing_text) if have_rosters else ("todo", None)

        mk_state, mk_status = optional(
            mk,
            mk_err,
            f"{len(mk.people):,} accounts ({mksap_mod.KIND_LABEL[mk.kind]})." if mk else "",
            "Add it to see MKSAP progress and how MKSAP volume relates to ITE scores.",
        )
        rep_state, rep_status = optional(
            rep,
            rep_err,
            f"{rep.get('exam_year') or ''} report, {len(rep['items'])} items.".strip() if rep else "",
            "Add it to see which content areas and questions fell furthest below national.",
        )
        cw_state = "done" if prior_cw.get() is not None else "todo"
        reps = abim_reps.get()
        if reps:
            ab_state = "done"
            ab_status = (
                "Exam years: "
                + ", ".join(str(r["exam_year"]) for r in sorted(reps, key=lambda r: r["exam_year"] or 0))
                + "."
            )
        else:
            ab_state, ab_status = (
                ("suggest", "Add it to compare predicted and actual board pass rates.")
                if have_rosters
                else ("todo", None)
            )
        return ui.tags.ol(
            _item(
                r_state,
                "ACP roster",
                "required",
                "The ACP Downloadable Roster with Score Results — one spreadsheet per exam year, each resident's "
                "scores and percentiles. Add every year you have for trends and class tracking.",
                "your program's IM-ITE score results from ACP (.xlsx or .csv).",
                r_status,
                "Trends by level, Classes, Year over year, Board pass, Reports.",
            ),
            _item(
                rep_state,
                "Program Performance Report",
                "optional",
                "ACP's program-level PDF: content-area ranks among programs and every question's program vs "
                "national % correct. No resident names.",
                "the same ACP score results, as a PDF.",
                rep_status,
                "Item gaps.",
            ),
            _item(
                mk_state,
                "MKSAP export",
                "optional",
                "Your program's MKSAP Digital activity — the members overview or the full detail (.csv). Residents "
                "can't export their own.",
                "MKSAP Tracker → Members → Export Overview (or Export Details).",
                mk_status,
                "MKSAP.",
                extra=mksap_howto(),
            ),
            _item(
                ab_state,
                "ABIM exam results",
                "optional",
                "ABIM's program reports for the Internal Medicine Certification Exam — the Examination Results "
                "report (pass/fail) or the Program Data Report (adds scores). Add one per exam year. Graduates are "
                "linked to their ITE by name; include the rosters from their PGY-3 year.",
                "ABIM's program reports for your program (PDF).",
                ab_status,
                "Board outcomes.",
            ),
            _item(
                cw_state,
                "Saved MKSAP crosswalk",
                "optional",
                "Only if you've used the app before: the matching file you downloaded after reviewing MKSAP "
                "matches. It reapplies your decisions.",
                "the .csv you saved from this page last time.",
                f"Loaded “{cw_name.get()}”." if cw_state == "done" else None,
            ),
            class_="checklist",
            aria_label="What to upload",
        )

    @render.ui
    def intake_notes():
        notes = skipped.get()
        if not notes:
            return None
        return ui.div(
            ui.strong(f"{len(notes)} file(s) not added"),
            ui.tags.ul(*[ui.tags.li(ui.strong(f"“{n}”"), " ", why) for n, why in notes]),
            class_="msg msg-warning",
            role="status",
        )

    # ------------------------------------------------------------------ files
    @render.ui
    def files():
        r = rosters()
        if r is None:
            return message("Upload one or more ACP roster files, or load the demo data.")
        rows = []
        for i, f in enumerate(r.files.itertuples()):
            needs_year = f.status == "error" and pd.isna(f.year) and "enter it" in f.message
            year_cell = (
                ui.input_numeric(f"year_{i}", None, value=None, min=2000, max=2100, width="7em")
                if needs_year
                else (str(int(f.year)) if pd.notna(f.year) else "—")
            )
            ok = f.status == "ok"
            rows.append(
                ui.tags.tr(
                    ui.tags.td(
                        ui.span("✓" if ok else "✕", class_="ok" if ok else "bad", aria_hidden="true"), " ", f.file
                    ),
                    ui.tags.td(year_cell),
                    ui.tags.td(str(f.kept) if ok else "—"),
                    ui.tags.td(f.message or ("" if ok else "")),
                    class_=None if ok else "row-error",
                )
            )
        head = ui.tags.thead(
            ui.tags.tr(*[ui.tags.th(h, scope="col") for h in ("File", "Exam year", "Residents", "Notes")])
        )
        demo_note = message("Showing invented demo data.", "info") if is_demo.get() else None
        return ui.div(demo_note, ui.tags.table(head, ui.tags.tbody(*rows), class_="table table-sm data-table"))

    @render.ui
    def program_status():
        if program_err.get():
            return message(program_err.get(), "error")
        rep = program.get()
        if rep is None:
            return None
        from ite_core.pdf_reports import items_summary

        s = items_summary(rep["items"])
        return ui.p(
            f"Program Performance Report {rep.get('exam_year') or ''}: {s['n']} items, {s['red']} red and "
            f"{s['yellow']} yellow flags — see Item gaps.",
            class_="hint",
        )

    @render.ui
    def mksap_status():
        mk, err = mksap()
        if err:
            return message(err, "error")
        if mk is None:
            return None
        extra = "" if mk.kind == "detail" else " Section coverage needs the full detail export."
        return ui.p(
            f"MKSAP {mksap_mod.KIND_LABEL[mk.kind]} export: {len(mk.people):,} accounts, {mk.bank:,} questions in "
            f"the bank.{extra}",
            class_="hint",
        )

    @render.ui
    def coverage():
        r = rosters()
        if r is None or r.long.empty:
            return None
        t = r.long.groupby(["Exam_Year", "PGY"]).size().unstack(fill_value=0)
        head = ui.tags.tr(
            ui.tags.th("Exam year", scope="col"), *[ui.tags.th(f"PGY-{p}", scope="col") for p in t.columns]
        )
        body = [ui.tags.tr(ui.tags.td(str(y)), *[ui.tags.td(str(v)) for v in row]) for y, row in t.iterrows()]
        n_people = r.long.ID.nunique()
        return ui.div(
            ui.h6("Residents tested, by year and level"),
            ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*body), class_="table table-sm data-table"),
            ui.p(
                f"{n_people} different residents across {len(t)} exam year(s), linked by ACP Candidate ID. "
                f"Current year: {r.current_year}.",
                class_="hint",
            ),
        )

    # ----------------------------------------------------------------- match
    # Each resident row carries its own controls (Confirm / pick an account / No MKSAP account). Plain HTML controls
    # send one event, {id, action, key}, so nothing has to stay in sync between separate dropdowns.
    def _row_js(acp_id: str, action: str, key_expr: str = "null") -> str:
        return (
            f"Shiny.setInputValue('{session.ns('row_action')}', {{id: '{acp_id}', action: '{action}', "
            f"key: {key_expr}, n: Math.random()}}, {{priority: 'event'}})"
        )

    @render.ui
    def match_section():
        r, (mk, _) = rosters(), mksap()
        if r is None or r.current_year is None or mk is None:
            return None
        return ui.card(
            ui.card_header(f"3 · Link {r.current_year} residents to their MKSAP accounts"),
            ui.p(
                "MKSAP exports have no ACP ID, so residents are matched by name (same surname and the same first name "
                "or initial). Review anything listed under “Needs your review”. Residents without an MKSAP account "
                "are fine — choose “No MKSAP account”.",
                class_="hint",
            ),
            ui.output_ui("match_summary"),
            ui.output_ui("review_rows"),
            ui.card_footer(
                ui.download_button("download_cw", "Download crosswalk (.csv)", class_="btn-sm"),
                ui.span(" Save it and upload it next time to keep your decisions.", class_="hint"),
            ),
        )

    @render.ui
    def match_summary():
        cw = crosswalk.get()
        if cw is None:
            return None
        need = int((~cw.confirmed_by_user & (cw.tier != "Exact")).sum())
        auto = int((~cw.confirmed_by_user & (cw.tier == "Exact")).sum())
        done = int(cw.confirmed_by_user.sum())
        linked = int(cw.mksap_key.notna().sum())
        return ui.div(
            ui.span(f"{need} need your review", class_="chip chip-ambiguous" if need else "chip chip-exact"),
            ui.span(f"{auto} matched automatically", class_="chip chip-exact"),
            ui.span(f"{done} reviewed by you", class_="chip chip-manual"),
            ui.span(f"{linked} of {len(cw)} residents linked to an account", class_="chip"),
            class_="chip-row",
        )

    def _account_select(cw, mk, row):
        cands = names.candidate_accounts(cw, mk.people, row.acp_id)
        opts = [ui.tags.option("Choose an MKSAP account…", value="", selected=True, disabled=True)]
        for c in cands.itertuples():
            label = f"{c.mk_last}, {c.mk_first}" + (
                f"  (now linked to {c.linked_to})" if isinstance(c.linked_to, str) else ""
            )
            opts.append(ui.tags.option(label, value=c.mk_key))
        return ui.tags.select(
            *opts,
            class_="form-select form-select-sm match-select",
            onchange=_row_js(row.acp_id, "set", "this.value"),
            **{"aria-label": f"MKSAP account for {row.ite_name}"},
        )

    def _row(cw, mk, row, pgy, mode):
        acct = f"{row.mksap_last}, {row.mksap_first}" if isinstance(row.mksap_key, str) else None
        if row.confirmed_by_user and acct is None:
            status = ui.span("No MKSAP account", class_="chip")
        elif acct is None:
            status = ui.span("No match found", class_="chip chip-unmatched")
        else:
            status = ui.span(acct, class_="match-acct")
        badge = {
            "Exact": "chip-exact",
            "Probable": "chip-probable",
            "Ambiguous": "chip-ambiguous",
            "Unmatched": "chip-unmatched",
            "Manual": "chip-manual",
        }.get(row.tier, "")
        controls = []
        if mode == "review" and acct is not None:
            controls.append(
                ui.tags.button("Confirm", class_="btn btn-sm btn-success", onclick=_row_js(row.acp_id, "confirm"))
            )
        controls.append(_account_select(cw, mk, row))
        if not (row.confirmed_by_user and acct is None):
            controls.append(
                ui.tags.button(
                    "No MKSAP account", class_="btn btn-sm btn-outline-secondary", onclick=_row_js(row.acp_id, "none")
                )
            )
        return ui.div(
            ui.div(
                ui.strong(row.ite_name),
                ui.span(f" · PGY-{pgy}" if pgy else "", class_="hint"),
                ui.span(" ✓" if row.confirmed_by_user else "", class_="ok"),
                class_="match-who",
            ),
            ui.div(
                status,
                " ",
                ui.span("Suggested" if mode == "review" and acct else row.tier, class_=f"chip {badge}")
                if not row.confirmed_by_user
                else None,
                class_="match-status",
            ),
            ui.div(*controls, class_="match-controls"),
            class_=f"match-row match-{mode}",
        )

    @render.ui
    def review_rows():
        cw, (mk, _), r = crosswalk.get(), mksap(), rosters()
        if cw is None or mk is None or r is None:
            return None
        cur = r.long[r.long.Exam_Year == r.current_year].set_index("ID").PGY
        order = cw.assign(tier_rank=cw.tier.map(TIER_ORDER), pgy_now=cw.acp_id.map(cur)).sort_values(
            ["tier_rank", "ite_name"]
        )
        need = order[~order.confirmed_by_user & (order.tier != "Exact")]
        auto = order[~order.confirmed_by_user & (order.tier == "Exact")]
        done = order[order.confirmed_by_user]
        n_prob = int((need.tier == "Probable").sum())
        free = names.unmatched_mksap(cw, mk.people).sort_values(["mk_last", "mk_first"])
        parts = []
        if len(need):
            parts += [
                ui.div(
                    ui.h6(f"Needs your review ({len(need)})", class_="m-0"),
                    ui.input_action_button(
                        "confirm_probable", f"Confirm all suggestions ({n_prob})", class_="btn-outline-success btn-sm"
                    )
                    if n_prob
                    else None,
                    class_="d-flex justify-content-between align-items-center mb-2",
                ),
                *[_row(cw, mk, x, x.pgy_now, "review") for x in need.itertuples()],
            ]
        else:
            parts.append(message("Every resident is matched or reviewed.", "info"))
        if len(done):
            parts += [
                ui.h6(f"Reviewed by you ({len(done)})", class_="mt-3"),
                *[_row(cw, mk, x, x.pgy_now, "done") for x in done.itertuples()],
            ]
        if len(auto):
            parts.append(
                ui.tags.details(
                    ui.tags.summary(f"Matched automatically ({len(auto)}) — same surname and first name"),
                    *[_row(cw, mk, x, x.pgy_now, "auto") for x in auto.itertuples()],
                    class_="explainer",
                )
            )
        parts.append(
            ui.tags.details(
                ui.tags.summary(
                    f"MKSAP accounts not linked to any resident ({len(free)}) — usually graduates or faculty"
                ),
                ui.tags.ul(
                    *[
                        ui.tags.li(f"{a}, {b} · {int(q):,} questions")
                        for a, b, q in zip(free.mk_last, free.mk_first, free.mk_answered, strict=True)
                    ],
                    class_="unlinked-list",
                ),
                class_="explainer",
            )
        )
        return ui.div(*parts)

    @reactive.effect
    @reactive.event(input.row_action)
    def _row_action():
        ev, cw, (mk, _) = input.row_action(), crosswalk.get(), mksap()
        if not ev or cw is None or mk is None:
            return
        rid, action = str(ev.get("id")), ev.get("action")
        if rid not in set(cw.acp_id):
            return
        try:
            if action == "confirm":
                key = cw.loc[cw.acp_id == rid, "mksap_key"].iloc[0]
                crosswalk.set(names.set_match(cw, rid, key if isinstance(key, str) else None, mk.people))
            elif action == "none":
                crosswalk.set(names.set_match(cw, rid, None, mk.people))
            elif action == "set" and ev.get("key"):
                owner = cw.loc[(cw.mksap_key == ev["key"]) & (cw.acp_id != rid), "ite_name"]
                crosswalk.set(names.reassign(cw, rid, ev["key"], mk.people))
                if len(owner):
                    ui.notification_show(
                        f"Moved that MKSAP account from {owner.iloc[0]} — please review their row.",
                        type="warning",
                        duration=8,
                    )
        except (KeyError, ValueError) as e:
            ui.notification_show(str(e).strip("'\""), type="error")

    @reactive.effect
    @reactive.event(input.confirm_probable)
    def _confirm():
        cw = crosswalk.get()
        if cw is not None:
            crosswalk.set(names.confirm_tier(cw, "Probable"))

    @render.download_button(filename=lambda: f"ite_mksap_crosswalk_{rosters().current_year}.csv", media_type="text/csv")
    def download_cw():
        cw = crosswalk.get()
        if cw is not None:
            yield S.crosswalk_csv(cw)

    @reactive.calc
    def abim_data():
        """(candidates, years) from every ABIM report added, or None."""
        reps = abim_reps.get()
        return abim.combine(reps) if reps else None

    return dataset, program, abim_data
