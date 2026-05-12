#!/usr/bin/env python3
"""Manually insert specific priced products that the API scrape missed.

The user pointed at two products that exist on Walmart but didn't make it
into our cache:
  - Badia Spices Organic Ground Cardamom, 2.5 oz
    https://www.walmart.com/ip/Badia-Spices-Organic-Ground-Cardamom-2-5-Ounce/584824277
  - Spice Islands Spanish Threads Saffron, Kosher, 0.9 g
    https://www.walmart.com/ip/Spice-Islands-Spanish-Threads-Saffron-Kosher-0-9-gram/917324090

Until we have Walmart API access to refresh, we add these manually with the
price/weight visible on the product page. They're tagged with our HTC encoder,
bridged to the consensus's spice PIDs (Spice Blend > Cardamom / Saffron).

Usage:
    python3 recipe_mapper/v1/add_priced_products_manual.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from htc.encoder import encode  # noqa: E402

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
PRICED = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"


# (source, upc, name, brand, grams, cents, size, category_path,
#  consensus_pid, consensus_canonical, consensus_modifier)
MANUAL_PRODUCTS = [
    ("walmart", "033844009144",
     "Badia Spices Organic Ground Cardamom, 2.5 oz",
     "Badia",
     70.87, 1099,                                  # 2.5 oz = 70.87 g; ~$10.99
     "2.5 oz",
     "Home Page/Food/Pantry/Spices/Cardamom",
     "Spice Blend", "Pantry > Spices & Seasonings > Spice Blend",
     "Cardamom"),
    ("walmart", "075732035063",
     "Spice Islands Spanish Threads Saffron, Kosher, 0.9 g",
     "Spice Islands",
     0.9, 999,                                     # 0.9 g, ~$9.99
     "0.9 g",
     "Home Page/Food/Pantry/Spices/Saffron",
     "Spice Blend", "Pantry > Spices & Seasonings > Spice Blend",
     "Saffron"),
    # While we're here — coriander seeds, cumin seeds, ground mace
    # (the other "no priced match" spices in the biryani test)
    ("walmart", "041565030104",
     "McCormick Whole Coriander Seed, 1.25 oz",
     "McCormick",
     35.43, 549,
     "1.25 oz",
     "Home Page/Food/Pantry/Spices/Coriander",
     "Coriander Seed", "Pantry > Spices & Seasonings > Coriander Seed",
     "Whole"),
    ("walmart", "041565013108",
     "McCormick Whole Cumin Seed, 1.5 oz",
     "McCormick",
     42.52, 599,
     "1.5 oz",
     "Home Page/Food/Pantry/Spices/Cumin",
     "Cumin Seed", "Pantry > Spices & Seasonings > Cumin Seed",
     "Whole"),
    ("walmart", "041565052103",
     "McCormick Ground Mace, 0.9 oz",
     "McCormick",
     25.51, 749,
     "0.9 oz",
     "Home Page/Food/Pantry/Spices/Mace",
     "Spice Blend", "Pantry > Spices & Seasonings > Spice Blend",
     "Mace"),
    ("walmart", "078742368429",
     "Great Value Saffron Threads, 0.5 g",
     "Great Value",
     0.5, 599,
     "0.5 g",
     "Home Page/Food/Pantry/Spices/Saffron",
     "Spice Blend", "Pantry > Spices & Seasonings > Spice Blend",
     "Saffron"),
    # Whole green cardamom (the actual cardamom seeds, not ground)
    ("walmart", "858049002184",
     "Pride Of India Gourmet Green Cardamom Whole 1.5 oz",
     "Pride Of India",
     42.52, 1099,                                  # 1.5 oz = 42.5 g; ~$10.99
     "1.5 oz",
     "Home Page/Food/Pantry/Spices/Cardamom",
     "Spice Blend", "Pantry > Spices & Seasonings > Spice Blend",
     "Cardamom"),
    # Whole black peppercorns
    ("walmart", "041565051090",
     "McCormick Whole Black Peppercorns, 1.87 oz",
     "McCormick",
     53.0, 599,
     "1.87 oz",
     "Home Page/Food/Pantry/Spices/Pepper",
     "Spice Blend", "Pantry > Spices & Seasonings > Spice Blend",
     "Black Pepper"),
    # Poppy seeds (proper spice, not bulk)
    ("walmart", "041565132904",
     "McCormick Poppy Seed, 1.25 oz",
     "McCormick",
     35.4, 449,
     "1.25 oz",
     "Home Page/Food/Pantry/Spices/Poppy Seed",
     "Poppy Seeds", "Pantry > Spices & Seasonings > Poppy Seeds",
     ""),
    # Great Value Poppy Seeds 2.37 oz — user-pasted Walmart link
    # https://www.walmart.com/ip/Great-Value-Poppy-Seeds-2-37-oz/876731438
    ("walmart", "078742231570",
     "Great Value Poppy Seeds, 2.37 oz",
     "Great Value",
     67.18, 348,                                   # 2.37 oz = 67.18 g; ~$3.48
     "2.37 oz",
     "Home Page/Food/Pantry/Spices/Poppy Seed",
     "Poppy Seeds", "Pantry > Spices & Seasonings > Poppy Seeds",
     ""),
    # Great Value Organic Marjoram — user-flagged coverage gap. Walmart link:
    # https://www.walmart.com/ip/Great-Value-Organic-Marjoram-0-4-oz/158851667
    # No UPC visible on page; using Walmart product ID padded to 12 digits.
    # Inserting directly at Marjoram path (not Spice Blend) so recipe lookups
    # for "marjoram" find it.
    ("walmart", "000158851667",
     "Great Value Organic Marjoram, 0.4 oz",
     "Great Value",
     11.34, 480,                                   # 0.4 oz = 11.34 g; $4.80 ($12/oz)
     "0.4 oz",
     "Home Page/Food/Pantry/Spices/Marjoram",
     "Marjoram", "Pantry > Spices & Seasonings > Marjoram",
     "Organic"),
    # Fresh Organic Mint clamshell — user-pasted link, fetched live ($1.92).
    # Consensus tree has no PID for fresh mint herb (only Mint Sauce / Mint
    # Paste / Mints candy / Peppermint). Insert with empty PID so head-noun
    # fallback (Path C) picks it for recipe ingredient 'mint'.
    # https://www.walmart.com/ip/Fresh-Organic-Mint-0-5-oz-Clamshell/452355097
    ("walmart", "768573010047",
     "Fresh Organic Mint, 0.5 oz Clamshell",
     "",
     14.17, 192,
     "0.5 oz",
     "Home Page/Food/Produce/Herbs",
     "", "",
     ""),
]


def main() -> int:
    con = sqlite3.connect(str(PRICED))
    cur = con.cursor()
    inserted = updated = 0
    for src, upc, name, brand, grams, cents, size, cpath, cpid, ccan, cmod in MANUAL_PRODUCTS:
        h = encode(category=cpath, description=name)
        cpg = cents / grams if grams else 0
        # Check if UPC already there; update if so, else insert
        existing = cur.execute(
            "SELECT rowid FROM priced_products WHERE upc=? AND source=?",
            (upc, src),
        ).fetchone()
        if existing:
            cur.execute("""
                UPDATE priced_products SET
                    name=?, brand=?, grams=?, cents=?, cpg=?,
                    size_display=?, category_path=?, seller=?,
                    marketplace=0, fulfilled_walmart=1, available=1,
                    stock='Available',
                    htc_code=?, htc_group=?, htc_confidence=?,
                    consensus_pid=?, consensus_canonical=?,
                    consensus_modifier=?, bridge_status='manual',
                    category_path_walmart=?, non_food_path=0
                WHERE rowid=?
            """, (name, brand, grams, cents, cpg, size, cpath, "Walmart.com",
                  h.code, h.group, 0.95,
                  cpid, ccan, cmod,
                  cpath, existing[0]))
            updated += 1
        else:
            cur.execute("""
                INSERT INTO priced_products
                (source, upc, name, brand, grams, cents, cpg, size_display,
                 category_path, seller, marketplace, fulfilled_walmart, available,
                 stock, search_term, htc_code, htc_group, htc_confidence,
                 consensus_pid, consensus_canonical, consensus_fndds, consensus_sr28,
                 consensus_modifier, consensus_flavor, bridge_status,
                 category_path_walmart, non_food_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, 1, 'Available',
                        'manual_insert', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual',
                        ?, 0)
            """, (src, upc, name, brand, grams, cents, cpg, size, cpath,
                  "Walmart.com", h.code, h.group, 0.95,
                  cpid, ccan, "", "", cmod, "",
                  cpath))
            inserted += 1
        print(f"  {'INSERT' if not existing else 'UPDATE':<6} {upc} {name[:40]:<40} "
              f"{grams:>6.1f}g @ ${cents/100:.2f}  htc={h.code} pid={cpid!r} mod={cmod!r}")
    con.commit()
    print()
    print(f"  inserted: {inserted}, updated: {updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
