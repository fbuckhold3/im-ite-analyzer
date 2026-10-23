"""Home: three entry cards (quick estimate, resident report, program analysis) that open the right tab, then a
step-by-step guide for residents and for program directors."""

from __future__ import annotations

from shiny import reactive, ui

from .common import tier_badge

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

# (title, detail, files as (label, optional)) per step
RESIDENT_STEPS = [
    (
        "Get your score report",
        "Your program receives an Examinee Performance Report PDF for each ITE you take. Ask for this year's and, "
        "if you have them, earlier years' to see your trajectory.",
        [("Examinee Performance Report · PDF", False)],
    ),
    (
        "Optional: add the program report",
        "Your program's Performance Report holds only program and national totals. With it, your missed questions "
        "are ranked against how residents did nationally.",
        [("Program Performance Report · PDF", True)],
    ),
    (
        "Upload on Resident report",
        "You'll see your estimated chance of passing ABIM, the score to aim for next year, content areas in three "
        "color bands, and your biggest misses and wins.",
        [],
    ),
    (
        "Keep or share it",
        "Download a PDF of the same analysis to keep, or to bring to your coach or program director.",
        [],
    ),
]

PD_STEPS = [
    (
        "Gather your files",
        "The ACP roster for each exam year you have — more years means trends and class tracking. The other two "
        "files are optional and each adds its own analysis.",
        [
            ("ACP roster · .xlsx/.csv, one per year", False),
            ("Program Performance Report · PDF", True),
            ("MKSAP Members export · .csv", True),
            ("ABIM exam results · PDF", True),
        ],
    ),
    (
        "Drop them all on Upload & Align",
        "One drop zone takes every file; the app works out what each one is, ticks it off a checklist, and suggests "
        "what to add next.",
        [],
    ),
    (
        "Review MKSAP matches",
        "MKSAP accounts are linked to residents by name. Confirm the suggestions, pick a different account, or mark "
        "“No MKSAP account” — not every resident has one.",
        [],
    ),
    (
        "Explore, then share",
        "Pick a section box: start with Board pass for the watch list, then trends, classes and item gaps. "
        "Reports builds a confidential PD report, a de-identified summary for committees, and one Excel workbook "
        "with all data.",
        [],
    ),
]

# What each PD file unlocks: (file, optional, tabs)
UNLOCKS = [
    ("ACP rosters", False, ["Trends by level", "Classes", "Year over year", "Board pass", "Reports"]),
    ("MKSAP export", True, ["MKSAP"]),
    ("Program Performance Report", True, ["Item gaps"]),
    ("ABIM exam results", True, ["Board outcomes"]),
]


def _steps(steps, tone):
    return ui.tags.ol(
        *[
            ui.tags.li(
                ui.div(str(i), class_="step-num", aria_hidden="true"),
                ui.div(
                    ui.h4(title),
                    ui.p(detail),
                    ui.div(
                        *[
                            ui.span(label, ui.span("optional", class_="file-opt") if opt else None, class_="file-pill")
                            for label, opt in files
                        ],
                        class_="file-pills",
                    )
                    if files
                    else None,
                    class_="step-body",
                ),
                class_="step",
            )
            for i, (title, detail, files) in enumerate(steps, start=1)
        ],
        class_=f"steps steps-{tone}",
    )


def _unlocks():
    return ui.div(
        ui.h4("What each file unlocks"),
        ui.div(
            *[
                ui.div(
                    ui.div(
                        ui.span(name, class_="unlock-file-name"),
                        ui.span("optional", class_="file-opt") if opt else None,
                        class_="unlock-file",
                    ),
                    ui.div("→", class_="unlock-arrow", aria_hidden="true"),
                    ui.div(*[ui.span(t, class_="unlock-tab") for t in tabs], class_="unlock-tabs"),
                    class_="unlock-row",
                )
                for name, opt, tabs in UNLOCKS
            ],
            class_="unlock-grid",
        ),
        class_="unlocks",
    )


def _resident_preview():
    """A small, clearly labeled illustration of the resident results (invented example values)."""
    bands = [
        ("band-ex-high", "50th percentile and above", "Cardiology · Nephrology · Endocrinology"),
        ("band-ex-mid", "25th–49th percentile", "Pulmonary · Gastroenterology"),
        ("band-ex-low", "Below 25th percentile", "Rheumatology · Infectious Diseases"),
    ]
    return ui.div(
        ui.h4("What you'll see"),
        ui.p("Example — not real data", class_="example-tag"),
        ui.div(
            ui.div(
                ui.span("PGY-1 · 48% correct · 83% estimated pass", class_="ex-score"),
                tier_badge("Intermediate"),
                class_="ex-row",
            ),
            ui.p("To reach Low risk next year (PGY-2), aim for about 60% correct.", class_="ex-target"),
            *[
                ui.div(ui.span(label, class_="ex-band-label"), ui.span(areas), class_=f"ex-band {cls}")
                for cls, label, areas in bands
            ],
            class_="ex-card",
            aria_hidden="true",
        ),
        class_="resident-preview",
    )


def _privacy_flow():
    stages = [
        ("Your files", "score reports, rosters, MKSAP export"),
        ("Analyzed in your session", "in memory, only while this page is open"),
        ("Your results", "charts, PDFs, reports, Excel"),
    ]
    parts = []
    for i, (title, sub) in enumerate(stages):
        if i:
            parts.append(ui.div("→", class_="flow-arrow", aria_hidden="true"))
        parts.append(ui.div(ui.strong(title), ui.span(sub), class_="flow-stage"))
    return ui.div(
        ui.div(*parts, class_="flow"),
        ui.p("Nothing is saved on the server and nothing is shared. Close the page and the data is gone."),
        class_="privacy-flow",
    )


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
    guide = ui.div(
        ui.h2("How to use it", id="how-to"),
        ui.div(
            ui.tags.section(
                ui.h3("If you're a resident"),
                ui.p("About five minutes, with one PDF.", class_="path-lede"),
                _steps(RESIDENT_STEPS, "resident"),
                _resident_preview(),
                ui.div(
                    ui.input_action_button("go_me2", "Analyze my report", class_="btn-primary"),
                    ui.input_action_button("go_calc2", "Just my score? Quick estimate", class_="btn-link"),
                    class_="path-actions",
                ),
                class_="path path-resident",
                aria_label="Steps for residents",
            ),
            ui.tags.section(
                ui.h3("If you're a program director"),
                ui.p("Rosters for every year you have; the rest is optional.", class_="path-lede"),
                _steps(PD_STEPS, "pd"),
                _unlocks(),
                ui.div(
                    ui.input_action_button("go_program2", "Analyze my program", class_="btn-primary"),
                    ui.span("or load the demo data on Upload & Align to look around first.", class_="hint"),
                    class_="path-actions",
                ),
                class_="path path-pd",
                aria_label="Steps for program directors",
            ),
            class_="paths",
        ),
        _privacy_flow(),
        class_="home-guide",
        aria_labelledby="how-to",
    )
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
            "Not sure where to start? See ",
            ui.tags.a("how to use it", href="#how-to"),
            " below, or try the demo data on Program analysis or the sample report on Resident report.",
            class_="hint text-center",
        ),
        guide,
    )


# button id -> tab; the guide's buttons repeat the cards'
TARGETS = {c["id"]: c["target"] for c in CARDS} | {"go_me2": "me", "go_calc2": "calc", "go_program2": "program"}


def home_server(input, session):
    for button, target in TARGETS.items():

        def make(button, target):
            @reactive.effect
            @reactive.event(input[button])
            def _go():
                ui.update_navset("nav", selected=target)

        make(button, target)
