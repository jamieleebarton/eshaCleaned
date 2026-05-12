#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CANONICAL_CSV = ROOT / "implementation" / "output" / "canonical_surface_normalized_with_product_proxies_CLEANED.csv"
ESHA_CSV = ROOT / "esha_cleaned.csv"
SR28_CSV = ROOT / "data" / "sr28_csv" / "food.csv"
FNDDS_CSV = ROOT / "data" / "fndds" / "MainFoodDesc16.csv"
CANONICAL_TO_ESHA_CSV = ROOT / "implementation" / "canonical_to_esha.csv"
ESHA_CANONICAL_CSV = ROOT / "esha_cleaned_canonical.csv"

ESHA_CLEAR_ONLY_CUES = (
    "bread dressing",
    "cajun rice dressing",
    "champagne",
    "chick fil a spicy",
    "citrus",
    "cucumber",
    "garlic",
    "lemon",
    "lime",
    "moroccan spiced",
    "nuoc cham",
    "oil and vinegar",
    "oil-and-vinegar",
    "sun dried tomato",
    "sun-dried tomato",
    "sundried tomato",
    "tangy lemon",
    "tomato",
    "vidalia onion",
    "vietnamese chili garlic",
    "wine vinegar",
)

WEAK_FNDDS_CODES = {"83100100", "83106000", "83112500"}
CARAMEL_CANDY_SURFACES = {
    "caramel candies",
    "caramel candy",
    "soft caramel candies",
    "soft caramel candy",
    "individually wrapped caramels",
}
CARAMEL_TOPPING_SURFACES = {
    "caramel sauce",
    "caramel dip",
}
FLAN_CONFECTION_SURFACE_FIXES = {
    "bubblegum": {"sr28": "168771", "esha": "23082"},
    "cajeta": {"sr28": "168841", "esha": "15686"},
    "caramel apple dip": {"sr28": "168841", "esha": "91634"},
    "caramel bit": {"sr28": "167974", "esha": "23015"},
    "caramel coloring": {"sr28": "169655", "esha": "25068"},
    "caramel filling": {"sr28": "168841", "esha": "15686"},
    "caramel flavored bits": {"sr28": "167974", "esha": "23015"},
    "caramel flavored topping": {"sr28": "168841", "esha": "23070"},
    "caramel squares": {"sr28": "167974", "esha": "23015"},
    "chocolate truffle": {"sr28": "169580", "esha": "93432"},
    "classic caramel": {"sr28": "168841", "esha": "31729"},
    "ferrero raffaello chocolate truffles": {"sr28": "169580", "esha": "93432"},
    "ferrero rocher hazelnut truffles": {"sr28": "169580", "esha": "93432"},
    "fresh truffles": {"sr28": "169580", "esha": "93432"},
    "gianduja": {"sr28": "169580", "esha": "93432"},
    "golf ball sized truffle": {"sr28": "169580", "esha": "93432"},
    "lindt lindor truffle": {"sr28": "169580", "esha": "93432"},
    "liquid caramel": {"sr28": "168841", "esha": "15613"},
    "salted caramel": {"sr28": "167974", "esha": "23015"},
    "soft caramel": {"sr28": "167974", "esha": "92971"},
    "starbucks frappuccino caramel coffee drink": {"sr28": "171880", "esha": "14166"},
    "tic tacs": {"sr28": "167990", "esha": "23225"},
    "truffle pulp": {"sr28": "169580", "esha": "93432"},
    "truffle shavings": {"sr28": "169580", "esha": "93432"},
    "tutti frutti": {"sr28": "167989", "esha": "23029"},
    "vanilla caramel": {"sr28": "168841", "esha": "15613"},
}
ICE_CREAM_BUCKET_SURFACE_FIXES = {
    "butterscotch caramel ice cream topping": {
        "sr28": "168841",
        "fndds": "91304010",
        "esha": "54304",
    },
    "caramel ice cream topping": {
        "sr28": "168841",
        "fndds": "91304010",
        "esha": "23070",
    },
    "frosty": {
        "esha": "2176",
    },
    "hot caramel ice cream topping": {
        "sr28": "168841",
        "fndds": "91304010",
        "esha": "23070",
    },
    "ice cream waffle bowls": {
        "sr28": "175000",
        "esha": "62443",
    },
    "magic shell ice cream topping": {
        "sr28": "168835",
        "esha": "54277",
    },
    "marshmallow ice cream topping warmed slightly": {
        "sr28": "169664",
        "fndds": "91304040",
        "esha": "23071",
    },
    "milky way ice cream topping": {
        "sr28": "168835",
        "esha": "23014",
    },
    "smucker s butterscotch ice cream topping": {
        "sr28": "168841",
        "fndds": "91304010",
        "esha": "23069",
    },
}
ICE_CREAM_CLEAR_SURFACES = {
    "ice cream sticks": "non_food_accessory_manual_review",
    "ice cream topping": "generic_ice_cream_topping_manual_review",
}
ICE_CREAM_EXACT_ESHA_SURFACE_FIXES = {
    "butter pecan ice cream": "2389",
    "coffee ice cream": "72376",
    "dulce de leche ice cream": "2732",
    "eggnog ice cream": "72851",
    "french vanilla ice cream": "72854",
    "low fat vanilla ice cream": "2009",
    "neapolitan ice cream": "492",
    "premium vanilla ice cream": "2006",
    "sugar free vanilla ice cream": "52151",
    "vanilla low fat ice cream": "2009",
}
FRUIT_VARIANT_SURFACE_FIXES = {
    "raspberry sherbet": {
        "fndds": "13150000",
    },
    "raspberry sorbet": {
        "fndds": "63430100",
        "esha": "72793",
    },
    "raspberry syrup": {
        "sr28": "169578",
        "esha": "15605",
    },
    "raspberry topping": {
        "esha": "35495",
    },
    "tamarind juice": {
        "sr28": "167786",
        "fndds": "92510650",
        "esha": "21133",
    },
    "watermelon pulp": {
        "sr28": "167765",
        "fndds": "63149010",
        "esha": "27373",
    },
    "watermelon sorbet": {
        "fndds": "63430100",
        "esha": "49765",
    },
    "watermelon syrup": {
        "sr28": "169578",
        "esha": "15634",
    },
    "watermelon wedges": {
        "sr28": "167765",
        "fndds": "63149010",
        "esha": "3860",
    },
}
FRUIT_CLEAR_SURFACES = {
    "gingered watermelon rind": "fruit_rind_manual_review",
    "raspberry leaf": "botanical_leaf_manual_review",
    "raspberry liquid": "ambiguous_raspberry_liquid_manual_review",
    "watermelon rind": "fruit_rind_manual_review",
}
SYRUP_JUICE_SORBET_TOPPING_FIXES = {
    "barley malt syrup": {
        "sr28": "169578",
        "esha": "25204",
    },
    "blueberry cranberry juice": {
        "fndds": "64100200",
        "esha": "4944",
    },
    "blueberry topping": {
        "fndds": "91361020",
        "esha": "35472",
    },
    "brown rice syrup": {
        "sr28": "169578",
    },
    "coffee flavored syrup": {
        "sr28": "169578",
        "esha": "31745",
    },
    "coffee syrup": {
        "sr28": "169578",
        "esha": "15627",
    },
    "cola syrup": {
        "sr28": "169578",
    },
    "cranberry syrup": {
        "sr28": "169578",
    },
    "fruit topping": {
        "fndds": "91361020",
    },
    "fudge topping": {
        "fndds": "91304020",
        "esha": "8681",
    },
    "hot fudge topping": {
        "fndds": "91304020",
        "esha": "54289",
    },
    "lemon juiced": {
        "fndds": "61204010",
        "esha": "3068",
    },
    "lemon sorbet": {
        "fndds": "63430110",
        "esha": "19318",
    },
    "lime juiced": {
        "fndds": "61207010",
        "esha": "3072",
    },
    "lychee syrup": {
        "sr28": "169578",
    },
    "maraschino cherry syrup": {
        "sr28": "169578",
        "esha": "31736",
    },
    "mango sorbet": {
        "fndds": "63430100",
        "esha": "307",
    },
    "monin red passion fruit syrup": {
        "sr28": "169578",
        "esha": "31779",
    },
    "passionfruit syrup": {
        "sr28": "169578",
        "esha": "31779",
    },
    "pineapple sorbet": {
        "fndds": "63430100",
        "esha": "49763",
    },
    "smucker s chocolate flavored ice cream topping": {
        "fndds": "91304020",
        "esha": "23212",
    },
    "sorbet": {
        "fndds": "63430100",
    },
    "strawberry ice cream topping": {
        "fndds": "91361020",
        "esha": "35498",
    },
    "vanilla coffee syrup": {
        "sr28": "169578",
        "esha": "31745",
    },
    "watermelon juice": {
        "fndds": "64133100",
    },
    "yuzu juice": {
        "fndds": "61207000",
    },
    "chocolate ice cream topping": {
        "fndds": "91304020",
        "esha": "23212",
    },
    "chocolate peanut butter ice cream topping": {
        "fndds": "91304020",
        "esha": "23212",
    },
}
SAUCE_FAMILY_FIXES = {
    "abalone sauce": {
        "fndds": "27150200",
        "esha": "53473",
    },
    "caribbean habanero hot sauce": {
        "fndds": "75511010",
        "esha": "21452",
    },
    "chicken wing sauce": {
        "fndds": "75511010",
        "esha": "21452",
    },
    "el yucateco chile habanero sauce": {
        "fndds": "75511010",
        "esha": "21452",
    },
    "habanero hot sauce": {
        "fndds": "75511010",
        "esha": "21452",
    },
    "habanero pepper sauce": {
        "fndds": "75511010",
        "esha": "21452",
    },
    "habanero sauce": {
        "fndds": "75511010",
        "esha": "21452",
    },
    "lawry s baja chipotle sauce with lime juice": {
        "fndds": "75511010",
        "esha": "33313",
    },
    "raspberry sauce": {
        "fndds": "91361020",
        "esha": "35495",
    },
    "spinach pesto sauce": {
        "fndds": "81302070",
        "esha": "33320",
    },
}
SAUCE_CLEAR_SURFACES = {
    "lamb sauce": "specialty_sauce_manual_review",
    "shrimp cocktail ring with sauce": "prepared_seafood_with_sauce_manual_review",
}
RELISH_FAMILY_FIXES = {
    "chile relish": {
        "fndds": "75515010",
        "esha": "52391",
    },
    "chili relish": {
        "fndds": "75515010",
        "esha": "52391",
    },
    "jalape o relish": {
        "fndds": "75515010",
        "esha": "52391",
    },
    "jalapeno relish": {
        "fndds": "75515010",
        "esha": "52391",
    },
    "mint relish": {
        "fndds": "63409020",
    },
    "mustard relish": {
        "fndds": "75515010",
        "esha": "52391",
    },
    "pepper relish": {
        "fndds": "75515010",
        "esha": "52391",
    },
    "red pepper relish": {
        "fndds": "75515010",
        "esha": "52391",
    },
    "relish sandwich spread": {
        "sr28": "171409",
        "fndds": "81302040",
        "esha": "9438",
    },
}
VINEGAR_FAMILY_FIXES = {
    "champagne vinegar": {
        "fndds": "64401000",
        "esha": "27082",
    },
    "jalape o vinegar": {
        "fndds": "64401000",
        "esha": "24880",
    },
    "pepper vinegar": {
        "fndds": "64401000",
        "esha": "35183",
    },
    "sherry vinegar": {
        "fndds": "64401000",
        "esha": "63267",
    },
    "sherry wine vinegar": {
        "fndds": "64401000",
        "esha": "63267",
    },
}
SHERBET_FAMILY_FIXES = {
    "lemon sherbet": {
        "fndds": "13150000",
    },
    "lime sherbet": {
        "fndds": "13150000",
    },
    "mixed fruit sherbet": {
        "fndds": "13150000",
    },
    "pineapple sherbet": {
        "fndds": "13150000",
    },
}
SPECIALTY_JUICE_CLEAR_SURFACES = {
    "habanero juice": "specialty_juice_manual_review",
    "lemongrass juice": "specialty_juice_manual_review",
}
PUDDING_MIX_FIXES = {
    "butterscotch flavored jello pudding mix": {
        "fndds": "13210280",
        "esha": "2750",
    },
    "chocolate jello pudding mix": {
        "sr28": "169603",
        "fndds": "13210220",
        "esha": "2635",
    },
}
YOGURT_FAMILY_FIXES = {
    "garlic yogurt dressing": {
        "fndds": "83115000",
    },
}
YOGURT_CLEAR_SURFACES = {
    "yogurt cheese": "specialty_yogurt_cheese_manual_review",
}
AVOCADO_SURFACE_FIXES = {
    "ripe haas avocado": {
        "sr28": "171706",
        "fndds": "63105010",
        "esha": "3210",
    },
    "ripe haas avocados": {
        "sr28": "171706",
        "fndds": "63105010",
        "esha": "3210",
    },
    "ripe hass avocado": {
        "sr28": "171706",
        "fndds": "63105010",
        "esha": "3210",
    },
    "ripe hass avocados": {
        "sr28": "171706",
        "fndds": "63105010",
        "esha": "3210",
    },
}
BABYFOOD_DESSERT_FIXES = {
    "banana cream pudding": {
        "esha": "2738",
    },
    "banana cream pudding mix": {
        "esha": "2749",
    },
    "cook and serve banana cream pudding": {
        "esha": "2749",
    },
    "instant banana cream pudding mix": {
        "esha": "2738",
    },
    "sugar free fat free banana cream pudding mix": {
        "esha": "58443",
    },
    "sugar free fat free instant banana cream pudding mix": {
        "esha": "58443",
    },
    "mango baby food": {
        "sr28": "171341",
        "esha": "23860",
    },
    "pear baby food": {
        "esha": "60097",
    },
}
CUSTARD_SURFACE_FIXES = {
    "american custard mix": {
        "sr28": "168772",
        "fndds": "13210300",
        "esha": "2795",
    },
    "cr me anglaise": {
        "fndds": "13210300",
        "esha": "2663",
    },
    "creme anglaise": {
        "fndds": "13210300",
        "esha": "2663",
    },
    "custard": {
        "fndds": "13210300",
        "esha": "2613",
    },
    "custard mix": {
        "sr28": "168772",
        "fndds": "13210300",
        "esha": "57893",
    },
    "custard powder": {
        "sr28": "168772",
        "fndds": "13210300",
        "esha": "57893",
    },
    "custard sauce": {
        "fndds": "13210300",
        "esha": "2663",
    },
    "vanilla custard": {
        "fndds": "13210300",
        "esha": "63155",
    },
    "vanilla custard powder": {
        "sr28": "168772",
        "fndds": "13210300",
        "esha": "2661",
    },
}
CHEESECAKE_YOGURT_FIXES = {
    "berry cheesecake yogurt": {
        "sr28": "170889",
        "fndds": "11430000",
        "esha": "72485",
    },
    "cheesecake yogurt": {
        "sr28": "170889",
        "fndds": "11430000",
        "esha": "72472",
    },
    "lemon cheesecake yogurt": {
        "sr28": "169898",
        "fndds": "11430000",
        "esha": "72508",
    },
}
CRACKER_SURFACE_FIXES = {
    "asian crackers": {
        "fndds": "54001000",
        "esha": "139",
    },
    "bear shaped graham crackers": {
        "sr28": "174957",
        "fndds": "54102015",
        "esha": "34639",
    },
    "butter crackers": {
        "sr28": "173258",
        "fndds": "54301030",
        "esha": "70963",
    },
    "buttery cracker": {
        "sr28": "173258",
        "fndds": "54301030",
        "esha": "70963",
    },
    "buttery round cracker": {
        "sr28": "173258",
        "fndds": "54301030",
        "esha": "70963",
    },
    "buttery round crackers": {
        "sr28": "173258",
        "fndds": "54301030",
        "esha": "70963",
    },
    "cheez it crackers": {
        "sr28": "174975",
        "fndds": "54304005",
        "esha": "53775",
    },
    "cheez it cracker": {
        "sr28": "174975",
        "fndds": "54304005",
        "esha": "53775",
    },
    "cheez-it crackers": {
        "sr28": "174975",
        "fndds": "54304005",
        "esha": "53775",
    },
    "cinnamon graham cracker": {
        "sr28": "174957",
        "fndds": "54102010",
        "esha": "36494",
    },
    "cinnamon graham crackers": {
        "sr28": "174957",
        "fndds": "54102010",
        "esha": "36494",
    },
    "club cracker": {
        "fndds": "54001000",
        "esha": "11717",
    },
    "club crackers": {
        "fndds": "54001000",
        "esha": "11717",
    },
    "crackers": {
        "fndds": "54001000",
        "esha": "139",
    },
    "deep dish graham cracker crust": {
        "sr28": "167520",
        "fndds": "53391100",
        "esha": "48475",
    },
    "double graham cracker": {
        "sr28": "174957",
        "fndds": "54102010",
        "esha": "43802",
    },
    "graham cracker tart shells": {
        "sr28": "167520",
        "fndds": "53391100",
        "esha": "62917",
    },
    "ginger crackers": {
        "fndds": "54001000",
        "esha": "139",
    },
    "graham cracker sheets": {
        "sr28": "174957",
        "fndds": "54102010",
        "esha": "71265",
    },
    "graham cracker square": {
        "sr28": "174957",
        "fndds": "54102010",
        "esha": "71265",
    },
    "graham cracker squares": {
        "sr28": "174957",
        "fndds": "54102010",
        "esha": "71265",
    },
    "honey flavored bear shaped graham crackers": {
        "sr28": "174957",
        "fndds": "54102015",
        "esha": "34639",
    },
    "honey graham cracker": {
        "sr28": "174957",
        "fndds": "54102010",
        "esha": "34639",
    },
    "honey graham crackers": {
        "sr28": "174957",
        "fndds": "54102010",
        "esha": "34639",
    },
    "hot and spicy cheez it crackers": {
        "sr28": "174975",
        "fndds": "54304005",
        "esha": "52974",
    },
    "individual graham cracker tart shells": {
        "sr28": "167520",
        "fndds": "53391100",
        "esha": "62917",
    },
    "multigrain wasa crackers": {
        "fndds": "54001000",
        "esha": "139",
    },
    "ready made graham cracker crust": {
        "sr28": "167520",
        "fndds": "53391100",
        "esha": "48475",
    },
    "reduced fat graham cracker crust": {
        "sr28": "167520",
        "fndds": "53391100",
        "esha": "48475",
    },
    "ritz crackers": {
        "sr28": "173258",
        "fndds": "54301030",
        "esha": "70963",
    },
    "savory crackers": {
        "fndds": "54001000",
        "esha": "43670",
    },
    "sesame crackers": {
        "fndds": "54001000",
        "esha": "34594",
    },
    "sleeve ritz crackers": {
        "sr28": "173258",
        "fndds": "54301030",
        "esha": "70963",
    },
    "sleeve saltine crackers": {
        "sr28": "172746",
        "fndds": "54325000",
        "esha": "31262",
    },
    "snackwell s fat free wheat crackers": {
        "fndds": "54001000",
        "esha": "139",
    },
    "thin wheat snack cracker": {
        "fndds": "54338010",
        "esha": "43746",
    },
    "town house cracker": {
        "fndds": "54001000",
        "esha": "52874",
    },
    "triscuit cracker": {
        "fndds": "54337020",
        "esha": "43584",
    },
    "vegan graham cracker crust": {
        "sr28": "167520",
        "fndds": "53391100",
        "esha": "48475",
    },
    "waverly cracker": {
        "fndds": "54001000",
        "esha": "139",
    },
    "wheat thins cracker": {
        "fndds": "54338010",
        "esha": "43746",
    },
    "wheat thins crackers": {
        "fndds": "54338010",
        "esha": "43746",
    },
    "whole grain salted crackers pulsed into fine": {
        "fndds": "54001000",
        "esha": "139",
    },
    "woven wheat cracker": {
        "fndds": "54337020",
        "esha": "37992",
    },
}
MISC_SURFACE_FIXES = {
    "hickory smoked thin sliced bacon brought to": {
        "sr28": "168277",
        "esha": "33390",
    },
}
# These repairs are only applied when both canonical registries agree on the
# same ESHA target for the canonical surface.
GRAPH_CONSENSUS_CANONICAL_FIXES = {
    "chili sauce": {
        "sr28": "171595",
        "fndds": "74402010",
        "esha": "434",
    },
    "chipotle sauce": {
        "esha": "33313",
    },
    "cream of onion soup": {
        "sr28": "171552",
        "esha": "50482",
    },
    "dill pickle relish": {
        "fndds": "75503020",
        "esha": "13357",
    },
    "malt vinegar": {
        "fndds": "64401000",
        "esha": "41309",
    },
    "nutritional yeast": {
        "esha": "7784",
    },
    "red wine vinegar": {
        "sr28": "172240",
        "fndds": "64401000",
        "esha": "27204",
    },
    "spaghetti squash": {
        "sr28": "169299",
        "fndds": "75233220",
        "esha": "5455",
    },
    "sweet pickle relish": {
        "sr28": "168561",
        "fndds": "75503020",
        "esha": "18032",
    },
    "vegetable broth": {
        "sr28": "171583",
        "fndds": "75657000",
        "esha": "50599",
    },
    "vegetable juice": {
        "fndds": "74303000",
        "esha": "6507",
    },
    "vegetarian chili": {
        "fndds": "41812450",
        "esha": "7760",
    },
    "white wine vinegar": {
        "fndds": "64401000",
        "esha": "53459",
    },
}
GRAPH_CHILI_SAUCE_TRAPDOOR_ESHA_CODES = {"13367", "39180", "9596"}

