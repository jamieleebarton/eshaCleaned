from __future__ import annotations

import re


BULK_CASE_RE = re.compile(
    r"("
    r"\(\s*\d+\s*pack\s*\)|"
    r"\bpack\s+of\s+\d+\b|"
    r"\b\d+\s*pack\b|"
    r"\b\d+\s*pk\b|"
    r"\bprice\s*/\s*case\b|"
    r"\bprice\s*/\s*pack\b.*\bper\s+case\b|"
    r"\bcase\s+of\b|"
    r"\b\d+\s*(?:packs?|pk|ct|count)?\s*/\s*case\b|"
    r"\b\d+\s+per\s+case\b|"
    r"--\s*\d+\s+case\b|"
    r"\b\d+\s+case\b|"
    r"\bper\s+case\b|"
    r"\bpacks?\s+per\s+case\b|"
    r"\bcase\s+pack\b|"
    r"\bcasepack\b|"
    r"\bdisplay\s+ready\s+carton\b|"
    r"\bbundle\s+of\s+\d+\s+cartons?\b|"
    r"\b\d+\s*/\s*carton\b|"
    r"\b\d+\s+cans?\s*/\s*carton\b|"
    r"\b\d+\s+boxes\s*/\s*carton\b|"
    r"\bbox(?:es)?\s*/\s*carton\b"
    r")",
    re.I,
)

HALF_AND_HALF_BEVERAGE_RE = re.compile(
    r"\b(arnold\s+palmer|iced\s+(?:green\s+)?tea|lemonade|drink\s+mix|hydration|water\s+bottles?)\b",
    re.I,
)
LIMITED_SALE_RE = re.compile(r"\blimit\s+\d+\s+at\s+sale\s+price\b", re.I)

SALT_NON_RETAIL_RE = re.compile(
    r"\b("
    r"softener|soft\s+water|pellets?|cooling\s+salt|ice\s+cream\s+salt|"
    r"no\s+salt\s+added|less\s+salt|lite\s+salt|low\s+sodium|alkaline|"
    r"canning|pickling|seasoned|kosher|sea\s+salt|himalayan|pink\s+salt|"
    r"smoked|truffle|coarse|fine|flaky|flake|fleur\s+de\s+sel|"
    r"epsom|lavender|bath|relax|calamari|old\s+salt|season|bacon|"
    r"luncheon\s+meat|green\s+beans?|kidney\s+beans?|pinto\s+beans?|"
    r"chickpea|seaweed|snack|papad|wafer|dessert\s+salt"
    r")\b",
    re.I,
)
EGG_NON_SHELL_RE = re.compile(
    r"\b("
    r"feed|layer|pellet|flock|waterfowl|duck|goose|"
    r"noodle|rolls?|biscuit|sandwich|sausage|soup|beater|substitute|"
    r"bite|bites|salad|waffle|scramble"
    r")\b",
    re.I,
)
BLACK_PEPPER_NOISE_RE = re.compile(
    r"\b("
    r"salt|sauce|chili|marinade|rub|seasoning|parmesan|"
    r"lemon|garlic|lime|onion|cajun|steak|citrus|blend|medley|"
    r"sausage|papad|tofu|capsules?|extract|variety|pack|pasta|"
    r"pepper\s+sauce|hot\s+chili"
    r")\b",
    re.I,
)
ONION_NOISE_RE = re.compile(
    r"\b("
    r"hushpuppy|ring|rings|fried|minced|powder|dip|mix|soup|"
    r"martini|silverskin|pickled|red\s+onions?|diced|chopped|"
    r"seasoning|bloom|bloomin|chip|crispy|ringer|flavor|herring|pierog|moonions"
    r")\b",
    re.I,
)
GREEN_ONION_NOISE_RE = re.compile(
    r"\b("
    r"dip|mix|dried|dehydrated|freeze\s*dried|spice|minced|powder|"
    r"seasoning|packet|can\b"
    r")\b",
    re.I,
)
BUTTER_NOISE_RE = re.compile(
    r"\b("
    r"syrup|syurp|pickle|pickles|biscuit|biscuits|sauce|glaze|"
    r"bread\s*&?\s*butter|bread\s+and\s+butter|"
    r"powder|finishing|truffle|steakhouse|caramel"
    r")\b",
    re.I,
)
CHEDDAR_NOISE_RE = re.compile(
    r"\b("
    r"curds?|snack|easy\s+cheese|sauce|dip|cracker|crackers|"
    r"mac\b|macaroni|breaded|popcorn|soup|burrito|pizza|meal|dinner"
    r")\b",
    re.I,
)
PARMESAN_NOISE_RE = re.compile(
    r"\b("
    r"alfredo|sauce|meal\s+mix|ravioli|pasta|butter\s+and\s+parmesan"
    r")\b",
    re.I,
)
TOMATO_NOISE_RE = re.compile(
    r"\b("
    r"clamato|cocktail|juice|soup|sauce|passata|paste|ketchup|"
    r"salsa|bruschetta|marinara|puree|diced|peeled|whole|canned|"
    r"crushed|stewed|habanero|green\s+chile|fire\s+roasted|"
    r"chopped|chunky|cut|polpa|style|green|breaded"
    r")\b",
    re.I,
)
OLIVE_OIL_NOISE_RE = re.compile(
    r"\b("
    r"pesto|sauce|dressing|spray|truffle|garlic|marinade|mayo|mayonnaise|"
    r"vinaigrette|butter|dip|paste|loaf|bread"
    r")\b",
    re.I,
)
SUGAR_NOISE_RE = re.compile(
    r"\b("
    r"tonic|energy\s+drink|mixer|cocktail|"
    r"gum|candy|cookie|snack|protein|yogurt"
    r")\b",
    re.I,
)
SUGAR_PHRASE_NOISE_RE = re.compile(r"\bzero\s+sugar\b", re.I)
FLOUR_NOISE_RE = re.compile(
    r"\b("
    r"taquito|hair|mousse|loaf|sardine|sardines|bread|mix|starter|"
    r"masa|besan|atta|cassava|lentil|bean|almond|coconut|oat|corn|"
    r"wheat|self\s*rising|whole\s+wheat|cake|paleo|arrowroot|tigernut"
    r")\b",
    re.I,
)
POTATO_NOISE_RE = re.compile(
    r"\b("
    r"chip|chips|crisps?|snack|snacks?|skins?|burrito|fries|fries|"
    r"mashed|loaded|cheddar|jalape[nñ]o|cheese|seasoned|hash|gratin|wedges"
    r")\b",
    re.I,
)


