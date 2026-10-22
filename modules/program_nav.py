"""Program analysis navigation: a grid of section boxes instead of a row of tabs.

Each box names the section, says in a line what it shows, and is muted (still clickable) with a "needs …" note when
the file it depends on hasn't been added. The sections themselves live in a hidden navset (id "program_nav").
"""

from __future__ import annotations

from shiny import reactive, render, ui

# (value, title, what it shows, needs: None / "rosters" / "mksap" / "program")
SECTIONS = [
    ("upload", "Upload & Align", "Add files, check what was found, review MKSAP matches", None),
    ("board", "Board pass", "Pass estimates, risk tiers and the watch list", "rosters"),
    ("trends", "Trends by level", "Each PGY level across exam years", "rosters"),
    ("classes", "Classes", "Each graduating class from PGY-1 to PGY-3", "rosters"),
    ("yoy", "Year over year", "The same residents, last year to this year", "rosters"),
    ("mksap", "MKSAP", "Progress by class and MKSAP vs ITE", "mksap"),
    ("items", "Item gaps", "Content areas and questions below national", "program"),
    ("reports", "Reports", "PD report, de-identified summary, all data", "any"),
]
NEEDS = {
    "rosters": "Needs ACP rosters",
    "mksap": "Needs the MKSAP export",
    "program": "Needs the Program Performance Report",
    "any": "Needs at least one file",
}


def program_nav_ui():
    return ui.output_ui("program_tiles")


def program_nav_server(input, session, dataset, program):
    def have() -> dict:
        ds, rep = dataset(), program()
        rosters = ds is not None and ds.wide is not None
        mksap = rosters and ds.mksap is not None
        return {"rosters": rosters, "mksap": mksap, "program": rep is not None, "any": rosters or rep is not None}

    @render.ui
    def program_tiles():
        ok = have()
        try:  # the hidden navset may not have reported its value yet
            current = input.program_nav() or "upload"
        except Exception:
            current = "upload"
        tiles = []
        for value, title, what, need in SECTIONS:
            locked = need is not None and not ok[need]
            active = value == current
            tiles.append(
                ui.tags.button(
                    ui.span(title, class_="ptile-title"),
                    ui.span(NEEDS[need] if locked else what, class_="ptile-what"),
                    type="button",
                    class_="ptile" + (" is-active" if active else "") + (" is-locked" if locked else ""),
                    aria_pressed="true" if active else "false",
                    onclick=f"Shiny.setInputValue('program_go', '{value}', {{priority: 'event'}})",
                )
            )
        # On phones the boxes are one scrolling row: bring the current one into view.
        keep_visible = ui.tags.script(
            "(function(){var r=document.querySelector('.ptiles'),a=r&&r.querySelector('.is-active');"
            "if(a&&r.scrollWidth>r.clientWidth){r.scrollLeft=a.offsetLeft-r.offsetLeft-16;}})();"
        )
        return ui.tags.nav(ui.div(*tiles, class_="ptiles"), keep_visible, aria_label="Program analysis sections")

    @reactive.effect
    @reactive.event(input.program_go)
    def _go():
        ui.update_navset("program_nav", selected=input.program_go())
