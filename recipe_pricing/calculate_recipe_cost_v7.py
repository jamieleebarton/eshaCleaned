#!/usr/bin/env python3
"""Recipe cost + macros calculator v7.

End-to-end planner. For a given recipe:
  - Loads the recipe-line classifications + grams
  - For each line, picks ONE Walmart/Kroger SKU using the canonical_path
    lookup we built
  - Filters by user facets (claims) if any
  - Picks cheapest cents/gram from matching SKUs
  - Computes line attributable cost = grams × cents/gram
  - Aggregates: shopping cart (full SKU prices), recipe-attributable cost,
    decision points (alternations, optional, specialty, broken)

Inputs:
  recipes_unified.csv                          (qty, grams, htc_code per line)
  buyability_classifications_cleaned.jsonl     (canonical_buy_form, usage, etc.)
  buy_form_to_canonical_path.csv               (lookup we just built)
  priced_products_v2.db                        (Walmart/Kroger products)

Usage:
  python3 calculate_recipe_cost_v7.py --recipe-id 233694
  python3 calculate_recipe_cost_v7.py --recipe-ids 233694,300767,25640
  python3 calculate_recipe_cost_v7.py --random 5
  python3 calculate_recipe_cost_v7.py --random 5 --facets organic,low_fat
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
CLEANED_CLS = ROOT / "recipe_pricing" / "buyability_classifications_cleaned.jsonl"
BUY_FORM_LOOKUP = ROOT / "recipe_pricing" / "buy_form_to_canonical_path.csv"
PRICED_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
EXCLUDED_UPCS = ROOT / "recipe_pricing" / "priced_products_excluded.csv"
FNDDS_NUTRIENTS = ROOT / "data" / "fndds" / "fndds_nutrient_lookup.csv"
PRODUCT_CLAIMS = ROOT / "recipe_pricing" / "product_claims.csv"


# Non-food / wrong-identity name filters — exclude products whose name contains
# these tokens unless the canonical itself does. Catches priced_products bridge errors.
NONFOOD_NOISE = {
    "water softener", "softener", "salt pellets", "fertilizer", "lotion",
    "soap", "candle", "scrub", "cleaning", "cleaner", "deodorant",
    "shampoo", "conditioner", "essential oil", "fragrance",
    "fishing line", "candle wick",
    # Baby food: must NEVER be picked for adult recipes unless recipe
    # explicitly says baby/infant food.
    "baby food", "infant food", "for toddlers", "for infants",
    "stage 1", "stage 2", "stage 3", "beech-nut", "gerber baby",
    "earth's best organic baby",
}
IDENTITY_CONFLICT = {
    "butter":      ["pecan", "peanut butter", "almond butter", "cashew butter",
                    "sunflower butter", "ice cream", "syrup", "flavor",
                    "popcorn topper", "candy", "bread & butter"],
    "salt":        ["water softener", "softener", "salt pellets", "rock salt",
                    "epsom", "bath", "for water", "ice melt"],
    "cream":       ["ice cream", "cream cheese", "sour cream", "whipped cream",
                    "shaving", "lotion"],
    "milk":        ["milk chocolate", "milk powder", "powdered milk"],
    "sugar":       ["sugar substitute", "sugar free", "sugar cookie"],
    "egg":         ["egg roll", "egg substitute", "egg replacer"],
    "eggs":        ["egg substitute", "egg replacer"],
}


@dataclass
class LineResult:
    line_index: int
    raw_display: str
    raw_item: str
    qty: float
    unit: str
    grams: float
    canonical_buy_form: str
    canonical_path: str
    buyability: str
    usage: str
    extracted_claims: list[str]
    base_ingredients: list[str]
    decision: str           # calculate | shop_only | skip | review
    sku_name: str = ""
    sku_brand: str = ""
    sku_upc: str = ""
    sku_grams: float = 0.0
    sku_cents: int = 0
    sku_cpg: float = 0.0
    line_cost_cents: float = 0.0
    # macros for THIS line's contribution
    line_kcal: float = 0.0
    line_protein_g: float = 0.0
    line_fat_g: float = 0.0
    line_carb_g: float = 0.0
    line_fiber_g: float = 0.0
    line_sodium_mg: float = 0.0
    note: str = ""


@dataclass
class RecipeResult:
    recipe_id: str
    recipe_title: str
    user_facets: list[str]
    lines: list[LineResult] = field(default_factory=list)
    shopping_list: list[tuple[str, str, int]] = field(default_factory=list)  # (canonical, sku_name, sku_cents)
    cart_total_cents: int = 0
    line_total_cents: float = 0.0
    # Recipe-level macro totals (sum of line contributions)
    total_kcal: float = 0.0
    total_protein_g: float = 0.0
    total_fat_g: float = 0.0
    total_carb_g: float = 0.0
    total_fiber_g: float = 0.0
    total_sodium_mg: float = 0.0
    decision_points: list[str] = field(default_factory=list)
    broken_flags: list[str] = field(default_factory=list)
    coverage: dict = field(default_factory=lambda: Counter())


# ---------------------------------------------------------------------------
# Index loaders
# ---------------------------------------------------------------------------
def load_unified() -> dict[str, list[dict]]:
    """recipe_id → [line_row, ...] in original order."""
    out: defaultdict[str, list[dict]] = defaultdict(list)
    with UNIFIED.open(newline="") as f:
        for row in csv.DictReader(f):
            rid = str(row.get("recipe_id", "")).strip()
            if rid:
                out[rid].append(row)
    return out


_QTY_PREFIX = re.compile(
    r"^(\d+(?:\.\d+)?(?:\s*[\-\/]\s*\d+(?:\.\d+)?)?\s*)?"
    r"(small|medium|large|extra large|big|jumbo|baby|tiny|whole|half|quarter|one|two|three|"
    r"a |an |several |few |handful |bunch of |head of |sprig of |slice of |piece of |can of |"
    r"package of |bag of |box of |jar of |bottle of )*",
    re.I,
)
_PREP_SUFFIX = re.compile(
    r",?\s*(diced|minced|chopped|sliced|cubed|grated|shredded|crushed|halved|"
    r"quartered|peeled|seeded|cored|trimmed|drained|rinsed|softened|melted|"
    r"warmed|toasted|cooked|raw|fresh|frozen|pounded|finely|coarsely|thinly|"
    r"thickly|cut into [^,]+|to taste|optional|for garnish|for serving|"
    r"for frying|for drizzling|or more|approximately).*$",
    re.I,
)
_NUM_UNIT_PREFIX = re.compile(
    r"^\s*\d+(?:\s*[\-\/]\s*\d+(?:\.\d+)?)?\s*"
    r"(?:bunch|cup|pint|quart|gallon|tablespoon|tbsp|teaspoon|tsp|"
    r"ounce|oz|pound|lb|gram|g|ml|liter|piece|slice|head|clove|sprig)s?\s+",
    re.I,
)


def _strip_buy_form_noise(buy_form: str) -> str:
    """Aggressive cleanup: drop leading qty+unit+adjectives and trailing prep."""
    s = buy_form.strip()
    # Remove leading "<num> <unit>" repeatedly
    while True:
        new = _NUM_UNIT_PREFIX.sub("", s)
        if new == s: break
        s = new
    # Remove leading qty + size adjectives
    s = _QTY_PREFIX.sub("", s).strip()
    # Drop trailing prep / "to taste" / "for garnish"
    s = _PREP_SUFFIX.sub("", s).strip()
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # Drop leading articles
    s = re.sub(r"^(a|an|the)\s+", "", s, flags=re.I).strip()
    return s


def load_classifications() -> dict[str, list[dict]]:
    """recipe_id → list of classification dicts (line_index aligned with ingredients order)."""
    out: dict[str, list[dict]] = {}
    with CLEANED_CLS.open() as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = str(r.get("recipe_id", ""))
            if rid:
                cls = sorted(r.get("classifications", []), key=lambda c: c.get("line_index", 0))
                out[rid] = cls
    return out


def load_buy_form_lookup() -> tuple[dict[str, str], set[str]]:
    """Returns (canonical_buy_form → canonical_path, overridden_set).
    Applies sidecar overrides last (so manual fixes win over auto-resolution).
    Tracks which canonical_buy_forms came from a manual override — the
    calculator skips the head-noun filter for those (override is trusted).

    Special override value `DERIVATIVE` marks the canonical_buy_form as
    derived from base ingredients (e.g. lemon zest from a lemon)."""
    out: dict[str, str] = {}
    overridden: set[str] = set()
    with BUY_FORM_LOOKUP.open() as f:
        for row in csv.DictReader(f):
            bf = (row.get("canonical_buy_form") or "").lower().strip()
            cp = (row.get("canonical_path") or "").strip()
            if bf and cp:
                out[bf] = cp
    overrides_path = ROOT / "recipe_pricing" / "buy_form_path_overrides.csv"
    if overrides_path.exists():
        with overrides_path.open() as f:
            for row in csv.DictReader(f):
                bf = (row.get("canonical_buy_form") or "").lower().strip()
                cp = (row.get("canonical_path") or "").strip()
                if bf and cp:
                    out[bf] = cp
                    overridden.add(bf)
    return out, overridden


def load_excluded_upcs() -> set[str]:
    """UPCs of products to skip (bridge errors / non-food)."""
    out: set[str] = set()
    if EXCLUDED_UPCS.exists():
        with EXCLUDED_UPCS.open() as f:
            for row in csv.DictReader(f):
                upc = (row.get("upc") or "").strip()
                if upc:
                    out.add(upc)
    return out


def load_product_claims() -> dict[str, set[str]]:
    """upc → set of claim flags. Used for facet filtering at query time."""
    out: dict[str, set[str]] = {}
    if not PRODUCT_CLAIMS.exists():
        return out
    with PRODUCT_CLAIMS.open() as f:
        for row in csv.DictReader(f):
            upc = (row.get("upc") or "").strip()
            claims_str = (row.get("claims") or "").strip()
            if not upc or not claims_str:
                continue
            claims = {c.strip() for c in claims_str.split("|") if c.strip()}
            if claims:
                out[upc] = claims
    return out


def load_fndds_macros() -> dict[str, dict]:
    """fndds_code → {kcal, protein, fat, carb, fiber, sodium} per 100g."""
    out: dict[str, dict] = {}
    if not FNDDS_NUTRIENTS.exists():
        return out
    with FNDDS_NUTRIENTS.open() as f:
        for row in csv.DictReader(f):
            code = (row.get("fndds_code") or "").strip()
            if not code:
                continue
            try:
                out[code] = {
                    "kcal":      float(row.get("energy_kcal") or 0),
                    "protein_g": float(row.get("protein_g") or 0),
                    "fat_g":     float(row.get("fat_g") or 0),
                    "carb_g":    float(row.get("carbs_g") or 0),
                    "fiber_g":   float(row.get("fiber_g") or 0),
                    "sodium_mg": float(row.get("sodium_mg") or 0),
                }
            except ValueError:
                continue
    return out


SR28_NUTRIENTS = ROOT / "data" / "sr28" / "sr28_nutrient_lookup.csv"


def _macros_for(prod: dict, fndds_lookup: dict, sr28_lookup: dict) -> tuple[dict | None, str]:
    """Return (macros, source) for a picked SKU. Tries the SKU's own
    consensus_fndds first; falls back to consensus_sr28 if FNDDS missing.
    Returns (None, '') when neither resolves."""
    fndds = (prod.get("fndds") or "").strip()
    if fndds and fndds in fndds_lookup:
        return fndds_lookup[fndds], "fndds"
    sr28 = (prod.get("sr28") or "").strip()
    if sr28 and sr28 in sr28_lookup:
        return sr28_lookup[sr28], "sr28"
    return None, ""

def load_sr28_macros() -> dict[str, dict]:
    """ndb_number → {kcal, protein, fat, carb, fiber, sodium} per 100g.
    Used as fallback when a SKU's consensus_fndds isn't in fndds_nutrient_lookup."""
    out: dict[str, dict] = {}
    if not SR28_NUTRIENTS.exists():
        return out
    with SR28_NUTRIENTS.open() as f:
        for row in csv.DictReader(f):
            code = (row.get("ndb") or "").strip()
            if not code: continue
            try:
                out[code] = {
                    "kcal":      float(row.get("energy_kcal") or 0),
                    "protein_g": float(row.get("protein_g") or 0),
                    "fat_g":     float(row.get("fat_g") or 0),
                    "carb_g":    float(row.get("carbs_g") or 0),
                    "fiber_g":   float(row.get("fiber_g") or 0),
                    "sodium_mg": float(row.get("sodium_mg") or 0),
                }
            except ValueError:
                continue
    return out


# ---------------------------------------------------------------------------
# SKU pick
# ---------------------------------------------------------------------------
# Words that don't need to match — form / processing / size descriptors
SOFT_WORDS = {
    "fresh", "dried", "ground", "powdered", "whole", "crushed", "chopped",
    "diced", "sliced", "minced", "grated", "shredded", "frozen", "raw",
    "cooked", "canned", "jarred", "pickled", "the", "a", "an", "of",
    "and", "or", "with", "for", "in", "to", "on",
    "small", "medium", "large", "extra", "big", "tiny",
}


def head_noun_words(canonical_buy_form: str) -> list[str]:
    """Return the meaningful nouns in canonical_buy_form, dropping
    form/processing/size descriptors. The LAST kept word is the head noun
    and must appear in the product name."""
    words = [w for w in canonical_buy_form.lower().split() if w]
    return [w for w in words if w not in SOFT_WORDS]


def _normalize_for_match(s: str) -> str:
    """Lowercase + strip hyphens + collapse spaces (so 'half-and-half' matches
    'half and half' and 'breadcrumbs' matches 'bread crumbs')."""
    s = s.lower()
    s = s.replace("-", " ")
    return " ".join(s.split())


# SKU-side modifiers that should NOT appear unless the recipe explicitly asks.
# Map: token in SKU name → token that must also appear in buy_form to allow.
ANTI_MODIFIERS = {
    "gluten free":     ["gluten", "gf"],
    "gluten-free":     ["gluten", "gf"],
    "sugar free":      ["sugar free", "sugarless", "diet"],
    "sugar-free":      ["sugar free", "sugarless", "diet"],
    "fat free":        ["fat free", "skim", "non fat", "nonfat"],
    "fat-free":        ["fat free", "skim", "non fat", "nonfat"],
    "skim":            ["skim", "fat free", "non fat", "nonfat"],
    "non fat":         ["skim", "fat free", "non fat", "nonfat"],
    "nonfat":          ["skim", "fat free", "non fat", "nonfat"],
    "low fat":         ["low fat", "lowfat", "reduced fat"],
    "low-fat":         ["low fat", "lowfat", "reduced fat"],
    "low sodium":      ["low sodium", "low salt", "reduced sodium"],
    "low-sodium":      ["low sodium", "low salt", "reduced sodium"],
    "diet ":           ["diet"],
    "lite ":           ["lite", "light"],
    "decaf":           ["decaf", "decaffeinated"],
    "organic":         ["organic"],
    "kosher":          ["kosher"],
    "halal":           ["halal"],
    "for toddlers":    ["toddler", "baby", "infant"],
    "for infants":     ["toddler", "baby", "infant"],
    "baby food":       ["baby"],
}

def passes_anti_modifier(name_l: str, bf_l: str) -> bool:
    for sku_token, allow_when in ANTI_MODIFIERS.items():
        if sku_token in name_l:
            if not any(a in bf_l for a in allow_when):
                return False
    return True


# Animal-protein paths that must reject plant-based imposters when the
# recipe doesn't ask for plant-based. We DO allow plant-based at:
#   - Meal > Plant Based > *  (intentional plant-based subtree)
#   - Meat & Seafood > Plant-Based Meats / Meat Alternatives (intentional)
#   - Dairy > Eggs > Egg Substitute (intentional)
_ANIMAL_PROTEIN_PATH_PREFIXES = (
    "Meat & Seafood > Beef",
    "Meat & Seafood > Poultry",
    "Meat & Seafood > Pork",
    "Meat & Seafood > Lamb",
    "Meat & Seafood > Bacon",
    "Meat & Seafood > Ham",
    "Meat & Seafood > Sausage",
    "Meat & Seafood > Hot Dogs",
    "Meat & Seafood > Chorizo",
    "Meat & Seafood > Deli Slices",
    "Meat & Seafood > Meatballs",
    "Meat & Seafood > Patties",
    "Meat & Seafood > Nuggets",
    "Dairy > Cheese",
    "Dairy > Yogurt",
    "Dairy > Milk",
    "Dairy > Butter",  # ‘Butter > Margarine’ inherits — handled by buy_form check below
    "Dairy > Cream",
)
_PLANT_MARKERS = (
    "beyond ", "impossible", "plant-based", "plant based",
    " vegan", "vegetarian", "meatless", "meat-free", "meat free",
    "tofu", "tempeh", "seitan",
    "dairy free", "dairy-free", "non-dairy", "non dairy",
    "soy crumble", "veggie burger", "veggie bacon", "veggie dog",
    "chick'n", "chik'n", "be'f", "saus'ge",
)


def _is_plant_at_animal_path(name: str, canonical_path: str,
                              canonical_buy_form: str) -> bool:
    """True iff the SKU is plant-based, the path is an animal-protein path,
    and the recipe's buy_form doesn't itself ask for plant-based.

    Strengthened: catches sibling-fallback slip-throughs by treating ANY
    Meat & Seafood / Dairy subpath as animal-protein UNLESS the path
    explicitly contains 'Plant-Based' / 'Meat Alternative' / 'Plant Milk'
    / 'Egg Substitute' segments."""
    if not canonical_path:
        return False
    cp_lower = canonical_path.lower()
    # Explicit plant-based subpaths are OK to keep plant SKUs at
    if any(seg in cp_lower for seg in (
        "plant-based", "plant based", "meat alternative", "plant milk",
        "egg substitute", "plant butter",
    )):
        return False
    # Explicit-list match (legacy)
    is_animal = any(canonical_path.startswith(p) for p in _ANIMAL_PROTEIN_PATH_PREFIXES)
    # Generalize: ANY Meat & Seafood subpath OR animal Dairy subpath
    if not is_animal:
        if canonical_path.startswith("Meat & Seafood"):
            is_animal = True
        elif canonical_path.startswith("Dairy") and not any(t in cp_lower for t in (
            "plant", "vegan", "non-dairy", "dairy-free", "almond milk",
            "soy milk", "oat milk", "coconut milk",
        )):
            is_animal = True
    if not is_animal:
        return False
    nl = (name or "").lower()
    if not any(t in nl for t in _PLANT_MARKERS):
        return False
    cl = (canonical_buy_form or "").lower()
    if any(t in cl for t in _PLANT_MARKERS):
        # Recipe explicitly wants plant-based (e.g. "vegan ground beef") — allow.
        return False
    return True


# Strong identity tokens. When recipe's canonical_buy_form contains the KEY,
# the picked SKU's name MUST contain at least one of the synonym values.
# This is enforced BEFORE the looser any-noun-match. Catches:
#   "whole wheat flour" → all-purpose flour (rejected)
#   "halibut fillets" → generic fish (rejected)
#   "bread dough" → corn muffin mix (rejected)
#   "buttermilk" → regular milk (rejected)
STRONG_IDENTITY_TOKENS: dict[str, tuple[str, ...]] = {
    # Form / preparation
    "whole wheat":  ("whole wheat", "wholewheat", "wholemeal", "whole grain"),
    "whole grain":  ("whole grain", "whole wheat", "wholewheat", "whole-wheat"),
    "self-rising":  ("self-rising", "self rising", "self-raising"),
    "dough":        ("dough",),
    # Fish species
    "halibut":   ("halibut",),
    "salmon":    ("salmon",),
    "tilapia":   ("tilapia",),
    "cod":       ("cod ", "cod,", "cod.", "atlantic cod", "pacific cod"),
    "swordfish": ("swordfish",),
    "tuna":      ("tuna",),
    "sardine":   ("sardine",),
    "anchovy":   ("anchovy", "anchovies"),
    "mackerel":  ("mackerel",),
    "trout":     ("trout",),
    "snapper":   ("snapper",),
    "grouper":   ("grouper",),
    # Meat species
    "lamb":      ("lamb",),
    "veal":      ("veal",),
    "duck":      ("duck",),
    "goose":     ("goose",),
    "venison":   ("venison",),
    "bison":     ("bison",),
    "rabbit":    ("rabbit",),
    # Specific bean
    "garbanzo":  ("garbanzo", "chickpea"),
    "chickpea":  ("chickpea", "garbanzo"),
    "kidney":    ("kidney",),
    "lima":      ("lima", "butter bean"),
    "cannellini":("cannellini", "white kidney"),
    "navy bean": ("navy",),
    "pinto":     ("pinto",),
    "black bean":("black bean",),
    "fava":      ("fava", "broad bean"),
    "lentil":    ("lentil",),
    "mung":      ("mung",),
    # Specific cheese / dairy
    "buttermilk":   ("buttermilk", "butter milk"),
    "ricotta":      ("ricotta",),
    "mascarpone":   ("mascarpone",),
    "feta":         ("feta",),
    "parmesan":     ("parmesan", "parmigiano"),
    "parmigiano":   ("parmesan", "parmigiano"),
    "ghee":         ("ghee",),
    "halloumi":     ("halloumi",),
    "manchego":     ("manchego",),
    "gruyere":      ("gruyere", "gruyère"),
    "asiago":       ("asiago",),
    # Specialty pantry
    "saffron":   ("saffron",),
    "tahini":    ("tahini", "sesame paste"),
    "miso":      ("miso",),
    "harissa":   ("harissa",),
    "gochujang": ("gochujang",),
    "pomegranate": ("pomegranate",),
    "mascarpone": ("mascarpone",),
    "matcha":    ("matcha",),
    # Extract flavors. Generic extract paths contain many flavors, so the
    # flavor word is identity, not a soft modifier.
    "vanilla extract": ("vanilla",),
    "almond extract": ("almond",),
    "lemon extract": ("lemon",),
    "peppermint extract": ("peppermint",),
    "orange extract": ("orange",),
    "maple extract": ("maple",),
    "rum extract": ("rum",),
    "anise extract": ("anise",),
    "coffee extract": ("coffee",),
    "coconut extract": ("coconut",),
    "cherry-flavored": ("cherry",),
    "cherry flavored": ("cherry",),
    # Specific oil
    "sesame oil": ("sesame",),
    "coconut oil": ("coconut",),
    "avocado oil": ("avocado",),
    # Specific rice / grain
    "basmati":   ("basmati",),
    "jasmine":   ("jasmine",),
    "arborio":   ("arborio",),
    "quinoa":    ("quinoa",),
    "couscous":  ("couscous",),
    "polenta":   ("polenta",),
    "millet":    ("millet",),
    "farro":     ("farro",),
    "barley":    ("barley",),
    "buckwheat": ("buckwheat",),
}


def _passes_strong_identity(name: str, canonical_buy_form: str) -> bool:
    """If the recipe's buy_form contains a STRONG_IDENTITY_TOKENS key, the
    SKU name must contain at least one synonym. Otherwise the SKU is the
    wrong food/form for this recipe."""
    nl = (name or "").lower()
    cl = (canonical_buy_form or "").lower()
    for key, synonyms in STRONG_IDENTITY_TOKENS.items():
        if key in cl:
            if not any(s in nl for s in synonyms):
                return False
    return True


# Multipack rejection — when recipe says "1 can" / "single can" / "one can"
# the picked SKU should NOT be a multipack. Detect: the SKU name contains
# "(N pack)" / "Pack of N" / "case of N" with N > 2.
import re as _re_mp
_MULTIPACK_RE = _re_mp.compile(
    r"\(?\s*(\d+)\s*[\-\s]*(?:ct|count|pk|pack|packs|case)\b"
    r"|pack\s+of\s+(\d+)\b",
    _re_mp.I,
)


def _is_multipack_for_single_can_recipe(name: str, canonical_buy_form: str) -> bool:
    """True if recipe asks for single can/jar/bottle but SKU is a multipack."""
    cl = (canonical_buy_form or "").lower()
    # Recipe wants a single unit
    wants_single = any(s in cl for s in (
        "1 can", "one can", "single can", "1 jar", "one jar",
        "1 bottle", "one bottle", "1 box", "one box",
    ))
    if not wants_single:
        return False
    nl = (name or "").lower()
    m = _MULTIPACK_RE.search(nl)
    if not m: return False
    for grp in m.groups():
        if grp:
            try:
                n = int(grp)
                if n > 2: return True
            except: continue
    return False


# Imposter-form tokens. SKUs matching any rule are rejected unless the
# recipe's canonical_buy_form / canonical_path explicitly asks for them.
# Each rule: (sku_token, requires_in_buy_form_or_path, applies_when_path_starts_with)
#   sku_token            — substring in SKU name that flags imposter
#   exemption_tokens     — if any of these is in buy_form, allow (recipe asked)
#   path_prefix_filter   — only apply rule when canonical_path starts with this
_IMPOSTER_RULES: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    # "imitation" never wanted unless recipe asks for it
    ("imitation",       ("imitation",),                 ()),
    # "cheese food" / "cheese product" are processed cheese substitutes
    ("cheese food",     ("cheese food", "cheese product"), ("Dairy",)),
    ("cheese product",  ("cheese product", "cheese food"), ("Dairy",)),
    # Bouillon / stock cube / concentrate at animal-protein paths means
    # the SKU is the *flavoring* not the protein itself.
    ("bouillon",        ("bouillon", "broth", "stock"),
        ("Meat & Seafood",)),
    ("stock cube",      ("stock cube", "bouillon", "broth"),
        ("Meat & Seafood",)),
    # Broth/stock recipes shouldn't pick "seasoning" packets.
    ("seasoning",       ("seasoning", "rub", "spice", "spice blend"),
        ("Pantry > Broth",)),
    # Vanilla "blend" is imitation vanilla — recipe asking for "extract"
    # gets the real thing only.
    ("blend",           ("blend",),
        ("Pantry > Baking Extracts",)),
    ("flavor",          ("flavor", "flavour"),
        ("Pantry > Baking Extracts",)),
]


def _is_imposter_for_recipe(name: str, canonical_buy_form: str,
                              canonical_path: str) -> bool:
    """Return True if SKU name matches a known imposter pattern that recipe
    didn't ask for. Used to reject e.g. Mexican Vanilla Blend for "vanilla
    extract", Knorr Shrimp Bouillon for "shrimp", Imitation Cheese for "cheese"."""
    nl = (name or "").lower()
    cl = (canonical_buy_form or "").lower()
    cp = canonical_path or ""
    for sku_tok, exempt_toks, path_prefix in _IMPOSTER_RULES:
        if sku_tok not in nl:
            continue
        if path_prefix and not any(cp.startswith(p) for p in path_prefix):
            continue
        if any(t in cl for t in exempt_toks):
            continue
        return True
    return False


