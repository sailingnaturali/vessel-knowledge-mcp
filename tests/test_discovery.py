from vessel_knowledge_mcp.discovery.n2k_sources import parse_devices, DiscoveredDevice


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


from vessel_knowledge_mcp.discovery.seed import paths_by_source


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


from vessel_knowledge_mcp.discovery.seed import diff_registry
from vessel_knowledge_mcp.discovery.n2k_sources import DiscoveredDevice
from vessel_knowledge_mcp.discovery.seed import propose_entries
from vessel_knowledge_mcp.models import Equipment, Measurement
from vessel_knowledge_mcp.vault import Vault


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
