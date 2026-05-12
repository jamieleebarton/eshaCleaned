from __future__ import annotations

import re
from typing import Iterable


def norm_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def norm_head(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def split_terms(value: object) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", str(value or "").lower()) if t}


# Curated aliases only. Do not use prefix matching here: "Pasta" must not match
# "Pasta Dish", and "Nuts" must not match "Nut Butter".
HEAD_ALIASES: dict[str, set[str]] = {
    "baked beans": {"baked beans"},
    "beans": {"beans"},
    "beans rice": {"beans rice", "beans and rice"},
    "beans and rice": {"beans rice", "beans and rice"},
    "biscuit": {"biscuit", "biscuits"},
    "biscuits": {"biscuit", "biscuits"},
    "brownie": {"brownie"},
    "base": {"base"},
    "bouillon": {"bouillon"},
    "broth": {"broth"},
    "candy": {"candy", "chocolate", "chocolate bar", "candy bar"},
    "candy bar": {"candy bar", "chocolate bar"},
    "catsup": {"catsup", "ketchup"},
    "chewing gum": {"chewing gum", "gum"},
    "chocolate": {"chocolate", "chocolate bar", "candy"},
    "chocolate bar": {"chocolate bar", "candy bar", "chocolate"},
    "coleslaw": {"coleslaw", "salad"},
    "cookie": {"cookie", "cookies"},
    "cookies": {"cookie", "cookies"},
    "cream cheese": {"cream cheese"},
    "croissant": {"croissant"},
    "doughnut": {"doughnut", "donut"},
    "donut": {"doughnut", "donut"},
    "dressing": {"dressing", "salad dressing"},
    "fruit spread": {"fruit spread", "spread"},
    "glucose gel": {"glucose gel", "glucose"},
    "gum": {"gum", "chewing gum"},
    "jam preserves": {"jam preserves", "jam"},
    "ketchup": {"ketchup", "catsup"},
    "macaroni cheese": {"macaroni cheese", "macaroni and cheese"},
    "macaroni and cheese": {"macaroni cheese", "macaroni and cheese"},
    "milk": {"milk"},
    "almond milk": {"almond milk"},
    "oat milk": {"oat milk"},
    "soy milk": {"soy milk"},
    "coconut milk": {"coconut milk"},
    "plant milk": {"almond milk", "oat milk", "soy milk", "coconut milk", "plant milk"},
    "buttermilk": {"buttermilk"},
    "eggnog": {"eggnog"},
    "eggnog substitute": {"eggnog substitute"},
    "cream substitute": {"cream substitute"},
    "kefir": {"kefir"},
    "macaroni": {"macaroni", "pasta"},
    "nut": {"nut", "nuts"},
    "nuts": {"nuts", "nut"},
    "noodle": {"noodle", "noodles"},
    "noodles": {"noodle", "noodles"},
    "peanut butter": {"peanut butter", "nut butter"},
    "cheese food": {"cheese food"},
    "pickle": {"pickle", "pickles"},
    "pickles": {"pickle", "pickles"},
    "pretzel": {"pretzel", "pretzels"},
    "pretzels": {"pretzel", "pretzels"},
    "ravioli": {"ravioli"},
    "roll": {"roll"},
    "salad dressing": {"salad dressing", "dressing"},
    "seed": {"seed", "seeds"},
    "seeds": {"seed", "seeds"},
    "sweetener": {"sweetener", "sugar"},
    "sugar": {"sugar", "sweetener"},
    "tomato": {"tomato", "tomatoes"},
    "tomatoes": {"tomato", "tomatoes"},
    "topping": {"topping", "dessert topping"},
    "tortellini": {"tortellini"},
    "wonton": {"wonton"},
    "quinoa": {"quinoa"},
    "dessert topping": {"dessert topping", "topping"},
}


def head_norms_for_targets(target_heads: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for head in target_heads:
        n = norm_head(head)
        if not n:
            continue
        out.add(n)
        out.update(HEAD_ALIASES.get(n, set()))
    return out


def head_matches_targets(target_heads: Iterable[str], esha_head_value: str) -> bool:
    h = norm_head(esha_head_value)
    return bool(h and h in head_norms_for_targets(target_heads))


def _has_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def _has_token(tokens: set[str], *needles: str) -> bool:
    return any(needle in tokens for needle in needles)


def _normalized_milk_tokens(tokens: Iterable[str], text: str) -> set[str]:
    out = split_terms(" ".join(tokens)) | split_terms(text)
    if "soymilk" in out:
        out.update({"soy", "milk"})
    if "oatmilk" in out:
        out.update({"oat", "milk"})
    if "alm" in out or "almondmilk" in out:
        out.update({"almond", "milk"})
    if "coconutmilk" in out:
        out.update({"coconut", "milk"})
    if "buttermilk" in out:
        out.update({"butter", "milk"})
    return out


def is_nut_butter_product(title_tokens: set[str], text: str) -> bool:
    nut_terms = {
        "almond", "peanut", "cashew", "hazelnut", "sunflower", "pistachio",
        "walnut", "pecan", "nut", "nuts",
    }
    return bool((title_tokens & nut_terms) and (title_tokens & {"butter", "spread", "paste"})) or _has_any(
        text,
        ("peanut butter", "almond butter", "cashew butter", "sunflower butter", "nut butter"),
    )


FOOD_SALAD_COMPONENTS = {
    "potato", "potatoes", "chicken", "cobb", "seafood", "crab", "tuna",
    "egg", "eggs", "lettuce", "greens", "macaroni", "pasta", "coleslaw",
    "slaw", "ham", "turkey", "chef",
}


def is_food_salad_product(title_tokens: set[str], text: str) -> bool:
    if "salad" not in title_tokens and "salad" not in text:
        return False
    phrases = (
        "potato salad",
        "seafood salad",
        "chicken salad",
        "tuna salad",
        "egg salad",
        "macaroni salad",
        "pasta salad",
        "cobb",
        "coleslaw",
        "cole slaw",
    )
    return bool((title_tokens & FOOD_SALAD_COMPONENTS) or any(phrase in text for phrase in phrases))


def category_bucket(category: str) -> str | None:
    c = norm_text(category)
    if not c:
        return None
    if "pasta by shape" in c or c == "all noodles":
        return "dry_pasta"
    if "pasta dinners" in c:
        return "pasta_dinner"
    if "canned & bottled beans" in c:
        return "canned_bottled_beans"
    if "popcorn, peanuts" in c or "seeds & related snacks" in c:
        return "popcorn_nuts_seeds"
    if "butter & spread" in c:
        return "butter_spread"
    if "plant based milk" in c:
        return "plant_milk"
    if c == "milk" or "milk/milk substitutes" in c or "milk/cream" in c:
        return "milk_family"
    if "milk additives" in c or "cream substitutes" in c or "cream/cream substitutes" in c:
        return "milk_additives"
    if "salad dressing" in c or "mayonnaise" in c:
        return "salad_dressing"
    if "dips" in c or "salsa" in c:
        return "dip_salsa"
    if "pickles, olives, peppers & relishes" in c or "pickles olives peppers relishes" in c:
        return "pickles_relish"
    if "frozen fruit" in c or "fruit juice concentrates" in c:
        return "frozen_fruit"
    if "frozen dinners" in c or "entrees" in c or "prepared meals" in c or "ready-made combination meals" in c:
        return "prepared_meal"
    if "frozen pizza" in c or c == "pizza":
        return "pizza"
    if "prepared pasta & pizza sauces" in c or "pasta sauces" in c or "pizza sauces" in c:
        return "pasta_pizza_sauce"
    if "bread & muffin mixes" in c or "cake cookie" in c or "cupcake mixes" in c:
        return "baking_mix"
    if "bacon" in c or "sausages" in c or "ribs" in c:
        return "bacon_meat"
    if "seasoning" in c or "spices" in c or "salts" in c or "marinades" in c or "tenderizers" in c:
        return "seasoning"
    if "puddings" in c or "custards" in c:
        return "pudding"
    if "dessert toppings" in c:
        return "dessert_topping"
    if "ice cream" in c or "frozen yogurt" in c or "frozen dessert" in c or "gelato" in c:
        return "frozen_dessert"
    if c == "coffee":
        return "coffee"
    if c == "yogurt" or ("yogurt" in c and "frozen yogurt" not in c):
        return "yogurt"
    return None


def allowed_heads_for_category(
    category: str,
    *,
    title_tokens: Iterable[str] = (),
    product_description: str = "",
) -> tuple[str, set[str]] | tuple[None, set[str]]:
    bucket = category_bucket(category)
    tokens = set(title_tokens)
    text = f"{norm_text(product_description)} {norm_text(category)}"
    if bucket == "dry_pasta":
        allowed = {"pasta", "noodles", "macaroni"}
        if "ravioli" in tokens:
            allowed.add("ravioli")
        if "tortellini" in tokens:
            allowed.add("tortellini")
        if "quinoa" in tokens and "pasta" not in tokens:
            allowed.add("quinoa")
        return bucket, allowed
    if bucket == "pasta_dinner":
        return bucket, {"pasta dish", "meal", "dish", "pasta", "noodles", "macaroni"}
    if bucket == "canned_bottled_beans":
        allowed = {"beans", "baked beans", "refried beans", "pork and beans", "snap beans", "soybeans"}
        if "rice" in tokens or "rice" in text:
            allowed |= {"beans rice", "beans and rice"}
        return bucket, allowed
    if bucket == "popcorn_nuts_seeds":
        allowed = {"popcorn", "nuts", "nut", "seeds", "seed", "pretzels", "pretzel", "chips", "snack", "trail mix"}
        if is_nut_butter_product(tokens, text):
            allowed |= {"nut butter", "peanut butter"}
        return bucket, allowed
    if bucket == "butter_spread":
        allowed = {"butter", "butter substitute", "spread", "fruit spread", "margarine"}
        if is_nut_butter_product(tokens, text):
            allowed |= {"nut butter", "peanut butter"}
        if _has_token(tokens, "oil") or "cooking spray" in text:
            allowed.add("oil")
        return bucket, allowed
    if bucket == "plant_milk":
        return bucket, {"almond milk", "oat milk", "soy milk", "coconut milk", "cream substitute"}
    if bucket == "milk_family":
        milk_tokens = _normalized_milk_tokens(tokens, text)
        if "kefir" in milk_tokens:
            return bucket, {"kefir"}
        if "buttermilk" in milk_tokens:
            return bucket, {"buttermilk"}
        if "eggnog" in milk_tokens or "nog" in milk_tokens:
            return bucket, {"eggnog", "eggnog substitute"}
        if milk_tokens & {"soy", "almond", "oat", "coconut"}:
            return bucket, {"almond milk", "oat milk", "soy milk", "coconut milk", "cream substitute"}
        return bucket, {"milk", "milk shake", "drink"}
    if bucket == "milk_additives":
        return bucket, {"cream substitute", "cream", "coffee", "drink", "syrup", "sweetener", "glucose", "milk"}
    if bucket == "salad_dressing":
        return bucket, {"salad dressing", "dressing", "sauce"}
    if bucket == "dip_salsa":
        allowed = {"dip", "salsa", "hummus", "sauce"}
        if is_food_salad_product(tokens, text):
            allowed.add("salad")
        return bucket, allowed
    if bucket == "pickles_relish":
        allowed = {"pickles", "pickle", "olives", "olive", "pepper", "peppers", "chili pepper", "chili peppers", "relish"}
        if tokens & {"salad"}:
            allowed.add("salad")
        return bucket, allowed
    if bucket == "frozen_fruit":
        return bucket, {
            "fruit",
            "berries",
            "apple",
            "apples",
            "banana",
            "bananas",
            "orange",
            "oranges",
            "strawberry",
            "strawberries",
            "blueberry",
            "blueberries",
            "blackberry",
            "blackberries",
            "raspberry",
            "raspberries",
            "cherry",
            "cherries",
            "mango",
            "mangos",
            "mangoes",
            "pineapple",
            "pineapples",
            "peach",
            "peaches",
            "smoothie",
            "juice",
        }
    if bucket == "prepared_meal":
        allowed = {"meal", "dish"}
        if tokens & {"pasta", "noodle", "noodles", "spaghetti", "macaroni", "lasagna", "ravioli", "fettuccine"}:
            allowed.add("pasta dish")
        if ("mac" in tokens or "macaroni" in tokens) and "cheese" in tokens:
            allowed.add("macaroni cheese")
        if "quesadilla" in tokens:
            allowed.add("quesadilla")
        if ("pot" in tokens and "pie" in tokens) or "potpie" in tokens:
            allowed.add("pot pie")
        if "rice" in tokens:
            allowed.add("rice dish")
        if "corndog" in tokens or "corndogs" in tokens or ("corn" in tokens and "dog" in tokens):
            allowed.add("corn dog")
        if "pizza" in tokens:
            allowed.add("pizza")
        if "sandwich" in tokens or "sub" in tokens:
            allowed.add("sandwich")
        if "wrap" in tokens:
            allowed.add("wrap")
        if "burrito" in tokens:
            allowed.add("burrito")
        if tokens & {"vegetarian", "veggie", "meatless", "plant"}:
            allowed.add("vegetarian meat")
        if ("mashed" in tokens or "mash" in tokens) and (tokens & {"potato", "potatoes"}):
            allowed.add("mashed potatoes")
        return bucket, allowed
    if bucket == "pizza":
        return bucket, {"pizza"}
    if bucket == "pasta_pizza_sauce":
        return bucket, {"sauce", "tomato sauce", "tomato paste", "ketchup", "salad dressing", "dressing"}
    if bucket == "baking_mix":
        allowed = {"baking mix", "brownie", "cake", "cookie", "cookies", "muffin", "pancakes", "waffles", "bread", "roll"}
        if ("mashed" in tokens or "mash" in tokens) and (tokens & {"potato", "potatoes"}):
            allowed = {"mashed potatoes"}
        return bucket, allowed
    if bucket == "dessert_topping":
        return bucket, {"dessert topping", "topping", "sauce", "syrup"}
    if bucket == "bacon_meat":
        allowed = {"bacon", "pork", "sausage"}
        if "turkey" in tokens:
            allowed.add("turkey")
        if "chicken" in tokens:
            allowed.add("chicken")
        return bucket, allowed
    if bucket == "seasoning":
        allowed = {"seasoning", "spice", "sauce", "salt", "sweetener", "sugar", "base"}
        if "bouillon" in tokens or "broth" in tokens or "stock" in tokens or "base" in tokens:
            allowed |= {"bouillon", "broth", "base"}
        return bucket, allowed
    if bucket == "pudding":
        return bucket, {"pudding", "custard", "dessert"}
    if bucket == "frozen_dessert":
        return bucket, {"ice cream", "yogurt", "frozen yogurt", "pudding", "dessert"}
    if bucket == "coffee":
        return bucket, {"coffee", "drink"}
    if bucket == "yogurt":
        allowed = {"yogurt", "parfait", "smoothie", "drink"}
        if "kefir" in tokens or "kefir" in text:
            allowed.add("kefir")
        return bucket, allowed
    return None, set()


def category_allows_head(
    *,
    category: str,
    product_description: str,
    title_tokens: Iterable[str],
    candidate_head: str,
) -> tuple[bool, str]:
    bucket, allowed = allowed_heads_for_category(
        category,
        title_tokens=title_tokens,
        product_description=product_description,
    )
    if not bucket:
        return True, ""
    h = norm_head(candidate_head)
    if h in allowed:
        return True, ""
    return False, f"category_head_mismatch:{bucket}:{candidate_head}"


def narrow_head_requires_title_support(candidate_head: str, title_tokens: Iterable[str], text: str = "") -> str | None:
    h = norm_head(candidate_head)
    tokens = set(title_tokens)
    body = norm_text(text)
    requirements: dict[str, set[str]] = {
        "pasta dish": {"pasta", "noodle", "noodles", "spaghetti", "macaroni", "lasagna", "ravioli", "fettuccine"},
        "pizza": {"pizza"},
        "sandwich": {"sandwich", "sub", "hoagie"},
        "wrap": {"wrap"},
        "burrito": {"burrito"},
        "ravioli": {"ravioli"},
        "tortellini": {"tortellini"},
        "vegetarian meat": {"vegetarian", "veggie", "meatless", "plant", "burger", "patty"},
        "doughnut": {"doughnut", "doughnuts", "donut", "donuts"},
        "brownie": {"brownie", "brownies"},
        "cream cheese": {"cream", "cheese"},
        "kefir": {"kefir"},
        "roll": {"roll", "rolls", "crescent", "dinner", "sandwich", "sourdough"},
        "wonton": {"wonton"},
    }
    needed = requirements.get(h)
    if needed and not (tokens & needed):
        return f"narrow_head_without_title_support:{candidate_head}"
    if h == "mashed potatoes" and not (("mashed" in tokens or "mash" in tokens) and (tokens & {"potato", "potatoes"})):
        return "narrow_head_without_title_support:Mashed Potatoes"
    if h == "popcorn" and "popcorn" not in tokens and "popcorn" not in body:
        return "narrow_head_without_title_support:Popcorn"
    if h == "coleslaw" and not ("coleslaw" in tokens or ("cole" in tokens and "slaw" in tokens)):
        return "narrow_head_without_title_support:Coleslaw"
    return None
