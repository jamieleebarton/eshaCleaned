from __future__ import annotations

from .contract_base import ContractFn, ContractSpec, MatchDecision, ProductFacts, accept, match_spec, reject

# ── Category tuples ─────────────────────────────────────────────
BUTTER_CATEGORIES = (
    "butter",
    "margarine",
    "spread",
    "shortening",
    "oil",
    "baking",
    "cooking",
    "popcorn",
    "seasoning",
)

PREPARED_CATEGORIES = (
    "bread",
    "bun",
    "roll",
    "croissant",
    "pastry",
    "frozen",
    "prepared",
    "meal",
    "dinner",
    "entree",
    "side",
    "sauce",
    "breakfast",
    "snack",
    "potato",
    "vegetable",
    "pasta",
    "noodle",
    "rice",
    "pizza",
    "sandwich",
    "tortilla",
    "muffin",
    "english muffin",
    "danish",
    "sweet roll",
    "hash brown",
    "grit",
    "frosting",
    "crouton",
    "fish",
    "seafood",
    "shellfish",
    "salmon",
    "tuna",
    "chicken",
    "turkey",
    "corn",
    "lobster",
    "mushroom",
    "veal",
    "gnocchi",
    "dumpling",
    "pretzel",
    "pancake",
    "french toast",
    "gratin",
    "scalloped",
)

PICKLE_CATEGORIES = (
    "pickle",
    "olive",
    "relish",
    "condiment",
)

PRODUCE_CATEGORIES = (
    "produce",
    "vegetable",
    "fruit",
    "pre packaged",
    "salad",
    "lettuce",
)

BAKING_CATEGORIES = (
    "baking",
    "chip",
    "chocolate",
    "cookie",
    "cracker",
    "cereal",
    "snack",
    "cake",
    "mix",
)

NUT_BUTTER_CATEGORIES = (
    "nut butter",
    "peanut butter",
    "seed butter",
    "nut",
    "seed",
    "spread",
)

SPRAY_CATEGORIES = (
    "cooking spray",
    "oil",
    "aerosol",
    "spray",
)

FLAVORED_OR_NONSTANDARD_BUTTER_TERMS = (
    "ball",
    "balls",
    "buffalo",
    "basil",
    "black",
    "brown",
    "canola",
    "caramel",
    "chili",
    "chipotle",
    "chive",
    "cranberry",
    "dill",
    "everything",
    "flavor",
    "flavored",
    "goat",
    "jalapeno",
    "lemon",
    "lime",
    "maple",
    "olive",
    "onion",
    "parmesan",
    "pumpkin",
    "sheep",
    "spread",
    "spreadable",
    "steakhouse",
    "sugar",
    "tomato",
    "toffee",
    "truffle",
    "vegetable",
)

# ── Factory helpers ─────────────────────────────────────────────

