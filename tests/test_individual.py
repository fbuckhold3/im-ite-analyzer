import pandas as pd

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
    # bands: 50th+ / 25th-49th / below 25th (by national percentile)
    assert a["strengths"] == ["General Internal Medicine", "Rheumatology", "Gastroenterology", "Geriatric Medicine"]
    assert set(a["focus_areas"]) == {"Infectious Diseases", "Endocrinology"}
    assert a["missed"].hvc.sum() == 2 and a["pgy_note"] is None
    assert a["pct_needed_low_next"] == 65.1


def test_pgy4_note():
    (r,) = pdf_reports.parse_examinee_text(examinee_pages(pgy=4))
    a = individual.analyze_examinee(r)
    assert "PGY-2 group" in a["pgy_note"] and a["pct_needed_low_next"] is None


def test_pick_mksap_account():
    one = pd.DataFrame(dict(mk_key=["Sample|Alex"], mk_last=["Sample"], mk_first=["Alex"]))
    assert individual.pick_mksap_account(one, "Anything, At All") == "Sample|Alex"  # single account: use it
    many = pd.DataFrame(
        dict(mk_key=["Sample|Alex", "Sample|Robin"], mk_last=["Sample"] * 2, mk_first=["Alex", "Robin"])
    )
    assert individual.pick_mksap_account(many, "Sample, Alex") == "Sample|Alex"
    assert individual.pick_mksap_account(many, "Other, Person") is None
    assert individual.pick_mksap_account(many, None) is None


def test_mksap_columns_from_program_sections():
    """The program MKSAP export can still be joined to one resident's ITE areas (e.g. for a PD drill-down)."""
    d = demo.make_demo()
    sections = mksap.by_section(mksap.load_mksap(d["mksap"][1]))
    key = sections.mk_key.iloc[0]
    a = individual.analyze_examinee(demo.sample_examinee_reports()[-1], mksap_sections=sections[sections.mk_key == key])
    t = a["areas"].set_index("area")
    assert 0 <= t.loc["Infectious Diseases", "mksap_pct_done"] <= 100
    assert "High Value Care" not in t.index


def test_next_year_targets_and_wording():
    assert individual.next_year_targets(1) == [(2, 59.7), (3, 65.1)]
    assert individual.next_year_targets(2) == [(3, 65.1)]
    assert individual.next_year_targets(3) == []
    assert individual.target_gap_phrase(56, 59.7) == "3.7 points more than this year's 56%"
    assert individual.target_gap_phrase(67, 65.1) == "you're already 1.9 points above it"


def test_rank_questions_against_program_report():
    rep = demo.sample_examinee_reports()[-1]
    q = individual.rank_questions(rep, demo.sample_resident_program_report())
    assert q["matched"] == q["missed_total"] == 11 and q["pgy_label"] == "PGY-2"
    assert list(q["misses"].national) == sorted(q["misses"].national, reverse=True)  # most-national-correct first
    assert list(q["wins"].national) == sorted(q["wins"].national) and len(q["wins"]) == 10
    missed = set(rep["missed"].objective)
    assert set(q["misses"].objective) <= missed and not (set(q["wins"].objective) & missed)


def test_rank_questions_needs_same_exam_year():
    rep = dict(demo.sample_examinee_reports()[-1], exam_year=2025)
    assert individual.rank_questions(rep, demo.sample_resident_program_report()) is None
