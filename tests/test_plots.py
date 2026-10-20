import pandas as pd
import pytest

from ite_core import demo, history, stats
from ite_core import session as S
from modules import plots


@pytest.fixture(scope="module")
def data():
    d = demo.make_demo()
    r = S.load_rosters([S.Upload(n, b) for n, b in d["rosters"]])
    return r.long, S.build_wide(r, None, None)


@pytest.mark.parametrize("metric", list(plots.LEVEL_METRICS))
def test_level_small_multiples_all_metrics(data, metric):
    long, _ = data
    fig = plots.level_small_multiples(history.by_level(long), metric)
    assert len(fig.data) == 3 and all(len(t.x) == 3 for t in fig.data)


def test_small_groups_are_hatched():
    lv = pd.DataFrame(dict(PGY=[1, 1], Exam_Year=[2025, 2026], n=[3, 12], ile=[40.0, 55.0], small_n=[True, False]))
    fig = plots.level_small_multiples(lv, "ile")
    assert list(fig.data[0].marker.pattern.shape) == ["/", ""]


def test_class_lines_current_solid_graduated_dashed(data):
    long, _ = data
    fig = plots.class_trajectories_figure(history.class_trajectories(long))
    dash = {t.name: t.line.dash for t in fig.data}
    assert dash["Class of 2028"] == "solid" and dash["Class of 2025"] == "dash"
    assert fig.data[0].name == "Class of 2029"  # newest first = first colour


def test_nomogram_points_and_bands():
    fig = plots.nomogram_figure()
    plots.set_points(fig, [(3, 65.0, 0.898)])
    assert list(fig.data[plots.POINTS_TRACE].x) == [65.0]
    assert len(fig.layout.shapes) == 3


@pytest.mark.parametrize("outcome", ["percentile", "pct_correct"])
def test_yoy_scatter(data, outcome):
    _, w = data
    fig = plots.yoy_scatter(stats.paired_points(w), outcome)
    assert {t.name for t in fig.data if t.name} == {"Now PGY-2", "Now PGY-3"}
