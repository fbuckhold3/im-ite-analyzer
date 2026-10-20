# im-ite-analyzer

[![CI](https://github.com/fbuckhold3/im-ite-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/fbuckhold3/im-ite-analyzer/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Analysis of the ACP Internal Medicine In-Training Examination (IM-ITE®) and MKSAP® question-bank
use, for internal medicine residents and program directors.

**Created by Fred Buckhold** ([ORCID 0000-0001-9049-3870](https://orcid.org/0000-0001-9049-3870)).

## What it does

| For | Upload | Get |
|---|---|---|
| Anyone | nothing — type a % correct and PGY (or all three years) | Estimated probability of passing ABIM, risk tier, the score needed for low risk |
| Residents | your ACP Examinee Performance Report (PDF), optionally your MKSAP export | Pass estimate, strengths and focus areas, missed objectives by content area, MKSAP coverage per area |
| Program directors | ACP roster files (any years), Program Performance Report, MKSAP export | Trends by PGY level and class, same-resident change, pass estimates, MKSAP-vs-ITE analysis, item-level gaps, reports |

Status: **in development** — the Calculator, My ITE report (resident self-analysis) and Program data →
Upload & Align, Trends by level, Classes and Year over year tabs work; ABIM, MKSAP, item gaps and
reports are next.
See [docs/REVISION_SPEC.md](docs/REVISION_SPEC.md) and [CHANGELOG.md](CHANGELOG.md).

## How the pass estimate works

Pass probabilities approximate the IM-ITE → ABIM prediction curves published by:

> McDonald FS, Jurich D, Duhigg LM, Paniagua M, Chick D, Wells M, Williams A, Alguire P.
> Correlations Between the USMLE Step Examinations, American College of Physicians In-Training Examination,
> and ABIM Internal Medicine Certification Examination. *Acad Med.* 2020;95(9):1388–1395.
> [doi:10.1097/ACM.0000000000003382](https://doi.org/10.1097/ACM.0000000000003382)

The coefficients are a logistic fit to the published curves, not values published by the authors.
Every method and its limitations are in [docs/METHODS.md](docs/METHODS.md).

## Intended use

Educational use only. The ITE is designed to help residents and programs find knowledge gaps while there is
still time to address them. These estimates are population-level associations. Do not use them for promotion,
remediation, employment or credentialing decisions. This is not medical or legal advice.

## Privacy

Uploads are processed in memory for your session and never stored, logged or shared. See [PRIVACY.md](PRIVACY.md).
This repository contains no resident or program data.

## Development

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pre-commit install          # blocks data files and emails from commits
.venv/bin/python -m pytest
.venv/bin/shiny run app.py --reload        # http://127.0.0.1:8000
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Security or privacy concerns: [SECURITY.md](SECURITY.md).

## Citing

If you use this software, please cite it (GitHub's **"Cite this repository"** button uses
[CITATION.cff](CITATION.cff)) and cite McDonald et al. (2020) for the pass-probability curves.

## License and trademarks

Copyright 2026 Fred Buckhold. Licensed under the [Apache License 2.0](LICENSE). Redistributions must keep
the [NOTICE](NOTICE) file, which carries the author credit and third-party attributions.

IM-ITE® and MKSAP® are registered trademarks of the American College of Physicians. This project is not
affiliated with or endorsed by ACP, ABIM or NBME.
