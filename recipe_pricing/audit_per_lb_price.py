#!/usr/bin/env python3
"""Find SKUs where the cents field stores per-lb price instead of package price.

Brisket symptom: 1293g (2.85 lb) at $12.99 stored when real package is $35.60.
Implied $/lb of $4.55 vs real $12.49 — off by 2.74×.

Approach: for Meat & Seafood + Produce SKUs at the typical fresh-cut sizes
(500g–10000g), compute implied $/lb. Flag rows where implied $/lb is well
under category-typical floor.

Floor heuristics (USDA + Walmart/Kroger 2024 typical):
  Beef:    $4.99/lb
  Pork:    $2.49/lb
  Chicken: $1.49/lb
  Lamb:    $5.99/lb
  Fish:    $5.99/lb
  Shellfish: $5.99/lb
  Produce: $0.49/lb

If implied $/lb < floor × 0.5 → suspect per-lb-as-package bug.

Outputs CSV ranked by severity. Manual review before applying.
"""
from __future__ import annotations
import csv, sqlite3
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT  = ROOT / "recipe_pricing" / "per_lb_price_audit.csv"

CATEGORY_FLOORS = {
    "Beef":      4.99,
    "Pork":      2.49,
    "Poultry":   1.49,
    "Chicken":   1.49,
    "Turkey":    1.49,
    "Lamb":      5.99,
    "Fish":      5.99,
    "Shellfish": 5.99,
    "Veal":      6.99,
    "Bacon":     5.99,
    "Ham":       3.49,
    "Sausage":   3.49,
}


def main():
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""SELECT name, grams, cents, consensus_canonical, upc
        FROM priced_products
        WHERE consensus_canonical LIKE 'Meat & Seafood%'
          AND available=1 AND grams >= 200 AND cents > 0""")
    rows = cur.fetchall()
    print(f"scanning {len(rows):,} meat SKUs ≥ 200g…")

    bugs = []
    for name, g, c, cp, upc in rows:
        # Determine category from path
        category = None
        for cat in CATEGORY_FLOORS:
            if cat in cp:
                category = cat; break
        if not category: continue
        floor = CATEGORY_FLOORS[category]
        implied_per_lb = (c / g) * 453.592 / 100  # cents/g × g/lb / 100
        if implied_per_lb < floor * 0.5:
            # Suspect: implied $/lb is way too low. Real price is likely
            # cents × g_per_lb_assumption (i.e. cents stores $/lb, not pkg)
            inferred_real_price = (c * g / 453.592) / 100  # if cents was $/lb
            bugs.append({
                "upc": upc,
                "category": category,
                "name": name[:90],
                "grams": round(g, 1),
                "stored_cents": c,
                "stored_dollars": round(c / 100, 2),
                "implied_per_lb": round(implied_per_lb, 2),
                "category_floor": floor,
                "inferred_real_price": round(inferred_real_price, 2),
                "lbs": round(g / 453.592, 2),
                "canonical_path": cp,
            })

    bugs.sort(key=lambda b: b["implied_per_lb"])
    print(f"  flagged: {len(bugs):,} suspect SKUs")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = ["upc","category","name","grams","lbs","stored_cents","stored_dollars",
             "implied_per_lb","category_floor","inferred_real_price","canonical_path"]
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for b in bugs: w.writerow(b)
    print(f"  → {OUT}\n")

    print(f"=== TOP 30 by lowest implied $/lb ===")
    for b in bugs[:30]:
        print(f"  ${b['implied_per_lb']:>5.2f}/lb (floor ${b['category_floor']:.2f})  "
              f"stored=${b['stored_dollars']:>6.2f}  if-per-lb→real=${b['inferred_real_price']:>6.2f}  "
              f"{b['lbs']:.1f}lb  {b['name'][:55]}")


if __name__ == "__main__":
    main()
