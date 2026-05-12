from __future__ import annotations

from .contract_base import ContractFn, MatchDecision, ProductFacts, accept, reject


SWEETENER_CATEGORIES = (
    "sugar",
    "sweetener",
    "baking",
    "granulated",
)

GRANULATED_SUGAR_EXCLUDES = (
    "brown",
    "powdered",
    "confectioner",
    "confectioners",
    "icing",
    "turbinado",
    "raw",
    "demerara",
    "muscovado",
    "coconut",
    "maple",
    "stevia",
    "sucralose",
    "substitute",
    "sweetener",
    "syrup",
    "cube",
    "cubes",
    "beet",
)


def _plain_granulated_sugar(product: ProductFacts, esha_code: str, esha_description: str) -> MatchDecision:
    if not product.category_has_any(*SWEETENER_CATEGORIES):
        return reject(f"{esha_code} category mismatch")
    excluded = [term for term in GRANULATED_SUGAR_EXCLUDES if term in product.description_tokens]
    if excluded:
        return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
    if product.has_phrase("granulated sugar") or product.has_all("granulated", "sugar"):
        return accept(f"{esha_code} reviewed contract accepted")
    if product.has_phrase("cane sugar"):
        return accept(f"{esha_code} reviewed contract accepted")
    if "sugar" in product.description_tokens and product.category_has_any("granulated", "sugar"):
        return accept(f"{esha_code} reviewed contract accepted")
    return reject(f"{esha_code} missing granulated sugar identity")


def make_plain_granulated_sugar_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        return _plain_granulated_sugar(product, esha_code, esha_description)

    return contract


CONTRACTS = {
    "25006": make_plain_granulated_sugar_contract("25006", "Sugar, white, granulated"),
}
