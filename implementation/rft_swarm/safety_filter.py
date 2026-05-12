"""Safety filter for swarm fix proposals.

Reads a fixes CSV, applies rejection rules, writes safe_fixes.csv and rejected_fixes.csv.
"""
import csv, sys
from pathlib import Path

# Rejection rules: list of (field, pattern, reason) tuples
# Pattern is checked case-insensitively against the field value
REJECTION_RULES = [
    # Soda / beverage cross-category leaks
    ("proposed_esha_desc", "beer", "reject_beer_for_non_alcoholic"),
    ("proposed_esha_desc", "water, tap", "reject_tap_water_for_bottled"),
    ("proposed_esha_desc", "tangerines, fresh", "reject_produce_leak"),
    ("proposed_esha_desc", "carbohydrate gel", "reject_gel_leak"),
    ("current_esha_desc", "beer", "reject_beer_for_non_alcoholic"),
    # Frozen → canned drift
    ("proposed_esha_desc", "canned", "reject_frozen_to_canned"),
    # Nut/seed identity loss
    ("product_description", "peanut", "reject_vegetable_for_nut"),
    ("product_description", "almond", "reject_vegetable_for_nut"),
    ("product_description", "cashew", "reject_vegetable_for_nut"),
    ("product_description", "walnut", "reject_vegetable_for_nut"),
    ("product_description", "pecan", "reject_vegetable_for_nut"),
    ("product_description", "pistachio", "reject_vegetable_for_nut"),
    ("product_description", "seed", "reject_vegetable_for_seed"),
    # Dressing-specific: don't flatten mayo variants
    ("product_description", "light mayonnaise", "reject_mayo_flattening"),
    ("product_description", "real mayonnaise", "reject_mayo_flattening"),
    ("product_description", "fat free mayonnaise", "reject_mayo_flattening"),
    # Don't route obvious salad toppings to dressing
    ("product_description", "bacon bits", "reject_dressing_for_topping"),
    ("product_description", "tortilla strips", "reject_dressing_for_topping"),
    ("product_description", "crouton", "reject_dressing_for_topping"),
]

# Extra logic: if product has a nut/seed word and proposed code is a vegetable, reject
VEGETABLE_CODES = {"squash", "vegetable", "broccoli", "carrot", "cauliflower", "pepper"}
NUT_WORDS = {"peanut", "almond", "cashew", "walnut", "pecan", "pistachio", "macadamia"}
SEED_WORDS = {"seed", "sunflower", "pumpkin", "sesame", "chia", "flax"}

def is_rejected(row):
    desc = (row.get("product_description") or "").lower()
    prop_desc = (row.get("proposed_esha_desc") or "").lower()
    cur_desc = (row.get("current_esha_desc") or "").lower()
    reason = row.get("reason", "")
    
    # Check explicit rules
    for field, pattern, rej_reason in REJECTION_RULES:
        val = (row.get(field) or "").lower()
        if pattern in val:
            # Exception: if the product is actually the pattern (e.g. "BEER" product on beer code)
            if pattern in desc and field.startswith("proposed"):
                continue
            # Exception: reject_frozen_to_canned only if product is frozen
            if rej_reason == "reject_frozen_to_canned" and "frozen" not in desc:
                continue
            # Exception: reject_vegetable_for_nut only if proposed is actually vegetable
            if rej_reason == "reject_vegetable_for_nut" and not any(v in prop_desc for v in VEGETABLE_CODES):
                continue
            # Exception: reject_vegetable_for_seed only if proposed is vegetable
            if rej_reason == "reject_vegetable_for_seed" and not any(v in prop_desc for v in VEGETABLE_CODES):
                continue
            return rej_reason
    
    # Special: don't change products that are already on a specific variant code
    # unless it's clearly wrong (we handle this in analyzer, but double-check)
    if reason.startswith("variant_word:") and cur_desc and prop_desc:
        # If current has a flavor word that proposed doesn't, and current isn't base
        # (e.g. strawberry applesauce -> unsweetened applesauce)
        # We already filtered base-only in analyzer, but extra safety:
        if any(v in cur_desc for v in ["strawberry", "blueberry", "cherry", "peach", "mango"]):
            if not any(v in prop_desc for v in ["strawberry", "blueberry", "cherry", "peach", "mango"]):
                return "reject_downgrade_variant"
    
    return None

def filter_file(path: Path):
    safe = []
    rejected = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            rej = is_rejected(row)
            if rej:
                row["reject_reason"] = rej
                rejected.append(row)
            else:
                safe.append(row)
    base = path.stem
    safe_path = path.with_name(f"{base}_safe.csv")
    rej_path = path.with_name(f"{base}_rejected.csv")
    if safe:
        with safe_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(safe[0].keys()))
            w.writeheader(); w.writerows(safe)
    if rejected:
        with rej_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rejected[0].keys()))
            w.writeheader(); w.writerows(rejected)
    print(f"{path.name}: {len(safe)} safe, {len(rejected)} rejected")
    return safe, rejected

if __name__ == "__main__":
    for p in sys.argv[1:]:
        filter_file(Path(p))
