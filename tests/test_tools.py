from vessel_knowledge_mcp.models import Equipment, Measurement, Zone
from vessel_knowledge_mcp.vault import Vault
from vessel_knowledge_mcp import tools


def _vault():
    eq = Equipment(
        equipment_id="bellmarine-ddw-10", manufacturer="Bellmarine", model="DDW-10",
        category="propulsion", aliases=["Bellmarine DDW 10kW", "DDW10"],
        part_numbers=[{"part": "IMP-2024", "description": "impeller"}],
        measurements={"temperature": Measurement(
            signalk_key="temperature", units="K", display_units="degC",
            zones=[Zone(state="normal", lower=273.15, upper=353.15)])},
    )
    return Vault(root=None, equipment=[eq])


def test_get_equipment_returns_card():
    out = tools.get_equipment(_vault(), "bellmarine-ddw-10")
    assert out["found"] is True
    assert out["equipment"]["model"] == "DDW-10"
    assert out["equipment"]["measurements"]["temperature"]["units"] == "K"


def test_get_equipment_missing():
    assert tools.get_equipment(_vault(), "ghost") == {"found": False, "equipment_id": "ghost"}


def test_find_equipment_matches_alias_case_insensitive():
    out = tools.find_equipment(_vault(), "ddw 10kw")
    assert out["matches"][0]["equipment_id"] == "bellmarine-ddw-10"


def test_find_equipment_no_match():
    assert tools.find_equipment(_vault(), "outboard")["matches"] == []
