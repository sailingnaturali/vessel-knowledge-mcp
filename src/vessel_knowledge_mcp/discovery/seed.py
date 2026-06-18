"""Pure discovery pipeline: group self-tree paths by source, match devices to
vault cards, propose registry entries, and diff against the current registry."""
from __future__ import annotations

from vessel_knowledge_mcp.registry import _instance_of
from vessel_knowledge_mcp.tools import find_equipment

# Self-tree leaf keys that are value/metadata, not child paths.
_LEAF_KEYS = {"value", "$source", "timestamp", "values", "meta", "pgn", "sentence"}
# Top-level self keys that aren't data paths. `$source` is included defensively —
# some server versions surface it at the vessel root.
_SELF_SKIP = {"uuid", "name", "mmsi", "type", "url", "version", "$source", "communication"}


def paths_by_source(self_tree: dict) -> dict[str, list[str]]:
    """Map each `$source` to the list of data paths it feeds."""
    out: dict[str, list[str]] = {}

    def walk(node: dict, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        src = node.get("$source")
        if isinstance(src, str):
            # A SignalK leaf path node carries $source and has no further path
            # children, so stopping here is correct (and intended).
            out.setdefault(src, []).append(prefix)
            return
        for k, v in node.items():
            if k in _LEAF_KEYS:
                continue
            walk(v, f"{prefix}.{k}" if prefix else k)

    for k, v in self_tree.items():
        if k in _SELF_SKIP:
            continue
        walk(v, k)
    return out


def match_equipment_id(vault, manufacturer: str | None, model: str | None) -> str | None:
    """Best vault equipment_id for a discovered device, via the find_equipment
    token scorer. None when no token matches."""
    query = " ".join(t for t in (manufacturer, model) if t)
    if not query:
        return None
    matches = find_equipment(vault, query)["matches"]
    return matches[0]["equipment_id"] if matches else None


def propose_entries(devices, source_paths: dict, vault) -> dict:
    """Build proposed registry entries (source='discovered') from discovered
    devices + their self-tree paths (a `paths_by_source` map), grouped by instance.

    If two devices feed the same instance, the first device's identity wins and
    both devices' paths accumulate under it — a rare case a human reviewer of the
    proposal would catch.
    """
    registry: dict[str, dict] = {}
    for dev in devices:
        eq_id = match_equipment_id(vault, dev.manufacturer, dev.model)
        card = vault.get(eq_id) if eq_id else None
        for path in source_paths.get(dev.source_ref, []):
            instance_id, instance = _instance_of(path)
            entry = registry.get(instance_id)
            if entry is None:
                entry = registry[instance_id] = {
                    "equipment_id": eq_id,
                    "manufacturer": dev.manufacturer,
                    "model": dev.model,
                    "serial": dev.serial,
                    "instance": instance,
                    "category": card.category if card else None,
                    "source": "discovered",
                    "paths": [],
                    "n2k": {"manufacturerCode": dev.manufacturer_code},
                }
            entry["paths"].append({"path": path, "measurement": path.rsplit(".", 1)[-1]})
    return registry
