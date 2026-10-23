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
    # interns (class of 2029 in the 2026 snapshot) have barely started the bank
    q_answered = np.minimum(np.round(ppl.mk_rate * np.where(ppl.grad >= 2029, 0.12, 1.0)), 1400).astype(int)
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
    section_weight = np.linspace(2.5, 0.4, len(sections))[rng.permutation(len(sections))]
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
        sec_pref = np.repeat(section_weight, 50)  # some sections are far more popular than others
        answered = (
            set(rng.choice(len(bank), size=n_ans, replace=False, p=sec_pref / sec_pref.sum())) if n_ans else set()
        )
        acc = norm.cdf(0.4 + 0.5 * p.ability)
        for j, (sec, qn) in enumerate(bank):
            a = j in answered
            rows.append((last, first, sec, qn, "Y" if a else "N", "Y" if a and rng.random() < acc else "N"))
    mk = pd.DataFrame(
        rows, columns=["Last Name", "First Name", "Subspecialty", "Question Number", "Answered?", "Correct?"]
    )
    return dict(rosters=rosters, mksap=("MKSAP detail DEMO.csv", mk.to_csv(index=False).encode()), people=ppl)


# ------------------------------------------------------------------ sample resident report
_SAMPLE_AREAS = {  # area: (2025 your%, 2026 your%, national mean, sd)  — invented
    "Cardiology": (61, 70, 66, 11),
    "Endocrinology": (55, 60, 68, 12),
    "Gastroenterology": (63, 71, 64, 13),
    "General Internal Medicine": (70, 78, 67, 10),
    "Geriatric Medicine": (64, 72, 67, 14),
    "Hematology/Oncology": (58, 66, 65, 11),
    "Infectious Diseases": (50, 57, 64, 13),
    "Nephrology": (49, 58, 58, 15),
    "Neurology": (52, 61, 64, 16),
    "Pulmonary and Critical Care Medicine": (60, 69, 65, 11),
    "Rheumatology": (68, 77, 69, 12),
    "High Value Care": (62, 70, 67, 11),
}
_SAMPLE_MISSED = {  # invented, generic objectives
    "Cardiology": [
        "Manage an invented rhythm disturbance.",
        "Choose therapy for a fictional valve lesion in an older patient with several competing risks.",
    ],
    "Endocrinology": [
        "Evaluate a made-up adrenal finding.",
        "Adjust an imaginary insulin regimen.**",
        "Recognize a fictional thyroid emergency.",
    ],
    "Infectious Diseases": [
        "Select antibiotics for an invented infection.",
        "Prevent a pretend outbreak.**",
        "Diagnose a fictional fever syndrome.",
        "Treat an imaginary resistant organism.",
    ],
    "Nephrology": ["Correct a made-up electrolyte problem.", "Evaluate an invented kidney injury."],
    "Neurology": ["Manage a fictional headache syndrome.", "Diagnose an invented neuropathy."],
}


def _sample_pages(year: int, pgy: int, idx: int, pct: int, ile: int) -> list[str]:
    head = (
        f"                    {year} Internal Medicine In-Training Examination\n"
        "                              Examinee Performance Report\n\n"
        "Name:    Sample, Alex\nCandidate ID:     900999\nProgram ID:     100000\n"
    )
    rows = []
    for area, v in _SAMPLE_AREAS.items():
        mine, nat, sd = v[idx], v[2] + (5 if idx == 1 else -2), v[3]
        pctile = int(round(100 * norm.cdf((mine - nat) / sd)))
        label = area + ("**" if area == "High Value Care" else "")
        rows.append(f"          {label:<50}{mine:>6}{nat:>16}{sd:>16}{pctile:>14}")
    p1 = (
        head + f"\n          Total Test Percent Correct Score           {pct}%\n"
        f"          Percentile Rank by PGY Level                {ile}\n"
        f"          PGY Level                                    {pgy}\n\n" + "\n".join(rows) + "\n\nEEID:900999$$\n"
    )
    missed = []
    for area, objs in _SAMPLE_MISSED.items():
        missed.append(area)
        for o in objs[: len(objs) - (1 if idx == 1 and len(objs) > 2 else 0)]:
            if len(o) > 70:  # wrap long objectives the way ACP's layout does
                cut = o.rfind(" ", 0, 70)
                missed += [o[:cut], o[cut + 1 :]]
            else:
                missed.append(o)
    p2 = head + "\n" + "\n".join(missed) + "\n\nEEID:900999$$\n"
    return [p1, p2]


