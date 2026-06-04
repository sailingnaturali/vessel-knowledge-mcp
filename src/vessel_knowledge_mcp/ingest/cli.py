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


def _cmd_ingest(args) -> int:
    # Heavy path: requires the `ingest` extra (anthropic) + pdftotext.
    import anthropic

    from vessel_knowledge_mcp.ingest.extract import extract_equipment
    from vessel_knowledge_mcp.ingest.pdf import page_texts
    from vessel_knowledge_mcp.ingest.writer import covered_pages, write_card

    vault_root = Path(args.vault)
    source_pdf = Path(args.pdf).name
    done = set() if args.force else covered_pages(vault_root, source_pdf)
    client = anthropic.Anthropic()
    written = 0
    for i, page in enumerate(page_texts(args.pdf), start=1):
        if i in done:
            continue
        eq = extract_equipment(page, source=args.source or source_pdf, client=client)
        if eq is None:
            continue
        write_card(vault_root, eq, source_pdf=source_pdf, page=i)
        written += 1
        print(f"page {i}: {eq.equipment_id}")
    print(f"Ingested {written} cards from {source_pdf}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vessel-knowledge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="extract equipment cards from a manual PDF")
    p_ingest.add_argument("pdf")
    p_ingest.add_argument("--vault", required=True)
    p_ingest.add_argument("--source", help="human source label (default: PDF filename)")
    p_ingest.add_argument("--force", action="store_true", help="re-ingest already-covered pages")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_index = sub.add_parser("index", help="regenerate INDEX.md")
    p_index.add_argument("--vault", required=True)
    p_index.set_defaults(func=_cmd_index)

    p_zones = sub.add_parser("zones", help="emit a SignalK meta-zones delta from bindings")
    p_zones.add_argument("--vault", required=True)
    p_zones.add_argument("--bindings", required=True,
                         help="JSON list of {model, path_prefix}")
    p_zones.add_argument("--out-bindings", help="write the path->equipment bindings map here")
    p_zones.add_argument("--strict", action="store_true",
                         help="exit non-zero on any zone warning")
    p_zones.set_defaults(func=_cmd_zones)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
