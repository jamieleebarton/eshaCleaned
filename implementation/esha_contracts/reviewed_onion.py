from __future__ import annotations

from .contract_base import ContractFn, MatchDecision, ProductFacts, accept, reject


FRENCH_FRIED_ONION_CATEGORIES = (
    "salad dressing",
    "mayonnaise",
    "herb",
    "spice",
    "seasoning",
    "marinade",
    "tenderizer",
    "snack",
    "french fries",
)

FRENCH_FRIED_ONION_STYLE_TERMS = (
    "french",
    "crispy",
    "original",
    "gourmet",
    "golden",
    "premium",
    "bits",
    "pieces",
    "organic",
)

FRENCH_FRIED_ONION_EXCLUDES = (
    "ring",
    "rings",
    "potato",
    "potatoes",
    "crisp",
    "crisps",
    "chip",
    "chips",
    "perogie",
    "perogies",
    "rice",
    "sushi",
    "casserole",
    "green",
    "bean",
    "beans",
    "pepper",
    "peppers",
    "soup",
    "dip",
    "base",
    "broth",
    "cheese",
    "cracker",
    "sandwich",
    "pizza",
    "bowl",
    "noodle",
    "noodles",
    "steak",
    "shrimp",
    "chicken",
    "beef",
    "cabbage",
)


def make_french_fried_onion_contract(esha_code: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*FRENCH_FRIED_ONION_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        missing = [term for term in ("onion", "fried") if not product.has_any(term)]
        if missing:
            return reject(f"{esha_code} missing required term(s): " + "|".join(missing))
        excluded = [term for term in FRENCH_FRIED_ONION_EXCLUDES if product.has_any(term)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        if not product.has_any(*FRENCH_FRIED_ONION_STYLE_TERMS):
            return reject(f"{esha_code} missing french-fried/crispy topping style")
        return accept(f"{esha_code} reviewed french fried onion topping contract accepted")

    return contract


CONTRACTS = {
    "90949": make_french_fried_onion_contract("90949"),
}
