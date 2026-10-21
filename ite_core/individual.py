"""Single-resident analysis from their own Examinee Performance Report (+ optional MKSAP).

Content areas are banded by the resident's national *percentile* (rank vs same-PGY U.S. residents), not
% correct, because area difficulty differs: 50th and above / 25th-49th / below 25th.
"""

from __future__ import annotations

import pandas as pd

from . import names
from .nomogram import DEFAULT_CUTOFFS, pass_prob, pct_for_prob, risk_tier

# ITE content area -> MKSAP section codes. PROVISIONAL: GIM / Geriatrics have no one-to-one
# MKSAP section; confirm with ACP before showing residents a study plan built on this.
ITE_TO_MKSAP = {
    "Cardiology": ["CV"],
    "Endocrinology": ["EN"],
    "Gastroenterology": ["GI"],
    "General Internal Medicine": ["FC", "CS", "IN", "DM"],
    "Geriatric Medicine": ["IN"],
    "Hematology/Oncology": ["HM", "ON"],
    "Infectious Diseases": ["ID"],
    "Nephrology": ["NP"],
    "Neurology": ["NR"],
    "Pulmonary and Critical Care Medicine": ["PM", "CC"],
    "Rheumatology": ["RM"],
    "High Value Care": [],
}
STRENGTH_AT, FOCUS_BELOW = 50, 25
# Internal keys stay Strength / Typical / Focus; these are the labels people see.
BAND_LABEL = {
    "Strength": "50th percentile and above",
    "Typical": "25th–49th percentile",
    "Focus": "Below 25th percentile",
}
BAND_ORDER = {"Focus": 0, "Typical": 1, "Strength": 2}


def analyze_examinee(
    report: dict,
    cutoffs=DEFAULT_CUTOFFS,
    mksap_sections: pd.DataFrame | None = None,
    strength_at: int = STRENGTH_AT,
    focus_below: int = FOCUS_BELOW,
) -> dict:
    """report: one item from pdf_reports.parse_examinee_pdf().
    mksap_sections: this person's rows from mksap.by_section() (Subspecialty, a, c, n), optional.
    """
    pgy, pct = report["pgy"], report["pct_correct"]
    prob = pass_prob(pct, pgy)
    out = dict(
        name=report.get("name"),
        candidate_id=report.get("candidate_id"),
        exam_year=report.get("exam_year"),
        pgy=pgy,
        pct_correct=pct,
        percentile=report.get("percentile"),
        pass_prob=prob,
        risk_tier=risk_tier(prob, cutoffs),
        pct_needed_low_now=round(pct_for_prob(cutoffs[1], pgy), 1) if pgy else None,
        pct_needed_low_next=round(pct_for_prob(cutoffs[1], pgy + 1), 1) if pgy and pgy < 3 else None,
    )

    areas = report["areas"]
    core = areas[areas.area != "High Value Care"].sort_values("percentile", ascending=False)
    missed = report["missed"]
    counts = missed.groupby("area").size().rename("n_missed")
    tbl = core.merge(counts, left_on="area", right_index=True, how="left").fillna({"n_missed": 0})
    tbl["n_missed"] = tbl.n_missed.astype(int)
    tbl["standing"] = [
        "Strength" if p >= strength_at else "Focus" if p < focus_below else "Typical" for p in tbl.percentile
    ]
    focus = tbl[tbl.standing == "Focus"]

    if mksap_sections is not None and len(mksap_sections):
        sec = mksap_sections.set_index("Subspecialty")

        def mk(area, col):
            codes = [c for c in ITE_TO_MKSAP.get(area, []) if c in sec.index]
            if not codes:
                return None
            a, c, n = (sec.loc[codes, k].sum() for k in ("a", "c", "n"))
            return round(100 * a / n, 1) if col == "done" else (round(100 * c / a, 1) if a else None)

        tbl["mksap_pct_done"] = [mk(a, "done") for a in tbl.area]
        tbl["mksap_accuracy"] = [mk(a, "acc") for a in tbl.area]

    out.update(
        areas=tbl.reset_index(drop=True),
        strengths=tbl[tbl.standing == "Strength"].area.tolist(),
        focus_areas=focus.area.tolist(),
        missed=missed.reset_index(drop=True),
        missed_by_area={a: g.objective.tolist() for a, g in missed.groupby("area", sort=False)},
        pgy_note=(
            "ACP compares PGY levels other than 1-3 (and non-IM residents) with the PGY-2 group; the pass estimate "
            "uses the PGY-3 curve."
            if pgy and pgy > 3
            else None
        ),
        hvc=areas[areas.area == "High Value Care"].to_dict("records"),
    )
    return out


