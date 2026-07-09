#!/usr/bin/env python3
"""Indexed HTC evidence workbench.

This module is deliberately not an adjudicator. It builds and queries a compact
retrieval workbench so an agent can reason over candidate families and witnesses
without scanning 20k+ HTC concepts or receiving giant raw CSV dumps.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRODUCTS = ROOT / "recipe_mapper" / "v1" / "output" / "htc_coded_store_products_v1.csv"
DEFAULT_CONSENSUS = ROOT / "recipe_mapper" / "v1" / "output" / "consensus_htc_tagged.csv"
DEFAULT_RECIPES = ROOT / "data" / "recipes_unified_normalized.csv"
DEFAULT_DB = ROOT / "output" / "htc_workbench" / "workbench.sqlite"

TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "best", "brand", "by", "com", "ct", "fl",
    "food", "foods", "for", "from", "great", "home", "in", "of", "or", "oz", "pack",
    "page", "the", "to", "value", "w", "with",
}


def clean_code(value: Any) -> str:
    return str(value or "").strip().lstrip("~")


def norm_text(value: Any) -> str:
    return str(value or "").lower().replace("&", " and ").replace("/", " ").replace(">", " ")


def tokens(value: Any) -> set[str]:
    out: set[str] = set()
    for token in TOKEN_RE.findall(norm_text(value)):
        if len(token) < 2 or token in STOPWORDS:
            continue
        out.add(token)
        if token.endswith("ies") and len(token) > 4:
            out.add(token[:-3] + "y")
        elif token.endswith("s") and len(token) > 3:
            out.add(token[:-1])
    return out


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def insert_csv_stream(
    con: sqlite3.Connection,
    table_name: str,
    path: Path,
    *,
    limit: int | None = None,
    row_hook: Any = None,
) -> tuple[list[str], int]:
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        create_text_table(con, table_name, columns)
        placeholders = ", ".join("?" for _ in columns)
        col_sql = ", ".join(quote_ident(col) for col in columns)
        sql = f"INSERT INTO {quote_ident(table_name)} ({col_sql}) VALUES ({placeholders})"
        batch = []
        count = 0
        for row in reader:
            if row_hook is not None:
                row_hook(row)
            batch.append([row.get(col, "") for col in columns])
            count += 1
            if len(batch) >= 10000:
                con.executemany(sql, batch)
                batch.clear()
            if limit is not None and count >= limit:
                break
        if batch:
            con.executemany(sql, batch)
    return columns, count


def create_text_table(con: sqlite3.Connection, name: str, columns: list[str]) -> None:
    con.execute(f"DROP TABLE IF EXISTS {quote_ident(name)}")
    ddl = ", ".join(f"{quote_ident(col)} TEXT" for col in columns)
    con.execute(f"CREATE TABLE {quote_ident(name)} ({ddl})")


def insert_rows(con: sqlite3.Connection, name: str, columns: list[str], rows: Iterable[dict[str, str]]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    col_sql = ", ".join(quote_ident(col) for col in columns)
    sql = f"INSERT INTO {quote_ident(name)} ({col_sql}) VALUES ({placeholders})"
    batch = []
    for row in rows:
        batch.append([row.get(col, "") for col in columns])
        if len(batch) >= 5000:
            con.executemany(sql, batch)
            batch.clear()
    if batch:
        con.executemany(sql, batch)


def try_create_fts(con: sqlite3.Connection, fts_name: str, source_table: str, columns: list[str]) -> None:
    try:
        con.execute(f"DROP TABLE IF EXISTS {quote_ident(fts_name)}")
        cols = ", ".join(quote_ident(col) for col in columns)
        con.execute(f"CREATE VIRTUAL TABLE {quote_ident(fts_name)} USING fts5({cols})")
        con.execute(
            f"INSERT INTO {quote_ident(fts_name)} ({cols}) "
            f"SELECT {cols} FROM {quote_ident(source_table)}"
        )
    except sqlite3.DatabaseError:
        # Some SQLite builds omit FTS5. Plain tables still work.
        pass


def build_full_code_summary(consensus_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "full_code_counts": Counter(),
        "leaf_counts": Counter(),
        "modifier_counts": Counter(),
        "title_samples": [],
        "path_counts": Counter(),
    })
    for row in consensus_rows:
        code = clean_code(row.get("htc_code"))
        if not code:
            continue
        group = grouped[code]
        full = str(row.get("htc_full_code") or "")
        leaf = str(row.get("retail_leaf_path") or "")
        mod = str(row.get("modifier") or "")
        path = str(row.get("canonical_path") or "")
        title = str(row.get("title") or "")
        if full:
            group["full_code_counts"][full] += 1
        if leaf:
            group["leaf_counts"][leaf] += 1
        if mod:
            group["modifier_counts"][mod] += 1
        if path:
            group["path_counts"][path] += 1
        if title and len(group["title_samples"]) < 8:
            group["title_samples"].append(title)

    out = []
    for code, data in grouped.items():
        out.append({
            "htc_code": code,
            "row_count": str(sum(data["leaf_counts"].values()) or sum(data["full_code_counts"].values())),
            "modal_canonical_path": data["path_counts"].most_common(1)[0][0] if data["path_counts"] else "",
            "top_full_codes_json": json.dumps(data["full_code_counts"].most_common(12)),
            "top_leaf_paths_json": json.dumps(data["leaf_counts"].most_common(12)),
            "top_modifiers_json": json.dumps(data["modifier_counts"].most_common(12)),
            "title_samples_json": json.dumps(data["title_samples"]),
        })
    return out


def new_summary_group() -> dict[str, Any]:
    return {
        "full_code_counts": Counter(),
        "leaf_counts": Counter(),
        "modifier_counts": Counter(),
        "title_samples": [],
        "path_counts": Counter(),
    }


def add_summary_row(grouped: dict[str, dict[str, Any]], row: dict[str, str]) -> None:
    code = clean_code(row.get("htc_code"))
    if not code:
        return
    group = grouped.setdefault(code, new_summary_group())
    full = str(row.get("htc_full_code") or "")
    leaf = str(row.get("retail_leaf_path") or "")
    mod = str(row.get("modifier") or "")
    path = str(row.get("canonical_path") or "")
    title = str(row.get("title") or "")
    if full:
        group["full_code_counts"][full] += 1
    if leaf:
        group["leaf_counts"][leaf] += 1
    if mod:
        group["modifier_counts"][mod] += 1
    if path:
        group["path_counts"][path] += 1
    if title and len(group["title_samples"]) < 8:
        group["title_samples"].append(title)


def summary_groups_to_rows(grouped: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    out = []
    for code, data in grouped.items():
        out.append({
            "htc_code": code,
            "row_count": str(sum(data["leaf_counts"].values()) or sum(data["full_code_counts"].values())),
            "modal_canonical_path": data["path_counts"].most_common(1)[0][0] if data["path_counts"] else "",
            "top_full_codes_json": json.dumps(data["full_code_counts"].most_common(12)),
            "top_leaf_paths_json": json.dumps(data["leaf_counts"].most_common(12)),
            "top_modifiers_json": json.dumps(data["modifier_counts"].most_common(12)),
            "title_samples_json": json.dumps(data["title_samples"]),
        })
    return out


def build_index(
    db_path: Path = DEFAULT_DB,
    products_path: Path = DEFAULT_PRODUCTS,
    consensus_path: Path = DEFAULT_CONSENSUS,
    recipes_path: Path = DEFAULT_RECIPES,
    *,
    enable_fts: bool = True,
    recipe_limit: int | None = None,
) -> dict[str, Any]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    wal_path = db_path.with_suffix(db_path.suffix + "-wal")
    shm_path = db_path.with_suffix(db_path.suffix + "-shm")
    for sidecar in [wal_path, shm_path]:
        if sidecar.exists():
            sidecar.unlink()
    started = time.time()
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA temp_store=MEMORY")

        products_cols, product_count = insert_csv_stream(con, "products", products_path)

        summary_groups: dict[str, dict[str, Any]] = {}
        consensus_cols, consensus_count = insert_csv_stream(
            con,
            "consensus",
            consensus_path,
            row_hook=lambda row: add_summary_row(summary_groups, row),
        )
        recipe_cols: list[str] = []
        recipe_count = 0
        if recipes_path.exists():
            recipe_cols, recipe_count = insert_csv_stream(con, "recipes", recipes_path, limit=recipe_limit)

        summary_cols = [
            "htc_code", "row_count", "modal_canonical_path", "top_full_codes_json",
            "top_leaf_paths_json", "top_modifiers_json", "title_samples_json",
        ]
        create_text_table(con, "full_code_summary", summary_cols)
        insert_rows(con, "full_code_summary", summary_cols, summary_groups_to_rows(summary_groups))

        con.execute("CREATE INDEX IF NOT EXISTS idx_products_rowid ON products(rowid)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_products_upc ON products(upc)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_products_htc ON products(htc_code)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_consensus_htc ON consensus(htc_code)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_consensus_full ON consensus(htc_full_code)")
        if recipe_cols and "htc_code" in recipe_cols:
            con.execute("CREATE INDEX IF NOT EXISTS idx_recipes_htc ON recipes(htc_code)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_full_code_summary_htc ON full_code_summary(htc_code)")

        if enable_fts:
            try_create_fts(con, "products_fts", "products", [
                col for col in ["name", "brand", "search_term", "category_path", "category_path_walmart", "tree_product_identity", "tree_modifier"]
                if col in products_cols
            ])
            try_create_fts(con, "consensus_fts", "consensus", [
                col for col in ["title", "branded_food_category", "product_identity_fixed", "canonical_path", "retail_leaf_path", "modifier"]
                if col in consensus_cols
            ])
            if recipe_cols:
                try_create_fts(con, "recipes_fts", "recipes", [
                    col for col in [
                        "recipe_id", "recipe_title", "ingredient_item", "display", "htc_code",
                        "normalized_canonical_text", "normalized_identity_phrase",
                        "normalized_user_claims", "normalized_form_facets",
                        "normalized_processing_facets",
                    ]
                    if col in recipe_cols
                ])

        meta = {
            "schema_version": 1,
            "built_at": time.time(),
            "products_path": str(products_path),
            "consensus_path": str(consensus_path),
            "recipes_path": str(recipes_path),
            "product_rows": product_count,
            "consensus_rows": consensus_count,
            "recipe_rows": recipe_count,
            "recipe_limit": recipe_limit,
            "fts_enabled": enable_fts,
        }
        con.execute("DROP TABLE IF EXISTS metadata")
        con.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)")
        con.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", [(k, json.dumps(v)) for k, v in meta.items()])
        con.commit()
        meta["elapsed_seconds"] = round(time.time() - started, 3)
        meta["db_path"] = str(db_path)
        return meta
    finally:
        con.close()


def row_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def product_by_key(con: sqlite3.Connection, *, rowid: str = "", upc: str = "") -> dict[str, Any]:
    con.row_factory = sqlite3.Row
    if rowid:
        row = con.execute("SELECT * FROM products WHERE rowid = ? LIMIT 1", (rowid,)).fetchone()
        return row_dict(row)
    if upc:
        row = con.execute("SELECT * FROM products WHERE upc = ? LIMIT 1", (upc,)).fetchone()
        return row_dict(row)
    raise ValueError("rowid or upc is required")


def observed_facets(product: dict[str, Any]) -> dict[str, list[str]]:
    text = " ".join(str(product.get(k) or "") for k in [
        "name", "brand", "search_term", "category_path", "category_path_walmart",
        "tree_product_identity", "tree_canonical_path", "tree_modifier",
    ]).lower()
    buckets = {
        "audience": ["baby", "infant", "toddler", "kids", "children"],
        "claims": ["organic", "whole grain", "gluten free", "non gmo", "no sugar", "no added sugar", "low sodium"],
        "form": ["cereal", "hot cereal", "oatmeal", "rolled", "instant", "powder", "mix", "drink", "juice", "cocktail", "concentrate"],
        "flavor": ["apple", "cranberry", "raspberry", "orange", "vanilla", "chocolate", "strawberry"],
    }
    return {name: [term for term in terms if term in text] for name, terms in buckets.items() if any(term in text for term in terms)}


def compact_product(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "source", "rowid", "upc", "name", "brand", "size_display", "category_path",
        "category_path_walmart", "search_term", "raw_htc_code", "tree_authority",
        "taxonomy_status", "tree_product_identity", "tree_canonical_path",
        "tree_modifier", "htc_code", "htc_confidence", "htc_source", "non_food_path",
    ]
    return {key: row.get(key, "") for key in keys}


def token_score(query_terms: set[str], text: str) -> tuple[float, list[str]]:
    terms = tokens(text)
    if not query_terms or not terms:
        return 0.0, []
    hits = sorted(query_terms & terms)
    return len(hits) / len(query_terms | terms), hits


def fetch_same_upc(con: sqlite3.Connection, upc: str, *, limit: int = 25) -> list[dict[str, Any]]:
    if not upc:
        return []
    rows = con.execute("SELECT * FROM products WHERE upc = ? LIMIT ?", (upc, limit)).fetchall()
    return [compact_product(dict(row)) for row in rows]


def search_recipe_use(con: sqlite3.Connection, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    qterms = tokens(query)
    if not qterms:
        return []
    has_recipes = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'recipes'"
    ).fetchone()
    if not has_recipes:
        return []
    has_fts = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'recipes_fts'"
    ).fetchone()
    if has_fts:
        match = " OR ".join(f'"{term}"' for term in sorted(qterms))
        rows = con.execute(
            "SELECT * FROM recipes_fts WHERE recipes_fts MATCH ? "
            "ORDER BY bm25(recipes_fts) LIMIT ?",
            (match, limit * 5),
        ).fetchall()
        scored = []
        for row in rows:
            d = dict(row)
            text = " ".join(str(d.get(k) or "") for k in [
                "ingredient_item", "display", "normalized_canonical_text",
                "normalized_identity_phrase", "normalized_user_claims",
                "normalized_form_facets", "normalized_processing_facets",
            ])
            score, hits = token_score(qterms, text)
            if score:
                scored.append((score, {
                    "recipe_id": d.get("recipe_id", ""),
                    "recipe_title": d.get("recipe_title", ""),
                    "ingredient_item": d.get("ingredient_item", ""),
                    "display": d.get("display", ""),
                    "htc_code": d.get("htc_code", ""),
                    "normalized_canonical_text": d.get("normalized_canonical_text", ""),
                    "normalized_identity_phrase": d.get("normalized_identity_phrase", ""),
                    "normalized_user_claims": d.get("normalized_user_claims", ""),
                    "normalized_form_facets": d.get("normalized_form_facets", ""),
                    "matched_terms": hits,
                }))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [row | {"score": round(score, 6)} for score, row in scored[:limit]]

    rows = con.execute("SELECT * FROM recipes LIMIT 20000").fetchall()
    scored = []
    for row in rows:
        d = dict(row)
        text = " ".join(str(d.get(k) or "") for k in [
            "ingredient_item", "display", "normalized_canonical_text",
            "normalized_identity_phrase", "normalized_user_claims",
            "normalized_form_facets", "normalized_processing_facets",
        ])
        score, hits = token_score(qterms, text)
        if score:
            scored.append((score, {
                "recipe_id": d.get("recipe_id", ""),
                "recipe_title": d.get("recipe_title", ""),
                "ingredient_item": d.get("ingredient_item", ""),
                "display": d.get("display", ""),
                "htc_code": d.get("htc_code", ""),
                "normalized_canonical_text": d.get("normalized_canonical_text", ""),
                "normalized_identity_phrase": d.get("normalized_identity_phrase", ""),
                "normalized_user_claims": d.get("normalized_user_claims", ""),
                "normalized_form_facets": d.get("normalized_form_facets", ""),
                "matched_terms": hits,
            }))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row | {"score": round(score, 6)} for score, row in scored[:limit]]


def search_consensus_direct(con: sqlite3.Connection, query: str, *, limit: int = 16) -> list[dict[str, Any]]:
    qterms = tokens(query)
    if not qterms:
        return []
    rows = con.execute("SELECT * FROM consensus").fetchall()
    scored = []
    core_terms = {"baby", "infant", "oatmeal", "cereal"}
    for row in rows:
        d = dict(row)
        text = " ".join(str(d.get(k) or "") for k in [
            "title", "branded_food_category", "product_identity_fixed",
            "canonical_path", "retail_leaf_path", "modifier",
        ])
        score, hits = token_score(qterms, text)
        if not score:
            continue
        lower = text.lower()
        core_hits = sorted(term for term in core_terms if term in lower and term in qterms)
        if core_hits:
            score += 0.12 * len(core_hits)
        if "baby" in qterms or "infant" in qterms:
            if any(term in lower for term in ["baby", "infant", "toddler"]):
                score += 0.35
            else:
                score -= 0.15
        scored.append((score, {
            "fdc_id": d.get("fdc_id", ""),
            "title": d.get("title", ""),
            "branded_food_category": d.get("branded_food_category", ""),
            "product_identity_fixed": d.get("product_identity_fixed", ""),
            "canonical_path": d.get("canonical_path", ""),
            "retail_leaf_path": d.get("retail_leaf_path", ""),
            "modifier": d.get("modifier", ""),
            "htc_code": d.get("htc_code", ""),
            "htc_full_code": d.get("htc_full_code", ""),
            "matched_terms": hits,
            "core_hits": core_hits,
        }))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row | {"score": round(score, 6)} for score, row in scored[:limit]]


def code_neighbor_fit(con: sqlite3.Connection, product: dict[str, Any], codes: list[str], *, limit_examples: int = 8) -> list[dict[str, Any]]:
    product_text = " ".join(str(product.get(k) or "") for k in [
        "name", "brand", "search_term", "category_path", "category_path_walmart",
        "tree_product_identity", "tree_canonical_path", "tree_modifier",
    ])
    product_terms = tokens(product_text)
    out = []
    seen = set()
    for raw_code in codes:
        code = clean_code(raw_code)
        if not code or code in seen:
            continue
        seen.add(code)
        rows = con.execute(
            "SELECT title, branded_food_category, product_identity_fixed, canonical_path, retail_leaf_path, "
            "modifier, htc_code, htc_full_code FROM consensus WHERE htc_code IN (?, ?) LIMIT ?",
            (code, "~" + code, limit_examples),
        ).fetchall()
        examples = [dict(row) for row in rows]
        neighbor_text = " ".join(
            " ".join(str(example.get(k) or "") for k in [
                "title", "branded_food_category", "product_identity_fixed", "canonical_path", "retail_leaf_path", "modifier",
            ])
            for example in examples
        )
        neighbor_terms = tokens(neighbor_text)
        shared = sorted(product_terms & neighbor_terms)
        product_only = sorted(product_terms - neighbor_terms)
        neighbor_only = sorted(neighbor_terms - product_terms)
        fit = (len(shared) / len(product_terms | neighbor_terms)) if product_terms and neighbor_terms else 0.0
        out.append({
            "htc_code": code,
            "fit_score": round(fit, 6),
            "shared_terms": shared[:16],
            "product_terms_not_seen_in_neighbors": product_only[:16],
            "neighbor_terms_not_seen_in_product": neighbor_only[:16],
            "question": "Is this product like the other products already living in this HTC code?",
            "examples": examples[:limit_examples],
            "risk": "outlier_candidate" if fit < 0.12 else "similar_neighbors",
        })
    out.sort(key=lambda row: row["fit_score"], reverse=True)
    return out


def family_id_from_path(path: str, code: str) -> str:
    parts = [re.sub(r"[^a-z0-9]+", "_", p.lower()).strip("_") for p in str(path or "").split(">") if p.strip()]
    core = "_".join(parts[:3]) if parts else clean_code(code)[:2]
    return core or "unknown"


def candidate_families(con: sqlite3.Connection, product: dict[str, Any], *, family_limit: int = 12) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    query = " ".join(str(product.get(k) or "") for k in [
        "name", "search_term", "tree_product_identity", "tree_canonical_path", "tree_modifier", "category_path", "category_path_walmart",
    ])
    qterms = tokens(query)
    facets = observed_facets(product)
    current_code = clean_code(product.get("htc_code") or product.get("raw_htc_code"))
    summary_rows = con.execute("SELECT * FROM full_code_summary").fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in summary_rows:
        d = dict(row)
        path_text = " ".join([
            d.get("modal_canonical_path", ""),
            d.get("top_leaf_paths_json", ""),
        ])
        text = " ".join([
            path_text,
            d.get("top_leaf_paths_json", ""),
            d.get("top_modifiers_json", ""),
            d.get("title_samples_json", ""),
        ])
        score, hits = token_score(qterms, text)
        signals = []
        suspicious = []
        lower_path = path_text.lower()
        audience_family = any(term in lower_path for term in ["baby & toddler", "baby food", "infant"])
        if "baby" in facets.get("audience", []) and audience_family:
            score += 0.35
            signals.append("audience_facet:product says baby and family is baby/infant/toddler")
        product_form_terms = set(facets.get("form", []))
        if product_form_terms & {"cereal", "hot cereal", "oatmeal"}:
            if not any(term in lower_path for term in ["cereal", "oatmeal", "oat"]):
                score -= 0.25
                suspicious.append("family_path_lacks_product_form:cereal/oatmeal")
        if current_code and clean_code(d.get("htc_code")) == current_code:
            score += 0.20
            signals.append("current_assignment:family contains current HTC code")
        if not score:
            continue
        fid = family_id_from_path(d.get("modal_canonical_path", ""), d.get("htc_code", ""))
        group = grouped.setdefault(fid, {
            "family_id": fid,
            "best_score": 0.0,
            "base_codes_seen": [],
            "matched_terms": Counter(),
            "signals": Counter(),
            "suspicious": Counter(),
            "top_paths": Counter(),
            "top_full_codes": Counter(),
            "matching_codes": [],
            "row_count": 0,
        })
        group["best_score"] = max(group["best_score"], score)
        group["base_codes_seen"].append(d.get("htc_code", ""))
        group["row_count"] += int(d.get("row_count") or 0)
        group["matched_terms"].update(hits)
        group["signals"].update(signals)
        group["suspicious"].update(suspicious)
        row_count = int(d.get("row_count") or 0)
        group["matching_codes"].append({
            "htc_code": clean_code(d.get("htc_code")),
            "score": round(score, 6),
            "row_count": row_count,
            "matched_terms": hits[:12],
            "modal_canonical_path": d.get("modal_canonical_path", ""),
            "top_full_codes": json.loads(d.get("top_full_codes_json") or "[]")[:4],
            "top_leaf_paths": json.loads(d.get("top_leaf_paths_json") or "[]")[:4],
            "top_modifiers": json.loads(d.get("top_modifiers_json") or "[]")[:4],
            "title_samples": json.loads(d.get("title_samples_json") or "[]")[:4],
        })
        for full_code, count in json.loads(d.get("top_full_codes_json") or "[]")[:4]:
            group["top_full_codes"][full_code] += int(count)
        for path, count in json.loads(d.get("top_leaf_paths_json") or "[]")[:4]:
            group["top_paths"][path] += int(count)
    families = sorted(grouped.values(), key=lambda g: (-g["best_score"], -g["row_count"], g["family_id"]))
    dashboard_families = []
    branches = []
    for group in families[:family_limit]:
        codes = list(dict.fromkeys(group["base_codes_seen"]))[:12]
        top_paths = group["top_paths"].most_common(8)
        dashboard_families.append({
            "family_id": group["family_id"],
            "score": round(group["best_score"], 6),
            "base_codes_seen": codes,
            "row_count": group["row_count"],
            "matched_terms": [term for term, _ in group["matched_terms"].most_common(12)],
            "signals": [signal for signal, _ in group["signals"].most_common(8)],
            "top_matching_codes": sorted(
                group["matching_codes"],
                key=lambda code: (-code["score"], -code["row_count"], code["htc_code"]),
            )[:8],
            "top_full_codes": group["top_full_codes"].most_common(8),
            "top_paths": top_paths,
            "why_plausible": (
                [f"matched_terms:{','.join(term for term, _ in group['matched_terms'].most_common(6))}"]
                + [signal for signal, _ in group["signals"].most_common(4)]
            ),
            "why_suspicious": [reason for reason, _ in group["suspicious"].most_common(6)],
            "expand_tools": [
                f"expand_candidate_family:{group['family_id']}",
                f"find_contradictions:{group['family_id']}",
                f"recipe_use:evaluate {group['family_id']}",
            ],
        })
    for group in families[family_limit:]:
        branches.append({
            "family_id": group["family_id"],
            "score": round(group["best_score"], 6),
            "base_code_count": len(set(group["base_codes_seen"])),
            "expand_tool": f"expand_candidate_family:{group['family_id']}",
        })
    return dashboard_families, branches


def expand_candidate_family(
    db_path: Path = DEFAULT_DB,
    *,
    family_id: str,
    limit_codes: int = 25,
    limit_examples_per_code: int = 4,
) -> dict[str, Any]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        matches = []
        for row in con.execute("SELECT * FROM full_code_summary").fetchall():
            d = dict(row)
            if family_id_from_path(d.get("modal_canonical_path", ""), d.get("htc_code", "")) == family_id:
                matches.append(d)
        matches.sort(key=lambda row: int(row.get("row_count") or 0), reverse=True)
        codes = [clean_code(row.get("htc_code")) for row in matches[:limit_codes]]
        examples: dict[str, list[dict[str, Any]]] = {}
        for code in codes:
            rows = con.execute(
                "SELECT fdc_id, title, branded_food_category, product_identity_fixed, canonical_path, "
                "retail_leaf_path, modifier, htc_code, htc_full_code, htc_confidence, htc_source "
                "FROM consensus WHERE htc_code IN (?, ?) LIMIT ?",
                (code, "~" + code, limit_examples_per_code),
            ).fetchall()
            examples[code] = [dict(row) for row in rows]
        return {
            "tool": "expand_candidate_family",
            "family_id": family_id,
            "code_count": len(matches),
            "codes": [
                {
                    "htc_code": clean_code(row.get("htc_code")),
                    "row_count": int(row.get("row_count") or 0),
                    "modal_canonical_path": row.get("modal_canonical_path", ""),
                    "top_full_codes": json.loads(row.get("top_full_codes_json") or "[]")[:8],
                    "top_leaf_paths": json.loads(row.get("top_leaf_paths_json") or "[]")[:8],
                    "top_modifiers": json.loads(row.get("top_modifiers_json") or "[]")[:8],
                    "title_samples": json.loads(row.get("title_samples_json") or "[]")[:8],
                    "examples": examples.get(clean_code(row.get("htc_code")), []),
                }
                for row in matches[:limit_codes]
            ],
            "cursor": None if len(matches) <= limit_codes else f"{family_id}:{limit_codes}",
        }
    finally:
        con.close()


def join_risks(product: dict[str, Any], recipe_examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facets = observed_facets(product)
    risks = []
    if "baby" in facets.get("audience", []):
        ordinary = [
            row for row in recipe_examples
            if "baby" not in " ".join(str(row.get(k) or "").lower() for k in ["ingredient_item", "display", "normalized_canonical_text"])
        ][:5]
        if ordinary:
            risks.append({
                "risk": "audience_mismatch",
                "product_audience": "baby",
                "question": "Should this SKU be blocked from ordinary recipe joins unless the recipe asks for baby/infant cereal?",
                "ordinary_recipe_examples": ordinary,
            })
    return risks


def build_dashboard(db_path: Path = DEFAULT_DB, *, rowid: str = "", upc: str = "") -> dict[str, Any]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        product = product_by_key(con, rowid=rowid, upc=upc)
        if not product:
            raise SystemExit(f"product not found: rowid={rowid!r} upc={upc!r}")
        same_upc = fetch_same_upc(con, str(product.get("upc") or ""))
        recipe_query = " ".join(str(product.get(k) or "") for k in ["tree_product_identity", "tree_modifier", "search_term", "name"])
        direct_query = " ".join(str(product.get(k) or "") for k in [
            "name", "search_term", "tree_product_identity", "tree_modifier", "category_path", "category_path_walmart",
        ])
        recipe_examples = search_recipe_use(con, recipe_query)
        consensus_direct = search_consensus_direct(con, direct_query)
        families, expandable = candidate_families(con, product)
        neighbor_codes = [product.get("htc_code", ""), product.get("raw_htc_code", "")]
        neighbor_codes.extend(row.get("htc_code", "") for row in consensus_direct[:8])
        return {
            "schema_version": 1,
            "product": compact_product(product),
            "observed_facets": observed_facets(product),
            "witnesses": {
                "same_upc": same_upc,
                "consensus_direct": consensus_direct,
                "code_neighbor_fit": code_neighbor_fit(con, product, neighbor_codes),
                "recipe_use": recipe_examples,
            },
            "candidate_families": families,
            "join_risks": join_risks(product, recipe_examples),
            "expandable_branches": expandable[:50],
            "agent_instruction": (
                "Use this dashboard to choose branches to expand before proposing an HTC/full-code/facet assignment. "
                "Do not treat the dashboard ranking as truth."
            ),
        }
    finally:
        con.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--db", type=Path, default=DEFAULT_DB)
    build.add_argument("--products", type=Path, default=DEFAULT_PRODUCTS)
    build.add_argument("--consensus", type=Path, default=DEFAULT_CONSENSUS)
    build.add_argument("--recipes", type=Path, default=DEFAULT_RECIPES)
    build.add_argument("--no-fts", action="store_true", help="skip FTS creation for a fast base-table build")
    build.add_argument("--recipe-limit", type=int, default=None, help="debug/smoke-test limit for recipe rows")
    dash = sub.add_parser("dashboard")
    dash.add_argument("--db", type=Path, default=DEFAULT_DB)
    dash.add_argument("--rowid", default="")
    dash.add_argument("--upc", default="")
    expand = sub.add_parser("expand-family")
    expand.add_argument("--db", type=Path, default=DEFAULT_DB)
    expand.add_argument("--family-id", required=True)
    expand.add_argument("--limit-codes", type=int, default=25)
    expand.add_argument("--limit-examples-per-code", type=int, default=4)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "build":
        print(json.dumps(
            build_index(
                args.db,
                args.products,
                args.consensus,
                args.recipes,
                enable_fts=not args.no_fts,
                recipe_limit=args.recipe_limit,
            ),
            indent=2,
            sort_keys=True,
        ))
    elif args.command == "dashboard":
        print(json.dumps(build_dashboard(args.db, rowid=args.rowid, upc=args.upc), indent=2, sort_keys=True))
    elif args.command == "expand-family":
        print(json.dumps(
            expand_candidate_family(
                args.db,
                family_id=args.family_id,
                limit_codes=args.limit_codes,
                limit_examples_per_code=args.limit_examples_per_code,
            ),
            indent=2,
            sort_keys=True,
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
