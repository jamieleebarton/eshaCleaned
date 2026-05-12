from __future__ import annotations

from .contract_base import ContractFn, MatchDecision, ProductFacts, accept, reject


SEASONING_CATEGORIES = ("spice", "seasoning", "salt", "marinade")
BAKING_CATEGORIES = ("baking", "flour", "sugar", "corn meal")
VEGETABLE_CATEGORIES = ("produce", "pre packaged", "vegetable", "vegetables", "fresh")
BEAN_CATEGORIES = ("bean", "beans", "legume", "vegetable", "canned", "bottled", "dried")
NUT_CATEGORIES = ("nut", "seed", "peanut")
MEAT_CATEGORIES = ("bacon", "meat", "pork", "sausage")
CONDIMENT_CATEGORIES = ("condiment", "dip", "salsa", "sauce", "ketchup", "vinegar", "marinade")
OIL_CATEGORIES = ("oil", "spray")
WINE_CATEGORIES = ("wine", "alcohol")
YOGURT_CATEGORIES = ("yogurt", "dairy")
TORTILLA_CATEGORIES = ("tortilla", "flatbread", "bread", "mexican")
DESSERT_TOPPING_CATEGORIES = ("baking decorations", "dessert", "topping")
FROZEN_DESSERT_CATEGORIES = ("ice cream", "frozen yogurt")
SEAFOOD_CATEGORIES = ("seafood", "fish", "shellfish", "frozen")
ALCOHOL_CATEGORIES = ("alcohol", "beer", "wine", "liquor")


def reject_terms(product: ProductFacts, esha_code: str, terms: tuple[str, ...]) -> MatchDecision | None:
    hits = [term for term in terms if product.has_any(term)]
    if hits:
        return reject(f"{esha_code} excluded term(s): " + "|".join(hits))
    return None


def require_category(product: ProductFacts, esha_code: str, categories: tuple[str, ...]) -> MatchDecision | None:
    if not product.category_has_any(*categories):
        return reject(f"{esha_code} category mismatch")
    return None


def make_simple_contract(
    esha_code: str,
    categories: tuple[str, ...],
    required_terms: tuple[str, ...],
    exclude_terms: tuple[str, ...],
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, categories)
        if category_reject:
            return category_reject
        if categories == VEGETABLE_CATEGORIES and product.category_has_any("canned", "frozen", "juice", "oil", "prepared", "processed", "sauce"):
            return reject(f"{esha_code} category state mismatch")
        missing = [term for term in required_terms if not product.has_any(term)]
        if missing:
            return reject(f"{esha_code} missing required term(s): " + "|".join(missing))
        term_reject = reject_terms(product, esha_code, exclude_terms)
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed top2500 head contract accepted")

    return contract


def powdered_sugar_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "45892", BAKING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("sugar"):
        return reject("45892 missing required term(s): sugar")
    if not product.has_any("powdered", "powder", "confectioner", "confectioners"):
        return reject("45892 missing required term(s): powdered")
    term_reject = reject_terms(
        product,
        "45892",
        ("bread", "cookie", "doughnut", "donut", "french", "toast", "frosting", "icing", "sprinkle"),
    )
    if term_reject:
        return term_reject
    return accept("45892 reviewed powdered sugar contract accepted")


def nut_contract(esha_code: str, nut_terms: tuple[str, ...]) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, NUT_CATEGORIES)
        if category_reject:
            return category_reject
        if not any(product.has_any(term) for term in nut_terms):
            return reject(f"{esha_code} missing required term(s): " + "|".join(nut_terms))
        term_reject = reject_terms(
            product,
            esha_code,
            (
                "bar",
                "almond",
                "bite",
                "bites",
                "brazil",
                "brownie",
                "butter",
                "candy",
                "cajun",
                "cashew",
                "chocolate",
                "cinnamon",
                "coffee",
                "cookie",
                "covered",
                "cranberry",
                "glazed",
                "granola",
                "honey",
                "hazelnut",
                "date",
                "mix",
                "mixed",
                "oil",
                "peanut",
                "pie",
                "praline",
                "roasted",
                "salted",
                "spicy",
                "spiced",
                "sweet",
                "sugar",
                "trail",
                "topping",
                "yogurt",
            ),
        )
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed plain nut contract accepted")

    return contract


def tomato_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5169", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("tomato", "tomatoes"):
        return reject("5169 missing required term(s): tomato")
    if product.category_has_any("canned", "frozen", "juice", "oil", "prepared", "processed", "sauce"):
        return reject("5169 category state mismatch")
    term_reject = reject_terms(
        product,
        "5169",
        (
            "basil",
            "canned",
            "cauliflower",
            "clam",
            "cocktail",
            "concentrate",
            "corn",
            "crushed",
            "chopped",
            "diced",
            "dried",
            "infused",
            "juice",
            "ketchup",
            "mushroom",
            "oil",
            "paste",
            "peeled",
            "pepper",
            "potato",
            "powder",
            "salsa",
            "sauce",
            "spinach",
            "stewed",
            "strained",
            "stuffed",
            "sun",
            "vegetable",
            "yellow",
            "zucchini",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("garlic", "oil", "roasted")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("5169 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("5169 reviewed fresh tomato contract accepted")


def onion_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6448", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("onion", "onions"):
        return reject("6448 missing required term(s): onion")
    if product.category_has_any("chip", "chips", "dip", "frozen", "ring", "rings", "snack", "soup"):
        return reject("6448 category prepared onion mismatch")
    term_reject = reject_terms(
        product,
        "6448",
        (
            "blend",
            "bread",
            "chip",
            "dip",
            "dried",
            "fajita",
            "fried",
            "medley",
            "mix",
            "mixed",
            "pepper",
            "peppers",
            "powder",
            "ring",
            "rings",
            "soup",
            "squash",
            "stir",
            "zucchini",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("beef", "pepper", "potato", "sauce", "squash", "zucchini")
        if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)
    ]
    if ingredient_hits:
        return reject("6448 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("6448 reviewed fresh onion contract accepted")


def diced_tomato_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "7425", ("canned", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("tomato", "tomatoes"):
        return reject("7425 missing required term(s): tomato")
    if not product.has_any("diced", "dice"):
        return reject("7425 missing required term(s): diced")
    term_reject = reject_terms(
        product,
        "7425",
        ("basil", "chili", "fire", "garlic", "green", "herb", "italian", "onion", "oregano", "pepper", "roasted", "sauce"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("basil", "chili", "cilantro", "chipotle", "garlic", "habanero", "jalapeno", "onion", "oregano", "pepper", "vinegar")
        if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)
    ]
    if ingredient_hits:
        return reject("7425 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("7425 reviewed canned diced tomato contract accepted")


def pepper_contract(esha_code: str, color: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, VEGETABLE_CATEGORIES)
        if category_reject:
            return category_reject
        if not product.has_all(color, "pepper"):
            return reject(f"{esha_code} missing required term(s): {color}|pepper")
        if not (product.has_any("bell", "sweet") or product.has_phrase(f"{color} pepper")):
            return reject(f"{esha_code} missing required term(s): bell")
        if product.category_has_any("canned", "frozen", "juice", "oil", "prepared", "processed", "sauce"):
            return reject(f"{esha_code} category state mismatch")
        term_reject = reject_terms(
            product,
            esha_code,
            (
                "blend",
                "baked",
                "bean",
                "broccoli",
                "cabbage",
                "canned",
                "chile",
                "chili",
                "cooked",
                "corn",
                "diced",
                "fire",
                "frozen",
                "garlic",
                "jalapeno",
                "jelly",
                "juice",
                "kit",
                "roasted",
                "sauce",
                "saute",
                "serrano",
                "squash",
                "stir",
                "tomato",
            ),
        )
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed fresh bell pepper contract accepted")

    return contract


def bacon_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "12165", MEAT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("bacon"):
        return reject("12165 missing required term(s): bacon")
    if product.category_has_any("frozen"):
        return reject("12165 category state mismatch")
    term_reject = reject_terms(
        product,
        "12165",
        ("bean", "bit", "canadian", "cheese", "chipotle", "cooked", "crumbles", "imitation", "jalapeno", "jam", "jerky", "link", "maple", "marinated", "meatball", "piece", "ready", "salad", "sausage", "topping", "turkey", "ultimate", "vegetarian"),
    )
    if term_reject:
        return term_reject
    return accept("12165 reviewed retail bacon contract accepted")


def cocoa_powder_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "23712", ("baking", "cocoa"))
    if category_reject:
        return category_reject
    if not product.has_all("cocoa", "powder"):
        return reject("23712 missing required term(s): cocoa|powder")
    term_reject = reject_terms(product, "23712", ("drink", "hot", "mix", "sweetened"))
    if term_reject:
        return term_reject
    return accept("23712 reviewed cocoa powder contract accepted")


def apple_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "3001", ("fruit", "produce", "pre packaged"))
    if category_reject:
        return category_reject
    if product.category_has_any("canned", "frozen", "jam", "jelly", "snack"):
        return reject("3001 category state mismatch")
    if not product.has_any("apple", "apples"):
        return reject("3001 missing required term(s): apple")
    term_reject = reject_terms(
        product,
        "3001",
        (
            "applesauce",
            "baked",
            "banana",
            "candy",
            "caramel",
            "cheddar",
            "cheese",
            "chip",
            "chocolate",
            "creme",
            "dipped",
            "juice",
            "kit",
            "mix",
            "nut",
            "nuts",
            "peanut",
            "pie",
            "pineapple",
            "parfait",
            "salad",
            "snack",
            "sprinkle",
            "sprinkles",
            "strawberry",
        ),
    )
    if term_reject:
        return term_reject
    return accept("3001 reviewed fresh apple contract accepted")


def banana_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "51329", ("fruit", "produce", "pre packaged"))
    if category_reject:
        return category_reject
    if product.category_has_any("canned", "frozen", "jam", "jelly", "juice", "smoothie", "spread"):
        return reject("51329 category state mismatch")
    if not product.has_any("banana", "bananas"):
        return reject("51329 missing required term(s): banana")
    term_reject = reject_terms(
        product,
        "51329",
        (
            "almond",
            "apple",
            "apples",
            "babies",
            "blend",
            "blossom",
            "brine",
            "bread",
            "butter",
            "cherry",
            "chip",
            "chocolate",
            "cup",
            "dehydrated",
            "dried",
            "frozen",
            "freeze",
            "freeze-dried",
            "granola",
            "grape",
            "grapes",
            "juice",
            "mandarin",
            "oatmeal",
            "peach",
            "peanut",
            "pepper",
            "peppers",
            "ring",
            "rings",
            "smoothie",
            "spinach",
            "spread",
            "strawberry",
            "vinegar",
        ),
    )
    if term_reject:
        return term_reject
    return accept("51329 reviewed banana contract accepted")


def salsa_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "25570", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("salsa"):
        return reject("25570 missing required term(s): salsa")
    term_reject = reject_terms(
        product,
        "25570",
        ("bean", "burrito", "cheese", "chip", "chips", "con", "dip", "dry", "meal", "pasta", "queso", "seasoning", "snack", "sunflower"),
    )
    if term_reject:
        return term_reject
    return accept("25570 reviewed salsa contract accepted")


def cream_soup_contract(esha_code: str, identity: str, rejects: tuple[str, ...]) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, ("soup",))
        if category_reject:
            return category_reject
        if not product.has_all("soup", "cream") or not product.has_any(identity):
            return reject(f"{esha_code} missing required term(s): soup|cream|{identity}")
        if not product.has_any("condensed"):
            return reject(f"{esha_code} missing required term(s): condensed")
        term_reject = reject_terms(
            product,
            esha_code,
            ("bowl", "dry", "instant", "meal", "mix", "prepared", "ready", "rice", "serve", "with", *rejects),
        )
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed condensed cream soup contract accepted")

    return contract


def seasoning_salt_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "91928", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("seasoning", "seasoned") or not product.has_any("salt"):
        return reject("91928 missing required term(s): seasoning|salt")
    if not (product.has_phrase("seasoning salt") or product.has_phrase("seasoned salt")):
        return reject("91928 missing required phrase(s): seasoning salt")
    term_reject = reject_terms(
        product,
        "91928",
        ("cajun", "celery", "free", "garlic", "jerk", "lemon", "mesquite", "onion", "pepper", "rotisserie", "spicy"),
    )
    if term_reject:
        return term_reject
    return accept("91928 reviewed seasoning salt contract accepted")


def cherry_tomato_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "90530", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("tomato", "tomatoes") or not product.has_any("cherry"):
        return reject("90530 missing required term(s): tomato|cherry")
    if product.category_has_any("canned", "frozen", "juice", "sauce"):
        return reject("90530 category state mismatch")
    term_reject = reject_terms(
        product,
        "90530",
        ("blend", "dried", "grape", "medley", "pasta", "roasted", "salad", "sauce", "snack"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("garlic", "oil", "roasted")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("90530 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("90530 reviewed cherry tomato contract accepted")


def capers_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5511", ("condiment", "pickle", "olive", "relish", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("caper", "capers"):
        return reject("5511 missing required term(s): caper")
    term_reject = reject_terms(product, "5511", ("berry", "berries", "salad", "sauce", "topping"))
    if term_reject:
        return term_reject
    return accept("5511 reviewed capers contract accepted")


def blueberry_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "3381", ("fruit", "produce", "pre packaged"))
    if category_reject:
        return category_reject
    if product.category_has_any("canned", "frozen", "jam", "jelly", "juice", "processed", "snack", "spread"):
        return reject("3381 category state mismatch")
    if not product.has_any("blueberry", "blueberries"):
        return reject("3381 missing required term(s): blueberry")
    term_reject = reject_terms(
        product,
        "3381",
        ("blackberry", "conserve", "cereal", "cream", "dried", "freeze", "frozen", "granola", "muffin", "snack", "strawberry", "syrup", "yogurt"),
    )
    if term_reject:
        return term_reject
    return accept("3381 reviewed fresh blueberry contract accepted")


def almond_contract(esha_code: str, require_cut: bool = False) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, NUT_CATEGORIES)
        if category_reject:
            return category_reject
        if not product.has_any("almond", "almonds"):
            return reject(f"{esha_code} missing required term(s): almond")
        if require_cut and not product.has_any("sliced", "slivered"):
            return reject(f"{esha_code} missing required term(s): sliced")
        term_reject = reject_terms(
            product,
            esha_code,
            ("bar", "butter", "candy", "chocolate", "coffee", "cookie", "covered", "granola", "honey", "milk", "mix", "oil", "roasted", "salted", "smoke", "snack", "sweet", "trail", "yogurt"),
        )
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed almond contract accepted")

    return contract


def vegetable_broth_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "1793", ("broth", "soup", "stock"))
    if category_reject:
        return category_reject
    if not product.has_any("vegetable") or not product.has_any("broth", "stock"):
        return reject("1793 missing required term(s): vegetable|broth")
    term_reject = reject_terms(product, "1793", ("beef", "bone", "chicken", "mushroom", "soup"))
    if term_reject:
        return term_reject
    return accept("1793 reviewed vegetable broth contract accepted")


def red_wine_contract(product: ProductFacts) -> MatchDecision:
    if not (product.category_has_any("wine", "alcohol") or product.category_has_any("cooking", "sauce")):
        return reject("22501 category mismatch")
    if not (product.has_phrase("red cooking wine") or product.has_phrase("red wine")):
        return reject("22501 missing required phrase(s): red wine")
    term_reject = reject_terms(
        product,
        "22501",
        ("balsamic", "dressing", "marinade", "mustard", "salad", "sauce", "vinegar", "vinaigrette"),
    )
    if term_reject:
        return term_reject
    return accept("22501 reviewed red wine retail shelf contract accepted")


def pineapple_juice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "3990", ("juice", "drink", "beverage"))
    if category_reject:
        return category_reject
    if not product.has_any("pineapple"):
        return reject("3990 missing required term(s): pineapple")
    if not product.has_any("juice"):
        return reject("3990 missing required term(s): juice")
    term_reject = reject_terms(
        product,
        "3990",
        ("banana", "blend", "coconut", "cocktail", "fiesta", "mango", "orange", "passion", "punch", "smoothie", "strawberry", "vegetable"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("apple", "cucumber", "mango", "orange", "strawberry")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("3990 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("3990 reviewed pineapple juice contract accepted")


def white_onion_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5104", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("white", "onion"):
        return reject("5104 missing required term(s): white|onion")
    if product.category_has_any("frozen", "prepared", "sauce"):
        return reject("5104 category state mismatch")
    term_reject = reject_terms(product, "5104", ("dip", "fried", "pearl", "powder", "ring", "rings", "soup"))
    if term_reject:
        return term_reject
    return accept("5104 reviewed white onion contract accepted")


def fresh_dill_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26622", ("herb", "spice", "produce", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("dill"):
        return reject("26622 missing required term(s): dill")
    if not product.has_any("fresh"):
        return reject("26622 missing required term(s): fresh")
    term_reject = reject_terms(
        product,
        "26622",
        ("cheese", "chip", "dip", "dressing", "garlic", "kraut", "paste", "pickle", "pickles", "salad", "sauce", "seasoning"),
    )
    if term_reject:
        return term_reject
    return accept("26622 reviewed fresh dill contract accepted")


def whipped_topping_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "508", (*DESSERT_TOPPING_CATEGORIES, "cream", "dairy", "frozen"))
    if category_reject:
        return category_reject
    if not product.has_all("whipped", "topping"):
        return reject("508 missing required term(s): whipped|topping")
    term_reject = reject_terms(
        product,
        "508",
        ("cake", "cocoa", "coffee", "hazelnut", "hot", "ice", "pancake", "pie", "pumpkin", "sundae"),
    )
    if term_reject:
        return term_reject
    return accept("508 reviewed frozen whipped topping contract accepted")


def fresh_mint_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26630", ("herb", "spice", "produce", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("mint", "spearmint", "peppermint"):
        return reject("26630 missing required term(s): mint")
    if not product.has_any("fresh"):
        return reject("26630 missing required term(s): fresh")
    term_reject = reject_terms(product, "26630", ("candy", "chocolate", "dried", "gum", "tea"))
    if term_reject:
        return term_reject
    return accept("26630 reviewed fresh mint contract accepted")


def vanilla_ice_cream_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "2004", FROZEN_DESSERT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("vanilla") or not product.has_phrase("ice cream"):
        return reject("2004 missing required phrase(s): vanilla ice cream")
    term_reject = reject_terms(
        product,
        "2004",
        ("bar", "cake", "cone", "cookie", "custard", "dairy", "frozen", "sandwich", "yogurt"),
    )
    if term_reject:
        return term_reject
    return accept("2004 reviewed vanilla ice cream contract accepted")


def dried_cranberry_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "48557", ("dried fruit", "fruit", "snack"))
    if category_reject:
        return category_reject
    if not product.has_any("cranberry", "cranberries") or not product.has_any("dried", "craisins"):
        return reject("48557 missing required term(s): dried|cranberry")
    term_reject = reject_terms(product, "48557", ("bar", "chocolate", "cookie", "juice", "mix", "salad", "sauce", "trail"))
    if term_reject:
        return term_reject
    return accept("48557 reviewed dried cranberry contract accepted")


def shrimp_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "52629", SEAFOOD_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("shrimp"):
        return reject("52629 missing required term(s): shrimp")
    term_reject = reject_terms(
        product,
        "52629",
        ("breaded", "chip", "cocktail", "cooked", "dinner", "fried", "meal", "pasta", "popcorn", "salad", "sauce", "scampi", "soup"),
    )
    if term_reject:
        return term_reject
    return accept("52629 reviewed raw shrimp contract accepted")


def cooked_shrimp_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "52630", SEAFOOD_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("shrimp"):
        return reject("52630 missing required term(s): shrimp")
    if not product.has_any("cooked"):
        return reject("52630 missing required term(s): cooked")
    term_reject = reject_terms(
        product,
        "52630",
        ("alfredo", "battered", "breaded", "butter", "chip", "cocktail", "coconut", "dinner", "fried", "meal", "pasta", "popcorn", "raw", "rice", "ring", "salad", "sauce", "scampi", "soup", "tray"),
    )
    if term_reject:
        return term_reject
    return accept("52630 reviewed cooked shrimp contract accepted")


def cream_of_tartar_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26017", ("baking", "spice", "seasoning"))
    if category_reject:
        return category_reject
    if not product.has_phrase("cream of tartar"):
        return reject("26017 missing required phrase(s): cream of tartar")
    return accept("26017 reviewed cream of tartar contract accepted")


def eggplant_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6813", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("eggplant", "eggplants"):
        return reject("6813 missing required term(s): eggplant")
    if product.category_has_any("canned", "frozen", "prepared", "sauce"):
        return reject("6813 category state mismatch")
    term_reject = reject_terms(product, "6813", ("breaded", "dip", "fried", "hummus", "lasagna", "parmigiana", "pickled", "tofu"))
    if term_reject:
        return term_reject
    return accept("6813 reviewed fresh eggplant contract accepted")


def fish_sauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "53474", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_phrase("fish sauce"):
        return reject("53474 missing required phrase(s): fish sauce")
    term_reject = reject_terms(product, "53474", ("dish", "meal", "sandwich", "salad", "tartar", "tarter"))
    if term_reject:
        return term_reject
    return accept("53474 reviewed fish sauce contract accepted")


def coconut_contract(esha_code: str, required_form: tuple[str, ...]) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, ("baking", "coconut", "nut", "snack"))
        if category_reject:
            return category_reject
        if not product.has_any("coconut"):
            return reject(f"{esha_code} missing required term(s): coconut")
        if required_form and not product.has_any(*required_form):
            return reject(f"{esha_code} missing required term(s): " + "|".join(required_form))
        term_reject = reject_terms(product, esha_code, ("bar", "beverage", "chip", "cream", "milk", "oil", "snack", "water", "yogurt"))
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed coconut contract accepted")

    return contract


def sherry_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "22604", ("wine", "alcohol", "cooking"))
    if category_reject:
        return category_reject
    if not product.has_any("sherry"):
        return reject("22604 missing required term(s): sherry")
    term_reject = reject_terms(product, "22604", ("vinegar", "sauce", "dressing"))
    if term_reject:
        return term_reject
    return accept("22604 reviewed cooking sherry contract accepted")


def green_chile_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "14984", ("canned", "vegetable", "pepper"))
    if category_reject:
        return category_reject
    if not product.has_any("green") or not product.has_any("chile", "chiles", "chili", "chilies"):
        return reject("14984 missing required term(s): green|chile")
    term_reject = reject_terms(product, "14984", ("burrito", "cheese", "chip", "dip", "fresh", "jalapeno", "salsa", "tomato"))
    if term_reject:
        return term_reject
    return accept("14984 reviewed canned diced green chile contract accepted")


def asparagus_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5001", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("asparagus", "asparagu"):
        return reject("5001 missing required term(s): asparagus")
    if product.category_has_any("canned", "frozen", "pickle", "prepared", "relish"):
        return reject("5001 category state mismatch")
    term_reject = reject_terms(product, "5001", ("bacon", "butter", "cheese", "marinated", "pickled", "ravioli", "roasted", "sauce"))
    if term_reject:
        return term_reject
    if product.ingredients_have_any("oil", "pepper", "salt", "vinegar"):
        return reject("5001 excluded ingredient term(s): oil|pepper|salt|vinegar")
    return accept("5001 reviewed fresh asparagus contract accepted")


def baking_chocolate_contract(esha_code: str, kind: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, ("baking", "chocolate", "candy"))
        if category_reject:
            return category_reject
        if not product.has_any("chocolate"):
            return reject(f"{esha_code} missing required term(s): chocolate")
        if not product.has_any(kind):
            return reject(f"{esha_code} missing required term(s): {kind}")
        term_reject = reject_terms(
            product,
            esha_code,
            ("almond", "bar", "beverage", "chip", "cookie", "drink", "ice", "milk", "sauce", "syrup"),
        )
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed baking chocolate contract accepted")

    return contract


def mixed_nuts_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4591", NUT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("mixed") or not product.has_any("nut", "nuts"):
        return reject("4591 missing required term(s): mixed|nuts")
    term_reject = reject_terms(
        product,
        "4591",
        ("bar", "bread", "candy", "chocolate", "cookie", "granola", "nougat", "trail", "yogurt"),
    )
    if term_reject:
        return term_reject
    return accept("4591 reviewed mixed nuts contract accepted")


def chili_sauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "434", (*CONDIMENT_CATEGORIES, "chili", "stew"))
    if category_reject:
        return category_reject
    if not product.has_any("chili", "chile") or not product.has_any("sauce"):
        return reject("434 missing required term(s): chili|sauce")
    term_reject = reject_terms(
        product,
        "434",
        ("barbecue", "bbq", "cheese", "curry", "dog", "garlic", "hot", "nacho"),
    )
    if term_reject:
        return term_reject
    return accept("434 reviewed tomato chili sauce contract accepted")


def yellow_cake_mix_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "46089", ("cake", "cupcake", "baking", "mix"))
    if category_reject:
        return category_reject
    if not product.has_any("yellow") or not product.has_any("cake") or not product.has_any("mix"):
        return reject("46089 missing required term(s): yellow|cake|mix")
    term_reject = reject_terms(
        product,
        "46089",
        ("baked", "chocolate", "cookie", "cupcake", "frosting", "icing", "prepared", "snack"),
    )
    if term_reject:
        return term_reject
    return accept("46089 reviewed yellow cake dry mix contract accepted")


def kalamata_olive_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6499", ("olive", "olives", "pickle", "relish", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("kalamata", "calamata") or not (
        product.has_any("olive", "olives", "olif") or product.has_phrase("olives")
    ):
        return reject("6499 missing required term(s): kalamata|olive")
    term_reject = reject_terms(
        product,
        "6499",
        ("bruschetta", "dip", "feta", "flavored", "green", "hummus", "mixed", "oregano", "paste", "salad", "salami", "sauce", "seasoned", "smoked", "spread", "tapenade", "thyme", "tray"),
    )
    if term_reject:
        return term_reject
    return accept("6499 reviewed kalamata olive contract accepted")


def golden_raisin_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "3934", ("dried fruit", "fruit", "snack"))
    if category_reject:
        return category_reject
    if not product.has_any("raisin", "raisins") or not product.has_any("golden"):
        return reject("3934 missing required term(s): golden|raisin")
    term_reject = reject_terms(
        product,
        "3934",
        ("almond", "berry", "bread", "cashew", "cereal", "cherry", "chocolate", "cranberry", "mix", "trail", "yogurt"),
    )
    if term_reject:
        return term_reject
    return accept("3934 reviewed golden raisin contract accepted")


def roma_tomato_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6492", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("tomato", "tomatoes") or not product.has_any("roma"):
        return reject("6492 missing required term(s): roma|tomato")
    if product.category_has_any("canned", "frozen", "juice", "sauce"):
        return reject("6492 category state mismatch")
    term_reject = reject_terms(
        product,
        "6492",
        ("canned", "diced", "paste", "puree", "sauce", "stewed"),
    )
    if term_reject:
        return term_reject
    return accept("6492 reviewed fresh roma tomato contract accepted")


def tomato_juice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "3996", ("juice", "drink", "beverage"))
    if category_reject:
        return category_reject
    if not product.has_any("tomato") or not product.has_any("juice"):
        return reject("3996 missing required term(s): tomato|juice")
    term_reject = reject_terms(
        product,
        "3996",
        ("beef", "carrot", "celery", "clam", "cocktail", "diced", "vegetable"),
    )
    if term_reject:
        return term_reject
    return accept("3996 reviewed tomato juice contract accepted")


def tomato_puree_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5476", ("tomato", "tomatoes", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("tomato", "tomatoes") or not product.has_any("puree", "pureed", "passata"):
        return reject("5476 missing required term(s): tomato|puree")
    term_reject = reject_terms(
        product,
        "5476",
        ("chopped", "crushed", "diced", "paste", "sauce", "seasoned", "stewed"),
    )
    if term_reject:
        return term_reject
    return accept("5476 reviewed tomato puree contract accepted")


def sunflower_seed_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4545", ("seed", "nut", "snack"))
    if category_reject:
        return category_reject
    if not product.has_any("sunflower") or not product.has_any("seed", "seeds", "kernel", "kernels"):
        return reject("4545 missing required term(s): sunflower|seed")
    if product.has_phrase("with shell") or product.has_phrase("in shell"):
        return reject("4545 excluded shell-on sunflower seed")
    if not (
        product.has_any("kernel", "kernels", "shelled", "hulled")
        or product.ingredients_have_any("kernel", "kernels")
        or product.ingredients_have_phrase("shelled sunflower")
        or product.ingredients_have_phrase("hulled sunflower")
    ):
        return reject("4545 missing kernel/shelled/hulled cue")
    term_reject = reject_terms(
        product,
        "4545",
        (
            "bar",
            "barbecue",
            "bbq",
            "bread",
            "breading",
            "cheddar",
            "chia",
            "chili",
            "chocolate",
            "cluster",
            "coconut",
            "crumb",
            "cranberry",
            "dill",
            "flavor",
            "flavored",
            "granola",
            "honey",
            "mix",
            "peanut",
            "peanuts",
            "pepita",
            "pepitas",
            "pumpkin",
            "raisin",
            "raisins",
            "ranch",
            "seasoned",
            "smackin",
            "spicy",
            "sweet",
            "taco",
            "toffee",
            "trail",
            "yogurt",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in (
            "caramel",
            "chipotle",
            "flavor",
            "flavors",
            "garlic",
            "maltodextrin",
            "msg",
            "onion",
            "paprika",
            "seasoning",
            "spice",
            "spices",
            "sugar",
            "toffee",
        )
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("4545 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("4545 reviewed sunflower seed contract accepted")


def yellow_cornmeal_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38004", BAKING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("yellow") or not product.has_any("cornmeal"):
        return reject("38004 missing required term(s): yellow|cornmeal")
    term_reject = reject_terms(
        product,
        "38004",
        ("arepa", "cake", "cornbread", "hush", "mix", "precooked", "self", "white"),
    )
    if term_reject:
        return term_reject
    return accept("38004 reviewed yellow cornmeal contract accepted")


def miniature_marshmallow_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "23008", ("candy", "marshmallow", "baking"))
    if category_reject:
        return category_reject
    if not product.has_any("marshmallow", "marshmallows"):
        return reject("23008 missing required term(s): marshmallow")
    if not product.has_any("mini", "miniature"):
        return reject("23008 missing required term(s): miniature")
    term_reject = reject_terms(product, "23008", ("cereal", "chocolate", "cocoa", "cookie", "hot"))
    if term_reject:
        return term_reject
    return accept("23008 reviewed miniature marshmallow contract accepted")


def penne_pasta_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "92830", ("pasta", "noodle", "noodles"))
    if category_reject:
        return category_reject
    if not product.has_any("penne"):
        return reject("92830 missing required term(s): penne")
    term_reject = reject_terms(
        product,
        "92830",
        ("alfredo", "amaranth", "brown", "chicken", "corn", "dinner", "gluten", "meal", "multigrain", "quinoa", "rice", "whole"),
    )
    if term_reject:
        return term_reject
    return accept("92830 reviewed dry penne pasta contract accepted")


def crabmeat_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26830", SEAFOOD_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("crab", "crabmeat"):
        return reject("26830 missing required term(s): crab")
    term_reject = reject_terms(
        product,
        "26830",
        ("cake", "imitation", "roll", "salad", "soup", "stuffed", "stuffing", "surimi", "sushi", "tilapia"),
    )
    if term_reject:
        return term_reject
    return accept("26830 reviewed crabmeat contract accepted")


def white_chocolate_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "90659", ("baking", "chocolate", "candy"))
    if category_reject:
        return category_reject
    if not product.has_any("white") or not product.has_any("chocolate"):
        return reject("90659 missing required term(s): white|chocolate")
    term_reject = reject_terms(
        product,
        "90659",
        ("bar", "beverage", "chip", "cookie", "drink", "frosting", "ice", "macadamia", "pudding", "sauce", "syrup", "yogurt"),
    )
    if term_reject:
        return term_reject
    return accept("90659 reviewed white baking chocolate contract accepted")


def white_chocolate_chip_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "23447", ("baking", "chocolate", "dessert", "topping"))
    if category_reject:
        return category_reject
    if not product.has_any("white") or not product.has_any("chocolate"):
        return reject("23447 missing required term(s): white|chocolate")
    if not product.has_any("chip", "chips", "morsel", "morsels", "chunk", "chunks"):
        return reject("23447 missing required term(s): chip")
    term_reject = reject_terms(
        product,
        "23447",
        ("cookie", "egg", "frosting", "pudding", "syrup"),
    )
    if term_reject:
        return term_reject
    return accept("23447 reviewed white chocolate chip contract accepted")


