from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
DEFAULT_INPUT = OUT_DIR / "product_to_best_esha_full_map.vSelf.fixyClusterFixed.csv"
DEFAULT_ESHA_SPINE = OUT_DIR / "esha_spine.csv"
DEFAULT_OUTPUT = OUT_DIR / "AUDIT_ME_wrong_assignments.csv"
DEFAULT_FULL_OUTPUT = OUT_DIR / "AUDIT_ME_FULL_product_to_best_esha_full_map.vSelf.wrongAssignmentAudit.csv"
DEFAULT_PAIR_OUTPUT = OUT_DIR / "AUDIT_ME_fixy_esha_pair_collisions.csv"
DEFAULT_SUMMARY = OUT_DIR / "AUDIT_ME_wrong_assignment_summary.json"


def _norm_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Concept:
    name: str
    group: str
    macro: str
    aliases: tuple[str, ...]
    preferred_esha: str = ""


CONCEPTS: tuple[Concept, ...] = (
    Concept("sauerkraut", "pickled_vegetable", "condiment", ("sauerkraut", "sauer kraut", "kraut"), "36986"),
    Concept("pickle", "pickled_vegetable", "condiment", ("dill pickle", "sour pickle", "sweet pickle", "pickle", "pickles", "gherkin")),
    Concept("relish", "pickled_vegetable", "condiment", ("relish",)),
    Concept("horseradish", "sauce_condiment", "condiment", ("horseradish sauce", "cream horseradish", "horseradish"), "53406"),
    Concept("mustard", "sauce_condiment", "condiment", ("mustard",), "35682"),
    Concept("ketchup", "sauce_condiment", "condiment", ("ketchup",)),
    Concept("bbq sauce", "sauce_condiment", "condiment", ("barbecue sauce", "bbq sauce")),
    Concept("hot sauce", "sauce_condiment", "condiment", ("hot sauce", "hotsauce")),
    Concept("pasta sauce", "sauce_condiment", "condiment", ("pasta sauce", "marinara")),
    Concept("tomato sauce", "sauce_condiment", "condiment", ("tomato sauce",)),
    Concept("salad dressing", "sauce_condiment", "condiment", ("salad dressing", "dressing"), "8046"),
    Concept("mayonnaise", "sauce_condiment", "condiment", ("mayonnaise", "mayo"), "8046"),
    Concept("jam", "fruit_spread", "condiment", ("jam",)),
    Concept("jelly", "fruit_spread", "condiment", ("jelly",)),
    Concept("preserves", "fruit_spread", "condiment", ("preserves", "fruit spread")),
    Concept("creamer", "cream_or_milk", "dairy_milk", ("coffee creamer", "cream substitute", "non dairy creamer", "nondairy creamer", "creamer"), "14669"),
    Concept("almond milk", "cream_or_milk", "dairy_milk", ("almond milk", "almondmilk", "almond beverage", "almond drink"), "14480"),
    Concept("soy milk", "cream_or_milk", "dairy_milk", ("soy milk", "soymilk", "soy beverage", "soy drink"), "21048"),
    Concept("rice milk", "cream_or_milk", "dairy_milk", ("rice milk", "ricemilk", "rice drink"), "20440"),
    Concept("oat milk", "cream_or_milk", "dairy_milk", ("oat milk", "oatmilk", "oat drink", "oat beverage"), "15536"),
    Concept("coconut milk", "cream_or_milk", "dairy_milk", ("coconut milk", "coconutmilk", "coconut drink", "coconut beverage")),
    Concept("cashew milk", "cream_or_milk", "dairy_milk", ("cashew milk", "cashewmilk", "cashew drink")),
    Concept("pea milk", "cream_or_milk", "dairy_milk", ("pea milk", "peamilk")),
    Concept("hemp milk", "cream_or_milk", "dairy_milk", ("hemp milk", "hempmilk")),
    Concept("macadamia milk", "cream_or_milk", "dairy_milk", ("macadamia milk", "macadamiamilk")),
    Concept("pistachio milk", "cream_or_milk", "dairy_milk", ("pistachio milk", "pistachiomilk")),
    Concept("whole milk", "cream_or_milk", "dairy_milk", ("whole milk", "vitamin d milk"), "222"),
    Concept("skim milk", "cream_or_milk", "dairy_milk", ("skim milk", "nonfat milk", "fat free milk"), "208"),
    Concept("lowfat milk", "cream_or_milk", "dairy_milk", ("lowfat milk", "low fat milk", "1% milk", "2% milk")),
    Concept("evaporated milk", "cream_or_milk", "dairy_milk", ("evaporated milk",), "20952"),
    Concept("condensed milk", "cream_or_milk", "dairy_milk", ("condensed milk", "sweetened condensed milk")),
    Concept("buttermilk", "cream_or_milk", "dairy_milk", ("buttermilk", "butter milk")),
    Concept("kefir", "cream_or_milk", "dairy_milk", ("kefir",)),
    Concept("egg nog", "cream_or_milk", "dairy_milk", ("egg nog", "eggnog", "holiday nog")),
    Concept("dry milk", "cream_or_milk", "dairy_milk", ("dry milk", "milk powder", "powdered milk")),
    Concept("milk shake", "cream_or_milk", "dairy_milk", ("milk shake", "milkshake")),
    Concept("chocolate milk", "cream_or_milk", "dairy_milk", ("chocolate milk drink", "chocolate milk")),
    Concept("coffee", "beverage", "beverage", ("cold brew coffee", "iced coffee", "coffee latte", "latte", "cold brew", "espresso", "coffee")),
    Concept("mocha latte", "beverage", "beverage", ("mocha latte", "caffe mocha", "coffee mocha", "mocha")),
    Concept("chai tea", "beverage", "beverage", ("chai tea", "chai")),
    Concept("protein shake", "beverage", "beverage", ("protein shake mix", "protein shake", "meal replacement shake")),
    Concept("seltzer", "beverage", "beverage", ("sparkling water", "seltzer water", "seltzer", "carbonated water", "flavored water")),
    Concept("dry drink mix", "beverage", "beverage", ("drink mix", "powdered drink", "dry mix")),
    Concept("hot cocoa", "beverage", "beverage", ("hot cocoa", "cocoa mix", "hot chocolate")),
    Concept("juice drink", "beverage", "beverage", ("juice drink", "juice cocktail", "fruit drink")),
    Concept("kombucha", "beverage", "beverage", ("kombucha", "jun kombucha", "jun-kombucha")),
    Concept("shrimp", "seafood", "seafood", ("shrimp", "shrimps"), "19141"),
    Concept("lobster", "seafood", "seafood", ("lobster", "lob tail", "lob tails"), "19145"),
    Concept("crab", "seafood", "seafood", ("crab", "crabs"), "19144"),
    Concept("scallop", "seafood", "seafood", ("scallop", "scallops")),
    Concept("clam", "seafood", "seafood", ("clam chowder", "clam", "clams"), "17325"),
    Concept("oyster", "seafood", "seafood", ("oyster", "oysters"), "19008"),
    Concept("cod", "seafood", "seafood", ("cod",), "70223"),
    Concept("haddock", "seafood", "seafood", ("haddock",)),
    Concept("flounder", "seafood", "seafood", ("flounder",)),
    Concept("salmon", "seafood", "seafood", ("salmon",)),
    Concept("tuna", "seafood", "seafood", ("tuna",)),
    Concept("tilapia", "seafood", "seafood", ("tilapia",)),
    Concept("fish", "seafood_generic", "seafood", ("fish",)),
    Concept("oyster mushroom", "mushroom", "vegetable", ("oyster mushroom", "oyster mushrooms"), "7948"),
    Concept("mushroom", "mushroom", "vegetable", ("mushroom", "mushrooms")),
    Concept("cream cheese", "cheese", "cheese", ("cream cheese", "creamcheese"), "1015"),
    Concept("feta", "cheese", "cheese", ("feta",), "1016"),
    Concept("goat cheese", "cheese", "cheese", ("goat cheese",)),
    Concept("cheddar", "cheese", "cheese", ("cheddar",)),
    Concept("havarti", "cheese", "cheese", ("havarti",)),
    Concept("ricotta", "cheese", "cheese", ("ricotta",)),
    Concept("swiss cheese", "cheese", "cheese", ("swiss cheese", "swiss")),
    Concept("brownie", "dessert", "dessert_snack", ("brownie", "brownies"), "22113"),
    Concept("ice cream", "dessert", "dessert_snack", ("ice cream", "icecream"), "2004"),
    Concept("gelato", "dessert", "dessert_snack", ("gelato",)),
    Concept("frozen dessert", "dessert", "dessert_snack", ("frozen dessert",)),
    Concept("yogurt", "dessert", "yogurt", ("yogurt", "oatgurt")),
    Concept("smoothie", "dessert", "beverage", ("smoothie",)),
    Concept("cheesecake", "dessert", "dessert_snack", ("cheesecake", "cheese cake")),
    Concept("cake", "dessert", "dessert_snack", ("cupcake", "snack cake", "cake")),
    Concept("doughnut", "bakery", "dessert_snack", ("doughnut", "donut"), "45563"),
    Concept("biscuit", "bakery", "grain", ("biscuit", "biscuits")),
    Concept("cracker", "bakery", "grain", ("cracker", "crackers"), "43785"),
    Concept("crescent roll", "bakery", "grain", ("crescent roll", "crescent rolls")),
    Concept("sweet roll", "bakery", "grain", ("sweet roll", "sweet rolls", "cinnamon roll")),
    Concept("ravioli", "pasta", "grain", ("ravioli",)),
    Concept("tortellini", "pasta", "grain", ("tortellini",)),
    Concept("pasta", "pasta", "grain", ("pasta",)),
    Concept("carrot", "produce", "vegetable", ("baby carrot", "carrots", "carrot")),
    Concept("tomato", "produce", "vegetable", ("tomatoes", "tomato")),
    Concept("okra", "produce", "vegetable", ("okra",)),
    Concept("eggplant", "produce", "vegetable", ("eggplant", "eggplants")),
    Concept("corn", "produce", "vegetable", ("corn",)),
    Concept("fig", "fruit", "fruit", ("figs", "fig")),
    Concept("apple", "apple_product", "fruit", ("granny smith apples", "gala apples", "fuji apples", "apples", "apple")),
    Concept("applesauce", "apple_product", "fruit", ("applesauce regular", "applesauce unsweetened", "applesauce flavored", "applesauce")),
    Concept("apple chips", "apple_product", "fruit", ("apple chips",)),
    Concept("apple juice", "apple_product", "beverage", ("apple juice 100%", "apple juice")),
    Concept("apple butter", "apple_product", "condiment", ("apple butter",)),
    Concept("apple pie filling", "apple_product", "dessert_snack", ("apple pie filling",)),
    Concept("caramel apple", "apple_product", "dessert_snack", ("caramel apples", "caramel apple")),
    Concept("fruit cup", "fruit", "fruit", ("fruit cup",)),
    Concept("cranberry", "fruit", "fruit", ("cranberries", "cranberry"), "41953"),
    Concept("blueberry", "fruit", "fruit", ("blueberries", "blueberry")),
    Concept("grapefruit", "fruit", "fruit", ("grapefruit",)),
    Concept("kidney beans", "bean", "vegetable", ("kidney beans", "kidney bean"), "7173"),
    Concept("bean salad", "bean", "vegetable", ("three bean salad", "3 bean salad", "bean salad")),
    Concept("trail mix", "snack", "dessert_snack", ("trail mix",)),
    Concept("popcorn", "snack", "dessert_snack", ("popcorn",)),
    Concept("potato chips", "snack", "dessert_snack", ("potato chips", "chips nfs")),
    Concept("pretzel", "snack", "dessert_snack", ("pretzels hard", "pretzel", "pretzels")),
    Concept("water enhancer", "beverage", "beverage", ("water enhancer",)),
    Concept("cocktail mixer", "beverage", "beverage", ("cocktail mixer", "martini flavored")),
    Concept("cereal", "grain", "grain", ("cereal rte", "cheerios", "cereal")),
    Concept("cereal bar", "snack", "dessert_snack", ("cereal or granola bar", "granola bar")),
    Concept("cookie", "dessert", "dessert_snack", ("cookie",)),
    Concept("waffle", "grain", "grain", ("waffle",)),
    Concept("chia seeds", "nut_seed", "nut_seed", ("chia seeds", "chia seed")),
    Concept("brussels sprouts", "produce", "vegetable", ("brussels sprouts", "brussel sprouts")),
    Concept("taralli", "bakery", "grain", ("taralli",)),
    Concept("bouillon", "seasoning", "condiment", ("bouillon", "stock cube", "broth cube")),
)

