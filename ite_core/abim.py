"""ABIM Internal Medicine Certification Exam results -> outcomes linked to each graduate's ITE and MKSAP.

Two ABIM program PDFs are read (text only, in memory):
  * Examination Results report — one row per first-time taker: "Last, First   Pass|Fail".
  * Program Data Report — the same rows plus a standardized score (or "Withheld by Candidate"), the program and
    all-programs pass rates, and the passing score. Its content-area chart is an image and is not read.

ABIM reports carry no ACP Candidate ID, so takers are linked to residents by name with the same rules as MKSAP
(names.match_mksap). Everything here is identifiable; it is shown only in the app and the confidential PD report.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import names
from .limits import ISSUE_HINT, UploadError
from .pdf_reports import pdf_pages

_YEAR = re.compile(r"(20\d\d)\s+INTERNAL MEDICINE CERTIFICATION EXAMINATION", re.I)
_ROW = re.compile(
    r"^\s*(?P<name>[^\s,][^,\n]*?,\s*\S[^\n]*?)\s{2,}(?P<result>Pass|Fail)\b"
    r"(?:\s{2,}(?P<score>\d{3}|Withheld by Candidate))?\s*$"
)
_ALL_RATE = re.compile(r"All\s+Programs:\s*(\d{1,3})\s*%", re.I)
_OUR_RATE = re.compile(r"Your\s+Program:\s*(\d{1,3})\s*%", re.I)
_PASSING = re.compile(r"passing score for this exam is\s*(\d{3})", re.I)

CANDIDATE_COLS = ["key", "last", "first", "name", "result", "passed", "score", "withheld", "exam_year", "file"]


def is_abim_text(text: str) -> bool:
    flat = re.sub(r"\s+", " ", text).upper()
    return "INTERNAL MEDICINE CERTIFICATION EXAM" in flat


def parse_abim_text(pages: list[str], name: str = "PDF") -> dict:
    """Pages of layout text -> {exam_year, kind, candidates, program_rate, all_rate, passing_score, file}."""
    allp = "\n".join(pages)
    if not is_abim_text(allp):
        raise UploadError(
            f"“{name}” doesn't look like an ABIM Internal Medicine Certification Exam report. {ISSUE_HINT}"
        )
    years = [int(y) for y in _YEAR.findall(allp)]
    year = max(set(years), key=years.count) if years else None
    rows = []
    for line in allp.splitlines():
        m = _ROW.match(line)
        if not m:
            continue
        full = re.sub(r"\s+", " ", m["name"]).strip()
        last, _, first = full.partition(",")
        score = m["score"]
        rows.append(
            dict(
                last=last.strip(),
                first=first.strip(),
                name=full,
                result=m["result"],
                passed=m["result"] == "Pass",
                score=float(score) if score and score.isdigit() else np.nan,
                withheld=bool(score) and not score.isdigit(),
            )
        )
    if not rows:
        raise UploadError(f"“{name}” has no candidate results that could be read. {ISSUE_HINT}")
    c = pd.DataFrame(rows).drop_duplicates("name")
    c["exam_year"] = year
    c["file"] = name
    c["key"] = [f"{year}|{n}" for n in c.name]
    num = lambda rx: (lambda m: int(m.group(1)) if m else None)(rx.search(allp))  # noqa: E731
    return dict(
        exam_year=year,
        kind="program_data" if c.score.notna().any() or c.withheld.any() or num(_OUR_RATE) else "results",
        candidates=c[CANDIDATE_COLS].reset_index(drop=True),
        program_rate=num(_OUR_RATE),
        all_rate=num(_ALL_RATE),
        passing_score=num(_PASSING),
        file=name,
    )


def parse_abim_pdf(source, name: str = "PDF") -> dict:
    return parse_abim_text(pdf_pages(source, name), name)


def combine(reports: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Several ABIM reports -> (candidates, years). A Program Data Report wins over a Results report for the same
    exam year (it adds scores); years holds the ABIM-reported pass rates and passing score per exam year."""
    by_year: dict = {}
    for r in reports:
        y = r["exam_year"]
        if y not in by_year or (r["kind"] == "program_data" and by_year[y]["kind"] != "program_data"):
            by_year[y] = r
    cands = pd.concat([r["candidates"] for r in by_year.values()], ignore_index=True) if by_year else None
    years = pd.DataFrame(
        [
            dict(
                exam_year=y,
                kind=r["kind"],
                program_rate=r["program_rate"],
                all_rate=r["all_rate"],
                passing_score=r["passing_score"],
                file=r["file"],
            )
            for y, r in sorted(by_year.items(), key=lambda kv: kv[0] or 0)
        ]
    )
    return (cands if cands is not None else pd.DataFrame(columns=CANDIDATE_COLS)), years


# ------------------------------------------------------------------------------------------- linking
def graduates(long: pd.DataFrame, exam_years) -> pd.DataFrame:
    """One row per resident who could have sat these ABIM exams (finished training the exam year or the year
    before): their last ITE before graduating, preferring PGY-3."""
    want = {y for y in exam_years if y} | {y - 1 for y in exam_years if y}
    g = long[long.Grad_Class.isin(want) & long.PGY.between(1, 3)]
    g = g.sort_values(["ID", "PGY", "Exam_Year"]).groupby("ID", as_index=False).tail(1)
    return g.reset_index(drop=True)


