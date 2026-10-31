# R mirror of ite_core/nomogram.py (the spec). Every result here is checked against
# tests/fixtures/nomogram_parity.json, which the pytest suite also checks. Change the Python
# first, regenerate the fixture, then match it here and bump SPEC_VERSION.

#' Nomogram constants
#'
#' `NOMOGRAM`: logistic coefficients (`b0`, `b1`) per PGY level, a fit to anchor
#' points read from McDonald et al. (2020). `SPEC_VERSION`: version of the Python
#' spec this package mirrors. `DEFAULT_CUTOFFS`: High below 50%, Intermediate
#' 50-90%, Low at 90% and above. `TIER_LABEL` / `TIER_ACTION`: display text per tier.
#'
#' @name nomogram_constants
#' @export
NOMOGRAM <- list(
  `1` = c(b0 = -7.0641,  b1 = 0.1811),
  `2` = c(b0 = -8.1445,  b1 = 0.1733),
  `3` = c(b0 = -11.9491, b1 = 0.2173)
)

#' @rdname nomogram_constants
#' @export
SPEC_VERSION <- "1"

#' @rdname nomogram_constants
#' @export
DEFAULT_CUTOFFS <- c(0.50, 0.90)

#' @rdname nomogram_constants
#' @export
TIER_LABEL <- c(High = "High risk", Intermediate = "Intermediate risk", Low = "Low risk")

#' @rdname nomogram_constants
#' @export
TIER_ACTION <- c(
  High         = "intervention recommended",
  Intermediate = "targeted board prep recommended",
  Low          = "continue current preparation"
)

TIER_ORDER <- c(Low = 0L, Intermediate = 1L, High = 2L)
DISPLAY_STEP <- 5L

# Python: max(1, min(3, int(pgy))) -- truncate toward zero, then clamp.
.pgy_key <- function(pgy) {
  k <- suppressWarnings(as.integer(as.numeric(as.character(pgy))))
  pmax(1L, pmin(3L, k))
}

.coef <- function(k, which) {
  vapply(k, function(i) if (is.na(i)) NA_real_ else NOMOGRAM[[as.character(i)]][[which]], numeric(1))
}

#' Estimated chance of passing ABIM
#'
#' P(pass) = 1 / (1 + exp(-(b0 + b1 * pct))), one curve per PGY level.
#'
#' @param pct Numeric. ITE percent correct (0-100).
#' @param pgy PGY level. Truncated to an integer, then clamped to 1-3.
#' @return Numeric probability (0-1), `NA` where either input is missing. Vectorised.
#' @export
pass_prob <- function(pct, pgy) {
  pct <- suppressWarnings(as.numeric(pct))
  if (length(pct) == 0 || length(pgy) == 0) return(numeric(0))
  k <- .pgy_key(pgy)
  n <- max(length(pct), length(k))
  pct <- rep_len(pct, n)
  k <- rep_len(k, n)
  1 / (1 + exp(-(.coef(k, "b0") + .coef(k, "b1") * pct)))
}

#' Percent correct needed to reach a probability
#'
#' Inverse of [pass_prob()]. `prob` of exactly 0 or 1 gives `-Inf` / `Inf`
#' (the Python spec raises an error there).
#'
#' @param prob Numeric probability.
#' @inheritParams pass_prob
#' @export
pct_for_prob <- function(prob, pgy) {
  k <- .pgy_key(pgy)
  (log(prob / (1 - prob)) - .coef(k, "b0")) / .coef(k, "b1")
}

#' Risk tier of failing ABIM
#'
#' @param prob Numeric probability from [pass_prob()].
#' @param cutoffs Length-2 numeric: High below `cutoffs[1]`, Low at or above
#'   `cutoffs[2]`. Cutoffs are a program choice.
#' @return `"High"`, `"Intermediate"` or `"Low"`; `NA` where `prob` is missing.
#' @export
risk_tier <- function(prob, cutoffs = DEFAULT_CUTOFFS) {
  stopifnot(length(cutoffs) == 2)
  prob <- as.numeric(prob)
  out <- ifelse(prob < cutoffs[1], "High", ifelse(prob < cutoffs[2], "Intermediate", "Low"))
  out <- as.character(out)
  out[is.na(prob)] <- NA_character_
  out
}

.check_tiers <- function(x) {
  bad <- !is.na(x) & !x %in% names(TIER_ORDER)
  if (any(bad)) stop("Unknown risk tier: ", paste(unique(x[bad]), collapse = ", "), call. = FALSE)
}