def simple_alcohol_contract(esha_code: str, identity: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, ALCOHOL_CATEGORIES)
        if category_reject:
            return category_reject
        if not product.has_any(identity):
            return reject(f"{esha_code} missing required term(s): {identity}")
        term_reject = reject_terms(
            product,
            esha_code,
            ("batter", "battered", "butter", "cake", "cheese", "drink", "hot", "mix", "non", "root", "sauce", "vinegar"),
        )
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed alcohol contract accepted")

    return contract


def sun_dried_tomato_contract(product: ProductFacts) -> MatchDecision:
    if not product.category_has_any("vegetable", "produce", "canned", "condiment", "pickle", "olive"):
        return reject("5446 category mismatch")
    if not product.has_any("tomato", "tomatoes") or not product.has_any("sun", "sundried"):
        return reject("5446 missing required term(s): sun|tomato")
    term_reject = reject_terms(product, "5446", ("bagel", "bread", "cheese", "dressing", "pasta", "sauce", "sausage", "spread", "tortilla"))
    if term_reject:
        return term_reject
    return accept("5446 reviewed sun dried tomato contract accepted")


def bread_flour_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38277", BAKING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("bread", "flour"):
        return reject("38277 missing required term(s): bread|flour")
    term_reject = reject_terms(product, "38277", ("almond", "cake", "gluten", "mix", "pancake", "rice", "rye", "soy", "tortilla", "whole"))
    if term_reject:
        return term_reject
    return accept("38277 reviewed bread flour contract accepted")


def cooking_oil_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "90965", OIL_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("oil"):
        return reject("90965 missing required term(s): oil")
    term_reject = reject_terms(
        product,
        "90965",
        ("avocado", "butter", "coconut", "flavored", "garlic", "olive", "peanut", "sesame", "spray", "truffle"),
    )
    if term_reject:
        return term_reject
    return accept("90965 reviewed neutral cooking oil contract accepted")


def corn_tortilla_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "13472", TORTILLA_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("tortilla", "tortillas") or not product.has_any("corn"):
        return reject("13472 missing required term(s): corn|tortilla")
    term_reject = reject_terms(product, "13472", ("bowl", "chip", "chips", "flour", "kit", "pizza", "roll", "shell", "taquito", "wrap"))
    if term_reject:
        return term_reject
    return accept("13472 reviewed corn tortilla contract accepted")


def plum_tomato_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5172", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("tomato", "tomatoes") or not product.has_any("plum", "roma"):
        return reject("5172 missing required term(s): plum|tomato")
    if product.category_has_any("canned", "frozen", "sauce"):
        return reject("5172 category state mismatch")
    term_reject = reject_terms(product, "5172", ("basil", "canned", "paste", "peeled", "sauce", "whole"))
    if term_reject:
        return term_reject
    return accept("5172 reviewed fresh plum tomato contract accepted")


def splenda_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "34814", ("sweetener", "sugar", "baking"))
    if category_reject:
        return category_reject
    if not product.has_any("splenda", "sucralose"):
        return reject("34814 missing required term(s): splenda|sucralose")
    term_reject = reject_terms(product, "34814", ("cookie", "drink", "ice", "juice", "soda", "sorbet", "tea"))
    if term_reject:
        return term_reject
    return accept("34814 reviewed Splenda sucralose sweetener contract accepted")


def pumpkin_puree_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6298", ("canned", "vegetable", "baking"))
    if category_reject:
        return category_reject
    if not product.has_any("pumpkin"):
        return reject("6298 missing required term(s): pumpkin")
    plain_canned_pumpkin = product.description_norm in {"pumpkin", "organic pumpkin"} or product.has_phrase("solid pack pumpkin")
    if not (plain_canned_pumpkin or product.has_any("pure", "puree", "pureed") or product.has_phrase("100 pure")):
        return reject("6298 missing required term(s): pure")
    term_reject = reject_terms(product, "6298", ("pie", "spice", "seed", "soup"))
    if term_reject:
        return term_reject
    return accept("6298 reviewed canned pumpkin puree contract accepted")


def mustard_contract(esha_code: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, CONDIMENT_CATEGORIES)
        if category_reject:
            return category_reject
        if not product.has_any("mustard"):
            return reject(f"{esha_code} missing required term(s): mustard")
        term_reject = reject_terms(product, esha_code, ("dressing", "honey", "marinade", "sauce", "vinaigrette"))
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed prepared mustard contract accepted")

    return contract


def applesauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "3006", ("fruit", "canned", "snack"))
    if category_reject:
        return category_reject
    if not product.has_any("applesauce"):
        return reject("3006 missing required term(s): applesauce")
    term_reject = reject_terms(product, "3006", ("cereal", "cookie", "dinner", "meal", "pouch", "squeezies", "toddler"))
    if term_reject:
        return term_reject
    return accept("3006 reviewed applesauce contract accepted")


def taco_seasoning_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26482", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("taco", "seasoning"):
        return reject("26482 missing required term(s): taco|seasoning")
    term_reject = reject_terms(product, "26482", ("cheese", "kit", "shell", "shells", "snack"))
    if term_reject:
        return term_reject
    return accept("26482 reviewed taco seasoning contract accepted")


def spaghetti_sauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "9114", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not (product.has_phrase("spaghetti sauce") or product.has_phrase("pasta sauce") or product.has_any("marinara")):
        return reject("9114 missing required phrase(s): spaghetti sauce")
    term_reject = reject_terms(product, "9114", ("alfredo", "beef", "dinner", "meal", "pasta", "ravioli", "vodka"))
    if term_reject:
        return term_reject
    return accept("9114 reviewed spaghetti sauce contract accepted")


def velveeta_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "1272", ("cheese", "dairy"))
    if category_reject:
        return category_reject
    if not product.has_any("velveeta"):
        return reject("1272 missing required term(s): velveeta")
    term_reject = reject_terms(product, "1272", ("mac", "macaroni", "shells", "skillet"))
    if term_reject:
        return term_reject
    return accept("1272 reviewed Velveeta cheese contract accepted")


def black_peppercorn_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26901", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("peppercorn", "peppercorns"):
        return reject("26901 missing required term(s): peppercorn")
    if not product.has_any("black"):
        return reject("26901 missing required term(s): black")
    term_reject = reject_terms(product, "26901", ("cheese", "dressing", "green", "gravy", "marinade", "medley", "pink", "sauce"))
    if term_reject:
        return term_reject
    return accept("26901 reviewed black peppercorn contract accepted")


def leek_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5206", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("leek", "leeks"):
        return reject("5206 missing required term(s): leek")
    if product.category_has_any("frozen", "prepared", "sauce"):
        return reject("5206 category state mismatch")
    term_reject = reject_terms(product, "5206", ("chinese", "freeze", "fried", "soup"))
    if term_reject:
        return term_reject
    return accept("5206 reviewed fresh leek contract accepted")


def plain_yogurt_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "2013", YOGURT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("plain", "yogurt"):
        return reject("2013 missing required term(s): plain|yogurt")
    term_reject = reject_terms(
        product,
        "2013",
        ("flavored", "greek", "kefir", "lowfat", "nonfat", "soy", "tofu", "vanilla"),
    )
    if term_reject:
        return term_reject
    return accept("2013 reviewed plain yogurt contract accepted")


def white_wine_contract(product: ProductFacts) -> MatchDecision:
    if not (product.category_has_any("wine", "alcohol") or product.category_has_any("cooking", "sauce")):
        return reject("22504 category mismatch")
    if not (product.has_phrase("white cooking wine") or product.has_phrase("white wine")):
        return reject("22504 missing required phrase(s): white wine")
    term_reject = reject_terms(
        product,
        "22504",
        (
            "alfredo",
            "balsamic",
            "champagne",
            "chicken",
            "cider",
            "dessert",
            "dijon",
            "dressing",
            "fortified",
            "marinade",
            "marsala",
            "mustard",
            "rose",
            "salad",
            "salame",
            "salami",
            "sauce",
            "sparkling",
            "sweet",
            "vinegar",
            "vinaigrette",
        ),
    )
    if term_reject:
        return term_reject
    if product.has_phrase("cooking wine") and not product.ingredients_have_any("wine"):
        return reject("22504 missing ingredient term(s): wine")
    return accept("22504 reviewed white wine retail shelf contract accepted")


def flour_tortilla_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "25490", TORTILLA_CATEGORIES)
    if category_reject:
        return category_reject
    if product.category_has_any("frozen", "pizza", "prepared", "sandwich", "wrap"):
        return reject("25490 category state mismatch")
    if not product.has_any("tortilla", "tortillas"):
        return reject("25490 missing required term(s): tortilla")
    if not (product.has_any("flour") or product.ingredients_have_any("flour")):
        return reject("25490 missing required term(s): flour|tortilla")
    term_reject = reject_terms(
        product,
        "25490",
        (
            "bowl",
            "bowls",
            "cassava",
            "cauliflower",
            "cheese",
            "chickpea",
            "chip",
            "corn",
            "dinner",
            "grain",
            "kit",
            "pizza",
            "roll",
            "rolls",
            "taquito",
            "wrap",
        ),
    )
    if term_reject:
        return term_reject
    if product.ingredients and not product.ingredients_have_any("flour"):
        return reject("25490 missing ingredient term(s): flour")
    return accept("25490 reviewed flour tortilla contract accepted")


def red_lentil_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "7378", ("lentil", "legume", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("lentil", "lentils"):
        return reject("7378 missing required term(s): lentil")
    if not product.has_any("red"):
        return reject("7378 missing required term(s): red")
    term_reject = reject_terms(
        product,
        "7378",
        (
            "bar",
            "bean",
            "beans",
            "bowl",
            "chip",
            "chips",
            "couscous",
            "curry",
            "dip",
            "dinner",
            "entree",
            "kit",
            "madras",
            "meal",
            "pasta",
            "pilaf",
            "rice",
            "salad",
            "sauce",
            "soup",
            "stew",
            "vegetable",
            "wrap",
        ),
    )
    if term_reject:
        return term_reject
    return accept("7378 reviewed dry red lentil contract accepted")


def ramen_noodle_contract(esha_code: str, flavor_terms: tuple[str, ...] = ()) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any("noodle", "noodles", "soup"):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any("ramen"):
            return reject(f"{esha_code} missing required term(s): ramen")
        if not product.has_any("noodle", "noodles"):
            return reject(f"{esha_code} missing required term(s): noodle")
        for term in flavor_terms:
            if not product.has_any(term):
                return reject(f"{esha_code} missing required term(s): {term}")
        term_reject = reject_terms(
            product,
            esha_code,
            (
                "beef",
                "bowl",
                "bowls",
                "cod",
                "dinner",
                "entree",
                "fresh",
                "kit",
                "meal",
                "miso",
                "packet",
                "salad",
                "seafood",
                "shrimp",
                "side",
                "tonkotsu",
                "vegetable",
                "veggie",
            ),
        )
        if term_reject:
            if esha_code == "28169" and any(term in term_reject.reason for term in ("beef", "shrimp", "vegetable", "veggie")):
                return term_reject
            if esha_code != "28169" and "beef" in term_reject.reason:
                return term_reject
            return term_reject
        if product.category_has_any("frozen", "deli"):
            return reject(f"{esha_code} category state mismatch")
        return accept(f"{esha_code} reviewed dry ramen noodle contract accepted")

    return contract


def andouille_sausage_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "58511", ("sausage", "meat", "pork", "brat"))
    if category_reject:
        return category_reject
    if not product.has_any("andouille"):
        return reject("58511 missing required term(s): andouille")
    if not product.has_any("sausage", "sausages"):
        return reject("58511 missing required term(s): sausage")
    term_reject = reject_terms(
        product,
        "58511",
        (
            "bean",
            "beans",
            "chicken",
            "dinner",
            "entree",
            "gumbo",
            "jambalaya",
            "meal",
            "rice",
            "soup",
            "stew",
            "turkey",
            "vegetarian",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("chicken", "turkey", "vegetarian")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("58511 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("58511 reviewed pork andouille sausage contract accepted")


def peanut_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4696", NUT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("peanut", "peanuts"):
        return reject("4696 missing required term(s): peanut")
    term_reject = reject_terms(
        product,
        "4696",
        (
            "bar",
            "brittle",
            "butter",
            "candy",
            "chocolate",
            "cookie",
            "cracker",
            "flour",
            "granola",
            "honey",
            "mix",
            "sauce",
            "spicy",
            "trail",
            "yogurt",
        ),
    )
    if term_reject:
        return term_reject
    return accept("4696 reviewed plain peanut contract accepted")


def cayenne_pepper_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "82043", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not (product.has_any("cayenne") or product.has_all("red", "pepper")):
        return reject("82043 missing required term(s): cayenne")
    if not product.has_any("pepper", "powder", "spice", "seasoning", "ground", "cayenne"):
        return reject("82043 missing required spice form")
    term_reject = reject_terms(
        product,
        "82043",
        ("cherries", "cherry", "drink", "hummus", "lemonade", "sauce", "truffle", "truffles"),
    )
    if term_reject:
        return term_reject
    return accept("82043 reviewed ground cayenne pepper contract accepted")


def lasagna_noodle_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "91211", ("noodle", "noodles", "pasta"))
    if category_reject:
        return category_reject
    if not product.has_any("lasagna"):
        return reject("91211 missing required term(s): lasagna")
    term_reject = reject_terms(
        product,
        "91211",
        (
            "bake",
            "bolognese",
            "cheese",
            "chicken",
            "dinner",
            "entree",
            "frozen",
            "meal",
            "meat",
            "prepared",
            "sauce",
            "soup",
            "vegetable",
        ),
    )
    if term_reject:
        return term_reject
    return accept("91211 reviewed dry lasagna noodle contract accepted")


def firm_tofu_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "12888", ("meat", "plant", "tofu", "vegetarian"))
    if category_reject:
        return category_reject
    if not product.has_any("tofu"):
        return reject("12888 missing required term(s): tofu")
    if not product.has_any("firm"):
        return reject("12888 missing required term(s): firm")
    term_reject = reject_terms(product, "12888", ("dessert", "dip", "drink", "noodle", "soup", "spread"))
    if term_reject:
        return term_reject
    return accept("12888 reviewed firm tofu contract accepted")


def splenda_granular_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "31180", ("baking", "sugar", "sweetener"))
    if category_reject:
        return category_reject
    if not product.has_any("splenda", "sucralose", "sweetener"):
        return reject("31180 missing required term(s): splenda|sucralose|sweetener")
    if not product.has_any("granular", "granulated"):
        return reject("31180 missing required term(s): granular")
    term_reject = reject_terms(product, "31180", ("brown", "cookie", "drink", "ice", "juice", "packet", "soda", "sorbet", "tea"))
    if term_reject:
        return term_reject
    return accept("31180 reviewed granular sucralose sweetener contract accepted")


def sauerkraut_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "36986", ("canned", "pickle", "relish", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("sauerkraut"):
        return reject("36986 missing required term(s): sauerkraut")
    term_reject = reject_terms(product, "36986", ("beet", "dog", "frankfurter", "garlic", "meal", "sandwich", "sausage"))
    if term_reject:
        return term_reject
    return accept("36986 reviewed sauerkraut contract accepted")


def soy_milk_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "20033", ("milk", "plant"))
    if category_reject:
        return category_reject
    if not (product.has_phrase("soy milk") or product.has_any("soymilk")):
        return reject("20033 missing required term(s): soy milk")
    term_reject = reject_terms(
        product,
        "20033",
        ("chai", "chocolate", "coffee", "creamer", "latte", "mocha", "nog", "powder", "shake", "vanilla"),
    )
    if term_reject:
        return term_reject
    return accept("20033 reviewed plain soy milk contract accepted")


def cranberry_juice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4986", ("beverage", "drink", "juice"))
    if category_reject:
        return category_reject
    if not product.has_any("cranberry"):
        return reject("4986 missing required term(s): cranberry")
    if not product.has_any("juice"):
        return reject("4986 missing required term(s): juice")
    term_reject = reject_terms(
        product,
        "4986",
        ("apple", "blend", "blueberry", "cocktail", "grape", "pomegranate", "raspberry", "sauce"),
    )
    if term_reject:
        return term_reject
    return accept("4986 reviewed cranberry juice contract accepted")


def hazelnut_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4513", NUT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("hazelnut", "hazelnuts", "filbert", "filberts"):
        return reject("4513 missing required term(s): hazelnut")
    term_reject = reject_terms(
        product,
        "4513",
        ("bar", "butter", "candy", "chocolate", "coffee", "cookie", "creamer", "cream", "ice", "spread", "syrup", "wafer"),
    )
    if term_reject:
        return term_reject
    return accept("4513 reviewed plain hazelnut contract accepted")


def cream_of_celery_soup_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "50473", ("canned", "soup"))
    if category_reject:
        return category_reject
    if not (product.has_any("soup") and product.has_any("cream") and product.has_any("celery")):
        return reject("50473 missing required term(s): cream|celery|soup")
    term_reject = reject_terms(product, "50473", ("chicken", "mushroom", "tripe", "vegetable"))
    if term_reject:
        return term_reject
    return accept("50473 reviewed condensed cream of celery soup contract accepted")


def cashew_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "63195", NUT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("cashew", "cashews"):
        return reject("63195 missing required term(s): cashew")
    term_reject = reject_terms(
        product,
        "63195",
        ("bar", "bite", "bites", "butter", "candy", "chocolate", "cluster", "clusters", "cookie", "curry", "granola", "honey", "mix", "sauce", "trail"),
    )
    if term_reject:
        return term_reject
    return accept("63195 reviewed plain cashew contract accepted")


def ranch_dressing_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "8555", ("dressing", "mayonnaise", "salad"))
    if category_reject:
        return category_reject
    if not product.has_any("ranch"):
        return reject("8555 missing required term(s): ranch")
    if not product.has_any("dressing"):
        return reject("8555 missing required term(s): dressing")
    term_reject = reject_terms(product, "8555", ("bacon", "buffalo", "chipotle", "dip", "dry", "jalapeno", "mix", "packet", "parmesan", "powder"))
    if term_reject:
        return term_reject
    return accept("8555 reviewed ranch dressing contract accepted")


def cherry_pie_filling_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "48015", ("filling", "pastry", "pie", "topping"))
    if category_reject:
        return category_reject
    if not product.has_all("cherry", "pie"):
        return reject("48015 missing required term(s): cherry|pie")
    if not product.has_any("filling", "fill"):
        return reject("48015 missing required term(s): filling")
    term_reject = reject_terms(product, "48015", ("cake", "low", "lite", "reduced", "sugar"))
    if term_reject:
        return term_reject
    return accept("48015 reviewed cherry pie filling contract accepted")


def tahini_contract(product: ProductFacts) -> MatchDecision:
    if not (product.category_has_any("condiment", "dressing", "sauce", "sesame") or product.category_has_any("ethnic", "mayonnaise")):
        return reject("4686 category mismatch")
    if not product.has_any("tahini"):
        return reject("4686 missing required term(s): tahini")
    term_reject = reject_terms(
        product,
        "4686",
        ("biscuit", "cashew", "chocolate", "cup", "dressing", "garlic", "green", "herb", "hummus", "lemon", "mushroom", "salad", "sauce", "spiced", "sweet", "potato"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("chickpea", "cilantro", "garlic", "lemon", "maple", "mushroom", "oil", "parsley", "potato", "sugar", "syrup", "vinegar", "water")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("4686 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("4686 reviewed tahini sesame paste contract accepted")


def miracle_whip_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "8479", ("condiment", "dressing", "mayonnaise", "sauce", "spread"))
    if category_reject:
        return category_reject
    if not product.has_all("miracle", "whip"):
        return reject("8479 missing required term(s): miracle|whip")
    term_reject = reject_terms(product, "8479", ("hot", "spicy"))
    if term_reject:
        return term_reject
    return accept("8479 reviewed Miracle Whip dressing contract accepted")


def kahlua_contract(product: ProductFacts) -> MatchDecision:
    if not product.category_has_any("alcohol", "liquor", "liqueur"):
        return reject("22519 category mismatch")
    if not (product.has_any("kahlua") or product.has_all("coffee", "liqueur")):
        return reject("22519 missing required term(s): coffee liqueur")
    term_reject = reject_terms(product, "22519", ("chocolate", "creamer", "cream", "powder"))
    if term_reject:
        return term_reject
    return accept("22519 reviewed coffee liqueur contract accepted")


def sunflower_oil_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "8233", OIL_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("sunflower", "oil"):
        return reject("8233 missing required term(s): sunflower|oil")
    term_reject = reject_terms(product, "8233", ("fish", "flavored", "garlic", "herb", "olive", "oyster", "spread", "tuna"))
    if term_reject:
        return term_reject
    return accept("8233 reviewed sunflower oil contract accepted")


def quick_oats_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "92017", ("cereal", "oat"))
    if category_reject:
        return category_reject
    if not product.has_any("oat", "oats", "oatmeal"):
        return reject("92017 missing required term(s): oat")
    if not product.has_any("quick", "minute"):
        return reject("92017 missing required term(s): quick")
    term_reject = reject_terms(product, "92017", ("bar", "cookie", "cut", "flavored", "granola", "instant", "maple", "protein", "steel"))
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("almond", "brown", "chia", "flax", "hemp", "maple", "sugar", "syrup")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("92017 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("92017 reviewed quick oats contract accepted")


def pasta_shape_contract(esha_code: str, shape: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, ("pasta", "noodle", "noodles"))
        if category_reject:
            return category_reject
        if not product.has_any(shape):
            return reject(f"{esha_code} missing required term(s): {shape}")
        term_reject = reject_terms(
            product,
            esha_code,
            (
                "alfredo",
                "butter",
                "chicken",
                "chickpea",
                "dinner",
                "egg",
                "herb",
                "kit",
                "konjac",
                "lemon",
                "lentil",
                "meal",
                "pilaf",
                "protein",
                "quinoa",
                "rice",
                "salad",
                "sauce",
                "soup",
                "spinach",
                "stroganoff",
                "sour",
                "chives",
                "roni",
                "tomato",
                "vegetable",
                "veggie",
                "whole",
            ),
        )
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed dry {shape} pasta contract accepted")

    return contract


def bisquick_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "16533", ("baking", "cooking mix", "cake", "cookie", "cupcake", "pancake", "waffle"))
    if category_reject:
        return category_reject
    if not product.has_any("bisquick"):
        return reject("16533 missing required term(s): bisquick")
    term_reject = reject_terms(product, "16533", ("biscuit", "buttermilk", "cheese", "complete", "gluten", "heart", "shake"))
    if term_reject:
        return term_reject
    return accept("16533 reviewed original Bisquick baking mix contract accepted")


def marshmallow_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "23007", ("candy", "marshmallow", "baking"))
    if category_reject:
        return category_reject
    if not product.has_any("marshmallow", "marshmallows"):
        return reject("23007 missing required term(s): marshmallow")
    term_reject = reject_terms(
        product,
        "23007",
        ("bar", "cereal", "chocolate", "cocoa", "cookie", "creme", "cream", "hot", "mini", "miniature", "syrup", "topping", "treat"),
    )
    if term_reject:
        return term_reject
    return accept("23007 reviewed plain marshmallow contract accepted")


def ritz_cracker_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "70963", ("cracker", "biscuit", "cookie", "snack"))
    if category_reject:
        return category_reject
    if not product.has_any("ritz"):
        return reject("70963 missing required term(s): ritz")
    if not product.has_any("cracker", "crackers"):
        return reject("70963 missing required term(s): cracker")
    term_reject = reject_terms(
        product,
        "70963",
        ("bits", "cheese", "chips", "fudge", "garlic", "peanut", "sandwich", "sour", "toasted", "vegetable"),
    )
    if term_reject:
        return term_reject
    return accept("70963 reviewed Ritz cracker contract accepted")


def coconut_oil_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "8037", OIL_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("coconut", "oil"):
        return reject("8037 missing required term(s): coconut|oil")
    term_reject = reject_terms(product, "8037", ("blend", "butter", "frosting", "spray", "sunflower"))
    if term_reject:
        return term_reject
    if product.ingredients_have_any("sunflower oil", "canola oil", "soybean oil") and not product.has_any("100%", "pure"):
        return reject("8037 excluded blended oil ingredient")
    return accept("8037 reviewed coconut oil contract accepted")


def pita_bread_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "42007", ("bread", "bun", "bakery"))
    if category_reject:
        return category_reject
    if not product.has_any("pita"):
        return reject("42007 missing required term(s): pita")
    term_reject = reject_terms(product, "42007", ("chip", "chips", "cracker", "crust", "gyro", "kit", "pizza", "sandwich"))
    if term_reject:
        return term_reject
    return accept("42007 reviewed pita bread contract accepted")


def ground_spice_contract(esha_code: str, spice: str, exclude: tuple[str, ...] = ()) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, SEASONING_CATEGORIES)
        if category_reject:
            return category_reject
        if not product.has_any(spice):
            return reject(f"{esha_code} missing required term(s): {spice}")
        if not product.has_any("ground", "powder"):
            return reject(f"{esha_code} missing required term(s): ground")
        term_reject = reject_terms(
            product,
            esha_code,
            ("bar", "chicken", "dip", "fajita", "sauce", "seasoned", "strip") + exclude,
        )
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed ground {spice} contract accepted")

    return contract


def ground_mustard_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26514", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("mustard"):
        return reject("26514 missing required term(s): mustard")
    if not product.has_any("ground", "powder"):
        return reject("26514 missing required term(s): ground")
    term_reject = reject_terms(
        product,
        "26514",
        ("dijon", "dressing", "honey", "prepared", "sauce", "seasoning", "vinaigrette"),
    )
    if term_reject:
        return term_reject
    return accept("26514 reviewed ground mustard contract accepted")


def crescent_roll_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "16638", ("bread", "dough", "roll", "biscuit"))
    if category_reject:
        return category_reject
    if not product.has_any("crescent"):
        return reject("16638 missing required term(s): crescent")
    term_reject = reject_terms(product, "16638", ("almond", "cookie"))
    if term_reject:
        return term_reject
    return accept("16638 reviewed refrigerated crescent roll contract accepted")


def ranch_dressing_mix_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "41429", ("dressing", "seasoning", "marinade", "tenderizer"))
    if category_reject:
        return category_reject
    if not product.has_any("ranch"):
        return reject("41429 missing required term(s): ranch")
    if not product.has_any("mix", "packet", "seasoning", "dry", "recipe"):
        return reject("41429 missing required term(s): mix")
    term_reject = reject_terms(product, "41429", ("bottled", "buffalo", "chipotle", "dip", "jalapeno", "parmesan", "salsa", "spicy"))
    if term_reject:
        return term_reject
    return accept("41429 reviewed dry ranch dressing mix contract accepted")


def graham_cracker_crust_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "48475", ("crust", "dough", "pie"))
    if category_reject:
        return category_reject
    if not product.has_all("graham", "cracker"):
        return reject("48475 missing required term(s): graham|cracker")
    if not product.has_any("crust"):
        return reject("48475 missing required term(s): crust")
    term_reject = reject_terms(product, "48475", ("cake", "cheesecake", "filling", "pie filling"))
    if term_reject:
        return term_reject
    return accept("48475 reviewed graham cracker crust contract accepted")


def baguette_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "19170", ("bread", "bakery", "dough"))
    if category_reject:
        return category_reject
    if not product.has_any("baguette"):
        return reject("19170 missing required term(s): baguette")
    term_reject = reject_terms(product, "19170", ("cheese", "dip", "garlic", "herb", "olive", "sandwich", "snack"))
    if term_reject:
        return term_reject
    return accept("19170 reviewed baguette contract accepted")


def watercress_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5222", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("watercress"):
        return reject("5222 missing required term(s): watercress")
    term_reject = reject_terms(product, "5222", ("juice", "pear", "spinach", "vanilla"))
    if term_reject:
        return term_reject
    return accept("5222 reviewed fresh watercress contract accepted")


def mini_chocolate_chip_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "23183", ("baking", "chocolate", "dessert", "topping"))
    if category_reject:
        return category_reject
    if not product.has_any("chocolate"):
        return reject("23183 missing required term(s): chocolate")
    if not product.has_any("chip", "chips", "morsel", "morsels"):
        return reject("23183 missing required term(s): chip")
    if not product.has_any("mini", "miniature"):
        return reject("23183 missing required term(s): mini")
    term_reject = reject_terms(product, "23183", ("bar", "cake", "cookie", "drizzle", "ice", "mug", "sandwich", "white"))
    if term_reject:
        return term_reject
    return accept("23183 reviewed mini chocolate chip contract accepted")


def lump_crabmeat_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "19153", SEAFOOD_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("crab", "crabmeat"):
        return reject("19153 missing required term(s): crab")
    if not product.has_any("lump", "crabmeat"):
        return reject("19153 missing required term(s): lump")
    term_reject = reject_terms(product, "19153", ("cake", "imitation", "roll", "salad", "soup", "stuffed", "stuffing", "surimi", "sushi"))
    if term_reject:
        return term_reject
    return accept("19153 reviewed lump crabmeat contract accepted")


def scallop_contract(product: ProductFacts) -> MatchDecision:
    if not product.category_has_any("fish", "seafood", "shellfish"):
        return reject("19029 category mismatch")
    if product.category_has_any("appetizer", "canned", "dinner", "entree", "meal"):
        return reject("19029 category prepared/canned mismatch")
    if not product.has_any("scallop", "scallops"):
        return reject("19029 missing required term(s): scallop")
    term_reject = reject_terms(
        product,
        "19029",
        ("bacon", "breaded", "flame", "lemon", "medley", "pepper", "potato", "sauce", "scalloped", "seared", "seasoned", "smoked", "squash", "teriyaki", "wrapped"),
    )
    if term_reject:
        return term_reject
    return accept("19029 reviewed sea scallop contract accepted")


def golden_syrup_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "90065", ("syrup", "molasses", "sugar"))
    if category_reject:
        return category_reject
    if not product.has_any("golden", "cane"):
        return reject("90065 missing required term(s): golden|cane")
    if not product.has_any("syrup"):
        return reject("90065 missing required term(s): syrup")
    term_reject = reject_terms(product, "90065", ("apple", "fruit", "maple", "mandarin", "orange", "peach", "pear", "pineapple"))
    if term_reject:
        return term_reject
    return accept("90065 reviewed golden/cane syrup contract accepted")


def white_cake_mix_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "46081", ("cake", "cookie", "cupcake", "baking"))
    if category_reject:
        return category_reject
    if not product.has_all("white", "cake"):
        return reject("46081 missing required term(s): white|cake")
    if not product.has_any("mix"):
        return reject("46081 missing required term(s): mix")
    term_reject = reject_terms(product, "46081", ("cheddar", "chocolate", "frosting", "red", "scone", "velvet"))
    if term_reject:
        return term_reject
    return accept("46081 reviewed white cake mix contract accepted")


def black_eyed_pea_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "90018", ("bean", "beans", "pea", "vegetable", "canned"))
    if category_reject:
        return category_reject
    if not (product.has_phrase("black eyed") or product.has_phrase("black-eyed") or product.has_any("cowpea", "cowpeas")):
        return reject("90018 missing required phrase(s): black eyed")
    term_reject = reject_terms(product, "90018", ("bacon", "green", "snack", "wasabi"))
    if term_reject:
        return term_reject
    return accept("90018 reviewed black-eyed pea contract accepted")


def mixed_salad_green_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "48561", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("green", "greens", "lettuce", "spring"):
        return reject("48561 missing required term(s): greens")
    term_reject = reject_terms(product, "48561", ("bacon", "cheese", "chicken", "dressing", "egg", "kit", "salad kit", "turkey"))
    if term_reject:
        return term_reject
    return accept("48561 reviewed mixed salad greens contract accepted")


def wonton_wrapper_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "12879", ("crust", "dough", "wrapper", "wrappers"))
    if category_reject:
        return category_reject
    if not product.has_any("wonton"):
        return reject("12879 missing required term(s): wonton")
    if not product.has_any("wrapper", "wrappers"):
        return reject("12879 missing required term(s): wrapper")
    term_reject = reject_terms(product, "12879", ("bites", "filled", "mini", "soup"))
    if term_reject:
        return term_reject
    return accept("12879 reviewed wonton wrapper contract accepted")


