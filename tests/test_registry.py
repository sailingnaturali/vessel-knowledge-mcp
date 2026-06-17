import json

from vessel_knowledge_mcp.registry import flatten_bindings, load_registry


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
