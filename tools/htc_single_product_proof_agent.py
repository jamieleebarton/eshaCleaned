#!/usr/bin/env python3
"""Single-product HTC proof agent backed by vLLM/Qwen.

This is intentionally slow per item. It builds a rich evidence packet, retrieves
candidate HTC concepts, asks a proposer model to choose, asks an independent
verifier model to challenge the proposal, and writes a proof artifact. It never
emits human-review states; unresolved means machine evidence expansion is still
required.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
HTC_V1 = ROOT / "recipe_mapper" / "v1"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
if str(HTC_V1) not in sys.path:
    sys.path.insert(0, str(HTC_V1))

from htc_product_auditor_agent import (  # noqa: E402
    DEFAULT_CONSENSUS,
    DEFAULT_PRODUCTS,
    build_references,
    clean_htc,
    rank_candidates,
    selected_rows,
    tokens,
    weighted_tokens,
)
from htc_workbench_index import (  # noqa: E402
    DEFAULT_DB as DEFAULT_WORKBENCH_DB,
    build_dashboard,
    build_index as build_workbench_index,
    expand_candidate_family,
)
from htc.full_code import parse_full_code  # noqa: E402

DEFAULT_OUT_DIR = ROOT / "output" / "htc_single_product_proof_agent"
DEFAULT_BASE_URL = "http://localhost:8001/v1"
DEFAULT_MODEL = "qwen3-30b"
DEFAULT_FACET_VOCAB = ROOT / "recipe_mapper" / "v1" / "output" / "htc_facet_vocab.json"
DEFAULT_RECIPES = ROOT / "data" / "recipes_unified_normalized.csv"
MAX_INITIAL_CANDIDATES = 5
MAX_TOOL_ROWS = 8
MAX_TOOL_REQUESTS = 6
MAX_FULL_CODE_EXAMPLES = 3

SYSTEM_PREFIX = """You are the Hestia HTC product auditor.

Mission: determine the correct HTC assignment for exactly one branded/store product.
No human review is allowed. If evidence is not sufficient, output a machine
next-step state: needs_more_evidence, with concrete evidence to gather next.

Rules:
- Look at the whole HTC picture: base htc_code, htc_full_code examples, variant/modifier, claims, audience/use-case, and recipe substitution consequences.
- The assignment must prevent bad recipe joins. A retail product can share a broad food family with a recipe ingredient but still be the wrong substitute because of audience, form, processing, flavor, or variant. Example: baby oatmeal cereal is not automatically usable for a recipe that asks for oatmeal.
- Stage both the base HTC and the best supported full-code/facet target when the evidence proves them. If full-code/facets are not proven, request tools instead of collapsing to the broad bucket.
- Prefer direct consensus witnesses with matching title/audience/form/modifier over broad candidate families. Never choose a full-code whose modifier contradicts the product identity.
- Do not trust current_htc_code if source authority is weak, raw, rejected, non-food, or category-only.
- Use product title, UPC, brand, aisle/category, search term, existing tree identity/path/modifier, current/raw HTC, and candidate corpus examples.
- Reject candidates where the canonical path/product identity contradicts the product title.
- A candidate supported only by a single rare corpus row is not enough unless other evidence is overwhelming.
- If the product says juice, do not choose vinegar, canned fruit, cider, soda, punch, smoothie, slush, or concentrate unless the product title explicitly says that subtype.
- Machine tools must be requested using only these exact forms:
  expand_candidate_family:<FAMILY_ID>
  get_full_code_summary:<HTC_CODE>
  get_recipe_use_examples:<QUERY>
  fetch_corpus_rows_for_htc_code:<HTC_CODE>
  fetch_corpus_rows_for_product_title:<PRODUCT TITLE>
  fetch_product_rows_for_upc:<UPC>
  search_store_products:<QUERY>
  search_consensus:<QUERY>
  search_recipe_ingredients:<QUERY>
  sql_query:<READ_ONLY_SQL_OVER_product_rows_AND_consensus_rows>
- Output strict JSON only. No markdown.

Shared output states:
- verified_update: the proposed HTC is proven better than current HTC.
- verified_current: current HTC is proven correct.
- needs_more_evidence: no HTC is proven yet; provide machine evidence expansion tasks.
- stage_recipe_join_policy is allowed when base/full-code is unresolved but
  recipe compatibility is proven enough to block unsafe joins.
