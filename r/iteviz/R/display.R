# Display helpers: the im-ite-analyzer visual (modules/common.py tier_badge, modules/resident.py estimate
# card, modules/plots.py nomogram_figure) in roundsui colours. htmltools + plotly only, no Shiny, so any
# app shell can use them inside renderUI() / renderPlotly().

# Okabe-Ito: distinguishable with common colour-vision deficiencies. Encodes PGY year, not risk.
PGY_COLOR <- c(`1` = "#0072B2", `2` = "#E69F00", `3` = "#009E73")

TIER_TOKEN <- c(High = "danger", Intermediate = "warning", Low = "success")

# Fallbacks mirror roundsui::roundsui_colors(); live values are used when roundsui is installed.
.colors <- function() {
  cols <- list(
    ink = "#13161F", ink_muted = "#5B6472",
    danger = "#D33A2C", warning = "#C2760A", success = "#16A34A"
  )
  if (requireNamespace("roundsui", quietly = TRUE)) {
    live <- tryCatch(roundsui::roundsui_colors(), error = function(e) NULL)
    if (is.list(live)) cols[intersect(names(cols), names(live))] <- live[intersect(names(cols), names(live))]
  }
  cols
}

.rgba <- function(hex, alpha) {
  v <- grDevices::col2rgb(hex)[, 1]
  sprintf("rgba(%d, %d, %d, %.2f)", v[1], v[2], v[3], alpha)
}

.fmt_pct <- function(x) paste0(format(round(x, 1), trim = TRUE), "%")

#' iteviz stylesheet
#'
#' An `htmltools::htmlDependency` for the badge, card and chip styles. The
#' helpers below attach it themselves; call this only to load it up front.
#' Colours come from roundsui CSS variables, with roundsui's values as fallback.
#'
#' @export
ite_dependency <- function() {
  htmltools::htmlDependency(
    name = "iteviz",
    version = as.character(utils::packageVersion("iteviz")),
    src = "www",
    package = "iteviz",
    stylesheet = "iteviz.css"
  )
}

.with_dep <- function(tag) htmltools::attachDependencies(tag, ite_dependency(), append = TRUE)

#' Risk tier badge
#'
#' A pill reading "High risk" / "Intermediate risk" / "Low risk". The tier
#' colour is always paired with the text.
#'
#' @param tier A tier from [risk_tier()], or `NA`.
#' @export
ite_tier_badge <- function(tier) {
  tier <- as.character(tier)[1]
  tag <- if (is.na(tier) || !tier %in% names(TIER_LABEL)) {
    htmltools::span(class = "iteviz-tier iteviz-tier--none", "\u2014")
  } else {
    htmltools::span(class = paste0("iteviz-tier iteviz-tier--", tolower(tier)), TIER_LABEL[[tier]])
  }
  .with_dep(tag)
}

#' Source line for the estimates
#'
#' The citation shown wherever estimates appear (McDonald et al. 2020).
#'
#' @export
ite_citation <- function() {
  .with_dep(htmltools::div(
    class = "iteviz-citation",
    "Estimates approximate McDonald et al., ", htmltools::tags$em("Acad Med"), " 2020 (",
    htmltools::a("doi", href = "https://doi.org/10.1097/ACM.0000000000003382", target = "_blank", rel = "noopener",
                 .noWS = "outside"),
    "); 2014\u201318 cohorts, shown to the nearest 5%."
  ))
}

#' Estimate card
#'
#' Headline estimate (`"~85%"`), tier badge with its recommended action, and the
#' ITE score it came from.
#'
#' @param pct ITE percent correct.
#' @param pgy PGY level of that exam.
#' @param compact Smaller layout for tight panels.
#' @param citation Include [ite_citation()] under the card.
#' @inheritParams risk_tier
#' @return A tag, or `NULL` when `pct` or `pgy` is missing (callers show their own empty state).
#' @export
ite_estimate_card <- function(pct, pgy, cutoffs = DEFAULT_CUTOFFS, compact = FALSE, citation = TRUE) {
  p <- pass_prob(pct, pgy)
  if (length(p) == 0 || is.na(p[1])) return(NULL)
  p <- p[1]
  tier <- risk_tier(p, cutoffs)
  card <- htmltools::div(
    class = paste0("iteviz-card iteviz-card--", tolower(tier), if (compact) " iteviz-card--compact"),
    htmltools::div(
      class = "iteviz-card__estimate",
      htmltools::div(class = "iteviz-card__number", prob_label(p)),
      htmltools::div(class = "iteviz-card__hint", "estimated chance of passing ABIM on the first attempt")
    ),
    htmltools::div(
      class = "iteviz-card__detail",
      htmltools::div(ite_tier_badge(tier), htmltools::span(class = "iteviz-card__action", TIER_ACTION[[tier]])),
      htmltools::div(class = "iteviz-card__stat", sprintf("PGY-%d ITE: %s correct", .pgy_key(pgy)[1], .fmt_pct(pct[1])))
    )
  )
  .with_dep(htmltools::tagList(card, if (citation) ite_citation()))
}

