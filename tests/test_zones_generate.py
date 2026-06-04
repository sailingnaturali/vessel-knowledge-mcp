from vessel_knowledge_mcp.models import Equipment, Measurement, Zone
from vessel_knowledge_mcp.vault import Vault
from vessel_knowledge_mcp.zones import generate_zones


def _vault():
    eq = Equipment(
        equipment_id="bellmarine-ddw-10", manufacturer="Bellmarine",
        model="DDW-10", category="propulsion",
        measurements={"temperature": Measurement(
            signalk_key="temperature", units="K", display_units="degC",
            zones=[Zone(state="normal", lower=273.15, upper=353.15),
                   Zone(state="alarm", lower=353.15, message="hot")],
        )},
    )
    return Vault(root=None, equipment=[eq])


def test_generate_emits_meta_delta_at_bound_path():
    delta, bindings, warnings = generate_zones(
        _vault(), [{"equipment_id": "bellmarine-ddw-10", "path_prefix": "propulsion.0"}]
    )
    meta = delta["updates"][0]["meta"]
    assert meta[0]["path"] == "propulsion.0.temperature"
    assert meta[0]["value"]["units"] == "K"
    assert meta[0]["value"]["zones"][0] == {"lower": 273.15, "upper": 353.15, "state": "normal"}
    assert delta["context"] == "vessels.self"
    assert warnings == []


def test_generate_builds_bindings_map():
    _, bindings, _ = generate_zones(
        _vault(), [{"equipment_id": "bellmarine-ddw-10", "path_prefix": "propulsion.0"}]
    )
    assert bindings["propulsion.0.temperature"] == {
        "equipment_id": "bellmarine-ddw-10", "measurement": "temperature"
    }


def test_generate_warns_on_unknown_equipment_id():
    _, _, warnings = generate_zones(_vault(), [{"equipment_id": "ghost", "path_prefix": "x.0"}])
    assert any("unknown equipment_id" in w for w in warnings)
