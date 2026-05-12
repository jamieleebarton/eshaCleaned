#!/usr/bin/env python3
"""Promote high-confidence Walmart/Kroger API cache offers into the priced DB.

This is a targeted repair layer for products that are present in the local
store API cache but were dropped or mis-tree-tagged by the older priced catalog
ingestion.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from htc_tree_core_v1 import htc_from_tree_identity  # noqa: E402

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
PRICED = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
HESTIA_CACHE = Path("/Users/jamiebarton/Desktop/Hestia/api/data/api_cache.db")


TARGETS = [
    {
        "source": "walmart",
        "cache_source": "walmart_search",
        "upc": "078742148281",
        "item_id": "100966386",
        "grams": 900.0,
        "size": "18 Large",
        "pid": "Eggs",
        "canonical": "Dairy > Eggs",
        "modifier": "",
    },
    {
        "source": "walmart",
        "cache_source": "walmart_search",
        "upc": "078742127088",
        "item_id": "172844767",
        "grams": 900.0,
        "size": "18 Large",
        "pid": "Eggs",
        "canonical": "Dairy > Eggs",
        "modifier": "",
    },
    {
        "source": "walmart",
        "cache_source": "walmart_search",
        "upc": "606105032917",
        "item_id": "",
        "grams": 907.184,
        "size": "2 lb Bag",
        "pid": "Tomatoes",
        "canonical": "Produce > Vegetables > Tomatoes",
        "modifier": "",
    },
]

TREE_UPDATES = [
    ("kroger", "0001111078866", "Ghee", "Pantry > Oil > Ghee", ""),
    ("kroger", "0001111003698", "Ghee", "Pantry > Oil > Ghee", ""),
    ("kroger", "0086155500011", "Ghee", "Pantry > Oil > Ghee", ""),
    ("kroger", "0086155500012", "Ghee", "Pantry > Oil > Ghee", ""),
    ("kroger", "0001111002369", "Spice Blend", "Pantry > Spices & Seasonings > Spice Blend", "Cardamom"),
    ("walmart", "606105032917", "Tomatoes", "Produce > Vegetables > Tomatoes", ""),
]


def normalize_upc(value: object) -> str:
    return str(value or "").strip()


def upc_forms(upc: str) -> tuple[str, ...]:
    stripped = upc.lstrip("0")
    if stripped and stripped != upc:
        return (upc, stripped)
    return (upc,)


def tree_htc(pid: str, canonical: str, modifier: str) -> tuple[str, str, float]:
    h = htc_from_tree_identity(canonical, pid, modifier, confidence=0.95, source="api_cache_tree")
    return h.code, h.group, h.confidence


def find_cache_item(con: sqlite3.Connection, cache_source: str, upc: str, item_id: str) -> dict[str, object]:
    needles = [n for n in (upc, upc.lstrip("0"), item_id) if n]
    for needle in needles:
        for (raw,) in con.execute(
            "SELECT raw_json FROM api_cache WHERE source=? AND raw_json LIKE ?",
            (cache_source, f"%{needle}%"),
        ):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, list):
                continue
            for item in data:
                item_upc = normalize_upc(item.get("upc"))
                item_id_value = str(item.get("itemId") or "")
                if needle in {item_upc, item_upc.lstrip("0"), item_id_value}:
                    return item
    raise RuntimeError(f"cache item not found for {cache_source} upc={upc} item_id={item_id}")


def walmart_available(item: dict[str, object]) -> tuple[int, str]:
    stock = str(item.get("stock") or "")
    available_online = item.get("availableOnline")
    available = int(stock == "Available" and available_online is not False)
    return available, stock or ("Available" if available else "Not available")


def upsert_target(cur: sqlite3.Cursor, item: dict[str, object], target: dict[str, object]) -> str:
    source = str(target["source"])
    upc = str(target["upc"])
    pid = str(target["pid"])
    canonical = str(target["canonical"])
    modifier = str(target["modifier"])
    grams = float(target["grams"])
    sale = item.get("salePrice") or item.get("msrp") or item.get("price_cents")
    sale_value = float(sale or 0)
    cents = int(round(sale_value * 100)) if sale_value < 100 else int(sale_value)
    if cents <= 0:
        raise RuntimeError(f"missing price for {upc} {item.get('name')}")
    cpg = cents / grams
    name = str(item.get("name") or "")
    brand = str(item.get("brandName") or item.get("brand") or "")
    category_path = str(item.get("categoryPath") or "")
    seller = str(item.get("sellerInfo") or "Walmart.com")
    marketplace = int(bool(item.get("marketplace")))
    fulfilled_walmart = int(bool(item.get("fulfilledByWalmart")))
    available, stock = walmart_available(item)
    htc_code, htc_group, htc_conf = tree_htc(pid, canonical, modifier)

    existing = cur.execute(
        f"SELECT rowid FROM priced_products WHERE source=? AND upc IN ({','.join('?' for _ in upc_forms(upc))})",
        (source, *upc_forms(upc)),
    ).fetchall()
    values = (
        name,
        brand,
        grams,
        cents,
        cpg,
        str(target.get("size") or item.get("size") or ""),
        category_path,
        seller,
        marketplace,
        fulfilled_walmart,
        available,
        stock,
        "api_cache_fix",
        htc_code,
        htc_group,
        htc_conf,
        pid,
        canonical,
        modifier,
        "api_cache_tree",
        category_path,
        0,
    )
    if existing:
        cur.execute(
            f"""
            UPDATE priced_products SET
                name=?, brand=?, grams=?, cents=?, cpg=?, size_display=?,
                category_path=?, seller=?, marketplace=?, fulfilled_walmart=?,
                available=?, stock=?, search_term=?, htc_code=?, htc_group=?,
                htc_confidence=?, consensus_pid=?, consensus_canonical=?,
                consensus_modifier=?, bridge_status=?, category_path_walmart=?,
                non_food_path=?
            WHERE source=? AND upc IN ({','.join('?' for _ in upc_forms(upc))})
            """,
            (*values, source, *upc_forms(upc)),
        )
        return f"UPDATE {source} {upc} {name} available={available} ${cents / 100:.2f}"

    cur.execute(
        """
        INSERT INTO priced_products
        (source, upc, name, brand, grams, cents, cpg, size_display,
         category_path, seller, marketplace, fulfilled_walmart, available,
         stock, search_term, htc_code, htc_group, htc_confidence,
         consensus_pid, consensus_canonical, consensus_fndds, consensus_sr28,
         consensus_modifier, consensus_flavor, bridge_status,
         category_path_walmart, non_food_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, '', '', ?, '', ?, ?, ?)
        """,
        (
            source,
            upc,
            name,
            brand,
            grams,
            cents,
            cpg,
            str(target.get("size") or item.get("size") or ""),
            category_path,
            seller,
            marketplace,
            fulfilled_walmart,
            available,
            stock,
            "api_cache_fix",
            htc_code,
            htc_group,
            htc_conf,
            pid,
            canonical,
            modifier,
            "api_cache_tree",
            category_path,
            0,
        ),
    )
    return f"INSERT {source} {upc} {name} available={available} ${cents / 100:.2f}"


def apply_tree_update(cur: sqlite3.Cursor, source: str, upc: str, pid: str, canonical: str, modifier: str) -> int:
    htc_code, htc_group, htc_conf = tree_htc(pid, canonical, modifier)
    cur.execute(
        f"""
        UPDATE priced_products SET
            htc_code=?, htc_group=?, htc_confidence=?,
            consensus_pid=?, consensus_canonical=?, consensus_modifier=?,
            bridge_status='api_cache_tree', non_food_path=0
        WHERE source=? AND upc IN ({','.join('?' for _ in upc_forms(upc))})
        """,
        (htc_code, htc_group, htc_conf, pid, canonical, modifier, source, *upc_forms(upc)),
    )
    return cur.rowcount


def main() -> int:
    cache = sqlite3.connect(str(HESTIA_CACHE))
    priced = sqlite3.connect(str(PRICED))
    cur = priced.cursor()

    for target in TARGETS:
        item = find_cache_item(
            cache,
            str(target["cache_source"]),
            str(target["upc"]),
            str(target.get("item_id") or ""),
        )
        print(upsert_target(cur, item, target))

    for source, upc, pid, canonical, modifier in TREE_UPDATES:
        count = apply_tree_update(cur, source, upc, pid, canonical, modifier)
        print(f"TREE {source} {upc} -> {canonical} / {pid} rows={count}")

    priced.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
