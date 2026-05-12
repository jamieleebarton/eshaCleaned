from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
ESHA_CSV = ROOT / "esha_cleaned.csv"
PRODUCTS_DB = ROOT / "data" / "master_products.db"


TOKEN_SYNONYMS = {
    "yoghurt": "yogurt",
    "chile": "chili",
    "chilies": "chili",
    "chiles": "chili",
    "garbanzos": "chickpea",
    "garbanzo": "chickpea",
    "powdered": "powder",
    "pwd": "powder",
    "nonfat": "skim",
    "skimmed": "skim",
    "catsup": "ketchup",
    "courgette": "zucchini",
    "aubergine": "eggplant",
    "filberts": "hazelnut",
    "filbert": "hazelnut",
    "mayo": "mayonnaise",
    "scallions": "scallion",
    "tumeric": "turmeric",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "by",
    "for",
    "from",
    "in",
    "intl",
    "international",
    "nfs",
    "no",
    "ns",
    "of",
    "or",
    "plain",
    "prepared",
    "recipe",
    "regular",
    "style",
    "the",
    "to",
    "type",
    "with",
    "without",
    "fs",
    "usda",
}

FORM_OPTIONAL = {
    "chunk",
    "chunks",
    "chopped",
    "coarse",
    "crushed",
    "diced",
    "fine",
    "flake",
    "flakes",
    "grated",
    "ground",
    "minced",
    "sliced",
    "shredded",
    "strip",
    "strips",
}

FORTIFICATION_WORDS = {
    "a",
    "acid",
    "added",
    "b",
    "calcium",
    "d",
    "enriched",
    "fortified",
    "folate",
    "folic",
    "iron",
    "niacin",
    "nutrient",
    "nutrients",
    "riboflavin",
    "thiamin",
    "vitamin",
    "vitamins",
}

FRUITS = {
    "apple",
    "apricot",
    "avocado",
    "banana",
    "berry",
    "blackberry",
    "blueberry",
    "cantaloupe",
    "cherry",
    "clementine",
    "coconut",
    "cranberry",
    "currant",
    "date",
    "fig",
    "fruit",
    "grape",
    "grapefruit",
    "guava",
    "kiwi",
    "kumquat",
    "lemon",
    "lime",
    "mango",
    "melon",
    "nectarine",
    "orange",
    "papaya",
    "peach",
    "pear",
    "persimmon",
    "pineapple",
    "plantain",
    "plum",
    "pomegranate",
    "prune",
    "raisin",
    "raspberry",
    "strawberry",
    "tangerine",
    "watermelon",
}

VEGETABLES = {
    "artichoke",
    "arugula",
    "asparagus",
    "bean",
    "beet",
    "broccoli",
    "cabbage",
    "carrot",
    "cauliflower",
    "celery",
    "chard",
    "collard",
    "corn",
    "cucumber",
    "edamame",
    "eggplant",
    "endive",
    "escarole",
    "fennel",
    "garlic",
    "ginger",
    "greens",
    "jicama",
    "kale",
    "kohlrabi",
    "leek",
    "lettuce",
    "mushroom",
    "okra",
    "olive",
    "onion",
    "parsley",
    "parsnip",
    "pea",
    "pepper",
    "pickle",
    "potato",
    "pumpkin",
    "radish",
    "rutabaga",
    "shallot",
    "spinach",
    "sprout",
    "squash",
    "sweetpotato",
    "tomatillo",
    "tomato",
    "turnip",
    "vegetable",
    "watercress",
    "yam",
    "zucchini",
}

MEATS = {
    "bacon",
    "beef",
    "bison",
    "bologna",
    "chorizo",
    "goat",
    "ham",
    "lamb",
    "meat",
    "pastrami",
    "pepperoni",
    "pork",
    "prosciutto",
    "rabbit",
    "salami",
    "sausage",
    "veal",
    "venison",
}

POULTRY = {"chicken", "duck", "goose", "hen", "pheasant", "poultry", "quail", "turkey"}

