"""Claude structured tool-use extraction of one Equipment card from a manual page.

Forced tool use -> no free-text JSON to parse. Instructions + schema are marked for
prompt caching (identical across every page of a manual). Zones MUST be in SignalK
canonical SI units (Kelvin, Pascal, m/s, ratio) so SignalK can compare them directly.
"""
from __future__ import annotations

from vessel_knowledge_mcp.models import Equipment, Measurement, Zone

_INSTRUCTIONS = """\
You are given the extracted text of ONE page of a marine equipment manual or spec sheet.

If the page specifies an identifiable piece of equipment (a model with ratings, specs,
or operating limits), call `record_equipment` with its fields. Otherwise call
`record_equipment` with is_equipment=false (cover, table of contents, legal, generic intro).

equipment_id: a stable lowercase slug like "bellmarine-ddw-10".
measurements: a map keyed by measurement name (temperature, voltage, rpm, pressure...).
Each measurement has a signalk_key (the SignalK leaf, e.g. "temperature", "voltage"),
units, and zones.

CRITICAL — units: express units and all zone bounds in SignalK CANONICAL SI units:
temperature in KELVIN (degC + 273.15), pressure in PASCAL, speed in m/s, ratios 0..1,
angles in radians. Put the human-facing unit (e.g. degC) in display_units. If the
manual gives 0-80 degC normal, emit lower: 273.15, upper: 353.15.

zones: ordered bands with state in [normal, alert, warn, alarm, emergency], each with
lower and/or upper (omit a bound for open-ended) and an optional message. Set confidence
to your confidence in the extracted ranges. Put the cleaned manual prose in prose.
"""

_STATES = ["normal", "alert", "warn", "alarm", "emergency"]

EQUIPMENT_TOOL = {
    "name": "record_equipment",
    "description": "Record one equipment model's structured spec card from the page.",
    "input_schema": {
        "type": "object",
        "properties": {
            "is_equipment": {"type": "boolean",
                             "description": "false if the page specifies no equipment"},
            "equipment_id": {"type": "string"},
            "manufacturer": {"type": "string"},
            "model": {"type": "string"},
            "category": {"type": "string",
                         "enum": ["propulsion", "electrical", "tankage", "watermaker",
                                  "climate", "navigation", "other"]},
            "aliases": {"type": "array", "items": {"type": "string"}},
            "part_numbers": {"type": "array", "items": {"type": "object", "properties": {
                "part": {"type": "string"}, "description": {"type": "string"}}}},
            "service_intervals": {"type": "array", "items": {"type": "object", "properties": {
                "task": {"type": "string"}, "interval": {"type": "string"},
                "source_page": {"type": "string"}}}},
            "measurements": {"type": "object", "additionalProperties": {"type": "object",
                "properties": {
                    "signalk_key": {"type": "string"},
                    "units": {"type": "string", "description": "SignalK canonical SI unit"},
                    "display_units": {"type": "string"},
                    "source_page": {"type": "string"},
                    "zones": {"type": "array", "items": {"type": "object", "properties": {
                        "state": {"type": "string", "enum": _STATES},
                        "lower": {"type": "number"}, "upper": {"type": "number"},
                        "message": {"type": "string"}}, "required": ["state"]}}},
                "required": ["signalk_key", "units", "zones"]}},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "prose": {"type": "string"},
        },
        "required": ["is_equipment"],
    },
    "cache_control": {"type": "ephemeral"},
}


def build_system_prompt() -> list[dict]:
    return [{"type": "text", "text": _INSTRUCTIONS, "cache_control": {"type": "ephemeral"}}]


def extract_equipment(chunk: str, source: str, *, client,
                      model: str = "claude-sonnet-4-6") -> Equipment | None:
    """Extract one page into an Equipment card, or None if the page has no equipment."""
    resp = client.messages.create(
        model=model, max_tokens=2000, system=build_system_prompt(),
        tools=[EQUIPMENT_TOOL], tool_choice={"type": "tool", "name": "record_equipment"},
        messages=[{"role": "user", "content": f"Source: {source}\n\n{chunk}"}],
    )
    data = None
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "record_equipment":
            data = dict(block.input) if block.input is not None else None
            break
    if not data or data.get("is_equipment") is False or "equipment_id" not in data:
        return None
    data.pop("is_equipment", None)
    measurements = {}
    for key, m in (data.pop("measurements", None) or {}).items():
        zones = [Zone(**{k: v for k, v in z.items() if k in {"state", "lower", "upper", "message"}})
                 for z in (m.get("zones") or [])]
        measurements[key] = Measurement(
            signalk_key=m["signalk_key"], units=m["units"], zones=zones,
            display_units=m.get("display_units"), source_page=m.get("source_page"))
    known = set(Equipment.__dataclass_fields__) - {"measurements", "source_pdf"}
    return Equipment(measurements=measurements,
                     **{k: v for k, v in data.items() if k in known})
