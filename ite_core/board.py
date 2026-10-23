"""Program board-pass view: every current resident's estimate, tier and change, under a chosen cutoff."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .individual import FOCUS_BELOW, STRENGTH_AT
from .nomogram import DEFAULT_CUTOFFS, TIER_ORDER, pct_for_prob, risk_tier, tier_change
from .roster import AREA_LABELS

TIERS = ["High", "Intermediate", "Low"]


def _years(w: pd.DataFrame) -> list[int]:
    return sorted(int(c.rsplit("_", 1)[1]) for c in w if c.startswith("Pct_Correct_"))


def board_table(w: pd.DataFrame, cutoffs=DEFAULT_CUTOFFS) -> pd.DataFrame:
    """One row per current resident. Tiers are recomputed from the stored probabilities with `cutoffs`.

    Columns: ID, Name, PGY, then per exam year Pct_<y>, Ile_<y>, Prob_<y>, Tier_<y>; then Tier (current),
    Tier_prev, Tier_change, dPct, dIle, Needed_Low (% correct for Low risk at the current PGY), Gap_Low
    (current % correct minus Needed_Low), and MKSAP columns when present.
    """
    years = _years(w)
    cy = int(w.attrs.get("current_year") or max(years))
    out = w[["ID", "Name", "PGY"]].copy()
    for y in years:
        out[f"Pct_{y}"] = w[f"Pct_Correct_{y}"]
        out[f"Ile_{y}"] = w[f"Percentile_{y}"]
        out[f"Prob_{y}"] = w[f"Pass_Prob_{y}"]
        out[f"Tier_{y}"] = out[f"Prob_{y}"].map(lambda p: risk_tier(p, cutoffs))
    out["Tier"] = out[f"Tier_{cy}"]
    out["Tier_prev"] = out[f"Tier_{cy - 1}"] if f"Tier_{cy - 1}" in out else None
    out["Tier_change"] = [tier_change(a, b) for a, b in zip(out.Tier_prev, out.Tier, strict=True)]
    out["dPct"] = out[f"Pct_{cy}"] - out[f"Pct_{cy - 1}"] if f"Pct_{cy - 1}" in out else np.nan
    out["dIle"] = out[f"Ile_{cy}"] - out[f"Ile_{cy - 1}"] if f"Ile_{cy - 1}" in out else np.nan
    out["Needed_Low"] = [round(pct_for_prob(cutoffs[1], p), 1) for p in out.PGY]
    out["Gap_Low"] = (out[f"Pct_{cy}"] - out.Needed_Low).round(1)
    for c in ("mk_answered", "mk_pct_correct"):
        if c in w:
            out[c] = w[c]
    out.attrs.update(current_year=cy, years=years, cutoffs=cutoffs)
    return out


def tier_summary(bt: pd.DataFrame) -> pd.DataFrame:
    """PGY x tier counts (rows PGY-1..3 plus All)."""
    t = pd.crosstab(bt.PGY, bt.Tier).reindex(columns=TIERS, fill_value=0)
    t.loc["All"] = t.sum()
    return t


def change_summary(bt: pd.DataFrame) -> dict:
    order = ["Worsened", "Improved", "Stable", "No prior"]
    c = bt.Tier_change.value_counts()
    return {k: int(c.get(k, 0)) for k in order}


def watch_list(bt: pd.DataFrame) -> pd.DataFrame:
    """PGY-2/3 residents in High or Intermediate risk, or whose tier worsened since last year.
    Most at risk first."""
    cy = bt.attrs["current_year"]
    m = bt.PGY.isin([2, 3]) & (bt.Tier.isin(["High", "Intermediate"]) | bt.Tier_change.eq("Worsened"))
    out = bt[m].assign(_o=bt.Tier.map(TIER_ORDER).fillna(0) * -1, _p=bt[f"Prob_{cy}"])
    return out.sort_values(["_o", "_p"]).drop(columns=["_o", "_p"])


def resident_history(long: pd.DataFrame, rid: str, cutoffs=DEFAULT_CUTOFFS) -> pd.DataFrame:
    """One resident's exam years, in the shape modules.common.trajectory_table() expects."""
    d = long[long.ID == rid].sort_values("Exam_Year")
    h = d[["Exam_Year", "PGY", "Pct_Correct", "Percentile", "Pass_Prob"]].reset_index(drop=True)
    h["Risk_Tier"] = h.Pass_Prob.map(lambda p: risk_tier(p, cutoffs))
    h["Pct_Needed_Low"] = [round(pct_for_prob(cutoffs[1], p), 1) for p in h.PGY]
    h["Delta_Pct"] = h.Pct_Correct.diff()
    h["Delta_Percentile"] = h.Percentile.diff()
    return h


