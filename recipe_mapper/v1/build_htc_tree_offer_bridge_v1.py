#!/usr/bin/env python3
"""Build an HTC/tree-first recipe ingredient -> store offer bridge.

Inputs are the explicit artifacts from build_htc_coded_inputs_v1.py.  This
script does not read learned contracts or old forbidden-term rows.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from htc_tree_core_v1 import (  # noqa: E402
    PACKAGING_NOISE,
    htc_compatible,
    identity_tokens,
    normalize_key,
    normalize_surface,
    title_noise_tokens,
)

csv.field_size_limit(sys.maxsize)

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "output"
DEFAULT_RECIPE = OUT_DIR / "htc_coded_recipe_ingredients_v1.csv"
DEFAULT_PRODUCTS = OUT_DIR / "htc_coded_store_products_v1.csv"
OUT_BRIDGE = OUT_DIR / "htc_tree_offer_bridge_v1.csv"
OUT_SUMMARY = OUT_DIR / "htc_tree_offer_bridge_v1_summary.json"

STORE_SCOPES = ("all", "kroger", "walmart")

COMPOSITE_NOISE_BY_GROUP = {
    "7": re.compile(r"\b(chocolate|candy|loaf|bread|muffin|cake|pie|smoothie|smoothies|baby|toddler|puree|pouch|yogurt|juice|cereal|chips?|snack|snaps?|crispy|bar|liqueur|liquor|wine|beer|cocktail)\b", re.I),
    "A": re.compile(r"\b(chocolate|candy|salad topper|trail mix|snack mix|cranberries|raisins|bar|cereal|cookie|cake|oats?|granola|bunches)\b", re.I),
    "E": re.compile(r"\b(cereal|cheerios|toast crunch|toaster|cookie|cake|candy|gum|mouthwash|toothpaste|hair|scalp|oil|meal|meatloaf|dessert|biscuit|biscuits|donut|donuts|donettes|fritter|flavored|sazon|candle|candles|fragrance)\b", re.I),
    "5": re.compile(r"\b(easter|chocolate|candy|egg noodle|noodle|vegan|free from eggs|egg[-\s]*free|plant[-\s]*based|replacer|substitute)\b", re.I),
}

PLAIN_FORM_BLOCKERS = re.compile(r"\b(loaf|muffin|cake|cookie|candy|chocolate|smoothie|smoothies|juice|puree|pouch|baby|toddler|cereal|snaps?|crispy|chips?|snack|seasoning|dip|sauce|salsa|dressing|mix|freeze[-\s]*dried|dried|frozen|can|canned|jar|jarred|pickled|liqueur|liquor|cocktail)\b", re.I)
BUTTER_FLAVOR_TEXT_RE = re.compile(r"\b(biscuit|biscuits|cookie|cookies|ice cream|popcorn|flavor(?:ed)?|tastin|spray|cracker|crackers|syrup|syurp|pasta|fettuccine|sides?|herb|spread|spreadable|olive oil|pecan|honey|croissant|loaf)\b", re.I)
INHERENT_DRIED_FRUIT_RE = re.compile(r"\b(raisins?|currants?|prunes?|dates?|sultanas?|dried\s+(?:apricots?|figs?|cherries?|cranberries?|mango(?:es)?|pineapples?|blueberries?))\b", re.I)
TITLE_INDEX_STOP = PACKAGING_NOISE | {
    "added", "all", "classic", "free", "fresh", "gluten", "kosher",
    "natural", "organic", "original", "pure", "real", "style",
}
SPECIFIC_ITEM_STOP = {
    "all", "black", "brown", "coarse", "fine", "fresh", "golden", "green",
    "ground", "large", "medium", "orange", "plain", "powder", "red", "ripe",
    "seed", "small", "sweet", "white", "whole", "yellow",
}

CHILI_PEPPER_VARIETY_KEYS = {
    "anaheim pepper",
    "chili pepper",
    "fresno chili pepper",
    "fresno pepper",
    "habanero pepper",
    "jalapeno pepper",
    "poblano pepper",
    "serrano pepper",
}

GENERIC_SPICE_PID_KEYS = {"seasoning", "spice blend", "seeds"}
SPICE_MODIFIER_FORM_WORDS = {
    "ground", "powder", "powdered", "seed", "seeds", "whole", "plain",
}
SPICE_BEVERAGE_NOISE_RE = re.compile(
    r"\b(beverage|coffee|drink|immune|kombucha|sleep|smoothie|soda|supplement|tea)\b",
    re.I,
)
RETAIL_NON_FOOD_CATEGORY_RE = re.compile(
    r"\b(beauty|body\s+wash|conditioner|cosmetic|garden|hair|home\s+improvement|"
    r"household|lipstick|live\s+plants?|lotion|patio|personal\s+care|plumbing|"
    r"shampoo|soap|toothpaste|water\s+filtration|water\s+softener)\b",
    re.I,
)


@dataclass(frozen=True)
class ProductOffer:
    source: str
    rowid: str
    upc: str
    name: str
    brand: str
    grams: float
    cents: int
    cpg: float
    category_path: str
    category_path_walmart: str
    tree_product_identity: str
    tree_canonical_path: str
    tree_modifier: str
    taxonomy_status: str
    htc_code: str
    htc_group: str
    htc_family: str
    htc_form: str
    htc_processing: str
    htc_ptype: str
    tree_authority: str
    title_terms_set: frozenset[str]

    @property
    def pid_key(self) -> str:
        return normalize_key(self.tree_product_identity)

    @property
    def modifier_key(self) -> str:
        return normalize_key(self.tree_modifier)

    @property
    def canonical_key(self) -> str:
        return normalize_surface(self.tree_canonical_path)

    @property
    def title_terms(self) -> set[str]:
        return set(self.title_terms_set)


def floatish(value: object) -> float:
    try:
        return float(str(value or "0"))
    except ValueError:
        return 0.0


def intish(value: object) -> int:
    try:
        return int(float(str(value or "0")))
    except ValueError:
        return 0


def load_recipe_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        return list(csv.DictReader(handle))


def load_products(path: Path) -> list[ProductOffer]:
    out: list[ProductOffer] = []
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            grams = floatish(row.get("grams"))
            cents = intish(row.get("cents"))
            if grams <= 0 or cents <= 0:
                continue
            if row.get("available") not in {"", "1"}:
                continue
            if row.get("marketplace") == "1":
                continue
            if row.get("htc_group") in {"", "0", "N"}:
                continue
            product_category_lc = normalize_surface(" ".join([
                row.get("category_path") or "",
                row.get("category_path_walmart") or "",
            ]))
            if RETAIL_NON_FOOD_CATEGORY_RE.search(product_category_lc):
                continue
            if not row.get("tree_product_identity") or not row.get("tree_canonical_path"):
                continue
            if (row.get("taxonomy_status") or "").startswith("reject"):
                continue
            out.append(ProductOffer(
                source=row.get("source") or "",
                rowid=row.get("rowid") or "",
                upc=row.get("upc") or f"rowid:{row.get('rowid') or ''}",
                name=row.get("name") or "",
                brand=row.get("brand") or "",
                grams=grams,
                cents=cents,
                cpg=cents / grams,
                category_path=row.get("category_path") or "",
                category_path_walmart=row.get("category_path_walmart") or "",
                tree_product_identity=row.get("tree_product_identity") or "",
                tree_canonical_path=row.get("tree_canonical_path") or "",
                tree_modifier=row.get("tree_modifier") or "",
                taxonomy_status=row.get("taxonomy_status") or "",
                htc_code=row.get("htc_code") or "",
                htc_group=row.get("htc_group") or "",
                htc_family=row.get("htc_family") or "",
                htc_form=row.get("htc_form") or "",
                htc_processing=row.get("htc_processing") or "",
                htc_ptype=row.get("htc_ptype") or "",
                tree_authority=row.get("tree_authority") or "",
                title_terms_set=frozenset(identity_tokens(row.get("name") or "")),
            ))
    return out


@dataclass
class ProductIndex:
    products: list[ProductOffer]
    by_pid: dict[tuple[str, str], list[int]]
    by_modifier: dict[tuple[str, str], list[int]]
    by_canonical: dict[tuple[str, str], list[int]]
    by_title_term: dict[tuple[str, str], list[int]]
    by_group_family: dict[tuple[str, str, str], list[int]]
    by_group: dict[tuple[str, str], list[int]]


def scopes_for(source: str) -> tuple[str, ...]:
    return ("all", source) if source in {"kroger", "walmart"} else ("all",)


def build_index(products: list[ProductOffer]) -> ProductIndex:
    by_pid: dict[tuple[str, str], list[int]] = defaultdict(list)
    by_modifier: dict[tuple[str, str], list[int]] = defaultdict(list)
    by_canonical: dict[tuple[str, str], list[int]] = defaultdict(list)
    by_title_term: dict[tuple[str, str], list[int]] = defaultdict(list)
    by_group_family: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    by_group: dict[tuple[str, str], list[int]] = defaultdict(list)
    for idx, product in enumerate(products):
        indexed_terms = product.title_terms | identity_tokens(product.tree_product_identity) | identity_tokens(product.tree_modifier)
        for scope in scopes_for(product.source):
            by_pid[(scope, product.pid_key)].append(idx)
            if product.modifier_key:
                by_modifier[(scope, product.modifier_key)].append(idx)
            by_canonical[(scope, product.canonical_key)].append(idx)
            for term in indexed_terms - TITLE_INDEX_STOP:
                by_title_term[(scope, term)].append(idx)
            by_group_family[(scope, product.htc_group, product.htc_family)].append(idx)
            by_group[(scope, product.htc_group)].append(idx)
    for bucket in (
        list(by_pid.values())
        + list(by_modifier.values())
        + list(by_canonical.values())
        + list(by_title_term.values())
        + list(by_group_family.values())
        + list(by_group.values())
    ):
        bucket.sort(key=lambda idx: (products[idx].cpg, products[idx].cents))
    return ProductIndex(products, by_pid, by_modifier, by_canonical, by_title_term, by_group_family, by_group)


def recipe_terms(row: dict[str, str]) -> set[str]:
    return identity_tokens(" ".join([
        row.get("ingredient_item") or "",
        row.get("tree_product_identity") or "",
        row.get("tree_modifier") or "",
    ]))


def spice_family_bridge_allowed(row: dict[str, str], product: ProductOffer) -> bool:
    """Allow generic spice-blend recipe slots to land on specific spice leaves.

    Taxonomy-v2 can encode recipe rows like "cumin seeds" as a generic
    Spice Blend family with `tree_modifier=Cumin`, while retail products often
    sit on specific leaves such as Cumin Seed.  The family mismatch is safe only
    when the modifier terms are present in the product title/tree and the
    product is still in the spices taxonomy.
    """
    if (row.get("htc_group") or "") != "E" or product.htc_group != "E":
        return False
    recipe_pid_key = normalize_key(row.get("tree_product_identity") or "")
    recipe_mod_key = normalize_key(row.get("tree_modifier") or "")
    if recipe_pid_key not in GENERIC_SPICE_PID_KEYS or not recipe_mod_key:
        return False
    modifier_terms = identity_tokens(recipe_mod_key) - SPICE_MODIFIER_FORM_WORDS
    if not modifier_terms:
        return False
    product_terms = product.title_terms | identity_tokens(product.tree_product_identity) | identity_tokens(product.tree_modifier)
    return (
        modifier_terms <= product_terms
        and "spices seasonings" in normalize_surface(product.tree_canonical_path)
    )


def canonical_related(recipe_path: str, product_path: str) -> bool:
    rp = normalize_surface(recipe_path)
    pp = normalize_surface(product_path)
    rp_compact = rp.replace(" ", "")
    pp_compact = pp.replace(" ", "")
    return bool(
        rp and pp and (
            rp == pp
            or rp_compact == pp_compact
            or rp.startswith(pp + " ")
            or pp.startswith(rp + " ")
        )
    )


def keys_related(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left == right or left.replace(" ", "") == right.replace(" ", "")


def product_matches_recipe(row: dict[str, str], product: ProductOffer) -> tuple[bool, float, str]:
    recipe_group = row.get("htc_group") or ""
    recipe_family = row.get("htc_family") or ""
    if not htc_compatible(recipe_group, recipe_family, product.htc_group, product.htc_family) and not spice_family_bridge_allowed(row, product):
        return False, 0.0, "htc_mismatch"

    item = row.get("ingredient_item") or ""
    item_lc = normalize_surface(item)
    terms = recipe_terms(row)
    recipe_pid_key = normalize_key(row.get("tree_product_identity") or "")
    recipe_mod_key = normalize_key(row.get("tree_modifier") or "")
    recipe_path = row.get("tree_canonical_path") or ""
    title_lc = normalize_surface(product.name)
    product_identity_terms = product.title_terms | identity_tokens(product.tree_product_identity) | identity_tokens(product.tree_modifier)
    specific_item_terms = identity_tokens(item) - SPECIFIC_ITEM_STOP
    if specific_item_terms and not (specific_item_terms & product_identity_terms):
        return False, 0.0, "specific_term_missing"
    if "zest" in item_lc and "zest" not in product_identity_terms:
        return False, 0.0, "zest_mismatch"
    if "seed" in item_lc and re.search(r"\b(ground|powder|blend|seasoning|curry|masala)\b", title_lc):
        if not re.search(r"\b(ground|powder|blend|seasoning|curry|masala)\b", item_lc):
            return False, 0.0, "seed_form_mismatch"
    if "ground" in item_lc:
        powder_names_identity = any(
            re.search(rf"\b{re.escape(term)}\s+powder(?:ed)?\b|\bpowder(?:ed)?\s+{re.escape(term)}\b", title_lc)
            for term in specific_item_terms
        )
        if not re.search(r"\bground\b", title_lc) and not powder_names_identity:
            return False, 0.0, "ground_form_mismatch"
    if "fresh ginger" in item_lc:
        if re.search(r"\b(sushi|pickled|juice|drink|boost|shot|tea|soda|dressing|sauce|snack|candy|cookie|cake)\b", title_lc):
            return False, 0.0, "fresh_spice_form_mismatch"
        if not product.tree_canonical_path.startswith("Produce >") and not re.search(r"\b(fresh|root|whole|minced|paste|crushed|grated)\b", title_lc):
            return False, 0.0, "fresh_spice_form_mismatch"
    if recipe_group == "E":
        product_category_lc = normalize_surface(" ".join([product.category_path, product.category_path_walmart]))
        if SPICE_BEVERAGE_NOISE_RE.search(f"{title_lc} {product_category_lc}"):
            return False, 0.0, "spice_beverage_product"

    score = 0.0
    reasons: list[str] = ["htc"]
    recipe_htc_code = (row.get("htc_code") or "")[:8]
    product_htc_code = (product.htc_code or "")[:8]
    if recipe_htc_code and product_htc_code and recipe_htc_code == product_htc_code:
        score += 40.0
        reasons.append("exact_htc")

    pid_related = keys_related(recipe_pid_key, product.pid_key)
    mod_related = keys_related(recipe_mod_key, product.modifier_key)
    breadcrumb_title_anchor = (
        recipe_pid_key in {"breadcrumb", "breadcrumbs", "bread crumb", "bread crumbs"}
        and {"bread", "crumb"} <= product.title_terms
    )
    cream_title_anchor = (
        recipe_pid_key == "heavy cream"
        and {"heavy", "cream"} <= product.title_terms
        and ("whipping" in product.title_terms or product.pid_key == "cream")
    )
    green_onion_title_anchor = (
        recipe_pid_key == "green onion"
        and {"green", "onion"} <= product.title_terms
        and product.pid_key == "onion"
        and product.tree_canonical_path.startswith("Produce > Vegetables > Onions")
    )
    recipe_modifier_terms = identity_tokens(recipe_mod_key) - SPICE_MODIFIER_FORM_WORDS
    generic_spice_modifier_anchor = (
        recipe_pid_key in GENERIC_SPICE_PID_KEYS
        and recipe_mod_key
        and (
            keys_related(recipe_mod_key, product.pid_key)
            or (
                recipe_modifier_terms
                and recipe_modifier_terms <= product_identity_terms
                and "spices seasonings" in normalize_surface(product.tree_canonical_path)
            )
        )
    )
    if recipe_pid_key == "heavy cream" and re.search(r"\b(dairy[-\s]*free|alternative|plant[-\s]*based)\b", title_lc):
        return False, 0.0, "cream_substitute"

    if recipe_pid_key and pid_related:
        score += 120.0
        reasons.append("pid")
    if recipe_mod_key and mod_related:
        score += 90.0
        reasons.append("modifier")
    if recipe_path and canonical_related(recipe_path, product.tree_canonical_path):
        score += 70.0
        reasons.append("canonical")
    if breadcrumb_title_anchor:
        score += 105.0
        reasons.append("breadcrumb_title")
    if cream_title_anchor:
        score += 110.0
        reasons.append("cream_title")
    if green_onion_title_anchor:
        score += 115.0
        reasons.append("green_onion_title")
    if generic_spice_modifier_anchor:
        score += 105.0
        reasons.append("spice_modifier_anchor")
    if specific_item_terms and specific_item_terms <= product_identity_terms:
        score += 45.0
        reasons.append("specific_terms")
    if terms and terms <= product.title_terms:
        score += 60.0
        reasons.append("title_terms")
    elif terms and terms & product.title_terms:
        score += 15.0 * len(terms & product.title_terms)
        reasons.append("title_overlap")

    # Parent baking-extract rows are acceptable for Vanilla Extract when title
    # carries the actual identity.
    if recipe_pid_key == "vanilla extract" and product.pid_key == "extract" and {"vanilla", "extract"} <= product.title_terms:
        score += 120.0
        reasons.append("extract_parent")
    if recipe_pid_key == "chili pepper" and product.pid_key in CHILI_PEPPER_VARIETY_KEYS:
        score += 115.0
        reasons.append("pepper_variety")

    if not reasons or score <= 0:
        return False, 0.0, "identity_mismatch"

    has_tree_anchor = (
        (recipe_pid_key and pid_related)
        or (recipe_mod_key and mod_related)
        or (recipe_path and canonical_related(recipe_path, product.tree_canonical_path))
        or breadcrumb_title_anchor
        or cream_title_anchor
        or green_onion_title_anchor
        or generic_spice_modifier_anchor
        or "extract_parent" in reasons
        or "pepper_variety" in reasons
    )
    if recipe_pid_key and product.pid_key and not pid_related and not has_tree_anchor:
        return False, 0.0, "tree_identity_conflict"

    # Plain fresh produce should not become dessert/baby/juice products.
    recipe_path_lc = normalize_surface(recipe_path)
    recipe_is_plain_fresh_produce = (
        recipe_group in {"6", "7"}
        and not any(term in item_lc for term in ("frozen", "canned", "dried", "dry"))
        and not INHERENT_DRIED_FRUIT_RE.search(item_lc)
        and (not recipe_path_lc or recipe_path_lc.startswith("produce "))
    )
    if recipe_is_plain_fresh_produce:
        product_category_lc = normalize_surface(" ".join([product.category_path, product.category_path_walmart]))
        if (
            PLAIN_FORM_BLOCKERS.search(product.name)
            or "canned packaged" in product_category_lc
            or product_category_lc.startswith("canned")
        ):
            return False, 0.0, "plain_produce_composite"
        if not product.tree_canonical_path.startswith("Produce >"):
            return False, 0.0, "plain_produce_nonfresh_path"
        if product.tree_canonical_path.startswith("Produce >"):
            score += 35.0
            reasons.append("produce_preferred")

    noise_re = COMPOSITE_NOISE_BY_GROUP.get(recipe_group)
    if noise_re and noise_re.search(product.name):
        # Keep true spice products like "Ground Cinnamon"; reject cereal/candy
        # style products whose tree identity is not the requested concept.
        if recipe_group in {"5", "7", "A", "E"}:
            return False, 0.0, "composite_noise"
        if not (recipe_pid_key and pid_related) and not (recipe_mod_key and mod_related):
            return False, 0.0, "composite_noise"

    if recipe_group == "1" and row.get("htc_family") == "4" and BUTTER_FLAVOR_TEXT_RE.search(product.name):
        return False, 0.0, "butter_flavor_text"

    if recipe_group == "E" and recipe_family == "3" and "fresh" in item_lc and "herb" not in normalize_surface(product.tree_canonical_path) and not product.tree_canonical_path.startswith("Produce >"):
        return False, 0.0, "fresh_herb_requires_fresh_path"

    if recipe_group == "5" and "hard boiled" in title_lc and "hard" not in item_lc and "boiled" not in item_lc:
        return False, 0.0, "egg_process_mismatch"
    if recipe_group == "5" and "pickled" in title_lc and "pickled" not in item_lc:
        return False, 0.0, "egg_process_mismatch"
    if recipe_group == "5" and re.search(r"\b(scramble|scrambled|mix|powder|liquid)\b", title_lc):
        if not re.search(r"\b(scramble|scrambled|mix|powder|liquid)\b", item_lc):
            return False, 0.0, "egg_process_mismatch"
    if recipe_group == "5" and recipe_pid_key in {"egg", "eggs"} and product.pid_key and product.pid_key not in {"egg", "eggs"}:
        return False, 0.0, "egg_product_form_mismatch"

    # Penalize unrequested title additions, but do not make package words fatal.
    noise = title_noise_tokens(product.name, terms | product.title_terms & terms)
    if len(noise) > 6 and not (recipe_pid_key and pid_related):
        score -= 25.0

    if product.taxonomy_status.startswith("quarantine"):
        score -= 15.0
    if product.tree_authority == "white_shell_egg_correction":
        score += 20.0

    return score >= 80.0, score, ";".join(reasons)


def candidate_ids(row: dict[str, str], index: ProductIndex, scope: str) -> list[int]:
    ids: set[int] = set()
    pid_key = normalize_key(row.get("tree_product_identity") or "")
    mod_key = normalize_key(row.get("tree_modifier") or "")
    canonical_key = normalize_surface(row.get("tree_canonical_path") or "")
    if pid_key:
        ids.update(index.by_pid.get((scope, pid_key), ())[:600])
    if mod_key:
        ids.update(index.by_modifier.get((scope, mod_key), ())[:600])
        if pid_key in GENERIC_SPICE_PID_KEYS:
            ids.update(index.by_pid.get((scope, mod_key), ())[:600])
    if canonical_key:
        ids.update(index.by_canonical.get((scope, canonical_key), ())[:600])
    group = row.get("htc_group") or ""
    family = row.get("htc_family") or ""
    if pid_key in GENERIC_SPICE_PID_KEYS and mod_key:
        ids.update(title_candidate_ids(row, index, scope, limit=350))
    if len(ids) < 80:
        ids.update(title_candidate_ids(row, index, scope, limit=350))
    if pid_key == "chili pepper":
        ids.update(index.by_group.get((scope, group), ())[:5000])
    if len(ids) < 50:
        if family and family != "0":
            ids.update(index.by_group_family.get((scope, group, family), ())[:100])
        else:
            ids.update(index.by_group.get((scope, group), ())[:100])
    return list(ids)


def title_candidate_ids(row: dict[str, str], index: ProductIndex, scope: str, *, limit: int) -> list[int]:
    group = row.get("htc_group") or ""
    family = row.get("htc_family") or ""
    terms = [
        term
        for term in recipe_terms(row) - TITLE_INDEX_STOP
        if len(term) > 2
    ]
    buckets = [
        index.by_title_term.get((scope, term), ())
        for term in terms
    ]
    buckets = [bucket for bucket in buckets if bucket]
    if not buckets:
        return []
    buckets.sort(key=len)
    if len(buckets) == 1:
        candidate_set = set(buckets[0][: min(1200, len(buckets[0]))])
    else:
        candidate_set = set(buckets[0][: min(2500, len(buckets[0]))])
        for bucket in buckets[1:3]:
            candidate_set &= set(bucket[: min(3000, len(bucket))])
        if not candidate_set:
            candidate_set = set(buckets[0][: min(600, len(buckets[0]))])
    compatible = [
        idx
        for idx in candidate_set
        if (
            htc_compatible(group, family, index.products[idx].htc_group, index.products[idx].htc_family)
            or spice_family_bridge_allowed(row, index.products[idx])
        )
    ]
    compatible.sort(key=lambda idx: (index.products[idx].cpg, index.products[idx].cents))
    return compatible[:limit]


def pick_offer(row: dict[str, str], index: ProductIndex, scope: str) -> tuple[ProductOffer | None, float, str, str]:
    if row.get("tree_canonical_path") == "__TAP_WATER__":
        return None, 999.0, "safe_tap_water", "tap_water"
    if row.get("htc_group") in {"", "0", "N"}:
        return None, 0.0, "no_htc_food_group", "recipe_htc_unresolved"

    scored: list[tuple[float, ProductOffer, str]] = []
    reject_counts: Counter[str] = Counter()
    for idx in candidate_ids(row, index, scope):
        product = index.products[idx]
        ok, score, reason = product_matches_recipe(row, product)
        if ok:
            scored.append((score, product, reason))
        else:
            reject_counts[reason] += 1

    if not scored:
        detail = ",".join(f"{k}:{v}" for k, v in reject_counts.most_common(4))
        return None, 0.0, "no_safe_offer", detail

    top_score = max(score for score, _, _ in scored)
    pool = [(score, product, reason) for score, product, reason in scored if score >= top_score - 25.0]
    pool.sort(key=lambda item: (item[1].cpg, item[1].cents, -item[0]))
    score, product, reason = pool[0]
    return product, score, "safe_priced", reason


def bridge_row(row: dict[str, str], scope: str, product: ProductOffer | None, score: float, status: str, detail: str) -> dict[str, str]:
    out = {
        "store_scope": scope,
        "ingredient_item": row.get("ingredient_item") or "",
        "recipe_count": row.get("recipe_count") or "",
        "terminal_status": status,
        "match_score": f"{score:.1f}",
        "match_detail": detail,
        "recipe_htc_code": row.get("htc_code") or "",
        "recipe_htc_group": row.get("htc_group") or "",
        "recipe_htc_family": row.get("htc_family") or "",
        "recipe_identity_code": row.get("identity_code") or "",
        "recipe_tree_identity": row.get("tree_product_identity") or "",
        "recipe_tree_canonical": row.get("tree_canonical_path") or "",
        "recipe_tree_modifier": row.get("tree_modifier") or "",
        "product_rowid": "",
        "source": "",
        "upc": "",
        "name": "",
        "brand": "",
        "grams": "",
        "cents": "",
        "cpg": "",
        "product_htc_code": "",
        "product_htc_group": "",
        "product_htc_family": "",
        "product_tree_identity": "",
        "product_tree_canonical": "",
        "product_tree_modifier": "",
        "product_taxonomy_status": "",
        "product_tree_authority": "",
    }
    if product:
        out.update({
            "product_rowid": product.rowid,
            "source": product.source,
            "upc": product.upc,
            "name": product.name,
            "brand": product.brand,
            "grams": f"{product.grams:.6g}",
            "cents": str(product.cents),
            "cpg": f"{product.cpg:.8f}",
            "product_htc_code": product.htc_code,
            "product_htc_group": product.htc_group,
            "product_htc_family": product.htc_family,
            "product_tree_identity": product.tree_product_identity,
            "product_tree_canonical": product.tree_canonical_path,
            "product_tree_modifier": product.tree_modifier,
            "product_taxonomy_status": product.taxonomy_status,
            "product_tree_authority": product.tree_authority,
        })
    return out


def build(args: argparse.Namespace) -> dict[str, object]:
    t0 = time.time()
    print(f"loading recipe HTC/tree rows: {args.recipe}", flush=True)
    recipe_rows = load_recipe_rows(args.recipe)
    print(f"loading product HTC/tree rows: {args.products}", flush=True)
    products = load_products(args.products)
    print(f"indexing {len(products):,} product offers", flush=True)
    index = build_index(products)

    out_rows: list[dict[str, str]] = []
    status_counts: Counter[str] = Counter()
    weighted_lines_by_status: Counter[str] = Counter()
    by_scope_status: dict[str, Counter[str]] = {scope: Counter() for scope in STORE_SCOPES}

    for i, row in enumerate(recipe_rows, 1):
        recipe_count = intish(row.get("recipe_count"))
        for scope in STORE_SCOPES:
            product, score, status, detail = pick_offer(row, index, scope)
            out_rows.append(bridge_row(row, scope, product, score, status, detail))
            status_counts[status] += 1
            by_scope_status[scope][status] += 1
            weighted_lines_by_status[status] += recipe_count
        if i % 1000 == 0:
            print(f"  bridged ingredients: {i:,}/{len(recipe_rows):,}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    summary = {
        "elapsed_s": round(time.time() - t0, 1),
        "recipe_ingredients": len(recipe_rows),
        "product_offers_indexed": len(products),
        "bridge_rows": len(out_rows),
        "status_counts": dict(status_counts.most_common()),
        "weighted_recipe_line_status_counts": dict(weighted_lines_by_status.most_common()),
        "by_scope_status_counts": {scope: dict(counter.most_common()) for scope, counter in by_scope_status.items()},
        "inputs": {"recipe": str(args.recipe), "products": str(args.products)},
        "output": str(args.out),
    }
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, default=DEFAULT_RECIPE)
    parser.add_argument("--products", type=Path, default=DEFAULT_PRODUCTS)
    parser.add_argument("--out", type=Path, default=OUT_BRIDGE)
    parser.add_argument("--summary-out", type=Path, default=OUT_SUMMARY)
    args = parser.parse_args()
    summary = build(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