def name_passes_filter(name: str, canonical_buy_form: str,
                         path_leaf: str = "",
                         canonical_path: str = "") -> bool:
    """Filter products at a path so we don't pick wildly off-identity SKUs.

    `path_leaf` is the leaf word of the canonical_path (e.g. 'Shrimp' for
    'Meat & Seafood > Shellfish > Shrimp'). When set, names matching the
    leaf word also pass — this lets override-substitutions (prawns → Shrimp)
    accept legitimate shrimp products even though 'prawn' isn't in the name.
    """
    nl_raw = name.lower()
    nl = _normalize_for_match(name)
    cl_raw = canonical_buy_form.lower()
    cl = _normalize_for_match(canonical_buy_form)
    # 0a. Plant-based at animal-protein path → reject (Beyond Chicken / Tofu Ham etc.)
    if _is_plant_at_animal_path(name, canonical_path, canonical_buy_form):
        return False
    # 0b. Strong identity tokens — recipe says "halibut" / "whole wheat" /
    # "buttermilk" / "dough" → SKU name MUST contain matching token.
    if not _passes_strong_identity(name, canonical_buy_form):
        return False
    # 0c. Multipack rejection — recipe wants single can; SKU is N-pack → reject.
    if _is_multipack_for_single_can_recipe(name, canonical_buy_form):
        return False
    # 0d. Imposter rejection — Mexican Vanilla Blend ≠ vanilla extract,
    # Knorr Shrimp Bouillon ≠ shrimp, Imitation Cheese ≠ cheese.
    if _is_imposter_for_recipe(name, canonical_buy_form, canonical_path):
        return False
    # 0. Anti-modifier: SKU has modifier that buy_form didn't request → reject
    if not passes_anti_modifier(nl_raw, cl_raw):
        return False
    # 1. Hardcoded non-food noise
    for noise in NONFOOD_NOISE:
        if noise in nl_raw and noise not in cl_raw:
            return False
    # 2. Hardcoded identity-conflict (butter pecan etc.)
    for c in IDENTITY_CONFLICT.get(cl_raw, []):
        if c in nl_raw:
            return False
    # 3. ANY-noun match — at least ONE meaningful word of canonical_buy_form
    #    OR the path's leaf word (for override-substitutions) must appear
    #    in product name.
    nouns = head_noun_words(canonical_buy_form)
    # Add path-leaf words as additional acceptable identity tokens
    if path_leaf:
        leaf_nouns = head_noun_words(path_leaf)
        for n in leaf_nouns:
            if n not in nouns:
                nouns.append(n)
    nl_nospace = nl.replace(" ", "")
    if nouns:
        any_match = False
        for noun in nouns:
            n = noun.replace("-", "")
            if (n in nl or (n + "s") in nl or n.rstrip("s") in nl
                or (n + "es") in nl):
                any_match = True
                break
            if (n in nl_nospace or (n + "s") in nl_nospace
                or n.rstrip("s") in nl_nospace):
                any_match = True
                break
        if not any_match:
            full_concat = "".join(nouns).replace("-", "")
            if full_concat in nl_nospace or (full_concat + "s") in nl_nospace:
                any_match = True
        if not any_match:
            return False
    return True


