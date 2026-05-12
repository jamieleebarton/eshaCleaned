#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION = ROOT / "implementation"
OUT_DIR = IMPLEMENTATION / "output" / "sparse_cascade_planner"
CLEAN_ROOT = ROOT.parent / "clean"

DEFAULT_OUT = OUT_DIR / "source_inventory.json"

RECIPE_QA_DB = ROOT / "data" / "recipe_qa.db"
LOCAL_RECIPE_FUNNEL_DB = IMPLEMENTATION / "output" / "recipe_funnel.db"
CLEAN_RECIPE_FUNNEL_DB = CLEAN_ROOT / "implementation" / "output" / "recipe_funnel.db"

PRICED_PRODUCTS_DB = ROOT / "recipe_pricing" / "data" / "priced_products_tagged.db"
LOCAL_API_CACHE_CSV = ROOT / "recipe_pricing" / "data" / "api_cache_products.csv"
CLEAN_API_CACHE_CSV = CLEAN_ROOT / "recipe_pricing" / "data" / "api_cache_products.csv"

CONSENSUS_CSV = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
FNDDS_DIR = ROOT / "data" / "fndds"
MASTER_PRODUCTS_DB = ROOT / "data" / "master_products.db"

LOCAL_RETAIL_BRIDGE_CSV = IMPLEMENTATION / "output" / "retail_canonical_surface_bridge.csv"
TMP_RETAIL_BRIDGE_CSV = Path("/tmp/hestia_native_artifacts/retail_canonical_surface_bridge.csv")

LOCAL_HESTIA_RECIPES_CSV = IMPLEMENTATION / "output" / "hestia_recipes_calculator_native.csv"
LOCAL_PACKAGE_DB = IMPLEMENTATION / "output" / "food_packages_calculator_native.db"
LOCAL_INGREDIENT_META_JSON = IMPLEMENTATION / "output" / "hestia_calculator_native_ingredient_meta.json"


def path_info(path: Path) -> dict[str, Any]:
    exists = path.exists()
    return {
        "path": str(path),
        "exists": exists,
        "bytes": path.stat().st_size if exists and path.is_file() else 0,
    }


def sqlite_tables(path: Path) -> list[str]:
    if not path.exists():
        return []
    with sqlite3.connect(str(path)) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [str(row[0]) for row in rows]


def sqlite_table_info(path: Path, table: str) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    with sqlite3.connect(str(path)) as conn:
        cols = [
            {
                "cid": int(row[0]),
                "name": row[1],
                "type": row[2],
                "notnull": int(row[3]),
                "default": row[4],
                "pk": int(row[5]),
            }
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        if not cols:
            return {"exists": False, "columns": []}
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return {"exists": True, "row_count": int(count), "columns": cols}


def recipe_qa_inventory(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"file": path_info(path), "tables": sqlite_tables(path)}
    if not path.exists():
        return out
    for table in ("recipe_cleaned", "recipe_item_overrides", "recipe_verdicts"):
        out[table] = sqlite_table_info(path, table)
    with sqlite3.connect(str(path)) as conn:
        if "recipe_cleaned" in out["tables"]:
            out["recipe_cleaned_nonempty_ingredients"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM recipe_cleaned WHERE COALESCE(ingredients_json, '') <> ''"
                ).fetchone()[0]
            )
        if "recipe_item_overrides" in out["tables"]:
            out["recipe_item_overrides_sources"] = dict(
                conn.execute(
                    "SELECT source, COUNT(*) FROM recipe_item_overrides GROUP BY source ORDER BY COUNT(*) DESC"
                ).fetchall()
            )
    return out


def priced_products_inventory(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"file": path_info(path), "tables": sqlite_tables(path)}
    if not path.exists() or "priced_products_tagged" not in out["tables"]:
        return out
    out["priced_products_tagged"] = sqlite_table_info(path, "priced_products_tagged")
    with sqlite3.connect(str(path)) as conn:
        out["by_source"] = [
            {
                "source": row[0],
                "rows": int(row[1]),
                "non_food_drop": int(row[2] or 0),
                "distinct_canonical": int(row[3]),
                "distinct_fndds_code": int(row[4]),
                "distinct_sr28_fdc_id": int(row[5]),
            }
            for row in conn.execute(
                """
                SELECT source,
                       COUNT(*),
                       SUM(CASE WHEN non_food_drop THEN 1 ELSE 0 END),
                       COUNT(DISTINCT canonical),
                       COUNT(DISTINCT fndds_code),
                       COUNT(DISTINCT sr28_fdc_id)
                FROM priced_products_tagged
                GROUP BY source
                ORDER BY source
                """
            ).fetchall()
        ]
        out["top_canonicals"] = [
            {"canonical": row[0], "rows": int(row[1]), "kept_rows": int(row[2] or 0)}
            for row in conn.execute(
                """
                SELECT canonical,
                       COUNT(*),
                       SUM(CASE WHEN non_food_drop = 0 THEN 1 ELSE 0 END)
                FROM priced_products_tagged
                GROUP BY canonical
                ORDER BY COUNT(*) DESC
                LIMIT 25
                """
            ).fetchall()
        ]
    return out


def csv_header_and_count(path: Path, sample_limit: int = 0) -> dict[str, Any]:
    out: dict[str, Any] = {"file": path_info(path), "fieldnames": [], "row_count": 0}
    if not path.exists():
        return out
    samples: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        out["fieldnames"] = list(reader.fieldnames or [])
        for row in reader:
            out["row_count"] += 1
            if sample_limit and len(samples) < sample_limit:
                samples.append(dict(row))
    if sample_limit:
        out["samples"] = samples
    return out


