import re

import pytest

from ite_core import abim, demo
from ite_core import session as S
from ite_core.nomogram import DEFAULT_CUTOFFS
from modules import report_builder as R

RESULTS = [
    "2026 INTERNAL MEDICINE CERTIFICATION EXAMINATION RESULTS\n"
    "CANDIDATE NAME                                            EXAM RESULT\n"
    "Tester, Alex                                                     Pass\n"
    "Van der Berg, Sam                                                Fail\n"
    "Lee-Park, Jordan Q                                               Pass\n"
]
PROGRAM_DATA = [
    "2025 OVERALL PROGRAM PERFORMANCE FOR INTERNAL MEDICINE\nCandidates Across\nAll Programs: 87%\n"
    "Candidates From\nYour Program: 67%\n",
    "2025 INTERNAL MEDICINE CERTIFICATION EXAMINATION RESULTS\n"
    "CANDIDATE NAME                          EXAM RESULT          STANDARDIZED SCORE\n"
    "Tester, Alex                                  Pass                       458\n"
    "Sample, Pat                                   Fail           Withheld by Candidate\n"
    "Example, Kim                                  Pass            Withheld by Candidate\n",
    "Note: The passing score for this exam is 371.\n",
]


def test_parse_results_report():
    r = abim.parse_abim_text(RESULTS, "r.pdf")
    c = r["candidates"]
    assert r["exam_year"] == 2026 and r["kind"] == "results"
    assert c.name.tolist() == ["Tester, Alex", "Van der Berg, Sam", "Lee-Park, Jordan Q"]
    assert c.passed.tolist() == [True, False, True] and c["last"].iloc[1] == "Van der Berg"
    assert c.score.isna().all() and not c.withheld.any()


def test_parse_program_data_report():
    r = abim.parse_abim_text(PROGRAM_DATA, "p.pdf")
    c = r["candidates"]
    assert (r["exam_year"], r["kind"], r["program_rate"], r["all_rate"], r["passing_score"]) == (
        2025,
        "program_data",
        67,
        87,
        371,
    )
    assert c.score.iloc[0] == 458 and c.withheld.tolist() == [False, True, True]


def test_not_abim():
    with pytest.raises(abim.UploadError):
        abim.parse_abim_text(["2026 INTERNAL MEDICINE IN-TRAINING EXAMINATION\nPROGRAM PERFORMANCE REPORT"])


def test_combine_prefers_program_data_for_same_year():
    a = abim.parse_abim_text([RESULTS[0].replace("2026", "2025")], "a.pdf")
    b = abim.parse_abim_text(PROGRAM_DATA, "b.pdf")
    cands, years = abim.combine([a, b])
    assert years.kind.tolist() == ["program_data"] and len(cands) == 3


@pytest.fixture(scope="module")
def demo_outcomes():
    d = demo.make_demo()
    r = S.load_rosters([S.Upload(n, b) for n, b in d["rosters"]])
    m = S.load_mksap(S.Upload(*d["mksap"]))
    cands, years = abim.combine(demo.sample_abim_reports())
    links = abim.link(cands, r.long)
    return cands, years, r.long, links, m.people, d["people"]


def test_link_and_outcomes(demo_outcomes):
    cands, years, long, links, people, _ = demo_outcomes
    assert (links.tier == "Unmatched").sum() == 2  # the deliberately renamed taker in each year
    t = abim.outcome_table(cands, links, long, people)
    assert t.predicted.notna().sum() == len(t) - 2
    assert set(t.ite_pgy.dropna()) == {3}
    s = abim.year_summary(t, years)
    assert s.takers.tolist() == [10, 10] and (s.linked == 9).all()
    assert s.observed.tolist() == [p / n for p, n in zip(s.passes, s.takers, strict=True)]
    tiers = abim.by_predicted_tier(t, DEFAULT_CUTOFFS)
    assert tiers.n.sum() == t.predicted.notna().sum()


def test_manual_link_moves_resident(demo_outcomes):
    cands, _, long, links, _, _ = demo_outcomes
    open_key = links[links.ID.isna()].key.iloc[0]
    taken = links.dropna(subset=["ID"]).iloc[0]
    out = abim.apply_links(links, {open_key: taken.ID})
    assert out.set_index("key").loc[open_key, "ID"] == taken.ID
    assert out.set_index("key").loc[taken.key, "tier"] == "Unmatched"  # no resident linked twice
    out = abim.apply_links(links, {open_key: None})
    assert out.set_index("key").loc[open_key, "tier"] == "Not ours"


def _outcomes_dict(demo_outcomes):
    cands, years, long, links, people, _ = demo_outcomes
    t = abim.outcome_table(cands, links, long, people)
    return dict(
        table=t,
        summary=abim.year_summary(t, years),
        tiers=abim.by_predicted_tier(t, DEFAULT_CUTOFFS),
        years=years,
    )


def test_outcomes_in_pd_report_without_names(demo_outcomes):
    d = demo.make_demo()
    r = S.load_rosters([S.Upload(n, b) for n, b in d["rosters"]])
    ds = S.Dataset(rosters=r, mksap=None, crosswalk=None, wide=S.build_wide(r, None, None))
    o = _outcomes_dict(demo_outcomes)
    html = R.content_without_library(R.build_report(ds, None, deidentified=False, outcomes=o).decode())
    assert "Board outcomes" in html
    section = html[html.index('id="outcomes"') : html.index('id="methods"')]
    for _, p in demo_outcomes[5].iterrows():
        assert not re.search(rf"\b{re.escape(p['last'])}\b", section), "name in the outcomes section"
    deid = R.content_without_library(R.build_report(ds, None, deidentified=True, outcomes=o).decode())
    assert "Board outcomes" not in deid and "ABIM result" not in deid
    assert "Board outcomes (PD report only)" in R.included_sections(ds, None, o)


def test_probable_link_waits_for_confirmation():
    import pandas as pd

    long = pd.DataFrame(
        dict(
            ID=["1", "2"],
            Name=["Lee-Park, Jordan", "Tester, Alex"],
            PGY=[3, 3],
            Exam_Year=[2025, 2025],
            Grad_Class=[2026, 2026],
            Pct_Correct=[70.0, 64.0],
            Percentile=[60.0, 30.0],
            Pass_Prob=[0.96, 0.85],
        )
    )
    r = abim.parse_abim_text(
        [
            "2026 INTERNAL MEDICINE CERTIFICATION EXAMINATION RESULTS\n"
            "Park, Jordan                                   Pass\n"
            "Tester, Alex                                   Pass\n"
        ],
        "r.pdf",
    )
    links = abim.link(r["candidates"], long).set_index("key")
    sugg = links.loc["2026|Park, Jordan"]
    assert sugg.tier == "Probable" and pd.isna(sugg.ID) and sugg.suggested == "1"
    assert links.loc["2026|Tester, Alex", "ID"] == "2"
    t = abim.outcome_table(r["candidates"], links.reset_index(), long)
    assert t.predicted.notna().sum() == 1  # the suggestion is not counted yet
    confirmed = abim.apply_links(links.reset_index(), {"2026|Park, Jordan": "1"})
    t = abim.outcome_table(r["candidates"], confirmed, long)
    assert t.predicted.notna().sum() == 2
