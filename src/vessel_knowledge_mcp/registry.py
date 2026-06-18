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

import httpx

logger = logging.getLogger(__name__)

DEFAULT_SIGNALK_URL = "http://localhost:3000"


def signalk_url() -> str:
    return os.environ.get("SIGNALK_URL", DEFAULT_SIGNALK_URL).rstrip("/")


def _fetch_signalk_registry(url: str) -> dict:
    resp = httpx.get(f"{url}/signalk/v2/api/resources/equipment", timeout=5.0)
    resp.raise_for_status()
    return resp.json()


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
    try:
        return _fetch_signalk_registry(signalk_url())
    except Exception as exc:  # network, JSON, or HTTP status
        logger.warning("registry fetch from SignalK failed: %s", exc)
        return {}


# Path families whose instance is the 3rd segment (group.subtype.instance.*),
# not the 2nd. Both batteries and tanks are keyed <type>.<instance> in SignalK.
_THREE_SEGMENT_PREFIXES = ("electrical.batteries.", "tanks.")


def _instance_of(path: str) -> tuple[str, str]:
    """Derive (instance-id, instance-name) from a data path.

    propulsion.port.temperature        -> ('propulsion.port', 'port')
    electrical.batteries.house.voltage -> ('electrical.batteries.house', 'house')
    tanks.fuel.0.currentLevel          -> ('tanks.fuel.0', '0')
    """
    parts = path.split(".")
    if path.startswith(_THREE_SEGMENT_PREFIXES) and len(parts) >= 3:
        return ".".join(parts[:3]), parts[2]
    return f"{parts[0]}.{parts[1]}", parts[1]


def migrate_bindings(bindings: dict, vault) -> dict:
    """Convert a legacy bindings.json (path -> {equipment_id, measurement}) into a
    registry collection grouped by instance. Identity is taken from the linked
    vault card; serial is unknown (null) until discovery (SP2) or a profile (SP3)."""
    registry: dict[str, dict] = {}
    for path, b in bindings.items():
        instance_id, instance = _instance_of(path)
        entry = registry.get(instance_id)
        if entry is None:
            eq = vault.get(b["equipment_id"])
            entry = registry[instance_id] = {
                "equipment_id": b["equipment_id"],
                "manufacturer": eq.manufacturer if eq else None,
                "model": eq.model if eq else None,
                "serial": None,
                "instance": instance,
                "category": eq.category if eq else None,
                "source": "declared",
                "paths": [],
            }
        entry["paths"].append({"path": path, "measurement": b["measurement"]})
    return registry


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
