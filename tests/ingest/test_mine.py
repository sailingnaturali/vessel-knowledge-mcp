import pytest

from vessel_knowledge_mcp.ingest.mine import to_si


@pytest.mark.parametrize("value,unit,si_value,si_units", [
    (120, "degC", 393.15, "K"),
    (0.8, "bar", 80000.0, "Pa"),
    (11, "bar", 1100000.0, "Pa"),
    (25, "kW", 25000.0, "W"),
    (400, "W", 400.0, "W"),
    (48, "V", 48.0, "V"),
    (500, "A", 500.0, "A"),
    (3000, "rpm", 50.0, "Hz"),
    (100, "L/h", pytest.approx(2.7778e-5, rel=1e-3), "m3/s"),
    (30, "psi", pytest.approx(206842.7, rel=1e-4), "Pa"),
])
def test_to_si(value, unit, si_value, si_units):
    got_value, got_units = to_si(value, unit)
    assert got_value == si_value
    assert got_units == si_units


def test_to_si_unknown_unit_passes_through():
    assert to_si(5, "furlongs") == (None, None)
