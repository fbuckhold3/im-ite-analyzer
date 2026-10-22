"""Work out what an uploaded file is, so a program director can drop every file in one place.

Pure and cheap: spreadsheets are read header-only and PDFs only up to their first three pages. The full loaders in
session.py still validate everything; this only routes each file to the right one. Messages name the file, never its
contents.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd
import pypdf

from . import mksap, names
from .roster import _canon

ROSTER, MKSAP, CROSSWALK, PROGRAM, EXAMINEE, UNKNOWN = (
    "roster",
    "mksap",
    "crosswalk",
    "program_report",
    "examinee_report",
    "unknown",
)

LABEL = {
    ROSTER: "ACP roster",
    MKSAP: "MKSAP export",
    CROSSWALK: "Saved MKSAP crosswalk",
    PROGRAM: "Program Performance Report",
    EXAMINEE: "Examinee Performance Report",
    UNKNOWN: "Not recognized",
}

_ROSTER_ANY = [("id", "candidate_id"), ("name",), ("pgy", "pgy_level"), ("total_test_percent_correct",)]


def _is_roster(columns) -> bool:
    cols = {_canon(c) for c in columns}
    return all(any(n in cols for n in alts) for alts in _ROSTER_ANY)


def _header(data: bytes, ext: str) -> list[str] | None:
    try:
        buf = io.BytesIO(data)
        df = pd.read_csv(buf, dtype=str, nrows=0) if ext == ".csv" else pd.read_excel(buf, dtype=str, nrows=0)
        return [str(c).strip() for c in df.columns]
    except Exception:
        return None


PDF_PAGES_CHECKED = 3  # some ACP PDFs open with an explanatory page before the report header


def _first_pages(data: bytes) -> str | None:
    try:
        r = pypdf.PdfReader(io.BytesIO(data))
        if r.is_encrypted and not r.decrypt(""):
            return None
        return " ".join(p.extract_text() or "" for p in r.pages[:PDF_PAGES_CHECKED])
    except Exception:
        return None


def detect(name: str, data: bytes) -> tuple[str, str]:
    """-> (kind, note). kind is one of the constants above; note is a short reason shown when not recognized."""
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        text = _first_pages(data)
        if text is None:
            return UNKNOWN, "could not be read as a PDF (damaged or password-protected)"
        flat = re.sub(r"\s+", " ", text).upper()
        if "PROGRAM PERFORMANCE REPORT" in flat:
            return PROGRAM, ""
        if "CANDIDATE ID" in flat or "EXAMINEE PERFORMANCE" in flat:
            return EXAMINEE, ""
        return UNKNOWN, "is a PDF but not an ACP IM-ITE report"
    if ext in (".csv", ".xlsx", ".xls"):
        cols = _header(data, ext)
        if cols is None:
            return UNKNOWN, "could not be read as a spreadsheet"
        if ext == ".csv":
            if {"acp_id", "mksap_key"} <= set(cols) and set(names.CROSSWALK_COLS) <= set(cols):
                return CROSSWALK, ""
            if set(mksap.REQUIRED) <= set(cols) or set(mksap.OVERVIEW_REQUIRED) <= set(cols):
                return MKSAP, ""
        if _is_roster(cols):
            return ROSTER, ""
        return UNKNOWN, "has columns that don't match an ACP roster, MKSAP export or saved crosswalk"
    return UNKNOWN, "is not a spreadsheet (.xlsx, .xls, .csv) or PDF"


EXAMINEE_NOTE = (
    "is a resident's Examinee Performance Report — open it on the Resident report page instead. It was not added here."
)


def sort_uploads(uploads) -> dict:
    """Group uploads (objects with .name and .data) by kind.

    -> {roster: [...], mksap: last or None, program_report: last or None, crosswalk: last or None,
        skipped: [(name, why), ...]}. A resident's Examinee report is skipped with a pointer to the right page.
    """
    out = {ROSTER: [], MKSAP: None, PROGRAM: None, CROSSWALK: None, "skipped": []}
    for up in uploads:
        kind, why = detect(up.name, up.data)
        if kind == ROSTER:
            out[ROSTER].append(up)
        elif kind in (MKSAP, PROGRAM, CROSSWALK):
            out[kind] = up
        else:
            out["skipped"].append((up.name, EXAMINEE_NOTE if kind == EXAMINEE else why))
    return out