CONCEPT_BY_NAME = {concept.name: concept for concept in CONCEPTS}
ALIASES = sorted(
    ((_norm_text(alias), concept) for concept in CONCEPTS for alias in concept.aliases),
    key=lambda item: (-len(item[0]), item[0]),
)
ALIAS_PATTERNS = tuple(
    (alias, concept)
    for alias, concept in ALIASES
)
GENERIC_CONCEPTS = {"fish", "cake", "pasta", "mushroom"}
WEAK_CURRENT_PARENTS = {"vegetables", "dish", "meal", "sauce", "drink", "juice drink", "water", "salad", "pickles"}
_PREFERRED_CACHE: dict[tuple[int, str], tuple[str, str]] = {}

AUDIT_FIELDS = [
    "wrong_assignment_flag",
    "mismatch_bucket",
    "severity",
    "confidence",
    "recommended_action",
    "evidence_reason",
    "candidate_esha_code",
    "candidate_esha_description",
    "new_leaf_label",
    "product_identity",
    "ingredient_identity",
    "fixy_identity",
    "current_esha_identity",
    "missing_terms_from_current_esha",
    "conflicting_terms_in_current_esha",
]

OUT_FIELDS = [
    *AUDIT_FIELDS,
    "fdc_id",
    "gtin_upc",
    "product_description",
    "branded_food_category",
    "brand_owner",
    "brand_name",
    "current_esha_code",
    "current_esha_description",
    "current_esha_head",
    "best_esha_code",
    "best_esha_description",
    "best_esha_head",
    "assignment_source",
    "self_heal_status",
    "self_heal_reason",
    "product_cluster_id",
    "category_lane",
    "product_form",
    "primary_food",
    "title_identity_terms",
    "ingredient_core_terms",
    "fixy_fndds_code",
    "fixy_fndds_description",
    "fndds_main_code",
    "fndds_main_description",
    "wweia_category_code",
    "wweia_category_description",
    "fixy_product_description",
    "fixy_category",
    "fixy_match_source",
    "candidate_mode",
    "candidate_reason",
    "surface_alignment_ok",
    "surface_missing_terms",
    "product_vs_cluster_dominant",
    "top_current_esha_codes",
    "top_current_esha_descriptions",
    "top_product_forms",
    "top_categories",
    "top_title_terms",
    "top_ingredient_terms",
    "sample_products",
    "fixy_cluster_fix_action",
    "fixy_cluster_fix_reason",
]