def link(cands: pd.DataFrame, long: pd.DataFrame) -> pd.DataFrame:
    """Automatic name links ABIM taker -> resident, with the MKSAP matching rules. Returns one row per taker:
    key, ID, tier (Exact / Probable / Ambiguous / Unmatched), suggested.

    Only Exact links count straight away (ID set). A Probable match is a suggestion (suggested set, ID None) until a
    person confirms it, so similar names can't attach the wrong resident's ITE to a result."""
    if cands.empty:
        return pd.DataFrame(columns=["key", "ID", "tier", "suggested"])
    grads = graduates(long, cands.exam_year.unique())
    people = cands.rename(columns={"key": "mk_key", "last": "mk_last", "first": "mk_first"})
    cw = names.match_mksap(grads[["ID", "Name"]], people)  # one row per graduate
    hit = cw.dropna(subset=["mksap_key"])[["mksap_key", "acp_id", "tier"]]
    out = cands[["key"]].merge(hit, left_on="key", right_on="mksap_key", how="left")
    out["tier"] = out.tier.fillna("Unmatched")
    out = out.rename(columns={"acp_id": "ID"})
    out["suggested"] = out.ID.where(out.tier == "Probable")
    out.loc[out.tier == "Probable", "ID"] = None
    return out[["key", "ID", "tier", "suggested"]]


def outcome_table(cands: pd.DataFrame, links: pd.DataFrame, long: pd.DataFrame, mksap_people=None) -> pd.DataFrame:
    """One row per ABIM taker: result, score, and (if linked) the last ITE before graduation with its pass estimate,
    plus MKSAP volume / accuracy when the graduate's account is in the MKSAP export (exact name match only)."""
    t = cands.merge(links, on="key", how="left")
    grads = graduates(long, cands.exam_year.unique()) if not cands.empty else long.iloc[0:0]
    ite = grads[["ID", "PGY", "Exam_Year", "Pct_Correct", "Percentile", "Pass_Prob"]].rename(
        columns={
            "PGY": "ite_pgy",
            "Exam_Year": "ite_year",
            "Pct_Correct": "ite_pct",
            "Percentile": "ite_ile",
            "Pass_Prob": "predicted",
        }
    )
    t = t.merge(ite, on="ID", how="left")
    t["mk_answered"] = np.nan
    t["mk_pct_correct"] = np.nan
    if mksap_people is not None and not grads.empty:
        mcw = names.match_mksap(grads[["ID", "Name"]], mksap_people)
        mcw = mcw[mcw.tier == "Exact"][["acp_id", "mksap_key"]]  # exact only: no review step for graduates
        mk = mcw.merge(mksap_people, left_on="mksap_key", right_on="mk_key")[
            ["acp_id", "mk_answered", "mk_pct_correct"]
        ]
        t = t.drop(columns=["mk_answered", "mk_pct_correct"]).merge(mk, left_on="ID", right_on="acp_id", how="left")
        t = t.drop(columns=["acp_id"])
    return t.sort_values(["exam_year", "predicted"], ascending=[True, False], na_position="last").reset_index(drop=True)


def year_summary(t: pd.DataFrame, years: pd.DataFrame) -> pd.DataFrame:
    """Per exam year: takers, passes, observed rate (all takers), and among takers linked to an ITE the predicted
    rate (mean estimated pass probability) next to their observed rate; ABIM-reported rates when available."""
    rows = []
    for y, d in t.groupby("exam_year"):
        linked = d[d.predicted.notna()]
        rows.append(
            dict(
                exam_year=int(y),
                takers=len(d),
                passes=int(d.passed.sum()),
                observed=float(d.passed.mean()),
                linked=len(linked),
                predicted=float(linked.predicted.mean()) if len(linked) else np.nan,
                observed_linked=float(linked.passed.mean()) if len(linked) else np.nan,
            )
        )
    s = pd.DataFrame(
        rows, columns=["exam_year", "takers", "passes", "observed", "linked", "predicted", "observed_linked"]
    )
    if not years.empty:
        s = s.merge(years[["exam_year", "program_rate", "all_rate", "passing_score"]], on="exam_year", how="left")
    return s


def apply_links(links: pd.DataFrame, overrides: dict) -> pd.DataFrame:
    """Manual decisions on top of the automatic links: {taker key: resident ID, or None for 'not one of ours'}. A
    resident linked by hand is removed from any other taker it had been linked to automatically."""
    out = links.copy()
    for key, rid in overrides.items():
        if rid is not None:
            out.loc[(out.ID == rid) & (out.key != key), ["ID", "tier"]] = [None, "Unmatched"]
        out.loc[out.key == key, ["ID", "tier"]] = [rid, "Manual" if rid is not None else "Not ours"]
    return out


def by_predicted_tier(t: pd.DataFrame, cutoffs) -> pd.DataFrame:
    """Linked takers grouped by the risk tier of their last-ITE estimate: n, passed, observed pass rate, mean
    estimate. The calibration check in one table."""
    from .nomogram import risk_tier

    d = t[t.predicted.notna()].assign(tier=lambda x: x.predicted.map(lambda p: risk_tier(p, cutoffs)))
    rows = []
    for tier in ("Low", "Intermediate", "High"):
        g = d[d.tier == tier]
        rows.append(
            dict(
                tier=tier,
                n=len(g),
                passed=int(g.passed.sum()),
                observed=float(g.passed.mean()) if len(g) else np.nan,
                predicted=float(g.predicted.mean()) if len(g) else np.nan,
            )
        )
    return pd.DataFrame(rows)
