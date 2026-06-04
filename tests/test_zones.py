from vessel_knowledge_mcp.models import Measurement, Zone
from vessel_knowledge_mcp.zones import validate_zones, zone_for


def _zones():
    return [
        Zone(state="normal", lower=273.15, upper=353.15),
        Zone(state="warn", lower=353.15, upper=368.15, message="high"),
        Zone(state="alarm", lower=368.15, message="over-temp"),
    ]


def test_zone_for_picks_band_lower_inclusive_upper_exclusive():
    z = _zones()
    assert zone_for(z, 300.0).state == "normal"
    assert zone_for(z, 353.15).state == "warn"   # lower-inclusive
    assert zone_for(z, 370.0).state == "alarm"    # open upper
    assert zone_for(z, 200.0) is None             # below all bands


def test_validate_zones_flags_overlap_and_gap():
    overlap = Measurement(signalk_key="t", units="K", zones=[
        Zone(state="normal", lower=0, upper=10),
        Zone(state="warn", lower=5, upper=20),
    ])
    gap = Measurement(signalk_key="t", units="K", zones=[
        Zone(state="normal", lower=0, upper=10),
        Zone(state="warn", lower=15, upper=20),
    ])
    clean = Measurement(signalk_key="t", units="K", zones=_zones())
    assert any("overlap" in w for w in validate_zones("t", overlap))
    assert any("gap" in w for w in validate_zones("t", gap))
    assert validate_zones("t", clean) == []
