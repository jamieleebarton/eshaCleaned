"""Nebius tool-loop worker for ESHA MD-card cleanup.

The worker talks to the ESHA audit API for evidence and lets Nebius request
additional product/card queries before returning a patch bundle.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from nebius_contract_patch_builder import build_bundle


ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "implementation" / "output" / "nebius_esha_tool_worker"
PROMPT_PATH = ROOT / "implementation" / "NEBIUS_ESHA_AUDIT_PROMPT.md"
CARD_INDEX_CSV = ROOT / "implementation" / "output" / "esha_code_query_pack_index.csv"
DEFAULT_AUDIT_API = "http://127.0.0.1:8765"
DEFAULT_BASE_URL = "https://api.studio.nebius.com/v1"
DEFAULT_MODEL = "Qwen/Qwen3-32B"
MAX_CARD_TOOL_CHARS = 4000
MAX_CONTRACT_TOOL_CHARS = 4000
TOOL_RESULT_MAX_CHARS = {
    "get_card": 4000,
    "get_contract_source": 4000,
    "matrix_slice": 3000,
    "cross_reference": 3000,
}
TOOL_RESULT_MAX_CHARS_DEFAULT = 2500
MAX_STUB_ONLY_ROUNDS = 2
DESTINATION_CODE_RE = re.compile(r"\besha\s*(\d+)\b", re.IGNORECASE)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_card",
            "description": "Return one ESHA MD card by ESHA code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "esha_code": {"type": "integer"},
                    "max_chars": {"type": "integer", "default": 60000},
                },
                "required": ["esha_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search retail products by product text, optionally limited to a category substring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "category": {"type": "string"},
                    "limit": {"type": "integer", "default": 25},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cross_reference",
            "description": "Return cross-reference conflict/destination rows for an ESHA source code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "esha_code": {"type": "integer"},
                    "limit": {"type": "integer", "default": 100},
                },
                "required": ["esha_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "matrix_slice",
            "description": "Return the ESHA cleanup matrix slice for a card. Use this to inspect noisy rows, likely destinations, and collision cleanup actions. Set rebuild true if the slice is missing or stale.",
            "parameters": {
                "type": "object",
                "properties": {
                    "esha_code": {"type": "integer"},
                    "limit": {"type": "integer", "default": 100},
                    "rebuild": {"type": "boolean", "default": False},
                },
                "required": ["esha_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_contract_source",
            "description": "Return the current reviewed ESHA contract source files for a code. Use this as contract-style evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "esha_code": {"type": "integer"},
                    "max_chars": {"type": "integer", "default": 60000},
                },
                "required": ["esha_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_queue",
            "description": "Return queued top ingredient/card cleanup rows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10},
                    "status": {"type": "string", "default": "todo"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_cards",
            "description": "List ESHA card index rows from the full card universe, optionally filtered by family.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50},
                    "offset": {"type": "integer", "default": 0},
                    "family": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "product_codes",
            "description": "Return product rows with their selected ESHA code list, primary code, and collision status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gtin": {"type": "string"},
                    "esha_code": {"type": "string"},
                    "collision_status": {"type": "string"},
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "collisions",
            "description": "Return products currently assigned to more than one ESHA code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "esha_code": {"type": "string"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_nutrient_fingerprint",
            "description": "Compare 2 or more ESHA codes by (kcal, protein, fat, carbs) per 100g. Returns profiles and pairwise euclidean distance. Use this to sanity-check whether a proposed proxy is nutritionally plausible before committing to it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "esha_codes": {"type": "array", "items": {"type": "integer"}, "minItems": 2},
                },
                "required": ["esha_codes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recipe_context",
            "description": "Return a recipe's clean_title and sibling ingredient list. Use when deciding whether an ambiguous ingredient (oil, sugar, flour) means the generic or a specific variant given its recipe neighborhood.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipe_id": {"type": "integer"},
                },
                "required": ["recipe_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prior_decisions",
            "description": "Return current registry state for a canonical across approved_normalization_rules, canonical_items, canonical_to_esha, reviewed_nutrition_anchors. Call this BEFORE proposing a contract change so you can reference existing decisions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "normalized_item": {"type": "string"},
                },
                "required": ["normalized_item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trace_entity",
            "description": "Return derived provenance and rebuild dependencies for a canonical, normalized item, ESHA code, GTIN, pack, or contract.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["canonical", "normalized_item", "esha_code", "gtin", "pack", "contract"]},
                    "key": {"type": "string"},
                    "limit": {"type": "integer", "default": 50},
                },
                "required": ["kind", "key"],
            },
        },
    },
]


def slug(value: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("_")
    return out[:80] or "esha"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def read_prompt() -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    return (
        text
        + "\n\nYou may call the provided tools to inspect more cards, search products, "
        + "and inspect cross-reference conflicts. Return final JSON only when you have "
        + "enough evidence to define the contract or ask for more context. Do not hand-write a "
        + "unified diff. Return structured_contract and keep patch null; local deterministic code "
        + "will generate and validate the patch. "
        + "The top ingredient queue is only a priority list; "
        + "valid ESHA cards outside that queue still count and can be targeted by ESHA code. "
        + "If the current card and contract already classify the evidence correctly, return "
        + "decision no_change with patch null."
    )


def http_json(method: str, base_url: str, path: str, payload: Any | None = None) -> Any:
    url = base_url.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(base_url: str, path: str, params: dict[str, Any]) -> Any:
    clean = {k: v for k, v in params.items() if v not in (None, "")}
    suffix = "?" + urlencode(clean) if clean else ""
    return http_json("GET", base_url, path + suffix)


def bounded_int(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0, min(parsed, maximum))


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_compare_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"\besha\s*\d+\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def significant_tokens(value: Any) -> set[str]:
    stop = {"and", "or", "the", "a", "an", "of", "for", "with", "to", "dessert", "topping", "food"}
    return {token for token in normalize_compare_text(value).split() if token and token not in stop}


def packet_needs_tool_followup(packet: dict[str, Any]) -> bool:
    assigned_rows = len((((packet.get("assigned_product_codes") or {}).get("rows")) or []))
    contract_match_count = safe_int((packet.get("contract_sources") or {}).get("match_count"), 0)
    crossref_rows = len(packet.get("cross_reference_rows") or [])
    index_row = ((packet.get("card") or {}).get("index_row")) or {}
    total_matches = safe_int(index_row.get("total_product_matches"), 0)
    top_category_count = safe_int(index_row.get("top_category_count"), 0)
    noisy_card = total_matches >= 20 and top_category_count >= max(10, total_matches // 2)
    return assigned_rows == 0 and (contract_match_count == 0 or noisy_card or crossref_rows == 0)


def build_tool_followup_message(packet: dict[str, Any]) -> str:
    code = packet.get("esha_code")
    description = packet.get("esha_description") or ((packet.get("card") or {}).get("index_row") or {}).get("description")
    return (
        "Do not return final JSON yet. This packet needs more grounded evidence before you finalize.\n"
        f"- Run `matrix_slice(esha_code={code}, rebuild=true, limit=50)` to inspect noisy rows and possible destinations.\n"
        f"- Run `product_codes(esha_code=\"{code}\", limit=25)` to confirm whether reviewed assignments exist.\n"
        "- If you cite any other ESHA destination code in `better_destination`, verify it first with "
        "`get_card(esha_code=...)` or `list_cards(...)`.\n"
        "- If accepted products differ by label variants, use `required_description_any_terms` instead of making "
        "every term or phrase mandatory.\n"
        f"Card under review: ESHA {code} {description or ''}".strip()
    )


def load_card_index_descriptions() -> dict[str, str]:
    if not CARD_INDEX_CSV.exists():
        return {}
    descriptions: dict[str, str] = {}
    with CARD_INDEX_CSV.open(encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            code = str(row.get("esha_code") or "").strip()
            description = str(row.get("description") or "").strip()
            if code and description:
                descriptions[code] = description
    return descriptions


def validate_better_destination_references(
    final: dict[str, Any], descriptions: dict[str, str] | None = None
) -> dict[str, Any]:
    descriptions = descriptions if descriptions is not None else load_card_index_descriptions()
    failures: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    for product in final.get("reject_products") or []:
        if not isinstance(product, dict):
            continue
        destination = str(product.get("better_destination") or "").strip()
        if not destination:
            continue
        match = DESTINATION_CODE_RE.search(destination)
        if not match:
            warnings.append(
                {
                    "gtin_upc": str(product.get("gtin_upc") or ""),
                    "better_destination": destination,
                    "warning": "destination_has_no_verifiable_esha_code",
                }
            )
            continue
        code = match.group(1)
        actual = descriptions.get(code)
        if not actual:
            failures.append(
                {
                    "gtin_upc": str(product.get("gtin_upc") or ""),
                    "better_destination": destination,
                    "error": f"destination_code_not_found:{code}",
                }
            )
            continue
        if "(" in destination and ")" in destination:
            claimed = destination[destination.find("(") + 1 : destination.rfind(")")].strip()
            claimed_tokens = significant_tokens(claimed)
            actual_tokens = significant_tokens(actual)
            if claimed_tokens and actual_tokens and not (claimed_tokens & actual_tokens):
                failures.append(
                    {
                        "gtin_upc": str(product.get("gtin_upc") or ""),
                        "better_destination": destination,
                        "actual_description": actual,
                        "error": f"destination_label_mismatch:{code}",
                    }
                )
    return {"ok": not failures, "failures": failures, "warnings": warnings}


def _truncate_strings_in_place(node: Any, cap: int) -> bool:
    truncated = False
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(value, str) and len(value) > cap:
                node[key] = value[:cap] + f"... [truncated {len(value) - cap} chars]"
                truncated = True
            else:
                if _truncate_strings_in_place(value, cap):
                    truncated = True
    elif isinstance(node, list):
        for item in node:
            if _truncate_strings_in_place(item, cap):
                truncated = True
    return truncated


def truncate_tool_result(name: str, result: Any) -> Any:
    cap = TOOL_RESULT_MAX_CHARS.get(name, TOOL_RESULT_MAX_CHARS_DEFAULT)
    encoded = json.dumps(result, ensure_ascii=False)
    if len(encoded) <= cap:
        return result
    if isinstance(result, (dict, list)):
        result_copy = json.loads(json.dumps(result))
        _truncate_strings_in_place(result_copy, cap)
        re_encoded = json.dumps(result_copy, ensure_ascii=False)
        if len(re_encoded) <= cap * 2:
            return result_copy
    return {
        "tool": name,
        "truncated": True,
        "original_chars": len(encoded),
        "cap_chars": cap,
        "content_preview": encoded[:cap] + "... [truncated]",
    }


def tool_call(base_url: str, name: str, arguments: dict[str, Any]) -> Any:
    if name == "get_card":
        return get_json(
            base_url,
            "/card",
            {
                "code": arguments.get("esha_code"),
                "max_chars": bounded_int(arguments.get("max_chars"), MAX_CARD_TOOL_CHARS, MAX_CARD_TOOL_CHARS),
            },
        )
    if name == "search_products":
        return get_json(
            base_url,
            "/search-products",
            {
                "query": arguments.get("query"),
                "category": arguments.get("category"),
                "limit": arguments.get("limit", 25),
            },
        )
    if name == "cross_reference":
        return get_json(
            base_url,
            "/cross-reference",
            {
                "code": arguments.get("esha_code"),
                "limit": arguments.get("limit", 100),
            },
        )
    if name == "matrix_slice":
        return get_json(
            base_url,
            "/matrix",
            {
                "code": arguments.get("esha_code"),
                "limit": arguments.get("limit", 100),
                "rebuild": "true" if arguments.get("rebuild") else "",
            },
        )
    if name == "get_contract_source":
        return get_json(
            base_url,
            "/contract",
            {
                "code": arguments.get("esha_code"),
                "max_chars": bounded_int(
                    arguments.get("max_chars"),
                    MAX_CONTRACT_TOOL_CHARS,
                    MAX_CONTRACT_TOOL_CHARS,
                ),
            },
        )
    if name == "get_queue":
        return get_json(
            base_url,
            "/queue",
            {
                "limit": arguments.get("limit", 10),
                "status": arguments.get("status", "todo"),
            },
        )
    if name == "list_cards":
        return get_json(
            base_url,
            "/cards",
            {
                "limit": arguments.get("limit", 50),
                "offset": arguments.get("offset", 0),
                "family": arguments.get("family"),
            },
        )
    if name == "product_codes":
        return get_json(
            base_url,
            "/product-codes",
            {
                "gtin": arguments.get("gtin"),
                "esha_code": arguments.get("esha_code"),
                "collision_status": arguments.get("collision_status"),
                "query": arguments.get("query"),
                "limit": arguments.get("limit", 50),
            },
        )
    if name == "collisions":
        return get_json(
            base_url,
            "/collisions",
            {
                "esha_code": arguments.get("esha_code"),
                "limit": arguments.get("limit", 50),
            },
        )
    elif name == "compare_nutrient_fingerprint":
        codes = arguments.get("esha_codes") or []
        codes_str = ",".join(str(int(c)) for c in codes)
        return get_json(base_url, "/nutrient-compare", {"codes": codes_str})
    elif name == "recipe_context":
        return get_json(base_url, "/recipe-context", {"recipe_id": int(arguments["recipe_id"])})
    elif name == "prior_decisions":
        return get_json(base_url, "/prior-decisions", {"normalized_item": str(arguments.get("normalized_item") or "")})
    elif name == "trace_entity":
        return get_json(
            base_url,
            "/trace",
            {
                "kind": str(arguments.get("kind") or ""),
                "key": str(arguments.get("key") or ""),
                "limit": arguments.get("limit", 50),
            },
        )
    return {"error": "unknown_tool", "tool": name}


def strip_thinking(content: str) -> str:
    if "</think>" in content:
        return content.split("</think>")[-1].strip()
    return content.strip()


def parse_final_json(content: str) -> dict[str, Any] | None:
    cleaned = strip_thinking(content)
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def call_nebius_http(request_body: dict[str, Any], base_url: str, api_key: str, timeout: float) -> Any:
    url = base_url.rstrip("/") + "/chat/completions"
    req = Request(
        url,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Nebius HTTP {exc.code}: {detail}") from exc


def call_nebius(client: Any, request: dict[str, Any], base_url: str, api_key: str, timeout: float) -> Any:
    if client is None:
        return call_nebius_http(request, base_url, api_key, timeout)
    response = client.chat.completions.create(**request)
    return response.model_dump()


def force_final_request(request: dict[str, Any]) -> dict[str, Any]:
    forced = dict(request)
    forced["messages"] = [
        *request["messages"][:2],
        {
            "role": "user",
            "content": (
                "No more tools are available. Return the required final JSON now. "
                "If audit_warnings includes no_direct_reviewed_contract_for_code "
                "and contract_sources.suggested_files is non-empty, do not return "
                "no_change. If the MD card contains plausible candidate products, "
                "return a structured_contract for a reviewed generated contract. "
                "Return needs_more_context only when you name the exact missing "
                "query or evidence. Keep patch null; do not hand-write a diff."
            ),
        },
    ]
    forced.pop("tools", None)
    forced["tool_choice"] = "none"
    return forced


def initial_packet(args: argparse.Namespace) -> dict[str, Any]:
    if args.esha_code is not None:
        return get_json(
            args.audit_api,
            "/packet",
            {
                "code": args.esha_code,
                "max_card_chars": args.max_card_chars,
                "crossref_limit": args.crossref_limit,
                "product_limit": args.product_limit,
            },
        )
    if args.item:
        return get_json(
            args.audit_api,
            "/packet",
            {
                "item": args.item,
                "max_card_chars": args.max_card_chars,
                "crossref_limit": args.crossref_limit,
                "product_limit": args.product_limit,
            },
        )
    queue = get_json(args.audit_api, "/queue", {"limit": 1, "status": "todo"})
    if not queue:
        return {"error": "empty_queue"}
    item = queue[0]["normalized_item"]
    return get_json(
        args.audit_api,
        "/packet",
        {
            "item": item,
            "max_card_chars": args.max_card_chars,
            "crossref_limit": args.crossref_limit,
            "product_limit": args.product_limit,
        },
    )


def codes_to_refresh(final: dict[str, Any], default_code: Any) -> list[str]:
    codes: list[str] = []
    for value in (default_code, final.get("esha_code"), final.get("code")):
        if value not in (None, ""):
            codes.append(str(value))
    for key in ("affected_esha_codes", "refresh_esha_codes"):
        value = final.get(key)
        if isinstance(value, list):
            codes.extend(str(item) for item in value if item not in (None, ""))
    return sorted(set(codes), key=lambda item: int(item) if item.isdigit() else 10**9)


def maybe_stage_and_gate(args: argparse.Namespace, final: dict[str, Any], out_dir: Path, default_code: Any) -> dict[str, Any]:
    patch = final.get("patch")
    if not patch:
        return {"status": "no_patch"}

    if not final.get("bundle_id"):
        final["bundle_id"] = out_dir.name
    stage = http_json("POST", args.audit_api, "/stage-patch", final)
    result: dict[str, Any] = {"stage": stage}
    bundle_id = stage.get("bundle_id")
    if bundle_id:
        result["validate"] = http_json("POST", args.audit_api, "/validate-patch", {"bundle_id": bundle_id})
        if args.apply:
            result["apply"] = http_json("POST", args.audit_api, "/apply-patch", {"bundle_id": bundle_id})
            if result["apply"].get("report", {}).get("applied") or result["apply"].get("applied"):
                result["refresh_codes"] = [
                    http_json("POST", args.audit_api, "/refresh-code", {"esha_code": code})
                    for code in codes_to_refresh(final, default_code)
                ]
    return result


def maybe_build_structured_patch(args: argparse.Namespace, packet: dict[str, Any], final: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    if args.use_raw_model_patch:
        return final
    if final.get("decision") in {"no_change", "needs_more_context"}:
        return final
    bundle_id = str(final.get("bundle_id") or out_dir.name)
    try:
        bundle = build_bundle(packet, final, bundle_id)
    except Exception as exc:
        updated = dict(final)
        updated["patch"] = None
        updated["structured_patch_builder"] = {
            "status": "builder_error",
            "error": type(exc).__name__,
            "message": str(exc),
        }
        return updated
    write_json(out_dir / "structured_patch_bundle.json", bundle)
    return bundle


def repair_feedback(final: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any] | None:
    builder = final.get("structured_patch_builder")
    if isinstance(builder, dict) and builder.get("status") in {"semantic_validation_failed", "builder_error"}:
        return {"source": "structured_patch_builder", "detail": builder}
    destination_validation = final.get("destination_validation")
    if isinstance(destination_validation, dict) and not bool(destination_validation.get("ok", True)):
        return {"source": "destination_validation", "detail": destination_validation}
    if gate_preflight_failed(gate):
        return {"source": "patch_gate", "detail": gate}
    return None


def gate_preflight_failed(gate: dict[str, Any]) -> bool:
    validate = gate.get("validate")
    if not isinstance(validate, dict):
        return False
    report = validate.get("report")
    return isinstance(report, dict) and not bool(report.get("preflight_ok"))


def truncate_contract_sources(packet: dict[str, Any], max_chars: int = 16000) -> dict[str, Any]:
    contracts = packet.get("contract_sources")
    if not isinstance(contracts, dict):
        return {}
    copied = {k: v for k, v in contracts.items() if k not in {"matches", "suggested_files"}}
    for key in ("matches", "suggested_files"):
        rows = []
        for row in contracts.get(key) or []:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            source = item.get("source")
            if isinstance(source, str) and len(source) > max_chars:
                item["source"] = source[:max_chars]
                item["truncated_for_repair"] = True
            rows.append(item)
        copied[key] = rows
    return copied


def repair_patch(
    args: argparse.Namespace,
    client: Any,
    base_url: str,
    api_key: str,
    packet: dict[str, Any],
    final: dict[str, Any],
    gate: dict[str, Any],
    repair_details: dict[str, Any],
    out_dir: Path,
    repair_index: int,
) -> dict[str, Any] | None:
    request = {
        "model": args.verifier_model or args.model or os.getenv("NEBIUS_VERIFIER_MODEL") or os.getenv("NEBIUS_MODEL", DEFAULT_MODEL),
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "messages": [
            {"role": "system", "content": read_prompt()},
            {
                "role": "user",
                "content": (
                    "The previous final JSON failed deterministic local validation. "
                    "Return corrected final JSON only. Preserve the decision unless the failure "
                    "proves the decision is wrong. If accepted products differ by label variants, "
                    "use required_description_any_terms instead of requiring every term or phrase. "
                    "If you named a better_destination with an ESHA code, the code and description "
                    "must agree with the index; otherwise remove or correct it.\n\n"
                    + json.dumps(
                        {
                            "esha_code": packet.get("esha_code"),
                            "esha_description": packet.get("esha_description"),
                            "audit_warnings": packet.get("audit_warnings"),
                            "card": packet.get("card"),
                            "contract_sources": truncate_contract_sources(packet),
                            "previous_final": final,
                            "repair_details": repair_details,
                            "gate": gate,
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                ),
            },
        ],
        "tool_choice": "none",
    }
    write_json(out_dir / f"request_patch_repair_{repair_index}.json", request)
    response = call_nebius(client, request, base_url=base_url, api_key=api_key, timeout=args.timeout)
    write_json(out_dir / f"response_patch_repair_{repair_index}.json", response)
    content = response["choices"][0]["message"].get("content") or ""
    repaired = parse_final_json(content)
    if repaired is None:
        return {"status": "invalid_repair_json", "raw_content": content}
    return repaired


def run(args: argparse.Namespace) -> dict[str, Any]:
    load_env_file(ROOT / ".env")
    load_env_file(Path.home() / ".env")

    packet = initial_packet(args)
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    item = str(packet.get("normalized_item") or args.item or args.esha_code or "queue")
    bundle_id = args.bundle_id or f"{slug(item)}_{packet.get('esha_code', 'no_code')}_{now}"
    out_dir = Path(args.out_dir) if args.out_dir else OUT_ROOT / bundle_id
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "packet.json", packet)

    request = {
        "model": args.model or os.getenv("NEBIUS_MODEL", DEFAULT_MODEL),
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "messages": [
            {"role": "system", "content": read_prompt()},
            {
                "role": "user",
                "content": "Audit this ESHA card packet. Use tools if needed. Return JSON only.\n\n"
                + json.dumps(packet, indent=2, ensure_ascii=False),
            },
        ],
        "tools": TOOLS,
        "tool_choice": "auto",
    }
    write_json(out_dir / "request_initial.json", request)
    if args.dry_run:
        return {"status": "dry_run", "out_dir": str(out_dir), "packet": packet}

    api_key = args.api_key or os.getenv("NEBIUS_API_KEY")
    if not api_key:
        result = {"status": "blocked", "error": "NEBIUS_API_KEY not set", "out_dir": str(out_dir)}
        write_json(out_dir / "worker_result.json", result)
        return result

    client = None
    base_url = args.base_url or os.getenv("NEBIUS_BASE_URL", DEFAULT_BASE_URL)
    try:
        from openai import OpenAI
    except ImportError:
        OpenAI = None  # type: ignore[assignment]
    if OpenAI is not None:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=args.timeout)

    raw_messages: list[dict[str, Any]] = []
    final: dict[str, Any] | None = None
    seen_tool_calls: set[str] = set()
    stub_only_streak = 0
    forced_tool_followup_sent = False
    for round_index in range(args.max_tool_rounds + 1):
        response = call_nebius(client, request, base_url=base_url, api_key=api_key, timeout=args.timeout)
        write_json(out_dir / f"response_round_{round_index}.json", response)
        message = response["choices"][0]["message"]
        raw_messages.append(message)
        request["messages"].append(message)

        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            round_stub_count = 0
            round_real_count = 0
            for call in tool_calls:
                name = call["function"]["name"]
                try:
                    arguments = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                tool_key = json.dumps({"name": name, "arguments": arguments}, sort_keys=True)
                if tool_key in seen_tool_calls:
                    round_stub_count += 1
                    tool_result = {
                        "error": "repeated_tool_call",
                        "tool": name,
                        "message": "This exact tool call was already returned. Use the existing evidence and return final JSON.",
                    }
                else:
                    round_real_count += 1
                    seen_tool_calls.add(tool_key)
                    tool_result = truncate_tool_result(name, tool_call(args.audit_api, name, arguments))
                request["messages"].append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "name": name,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )
            if round_real_count == 0 and round_stub_count > 0:
                stub_only_streak += 1
            else:
                stub_only_streak = 0
            if stub_only_streak >= MAX_STUB_ONLY_ROUNDS:
                break
            time.sleep(args.tool_delay)
            continue

        content = message.get("content") or ""
        final = parse_final_json(content)
        if final is None:
            final = {"status": "invalid_json", "raw_content": content}
            break
        if not forced_tool_followup_sent and not seen_tool_calls and packet_needs_tool_followup(packet):
            forced_tool_followup_sent = True
            request["messages"].append({"role": "user", "content": build_tool_followup_message(packet)})
            final = None
            continue
        break

    if final is None:
        forced_request = force_final_request(request)
        write_json(out_dir / "request_forced_final.json", forced_request)
        response = call_nebius(client, forced_request, base_url=base_url, api_key=api_key, timeout=args.timeout)
        write_json(out_dir / "response_forced_final.json", response)
        message = response["choices"][0]["message"]
        raw_messages.append(message)
        content = message.get("content") or ""
        final = parse_final_json(content)
        if final is None:
            final = {"status": "max_tool_rounds_exceeded", "messages": raw_messages, "forced_final_raw": content}
    final = maybe_build_structured_patch(args, packet, final, out_dir)
    destination_validation = validate_better_destination_references(final)
    if destination_validation["failures"] or destination_validation["warnings"]:
        final["destination_validation"] = destination_validation
    write_json(out_dir / "final.json", final)
    gate = maybe_stage_and_gate(args, final, out_dir, packet.get("esha_code"))
    for repair_index in range(args.patch_repair_rounds):
        feedback = repair_feedback(final, gate)
        if feedback is None:
            break
        repaired = repair_patch(
            args,
            client,
            base_url,
            api_key,
            packet,
            final,
            gate,
            feedback,
            out_dir,
            repair_index + 1,
        )
        if not isinstance(repaired, dict) or repaired.get("status") == "invalid_repair_json":
            write_json(out_dir / f"patch_repair_{repair_index + 1}_failed.json", repaired)
            break
        final = maybe_build_structured_patch(args, packet, repaired, out_dir)
        destination_validation = validate_better_destination_references(final)
        if destination_validation["failures"] or destination_validation["warnings"]:
            final["destination_validation"] = destination_validation
        write_json(out_dir / f"final_repaired_{repair_index + 1}.json", final)
        gate = maybe_stage_and_gate(args, final, out_dir, packet.get("esha_code"))
    write_json(out_dir / "gate.json", gate)
    result = {"status": "done", "out_dir": str(out_dir), "final": final, "gate": gate}
    write_json(out_dir / "worker_result.json", result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Nebius ESHA tool-loop worker")
    parser.add_argument("--audit-api", default=os.getenv("ESHA_AUDIT_API", DEFAULT_AUDIT_API))
    parser.add_argument("--item")
    parser.add_argument("--esha-code", type=int)
    parser.add_argument("--bundle-id")
    parser.add_argument("--out-dir")
    parser.add_argument("--model")
    parser.add_argument("--verifier-model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=7000)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-tool-rounds", type=int, default=8)
    parser.add_argument("--tool-delay", type=float, default=0.0)
    parser.add_argument("--patch-repair-rounds", type=int, default=1)
    parser.add_argument("--use-raw-model-patch", action="store_true")
    parser.add_argument("--max-card-chars", type=int, default=60000)
    parser.add_argument("--crossref-limit", type=int, default=50)
    parser.add_argument("--product-limit", type=int, default=25)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    result = run(build_parser().parse_args())
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