CODE_PATTERN = re.compile(r"(code:)(\d+)")


def normalize_key(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = cleaned.replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_esha_descriptions() -> dict[str, str]:
    out: dict[str, str] = {}
    with ESHA_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle):
            code = (row.get("EshaCode") or "").strip()
            desc = (row.get("Description") or "").strip()
            if code and desc:
                out[code] = desc
    return out


def load_sr28_descriptions() -> dict[str, str]:
    out: dict[str, str] = {}
    with SR28_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle):
            code = (row.get("fdc_id") or "").strip()
            desc = (row.get("long_desc") or row.get("description") or "").strip()
            if code and desc:
                out[code] = desc
    return out


def load_fndds_descriptions() -> dict[str, str]:
    out: dict[str, str] = {}
    with FNDDS_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle):
            code = (row.get("Food code") or row.get("FoodCode") or "").strip()
            desc = (row.get("Main food description") or row.get("Main food desc") or "").strip()
            if code and desc:
                out[code] = desc
    return out


@lru_cache(maxsize=1)
def load_graph_consensus_esha_codes() -> dict[str, str]:
    canonical_to_esha: dict[str, set[str]] = defaultdict(set)
    esha_canonical_hints: dict[str, set[str]] = defaultdict(set)

    if CANONICAL_TO_ESHA_CSV.exists():
        with CANONICAL_TO_ESHA_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            for row in csv.DictReader(handle):
                canonical = normalize_key(row.get("canonical_name", ""))
                code = (row.get("esha_code") or "").strip()
                if canonical and code:
                    canonical_to_esha[canonical].add(code)

    if ESHA_CANONICAL_CSV.exists():
        with ESHA_CANONICAL_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            for row in csv.DictReader(handle):
                canonical = normalize_key(row.get("canonical_shopping_item", ""))
                code = (row.get("EshaCode") or "").strip()
                if canonical and code:
                    esha_canonical_hints[canonical].add(code)

    consensus: dict[str, str] = {}
    for canonical in set(canonical_to_esha) | set(esha_canonical_hints):
        agreed = canonical_to_esha[canonical] & esha_canonical_hints[canonical]
        if len(agreed) == 1:
            consensus[canonical] = next(iter(agreed))
    return consensus