PAIR_FIELDS = [
    "fixy_pair_collision_flag",
    "row_count",
    "sample_fdc_ids",
    "sample_products",
    "mismatch_bucket",
    "severity",
    "confidence",
    "recommended_action",
    "evidence_reason",
    "candidate_esha_code",
    "candidate_esha_description",
    "fixy_identity",
    "current_esha_identity",
    "missing_terms_from_current_esha",
    "conflicting_terms_in_current_esha",
    "best_esha_code",
    "best_esha_description",
    "best_esha_head",
    "fixy_fndds_code",
    "fixy_fndds_description",
    "fndds_main_code",
    "fndds_main_description",
    "wweia_category_code",
    "wweia_category_description",
    "top_categories",
]


def norm(value: object) -> str:
    return _norm_text(value)


def has_phrase(text: str, phrase: str) -> bool:
    phrase = norm(phrase)
    if not phrase:
        return False
    return f" {phrase} " in f" {text} "


@lru_cache(maxsize=500_000)
def _concept_names_for_normalized(value: str) -> frozenset[str]:
    found: set[str] = set()
    padded = f" {value} "
    for alias, concept in ALIAS_PATTERNS:
        if f" {alias} " in padded:
            found.add(concept.name)
    if "oyster mushroom" in found:
        found.discard("oyster")
    if "creamer" in found:
        found.discard("coffee")
    if "cream cheese" in found:
        found.discard("cake")
    return frozenset(found)


