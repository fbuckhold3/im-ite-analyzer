"""Single-resident analysis from their own Examinee Performance Report (+ optional MKSAP).

Strengths / areas to improve use the content-area *percentile* (rank vs same-PGY U.S.
residents), not % correct, because area difficulty differs.
"""

from __future__ import annotations

import pandas as pd

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
STRENGTH_AT, FOCUS_BELOW = 60, 35


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
    if focus.empty:  # nothing below the cutoff: still name the two relatively weakest areas
        focus = tbl.tail(2)

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
        missed_by_area={a: g.objective.tolist() for a, g in missed.groupby("area", sort=False)},
        hvc=areas[areas.area == "High Value Care"].to_dict("records"),
    )
    return out
