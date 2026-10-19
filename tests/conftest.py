"""Synthetic fixtures — every name and ID here is invented. Never put real resident data in tests."""

import numpy as np
import pandas as pd
import pytest

from ite_core.roster import AREAS

# ID, Name, PGY in 2026
PEOPLE = [
    ("1001", "Smith, Paula", 2),  # duplicate surname #1
    ("1002", "Smith, Robert", 3),  # duplicate surname #2 (MKSAP has "Rob")
    ("1003", "Abi-Karam, Lina", 3),  # hyphenated surname; MKSAP "Abi Karam"
    ("1004", "Nguyen, Thomas", 2),  # MKSAP all caps + nickname "Tom"
    ("1005", "Okafor, Ada", 1),  # no MKSAP account
    ("1006", "Garcia, Maria Elena", 1),  # middle name
]


def roster_frame(year: int, style: str = "modern", pgy_shift: int = 0, extra_rows=()):
    rows = []
    for i, (pid, name, pgy26) in enumerate(PEOPLE):
        pgy = pgy26 - (2026 - year)
        if pgy < 1:
            continue
        pc = 55 + 4 * pgy + i
        r = dict(
            ID=float(pid) if style == "2023" else int(pid),
            Name=name,
            PGY=float(pgy) if style == "2023" else pgy,
            Program_Number=999999,
            Program_Name="TEST PROGRAM",
            Total_Test_Percent_Correct=pc,
            Total_Test_Percentile_Rank=10 + 12 * i,
        )
        for stem in AREAS:
            r[f"{stem}_Percent_Correct"] = pc + 1
            if style != "2023":
                r[f"{stem}_Percentile_Rank"] = 40 + i
        rows.append(r)
    rows.extend(extra_rows)
    df = pd.DataFrame(rows)
    if style == "2023":  # different column order, percentile before % correct
        first = [
            "ID",
            "Name",
            "PGY",
            "Program_Number",
            "Program_Name",
            "Total_Test_Percentile_Rank",
            "Total_Test_Percent_Correct",
        ]
        df = df[first + [c for c in df.columns if c not in first]]
    return df


@pytest.fixture
def roster_files(tmp_path):
    """Three years: 2024 (2023-style layout + a blank-ID row + a PGY-4), 2025, 2026."""
    paths = []
    for y in (2024, 2025, 2026):
        extra = (
            [
                dict(ID=np.nan, Name="Blank, Row", PGY=1.0, Total_Test_Percent_Correct=50),
                dict(ID=2001.0, Name="Chief, Pat", PGY=4.0, Total_Test_Percent_Correct=70),
            ]
            if y == 2024
            else []
        )
        p = tmp_path / f"{y} Downloadable Roster with Score Results_TEST.xlsx"
        roster_frame(y, "2023" if y == 2024 else "modern", extra_rows=extra).to_excel(p, index=False)
        paths.append(p)
    return paths


def mksap_rows():
    """Long MKSAP export: 3 sections x 4 questions each; question numbers repeat within a section."""
    people = [
        ("Smith", "Paula", 300),
        ("Smith", "Rob", 40),
        ("Smith", "Priya", 500),  # Priya = graduate
        ("Abi Karam", "Lina", 900),
        ("NGUYEN", "Tom", 120),
        ("Garcia", "Maria", 0),
        ("Lee", "Jordan", 50),
    ]  # MKSAP-only graduate
    rows = []
    for last, first, _ in people:
        for sec in ("CV", "GI", "NP"):
            for q in (1, 2, 1, 2):  # repeated numbers = different items
                rows.append({"Last Name": last, "First Name": first, "Subspecialty": sec, "Question Number": q})
    df = pd.DataFrame(rows)
    rng = np.random.default_rng(0)
    df["Answered?"] = np.where((df["First Name"] != "Maria") & (rng.random(len(df)) < 0.75), "Y", "N")
    df["Correct?"] = np.where(df["Answered?"].eq("Y") & (rng.random(len(df)) < 0.6), "Y", "N")
    return df