def concept_names(text: str) -> set[str]:
    return set(_concept_names_for_normalized(norm(text)))


def names_text(names: set[str]) -> str:
    return "|".join(sorted(names))


def surface_text(row: dict[str, str], fields: tuple[str, ...]) -> str:
    return " ".join(str(row.get(field, "") or "") for field in fields)


def product_concepts(row: dict[str, str]) -> set[str]:
    return concept_names(
        surface_text(
            row,
            (
                "product_description",
            ),
        )
    )


def ingredient_concepts(row: dict[str, str]) -> set[str]:
    return concept_names(row.get("ingredient_core_terms", ""))


def fixy_concepts(row: dict[str, str]) -> set[str]:
    return concept_names(surface_text(row, ("fixy_fndds_description", "fndds_main_description")))


def current_concepts(row: dict[str, str]) -> set[str]:
    return concept_names(surface_text(row, ("best_esha_head", "best_esha_description")))


def current_text(row: dict[str, str]) -> str:
    return norm(surface_text(row, ("best_esha_head", "best_esha_description")))


def fixy_text(row: dict[str, str]) -> str:
    return norm(surface_text(row, ("fixy_fndds_description", "fndds_main_description")))


def product_text(row: dict[str, str]) -> str:
    return norm(surface_text(row, ("product_description", "product_form", "primary_food", "title_identity_terms")))


def assigned(row: dict[str, str]) -> bool:
    return bool(str(row.get("best_esha_code", "") or "").strip())


def concept_macro(name: str) -> str:
    return CONCEPT_BY_NAME[name].macro


def concept_group(name: str) -> str:
    return CONCEPT_BY_NAME[name].group


def macro_from_text(text: str) -> str:
    concepts = concept_names(text)
    macros = Counter(concept_macro(name) for name in concepts)
    if macros:
        return macros.most_common(1)[0][0]
    value = norm(text)
    if any(term in value for term in ("vegetable", "pickles", "relish", "sauce", "condiment", "dressing")):
        return "condiment" if any(term in value for term in ("pickle", "relish", "sauce", "dressing")) else "vegetable"
    if any(term in value for term in ("drink", "beverage", "water", "juice", "coffee", "tea")):
        return "beverage"
    if any(term in value for term in ("fish", "seafood", "shellfish")):
        return "seafood"
    if "cheese" in value:
        return "cheese"
    if "milk" in value or "cream" in value:
        return "dairy_milk"
    return ""


def current_macro(row: dict[str, str], current: set[str]) -> str:
    if current:
        macros = Counter(concept_macro(name) for name in current)
        return macros.most_common(1)[0][0]
    return macro_from_text(surface_text(row, ("best_esha_head", "best_esha_description", "best_esha_family")))


def product_macro(row: dict[str, str], evidence: set[str], fixy: set[str]) -> str:
    if evidence:
        macros = Counter(concept_macro(name) for name in evidence)
        return macros.most_common(1)[0][0]
    if fixy:
        macros = Counter(concept_macro(name) for name in fixy)
        return macros.most_common(1)[0][0]
    return macro_from_text(surface_text(row, ("product_description", "branded_food_category", "product_form", "primary_food")))


def evidence_concepts(product: set[str], fixy: set[str]) -> set[str]:
    if product and fixy:
        overlap = product & fixy
        if overlap:
            return set(overlap)
        return set(product)
    return set(product or fixy)


CORE_STOPWORDS = {
    "a",
    "all",
    "and",
    "as",
    "beverage",
    "code",
    "fl",
    "flavor",
    "flavored",
    "food",
    "fresh",
    "from",
    "made",
    "nfs",
    "no",
    "ns",
    "original",
    "oz",
    "plain",
    "regular",
    "sweetened",
    "unsweetened",
    "vanilla",
    "with",
}


def core_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in norm(text).split():
        if len(token) < 3 or token in CORE_STOPWORDS:
            continue
        if token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"
        elif token.endswith("s") and len(token) > 4:
            token = token[:-1]
        tokens.add(token)
    return tokens


def pair_text_overlap_ok(row: dict[str, str]) -> bool:
    current_tokens = core_tokens(surface_text(row, ("best_esha_head", "best_esha_description")))
    fixy_tokens = core_tokens(surface_text(row, ("fixy_fndds_description", "fndds_main_description")))
    return bool(current_tokens & fixy_tokens)


