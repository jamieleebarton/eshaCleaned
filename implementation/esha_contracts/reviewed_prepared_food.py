from __future__ import annotations

from .contract_base import ContractFn, MatchDecision, ProductFacts, accept, reject


GREEN_BEAN_CASSEROLE_CATEGORIES = (
    "deli",
    "prepared",
    "processed",
    "meal",
    "side",
    "frozen",
    "canned",
    "vegetable",
    "vegetables",
)

GREEN_BEAN_CASSEROLE_EXCLUDES = (
    "whole",
    "plain",
    "snap",
    "string",
    "wax",
    "almondine",
)


def make_green_bean_casserole_contract(esha_code: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*GREEN_BEAN_CASSEROLE_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        missing = [term for term in ("green", "bean", "casserole") if not product.has_any(term)]
        if missing:
            return reject(f"{esha_code} missing required term(s): " + "|".join(missing))
        excluded = [term for term in GREEN_BEAN_CASSEROLE_EXCLUDES if product.has_any(term)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed green bean casserole contract accepted")

    return contract


CONTRACTS = {
    "1135": make_green_bean_casserole_contract("1135"),
}