#' Compare two risk tiers
#'
#' @param prev,cur Risk tiers (see [risk_tier()]).
#' @return `"No prior"`, `"No current"`, `"Worsened"`, `"Improved"` or `"Stable"`. Vectorised.
#' @export
tier_change <- function(prev, cur) {
  if (length(prev) == 0 || length(cur) == 0) return(character(0))
  n <- max(length(prev), length(cur))
  prev <- rep_len(as.character(prev), n)
  cur <- rep_len(as.character(cur), n)
  .check_tiers(prev)
  .check_tiers(cur)
  d <- unname(TIER_ORDER[cur] - TIER_ORDER[prev])
  out <- ifelse(d > 0, "Worsened", ifelse(d < 0, "Improved", "Stable"))
  out[is.na(cur)] <- "No current"
  out[is.na(prev)] <- "No prior"
  out
}

#' How an estimated probability is shown
#'
#' Rounded DOWN to the nearest 5% and marked approximate (`"~85%"`), with
#' "greater-or-equal 95%" and `"<5%"` at the ends and an em dash when missing. Rounding
#' down keeps the label consistent with the tier: 89.8% reads `"~85%"`, never
#' `"90%"` next to an Intermediate badge.
#'
#' @param p Numeric probability.
#' @export
prob_label <- function(p) {
  p <- as.numeric(p)
  v <- floor(100 * p + 1e-9)
  out <- paste0("~", DISPLAY_STEP * (v %/% DISPLAY_STEP), "%")
  out[which(v < DISPLAY_STEP)] <- "<5%"
  out[which(v >= 95)] <- "\u226595%"
  out[is.na(p)] <- "\u2014"
  out
}

# Named scores (names = PGY) -> data frame sorted by PGY. NULL values become NA.
.as_scores <- function(scores, keep_na = FALSE) {
  if (is.null(scores) || length(scores) == 0) return(data.frame(pgy = integer(0), pct = numeric(0)))
  nm <- names(scores)
  if (is.null(nm) || any(!nzchar(nm))) {
    stop("`scores` must be named by PGY, e.g. c(`1` = 62, `2` = 65).", call. = FALSE)
  }
  vals <- vapply(scores, function(v) {
    if (is.null(v) || length(v) == 0) NA_real_ else suppressWarnings(as.numeric(v[[1]]))
  }, numeric(1))
  pgy <- as.integer(as.numeric(nm))
  o <- order(pgy)
  out <- data.frame(pgy = pgy[o], pct = unname(vals[o]))
  if (!keep_na) out <- out[!is.na(out$pct), , drop = FALSE]
  out
}

#' Per-PGY trajectory
#'
#' One row per PGY with the estimate and tier, plus the percent correct that
#' would have reached the Low-risk tier (explains why a tier can worsen with an
#' unchanged score: each PGY curve is steeper).
#'
#' @param scores Named numeric vector or list, names = PGY, e.g. `c(`1` = 62, `2` = 65)`.
#' @inheritParams risk_tier
#' @return Tibble: `pgy, pct_correct, pass_prob, risk_tier, pct_needed_low, delta_pct, tier_change`.
#' @export
trajectory <- function(scores, cutoffs = DEFAULT_CUTOFFS) {
  s <- .as_scores(scores, keep_na = TRUE)
  p <- pass_prob(s$pct, s$pgy)
  tier <- risk_tier(p, cutoffs)
  tibble::tibble(
    pgy            = s$pgy,
    pct_correct    = s$pct,
    pass_prob      = p,
    risk_tier      = tier,
    pct_needed_low = round(pct_for_prob(rep_len(cutoffs[2], nrow(s)), s$pgy), 1),
    delta_pct      = c(NA_real_, diff(s$pct))[seq_len(nrow(s))],
    tier_change    = tier_change(c(NA_character_, utils::head(tier, -1)), tier)[seq_len(nrow(s))]
  )
}

#' Nomogram curves for plotting
#'
#' @param step,lo,hi Percent-correct grid (same points as numpy `arange(lo, hi + step/2, step)`).
#' @return Long tibble: `pgy, pct_correct, pass_prob`.
#' @export
curves <- function(step = 1, lo = 20, hi = 100) {
  n <- ceiling((hi + step / 2 - lo) / step)
  x <- lo + (seq_len(n) - 1) * step
  pgy <- rep(1:3, each = n)
  tibble::tibble(pgy = pgy, pct_correct = rep(x, 3), pass_prob = pass_prob(rep(x, 3), pgy))
}