def preferred_candidate(concept: str, esha: dict[str, str]) -> tuple[str, str]:
    cache_key = (id(esha), concept)
    if cache_key in _PREFERRED_CACHE:
        return _PREFERRED_CACHE[cache_key]
    preferred = CONCEPT_BY_NAME[concept].preferred_esha
    if preferred and preferred in esha:
        _PREFERRED_CACHE[cache_key] = (preferred, esha[preferred])
        return _PREFERRED_CACHE[cache_key]
    normalized = norm(concept)
    matches = [
        (code, desc)
        for code, desc in esha.items()
        if has_phrase(norm(desc), normalized)
    ]
    if not matches:
        _PREFERRED_CACHE[cache_key] = ("", "")
        return _PREFERRED_CACHE[cache_key]
    matches.sort(key=lambda item: (0 if norm(item[1]).startswith(normalized) else 1, len(item[1]), item[0]))
    _PREFERRED_CACHE[cache_key] = matches[0]
    return _PREFERRED_CACHE[cache_key]


def shared_group_conflicts(product: set[str], current: set[str]) -> list[tuple[str, str]]:
    conflicts: list[tuple[str, str]] = []
    for p_name in sorted(product):
        p_group = concept_group(p_name)
        if p_name in current:
            continue
        for c_name in sorted(current):
            if concept_group(c_name) == p_group and c_name != p_name:
                if c_name in GENERIC_CONCEPTS and p_name not in GENERIC_CONCEPTS:
                    conflicts.append((p_name, c_name))
                elif p_name not in GENERIC_CONCEPTS:
                    conflicts.append((p_name, c_name))
    return conflicts


def missing_product_terms(product: set[str], current: set[str]) -> set[str]:
    return {name for name in product if name not in current and name not in GENERIC_CONCEPTS}


def component_flavor_conflict(product: set[str], current: set[str]) -> tuple[str, str]:
    if "coffee" in product and any(name.endswith(" milk") for name in current):
        return "coffee", next(name for name in current if name.endswith(" milk"))
    if product & {"yogurt", "smoothie"} and current & {"cake", "cheesecake"}:
        return sorted(product & {"yogurt", "smoothie"})[0], sorted(current & {"cake", "cheesecake"})[0]
    if product & {"ice cream", "gelato", "frozen dessert"} and current & {"brownie", "cake", "cheesecake"}:
        return sorted(product & {"ice cream", "gelato", "frozen dessert"})[0], sorted(current & {"brownie", "cake", "cheesecake"})[0]
    return "", ""


def form_conflict(product: set[str], current: set[str]) -> tuple[str, str]:
    if product & {"seltzer"} and current & {"dry drink mix", "juice drink"}:
        return "seltzer", sorted(current & {"dry drink mix", "juice drink"})[0]
    if product & {"hot cocoa"} and current & {"juice drink"}:
        return "hot cocoa", "juice drink"
    if product & {"creamer"} and current & {"almond milk", "soy milk", "rice milk", "oat milk", "coconut milk"}:
        return "creamer", sorted(current & {"almond milk", "soy milk", "rice milk", "oat milk", "coconut milk"})[0]
    if product & {"whole milk", "skim milk", "lowfat milk"} and current & {"evaporated milk", "condensed milk", "dry milk", "buttermilk"}:
        return sorted(product & {"whole milk", "skim milk", "lowfat milk"})[0], sorted(current & {"evaporated milk", "condensed milk", "dry milk", "buttermilk"})[0]
    return "", ""


def classify_fixy_pair_collision(
    row: dict[str, str],
    *,
    product: set[str],
    ingredient: set[str],
    fixy: set[str],
    current: set[str],
    esha: dict[str, str],
) -> dict[str, str] | None:
    if not assigned(row):
        return None
    if not str(row.get("fixy_fndds_code", "") or "").strip():
        return None
    if not str(row.get("fixy_fndds_description", "") or "").strip():
        return None

    fixy_value = fixy_text(row)
    current_value = current_text(row)
    if not fixy_value or not current_value:
        return None

    group_conflicts = shared_group_conflicts(fixy, current)
    if group_conflicts:
        f_name, c_name = group_conflicts[0]
        return row_output(
            row,
            bucket="fixy_pair_same_group_conflict",
            severity=99,
            confidence=0.98,
            action="remap_existing_leaf",
            reason=f"fixy_identity={f_name};current_esha_identity={c_name}",
            product=product,
            ingredient=ingredient,
            fixy=fixy,
            current=current,
            missing={f_name},
            conflicting={c_name},
            esha=esha,
        )

    missing = missing_product_terms(fixy, current)
    f_macro = ""
    c_macro = ""
    if fixy:
        f_macro = Counter(concept_macro(name) for name in fixy).most_common(1)[0][0]
    else:
        f_macro = macro_from_text(fixy_value)
    if current:
        c_macro = Counter(concept_macro(name) for name in current).most_common(1)[0][0]
    else:
        c_macro = macro_from_text(current_value)

    if f_macro and c_macro and f_macro != c_macro:
        return row_output(
            row,
            bucket="fixy_pair_cross_macro_conflict",
            severity=99,
            confidence=0.96,
            action="remap_existing_leaf",
            reason=f"fixy_macro={f_macro};current_macro={c_macro}",
            product=product,
            ingredient=ingredient,
            fixy=fixy,
            current=current,
            missing=missing or fixy,
            conflicting=current,
            esha=esha,
        )

    if missing and not pair_text_overlap_ok(row):
        return row_output(
            row,
            bucket="fixy_pair_identity_missing_from_current",
            severity=97,
            confidence=0.93,
            action="remap_existing_leaf",
            reason=f"fixy_identity_missing_from_current={names_text(missing)}",
            product=product,
            ingredient=ingredient,
            fixy=fixy,
            current=current,
            missing=missing,
            conflicting=current,
            esha=esha,
        )

    if not fixy and not current and not pair_text_overlap_ok(row):
        return row_output(
            row,
            bucket="fixy_pair_no_text_overlap",
            severity=90,
            confidence=0.84,
            action="quarantine_review",
            reason="fixy_and_current_descriptions_have_no_core_token_overlap",
            product=product,
            ingredient=ingredient,
            fixy=fixy,
            current=current,
            missing=set(),
            conflicting=set(),
            esha=esha,
        )

    return None


