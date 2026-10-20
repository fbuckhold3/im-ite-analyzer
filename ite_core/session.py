"""Turn one visitor's uploads into the dataset every tab reads. Pure functions — no Shiny, no disk.

Errors in one file never stop the others: each file gets a status row, and problems are collected as
user-facing messages (file names and counts only, never file contents).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd

from . import history, mksap, names, pdf_reports, roster
from .limits import CROSSWALK_EXT, MAX_FILES, MKSAP_EXT, PDF_EXT, ROSTER_EXT, UploadError, check_file
from .nomogram import DEFAULT_CUTOFFS


@dataclass
class Upload:
    name: str
    data: bytes
    year: int | None = None  # user override for rosters


@dataclass
class Rosters:
    long: pd.DataFrame  # with Grad_Class / Pass_Prob / Risk_Tier
    files: pd.DataFrame  # one status row per uploaded file
    current_year: int | None


@dataclass
class Mksap:
    name: str
    people: pd.DataFrame
    sections: pd.DataFrame | None  # None for the members-overview export
    bank: int
    kind: str = "detail"  # "overview" or "detail"


@dataclass
class Dataset:
    rosters: Rosters
    mksap: Mksap | None
    crosswalk: pd.DataFrame | None
    wide: pd.DataFrame | None
    messages: list[str] = field(default_factory=list)


FILE_COLS = ["file", "status", "year", "kept", "dropped_blank_id", "dropped_pgy", "percentiles", "message"]


def load_rosters(uploads: list[Upload], cutoffs=DEFAULT_CUTOFFS, include_pgy4: bool = False) -> Rosters:
    status, frames, seen_years = [], [], {}
    if len(uploads) > MAX_FILES:
        raise UploadError(f"Please upload at most {MAX_FILES} roster files at a time.")
    for up in uploads:
        row = dict(
            file=up.name,
            status="error",
            year=up.year,
            kept=0,
            dropped_blank_id=0,
            dropped_pgy=0,
            percentiles=None,
            message="",
        )
        try:
            check_file(up.name, len(up.data), ROSTER_EXT, "roster")
            d, info = roster.load_roster(up.data, filename=up.name, year=up.year, include_pgy4=include_pgy4)
            row.update(
                year=info["year"],
                kept=info["rows_kept"],
                dropped_blank_id=info["dropped_blank_id"],
                dropped_pgy=info["dropped_pgy"],
                percentiles=bool(info["has_percentile"]),
            )
            if info["year"] in seen_years:
                raise UploadError(f"Exam year {info['year']} was already loaded from “{seen_years[info['year']]}”.")
            if info["duplicate_ids"]:
                raise UploadError(f"{len(info['duplicate_ids'])} Candidate ID(s) appear more than once in this file.")
            if d.empty:
                raise UploadError("No residents with a Candidate ID and PGY 1–3 were found.")
            seen_years[info["year"]] = up.name
            frames.append(d)
            notes = []
            if not info["has_percentile"]:
                notes.append("no percentiles in this file")
            elif not info["areas_percentile"]:
                notes.append("no content-area percentiles (older ACP layout)")
            row.update(status="ok", message="; ".join(notes))
        except UploadError as e:
            row["message"] = str(e)
        except Exception:  # never surface tracebacks (they can echo cell contents)
            row["message"] = "This file could not be processed."
        status.append(row)
    files = pd.DataFrame(status, columns=FILE_COLS)
    if not frames:
        return Rosters(long=pd.DataFrame(), files=files, current_year=None)
    long = history.add_derived(pd.concat(frames, ignore_index=True), cutoffs)
    return Rosters(long=long, files=files, current_year=int(long.Exam_Year.max()))


def load_mksap(up: Upload) -> Mksap:
    check_file(up.name, len(up.data), MKSAP_EXT, "MKSAP CSV")
    kind, people, sections = mksap.read_export(up.data, name=up.name)
    if people.empty:
        raise UploadError(f"“{up.name}” has no MKSAP accounts in it.")
    return Mksap(name=up.name, people=people, sections=sections, bank=int(people.mk_bank.max()), kind=kind)


def match(rosters: Rosters, mk: Mksap, prior: pd.DataFrame | None = None) -> pd.DataFrame:
    """Automatic proposals for current residents, then any confirmed rows from a re-uploaded crosswalk."""
    cur = rosters.long[rosters.long.Exam_Year == rosters.current_year]
    cw = names.match_mksap(cur, mk.people)
    if prior is None or prior.empty:
        return cw
    keys = set(mk.people.mk_key)
    for _, p in prior[prior.confirmed_by_user].iterrows():
        if p.acp_id not in set(cw.acp_id):
            continue
        key = p.mksap_key if isinstance(p.mksap_key, str) and p.mksap_key in keys else None
        if isinstance(p.mksap_key, str) and key is None:
            continue  # that MKSAP account isn't in this export — keep the automatic proposal
        holder = cw.index[(cw.mksap_key == key) & (cw.acp_id != p.acp_id)] if key else []
        if len(holder):  # free the account if the automatic match had given it to someone else
            cw.loc[holder, ["mksap_key", "mksap_last", "mksap_first"]] = None
            cw.loc[holder, "tier"] = "Unmatched"
        cw = names.set_match(cw, p.acp_id, key, mk.people)
    return cw


def read_crosswalk(up: Upload) -> pd.DataFrame:
    check_file(up.name, len(up.data), CROSSWALK_EXT, "crosswalk CSV")
    try:
        return names.read_crosswalk(io.BytesIO(up.data))
    except ValueError as e:
        raise UploadError(f"“{up.name}”: {e}") from e


def build_wide(rosters: Rosters, mk: Mksap | None, cw: pd.DataFrame | None) -> pd.DataFrame | None:
    if rosters.current_year is None:
        return None
    w = history.wide(rosters.long, rosters.current_year)
    return history.attach_mksap(w, cw, mk.people) if mk is not None and cw is not None else w


def crosswalk_csv(cw: pd.DataFrame) -> bytes:
    return cw[names.CROSSWALK_COLS].to_csv(index=False).encode()


def load_program_report(up: Upload) -> dict:
    """ACP Program Performance Report PDF -> {program_id, program_name, exam_year, areas, items (flagged)}."""
    check_file(up.name, len(up.data), PDF_EXT, "PDF")
    rep = pdf_reports.parse_program_pdf(up.data, name=up.name)
    rep["file"] = up.name
    return rep
