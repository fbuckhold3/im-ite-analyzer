import pandas as pd
import pytest

from ite_core import demo, mksap, names, stats
from ite_core import session as S


@pytest.fixture(scope="module")
def data():
    d = demo.make_demo()
    r = S.load_rosters([S.Upload(n, b) for n, b in d["rosters"]])
    mk = S.load_mksap(S.Upload(*d["mksap"]))
    cw = names.confirm_tier(S.match(r, mk), "Probable")  # a reviewed dataset: suggestions confirmed
    return S.build_wide(r, mk, cw), mk


def test_progress_by_pgy(data):
    w, _ = data
    pr = mksap.progress_by_pgy(w).set_index("PGY")
    assert pr.n.sum() == 29  # one demo resident has no MKSAP account
    v = w[(w.PGY == 2) & w.mk_answered.notna()]
    assert pr.loc[2, "med"] == v.mk_answered.median()
    assert pr.loc[2, "acc"] == round(100 * v.mk_correct.sum() / v.mk_answered.sum(), 1)


def test_bins_table(data):
    w, _ = data
    b = mksap.bins_table(w)
    assert list(b.index) == mksap.VOLUME_LABELS and b.values.sum() == 29


def test_section_table_math():
    sections = pd.DataFrame(
        dict(mk_key=["a", "a", "b"], Subspecialty=["CV", "GI", "CV"], a=[10, 0, 30], c=[5, 0, 15], n=[50, 40, 50])
    )
    w = pd.DataFrame(dict(mk_key=["a", "b"], PGY=[2, 2], mk_answered=[10, 30]))
    st = mksap.section_table(sections, w).set_index("Subspecialty")
    assert st.loc["CV", "done"] == 40.0 and st.loc["CV", "acc"] == 50.0  # 40 / (2 x 50); 20 / 40
    assert pd.isna(st.loc["GI", "acc"]) and st.loc["GI", "done"] == 0.0
    assert st.index[0] == "CV"  # largest section first


def test_models_need_minimum_n(data):
    w, _ = data
    ok = stats.mksap_models(w)
    assert ok["ok"] and ok["n"] == 19
    few = stats.mksap_models(w.head(8))
    assert not few["ok"] and "at least 10" in few["reason"]


def test_models_without_mksap():
    d = demo.make_demo()
    r = S.load_rosters([S.Upload(n, b) for n, b in d["rosters"]])
    w = S.build_wide(r, None, None)
    assert not stats.mksap_models(w)["ok"]
    assert stats.mksap_points(w).empty and mksap.progress_by_pgy(w).empty


def test_points_and_trend(data):
    w, _ = data
    pts = stats.mksap_points(w)
    assert len(pts) == 19 and set(pts.PGY) == {2, 3}
    xs, ys = stats.trend_line(pts.mk_answered, pts.dPct_1yr)
    assert len(xs) == 50 and xs.min() >= pts.mk_answered.min() - 1e-6
    assert stats.trend_line(pts.mk_answered.head(2), pts.dPct_1yr.head(2))[0].size == 0


def _overview_from_detail(detail_csv: bytes) -> bytes:
    """Invented overview built from the demo detail export (same people, totals only)."""
    people = mksap.per_person(mksap.load_mksap(detail_csv))
    ov = pd.DataFrame(
        {
            "Last Name": people.mk_last,
            "First Name": people.mk_first,
            "Total Questions": 600,
            "Number Complete": people.mk_answered,
            "Percentage Complete": (100 * people.mk_answered / 600).round(),
            "Number Correct": people.mk_correct,
            "Percentage Correct": (100 * people.mk_correct / people.mk_answered.where(people.mk_answered > 0))
            .fillna(0)
            .round(),
        }
    )
    return ov.to_csv(index=False).encode()


def test_overview_export_detected_and_analysable():
    d = demo.make_demo()
    r = S.load_rosters([S.Upload(n, b) for n, b in d["rosters"]])
    mk = S.load_mksap(S.Upload("members-overview.csv", _overview_from_detail(d["mksap"][1])))
    assert mk.kind == "overview" and mk.sections is None and mk.bank == 600
    det = S.load_mksap(S.Upload(*d["mksap"]))
    assert det.kind == "detail" and det.sections is not None
    cw = S.match(r, mk)
    assert (cw.mksap_key.notna()).sum() == (S.match(r, det).mksap_key.notna()).sum()
    w = S.build_wide(r, mk, names.confirm_tier(cw, "Probable"))
    assert stats.mksap_models(w)["ok"]
    assert mksap.progress_by_pgy(w).n.sum() == 29


def test_unknown_mksap_layout_is_explained():
    bad = pd.DataFrame({"Last Name": ["A"], "First Name": ["B"], "Score": [1]}).to_csv(index=False).encode()
    with pytest.raises(mksap.UploadError, match="members overview"):
        mksap.read_export(bad, "x.csv")
    ov = (
        pd.DataFrame(
            {
                "Last Name": ["A"],
                "First Name": ["B"],
                "Total Questions": [10],
                "Number Complete": ["lots"],
                "Number Correct": [1],
            }
        )
        .to_csv(index=False)
        .encode()
    )
    with pytest.raises(mksap.UploadError, match="not numbers"):
        mksap.read_export(ov, "x.csv")
