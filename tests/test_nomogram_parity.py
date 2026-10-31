"""The committed parity fixture must match ite_core.nomogram. The R port (r/iteviz) checks the same file."""

import json
import math
from pathlib import Path

import pytest

from ite_core import nomogram
from scripts.make_parity_fixture import OUT, build_fixture

FIXTURE = json.loads(Path(OUT).read_text(encoding="utf-8"))


def _same(a, b, path="fixture"):
    """Floats within 1e-12 (exp() may differ in the last digit across platforms); everything else exact."""
    if isinstance(a, float) or isinstance(b, float):
        assert a is not None and b is not None, path
        assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12), path
    elif isinstance(a, dict):
        assert isinstance(b, dict) and a.keys() == b.keys(), path
        for k in a:
            _same(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _same(x, y, f"{path}[{i}]")
    else:
        assert a == b, path


def test_fixture_is_current():
    """Fails when nomogram.py changes without regenerating: run scripts/make_parity_fixture.py (and bump
    SPEC_VERSION if results changed on purpose), then update r/iteviz to match."""
    _same(json.loads(json.dumps(build_fixture(), ensure_ascii=False)), FIXTURE)


def test_fixture_matches_spec_constants():
    assert FIXTURE["spec_version"] == nomogram.SPEC_VERSION
    assert {int(k): tuple(v) for k, v in FIXTURE["coefficients"].items()} == nomogram.NOMOGRAM
    assert tuple(FIXTURE["cutoffs"]) == nomogram.DEFAULT_CUTOFFS


@pytest.mark.parametrize("pct,pgy,label", [(65, 3, "~85%"), (60, 1, "≥95%"), (20, 3, "<5%")])
def test_fixture_spot_values(pct, pgy, label):
    case = next(c for c in FIXTURE["point_cases"] if c["pct"] == pct and c["pgy"] == pgy)
    assert case["label"] == label
