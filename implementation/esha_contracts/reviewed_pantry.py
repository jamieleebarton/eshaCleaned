from __future__ import annotations

from .contract_base import ContractFn, ContractSpec, MatchDecision, ProductFacts, accept, match_spec, reject


SALT_CATEGORIES = (
    "salt",
    "seasoning",
    "spice",
    "herb",
    "extract",
)

WATER_CATEGORIES = (
    "water",
    "drink",
    "beverage",
)

MILK_CATEGORIES = (
    "milk",
    "dairy",
    "beverage",
)

JUICE_CATEGORIES = (
    "juice",
    "drink",
    "beverage",
    "water enhancer",
    "frozen fruit",
    "fruit juice",
)

BAKING_CATEGORIES = (
    "baking",
    "extract",
    "supply",
)

SOY_SAUCE_CATEGORIES = (
    "sauce",
    "condiment",
    "oriental",
    "ethnic",
    "cooking sauce",
)

FLOUR_CATEGORIES = (
    "flour",
    "grain",
    "corn meal",
    "baking",
)

PLANT_MILK_TERMS = (
    "almond",
    "oat",
    "soy",
    "soymilk",
    "coconut",
    "rice",
    "cashew",
    "hemp",
    "plant",
)

FLAVORED_MILK_TERMS = (
    "banana",
    "caramel",
    "chocolate",
    "cocoa",
    "coffee",
    "flavor",
    "flavored",
    "malted",
    "mocha",
    "protein",
    "shake",
    "smoothie",
    "strawberry",
    "vanilla",
)

OTHER_DAIRY_TERMS = (
    "buttermilk",
    "cheese",
    "condensed",
    "cream",
    "evaporated",
    "kefir",
    "powder",
    "yogurt",
    "yoghurt",
)

PLAIN_WATER_EXCLUDES = (
    "alkaline",
    "berry",
    "blackberry",
    "blueberry",
    "beverage",
    "bubble",
    "bubbles",
    "caffeinated",
    "carbonated",
    "cherry",
    "coconut",
    "cranberry",
    "cucumber",
    "essence",
    "flavor",
    "flavored",
    "ginger",
    "grape",
    "lemon",
    "lemonade",
    "lime",
    "mango",
    "melon",
    "mint",
    "orange",
    "passion",
    "peach",
    "pineapple",
    "pomegranate",
    "raspberry",
    "sparkling",
    "strawberry",
    "seltzer",
    "tonic",
    "vitamin",
    "watermelon",
)

PLAIN_SALT_EXCLUDES = (
    "bbq",
    "barbecue",
    "canning",
    "celery",
    "garlic",
    "herb",
    "jalapeno",
    "light",
    "lite",
    "low",
    "onion",
    "pepper",
    "pickling",
    "popcorn",
    "potassium",
    "reduced",
    "seasoning",
    "seasonings",
    "seasoned",
    "smoked",
    "sodium",
    "spice",
    "spices",
    "substitute",
    "taco",
    "truffle",
)

PLAIN_SALT_INGREDIENT_EXCLUDES = (
    "chili",
    "cumin",
    "garlic",
    "mustard",
    "onion",
    "paprika",
    "pepper",
    "sage",
    "spice",
    "spices",
    "thyme",
    "turmeric",
)

LEMON_JUICE_EXCLUDES = (
    "apple",
    "basil",
    "blend",
    "cocktail",
    "cucumber",
    "drink",
    "ginger",
    "grape",
    "island",
    "lemonade",
    "lime",
    "mango",
    "marinade",
    "orange",
    "passion",
    "pepper",
    "pineapple",
    "raspberry",
    "slice",
    "sliced",
    "sparkling",
    "strawberry",
    "watermelon",
)

SOY_SAUCE_EXCLUDES = (
    "bao",
    "bun",
    "chicken",
    "cracker",
    "dumpling",
    "filled",
    "noodle",
    "paste",
    "pizza",
    "pork",
    "potsticker",
    "ramen",
    "sweet",
    "tamari",
    "wrapped",
)

FLOUR_EXCLUDES = (
    "almond",
    "bread",
    "cake",
    "coconut",
    "gluten",
    "pastry",
    "pizza",
    "rising",
    "self",
)

SELF_RISING_FLOUR_EXCLUDES = (
    "almond",
    "bread",
    "cake",
    "coconut",
    "corn",
    "cornbread",
    "cornmeal",
    "gluten",
    "mix",
    "meal",
    "pancake",
    "pastry",
    "pizza",
    "whole",
)

SELF_RISING_FLOUR_INGREDIENT_EXCLUDES = (
    "corn",
    "cornmeal",
    "egg",
    "eggs",
    "milk",
    "oil",
    "sugar",
    "syrup",
    "whey",
)


def make_plain_salt_contract(esha_code: str, esha_description: str) -> ContractFn:
    spec = ContractSpec(
        esha_code=esha_code,
        esha_description=esha_description,
        allowed_categories=SALT_CATEGORIES,
        search_terms=("salt",),
        required_terms=("salt",),
        exclude_terms=PLAIN_SALT_EXCLUDES,
    )

    def contract(product: ProductFacts) -> MatchDecision:
        decision = match_spec(product, spec)
        if decision.status != "accept":
            return decision
        ingredient_excluded = [
            term for term in PLAIN_SALT_INGREDIENT_EXCLUDES if product.ingredients_have_any(term)
        ]
        if ingredient_excluded:
            return reject(f"{esha_code} excluded ingredient term(s): " + "|".join(ingredient_excluded))
        return decision

    return contract


