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


def test_find_equipment_matches_category_via_token():
    # "propulsion motor" must resolve to the propulsion-category card even though
    # neither word is a substring of the id/model/aliases — category + tokenizing.
    out = tools.find_equipment(_vault(), "the propulsion motor")
    assert [m["equipment_id"] for m in out["matches"]] == ["bellmarine-ddw-10"]
    assert out["matches"][0]["category"] == "propulsion"


def test_find_equipment_ignores_one_char_tokens():
    # a stray single-char token must not match-all
    assert tools.find_equipment(_vault(), "x")["matches"] == []


def test_list_equipment_returns_all_cards():
    out = tools.list_equipment(_vault())
    assert out["equipment"] == [{
        "equipment_id": "bellmarine-ddw-10", "manufacturer": "Bellmarine",
        "model": "DDW-10", "category": "propulsion",
    }]


def test_find_equipment_ranks_exact_field_match_first():
    from vessel_knowledge_mcp.models import Equipment
    from vessel_knowledge_mcp.vault import Vault
    exact = Equipment(equipment_id="ddw-10", manufacturer="Bellmarine",
                      model="DDW-10", category="propulsion")
    fuzzy = Equipment(equipment_id="ddw-100", manufacturer="Bellmarine",
                      model="DDW-100", category="propulsion")
    v = Vault(root=None, equipment=[fuzzy, exact])   # fuzzy listed first
    out = tools.find_equipment(v, "ddw-10")
    assert [m["equipment_id"] for m in out["matches"]] == ["ddw-10", "ddw-100"]
