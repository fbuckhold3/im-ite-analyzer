import re

import pandas as pd
import pytest

from ite_core import demo, pdf_reports
from ite_core import session as S
from modules import report_builder as R
from modules.items_tab import item_frame
from tests.conftest import program_pages


@pytest.fixture(scope="module")
def ds():
    d = demo.make_demo()
    r = S.load_rosters([S.Upload(n, b) for n, b in d["rosters"]])
    m = S.load_mksap(S.Upload(*d["mksap"]))
    cw = S.match(r, m)
    return S.Dataset(rosters=r, mksap=m, crosswalk=cw, wide=S.build_wide(r, m, cw)), d["people"]


@pytest.fixture(scope="module")
def program():
    return demo.sample_program_report()


# --- item helpers -----------------------------------------------------------------------------
def test_item_helpers():
    p = pdf_reports.parse_program_text(program_pages())
    s = pdf_reports.items_summary(p["items"])
    assert (s["n"], s["red"], s["yellow"]) == (3, 1, 1)
    assert pdf_reports.residents_per_group(p["areas"]) == {"1": 25, "2": 29, "3": 27, "A": 81}
    assert "Number of Residents" not in set(pdf_reports.area_ranks(p["areas"]).area)
    f = item_frame(p["items"])
    assert f.Flag.tolist() == ["red", "yellow", ""]  # flagged first
    assert f.HVC.tolist()[1] == "HVC"


def test_demo_program_report(program):
    s = pdf_reports.items_summary(program["items"])
    assert s["n"] > 30 and s["red"] > 0 and program["program_name"] == "DEMO INTERNAL MEDICINE PROGRAM"


# --- reports ----------------------------------------------------------------------------------
def test_sections(ds, program):
    data, _ = ds
    assert R.included_sections(data, program) == [
        "ABIM pass estimates",
        "ITE results over time",
        "Year over year",
        "MKSAP",
        "Item-level gaps",
    ]
    assert R.included_sections(None, program) == ["Item-level gaps"]
    assert R.included_sections(None, None) == []


def test_identified_report(ds, program):
    data, _ = ds
    html = R.build_report(data, program, deidentified=False).decode()
    assert html.startswith("<!doctype html>") and "Confidential" in html
    assert html.count("Plotly.newPlot") >= 6 and html.count("plotly.js v") == 1  # library embedded once
    assert "Watch list" in html


def test_deidentified_report_has_no_names_or_ids(ds, program):
    data, people = ds
    html = R.build_report(data, program, deidentified=True).decode()
    assert "De-identified" in html and "Watch list" not in html
    content = R.content_without_library(html)
    for _, p in people.iterrows():
        assert not re.search(rf"\b{re.escape(p['last'])}\b", content, re.I), "resident surname leaked"
        assert not re.search(rf"\b{re.escape(p['first'])}\b", content), "resident first name leaked"
        assert str(p.ID) not in content, "candidate ID leaked"


def test_small_groups_suppressed(ds):
    data, _ = ds
    long = data.rosters.long
    keep = long[(long.PGY != 1) | (long.ID.isin(long[long.PGY == 1].ID.unique()[:3]))]  # 3 interns per year
    r = S.Rosters(long=keep, files=data.rosters.files, current_year=data.rosters.current_year)
    small = S.Dataset(rosters=r, mksap=None, crosswalk=None, wide=S.build_wide(r, None, None))
    html = R.build_report(small, None, deidentified=True).decode()
    assert "&lt;5" in html or "<5" in html
    ident = R.build_report(small, None, deidentified=False).decode()
    assert "(n=3)" in ident  # the identified report keeps exact small counts


def test_sup_count():
    assert [R.sup_count(k) for k in (0, 1, 4, 5, 12)] == ["0", "<5", "<5", "5", "12"]


def test_report_without_rosters(program):
    html = R.build_report(None, program, deidentified=True).decode()
    assert "Item-level gaps" in html and "Estimated ABIM pass probability" not in html


def test_frames_are_not_mutated(ds, program):
    data, _ = ds
    before = data.wide.copy()
    R.build_report(data, program, deidentified=True)
    pd.testing.assert_frame_equal(before, data.wide)


def test_deidentified_tiers_cannot_be_recovered_by_subtraction(ds):
    """Group sizes are public in the report, so suppressed tier counts must not be solvable."""
    data, _ = ds
    html = R.content_without_library(R.build_report(data, None, deidentified=True).decode())
    assert "Intermediate risk</th>" not in html and "Below Low risk" in html
    assert "≥" in html  # Low risk shown as a range wherever Below Low risk is suppressed
    assert "improved" not in html or "omitted" in html


def test_report_summary_tiles_and_takeaways(ds, program):
    data, _ = ds
    html = R.content_without_library(R.build_report(data, program, deidentified=False).decode())
    for s in ("Residents tested", "PGY-2/3 in Low risk", "On the watch list", "Red-flag items", 'class="takeaway"'):
        assert s in html, s
    assert 'class="tierbar"' in html and "badge b-Low" in html


def test_deidentified_tiles_respect_suppression(ds, program):
    data, _ = ds
    html = R.content_without_library(R.build_report(data, program, deidentified=True).decode())
    assert "On the watch list" not in html and "tierbar" not in html.split("</style>")[1]
    assert "PGY-2/3 below Low risk" in html


def test_projected_pass_rate_in_reports(ds):
    data, _ = ds
    ident = R.content_without_library(R.build_report(data, None, deidentified=False).decode())
    deid = R.content_without_library(R.build_report(data, None, deidentified=True).decode())
    assert "Projected ABIM pass rate" in ident and "likely" in ident
    assert "Projected ABIM pass rate" in deid and "pass</div>" not in deid  # no "likely a–b pass" range


def test_projected_pass_rate_suppressed_for_small_classes(ds):
    data, _ = ds
    long = data.rosters.long
    cy = data.rosters.current_year
    interns = long[(long.PGY == 1) & (long.Exam_Year == cy)].ID.unique()
    keep = long[~long.ID.isin(interns[3:])]  # 3 current interns
    r = S.Rosters(long=keep, files=data.rosters.files, current_year=data.rosters.current_year)
    small = S.Dataset(rosters=r, mksap=None, crosswalk=None, wide=S.build_wide(r, None, None))
    html = R.content_without_library(R.build_report(small, None, deidentified=True).decode())
    assert "fewer than 5 residents" in html