def row_output(
    row: dict[str, str],
    *,
    bucket: str,
    severity: int,
    confidence: float,
    action: str,
    reason: str,
    product: set[str],
    ingredient: set[str],
    fixy: set[str],
    current: set[str],
    missing: set[str],
    conflicting: set[str],
    esha: dict[str, str],
) -> dict[str, str]:
    candidate_code = ""
    candidate_desc = ""
    new_leaf_label = ""
    for name in sorted(missing or product or fixy):
        candidate_code, candidate_desc = preferred_candidate(name, esha)
        if candidate_code:
            break
    if action == "needs_new_esha_leaf":
        new_leaf_label = sorted(missing or product or fixy)[0] if (missing or product or fixy) else ""
    out = {
        "wrong_assignment_flag": "TRUE",
        "mismatch_bucket": bucket,
        "severity": str(severity),
        "confidence": f"{confidence:.2f}",
        "recommended_action": action,
        "evidence_reason": reason,
        "candidate_esha_code": candidate_code,
        "candidate_esha_description": candidate_desc,
        "new_leaf_label": new_leaf_label,
        "product_identity": names_text(product),
        "ingredient_identity": names_text(ingredient),
        "fixy_identity": names_text(fixy),
        "current_esha_identity": names_text(current),
        "missing_terms_from_current_esha": names_text(missing),
        "conflicting_terms_in_current_esha": names_text(conflicting),
        "current_esha_code": row.get("best_esha_code", ""),
        "current_esha_description": row.get("best_esha_description", ""),
        "current_esha_head": row.get("best_esha_head", ""),
    }
    for field in OUT_FIELDS:
        out.setdefault(field, row.get(field, ""))
    return out


def classify_row(row: dict[str, str], esha: dict[str, str]) -> dict[str, str] | None:
    product = product_concepts(row)
    ingredient = ingredient_concepts(row)
    fixy = fixy_concepts(row)
    current = current_concepts(row)
    product_or_fixy = evidence_concepts(product, fixy)

    pair_collision = classify_fixy_pair_collision(
        row,
        product=product,
        ingredient=ingredient,
        fixy=fixy,
        current=current,
        esha=esha,
    )
    if pair_collision:
        return pair_collision

    if not product_or_fixy and not fixy:
        return None

    component_left, component_right = component_flavor_conflict(product_or_fixy, current)
    if component_left and assigned(row):
        return row_output(
            row,
            bucket="component_flavor_conflict",
            severity=92,
            confidence=0.92,
            action="quarantine_review",
            reason=f"product_is_{component_left};current_esha_is_{component_right}",
            product=product,
            ingredient=ingredient,
            fixy=fixy,
            current=current,
            missing={component_left},
            conflicting={component_right},
            esha=esha,
        )

    form_left, form_right = form_conflict(product_or_fixy, current)
    if form_left and assigned(row):
        return row_output(
            row,
            bucket="form_conflict",
            severity=94,
            confidence=0.95,
            action="remap_existing_leaf",
            reason=f"product_form={form_left};current_esha_form={form_right}",
            product=product,
            ingredient=ingredient,
            fixy=fixy,
            current=current,
            missing={form_left},
            conflicting={form_right},
            esha=esha,
        )

    group_conflicts = shared_group_conflicts(product_or_fixy, current)
    if group_conflicts and assigned(row):
        p_name, c_name = group_conflicts[0]
        if concept_group(p_name) == "seafood":
            bucket = "species_or_base_conflict"
        elif concept_group(p_name) in {"cream_or_milk", "beverage"}:
            bucket = "form_conflict"
        else:
            bucket = "same_macro_identity_conflict"
        return row_output(
            row,
            bucket=bucket,
            severity=96,
            confidence=0.96 if p_name in product else 0.88,
            action="remap_existing_leaf",
            reason=f"product_identity={p_name};current_esha_identity={c_name}",
            product=product,
            ingredient=ingredient,
            fixy=fixy,
            current=current,
            missing={p_name},
            conflicting={c_name},
            esha=esha,
        )

    if assigned(row):
        p_macro = product_macro(row, product_or_fixy, fixy)
        c_macro = current_macro(row, current)
        if p_macro and c_macro and p_macro != c_macro and not ({p_macro, c_macro} <= {"dairy_milk", "beverage"}):
            missing = missing_product_terms(product_or_fixy, current)
            if missing:
                return row_output(
                    row,
                    bucket="cross_macro_conflict",
                    severity=98,
                    confidence=0.90,
                    action="remap_existing_leaf",
                    reason=f"product_macro={p_macro};current_macro={c_macro}",
                    product=product,
                    ingredient=ingredient,
                    fixy=fixy,
                    current=current,
                    missing=missing,
                    conflicting=current,
                    esha=esha,
                )

        missing = missing_product_terms(product_or_fixy, current)
        current_value = current_text(row)
        if missing and (fixy & missing or product & missing):
            if any(has_phrase(current_value, parent) for parent in WEAK_CURRENT_PARENTS) or row.get("surface_alignment_ok", "").lower() == "false":
                return row_output(
                    row,
                    bucket="identity_missing_from_current",
                    severity=86,
                    confidence=0.86,
                    action="remap_existing_leaf",
                    reason=f"current_esha_missing_identity={names_text(missing)}",
                    product=product,
                    ingredient=ingredient,
                    fixy=fixy,
                    current=current,
                    missing=missing,
                    conflicting=current,
                    esha=esha,
                )

    if not assigned(row):
        supported = product_or_fixy & fixy if product_or_fixy and fixy else product_or_fixy
        if supported:
            action = "remap_existing_leaf"
            for name in sorted(supported):
                code, _ = preferred_candidate(name, esha)
                if code:
                    break
            else:
                action = "needs_new_esha_leaf"
            return row_output(
                row,
                bucket="missing_leaf_confirmed",
                severity=70,
                confidence=0.82,
                action=action,
                reason=f"unassigned_with_identity={names_text(supported)}",
                product=product,
                ingredient=ingredient,
                fixy=fixy,
                current=current,
                missing=supported,
                conflicting=set(),
                esha=esha,
            )

    if row.get("candidate_mode") in {"split_cluster_repair_candidate", "stable_surface_mismatch_candidate"} and row.get("product_vs_cluster_dominant") == "product_differs_from_cluster_dominant":
        missing = missing_product_terms(product_or_fixy, current)
        return row_output(
            row,
            bucket="cluster_impurity",
            severity=74,
            confidence=0.76,
            action="quarantine_review",
            reason="product_assignment_differs_from_cluster_dominant",
            product=product,
            ingredient=ingredient,
            fixy=fixy,
            current=current,
            missing=missing,
            conflicting=current,
            esha=esha,
        )

    return None


