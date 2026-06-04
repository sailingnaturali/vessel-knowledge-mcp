import pytest

from vessel_knowledge_mcp.models import Equipment, Measurement, Zone

CARD = """\
---
equipment_id: bellmarine-ddw-10
manufacturer: Bellmarine
model: DDW-10
category: propulsion
aliases: ["Bellmarine DDW 10kW", "DDW10"]
part_numbers:
  - { part: "IMP-2024", description: "raw-water impeller" }
service_intervals:
  - { task: "impeller inspection", interval: "annual", source_page: "m.pdf#page=51" }
measurements:
  temperature:
    signalk_key: temperature
    units: K
    display_units: degC
    source_page: "m.pdf#page=42"
    zones:
      - { state: normal, lower: 273.15, upper: 353.15 }
      - { state: warn, lower: 353.15, upper: 368.15, message: "Motor temp high" }
      - { state: alarm, lower: 368.15, message: "Over-temp" }
confidence: high
source_pdf: "m.pdf"
---
Manual prose about the motor.
"""


def test_from_markdown_parses_nested_measurements():
    eq = Equipment.from_markdown(CARD)
    assert eq.equipment_id == "bellmarine-ddw-10"
    assert eq.aliases == ["Bellmarine DDW 10kW", "DDW10"]
    temp = eq.measurements["temperature"]
    assert isinstance(temp, Measurement)
    assert temp.units == "K"
    assert temp.display_units == "degC"
    assert isinstance(temp.zones[0], Zone)
    assert temp.zones[0].upper == 353.15
    assert temp.zones[2].lower == 368.15 and temp.zones[2].upper is None
    assert eq.prose.strip() == "Manual prose about the motor."


def test_round_trips_through_markdown():
    eq = Equipment.from_markdown(CARD)
    again = Equipment.from_markdown(eq.to_markdown())
    assert again.equipment_id == eq.equipment_id
    assert again.measurements["temperature"].zones[1].message == "Motor temp high"
    assert again.part_numbers == eq.part_numbers
    assert again.prose == eq.prose


def test_from_markdown_rejects_single_fence():
    bad = "---\nequipment_id: x\nmodel: y\ncategory: z\nManual prose with no closing fence.\n"
    with pytest.raises(ValueError):
        Equipment.from_markdown(bad)


def test_from_markdown_rejects_missing_required_fields():
    bad = "---\nequipment_id: x\nmanufacturer: Acme\n---\nProse.\n"
    with pytest.raises(ValueError):
        Equipment.from_markdown(bad)