def sample_examinee_reports() -> list[dict]:
    """An invented resident's reports for two years (PGY-1 2025, PGY-2 2026), already parsed."""
    from .pdf_reports import parse_examinee_text

    return parse_examinee_text(_sample_pages(2025, 1, 0, 59, 45) + _sample_pages(2026, 2, 1, 67, 50))


# ------------------------------------------------------------------ sample Program Performance Report
_VERBS = ["Diagnose", "Manage", "Treat", "Evaluate", "Recognize", "Prevent", "Screen for"]
_THINGS = [
    "an invented condition",
    "a fictional syndrome",
    "a made-up complication",
    "an imaginary disorder",
    "a pretend presentation",
    "a hypothetical finding",
]


def sample_program_report(seed: int = 11) -> dict:
    """An invented ACP Program Performance Report, already parsed (areas + flagged items). Program 100000."""
    from .pdf_reports import parse_program_text

    rng = np.random.default_rng(seed)
    areas = [
        "Cardiology",
        "Endocrinology",
        "Gastroenterology",
        "General Internal Medicine",
        "Geriatric Medicine",
        "Hematology/Oncology",
        "Infectious Diseases",
        "Nephrology",
        "Neurology",
        "Pulmonary and Critical Care Medicine",
        "Rheumatology",
    ]
    p1 = (
        "                     2026 INTERNAL MEDICINE IN-TRAINING EXAMINATION\n"
        "                                PROGRAM PERFORMANCE REPORT\n"
        "PROGRAM NAME:               DEMO INTERNAL MEDICINE PROGRAM                       PROGRAM:            100000\n"
    )
    lines = [
        "2026 INTERNAL MEDICINE IN-TRAINING EXAMINATION:  PROGRAM PERFORMANCE REPORT        PROGRAM:            100000",
        "                                 2026 MEAN PERCENT CORRECT SCORES",
    ]
    for a in areas + ["High Value Care**"]:
        nums = []
        for nat in (60, 67, 70, 66):
            ours = int(nat + rng.normal(0, 4))
            nums += [nat, ours, int(np.clip(50 + 6 * (ours - nat) + rng.normal(0, 8), 1, 99))]
        lines.append(f"{a:<40}" + "".join(f"{n:<11}" for n in nums))
    lines.append(
        f"{'Total Test (SD)':<40}60 (9)     60 (6)     51         67 (9)     68 (8)      60        70 (8)    "
        "70 (8)     53         66 (9)     66 (8)     55"
    )
    lines.append(
        f"{'Number of Residents':<40}12500      10                    12800       10                    "
        "11600      10                    37000      30"
    )
    p2 = "\n".join(lines) + "\n"
    item_pages = []
    for a in areas:
        rows = [
            f"Educational Objectives for {a} Items                          ALL   Your    ALL   Your    ALL   Your  "
            "ALL   Your"
        ]
        for k in range(int(rng.integers(3, 7))):
            obj = f"{_VERBS[(k + len(a)) % len(_VERBS)]} {_THINGS[k % len(_THINGS)]} ({a.split()[0].lower()} {k + 1})."
            if k == 1:
                obj = obj[:-1] + ".**"  # HVC marker, as ACP prints it
            nat = [int(x) for x in rng.integers(35, 90, 3)]
            ours = [int(np.clip(n + rng.normal(-3, 12), 0, 100)) for n in nat]
            nat_a, our_a = int(np.mean(nat)), int(np.mean(ours))
            nums = [nat[0], ours[0], nat[1], ours[1], nat[2], ours[2], nat_a, our_a]
            rows.append(f"{obj:<70}" + "".join(f"{n:>6}" for n in nums))
        item_pages.append(
            "2026 INTERNAL MEDICINE IN-TRAINING EXAMINATION:  PROGRAM PERFORMANCE REPORT\n" + "\n".join(rows)
        )
    rep = parse_program_text([p1, p2] + item_pages)
    rep["file"] = "DEMO Program Performance Report"
    return rep


