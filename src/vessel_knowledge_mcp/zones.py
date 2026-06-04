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
