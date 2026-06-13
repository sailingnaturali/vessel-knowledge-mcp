"""Deterministic candidate mining: numeric spec values near unit tokens.

No model in the data path (issue #7). Mining finds *candidates*; a human
promotes verified values into the equipment card. SI conversions are fixed
arithmetic into SignalK canonical units (K, Pa, W, Hz, m3/s).
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

# unit key -> (kind, si_units, converter)
_CONVERSIONS: dict[str, tuple[str, str, Callable[[float], float]]] = {
    "degC": ("temperature", "K", lambda v: round(v + 273.15, 4)),
    "bar":  ("pressure", "Pa", lambda v: v * 100_000.0),
    "kPa":  ("pressure", "Pa", lambda v: v * 1_000.0),
    "psi":  ("pressure", "Pa", lambda v: v * 6_894.757),
    "Pa":   ("pressure", "Pa", lambda v: v),
    "kW":   ("power", "W", lambda v: v * 1_000.0),
    "W":    ("power", "W", lambda v: v),
    "V":    ("voltage", "V", lambda v: v),
    "A":    ("current", "A", lambda v: v),
    "rpm":  ("rotation", "Hz", lambda v: v / 60.0),
    "L/h":  ("flow", "m3/s", lambda v: v * 0.001 / 3600.0),
}


def to_si(value: float, unit: str) -> tuple[float | None, str | None]:
    """Convert a value in a mined unit to SignalK canonical SI, or (None, None)."""
    entry = _CONVERSIONS.get(unit)
    if entry is None:
        return (None, None)
    _, si_units, conv = entry
    return (conv(value), si_units)


def kind_of(unit: str) -> str:
    entry = _CONVERSIONS.get(unit)
    return entry[0] if entry else "other"
