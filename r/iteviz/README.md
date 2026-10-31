# iteviz

R mirror of this repo's nomogram (`ite_core/nomogram.py`): the estimated chance of passing the ABIM
certification exam from IM-ITE percent correct and PGY level, approximating the published curves of
McDonald et al., *Acad Med* 2020 ([doi](https://doi.org/10.1097/ACM.0000000000003382)). It is an
approximation from 2014–18 cohorts — a guide, not a precise prediction.

```r
renv::install("fbuckhold3/im-ite-analyzer/r/iteviz")   # subdirectory of this repo

iteviz::pass_prob(65, 3)              # 0.898
iteviz::risk_tier(0.898)              # "Intermediate"  (default cutoffs 50% / 90%)
iteviz::prob_label(0.898)             # "~85%"  (rounded down to 5%; never show a raw %)
iteviz::trajectory(c(`1` = 65, `2` = 65, `3` = 65))
```

Display helpers (htmltools + plotly; use inside `renderUI()` / `renderPlotly()`):
`ite_estimate_card()`, `ite_year_chips()`, `ite_tier_badge()`, `ite_nomogram_plot()`, `ite_citation()`.
Colours follow roundsui CSS variables when present, with roundsui's values as fallback.

## Parity with the Python spec

Python is the spec. `scripts/make_parity_fixture.py` writes `tests/fixtures/nomogram_parity.json` from
`nomogram.py`; pytest (`tests/test_nomogram_parity.py`) and testthat (`r/iteviz/tests/testthat/test-parity.R`)
both check it. To change the math, cutoffs, tier names or labels:

1. Edit `ite_core/nomogram.py` and bump `SPEC_VERSION`.
2. `.venv/bin/python scripts/make_parity_fixture.py`
3. Update `r/iteviz/R/nomogram.R` (including `SPEC_VERSION`) until `devtools::test("r/iteviz")` passes.
