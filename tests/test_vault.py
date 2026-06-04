from pathlib import Path

from vessel_knowledge_mcp.vault import Vault

CARD = """\
---
equipment_id: bellmarine-ddw-10
manufacturer: Bellmarine
model: DDW-10
category: propulsion
aliases: ["DDW10"]
measurements: {}
---
prose
"""


def _seed(tmp_path: Path) -> Path:
    d = tmp_path / "equipment"
    d.mkdir()
    (d / "bellmarine-ddw-10.md").write_text(CARD)
    return tmp_path


def test_load_reads_cards(tmp_path):
    vault = Vault.load(_seed(tmp_path))
    assert len(vault.equipment) == 1
    assert vault.equipment[0].equipment_id == "bellmarine-ddw-10"


def test_get_by_id_is_case_insensitive(tmp_path):
    vault = Vault.load(_seed(tmp_path))
    assert vault.get("BELLMARINE-DDW-10").model == "DDW-10"
    assert vault.get("missing") is None


def test_load_missing_dir_is_empty(tmp_path):
    assert Vault.load(tmp_path / "nope").equipment == []