def add_note(row: dict[str, str], note: str) -> None:
    notes = [part.strip() for part in (row.get("notes") or "").split(";") if part.strip()]
    if note not in notes:
        notes.append(note)
    row["notes"] = "; ".join(notes)


def drop_note_contains(row: dict[str, str], fragment: str) -> None:
    if not row.get("notes"):
        return
    notes = [part.strip() for part in row["notes"].split(";") if part.strip()]
    notes = [part for part in notes if fragment not in part]
    row["notes"] = "; ".join(notes)


def sync_match_type(match_type: str, code: str) -> str:
    if not match_type or not code:
        return match_type
    if not CODE_PATTERN.search(match_type):
        return match_type
    return CODE_PATTERN.sub(rf"\g<1>{code}", match_type, count=1)


def clear_fndds(row: dict[str, str]) -> None:
    row["fndds_code"] = ""
    row["fndds_description"] = ""
    row["fndds_match_type"] = ""


def clear_proxy(row: dict[str, str]) -> None:
    for field in (
        "proxy_target",
        "proxy_source",
        "proxy_code",
        "proxy_description",
        "proxy_reason",
        "proxy_review_status",
    ):
        row[field] = ""


def clear_product_proxy_fields(row: dict[str, str]) -> None:
    row["hestia_proxy_code"] = ""
    for field in (
        "product_proxy_match_state",
        "hestia_product_proxy_code",
        "product_proxy_review_status",
        "product_proxy_matched_product_count",
        "product_proxy_median_calories",
        "product_proxy_median_protein_g",
        "product_proxy_median_fat_g",
        "product_proxy_median_carbs_g",
        "product_proxy_median_sugar_g",
        "product_proxy_median_sodium_mg",
        "product_proxy_basis",
        "product_proxy_sr28_anchor_code",
        "product_proxy_sr28_anchor_description",
        "product_proxy_sr28_anchor_match_type",
        "product_proxy_sr28_anchor_basis",
    ):
        row[field] = ""


