"""Pure implementations of the MCP tools. No I/O beyond the Vault + bindings map."""
from __future__ import annotations

from dataclasses import asdict

from vessel_knowledge_mcp.vault import Vault
from vessel_knowledge_mcp.zones import classify_reading

# Human messages for the abnormal verdicts classify_reading can return.
_ABNORMAL_MESSAGES = {
    "no_zones": "no rated zones on this measurement — cannot judge the reading",
    "fault": "reading is not a number — suspect a sensor fault",
    "out_of_range_low": "value is below the lowest rated band — abnormal, low side",
    "out_of_range_high": "value is above the highest rated band — abnormal, high side",
    "unrated_gap": "value falls in a gap between rated bands — card may be incomplete",
}


def _card_dict(eq) -> dict:
    return asdict(eq)


def get_equipment(vault: Vault, equipment_id: str) -> dict:
    eq = vault.get(equipment_id)
    if eq is None:
        return {"found": False, "equipment_id": equipment_id}
    return {"found": True, "equipment": _card_dict(eq)}


def _summary(e) -> dict:
    return {"equipment_id": e.equipment_id, "manufacturer": e.manufacturer,
            "model": e.model, "category": e.category}


def find_equipment(vault: Vault, query: str) -> dict:
    """Resolve a free-text query to equipment. Matches if any query word (>=2 chars)
    is a substring of any of the card's id/manufacturer/model/category/aliases — so
    multi-word, category-style queries like "propulsion motor" resolve.
    Exact field hits rank above substring hits ("ddw-10" before "ddw-100").
    """
    tokens = [t for t in query.strip().casefold().split() if len(t) >= 2]
    matches: list[tuple[int, dict]] = []
    for e in vault.equipment:
        hay = [f.casefold() for f in (e.equipment_id, e.manufacturer, e.model,
                                      e.category, *e.aliases) if f]
        if tokens and any(tok in h for tok in tokens for h in hay):
            exact = any(tok == h for tok in tokens for h in hay)
            matches.append((0 if exact else 1, _summary(e)))
    matches.sort(key=lambda t: t[0])           # stable: insertion order within rank
    return {"matches": [m for _, m in matches]}


def list_equipment(vault: Vault) -> dict:
    """Every equipment card in the vault (id, manufacturer, model, category)."""
    return {"equipment": [_summary(e) for e in vault.equipment]}


def check_reading(vault: Vault, equipment_id: str, measurement: str, value: float,
                  units: str | None = None) -> dict:
    """Judge a reading against the card's rated zones.

    ``value`` MUST be in the card's (SI) units; pass ``units`` to have that
    checked — a mismatch is rejected rather than silently judged against the
    wrong scale (95 degC vs a Kelvin band would read as a benign under-range).
    """
    eq = vault.get(equipment_id)
    if eq is None:
        return {"found": False, "equipment_id": equipment_id}
    m = eq.measurements.get(measurement)
    if m is None:
        return {"found": False, "equipment_id": equipment_id,
                "error": f"no measurement '{measurement}' on {equipment_id}"}
    if units is not None and units != m.units:
        return {"found": False, "equipment_id": equipment_id,
                "error": f"unit mismatch: value given in '{units}' but the card's "
                         f"zones are in '{m.units}' — convert before checking"}
    state, z = classify_reading(m.zones, value)
    return {
        "found": True, "equipment_id": equipment_id, "measurement": measurement,
        "value": value, "units": m.units, "display_units": m.display_units,
        "state": state,
        "message": z.message if z else _ABNORMAL_MESSAGES.get(state),
    }


def explain_notification(vault: Vault, bindings: dict, path: str,
                         state: str | None = None, value: float | None = None) -> dict:
    # SignalK fires notifications.<data-path>; bindings are keyed by the bare
    # data path (mirrors signalk-mcp's prefix stripping). Echo the path as given.
    lookup = path.removeprefix("notifications.")
    binding = bindings.get(lookup)
    if binding is None:
        return {"found": False, "path": path,
                "error": f"no equipment bound to '{lookup}'"}
    eq = vault.get(binding["equipment_id"])
    if eq is None:
        return {"found": False, "path": path,
                "error": f"bound equipment '{binding['equipment_id']}' not in vault"}
    measurement = binding["measurement"]
    m = eq.measurements.get(measurement)
    state_mismatch = False
    if value is not None:
        verdict = check_reading(vault, eq.equipment_id, measurement, value)
        state_out = verdict.get("state", state)
        message = verdict.get("message")
        # The fired state and the value-derived state can disagree (stale
        # notification, drifted zones) — say so instead of silently picking one.
        state_mismatch = state is not None and state_out != state
    else:
        state_out = state
        message = None
        if m is not None and state is not None:
            for z in m.zones:
                if z.state == state:
                    message = z.message
                    break
    return {
        "found": True, "path": path, "equipment_id": eq.equipment_id,
        "manufacturer": eq.manufacturer, "model": eq.model, "measurement": measurement,
        "reported_state": state,
        "state": state_out,
        "state_mismatch": state_mismatch,
        "message": message,
        "units": m.units if m else None,
        "display_units": m.display_units if m else None,
        "rated_zones": [_zone_summary(z) for z in (m.zones if m else [])],
        "prose": eq.prose,
    }


def _zone_summary(z) -> dict:
    return {"state": z.state, "lower": z.lower, "upper": z.upper, "message": z.message}