def is_bulk_case_product(name: str) -> bool:
    return bool(BULK_CASE_RE.search(name or ""))


def is_retail_price_reject(name: str, canonical: str = "") -> bool:
    lower_name = name or ""
    canonical_key = canonical.strip().lower()
    if is_bulk_case_product(name):
        return True
    if canonical_key in {"half and half", "half-and-half", "half & half"}:
        return bool(HALF_AND_HALF_BEVERAGE_RE.search(lower_name))
    if canonical_key == "whole ham":
        return bool(LIMITED_SALE_RE.search(lower_name))
    if canonical_key == "salt":
        return bool(SALT_NON_RETAIL_RE.search(lower_name))
    if canonical_key == "egg":
        return bool(EGG_NON_SHELL_RE.search(lower_name))
    if canonical_key in {"black pepper", "ground black pepper"}:
        return bool(BLACK_PEPPER_NOISE_RE.search(lower_name))
    if canonical_key == "onion":
        return bool(ONION_NOISE_RE.search(lower_name))
    if canonical_key == "green onion":
        return bool(GREEN_ONION_NOISE_RE.search(lower_name))
    if canonical_key in {"butter", "salted butter", "unsalted butter"}:
        return bool(BUTTER_NOISE_RE.search(lower_name))
    if canonical_key == "cheddar cheese":
        return bool(CHEDDAR_NOISE_RE.search(lower_name))
    if canonical_key == "parmesan cheese":
        return bool(PARMESAN_NOISE_RE.search(lower_name))
    if canonical_key == "tomato":
        return bool(TOMATO_NOISE_RE.search(lower_name))
    if canonical_key in {"olive oil", "extra virgin olive oil"}:
        return bool(OLIVE_OIL_NOISE_RE.search(lower_name))
    if canonical_key == "sugar":
        return bool(SUGAR_NOISE_RE.search(lower_name) or SUGAR_PHRASE_NOISE_RE.search(lower_name))
    if canonical_key in {"flour", "all purpose flour", "all-purpose flour"}:
        return bool(FLOUR_NOISE_RE.search(lower_name))
    if canonical_key == "potato":
        return bool(POTATO_NOISE_RE.search(lower_name))
    return False


