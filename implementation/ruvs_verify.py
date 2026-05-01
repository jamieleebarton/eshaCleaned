"""B2: call DeepSeek with tools, collect verdict JSON, return LineVerdict."""
from __future__ import annotations
import datetime as _dt
import json
from typing import Any

from ruvs.schemas import Packet, LineVerdict, FACETS, FACET_ENUMS
from ruvs.prompts import build_stamp_messages
from ruvs.tools.walmart import WALMART_TOOL_SCHEMA, walmart_search
from ruvs.tools.kroger import KROGER_TOOL_SCHEMA, kroger_search
from ruvs.tools.flag_grams_suspect import FLAG_GRAMS_TOOL_SCHEMA, flag_grams_suspect
from ruvs.nebius import NebiusClient, ToolCall, MessageResult

MAX_TOOL_CALLS_PER_LINE = 8

_TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": s["name"], "description": s["description"],
                                       "parameters": s["input_schema"]}}
    for s in (WALMART_TOOL_SCHEMA, KROGER_TOOL_SCHEMA, FLAG_GRAMS_TOOL_SCHEMA)
]


def verify_line(*, packet: Packet, client: NebiusClient, run_id: str) -> LineVerdict:
    messages = build_stamp_messages(packet)
    tool_calls_log: list[dict[str, Any]] = []
    grams_flags: list[str] = []
    total_cost = 0.0
    for _iteration in range(MAX_TOOL_CALLS_PER_LINE + 1):
        result: MessageResult = client.chat(messages=messages, tools=_TOOL_SCHEMAS)
        total_cost += result.cost_usd
        if not result.tool_calls:
            return _parse_verdict(
                result.content, packet, run_id, client_model=client.model,
                evidence={"tool_calls": tool_calls_log, "cost_usd": total_cost,
                          "grams_flags": grams_flags, "audit_match": packet.audit_candidates[:1]},
            )
        # dispatch tool calls and append tool messages, then continue loop
        messages.append({
            "role": "assistant",
            "content": result.content or "",
            "tool_calls": [{"id": tc.id, "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                           for tc in result.tool_calls],
        })
        for tc in result.tool_calls:
            output = _dispatch_tool(tc)
            tool_calls_log.append({"name": tc.name, "args": tc.arguments, "output_summary": _summary(output)})
            if tc.name == "flag_grams_suspect":
                grams_flags.append(tc.arguments.get("reason", ""))
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(output)})
    # exceeded budget of tool turns
    return _ambiguous_loop_exceeded(packet, run_id, client.model, tool_calls_log, total_cost)


def _dispatch_tool(tc: ToolCall) -> Any:
    if tc.name == "walmart_search":
        return [_pc_to_dict(c) for c in walmart_search(tc.arguments.get("query", ""),
                                                       limit=int(tc.arguments.get("limit", 10)))]
    if tc.name == "kroger_search":
        return [_pc_to_dict(c) for c in kroger_search(tc.arguments.get("query", ""),
                                                      limit=int(tc.arguments.get("limit", 10)))]
    if tc.name == "flag_grams_suspect":
        return flag_grams_suspect(reason=tc.arguments.get("reason", ""))
    return {"error": f"unknown tool: {tc.name}"}


def _pc_to_dict(c) -> dict:
    return {"upc": c.upc, "title": c.title, "grams": c.grams, "price_cents": c.price_cents, "retail": c.retail}


def _summary(output: Any) -> str:
    if isinstance(output, list):
        return f"{len(output)} results"
    if isinstance(output, dict):
        return output.get("status", "ok")
    return str(type(output))


def _parse_verdict(content: str, packet: Packet, run_id: str, *, client_model: str, evidence: dict) -> LineVerdict:
    try:
        data = json.loads(_strip_codeblock(content))
        facets_in = data.get("facets", {})
        facets = {f: facets_in.get(f, _default_for(f)) for f in FACETS}
        fix = data.get("fix_proposed")
    except (json.JSONDecodeError, KeyError, TypeError):
        facets = {f: ("ambiguous" if f == "canonical_correct" else _default_for(f)) for f in FACETS}
        fix = None
        evidence = {**evidence, "model_protocol_error": True, "raw_content": content[:2000]}
    return LineVerdict(
        recipe_id=packet.recipe_id, line_idx=packet.line_idx, config_bucket=packet.config_bucket,
        model=client_model, run_id=run_id, facets=facets, evidence=evidence, fix_proposed=fix,
        ts=_dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _default_for(facet: str) -> str:
    """Return a safe default value (clean) for a facet."""
    return "ok" if "ok" in FACET_ENUMS[facet] else FACET_ENUMS[facet][0]


def _strip_codeblock(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if "```" in s[3:] else s[3:]
        if s.startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0]
    return s.strip()


def _ambiguous_loop_exceeded(packet: Packet, run_id: str, model: str, log: list, cost: float) -> LineVerdict:
    facets = {f: ("ambiguous" if f == "canonical_correct" else _default_for(f)) for f in FACETS}
    return LineVerdict(
        recipe_id=packet.recipe_id, line_idx=packet.line_idx, config_bucket=packet.config_bucket,
        model=model, run_id=run_id, facets=facets,
        evidence={"tool_calls": log, "cost_usd": cost, "tool_loop_exceeded": True},
        fix_proposed=None,
        ts=_dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
