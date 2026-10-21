"""Home: three entry cards (quick estimate, resident report, program analysis) that open the right tab."""

from __future__ import annotations

from shiny import reactive, ui

CARDS = [
    dict(
        id="go_calc",
        target="calc",
        icon="①",
        title="Quick estimate",
        who="Anyone with a score",
        bring="Your ITE percent correct and PGY level (one exam or all three years).",
        get="Estimated chance of passing ABIM, risk tier, and the score you need next year to stay in Low risk.",
        button="Estimate my chance",
    ),
    dict(
        id="go_me",
        target="me",
        icon="②",
        title="Resident report",
        who="Residents (and PDs, one resident at a time)",
        bring="Your ACP Examinee Performance Report (PDF). Optional: your program's Performance Report.",
        get="Pass estimate with next-year targets, content areas by color, your biggest misses and wins vs "
        "national, and a PDF to keep.",
        button="Analyze my report",
    ),
    dict(
        id="go_program",
        target="program",
        icon="③",
        title="Program analysis",
        who="Program directors",
        bring="ACP roster files (any years), MKSAP program export, Program Performance Report.",
        get="Trends by level and class, board-pass watch list, MKSAP impact, item gaps, reports and all data.",
        button="Analyze my program",
    ),
]


def home_ui():
    cards = [
        ui.div(
            ui.div(c["icon"], class_="home-icon", aria_hidden="true"),
            ui.h3(c["title"]),
            ui.p(c["who"], class_="home-who"),
            ui.tags.dl(ui.tags.dt("You bring"), ui.tags.dd(c["bring"]), ui.tags.dt("You get"), ui.tags.dd(c["get"])),
            ui.input_action_button(c["id"], c["button"], class_="btn-primary w-100"),
            class_="home-card",
        )
        for c in CARDS
    ]
    return ui.div(
        ui.div(
            ui.h2("Make sense of the ACP In-Training Exam"),
            ui.p(
                "Estimate the chance of passing ABIM, find knowledge gaps, and follow residents and classes over "
                "time. Files stay in your browser session — nothing is stored."
            ),
            class_="home-hero",
        ),
        ui.div(*cards, class_="home-grid"),
        ui.p(
            "Not sure where to start? Try the demo data on Program analysis or the sample report on Resident report.",
            class_="hint text-center",
        ),
    )


def home_server(input, session):
    for c in CARDS:

        def make(card):
            @reactive.effect
            @reactive.event(input[card["id"]])
            def _go():
                ui.update_navs("nav", selected=card["target"])

        make(c)
