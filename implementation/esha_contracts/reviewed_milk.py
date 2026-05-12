from __future__ import annotations

from .contract_base import ContractFn, MatchDecision, ProductFacts, accept, reject


MILK_CATEGORY_TERMS = (
    "milk",
    "dairy",
    "beverage",
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
    "chocolate",
    "cocoa",
    "strawberry",
    "vanilla",
    "banana",
    "coffee",
    "mocha",
    "caramel",
    "flavored",
    "flavor",
    "malted",
    "shake",
    "smoothie",
    "protein",
)

OTHER_DAIRY_TERMS = (
    "yogurt",
    "yoghurt",
    "cheese",
    "butter",
    "kefir",
)

LOWER_FAT_PHRASES = (
    "2 percent",
    "1 percent",
    "0 percent",
    "reduced fat",
    "low fat",
    "fat free",
    "non fat",
    "nonfat",
    "skim",
    "lowfat",
)


def category_ok(product: ProductFacts) -> bool:
    return product.category_has_any(*MILK_CATEGORY_TERMS)


def has_milk_cue(product: ProductFacts) -> bool:
    return product.has_any("milk") or product.has_phrase("vitamin d milk")


def whole_milk_cue(product: ProductFacts) -> bool:
    return product.has_any("whole") or product.has_phrase("3.25 percent") or product.has_phrase("vitamin d milk")


def reject_plain_milk_conflicts(product: ProductFacts, esha_code: str, allow_flavors: tuple[str, ...] = ()) -> MatchDecision | None:
    allowed_flavors = set(allow_flavors)
    if not category_ok(product):
        return reject(f"{esha_code} category mismatch")
    if not has_milk_cue(product):
        return reject(f"{esha_code} missing milk cue")
    plant_hits = [term for term in PLANT_MILK_TERMS if product.has_any(term)]
    if plant_hits:
        return reject(f"{esha_code} plant milk term(s): " + "|".join(plant_hits))
    dairy_hits = [term for term in OTHER_DAIRY_TERMS if product.has_any(term)]
    if dairy_hits or product.has_phrase("ice cream"):
        if product.has_phrase("ice cream"):
            dairy_hits.append("ice cream")
        return reject(f"{esha_code} other dairy term(s): " + "|".join(sorted(set(dairy_hits))))
    lower_fat_hits = [phrase for phrase in LOWER_FAT_PHRASES if product.has_phrase(phrase)]
    if lower_fat_hits:
        return reject(f"{esha_code} lower-fat cue(s): " + "|".join(lower_fat_hits))
    flavor_hits = [term for term in FLAVORED_MILK_TERMS if term not in allowed_flavors and product.has_any(term)]
    if flavor_hits:
        return reject(f"{esha_code} flavored milk term(s): " + "|".join(flavor_hits))
    return None


def make_plain_whole_milk_contract(esha_code: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        conflict = reject_plain_milk_conflicts(product, esha_code)
        if conflict:
            return conflict
        if not whole_milk_cue(product):
            return reject(f"{esha_code} missing whole-milk cue")
        return accept(f"{esha_code} reviewed plain whole milk contract accepted")

    return contract


def make_whole_chocolate_milk_contract(esha_code: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        conflict = reject_plain_milk_conflicts(product, esha_code, allow_flavors=("chocolate", "cocoa"))
        if conflict:
            return conflict
        if not product.has_any("chocolate", "cocoa"):
            return reject(f"{esha_code} missing chocolate cue")
        if not whole_milk_cue(product):
            return reject(f"{esha_code} missing whole-milk cue")
        return accept(f"{esha_code} reviewed whole chocolate milk contract accepted")

    return contract


CONTRACTS: dict[str, ContractFn] = {
    "1": make_plain_whole_milk_contract("1"),
    "55041": make_whole_chocolate_milk_contract("55041"),
}
