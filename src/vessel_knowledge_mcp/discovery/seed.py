"""Pure discovery pipeline: group self-tree paths by source, match devices to
vault cards, propose registry entries, and diff against the current registry."""
from __future__ import annotations

from vessel_knowledge_mcp.registry import _instance_of
from vessel_knowledge_mcp.tools import find_equipment

# Self-tree leaf keys that are value/metadata, not child paths.
_LEAF_KEYS = {"value", "$source", "timestamp", "values", "meta", "pgn", "sentence"}
# Top-level self keys that aren't data paths. `$source` is included defensively —
# some server versions surface it at the vessel root. `notifications` is skipped
# because n2k-signalk fans a single engine PGN (e.g. 127489) out into dozens of
# `notifications.propulsion.<engine>.*` alert leaves that carry the device's
# `$source`; treating those as equipment data paths proposes a bogus
# `notifications.propulsion` instance (seen end-to-end via the virtual-device harness).
_SELF_SKIP = {"uuid", "name", "mmsi", "type", "url", "version", "$source",
              "communication", "notifications"}


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


def diff_registry(current: dict, proposed: dict) -> dict:
    """Partition proposed instances into those not present in current ('added')
    and those already present ('conflicts', never auto-merged — that's SP3)."""
    return {"added": [k for k in proposed if k not in current],
            "conflicts": [k for k in proposed if k in current]}


def reconcile(declared: dict, discovered: dict) -> tuple[dict, list[str]]:
    """Field-level merge: declared wins on identity, discovered fills serial +
    n2k + extra paths and contributes undeclared instances. Returns (merged, warnings)."""
    merged: dict[str, dict] = {}
    warnings: list[str] = []
    for iid, d in declared.items():
        x = discovered.get(iid)
        if x is None:
            merged[iid] = dict(d)
            continue
        m = dict(d)  # declared identity authoritative
        if not d.get("serial") and x.get("serial"):
            m["serial"] = x["serial"]
        if x.get("n2k"):
            m["n2k"] = dict(x["n2k"])
        seen = {p["path"] for p in d.get("paths", [])}
        m["paths"] = list(d.get("paths", [])) + [
            p for p in x.get("paths", []) if p["path"] not in seen]
        m["source"] = "declared"
        if x.get("equipment_id") and x["equipment_id"] != d.get("equipment_id"):
            warnings.append(
                f"{iid}: discovered equipment_id '{x['equipment_id']}' != "
                f"declared '{d.get('equipment_id')}' (kept declared)")
        merged[iid] = m
    for iid, x in discovered.items():
        if iid not in declared:
            merged[iid] = dict(x)
            warnings.append(f"{iid}: discovered but not declared — add it to the profile")
    if discovered:
        for iid in declared:
            if iid not in discovered:
                warnings.append(f"{iid}: declared but not seen on the bus")
    return merged, warnings
