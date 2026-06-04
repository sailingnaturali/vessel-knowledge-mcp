"""Pure implementations of the MCP tools. No I/O beyond the Vault + bindings map."""
from __future__ import annotations

from dataclasses import asdict

from vessel_knowledge_mcp.vault import Vault
from vessel_knowledge_mcp.zones import zone_for


def _card_dict(eq) -> dict:
    return asdict(eq)


def get_equipment(vault: Vault, equipment_id: str) -> dict:
    eq = vault.get(equipment_id)
    if eq is None:
        return {"found": False, "equipment_id": equipment_id}
    return {"found": True, "equipment": _card_dict(eq)}


def find_equipment(vault: Vault, query: str) -> dict:
    q = query.strip().casefold()
    matches = []
    for e in vault.equipment:
        haystack = [e.equipment_id, e.manufacturer, e.model, *e.aliases]
        if any(q in h.casefold() for h in haystack if h):
            matches.append({"equipment_id": e.equipment_id,
                            "manufacturer": e.manufacturer, "model": e.model})
    return {"matches": matches}


def check_reading(vault: Vault, equipment_id: str, measurement: str, value: float) -> dict:
    eq = vault.get(equipment_id)
    if eq is None:
        return {"found": False, "equipment_id": equipment_id}
    m = eq.measurements.get(measurement)
    if m is None:
        return {"found": False, "equipment_id": equipment_id,
                "error": f"no measurement '{measurement}' on {equipment_id}"}
    z = zone_for(m.zones, value)
    return {
        "found": True, "equipment_id": equipment_id, "measurement": measurement,
        "value": value, "units": m.units, "display_units": m.display_units,
        "state": z.state if z else "unknown",
        "message": z.message if z else None,
    }


def explain_notification(vault: Vault, bindings: dict, path: str,
                         state: str | None = None, value: float | None = None) -> dict:
    binding = bindings.get(path)
    if binding is None:
        return {"found": False, "path": path,
                "error": f"no equipment bound to '{path}'"}
    eq = vault.get(binding["equipment_id"])
    if eq is None:
        return {"found": False, "path": path,
                "error": f"bound equipment '{binding['equipment_id']}' not in vault"}
    measurement = binding["measurement"]
    m = eq.measurements.get(measurement)
    if value is not None:
        verdict = check_reading(vault, eq.equipment_id, measurement, value)
        state_out = verdict.get("state", state)
        message = verdict.get("message")
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
        "message": message,
        "units": m.units if m else None,
        "display_units": m.display_units if m else None,
        "rated_zones": [_zone_summary(z) for z in (m.zones if m else [])],
        "prose": eq.prose,
    }


def _zone_summary(z) -> dict:
    return {"state": z.state, "lower": z.lower, "upper": z.upper, "message": z.message}
