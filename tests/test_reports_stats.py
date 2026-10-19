import numpy as np
import pandas as pd
import pytest

from ite_core import individual, mksap, pdf_reports, stats
from tests.conftest import examinee_pages, program_pages


# --- examinee report ------------------------------------------------------------------
def test_examinee_report_parse():
    (r,) = pdf_reports.parse_examinee_text(examinee_pages())
    assert (r["candidate_id"], r["program_id"], r["exam_year"]) == ("1001", "999999", 2026)
    assert (r["pct_correct"], r["percentile"], r["pgy"]) == (68, 38, 3)
    assert len(r["areas"]) == 12
    hvc = r["areas"].set_index("area").loc["High Value Care"]
    assert hvc.percentile == 53
    m = r["missed"]
    assert m.area.tolist() == ["Cardiology", "Cardiology", "Endocrinology", "Infectious Diseases"]
    assert m.objective.iloc[1].endswith("wraps onto a second printed line.")  # wrapped line joined
    assert m.hvc.tolist() == [False, False, True, False] and not m.objective.str.contains(r"\*").any()


def test_composite_report_splits_on_candidate_id():
    pages = examinee_pages(cid="1001") + examinee_pages(name="Test, Blake", cid="1002", pc=60, ile=20, pgy=2)
    reps = pdf_reports.parse_examinee_text(pages)
    assert [r["candidate_id"] for r in reps] == ["1001", "1002"]
    assert reps[1]["pages"] == [2, 3] and reps[1]["pgy"] == 2


def test_individual_analysis():
    (r,) = pdf_reports.parse_examinee_text(examinee_pages())
    sec = pd.DataFrame(dict(Subspecialty=["CV", "ID"], a=[50, 5], c=[40, 2], n=[100, 50]))
    a = individual.analyze_examinee(r, mksap_sections=sec)
    assert a["risk_tier"] == "Low"  # 68% at PGY-3 -> 0.944
    assert round(a["pass_prob"], 3) == round(1 / (1 + np.exp(-(-11.9491 + 0.2173 * 68))), 3)
    assert a["pct_needed_low_next"] is None and a["pct_needed_low_now"] == 65.1
    assert a["strengths"] == ["General Internal Medicine", "Rheumatology"]
    assert "Infectious Diseases" in a["focus_areas"] and "Endocrinology" in a["focus_areas"]
    t = a["areas"].set_index("area")
    assert t.loc["Cardiology", "n_missed"] == 2 and t.loc["Cardiology", "mksap_pct_done"] == 50.0
    assert t.loc["Infectious Diseases", "mksap_accuracy"] == 40.0
    assert pd.isna(t.loc["Nephrology", "mksap_pct_done"])


# --- program report -------------------------------------------------------------------
def test_program_report_parse_and_flags():
    p = pdf_reports.parse_program_text(program_pages())
    assert (p["program_id"], p["program_name"], p["exam_year"]) == ("999999", "TEST PROGRAM", 2026)
    ar = p["areas"].set_index("area")
    assert ar.loc["Cardiology", "rank2"] == 59 and ar.loc["Total Test", "ourA"] == 66
    assert ar.loc["Number of Residents", "ourA"] == 81
    it = p["items"]
    assert len(it) == 3
    assert it.objective.iloc[1].endswith("long objective that wraps.")
    assert it.hvc.tolist() == [False, False, True]
    assert it.flag.tolist() == [None, "red", "yellow"]


# --- program stats --------------------------------------------------------------------
@pytest.fixture
def synthetic_wide():
    """60 PGY-2/3 residents where MKSAP volume truly adds ~2 points per doubling."""
    rng = np.random.default_rng(1)
    n = 60
    pgy = np.repeat([2, 3], n // 2)
    prev = rng.normal(62, 6, n)
    q = np.round(np.exp(rng.uniform(np.log(20), np.log(1500), n)))
    cur = 10 + 0.85 * prev + 2 / np.log(2) * np.log1p(q) * 0.5 + rng.normal(0, 2, n)
    w = pd.DataFrame(
        dict(
            ID=[str(i) for i in range(n)],
            PGY=pgy,
            Pct_Correct_2025=prev,
            Pct_Correct_2026=cur,
            Percentile_2025=prev - 20,
            Percentile_2026=cur - 20,
            mk_answered=q,
            mk_correct=np.round(q * 0.6),
            mk_pct_correct=rng.normal(60, 5, n),
        )
    )
    w["dPct_1yr"] = w.Pct_Correct_2026 - w.Pct_Correct_2025
    w["dPctile_1yr"] = w.Percentile_2026 - w.Percentile_2025
    w.attrs["current_year"] = 2026
    return w


def test_mksap_models_recover_effect(synthetic_wide):
    m = stats.mksap_models(synthetic_wide)
    assert m["n"] == 60 and 0.5 < m["dbl"] < 1.5 and m["p_vol"] < 0.01
    assert m["r2_vol"] > m["r2_base"]
    assert m["eff_100_800"] == pytest.approx(m["b_vol"] * np.log(8), abs=0.06)


def test_thirds_and_paired(synthetic_wide):
    by_pgy, pooled = stats.mksap_thirds(synthetic_wide)
    assert by_pgy.n.sum() == 60 and pooled.vol.tolist() == ["Lowest", "Middle", "Highest"]
    assert pooled.set_index("vol").dpc["Highest"] > pooled.set_index("vol").dpc["Lowest"]
    pc = stats.paired_change(synthetic_wide, 2)
    assert pc["n"] == 30 and 0 <= pc["p"] <= 1


def test_volume_bins():
    b = mksap.volume_bin(pd.Series([0, 99, 100, 999, 1000]))
    assert b.tolist() == ["Under 100", "Under 100", "100–249", "500–999", "1,000+"]
