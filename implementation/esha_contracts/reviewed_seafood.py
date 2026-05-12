from __future__ import annotations

from .contract_base import ContractFn, MatchDecision, ProductFacts, accept, reject


SEAFOOD_CATEGORIES = (
    "fish",
    "seafood",
    "shellfish",
)

CRAWFISH_TAIL_REJECT_TERMS = (
    "base",
    "bisque",
    "boil",
    "boudin",
    "bread",
    "casserole",
    "crab",
    "dip",
    "dinner",
    "etouffee",
    "gumbo",
    "jambalaya",
    "mix",
    "monica",
    "pasta",
    "pie",
    "pork",
    "rice",
    "rotini",
    "sauce",
    "sausage",
    "seasoning",
    "shrimp",
    "soup",
    "stock",
    "stuffed",
    "whl",
)

CRAWFISH_TAIL_INGREDIENT_REJECT_TERMS = (
    "crab",
    "pasta",
    "pork",
    "rice",
    "sausage",
    "shrimp",
)

CRAWFISH_TAIL_REJECT_PHRASES = (
    "whole boiled",
    "whole cooked",
    "whl boiled",
)


def make_crawfish_tail_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*SEAFOOD_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        has_crawfish = product.has_any("crawfish", "crayfish") or product.ingredients_have_any("crawfish", "crayfish")
        if not has_crawfish:
            return reject(f"{esha_code} missing required term(s): crawfish")
        has_tail_meat = (
            product.has_any("tail", "tails", "tailmeat", "meat")
            or product.has_phrase("tail meat")
            or product.ingredients_have_any("tail", "tails", "tailmeat", "meat")
            or product.ingredients_have_phrase("tail meat")
        )
        if not has_tail_meat:
            return reject(f"{esha_code} missing required term(s): tail|meat")
        excluded = [term for term in CRAWFISH_TAIL_REJECT_TERMS if product.has_any(term)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        excluded_phrases = [phrase for phrase in CRAWFISH_TAIL_REJECT_PHRASES if product.has_phrase(phrase)]
        if excluded_phrases:
            return reject(f"{esha_code} excluded phrase(s): " + "|".join(excluded_phrases))
        ingredient_excluded = [
            term for term in CRAWFISH_TAIL_INGREDIENT_REJECT_TERMS
            if product.ingredients_have_any(term)
        ]
        if ingredient_excluded:
            return reject(f"{esha_code} excluded ingredient term(s): " + "|".join(ingredient_excluded))
        return accept(f"{esha_code} reviewed crawfish tail contract accepted")

    return contract


CONTRACTS: dict[str, ContractFn] = {
    "24190": make_crawfish_tail_contract("24190", "Crawfish, wild, mixed species, steamed"),
}