SEAFOOD = {
    "anchovy",
    "bass",
    "catfish",
    "clam",
    "cod",
    "crab",
    "crawfish",
    "fish",
    "flounder",
    "haddock",
    "halibut",
    "herring",
    "lobster",
    "mackerel",
    "mahi",
    "mussel",
    "octopus",
    "oyster",
    "perch",
    "pollock",
    "salmon",
    "sardine",
    "scallop",
    "seafood",
    "shellfish",
    "shrimp",
    "snapper",
    "sole",
    "squid",
    "swai",
    "tilapia",
    "trout",
    "tuna",
}

LEGUMES = {
    "bean",
    "chickpea",
    "edamame",
    "garbanzo",
    "hummus",
    "legume",
    "lentil",
    "pea",
    "peanut",
    "pulse",
    "soybean",
    "split",
    "tempeh",
    "tofu",
}

NUTS_SEEDS = {
    "almond",
    "cashew",
    "chia",
    "chestnut",
    "coconut",
    "flax",
    "hazelnut",
    "hemp",
    "macadamia",
    "nut",
    "pecan",
    "peanut",
    "pine",
    "pistachio",
    "poppy",
    "pumpkin",
    "seed",
    "sesame",
    "sunflower",
    "walnut",
}

GRAINS = {
    "bagel",
    "barley",
    "bran",
    "bread",
    "buckwheat",
    "bun",
    "cereal",
    "cornmeal",
    "couscous",
    "cracker",
    "crouton",
    "flour",
    "granola",
    "grain",
    "macaroni",
    "millet",
    "noodle",
    "oat",
    "oatmeal",
    "pasta",
    "pita",
    "quinoa",
    "rice",
    "roll",
    "rye",
    "sorghum",
    "spaghetti",
    "tortilla",
    "wheat",
}

SPICES_HERBS = {
    "basil",
    "bay",
    "cardamom",
    "chervil",
    "cilantro",
    "cinnamon",
    "clove",
    "coriander",
    "cumin",
    "dill",
    "extract",
    "herb",
    "marjoram",
    "mint",
    "nutmeg",
    "oregano",
    "paprika",
    "parsley",
    "pepper",
    "peppercorn",
    "rosemary",
    "saffron",
    "sage",
    "salt",
    "seasoning",
    "spice",
    "tarragon",
    "thyme",
    "turmeric",
    "vanilla",
}

CONDIMENTS = {
    "barbecue",
    "bbq",
    "chutney",
    "condiment",
    "dressing",
    "dip",
    "gravy",
    "horseradish",
    "ketchup",
    "marinade",
    "mayonnaise",
    "mustard",
    "olive",
    "pesto",
    "pickle",
    "relish",
    "salsa",
    "sauce",
    "soy",
    "spread",
    "tamari",
    "teriyaki",
    "vinegar",
    "worcestershire",
}

DESSERT_SNACK = {
    "bar",
    "biscuit",
    "brownie",
    "cake",
    "candy",
    "chip",
    "chocolate",
    "cookie",
    "cracker",
    "custard",
    "dessert",
    "donut",
    "gelatin",
    "ice",
    "muffin",
    "pastry",
    "pie",
    "pudding",
    "snack",
    "sorbet",
    "sherbet",
}

DESSERT_HEADS = DESSERT_SNACK - {"ice"}

PLANT_MILK_SOURCES = {"almond", "cashew", "coconut", "hemp", "oat", "rice", "soy", "soymilk"}

SOLID_DESSERT_TOKENS = {
    "bar", "biscuit", "brownie", "cake", "candy", "cookie",
    "cracker", "donut", "muffin", "pastry", "pie", "wafer", "truffle",
}

