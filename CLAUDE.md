# im-ite-analyzer — Claude Code notes

Python app for ACP IM-ITE + MKSAP analysis, built for use by any internal medicine program and
its residents. Plan + acceptance criteria: `docs/REVISION_SPEC.md`. Methods: `docs/METHODS.md`.
Private, machine-local notes (if present): `CLAUDE.local.md`.

## Four uses the app must serve
1. **Quick calculator** — enter % correct + PGY (or all three years) → ABIM pass estimate, tier, trajectory.
2. **PD program analysis** — upload ACP roster(s) (.xlsx/.csv, any years) and/or the Program Performance
   Report PDF → trends, class matrix, board-pass estimates, item-gap flags.
3. **Resident self-analysis** — upload own Examinee Performance Report PDF → pass estimate,
   strengths / focus areas, missed objectives by area.
4. **MKSAP** — PD adds the program's MKSAP Digital export (members overview or full detail; residents
   cannot export their own) → progress + MKSAP-vs-ITE analysis. Export steps: docs/MKSAP_EXPORT.md (MKSAP Tracker → Members → Export Overview / Export Details).

## Layout
- `ite_core/` pure functions, no Shiny, no disk writes: `nomogram`, `roster`, `names`, `mksap`,
  `history`, `stats`, `pdf_reports`, `individual`.
- `tests/` pytest on synthetic fixtures only (`tests/conftest.py`). Run: `.venv/bin/python -m pytest`.
- `scripts/validate_real_data.py <dir>` checks ite_core against a private real-data analysis (aggregates only).
- `scripts/check_no_data.py` blocks data files / emails from commits (pre-commit + CI).
- `app.py` page_navbar + footer; `modules/` one Shiny module per tab (`calculator`, `resident`, `upload_align`) plus `program_tabs.py`
  (Trends / Classes / Year-over-year sub-tabs under Program data), `board.py` (Board pass sub-tab), `mksap_tab.py` (MKSAP sub-tab), `items_tab.py` (Item gaps), `reports_tab.py` + `report_builder.py`
  (HTML report downloads) + `data_export.py` (combined .xlsx; builder is pure but lives in modules/ because it reuses plots), `common.py` (badges, citation, footer) and `plots.py` (plotly builders, updated in place via shinywidgets).
- `upload_server()` returns a reactive `session.Dataset` (rosters, mksap, crosswalk, wide) — later tabs read it.
- `ite_core/session.py` assembles uploads (pure); `ite_core/limits.py` caps + `UploadError`; `ite_core/demo.py` invented data.

## Environment
- Python 3.12 in `.venv/`. `requirements.txt` = runtime; `requirements-dev.txt` adds pytest, ruff, pre-commit.
- Lint/format: `.venv/bin/ruff check . && .venv/bin/ruff format --check .` (config in pyproject.toml).
- Run: `.venv/bin/shiny run app.py --reload`.
- Deploy: Posit Connect Cloud from GitHub — it builds with **Python 3.11** (ignored manifest/.python-version 3.12
  on 2026-10-19), so every pin must support 3.11; CI runs 3.11 + 3.12. `requirements.txt` pins exact versions; regenerate `manifest.json`
  with `scripts/write_manifest.sh` (explicit deploy file list — never run write-manifest on the repo root,
  it would list local-only files). **Gotcha:** manifest.json carries its own copy of the package list.
- PDFs read with `pypdf` (pure Python). Never shell out to `pdftotext` — not on the server.
  Avoid PyMuPDF (AGPL) — incompatible with this project's Apache-2.0 licensing.

## Rules (repo is PUBLIC)
- Never commit real data, program names/numbers, or institution branding. Tests use invented names/IDs.
- Uploaded data is processed in memory only; no server-side persistence, no analytics. Shiny writes uploads to a
  temp file — read it and delete it immediately (`upload_align._take`). Raise `UploadError` (file names/counts
  only) for anything a user can cause; `app.sanitize_errors = True` hides everything else.
- Nomogram: cite McDonald et al. 2020 wherever predictions are shown, and describe it as an
  approximation of the published curves (see docs/METHODS.md).
- PDFs: `modules/resident_pdf.py` (reportlab) + `modules/static_charts.py` (matplotlib **object API only — never
  pyplot**, which has global state and breaks with concurrent visitors). Keep static charts visually in step with
  `plots.py`. Program reports stay HTML with print CSS.
- Every plot builder returns `widget_safe(fig)`: one NaN in widget data disconnects the session, and it also
  strips Plotly's cloud buttons (`sendChartToCloud` in plotly.js 4 uploads chart data to Plotly Cloud).
- De-identified outputs: suppress counts 1–4 and n<5 groups AND apply complementary suppression (totals are
  visible); privacy checks must exclude the embedded plotly.js source (`content_without_library`).
- Tier cutoffs are a setting (default High <50%, Intermediate 50–90%, Low ≥90%). Display probabilities with
  `common.fmt_prob` (rounds DOWN) so 89.8% never reads as "90%" next to an Intermediate badge.
- `individual.ITE_TO_MKSAP` (ITE area → MKSAP section codes) is provisional, esp. GIM / Geriatrics.
- Update CHANGELOG.md for user-visible changes; bump version in pyproject.toml + CITATION.cff on release.