def clear_esha(row: dict[str, str], reason: str) -> None:
    row["esha_code"] = ""
    row["esha_description"] = ""
    row["esha_match_type"] = f"reviewed_clear:{reason}"


def clear_nutrition_backbone(row: dict[str, str], reason: str) -> None:
    for field in (
        "nutrition_code",
        "nutrition_code_type",
        "sr28_code",
        "sr28_description",
        "sr28_match_type",
        "fndds_code",
        "fndds_description",
        "fndds_match_type",
        "esha_code",
        "esha_description",
        "proxy_target",
        "proxy_source",
        "proxy_code",
        "proxy_description",
        "proxy_reason",
    ):
        row[field] = ""
    row["nutrition_match_state"] = "reviewed_nutrition_unknown"
    row["esha_match_type"] = f"reviewed_clear:{reason}"
    row["unmatched_reason"] = reason
    clear_product_proxy_fields(row)


def clear_salad_dressing_backbone(row: dict[str, str], reason: str) -> None:
    clear_nutrition_backbone(row, reason)


def set_esha(row: dict[str, str], code: str, descriptions: dict[str, str], reason: str) -> None:
    row["esha_code"] = code
    row["esha_description"] = descriptions[code]
    row["esha_match_type"] = f"pack_signal:code:{code}:{reason}"


