#!/usr/bin/env python3
"""Dedupe redundant adjacent segments across all paths.

Three patterns this fixes:
  A. Plural/singular leaf duplicate:
     'Meal > Sandwiches > Sandwich' → 'Meal > Sandwiches'
     'Bakery > Rolls > Roll' → 'Bakery > Rolls'
  B. Whole-segment substring (child contains parent's exact phrase):
     'Pantry > Sweeteners > Syrup > Maple Syrup' → 'Pantry > Sweeteners > Syrup > Maple'
     'Dairy > Cheese > Cottage Cheese' → 'Dairy > Cheese > Cottage'
     'Snack > Gum > Bubble Gum' → 'Snack > Gum > Bubble'
  C. Repeated phrase (compound segments echoing each other):
     'Frozen > Breakfast Sandwiches > Breakfast Sandwich > Egg Cheese'
       → 'Frozen > Breakfast Sandwiches > Egg Cheese'

Skip-list preserves canonical multi-word names where the redundancy is meaningful.
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
LOG = V2 / "dedupe_adjacent_segments_log.csv"

csv.field_size_limit(sys.maxsize)

# Don't strip these even if they're substrings — they're canonical names
PRESERVE_SEGMENTS = {
    "Cottage Cheese", "Cream Cheese", "Goat Cheese", "Blue Cheese", "String Cheese",
    "Ice Cream", "Sour Cream", "Heavy Cream", "Light Cream", "Whipped Cream",
    "Cream Soda", "Coffee Creamer",
    "Hot Dog", "Hot Dogs", "Trail Mix", "Snack Mix",
    "Peanut Butter", "Almond Butter", "Cashew Butter", "Cocoa Butter",
    "Cookie Butter", "Sunflower Seed Butter",
    "Salad Dressing", "Salad Dressings",
    "Whole Grain", "Multi Grain", "Whole Wheat",
    "Fat Free", "Low Fat", "Reduced Fat", "Sugar Free", "Gluten Free",
    "Lactose Free", "Dairy Free", "Plant Based", "Sea Salt",
    "Whole Milk", "Low Moisture", "Part Skim",
    "Sharp Cheddar", "Mild Cheddar", "Mexican Blend",
}

PLURAL_TO_SINGULAR = {
    "sandwiches": "sandwich", "rolls": "roll", "buns": "bun", "cookies": "cookie",
    "muffins": "muffin", "bagels": "bagel", "doughnuts": "doughnut", "donuts": "donut",
    "croissants": "croissant", "biscuits": "biscuit", "pies": "pie", "cakes": "cake",
    "cupcakes": "cupcake", "brownies": "brownie", "tortillas": "tortilla",
    "flatbreads": "flatbread", "breadsticks": "breadstick",
    "pretzels": "pretzel", "crackers": "cracker", "chips": "chip",
    "nuts": "nut", "puffs": "puff", "sticks": "stick",
    "yogurts": "yogurt", "milks": "milk", "creams": "cream", "butters": "butter",
    "eggs": "egg", "cheeses": "cheese",
    "sauces": "sauce", "soups": "soup", "salsas": "salsa", "syrups": "syrup",
    "olives": "olive", "pickles": "pickle", "mushrooms": "mushroom",
    "tomatoes": "tomato", "potatoes": "potato", "peppers": "pepper",
    "onions": "onion", "carrots": "carrot", "apples": "apple", "oranges": "orange",
    "berries": "berry", "cherries": "cherry", "raspberries": "raspberry",
    "blueberries": "blueberry", "strawberries": "strawberry",
    "noodles": "noodle", "beans": "bean", "peas": "pea", "lentils": "lentil",
    "vegetables": "vegetable", "fruits": "fruit", "spices": "spice",
    "seasonings": "seasoning", "dressings": "dressing", "mixes": "mix",
    "snacks": "snack", "bars": "bar", "puffs": "puff", "balls": "ball",
    "bites": "bite", "rings": "ring", "wraps": "wrap", "cones": "cone",
    "shells": "shell", "squares": "square", "twists": "twist",
    "patties": "patty", "loaves": "loaf",
    "drinks": "drink", "shots": "shot", "shakes": "shake", "smoothies": "smoothie",
    "teas": "tea", "juices": "juice", "sodas": "soda", "lemonades": "lemonade",
    "beverages": "beverage", "waters": "water",
    "chocolates": "chocolate", "candies": "candy", "puddings": "pudding",
    "salads": "salad", "dishes": "dish", "entrees": "entree", "kits": "kit",
    "dumplings": "dumpling", "crisps": "crisp",
    "sausages": "sausage", "pizzas": "pizza", "appetizers": "appetizer",
    "powders": "powder", "shells": "shell",
    "spreads": "spread", "dips": "dip", "rinds": "rind", "skins": "skin",
    "bagels": "bagel", "scones": "scone",
    "pastries": "pastry", "tarts": "tart", "macarons": "macaron",
    "donuts": "donut", "doughnuts": "doughnut",
    "pies": "pie", "kits": "kit",
}
SINGULAR_TO_PLURAL = {v: k for k, v in PLURAL_TO_SINGULAR.items()}


def is_singular_plural_pair(a: str, b: str) -> bool:
    al, bl = a.lower(), b.lower()
    if al == bl: return True
    if PLURAL_TO_SINGULAR.get(al) == bl: return True
    if PLURAL_TO_SINGULAR.get(bl) == al: return True
    if SINGULAR_TO_PLURAL.get(al) == bl: return True
    if SINGULAR_TO_PLURAL.get(bl) == al: return True
    return False


def strip_word_from_segment(seg: str, word: str) -> str:
    """Remove `word` (case-insensitive) from segment, return cleaned segment."""
    pattern = re.compile(rf"\b{re.escape(word)}\b", re.I)
    cleaned = pattern.sub("", seg).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)  # collapse whitespace
    return cleaned


def dedupe_path(path: str) -> tuple[str, list[str]]:
    """Apply dedupe rules iteratively. Return (new_path, applied_rules)."""
    if not path or " > " not in path:
        return path, []
    segs = path.split(" > ")
    applied: list[str] = []
    changed = True
    iterations = 0
    while changed and iterations < 6:
        changed = False
        iterations += 1
        out: list[str] = []
        i = 0
        while i < len(segs):
            cur = segs[i]
            nxt = segs[i+1] if i+1 < len(segs) else None
            if nxt is None:
                out.append(cur); i += 1; continue
            cur_l, nxt_l = cur.lower(), nxt.lower()

            # Pattern A — plural/singular pair (drop the leaf if last)
            if is_singular_plural_pair(cur, nxt) and i+2 == len(segs):
                # Keep the parent (cur), drop the leaf (nxt)
                out.append(cur)
                applied.append(f"singular-plural-leaf:{nxt}")
                changed = True
                i += 2  # skip the next segment
                continue

            # Pattern B — child segment ends with or equals the parent segment
            # 'Cheese > Cottage Cheese' → 'Cheese > Cottage'
            # 'Syrup > Maple Syrup' → 'Syrup > Maple'
            if (nxt not in PRESERVE_SEGMENTS and
                len(nxt.split()) > 1 and
                nxt_l != cur_l and
                (nxt_l.endswith(" " + cur_l) or nxt_l.startswith(cur_l + " "))):
                cleaned = strip_word_from_segment(nxt, cur)
                if cleaned and cleaned.lower() != cur_l:
                    out.append(cur)
                    out.append(cleaned)
                    applied.append(f"strip-parent-echo:{cur}|{nxt}->{cleaned}")
                    changed = True
                    i += 2
                    continue

            # Pattern C — child fully contains parent as substring (multi-word echo)
            # 'Breakfast Sandwiches > Breakfast Sandwich > Egg Cheese' → drop one
            if cur not in PRESERVE_SEGMENTS and nxt not in PRESERVE_SEGMENTS:
                cur_words = set(cur_l.split())
                nxt_words = set(nxt_l.split())
                overlap = cur_words & nxt_words
                # If they share most words AND one has size 2+ words AND they're plural/singular variants of compound
                if (overlap and len(cur_words) >= 2 and len(nxt_words) >= 2
                    and (cur_words.issubset(nxt_words) or nxt_words.issubset(cur_words)
                         or len(overlap) / max(len(cur_words), len(nxt_words)) >= 0.66)):
                    # Keep the more-specific one (more words) or the parent (cur) if same length
                    if len(nxt_words) > len(cur_words):
                        # leaf has extra info → drop parent, keep leaf
                        out.append(nxt)
                        applied.append(f"compound-echo-drop-parent:{cur}|{nxt}")
                    else:
                        out.append(cur)
                        applied.append(f"compound-echo-drop-leaf:{cur}|{nxt}")
                    changed = True
                    i += 2
                    continue

            out.append(cur)
            i += 1
        segs = out

    new_path = " > ".join(segs)
    return new_path, applied


def main(apply_mode: bool) -> None:
    print(f"  mode: {'APPLY' if apply_mode else 'DRY-RUN'}")
    n_total = 0
    n_changed = 0
    rule_counter: dict[str, int] = {}
    samples: list[dict] = []
    log_rows: list[dict] = []

    if apply_mode:
        tmp = AUDIT.with_suffix(".tmp.csv")
        fout = tmp.open("w", encoding="utf-8", newline="")
    else:
        fout = None

    with AUDIT.open(encoding="utf-8", newline="") as fin:
        rdr = csv.DictReader(fin)
        wtr = None
        if fout:
            wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
            wtr.writeheader()
        for r in rdr:
            n_total += 1
            old_cp = r.get("canonical_path", "") or ""
            old_rlp = r.get("retail_leaf_path", "") or ""
            new_cp, rules_cp = dedupe_path(old_cp)
            new_rlp, rules_rlp = dedupe_path(old_rlp)
            if new_cp != old_cp or new_rlp != old_rlp:
                n_changed += 1
                for rule in rules_cp + rules_rlp:
                    short = rule.split(":")[0]
                    rule_counter[short] = rule_counter.get(short, 0) + 1
                if len(samples) < 30:
                    samples.append({
                        "old_cp": old_cp, "new_cp": new_cp,
                        "old_rlp": old_rlp, "new_rlp": new_rlp,
                        "rules": " ; ".join(rules_cp + rules_rlp)[:200],
                    })
                if apply_mode:
                    r["canonical_path"] = new_cp
                    r["retail_leaf_path"] = new_rlp
                    log_rows.append({
                        "fdc_id": r.get("fdc_id", ""),
                        "old_cp": old_cp, "new_cp": new_cp,
                        "old_rlp": old_rlp, "new_rlp": new_rlp,
                        "rules": " ; ".join(rules_cp + rules_rlp),
                    })
            if wtr: wtr.writerow(r)

    if fout:
        fout.close()
        shutil.move(str(tmp), str(AUDIT))
        if log_rows:
            cols = list(log_rows[0].keys())
            with LOG.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=cols)
                w.writeheader()
                w.writerows(log_rows)
            print(f"  wrote {LOG.name}")

    print(f"  rows scanned: {n_total:,}")
    print(f"  rows changed: {n_changed:,}")
    print(f"  rule application counts:")
    for rule in sorted(rule_counter, key=lambda k: -rule_counter[k]):
        print(f"    {rule:<35} {rule_counter[rule]:>5}")
    print()
    print(f"  --- sample changes (up to 30) ---")
    for s in samples[:30]:
        if s['old_cp'] != s['new_cp']:
            print(f"    cp : {s['old_cp']}")
            print(f"      → {s['new_cp']}")
        if s['old_rlp'] != s['new_rlp']:
            print(f"    rlp: {s['old_rlp']}")
            print(f"      → {s['new_rlp']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    main(args.apply)
