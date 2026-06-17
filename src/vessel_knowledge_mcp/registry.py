"""Load the equipment registry and flatten it to a path->binding map.

Registry source precedence:
  1. VESSEL_KNOWLEDGE_REGISTRY_PATH (local JSON file) — explicit dev/offline override.
  2. SignalK resources/equipment at SIGNALK_URL (default http://localhost:3000).
A read failure yields an empty registry (logged) so explain_notification degrades
to its "no equipment bound" path rather than crashing.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SIGNALK_URL = "http://localhost:3000"


def registry_file() -> Path | None:
    p = os.environ.get("VESSEL_KNOWLEDGE_REGISTRY_PATH")
    return Path(p).expanduser() if p else None


def load_registry(path: Path | None = None) -> dict:
    """Return the equipment registry collection (instance-id -> entry)."""
    path = path if path is not None else registry_file()
    if path is not None:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("registry file %s unreadable: %s", path, exc)
            return {}
    return {}  # SignalK fetch added in Task 2


def flatten_bindings(registry: dict) -> dict:
    """Flatten registry entries' paths[] into {path: {equipment_id, measurement}}.

    Entries with a null equipment_id (discovered-but-unlinked, SP2) contribute
    nothing — their paths resolve to the unbound-path error until a card is linked.
    """
    out: dict[str, dict] = {}
    for entry in registry.values():
        eq = entry.get("equipment_id")
        if not eq:
            continue
        for p in entry.get("paths", []):
            out[p["path"]] = {"equipment_id": eq, "measurement": p["measurement"]}
    return out
