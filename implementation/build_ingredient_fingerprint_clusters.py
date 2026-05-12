from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

import match_esha_to_products as matcher
from build_product_to_best_esha_full_map import FIELDNAMES, hinted_product_family


ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_DB = ROOT / "data" / "master_products.db"
ESHA_CSV = ROOT / "esha_cleaned.csv"
DEFAULT_MAP_CSV = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.csv"
OUT_DIR = ROOT / "implementation" / "output"
OUT_CLUSTERS = OUT_DIR / "ingredient_fingerprint_clusters.csv"
OUT_PROPOSALS = OUT_DIR / "ingredient_cluster_proposals.csv"
OUT_SUMMARY = OUT_DIR / "ingredient_cluster_summary.json"
OUT_APPLIED = OUT_DIR / "product_to_best_esha_full_map.vM.csv"
OUT_APPLIED_DIFF = OUT_DIR / "ingredient_cluster_applied_diff.csv"
OUT_QUARANTINE = OUT_DIR / "ingredient_assignment_quarantine.csv"


INGREDIENT_STOPWORDS = {
    "ingredient", "ingredients", "contains", "containing", "contain",
    "less", "than", "may", "include", "includes", "including",
    "trace", "amount", "amounts", "small",
    "and", "or",
    "natural", "artificial", "flavor", "flavors", "flavored", "flavoring", "flavorings",
    "color", "colors", "coloring", "added", "fortified", "enriched",
    "organic", "non", "gmo", "free",
    "the", "a", "an", "to", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it", "its",
    "no", "not", "on", "this", "that", "these", "those",
    "ascorbic", "citric", "acid", "acids",
    "modified", "concentrate", "concentrated",
    "high", "fructose", "low",
    "preservative", "preservatives", "freshness",
    "g", "mg", "mcg", "iu", "kg", "ml", "oz",
}

TITLE_NOISE = matcher.STOPWORDS | {
    "brand", "quality", "premium", "select", "original", "classic", "natural",
    "naturally", "fresh", "freshly", "great", "value", "market", "marketplace",
    "food", "foods", "product", "products", "pack", "packs", "bag", "box",
    "can", "cans", "jar", "jars", "bottle", "bottles", "oz", "lb", "ct",
}

STATE_TERMS = {
    "canned", "can", "frozen", "fresh", "raw", "dried", "dry", "powder",
    "powdered", "evaporated", "condensed", "roasted", "toasted", "smoked",
    "pickled", "cultured", "filled", "goat", "buttermilk", "skim", "nonfat",
    "whole", "reduced", "lowfat", "lactose", "shelf", "stable",
    "one_percent", "two_percent", "french", "infant", "baby",
    "flour", "meal", "ground", "sliced", "slivered", "chopped", "topping",
}

PROFILE_CLUSTER_FAMILIES = {"nut_seed", "vegetable", "milk"}

INGREDIENT_PROFILE_DROP = INGREDIENT_STOPWORDS | {
    "vegetable", "oil", "oils", "peanut", "cottonseed", "soybean", "sunflower",
    "canola", "safflower", "palm", "rapeseed", "corn", "sea", "xanthan", "gum",
    "guar", "locust", "bean", "maltodextrin", "dextrin", "starch", "modified",
    "lecithin", "tocopherol", "tocopherols", "niacin", "thiamin", "riboflavin",
    "folic", "vitamin", "vitamins", "palmitate", "dioxide", "calcium",
    "chloride", "disodium", "edta", "sulfite", "sulfites",
}

FORM_TERMS = {
    "french", "cut", "sliced", "slice", "pieces", "piece", "diced", "chopped",
    "whole", "halves", "spears", "stems", "florets", "shredded", "grated",
    "ground", "crushed", "chunk", "chunks",
}

GENERIC_PRIMARY_TOKENS = {"nut", "nuts", "seed", "seeds"}

GENERIC_IDENTITY_TERMS = {
    "food", "dish", "prepared", "recipe", "style", "type", "plain", "regular",
    "snack", "mix", "with", "added", "fresh", "natural", "artificial",
    "water", "salt", "sugar", "oil", "flavor", "flavors", "flavored",
}

HARD_FORM_MISMATCH_REASONS = {
    "bagel_anchor_without_bagel_product",
    "bagel_anchor_on_pizza_product",
    "bar_anchor_without_bar_product",
    "energy_bar_anchor_without_energy_bar_product",
    "bar_anchor_on_nonbar_mix_product",
    "plant_milk_anchor_on_pudding_product",
    "plant_milk_anchor_on_non_milk_product",
    "waffle_product_without_waffle_anchor",
    "pancake_product_without_pancake_anchor",
    "crepe_product_without_crepe_anchor",
    "french_toast_product_without_french_toast_anchor",
    "prepared_meal_product_to_component_anchor",
    "fresh_sliced_apple_anchor_on_composite_apple_product",
    "applesauce_anchor_on_cider_product",
    "bacon_anchor_on_pepperoni_product",
    "bacon_anchor_on_component_product",
    "bacon_anchor_poultry_subtype_mismatch",
    "bacon_anchor_without_bacon_product",
    "burrito_product_without_burrito_anchor",
    "burger_product_without_burger_anchor",
    "croissant_product_without_croissant_anchor",
    "dressing_product_without_dressing_anchor",
    "generic_bacon_anchor_on_turkey_bacon_product",
    "soup_product_without_soup_anchor",
    "chip_product_without_chip_anchor",
    "mashed_product_without_mashed_anchor",
    "muffin_product_without_muffin_anchor",
    "cookie_product_without_cookie_anchor",
    "dough_product_without_dough_anchor",
    "pastry_product_without_pastry_anchor",
    "fritter_product_without_fritter_anchor",
    "granola_product_without_granola_anchor",
    "strudel_product_without_strudel_anchor",
    "puff_product_without_puff_anchor",
    "hummus_product_without_hummus_anchor",
    "dip_product_without_dip_anchor",
    "salsa_product_without_salsa_anchor",
    "candy_product_without_candy_anchor",
    "truffle_product_without_truffle_anchor",
    "pudding_product_without_pudding_anchor",
    "custard_product_without_custard_anchor",
    "creamer_product_without_creamer_anchor",
    "baking_chips_anchor_without_baking_chip_product",
    "baking_mix_anchor_on_non_baking_mix_product",
    "baking_mix_anchor_on_plain_flour_product",
    "baking_powder_anchor_without_baking_powder_product",
    "baking_soda_anchor_without_baking_soda_product",
    "wheat_free_anchor_on_wheat_product",
    "flour_product_without_flour_anchor",
    "milk_product_without_milk_anchor",
    "single_fruit_anchor_on_mixed_fruit_product",
    "base_anchor_without_base_product",
    "base_subtype_without_subtype_product",
    "dry_batter_mix_anchor_on_prepared_fish_product",
    "beans_and_rice_anchor_without_rice_product",
    "beans_and_rice_anchor_on_prepared_entree_product",
    "beans_anchor_subtype_mismatch",
    "beans_anchor_on_prepared_component_product",
    "beans_anchor_on_vanilla_bean_flavor_product",
    "bean_product_without_bean_anchor",
    "bean_anchor_on_without_beans_product",
    "french_toast_anchor_without_french_toast_product",
    "infant_anchor_without_infant_product",
    "bread_anchor_without_bread_product",
    "breaded_anchor_without_breaded_product",
    "cake_anchor_without_cake_product",
    "cereal_anchor_without_cereal_product",
    "chocolate_anchor_without_chocolate_product",
    "cookie_anchor_without_cookie_product",
    "kefir_anchor_without_kefir_product",
    "milk_fat_state_missing",
    "muffin_anchor_without_muffin_product",
    "oatmeal_product_without_oatmeal_anchor",
    "nut_butter_without_butter_identity",
    "nut_processed_form_missing",
    "nut_whole_processed_form_mismatch",
    "pastry_anchor_without_pastry_product",
    "pie_anchor_without_pie_product",
    "pizza_anchor_without_pizza_product",
    "quiche_product_without_quiche_anchor",
    "roll_product_without_roll_anchor",
    "salad_anchor_without_salad_product",
    "sandwich_product_without_sandwich_anchor",
    "sauce_anchor_on_plain_pasta_product",
    "taco_product_without_taco_anchor",
    "topping_anchor_without_topping_product",
    "wrap_product_without_wrap_anchor",
}

