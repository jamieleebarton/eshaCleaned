from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import match_esha_to_products as matcher


TOKEN_RE = re.compile(r"[a-z][a-z0-9']*")

MODIFIER_TERMS = {
    "all",
    "and",
    "baby",
    "bag",
    "bags",
    "boneless",
    "bone",
    "brand",
    "classic",
    "count",
    "cut",
    "double",
    "extra",
    "fat",
    "flavor",
    "flavored",
    "free",
    "fresh",
    "freshly",
    "grade",
    "in",
    "jumbo",
    "large",
    "light",
    "medium",
    "mini",
    "natural",
    "organic",
    "peeled",
    "premium",
    "select",
    "size",
    "skinless",
    "small",
    "style",
    "trim",
    "whole",
}

STATE_TERMS = {
    "baked",
    "boiled",
    "canned",
    "cooked",
    "dehydrated",
    "dried",
    "dry",
    "freeze",
    "freezedried",
    "frozen",
    "grilled",
    "raw",
    "roasted",
    "smoked",
    "steamed",
}

FRUIT_TERMS = set(matcher.FRUITS) | {
    "blueberry",
    "cranberry",
    "mango",
    "prune",
    "raisin",
}
VEGETABLE_TERMS = set(matcher.VEGETABLES) | {"carrot", "beet", "pea"}
MEAT_TERMS = set(matcher.MEATS)
POULTRY_TERMS = set(matcher.POULTRY)
SEAFOOD_TERMS = set(matcher.SEAFOOD)
SPECIES_TERMS = {"beef", "pork", "turkey", "chicken", "lamb", "veal"}

DAIRY_TERMS = {
    "butter",
    "buttermilk",
    "cheese",
    "cream",
    "creme",
    "fraiche",
    "half",
    "milk",
    "yogurt",
}

FOOD_DOMAIN_TERMS = FRUIT_TERMS | VEGETABLE_TERMS | MEAT_TERMS | POULTRY_TERMS | SEAFOOD_TERMS

PREPARED_MEAL_CATEGORY_MARKERS = {
    "breakfast sandwiches",
    "breakfast sandwich",
    "frozen breakfast",
    "frozen dinners",
    "dinners & entrees",
    "dinners and entrees",
    "entrees",
    "prepared meals",
    "ready-made",
}

WHOLE_FRUIT_SNACK_CATEGORY_MARKERS = {
    "wholesome snacks",
    "dried fruit",
    "nuts, seeds & dried fruit",
}

PROCESSED_FRUIT_FORMS = {
    "bar",
    "candy",
    "cake",
    "chips",
    "cookie",
    "cracker",
    "drink",
    "fruit_snacks",
    "juice",
    "juice_drink",
    "muffin",
    "sauce",
    "snack",
}

FORM_TERMS = {
    "bagel",
    "bar",
    "biscuit",
    "bread",
    "burrito",
    "cake",
    "candy",
    "cereal",
    "chips",
    "chicken_strips",
    "cookie",
    "cracker",
    "doughnut",
    "dressing",
    "fruit_snacks",
    "meal",
    "muffin",
    "nuggets",
    "nuts",
    "pasta",
    "pizza",
    "popcorn",
    "pretzels",
    "salad",
    "salad_dressing",
    "sausage",
    "sandwich",
    "sauce",
    "snack",
    "soup",
    "strip",
    "strips",
    "tenders",
    "wrap",
    "juice",
    "drink",
    "coffee",
    "dry_pasta",
    "tea",
    "mashed_potatoes",
    "turkey_bacon",
}

ALL_IDENTITY_TERMS = (
    FRUIT_TERMS
    | VEGETABLE_TERMS
    | MEAT_TERMS
    | POULTRY_TERMS
    | SEAFOOD_TERMS
    | DAIRY_TERMS
    | FORM_TERMS
    | {"egg", "eggs", "honey", "mustard", "oil", "olive", "rice", "sausage"}
)

DOMAIN_TERMS = {
    "fruit": FRUIT_TERMS,
    "vegetable": VEGETABLE_TERMS,
    "meat": MEAT_TERMS,
    "poultry": POULTRY_TERMS,
    "seafood": SEAFOOD_TERMS,
    "dairy": DAIRY_TERMS,
}

