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


@dataclass
class Candidate:
    page: int                 # true PDF page number (1-based)
    line_no: int              # 1-based within the page
    line: str                 # verbatim source line (stripped)
    value: float
    unit: str                 # normalized unit key from _CONVERSIONS
    kind: str
    value_high: float | None = None       # set for ranges like "7-8 bar"
    si_value: float | None = None
    si_value_high: float | None = None
    si_units: str | None = None


_NUM = r"\d+(?:[.,]\d+)?"

# Unit token regexes -> normalized unit key. Order matters: longer/more
# specific tokens first so "kW" isn't matched as "W" and "Vdc" not as "V".
_UNIT_TOKENS: list[tuple[str, str]] = [
    # "celcius" tolerated: the Oceanvolt SP25 manual misspells it on the very
    # page that carries the controller warning threshold.
    (r"(?:°\s*C|℃|deg\s*C|cel[sc]ius)", "degC"),
    (r"kPa\b", "kPa"),
    (r"Pa\b", "Pa"),
    (r"bar\b", "bar"),
    (r"psi\b", "psi"),
    (r"kW\b", "kW"),
    (r"[Ww]att(?:s)?\b", "W"),
    (r"W\b", "W"),
    (r"V(?:dc|DC|ac|AC)?\b", "V"),
    (r"A\b", "A"),
    (r"rpm\b", "rpm"),
    (r"(?:L|[Ll]it\.?)\s*/\s*h(?:our)?\b", "L/h"),
]


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _patterns() -> list[tuple[re.Pattern, str, bool]]:
    """(compiled pattern, unit key, is_range) — ranges first per unit."""
    pats: list[tuple[re.Pattern, str, bool]] = []
    for token_re, unit in _UNIT_TOKENS:
        pats.append((re.compile(
            rf"(?<![\w.,])({_NUM})\s*[-–—]\s*({_NUM})\s*{token_re}"), unit, True))
        pats.append((re.compile(
            rf"(?<![\w.,])({_NUM})\s*{token_re}"), unit, False))
    return pats


_PATTERNS = _patterns()


def mine_page(text: str, page_no: int) -> list[Candidate]:
    out: list[Candidate] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        consumed: list[tuple[int, int]] = []
        found: list[tuple[int, Candidate]] = []
        for pattern, unit, is_range in _PATTERNS:
            for m in pattern.finditer(line):
                span = m.span()
                if any(span[0] < e and span[1] > s for s, e in consumed):
                    continue  # inside an already-matched (range) span
                consumed.append(span)
                value = _num(m.group(1))
                value_high = _num(m.group(2)) if is_range else None
                si_value, si_units = to_si(value, unit)
                si_high = to_si(value_high, unit)[0] if value_high is not None else None
                found.append((span[0], Candidate(
                    page=page_no, line_no=line_no, line=line,
                    value=value, value_high=value_high, unit=unit,
                    kind=kind_of(unit), si_value=si_value,
                    si_value_high=si_high, si_units=si_units)))
        out.extend(c for _, c in sorted(found, key=lambda t: t[0]))
    return out


def mine_pages(pages: list[str]) -> list[Candidate]:
    """Mine every page; page numbers are 1-based true PDF pages."""
    out: list[Candidate] = []
    for page_no, text in enumerate(pages, start=1):
        if text.strip():
            out.extend(mine_page(text, page_no))
    return out
