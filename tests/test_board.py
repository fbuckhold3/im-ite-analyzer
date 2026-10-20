import pandas as pd
import pytest

from ite_core import board, demo, history
from ite_core import session as S


@pytest.fixture(scope="module")
def data():
    d = demo.make_demo()
    r = S.load_rosters([S.Upload(n, b) for n, b in d["rosters"]])
    return r.long, S.build_wide(r, None, None)


def test_board_table_shape(data):
    _, w = data
    bt = board.board_table(w)
    assert len(bt) == 30 and bt.attrs["years"] == [2024, 2025, 2026]
    assert {"Pct_2026", "Ile_2026", "Prob_2026", "Tier", "Tier_change", "Gap_Low"} <= set(bt.columns)
    pgy1 = bt[bt.PGY == 1]
    assert (pgy1.Tier_change == "No prior").all() and (pgy1.Needed_Low == 51.1).all()


def test_cutoff_recomputes_tiers(data):
    _, w = data
    strict, loose = board.board_table(w, (0.5, 0.95)), board.board_table(w, (0.5, 0.75))
    assert (strict.Tier == "Low").sum() <= (loose.Tier == "Low").sum()
    assert (strict.Needed_Low > loose.Needed_Low).all()


def test_tier_summary_and_changes(data):
    _, w = data
    bt = board.board_table(w)
    ts = board.tier_summary(bt)
    assert list(ts.columns) == ["High", "Intermediate", "Low"] and ts.loc["All"].sum() == 30
    assert sum(board.change_summary(bt).values()) == 30


def test_watch_list_rules():
    bt = pd.DataFrame(
        dict(
            ID=list("abcde"),
            Name=list("ABCDE"),
            PGY=[1, 2, 3, 3, 2],
            Tier=["High", "Low", "Intermediate", "High", "Low"],
            Tier_change=["No prior", "Stable", "Stable", "Worsened", "Worsened"],
            Prob_2026=[0.3, 0.95, 0.7, 0.4, 0.92],
        )
    )
    bt.attrs["current_year"] = 2026
    wl = board.watch_list(bt)
    assert wl.ID.tolist() == ["d", "c", "e"]  # PGY-1 excluded; High first, then Intermediate, then worsened Low


def test_resident_history_and_areas(data):
    long, w = data
    rid = w[w.PGY == 3].ID.iloc[0]
    h = board.resident_history(long, rid)
    assert h.Exam_Year.tolist() == [2024, 2025, 2026] and h.PGY.tolist() == [1, 2, 3]
    a = board.resident_areas(long, rid)
    assert len(a) == 11 and a.attrs["exam_year"] == 2026 and set(a.standing) <= {"Strength", "Typical", "Focus"}


def test_areas_missing_for_old_layout(data):
    long, _ = data
    old = long.drop(columns=[c for c in long if c.startswith("ile_")])
    assert board.resident_areas(old, long.ID.iloc[0]) is None


def test_single_year_board(data):
    long, _ = data
    w = history.wide(long[long.Exam_Year == 2026])
    bt = board.board_table(w)
    assert (bt.Tier_change == "No prior").all() and bt.dPct.isna().all()