_FORM_ENCODER = None
def _get_form_encoder():
    global _FORM_ENCODER
    if _FORM_ENCODER is not None:
        return _FORM_ENCODER
    import sys as _s
    _root = str(Path(__file__).resolve().parents[1])
    if _root not in _s.path:
        _s.path.insert(0, _root)
    try:
        from recipe_mapper.v1.htc.encoder import encode as _enc
        _FORM_ENCODER = _enc
    except Exception as e:
        print(f"WARNING: form-aware encoder unavailable: {e!r}", file=_s.stderr)
        _FORM_ENCODER = False
    return _FORM_ENCODER


import re as _re
_RECIPE_LEAF_STOP = {"the","a","an","of","and","or","with","fresh","raw","organic","plain"}
def _recipe_filter_tokens(canonical_path: str, buy_form: str) -> list[str]:
    """Tokens from canonical_path leaf + buy_form that should appear in the
    picked SKU's name. Combines path leaf (for whole/skim/dijon/etc) with
    buy_form modifiers."""
    leaf = canonical_path.split(" > ")[-1].lower() if canonical_path else ""
    leaf_toks = [w for w in _re.findall(r"[a-z]+", leaf) if len(w)>2 and w not in _RECIPE_LEAF_STOP]
    bf_toks = [w for w in _re.findall(r"[a-z]+", (buy_form or "").lower()) if len(w)>2 and w not in _RECIPE_LEAF_STOP]
    seen = set(); out = []
    for w in leaf_toks + bf_toks:
        if w not in seen:
            seen.add(w); out.append(w)
    return out

