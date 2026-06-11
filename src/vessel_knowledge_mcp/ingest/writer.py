"""Write equipment cards into the vault; track which source pages are already covered."""
from __future__ import annotations

import re
from pathlib import Path

from vessel_knowledge_mcp.models import Equipment

_PAGE_RE = re.compile(r"source_pdf:\s*['\"]?([^'\"#]+)#page=(\d+)")
# equipment_id becomes a filename: slug-only, no traversal (fleet conventions R5).
_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def write_card(vault_root: Path, eq: Equipment, *, source_pdf: str, page: int) -> Path:
    if not _SLUG_RE.match(eq.equipment_id):
        raise ValueError(
            f"equipment_id {eq.equipment_id!r} is not a valid slug "
            "(^[a-z0-9-]+$) — refusing to build a vault path from it"
        )
    eq.source_pdf = f"{source_pdf}#page={page}"
    eq_dir = Path(vault_root) / "equipment"
    eq_dir.mkdir(parents=True, exist_ok=True)
    path = eq_dir / f"{eq.equipment_id}.md"
    path.write_text(eq.to_markdown(), encoding="utf-8")
    return path


def covered_pages(vault_root: Path, source_pdf: str) -> set[int]:
    """Pages of source_pdf already represented by a card (for resumable ingest)."""
    eq_dir = Path(vault_root) / "equipment"
    covered: set[int] = set()
    if not eq_dir.is_dir():
        return covered
    for md in eq_dir.rglob("*.md"):
        for pdf, page in _PAGE_RE.findall(md.read_text(encoding="utf-8")):
            if pdf.strip() == source_pdf:
                covered.add(int(page))
    return covered
