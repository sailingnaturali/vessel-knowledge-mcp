from vessel_knowledge_mcp.models import Equipment, Measurement, Zone
from vessel_knowledge_mcp.vault import Vault
from vessel_knowledge_mcp import tools


def _vault():
    eq = Equipment(
        equipment_id="bellmarine-ddw-10", manufacturer="Bellmarine", model="DDW-10",
        category="propulsion",
        measurements={"temperature": Measurement(
            signalk_key="temperature", units="K", display_units="degC",
            zones=[Zone(state="normal", lower=273.15, upper=353.15),
                   Zone(state="warn", lower=353.15, upper=368.15, message="high"),
                   Zone(state="alarm", lower=368.15, message="over-temp")])},
    )
    return Vault(root=None, equipment=[eq])


def test_check_reading_normal():
    out = tools.check_reading(_vault(), "bellmarine-ddw-10", "temperature", 300.0)
    assert out["state"] == "normal"
    assert out["units"] == "K"


def test_check_reading_alarm_carries_message():
    out = tools.check_reading(_vault(), "bellmarine-ddw-10", "temperature", 370.0)
    assert out["state"] == "alarm"
    assert out["message"] == "over-temp"


def test_check_reading_unknown_equipment():
    out = tools.check_reading(_vault(), "ghost", "temperature", 1.0)
    assert out["found"] is False


def test_check_reading_unknown_measurement():
    out = tools.check_reading(_vault(), "bellmarine-ddw-10", "rpm", 1.0)
    assert out["found"] is False
    assert "rpm" in out["error"]


def test_below_range_reads_abnormal_low_not_unknown():
    # Cards rarely author a low alarm band; under-range is the COMMON abnormal
    # case and must not collapse into a benign "unknown" (fleet conventions R1).
    out = tools.check_reading(_vault(), "bellmarine-ddw-10", "temperature", 250.0)
    assert out["found"] is True
    assert out["state"] == "out_of_range_low"
    assert "below" in out["message"].lower()


def test_above_all_bands_reads_abnormal_high():
    eq = Equipment(
        equipment_id="x", manufacturer="m", model="mo", category="c",
        measurements={"t": Measurement(
            signalk_key="t", units="K",
            zones=[Zone(state="normal", lower=273.15, upper=353.15)])},
    )
    out = tools.check_reading(Vault(root=None, equipment=[eq]), "x", "t", 400.0)
    assert out["state"] == "out_of_range_high"


def test_gap_between_bands_reads_unrated_not_unknown():
    eq = Equipment(
        equipment_id="x", manufacturer="m", model="mo", category="c",
        measurements={"t": Measurement(
            signalk_key="t", units="K",
            zones=[Zone(state="normal", lower=0.0, upper=10.0),
                   Zone(state="alarm", lower=20.0, upper=30.0)])},
    )
    out = tools.check_reading(Vault(root=None, equipment=[eq]), "x", "t", 15.0)
    assert out["state"] == "unrated_gap"


def test_nan_reads_fault():
    out = tools.check_reading(_vault(), "bellmarine-ddw-10", "temperature", float("nan"))
    assert out["state"] == "fault"


def test_no_zones_reads_no_zones():
    eq = Equipment(
        equipment_id="x", manufacturer="m", model="mo", category="c",
        measurements={"t": Measurement(signalk_key="t", units="K", zones=[])},
    )
    out = tools.check_reading(Vault(root=None, equipment=[eq]), "x", "t", 1.0)
    assert out["state"] == "no_zones"


def test_unit_mismatch_is_rejected_not_silently_unknown():
    # 95 degC against a Kelvin card would read below-range; the card knows its
    # units and the caller said degC — reject loudly instead.
    out = tools.check_reading(_vault(), "bellmarine-ddw-10", "temperature", 95.0,
                              units="degC")
    assert out["found"] is False
    assert "degC" in out["error"] and "K" in out["error"]


def test_matching_units_accepted():
    out = tools.check_reading(_vault(), "bellmarine-ddw-10", "temperature", 300.0,
                              units="K")
    assert out["state"] == "normal"


def test_overlapping_zones_prefer_most_severe():
    eq = Equipment(
        equipment_id="x", manufacturer="m", model="mo", category="c",
        measurements={"t": Measurement(
            signalk_key="t", units="K",
            zones=[Zone(state="normal", lower=0.0, upper=100.0),
                   Zone(state="alarm", lower=90.0, upper=100.0, message="hot")])},
    )
    out = tools.check_reading(Vault(root=None, equipment=[eq]), "x", "t", 95.0)
    assert out["state"] == "alarm"
