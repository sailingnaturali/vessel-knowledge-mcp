import json
from pathlib import Path

from vessel_knowledge_mcp.discovery.n2k_sources import DiscoveredDevice, parse_devices
from vessel_knowledge_mcp.discovery.seed import (
    diff_registry, paths_by_source, propose_entries, reconcile)
from vessel_knowledge_mcp.ingest.cli import main as cli_main
from vessel_knowledge_mcp.models import Equipment, Measurement
from vessel_knowledge_mcp.vault import Vault


def test_parse_devices_extracts_n2k_identity():
    sources = {
        "defaults": {},
        "n2k-1": {
            "22": {"n2k": {"manufacturerCode": 358, "modelId": "ServoProp 25",
                           "modelSerialCode": "OV-25-00412", "canName": "abc"}},
            "16": {"label": "no n2k block here"},
        },
        "signalk-mock-vessel": {},
    }
    devs = parse_devices(sources)
    assert len(devs) == 1
    d = devs[0]
    assert isinstance(d, DiscoveredDevice)
    assert d.source_ref == "n2k-1.22"
    assert d.manufacturer_code == 358
    assert d.model == "ServoProp 25"
    assert d.serial == "OV-25-00412"


def test_parse_devices_string_manufacturer_code():
    sources = {"bus": {"3": {"n2k": {"manufacturerCode": "Victron Energy",
                                      "modelId": "Cerbo GX"}}}}
    d = parse_devices(sources)[0]
    assert d.manufacturer == "Victron Energy"
    assert d.manufacturer_code is None
    assert d.model == "Cerbo GX"


def test_paths_by_source_groups_leaves_by_source():
    self_tree = {
        "uuid": "urn:mrn:signalk:x",
        "propulsion": {
            "0": {
                "revolutions": {"value": 20.0, "$source": "n2k-1.22", "timestamp": "t"},
                "temperature": {"value": 320.0, "$source": "n2k-1.22"},
            }
        },
        "navigation": {
            "position": {"value": {"latitude": 1, "longitude": 2}, "$source": "gps.1"}
        },
    }
    out = paths_by_source(self_tree)
    assert sorted(out["n2k-1.22"]) == ["propulsion.0.revolutions", "propulsion.0.temperature"]
    assert sorted(out["gps.1"]) == ["navigation.position"]


def test_paths_by_source_empty_tree():
    assert paths_by_source({}) == {}


def test_paths_by_source_ignores_non_string_source():
    out = paths_by_source({"environment": {"depth":
                          {"$source": {"label": "bad"}, "value": 5.0}}})
    assert out == {}


def test_paths_by_source_skips_notifications():
    # n2k-signalk fans one engine PGN into many notifications.* alert leaves that
    # carry the device $source; those must never become equipment data paths.
    self_tree = {
        "propulsion": {"port": {"temperature": {"value": 320.0, "$source": "n2k-1.22"}}},
        "notifications": {"propulsion": {"port": {"temperature":
                          {"value": {"state": "alert"}, "$source": "n2k-1.22"}}}},
    }
    out = paths_by_source(self_tree)
    assert out["n2k-1.22"] == ["propulsion.port.temperature"]
    assert not any(p.startswith("notifications") for p in out["n2k-1.22"])


def _vault():
    return Vault(root=None, equipment=[Equipment(
        equipment_id="oceanvolt-hpsp25", manufacturer="Oceanvolt",
        model="HighPower ServoProp 25", category="propulsion",
        measurements={"temperature": Measurement(signalk_key="temperature", units="K")})])


def test_propose_entries_builds_matched_discovered_entry():
    devices = [DiscoveredDevice(source_ref="n2k-1.22", manufacturer_code=1857,
                                manufacturer="Oceanvolt", model="ServoProp 25",
                                serial="OV-25-00412")]
    pbs = {"n2k-1.22": ["propulsion.0.temperature", "propulsion.0.revolutions"]}
    reg = propose_entries(devices, pbs, _vault())
    assert set(reg) == {"propulsion.0"}
    e = reg["propulsion.0"]
    assert e["source"] == "discovered"
    assert e["equipment_id"] == "oceanvolt-hpsp25"
    assert e["category"] == "propulsion"
    assert e["serial"] == "OV-25-00412"
    assert e["n2k"] == {"manufacturerCode": 1857}
    assert {p["path"] for p in e["paths"]} == {
        "propulsion.0.temperature", "propulsion.0.revolutions"}
    assert {p["measurement"] for p in e["paths"]} == {"temperature", "revolutions"}


def test_propose_entries_no_match_leaves_equipment_id_null():
    devices = [DiscoveredDevice(source_ref="b.9", manufacturer_code=None,
                                manufacturer=None, model="Totally Unknown Widget",
                                serial=None)]
    pbs = {"b.9": ["tanks.fuel.0.currentLevel"]}
    reg = propose_entries(devices, pbs, _vault())
    assert reg["tanks.fuel.0"]["equipment_id"] is None
    assert reg["tanks.fuel.0"]["category"] is None
    assert reg["tanks.fuel.0"]["instance"] == "0"
    assert reg["tanks.fuel.0"]["paths"][0]["measurement"] == "currentLevel"


def test_diff_registry_partitions_added_and_conflicts():
    current = {"propulsion.port": {"source": "declared"}}
    proposed = {"propulsion.port": {"source": "discovered"},
                "electrical.batteries.house": {"source": "discovered"}}
    d = diff_registry(current, proposed)
    assert d["added"] == ["electrical.batteries.house"]
    assert d["conflicts"] == ["propulsion.port"]