EXCLUSIVE_FORM_MISMATCHES = {
    "sandwich": {"biscuit", "cake", "cracker", "muffin", "salad", "snack"},
    "salad_dressing": {"mustard", "sauce", "dip", "salad", "bacon", "cheese"},
    "dried_fruit": {
        "bar",
        "cake",
        "candy",
        "cereal",
        "chips",
        "cookie",
        "cracker",
        "ice_cream",
        "juice",
        "juice_drink",
        "muffin",
        "pretzels",
        "seeds",
        "snack",
    },
    "produce": {"salad", "meal", "dish", "sandwich", "soup", "juice", "dressing"},
    "raw_meat": {"sandwich", "meal", "dish", "soup", "salad", "vegetarian_meat"},
    "canned_seafood": {"oil", "sandwich", "meal", "dish", "salad", "sauce"},
    "mashed_potatoes": {"meal", "dish", "pizza", "biscuit", "muffin", "cake"},
    "chicken_strips": {"bar", "burrito", "cereal", "dish", "meal", "pasta_dish", "pizza", "salad", "sandwich", "snack"},
    "turkey_bacon": {"bacon", "beef", "chicken", "pork", "sausage"},
    "tea": {"cake", "cookie", "meal", "sandwich", "bar", "snack"},
    "coffee": {"cake", "cookie", "meal", "sandwich", "bar", "snack"},
    "dry_pasta": {"dish", "meal", "pasta_dish", "pizza", "sauce", "salad"},
    "salad": {"salad_dressing", "sauce", "dip"},
    "sausage": {"beef", "chicken", "pork", "turkey"},
    "cookie": {"biscuit", "cake", "cracker", "muffin"},
    "cracker": {"biscuit", "cake", "cookie", "muffin"},
    "pretzels": {"biscuit", "cake", "cookie", "cracker"},
}

FORM_PHRASES = (
    ("mashed potatoes", "mashed_potatoes"),
    ("mashed potato", "mashed_potatoes"),
    ("chicken strips", "chicken_strips"),
    ("chicken strip", "chicken_strips"),
    ("fruit snacks", "fruit_snacks"),
    ("fruit snack", "fruit_snacks"),
    ("salad dressing", "salad_dressing"),
    ("sausage", "sausage"),
    ("breakfast sandwich", "sandwich"),
    ("sandwich bread", "bread"),
    ("sandwich", "sandwich"),
    ("burrito", "burrito"),
    ("wrap", "wrap"),
    ("meal", "prepared_meal"),
    ("nuggets", "nuggets"),
    ("nugget", "nuggets"),
    ("tenders", "tenders"),
    ("tender", "tenders"),
    ("strips", "strips"),
    ("strip", "strips"),
    ("biscuit", "biscuit"),
    ("muffin", "muffin"),
    ("dressing", "salad_dressing"),
    ("mustard", "mustard"),
    ("juice drink", "juice_drink"),
    ("tea", "tea"),
    ("coffee", "coffee"),
    ("juice", "juice"),
    ("drink", "drink"),
    ("sardine", "fish"),
    ("mackerel", "fish"),
    ("fish", "fish"),
    ("pasta dish", "pasta_dish"),
    ("dish", "prepared_meal"),
    ("spaghetti", "dry_pasta"),
    ("macaroni", "dry_pasta"),
    ("ravioli", "dry_pasta"),
    ("tortellini", "dry_pasta"),
    ("noodles", "dry_pasta"),
    ("noodle", "dry_pasta"),
    ("pasta", "pasta"),
    ("cookie", "cookie"),
    ("cake", "cake"),
    ("cracker", "cracker"),
    ("bread", "bread"),
    ("nut", "nuts"),
    ("chips", "chips"),
    ("chip", "chips"),
    ("pretzel", "pretzels"),
    ("popcorn", "popcorn"),
    ("salad", "salad"),
    ("cream", "cream"),
    ("milk", "milk"),
    ("cheese", "cheese"),
    ("oil", "oil"),
)


@dataclass(frozen=True)
class FoodIdentity:
    source: str
    text: str
    category: str
    tokens: frozenset[str]
    title_tokens: frozenset[str]
    ingredient_tokens: frozenset[str]
    form: str
    state_terms: frozenset[str]
    identity_terms: frozenset[str]
    primary_terms: frozenset[str]
    component_terms: frozenset[str]