def ground_flaxseed_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "29575", ("seed", "grain", "spice", "powder"))
    if category_reject:
        return category_reject
    if not product.has_any("flax", "flaxseed", "linaza"):
        return reject("29575 missing required term(s): flax")
    if not product.has_any("ground", "milled", "meal", "molida"):
        return reject("29575 missing required term(s): ground")
    term_reject = reject_terms(product, "29575", ("bar", "cereal", "chia", "chip", "oil", "pumpkin", "sesame", "sunflower"))
    if term_reject:
        return term_reject
    return accept("29575 reviewed ground flaxseed contract accepted")


def colby_monterey_jack_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "1282", ("cheese",))
    if category_reject:
        return category_reject
    if not product.has_any("colby"):
        return reject("1282 missing required term(s): colby")
    if not product.has_any("jack"):
        return reject("1282 missing required term(s): jack")
    if not (product.has_any("monterey") or product.has_phrase("colby jack")):
        return reject("1282 missing required term(s): monterey")
    term_reject = reject_terms(product, "1282", ("cracker", "dip", "mac", "popcorn", "sauce", "snack"))
    if term_reject:
        return term_reject
    return accept("1282 reviewed colby monterey jack contract accepted")


def guacamole_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "13485", ("dip", "salsa", "produce", "prepared", "condiment"))
    if category_reject:
        return category_reject
    if not product.has_any("guacamole"):
        return reject("13485 missing required term(s): guacamole")
    term_reject = reject_terms(product, "13485", ("bacon", "burger", "cheese", "chips", "kit", "sandwich", "salsa"))
    if term_reject:
        return term_reject
    return accept("13485 reviewed guacamole contract accepted")


def tomatoes_green_chile_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "42757", ("tomato", "canned", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("tomato", "tomatoes"):
        return reject("42757 missing required term(s): tomato")
    if not product.has_any("chile", "chiles", "chili", "chilies"):
        return reject("42757 missing required term(s): chile")
    term_reject = reject_terms(product, "42757", ("paste", "salsa", "sauce", "soup"))
    if term_reject:
        return term_reject
    return accept("42757 reviewed tomatoes with green chiles contract accepted")


def turkey_breast_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "51131", ("turkey", "poultry", "meat", "fresh", "frozen"))
    if category_reject:
        return category_reject
    if not product.has_all("turkey", "breast"):
        return reject("51131 missing required term(s): turkey|breast")
    term_reject = reject_terms(product, "51131", ("deli", "ham", "lunchmeat", "sausage", "sliced", "smoked"))
    if term_reject:
        return term_reject
    return accept("51131 reviewed raw turkey breast contract accepted")


def romano_cheese_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "1262", ("cheese",))
    if category_reject:
        return category_reject
    if not product.has_any("romano", "pecorino"):
        return reject("1262 missing required term(s): romano")
    term_reject = reject_terms(product, "1262", ("crumb", "dressing", "pasta", "rice", "sauce"))
    if term_reject:
        return term_reject
    return accept("1262 reviewed romano cheese contract accepted")


def plain_coffee_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "24339", ("coffee",))
    if category_reject:
        return category_reject
    if not product.has_any("coffee"):
        return reject("24339 missing required term(s): coffee")
    term_reject = reject_terms(product, "24339", ("bar", "candy", "creamer", "cream", "ice", "protein", "yogurt"))
    if term_reject:
        return term_reject
    return accept("24339 reviewed plain coffee contract accepted")


def milk_chocolate_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "41521", ("chocolate", "candy", "baking"))
    if category_reject:
        return category_reject
    if not product.has_all("milk", "chocolate"):
        return reject("41521 missing required term(s): milk|chocolate")
    term_reject = reject_terms(product, "41521", ("almond", "beverage", "caramel", "drink", "ice", "milkshake", "peanut", "protein"))
    if term_reject:
        return term_reject
    return accept("41521 reviewed milk chocolate contract accepted")


def baking_soda_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "28003", ("baking", "leavening"))
    if category_reject:
        return category_reject
    if not product.has_all("baking", "soda"):
        return reject("28003 missing required term(s): baking|soda")
    return accept("28003 reviewed baking soda contract accepted")


def pumpkin_seed_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4522", NUT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("pumpkin"):
        return reject("4522 missing required term(s): pumpkin")
    if not product.has_any("seed", "seeds", "pepita", "pepitas"):
        return reject("4522 missing required term(s): seed")
    term_reject = reject_terms(product, "4522", ("bar", "butter", "chocolate", "cluster", "mix", "oil", "trail"))
    if term_reject:
        return term_reject
    return accept("4522 reviewed pumpkin seed contract accepted")


def pizza_dough_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "46509", ("dough", "crust", "pizza", "bread"))
    if category_reject:
        return category_reject
    if not product.has_any("pizza"):
        return reject("46509 missing required term(s): pizza")
    if not product.has_any("dough", "crust"):
        return reject("46509 missing required term(s): dough")
    term_reject = reject_terms(product, "46509", ("baked", "cheese", "garlic", "kit", "meal", "sauce", "snack"))
    if term_reject:
        return term_reject
    return accept("46509 reviewed pizza dough contract accepted")


def clam_juice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "19021", ("juice", "seafood", "clam", "canned"))
    if category_reject:
        return category_reject
    if not product.has_all("clam", "juice"):
        return reject("19021 missing required term(s): clam|juice")
    term_reject = reject_terms(product, "19021", ("tomato", "cocktail", "drink"))
    if term_reject:
        return term_reject
    return accept("19021 reviewed clam juice contract accepted")


def xanthan_gum_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38799", ("baking", "gum", "powder"))
    if category_reject:
        return category_reject
    if not product.has_any("xanthan"):
        return reject("38799 missing required term(s): xanthan")
    return accept("38799 reviewed xanthan gum contract accepted")


def simple_fresh_fruit_contract(esha_code: str, fruit: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, ("fruit", "produce", "pre packaged"))
        if category_reject:
            return category_reject
        if product.category_has_any("drink", "juice", "jam", "jelly", "smoothie", "spread", "syrup"):
            return reject(f"{esha_code} category processed fruit mismatch")
        fruit_terms = (fruit, "kiwifruit") if fruit == "kiwi" else (fruit,)
        if not product.has_any(*fruit_terms):
            return reject(f"{esha_code} missing required term(s): {fruit}")
        term_reject = reject_terms(product, esha_code, ("candy", "chocolate", "dip", "drink", "juice", "mix", "sauce", "snack", "syrup", "yogurt"))
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed fresh {fruit} contract accepted")

    return contract


def salted_peanut_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "49270", NUT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("peanut", "peanuts"):
        return reject("49270 missing required term(s): peanut")
    if not product.has_any("salted", "salt"):
        return reject("49270 missing required term(s): salted")
    term_reject = reject_terms(product, "49270", ("bar", "butter", "candy", "chocolate", "cluster", "mix", "trail"))
    if term_reject:
        return term_reject
    return accept("49270 reviewed salted peanut contract accepted")


def phyllo_dough_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "45528", ("dough", "pastry", "frozen"))
    if category_reject:
        return category_reject
    if not product.has_any("phyllo", "filo"):
        return reject("45528 missing required term(s): phyllo")
    term_reject = reject_terms(product, "45528", ("appetizer", "cup", "filled", "shell"))
    if term_reject:
        return term_reject
    return accept("45528 reviewed phyllo dough contract accepted")


def dry_breadcrumb_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "42004", ("bread", "breadcrumb", "crumb", "baking"))
    if category_reject:
        return category_reject
    if not product.has_any("breadcrumb", "breadcrumbs", "crumb", "crumbs"):
        return reject("42004 missing required term(s): breadcrumb")
    term_reject = reject_terms(product, "42004", ("crouton", "cube", "fish", "meatball", "stuffing"))
    if term_reject:
        return term_reject
    return accept("42004 reviewed dry breadcrumb contract accepted")


def caramel_candy_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "23015", ("candy",))
    if category_reject:
        return category_reject
    if not product.has_any("caramel", "caramels"):
        return reject("23015 missing required term(s): caramel")
    term_reject = reject_terms(product, "23015", ("apple", "dip", "ice", "sauce", "syrup", "topping"))
    if term_reject:
        return term_reject
    return accept("23015 reviewed caramel candy contract accepted")


def semisweet_chocolate_morsel_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "23442", ("baking", "chocolate", "candy", "topping"))
    if category_reject:
        return category_reject
    if not product.has_any("chocolate"):
        return reject("23442 missing required term(s): chocolate")
    if not (product.has_any("semisweet") or product.has_phrase("semi sweet") or product.has_phrase("semi-sweet")):
        return reject("23442 missing required term(s): semisweet")
    if not product.has_any("chip", "chips", "morsel", "morsels"):
        return reject("23442 missing required term(s): morsel")
    term_reject = reject_terms(product, "23442", ("bar", "cookie", "ice", "milk", "sandwich"))
    if term_reject:
        return term_reject
    return accept("23442 reviewed semisweet chocolate morsel contract accepted")


def pecan_piece_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4577", NUT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("pecan", "pecans"):
        return reject("4577 missing required term(s): pecan")
    term_reject = reject_terms(product, "4577", ("bar", "butter", "candy", "chocolate", "pie", "praline", "turtle"))
    if term_reject:
        return term_reject
    return accept("4577 reviewed pecan piece contract accepted")


def instant_coffee_powder_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "20013", ("coffee",))
    if category_reject:
        return category_reject
    if not product.has_any("coffee", "espresso"):
        return reject("20013 missing required term(s): coffee")
    if not product.has_any("instant", "powder"):
        return reject("20013 missing required term(s): instant")
    term_reject = reject_terms(product, "20013", ("candy", "drink", "ice", "ready", "tea"))
    if term_reject:
        return term_reject
    return accept("20013 reviewed instant coffee powder contract accepted")


def devil_food_cake_mix_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "46494", ("cake", "cupcake", "baking", "mix"))
    if category_reject:
        return category_reject
    if not product.has_any("devil", "devils", "devil's"):
        return reject("46494 missing required term(s): devil")
    if not product.has_all("cake", "mix"):
        return reject("46494 missing required term(s): cake|mix")
    term_reject = reject_terms(product, "46494", ("cookie", "frosting", "pudding"))
    if term_reject:
        return term_reject
    return accept("46494 reviewed devil food cake mix contract accepted")


def raw_chicken_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "15071", ("chicken", "poultry", "meat"))
    if category_reject:
        return category_reject
    if not product.has_any("chicken"):
        return reject("15071 missing required term(s): chicken")
    term_reject = reject_terms(product, "15071", ("breaded", "cooked", "deli", "fat", "nugget", "sausage", "strip", "tender"))
    if term_reject:
        return term_reject
    return accept("15071 reviewed raw chicken contract accepted")


def whole_roasting_chicken_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "15130", ("chicken", "poultry", "meat"))
    if category_reject:
        return category_reject
    if not product.has_any("chicken"):
        return reject("15130 missing required term(s): chicken")
    if not (product.has_any("whole", "roaster", "roasting") or product.has_phrase("whole chicken")):
        return reject("15130 missing required term(s): whole|roasting")
    term_reject = reject_terms(
        product,
        "15130",
        ("boneless", "breast", "breasts", "cooked", "drumstick", "drumsticks", "nugget", "sausage", "skinless", "strip", "tender", "thigh", "thighs", "wing", "wings"),
    )
    if term_reject:
        return term_reject
    return accept("15130 reviewed whole roasting chicken contract accepted")


def lowfat_plain_yogurt_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "11967", YOGURT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("yogurt", "yoghurt"):
        return reject("11967 missing required term(s): yogurt")
    if not product.has_any("plain"):
        return reject("11967 missing required term(s): plain")
    if not (product.has_phrase("low fat") or product.has_any("lowfat", "low-fat")):
        return reject("11967 missing required term(s): lowfat")
    term_reject = reject_terms(product, "11967", ("blueberry", "drink", "honey", "smoothie", "strawberry", "tube", "vanilla"))
    if term_reject:
        return term_reject
    return accept("11967 reviewed lowfat plain yogurt contract accepted")


def shortening_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "8278", ("shortening", "oil", "baking"))
    if category_reject:
        return category_reject
    if not product.has_any("shortening", "crisco"):
        return reject("8278 missing required term(s): shortening")
    term_reject = reject_terms(product, "8278", ("butter", "cookies", "lard", "margarine", "spray"))
    if term_reject:
        return term_reject
    return accept("8278 reviewed shortening contract accepted")


def mango_chutney_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "3838", (*CONDIMENT_CATEGORIES, "chutney"))
    if category_reject:
        return category_reject
    if not product.has_all("mango", "chutney"):
        return reject("3838 missing required term(s): mango|chutney")
    term_reject = reject_terms(product, "3838", ("salsa", "snack", "tea", "yogurt"))
    if term_reject:
        return term_reject
    return accept("3838 reviewed mango chutney contract accepted")


def caramel_topping_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "23070", ("syrup", "topping", "dessert"))
    if category_reject:
        return category_reject
    if not product.has_any("caramel"):
        return reject("23070 missing required term(s): caramel")
    if not product.has_any("topping", "sauce", "syrup"):
        return reject("23070 missing required term(s): topping")
    term_reject = reject_terms(product, "23070", ("apple", "bar", "candy", "coffee", "cream", "popcorn"))
    if term_reject:
        return term_reject
    return accept("23070 reviewed caramel topping contract accepted")


def imitation_crab_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "19037", SEAFOOD_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("crab", "crabmeat"):
        return reject("19037 missing required term(s): crab")
    if not product.has_any("imitation", "surimi"):
        return reject("19037 missing required term(s): imitation")
    term_reject = reject_terms(product, "19037", ("cake", "dip", "ravioli", "salad", "sushi"))
    if term_reject:
        return term_reject
    return accept("19037 reviewed imitation crab contract accepted")


def extra_firm_tofu_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "12893", ("meat", "plant", "tofu", "vegetarian"))
    if category_reject:
        return category_reject
    if not product.has_any("tofu"):
        return reject("12893 missing required term(s): tofu")
    if not product.has_any("firm"):
        return reject("12893 missing required term(s): firm")
    term_reject = reject_terms(product, "12893", ("dessert", "dip", "drink", "noodle", "soup", "spread"))
    if term_reject:
        return term_reject
    return accept("12893 reviewed extra firm tofu contract accepted")


def dry_roasted_peanut_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4756", NUT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("peanut", "peanuts"):
        return reject("4756 missing required term(s): peanut")
    if not product.has_any("roasted"):
        return reject("4756 missing required term(s): roasted")
    term_reject = reject_terms(product, "4756", ("bar", "butter", "candy", "chocolate", "cracker", "honey", "mix", "trail"))
    if term_reject:
        return term_reject
    return accept("4756 reviewed dry roasted peanut contract accepted")


def generic_olive_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "9539", ("olive", "olives", "pickle", "relish", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("olive", "olives", "olif"):
        return reject("9539 missing required term(s): olive")
    term_reject = reject_terms(product, "9539", ("hummus", "oil", "salad", "snack", "tapenade"))
    if term_reject:
        return term_reject
    return accept("9539 reviewed olive contract accepted")


def generic_tortilla_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "51362", TORTILLA_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("tortilla", "tortillas"):
        return reject("51362 missing required term(s): tortilla")
    term_reject = reject_terms(product, "51362", ("bowl", "chip", "chips", "filled", "kit", "meal", "pizza", "taquito"))
    if term_reject:
        return term_reject
    return accept("51362 reviewed generic tortilla contract accepted")


def baked_beans_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "27301", ("bean", "legume", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("bean", "beans"):
        return reject("27301 missing required term(s): beans")
    if not product.has_any("baked"):
        return reject("27301 missing required term(s): baked")
    term_reject = reject_terms(product, "27301", ("black", "coffee", "espresso", "green", "kidney", "refried", "snack"))
    if term_reject:
        return term_reject
    return accept("27301 reviewed baked beans contract accepted")


def vermouth_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "35205", (*WINE_CATEGORIES, "cooking", "sauce"))
    if category_reject:
        return category_reject
    if not product.has_any("vermouth"):
        return reject("35205 missing required term(s): vermouth")
    term_reject = reject_terms(product, "35205", ("beef", "meal", "sauce"))
    if term_reject:
        return term_reject
    return accept("35205 reviewed vermouth contract accepted")


def espresso_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "33295", ("coffee",))
    if category_reject:
        return category_reject
    if not product.has_any("espresso"):
        return reject("33295 missing required term(s): espresso")
    term_reject = reject_terms(product, "33295", ("bar", "bean", "beans", "candy", "chocolate", "cream", "ice", "protein"))
    if term_reject:
        return term_reject
    return accept("33295 reviewed espresso contract accepted")


def flax_seed_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4770", NUT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("flax", "flaxseed"):
        return reject("4770 missing required term(s): flax")
    term_reject = reject_terms(product, "4770", ("bar", "bread", "cereal", "chia", "oil", "snack"))
    if term_reject:
        return term_reject
    return accept("4770 reviewed flax seed contract accepted")


def popped_popcorn_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "37597", ("popcorn", "snack"))
    if category_reject:
        return category_reject
    if not product.has_any("popcorn"):
        return reject("37597 missing required term(s): popcorn")
    term_reject = reject_terms(
        product,
        "37597",
        ("candy", "caramel", "cheese", "chicken", "chocolate", "kernel", "kernels", "seasoning", "shrimp"),
    )
    if term_reject:
        return term_reject
    return accept("37597 reviewed popped popcorn contract accepted")


def fresh_spinach_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6863", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("spinach"):
        return reject("6863 missing required term(s): spinach")
    term_reject = reject_terms(product, "6863", ("dip", "kit", "meal", "pizza", "quiche", "soup"))
    if term_reject:
        return term_reject
    return accept("6863 reviewed fresh spinach contract accepted")


def white_kidney_bean_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "17741", BEAN_CATEGORIES)
    if category_reject:
        return category_reject
    if not (product.has_phrase("white kidney beans") or product.has_any("cannellini")):
        return reject("17741 missing required term(s): white kidney/cannellini")
    term_reject = reject_terms(product, "17741", ("baked", "black", "green", "meal", "pinto", "refried", "salad", "soup"))
    if term_reject:
        return term_reject
    return accept("17741 reviewed white kidney bean contract accepted")


def skirt_steak_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38987", (*MEAT_CATEGORIES, "beef"))
    if category_reject:
        return category_reject
    if not product.has_any("skirt"):
        return reject("38987 missing required term(s): skirt")
    if not product.has_any("steak"):
        return reject("38987 missing required term(s): steak")
    term_reject = reject_terms(product, "38987", ("bourbon", "carne", "chimichurri", "dinner", "fajita", "fajitas", "garlic", "honey", "jerky", "marinated", "meal", "potatoes", "sandwich", "sauce", "seasoned", "seasoning", "teriyaki"))
    if term_reject:
        return term_reject
    return accept("38987 reviewed skirt steak contract accepted")


def french_style_green_bean_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6251", ("canned", "frozen", "vegetable", "vegetables"))
    if category_reject:
        return category_reject
    if not product.has_all("green", "bean"):
        return reject("6251 missing required term(s): green|bean")
    if not (product.has_any("french") or product.has_phrase("french style") or product.has_phrase("french cut")):
        return reject("6251 missing required term(s): french")
    term_reject = reject_terms(product, "6251", ("almondine", "casserole", "dish", "jelly", "meal", "soup"))
    if term_reject:
        return term_reject
    return accept("6251 reviewed French-style green bean contract accepted")


def beef_roast_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "27980", (*MEAT_CATEGORIES, "beef"))
    if category_reject:
        return category_reject
    if not product.has_any("beef"):
        return reject("27980 missing required term(s): beef")
    if not product.has_any("roast"):
        return reject("27980 missing required term(s): roast")
    term_reject = reject_terms(product, "27980", ("cat", "dinner", "dog", "hash", "meal", "pork", "sandwich", "seasoning"))
    if term_reject:
        return term_reject
    return accept("27980 reviewed beef roast contract accepted")


def juniper_berry_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "35078", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("juniper"):
        return reject("35078 missing required term(s): juniper")
    term_reject = reject_terms(product, "35078", ("glaze", "ketchup", "meal", "sauce"))
    if term_reject:
        return term_reject
    return accept("35078 reviewed juniper berry contract accepted")


def raw_cane_sugar_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "49315", BAKING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("sugar"):
        return reject("49315 missing required term(s): sugar")
    if not (product.has_any("cane", "turbinado", "raw") or product.has_phrase("raw cane")):
        return reject("49315 missing required term(s): cane/raw/turbinado")
    term_reject = reject_terms(product, "49315", ("beverage", "brown", "confectioners", "powdered", "substitute"))
    if term_reject:
        return term_reject
    return accept("49315 reviewed raw cane sugar contract accepted")


def stuffed_green_olive_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "7846", ("olive", "olives", "pickle", "relish", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("olive", "olives", "olif"):
        return reject("7846 missing required term(s): olive")
    if not product.has_any("stuffed", "pimento"):
        return reject("7846 missing required term(s): stuffed/pimento")
    term_reject = reject_terms(product, "7846", ("cheese", "loaf", "salad", "spread", "tapenade"))
    if term_reject:
        return term_reject
    return accept("7846 reviewed stuffed green olive contract accepted")


def white_pepper_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26037", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("white"):
        return reject("26037 missing required term(s): white")
    if not product.has_any("pepper", "peppercorn"):
        return reject("26037 missing required term(s): pepper")
    term_reject = reject_terms(product, "26037", ("cheese", "dinner", "gravy", "macaroni", "sauce"))
    if term_reject:
        return term_reject
    return accept("26037 reviewed white pepper contract accepted")


def ciabatta_bun_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "23640", ("bread", "bun", "roll", "bakery"))
    if category_reject:
        return category_reject
    if not product.has_any("ciabatta"):
        return reject("23640 missing required term(s): ciabatta")
    term_reject = reject_terms(product, "23640", ("cheese", "garlic", "pizza", "sandwich"))
    if term_reject:
        return term_reject
    return accept("23640 reviewed ciabatta bun contract accepted")


def flank_steak_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "58267", (*MEAT_CATEGORIES, "beef"))
    if category_reject:
        return category_reject
    if not product.has_any("flank"):
        return reject("58267 missing required term(s): flank")
    if not product.has_any("steak"):
        return reject("58267 missing required term(s): steak")
    term_reject = reject_terms(product, "58267", ("carne", "chimichurri", "citrus", "dinner", "fajita", "fajitas", "garlic", "jerky", "marinated", "meal", "peppered", "pineapple", "sandwich", "sauce", "seasoned", "seasoning", "teriyaki"))
    if term_reject:
        return term_reject
    return accept("58267 reviewed flank steak contract accepted")


def refrigerated_breadstick_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "42257", ("baking", "bread", "bun", "dough"))
    if category_reject:
        return category_reject
    if not product.has_any("breadstick", "breadsticks"):
        return reject("42257 missing required term(s): breadstick")
    term_reject = reject_terms(product, "42257", ("chips", "cookie", "cracker", "crouton", "pretzel"))
    if term_reject:
        return term_reject
    return accept("42257 reviewed refrigerated breadstick contract accepted")


def candied_red_cherry_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "48217", ("baking", "canned", "fruit", "topping", "pickle", "olive"))
    if category_reject:
        return category_reject
    if not (product.has_any("cherries", "cherry") and (product.has_any("maraschino", "candied") or product.has_phrase("red glace"))):
        return reject("48217 missing required term(s): candied/maraschino cherry")
    term_reject = reject_terms(product, "48217", ("chocolate", "cobbler", "ice", "pie", "turnover"))
    if term_reject:
        return term_reject
    return accept("48217 reviewed candied red cherry contract accepted")


def canadian_bacon_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "12008", (*MEAT_CATEGORIES, "bacon"))
    if category_reject:
        return category_reject
    if not product.has_all("canadian", "bacon"):
        return reject("12008 missing required term(s): canadian|bacon")
    term_reject = reject_terms(product, "12008", ("breakfast", "muffin", "pizza", "sandwich", "vegetarian"))
    if term_reject:
        return term_reject
    return accept("12008 reviewed canadian bacon contract accepted")


def chili_paste_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "34574", (*CONDIMENT_CATEGORIES, "pepper"))
    if category_reject:
        return category_reject
    if not product.has_any("chili", "chile"):
        return reject("34574 missing required term(s): chili")
    if not product.has_any("paste"):
        return reject("34574 missing required term(s): paste")
    term_reject = reject_terms(product, "34574", ("bean", "chips", "meal", "sauce"))
    if term_reject:
        return term_reject
    return accept("34574 reviewed chili paste contract accepted")


def chili_garlic_sauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "33128", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("chili", "chile"):
        return reject("33128 missing required term(s): chili")
    if not product.has_any("garlic"):
        return reject("33128 missing required term(s): garlic")
    if not product.has_any("sauce"):
        return reject("33128 missing required term(s): sauce")
    term_reject = reject_terms(product, "33128", ("chips", "meal", "seasoning"))
    if term_reject:
        return term_reject
    return accept("33128 reviewed chili garlic sauce contract accepted")


def pomegranate_juice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4928", ("beverage", "drink", "juice"))
    if category_reject:
        return category_reject
    if not product.has_any("pomegranate"):
        return reject("4928 missing required term(s): pomegranate")
    if not product.has_any("juice"):
        return reject("4928 missing required term(s): juice")
    term_reject = reject_terms(product, "4928", ("blueberry", "cocktail", "drink", "mango", "sparkling", "tea"))
    if term_reject:
        return term_reject
    return accept("4928 reviewed pomegranate juice contract accepted")


def frozen_hash_browns_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5589", ("frozen", "potato", "vegetable"))
    if category_reject:
        return category_reject
    if not (product.has_phrase("hash brown") or product.has_phrase("hash browns") or product.has_any("hashbrowns")):
        return reject("5589 missing required term(s): hash browns")
    term_reject = reject_terms(product, "5589", ("breakfast", "casserole", "cheese", "loaded", "meal", "sandwich"))
    if term_reject:
        return term_reject
    return accept("5589 reviewed frozen hash browns contract accepted")


def chocolate_shavings_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4966", ("baking", "chocolate", "dessert", "topping"))
    if category_reject:
        return category_reject
    if not product.has_any("chocolate"):
        return reject("4966 missing required term(s): chocolate")
    if not product.has_any("shaving", "shavings", "curl", "curls"):
        return reject("4966 missing required term(s): shavings")
    term_reject = reject_terms(product, "4966", ("bar", "cookie", "drink", "ice", "syrup"))
    if term_reject:
        return term_reject
    return accept("4966 reviewed chocolate shavings contract accepted")


def grapefruit_juice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "794", ("beverage", "drink", "juice"))
    if category_reject:
        return category_reject
    if not product.has_any("grapefruit"):
        return reject("794 missing required term(s): grapefruit")
    if not product.has_any("juice"):
        return reject("794 missing required term(s): juice")
    term_reject = reject_terms(product, "794", ("cocktail", "drink", "orange", "soda"))
    if term_reject:
        return term_reject
    return accept("794 reviewed grapefruit juice contract accepted")


def oyster_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "19026", SEAFOOD_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("oyster", "oysters"):
        return reject("19026 missing required term(s): oyster")
    term_reject = reject_terms(product, "19026", ("breaded", "cracker", "fried", "mushroom", "sauce", "smoked"))
    if term_reject:
        return term_reject
    return accept("19026 reviewed oyster contract accepted")


def fresh_white_mushroom_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "7351", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if product.category_has_any("canned", "frozen", "prepared", "sauce", "soup"):
        return reject("7351 category state mismatch")
    if not product.has_any("white") or not product.has_any("mushroom", "mushrooms"):
        return reject("7351 missing required term(s): white|mushroom")
    term_reject = reject_terms(product, "7351", ("gravy", "marinated", "medley", "onion", "onions", "pizza", "seasoned", "soup", "stir"))
    if term_reject:
        return term_reject
    return accept("7351 reviewed fresh white mushroom contract accepted")


def refrigerated_biscuit_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "16621", ("baking", "dough", "bread", "bakery", "crust"))
    if category_reject:
        return category_reject
    if not product.has_any("biscuit", "biscuits"):
        return reject("16621 missing required term(s): biscuit")
    term_reject = reject_terms(product, "16621", ("blueberry", "cookie", "cookies", "egg", "sandwich", "sausage", "scone"))
    if term_reject:
        return term_reject
    return accept("16621 reviewed refrigerated biscuit contract accepted")


def dark_beer_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "34067", ALCOHOL_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("beer", "stout", "porter"):
        return reject("34067 missing required term(s): beer")
    if not (product.has_any("dark", "stout", "porter") or product.has_phrase("black lager")):
        return reject("34067 missing required term(s): dark")
    term_reject = reject_terms(product, "34067", ("batter", "butter", "cake", "cheese", "chocolate", "drink", "non", "root", "sauce"))
    if term_reject:
        return term_reject
    return accept("34067 reviewed dark beer contract accepted")


def ladyfinger_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "15424", ("cookie", "bakery", "biscuit"))
    if category_reject:
        return category_reject
    if not product.has_any("ladyfinger", "ladyfingers"):
        return reject("15424 missing required term(s): ladyfinger")
    term_reject = reject_terms(product, "15424", ("lemon", "sandwich"))
    if term_reject:
        return term_reject
    return accept("15424 reviewed ladyfinger contract accepted")


def thousand_island_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "295", (*CONDIMENT_CATEGORIES, "dressing", "mayonnaise"))
    if category_reject:
        return category_reject
    if not product.has_all("thousand", "island"):
        return reject("295 missing required term(s): thousand|island")
    if not product.has_any("dressing", "sauce"):
        return reject("295 missing required term(s): dressing")
    term_reject = reject_terms(product, "295", ("fat", "free", "italian", "light", "ranch", "vinaigrette"))
    if term_reject:
        return term_reject
    return accept("295 reviewed thousand island dressing contract accepted")


def prawn_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "73123", SEAFOOD_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("prawn", "prawns"):
        return reject("73123 missing required term(s): prawn")
    term_reject = reject_terms(product, "73123", ("cracker", "crackers", "dumpling", "gyoza", "salad", "vegetarian"))
    if term_reject:
        return term_reject
    return accept("73123 reviewed prawn contract accepted")


def rice_noodle_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "33770", ("noodle", "noodles", "pasta"))
    if category_reject:
        return category_reject
    if not product.has_any("rice"):
        return reject("33770 missing required term(s): rice")
    if not product.has_any("noodle", "noodles", "stick", "sticks"):
        return reject("33770 missing required term(s): noodle")
    term_reject = reject_terms(product, "33770", ("dinner", "egg", "meal", "pad", "ramen", "sauce", "soup", "tagliatelle"))
    if term_reject:
        return term_reject
    return accept("33770 reviewed dry rice noodle contract accepted")


def silken_tofu_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "12896", ("meat", "plant", "tofu", "vegetarian"))
    if category_reject:
        return category_reject
    if not product.has_all("silken", "tofu"):
        return reject("12896 missing required term(s): silken|tofu")
    term_reject = reject_terms(product, "12896", ("dip", "drink", "noodle", "soup", "spread"))
    if term_reject:
        return term_reject
    return accept("12896 reviewed silken tofu contract accepted")


def lemonade_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4794", ("beverage", "drink", "juice"))
    if category_reject:
        return category_reject
    if not product.has_any("lemonade"):
        return reject("4794 missing required term(s): lemonade")
    term_reject = reject_terms(product, "4794", ("beer", "hard", "tea", "vodka"))
    if term_reject:
        return term_reject
    return accept("4794 reviewed lemonade contract accepted")


def habanero_pepper_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "37877", (*VEGETABLE_CATEGORIES, "pepper"))
    if category_reject:
        return category_reject
    if product.category_has_any("canned", "sauce", "salsa", "pickle", "relish"):
        return reject("37877 category state mismatch")
    if not product.has_any("habanero"):
        return reject("37877 missing required term(s): habanero")
    term_reject = reject_terms(product, "37877", ("cheese", "chips", "hot", "pickled", "sauce", "salsa"))
    if term_reject:
        return term_reject
    return accept("37877 reviewed fresh habanero pepper contract accepted")


def sprite_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "20032", ("beverage", "drink", "soda", "soft"))
    if category_reject:
        return category_reject
    if not product.has_any("sprite"):
        return reject("20032 missing required term(s): sprite")
    term_reject = reject_terms(product, "20032", ("candy", "cocktail", "fruit", "gummy", "zero"))
    if term_reject:
        return term_reject
    return accept("20032 reviewed Sprite contract accepted")


