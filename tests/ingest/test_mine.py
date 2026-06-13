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


from vessel_knowledge_mcp.ingest.mine import Candidate, mine_page, mine_pages  # noqa: E402


def _by_unit(cands, unit):
    return [c for c in cands if c.unit == unit]


def test_mine_page_temperature_spellings():
    text = (
        "warning if the motor temperature is higher than 120 celsius\n"
        "controller limit 110 °C in continuous use\n"
        "store above 5°C\n"
    )
    cands = mine_page(text, page_no=58)
    temps = _by_unit(cands, "degC")
    assert [c.value for c in temps] == [120.0, 110.0, 5.0]
    assert temps[0].si_value == 393.15
    assert temps[0].si_units == "K"
    assert temps[0].page == 58
    assert temps[0].line_no == 1
    assert "120 celsius" in temps[0].line


def test_mine_page_decimal_comma_and_range():
    text = (
        "stops if the pump pressure exceeds 11 bar or doesn't reach 0,8 bar\n"
        "check the working pressure of the unit is correct (7-8 bar)\n"
    )
    cands = mine_page(text, page_no=31)
    bars = _by_unit(cands, "bar")
    # line 1: two singles; line 2: one range candidate (not two singles)
    assert [(c.value, c.value_high) for c in bars] == [
        (11.0, None), (0.8, None), (7.0, 8.0)]
    rng = bars[2]
    assert rng.si_value == 700000.0
    assert rng.si_value_high == 800000.0


def test_mine_page_power_current_voltage():
    text = (
        "SP25 nominal power 25 kW and peak 30 kW\n"
        "current nominal 500 A peak 600 A on the 48 Vdc bus\n"
        "average electric consumption: 400 Watt\n"
    )
    cands = mine_page(text, page_no=12)
    assert [c.value for c in _by_unit(cands, "kW")] == [25.0, 30.0]
    assert [c.value for c in _by_unit(cands, "A")] == [500.0, 600.0]
    assert [c.value for c in _by_unit(cands, "V")] == [48.0]
    assert [c.value for c in _by_unit(cands, "W")] == [400.0]


def test_mine_page_tolerates_celcius_misspelling():
    # The SP25 user manual p.58 really spells it "celcius" — and that line
    # carries the controller warning threshold. Mining must not miss it.
    text = "controller is higher than 110 celcius this will trigger a warning\n"
    cands = mine_page(text, page_no=58)
    assert [(c.value, c.unit) for c in cands] == [(110.0, "degC")]


def test_mine_page_ignores_unitless_and_page_numbers():
    text = "Table 5 error codes\n65\ncode 12 motor feedback error\n"
    assert mine_page(text, page_no=65) == []


def test_mine_pages_numbers_from_one():
    pages = ["", "limit 90 °C", ""]
    cands = mine_pages(pages)
    assert len(cands) == 1
    assert cands[0].page == 2
