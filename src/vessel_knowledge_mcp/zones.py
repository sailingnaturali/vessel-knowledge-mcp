"""Pure zone math: matching, validation, and SignalK delta generation."""
from __future__ import annotations

import math

from vessel_knowledge_mcp.models import Measurement, Zone

_NEG_INF = float("-inf")
_POS_INF = float("inf")

# SignalK alarm-state severity, for resolving overlapping bands.
_SEVERITY = {"nominal": 0, "normal": 1, "alert": 2, "warn": 3, "alarm": 4, "emergency": 5}


def _bounds(z: Zone) -> tuple[float, float]:
    return (_NEG_INF if z.lower is None else z.lower,
            _POS_INF if z.upper is None else z.upper)


def zone_for(zones: list[Zone], value: float) -> Zone | None:
    """Return the zone containing value (lower-inclusive, upper-exclusive), or None.

    Prefer classify_reading for verdicts — None here conflates below-range,
    gaps, and no-zones, which must not read as benign (fleet conventions R1)."""
    for z in zones:
        lo, hi = _bounds(z)
        if lo <= value < hi:
            return z
    return None


def classify_reading(zones: list[Zone], value: float) -> tuple[str, Zone | None]:
    """Verdict for a reading: the matched zone's state, or an explicit abnormal
    marker — never a bare 'unknown' (R1).

    Returns (state, zone): state is a zone state (overlaps resolve to the most
    severe matching band) or one of 'no_zones' | 'fault' | 'out_of_range_low' |
    'out_of_range_high' | 'unrated_gap'.
    """
    if not zones:
        return "no_zones", None
    if value is None or math.isnan(value):
        return "fault", None
    matching = [z for z in zones if _bounds(z)[0] <= value < _bounds(z)[1]]
    if matching:
        best = max(matching, key=lambda z: _SEVERITY.get(z.state, 0))
        return best.state, best
    lowest = min(_bounds(z)[0] for z in zones)
    highest = max(_bounds(z)[1] for z in zones)
    if value < lowest:
        return "out_of_range_low", None
    if value >= highest:
        return "out_of_range_high", None
    return "unrated_gap", None


def validate_zones(key: str, m: Measurement) -> list[str]:
    """Warn on overlapping or gapped adjacent bands (sorted by lower bound)."""
    warnings: list[str] = []
    ordered = sorted(m.zones, key=lambda z: _NEG_INF if z.lower is None else z.lower)
    for a, b in zip(ordered, ordered[1:]):
        a_hi = _POS_INF if a.upper is None else a.upper
        b_lo = _NEG_INF if b.lower is None else b.lower
        # a_hi == b_lo means the bands touch exactly: contiguous, no warning
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
    """Join equipment cards against {equipment_id, path_prefix} bindings.

    Returns (signalk_delta, bindings_map, warnings).
    - signalk_delta: a single delta with a `meta` array, ready to merge into baseDeltas.json
    - bindings_map: full SignalK path -> {equipment_id, measurement}
    - warnings: unknown equipment_ids + per-measurement zone overlaps/gaps
    """
    meta: list[dict] = []
    bindings_map: dict[str, dict] = {}
    warnings: list[str] = []
    for b in bindings:
        eq = vault.get(b["equipment_id"])
        if eq is None:
            warnings.append(f"unknown equipment_id: {b['equipment_id']}")
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
