"""Load the path -> {equipment_id, measurement} resolver map."""
from __future__ import annotations

import json
import os
from pathlib import Path


def bindings_path() -> Path | None:
    p = os.environ.get("VESSEL_KNOWLEDGE_BINDINGS_PATH")
    return Path(p).expanduser() if p else None


def load_bindings(path: Path | None = None) -> dict[str, dict]:
    path = path if path is not None else bindings_path()
    if path is None or not Path(path).is_file():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))