def craisin_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "3487", ("dried fruit", "fruit", "snack"))
    if category_reject:
        return category_reject
    if not (product.has_any("craisin", "craisins") or (product.has_any("dried") and product.has_any("cranberry", "cranberries"))):
        return reject("3487 missing required term(s): craisin|dried cranberry")
    term_reject = reject_terms(product, "3487", ("almond", "bar", "chocolate", "cluster", "granola", "juice", "mix", "raisin", "roll", "salad", "sauce", "trail", "turkey"))
    if term_reject:
        return term_reject
    return accept("3487 reviewed Craisin contract accepted")


def hot_dog_bun_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "15455", ("bread", "bun", "buns", "roll", "bakery"))
    if category_reject:
        return category_reject
    if not (product.has_phrase("hot dog bun") or product.has_phrase("hotdog bun") or (product.has_any("dog", "hotdog") and product.has_any("bun", "buns"))):
        return reject("15455 missing required phrase(s): hot dog bun")
    term_reject = reject_terms(product, "15455", ("hamburger", "slider", "stuffing"))
    if term_reject:
        return term_reject
    return accept("15455 reviewed hot dog bun contract accepted")


def black_pepper_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "90212", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("black", "pepper"):
        return reject("90212 missing required term(s): black|pepper")
    term_reject = reject_terms(
        product,
        "90212",
        (
            "bean",
            "burger",
            "caesar",
            "dip",
            "garlic",
            "kit",
            "olive",
            "onion",
            "rice",
            "rub",
            "salmon",
            "salsa",
            "salt",
            "seasoned",
            "soup",
            "steak",
            "tapenade",
            "tuna",
            "turmeric",
            "white",
        ),
    )
    if term_reject:
        return term_reject
    return accept("90212 reviewed black pepper contract accepted")


def fresh_garlic_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "49598", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("garlic"):
        return reject("49598 missing required term(s): garlic")
    if not (product.has_any("fresh", "peeled") or product.ingredients_have_any("garlic")):
        return reject("49598 missing required term(s): fresh/peeled")
    term_reject = reject_terms(
        product,
        "49598",
        (
            "bread",
            "cheese",
            "dip",
            "dressing",
            "hummus",
            "marinated",
            "minced",
            "oil",
            "paste",
            "pickle",
            "pickled",
            "pizza",
            "powder",
            "salt",
            "sauce",
            "seasoning",
            "spread",
            "stuffed",
        ),
    )
    if term_reject:
        return term_reject
    return accept("49598 reviewed fresh garlic contract accepted")


def brown_egg_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "37777", ("egg", "eggs"))
    if category_reject:
        return category_reject
    if not product.has_any("egg", "eggs"):
        return reject("37777 missing required term(s): egg")
    if not product.has_any("brown"):
        return reject("37777 missing required term(s): brown")
    term_reject = reject_terms(product, "37777", ("bites", "liquid", "noodle", "sandwich", "substitute", "white", "whites"))
    if term_reject:
        return term_reject
    return accept("37777 reviewed brown egg contract accepted")


def vanilla_extract_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26624", ("baking", "extract", "extracts", "spice"))
    if category_reject:
        return category_reject
    if not product.has_any("vanilla"):
        return reject("26624 missing required term(s): vanilla")
    if not product.has_any("extract", "extracts", "flavor", "flavoring"):
        return reject("26624 missing required term(s): extract/flavor")
    term_reject = reject_terms(product, "26624", ("candle", "coffee", "creamer", "frosting", "ice", "protein", "syrup", "yogurt"))
    if term_reject:
        return term_reject
    return accept("26624 reviewed vanilla extract contract accepted")


def brown_sugar_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "63413", BAKING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("sugar"):
        return reject("63413 missing required term(s): sugar")
    if not product.has_any("brown"):
        return reject("63413 missing required term(s): brown")
    term_reject = reject_terms(
        product,
        "63413",
        ("blend", "colored", "confectioner", "confectioners", "cube", "demerara", "granulated", "powdered", "sprinkle", "sweetener", "zero"),
    )
    if term_reject:
        return term_reject
    return accept("63413 reviewed brown sugar contract accepted")


def parmesan_cheese_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "1251", ("cheese",))
    if category_reject:
        return category_reject
    if not product.has_any("parmesan"):
        return reject("1251 missing required term(s): parmesan")
    term_reject = reject_terms(
        product,
        "1251",
        (
            "asiago",
            "blend",
            "cheddar",
            "cracker",
            "fontina",
            "four",
            "garlic",
            "mozzarella",
            "pasta",
            "pizza",
            "provolone",
            "red",
            "rice",
            "romano",
            "sauce",
            "three",
        ),
    )
    if term_reject:
        return term_reject
    return accept("1251 reviewed parmesan cheese contract accepted")


def sour_cream_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "555", ("cream",))
    if category_reject:
        return category_reject
    if not product.has_all("sour", "cream"):
        return reject("555 missing required term(s): sour|cream")
    term_reject = reject_terms(
        product,
        "555",
        ("alternative", "chip", "dairy-free", "dip", "free", "ice", "milk-free", "plant", "pop", "pops", "snack"),
    )
    if term_reject:
        return term_reject
    return accept("555 reviewed sour cream contract accepted")


def cream_cheese_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "1015", ("cheese",))
    if category_reject:
        return category_reject
    if not product.has_phrase("cream cheese"):
        return reject("1015 missing required phrase(s): cream cheese")
    term_reject = reject_terms(
        product,
        "1015",
        (
            "alternative",
            "brie",
            "cake",
            "cheddar",
            "colby",
            "cranberry",
            "dairy-free",
            "free",
            "garden",
            "italian",
            "jalapeno",
            "king",
            "lox",
            "mexican",
            "monterey",
            "mozzarella",
            "muenster",
            "pczki",
            "powdered",
            "salmon",
            "scallion",
            "shredded",
            "strawberry",
            "vegetable",
        ),
    )
    if term_reject:
        return term_reject
    return accept("1015 reviewed cream cheese contract accepted")


def honey_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "25132", ("honey",))
    if category_reject:
        return category_reject
    if not product.has_any("honey"):
        return reject("25132 missing required term(s): honey")
    term_reject = reject_terms(
        product,
        "25132",
        ("bourbon", "chipotle", "cinnamon", "cocoa", "flavor", "hot", "lavender", "lemon", "mango", "pepper", "salted", "spread", "vanilla"),
    )
    if term_reject:
        return term_reject
    return accept("25132 reviewed plain honey contract accepted")


def chicken_breast_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "15054", ("chicken", "poultry", "meat"))
    if category_reject:
        return category_reject
    if not product.has_all("chicken", "breast"):
        return reject("15054 missing required term(s): chicken|breast")
    if not (product.has_any("skinles") or product.ingredients_have_any("skinles")):
        return reject("15054 missing required term(s): skinless")
    term_reject = reject_terms(
        product,
        "15054",
        (
            "applewood",
            "bone",
            "breaded",
            "chipotle",
            "cooked",
            "cordon",
            "deli",
            "fajita",
            "fajitas",
            "grilled",
            "honey",
            "italian",
            "marinated",
            "nugget",
            "parmesan",
            "ready",
            "seasoned",
            "shawarma",
            "smokehouse",
            "split",
            "sriracha",
            "strip",
            "stuffed",
            "tender",
            "teriyaki",
            "thai",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("applewood", "garlic", "lime", "mustard", "onion", "smoke", "soy", "spices", "sugar", "worcestershire")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("15054 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("15054 reviewed skinless raw chicken breast contract accepted")


def heavy_whipping_cream_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "502", ("cream",))
    if category_reject:
        return category_reject
    if not product.has_all("heavy", "whipping", "cream"):
        return reject("502 missing required term(s): heavy|whipping|cream")
    term_reject = reject_terms(product, "502", ("coffee", "ice", "topping", "whipped"))
    if term_reject:
        return term_reject
    return accept("502 reviewed heavy whipping cream contract accepted")


def light_cream_contract(product: ProductFacts) -> MatchDecision:
    if product.category_has_any("health", "medicine", "skin", "beauty"):
        return reject("501 category mismatch")
    if not product.has_any("cream", "crema"):
        return reject("501 missing required term(s): cream|crema")
    if not (
        product.has_phrase("light cream")
        or product.has_phrase("lite cream")
        or product.has_phrase("table cream")
        or product.has_phrase("coffee cream")
        or product.has_phrase("media crema")
        or product.has_phrase("crema mexicana")
        or product.has_all("light", "cream")
        or product.has_all("lite", "cream")
    ):
        return reject("501 missing required term(s): light|table|coffee cream")
    term_reject = reject_terms(
        product,
        "501",
        ("antacid", "cheese", "ice", "salad", "skin", "soup", "sour", "tablet", "tablets", "topping", "whipped"),
    )
    if term_reject:
        return term_reject
    if (
        not product.category_has_any("bakery", "baking", "cream", "dairy", "hispanic", "international")
        and not product.has_any("crema", "media")
    ):
        return reject("501 category mismatch")
    return accept("501 reviewed light/table cream contract accepted")


def fresh_carrot_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "7320", ("pre packaged", "produce", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("carrot", "carrots"):
        return reject("7320 missing required term(s): carrot")
    if product.category_has_any("canned", "frozen", "juice", "prepared", "processed"):
        return reject("7320 category state mismatch")
    term_reject = reject_terms(
        product,
        "7320",
        ("cake", "celery", "chili", "drink", "gummy", "juice", "meets", "nectar", "puree", "ranch", "seasoning", "snack"),
    )
    if term_reject:
        return term_reject
    return accept("7320 reviewed fresh carrot contract accepted")


def green_onion_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5709", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    has_green_onion_identity = (
        product.has_phrase("green onion")
        or product.has_phrase("green onions")
        or product.has_all("green", "onion")
        or product.has_all("green", "onions")
        or product.has_any("scallion", "scallions")
    )
    if not has_green_onion_identity:
        return reject("5709 missing required term(s): green onion/scallion")
    if product.category_has_any("canned", "frozen", "juice", "oil", "prepared", "processed", "sauce"):
        return reject("5709 category state mismatch")
    term_reject = reject_terms(product, "5709", ("dip", "dried", "freeze", "minced", "paste", "powder", "ring", "soup"))
    if term_reject:
        return term_reject
    return accept("5709 reviewed fresh green onion contract accepted")


def fresh_cilantro_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "92175", ("herb", "spice", "produce", "pre packaged", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("cilantro"):
        return reject("92175 missing required term(s): cilantro")
    term_reject = reject_terms(product, "92175", ("dressing", "dry", "dried", "hummus", "paste", "rice", "sauce", "seasoning"))
    if term_reject:
        return term_reject
    return accept("92175 reviewed fresh cilantro contract accepted")


def fresh_lemon_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "3853", ("fruit", "produce", "pre packaged"))
    if category_reject:
        return category_reject
    if not product.has_any("lemon", "lemons"):
        return reject("3853 missing required term(s): lemon")
    term_reject = reject_terms(product, "3853", ("bar", "candy", "curd", "drink", "juice", "pie", "sauce", "soda", "tea"))
    if term_reject:
        return term_reject
    return accept("3853 reviewed fresh lemon contract accepted")


def simple_juice_contract(esha_code: str, fruit: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, ("juice", "beverage", "drink"))
        if category_reject:
            return category_reject
        if not product.has_all(fruit, "juice"):
            return reject(f"{esha_code} missing required term(s): {fruit}|juice")
        fruit_blend_terms = (
            "apple",
            "banana",
            "carrot",
            "cranberry",
            "cucumber",
            "grape",
            "lemongrass",
            "lemon",
            "mandarin",
            "mango",
            "passion",
            "peach",
            "pineapple",
            "pomegranate",
            "spinach",
            "strawberry",
            "tangerine",
            "vegetable",
        )
        blend_hits = [term for term in fruit_blend_terms if term != fruit and product.has_any(term)]
        if blend_hits:
            return reject(f"{esha_code} excluded blend term(s): " + "|".join(blend_hits))
        ingredient_blend_hits = [
            term
            for term in fruit_blend_terms
            if term != fruit and product.ingredients_have_any(term)
        ]
        if ingredient_blend_hits:
            return reject(f"{esha_code} excluded ingredient blend term(s): " + "|".join(ingredient_blend_hits))
        if product.ingredients and not (
            product.ingredients_have_any(fruit)
            or product.ingredients_have_phrase(f"{fruit} juice")
            or product.ingredients_have_phrase(f"{fruit}s")
        ):
            return reject(f"{esha_code} missing ingredient term(s): {fruit}")
        if (
            product.has_phrase("in juice")
            or product.has_phrase("in fruit juice")
            or product.has_phrase("in 100% fruit juice")
        ):
            return reject(f"{esha_code} packed fruit in juice state mismatch")
        term_reject = reject_terms(
            product,
            esha_code,
            (
                "blend",
                "chunks",
                "citrus",
                "cocktail",
                "cups",
                "drink",
                "flavored",
                "gold",
                "holiday",
                "nectar",
                "pieces",
                "pouch",
                "punch",
                "segments",
                "slices",
                "soda",
                "tea",
                "tidbits",
            ),
        )
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed {fruit} juice contract accepted")

    return contract


def simple_cheese_contract(esha_code: str, cheese: str, exclude: tuple[str, ...] = ()) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, ("cheese",))
        if category_reject:
            return category_reject
        if not product.has_any(cheese):
            return reject(f"{esha_code} missing required term(s): {cheese}")
        term_reject = reject_terms(
            product,
            esha_code,
            ("cracker", "dip", "imitation", "pasta", "pizza", "sauce", "snack", "snacking", "string", "style") + exclude,
        )
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed {cheese} cheese contract accepted")

    return contract


def dried_herb_contract(esha_code: str, herb: str, exclude: tuple[str, ...] = ()) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, SEASONING_CATEGORIES)
        if category_reject:
            return category_reject
        herb_terms = (herb, f"{herb}s")
        if not product.has_any(*herb_terms):
            return reject(f"{esha_code} missing required term(s): {herb}")
        term_reject = reject_terms(
            product,
            esha_code,
            ("bar", "chicken", "dip", "dressing", "oil", "pasta", "rice", "salt", "sauce", "seasoning", "soup", "spray", "spritzers") + exclude,
        )
        if term_reject:
            return term_reject
        ingredient_hits = [term for term in ("oil", "salt", "sugar") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)]
        if ingredient_hits:
            return reject(f"{esha_code} excluded ingredient term(s): " + "|".join(ingredient_hits))
        return accept(f"{esha_code} reviewed dried {herb} contract accepted")

    return contract


def tomato_paste_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "9161", ("tomato", "tomatoes", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_all("tomato", "paste"):
        return reject("9161 missing required term(s): tomato|paste")
    term_reject = reject_terms(
        product,
        "9161",
        ("alfredo", "bruschetta", "diced", "ketchup", "marinara", "pasta", "pizza", "salsa", "sauce", "soup", "spaghetti", "stewed"),
    )
    if term_reject:
        return term_reject
    return accept("9161 reviewed tomato paste contract accepted")


def egg_white_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "19507", ("egg", "eggs", "substitute"))
    if category_reject:
        return category_reject
    if not product.has_any("egg", "eggs") or not product.has_any("white", "whites"):
        return reject("19507 missing required term(s): egg|white")
    term_reject = reject_terms(
        product,
        "19507",
        ("bar", "bite", "bites", "breakfast", "cheese", "muffin", "noodle", "omelet", "plant", "sandwich", "wrap", "yolk"),
    )
    if term_reject:
        return term_reject
    if product.ingredients and not (product.ingredients_have_any("egg", "eggs") and product.ingredients_have_any("white", "whites")):
        return reject("19507 missing ingredient term(s): egg|white")
    return accept("19507 reviewed egg white contract accepted")


def balsamic_vinegar_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "51162", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("balsamic", "vinegar"):
        return reject("51162 missing required term(s): balsamic|vinegar")
    term_reject = reject_terms(
        product,
        "51162",
        ("blackberry", "dressing", "fig", "glaze", "golden", "honey", "ketchup", "marinade", "pomegranate", "raspberry", "reduction", "rose", "sauce", "vinaigrette", "white"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("blackberry", "fig", "pomegranate", "raspberry")
        if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)
    ]
    if ingredient_hits:
        return reject("51162 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("51162 reviewed balsamic vinegar contract accepted")


def white_vinegar_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "27202", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("white", "vinegar"):
        return reject("27202 missing required term(s): white|vinegar")
    if not product.has_any("distilled"):
        return reject("27202 missing required term(s): distilled")
    term_reject = reject_terms(
        product,
        "27202",
        ("apple", "balsamic", "cider", "cleaning", "dressing", "garlic", "herb", "rice", "seasoned", "wine"),
    )
    if term_reject:
        return term_reject
    return accept("27202 reviewed distilled white vinegar contract accepted")


def half_and_half_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "500", ("cream", "dairy"))
    if category_reject:
        return category_reject
    if not product.has_any("half"):
        return reject("500 missing required term(s): half")
    term_reject = reject_terms(
        product,
        "500",
        ("chocolate", "coffee", "creamer", "creamers", "fat", "free", "nonfat", "skim", "singles", "sugar", "vanilla"),
    )
    if term_reject:
        return term_reject
    ingredient_rejects = ("artificial", "corn", "flavor", "flavors", "sugar", "syrup")
    ingredient_hits = [term for term in ingredient_rejects if product.ingredients_have_any(term)]
    if ingredient_hits:
        return reject("500 excluded ingredient term(s): " + "|".join(ingredient_hits))
    if product.ingredients and not product.ingredients_have_any("cream"):
        return reject("500 missing ingredient term(s): cream")
    return accept("500 reviewed half and half contract accepted")


def garlic_salt_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "669", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_phrase("garlic salt"):
        return reject("669 missing required phrase(s): garlic salt")
    term_reject = reject_terms(
        product,
        "669",
        ("black", "butter", "himalayan", "master", "pink", "sea"),
    )
    if term_reject:
        return term_reject
    return accept("669 reviewed garlic salt contract accepted")


def evaporated_milk_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "20952", ("milk", "dairy", "canned"))
    if category_reject:
        return category_reject
    if not product.has_all("evaporated", "milk"):
        return reject("20952 missing required term(s): evaporated|milk")
    term_reject = reject_terms(product, "20952", ("chocolate", "coconut", "condensed", "cream", "powder", "sweetened"))
    if term_reject:
        return term_reject
    return accept("20952 reviewed evaporated milk contract accepted")


def maple_syrup_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "25002", ("syrup", "molasses"))
    if category_reject:
        return category_reject
    if not product.has_all("maple", "syrup"):
        return reject("25002 missing required term(s): maple|syrup")
    term_reject = reject_terms(
        product,
        "25002",
        ("butter", "coffee", "flavor", "flavored", "pancake", "sugarfree", "zero"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("cellulose", "corn", "erythritol", "flavor", "flavors", "fructose", "glycerin", "monk", "water")
        if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)
    ]
    if ingredient_hits:
        return reject("25002 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("25002 reviewed maple syrup contract accepted")


def molasses_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "25003", ("syrup", "molasses"))
    if category_reject:
        return category_reject
    if not product.has_any("molasses"):
        return reject("25003 missing required term(s): molasses")
    term_reject = reject_terms(
        product,
        "25003",
        ("candy", "chocolate", "date", "peanut", "pomegranate", "pomegrenate", "sorghum"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("chocolate", "date", "peanut", "pomegranate", "sorghum")
        if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)
    ]
    if ingredient_hits:
        return reject("25003 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("25003 reviewed molasses contract accepted")


def dark_brown_sugar_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "45896", BAKING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("dark", "brown", "sugar"):
        return reject("45896 missing required term(s): dark|brown|sugar")
    term_reject = reject_terms(
        product,
        "45896",
        ("chocolate", "cocoa", "coffee", "liquid", "sweetener", "zero"),
    )
    if term_reject:
        return term_reject
    return accept("45896 reviewed dark brown sugar contract accepted")


def monterey_jack_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "1324", ("cheese",))
    if category_reject:
        return category_reject
    if not product.has_phrase("monterey jack"):
        return reject("1324 missing required phrase(s): monterey jack")
    term_reject = reject_terms(
        product,
        "1324",
        ("blend", "cheddar", "colby", "cracker", "jalapeno", "mexican", "pepper", "snack", "stick", "sticks", "taco"),
    )
    if term_reject:
        return term_reject
    return accept("1324 reviewed monterey jack cheese contract accepted")