def load_esha(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            code = str(row.get("esha_code", "") or "").strip()
            desc = str(row.get("esha_description", "") or "").strip()
            if code and desc:
                out[code] = desc
    return out


def build_audit(input_path: Path, esha_path: Path) -> tuple[list[dict[str, str]], dict[str, object]]:
    esha = load_esha(esha_path)
    rows: list[dict[str, str]] = []
    total = 0
    assigned_count = 0
    with input_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            total += 1
            if assigned(row):
                assigned_count += 1
            out = classify_row(row, esha)
            if out:
                rows.append(out)
    rows.sort(
        key=lambda row: (
            -int(row["severity"] or 0),
            -float(row["confidence"] or 0),
            row["mismatch_bucket"],
            row.get("product_description", ""),
            row.get("fdc_id", ""),
        )
    )
    bucket_counts = Counter(row["mismatch_bucket"] for row in rows)
    action_counts = Counter(row["recommended_action"] for row in rows)
    summary = {
        "input_map": str(input_path),
        "rows_scanned": total,
        "assigned_rows_scanned": assigned_count,
        "wrong_assignment_rows": len(rows),
        "bucket_counts": {key: int(value) for key, value in bucket_counts.most_common()},
        "recommended_action_counts": {key: int(value) for key, value in action_counts.most_common()},
    }
    return rows, summary


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in OUT_FIELDS})


def empty_audit_fields() -> dict[str, str]:
    return {field: "" for field in AUDIT_FIELDS}