"""

PROPOSER_SCHEMA = {
    "selected_htc_code": "string or null",
    "selected_htc_full_code": "string or null",
    "verdict": "verified_update|verified_current|needs_more_evidence",
    "confidence": "high|medium|low",
    "rationale": "short string",
    "recipe_join_risk": "short string",
    "recipe_compatibility": {
        "ordinary_ingredient_substitute": "yes|no|uncertain",
        "compatible_recipe_terms": ["strings"],
        "incompatible_recipe_terms": ["strings"],
        "join_level": "base_htc|variant|full_code|blocked|uncertain",
        "evidence": ["strings"],
    },
    "supporting_evidence": ["strings"],
    "contradicting_evidence": ["strings"],
    "needed_machine_evidence": ["strings"],
}

PLANNER_SCHEMA = {
    "selected_tools": ["expand_candidate_family:<FAMILY_ID>", "get_full_code_summary:<HTC_CODE>", "get_recipe_use_examples:<QUERY>"],
    "rationale": "short string",
    "risk_focus": ["strings"],
}

VERIFIER_SCHEMA = {
    "verifier_verdict": "verified_update|verified_current|needs_more_evidence",
    "accepted_htc_code": "string or null",
    "accepted_htc_full_code": "string or null",
    "confidence": "high|medium|low",
    "rationale": "short string",
    "recipe_join_risk": "short string",
    "recipe_compatibility": {
        "ordinary_ingredient_substitute": "yes|no|uncertain",
        "compatible_recipe_terms": ["strings"],
        "incompatible_recipe_terms": ["strings"],
        "join_level": "base_htc|variant|full_code|blocked|uncertain",
        "evidence": ["strings"],
    },
    "blocking_contradictions": ["strings"],
    "required_next_tools": ["strings"],
}

FIXER_SCHEMA = {
    "fixer_verdict": "stage_htc_update|stage_full_code_repair|stage_recipe_join_policy|no_change_verified_current|machine_evidence_expansion",
    "accepted_htc_code": "string or null",
    "accepted_htc_full_code": "string or null",
    "confidence": "high|medium|low",
    "rationale": "short string",
    "recipe_join_risk": "short string",
    "staged_change": {
        "from_htc_code": "string",
        "from_htc_full_code": "string",
        "to_htc_code": "string or null",
        "to_htc_full_code": "string or null",
        "facet_updates": {},
        "recipe_join_policy": {},
        "evidence_ids": ["strings"],
        "write_scope": ["product_htc_assignment|full_code_assignment|recipe_join_policy"],
        "facet_notes": "string",
    },
    "required_next_tools": ["strings"],
}


def post_chat(base_url: str, model: str, messages: list[dict[str, str]], *, max_tokens: int = 900, temperature: float = 0.0, timeout: int = 300) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=data,
        headers={"Content-Type": "application/json", "Authorization": "Bearer EMPTY"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - local vLLM endpoint
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"vLLM HTTP {exc.code}: {body[:2000]}") from exc
    content = raw["choices"][0]["message"].get("content") or "{}"
    return parse_json_object(content)


def parse_json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {"raw": value}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                value = json.loads(match.group(0))
                return value if isinstance(value, dict) else {"raw": value}
            except json.JSONDecodeError:
                pass
    return {"parse_error": True, "raw_text": text[:4000]}


def proof_key(row_number: int, row: dict[str, str]) -> str:
    upc = str(row.get("upc") or "").strip()
    rowid = str(row.get("rowid") or "").strip()
    if upc and rowid:
        return f"{upc}_rowid_{rowid}"
    return upc or rowid or str(row_number)


def load_product_row(products_path: Path, *, upc: str = "", rowid: str = "") -> tuple[int, dict[str, str]]:
    upcs = {upc} if upc else set()
    rowids = {rowid} if rowid else set()
    rows = selected_rows(products_path, limit=1 if not upcs and not rowids else 0, upcs=upcs, rowids=rowids)
    if not rows:
        raise SystemExit(f"product row not found: upc={upc!r} rowid={rowid!r}")
    return rows[0]


def same_upc_rows(products_path: Path, upc: str, *, limit: int = 20) -> list[dict[str, str]]:
    if not upc:
        return []
    out = []
    with products_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("upc") or "") == upc:
                out.append(row)
                if len(out) >= limit:
                    break
    return out


def same_search_rows(products_path: Path, search_term: str, *, limit: int = 20) -> list[dict[str, str]]:
    if not search_term:
        return []
    out = []
    needle = search_term.strip().lower()
    with products_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("search_term") or "").strip().lower() == needle:
                out.append(row)
                if len(out) >= limit:
                    break
    return out


def compact_product(row: dict[str, str]) -> dict[str, Any]:
    keys = [
        "source", "rowid", "upc", "name", "brand", "grams", "cents", "size_display",
        "category_path", "category_path_walmart", "search_term", "raw_htc_code",
        "tree_authority", "taxonomy_status", "tree_product_identity", "tree_canonical_path",
        "tree_modifier", "htc_code", "htc_confidence", "htc_source", "non_food_path",
    ]
    return {k: row.get(k, "") for k in keys}


def product_clues(row: dict[str, str]) -> dict[str, Any]:
    text = " ".join(str(row.get(k) or "") for k in [
        "name", "brand", "search_term", "category_path", "category_path_walmart",
        "tree_product_identity", "tree_canonical_path", "tree_modifier",
    ]).lower()
    clue_groups = {
        "audience": ["baby", "infant", "toddler", "kids", "children"],
        "claims": ["organic", "whole grain", "gluten free", "non gmo", "no sugar", "no added sugar", "low sodium"],
        "form_or_use": ["cereal", "hot cereal", "oatmeal", "drink", "juice", "cocktail", "concentrate", "powder", "mix", "pouch"],
    }
    return {
        group: [term for term in terms if term in text]
        for group, terms in clue_groups.items()
        if any(term in text for term in terms)
    }


def compact_consensus(row: dict[str, str]) -> dict[str, Any]:
    keys = [
        "fdc_id", "title", "branded_food_category", "product_identity_fixed",
        "canonical_path", "retail_leaf_path", "modifier", "htc_code", "htc_full_code",
        "htc_confidence", "htc_source",
    ]
    return {k: row.get(k, "") for k in keys}


def load_facet_vocab(path: Path = DEFAULT_FACET_VOCAB) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def summarize_full_code_examples(consensus_path: Path, codes: set[str], *, limit_per_code: int = 8) -> dict[str, Any]:
    if not codes:
        return {}
    summaries: dict[str, dict[str, Any]] = {
        code: {
            "htc_full_code_counts": Counter(),
            "retail_leaf_path_counts": Counter(),
            "modifier_counts": Counter(),
            "claim_counts": Counter(),
            "examples": [],
        }
        for code in codes
    }
    with consensus_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            code = clean_htc(row.get("htc_code"))
            if code not in summaries:
                continue
            summary = summaries[code]
            full_code = str(row.get("htc_full_code") or "")
            if full_code:
                summary["htc_full_code_counts"][full_code] += 1
                parsed = parse_full_code(full_code)
                for claim in parsed.get("claims") or []:
                    summary["claim_counts"][claim] += 1
            leaf = str(row.get("retail_leaf_path") or "")
            mod = str(row.get("modifier") or "")
            if leaf:
                summary["retail_leaf_path_counts"][leaf] += 1
            if mod:
                summary["modifier_counts"][mod] += 1
            if len(summary["examples"]) < limit_per_code:
                parsed = parse_full_code(full_code)
                summary["examples"].append({
                    "fdc_id": row.get("fdc_id"),
                    "title": row.get("title"),
                    "htc_full_code": full_code,
                    "full_code_parts": parsed,
                    "canonical_path": row.get("canonical_path"),
                    "retail_leaf_path": leaf,
                    "modifier": mod,
                })
    out = {}
    for code, summary in summaries.items():
        out[code] = {
            "top_htc_full_codes": summary["htc_full_code_counts"].most_common(8),
            "top_retail_leaf_paths": summary["retail_leaf_path_counts"].most_common(8),
            "top_modifiers": summary["modifier_counts"].most_common(8),
            "top_claims": summary["claim_counts"].most_common(8),
            "examples": summary["examples"],
        }
    return out


def candidate_neighbor_rows(candidates: list[Any], consensus_path: Path) -> list[dict[str, Any]]:
    candidate_codes = {clean_htc(c.htc_code if hasattr(c, "htc_code") else c.get("htc_code")) for c in candidates[:MAX_INITIAL_CANDIDATES]}
    candidate_codes.discard("")
    full_code_summaries = summarize_full_code_examples(consensus_path, candidate_codes, limit_per_code=MAX_FULL_CODE_EXAMPLES)
    facet_vocab = load_facet_vocab()
    rows = []
    for cand in candidates[:MAX_INITIAL_CANDIDATES]:
        d = asdict(cand) if hasattr(cand, "__dataclass_fields__") else dict(cand)
        code = clean_htc(d.get("htc_code"))
        full_summary = full_code_summaries.get(code, {})
        rows.append({
            "htc_code": code,
            "score": d.get("score"),
            "canonical_path": d.get("canonical_path"),
            "retail_leaf_path": d.get("retail_leaf_path"),
            "product_identity": d.get("product_identity"),
            "row_count": d.get("row_count"),
            "full_code_summary": {
                "top_htc_full_codes": (full_summary.get("top_htc_full_codes") or [])[:4],
                "top_retail_leaf_paths": (full_summary.get("top_retail_leaf_paths") or [])[:4],
                "top_modifiers": (full_summary.get("top_modifiers") or [])[:4],
                "top_claims": (full_summary.get("top_claims") or [])[:4],
                "examples": (full_summary.get("examples") or [])[:MAX_FULL_CODE_EXAMPLES],
            },
            "facet_vocab": {
                key: values[:6]
                for key, values in (facet_vocab.get(code) or facet_vocab.get("~" + code) or {}).items()
            },
            "evidence_terms": d.get("evidence_terms"),
            "missing_required_identity_terms": d.get("missing_required_identity_terms"),
            "title_samples": d.get("title_samples"),
            "signal_scores": {
                "title_overlap": d.get("title_overlap"),
                "search_overlap": d.get("search_overlap"),
                "path_overlap": d.get("path_overlap"),
                "aisle_overlap": d.get("aisle_overlap"),
                "string_similarity": d.get("string_similarity"),
                "authority_penalty": d.get("authority_penalty"),
            },
        })
    return rows


def consensus_rows_for_htc_code(consensus_path: Path, htc_code: str, *, limit: int = MAX_TOOL_ROWS) -> list[dict[str, Any]]:
    target = clean_htc(htc_code)
    if not target:
        return []
    out = []
    with consensus_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            if clean_htc(row.get("htc_code")) == target:
                out.append(compact_consensus(row))
                if len(out) >= limit:
                    break
    return out


def consensus_rows_for_product_title(consensus_path: Path, title: str, *, limit: int = MAX_TOOL_ROWS) -> list[dict[str, Any]]:
    title_terms = weighted_title_terms(title)
    if not title_terms:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    with consensus_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            row_terms = weighted_title_terms(row.get("title", ""))
            if not row_terms:
                continue
            hits = title_terms & row_terms
            if not hits:
                continue
            score = len(hits) / len(title_terms | row_terms)
            if score >= 0.18:
                scored.append((score, compact_consensus(row)))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row | {"title_similarity": round(score, 6)} for score, row in scored[:limit]]


def product_rows_for_upc(products_path: Path, upc: str, *, limit: int = MAX_TOOL_ROWS) -> list[dict[str, Any]]:
    target = str(upc or "").strip()
    if not target:
        return []
    out = []
    with products_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("upc") or "").strip() == target:
                out.append(compact_product(row))
                if len(out) >= limit:
                    break
    return out


def search_store_products(products_path: Path, query: str, *, limit: int = MAX_TOOL_ROWS) -> list[dict[str, Any]]:
    qterms = tokens(query, keep_weak=True)
    if not qterms:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    with products_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            text = " ".join(str(row.get(k) or "") for k in ["name", "brand", "search_term", "category_path", "category_path_walmart", "tree_product_identity", "tree_canonical_path"])
            rterms = tokens(text, keep_weak=True)
            hits = qterms & rterms
            if not hits:
                continue
            score = len(hits) / len(qterms | rterms)
            scored.append((score, compact_product(row) | {"matched_terms": sorted(hits)}))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row | {"search_score": round(score, 6)} for score, row in scored[:limit]]


def search_consensus(consensus_path: Path, query: str, *, limit: int = MAX_TOOL_ROWS) -> list[dict[str, Any]]:
    qterms = tokens(query, keep_weak=True)
    if not qterms:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    with consensus_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            text = " ".join(str(row.get(k) or "") for k in ["title", "branded_food_category", "product_identity_fixed", "canonical_path", "retail_leaf_path", "modifier", "htc_code", "htc_full_code"])
            rterms = tokens(text, keep_weak=True)
            hits = qterms & rterms
            if not hits:
                continue
            score = len(hits) / len(qterms | rterms)
            scored.append((score, compact_consensus(row) | {"matched_terms": sorted(hits)}))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row | {"search_score": round(score, 6)} for score, row in scored[:limit]]


def compact_recipe_line(row: dict[str, str]) -> dict[str, Any]:
    keys = [
        "recipe_id", "recipe_title", "ingredient_item", "display", "htc_code",
        "htc_confidence", "facet_flavor", "facet_form", "facet_processing",
        "facet_claims", "facet_modifier", "facet_variant",
        "normalized_canonical_text", "normalized_identity_phrase",
        "normalized_user_claims", "normalized_form_facets", "normalized_processing_facets",
    ]
    return {k: row.get(k, "") for k in keys}


def search_recipe_ingredients(recipes_path: Path, query: str, *, limit: int = MAX_TOOL_ROWS) -> list[dict[str, Any]]:
    qterms = tokens(query, keep_weak=True)
    if not qterms or not recipes_path.exists():
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    with recipes_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            text = " ".join(str(row.get(k) or "") for k in [
                "ingredient_item", "display", "normalized_canonical_text",
                "normalized_identity_phrase", "normalized_user_claims",
                "normalized_form_facets", "normalized_processing_facets",
            ])
            rterms = tokens(text, keep_weak=True)
            hits = qterms & rterms
            if not hits:
                continue
            score = len(hits) / len(qterms | rterms)
            scored.append((score, compact_recipe_line(row) | {"matched_terms": sorted(hits)}))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row | {"search_score": round(score, 6)} for score, row in scored[:limit]]


SQL_CACHE: dict[tuple[str, str], sqlite3.Connection] = {}


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def load_sqlite_connection(products_path: Path, consensus_path: Path) -> sqlite3.Connection:
    key = (str(products_path), str(consensus_path))
    cached = SQL_CACHE.get(key)
    if cached:
        return cached
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    for table_name, path in [("product_rows", products_path), ("consensus_rows", consensus_path)]:
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            con.execute(
                f"CREATE TABLE {quote_ident(table_name)} ({', '.join(quote_ident(f) + ' TEXT' for f in fieldnames)})"
            )
            placeholders = ", ".join("?" for _ in fieldnames)
            columns = ", ".join(quote_ident(f) for f in fieldnames)
            insert_sql = f"INSERT INTO {quote_ident(table_name)} ({columns}) VALUES ({placeholders})"
            batch = []
            for row in reader:
                batch.append([row.get(f, "") for f in fieldnames])
                if len(batch) >= 5000:
                    con.executemany(insert_sql, batch)
                    batch.clear()
            if batch:
                con.executemany(insert_sql, batch)
    SQL_CACHE[key] = con
    return con


def sql_query(products_path: Path, consensus_path: Path, sql: str, *, limit: int = 20) -> dict[str, Any]:
    query = str(sql or "").strip()
    lowered = query.lower()
    if not (lowered.startswith("select ") or lowered.startswith("with ") or lowered.startswith("pragma ")):
        return {"error": "only read-only SELECT/WITH/PRAGMA SQL is allowed", "rows": []}
    if any(token in lowered for token in [" insert ", " update ", " delete ", " drop ", " alter ", " attach ", " detach ", " create "]):
        return {"error": "mutating SQL is not allowed", "rows": []}
    try:
        con = load_sqlite_connection(products_path, consensus_path)
        rows = con.execute(query).fetchmany(limit)
        return {
            "row_count": len(rows),
            "rows": [dict(row) for row in rows],
            "tables": ["product_rows", "consensus_rows"],
        }
    except Exception as exc:  # noqa: BLE001 - tool errors must be returned to the model
        return {"error": repr(exc), "rows": [], "tables": ["product_rows", "consensus_rows"]}


def weighted_title_terms(title: str) -> set[str]:
    return weighted_tokens({"name": title, "search_term": title, "tree_product_identity": title})["title"]


def execute_machine_tools(
    products_path: Path,
    consensus_path: Path,
    recipes_path: Path,
    workbench_db: Path,
    requested_tools: list[Any],
) -> list[dict[str, Any]]:
    results = []
    for tool in requested_tools:
        spec = str(tool or "").strip()
        if not spec:
            continue
        name, _, arg = spec.partition(":")
        if name == "expand_candidate_family":
            results.append(expand_candidate_family(workbench_db, family_id=arg))
            continue
        if name == "get_full_code_summary":
            rows = consensus_rows_for_htc_code(consensus_path, arg)
        elif name == "get_recipe_use_examples":
            rows = search_recipe_ingredients(recipes_path, arg)
        elif name == "fetch_corpus_rows_for_htc_code":
            rows = consensus_rows_for_htc_code(consensus_path, arg)
        elif name == "fetch_corpus_rows_for_product_title":
            rows = consensus_rows_for_product_title(consensus_path, arg)
        elif name == "fetch_product_rows_for_upc":
            rows = product_rows_for_upc(products_path, arg)
        elif name == "search_store_products":
            rows = search_store_products(products_path, arg)
        elif name == "search_consensus":
            rows = search_consensus(consensus_path, arg)
        elif name == "search_recipe_ingredients":
            rows = search_recipe_ingredients(recipes_path, arg)
        elif name == "sql_query":
            result = sql_query(products_path, consensus_path, arg)
            results.append({
                "tool": name,
                "argument": arg,
                **result,
            })
            continue
        else:
            rows = []
        results.append({
            "tool": name,
            "argument": arg,
            "row_count": len(rows),
            "rows": rows,
        })
    return results


def valid_machine_tool(spec: Any) -> bool:
    text = str(spec or "").strip()
    return (
        text.startswith("expand_candidate_family:")
        or text.startswith("get_full_code_summary:")
        or text.startswith("get_recipe_use_examples:")
        or text.startswith("fetch_corpus_rows_for_htc_code:")
        or text.startswith("fetch_corpus_rows_for_product_title:")
        or text.startswith("fetch_product_rows_for_upc:")
        or text.startswith("search_store_products:")
        or text.startswith("search_consensus:")
        or text.startswith("search_recipe_ingredients:")
        or text.startswith("sql_query:")
    )


def machine_tool_requests(packet: dict[str, Any], proposal: dict[str, Any], verifier: dict[str, Any]) -> list[str]:
    requests = []
    dashboard = packet.get("workbench_dashboard") if isinstance(packet.get("workbench_dashboard"), dict) else {}
    for family in dashboard.get("candidate_families") or []:
        if not isinstance(family, dict):
            continue
        family_id = str(family.get("family_id") or "").strip()
        if family_id:
            requests.append(f"expand_candidate_family:{family_id}")
        if len(requests) >= 3:
            break
    for spec in proposal.get("needed_machine_evidence") or []:
        if valid_machine_tool(spec):
            requests.append(str(spec))
    for spec in verifier.get("required_next_tools") or []:
        if valid_machine_tool(spec):
            requests.append(str(spec))
    selected = clean_htc(proposal.get("selected_htc_code") or verifier.get("accepted_htc_code") or "")
    if selected:
        requests.append(f"fetch_corpus_rows_for_htc_code:{selected}")
    product = packet.get("product") if isinstance(packet.get("product"), dict) else {}
    name = str(product.get("name") or "").strip()
    upc = str(product.get("upc") or "").strip()
    if upc:
        requests.append(f"fetch_product_rows_for_upc:{upc}")
    if name:
        requests.append(f"fetch_corpus_rows_for_product_title:{name}")
        requests.append(f"search_store_products:{name}")
        requests.append(f"search_consensus:{name}")
        requests.append(f"search_recipe_ingredients:{name}")
    for cand in packet.get("candidate_htc_concepts") or []:
        if not isinstance(cand, dict):
            continue
        code = clean_htc(cand.get("htc_code"))
        if code:
            requests.append(f"fetch_corpus_rows_for_htc_code:{code}")
        if len(requests) >= 6:
            break
    seen = set()
    unique = []
    for req in requests:
        if req not in seen:
            unique.append(req)
            seen.add(req)
    return unique[:MAX_TOOL_REQUESTS]


def planner_tool_requests(packet: dict[str, Any], planner: dict[str, Any]) -> list[str]:
    requests = []
    for spec in planner.get("selected_tools") or []:
        if valid_machine_tool(spec):
            requests.append(str(spec))
    for spec in packet.get("suggested_expansion_tools") or []:
        if valid_machine_tool(spec):
            requests.append(str(spec))
    seen = set()
    unique = []
    for req in requests:
        if req not in seen:
            unique.append(req)
            seen.add(req)
    return unique[:MAX_TOOL_REQUESTS]


def build_workbench_dashboard_for_row(args: argparse.Namespace, row: dict[str, str]) -> dict[str, Any]:
    db_path = Path(getattr(args, "workbench_db", DEFAULT_WORKBENCH_DB))
    if not getattr(args, "no_workbench", False) and not db_path.exists() and getattr(args, "build_workbench_if_missing", False):
        build_workbench_index(
            db_path,
            args.products,
            args.consensus,
            args.recipes,
            enable_fts=not getattr(args, "no_workbench_fts", False),
            recipe_limit=getattr(args, "workbench_recipe_limit", None) or None,
        )
    if getattr(args, "no_workbench", False) or not db_path.exists():
        return {
            "unavailable": True,
            "db_path": str(db_path),
            "reason": "workbench disabled or database missing",
        }
    return build_dashboard(
        db_path,
        rowid=str(row.get("rowid") or ""),
        upc=str(row.get("upc") or ""),
    )


def compact_workbench_dashboard(dashboard: dict[str, Any]) -> dict[str, Any]:
    if dashboard.get("unavailable"):
        return dashboard
    witnesses = dashboard.get("witnesses") if isinstance(dashboard.get("witnesses"), dict) else {}
    return {
        "schema_version": dashboard.get("schema_version"),
        "observed_facets": dashboard.get("observed_facets") or {},
        "candidate_families": [
            {
                "family_id": family.get("family_id"),
                "score": family.get("score"),
                "base_codes_seen": (family.get("base_codes_seen") or [])[:8],
                "matched_terms": (family.get("matched_terms") or [])[:10],
                "signals": (family.get("signals") or [])[:6],
                "top_matching_codes": (family.get("top_matching_codes") or [])[:6],
                "top_full_codes": (family.get("top_full_codes") or [])[:6],
                "top_paths": (family.get("top_paths") or [])[:5],
                "why_plausible": (family.get("why_plausible") or [])[:5],
                "why_suspicious": (family.get("why_suspicious") or [])[:5],
                "expand_tools": (family.get("expand_tools") or [])[:3],
            }
            for family in (dashboard.get("candidate_families") or [])[:6]
            if isinstance(family, dict)
        ],
        "join_risks": [
            {
                "risk": risk.get("risk"),
                "product_audience": risk.get("product_audience"),
                "question": risk.get("question"),
                "ordinary_recipe_examples": (risk.get("ordinary_recipe_examples") or [])[:3],
            }
            for risk in (dashboard.get("join_risks") or [])[:4]
            if isinstance(risk, dict)
        ],
        "witnesses": {
            "same_upc": (witnesses.get("same_upc") or [])[:8],
            "code_neighbor_fit": [
                {
                    "htc_code": row.get("htc_code"),
                    "fit_score": row.get("fit_score"),
                    "shared_terms": (row.get("shared_terms") or [])[:12],
                    "product_terms_not_seen_in_neighbors": (row.get("product_terms_not_seen_in_neighbors") or [])[:12],
                    "neighbor_terms_not_seen_in_product": (row.get("neighbor_terms_not_seen_in_product") or [])[:12],
                    "risk": row.get("risk"),
                    "question": row.get("question"),
                    "examples": (row.get("examples") or [])[:3],
                }
                for row in (witnesses.get("code_neighbor_fit") or [])[:8]
                if isinstance(row, dict)
            ],
            "recipe_use": (witnesses.get("recipe_use") or [])[:8],
        },
        "expandable_branches": (dashboard.get("expandable_branches") or [])[:12],
    }


def pre_expand_dashboard_families(args: argparse.Namespace, dashboard: dict[str, Any], *, limit: int = 2) -> list[dict[str, Any]]:
    if dashboard.get("unavailable"):
        return []
    expanded = []
    for family in (dashboard.get("candidate_families") or [])[:limit]:
        if not isinstance(family, dict):
            continue
        family_id = str(family.get("family_id") or "").strip()
        if not family_id:
            continue
        expanded_family = expand_candidate_family(
            args.workbench_db,
            family_id=family_id,
            limit_codes=6,
            limit_examples_per_code=2,
        )
        expanded_family["codes"] = [
            {
                "htc_code": code.get("htc_code"),
                "row_count": code.get("row_count"),
                "modal_canonical_path": code.get("modal_canonical_path"),
                "top_full_codes": (code.get("top_full_codes") or [])[:6],
                "top_leaf_paths": (code.get("top_leaf_paths") or [])[:5],
                "top_modifiers": (code.get("top_modifiers") or [])[:5],
                "title_samples": (code.get("title_samples") or [])[:4],
                "examples": (code.get("examples") or [])[:2],
            }
            for code in (expanded_family.get("codes") or [])[:6]
            if isinstance(code, dict)
        ]
        expanded.append(expanded_family)
    return expanded


def suggested_dashboard_tools(dashboard: dict[str, Any], *, limit: int = 2) -> list[str]:
    tools = []
    for family in (dashboard.get("candidate_families") or [])[:limit]:
        if not isinstance(family, dict):
            continue
        family_id = str(family.get("family_id") or "").strip()
        if family_id:
            tools.append(f"expand_candidate_family:{family_id}")
    return tools


def compact_tool_result_for_prompt(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("tool") == "expand_candidate_family":
        return {
            "tool": "expand_candidate_family",
            "family_id": result.get("family_id"),
            "code_count": result.get("code_count"),
            "codes": [
                {
                    "htc_code": code.get("htc_code"),
                    "row_count": code.get("row_count"),
                    "modal_canonical_path": code.get("modal_canonical_path"),
                    "top_full_codes": (code.get("top_full_codes") or [])[:4],
                    "top_leaf_paths": (code.get("top_leaf_paths") or [])[:3],
                    "top_modifiers": (code.get("top_modifiers") or [])[:3],
                    "title_samples": (code.get("title_samples") or [])[:2],
                    "examples": [
                        {
                            "title": example.get("title"),
                            "htc_code": example.get("htc_code"),
                            "htc_full_code": example.get("htc_full_code"),
                            "canonical_path": example.get("canonical_path"),
                            "retail_leaf_path": example.get("retail_leaf_path"),
                            "modifier": example.get("modifier"),
                        }
                        for example in (code.get("examples") or [])[:1]
                        if isinstance(example, dict)
                    ],
                }
                for code in (result.get("codes") or [])[:4]
                if isinstance(code, dict)
            ],
            "cursor": result.get("cursor"),
        }
    if "rows" in result:
        rows = result.get("rows") if isinstance(result.get("rows"), list) else []
        return {
            **{k: v for k, v in result.items() if k != "rows"},
            "rows": rows[:5],
        }
    return result


def compact_tool_results_for_prompt(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [compact_tool_result_for_prompt(result) for result in results if isinstance(result, dict)]


def compact_ranker_candidates(candidates: list[Any]) -> list[dict[str, Any]]:
    out = []
    for cand in candidates[:5]:
        d = asdict(cand) if hasattr(cand, "__dataclass_fields__") else dict(cand)
        out.append({
            "htc_code": clean_htc(d.get("htc_code")),
            "score": d.get("score"),
            "canonical_path": d.get("canonical_path"),
            "retail_leaf_path": d.get("retail_leaf_path"),
            "product_identity": d.get("product_identity"),
            "row_count": d.get("row_count"),
            "evidence_terms": (d.get("evidence_terms") or [])[:10],
            "missing_required_identity_terms": (d.get("missing_required_identity_terms") or [])[:8],
            "signal_scores": {
                "title_overlap": d.get("title_overlap"),
                "search_overlap": d.get("search_overlap"),
                "path_overlap": d.get("path_overlap"),
                "aisle_overlap": d.get("aisle_overlap"),
                "string_similarity": d.get("string_similarity"),
                "authority_penalty": d.get("authority_penalty"),
            },
        })
    return out


def build_evidence_packet(args: argparse.Namespace, row_number: int, row: dict[str, str], refs: dict, inv: dict, df: dict) -> tuple[dict[str, Any], list[Any]]:
    consensus_path = args.consensus
    candidates = rank_candidates(row, refs, inv, df)
    signals = {key: sorted(value) for key, value in weighted_tokens(row).items()}
    dashboard = build_workbench_dashboard_for_row(args, row)
    compact_dashboard = compact_workbench_dashboard(dashboard)
    raw_witnesses = dashboard.get("witnesses") if isinstance(dashboard.get("witnesses"), dict) else {}
    packet = {
        "schema_version": 2,
        "product": compact_product(row),
        "row_number": row_number,
        "direct_consensus_candidates": (raw_witnesses.get("consensus_direct") or [])[:10],
        "workbench_dashboard": compact_dashboard,
        "suggested_expansion_tools": suggested_dashboard_tools(compact_dashboard),
        "supplemental_ranker_witnesses": {
            "ranker_is_not_truth": True,
            "signals": signals,
            "product_clues": product_clues(row),
            "candidate_htc_concepts": compact_ranker_candidates(candidates),
        },
        "tool_contract": [
            "expand_candidate_family:<FAMILY_ID>",
            "get_full_code_summary:<HTC_CODE>",
            "get_recipe_use_examples:<QUERY>",
            "fetch_product_rows_for_upc:<UPC>",
            "search_consensus:<QUERY>",
            "search_store_products:<QUERY>",
            "search_recipe_ingredients:<QUERY>",
            "sql_query:<READ_ONLY_SQL_OVER_product_rows_AND_consensus_rows>",
        ],
        "recipe_join_question": (
            "Decide whether this retail product may satisfy ordinary recipe ingredient terms, "
            "or whether it must be limited to variant/full-code joins or blocked joins."
        ),
    }
    return packet, candidates


def proposer_messages(packet: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PREFIX},
        {"role": "user", "content": json.dumps({
            "role": "proposer",
            "task": "Choose the correct HTC code or state needs_more_evidence.",
            "output_schema": PROPOSER_SCHEMA,
            "evidence_packet": packet,
        }, sort_keys=True)},
    ]


def planner_messages(packet: dict[str, Any]) -> list[dict[str, str]]:
    planner_packet = {
        "product": packet.get("product"),
        "workbench_dashboard": packet.get("workbench_dashboard"),
        "supplemental_ranker_witnesses": packet.get("supplemental_ranker_witnesses"),
        "tool_contract": packet.get("tool_contract"),
        "task_focus": (
            "Choose the smallest set of branch expansions needed before HTC/full-code reasoning. "
            "Prefer expanding candidate families over raw searches. Always include suspicious family rivals."
        ),
    }
    return [
        {"role": "system", "content": SYSTEM_PREFIX + "\nYou are now the evidence planner. Do not decide the final HTC."},
        {"role": "user", "content": json.dumps({
            "role": "planner",
            "task": "Select machine evidence tools to run before proposer reasoning.",
            "output_schema": PLANNER_SCHEMA,
            "evidence_map": planner_packet,
        }, sort_keys=True)},
    ]


def verifier_messages(packet: dict[str, Any], proposal: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PREFIX + "\nYou are now the independent verifier. Challenge the proposal aggressively."},
        {"role": "user", "content": json.dumps({
            "role": "verifier",
            "task": "Audit the proposal. Accept only if proof is strong; otherwise request machine evidence expansion.",
            "output_schema": VERIFIER_SCHEMA,
            "proposal_to_verify": proposal,
            "evidence_packet": packet,
        }, sort_keys=True)},
    ]


def fixer_messages(packet: dict[str, Any], proposal: dict[str, Any], verifier: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PREFIX + (
            "\nYou are now the fixer. Stage a code/full-code change only if the auditor accepted it. "
            "Do not invent a code. If the auditor rejects the HTC/full-code but establishes recipe compatibility "
            "such as ordinary_ingredient_substitute=no or join_level=blocked, stage_recipe_join_policy instead "
            "of returning machine_evidence_expansion."
        )},
        {"role": "user", "content": json.dumps({
            "role": "fixer",
            "task": "Decide the queue action from the proposal, auditor verdict, and evidence packet.",
            "output_schema": FIXER_SCHEMA,
            "proposal": proposal,
            "auditor": verifier,
            "evidence_packet": packet,
        }, sort_keys=True)},
    ]


def role_base_url(args: argparse.Namespace, role: str) -> str:
    return str(getattr(args, f"{role}_model_base_url", "") or args.model_base_url)


def role_model_name(args: argparse.Namespace, role: str) -> str:
    return str(getattr(args, f"{role}_model_name", "") or args.model_name)


def role_temperature(args: argparse.Namespace, role: str) -> float:
    value = getattr(args, f"{role}_temperature", None)
    return float(args.temperature if value is None else value)


def recipe_policy_from_compatibility(source: dict[str, Any]) -> dict[str, Any]:
    compat = source.get("recipe_compatibility") if isinstance(source.get("recipe_compatibility"), dict) else {}
    ordinary = str(compat.get("ordinary_ingredient_substitute") or "").strip().lower()
    join_level = str(compat.get("join_level") or "").strip().lower()
    incompatible = compat.get("incompatible_recipe_terms") if isinstance(compat.get("incompatible_recipe_terms"), list) else []
    compatible = compat.get("compatible_recipe_terms") if isinstance(compat.get("compatible_recipe_terms"), list) else []
    evidence = compat.get("evidence") if isinstance(compat.get("evidence"), list) else []
    if ordinary != "no" and join_level not in {"blocked", "full_code"} and not incompatible:
        return {}
    return {
        "ordinary_ingredient_substitute": ordinary or "no",
        "join_level": join_level or "blocked",
        "compatible_recipe_terms": compatible,
        "incompatible_recipe_terms": incompatible,
        "blocks": [
            {"recipe_query": term, "reason": source.get("recipe_join_risk") or "auditor identified recipe compatibility risk"}
            for term in incompatible
        ],
        "allows": [
            {"recipe_query": term, "reason": "explicit recipe/audience/form match"}
            for term in compatible
        ],
        "evidence": evidence,
    }


def fallback_recipe_policy(proposal: dict[str, Any], verifier: dict[str, Any]) -> dict[str, Any]:
    verifier_policy = recipe_policy_from_compatibility(verifier)
    if verifier_policy:
        return verifier_policy
    return recipe_policy_from_compatibility(proposal)


def find_full_code_witness(value: Any, full_code: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if str(value.get("htc_full_code") or "").strip() == full_code:
            return value
        for child in value.values():
            found = find_full_code_witness(child, full_code)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_full_code_witness(child, full_code)
            if found:
                return found
    return None


def full_code_modifier_contradictions(product: dict[str, Any], witness: dict[str, Any]) -> list[str]:
    modifier = " ".join(str(witness.get(key) or "") for key in ["modifier", "retail_leaf_path"])
    if not modifier:
        return []
    product_terms = tokens(" ".join(str(product.get(key) or "") for key in [
        "name", "brand", "search_term", "category_path", "category_path_walmart",
        "tree_product_identity", "tree_canonical_path", "tree_modifier",
    ]), keep_weak=True)
    modifier_terms = tokens(modifier, keep_weak=True)
    ignored = {
        "baby", "cereal", "food", "foods", "grain", "grow", "hot", "infant", "non",
        "oat", "oatmeal", "organic", "pantry", "toddler", "whole", "with",
    }
    absent = sorted(term for term in modifier_terms - product_terms - ignored if len(term) > 3)
    return absent[:8]


def validate_final_state_against_packet(final: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    full_code = str(final.get("accepted_htc_full_code") or "").strip()
    if not full_code or final.get("action") not in {"stage_htc_update", "stage_full_code_repair"}:
        return final
    witness = find_full_code_witness(packet, full_code)
    if not witness:
        return final
    product = packet.get("product") if isinstance(packet.get("product"), dict) else {}
    absent = full_code_modifier_contradictions(product, witness)
    if not absent:
        return final
    repaired = dict(final)
    repaired.update({
        "action": "machine_evidence_expansion",
        "verdict": "needs_more_evidence",
        "validation_errors": [{
            "error": "accepted_full_code_modifier_contradicts_product",
            "accepted_htc_full_code": full_code,
            "absent_modifier_terms": absent,
            "witness_modifier": witness.get("modifier"),
            "witness_retail_leaf_path": witness.get("retail_leaf_path"),
        }],
        "production_writes": False,
    })
    return repaired


def final_state_from_fixer(
    current_htc: str,
    fixer: dict[str, Any],
    *,
    proposal: dict[str, Any] | None = None,
    verifier: dict[str, Any] | None = None,
) -> dict[str, Any]:
    accepted = clean_htc(fixer.get("accepted_htc_code") or "")
    accepted_full_code = str(fixer.get("accepted_htc_full_code") or "").strip()
    staged_change = fixer.get("staged_change") if isinstance(fixer.get("staged_change"), dict) else {}
    if not accepted_full_code:
        accepted_full_code = str(staged_change.get("to_htc_full_code") or "").strip()
    recipe_join_policy = staged_change.get("recipe_join_policy") if isinstance(staged_change.get("recipe_join_policy"), dict) else {}
    verdict = str(fixer.get("fixer_verdict") or "machine_evidence_expansion")
    verifier_verdict = str((verifier or {}).get("verifier_verdict") or "")
    policy_allowed = verdict == "stage_recipe_join_policy" or verifier_verdict in {"verified_current", "verified_update"}
    if not recipe_join_policy and policy_allowed:
        recipe_join_policy = fallback_recipe_policy(proposal or {}, verifier or {})
    if verdict == "stage_htc_update" and accepted and accepted != current_htc:
        action = "stage_htc_update"
        shared_verdict = "verified_update"
    elif verdict in {"stage_htc_update", "stage_full_code_repair"} and accepted_full_code:
        action = "stage_full_code_repair"
        shared_verdict = "verified_current" if not accepted or accepted == current_htc else "verified_update"
    elif verdict == "stage_recipe_join_policy" or (recipe_join_policy and not accepted_full_code and not accepted):
        action = "stage_recipe_join_policy"
        shared_verdict = "verified_current"
    elif verdict == "no_change_verified_current":
        action = "no_change_verified_current"
        shared_verdict = "verified_current"
    else:
        action = "machine_evidence_expansion"
        shared_verdict = "needs_more_evidence"
    raw_write_scope = staged_change.get("write_scope") if isinstance(staged_change.get("write_scope"), list) else []
    if action == "stage_full_code_repair":
        write_scope = [
            scope for scope in raw_write_scope
            if scope in {"full_code_assignment", "recipe_join_policy"}
        ]
        if "full_code_assignment" not in write_scope:
            write_scope.insert(0, "full_code_assignment")
    elif action == "stage_recipe_join_policy":
        write_scope = raw_write_scope or ["recipe_join_policy"]
    elif action == "stage_htc_update":
        write_scope = raw_write_scope or (
            ["product_htc_assignment", "full_code_assignment"] if accepted_full_code else ["product_htc_assignment"]
        )
    else:
        write_scope = raw_write_scope
    return {
        "verdict": shared_verdict,
        "accepted_htc_code": accepted,
        "accepted_htc_full_code": accepted_full_code,
        "facet_updates": staged_change.get("facet_updates") if isinstance(staged_change.get("facet_updates"), dict) else {},
        "recipe_join_policy": recipe_join_policy,
        "evidence_ids": staged_change.get("evidence_ids") if isinstance(staged_change.get("evidence_ids"), list) else [],
        "write_scope": write_scope,
        "facet_notes": staged_change.get("facet_notes", ""),
        "action": action,
        "production_writes": False,
    }


def run_product(args: argparse.Namespace, refs: dict, inv: dict, df: dict, row_number: int, row: dict[str, str]) -> dict[str, Any]:
    packet, _candidates = build_evidence_packet(args, row_number, row, refs, inv, df)
    t0 = time.time()
    rounds = []
    machine_evidence_rounds = []
    planner: dict[str, Any] = {}
    planner_timing = 0.0
    if getattr(args, "planning_rounds", 1):
        planner_start = time.time()
        planner = post_chat(
            role_base_url(args, "planner"),
            role_model_name(args, "planner"),
            planner_messages(packet),
            max_tokens=min(args.max_tokens, 700),
            temperature=role_temperature(args, "planner"),
            timeout=args.timeout,
        )
        planner_timing = round(time.time() - planner_start, 3)
        planned_tools = planner_tool_requests(packet, planner)
        planned_results = execute_machine_tools(args.products, args.consensus, args.recipes, args.workbench_db, planned_tools)
        packet["planned_evidence"] = {
            "planner": planner,
            "requested_tools": planned_tools,
            "tool_results": compact_tool_results_for_prompt(planned_results),
        }
    proposal: dict[str, Any] = {}
    verifier: dict[str, Any] = {}
    for round_index in range(args.evidence_rounds + 1):
        round_start = time.time()
        proposal = post_chat(
            role_base_url(args, "proposer"),
            role_model_name(args, "proposer"),
            proposer_messages(packet),
            max_tokens=args.max_tokens,
            temperature=role_temperature(args, "proposer"),
            timeout=args.timeout,
        )
        proposal_done = time.time()
        verifier = post_chat(
            role_base_url(args, "auditor"),
            role_model_name(args, "auditor"),
            verifier_messages(packet, proposal),
            max_tokens=args.max_tokens,
            temperature=role_temperature(args, "auditor"),
            timeout=args.timeout,
        )
        verifier_done = time.time()
        rounds.append({
            "round": round_index,
            "proposal": proposal,
            "verifier": verifier,
            "timing_seconds": {
                "proposal": round(proposal_done - round_start, 3),
                "verifier": round(verifier_done - proposal_done, 3),
                "total_model": round(verifier_done - round_start, 3),
            },
        })
        if verifier.get("verifier_verdict") != "needs_more_evidence" or round_index >= args.evidence_rounds:
            break
        requested_tools = machine_tool_requests(packet, proposal, verifier)
        if not requested_tools:
            break
        tool_results = execute_machine_tools(args.products, args.consensus, args.recipes, args.workbench_db, requested_tools)
        machine_evidence_rounds.append({
            "round": round_index + 1,
            "requested_tools": requested_tools,
            "tool_results": compact_tool_results_for_prompt(tool_results),
        })
        packet["machine_evidence_rounds"] = machine_evidence_rounds
    fixer_start = time.time()
    fixer = post_chat(
        role_base_url(args, "fixer"),
        role_model_name(args, "fixer"),
        fixer_messages(packet, proposal, verifier),
        max_tokens=args.max_tokens,
        temperature=role_temperature(args, "fixer"),
        timeout=args.timeout,
    )
    fixer_done = time.time()
    final = final_state_from_fixer(clean_htc(row.get("htc_code")), fixer, proposal=proposal, verifier=verifier)
    final = validate_final_state_against_packet(final, packet)
    t2 = time.time()
    first_timing = rounds[0]["timing_seconds"] if rounds else {"proposal": 0.0, "verifier": 0.0}
    result = {
        "schema_version": 1,
        "agent": "htc_single_product_proof_agent",
        "model_base_url": args.model_base_url,
        "model_name": args.model_name,
        "model_roles": {
            "planner": {"base_url": role_base_url(args, "planner"), "model": role_model_name(args, "planner")},
            "proposer": {"base_url": role_base_url(args, "proposer"), "model": role_model_name(args, "proposer")},
            "auditor": {"base_url": role_base_url(args, "auditor"), "model": role_model_name(args, "auditor")},
            "fixer": {"base_url": role_base_url(args, "fixer"), "model": role_model_name(args, "fixer")},
        },
        "row_number": row_number,
        "product": compact_product(row),
        "planner": planner,
        "proposal": proposal,
        "verifier": verifier,
        "fixer": fixer,
        "model_rounds": rounds,
        "machine_evidence_rounds": machine_evidence_rounds,
        "final": final,
        "timing_seconds": {
            "planner": planner_timing,
            "proposal": first_timing.get("proposal", 0.0),
            "verifier": first_timing.get("verifier", 0.0),
            "fixer": round(fixer_done - fixer_start, 3),
            "total_model": round(t2 - t0, 3),
        },
        "evidence_packet": packet,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    output = args.out_dir / f"proof_{proof_key(row_number, row)}.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result["output"] = str(output)
    write_queue_record(args.out_dir, result)
    return result


def run_one(args: argparse.Namespace) -> dict[str, Any]:
    refs, inv, df = build_references(args.consensus)
    row_number, row = load_product_row(args.products, upc=args.upc, rowid=args.rowid)
    return run_product(args, refs, inv, df, row_number, row)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_queue_record(out_dir: Path, result: dict[str, Any]) -> None:
    final = result.get("final") if isinstance(result.get("final"), dict) else {}
    product = result.get("product") if isinstance(result.get("product"), dict) else {}
    proof = result.get("output")
    if final.get("action") == "stage_htc_update":
        append_jsonl(out_dir / "staged_htc_updates.jsonl", {
            "action": "stage_htc_update",
            "upc": product.get("upc"),
            "rowid": product.get("rowid"),
            "name": product.get("name"),
            "from_htc_code": clean_htc(product.get("htc_code")),
            "to_htc_code": final.get("accepted_htc_code"),
            "to_htc_full_code": final.get("accepted_htc_full_code"),
            "facet_updates": final.get("facet_updates") or {},
            "recipe_join_policy": final.get("recipe_join_policy") or {},
            "evidence_ids": final.get("evidence_ids") or [],
            "write_scope": final.get("write_scope") or [],
            "facet_notes": final.get("facet_notes"),
            "verdict": final.get("verdict"),
            "proof": proof,
            "production_writes": False,
        })
    elif final.get("action") == "stage_full_code_repair":
        append_jsonl(out_dir / "staged_full_code_repairs.jsonl", {
            "action": "stage_full_code_repair",
            "upc": product.get("upc"),
            "rowid": product.get("rowid"),
            "name": product.get("name"),
            "from_htc_code": clean_htc(product.get("htc_code")),
            "to_htc_code": final.get("accepted_htc_code") or clean_htc(product.get("htc_code")),
            "to_htc_full_code": final.get("accepted_htc_full_code"),
            "facet_updates": final.get("facet_updates") or {},
            "recipe_join_policy": final.get("recipe_join_policy") or {},
            "evidence_ids": final.get("evidence_ids") or [],
            "write_scope": final.get("write_scope") or ["full_code_assignment"],
            "facet_notes": final.get("facet_notes"),
            "verdict": final.get("verdict"),
            "proof": proof,
            "production_writes": False,
        })
    elif final.get("action") == "stage_recipe_join_policy":
        append_jsonl(out_dir / "staged_recipe_join_policies.jsonl", {
            "action": "stage_recipe_join_policy",
            "upc": product.get("upc"),
            "rowid": product.get("rowid"),
            "name": product.get("name"),
            "current_htc_code": clean_htc(product.get("htc_code")),
            "recipe_join_policy": final.get("recipe_join_policy") or {},
            "evidence_ids": final.get("evidence_ids") or [],
            "write_scope": final.get("write_scope") or ["recipe_join_policy"],
            "facet_notes": final.get("facet_notes"),
            "verdict": final.get("verdict"),
            "proof": proof,
            "production_writes": False,
        })
    elif final.get("action") == "machine_evidence_expansion":
        verifier = result.get("verifier") if isinstance(result.get("verifier"), dict) else {}
        packet = result.get("evidence_packet") if isinstance(result.get("evidence_packet"), dict) else {}
        proposal = result.get("proposal") if isinstance(result.get("proposal"), dict) else {}
        required_next_tools = [
            str(tool)
            for tool in (verifier.get("required_next_tools") or [])
            if valid_machine_tool(tool)
        ]
        if not required_next_tools:
            required_next_tools = machine_tool_requests(packet, proposal, verifier)
        append_jsonl(out_dir / "machine_evidence_expansion.jsonl", {
            "action": "machine_evidence_expansion",
            "upc": product.get("upc"),
            "rowid": product.get("rowid"),
            "name": product.get("name"),
            "current_htc_code": clean_htc(product.get("htc_code")),
            "required_next_tools": required_next_tools,
            "proof": proof,
            "production_writes": False,
        })


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consensus", type=Path, default=DEFAULT_CONSENSUS)
    parser.add_argument("--products", type=Path, default=DEFAULT_PRODUCTS)
    parser.add_argument("--recipes", type=Path, default=DEFAULT_RECIPES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--upc", default="")
    parser.add_argument("--rowid", default="")
    parser.add_argument("--model-base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model-name", default=DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--planner-model-base-url", default="")
    parser.add_argument("--planner-model-name", default="")
    parser.add_argument("--planner-temperature", type=float, default=None)
    parser.add_argument("--proposer-model-base-url", default="")
    parser.add_argument("--proposer-model-name", default="")
    parser.add_argument("--proposer-temperature", type=float, default=None)
    parser.add_argument("--auditor-model-base-url", default="")
    parser.add_argument("--auditor-model-name", default="")
    parser.add_argument("--auditor-temperature", type=float, default=None)
    parser.add_argument("--fixer-model-base-url", default="")
    parser.add_argument("--fixer-model-name", default="")
    parser.add_argument("--fixer-temperature", type=float, default=None)
    parser.add_argument("--workbench-db", type=Path, default=DEFAULT_WORKBENCH_DB)
    parser.add_argument("--no-workbench", action="store_true")
    parser.add_argument("--build-workbench-if-missing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--workbench-recipe-limit", type=int, default=250000)
    parser.add_argument("--no-workbench-fts", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=1000)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--evidence-rounds", type=int, default=1)
    parser.add_argument("--planning-rounds", type=int, default=1)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_one(args)
    print(json.dumps({
        "agent": result["agent"],
        "product": result["product"],
        "planner": result["planner"],
        "proposal": result["proposal"],
        "verifier": result["verifier"],
        "fixer": result["fixer"],
        "final": result["final"],
        "timing_seconds": result["timing_seconds"],
        "output": result["output"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
