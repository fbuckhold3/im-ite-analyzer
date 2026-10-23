# Changelog

All notable changes are recorded here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Added
- **Board outcomes** (new section): drop ABIM's Examination Results report and/or Program Data Report (PDF) on
  Upload & Align. Takers are linked to graduates' ITE records by name (manual linking for the rest) and the section
  shows predicted vs observed pass rate per exam year, outcomes by predicted risk tier, each graduate's estimate
  against their result, ABIM score vs last ITE (Program Data Report), and an anonymous table of estimate, MKSAP and
  result. Included in the confidential PD report only. `ite_core/abim.py`, `modules/outcomes_tab.py`.
- **Projected ABIM pass rate by class** on Board pass and in the PD report: the average of residents' estimated
  pass probabilities, with a likely range (middle 80%, by chance alone) for the number who pass. The de-identified
  summary shows the rate only and suppresses classes under 5.
- **Home** page with three entry cards (Quick estimate, Resident report, Program analysis), each saying what to
  bring and what you get, plus a "How to use it" guide: numbered steps for residents and for program directors,
  a labeled example of the resident results, a "what each file unlocks" map, and a files → session → results
  privacy strip.
- **Resident report**: board-pass curve directly under the estimate with next-year targets (the % correct needed
  next year for ≥90% pass probability; not shown for PGY-3); content areas in three colored percentile bands
  (≥50th, 25th–49th, <25th); optional Program Performance Report upload ranks the resident's 20 biggest misses
  and 10 notable wins against national % correct. Same content in the resident PDF.
- **PD report design**: header band with the program name, summary tiles (residents tested, PGY-2/3 in Low
  risk, watch list or suppressed below-Low count, mean percentile change, MKSAP effect, red-flag items), section
  cards with a one-line takeaway, colored tier/flag badges, tier distribution bars (identified report only),
  larger chart text and side-by-side charts on wide screens. Print layout and suppression rules unchanged.
