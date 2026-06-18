"""Extract N2K device identity from a SignalK sources tree.

ALL knowledge of the served sources-tree N2K shape lives here, so a real-hardware
quirk (field spelling, manufacturerCode as int vs name) is a one-file change.
Validated end-to-end by the virtual-device harness (tests/harness/).
"""
from __future__ import annotations

from dataclasses import dataclass

# NMEA 2000 manufacturer codes -> name. Extend as needed; unknown codes leave
# `manufacturer` None and the model string still drives matching.
MANUFACTURER_CODES: dict[int, str] = {
    358: "Victron Energy",
    847: "Oceanvolt",
}


@dataclass
class DiscoveredDevice:
    source_ref: str
    manufacturer_code: int | None
    manufacturer: str | None
    model: str | None
    serial: str | None


def parse_devices(sources_tree: dict) -> list[DiscoveredDevice]:
    devices: list[DiscoveredDevice] = []
    for label, srcs in sources_tree.items():
        if not isinstance(srcs, dict):
            continue
        for key, sub in srcs.items():
            if not isinstance(sub, dict):
                continue
            n2k = sub.get("n2k")
            if not isinstance(n2k, dict):
                continue
            raw = n2k.get("manufacturerCode")
            if raw is None:
                continue
            if isinstance(raw, str):
                manufacturer, code = raw, None
            else:
                manufacturer, code = MANUFACTURER_CODES.get(raw), raw
            devices.append(DiscoveredDevice(
                source_ref=f"{label}.{key}",
                manufacturer_code=code,
                manufacturer=manufacturer,
                model=n2k.get("modelId"),
                serial=n2k.get("modelSerialCode"),
            ))
    return devices
