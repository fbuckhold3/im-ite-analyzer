import pandas as pd
import pytest

from ite_core import history, mksap, names, roster


@pytest.fixture
def people(mksap_csv):
    return mksap.per_person(mksap.load_mksap(mksap_csv))


@pytest.fixture
def ite(roster_files):
    d, _ = roster.load_roster(roster_files[2])
    return d


def test_norm_tokens():
    assert names.norm_tokens("Abi-Karam") == ["abi", "karam"]
    assert names.norm_tokens("  AL MATNI ") == ["al", "matni"]
    assert names.norm_tokens("José") == ["jose"]
    assert names.split_ite_name("Garcia, Maria Elena") == (["garcia"], ["maria", "elena"])


def test_mksap_counts_rows_not_question_numbers(people):
    assert (people.mk_bank == 12).all()  # 3 sections x 4 rows, numbers repeat
    maria = people.set_index("mk_first").loc["Maria"]
    assert maria.mk_answered == 0 and pd.isna(maria.mk_pct_correct)


def test_mksap_bad_file(tmp_path):
    p = tmp_path / "x.csv"
    pd.DataFrame({"Last Name": ["a"]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="MKSAP"):
        mksap.load_mksap(p)


def test_matching_tiers(ite, people):
    cw = names.match_mksap(ite, people).set_index("acp_id")
    assert cw.loc["1001", "mksap_first"] == "Paula" and cw.loc["1001", "tier"] == "Exact"  # not Priya
    assert cw.loc["1002", "mksap_first"] == "Rob" and cw.loc["1002", "tier"] == "Probable"  # initial only
    assert cw.loc["1003", "mksap_last"] == "Abi Karam" and cw.loc["1003", "tier"] == "Exact"
    assert cw.loc["1004", "mksap_last"] == "NGUYEN" and cw.loc["1004", "tier"] == "Probable"
    assert cw.loc["1005", "tier"] == "Unmatched"
    assert cw.loc["1006", "mksap_first"] == "Maria" and cw.loc["1006", "tier"] == "Exact"
    assert not cw.confirmed_by_user.any()
    left = set(names.unmatched_mksap(cw.reset_index(), people).mk_first)
    assert left == {"Priya", "Jordan"}


def test_surname_alone_is_never_enough():
    ite = pd.DataFrame(dict(ID=["1"], Name=["Smith, Paula"]))
    ppl = pd.DataFrame(dict(mk_key=["Smith|Robert"], mk_last=["Smith"], mk_first=["Robert"]))
    assert names.match_mksap(ite, ppl).tier.iloc[0] == "Unmatched"


def test_compound_surname_token_fallback():
    ite = pd.DataFrame(dict(ID=["1"], Name=["Garcia-Lopez, Ana"]))
    ppl = pd.DataFrame(dict(mk_key=["Lopez|Ana"], mk_last=["Lopez"], mk_first=["Ana"]))
    assert names.match_mksap(ite, ppl).tier.iloc[0] == "Probable"


def test_ambiguous_and_double_claim():
    ppl = pd.DataFrame(dict(mk_key=["Kim|J", "Kim|Jo"], mk_last=["Kim", "Kim"], mk_first=["J", "Jo"]))
    one = names.match_mksap(pd.DataFrame(dict(ID=["1"], Name=["Kim, Jae"])), ppl)
    assert one.tier.iloc[0] == "Ambiguous" and one.n_candidates.iloc[0] == 2
    ppl1 = ppl.iloc[:1]
    two = names.match_mksap(pd.DataFrame(dict(ID=["1", "2"], Name=["Kim, Jae", "Kim, Jin"])), ppl1)
    assert (two.tier == "Ambiguous").all() and two.mksap_key.isna().all()


def test_override_and_crosswalk_roundtrip(ite, people, tmp_path):
    cw = names.match_mksap(ite, people)
    cw = names.set_match(cw, "1005", "Lee|Jordan", people)
    with pytest.raises(ValueError, match="already linked"):
        names.set_match(cw, "1001", "Lee|Jordan", people)
    cw = names.set_match(cw, "1002", None, people)
    p = tmp_path / "crosswalk.csv"
    cw.to_csv(p, index=False)
    back = names.read_crosswalk(p).set_index("acp_id")
    assert back.loc["1005", "mksap_key"] == "Lee|Jordan" and back.loc["1005", "confirmed_by_user"]
    assert back.loc["1002", "mksap_key"] is None and back.loc["1002", "tier"] == "Unmatched"


def test_attach_mksap(roster_files, people):
    long, _ = roster.load_rosters(roster_files)
    long = history.add_derived(long)
    w = history.wide(long)
    cw = names.match_mksap(long[long.Exam_Year == 2026], people)
    w2 = history.attach_mksap(w, cw, people).set_index("ID")
    assert w2.loc["1003", "mk_bank"] == 12 and pd.isna(w2.loc["1005", "mk_answered"])
    assert len(w2) == len(w)