# Pass K.4 — packaging/portion tokens that count as dessert ONLY when a sweet
# anchor co-occurs (or the brand is a known confection brand). Without the
# co-occurrence gate these would false-positive on "ring of onion", "bite-size
# carrots", etc.
CONTEXTUAL_DESSERT_TOKENS = {
    "pretzel", "pretzels", "cup", "cups",
    "strip", "strips", "nachos", "kit",
    "ring", "rings", "twist", "twists",
    "bite", "bites", "pop", "pops",
}
SWEET_ANCHORS = {
    "chocolate", "candy", "caramel", "sugar", "frosted", "glazed", "sweet",
    "marshmallow", "fudge", "peanut", "butter", "gummi", "gummy", "sour",
    "honey", "syrup", "lollipop", "toffee", "praline",
}
SWEET_BRANDS = {
    "REESE'S", "REESES", "HERSHEY'S", "HERSHEYS", "M&M", "M&M'S", "MM",
    "SNICKERS", "TWIX", "KIT KAT", "KITKAT", "NESTLE", "CADBURY", "MARS",
    "SKITTLES", "STARBURST", "GHIRARDELLI", "LINDT", "WERTHER'S", "WERTHERS",
    "TRIDENT", "BUBBALOO", "HALLS", "KING HENRY'S", "KING HENRYS",
    "JOLLY RANCHER", "RAYGE", "PEZ", "DOVE", "GODIVA", "ANDES",
    "TWIZZLERS", "LIFE SAVERS", "NESTLE TOLL HOUSE",
}


def is_dessert_context(tokens, brand: str | None = None) -> bool:
    """Return True if the token set should be treated as dessert/confection.

    A solid dessert token (bar/cake/cookie/candy/etc.) is enough on its own.
    A contextual token (cup/strip/ring/pretzel/etc.) only counts as dessert
    when accompanied by a sweet anchor or a confection brand — so "ring of
    onion" stays vegetable while "Sour Apple Rings" becomes dessert.
    """
    tok_set = set(tokens) if not isinstance(tokens, set) else tokens
    if tok_set & SOLID_DESSERT_TOKENS:
        return True
    if tok_set & CONTEXTUAL_DESSERT_TOKENS:
        if tok_set & SWEET_ANCHORS:
            return True
        if brand and brand.strip().upper() in SWEET_BRANDS:
            return True
    return False


# Pass K.1 — subtype tokens within each broad family. The family detector
# already routes products into the right family; subtype distinguishes within.
# Used in score_candidate (matcher) and best_code (heal passes) to PREVENT
# matching, e.g., HONEY ROASTED ALMONDS → "Almond Butter, crunchy with flaxseed"
# (roasted product vs butter ESHA — INCOMPATIBLE_SUBTYPES forbids this pair).
SUBTYPE_TOKENS = {
    "nut_seed":  {"raw", "roasted", "toasted", "butter", "oil", "flour", "meal", "milk",
                  "paste", "spread", "brittle", "candied", "glazed", "powder"},
    "fruit":     {"fresh", "raw", "dried", "canned", "frozen", "sauce", "juice", "jam",
                  "jelly", "preserve", "syrup", "glazed", "candied", "chip", "crisp"},
    "vegetable": {"raw", "fresh", "cooked", "steamed", "boiled", "canned", "frozen",
                  "dried", "pickled", "fermented", "sauce", "juice", "powder"},
    "milk":      {"whole", "skim", "2", "1", "reduced", "chocolate", "strawberry",
                  "vanilla", "powdered", "condensed", "evaporated", "lactose"},
    "cheese":    {"shredded", "sliced", "block", "crumbled", "cubed", "grated", "spread"},
    "meat":      {"raw", "cooked", "cured", "smoked", "jerky", "ground", "sliced", "deli"},
    "grain":     {"flour", "bread", "cereal", "pasta", "tortilla", "cracker", "cookie",
                  "cake", "mix", "pancake"},
}

INCOMPATIBLE_SUBTYPES = {
    "nut_seed":  [({"roasted", "raw", "whole", "salted", "unsalted"},
                   {"butter", "oil", "flour", "meal", "milk", "paste"}),
                  ({"butter"}, {"oil", "flour", "meal"})],
    "fruit":     [({"fresh", "raw"},
                   {"sauce", "juice", "jam", "jelly", "dried", "canned", "syrup", "crisp"}),
                  ({"dried", "crisp"}, {"fresh", "sauce", "juice"}),
                  ({"juice"}, {"fresh", "dried", "jam"})],
    "vegetable": [({"fresh", "raw"}, {"sauce", "juice", "powder", "dried", "canned"})],
    "milk":      [({"whole", "skim", "2", "1", "reduced"}, {"powdered", "condensed"})],
}