STRICT_PRODUCT_FORMS = {
    "soup": {"soup", "chowder", "bisque"},
    "chip": {"chip", "chips", "crisp", "crisps"},
    "mashed": {"mashed"},
    "waffle": {"waffle", "waffles"},
    "pancake": {"pancake", "pancakes"},
    "crepe": {"crepe", "crepes"},
    "muffin": {"muffin", "muffins"},
    "cookie": {"cookie", "cookies"},
    "dough": {"dough"},
    "pastry": {"pastry", "pastries"},
    "fritter": {"fritter", "fritters"},
    "strudel": {"strudel"},
    "puff": {"puff", "puffs"},
    "hummus": {"hummus"},
    "dip": {"dip", "dips", "dipping", "dippin"},
    "salsa": {"salsa"},
    "candy": {"candy", "candies"},
    "truffle": {"truffle", "truffles"},
    "pudding": {"pudding", "puddings"},
    "custard": {"custard", "custards"},
    "creamer": {"creamer", "creamers"},
    "flour": {"flour", "flours"},
    "dressing": {"dressing", "dressings", "vinaigrette", "mayonnaise", "mayo"},
    "quiche": {"quiche", "quiches"},
    "sandwich": {"sandwich", "sandwiches", "club"},
    "wrap": {"wrap", "wraps"},
    "burrito": {"burrito", "burritos"},
    "taco": {"taco", "tacos"},
    "croissant": {"croissant", "croissants"},
    "roll": {"roll", "rolls"},
    "burger": {"burger", "burgers", "patty", "patties"},
    "oatmeal": {"oatmeal"},
    "granola": {"granola"},
}

STRONG_ANCHOR_SOURCES = {"fallback_category_family"}
WEAK_ANCHOR_SOURCES = {"legacy_best_map"}
PC_ANCHORED_MIN_SCORE = 6.0

TOKEN_RE = re.compile(r"[a-z][a-z0-9']+")


@dataclass(frozen=True)
class EshaAnchor:
    code: str
    description: str
    family: str
    tokens: frozenset[str]
    hard_terms: frozenset[str]
    identity_terms: frozenset[str]