def norm_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def norm_token(token: str) -> str:
    token = matcher.singular(str(token).lower().strip("'"))
    token = matcher.TOKEN_SYNONYMS.get(token, token)
    if token == "blueberrie":
        return "blueberry"
    if token == "strawberrie":
        return "strawberry"
    if token == "cranberrie":
        return "cranberry"
    if token == "rasberrie":
        return "raspberry"
    if token == "cherrie":
        return "cherry"
    if token in {"cookie", "cooky", "cooie"}:
        return "cookie"
    if token == "cracker":
        return "cracker"
    if token == "potatoe":
        return "potato"
    if token == "tomatoe":
        return "tomato"
    return token


def tokenize(value: object) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in TOKEN_RE.findall(norm_text(value)):
        token = norm_token(raw)
        if len(token) < 2:
            continue
        expanded = (token, *matcher.COMPOUND_TOKEN_EXPANSIONS.get(token, ()))
        for part in expanded:
            part = norm_token(part)
            if len(part) < 2 or part in seen:
                continue
            seen.add(part)
            out.append(part)
    return tuple(out)


def split_signature(value: object) -> frozenset[str]:
    return frozenset(norm_token(t) for t in str(value or "").split() if t)


def detect_form(text: str, category: str, tokens: set[str], identity_terms: set[str], *, is_esha: bool) -> str:
    body = f"{norm_text(text)} {norm_text(category)}"
    category_norm = norm_text(category)

    if not is_esha:
        text_norm = norm_text(text)
        category_has_prepared_meal = any(marker in category_norm for marker in PREPARED_MEAL_CATEGORY_MARKERS)
        explicit_fruit_dried_state = bool(tokens & {"dried", "freeze", "freezedried", "dehydrated", "prune", "raisin"})
        whole_fruit_snack_category = any(marker in category_norm for marker in WHOLE_FRUIT_SNACK_CATEGORY_MARKERS)
        fruit_identity = identity_terms & FRUIT_TERMS
        processed_fruit_form = bool(identity_terms & PROCESSED_FRUIT_FORMS)

        if "sandwich bread" in text_norm:
            return "bread"
        if "turkey bacon" in text_norm and (
            any(x in category_norm for x in ("bacon", "sausages", "ribs"))
            or any(x in text_norm for x in ("pieces", "crumbles", "chopped", "formed"))
        ):
            return "turkey_bacon"
        if "salad" in text_norm and any(x in text_norm for x in ("lettuce", "romaine", "cobb", "greens")):
            return "salad"
        if "breakfast sandwich" in category_norm or "sandwich" in text_norm:
            return "sandwich"
        if "sausage" in text_norm or "sausages" in category_norm or "hotdogs" in category_norm or "brats" in category_norm:
            return "sausage"
        if "soup" in category_norm or "soup" in text_norm:
            return "soup"
        if "pasta by shape" in category_norm and not any(
            marker in text_norm for marker in ("alfredo", "side dish", "sauce", "meal", "dinner", "with grilled", "with chicken")
        ):
            return "dry_pasta"
        if "tea" in category_norm or "tea" in tokens:
            return "tea"
        if "coffee" in category_norm or "coffee" in tokens:
            return "coffee"
        if any(
            x in category_norm
            for x in (
                "powdered drinks",
                "energy, protein",
                "muscle recovery drinks",
                "fruit & vegetable juice",
                "nectars",
                "fruit drinks",
                "iced & bottle tea",
                "liquid water enhancer",
                "water",
                "soda",
                "other drinks",
            )
        ):
            return "juice_drink" if "juice" in category_norm else "drink"
        if "plant based milk" in category_norm:
            return "milk"
        if any(x in text_norm for x in ("beverage", "smoothie", "shake", "drink mix", "lemonade", "sparkling water")):
            return "drink"
        if "salad" in text_norm and "dressing" not in text_norm:
            return "salad"
        # Title wins over ambiguous retail categories like "Cookies & Biscuits".
        # Otherwise every cookie/cracker in that category can be routed to a
        # US-style biscuit code just because the category contains "biscuits".
        if any(x in text_norm for x in ("cookie", "cookies", "oreo", "snickerdoodle")):
            return "cookie"
        if any(x in text_norm for x in ("cracker", "crackers", "crckr", "goldfish", "cheez-it", "cheez it", "graham")):
            return "cracker"
        if "pretzel" in text_norm or "pretzels" in text_norm:
            return "pretzels"
        if "donut" in text_norm or "doughnut" in text_norm:
            return "doughnut"
        if "fudge" in text_norm or "candy wafer" in text_norm or "candy wafers" in text_norm:
            return "candy"
        if ("cookies & biscuits" in category_norm or "biscuits/cookies" in category_norm) and "biscuit" not in text_norm:
            return "cookie"
        if (
            "chicken strip" in text_norm
            and not category_has_prepared_meal
            and not any(word in text_norm for word in ("pizza", "salad", "wrap", "sandwich", "pasta"))
        ):
            return "chicken_strips"
        if "canned seafood" in category_norm:
            return "canned_seafood"
        if "unprepared" in category_norm and (identity_terms & (MEAT_TERMS | POULTRY_TERMS)):
            return "raw_meat"
        if "pre-packaged fruit" in category_norm and (identity_terms & (FRUIT_TERMS | VEGETABLE_TERMS)):
            return "produce"
        if "salad dressing" in category_norm or "mayonnaise" in category_norm:
            return "salad_dressing"
        if ("mashed potato" in text_norm or "mashed potatoes" in text_norm) and not category_has_prepared_meal:
            return "mashed_potatoes"
        if fruit_identity and (explicit_fruit_dried_state or (whole_fruit_snack_category and not processed_fruit_form)):
            return "dried_fruit"
        if category_has_prepared_meal:
            return "prepared_meal"
    else:
        head = norm_text(str(text or "").split(",", 1)[0])
        if head in {
            "bagel",
            "biscuit",
            "bread",
            "cake",
            "coffee",
            "cookie",
            "cracker",
            "drink",
            "juice",
            "juice drink",
            "muffin",
            "mustard",
            "pasta",
            "popcorn",
            "pretzels",
            "salad",
            "sausage",
            "soup",
            "tea",
        }:
            return "juice_drink" if head == "juice drink" else ("dry_pasta" if head == "pasta" else head)
        if head in {"noodles", "macaroni", "spaghetti", "ravioli", "tortellini"}:
            return "dry_pasta"
        if head == "bacon":
            return "turkey_bacon" if "turkey" in identity_terms else "bacon"
        if head == "salad dressing":
            return "salad_dressing"
        if head == "breakfast sandwich" or head == "sandwich":
            return "sandwich"
        if head == "mashed potatoes":
            return "mashed_potatoes"
        if head == "strips" and "chicken" in identity_terms:
            return "chicken_strips"
        if head == "chicken":
            if "strip" in tokens or "strips" in tokens:
                return "chicken_strips"
            return "chicken"
        if body.startswith("fish,") or body.startswith("sardine") or body.startswith("sardines") or body.startswith("mackerel"):
            return "fish"
        if body.startswith("breakfast sandwich") or body.startswith("sandwich"):
            return "sandwich"
        if body.startswith("salad dressing"):
            return "salad_dressing"
        if body.startswith("fruit snacks"):
            return "fruit_snacks"
        if body.startswith("pork") or body.startswith("beef") or body.startswith("lamb") or body.startswith("veal"):
            return "raw_meat" if "raw" in tokens else "meat"
        if (identity_terms & FRUIT_TERMS) and ("dried" in tokens or "freeze" in tokens or "dehydrated" in tokens):
            return "dried_fruit"
        if body.startswith("carrot") or body.startswith("beet") or body.startswith("vegetable"):
            return "produce"

    for phrase, form in FORM_PHRASES:
        if phrase in body:
            return form
    return ""


