import math

from ite_core import demo, pdf_reports
from modules import items_tab as I
from modules import plots, program_nav


def test_gap_classes():
    assert [I.gap_class(v) for v in (-25, -20, -15, -10, -9, 0, 9, 10, 30)] == [
        "gap-sev",
        "gap-sev",
        "gap-neg",
        "gap-neg",
        "gap-0",
        "gap-0",
        "gap-0",
        "gap-pos",
        "gap-pos",
    ]
    assert I.gap_class(math.nan) == "gap-na" and I.gap_class(None) == "gap-na"


def test_items_table_orders_flagged_first_and_labels_gaps():
    it = demo.sample_program_report()["items"]
    html = str(I.items_table(it))
    assert html.count('class="it-row') == len(it)
    first_yellow, last_red = html.find("flag-yellow"), html.rfind("flag-red")
    assert -1 < last_red < first_yellow  # red rows before yellow rows
    assert 'data-label="PGY-1"' in html and "vs" in html


def test_heatmap_sorts_lowest_rank_first_and_has_no_nan():
    ranks = pdf_reports.area_ranks(demo.sample_program_report()["areas"])
    fig = plots.area_ranks_heatmap(ranks)
    hm = fig.data[0]
    areas = [a for a in hm.y if a != "Total test"]
    all_rank = ranks.set_index("area").rankA
    assert list(all_rank.loc[areas]) == sorted(all_rank.loc[areas])
    assert list(hm.x) == ["PGY-1", "PGY-2", "PGY-3", "All PGYs"]
    assert all(v is None or v == v for row in hm.z for v in row)  # widget_safe: no NaN


def test_section_boxes_match_the_app_sections():
    import app

    html = str(app.app_ui)
    for value, *_ in program_nav.SECTIONS:
        assert f'data-value="{value}"' in html, value
