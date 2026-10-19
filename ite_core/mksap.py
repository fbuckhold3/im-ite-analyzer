"""MKSAP Digital detail export: one row per person x question.

Columns: Last Name, First Name, Subspecialty, Question Number, Answered?, Correct? (Y/N).
Question numbers repeat within a subspecialty for different items — count rows, never
de-duplicate on the number. Each person carries the full bank (3,156 rows in 2026).
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

from .limits import ISSUE_HINT, MAX_MKSAP_ROWS, UploadError, check_rows

REQUIRED = ["Last Name", "First Name", "Subspecialty", "Answered?", "Correct?"]

# Section codes seen in the 2026 export. TODO: confirm HP / IN / CS / FC labels with ACP.
SECTION_NAMES = {
    "CV": "Cardiovascular",
    "EN": "Endocrinology",
    "GI": "Gastroenterology",
    "HM": "Hematology",
    "ON": "Oncology",
    "ID": "Infectious Disease",
    "NP": "Nephrology",
    "NR": "Neurology",
    "PM": "Pulmonary",
    "CC": "Critical Care",
    "RM": "Rheumatology",
    "DM": "Dermatology",
    "FC": "Foundations of Clinical Practice",
    "CS": "Common Symptoms",
    "HP": "Hospital Medicine",
    "IN": "Interdisciplinary Medicine",
}

VOLUME_BINS = [0, 100, 250, 500, 1000, np.inf]
VOLUME_LABELS = ["Under 100", "100–249", "250–499", "500–999", "1,000+"]


def load_mksap(source, name: str = "MKSAP file") -> pd.DataFrame:
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    try:
        m = pd.read_csv(source, dtype=str, nrows=MAX_MKSAP_ROWS + 1)
    except Exception as e:
        raise UploadError(f"“{name}” could not be read as a CSV file.") from e
    check_rows(name, len(m), MAX_MKSAP_ROWS)
    m.columns = [c.strip() for c in m.columns]
    missing = [c for c in REQUIRED if c not in m.columns]
    if missing:
        raise UploadError(
            f"“{name}” is not an MKSAP Digital detail export — missing column(s): {', '.join(missing)}. {ISSUE_HINT}"
        )
    m["Last Name"] = m["Last Name"].str.strip()
    m["First Name"] = m["First Name"].str.strip()
    m["ans"] = m["Answered?"].str.strip().str.upper().eq("Y")
    m["cor"] = m["Correct?"].str.strip().str.upper().eq("Y")
    m["mk_key"] = m["Last Name"] + "|" + m["First Name"]
    return m


def per_person(m: pd.DataFrame) -> pd.DataFrame:
    per = (
        m.groupby("mk_key", sort=True)
        .agg(
            mk_last=("Last Name", "first"),
            mk_first=("First Name", "first"),
            mk_answered=("ans", "sum"),
            mk_correct=("cor", "sum"),
            mk_bank=("ans", "size"),
        )
        .reset_index()
    )
    per["mk_pct_correct"] = (100 * per.mk_correct / per.mk_answered).where(per.mk_answered >= 1)
    per["mk_pct_bank"] = 100 * per.mk_answered / per.mk_bank
    return per


def by_section(m: pd.DataFrame) -> pd.DataFrame:
    """Person x subspecialty: a = answered, c = correct, n = items in bank."""
    s = m.groupby(["mk_key", "Subspecialty"]).agg(a=("ans", "sum"), c=("cor", "sum"), n=("ans", "size")).reset_index()
    s["section_name"] = s.Subspecialty.map(SECTION_NAMES).fillna(s.Subspecialty)
    return s


def volume_bin(answered: pd.Series) -> pd.Series:
    return pd.cut(answered, VOLUME_BINS, right=False, labels=VOLUME_LABELS)
