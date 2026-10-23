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

**Watch list (Board pass tab).** PGY-2 and PGY-3 residents whose current estimate is below the Low-risk cutoff,
or whose tier worsened since the prior exam year. PGY-1s are excluded because the PGY-1 curve places almost
everyone in Low risk. "Points from Low risk" = current % correct minus the % correct at which the resident's PGY
curve reaches the Low-risk cutoff.

### Projected class pass rate (`board.py`)
For each current class (PGY level), the projected ABIM pass rate is the mean of the residents' estimated pass
probabilities — the expected share passing if the estimates hold. The "likely" range is the central 80% of the exact
distribution of the number who pass (Poisson-binomial, from each resident's probability), assuming results are
independent and the estimates exact. It therefore reflects chance only, not uncertainty in the approximated
nomogram, and PGY-1 projections (intern ITE, shallow curve) are the least informative. Residents without a
current-year score are excluded and counted. De-identified summary: rate only (the range would reveal how many are
below Low risk), and classes under 5 suppressed.

### Board outcomes: ABIM results vs ITE prediction (`abim.py`)
ABIM's program PDFs are read as text: the Examination Results report (name + Pass/Fail per first-time taker) and the
Program Data Report (adds the standardized score or "Withheld by Candidate", the program and all-programs pass
rates, and the passing score; its content-area chart is an image and is not read). If both cover the same exam year,
the Program Data Report is used. ABIM reports carry no ACP ID, so takers are linked to residents who finished
training in the exam year or the year before by name, with the MKSAP rules (exact surname or shared surname token
plus first-name agreement); unmatched takers can be linked by hand. "Predicted" is the estimated pass probability
from each graduate's last ITE before graduating (PGY-3 when available) and is compared with the observed pass rate
among linked takers, per exam year and by predicted risk tier. MKSAP volume / accuracy come from the current export
(auto-matched exact/probable only) and may include activity after the exam. Cohorts are small, so this is
descriptive: a check on the estimate, not a measure of the program. Shown in the app and the confidential PD report
only; the anonymous table has no names; never in the de-identified summary.

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
  graded Exact / Probable / Ambiguous / Unmatched (Manual once a user links an account by hand), and every one
  can be reviewed and overridden. In the app, residents needing review are listed first, each with a suggested
  account (same surname first, then same initial); the reviewer confirms, picks another account, or marks
  "No MKSAP account" (residents are not required to have one). Picking an account that is already linked moves it,
  and the resident it came from returns to the review list.

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
  - **Export types**: MKSAP Digital offers a members overview (per-person totals) and a full detail export
    (per person × question). They count the bank differently (2026: 2,375 vs 3,156), so "% of the bank" is only
    comparable within one export type; on the 2026 data every ITE analysis agreed between the two
    (+2.2 points per doubling and R² 0.59 → 0.69 with either). Section coverage needs the full detail.
  - **Minimum sample**: the regressions are not run with fewer than 10 residents who have both ITE years and an
    MKSAP account; results with p ≥ .05 are reported as not statistically clear.
  - **Section table**: % attempted = questions answered ÷ (section size × residents in the class); accuracy =
    correct ÷ answered. Section names are inferred from MKSAP's two-letter codes.
  - **Interpretation**: observational and confounded (motivation, rotations, prior knowledge), with small samples.
    The MKSAP snapshot may post-date the ITE, and MKSAP editions reset question counts.

## 5. Item-level gaps (`pdf_reports.py`)
From the ACP Program Performance Report, gap = program % correct − national % correct, per item and PGY group.
**Red**: All-PGY gap ≤ −10 points. **Yellow** (not red): any single-PGY gap ≤ −20 points. In a small program
one resident moves a single-PGY percentage by several points, so treat flags as prompts for review, not findings.

## 5b. Downloadable reports
- **Identified PD report**: everything shown in the app, including names and the watch list. Confidential.
- **De-identified program summary**: aggregates only — no names or IDs, no per-person tiers, unlabeled chart
  points. Counts of 1–4 are shown as "<5" and group means from fewer than 5 residents are suppressed. Because
  group sizes are visible elsewhere in the report, tiers are collapsed to *Below Low risk* vs *Low risk*, and Low
  is shown as a range (e.g. "≥6") whenever Below Low is suppressed; the tier-change line is omitted if any change
  count is under 5. Residual risk: unlabeled scatter points can still be recognised by someone who knows an
  individual's scores — review before sharing outside the program.

- **All data (.xlsx)**: every table the app computes, row-level and identified; never offered de-identified,
  because resident-level rows can be re-identified even without names.

## 6. Resident self-analysis (`individual.py`)
Content areas are ranked by the resident's percentile (not % correct, since area difficulty differs).
Areas fall into three bands: 50th percentile and above, 25th–49th, and below 25th (no fallback: if no area is
below the 25th, that band is empty). Missed objectives are grouped by area as printed in the ACP report.

**Next-year targets.** For PGY-1 and PGY-2, the % correct at which each later PGY curve reaches the Low-risk cutoff
(90% by default) is shown on the curve; none for PGY-3.

**Biggest misses and notable wins.** When the resident also uploads the Program Performance Report for the same
exam year, each item in their report is matched to the program report by content area + objective text, and the
national % correct at the resident's PGY level is attached. Misses are ranked by how many residents nationally got
the item right (missing an item most people answer correctly is the largest gap; top 20); wins are items the
resident answered correctly that few residents nationally did (top 10). Any item not listed as missed in the
resident's report is counted as answered correctly. Reports from different exam years are not
combined. The ITE-area → MKSAP-section map is provisional.

## Intended use
ACP describes the IM-ITE as intended solely as an educational program. These analyses help residents and
programs find knowledge gaps and target support. Do not use them for promotion, remediation or employment
decisions, or as a substitute for clinical competency assessment.
