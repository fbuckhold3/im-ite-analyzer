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

from ite_core import demo, names
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


@module.ui
def upload_ui():
    return ui.div(
        ui.layout_columns(
            ui.card(
                ui.card_header("1 · Upload"),
                privacy_note(),
                ui.input_file(
                    "rosters",
                    "ACP Downloadable Roster(s) — one per exam year",
                    multiple=True,
                    accept=[".xlsx", ".xls", ".csv"],
                    button_label="Choose files…",
                ),
                ui.input_file(
                    "mksap",
                    "MKSAP Digital program export (optional) — members overview or full detail, .csv",
                    accept=[".csv"],
                    button_label="Choose file…",
                ),
                mksap_howto(),
                ui.input_file(
                    "program_pdf",
                    "ACP Program Performance Report (PDF, optional) — for item-level gaps",
                    accept=[".pdf"],
                    button_label="Choose PDF…",
                ),
                ui.input_file(
                    "crosswalk",
                    "Saved crosswalk from an earlier session (optional)",
                    accept=[".csv"],
                    button_label="Choose file…",
                ),
                ui.p(f"Up to {MAX_FILE_MB} MB per file.", class_="hint"),
                ui.div(
                    ui.input_action_button("demo", "Load demo data", class_="btn-outline-primary btn-sm"),
                    ui.input_action_button("clear", "Clear", class_="btn-outline-secondary btn-sm"),
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
    crosswalk: reactive.Value[pd.DataFrame | None] = reactive.value(None)
    is_demo = reactive.value(False)
    program: reactive.Value[dict | None] = reactive.value(None)
    program_err: reactive.Value[str | None] = reactive.value(None)

    # ------------------------------------------------------------------ intake
    @reactive.effect
    @reactive.event(input.rosters)
    def _rosters():
        roster_ups.set([_take(f) for f in input.rosters() or []])
        is_demo.set(False)

    @reactive.effect
    @reactive.event(input.mksap)
    def _mksap():
        files = input.mksap() or []
        mksap_up.set(_take(files[0]) if files else None)
        is_demo.set(False)

    @reactive.effect
    @reactive.event(input.crosswalk)
    def _crosswalk():
        files = input.crosswalk() or []
        if not files:
            return
        try:
            prior_cw.set(S.read_crosswalk(_take(files[0])))
            ui.notification_show("Crosswalk loaded — your earlier decisions were applied.", type="message")
        except UploadError as e:
            ui.notification_show(str(e), type="error", duration=10)

    @reactive.effect
    @reactive.event(input.program_pdf)
    def _program_pdf():
        files = input.program_pdf() or []
        if not files:
            return
        up = _take(files[0])
        try:
            program.set(S.load_program_report(up))
            program_err.set(None)
        except UploadError as e:
            program.set(None)
            program_err.set(str(e))
        except Exception:
            program.set(None)
            program_err.set(f"“{up.name}” could not be processed.")

    @reactive.effect
    @reactive.event(input.demo)
    def _demo():
        d = demo.make_demo()
        roster_ups.set([S.Upload(n, b) for n, b in d["rosters"]])
        mksap_up.set(S.Upload(*d["mksap"]))
        program.set(demo.sample_program_report())
        program_err.set(None)
        prior_cw.set(None)
        is_demo.set(True)

    @reactive.effect
    @reactive.event(input.clear)
    def _clear():
        roster_ups.set([])
        mksap_up.set(None)
        prior_cw.set(None)
        crosswalk.set(None)
        program.set(None)
        program_err.set(None)
        is_demo.set(False)

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

    return dataset, program
