#!/usr/bin/env python3
"""End-to-end demo planner. Picks N real recipes, runs the calculation
flow using the cleaned data layer, prints the result.

Per recipe-line:
  recipes_unified           → raw display, qty, grams_resolved
  classifier (cleaned)      → canonical_buy_form, buyability, usage,
                              extracted_claims, base_ingredients
  priced_products_v2.db     → cheapest matching Walmart product
                              (matched by consensus_pid / consensus_canonical
                              against canonical_buy_form text)
  calc_decision rules:
    derivative                → SKIP (already shopping for upstream)
    unbuyable / nonsense      → REVIEW
    usage in {to_taste,garnish,optional} → shop_only (no quantity calc)
    everything else           → calculate cost = grams × cents_per_gram
                                                 → macros from FNDDS lookup
                                                   (skipped in this demo —
                                                    we only show cost)

Aggregates per-recipe shopping list, total cost, decision points.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
CLEANED_CLS = ROOT / "recipe_pricing" / "buyability_classifications_cleaned.jsonl"
PRICED_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"

# Pick recipes that exhibit the variety we improved
DEMO_RECIPE_IDS = {
    "233694",  # Buffalo Potatoes (cayenne pepper sauce, multiple to_taste)
    "300767",  # Easy Hush Puppies from Arkansas (boiling water = derivative)
    "25640",   # Easy Lobster Bisque (alternation, specialty)
    "382",     # Avocado Salsa (lots of alternation)
}


# Common non-food noise terms that show up in priced_products with food
# consensus_pid due to bridge errors. Filter products whose name contains
# any of these UNLESS the canonical_buy_form itself contains the term
# (e.g. canonical_buy_form="ice cream" should match products with "ice cream"
# in name).
NONFOOD_NOISE = [
    "water softener", "softener", "pellets", "fertilizer", "lotion",
    "soap", "candle", "scrub", "cleaning", "cleaner", "deodorant",
    "shampoo", "conditioner", "essential oil", "fragrance",
    "fishing line",
]
# Identity-conflict noise: when canonical_buy_form is "butter", these
# products contain "butter" in their name but ARE NOT butter.
IDENTITY_CONFLICT = {
    "butter": ["pecan", "peanut butter", "almond butter", "cashew butter",
               "sunflower butter", "cookie", "ice cream", "syrup", "flavor",
               "popcorn", "spread", "candy"],
    "salt": ["water softener", "softener", "pellets", "rock salt",
             "epsom", "bath", "sea salt", "kosher salt"],  # bare 'salt' shouldn't match these specialty
    "cream": ["ice cream", "cream cheese", "sour cream", "whipped cream",
              "shaving", "lotion"],
    "milk": ["chocolate milk", "milk chocolate", "milk powder", "powdered milk"],
    "sugar": ["sugar substitute", "sugar free", "sugar cookie"],
}

def name_passes_filter(name: str, canonical: str) -> bool:
    nl = name.lower()
    cl = canonical.lower()
    # Exclude obvious non-food noise unless the canonical itself includes it
    for noise in NONFOOD_NOISE:
        if noise in nl and noise not in cl:
            return False
    # Identity-conflict filter: bare-canonical shouldn't match modifier-prefixed names
    conflicts = IDENTITY_CONFLICT.get(cl, [])
    for c in conflicts:
        if c in nl:
            return False
    return True


def find_cheapest_product(con: sqlite3.Connection,
                           canonical_buy_form: str) -> dict | None:
    """Look up cheapest product where consensus_pid (the leaf identity)
    EXACTLY matches canonical_buy_form (case-insensitive, plural-tolerant).
    Then apply name-based filter to exclude bridge-error mismatches
    (water softener salt at Salt pid, butter pecan ice cream at Butter pid)."""
    if not canonical_buy_form:
        return None
    cur = con.cursor()
    target = canonical_buy_form.lower().strip()
    candidates = [target]
    if target.endswith("s") and not target.endswith("ss"):
        candidates.append(target[:-1])
    else:
        candidates.append(target + "s")

    for candidate in candidates:
        cur.execute("""
            SELECT name, brand, grams, cents, cpg, consensus_canonical, consensus_pid
            FROM priced_products
            WHERE LOWER(consensus_pid) = ?
              AND available = 1 AND grams > 0 AND cents > 0
            ORDER BY cpg ASC
        """, (candidate,))
        rows = cur.fetchall()
        for row in rows:
            name = row[0] or ""
            if name_passes_filter(name, target):
                return {"name": name, "brand": row[1], "grams": row[2],
                        "cents": row[3], "cpg": row[4],
                        "match": f"pid={candidate}"}
    return None


def load_unified_lines(target_ids: set[str]) -> dict[str, list[dict]]:
    """recipes_unified is per-line. Group lines by recipe_id."""
    out: defaultdict[str, list[dict]] = defaultdict(list)
    with UNIFIED.open(newline="") as f:
        for row in csv.DictReader(f):
            rid = str(row.get("recipe_id", "")).strip()
            if rid in target_ids:
                out[rid].append(row)
    return out


def load_classifications(target_ids: set[str]) -> dict[str, dict[int, dict]]:
    """Load cleaned classifications keyed by (recipe_id, line_index)."""
    out: dict[str, dict[int, dict]] = {}
    with CLEANED_CLS.open() as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = str(r.get("recipe_id"))
            if rid in target_ids:
                out[rid] = {c["line_index"]: c for c in r.get("classifications", [])}
    return out


def calc_decision(buyability: str, usage: str) -> str:
    if buyability in ("derivative",):
        return "skip_derivative"
    if buyability in ("unbuyable", "nonsense"):
        return "review"
    if usage in ("to_taste", "garnish", "optional"):
        return "shop_only"
    return "calculate"


def render_recipe(rid: str, unified_lines: list[dict], classifications: dict,
                   con: sqlite3.Connection) -> None:
    if not unified_lines:
        print(f"\n  recipe {rid} not found in recipes_unified")
        return

    title = unified_lines[0].get("recipe_title", "?")
    print(f"\n{'='*80}")
    print(f"RECIPE [{rid}] {title}")
    print('='*80)

    shopping_list: list[tuple[str, str, int]] = []  # (display_form, sku_name, sku_cents)
    total_line_cost_cents = 0.0
    decisions: list[str] = []
    cls_idx_to_use = {c.get("line_index"): c for c in classifications.values()}

    print(f"\n{'#':<3} {'RAW INGREDIENT':<55} {'CLEANED':<28} {'DECISION':<18} {'COST'}")
    print('-'*125)

    # Match unified lines to classifications by ingredient_item + display match
    # since recipes_unified doesn't have line_index. For the demo we walk in order.
    cls_list = list(classifications.values())
    for i, urow in enumerate(unified_lines):
        display = urow.get("display", "")
        try:
            grams = float(urow.get("grams_resolved") or 0)
        except (TypeError, ValueError):
            grams = 0.0

        # Find matching classification by ingredient_item or by index order
        c = None
        item_key = (urow.get("ingredient_item") or "").lower().strip()
        for cc in cls_list:
            if cc.get("line_index") == i:
                c = cc; break
        if not c and cls_list and i < len(cls_list):
            c = cls_list[i]

        if not c:
            print(f"  {i:<3} {display[:53]:<55} (no classification)")
            continue

        canon = c.get("canonical_buy_form") or ""
        bu = c.get("buyability", "")
        us = c.get("usage", "")
        claims = c.get("extracted_claims") or []
        base = c.get("base_ingredients") or []

        decision = calc_decision(bu, us)

        cost_str = ""
        if decision == "calculate":
            prod = find_cheapest_product(con, canon)
            if prod and grams > 0:
                line_cents = grams * (prod["cpg"] or 0)
                total_line_cost_cents += line_cents
                cost_str = f"${line_cents/100:.2f}"
                shopping_list.append((canon, prod["name"], prod["cents"]))
            elif prod:
                cost_str = "(no grams)"
                shopping_list.append((canon, prod["name"], prod["cents"]))
            else:
                cost_str = "(no SKU)"
        elif decision == "shop_only":
            prod = find_cheapest_product(con, canon)
            if prod:
                shopping_list.append((canon, prod["name"], prod["cents"]))
                cost_str = "(shop_only)"
            else:
                cost_str = "(shop_only,no SKU)"
        elif decision == "skip_derivative":
            cost_str = f"← {','.join(base) or 'upstream'}"
        elif decision == "review":
            cost_str = "FLAG"

        decisions.append(f"{i}:{decision}:{bu}/{us}")

        canon_display = canon if canon else "—"
        if claims:
            canon_display += f" + [{','.join(claims)}]"

        print(f"  {i:<3} {display[:53]:<55} {canon_display[:26]:<28} {decision:<18} {cost_str}")

    print('-'*125)
    print(f"\nLINE-COST TOTAL:        ${total_line_cost_cents/100:.2f}")
    # Aggregate shopping list (dedupe by SKU name)
    sku_seen: dict[str, int] = {}
    for canon, name, cents in shopping_list:
        sku_seen[name] = cents
    print(f"\nSHOPPING LIST ({len(sku_seen)} SKUs):")
    total_cart_cents = 0
    for name, cents in sku_seen.items():
        total_cart_cents += cents or 0
        print(f"  • {name[:75]:<75}  ${(cents or 0)/100:.2f}")
    print(f"\nFULL CART TOTAL:        ${total_cart_cents/100:.2f}")
    print(f"  (vs. line-attributed cost ${total_line_cost_cents/100:.2f} — difference is leftover product)")


def main() -> int:
    if not all(p.exists() for p in [UNIFIED, CLEANED_CLS, PRICED_DB]):
        for p in [UNIFIED, CLEANED_CLS, PRICED_DB]:
            print(f"  {p}: {'OK' if p.exists() else 'MISSING'}", file=sys.stderr)
        raise SystemExit("missing required input files")

    print(f"loading recipes_unified rows for {len(DEMO_RECIPE_IDS)} demo recipes...", file=sys.stderr)
    unified_by_recipe = load_unified_lines(DEMO_RECIPE_IDS)
    print(f"  found {sum(len(v) for v in unified_by_recipe.values())} ingredient lines", file=sys.stderr)

    print(f"loading classifier output...", file=sys.stderr)
    cls_by_recipe = load_classifications(DEMO_RECIPE_IDS)
    print(f"  found classifications for {len(cls_by_recipe)} recipes", file=sys.stderr)

    con = sqlite3.connect(str(PRICED_DB))

    for rid in DEMO_RECIPE_IDS:
        render_recipe(rid, unified_by_recipe.get(rid, []), cls_by_recipe.get(rid, {}), con)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
