from __future__ import annotations

from .contract_base import ContractFn, ContractSpec, MatchDecision, ProductFacts, accept, match_spec, reject


NUT_BUTTER_CATEGORIES = ("nut & seed butters", "nut and seed butters", "nut butters")
ICE_CREAM_CATEGORIES = ("ice cream & frozen yogurt", "other frozen desserts")
FROZEN_DESSERT_CATEGORIES = ("ice cream & frozen yogurt", "other frozen desserts")
CEREAL_CATEGORIES = ("cereal", "processed cereal products")
SANDWICH_CATEGORIES = ("lunch snacks & combinations", "frozen breakfast sandwiches, biscuits & meals", "breads & buns")
TOPPING_CATEGORIES = ("baking decorations & dessert toppings", "desserts/dessert sauces/toppings", "cake, cookie & cupcake mixes")
SNACK_CATEGORIES = ("snack, energy & granola bars", "popcorn, peanuts, seeds & related snacks", "chips, pretzels & snacks", "cookies & biscuits")
BEVERAGE_CATEGORIES = ("other drinks", "energy, protein & muscle recovery drinks", "coffee", "smoothie", "shake")
FORMULA_CATEGORIES = ("meal replacement supplements", "children nutritional", "specialty formula", "other drinks")
BEAN_CATEGORIES = ("bean", "beans", "legume", "vegetable", "canned", "frozen", "prepared", "processed")
OIL_CATEGORIES = ("oil", "cooking spray", "condiment", "sauce")
SPREAD_CATEGORIES = ("jam, jelly & fruit spreads", "dips & salsa", "condiment", "sauce")
MARGARINE_CATEGORIES = ("butter & spread", "margarine", "dairy")
CREAMER_CATEGORIES = ("cream", "coffee", "other drinks")
MEAL_CATEGORIES = ("frozen dinners & entrees", "prepared wraps and burittos", "meal", "dinner", "entree")
BAKING_CATEGORIES = ("baking/cooking mixes/supplies", "baking needs", "baking decorations & dessert toppings")


ALL_NUT_SEED_TYPES = ("almond", "cashew", "hazelnut", "pistachio", "macadamia", "walnut", "pecan", "peanut", "sunflower", "sesame", "tahini", "pumpkin")