def _encode_buy_form_form_aware(canonical_buy_form: str, canonical_path: str) -> str:
    """Encode the buy_form on the fly using identity_mode=False so we get a
    form/processing/ptype-bearing HTC. Returns 8-char code or '' on failure."""
    enc = _get_form_encoder()
    if not enc: return ""
    try:
        return enc("", description=canonical_buy_form,
                    food_name=canonical_buy_form,
                    canonical_path=canonical_path,
                    identity_mode=False).code
    except Exception:
        return ""


def _contextual_path_override(canonical_buy_form: str, display: str,
                              canonical_path: str) -> str:
    """Use recipe display text to recover shopping specificity.

    The classifier can collapse "unsweetened chocolate squares" to
    "chocolate" or "cherry-flavored craisins" to a candy-like path. The
    original recipe text still carries the shopping leaf, so repair that
    before querying products.
    """
    bf = _normalize_for_match(canonical_buy_form or "")
    text = _normalize_for_match(f"{canonical_buy_form or ''} {display or ''}")

    if "vanilla extract" in text:
        return "Pantry > Baking Extracts > Vanilla Extract"
    if "craisins" in text or "dried cranberr" in text:
        return "Snack > Dried Fruit > Dried Cranberries"
    if "chocolate chip" in text or "chocolate morsel" in text:
        return "Pantry > Chocolate Chips"
    if "chocolate" in text and ("square" in text or "baking square" in text):
        return "Snack > Chocolate Candy > Chocolate Squares"
    if "chocolate" in text and "baking bar" in text:
        return "Snack > Chocolate Candy > Chocolate Bar"
    if "caramels" in text and not any(t in bf for t in ("topping", "sauce", "syrup")):
        return "Snack > Candy > Caramel Candy"
    return canonical_path