def swiss_cheese_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "33366", ("cheese",))
    if category_reject:
        return category_reject
    if not product.has_any("swiss"):
        return reject("33366 missing required term(s): swiss")
    term_reject = reject_terms(
        product,
        "33366",
        (
            "american",
            "assorted",
            "blend",
            "breakfast",
            "cheddar",
            "colby",
            "cracker",
            "dip",
            "gruyere",
            "imitation",
            "jack",
            "mac",
            "medley",
            "mozzarella",
            "parmesan",
            "pasta",
            "pepper",
            "pizza",
            "provolone",
            "romano",
            "sauce",
            "snack",
            "spread",
            "style",
            "tray",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("american", "cheddar", "colby", "gruyere", "jack", "mozzarella", "parmesan", "provolone", "romano")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("33366 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("33366 reviewed swiss cheese contract accepted")


def curry_powder_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26004", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("curry"):
        return reject("26004 missing required term(s): curry")
    if not product.has_any("powder", "seasoning", "spice", "blend"):
        return reject("26004 missing required form term(s): powder|seasoning|spice|blend")
    term_reject = reject_terms(product, "26004", ("chicken", "noodle", "olive", "paste", "relish", "sauce", "simmer"))
    if term_reject:
        return term_reject
    return accept("26004 reviewed curry powder contract accepted")


def italian_seasoning_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "93282", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("italian"):
        return reject("93282 missing required term(s): italian")
    if not product.has_any("seasoning", "herb", "herbs", "blend"):
        return reject("93282 missing required form term(s): seasoning|herb|blend")
    term_reject = reject_terms(product, "93282", ("breadcrumb", "dressing", "marinade", "pasta", "pizza", "sauce"))
    if term_reject:
        return term_reject
    return accept("93282 reviewed italian seasoning contract accepted")


def shallot_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6449", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("shallot", "shallots"):
        return reject("6449 missing required term(s): shallot")
    if product.category_has_any("canned", "frozen", "oil", "prepared", "processed", "sauce"):
        return reject("6449 category state mismatch")
    term_reject = reject_terms(
        product,
        "6449",
        ("bean", "butter", "cube", "cubes", "dip", "dressing", "green", "oil", "paste", "potato", "preserved", "sauce", "sausage", "soup", "vinaigrette"),
    )
    if term_reject:
        return term_reject
    return accept("6449 reviewed fresh shallot contract accepted")


def fresh_broccoli_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6757", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("broccoli"):
        return reject("6757 missing required term(s): broccoli")
    if product.category_has_any("canned", "frozen", "prepared", "processed", "sauce"):
        return reject("6757 category state mismatch")
    term_reject = reject_terms(
        product,
        "6757",
        ("carrot", "cauliflower", "cheese", "coleslaw", "frozen", "kit", "medley", "pasta", "quiche", "rice", "sauce", "slaw", "soup", "stir", "tot", "tots"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("carrot", "cauliflower", "cheese", "sauce") if product.ingredients_have_any(term)]
    if ingredient_hits:
        return reject("6757 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("6757 reviewed fresh broccoli contract accepted")


def fresh_cabbage_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6765", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("cabbage"):
        return reject("6765 missing required term(s): cabbage")
    if product.category_has_any("canned", "frozen", "prepared", "processed"):
        return reject("6765 category state mismatch")
    term_reject = reject_terms(
        product,
        "6765",
        ("carrot", "coleslaw", "dressing", "kit", "pickled", "red", "sauerkraut", "seasoned", "slaw"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("carrot", "dressing", "red") if product.ingredients_have_any(term)]
    if ingredient_hits:
        return reject("6765 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("6765 reviewed fresh cabbage contract accepted")


def lowfat_buttermilk_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "7", ("milk", "dairy"))
    if category_reject:
        return category_reject
    if not product.has_any("buttermilk"):
        return reject("7 missing required term(s): buttermilk")
    if not product.has_any("cultured"):
        return reject("7 missing required term(s): cultured")
    if not (product.has_any("lowfat", "reduced") or product.has_phrase("low fat") or product.has_phrase("1 percent")):
        return reject("7 missing required lowfat cue")
    term_reject = reject_terms(product, "7", ("chocolate", "flavor", "flavored", "whole"))
    if term_reject:
        return term_reject
    return accept("7 reviewed lowfat cultured buttermilk contract accepted")


def whole_buttermilk_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "37935", ("milk", "dairy"))
    if category_reject:
        return category_reject
    if not product.has_any("buttermilk"):
        return reject("37935 missing required term(s): buttermilk")
    if not (product.has_any("whole") or product.has_phrase("whole milk")):
        return reject("37935 missing required term(s): whole")
    term_reject = reject_terms(
        product,
        "37935",
        ("chocolate", "fatfree", "flavor", "flavored", "goat", "lowfat", "nonfat", "powder", "reduced", "skim"),
    )
    if term_reject:
        return term_reject
    if product.has_phrase("fat free") or product.has_phrase("low fat") or product.has_phrase("1 percent"):
        return reject("37935 excluded reduced-fat cue")
    return accept("37935 reviewed whole buttermilk contract accepted")


def sweetened_condensed_milk_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "20950", ("milk", "dairy", "canned"))
    if category_reject:
        return category_reject
    if not product.has_all("condensed", "milk"):
        return reject("20950 missing required term(s): condensed|milk")
    if not (product.has_any("sweetened") or product.ingredients_have_any("sugar") or product.ingredients_have_phrase("sugar")):
        return reject("20950 missing sweetened cue")
    term_reject = reject_terms(product, "20950", ("caramel", "chocolate", "coconut", "creamer", "evaporated", "filled", "spread"))
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("cacao", "caramel", "chocolate", "cocoa", "coconut", "hydrogenated", "oil", "soybean", "vegetable")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("20950 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("20950 reviewed sweetened condensed milk contract accepted")


def vegetable_shortening_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "90963", ("oil", "butter", "spread", "shortening"))
    if category_reject:
        return category_reject
    if not product.has_any("shortening"):
        return reject("90963 missing required term(s): shortening")
    if not product.has_any("vegetable"):
        return reject("90963 missing required term(s): vegetable")
    term_reject = reject_terms(product, "90963", ("animal", "butter", "flavor", "flavored"))
    if term_reject:
        return term_reject
    return accept("90963 reviewed vegetable shortening contract accepted")


def fresh_mushroom_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "41502", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("mushroom", "mushrooms"):
        return reject("41502 missing required term(s): mushroom")
    if product.category_has_any("canned", "frozen", "prepared", "processed", "sauce"):
        return reject("41502 category state mismatch")
    term_reject = reject_terms(
        product,
        "41502",
        ("alfredo", "dried", "extract", "kit", "oil", "pasta", "pizza", "powder", "rice", "risotto", "sauce", "seasoned", "soup"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("garlic", "oil", "onion", "rice", "sauce")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("41502 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("41502 reviewed fresh mushroom contract accepted")


def frozen_peas_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "1817", ("frozen", "vegetable", "vegetables"))
    if category_reject:
        return category_reject
    if not product.has_any("pea", "peas"):
        return reject("1817 missing required term(s): pea")
    if not product.category_has_any("frozen"):
        return reject("1817 category state mismatch")
    if product.category_has_any("appetizer", "appetizers", "dinner", "dinners", "entree", "entrees", "prepared", "side", "sides"):
        return reject("1817 category prepared-food mismatch")
    term_reject = reject_terms(
        product,
        "1817",
        (
            "bean",
            "blackeye",
            "blackeyed",
            "broccoli",
            "carrot",
            "cauliflower",
            "chickpea",
            "curry",
            "dinner",
            "medley",
            "pigeon",
            "pepper",
            "rice",
            "riced",
            "samosa",
            "samosas",
            "sauce",
            "snap",
            "soup",
            "squash",
            "stir",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("bean", "broccoli", "carrot", "cauliflower", "chickpea", "mushroom", "onion", "pepper", "squash")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("1817 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("1817 reviewed frozen peas contract accepted")


def green_beans_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "27329", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("green", "bean"):
        return reject("27329 missing required term(s): green|bean")
    term_reject = reject_terms(
        product,
        "27329",
        (
            "almondine",
            "casserole",
            "carrot",
            "chip",
            "chili",
            "corn",
            "dinner",
            "fried",
            "jelly",
            "kidney",
            "lima",
            "mushroom",
            "pea",
            "pickled",
            "rice",
            "salad",
            "sauce",
            "snack",
            "soup",
            "spicy",
            "stew",
            "wax",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("carrot", "corn", "cream", "fried", "milk", "mushroom", "onion", "pea")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("27329 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("27329 reviewed plain green beans contract accepted")


def superfine_sugar_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "45897", BAKING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("sugar"):
        return reject("45897 missing required term(s): sugar")
    if not product.has_any("superfine", "caster"):
        return reject("45897 missing required term(s): superfine")
    term_reject = reject_terms(product, "45897", ("brown", "confectioner", "confectioners", "powdered"))
    if term_reject:
        return term_reject
    return accept("45897 reviewed superfine sugar contract accepted")


def fresh_sweet_potato_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "48595", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("sweet", "potato"):
        return reject("48595 missing required term(s): sweet|potato")
    if product.category_has_any("canned", "frozen", "juice", "prepared", "processed", "snack"):
        return reject("48595 category state mismatch")
    term_reject = reject_terms(
        product,
        "48595",
        ("bourbon", "candied", "chip", "chipotle", "fries", "fry", "honey", "maple", "pie", "puff", "season", "seasoned", "syrup", "vanilla", "yam"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("seasoning", "sugar", "syrup") if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("48595 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("48595 reviewed fresh sweet potato contract accepted")


def rolled_oats_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "93116", ("cereal", "grain", "oat"))
    if category_reject:
        return category_reject
    if not product.has_any("oat", "oats"):
        return reject("93116 missing required term(s): oat")
    if not product.has_any("rolled"):
        return reject("93116 missing required term(s): rolled")
    if not (product.has_any("old", "oldfashioned") or product.has_phrase("old fashioned")):
        return reject("93116 missing required term(s): old fashioned")
    term_reject = reject_terms(
        product,
        "93116",
        ("almond", "bar", "cranberry", "granola", "instant", "lowfat", "quick", "vanilla"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("almond", "cranberry", "honey", "rice", "sugar", "syrup", "wheat")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("93116 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("93116 reviewed old fashioned rolled oats contract accepted")


def light_corn_syrup_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "25000", ("syrup", "sugar"))
    if category_reject:
        return category_reject
    if not product.has_all("corn", "syrup", "light"):
        return reject("25000 missing required term(s): light|corn|syrup")
    term_reject = reject_terms(product, "25000", ("chocolate", "dark", "maple", "pancake"))
    if term_reject:
        return term_reject
    return accept("25000 reviewed light corn syrup contract accepted")


def ground_turkey_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "16157", ("poultry", "turkey", "chicken"))
    if category_reject:
        return category_reject
    if product.category_has_any("cold", "cut", "cuts", "pepperoni", "salami", "sandwich", "sausage", "snack"):
        return reject("16157 category prepared-meat mismatch")
    if not product.has_all("ground", "turkey"):
        return reject("16157 missing required term(s): ground|turkey")
    term_reject = reject_terms(
        product,
        "16157",
        ("breast", "deli", "meatball", "meatballs", "patty", "patties", "sausage", "tenderloin"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("bread", "cheese", "crumbs", "egg", "pork", "sauce", "spice") if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("16157 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("16157 reviewed raw ground turkey contract accepted")


def chickpea_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4441", BEAN_CATEGORIES)
    if category_reject:
        return category_reject
    if product.category_has_any("frozen", "snack", "snacks"):
        return reject("4441 category state mismatch")
    has_chickpea = product.has_any("chickpea", "chickpeas", "garbanzo", "garbanzos") or product.has_all("chick", "peas")
    if not has_chickpea:
        return reject("4441 missing required term(s): chickpea")
    term_reject = reject_terms(
        product,
        "4441",
        ("blend", "chip", "chips", "chili", "dinner", "flour", "green", "hummus", "lentil", "pasta", "rice", "riced", "snack", "soup", "trio"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("flour", "lentil", "pea", "rice", "sunflower", "wheat") if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("4441 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("4441 reviewed cooked chickpea contract accepted")


def cottage_cheese_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "1508", ("cheese", "dairy"))
    if category_reject:
        return category_reject
    if not product.has_all("cottage", "cheese"):
        return reject("1508 missing required term(s): cottage|cheese")
    term_reject = reject_terms(
        product,
        "1508",
        ("breakfast", "dinner", "dip", "entree", "frozen", "lasagna", "meal", "pizza", "ravioli", "snack"),
    )
    if term_reject:
        return term_reject
    return accept("1508 reviewed cottage cheese contract accepted")


def frozen_sweet_corn_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "9633", ("frozen", "vegetable", "vegetables"))
    if category_reject:
        return category_reject
    if not product.category_has_any("frozen"):
        return reject("9633 category state mismatch")
    if product.category_has_any("appetizer", "appetizers", "breakfast", "dinner", "dinners", "entree", "entrees", "prepared", "side", "sides"):
        return reject("9633 category prepared-food mismatch")
    if not product.has_any("corn"):
        return reject("9633 missing required term(s): corn")
    term_reject = reject_terms(
        product,
        "9633",
        ("bread", "chili", "dinner", "meal", "rice", "sauce", "seasoned", "soup"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("butter", "cream", "pepper", "rice", "sauce", "seasoning") if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("9633 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("9633 reviewed frozen sweet corn contract accepted")


def apple_juice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "793", ("beverage", "drink", "drinks", "juice", "juices"))
    if category_reject:
        return category_reject
    if not product.has_all("apple", "juice"):
        return reject("793 missing required term(s): apple|juice")
    term_reject = reject_terms(
        product,
        "793",
        (
            "banana",
            "beverage",
            "carrot",
            "cherry",
            "cider",
            "cocktail",
            "cranberry",
            "cucumber",
            "drink",
            "grape",
            "ginger",
            "kale",
            "lemon",
            "mango",
            "mixed",
            "orange",
            "peach",
            "pear",
            "pineapple",
            "sparkling",
            "strawberry",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in (
            "banana",
            "carrot",
            "celery",
            "cherry",
            "cranberry",
            "cucumber",
            "ginger",
            "grape",
            "kale",
            "lemon",
            "mango",
            "orange",
            "pear",
            "pineapple",
            "strawberry",
            "vegetable",
        )
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("793 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("793 reviewed apple juice contract accepted")


def fresh_russet_potato_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "48587", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("russet", "potato"):
        return reject("48587 missing required term(s): russet|potato")
    if product.category_has_any("canned", "chip", "chips", "entree", "frozen", "prepared", "processed", "side", "sides"):
        return reject("48587 category state mismatch")
    term_reject = reject_terms(
        product,
        "48587",
        ("chip", "chips", "frozen", "fries", "mashed", "meal", "mix", "seasoned", "soup"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("cream", "milk", "oil", "salt", "sugar") if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("48587 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("48587 reviewed fresh russet potato contract accepted")


def ground_pork_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "12281", ("meat", "pork"))
    if category_reject:
        return category_reject
    if product.category_has_any("canned", "cooked", "prepared", "processed", "sausage", "snack"):
        return reject("12281 category prepared-meat mismatch")
    if not product.has_all("ground", "pork"):
        return reject("12281 missing required term(s): ground|pork")
    term_reject = reject_terms(
        product,
        "12281",
        ("carnitas", "luncheon", "meatball", "meatballs", "patty", "sausage", "seasoned", "vegetables"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("bread", "carrot", "cheese", "crumbs", "mushroom", "sauce", "spice") if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("12281 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("12281 reviewed raw ground pork contract accepted")


def celery_seed_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26040", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("celery", "seed"):
        return reject("26040 missing required term(s): celery|seed")
    term_reject = reject_terms(product, "26040", ("salt", "soup"))
    if term_reject:
        return term_reject
    return accept("26040 reviewed celery seed contract accepted")


def ground_cardamom_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26039", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("ground", "cardamom"):
        return reject("26039 missing required term(s): ground|cardamom")
    return accept("26039 reviewed ground cardamom contract accepted")


def pumpkin_pie_spice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26029", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("pumpkin", "pie"):
        return reject("26029 missing required term(s): pumpkin|pie")
    if not product.has_any("spice"):
        return reject("26029 missing required term(s): spice")
    term_reject = reject_terms(product, "26029", ("bar", "butter", "cake", "cashew", "cream", "latte", "milk", "pudding", "sunflower"))
    if term_reject:
        return term_reject
    return accept("26029 reviewed pumpkin pie spice contract accepted")


def garam_masala_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "36425", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("garam", "masala"):
        return reject("36425 missing required term(s): garam|masala")
    return accept("36425 reviewed garam masala contract accepted")


def dill_weed_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26021", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("dill", "weed"):
        return reject("26021 missing required term(s): dill|weed")
    term_reject = reject_terms(product, "26021", ("dip", "dressing", "pickle", "sauce"))
    if term_reject:
        return term_reject
    return accept("26021 reviewed dried dill weed contract accepted")


def yellow_mustard_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "18031", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("yellow", "mustard"):
        return reject("18031 missing required term(s): yellow|mustard")
    term_reject = reject_terms(
        product,
        "18031",
        ("chip", "cracker", "dressing", "honey", "pretzel", "snack", "sweet", "vinaigrette"),
    )
    if term_reject:
        return term_reject
    if product.ingredients_have_any("honey"):
        return reject("18031 excluded ingredient term(s): honey")
    return accept("18031 reviewed yellow mustard contract accepted")


def poultry_seasoning_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26028", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("poultry", "seasoning"):
        return reject("26028 missing required term(s): poultry|seasoning")
    if product.category_has_any("chicken", "frozen", "meat", "poultry", "turkey"):
        return reject("26028 category actual-poultry mismatch")
    term_reject = reject_terms(product, "26028", ("chicken", "turkey"))
    if term_reject:
        return term_reject
    if product.ingredients_have_any("chicken", "turkey"):
        return reject("26028 excluded ingredient term(s): chicken|turkey")
    return accept("26028 reviewed poultry seasoning contract accepted")


def canned_named_bean_contract(esha_code: str, required_terms: tuple[str, ...]) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, BEAN_CATEGORIES)
        if category_reject:
            return category_reject
        missing = [term for term in required_terms if not product.has_any(term)]
        if missing:
            return reject(f"{esha_code} missing required term(s): " + "|".join(missing))
        if product.category_has_any("frozen", "snack", "snacks"):
            return reject(f"{esha_code} category state mismatch")
        term_reject = reject_terms(
            product,
            esha_code,
            ("chip", "chips", "chili", "dinner", "flour", "hummus", "pasta", "rice", "sauced", "savory", "snack", "soup", "style"),
        )
        if term_reject:
            return term_reject
        ingredient_hits = [
            term for term in ("flour", "garlic", "oil", "onion", "tomato") if product.ingredients_have_any(term)
        ]
        if ingredient_hits:
            return reject(f"{esha_code} excluded ingredient term(s): " + "|".join(ingredient_hits))
        return accept(f"{esha_code} reviewed canned named bean contract accepted")

    return contract


def apple_cider_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4085", ("beverage", "cider", "drink", "juice"))
    if category_reject:
        return category_reject
    if not product.has_all("apple", "cider"):
        return reject("4085 missing required term(s): apple|cider")
    term_reject = reject_terms(
        product,
        "4085",
        ("alcohol", "beer", "blueberry", "carbonated", "cocktail", "donut", "hard", "lemon", "mix", "sparkling", "spice", "spiced", "vinegar"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("allspice", "cinnamon", "clove", "lemon", "orange", "spice", "spices") if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("4085 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("4085 reviewed apple cider contract accepted")


def maraschino_cherry_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "31332", ("fruit", "cherry", "cherries", "prepared", "processed"))
    if category_reject:
        return category_reject
    if not product.has_any("maraschino"):
        return reject("31332 missing required term(s): maraschino")
    if not product.has_any("cherry", "cherries"):
        return reject("31332 missing required term(s): cherry")
    term_reject = reject_terms(product, "31332", ("chocolate", "cookie", "pie", "soda"))
    if term_reject:
        return term_reject
    return accept("31332 reviewed maraschino cherry contract accepted")


def oyster_sauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "53473", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("oyster", "sauce"):
        return reject("53473 missing required term(s): oyster|sauce")
    term_reject = reject_terms(product, "53473", ("chicken", "dinner", "flavored", "lo", "meal", "mein", "noodle", "stir", "vegan", "vegetarian"))
    if term_reject:
        return term_reject
    if product.ingredients and not product.ingredients_have_phrase("oyster"):
        return reject("53473 missing ingredient term(s): oyster")
    if product.ingredients_have_any("chicken"):
        return reject("53473 excluded ingredient term(s): chicken")
    return accept("53473 reviewed oyster sauce contract accepted")


def cocoa_powder_contract_v2(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "41522", ("baking", "cocoa", "drink", "drinks", "powder", "powdered"))
    if category_reject:
        return category_reject
    if not product.has_all("cocoa", "powder"):
        return reject("41522 missing required term(s): cocoa|powder")
    term_reject = reject_terms(
        product,
        "41522",
        ("drink", "flavor", "flavored", "hot", "milk", "mix", "muscle", "prebiotic", "protein", "recovery", "sweetened", "vanilla"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("artificial", "flavor", "flavors", "milk", "protein", "sugar", "vanilla")
        if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)
    ]
    if ingredient_hits:
        return reject("41522 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("41522 reviewed cocoa powder contract accepted")


def chocolate_syrup_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "23437", ("syrup", "molasses", "topping"))
    if category_reject:
        return category_reject
    if not product.has_all("chocolate", "syrup"):
        return reject("23437 missing required term(s): chocolate|syrup")
    term_reject = reject_terms(product, "23437", ("caramel", "coconut", "coffee", "hazelnut", "strawberry"))
    if term_reject:
        return term_reject
    return accept("23437 reviewed chocolate syrup contract accepted")


def snow_pea_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "48582", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("snow", "peas"):
        return reject("48582 missing required term(s): snow|peas")
    if product.category_has_any("canned", "frozen", "prepared", "processed", "snack"):
        return reject("48582 category state mismatch")
    term_reject = reject_terms(
        product,
        "48582",
        ("chip", "chili", "dinner", "meal", "pasta", "rice", "sauce", "sesame", "snack", "soup", "stir", "sunflower"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("carrot", "pepper", "rice", "sauce", "sesame") if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("48582 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("48582 reviewed fresh snow pea contract accepted")


def light_sour_cream_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "553", ("cream", "dairy"))
    if category_reject:
        return category_reject
    if not product.has_all("sour", "cream"):
        return reject("553 missing required term(s): sour|cream")
    if not product.has_any("light"):
        return reject("553 missing required term(s): light")
    term_reject = reject_terms(product, "553", ("dip", "flavor", "flavored", "onion"))
    if term_reject:
        return term_reject
    return accept("553 reviewed light sour cream contract accepted")


def frozen_mixed_vegetable_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "9669", ("frozen", "vegetable", "vegetables"))
    if category_reject:
        return category_reject
    if not product.category_has_any("frozen"):
        return reject("9669 category state mismatch")
    if not product.has_all("mixed", "vegetable"):
        return reject("9669 missing required term(s): mixed|vegetable")
    if product.category_has_any("appetizer", "breakfast", "dinner", "entree", "prepared", "side", "sides"):
        return reject("9669 category prepared-food mismatch")
    term_reject = reject_terms(product, "9669", ("butter", "dinner", "meal", "rice", "sauce", "seasoned", "soup"))
    if term_reject:
        return term_reject
    return accept("9669 reviewed frozen mixed vegetable contract accepted")


def orange_marmalade_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "23005", ("jam", "jelly", "marmalade", "spread"))
    if category_reject:
        return category_reject
    if not product.has_all("orange", "marmalade"):
        return reject("23005 missing required term(s): orange|marmalade")
    term_reject = reject_terms(product, "23005", ("cookie", "sauce", "tea"))
    if term_reject:
        return term_reject
    return accept("23005 reviewed orange marmalade contract accepted")


def pizza_sauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "45487", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("pizza", "sauce"):
        return reject("45487 missing required term(s): pizza|sauce")
    term_reject = reject_terms(product, "45487", ("alfredo", "chicken", "dinner", "meal", "pasta", "snack"))
    if term_reject:
        return term_reject
    if product.ingredients_have_any("chicken"):
        return reject("45487 excluded ingredient term(s): chicken")
    return accept("45487 reviewed pizza sauce contract accepted")


def long_grain_white_rice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38528", ("rice",))
    if category_reject:
        return category_reject
    if not product.has_all("long", "grain", "white", "rice"):
        return reject("38528 missing required term(s): long|grain|white|rice")
    term_reject = reject_terms(product, "38528", ("cooked", "dinner", "flavored", "instant", "meal", "microwave", "mix", "pilaf", "ready", "seasoned"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("cooked", "oil") if product.ingredients_have_any(term)]
    if ingredient_hits:
        return reject("38528 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("38528 reviewed dry long grain white rice contract accepted")


def onion_flake_contract(product: ProductFacts) -> MatchDecision:
    if not product.category_has_any("herb", "spice"):
        return reject("5113 category mismatch")
    if not product.has_any("onion") or not product.has_any("flake", "flakes"):
        return reject("5113 missing required term(s): onion|flakes")
    term_reject = reject_terms(product, "5113", ("chili", "dip", "garlic", "guacamole", "lime", "seasoning", "soup"))
    if term_reject:
        return term_reject
    return accept("5113 reviewed dehydrated onion flakes contract accepted")


def couscous_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38281", ("grain", "pasta", "rice", "seed"))
    if category_reject:
        return category_reject
    if not product.has_any("couscous"):
        return reject("38281 missing required term(s): couscous")
    term_reject = reject_terms(product, "38281", ("dinner", "entree", "garlic", "kit", "meal", "pizza", "salad", "sauce", "seasoned", "soup"))
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("chicken", "garlic", "meal", "sauce", "seasoning", "vegetable") if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("38281 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("38281 reviewed dry couscous contract accepted")


def iceberg_lettuce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "27413", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("iceberg", "lettuce"):
        return reject("27413 missing required term(s): iceberg|lettuce")
    if product.category_has_any("canned", "frozen", "prepared", "processed"):
        return reject("27413 category state mismatch")
    term_reject = reject_terms(product, "27413", ("blend", "chip", "chili", "chopped", "cobb", "kit", "meal", "mix", "rice", "romaine", "salad", "sauce", "shreds", "shredded", "slaw", "soup"))
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("bacon", "cabbage", "carrot", "cheese", "chicken", "dressing", "egg", "spinach") if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("27413 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("27413 reviewed iceberg lettuce contract accepted")


def pesto_sauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "33320", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("pesto"):
        return reject("33320 missing required term(s): pesto")
    term_reject = reject_terms(product, "33320", ("chicken", "dinner", "meal", "pizza", "ravioli", "snack"))
    if term_reject:
        return term_reject
    return accept("33320 reviewed pesto sauce contract accepted")


def corn_oil_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "8009", OIL_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("corn", "oil"):
        return reject("8009 missing required term(s): corn|oil")
    term_reject = reject_terms(product, "8009", ("blend", "butter", "dressing", "popcorn", "spray"))
    if term_reject:
        return term_reject
    return accept("8009 reviewed corn oil contract accepted")


def red_cabbage_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6768", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("red", "cabbage"):
        return reject("6768 missing required term(s): red|cabbage")
    if product.category_has_any("canned", "frozen", "prepared", "processed"):
        return reject("6768 category state mismatch")
    term_reject = reject_terms(
        product,
        "6768",
        ("carrot", "coleslaw", "dressing", "green", "kit", "pickled", "sauerkraut", "seasoned", "slaw"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("carrot", "dressing", "green") if product.ingredients_have_any(term)]
    if ingredient_hits:
        return reject("6768 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("6768 reviewed fresh red cabbage contract accepted")


def saltine_cracker_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "31262", ("cracker", "crackers", "biscotti"))
    if category_reject:
        return category_reject
    if not product.has_any("saltine", "saltines"):
        return reject("31262 missing required term(s): saltine")
    term_reject = reject_terms(product, "31262", ("chocolate", "cream", "flavored", "sandwich"))
    if term_reject:
        return term_reject
    return accept("31262 reviewed saltine cracker contract accepted")


def pearl_barley_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "93100", ("barley", "grain", "grains", "seed"))
    if category_reject:
        return category_reject
    if not product.has_all("barley", "pearl"):
        return reject("93100 missing required term(s): barley|pearl")
    term_reject = reject_terms(product, "93100", ("soup", "mix", "meal"))
    if term_reject:
        return term_reject
    return accept("93100 reviewed pearl barley contract accepted")


def crystallized_ginger_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26646", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("crystallized", "ginger"):
        return reject("26646 missing required term(s): crystallized|ginger")
    term_reject = reject_terms(product, "26646", ("cookie", "tea"))
    if term_reject:
        return term_reject
    return accept("26646 reviewed crystallized ginger contract accepted")


def grenadine_syrup_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "25066", ("adult", "beverage", "cocktail", "drink", "grenadine", "mix", "mixer", "molasses", "syrup"))
    if category_reject:
        return category_reject
    if not product.has_any("grenadine"):
        return reject("25066 missing required term(s): grenadine")
    if not product.has_any("syrup", "mixer"):
        return reject("25066 missing required term(s): syrup|mixer")
    term_reject = reject_terms(product, "25066", ("alcohol", "jelly", "seltzer", "sparkling"))
    if term_reject:
        return term_reject
    return accept("25066 reviewed grenadine syrup contract accepted")


def club_soda_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4787", ("soda", "water"))
    if category_reject:
        return category_reject
    if not product.has_all("club", "soda"):
        return reject("4787 missing required term(s): club|soda")
    term_reject = reject_terms(product, "4787", ("enhancer", "flavored", "fruit", "mix", "raspberry", "syrup"))
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("flavor", "flavors", "starch", "sucralose", "sugar", "syrup") if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("4787 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("4787 reviewed club soda contract accepted")


def ground_chicken_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "14790", ("chicken", "poultry"))
    if category_reject:
        return category_reject
    if product.category_has_any("cold", "cut", "cuts", "sausage", "snack"):
        return reject("14790 category prepared-meat mismatch")
    if not product.has_all("ground", "chicken"):
        return reject("14790 missing required term(s): ground|chicken")
    term_reject = reject_terms(product, "14790", ("meatball", "meatballs", "nugget", "nuggets", "patty", "sausage", "strip", "tender"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("bread", "cheese", "crumb", "pork", "sauce") if product.ingredients_have_any(term)]
    if ingredient_hits:
        return reject("14790 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("14790 reviewed raw ground chicken contract accepted")


def frozen_plain_berry_contract(esha_code: str, berry: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, ("frozen", "fruit"))
        if category_reject:
            return category_reject
        if not product.category_has_any("frozen"):
            return reject(f"{esha_code} category frozen mismatch")
        if product.category_has_any("candy", "dessert", "desserts", "ice", "yogurt"):
            return reject(f"{esha_code} category dessert mismatch")
        if not product.has_any(berry):
            return reject(f"{esha_code} missing required term(s): {berry}")
        term_reject = reject_terms(
        product,
        esha_code,
        (
            "apple",
            "bar",
            "blend",
            "cake",
            "concentrate",
            "cranberry",
            "cream",
            "grape",
            "ice",
            "juice",
            "lemonade",
            "mousse",
            "pear",
            "sherbet",
            "sorbet",
            "smoothie",
            "yogurt",
        ),
        )
        if term_reject:
            return term_reject
        ingredient_hits = [
            term for term in ("cream", "erythritol", "flavor", "milk", "sugar", "water") if product.ingredients_have_any(term)
        ]
        if ingredient_hits and not product.category_has_any("fruit"):
            return reject(f"{esha_code} excluded ingredient term(s): " + "|".join(ingredient_hits))
        return accept(f"{esha_code} reviewed frozen plain {berry} contract accepted")

    return contract


def wild_rice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38289", ("rice",))
    if category_reject:
        return category_reject
    if not product.has_all("wild", "rice"):
        return reject("38289 missing required term(s): wild|rice")
    term_reject = reject_terms(
        product,
        "38289",
        ("arborio", "blend", "brown", "dinner", "entree", "flavored", "kit", "meal", "mix", "mushroom", "pilaf", "risotto", "seasoning", "seasonings", "soup", "white"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("arborio", "basmati", "brown", "long grain rice", "mushroom", "red", "risotto", "seasoning", "white")
        if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)
    ]
    if ingredient_hits:
        return reject("38289 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("38289 reviewed dry wild rice contract accepted")


def enchilada_sauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "13488", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("enchilada", "sauce"):
        return reject("13488 missing required term(s): enchilada|sauce")
    term_reject = reject_terms(product, "13488", ("chicken", "dinner", "meal", "mix", "seasoning"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("cheddar", "cheese", "chicken") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)]
    if ingredient_hits:
        return reject("13488 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("13488 reviewed enchilada sauce contract accepted")


def lentil_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "7005", BEAN_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("lentil", "lentils"):
        return reject("7005 missing required term(s): lentil")
    term_reject = reject_terms(product, "7005", ("bean", "blend", "chip", "chili", "dinner", "dip", "meal", "pea", "rice", "snack", "soup", "stew"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("bean", "pea", "rice") if product.ingredients_have_any(term)]
    if ingredient_hits:
        return reject("7005 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("7005 reviewed plain lentil contract accepted")


def seasoned_breadcrumb_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "42144", ("bread", "breading", "crumb", "crumbs", "mix"))
    if category_reject:
        return category_reject
    if not product.has_all("bread", "crumb"):
        return reject("42144 missing required term(s): bread|crumb")
    if not product.has_any("seasoned", "italian"):
        return reject("42144 missing required term(s): seasoned")
    term_reject = reject_terms(
        product,
        "42144",
        ("bean", "chipotle", "cilantro", "coconut", "dinner", "empanizador", "entree", "fish", "hot", "lime", "meal", "mexican", "spicy"),
    )
    if term_reject:
        return term_reject
    return accept("42144 reviewed seasoned bread crumb contract accepted")


def agave_nectar_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "63655", ("honey", "sugar", "syrup", "sweetener"))
    if category_reject:
        return category_reject
    if not product.has_any("agave"):
        return reject("63655 missing required term(s): agave")
    if not (product.has_any("nectar", "syrup", "sweetener") or product.ingredients_have_any("agave")):
        return reject("63655 missing required nectar cue")
    term_reject = reject_terms(product, "63655", ("chip", "chips", "cocktail", "pickle", "salsa", "wine"))
    if term_reject:
        return term_reject
    return accept("63655 reviewed agave nectar contract accepted")


def italian_bread_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "71219", ("bread", "bun", "buns"))
    if category_reject:
        return category_reject
    if not product.has_all("italian", "bread"):
        return reject("71219 missing required term(s): italian|bread")
    term_reject = reject_terms(product, "71219", ("crumb", "crumbs", "dinner", "meal", "sandwich", "seasoned"))
    if term_reject:
        return term_reject
    return accept("71219 reviewed Italian bread contract accepted")


def cantaloupe_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "25757", ("fruit", "produce"))
    if category_reject:
        return category_reject
    if not product.has_any("cantaloupe"):
        return reject("25757 missing required term(s): cantaloupe")
    term_reject = reject_terms(product, "25757", ("candy", "cup", "grape", "honeydew", "trio", "watermelon"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("grape", "honeydew", "watermelon") if product.ingredients_have_any(term)]
    if ingredient_hits:
        return reject("25757 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("25757 reviewed fresh cantaloupe contract accepted")


def baking_cocoa_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "28211", ("baking", "cocoa", "powder"))
    if category_reject:
        return category_reject
    if not product.has_any("cocoa"):
        return reject("28211 missing required term(s): cocoa")
    if not (product.has_any("powder", "baking", "unsweetened") or product.ingredients_have_phrase("cocoa powder")):
        return reject("28211 missing required cocoa powder cue")
    term_reject = reject_terms(product, "28211", ("drink", "mocha", "protein", "sweetened"))
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("coffee", "flavor", "milk", "protein", "sugar") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)
    ]
    if ingredient_hits:
        return reject("28211 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("28211 reviewed baking cocoa contract accepted")


def tilapia_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "72906", SEAFOOD_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("tilapia"):
        return reject("72906 missing required term(s): tilapia")
    term_reject = reject_terms(product, "72906", ("basil", "breaded", "florentine", "lemon", "meal", "pepper", "seasoned", "seasoning", "sauce"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("garlic", "oil", "sauce", "seasoning", "spinach") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)]
    if ingredient_hits:
        return reject("72906 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("72906 reviewed tilapia contract accepted")


def brussels_sprout_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5032", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not (product.has_any("brussel", "brussels") and product.has_any("sprout", "sprouts")):
        return reject("5032 missing required term(s): brussels|sprouts")
    term_reject = reject_terms(product, "5032", ("chip", "chili", "dinner", "garlic", "kit", "meal", "onion", "pepper", "rice", "roasting", "sauce", "seasoned", "snack"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("garlic", "oil", "onion", "pepper", "seasoning") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)]
    if ingredient_hits:
        return reject("5032 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("5032 reviewed plain brussels sprouts contract accepted")


def ground_lamb_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "13578", ("lamb", "meat"))
    if category_reject:
        return category_reject
    if not product.has_all("ground", "lamb"):
        return reject("13578 missing required term(s): ground|lamb")
    term_reject = reject_terms(product, "13578", ("burger", "meatball", "patty", "sausage"))
    if term_reject:
        return term_reject
    return accept("13578 reviewed raw ground lamb contract accepted")


def jam_contract(esha_code: str, fruit: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, ("fruit", "jam", "jelly", "spread"))
        if category_reject:
            return category_reject
        if not product.has_any(fruit):
            return reject(f"{esha_code} missing required term(s): {fruit}")
        if not product.has_any("jam", "preserves", "spread"):
            return reject(f"{esha_code} missing jam cue")
        other_fruits = ("blueberry", "cranberry", "mango", "orange", "peach", "strawberry")
        term_reject = reject_terms(product, esha_code, tuple(term for term in other_fruits if term != fruit) + ("cookie", "pastry", "sauce"))
        if term_reject:
            return term_reject
        ingredient_hits = [
            term for term in other_fruits if term != fruit and (product.ingredients_have_any(term) or product.ingredients_have_phrase(term))
        ]
        if ingredient_hits:
            return reject(f"{esha_code} excluded ingredient term(s): " + "|".join(ingredient_hits))
        return accept(f"{esha_code} reviewed {fruit} jam contract accepted")

    return contract


def plain_jam_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "23054", ("fruit", "jam", "jelly", "preserve", "spread"))
    if category_reject:
        return category_reject
    if not product.has_any("jam", "jelly", "preserve", "preserves", "spread"):
        return reject("23054 missing jam cue")
    term_reject = reject_terms(product, "23054", ("cookie", "pastry", "sauce", "syrup"))
    if term_reject:
        return term_reject
    return accept("23054 reviewed plain jam contract accepted")


def sourdough_bread_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "19179", ("bread", "bun", "buns"))
    if category_reject:
        return category_reject
    if not product.has_all("sourdough", "bread"):
        return reject("19179 missing required term(s): sourdough|bread")
    term_reject = reject_terms(product, "19179", ("dinner", "garlic", "meal", "sandwich", "stuffing"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("garlic",) if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)]
    if ingredient_hits:
        return reject("19179 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("19179 reviewed sourdough bread contract accepted")


def cranberry_sauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "27383", ("canned", "fruit", "sauce"))
    if category_reject:
        return category_reject
    if not product.has_all("cranberry", "sauce"):
        return reject("27383 missing required term(s): cranberry|sauce")
    term_reject = reject_terms(
        product,
        "27383",
        ("bbq", "barbecue", "char", "chipotle", "citru", "citrus", "cooking", "dressing", "glaze", "maple", "marinade", "mustard", "orange", "pomegranate", "port"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("garlic", "jalapeno", "mustard", "pepper", "tomato", "vinegar") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)]
    if ingredient_hits:
        return reject("27383 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("27383 reviewed cranberry sauce contract accepted")


def extra_lean_ground_beef_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "47445", ("beef", "meat"))
    if category_reject:
        return category_reject
    if not product.has_all("ground", "beef"):
        return reject("47445 missing required term(s): ground|beef")
    if not (product.has_any("extra", "lean") or product.has_phrase("96% lean") or product.has_phrase("97% lean")):
        return reject("47445 missing extra lean cue")
    term_reject = reject_terms(product, "47445", ("frank", "hotdog", "meatball", "patty", "sausage", "stew"))
    if term_reject:
        return term_reject
    return accept("47445 reviewed extra lean ground beef contract accepted")


def fat_free_sour_cream_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "550", ("cream", "dairy"))
    if category_reject:
        return category_reject
    if not product.has_all("sour", "cream"):
        return reject("550 missing required term(s): sour|cream")
    if not (product.has_phrase("fat free") or product.has_any("fatfree", "nonfat")):
        return reject("550 missing fat-free cue")
    term_reject = reject_terms(product, "550", ("chip", "dip", "flavored", "onion", "snack"))
    if term_reject:
        return term_reject
    return accept("550 reviewed fat-free sour cream contract accepted")


def creme_fraiche_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "49654", ("cream", "dairy"))
    if category_reject:
        return category_reject
    if not (product.has_all("creme", "fraiche") or product.has_all("crème", "fraîche")):
        return reject("49654 missing required term(s): creme|fraiche")
    term_reject = reject_terms(product, "49654", ("dip", "flavored", "sauce"))
    if term_reject:
        return term_reject
    return accept("49654 reviewed creme fraiche contract accepted")


def fresh_mozzarella_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "1250", ("cheese",))
    if category_reject:
        return category_reject
    if not product.has_any("mozzarella"):
        return reject("1250 missing required term(s): mozzarella")
    if not (
        product.has_any("fresh", "fresca", "bocconcini", "ciliegine", "ovoline", "pearl", "pearls", "ball", "balls")
        or product.has_phrase("fresh mozzarella")
    ):
        return reject("1250 missing fresh mozzarella cue")
    term_reject = reject_terms(product, "1250", ("blend", "cheddar", "low", "moisture", "parmesan", "pizza", "shredded", "snack", "stick", "string"))
    if term_reject:
        return term_reject
    return accept("1250 reviewed fresh mozzarella contract accepted")


def nonfat_mozzarella_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "48321", ("cheese",))
    if category_reject:
        return category_reject
    if not product.has_any("mozzarella"):
        return reject("48321 missing required term(s): mozzarella")
    if not (product.has_phrase("fat free") or product.has_any("nonfat", "fat-free")):
        return reject("48321 missing nonfat cue")
    if not (
        product.has_any("shredded", "shred")
        or product.has_phrase("fine cut")
        or product.has_phrase("finely shredded")
    ):
        return reject("48321 missing shredded cue")
    term_reject = reject_terms(
        product,
        "48321",
        (
            "blend",
            "cheddar",
            "cube",
            "cubes",
            "cubed",
            "feta",
            "fresh",
            "parmesan",
            "part-skim",
            "pizza",
            "provolone",
            "reduced fat",
            "romano",
            "stick",
            "sticks",
            "string",
            "whole milk",
        ),
    )
    if term_reject:
        return term_reject
    return accept("48321 reviewed nonfat shredded mozzarella contract accepted")


def vanilla_wafer_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "52964", ("cookie", "cookies", "wafer", "wafers"))
    if category_reject:
        return category_reject
    if not product.has_all("vanilla", "wafer"):
        return reject("52964 missing required term(s): vanilla|wafer")
    term_reject = reject_terms(product, "52964", ("cream", "ice", "protein", "sandwich"))
    if term_reject:
        return term_reject
    return accept("52964 reviewed vanilla wafer contract accepted")


def fresh_radish_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5716", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("radish", "radishes"):
        return reject("5716 missing required term(s): radish")
    if product.category_has_any("canned", "frozen", "processed", "snack"):
        return reject("5716 category state mismatch")
    term_reject = reject_terms(product, "5716", ("chip", "pickled", "sauce", "snack"))
    if term_reject:
        return term_reject
    return accept("5716 reviewed fresh radish contract accepted")


def instant_rice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "8968", ("rice",))
    if category_reject:
        return category_reject
    if not product.has_all("instant", "rice"):
        return reject("8968 missing required term(s): instant|rice")
    term_reject = reject_terms(product, "8968", ("cooked", "dinner", "flavored", "meal", "microwave", "pilaf", "ready", "seasoned"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("cooked", "oil", "seasoning") if product.ingredients_have_any(term)]
    if ingredient_hits:
        return reject("8968 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("8968 reviewed dry instant rice contract accepted")


def pumpkin_seed_contract_v2(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "63537", NUT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("pumpkin", "seed"):
        return reject("63537 missing required term(s): pumpkin|seed")
    term_reject = reject_terms(
        product,
        "63537",
        (
            "almond",
            "banana",
            "bar",
            "bark",
            "blueberry",
            "butter",
            "cacao",
            "cashew",
            "cereal",
            "chocolate",
            "cluster",
            "clusters",
            "coffee",
            "energy",
            "flavored",
            "mix",
            "sunflower",
            "walnut",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("cashew", "date", "dates") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)]
    if ingredient_hits:
        return reject("63537 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("63537 reviewed pumpkin seed contract accepted")


def alfredo_sauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "9559", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("alfredo", "sauce"):
        return reject("9559 missing required term(s): alfredo|sauce")
    term_reject = reject_terms(product, "9559", ("chicken", "dinner", "meal", "pasta"))
    if term_reject:
        return term_reject
    return accept("9559 reviewed alfredo sauce contract accepted")


def beef_hot_dog_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "57968", ("brat", "brats", "hotdog", "hotdogs", "sausage"))
    if category_reject:
        return category_reject
    if not product.has_any("beef"):
        return reject("57968 missing required term(s): beef")
    if not (product.has_phrase("hot dog") or product.has_any("hotdog", "hotdogs", "frank", "franks")):
        return reject("57968 missing hot dog cue")
    term_reject = reject_terms(product, "57968", ("appetizer", "chili", "corn", "mini", "pork"))
    if term_reject:
        return term_reject
    return accept("57968 reviewed beef hot dog contract accepted")


def tamari_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26705", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("tamari", "soy"):
        return reject("26705 missing required term(s): tamari|soy")
    term_reject = reject_terms(product, "26705", ("cracker", "fish", "marinade", "snack"))
    if term_reject:
        return term_reject
    return accept("26705 reviewed tamari soy sauce contract accepted")


def dark_corn_syrup_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "25010", ("syrup", "sugar"))
    if category_reject:
        return category_reject
    if not product.has_all("dark", "corn", "syrup"):
        return reject("25010 missing required term(s): dark|corn|syrup")
    return accept("25010 reviewed dark corn syrup contract accepted")


def spicy_brown_mustard_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "33167", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("spicy", "brown", "mustard"):
        return reject("33167 missing required term(s): spicy|brown|mustard")
    term_reject = reject_terms(product, "33167", ("dressing", "firecracker", "honey", "pretzel", "snack"))
    if term_reject:
        return term_reject
    if product.ingredients_have_any("horseradish"):
        return reject("33167 excluded ingredient term(s): horseradish")
    return accept("33167 reviewed spicy brown mustard contract accepted")


def jasmine_rice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "46522", ("rice",))
    if category_reject:
        return category_reject
    if not product.has_all("jasmine", "rice"):
        return reject("46522 missing required term(s): jasmine|rice")
    term_reject = reject_terms(product, "46522", ("cooked", "dinner", "flavored", "instant", "meal", "microwave", "mix", "ready", "seasoned"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("cooked", "oil", "precooked", "seasoning") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)]
    if ingredient_hits:
        return reject("46522 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("46522 reviewed dry jasmine rice contract accepted")


def garlic_paste_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "34571", (*VEGETABLE_CATEGORIES, *CONDIMENT_CATEGORIES))
    if category_reject:
        return category_reject
    if not product.has_all("garlic", "paste"):
        return reject("34571 missing required term(s): garlic|paste")
    term_reject = reject_terms(product, "34571", ("chili", "rice", "sauce", "tomato"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("tomato",) if product.ingredients_have_any(term)]
    if ingredient_hits:
        return reject("34571 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("34571 reviewed garlic paste contract accepted")


def red_kidney_bean_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "7173", BEAN_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("red", "kidney"):
        return reject("7173 missing required term(s): red|kidney")
    term_reject = reject_terms(product, "7173", ("baked", "black", "blend", "chickpea", "chili", "pinto", "three", "tri"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("garlic", "ham", "onion", "pepper", "tomato") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)]
    if ingredient_hits:
        return reject("7173 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("7173 reviewed red kidney bean contract accepted")


def bamboo_shoot_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6463", ("canned", "vegetable", "vegetables"))
    if category_reject:
        return category_reject
    if not product.has_all("bamboo", "shoot"):
        return reject("6463 missing required term(s): bamboo|shoot")
    term_reject = reject_terms(product, "6463", ("chicken", "dinner", "meal", "noodle", "ramen", "soup", "stir"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("broccoli", "carrot", "chicken", "mushroom", "pepper", "pork") if product.ingredients_have_any(term)]
    if ingredient_hits:
        return reject("6463 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("6463 reviewed canned bamboo shoot contract accepted")


def olive_oil_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "8008", OIL_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("olive", "oil"):
        return reject("8008 missing required term(s): olive|oil")
    term_reject = reject_terms(product, "8008", ("butter", "dressing", "garlic", "marinade", "mayo", "mayonnaise", "spray", "truffle"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("basil", "cheese", "garlic", "parmesan", "spice", "spices") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)]
    if ingredient_hits:
        return reject("8008 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("8008 reviewed olive oil contract accepted")


def garlic_powder_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26508", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("garlic"):
        return reject("26508 missing required term(s): garlic")
    if not product.has_any("powder", "powdered", "granulated"):
        return reject("26508 missing powder/granulated cue")
    term_reject = reject_terms(product, "26508", ("bread", "butter", "dip", "pepper", "salt", "sauce", "seasoning"))
    if term_reject:
        return term_reject
    return accept("26508 reviewed garlic powder contract accepted")


def cumin_spice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26036", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("cumin"):
        return reject("26036 missing required term(s): cumin")
    term_reject = reject_terms(product, "26036", ("blend", "chili", "curry", "garam", "sauce", "seasoning", "taco"))
    if term_reject:
        return term_reject
    return accept("26036 reviewed cumin spice contract accepted")


def ground_beef_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "16791", ("beef", "meat"))
    if category_reject:
        return category_reject
    if not product.has_all("ground", "beef"):
        return reject("16791 missing required term(s): ground|beef")
    term_reject = reject_terms(product, "16791", ("jerky", "meatball", "patty", "roast", "sausage", "seasoned", "steak", "stew", "taco"))
    if term_reject:
        return term_reject
    return accept("16791 reviewed raw ground beef contract accepted")


def ground_beef_80_20_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "58121", ("beef", "meat"))
    if category_reject:
        return category_reject
    if not product.has_all("ground", "beef"):
        return reject("58121 missing required term(s): ground|beef")
    has_80_20_cue = (
        product.has_phrase("80 percent lean")
        or product.has_phrase("20 percent fat")
        or product.has_all("80", "20", "lean", "fat")
    )
    if not has_80_20_cue:
        return reject("58121 missing 80/20 lean cue")
    term_reject = reject_terms(
        product,
        "58121",
        ("73", "85", "90", "93", "95", "96", "97", "jerky", "meatball", "patty", "sausage", "seasoned", "steak", "stew", "taco"),
    )
    if term_reject:
        return term_reject
    return accept("58121 reviewed 80/20 ground beef contract accepted")


def zucchini_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "49326", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if product.category_has_any("canned", "frozen"):
        return reject("49326 category fresh mismatch")
    if not product.has_any("zucchini"):
        return reject("49326 missing required term(s): zucchini")
    term_reject = reject_terms(product, "49326", ("bread", "chip", "frozen", "noodle", "noodles", "pasta", "sauce", "spiral", "zoodles"))
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("bean", "broccoli", "carrot", "cauliflower", "pepper")
        if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)
    ]
    if ingredient_hits:
        return reject("49326 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("49326 reviewed fresh zucchini contract accepted")


def fresh_herb_contract(esha_code: str, herb: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, ("fresh", "herb", "herbs", "pre packaged", "produce", "spice", "vegetable"))
        if category_reject:
            return category_reject
        if (
            product.category_has_any("herb", "herbs", "spice")
            and not product.category_has_any("fresh", "pre packaged", "produce", "vegetable")
            and not product.has_any("fresh")
        ):
            return reject(f"{esha_code} category dried herb mismatch")
        herb_terms = (herb, f"{herb}s")
        if not product.has_any(*herb_terms):
            return reject(f"{esha_code} missing required term(s): {herb}")
        term_reject = reject_terms(product, esha_code, ("blend", "dried", "flakes", "garlic", "ground", "oil", "paste", "rub", "sauce", "seasoning", "soup"))
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed fresh {herb} contract accepted")

    return contract


def fresh_parsley_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26013", ("fresh", "produce", "pre packaged", "herb", "vegetable"))
    if category_reject:
        return category_reject
    if product.category_has_any("frozen"):
        return reject("26013 category frozen mismatch")
    if (
        product.category_has_any("baking", "herb", "herbs", "pantry", "spice", "spices")
        and not product.category_has_any("fresh", "pre packaged", "produce", "vegetable")
        and not product.has_any("fresh")
    ):
        return reject("26013 category dried herb mismatch")
    if not product.has_any("parsley"):
        return reject("26013 missing required term(s): parsley")
    term_reject = reject_terms(
        product,
        "26013",
        (
            "blend",
            "dried",
            "flakes",
            "freeze",
            "frozen",
            "garlic",
            "ground",
            "kit",
            "kale",
            "carrot",
            "carrots",
            "cabbage",
            "celery",
            "lettuce",
            "oil",
            "paste",
            "potato",
            "potatoes",
            "puree",
            "romaine",
            "salad",
            "salt",
            "sauce",
            "seasoned",
            "seasoning",
            "soup",
            "spinach",
            "squash",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in (
            "cabbage",
            "carrot",
            "celery",
            "garlic",
            "kale",
            "lettuce",
            "oil",
            "potato",
            "romaine",
            "salt",
            "sauce",
            "seasoning",
            "spinach",
            "squash",
            "sugar",
            "water",
        )
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("26013 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("26013 reviewed fresh parsley contract accepted")


def fresh_chive_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5359", ("pre packaged", "produce", "vegetable", "vegetables", "fresh"))
    if category_reject:
        return category_reject
    if not product.has_any("chive", "chives"):
        return reject("5359 missing required term(s): chive")
    term_reject = reject_terms(
        product,
        "5359",
        (
            "blend",
            "cheese",
            "chipotle",
            "cream",
            "dried",
            "garlic",
            "lemon",
            "onion",
            "paprika",
            "potato",
            "sauce",
            "seasoned",
            "seasoning",
            "sour",
            "vegan",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("cashew", "cheese", "garlic", "oil", "onion", "paprika", "pepper", "potato", "salt", "sugar")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("5359 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("5359 reviewed fresh chive contract accepted")


def lemon_zest_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "31962", ("baking", "fruit", "produce", "spice"))
    if category_reject:
        return category_reject
    if not product.has_any("lemon"):
        return reject("31962 missing required term(s): lemon")
    if not product.has_any("zest", "peel"):
        return reject("31962 missing zest/peel cue")
    term_reject = reject_terms(product, "31962", ("extract", "juice", "lemonade", "pepper", "sauce", "tea"))
    if term_reject:
        return term_reject
    return accept("31962 reviewed lemon zest contract accepted")


def egg_yolk_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "19600", ("egg", "eggs"))
    if category_reject:
        return category_reject
    if not product.has_any("egg", "eggs"):
        return reject("19600 missing required term(s): egg")
    if not product.has_any("yolk", "yolks"):
        return reject("19600 missing required term(s): yolk")
    term_reject = reject_terms(product, "19600", ("mayo", "mayonnaise", "noodle", "pasta", "powder"))
    if term_reject:
        return term_reject
    return accept("19600 reviewed egg yolk contract accepted")


def whole_wheat_flour_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38929", BAKING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("wheat", "flour"):
        return reject("38929 missing required term(s): wheat|flour")
    if not product.has_any("whole"):
        return reject("38929 missing required term(s): whole")
    term_reject = reject_terms(product, "38929", ("all", "bread", "cracker", "pancake", "tortilla", "white"))
    if term_reject:
        return term_reject
    return accept("38929 reviewed whole wheat flour contract accepted")


def generic_vinegar_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "24880", ("condiment", "sauce", "vinegar"))
    if category_reject:
        return category_reject
    if not product.has_any("vinegar"):
        return reject("24880 missing required term(s): vinegar")
    term_reject = reject_terms(
        product,
        "24880",
        ("chip", "dressing", "drinking", "flavored", "glaze", "gummy", "honey", "maple", "marinade", "pickle", "sauce", "seasoned", "sparkling", "sushi"),
    )
    if term_reject:
        return term_reject
    return accept("24880 reviewed vinegar contract accepted")


def avocado_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "44419", ("fruit", "produce", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("avocado"):
        return reject("44419 missing required term(s): avocado")
    term_reject = reject_terms(product, "44419", ("dressing", "guacamole", "oil", "salsa", "sauce", "spread", "toast"))
    if term_reject:
        return term_reject
    return accept("44419 reviewed fresh avocado contract accepted")


def bay_leaf_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26495", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("bay"):
        return reject("26495 missing required term(s): bay")
    if not product.has_any("leaf", "leaves", "ground"):
        return reject("26495 missing leaf cue")
    term_reject = reject_terms(product, "26495", ("candle", "sauce", "seasoning", "soup"))
    if term_reject:
        return term_reject
    return accept("26495 reviewed bay leaf contract accepted")


def coriander_spice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26041", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("coriander"):
        return reject("26041 missing required term(s): coriander")
    term_reject = reject_terms(product, "26041", ("blend", "chutney", "cumin", "curry", "sauce", "seasoning"))
    if term_reject:
        return term_reject
    return accept("26041 reviewed coriander spice contract accepted")


def cauliflower_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5049", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("cauliflower"):
        return reject("5049 missing required term(s): cauliflower")
    term_reject = reject_terms(product, "5049", ("au", "bake", "broccoli", "brown", "buffalo", "casserole", "crust", "gratin", "hash", "pizza", "puree", "rice", "riced", "sauce", "seasoned"))
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("broccoli", "cheese", "garlic", "oil", "pepper") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)
    ]
    if ingredient_hits:
        return reject("5049 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("5049 reviewed fresh cauliflower contract accepted")


def jalapeno_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "39180", (*VEGETABLE_CATEGORIES, "pepper"))
    if category_reject:
        return category_reject
    if product.category_has_any("pickle", "pickles", "relish"):
        return reject("39180 category pickled/relish mismatch")
    if not product.has_any("jalapeno"):
        return reject("39180 missing required term(s): jalapeno")
    term_reject = reject_terms(product, "39180", ("cheese", "dip", "nacho", "pickle", "pickled", "salsa", "sauce"))
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("cabbage", "cheese", "garlic", "sriracha", "vinegar") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)]
    if ingredient_hits:
        return reject("39180 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("39180 reviewed jalapeno pepper contract accepted")


def tortilla_chip_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "44330", ("chip", "chips", "snack", "tortilla"))
    if category_reject:
        return category_reject
    if not product.has_any("tortilla"):
        return reject("44330 missing required term(s): tortilla")
    if not product.has_any("chip", "chips"):
        return reject("44330 missing required term(s): chip")
    term_reject = reject_terms(
        product,
        "44330",
        ("cheddar", "cheese", "chili", "churro", "churros", "cinnamon", "flamin", "fuego", "hot", "jalapeno", "pumpkin", "ranch", "rolled", "roller", "salsa", "spici", "spicy", "ultimate"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("cheddar", "cheese", "chili", "cilantro", "flavor", "garlic", "jalapeno", "ranch", "seasoning", "tomato", "vinegar", "whey")
        if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)
    ]
    if ingredient_hits:
        return reject("44330 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("44330 reviewed plain tortilla chip contract accepted")


def dark_chocolate_contract_v2(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "16858", ("baking", "candy", "chocolate"))
    if category_reject:
        return category_reject
    if not product.has_all("dark", "chocolate"):
        return reject("16858 missing required term(s): dark|chocolate")
    term_reject = reject_terms(
        product,
        "16858",
        (
            "almond",
            "assorted",
            "assortment",
            "bark",
            "clusters",
            "coconut",
            "cookie",
            "creme",
            "drink",
            "fine",
            "ice",
            "mint",
            "non",
            "nonpareil",
            "nonpareils",
            "orange",
            "pareils",
            "raspberry",
            "sauce",
            "syrup",
            "truffle",
            "truffles",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("almond", "cashew", "cherry", "coconut", "hazelnut", "orange", "peanut", "pecan", "peppermint", "raspberry", "walnut")
        if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)
    ]
    if ingredient_hits:
        return reject("16858 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("16858 reviewed dark chocolate contract accepted")


def plain_rice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "24087", ("rice",))
    if category_reject:
        return category_reject
    if not product.has_any("rice"):
        return reject("24087 missing required term(s): rice")
    term_reject = reject_terms(
        product,
        "24087",
        (
            "beans",
            "beef",
            "broccoli",
            "brown",
            "cake",
            "cooked",
            "cracker",
            "dinner",
            "fried",
            "instant",
            "meal",
            "medley",
            "microwave",
            "mix",
            "pudding",
            "ready",
            "seasoned",
            "spanish",
            "white",
            "wild",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("bean", "beef", "broccoli", "chicken", "oil", "seasoning") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)]
    if ingredient_hits:
        return reject("24087 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("24087 reviewed plain dry rice contract accepted")


def plain_corn_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38652", ("canned", "corn", "vegetable", "vegetables"))
    if category_reject:
        return category_reject
    if not product.has_any("corn"):
        return reject("38652 missing required term(s): corn")
    term_reject = reject_terms(
        product,
        "38652",
        ("bread", "cereal", "chip", "chips", "flake", "flakes", "meal", "mexican", "oil", "popcorn", "snack", "taquito", "tortilla"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [term for term in ("cheese", "chili", "lime", "oil", "pepper", "seasoning") if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)]
    if ingredient_hits:
        return reject("38652 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("38652 reviewed plain corn contract accepted")


def fresh_orange_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "71682", ("fruit", "produce", "pre packaged"))
    if category_reject:
        return category_reject
    if product.category_has_any("jam", "jelly", "spread"):
        return reject("71682 category processed fruit mismatch")
    if not product.has_any("orange", "oranges"):
        return reject("71682 missing required term(s): orange")
    term_reject = reject_terms(product, "71682", ("beverage", "candied", "chicken", "confiture", "juice", "marmalade", "peel", "sauce", "soda", "syrup"))
    if term_reject:
        return term_reject
    return accept("71682 reviewed fresh orange contract accepted")


def fresh_lime_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "3857", ("fruit", "produce", "pre packaged"))
    if category_reject:
        return category_reject
    if not product.has_any("lime", "limes"):
        return reject("3857 missing required term(s): lime")
    term_reject = reject_terms(product, "3857", ("beverage", "blend", "chip", "fajita", "juice", "onion", "peel", "pepper", "sauce", "soda", "syrup", "vegetable"))
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("onion", "pepper", "vegetable") if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("3857 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("3857 reviewed fresh lime contract accepted")


def fresh_pineapple_contract(product: ProductFacts) -> MatchDecision:
    if not product.category_has_any("pre packaged", "produce"):
        return reject("27367 category mismatch")
    if product.category_has_any("canned", "frozen", "juice"):
        return reject("27367 category processed fruit mismatch")
    if not product.has_any("pineapple"):
        return reject("27367 missing required term(s): pineapple")
    term_reject = reject_terms(
        product,
        "27367",
        (
            "banana",
            "blend",
            "candied",
            "canned",
            "dried",
            "juice",
            "mango",
            "onion",
            "papaya",
            "pepper",
            "ring",
            "rings",
            "smoothie",
            "stir",
            "strawberry",
            "syrup",
            "tidbit",
            "tidbits",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("banana", "mango", "onion", "papaya", "pepper", "strawberry", "sugar", "syrup")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("27367 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("27367 reviewed fresh pineapple contract accepted")


def chicken_broth_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "50343", ("broth", "stock", "soup"))
    if category_reject:
        return category_reject
    if not product.has_any("broth", "stock"):
        return reject("50343 missing required term(s): broth|stock")
    if not product.has_any("chicken"):
        return reject("50343 missing required term(s): chicken")
    term_reject = reject_terms(product, "50343", ("beef", "bouillon", "cube", "cubes", "gravy", "noodle", "powder", "vegetable"))
    if term_reject:
        return term_reject
    return accept("50343 reviewed chicken broth contract accepted")


def jumbo_shell_pasta_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "91214", ("pasta", "noodle", "noodles"))
    if category_reject:
        return category_reject
    if not product.has_any("jumbo"):
        return reject("91214 missing required term(s): jumbo")
    if not product.has_any("shell", "shells"):
        return reject("91214 missing required term(s): shell")
    term_reject = reject_terms(product, "91214", ("dinner", "meal", "ravioli", "sauce", "stuffed"))
    if term_reject:
        return term_reject
    return accept("91214 reviewed jumbo shell pasta contract accepted")


def elbow_macaroni_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38579", ("pasta", "noodle", "macaroni"))
    if category_reject:
        return category_reject
    if not product.has_any("macaroni"):
        return reject("38579 missing required term(s): macaroni")
    if not product.has_any("elbow", "elbows"):
        return reject("38579 missing required term(s): elbow")
    term_reject = reject_terms(product, "38579", ("cheese", "dinner", "entree", "meal", "sauce"))
    if term_reject:
        return term_reject
    return accept("38579 reviewed dry elbow macaroni contract accepted")


def pie_crust_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "40775", ("baking", "crust", "dough", "frozen", "pie"))
    if category_reject:
        return category_reject
    if not product.has_all("pie", "crust"):
        return reject("40775 missing required term(s): pie|crust")
    term_reject = reject_terms(product, "40775", ("cookie", "graham", "pizza", "pot", "quiche"))
    if term_reject:
        return term_reject
    return accept("40775 reviewed frozen pie crust contract accepted")


def hamburger_bun_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "42508", ("bakery", "bread", "bun", "buns", "roll"))
    if category_reject:
        return category_reject
    if not product.has_any("hamburger"):
        return reject("42508 missing required term(s): hamburger")
    if not product.has_any("bun", "buns", "roll", "rolls"):
        return reject("42508 missing required term(s): bun")
    term_reject = reject_terms(product, "42508", ("hot", "slider", "stuffing"))
    if term_reject:
        return term_reject
    return accept("42508 reviewed hamburger bun contract accepted")


def prosciutto_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "92863", ("meat", "pork", "sausage"))
    if category_reject:
        return category_reject
    if not product.has_any("prosciutto"):
        return reject("92863 missing required term(s): prosciutto")
    term_reject = reject_terms(product, "92863", ("cheese", "cracker", "pizza", "sandwich", "snack", "wrapped"))
    if term_reject:
        return term_reject
    return accept("92863 reviewed sliced prosciutto contract accepted")


def pepperoni_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "13021", ("meat", "pork", "sausage"))
    if category_reject:
        return category_reject
    if not product.has_any("pepperoni"):
        return reject("13021 missing required term(s): pepperoni")
    term_reject = reject_terms(product, "13021", ("bread", "cheese", "cracker", "pizza", "roll", "sandwich", "snack"))
    if term_reject:
        return term_reject
    return accept("13021 reviewed pepperoni contract accepted")


def prepared_horseradish_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "27004", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("horseradish"):
        return reject("27004 missing required term(s): horseradish")
    term_reject = reject_terms(product, "27004", ("cream", "creamy", "dip", "garlic", "ketchup", "mustard", "onion", "sauce", "sriracha"))
    if term_reject:
        return term_reject
    return accept("27004 reviewed prepared horseradish contract accepted")


def mandarin_orange_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "31312", ("canned", "fruit", "snack"))
    if category_reject:
        return category_reject
    if product.category_has_any("concentrate", "frozen", "juice"):
        return reject("31312 category state mismatch")
    if not product.has_any("mandarin"):
        return reject("31312 missing required term(s): mandarin")
    if not product.has_any("orange", "oranges"):
        return reject("31312 missing required term(s): orange")
    term_reject = reject_terms(product, "31312", ("beverage", "blend", "frozen", "juice", "pineapple", "smoothie", "strawberry"))
    if term_reject:
        return term_reject
    return accept("31312 reviewed mandarin oranges contract accepted")


def basmati_rice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "46516", ("grain", "rice"))
    if category_reject:
        return category_reject
    if product.category_has_any("flavored"):
        return reject("46516 category state mismatch")
    if not product.has_all("basmati", "rice"):
        return reject("46516 missing required term(s): basmati|rice")
    term_reject = reject_terms(product, "46516", ("blend", "cooked", "dinner", "flavored", "flax", "garlic", "herb", "herbs", "instant", "meal", "microwave", "pilaf", "ready", "red", "roasted", "seasoned", "wild"))
    if term_reject:
        return term_reject
    return accept("46516 reviewed dry basmati rice contract accepted")


def marinara_sauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "9083", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("marinara", "sauce"):
        return reject("9083 missing required term(s): marinara|sauce")
    term_reject = reject_terms(product, "9083", ("alfredo", "cheese", "meat", "pizza", "vodka"))
    if term_reject:
        return term_reject
    return accept("9083 reviewed marinara sauce contract accepted")


def puff_pastry_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "49045", ("bakery", "baking", "dough", "frozen", "pastry"))
    if category_reject:
        return category_reject
    if not product.has_all("puff", "pastry"):
        return reject("49045 missing required term(s): puff|pastry")
    term_reject = reject_terms(
        product,
        "49045",
        (
            "appetizer",
            "appetizers",
            "bacon",
            "beef",
            "bite",
            "blueberry",
            "bourekas",
            "brie",
            "caramelized",
            "cheese",
            "crab",
            "creamy",
            "custard",
            "dessert",
            "dog",
            "dogs",
            "feta",
            "filled",
            "frank",
            "franks",
            "gorgonzola",
            "gravy",
            "meal",
            "onion",
            "potato",
            "puffs",
            "salmon",
            "spinach",
            "strudel",
            "toaster",
            "turnover",
            "wrapped",
        ),
    )
    if term_reject:
        return term_reject
    return accept("49045 reviewed puff pastry contract accepted")


def vanilla_bean_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "35278", (*BAKING_CATEGORIES, "spice"))
    if category_reject:
        return category_reject
    if not product.has_all("vanilla", "bean"):
        return reject("35278 missing required term(s): vanilla|bean")
    term_reject = reject_terms(product, "35278", ("cocoa", "extract", "paste", "sugar", "syrup", "yogurt"))
    if term_reject:
        return term_reject
    return accept("35278 reviewed vanilla bean contract accepted")


def condensed_tomato_soup_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "50504", ("soup",))
    if category_reject:
        return category_reject
    if not product.has_all("tomato", "soup"):
        return reject("50504 missing required term(s): tomato|soup")
    if not product.has_any("condensed"):
        return reject("50504 missing required term(s): condensed")
    term_reject = reject_terms(product, "50504", ("basil", "bisque", "cream", "creamy", "pasta"))
    if term_reject:
        return term_reject
    return accept("50504 reviewed condensed tomato soup contract accepted")


def butterscotch_chip_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "23184", ("baking", "chip", "chocolate", "dessert"))
    if category_reject:
        return category_reject
    if not product.has_any("butterscotch"):
        return reject("23184 missing required term(s): butterscotch")
    if not product.has_any("chip", "chips", "morsel", "morsels"):
        return reject("23184 missing required term(s): chip|morsel")
    term_reject = reject_terms(product, "23184", ("candy", "extract", "ganache", "schnapp", "schnapps", "syrup", "topping"))
    if term_reject:
        return term_reject
    return accept("23184 reviewed butterscotch baking chip contract accepted")


def chicken_thigh_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "15061", ("chicken", "meat", "poultry"))
    if category_reject:
        return category_reject
    if not product.has_all("chicken", "thigh"):
        return reject("15061 missing required term(s): chicken|thigh")
    if product.has_any("drumstick", "drumsticks"):
        return reject("15061 excluded term(s): drumstick")
    if product.has_phrase("bone-in") or product.has_phrase("bone in"):
        return reject("15061 excluded phrase(s): bone-in")
    if product.has_phrase("skin-on") or product.has_phrase("skin on"):
        return reject("15061 excluded phrase(s): skin-on")
    term_reject = reject_terms(product, "15061", ("breaded", "cooked", "dinner", "meal", "seasoned", "smoked", "wing"))
    if term_reject:
        return term_reject
    return accept("15061 reviewed raw chicken thigh contract accepted")


def chicken_wing_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "15046", ("chicken", "meat", "poultry"))
    if category_reject:
        return category_reject
    if not product.has_all("chicken", "wing"):
        return reject("15046 missing required term(s): chicken|wing")
    term_reject = reject_terms(product, "15046", ("breaded", "cooked", "dinner", "meal", "sauce", "seasoned", "smoked"))
    if term_reject:
        return term_reject
    return accept("15046 reviewed raw chicken wing contract accepted")


def salmon_fillet_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "17230", SEAFOOD_CATEGORIES)
    if category_reject:
        return category_reject
    if product.category_has_any("canned"):
        return reject("17230 category state mismatch")
    if not product.has_any("salmon"):
        return reject("17230 missing required term(s): salmon")
    if product.has_phrase("in oil"):
        return reject("17230 excluded phrase(s): in oil")
    if product.has_phrase("smoke flavored"):
        return reject("17230 excluded phrase(s): smoke flavored")
    term_reject = reject_terms(product, "17230", ("burger", "canned", "cooked", "dip", "jerky", "meal", "patty", "salad", "sauce", "seasoned", "smoked"))
    if term_reject:
        return term_reject
    return accept("17230 reviewed raw salmon fillet contract accepted")


def beef_stew_meat_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "27997", ("beef", "meat"))
    if category_reject:
        return category_reject
    if not product.has_all("beef", "stew"):
        return reject("27997 missing required term(s): beef|stew")
    if not product.has_any("meat", "chunks", "cut", "cuts"):
        return reject("27997 missing required stew meat cue")
    term_reject = reject_terms(product, "27997", ("cooked", "dinner", "meal", "seasoned", "soup"))
    if term_reject:
        return term_reject
    return accept("27997 reviewed beef stew meat contract accepted")


def italian_sausage_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "13082", ("meat", "pork", "sausage"))
    if category_reject:
        return category_reject
    if not product.has_all("italian", "sausage"):
        return reject("13082 missing required term(s): italian|sausage")
    term_reject = reject_terms(product, "13082", ("chicken", "crumbles", "dinner", "meal", "plant", "pizza", "turkey"))
    if term_reject:
        return term_reject
    return accept("13082 reviewed Italian pork sausage contract accepted")


def baby_carrot_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "9329", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("baby", "carrot"):
        return reject("9329 missing required term(s): baby|carrot")
    term_reject = reject_terms(product, "9329", ("cooked", "dip", "juice", "meal", "seasoned", "soup"))
    if term_reject:
        return term_reject
    return accept("9329 reviewed fresh baby carrot contract accepted")


def red_onion_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "90467", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("red", "onion"):
        return reject("90467 missing required term(s): red|onion")
    term_reject = reject_terms(product, "90467", ("dip", "fried", "pickled", "powder", "ring", "rings", "soup"))
    if term_reject:
        return term_reject
    return accept("90467 reviewed fresh red onion contract accepted")


def arugula_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6032", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("arugula", "rocket"):
        return reject("6032 missing required term(s): arugula")
    term_reject = reject_terms(product, "6032", ("dressing", "kit", "meal", "pizza", "salad"))
    if term_reject:
        return term_reject
    return accept("6032 reviewed fresh arugula contract accepted")


def onion_soup_mix_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "37790", ("soup", "seasoning", "mix"))
    if category_reject:
        return category_reject
    if not product.has_all("onion", "soup"):
        return reject("37790 missing required term(s): onion|soup")
    if not product.has_any("mix", "packet", "recipe"):
        return reject("37790 missing required soup mix cue")
    term_reject = reject_terms(product, "37790", ("broth", "canned", "french", "ready"))
    if term_reject:
        return term_reject
    return accept("37790 reviewed dry onion soup mix contract accepted")


def italian_breadcrumb_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "42358", ("bread", "breading", "crumb", "crumbs", "mix"))
    if category_reject:
        return category_reject
    if not product.has_any("italian"):
        return reject("42358 missing required term(s): italian")
    if not product.has_any("breadcrumb", "breadcrumbs", "crumb", "crumbs"):
        return reject("42358 missing required term(s): breadcrumb")
    term_reject = reject_terms(product, "42358", ("coconut", "dinner", "entree", "fish", "meal"))
    if term_reject:
        return term_reject
    return accept("42358 reviewed Italian bread crumb contract accepted")


def teriyaki_sauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "53615", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("teriyaki", "sauce"):
        return reject("53615 missing required term(s): teriyaki|sauce")
    term_reject = reject_terms(product, "53615", ("beef", "chicken", "jerky", "meal", "noodle", "rice"))
    if term_reject:
        return term_reject
    return accept("53615 reviewed teriyaki sauce contract accepted")


def whole_wheat_bread_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "36158", ("bakery", "bread"))
    if category_reject:
        return category_reject
    if not product.has_all("whole", "wheat", "bread"):
        return reject("36158 missing required term(s): whole|wheat|bread")
    term_reject = reject_terms(product, "36158", ("bagel", "bun", "crumb", "crouton", "dough", "english", "muffin", "roll", "tortilla"))
    if term_reject:
        return term_reject
    return accept("36158 reviewed whole wheat bread contract accepted")


def ginger_root_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "90442", ("fresh", "produce", "spice", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("ginger"):
        return reject("90442 missing required term(s): ginger")
    if product.category_has_any("beverage", "candy", "drink", "soda", "tea"):
        return reject("90442 category processed ginger mismatch")
    term_reject = reject_terms(product, "90442", ("ale", "beer", "candy", "chew", "crystallized", "ground", "powder", "syrup", "tea"))
    if term_reject:
        return term_reject
    return accept("90442 reviewed fresh ginger root contract accepted")


def arborio_rice_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "93184", ("grain", "rice"))
    if category_reject:
        return category_reject
    if not product.has_all("arborio", "rice"):
        return reject("93184 missing required term(s): arborio|rice")
    term_reject = reject_terms(product, "93184", ("blend", "dinner", "meal", "risotto", "seasoned", "side"))
    if term_reject:
        return term_reject
    return accept("93184 reviewed dry arborio rice contract accepted")


def ginger_ale_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4790", ("beverage", "soda", "soft", "drink"))
    if category_reject:
        return category_reject
    if not product.has_all("ginger", "ale"):
        return reject("4790 missing required term(s): ginger|ale")
    term_reject = reject_terms(product, "4790", ("beer", "diet", "hard", "light", "sugarfree", "zero"))
    if term_reject:
        return term_reject
    if product.has_phrase("sugar free") or product.has_phrase("zero sugar"):
        return reject("4790 excluded phrase(s): sugar free|zero sugar")
    return accept("4790 reviewed regular ginger ale contract accepted")


def apricot_preserves_contract(product: ProductFacts) -> MatchDecision:
    category_ok = product.category_has_any("jam", "jelly", "preserve", "spread", "condiment", "sauce", "pantry")
    preserve_cue = (
        product.has_any("jam", "preserv")
        or product.has_phrase("preserve")
        or product.has_phrase("preserves")
    )
    if not category_ok and not preserve_cue:
        return reject("23299 category mismatch")
    if not product.has_any("apricot"):
        return reject("23299 missing required term(s): apricot")
    if not preserve_cue:
        return reject("23299 missing required preserve cue")
    term_reject = reject_terms(product, "23299", ("bar", "cookie", "dried", "fruit", "glaze", "sauce", "syrup"))
    if term_reject:
        return term_reject
    return accept("23299 reviewed apricot preserves contract accepted")


def dried_apricot_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "48542", ("dried", "fruit", "snack", "wholesome"))
    if category_reject:
        return category_reject
    if not product.has_any("apricot", "apricots"):
        return reject("48542 missing required term(s): apricot")
    if not (product.has_any("dried", "sun-dried") or product.has_phrase("dried apricot")):
        return reject("48542 missing dried fruit cue")
    term_reject = reject_terms(
        product,
        "48542",
        ("canned", "conditioner", "juice", "kernel", "nectar", "oil", "shampoo", "syrup", "yogurt"),
    )
    if term_reject:
        return term_reject
    return accept("48542 reviewed dried apricot contract accepted")


def cream_cheese_state_contract(esha_code: str, state_terms: tuple[str, ...]) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, ("cheese", "dairy"))
        if category_reject:
            return category_reject
        if not product.has_phrase("cream cheese"):
            return reject(f"{esha_code} missing required phrase(s): cream cheese")
        state_ok = any(product.has_any(term) for term in state_terms)
        state_ok = state_ok or product.has_phrase("less fat") or product.has_phrase("fat free")
        if not state_ok:
            return reject(f"{esha_code} missing required cream cheese state")
        term_reject = reject_terms(product, esha_code, ("chip", "cracker", "dip", "frosting", "icing", "spread"))
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed cream cheese state contract accepted")

    return contract


def condensed_cream_chicken_soup_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "50475", ("soup",))
    if category_reject:
        return category_reject
    if not product.has_all("cream", "chicken", "soup"):
        return reject("50475 missing required term(s): cream|chicken|soup")
    if not product.has_any("condensed"):
        return reject("50475 missing required term(s): condensed")
    term_reject = reject_terms(product, "50475", ("celery", "mushroom", "noodle", "potato", "ready"))
    if term_reject:
        return term_reject
    return accept("50475 reviewed condensed cream of chicken soup contract accepted")


def quinoa_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38079", ("grain", "quinoa", "rice"))
    if category_reject:
        return category_reject
    if product.category_has_any("flavored"):
        return reject("38079 category prepared grain mismatch")
    if not product.has_any("quinoa"):
        return reject("38079 missing required term(s): quinoa")
    term_reject = reject_terms(
        product,
        "38079",
        (
            "bar",
            "barley",
            "basmati",
            "buckwheat",
            "bulgur",
            "chip",
            "couscous",
            "cracker",
            "dinner",
            "lentil",
            "meal",
            "mediterranean",
            "millet",
            "pilaf",
            "rice",
            "salad",
            "side",
            "soup",
            "spinach",
            "tomato",
        ),
    )
    if term_reject:
        return term_reject
    return accept("38079 reviewed dry quinoa contract accepted")


def cream_style_corn_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "6265", ("canned", "corn", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("corn"):
        return reject("6265 missing required term(s): corn")
    if not (product.has_any("cream", "creamed") or product.has_phrase("cream style")):
        return reject("6265 missing cream-style cue")
    term_reject = reject_terms(product, "6265", ("bread", "chip", "frozen", "meal", "muffin", "soup"))
    if term_reject:
        return term_reject
    return accept("6265 reviewed cream-style corn contract accepted")


def graham_cracker_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "34639", ("cracker", "cookie", "snack"))
    if category_reject:
        return category_reject
    if not product.has_all("graham", "cracker"):
        return reject("34639 missing required term(s): graham|cracker")
    term_reject = reject_terms(product, "34639", ("cereal", "crust", "pie", "sandwich"))
    if term_reject:
        return term_reject
    return accept("34639 reviewed graham cracker contract accepted")


def lard_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "8107", ("baking", "fat", "lard", "oil"))
    if category_reject:
        return category_reject
    if not product.has_any("lard"):
        return reject("8107 missing required term(s): lard")
    term_reject = reject_terms(product, "8107", ("soap", "seasoning"))
    if term_reject:
        return term_reject
    return accept("8107 reviewed lard contract accepted")


def pork_loin_roast_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "12285", ("meat", "pork"))
    if category_reject:
        return category_reject
    if not product.has_all("pork", "loin"):
        return reject("12285 missing required term(s): pork|loin")
    roast_like = (
        product.has_any("roast", "roasts", "filet", "fillet", "boneles")
        or product.has_phrase("boneless")
    )
    if not roast_like:
        return reject("12285 missing required roast/boneless cue")
    term_reject = reject_terms(
        product,
        "12285",
        (
            "applewood",
            "bacon",
            "barbecue",
            "bbq",
            "butt",
            "chop",
            "chops",
            "garlic",
            "gravy",
            "ham",
            "herb",
            "korean",
            "lemon",
            "marinated",
            "meal",
            "mesquite",
            "pepper",
            "portobello",
            "ribs",
            "sausage",
            "seasoned",
            "shoulder",
            "smoked",
            "steak",
            "tenderloin",
        ),
    )
    if term_reject:
        return term_reject
    if product.has_phrase("roasted garlic"):
        return reject("12285 excluded phrase(s): roasted garlic")
    return accept("12285 reviewed pork loin roast contract accepted")


def whole_ham_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "12170", ("ham", "meat", "pork"))
    if category_reject:
        return category_reject
    if not product.has_any("ham"):
        return reject("12170 missing required term(s): ham")
    whole_like = (
        product.has_any("whole", "half", "portion", "quarter", "spiral", "shank")
        or product.has_phrase("bone in")
        or product.has_phrase("bone-in")
        or product.has_phrase("whole family")
        or product.has_phrase("whole muscle")
        or product.has_phrase("spiral cut")
        or product.has_phrase("spiral-cut")
    )
    if not whole_like:
        return reject("12170 missing required whole ham cue")
    term_reject = reject_terms(
        product,
        "12170",
        (
            "base",
            "bean",
            "beans",
            "bites",
            "breakfast",
            "burrito",
            "cheddar",
            "cheese",
            "chicken",
            "chips",
            "croquette",
            "croquettes",
            "deli",
            "diced",
            "egg",
            "flavor",
            "flavored",
            "flavour",
            "gruyere",
            "jerky",
            "lunch",
            "lunchmeat",
            "meatless",
            "omelet",
            "pepperoni",
            "pizza",
            "salad",
            "sandwich",
            "seasoning",
            "slice",
            "sliced",
            "snack",
            "soup",
            "spread",
            "steak",
            "steaks",
            "sub",
            "turkey",
            "vegan",
            "veggie",
            "vegetarian",
            "wrap",
        ),
    )
    if term_reject:
        return term_reject
    return accept("12170 reviewed whole ham contract accepted")


def pimiento_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "9200", ("canned", "condiment", "vegetable"))
    if category_reject:
        return category_reject
    if not product.has_any("pimiento", "pimientos", "pimento", "pimentos"):
        return reject("9200 missing required term(s): pimiento")
    term_reject = reject_terms(product, "9200", ("cheese", "olive", "olives", "spread"))
    if term_reject:
        return term_reject
    return accept("9200 reviewed canned pimiento contract accepted")


def pistachio_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4521", NUT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("pistachio"):
        return reject("4521 missing required term(s): pistachio")
    term_reject = reject_terms(
        product,
        "4521",
        (
            "bar",
            "bbq",
            "butter",
            "chili",
            "chocolate",
            "cluster",
            "honey",
            "jalapeno",
            "ranch",
            "sweet",
            "vinegar",
        ),
    )
    if term_reject:
        return term_reject
    return accept("4521 reviewed pistachio contract accepted")


def oat_bran_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38064", ("bran", "cereal", "grain"))
    if category_reject:
        return category_reject
    if not product.has_all("oat", "bran"):
        return reject("38064 missing required term(s): oat|bran")
    term_reject = reject_terms(
        product,
        "38064",
        ("almond", "bar", "bread", "cluster", "flake", "granola", "muffin", "raisin", "rice", "vanilla", "wheat"),
    )
    if term_reject:
        return term_reject
    return accept("38064 reviewed dry oat bran contract accepted")


def reduced_fat_sour_cream_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "538", ("dairy", "sour", "cream"))
    if category_reject:
        return category_reject
    if not product.has_phrase("sour cream"):
        return reject("538 missing required phrase(s): sour cream")
    if not (product.has_any("reduced", "light") or product.has_phrase("less fat")):
        return reject("538 missing reduced-fat cue")
    term_reject = reject_terms(product, "538", ("chip", "dip", "onion", "potato"))
    if term_reject:
        return term_reject
    return accept("538 reviewed reduced-fat sour cream contract accepted")


def marshmallow_creme_contract(esha_code: str) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, ("baking", "dessert", "topping"))
        if category_reject:
            return category_reject
        if not product.has_any("marshmallow"):
            return reject(f"{esha_code} missing required term(s): marshmallow")
        if not product.has_any("cream", "creme", "fluff"):
            return reject(f"{esha_code} missing marshmallow creme cue")
        term_reject = reject_terms(product, esha_code, ("bar", "candy", "cereal", "cookie", "hot", "ice"))
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed marshmallow creme contract accepted")

    return contract


def chunky_salsa_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "7480", ("condiment", "salsa", "sauce"))
    if category_reject:
        return category_reject
    if not product.has_any("salsa"):
        return reject("7480 missing required term(s): salsa")
    if not product.has_any("chunky"):
        return reject("7480 missing required term(s): chunky")
    term_reject = reject_terms(product, "7480", ("bean", "cheese", "con", "dip", "fruit", "mango", "pineapple", "queso", "verde"))
    if term_reject:
        return term_reject
    return accept("7480 reviewed chunky salsa contract accepted")


def potato_starch_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "30261", ("baking", "starch"))
    if category_reject:
        return category_reject
    if not product.has_all("potato", "starch"):
        return reject("30261 missing required term(s): potato|starch")
    term_reject = reject_terms(product, "30261", ("chip", "flour", "snack"))
    if term_reject:
        return term_reject
    return accept("30261 reviewed potato starch contract accepted")


def steak_sauce_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "92310", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not (product.has_phrase("steak sauce") or product.has_any("a1", "a.1")):
        return reject("92310 missing required term(s): steak sauce")
    term_reject = reject_terms(product, "92310", ("marinade", "seasoning"))
    if term_reject:
        return term_reject
    return accept("92310 reviewed steak sauce contract accepted")


def barley_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "37704", ("barley", "grain"))
    if category_reject:
        return category_reject
    if not product.has_any("barley"):
        return reject("37704 missing required term(s): barley")
    term_reject = reject_terms(product, "37704", ("beer", "cereal", "malt", "soup"))
    if term_reject:
        return term_reject
    return accept("37704 reviewed barley contract accepted")


def rye_bread_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "19177", ("bakery", "bread"))
    if category_reject:
        return category_reject
    if not product.has_all("rye", "bread"):
        return reject("19177 missing required term(s): rye|bread")
    term_reject = reject_terms(product, "19177", ("bagel", "chip", "cracker", "crispbread", "crumb", "crouton", "mix"))
    if term_reject:
        return term_reject
    return accept("19177 reviewed rye bread contract accepted")


def chow_mein_noodle_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38346", ("noodle", "pasta"))
    if category_reject:
        return category_reject
    if not product.has_all("chow", "mein"):
        return reject("38346 missing required term(s): chow|mein")
    if not product.has_any("noodle"):
        return reject("38346 missing required term(s): noodle")
    term_reject = reject_terms(product, "38346", ("dinner", "meal", "sauce"))
    if term_reject:
        return term_reject
    return accept("38346 reviewed chow mein noodle contract accepted")


def biscuit_mix_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "42317", ("baking", "mix"))
    if category_reject:
        return category_reject
    if not product.has_all("biscuit", "mix"):
        return reject("42317 missing required term(s): biscuit|mix")
    term_reject = reject_terms(product, "42317", ("breakfast", "sandwich"))
    if term_reject:
        return term_reject
    return accept("42317 reviewed biscuit mix contract accepted")


def self_rising_white_cornmeal_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38255", ("baking", "corn", "grain", "meal", "flour"))
    if category_reject:
        return category_reject
    if not (product.has_any("cornmeal") or (product.has_any("corn") and product.has_any("meal"))):
        return reject("38255 missing required term(s): cornmeal")
    if not product.has_any("white"):
        return reject("38255 missing required term(s): white")
    if not (product.has_phrase("self rising") or product.has_phrase("self-rising") or (product.has_any("self") and product.has_any("rising"))):
        return reject("38255 missing required term(s): self|rising")
    term_reject = reject_terms(product, "38255", ("blue", "breading", "cornbread", "fish", "fry", "hush", "mush", "puppy", "yellow"))
    if term_reject:
        return term_reject
    return accept("38255 reviewed self-rising white cornmeal contract accepted")


def vital_wheat_gluten_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38448", ("baking", "flour"))
    if category_reject:
        return category_reject
    if not product.has_all("wheat", "gluten"):
        return reject("38448 missing required term(s): wheat|gluten")
    if not product.has_any("vital"):
        return reject("38448 missing required term(s): vital")
    return accept("38448 reviewed vital wheat gluten contract accepted")


def rye_flour_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "38022", BAKING_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("rye", "flour"):
        return reject("38022 missing required term(s): rye|flour")
    term_reject = reject_terms(product, "38022", ("bread", "cracker", "mix"))
    if term_reject:
        return term_reject
    return accept("38022 reviewed rye flour contract accepted")


def apple_pie_filling_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "48001", ("baking", "fruit", "pie"))
    if category_reject:
        return category_reject
    if not product.has_all("apple", "pie"):
        return reject("48001 missing required term(s): apple|pie")
    if not product.has_any("filling"):
        return reject("48001 missing required term(s): filling")
    term_reject = reject_terms(product, "48001", ("crust", "turnover"))
    if term_reject:
        return term_reject
    return accept("48001 reviewed apple pie filling contract accepted")


def potato_chip_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "53909", ("chip", "chips", "snack"))
    if category_reject:
        return category_reject
    if not product.has_all("potato", "chip"):
        return reject("53909 missing required term(s): potato|chip")
    term_reject = reject_terms(
        product,
        "53909",
        (
            "barbecue",
            "bbq",
            "cheddar",
            "chocolate",
            "cookie",
            "dip",
            "hot",
            "jalapeno",
            "onion",
            "root",
            "sour",
            "sweet",
            "tortilla",
            "vegetable",
            "vinegar",
        ),
    )
    if term_reject:
        return term_reject
    return accept("53909 reviewed potato chip contract accepted")


def salami_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "13234", ("meat", "salami", "sausage"))
    if category_reject:
        return category_reject
    if not product.has_any("salami"):
        return reject("13234 missing required term(s): salami")
    term_reject = reject_terms(
        product,
        "13234",
        ("bite", "bites", "charcuterie", "cheddar", "cheese", "cracker", "panino", "pizza", "plate", "snack", "snacker", "snackers", "turkey"),
    )
    if term_reject:
        return term_reject
    return accept("13234 reviewed salami contract accepted")


def almond_milk_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "16455", ("milk", "plant"))
    if category_reject:
        return category_reject
    if not product.has_phrase("almond milk"):
        return reject("16455 missing required phrase(s): almond milk")
    term_reject = reject_terms(product, "16455", ("chocolate", "coffee", "creamer", "latte", "mocha", "nog", "protein", "shake", "vanilla"))
    if term_reject:
        return term_reject
    return accept("16455 reviewed plain almond milk contract accepted")


