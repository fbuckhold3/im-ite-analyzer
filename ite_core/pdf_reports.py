"""Parse ACP ITE PDFs with pypdf (pure Python — no pdftotext binary on the server).

* Examinee Performance Report (one resident, ~4 pages; or the composite of all residents):
  total % correct, percentile, PGY, content-area table, missed educational objectives.
* Program Performance Report: content-area table (p.2) and the per-item table, with
  red / yellow flags for items far below national.

Each parser has a *_text() form that takes a list of page strings, so tests can use
synthetic text instead of real PDFs.
"""

from __future__ import annotations

import io
import re

import pandas as pd
import pypdf

from .limits import ISSUE_HINT, UploadError, check_pages

# Content areas as ACP prints them in reports (HVC is a cross-cutting area)
REPORT_AREAS = [
    "Cardiology",
    "Endocrinology",
    "Gastroenterology",
    "General Internal Medicine",
    "Geriatric Medicine",
    "Hematology/Oncology",
    "Infectious Diseases",
    "Nephrology",
    "Neurology",
    "Pulmonary and Critical Care Medicine",
    "Rheumatology",
    "High Value Care",
]
RED_GAP, YELLOW_GAP = -10, -20


def pdf_pages(source, name: str = "PDF") -> list[str]:
    """Layout-preserving text of every page. Raises UploadError for unreadable / encrypted / oversized PDFs."""
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    try:
        reader = pypdf.PdfReader(source)
        if reader.is_encrypted and not reader.decrypt(""):
            raise UploadError(f"“{name}” is password-protected. Please upload the unprotected ACP PDF.")
        check_pages(name, len(reader.pages))
        return [p.extract_text(extraction_mode="layout") or "" for p in reader.pages]
    except UploadError:
        raise
    except Exception as e:  # pypdf raises many types for damaged files
        raise UploadError(f"“{name}” could not be read as a PDF.") from e


def _year(text: str) -> int | None:
    m = re.search(r"(20\d\d)\s+INTERNAL MEDICINE IN-TRAINING", text, re.I)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------- examinee report
_HEADER = re.compile(
    r"^(Name:|Candidate ID:|Program ID:|EEID:|Page \d+ of \d+|\d{4} Internal Medicine In-Training"
    r"|Examinee Performance Report)",
    re.I,
)


def parse_examinee_text(pages: list[str]) -> list[dict]:
    """One dict per resident (the composite PDF holds many, grouped on Candidate ID)."""
    groups: list[dict] = []
    for i, t in enumerate(pages):
        cid = re.search(r"Candidate ID:\s*(\d+)", t)
        cid = cid.group(1) if cid else None
        yr = _year(t)
        new_year = yr is not None and groups and groups[-1]["exam_year"] not in (None, yr)
        if not groups or (cid and cid != groups[-1]["candidate_id"]) or new_year:
            name = re.search(r"Name:\s*(.+)", t)
            prog = re.search(r"Program ID:\s*(\d+)", t)
            groups.append(
                dict(
                    candidate_id=cid,
                    name=name.group(1).strip() if name else None,
                    program_id=prog.group(1) if prog else None,
                    exam_year=_year(t),
                    pages=[],
                )
            )
        groups[-1]["pages"].append(i)
    return [_parse_one_examinee([pages[i] for i in g["pages"]], g) for g in groups]


def _parse_one_examinee(pages: list[str], meta: dict) -> dict:
    first = pages[0]
    num = lambda pat: (lambda m: float(m.group(1)) if m else None)(re.search(pat, first))
    out = dict(meta)
    pgy = re.search(r"^\s*PGY Level\s+(\d+)", first, re.M)
    out.update(
        pct_correct=num(r"Total Test Percent Correct Score\s+(\d+)%?"),
        percentile=num(r"Percentile Rank by PGY Level\s+(\d+)"),
        pgy=int(pgy.group(1)) if pgy else None,
    )

    area_rows = []
    for line in first.splitlines():
        m = re.match(r"^\s*([A-Za-z][A-Za-z/ ]+?)(\*\*)?\s{2,}(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$", line)
        if m and m.group(1).strip() in REPORT_AREAS:
            area_rows.append(
                dict(
                    area=m.group(1).strip(),
                    pct_correct=int(m.group(3)),
                    national_mean=int(m.group(4)),
                    national_sd=int(m.group(5)),
                    percentile=int(m.group(6)),
                )
            )
    areas = pd.DataFrame(area_rows, columns=["area", "pct_correct", "national_mean", "national_sd", "percentile"])
    areas["z"] = ((areas.pct_correct - areas.national_mean) / areas.national_sd).round(2)

    missed, area, prev = [], None, None
    for t in pages[1:]:
        for line in t.splitlines():
            s = line.strip()
            if not s or _HEADER.match(s):
                continue
            if s in REPORT_AREAS:
                area, prev = s, None
                continue
            if area is None:
                continue
            if prev is not None and not prev["objective"].rstrip("*").endswith("."):
                prev["objective"] += " " + s  # wrapped line
                continue
            prev = dict(area=area, objective=s)
            missed.append(prev)
    mo = pd.DataFrame(missed, columns=["area", "objective"])
    mo["hvc"] = mo.objective.str.endswith("**")
    mo["objective"] = mo.objective.str.replace("**", "", regex=False).str.strip()
    out.update(areas=areas, missed=mo)
    return out


