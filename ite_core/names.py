"""Name normalisation and ITE <-> MKSAP identity matching.

ITE <-> ITE across years uses the ACP Candidate ID (stable). MKSAP has names only, so:
  1. candidate = exact normalised last name AND first-name agreement (same initial or a
     known nickname pair). Never accept a surname-only match — that is how
     "Smith, P." was once merged into "Smith, R.".
  2. fallback for compound / hyphenated surnames: any shared last-name token + first agreement.
  3. several candidates -> keep those whose first token is identical; else Ambiguous.
  4. an MKSAP account proposed for two ITE residents -> both Ambiguous.
Tiers: Exact (last + first token identical), Probable, Ambiguous, Unmatched.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

TIERS = ["Exact", "Probable", "Ambiguous", "Unmatched", "Manual"]  # Manual = linked by the user
CROSSWALK_COLS = [
    "acp_id",
    "ite_name",
    "mksap_key",
    "mksap_last",
    "mksap_first",
    "tier",
    "n_candidates",
    "confirmed_by_user",
]

_NICK_GROUPS = [
    {"thomas", "tom", "tommy"},
    {"katherine", "kate", "katie", "kathryn", "catherine", "cate"},
    {"william", "will", "bill", "billy", "liam"},
    {"robert", "rob", "bob", "bobby"},
    {"richard", "rick", "rich", "dick"},
    {"elizabeth", "liz", "beth", "eliza", "betsy"},
    {"james", "jim", "jimmy", "jamie"},
    {"michael", "mike", "mick"},
    {"joseph", "joe", "joey"},
    {"jonathan", "jon", "john", "johnny", "jack"},
    {"margaret", "maggie", "meg", "peggy"},
    {"alexander", "alex", "xander", "sasha"},
    {"alexandra", "alex", "sasha", "lexi"},
    {"christopher", "chris", "topher"},
    {"christina", "christine", "chris", "tina"},
    {"daniel", "dan", "danny"},
    {"david", "dave"},
    {"edward", "ed", "eddie", "ted"},
    {"jennifer", "jen", "jenny"},
    {"matthew", "matt"},
    {"nicholas", "nick", "nico"},
    {"patricia", "pat", "patty", "trish"},
    {"patrick", "pat"},
    {"samuel", "sam"},
    {"samantha", "sam"},
    {"steven", "stephen", "steve"},
    {"susan", "sue", "susie"},
    {"victoria", "vicky", "tori"},
    {"anthony", "tony"},
    {"benjamin", "ben"},
    {"andrew", "andy", "drew"},
    {"abigail", "abby"},
    {"rebecca", "becca", "becky"},
    {"zachary", "zach", "zack"},
    {"gregory", "greg"},
    {"timothy", "tim"},
    {"kenneth", "ken"},
    {"jessica", "jess"},
    {"mohammed", "mohammad", "muhammad", "mohamed"},
]
NICKNAMES: dict[str, set[str]] = {}
for _g in _NICK_GROUPS:
    for _n in _g:
        NICKNAMES.setdefault(_n, set()).update(_g - {_n})


def norm_tokens(s) -> list[str]:
    """NFKD -> ASCII, lowercase, punctuation/hyphens to spaces, split."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return []
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", " ", s).split()


def split_ite_name(name) -> tuple[list[str], list[str]]:
    """'Last, First Middle' -> (last tokens, first tokens). Also accepts 'First Last'."""
    name = "" if name is None else str(name)
    if "," in name:
        last, first = name.split(",", 1)
    else:
        parts = name.split()
        first, last = (parts[0] if parts else ""), " ".join(parts[1:])
    return norm_tokens(last), norm_tokens(first)


def first_agrees(a: list[str], b: list[str]) -> str | None:
    """'exact' (same first token), 'initial', 'nickname', or None."""
    if not a or not b:
        return None
    if a[0] == b[0]:
        return "exact"
    if a[0][0] == b[0][0]:
        return "initial"
    if b[0] in NICKNAMES.get(a[0], ()):
        return "nickname"
    return None


