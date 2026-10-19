"""Program analyses: paired year-over-year change and MKSAP -> next-ITE models.

All observational. The MKSAP snapshot may post-date the ITE, and MKSAP editions reset.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

THIRDS = ["Lowest", "Middle", "Highest"]


def _year(w: pd.DataFrame, year: int | None) -> int:
    return int(
        year or w.attrs.get("current_year") or max(int(c.rsplit("_", 1)[1]) for c in w if c.startswith("Pct_Correct_"))
    )


def _analysis_frame(w: pd.DataFrame, year: int | None = None) -> pd.DataFrame:
    """Residents with both this year's and last year's ITE, with generic column names."""
    y = _year(w, year)
    s = w[w.dPct_1yr.notna()].copy()
    s["pc_cur"], s["pc_prev"] = s[f"Pct_Correct_{y}"], s[f"Pct_Correct_{y - 1}"]
    s["ile_cur"], s["ile_prev"] = s[f"Percentile_{y}"], s[f"Percentile_{y - 1}"]
    if "mk_answered" in s:
        s["log_ans"] = np.log1p(s.mk_answered)
    return s


def paired_change(w: pd.DataFrame, pgy: int, year: int | None = None) -> dict:
    """Same residents, last year -> this year, one PGY level. Wilcoxon signed-rank on percentile change."""
    s = _analysis_frame(w, year)
    s = s[s.PGY == pgy]
    d = s.dPctile_1yr.dropna()
    p = stats.wilcoxon(d).pvalue if len(d) >= 2 and (d != 0).any() else np.nan
    return dict(
        pgy=pgy,
        n=int(len(d)),
        d_mean=round(d.mean(), 1),
        d_med=float(d.median()) if len(d) else np.nan,
        p=round(p, 3),
        d_pc=round(s.dPct_1yr.mean(), 1),
        up=int((d >= 10).sum()),
        down=int((d <= -10).sum()),
    )


def _spear(s, a, b):
    r = stats.spearmanr(s[a], s[b], nan_policy="omit")
    return [round(float(r[0]), 3), round(float(r[1]), 3)]


def mksap_models(w: pd.DataFrame, year: int | None = None) -> dict:
    """MKSAP volume / accuracy vs this year's ITE, adjusted for last year's ITE and PGY.

    Outcome: % correct (headline, because the ABIM nomogram uses it) and percentile.
      base  : pc_cur ~ pc_prev + C(PGY)
      vol   : + log(1 + questions answered)    -> report beta*ln2 per doubling, beta*ln8 for 100 -> 800
      acc   : + MKSAP % correct
      both  : + log_ans + MKSAP % correct
    """
    s = _analysis_frame(w, year).dropna(subset=["mk_answered"])
    fit = lambda f, d=s: smf.ols(f, d).fit()
    g0 = fit("pc_cur ~ pc_prev + C(PGY)")
    g1 = fit("pc_cur ~ pc_prev + C(PGY) + log_ans")
    acc = s.dropna(subset=["mk_pct_correct"])
    g2 = fit("pc_cur ~ pc_prev + C(PGY) + mk_pct_correct", acc)
    g3 = fit("pc_cur ~ pc_prev + C(PGY) + log_ans + mk_pct_correct", acc)
    il = s.dropna(subset=["ile_cur", "ile_prev"])
    h0 = fit("ile_cur ~ ile_prev + C(PGY)", il)
    h1 = fit("ile_cur ~ ile_prev + C(PGY) + log_ans", il)
    return dict(
        n=int(len(s)),
        n_acc=int(len(acc)),
        n_ile=int(len(il)),
        dbl=round(g1.params.log_ans * np.log(2), 1),
        b_vol=round(g1.params.log_ans, 2),
        p_vol=float(g1.pvalues.log_ans),
        eff_100_800=round(g1.params.log_ans * np.log(8), 1),
        r2_base=round(g0.rsquared, 2),
        r2_vol=round(g1.rsquared, 2),
        r2_both=round(g3.rsquared, 2),
        b_acc=round(g2.params.mk_pct_correct, 2),
        p_acc=float(g2.pvalues.mk_pct_correct),
        p_vol_both=float(g3.pvalues.log_ans),
        p_acc_both=float(g3.pvalues.mk_pct_correct),
        dbl_ile=round(h1.params.log_ans * np.log(2), 1),
        p_ile=float(h1.pvalues.log_ans),
        r2_ile_base=round(h0.rsquared, 2),
        r2_ile_vol=round(h1.rsquared, 2),
        rho_q_pc_cur=_spear(s, "mk_answered", "pc_cur"),
        rho_q_dpc=_spear(s, "mk_answered", "dPct_1yr"),
        rho_q_pc_prev=_spear(s, "mk_answered", "pc_prev"),
        rho_acc_pc_cur=_spear(s, "mk_pct_correct", "pc_cur"),
    )


def mksap_thirds(w: pd.DataFrame, year: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split residents into thirds of MKSAP volume *within each PGY*; compare ITE change.

    Ties are broken by row order (roster order), as in the Oct 2026 analysis.
    Returns (by PGY x third, pooled by third).
    """
    s = _analysis_frame(w, year).dropna(subset=["mk_answered"])
    s["vol"] = (
        s.groupby("PGY")
        .mk_answered.transform(lambda x: pd.qcut(x.rank(method="first"), 3, labels=THIRDS))
        .astype(pd.CategoricalDtype(THIRDS, ordered=True))
    )
    agg = dict(
        n=("ID", "size"),
        q=("mk_answered", "median"),
        pc_prev=("pc_prev", "mean"),
        pc_cur=("pc_cur", "mean"),
        dpc=("dPct_1yr", "mean"),
        ile_prev=("ile_prev", "mean"),
        ile_cur=("ile_cur", "mean"),
        dile=("dPctile_1yr", "mean"),
    )
    by_pgy = s.groupby(["PGY", "vol"], observed=True).agg(**agg).round(1).reset_index()
    pooled = s.groupby("vol", observed=True).agg(**agg).round(1).reset_index()
    return by_pgy, pooled


def mksap_by_pgy(w: pd.DataFrame, year: int | None = None) -> pd.DataFrame:
    """Per PGY: MKSAP volume summary and Spearman rho of volume vs this year's percentile."""
    y = _year(w, year)
    rows = []
    for p, v in w.dropna(subset=["mk_answered"]).groupby("PGY"):
        a = v.mk_answered
        rho = stats.spearmanr(a, v[f"Percentile_{y}"], nan_policy="omit")
        rows.append(
            dict(
                PGY=int(p),
                n=int(len(v)),
                med=a.median(),
                q1=a.quantile(0.25),
                q3=a.quantile(0.75),
                acc=round(100 * v.mk_correct.sum() / max(1, a.sum()), 1),
                rho_vol_ile=round(float(rho[0]), 2),
                p_vol_ile=round(float(rho[1]), 3),
            )
        )
    return pd.DataFrame(rows)