def parse_examinee_pdf(source, name: str = "PDF") -> list[dict]:
    reps = [r for r in parse_examinee_text(pdf_pages(source, name)) if r["candidate_id"]]
    if not reps or all(r["pct_correct"] is None for r in reps):
        raise UploadError(f"“{name}” doesn't look like an ACP IM-ITE Examinee Performance Report. {ISSUE_HINT}")
    return reps


# ---------------------------------------------------------------------- program report
def parse_program_text(pages: list[str]) -> dict:
    allp = "\n".join(pages)
    pid = re.search(r"PROGRAM:\s+(\d+)", allp)
    pname = re.search(r"PROGRAM NAME:\s+(.+?)\s{2,}", allp)
    return dict(
        program_id=pid.group(1) if pid else None,
        program_name=pname.group(1).strip() if pname else None,
        exam_year=_year(allp),
        areas=_program_areas(pages),
        items=flag_items(_program_items(pages)),
    )


def _program_areas(pages: list[str]) -> pd.DataFrame:
    """'MEAN PERCENT CORRECT SCORES' table: per PGY group, all-programs mean, our mean, our %ile rank."""
    rows = []
    for t in pages:
        if "MEAN PERCENT CORRECT SCORES" not in t:
            continue
        for line in t.splitlines():
            s = line.strip()
            m = re.match(r"^([A-Za-z][A-Za-z /]+?)(?:\s*\(SD\))?(\*{0,2})\s+((?:\d+\s*(?:\(\d+\))?\s*){12})$", s)
            if not m or s.startswith("Number"):
                continue
            nums = [int(x) for x in re.findall(r"\d+", re.sub(r"\(\d+\)", "", m.group(3)))]
            if len(nums) != 12:
                continue
            name = m.group(1).strip()
            name = "Total Test" if name.startswith("Total Test") else name
            r = dict(area=name)
            for k, g in zip(("1", "2", "3", "A"), range(0, 12, 3), strict=True):
                r[f"all{k}"], r[f"our{k}"], r[f"rank{k}"] = nums[g : g + 3]
            rows.append(r)
        n = re.search(r"Number of Residents\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", t)
        if n:
            v = [int(x) for x in n.groups()]
            rows.append(
                dict(
                    area="Number of Residents",
                    all1=v[0],
                    our1=v[1],
                    all2=v[2],
                    our2=v[3],
                    all3=v[4],
                    our3=v[5],
                    allA=v[6],
                    ourA=v[7],
                )
            )
        break
    return pd.DataFrame(rows)


def _program_items(pages: list[str]) -> pd.DataFrame:
    rows, area, pending = [], None, None
    for page_no, page in enumerate(pages, 1):
        for line in page.splitlines():
            s = line.rstrip()
            m = re.match(r"\s*Educational Objectives for (.+?) Items", s)
            if m:
                area, pending = m.group(1).strip(), None
                continue
            if area is None:
                continue
            m = re.match(r"^\s*(\S.*?)\s{2,}((?:\d{1,3}\s+){7}\d{1,3})\s*$", s)
            if m:
                n = [int(x) for x in m.group(2).split()]
                pending = dict(
                    area=area,
                    objective=m.group(1).strip(),
                    page=page_no,
                    all1=n[0],
                    our1=n[1],
                    all2=n[2],
                    our2=n[3],
                    all3=n[4],
                    our3=n[5],
                    allA=n[6],
                    ourA=n[7],
                )
                rows.append(pending)
                continue
            t = s.strip()
            if (
                pending
                and t
                and not re.search(r"\d", t)
                and not t.startswith(("PGY", "ALL", "GRPID"))
                and not t.isupper()
            ):
                pending["objective"] += " " + t  # wrapped objective line
    df = pd.DataFrame(
        rows, columns=["area", "objective", "page", "all1", "our1", "all2", "our2", "all3", "our3", "allA", "ourA"]
    )
    df["hvc"] = df.objective.str.contains(r"\*\*")
    df["objective"] = df.objective.str.replace("**", "", regex=False).str.strip()
    for k in ("1", "2", "3", "A"):
        df[f"gap{k}"] = df[f"our{k}"] - df[f"all{k}"]
    return df


def flag_items(df: pd.DataFrame, red: int = RED_GAP, yellow: int = YELLOW_GAP) -> pd.DataFrame:
    """red = All-PGY gap <= -10; yellow = (not red) any single-PGY gap <= -20.

    Caveat for display: one resident is ~4 points at a single PGY level.
    """
    out = df.copy()
    is_red = out.gapA <= red
    is_yellow = ~is_red & (out[["gap1", "gap2", "gap3"]] <= yellow).any(axis=1)
    out["flag"] = None
    out.loc[is_red, "flag"] = "red"
    out.loc[is_yellow, "flag"] = "yellow"
    return out


def parse_program_pdf(source, name: str = "PDF") -> dict:
    p = parse_program_text(pdf_pages(source, name))
    if p["items"].empty and p["areas"].empty:
        raise UploadError(f"“{name}” doesn't look like an ACP IM-ITE Program Performance Report. {ISSUE_HINT}")
    return p
