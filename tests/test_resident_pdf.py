import io
import threading

import pypdf
import pytest

from ite_core import demo, pdf_reports
from ite_core import session as S
from modules import resident_pdf as RP
from modules import static_charts
from tests.conftest import examinee_pages


def _text(pdf: bytes) -> tuple[int, str]:
    r = pypdf.PdfReader(io.BytesIO(pdf))
    return len(r.pages), "\n".join(p.extract_text() or "" for p in r.pages)


@pytest.fixture(scope="module")
def roster_ds():
    d = demo.make_demo()
    r = S.load_rosters([S.Upload(n, b) for n, b in d["rosters"]])
    m = S.load_mksap(S.Upload(*d["mksap"]))
    cw = S.match(r, m)
    return S.Dataset(rosters=r, mksap=m, crosswalk=cw, wide=S.build_wide(r, m, cw))


def test_pdf_from_score_report():
    content = RP.from_examinee(demo.sample_examinee_reports())
    pdf = RP.resident_pdf(content)
    assert pdf.startswith(b"%PDF")
    pages, text = _text(pdf)
    assert 2 <= pages <= 4
    for s in (
        "Sample, Alex",
        "Board-pass estimate",
        "Low risk",
        "All missed objectives (11)",
        "Infectious Diseases",
        "Select antibiotics for an invented infection.",
        "(HVC)",
        "McDonald",
        "To be at 90% or higher next year (PGY-3)",
        "50th percentile and above",
    ):
        assert s in text, s
    assert RP.pdf_filename(content) == "ITE2026_Sample__Alex.pdf"


def test_pdf_from_roster_has_no_objectives(roster_ds):
    rid = roster_ds.wide[roster_ds.wide.PGY == 2].ID.iloc[0]
    _, text = _text(RP.resident_pdf(RP.from_roster(roster_ds, rid)))
    assert "Prepared by the residency program" in text
    assert "Missed objectives come from the resident's own ACP score report" in text
    assert "National mean" not in text


def test_roster_pdf_shows_mksap_when_linked(roster_ds):
    w = roster_ds.wide
    rid = w[w.mk_answered.notna() & (w.PGY == 3)].ID.iloc[0]
    _, text = _text(RP.resident_pdf(RP.from_roster(roster_ds, rid)))
    assert "MKSAP (program export)" in text


def test_single_year_pgy4_and_special_characters():
    (r,) = pdf_reports.parse_examinee_text(examinee_pages(name="O'Brien & <Test>, Zoë", pgy=4))
    pages, text = _text(RP.resident_pdf(RP.from_examinee([r])))
    assert pages >= 1 and "O'Brien & <Test>, Zoë" in text and "PGY-2 group" in text


def test_roster_without_area_percentiles(roster_ds):
    long = roster_ds.rosters.long.drop(columns=[c for c in roster_ds.rosters.long if c.startswith("ile_")])
    r = S.Rosters(long=long, files=roster_ds.rosters.files, current_year=2026)
    ds = S.Dataset(rosters=r, mksap=None, crosswalk=None, wide=S.build_wide(r, None, None))
    _, text = _text(RP.resident_pdf(RP.from_roster(ds, ds.wide.ID.iloc[0])))
    assert "not available from this roster" in text


def test_charts_are_thread_safe():
    """matplotlib object API only: concurrent visitors must not corrupt each other's charts."""
    a = demo.sample_examinee_reports()
    from ite_core import individual

    areas = individual.analyze_examinee(a[-1])["areas"]
    out, errors = [], []

    def work():
        try:
            out.append(static_charts.area_percentile_png(areas))
        except Exception as e:  # pragma: no cover - only on failure
            errors.append(e)

    threads = [threading.Thread(target=work) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(out) == 6 and all(png.startswith(b"\x89PNG") for png in out)


def test_pdf_with_program_report_ranks_questions():
    content = RP.from_examinee(demo.sample_examinee_reports(), program=demo.sample_resident_program_report())
    _, text = _text(RP.resident_pdf(content))
    assert "Biggest misses (11)" in text and "Notable wins (10)" in text and "got it right" in text