@pytest.fixture
def mksap_csv(tmp_path):
    p = tmp_path / "mksap.csv"
    mksap_rows().to_csv(p, index=False)
    return p


EXAMINEE_PAGE1 = """                                2026 Internal Medicine In-Training Examination®
                                             Examinee Performance Report

Name:    {name}
Candidate ID:     {cid}
Program ID:     999999

                                         Total Test Percent Correct Score           {pc}%
                                         Percentile Rank by PGY Level                {ile}
                                         PGY Level                                    {pgy}

          Cardiology                                               69               71               11             34
          Endocrinology                                            61               71               12             15
          Gastroenterology                                         71               69               13             48
          General Internal Medicine                                79               70               10             77
          Geriatric Medicine                                       75               72               14             48
          Hematology/Oncology                                      67               69               11             35
          Infectious Diseases                                      52               68               13              9
          Nephrology                                               56               62               15             28
          Neurology                                                60               67               16             22
          Pulmonary and Critical Care Medicine                     65               71               11             24
          Rheumatology                                             83               72               12             73

          High Value Care**                                        74               71               11             53

EEID:{cid}$$
                                                           Page 1 of 2
"""

EXAMINEE_PAGE2 = """                                2026 Internal Medicine In-Training Examination®
                                             Examinee Performance Report
Name:    {name}
Candidate ID:     {cid}
Program ID:     999999

Cardiology
Diagnose an invented arrhythmia.
Manage a fictional valve lesion in a patient with a very long objective that wraps onto a
second printed line.
Endocrinology
Treat a made-up thyroid condition.**
Infectious Diseases
Treat an imaginary infection.

EEID:{cid}$$
                                                           Page 2 of 2
"""


def examinee_pages(name="Test, Alex", cid="1001", pc=68, ile=38, pgy=3):
    k = dict(name=name, cid=cid, pc=pc, ile=ile, pgy=pgy)
    return [EXAMINEE_PAGE1.format(**k), EXAMINEE_PAGE2.format(**k)]


PROGRAM_P1 = """                     2026 INTERNAL MEDICINE IN-TRAINING EXAMINATION®
                                PROGRAM PERFORMANCE REPORT
PROGRAM NAME:               TEST PROGRAM                                  PROGRAM:            999999
"""
PROGRAM_P2 = """2026 INTERNAL MEDICINE IN-TRAINING EXAMINATION®:  PROGRAM PERFORMANCE REPORT        PROGRAM:            999999
                                 2026 MEAN PERCENT CORRECT SCORES
CONTENT AREA                            Programs   Program     Rank       Programs   Program    Rank     Programs     Program   Rank      Programs   Program    Rank

Cardiology                              59         58         41         68         69          59        71        70         41         66         66         52
High Value Care**                       61         63         68         68         72          75        71        72         52         67         69         69
Total Test (SD)                         60 (9)     60 (6)     51         67 (9)     69 (9)      68        70 (8)    70 (8)     53         66 (9)     66 (9)     57
Number of Residents                     12512      25                    12844       29                    11594     27                   37555      81
"""
PROGRAM_P3 = """2026 INTERNAL MEDICINE IN-TRAINING EXAMINATION®:  PROGRAM PERFORMANCE REPORT        PROGRAM:            999999
                                                                     PGY1          PGY2          PGY3        ALL PGYs
Educational Objectives for Cardiology Items                          ALL   Your    ALL   Your    ALL   Your  ALL   Your
Diagnose an invented arrhythmia.                                       64    68      79    79      83    78    75    75
Manage a fictional valve lesion in a patient with a long objective     53    40      53    38      56    40    54    40
that wraps.
Treat a pretend cardiomyopathy.**                                      80    55      80    78      80    79    80    71
                                                                                      GRPID:999999$$
"""


def program_pages():
    return [PROGRAM_P1, PROGRAM_P2, PROGRAM_P3]