def sample_resident_program_report() -> dict:
    """An invented Program Performance Report matching the sample resident's exam, so the sample can show the
    'biggest misses / notable wins' ranking. Every sample missed objective appears, plus invented items answered
    correctly."""
    from .pdf_reports import flag_items

    rng = np.random.default_rng(5)
    rows = []
    for area in _SAMPLE_AREAS:
        if area == "High Value Care":
            continue
        missed = _SAMPLE_MISSED.get(area, [])
        extra = [
            f"{_VERBS[k % len(_VERBS)]} {_THINGS[(k + len(area)) % len(_THINGS)]} ({area.split()[0].lower()} "
            f"item {k + 1})."
            for k in range(5)
        ]
        for obj in missed + extra:
            hvc = obj.endswith("**")
            nat = [int(x) for x in rng.integers(20, 92, 3)]
            ours = [int(np.clip(n + rng.normal(0, 8), 0, 100)) for n in nat]
            rows.append(
                dict(
                    area=area,
                    objective=obj.replace("**", ""),
                    page=3,
                    hvc=hvc,
                    all1=nat[0],
                    our1=ours[0],
                    all2=nat[1],
                    our2=ours[1],
                    all3=nat[2],
                    our3=ours[2],
                    allA=int(np.mean(nat)),
                    ourA=int(np.mean(ours)),
                )
            )
    items = pd.DataFrame(rows)
    for k in ("1", "2", "3", "A"):
        items[f"gap{k}"] = items[f"our{k}"] - items[f"all{k}"]
    return dict(
        program_id="100000",
        program_name="DEMO INTERNAL MEDICINE PROGRAM",
        exam_year=2026,
        areas=pd.DataFrame(),
        items=flag_items(items),
        file="DEMO Program Performance Report (sample resident)",
    )


def _abim_pages(year: int, rows: list[tuple[str, str, str]], program_data: bool, rates=None) -> list[str]:
    """ABIM-style text pages (invented): rows of (name, result, score-or-'Withheld by Candidate')."""
    head = f"{year} INTERNAL MEDICINE CERTIFICATION EXAMINATION RESULTS\n" + "CANDIDATE NAME".ljust(60) + "EXAM RESULT"
    head += "        STANDARDIZED SCORE\n" if program_data else "\n"
    body = "\n".join(f"{n:<60}{r:<12}{s if program_data else ''}".rstrip() for n, r, s in rows)
    pages = [head + body]
    if program_data:
        ours, everyone = rates
        pages.insert(
            0,
            f"{year} OVERALL PROGRAM PERFORMANCE FOR INTERNAL MEDICINE\n"
            f"Candidates Across\nAll Programs: {everyone}%\nCandidates From\nYour Program: {ours}%\n",
        )
        pages.append("Note: The passing score for this exam is 371.\n")
    return pages


def sample_abim_reports(seed: int = 3) -> list[dict]:
    """Invented ABIM results for the demo program's two most recent graduating classes: a Program Data Report (with
    scores) for one exam year and an Examination Results report (pass/fail only) for the next. Results follow each
    graduate's estimated pass probability from their PGY-3 ITE, with chance. One name is spelled differently so the
    manual-linking step has something to show."""
    from . import abim  # local: abim imports names, which is heavier than demo needs elsewhere

    rng = np.random.default_rng(seed)
    d = make_demo()
    from . import session as S

    long = S.load_rosters([S.Upload(n, b) for n, b in d["rosters"]]).long
    cy = int(long.Exam_Year.max())
    out = []
    for grad, program_data in ((cy - 1, True), (cy, False)):
        g = long[(long.Grad_Class == grad) & (long.PGY == 3)].sort_values("Name")
        rows = []
        for i, r in enumerate(g.itertuples()):
            p = float(r.Pass_Prob)
            passed = rng.random() < min(0.995, p)
            score = int(np.clip(371 + (45 if passed else -35) + 60 * (p - 0.9) + rng.normal(0, 30), 210, 790))
            score = max(score, 371) if passed else min(score, 370)
            name = r.Name
            if i == 2:  # a different first name than on the ITE roster -> needs a manual link
                last = name.split(",")[0]
                name = f"{last}, Jordan"
            withheld = program_data and i == 4
            rows.append((name, "Pass" if passed else "Fail", "Withheld by Candidate" if withheld else str(score)))
        n_pass = sum(r[1] == "Pass" for r in rows)
        rates = (int(100 * n_pass / len(rows)), 87)
        pages = _abim_pages(grad, rows, program_data, rates)
        out.append(abim.parse_abim_text(pages, f"ABIM {'Program Data' if program_data else 'Results'} {grad} DEMO.pdf"))
    return out
