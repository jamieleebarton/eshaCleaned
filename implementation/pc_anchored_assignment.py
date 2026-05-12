"""Pass M — PC-anchored candidate pool architecture.

Hypothesis (verified on this dataset):
  84% of ESHA codes with trusted product mappings have >= 70% PC dominance.
  Each ESHA code structurally belongs to 1-3 canonical branded_food_categories.

So an ESHA code like 3759 "Adam's Apple, sections, fresh" has canonical PC =
"Pre-Packaged Fruit & Vegetables". Products in PC = "Chewing Gum & Mints" should
NOT be able to match it, regardless of token overlap on "apple". Period.

This module computes:
  esha_canonical_pcs[code] -> list[(pc_name, share)]   (top 1-3 PCs per ESHA)
  pc_candidate_pool[pc_name] -> set[esha_code]         (inverse, the candidate pool)

For ESHAs with no trusted rows (about 60% of all codes in the augmented graph),
canonical PC is derived from the ESHA description's family + form tokens.

The matcher's score_candidate then operates on candidates from the PC pool ONLY,
falling back to family-based pool only if the PC pool is empty (rare new PCs).

This is the structural fix. PC = partition. Ingredients/tokens = discriminator
within the partition.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent

# Minimum trusted-row support to count an ESHA's PC mapping as "canonical"
MIN_PC_SUPPORT = 5
# Top-N PCs per ESHA: even multi-PC ESHAs cap at 3 most-common PCs
MAX_PCS_PER_ESHA = 3
# A PC is "canonical" for an ESHA if its share among trusted products is >= this
CANONICAL_PC_MIN_SHARE = 0.10  # very permissive; 10% of products from this PC -> include


# ---------------------------------------------------------------------------
# DERIVED PC for ESHAs with no trusted rows
#
# When an ESHA has zero (or too few) trusted products mapping to it, we derive
# its canonical PC from the description. Map family + form tokens -> likely PC.
#
# This is the seed map for codes like "Almond Butter, crunchy with flaxseed"
# (newly augmented from esha_cleaned.csv) that no product has yet landed on.
# ---------------------------------------------------------------------------

# Family -> default PC. Coarse but always available as fallback.
FAMILY_DEFAULT_PC = {
    "milk":          "Milk",
    "plant_milk":    "Plant Based Milks",
    "cream":         "Cream/Cream Substitutes",
    "cheese":        "Cheese",
    "yogurt":        "Yogurt",
    "butter":        "Butter & Margarine",
    "nut_butter":    "Nut & Seed Butters",
    "fruit":         "Pre-Packaged Fruit & Vegetables",
    "vegetable":     "Pre-Packaged Fruit & Vegetables",
    "legume":        "Canned Vegetables",
    "nut_seed":      "Popcorn, Peanuts, Seeds & Related Snacks",
    "grain":         "Cereal",
    "meat":          "Pre-Packaged Meat",
    "poultry":       "Pre-Packaged Meat",
    "seafood":       "Pre-Packaged Seafood",
    "egg":           "Eggs",
    "beverage":      "Non Alcoholic Beverages  Ready to Drink",
    "spice":         "Herbs & Spices",
    "condiment":     "Condiments",
    "soup":          "Canned Soup",
    "dessert_snack": "Confectionery Products",
    "sweetener":     "Granulated, Brown & Powdered Sugar",
    "oil":           "Oils",
    "prepared_food": "Frozen Dinners & Entrees",
    "infant_formula": "Baby/Infant Foods/Beverages",
}

# Description-form-token overrides. If the ESHA description matches these
# patterns, we override the family-default PC with a more specific one.
DESCRIPTION_PC_OVERRIDES = [
    # (regex, override_pc)
    (re.compile(r"\bjuice\b", re.I),                     "Fruit & Vegetable Juice, Nectars & Fruit Drinks"),
    (re.compile(r"\bsoup\b|\bbroth\b|\bbouillon\b", re.I), "Canned Soup"),
    (re.compile(r"\bcondensed\b.*\bsoup\b", re.I),       "Canned Condensed Soup"),
    (re.compile(r"\bgum\b", re.I),                       "Chewing Gum & Mints"),
    (re.compile(r"\bmint(s)?\b.*\bcandy\b|\bcandy\b.*\bmint(s)?\b", re.I), "Chewing Gum & Mints"),
    (re.compile(r"\bcandy\b", re.I),                     "Candy"),
    (re.compile(r"\bchocolate\s+bar\b|\bchocolate,?\s+bar\b", re.I), "Chocolate"),
    (re.compile(r"\bcookie(s)?\b|\bbiscuit(s)?\b", re.I), "Cookies & Biscuits"),
    (re.compile(r"\bcake\b|\bcupcake\b|\bmuffin\b|\bbrownie\b", re.I), "Cakes, Cupcakes, Snack Cakes"),
    (re.compile(r"\bpie\b|\bpastry\b|\bdanish\b|\bturnover\b|\bstrudel\b", re.I), "Pies/Pastries"),
    (re.compile(r"\bpie\s+filling\b|\bfruit\s+filling\b", re.I), "Pastry Shells & Fillings"),
    (re.compile(r"\bcracker(s)?\b|\bbiscotti\b|\bflatbread\b", re.I), "Crackers & Biscotti"),
    (re.compile(r"\bsoda\b|\bcola\b|\bcarbonated\b", re.I), "Soda"),
    (re.compile(r"\bbeer\b|\blager\b|\bale\b", re.I),    "Beer"),
    (re.compile(r"\bwine\b", re.I),                      "Wine"),
    (re.compile(r"\bcoffee\b", re.I),                    "Coffee"),
    (re.compile(r"\btea\b", re.I),                       "Tea"),
    (re.compile(r"\bwater\b", re.I),                     "Water"),
    (re.compile(r"\bcereal\b", re.I),                    "Cereal"),
    (re.compile(r"\bgranola\b|\boatmeal\b", re.I),       "Cereal"),
    (re.compile(r"\bbar(s)?,?\s+granola\b|\bgranola\s+bar(s)?\b", re.I), "Cereal Bars & Granola Bars"),
    (re.compile(r"\bbar(s)?,?\s+(snack|energy)\b", re.I), "Snack, Energy & Granola Bars"),
    (re.compile(r"\byogurt\b", re.I),                    "Yogurt"),
    (re.compile(r"\bice\s+cream\b|\bfrozen\s+yogurt\b", re.I), "Ice Cream & Frozen Yogurt"),
    (re.compile(r"\bsorbet\b|\bsherbet\b", re.I),        "Frozen Desserts & Toppings"),
    (re.compile(r"\bpizza\b", re.I),                     "Frozen Pizza"),
    (re.compile(r"\bstuffing\b", re.I),                  "Stuffing"),
    (re.compile(r"\bsalsa\b|\bdip\b", re.I),             "Dips & Salsa"),
    (re.compile(r"\bsauce\b.*\bpasta\b|\bpasta\s+sauce\b", re.I), "Prepared Pasta & Pizza Sauces"),
    (re.compile(r"\bketchup\b|\bmustard\b|\bmayo\b|\bmayonnaise\b", re.I), "Condiments"),
    (re.compile(r"\bdressing\b|\bvinaigrette\b", re.I),  "Salad Dressing & Mayonnaise"),
    (re.compile(r"\bcanned\b.*\bvegetable(s)?\b|\bvegetable(s)?,?\s+canned\b", re.I), "Canned Vegetables"),
    (re.compile(r"\bfrozen\b.*\bvegetable(s)?\b", re.I), "Frozen Vegetables"),
    (re.compile(r"\bfresh\b.*\b(apple|orange|banana|berry|grape|pear|peach|plum|melon)\b", re.I), "Pre-Packaged Fruit & Vegetables"),
    (re.compile(r"\bfresh\b.*\b(carrot|broccoli|spinach|lettuce|tomato|cucumber|onion|pepper)\b", re.I), "Pre-Packaged Fruit & Vegetables"),
    (re.compile(r"\bdried\b.*\bfruit\b", re.I),          "Dried Fruit"),
    (re.compile(r"\bjam\b|\bjelly\b|\bpreserve(s)?\b|\bmarmalade\b", re.I), "Jam, Jelly & Preserves"),
    (re.compile(r"\bsyrup\b", re.I),                     "Syrup, Honey, Sugar Substitutes"),
    (re.compile(r"\bhoney\b", re.I),                     "Syrup, Honey, Sugar Substitutes"),
    (re.compile(r"\boil\b", re.I),                       "Oils"),
    (re.compile(r"\bvinegar\b", re.I),                   "Cooking Wines & Vinegars"),
    (re.compile(r"\bnut\s+butter\b|\bbutter,?\s+(almond|peanut|cashew|hazelnut|sunflower)\b", re.I), "Nut & Seed Butters"),
    (re.compile(r"\bnut(s)?,?\s+(almond|peanut|cashew|walnut|pecan|hazelnut|pistachio)\b", re.I), "Popcorn, Peanuts, Seeds & Related Snacks"),
    (re.compile(r"\b(almond|peanut|cashew|walnut|pecan|pistachio)(s)?,?\s+(roasted|raw|whole|sliced|slivered|salted|smoked)\b", re.I), "Popcorn, Peanuts, Seeds & Related Snacks"),
    (re.compile(r"\btrail\s+mix\b|\bsnack\s+mix\b|\bnut\s+mix\b", re.I), "Popcorn, Peanuts, Seeds & Related Snacks"),
    (re.compile(r"\bjerky\b", re.I),                     "Jerky & Meat Snacks"),
    (re.compile(r"\bmilk\b,?\s*chocolate\b|\bchocolate\b\s+milk\b", re.I), "Milk"),
    (re.compile(r"\balmond\s+milk\b|\bsoy\s+milk\b|\bcoconut\s+milk\b|\boat\s+milk\b|\brice\s+milk\b", re.I), "Plant Based Milks"),
    (re.compile(r"\bbutter\b", re.I),                    "Butter & Margarine"),
    (re.compile(r"\bcheese\b", re.I),                    "Cheese"),
    (re.compile(r"\bmacaroni\s+(and|&)\s+cheese\b", re.I), "Other Deli"),
    (re.compile(r"\bsalad\b.*\b(macaroni|pasta|potato|cole\s*slaw)\b", re.I), "Other Deli"),
    (re.compile(r"\bbread\b|\bbun\b|\broll\b|\btortilla\b|\bbagel\b", re.I), "Breads & Buns"),
    (re.compile(r"\bpasta\b|\bnoodle\b|\bspaghetti\b|\bmacaroni\b", re.I), "Pasta by Shape & Type"),
    (re.compile(r"\brice\b", re.I),                      "Rice"),
    (re.compile(r"\bquinoa\b|\bbarley\b|\boat(s)?\b|\bcouscous\b", re.I), "Grains"),
    (re.compile(r"\bbean(s)?,?\s+(refried|black|pinto|kidney|navy)\b", re.I), "Canned Vegetables"),
    (re.compile(r"\bhummus\b", re.I),                    "Dips & Salsa"),
    (re.compile(r"\bguacamole\b", re.I),                 "Dips & Salsa"),
]


def derive_canonical_pc(esha_description: str, family: str | None) -> str | None:
    """Derive a likely canonical PC for an ESHA from its description + family.

    Used as fallback when an ESHA has no trusted-row product mappings.
    """
    if not esha_description:
        return FAMILY_DEFAULT_PC.get(family or "")
    # Apply description regex overrides first (more specific)
    for pattern, pc in DESCRIPTION_PC_OVERRIDES:
        if pattern.search(esha_description):
            return pc
    # Family default
    return FAMILY_DEFAULT_PC.get(family or "")


# ---------------------------------------------------------------------------
# Loading + computing canonical PCs
# ---------------------------------------------------------------------------


def load_trusted_pc_mappings(legacy_csv_path: Path | str) -> list[tuple[str, str, str, float]]:
    """Read trusted ESHA -> PC observations from the existing legacy/best-map CSV.

    Returns list of (esha_code, branded_food_category, esha_family, score) tuples.
    Filters to assignment_source = legacy_best_map OR fallback_category_family,
    score >= 8 (loose enough to give us coverage).
    """
    out = []
    p = Path(legacy_csv_path)
    if not p.exists():
        return out
    with p.open(newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader((line.replace("\x00", "") for line in fh))
        for row in reader:
            src = (row.get("assignment_source") or "").strip()
            if src not in ("legacy_best_map", "fallback_category_family"):
                continue
            try:
                score = float(row.get("score") or 0.0)
            except ValueError:
                score = 0.0
            if score < 8:
                continue
            code = (row.get("best_esha_code") or "").strip()
            pc = (row.get("branded_food_category") or "").strip()
            fam = (row.get("best_esha_family") or "").strip()
            if code and pc:
                out.append((code, pc, fam, score))
    return out


def compute_canonical_pcs(
    trusted_observations: list[tuple[str, str, str, float]],
    all_esha_codes: list[tuple[str, str, str]],  # (code, description, family)
) -> tuple[dict[str, list[tuple[str, float]]], dict[str, set[str]]]:
    """Compute esha_canonical_pcs and the inverse pc_candidate_pool.

    For ESHAs with sufficient trusted observations, use the actual PC distribution.
    For ESHAs with no/few observations, derive canonical PC from description.

    Returns:
      esha_canonical_pcs: code -> [(pc_name, share), ...] (top up to MAX_PCS_PER_ESHA)
      pc_candidate_pool: pc_name -> set[code]
    """
    # Aggregate PC counts per ESHA from trusted observations
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for code, pc, _fam, _score in trusted_observations:
        counts[code][pc] += 1

    esha_canonical_pcs: dict[str, list[tuple[str, float]]] = {}
    derived_count = 0
    observed_count = 0

    # 1. ESHAs with observations: take top PCs by share
    for code, pc_dict in counts.items():
        total = sum(pc_dict.values())
        if total < MIN_PC_SUPPORT:
            continue  # too few observations, treat as no observations
        sorted_pcs = sorted(pc_dict.items(), key=lambda kv: kv[1], reverse=True)
        canonical = []
        for pc, n in sorted_pcs[:MAX_PCS_PER_ESHA]:
            share = n / total
            if share >= CANONICAL_PC_MIN_SHARE:
                canonical.append((pc, share))
        if canonical:
            esha_canonical_pcs[code] = canonical
            observed_count += 1

    # 2. ESHAs with no/few observations: derive from description
    observed_set = set(esha_canonical_pcs.keys())
    for code, desc, fam in all_esha_codes:
        if code in observed_set:
            continue
        derived_pc = derive_canonical_pc(desc, fam)
        if derived_pc:
            esha_canonical_pcs[code] = [(derived_pc, 1.0)]
            derived_count += 1

    # 3. Build inverse: pc_candidate_pool
    pc_candidate_pool: dict[str, set[str]] = defaultdict(set)
    for code, pcs in esha_canonical_pcs.items():
        for pc, _share in pcs:
            pc_candidate_pool[pc].add(code)

    print(f"[pc_anchored] ESHAs with PC from observations: {observed_count:,}", flush=True)
    print(f"[pc_anchored] ESHAs with PC derived from description: {derived_count:,}", flush=True)
    print(f"[pc_anchored] PCs in candidate pool: {len(pc_candidate_pool):,}", flush=True)
    return esha_canonical_pcs, dict(pc_candidate_pool)


def save_canonical_pcs(
    esha_canonical_pcs: dict[str, list[tuple[str, float]]],
    out_path: Path | str,
) -> None:
    out = {code: [{"pc": pc, "share": share} for pc, share in pcs] for code, pcs in esha_canonical_pcs.items()}
    Path(out_path).write_text(json.dumps(out, sort_keys=True))


def load_canonical_pcs(in_path: Path | str) -> dict[str, list[tuple[str, float]]]:
    p = Path(in_path)
    if not p.exists():
        return {}
    j = json.loads(p.read_text())
    return {code: [(item["pc"], item["share"]) for item in items] for code, items in j.items()}


# ---------------------------------------------------------------------------
# Compatibility: which OTHER PCs can a product in PC=X borrow candidates from?
# ---------------------------------------------------------------------------

# Hand-curated PC compatibility groups. Products in any PC of a group can
# reasonably borrow ESHA candidates from the others. Used as fallback when
# the strict pc_candidate_pool[product.PC] is empty or sparse.
PC_COMPAT_GROUPS = [
    # Soups
    {"Canned Soup", "Canned Condensed Soup", "Other Soups", "Dry Soup, Stock, Broth & Bouillon"},
    # Beverages — non-alcoholic
    {"Fruit & Vegetable Juice, Nectars & Fruit Drinks", "Powdered Drinks", "Iced & Bottle Tea",
     "Iced & Bottled Coffee", "Sport Drinks", "Energy, Protein & Muscle Recovery Drinks",
     "Non Alcoholic Beverages  Ready to Drink", "Other Drinks"},
    # Carbonated beverages
    {"Soda", "Sparkling Water, Seltzer Water, Tonic Water & Carbonated Water"},
    # Water
    {"Water", "Sparkling Water, Seltzer Water, Tonic Water & Carbonated Water"},
    # Fresh produce
    {"Pre-Packaged Fruit & Vegetables", "Fresh Produce"},
    # Snacks - sweet
    {"Confectionery Products", "Candy", "Chocolate", "Cookies & Biscotti", "Cookies & Biscuits",
     "Cakes, Cupcakes, Snack Cakes", "Pies/Pastries", "Cereal Bars & Granola Bars",
     "Snack, Energy & Granola Bars", "Wholesome Snacks", "Frozen Desserts & Toppings",
     "Ice Cream & Frozen Yogurt", "Pies, Pastries, Donuts"},
    # Snacks - savory
    {"Popcorn, Peanuts, Seeds & Related Snacks", "Pretzels & Salty Snacks",
     "Chips, Pretzels & Snacks", "Crackers & Biscotti", "Flavored Snack Crackers",
     "Other Snacks", "Snack Mix, Trail Mix"},
    # Vegetables
    {"Canned Vegetables", "Frozen Vegetables", "Pre-Packaged Fruit & Vegetables", "Fresh Produce"},
    # Meat
    {"Pre-Packaged Meat", "Jerky & Meat Snacks", "Frozen Meat", "Pepperoni, Salami & Cold Cuts"},
    # Dry pasta/noodles. Do not borrow prepared meal or pizza candidates:
    # "Pasta by Shape & Type" is retail dry noodles, not pasta dishes.
    {"Pasta by Shape & Type", "All Noodles"},
    # Prepared Italian/frozen meals stay separate from dry pasta.
    {"Pasta Dinners", "Frozen Dinners & Entrees", "Frozen Appetizers & Hors D'oeuvres"},
    # Bread
    {"Breads & Buns", "Croissants, Sweet Rolls, Muffins & Other Pastries", "Bakery Mixes",
     "Crusts & Dough"},
    # Dairy
    {"Milk", "Plant Based Milks", "Cream/Cream Substitutes", "Milk Additives"},
    # Cheese
    {"Cheese"},
    # Nut/seed butters are spreads, not snack nuts/popcorn.
    {"Nut & Seed Butters"},
    # Sauce/condiment
    {"Condiments", "Salad Dressing & Mayonnaise", "Prepared Pasta & Pizza Sauces",
     "Dips & Salsa", "Pickles, Olives, Peppers & Relishes"},
    # Cereal
    {"Cereal", "Processed Cereal Products", "Cereal Bars & Granola Bars"},
    # Stuffing / sides
    {"Stuffing", "Other Deli", "Side Dishes"},
]


def expand_pc_pool(
    primary_pc: str,
    pc_candidate_pool: dict[str, set[str]],
    *,
    minimum_codes: int = 20,
) -> set[str]:
    """Get candidate ESHA codes for a PC, expanding to compatible PCs only if sparse.

    Returns at least `minimum_codes` candidates if possible, by adding ESHA codes
    from PCs in the same compatibility group. If still sparse, returns whatever
    we have.
    """
    pool = set(pc_candidate_pool.get(primary_pc, set()))
    if len(pool) >= minimum_codes:
        return pool
    # Expand within the compatibility group
    for group in PC_COMPAT_GROUPS:
        if primary_pc in group:
            for sibling_pc in group:
                if sibling_pc != primary_pc:
                    pool.update(pc_candidate_pool.get(sibling_pc, set()))
            break
    return pool
