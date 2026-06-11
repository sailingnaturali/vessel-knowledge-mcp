"""Equipment card model + markdown-frontmatter (de)serialization."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields

import yaml

_FENCE = "---"


@dataclass
class Zone:
    state: str                       # normal | alert | warn | alarm | emergency
    lower: float | None = None
    upper: float | None = None
    message: str | None = None


@dataclass
class Measurement:
    signalk_key: str                 # leaf appended to a bound path-prefix
    units: str                       # SignalK canonical SI units (K, Pa, m/s, ratio...)
    zones: list[Zone] = field(default_factory=list)
    display_units: str | None = None
    source_page: str | None = None


@dataclass
class Equipment:
    equipment_id: str
    manufacturer: str
    model: str
    category: str
    aliases: list[str] = field(default_factory=list)
    part_numbers: list[dict] = field(default_factory=list)
    service_intervals: list[dict] = field(default_factory=list)
    measurements: dict[str, Measurement] = field(default_factory=dict)
    confidence: str | None = None
    source_pdf: str | None = None
    prose: str = ""

    @classmethod
    def from_markdown(cls, text: str) -> "Equipment":
        # Fences are line-anchored: a bare '---' inside a YAML value or the
        # prose must not shift the split (fleet conventions R5).
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].strip() != _FENCE:
            raise ValueError("markdown must start with a '---' frontmatter fence")
        close = next((i for i, ln in enumerate(lines[1:], start=1)
                      if ln.strip() == _FENCE), None)
        if close is None:
            raise ValueError("markdown must have opening and closing '---' frontmatter fences")
        fm = "".join(lines[1:close])
        body = "".join(lines[close + 1:])
        data = yaml.safe_load(fm) or {}
        measurements = {}
        for key, m in (data.get("measurements") or {}).items():
            zones = [Zone(**z) for z in (m.get("zones") or [])]
            mfields = {f.name for f in fields(Measurement)} - {"zones"}
            measurements[key] = Measurement(
                zones=zones, **{k: v for k, v in m.items() if k in mfields}
            )
        known = {f.name for f in fields(cls)} - {"prose", "measurements"}
        kwargs = {k: v for k, v in data.items() if k in known}
        try:
            return cls(prose=body.lstrip("\n"), measurements=measurements, **kwargs)
        except TypeError as exc:
            raise ValueError(f"equipment card missing required field: {exc}") from exc

    def to_markdown(self) -> str:
        data = {k: v for k, v in asdict(self).items() if k not in ("prose",)}
        # asdict() already turned nested dataclasses into dicts; drop empty zone fields.
        for m in data.get("measurements", {}).values():
            m["zones"] = [{k: v for k, v in z.items() if v is not None} for z in m["zones"]]
            for k in [k for k, v in list(m.items()) if v is None]:
                del m[k]
        data = {k: v for k, v in data.items() if v not in (None, [], {}, "")}
        fm = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
        return f"{_FENCE}\n{fm}\n{_FENCE}\n{self.prose}"