def extract_subtype(tokens, family: str) -> set[str]:
    members = SUBTYPE_TOKENS.get(family, set())
    if not members:
        return set()
    tok_iter = tokens if isinstance(tokens, (list, tuple, set, frozenset)) else list(tokens)
    return {t for t in tok_iter if t in members}


def subtype_compatible(p_tokens, e_tokens, family: str) -> bool:
    """True if product and ESHA tokens are subtype-compatible for the family.

    Returns True when either side has no subtype tokens (cannot disprove).
    Returns False only when an explicit INCOMPATIBLE_SUBTYPES pair fires
    in either direction (product↔ESHA).
    """
    rules = INCOMPATIBLE_SUBTYPES.get(family)
    if not rules:
        return True
    p_st = extract_subtype(p_tokens, family)
    e_st = extract_subtype(e_tokens, family)
    if not p_st or not e_st:
        return True
    for left, right in rules:
        if (p_st & left) and (e_st & right):
            return False
        if (p_st & right) and (e_st & left):
            return False
    return True


# Pass K.2 — generic filler tokens that should NOT count toward over-specific
# attractor penalty. These are descriptive but non-discriminative.
GENERIC_FILLER_TOKENS = {
    "with", "added", "fresh", "plain", "regular", "style", "type", "prepared",
    "and", "or", "of", "the", "in", "to", "for", "from", "by",
    "no", "low", "reduced", "free", "natural",
}

# Compound tokens emitted as a single word by tokens_for need to be split
# back into their parts for detect_family / FRUITS / VEGETABLES matching.
# Without this, "Applesauce, unsweetened, canned" tokenizes to {applesauce}
# and never matches FRUITS (which contains "apple"), so 3006 falls into
# prepared_food instead of fruit and never appears in fruit-family heal pools.
COMPOUND_TOKEN_EXPANSIONS = {
    "applesauce": {"apple", "sauce"},
    "almondmilk": {"almond", "milk"},
    "cashewmilk": {"cashew", "milk"},
    "coconutmilk": {"coconut", "milk"},
    "goatcheese": {"goat", "cheese"},
    "hempmilk": {"hemp", "milk"},
    "oatmilk": {"oat", "milk"},
    "ricemilk": {"rice", "milk"},
    "soymilk": {"soy", "milk"},
    "buttermilk": {"butter", "milk"},
    "cornbread": {"corn", "bread"},
    "shortbread": {"short", "bread"},
    "gingerbread": {"ginger", "bread"},
    "sourdough": {"sour", "dough"},
    "cheesecake": {"cheese", "cake"},
    "cupcake": {"cup", "cake"},
    "pancake": {"pan", "cake"},
    "shortcake": {"short", "cake"},
    "icecream": {"ice", "cream"},
}


@dataclass(frozen=True)
class EshaProfile:
    code: str
    description: str
    norm: str
    tokens: tuple[str, ...]
    family: str
    hard_terms: tuple[str, ...]
    attrs: tuple[str, ...]
    fts_terms: tuple[str, ...]
    skip_reason: str = ""


@dataclass(frozen=True)
class ProductRow:
    gtin_upc: str
    fdc_id: str
    description: str
    brand_owner: str
    brand_name: str
    category: str
    serving_size: str
    serving_size_unit: str
    calories: str
    protein_g: str
    fat_g: str
    carbs_g: str
    sugar_g: str
    sodium_mg: str
    ingredients: str = ""