def match_mksap(ite: pd.DataFrame, mksap_people: pd.DataFrame) -> pd.DataFrame:
    """Propose an MKSAP account for each ITE resident.

    ite: one row per resident with ID, Name (ACP 'Last, First').
    mksap_people: mksap.per_person() output (mk_key, mk_last, mk_first).
    Returns the crosswalk (CROSSWALK_COLS), one row per ITE resident.
    """
    mk = mksap_people[["mk_key", "mk_last", "mk_first"]].copy()
    mk["last_t"] = mk.mk_last.map(norm_tokens)
    mk["first_t"] = mk.mk_first.map(norm_tokens)

    proposals = []
    for _, r in ite[["ID", "Name"]].drop_duplicates("ID").iterrows():
        lt, ft = split_ite_name(r.Name)
        agree = mk["first_t"].map(lambda x, ft=ft: first_agrees(ft, x))
        exact_last = mk["last_t"].map(lambda x, lt=lt: x == lt)
        cand = mk[exact_last & agree.notna()]
        how_last = "exact"
        if cand.empty:  # compound / hyphenated surnames
            overlap = mk["last_t"].map(lambda x, lt=lt: bool(set(x) & set(lt)))
            cand = mk[overlap & agree.notna()]
            how_last = "token"
        n_cand = len(cand)
        if len(cand) > 1:
            same_first = cand[agree.loc[cand.index].eq("exact")]
            if len(same_first) >= 1:
                cand = same_first
        if len(cand) == 1:
            c = cand.iloc[0]
            tier = "Exact" if how_last == "exact" and agree.loc[cand.index[0]] == "exact" else "Probable"
            proposals.append(
                dict(
                    acp_id=r.ID,
                    ite_name=r.Name,
                    mksap_key=c.mk_key,
                    mksap_last=c.mk_last,
                    mksap_first=c.mk_first,
                    tier=tier,
                    n_candidates=n_cand,
                )
            )
        else:
            proposals.append(
                dict(
                    acp_id=r.ID,
                    ite_name=r.Name,
                    mksap_key=None,
                    mksap_last=None,
                    mksap_first=None,
                    tier="Ambiguous" if len(cand) > 1 else "Unmatched",
                    n_candidates=n_cand,
                )
            )
    cw = pd.DataFrame(proposals, columns=CROSSWALK_COLS[:-1])
    # one MKSAP account may not be claimed by two residents
    claimed = cw.mksap_key.notna() & cw.mksap_key.duplicated(keep=False)
    cw.loc[claimed, "tier"] = "Ambiguous"
    cw.loc[claimed, ["mksap_key", "mksap_last", "mksap_first"]] = None
    cw["confirmed_by_user"] = False
    return cw


def unmatched_mksap(crosswalk: pd.DataFrame, mksap_people: pd.DataFrame) -> pd.DataFrame:
    """MKSAP accounts not linked to any ITE resident (expected: graduates, faculty, others)."""
    used = set(crosswalk.mksap_key.dropna())
    return mksap_people[~mksap_people.mk_key.isin(used)].reset_index(drop=True)


