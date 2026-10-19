"""Synthetic demo program — invented people, invented scores. Lets anyone try the app without real files.

Files are produced in the same formats ACP and MKSAP export, so they travel the normal upload path.
Deliberate edge cases: a hyphenated surname, an all-caps MKSAP name, a nickname, a resident with no
MKSAP account, and MKSAP accounts belonging to graduates.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
from scipy.stats import norm

from .mksap import SECTION_NAMES
from .roster import AREAS

EXAM_YEARS = (2024, 2025, 2026)
NATIONAL_MEAN = {1: 60, 2: 67, 3: 70}  # approximate national PGY means (2026 ACP histograms)
PER_CLASS = 10

_FIRST = [
    "Avery",
    "Jordan",
    "Riley",
    "Casey",
    "Morgan",
    "Quinn",
    "Rowan",
    "Skyler",
    "Emerson",
    "Finley",
    "Harper",
    "Reese",
    "Sawyer",
    "Parker",
    "Dakota",
    "Hayden",
    "Elliot",
    "Marlowe",
    "Sage",
    "Tatum",
    "Blair",
    "Shiloh",
    "Arden",
    "Lennox",
    "Remy",
    "Oakley",
    "Ellis",
    "Kendall",
    "Peyton",
    "Jules",
    "Thomas",
    "Marin",
    "Briar",
    "Corin",
    "Darcy",
    "Lane",
    "Noel",
    "Wren",
    "Zion",
    "Indy",
]
_LAST = [
    "Alder",
    "Birchwood",
    "Calloway",
    "Dunmore",
    "Ellery",
    "Fairbanks",
    "Garrow",
    "Holloway",
    "Ingram",
    "Jessop",
    "Kestrel",
    "Linwood",
    "Marchetti",
    "Northcott",
    "Oakhurst",
    "Pellham",
    "Quarry",
    "Ravel",
    "Stroud",
    "Thackery",
    "Underhill",
    "Vance",
    "Whitlock",
    "Yardley",
    "Zeller",
    "Ashdown",
    "Brightwater",
    "Carrow",
    "Delacroix-Moss",
    "Everly",
    "Fenwick",
    "Galloway",
    "Hartigan",
    "Ivers",
    "Juniper",
    "Kingsley",
    "Lockhart",
    "Merriweather",
    "Nightingale",
    "Osgood",
]


def _people(rng) -> pd.DataFrame:
    rows, i = [], 0
    for grad in range(2025, 2030):  # classes with at least one exam in 2024-2026
        for _ in range(PER_CLASS):
            rows.append(
                dict(
                    ID=str(900101 + i),
                    first=_FIRST[i % 40],
                    last=_LAST[(i + 3 * (i // 40)) % 40],
                    grad=grad,
                    ability=rng.normal(0, 1),
                    mk_rate=rng.lognormal(5.6, 0.9),
                )
            )
            i += 1
    return pd.DataFrame(rows)


def _xlsx(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def make_demo(seed: int = 7) -> dict:
    """{'rosters': [(filename, bytes), ...], 'mksap': (filename, bytes), 'people': DataFrame}."""
    rng = np.random.default_rng(seed)
    ppl = _people(rng)
    q_answered = np.minimum(np.round(ppl.mk_rate), 1400).astype(int)
    rosters = []
    for y in EXAM_YEARS:
        pgy = y + 4 - ppl.grad
        d = ppl[(pgy >= 1) & (pgy <= 3)].copy()
        d["PGY"] = pgy[d.index]
        mk_boost = 1.1 * np.log2(1 + q_answered[d.index] / 100) * (d.PGY > 1)
        nat = d.PGY.map(NATIONAL_MEAN)
        pct = (nat + 6.5 * d.ability + mk_boost + rng.normal(0, 2.5, len(d))).round().clip(25, 95)
        out = pd.DataFrame(
            dict(
                ID=d.ID.astype(int),
                Name=d["last"] + ", " + d["first"],
                PGY=d.PGY,
                Program_Number=100000,
                Program_Name="DEMO INTERNAL MEDICINE PROGRAM",
                Total_Test_Percent_Correct=pct.astype(int),
                Total_Test_Percentile_Rank=(100 * norm.cdf((pct - nat) / 8)).round().clip(1, 99).astype(int),
            )
        )
        for stem in AREAS:
            a = (pct + rng.normal(0, 7, len(d))).round().clip(10, 100)
            out[f"{stem}_Percent_Correct"] = a.astype(int).values
            out[f"{stem}_Percentile_Rank"] = (100 * norm.cdf((a - nat) / 11)).round().clip(1, 99).astype(int)
        rosters.append((f"{y} Downloadable Roster with Score Results_DEMO.xlsx", _xlsx(out)))

    # MKSAP: current residents (grad >= 2027) except one, plus two graduates; small 16 x 50 bank
    sections = list(SECTION_NAMES)
    bank = [(s, 1000 * (k + 1) + n) for k, s in enumerate(sections) for n in range(50)]
    accounts = ppl[ppl.grad >= 2027].iloc[1:].copy()  # first current resident has no MKSAP account
    accounts = pd.concat([accounts, ppl[ppl.grad == 2026].head(2)])  # graduates still in MKSAP
    rows = []
    for idx, p in accounts.iterrows():
        last, first = p["last"], p["first"]
        if first == "Thomas":
            first = "Tom"  # nickname
        if idx % 9 == 4:
            last = last.upper()  # all-caps
        last = last.replace("-", " ")  # hyphen dropped in MKSAP
        n_ans = min(len(bank), int(q_answered[idx] * len(bank) / 3156 * 4))
        answered = set(rng.choice(len(bank), size=n_ans, replace=False)) if n_ans else set()
        acc = norm.cdf(0.4 + 0.5 * p.ability)
        for j, (sec, qn) in enumerate(bank):
            a = j in answered
            rows.append((last, first, sec, qn, "Y" if a else "N", "Y" if a and rng.random() < acc else "N"))
    mk = pd.DataFrame(
        rows, columns=["Last Name", "First Name", "Subspecialty", "Question Number", "Answered?", "Correct?"]
    )
    return dict(rosters=rosters, mksap=("MKSAP detail DEMO.csv", mk.to_csv(index=False).encode()), people=ppl)