def _write(p, obj):
    Path(p).write_text(json.dumps(obj), encoding="utf-8")


def _seed_vault(tmp_path):
    """A self-contained vault (no dependency on the sibling vault repo / CWD)."""
    eq_dir = tmp_path / "vault" / "equipment"
    eq_dir.mkdir(parents=True)
    (eq_dir / "oceanvolt-hpsp25.md").write_text(
        "---\nequipment_id: oceanvolt-hpsp25\nmanufacturer: Oceanvolt\n"
        "model: HighPower ServoProp 25\ncategory: propulsion\nmeasurements:\n"
        "  temperature:\n    signalk_key: temperature\n    units: K\n---\n",
        encoding="utf-8")
    return tmp_path / "vault"


def test_build_registry_cli_writes_and_guards_empty(tmp_path):
    vault = _seed_vault(tmp_path)
    _write(tmp_path / "bindings.json",
           [{"path_prefix": "propulsion.port", "equipment_id": "oceanvolt-hpsp25",
             "serial": "OV-1"}])
    out = tmp_path / "declared.json"
    rc = cli_main(["build-registry", "--bindings", str(tmp_path / "bindings.json"),
                   "--vault", str(vault), "--out", str(out)])
    assert rc == 0
    reg = json.loads(out.read_text())
    assert reg["propulsion.port"]["serial"] == "OV-1"
    assert reg["propulsion.port"]["source"] == "declared"

    _write(tmp_path / "empty.json", [])
    out2 = tmp_path / "empty-out.json"
    rc2 = cli_main(["build-registry", "--bindings", str(tmp_path / "empty.json"),
                    "--vault", str(vault), "--out", str(out2)])
    assert rc2 == 1
    assert not out2.exists()


def test_discover_cli_writes_added_only(tmp_path):
    vault = _seed_vault(tmp_path)
    sources = {"n2k-1": {"22": {"n2k": {"manufacturerCode": 1857,
                                        "modelId": "ServoProp 25",
                                        "modelSerialCode": "OV-1"}}}}
    self_tree = {"propulsion": {"0": {"temperature":
                 {"value": 320.0, "$source": "n2k-1.22"}}}}
    _write(tmp_path / "sources.json", sources)
    _write(tmp_path / "self.json", self_tree)
    _write(tmp_path / "registry.json", {"electrical.batteries.house": {"source": "declared"}})
    rc = cli_main(["discover",
                   "--sources", str(tmp_path / "sources.json"),
                   "--self", str(tmp_path / "self.json"),
                   "--vault", str(vault),
                   "--registry", str(tmp_path / "registry.json"),
                   "--write"])
    assert rc == 0
    merged = json.loads((tmp_path / "registry.json").read_text())
    assert "electrical.batteries.house" in merged       # declared untouched
    assert merged["propulsion.0"]["source"] == "discovered"
    assert merged["propulsion.0"]["equipment_id"] == "oceanvolt-hpsp25"


def _declared(serial=None):
    return {"propulsion.port": {
        "equipment_id": "oceanvolt-hpsp25", "manufacturer": "Oceanvolt",
        "model": "HighPower ServoProp 25", "serial": serial, "instance": "port",
        "category": "propulsion", "source": "declared",
        "paths": [{"path": "propulsion.port.temperature", "measurement": "temperature"}]}}


def _discovered(eq="oceanvolt-hpsp25", serial="BUS-9", extra_path=True):
    paths = [{"path": "propulsion.port.revolutions", "measurement": "revolutions"}] \
        if extra_path else []
    return {"propulsion.port": {
        "equipment_id": eq, "manufacturer": "Oceanvolt", "model": "ServoProp 25",
        "serial": serial, "instance": "port", "category": "propulsion",
        "source": "discovered", "paths": paths, "n2k": {"manufacturerCode": 847}}}


def test_reconcile_fills_serial_keeps_declared_identity():
    merged, warnings = reconcile(_declared(serial=None), _discovered())
    e = merged["propulsion.port"]
    assert e["serial"] == "BUS-9"
    assert e["model"] == "HighPower ServoProp 25"
    assert e["source"] == "declared"
    assert e["n2k"] == {"manufacturerCode": 847}
    assert {p["path"] for p in e["paths"]} == {
        "propulsion.port.temperature", "propulsion.port.revolutions"}
    assert warnings == []


def test_reconcile_declared_serial_wins():
    merged, _ = reconcile(_declared(serial="DECL"), _discovered(serial="BUS-9"))
    assert merged["propulsion.port"]["serial"] == "DECL"


def test_reconcile_discovered_only_added():
    merged, warnings = reconcile({}, _discovered())
    assert merged["propulsion.port"]["source"] == "discovered"
    assert any("not declared" in w for w in warnings)


def test_reconcile_identity_conflict_warns_keeps_declared():
    merged, warnings = reconcile(_declared(), _discovered(eq="simrad-xx"))
    assert merged["propulsion.port"]["equipment_id"] == "oceanvolt-hpsp25"
    assert any("simrad-xx" in w for w in warnings)


def test_reconcile_idempotent():
    once, _ = reconcile(_declared(serial=None), _discovered())
    twice, _ = reconcile(once, _discovered())
    assert twice == once


def test_reconcile_declared_not_seen_warns():
    declared = {**_declared(),
                "electrical.batteries.house": {"equipment_id": "victron-cerbo-gx",
                                               "instance": "house", "source": "declared",
                                               "paths": []}}
    merged, warnings = reconcile(declared, _discovered())  # discovered only has propulsion.port
    assert "electrical.batteries.house" in merged
    assert any("not seen" in w and "electrical.batteries.house" in w for w in warnings)