def set_match(crosswalk: pd.DataFrame, acp_id: str, mksap_key: str | None, mksap_people: pd.DataFrame) -> pd.DataFrame:
    """User override: link a resident to an MKSAP account, or None for 'no MKSAP account'."""
    cw = crosswalk.copy()
    i = cw.index[cw.acp_id == acp_id]
    if len(i) != 1:
        raise KeyError(f"Unknown ACP ID {acp_id}")
    if mksap_key is None:
        cw.loc[i, ["mksap_key", "mksap_last", "mksap_first"]] = None
        cw.loc[i, "tier"] = "Unmatched"
    else:
        hit = mksap_people[mksap_people.mk_key == mksap_key]
        if hit.empty:
            raise KeyError(f"Unknown MKSAP account {mksap_key}")
        other = cw.index[(cw.mksap_key == mksap_key) & (cw.acp_id != acp_id)]
        if len(other):
            raise ValueError(f"MKSAP account already linked to {cw.loc[other[0], 'ite_name']}")
        cw.loc[i, ["mksap_key", "mksap_last", "mksap_first"]] = [mksap_key, hit.mk_last.iloc[0], hit.mk_first.iloc[0]]
        if cw.loc[i[0], "tier"] in ("Ambiguous", "Unmatched"):
            cw.loc[i, "tier"] = "Manual"  # keep Exact/Probable if the user re-selected the proposed account
    cw.loc[i, "confirmed_by_user"] = True
    return cw


def read_crosswalk(source) -> pd.DataFrame:
    """Re-load a crosswalk exported from an earlier session."""
    cw = pd.read_csv(source, dtype=str)
    missing = set(CROSSWALK_COLS) - set(cw.columns)
    if missing:
        raise ValueError(f"Not a crosswalk file — missing column(s): {', '.join(sorted(missing))}")
    cw["confirmed_by_user"] = cw.confirmed_by_user.str.lower().eq("true")
    cw["n_candidates"] = pd.to_numeric(cw.n_candidates, errors="coerce")
    return cw[CROSSWALK_COLS].astype(object).where(cw[CROSSWALK_COLS].notna(), None)


def confirm_tier(crosswalk: pd.DataFrame, tier: str) -> pd.DataFrame:
    """Mark every proposal of one tier (e.g. 'Probable') as reviewed and accepted by the user."""
    cw = crosswalk.copy()
    cw.loc[(cw.tier == tier) & cw.mksap_key.notna(), "confirmed_by_user"] = True
    return cw


def reassign(crosswalk: pd.DataFrame, acp_id: str, mksap_key: str | None, mksap_people: pd.DataFrame) -> pd.DataFrame:
    """Like set_match, but if the account already belongs to another resident, take it from them (their row goes
    back to Unmatched and unreviewed). The person reviewing decides; they see the other row change."""
    cw = crosswalk.copy()
    if mksap_key is not None:
        other = cw.index[(cw.mksap_key == mksap_key) & (cw.acp_id != acp_id)]
        if len(other):
            cw.loc[other, ["mksap_key", "mksap_last", "mksap_first"]] = None
            cw.loc[other, "tier"] = "Unmatched"
            cw.loc[other, "confirmed_by_user"] = False
    return set_match(cw, acp_id, mksap_key, mksap_people)


def candidate_accounts(crosswalk: pd.DataFrame, mksap_people: pd.DataFrame, acp_id: str) -> pd.DataFrame:
    """MKSAP accounts to offer for one resident, most likely first: same surname token, then same first initial,
    then the rest; accounts already linked to someone else come last (choosing one moves it)."""
    row = crosswalk[crosswalk.acp_id == acp_id].iloc[0]
    lt, ft = split_ite_name(row.ite_name)
    ppl = mksap_people[["mk_key", "mk_last", "mk_first"]].copy()
    owners = crosswalk.dropna(subset=["mksap_key"]).set_index("mksap_key").ite_name
    ppl["linked_to"] = ppl.mk_key.map(owners)
    ppl.loc[ppl.mk_key == row.mksap_key, "linked_to"] = None
    surname = ppl.mk_last.map(lambda x: bool(set(norm_tokens(x)) & set(lt)))
    initial = ppl.mk_first.map(lambda x: bool(ft) and first_agrees(ft, norm_tokens(x)) is not None)
    ppl["score"] = surname * 2 + initial * 1 - ppl.linked_to.notna() * 4
    return ppl.sort_values(["score", "mk_last", "mk_first"], ascending=[False, True, True]).reset_index(drop=True)
