"""vessel-knowledge-mcp server. Exposes equipment tools over stdio.

Vault from VESSEL_KNOWLEDGE_VAULT_PATH; equipment registry from SignalK (resources/equipment) or VESSEL_KNOWLEDGE_REGISTRY_PATH.
"""
from __future__ import annotations

import asyncio
import json
import logging

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from vessel_knowledge_mcp import tools
from vessel_knowledge_mcp.registry import flatten_bindings, load_registry
from vessel_knowledge_mcp.vault import Vault

logger = logging.getLogger(__name__)


def dispatch(vault: Vault, bindings: dict, name: str, args: dict) -> dict:
    """Route a tool call to its implementation. Shared by the server and tests."""
    if name == "get_equipment":
        return tools.get_equipment(vault, equipment_id=args["equipment_id"])
    if name == "find_equipment":
        return tools.find_equipment(vault, query=args["query"])
    if name == "list_equipment":
        return tools.list_equipment(vault)
    if name == "check_reading":
        return tools.check_reading(vault, equipment_id=args["equipment_id"],
                                   measurement=args["measurement"], value=args["value"],
                                   units=args.get("units"))
    if name == "explain_notification":
        return tools.explain_notification(vault, bindings, path=args["path"],
                                          state=args.get("state"), value=args.get("value"))
    raise ValueError(f"Unknown tool: {name}")


def build_server(vault: Vault, bindings: dict) -> Server:
    server = Server("vessel-knowledge-mcp")

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="explain_notification",
                description=("Explain a SignalK notification: what equipment is on the path, "
                             "its rated zones, the current state, and what to check (manual prose)."),
                inputSchema={"type": "object", "properties": {
                    "path": {"type": "string", "description": "SignalK path that raised the notification"},
                    "state": {"type": "string", "description": "alarm state reported by SignalK"},
                    "value": {"type": "number", "description": "current value, if known"}},
                    "required": ["path"]},
            ),
            types.Tool(
                name="get_equipment",
                description="Full equipment card: specs, part numbers, service intervals, rated zones.",
                inputSchema={"type": "object",
                             "properties": {"equipment_id": {"type": "string"}},
                             "required": ["equipment_id"]},
            ),
            types.Tool(
                name="find_equipment",
                description=("Resolve a free-text query to equipment. Matches any query word "
                             "against id/manufacturer/model/category/aliases, so "
                             "'propulsion motor' or 'watermaker' resolve, not just exact makes."),
                inputSchema={"type": "object", "properties": {"query": {"type": "string"}},
                             "required": ["query"]},
            ),
            types.Tool(
                name="list_equipment",
                description="List every equipment card in the vault (id, manufacturer, model, category).",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="check_reading",
                description=(
                    "Deterministic in/out-of-range verdict for a value against an "
                    "equipment's rated zones. `value` must be in the card's SI units "
                    "(e.g. Kelvin, not degC); pass `units` to have that verified."
                ),
                inputSchema={"type": "object", "properties": {
                    "equipment_id": {"type": "string"},
                    "measurement": {"type": "string"},
                    "value": {"type": "number"},
                    "units": {"type": "string",
                              "description": "Units of `value`; rejected if they differ from the card's units"}},
                    "required": ["equipment_id", "measurement", "value"]},
            ),
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
        result = dispatch(vault, bindings, name, arguments or {})
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    return server


async def _run() -> None:
    vault = Vault.load()
    bindings = flatten_bindings(load_registry())
    logger.info("loaded %d equipment cards, %d bound paths", len(vault.equipment), len(bindings))
    server = build_server(vault, bindings)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