#' One chip per ITE year
#'
#' `PGY-1 . 62% . ~95% . Low risk` for every year with a score, oldest first.
#'
#' @param scores Named numeric vector or list, names = PGY, e.g. `c(`1` = 62, `2` = 65)`.
#' @inheritParams risk_tier
#' @return A tag, or `NULL` when there are no scores.
#' @export
ite_year_chips <- function(scores, cutoffs = DEFAULT_CUTOFFS) {
  s <- .as_scores(scores)
  if (nrow(s) == 0) return(NULL)
  p <- pass_prob(s$pct, s$pgy)
  tier <- risk_tier(p, cutoffs)
  chips <- lapply(seq_len(nrow(s)), function(i) {
    htmltools::span(
      class = paste0("iteviz-chip iteviz-chip--", tolower(tier[i])),
      paste(sprintf("PGY-%d", s$pgy[i]), .fmt_pct(s$pct[i]), prob_label(p[i]), TIER_LABEL[[tier[i]]], sep = " \u00b7 ")
    )
  })
  .with_dep(htmltools::div(class = "iteviz-chips", chips))
}

#' Nomogram chart
#'
#' The three PGY curves on tier bands, with the resident's scores as points
#' coloured by PGY. Hover reads `PGY-2: 65% correct -> ~95%`. Plotly's cloud
#' share buttons are removed (they upload chart data to a third party).
#'
#' @param scores Optional named scores (see [ite_year_chips()]).
#' @param height Optional plot height in pixels.
#' @inheritParams risk_tier
#' @return A plotly htmlwidget.
#' @export
ite_nomogram_plot <- function(scores = NULL, cutoffs = DEFAULT_CUTOFFS, height = NULL) {
  cols <- .colors()
  cv <- curves(step = 0.5, lo = 30, hi = 95)
  fig <- plotly::plot_ly(height = height)
  for (p in 1:3) {
    d <- cv[cv$pgy == p, ]
    fig <- plotly::add_trace(
      fig, x = d$pct_correct, y = d$pass_prob, type = "scatter", mode = "lines",
      name = paste0("PGY-", p), line = list(color = PGY_COLOR[[p]], width = 2.5),
      hovertemplate = paste0("PGY-", p, " curve at %{x:.0f}% correct<extra></extra>")
    )
  }

  s <- .as_scores(scores)
  if (nrow(s) > 0) {
    prob <- pass_prob(s$pct, s$pgy)
    fig <- plotly::add_trace(
      fig, x = s$pct, y = prob, type = "scatter", mode = "markers", showlegend = FALSE,
      text = sprintf("PGY-%d: %.0f%% correct \u2192 %s", s$pgy, s$pct, prob_label(prob)),
      hovertemplate = "%{text}<extra></extra>",
      marker = list(size = 13, color = unname(PGY_COLOR[as.character(.pgy_key(s$pgy))]),
                    line = list(color = "#1a1a1a", width = 1.5))
    )
  }

  spans <- list(High = c(0, cutoffs[1]), Intermediate = cutoffs, Low = c(cutoffs[2], 1.02))
  shapes <- lapply(names(spans), function(t) list(
    type = "rect", xref = "paper", x0 = 0, x1 = 1, y0 = spans[[t]][1], y1 = spans[[t]][2],
    fillcolor = .rgba(cols[[TIER_TOKEN[[t]]]], 0.10), line = list(width = 0), layer = "below"
  ))
  # Curves start low on the left and are near 100% on the right, so the High and
  # Intermediate labels sit at the right edge and the Low label at the left.
  annotations <- lapply(names(spans), function(t) {
    left <- t == "Low"
    list(
      xref = "paper", x = if (left) 0.01 else 0.99, xanchor = if (left) "left" else "right",
      y = (spans[[t]][1] + min(spans[[t]][2], 1)) / 2, text = TIER_LABEL[[t]],
      showarrow = FALSE, font = list(size = 11, color = cols$ink_muted)
    )
  })

  fig |>
    plotly::layout(
      shapes = shapes, annotations = annotations,
      xaxis = list(title = "ITE percent correct", range = c(30, 95), dtick = 10, ticksuffix = "%"),
      yaxis = list(title = "Estimated probability of passing ABIM", range = c(0, 1.02), tickformat = ".0%"),
      legend = list(orientation = "h", yanchor = "bottom", y = 0.02, xanchor = "right", x = 0.99),
      margin = list(l = 55, r = 20, t = 10, b = 50),
      hovermode = "closest",
      paper_bgcolor = "rgba(0,0,0,0)", plot_bgcolor = "rgba(0,0,0,0)",
      font = list(color = cols$ink)
    ) |>
    plotly::config(
      displaylogo = FALSE,
      modeBarButtonsToRemove = c("sendDataToCloud", "editInChartStudio", "lasso2d", "select2d")
    )
}
