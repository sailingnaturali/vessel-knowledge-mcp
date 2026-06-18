from vessel_knowledge_mcp.models import Equipment, Measurement
from vessel_knowledge_mcp.vault import Vault
from vessel_knowledge_mcp import tools
from vessel_knowledge_mcp.server import dispatch


def _vault():
    return Vault(root=None, equipment=[Equipment(
        equipment_id="oceanvolt-hpsp25", manufacturer="Oceanvolt",
        model="HighPower ServoProp 25", category="propulsion",
        measurements={"temperature": Measurement(signalk_key="temperature", units="K")})])


def _registry():
    return {
        "propulsion.port": {
            "equipment_id": "oceanvolt-hpsp25", "manufacturer": "Oceanvolt",
            "model": "HighPower ServoProp 25", "serial": "OV-1", "instance": "port",
            "category": "propulsion", "source": "declared",
            "paths": [{"path": "propulsion.port.temperature", "measurement": "temperature"}]},
        "propulsion.starboard": {
            "equipment_id": "oceanvolt-hpsp25", "manufacturer": "Oceanvolt",
            "model": "HighPower ServoProp 25", "serial": "OV-2", "instance": "starboard",
            "category": "propulsion", "source": "declared", "paths": []},
        "tanks.fuel.0": {
            "equipment_id": "unknown-x", "manufacturer": None, "model": None,
            "serial": None, "instance": "0", "category": "tank", "source": "discovered",
            "paths": []},
    }


def test_list_installed_summarizes_each_instance():
    out = tools.list_installed(_vault(), _registry())
    by_id = {e["instance_id"]: e for e in out["installed"]}
    assert by_id["propulsion.port"]["serial"] == "OV-1"
    assert by_id["propulsion.port"]["has_card"] is True
    assert by_id["tanks.fuel.0"]["has_card"] is False


def test_get_installed_exact_key_joins_card():
    out = tools.get_installed(_vault(), _registry(), "propulsion.port")
    assert out["found"] is True
    assert out["instance_id"] == "propulsion.port"
    assert out["installed"]["serial"] == "OV-1"
    assert out["card"]["equipment_id"] == "oceanvolt-hpsp25"


def test_get_installed_short_name_unique():
    out = tools.get_installed(_vault(), _registry(), "port")
    assert out["found"] is True
    assert out["instance_id"] == "propulsion.port"


def test_get_installed_ambiguous_short_name():
    reg = _registry()
    reg["electrical.batteries.0"] = {**reg["tanks.fuel.0"], "instance": "0"}
    out = tools.get_installed(_vault(), reg, "0")
    assert out["found"] is False
    assert "error" in out


def test_get_installed_absent():
    assert tools.get_installed(_vault(), _registry(), "nope")["found"] is False


def test_get_installed_linked_but_missing_card():
    out = tools.get_installed(_vault(), _registry(), "tanks.fuel.0")
    assert out["found"] is True
    assert out["card"] is None


def test_get_installed_null_equipment_id():
    reg = {"sensor.0": {"equipment_id": None, "instance": "0", "manufacturer": None,
                        "model": None, "serial": None, "category": None,
                        "source": "discovered", "paths": []}}
    assert tools.list_installed(_vault(), reg)["installed"][0]["has_card"] is False
    out = tools.get_installed(_vault(), reg, "sensor.0")
    assert out["found"] is True
    assert out["card"] is None


def test_dispatch_list_installed():
    out = dispatch(_vault(), {}, "list_installed", {}, registry=_registry())
    assert any(e["instance_id"] == "propulsion.port" for e in out["installed"])


def test_dispatch_list_installed_no_registry():
    out = dispatch(_vault(), {}, "list_installed", {})  # registry omitted -> {}
    assert out["installed"] == []


def test_dispatch_get_installed():
    out = dispatch(_vault(), {}, "get_installed", {"instance": "port"}, registry=_registry())
    assert out["instance_id"] == "propulsion.port"