def _total_spend(grams_needed: float, sku_grams: float, sku_cents: int) -> int:
    """Total cents you actually pay if buying enough whole packages of this SKU
    to cover grams_needed. ceil(need / size) × price.
    When grams_needed unknown, fall back to per-gram price (cpg) for ranking."""
    if not sku_grams or sku_grams <= 0 or not sku_cents:
        return 10**12
    if grams_needed <= 0:
        return sku_cents  # cpg-equivalent — picks cheapest pkg, which is fine
    import math
    n = max(1, math.ceil(grams_needed / sku_grams))
    return n * sku_cents


# Mix/sachet hint tokens. A SKU under 100g whose name contains any of these
# tokens is almost certainly a dry packet, not a liquid bottle.
_MIX_TOKENS = (" mix", " packet", " sachet", " powder", "instant ",
                "seasoning packet", " base", " bouillon")
SACHET_GRAMS = 100.0  # typical broth/gravy mix sachet ≤ 100g; liquid ≥ 100g


def _is_likely_dry_mix(name: str, grams: float) -> bool:
    """Heuristic: small package + name suggests dry-form."""
    if grams >= SACHET_GRAMS:
        return False
    nl = (name or "").lower()
    return any(t in nl for t in _MIX_TOKENS)


# Load canonical_path alias map at module import time. The map is curated;
# entries redirect a recipe-side canonical_path to the priced-side path
# where the actual SKUs live (cross-category fixes, spelling, redundant
# adjectives, etc.).
_PATH_ALIASES: dict[str, str] = {}
def _load_path_aliases() -> dict[str, str]:
    global _PATH_ALIASES
    if _PATH_ALIASES: return _PATH_ALIASES
    p = ROOT / "recipe_pricing" / "canonical_path_aliases.csv"
    if not p.exists(): return {}
    out: dict[str, str] = {}
    with p.open() as f:
        for row in csv.DictReader(f):
            old = (row.get("old_path") or "").strip()
            new = (row.get("new_path") or "").strip()
            if old and new and old != new:
                out[old] = new
    # Resolve transitive chains (a→b, b→c → a→c)
    for k in list(out.keys()):
        seen = {k}
        v = out[k]
        while v in out and v not in seen:
            seen.add(v); v = out[v]
        out[k] = v
    _PATH_ALIASES = out
    return out


