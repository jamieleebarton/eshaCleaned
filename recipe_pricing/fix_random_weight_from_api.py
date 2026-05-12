#!/usr/bin/env python3
"""Fix random-weight (sold_by=WEIGHT) SKUs in priced_products_v2.db using
the Kroger API truth from api_cache.db.

Bug: scraper stored item_info.net_weight (the catalog total / case weight)
as `grams` and stored price_cents (which is per-pound for WEIGHT-sold
items) as `cents`. So a SKU like Tyson Fresh Chicken Wings shows as
10342g (22.8 lb) at $4.99 → implied $0.22/lb (impossible).

Fix: read avg_weight_per_unit from item_info, recompute:
    grams = avg_weight_per_unit_lb × 453.6
    cents = price_cents × avg_weight_per_unit_lb

Applies only to SKUs whose Kroger API record has sold_by=WEIGHT and a
parseable avg_weight_per_unit.

Backs up DB. Logs each fix.
"""
from __future__ import annotations
import csv, json, re, shutil, sqlite3, sys
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK  = DB.with_name("priced_products_v2.before_random_weight_fix.db")
LOG  = ROOT / "recipe_pricing" / "random_weight_fixes.csv"
API_DB = Path("/Users/jamiebarton/Desktop/Hestia/api/data/api_cache.db")


def collect_weight_skus() -> dict[str, dict]:
    """upc → {avg_weight_lb, price_cents, name} for Kroger sold_by=WEIGHT items."""
    api = sqlite3.connect(str(API_DB))
    cur = api.cursor()
    cur.execute("SELECT raw_json FROM api_cache WHERE source LIKE 'kroger%'")
    out: dict[str, dict] = {}
    for (j,) in cur.fetchall():
        try: d = json.loads(j)
        except: continue
        items = d if isinstance(d, list) else d.get("items", d.get("data", []))
        if not isinstance(items, list): continue
        for item in items:
            upc = item.get("upc") or item.get("product_meta", {}).get("kroger_upc")
            if not upc: continue
            meta = item.get("product_meta", {})
            if meta.get("sold_by") != "WEIGHT": continue
            info = meta.get("item_info", {})
            avg_w = info.get("avg_weight_per_unit", "")
            m = re.match(r"([\d.]+)", avg_w or "")
            if not m: continue
            avg_lb = float(m.group(1))
            if avg_lb <= 0 or avg_lb > 30: continue  # sanity
            price_cents = item.get("price_cents")
            if not price_cents: continue
            out[upc] = {
                "avg_weight_lb": avg_lb,
                "price_cents": int(price_cents),
                "name": item.get("name", "")[:80],
            }
    api.close()
    return out


def main():
    if not BAK.exists():
        print(f"backing up DB → {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))

    print("loading Kroger sold_by=WEIGHT SKUs from api_cache…", file=sys.stderr)
    weight_meta = collect_weight_skus()
    print(f"  {len(weight_meta)} distinct UPCs", file=sys.stderr)

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log_rows = []
    n_rows_updated = 0
    n_upcs_fixed = 0

    for upc, meta in weight_meta.items():
        new_grams = round(meta["avg_weight_lb"] * 453.6, 1)
        # Cents was per-lb; new package cents = per-lb × avg_weight_lb
        new_cents = round(meta["price_cents"] * meta["avg_weight_lb"])
        # Get current values for logging
        cur.execute("SELECT name, grams, cents FROM priced_products WHERE upc = ? LIMIT 1", (upc,))
        row = cur.fetchone()
        if not row: continue
        name, old_g, old_c = row
        # Only update if the values actually need fixing (sanity guard against
        # SKUs we already fixed in earlier passes)
        if abs(old_g - new_grams) < 1 and abs(old_c - new_cents) < 1:
            continue
        cur.execute("""UPDATE priced_products SET grams = ?, cents = ?,
            cpg = CAST(? AS REAL) / NULLIF(?, 0)
            WHERE upc = ?""", (new_grams, new_cents, new_cents, new_grams, upc))
        if cur.rowcount > 0:
            n_rows_updated += cur.rowcount
            n_upcs_fixed += 1
        log_rows.append({
            "upc": upc,
            "name": name[:80] if name else meta["name"],
            "avg_weight_lb": meta["avg_weight_lb"],
            "per_lb_cents": meta["price_cents"],
            "old_grams": round(old_g, 1) if old_g else 0,
            "new_grams": new_grams,
            "old_cents": old_c,
            "new_cents": new_cents,
            "rows_updated": cur.rowcount,
        })
    con.commit()
    con.close()

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["upc","name","avg_weight_lb","per_lb_cents",
            "old_grams","new_grams","old_cents","new_cents","rows_updated"])
        w.writeheader()
        for r in log_rows: w.writerow(r)

    print(f"\nfixed UPCs: {n_upcs_fixed}", file=sys.stderr)
    print(f"updated rows: {n_rows_updated}", file=sys.stderr)
    print(f"  → log: {LOG}", file=sys.stderr)

    print(f"\nTOP 15 fixes by SKU rows updated:", file=sys.stderr)
    log_rows.sort(key=lambda r: -r["rows_updated"])
    for r in log_rows[:15]:
        print(f"  +{r['rows_updated']:>3}  {r['old_grams']:>5.0f}g/${r['old_cents']/100:.2f} "
              f"→ {r['new_grams']:>5.0f}g/${r['new_cents']/100:.2f}  ({r['avg_weight_lb']}lb @ "
              f"${r['per_lb_cents']/100:.2f}/lb)  {r['name'][:50]}", file=sys.stderr)


if __name__ == "__main__":
    main()
