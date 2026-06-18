"""Pure discovery pipeline: group self-tree paths by source, match devices to
vault cards, propose registry entries, and diff against the current registry."""
from __future__ import annotations

# Self-tree leaf keys that are value/metadata, not child paths.
_LEAF_KEYS = {"value", "$source", "timestamp", "values", "meta", "pgn", "sentence"}
# Top-level self keys that aren't data paths.
_SELF_SKIP = {"uuid", "name", "mmsi", "type", "url", "version", "$source", "communication"}


def paths_by_source(self_tree: dict) -> dict[str, list[str]]:
    """Map each `$source` to the list of data paths it feeds."""
    out: dict[str, list[str]] = {}

    def walk(node: dict, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        src = node.get("$source")
        if isinstance(src, str):
            out.setdefault(src, []).append(prefix)
            return
        for k, v in node.items():
            if k in _LEAF_KEYS:
                continue
            walk(v, f"{prefix}.{k}" if prefix else k)

    for k, v in self_tree.items():
        if k in _SELF_SKIP:
            continue
        walk(v, k)
    return out
