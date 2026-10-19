import math

import pandas as pd
import pytest

from ite_core import history, nomogram, roster
from tests.conftest import roster_frame


# --- nomogram -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "pct,pgy,expected",
    [
        # Cross-checked against an independent R implementation of the same coefficients.
        (60, 1, 0.9782),
        (65, 1, 0.9911),
        (65, 2, 0.9577),
        (65, 3, 0.8980),
        (70, 3, 0.9631),
        (55, 2, 0.8001),
    ],
)
def test_pass_prob_known_values(pct, pgy, expected):
    assert round(nomogram.pass_prob(pct, pgy), 4) == expected


def test_pass_prob_missing_and_clamped():
    assert math.isnan(nomogram.pass_prob(None, 2))
    assert math.isnan(nomogram.pass_prob(float("nan"), 2))
    assert nomogram.pass_prob(65, 4) == nomogram.pass_prob(65, 3)


def test_tiers_default_and_custom():
    assert nomogram.risk_tier(0.49) == "High"
    assert nomogram.risk_tier(0.50) == "Intermediate"
    assert nomogram.risk_tier(0.899) == "Intermediate"
    assert nomogram.risk_tier(0.90) == "Low"
    assert nomogram.risk_tier(0.80, cutoffs=(0.5, 0.75)) == "Low"  # stricter/looser cutoffs are a setting
    assert nomogram.risk_tier(None) is None


def test_inverse_roundtrip():
    for pgy in (1, 2, 3):
        assert nomogram.pass_prob(nomogram.pct_for_prob(0.9, pgy), pgy) == pytest.approx(0.9)


def test_trajectory_same_score_can_worsen_tier():
    t = nomogram.trajectory({1: 65, 2: 65, 3: 65})
    assert t.Risk_Tier.tolist() == ["Low", "Low", "Intermediate"]
    assert t.Tier_Change.tolist() == ["No prior", "Stable", "Worsened"]
    assert t.Pct_Needed_Low.tolist() == [51.1, 59.7, 65.1]


# --- roster ---------------------------------------------------------------------------
def test_2023_style_roster_float_ids_blank_rows(roster_files):
    d, info = roster.load_roster(roster_files[0])
    assert info["year"] == 2024
    assert info["dropped_blank_id"] == 1 and info["dropped_pgy"] == 1  # blank ID + PGY-4
    assert set(d.ID) == {"1002", "1003"}  # only 2026 PGY-3s sat in 2024; float 1002.0 -> "1002"
    assert d.PGY.dtype.kind == "i"
    assert info["areas_percentile"] == [] and len(info["areas_pct_correct"]) == 12
    assert "pc_cards" in d and "ile_cards" not in d


def test_pgy4_toggle(roster_files):
    d, _ = roster.load_roster(roster_files[0], include_pgy4=True)
    assert "2001" in set(d.ID)


def test_modern_roster_and_csv_bytes(tmp_path):
    df = roster_frame(2026)
    p = tmp_path / "roster.csv"
    df.to_csv(p, index=False)
    d, info = roster.load_roster(p.read_bytes(), filename="ITE 2026 roster.csv")
    assert info["year"] == 2026 and len(d) == 6 and d.ile_cards.notna().all()


def test_year_override_and_missing_year(tmp_path):
    p = tmp_path / "roster.xlsx"
    roster_frame(2026).to_excel(p, index=False)
    with pytest.raises(ValueError, match="exam year"):
        roster.load_roster(p)
    d, info = roster.load_roster(p, year=2026)
    assert info["year"] == 2026


def test_not_a_roster(tmp_path):
    p = tmp_path / "x_2026.csv"
    pd.DataFrame(dict(a=[1])).to_csv(p, index=False)
    with pytest.raises(ValueError, match="missing column"):
        roster.load_roster(p)


def test_same_year_uploaded_twice(roster_files):
    with pytest.raises(ValueError, match="uploaded twice"):
        roster.load_rosters([roster_files[2], roster_files[2]])


# --- history --------------------------------------------------------------------------
def test_long_wide_and_class(roster_files):
    long, _ = roster.load_rosters(roster_files)
    long = history.add_derived(long)
    assert (long.Grad_Class == long.Exam_Year + 4 - long.PGY).all()
    w = history.wide(long)
    assert w.attrs["current_year"] == 2026 and len(w) == 6
    p3 = w.set_index("ID").loc["1002"]  # PGY-3 in 2026: has 2024, 2025, 2026
    assert p3.PGY_2024 == 1 and p3.PGY_2025 == 2
    assert p3.dPct_1yr == p3.Pct_Correct_2026 - p3.Pct_Correct_2025
    assert w.set_index("ID").loc["1005", "Tier_change"] == "No prior"  # PGY-1
    lv = history.by_level(long)
    assert lv.set_index(["PGY", "Exam_Year"]).n.sum() == len(long)
    m = history.class_matrix(long)
    assert 2027 in m.index and "change" in m