def set_sr28(row: dict[str, str], code: str, descriptions: dict[str, str], match_type: str) -> None:
    row["sr28_code"] = code
    row["sr28_description"] = descriptions[code]
    row["sr28_match_type"] = match_type


def set_fndds(row: dict[str, str], code: str, descriptions: dict[str, str], match_type: str) -> None:
    row["fndds_code"] = code
    row["fndds_description"] = descriptions[code]
    row["fndds_match_type"] = match_type


def set_proxy_from_sr28(row: dict[str, str], code: str, descriptions: dict[str, str], reason: str) -> None:
    row["proxy_target"] = descriptions[code]
    row["proxy_source"] = "sr28"
    row["proxy_code"] = code
    row["proxy_description"] = descriptions[code]
    row["proxy_reason"] = reason


def set_product_proxy_anchor(
    row: dict[str, str],
    code: str,
    descriptions: dict[str, str],
    match_type: str,
    basis: str,
) -> None:
    row["product_proxy_sr28_anchor_code"] = code
    row["product_proxy_sr28_anchor_description"] = descriptions[code]
    row["product_proxy_sr28_anchor_match_type"] = match_type
    row["product_proxy_sr28_anchor_basis"] = basis


def set_direct_sr28_nutrition(
    row: dict[str, str],
    code: str,
    descriptions: dict[str, str],
    match_type: str,
) -> None:
    row["nutrition_code"] = f"SR28:{code}"
    row["nutrition_code_type"] = "sr28_reference_match"
    row["nutrition_match_state"] = "sr28_match"
    row["unmatched_reason"] = ""
    set_sr28(row, code, descriptions, match_type)


def set_direct_fndds_nutrition(
    row: dict[str, str],
    code: str,
    descriptions: dict[str, str],
    match_type: str,
) -> None:
    row["nutrition_code"] = f"FNDDS:{code}"
    row["nutrition_code_type"] = "fndds_reference_match"
    row["nutrition_match_state"] = "fndds_match"
    row["unmatched_reason"] = ""
    set_fndds(row, code, descriptions, match_type)


def apply_direct_sr28_esha_fix(
    row: dict[str, str],
    *,
    sr28_code: str,
    esha_code: str,
    sr28_desc: dict[str, str],
    esha_desc: dict[str, str],
    note: str,
) -> None:
    set_direct_sr28_nutrition(row, sr28_code, sr28_desc, f"surface_signal_repair:code:{sr28_code}")
    set_esha(row, esha_code, esha_desc, "surface_signal_repair")
    clear_fndds(row)
    clear_proxy(row)
    clear_product_proxy_fields(row)
    add_note(row, note)


def apply_direct_surface_fix(
    row: dict[str, str],
    *,
    sr28_code: str | None,
    fndds_code: str | None,
    esha_code: str | None,
    sr28_desc: dict[str, str],
    fndds_desc: dict[str, str],
    esha_desc: dict[str, str],
    note: str,
) -> None:
    if sr28_code:
        set_direct_sr28_nutrition(row, sr28_code, sr28_desc, f"surface_signal_repair:code:{sr28_code}")
    elif fndds_code:
        set_direct_fndds_nutrition(row, fndds_code, fndds_desc, f"surface_signal_repair:code:{fndds_code}")
        row["sr28_code"] = ""
        row["sr28_description"] = ""
        row["sr28_match_type"] = ""
    else:
        row["nutrition_code"] = ""
        row["nutrition_code_type"] = ""
        row["nutrition_match_state"] = "reviewed_nutrition_unknown"
        row["sr28_code"] = ""
        row["sr28_description"] = ""
        row["sr28_match_type"] = ""
        row["unmatched_reason"] = ""

    if fndds_code:
        set_fndds(row, fndds_code, fndds_desc, f"surface_signal_repair:code:{fndds_code}")
        drop_note_contains(row, "source_gap:fndds")
    else:
        clear_fndds(row)

    if esha_code:
        set_esha(row, esha_code, esha_desc, "surface_signal_repair")
        drop_note_contains(row, "source_gap:esha")
    else:
        row["esha_code"] = ""
        row["esha_description"] = ""
        row["esha_match_type"] = ""

    clear_proxy(row)
    clear_product_proxy_fields(row)
    add_note(row, note)