def make_plain_water_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*WATER_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any("water"):
            return reject(f"{esha_code} missing required term(s): water")
        excluded = [term for term in PLAIN_WATER_EXCLUDES if product.has_any(term)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        ingredient_excluded = [
            term for term in ("co2", "carbonated", "flavor", "sweetener")
            if product.ingredients_have_any(term)
        ]
        if ingredient_excluded:
            return reject(f"{esha_code} excluded ingredient term(s): " + "|".join(ingredient_excluded))
        if product.has_phrase("carbonated water"):
            return reject(f"{esha_code} excluded phrase(s): carbonated water")
        if (
            product.ingredients_have_phrase("carbonated water")
            or product.ingredients_have_phrase("natural flavor")
            or product.ingredients_have_phrase("co2")
        ):
            return reject(f"{esha_code} excluded ingredient phrase(s): carbonated/flavored water")
        return accept(f"{esha_code} reviewed plain water contract accepted")

    return contract


def make_plain_milk_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*MILK_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any("milk"):
            return reject(f"{esha_code} missing required term(s): milk")
        plant_hits = [term for term in PLANT_MILK_TERMS if product.has_any(term)]
        if plant_hits:
            return reject(f"{esha_code} excluded term(s): " + "|".join(plant_hits))
        flavor_hits = [term for term in FLAVORED_MILK_TERMS if product.has_any(term)]
        if flavor_hits:
            return reject(f"{esha_code} excluded term(s): " + "|".join(flavor_hits))
        dairy_hits = [term for term in OTHER_DAIRY_TERMS if product.has_any(term)]
        if dairy_hits:
            return reject(f"{esha_code} excluded term(s): " + "|".join(dairy_hits))
        if product.has_phrase("ice cream"):
            return reject(f"{esha_code} excluded phrase(s): ice cream")
        return accept(f"{esha_code} reviewed plain milk contract accepted")

    return contract


def make_lemon_juice_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*JUICE_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_all("lemon", "juice"):
            return reject(f"{esha_code} missing required term(s): lemon|juice")
        excluded = [term for term in LEMON_JUICE_EXCLUDES if product.has_any(term)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed lemon juice contract accepted")

    return contract


def make_baking_powder_contract(esha_code: str, esha_description: str) -> ContractFn:
    spec = ContractSpec(
        esha_code=esha_code,
        esha_description=esha_description,
        allowed_categories=BAKING_CATEGORIES,
        search_terms=("baking", "powder"),
        required_terms=("baking", "powder"),
        exclude_terms=("mix",),
    )

    def contract(product: ProductFacts) -> MatchDecision:
        return match_spec(product, spec)

    return contract


def make_baking_soda_contract(esha_code: str, esha_description: str) -> ContractFn:
    spec = ContractSpec(
        esha_code=esha_code,
        esha_description=esha_description,
        allowed_categories=BAKING_CATEGORIES,
        search_terms=("baking", "soda"),
        required_terms=("baking", "soda"),
        exclude_terms=("drink", "energy"),
    )

    def contract(product: ProductFacts) -> MatchDecision:
        return match_spec(product, spec)

    return contract


def make_soy_sauce_contract(esha_code: str, esha_description: str) -> ContractFn:
    spec = ContractSpec(
        esha_code=esha_code,
        esha_description=esha_description,
        allowed_categories=SOY_SAUCE_CATEGORIES,
        search_terms=("soy", "sauce"),
        required_terms=("soy", "sauce"),
        exclude_terms=SOY_SAUCE_EXCLUDES,
    )

    def contract(product: ProductFacts) -> MatchDecision:
        return match_spec(product, spec)

    return contract


def make_all_purpose_flour_contract(esha_code: str, esha_description: str) -> ContractFn:
    spec = ContractSpec(
        esha_code=esha_code,
        esha_description=esha_description,
        allowed_categories=FLOUR_CATEGORIES,
        search_terms=("flour", "all", "purpose"),
        required_terms=("flour", "all", "purpose"),
        exclude_terms=FLOUR_EXCLUDES,
    )

    def contract(product: ProductFacts) -> MatchDecision:
        return match_spec(product, spec)

    return contract


def make_self_rising_flour_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.has_any("flour"):
            return reject(f"{esha_code} missing required term(s): flour")
        if not product.has_all("self", "rising"):
            return reject(f"{esha_code} missing required term(s): self|rising")
        excluded = [term for term in SELF_RISING_FLOUR_EXCLUDES if product.has_any(term)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        ingredient_excluded = [term for term in SELF_RISING_FLOUR_INGREDIENT_EXCLUDES if product.ingredients_have_any(term)]
        if ingredient_excluded:
            return reject(f"{esha_code} excluded ingredient term(s): " + "|".join(ingredient_excluded))
        return accept(f"{esha_code} reviewed self-rising flour contract accepted")

    return contract


CONTRACTS: dict[str, ContractFn] = {
    "21134": make_plain_water_contract("21134", "Water, tap"),
    "24340": make_plain_milk_contract("24340", "Milk"),
    "3068": make_lemon_juice_contract("3068", "Juice, lemon, fresh"),
    "28003": make_baking_soda_contract("28003", "Baking Soda"),
    "28073": make_baking_powder_contract("28073", "Baking Powder, double acting"),
    "34714": make_plain_salt_contract("34714", "Salt"),
    "38033": make_self_rising_flour_contract("38033", "Flour, all purpose, self rising, white, enriched"),
    "45984": make_all_purpose_flour_contract("45984", "Flour, all purpose, unbleached"),
    "53002": make_soy_sauce_contract("53002", "Sauce, soy, from soy & wheat"),
}