def domain_for_terms(terms: Iterable[str]) -> dict[str, set[str]]:
    term_set = set(terms)
    return {domain: term_set & values for domain, values in DOMAIN_TERMS.items() if term_set & values}


def choose_primary(identity_terms: set[str], form: str, category: str, *, is_esha: bool) -> frozenset[str]:
    terms = set(identity_terms) - MODIFIER_TERMS - STATE_TERMS

    if form in {"tea", "coffee", "drink", "juice", "juice_drink", "dry_pasta"}:
        return frozenset({form})

    if form in {
        "sandwich",
        "salad_dressing",
        "fruit_snacks",
        "dried_fruit",
        "canned_seafood",
        "raw_meat",
        "produce",
        "prepared_meal",
        "mashed_potatoes",
        "chicken_strips",
        "turkey_bacon",
        "salad",
    }:
        return frozenset(terms)
    if terms & (FRUIT_TERMS | VEGETABLE_TERMS | MEAT_TERMS | POULTRY_TERMS | SEAFOOD_TERMS):
        return frozenset(terms & (FRUIT_TERMS | VEGETABLE_TERMS | MEAT_TERMS | POULTRY_TERMS | SEAFOOD_TERMS))
    if terms & DAIRY_TERMS:
        return frozenset(terms & DAIRY_TERMS)
    if form:
        return frozenset({form})
    return frozenset(terms)


