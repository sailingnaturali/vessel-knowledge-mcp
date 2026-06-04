from vessel_knowledge_mcp.models import Equipment, Measurement, Zone
from vessel_knowledge_mcp.vault import Vault
from vessel_knowledge_mcp.server import dispatch


def _vault():
    eq = Equipment(
        equipment_id="bellmarine-ddw-10", manufacturer="Bellmarine", model="DDW-10",
        category="propulsion", aliases=["DDW10"],
        measurements={"temperature": Measurement(
            signalk_key="temperature", units="K",
            zones=[Zone(state="normal", lower=273.15, upper=353.15)])},
    )
    return Vault(root=None, equipment=[eq])


_BINDINGS = {"propulsion.0.temperature":
             {"equipment_id": "bellmarine-ddw-10", "measurement": "temperature"}}


def test_dispatch_get_equipment():
    out = dispatch(_vault(), _BINDINGS, "get_equipment", {"equipment_id": "bellmarine-ddw-10"})
    assert out["found"] is True


def test_dispatch_check_reading():
    out = dispatch(_vault(), _BINDINGS, "check_reading",
                   {"equipment_id": "bellmarine-ddw-10", "measurement": "temperature", "value": 300.0})
    assert out["state"] == "normal"


def test_dispatch_explain_notification():
    out = dispatch(_vault(), _BINDINGS, "explain_notification",
                   {"path": "propulsion.0.temperature", "state": "normal", "value": 300.0})
    assert out["equipment_id"] == "bellmarine-ddw-10"


def test_dispatch_find_equipment():
    out = dispatch(_vault(), _BINDINGS, "find_equipment", {"query": "ddw10"})
    assert out["matches"][0]["equipment_id"] == "bellmarine-ddw-10"


def test_dispatch_list_equipment():
    out = dispatch(_vault(), _BINDINGS, "list_equipment", {})
    assert out["equipment"][0]["equipment_id"] == "bellmarine-ddw-10"
    assert out["equipment"][0]["category"] == "propulsion"


def test_dispatch_unknown_tool():
    import pytest
    with pytest.raises(ValueError):
        dispatch(_vault(), _BINDINGS, "nope", {})