def cream_of_coconut_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "4649", ("baking", "canned", "coconut"))
    if category_reject:
        return category_reject
    if not (product.has_phrase("cream of coconut") or product.has_all("coconut", "cream")):
        return reject("4649 missing required term(s): coconut cream")
    term_reject = reject_terms(product, "4649", ("ice", "milk", "oil", "soup", "water", "yogurt"))
    if term_reject:
        return term_reject
    return accept("4649 reviewed cream of coconut contract accepted")


def desiccated_coconut_contract(product: ProductFacts) -> MatchDecision:
    category_ok = product.category_has_any("baking", "coconut", "fruit", "pantry", "international", "natural", "organic")
    if not product.has_any("coconut"):
        return reject("63085 missing required term(s): coconut")
    form_ok = (
        product.has_any("desiccated", "powder")
        or product.has_phrase("coconut powder")
        or (
            product.has_any("flake", "flakes", "shredded")
            and (product.has_any("unsweetened", "raw") or product.has_phrase("no sugar added"))
        )
    )
    if not category_ok and not form_ok:
        return reject("63085 category mismatch")
    if not form_ok:
        return reject("63085 missing required term(s): desiccated|powder")
    term_reject = reject_terms(
        product,
        "63085",
        ("bar", "butter", "candy", "chip", "chips", "cookie", "cream", "creamer", "flour", "milk", "oil", "protein", "snack", "sweetened", "toasted", "water"),
    )
    if term_reject:
        return term_reject
    return accept("63085 reviewed desiccated coconut contract accepted")


