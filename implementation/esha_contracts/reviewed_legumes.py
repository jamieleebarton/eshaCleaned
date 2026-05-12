from __future__ import annotations

from .contract_base import ContractFn, MatchDecision, ProductFacts, accept, reject


BEAN_CATEGORY_TERMS = (
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

PREPARED_EXCLUDES = (
    "baked",
    "refried",
    "soup",
    "chili",
    "stew",
    "salad",
    "rice",
    "burrito",
    "wrap",
    "taco",
    "fajita",
    "dip",
    "hummus",
    "casserole",
    "meal",
    "dinner",
    "entree",
    "sauce",
    "snack",
    "chip",
    "coffee",
    "espresso",
)

BLEND_EXCLUDES = ("tri", "three", "blend", "mixed", "medley", "mix")

BEAN_SPECIES = (
    "black",
    "pinto",
    "kidney",
    "lima",
    "navy",
    "garbanzo",
    "chickpea",
    "red",
    "white",
    "green",
    "wax",
    "snap",
    "string",
)


def category_ok(product: ProductFacts) -> bool:
    return product.category_has_any(*BEAN_CATEGORY_TERMS)


def beanish(product: ProductFacts) -> bool:
    return product.has_any("bean", "beans", "chickpea", "chickpeas", "garbanzo", "garbanzos")


def has_any_species(product: ProductFacts, species: tuple[str, ...]) -> bool:
    return product.has_any(*species)


def rejection_terms(product: ProductFacts, allowed_species: tuple[str, ...], extra_excludes: tuple[str, ...]) -> list[str]:
    excluded = []
    allowed = set(allowed_species)
    for term in PREPARED_EXCLUDES + BLEND_EXCLUDES + extra_excludes:
        if product.has_any(term) and term not in allowed:
            excluded.append(term)
    for species in BEAN_SPECIES:
        if species not in allowed and product.has_any(species):
            excluded.append(species)
    return sorted(set(excluded))


def modifier_rejection(product: ProductFacts, esha_description: str) -> str:
    desc = esha_description.lower()
    if "unsalted" in desc and not (
        product.has_any("unsalted") or product.has_phrase("no salt") or product.has_phrase("no salt added")
    ):
        return "missing unsalted/no-salt cue"
    if ("low sodium" in desc or "less salt" in desc or "reduced sodium" in desc) and not (
        product.has_phrase("low sodium")
        or product.has_phrase("reduced sodium")
        or product.has_phrase("less salt")
        or product.has_phrase("50% less salt")
        or product.has_phrase("50 percent less salt")
    ):
        return "missing low/reduced sodium cue"
    if "spicy" in desc and not product.has_any("spicy", "jalapeno", "chile", "chili", "pepper", "peppers"):
        return "missing spicy/jalapeno/pepper cue"
    if "jalapeno" in desc and not product.has_any("jalapeno"):
        return "missing jalapeno cue"
    if "green chile" in desc and not product.has_any("chile", "chili"):
        return "missing chile cue"
    if "salsa" in desc and not product.has_any("salsa"):
        return "missing salsa cue"
    if ("frozen" in desc or "fzn" in desc) and not (product.has_any("frozen") or product.category_has_any("frozen")):
        return "missing frozen cue"
    if "baby" in desc and not product.has_any("baby"):
        return "missing baby cue"
    if "large" in desc and not product.has_any("large"):
        return "missing large cue"
    if "small" in desc and not product.has_any("small"):
        return "missing small cue"
    if "fordhook" in desc and not product.has_any("fordhook"):
        return "missing fordhook cue"
    if "lima, green" in desc and not product.has_any("green"):
        return "missing green lima cue"
    return ""


def make_species_contract(
    esha_code: str,
    esha_description: str,
    species: tuple[str, ...],
    required_terms: tuple[str, ...] = (),
    extra_excludes: tuple[str, ...] = (),
    allow_refried: bool = False,
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not category_ok(product):
            return reject(f"{esha_code} category mismatch")
        if not beanish(product):
            return reject(f"{esha_code} missing bean/chickpea cue")
        if not has_any_species(product, species):
            return reject(f"{esha_code} missing species cue: " + "|".join(species))
        missing = [term for term in required_terms if not product.has_any(term)]
        if missing:
            return reject(f"{esha_code} missing required term(s): " + "|".join(missing))
        modifier_error = modifier_rejection(product, esha_description)
        if modifier_error:
            return reject(f"{esha_code} {modifier_error}")
        excludes = tuple(term for term in extra_excludes if term != "refried") if allow_refried else extra_excludes
        rejected = rejection_terms(product, species, excludes)
        if allow_refried:
            rejected = [term for term in rejected if term != "refried"]
        if rejected:
            return reject(f"{esha_code} excluded term(s): " + "|".join(rejected))
        return accept(f"{esha_code} reviewed legume contract accepted")

    return contract


def make_refried_contract(
    esha_code: str,
    esha_description: str,
    species: tuple[str, ...] = (),
    required_terms: tuple[str, ...] = (),
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        if not category_ok(product):
            return reject(f"{esha_code} category mismatch")
        if not beanish(product):
            return reject(f"{esha_code} missing bean cue")
        if not product.has_any("refried"):
            return reject(f"{esha_code} missing refried cue")
        if species and not has_any_species(product, species):
            return reject(f"{esha_code} missing species cue: " + "|".join(species))
        missing = [term for term in required_terms if not product.has_any(term)]
        if missing:
            return reject(f"{esha_code} missing required term(s): " + "|".join(missing))
        modifier_error = modifier_rejection(product, esha_description)
        if modifier_error:
            return reject(f"{esha_code} {modifier_error}")
        rejected = []
        for term in ("baked", "soup", "chili", "stew", "salad", "rice", "burrito", "wrap", "taco", "fajita", "dip", "hummus", "snack", "chip", "coffee", "espresso"):
            if product.has_any(term):
                rejected.append(term)
        if species:
            allowed = set(species)
            for other in BEAN_SPECIES:
                if other not in allowed and product.has_any(other):
                    rejected.append(other)
        if rejected:
            return reject(f"{esha_code} excluded term(s): " + "|".join(sorted(set(rejected))))
        return accept(f"{esha_code} reviewed refried bean contract accepted")

    return contract


BLACK_BEAN_CODES = {
    "9729": "Beans, black, unsalted, fat free, canned",
    "9730": "Beans, black, caribbean, canned",
    "13477": "Beans, black",
    "7012": "Beans, black, mature, cooked",
    "7041": "Beans, black turtle, mature, cooked",
    "7042": "Beans, black turtle, mature, canned",
    "7114": "Beans, black, mature",
    "7115": "Beans, black turtle, mature",
    "7168": "Beans, black, canned",
    "7826": "Beans, black, Sun Vista, canned",
    "7835": "Beans, black, 50% less salt, canned",
    "9099": "Beans, black, whole, canned",
    "90001": "Beans, black, mature, cooked with salt",
}

FERMENTED_BLACK_BEAN_CODES = {
    "7098": "Beans, black, fermented, Szechuan, INTL",
    "7099": "Beans, black, fermented, Fujian province, INTL",
    "7100": "Beans, black, fermented, Hunan province, INTL",
    "7101": "Beans, black, fermented, Hebei province, INTL",
}

PINTO_BEAN_CODES = {
    "5730": "Beans, pinto, immature, frozen, 10oz package",
    "5731": "Beans, pinto, immature, cooked from fzn, drained, 10oz package",
    "7448": "Beans, pinto, unsalted, fat free, canned",
    "7453": "Beans, pinto, spicy, with jalapeno & red pepper, fat free, canned",
    "13479": "Beans, pinto, whole",
    "7013": "Beans, pinto, mature, cooked",
    "7051": "Beans, pinto, mature, canned",
    "7124": "Beans, pinto, mature",
    "7822": "Beans, pinto, Sun Vista, canned",
    "15350": "Beans, pinto, mature, USDA Commodity",
    "36265": "Beans, pinto, low sodium, canned, FS",
    "38946": "Beans, pinto, canned, drained",
    "39176": "Beans, pinto, canned, drained, rinsed",
    "45828": "Beans, pinto, premium, canned",
    "48998": "Beans, pinto, with sea salt, canned",
    "5854": "Beans, pinto, immature, cooked from fzn with salt, drained, 10oz package",
    "90012": "Beans, pinto, mature, cooked with salt",
}

KIDNEY_BEAN_CODES = {
    "7446": "Beans, kidney, unsalted, fat free, canned",
    "7007": "Beans, kidney, red, mature",
    "7008": "Beans, kidney, all types, mature, cooked",
    "7046": "Beans, kidney, red, California, mature, cooked",
    "7047": "Beans, kidney, red, mature, cooked",
    "7049": "Beans, kidney, royal red, mature, cooked",
    "7087": "Beans, kidney, all types, mature, canned",
    "7092": "Beans, kidney, all types, mature",
    "7119": "Beans, kidney, red, California, mature",
    "7120": "Beans, kidney, royal red, mature",
    "7173": "Beans, kidney, red, canned",
    "7292": "Beans, kidney, red, mature, canned",
    "9261": "Beans, kidney, dark red, canned",
    "9374": "Beans, kidney, canned",
    "15348": "Beans, kidney, all types, mature, canned, USDA Commodity",
    "38878": "Beans, kidney, red, canned, drained, rinsed",
    "38945": "Beans, kidney, red, canned, drained",
    "48617": "Beans, kidney, dark, canned",
    "90006": "Beans, kidney, all types, mature, cooked with salt",
    "90007": "Beans, kidney, red, California, mature, cooked with salt",
    "90008": "Beans, kidney, red, mature, cooked with salt",
    "90009": "Beans, kidney, royal red, mature, cooked with salt",
}

WHITE_KIDNEY_BEAN_CODES = {
    "9732": "Beans, white kidney, unsalted, canned",
    "17741": "Beans, white kidney, canned",
}

RED_BEAN_CODES = {
    "9735": "Beans, red, small, unsalted, canned",
    "9377": "Beans, red, canned",
    "9768": "Beans, red, small, mature",
}

WHITE_BEAN_CODES = {
    "7002": "Beans, white, small, mature",
    "7003": "Beans, white, small, mature, cooked",
    "7053": "Beans, white, mature, cooked",
    "7054": "Beans, white, mature, canned",
    "7126": "Beans, white, mature",
    "7838": "Beans, white, small, canned",
    "90013": "Beans, white, small, mature, cooked with salt",
    "90015": "Beans, white, mature, cooked with salt",
}

NAVY_BEAN_CODES = {
    "7447": "Beans, navy, unsalted, canned",
    "7022": "Beans, navy, mature, cooked",
    "7121": "Beans, navy, mature",
    "7122": "Beans, navy, mature, canned",
    "15349": "Beans, navy, mature, USDA Commodity",
    "90010": "Beans, navy, mature, cooked with salt",
}

GARBANZO_CODES = {
    "7445": "Beans, garbanzo, unsalted, canned",
    "7381": "Beans, garbanzo, dried",
    "9766": "Beans, garbanzo, mature, dry",
    "9984": "Beans, garbanzo, canned",
    "9989": "Beans, garbanzo, mature, cooked with salt",
    "9991": "Beans, garbanzo, mature",
    "9992": "Beans, garbanzo, mature, canned",
    "9993": "Beans, garbanzo, mature, cooked",
    "37815": "Beans, chickpea, unsalted, canned",
    "38883": "Beans, garbanzo, mature, canned, drained",
    "38887": "Beans, chickpea, mature, canned, drained, rinsed",
    "46912": "Beans, garbanzo, frozen",
}

LIMA_BEAN_CODES = {
    "701": "Beans, lima, baby, frozen, FS",
    "5726": "Beans, lima, fordhook, immature, frozen",
    "5727": "Beans, lima, baby, immature, frozen, 10 ounce package",
    "9734": "Beans, lima, baby, unsalted, canned",
    "5019": "Beans, lima, baby, immature, cooked from fzn, drained",
    "5247": "Beans, lima, fordhook, immature, cooked from fzn, drained",
    "5319": "Beans, lima, immature, cooked, drained",
    "5527": "Beans, lima, immature, unsalted, canned, with liquid",
    "5570": "Beans, lima, immature, canned, with liquid",
    "5680": "Beans, lima, immature",
    "5849": "Beans, lima, immature, cooked with salt, drained",
    "5850": "Beans, lima, baby, immature, cooked from fzn with salt, drained",
    "5851": "Beans, lima, fordhook, immature, cooked from fzn with salt, drained",
    "6222": "Beans, lima, baby, frozen",
    "6223": "Beans, lima, fordhook, frozen",
    "6744": "Beans, lima, fordhook, immature, frozen, 10oz package",
    "6745": "Beans, lima, large, immature, cooked from fzn, drained 10 ounce package",
    "6747": "Beans, lima, baby, immature, cooked from fzn, drained, 10oz package",
    "7009": "Beans, lima, baby, mature",
    "7010": "Beans, lima, large, mature, cooked",
    "7011": "Beans, lima, large, mature, canned",
    "7025": "Beans, lima, large, mature",
    "7058": "Beans, lima, baby, mature, cooked",
    "12957": "Beans, lima, petite, frozen",
    "15785": "Beans, lima, baby, immature, frozen",
    "16554": "Beans, lima, baby, microwaved, frozen",
    "26893": "Beans, lima, fordhook, immature, cooked from fzn with salt, drained,10oz",
    "51043": "Beans, lima, green, canned",
    "90545": "Beans, lima, baby, immature, cooked from fzn with salt, drained 10oz package",
    "90020": "Beans, lima, large, mature, cooked with salt",
    "90021": "Beans, lima, baby, mature, cooked with salt",
}

REFRIED_BLACK_CODES = {
    "9736": "Refried Beans, black, canned",
    "9737": "Refried Beans, spicy black, canned",
    "9738": "Refried Beans, black soy & black, canned",
    "7103": "Refried Beans, black, low fat, instant, serving",
    "41763": "Refried Beans, black, low fat, canned",
    "48992": "Beans, black, refried, with jalapeno peppers, canned",
}

REFRIED_KIDNEY_CODES = {
    "9739": "Refried Beans, kidney, canned",
}

REFRIED_RED_CODES = {
    "16950": "Beans, red, refried, canned",
}

REFRIED_GENERIC_CODES = {
    "7486": "Refried Beans, with cheese",
    "13478": "Refried Beans",
    "7024": "Refried Beans, canned",
    "7064": "Refried Beans, with jalapeno, low fat, instant, serving",
    "7179": "Refried Beans, fat free, canned",
    "7180": "Refried Beans, traditional, canned",
    "7182": "Refried Beans, with green chiles, canned",
    "7184": "Refried Beans, spicy, fat free, canned",
    "7185": "Refried Beans, vegetarian, canned",
    "7820": "Refried Beans, International Dish, instant",
    "9095": "Refried Beans, spicy jalapeno, canned",
    "9096": "Refried Beans, original, canned, FS",
    "9097": "Refried Beans, vegetarian, canned, FS",
    "9098": "Refried Beans, no fat, canned",
    "14922": "Refried Beans, salsa, canned",
    "15351": "Refried Beans, canned, USDA Commodity",
    "48999": "Refried Beans, traditional style, fat free, canned",
    "49561": "Refried Beans, refritos",
    "53659": "Refried Beans, with chile & lime flavor, low fat, instant, serving",
    "72632": "Refried Beans, with o cheese",
    "90854": "Refried Beans, vegetarian blend",
}


CONTRACTS: dict[str, ContractFn] = {}

for _code, _description in BLACK_BEAN_CODES.items():
    CONTRACTS[_code] = make_species_contract(_code, _description, ("black",), extra_excludes=("soy",))
for _code, _description in FERMENTED_BLACK_BEAN_CODES.items():
    CONTRACTS[_code] = make_species_contract(_code, _description, ("black",), required_terms=("fermented",), extra_excludes=("soy",))
for _code, _description in PINTO_BEAN_CODES.items():
    CONTRACTS[_code] = make_species_contract(_code, _description, ("pinto",))
for _code, _description in KIDNEY_BEAN_CODES.items():
    CONTRACTS[_code] = make_species_contract(_code, _description, ("kidney", "red"), required_terms=("kidney",), extra_excludes=("white",))
for _code, _description in WHITE_KIDNEY_BEAN_CODES.items():
    CONTRACTS[_code] = make_species_contract(_code, _description, ("kidney", "white"), required_terms=("kidney", "white"))
for _code, _description in RED_BEAN_CODES.items():
    CONTRACTS[_code] = make_species_contract(_code, _description, ("red",), extra_excludes=("kidney",))
for _code, _description in WHITE_BEAN_CODES.items():
    CONTRACTS[_code] = make_species_contract(_code, _description, ("white",), extra_excludes=("kidney",))
for _code, _description in NAVY_BEAN_CODES.items():
    CONTRACTS[_code] = make_species_contract(_code, _description, ("navy",))
for _code, _description in GARBANZO_CODES.items():
    CONTRACTS[_code] = make_species_contract(_code, _description, ("garbanzo", "chickpea"))
for _code, _description in LIMA_BEAN_CODES.items():
    CONTRACTS[_code] = make_species_contract(_code, _description, ("lima",))
for _code, _description in REFRIED_BLACK_CODES.items():
    CONTRACTS[_code] = make_refried_contract(_code, _description, ("black",))
for _code, _description in REFRIED_KIDNEY_CODES.items():
    CONTRACTS[_code] = make_refried_contract(_code, _description, ("kidney",))
for _code, _description in REFRIED_RED_CODES.items():
    CONTRACTS[_code] = make_refried_contract(_code, _description, ("red",))
for _code, _description in REFRIED_GENERIC_CODES.items():
    CONTRACTS[_code] = make_refried_contract(_code, _description)
