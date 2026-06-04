"""Load a markdown equipment vault from disk."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from vessel_knowledge_mcp.models import Equipment


def vault_path() -> Path:
    """Vault directory from VESSEL_KNOWLEDGE_VAULT_PATH (default ~/.vessel-knowledge-vault)."""
    return Path(
        os.environ.get("VESSEL_KNOWLEDGE_VAULT_PATH", "~/.vessel-knowledge-vault")
    ).expanduser()


@dataclass
class Vault:
    root: Path
    equipment: list[Equipment]

    @classmethod
    def load(cls, root: Path | None = None) -> "Vault":
        root = Path(root) if root is not None else vault_path()
        equipment: list[Equipment] = []
        eq_dir = root / "equipment"
        if eq_dir.is_dir():
            for md in sorted(eq_dir.rglob("*.md")):
                equipment.append(Equipment.from_markdown(md.read_text(encoding="utf-8")))
        return cls(root=root, equipment=equipment)

    def get(self, equipment_id: str) -> Equipment | None:
        target = equipment_id.strip().casefold()
        for e in self.equipment:
            if e.equipment_id.casefold() == target:
                return e
        return None
