from __future__ import annotations

import match_esha_to_products as matcher

from .contract_base import (
    ContractFn,
    ContractSpec,
    MatchDecision,
    ProductFacts,
    accept,
    match_spec,
    reject,
    todo,
)


BEAN_CATEGORIES = (
    "bean",
    "beans",
    "legume",
    "lentil",
    "vegetable",
    "canned",
    "bottled",
    "frozen",
    "prepared",
    "processed",
)

PINTO_BASE_EXCLUDES = (
    "baked",
    "refried",
    "rice",
    "salad",
    "burrito",
    "topping",
    "stew",
    "fajita",
    "cheese",
    "dip",
    "chili",
    "mix",
    "black",
    "kidney",
    "lima",
    "navy",
    "garbanzo",
    "chickpea",
    "green",
    "espresso",
    "coffee",
)

REFRIED_PINTO_EXCLUDES = (
    "baked",
    "rice",
    "salad",
    "burrito",
    "topping",
    "stew",
    "fajita",
    "cheese",
    "black",
    "kidney",
    "lima",
    "navy",
    "green",
    "espresso",
    "coffee",
)

PREPARED_DISH_TERMS = (
    "casserole",
    "meal",
    "dish",
    "dinner",
    "entree",
    "side",
    "sauce",
    "almondine",
    "gravy",
)

MAYONNAISE_FLAVOR_EXCLUDES = (
    # Flavor modifiers that define a DIFFERENT card (chipotle mayo, lime mayo,
    # etc. each own their specific ESHA). Plain mayo must reject all of these.
    "chipotle",
    "mango",
    "sundried",
    "tomato",
    "campfire",
    "relish",
    "onion",
    "ranch",
    "garlic",
    "bacon",
    "sandwich",
    "sriracha",
    "wasabi",
    "habanero",
    "jalapeno",
    "lime",
    "serrano",
    "pesto",
    "truffle",
    "ketchup",
    "spicy",
    "aioli",
    "avocado",  # avocado mayo
    # Fat/nutrition class modifiers — these define a different nutrition
    # profile; plain mayo ESHA 8046 is regular mayo only. Light, fat free,
    # reduced fat, olive oil mayo etc. each own their specific ESHA.
    "light",
    "lite",
    "low-fat",
    "lowfat",
    "low fat",
    "fat-free",
    "fat free",
    "fatfree",
    "reduced",
    "olive oil",
    "canola",
    "soybean oil",
    # Non-dairy / plant imitators
    "vegan",
    "plant-based",
    "plant based",
    "plantbased",
    "non-dairy",
    "non dairy",
    "imitation",
)

CHEDDAR_EXCLUDES = (
    "alternative",
    "ale",
    # Prepared / composite dishes (existing)
    "mac",
    "macaroni",
    "pasta",
    "sauce",
    "dip",
    "soup",
    "cracker",
    "chip",
    "popcorn",
    "snack",
    "meal",
    "sandwich",
    "hash",
    "potato",
    "potatoe",
    "burrito",
    "pizza",
    "kit",
    "dinner",
    "entree",
    # Other cheese species — each owns its own ESHA card. Plain cheddar
    # must reject anything tagged as a blend with or substitute for
    # another cheese variety.
    "jack",
    "monterey",
    "colby",
    "swiss",
    "parmesan",
    "parmigiano",
    "romano",
    "mozzarella",
    "provolone",
    "gouda",
    "feta",
    "brie",
    "ricotta",
    "asiago",
    "muenster",
    "american cheese",
    "gruyere",
    # Imitation / non-dairy
    "cashew",
    "vegan",
    "plant-based",
    "plant based",
    "plantbased",
    "non-dairy",
    "non dairy",
    "nondairy",
    "imitation",
    # Multi-cheese platters / blends
    "blend",
    "blended",
    "chive",
    "chives",
    "onion",
    "trio",
    "tray",
    "platter",
    "assortment",
    "truffle",
    "truffles",
)

# Approved plain-cheddar MODIFIERS (must still satisfy exclude_terms; these
# just document that sharp/mild/white/yellow/double/triple cheddar are fine).
CHEDDAR_ALLOWED_MODIFIERS = (
    "sharp", "mild", "medium", "extra",
    "white", "yellow", "red", "orange",
    "double", "triple", "aged", "block", "shredded",
    "slice", "sliced", "shred",
)

HASH_BROWN_EXCLUDES = (
    "breakfast",
    "casserole",
    "cheese",
    "sliced",
    "slice",
    "loaded",
    "meal",
    "mashed",
    "gratin",
    "au",
    "sandwich",
)

SLICED_POTATO_EXCLUDES = (
    "hash",
    "hashbrown",
    "hashbrowns",
    "fries",
    "fry",
    "tot",
    "tots",
    "mashed",
    "shredded",
    "diced",
    "patty",
)


def has_mayo(product: ProductFacts) -> bool:
    return product.has_any("mayonnaise", "mayo")


def has_potato(product: ProductFacts) -> bool:
    return product.has_any("potato", "potatoes")


