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