def normalize_text(text: str) -> str:
    text = (text or "").lower().replace("&", " and ")
    text = text.replace("non-fat", "nonfat").replace("non fat", "nonfat")
    text = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"\1 percent", text)
    text = re.sub(r"[^a-z0-9.]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def singular(token: str) -> str:
    token = TOKEN_SYNONYMS.get(token, token)
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("oes"):
        return token[:-2]
    if len(token) > 4 and token.endswith("ves"):
        return token[:-3] + "f"
    if len(token) > 3 and token.endswith("s") and token not in {"couscous", "hummus", "molasses", "swiss", "watercress"}:
        return token[:-1]
    return token


def tokens_for(text: str) -> list[str]:
    out: list[str] = []
    for token in normalize_text(text).split():
        if token == "percent":
            out.append(token)
            continue
        if token.replace(".", "", 1).isdigit():
            out.append(token)
            continue
        normalized = TOKEN_SYNONYMS.get(singular(token), singular(token))
        out.append(normalized)
        # If this token is a known compound (e.g. "applesauce"), also emit its
        # parts so downstream FRUITS / VEGETABLES / detect_family checks see them.
        for part in COMPOUND_TOKEN_EXPANSIONS.get(normalized, ()):
            if part not in out:
                out.append(part)
    return out


def contains_token(tokens: Iterable[str], *needles: str) -> bool:
    token_set = set(tokens)
    return any(needle in token_set for needle in needles)


def has_phrase(norm: str, phrase: str) -> bool:
    return bool(re.search(r"\b" + re.escape(phrase) + r"\b", norm))


def product_has_term(product_norm: str, product_tokens: set[str], term: str) -> bool:
    variants = {term}
    if term == "chickpea":
        variants |= {"garbanzo"}
    elif term == "eggplant":
        variants |= {"aubergine"}
    elif term == "hazelnut":
        variants |= {"filbert"}
    elif term == "ketchup":
        variants |= {"catsup"}
    elif term == "powder":
        variants |= {"dry", "powdered"}
    elif term == "scallion":
        variants |= {"green onion"}
    elif term == "skim":
        variants |= {"0 percent", "fat free", "nonfat"}
    elif term == "turmeric":
        variants |= {"tumeric"}
    elif term == "yogurt":
        variants |= {"yoghurt"}
    elif term == "zucchini":
        variants |= {"courgette"}
    for variant in variants:
        if " " in variant:
            if has_phrase(product_norm, variant):
                return True
        elif variant in product_tokens:
            return True
    return False


def detect_family(tokens: list[str], norm: str) -> str:
    token_set = set(tokens)
    first = tokens[0] if tokens else ""
    if "sample" in token_set or norm.startswith("jane sample"):
        return "nonfood"
    if "human" in token_set and "milk" in token_set:
        return "nonfood"
    if "formula" in token_set and ("infant" in token_set or "baby" in token_set):
        return "infant_formula"
    if first in {"dish", "dinner", "entree", "meal"} or "casserole" in token_set:
        return "prepared_food"
    if (
        first in {"beverage", "coffee", "drink", "juice", "soda", "tea", "water"}
        or "cocoa" in token_set
        or "shake" in token_set
    ) and not (first == "milk" and "shake" not in token_set):
        return "beverage"
    # "soda" anywhere in description (Pass E refinement). Catches
    # "MOUNTAIN DEW BAJA BLAST TROPICAL LIME FLAVOR SODA" where the brand is the
    # first token. Excludes "baking soda" which is a leavener.
    if "soda" in token_set and "baking" not in token_set:
        return "beverage"
    if first in {"syrup", "sugar", "honey", "molasses"}:
        return "sweetener"
    # Plant milk requires NO solid-dessert token; otherwise this misclassifies
    # "MILK CHOCOLATE WITH ALMONDS BAR" as plant_milk just because "almond"+"milk"
    # are present.
    if "milk" in token_set and token_set & PLANT_MILK_SOURCES and not (token_set & SOLID_DESSERT_TOKENS):
        return "plant_milk"
    if "yogurt" in token_set:
        return "yogurt"
    if "cheese" in token_set or "mozzarella" in token_set or "ricotta" in token_set:
        return "cheese"
    if "butter" in token_set and token_set & (NUTS_SEEDS | LEGUMES | {"soynut", "soy"}):
        return "nut_butter"
    if first in {"butter", "ghee"}:
        return "butter"
    if "ice" in token_set and "cream" in token_set:
        return "dessert_snack"
    if "cream" in token_set or "creamer" in token_set:
        return "cream"
    # Composite milk-based dessert (e.g. "MILK CHOCOLATE BAR", "MILK CHOCOLATE COOKIE",
    # "MILK CHOCOLATE PRETZELS", "REESE'S MILK CHOCOLATE CUPS").
    # The presence of a solid-dessert OR sweet-anchored contextual token alongside
    # "milk" means the product is a confection, not a dairy beverage.
    if "milk" in token_set:
        if token_set & SOLID_DESSERT_TOKENS:
            return "dessert_snack"
        if (token_set & CONTEXTUAL_DESSERT_TOKENS) and (token_set & SWEET_ANCHORS):
            return "dessert_snack"
    if "milk" in token_set or "buttermilk" in token_set or "eggnog" in token_set or "kefir" in token_set or "malted" in token_set:
        return "milk"
    if token_set & {"egg", "eggnog"}:
        return "egg"
    if first == "oil" or token_set & {"lard", "margarine", "oil", "shortening"}:
        return "oil"
    if token_set & {"chili", "soup", "stew"}:
        return "soup"
    if token_set & CONDIMENTS:
        return "condiment"
    if token_set & SPICES_HERBS:
        return "spice"
    if token_set & SEAFOOD:
        return "seafood"
    if token_set & POULTRY:
        return "poultry"
    if token_set & MEATS:
        return "meat"
    if "bean" in token_set and token_set & {"green", "snap", "string", "wax"}:
        return "vegetable"
    if token_set & LEGUMES:
        return "legume"
    if token_set & NUTS_SEEDS:
        return "nut_seed"
    if token_set & VEGETABLES:
        return "vegetable"
    if token_set & FRUITS and token_set.isdisjoint({"butter", "cheese", "cream", "milk", "yogurt"}):
        return "fruit"
    if token_set & GRAINS:
        return "grain"
    if token_set & DESSERT_SNACK:
        return "dessert_snack"
    if "supplement" in token_set or "capsule" in token_set or "tablet" in token_set:
        return "supplement"
    return "prepared_food"


def detect_attrs(tokens: list[str], norm: str, family: str) -> list[str]:
    token_set = set(tokens)
    attrs: list[str] = []
    if family in {"milk", "plant_milk", "yogurt", "cream", "cheese"}:
        if has_phrase(norm, "whole") or has_phrase(norm, "3.25 percent"):
            attrs.append("whole_fat")
        if has_phrase(norm, "2 percent") or has_phrase(norm, "reduced fat"):
            attrs.append("two_percent")
        if has_phrase(norm, "1 percent") or has_phrase(norm, "low fat"):
            attrs.append("one_percent")
        if "skim" in token_set or has_phrase(norm, "fat free") or has_phrase(norm, "0 percent"):
            attrs.append("skim")
        if has_phrase(norm, "lactose free") or has_phrase(norm, "low lactose"):
            attrs.append("lactose_free")
    if family in {"butter", "legume", "nut_seed", "oil"}:
        if "unsalted" in token_set or has_phrase(norm, "no salt"):
            attrs.append("unsalted")
        elif "salted" in token_set:
            attrs.append("salted")
    if "sweetened" in token_set:
        attrs.append("sweetened")
    if "unsweetened" in token_set:
        attrs.append("unsweetened")
    if has_phrase(norm, "sugar free") or has_phrase(norm, "no sugar"):
        attrs.append("sugar_free")
    if has_phrase(norm, "low sodium") or has_phrase(norm, "reduced sodium"):
        attrs.append("low_sodium")
    if "evaporated" in token_set:
        attrs.append("evaporated")
    if "condensed" in token_set:
        attrs.append("condensed")
    if "canned" in token_set or "can" in token_set:
        attrs.append("canned")
    if "frozen" in token_set:
        attrs.append("frozen")
    if "dehydrated" in token_set or "dried" in token_set or "dry" in token_set or "powder" in token_set:
        attrs.append("dry")
    if "fresh" in token_set:
        attrs.append("fresh")
    if "raw" in token_set:
        attrs.append("raw")
    if "baked" in token_set or "cooked" in token_set or "grilled" in token_set or "roasted" in token_set:
        attrs.append("cooked")
    if "pickled" in token_set:
        attrs.append("pickled")
    if "smoked" in token_set:
        attrs.append("smoked")
    return attrs


def meaningful_terms(tokens: list[str], family: str, attrs: list[str]) -> list[str]:
    terms: list[str] = []
    attr_noise = set(FORTIFICATION_WORDS)
    if "whole_fat" in attrs:
        attr_noise |= {"3.25", "percent", "whole"}
    if "two_percent" in attrs:
        attr_noise |= {"2", "fat", "percent", "reduced"}
    if "one_percent" in attrs:
        attr_noise |= {"1", "fat", "low", "percent"}
    if "skim" in attrs:
        attr_noise |= {"fat", "free", "nonfat", "skim"}
    if "low_sodium" in attrs:
        attr_noise |= {"low", "reduced", "sodium"}
    if "dry" in attrs:
        attr_noise |= {"dehydrated", "dried", "dry", "powder"}
    if "canned" in attrs:
        attr_noise |= {"can", "canned"}
    if "frozen" in attrs:
        attr_noise.add("frozen")
    if "evaporated" in attrs:
        attr_noise.add("evaporated")
    if "condensed" in attrs:
        attr_noise.add("condensed")
    if "fresh" in attrs:
        attr_noise.add("fresh")
    if "raw" in attrs:
        attr_noise.add("raw")
    if "cooked" in attrs:
        attr_noise |= {"baked", "cooked", "grilled", "roasted"}
    for token in tokens:
        if len(token) < 2 or token in STOPWORDS or token in attr_noise:
            continue
        if token.replace(".", "", 1).isdigit():
            continue
        if re.search(r"\d", token):
            continue
        if token in FORM_OPTIONAL and family not in {"grain", "spice"}:
            continue
        if family == "nut_butter" and token == "nut":
            continue
        if token not in terms:
            terms.append(token)
    if family == "milk" and "milk" not in terms:
        terms.insert(0, "milk")
    if family == "egg" and "egg" not in terms:
        terms.insert(0, "egg")
    return terms


def hard_terms_for(terms: list[str], family: str, attrs: list[str]) -> list[str]:
    if family == "nonfood":
        return []
    hard = [term for term in terms if term not in {"food", "plain", "regular"}]
    if family == "beverage" and "juice" in terms:
        hard = [term for term in hard if term not in {"beverage", "drink"}]
    if family == "prepared_food":
        hard = hard[:5]
    elif family in {"fruit", "legume", "meat", "nut_seed", "poultry", "seafood", "vegetable"}:
        hard = hard[:4]
    elif family in {"butter", "cheese", "cream", "egg", "grain", "milk", "oil", "spice", "yogurt"}:
        hard = hard[:5]
    if not hard and terms:
        hard = terms[:2]
    return hard


def profile_for(row: dict[str, str]) -> EshaProfile:
    description = (row.get("Description") or "").strip()
    code = (row.get("EshaCode") or "").strip()
    norm = normalize_text(description)
    tokens = tokens_for(description)
    family = detect_family(tokens, norm)
    skip_reason = "sample_or_non_retail_food" if family == "nonfood" or code == "-1" else ""
    attrs = detect_attrs(tokens, norm, family)
    terms = meaningful_terms(tokens, family, attrs)
    hard_terms = hard_terms_for(terms, family, attrs)
    fts_terms: list[str] = []
    for term in hard_terms:
        if len(term) >= 3 and term not in {"drink", "food"} and term not in fts_terms:
            fts_terms.append(term)
    for attr in attrs:
        if attr in {"canned", "condensed", "evaporated", "frozen", "pickled", "smoked", "unsalted"} and attr not in fts_terms:
            fts_terms.append(attr)
        elif attr == "dry":
            dry_term = "powder" if family in {"beverage", "milk"} else "dry"
            if dry_term not in fts_terms:
                fts_terms.append(dry_term)
        elif attr == "skim" and "skim" not in fts_terms:
            fts_terms.append("skim")
        elif attr == "whole_fat" and "whole" not in fts_terms:
            fts_terms.append("whole")
    return EshaProfile(
        code=code,
        description=description,
        norm=norm,
        tokens=tuple(tokens),
        family=family,
        hard_terms=tuple(hard_terms),
        attrs=tuple(attrs),
        fts_terms=tuple(fts_terms[:6]),
        skip_reason=skip_reason,
    )
