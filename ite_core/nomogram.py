"""ABIM pass prediction from ITE % correct, approximating the McDonald et al. (2020) curves.

P(pass) = 1 / (1 + exp(-(b0 + b1 * pct_correct))), one curve per PGY level.

The paper publishes prediction *curves*, not coefficients. These coefficients are a logistic
fit to anchor points read from those curves, so treat results as an approximation.
Source: McDonald FS, et al. Acad Med. 2020;95(9):1388-1395. doi:10.1097/ACM.0000000000003382
See docs/METHODS.md.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

NOMOGRAM = {1: (-7.0641, 0.1811), 2: (-8.1445, 0.1733), 3: (-11.9491, 0.2173)}

# Default: High < 50%, Intermediate 50-90%, Low >= 90%.
# Cutoffs are a program choice — expose them as a setting, not a constant.
DEFAULT_CUTOFFS = (0.50, 0.90)
TIER_ORDER = {"Low": 0, "Intermediate": 1, "High": 2}


def _pgy_key(pgy) -> int:
    return max(1, min(3, int(pgy)))


def pass_prob(pct, pgy) -> float:
    """Pass probability for one score. NaN if either input is missing. PGY clamped to 1-3."""
    if pct is None or pgy is None or pd.isna(pct) or pd.isna(pgy):
        return np.nan
    b0, b1 = NOMOGRAM[_pgy_key(pgy)]
    return 1 / (1 + math.exp(-(b0 + b1 * float(pct))))


def pass_prob_series(pct: pd.Series, pgy: pd.Series) -> pd.Series:
    return pd.Series([pass_prob(a, b) for a, b in zip(pct, pgy, strict=True)], index=pct.index, dtype=float)


def pct_for_prob(prob: float, pgy) -> float:
    """Inverse of the nomogram: % correct needed at this PGY to reach `prob`."""
    b0, b1 = NOMOGRAM[_pgy_key(pgy)]
    return (math.log(prob / (1 - prob)) - b0) / b1


def risk_tier(prob, cutoffs: tuple[float, float] = DEFAULT_CUTOFFS):
    """'High' / 'Intermediate' / 'Low' risk of failing ABIM; None if prob is missing."""
    if prob is None or pd.isna(prob):
        return None
    high_below, low_at = cutoffs
    return "High" if prob < high_below else "Intermediate" if prob < low_at else "Low"


def tier_change(prev, cur) -> str:
    """Compare two risk tiers: 'No prior', 'Worsened', 'Improved', or 'Stable'."""
    if prev is None or pd.isna(prev):
        return "No prior"
    if cur is None or pd.isna(cur):
        return "No current"
    d = TIER_ORDER[cur] - TIER_ORDER[prev]
    return "Worsened" if d > 0 else "Improved" if d < 0 else "Stable"


def trajectory(scores: dict, cutoffs: tuple[float, float] = DEFAULT_CUTOFFS) -> pd.DataFrame:
    """Simple-calculator view: {pgy: pct_correct} -> one row per PGY with probability and tier.

    Also gives the % correct that would have put each year in the Low-risk tier, which
    explains why a tier can worsen with an unchanged score (each PGY curve is steeper).
    """
    rows = []
    for pgy in sorted(int(k) for k in scores):
        pct = scores[pgy]
        p = pass_prob(pct, pgy)
        rows.append(
            dict(
                PGY=pgy,
                Pct_Correct=pct,
                Pass_Prob=p,
                Risk_Tier=risk_tier(p, cutoffs),
                Pct_Needed_Low=round(pct_for_prob(cutoffs[1], pgy), 1),
            )
        )
    out = pd.DataFrame(rows, columns=["PGY", "Pct_Correct", "Pass_Prob", "Risk_Tier", "Pct_Needed_Low"])
    out["Delta_Pct"] = out.Pct_Correct.diff()
    out["Tier_Change"] = [tier_change(a, b) for a, b in zip(out.Risk_Tier.shift(), out.Risk_Tier, strict=True)]
    return out


def curves(step: float = 1.0, lo: float = 20, hi: float = 100) -> pd.DataFrame:
    """Long table of the three nomogram curves for plotting."""
    x = np.arange(lo, hi + step / 2, step)
    return pd.concat(
        [pd.DataFrame(dict(PGY=p, Pct_Correct=x, Pass_Prob=[pass_prob(v, p) for v in x])) for p in NOMOGRAM],
        ignore_index=True,
    )
