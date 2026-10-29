import io

import pandas as pd
from reportlab.pdfgen import canvas

from ite_core import demo, names
from ite_core import detect as D


def _pdf(*lines) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i, line in enumerate(lines):
        c.drawString(72, 720 - 16 * i, line)
    c.save()
    return buf.getvalue()


def test_demo_files_are_recognized():
    d = demo.make_demo()
    for name, data in d["rosters"]:
        assert D.detect(name, data)[0] == D.ROSTER
    assert D.detect(*d["mksap"])[0] == D.MKSAP


def test_csv_kinds(roster_files, mksap_csv):
    for p in roster_files:
        assert D.detect(p.name, p.read_bytes())[0] == D.ROSTER
    assert D.detect("mk.csv", mksap_csv.read_bytes())[0] == D.MKSAP
    overview = pd.DataFrame(columns=["Last Name", "First Name", "Total Questions", "Number Complete", "Number Correct"])
    assert D.detect("overview.csv", overview.to_csv(index=False).encode())[0] == D.MKSAP
    cw = pd.DataFrame(columns=names.CROSSWALK_COLS).to_csv(index=False).encode()
    assert D.detect("crosswalk.csv", cw)[0] == D.CROSSWALK


def test_pdf_kinds():
    prog = _pdf("2026 INTERNAL MEDICINE IN-TRAINING EXAMINATION", "PROGRAM PERFORMANCE REPORT")
    assert D.detect("p.pdf", prog)[0] == D.PROGRAM
    exam = _pdf("2026 Internal Medicine In-Training Examination", "Examinee Performance Report", "Candidate ID: 1")
    assert D.detect("e.pdf", exam)[0] == D.EXAMINEE
    assert D.detect("x.pdf", _pdf("A grocery list"))[0] == D.UNKNOWN


def test_unknown_and_damaged():
    assert D.detect("notes.txt", b"hello") == (D.UNKNOWN, "is not a spreadsheet (.xlsx, .xls, .csv) or PDF")
    assert D.detect("broken.pdf", b"%PDF-garbage")[0] == D.UNKNOWN
    assert D.detect("other.csv", b"a,b,c\n1,2,3\n")[0] == D.UNKNOWN
    assert D.detect("broken.xlsx", b"not a zip")[0] == D.UNKNOWN


def test_sort_uploads_routes_each_file(roster_files, mksap_csv):
    from ite_core.session import Upload

    ups = [Upload(p.name, p.read_bytes()) for p in roster_files]
    ups += [
        Upload("mk.csv", mksap_csv.read_bytes()),
        Upload("p.pdf", _pdf("PROGRAM PERFORMANCE REPORT")),
        Upload("me.pdf", _pdf("Examinee Performance Report", "Candidate ID: 1")),
        Upload("notes.txt", b"x"),
    ]
    got = D.sort_uploads(ups)
    assert [u.name for u in got[D.ROSTER]] == [p.name for p in roster_files]
    assert got[D.MKSAP].name == "mk.csv" and got[D.PROGRAM].name == "p.pdf" and got[D.CROSSWALK] is None
    assert [n for n, _ in got["skipped"]] == ["me.pdf", "notes.txt"]
    assert "Resident report" in got["skipped"][0][1]


def test_program_report_with_cover_page():
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "About this report")
    c.showPage()
    c.drawString(72, 720, "PROGRAM PERFORMANCE REPORT")
    c.save()
    assert D.detect("p.pdf", buf.getvalue())[0] == D.PROGRAM


def test_abim_pdf_detected_and_routed():
    from ite_core.session import Upload

    pdf = _pdf("2026 INTERNAL MEDICINE CERTIFICATION EXAMINATION RESULTS", "Tester, Alex      Pass")
    assert D.detect("err.pdf", pdf)[0] == D.ABIM
    got = D.sort_uploads([Upload("err.pdf", pdf)])
    assert [u.name for u in got[D.ABIM]] == ["err.pdf"] and not got["skipped"]


def test_roster_with_title_rows_is_detected():
    data = b'ACP IM-ITE roster export,,,\n,,,\nCandidate ID,Name,PGY,Total Test Percent Correct\n1001,"Test, A",1,60\n'
    assert D.detect("2026 roster.csv", data)[0] == D.ROSTER
