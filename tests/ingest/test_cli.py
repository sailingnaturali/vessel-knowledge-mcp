import json
from pathlib import Path

from vessel_knowledge_mcp.ingest import cli

CARD = """\
---
equipment_id: bellmarine-ddw-10
manufacturer: Bellmarine
model: DDW-10
category: propulsion
measurements:
  temperature:
    signalk_key: temperature
    units: K
    zones:
      - { state: normal, lower: 273.15, upper: 353.15 }
---
prose
"""


def _seed_vault(tmp_path: Path) -> Path:
    (tmp_path / "equipment").mkdir()
    (tmp_path / "equipment" / "bellmarine-ddw-10.md").write_text(CARD)
    return tmp_path


def test_zones_subcommand_writes_delta_and_bindings(tmp_path, capsys):
    vault = _seed_vault(tmp_path)
    bindings_in = tmp_path / "in.json"
    bindings_in.write_text(json.dumps([{"model": "bellmarine-ddw-10", "path_prefix": "propulsion.0"}]))
    out_bindings = tmp_path / "out_bindings.json"
    rc = cli.main(["zones", "--vault", str(vault), "--bindings", str(bindings_in),
                   "--out-bindings", str(out_bindings)])
    assert rc == 0
    delta = json.loads(capsys.readouterr().out)
    assert delta["updates"][0]["meta"][0]["path"] == "propulsion.0.temperature"
    assert json.loads(out_bindings.read_text())["propulsion.0.temperature"]["equipment_id"] == "bellmarine-ddw-10"