def normalize_gtin(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def normalized_token(token: str) -> str:
    token = token.lower().strip("'")
    token = matcher.TOKEN_SYNONYMS.get(matcher.singular(token), matcher.singular(token))
    return token


def tokenize_ingredients(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in TOKEN_RE.findall((text or "").lower()):
        token = normalized_token(raw)
        if len(token) < 3 or token in INGREDIENT_STOPWORDS:
            continue
        for expanded in (token, *matcher.COMPOUND_TOKEN_EXPANSIONS.get(token, ())):
            if expanded and expanded not in INGREDIENT_STOPWORDS and expanded not in seen:
                seen.add(expanded)
                out.append(expanded)
    return tuple(out)


def title_tokens(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for token in matcher.tokens_for(text or ""):
        token = normalized_token(token)
        if len(token) < 2 or token in TITLE_NOISE:
            continue
        if token not in seen:
            seen.add(token)
            out.append(token)
    return tuple(out)


def primary_food(tokens: tuple[str, ...]) -> str:
    token_set = set(tokens)
    ordered_domains = [
        matcher.SEAFOOD,
        matcher.POULTRY,
        matcher.MEATS,
        matcher.LEGUMES,
        matcher.NUTS_SEEDS,
        matcher.VEGETABLES,
        matcher.FRUITS,
        matcher.GRAINS,
        matcher.DESSERT_HEADS | {"gum", "gummy", "gummi", "candy", "chocolate", "cookie", "cracker"},
    ]
    for domain in ordered_domains:
        specific = [token for token in tokens if token in domain and token not in GENERIC_PRIMARY_TOKENS]
        if specific:
            return specific[0]
        for token in tokens:
            if token in domain:
                return token
    if "milk" in token_set:
        return "milk"
    if "cheese" in token_set:
        return "cheese"
    if "yogurt" in token_set:
        return "yogurt"
    if "cream" in token_set or "creamer" in token_set:
        return "cream"
    return ""


def product_family_for(description: str, category: str, title: tuple[str, ...]) -> str:
    text = f"{description or ''} {category or ''}".lower()
    norm_category = (category or "").strip().lower()
    token_set = set(title)
    if norm_category in {"puddings & custards"} or {"pudding", "custard"} & token_set:
        return "dessert_snack"
    if {"rub", "seasoning", "spice"} & token_set:
        return "spice"
    if {"jelly", "jam", "preserve", "preserves", "marmalade"} & token_set:
        return "condiment"
    if "applesauce" in token_set or ({"apple", "sauce"} <= token_set):
        return "condiment"
    if "creamer" in token_set or "milk additives" in text:
        return "cream"
    if norm_category in {"plant based milk", "milk/milk substitutes"} and not ({"shake", "bar", "candy", "truffle"} & token_set):
        return "plant_milk"
    if norm_category in {"chocolate", "candy", "confectionery", "confectionery products"}:
        return "dessert_snack"
    if "bar" in token_set or "bars" in text:
        return "dessert_snack"
    if {"candy", "truffle", "chocolate"} & token_set and not norm_category in {"plant based milk", "milk/milk substitutes"}:
        return "dessert_snack"
    if "shake" in token_set or "drink" in token_set or "meal replacement" in text:
        return "beverage"
    family = hinted_product_family(description, category)
    primary = primary_food(title)
    nut_category = any(part in text for part in ("peanuts", "seeds", "related snacks", "nuts"))
    if family in {"sweetener", "spice"} and primary in matcher.NUTS_SEEDS and nut_category:
        return "nut_seed"
    return family


def state_lane(description: str, category: str, tokens: tuple[str, ...]) -> str:
    text = f"{description or ''} {category or ''}".lower()
    token_set = set(tokens) | set(title_tokens(text))
    states: list[str] = []
    if "frozen" in token_set:
        states.append("frozen")
    elif "canned" in token_set or "can" in token_set or "shelf" in token_set:
        states.append("canned")
    elif "fresh" in token_set or "raw" in token_set:
        states.append("fresh")
    if "evaporated" in token_set:
        states.append("evaporated")
    if "condensed" in token_set:
        states.append("condensed")
    if "filled" in token_set:
        states.append("filled")
    if "goat" in token_set:
        states.append("goat")
    if "buttermilk" in token_set:
        states.append("buttermilk")
    if "lactose" in token_set:
        states.append("lactose")
    if "fat free" in text or "nonfat" in token_set or "skim" in token_set:
        states.append("skim")
    elif "whole" in token_set:
        states.append("whole")
    elif "2%" in text or "2 percent" in text or "reduced fat" in text:
        states.append("two_percent")
    elif "1%" in text or "1 percent" in text or "low fat" in text or "lowfat" in token_set:
        states.append("one_percent")
    if "powder" in token_set or "powdered" in token_set or "dry" in token_set or "dried" in token_set:
        states.append("dry")
    for form in ("flour", "meal", "ground", "sliced", "slivered", "chopped", "raw", "roasted", "toasted"):
        if form in token_set:
            states.append(form)
    if "french" in token_set:
        states.append("french")
    elif "cut" in token_set:
        states.append("cut")
    if "no salt" in text or "unsalted" in token_set:
        states.append("unsalted")
    elif "salted" in token_set:
        states.append("salted")
    if "infant" in token_set or "baby food" in text or "babyfood" in token_set:
        states.append("infant")
    return "+".join(states) if states else "generic"


def ingredient_key(tokens: tuple[str, ...]) -> str:
    return " ".join(sorted(set(tokens)))


def ingredient_profile_key(tokens: tuple[str, ...], product_family: str, primary: str) -> str:
    """Conservative near-fingerprint for stable identities.

    Exact fingerprints miss obvious same-food cases where brands vary carrier oils,
    gums, starches, or vitamin/additive wording. This profile keeps the identity
    food plus meaningful formula modifiers, while still requiring family, primary,
    and state lane to match in the cluster id.
    """
    if product_family not in PROFILE_CLUSTER_FAMILIES or not primary:
        return ""

    keep_always = {
        primary, "water", "salt", "sugar", "honey", "syrup", "vinegar",
        "roasted", "toasted", "smoked", "sweetened", "unsweetened", "skim",
        "whole", "reduced", "lowfat", "nonfat", "lactose",
    }
    drop = set(INGREDIENT_PROFILE_DROP)
    drop.discard(primary)

    out: set[str] = set()
    for token in tokens:
        if token in keep_always:
            out.add(token)
            continue
        if token in drop:
            continue
        if product_family == "vegetable" and token in matcher.VEGETABLES:
            out.add(token)
        elif product_family == "nut_seed" and token in matcher.NUTS_SEEDS:
            out.add(token)
        elif product_family == "milk" and token in {"milk", "cream", "buttermilk"}:
            out.add(token)

    if primary not in out:
        return ""
    return " ".join(sorted(out))


def cluster_id_for(parts: tuple[str, ...]) -> str:
    payload = "\t".join(parts).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:16]


def load_products() -> pd.DataFrame:
    con = sqlite3.connect(str(PRODUCTS_DB))
    try:
        df = pd.read_sql_query(
            """
            SELECT gtin_upc, fdc_id, description AS product_description,
                   brand_owner, brand_name, branded_food_category,
                   COALESCE(NULLIF(ingredients_clean, ''), NULLIF(ingredients, ''), '') AS ingredients
            FROM products
            ORDER BY gtin_upc
            """,
            con,
            dtype={"gtin_upc": str, "fdc_id": str},
        )
    finally:
        con.close()
    df["gtin_upc"] = df["gtin_upc"].map(normalize_gtin)
    return df


def load_current_map(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    df["gtin_upc"] = df["gtin_upc"].map(normalize_gtin)
    df["score_num"] = pd.to_numeric(df.get("score", ""), errors="coerce")
    return df


def load_esha_anchors() -> dict[str, EshaAnchor]:
    out: dict[str, EshaAnchor] = {}
    with ESHA_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle):
            if "EshaCode" not in row and "Code" in row:
                row = {**row, "EshaCode": row.get("Code", "")}
            profile = matcher.profile_for(row)
            if not profile.code or profile.skip_reason:
                continue
            hard_terms = frozenset(profile.hard_terms)
            identity_terms = frozenset(t for t in hard_terms if t not in GENERIC_IDENTITY_TERMS)
            if not identity_terms:
                identity_terms = frozenset(t for t in profile.tokens if t not in GENERIC_IDENTITY_TERMS and t not in STATE_TERMS)
            out[profile.code] = EshaAnchor(
                code=profile.code,
                description=profile.description,
                family=profile.family,
                tokens=frozenset(profile.tokens),
                hard_terms=hard_terms,
                identity_terms=identity_terms,
            )
    return out


def explicit_states(tokens: set[str]) -> set[str]:
    states = set(tokens & STATE_TERMS)
    if "1" in tokens:
        states.add("one_percent")
    if "2" in tokens:
        states.add("two_percent")
    if "3.25" in tokens or "3.5" in tokens:
        states.add("whole")
    if "powdered" in states:
        states.add("powder")
    if "nonfat" in states:
        states.add("skim")
    if "lowfat" in states:
        states.add("one_percent")
    if "reduced" in states:
        states.add("two_percent")
    return states


def state_compatible(product_states: set[str], anchor_tokens: set[str]) -> bool:
    anchor_states = explicit_states(anchor_tokens)
    if not anchor_states or not product_states:
        return True
    conflicts = [
        ({"frozen"}, {"canned", "fresh", "raw"}),
        ({"canned"}, {"frozen", "fresh", "raw"}),
        ({"fresh", "raw"}, {"dry", "dried", "powder", "powdered"}),
        ({"evaporated"}, {"condensed", "powder", "powdered"}),
        ({"condensed"}, {"evaporated", "powder", "powdered"}),
        ({"skim"}, {"whole", "two_percent", "one_percent"}),
        ({"whole"}, {"skim", "two_percent", "one_percent"}),
        ({"two_percent", "one_percent"}, {"whole", "skim"}),
        ({"one_percent"}, {"two_percent"}),
        ({"butter", "paste", "spread"}, {"roasted", "raw", "whole"}),
    ]
    for left, right in conflicts:
        if anchor_states & left and product_states & right:
            return False
        if anchor_states & right and product_states & left:
            return False
    if "french" in anchor_states and "french" not in product_states:
        return False
    if "infant" in anchor_states and "infant" not in product_states:
        return False
    return True


def is_real_bar_product(desc: str, category: str) -> bool:
    text = f"{desc} {category}".lower()
    if "bar-b-q" in text or "bar-b-que" in text:
        text = text.replace("bar-b-q", "bbq").replace("bar-b-que", "bbq")
    desc_text = desc.lower()
    if re.search(r"\b(?:protein|energy|fruit|granola|cereal|meal|nutrition|snack|breakfast|dessert|truffle|chocolate|brownie|cheesecake|fig|date|oat|oatmeal)\s+bars?\b", desc_text):
        return True
    if re.search(r"\b(?:chewy|crispy|crunchy|soft baked|soft-baked)\s+bars?\b", desc_text):
        return True
    if re.search(r"\bbars?\s+(?:\d|count|ct|pack|box|case|size|variety|flavor|flavored|chocolate|vanilla|strawberry|apple|almond|peanut|oat|granola|protein|energy|nutrition|breakfast)\b", desc_text):
        return True
    if re.search(r"\bbars?\s*(?:,|$)", desc_text):
        return True
    nonbar_forms = (
        "trail mix", "snack mix", "power mix", "protein powder", "shake",
        "cracklin", "pork rind", "chicharron", "cluster", "clusters",
        "dried ", "sliced ", "frozen ", "blend", "cherries", "apricots",
    )
    if any(term in desc_text for term in nonbar_forms):
        return False
    if "bars" in category.lower() or "bar" in category.lower():
        return True
    return False


def has_energy_bar_context(desc: str, category: str, evidence: set[str]) -> bool:
    text = f"{desc} {category}".lower()
    return bool(
        {"energy", "protein", "diet", "carbohydrate"} & evidence
        or any(term in text for term in ("energy bar", "protein bar", "high protein", "low carbohydrate", "snack, energy"))
    )


def is_infant_food_anchor(anchor_text: str, anchor_tokens: set[str]) -> bool:
    """True for baby-food taxonomy heads, not ordinary 'baby' vegetables."""
    return bool(
        "infant" in anchor_tokens
        or anchor_text.startswith("infant ")
        or anchor_text.startswith("infant,")
        or "baby food" in anchor_text
        or re.search(r"\bstage\s*\d\b", anchor_text)
        or re.search(r"\b\d+\s*months?\b", anchor_text)
    )


def is_infant_product(desc: str, category: str, evidence: set[str]) -> bool:
    text = f"{desc} {category}".lower()
    return bool(
        "infant" in evidence
        or "toddler" in evidence
        or "baby/infant" in text
        or "baby food" in text
        or "babyfood" in evidence
        or " for baby" in text
        or text.startswith("baby ")
    )


BEAN_SUBTYPES = {
    "black": {"black"},
    "garbanzo": {"garbanzo", "chickpea", "chickpeas"},
    "great_northern": {"great", "northern"},
    "butter": {"butter", "lima"},
    "kidney": {"kidney"},
    "pinto": {"pinto"},
    "navy": {"navy"},
    "cannellini": {"cannellini", "white"},
    "red": {"red"},
    "baked": {"baked", "homestyle", "barbecue", "bbq"},
}


def bean_subtypes_from(tokens: set[str], text: str = "") -> set[str]:
    out: set[str] = set()
    text_l = text.lower()
    if "black gram" in text_l:
        out.add("black_gram")
    for subtype, aliases in BEAN_SUBTYPES.items():
        if subtype == "great_northern":
            if "great northern" in text_l or {"great", "northern"} <= tokens:
                out.add(subtype)
            continue
        if tokens & aliases or any(alias in text_l for alias in aliases):
            out.add(subtype)
    return out


def form_mismatch_reason(row: pd.Series, anchor: EshaAnchor, evidence: set[str]) -> str | None:
    """Reject cases where a component token is mistaken for the product form."""
    desc = str(row.get("product_description") or "").lower()
    category = str(row.get("branded_food_category") or "").lower()
    product_text = f"{desc} {category}"
    anchor_text = anchor.description.lower()
    anchor_tokens = set(anchor.tokens)
    anchor_head = anchor_text.split(",", 1)[0].strip()
    product_family = str(row.get("_product_family") or "")
    title_evidence = set(row.get("_title_tokens") or ())

    if "bagel" in anchor_tokens or "bagel" in anchor_text:
        if ("pizza" in evidence or "pizza" in category) and "pizza" not in anchor_text:
            return "bagel_anchor_on_pizza_product"
        if "bagel" not in evidence and "bagel" not in desc:
            return "bagel_anchor_without_bagel_product"

    if anchor_head == "bar" or anchor_text.startswith("bar,"):
        if any(term in product_text for term in ("trail mix", "snack mix", "power mix")) and "bar" not in desc:
            return "bar_anchor_on_nonbar_mix_product"
        if not is_real_bar_product(desc, category):
            return "bar_anchor_without_bar_product"
        energy_anchor = any(term in anchor_text for term in ("energy", "high protein", "low carbohydrate", "diet"))
        if energy_anchor and not has_energy_bar_context(desc, category, evidence):
            return "energy_bar_anchor_without_energy_bar_product"

    if anchor_head == "base" or anchor_text.startswith("base,"):
        base_product = any(term in product_text for term in (" base", "base ", "stock", "broth", "bouillon", "soup base", "sauce base"))
        if not base_product:
            return "base_anchor_without_base_product"
        base_subtypes = {
            "butter": {"butter"},
            "ham": {"ham"},
            "pork": {"pork"},
            "seafood": {"seafood", "fish", "shrimp", "crab", "clam"},
        }
        for subtype, aliases in base_subtypes.items():
            if subtype in anchor_text and not (evidence & aliases):
                return "base_subtype_without_subtype_product"

    if anchor_head == "batter" or anchor_text.startswith("batter,"):
        dry_mix_anchor = "dry mix" in anchor_text or "mix" in anchor_tokens
        dry_mix_product = any(term in product_text for term in ("batter mix", "dry mix", "coating mix", "breader", "breading mix"))
        if dry_mix_anchor and not dry_mix_product:
            return "dry_batter_mix_anchor_on_prepared_fish_product"

    if anchor_head == "pizza" or anchor_text.startswith("pizza,"):
        if "pizza" not in product_text:
            return "pizza_anchor_without_pizza_product"

    if anchor_head == "sauce" or anchor_text.startswith("sauce,"):
        plain_pasta_lane = "pasta by shape" in category or "pasta by shape & type" in category
        sauce_product = any(term in product_text for term in ("sauce", "marinara", "alfredo", "pesto", "ragout", "ragu"))
        if plain_pasta_lane and not sauce_product:
            return "sauce_anchor_on_plain_pasta_product"

    if anchor_head.startswith("beans & rice") or anchor_head.startswith("beans and rice"):
        prepared_entree = any(term in product_text for term in ("burrito", "wrap", "frozen dinners", "entree", "prepared meals"))
        if prepared_entree:
            return "beans_and_rice_anchor_on_prepared_entree_product"
        if "rice" not in evidence:
            return "beans_and_rice_anchor_without_rice_product"

    if anchor_head.startswith("beans"):
        bean_product = "bean" in evidence or "beans" in product_text
        if not bean_product:
            return "bean_product_without_bean_anchor"
        true_bean_lane = any(
            term in category
            for term in (
                "canned & bottled beans",
                "vegetable and lentil mixes",
                "vegetables - prepared/processed",
                "vegetables  prepared/processed",
                "vegetables prepared/processed",
            )
        )
        vanilla_bean_flavor = "vanilla bean" in product_text and any(
            term in category
            for term in (
                "cereal",
                "yogurt",
                "dessert",
                "ice cream",
                "frozen yogurt",
                "chocolate",
                "coffee",
                "cream",
                "creamer",
                "milk additives",
                "protein",
                "supplement",
            )
        )
        if vanilla_bean_flavor and not true_bean_lane:
            return "beans_anchor_on_vanilla_bean_flavor_product"
        component_terms = (
            "burger", "burgers", "patty", "patties", "tamale", "tamales",
            "burrito", "wrap", "wraps", "bowl", "bowls", "spring roll",
            "egg roll", "stock", "broth", "soup", "dressing", "salad",
            "dip", "salsa", "hummus", "enchilada", "quesadilla",
        )
        component_category = any(
            term in category
            for term in (
                "frozen patties",
                "burgers",
                "frozen appetizers",
                "hors d'oeuvres",
                "prepared wraps",
                "burittos",
                "burritos",
                "other deli",
                "prepared meals",
                "frozen dinners",
                "entrees",
                "canned soup",
                "deli salads",
                "dips & salsa",
            )
        )
        if (
            anchor_head == "beans"
            and (any(term in product_text for term in component_terms) or component_category)
            and not true_bean_lane
        ):
            return "beans_anchor_on_prepared_component_product"
        product_subtypes = bean_subtypes_from(evidence, product_text)
        anchor_subtypes = bean_subtypes_from(anchor_tokens, anchor_text)
        if "black_gram" in anchor_subtypes and "black" in product_subtypes and "black_gram" not in product_subtypes:
            return "beans_anchor_subtype_mismatch"
        comparable_anchor = anchor_subtypes - {"baked"}
        comparable_product = product_subtypes - {"baked"}
        if comparable_anchor and comparable_product and comparable_anchor.isdisjoint(comparable_product):
            return "beans_anchor_subtype_mismatch"

    if anchor_head.startswith("baking chip") or "baking chips" in anchor_head:
        baking_chip_product = any(term in product_text for term in ("baking chip", "baking chips", "morsel", "morsels"))
        if not baking_chip_product:
            return "baking_chips_anchor_without_baking_chip_product"

    if anchor_head.startswith("baking mix") or "baking mix" in anchor_head:
        plain_flour_product = "flour" in evidence or "flour" in product_text
        baking_mix_product = bool(
            "baking mix" in product_text
            or any(term in category for term in ("cake cookie", "cupcake mixes", "baking additives"))
            or any(
                term in product_text
                for term in (
                    "cake mix", "cookie mix", "cupcake mix", "brownie mix",
                    "muffin mix", "pancake mix", "waffle mix", "biscuit mix",
                    "bread mix", "cornbread mix",
                )
            )
        )
        if plain_flour_product and not baking_mix_product:
            return "baking_mix_anchor_on_plain_flour_product"
        non_baking_mix_product = bool(
            any(term in product_text for term in ("granola mix", "trail mix", "snack mix", "nut mix", "syrup", "honey"))
            or any(term in category for term in ("cereal", "syrups", "molasses", "peanuts", "seeds", "related snacks"))
        )
        if not baking_mix_product or non_baking_mix_product:
            return "baking_mix_anchor_on_non_baking_mix_product"
    if anchor_head.startswith("baking powder"):
        if "baking powder" not in product_text and not ({"baking", "powder"} <= evidence):
            return "baking_powder_anchor_without_baking_powder_product"
    if anchor_head.startswith("baking soda"):
        if "baking soda" not in product_text and not ({"baking", "soda"} <= evidence):
            return "baking_soda_anchor_without_baking_soda_product"
    if "wheat free" in anchor_text and "wheat" in evidence:
        return "wheat_free_anchor_on_wheat_product"

    milk_category = category.strip() in {"milk", "milk/cream - shelf stable", "milk/milk substitutes", "plant based milk"}
    if milk_category and not (
        anchor_head.startswith("milk")
        or anchor_head.startswith("almond milk")
        or "milk" in anchor_head
        or "beverage" in anchor_head
        or "drink" in anchor_head
        or "creamer" in anchor_head
    ):
        return "milk_product_without_milk_anchor"

    if anchor.family == "plant_milk":
        if "pudding" in evidence or "custard" in evidence or "pudding" in category or "custard" in category:
            return "plant_milk_anchor_on_pudding_product"
        plant_milk_category = any(c in category for c in ("plant based milk", "milk/milk substitutes"))
        if product_family != "plant_milk" and not plant_milk_category:
            return "plant_milk_anchor_on_non_milk_product"

    for form, aliases in STRICT_PRODUCT_FORMS.items():
        product_has_form = bool(title_evidence & aliases) or any(alias in product_text for alias in aliases)
        if not product_has_form:
            continue
        anchor_has_form = bool(anchor_tokens & aliases) or any(alias in anchor_text for alias in aliases)
        if not anchor_has_form:
            return f"{form}_product_without_{form}_anchor"
    if {"french", "toast"} <= evidence and "french toast" not in anchor_text:
        return "french_toast_product_without_french_toast_anchor"

    prepared_meal_category = any(c in category for c in ("frozen dinners", "entrees", "prepared meals"))
    if prepared_meal_category:
        anchor_prepared_terms = {
            "dinner", "entree", "entrée", "meal", "bowl", "plate", "with",
            "sandwich", "pizza", "pasta", "lasagna", "casserole", "soup",
            "stew", "chicken", "beef", "pork", "turkey",
        }
        if not (anchor_tokens & anchor_prepared_terms) and not any(t in anchor_text for t in anchor_prepared_terms):
            return "prepared_meal_product_to_component_anchor"

    if {"apple", "sliced", "fresh"} <= anchor_tokens:
        composite_apple_terms = (
            "candy apple", "candy apples", "caramel apple", "cheddar", "cheese",
            "peanut butter", "dippin", "dip", "snack kit", "snack tray", "tray",
        )
        if any(term in desc for term in composite_apple_terms):
            return "fresh_sliced_apple_anchor_on_composite_apple_product"

    if "applesauce" in anchor_text and ("cider" in evidence or "cider" in desc):
        return "applesauce_anchor_on_cider_product"

    if ("without beans" in desc or "no beans" in desc) and ("bean" in anchor_tokens or "bean" in anchor_text):
        return "bean_anchor_on_without_beans_product"

    if "bacon" in anchor_tokens or "bacon" in anchor_text:
        meat_lane = any(c in category for c in ("bacon", "sausages", "ribs", "meat/poultry", "poultry", "chicken", "turkey", "meat"))
        actual_bacon_product = bool(
            "bacon" in evidence
            and (
                "turkey bacon" in desc
                or "chicken bacon" in desc
                or "bacon" in category
                or any(term in desc for term in ("sliced bacon", "smoked bacon", "cured bacon", "bacon pieces", "bacon crumbles"))
            )
        )
        if "bacon" not in evidence:
            return "bacon_anchor_without_bacon_product"
        if "pepperoni" in evidence or "pepperoni" in category:
            return "bacon_anchor_on_pepperoni_product"
        if "turkey" in evidence and "turkey" not in anchor_tokens and "turkey" not in anchor_text:
            return "generic_bacon_anchor_on_turkey_bacon_product"
        if "turkey" in anchor_tokens and "chicken" in evidence and "turkey" not in evidence:
            return "bacon_anchor_poultry_subtype_mismatch"
        if not actual_bacon_product and (
            not meat_lane
            or any(term in desc for term in ("with bacon", "bacon-wrapped", "bacon wrapped", "bacon ranch", "bacon & cheddar", "bacon and cheddar"))
            or evidence & {"brussels", "sprout", "sprouts", "croissant", "sandwich", "wrap", "roll", "taco", "filling", "quiche", "dressing"}
        ):
            return "bacon_anchor_on_component_product"

    product_fruits = evidence & matcher.FRUITS
    anchor_fruits = anchor_tokens & matcher.FRUITS
    mixed_fruit_anchor = any(term in anchor_text for term in ("mixed", "blend", "smoothie", "salad", "cocktail"))
    if anchor.family == "fruit" and anchor_fruits and len(product_fruits - anchor_fruits) > 0 and not mixed_fruit_anchor:
        return "single_fruit_anchor_on_mixed_fruit_product"

    return None


def anchor_gate(row: pd.Series, anchor: EshaAnchor | None) -> tuple[bool, str, float]:
    if anchor is None:
        return False, "missing_esha_anchor", 0.0
    source = str(row.get("assignment_source") or "")
    score = float(row.get("score_num") or 0.0) if pd.notna(row.get("score_num")) else 0.0
    if source in STRONG_ANCHOR_SOURCES and score >= 12:
        source_weight = min(4.0, 2.0 + math.log1p(score) / 2.0)
    elif source in WEAK_ANCHOR_SOURCES:
        source_weight = 1.0
    elif source == "pc_anchored" and score >= PC_ANCHORED_MIN_SCORE:
        source_weight = 1.0
    else:
        return False, "untrusted_source", 0.0

    title = tuple(row["_title_tokens"])
    ingredients = tuple(row["_ingredient_tokens"])
    evidence = set(title) | set(ingredients)
    if not evidence:
        return False, "no_product_evidence", 0.0

    identity_hits = evidence & set(anchor.identity_terms)
    if anchor.identity_terms and not identity_hits:
        return False, "identity_no_overlap", 0.0
    identity_coverage = len(identity_hits) / max(len(anchor.identity_terms), 1)
    if identity_coverage < 0.34:
        return False, "weak_identity_coverage", 0.0
    anchor_text = anchor.description.lower()
    form_reason = form_mismatch_reason(row, anchor, evidence)
    if form_reason:
        return False, form_reason, 0.0
    if ("salad" in anchor.tokens or "salad" in anchor_text) and "salad dressing" not in anchor_text and "salad" not in evidence:
        return False, "salad_anchor_without_salad_product", 0.0
    if ("breaded" in anchor.tokens or "breaded" in anchor_text) and "breaded" not in evidence:
        return False, "breaded_anchor_without_breaded_product", 0.0
    if ("topping" in anchor.tokens or "topping" in anchor_text) and "topping" not in evidence:
        return False, "topping_anchor_without_topping_product", 0.0
    if ("chocolate" in anchor_text or "cocoa" in anchor_text) and not ({"chocolate", "cocoa"} & evidence):
        return False, "chocolate_anchor_without_chocolate_product", 0.0
    if "kefir" in anchor_text and "kefir" not in evidence:
        return False, "kefir_anchor_without_kefir_product", 0.0
    if "applesauce" in anchor_text and "cherry" in evidence and "cherry" not in anchor_text:
        return False, "cherry_applesauce_without_cherry_anchor", 0.0
    if "french toast" in anchor_text and not ({"french", "toast"} <= evidence):
        return False, "french_toast_anchor_without_french_toast_product", 0.0
    if "bar" in anchor.tokens and "bar" not in evidence and "bars" not in str(row.get("branded_food_category") or "").lower():
        return False, "bar_anchor_without_bar_product", 0.0
    if "cereal" in anchor.tokens and "cereal" not in evidence and "cereal" not in str(row.get("branded_food_category") or "").lower():
        return False, "cereal_anchor_without_cereal_product", 0.0
    for bakery_form in ("cookie", "cake", "pie", "pastry", "muffin", "bread"):
        if bakery_form in anchor_text and bakery_form not in evidence:
            return False, f"{bakery_form}_anchor_without_{bakery_form}_product", 0.0

    product_family = str(row["_product_family"])
    if anchor.family == "nut_butter" and product_family == "nut_seed":
        if "butter" not in evidence and "paste" not in evidence and "spread" not in evidence:
            return False, "nut_butter_without_butter_identity", 0.0

    if is_infant_food_anchor(anchor_text, set(anchor.tokens)) and not is_infant_product(
        str(row.get("product_description") or ""),
        str(row.get("branded_food_category") or ""),
        set(title) | set(ingredients),
    ):
        return False, "infant_anchor_without_infant_product", 0.0

    product_primary = str(row["_primary"])
    anchor_primary = primary_food(tuple(anchor.tokens))
    if product_primary and anchor_primary and product_primary != anchor_primary:
        return False, "primary_mismatch", 0.0

    product_states = explicit_states(set(title) | set(ingredients) | set(str(row["_state_lane"]).split("+")))
    if is_infant_food_anchor(anchor_text, set(anchor.tokens)) and not is_infant_product(
        str(row.get("product_description") or ""),
        str(row.get("branded_food_category") or ""),
        set(title) | set(ingredients),
    ):
        return False, "infant_anchor_without_infant_product", 0.0
    anchor_states = explicit_states(set(anchor.tokens))
    milk_fat_states = {"skim", "whole", "one_percent", "two_percent"}
    if product_family == "milk" and (anchor_states & milk_fat_states) and not (product_states & milk_fat_states):
        return False, "milk_fat_state_missing", 0.0
    nut_product_forms = {"flour", "meal", "butter", "paste", "milk", "oil"}
    nut_whole_forms = {"whole", "raw", "roasted", "toasted", "sliced", "slivered", "chopped"}
    if product_family == "nut_seed":
        if (anchor_states & nut_product_forms) and not (product_states & nut_product_forms):
            return False, "nut_processed_form_missing", 0.0
        if (anchor_states & nut_whole_forms) and (product_states & nut_product_forms):
            return False, "nut_whole_processed_form_mismatch", 0.0
    if not state_compatible(product_states, set(anchor.tokens)):
        return False, "state_mismatch", 0.0

    if not matcher.subtype_compatible(set(title) | set(ingredients), set(anchor.tokens), product_family):
        return False, "subtype_mismatch", 0.0

    identity_bonus = min(1.0, len(identity_hits) / max(len(anchor.identity_terms), 1))
    return True, "ok", source_weight + identity_bonus


def candidate_gate(row: pd.Series, anchor: EshaAnchor | None) -> tuple[bool, str]:
    """Check whether this product can receive the proposed ESHA anchor.

    Unlike anchor_gate, this ignores whether the product's current assignment is
    trusted. It only checks product evidence against the candidate ESHA.
    """
    if anchor is None:
        return False, "missing_esha_anchor"

    title = tuple(row["_title_tokens"])
    ingredients = tuple(row["_ingredient_tokens"])
    evidence = set(title) | set(ingredients)
    if not evidence:
        return False, "no_product_evidence"

    identity_hits = evidence & set(anchor.identity_terms)
    if anchor.identity_terms and not identity_hits:
        return False, "identity_no_overlap"
    identity_coverage = len(identity_hits) / max(len(anchor.identity_terms), 1)
    if identity_coverage < 0.34:
        return False, "weak_identity_coverage"

    anchor_text = anchor.description.lower()
    form_reason = form_mismatch_reason(row, anchor, evidence)
    if form_reason:
        return False, form_reason
    if ("salad" in anchor.tokens or "salad" in anchor_text) and "salad dressing" not in anchor_text and "salad" not in evidence:
        return False, "salad_anchor_without_salad_product"
    if ("breaded" in anchor.tokens or "breaded" in anchor_text) and "breaded" not in evidence:
        return False, "breaded_anchor_without_breaded_product"
    if ("topping" in anchor.tokens or "topping" in anchor_text) and "topping" not in evidence:
        return False, "topping_anchor_without_topping_product"
    if ("chocolate" in anchor_text or "cocoa" in anchor_text) and not ({"chocolate", "cocoa"} & evidence):
        return False, "chocolate_anchor_without_chocolate_product"
    if "kefir" in anchor_text and "kefir" not in evidence:
        return False, "kefir_anchor_without_kefir_product"
    if "applesauce" in anchor_text and "cherry" in evidence and "cherry" not in anchor_text:
        return False, "cherry_applesauce_without_cherry_anchor"
    if "french toast" in anchor_text and not ({"french", "toast"} <= evidence):
        return False, "french_toast_anchor_without_french_toast_product"
    if "bar" in anchor.tokens and "bar" not in evidence and "bars" not in str(row.get("branded_food_category") or "").lower():
        return False, "bar_anchor_without_bar_product"
    if "cereal" in anchor.tokens and "cereal" not in evidence and "cereal" not in str(row.get("branded_food_category") or "").lower():
        return False, "cereal_anchor_without_cereal_product"
    for bakery_form in ("cookie", "cake", "pie", "pastry", "muffin", "bread"):
        if bakery_form in anchor_text and bakery_form not in evidence:
            return False, f"{bakery_form}_anchor_without_{bakery_form}_product"

    product_family = str(row["_product_family"])
    if anchor.family == "nut_butter" and product_family == "nut_seed":
        if "butter" not in evidence and "paste" not in evidence and "spread" not in evidence:
            return False, "nut_butter_without_butter_identity"

    if is_infant_food_anchor(anchor_text, set(anchor.tokens)) and not is_infant_product(
        str(row.get("product_description") or ""),
        str(row.get("branded_food_category") or ""),
        set(title) | set(ingredients),
    ):
        return False, "infant_anchor_without_infant_product"

    product_primary = str(row["_primary"])
    anchor_primary = primary_food(tuple(anchor.tokens))
    if product_primary and anchor_primary and product_primary != anchor_primary:
        return False, "primary_mismatch"

    product_states = explicit_states(set(title) | set(ingredients) | set(str(row["_state_lane"]).split("+")))
    if is_infant_food_anchor(anchor_text, set(anchor.tokens)) and not is_infant_product(
        str(row.get("product_description") or ""),
        str(row.get("branded_food_category") or ""),
        set(title) | set(ingredients),
    ):
        return False, "infant_anchor_without_infant_product"
    anchor_states = explicit_states(set(anchor.tokens))
    milk_fat_states = {"skim", "whole", "one_percent", "two_percent"}
    if product_family == "milk" and (anchor_states & milk_fat_states) and not (product_states & milk_fat_states):
        return False, "milk_fat_state_missing"
    nut_product_forms = {"flour", "meal", "butter", "paste", "milk", "oil"}
    nut_whole_forms = {"whole", "raw", "roasted", "toasted", "sliced", "slivered", "chopped"}
    if product_family == "nut_seed":
        if (anchor_states & nut_product_forms) and not (product_states & nut_product_forms):
            return False, "nut_processed_form_missing"
        if (anchor_states & nut_whole_forms) and (product_states & nut_product_forms):
            return False, "nut_whole_processed_form_mismatch"
    if not state_compatible(product_states, set(anchor.tokens)):
        return False, "state_mismatch"

    if not matcher.subtype_compatible(set(title) | set(ingredients), set(anchor.tokens), product_family):
        return False, "subtype_mismatch"

    return True, "ok"


def build_product_features(products: pd.DataFrame, current: pd.DataFrame) -> pd.DataFrame:
    assignment_cols = [
        "best_esha_code", "best_esha_description", "best_esha_family",
        "score", "score_num", "n_candidates", "assignment_source",
    ]
    # FDC id is the row identity in this corpus. GTINs are not unique, and
    # joining current assignments by GTIN can cross-pollinate duplicate UPC rows.
    merge_key = "fdc_id" if "fdc_id" in current.columns and "fdc_id" in products.columns else "gtin_upc"
    current_cols = [merge_key] + [c for c in assignment_cols if c in current.columns]
    current_keyed = current[current_cols].drop_duplicates(merge_key, keep="first")
    df = products.merge(
        current_keyed,
        on=merge_key,
        how="left",
    )
    df["best_esha_code"] = df["best_esha_code"].fillna("")
    df["assignment_source"] = df["assignment_source"].fillna("")
    df["_ingredient_tokens"] = df["ingredients"].astype(str).map(tokenize_ingredients)
    df["_ingredient_key"] = df["_ingredient_tokens"].map(ingredient_key)
    df["_ingredient_token_count"] = df["_ingredient_tokens"].map(lambda xs: len(set(xs)))
    df["_title_tokens"] = df["product_description"].astype(str).map(title_tokens)
    df["_primary"] = df["_title_tokens"].map(primary_food)
    df["_product_family"] = df.apply(
        lambda r: product_family_for(str(r["product_description"]), str(r["branded_food_category"]), r["_title_tokens"]),
        axis=1,
    )
    df["_state_lane"] = df.apply(
        lambda r: state_lane(str(r["product_description"]), str(r["branded_food_category"]), r["_title_tokens"]),
        axis=1,
    )
    df["_ingredient_profile_key"] = df.apply(
        lambda r: ingredient_profile_key(
            r["_ingredient_tokens"],
            str(r["_product_family"]),
            str(r["_primary"]),
        ),
        axis=1,
    )
    df["_cluster_id"] = df.apply(
        lambda r: cluster_id_for(
            (
                r["_ingredient_key"],
                str(r["_product_family"]),
                str(r["_primary"]),
                str(r["_state_lane"]),
            )
        )
        if r["_ingredient_key"] else "",
        axis=1,
    )
    df["_profile_cluster_id"] = df.apply(
        lambda r: cluster_id_for(
            (
                r["_ingredient_profile_key"],
                str(r["_product_family"]),
                str(r["_primary"]),
                str(r["_state_lane"]),
            )
        )
        if r["_ingredient_profile_key"] else "",
        axis=1,
    )
    return df


def top_values(values: pd.Series, limit: int = 3) -> str:
    counts = Counter(v for v in values.astype(str) if v)
    return " | ".join(f"{k}:{v}" for k, v in counts.most_common(limit))


def choose_cluster_anchor(group: pd.DataFrame, anchors: dict[str, EshaAnchor]) -> dict[str, object]:
    valid = group[group["_anchor_valid"]].copy()
    if valid.empty:
        return {
            "safe_to_apply": False,
            "reject_reason": "no_valid_anchor",
            "anchor_code": "",
            "anchor_description": "",
            "anchor_family": "",
            "anchor_rows": 0,
            "anchor_weight": 0.0,
            "anchor_share": 0.0,
        }

    code_weights = valid.groupby("best_esha_code")["_anchor_weight"].sum().sort_values(ascending=False)
    code_rows = valid.groupby("best_esha_code").size().sort_values(ascending=False)
    top_code = str(code_weights.index[0])
    top_weight = float(code_weights.iloc[0])
    total_weight = float(code_weights.sum())
    share = top_weight / max(total_weight, 1e-9)
    top_rows = int(code_rows.get(top_code, 0))
    anchor = anchors.get(top_code)

    cluster_n = len(group)
    family_counts = valid.groupby("best_esha_family")["_anchor_weight"].sum().sort_values(ascending=False)
    family_share = float(family_counts.iloc[0] / max(family_counts.sum(), 1e-9)) if len(family_counts) else 0.0

    safe = True
    reason = "ok"
    if cluster_n < 2:
        safe, reason = False, "singleton_cluster"
    elif cluster_n >= 20 and top_rows < 3:
        safe, reason = False, "insufficient_anchor_support"
    elif cluster_n >= 5 and top_rows < 2:
        safe, reason = False, "insufficient_anchor_support"
    elif top_rows < 2 and top_weight < 3.0:
        safe, reason = False, "insufficient_anchor_support"
    elif share < 0.67:
        safe, reason = False, "weak_code_consensus"
    elif family_share < 0.80:
        safe, reason = False, "weak_family_consensus"
    elif anchor is None:
        safe, reason = False, "missing_top_anchor"

    return {
        "safe_to_apply": bool(safe),
        "reject_reason": reason,
        "anchor_code": top_code,
        "anchor_description": anchor.description if anchor else "",
        "anchor_family": anchor.family if anchor else "",
        "anchor_rows": top_rows,
        "anchor_weight": round(top_weight, 4),
        "anchor_share": round(share, 4),
    }


def build_clusters(features: pd.DataFrame, anchors: dict[str, EshaAnchor]) -> tuple[pd.DataFrame, pd.DataFrame]:
    features["_anchor_valid"] = False
    features["_anchor_reason"] = ""
    features["_anchor_weight"] = 0.0

    for idx, row in features.iterrows():
        code = str(row.get("best_esha_code") or "").split(".")[0]
        ok, reason, weight = anchor_gate(row, anchors.get(code))
        features.at[idx, "_anchor_valid"] = ok
        features.at[idx, "_anchor_reason"] = reason
        features.at[idx, "_anchor_weight"] = weight

    cluster_rows: list[dict[str, object]] = []
    proposals: list[dict[str, object]] = []
    proposed_gtins: set[str] = set()

    def process_group(cluster_id: str, group: pd.DataFrame, cluster_type: str, key_col: str) -> None:
        decision = choose_cluster_anchor(group, anchors)
        examples = " || ".join(group["product_description"].astype(str).head(5))
        bad_reasons = top_values(group.loc[~group["_anchor_valid"], "_anchor_reason"], limit=4)
        row = {
            "cluster_id": cluster_id,
            "cluster_type": cluster_type,
            "n_products": int(len(group)),
            "ingredient_token_count": int(group["_ingredient_token_count"].iloc[0]),
            "product_family": str(group["_product_family"].iloc[0]),
            "primary_food": str(group["_primary"].iloc[0]),
            "state_lane": str(group["_state_lane"].iloc[0]),
            "ingredient_key": str(group[key_col].iloc[0]),
            "top_categories": top_values(group["branded_food_category"]),
            "top_current_codes": top_values(group["best_esha_code"]),
            "valid_anchor_rows": int(group["_anchor_valid"].sum()),
            "invalid_anchor_reasons": bad_reasons,
            "examples": examples,
            **decision,
        }
        cluster_rows.append(row)

        if not decision["safe_to_apply"]:
            return
        new_code = str(decision["anchor_code"])
        anchor = anchors.get(new_code)
        if not anchor:
            return
        for _, product in group.iterrows():
            gtin = str(product["gtin_upc"])
            if gtin in proposed_gtins:
                continue
            old_code = str(product.get("best_esha_code") or "").split(".")[0]
            if old_code == new_code:
                continue
            candidate_ok, _candidate_reason = candidate_gate(product, anchor)
            if not candidate_ok:
                continue
            proposals.append(
                {
                    "gtin_upc": gtin,
                    "product_description": product["product_description"],
                    "branded_food_category": product["branded_food_category"],
                    "brand_owner": product["brand_owner"],
                    "brand_name": product["brand_name"],
                    "cluster_id": cluster_id,
                    "cluster_type": cluster_type,
                    "cluster_n": int(len(group)),
                    "ingredient_token_count": int(product["_ingredient_token_count"]),
                    "ingredient_key": product[key_col],
                    "product_family": product["_product_family"],
                    "primary_food": product["_primary"],
                    "state_lane": product["_state_lane"],
                    "old_esha_code": old_code,
                    "old_esha_description": product.get("best_esha_description", ""),
                    "old_esha_family": product.get("best_esha_family", ""),
                    "old_assignment_source": product.get("assignment_source", ""),
                    "old_score": product.get("score", ""),
                    "proposed_esha_code": new_code,
                    "proposed_esha_description": anchor.description,
                    "proposed_esha_family": anchor.family,
                    "anchor_rows": int(decision["anchor_rows"]),
                    "anchor_weight": decision["anchor_weight"],
                    "anchor_share": decision["anchor_share"],
                    "proposal_source": f"ingredient_{cluster_type}_cluster",
                }
            )
            proposed_gtins.add(gtin)

    exact = features[(features["_cluster_id"] != "") & (features["_ingredient_token_count"] > 0)].copy()
    for cluster_id, group in exact.groupby("_cluster_id", sort=False):
        process_group(str(cluster_id), group, "fingerprint", "_ingredient_key")

    profile = features[(features["_profile_cluster_id"] != "") & (features["_ingredient_token_count"] > 0)].copy()
    for cluster_id, group in profile.groupby("_profile_cluster_id", sort=False):
        process_group(str(cluster_id), group, "profile", "_ingredient_profile_key")

    return pd.DataFrame(cluster_rows), pd.DataFrame(proposals)


def build_assignment_quarantine(features: pd.DataFrame, anchors: dict[str, EshaAnchor]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    assigned = features[features["best_esha_code"].astype(str).str.strip() != ""]
    for _, product in assigned.iterrows():
        code = str(product.get("best_esha_code") or "").split(".")[0]
        anchor = anchors.get(code)
        ok, reason = candidate_gate(product, anchor)
        if ok:
            continue
        evidence = set(product["_title_tokens"]) | set(product["_ingredient_tokens"])
        form_reason = form_mismatch_reason(product, anchor, evidence) if anchor is not None else None
        display_reason = form_reason if form_reason in HARD_FORM_MISMATCH_REASONS else reason
        hard = hard_quarantine(product, anchor, reason)
        rows.append(
            {
                "gtin_upc": product["gtin_upc"],
                "fdc_id": product["fdc_id"],
                "product_description": product["product_description"],
                "branded_food_category": product["branded_food_category"],
                "brand_owner": product["brand_owner"],
                "brand_name": product["brand_name"],
                "current_esha_code": code,
                "current_esha_description": product.get("best_esha_description", ""),
                "current_esha_family": product.get("best_esha_family", ""),
                "assignment_source": product.get("assignment_source", ""),
                "score": product.get("score", ""),
                "product_family": product["_product_family"],
                "primary_food": product["_primary"],
                "state_lane": product["_state_lane"],
                "ingredient_key": product["_ingredient_key"],
                "quarantine_reason": display_reason,
                "hard_quarantine": hard,
            }
        )
    return pd.DataFrame(rows)


def hard_quarantine(row: pd.Series, anchor: EshaAnchor | None, reason: str) -> bool:
    if anchor is None:
        return False
    desc = str(row.get("product_description") or "").lower()
    category = str(row.get("branded_food_category") or "").lower()
    anchor_text = anchor.description.lower()
    evidence = set(row["_title_tokens"]) | set(row["_ingredient_tokens"])
    product_states = explicit_states(evidence | set(str(row["_state_lane"]).split("+")))

    form_reason = form_mismatch_reason(row, anchor, evidence)
    if form_reason in HARD_FORM_MISMATCH_REASONS:
        return True
    if reason in HARD_FORM_MISMATCH_REASONS:
        return True
    if is_infant_food_anchor(anchor_text, set(anchor.tokens)) and not is_infant_product(desc, category, evidence):
        return True
    if reason == "cherry_applesauce_without_cherry_anchor":
        return True
    if "applesauce" in anchor_text and ({"jelly", "jam", "preserve", "preserves"} & evidence):
        return True
    if "applesauce" in anchor_text and ({"rub", "seasoning", "spice"} & evidence):
        return True
    if anchor.family == "plant_milk" and any(c in category for c in ("chocolate", "candy", "confectionery")):
        return True
    if anchor.family == "plant_milk" and ("milk additives" in category or "creamer" in evidence):
        return True
    if anchor.family == "plant_milk" and ({"shake", "meal", "replacement"} & evidence) and "almond" not in set(row["_ingredient_tokens"]):
        return True
    if anchor.family == "nut_seed" and "meal" in anchor_text and "bars" in category:
        return True
    if anchor.family == "nut_seed" and "meal" in anchor_text and "meal" not in product_states and "flour" not in product_states:
        if any(c in category for c in ("peanuts", "seeds", "related snacks")):
            return True
    return False


def apply_proposals(
    current: pd.DataFrame,
    proposals: pd.DataFrame,
    quarantine: pd.DataFrame | None = None,
    *,
    quarantine_invalid_current: bool = False,
) -> pd.DataFrame:
    apply = (
        proposals.drop_duplicates("gtin_upc", keep="first").set_index("gtin_upc")
        if not proposals.empty
        else pd.DataFrame()
    )
    out = current.copy()
    diff_parts: list[pd.DataFrame] = []

    if not apply.empty:
        matched = out["gtin_upc"].isin(apply.index)
        before = out.loc[matched, [
            "gtin_upc", "best_esha_code", "best_esha_description", "best_esha_family", "assignment_source"
        ]].copy()
        before = before.rename(
            columns={
                "best_esha_code": "old_esha_code",
                "best_esha_description": "old_esha_description",
                "best_esha_family": "old_esha_family",
                "assignment_source": "old_assignment_source",
            }
        )

        out.loc[matched, "best_esha_code"] = out.loc[matched, "gtin_upc"].map(apply["proposed_esha_code"])
        out.loc[matched, "best_esha_description"] = out.loc[matched, "gtin_upc"].map(apply["proposed_esha_description"])
        out.loc[matched, "best_esha_family"] = out.loc[matched, "gtin_upc"].map(apply["proposed_esha_family"])
        out.loc[matched, "score"] = out.loc[matched, "gtin_upc"].map(apply["anchor_share"]).astype(str)
        out.loc[matched, "assignment_source"] = out.loc[matched, "gtin_upc"].map(apply["proposal_source"])

        after = out.loc[matched, ["gtin_upc", "best_esha_code", "best_esha_description", "best_esha_family"]].copy()
        after = after.rename(
            columns={
                "best_esha_code": "new_esha_code",
                "best_esha_description": "new_esha_description",
                "best_esha_family": "new_esha_family",
            }
        )
        meta_cols = ["cluster_id", "cluster_type", "anchor_rows", "anchor_share", "proposal_source"]
        meta = apply[[c for c in meta_cols if c in apply.columns]].reset_index()
        diff_parts.append(before.merge(after, on="gtin_upc", how="left").merge(meta, on="gtin_upc", how="left"))

    if quarantine_invalid_current and quarantine is not None and not quarantine.empty:
        proposed_gtins = set(apply.index) if not apply.empty else set()
        q = quarantine[
            (quarantine["hard_quarantine"] == True)
            & (~quarantine["gtin_upc"].isin(proposed_gtins))
        ].drop_duplicates("gtin_upc", keep="first")
        q_apply = q.set_index("gtin_upc")
        matched_q = out["gtin_upc"].isin(q_apply.index) & (out["best_esha_code"].astype(str).str.strip() != "")
        before_q = out.loc[matched_q, [
            "gtin_upc", "best_esha_code", "best_esha_description", "best_esha_family", "assignment_source"
        ]].copy()
        before_q = before_q.rename(
            columns={
                "best_esha_code": "old_esha_code",
                "best_esha_description": "old_esha_description",
                "best_esha_family": "old_esha_family",
                "assignment_source": "old_assignment_source",
            }
        )
        out.loc[matched_q, "best_esha_code"] = ""
        out.loc[matched_q, "best_esha_description"] = ""
        out.loc[matched_q, "best_esha_family"] = ""
        out.loc[matched_q, "score"] = ""
        if "n_candidates" in out.columns:
            out.loc[matched_q, "n_candidates"] = "0"
        out.loc[matched_q, "assignment_source"] = "ingredient_candidate_gate_quarantine"

        after_q = out.loc[matched_q, ["gtin_upc", "best_esha_code", "best_esha_description", "best_esha_family"]].copy()
        after_q = after_q.rename(
            columns={
                "best_esha_code": "new_esha_code",
                "best_esha_description": "new_esha_description",
                "best_esha_family": "new_esha_family",
            }
        )
        meta_q = q_apply[["quarantine_reason"]].reset_index()
        diff_q = before_q.merge(after_q, on="gtin_upc", how="left").merge(meta_q, on="gtin_upc", how="left")
        diff_q["proposal_source"] = "ingredient_candidate_gate_quarantine"
        diff_parts.append(diff_q)

    applied = out
    applied["best_esha_head"] = applied["best_esha_description"].astype(str).map(
        lambda value: value.split(",", 1)[0].strip() if value.strip() else ""
    )
    output_fields = [c for c in FIELDNAMES if c in applied.columns]
    if "best_esha_head" in applied.columns and "best_esha_head" not in output_fields:
        insert_at = output_fields.index("best_esha_description") + 1 if "best_esha_description" in output_fields else len(output_fields)
        output_fields.insert(insert_at, "best_esha_head")
    applied = applied[output_fields]
    applied.to_csv(OUT_APPLIED, index=False)
    diff_df = pd.concat(diff_parts, ignore_index=True) if diff_parts else pd.DataFrame()
    diff_df.to_csv(OUT_APPLIED_DIFF, index=False)
    return applied


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-map", type=Path, default=DEFAULT_MAP_CSV)
    parser.add_argument("--apply", action="store_true", help="also write product_to_best_esha_full_map.vM.csv")
    parser.add_argument(
        "--quarantine-invalid-current",
        action="store_true",
        help="when applying vM, blank current assignments that fail the ingredient/category candidate gate and have no safe cluster replacement",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("loading products", flush=True)
    products = load_products()
    print(f"  products: {len(products):,}", flush=True)

    print(f"loading current map: {args.current_map}", flush=True)
    current = load_current_map(args.current_map)
    print(f"  map rows: {len(current):,}", flush=True)

    print("loading ESHA anchors", flush=True)
    anchors = load_esha_anchors()
    print(f"  anchors: {len(anchors):,}", flush=True)

    print("building ingredient fingerprint features", flush=True)
    features = build_product_features(products, current)
    with_ingredients = int((features["_ingredient_token_count"] > 0).sum())
    print(f"  rows with ingredient tokens: {with_ingredients:,}", flush=True)

    print("building clusters and proposals", flush=True)
    clusters, proposals = build_clusters(features, anchors)
    clusters.to_csv(OUT_CLUSTERS, index=False)
    proposals.to_csv(OUT_PROPOSALS, index=False)
    print(f"  wrote {OUT_CLUSTERS.relative_to(ROOT)} ({len(clusters):,} clusters)", flush=True)
    print(f"  wrote {OUT_PROPOSALS.relative_to(ROOT)} ({len(proposals):,} proposals)", flush=True)

    print("validating current assignments", flush=True)
    quarantine = build_assignment_quarantine(features, anchors)
    quarantine.to_csv(OUT_QUARANTINE, index=False)
    print(f"  wrote {OUT_QUARANTINE.relative_to(ROOT)} ({len(quarantine):,} rows)", flush=True)

    safe_clusters = clusters[clusters.get("safe_to_apply", False) == True] if not clusters.empty else clusters
    summary = {
        "products": int(len(products)),
        "rows_with_ingredient_tokens": with_ingredients,
        "clusters": int(len(clusters)),
        "clusters_by_type": clusters["cluster_type"].value_counts().to_dict() if not clusters.empty and "cluster_type" in clusters else {},
        "clusters_size_ge_2": int((clusters["n_products"] >= 2).sum()) if not clusters.empty else 0,
        "safe_clusters": int(len(safe_clusters)),
        "safe_clusters_by_type": safe_clusters["cluster_type"].value_counts().to_dict() if not safe_clusters.empty and "cluster_type" in safe_clusters else {},
        "proposals": int(len(proposals)),
        "proposals_by_source": proposals["proposal_source"].value_counts().to_dict() if not proposals.empty else {},
        "proposal_old_unassigned": int((proposals["old_esha_code"].astype(str) == "").sum()) if not proposals.empty else 0,
        "proposal_old_assigned": int((proposals["old_esha_code"].astype(str) != "").sum()) if not proposals.empty else 0,
        "current_assignment_quarantine": int(len(quarantine)),
        "current_assignment_hard_quarantine": int(quarantine["hard_quarantine"].sum()) if not quarantine.empty else 0,
        "current_assignment_quarantine_reasons": quarantine["quarantine_reason"].value_counts().head(20).to_dict() if not quarantine.empty else {},
        "current_assignment_hard_quarantine_reasons": quarantine[quarantine["hard_quarantine"] == True]["quarantine_reason"].value_counts().head(20).to_dict() if not quarantine.empty else {},
        "top_proposed_codes": proposals["proposed_esha_code"].value_counts().head(20).to_dict() if not proposals.empty else {},
        "cluster_reject_reasons": clusters["reject_reason"].value_counts().to_dict() if not clusters.empty else {},
    }

    if args.apply:
        print("applying proposals to vM map", flush=True)
        applied = apply_proposals(
            current,
            proposals,
            quarantine,
            quarantine_invalid_current=args.quarantine_invalid_current,
        )
        summary["applied_output_csv"] = str(OUT_APPLIED)
        summary["applied_assignments"] = int((applied["best_esha_code"].astype(str).str.strip() != "").sum())
        summary["applied_diff_csv"] = str(OUT_APPLIED_DIFF)
        summary["quarantine_invalid_current_applied"] = bool(args.quarantine_invalid_current)
        summary["applied_quarantined_assignments"] = int((applied["assignment_source"] == "ingredient_candidate_gate_quarantine").sum())
        print(f"  wrote {OUT_APPLIED.relative_to(ROOT)}", flush=True)
        print(f"  wrote {OUT_APPLIED_DIFF.relative_to(ROOT)}", flush=True)

    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
