import json

from vessel_knowledge_mcp.bindings import load_bindings


def test_load_bindings_reads_json(tmp_path):
    p = tmp_path / "bindings.json"
    p.write_text(json.dumps({"propulsion.0.temperature":
                             {"equipment_id": "bellmarine-ddw-10", "measurement": "temperature"}}))
    b = load_bindings(p)
    assert b["propulsion.0.temperature"]["equipment_id"] == "bellmarine-ddw-10"


def test_load_bindings_missing_file_is_empty(tmp_path):
    assert load_bindings(tmp_path / "nope.json") == {}
