import json

import vessel_knowledge_mcp.registry as registry_mod
from vessel_knowledge_mcp.registry import flatten_bindings, load_registry, migrate_bindings
from vessel_knowledge_mcp.models import Equipment, Measurement
from vessel_knowledge_mcp.vault import Vault


def _registry():
    return {
        "propulsion.port": {
            "equipment_id": "oceanvolt-hpsp25", "manufacturer": "Oceanvolt",
            "model": "HighPower ServoProp 25", "serial": "OV-25-00412",
            "instance": "port", "category": "propulsion", "source": "declared",
            "paths": [
                {"path": "propulsion.port.temperature", "measurement": "temperature"},
                {"path": "propulsion.port.controllerTemperature",
                 "measurement": "controllerTemperature"},
            ],
        },
    }


def test_flatten_bindings_maps_each_path():
    out = flatten_bindings(_registry())
    assert out["propulsion.port.temperature"] == {
        "equipment_id": "oceanvolt-hpsp25", "measurement": "temperature"}
    assert out["propulsion.port.controllerTemperature"]["measurement"] == \
        "controllerTemperature"


def test_flatten_skips_null_equipment_id():
    reg = {"propulsion.port": {"equipment_id": None, "instance": "port",
                               "paths": [{"path": "propulsion.port.temperature",
                                          "measurement": "temperature"}]}}
    assert flatten_bindings(reg) == {}


def test_load_registry_reads_local_file(tmp_path):
    p = tmp_path / "equipment-registry.json"
    p.write_text(json.dumps(_registry()))
    reg = load_registry(p)
    assert reg["propulsion.port"]["serial"] == "OV-25-00412"


def test_load_registry_missing_file_is_empty(tmp_path):
    assert load_registry(tmp_path / "nope.json") == {}


def test_load_registry_fetches_signalk_when_no_file(monkeypatch):
    monkeypatch.delenv("VESSEL_KNOWLEDGE_REGISTRY_PATH", raising=False)
    monkeypatch.setattr(registry_mod, "_fetch_signalk_registry",
                        lambda url: {"propulsion.port": {"equipment_id": "x"}})
    assert load_registry()["propulsion.port"]["equipment_id"] == "x"


def test_load_registry_file_wins_over_signalk(tmp_path, monkeypatch):
    p = tmp_path / "equipment-registry.json"
    p.write_text(json.dumps({"propulsion.port": {"equipment_id": "from-file"}}))
    monkeypatch.setenv("VESSEL_KNOWLEDGE_REGISTRY_PATH", str(p))

    def _boom(url):
        raise AssertionError("SignalK must not be called when the file override is set")

    monkeypatch.setattr(registry_mod, "_fetch_signalk_registry", _boom)
    assert load_registry()["propulsion.port"]["equipment_id"] == "from-file"


def test_load_registry_empty_when_fetch_fails(monkeypatch):
    monkeypatch.delenv("VESSEL_KNOWLEDGE_REGISTRY_PATH", raising=False)

    def _boom(url):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(registry_mod, "_fetch_signalk_registry", _boom)
    assert load_registry() == {}


def _vault_with(eq_id, mfr, model, category):
    return Vault(root=None, equipment=[Equipment(
        equipment_id=eq_id, manufacturer=mfr, model=model, category=category,
        measurements={"temperature": Measurement(signalk_key="temperature", units="K")})])


def test_migrate_bindings_groups_by_instance_with_identity():
    bindings = {
        "propulsion.port.temperature":
            {"equipment_id": "oceanvolt-hpsp25", "measurement": "temperature"},
        "propulsion.port.controllerTemperature":
            {"equipment_id": "oceanvolt-hpsp25", "measurement": "controllerTemperature"},
    }
    vault = _vault_with("oceanvolt-hpsp25", "Oceanvolt", "HighPower ServoProp 25",
                        "propulsion")
    reg = migrate_bindings(bindings, vault)
    assert set(reg) == {"propulsion.port"}
    e = reg["propulsion.port"]
    assert e["manufacturer"] == "Oceanvolt"
    assert e["instance"] == "port"
    assert e["serial"] is None
    assert e["source"] == "declared"
    assert {p["path"] for p in e["paths"]} == {
        "propulsion.port.temperature", "propulsion.port.controllerTemperature"}


def test_migrate_bindings_battery_instance_path():
    bindings = {"electrical.batteries.house.voltage":
                {"equipment_id": "victron-cerbo-gx", "measurement": "voltage"}}
    vault = _vault_with("victron-cerbo-gx", "Victron", "Cerbo GX", "electrical")
    reg = migrate_bindings(bindings, vault)
    assert "electrical.batteries.house" in reg
    assert reg["electrical.batteries.house"]["instance"] == "house"