def resident_areas(long: pd.DataFrame, rid: str) -> pd.DataFrame | None:
    """Latest-year content-area percentiles from the roster (None for 2023-style rosters without them).
    Same columns the resident tab's area chart uses; national mean/SD are not in rosters."""
    d = long[long.ID == rid].sort_values("Exam_Year")
    if d.empty:
        return None
    row = d.iloc[-1]
    rows = []
    for key, label in AREA_LABELS.items():
        if key == "hvc" or f"ile_{key}" not in row or pd.isna(row[f"ile_{key}"]):
            continue
        ile = float(row[f"ile_{key}"])
        rows.append(
            dict(
                area=label,
                pct_correct=row.get(f"pc_{key}"),
                national_mean=np.nan,
                percentile=ile,
                standing="Strength" if ile >= STRENGTH_AT else "Focus" if ile < FOCUS_BELOW else "Typical",
            )
        )
    if not rows:
        return None
    out = pd.DataFrame(rows).sort_values("percentile", ascending=False).reset_index(drop=True)
    out.attrs["exam_year"] = int(row.Exam_Year)
    return out


RANGE_LEVEL = 0.80  # central share of the "likely range" for the number of passes


def passes_distribution(probs) -> np.ndarray:
    """Exact distribution of the number of passes among independent residents (Poisson-binomial).

    Element k is P(exactly k pass). Built by convolution — exact, and instant for program-sized groups.
    """
    dist = np.array([1.0])
    for p in probs:
        dist = np.convolve(dist, [1 - p, p])
    return dist


def likely_range(probs, level: float = RANGE_LEVEL) -> tuple[int, int]:
    """Smallest and largest number of passes in the central `level` of the distribution."""
    cdf = np.cumsum(passes_distribution(probs))
    tail = (1 - level) / 2
    lo = int(np.searchsorted(cdf, tail - 1e-12))
    hi = int(np.searchsorted(cdf, 1 - tail - 1e-12))
    return lo, min(hi, len(cdf) - 1)


def class_pass_rates(bt: pd.DataFrame, level: float = RANGE_LEVEL) -> pd.DataFrame:
    """Projected ABIM pass rate for each current class (PGY level).

    projected = mean of the residents' estimated pass probabilities (the expected share passing); lo/hi = likely
    range for the number who pass, assuming residents pass or fail independently and the estimates are exact — so it
    reflects chance only, not uncertainty in the nomogram. Residents without a current-year estimate are counted
    in `missing`, not in n.
    """
    cy = bt.attrs["current_year"]
    rows = []
    for p in sorted((int(x) for x in bt.PGY.dropna().unique()), reverse=True):  # closest to the exam first
        if p not in (1, 2, 3):
            continue
        probs = bt.loc[bt.PGY == p, f"Prob_{cy}"]
        ok = probs.dropna().to_numpy(dtype=float)
        lo, hi = likely_range(ok, level) if len(ok) else (0, 0)
        rows.append(
            dict(
                PGY=p,
                grad_class=cy + 4 - p,
                n=len(ok),
                missing=int(probs.isna().sum()),
                projected=float(ok.mean()) if len(ok) else np.nan,
                expected_passes=float(ok.sum()),
                lo=lo,
                hi=hi,
            )
        )
    out = pd.DataFrame(rows, columns=["PGY", "grad_class", "n", "missing", "projected", "expected_passes", "lo", "hi"])
    out.attrs.update(current_year=cy, level=level)
    return out
