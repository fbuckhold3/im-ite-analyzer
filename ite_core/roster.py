"""Load ACP 'Downloadable Roster with Score Results' files (.xlsx / .csv), any year.

Columns differ by year (2023: area % correct only, different order; 2024+: % correct and
percentile per area), so everything is detected by column name, never by position.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import numpy as np
import pandas as pd

# ACP column stem -> short key used in ite_core column names
AREAS = {
    "Cardiology": "cards",
    "Endocrinology": "endo",
    "Gastroenterology": "gi",
    "General_Internal_Medicine": "gim",
    "Geriatric_Medicine": "geri",
    "Hematology_Oncology": "hemonc",
    "Infectious_Diseases": "id",
    "Nephrology": "nephro",
    "Neurology": "neuro",
    "Pulmonary_and_Critical_Care_Medicine": "pulm_ccm",
    "Rheumatology": "rheum",
    "High_Value_Care": "hvc",
}
AREA_LABELS = {
    k: s.replace("_and_", " and ").replace("Hematology_Oncology", "Hematology/Oncology").replace("_", " ")
    for s, k in AREAS.items()
}

BASE_COLS = ["ID", "Name", "Exam_Year", "PGY", "Pct_Correct", "Percentile"]


def _canon(col: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(col).strip().lower()).strip("_")


def year_from_filename(name) -> int | None:
    m = re.search(r"(20\d\d)", Path(str(name)).name)
    return int(m.group(1)) if m else None


def clean_id(x) -> str | None:
    """ACP Candidate ID as a string. 2023 rosters load IDs as floats (6352918.0)."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    s = str(x).strip()
    if not s or s.lower() == "nan":
        return None
    if re.fullmatch(r"\d+(\.0+)?", s):
        return str(int(float(s)))
    return s


def read_table(source, filename: str | None = None) -> pd.DataFrame:
    """Read .xlsx/.xls/.csv from a path, bytes, or file-like object. Everything as text."""
    name = str(filename or source)
    is_csv = name.lower().endswith(".csv")
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    if is_csv:
        return pd.read_csv(source, dtype=str)
    return pd.read_excel(source, dtype=str)


def load_roster(
    source, filename: str | None = None, year: int | None = None, include_pgy4: bool = False
) -> tuple[pd.DataFrame, dict]:
    """One ACP roster -> tidy table + a small report of what was detected.

    Output columns: ID, Name, Exam_Year, PGY, Pct_Correct, Percentile, Program_Number,
    Program_Name, then pc_<area> / ile_<area> for each content area present.
    """
    raw = read_table(source, filename)
    cols = {_canon(c): c for c in raw.columns}

    def col(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    required = dict(
        ID=col("id", "candidate_id"),
        Name=col("name"),
        PGY=col("pgy", "pgy_level"),
        Pct_Correct=col("total_test_percent_correct"),
    )
    missing = [k for k, v in required.items() if v is None]
    if missing:
        raise ValueError(f"Not an ACP roster file — missing column(s): {', '.join(missing)}")

    yr = year or year_from_filename(filename or source)
    if yr is None:
        raise ValueError("Could not tell the exam year from the file name — please enter it.")

    num = lambda c: pd.to_numeric(raw[c], errors="coerce") if c else pd.Series(np.nan, index=raw.index)
    out = pd.DataFrame(
        dict(
            ID=raw[required["ID"]].map(clean_id),
            Name=raw[required["Name"]].astype("string").str.strip(),
            Exam_Year=yr,
            PGY=num(required["PGY"]),
            Pct_Correct=num(required["Pct_Correct"]),
            Percentile=num(col("total_test_percentile_rank")),
            Program_Number=raw[col("program_number")].map(clean_id) if col("program_number") else None,
            Program_Name=raw[col("program_name")] if col("program_name") else None,
        )
    )
    areas_pc, areas_ile = [], []
    for stem, key in AREAS.items():
        c_pc, c_ile = col(f"{_canon(stem)}_percent_correct"), col(f"{_canon(stem)}_percentile_rank")
        if c_pc:
            out[f"pc_{key}"] = num(c_pc)
            areas_pc.append(key)
        if c_ile:
            out[f"ile_{key}"] = num(c_ile)
            areas_ile.append(key)

    n_raw = len(out)
    no_id = out.ID.isna()
    keep_pgy = out.PGY.between(1, 4 if include_pgy4 else 3)
    out = out[~no_id & keep_pgy].copy()
    out["PGY"] = out.PGY.astype(int)
    dupes = out.ID[out.ID.duplicated()].tolist()
    info = dict(
        filename=str(filename or source),
        year=yr,
        rows_in_file=n_raw,
        rows_kept=len(out),
        dropped_blank_id=int(no_id.sum()),
        dropped_pgy=int((~no_id & ~keep_pgy).sum()),
        has_percentile=out.Percentile.notna().any(),
        areas_pct_correct=areas_pc,
        areas_percentile=areas_ile,
        duplicate_ids=dupes,
    )
    return out.reset_index(drop=True), info


def load_rosters(files: list, include_pgy4: bool = False) -> tuple[pd.DataFrame, list[dict]]:
    """Several rosters -> one long table. `files` items: path, or (source, filename[, year])."""
    frames, infos = [], []
    for f in files:
        src, fn, yr = (f, None, None) if not isinstance(f, (tuple, list)) else (list(f) + [None, None])[:3]
        d, info = load_roster(src, fn, yr, include_pgy4)
        frames.append(d)
        infos.append(info)
    long = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=BASE_COLS)
    clash = long.duplicated(["ID", "Exam_Year"], keep=False)
    if clash.any():
        years = sorted(long.loc[clash, "Exam_Year"].unique().tolist())
        raise ValueError(
            f"The same Candidate ID appears twice for exam year(s) {years} — was one year's roster uploaded twice?"
        )
    return long, infos
