#!/usr/bin/env python3
"""Add categoryPath + non_food_path flag to priced_products_v2.

Walmart's raw API gives a categoryPath like:
  'Home Page/Food/Pantry/Pantry meal essentials'        ← FOOD
  'Home Page/Toys/Easter/Confetti Eggs'                 ← NOT FOOD
  'Home Page/Health/Personal Care/Oral Care/Mouthwash'  ← NOT FOOD
  'Home Page/Beauty/Bath & Body/Soap'                   ← NOT FOOD

We dropped this column when we built priced_products_v2.db; pulling it back
in lets us catch the joke products (confetti eggs) and personal-care junk
(mouthwash mint, lemon zest dish soap) that leaked into the food matcher.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
HESTIA_CACHE = Path("/Users/jamiebarton/Desktop/Hestia/api/data/api_cache.db")
PRICED = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"

NON_FOOD_PATH_PATTERNS = re.compile(
    r"\b(toys?|games?|puzzles?|"
    r"health\s*&?\s*personal\s*care|personal\s*care|"
    r"oral\s*care|mouthwash|toothpaste|deodorant|shampoo|conditioner|"
    r"beauty|bath\s*&?\s*body|skin\s*care|cosmetics?|fragrances?|"
    r"cleaning|laundry|paper\s*products|"
    r"pets?|pet\s*food|cat\s*food|dog\s*food|"
    r"baby\s*care|diapers?|wipes?|"
    r"home\s*decor|crafts?|party\s*supplies|holiday|easter|christmas|halloween|"
    r"cascaron|confetti|decoration|gift|seasonal|"
    r"office|electronics|automotive|hardware|garden|patio|"
    r"medicine|first\s*aid|vitamins?(?!\s*&?\s*supplements)|"
    r"supplements(?!\s*&?\s*food)|protein\s*(?:powder|drink|shake|supplement)|"
    r"meal\s*replacement|weight\s*loss|keto)",
    re.I,
)


def main() -> int:
    prc = sqlite3.connect(str(PRICED))
    cur = prc.cursor()
    cols = {r[1] for r in cur.execute("PRAGMA table_info(priced_products)")}
    for col, ddl in [
        ("category_path_walmart", "ALTER TABLE priced_products ADD COLUMN category_path_walmart TEXT"),
        ("non_food_path", "ALTER TABLE priced_products ADD COLUMN non_food_path INTEGER DEFAULT 0"),
    ]:
        if col not in cols:
            cur.execute(ddl)
    prc.commit()

    print("walking raw walmart cache to extract categoryPath per UPC...")
    hc = sqlite3.connect(str(HESTIA_CACHE))
    upc_to_path: dict[str, str] = {}
    for raw in hc.execute("SELECT raw_json FROM api_cache WHERE source='walmart_search'"):
        try:
            items = json.loads(raw[0])
        except Exception:
            continue
        if not isinstance(items, list):
            continue
        for it in items:
            upc = str(it.get("upc") or "").strip()
            if not upc:
                continue
            cp = it.get("categoryPath") or ""
            if cp and upc not in upc_to_path:
                upc_to_path[upc] = cp
    print(f"  {len(upc_to_path):,} UPC → categoryPath")

    print("updating priced_products...")
    rows = cur.execute("SELECT rowid, upc, source FROM priced_products").fetchall()
    n = matched = nf_dropped = 0
    upds = []
    for rowid, upc, src in rows:
        n += 1
        cp = upc_to_path.get(upc, "")
        is_nf = 1 if (cp and NON_FOOD_PATH_PATTERNS.search(cp)) else 0
        if cp:
            matched += 1
        if is_nf:
            nf_dropped += 1
        upds.append((cp, is_nf, rowid))
    cur.executemany(
        "UPDATE priced_products SET category_path_walmart=?, non_food_path=? WHERE rowid=?",
        upds,
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pp_nfp ON priced_products(non_food_path)")
    prc.commit()

    print(f"  total rows:                  {n:,}")
    print(f"  with categoryPath:           {matched:,}")
    print(f"  flagged non-food by path:    {nf_dropped:,}")

    # Sample non-food drops
    print()
    print("=== sample products newly flagged as non-food ===")
    for r in cur.execute("""
        SELECT substr(name,1,50), category_path_walmart, htc_group
        FROM priced_products WHERE non_food_path=1 ORDER BY RANDOM() LIMIT 12
    """):
        print(f"  {r[0]:<50}  path={r[1][:60]}  htc={r[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