def group_by_resident(reports: list[dict]) -> dict[str, list[dict]]:
    """Candidate ID -> that resident's reports, oldest exam year first (one per year; a later upload wins)."""
    by: dict[str, dict[int, dict]] = {}
    for r in reports:
        if r.get("candidate_id"):
            by.setdefault(r["candidate_id"], {})[r.get("exam_year") or 0] = r
    return {cid: [yrs[y] for y in sorted(yrs)] for cid, yrs in by.items()}


def history(reports: list[dict], cutoffs=DEFAULT_CUTOFFS) -> pd.DataFrame:
    """One resident's reports -> one row per exam year with pass estimate, tier and changes."""
    rows = [
        dict(Exam_Year=r.get("exam_year"), PGY=r["pgy"], Pct_Correct=r["pct_correct"], Percentile=r["percentile"])
        for r in reports
        if r.get("pgy") and r.get("pct_correct") is not None
    ]
    h = pd.DataFrame(rows, columns=["Exam_Year", "PGY", "Pct_Correct", "Percentile"])
    h["Pass_Prob"] = [pass_prob(a, b) for a, b in zip(h.Pct_Correct, h.PGY, strict=True)]
    h["Risk_Tier"] = h.Pass_Prob.map(lambda p: risk_tier(p, cutoffs))
    h["Pct_Needed_Low"] = [round(pct_for_prob(cutoffs[1], p), 1) for p in h.PGY]
    h["Delta_Pct"] = h.Pct_Correct.diff()
    h["Delta_Percentile"] = h.Percentile.diff()
    return h


def pick_mksap_account(people: pd.DataFrame, report_name: str | None) -> str | None:
    """A resident's own export has one account: use it. Otherwise match the report name (first-name rule)."""
    if len(people) == 1:
        return people.mk_key.iloc[0]
    if not report_name:
        return None
    cw = names.match_mksap(pd.DataFrame(dict(ID=["me"], Name=[report_name])), people)
    return cw.mksap_key.iloc[0]


def next_year_targets(pgy, cutoffs=DEFAULT_CUTOFFS) -> list[tuple[int, float]]:
    """[(later PGY, % correct needed there for the Low-risk cutoff), ...]; empty at PGY-3 and above."""
    if not pgy:
        return []
    return [(p, round(pct_for_prob(cutoffs[1], p), 1)) for p in range(int(pgy) + 1, 4)]


def _norm_objective(s: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def rank_questions(report: dict, program: dict, top_misses: int = 20, top_wins: int = 10) -> dict | None:
    """Rank one resident's questions against national results from the program's Performance Report.

    Missed questions are matched to report items by content area + objective text (2026: 7,071 of 7,073 matched).
    Everything on the exam that was not missed counts as answered correctly.
      misses: missed questions that the most residents at the same PGY level answered correctly nationally
      wins:   the hardest questions (lowest national % correct at that PGY) the resident answered correctly
    Returns None when the reports are from different exam years.
    """
    if program is None or (
        report.get("exam_year") and program.get("exam_year") and report["exam_year"] != program["exam_year"]
    ):
        return None
    items = program["items"].copy()
    pgy = report.get("pgy") or 2
    col = f"all{min(3, max(1, int(pgy)))}" if 1 <= int(pgy) <= 3 else "allA"
    items["key"] = items.area + "|" + items.objective.map(_norm_objective)
    missed = report["missed"]
    mkeys = set(missed.area + "|" + missed.objective.map(_norm_objective))
    items["missed"] = items.key.isin(mkeys)
    items["national"] = items[col]
    cols = ["area", "objective", "hvc", "national"]
    misses = items[items.missed].sort_values(["national", "area"], ascending=[False, True]).head(top_misses)[cols]
    wins = items[~items.missed].sort_values(["national", "area"]).head(top_wins)[cols]
    return dict(
        misses=misses.reset_index(drop=True),
        wins=wins.reset_index(drop=True),
        matched=int(items.missed.sum()),
        missed_total=int(len(missed)),
        pgy_column=col,
        pgy_label="all PGYs" if col == "allA" else f"PGY-{col[-1]}",
    )


def target_gap_phrase(pct_now, target) -> str:
    """'4.3 points more than this year's 56%' or 'you're already 1.9 points above it'."""
    if pct_now is None or pct_now != pct_now:
        return ""
    gap = round(target - pct_now, 1)
    if gap > 0:
        return f"{gap:.1f} points more than this year's {pct_now:.0f}%"
    return f"you're already {abs(gap):.1f} points above it" if gap < 0 else "the same as this year"