def dried_currant_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "9755", ("dried", "fruit", "snack"))
    if category_reject:
        return category_reject
    if not product.has_any("currant"):
        return reject("9755 missing required term(s): currant")
    term_reject = reject_terms(product, "9755", ("black", "jam", "jelly", "juice", "syrup"))
    if term_reject:
        return term_reject
    return accept("9755 reviewed dried currant contract accepted")


def white_cheddar_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "36978", ("cheese",))
    if category_reject:
        return category_reject
    if not product.has_all("white", "cheddar"):
        return reject("36978 missing required term(s): white|cheddar")
    term_reject = reject_terms(
        product,
        "36978",
        (
            "blend",
            "cracker",
            "cream",
            "crisp",
            "crisps",
            "dip",
            "dippable",
            "macaroni",
            "marble",
            "mexican",
            "monterey",
            "popcorn",
            "sauce",
            "snack",
            "snacker",
            "snackers",
            "spreadable",
            "triple",
            "yellow",
        ),
    )
    if term_reject:
        return term_reject
    return accept("36978 reviewed white cheddar cheese contract accepted")


def cheddar_cheese_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "634", ("cheese",))
    if category_reject:
        return category_reject
    if not product.has_any("cheddar"):
        return reject("634 missing required term(s): cheddar")
    term_reject = reject_terms(
        product,
        "634",
        (
            "american",
            "asiago",
            "blend",
            "blends",
            "cashew",
            "colby",
            "cracker",
            "cream",
            "dip",
            "gouda",
            "jack",
            "jalapeno",
            "mac",
            "macaroni",
            "mexican",
            "monterey",
            "mozzarella",
            "parmesan",
            "pasta",
            "pepper",
            "pizza",
            "plant",
            "provolone",
            "queso",
            "romano",
            "snack",
            "snacker",
            "snackers",
            "spicy",
            "swiss",
            "taco",
            "vegan",
        ),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term
        for term in ("almond", "cashew", "coconut", "jalapeno", "monterey", "mozzarella", "pepper", "romano", "swiss")
        if product.ingredients_have_any(term) or product.ingredients_have_phrase(term)
    ]
    if ingredient_hits:
        return reject("634 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("634 reviewed cheddar cheese contract accepted")


def catfish_fillet_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "17033", SEAFOOD_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("catfish"):
        return reject("17033 missing required term(s): catfish")
    term_reject = reject_terms(product, "17033", ("breaded", "cooked", "dinner", "meal", "nugget", "seasoned"))
    if term_reject:
        return term_reject
    return accept("17033 reviewed catfish fillet contract accepted")


def anchovy_paste_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "34570", ("condiment", "fish", "seafood"))
    if category_reject:
        return category_reject
    if not product.has_any("anchovy", "anchovies"):
        return reject("34570 missing required term(s): anchovy")
    if not product.has_any("paste"):
        return reject("34570 missing required term(s): paste")
    return accept("34570 reviewed anchovy paste contract accepted")


def asparagus_spear_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "5711", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("asparagus"):
        return reject("5711 missing required term(s): asparagus")
    term_reject = reject_terms(product, "5711", ("canned", "frozen", "pickled", "soup"))
    if term_reject:
        return term_reject
    return accept("5711 reviewed fresh asparagus spear contract accepted")


def ground_veal_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "11581", ("meat", "veal"))
    if category_reject:
        return category_reject
    if not product.has_all("ground", "veal"):
        return reject("11581 missing required term(s): ground|veal")
    term_reject = reject_terms(product, "11581", ("breaded", "cooked", "meal"))
    if term_reject:
        return term_reject
    return accept("11581 reviewed ground veal contract accepted")


def raspberry_preserves_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "91272", ("jam", "jelly", "preserve", "spread"))
    if category_reject:
        return category_reject
    if not product.has_any("raspberry"):
        return reject("91272 missing required term(s): raspberry")
    if not product.has_any("preserve", "preserves", "jam"):
        return reject("91272 missing required preserve cue")
    term_reject = reject_terms(product, "91272", ("bar", "cookie", "sauce", "syrup"))
    if term_reject:
        return term_reject
    return accept("91272 reviewed raspberry preserves contract accepted")


def seedless_raspberry_jam_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "90887", ("jam", "jelly", "preserve", "spread"))
    if category_reject:
        return category_reject
    if not product.has_any("raspberry"):
        return reject("90887 missing required term(s): raspberry")
    if not product.has_any("jam", "preserve", "preserves", "spread"):
        return reject("90887 missing jam/preserve cue")
    if not (product.has_any("seedless") or product.ingredients_have_any("seedless")):
        return reject("90887 missing required term(s): seedless")
    term_reject = reject_terms(product, "90887", ("bar", "cookie", "jalapeno", "sauce", "syrup"))
    if term_reject:
        return term_reject
    return accept("90887 reviewed seedless raspberry jam contract accepted")


def liquid_egg_substitute_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "41383", ("egg", "substitute"))
    if category_reject:
        return category_reject
    if not product.has_any("egg"):
        return reject("41383 missing required term(s): egg")
    if not product.has_any("liquid"):
        return reject("41383 missing required term(s): liquid")
    if not (product.has_any("substitute") or product.has_phrase("egg product") or product.has_any("breakfree", "break-free")):
        return reject("41383 missing egg substitute cue")
    term_reject = reject_terms(product, "41383", ("whole", "white", "whites", "powder"))
    if term_reject:
        return term_reject
    return accept("41383 reviewed liquid egg substitute contract accepted")


def honeydew_melon_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "25758", ("fruit", "produce", "pre packaged"))
    if category_reject:
        return category_reject
    if not product.has_any("honeydew"):
        return reject("25758 missing required term(s): honeydew")
    if product.category_has_any("canned", "frozen", "juice", "powdered"):
        return reject("25758 category state mismatch")
    term_reject = reject_terms(
        product,
        "25758",
        ("candy", "cantaloupe", "drink", "flavor", "flavored", "frozen", "ice", "juice", "mix", "taffy", "trio", "watermelon"),
    )
    if term_reject:
        return term_reject
    ingredient_hits = [
        term for term in ("cantaloupe", "grape", "pineapple", "strawberry", "watermelon")
        if product.ingredients_have_any(term)
    ]
    if ingredient_hits:
        return reject("25758 excluded ingredient term(s): " + "|".join(ingredient_hits))
    return accept("25758 reviewed fresh honeydew contract accepted")


def spice_seed_contract(esha_code: str, seed: str, reject_ground: bool = False) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        category_reject = require_category(product, esha_code, SEASONING_CATEGORIES)
        if category_reject:
            return category_reject
        if not product.has_any(seed):
            return reject(f"{esha_code} missing required term(s): {seed}")
        if not product.has_any("seed", "seeds"):
            return reject(f"{esha_code} missing required term(s): seed")
        if reject_ground and product.has_any("ground", "powder"):
            return reject(f"{esha_code} excluded ground seed")
        term_reject = reject_terms(product, esha_code, ("candy", "cookie", "oil", "sauce", "tea"))
        if term_reject:
            return term_reject
        return accept(f"{esha_code} reviewed {seed} seed contract accepted")

    return contract


def serrano_pepper_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "37838", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("serrano"):
        return reject("37838 missing required term(s): serrano")
    if not product.has_any("pepper", "peppers", "chile", "chiles", "chili", "chilies"):
        return reject("37838 missing required term(s): pepper")
    if product.category_has_any("canned", "pickle", "pickles", "relish", "salsa", "sauce"):
        return reject("37838 category state mismatch")
    term_reject = reject_terms(
        product,
        "37838",
        ("canned", "cheese", "chip", "dried", "ham", "jam", "pickled", "salsa", "sauce", "snack", "stuffed", "yogurt"),
    )
    if term_reject:
        return term_reject
    return accept("37838 reviewed fresh serrano pepper contract accepted")


def hot_chili_pepper_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "13367", VEGETABLE_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("pepper", "peppers", "chile", "chiles", "chili", "chilies"):
        return reject("13367 missing required term(s): pepper")
    if not product.has_any("hot", "habanero", "jalapeno", "serrano", "thai", "fresno"):
        return reject("13367 missing required hot chile cue")
    term_reject = reject_terms(
        product,
        "13367",
        ("can", "canned", "chip", "chips", "diced", "jar", "pickled", "sauce", "sliced", "snack", "vinegar"),
    )
    if term_reject:
        return term_reject
    return accept("13367 reviewed fresh hot chili pepper contract accepted")


def candied_ginger_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "49218", ("candy", "snack"))
    if category_reject:
        return category_reject
    if not product.has_any("ginger"):
        return reject("49218 missing required term(s): ginger")
    if not product.has_any("candied", "crystallized", "crystallised", "sweetened"):
        return reject("49218 missing candied ginger cue")
    term_reject = reject_terms(product, "49218", ("bar", "beer", "cookie", "drink", "tea"))
    if term_reject:
        return term_reject
    return accept("49218 reviewed candied ginger contract accepted")


def halibut_fillet_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "41219", SEAFOOD_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_any("halibut"):
        return reject("41219 missing required term(s): halibut")
    if not product.has_any("fillet", "fillets"):
        return reject("41219 missing required term(s): fillet")
    term_reject = reject_terms(product, "41219", ("breaded", "cooked", "meal", "seasoned"))
    if term_reject:
        return term_reject
    return accept("41219 reviewed halibut fillet contract accepted")


def msg_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "26098", SEASONING_CATEGORIES)
    if category_reject:
        return category_reject
    if not (product.has_any("msg") or product.ingredients_have_any("msg") or product.has_phrase("monosodium glutamate")):
        return reject("26098 missing required term(s): msg")
    term_reject = reject_terms(product, "26098", ("salt", "seasoned"))
    if term_reject:
        return term_reject
    return accept("26098 reviewed MSG seasoning contract accepted")


def beef_gravy_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "53023", ("gravy", "sauce"))
    if category_reject:
        return category_reject
    if not product.has_all("beef", "gravy"):
        return reject("53023 missing required term(s): beef|gravy")
    term_reject = reject_terms(
        product,
        "53023",
        ("base", "broth", "burger", "corned", "frank", "jerky", "meatball", "pasta", "patty", "patties", "roast", "rub", "snack", "stew", "stock"),
    )
    if term_reject:
        return term_reject
    return accept("53023 reviewed beef gravy contract accepted")


def fruit_cocktail_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "3164", ("canned", "fruit"))
    if category_reject:
        return category_reject
    if not product.has_all("fruit", "cocktail"):
        return reject("3164 missing required term(s): fruit|cocktail")
    if not product.has_any("juice"):
        return reject("3164 missing required term(s): juice")
    term_reject = reject_terms(product, "3164", ("gel", "snack", "syrup"))
    if term_reject:
        return term_reject
    return accept("3164 reviewed canned fruit cocktail in juice contract accepted")


def dried_prune_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "3126", ("dried", "fruit", "snack", "wholesome"))
    if category_reject:
        return category_reject
    if not product.has_any("prune", "prunes"):
        return reject("3126 missing required term(s): prune")
    term_reject = reject_terms(
        product,
        "3126",
        ("cake", "cereal", "filling", "juice", "lekvar", "smoothie", "yogurt"),
    )
    if term_reject:
        return term_reject
    return accept("3126 reviewed dried prune contract accepted")


def malt_vinegar_contract(product: ProductFacts) -> MatchDecision:
    category_reject = require_category(product, "41309", CONDIMENT_CATEGORIES)
    if category_reject:
        return category_reject
    if not product.has_all("malt", "vinegar"):
        return reject("41309 missing required term(s): malt|vinegar")
    term_reject = reject_terms(
        product,
        "41309",
        ("batter", "beetroot", "chip", "chips", "fish", "ketchup", "pickle", "pickled", "pretzel", "snack"),
    )
    if term_reject:
        return term_reject
    return accept("41309 reviewed malt vinegar contract accepted")


