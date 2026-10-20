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
    @reactive.event(input.demo)
    def _demo():
        d = demo.make_demo()
        roster_ups.set([S.Upload(n, b) for n, b in d["rosters"]])
        mksap_up.set(S.Upload(*d["mksap"]))
        prior_cw.set(None)
        is_demo.set(True)

    @reactive.effect
    @reactive.event(input.clear)
    def _clear():
        roster_ups.set([])
        mksap_up.set(None)
        prior_cw.set(None)
        crosswalk.set(None)
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
    @render.ui
    def match_section():
        r, (mk, _) = rosters(), mksap()
        if r is None or r.current_year is None or mk is None:
            return None
        return ui.card(
            ui.card_header(f"3 · Match {r.current_year} residents to MKSAP accounts"),
            ui.p(
                "MKSAP exports have no ACP ID, so residents are matched by name: same surname and the same first "
                "name or initial. Check anything not marked Exact.",
                class_="hint",
            ),
            ui.output_ui("match_summary"),
            ui.layout_columns(
                ui.div(ui.output_data_frame("match_table")),
                ui.div(
                    ui.output_ui("edit_panel"),
                    ui.hr(),
                    ui.h6("MKSAP accounts with no matching resident"),
                    ui.p("Usually graduates, faculty or other learners.", class_="hint"),
                    ui.output_data_frame("unmatched_table"),
                ),
                col_widths=(7, 5),
            ),
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
        counts = cw.tier.value_counts()
        chips = [ui.span(f"{counts.get(t, 0)} {t}", class_=f"chip chip-{t.lower()}") for t in TIER_ORDER]
        confirmed = int(cw.confirmed_by_user.sum())
        return ui.div(*chips, ui.span(f"{confirmed} reviewed by you", class_="chip"), class_="chip-row")

    def _review_frame(cw: pd.DataFrame) -> pd.DataFrame:
        cur = rosters().long
        pgy = cur[cur.Exam_Year == rosters().current_year].set_index("ID").PGY
        out = pd.DataFrame(
            {
                "Resident": cw.ite_name,
                "PGY": cw.acp_id.map(pgy),
                "MKSAP account": [
                    f"{a}, {b}" if isinstance(a, str) else "—"
                    for a, b in zip(cw.mksap_last, cw.mksap_first, strict=True)
                ],
                "Match": cw.tier,
                "Reviewed": cw.confirmed_by_user.map({True: "yes", False: ""}),
            }
        )
        return out.assign(_o=cw.tier.map(TIER_ORDER)).sort_values(["_o", "Resident"]).drop(columns="_o")

    @render.data_frame
    def match_table():
        cw = crosswalk.get()
        if cw is None:
            return None
        return render.DataGrid(_review_frame(cw), filters=True, height="420px", width="100%")

    @render.data_frame
    def unmatched_table():
        cw, (mk, _) = crosswalk.get(), mksap()
        if cw is None or mk is None:
            return None
        u = names.unmatched_mksap(cw, mk.people)
        df = pd.DataFrame({"MKSAP account": u.mk_last + ", " + u.mk_first, "Questions answered": u.mk_answered})
        return render.DataGrid(df.sort_values("MKSAP account"), height="220px", width="100%")

    @render.ui
    def edit_panel():
        cw, (mk, _) = crosswalk.get(), mksap()
        if cw is None or mk is None:
            return None
        order = cw.assign(_o=cw.tier.map(TIER_ORDER)).sort_values(["_o", "ite_name"])
        residents = {a: f"{n} ({t})" for a, n, t in zip(order.acp_id, order.ite_name, order.tier, strict=True)}
        free = names.unmatched_mksap(cw, mk.people).sort_values(["mk_last", "mk_first"])
        accounts = {NO_ACCOUNT: "— No MKSAP account —"}
        accounts.update({k: f"{a}, {b}" for k, a, b in zip(free.mk_key, free.mk_last, free.mk_first, strict=True)})
        n_prob = int(((cw.tier == "Probable") & ~cw.confirmed_by_user).sum())
        return ui.div(
            ui.h6("Fix a match"),
            ui.input_selectize("edit_resident", "Resident", residents),
            ui.input_selectize("edit_account", "MKSAP account (unlinked accounts)", accounts),
            ui.div(
                ui.input_action_button("apply", "Apply", class_="btn-primary btn-sm"),
                ui.input_action_button(
                    "confirm_probable",
                    f"Accept all Probable ({n_prob})",
                    class_="btn-outline-primary btn-sm",
                    disabled=n_prob == 0,
                ),
                class_="button-row",
            ),
        )

    @reactive.effect
    @reactive.event(input.apply)
    def _apply():
        cw, (mk, _) = crosswalk.get(), mksap()
        if cw is None or mk is None:
            return
        acc = input.edit_account()
        try:
            crosswalk.set(names.set_match(cw, input.edit_resident(), None if acc == NO_ACCOUNT else acc, mk.people))
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

    return dataset