def api_cache_inventory(local_path: Path, clean_path: Path) -> dict[str, Any]:
    chosen = local_path if local_path.exists() else clean_path
    out = {
        "local": path_info(local_path),
        "clean_fallback": path_info(clean_path),
        "chosen": str(chosen) if chosen.exists() else "",
        "fieldnames": [],
        "row_count": 0,
        "source_counts": {},
    }
    if not chosen.exists():
        return out
    source_counts: Counter[str] = Counter()
    with chosen.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        out["fieldnames"] = list(reader.fieldnames or [])
        for row in reader:
            out["row_count"] += 1
            source_counts[(row.get("source") or "").strip()] += 1
    out["source_counts"] = dict(source_counts)
    return out


def consensus_inventory(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "file": path_info(path),
        "fieldnames": [],
        "row_count": 0,
        "assigned_esha_rows": 0,
        "distinct_fdc_id": 0,
        "distinct_esha_code": 0,
        "distinct_fndds_code": 0,
        "match_sources": {},
        "known_bad_examples": [],
    }
    if not path.exists():
        return out
    fdc_ids: set[str] = set()
    esha_codes: set[str] = set()
    fndds_codes: set[str] = set()
    match_sources: Counter[str] = Counter()
    bad_examples: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        out["fieldnames"] = list(reader.fieldnames or [])
        for row in reader:
            out["row_count"] += 1
            fdc_id = (row.get("fdc_id") or "").strip()
            esha_code = (row.get("esha_code") or "").strip()
            fndds_code = (row.get("fndds_code") or "").strip()
            if fdc_id:
                fdc_ids.add(fdc_id)
            if esha_code:
                esha_codes.add(esha_code)
                out["assigned_esha_rows"] += 1
            if fndds_code:
                fndds_codes.add(fndds_code)
            match_sources[(row.get("match_source") or "").strip()] += 1
            title = (row.get("title") or "").upper()
            fndds_desc = (row.get("fndds_desc") or "").lower()
            if "MUFFIN" in title and "mix" in fndds_desc and len(bad_examples) < 5:
                bad_examples.append(
                    {
                        "fdc_id": row.get("fdc_id", ""),
                        "title": row.get("title", ""),
                        "fndds_code": row.get("fndds_code", ""),
                        "fndds_desc": row.get("fndds_desc", ""),
                        "esha_code": row.get("esha_code", ""),
                        "esha_desc": row.get("esha_desc", ""),
                        "match_source": row.get("match_source", ""),
                        "matched_key": row.get("matched_key", ""),
                        "consensus_reason": row.get("consensus_reason", ""),
                    }
                )
    out["distinct_fdc_id"] = len(fdc_ids)
    out["distinct_esha_code"] = len(esha_codes)
    out["distinct_fndds_code"] = len(fndds_codes)
    out["match_sources"] = dict(match_sources.most_common(25))
    out["known_bad_examples"] = bad_examples
    return out


def fndds_inventory(path: Path) -> dict[str, Any]:
    files = {
        "main_food_desc": path / "MainFoodDesc16.csv",
        "ingredient_links": path / "FNDDSIngred.csv",
        "sr_links": path / "FNDDSSRLinks.csv",
        "nutrient_lookup": path / "fndds_nutrient_lookup.csv",
        "portion_weights_db": path / "food_portion_weights.db",
    }
    out: dict[str, Any] = {"dir": path_info(path), "files": {}}
    for name, file_path in files.items():
        if file_path.suffix == ".db":
            out["files"][name] = {"file": path_info(file_path), "tables": sqlite_tables(file_path)}
        else:
            out["files"][name] = csv_header_and_count(file_path)
    return out


def master_products_inventory(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"file": path_info(path), "tables": sqlite_tables(path)}
    if not path.exists():
        return out
    for table in ("products", "product_fndds_tag", "product_code_tags"):
        out[table] = sqlite_table_info(path, table)
    return out


def retail_bridge_inventory() -> dict[str, Any]:
    return {
        "local": path_info(LOCAL_RETAIL_BRIDGE_CSV),
        "tmp": path_info(TMP_RETAIL_BRIDGE_CSV),
        "chosen": str(LOCAL_RETAIL_BRIDGE_CSV if LOCAL_RETAIL_BRIDGE_CSV.exists() else TMP_RETAIL_BRIDGE_CSV),
    }


def generated_artifacts_inventory() -> dict[str, Any]:
    return {
        "recipe_funnel_local": path_info(LOCAL_RECIPE_FUNNEL_DB),
        "recipe_funnel_clean_fallback": path_info(CLEAN_RECIPE_FUNNEL_DB),
        "hestia_recipes_calculator_native": path_info(LOCAL_HESTIA_RECIPES_CSV),
        "food_packages_calculator_native": path_info(LOCAL_PACKAGE_DB),
        "ingredient_meta": path_info(LOCAL_INGREDIENT_META_JSON),
    }


def build_inventory() -> dict[str, Any]:
    return {
        "root": str(ROOT),
        "recipe_qa": recipe_qa_inventory(RECIPE_QA_DB),
        "recipe_funnel": {
            "local": path_info(LOCAL_RECIPE_FUNNEL_DB),
            "clean_fallback": path_info(CLEAN_RECIPE_FUNNEL_DB),
        },
        "priced_products": priced_products_inventory(PRICED_PRODUCTS_DB),
        "api_cache": api_cache_inventory(LOCAL_API_CACHE_CSV, CLEAN_API_CACHE_CSV),
        "retail_bridge": retail_bridge_inventory(),
        "consensus": consensus_inventory(CONSENSUS_CSV),
        "fndds": fndds_inventory(FNDDS_DIR),
        "master_products": master_products_inventory(MASTER_PRODUCTS_DB),
        "generated_artifacts": generated_artifacts_inventory(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory sparse cascade planner input artifacts.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = build_inventory()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "sections": sorted(inventory)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
