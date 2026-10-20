import pandas as pd
import pytest

from ite_core import demo, individual, mksap, pdf_reports
from tests.conftest import examinee_pages


def test_sample_reports_split_by_year():
    reps = demo.sample_examinee_reports()
    assert [(r["exam_year"], r["pgy"]) for r in reps] == [(2025, 1), (2026, 2)]
    for r in reps:
        assert len(r["areas"]) == 12 and len(r["missed"]) > 0
        assert r["missed"].objective.str.endswith(".").all()  # wrapped lines re-joined


def test_same_candidate_two_years_in_one_file_are_two_reports():
    pages = examinee_pages(cid="1001") + [
        p.replace("2026 Internal", "2027 Internal") for p in examinee_pages(cid="1001")
    ]
    reps = pdf_reports.parse_examinee_text(pages)
    assert [r["exam_year"] for r in reps] == [2026, 2027]


def test_history_and_grouping():
    reps = demo.sample_examinee_reports()
    groups = individual.group_by_resident(reps + [reps[0]])  # duplicate year collapses
    (only,) = groups.values()
    h = individual.history(only)
    assert h.Exam_Year.tolist() == [2025, 2026]
    assert h.Delta_Pct.iloc[1] == 8 and h.Delta_Percentile.iloc[1] == 5
    assert h.Pct_Needed_Low.tolist() == [51.1, 59.7]


def test_analysis_outputs():
    a = individual.analyze_examinee(demo.sample_examinee_reports()[-1])
    assert a["strengths"] == ["General Internal Medicine", "Rheumatology"]
    assert set(a["focus_areas"]) == {"Neurology", "Infectious Diseases", "Endocrinology"}
    assert a["missed"].hvc.sum() == 2 and a["pgy_note"] is None
    assert a["pct_needed_low_next"] == 65.1


def test_pgy4_note():
    (r,) = pdf_reports.parse_examinee_text(examinee_pages(pgy=4))
    a = individual.analyze_examinee(r)
    assert "PGY-2 group" in a["pgy_note"] and a["pct_needed_low_next"] is None


def test_pick_mksap_account():
    own = mksap.per_person(mksap.load_mksap(demo.sample_mksap_csv()))
    assert individual.pick_mksap_account(own, "Anything, At All") == "Sample|Alex"  # single account: use it
    many = pd.DataFrame(
        dict(mk_key=["Sample|Alex", "Sample|Robin"], mk_last=["Sample"] * 2, mk_first=["Alex", "Robin"])
    )
    assert individual.pick_mksap_account(many, "Sample, Alex") == "Sample|Alex"
    assert individual.pick_mksap_account(many, "Other, Person") is None
    assert individual.pick_mksap_account(many, None) is None


@pytest.mark.parametrize("area,codes", [("Infectious Diseases", ["ID"]), ("High Value Care", [])])
def test_mksap_columns_from_own_export(area, codes):
    raw = mksap.load_mksap(demo.sample_mksap_csv())
    sec = mksap.by_section(raw)
    a = individual.analyze_examinee(demo.sample_examinee_reports()[-1], mksap_sections=sec)
    t = a["areas"].set_index("area")
    if codes:
        assert 0 <= t.loc[area, "mksap_pct_done"] <= 100
    else:
        assert area not in t.index  # HVC is reported separately
