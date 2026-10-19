# Methods

How every number in im-ite-analyzer is computed, and the limits of each. Code references are to `ite_core/`.

## 1. ABIM pass-probability estimate (`nomogram.py`)

**Source.** McDonald FS, Jurich D, Duhigg LM, Paniagua M, Chick D, Wells M, Williams A, Alguire P.
Correlations Between the USMLE Step Examinations, American College of Physicians In-Training Examination,
and ABIM Internal Medicine Certification Examination. *Acad Med.* 2020;95(9):1388–1395.
[doi:10.1097/ACM.0000000000003382](https://doi.org/10.1097/ACM.0000000000003382)

The study (≈31,000 U.S. IM residents taking the IM-ITE in 2014 or 2015 and the ABIM certification exam in
2015–2018) published curves of the probability of passing ABIM on the first attempt, by IM-ITE % correct,
separately for PGY-1, PGY-2 and PGY-3.

**Approximation used here.** The paper reports curves, not coefficients. We fit a logistic curve per PGY level
to points read from the published figure:

P(pass) = 1 / (1 + e^−(b0 + b1 × % correct))

| PGY | b0 | b1 | % correct for P = 0.90 |
|---|---|---|---|
| 1 | −7.0641 | 0.1811 | 51.1 |
| 2 | −8.1445 | 0.1733 | 59.7 |
| 3 | −11.9491 | 0.2173 | 65.1 |

PGY values above 3 use the PGY-3 curve.

**Limitations.**
- An approximation of published curves, not the authors' model. Do not quote these as the authors' coefficients.
- Fitted on 2014–2015 exam cohorts. Exam difficulty, the ABIM exam and pass rates have changed since.
- Uses % correct only. The source study found USMLE scores and other factors also predict passing.
- A population-level association. It does not determine any individual's outcome.

**Risk tiers.** High < 50%, Intermediate 50–90%, Low ≥ 90% by default. Programs can change the cutoffs.
Because each PGY curve is steeper than the last, the same % correct gives a lower probability later in
training, so a tier can worsen with an unchanged score. The app shows the percentile alongside to make this clear.

## 2. Percent correct vs percentile
- **% correct**: share of exam items answered correctly. It depends on that year's exam difficulty and rises
  with training. It drives the ABIM estimate.
- **Percentile**: rank among same-PGY U.S. examinees that year (ACP-reported). It is the better measure for
  comparing years, levels and classes.

## 3. Linking records (`roster.py`, `names.py`)
- **Across ITE years**: ACP Candidate ID, which stays the same from year to year.
- **ITE ↔ MKSAP**: by name, because MKSAP exports carry no ACP ID. Names are normalized (accents removed,
  lowercase, punctuation to spaces). A match needs the exact surname, or a shared surname token for compound
  names, **plus** agreement on first name (same initial or a known nickname). Several candidates are narrowed
  to an identical first name; otherwise the resident is left Ambiguous for the user to resolve. Matches are
  graded Exact / Probable / Ambiguous / Unmatched, and every one can be reviewed and overridden.

## 4. Program analyses (`history.py`, `stats.py`)
- **Graduating class** = exam year + 4 − PGY.
- **By level**: per PGY × exam year — n, mean % correct, mean/median percentile, % ≥ 50th, % < 35th,
  % at/above the Low-risk cutoff. Different residents fill each cell.
- **Same-resident change**: last year → this year percentile change, Wilcoxon signed-rank test per PGY level.
- **MKSAP and the next ITE** (residents with both years of ITE):
  - Spearman correlations of questions answered with current % correct, with gain, and with *prior* % correct.
    The last one checks whether stronger residents simply do more questions.
  - OLS: `current % correct ~ prior % correct + PGY + log(1 + questions)`. The volume effect is reported per
    doubling (β × ln 2) and for 100 → 800 questions (β × ln 8), with R² with and without volume. It is repeated
    with MKSAP accuracy and with percentile as the outcome.
  - Thirds of MKSAP volume within each PGY. Ties are broken by row order, so with tied counts the split can
    differ slightly between runs on reordered files.
  - **Interpretation**: observational and confounded (motivation, rotations, prior knowledge), with small samples.
    The MKSAP snapshot may post-date the ITE, and MKSAP editions reset question counts.

## 5. Item-level gaps (`pdf_reports.py`)
From the ACP Program Performance Report, gap = program % correct − national % correct, per item and PGY group.
**Red**: All-PGY gap ≤ −10 points. **Yellow** (not red): any single-PGY gap ≤ −20 points. In a small program
one resident moves a single-PGY percentage by several points, so treat flags as prompts for review, not findings.

## 6. Resident self-analysis (`individual.py`)
Content areas are ranked by the resident's percentile (not % correct, since area difficulty differs).
Strength ≥ 60th percentile; Focus < 35th, or the two weakest areas if none fall below 35th. Missed objectives
are grouped by area as printed in the ACP report. The ITE-area → MKSAP-section map is provisional.

## Intended use
ACP describes the IM-ITE as intended solely as an educational program. These analyses help residents and
programs find knowledge gaps and target support. Do not use them for promotion, remediation or employment
decisions, or as a substitute for clinical competency assessment.
