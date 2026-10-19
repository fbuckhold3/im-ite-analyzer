# im-ite-analyzer — Product Spec

Status: v0.1 (core library built) · Author: Fred Buckhold

> PRIVACY: this spec contains no resident or program data. Never commit rosters, MKSAP exports,
> reports or crosswalks (.gitignore blocks *.xlsx/*.csv/*.html/*.pdf). Tests use synthetic fixtures.
> Validation against real data runs locally via `scripts/validate_real_data.py` with private targets.

---

## 1. Goal
A general ACP IM-ITE + MKSAP analysis app that any internal medicine program, or an individual
resident, can use. Four uses:

1. **Quick calculator** — % correct + PGY (optionally all three years) → ABIM pass estimate, risk tier,
   trajectory, and the % correct that would reach the Low-risk tier.
2. **Program analysis (PD)** — upload any number of ACP roster files and/or the Program Performance
   Report → program trends, individual trajectories + pass estimates, item-gap analysis, reports.
3. **Resident self-analysis** — upload one's own Examinee Performance Report → pass estimate, strengths
   and focus areas, missed educational objectives grouped by content area.
4. **MKSAP** — add an MKSAP Digital detail export (PD: whole program; resident: own data) → progress
   and MKSAP-vs-ITE analysis.

Nothing institution-specific in the core. Optional integrations (e.g. a program's own database export)
belong in separate, opt-in modules.

## 2. Inputs (all uploaded per session, processed in memory)
| Input | Format | Notes / gotchas seen in real files |
|---|---|---|
| ACP Downloadable Roster, one per year | .xlsx or .csv | Year from filename (`20\d\d`); user can override. **Columns differ by year**: 2023 has area % correct but *no* area percentiles and a different column order; 2024+ have both. Detect by name, never by position. `ID` may load as float → cast to int → str. Drop rows with blank ID / PGY outside 1–3 (PGY-4 optional toggle). |
| MKSAP Digital detail export | .csv (~350k rows for a program) | Columns: `Last Name, First Name, Subspecialty, Question Number, Answered?, Correct?` (Y/N). One row per person × item. Question numbers repeat within a subspecialty (different items) — count rows, don't dedupe on number. Every person carries the full bank (3,156 items in the 2026 edition). Includes graduates/faculty → many legitimately unmatched. Name case varies. |
| ACP Examinee Performance Report | .pdf | Single resident (~4 pages) or the composite of all residents; split on `Candidate ID:`. Page 1: total % correct, percentile, PGY, content-area table (yours / national mean / SD / percentile). Later pages: missed objectives by area; `**` = High Value Care. |
| ACP Program Performance Report | .pdf | p.2 content-area table (all-programs mean, program mean, program %ile rank per PGY group); then every item with national vs program % correct per PGY. |
| (optional) Email roster | .csv/.xlsx | Name + email; for the emailing manifest. |
| (optional) Crosswalk from a prior session | .csv | Re-upload to skip re-confirming matches. |

National PGY means (from the ACP histograms) are not in the roster — allow optional manual entry per
year; percentiles already encode national standing.

## 3. Identity resolution
**A. ITE ↔ ITE across years** — the ACP Candidate `ID` is stable across years. Use it as the person key;
fall back to name only if an ID is missing.

**B. MKSAP ↔ ITE** — names only:
1. Normalize: NFKD → ASCII, lowercase, punctuation/hyphens to spaces, collapse whitespace.
   ITE `Name` is "Last, First Middle"; MKSAP has separate Last/First.
2. Candidate = exact normalized last name **AND** first-name agreement (same initial, or a known nickname pair).
   ⚠️ A surname-only rule once merged *Smith, P.* into *Smith, R.* — always require first-name agreement.
3. Fallback for compound/hyphenated surnames: any shared last-name token + first-name agreement.
4. >1 candidate: keep those with an identical first token; otherwise Ambiguous.
5. An MKSAP account proposed for two residents → both Ambiguous.
6. Tiers: **Exact** (last + first token identical), **Probable**, **Ambiguous**, **Unmatched**.
7. Review UI: every ITE resident with proposed match, tier badge, override dropdown (searchable unmatched
   MKSAP names) or "no MKSAP account". Separate list of unmatched MKSAP accounts (expected: graduates).
8. Export/import crosswalk (`acp_id, ite_name, mksap_key, mksap_last, mksap_first, tier, n_candidates, confirmed_by_user`).

Acceptance on real data: every current resident with an MKSAP account matched, 0 false merges, graduates
and other MKSAP-only accounts listed as unmatched.

## 4. Data model (in-memory per session)
- `ite_long`: ID, Name, Exam_Year, PGY, Pct_Correct, Percentile, area columns, Grad_Class = Exam_Year + 4 − PGY, Pass_Prob, Risk_Tier
- `ite_wide`: one row per current resident with `<metric>_<year>` + 1-year deltas (% correct, percentile, pass prob, tier change)
- `mksap_person`: answered, correct, bank size, pct_correct, pct_bank
- `mksap_section`: person × subspecialty answered/correct/n
- `crosswalk`

## 5. Analyses / tabs
1. **Upload & Align** — file drop, detected year/columns per file, match review (§3), privacy note.
2. **Program trends by PGY level** — small multiples (PGY-1/2/3 × exam years) with metric toggle: mean %ile,
   median %ile, % ≥50th, % <35th, mean % correct, % at/above the Low-risk cutoff. Table with n per cell.
3. **Class matrix** — rows = graduating class, cols = PGY-1/2/3, cell = mean %ile (n, exam year); last col = change.
4. **Year-over-year (same people)** — paired percentile change per class; Wilcoxon signed-rank; prior vs
   current scatter with diagonal + 20th/35th guides.
5. **ABIM pass estimate** — logistic approximation of the McDonald et al. 2020 curves (see METHODS.md):
   PGY1 (−7.0641, 0.1811), PGY2 (−8.1445, 0.1733), PGY3 (−11.9491, 0.2173).
   Tier cutoffs are a setting; **default High <50%, Intermediate 50–90%, Low ≥90%**. Watch list for PGY-2/3.
   Explain that a tier can worsen with an unchanged score because each PGY curve is steeper (show percentile alongside).
6. **MKSAP** —
   - Progress: questions answered by class (strip + IQR), bins (<100, 100–249, 250–499, 500–999, 1000+),
     % of bank, accuracy; section heat table (% attempted, accuracy by class).
   - Relationship to ITE: Spearman ρ of questions vs current % correct, vs gain, vs *prior* % correct
     (shows it is not only strong residents doing more); thirds-within-class table; OLS
     `current ~ prior + PGY + log(1+Qs)` (report β·ln2 per doubling, β·ln8 for 100→800, R² with/without),
     and `+ MKSAP % correct`. Same with percentile outcome. Outcome toggle on the scatter.
   - Caveats: observational; MKSAP snapshot may post-date the ITE; MKSAP editions reset; small n.
   - Future: multiple date-stamped MKSAP snapshots → progress over time.
7. **Content areas** — area % correct / percentile by class; program-report rank table.
8. **Item-level gaps** — from the Program Performance Report: every item (objective, area, national vs
   program % correct for PGY1/2/3/All; wrapped objective lines; `**` HVC marker). Flag **red** = All-PGY
   gap ≤ −10 points, **yellow** = any single-PGY gap ≤ −20. Sortable table + annotated PDF (later).
   Caveat: one resident ≈ several points at a single PGY level in a small program.
9. **Resident self-analysis** — pass estimate + score needed for Low risk now/next year; areas ranked by
   percentile (Strength ≥60th, Focus <35th, else the two weakest); missed objectives by area; optional
   MKSAP section coverage/accuracy next to each ITE area.
10. **Reports & exports**
    - Identified PD report (self-contained HTML).
    - De-identified program summary (aggregates only, unlabeled dots, no per-person risk). Suppress any
      cell with n<5.
    - Individual PDF splitter + emailing manifest (.xlsx with an Excel table named `Reports`) for a
      Power Automate flow (manifest columns CandidateID, Name, FirstName, PGY, FileName, Email, Send, SentOn).

Every tab and report opens with a "How to read these numbers" box: % correct (share of items right;
depends on exam difficulty; rises with PGY — national ≈60/67/70% in 2026; drives the ABIM estimate) vs
percentile (rank vs same-PGY U.S. residents that year; best for comparing years/classes; a resident can
gain % correct and lose percentile).

## 6. Architecture
- Python Shiny + plotly + pandas.
- `ite_core/` pure functions (roster, names, nomogram, mksap, history, stats, pdf_reports, individual)
  with **pytest** tests on synthetic fixtures; `modules/` one Shiny module per tab.
- PDFs via `pypdf` (pure Python, BSD). No system binaries; no AGPL dependencies.
- Deployment: Posit Connect Cloud (`requirements.txt` + `manifest.json`). In-memory processing only; no
  server-side persistence; visible privacy note on every upload.

## 7. Build order
1. ✅ `ite_core` + tests; validated against a private real-data analysis.
2. ✅ Upload & Align tab with crosswalk export/import; quick-calculator tab; demo data; upload hardening.
3. Trends + class matrix. 4. ABIM tab. 5. MKSAP tab. 6. Resident self-analysis tab.
7. Item gaps + report downloads. 8. PDF splitter + emailing manifest.

## 8. Open questions
- One program per session, or allow comparing programs?
- MKSAP section-code labels (HP, IN, CC, FC, CS) and the ITE-area → MKSAP-section map — confirm with ACP.
- Access model: public calculator vs sign-in for uploads.
- MKSAP-thirds tie-breaking: currently row order (matches the original analysis); consider an
  order-independent rule.
