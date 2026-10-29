import io

import pandas as pd
import pytest

from ite_core import demo, limits, names, pdf_reports, roster
from ite_core import session as S
from ite_core.limits import UploadError


@pytest.fixture(scope="module")
def demo_files():
    return demo.make_demo()


@pytest.fixture(scope="module")
def loaded(demo_files):
    r = S.load_rosters([S.Upload(n, b) for n, b in demo_files["rosters"]])
    mk = S.load_mksap(S.Upload(*demo_files["mksap"]))
    return r, mk


def test_demo_end_to_end(loaded):
    r, mk = loaded
    assert (r.files.status == "ok").all() and r.current_year == 2026
    cw = S.match(r, mk)
    assert len(cw) == 30
    assert cw.tier.value_counts().to_dict() == {"Exact": 28, "Probable": 1, "Unmatched": 1}  # nickname; no account
    assert len(names.unmatched_mksap(cw, mk.people)) == 2  # the two graduates
    w = S.build_wide(r, mk, cw)
    assert len(w) == 30 and w.mk_answered.notna().sum() == 28  # the Probable match waits for review
    w = S.build_wide(r, mk, names.confirm_tier(cw, "Probable"))
    assert w.mk_answered.notna().sum() == 29  # counted once confirmed


def test_one_bad_file_does_not_stop_the_rest(demo_files):
    ups = [S.Upload(n, b) for n, b in demo_files["rosters"]]
    ups.append(S.Upload("notes_2023.xlsx", b"not really a spreadsheet"))
    ups.append(S.Upload("roster.docx", b"x"))
    ups.append(S.Upload(ups[0].name.replace("2024", "copy 2024"), ups[0].data))  # same year twice
    r = S.load_rosters(ups)
    st = r.files.set_index("file").status
    assert (st == "ok").sum() == 3 and (st == "error").sum() == 3
    msgs = " ".join(r.files.message)
    assert "could not be read" in msgs and "not a roster file" in msgs and "already loaded" in msgs
    assert r.current_year == 2026


def test_year_override(demo_files):
    name, data = demo_files["rosters"][-1]
    r = S.load_rosters([S.Upload("roster.xlsx", data)])
    assert r.files.status.iloc[0] == "error" and "please enter it" in r.files.message.iloc[0]
    r = S.load_rosters([S.Upload("roster.xlsx", data, year=2026)])
    assert r.files.status.iloc[0] == "ok" and r.current_year == 2026


def test_size_and_type_limits(monkeypatch):
    with pytest.raises(UploadError, match="not a MKSAP CSV file"):
        S.load_mksap(S.Upload("mksap.xlsx", b"x"))
    monkeypatch.setattr(limits, "MAX_FILE_MB", 0.000001)
    with pytest.raises(UploadError, match="limit is"):
        S.load_mksap(S.Upload("mksap.csv", b"a,b\n1,2\n"))


def test_too_many_rows(monkeypatch):
    monkeypatch.setattr(roster, "MAX_ROSTER_ROWS", 3)
    df = pd.DataFrame(dict(ID=range(5), Name="A, B", PGY=1, Total_Test_Percent_Correct=60))
    with pytest.raises(UploadError, match="more than 3 rows"):
        roster.read_table(df.to_csv(index=False).encode(), "r_2026.csv")


def test_error_messages_never_echo_contents():
    secret = b"Doe, Jane,1234,secret-score"
    with pytest.raises(UploadError) as e:
        roster.load_roster(secret)  # no filename given
    assert "Doe" not in str(e.value) and "secret" not in str(e.value)


def test_bad_pdf_is_friendly():
    with pytest.raises(UploadError, match="could not be read as a PDF"):
        pdf_reports.parse_examinee_pdf(b"%PDF-1.4 garbage", name="report.pdf")


def test_crosswalk_reupload_restores_overrides(loaded):
    r, mk = loaded
    cw = S.match(r, mk)
    unmatched = cw[cw.tier == "Unmatched"].acp_id.iloc[0]
    grad = names.unmatched_mksap(cw, mk.people).mk_key.iloc[0]
    cw = names.set_match(cw, unmatched, grad, mk.people)  # user links a resident by hand
    cw = names.confirm_tier(cw, "Probable")
    prior = S.read_crosswalk(S.Upload("crosswalk.csv", S.crosswalk_csv(cw)))
    again = S.match(r, mk, prior).set_index("acp_id")
    assert again.loc[unmatched, "mksap_key"] == grad and again.loc[unmatched, "confirmed_by_user"]
    assert again.loc[unmatched, "tier"] == "Manual"
    assert again[again.tier == "Probable"].confirmed_by_user.all()


def test_bad_crosswalk():
    with pytest.raises(UploadError, match="Not a crosswalk"):
        S.read_crosswalk(S.Upload("cw.csv", pd.DataFrame(dict(a=[1])).to_csv(index=False).encode()))


def test_confirm_tier_only_touches_that_tier(loaded):
    r, mk = loaded
    cw = names.confirm_tier(S.match(r, mk), "Probable")
    assert cw[cw.tier == "Probable"].confirmed_by_user.all()
    assert not cw[cw.tier == "Exact"].confirmed_by_user.any()


def test_demo_is_deterministic():
    a, b = demo.make_demo(), demo.make_demo()
    assert a["rosters"][0][1] == b["rosters"][0][1] or pd.read_excel(io.BytesIO(a["rosters"][0][1])).equals(
        pd.read_excel(io.BytesIO(b["rosters"][0][1]))
    )