def passes_retail_identity(name: str, canonical: str = "", category: str = "") -> bool:
    canonical_key = canonical.strip().lower()
    lower_name = (name or "").lower()
    lower_category = (category or "").lower()
    has_category = bool(lower_category.strip())
    if not canonical_key:
        return True
    if canonical_key == "salt":
        return "salt" in lower_name and not re.search(r"\b(celery|season(?:ed)?|onion|garlic|pepper)\b", lower_name)
    if canonical_key in {"black pepper", "ground black pepper"}:
        if "pepper" not in lower_name:
            return False
        if "black" not in lower_name and "peppercorn" not in lower_name:
            return False
        return True if not has_category else any(term in lower_category for term in ("herb", "spice", "seasoning", "marinade", "tenderizer"))
    if canonical_key == "egg":
        if "egg" not in lower_name and "eggs" not in lower_name:
            return False
        return True if not has_category else "egg" in lower_category
    if canonical_key == "onion":
        if "onion" not in lower_name:
            return False
        if re.search(r"\b(red|scallion|green)\b", lower_name):
            return False
        if has_category and any(term in lower_category for term in ("pickles", "canned", "french fries", "frozen", "deli")):
            return False
        return True if not has_category else any(term in lower_category for term in ("produce", "vegetable", "fruit", "onion"))
    if canonical_key == "milk":
        if "milk" not in lower_name:
            return False
        if re.search(r"\b(chocolate|strawberry|vanilla|almond|oat|soy|coconut|rice|shake|ice\s+cream|dessert|klondike|cookies?|bar|bars)\b", lower_name):
            return False
        return True if not has_category else any(term in lower_category for term in ("milk", "dairy"))
    if canonical_key == "potato":
        if "potato" not in lower_name and "potatoes" not in lower_name:
            return False
        if POTATO_NOISE_RE.search(lower_name):
            return False
        return True if not has_category else any(term in lower_category for term in ("produce", "vegetable", "potato"))
    if canonical_key in {"butter", "salted butter", "unsalted butter"}:
        if "butter" not in lower_name and "beurre" not in lower_name:
            return False
        if re.search(r"\bsyu?rp\b|\bsyrup\b", lower_name):
            return False
        return True if not has_category else any(term in lower_category for term in ("butter", "spread", "dairy"))
    if canonical_key == "mayonnaise":
        if "mayonnaise" not in lower_name and "mayo" not in lower_name:
            return False
        reject = re.compile(
            r"\b(chipotle|mango|sundried|campfire|relish|ranch|sriracha|wasabi|"
            r"habanero|jalapeno|serrano|pesto|truffle|ketchup|spicy|aioli|"
            r"avocado(?:\s+oil)?|light|lite|low[\s-]?fat|lowfat|fat[\s-]?free|"
            r"fatfree|reduced|olive[\s-]?oil|canola|soybean[\s-]?oil|"
            r"vegan|plant[\s-]?based|plantbased|non[\s-]?dairy|imitation)\b",
            re.I,
        )
        if reject.search(lower_name):
            return False
        return True if not has_category else any(term in lower_category for term in ("condiment", "sauce", "dressing", "mayo"))
    if canonical_key == "cheddar cheese":
        if "cheddar" not in lower_name or "cheese" not in lower_name:
            return False
        reject = re.compile(
            r"\b(jack|monterey|colby|swiss|parmesan|parmigiano|romano|"
            r"mozzarella|provolone|gouda|feta|brie|ricotta|asiago|muenster|"
            r"gruyere|cashew|vegan|plant[\s-]?based|plantbased|non[\s-]?dairy|"
            r"nondairy|imitation|blend|trio|tray|platter|assortment)\b",
            re.I,
        )
        if reject.search(lower_name):
            return False
        return True if not has_category else "cheese" in lower_category
    if canonical_key == "sugar":
        if "sugar" not in lower_name:
            return False
        return True if not has_category else any(term in lower_category for term in ("sweetener", "sugar", "baking"))
    if canonical_key in {"flour", "all purpose flour", "all-purpose flour"}:
        if "flour" not in lower_name:
            return False
        if canonical_key in {"all purpose flour", "all-purpose flour"} and "all purpose" not in lower_name and "all-purpose" not in lower_name:
            return False
        return True if not has_category else ("flour" in lower_category or "corn meal" in lower_category)
    if canonical_key == "olive oil":
        if "olive oil" not in lower_name:
            return False
        return True if not has_category else "oil" in lower_category
    if canonical_key == "tomato":
        if "tomato" not in lower_name:
            return False
        if has_category and any(term in lower_category for term in ("canned", "frozen")):
            return False
        return True if not has_category else any(term in lower_category for term in ("produce", "vegetable", "fruit", "tomato"))
    if canonical_key == "extra virgin olive oil":
        if "olive oil" not in lower_name:
            return False
        if "extra virgin" not in lower_name:
            return False
        return True if not has_category else "oil" in lower_category
    return True
