"""CLI: vessel-knowledge ingest|index|zones."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vessel_knowledge_mcp.vault import Vault
from vessel_knowledge_mcp.zones import generate_zones


def _cmd_zones(args) -> int:
    vault = Vault.load(Path(args.vault))
    bindings = json.loads(Path(args.bindings).read_text(encoding="utf-8"))
    delta, bindings_map, warnings = generate_zones(vault, bindings)
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    if warnings and args.strict:
        print("strict: refusing to emit zones with warnings", file=sys.stderr)
        return 1
    if args.out_bindings:
        Path(args.out_bindings).write_text(json.dumps(bindings_map, indent=2), encoding="utf-8")
    print(json.dumps(delta, indent=2))
    return 0


def _cmd_index(args) -> int:
    vault = Vault.load(Path(args.vault))
    lines = ["# Equipment Index", ""]
    for e in sorted(vault.equipment, key=lambda e: e.equipment_id):
        lines.append(f"- **{e.manufacturer} {e.model}** (`{e.equipment_id}`) — "
                     f"{', '.join(e.measurements) or 'no measurements'}")
    (Path(args.vault) / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {Path(args.vault) / 'INDEX.md'} ({len(vault.equipment)} cards)")
    return 0


def _cmd_migrate_bindings(args) -> int:
    from vessel_knowledge_mcp.registry import migrate_bindings

    bindings = json.loads(Path(args.bindings).read_text(encoding="utf-8"))
    vault = Vault.load(Path(args.vault)) if args.vault else Vault.load()
    registry = migrate_bindings(bindings, vault)
    Path(args.out).write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(registry)} instances to {args.out}")
    return 0


def _cmd_ingest(args) -> int:
    # Deterministic pipeline (issue #7): pdftotext -> regex mining -> review
    # file. No model in the data path; never mints new equipment IDs.
    from vessel_knowledge_mcp.ingest import pdf
    from vessel_knowledge_mcp.ingest.mine import mine_pages
    from vessel_knowledge_mcp.ingest.review import render_review, write_review

    vault_root = Path(args.vault)
    card = vault_root / "equipment" / f"{args.equipment_id}.md"
    if not card.is_file():
        print(f"no card at {card} — create the equipment card first; "
              "ingest mines review candidates for an existing card",
              file=sys.stderr)
        return 1
    pages = pdf.page_texts(args.pdf)
    candidates = mine_pages(pages)
    source_pdf = Path(args.pdf).name
    out = write_review(vault_root, args.equipment_id, source_pdf,
                       render_review(args.equipment_id, source_pdf, candidates))
    print(f"{len(candidates)} candidates on {len({c.page for c in candidates})} "
          f"pages -> {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vessel-knowledge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser(
        "ingest",
        help="mine spec candidates from a manual PDF into a review file")
    p_ingest.add_argument("pdf")
    p_ingest.add_argument("--vault", required=True)
    p_ingest.add_argument("--equipment-id", required=True,
                          help="existing card the candidates are for "
                               "(ingest never creates new equipment IDs)")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_index = sub.add_parser("index", help="regenerate INDEX.md")
    p_index.add_argument("--vault", required=True)
    p_index.set_defaults(func=_cmd_index)

    p_mig = sub.add_parser("migrate-bindings",
        help="convert a legacy bindings.json into an equipment-registry.json")
    p_mig.add_argument("bindings")
    p_mig.add_argument("--vault")
    p_mig.add_argument("--out", required=True)
    p_mig.set_defaults(func=_cmd_migrate_bindings)

    p_zones = sub.add_parser("zones", help="emit a SignalK meta-zones delta from bindings")
    p_zones.add_argument("--vault", required=True)
    p_zones.add_argument("--bindings", required=True,
                         help="JSON list of {equipment_id, path_prefix}")
    p_zones.add_argument("--out-bindings", help="write the path->equipment bindings map here")
    p_zones.add_argument("--strict", action="store_true",
                         help="exit non-zero on any zone warning")
    p_zones.set_defaults(func=_cmd_zones)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