def make_plain_animal_milk_contract(esha_code: str, esha_description: str, species: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        spec = ContractSpec(
            esha_code=esha_code,
            esha_description=esha_description,
            allowed_categories=("milk", "milk/cream"),
            search_terms=(species, "milk"),
            required_terms=(species, "milk"),
            exclude_terms=(
                "butter",
                "cheddar",
                "cheese",
                "chevre",
                "cultured",
                "condensed",
                "cream",
                "dried",
                "dry",
                "evaporated",
                "feta",
                "flavor",
                "flavored",
                "gouda",
                "ice",
                "jack",
                "kefir",
                "manchego",
                "mix",
                "pecan",
                "pecans",
                "powder",
                "powdered",
                "ricotta",
                "shake",
                "yogurt",
                "yoghurt",
            ),
        )
        return match_spec(product, spec)

    return contract


def make_carob_dry_mix_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("powdered drinks", "other drinks", "breakfast drinks", "non alcoholic beverages"):
            return reject(f"{esha_code} category mismatch")
        if not (product.has_any("carob") or product.ingredients_have_any("carob")):
            return reject(f"{esha_code} missing carob identity")
        if not (
            product.has_any("mix", "powder", "drink")
            or product.ingredients_have_any("powder")
        ):
            return reject(f"{esha_code} missing dry-mix signal")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_low_sodium_milk_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("milk", "milk/cream"):
            return reject(f"{esha_code} category mismatch")
        if "milk" not in product.description_tokens:
            return reject(f"{esha_code} missing milk term")
        if not (
            product.has_phrase("low sodium")
            or product.has_phrase("lower sodium")
            or product.has_phrase("reduced sodium")
        ):
            return reject(f"{esha_code} missing low-sodium claim")
        if product.has_any(
            "condensed",
            "evaporated",
            "powder",
            "mix",
            "cocoa",
            "chocolate",
            "protein",
            "almond",
            "soy",
            "oat",
            "coconut",
            "cheese",
            "yogurt",
            "creamer",
        ):
            return reject(f"{esha_code} excluded milk subtype")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


PLAIN_COW_MILK_EXCLUDES = (
    "almond",
    "banana",
    "butter",
    "caramel",
    "cheese",
    "chocolate",
    "cocoa",
    "coconut",
    "coffee",
    "condensed",
    "creamer",
    "cream",
    "evaporated",
    "flavor",
    "flavored",
    "ice",
    "mix",
    "oat",
    "powder",
    "protein",
    "shake",
    "smoothie",
    "soy",
    "strawberry",
    "vanilla",
    "yogurt",
    "yoghurt",
)


def make_plain_cow_milk_contract(esha_code: str, esha_description: str, fat_style: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("milk"):
            return reject(f"{esha_code} category mismatch")
        if "milk" not in product.description_tokens:
            return reject(f"{esha_code} missing milk identity")
        if any(term in product.description_tokens for term in PLAIN_COW_MILK_EXCLUDES):
            return reject(f"{esha_code} excluded flavored milk subtype")
        raw = product.description.lower()
        if any(bad in raw for bad in ("1/2", "1 1/2", "1½")):
            return reject(f"{esha_code} excluded fractional-fat subtype")
        if fat_style == "whole":
            if not (
                product.has_phrase("whole milk")
                or product.has_all("whole", "milk")
                or product.has_phrase("vitamin d milk")
            ):
                return reject(f"{esha_code} missing whole-milk identity")
            if product.has_any("1", "2", "skim", "nonfat") or product.has_phrase("low fat") or product.has_phrase("lowfat") or product.has_phrase("fat free") or product.has_phrase("reduced fat"):
                return reject(f"{esha_code} excluded lower-fat subtype")
            return accept(f"{esha_code} reviewed contract accepted")
        if fat_style == "two_percent":
            if not (
                "2%" in raw
                or "2 percent" in raw
                or product.has_phrase("reduced fat milk")
                or product.has_phrase("reduced milkfat")
            ):
                return reject(f"{esha_code} missing 2-percent identity")
            if product.has_any("whole", "skim", "nonfat") or product.has_phrase("fat free"):
                return reject(f"{esha_code} excluded non-2-percent subtype")
            return accept(f"{esha_code} reviewed contract accepted")
        if fat_style == "one_percent":
            if not (
                "1%" in raw
                or "1 percent" in raw
                or product.has_phrase("lowfat milk")
                or product.has_phrase("low fat milk")
            ):
                return reject(f"{esha_code} missing 1-percent identity")
            if product.has_any("whole", "skim", "nonfat", "2") or product.has_phrase("fat free") or product.has_phrase("reduced fat"):
                return reject(f"{esha_code} excluded non-1-percent subtype")
            return accept(f"{esha_code} reviewed contract accepted")
        return reject(f"{esha_code} unsupported milk fat style")

    return contract


def make_skim_milk_dry_mix_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("milk", "milk additives"):
            return reject(f"{esha_code} category mismatch")
        if not (product.has_any("milk") or product.ingredients_have_any("milk")):
            return reject(f"{esha_code} missing milk identity")
        if not (product.has_any("skim", "nonfat") or product.ingredients_have_any("skim", "nonfat")):
            return reject(f"{esha_code} missing skim identity")
        if not (
            product.has_any("mix", "instant", "powder")
            or product.ingredients_have_any("powder")
        ):
            return reject(f"{esha_code} missing dry-mix signal")
        if product.has_any(
            "chocolate",
            "cocoa",
            "coffee",
            "latte",
            "cappuccino",
            "tea",
            "protein",
            "shake",
            "smoothie",
            "vanilla",
            "strawberry",
            "caramel",
            "coconut",
            "almond",
            "soy",
            "oat",
        ):
            return reject(f"{esha_code} excluded flavored beverage")
        if product.ingredients_have_any("cocoa", "coffee", "tea", "coconut", "almond", "soy", "oat"):
            return reject(f"{esha_code} excluded flavored beverage ingredient")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_focus_water_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("water"):
            return reject(f"{esha_code} category mismatch")
        if not (
            (product.has_any("focus") and product.has_any("water"))
            or product.has_phrase("focus functional energy water beverage")
            or product.has_phrase("focus water beverage")
        ):
            return reject(f"{esha_code} missing focus-water identity")
        if product.has_any("enhancer", "powder", "protein", "tea"):
            return reject(f"{esha_code} excluded non-water subtype")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_sparkling_water_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("water"):
            return reject(f"{esha_code} category mismatch")
        if not (
            product.has_phrase("sparkling water")
            or (product.has_any("sparkling") and product.has_any("water"))
            or product.has_phrase("seltzer water")
        ):
            return reject(f"{esha_code} missing sparkling-water identity")
        if product.has_any("enhancer", "powder", "protein", "tea", "juice") or product.has_phrase("lemonade"):
            return reject(f"{esha_code} excluded non-water subtype")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_stur_water_enhancer_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("liquid water enhancer"):
            return reject(f"{esha_code} category mismatch")
        if "stur" not in product.description_tokens:
            return reject(f"{esha_code} missing stur identity")
        if not (product.has_phrase("water enhancer") or product.has_phrase("liquid water enhancer")):
            return reject(f"{esha_code} missing water-enhancer identity")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_rice_milk_vanilla_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("plant based milk", "other drinks", "milk additives", "powdered drinks"):
            return reject(f"{esha_code} category mismatch")
        has_rice_milk = (
            product.has_phrase("rice milk")
            or (product.has_any("rice") and product.has_any("milk"))
            or (product.ingredients_have_any("rice") and product.ingredients_have_any("milk"))
        )
        if not has_rice_milk:
            return reject(f"{esha_code} missing rice-milk identity")
        if not (product.has_any("vanilla") or product.ingredients_have_any("vanilla")):
            return reject(f"{esha_code} missing vanilla identity")
        if product.has_any(
            "chocolate",
            "cocoa",
            "candy",
            "bar",
            "bars",
            "cake",
            "cakes",
            "cookie",
            "cookies",
            "crisp",
            "crisped",
            "fudge",
            "sandwich",
            "shake",
            "horchata",
            "cinnamon",
        ):
            return reject(f"{esha_code} excluded rice-milk subtype")
        if product.ingredients_have_any("cocoa", "chocolate", "coffee"):
            return reject(f"{esha_code} excluded rice-milk ingredient")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_original_frozen_pancake_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("frozen pancakes", "pancakes", "waffles", "french toast", "crepes"):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any("pancake", "pancakes"):
            return reject(f"{esha_code} missing pancake identity")
        if product.has_any("potato", "scallion", "korean", "kimchi", "veggie", "vegetable", "apple", "berry", "blueberry", "banana", "chocolate", "flavor", "flavored", "vanilla", "wildberry", "stuffed"):
            return reject(f"{esha_code} excluded flavored pancake subtype")
        if product.has_any("dutch", "danish"):
            return reject(f"{esha_code} excluded specialty pancake subtype")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_original_frozen_waffle_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("frozen pancakes", "pancakes", "waffles", "french toast", "crepes"):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any("waffle", "waffles"):
            return reject(f"{esha_code} missing waffle identity")
        if product.has_any("apple", "banana", "berry", "birthday", "blueberry", "cake", "cherry", "chicken", "cinnamon", "chocolate", "filled", "flavor", "flavored", "gluten", "maple", "paleo", "power", "protein", "strawberry", "vanilla", "bacon", "sausage"):
            return reject(f"{esha_code} excluded flavored waffle subtype")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_frozen_waffle_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("frozen pancakes", "pancakes", "waffles", "french toast", "crepes"):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any("waffle", "waffles"):
            return reject(f"{esha_code} missing waffle identity")
        if product.has_any("cone", "cones", "ice", "cream", "sundae", "dessert", "bowl"):
            return reject(f"{esha_code} excluded dessert subtype")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_blueberry_frozen_waffle_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("frozen pancakes", "pancakes", "waffles", "french toast", "crepes"):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any("waffle", "waffles"):
            return reject(f"{esha_code} missing waffle identity")
        if "blueberry" not in product.description_tokens:
            return reject(f"{esha_code} missing blueberry identity")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_frozen_buttermilk_pancake_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("frozen pancakes", "pancakes", "waffles", "french toast", "crepes"):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any("pancake", "pancakes"):
            return reject(f"{esha_code} missing pancake identity")
        if "buttermilk" not in product.description_tokens:
            return reject(f"{esha_code} missing buttermilk identity")
        if product.has_any("blueberry", "chocolate", "maple", "potato", "berry", "apple", "banana"):
            return reject(f"{esha_code} excluded flavored pancake subtype")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_frozen_blueberry_pancake_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("frozen pancakes", "pancakes", "waffles", "french toast", "crepes"):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any("pancake", "pancakes"):
            return reject(f"{esha_code} missing pancake identity")
        if "blueberry" not in product.description_tokens:
            return reject(f"{esha_code} missing blueberry identity")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_tempeh_original_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("other meats", "vegetable based", "vegetarian frozen meats"):
            return reject(f"{esha_code} category mismatch")
        if "tempeh" not in product.description_tokens:
            return reject(f"{esha_code} missing tempeh identity")
        if "original" not in product.description_tokens:
            return reject(f"{esha_code} missing original identity")
        if product.has_any("starter", "buffalo", "bacon", "curry", "grain", "flax", "black", "chickpea", "quinoa", "cake"):
            return reject(f"{esha_code} excluded tempeh subtype")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_vanilla_ready_drink_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("other drinks", "non alcoholic beverages", "drinks flavoured"):
            return reject(f"{esha_code} category mismatch")
        if "vanilla" not in product.description_tokens:
            return reject(f"{esha_code} missing vanilla identity")
        if not (
            product.has_phrase("vanilla drink")
            or product.has_phrase("drink vanilla")
            or product.has_phrase("vanilla beverage")
            or product.has_phrase("very vanilla")
        ):
            return reject(f"{esha_code} missing drink identity")
        if product.has_any(
            "almond",
            "balanced",
            "bean",
            "berry",
            "blackberry",
            "blueberry",
            "brew",
            "cappuccino",
            "cashew",
            "chai",
            "cherry",
            "cinnamon",
            "classic",
            "coffee",
            "cold",
            "coconut",
            "cream",
            "creamy",
            "dairy",
            "earl",
            "energy",
            "enhanced",
            "enriched",
            "espresso",
            "grey",
            "horchata",
            "iced",
            "irish",
            "keto",
            "latte",
            "moss",
            "nutritional",
            "orange",
            "oat",
            "plant",
            "probiotic",
            "protein",
            "rice",
            "sleep",
            "shake",
            "seltzer",
            "smoothie",
            "soda",
            "soy",
            "strawberry",
            "tea",
            "turmeric",
            "yogurt",
        ):
            return reject(f"{esha_code} excluded vanilla drink subtype")
        if product.ingredients_have_any(
            "almond",
            "cashew",
            "coffee",
            "coconut",
            "oat",
            "pea",
            "protein",
            "rice",
            "tea",
            "turmeric",
        ):
            return reject(f"{esha_code} excluded vanilla drink ingredient")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_seltzer_water_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("water", "drink", "beverage"):
            return reject(f"{esha_code} category mismatch")
        if "seltzer" not in product.description_tokens:
            return reject(f"{esha_code} missing required term(s): seltzer")
        if product.has_any("club", "tonic"):
            return reject(f"{esha_code} excluded seltzer subtype")
        if product.has_any("juice", "lemonade", "maple", "punch", "sap"):
            return reject(f"{esha_code} excluded seltzer subtype")
        if product.ingredients_have_any("juice", "quinine", "sugar", "sweetener", "maple", "sap"):
            return reject(f"{esha_code} excluded seltzer ingredient")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_cheddar_cheese_sauce_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not (product.has_any("cheddar") and product.has_any("sauce")):
            return reject(f"{esha_code} missing cheddar-sauce identity")
        if product.has_any(
            "alternative",
            "cheez",
            "dinner",
            "elbow",
            "frozen",
            "helper",
            "mac",
            "macaroni",
            "meal",
            "noodle",
            "noodles",
            "pasta",
            "ravioli",
            "rice",
            "shell",
            "shells",
            "spaghetti",
            "style",
            "tortellini",
            "vegetable",
            "vegan",
            "veggie",
        ):
            return reject(f"{esha_code} excluded prepared food")
        if product.has_phrase("no dairy") or product.has_phrase("plant based") or product.has_phrase("plant-based"):
            return reject(f"{esha_code} excluded non-dairy cheddar sauce")
        if product.category_has_any("pasta dinner", "prepared side", "frozen", "vegetable", "meal", "dinner"):
            return reject(f"{esha_code} category mismatch")
        if product.has_any("mix", "powder") or product.ingredients_have_any("powder"):
            return reject(f"{esha_code} excluded sauce mix")
        if not (
            product.category_has_any("sauce", "condiment", "dip")
            or product.has_phrase("cheddar cheese sauce")
            or product.has_phrase("double cheddar sauce")
            or product.has_phrase("aged cheddar cheese sauce")
            or product.has_phrase("sharp cheddar cheese sauce")
        ):
            return reject(f"{esha_code} category mismatch")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_grated_parmesan_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("cheese"):
            return reject(f"{esha_code} category mismatch")
        if not (product.has_any("parmesan") and product.has_any("cheese")):
            return reject(f"{esha_code} missing parmesan-cheese identity")
        if not product.has_any("grated"):
            return reject(f"{esha_code} missing grated form")
        if product.has_any(
            "alternative",
            "asiago",
            "blend",
            "cotija",
            "four",
            "garlic",
            "herb",
            "mexican",
            "mozzarella",
            "other",
            "pizza",
            "pasta",
            "ravioli",
            "ricotta",
            "romano",
            "tortellini",
            "sauce",
            "soup",
            "style",
            "toast",
            "cracker",
            "dip",
            "bread",
        ):
            return reject(f"{esha_code} excluded prepared food")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def _cheddar_base_reject(product: ProductFacts, esha_code: str) -> MatchDecision | None:
    if not product.category_has_any("cheese", "dairy"):
        return reject(f"{esha_code} category mismatch")
    if "cheddar" not in product.description_tokens:
        return reject(f"{esha_code} missing cheddar identity")
    excluded = [term for term in CHEDDAR_EXCLUDES if term in product.description_tokens]
    if excluded:
        return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
    excluded_phrases = [
        phrase
        for phrase in ("mac cheese", "mac & cheese", "macaroni and cheese", "macaroni cheese")
        if product.has_phrase(phrase)
    ]
    if excluded_phrases:
        return reject(f"{esha_code} excluded phrase(s): " + "|".join(excluded_phrases))
    dairy_alt_phrases = [
        phrase
        for phrase in ("plant based", "plant-based", "non dairy", "non-dairy", "dairy free", "dairy-free")
        if product.has_phrase(phrase)
    ]
    if dairy_alt_phrases:
        return reject(f"{esha_code} excluded phrase(s): " + "|".join(dairy_alt_phrases))
    return None


def make_cheddar_variant_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...] = (),
    required_any_terms: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        base_reject = _cheddar_base_reject(product, esha_code)
        if base_reject:
            return base_reject
        missing = [term for term in required_terms if term not in product.description_tokens]
        if missing:
            return reject(f"{esha_code} missing required term(s): " + "|".join(missing))
        if required_any_terms and not any(term in product.description_tokens for term in required_any_terms):
            return reject(f"{esha_code} missing required term(s): " + "|".join(required_any_terms))
        excluded = [term for term in exclude_terms if term in product.description_tokens]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed cheddar contract accepted")

    return contract


def make_infant_green_bean_potato_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not (product.category_has_any("baby", "infant") or product.has_any("baby", "infant")):
            return reject(f"{esha_code} category mismatch")
        has_green_bean = (
            product.has_phrase("green bean")
            or product.has_phrase("green beans")
            or (
                "green" in product.description_tokens
                and "bean" in product.description_tokens
            )
            or product.ingredients_have_phrase("green bean")
            or product.ingredients_have_phrase("green beans")
        )
        if not has_green_bean:
            return reject(f"{esha_code} missing green-bean identity")
        if not (
            "potato" in product.description_tokens
            or "potatoes" in product.description_tokens
            or product.ingredients_have_any("potato", "potatoes", "sweetpotato", "sweetpotatoes")
        ):
            return reject(f"{esha_code} missing potato identity")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_wild_rice_pancake_mix_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("cake", "cookie", "cupcake", "bread", "muffin", "mix"):
            return reject(f"{esha_code} category mismatch")
        has_pancake_mix = (
            product.has_any("pancake", "pancakes")
            or product.has_phrase("pancake mix")
            or product.has_phrase("pancake and waffle mix")
            or product.has_phrase("pancake & waffle mix")
        )
        if not has_pancake_mix:
            return reject(f"{esha_code} missing pancake identity")
        if not (product.has_any("wild") and product.has_any("rice")):
            return reject(f"{esha_code} missing wild-rice identity")
        if not product.has_any("mix"):
            return reject(f"{esha_code} missing mix identity")
        if product.has_any("soup", "stuffing", "pilaf", "meal"):
            return reject(f"{esha_code} excluded meal subtype")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_ten_grain_waffle_mix_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("cake", "cookie", "cupcake", "bread", "muffin", "mix"):
            return reject(f"{esha_code} category mismatch")
        has_waffle_mix = (
            product.has_any("waffle", "waffles")
            or product.has_phrase("waffle mix")
            or product.has_phrase("pancake and waffle mix")
            or product.has_phrase("pancake & waffle mix")
        )
        if not has_waffle_mix:
            return reject(f"{esha_code} missing waffle identity")
        if "grain" not in product.description_tokens:
            return reject(f"{esha_code} missing grain identity")
        if not (product.has_phrase("10 grain") or product.has_phrase("ten grain")):
            return reject(f"{esha_code} missing 10-grain identity")
        if not product.has_any("mix"):
            return reject(f"{esha_code} missing mix identity")
        if product.has_any("cookie", "cupcake", "cake", "brownie", "free") or product.has_phrase("grain free"):
            return reject(f"{esha_code} excluded baked-dessert subtype")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_agra_peas_greens_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("prepared", "entree", "side", "other deli"):
            return reject(f"{esha_code} category mismatch")
        has_identity = (
            product.has_any("agra")
            or product.has_phrase("peas and greens")
            or product.has_phrase("peas & greens")
        )
        if not has_identity:
            return reject(f"{esha_code} missing agra/peas-and-greens identity")
        if product.has_phrase("green peas") or product.has_phrase("green bean"):
            return reject(f"{esha_code} excluded plain vegetable subtype")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_spicy_tempeh_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("other meats", "vegetarian frozen meats", "vegetable based"):
            return reject(f"{esha_code} category mismatch")
        if not (product.has_any("tempeh") or product.ingredients_have_any("tempeh")):
            return reject(f"{esha_code} missing tempeh identity")
        if not (
            product.has_any("spicy", "hot", "buffalo", "jalapeno", "chili", "chile", "sriracha")
            or product.has_phrase("hot and spicy")
        ):
            return reject(f"{esha_code} missing spicy identity")
        if product.has_any(
            "burger",
            "burgers",
            "patty",
            "patties",
            "sausage",
            "breakfast",
            "pollock",
            "beef",
            "chicken",
            "wrap",
            "burrito",
            "juice",
            "soup",
            "puffs",
            "straws",
        ):
            return reject(f"{esha_code} excluded non-tempeh subtype")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def make_vegetarian_jerky_original_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("snack", "jerky"):
            return reject(f"{esha_code} category mismatch")
        if not (
            product.has_any("jerky", "jurky")
            or product.has_phrase("vegan jerky")
            or product.has_phrase("vegetarian jerky")
            or product.has_phrase("meatless vegan jerky")
        ):
            return reject(f"{esha_code} missing jerky identity")
        if not (
            product.has_any("vegetarian", "vegan", "meatless")
            or product.has_phrase("plant based")
            or product.has_phrase("plant-based")
        ):
            return reject(f"{esha_code} missing vegetarian identity")
        if "original" not in product.description_tokens:
            return reject(f"{esha_code} missing original identity")
        if product.has_any(
            "barbecue",
            "bbq",
            "chipotle",
            "cracked",
            "habanero",
            "hickory",
            "lime",
            "mesquite",
            "pepper",
            "pineapple",
            "smoked",
            "smoky",
            "teriyaki",
            "thai",
        ):
            return reject(f"{esha_code} excluded flavored jerky subtype")
        if product.has_any("beef", "chicken", "pork", "burger", "sausage", "chorizo", "meatball", "chili"):
            return reject(f"{esha_code} excluded meat alternative subtype")
        return accept(f"{esha_code} reviewed contract accepted")

    return contract


def baked_bean_decision(product: ProductFacts, esha_code: str, esha_description: str) -> MatchDecision:
    spec = ContractSpec(
        esha_code=esha_code,
        esha_description=esha_description,
        allowed_categories=BEAN_CATEGORIES,
        search_terms=("baked", "bean"),
        required_terms=("baked", "bean"),
        exclude_terms=(
            "lima",
            "kidney",
            "black",
            "pinto",
            "navy",
            "garbanzo",
            "chickpea",
            "refried",
            "green",
            "snap",
            "string",
            "wax",
            "espresso",
            "coffee",
        ),
    )
    return match_spec(product, spec)


def match_esha_0007037(product: ProductFacts) -> MatchDecision:
    return baked_bean_decision(product, "7037", "Baked Beans, prepared from recipe")


def match_esha_0009259(product: ProductFacts) -> MatchDecision:
    spec = ContractSpec(
        esha_code="9259",
        esha_description="Beans, pinto, canned",
        allowed_categories=BEAN_CATEGORIES,
        search_terms=("pinto", "bean", "canned"),
        required_terms=("pinto", "bean"),
        exclude_terms=PINTO_BASE_EXCLUDES,
    )
    return match_spec(product, spec)


def match_esha_0041762(product: ProductFacts) -> MatchDecision:
    spec = ContractSpec(
        esha_code="41762",
        esha_description="Beans, pinto, whole, canned",
        allowed_categories=BEAN_CATEGORIES,
        search_terms=("whole", "pinto", "bean", "canned"),
        required_terms=("whole", "pinto", "bean"),
        exclude_terms=PINTO_BASE_EXCLUDES,
    )
    return match_spec(product, spec)


def match_esha_0009740(product: ProductFacts) -> MatchDecision:
    spec = ContractSpec(
        esha_code="9740",
        esha_description="Refried Beans, pinto, canned",
        allowed_categories=BEAN_CATEGORIES,
        search_terms=("refried", "pinto", "bean", "canned"),
        required_terms=("refried", "pinto", "bean"),
        exclude_terms=REFRIED_PINTO_EXCLUDES,
    )
    return match_spec(product, spec)


def match_esha_0009741(product: ProductFacts) -> MatchDecision:
    spec = ContractSpec(
        esha_code="9741",
        esha_description="Refried Beans, spicy pinto, canned",
        allowed_categories=BEAN_CATEGORIES,
        search_terms=("refried", "spicy", "pinto", "bean", "canned"),
        required_terms=("refried", "spicy", "pinto", "bean"),
        exclude_terms=REFRIED_PINTO_EXCLUDES,
    )
    return match_spec(product, spec)


def match_esha_0045829(product: ProductFacts) -> MatchDecision:
    spec = ContractSpec(
        esha_code="45829",
        esha_description="Beans, pinto, with jalapeno peppers, canned",
        allowed_categories=BEAN_CATEGORIES,
        search_terms=("pinto", "bean", "jalapeno", "canned"),
        required_terms=("pinto", "bean", "jalapeno"),
        exclude_terms=PINTO_BASE_EXCLUDES,
    )
    return match_spec(product, spec)


def match_esha_0045831(product: ProductFacts) -> MatchDecision:
    spec = ContractSpec(
        esha_code="45831",
        esha_description="Beans, pinto, with chopped sweet onion, canned",
        allowed_categories=BEAN_CATEGORIES,
        search_terms=("pinto", "bean", "onion", "canned"),
        required_terms=("pinto", "bean", "onion"),
        exclude_terms=PINTO_BASE_EXCLUDES,
    )
    return match_spec(product, spec)


def match_esha_0027335(product: ProductFacts) -> MatchDecision:
    spec = ContractSpec(
        esha_code="27335",
        esha_description="Beans, pinto",
        allowed_categories=BEAN_CATEGORIES,
        search_terms=("pinto", "bean"),
        required_terms=("pinto", "bean"),
        exclude_terms=PINTO_BASE_EXCLUDES,
    )
    return match_spec(product, spec)


def make_green_bean_casserole_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        spec = ContractSpec(
            esha_code=esha_code,
            esha_description=esha_description,
            allowed_categories=("vegetable", "prepared", "processed", "meal", "side", "frozen", "canned"),
            search_terms=("green", "bean", "casserole"),
            required_terms=("green", "bean", "casserole"),
            exclude_terms=("whole", "plain", "snap", "string", "wax", "almondine"),
        )
        return match_spec(product, spec)

    return contract


def make_green_bean_plain_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        spec = ContractSpec(
            esha_code=esha_code,
            esha_description=esha_description,
            allowed_categories=("vegetable", "vegetables", "canned", "frozen", "produce", "prepared", "processed"),
            search_terms=("green", "bean"),
            required_terms=("green", "bean"),
            exclude_terms=PREPARED_DISH_TERMS,
        )
        return match_spec(product, spec)

    return contract


def make_mayonnaise_plain_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not has_mayo(product):
            return reject(f"{esha_code} missing mayonnaise/mayo cue")
        spec = ContractSpec(
            esha_code=esha_code,
            esha_description=esha_description,
            allowed_categories=("condiment", "sauce", "dressing", "mayonnaise", "mayo"),
            search_terms=("mayonnaise", "mayo"),
            required_terms=(),
            exclude_terms=MAYONNAISE_FLAVOR_EXCLUDES,
        )
        return match_spec(product, spec)

    return contract


def match_esha_0022937(product: ProductFacts) -> MatchDecision:
    if not has_mayo(product):
        return reject("22937 missing mayonnaise/mayo cue")
    excludes = tuple(
        term
        for term in MAYONNAISE_FLAVOR_EXCLUDES
        if term not in {"chipotle", "lime", "sandwich"}
    )
    spec = ContractSpec(
        esha_code="22937",
        esha_description="Dressing, mayonnaise, chipotle",
        allowed_categories=("condiment", "sauce", "dressing", "mayonnaise", "mayo"),
        search_terms=("chipotle", "mayonnaise"),
        required_terms=("chipotle",),
        exclude_terms=excludes,
    )
    return match_spec(product, spec)


def make_cheddar_cheese_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        spec = ContractSpec(
            esha_code=esha_code,
            esha_description=esha_description,
            allowed_categories=("cheese", "dairy"),
            search_terms=("cheddar", "cheese"),
            required_terms=("cheddar",),
            exclude_terms=CHEDDAR_EXCLUDES,
            exclude_phrases=("mac cheese", "mac & cheese", "macaroni and cheese", "macaroni cheese"),
        )
        return match_spec(product, spec)

    return contract


def hash_brown_decision(product: ProductFacts, esha_code: str, esha_description: str) -> MatchDecision:
    hash_brown = (
        product.has_all("hash", "brown")
        or product.has_any("hashbrown", "hashbrowns")
        or product.has_phrase("hash brown")
        or product.has_phrase("hash browns")
    )
    if not hash_brown:
        return reject(f"{esha_code} missing hash brown cue")
    spec = ContractSpec(
        esha_code=esha_code,
        esha_description=esha_description,
        allowed_categories=("potato", "potatoes", "vegetable", "frozen", "prepared", "processed"),
        search_terms=("hash", "brown", "potato"),
        required_terms=(),
        exclude_terms=HASH_BROWN_EXCLUDES,
    )
    return match_spec(product, spec)


def make_hash_brown_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        return hash_brown_decision(product, esha_code, esha_description)

    return contract


def make_sliced_potato_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not has_potato(product):
            return reject(f"{esha_code} missing potato cue")
        spec = ContractSpec(
            esha_code=esha_code,
            esha_description=esha_description,
            allowed_categories=("potato", "potatoes", "vegetable", "canned", "frozen", "prepared", "processed"),
            search_terms=("sliced", "potato"),
            required_terms=(),
            exclude_terms=SLICED_POTATO_EXCLUDES,
            required_phrases=("sliced potato",),
        )
        return match_spec(product, spec)

    return contract


BAKED_BEAN_CONTRACTS = {
    "7449": "Baked Beans, with sorghum & mustard, fat free, canned",
    "7462": "Baked Beans, brown sugar & bacon, canned",
    "7037": "Baked Beans, prepared from recipe",
    "7038": "Baked Beans, vegetarian, canned",
    "7039": "Baked Beans, with beef, canned",
    "7040": "Baked Beans, with pork, canned",
    "7139": "Baked Beans, barbecue",
    "7825": "Baked Beans, sweet bacon, canned",
    "7832": "Baked Beans, brick oven style, canned",
    "7833": "Baked Beans, honey mustard, canned",
    "7834": "Baked Beans, maple sugar, canned",
    "9308": "Baked Beans, vegetarian, with tomato sauce, canned",
    "9900": "Baked Beans, original, 8 ounce, canned",
    "9901": "Baked Beans, vegetarian, 16 ounce, canned",
    "9902": "Baked Beans, vegetarian, 28 ounce, canned",
    "9903": "Baked Beans, barbecue, 28 ounce, canned",
    "25278": "Baked Beans, with bacon & onion, canned",
    "27301": "Baked Beans",
    "39855": "Baked Beans, plain, canned",
    "48614": "Baked Beans, hickory & bacon, canned",
    "48615": "Baked Beans, homestyle, canned",
    "48616": "Baked Beans, original, canned",
    "41175": "Dish, chicken, cookout, with baked beans",
    "48989": "Baked Beans, canned",
    "56101": "Baked Beans, with franks, canned",
    "92132": "Baked Beans, unsalted, canned",
    "57054": "Baked Beans, vegetarian, 8 ounce, canned",
    "57056": "Baked Beans, barbecue, 16 ounce, canned",
    "91531": "Baked Beans, Boston recipe, canned",
    "91533": "Baked Beans, onion, canned",
    "91535": "Baked Beans, bold & spicy, canned",
    "91536": "Baked Beans, barbecue, canned",
    "91537": "Baked Beans, maple cured bacon, canned",
    "91538": "Baked Beans, country style, canned",
}

GREEN_BEAN_CASSEROLE_CONTRACTS = {
    "330": "Casserole, green bean",
    "1135": "Green Bean Casserole",
}

GREEN_BEAN_PLAIN_CONTRACTS = {
    "7287": "Beans, green, canned",
    "7288": "Beans, green, cooked",
    "7289": "Beans, green, frozen",
    "7290": "Beans, green, raw",
    "9121": "Beans, snap, green, cooked",
    "9122": "Beans, snap, green, canned",
    "9123": "Beans, snap, green, frozen",
    "9124": "Beans, snap, green, raw",
    "11404": "Beans, green, no salt added, canned",
    "11405": "Beans, green, cut, canned",
    "11406": "Beans, green, French style, canned",
    "11407": "Beans, green, whole, canned",
    "11408": "Beans, green, frozen, cooked",
    "11409": "Beans, green, frozen, cooked with salt",
    "11410": "Beans, green, canned, drained",
}

MAYONNAISE_PLAIN_CONTRACTS = {
    "8021": "Dressing, mayonnaise type",
    "8032": "Mayonnaise, regular",
    "8046": "Dressing, mayonnaise",
    "8069": "Mayonnaise, reduced calorie",
    "8122": "Mayonnaise, fat free",
    "8145": "Mayonnaise, light",
    "8149": "Mayonnaise, low sodium",
    "8203": "Mayonnaise, soybean oil",
    "8204": "Mayonnaise, canola oil",
    "8205": "Mayonnaise, olive oil",
    "8230": "Mayonnaise, regular, with salt",
    "8231": "Mayonnaise, regular, without salt",
    "8258": "Mayonnaise, reduced fat",
    "8501": "Mayonnaise",
    "8503": "Mayonnaise, cholesterol free",
    "24581": "Mayonnaise, store brand",
}

CHEDDAR_CHEESE_CONTRACTS = {
    "633": "Cheese, cheddar, mild",
    "634": "Cheese, cheddar, medium, 1\"",
    "635": "Cheese, cheddar, sharp, 1\"",
    "636": "Cheese, cheddar, extra sharp, 1\"",
    "1007": "Cheese, cheddar, diced",
    "1008": "Cheese, cheddar, shredded",
    "1280": "Cheese, cheddar, medium",
    "1522": "Cheese, cheddar, 1\" cube",
    "33342": "Cheese, cheddar",
    "47800": "Cheese, cheddar, mild",
    "47805": "Cheese, cheddar, extra sharp",
    "47809": "Cheese, cheddar, sharp",
}

HASH_BROWN_CONTRACTS = {
    "9560": "Hash Browns",
    "1124": "Potatoes, hash brown",
    "9657": "Potatoes, hash brown, frozen",
    "5140": "Potatoes, hash brown, cooked",
    "5141": "Potatoes, hash brown, frozen, cooked",
    "5273": "Potatoes, hash brown, patty",
    "5463": "Potatoes, hash brown, shredded",
    "5589": "Potatoes, hash brown, restaurant",
    "6155": "Hash Browns",
    "6401": "Potatoes, hash brown, with salt",
    "6402": "Potatoes, hash brown, without salt",
}

SLICED_POTATO_CONTRACTS = {
    "57363": "Potatoes, sliced, canned",
    "57364": "Potatoes, sliced, canned, drained",
}

ANIMAL_MILK_CONTRACTS = {
    "23": ("Milk, goat, with added vitamin D milk", "goat"),
    "42": ("Milk, sheep", "sheep"),
}

STRICT_CONTRACT_OVERRIDES = {
    "1": make_plain_cow_milk_contract("1", "Milk, whole, 3.25%, with added vitamin D", "whole"),
    "2": make_plain_cow_milk_contract("2", "Milk, 2%, with added vitamin A & D", "two_percent"),
    "4": make_plain_cow_milk_contract("4", "Milk, 1%, with added vitamin A & D", "one_percent"),
    "43": make_carob_dry_mix_contract("43", "Drink, carob, dry mix"),
    "52": make_low_sodium_milk_contract("52", "Milk, low sodium"),
    "67": make_skim_milk_dry_mix_contract("67", "Milk, nonfat/skim, with o added vitamin A & D, dry mix"),
    "615": make_rice_milk_vanilla_contract("615", "Rice Milk, vanilla"),
    "618": make_vanilla_ready_drink_contract("618", "Drink, vanilla, ready to drink package"),
    "633": make_cheddar_variant_contract("633", "Cheese, cheddar, mild", required_terms=("mild",)),
    "1008": make_cheddar_variant_contract(
        "1008",
        "Cheese, cheddar, shredded",
        required_any_terms=("shredded", "shred", "shreds"),
        exclude_terms=("slice", "sliced", "stick", "sticks", "twist", "twists", "cube", "cubed", "diced"),
    ),
    "1280": make_cheddar_variant_contract("1280", "Cheese, cheddar, medium", required_terms=("medium",)),
    "33342": make_cheddar_variant_contract("33342", "Cheese, cheddar", exclude_terms=("mild", "medium", "sharp", "extra")),
    "635": make_cheddar_variant_contract("635", "Cheese, cheddar, sharp, 1\"", required_terms=("sharp",), exclude_terms=("extra",)),
    "636": make_cheddar_variant_contract("636", "Cheese, cheddar, extra sharp, 1\"", required_terms=("extra", "sharp")),
    "4791": make_seltzer_water_contract("4791", "Water, seltzer"),
    "9558": make_cheddar_cheese_sauce_contract("9558", "Sauce, cheese, cheddar, ready to serve"),
    "1075": make_grated_parmesan_contract("1075", "Cheese, parmesan, grated"),
    "436": make_infant_green_bean_potato_contract("436", "Infant Vegetable, green bean potato"),
    "16477": make_agra_peas_greens_contract("16477", "Dish, Agra peas & greens"),
    "16514": make_spicy_tempeh_contract("16514", "Tempeh, spicy veggie"),
    "16515": make_vegetarian_jerky_original_contract("16515", "Vegetarian Meat, Jurky, original"),
    "12470": make_frozen_waffle_contract("12470", "Waffles, frozen"),
    "16642": make_original_frozen_pancake_contract("16642", "Pancakes, original, frozen"),
    "16643": make_frozen_buttermilk_pancake_contract("16643", "Pancakes, buttermilk, frozen"),
    "16646": make_frozen_blueberry_pancake_contract("16646", "Pancakes, blueberry, frozen"),
    "16693": make_wild_rice_pancake_mix_contract("16693", "Pancakes, wild rice, dry mix"),
    "16695": make_ten_grain_waffle_mix_contract("16695", "Waffles, 10 grain, quick, dry mix"),
    "37261": make_focus_water_contract("37261", "Drink, flavored water, focus"),
    "37281": make_stur_water_enhancer_contract("37281", "Drink, flavored water, stur-D"),
    "37282": make_sparkling_water_contract("37282", "Drink, flavored water, spark"),
    "45213": make_original_frozen_waffle_contract("45213", "Waffles, original, frozen"),
    "52742": make_blueberry_frozen_waffle_contract("52742", "Waffles, blueberry"),
    "91243": make_tempeh_original_contract("91243", "Tempeh, original"),
}


def make_baked_bean_contract(esha_code: str, esha_description: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        return baked_bean_decision(product, esha_code, esha_description)

    return contract


CONTRACTS: dict[str, ContractFn] = {
    "7037": match_esha_0007037,
    "9259": match_esha_0009259,
    "41762": match_esha_0041762,
    "9740": match_esha_0009740,
    "9741": match_esha_0009741,
    "45829": match_esha_0045829,
    "45831": match_esha_0045831,
    "27335": match_esha_0027335,
    "22937": match_esha_0022937,
}
CONTRACT_SOURCES: dict[str, str] = {code: __name__ for code in CONTRACTS}

for _code, _description in BAKED_BEAN_CONTRACTS.items():
    CONTRACTS.setdefault(_code, make_baked_bean_contract(_code, _description))
    CONTRACT_SOURCES.setdefault(_code, __name__)
for _code, _description in GREEN_BEAN_CASSEROLE_CONTRACTS.items():
    CONTRACTS.setdefault(_code, make_green_bean_casserole_contract(_code, _description))
    CONTRACT_SOURCES.setdefault(_code, __name__)
for _code, _description in GREEN_BEAN_PLAIN_CONTRACTS.items():
    CONTRACTS.setdefault(_code, make_green_bean_plain_contract(_code, _description))
    CONTRACT_SOURCES.setdefault(_code, __name__)
for _code, _description in MAYONNAISE_PLAIN_CONTRACTS.items():
    CONTRACTS.setdefault(_code, make_mayonnaise_plain_contract(_code, _description))
    CONTRACT_SOURCES.setdefault(_code, __name__)
for _code, _description in CHEDDAR_CHEESE_CONTRACTS.items():
    CONTRACTS.setdefault(_code, make_cheddar_cheese_contract(_code, _description))
    CONTRACT_SOURCES.setdefault(_code, __name__)
for _code, _description in HASH_BROWN_CONTRACTS.items():
    CONTRACTS.setdefault(_code, make_hash_brown_contract(_code, _description))
    CONTRACT_SOURCES.setdefault(_code, __name__)
for _code, _description in SLICED_POTATO_CONTRACTS.items():
    CONTRACTS.setdefault(_code, make_sliced_potato_contract(_code, _description))
    CONTRACT_SOURCES.setdefault(_code, __name__)

# Dynamically import reviewed family modules as agents create them.
# Reviewed modules override seed contracts so fixes can land outside this base registry.
import importlib
import pkgutil

for _mod_info in pkgutil.iter_modules(__path__):
    if _mod_info.name.startswith("reviewed_"):
        _mod = importlib.import_module(f".{_mod_info.name}", __package__)
        if hasattr(_mod, "CONTRACTS"):
            for _code, _fn in _mod.CONTRACTS.items():
                CONTRACTS[_code] = _fn
                CONTRACT_SOURCES[_code] = _mod.__name__

for _code, (_description, _species) in ANIMAL_MILK_CONTRACTS.items():
    CONTRACTS[_code] = make_plain_animal_milk_contract(_code, _description, _species)
    CONTRACT_SOURCES[_code] = __name__

for _code, _fn in STRICT_CONTRACT_OVERRIDES.items():
    CONTRACTS[_code] = _fn
    CONTRACT_SOURCES[_code] = __name__


def evaluate(profile_code: str, row: matcher.ProductRow) -> MatchDecision | None:
    contract = CONTRACTS.get(profile_code)
    if not contract:
        return None
    return contract(ProductFacts.from_row(row))


def evaluate_facts(profile_code: str, facts: ProductFacts) -> MatchDecision | None:
    contract = CONTRACTS.get(profile_code)
    if not contract:
        return None
    return contract(facts)


def diagnose(profile_code: str, row: matcher.ProductRow, esha_description: str) -> MatchDecision:
    decision = evaluate(profile_code, row)
    if decision:
        return decision
    return todo(f"TODO contract for ESHA {profile_code}: {esha_description}")


def contract_status(profile_code: str) -> str:
    return "reviewed" if profile_code in CONTRACTS else "todo"


def contract_source_module(profile_code: str) -> str:
    return CONTRACT_SOURCES.get(profile_code, "")
