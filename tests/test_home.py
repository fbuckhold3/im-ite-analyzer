from ite_core import individual, nomogram
from modules import home


def test_guide_buttons_open_real_tabs():
    assert set(home.TARGETS.values()) == {"calc", "me", "program"}
    assert {"go_me2", "go_calc2", "go_program2"} <= set(home.TARGETS)


def test_home_guide_renders_both_paths():
    html = str(home.home_ui())
    for s in ("If you're a resident", "If you're a program director", "What each file unlocks", 'id="how-to"'):
        assert s in html, s


def test_example_numbers_match_the_model():
    """The illustrative resident example must be consistent with the nomogram it illustrates."""
    p = nomogram.pass_prob(48, 1)
    assert 0.5 <= p < nomogram.DEFAULT_CUTOFFS[1]  # Intermediate
    html = str(home.home_ui())
    assert f"{int(p * 100)}% estimated pass" in html
    (pgy, target), *_ = individual.next_year_targets(1, nomogram.DEFAULT_CUTOFFS)
    assert pgy == 2 and f"aim for about {round(target)}% correct" in html