def make_butter_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
    allowed_categories: tuple[str, ...] = BUTTER_CATEGORIES,
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if product.category_has_any("nut", "seed", "peanut"):
            return reject(f"{esha_code} nut/seed butter category")
        if not product.category_has_any(*allowed_categories):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any("butter", "ghee", "clarified"):
            return reject(f"{esha_code} missing butter/ghee cue")
        missing = [t for t in required_terms if not product.has_any(t)]
        if missing:
            return reject(f"{esha_code} missing required term(s): " + "|".join(missing))
        excluded = [t for t in exclude_terms if product.has_any(t) or product.ingredients_have_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        nonstandard = [
            t for t in FLAVORED_OR_NONSTANDARD_BUTTER_TERMS
            if t not in required_terms and (product.has_any(t) or product.ingredients_have_any(t))
        ]
        if nonstandard:
            return reject(f"{esha_code} nonstandard butter term(s): " + "|".join(nonstandard))
        return accept(f"{esha_code} reviewed butter contract accepted")
    return contract

def make_ghee_contract(
    esha_code: str,
    esha_description: str,
    exclude_terms: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if product.category_has_any("nut", "seed", "peanut"):
            return reject(f"{esha_code} nut/seed butter category")
        if not product.category_has_any(*BUTTER_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any("ghee", "clarified"):
            return reject(f"{esha_code} missing ghee/clarified cue")
        excluded = [t for t in exclude_terms if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        nonstandard = [t for t in FLAVORED_OR_NONSTANDARD_BUTTER_TERMS if product.has_any(t)]
        if nonstandard:
            return reject(f"{esha_code} nonstandard butter term(s): " + "|".join(nonstandard))
        return accept(f"{esha_code} reviewed ghee contract accepted")
    return contract

def make_prepared_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = ("butter", "ghee", "clarified", "margarine", "shortening"),
    allowed_categories: tuple[str, ...] = PREPARED_CATEGORIES,
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*allowed_categories):
            return reject(f"{esha_code} category mismatch")
        missing = [t for t in required_terms if not product.has_any(t)]
        if missing:
            return reject(f"{esha_code} missing required term(s): " + "|".join(missing))
        excluded = [t for t in exclude_terms if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed prepared dish contract accepted")
    return contract

def make_non_butter_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = ("butter", "ghee", "clarified"),
    allowed_categories: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if allowed_categories and not product.category_has_any(*allowed_categories):
            return reject(f"{esha_code} category mismatch")
        missing = [t for t in required_terms if not product.has_any(t)]
        if missing:
            return reject(f"{esha_code} missing required term(s): " + "|".join(missing))
        excluded = [t for t in exclude_terms if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed non-butter contract accepted")
    return contract

# ── Contract assignments ────────────────────────────────────────

CONTRACTS: dict[str, ContractFn] = {}

CONTRACTS["25765"] = make_butter_contract("25765", "Butter", (), ("unsalted", "no salt", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["8000"] = make_butter_contract("8000", "Butter, salted", (), ("unsalted", "no salt", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33826"] = make_butter_contract("33826", "Butter, salted, But-R-Cups, 5 gram, FS", (), ("unsalted", "no salt", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33825"] = make_butter_contract("33825", "Butter, salted, But-R-Cups, 6.3 gram, FS", (), ("unsalted", "no salt", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33817"] = make_butter_contract("33817", "Butter, salted, Continentals, FS", (), ("unsalted", "no salt", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33812"] = make_butter_contract("33812", "Butter, salted, grade AA, FS", (), ("unsalted", "no salt", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33819"] = make_butter_contract("33819", "Butter, salted, grade AA, prints, FS", (), ("unsalted", "no salt", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33813"] = make_butter_contract("33813", "Butter, salted, grade B, FS", (), ("unsalted", "no salt", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["8735"] = make_butter_contract("8735", "Butter, salted, sweet cream", ("sweet", "cream",), ("unsalted", "no salt", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["8791"] = make_butter_contract("8791", "Butter, sweet cream, salted", ("sweet", "cream",), ("unsalted", "no salt", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["8025"] = make_butter_contract("8025", "Butter, unsalted", ("unsalted",), ("salted", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33818"] = make_butter_contract("33818", "Butter, unsalted, Continentals, FS", ("unsalted",), ("salted", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["44951"] = make_butter_contract("44951", "Butter, unsalted, cultured", ("unsalted", "cultured",), ("salted", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33814"] = make_butter_contract("33814", "Butter, unsalted, grade AA, FS", ("unsalted",), ("salted", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33820"] = make_butter_contract("33820", "Butter, unsalted, grade AA, prints, FS", ("unsalted",), ("salted", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["8734"] = make_butter_contract("8734", "Butter, unsalted, sweet cream", ("unsalted", "sweet", "cream",), ("salted", "whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["8142"] = make_butter_contract("8142", "Butter, salted, whipped", ("whipped", "salted",), ("light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["8732"] = make_butter_contract("8732", "Butter, unsalted, whipped", ("whipped", "unsalted",), ("light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["8733"] = make_butter_contract("8733", "Butter, whipped", ("whipped",), ("light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["8794"] = make_butter_contract("8794", "Butter, whipped, sweet cream, salted", ("whipped", "salted", "sweet", "cream",), ("light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["8795"] = make_butter_contract("8795", "Butter, whipped, sweet cream, light, salted", ("whipped", "salted", "sweet", "cream",), ("light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["8796"] = make_butter_contract("8796", "Butter, whipped, sweet cream, unsalted", ("whipped", "unsalted", "sweet", "cream",), ("light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33822"] = make_butter_contract("33822", "Butter, salted, whipped, But-R-Cups, 10 gram, FS", ("whipped", "salted",), ("light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33824"] = make_butter_contract("33824", "Butter, salted, whipped, But-R-Cups, 5 gram, FS", ("whipped", "salted",), ("light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33827"] = make_butter_contract("33827", "Butter, salted, whipped, But-R-Cups, 720/5 gram, FS", ("whipped", "salted",), ("light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33823"] = make_butter_contract("33823", "Butter, salted, whipped, tub, FS", ("whipped", "salted",), ("light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["44469"] = make_butter_contract("44469", "Butter, light, salted", ("light", "salted",), ("whipped", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["44470"] = make_butter_contract("44470", "Butter, light, unsalted", ("light", "unsalted",), ("whipped", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["8792"] = make_butter_contract("8792", "Butter, sweet cream, light, salted", ("light", "salted", "sweet", "cream",), ("whipped", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["44964"] = make_butter_contract("44964", "Butter, soft, light, with canola oil", ("light", "canola",), ("whipped", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["33816"] = make_butter_contract("33816", "Butter, light salt, Continentals, FS", ("light",), ("whipped", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["20600"] = make_butter_contract("20600", "Butter, sweet cream, unsalted", ("sweet", "cream", "unsalted",), ("whipped", "light", "honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["51155"] = make_ghee_contract("51155", "Butter, clarified", ("honey", "garlic", "roasted", "popcorn", "seafood", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["51157"] = make_ghee_contract("51157", "Butter, Ghee", ("honey", "garlic", "roasted", "popcorn", "seafood", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["51159"] = make_ghee_contract("51159", "Butter, Ghee, clarified", ("honey", "garlic", "roasted", "popcorn", "seafood", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["33815"] = make_ghee_contract("33815", "Butter, clarified, FS", ("honey", "garlic", "roasted", "popcorn", "seafood", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["33821"] = make_ghee_contract("33821", "Butter, clarified, tub, FS", ("honey", "garlic", "roasted", "popcorn", "seafood", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["8031"] = make_ghee_contract("8031", "Oil, butter, anhydrous", ("honey", "garlic", "roasted", "popcorn", "seafood", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["8797"] = make_butter_contract("8797", "Butter, honey", ("honey",), ("garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["8798"] = make_butter_contract("8798", "Butter, roasted garlic", ("garlic",), ("honey", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["51156"] = make_butter_contract("51156", "Butter, popcorn", ("popcorn",), ("honey", "garlic", "roasted", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["51158"] = make_butter_contract("51158", "Butter, seafood", ("seafood",), ("honey", "garlic", "roasted", "popcorn", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["44965"] = make_butter_contract("44965", "Butter, soft, sweet cream, with canola oil", ("soft", "sweet", "cream", "canola",), ("honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["26800"] = make_butter_contract("26800", "Butter, soft, with olive oil", ("soft", "olive",), ("honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "blend", "margarine", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos", "honey", "garlic", "roasted", "popcorn", "seafood", "herb", "cinnamon", "clarified", "ghee",))
CONTRACTS["44709"] = make_butter_contract("44709", "butter and margarine, blend, 80%, unsalted, stick", ("blend", "margarine",), ("honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "cookie", "nut", "peanut", "almond", "cashew", "soy", "coconut", "apple", "fruit",))
CONTRACTS["33828"] = make_butter_contract("33828", "butter and margarine, clarified blend, with vegetable oil, FS", ("blend", "margarine", "clarified",), ("honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "cookie", "nut", "peanut", "almond", "cashew", "soy", "coconut", "apple", "fruit",))
CONTRACTS["40889"] = make_butter_contract("40889", "Spread, SunGlow, butter blend", ("spread", "blend",), ("honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "cookie", "nut", "peanut", "almond", "cashew", "soy", "coconut", "apple", "fruit",))
CONTRACTS["35282"] = make_butter_contract("35282", "Spread, butter blend, regular, with omega 3, stick", ("spread", "blend",), ("honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "cookie", "nut", "peanut", "almond", "cashew", "soy", "coconut", "apple", "fruit",))
CONTRACTS["35281"] = make_butter_contract("35281", "Spread, butter blend, with omega 3, with o salt, stick", ("spread", "blend",), ("honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "cookie", "nut", "peanut", "almond", "cashew", "soy", "coconut", "apple", "fruit",))
CONTRACTS["44721"] = make_butter_contract("44721", "Spread, vegetable oil & butter, reduced calorie", ("spread", "vegetable",), ("honey", "garlic", "roasted", "popcorn", "seafood", "clarified", "ghee", "substitute", "cookie", "nut", "peanut", "almond", "cashew", "soy", "coconut", "apple", "fruit",))
CONTRACTS["36687"] = make_butter_contract("36687", "Shortening, Move Over Butter, soy cottonseed hydrogenated soy, FS", ("shortening",), ("butter", "ghee", "clarified", "margarine", "blend", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["36688"] = make_butter_contract("36688", "Shortening, Move Over Butter, sodium free, FS", ("shortening",), ("butter", "ghee", "clarified", "margarine", "blend", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["90987"] = make_butter_contract("90987", "Shortening, vegetable, butter flavor", ("shortening",), ("butter", "ghee", "clarified", "margarine", "blend", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["397"] = make_butter_contract("397", "Butter Substitute, culinary cream, vegetarian, 730, FS", ("substitute", "culinary",), ("butter", "ghee", "clarified", "margarine", "blend", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["44466"] = make_butter_contract("44466", "Butter Substitute, low fat, powder", ("substitute", "powder",), ("butter", "ghee", "clarified", "margarine", "blend", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["44980"] = make_butter_contract("44980", "Butter Substitute, natural, fat free, sprinkles", ("substitute", "sprinkle",), ("butter", "ghee", "clarified", "margarine", "blend", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["90961"] = make_butter_contract("90961", "Butter Substitute, Veggie, plain, soy, vegetarian", ("substitute", "veggie", "soy",), ("butter", "ghee", "clarified", "margarine", "blend", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["90962"] = make_butter_contract("90962", "Butter Substitute, Veggie, honey butter, soy, vegetarian", ("substitute", "veggie", "honey", "soy",), ("butter", "ghee", "clarified", "margarine", "blend", "shortening", "cookie", "nut", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",))
CONTRACTS["49524"] = make_non_butter_contract("49524", "Spread, cookie butter, speculoos", ("cookie", "speculoo",), ("butter", "ghee", "clarified", "margarine", "shortening", "nut", "peanut", "almond", "peanut", "almond", "cashew", "hazelnut", "pecan", "walnut", "pistachio", "macadamia", "brazil", "coconut", "soy", "soynut", "sunflower", "sesame", "pumpkin", "flax", "chia", "hemp", "poppy", "pine", "nut", "seed", "apple", "cookie", "fruit", "speculoo", "speculoos",), PREPARED_CATEGORIES)
CONTRACTS["36155"] = make_prepared_contract("36155", "Bread, rye, toasted, with butter", ("bread", "rye",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["36159"] = make_prepared_contract("36159", "Bread, wheat, toasted, with butter", ("bread", "wheat",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["36161"] = make_prepared_contract("36161", "Bread, white, toasted, with butter", ("bread", "white",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["42064"] = make_prepared_contract("42064", "English Muffin, with butter, fast food", ("english", "muffin",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["45122"] = make_prepared_contract("45122", "Pancakes, with butter & syrup, fast food", ("pancake",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["42353"] = make_prepared_contract("42353", "French Toast, with butter, fast food", ("french", "toast",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["51968"] = make_prepared_contract("51968", "French Toast, with butter & cinnamon sugar", ("french", "toast",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["54675"] = make_prepared_contract("54675", "Breakfast Sandwich, chicken strip, honey butter, with biscuit", ("breakfast", "sandwich", "chicken", "biscuit",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["41009"] = make_prepared_contract("41009", "Sandwich, pretzel pocket, turkey & cheddar, with butter", ("sandwich", "pretzel",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["53960"] = make_prepared_contract("53960", "Croissant, all butter, frozen, 2 ounce, FS", ("croissant",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["53961"] = make_prepared_contract("53961", "Croissant, all butter, sliced, frozen, 3 ounce, FS", ("croissant",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["25744"] = make_prepared_contract("25744", "Croissant, butter", ("croissant",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["18982"] = make_prepared_contract("18982", "Danish, gooey butter", ("danish",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["92599"] = make_prepared_contract("92599", "Sweet Roll, butter swirl, with frosting, frozen dough", ("sweet", "roll",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["92600"] = make_prepared_contract("92600", "Sweet Roll, butter swirl, with o frosting, frozen dough", ("sweet", "roll",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["5276"] = make_prepared_contract("5276", "Casserole, potato au gratin, prepared from dry with water milk butter", ("casserole", "potato", "gratin",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["5786"] = make_prepared_contract("5786", "Casserole, potatoes au gratin, prepared from recipe with butter", ("casserole", "potato", "gratin",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["57484"] = make_prepared_contract("57484", "Casserole, scalloped potatoes, prepared from dry with whole milk &butter", ("casserole", "scalloped", "potato",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["5785"] = make_prepared_contract("5785", "Casserole, scalloped potatoes, prepared from recipe with butter", ("casserole", "scalloped", "potato",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["35985"] = make_prepared_contract("35985", "Chicken, grilled, with garlic butter & oil", ("chicken", "grilled",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["52498"] = make_prepared_contract("52498", "Chicken, grilled, with garlic butter & oil, senior", ("chicken", "grilled",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["35986"] = make_prepared_contract("35986", "Fish, salmon, grilled, with garlic butter & oil", ("salmon", "grilled",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["19407"] = make_prepared_contract("19407", "Dish, lobster, with butter sauce", ("lobster",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["11904"] = make_prepared_contract("11904", "Dish, veal, with butter sauce", ("veal",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["54436"] = make_prepared_contract("54436", "Turkey, breast, butter, foil wrapped, raw, frozen, FS", ("turkey", "breast",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["41314"] = make_prepared_contract("41314", "Corn, cobbette, with butter flavored oil", ("corn", "cobbette",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["91381"] = make_prepared_contract("91381", "Corn, cobbette, with o butter", ("corn", "cobbette",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["6175"] = make_prepared_contract("6175", "Dish, corn, cob, with butter, fast food", ("corn", "cob",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["18211"] = make_prepared_contract("18211", "Dish, corn, with butter sauce, frozen", ("corn",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["36025"] = make_prepared_contract("36025", "Dish, corn, with herb butter sauce", ("corn", "herb",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["1809"] = make_prepared_contract("1809", "Dish, yellow corn, Simply Sweet, with butter sauce, frozen, FS", ("corn",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["6360"] = make_prepared_contract("6360", "Vegetable Dish, baby sweet peas, with butter sce, low fat, frozen", ("pea",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["6349"] = make_prepared_contract("6349", "Vegetable Dish, broccoli spears, with butter sce, low fat, frozen", ("broccoli",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["16565"] = make_prepared_contract("16565", "Vegetable Dish, corn & peas, with herb butter sauce, frozen", ("corn", "pea", "herb",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["6347"] = make_prepared_contract("6347", "Vegetable Dish, cut leaf spinach, with butter sce, low fat, frozen", ("spinach",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["6342"] = make_prepared_contract("6342", "Vegetable Dish, white shoepeg corn, with butter sce, lowfat,frozen", ("corn",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["36093"] = make_prepared_contract("36093", "Dish, vegetables, garden, with herb butter sauce", ("vegetable", "herb",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["42800"] = make_prepared_contract("42800", "Dish, mushrooms, butter breaded, frozen, FS", ("mushroom",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["49379"] = make_prepared_contract("49379", "Dumpling, gnocchi, sweet potato, with butter & sage, frozen", ("gnocchi", "sweet", "potato",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["57309"] = make_prepared_contract("57309", "Dish, noodles, with butter & herb sauce, dry", ("noodle", "herb",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["57308"] = make_prepared_contract("57308", "Dish, noodles, with butter sauce, dry", ("noodle",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["13913"] = make_prepared_contract("13913", "Pasta Dish, angel hair, butter & garlic, dry mix", ("pasta", "angel", "hair", "garlic",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["66150"] = make_prepared_contract("66150", "Pasta Dish, with vegetable & garlic butter sauce, frozen, serving", ("pasta", "vegetable", "garlic",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["66148"] = make_prepared_contract("66148", "Pasta Dish, with vegetable & herbed butter sauce, frozen", ("pasta", "vegetable", "herb",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["13916"] = make_prepared_contract("13916", "Rigatoni, with butter & herb sauce, dry", ("rigatoni", "herb",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["38613"] = make_prepared_contract("38613", "Pilaf, rice, herb & butter, dry", ("pilaf", "rice", "herb",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["25516"] = make_prepared_contract("25516", "Rice Dish, long grain & wild, butter & herb, fast cook, dry", ("rice", "long", "grain", "wild", "herb",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["92854"] = make_prepared_contract("92854", "Rice Dish, with garlic butter sauce, dry", ("rice", "garlic",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["57334"] = make_prepared_contract("57334", "Rice Dish, with herb & butter sauce, dry", ("rice", "herb",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["25522"] = make_prepared_contract("25522", "Dish, Ready Rice, butter & garlic, ready to heat", ("rice", "garlic",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["49187"] = make_prepared_contract("49187", "Dish, potatoes, creamy butter, in a cup, dry", ("potato",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["40996"] = make_prepared_contract("40996", "Dish, pretzel dog, jumbo, with butter", ("pretzel", "dog",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["41003"] = make_prepared_contract("41003", "Dish, pretzel dog, with butter", ("pretzel", "dog",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["24365"] = make_prepared_contract("24365", "Mashed Potatoes, REAL, butter & herb, prepared, from dry, FS", ("mashed", "potato",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["8894"] = make_prepared_contract("8894", "Mashed Potatoes, bites, Spudsters, butter flavor, frozen, FS", ("mashed", "potato", "bite",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["24362"] = make_prepared_contract("24362", "Mashed Potatoes, butter & herb, dry mix", ("mashed", "potato",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["17514"] = make_prepared_contract("17514", "Mashed Potatoes, butter & herb, dry serving", ("mashed", "potato",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["17503"] = make_prepared_contract("17503", "Mashed Potatoes, creamy butter, homestyle, dry mix, serving", ("mashed", "potato",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["5464"] = make_prepared_contract("5464", "Mashed Potatoes, flakes, prepared from dry with milk & butter", ("mashed", "potato", "flake",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["341"] = make_prepared_contract("341", "Mashed Potatoes, flakes, with butter flavor, dry", ("mashed", "potato", "flake",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["342"] = make_prepared_contract("342", "Mashed Potatoes, flakes, with parsley butter flavor, dry", ("mashed", "potato", "flake", "parsley",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["5585"] = make_prepared_contract("5585", "Mashed Potatoes, granules, prepared with whole milk & butter", ("mashed", "potato", "granule",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["5569"] = make_prepared_contract("5569", "Mashed Potatoes, prepared from recipe with whole milk & butter", ("mashed", "potato",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["6397"] = make_prepared_contract("6397", "Mashed Potatoes, with natural butter flavor", ("mashed", "potato",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["5590"] = make_prepared_contract("5590", "Hash Browns, with butter sauce, frozen, 6oz package", ("hash", "brown",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["5591"] = make_prepared_contract("5591", "Hash Browns, with butter sauce, prepared from fzn", ("hash", "brown",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["49353"] = make_prepared_contract("49353", "Dish, butter chicken, with basmati rice, frozen", ("chicken", "basmati", "rice",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["70080"] = make_prepared_contract("70080", "Meal, chicken, with butter sauce potato & vegetable, low calorie, frozen", ("chicken", "meal",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["16639"] = make_prepared_contract("16639", "Roll, crescent, butter flake, refrigerated dough", ("roll", "crescent",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["16637"] = make_prepared_contract("16637", "Roll, crescent, garlic butter, refrigerated dough", ("roll", "crescent", "garlic",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["33572"] = make_prepared_contract("33572", "Tortilla, flour, butter flavor, 8\"", ("tortilla", "flour",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["33573"] = make_prepared_contract("33573", "Tortilla, flour, butter, 8\"", ("tortilla", "flour",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["42334"] = make_prepared_contract("42334", "Croutons, garlic butter", ("crouton", "garlic",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["69166"] = make_prepared_contract("69166", "Salad Topping, croutons, butter garlic", ("crouton", "garlic",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["5337"] = make_prepared_contract("5337", "Frosting, Rich & Creamy, butter cream", ("frosting",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["5105"] = make_prepared_contract("5105", "Frosting, Whipped, butter cream", ("frosting", "whipped",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["46034"] = make_prepared_contract("46034", "Frosting, chocolate, creamy, prepared from dry mix with butter", ("frosting", "chocolate",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["45793"] = make_prepared_contract("45793", "Frosting, chocolate, glaze, prepared from recipe with butter", ("frosting", "chocolate", "glaze",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["40363"] = make_prepared_contract("40363", "Grits, corn, with butter flavor, instant", ("grit", "corn",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["53736"] = make_prepared_contract("53736", "Sauce, white, thin, prepared from recipe with butter", ("sauce", "white",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["9394"] = make_prepared_contract("9394", "Sauce,Whisk & Serve , hollandaise, with o msg & butter, dry, FS", ("sauce", "hollandaise",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["33846"] = make_prepared_contract("33846", "Base, butter sauce, FS", ("base", "sauce",), ("butter", "ghee", "clarified", "margarine", "shortening",))
CONTRACTS["23200"] = make_non_butter_contract("23200", "Baking Chips, chocolate, semi sweet, with butter", ("chip", "chocolate",), ("butter", "ghee",), BAKING_CATEGORIES)
CONTRACTS["90728"] = make_non_butter_contract("90728", "Baking Chips, chocolate, semi sweet, with butter, large", ("chip", "chocolate", "large",), ("butter", "ghee",), BAKING_CATEGORIES)
CONTRACTS["90729"] = make_non_butter_contract("90729", "Baking Chips, chocolate, semi sweet, with butter, mini", ("chip", "chocolate", "mini",), ("butter", "ghee",), BAKING_CATEGORIES)
CONTRACTS["8002"] = make_non_butter_contract("8002", "Cooking Spray, butter flavor", ("spray",), ("butter", "ghee", "clarified", "margarine",), SPRAY_CATEGORIES)
CONTRACTS["37716"] = make_non_butter_contract("37716", "Cooking Spray, butter flavor, corn, 1/3 sec spray", ("spray", "corn",), ("butter", "ghee", "clarified", "margarine",), SPRAY_CATEGORIES)
CONTRACTS["44914"] = make_non_butter_contract("44914", "Cooking Spray, canola, butter, 1/3 sec spray", ("spray", "canola",), ("butter", "ghee", "clarified", "margarine",), SPRAY_CATEGORIES)
CONTRACTS["44917"] = make_non_butter_contract("44917", "Cooking Spray, non-aerosol, canola, butter, 1/3 sec spray", ("spray", "canola", "aerosol",), ("butter", "ghee", "clarified", "margarine",), SPRAY_CATEGORIES)
CONTRACTS["44842"] = make_non_butter_contract("44842", "Oil, cooking spray, canola, with butter flavor, 0.33 second", ("spray", "canola",), ("butter", "ghee", "clarified", "margarine",), SPRAY_CATEGORIES)
CONTRACTS["48564"] = make_non_butter_contract("48564", "Lettuce, butter, fresh", ("lettuce",), ("butter", "ghee",), PRODUCE_CATEGORIES)
CONTRACTS["69198"] = make_non_butter_contract("69198", "Salad, butter lettuce & leaf lettuce", ("lettuce", "salad",), ("butter", "ghee",), PRODUCE_CATEGORIES)
CONTRACTS["24418"] = make_non_butter_contract("24418", "Nut Butter, Soy Butter 4 Me", ("soynut", "nut",), ("butter", "ghee", "clarified", "margarine", "shortening",), NUT_BUTTER_CATEGORIES)
CONTRACTS["17984"] = make_non_butter_contract("17984", "Nut Butter, SoyNut, chocolate", ("soynut", "chocolate",), ("butter", "ghee", "clarified", "margarine", "shortening",), NUT_BUTTER_CATEGORIES)
CONTRACTS["17981"] = make_non_butter_contract("17981", "Nut Butter, SoyNut, chunky, honey", ("soynut", "chunky",), ("butter", "ghee", "clarified", "margarine", "shortening",), NUT_BUTTER_CATEGORIES)
CONTRACTS["17979"] = make_non_butter_contract("17979", "Nut Butter, SoyNut, chunky, original", ("soynut", "chunky",), ("butter", "ghee", "clarified", "margarine", "shortening",), NUT_BUTTER_CATEGORIES)
CONTRACTS["17983"] = make_non_butter_contract("17983", "Nut Butter, SoyNut, chunky, unsweetened", ("soynut", "chunky", "unsweetened",), ("butter", "ghee", "clarified", "margarine", "shortening",), NUT_BUTTER_CATEGORIES)
CONTRACTS["17982"] = make_non_butter_contract("17982", "Nut Butter, SoyNut, creamy, honey", ("soynut", "creamy",), ("butter", "ghee", "clarified", "margarine", "shortening",), NUT_BUTTER_CATEGORIES)
CONTRACTS["17980"] = make_non_butter_contract("17980", "Nut Butter, SoyNut, creamy, original", ("soynut", "creamy",), ("butter", "ghee", "clarified", "margarine", "shortening",), NUT_BUTTER_CATEGORIES)
CONTRACTS["17987"] = make_non_butter_contract("17987", "Nut Butter, SoyNut, creamy, unsweetened", ("soynut", "creamy", "unsweetened",), ("butter", "ghee", "clarified", "margarine", "shortening",), NUT_BUTTER_CATEGORIES)
CONTRACTS["63503"] = make_non_butter_contract("63503", "Nut Butter, brazil", ("brazil", "nut",), ("butter", "ghee", "clarified", "margarine", "shortening",), NUT_BUTTER_CATEGORIES)
CONTRACTS["12992"] = make_non_butter_contract("12992", "Pickles, bread & butter", ("pickle",), ("butter", "ghee", "clarified", "margarine",), PICKLE_CATEGORIES)
CONTRACTS["27187"] = make_non_butter_contract("27187", "Pickles, bread & butter, Sandwich Stackers", ("pickle",), ("butter", "ghee", "clarified", "margarine",), PICKLE_CATEGORIES)
CONTRACTS["9689"] = make_non_butter_contract("9689", "Pickles, bread & butter, chips", ("pickle", "chip",), ("butter", "ghee", "clarified", "margarine",), PICKLE_CATEGORIES)
CONTRACTS["27192"] = make_non_butter_contract("27192", "Pickles, bread & butter, chips, original", ("pickle", "chip",), ("butter", "ghee", "clarified", "margarine",), PICKLE_CATEGORIES)
CONTRACTS["12974"] = make_non_butter_contract("12974", "Pickles, bread & butter, chips, with o salt", ("pickle", "chip",), ("butter", "ghee", "clarified", "margarine",), PICKLE_CATEGORIES)
CONTRACTS["93302"] = make_non_butter_contract("93302", "Pickles, bread & butter, chopped", ("pickle", "chopped",), ("butter", "ghee", "clarified", "margarine",), PICKLE_CATEGORIES)
CONTRACTS["93301"] = make_non_butter_contract("93301", "Pickles, bread & butter, large, 3\" long", ("pickle",), ("butter", "ghee", "clarified", "margarine",), PICKLE_CATEGORIES)
CONTRACTS["93304"] = make_non_butter_contract("93304", "Pickles, bread & butter, medium, 2 3/4\" long", ("pickle",), ("butter", "ghee", "clarified", "margarine",), PICKLE_CATEGORIES)
CONTRACTS["93305"] = make_non_butter_contract("93305", "Pickles, bread & butter, midget, 2 1/8\" long", ("pickle",), ("butter", "ghee", "clarified", "margarine",), PICKLE_CATEGORIES)
CONTRACTS["9688"] = make_non_butter_contract("9688", "Pickles, bread & butter, sandwich slice", ("pickle",), ("butter", "ghee", "clarified", "margarine",), PICKLE_CATEGORIES)
CONTRACTS["93303"] = make_non_butter_contract("93303", "Pickles, bread & butter, slices", ("pickle",), ("butter", "ghee", "clarified", "margarine",), PICKLE_CATEGORIES)
CONTRACTS["93306"] = make_non_butter_contract("93306", "Pickles, bread & butter, small, 2 1/2\" long", ("pickle",), ("butter", "ghee", "clarified", "margarine",), PICKLE_CATEGORIES)
CONTRACTS["93307"] = make_non_butter_contract("93307", "Pickles, bread & butter, spear", ("pickle",), ("butter", "ghee", "clarified", "margarine",), PICKLE_CATEGORIES)
CONTRACTS["14249"] = make_non_butter_contract("14249", "Rice Cake, Cracker Jack butter toffee", ("rice", "cake", "cracker", "toffee",), ("butter", "ghee",), BAKING_CATEGORIES)
CONTRACTS["14262"] = make_non_butter_contract("14262", "Rice Cake, butter popped corn", ("rice", "cake", "popcorn",), ("butter", "ghee",), BAKING_CATEGORIES)
CONTRACTS["91927"] = make_non_butter_contract("91927", "Salt, imitation butter flavor", ("salt", "imitation",), ("butter", "ghee",), ("salt", "seasoning"))
CONTRACTS["24172"] = make_non_butter_contract("24172", "Seasoning, butter", ("seasoning",), ("butter", "ghee",), ("seasoning", "spice", "salt"))
CONTRACTS["8348"] = make_non_butter_contract("8348", "Oil, nutmeg butter", ("nutmeg",), ("butter", "ghee",), ("oil", "baking"))
CONTRACTS["8352"] = make_non_butter_contract("8352", "Oil, ucuhuba butter", ("ucuhuba",), ("butter", "ghee",), ("oil", "baking"))
