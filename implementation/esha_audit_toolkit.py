"""Read-only ESHA audit packet toolkit.

This is the backend that an MCP server or Nebius batch runner should wrap.
It exposes the current MD-card evidence without giving an LLM direct write
access to source files.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any


IMPLEMENTATION_ROOT = Path(__file__).resolve().parent
REPO_ROOT = IMPLEMENTATION_ROOT.parent
OUTPUT_ROOT = IMPLEMENTATION_ROOT / "output"
PRODUCT_DB = REPO_ROOT / "data" / "master_products.db"
PROGRESS_CSV = OUTPUT_ROOT / "top2500_cleanup_progress.csv"
PACK_INDEX_CSV = OUTPUT_ROOT / "esha_code_query_pack_index.csv"
CROSSREF_INDEX_CSV = OUTPUT_ROOT / "esha_query_cross_reference_index.csv"
LOOKUP_DB = OUTPUT_ROOT / "product_esha_lookup.db"
NEBIUS_AUDIT_OUT = OUTPUT_ROOT / "nebius_esha_audit"
FORBIDDEN_FILES = {"implementation/approved_normalization_rules.csv"}
CONTRACT_ROOT = IMPLEMENTATION_ROOT / "esha_contracts"
MATRIX_SLICE_DIR = OUTPUT_ROOT / "esha_cleanup_matrix_slices"
GLOBAL_MATRIX_CSV = OUTPUT_ROOT / "esha_cleanup_matrix.csv"
GRAPH_DB = OUTPUT_ROOT / "provenance_graph.db"

FAMILY_CONTRACT_HINTS = {
    "beverage": ("reviewed_pantry.py",),
    "grain": ("reviewed_pantry.py",),
    "milk": ("reviewed_pantry.py",),
    "oil": ("reviewed_pantry.py",),
    "spice": ("reviewed_pantry.py", "reviewed_top2500_head.py"),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def dump_json(obj: Any, out: str | None = None) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def command_result(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        args,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": args,
    }


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def queue_next(
    limit: int,
    priorities: set[str] | None = None,
    issue_class: str | None = None,
    status: str | None = "todo",
) -> list[dict[str, str]]:
    rows = read_csv(PROGRESS_CSV)
    selected: list[dict[str, str]] = []
    for row in rows:
        if status and row.get("check_status") != status:
            continue
        if priorities and row.get("issue_priority") not in priorities:
            continue
        if issue_class and row.get("issue_class") != issue_class:
            continue
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def all_cards(limit: int = 50, offset: int = 0, family: str | None = None) -> list[dict[str, str]]:
    rows = read_csv(PACK_INDEX_CSV)
    selected: list[dict[str, str]] = []
    skipped = 0
    wanted_family = family.strip().lower() if family else None
    for row in rows:
        if wanted_family and row.get("family", "").strip().lower() != wanted_family:
            continue
        if skipped < offset:
            skipped += 1
            continue
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def find_index_row(esha_code: int) -> dict[str, str] | None:
    code = str(esha_code)
    for row in read_csv(PACK_INDEX_CSV):
        if row.get("esha_code") == code:
            return row
    return None


def find_pack_path(esha_code: int) -> Path | None:
    row = find_index_row(esha_code)
    if row and row.get("pack_path"):
        path = Path(row["pack_path"])
        if path.exists():
            return path
    matches = sorted((OUTPUT_ROOT / "esha_code_query_packs").glob(f"*/*{esha_code:06d}_*.md"))
    return matches[0] if matches else None


def card_sections(markdown: str) -> list[str]:
    return re.findall(r"^##\s+(.+?)\s*$", markdown, flags=re.MULTILINE)


def get_card(esha_code: int, max_chars: int = 60000) -> dict[str, Any]:
    index_row = find_index_row(esha_code)
    pack_path = find_pack_path(esha_code)
    if not pack_path:
        return {
            "error": "card_not_found",
            "esha_code": esha_code,
            "index_row": index_row,
        }
    text = pack_path.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return {
        "esha_code": esha_code,
        "index_row": index_row,
        "pack_path": str(pack_path),
        "truncated": truncated,
        "sections": card_sections(text),
        "card_markdown": text,
    }


def contract_sources(esha_code: int, max_chars: int = 60000) -> dict[str, Any]:
    code = str(esha_code)
    padded = f"{esha_code:07d}"
    patterns = (
        f'"{code}"',
        f"'{code}'",
        f"match_esha_{padded}",
        f"ESHA {code}:",
    )
    paths = [
        CONTRACT_ROOT / "__init__.py",
        *sorted(CONTRACT_ROOT.glob("reviewed_*.py")),
    ]
    matches: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not any(pattern in text for pattern in patterns):
            continue
        truncated = len(text) > max_chars
        matches.append(
            {
                "path": str(path),
                "relative_path": str(path.relative_to(REPO_ROOT)),
                "truncated": truncated,
                "source": text[:max_chars] if truncated else text,
            }
        )
    suggested: list[dict[str, Any]] = []
    if not matches:
        family = (find_index_row(esha_code) or {}).get("family", "")
        for filename in FAMILY_CONTRACT_HINTS.get(family, ()):
            path = CONTRACT_ROOT / filename
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            truncated = len(text) > max_chars
            suggested.append(
                {
                    "path": str(path),
                    "relative_path": str(path.relative_to(REPO_ROOT)),
                    "truncated": truncated,
                    "reason": f"existing reviewed contract module for {family} cards without a direct contract",
                    "source": text[:max_chars] if truncated else text,
                }
            )
    return {"esha_code": esha_code, "matches": matches, "suggested_files": suggested}


def safe_fts_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", query.lower())
    return " ".join(tokens)


def search_products(query: str, limit: int = 25, category: str | None = None) -> dict[str, Any]:
    fts_query = safe_fts_query(query)
    if not fts_query:
        return {"query": query, "fts_query": fts_query, "rows": []}

    sql = """
        SELECT
            p.gtin_upc,
            p.fdc_id,
            p.description,
            p.brand_owner,
            p.brand_name,
            p.branded_food_category,
            p.ingredients,
            p.package_weight,
            p.serving_size,
            p.serving_size_unit,
            p.calories,
            p.protein_g,
            p.fat_g,
            p.carbs_g,
            p.sugar_g,
            p.sodium_mg,
            bm25(products_fts) AS score
        FROM products_fts
        JOIN products p ON p.rowid = products_fts.rowid
        WHERE products_fts MATCH ?
    """
    params: list[Any] = [fts_query]
    if category:
        sql += " AND lower(coalesce(p.branded_food_category, '')) LIKE ?"
        params.append(f"%{category.lower()}%")
    sql += " ORDER BY score LIMIT ?"
    params.append(limit)

    with sqlite3.connect(PRODUCT_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    return {"query": query, "fts_query": fts_query, "category": category, "rows": rows}


def cross_reference(esha_code: int, limit: int = 100) -> list[dict[str, str]]:
    code = str(esha_code)
    rows: list[dict[str, str]] = []
    if not CROSSREF_INDEX_CSV.exists():
        return rows
    for row in read_csv(CROSSREF_INDEX_CSV):
        if row.get("source_code") == code:
            rows.append(row)
            if len(rows) >= limit:
                break
    return rows


def matrix_slice(esha_code: int, limit: int = 100, rebuild: bool = False) -> dict[str, Any]:
    code = str(esha_code)
    MATRIX_SLICE_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = MATRIX_SLICE_DIR / f"{code}.csv"
    summary_path = MATRIX_SLICE_DIR / f"{code}.md"
    build = None
    if rebuild or not csv_path.exists():
        build = command_result(
            [
                "python3",
                "implementation/build_esha_cleanup_matrix.py",
                "--code",
                code,
                "--out-csv",
                str(csv_path),
                "--out-summary",
                str(summary_path),
            ]
        )

    rows: list[dict[str, str]] = []
    source = ""
    if csv_path.exists():
        rows = read_csv(csv_path)
        source = "slice"
    elif GLOBAL_MATRIX_CSV.exists():
        rows = [row for row in read_csv(GLOBAL_MATRIX_CSV) if row.get("source_code") == code]
        source = "global"

    summary = summary_path.read_text(encoding="utf-8", errors="replace") if summary_path.exists() else ""
    return {
        "esha_code": esha_code,
        "status": "ok" if rows or csv_path.exists() else "missing",
        "source": source,
        "matrix_csv": str(csv_path),
        "matrix_summary": str(summary_path),
        "build": build,
        "total_rows": len(rows),
        "rows": rows[:limit],
        "summary": summary[:12000],
    }


def code_filter_sql(code: str) -> tuple[str, list[Any]]:
    return (
        """
        EXISTS (
            SELECT 1
            FROM product_esha_assignments a
            WHERE a.gtin_upc = r.gtin_upc AND a.esha_code = ?
        )
        """,
        [code],
    )


def product_codes(
    limit: int = 50,
    gtin: str | None = None,
    esha_code: str | None = None,
    collision_status: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    if not LOOKUP_DB.exists():
        return {
            "error": "lookup_db_not_found",
            "lookup_db": str(LOOKUP_DB),
            "suggested_rebuild_command": "python3 implementation/build_product_esha_lookup.py",
        }
    sql = "SELECT * FROM product_esha_code_rollup r"
    where: list[str] = []
    params: list[Any] = []
    if gtin:
        where.append("r.gtin_upc = ?")
        params.append(gtin)
    if esha_code:
        clause, clause_params = code_filter_sql(str(esha_code))
        where.append(clause)
        params.extend(clause_params)
    if collision_status:
        where.append("r.collision_status = ?")
        params.append(collision_status)
    if q:
        where.append("lower(r.product_description) LIKE ?")
        params.append(f"%{q.lower()}%")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.esha_code_count DESC, r.product_description, r.gtin_upc LIMIT ?"
    params.append(limit)
    with sqlite3.connect(LOOKUP_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    return {
        "lookup_db": str(LOOKUP_DB),
        "filters": {
            "gtin": gtin,
            "esha_code": esha_code,
            "collision_status": collision_status,
            "q": q,
            "limit": limit,
        },
        "rows": rows,
    }


def product_collisions(limit: int = 50, esha_code: str | None = None) -> dict[str, Any]:
    return product_codes(limit=limit, esha_code=esha_code, collision_status="collision")


def trace_entity(kind: str, key: str, limit: int = 50) -> dict[str, Any]:
    from provenance_graph import trace_entity as graph_trace_entity

    return graph_trace_entity(kind, key, db_path=GRAPH_DB, edge_limit=limit)


def progress_row_for_item(normalized_item: str) -> dict[str, str] | None:
    wanted = normalized_item.strip().lower()
    for row in read_csv(PROGRESS_CSV):
        if row.get("normalized_item", "").strip().lower() == wanted:
            return row
    return None


def packet_for_code(
    esha_code: int,
    max_card_chars: int = 60000,
    crossref_limit: int = 50,
    product_limit: int = 25,
) -> dict[str, Any]:
    index_row = find_index_row(esha_code)
    description = index_row.get("description") if index_row else ""
    card = get_card(esha_code, max_chars=max_card_chars)
    contracts = contract_sources(esha_code, max_chars=30000)
    crossref = cross_reference(esha_code, limit=crossref_limit)
    assigned_products = product_codes(limit=product_limit, esha_code=str(esha_code))
    products = search_products(description or str(esha_code), limit=product_limit)
    warnings: list[str] = []
    if not contracts.get("matches"):
        warnings.append("no_direct_reviewed_contract_for_code")
    if not assigned_products.get("rows"):
        warnings.append("no_products_currently_assigned_to_code")
    return {
        "task": "audit_esha_card",
        "lookup_mode": "esha_code",
        "normalized_item": description,
        "esha_code": esha_code,
        "esha_description": description,
        "all_card_index_row": index_row,
        "card": card,
        "contract_sources": contracts,
        "cross_reference_rows": crossref,
        "assigned_product_codes": assigned_products,
        "product_search": products,
        "audit_warnings": warnings,
        "instructions": {
            "source_of_truth": "ESHA MD card plus reviewed ESHA contract",
            "shopping_expectation_question": "If a recipe called for this ESHA item, would a shopper reasonably expect this product in the cart?",
            "patch_scope": "product-side ESHA card/query contracts, generated card artifacts, and regression tests only",
            "allowed_decisions": [
                "no_change",
                "tighten_current_contract",
                "retarget_to_more_specific_esha",
                "explicit_no_esha_terminal",
                "query_rescue_only",
                "needs_more_context",
            ],
            "model_returns_structured_contract": True,
            "patch_lands_only_through_gate": True,
        },
    }


def surface_packet(
    normalized_item: str,
    max_card_chars: int = 60000,
    crossref_limit: int = 50,
    product_limit: int = 25,
) -> dict[str, Any]:
    progress = progress_row_for_item(normalized_item)
    if not progress:
        return {"error": "top2500_item_not_found", "normalized_item": normalized_item}

    code = parse_int(progress.get("esha_code"))
    card = get_card(code, max_chars=max_card_chars) if code is not None else None
    contracts = contract_sources(code, max_chars=30000) if code is not None else None
    crossref = cross_reference(code, limit=crossref_limit) if code is not None else []
    assigned_products = product_codes(limit=product_limit, esha_code=str(code)) if code is not None else None
    products = search_products(normalized_item, limit=product_limit)
    warnings: list[str] = []
    if code is None:
        warnings.append("no_esha_code_for_surface")
    elif contracts and not contracts.get("matches"):
        warnings.append("no_direct_reviewed_contract_for_code")
    if assigned_products is not None and not assigned_products.get("rows"):
        warnings.append("no_products_currently_assigned_to_code")

    return {
        "task": "audit_esha_card",
        "lookup_mode": "top2500_item",
        "normalized_item": normalized_item,
        "top2500_progress_row": progress,
        "esha_code": code,
        "esha_description": progress.get("esha_description"),
        "card": card,
        "contract_sources": contracts,
        "cross_reference_rows": crossref,
        "assigned_product_codes": assigned_products,
        "product_search": products,
        "audit_warnings": warnings,
        "instructions": {
            "source_of_truth": "ESHA MD card plus reviewed ESHA contract",
            "shopping_expectation_question": "If a recipe called for this ESHA item, would a shopper reasonably expect this product in the cart?",
            "patch_scope": "product-side ESHA card/query contracts, generated card artifacts, and regression tests only",
            "allowed_decisions": [
                "no_change",
                "tighten_current_contract",
                "retarget_to_more_specific_esha",
                "explicit_no_esha_terminal",
                "query_rescue_only",
                "needs_more_context",
            ],
            "model_returns_structured_contract": True,
            "patch_lands_only_through_gate": True,
        },
    }


def stage_patch(bundle_path: str) -> dict[str, Any]:
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    bundle_id = bundle.get("bundle_id")
    if not bundle_id:
        return {"error": "missing_bundle_id"}

    patch_text = bundle.get("patch", "")
    forbidden_hits = [name for name in FORBIDDEN_FILES if name in patch_text]
    if forbidden_hits:
        return {"error": "forbidden_file_in_patch", "forbidden_hits": forbidden_hits}

    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(bundle_id)).strip("_")
    if not safe_id:
        return {"error": "invalid_bundle_id"}

    out_dir = NEBIUS_AUDIT_OUT / safe_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bundle.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "proposal.patch").write_text(patch_text, encoding="utf-8")
    return {
        "status": "staged",
        "bundle_id": safe_id,
        "bundle_path": str(out_dir / "bundle.json"),
        "patch_path": str(out_dir / "proposal.patch"),
    }


# --- new tools for MCP workbench (2026-04-22) ---

NUTRITION_PATH = IMPLEMENTATION_ROOT / "esha_nutrition.csv"
CANONICAL_TO_ESHA_PATH = IMPLEMENTATION_ROOT / "canonical_to_esha.csv"

_NUTRITION_CACHE: dict[int, dict[str, Any]] = {}


def _load_nutrition() -> dict[int, dict[str, Any]]:
    if _NUTRITION_CACHE:
        return _NUTRITION_CACHE
    for row in read_csv(NUTRITION_PATH):
        try:
            code = int(row["EshaCode"])
        except (ValueError, KeyError):
            continue

        def f(key: str) -> float | None:
            v = row.get(key)
            if v in (None, ""):
                return None
            try:
                return float(v)
            except ValueError:
                return None

        _NUTRITION_CACHE[code] = {
            "esha_code": code,
            "esha_description": row.get("esha_description", ""),
            "tier": row.get("tier", ""),
            "kcal_per_100g": f("kcal_per_100g"),
            "protein_per_100g": f("protein_per_100g"),
            "fat_per_100g": f("fat_per_100g"),
            "carbs_per_100g": f("carbs_per_100g"),
        }
    return _NUTRITION_CACHE


def compare_nutrient_fingerprint(esha_codes: list[int]) -> dict[str, Any]:
    """Return per-code nutrient profile + pairwise euclidean distance.

    Distances are over the (kcal, protein, fat, carbs) vector. Missing
    components contribute a fixed penalty so the agent can flag missing data.
    """
    nutrition = _load_nutrition()
    profiles: list[dict[str, Any]] = []
    for code in esha_codes:
        prof = nutrition.get(int(code))
        if prof is None:
            profiles.append({
                "esha_code": int(code),
                "esha_description": None,
                "tier": None,
                "kcal_per_100g": None,
                "protein_per_100g": None,
                "fat_per_100g": None,
                "carbs_per_100g": None,
            })
        else:
            profiles.append(dict(prof))

    def vec(p: dict[str, Any]) -> list[float | None]:
        return [p["kcal_per_100g"], p["protein_per_100g"], p["fat_per_100g"], p["carbs_per_100g"]]

    def distance(a: list[float | None], b: list[float | None]) -> float:
        total = 0.0
        for x, y in zip(a, b):
            if x is None or y is None:
                total += 2500.0
            else:
                total += (x - y) ** 2
        return total ** 0.5

    pairs = []
    for i in range(len(profiles)):
        for j in range(i + 1, len(profiles)):
            pairs.append({
                "code_a": profiles[i]["esha_code"],
                "code_b": profiles[j]["esha_code"],
                "distance": distance(vec(profiles[i]), vec(profiles[j])),
            })

    return {
        "profiles": profiles,
        "pairwise_euclid": pairs,
        "method": "euclidean over (kcal, protein_g, fat_g, carbs_g) per 100g; missing component => +50 penalty per axis",
    }


RECIPE_QA_DB = REPO_ROOT / "data" / "recipe_qa.db"


def recipe_context(recipe_id: int) -> dict[str, Any]:
    """Return recipe title + sibling ingredient list for context-aware resolution."""
    import sqlite3
    if not RECIPE_QA_DB.exists():
        return {"ok": False, "error": "recipe_qa.db missing"}
    con = sqlite3.connect(f"file:{RECIPE_QA_DB}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT recipe_id, clean_title, ingredients_json FROM recipe_verdicts WHERE recipe_id=?",
            (int(recipe_id),),
        ).fetchone()
    finally:
        con.close()
    if not row:
        return {"ok": False, "error": "recipe not found", "recipe_id": int(recipe_id)}
    rid, title, ings_json = row
    try:
        ingredients = json.loads(ings_json) if ings_json else []
    except json.JSONDecodeError:
        ingredients = []
    norm: list[dict[str, str]] = []
    for ing in ingredients:
        if isinstance(ing, str):
            norm.append({"display": ing, "item": ing})
        elif isinstance(ing, dict):
            norm.append({
                "display": (ing.get("display") or "").strip(),
                "item": (ing.get("item") or "").strip(),
            })
    return {
        "ok": True,
        "recipe_id": rid,
        "clean_title": title or "",
        "ingredients": norm,
    }


APPROVED_NORM_RULES = REPO_ROOT / "implementation" / "approved_normalization_rules.csv"
CANONICAL_ITEMS = REPO_ROOT / "implementation" / "canonical_items.csv"
REVIEWED_NUTRITION_ANCHORS = REPO_ROOT / "implementation" / "reviewed_nutrition_anchors.csv"


def prior_decisions(normalized_item: str) -> dict[str, Any]:
    """Return current registry state for a canonical across reviewed CSVs.

    Reads the existing source of truth — does not create a new memory store.
    """
    term = (normalized_item or "").strip().lower()

    def filter_rows(path: Path, fields: list[str]) -> list[dict[str, str]]:
        if not path.exists():
            return []
        hits: list[dict[str, str]] = []
        for row in read_csv(path):
            for f in fields:
                v = (row.get(f) or "").strip().lower()
                if v == term:
                    hits.append(row)
                    break
        return hits

    return {
        "normalized_item": term,
        "approved_normalization_rules": filter_rows(
            APPROVED_NORM_RULES, ["input_surface", "canonical_concept_key", "canonical_surface"]
        ),
        "canonical_items": filter_rows(
            CANONICAL_ITEMS, ["canonical_name"]
        ),
        "canonical_to_esha": filter_rows(
            CANONICAL_TO_ESHA_PATH, ["canonical_name"]
        ),
        "reviewed_nutrition_anchors": filter_rows(
            REVIEWED_NUTRITION_ANCHORS, ["concept_key"]
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ESHA audit packet toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    queue_parser = sub.add_parser("queue")
    queue_parser.add_argument("--limit", type=int, default=20)
    queue_parser.add_argument("--priority", action="append", default=None)
    queue_parser.add_argument("--issue-class")
    queue_parser.add_argument("--status", default="todo")
    queue_parser.add_argument("--out")

    cards_parser = sub.add_parser("cards")
    cards_parser.add_argument("--limit", type=int, default=50)
    cards_parser.add_argument("--offset", type=int, default=0)
    cards_parser.add_argument("--family")
    cards_parser.add_argument("--out")

    card_parser = sub.add_parser("card")
    card_parser.add_argument("--code", type=int, required=True)
    card_parser.add_argument("--max-chars", type=int, default=60000)
    card_parser.add_argument("--out")

    packet_parser = sub.add_parser("packet")
    packet_parser.add_argument("--item")
    packet_parser.add_argument("--code", type=int)
    packet_parser.add_argument("--max-card-chars", type=int, default=60000)
    packet_parser.add_argument("--crossref-limit", type=int, default=50)
    packet_parser.add_argument("--product-limit", type=int, default=25)
    packet_parser.add_argument("--out")

    products_parser = sub.add_parser("search-products")
    products_parser.add_argument("--query", required=True)
    products_parser.add_argument("--category")
    products_parser.add_argument("--limit", type=int, default=25)
    products_parser.add_argument("--out")

    crossref_parser = sub.add_parser("crossref")
    crossref_parser.add_argument("--code", type=int, required=True)
    crossref_parser.add_argument("--limit", type=int, default=100)
    crossref_parser.add_argument("--out")

    matrix_parser = sub.add_parser("matrix")
    matrix_parser.add_argument("--code", type=int, required=True)
    matrix_parser.add_argument("--limit", type=int, default=100)
    matrix_parser.add_argument("--rebuild", action="store_true")
    matrix_parser.add_argument("--out")

    contract_parser = sub.add_parser("contract")
    contract_parser.add_argument("--code", type=int, required=True)
    contract_parser.add_argument("--max-chars", type=int, default=60000)
    contract_parser.add_argument("--out")

    codes_parser = sub.add_parser("product-codes")
    codes_parser.add_argument("--limit", type=int, default=50)
    codes_parser.add_argument("--gtin")
    codes_parser.add_argument("--esha-code")
    codes_parser.add_argument("--collision-status")
    codes_parser.add_argument("--query")
    codes_parser.add_argument("--out")

    collisions_parser = sub.add_parser("collisions")
    collisions_parser.add_argument("--limit", type=int, default=50)
    collisions_parser.add_argument("--esha-code")
    collisions_parser.add_argument("--out")

    trace_parser = sub.add_parser("trace")
    trace_parser.add_argument("--kind", required=True, choices=("canonical", "normalized_item", "esha_code", "gtin", "pack", "contract"))
    trace_parser.add_argument("--key", required=True)
    trace_parser.add_argument("--limit", type=int, default=50)
    trace_parser.add_argument("--out")

    stage_parser = sub.add_parser("stage-patch")
    stage_parser.add_argument("--bundle", required=True)
    stage_parser.add_argument("--out")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "queue":
        priorities = set(args.priority) if args.priority else None
        result = queue_next(args.limit, priorities, args.issue_class, args.status)
    elif args.command == "cards":
        result = all_cards(args.limit, args.offset, args.family)
    elif args.command == "card":
        result = get_card(args.code, args.max_chars)
    elif args.command == "packet":
        if args.code is not None:
            result = packet_for_code(
                args.code,
                max_card_chars=args.max_card_chars,
                crossref_limit=args.crossref_limit,
                product_limit=args.product_limit,
            )
        elif args.item:
            result = surface_packet(
                args.item,
                max_card_chars=args.max_card_chars,
                crossref_limit=args.crossref_limit,
                product_limit=args.product_limit,
            )
        else:
            raise SystemExit("packet requires --item or --code")
    elif args.command == "search-products":
        result = search_products(args.query, args.limit, args.category)
    elif args.command == "crossref":
        result = cross_reference(args.code, args.limit)
    elif args.command == "matrix":
        result = matrix_slice(args.code, args.limit, args.rebuild)
    elif args.command == "contract":
        result = contract_sources(args.code, args.max_chars)
    elif args.command == "product-codes":
        result = product_codes(
            limit=args.limit,
            gtin=args.gtin,
            esha_code=args.esha_code,
            collision_status=args.collision_status,
            q=args.query,
        )
    elif args.command == "collisions":
        result = product_collisions(limit=args.limit, esha_code=args.esha_code)
    elif args.command == "trace":
        result = trace_entity(args.kind, args.key, args.limit)
    elif args.command == "stage-patch":
        result = stage_patch(args.bundle)
    else:
        raise SystemExit(f"unknown command: {args.command}")
    dump_json(result, getattr(args, "out", None))


if __name__ == "__main__":
    main()
