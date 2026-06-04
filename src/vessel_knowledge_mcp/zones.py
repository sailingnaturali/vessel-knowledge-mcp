"""Pure zone math: matching, validation, and SignalK delta generation."""
from __future__ import annotations

from vessel_knowledge_mcp.models import Equipment, Measurement, Zone

_NEG_INF = float("-inf")
_POS_INF = float("inf")


def zone_for(zones: list[Zone], value: float) -> Zone | None:
    """Return the zone containing value (lower-inclusive, upper-exclusive), or None."""
    for z in zones:
        lo = _NEG_INF if z.lower is None else z.lower
        hi = _POS_INF if z.upper is None else z.upper
        if lo <= value < hi:
            return z
    return None


def validate_zones(key: str, m: Measurement) -> list[str]:
    """Warn on overlapping or gapped adjacent bands (sorted by lower bound)."""
    warnings: list[str] = []
    ordered = sorted(m.zones, key=lambda z: _NEG_INF if z.lower is None else z.lower)
    for a, b in zip(ordered, ordered[1:]):
        a_hi = _POS_INF if a.upper is None else a.upper
        b_lo = _NEG_INF if b.lower is None else b.lower
        if a_hi > b_lo:
            warnings.append(f"{key}: zones overlap between {a.state} and {b.state}")
        elif a_hi < b_lo:
            warnings.append(f"{key}: gap between {a.state} and {b.state}")
    return warnings


def _zone_dict(z: Zone) -> dict:
    out: dict = {}
    if z.lower is not None:
        out["lower"] = z.lower
    if z.upper is not None:
        out["upper"] = z.upper
    out["state"] = z.state
    if z.message is not None:
        out["message"] = z.message
    return out


def generate_zones(vault, bindings: list[dict]) -> tuple[dict, dict, list[str]]:
    """Join equipment cards against {model, path_prefix} bindings.

    Returns (signalk_delta, bindings_map, warnings).
    - signalk_delta: a single delta with a `meta` array, ready to merge into baseDeltas.json
    - bindings_map: full SignalK path -> {equipment_id, measurement}
    - warnings: unknown models + per-measurement zone overlaps/gaps
    """
    meta: list[dict] = []
    bindings_map: dict[str, dict] = {}
    warnings: list[str] = []
    for b in bindings:
        eq = vault.get(b["model"])
        if eq is None:
            warnings.append(f"unknown model: {b['model']}")
            continue
        prefix = b["path_prefix"].rstrip(".")
        for key, m in eq.measurements.items():
            warnings.extend(validate_zones(key, m))
            path = f"{prefix}.{m.signalk_key}"
            meta.append({"path": path,
                         "value": {"units": m.units, "zones": [_zone_dict(z) for z in m.zones]}})
            bindings_map[path] = {"equipment_id": eq.equipment_id, "measurement": key}
    delta = {"context": "vessels.self", "updates": [{"meta": meta}]}
    return delta, bindings_map, warnings