def exact_esha_code_for(row: dict[str, str]) -> str | None:
    surface = normalize_key(row.get("canonical_surface", ""))
    normalized = normalize_key(row.get("canonical_normalized", ""))
    shopping = normalize_key(row.get("canonical_shopping_item", ""))
    joined = " | ".join(part for part in (surface, normalized, shopping) if part)

    if surface in ICE_CREAM_EXACT_ESHA_SURFACE_FIXES:
        return ICE_CREAM_EXACT_ESHA_SURFACE_FIXES[surface]
    if "tootsie pop" in joined:
        if "mini" in joined:
            return "92708"
        if "small" in joined:
            return "92710"
        return "92709"
    if "tootsie roll midgee" in joined:
        return "92721"
    if "half and half" in joined:
        return "500"
    if surface == "hard candy":
        return "23031"
    if surface in {"candy cane", "candy canes"}:
        return "92711"
    if surface == "orange slice candy":
        return "31186"
    if surface in CARAMEL_CANDY_SURFACES:
        return "23015"
    if surface in CARAMEL_TOPPING_SURFACES:
        if surface == "caramel sauce":
            return "15686"
        return "91634"
    if "balsamic italian dressing" in surface:
        return "44981"
    if "newmans own southwest" in joined or "newman s own southwest" in joined:
        return "34736"
    if "greek feta cheese dressing" in surface:
        return "27911"
    if "greek vinaigrette" in joined or surface in {"greek dressing", "greek salad dressing"}:
        return "18331"
    if "raspberry vinaigrette" in joined:
        if "light" in joined or "lite" in joined:
            return "27487"
        return "18337"
    if "pomegranate vinaigrette" in joined:
        return "19708"
    if "italian vinaigrette" in joined:
        return "18334"
    if "french vinaigrette" in joined:
        return "8015"
    if "mayonnaise" in joined:
        if "fat free" in joined:
            return "8069"
        return "8046"
    if "whipped dressing" in joined:
        return "44700"
    if "ranch" in surface and "dressing" in surface and "ranch" not in (row.get("esha_description") or "").lower():
        if "buttermilk" in surface:
            return "8451"
        return "25381"
    if "balsamic" in surface and "dressing" in surface and "italian" not in surface:
        return "18324"
    return None


def canonical_keys_for_row(row: dict[str, str]) -> list[str]:
    keys = []
    for value in (
        row.get("canonical_normalized", ""),
        row.get("canonical_shopping_item", ""),
        row.get("canonical_surface", ""),
    ):
        key = normalize_key(value)
        if key and key not in keys:
            keys.append(key)
    return keys


def graph_consensus_esha_code_for(row: dict[str, str], consensus_codes: dict[str, str]) -> tuple[str | None, str | None]:
    for key in canonical_keys_for_row(row):
        code = consensus_codes.get(key)
        if code:
            return key, code
    return None, None


def should_clear_wrong_italian_esha(row: dict[str, str]) -> bool:
    surface = normalize_key(row.get("canonical_surface", ""))
    esha_desc = (row.get("esha_description") or "").lower()
    if "italian" not in esha_desc:
        return False
    if "italian" in surface:
        return False
    return any(cue in surface for cue in ESHA_CLEAR_ONLY_CUES)


def should_clear_weak_fndds(row: dict[str, str]) -> bool:
    surface = normalize_key(row.get("canonical_surface", ""))
    fndds_code = (row.get("fndds_code") or "").strip()
    if fndds_code not in WEAK_FNDDS_CODES:
        return False
    if "half and half" in surface:
        return True
    if "dressing" in surface or "vinaigrette" in surface:
        return True
    return False


