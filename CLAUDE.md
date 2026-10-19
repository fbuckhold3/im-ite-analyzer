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
4. **MKSAP** — PD or resident adds the MKSAP Digital detail export → progress + MKSAP-vs-ITE analysis.

## Layout
- `ite_core/` pure functions, no Shiny, no disk writes: `nomogram`, `roster`, `names`, `mksap`,
  `history`, `stats`, `pdf_reports`, `individual`.
- `tests/` pytest on synthetic fixtures only (`tests/conftest.py`). Run: `.venv/bin/python -m pytest`.
- `scripts/validate_real_data.py <dir>` checks ite_core against a private real-data analysis (aggregates only).
- `scripts/check_no_data.py` blocks data files / emails from commits (pre-commit + CI).
- `modules/` (step 2+) one Shiny module per tab.

## Environment
- Python 3.12 in `.venv/`. `requirements.txt` = runtime; `requirements-dev.txt` adds pytest, ruff, pre-commit.
- Lint/format: `.venv/bin/ruff check . && .venv/bin/ruff format --check .` (config in pyproject.toml).
- Deploy: Posit Connect Cloud. Needs `manifest.json` at repo root once `app.py` exists:
  `rsconnect write-manifest shiny .`. **Gotcha:** manifest.json pins its own package versions —
  regenerate it whenever requirements.txt changes.
- PDFs read with `pypdf` (pure Python). Never shell out to `pdftotext` — not on the server.
  Avoid PyMuPDF (AGPL) — incompatible with this project's Apache-2.0 licensing.

## Rules (repo is PUBLIC)
- Never commit real data, program names/numbers, or institution branding. Tests use invented names/IDs.
- Uploaded data is processed in memory only; no server-side persistence, no analytics.
- Nomogram: cite McDonald et al. 2020 wherever predictions are shown, and describe it as an
  approximation of the published curves (see docs/METHODS.md).
- Tier cutoffs are a setting (default High <50%, Intermediate 50–90%, Low ≥90%).
- `individual.ITE_TO_MKSAP` (ITE area → MKSAP section codes) is provisional, esp. GIM / Geriatrics.
- Update CHANGELOG.md for user-visible changes; bump version in pyproject.toml + CITATION.cff on release.
