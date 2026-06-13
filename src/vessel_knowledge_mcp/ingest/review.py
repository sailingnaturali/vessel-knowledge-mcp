"""Render mined candidates into a human-review markdown file.

The review file is the hand-off point: a human verifies each candidate
against the manual page and promotes real limits into the equipment card's
zones (with source_page provenance), then deletes the review file.
"""
from __future__ import annotations

import re
from pathlib import Path

from vessel_knowledge_mcp.ingest.mine import Candidate

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def _fmt_num(v: float) -> str:
    return f"{v:g}"


def _entry(c: Candidate) -> str:
    val = _fmt_num(c.value)
    if c.value_high is not None:
        val = f"{val}–{_fmt_num(c.value_high)}"
    si = ""
    if c.si_value is not None:
        si_val = _fmt_num(c.si_value)
        if c.si_value_high is not None:
            si_val = f"{si_val}–{_fmt_num(c.si_value_high)}"
        si = f" (= {si_val} {c.si_units}, {c.kind})"
    return f"- [ ] **{val} {c.unit}**{si} — `{c.line}` (line {c.line_no})"


def render_review(equipment_id: str, source_pdf: str,
                  candidates: list[Candidate]) -> str:
    lines = [
        f"# Ingest review: {equipment_id}",
        "",
        f"Source: `{source_pdf}` — {len(candidates)} candidates on "
        f"{len({c.page for c in candidates})} pages.",
        "",
        "Verify each value against the manual page, promote the real limits into",
        f"`equipment/{equipment_id}.md` (zones in SI units, `source_page:` pointing at",
        "the PDF page), then delete this file. Values below are MINED CANDIDATES,",
        "not verified limits.",
    ]
    by_page: dict[int, list[Candidate]] = {}
    for c in candidates:
        by_page.setdefault(c.page, []).append(c)
    for page in sorted(by_page):
        lines += ["", f"## Page {page}", ""]
        lines += [_entry(c) for c in by_page[page]]
    return "\n".join(lines) + "\n"


def write_review(vault_root: Path, equipment_id: str, source_pdf: str,
                 content: str) -> Path:
    if not _SLUG_RE.match(equipment_id):
        raise ValueError(
            f"equipment_id {equipment_id!r} is not a valid slug (^[a-z0-9-]+$)")
    out_dir = Path(vault_root) / "reviews"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{equipment_id}--{Path(source_pdf).stem}.md"
    out.write_text(content, encoding="utf-8")
    return out
