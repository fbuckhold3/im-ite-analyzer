render <- function(x) as.character(htmltools::renderTags(x)$html)

test_that("tier badge shows the tier name with its class", {
  expect_match(render(ite_tier_badge("Intermediate")), "iteviz-tier--intermediate")
  expect_match(render(ite_tier_badge("Intermediate")), "Intermediate risk")
  expect_match(render(ite_tier_badge(NA)), "iteviz-tier--none")
})

test_that("badge carries the stylesheet", {
  deps <- htmltools::findDependencies(ite_tier_badge("Low"))
  expect_true(any(vapply(deps, function(d) d$name == "iteviz", logical(1))))
})

test_that("estimate card headlines the rounded estimate", {
  html <- render(ite_estimate_card(65, 3))
  expect_match(html, "~85%", fixed = TRUE)
  expect_match(html, "Intermediate risk")
  expect_match(html, "PGY-3 ITE: 65% correct", fixed = TRUE)
  expect_match(html, "McDonald")
  expect_false(grepl("McDonald", render(ite_estimate_card(65, 3, citation = FALSE))))
  expect_null(ite_estimate_card(NA, 2))
})

test_that("year chips: one per scored year, oldest first", {
  html <- render(ite_year_chips(list(`2` = 65, `1` = 62, `3` = NULL)))
  expect_equal(lengths(regmatches(html, gregexpr("iteviz-chip ", html))), 2)
  expect_lt(regexpr("PGY-1", html), regexpr("PGY-2", html))
  expect_null(ite_year_chips(c(`1` = NA)))
})

test_that("nomogram plot: 3 curves, scores, 3 bands, no cloud buttons", {
  fig <- plotly::plotly_build(ite_nomogram_plot(c(`1` = 60, `2` = 65)))
  expect_length(fig$x$data, 4)
  expect_length(fig$x$layout$shapes, 3)
  expect_true("sendDataToCloud" %in% fig$x$config$modeBarButtonsToRemove)
  expect_length(plotly::plotly_build(ite_nomogram_plot())$x$data, 3)
})

test_that("unnamed scores are rejected", {
  expect_error(trajectory(c(60, 65)), "named by PGY")
})