- **Resident PDF** (US Letter, 2–6 pages): estimate and tier, content-area chart and table, trajectory with the
  nomogram, missed objectives. Download from **My ITE report** (from the resident's own score report) or from the
  **Board pass** resident detail (from roster data; no missed objectives or national means, labelled as prepared
  by the program). Built in memory with reportlab + static matplotlib charts (object API — safe for concurrent
  visitors). New dependencies: `reportlab==5.0.1`, `matplotlib==3.11.2`.
- Program HTML reports are print-ready: "Print / Save as PDF" button, US Letter page setup, one section per page,
  toolbars hidden, and a confidentiality / de-identified line on every printed page.
- **Download all data (.xlsx)** on the Reports tab: one identified workbook with a Read me sheet plus Residents,
  ITE by exam (every resident × exam year with content areas and graduating class), By PGY level, By class,
  Year over year (+ summary), MKSAP (+ sections for the full detail export), Crosswalk, Item gaps and Area ranks —
  each included only when its data was uploaded. `modules/data_export.py`.
- **Item gaps** sub-tab from the ACP Program Performance Report (new optional PDF upload on Upload & Align):
  content-area percentile ranks among programs by PGY group, red/yellow item flags with adjustable cutoffs, a
  filterable item table, flagged-items CSV and all-items Excel downloads. Invented sample report in the demo.
- **Reports** sub-tab: self-contained HTML downloads (charts interactive offline) — an identified PD report
  (watch list, names) and a de-identified program summary (aggregates only; counts of 1–4 and groups under 5
  suppressed, with complementary suppression so hidden counts can't be recovered by subtraction; unlabeled
  points). `modules/report_builder.py`.

### Changed
- **Program analysis upload**: one drop zone for every file. Each file is recognized from its contents
  (`ite_core/detect.py`: ACP roster, MKSAP overview/detail export, Program Performance Report, saved crosswalk) and
  ticked off a "What to upload" checklist that says what each file is, where to get it, what it unlocks, and
  suggests adding the optional ones. A resident's Examinee report dropped here is pointed to Resident report;
  anything unrecognized is listed with the reason. Files added later join the ones already loaded.
- **Program analysis navigation**: section boxes (name + one line, muted with "Needs …" until their file is
  added) replace the row of sub-tabs; on phones they become one scrolling row.
- **Item gaps**: content areas shown as a heatmap (area × PGY group, program rank among programs, lowest first,
  numbers in every cell) instead of the dot plot; summary tiles; questions in a formatted table with flag badges,
  a program-vs-national bar and colour-coded gap chips, filterable by content area (stacked cards on phones).
  The PD report uses the same heatmap and table.
- Higher contrast throughout: tinted page background behind white cards, firmer card and table headers.
- **MKSAP matching** on Upload & Align redesigned: residents needing review come first, one row each with
  Confirm / account picker / "No MKSAP account"; choosing an account already linked to someone else moves it and
  sends that resident back for review; automatic matches and unlinked accounts are collapsed below.
- Resident area bands are now 50th / 25th percentile (were 60th / 35th with a "two weakest" fallback).
- Scope: the app is an analyzer only; splitting score reports and emailing residents are out of scope.

### Security
- Removed Plotly's "Share chart" (Plotly Cloud upload) and Chart Studio buttons from every chart in the app and
  the reports, so resident data can't be uploaded to a third party from a chart toolbar.
- MKSAP **members overview** export accepted alongside the full detail export (detected from the columns);
  every analysis works with either except section coverage, which needs the full detail. Upload & Align shows
  the export type and bank size; "How to get your program's MKSAP export" help and `docs/MKSAP_EXPORT.md`
  (MKSAP Tracker → Members → Export Overview / Export Details).

### Changed
- MKSAP is program-level only: residents cannot export their own MKSAP data, so the MKSAP upload, sample file
  and MKSAP columns were removed from **My ITE report**.
- **MKSAP** sub-tab: progress by class (median and IQR of questions answered, % of bank, accuracy; strip plot;
  volume bins; section table of % attempted and accuracy by PGY) and MKSAP vs the next ITE for PGY-2/3
  (plain-language headline from the adjusted regression, thirds-within-class chart, scatter with trend line,
  Spearman correlations with a guarded interpretation, accuracy effect, caveats). Outcome toggle: % correct /
  percentile. Regressions are skipped below 10 paired residents; non-significant results are labelled as such.
- `mksap.progress_by_pgy`, `bins_table`, `section_table`; `stats.mksap_points`, `trend_line`, `MIN_MODEL_N`.

### Changed
- Demo MKSAP data is more realistic: interns answer far fewer questions and sections differ in popularity.
- **Board pass** sub-tab: tier counts by PGY and tier changes since last year; nomogram with every current
  resident (click a dot, or use the picker, to open their year-by-year history and roster content-area
  percentiles); PGY-2/3 watch list (below Low risk or tier worsened, with points from the Low-risk score);
  sortable table of all residents (% correct, percentile, estimates, tier, change, MKSAP) with CSV download;
  adjustable Low-risk cutoff for the tab.
- `ite_core.board`: `board_table`, `tier_summary`, `change_summary`, `watch_list`, `resident_history`,
  `resident_areas`.

### Fixed
- Charts with missing values (e.g. roster area data without national means) no longer disconnect the session:
  every figure is cleaned of NaN before it is sent to the browser (`plots.widget_safe`).
- **Program data** sub-tabs reading the uploaded rosters:
  - **Trends by level** — PGY-1/2/3 small multiples across exam years with a metric toggle (mean/median
    percentile, % ≥50th, % <35th, mean % correct, % Low risk) and a value (n) table; groups under 5 hatched
    and flagged.
  - **Classes** — trajectory line per graduating class (current solid, graduated dashed, fixed colours,
    end labels) and a class matrix with change from first to latest ITE; percentile / % correct toggle.
  - **Year over year** — same-resident change per PGY with Wilcoxon test in plain language, and a prior-vs-
    current scatter (diagonal, 20th/35th guides); % correct framed as an expected rise with training.
- `history.class_trajectories()`, `small_n` flags; `stats.paired_points()`, `paired_change(outcome=)`.

### Fixed
- Paired analyses no longer fail when only one exam year is uploaded.
- **My ITE report** tab: a resident uploads their ACP Examinee Performance Report PDF (plus earlier years and,
  optionally, their own MKSAP export) → pass estimate and tier, score needed for Low risk now and next year,
  content-area percentile chart and table (Strength ≥60th / Focus <35th), missed objectives grouped by area
  (focus areas first, HVC marked), trajectory over years, MKSAP coverage per area (provisional mapping),
  print / save-as-PDF view. A composite PDF shows a resident picker. Invented sample report for trying it out.
- `individual.history()`, `group_by_resident()`, `pick_mksap_account()`; PGY-4 / non-IM comparison-group note.

### Fixed
- Examinee reports for the same Candidate ID in different exam years are no longer merged when they sit in
  one PDF.
- Shiny web app (`app.py`): **Calculator** tab (one exam or all years; pass estimate, tier, score needed for
  Low risk, nomogram plot that updates in place, trajectory table) and **Program data → Upload & Align** tab
  (multi-year ACP rosters, optional MKSAP export and saved crosswalk, per-file status with year fix-up,
  residents-by-year coverage, MKSAP match review with fix-a-match panel, "Accept all Probable",
  crosswalk download). About tab and footer with author credit, citation, privacy and trademark notes.
- Invented demo program (`ite_core.demo`) so anyone can try the app without real files.
- Public-upload hardening (`ite_core.limits`): file type/size/row/page caps; friendly errors that never echo
  file contents; uploads deleted from temp storage immediately after reading; sanitized error display.
- `Manual` match tier for links made by the user.
- `manifest.json` for Posit Connect Cloud, generated by `scripts/write_manifest.sh`; pinned runtime versions.

### Fixed
- Deploy on Posit Connect Cloud, which builds with Python 3.11: pinned numpy 2.4.6 / scipy 1.17.1 (the newest
  releases supporting 3.11); CI now tests Python 3.11 and 3.12.

## [0.1.0] - 2026-10-19
### Added
- `ite_core` analysis library: ACP roster loading (any year layout), ITE↔MKSAP name matching with review
  tiers and crosswalk export/import, ABIM pass-probability estimates (approximating McDonald et al. 2020),
  multi-year program tables, MKSAP-vs-ITE models, parsers for the ACP Examinee and Program Performance
  Report PDFs, item-gap flags, and single-resident analysis.
- pytest suite on synthetic data; validation script for private real-data checks.
- Apache-2.0 license, NOTICE, CITATION.cff, privacy, methods, security and contributing docs; CI.
