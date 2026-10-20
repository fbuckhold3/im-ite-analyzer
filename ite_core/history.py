"""Multi-year ITE tables: long (person x year), wide (current residents), by level, by class."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .nomogram import DEFAULT_CUTOFFS, pass_prob_series, risk_tier, tier_change

WIDE_METRICS = ["PGY", "Pct_Correct", "Percentile", "Pass_Prob", "Risk_Tier"]
SMALL_N = 5  # cells with fewer residents are flagged (and suppressed in de-identified outputs)


def add_derived(long: pd.DataFrame, cutoffs=DEFAULT_CUTOFFS) -> pd.DataFrame:
    """Grad_Class (= Exam_Year + 4 - PGY), Pass_Prob, Risk_Tier."""
    out = long.copy()
    out["Grad_Class"] = out.Exam_Year + 4 - out.PGY
    out["Pass_Prob"] = pass_prob_series(out.Pct_Correct, out.PGY)
    out["Risk_Tier"] = out.Pass_Prob.map(lambda p: risk_tier(p, cutoffs))
    return out


def _agg(cutoffs):
    low_at = cutoffs[1]
    return dict(
        n=("ID", "size"),
        pc=("Pct_Correct", "mean"),
        ile=("Percentile", "mean"),
        med=("Percentile", "median"),
        ge50=("Percentile", lambda s: round(100 * (s >= 50).mean())),
        lt35=("Percentile", lambda s: round(100 * (s < 35).mean())),
        pp_low=("Pass_Prob", lambda s: round(100 * (s >= low_at).mean())),
    )


def by_level(long: pd.DataFrame, cutoffs=DEFAULT_CUTOFFS) -> pd.DataFrame:
    """PGY x exam year: n, mean % correct, mean/median percentile, % >=50th, % <35th,
    % at or above the Low-risk cutoff (pp_low)."""
    out = long.groupby(["PGY", "Exam_Year"]).agg(**_agg(cutoffs)).round(1).reset_index()
    out["small_n"] = out.n < SMALL_N
    return out


def by_class(long: pd.DataFrame, cutoffs=DEFAULT_CUTOFFS) -> pd.DataFrame:
    """Graduating class x PGY, with the exam year each cell came from."""
    g = long.groupby(["Grad_Class", "PGY"]).agg(**_agg(cutoffs), Exam_Year=("Exam_Year", "first"))
    out = g.round(1).reset_index()
    out["small_n"] = out.n < SMALL_N
    return out


def class_trajectories(long: pd.DataFrame, value: str = "ile", cutoffs=DEFAULT_CUTOFFS) -> pd.DataFrame:
    """by_class() plus `status`: 'current' if the class is still in training in the latest exam year,
    else 'graduated'. Sorted newest class first (the fixed colour order for charts)."""
    t = by_class(long, cutoffs)
    latest = int(long.Exam_Year.max())
    t["status"] = np.where(t.Grad_Class > latest, "current", "graduated")
    t["value"] = t[value]
    return t.sort_values(["Grad_Class", "PGY"], ascending=[False, True]).reset_index(drop=True)


def class_matrix(long: pd.DataFrame, value: str = "ile") -> pd.DataFrame:
    """Rows = graduating class, cols = PGY-1/2/3 (mean percentile by default), + change PGY-1 -> latest."""
    m = by_class(long).pivot(index="Grad_Class", columns="PGY", values=value)
    first = m.get(1)
    latest = m.ffill(axis=1).iloc[:, -1]
    m["change"] = latest - first if first is not None else np.nan
    return m


def wide(long: pd.DataFrame, current_year: int | None = None) -> pd.DataFrame:
    """One row per resident tested in `current_year` (default: latest), keeping roster order.

    Columns: ID, Name, PGY, then <metric>_<year> for every exam year, then 1-year deltas
    (dPct_1yr, dPctile_1yr, dProb_1yr) and Tier_change vs the prior year.
    """
    yr = int(current_year or long.Exam_Year.max())
    cur = long[long.Exam_Year == yr]
    w = cur[["ID", "Name", "PGY"]].reset_index(drop=True).copy()
    for y in sorted(long.Exam_Year.unique()):
        s = long[long.Exam_Year == y].set_index("ID")
        for c in WIDE_METRICS:
            if c in s:
                w[f"{c}_{y}"] = w.ID.map(s[c])
    w = w.drop(columns=[f"PGY_{yr}"])
    prev = yr - 1
    if f"Pct_Correct_{prev}" in w:
        w["dPct_1yr"] = w[f"Pct_Correct_{yr}"] - w[f"Pct_Correct_{prev}"]
        w["dPctile_1yr"] = w[f"Percentile_{yr}"] - w[f"Percentile_{prev}"]
        w["dProb_1yr"] = w[f"Pass_Prob_{yr}"] - w[f"Pass_Prob_{prev}"]
        w["Tier_change"] = [
            tier_change(a, b) for a, b in zip(w[f"Risk_Tier_{prev}"], w[f"Risk_Tier_{yr}"], strict=True)
        ]
    else:
        w["dPct_1yr"] = w["dPctile_1yr"] = w["dProb_1yr"] = np.nan
        w["Tier_change"] = "No prior"
    w.attrs["current_year"] = yr
    return w


def attach_mksap(w: pd.DataFrame, crosswalk: pd.DataFrame, people: pd.DataFrame) -> pd.DataFrame:
    """Add mk_* columns via the confirmed crosswalk (acp_id -> mksap_key). Unlinked -> NaN."""
    link = crosswalk.dropna(subset=["mksap_key"])[["acp_id", "mksap_key"]]
    cols = ["mk_key", "mk_answered", "mk_correct", "mk_bank", "mk_pct_correct", "mk_pct_bank"]
    mk = link.merge(people[cols], left_on="mksap_key", right_on="mk_key").drop(columns=["mksap_key"])
    out = w.merge(mk.rename(columns={"acp_id": "ID"}), on="ID", how="left")
    out.attrs.update(w.attrs)
    return out