def product_identity(
    *,
    product_description: str,
    category: str,
    ingredient_signature: str = "",
) -> FoodIdentity:
    title_tokens = frozenset(tokenize(product_description))
    ingredient_tokens = split_signature(ingredient_signature)
    category_tokens = frozenset(tokenize(category))
    tokens = frozenset(title_tokens | ingredient_tokens | category_tokens)
    title_identity_terms = {t for t in title_tokens if t in ALL_IDENTITY_TERMS and t not in MODIFIER_TERMS}
    ingredient_identity_terms = {t for t in ingredient_tokens if t in ALL_IDENTITY_TERMS and t not in MODIFIER_TERMS}
    category_identity_terms = {t for t in category_tokens if t in ALL_IDENTITY_TERMS and t not in MODIFIER_TERMS}
    # Product identity is led by title/category. Ingredients support the title;
    # they do not turn a complex meal into every component it contains.
    identity_terms = set(title_identity_terms)
    if identity_terms:
        identity_terms |= ingredient_identity_terms & identity_terms
    else:
        identity_terms |= category_identity_terms
        if len(ingredient_identity_terms) <= 4:
            identity_terms |= ingredient_identity_terms
    # Vehicles/flavors should not become primary when the product has a stronger
    # food identity.
    if identity_terms & SEAFOOD_TERMS:
        identity_terms -= {"oil", "olive"}
    if identity_terms & (MEAT_TERMS | POULTRY_TERMS):
        identity_terms -= {"bone"}
    form = detect_form(product_description, category, set(title_tokens | category_tokens), identity_terms, is_esha=False)
    if form == "sandwich" and "biscuit" in identity_terms:
        identity_terms -= {"butter", "buttermilk", "milk"}
    if form == "chicken_strips":
        identity_terms = (identity_terms & (POULTRY_TERMS | {"strip", "strips", "tenders", "nuggets"})) | {"chicken", "strip"}
    state_terms = frozenset(t for t in tokens if t in STATE_TERMS)
    primary = choose_primary(identity_terms, form, category, is_esha=False)
    return FoodIdentity(
        source="product",
        text=product_description,
        category=category,
        tokens=tokens,
        title_tokens=title_tokens,
        ingredient_tokens=ingredient_tokens,
        form=form,
        state_terms=state_terms,
        identity_terms=frozenset(identity_terms),
        primary_terms=primary,
        component_terms=frozenset(identity_terms | state_terms),
    )


def esha_identity(description: str) -> FoodIdentity:
    head = str(description or "").split(",", 1)[0]
    title_tokens = frozenset(tokenize(description))
    tokens = title_tokens
    identity_terms = {t for t in tokens if t in ALL_IDENTITY_TERMS and t not in MODIFIER_TERMS}
    form = detect_form(description, "", set(tokens), identity_terms, is_esha=True)
    state_terms = frozenset(t for t in tokens if t in STATE_TERMS)
    primary = choose_primary(identity_terms, form, "", is_esha=True)
    return FoodIdentity(
        source="esha",
        text=description,
        category="",
        tokens=tokens,
        title_tokens=title_tokens,
        ingredient_tokens=frozenset(),
        form=form,
        state_terms=state_terms,
        identity_terms=frozenset(identity_terms),
        primary_terms=primary,
        component_terms=frozenset(identity_terms | state_terms),
    )


