import pandas as pd
import pytest

from ite_core import demo, history, stats
from ite_core import session as S


@pytest.fixture(scope="module")
def data():
    d = demo.make_demo()
    r = S.load_rosters([S.Upload(n, b) for n, b in d["rosters"]])
    return r.long, S.build_wide(r, None, None)


def test_small_n_flag():
    long = pd.DataFrame(
        dict(
            ID=[str(i) for i in range(7)],
            Exam_Year=2026,
            PGY=[1] * 6 + [2],
            Pct_Correct=60.0,
            Percentile=50.0,
            Pass_Prob=0.95,
            Grad_Class=[2029] * 6 + [2028],
        )
    )
    lv = history.by_level(long).set_index("PGY")
    assert not lv.loc[1, "small_n"] and lv.loc[2, "small_n"]
    assert history.by_class(long).set_index("Grad_Class").loc[2028, "small_n"]


def test_class_trajectories(data):
    long, _ = data
    t = history.class_trajectories(long)
    assert t.Grad_Class.iloc[0] == t.Grad_Class.max()  # newest class first
    status = t.drop_duplicates("Grad_Class").set_index("Grad_Class").status
    assert status[2027] == "current" and status[2026] == "graduated"  # latest exam year is 2026
    assert (t.value == t.ile).all()
    assert (history.class_trajectories(long, "pc").value == t.pc).all()


def test_paired_change_outcomes(data):
    _, w = data
    pct = stats.paired_change(w, 2, outcome="pct_correct")
    ile = stats.paired_change(w, 2)
    assert pct["n"] == ile["n"] == 10
    assert pct["d_mean"] == pct["d_pc"] and ile["d_mean"] == ile["d_ile"]
    assert 0 <= ile["p"] <= 1


def test_paired_points(data):
    _, w = data
    pts = stats.paired_points(w)
    assert len(pts) == 20 and set(pts.PGY) == {2, 3}  # PGY-1s have no prior year
    assert (pts.dPctile_1yr == pts.ile_cur - pts.ile_prev).all()


def test_single_year_has_no_pairs(data):
    long, _ = data
    one = long[long.Exam_Year == 2026]
    w = history.wide(one)
    assert stats.paired_points(w).empty
    assert stats.paired_change(w, 2)["n"] == 0