CONTRACTS: dict[str, ContractFn] = {
    "15061": chicken_thigh_contract,
    "15046": chicken_wing_contract,
    "17230": salmon_fillet_contract,
    "27997": beef_stew_meat_contract,
    "13082": italian_sausage_contract,
    "9329": baby_carrot_contract,
    "90467": red_onion_contract,
    "6032": arugula_contract,
    "37790": onion_soup_mix_contract,
    "42358": italian_breadcrumb_contract,
    "53615": teriyaki_sauce_contract,
    "36158": whole_wheat_bread_contract,
    "44895": make_simple_contract("44895", OIL_CATEGORIES, ("sunflower", "oil"), ("butter", "dressing", "spray")),
    "26627": fresh_herb_contract("26627", "rosemary"),
    "90442": ginger_root_contract,
    "25760": simple_fresh_fruit_contract("25760", "strawberry"),
    "47878": simple_cheese_contract("47878", "gruyere", ("cracker", "dressing", "emmentaler", "fondue", "puff", "sauce")),
    "93184": arborio_rice_contract,
    "4790": ginger_ale_contract,
    "23299": apricot_preserves_contract,
    "48542": dried_apricot_contract,
    "91953": make_simple_contract("91953", SEASONING_CATEGORIES, ("onion", "salt"), ("chip", "dip", "soup")),
    "38079": quinoa_contract,
    "1452": cream_cheese_state_contract("1452", ("fat", "free", "fatfree", "nonfat")),
    "33229": cream_cheese_state_contract("33229", ("light", "reduced")),
    "55029": cream_cheese_state_contract("55029", ("reduced", "light")),
    "50475": condensed_cream_chicken_soup_contract,
    "6265": cream_style_corn_contract,
    "4521": pistachio_contract,
    "34639": graham_cracker_contract,
    "8107": lard_contract,
    "9200": pimiento_contract,
    "1005": simple_cheese_contract("1005", "brie", ("cracker", "dressing", "fondue", "puff", "sauce", "spreadable", "truffle")),
    "38064": oat_bran_contract,
    "538": reduced_fat_sour_cream_contract,
    "23064": marshmallow_creme_contract("23064"),
    "23071": marshmallow_creme_contract("23071"),
    "7480": chunky_salsa_contract,
    "26024": ground_spice_contract("26024", "mace"),
    "30261": potato_starch_contract,
    "92310": steak_sauce_contract,
    "37704": barley_contract,
    "19177": rye_bread_contract,
    "38346": chow_mein_noodle_contract,
    "42317": biscuit_mix_contract,
    "38255": self_rising_white_cornmeal_contract,
    "38448": vital_wheat_gluten_contract,
    "38022": rye_flour_contract,
    "1060": make_simple_contract("1060", ("cheese", "dairy"), ("neufchatel", "cheese"), ("cracker", "dip", "frosting", "icing", "spread")),
    "48001": apple_pie_filling_contract,
    "53909": potato_chip_contract,
    "13234": salami_contract,
    "16455": almond_milk_contract,
    "4649": cream_of_coconut_contract,
    "9755": dried_currant_contract,
    "634": cheddar_cheese_contract,
    "36978": white_cheddar_contract,
    "17033": catfish_fillet_contract,
    "34570": anchovy_paste_contract,
    "5711": asparagus_spear_contract,
    "1281": simple_cheese_contract("1281", "colby", ("cracker", "dip", "jack", "marbled", "sauce")),
    "11581": ground_veal_contract,
    "91272": raspberry_preserves_contract,
    "90887": seedless_raspberry_jam_contract,
    "41383": liquid_egg_substitute_contract,
    "26013": fresh_parsley_contract,
    "1054": simple_cheese_contract("1054", "gouda", ("asiago", "cheddar", "chipotle", "cumin", "jalapeno", "mac", "smoked", "spread", "truffle")),
    "33351": simple_cheese_contract("33351", "muenster", ("cheddar", "marbled", "pepperoni", "salami", "sandwich", "sausage")),
    "35063": spice_seed_contract("35063", "fenugreek", reject_ground=True),
    "25758": honeydew_melon_contract,
    "37838": serrano_pepper_contract,
    "26106": spice_seed_contract("26106", "anise"),
    "49218": candied_ginger_contract,
    "41219": halibut_fillet_contract,
    "26098": msg_contract,
    "53023": beef_gravy_contract,
    "3164": fruit_cocktail_contract,
    "3126": dried_prune_contract,
    "41309": malt_vinegar_contract,
    "38579": elbow_macaroni_contract,
    "40775": pie_crust_contract,
    "42508": hamburger_bun_contract,
    "92863": prosciutto_contract,
    "13021": pepperoni_contract,
    "27004": prepared_horseradish_contract,
    "31312": mandarin_orange_contract,
    "46516": basmati_rice_contract,
    "9083": marinara_sauce_contract,
    "49045": puff_pastry_contract,
    "35278": vanilla_bean_contract,
    "50504": condensed_tomato_soup_contract,
    "23184": butterscotch_chip_contract,
    "91972": make_simple_contract("91972", SEASONING_CATEGORIES, ("celery", "salt"), ("chip", "dip", "seed", "soup")),
    "31545": make_simple_contract("31545", CONDIMENT_CATEGORIES, ("hoisin", "sauce"), ("dressing", "marinade", "meal")),
    "91947": make_simple_contract("91947", SEASONING_CATEGORIES, ("cajun", "seasoning"), ("butter", "dip", "sauce", "snack")),
    "93138": make_simple_contract("93138", ("baking", "cereal", "grain"), ("wheat", "germ"), ("bread", "cereal", "cracker")),
    "4715": nut_contract("4715", ("macadamia",)),
    "90212": black_pepper_contract,
    "49598": fresh_garlic_contract,
    "37777": brown_egg_contract,
    "26624": vanilla_extract_contract,
    "63413": brown_sugar_contract,
    "1251": parmesan_cheese_contract,
    "26003": ground_spice_contract("26003", "cinnamon", ("sugar",)),
    "555": sour_cream_contract,
    "1015": cream_cheese_contract,
    "25132": honey_contract,
    "15054": chicken_breast_contract,
    "15130": whole_roasting_chicken_contract,
    "18030": make_simple_contract("18030", CONDIMENT_CATEGORIES, ("worcestershire",), ("marinade", "seasoning")),
    "7320": fresh_carrot_contract,
    "26010": make_simple_contract("26010", SEASONING_CATEGORIES, ("paprika",), ("chip", "chicken", "sauce", "seasoning")),
    "501": light_cream_contract,
    "502": heavy_whipping_cream_contract,
    "93509": dried_herb_contract("93509", "oregano"),
    "93286": make_simple_contract("93286", SEASONING_CATEGORIES, ("kosher", "salt"), ("almond", "bar", "candy", "chip", "chocolate", "garlic", "nut", "pepper", "seasoned", "snack")),
    "3072": simple_juice_contract("3072", "lime"),
    "5709": green_onion_contract,
    "92175": fresh_cilantro_contract,
    "1854": simple_juice_contract("1854", "orange"),
    "22940": make_simple_contract("22940", CONDIMENT_CATEGORIES, ("dijon", "mustard"), ("dressing", "honey", "sauce")),
    "26026": ground_spice_contract("26026", "nutmeg"),
    "3853": fresh_lemon_contract,
    "1565": simple_cheese_contract("1565", "mozzarella", ("cheddar", "parmesan", "provolone", "stick", "sticks")),
    "4086": ground_spice_contract("4086", "ginger"),
    "8084": make_simple_contract("8084", OIL_CATEGORIES, ("canola", "oil"), ("blend", "dressing", "spray")),
    "15401": dried_herb_contract("15401", "thyme"),
    "8008": olive_oil_contract,
    "26508": garlic_powder_contract,
    "26036": cumin_spice_contract,
    "26035": dried_herb_contract("26035", "parsley"),
    "6448": onion_contract,
    "24087": plain_rice_contract,
    "50343": chicken_broth_contract,
    "38652": plain_corn_contract,
    "39463": fresh_mushroom_contract,
    "71682": fresh_orange_contract,
    "3857": fresh_lime_contract,
    "27367": fresh_pineapple_contract,
    "16791": ground_beef_contract,
    "58121": ground_beef_80_20_contract,
    "49326": zucchini_contract,
    "26046": fresh_herb_contract("26046", "basil"),
    "31962": lemon_zest_contract,
    "19600": egg_yolk_contract,
    "38929": whole_wheat_flour_contract,
    "24880": generic_vinegar_contract,
    "26623": fresh_herb_contract("26623", "thyme"),
    "26009": dried_herb_contract("26009", "oregano"),
    "44419": avocado_contract,
    "26495": bay_leaf_contract,
    "26041": coriander_spice_contract,
    "5359": fresh_chive_contract,
    "27371": simple_fresh_fruit_contract("27371", "strawberry"),
    "5049": cauliflower_contract,
    "26110": make_simple_contract("26110", SEASONING_CATEGORIES, ("mustard",), ("dressing", "honey", "sauce", "seasoning")),
    "26514": ground_mustard_contract,
    "26030": dried_herb_contract("26030", "rosemary"),
    "35024": make_simple_contract("35024", SEASONING_CATEGORIES, ("turmeric",), ("drink", "shot", "supplement", "tea")),
    "9555": make_simple_contract("9555", CONDIMENT_CATEGORIES, ("barbecue", "sauce"), ("chip", "meatball", "rib", "seasoning")),
    "35186": make_simple_contract("35186", CONDIMENT_CATEGORIES, ("rice", "vinegar"), ("dressing", "marinade", "seasoned", "sushi")),
    "6927": make_simple_contract("6927", ("canned", "tomato", "tomatoes", "vegetable"), ("crushed", "tomato"), ("marinara", "paste", "pizza", "sauce", "soup", "stewed")),
    "39180": jalapeno_contract,
    "13367": hot_chili_pepper_contract,
    "27415": make_simple_contract("27415", VEGETABLE_CATEGORIES, ("romaine", "lettuce"), ("caesar", "dressing", "kit", "salad")),
    "36160": make_simple_contract("36160", ("bakery", "bread", "bun"), ("white", "bread"), ("crumb", "crouton", "dough", "garlic", "stuffing")),
    "19171": make_simple_contract("19171", ("bakery", "bread"), ("french", "bread"), ("challah", "garlic", "pizza", "sandwich", "stick", "toast", "toasting")),
    "44330": tortilla_chip_contract,
    "3383": simple_fresh_fruit_contract("3383", "raspberry"),
    "9676": make_simple_contract("9676", ("canned", "tomato", "tomatoes", "vegetable"), ("stewed", "tomato"), ("sauce", "soup")),
    "12280": make_simple_contract("12280", ("meat", "pork"), ("pork", "tenderloin"), ("bacon", "garlic", "herb", "marinated", "peppercorn", "seasoned", "sausage", "teriyaki")),
    "36021": make_simple_contract("36021", VEGETABLE_CATEGORIES, ("broccoli", "floret"), ("bake", "casserole", "cheese", "rice", "sauce", "seasoned")),
    "46903": make_simple_contract("46903", VEGETABLE_CATEGORIES, ("butternut", "squash"), ("noodle", "noodles", "pasta", "ravioli", "sauce", "soup", "spiral", "spiralized")),
    "16858": dark_chocolate_contract_v2,
    "1235": simple_cheese_contract("1235", "blue", ("dip", "dressing", "salad")),
    "12285": pork_loin_roast_contract,
    "12170": whole_ham_contract,
    "71030": make_simple_contract("71030", ("baking", "cracker", "crumb"), ("graham", "crumb"), ("crust", "pie")),
    "51333": make_simple_contract("51333", VEGETABLE_CATEGORIES, ("red", "potato"), ("chip", "fry", "mashed", "salad", "seasoned")),
    "5180": make_simple_contract("5180", CONDIMENT_CATEGORIES, ("tomato", "sauce"), ("alfredo", "bbq", "ketchup", "marinara", "pasta", "pizza", "salsa", "spaghetti", "vodka")),
    "15399": dried_herb_contract("15399", "basil"),
    "9161": tomato_paste_contract,
    "19507": egg_white_contract,
    "51162": balsamic_vinegar_contract,
    "26019": ground_spice_contract("26019", "clove"),
    "26004": curry_powder_contract,
    "27202": white_vinegar_contract,
    "1324": monterey_jack_contract,
    "669": garlic_salt_contract,
    "1237": simple_cheese_contract("1237", "feta", ("blueberry", "dressing", "goat", "salad")),
    "20952": evaporated_milk_contract,
    "500": half_and_half_contract,
    "6449": shallot_contract,
    "25002": maple_syrup_contract,
    "33366": swiss_cheese_contract,
    "93282": italian_seasoning_contract,
    "45896": dark_brown_sugar_contract,
    "25003": molasses_contract,
    "6757": fresh_broccoli_contract,
    "26000": ground_spice_contract("26000", "allspice"),
    "6765": fresh_cabbage_contract,
    "7": lowfat_buttermilk_contract,
    "37935": whole_buttermilk_contract,
    "20950": sweetened_condensed_milk_contract,
    "90963": vegetable_shortening_contract,
    "41502": fresh_mushroom_contract,
    "1817": frozen_peas_contract,
    "27329": green_beans_contract,
    "45897": superfine_sugar_contract,
    "48595": fresh_sweet_potato_contract,
    "93116": rolled_oats_contract,
    "25000": light_corn_syrup_contract,
    "16157": ground_turkey_contract,
    "4441": chickpea_contract,
    "1508": cottage_cheese_contract,
    "9633": frozen_sweet_corn_contract,
    "793": apple_juice_contract,
    "48587": fresh_russet_potato_contract,
    "12281": ground_pork_contract,
    "26040": celery_seed_contract,
    "26039": ground_cardamom_contract,
    "26029": pumpkin_pie_spice_contract,
    "36425": garam_masala_contract,
    "26021": dill_weed_contract,
    "18031": yellow_mustard_contract,
    "26028": poultry_seasoning_contract,
    "33312": simple_cheese_contract("33312", "provolone", ("asiago", "blend", "fontina", "mozzarella", "parmesan")),
    "26015": make_simple_contract("26015", SEASONING_CATEGORIES, ("poppy", "seed"), ("cake", "dressing", "muffin")),
    "7169": canned_named_bean_contract("7169", ("cannellini",)),
    "4085": apple_cider_contract,
    "33341": simple_cheese_contract("33341", "american", ("cheddar", "colby", "mac", "macaroni", "melt")),
    "31332": maraschino_cherry_contract,
    "53473": oyster_sauce_contract,
    "26025": dried_herb_contract("26025", "marjoram"),
    "41522": cocoa_powder_contract_v2,
    "23437": chocolate_syrup_contract,
    "48582": snow_pea_contract,
    "553": light_sour_cream_contract,
    "9669": frozen_mixed_vegetable_contract,
    "23005": orange_marmalade_contract,
    "45487": pizza_sauce_contract,
    "38528": long_grain_white_rice_contract,
    "5113": onion_flake_contract,
    "38281": couscous_contract,
    "27413": iceberg_lettuce_contract,
    "33320": pesto_sauce_contract,
    "26018": make_simple_contract("26018", SEASONING_CATEGORIES, ("caraway", "seed"), ()),
    "26014": make_simple_contract("26014", SEASONING_CATEGORIES, ("table", "salt"), ("blend", "celery", "free", "garlic", "herb", "onion", "pepper", "seasoning")),
    "8009": corn_oil_contract,
    "6768": red_cabbage_contract,
    "9260": canned_named_bean_contract("9260", ("great", "northern")),
    "31262": saltine_cracker_contract,
    "93100": pearl_barley_contract,
    "26646": crystallized_ginger_contract,
    "25066": grenadine_syrup_contract,
    "31961": make_simple_contract("31961", SEASONING_CATEGORIES, ("saffron", "thread"), ()),
    "4787": club_soda_contract,
    "14790": ground_chicken_contract,
    "9651": frozen_plain_berry_contract("9651", "strawberry"),
    "38289": wild_rice_contract,
    "13488": enchilada_sauce_contract,
    "7005": lentil_contract,
    "1240": simple_cheese_contract("1240", "gorgonzola"),
    "42144": seasoned_breadcrumb_contract,
    "63655": agave_nectar_contract,
    "71219": italian_bread_contract,
    "26105": make_simple_contract("26105", SEASONING_CATEGORIES, ("fennel", "seed"), ()),
    "25757": cantaloupe_contract,
    "28211": baking_cocoa_contract,
    "72906": tilapia_contract,
    "5032": brussels_sprout_contract,
    "47873": simple_cheese_contract("47873", "fontina", ("asiago", "blend", "parmesan", "provolone")),
    "13578": ground_lamb_contract,
    "23054": plain_jam_contract,
    "23205": jam_contract("23205", "apricot"),
    "19179": sourdough_bread_contract,
    "27383": cranberry_sauce_contract,
    "47445": extra_lean_ground_beef_contract,
    "550": fat_free_sour_cream_contract,
    "63085": desiccated_coconut_contract,
    "49654": creme_fraiche_contract,
    "1250": fresh_mozzarella_contract,
    "48321": nonfat_mozzarella_contract,
    "52964": vanilla_wafer_contract,
    "5716": fresh_radish_contract,
    "8968": instant_rice_contract,
    "48588": frozen_plain_berry_contract("48588", "raspberry"),
    "63537": pumpkin_seed_contract_v2,
    "92242": jam_contract("92242", "raspberry"),
    "25877": make_simple_contract("25877", ("bread", "crouton", "croutons"), ("crouton",), ("meal", "salad")),
    "9559": alfredo_sauce_contract,
    "57968": beef_hot_dog_contract,
    "26705": tamari_contract,
    "25010": dark_corn_syrup_contract,
    "33167": spicy_brown_mustard_contract,
    "46522": jasmine_rice_contract,
    "26031": make_simple_contract("26031", SEASONING_CATEGORIES, ("ground", "sage"), ()),
    "36409": make_simple_contract("36409", SEASONING_CATEGORIES, ("herbes", "provence"), ()),
    "34571": garlic_paste_contract,
    "7173": red_kidney_bean_contract,
    "6463": bamboo_shoot_contract,
    "7378": red_lentil_contract,
    "92163": ramen_noodle_contract("92163"),
    "28169": ramen_noodle_contract("28169", ("chicken",)),
    "58511": andouille_sausage_contract,
    "38328": pasta_shape_contract("38328", "orzo"),
    "16533": bisquick_contract,
    "23007": marshmallow_contract,
    "70963": ritz_cracker_contract,
    "8037": coconut_oil_contract,
    "42007": pita_bread_contract,
    "54387": whipped_topping_contract,
    "26571": ground_spice_contract("26571", "coriander", ("cumin",)),
    "16638": crescent_roll_contract,
    "26503": ground_spice_contract("26503", "cumin", ("coriander",)),
    "41429": ranch_dressing_mix_contract,
    "48475": graham_cracker_crust_contract,
    "19170": baguette_contract,
    "5222": watercress_contract,
    "23183": mini_chocolate_chip_contract,
    "19153": lump_crabmeat_contract,
    "19029": scallop_contract,
    "90065": golden_syrup_contract,
    "46081": white_cake_mix_contract,
    "90018": black_eyed_pea_contract,
    "48561": mixed_salad_green_contract,
    "12879": wonton_wrapper_contract,
    "1282": colby_monterey_jack_contract,
    "13485": guacamole_contract,
    "42757": tomatoes_green_chile_contract,
    "51131": turkey_breast_contract,
    "1262": romano_cheese_contract,
    "24339": plain_coffee_contract,
    "41521": milk_chocolate_contract,
    "28003": baking_soda_contract,
    "91200": pasta_shape_contract("91200", "bow"),
    "4522": pumpkin_seed_contract,
    "91193": pasta_shape_contract("91193", "rotini"),
    "38591": pasta_shape_contract("38591", "linguine"),
    "46509": pizza_dough_contract,
    "19021": clam_juice_contract,
    "38799": xanthan_gum_contract,
    "3858": simple_fresh_fruit_contract("3858", "kiwi"),
    "27373": simple_fresh_fruit_contract("27373", "watermelon"),
    "49270": salted_peanut_contract,
    "45528": phyllo_dough_contract,
    "42004": dry_breadcrumb_contract,
    "23015": caramel_candy_contract,
    "23442": semisweet_chocolate_morsel_contract,
    "35204": simple_alcohol_contract("35204", "marsala"),
    "22514": simple_alcohol_contract("22514", "gin"),
    "38589": pasta_shape_contract("38589", "rigatoni"),
    "4577": pecan_piece_contract,
    "20013": instant_coffee_powder_contract,
    "46494": devil_food_cake_mix_contract,
    "15071": raw_chicken_contract,
    "11967": lowfat_plain_yogurt_contract,
    "37836": make_simple_contract("37836", VEGETABLE_CATEGORIES, ("bok", "choy"), ("sauce", "soup")),
    "8278": shortening_contract,
    "5799": make_simple_contract("5799", VEGETABLE_CATEGORIES, ("acorn", "squash"), ("baby", "soup")),
    "3838": mango_chutney_contract,
    "49277": nut_contract("49277", ("walnut",)),
    "23070": caramel_topping_contract,
    "19037": imitation_crab_contract,
    "12893": extra_firm_tofu_contract,
    "4756": dry_roasted_peanut_contract,
    "8047": make_simple_contract("8047", OIL_CATEGORIES, ("grapeseed", "oil"), ("dressing", "spray")),
    "9539": generic_olive_contract,
    "51362": generic_tortilla_contract,
    "27301": baked_beans_contract,
    "22670": simple_alcohol_contract("22670", "whiskey"),
    "35205": vermouth_contract,
    "33295": espresso_contract,
    "38396": pasta_shape_contract("38396", "shell"),
    "4770": flax_seed_contract,
    "37597": popped_popcorn_contract,
    "91198": pasta_shape_contract("91198", "ziti"),
    "12008": canadian_bacon_contract,
    "34574": chili_paste_contract,
    "33128": chili_garlic_sauce_contract,
    "91197": pasta_shape_contract("91197", "penne"),
    "4928": pomegranate_juice_contract,
    "5589": frozen_hash_browns_contract,
    "8772": make_simple_contract("8772", OIL_CATEGORIES, ("safflower", "oil"), ("dressing", "margarine", "mayonnaise", "spray")),
    "4966": chocolate_shavings_contract,
    "794": grapefruit_juice_contract,
    "19026": oyster_contract,
    "7351": fresh_white_mushroom_contract,
    "16621": refrigerated_biscuit_contract,
    "34067": dark_beer_contract,
    "15424": ladyfinger_contract,
    "295": thousand_island_contract,
    "73123": prawn_contract,
    "8085": make_simple_contract("8085", OIL_CATEGORIES, ("walnut", "oil"), ("dressing", "spray")),
    "52470": make_simple_contract("52470", ("bread", "bun", "roll", "bakery"), ("kaiser",), ("sandwich",)),
    "33770": rice_noodle_contract,
    "38801": make_simple_contract("38801", (*BAKING_CATEGORIES, "starch"), ("arrowroot",), ("cookie", "cracker")),
    "12896": silken_tofu_contract,
    "91201": pasta_shape_contract("91201", "farfalle"),
    "4794": lemonade_contract,
    "93175": make_simple_contract("93175", (*BAKING_CATEGORIES, "starch"), ("tapioca",), ("pudding", "pearl", "pearls")),
    "37877": habanero_pepper_contract,
    "20032": sprite_contract,
    "3487": craisin_contract,
    "15455": hot_dog_bun_contract,
    "91214": jumbo_shell_pasta_contract,
    "6863": fresh_spinach_contract,
    "17741": white_kidney_bean_contract,
    "38987": skirt_steak_contract,
    "6251": french_style_green_bean_contract,
    "27980": beef_roast_contract,
    "35078": juniper_berry_contract,
    "49315": raw_cane_sugar_contract,
    "7846": stuffed_green_olive_contract,
    "26037": white_pepper_contract,
    "23640": ciabatta_bun_contract,
    "58267": flank_steak_contract,
    "42257": refrigerated_breadstick_contract,
    "48217": candied_red_cherry_contract,
    "91182": pasta_shape_contract("91182", "fettuccine"),
    "29575": ground_flaxseed_contract,
    "4696": peanut_contract,
    "82043": cayenne_pepper_contract,
    "91211": lasagna_noodle_contract,
    "12888": firm_tofu_contract,
    "31180": splenda_granular_contract,
    "22671": simple_alcohol_contract("22671", "bourbon"),
    "36986": sauerkraut_contract,
    "20033": soy_milk_contract,
    "4986": cranberry_juice_contract,
    "4513": hazelnut_contract,
    "50473": cream_of_celery_soup_contract,
    "63195": cashew_contract,
    "8555": ranch_dressing_contract,
    "48015": cherry_pie_filling_contract,
    "4686": tahini_contract,
    "8479": miracle_whip_contract,
    "22519": kahlua_contract,
    "8233": sunflower_oil_contract,
    "92017": quick_oats_contract,
    "22593": simple_alcohol_contract("22593", "rum"),
    "508": whipped_topping_contract,
    "26630": fresh_mint_contract,
    "2004": vanilla_ice_cream_contract,
    "48557": dried_cranberry_contract,
    "52629": shrimp_contract,
    "52630": cooked_shrimp_contract,
    "26017": cream_of_tartar_contract,
    "6813": eggplant_contract,
    "53474": fish_sauce_contract,
    "4511": coconut_contract("4511", ("shredded",)),
    "4573": coconut_contract("4573", ("flaked",)),
    "22604": sherry_contract,
    "14984": green_chile_contract,
    "5001": asparagus_contract,
    "41524": baking_chocolate_contract("41524", "semisweet"),
    "22513": simple_alcohol_contract("22513", "brandy"),
    "5446": sun_dried_tomato_contract,
    "22594": simple_alcohol_contract("22594", "vodka"),
    "38277": bread_flour_contract,
    "22614": simple_alcohol_contract("22614", "beer"),
    "90965": cooking_oil_contract,
    "13472": corn_tortilla_contract,
    "5172": plum_tomato_contract,
    "46086": make_simple_contract("46086", BAKING_CATEGORIES, ("cake", "flour"), ("bread", "mix", "pancake", "rice")),
    "34814": splenda_contract,
    "6298": pumpkin_puree_contract,
    "45336": mustard_contract("45336"),
    "35682": mustard_contract("35682"),
    "3006": applesauce_contract,
    "5441": pepper_contract("5441", "yellow"),
    "26482": taco_seasoning_contract,
    "24169": baking_chocolate_contract("24169", "unsweetened"),
    "4356": baking_chocolate_contract("4356", "bittersweet"),
    "4591": mixed_nuts_contract,
    "434": chili_sauce_contract,
    "46089": yellow_cake_mix_contract,
    "6499": kalamata_olive_contract,
    "3934": golden_raisin_contract,
    "6492": roma_tomato_contract,
    "3996": tomato_juice_contract,
    "5476": tomato_puree_contract,
    "4545": sunflower_seed_contract,
    "38004": yellow_cornmeal_contract,
    "23008": miniature_marshmallow_contract,
    "92830": penne_pasta_contract,
    "26830": crabmeat_contract,
    "90659": white_chocolate_contract,
    "23447": white_chocolate_chip_contract,
    "9114": spaghetti_sauce_contract,
    "1272": velveeta_contract,
    "26901": black_peppercorn_contract,
    "5206": leek_contract,
    "3380": banana_contract,
    "25570": salsa_contract,
    "50477": cream_soup_contract("50477", "mushroom", ("chicken",)),
    "90374": cream_soup_contract("90374", "chicken", ("mushroom",)),
    "91928": seasoning_salt_contract,
    "90530": cherry_tomato_contract,
    "5511": capers_contract,
    "3381": blueberry_contract,
    "4504": almond_contract("4504"),
    "49260": almond_contract("49260", require_cut=True),
    "1793": vegetable_broth_contract,
    "22501": red_wine_contract,
    "3990": pineapple_juice_contract,
    "5104": white_onion_contract,
    "26622": fresh_dill_contract,
    "36417": make_simple_contract("36417", SEASONING_CATEGORIES, ("chili", "powder"), ("chocolate", "hemp", "protein", "sauce")),
    "45892": powdered_sugar_contract,
    "4578": nut_contract("4578", ("pecan",)),
    "4557": nut_contract("4557", ("walnut",)),
    "30000": make_simple_contract("30000", BAKING_CATEGORIES, ("cornstarch",), ("cereal", "confectioner", "confectioners", "fortified", "hydrolyzed", "powdered", "sugar", "thicken", "thickener")),
    "5055": make_simple_contract("5055", VEGETABLE_CATEGORIES, ("celery",), ("butter", "carrot", "cooked", "frozen", "ginger", "green", "gumbo", "juice", "kick", "lemon", "mix", "peanut", "pineapple", "powder", "salt", "seed", "soup", "spinach")),
    "7805": make_simple_contract("7805", VEGETABLE_CATEGORIES, ("red", "onion"), ("blend", "carrot", "confiture", "dip", "fried", "jam", "mediterranean", "parsnip", "pickled", "potato", "powder", "ring", "rings", "root", "soup", "squash", "zucchini")),
    "5169": tomato_contract,
    "7425": diced_tomato_contract,
    "6989": pepper_contract("6989", "red"),
    "6846": pepper_contract("6846", "green"),
    "5715": make_simple_contract("5715", VEGETABLE_CATEGORIES, ("potato",), ("bite", "canned", "cheddar", "chip", "frozen", "fry", "fries", "hash", "loaded", "mashed", "packet", "seasoning", "skin", "sweet")),
    "3766": make_simple_contract("3766", ("dried fruit", "fruit", "snack"), ("raisin",), ("bread", "cereal", "chocolate", "cookie", "covered", "cranberry", "mix", "trail", "yogurt")),
    "12165": bacon_contract,
    "27204": make_simple_contract("27204", CONDIMENT_CATEGORIES, ("vinegar", "red", "wine"), ("dressing", "garlic", "herb", "marinade")),
    "26669": make_simple_contract("26669", CONDIMENT_CATEGORIES, ("ketchup",), ("chip", "fries", "hamburger", "meatloaf", "mustard")),
    "44966": make_simple_contract("44966", ("margarine", "spread"), ("margarine",), ("butter", "blend", "cookie", "frosting", "potato")),
    "22504": white_wine_contract,
    "49296": make_simple_contract("49296", SEASONING_CATEGORIES, ("sea", "salt"), ("almond", "bar", "candy", "chip", "chocolate", "cracker", "garlic", "nut", "onion", "pepper", "seasoned", "smoked", "snack", "truffle", "vinegar")),
    "26008": make_simple_contract("26008", SEASONING_CATEGORIES, ("onion", "powder"), ("chip", "dip", "ring", "soup")),
    "51329": banana_contract,
    "26513": make_simple_contract("26513", SEASONING_CATEGORIES, ("mustard",), ("dressing", "honey", "sauce")),
    "8771": make_simple_contract("8771", OIL_CATEGORIES, ("sesame", "oil"), ("dressing", "marinade", "sauce", "snack")),
    "44896": make_simple_contract("44896", OIL_CATEGORIES, ("peanut", "oil"), ("butter", "dressing", "marinade", "sauce", "snack")),
    "35301": make_simple_contract("35301", OIL_CATEGORIES, ("cooking", "spray"), ("butter", "flavor")),
    "23712": cocoa_powder_contract,
    "53475": make_simple_contract("53475", CONDIMENT_CATEGORIES, ("cider", "vinegar"), ("dressing", "flavored", "gummy", "honey", "maple", "marinade")),
    "42439": make_simple_contract("42439", ("bread", "breading", "baking"), ("bread", "crumb"), ("garlic", "herb", "italian", "parmesan", "seasoned")),
    "3088": make_simple_contract("3088", ("fruit", "produce", "spice"), ("orange",), ("beef", "candied", "candy", "chicken", "dish", "meal", "smoothie", "sugar", "syrup")),
    "28000": make_simple_contract("28000", BAKING_CATEGORIES, ("yeast",), ("extract", "nutritional", "spread")),
    "53471": make_simple_contract("53471", CONDIMENT_CATEGORIES, ("tabasco", "sauce"), ("buffalo", "habanero", "jerky", "meat", "scorpion", "stick")),
    "53470": make_simple_contract("53470", CONDIMENT_CATEGORIES, ("hot", "sauce"), ("barbecue", "cheese", "cocktail", "curry", "dog", "nacho", "tartar")),
    "4523": make_simple_contract("4523", ("seed", "spice"), ("sesame",), ("apricot", "bar", "bun", "coconut", "cracker", "crunch", "crunchy", "date", "mini", "minis", "oil", "rice", "snack", "sugar", "sunflower", "syrup", "tahini")),
    "25490": flour_tortilla_contract,
    "2013": plain_yogurt_contract,
    "3001": apple_contract,
}