def build_outputs(
    input_path: Path,
    esha_path: Path,
    *,
    suspect_path: Path,
    full_path: Path,
    pair_path: Path,
) -> dict[str, object]:
    esha = load_esha(esha_path)
    total = 0
    assigned_count = 0
    suspect_count = 0
    bucket_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    pair_index: dict[tuple[str, str, str, str], dict[str, object]] = {}
    input_fields: list[str]

    full_path.parent.mkdir(parents=True, exist_ok=True)
    suspect_path.parent.mkdir(parents=True, exist_ok=True)
    pair_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open(newline="", encoding="utf-8") as in_handle:
        reader = csv.DictReader(in_handle)
        input_fields = list(reader.fieldnames or [])
        full_fields = AUDIT_FIELDS + [field for field in input_fields if field not in AUDIT_FIELDS]
        with full_path.open("w", newline="", encoding="utf-8") as full_handle, suspect_path.open(
            "w", newline="", encoding="utf-8"
        ) as suspect_handle:
            full_writer = csv.DictWriter(full_handle, fieldnames=full_fields)
            suspect_writer = csv.DictWriter(suspect_handle, fieldnames=OUT_FIELDS)
            full_writer.writeheader()
            suspect_writer.writeheader()

            for row in reader:
                total += 1
                if assigned(row):
                    assigned_count += 1
                audit = classify_row(row, esha)
                pair_key = (
                    str(row.get("best_esha_code", "") or "").strip(),
                    str(row.get("best_esha_description", "") or "").strip(),
                    str(row.get("fixy_fndds_code", "") or "").strip(),
                    str(row.get("fixy_fndds_description", "") or "").strip(),
                )
                if pair_key[0] and pair_key[2] and pair_key[3]:
                    pair = pair_index.setdefault(
                        pair_key,
                        {
                            "fixy_pair_collision_flag": "FALSE",
                            "row_count": 0,
                            "sample_fdc_ids": [],
                            "sample_products": [],
                            "category_counts": Counter(),
                            "audit": {},
                            "best_esha_head": row.get("best_esha_head", ""),
                            "fndds_main_code": row.get("fndds_main_code", ""),
                            "fndds_main_description": row.get("fndds_main_description", ""),
                            "wweia_category_code": row.get("wweia_category_code", ""),
                            "wweia_category_description": row.get("wweia_category_description", ""),
                        },
                    )
                    pair["row_count"] = int(pair["row_count"]) + 1
                    if len(pair["sample_fdc_ids"]) < 8 and row.get("fdc_id"):
                        pair["sample_fdc_ids"].append(row.get("fdc_id", ""))
                    if len(pair["sample_products"]) < 5 and row.get("product_description"):
                        pair["sample_products"].append(row.get("product_description", ""))
                    if row.get("branded_food_category"):
                        pair["category_counts"][row.get("branded_food_category", "")] += 1
                    if audit and audit.get("mismatch_bucket", "").startswith("fixy_pair_"):
                        pair["fixy_pair_collision_flag"] = "TRUE"
                        if not pair["audit"]:
                            pair["audit"] = audit
                if audit:
                    suspect_count += 1
                    bucket_counts[audit["mismatch_bucket"]] += 1
                    action_counts[audit["recommended_action"]] += 1
                    full_row = {**row, **{field: audit.get(field, "") for field in AUDIT_FIELDS}}
                    suspect_writer.writerow({field: audit.get(field, "") for field in OUT_FIELDS})
                else:
                    full_row = {**row, **empty_audit_fields(), "wrong_assignment_flag": "FALSE"}
                full_writer.writerow({field: full_row.get(field, "") for field in full_fields})

    pair_rows: list[dict[str, str]] = []
    for (best_code, best_desc, fixy_code, fixy_desc), pair in pair_index.items():
        audit = dict(pair.get("audit") or {})
        category_counts = pair["category_counts"]
        pair_rows.append(
            {
                "fixy_pair_collision_flag": str(pair["fixy_pair_collision_flag"]),
                "row_count": str(pair["row_count"]),
                "sample_fdc_ids": " | ".join(pair["sample_fdc_ids"]),
                "sample_products": " || ".join(pair["sample_products"]),
                "mismatch_bucket": audit.get("mismatch_bucket", ""),
                "severity": audit.get("severity", ""),
                "confidence": audit.get("confidence", ""),
                "recommended_action": audit.get("recommended_action", ""),
                "evidence_reason": audit.get("evidence_reason", ""),
                "candidate_esha_code": audit.get("candidate_esha_code", ""),
                "candidate_esha_description": audit.get("candidate_esha_description", ""),
                "fixy_identity": audit.get("fixy_identity", ""),
                "current_esha_identity": audit.get("current_esha_identity", ""),
                "missing_terms_from_current_esha": audit.get("missing_terms_from_current_esha", ""),
                "conflicting_terms_in_current_esha": audit.get("conflicting_terms_in_current_esha", ""),
                "best_esha_code": best_code,
                "best_esha_description": best_desc,
                "best_esha_head": str(pair.get("best_esha_head", "")),
                "fixy_fndds_code": fixy_code,
                "fixy_fndds_description": fixy_desc,
                "fndds_main_code": str(pair.get("fndds_main_code", "")),
                "fndds_main_description": str(pair.get("fndds_main_description", "")),
                "wweia_category_code": str(pair.get("wweia_category_code", "")),
                "wweia_category_description": str(pair.get("wweia_category_description", "")),
                "top_categories": " | ".join(f"{key}:{value}" for key, value in category_counts.most_common(5)),
            }
        )
    pair_rows.sort(
        key=lambda row: (
            row["fixy_pair_collision_flag"] != "TRUE",
            -int(row["severity"] or 0),
            -int(row["row_count"] or 0),
            row["best_esha_description"],
            row["fixy_fndds_description"],
        )
    )
    with pair_path.open("w", newline="", encoding="utf-8") as pair_handle:
        writer = csv.DictWriter(pair_handle, fieldnames=PAIR_FIELDS)
        writer.writeheader()
        writer.writerows(pair_rows)

    return {
        "input_map": str(input_path),
        "rows_scanned": total,
        "assigned_rows_scanned": assigned_count,
        "wrong_assignment_rows": suspect_count,
        "bucket_counts": {key: int(value) for key, value in bucket_counts.most_common()},
        "recommended_action_counts": {key: int(value) for key, value in action_counts.most_common()},
        "full_output": str(full_path),
        "suspect_output": str(suspect_path),
        "pair_collision_output": str(pair_path),
        "distinct_fixy_esha_pairs": len(pair_rows),
        "distinct_flagged_fixy_esha_pairs": sum(1 for row in pair_rows if row["fixy_pair_collision_flag"] == "TRUE"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build one whole-corpus wrong Product -> ESHA assignment audit.")
    parser.add_argument("--input-map", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--esha-spine", type=Path, default=DEFAULT_ESHA_SPINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--full-output", type=Path, default=DEFAULT_FULL_OUTPUT)
    parser.add_argument("--pair-output", type=Path, default=DEFAULT_PAIR_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    summary = build_outputs(
        args.input_map,
        args.esha_spine,
        suspect_path=args.output,
        full_path=args.full_output,
        pair_path=args.pair_output,
    )
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