def repair_rows(rows: list[dict[str, str]]) -> list[str]:
    esha_desc = load_esha_descriptions()
    sr28_desc = load_sr28_descriptions()
    fndds_desc = load_fndds_descriptions()
    graph_consensus_codes = load_graph_consensus_esha_codes()
    changed: list[str] = []

    for row in rows:
        surface = row.get("canonical_surface", "")
        original = dict(row)
        surface_key = normalize_key(surface)

        row["sr28_match_type"] = sync_match_type(row.get("sr28_match_type", ""), row.get("sr28_code", "").strip())
        row["fndds_match_type"] = sync_match_type(row.get("fndds_match_type", ""), row.get("fndds_code", "").strip())
        row["esha_match_type"] = sync_match_type(row.get("esha_match_type", ""), row.get("esha_code", "").strip())

        if surface_key.startswith("tootsie roll"):
            row["family_base"] = "tootsie roll"
        if row.get("sr28_code") == "167990" and row.get("esha_code") == "41369":
            set_esha(row, "23031", esha_desc, "surface_signal_repair")
            add_note(row, "surface_signal_repair:hard_candy_all_flavors_esha")
        if surface_key in FLAN_CONFECTION_SURFACE_FIXES:
            fix = FLAN_CONFECTION_SURFACE_FIXES[surface_key]
            apply_direct_sr28_esha_fix(
                row,
                sr28_code=fix["sr28"],
                esha_code=fix["esha"],
                sr28_desc=sr28_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_flan_confection_backbone:{surface_key}",
            )

        if surface_key in ICE_CREAM_BUCKET_SURFACE_FIXES:
            fix = ICE_CREAM_BUCKET_SURFACE_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_vanilla_ice_cream_bucket:{surface_key}",
            )

        if surface_key in ICE_CREAM_CLEAR_SURFACES:
            clear_nutrition_backbone(row, ICE_CREAM_CLEAR_SURFACES[surface_key])
            add_note(row, f"surface_signal_repair:cleared_vanilla_ice_cream_bucket:{surface_key}")

        if surface_key in FRUIT_VARIANT_SURFACE_FIXES:
            fix = FRUIT_VARIANT_SURFACE_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_raw_fruit_variant_bucket:{surface_key}",
            )

        if surface_key in FRUIT_CLEAR_SURFACES:
            clear_nutrition_backbone(row, FRUIT_CLEAR_SURFACES[surface_key])
            add_note(row, f"surface_signal_repair:cleared_raw_fruit_variant_bucket:{surface_key}")

        if surface_key in SYRUP_JUICE_SORBET_TOPPING_FIXES:
            fix = SYRUP_JUICE_SORBET_TOPPING_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_syrup_juice_sorbet_topping_bucket:{surface_key}",
            )

        if surface_key in SAUCE_FAMILY_FIXES:
            fix = SAUCE_FAMILY_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_raw_sauce_bucket:{surface_key}",
            )

        if surface_key in SAUCE_CLEAR_SURFACES:
            clear_nutrition_backbone(row, SAUCE_CLEAR_SURFACES[surface_key])
            add_note(row, f"surface_signal_repair:cleared_raw_sauce_bucket:{surface_key}")

        if surface_key in RELISH_FAMILY_FIXES:
            fix = RELISH_FAMILY_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_raw_relish_bucket:{surface_key}",
            )

        if surface_key in VINEGAR_FAMILY_FIXES:
            fix = VINEGAR_FAMILY_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_wine_pepper_vinegar_bucket:{surface_key}",
            )

        if surface_key in SHERBET_FAMILY_FIXES:
            fix = SHERBET_FAMILY_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_raw_sherbet_bucket:{surface_key}",
            )

        if surface_key in SPECIALTY_JUICE_CLEAR_SURFACES:
            clear_nutrition_backbone(row, SPECIALTY_JUICE_CLEAR_SURFACES[surface_key])
            add_note(row, f"surface_signal_repair:cleared_specialty_juice_bucket:{surface_key}")

        if surface_key in PUDDING_MIX_FIXES:
            fix = PUDDING_MIX_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_gelatin_pudding_bucket:{surface_key}",
            )

        if surface_key in YOGURT_FAMILY_FIXES:
            fix = YOGURT_FAMILY_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_yogurt_family_bucket:{surface_key}",
            )

        if surface_key in YOGURT_CLEAR_SURFACES:
            clear_nutrition_backbone(row, YOGURT_CLEAR_SURFACES[surface_key])
            add_note(row, f"surface_signal_repair:cleared_yogurt_family_bucket:{surface_key}")

        if surface_key in AVOCADO_SURFACE_FIXES:
            fix = AVOCADO_SURFACE_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_avocado_frozen_halves_residue:{surface_key}",
            )

        if surface_key in BABYFOOD_DESSERT_FIXES:
            fix = BABYFOOD_DESSERT_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_babyfood_dessert_residue:{surface_key}",
            )

        if surface_key in CUSTARD_SURFACE_FIXES:
            fix = CUSTARD_SURFACE_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_custard_residue:{surface_key}",
            )

        if surface_key in CHEESECAKE_YOGURT_FIXES:
            fix = CHEESECAKE_YOGURT_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_cheesecake_yogurt_residue:{surface_key}",
            )

        if surface_key in CRACKER_SURFACE_FIXES:
            fix = CRACKER_SURFACE_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_whole_wheat_cracker_bucket:{surface_key}",
            )

        if surface_key in MISC_SURFACE_FIXES:
            fix = MISC_SURFACE_FIXES[surface_key]
            apply_direct_surface_fix(
                row,
                sr28_code=fix.get("sr28"),
                fndds_code=fix.get("fndds"),
                esha_code=fix.get("esha"),
                sr28_desc=sr28_desc,
                fndds_desc=fndds_desc,
                esha_desc=esha_desc,
                note=f"surface_signal_repair:cleared_cross_family_residue:{surface_key}",
            )

        graph_canonical_key, graph_consensus_esha = graph_consensus_esha_code_for(row, graph_consensus_codes)
        if graph_canonical_key in GRAPH_CONSENSUS_CANONICAL_FIXES:
            fix = GRAPH_CONSENSUS_CANONICAL_FIXES[graph_canonical_key]
            if graph_consensus_esha == fix.get("esha"):
                current_esha_code = (row.get("esha_code") or "").strip()
                current_esha_desc = (row.get("esha_description") or "").lower()
                if graph_canonical_key != "chili sauce" or (
                    current_esha_code in GRAPH_CHILI_SAUCE_TRAPDOOR_ESHA_CODES
                    or "chile pepper" in current_esha_desc
                ):
                    apply_direct_surface_fix(
                        row,
                        sr28_code=fix.get("sr28"),
                        fndds_code=fix.get("fndds"),
                        esha_code=fix.get("esha"),
                        sr28_desc=sr28_desc,
                        fndds_desc=fndds_desc,
                        esha_desc=esha_desc,
                        note=f"surface_signal_repair:graph_consensus:{graph_canonical_key}",
                    )

        if surface_key in {"bread dressing", "cajun rice dressing"}:
            clear_salad_dressing_backbone(row, "non_salad_dressing_manual_review")
            add_note(row, "surface_signal_repair:cleared_non_salad_dressing_backbone")

        exact_esha = exact_esha_code_for(row)
        if exact_esha:
            set_esha(row, exact_esha, esha_desc, "surface_signal_repair")
            add_note(row, f"surface_signal_repair:esha:{exact_esha}")

            if exact_esha == "500":
                if (row.get("sr28_description") or "").lower().find("heavy") != -1 or (row.get("fndds_description") or "").lower().find("heavy") != -1:
                    row["nutrition_code"] = ""
                    row["nutrition_code_type"] = ""
                    row["nutrition_match_state"] = "reviewed_nutrition_unknown"
                    row["sr28_code"] = ""
                    row["sr28_description"] = ""
                    row["sr28_match_type"] = ""
                    clear_fndds(row)
                    row["proxy_code"] = ""
                    row["proxy_description"] = ""
                    row["proxy_reason"] = ""
                    row["proxy_target"] = ""
                    row["proxy_source"] = ""
                    row["unmatched_reason"] = "wave1_direct_cream_family_poison"
            elif exact_esha == "19708":
                set_sr28(row, "171417", sr28_desc, "pack_signal:code:171417:pomegranate_vinaigrette_backbone")
                set_proxy_from_sr28(row, "171417", sr28_desc, "surface signal repair: vinaigrette backbone")
                clear_fndds(row)
            elif exact_esha in {"25381", "8451"} and "ranch" in surface_key and row.get("sr28_code") not in {"173592", "169895"}:
                set_sr28(row, "173592", sr28_desc, "pack_signal:code:173592:ranch_backbone")
                set_proxy_from_sr28(row, "173592", sr28_desc, "surface signal repair: ranch backbone")
                clear_fndds(row)
            elif exact_esha in {"92708", "92709", "92710"} and "tootsie pop" in surface_key:
                set_sr28(row, "167990", sr28_desc, "surface_signal_repair:code:167990")
                clear_fndds(row)
                set_proxy_from_sr28(row, "167990", sr28_desc, "candy/lollipop proxy candidate; hard candy backbone")
                set_product_proxy_anchor(
                    row,
                    "167990",
                    sr28_desc,
                    "surface_signal_repair:code:167990",
                    "surface_signal_repair",
                )
                add_note(row, "surface_signal_repair:tootsie_pop_hard_candy_backbone")
            elif exact_esha == "92721":
                row["nutrition_code"] = "SR28:167971"
                row["nutrition_code_type"] = "sr28_reference_match"
                row["nutrition_match_state"] = "sr28_match"
                row["unmatched_reason"] = ""
                set_sr28(row, "167971", sr28_desc, "surface_signal_repair:code:167971")
                clear_fndds(row)
                clear_proxy(row)
                clear_product_proxy_fields(row)
                row["notes"] = "surface_signal_repair: dropped bread-roll bridge and restored Tootsie Roll candy backbone"
            elif exact_esha == "23015":
                set_direct_sr28_nutrition(row, "167974", sr28_desc, "surface_signal_repair:code:167974")
                clear_fndds(row)
                clear_proxy(row)
                clear_product_proxy_fields(row)
                add_note(row, "surface_signal_repair:caramel_candy_family")
            elif exact_esha in {"15686", "91634"}:
                set_direct_sr28_nutrition(row, "168841", sr28_desc, "surface_signal_repair:code:168841")
                clear_fndds(row)
                clear_proxy(row)
                clear_product_proxy_fields(row)
                add_note(row, "surface_signal_repair:caramel_topping_family")
            elif exact_esha == "92711":
                set_direct_sr28_nutrition(row, "167990", sr28_desc, "surface_signal_repair:code:167990")
                set_fndds(row, "91745020", fndds_desc, "surface_signal_repair:code:91745020")
                clear_proxy(row)
                clear_product_proxy_fields(row)
                add_note(row, "surface_signal_repair:candy_cane_hard_candy_family")
            elif exact_esha == "71228" or surface_key == "wheat flatbread":
                set_sr28(row, "174916", sr28_desc, "surface_signal_repair:code:174916")
                set_fndds(row, "51301600", fndds_desc, "surface_signal_repair:code:51301600")
                set_proxy_from_sr28(row, "174916", sr28_desc, "surface signal repair: whole wheat pita proxy")
                set_product_proxy_anchor(row, "174916", sr28_desc, "surface_signal_repair", "surface_signal_repair")
            elif surface_key == "french vanilla ice cream":
                apply_direct_surface_fix(
                    row,
                    sr28_code="167981",
                    fndds_code="13110100",
                    esha_code=exact_esha,
                    sr28_desc=sr28_desc,
                    fndds_desc=fndds_desc,
                    esha_desc=esha_desc,
                    note="surface_signal_repair:french_vanilla_ice_cream_floor",
                )
            elif surface_key in {"low fat vanilla ice cream", "vanilla low fat ice cream"}:
                apply_direct_surface_fix(
                    row,
                    sr28_code="167572",
                    fndds_code="13110100",
                    esha_code=exact_esha,
                    sr28_desc=sr28_desc,
                    fndds_desc=fndds_desc,
                    esha_desc=esha_desc,
                    note="surface_signal_repair:light_vanilla_ice_cream_floor",
                )
            elif surface_key == "premium vanilla ice cream":
                apply_direct_surface_fix(
                    row,
                    sr28_code="167573",
                    fndds_code="13110100",
                    esha_code=exact_esha,
                    sr28_desc=sr28_desc,
                    fndds_desc=fndds_desc,
                    esha_desc=esha_desc,
                    note="surface_signal_repair:rich_vanilla_ice_cream_floor",
                )
            elif surface_key == "sugar free vanilla ice cream":
                apply_direct_surface_fix(
                    row,
                    sr28_code="169631",
                    fndds_code="13110320",
                    esha_code=exact_esha,
                    sr28_desc=sr28_desc,
                    fndds_desc=fndds_desc,
                    esha_desc=esha_desc,
                    note="surface_signal_repair:no_sugar_added_vanilla_ice_cream_floor",
                )
            elif should_clear_weak_fndds(row):
                if row.get("fndds_code") != "83107000":
                    clear_fndds(row)
                    add_note(row, "surface_signal_repair:cleared_generic_fndds")

        if should_clear_wrong_italian_esha(row) and not exact_esha:
            clear_esha(row, "no_safe_exact_non_italian_pack")
            add_note(row, "surface_signal_repair:cleared_wrong_italian_esha")
            if should_clear_weak_fndds(row):
                clear_fndds(row)

        if surface_key == "wheat flatbread":
            set_esha(row, "71228", esha_desc, "surface_signal_repair")
            set_sr28(row, "174916", sr28_desc, "surface_signal_repair:code:174916")
            set_fndds(row, "51301600", fndds_desc, "surface_signal_repair:code:51301600")
            set_proxy_from_sr28(row, "174916", sr28_desc, "surface signal repair: whole wheat pita proxy")
            set_product_proxy_anchor(row, "174916", sr28_desc, "surface_signal_repair", "surface_signal_repair")
            add_note(row, "surface_signal_repair:wheat_flatbread_to_whole_wheat_pita")

        if should_clear_weak_fndds(row) and row.get("fndds_code") in WEAK_FNDDS_CODES:
            clear_fndds(row)
            add_note(row, "surface_signal_repair:cleared_generic_fndds")

        if row.get("product_proxy_sr28_anchor_code") == "167574" and row.get("sr28_code") and row.get("sr28_code") != "167574":
            set_product_proxy_anchor(
                row,
                row["sr28_code"],
                sr28_desc,
                row.get("sr28_match_type", "") or f"surface_signal_repair:code:{row['sr28_code']}",
                "surface_signal_repair",
            )
            add_note(row, "surface_signal_repair:cleared_stale_flan_anchor")

        if surface_key == "hard candy" and row.get("esha_code") == "23031":
            add_note(row, "surface_signal_repair:hard_candy_all_flavors_esha")

        if row != original:
            changed.append(surface)

    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair canonical surface rows using strong pack/card signals")
    parser.add_argument("--csv", type=Path, default=CANONICAL_CSV)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    rows = read_rows(args.csv)
    if not rows:
        raise SystemExit("canonical_csv_has_no_rows")

    changed = repair_rows(rows)
    unique_changed = sorted(set(changed))
    print(f"rows_changed={len(changed)} unique_surfaces_changed={len(unique_changed)}")
    for surface in unique_changed[:120]:
        print(surface)

    if args.write:
        write_rows(args.csv, list(rows[0].keys()), rows)
        print(f"wrote={args.csv}")


if __name__ == "__main__":
    main()
