"""Safety filter v2 for swarm fix proposals."""
import csv, sys
from pathlib import Path

REJECT_PATTERNS = [
    # Cross-category leaks
    ("product_description", "root beer", "proposed_esha_desc", "beer", "reject_rootbeer_to_beer"),
    ("product_description", "ginger beer", "proposed_esha_desc", "beer", "reject_gingerbeer_to_beer"),
    ("proposed_esha_desc", "water, tap", None, None, "reject_tap_water"),
    ("proposed_esha_desc", "tangerines, fresh", None, None, "reject_produce_leak"),
    ("proposed_esha_desc", "carbohydrate gel", None, None, "reject_gel_leak"),
    # Frozen vegetables -> canned is nutritionally wrong
    ("branded_food_category", "frozen vegetables", "proposed_esha_desc", "canned", "reject_frozen_to_canned"),
    ("branded_food_category", "frozen vegetables", "proposed_esha_desc", "sprouts", "reject_frozen_to_sprouts"),
    # Vinaigrette flattening
    ("product_description", "vinaigrette", "proposed_esha_desc", "balsamic", "reject_vinaigrette_flatten"),
    ("product_description", "vinaigrette", "proposed_esha_desc", "balsamic", "reject_vinaigrette_flatten"),
    # Mayo flattening
    ("product_description", "light mayonnaise", "proposed_esha_desc", "mayonnaise", "reject_mayo_flatten"),
    ("product_description", "fat free mayonnaise", "proposed_esha_desc", "mayonnaise", "reject_mayo_flatten"),
    ("product_description", "real mayonnaise", "proposed_esha_desc", "mayonnaise", "reject_mayo_flatten"),
    ("product_description", "honey mustard mayonnaise", "proposed_esha_desc", "mayonnaise", "reject_mayo_flatten"),
    ("product_description", "chipotle mayonnaise", "proposed_esha_desc", "mayonnaise", "reject_mayo_flatten"),
    # Nut/seed -> vegetable
    ("product_description", "peanut", "proposed_esha_desc", "squash", "reject_nut_to_veg"),
    ("product_description", "almond", "proposed_esha_desc", "squash", "reject_nut_to_veg"),
    ("product_description", "cashew", "proposed_esha_desc", "squash", "reject_nut_to_veg"),
    ("product_description", "walnut", "proposed_esha_desc", "squash", "reject_nut_to_veg"),
    ("product_description", "pecan", "proposed_esha_desc", "squash", "reject_nut_to_veg"),
    ("product_description", "pistachio", "proposed_esha_desc", "squash", "reject_nut_to_veg"),
    ("product_description", "seed", "proposed_esha_desc", "squash", "reject_seed_to_veg"),
    # Dressing -> oil / glaze
    ("product_description", "balsamic glaze", "proposed_esha_desc", "barbecue", "reject_glaze_misroute"),
    ("product_description", "poppyseed", "proposed_esha_desc", "oil", "reject_poppy_to_oil"),
    # Chocolate category -> milk leaks (milk chocolate is still chocolate, not dairy milk)
    ("branded_food_category", "chocolate", "proposed_esha_desc", "milk, chocolate", "reject_choc_to_milk"),
    # Cookie/biscuit mismatches
    ("product_description", "pumpkin spice", "proposed_esha_desc", "pumpkin flowers", "reject_pumpkin_mismatch"),
    ("product_description", "ladyfinger", "proposed_esha_desc", "m m", "reject_ladyfinger_mismatch"),
    ("product_description", "ginger snap", "proposed_esha_desc", "bar, snack", "reject_gingersnap_downgrade"),
    ("product_description", "meringue", "proposed_esha_desc", "yogurt", "reject_meringue_mismatch"),
    # Bread mismatches
    ("product_description", "bratwurst bun", "proposed_esha_desc", "sausage", "reject_bun_to_sausage"),
    ("product_description", "ciabatta", "proposed_esha_desc", "8-grain", "reject_ciabatta_mismatch"),
    ("product_description", "muffin", "proposed_esha_desc", "corn", "reject_muffin_to_corn"),
    ("product_description", "baguette", "proposed_esha_desc", "baby", "reject_baguette_to_baby"),
    # Chip downgrades
    ("product_description", "blue corn", "proposed_esha_desc", "chips, tortilla", "reject_bluecorn_downgrade"),
    # Cookie mismatches
    ("product_description", "chocolate chip", "proposed_esha_desc", "cannoli", "reject_cookie_to_cannoli"),
    ("product_description", "sandwich cookies", "proposed_esha_desc", "sugar sodium free", "reject_sandwich_to_specific"),
    # Chip mismatches
    ("branded_food_category", "chips, pretzels & snacks", "proposed_esha_desc", "vegetables, canned", "reject_chip_to_veg"),
    # Chocolate mismatches
    ("product_description", "truffle", "proposed_esha_desc", "bar, chocolate", "reject_truffle_to_bar"),
    ("product_description", "frosty", "proposed_esha_desc", "frozen dessert", "reject_frosty"),
    # Bread mismatches
    ("product_description", "brioche", "proposed_esha_desc", "8-grain", "reject_brioche_mismatch"),
    ("product_description", "brioche", "proposed_esha_desc", "7 grain", "reject_brioche_mismatch"),
    ("product_description", "ciabatta", "proposed_esha_desc", "white", "reject_ciabatta_to_white"),
]

# Proposed descriptions that are too generic for their categories
TOO_GENERIC = {
    "cookies_biscuits": {"chips", "bar, chocolate"},
    "chips_pretzels_snacks": {"chips", "vegetables, canned"},
    "chocolate": {"bar, chocolate", "frozen dessert"},
}

def is_too_generic(row):
    prop = (row.get("proposed_esha_desc") or "").lower().strip()
    cat = slugify(row.get("branded_food_category", ""))
    generics = TOO_GENERIC.get(cat, set())
    for g in generics:
        if prop == g:
            return f"reject_too_generic:{g}"
    return None

def slugify(t): return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")

def is_noop(row):
    return row.get("current_esha_code","").strip() == row.get("proposed_esha_code","").strip()

def is_rejected(row):
    if is_noop(row):
        return "reject_noop"
    for f1, p1, f2, p2, reason in REJECT_PATTERNS:
        v1 = (row.get(f1) or "").lower()
        if p1 and p1 not in v1:
            continue
        if f2:
            v2 = (row.get(f2) or "").lower()
            if p2 and p2 not in v2:
                continue
        # Special: root beer check - make sure it's not "root beer" product
        if reason == "reject_rootbeer_to_beer" and "root beer" in v1:
            return reason
        if reason == "reject_gingerbeer_to_beer" and "ginger beer" in v1:
            return reason
        if reason in ("reject_rootbeer_to_beer", "reject_gingerbeer_to_beer"):
            continue
        return reason
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
    base = path.stem.replace("_safe","").replace("_rejected","")
    orig = path.with_name(f"{base}.csv")
    safe_path = orig.with_name(f"{base}_safe.csv")
    rej_path = orig.with_name(f"{base}_rejected.csv")
    if safe:
        with safe_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(safe[0].keys()))
            w.writeheader(); w.writerows(safe)
    if rejected:
        with rej_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rejected[0].keys()))
            w.writeheader(); w.writerows(rejected)
    print(f"{orig.name}: {len(safe)} safe, {len(rejected)} rejected")
    return safe, rejected

if __name__ == "__main__":
    for p in sys.argv[1:]:
        filter_file(Path(p))
