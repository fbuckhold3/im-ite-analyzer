# Parity with ite_core/nomogram.py via the shared fixture at the analyzer repo root
# (tests/fixtures/nomogram_parity.json, also checked by pytest). Skipped when the
# package is tested outside a checkout of the analyzer repo.

fixture_path <- function() {
  testthat::test_path("..", "..", "..", "..", "tests", "fixtures", "nomogram_parity.json")
}

load_fixture <- function(simplify) {
  testthat::skip_if_not_installed("jsonlite")
  path <- fixture_path()
  testthat::skip_if_not(file.exists(path), "parity fixture not found (run inside the im-ite-analyzer checkout)")
  jsonlite::read_json(path, simplifyVector = simplify)
}

null_to_na <- function(x, na = NA) if (is.null(x)) na else x

test_that("spec version and constants match the Python spec", {
  fx <- load_fixture(TRUE)
  expect_identical(SPEC_VERSION, fx$spec_version)
  for (k in c("1", "2", "3")) {
    expect_equal(unname(NOMOGRAM[[k]]), fx$coefficients[[k]])
  }
  expect_equal(DEFAULT_CUTOFFS, fx$cutoffs)
  expect_equal(TIER_LABEL[c("High", "Intermediate", "Low")],
               unlist(fx$tier_label)[c("High", "Intermediate", "Low")])
})

test_that("pass_prob, tier and label match for every score/PGY case", {
  pc <- load_fixture(TRUE)$point_cases
  p <- pass_prob(pc$pct, pc$pgy)
  expect_equal(p, pc$prob, tolerance = 1e-12)
  expect_identical(risk_tier(p), pc$tier)
  expect_identical(prob_label(p), pc$label)
})

test_that("tier and label match at every boundary, straight from the probability", {
  pr <- load_fixture(TRUE)$prob_cases
  expect_identical(risk_tier(pr$prob), pr$tier)
  expect_identical(prob_label(pr$prob), pr$label)
})

test_that("custom cutoffs match", {
  for (case in load_fixture(FALSE)$custom_cutoff_cases) {
    expect_identical(risk_tier(case$prob, unlist(case$cutoffs)), case$tier)
  }
})

test_that("pct_for_prob matches", {
  pf <- load_fixture(TRUE)$pct_for_prob_cases
  expect_equal(pct_for_prob(pf$prob, pf$pgy), pf$pct, tolerance = 1e-12)
})

test_that("tier_change matches", {
  tc <- load_fixture(TRUE)$tier_change_cases
  expect_identical(tier_change(tc$prev, tc$cur), tc$out)
})

test_that("trajectory matches", {
  for (case in load_fixture(FALSE)$trajectory_cases) {
    got <- trajectory(case$scores)
    rows <- case$rows
    col <- function(name, na) vapply(rows, function(r) null_to_na(r[[name]], na), na)
    expect_identical(got$pgy, as.integer(col("pgy", NA_integer_)))
    expect_equal(got$pct_correct, col("pct_correct", NA_real_), tolerance = 1e-12)
    expect_equal(got$pass_prob, col("pass_prob", NA_real_), tolerance = 1e-12)
    expect_identical(got$risk_tier, col("risk_tier", NA_character_))
    expect_equal(got$pct_needed_low, col("pct_needed_low", NA_real_))
    expect_equal(got$delta_pct, col("delta_pct", NA_real_), tolerance = 1e-12)
    expect_identical(got$tier_change, col("tier_change", NA_character_))
  }
})

test_that("curves match", {
  cc <- load_fixture(TRUE)$curves_case
  got <- curves(step = cc$step, lo = cc$lo, hi = cc$hi)
  expect_identical(got$pgy, as.integer(cc$rows$pgy))
  expect_equal(got$pct_correct, cc$rows$pct_correct)
  expect_equal(got$pass_prob, cc$rows$pass_prob, tolerance = 1e-12)
  expect_identical(nrow(curves(step = 0.5, lo = 30, hi = 95)), as.integer(cc$n_rows_step_half_30_95))
})