def find_cheapest(con: sqlite3.Connection, canonical_path: str,
                   canonical_buy_form: str, user_facets: list[str],
                   excluded_upcs: set[str],
                   product_claims: dict[str, set[str]],
                   trust_override: bool = False,
                   grams_needed: float = 0.0) -> dict | None:
    """Pick a SKU. If the leaf-path winner is a tiny mix sachet (<100g named
    'mix/packet/etc') but the recipe needs >100g, that's a form mismatch:
    retry at parent path which usually has the liquid SKUs (e.g.
    'Broth & Stock > Turkey Broth' has only mix sachets, but parent
    'Broth & Stock' has 1,800+ liquid cartons including chicken/beef
    that the recipe author would substitute)."""
    # Apply canonical_path alias map FIRST. Recipe-side paths often differ
    # from priced-side paths (Pantry > Spices > Cilantro vs Produce >
    # Vegetables > Cilantro). Alias rewires the query to where SKUs live.
    aliases = _load_path_aliases()
    if canonical_path in aliases:
        canonical_path = aliases[canonical_path]
    prod = _find_at_path(con, canonical_path, canonical_buy_form, user_facets,
                          excluded_upcs, product_claims, trust_override,
                          grams_needed)
    # Sibling-fallback fires when:
    #   (a) the leaf-path winner is a tiny mix sachet but recipe wants bulk
    #       (e.g. "5 cups turkey broth" → 1180g need, leaf has only 27g
    #       gravy-mix sachets, parent has liquid broths)
    #   (b) the leaf path returned nothing (e.g. plant-based filter rejected
    #       the only SKU; recipe asks for chicken at a leaf where only
    #       Beyond Chicken existed — parent "Poultry" has real chicken).
    needs_fallback = False
    if prod is None and grams_needed >= SACHET_GRAMS:
        needs_fallback = True
    elif prod and grams_needed >= SACHET_GRAMS and \
         _is_likely_dry_mix(prod.get("name", ""), prod.get("grams", 0)):
        needs_fallback = True
    if needs_fallback:
        parent = " > ".join(canonical_path.split(" > ")[:-1])
        if parent:
            sibling = _find_liquid_under_prefix(
                con, parent, canonical_buy_form, user_facets,
                excluded_upcs, product_claims, trust_override, grams_needed,
                exclude_path=canonical_path,
            )
            if sibling:
                sibling["match"] = (sibling.get("match", "") + "+sibling_fallback").strip("+")
                return sibling
    return prod


def _find_liquid_under_prefix(con: sqlite3.Connection, parent_prefix: str,
                                canonical_buy_form: str, user_facets: list[str],
                                excluded_upcs: set[str],
                                product_claims: dict[str, set[str]],
                                trust_override: bool, grams_needed: float,
                                exclude_path: str = "") -> dict | None:
    """Search all SKUs under a parent-path prefix that are bulk-form
    (grams >= SACHET_GRAMS) and don't have mix/packet/sachet in the name.
    Used as fallback when the leaf path returns only sachets but the recipe
    needs >100g."""
    cur = con.cursor()
    user_facet_set = {f.lower().strip() for f in user_facets}
    path_leaf = parent_prefix.split(" > ")[-1]
    cur.execute("""
        SELECT upc, name, brand, grams, cents, cpg, consensus_canonical, consensus_fndds, consensus_sr28
        FROM priced_products
        WHERE consensus_canonical LIKE ?
          AND consensus_canonical != ?
          AND available = 1 AND grams >= ? AND cents > 0
    """, (parent_prefix + " > %", exclude_path, SACHET_GRAMS))
    candidates = []
    for row in cur.fetchall():
        upc, name = row[0], row[1] or ""
        if upc in excluded_upcs: continue
        if _is_likely_dry_mix(name, row[3] or 0): continue
        # Form filter — same name_passes_filter used by leaf strategies
        if not name_passes_filter(name, canonical_buy_form, path_leaf,
                                   canonical_path=row[6] or ""): continue
        if user_facet_set:
            prod_claims = product_claims.get(upc)
            if prod_claims is not None:
                if not user_facet_set.issubset(prod_claims): continue
            else:
                if not all(f.replace("_"," ") in name.lower() for f in user_facet_set):
                    continue
        spend = _total_spend(grams_needed, row[3] or 0, row[4] or 0)
        candidates.append((spend, row[5] or 0, row[3] or 0, row))
    if not candidates:
        return None
    candidates.sort()
    row = candidates[0][3]
    return {"upc": row[0], "name": row[1], "brand": row[2], "grams": row[3],
            "cents": row[4], "cpg": row[5], "fndds": row[7] or "",
            "sr28": row[8] or "", "match": "sibling"}


def _find_at_path(con: sqlite3.Connection, canonical_path: str,
                   canonical_buy_form: str, user_facets: list[str],
                   excluded_upcs: set[str],
                   product_claims: dict[str, set[str]],
                   trust_override: bool,
                   grams_needed: float) -> dict | None:
    if not canonical_path:
        return None
    cur = con.cursor()
    user_facet_set = {f.lower().strip() for f in user_facets}

    # When override is in effect, the filter ALSO accepts the path leaf word
    # (so prawns → Shrimp path picks up shrimp-named SKUs).
    path_leaf = canonical_path.split(" > ")[-1] if trust_override and canonical_path else ""

    # Form-aware HTC: prefer SKUs with matching htc_form_code so "ground
    # cinnamon" doesn't pick "Bacon DIY Kit" and "whole ham" doesn't pick deli.
    form_htc = _encode_buy_form_form_aware(canonical_buy_form, canonical_path)

    def _rank_and_pick(rows: list, match_label: str) -> dict | None:
        """Filter rows through name/facet checks, then pick the SKU that
        minimizes ACTUAL TOTAL SPEND for grams_needed (ceil(need/size) × cents).
        For small needs this prefers the smallest sufficient bottle over
        bulk; for large needs it prefers cheapest-per-gram (same as cpg ASC)."""
        survivors = []
        for row in rows:
            upc, name = row[0], row[1] or ""
            if upc in excluded_upcs: continue
            if not name_passes_filter(name, canonical_buy_form, path_leaf,
                                   canonical_path=row[6] or canonical_path): continue
            if user_facet_set:
                prod_claims = product_claims.get(upc)
                if prod_claims is not None:
                    if not user_facet_set.issubset(prod_claims): continue
                else:
                    if not all(f.replace("_", " ") in name.lower() for f in user_facet_set):
                        continue
            survivors.append(row)
        if not survivors:
            return None
        survivors.sort(key=lambda row: (
            _total_spend(grams_needed, row[3] or 0, row[4] or 0),
            row[5] or 0,  # cpg tiebreak — among equal-spend, prefer cheapest/g
            row[3] or 0,  # then prefer smallest pkg (less waste)
        ))
        row = survivors[0]
        return {"upc": row[0], "name": row[1], "brand": row[2], "grams": row[3],
                "cents": row[4], "cpg": row[5], "fndds": row[7] or "", "sr28": row[8] or "",
                "match": match_label}

    # Strategy A: form-aware HTC exact match (highest priority)
    if form_htc:
        cur.execute("""
            SELECT upc, name, brand, grams, cents, cpg, consensus_canonical, consensus_fndds, consensus_sr28
            FROM priced_products
            WHERE htc_form_code = ? AND consensus_canonical = ?
              AND available = 1 AND grams > 0 AND cents > 0
        """, (form_htc, canonical_path))
        prod = _rank_and_pick(cur.fetchall(), "form_htc")
        if prod: return prod

    # Strategy B: exact path + claims-match (if user has facets)
    if user_facet_set:
        cur.execute("""
            SELECT upc, name, brand, grams, cents, cpg, consensus_canonical, consensus_fndds, consensus_sr28
            FROM priced_products
            WHERE consensus_canonical = ?
              AND available = 1 AND grams > 0 AND cents > 0
        """, (canonical_path,))
        prod = _rank_and_pick(cur.fetchall(), "path+facets")
        if prod: return prod

    # Strategy C: exact path, ranked by recipe-leaf token containment first,
    # then by total-spend (so "Dijon mustard" picks Dijon-named SKU even if a
    # different mustard is cheaper, but among Dijons picks cheapest-total).
    filt_toks = _recipe_filter_tokens(canonical_path, canonical_buy_form)
    cur.execute("""
        SELECT upc, name, brand, grams, cents, cpg, consensus_canonical, consensus_fndds, consensus_sr28
        FROM priced_products
        WHERE consensus_canonical = ?
          AND available = 1 AND grams > 0 AND cents > 0
    """, (canonical_path,))
    candidates = []
    for row in cur.fetchall():
        upc, name = row[0], row[1] or ""
        if upc in excluded_upcs: continue
        if not name_passes_filter(name, canonical_buy_form, path_leaf,
                                   canonical_path=row[6] or canonical_path): continue
        nl = name.lower()
        n_match = sum(1 for t in filt_toks if t in nl)
        spend = _total_spend(grams_needed, row[3] or 0, row[4] or 0)
        candidates.append((-n_match, spend, row[5] or 0, row[3] or 0, row))
    if candidates:
        candidates.sort()
        row = candidates[0][4]
        return {"upc": row[0], "name": row[1], "brand": row[2], "grams": row[3],
                "cents": row[4], "cpg": row[5], "fndds": row[7] or "", "sr28": row[8] or "",
                "match": "path_ranked"}

    return None


