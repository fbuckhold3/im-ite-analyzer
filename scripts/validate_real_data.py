"""Check ite_core against a private, real-data analysis. Prints aggregates only — no names or IDs.

Usage:  .venv/bin/python scripts/validate_real_data.py <data_dir>

<data_dir> (never committed) must contain:
  rosters/*.xlsx                    ACP Downloadable Rosters, one per exam year
  *MKSAP*.csv                       MKSAP Digital detail export
  *Program Report*.pdf              ACP Program Performance Report (latest year)
  *Resident Score Reports*.pdf      ACP composite Examinee Performance Reports (latest year)
  analysis/*.csv                    outputs of the original reference analysis, to compare against
  validation_targets.json           expected headline numbers (see TARGET_KEYS below); optional
                                    "yoy": {"<pgy>": {"n", "d_ile", "p", "d_pc"}} for paired change;
                                    "files": {"mksap": ..., "program_report": ..., "score_reports": ...}
                                    to pick specific files when a pattern matches more than one
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ite_core import history, individual, mksap, names, pdf_reports, roster, stats  # noqa: E402

TARGET_KEYS = [
    "n_matched",
    "n_mksap_only",
    "n_model",
    "dbl",
    "r2_base",
    "r2_vol",
    "dbl_ile",
    "p_ile",
    "rho_q_pc_cur",
    "rho_q_dpc",
    "rho_q_pc_prev",
    "b_acc",
    "p_acc",
    "top_third_dpc",
    "bottom_third_dpc",
    "n_items",
    "n_red",
    "n_yellow",
]

if len(sys.argv) < 2:
    sys.exit(__doc__)
DATA = Path(sys.argv[1]).expanduser()
A = DATA / "analysis"
T = json.loads((DATA / "validation_targets.json").read_text())
missing = [k for k in TARGET_KEYS if k not in T]
if missing:
    sys.exit(f"validation_targets.json is missing: {missing}")
results = []


def one(pattern, key):
    if key in T.get("files", {}):
        return DATA / T["files"][key]
    hits = sorted(DATA.glob(pattern))
    if len(hits) != 1:
        sys.exit(f"Expected exactly one file matching {pattern!r} in {DATA}, found {len(hits)}")
    return hits[0]


def check(label, got, want, tol=0.0):
    ok = (got == want) if tol == 0 else (got is not None and abs(got - want) <= tol)
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: got {got}, want {want}")


def same_frame(label, a, b, keys, cols):
    m = a.merge(b, on=keys, how="outer", suffixes=("", "_ref"), indicator=True)
    both = m[m._merge == "both"]
    diff = sum(
        int(
            (
                ~np.isclose(
                    pd.to_numeric(both[c], errors="coerce"),
                    pd.to_numeric(both[f"{c}_ref"], errors="coerce"),
                    equal_nan=True,
                )
            ).sum()
        )
        for c in cols
    )
    check(f"{label}: rows only on one side", int((m._merge != "both").sum()), 0)
    check(f"{label}: differing cells", diff, 0)


print("\n== 1. Rosters -> long table")
long, infos = roster.load_rosters(sorted((DATA / "rosters").glob("*.xlsx")))
for i in infos:
    print(
        f"  {i['year']}: kept {i['rows_kept']}/{i['rows_in_file']} (blank ID {i['dropped_blank_id']}, "
        f"PGY {i['dropped_pgy']}), areas %ile={len(i['areas_percentile'])}"
    )
long = history.add_derived(long)
cur_year = int(long.Exam_Year.max())
same_frame(
    "vs ite_history_long.csv",
    long,
    pd.read_csv(A / "ite_history_long.csv", dtype={"ID": str}),
    ["ID", "Exam_Year"],
    ["PGY", "Pct_Correct", "Percentile", "Grad_Class", "Pass_Prob"],
)
agg_cols = ["n", "pc", "ile", "med", "ge50", "lt35", "pp90"]
same_frame(
    "by_level",
    history.by_level(long).rename(columns={"pp_low": "pp90"}),
    pd.read_csv(A / "ite_by_level.csv"),
    ["PGY", "Exam_Year"],
    agg_cols,
)
same_frame(
    "by_class",
    history.by_class(long).rename(columns={"pp_low": "pp90"}),
    pd.read_csv(A / "ite_by_class.csv"),
    ["Grad_Class", "PGY"],
    agg_cols,
)

print("\n== 2. Prior-year scores: rosters vs the values used in the reference analysis (ite_long.csv)")
old = pd.read_csv(A / "ite_long.csv", dtype={"ID": str})
old = old[old.Exam_Year < cur_year]
m = old.merge(long, on=["ID", "Exam_Year"], suffixes=("_ref", "_roster"), how="left")
for c in ("PGY", "Pct_Correct", "Percentile"):
    a, b = m[f"{c}_ref"], m[f"{c}_roster"]
    check(f"{c} differences", int((a.notna() & b.notna() & (a != b)).sum()), 0)

print("\n== 3. MKSAP <-> ITE matching")
people = mksap.per_person(mksap.load_mksap(one("*MKSAP*.csv", "mksap")))
cur = long[long.Exam_Year == cur_year]
cw = names.match_mksap(cur, people)
print("  tiers:", cw.tier.value_counts().to_dict(), "| MKSAP people:", len(people))
check("ITE residents matched", int(cw.mksap_key.notna().sum()), T["n_matched"])
check("MKSAP-only people", len(names.unmatched_mksap(cw, people)), T["n_mksap_only"])
refmk = pd.read_csv(A / "mksap_per_person.csv", dtype={"ID": str}).dropna(subset=["ID"])
agree = cw.merge(refmk[["ID", "key"]], left_on="acp_id", right_on="ID", how="outer")
check("matches differing from reference analysis", int((agree.mksap_key != agree.key).sum()), 0)

print("\n== 4. MKSAP -> ITE models")
w = history.attach_mksap(history.wide(long, cur_year), cw, people)
md = stats.mksap_models(w)
check("n (PGY-2/3 with prior)", md["n"], T["n_model"])
check("% correct per doubling", md["dbl"], T["dbl"], 0.05)
check("R² base", md["r2_base"], T["r2_base"], 0.005)
check("R² + volume", md["r2_vol"], T["r2_vol"], 0.005)
check("percentile per doubling", md["dbl_ile"], T["dbl_ile"], 0.05)
check("p (percentile volume)", round(md["p_ile"], 3), T["p_ile"], 0.0005)
check("rho(Qs, current % correct)", round(md["rho_q_pc_cur"][0], 2), T["rho_q_pc_cur"], 0.005)
check("rho(Qs, gain)", round(md["rho_q_dpc"][0], 2), T["rho_q_dpc"], 0.005)
check("rho(Qs, prior % correct)", round(md["rho_q_pc_prev"][0], 2), T["rho_q_pc_prev"], 0.005)
check("MKSAP accuracy beta", md["b_acc"], T["b_acc"], 0.005)
check("p (accuracy)", round(md["p_acc"], 3), T["p_acc"], 0.0005)
_, pooled = stats.mksap_thirds(w)
pooled = pooled.set_index("vol")
check("top third Δ % correct", pooled.loc["Highest", "dpc"], T["top_third_dpc"], 0.05)
check("bottom third Δ % correct", pooled.loc["Lowest", "dpc"], T["bottom_third_dpc"], 0.05)

print("\n== 4b. Same residents, last year -> this year (paired)")
for pgy, want in T.get("yoy", {}).items():
    pc = stats.paired_change(w, int(pgy))
    check(f"PGY-{pgy} n", pc["n"], want["n"])
    check(f"PGY-{pgy} mean percentile change", pc["d_ile"], want["d_ile"], 0.05)
    check(f"PGY-{pgy} Wilcoxon p", pc["p"], want["p"], 0.0005)
    check(f"PGY-{pgy} mean % correct change", pc["d_pc"], want["d_pc"], 0.05)

print("\n== 5. Program Performance Report")
prog = pdf_reports.parse_program_pdf(one("*Program Report*.pdf", "program_report"))
it = prog["items"]
check("items parsed", len(it), T["n_items"])
check("red flags", int((it.flag == "red").sum()), T["n_red"])
check("yellow flags", int((it.flag == "yellow").sum()), T["n_yellow"])
ref_items = pd.read_csv(sorted(A.glob("program_items_*.csv"))[-1])
check(
    "objective text identical to reference",
    int((it.objective.values != ref_items.objective.values).sum()) if len(it) == len(ref_items) else -1,
    0,
)
check("content-area rows (12 areas + total)", int(prog["areas"].area.ne("Number of Residents").sum()), 13)

print("\n== 6. Examinee reports vs roster")
reps = pdf_reports.parse_examinee_pdf(one("*Resident Score Reports*.pdf", "score_reports"))
r = cur.set_index("ID")
check("reports found", len(reps), len(cur))
check(
    "total / percentile / PGY disagreeing with roster",
    sum(
        1
        for x in reps
        if x["candidate_id"] not in r.index
        or (x["pct_correct"], x["percentile"], x["pgy"])
        != tuple(r.loc[x["candidate_id"], ["Pct_Correct", "Percentile", "PGY"]])
    ),
    0,
)
area_bad = 0
for x in reps:
    row = r.loc[x["candidate_id"]]
    for _, a in x["areas"].iterrows():
        key = roster.AREAS[a.area.replace(" and ", "_and_").replace("/", "_").replace(" ", "_")]
        area_bad += int(a.pct_correct != row[f"pc_{key}"] or a.percentile != row[f"ile_{key}"])
check("area cells disagreeing with roster", area_bad, 0)
check(
    "missed objectives with parse leftovers",
    sum(int((~x["missed"].objective.str.endswith(".")).sum()) for x in reps),
    0,
)
individual.analyze_examinee(reps[0])  # smoke test

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