def _domain_mismatch(product: FoodIdentity, candidate: FoodIdentity) -> str:
    product_domains = domain_for_terms(product.primary_terms)
    candidate_domains = domain_for_terms(candidate.primary_terms)
    for domain, product_terms in product_domains.items():
        candidate_terms = candidate_domains.get(domain, set())
        if candidate_terms and not (product_terms & candidate_terms):
            return f"{domain}_identity_mismatch:{','.join(sorted(product_terms))}!={','.join(sorted(candidate_terms))}"
        if (
            not candidate_terms
            and candidate.primary_terms
            and product.form not in {"sandwich", "salad_dressing", "fruit_snacks", "prepared_meal"}
        ):
            return f"{domain}_identity_missing:{','.join(sorted(product_terms))}->candidate:{candidate.form or 'none'}"
    return ""


def compatibility_reason(product: FoodIdentity, candidate: FoodIdentity) -> str:
    if not product.primary_terms:
        return ""

    mismatch = _domain_mismatch(product, candidate)
    if mismatch:
        return mismatch

    if product.form in EXCLUSIVE_FORM_MISMATCHES and candidate.form in EXCLUSIVE_FORM_MISMATCHES[product.form]:
        return f"form_mismatch:{product.form}!={candidate.form}"

    if product.form == "sandwich" and candidate.form != "sandwich":
        return f"form_mismatch:sandwich!={candidate.form or 'none'}"

    if product.form == "mashed_potatoes" and candidate.form != "mashed_potatoes":
        return f"form_mismatch:mashed_potatoes!={candidate.form or 'none'}"

    if product.form == "chicken_strips":
        if "chicken" not in candidate.identity_terms and "chicken" not in candidate.primary_terms:
            return f"poultry_identity_missing:chicken->candidate:{candidate.form or 'none'}"
        if candidate.form in EXCLUSIVE_FORM_MISMATCHES["chicken_strips"]:
            return f"form_mismatch:chicken_strips!={candidate.form}"

    if product.form == "turkey_bacon":
        if candidate.form != "turkey_bacon":
            return f"form_mismatch:turkey_bacon!={candidate.form or 'none'}"

    if product.form == "sausage":
        product_species = product.primary_terms & SPECIES_TERMS
        candidate_species = candidate.primary_terms & SPECIES_TERMS
        if candidate.form != "sausage":
            return f"form_mismatch:sausage!={candidate.form or 'none'}"
        if len(product_species) == 1 and candidate_species and not (product_species & candidate_species):
            return f"sausage_species_mismatch:{','.join(sorted(product_species))}!={','.join(sorted(candidate_species))}"
        if len(product_species) == 1 and not candidate_species:
            return f"sausage_species_missing:{','.join(sorted(product_species))}->candidate:{candidate.form or 'none'}"

    if product.form == "soup":
        product_species = product.primary_terms & SPECIES_TERMS
        candidate_species = candidate.primary_terms & SPECIES_TERMS
        if len(product_species) == 1 and candidate_species and not (product_species & candidate_species):
            return f"soup_species_mismatch:{','.join(sorted(product_species))}!={','.join(sorted(candidate_species))}"

    if product.form in {"tea", "coffee"} and candidate.form != product.form:
        return f"form_mismatch:{product.form}!={candidate.form or 'none'}"

    if product.form in {"juice", "juice_drink"} and candidate.form not in {"juice", "juice_drink", "drink"}:
        return f"form_mismatch:{product.form}!={candidate.form or 'none'}"

    if product.form == "dry_pasta" and candidate.form != "dry_pasta":
        return f"form_mismatch:dry_pasta!={candidate.form or 'none'}"

    if product.form == "salad" and candidate.form not in {"salad", "prepared_meal"}:
        return f"form_mismatch:salad!={candidate.form or 'none'}"

    if product.form == "prepared_meal" and candidate.form in {
        "bar",
        "biscuit",
        "burrito",
        "cake",
        "chips",
        "cookie",
        "cracker",
        "muffin",
        "mustard",
        "oil",
        "popcorn",
        "salad",
        "sandwich",
        "sauce",
        "pasta",
        "wrap",
    }:
        return f"form_mismatch:prepared_meal!={candidate.form}"

    if product.form == "prepared_meal":
        product_species = product.primary_terms & SPECIES_TERMS
        candidate_species = candidate.primary_terms & SPECIES_TERMS
        if len(product_species) == 1 and candidate_species and not (product_species & candidate_species):
            return f"prepared_meal_species_mismatch:{','.join(sorted(product_species))}!={','.join(sorted(candidate_species))}"
        if len(product_species) == 1 and not candidate_species:
            return f"prepared_meal_species_missing:{','.join(sorted(product_species))}->candidate:{candidate.form or 'none'}"
        if len(product_species) == 1 and candidate.form in {"sauce", "pasta", "dry_pasta"}:
            return f"prepared_meal_species_missing:{','.join(sorted(product_species))}->candidate:{candidate.form or 'none'}"

    if product.form == "salad_dressing":
        if candidate.form != "salad_dressing":
            return f"form_mismatch:salad_dressing!={candidate.form or 'none'}"
        for flavor in ("mustard", "ranch", "honey"):
            if flavor in product.identity_terms and flavor not in candidate.identity_terms:
                return f"dressing_flavor_missing:{flavor}"

    if product.form == "canned_seafood":
        if candidate.form != "fish":
            return f"form_mismatch:canned_seafood!={candidate.form or 'none'}"
        species = product.primary_terms & SEAFOOD_TERMS
        candidate_species = candidate.primary_terms & SEAFOOD_TERMS
        if species and candidate_species and not (species & candidate_species):
            return f"seafood_identity_mismatch:{','.join(sorted(species))}!={','.join(sorted(candidate_species))}"

    if product.form == "raw_meat":
        product_species = product.primary_terms & (MEAT_TERMS | POULTRY_TERMS)
        candidate_species = candidate.primary_terms & (MEAT_TERMS | POULTRY_TERMS)
        if candidate.form not in {"raw_meat", "meat"}:
            return f"form_mismatch:raw_meat!={candidate.form or 'none'}"
        if product_species and candidate_species and not (product_species & candidate_species):
            return f"meat_species_mismatch:{','.join(sorted(product_species))}!={','.join(sorted(candidate_species))}"

    if product.form == "produce":
        produce_terms = product.primary_terms & (FRUIT_TERMS | VEGETABLE_TERMS)
        candidate_terms = candidate.primary_terms & (FRUIT_TERMS | VEGETABLE_TERMS)
        if candidate.form not in {"produce", "dried_fruit", ""} and not (produce_terms & candidate_terms):
            return f"form_mismatch:produce!={candidate.form or 'none'}"
        if produce_terms and candidate_terms and not (produce_terms & candidate_terms):
            return f"produce_identity_mismatch:{','.join(sorted(produce_terms))}!={','.join(sorted(candidate_terms))}"

    if product.form == "dried_fruit":
        fruit = product.primary_terms & FRUIT_TERMS
        candidate_fruit = candidate.primary_terms & FRUIT_TERMS
        if fruit and candidate_fruit and not (fruit & candidate_fruit):
            return f"fruit_identity_mismatch:{','.join(sorted(fruit))}!={','.join(sorted(candidate_fruit))}"
        if candidate.form != "dried_fruit":
            return f"form_mismatch:dried_fruit!={candidate.form or 'none'}"
        if not (candidate.state_terms & {"dried", "dry", "dehydrated", "freeze", "freezedried"}):
            return "state_mismatch:dried_product_to_non_dried_candidate"

    strict_forms = {
        "biscuit",
        "bread",
        "cake",
        "candy",
        "cheese",
        "chips",
        "chicken",
        "chicken_strips",
        "cookie",
        "cracker",
        "coffee",
        "cream",
        "drink",
        "dry_pasta",
        "fruit_snacks",
        "milk",
        "muffin",
        "mustard",
        "nuggets",
        "oil",
        "popcorn",
        "pretzels",
        "salad",
        "sausage",
        "sauce",
        "tea",
        "tenders",
        "turkey_bacon",
    }
    if product.form in strict_forms and candidate.form and candidate.form != product.form:
        return f"form_mismatch:{product.form}!={candidate.form}"

    return ""


def compatible(product: FoodIdentity, candidate: FoodIdentity) -> bool:
    return compatibility_reason(product, candidate) == ""
