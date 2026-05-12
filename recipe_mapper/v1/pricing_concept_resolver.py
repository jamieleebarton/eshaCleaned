#!/usr/bin/env python3
"""Resolve recipe ingredient surfaces to safe shopping concepts.

The v7 calculator intentionally refuses broad retail head-noun fallback. This
module keeps that safety property while letting the calculator use the assets
that already exist in the audit bundle: SR28 ingredient aliases, reviewed
normalization rules, canonical aliases, identity registry, and tree nodes.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

INGREDIENT_TO_SR28 = HERE / "output" / "ingredient_to_sr28.csv"
IDENTITY_REGISTRY = HERE / "output" / "identity_registry.csv"
CONSENSUS_TREE_NODES = HERE / "output" / "consensus_tree_nodes.csv"
APPROVED_NORMALIZATION_RULES = ROOT / "implementation" / "approved_normalization_rules.csv"
SUPPLEMENTAL_CONCEPTS = ROOT / "implementation" / "supplemental_concepts_seed.csv"
CANONICAL_ALIASES = ROOT / "implementation" / "canonical_aliases.csv"

WS = re.compile(r"[^a-z0-9]+")


def normalize_surface(value: str) -> str:
    return " ".join(WS.sub(" ", (value or "").lower()).split())


def singular_word(value: str) -> str:
    if value.endswith("ies") and len(value) > 4:
        return value[:-3] + "y"
    if value.endswith("es") and len(value) > 3 and value[-3] in "sxz":
        return value[:-2]
    if value.endswith("s") and len(value) > 2 and not value.endswith("ss"):
        return value[:-1]
    return value


def normalize_key(value: str) -> str:
    return " ".join(singular_word(part) for part in normalize_surface(value).split())


@dataclass(frozen=True)
class ProductGate:
    """Extra product checks required by a resolved recipe concept."""

    required_all: tuple[str, ...] = ()
    required_any: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    required_path_any: tuple[str, ...] = ()
    forbidden_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedIngredient:
    input_surface: str
    normalized_surface: str
    concepts: frozenset[tuple[str, str]]
    source: str
    product_gate: ProductGate = ProductGate()
    nutrition_anchor: str = ""
    notes: tuple[str, ...] = ()

    def match_concepts(self, include_equivalents: bool = True) -> frozenset[tuple[str, str]]:
        concepts = set(self.concepts)
        if include_equivalents:
            for concept in self.concepts:
                concepts.update(SAFE_EQUIVALENT_PRODUCT_CONCEPTS.get(concept, ()))
        return frozenset(concepts)


@dataclass(frozen=True)
class AliasSpec:
    canonical_surface: str
    concepts: tuple[tuple[str, str], ...]
    gate: ProductGate = ProductGate()
    nutrition_anchor: str = ""
    notes: tuple[str, ...] = ()


def _gate(
    *,
    all_terms: Iterable[str] = (),
    any_terms: Iterable[str] = (),
    forbidden: Iterable[str] = (),
    path_any: Iterable[str] = (),
    path_forbidden: Iterable[str] = (),
) -> ProductGate:
    return ProductGate(
        required_all=tuple(normalize_surface(t) for t in all_terms if t),
        required_any=tuple(normalize_surface(t) for t in any_terms if t),
        forbidden=tuple(normalize_surface(t) for t in forbidden if t),
        required_path_any=tuple(normalize_surface(t) for t in path_any if t),
        forbidden_path=tuple(normalize_surface(t) for t in path_forbidden if t),
    )


def _concept(path: str, modifier: str = "") -> tuple[str, str]:
    return (path, normalize_surface(modifier))


SPICE_PATH = "Pantry > Spices & Seasonings"

MANUAL_ALIAS_SPECS: dict[str, AliasSpec] = {
    "all purpose flour": AliasSpec(
        "all-purpose flour",
        (_concept("Pantry > Flour"),),
        _gate(
            all_terms=("flour",),
            any_terms=("all purpose", "all-purpose"),
            forbidden=("whole wheat", "almond flour", "coconut flour", "rice flour", "pancake mix", "baking mix"),
            path_any=("baking", "flour", "pantry"),
        ),
        "SR28:168894",
    ),
    "unbleached all purpose flour": AliasSpec(
        "all-purpose flour",
        (_concept("Pantry > Flour"),),
        _gate(
            all_terms=("flour",),
            any_terms=("all purpose", "all-purpose", "unbleached"),
            forbidden=("whole wheat", "almond flour", "coconut flour", "rice flour", "pancake mix", "baking mix"),
            path_any=("baking", "flour", "pantry"),
        ),
        "SR28:168936",
    ),
    "granulated sugar": AliasSpec(
        "granulated sugar",
        (_concept("Pantry > Sweeteners > Sugar"),),
        _gate(
            all_terms=("sugar",),
            any_terms=("granulated", "pure cane", "white sugar"),
            forbidden=("powdered", "confectioners", "brown sugar", "substitute", "splenda", "stevia", "sugar free"),
            path_any=("sugar", "sweeteners", "baking"),
        ),
        "SR28:169655",
    ),
    "white sugar": AliasSpec(
        "granulated sugar",
        (_concept("Pantry > Sweeteners > Sugar"),),
        _gate(
            all_terms=("sugar",),
            any_terms=("granulated", "white", "pure cane"),
            forbidden=("powdered", "confectioners", "brown sugar", "substitute", "splenda", "stevia", "sugar free"),
            path_any=("sugar", "sweeteners", "baking"),
        ),
        "SR28:169655",
    ),
    "powdered sugar": AliasSpec(
        "powdered sugar",
        (_concept("Pantry > Sweeteners > Sugar"),),
        _gate(
            all_terms=("sugar",),
            any_terms=("powdered", "confectioners", "confectioner"),
            forbidden=("granulated", "brown sugar", "substitute", "splenda", "stevia", "sugar free"),
            path_any=("sugar", "sweeteners", "baking"),
        ),
    ),
    "unsalted butter": AliasSpec(
        "unsalted butter",
        (_concept("Dairy > Butter"),),
        _gate(
            all_terms=("butter", "unsalted"),
            forbidden=("butter pecan", "ice cream", "cookie", "popcorn", "spray", "spread", "peanut", "almond"),
            path_any=("dairy", "butter"),
        ),
        "SR28:173430",
    ),
    "salted butter": AliasSpec(
        "salted butter",
        (_concept("Dairy > Butter"),),
        _gate(
            all_terms=("butter",),
            any_terms=("salted", "sweet cream"),
            forbidden=("unsalted", "butter pecan", "ice cream", "cookie", "popcorn", "spray", "peanut", "almond"),
            path_any=("dairy", "butter"),
        ),
    ),
    "kosher salt": AliasSpec(
        "kosher salt",
        (_concept(f"{SPICE_PATH} > Salt"),),
        _gate(
            all_terms=("salt", "kosher"),
            forbidden=("celery salt", "garlic salt", "onion salt", "seasoned salt", "seasoning salt", "bacon flavored", "black pepper"),
            path_any=("salt", "spices", "seasonings", "baking"),
        ),
        "SR28:173468",
    ),
    "sea salt": AliasSpec(
        "sea salt",
        (_concept(f"{SPICE_PATH} > Salt"),),
        _gate(
            all_terms=("salt",),
            any_terms=("sea salt", "fine sea", "coarse sea"),
            forbidden=("celery salt", "garlic salt", "onion salt", "seasoned salt", "seasoning salt", "bacon flavored", "black pepper"),
            path_any=("salt", "spices", "seasonings", "baking"),
        ),
        "SR28:173468",
    ),
    "black pepper": AliasSpec(
        "black pepper",
        (_concept(f"{SPICE_PATH} > Black Pepper"),),
        _gate(
            all_terms=("pepper",),
            any_terms=("black pepper", "peppercorn"),
            forbidden=("lemon pepper", "seasoned", "sauce", "chips", "cracker", "salmon"),
            path_any=("pepper", "spices", "seasonings"),
        ),
        "SR28:170931",
    ),
    "ground black pepper": AliasSpec(
        "black pepper",
        (_concept(f"{SPICE_PATH} > Black Pepper"),),
        _gate(
            all_terms=("pepper",),
            any_terms=("black pepper", "ground pepper", "peppercorn"),
            forbidden=("lemon pepper", "seasoned", "sauce", "chips", "cracker", "salmon"),
            path_any=("pepper", "spices", "seasonings"),
        ),
        "SR28:170931",
    ),
    "ground cinnamon": AliasSpec(
        "ground cinnamon",
        (_concept(f"{SPICE_PATH} > Cinnamon"),),
        _gate(
            all_terms=("cinnamon",),
            forbidden=("cereal", "toast", "toaster", "roll", "bun", "applesauce", "snack", "cookie", "bar"),
            path_any=("cinnamon", "spices", "seasonings"),
        ),
        "SR28:171320",
    ),
    "cinnamon": AliasSpec(
        "cinnamon",
        (_concept(f"{SPICE_PATH} > Cinnamon"),),
        _gate(
            all_terms=("cinnamon",),
            forbidden=("cereal", "toast", "toaster", "roll", "bun", "applesauce", "snack", "cookie", "bar"),
            path_any=("cinnamon", "spices", "seasonings"),
        ),
        "SR28:171320",
    ),
    "ground cumin": AliasSpec(
        "ground cumin",
        (_concept(f"{SPICE_PATH} > Cumin"),),
        _gate(
            all_terms=("cumin",),
            forbidden=("sauce", "hummus", "snack", "chips", "seasoned rice"),
            path_any=("cumin", "spices", "seasonings"),
        ),
    ),
    "cumin": AliasSpec(
        "cumin",
        (_concept(f"{SPICE_PATH} > Cumin"),),
        _gate(
            all_terms=("cumin",),
            forbidden=("sauce", "hummus", "snack", "chips", "seasoned rice"),
            path_any=("cumin", "spices", "seasonings"),
        ),
    ),
    "paprika": AliasSpec(
        "paprika",
        (_concept(f"{SPICE_PATH} > Paprika"),),
        _gate(all_terms=("paprika",), forbidden=("chips", "snack", "sauce"), path_any=("paprika", "spices", "seasonings")),
    ),
    "cayenne pepper": AliasSpec(
        "cayenne pepper",
        (_concept(f"{SPICE_PATH} > Cayenne Pepper"),),
        _gate(all_terms=("cayenne",), forbidden=("sauce", "chips", "snack"), path_any=("cayenne", "spices", "seasonings")),
    ),
    "bay leaf": AliasSpec(
        "bay leaves",
        (_concept(f"{SPICE_PATH} > Bay Leaves"),),
        _gate(all_terms=("bay",), any_terms=("leaf", "leaves"), forbidden=("candle", "laurel wreath"), path_any=("bay", "spices", "seasonings")),
    ),
    "bay leave": AliasSpec(
        "bay leaves",
        (_concept(f"{SPICE_PATH} > Bay Leaves"),),
        _gate(all_terms=("bay",), any_terms=("leaf", "leaves"), forbidden=("candle", "laurel wreath"), path_any=("bay", "spices", "seasonings")),
    ),
    "parmesan cheese": AliasSpec(
        "parmesan cheese",
        (_concept("Dairy > Cheese > Parmesan"),),
        _gate(
            all_terms=("parmesan",),
            forbidden=("pasta sauce", "sauce", "breadstick", "cracker", "crisps", "snack", "dressing"),
            path_any=("dairy", "cheese", "parmesan"),
        ),
        "SR28:171247",
    ),
    "grated parmesan cheese": AliasSpec(
        "grated parmesan cheese",
        (_concept("Dairy > Cheese > Parmesan"),),
        _gate(
            all_terms=("parmesan",),
            any_terms=("grated", "shredded", "parmesan"),
            forbidden=("pasta sauce", "sauce", "breadstick", "cracker", "crisps", "snack", "dressing"),
            path_any=("dairy", "cheese", "parmesan"),
        ),
        "SR28:171247",
    ),
    "sharp cheddar cheese": AliasSpec(
        "sharp cheddar cheese",
        (_concept("Dairy > Cheese > Cheddar"),),
        _gate(
            all_terms=("cheddar",),
            any_terms=("sharp", "extra sharp"),
            forbidden=("dip", "soup", "cracker", "snack", "sauce", "macaroni"),
            path_any=("dairy", "cheese", "cheddar"),
        ),
        "SR28:170899",
    ),
    "heavy cream": AliasSpec(
        "heavy cream",
        (_concept("Dairy > Cream > Heavy Cream"),),
        _gate(
            all_terms=("cream",),
            any_terms=("heavy", "whipping"),
            forbidden=("coffee creamer", "ice cream", "whipped topping", "half and half", "non dairy", "almond", "coconut"),
            path_any=("dairy", "cream"),
        ),
        "SR28:170859",
    ),
    "heavy whipping cream": AliasSpec(
        "heavy whipping cream",
        (_concept("Dairy > Cream > Heavy Whipping Cream"),),
        _gate(
            all_terms=("cream",),
            any_terms=("heavy", "whipping"),
            forbidden=("coffee creamer", "ice cream", "whipped topping", "half and half", "non dairy", "almond", "coconut"),
            path_any=("dairy", "cream"),
        ),
        "SR28:170859",
    ),
    "egg": AliasSpec(
        "eggs",
        (_concept("Dairy > Eggs"),),
        _gate(
            all_terms=("egg",),
            forbidden=(
                "egg noodle", "noodle", "roll wrapper", "easter", "chocolate",
                "vegan", "free from eggs", "mayonnaise", "hard boiled",
                "powder", "liquid", "substitute", "replacer", "plant based",
                "egg free",
            ),
            path_any=("dairy", "eggs"),
        ),
    ),
    "eggs": AliasSpec(
        "eggs",
        (_concept("Dairy > Eggs"),),
        _gate(
            all_terms=("egg",),
            forbidden=(
                "egg noodle", "noodle", "roll wrapper", "easter", "chocolate",
                "vegan", "free from eggs", "mayonnaise", "hard boiled",
                "powder", "liquid", "substitute", "replacer", "plant based",
                "egg free",
            ),
            path_any=("dairy", "eggs"),
        ),
    ),
    "egg yolk": AliasSpec(
        "egg yolk",
        (_concept("Dairy > Eggs"),),
        _gate(
            all_terms=("egg",),
            forbidden=(
                "egg noodle", "noodle", "roll wrapper", "easter", "chocolate",
                "vegan", "free from eggs", "mayonnaise", "hard boiled",
                "powder", "liquid", "substitute", "replacer", "plant based",
                "egg free",
            ),
            path_any=("dairy", "eggs"),
        ),
    ),
    "egg yolks": AliasSpec(
        "egg yolk",
        (_concept("Dairy > Eggs"),),
        _gate(
            all_terms=("egg",),
            forbidden=(
                "egg noodle", "noodle", "roll wrapper", "easter", "chocolate",
                "vegan", "free from eggs", "mayonnaise", "hard boiled",
                "powder", "liquid", "substitute", "replacer", "plant based",
                "egg free",
            ),
            path_any=("dairy", "eggs"),
        ),
    ),
    "egg white": AliasSpec(
        "egg whites",
        (_concept("Dairy > Egg Whites"), _concept("Dairy > Eggs")),
        _gate(
            all_terms=("egg",),
            any_terms=("white", "whites"),
            forbidden=("egg noodle", "noodle", "roll wrapper", "easter", "chocolate", "vegan", "free from eggs", "mayonnaise", "whole egg powder", "powder"),
            path_any=("dairy", "eggs"),
        ),
    ),
    "egg whites": AliasSpec(
        "egg whites",
        (_concept("Dairy > Egg Whites"), _concept("Dairy > Eggs")),
        _gate(
            all_terms=("egg",),
            any_terms=("white", "whites"),
            forbidden=("egg noodle", "noodle", "roll wrapper", "easter", "chocolate", "vegan", "free from eggs", "mayonnaise", "whole egg powder", "powder"),
            path_any=("dairy", "eggs"),
        ),
    ),
    "garlic": AliasSpec(
        "garlic",
        (_concept("Produce > Vegetables > Garlic"),),
        _gate(
            all_terms=("garlic",),
            forbidden=("garlic salt", "garlic powder", "garlic sauce", "garlic butter", "garlic bread", "seasoning", "snack"),
            path_any=("produce", "fresh vegetables", "garlic"),
        ),
        "SR28:169230",
    ),
    "garlic clove": AliasSpec(
        "garlic",
        (_concept("Produce > Vegetables > Garlic"),),
        _gate(
            all_terms=("garlic",),
            forbidden=("garlic salt", "garlic powder", "garlic sauce", "garlic butter", "garlic bread", "seasoning", "snack"),
            path_any=("produce", "fresh vegetables", "garlic"),
        ),
        "SR28:169230",
    ),
    "garlic cloves": AliasSpec(
        "garlic",
        (_concept("Produce > Vegetables > Garlic"),),
        _gate(
            all_terms=("garlic",),
            forbidden=("garlic salt", "garlic powder", "garlic sauce", "garlic butter", "garlic bread", "seasoning", "snack"),
            path_any=("produce", "fresh vegetables", "garlic"),
        ),
        "SR28:169230",
    ),
    "cornstarch": AliasSpec(
        "cornstarch",
        (_concept("Pantry > Flour > Cornstarch"), _concept("Pantry > Flour > Corn Starch")),
        _gate(
            any_terms=("cornstarch", "corn starch"),
            forbidden=("baby powder", "body powder", "laundry", "starch spray"),
            path_any=("baking", "flour", "corn starch", "cornstarch", "pantry"),
        ),
    ),
    "corn starch": AliasSpec(
        "cornstarch",
        (_concept("Pantry > Flour > Corn Starch"), _concept("Pantry > Flour > Cornstarch")),
        _gate(
            any_terms=("cornstarch", "corn starch"),
            forbidden=("baby powder", "body powder", "laundry", "starch spray"),
            path_any=("baking", "flour", "corn starch", "cornstarch", "pantry"),
        ),
    ),
    "ground beef": AliasSpec(
        "ground beef",
        (_concept("Meat & Seafood > Beef > Ground Beef"),),
        _gate(
            all_terms=("beef",),
            any_terms=("ground", "hamburger"),
            forbidden=("plant based", "vegan", "impossible", "beyond", "seasoning", "helper"),
            path_any=("meat", "beef"),
        ),
    ),
    "lean ground beef": AliasSpec(
        "ground beef",
        (_concept("Meat & Seafood > Beef > Ground Beef"),),
        _gate(
            all_terms=("beef",),
            any_terms=("ground", "hamburger"),
            forbidden=("plant based", "vegan", "impossible", "beyond", "seasoning", "helper"),
            path_any=("meat", "beef"),
        ),
    ),
}

MANUAL_ALIAS_SPECS.update({
    "lemon": AliasSpec(
        "lemons",
        (_concept("Produce > Fruit > Lemons"), _concept("Frozen > Frozen Fruit > Lemons")),
        _gate(all_terms=("lemon",), forbidden=("bar", "loaf", "cake", "mix", "drop", "paste", "juice", "drink"), path_any=("produce", "fruit", "citrus", "lemons")),
        "SR28:167746",
    ),
    "lemon zest": AliasSpec(
        "lemons",
        (_concept("Produce > Fruit > Lemons"), _concept("Frozen > Frozen Fruit > Lemons")),
        _gate(all_terms=("lemon",), forbidden=("bar", "loaf", "cake", "mix", "drop", "paste", "juice", "drink"), path_any=("produce", "fruit", "citrus", "lemons")),
        "SR28:167749",
    ),
    "lime": AliasSpec(
        "limes",
        (_concept("Produce > Fruit > Limes"), _concept("Frozen > Frozen Fruit > Lime")),
        _gate(all_terms=("lime",), forbidden=("dressing", "mix", "juice", "drink", "chips", "seasoning"), path_any=("produce", "fruit", "citrus", "limes")),
    ),
    "lime zest": AliasSpec(
        "limes",
        (_concept("Produce > Fruit > Limes"), _concept("Frozen > Frozen Fruit > Lime")),
        _gate(all_terms=("lime",), forbidden=("dressing", "mix", "juice", "drink", "chips", "seasoning"), path_any=("produce", "fruit", "citrus", "limes")),
    ),
    "orange zest": AliasSpec(
        "oranges",
        (_concept("Produce > Fruit > Oranges"), _concept("Frozen > Frozen Fruit > Oranges")),
        _gate(all_terms=("orange",), forbidden=("juice", "drink", "candy", "marmalade", "sauce"), path_any=("produce", "fruit", "citrus", "oranges")),
    ),
    "red onion": AliasSpec(
        "red onion",
        (_concept("Produce > Vegetables > Onions > Red"), _concept("Produce > Vegetables > Red Onion"), _concept("Produce > Vegetables > Red Onions")),
        _gate(all_terms=("onion", "red"), forbidden=("ring", "dip", "soup", "chips", "seasoning"), path_any=("produce", "vegetables", "onions")),
    ),
    "yellow onion": AliasSpec(
        "yellow onion",
        (_concept("Produce > Vegetables > Onions > Yellow"), _concept("Produce > Vegetables > Onions")),
        _gate(all_terms=("onion",), any_terms=("yellow", "sweet"), forbidden=("ring", "dip", "soup", "chips", "seasoning"), path_any=("produce", "vegetables", "onions")),
    ),
    "white onion": AliasSpec(
        "white onion",
        (_concept("Produce > Vegetables > Onions"),),
        _gate(all_terms=("onion",), any_terms=("white", "onion"), forbidden=("ring", "dip", "soup", "chips", "seasoning"), path_any=("produce", "vegetables", "onions")),
    ),
    "red bell pepper": AliasSpec(
        "red bell pepper",
        (_concept("Produce > Vegetables > Bell Peppers > Red"), _concept("Produce > Vegetables > Bell Peppers")),
        _gate(all_terms=("pepper",), any_terms=("red bell", "red pepper"), forbidden=("roasted", "sauce", "flakes", "seasoning", "chips"), path_any=("produce", "vegetables", "peppers")),
    ),
    "green bell pepper": AliasSpec(
        "green bell pepper",
        (_concept("Produce > Vegetables > Bell Peppers > Green"), _concept("Produce > Vegetables > Bell Peppers"), _concept("Produce > Vegetables > Green Peppers")),
        _gate(all_terms=("pepper",), any_terms=("green bell", "green pepper"), forbidden=("sauce", "flakes", "seasoning", "chips"), path_any=("produce", "vegetables", "peppers")),
    ),
    "green pepper": AliasSpec(
        "green bell pepper",
        (_concept("Produce > Vegetables > Green Peppers"), _concept("Produce > Vegetables > Bell Peppers > Green"), _concept("Produce > Vegetables > Bell Peppers")),
        _gate(all_terms=("pepper",), any_terms=("green", "bell"), forbidden=("sauce", "flakes", "seasoning", "chips"), path_any=("produce", "vegetables", "peppers")),
    ),
    "bell pepper": AliasSpec(
        "bell pepper",
        (_concept("Produce > Vegetables > Bell Peppers"),),
        _gate(all_terms=("pepper",), any_terms=("bell", "pepper"), forbidden=("sauce", "flakes", "seasoning", "chips"), path_any=("produce", "vegetables", "peppers")),
    ),
    "dijon mustard": AliasSpec(
        "dijon mustard",
        (_concept("Pantry > Condiments > Mustard"),),
        _gate(all_terms=("mustard", "dijon"), forbidden=("honey mustard", "dressing", "pretzel", "chips"), path_any=("condiments", "mustard", "pantry")),
    ),
    "dry mustard": AliasSpec(
        "dry mustard",
        (_concept("Pantry > Condiments > Mustard"), _concept(f"{SPICE_PATH} > Mustard")),
        _gate(all_terms=("mustard",), any_terms=("dry", "ground", "powder"), forbidden=("dressing", "pretzel", "chips"), path_any=("mustard", "spices", "seasonings", "condiments")),
    ),
    "light brown sugar": AliasSpec(
        "light brown sugar",
        (_concept("Pantry > Sweeteners > Sugar > Brown Sugar"),),
        _gate(all_terms=("brown sugar",), any_terms=("light", "brown"), forbidden=("cracker", "cereal", "substitute"), path_any=("sugar", "sweeteners", "baking")),
    ),
    "dark brown sugar": AliasSpec(
        "dark brown sugar",
        (_concept("Pantry > Sweeteners > Sugar > Brown Sugar"),),
        _gate(all_terms=("brown sugar",), any_terms=("dark", "brown"), forbidden=("cracker", "cereal", "substitute"), path_any=("sugar", "sweeteners", "baking")),
    ),
    "caster sugar": AliasSpec(
        "granulated sugar",
        (_concept("Pantry > Sweeteners > Sugar"),),
        _gate(all_terms=("sugar",), any_terms=("caster", "superfine", "granulated"), forbidden=("powdered", "brown sugar", "substitute"), path_any=("sugar", "sweeteners", "baking")),
    ),
    "whole wheat flour": AliasSpec(
        "whole wheat flour",
        (_concept("Pantry > Flour"),),
        _gate(all_terms=("flour",), any_terms=("whole wheat", "wheat flour"), forbidden=("almond flour", "coconut flour", "pancake mix", "baking mix"), path_any=("baking", "flour", "pantry")),
    ),
    "mozzarella cheese": AliasSpec(
        "mozzarella cheese",
        (_concept("Dairy > Cheese > Mozzarella"), _concept("Dairy > Mozzarella Cheese")),
        _gate(all_terms=("mozzarella",), forbidden=("sticks", "breaded", "pizza", "snack", "dip"), path_any=("dairy", "cheese", "mozzarella")),
    ),
    "monterey jack cheese": AliasSpec(
        "monterey jack cheese",
        (_concept("Dairy > Cheese > Monterey Jack"),),
        _gate(all_terms=("jack",), any_terms=("monterey", "monterey jack"), forbidden=("dip", "cracker", "snack", "soup"), path_any=("dairy", "cheese")),
    ),
    "feta cheese": AliasSpec(
        "feta cheese",
        (_concept("Dairy > Cheese > Feta"),),
        _gate(all_terms=("feta",), forbidden=("dressing", "dip", "snack"), path_any=("dairy", "cheese", "feta")),
    ),
    "swiss cheese": AliasSpec(
        "swiss cheese",
        (_concept("Dairy > Cheese > Swiss"),),
        _gate(all_terms=("swiss",), forbidden=("sandwich", "cracker", "soup", "dip"), path_any=("dairy", "cheese", "swiss")),
    ),
    "ricotta cheese": AliasSpec(
        "ricotta cheese",
        (_concept("Dairy > Cheese > Ricotta"),),
        _gate(all_terms=("ricotta",), forbidden=("lasagna", "meal", "dip"), path_any=("dairy", "cheese", "ricotta")),
    ),
    "chicken stock": AliasSpec(
        "chicken stock",
        (_concept("Pantry > Broth & Stock > Chicken Stock"), _concept("Pantry > Broth & Stock > Broth")),
        _gate(all_terms=("chicken",), any_terms=("stock", "broth"), forbidden=("base", "bouillon", "ramen", "soup mix"), path_any=("broth", "stock", "pantry")),
    ),
    "white vinegar": AliasSpec(
        "white vinegar",
        (_concept("Pantry > Vinegar"), _concept("Pantry > Sauces & Salsas > White Vinegar")),
        _gate(all_terms=("vinegar",), any_terms=("white", "distilled"), forbidden=("cleaning", "chips", "dressing"), path_any=("vinegar", "pantry")),
    ),
    "buttermilk": AliasSpec(
        "buttermilk",
        (_concept("Dairy > Buttermilk"),),
        _gate(all_terms=("buttermilk",), forbidden=("pancake mix", "biscuit", "powder", "coffee creamer"), path_any=("dairy", "milk", "buttermilk")),
    ),
    "cocoa powder": AliasSpec(
        "cocoa powder",
        (_concept("Pantry > Baking Cocoa > Cocoa Powder"),),
        _gate(all_terms=("cocoa",), any_terms=("powder", "unsweetened"), forbidden=("drink mix", "hot cocoa", "candy", "protein"), path_any=("baking", "cocoa", "pantry")),
    ),
    "unsweetened cocoa powder": AliasSpec(
        "cocoa powder",
        (_concept("Pantry > Baking Cocoa > Cocoa Powder"),),
        _gate(all_terms=("cocoa",), any_terms=("powder", "unsweetened"), forbidden=("drink mix", "hot cocoa", "candy", "protein"), path_any=("baking", "cocoa", "pantry")),
    ),
    "almond extract": AliasSpec(
        "almond extract",
        (_concept("Pantry > Baking Extracts > Almond Extract"),),
        _gate(all_terms=("extract", "almond"), forbidden=("milk", "creamer", "snack"), path_any=("extract", "baking", "pantry")),
    ),
    "active dry yeast": AliasSpec(
        "active dry yeast",
        (_concept("Pantry > Baking Extracts > Yeast"),),
        _gate(all_terms=("yeast",), any_terms=("active dry", "instant", "rapid rise"), forbidden=("extract spread", "nutritional yeast"), path_any=("yeast", "baking", "pantry")),
    ),
    "flour tortilla": AliasSpec(
        "flour tortillas",
        (_concept("Bakery > Tortillas"),),
        _gate(all_terms=("tortilla",), any_terms=("flour", "soft taco", "fajita"), forbidden=("chips", "crisps", "corn tortilla chips"), path_any=("tortilla", "bakery", "bread")),
    ),
    "flour tortillas": AliasSpec(
        "flour tortillas",
        (_concept("Bakery > Tortillas"),),
        _gate(all_terms=("tortilla",), any_terms=("flour", "soft taco", "fajita"), forbidden=("chips", "crisps", "corn tortilla chips"), path_any=("tortilla", "bakery", "bread")),
    ),
    "skim milk": AliasSpec(
        "skim milk",
        (_concept("Dairy > Milk"),),
        _gate(all_terms=("milk",), any_terms=("skim", "fat free", "nonfat"), forbidden=("powder", "creamer", "almond", "oat", "soy", "chocolate"), path_any=("dairy", "milk")),
    ),
    "hot sauce": AliasSpec(
        "hot sauce",
        (_concept("Pantry > Sauces & Salsas > Hot Sauce"), _concept("Pantry > Sauces & Salsas > Hot Pepper Sauce")),
        _gate(all_terms=("sauce",), any_terms=("hot", "pepper", "tabasco", "sriracha"), forbidden=("marinade", "wing sauce"), path_any=("sauce", "condiments", "pantry")),
    ),
    "tabasco sauce": AliasSpec(
        "hot sauce",
        (_concept("Pantry > Sauces & Salsas > Hot Sauce"), _concept("Pantry > Sauces & Salsas > Hot Pepper Sauce")),
        _gate(all_terms=("tabasco",), any_terms=("sauce", "pepper"), forbidden=("marinade", "wing sauce"), path_any=("sauce", "condiments", "pantry")),
    ),
    "applesauce": AliasSpec(
        "applesauce",
        (_concept("Pantry > Applesauce"), _concept("Pantry > Canned Fruit > Applesauce")),
        _gate(all_terms=("applesauce",), forbidden=("mango", "peach", "strawberry", "berry", "cinnamon", "pouch", "fruit snack"), path_any=("applesauce", "pantry", "canned fruit")),
    ),
    "vanilla yogurt": AliasSpec(
        "vanilla yogurt",
        (_concept("Dairy > Yogurt"),),
        _gate(
            all_terms=("yogurt", "vanilla"),
            forbidden=(
                "frozen yogurt", "ice cream", "covered", "coated", "almond",
                "dairy free", "plant based", "soy", "coconut", "mixed berry",
                "strawberry", "cherry", "tropical", "tube", "drink",
                "smoothie", "bar", "granola", "m m", "oreo",
            ),
            path_any=("dairy", "yogurt"),
        ),
    ),
})


SAFE_EQUIVALENT_PRODUCT_CONCEPTS: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {
    _concept(f"{SPICE_PATH} > Black Pepper"): (
        _concept(f"{SPICE_PATH} > Spice Blend", "black pepper"),
        _concept(f"{SPICE_PATH} > Seasoning", "black pepper"),
    ),
    _concept(f"{SPICE_PATH} > Cinnamon"): (
        _concept(f"{SPICE_PATH} > Spice Blend", "cinnamon"),
        _concept(f"{SPICE_PATH} > Seasoning", "cinnamon"),
    ),
    _concept(f"{SPICE_PATH} > Cumin"): (
        _concept(f"{SPICE_PATH} > Spice Blend", "cumin"),
        _concept(f"{SPICE_PATH} > Seasoning", "cumin"),
        _concept(f"{SPICE_PATH} > Cumin Seeds"),
    ),
    _concept(f"{SPICE_PATH} > Paprika"): (
        _concept(f"{SPICE_PATH} > Spice Blend", "paprika"),
        _concept(f"{SPICE_PATH} > Seasoning", "paprika"),
    ),
    _concept(f"{SPICE_PATH} > Cayenne Pepper"): (
        _concept(f"{SPICE_PATH} > Spice Blend", "cayenne pepper"),
        _concept(f"{SPICE_PATH} > Seasoning", "cayenne pepper"),
    ),
    _concept(f"{SPICE_PATH} > Bay Leaves"): (
        _concept(f"{SPICE_PATH} > Spice Blend", "bay leaves"),
        _concept(f"{SPICE_PATH} > Seasoning", "bay leaves"),
    ),
    _concept("Dairy > Cream > Heavy Cream"): (
        _concept("Dairy > Cream > Heavy Whipping Cream"),
        _concept("Dairy > Cream > Whipping Cream"),
    ),
    _concept("Dairy > Cream > Heavy Whipping Cream"): (
        _concept("Dairy > Cream > Heavy Cream"),
        _concept("Dairy > Cream > Whipping Cream"),
    ),
    _concept("Pantry > Flour > Cornstarch"): (
        _concept("Pantry > Flour > Corn Starch"),
    ),
    _concept("Pantry > Flour > Corn Starch"): (
        _concept("Pantry > Flour > Cornstarch"),
    ),
    _concept("Dairy > Eggs"): (
        _concept("Dairy > Eggs > Egg Whites"),
    ),
}


class PricingConceptResolver:
    def __init__(
        self,
        *,
        ingredient_to_sr28: Path = INGREDIENT_TO_SR28,
        identity_registry: Path = IDENTITY_REGISTRY,
        consensus_tree_nodes: Path = CONSENSUS_TREE_NODES,
        approved_rules: Path = APPROVED_NORMALIZATION_RULES,
        supplemental_concepts: Path = SUPPLEMENTAL_CONCEPTS,
        canonical_aliases: Path = CANONICAL_ALIASES,
    ) -> None:
        self.pid_index: dict[str, set[tuple[str, str]]] = {}
        self.sr28_item_index: dict[str, str] = {}
        self.surface_aliases: dict[str, str] = {}
        self._load_tree(identity_registry)
        self._load_tree(consensus_tree_nodes)
        self._load_sr28_items(ingredient_to_sr28)
        self._load_surface_aliases(supplemental_concepts, canonical_aliases, approved_rules)

    def _add_pid(self, pid: str, canonical: str) -> None:
        pid_key = normalize_key(pid)
        if not pid_key or not canonical:
            return
        self.pid_index.setdefault(pid_key, set()).add(_concept(canonical))

    def _load_tree(self, path: Path) -> None:
        if not path.exists():
            return
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                self._add_pid(row.get("product_identity_fixed") or "", row.get("canonical_path") or "")

    def _load_sr28_items(self, path: Path) -> None:
        if not path.exists():
            return
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                item = normalize_key(row.get("item") or "")
                if item:
                    self.sr28_item_index[item] = row.get("fdc_id") or ""

    def _load_surface_aliases(self, supplemental: Path, canonical_aliases: Path, approved_rules: Path) -> None:
        if supplemental.exists():
            with supplemental.open(encoding="utf-8", errors="replace", newline="") as handle:
                for row in csv.DictReader(handle):
                    if (row.get("review_status") or "").strip().lower() != "approved":
                        continue
                    alias = normalize_key(row.get("alias") or "")
                    canonical = normalize_key(row.get("canonical_concept") or "")
                    if alias and canonical:
                        self.surface_aliases[alias] = canonical
        if canonical_aliases.exists():
            with canonical_aliases.open(encoding="utf-8", errors="replace", newline="") as handle:
                for row in csv.DictReader(handle):
                    alias = normalize_key(row.get("surface") or "")
                    canonical = normalize_key(row.get("canonical_name") or "")
                    if alias and canonical:
                        self.surface_aliases.setdefault(alias, canonical)
        if approved_rules.exists():
            with approved_rules.open(encoding="utf-8", errors="replace", newline="") as handle:
                for row in csv.DictReader(handle):
                    if (row.get("status") or "").strip().lower() != "approved":
                        continue
                    if (row.get("rule_type") or "").strip().lower() != "alias":
                        continue
                    if (row.get("match_type") or "").strip().lower() != "exact":
                        continue
                    alias = normalize_key(row.get("input_surface") or "")
                    canonical = normalize_key(row.get("canonical_surface") or "")
                    if alias and canonical and canonical != "manual quantity required":
                        self.surface_aliases.setdefault(alias, canonical)

    def resolve(
        self,
        item: str,
        fallback_concepts: Iterable[tuple[str, str]] | None = None,
    ) -> ResolvedIngredient:
        item_key = normalize_key(item)
        spec = MANUAL_ALIAS_SPECS.get(item_key)
        if spec:
            return ResolvedIngredient(
                input_surface=item,
                normalized_surface=spec.canonical_surface,
                concepts=frozenset(spec.concepts),
                source="manual_alias",
                product_gate=spec.gate,
                nutrition_anchor=spec.nutrition_anchor,
                notes=spec.notes,
            )

        canonical_alias = self.surface_aliases.get(item_key)
        if canonical_alias:
            alias_spec = MANUAL_ALIAS_SPECS.get(canonical_alias)
            if alias_spec:
                return ResolvedIngredient(
                    input_surface=item,
                    normalized_surface=alias_spec.canonical_surface,
                    concepts=frozenset(alias_spec.concepts),
                    source="reviewed_surface_alias",
                    product_gate=alias_spec.gate,
                    nutrition_anchor=alias_spec.nutrition_anchor,
                    notes=alias_spec.notes,
                )
            alias_concepts = self.pid_index.get(canonical_alias)
            if alias_concepts:
                return ResolvedIngredient(
                    input_surface=item,
                    normalized_surface=canonical_alias,
                    concepts=frozenset(alias_concepts),
                    source="reviewed_surface_alias",
                    nutrition_anchor=self._anchor_for(item_key),
                )

        direct_concepts = self.pid_index.get(item_key)
        if direct_concepts:
            return ResolvedIngredient(
                input_surface=item,
                normalized_surface=item_key,
                concepts=frozenset(direct_concepts),
                source="tree_identity_exact",
                nutrition_anchor=self._anchor_for(item_key),
            )

        fallback = frozenset(fallback_concepts or ())
        if fallback:
            return ResolvedIngredient(
                input_surface=item,
                normalized_surface=item_key,
                concepts=fallback,
                source="legacy_fast_concepts",
                nutrition_anchor=self._anchor_for(item_key),
            )

        return ResolvedIngredient(
            input_surface=item,
            normalized_surface=item_key,
            concepts=frozenset(),
            source="unresolved",
            nutrition_anchor=self._anchor_for(item_key),
        )

    def _anchor_for(self, item_key: str) -> str:
        fdc_id = self.sr28_item_index.get(item_key)
        return f"SR28:{fdc_id}" if fdc_id else ""


def product_passes_gate(resolved: ResolvedIngredient, product: dict) -> bool:
    gate = resolved.product_gate
    if not any((gate.required_all, gate.required_any, gate.forbidden, gate.required_path_any, gate.forbidden_path)):
        return True

    title = normalize_surface(str(product.get("name") or ""))
    path_blob = normalize_surface(" ".join(
        str(product.get(key) or "")
        for key in ("canonical", "category_path", "category_path_walmart")
    ))

    if any(term and term not in title for term in gate.required_all):
        return False
    if gate.required_any and not any(term and term in title for term in gate.required_any):
        return False
    if any(term and term in title for term in gate.forbidden):
        return False
    if gate.required_path_any and not any(term and term in path_blob for term in gate.required_path_any):
        return False
    if any(term and term in path_blob for term in gate.forbidden_path):
        return False
    return True