def _exclude_others(allowed: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(t for t in ALL_NUT_SEED_TYPES if t not in allowed)


def _make_spread_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_required: tuple[str, ...] = (),
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*NUT_BUTTER_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        missing = [t for t in extra_required if not product.has_any(t)]
        if missing:
            return reject(f"{esha_code} missing required term(s): " + "|".join(missing))
        excluded = [t for t in _exclude_others(required_terms) + extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        excluded_ingredients = [t for t in extra_excludes if product.ingredients_have_any(t)]
        if excluded_ingredients:
            return reject(f"{esha_code} excluded ingredient term(s): " + "|".join(excluded_ingredients))
        return accept(f"{esha_code} reviewed nut butter spread accepted")
    return contract


def _make_ice_cream_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*ICE_CREAM_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed ice cream contract accepted")
    return contract


def _make_frozen_dessert_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*FROZEN_DESSERT_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed frozen dessert contract accepted")
    return contract


def _make_cereal_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*CEREAL_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed cereal contract accepted")
    return contract


def _make_sandwich_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*SANDWICH_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed sandwich contract accepted")
    return contract


def _make_topping_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*TOPPING_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed topping contract accepted")
    return contract


def _make_snack_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*SNACK_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed snack contract accepted")
    return contract


def _make_beverage_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*BEVERAGE_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed beverage contract accepted")
    return contract


def _make_baking_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*BAKING_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed baking contract accepted")
    return contract


def _make_formula_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*FORMULA_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed formula contract accepted")
    return contract


def _make_bean_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*BEAN_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        if product.has_any("peanut", "almond", "cashew", "sunflower", "sesame", "tahini", "hazelnut", "pistachio", "macadamia", "walnut", "pecan"):
            return reject(f"{esha_code} nut butter cue conflicts with butter bean")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed butter bean contract accepted")
    return contract


def _make_margarine_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*MARGARINE_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed margarine contract accepted")
    return contract


def _make_oil_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*OIL_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed oil contract accepted")
    return contract


def _make_spread_contract_other(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*SPREAD_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed spread contract accepted")
    return contract


def _make_creamer_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*CREAMER_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed creamer contract accepted")
    return contract


def _make_meal_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    extra_excludes: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not product.category_has_any(*MEAL_CATEGORIES):
            return reject(f"{esha_code} category mismatch")
        if not product.has_any(*required_terms):
            return reject(f"{esha_code} missing required term(s)")
        excluded = [t for t in extra_excludes if product.has_any(t)]
        if excluded:
            return reject(f"{esha_code} excluded term(s): " + "|".join(excluded))
        return accept(f"{esha_code} reviewed meal contract accepted")
    return contract




# Build contracts and named functions
CONTRACTS: dict[str, ContractFn] = {}

# peanut_butter_spread
CONTRACTS["4576"] = _make_spread_contract("4576", 'Nut Butter, peanut, chunky, unsalted', ('peanut', 'chunky'), ())
globals()["match_esha_04576"] = CONTRACTS["4576"]
CONTRACTS["4626"] = _make_spread_contract("4626", 'Nut Butter, peanut, chunky', ('peanut', 'chunky'), ())
globals()["match_esha_04626"] = CONTRACTS["4626"]
CONTRACTS["4627"] = _make_spread_contract("4627", 'Nut Butter, peanut, creamy', ('peanut', 'creamy'), ())
globals()["match_esha_04627"] = CONTRACTS["4627"]
CONTRACTS["4636"] = _make_spread_contract("4636", 'Nut Butter, peanut, creamy, unsalted', ('peanut', 'creamy'), ('salt',))
globals()["match_esha_04636"] = CONTRACTS["4636"]
CONTRACTS["4747"] = _make_spread_contract("4747", 'Peanut Butter, reduced fat', ('peanut',), ('reduced', 'fat'))
globals()["match_esha_04747"] = CONTRACTS["4747"]
CONTRACTS["14924"] = _make_spread_contract("14924", 'Peanut Butter, creamy, with omega 3', ('peanut', 'creamy'), ('omega',))
globals()["match_esha_14924"] = CONTRACTS["14924"]
CONTRACTS["15725"] = _make_spread_contract("15725", 'Peanut Butter, creamy, unsalted, serving, org', ('peanut', 'creamy'), ('unsalted',))
globals()["match_esha_15725"] = CONTRACTS["15725"]
CONTRACTS["15726"] = _make_spread_contract("15726", 'Peanut Butter, crunchy, unsalted, serving, org', ('peanut', 'crunchy'), ('unsalted',))
globals()["match_esha_15726"] = CONTRACTS["15726"]
CONTRACTS["18852"] = _make_spread_contract("18852", 'Nut Butter, peanut, creamy, Natural, no stir', ('peanut', 'creamy'), ('stir',))
globals()["match_esha_18852"] = CONTRACTS["18852"]
CONTRACTS["24405"] = _make_spread_contract("24405", 'Nut Butter, peanut, creamy, PB 4 Me', ('peanut', 'creamy'), ())
globals()["match_esha_24405"] = CONTRACTS["24405"]
CONTRACTS["24406"] = _make_spread_contract("24406", 'Nut Butter, peanut, crunchy, PB 4 Me', ('peanut', 'chunky'), ())
globals()["match_esha_24406"] = CONTRACTS["24406"]
CONTRACTS["25778"] = _make_spread_contract(
    "25778",
    'Peanut Butter',
    ('peanut',),
    ('butter',),
    (
        "apple",
        "banana",
        "blend",
        "brownie",
        "chia",
        "chocolate",
        "cinnamon",
        "cocoa",
        "cookie",
        "cup",
        "fudge",
        "grape",
        "honey",
        "jelly",
        "maple",
        "marshmallow",
        "mini",
        "nutrient",
        "powder",
        "powdered",
        "protein",
        "reduced",
        "strawberry",
    ),
)
globals()["match_esha_25778"] = CONTRACTS["25778"]
CONTRACTS["26858"] = _make_spread_contract("26858", 'Peanut Butter, smooth, reduced fat', ('peanut', 'smooth'), ('reduced', 'fat'))
globals()["match_esha_26858"] = CONTRACTS["26858"]
CONTRACTS["26859"] = _make_spread_contract("26859", 'Peanut Butter, smooth, vitamin & mineral fortified', ('peanut', 'smooth'), ('vitamin', 'fortified'))
globals()["match_esha_26859"] = CONTRACTS["26859"]
CONTRACTS["27922"] = _make_spread_contract("27922", 'Nut Butter, peanut, creamy, with agave syrup', ('peanut', 'creamy'), ('agave',))
globals()["match_esha_27922"] = CONTRACTS["27922"]
CONTRACTS["27923"] = _make_spread_contract("27923", 'Nut Butter, peanut, crunchy, with agave syrup', ('peanut', 'chunky'), ('agave',))
globals()["match_esha_27923"] = CONTRACTS["27923"]
CONTRACTS["36669"] = _make_spread_contract("36669", 'Nut Butter, peanut, creamy, honey roast', ('peanut', 'creamy'), ('honey', 'roast'))
globals()["match_esha_36669"] = CONTRACTS["36669"]
CONTRACTS["36670"] = _make_spread_contract("36670", 'Nut Butter, peanut, creamy, plus, with added vitamin & min', ('peanut', 'creamy'), ('vitamin',))
globals()["match_esha_36670"] = CONTRACTS["36670"]
CONTRACTS["36671"] = _make_spread_contract("36671", 'Nut Butter, peanut, creamy, reduced fat', ('peanut', 'creamy'), ('reduced', 'fat'))
globals()["match_esha_36671"] = CONTRACTS["36671"]
CONTRACTS["36672"] = _make_spread_contract("36672", 'Nut Butter, peanut, creamy, whipped, reduced sugar', ('peanut', 'creamy'), ('whipped', 'reduced', 'sugar'))
globals()["match_esha_36672"] = CONTRACTS["36672"]
CONTRACTS["36673"] = _make_spread_contract("36673", 'Nut Butter, peanut, crunchy', ('peanut', 'chunky'), ())
globals()["match_esha_36673"] = CONTRACTS["36673"]
CONTRACTS["36674"] = _make_spread_contract("36674", 'Nut Butter, peanut, crunchy, honey roast', ('peanut', 'chunky'), ('honey', 'roast'))
globals()["match_esha_36674"] = CONTRACTS["36674"]
CONTRACTS["36675"] = _make_spread_contract("36675", 'Nut Butter, peanut, crunchy, reduced fat', ('peanut', 'chunky'), ('reduced', 'fat'))
globals()["match_esha_36675"] = CONTRACTS["36675"]
CONTRACTS["39901"] = _make_spread_contract("39901", 'Nut Butter, peanut, creamy, with salt, roasted', ('peanut', 'creamy'), ('roasted',))
globals()["match_esha_39901"] = CONTRACTS["39901"]
CONTRACTS["39902"] = _make_spread_contract("39902", 'Nut Butter, peanut, crunchy, with salt, roasted', ('peanut', 'chunky'), ('roasted',))
globals()["match_esha_39902"] = CONTRACTS["39902"]
CONTRACTS["39903"] = _make_spread_contract("39903", 'Nut Butter, peanut, creamy, no salt, roasted', ('peanut', 'creamy'), ('salt', 'roasted'))
globals()["match_esha_39903"] = CONTRACTS["39903"]
CONTRACTS["39904"] = _make_spread_contract("39904", 'Nut Butter, peanut, crunchy, no salt, roasted', ('peanut', 'chunky'), ('salt', 'roasted'))
globals()["match_esha_39904"] = CONTRACTS["39904"]
CONTRACTS["39905"] = _make_spread_contract("39905", 'Nut Butter, peanut, creamy, no stir', ('peanut', 'creamy'), ('stir',))
globals()["match_esha_39905"] = CONTRACTS["39905"]
CONTRACTS["39906"] = _make_spread_contract("39906", 'Nut Butter, peanut, crunchy, no stir', ('peanut', 'chunky'), ('stir',))
globals()["match_esha_39906"] = CONTRACTS["39906"]
CONTRACTS["49283"] = _make_spread_contract("49283", 'Peanut Butter, creamy, with unblanched peanuts, salted', ('peanut', 'creamy'), ())
globals()["match_esha_49283"] = CONTRACTS["49283"]
CONTRACTS["49284"] = _make_spread_contract("49284", 'Peanut Butter, crunchy, with unblanched peanuts, unsalted', ('peanut', 'chunky'), ('unsalted',))
globals()["match_esha_49284"] = CONTRACTS["49284"]
CONTRACTS["49285"] = _make_spread_contract("49285", 'Peanut Butter, valencia, creamy, with sea salt', ('peanut', 'valencia'), ())
globals()["match_esha_49285"] = CONTRACTS["49285"]
CONTRACTS["62937"] = _make_spread_contract("62937", 'Peanut Butter, crunchy, extra', ('peanut', 'chunky'), ())
globals()["match_esha_62937"] = CONTRACTS["62937"]
CONTRACTS["62939"] = _make_spread_contract("62939", 'Peanut Butter, crunchy, reduced fat', ('peanut', 'chunky'), ('reduced', 'fat'))
globals()["match_esha_62939"] = CONTRACTS["62939"]
CONTRACTS["62940"] = _make_spread_contract("62940", 'Peanut Butter, simply, low sodium & 33% less sugar', ('peanut',), ('sodium', 'sugar'))
globals()["match_esha_62940"] = CONTRACTS["62940"]
CONTRACTS["62941"] = _make_spread_contract("62941", 'Nut Butter, peanut, apple cinnamon', ('peanut',), ('apple', 'cinnamon'))
globals()["match_esha_62941"] = CONTRACTS["62941"]
CONTRACTS["62942"] = _make_spread_contract("62942", 'Nut Butter, peanut, chocolate silk', ('peanut',), ('chocolate', 'silk'))
globals()["match_esha_62942"] = CONTRACTS["62942"]
CONTRACTS["62943"] = _make_spread_contract("62943", 'Peanut Butter, with berry flavors', ('peanut',), ('berry',))
globals()["match_esha_62943"] = CONTRACTS["62943"]
CONTRACTS["62944"] = _make_spread_contract("62944", 'Peanut Butter, natural, creamy', ('peanut', 'creamy'), ())
globals()["match_esha_62944"] = CONTRACTS["62944"]
CONTRACTS["62945"] = _make_spread_contract("62945", 'Peanut Butter, natural, chunky', ('peanut', 'chunky'), ())
globals()["match_esha_62945"] = CONTRACTS["62945"]
CONTRACTS["62946"] = _make_spread_contract("62946", 'Peanut Butter, natural, creamy, unsalted', ('peanut', 'creamy'), ('unsalted',))
globals()["match_esha_62946"] = CONTRACTS["62946"]
CONTRACTS["62947"] = _make_spread_contract("62947", 'Peanut Butter, natural, chunky, unsalted', ('peanut', 'chunky'), ('unsalted',))
globals()["match_esha_62947"] = CONTRACTS["62947"]
CONTRACTS["62948"] = _make_spread_contract("62948", 'Peanut Butter, natural, creamy, reduced fat', ('peanut', 'creamy'), ('reduced', 'fat'))
globals()["match_esha_62948"] = CONTRACTS["62948"]
CONTRACTS["62949"] = _make_spread_contract("62949", 'Peanut Butter, with grape jelly', ('peanut',), ('grape', 'jelly'))
globals()["match_esha_62949"] = CONTRACTS["62949"]
CONTRACTS["62950"] = _make_spread_contract("62950", 'Peanut Butter, with strawberry jelly', ('peanut',), ('strawberry', 'jelly'))
globals()["match_esha_62950"] = CONTRACTS["62950"]
CONTRACTS["63335"] = _make_spread_contract("63335", 'Peanut Butter, reduced sodium', ('peanut',), ('sodium',))
globals()["match_esha_63335"] = CONTRACTS["63335"]
CONTRACTS["63338"] = _make_spread_contract("63338", 'Peanut Butter, creamy, reduced fat', ('peanut', 'creamy'), ('reduced', 'fat'))
globals()["match_esha_63338"] = CONTRACTS["63338"]
CONTRACTS["63339"] = _make_spread_contract("63339", 'Peanut Butter, creamy, vitamin & mineral fortified', ('peanut', 'creamy'), ('vitamin', 'fortified'))
globals()["match_esha_63339"] = CONTRACTS["63339"]
CONTRACTS["63340"] = _make_spread_contract("63340", 'Nut Butter, peanut, chunky, vitamin & mineral fortified', ('peanut', 'chunky'), ('vitamin', 'fortified'))
globals()["match_esha_63340"] = CONTRACTS["63340"]
CONTRACTS["63380"] = _make_spread_contract("63380", 'Peanut Butter, super chunk', ('peanut', 'chunk'), ())
globals()["match_esha_63380"] = CONTRACTS["63380"]
CONTRACTS["63382"] = _make_spread_contract("63382", 'Peanut Butter, super chunk, reduced fat', ('peanut', 'chunk'), ('reduced', 'fat'))
globals()["match_esha_63382"] = CONTRACTS["63382"]
CONTRACTS["63383"] = _make_spread_contract("63383", 'Nut Butter, peanut, creamy, roasted honey nut', ('peanut', 'creamy'), ('honey', 'roast'))
globals()["match_esha_63383"] = CONTRACTS["63383"]
CONTRACTS["63384"] = _make_spread_contract("63384", 'Peanut Butter, super chunk, roasted honey nut', ('peanut', 'chunk'), ('honey', 'roast'))
globals()["match_esha_63384"] = CONTRACTS["63384"]
CONTRACTS["63385"] = _make_spread_contract("63385", 'Nut Butter, peanut, creamy, Squeez It', ('peanut', 'creamy'), ())
globals()["match_esha_63385"] = CONTRACTS["63385"]
CONTRACTS["63386"] = _make_spread_contract("63386", 'Peanut Butter, snack, creamy, Squeeze Stix', ('peanut', 'creamy'), ())
globals()["match_esha_63386"] = CONTRACTS["63386"]
CONTRACTS["63387"] = _make_spread_contract("63387", 'Peanut Butter, snack, creamy, chocolate, Squeeze Stix', ('peanut', 'creamy'), ('chocolate',))
globals()["match_esha_63387"] = CONTRACTS["63387"]
CONTRACTS["63445"] = _make_spread_contract("63445", 'Nut Butter, peanut, smooth, USDA Commodity', ('peanut', 'smooth'), ())
globals()["match_esha_63445"] = CONTRACTS["63445"]
CONTRACTS["63464"] = _make_spread_contract("63464", 'Peanut Butter, crunchy, Valencia', ('peanut', 'chunky'), ('valencia',))
globals()["match_esha_63464"] = CONTRACTS["63464"]
CONTRACTS["63466"] = _make_spread_contract("63466", 'Peanut Butter, creamy, Valencia', ('peanut', 'creamy'), ('valencia',))
globals()["match_esha_63466"] = CONTRACTS["63466"]
CONTRACTS["63652"] = _make_spread_contract("63652", 'Nut Butter, peanut, creamy, with omegas', ('peanut', 'creamy'), ('omega',))
globals()["match_esha_63652"] = CONTRACTS["63652"]
CONTRACTS["63653"] = _make_spread_contract("63653", 'Nut Butter, peanut, chunky, with omegas', ('peanut', 'chunky'), ('omega',))
globals()["match_esha_63653"] = CONTRACTS["63653"]
CONTRACTS["63721"] = _make_spread_contract("63721", 'Peanut Butter, reduced sugar', ('peanut',), ('sugar',))
globals()["match_esha_63721"] = CONTRACTS["63721"]

# almond_butter_spread
CONTRACTS["4534"] = _make_spread_contract("4534", 'Nut Butter, almond, unsalted', ('almond',), ('unsalted',))
globals()["match_esha_04534"] = CONTRACTS["4534"]
CONTRACTS["4572"] = _make_spread_contract("4572", 'Nut Butter, almond', ('almond',), ())
globals()["match_esha_04572"] = CONTRACTS["4572"]
CONTRACTS["15719"] = _make_spread_contract("15719", 'Nut Butter, creamy, almond, unsalted', ('almond', 'creamy'), ('unsalted',))
globals()["match_esha_15719"] = CONTRACTS["15719"]
CONTRACTS["15720"] = _make_spread_contract("15720", 'Nut Butter, crunchy, almond, unsalted', ('almond', 'crunchy'), ('unsalted',))
globals()["match_esha_15720"] = CONTRACTS["15720"]
CONTRACTS["15721"] = _make_spread_contract("15721", 'Nut Butter, creamy, almond', ('almond', 'creamy'), ())
globals()["match_esha_15721"] = CONTRACTS["15721"]
CONTRACTS["15722"] = _make_spread_contract("15722", 'Nut Butter, crunchy, almond', ('almond', 'crunchy'), ())
globals()["match_esha_15722"] = CONTRACTS["15722"]
CONTRACTS["27924"] = _make_spread_contract("27924", 'Nut Butter, almond, creamy, with agave syrup', ('almond', 'creamy'), ('agave',))
globals()["match_esha_27924"] = CONTRACTS["27924"]
CONTRACTS["39890"] = _make_spread_contract("39890", 'Nut Butter, almond, creamy, no salt, raw', ('almond', 'creamy'), ('salt', 'raw'))
globals()["match_esha_39890"] = CONTRACTS["39890"]
CONTRACTS["39891"] = _make_spread_contract("39891", 'Nut Butter, almond, crunchy, no salt, raw', ('almond', 'crunchy'), ('salt', 'raw'))
globals()["match_esha_39891"] = CONTRACTS["39891"]
CONTRACTS["39892"] = _make_spread_contract("39892", 'Nut Butter, almond, crunchy, no salt, roasted', ('almond', 'crunchy'), ('salt', 'roasted'))
globals()["match_esha_39892"] = CONTRACTS["39892"]
CONTRACTS["39893"] = _make_spread_contract("39893", 'Nut Butter, almond, creamy, no salt, roasted', ('almond', 'creamy'), ('salt', 'roasted'))
globals()["match_esha_39893"] = CONTRACTS["39893"]
CONTRACTS["39894"] = _make_spread_contract("39894", 'Nut Butter, almond, crunchy, natural, no salt, roasted', ('almond', 'crunchy'), ('salt', 'roasted'))
globals()["match_esha_39894"] = CONTRACTS["39894"]
CONTRACTS["39895"] = _make_spread_contract("39895", 'Nut Butter, almond, creamy, natural, no salt, raw', ('almond', 'creamy'), ('salt', 'raw'))
globals()["match_esha_39895"] = CONTRACTS["39895"]
CONTRACTS["39896"] = _make_spread_contract("39896", 'Nut Butter, almond, honey, natural', ('almond',), ('honey',))
globals()["match_esha_39896"] = CONTRACTS["39896"]
CONTRACTS["39897"] = _make_spread_contract("39897", 'Nut Butter, almond, creamy, hint of sea salt', ('almond', 'creamy'), ())
globals()["match_esha_39897"] = CONTRACTS["39897"]
CONTRACTS["39898"] = _make_spread_contract("39898", 'Nut Butter, almond, crunchy, hint of sea salt', ('almond', 'crunchy'), ())
globals()["match_esha_39898"] = CONTRACTS["39898"]
CONTRACTS["39899"] = _make_spread_contract("39899", 'Nut Butter, almond, creamy, no stir', ('almond', 'creamy'), ('stir',))
globals()["match_esha_39899"] = CONTRACTS["39899"]
CONTRACTS["39900"] = _make_spread_contract("39900", 'Nut Butter, almond, crunchy, no stir', ('almond', 'crunchy'), ('stir',))
globals()["match_esha_39900"] = CONTRACTS["39900"]
CONTRACTS["42996"] = _make_spread_contract("42996", 'Nut Butter, almond, org', ('almond',), ())
globals()["match_esha_42996"] = CONTRACTS["42996"]
CONTRACTS["42997"] = _make_spread_contract("42997", 'Nut Butter, almond, strawberry', ('almond',), ('strawberry',))
globals()["match_esha_42997"] = CONTRACTS["42997"]
CONTRACTS["42998"] = _make_spread_contract("42998", 'Nut Butter, almond haze, org', ('almond',), ())
globals()["match_esha_42998"] = CONTRACTS["42998"]
CONTRACTS["43004"] = _make_spread_contract("43004", 'Nut Butter, almond, chocolate, unsweetened', ('almond',), ('chocolate', 'unsweetened'))
globals()["match_esha_43004"] = CONTRACTS["43004"]
CONTRACTS["43006"] = _make_spread_contract("43006", 'Nut Butter, almond, chocolate bliss, with lite coconut', ('almond',), ('chocolate', 'coconut'))
globals()["match_esha_43006"] = CONTRACTS["43006"]
CONTRACTS["43007"] = _make_spread_contract("43007", 'Nut Butter, almond, chocolate bliss, with lite coconut, org', ('almond',), ('chocolate', 'coconut'))
globals()["match_esha_43007"] = CONTRACTS["43007"]
CONTRACTS["43008"] = _make_spread_contract("43008", 'Nut Butter, almond, chocolate bliss, with lite coconut, unsweetened', ('almond',), ('chocolate', 'coconut', 'unsweetened'))
globals()["match_esha_43008"] = CONTRACTS["43008"]
CONTRACTS["48985"] = _make_spread_contract("48985", 'Almond Butter, crunchy, with roasted flaxseed, salted', ('almond', 'crunchy'), ())
globals()["match_esha_48985"] = CONTRACTS["48985"]
CONTRACTS["63493"] = _make_spread_contract("63493", 'Nut Butter, almond, cherry', ('almond',), ('cherry',))
globals()["match_esha_63493"] = CONTRACTS["63493"]
CONTRACTS["63494"] = _make_spread_contract("63494", 'Nut Butter, almond, orange', ('almond',), ('orange',))
globals()["match_esha_63494"] = CONTRACTS["63494"]
CONTRACTS["63495"] = _make_spread_contract("63495", 'Nut Butter, almond haze', ('almond',), ())
globals()["match_esha_63495"] = CONTRACTS["63495"]
CONTRACTS["63509"] = _make_spread_contract("63509", 'Nut Butter, almond, chocolate', ('almond',), ('chocolate',))
globals()["match_esha_63509"] = CONTRACTS["63509"]
CONTRACTS["63510"] = _make_spread_contract("63510", 'Nut Butter, almond, chocolate, org', ('almond',), ('chocolate',))
globals()["match_esha_63510"] = CONTRACTS["63510"]

# cashew_butter_spread
CONTRACTS["4537"] = _make_spread_contract("4537", 'Nut Butter, cashew, plain, unsalted', ('cashew',), ('unsalted',))
globals()["match_esha_04537"] = CONTRACTS["4537"]
CONTRACTS["4662"] = _make_spread_contract("4662", 'Nut Butter, cashew, plain', ('cashew',), ())
globals()["match_esha_04662"] = CONTRACTS["4662"]
CONTRACTS["15723"] = _make_spread_contract("15723", 'Nut Butter, cashew, creamy, unsalted, serving', ('cashew', 'creamy'), ('unsalted',))
globals()["match_esha_15723"] = CONTRACTS["15723"]
CONTRACTS["39908"] = _make_spread_contract("39908", 'Nut Butter, cashew, creamy, natural, no salt', ('cashew', 'creamy'), ('salt',))
globals()["match_esha_39908"] = CONTRACTS["39908"]
CONTRACTS["63497"] = _make_spread_contract("63497", 'Nut Butter, cashew', ('cashew',), ())
globals()["match_esha_63497"] = CONTRACTS["63497"]
CONTRACTS["63504"] = _make_spread_contract("63504", 'Nut Butter, cashew, org', ('cashew',), ())
globals()["match_esha_63504"] = CONTRACTS["63504"]

# sunflower_butter_spread
CONTRACTS["4550"] = _make_spread_contract("4550", 'Sunflower Seed Butter, unsalted', ('sunflower',), ('unsalted',))
globals()["match_esha_04550"] = CONTRACTS["4550"]
CONTRACTS["4661"] = _make_spread_contract("4661", 'Sunflower Seed Butter', ('sunflower',), ())
globals()["match_esha_04661"] = CONTRACTS["4661"]
CONTRACTS["39907"] = _make_spread_contract("39907", 'Nut Butter, sunflower seed, hint of sea salt, roasted', ('sunflower',), ('roasted',))
globals()["match_esha_39907"] = CONTRACTS["39907"]
CONTRACTS["63502"] = _make_spread_contract("63502", 'Nut Butter, sunflower seed', ('sunflower',), ())
globals()["match_esha_63502"] = CONTRACTS["63502"]

# sesame_butter_spread
CONTRACTS["4683"] = _make_spread_contract("4683", 'Sesame Seed Butter, paste', ('sesame',), ())
globals()["match_esha_04683"] = CONTRACTS["4683"]
CONTRACTS["39911"] = _make_spread_contract("39911", 'Nut Butter, sesame tahini, creamy, natural, with salt, raw', ('sesame', 'tahini'), ('raw',))
globals()["match_esha_39911"] = CONTRACTS["39911"]
CONTRACTS["39912"] = _make_spread_contract("39912", 'Nut Butter, sesame tahini, creamy,natural, with salt, roasted', ('sesame', 'tahini'), ('roasted',))
globals()["match_esha_39912"] = CONTRACTS["39912"]
CONTRACTS["53719"] = _make_spread_contract("53719", 'Sesame Seed Butter', ('sesame',), ())
globals()["match_esha_53719"] = CONTRACTS["53719"]
CONTRACTS["63465"] = _make_spread_contract("63465", 'Sesame Butter, tahini', ('sesame', 'tahini'), ())
globals()["match_esha_63465"] = CONTRACTS["63465"]
CONTRACTS["63762"] = _make_spread_contract("63762", 'Sesame Seed Butter, from rstd & toasted kernels', ('sesame',), ('toasted',))
globals()["match_esha_63762"] = CONTRACTS["63762"]
CONTRACTS["63763"] = _make_spread_contract("63763", 'Sesame Seed Butter, from raw & stone ground kernels', ('sesame',), ('raw', 'stone'))
globals()["match_esha_63763"] = CONTRACTS["63763"]
CONTRACTS["63764"] = _make_spread_contract("63764", 'Sesame Seed Butter, from unrstd kernels', ('sesame',), ())
globals()["match_esha_63764"] = CONTRACTS["63764"]

# hazelnut_butter_spread
CONTRACTS["15724"] = _make_spread_contract("15724", 'Nut Butter, hazelnut, creamy, unsalted, serving', ('hazelnut', 'creamy'), ('unsalted',))
globals()["match_esha_15724"] = CONTRACTS["15724"]
CONTRACTS["43005"] = _make_spread_contract("43005", 'Nut Butter, hazelnut, chocolate haze, unsweetened', ('hazelnut',), ('chocolate', 'unsweetened'))
globals()["match_esha_43005"] = CONTRACTS["43005"]
CONTRACTS["63498"] = _make_spread_contract("63498", 'Nut Butter, hazelnut', ('hazelnut',), ())
globals()["match_esha_63498"] = CONTRACTS["63498"]
CONTRACTS["63511"] = _make_spread_contract("63511", 'Nut Butter, hazelnut, chocolate cherry haze', ('hazelnut',), ('chocolate', 'cherry'))
globals()["match_esha_63511"] = CONTRACTS["63511"]
CONTRACTS["63512"] = _make_spread_contract("63512", 'Nut Butter, hazelnut, chocolate haze', ('hazelnut',), ('chocolate',))
globals()["match_esha_63512"] = CONTRACTS["63512"]
CONTRACTS["63513"] = _make_spread_contract("63513", 'Nut Butter, hazelnut, chocolate cherry haze, org', ('hazelnut',), ('chocolate', 'cherry'))
globals()["match_esha_63513"] = CONTRACTS["63513"]

# pistachio_butter_spread
CONTRACTS["42999"] = _make_spread_contract("42999", 'Nut Butter, pistachio, org', ('pistachio',), ())
globals()["match_esha_42999"] = CONTRACTS["42999"]
CONTRACTS["63500"] = _make_spread_contract("63500", 'Nut Butter, pistachio', ('pistachio',), ())
globals()["match_esha_63500"] = CONTRACTS["63500"]

# macadamia_butter_spread
CONTRACTS["43000"] = _make_spread_contract("43000", 'Nut Butter, macadamia, org', ('macadamia',), ())
globals()["match_esha_43000"] = CONTRACTS["43000"]
CONTRACTS["63506"] = _make_spread_contract("63506", 'Nut Butter, macadamia', ('macadamia',), ())
globals()["match_esha_63506"] = CONTRACTS["63506"]

# walnut_butter_spread
CONTRACTS["43001"] = _make_spread_contract("43001", 'Nut Butter, walnut, org', ('walnut',), ())
globals()["match_esha_43001"] = CONTRACTS["43001"]
CONTRACTS["63508"] = _make_spread_contract("63508", 'Nut Butter, walnut', ('walnut',), ())
globals()["match_esha_63508"] = CONTRACTS["63508"]

# pecan_butter_spread
CONTRACTS["43002"] = _make_spread_contract("43002", 'Nut Butter, pecan', ('pecan',), ())
globals()["match_esha_43002"] = CONTRACTS["43002"]
CONTRACTS["43003"] = _make_spread_contract("43003", 'Nut Butter, pecan, org', ('pecan',), ())
globals()["match_esha_43003"] = CONTRACTS["43003"]

# pumpkin_seed_butter_spread
CONTRACTS["63501"] = _make_spread_contract("63501", 'Nut Butter, pumpkin seed', ('pumpkin',), ())
globals()["match_esha_63501"] = CONTRACTS["63501"]

# ice_cream
CONTRACTS["2207"] = _make_ice_cream_contract("2207", 'Ice Cream, peanut butter cup', ('ice', 'cream', 'peanut', 'butter'), ())
globals()["match_esha_02207"] = CONTRACTS["2207"]
CONTRACTS["2389"] = _make_ice_cream_contract("2389", 'Ice Cream, butter pecan', ('ice', 'cream', 'butter', 'pecan'), ())
globals()["match_esha_02389"] = CONTRACTS["2389"]
CONTRACTS["2394"] = _make_ice_cream_contract("2394", 'Ice Cream, chocolate peanut butter', ('ice', 'cream', 'chocolate', 'peanut', 'butter'), ())
globals()["match_esha_02394"] = CONTRACTS["2394"]
CONTRACTS["18183"] = _make_ice_cream_contract("18183", 'Ice Cream Sandwich, chocolate peanut butter, lowfat', ('ice', 'cream', 'chocolate', 'peanut', 'butter'), ())
globals()["match_esha_18183"] = CONTRACTS["18183"]
CONTRACTS["18383"] = _make_ice_cream_contract("18383", 'Ice Cream, butter pecan, light', ('ice', 'cream', 'butter', 'pecan'), ())
globals()["match_esha_18383"] = CONTRACTS["18383"]
CONTRACTS["18413"] = _make_ice_cream_contract("18413", 'Ice Cream, peanut butter cup, light', ('ice', 'cream', 'peanut', 'butter'), ())
globals()["match_esha_18413"] = CONTRACTS["18413"]
CONTRACTS["18427"] = _make_ice_cream_contract("18427", 'Ice Cream, butter pecan, light, no sugar added, with Splenda', ('ice', 'cream', 'butter', 'pecan'), ())
globals()["match_esha_18427"] = CONTRACTS["18427"]
CONTRACTS["18576"] = _make_ice_cream_contract("18576", 'Ice Cream, Loaded, chocolate peanut butter cup', ('ice', 'cream', 'chocolate', 'peanut', 'butter'), ())
globals()["match_esha_18576"] = CONTRACTS["18576"]
CONTRACTS["19204"] = _make_ice_cream_contract("19204", 'Ice Cream, butter pecan, old fashioned', ('ice', 'cream', 'butter', 'pecan'), ())
globals()["match_esha_19204"] = CONTRACTS["19204"]
CONTRACTS["19208"] = _make_ice_cream_contract("19208", "Ice Cream, peanut butter 'n chocolate", ('ice', 'cream', 'peanut', 'butter', 'chocolate'), ())
globals()["match_esha_19208"] = CONTRACTS["19208"]
CONTRACTS["19214"] = _make_ice_cream_contract("19214", "Ice Cream, Reese's peanut butter cup", ('ice', 'cream', 'peanut', 'butter'), ())
globals()["match_esha_19214"] = CONTRACTS["19214"]
CONTRACTS["19727"] = _make_ice_cream_contract("19727", 'Ice Cream, butter pecan, non dairy, FS', ('ice', 'cream', 'butter', 'pecan'), ())
globals()["match_esha_19727"] = CONTRACTS["19727"]
CONTRACTS["71475"] = _make_ice_cream_contract("71475", 'Ice Cream, butter almond', ('ice', 'cream', 'butter', 'almond'), ())
globals()["match_esha_71475"] = CONTRACTS["71475"]
CONTRACTS["71508"] = _make_ice_cream_contract("71508", 'Ice Cream, butter pecan, no sugar added, reduced fat', ('ice', 'cream', 'butter', 'pecan'), ())
globals()["match_esha_71508"] = CONTRACTS["71508"]
CONTRACTS["71519"] = _make_ice_cream_contract("71519", 'Ice Cream, butter pecan, homemade style', ('ice', 'cream', 'butter', 'pecan'), ())
globals()["match_esha_71519"] = CONTRACTS["71519"]
CONTRACTS["71532"] = _make_ice_cream_contract("71532", 'Ice Cream, Reeses peanut butter cups', ('ice', 'cream', 'peanut', 'butter'), ())
globals()["match_esha_71532"] = CONTRACTS["71532"]
CONTRACTS["72751"] = _make_ice_cream_contract("72751", 'Ice Cream, peanut butter', ('ice', 'cream', 'peanut', 'butter'), ())
globals()["match_esha_72751"] = CONTRACTS["72751"]

# frozen_dessert
CONTRACTS["2371"] = _make_frozen_dessert_contract("2371", "Frozen Dessert, Blizzard, Reese's peanut butter cups, small", ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_02371"] = CONTRACTS["2371"]
CONTRACTS["2372"] = _make_frozen_dessert_contract("2372", "Frozen Dessert, Blizzard, Reese's peanut butter cups, medium", ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_02372"] = CONTRACTS["2372"]
CONTRACTS["11998"] = _make_frozen_dessert_contract("11998", "Frozen Dessert Sandwich, peanut butter, dairy free, li'l", ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_11998"] = CONTRACTS["11998"]
CONTRACTS["12282"] = _make_frozen_dessert_contract("12282", 'Frozen Dessert Bar, peanut butter fudge, non dairy', ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_12282"] = CONTRACTS["12282"]
CONTRACTS["12305"] = _make_frozen_dessert_contract("12305", 'Frozen Dessert, chocolate peanut butter, non dairy', ('frozen', 'dessert', 'chocolate', 'peanut', 'butter'), ())
globals()["match_esha_12305"] = CONTRACTS["12305"]
CONTRACTS["12357"] = _make_frozen_dessert_contract("12357", 'Frozen Dessert, butter pecan, non dairy', ('frozen', 'dessert', 'butter', 'pecan'), ())
globals()["match_esha_12357"] = CONTRACTS["12357"]
CONTRACTS["12363"] = _make_frozen_dessert_contract("12363", 'Frozen Dessert, chocolate peanut butter, dairy free', ('frozen', 'dessert', 'chocolate', 'peanut', 'butter'), ())
globals()["match_esha_12363"] = CONTRACTS["12363"]
CONTRACTS["12380"] = _make_frozen_dessert_contract("12380", 'Frozen Dessert, peanut butter zig zag, dairy free', ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_12380"] = CONTRACTS["12380"]
CONTRACTS["12393"] = _make_frozen_dessert_contract("12393", 'Frozen Dessert, butter pecan, dairy free', ('frozen', 'dessert', 'butter', 'pecan'), ())
globals()["match_esha_12393"] = CONTRACTS["12393"]
CONTRACTS["12400"] = _make_frozen_dessert_contract("12400", 'Frozen Dessert, peanut butter, dairy free', ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_12400"] = CONTRACTS["12400"]
CONTRACTS["19375"] = _make_frozen_dessert_contract("19375", "Frozen Dessert, 31 Below, Reese's peanut butter cup, small", ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_19375"] = CONTRACTS["19375"]
CONTRACTS["19376"] = _make_frozen_dessert_contract("19376", "Frozen Dessert, 31 Below, Reese's peanut butter cup, medium", ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_19376"] = CONTRACTS["19376"]
CONTRACTS["19377"] = _make_frozen_dessert_contract("19377", "Frozen Dessert, 31 Below, Reese's peanut butter cup, large", ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_19377"] = CONTRACTS["19377"]
CONTRACTS["19439"] = _make_frozen_dessert_contract("19439", "Frozen Dessert, sundae, Reese's peanut butter cup", ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_19439"] = CONTRACTS["19439"]
CONTRACTS["35451"] = _make_frozen_dessert_contract("35451", 'Frozen Dessert, Blizzard, peanut butter Butterfinger, small', ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_35451"] = CONTRACTS["35451"]
CONTRACTS["35452"] = _make_frozen_dessert_contract("35452", 'Frozen Dessert, Blizzard, peanut butter Butterfinger, medium', ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_35452"] = CONTRACTS["35452"]
CONTRACTS["35453"] = _make_frozen_dessert_contract("35453", 'Frozen Dessert, Blizzard, peanut butter Butterfinger, large', ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_35453"] = CONTRACTS["35453"]
CONTRACTS["35456"] = _make_frozen_dessert_contract("35456", "Frozen Dessert, Blizzard, Reese's peanut butter cups, large", ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_35456"] = CONTRACTS["35456"]
CONTRACTS["35661"] = _make_frozen_dessert_contract("35661", "Frozen Dessert, Blizzard, Reese's peanut butter cups, mini", ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_35661"] = CONTRACTS["35661"]
CONTRACTS["43959"] = _make_frozen_dessert_contract("43959", "Frozen Dessert, Blendrrr, Reese's peanut butter fudge, small", ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_43959"] = CONTRACTS["43959"]
CONTRACTS["43960"] = _make_frozen_dessert_contract("43960", "Frozen Dessert, Blendrrr, Reese's peanut butter fudge, medium", ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_43960"] = CONTRACTS["43960"]
CONTRACTS["43961"] = _make_frozen_dessert_contract("43961", "Frozen Dessert, Blendrrr, Reese's peanut butter fudge, large", ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_43961"] = CONTRACTS["43961"]
CONTRACTS["52264"] = _make_frozen_dessert_contract("52264", "Frozen Dessert, 31 Below, Reese's peanut butter cup, mini", ('frozen', 'dessert', 'peanut', 'butter'), ())
globals()["match_esha_52264"] = CONTRACTS["52264"]

# cereal
CONTRACTS["40034"] = _make_cereal_contract("40034", "Cereal, Cap'n Crunch, peanut butter", ('cereal', 'peanut', 'butter'), ())
globals()["match_esha_40034"] = CONTRACTS["40034"]
CONTRACTS["40343"] = _make_cereal_contract("40343", "Cereal, Reese's Peanut Butter Puffs", ('cereal', 'peanut', 'butter'), ())
globals()["match_esha_40343"] = CONTRACTS["40343"]
CONTRACTS["60925"] = _make_cereal_contract("60925", 'Cereal, Peanut Butter Bumpers', ('cereal', 'peanut', 'butter'), ())
globals()["match_esha_60925"] = CONTRACTS["60925"]
CONTRACTS["61495"] = _make_cereal_contract("61495", 'Cereal, Puffins, peanut butter', ('cereal', 'peanut', 'butter'), ())
globals()["match_esha_61495"] = CONTRACTS["61495"]

# sandwich
CONTRACTS["18900"] = _make_sandwich_contract("18900", "Sandwich, peanut butter jelly, with french bread, kids'", ('sandwich', 'peanut', 'butter', 'jelly'), ())
globals()["match_esha_18900"] = CONTRACTS["18900"]
CONTRACTS["81144"] = _make_sandwich_contract("81144", 'Sandwich, peanut butter & jelly, grape, with o crust', ('sandwich', 'peanut', 'butter', 'jelly'), ())
globals()["match_esha_81144"] = CONTRACTS["81144"]
CONTRACTS["81145"] = _make_sandwich_contract("81145", 'Sandwich, peanut butter & jelly, strawberry, with o crust', ('sandwich', 'peanut', 'butter', 'jelly'), ())
globals()["match_esha_81145"] = CONTRACTS["81145"]

# topping
CONTRACTS["23380"] = _make_topping_contract("23380", 'Topping, peanut butter fudge, fruit sweetened', ('topping', 'peanut', 'butter'), ())
globals()["match_esha_23380"] = CONTRACTS["23380"]
CONTRACTS["35490"] = _make_topping_contract("35490", 'Topping, dessert, peanut butter', ('topping', 'peanut', 'butter'), ())
globals()["match_esha_35490"] = CONTRACTS["35490"]
CONTRACTS["49681"] = _make_topping_contract("49681", "Topping, dessert, Reese's peanut butter cup", ('topping', 'peanut', 'butter'), ())
globals()["match_esha_49681"] = CONTRACTS["49681"]
CONTRACTS["54280"] = _make_topping_contract("54280", 'Topping, peanut butter, hard', ('topping', 'peanut', 'butter'), ())
globals()["match_esha_54280"] = CONTRACTS["54280"]
CONTRACTS["54330"] = _make_topping_contract("54330", 'Topping, peanut butter, ready to use, FS', ('topping', 'peanut', 'butter'), ())
globals()["match_esha_54330"] = CONTRACTS["54330"]
CONTRACTS["92532"] = _make_topping_contract("92532", 'Topping, dessert, peanut butter and chocolate sprinkles', ('topping', 'peanut', 'butter'), ())
globals()["match_esha_92532"] = CONTRACTS["92532"]

# snack
CONTRACTS["14251"] = _make_snack_contract("14251", 'Rice Cake, peanut butter chocolate chip', ('rice', 'cake', 'peanut', 'butter'), ())
globals()["match_esha_14251"] = CONTRACTS["14251"]
CONTRACTS["24667"] = _make_snack_contract("24667", 'Tart, peanut butter cream, mini', ('tart', 'peanut', 'butter'), ())
globals()["match_esha_24667"] = CONTRACTS["24667"]
CONTRACTS["49494"] = _make_snack_contract("49494", 'Cupcake, dark chocolate, with peanut butter filling', ('cupcake', 'chocolate', 'peanut', 'butter'), ())
globals()["match_esha_49494"] = CONTRACTS["49494"]
CONTRACTS["93001"] = _make_snack_contract("93001", 'Dessert, peanut butter cup, bar, no bake, dry mix, serving', ('dessert', 'peanut', 'butter'), ())
globals()["match_esha_93001"] = CONTRACTS["93001"]

# beverage
CONTRACTS["24233"] = _make_beverage_contract("24233", 'Blended Coffee, chocolate peanut butter, dry mix, FS', ('coffee', 'chocolate', 'peanut', 'butter'), ())
globals()["match_esha_24233"] = CONTRACTS["24233"]
CONTRACTS["46606"] = _make_beverage_contract("46606", "Smoothie, Peanut Butter Moo'd, small", ('smoothie', 'peanut', 'butter'), ())
globals()["match_esha_46606"] = CONTRACTS["46606"]
CONTRACTS["81275"] = _make_beverage_contract("81275", "Smoothie, Peanut Butter Moo'd, medium", ('smoothie', 'peanut', 'butter'), ())
globals()["match_esha_81275"] = CONTRACTS["81275"]

# baking_chip
CONTRACTS["18296"] = _make_baking_contract("18296", 'Baking Chips, peanut butter & milk chocolate morsels', ('baking', 'chip', 'peanut', 'butter'), ())
globals()["match_esha_18296"] = CONTRACTS["18296"]

# formula
CONTRACTS["4342"] = _make_formula_contract("4342", 'Formula, Ensure Plus, butter pecan, ready to use', ('formula', 'ensure', 'butter', 'pecan'), ())
globals()["match_esha_04342"] = CONTRACTS["4342"]
CONTRACTS["29428"] = _make_formula_contract("29428", 'Formula, TwoCal HN, butter pecan, ready to use', ('formula', 'twocal', 'butter', 'pecan'), ())
globals()["match_esha_29428"] = CONTRACTS["29428"]
CONTRACTS["29433"] = _make_formula_contract("29433", 'Formula, Nepro, butter pecan, with Carb Steady, ready to drink', ('formula', 'nepro', 'butter', 'pecan'), ())
globals()["match_esha_29433"] = CONTRACTS["29433"]

# butter_beans
CONTRACTS["12970"] = _make_bean_contract("12970", 'Beans, butter, mature, speckled, frozen', ('bean', 'butter'), ())
globals()["match_esha_12970"] = CONTRACTS["12970"]
CONTRACTS["7823"] = _make_bean_contract("7823", 'Beans, butter, canned', ('bean', 'butter'), ())
globals()["match_esha_07823"] = CONTRACTS["7823"]
CONTRACTS["12959"] = _make_bean_contract("12959", 'Beans, butter, mature, frozen', ('bean', 'butter'), ())
globals()["match_esha_12959"] = CONTRACTS["12959"]

# margarine_oil
CONTRACTS["8135"] = _make_margarine_contract("8135", 'Margarine & Butter, blend, with soybean oil', ('margarine', 'butter'), ())
globals()["match_esha_08135"] = CONTRACTS["8135"]
CONTRACTS["37591"] = _make_margarine_contract("37591", 'Oil, popcorn, soybean, butter', ('oil', 'soybean', 'butter'), ())
globals()["match_esha_37591"] = CONTRACTS["37591"]
CONTRACTS["44770"] = _make_margarine_contract("44770", 'Oil, soybean, partially hydrogenated, industrial, non dairy butter flavor', ('oil', 'soybean', 'butter'), ())
globals()["match_esha_44770"] = CONTRACTS["44770"]
CONTRACTS["44912"] = _make_margarine_contract("44912", 'Cooking Spray, soybean, butter, 1/3 sec spray', ('cooking', 'spray', 'soybean', 'butter'), ())
globals()["match_esha_44912"] = CONTRACTS["44912"]

# pumpkin_butter
CONTRACTS["49309"] = _make_spread_contract_other("49309", 'Spread, pumpkin butter', ('pumpkin', 'butter'), ())
globals()["match_esha_49309"] = CONTRACTS["49309"]

# meal_dish
CONTRACTS["6345"] = _make_meal_contract("6345", 'Vegetable Dish, baby lima bean, with butter sce, low fat, frozen', ('vegetable', 'lima', 'bean', 'butter'), ())
globals()["match_esha_06345"] = CONTRACTS["6345"]
CONTRACTS["9266"] = _make_meal_contract("9266", 'Dish, edamame soybeans, with carrots & herb butter sauce', ('dish', 'edamame', 'soybean', 'butter'), ())
globals()["match_esha_09266"] = CONTRACTS["9266"]
CONTRACTS["49363"] = _make_meal_contract("49363", 'Meal, fish, sole, filet, with butter beans & spinach, frozen', ('meal', 'fish', 'butter', 'bean'), ())
globals()["match_esha_49363"] = CONTRACTS["49363"]

# creamer
CONTRACTS["54242"] = _make_creamer_contract("54242", 'Cream Substitute, butter pecan', ('cream', 'butter', 'pecan'), ())
globals()["match_esha_54242"] = CONTRACTS["54242"]
