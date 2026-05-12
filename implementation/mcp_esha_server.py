"""MCP stdio server exposing the ESHA audit workbench.

Wraps implementation/esha_audit_api.py over stdio. Tool schemas come from
nebius_esha_tool_worker.TOOLS so Nebius and Claude Code see the same surface.

Usage:
    python3 implementation/mcp_esha_server.py               # normal MCP stdio
    python3 implementation/mcp_esha_server.py --self-test   # emit tools JSON, exit
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "implementation"))

from nebius_esha_tool_worker import TOOLS  # noqa: E402

AUDIT_API = os.environ.get("ESHA_AUDIT_API", "http://127.0.0.1:8765")


TOOL_ROUTES = {
    "get_card":                  ("GET", "/card",             ["esha_code", "max_chars"]),
    "search_products":           ("GET", "/search-products",  ["query", "category", "limit"]),
    "cross_reference":           ("GET", "/cross-reference",  ["esha_code", "limit"]),
    "matrix_slice":              ("GET", "/matrix",           ["esha_code", "limit", "rebuild"]),
    "get_contract_source":       ("GET", "/contract",         ["esha_code", "max_chars"]),
    "get_queue":                 ("GET", "/queue",            ["limit", "status", "priority"]),
    "list_cards":                ("GET", "/cards",            ["limit", "offset", "family"]),
    "product_codes":             ("GET", "/product-codes",    ["esha_code", "limit"]),
    "collisions":                ("GET", "/collisions",       ["esha_code", "limit"]),
    "compare_nutrient_fingerprint": ("GET", "/nutrient-compare", ["esha_codes"]),
    "recipe_context":            ("GET", "/recipe-context",   ["recipe_id"]),
    "prior_decisions":           ("GET", "/prior-decisions",  ["normalized_item"]),
    "trace_entity":              ("GET", "/trace",            ["kind", "key", "limit"]),
}


def _translate_args(name: str, args: dict) -> dict:
    """Map tool arguments into the audit API's expected query-param shape."""
    out: dict[str, str] = {}
    for k, v in (args or {}).items():
        if v is None:
            continue
        if name == "compare_nutrient_fingerprint" and k == "esha_codes":
            out["codes"] = ",".join(str(int(c)) for c in v)
        elif isinstance(v, bool):
            out[k] = "true" if v else "false"
        elif isinstance(v, (list, tuple)):
            out[k] = ",".join(str(x) for x in v)
        else:
            out[k] = str(v)
    return out


def _http_get(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{AUDIT_API}{path}?{qs}", timeout=30) as r:
        return json.loads(r.read())


def dispatch(name: str, arguments: dict) -> dict:
    if name not in TOOL_ROUTES:
        return {"error": "unknown_tool", "name": name}
    _, path, _ = TOOL_ROUTES[name]
    return _http_get(path, _translate_args(name, arguments))


def self_test() -> None:
    tools = [t["function"] for t in TOOLS]
    json.dump({"tools": tools}, sys.stdout)


async def run_mcp() -> None:
    # Lazy import — only required for stdio mode
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    import mcp.types as types

    server = Server("esha-audit-workbench")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=t["function"]["name"],
                description=t["function"]["description"],
                inputSchema=t["function"]["parameters"],
            )
            for t in TOOLS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        result = dispatch(name, arguments)
        return [types.TextContent(type="text", text=json.dumps(result))]

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    asyncio.run(run_mcp())


if __name__ == "__main__":
    main()