def calc_decision(buyability: str, usage: str, identity_resolved: bool = True) -> str:
    if buyability == "derivative":
        return "calculate_via_base"
    if buyability in ("unbuyable", "nonsense"):
        return "review"
    # NEW: classifier flagged unresolved identity (e.g. "additional seasoning",
    # "assorted X", "your favorite herb") — surface to user, don't try to look up
    if identity_resolved is False and buyability == "buyable":
        return "user_choice_unresolved"
    if usage in ("to_taste", "garnish", "optional"):
        return "shop_only"
    return "calculate"


# ---------------------------------------------------------------------------
# Planner core
# ---------------------------------------------------------------------------
def calculate(recipe_id: str, unified: dict, classifications: dict,
               buy_form_lookup: dict, con: sqlite3.Connection,
               user_facets: list[str],
               excluded_upcs: set[str],
               fndds_macros: dict[str, dict],
               product_claims: dict[str, set[str]],
               overridden: set[str],
               sr28_macros: dict[str, dict] | None = None) -> RecipeResult:
    sr28_macros = sr28_macros or {}
    lines = unified.get(recipe_id, [])
    cls = classifications.get(recipe_id, [])
    if not lines:
        return RecipeResult(recipe_id=recipe_id, recipe_title="(not found)", user_facets=user_facets)
    title = lines[0].get("recipe_title", "?")
    result = RecipeResult(recipe_id=recipe_id, recipe_title=title, user_facets=user_facets)

    skus_seen: dict[str, int] = {}

    # match unified rows to classifications by ORDER (recipes_unified has no line_index)
    for i, urow in enumerate(lines):
        c = cls[i] if i < len(cls) else {}
        canon = (c.get("canonical_buy_form") or "").strip()
        bu = c.get("buyability") or ""
        us = c.get("usage") or ""
        claims = c.get("extracted_claims") or []
        base = c.get("base_ingredients") or []
        try:
            grams = float(urow.get("grams_resolved") or 0)
        except (TypeError, ValueError):
            grams = 0.0
        try:
            qty = float(urow.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0.0

        canonical_path = buy_form_lookup.get(canon.lower(), "")
        # Fallback: if buy_form has noise (leading qty/size/prep), strip it and retry.
        # E.g. "1 onion" → "onion", "1 bunch broccoli cut into bite size pieces" →
        # "broccoli", "1 sweet red pepper" → "sweet red pepper".
        if not canonical_path:
            cl = canon.lower().strip()
            stripped = _strip_buy_form_noise(cl)
            if stripped and stripped != cl:
                canonical_path = buy_form_lookup.get(stripped, "")
        # Special path value `DERIVATIVE` flips this line to derivative
        # (used by overrides for lemon zest, ice cubes, etc.)
        if canonical_path == "DERIVATIVE":
            bu = "derivative"
            canonical_path = ""
        else:
            canonical_path = _contextual_path_override(
                canon, urow.get("display", "") or "", canonical_path)
        identity_resolved = c.get("identity_resolved", True)
        decision = calc_decision(bu, us, identity_resolved)
        line = LineResult(
            line_index=i,
            raw_display=urow.get("display", "") or "",
            raw_item=urow.get("ingredient_item", "") or "",
            qty=qty,
            unit=urow.get("unit", "") or "",
            grams=grams,
            canonical_buy_form=canon,
            canonical_path=canonical_path,
            buyability=bu, usage=us,
            extracted_claims=claims,
            base_ingredients=base,
            decision=decision,
        )

        if decision == "calculate_via_base":
            # Derivative — use first base_ingredient's path/SKU for cost+macros.
            # The classifier told us this is e.g. "egg wash" made from [eggs, water].
            # We use eggs as the calculable form. Water is treated as zero.
            primary_base = (base[0] if base else "").lower().strip()
            if not primary_base or primary_base == "water":
                line.note = f"derivative (water/recipe — zero contribution)"
            else:
                base_path = buy_form_lookup.get(primary_base, "")
                if not base_path:
                    line.note = f"derivative; base '{primary_base}' has no path"
                    result.coverage["no_sku_via_base"] += 1
                else:
                    trust_base = primary_base in overridden
                    prod = find_cheapest(con, base_path, primary_base,
                                          user_facets, excluded_upcs,
                                          product_claims, trust_base,
                                          grams_needed=grams)
                    if prod and grams > 0:
                        line.sku_name = prod["name"]
                        line.sku_brand = prod["brand"] or ""
                        line.sku_upc = prod.get("upc", "")
                        line.sku_grams = prod["grams"] or 0
                        line.sku_cents = prod["cents"] or 0
                        line.sku_cpg = prod["cpg"] or 0
                        line.line_cost_cents = grams * (prod["cpg"] or 0)
                        line.canonical_buy_form = primary_base + " (via derivative)"
                        line.canonical_path = base_path
                        line.note = f"derivative resolved via base='{primary_base}'"
                        # Macros from FNDDS bridge
                        macros, _ = _macros_for(prod, fndds_macros, sr28_macros)
                        if macros:
                            scale = grams / 100.0
                            line.line_kcal      = macros["kcal"]      * scale
                            line.line_protein_g = macros["protein_g"] * scale
                            line.line_fat_g     = macros["fat_g"]     * scale
                            line.line_carb_g    = macros["carb_g"]    * scale
                            line.line_fiber_g   = macros["fiber_g"]   * scale
                            line.line_sodium_mg = macros["sodium_mg"] * scale
                        if prod["name"] not in skus_seen:
                            skus_seen[prod["name"]] = prod["cents"]
                            result.shopping_list.append((
                                primary_base + " (for " + canon + ")",
                                prod["name"], prod["cents"]))
                    else:
                        line.note = f"derivative; no SKU for base '{primary_base}'"
                        result.coverage["no_sku_via_base"] += 1
        elif decision == "review":
            line.note = f"flagged: {bu}"
            result.broken_flags.append(f"line {i}: {bu} - {urow.get('display','')[:60]}")
        elif decision == "user_choice_unresolved":
            line.note = f"unresolved identity: '{canon}' — user must specify"
            result.decision_points.append(
                f"unresolved [{i}]: '{canon}' (classifier flagged — needs user choice)"
            )
            result.coverage["user_choice_unresolved"] += 1
        elif decision in ("calculate", "shop_only"):
            trust = canon.lower() in overridden
            prod = find_cheapest(con, canonical_path, canon, user_facets,
                                   excluded_upcs, product_claims, trust,
                                   grams_needed=grams)
            if prod:
                line.sku_name = prod["name"]
                line.sku_brand = prod["brand"] or ""
                line.sku_upc = prod.get("upc", "")
                line.sku_grams = prod["grams"] or 0
                line.sku_cents = prod["cents"] or 0
                line.sku_cpg = prod["cpg"] or 0
                if decision == "calculate" and grams > 0:
                    line.line_cost_cents = grams * (prod["cpg"] or 0)
                    # Macro contribution: FNDDS first, SR28 fallback
                    macros, _ = _macros_for(prod, fndds_macros, sr28_macros)
                    if macros:
                        scale = grams / 100.0
                        line.line_kcal      = macros["kcal"]      * scale
                        line.line_protein_g = macros["protein_g"] * scale
                        line.line_fat_g     = macros["fat_g"]     * scale
                        line.line_carb_g    = macros["carb_g"]    * scale
                        line.line_fiber_g   = macros["fiber_g"]   * scale
                        line.line_sodium_mg = macros["sodium_mg"] * scale
                # add to shopping list (dedupe by sku name)
                if prod["name"] not in skus_seen:
                    skus_seen[prod["name"]] = prod["cents"]
                    result.shopping_list.append((canon, prod["name"], prod["cents"]))
            else:
                line.note = "no SKU found at canonical_path" if canonical_path else "no canonical_path lookup"
                result.coverage["no_sku"] += 1

        # Collect decision points
        if bu == "alternation":
            result.decision_points.append(
                f"alternation [{i}]: chose '{canon}' over {base or '[]'}"
            )
        if bu == "specialty":
            result.decision_points.append(f"specialty [{i}]: {canon}")
        if us == "optional":
            result.decision_points.append(f"optional [{i}]: {canon}")

        result.lines.append(line)
        result.coverage[decision] += 1
        if line.line_cost_cents:
            result.line_total_cents += line.line_cost_cents
        result.total_kcal      += line.line_kcal
        result.total_protein_g += line.line_protein_g
        result.total_fat_g     += line.line_fat_g
        result.total_carb_g    += line.line_carb_g
        result.total_fiber_g   += line.line_fiber_g
        result.total_sodium_mg += line.line_sodium_mg

    result.cart_total_cents = sum(skus_seen.values())
    return result


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
def render(r: RecipeResult) -> None:
    print(f"\n{'='*88}")
    print(f"RECIPE [{r.recipe_id}] {r.recipe_title}")
    if r.user_facets:
        print(f"USER FACETS: {', '.join(r.user_facets)}")
    print('='*88)
    print(f"{'#':<3} {'INGREDIENT':<48} {'BUY':<26} {'DEC':<11} {'COST'}")
    print('-'*120)
    for ln in r.lines:
        canon = ln.canonical_buy_form or "—"
        if ln.extracted_claims:
            canon += " +[" + ",".join(ln.extracted_claims) + "]"
        cost = (
            f"${ln.line_cost_cents/100:.2f}" if ln.line_cost_cents > 0
            else (ln.note or "")
        )
        print(f"  {ln.line_index:<3} {ln.raw_display[:46]:<48} {canon[:24]:<26} {ln.decision:<11} {cost}")
    print('-'*120)
    print(f"\nLINE-ATTRIBUTABLE COST:  ${r.line_total_cents/100:.2f}")
    print(f"FULL CART TOTAL:         ${r.cart_total_cents/100:.2f}")
    print(f"\nMACROS (recipe total):")
    print(f"  kcal:    {r.total_kcal:>8.0f}")
    print(f"  protein: {r.total_protein_g:>8.1f} g")
    print(f"  fat:     {r.total_fat_g:>8.1f} g")
    print(f"  carb:    {r.total_carb_g:>8.1f} g")
    print(f"  fiber:   {r.total_fiber_g:>8.1f} g")
    print(f"  sodium:  {r.total_sodium_mg:>8.0f} mg")
    print(f"\nSHOPPING LIST ({len(r.shopping_list)} SKUs):")
    for canon, name, cents in r.shopping_list:
        print(f"  • {name[:75]:<75}  ${(cents or 0)/100:.2f}    (for: {canon})")
    if r.decision_points:
        print(f"\nDECISION POINTS ({len(r.decision_points)}):")
        for d in r.decision_points:
            print(f"  ⚠ {d}")
    if r.broken_flags:
        print(f"\nBROKEN FLAGS ({len(r.broken_flags)}):")
        for b in r.broken_flags:
            print(f"  ✗ {b}")
    print(f"\nCOVERAGE: {dict(r.coverage)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe-id", help="single recipe_id")
    ap.add_argument("--recipe-ids", help="comma-separated recipe_ids")
    ap.add_argument("--random", type=int, default=0, help="N random recipes")
    ap.add_argument("--facets", default="", help="comma-separated user facets (organic,low_fat,vegan,...)")
    args = ap.parse_args()
    user_facets = [f.strip() for f in args.facets.split(",") if f.strip()]

    print("loading recipes_unified...", file=sys.stderr)
    unified = load_unified()
    print("loading classifications...", file=sys.stderr)
    cls = load_classifications()
    print("loading buy_form lookup...", file=sys.stderr)
    bfl, overridden = load_buy_form_lookup()
    print("loading excluded upcs...", file=sys.stderr)
    excluded_upcs = load_excluded_upcs()
    print("loading FNDDS macros...", file=sys.stderr)
    fndds_macros = load_fndds_macros()
    sr28_macros  = load_sr28_macros()
    print(f"  loaded {len(fndds_macros):,} FNDDS macros, {len(sr28_macros):,} SR28 macros (fallback)", file=sys.stderr)
    print("loading product claims...", file=sys.stderr)
    product_claims = load_product_claims()
    print(f"  {len(unified):,} recipes, {len(cls):,} classified, "
          f"{len(bfl):,} buy_form mappings, {len(excluded_upcs):,} excluded upcs, "
          f"{len(fndds_macros):,} fndds macros",
          file=sys.stderr)

    target_ids: list[str] = []
    if args.recipe_id:
        target_ids = [args.recipe_id]
    elif args.recipe_ids:
        target_ids = [x.strip() for x in args.recipe_ids.split(",")]
    elif args.random:
        rng = random.Random(42)
        candidates = [k for k in cls.keys() if k in unified]
        target_ids = rng.sample(candidates, min(args.random, len(candidates)))
    else:
        target_ids = ["233694", "300767", "25640", "382"]   # demo defaults

    con = sqlite3.connect(str(PRICED_DB))
    for rid in target_ids:
        result = calculate(rid, unified, cls, bfl, con, user_facets,
                            excluded_upcs, fndds_macros, product_claims,
                            overridden, sr28_macros=sr28_macros)
        render(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
