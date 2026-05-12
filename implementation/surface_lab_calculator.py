from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from esha_nutrition import nutrition_for_esha
from product_matcher import match_products, search_products
from schema import NutritionEstimate, NutritionState, ShoppingState
from sr28_nutrition import nutrition_for_grams, sr28_per_100g
from taxonomy_lookup import lookup_taxonomy, metadata_kwargs


ROOT = Path(__file__).resolve().parent.parent
IMPLEMENTATION = ROOT / "implementation"
LOCAL_CLEAN_ROOT = ROOT.parent / "clean"
LOCAL_RFT_SURFACE_CSV = LOCAL_CLEAN_ROOT / "canonical_surface_normalized_with_product_proxies_rft_cleaned.csv"
REPO_SURFACE_CSV = IMPLEMENTATION / "output" / "canonical_surface_normalized_with_product_proxies_CLEANED.csv"
DEFAULT_SURFACE_CSV = REPO_SURFACE_CSV
DEFAULT_PRODUCT_ESHA_MAP_CSV = IMPLEMENTATION / "output" / "product_esha_fixy.identity_gated.csv"
TMP_PRODUCT_ESHA_MAP_CSV = Path("/tmp/hestia_native_artifacts/product_esha_fixy.identity_gated.csv")
FALLBACK_PRODUCT_ESHA_MAP_CSV = IMPLEMENTATION / "output" / "product_to_best_esha_full_map.vSelf.csv"
DEFAULT_RETAIL_SURFACE_BRIDGE_CSV = IMPLEMENTATION / "output" / "retail_canonical_surface_bridge.csv"
TMP_RETAIL_SURFACE_BRIDGE_CSV = Path("/tmp/hestia_native_artifacts/retail_canonical_surface_bridge.csv")
SURFACE_CSV = Path(
    os.environ.get("HESTIA_SURFACE_CSV")
    or (DEFAULT_SURFACE_CSV if DEFAULT_SURFACE_CSV.exists() else LOCAL_RFT_SURFACE_CSV)
)
PRODUCT_ESHA_MAP_CSV = Path(
    os.environ.get("HESTIA_PRODUCT_ESHA_MAP_CSV")
    or (
        DEFAULT_PRODUCT_ESHA_MAP_CSV
        if DEFAULT_PRODUCT_ESHA_MAP_CSV.exists()
        else TMP_PRODUCT_ESHA_MAP_CSV
        if TMP_PRODUCT_ESHA_MAP_CSV.exists()
        else FALLBACK_PRODUCT_ESHA_MAP_CSV
    )
)
RETAIL_SURFACE_BRIDGE_CSV = Path(
    os.environ.get("HESTIA_RETAIL_SURFACE_BRIDGE_CSV")
    or (
        DEFAULT_RETAIL_SURFACE_BRIDGE_CSV
        if DEFAULT_RETAIL_SURFACE_BRIDGE_CSV.exists()
        else TMP_RETAIL_SURFACE_BRIDGE_CSV
        if TMP_RETAIL_SURFACE_BRIDGE_CSV.exists()
        else DEFAULT_RETAIL_SURFACE_BRIDGE_CSV
    )
)
APPROVED_RULES_CSV = IMPLEMENTATION / "approved_normalization_rules.csv"
FNDDS_NUTRIENTS_CSV = ROOT / "data" / "fndds" / "fndds_nutrient_lookup.csv"
ESHA_PACK_INDEX_CSV = IMPLEMENTATION / "output" / "esha_code_query_pack_index.csv"
PRODUCT_ESHA_LOOKUP_DB = IMPLEMENTATION / "output" / "product_esha_lookup.db"
REPO_API_CACHE_PRODUCTS_CSV = ROOT / "recipe_pricing" / "data" / "api_cache_products.csv"
LOCAL_API_CACHE_PRODUCTS_CSV = LOCAL_CLEAN_ROOT / "recipe_pricing" / "data" / "api_cache_products.csv"
API_CACHE_PRODUCTS_CSV = REPO_API_CACHE_PRODUCTS_CSV if REPO_API_CACHE_PRODUCTS_CSV.exists() else LOCAL_API_CACHE_PRODUCTS_CSV
PRODUCT_MAP_PRODUCTS_PER_CODE = 100


@dataclass
class LabProduct:
    gtin_upc: str
    description: str
    brand_name: str
    category: str
    source: str
    decision: str = "candidate"
    reason: str = ""


@dataclass
class LabResolution:
    input_item: str
    input_display: str
    canonical_name: str
    shopping_canonical: str
    sr28_fdc_id: str
    fndds_code: str
    esha_code: str
    esha_description: str
    nutrition_state: str
    shopping_state: str
    grams: float | None
    nutrition_source: str
    nutrition: NutritionEstimate | None
    products: list[LabProduct]
    rejected_products: list[LabProduct]
    path: list[str]
    notes: str
    canonical_path: str = ""
    retail_leaf_path: str = ""
    canonical_label: str = ""
    product_identity_fixed: str = ""
    htc_code: str = ""
    htc_sku_code: str = ""
    htc_group: str = ""
    htc_family: str = ""
    htc_food: str = ""
    htc_form: str = ""
    htc_processing: str = ""
    htc_ptype: str = ""
    htc_check: str = ""
    htc_confidence: float | None = None
    htc_source: str = ""
    taxonomy_source: str = ""


_SURFACE_ROWS: list[dict[str, str]] | None = None
_SURFACE_INDEX: dict[str, list[dict[str, str]]] | None = None
_APPROVED_EXACT: dict[str, str] | None = None
_APPROVED_REGEX: list[tuple[re.Pattern[str], str, str]] | None = None
_FNDDS_PER_100G: dict[str, dict[str, float]] | None = None
_ESHA_PACK_INDEX: dict[str, Path] | None = None
_API_CACHE_PRODUCTS: dict[str, list[LabProduct]] | None = None
_PRODUCT_MAP_INDEX: dict[str, list[LabProduct]] | None = None
_RETAIL_SURFACE_BRIDGE_PRODUCTS: dict[str, list[LabProduct]] | None = None


def configure_data_sources(
    *,
    surface_csv: str | Path | None = None,
    product_esha_map_csv: str | Path | None = None,
    retail_surface_bridge_csv: str | Path | None = None,
) -> None:
    """Point the lab calculator at alternate generated artifacts.

    This is intentionally explicit so callers can opt into experimental RFT /
    concept-anchor files without changing the stable repo defaults.
    """
    global SURFACE_CSV, PRODUCT_ESHA_MAP_CSV, RETAIL_SURFACE_BRIDGE_CSV
    global _SURFACE_ROWS, _SURFACE_INDEX, _PRODUCT_MAP_INDEX, _RETAIL_SURFACE_BRIDGE_PRODUCTS

    if surface_csv is not None:
        SURFACE_CSV = Path(surface_csv)
        _SURFACE_ROWS = None
        _SURFACE_INDEX = None
    if product_esha_map_csv is not None:
        PRODUCT_ESHA_MAP_CSV = Path(product_esha_map_csv)
        _PRODUCT_MAP_INDEX = None
    if retail_surface_bridge_csv is not None:
        RETAIL_SURFACE_BRIDGE_CSV = Path(retail_surface_bridge_csv)
        _RETAIL_SURFACE_BRIDGE_PRODUCTS = None

SURFACE_ALIAS_REDIRECTS = {
    "sugar": "granulated sugar",
    "white granulated sugar": "granulated sugar",
    "sugars granulated": "granulated sugar",
    "flour": "all purpose flour",
    "garlic raw": "garlic",
    "oil olive salad or cooking": "olive oil",
    "lemon juice raw": "lemon juice",
    "milk whole 3 25 milkfat with added vitamin d": "whole milk",
    "milk whole 3 25% milkfat with added vitamin d": "whole milk",
    "cheese cheddar includes foods for usda s food distribution program": "cheddar cheese",
    "beef ground 80 lean meat 20 fat raw": "80% lean ground beef",
    "beef ground 80% lean meat 20% fat raw": "80% lean ground beef",
    "beef round top round steak boneless separable lean and fat trimmed to 0 fat all grades raw": "round steak",
    "beef round top round steak separable lean and fat trimmed to 1 8 fat all grades raw": "round steak",
    "pork fresh loin center loin chops bone in separable lean only raw": "pork chop",
    "pork fresh loin center loin chops boneless separable lean only raw": "pork chop",
    "bone in pork rib chop": "pork chop",
    "bone in pork rib chops": "pork chop",
    "spices oregano dried": "dried oregano",
    "oil vegetable soybean refined": "vegetable oil",
    "chicken broiler or fryers breast skinless boneless meat only raw": "chicken breast",
    "chicken broilers or fryers meat and skin raw": "whole chicken",
    "spices paprika": "paprika",
    "spices cinnamon ground": "ground cinnamon",
    "spices garlic powder": "garlic powder",
    "spices cumin seed": "cumin",
    "spices cloves ground": "ground cloves",
    "spices pepper red or cayenne": "cayenne pepper",
    "coriander cilantro leaves raw": "fresh cilantro",
    "peppers sweet red raw": "red bell pepper",
    "lime juice raw": "lime juice",
    "salad dressing mayonnaise regular": "mayonnaise",
    "mustard prepared yellow": "yellow mustard",
    "spices chili powder": "chili powder",
    "candies semisweet chocolate": "semisweet chocolate",
    "tomatoes red ripe canned packed in tomato juice": "canned tomatoes",
    "spices thyme dried": "dried thyme",
    "spices basil dried": "dried basil",
    "nuts walnuts english": "walnuts",
    "potatoes flesh and skin raw": "potato",
    "spices bay leaf": "bay leaf",
    "onions young green tops only": "green onion",
    "cocoa dry powder unsweetened": "cocoa powder",
    "egg yolk dried": "egg yolk",
    "fresh egg": "egg",
    "fresh eggs": "egg",
    "pork cured bacon unprepared": "bacon",
    "peppers jalapeno raw": "jalapeno",
    "spices ginger ground": "ground ginger",
    "raisins dark seedless includes foods for usda s food distribution program": "raisins",
    "apples raw with skin includes foods for usda s food distribution program": "apple",
    "spinach raw": "fresh spinach",
    "margarine regular hard soybean hydrogenated": "margarine",
    "sauce ready to serve pepper tabasco": "hot sauce",
    "tomato products canned paste without salt added includes foods for usda s food distribution program": "tomato paste",
    "olives ripe canned small extra large": "black olives",
    "nuts coconut meat dried desiccated sweetened flaked packaged": "sweetened coconut flakes",
    "spices curry powder": "curry powder",
    "spices coriander seed": "coriander seed",
    "cucumber with peel raw": "cucumber",
    "oil sesame salad or cooking": "sesame oil",
    "sauce salsa ready to serve": "salsa",
    "peanut butter smooth style with salt includes foods for usda s food distribution program": "peanut butter",
    "creamy peanut butter": "peanut butter",
    "creamy peanut butter creamy": "peanut butter",
    "avocados raw all commercial varieties": "avocado",
    "chives raw": "chives",
    "shortening household soybean partially hydrogenated cottonseed partially hydrogenated": "shortening",
    "spices allspice ground": "allspice",
    "spices pepper white": "white pepper",
    "cream fluid half and half": "half-and-half",
    "soup vegetable broth ready to serve": "vegetable broth",
    "soup cream of mushroom canned condensed": "cream of mushroom soup",
    "dessert topping semi solid frozen": "whipped topping",
    "yogurt cheese": "plain greek yogurt",
    "milk nonfat fluid with added vitamin a and vitamin d fat free or skim": "skim milk",
    "spices turmeric ground": "turmeric",
    "spices parsley dried": "dried parsley",
    "alcoholic beverage wine table red": "red wine",
    "seeds sesame seeds whole dried": "sesame seeds",
    "syrup maple canadian": "maple syrup",
    "spearmint fresh": "fresh mint",
    "corn syrup light or dark": "corn syrup",
    "lettuce red leaf raw": "red leaf lettuce",
    "beef broth bouillon or consomme": "beef broth",
    "corn sweet yellow raw": "corn",
    "peppers chili green canned": "green chiles",
    "tortillas ready to bake or fry flour shelf stable": "flour tortillas",
    "mushrooms chanterelle raw": "chanterelle mushrooms",
    "bread french or vienna includes sourdough": "french bread",
    "blueberries raw": "blueberries",
    "cheese ricotta whole milk": "ricotta cheese",
    "soup cream of chicken canned condensed": "cream of chicken soup",
    "cowpeas blackeyes immature seeds frozen unprepared": "black eyed peas",
    "rice white long grain regular raw enriched": "white rice",
    "sauce pasta spaghetti marinara ready to serve": "marinara sauce",
    "oranges raw all commercial varieties": "orange",
    "nuts coconut milk canned liquid expressed from grated meat and water": "coconut milk",
    "rice white long grain regular enriched cooked": "cooked white rice",
    "applesauce canned sweetened with salt": "applesauce",
    "alcoholic beverage distilled rum 80 proof": "rum",
    "sweeteners tabletop sucralose splenda packets": "splenda",
    "pumpkin canned without salt": "canned pumpkin",
    "spices sage ground": "sage",
    "egg whole cooked hard boiled": "hard boiled egg",
    "leeks bulb and lower leaf portion raw": "leeks",
    "cookies graham crackers plain or honey includes cinnamon": "graham crackers",
    "chicken broilers or fryers breast meat only cooked roasted": "cooked chicken breast",
    "seasoning mix dry taco original": "taco seasoning",
    "asparagus raw": "asparagus",
    "cheese cottage with vegetables": "cottage cheese",
    "chickpeas garbanzo beans bengal gram mature seeds canned drained solids": "chickpeas",
    "apples raw granny smith with skin includes foods for usda s food distribution program": "granny smith apple",
    "wheat flour white all purpose self rising enriched": "self rising flour",
    "alcoholic beverage beer regular all": "beer",
    "peaches yellow raw": "peach",
    "ice creams vanilla": "vanilla ice cream",
    "pork cured ham boneless regular approximately 11% fat roasted": "ham",
    "pork cured ham steak": "ham steak",
    "pork cured ham steak boneless extra lean": "ham steak",
    "pork cured ham steak boneless extra lean unheated": "ham steak",
    "pork fresh shoulder whole separable lean and fat raw": "pork shoulder",
    "noodles egg enriched cooked": "egg noodles",
    "nuts pine nuts dried": "pine nuts",
    "oil peanut salad or cooking": "peanut oil",
    "candies white chocolate": "white chocolate",
    "cornmeal degermed enriched yellow": "yellow cornmeal",
    "spices tarragon dried": "tarragon",
    "pineapple raw all varieties": "pineapple",
    "soup chicken broth or bouillon dry": "chicken bouillon",
    "turkey ground raw": "ground turkey",
    "sauce barbecue": "barbecue sauce",
    "chicken broilers or fryers dark meat thigh meat only raw": "chicken thigh",
    "beans snap green raw": "green beans",
    "canned green bean": "green beans",
    "canned green beans": "green beans",
    "chicken broilers or fryers meat only cooked roasted": "cooked chicken",
    "peppers sweet yellow raw": "yellow bell pepper",
    "cheese mozzarella nonfat": "fat free mozzarella cheese",
    "nonfat mozzarella cheese": "fat free mozzarella cheese",
    "tomatoes red ripe raw year round average": "tomato",
    "mushrooms white raw": "white mushroom",
    "peppers sweet green raw": "green bell pepper",
    "cheese parmesan grated": "parmesan cheese",
    "onions spring or scallions includes tops and bulb raw": "green onion",
    "scallion": "green onion",
    "scallions": "green onion",
    "soy sauce made from soy and wheat shoyu": "soy sauce",
    "lettuce iceberg includes crisphead types raw": "iceberg lettuce",
    "orange juice canned unsweetened": "orange juice",
    "orange peel raw": "orange peel",
    "sugars powdered": "powdered sugar",
    "sugars brown": "brown sugar",
    "pasta dry enriched": "dry pasta",
    "bananas raw": "banana",
    "alcoholic beverage wine table white": "white wine",
    "bread white commercially prepared includes soft bread crumbs": "white bread",
    "bread white commercially prepared toasted": "white bread",
    "tomato products canned sauce": "tomato sauce",
    "pineapple canned juice pack drained": "canned pineapple",
    "ginger root raw": "ginger root",
    "water bottled generic": "water",
    "biscuits plain or buttermilk dry mix": "biscuit mix",
    "cheese cream": "cream cheese",
    "jams and preserves": "jam",
    "jams and preserves apricot": "apricot preserves",
    "apricot dried uncooked": "dried apricot",
    "spice mustard seed ground": "ground mustard",
    "spices mustard seed ground": "ground mustard",
    "dry mustard": "ground mustard",
    "mustard dry": "ground mustard",
    "spice mustard seed yellow ground": "yellow mustard seed",
    "spices mustard seed yellow ground": "yellow mustard seed",
    "self rising white cornmeal": "cornmeal",
    "cornmeal white self rising degermed enriched": "cornmeal",
    "wheat flour white all purpose enriched bleached": "all purpose flour",
    "wheat flour white all purpose enriched unbleached": "all purpose flour",
    "baking apple": "granny smith apple",
    "baking apples": "granny smith apple",
    "butter salted": "salted butter",
    "butter without salt": "unsalted butter",
    "soup chicken broth ready to serve": "chicken broth",
    "milk buttermilk fluid whole": "whole buttermilk",
    "milk canned condensed sweetened": "sweetened condensed milk",
    "milk canned evaporated with added vitamin d and without added vitamin a": "evaporated milk",
    "cream fluid light coffee cream or table cream": "light cream",
    "cream sour cultured": "sour cream",
    "sauce ready to serve pepper or hot": "hot sauce",
    "sauce worcestershire": "worcestershire sauce",
    "sauce pizza canned ready to serve": "pizza sauce",
    "sausage italian pork mild raw": "italian sausage",
    "salami dry or hard pork beef": "salami",
    "crustaceans shrimp cooked": "cooked shrimp",
    "red delicious apples": "red delicious apple",
    "refrigerated crescent dinner rolls": "refrigerated crescent dinner roll",
    "tart apples": "tart apple",
    "wonton wrappers": "wonton wrapper",
    "mixed salad greens": "mixed salad green",
    "gingerroot": "ginger root",
    "fresh gingerroot": "ginger root",
    "grapefruit juice pink raw": "grapefruit juice",
    "gingersnap crumbs": "gingersnap cookies",
    "thickened cream": "heavy cream",
    "chicken flavored ramen noodle": "chicken flavored ramen noodles",
    "chicken flavored ramen noodles": "chicken flavored ramen noodles",
    "chicken-flavored ramen noodles": "chicken flavored ramen noodles",
    "ramen noodle": "ramen noodles",
    "chili garlic sauce": "chili-garlic sauce",
    "parsley fresh": "fresh parsley",
    "leavening agents baking soda": "baking soda",
    "lemon peel raw": "lemon peel",
    "lemons raw without peel": "fresh lemons",
    "cheese swiss": "swiss cheese",
    "cheese provolone": "provolone cheese",
    "flat leaf parsley": "fresh parsley",
    "flat-leaf parsley": "fresh parsley",
    "fresh flat leaf parsley": "fresh parsley",
    "fresh flat-leaf parsley": "fresh parsley",
    "italian parsley": "fresh parsley",
    "fresh italian parsley": "fresh parsley",
    "flat leaf italian parsley": "fresh parsley",
    "flat-leaf italian parsley": "fresh parsley",
    "fresh parsley leaves": "fresh parsley",
    "spice pepper black": "black pepper",
    "spices pepper black": "black pepper",
    "spices rosemary dried": "dried rosemary",
    "spices onion powder": "onion powder",
    "leavening agents yeast baker s active dry": "active dry yeast",
    "leavening agents baking powder double acting sodium aluminum sulfate": "baking powder",
    "baking mixes pancakes dry mix complete": "pancake mix",
    "bread stuffing dry mix": "stuffing mix",
    "spices cardamom": "cardamom",
    "nuts almonds": "almonds",
    "butter clarified butter ghee": "ghee",
    "peppers hot chili red raw": "red chili pepper",
    "shortening vegetable household composite": "shortening",
    "nuts walnuts black dried": "walnuts",
    "cream fluid heavy whipping": "heavy cream",
    "cookies gingersnaps": "gingersnap cookies",
    "wheat flour white cake enriched": "cake flour",
    "spices nutmeg ground": "nutmeg",
    "alcoholic beverage distilled all gin rum vodka whiskey 80 proof": "vodka",
    "cereals oats regular and quick not fortified dry": "oats",
    "dates deglet noor": "dates",
    "beans black mature seeds cooked boiled without salt": "black beans",
    "fish salmon atlantic farmed raw": "salmon",
    "bread crumbs dry grated plain": "breadcrumbs",
    "shallots raw": "shallot",
    "capers canned": "capers",
    "beef cured corned beef brisket raw": "corned beef",
    "potatoes red flesh and skin raw": "red potatoes",
    "rutabagas raw": "rutabaga",
    "squash summer zucchini includes skin raw": "zucchini",
    "canadian bacon cooked pan fried": "canadian bacon",
    "tomatillos raw": "tomatillo",
    "dry coconut powder": "coconut powder",
    "kraft velveeta pasteurized process cheese spread": "velveeta",
    "whipped dessert topping": "whipped topping",
    "chicken roasting meat only raw": "whole chicken",
    "pork fresh loin top loin roasts boneless separable lean and fat raw": "pork loin roast",
    "whole ham": "whole ham",
    "half ham": "whole ham",
    "bone in ham": "whole ham",
    "boneless ham": "whole ham",
    "ham roast": "whole ham",
    "ham whole cooked extra lean": "whole ham",
    "ham whole raw": "whole ham",
    "ham cured bone in": "whole ham",
    "cured bone in ham": "whole ham",
    "4 to 6 lb ham": "whole ham",
    "4 6 lb ham": "whole ham",
    "dry white vermouth": "dry vermouth",
    "sherry cooking wine": "cooking sherry",
    "chili sauce chili": "chili sauce",
    "lime peel raw": "lime peel",
    "fettuccine": "fettuccine pasta",
    "white creamed corn white": "creamed corn",
    "cheese crumbles gorgonzola": "gorgonzola cheese",
    "angel hair": "angel hair pasta",
    "campbell s condensed cheddar cheese soup 10 5 ounce can": "condensed cheddar cheese soup",
    "kellogg s toasted rice cereal rice krispies": "rice krispies cereal",
    "corn kernel": "corn",
    "corn kernels": "corn",
    "mashed ripe bananas": "banana",
    "fresh tomato": "tomato",
    "fresh tomatoes": "tomato",
    "cereals quaker quick oats dry": "oats",
    "oil or butter": "vegetable oil",
    "apples dried sulfured uncooked": "dried apples",
    "fully cooked italian style meatballs": "italian meatballs",
    "fully cooked italian style meatball": "italian meatballs",
    "frozen italian style meatballs": "italian meatballs",
    "italian style meatballs": "italian meatballs",
    "pork side rib": "pork ribs",
    "pork side ribs": "pork ribs",
    "side ribs": "pork ribs",
    "uncooked whole oats": "oats",
    "whole oats": "oats",
}

SURFACE_CANONICAL_OVERRIDES = {
    "whole ham": "whole ham",
    "fat free parmesan": "fat free parmesan",
}

SURFACE_SHOPPING_OVERRIDES = {
    "banana": "banana",
    "bananas": "banana",
    "cardamom pod": "cardamom whole",
    "cardamom pods": "cardamom whole",
    "crushed tomatoes": "crushed tomatoes",
    "egg yolk": "egg",
    "egg yolks": "egg",
    "corn kernel": "corn",
    "corn kernels": "corn",
    "fresh tomato": "tomatoes",
    "fresh tomatoes": "tomatoes",
    "gingersnap crumbs": "gingersnap cookies",
    "green bean": "fresh green beans",
    "green beans": "fresh green beans",
    "canned green bean": "canned green beans",
    "canned green beans": "canned green beans",
    "ground clove": "ground cloves",
    "lemon": "fresh lemons",
    "lemons": "fresh lemons",
    "lemon peel": "fresh lemons",
    "lemon rind": "fresh lemons",
    "lemon zest": "fresh lemons",
    "orange peel": "orange",
    "orange rind": "orange",
    "orange zest": "orange",
    "saffron thread": "saffron threads",
    "saffron threads": "saffron threads",
    "hamburger patties": "hamburger",
    "hamburger patty": "hamburger",
    "snow pea": "snow peas",
    "snow peas": "snow peas",
    "seedless grape": "seedless grapes",
    "seedless grapes": "seedless grapes",
}

RETAIL_BRIDGE_KEY_FALLBACKS = {
    "beef bologna": ["bologna"],
    "black peppercorn": ["peppercorn"],
    "black peppercorns": ["peppercorn"],
    "clove": ["ground cloves"],
    "cinnamon stick": ["cinnamon"],
    "cinnamon sticks": ["cinnamon"],
    "italian roll": ["hoagie roll", "kaiser roll", "roll"],
    "italian rolls": ["hoagie roll", "kaiser roll", "rolls"],
    "kernel corn": ["corn", "yellow corn"],
    "canned green beans": ["green beans"],
    "kosher salt": ["salt"],
    "light brown sugar": ["brown sugar", "sugar"],
    "sesame oil": ["sesame"],
    "turbinado sugar": ["sugar", "brown sugar"],
    "whole black peppercorn": ["peppercorn"],
    "whole black peppercorns": ["peppercorn"],
    "whole kernel corn": ["corn", "yellow corn"],
}

SURFACE_ESHA_OVERRIDES = {
    "egg yolk dried": ("19508", "Egg Yolk, raw, large"),
    "egg yolk": ("19508", "Egg Yolk, raw, large"),
    "egg yolks": ("19508", "Egg Yolk, raw, large"),
    "egg white": ("21111", "Egg, white, raw, large"),
    "egg whites": ("21111", "Egg, white, raw, large"),
    "pasteurized liquid egg white": ("21111", "Egg, white, raw, large"),
    "pasteurized liquid egg whites": ("21111", "Egg, white, raw, large"),
    "egg": ("19500", "Egg, whole, raw"),
    "eggs": ("19500", "Egg, whole, raw"),
    "egg whole raw": ("19500", "Egg, whole, raw"),
    "chipotle mayonnaise": ("22937", "Dressing, mayonnaise, chipotle"),
    "horseradish mayonnaise": ("33347", "Dressing, mayonnaise, horseradish"),
    "mango mayonnaise": ("22945", "Dressing, mayonnaise, mango"),
    "soy mayonnaise": ("8032", "Dressing, mayonnaise type, soybean"),
    "canadian bacon": ("12008", "Canadian Bacon, cured"),
    "back bacon": ("12008", "Canadian Bacon, cured"),
    "turkey bacon": ("13125", "Bacon, turkey"),
    "bacon bit": ("27096", "Bacon, bits, real, serving"),
    "bacon bits": ("27096", "Bacon, bits, real, serving"),
    "real bacon bit": ("27096", "Bacon, bits, real, serving"),
    "real bacon bits": ("27096", "Bacon, bits, real, serving"),
    "vegetarian bacon": ("7509", "Vegetarian Meat, bacon, strips"),
    "veggie bacon": ("7509", "Vegetarian Meat, bacon, strips"),
    "vegan bacon": ("7509", "Vegetarian Meat, bacon, strips"),
    "vegetarian bacon bit": ("27044", "Vegetarian Meat, bacon bits"),
    "vegetarian bacon bits": ("27044", "Vegetarian Meat, bacon bits"),
    "imitation bacon": ("7509", "Vegetarian Meat, bacon, strips"),
    "imitation bacon bit": ("27044", "Vegetarian Meat, bacon bits"),
    "imitation bacon bits": ("27044", "Vegetarian Meat, bacon bits"),
    "all purpose flour": ("45984", "Flour, all purpose, unbleached"),
    "80% lean ground beef": ("58121", "Beef, ground, hamburger, raw, 20% fat"),
    "granulated sugar": ("25006", "Sugar, white, granulated"),
    "biscuit mix": ("42317", "Biscuit mix"),
    "beet sugar": ("39201", "Sugar, beet, fruit"),
    "cream cheese": ("1015", "Cheese, cream"),
    "jam": ("23054", "Jam"),
    "apricot preserves": ("23299", "Preserves, apricot"),
    "dried apricot": ("48542", "Apricot, dried"),
    "ginger root": ("90442", "Spice, ginger root, fresh"),
    "ground mustard": ("26514", "Spice, mustard seed, ground"),
    "macaroni": ("38061", "Pasta, macaroni, enriched, dry"),
    "ramen noodles": ("92163", "Soup, ramen noodle, any flavor, dry"),
    "chicken flavored ramen noodles": ("28169", "Soup, ramen noodle, chicken flavor, dry"),
    "chicken broth": ("50343", "Broth, chicken, canned"),
    "chicken stock": ("50343", "Broth, chicken, canned"),
    "soup chicken broth ready to serve": ("50343", "Broth, chicken, canned"),
    "whole buttermilk": ("37935", "Buttermilk, whole"),
    "sweetened condensed milk": ("20950", "Milk, condensed, sweetened"),
    "evaporated milk": ("20952", "Milk, evaporated"),
    "light cream": ("501", "Cream, light"),
    "table cream": ("501", "Cream, light"),
    "coffee cream": ("501", "Cream, light"),
    "cream fluid light coffee cream or table cream": ("501", "Cream, light"),
    "sour cream": ("555", "Sour Cream"),
    "cream sour cultured": ("555", "Sour Cream"),
    "hot sauce": ("53470", "Sauce, hot, ready to serve"),
    "hot pepper sauce": ("53470", "Sauce, hot, ready to serve"),
    "pizza sauce": ("45487", "Sauce, pizza"),
    "mild italian sausage": ("13082", "Sausage, Italian, mild, raw"),
    "ham": ("12005", "Pork, cured ham, whole, roasted"),
    "beef stew meat": ("27997", "Beef, stew meat, chuck, raw"),
    "boneless beef stew meat": ("27997", "Beef, stew meat, chuck, raw"),
    "beef chuck stew meat": ("27997", "Beef, stew meat, chuck, raw"),
    "chuck stew meat": ("27997", "Beef, stew meat, chuck, raw"),
    "stew meat": ("27997", "Beef, stew meat, chuck, raw"),
    "pork chop": ("12028", "Pork, chop, whole loin, raw"),
    "pork chops": ("12028", "Pork, chop, whole loin, raw"),
    "italian sausage": ("13082", "Sausage, Italian, mild, raw"),
    "salami": ("13234", "Salami, FS"),
    "salami dry or hard pork beef": ("13234", "Salami, FS"),
    "cooked shrimp": ("52630", "Shrimp, untreated, cooked"),
    "crustaceans shrimp cooked": ("52630", "Shrimp, untreated, cooked"),
    "linguine": ("38591", "Pasta, semolina, linguine, dry"),
    "linguine pasta": ("38591", "Pasta, semolina, linguine, dry"),
    "self rising white cornmeal": ("38255", "Cornmeal, white, degerminated, enriched, self rising"),
    "red lentil": ("7378", "Beans, lentils, red, dried"),
    "rice vinegar": ("35186", "Vinegar, rice, 42 grain"),
    "grapefruit juice": ("794", "Juice, grapefruit"),
    "grapefruit juice pink raw": ("794", "Juice, grapefruit"),
    "onion": ("7499", "Onion, yellow, fresh, chopped"),
    "green onion": ("5709", "Onion, green, chopped, fresh"),
    "mushroom": ("7351", "Mushrooms, white, fresh"),
    "green bell pepper": ("6846", 'Peppers, sweet, bell, green, fresh, medium, 2 1/2"'),
    "green pepper": ("6846", 'Peppers, sweet, bell, green, fresh, medium, 2 1/2"'),
    "sweet green pepper": ("6846", 'Peppers, sweet, bell, green, fresh, medium, 2 1/2"'),
    "ground cinnamon": ("26003", "Spice, cinnamon, ground"),
    "ground cloves": ("26019", "Spice, cloves, ground"),
    "orange juice": ("1854", "Juice, orange"),
    "powdered sugar": ("45892", "Sugar, powdered"),
    "white wine": ("22504", "Wine, white, medium, 5 fl ounce serving"),
    "white bread": ("36160", "Bread, white, commercially prepared"),
    "tomato sauce": ("5180", "Tomato products, canned, sauce"),
    "canned pineapple": ("3912", "Pineapple, canned, juice pack, drained"),
    "spiced rum": ("22593", "Alcohol, rum, 80 proof"),
    "sake": ("22676", "Wine, sake, Japanese"),
    "coconut powder": ("63085", "Coconut, desiccated, medium"),
    "desiccated coconut": ("63085", "Coconut, desiccated, medium"),
    "velveeta": ("1272", "Cheese Spread, Velveeta, pasteurized, processed"),
    "whipped topping": ("54387", "Topping, whipped, low fat, frozen"),
    "chicken": ("15071", "Chicken, whole, unpeeled, raw"),
    "whole chicken": ("15071", "Chicken, whole, unpeeled, raw"),
    "chicken broilers or fryers meat and skin raw": ("15071", "Chicken, whole, unpeeled, raw"),
    "skin on chicken": ("15071", "Chicken, whole, unpeeled, raw"),
    "pork shoulder": ("12221", "Pork, shoulder, whole, raw"),
    "pork shoulder butt": ("12221", "Pork, shoulder, whole, raw"),
    "pork butt": ("12221", "Pork, shoulder, whole, raw"),
    "pork loin roast": ("12285", "Pork, roast, top loin, raw"),
    "whole ham": ("12170", "Pork, cured ham, whole"),
    "yellow mustard seed": ("26110", "Spice, mustard seed, yellow, ground"),
    "fat free parmesan": ("48320", "Cheese, parmesan, fat free, topping"),
    "fresh parsley": ("26013", "Herb, parsley, sprigs, fresh"),
    "parsley fresh": ("26013", "Herb, parsley, sprigs, fresh"),
    "flat leaf parsley": ("26013", "Herb, parsley, sprigs, fresh"),
    "flat-leaf parsley": ("26013", "Herb, parsley, sprigs, fresh"),
    "fresh flat leaf parsley": ("26013", "Herb, parsley, sprigs, fresh"),
    "fresh flat-leaf parsley": ("26013", "Herb, parsley, sprigs, fresh"),
    "italian parsley": ("26013", "Herb, parsley, sprigs, fresh"),
    "fresh italian parsley": ("26013", "Herb, parsley, sprigs, fresh"),
    "flat leaf italian parsley": ("26013", "Herb, parsley, sprigs, fresh"),
    "flat-leaf italian parsley": ("26013", "Herb, parsley, sprigs, fresh"),
    "fresh parsley leaves": ("26013", "Herb, parsley, sprigs, fresh"),
}

SURFACE_ESHA_NUTRITION_PRIORITY = {
    "macaroni",
    "ramen noodles",
    "chicken flavored ramen noodles",
}

SURFACE_SR28_NUTRITION_OVERRIDES = {
    "egg": ("171287", "Egg, whole, raw, fresh"),
    "eggs": ("171287", "Egg, whole, raw, fresh"),
    "egg whole raw": ("171287", "Egg, whole, raw, fresh"),
    "egg yolk": ("172184", "Egg, yolk, raw, fresh"),
    "egg yolks": ("172184", "Egg, yolk, raw, fresh"),
    "egg white": ("172183", "Egg, white, raw, fresh"),
    "egg whites": ("172183", "Egg, white, raw, fresh"),
    "pasteurized liquid egg white": ("172183", "Egg, white, raw, fresh"),
    "pasteurized liquid egg whites": ("172183", "Egg, white, raw, fresh"),
    "chicken": ("171447", "Chicken, broilers or fryers, meat and skin, raw"),
    "bacon bit": ("168322", "Pork, cured, bacon, pre-sliced, cooked, pan-fried"),
    "bacon bits": ("168322", "Pork, cured, bacon, pre-sliced, cooked, pan-fried"),
    "real bacon bit": ("168322", "Pork, cured, bacon, pre-sliced, cooked, pan-fried"),
    "real bacon bits": ("168322", "Pork, cured, bacon, pre-sliced, cooked, pan-fried"),
    "sake": ("167723", "Alcoholic beverage, rice (sake)"),
    "beef stew meat": ("170810", "Beef, chuck for stew, separable lean and fat, choice, raw"),
    "boneless beef stew meat": ("170810", "Beef, chuck for stew, separable lean and fat, choice, raw"),
    "beef chuck stew meat": ("170810", "Beef, chuck for stew, separable lean and fat, choice, raw"),
    "chuck stew meat": ("170810", "Beef, chuck for stew, separable lean and fat, choice, raw"),
    "stew meat": ("170810", "Beef, chuck for stew, separable lean and fat, choice, raw"),
    "pork chop": ("169194", "Pork, fresh, loin, blade (chops or roasts), boneless, separable lean only, raw"),
    "pork chops": ("169194", "Pork, fresh, loin, blade (chops or roasts), boneless, separable lean only, raw"),
    "dried apple": ("171691", "Apples, dried, sulfured, uncooked"),
    "dried apples": ("171691", "Apples, dried, sulfured, uncooked"),
    "italian meatballs": ("171638", "Meatballs, frozen, Italian style"),
    "fully cooked italian style meatballs": ("171638", "Meatballs, frozen, Italian style"),
    "whole chicken": ("171447", "Chicken, broilers or fryers, meat and skin, raw"),
    "skin on chicken": ("171447", "Chicken, broilers or fryers, meat and skin, raw"),
    "chicken broilers or fryers meat and skin raw": ("171447", "Chicken, broilers or fryers, meat and skin, raw"),
    "pork shoulder": ("167849", "Pork, fresh, shoulder, (Boston butt), blade (steaks), separable lean and fat, raw"),
    "pork shoulder butt": ("167849", "Pork, fresh, shoulder, (Boston butt), blade (steaks), separable lean and fat, raw"),
    "pork butt": ("167849", "Pork, fresh, shoulder, (Boston butt), blade (steaks), separable lean and fat, raw"),
    "kosher salt": ("173468", "Salt, table"),
    "black peppercorn": ("170931", "Spices, pepper, black"),
    "black peppercorns": ("170931", "Spices, pepper, black"),
    "whole black peppercorn": ("170931", "Spices, pepper, black"),
    "whole black peppercorns": ("170931", "Spices, pepper, black"),
    "fettuccine": ("169736", "Pasta, dry, enriched"),
    "fettuccine pasta": ("169736", "Pasta, dry, enriched"),
    "angel hair": ("169736", "Pasta, dry, enriched"),
    "angel hair pasta": ("169736", "Pasta, dry, enriched"),
}

SURFACE_NO_ESHA_SR28_OVERRIDES = {
    "canning salt": ("173468", "Salt, table", "", "no exact local ESHA canning salt row; use SR28 salt nutrition and canning-salt shopping products"),
    "dried italian seasoning": ("171328", "Spices, oregano, dried", "", "local Italian-seasoning ESHA row is nutrition_unknown; use oregano as reviewed SR28 dried-herb proxy"),
    "italian meatballs": ("171638", "Meatballs, frozen, Italian style", "", "local Italian-meatballs surface has no verified nutrition anchor; use SR28 frozen Italian meatballs"),
    "italian seasoning": ("171328", "Spices, oregano, dried", "", "local Italian-seasoning ESHA row is nutrition_unknown; use oregano as reviewed SR28 dried-herb proxy"),
    "kosher salt": ("173468", "Salt, table", "", "local kosher-salt ESHA row has no verified nutrition anchor; use SR28 salt nutrition and kosher-salt shopping products"),
    "pickling salt": ("173468", "Salt, table", "", "no exact local ESHA pickling salt row; use SR28 salt nutrition and pickling-salt shopping products"),
    "canning and pickling salt": ("173468", "Salt, table", "canning pickling salt", "no exact local ESHA canning/pickling salt row; use SR28 salt nutrition and exact shopping products"),
}

SURFACE_MANUAL_FNDDS_OVERRIDES = {
    "chocolate sandwich cookie": ("53209015", "Cookie, chocolate sandwich", "chocolate sandwich cookie"),
    "chocolate sandwich cookies": ("53209015", "Cookie, chocolate sandwich", "chocolate sandwich cookie"),
    "chocolate sandwich cooky": ("53209015", "Cookie, chocolate sandwich", "chocolate sandwich cookie"),
    "canned spaghetti in tomato sauce": ("58146150", "Pasta with tomato-based sauce and cheese", "spaghetti in tomato sauce"),
    "orange flavored sweetened drink mix": ("92900110", "Fruit flavored drink, powdered, not reconstituted", "orange drink mix"),
    "orange drink mix": ("92900110", "Fruit flavored drink, powdered, not reconstituted", "orange drink mix"),
    "orange flavored drink mix": ("92900110", "Fruit flavored drink, powdered, not reconstituted", "orange drink mix"),
    "strawberry pie filling": ("63203701", "Pie filling, NFS", "strawberry pie filling"),
    "spaghetti in tomato sauce": ("58146150", "Pasta with tomato-based sauce and cheese", "spaghetti in tomato sauce"),
}

SURFACE_NON_INGREDIENT_EXACT = {
    "aluminum foil",
    "aluminium foil",
    "plastic wrap",
    "quart size ziploc bags",
    "quart sized ziploc bags",
    "ziploc bag",
    "ziploc bags",
}

SURFACE_NUTRITION_CLEARS = {
    "bottled water": "water_is_not_a_planner_purchase",
    "soft egg sandwich bun": "egg_word_is_bread_product_not_shell_egg",
    "soft egg sandwich buns": "egg_word_is_bread_product_not_shell_egg",
    "stock": "generic_stock_requires_source_animal_or_vegetable",
    "tap water": "water_is_not_a_planner_purchase",
    "water": "water_is_not_a_planner_purchase",
    "water bottled generic": "water_is_not_a_planner_purchase",
}

SURFACE_ESHA_CLEARS = {
    "cinnamon sugar": "wrong_esha_cinnamon_brown_sugar_topping",
    "creme de menthe": "wrong_esha_vodka",
    "creme de cacao": "wrong_esha_vodka",
    "pasta": "wrong_esha_crispy_pasta",
    "dry pasta": "wrong_esha_corn_pasta",
    "fettuccine": "wrong_esha_macaroni_shape",
    "fettuccine pasta": "wrong_esha_macaroni_shape",
    "angel hair": "wrong_esha_refrigerated_pasta_form",
    "angel hair pasta": "wrong_esha_refrigerated_pasta_form",
    "veal": "wrong_esha_veal_heart",
}

TEXT_FALLBACK_BLOCKLIST = {
    "hamburger patties",
    "hamburger patty",
    "stock",
    "veal",
}


def normalize_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ").replace("|", " ")
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", text).split())


def _manual_fndds_row(text: str) -> dict[str, str] | None:
    key = normalize_key(text)
    match = SURFACE_MANUAL_FNDDS_OVERRIDES.get(key)
    if not match:
        return None
    code, description, canonical = match
    return {
        "canonical_surface": text,
        "canonical_normalized": canonical,
        "canonical_shopping_item": canonical,
        "record_type": "ingredient",
        "nutrition_code": f"FNDDS:{code}",
        "nutrition_code_type": "fndds_reference_match",
        "nutrition_match_state": "fndds_match",
        "sr28_code": "",
        "sr28_description": "",
        "sr28_match_type": "",
        "fndds_code": code,
        "fndds_description": description,
        "fndds_match_type": "surface_lab_manual_exact",
        "esha_code": "",
        "esha_description": "",
        "esha_match_type": "reviewed_no_esha_target:surface_lab",
        "product_query": canonical,
    }


def _sr28_override_surface_row(key: str, display: str | None = None) -> dict[str, str] | None:
    match = SURFACE_SR28_NUTRITION_OVERRIDES.get(normalize_key(key))
    if not match:
        return None
    code, description = match
    canonical = normalize_key(key)
    return {
        "canonical_surface": display or key,
        "canonical_normalized": canonical,
        "canonical_shopping_item": canonical,
        "record_type": "ingredient",
        "nutrition_code": f"SR28:{code}",
        "nutrition_code_type": "sr28_reference_match",
        "nutrition_match_state": "sr28_match",
        "sr28_code": code,
        "sr28_description": description,
        "sr28_match_type": "surface_lab_sr28_override_synthetic",
        "fndds_code": "",
        "fndds_description": "",
        "fndds_match_type": "",
        "esha_code": "",
        "esha_description": "",
        "esha_match_type": "reviewed_no_esha_target:surface_lab",
        "product_query": canonical,
    }


def _load_surface_rows() -> list[dict[str, str]]:
    global _SURFACE_ROWS
    if _SURFACE_ROWS is not None:
        return _SURFACE_ROWS
    with SURFACE_CSV.open(newline="", encoding="utf-8-sig") as handle:
        _SURFACE_ROWS = list(csv.DictReader(handle))
    return _SURFACE_ROWS


def _load_api_cache_products() -> dict[str, list[LabProduct]]:
    global _API_CACHE_PRODUCTS
    if _API_CACHE_PRODUCTS is not None:
        return _API_CACHE_PRODUCTS
    out: dict[str, list[LabProduct]] = {}
    if not API_CACHE_PRODUCTS_CSV.exists():
        _API_CACHE_PRODUCTS = out
        return out
    with API_CACHE_PRODUCTS_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if len(row) < 6:
                continue
            source, gtin_upc, description, _grams, _cents, canonical = row[:6]
            key = normalize_key(canonical)
            if not key or not description:
                continue
            out.setdefault(key, []).append(
                LabProduct(
                    gtin_upc=(gtin_upc or "").strip(),
                    description=description.strip(),
                    brand_name=source.strip(),
                    category="api cache",
                    source="api_cache_exact",
                )
            )
    _API_CACHE_PRODUCTS = out
    return out


def _surface_index() -> dict[str, list[dict[str, str]]]:
    global _SURFACE_INDEX
    if _SURFACE_INDEX is not None:
        return _SURFACE_INDEX
    index: dict[str, list[dict[str, str]]] = {}
    for row in _load_surface_rows():
        for field in ("canonical_surface", "canonical_normalized", "canonical_shopping_item"):
            key = normalize_key(row.get(field, ""))
            if key:
                index.setdefault(key, []).append(row)
    _SURFACE_INDEX = index
    return index


def _row_score(row: dict[str, str], query_key: str) -> tuple[int, int, int, int]:
    record_score = 1 if (row.get("record_type") or "") == "ingredient" else 0
    surface_score = 1 if normalize_key(row.get("canonical_surface", "")) == query_key else 0
    nutrition_score = 1 if _row_has_reviewed_nutrition(row) else 0
    esha_score = 1 if (row.get("esha_code") or "").strip() else 0
    return record_score, surface_score, nutrition_score, esha_score


def _best_surface_row(candidates: list[dict[str, str]], query_key: str) -> dict[str, str] | None:
    if not candidates:
        return None
    return max(candidates, key=lambda row: _row_score(row, query_key))


def _load_approved_rules() -> tuple[dict[str, str], list[tuple[re.Pattern[str], str, str]]]:
    global _APPROVED_EXACT, _APPROVED_REGEX
    if _APPROVED_EXACT is not None and _APPROVED_REGEX is not None:
        return _APPROVED_EXACT, _APPROVED_REGEX
    exact: dict[str, str] = {}
    regexes: list[tuple[re.Pattern[str], str, str]] = []
    if APPROVED_RULES_CSV.exists():
        with APPROVED_RULES_CSV.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                if (row.get("status") or "").strip() != "approved":
                    continue
                surface = (row.get("input_surface") or "").strip()
                concept_key = (row.get("canonical_concept_key") or "").strip()
                if not surface or not concept_key:
                    continue
                match_type = (row.get("match_type") or "").strip()
                if match_type == "exact":
                    exact.setdefault(normalize_key(surface), concept_key)
                elif match_type == "regex":
                    try:
                        regexes.append((re.compile(surface, re.I), concept_key, row.get("rule_id", "")))
                    except re.error:
                        continue
    _APPROVED_EXACT = exact
    _APPROVED_REGEX = regexes
    return exact, regexes


def _concept_base(concept_key: str) -> str:
    return (concept_key or "").split("|", 1)[0].strip()


def _expand_regex_concept_key(regex: re.Pattern[str], concept_key: str, text: str) -> str:
    if "\\" not in concept_key:
        return concept_key
    try:
        return regex.sub(concept_key, text, count=1)
    except re.error:
        return concept_key


def _load_fndds_per_100g() -> dict[str, dict[str, float]]:
    global _FNDDS_PER_100G
    if _FNDDS_PER_100G is not None:
        return _FNDDS_PER_100G
    out: dict[str, dict[str, float]] = {}
    if FNDDS_NUTRIENTS_CSV.exists():
        with FNDDS_NUTRIENTS_CSV.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                code = (row.get("fndds_code") or "").strip()
                if not code:
                    continue
                try:
                    out[code] = {
                        "kcal": float(row.get("energy_kcal") or 0),
                        "protein": float(row.get("protein_g") or 0),
                        "fat": float(row.get("fat_g") or 0),
                        "carbs": float(row.get("carbs_g") or 0),
                    }
                except ValueError:
                    continue
    _FNDDS_PER_100G = out
    return out


def _load_esha_pack_index() -> dict[str, Path]:
    global _ESHA_PACK_INDEX
    if _ESHA_PACK_INDEX is not None:
        return _ESHA_PACK_INDEX
    out: dict[str, Path] = {}
    if ESHA_PACK_INDEX_CSV.exists():
        with ESHA_PACK_INDEX_CSV.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                code = (row.get("esha_code") or "").strip()
                pack_path = (row.get("pack_path") or "").strip()
                if code and pack_path:
                    out[code] = Path(pack_path)
    _ESHA_PACK_INDEX = out
    return out


def _score_num(row: dict[str, str]) -> float:
    for field in ("score_num", "score"):
        raw = (row.get(field) or "").strip()
        if not raw:
            continue
        try:
            return float(raw)
        except ValueError:
            continue
    return 0.0


def _load_product_map_index() -> dict[str, list[LabProduct]]:
    global _PRODUCT_MAP_INDEX
    if _PRODUCT_MAP_INDEX is not None:
        return _PRODUCT_MAP_INDEX
    buckets: dict[str, list[tuple[float, LabProduct]]] = {}
    if not PRODUCT_ESHA_MAP_CSV.exists():
        _PRODUCT_MAP_INDEX = {}
        return _PRODUCT_MAP_INDEX

    with PRODUCT_ESHA_MAP_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        for row in reader:
            code = (row.get("best_esha_code") or "").strip()
            description = (row.get("product_description") or "").strip()
            if not code or not description:
                continue
            product = LabProduct(
                gtin_upc=(row.get("gtin_upc") or "").strip(),
                description=description,
                brand_name=(row.get("brand_name") or row.get("brand_owner") or "").strip(),
                category=(row.get("branded_food_category") or "").strip(),
                source="concept_anchor_map",
            )
            buckets.setdefault(code, []).append((_score_num(row), product))

    index: dict[str, list[LabProduct]] = {}
    for code, scored_products in buckets.items():
        scored_products.sort(key=lambda item: item[0], reverse=True)
        index[code] = [product for _, product in scored_products[:PRODUCT_MAP_PRODUCTS_PER_CODE]]
    _PRODUCT_MAP_INDEX = index
    return index


def _product_map_products(esha_code: str, limit: int = 25) -> list[LabProduct]:
    code = (esha_code or "").strip()
    if not code:
        return []
    return list(_load_product_map_index().get(code, [])[:limit])


def _index_bridge_product(out: dict[str, list[LabProduct]], key: str, product: LabProduct) -> None:
    norm = normalize_key(key)
    if norm:
        out.setdefault(norm, []).append(product)


def _load_retail_surface_bridge_products() -> dict[str, list[LabProduct]]:
    global _RETAIL_SURFACE_BRIDGE_PRODUCTS
    if _RETAIL_SURFACE_BRIDGE_PRODUCTS is not None:
        return _RETAIL_SURFACE_BRIDGE_PRODUCTS
    out: dict[str, list[LabProduct]] = {}
    if not RETAIL_SURFACE_BRIDGE_CSV.exists():
        _RETAIL_SURFACE_BRIDGE_PRODUCTS = out
        return out

    with RETAIL_SURFACE_BRIDGE_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        for row in reader:
            if (row.get("canonical_match_status") or "").strip() != "assigned":
                continue
            product_name = (row.get("name") or "").strip()
            if not product_name:
                continue
            retail_source = (row.get("retail_source") or row.get("source") or "").strip()
            product = LabProduct(
                gtin_upc=(row.get("upc") or row.get("gtin_upc") or "").strip(),
                description=product_name,
                brand_name=retail_source,
                category="",
                source=f"retail_surface_bridge:{retail_source}" if retail_source else "retail_surface_bridge",
            )
            for field in (
                "search_term",
                "canonical_surface",
                "canonical_normalized",
                "canonical_shopping_item",
                "product_query",
            ):
                _index_bridge_product(out, row.get(field, ""), product)

    for products in out.values():
        products.sort(key=lambda product: (0 if product.source.endswith(":walmart") else 1, product.description.lower()))

    _RETAIL_SURFACE_BRIDGE_PRODUCTS = out
    return out


def _retail_surface_products(shopping_query: str, limit: int = 100) -> list[LabProduct]:
    key = normalize_key(shopping_query)
    if not key:
        return []
    seen: set[tuple[str, str]] = set()
    products: list[LabProduct] = []
    bridge = _load_retail_surface_bridge_products()
    lookup_keys = [key, *RETAIL_BRIDGE_KEY_FALLBACKS.get(key, [])]
    for lookup_key in lookup_keys:
        for product in bridge.get(lookup_key, []):
            dedupe_key = (product.source, product.gtin_upc or product.description)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            products.append(product)
            if len(products) >= limit:
                return products
    return products


def _split_md_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


_BRIDGE_DB_PATH = "/Users/jamiebarton/Desktop/Hestia/api/data/canonical_retail_bridge.db"
_BRIDGE_BY_KEY: dict[str, dict] | None = None
_MASTER_PRODUCTS_DB = "/Users/jamiebarton/Desktop/esha_audit_bundle/data/master_products.db"


def _load_canonical_retail_bridge() -> dict[str, dict]:
    global _BRIDGE_BY_KEY
    if _BRIDGE_BY_KEY is not None:
        return _BRIDGE_BY_KEY
    out: dict[str, dict] = {}
    try:
        conn = sqlite3.connect(_BRIDGE_DB_PATH)
        for ck, exp_path, exp_paths, allowed_var, allowed_form, allowed_proc, forbid, allow_fl, allow_co, n in conn.execute(
            "SELECT canonical_key, expected_canonical_path, expected_canonical_paths, allowed_variants, "
            "allowed_forms, allowed_processing_storage, forbidden_modifiers, "
            "allow_flavored, allow_combo, audit_row_count "
            "FROM canonical_retail_bridge"
        ):
            expected_paths = []
            if exp_paths:
                try:
                    expected_paths = json.loads(exp_paths)
                except Exception:
                    expected_paths = []
            out[ck] = {
                "expected_canonical_path": exp_path,
                "expected_canonical_paths": expected_paths,
                "allowed_variants": json.loads(allowed_var) if allowed_var else None,
                "allowed_forms": json.loads(allowed_form) if allowed_form else None,
                "allowed_processing_storage": json.loads(allowed_proc) if allowed_proc else None,
                "forbidden_modifiers": json.loads(forbid) if forbid else [],
                "allow_flavored": bool(allow_fl),
                "allow_combo": bool(allow_co),
                "audit_row_count": n,
            }
        conn.close()
    except Exception:
        pass
    _BRIDGE_BY_KEY = out
    return out


def _audit_path_products(canonical: str, limit: int = 25) -> list[LabProduct]:
    """Step D (Part 6): pull candidate UPCs from product_audit_classification
    where the canonical_path matches the canonical's expected path from the
    canonical_retail_bridge. Hydrate each UPC from master_products.products
    for description + brand. Solves the cache-poor case: canonicals like
    'macaroni' / 'white sugar' where the existing chain returns only
    salads/dinners/flavored variants."""
    canonical_key = normalize_key(canonical)
    bridge = _load_canonical_retail_bridge()
    spec = bridge.get(canonical_key)
    forbidden_modifiers: set[str] = set()
    # Fall back to hard-coded expectation dict if bridge has no row
    if not spec or not spec.get("expected_canonical_path"):
        hard = _CANONICAL_AUDIT_EXPECTATION.get(canonical_key)
        if not hard:
            return []
        prefixes, hard_forbidden = hard
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        if not prefixes:
            return []
        forbidden_modifiers = set(hard_forbidden or [])
    else:
        prefixes = [spec["expected_canonical_path"]]
        # Bridge stores forbidden_modifiers as a comma-joined string; tolerate list/None too
        raw_forbidden = spec.get("forbidden_modifiers")
        if isinstance(raw_forbidden, str) and raw_forbidden.strip():
            forbidden_modifiers = {t.strip().lower() for t in raw_forbidden.split(",") if t.strip()}
        elif isinstance(raw_forbidden, (list, tuple, set)):
            forbidden_modifiers = {str(t).strip().lower() for t in raw_forbidden if str(t).strip()}
        # Hard-coded forbidden as a fallback layer (audit bridge alone can be sparse)
        hard = _CANONICAL_AUDIT_EXPECTATION.get(canonical_key)
        if hard:
            _, hard_forbidden = hard
            if hard_forbidden:
                forbidden_modifiers |= set(hard_forbidden)
    if not prefixes:
        return []
    # Query classification table for UPCs whose canonical_path starts with the expected
    upcs: list[str] = []
    try:
        conn = sqlite3.connect(_AUDIT_CLASS_DB_PATH)
        for prefix in prefixes:
            for (upc,) in conn.execute(
                "SELECT upc FROM product_audit_classification "
                "WHERE canonical_path LIKE ? "
                "AND classification_method != 'unclassified' "
                "AND audit_confidence >= 0.50 "
                "LIMIT ?",
                (prefix + "%", limit * 4),
            ):
                if upc:
                    upcs.append(str(upc))
            if len(upcs) >= limit * 2:
                break
        conn.close()
    except Exception:
        return []
    if not upcs:
        return []
    # Dedup
    seen: set[str] = set()
    upcs_uniq: list[str] = []
    for u in upcs:
        if u in seen:
            continue
        seen.add(u)
        upcs_uniq.append(u)
        if len(upcs_uniq) >= limit:
            break
    # Hydrate from master_products
    products: list[LabProduct] = []
    try:
        mp = sqlite3.connect(_MASTER_PRODUCTS_DB)
        # Query in a single IN statement (sqlite param limit ~999, we have <= 25)
        # GTINs vary across DBs: classification stores stripped (e.g.
        # 78742230498), master_products stores zero-padded to 12-digit
        # (078742230498) or 13-digit (0078742230498). Try all common widths.
        variants: set[str] = set()
        for u in upcs_uniq:
            stripped = u.lstrip("0") or "0"
            variants.add(stripped)
            variants.add(u)
            variants.add(stripped.zfill(12))
            variants.add(stripped.zfill(13))
            variants.add(stripped.zfill(14))
        variant_list = list(variants)
        placeholders = ",".join("?" for _ in variant_list)
        rows = mp.execute(
            f"SELECT gtin_upc, description, brand_name, branded_food_category "
            f"FROM products WHERE gtin_upc IN ({placeholders})",
            tuple(variant_list),
        ).fetchall()
        mp.close()
        for upc, desc, brand, cat in rows:
            desc_l = (desc or "").lower()
            brand_l = (brand or "").lower()
            # Apply forbidden_modifier filter before returning. Audit can
            # mis-classify combo products (e.g. Mac & Cheese Dinner under
            # Pantry > Pasta > Macaroni > Enriched). Title token check is the
            # safety net.
            if forbidden_modifiers and any(
                tok and tok in desc_l for tok in forbidden_modifiers
            ):
                continue
            products.append(LabProduct(
                gtin_upc=str(upc or ""),
                description=str(desc or ""),
                brand_name=str(brand or ""),
                category=str(cat or ""),
                source="audit_path_lookup",
            ))
    except Exception:
        return []
    return products[:limit]


def _esha_pack_products(esha_code: str, limit: int = 25) -> list[LabProduct]:
    if PRODUCT_ESHA_LOOKUP_DB.exists() and PRODUCT_ESHA_LOOKUP_DB.stat().st_size > 0:
        try:
            with sqlite3.connect(PRODUCT_ESHA_LOOKUP_DB) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT
                        gtin_upc,
                        product_description,
                        brand_name,
                        branded_food_category
                    FROM product_esha_assignments
                    WHERE esha_code = ?
                    ORDER BY match_score DESC, assignment_rank ASC
                    LIMIT ?
                    """,
                    (esha_code, limit),
                ).fetchall()
            if rows:
                return [
                    LabProduct(
                        gtin_upc=str(row["gtin_upc"] or ""),
                        description=str(row["product_description"] or ""),
                        brand_name=str(row["brand_name"] or ""),
                        category=str(row["branded_food_category"] or ""),
                        source="esha_reviewed_lookup",
                    )
                    for row in rows
                ]
        except sqlite3.Error:
            pass

    products = _product_map_products(esha_code, limit=limit)
    if products:
        return products

    pack_path = _load_esha_pack_index().get(esha_code)
    if not pack_path or not pack_path.exists():
        return []
    products: list[LabProduct] = []
    section = ""
    in_table = False
    for line in pack_path.read_text(encoding="utf-8").splitlines():
        if line == "## Candidate Clean Products":
            section = "candidate_clean"
            in_table = False
            continue
        if line == "## Rows To Clean Up":
            section = "rows_to_cleanup"
            in_table = False
            continue
        if line.startswith("## ") and section:
            section = ""
            in_table = False
            continue
        if section != "candidate_clean":
            continue
        if line.startswith("| rank | gtin_upc | fdc_id | description | category |"):
            in_table = True
            continue
        if not in_table or line.startswith("| ---") or not line.startswith("| "):
            continue
        parts = _split_md_row(line)
        if len(parts) == 7:
            _, gtin_upc, _, description, category, _, _ = parts
        elif len(parts) == 8:
            _, gtin_upc, _, description, category, _, _, _ = parts
        else:
            continue
        products.append(
            LabProduct(
                gtin_upc=gtin_upc,
                description=description,
                brand_name="",
                category=category,
                source="esha_pack_candidate_clean",
            )
        )
        if len(products) >= limit:
            break
    return products


def _is_retail_bridge_product(product: LabProduct) -> bool:
    return (product.source or "").startswith("retail_surface_bridge")


def _product_text(product: LabProduct) -> str:
    if _is_retail_bridge_product(product):
        return normalize_key(f"{product.description} {product.brand_name}")
    return normalize_key(f"{product.description} {product.brand_name} {product.category}")


def _product_tokens(product: LabProduct) -> set[str]:
    return set(_product_text(product).split())


def _has_phrase(text: str, phrase: str) -> bool:
    return f" {normalize_key(text)} ".find(f" {normalize_key(phrase)} ") >= 0


_COMBO_DEMOTE_CONFIDENCE_THRESHOLD = 0.50


def _reject_combo_product(canonical: str, product: LabProduct) -> str:
    """Combo / prepared / kit detector. Step C (Part 3) demotes this to
    unclassified-fallback only — when the product has a confident audit
    classification AND its canonical_path is plausibly compatible with the
    canonical, we DO NOT combo-reject. The structured matcher (accept_via_audit)
    has already had a chance to decide; combo_product should not override it
    for classified products.
    """
    canonical_tokens = set(normalize_key(canonical).split())
    product_tokens = _product_tokens(product)
    combo_terms = {
        "bar", "bars", "blend", "bread", "casserole", "chips", "dinner",
        "dinners", "entree", "fry", "medley", "mix", "mixed", "pasta",
        "salad", "side", "sides", "stir", "tortilla", "tortillas",
    }
    extra_combo = product_tokens & (combo_terms - canonical_tokens)
    if not extra_combo:
        return ""

    # Step C demote rule: if the product has a confident audit classification
    # whose canonical_path leaf token-overlaps the canonical, the audit's
    # decision wins over the title blocklist.
    upc = (product.gtin_upc or "").strip()
    if upc:
        classes = _load_audit_class_by_upc()
        cls = classes.get(upc) or classes.get(upc.lstrip("0"))
        if cls:
            canonical_path, variant, flavor, ftc, ps, conf, method = cls
            if (
                method != "unclassified"
                and conf >= _COMBO_DEMOTE_CONFIDENCE_THRESHOLD
                and canonical_path
            ):
                # Last segment of the audit's canonical_path — the "leaf" food.
                leaf = canonical_path.split(" > ")[-1].lower()
                leaf_tokens = {t for t in re.findall(r"[a-z0-9]+", leaf) if len(t) > 1}
                # If the canonical's tokens overlap with the audit's leaf tokens,
                # trust the audit. Example: macaroni canonical, audit leaf
                # "Macaroni" -> overlap, do not combo-reject even if title has
                # "pasta".
                if canonical_tokens & leaf_tokens:
                    return ""
                # Or: forbid only when the audit explicitly says this is a
                # kit/prepared/salad path.
                bad_path_tokens = {"salad", "kit", "kits", "dinner", "dinners",
                                    "casserole", "meal", "meals", "prepared"}
                path_tokens = {
                    t for t in re.findall(r"[a-z0-9]+", canonical_path.lower())
                    if len(t) > 1
                }
                if not (path_tokens & bad_path_tokens):
                    return ""

    return "combo_or_prepared_product:" + "/".join(sorted(extra_combo))


def _product_desc(product: LabProduct) -> str:
    return normalize_key(product.description)


def _product_category(product: LabProduct) -> str:
    return normalize_key(product.category)


def _contains_phrase(text: str, phrase: str) -> bool:
    return f" {text} ".find(f" {normalize_key(phrase)} ") >= 0


def _accept_milk_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    if canonical_key not in {"milk", "whole milk", "skim milk", "nonfat milk", "low fat milk", "lowfat milk", "reduced fat milk"}:
        return None
    desc = _product_desc(product)
    category = _product_category(product)
    text = _product_text(product)
    tokens = set(text.split())
    if "milk" not in tokens:
        return False, "missing_milk_identity"
    plant_or_species = {
        "almond",
        "cashew",
        "coconut",
        "flax",
        "goat",
        "hemp",
        "macadamia",
        "oat",
        "pea",
        "rice",
        "sheep",
        "soy",
    }
    plant_hit = tokens & plant_or_species
    if plant_hit:
        return False, "plant_or_species_milk:" + "/".join(sorted(plant_hit))
    flavored = tokens & {
        "banana",
        "beverage",
        "chocolate",
        "cocoa",
        "coffee",
        "drink",
        "flavored",
        "latte",
        "mocha",
        "nesquik",
        "protein",
        "shake",
        "smoothie",
        "strawberry",
        "vanilla",
    }
    if flavored:
        return False, "flavored_or_supplement_milk:" + "/".join(sorted(flavored))
    other_dairy = tokens & {"butter", "buttermilk", "cheese", "cream", "creamer", "evaporated", "condensed", "kefir", "powder", "powdered", "yogurt"}
    if other_dairy:
        return False, "different_dairy_product:" + "/".join(sorted(other_dairy))
    if (
        not any(term in category for term in ("milk", "dairy"))
        and product.source != "esha_pack_candidate_clean"
        and not _is_retail_bridge_product(product)
    ):
        return False, "milk_requires_milk_category"
    whole_blockers = tokens & {"1", "1%", "2", "2%", "fat", "free", "lactose", "lowfat", "nonfat", "reduced", "skim"}
    if canonical_key in {"milk", "whole milk"}:
        if whole_blockers:
            return False, "not_whole_milk:" + "/".join(sorted(whole_blockers))
        if canonical_key == "milk" and desc == "milk":
            return True, "plain_whole_milk_label"
        if "whole" in tokens or _contains_phrase(desc, "vitamin d milk"):
            return True, "whole_milk_label"
        return False, "missing_whole_milk_identity"
    if canonical_key in {"skim milk", "nonfat milk"}:
        if _contains_phrase(desc, "fat free") or "skim" in tokens or "nonfat" in tokens or "0%" in tokens:
            return True, "skim_nonfat_milk_label"
        return False, "missing_skim_nonfat_identity"
    if canonical_key in {"low fat milk", "lowfat milk"}:
        if tokens & {"2%", "reduced", "skim", "nonfat", "whole"} or _contains_phrase(desc, "fat free"):
            return False, "not_lowfat_one_percent_milk"
        if "lowfat" in tokens or _contains_phrase(desc, "low fat") or "1%" in tokens:
            return True, "lowfat_one_percent_milk_label"
        return False, "missing_lowfat_one_percent_identity"
    if canonical_key == "reduced fat milk":
        if tokens & {"1%", "lowfat", "skim", "nonfat", "whole"} or _contains_phrase(desc, "low fat") or _contains_phrase(desc, "fat free"):
            return False, "not_reduced_fat_two_percent_milk"
        if _contains_phrase(desc, "reduced fat") or "2%" in tokens:
            return True, "reduced_fat_two_percent_milk_label"
        return False, "missing_reduced_fat_two_percent_identity"
    return True, "plain_milk_label"


def _accept_egg_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    if canonical_key not in {"egg", "eggs"}:
        return None
    category = _product_category(product)
    desc_tokens = set(_product_desc(product).split())
    if "egg" not in desc_tokens and "eggs" not in desc_tokens:
        return False, "missing_egg_identity"
    reject = desc_tokens & {
        "beater",
        "beaters",
        "bite",
        "bites",
        "based",
        "liquid",
        "omelet",
        "patty",
        "patties",
        "plant",
        "product",
        "products",
        "sandwich",
        "substitute",
        "substitutes",
        "vegan",
        "white",
        "whites",
        "yolk",
        "yolks",
        "mates",
    }
    if reject:
        return False, "not_plain_shell_egg:" + "/".join(sorted(reject))
    if any(term in category for term in ("egg", "eggs")) or _is_retail_bridge_product(product):
        return True, "plain_shell_egg_label"
    return False, "egg_requires_egg_category"


def _accept_mayonnaise_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    if canonical_key != "mayonnaise":
        return None
    category = _product_category(product)
    desc = _product_desc(product)
    tokens = set(desc.split())
    has_mayo_identity = "mayonnaise" in tokens or _contains_phrase(desc, "real mayonnaise")
    if not has_mayo_identity:
        return False, "missing_mayonnaise_identity"
    reject = tokens & {
        "aioli",
        "avocado",
        "bacon",
        "canola",
        "chipotle",
        "fat",
        "flavored",
        "flavour",
        "free",
        "garlic",
        "horseradish",
        "jalapeno",
        "japanese",
        "ketchup",
        "lime",
        "lite",
        "light",
        "low",
        "lowfat",
        "olive",
        "oil",
        "nonfat",
        "pesto",
        "plant",
        "reduced",
        "safflower",
        "serrano",
        "spicy",
        "truffle",
        "vegan",
        "yolk",
    }
    if reject:
        return False, "not_plain_mayonnaise:" + "/".join(sorted(reject))
    if any(term in category for term in ("condiment", "dressing", "mayonnaise", "sauce", "spread")):
        return True, "plain_mayonnaise_label"
    return False, "mayonnaise_requires_condiment_category"


def _accept_oil_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    if canonical_key not in {"oil", "vegetable oil", "peanut oil", "sesame oil", "toasted sesame oil", "olive oil", "extra virgin olive oil"}:
        return None
    desc = _product_desc(product)
    category = _product_category(product)
    tokens = set(_product_text(product).split())
    if "oil" not in tokens and "oils" not in tokens:
        return False, "missing_oil_identity"
    product_form_noise = tokens & {
        "bar",
        "bean",
        "beans",
        "beancurd",
        "butter",
        "dressing",
        "marinade",
        "sauce",
        "snack",
        "snacks",
        "spray",
        "spread",
        "tofu",
    }
    if product_form_noise:
        return False, "not_bottled_oil:" + "/".join(sorted(product_form_noise))
    if (
        not any(term in category for term in ("oil", "oils", "cooking"))
        and product.source != "esha_pack_candidate_clean"
        and not _is_retail_bridge_product(product)
    ):
        return False, "oil_requires_oil_category"
    if canonical_key in {"olive oil", "extra virgin olive oil"}:
        if "olive" not in tokens:
            return False, "missing_olive_oil_identity"
        reject = tokens & {"butter", "dressing", "garlic", "marinade", "mayo", "mayonnaise", "pesto", "sauce", "spray", "truffle"}
        if reject:
            return False, "not_plain_olive_oil:" + "/".join(sorted(reject))
        if canonical_key == "extra virgin olive oil":
            if {"extra", "virgin"} <= tokens or _contains_phrase(desc, "extra virgin"):
                return True, "extra_virgin_olive_oil_label"
            return False, "missing_extra_virgin_identity"
        return True, "olive_oil_label"
    if canonical_key == "peanut oil":
        if "peanut" in tokens:
            return True, "peanut_oil_label"
        return False, "missing_peanut_oil_identity"
    if canonical_key == "sesame oil":
        if "sesame" in tokens:
            return True, "sesame_oil_label"
        return False, "missing_sesame_oil_identity"
    if canonical_key == "toasted sesame oil":
        if "sesame" not in tokens:
            return False, "missing_sesame_oil_identity"
        if tokens & {"dark", "roasted", "toasted"}:
            return True, "toasted_sesame_oil_label"
        return False, "missing_toasted_sesame_identity"
    named_oil_noise = tokens & {"avocado", "coconut", "olive", "peanut", "sesame", "walnut"}
    if named_oil_noise:
        return False, "named_oil_not_neutral:" + "/".join(sorted(named_oil_noise))
    if canonical_key == "vegetable oil" and not (tokens & {"canola", "corn", "safflower", "soy", "soybean", "sunflower", "vegetable"}):
        return False, "missing_vegetable_neutral_oil_identity"
    if canonical_key == "oil" and "oil" not in tokens:
        return False, "missing_oil_identity"
    if canonical_key == "oil" and _contains_phrase(desc, "essential oil"):
        return False, "essential_oil_not_food"
    return True, "neutral_oil_label"


def _accept_cocoa_powder_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    if canonical_key not in {"cocoa powder", "dutch cocoa powder"}:
        return None
    desc = _product_desc(product)
    tokens = set(_product_text(product).split())
    if not (tokens & {"cacao", "cocoa"}):
        return False, "missing_cocoa_identity"
    if "powder" not in tokens and "powdered" not in tokens:
        return False, "missing_cocoa_powder_form"
    hot_mix_noise = tokens & {
        "bar",
        "beverage",
        "butter",
        "candy",
        "chip",
        "chips",
        "drink",
        "frosting",
        "ganache",
        "morsel",
        "morsels",
        "peanut",
        "spread",
        "plant",
        "protein",
        "syrup",
        "truffle",
        "truffles",
    }
    if hot_mix_noise:
        return False, "not_plain_cocoa_powder:" + "/".join(sorted(hot_mix_noise))
    if "mix" in tokens or _contains_phrase(desc, "hot cocoa") or _contains_phrase(desc, "hot chocolate"):
        return False, "hot_cocoa_mix_not_cocoa_powder"
    if canonical_key == "dutch cocoa powder" and not (tokens & {"alkali", "alkalized", "dutch", "processed"}):
        return False, "missing_dutch_alkali_identity"
    return True, "plain_cocoa_powder_label"


def _accept_raw_produce_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    if canonical_key not in {
        "apple",
        "tart apple",
        "granny smith apple",
        "red delicious apple",
        "blueberry",
        "cherry tomato",
        "lemon",
        "lemons",
        "fresh lemon",
        "fresh lemons",
        "orange",
        "oranges",
        "fresh orange",
        "fresh oranges",
        "grape",
        "grapes",
        "seedless grape",
        "seedless grapes",
    }:
        return None
    category = _product_category(product)
    tokens = _product_tokens(product)
    if canonical_key in {"apple", "tart apple", "granny smith apple", "red delicious apple"}:
        if "apple" not in tokens and "apples" not in tokens:
            return False, "missing_apple_identity"
        if canonical_key == "granny smith apple" and not {"granny", "smith"} <= tokens:
            return False, "missing_granny_smith_identity"
        if canonical_key == "red delicious apple" and not {"red", "delicious"} <= tokens:
            return False, "missing_red_delicious_identity"
        reject = tokens & {
            "bar",
            "candy",
            "caramel",
            "cider",
            "cookie",
            "fudge",
            "glaze",
            "granola",
            "juice",
            "licorice",
            "mix",
            "oatmeal",
            "pie",
            "protein",
            "sauce",
            "snack",
            "syrup",
            "twists",
        }
        if reject:
            return False, "not_plain_fresh_apple:" + "/".join(sorted(reject))
        if any(term in category for term in ("canned", "frozen", "juice", "snack")):
            return False, "apple_requires_fresh_produce_category"
        if any(term in category for term in ("fruit", "produce", "pre packaged", "vegetable")) or _is_retail_bridge_product(product):
            return True, "plain_fresh_apple_label"
        return False, "apple_requires_fresh_produce_category"
    if canonical_key == "blueberry":
        if "blueberry" not in tokens and "blueberries" not in tokens:
            return False, "missing_blueberry_identity"
        reject = tokens & {"bagel", "bread", "cereal", "cream", "drink", "juice", "lemonade", "muffin", "smoothie", "water", "yogurt"}
        if reject:
            return False, "not_plain_fresh_blueberry:" + "/".join(sorted(reject))
        if any(term in category for term in ("canned", "frozen", "juice", "jam", "jelly", "snack", "spread")):
            return False, "blueberry_requires_fresh_produce_category"
        if any(term in category for term in ("fruit", "produce", "pre packaged")) or _is_retail_bridge_product(product):
            return True, "plain_fresh_blueberry_label"
        return False, "blueberry_requires_fresh_produce_category"

    if canonical_key in {"lemon", "lemons", "fresh lemon", "fresh lemons"}:
        if not (tokens & {"lemon", "lemons"}):
            return False, "missing_lemon_identity"
        reject = tokens & {
            "bar",
            "cake",
            "cookie",
            "cream",
            "drink",
            "essence",
            "flavored",
            "flavour",
            "jam",
            "jelly",
            "juice",
            "lemonade",
            "oil",
            "paste",
            "peel",
            "preserved",
            "rind",
            "seltzer",
            "slice",
            "sliced",
            "soda",
            "sparkling",
            "water",
            "zest",
        }
        if reject:
            return False, "not_plain_fresh_lemon:" + "/".join(sorted(reject))
        if any(term in category for term in ("fruit", "produce", "pre packaged", "vegetable")) or _is_retail_bridge_product(product):
            return True, "plain_fresh_lemon_label"
        return False, "lemon_requires_fresh_produce_category"

    if canonical_key in {"orange", "oranges", "fresh orange", "fresh oranges"}:
        if not (tokens & {"orange", "oranges"}):
            return False, "missing_orange_identity"
        reject = tokens & {
            "bar",
            "beverage",
            "canned",
            "chocolate",
            "cocktail",
            "cup",
            "cups",
            "drink",
            "dried",
            "extract",
            "gel",
            "juice",
            "mandarin",
            "marmalade",
            "oil",
            "peel",
            "rind",
            "sauce",
            "segments",
            "snack",
            "zest",
        }
        if reject:
            return False, "not_plain_fresh_orange:" + "/".join(sorted(reject))
        if any(term in category for term in ("fruit", "produce", "pre packaged", "vegetable")) or _is_retail_bridge_product(product):
            return True, "plain_fresh_orange_label"
        return False, "orange_requires_fresh_produce_category"

    if canonical_key in {"grape", "grapes", "seedless grape", "seedless grapes"}:
        if not (tokens & {"grape", "grapes"}):
            return False, "missing_grape_identity"
        if canonical_key in {"seedless grape", "seedless grapes"} and "seedless" not in tokens:
            return False, "missing_seedless_grape_identity"
        reject = tokens & {
            "apple",
            "apples",
            "bar",
            "candy",
            "caramel",
            "cheese",
            "cocktail",
            "dip",
            "drink",
            "dried",
            "frozen",
            "freeze",
            "juice",
            "jelly",
            "jam",
            "lemon",
            "lime",
            "pops",
            "pretzel",
            "pretzels",
            "smoothie",
            "sour",
            "tablet",
            "water",
            "wine",
            "yogurt",
        }
        if reject:
            return False, "not_plain_fresh_grapes:" + "/".join(sorted(reject))
        if any(term in category for term in ("fruit", "produce", "pre packaged", "vegetable")) or _is_retail_bridge_product(product):
            return True, "plain_fresh_grapes_label"
        return False, "grapes_require_fresh_produce_category"

    if canonical_key in {"snow pea", "snow peas"}:
        if "snow" not in tokens or not (tokens & {"pea", "peas"}):
            return False, "missing_snow_pea_identity"
        reject = tokens & {"blend", "broccoli", "carrot", "frozen", "mushroom", "noodle", "onion", "rice", "salad", "sauce", "stir", "teriyaki"}
        if reject:
            return False, "not_plain_snow_peas:" + "/".join(sorted(reject))
        if any(term in category for term in ("fruit", "produce", "pre packaged", "vegetable")) or _is_retail_bridge_product(product):
            return True, "plain_snow_pea_label"
        return False, "snow_peas_require_fresh_produce_category"

    if "cherry" not in tokens or ("tomato" not in tokens and "tomatoes" not in tokens):
        return False, "missing_cherry_tomato_identity"
    reject = tokens & {"marinara", "pasta", "passata", "roasted", "salad", "sauce"}
    if reject:
        return False, "not_plain_cherry_tomato:" + "/".join(sorted(reject))
    if any(term in category for term in ("canned", "frozen", "juice", "sauce")):
        return False, "cherry_tomato_requires_fresh_produce_category"
    if any(term in category for term in ("fruit", "produce", "pre packaged", "tomato", "vegetable")) or _is_retail_bridge_product(product):
        return True, "plain_fresh_cherry_tomato_label"
    return False, "cherry_tomato_requires_fresh_produce_category"


def _accept_breadcrumb_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    if canonical_key not in {"breadcrumbs", "bread crumbs", "italian breadcrumbs", "seasoned breadcrumbs"}:
        return None
    desc = _product_desc(product)
    category = _product_category(product)
    tokens = _product_tokens(product)
    has_breadcrumb_identity = (
        "breadcrumb" in tokens
        or "breadcrumbs" in tokens
        or ("bread" in tokens and ("crumb" in tokens or "crumbs" in tokens))
        or _contains_phrase(desc, "bread crumbs")
    )
    if not has_breadcrumb_identity:
        return False, "missing_breadcrumb_identity"
    category_noise = {"dinner", "entree", "fish", "frozen", "meal", "meat", "seafood", "shrimp"} & set(category.split())
    if category_noise:
        return False, "breadcrumbs_embedded_in_prepared_product:" + "/".join(sorted(category_noise))
    product_noise = tokens & {"beef", "chicken", "fish", "haddock", "lobster", "mac", "meatball", "shrimp", "sticks", "strips"}
    if product_noise:
        return False, "breadcrumbs_embedded_in_prepared_product:" + "/".join(sorted(product_noise))
    if not any(term in category for term in ("baking", "bread", "breading")) and product.source != "esha_pack_candidate_clean":
        return False, "breadcrumbs_require_baking_or_bread_category"
    if canonical_key == "italian breadcrumbs":
        if "italian" in tokens:
            return True, "italian_breadcrumb_label"
        return False, "missing_italian_breadcrumb_identity"
    if canonical_key == "seasoned breadcrumbs":
        if "seasoned" in tokens:
            return True, "seasoned_breadcrumb_label"
        return False, "missing_seasoned_breadcrumb_identity"
    flavored = tokens & {"garlic", "herb", "italian", "parmesan", "seasoned"}
    if flavored:
        return False, "not_plain_breadcrumbs:" + "/".join(sorted(flavored))
    return True, "plain_breadcrumb_label"


def _accept_fresh_mint_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    if canonical_key not in {"fresh mint", "mint"}:
        return None
    category = _product_category(product)
    tokens = _product_tokens(product)
    if not (tokens & {"mint", "peppermint", "spearmint"}):
        return False, "missing_mint_identity"
    reject = tokens & {"candy", "chip", "chocolate", "dessert", "drink", "dried", "flavor", "frozen", "gelato", "gum", "ice", "jelly", "juice", "lemonade", "mouthwash", "rinse", "smoothie", "spice", "sugar", "tea", "water"}
    if reject:
        return False, "not_fresh_mint_herb:" + "/".join(sorted(reject))
    botanical_cues = tokens & {"live", "organic", "peppermint", "plant", "plants", "spearmint", "sweet"}
    if botanical_cues and not (tokens & {"cut", "sifted", "whole"}):
        return True, "fresh_mint_botanical_label"
    if "fresh" not in tokens and not any(term in category for term in ("produce", "vegetable")):
        return False, "missing_fresh_mint_identity"
    if any(term in category for term in ("herb", "spice", "produce", "vegetable")):
        return True, "fresh_mint_herb_label"
    return False, "fresh_mint_requires_herb_or_produce_category"


def _accept_hot_sauce_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    if canonical_key not in {"hot pepper sauce", "hot sauce"}:
        return None
    category = _product_category(product)
    tokens = _product_tokens(product)
    if "sauce" not in tokens and "sauces" not in tokens:
        return False, "missing_hot_sauce_identity"
    if not (tokens & {"hot", "pepper", "chili", "chile", "habanero", "jalapeno", "tabasco"}):
        return False, "missing_hot_pepper_identity"
    reject = tokens & {"barbecue", "bbq", "cheese", "cocktail", "curry", "dog", "nacho", "tartar"}
    if reject:
        return False, "not_plain_hot_sauce:" + "/".join(sorted(reject))
    if any(term in category for term in ("condiment", "sauce", "ketchup", "mustard", "ethnic", "cooking")):
        return True, "hot_sauce_label"
    if _is_retail_bridge_product(product) or product.source == "api_cache_exact":
        return True, "hot_sauce_label"
    return False, "hot_sauce_requires_condiment_category"


def _accept_recipe_volume_edge_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    """Guard high-risk recipe-506745 style ingredients that are easy to overmatch."""
    desc = _product_desc(product)
    category = _product_category(product)
    tokens = _product_tokens(product)

    if canonical_key == "beef gravy":
        if not ({"beef", "gravy"} <= tokens):
            return False, "missing_ready_beef_gravy_identity"
        reject = tokens & {
            "au",
            "base",
            "bone",
            "broth",
            "cat",
            "demi",
            "dinner",
            "dog",
            "dry",
            "glace",
            "granules",
            "jus",
            "meal",
            "mix",
            "packet",
            "potatoes",
            "powder",
            "reduction",
            "salisbury",
            "seasoning",
            "soup",
            "stock",
        }
        if reject:
            return False, "not_ready_beef_gravy:" + "/".join(sorted(reject))
        return True, "ready_beef_gravy_label"

    if canonical_key == "veal":
        if "veal" not in tokens:
            return False, "missing_veal_identity"
        reject = tokens & {
            "beef",
            "blend",
            "broth",
            "cannelloni",
            "demi",
            "florentine",
            "glace",
            "instant",
            "magic",
            "mix",
            "noodles",
            "pork",
            "reduction",
            "refill",
            "seasoning",
            "spices",
            "spinach",
            "stock",
        }
        if reject:
            return False, "not_plain_veal_meat:" + "/".join(sorted(reject))
        meat_form = tokens & {"chop", "chops", "cutlet", "cutlets", "ground", "meat", "roast", "scallopini", "scaloppini", "stew"}
        if meat_form:
            return True, "plain_veal_meat_label"
        return False, "veal_requires_plain_meat_cut"

    if canonical_key == "beef brisket":
        if not ({"beef", "brisket"} <= tokens):
            return False, "missing_beef_brisket_identity"
        reject = tokens & {
            "baked",
            "bean",
            "beans",
            "barbecue",
            "bbq",
            "bun",
            "burnt",
            "chopped",
            "combo",
            "cooked",
            "corned",
            "deli",
            "flavor",
            "fully",
            "hash",
            "heat",
            "hickory",
            "lunch",
            "packaged",
            "patties",
            "patty",
            "ready",
            "sauce",
            "sandwich",
            "seasoned",
            "shredded",
            "smoked",
            "snack",
            "swiss",
            "top",
            "round",
        }
        if reject:
            return False, "not_plain_beef_brisket:" + "/".join(sorted(reject))
        return True, "plain_beef_brisket_label"

    if canonical_key in {"chicken stock", "chicken broth"}:
        if "chicken" not in tokens or not (tokens & {"stock", "broth"}):
            return False, "missing_chicken_stock_identity"
        if canonical_key == "chicken stock" and "stock" not in tokens:
            return False, "missing_chicken_stock_identity"
        reject = tokens & {
            "base",
            "better",
            "bouillon",
            "concentrate",
            "concentrated",
            "cube",
            "cubes",
            "granulated",
            "jar",
            "knorr",
            "powder",
            "ramen",
        }
        if reject:
            return False, "not_ready_chicken_stock:" + "/".join(sorted(reject))
        return True, "ready_chicken_stock_label"

    if canonical_key in {"hamburger", "hamburger patty", "hamburger patties"}:
        if not ("beef" in tokens and (tokens & {"burger", "burgers", "ground", "hamburger", "patty", "patties"})):
            return False, "missing_hamburger_patty_identity"
        reject = tokens & {
            "bacon",
            "barbecue",
            "bbq",
            "beyond",
            "bun",
            "cheese",
            "covered",
            "dinner",
            "dill",
            "garlic",
            "helper",
            "impossible",
            "meal",
            "pickle",
            "plant",
            "potatoes",
            "sauce",
            "sandwich",
            "stroganoff",
            "veggie",
        }
        if reject:
            return False, "not_plain_hamburger_patty:" + "/".join(sorted(reject))
        return True, "plain_hamburger_patty_label"

    if canonical_key == "chicken":
        if "chicken" not in tokens:
            return False, "missing_chicken_identity"
        reject = tokens & {
            "apple",
            "can",
            "canned",
            "chilorio",
            "cooked",
            "crispups",
            "entree",
            "fully",
            "poblano",
            "pulled",
            "rotisserie",
            "sausage",
            "seasoned",
            "shredded",
            "tacos",
            "tinga",
        }
        if reject:
            return False, "not_plain_raw_chicken:" + "/".join(sorted(reject))
        form = tokens & {
            "breast",
            "breasts",
            "drumsticks",
            "drums",
            "fresh",
            "natural",
            "picnic",
            "thighs",
            "whole",
        }
        if form:
            return True, "plain_raw_chicken_label"
        if any(term in category for term in ("meat", "poultry")):
            return True, "plain_raw_chicken_label"
        return False, "chicken_requires_raw_piece_or_whole_form"

    if canonical_key in {"fresh green beans", "green bean", "green beans", "snap beans", "string beans"}:
        if not ("green" in tokens and (tokens & {"bean", "beans"})):
            return False, "missing_green_bean_identity"
        reject = tokens & {
            "baby",
            "butter",
            "casserole",
            "dog",
            "garlic",
            "herb",
            "italian",
            "meal",
            "onions",
            "purina",
            "sauce",
            "seasoned",
        }
        if reject:
            return False, "not_plain_green_beans:" + "/".join(sorted(reject))
        if tokens & {"fresh", "frozen", "canned", "cut", "whole", "trimmed"} or _is_retail_bridge_product(product):
            return True, "plain_green_beans_label"
        return False, "green_beans_requires_plain_form"

    if canonical_key == "corn":
        if "corn" not in tokens:
            return False, "missing_corn_identity"
        reject = tokens & {
            "breakfast",
            "bread",
            "cheddar",
            "chips",
            "cereal",
            "cornbread",
            "cornstarch",
            "crumbs",
            "flakes",
            "frosted",
            "meal",
            "popcorn",
            "salad",
            "starch",
            "street",
            "syrup",
            "tortilla",
        }
        if reject:
            return False, "not_plain_corn_kernels:" + "/".join(sorted(reject))
        if tokens & {"cream", "creamed"} and not tokens & {"kernel", "kernels", "whole"}:
            return False, "not_plain_corn_kernels:cream_style"
        if tokens & {"canned", "cob", "frozen", "gold", "golden", "kernel", "kernels", "sweet", "white", "whole", "yellow"}:
            return True, "plain_corn_kernel_label"
        return False, "corn_requires_kernel_or_sweet_corn_form"

    if canonical_key in {"fresh tomato", "fresh tomatoes", "tomato", "tomatoes"}:
        if not (tokens & {"tomato", "tomatoes"}):
            return False, "missing_tomato_identity"
        reject = tokens & {
            "canned",
            "chili",
            "diced",
            "green",
            "juice",
            "julienne",
            "ketchup",
            "oil",
            "paste",
            "peeled",
            "petite",
            "puree",
            "salsa",
            "sauce",
            "stewed",
            "sun",
        }
        if reject:
            return False, "not_plain_fresh_tomato:" + "/".join(sorted(reject))
        if "fresh" in tokens or any(term in category for term in ("fruit", "produce", "tomato", "vegetable")) or _is_retail_bridge_product(product):
            return True, "plain_fresh_tomato_label"
        return False, "tomato_requires_fresh_produce_category"

    if canonical_key == "potato":
        if not (tokens & {"potato", "potatoes"}):
            return False, "missing_potato_identity"
        reject = tokens & {
            "bake",
            "baked",
            "butter",
            "cheese",
            "complete",
            "crisps",
            "garlic",
            "gratin",
            "hash",
            "herb",
            "loaded",
            "mashed",
            "onion",
            "onions",
            "parmesan",
            "patties",
            "patty",
            "pepper",
            "peppers",
            "roasted",
            "seasoned",
            "side",
            "snack",
            "wedges",
        }
        if reject:
            return False, "not_plain_potato:" + "/".join(sorted(reject))
        if tokens & {"fresh", "russet", "red", "yellow", "yukon", "whole", "diced", "sliced", "new", "canned"}:
            return True, "plain_potato_label"
        if any(term in category for term in ("produce", "vegetable")):
            return True, "plain_potato_label"
        return False, "potato_requires_plain_whole_or_canned_form"

    if canonical_key in {"fresh parsley", "parsley"}:
        if "parsley" not in tokens:
            return False, "missing_parsley_identity"
        reject = tokens & {
            "dried",
            "flakes",
            "freeze",
            "garlic",
            "plant",
            "plants",
            "powder",
            "seasoning",
            "spice",
            "soup",
        }
        if reject:
            return False, "not_fresh_parsley:" + "/".join(sorted(reject))
        if desc in {"parsley", "organic italian parsley", "simple truth organic italian parsley"}:
            return True, "fresh_parsley_label"
        if _contains_phrase(desc, "organic italian parsley"):
            return True, "fresh_parsley_label"
        if tokens & {"fresh", "clamshell", "bunch"}:
            return True, "fresh_parsley_label"
        if any(term in category for term in ("herb", "produce", "vegetable")):
            return True, "fresh_parsley_label"
        return False, "parsley_requires_fresh_herb_form"

    if canonical_key in {"red cabbage", "purple cabbage"}:
        if not ({"red", "cabbage"} <= tokens or {"purple", "cabbage"} <= tokens):
            return False, "missing_red_cabbage_identity"
        reject = tokens & {
            "apple",
            "assorted",
            "beets",
            "cucumber",
            "mild",
            "pickled",
            "rotessa",
            "sarsons",
            "sour",
            "sweet",
            "tomato",
            "vegetables",
        }
        if reject:
            return False, "not_plain_red_cabbage:" + "/".join(sorted(reject))
        if desc in {"red cabbage", "organic red cabbage"}:
            return True, "plain_red_cabbage_label"
        if "fresh" in tokens or any(term in category for term in ("produce", "vegetable")):
            return True, "plain_red_cabbage_label"
        return False, "red_cabbage_requires_fresh_produce_form"

    if canonical_key in {"split pea", "split peas"}:
        if not ("split" in tokens and (tokens & {"pea", "peas"})):
            return False, "missing_split_pea_identity"
        reject = tokens & {
            "bacon",
            "campbell",
            "campbells",
            "canned",
            "chunky",
            "condensed",
            "ham",
            "healthy",
            "mcdougall",
            "progresso",
            "request",
            "soup",
            "smoke",
            "with",
        }
        if reject:
            return False, "not_dry_split_peas:" + "/".join(sorted(reject))
        if tokens & {"dry", "dried", "green", "peas", "split", "yellow"}:
            return True, "dry_split_peas_label"
        return False, "split_peas_require_dry_plain_form"

    if canonical_key in {"navy bean", "navy beans"}:
        if not ("navy" in tokens and (tokens & {"bean", "beans"})):
            return False, "missing_navy_bean_identity"
        reject = tokens & {
            "baked",
            "bourbon",
            "brown",
            "bush",
            "bushs",
            "can",
            "canned",
            "cream",
            "creole",
            "grillin",
            "heat",
            "low",
            "sodium",
            "style",
            "sugar",
        }
        if reject:
            return False, "not_dry_navy_beans:" + "/".join(sorted(reject))
        if tokens & {"dry", "dried", "lb", "pound", "raw"}:
            return True, "dry_navy_beans_label"
        if desc in {"kroger navy beans", "navy bean"}:
            return True, "dry_navy_beans_label"
        return False, "navy_beans_require_dry_plain_form"

    if canonical_key == "rice":
        if "rice" not in tokens:
            return False, "missing_rice_identity"
        reject = tokens & {
            "bean",
            "beans",
            "beef",
            "broccoli",
            "cheddar",
            "cheese",
            "chicken",
            "cilantro",
            "coconut",
            "creamy",
            "cup",
            "cups",
            "dinner",
            "flavor",
            "flavored",
            "fried",
            "garden",
            "garlic",
            "knorr",
            "lemon",
            "meal",
            "mexican",
            "pilaf",
            "pouch",
            "ready",
            "roni",
            "sides",
            "spanish",
            "street",
            "vegetable",
            "vermicelli",
            "wild",
        }
        if reject:
            return False, "not_plain_dry_rice:" + "/".join(sorted(reject))
        if tokens & {"bag", "basmati", "calrose", "enriched", "extra", "grain", "instant", "jasmine", "long", "mahatma", "minute", "rice", "white"}:
            return True, "plain_dry_rice_label"
        return False, "rice_requires_plain_dry_form"

    return None


def _accept_batch11_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    category = _product_category(product)
    tokens = _product_tokens(product)
    desc = _product_desc(product)

    if canonical_key == "tomato":
        if not (tokens & {"tomato", "tomatoes"}):
            return False, "missing_tomato_identity"
        reject = tokens & {"canned", "catsup", "chopped", "crushed", "diced", "juice", "ketchup", "paste", "peeled", "pizza", "puree", "sauce", "soup", "stewed", "whole"}
        if reject:
            return False, "not_plain_fresh_tomato:" + "/".join(sorted(reject))
        if any(term in category for term in ("fruit", "produce", "tomato", "vegetable")) or _is_retail_bridge_product(product):
            return True, "fresh_tomato_label"
        return False, "tomato_requires_fresh_produce_category"

    if canonical_key == "crushed tomatoes":
        if not (tokens & {"tomato", "tomatoes"}) or "crushed" not in tokens:
            return False, "missing_crushed_tomato_identity"
        reject = tokens & {"bisque", "juice", "ketchup", "paste", "pizza", "puree", "salsa", "sauce", "soup", "vodka"}
        if reject:
            return False, "not_plain_crushed_tomatoes:" + "/".join(sorted(reject))
        if any(term in category for term in ("tomato", "vegetable")):
            return True, "crushed_tomatoes_label"
        return False, "crushed_tomatoes_require_tomato_category"

    if canonical_key in {"cardamom", "cardamom whole", "cardamom pod", "cardamom pods"}:
        if "cardamom" not in tokens:
            return False, "missing_cardamom_identity"
        reject = tokens & {
            "bar",
            "butter",
            "cake",
            "chocolate",
            "coffee",
            "cookie",
            "cookies",
            "gelato",
            "granola",
            "ice",
            "jam",
            "jelly",
            "marmalade",
            "mustard",
            "pasta",
            "preserves",
            "rice",
            "sauce",
            "sorbetto",
            "tea",
            "yogurt",
        }
        if reject:
            return False, "not_plain_cardamom_pods:" + "/".join(sorted(reject))
        whole_like = tokens & {"green", "whole", "pod", "pods"}
        if "spice" not in category and "herb" not in category and "seasoning" not in category:
            return False, "cardamom_requires_spice_category"
        if canonical_key in {"cardamom whole", "cardamom pod", "cardamom pods"} and not whole_like:
            return False, "missing_whole_cardamom_identity"
        return True, "whole_cardamom_label" if whole_like else "cardamom_spice_label"

    if canonical_key in {"ground clove", "ground cloves"}:
        if "clove" not in tokens and "cloves" not in tokens:
            return False, "missing_ground_clove_identity"
        if "ground" not in tokens and not _contains_phrase(desc, "cloves ground"):
            return False, "missing_ground_clove_state"
        reject = tokens & {"candy", "drink", "gum", "oil", "sauce", "soap", "tea", "toothpaste"}
        if reject:
            return False, "not_plain_ground_cloves:" + "/".join(sorted(reject))
        if any(term in category for term in ("herb", "spice", "seasoning")):
            return True, "ground_cloves_label"
        return False, "ground_cloves_require_spice_category"

    if canonical_key in {"saffron thread", "saffron threads"}:
        if "saffron" not in tokens:
            return False, "missing_saffron_identity"
        if "thread" not in tokens and "threads" not in tokens:
            return False, "missing_saffron_thread_identity"
        reject = tokens & {"candy", "chip", "chips", "oil", "rice", "risotto", "salt", "syrup"}
        if reject:
            return False, "not_plain_saffron_threads:" + "/".join(sorted(reject))
        if any(term in category for term in ("herb", "spice", "seasoning")):
            return True, "saffron_threads_label"
        return False, "saffron_threads_require_spice_category"

    if canonical_key in {"black pepper", "ground black pepper"}:
        has_pepper_identity = {"black", "pepper"} <= tokens or ("black" in tokens and (tokens & {"peppercorn", "peppercorns"}))
        if not has_pepper_identity:
            return False, "missing_black_pepper_identity"
        reject = tokens & {"capsule", "capsules", "extract", "garlic", "lemon", "lime", "marinade", "onion", "papad", "parmesan", "rub", "salt", "sauce", "sausage", "seasoning", "tofu"}
        if reject:
            return False, "not_plain_black_pepper:" + "/".join(sorted(reject))
        if "chili" in tokens or "chilies" in tokens or "chiles" in tokens:
            return False, "not_plain_black_pepper:chili"
        if any(term in category for term in ("herb", "spice", "seasoning")) or _is_retail_bridge_product(product) or product.source == "api_cache_exact":
            return True, "black_pepper_label"
        return False, "black_pepper_requires_spice_category"

    if canonical_key == "onion":
        if not (tokens & {"onion", "onions"}):
            return False, "missing_onion_identity"
        reject = tokens & {
            "blend",
            "dip",
            "dried",
            "fajita",
            "fried",
            "martini",
            "medley",
            "mix",
            "mixed",
            "pearl",
            "pepper",
            "peppers",
            "pickle",
            "pickled",
            "potato",
            "potatoes",
            "powder",
            "ring",
            "rings",
            "silverskin",
            "soup",
            "squash",
            "zucchini",
        }
        if reject:
            return False, "not_plain_fresh_onion:" + "/".join(sorted(reject))
        if any(term in category for term in ("canned", "chip", "chips", "dip", "frozen", "ring", "rings", "snack", "soup")):
            return False, "onion_requires_fresh_produce_category"
        if any(term in category for term in ("onion", "produce", "fruit and vegetables")) or _is_retail_bridge_product(product):
            return True, "fresh_onion_label"
        return False, "onion_requires_fresh_produce_category"

    if canonical_key in {"butter", "salted butter", "unsalted butter"}:
        if "butter" not in tokens and "beurre" not in tokens:
            return False, "missing_butter_identity"
        desc_tokens = set(desc.split())
        if canonical_key == "unsalted butter" and "unsalted" not in tokens:
            return False, "missing_unsalted_butter_identity"
        if canonical_key == "salted butter" and "unsalted" in tokens:
            return False, "not_salted_butter:unsalted"
        if {"dairy", "free"} <= tokens or {"plant", "based"} <= tokens:
            return False, "not_plain_butter:plant_or_dairy_free"
        reject = desc_tokens & {
            "biscuit", "biscuits", "canola", "chip", "chips", "flavor", "flavored",
            "garlic", "glaze", "ham", "herb", "oil", "olive", "pickle", "pickles",
            "plant", "powder", "sauce", "spread", "spreadable", "syrup", "vegetable",
        }
        if reject:
            return False, "not_plain_butter:" + "/".join(sorted(reject))
        if _contains_phrase(desc, "bread and butter") or _contains_phrase(desc, "bread & butter"):
            return False, "not_plain_butter:bread_and_butter"
        if _contains_phrase(desc, "spreadable butter") or _contains_phrase(desc, "butter spread") or _contains_phrase(desc, "butter blend"):
            return False, "not_plain_butter:spread_or_blend"
        if any(term in category for term in ("butter", "dairy")) or _is_retail_bridge_product(product) or product.source == "api_cache_exact":
            return True, "plain_butter_label"
        return False, "butter_requires_dairy_category"

    if canonical_key == "cheddar cheese":
        if "cheddar" not in tokens:
            return False, "missing_cheddar_identity"
        reject = tokens & {
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
            "snacking",
            "spicy",
            "swiss",
            "taco",
            "vegan",
        }
        if reject:
            return False, "not_plain_cheddar:" + "/".join(sorted(reject))
        if any(term in category for term in ("cheese", "dairy")) or _is_retail_bridge_product(product):
            return True, "plain_cheddar_label"
        return False, "cheddar_requires_cheese_category"

    if canonical_key == "white mushroom":
        if "mushroom" not in tokens and "mushrooms" not in tokens:
            return False, "missing_mushroom_identity"
        if not (tokens & {"button", "white"}):
            return False, "missing_white_mushroom_identity"
        reject = tokens & {"beef", "cream", "gravy", "pizza", "sauce", "soup", "truffle", "wine"}
        if reject:
            return False, "not_plain_white_mushroom:" + "/".join(sorted(reject))
        if any(term in category for term in ("produce", "vegetable", "mushroom")):
            return True, "white_mushroom_label"
        return False, "white_mushroom_requires_produce_category"

    if canonical_key == "dried oregano":
        if "oregano" not in tokens:
            return False, "missing_oregano_identity"
        if not (
            tokens & {"dried", "ground", "leaf", "leaves", "oregano", "whole"}
            or any(term in category for term in ("herb", "spice", "seasoning"))
            or _is_retail_bridge_product(product)
        ):
            return False, "missing_dried_oregano_form"
        reject = tokens & {"basil", "cracker", "crackers", "diced", "garlic", "olive", "tomato", "tomatoes"}
        if reject:
            return False, "not_plain_dried_oregano:" + "/".join(sorted(reject))
        if any(term in category for term in ("herb", "spice", "seasoning")) or _is_retail_bridge_product(product):
            return True, "dried_oregano_label"
        return False, "dried_oregano_requires_spice_category"

    if canonical_key in {"scallion", "green onion"}:
        has_identity = (
            "scallion" in tokens
            or "scallions" in tokens
            or _contains_phrase(desc, "green onion")
            or _contains_phrase(desc, "green onions")
            or _contains_phrase(desc, "spring onion")
            or _contains_phrase(desc, "spring onions")
        )
        if not has_identity:
            return False, "missing_scallion_identity"
        reject = tokens & {
            "almond",
            "avocado",
            "bacon",
            "bean",
            "beans",
            "broccoli",
            "cabbage",
            "carrot",
            "carrots",
            "celery",
            "cheese",
            "cilantro",
            "corn",
            "cream",
            "crisp",
            "crispy",
            "crouton",
            "dip",
            "dressing",
            "kale",
            "kit",
            "leaf",
            "lettuce",
            "pepita",
            "pepitas",
            "radicchio",
            "ranch",
            "romaine",
            "salad",
            "savoy",
            "sauce",
            "sesame",
            "slaw",
            "smoked",
            "southwest",
            "spread",
            "sausage",
            "tortilla",
            "wonton",
        }
        if reject:
            return False, "not_plain_scallion:" + "/".join(sorted(reject))
        if any(_contains_phrase(desc, phrase) for phrase in ("salad kit", "chopped salad", "salad blend")):
            return False, "not_plain_scallion:salad_kit"
        if any(term in category for term in ("fruit", "herb", "onion", "produce", "vegetable")):
            return True, "plain_scallion_label"
        return False, "green_onion_requires_produce_category"

    if canonical_key == "mushroom":
        if "mushroom" not in tokens and "mushrooms" not in tokens:
            return False, "missing_mushroom_identity"
        reject = tokens & {
            "beech",
            "canned",
            "cream",
            "enoki",
            "gravy",
            "gourmet",
            "marinated",
            "mix",
            "morel",
            "oyster",
            "pizza",
            "porcini",
            "risotto",
            "sauce",
            "seasoning",
            "shiitake",
            "snack",
            "soup",
            "stock",
            "truffle",
            "wild",
        }
        if reject:
            return False, "not_plain_fresh_mushroom:" + "/".join(sorted(reject))
        if any(term in category for term in ("produce", "vegetable", "mushroom", "pre packaged")):
            return True, "plain_fresh_mushroom_label"
        return False, "mushroom_requires_fresh_produce_category"

    if canonical_key in {"green bell pepper", "green pepper", "sweet green pepper"}:
        if "pepper" not in tokens and "peppers" not in tokens:
            return False, "missing_green_pepper_identity"
        if "green" not in tokens:
            return False, "missing_green_pepper_identity"
        if "bell" not in tokens and not any(term in category for term in ("produce", "vegetable", "pepper")):
            return False, "missing_bell_pepper_identity"
        reject = tokens & {"dip", "jelly", "onion", "pizza", "salsa", "sauce", "tomato"}
        if reject:
            return False, "not_plain_green_bell_pepper:" + "/".join(sorted(reject))
        if any(term in category for term in ("produce", "vegetable", "pepper")):
            return True, "green_bell_pepper_label"
        return False, "green_bell_pepper_requires_produce_category"

    return None


def _accept_batch12_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    category = _product_category(product)
    tokens = _product_tokens(product)
    desc = _product_desc(product)

    if canonical_key == "iceberg lettuce":
        if not {"iceberg", "lettuce"} <= tokens:
            return False, "missing_iceberg_lettuce_identity"
        reject = tokens & {
            "american",
            "blend",
            "cobb",
            "chopped",
            "classic",
            "garden",
            "kit",
            "mix",
            "salad",
            "shreds",
            "shredded",
            "slaw",
        }
        if reject:
            return False, "not_head_iceberg_lettuce:" + "/".join(sorted(reject))
        if any(term in category for term in ("kit", "prepared", "salad")):
            return False, "iceberg_head_requires_whole_produce_category"
        if any(term in category for term in ("lettuce", "produce", "vegetable")):
            return True, "whole_iceberg_lettuce_label"
        return False, "iceberg_requires_produce_category"

    if canonical_key == "whole ham":
        if "ham" not in tokens:
            return False, "missing_ham_identity"
        reject = tokens & {
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
        }
        if reject:
            return False, "not_whole_ham:" + "/".join(sorted(reject))
        whole_like = (
            bool({"whole", "half", "portion", "quarter"} & tokens)
            or bool({"bone", "spiral", "shank"} & tokens)
            or _contains_phrase(desc, "whole family")
            or _contains_phrase(desc, "whole muscle")
            or _contains_phrase(desc, "bone in")
            or _contains_phrase(desc, "bone-in")
            or _contains_phrase(desc, "spiral cut")
            or _contains_phrase(desc, "spiral-cut")
        )
        if not whole_like:
            return False, "missing_whole_ham_cue"
        if any(term in category for term in ("ham", "meat", "pork")) or _is_retail_bridge_product(product):
            return True, "whole_ham_label"
        return False, "whole_ham_requires_meat_category"

    return None


def _accept_batch9_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    category = _product_category(product)
    tokens = _product_tokens(product)

    if canonical_key == "mixed nuts":
        if "mixed" not in tokens or not (tokens & {"nut", "nuts"}):
            return False, "missing_mixed_nuts_identity"
        reject = tokens & {"bar", "bread", "candy", "chocolate", "cookie", "granola", "nougat", "trail", "yogurt"}
        if reject:
            return False, "not_plain_mixed_nuts:" + "/".join(sorted(reject))
        if any(term in category for term in ("nut", "seed", "snack")) or _is_retail_bridge_product(product):
            return True, "plain_mixed_nuts_label"
        return False, "mixed_nuts_require_nut_category"

    if canonical_key == "bittersweet chocolate":
        if "bittersweet" not in tokens or "chocolate" not in tokens:
            return False, "missing_bittersweet_chocolate_identity"
        reject = tokens & {"beverage", "chip", "chips", "cookie", "cookies", "drink", "ice", "milk", "sauce", "syrup"}
        if reject:
            return False, "not_plain_bittersweet_chocolate:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "chocolate", "candy")):
            return True, "bittersweet_chocolate_label"
        return False, "bittersweet_chocolate_requires_chocolate_category"

    if canonical_key == "chili sauce":
        if not (tokens & {"chili", "chile"}) or "sauce" not in tokens:
            return False, "missing_chili_sauce_identity"
        reject = tokens & {"barbecue", "bbq", "cheese", "curry", "dog", "garlic", "hot", "nacho", "sweet"}
        if reject:
            return False, "not_plain_chili_sauce:" + "/".join(sorted(reject))
        if any(term in category for term in ("chili", "condiment", "ketchup", "sauce", "stew")):
            return True, "chili_sauce_label"
        return False, "chili_sauce_requires_condiment_category"

    if canonical_key == "yellow cake mix":
        if not {"yellow", "cake", "mix"} <= tokens:
            return False, "missing_yellow_cake_mix_identity"
        reject = tokens & {"baked", "chocolate", "cookie", "cupcake", "frosting", "icing", "prepared", "snack"}
        if reject:
            return False, "not_plain_yellow_cake_mix:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "cake", "cupcake", "mix")):
            return True, "yellow_cake_mix_label"
        return False, "yellow_cake_mix_requires_baking_category"

    if canonical_key == "kalamata olive":
        if not (tokens & {"kalamata", "calamata"}) or not (tokens & {"olive", "olives"}):
            return False, "missing_kalamata_olive_identity"
        reject = tokens & {"dip", "hummus", "paste", "salad", "sauce", "spread", "tapenade"}
        if reject:
            return False, "not_plain_kalamata_olives:" + "/".join(sorted(reject))
        if any(term in category for term in ("olive", "pickle", "relish", "vegetable")):
            return True, "kalamata_olive_label"
        return False, "kalamata_olive_requires_olive_category"

    if canonical_key == "golden raisin":
        if "golden" not in tokens or not (tokens & {"raisin", "raisins"}):
            return False, "missing_golden_raisin_identity"
        reject = tokens & {"almond", "berries", "berry", "bread", "cashew", "cereal", "cherry", "chocolate", "cranberries", "cranberry", "mix", "trail", "yogurt"}
        if reject:
            return False, "not_plain_golden_raisins:" + "/".join(sorted(reject))
        if any(term in category for term in ("dried", "fruit", "snack")):
            return True, "golden_raisin_label"
        return False, "golden_raisin_requires_dried_fruit_category"

    if canonical_key == "roma tomato":
        if "roma" not in tokens or not (tokens & {"tomato", "tomatoes"}):
            return False, "missing_roma_tomato_identity"
        reject = tokens & {"canned", "chopped", "diced", "paste", "petite", "puree", "sauce", "stewed"}
        if reject:
            return False, "not_fresh_roma_tomato:" + "/".join(sorted(reject))
        if any(term in category for term in ("fruit", "produce", "tomato", "vegetable")):
            return True, "fresh_roma_tomato_label"
        return False, "roma_tomato_requires_fresh_produce_category"

    if canonical_key == "self rising flour":
        if not {"self", "rising", "flour"} <= tokens:
            return False, "missing_self_rising_flour_identity"
        reject = tokens & {"almond", "cake", "cornmeal", "gluten", "mix", "pancake", "whole"}
        if reject:
            return False, "not_plain_self_rising_flour:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "flour", "grain")):
            return True, "self_rising_flour_label"
        return False, "self_rising_flour_requires_flour_category"

    if canonical_key == "tomato juice":
        if "tomato" not in tokens or "juice" not in tokens:
            return False, "missing_tomato_juice_identity"
        reject = tokens & {"beef", "carrot", "celery", "clam", "cocktail", "diced", "vegetable"}
        if reject:
            return False, "not_plain_tomato_juice:" + "/".join(sorted(reject))
        if any(term in category for term in ("beverage", "drink", "juice")):
            return True, "tomato_juice_label"
        return False, "tomato_juice_requires_juice_category"

    if canonical_key == "tomato puree":
        if not (tokens & {"tomato", "tomatoes"}) or not (tokens & {"passata", "puree", "pureed"}):
            return False, "missing_tomato_puree_identity"
        reject = tokens & {"chopped", "crushed", "diced", "paste", "sauce", "seasoned", "stewed"}
        if reject:
            return False, "not_plain_tomato_puree:" + "/".join(sorted(reject))
        if any(term in category for term in ("tomato", "vegetable")):
            return True, "tomato_puree_label"
        return False, "tomato_puree_requires_tomato_category"

    if canonical_key == "sunflower seed":
        if "sunflower" not in tokens or not (tokens & {"kernel", "kernels", "seed", "seeds"}):
            return False, "missing_sunflower_seed_identity"
        reject = tokens & {"bar", "bread", "breading", "chia", "chocolate", "cluster", "coconut", "crumb", "granola", "pumpkin", "ranch"}
        if reject:
            return False, "not_plain_sunflower_seeds:" + "/".join(sorted(reject))
        if any(term in category for term in ("nut", "seed", "snack")):
            return True, "sunflower_seed_label"
        return False, "sunflower_seed_requires_seed_category"

    if canonical_key == "yellow cornmeal":
        if "yellow" not in tokens or "cornmeal" not in tokens:
            return False, "missing_yellow_cornmeal_identity"
        reject = tokens & {"arepa", "cake", "cornbread", "hush", "mix", "precooked", "self", "white"}
        if reject:
            return False, "not_plain_yellow_cornmeal:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "corn", "flour", "meal")):
            return True, "yellow_cornmeal_label"
        return False, "yellow_cornmeal_requires_flour_category"

    if canonical_key == "miniature marshmallow":
        if not (tokens & {"marshmallow", "marshmallows"}):
            return False, "missing_marshmallow_identity"
        if not (tokens & {"mini", "miniature"}):
            return False, "missing_miniature_marshmallow_identity"
        reject = tokens & {"cereal", "chocolate", "cocoa", "cookie", "hot"}
        if reject:
            return False, "not_plain_miniature_marshmallows:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "candy", "marshmallow")):
            return True, "miniature_marshmallow_label"
        return False, "miniature_marshmallow_requires_candy_category"

    if canonical_key in {"gingersnap crumbs", "gingersnap cookies"}:
        if "gingersnap" not in tokens:
            return False, "missing_gingersnap_identity"
        reject = tokens & {"bar", "cereal", "chocolate", "cream", "ice", "latte", "milk", "trail", "waffle"}
        if reject:
            return False, "not_plain_gingersnap_cookies:" + "/".join(sorted(reject))
        if any(term in category for term in ("cookie", "biscuit")):
            return True, "gingersnap_cookie_label"
        return False, "gingersnap_requires_cookie_category"

    if canonical_key == "penne pasta":
        if "penne" not in tokens:
            return False, "missing_penne_identity"
        reject = tokens & {"alfredo", "amaranth", "brown", "chicken", "corn", "dinner", "gluten", "meal", "multigrain", "quinoa", "rice", "whole"}
        if reject:
            return False, "not_plain_penne_pasta:" + "/".join(sorted(reject))
        if any(term in category for term in ("noodle", "pasta")):
            return True, "penne_pasta_label"
        return False, "penne_pasta_requires_pasta_category"

    if canonical_key == "crabmeat":
        if not (tokens & {"crab", "crabmeat"}):
            return False, "missing_crabmeat_identity"
        reject = tokens & {"cake", "imitation", "roll", "salad", "soup", "stuffed", "stuffing", "surimi", "sushi", "tilapia"}
        if reject:
            return False, "not_plain_crabmeat:" + "/".join(sorted(reject))
        if any(term in category for term in ("canned", "fish", "seafood", "shellfish")):
            return True, "plain_crabmeat_label"
        return False, "crabmeat_requires_seafood_category"

    if canonical_key == "white chocolate":
        if "white" not in tokens or "chocolate" not in tokens:
            return False, "missing_white_chocolate_identity"
        reject = tokens & {"chip", "chips", "cookie", "drink", "frosting", "ice", "macadamia", "peppermint", "pudding", "sauce", "syrup", "yogurt"}
        if reject:
            return False, "not_plain_white_chocolate:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "candy", "chocolate")):
            return True, "white_chocolate_label"
        return False, "white_chocolate_requires_chocolate_category"

    if canonical_key == "white chocolate chips":
        if "white" not in tokens or "chocolate" not in tokens or not (tokens & {"chip", "chips", "chunk", "chunks", "morsel", "morsels"}):
            return False, "missing_white_chocolate_chip_identity"
        reject = tokens & {"cookie", "egg", "frosting", "pudding", "syrup"}
        if reject:
            return False, "not_plain_white_chocolate_chips:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "chocolate", "dessert", "topping")):
            return True, "white_chocolate_chip_label"
        return False, "white_chocolate_chips_require_baking_category"

    return None


def _accept_batch10_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    category = _product_category(product)
    tokens = _product_tokens(product)
    desc = _product_desc(product)

    if canonical_key == "peanut":
        if not (tokens & {"peanut", "peanuts"}):
            return False, "missing_peanut_identity"
        reject = tokens & {"bar", "boiled", "brittle", "butter", "cajun", "candy", "chocolate", "cookie", "cracker", "flour", "granola", "green", "honey", "mix", "sauce", "spicy", "trail", "yogurt"}
        if reject:
            return False, "not_plain_peanuts:" + "/".join(sorted(reject))
        if any(term in category for term in ("nut", "peanut", "seed", "snack")):
            return True, "plain_peanut_label"
        return False, "peanut_requires_nut_category"

    if canonical_key == "pumpkin puree":
        if "pumpkin" not in tokens:
            return False, "missing_pumpkin_identity"
        reject = tokens & {"bread", "cake", "cookie", "muffin", "pie", "seed", "spice", "soup"}
        if reject:
            return False, "not_plain_canned_pumpkin:" + "/".join(sorted(reject))
        if tokens & {"pure", "puree", "pureed"} or _contains_phrase(desc, "100 pure") or desc in {"pumpkin", "organic pumpkin"}:
            if any(term in category for term in ("baking", "canned", "vegetable")):
                return True, "plain_canned_pumpkin_label"
            return False, "pumpkin_requires_canned_or_baking_category"
        return False, "missing_plain_pumpkin_puree_identity"

    if canonical_key == "pumpkin pie mix":
        if not {"pumpkin", "pie"} <= tokens or "mix" not in tokens:
            return False, "missing_pumpkin_pie_mix_identity"
        reject = tokens & {
            "almond",
            "bar",
            "bars",
            "cake",
            "cheesecake",
            "cookie",
            "dip",
            "drink",
            "granola",
            "protein",
            "powder",
            "pretzel",
            "scone",
            "seasoning",
            "spice",
            "trail",
            "yogurt",
        }
        if reject:
            return False, "not_plain_pumpkin_pie_mix:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "canned", "custard", "filling", "pastry", "pudding", "vegetable")):
            return True, "pumpkin_pie_mix_label"
        return False, "pumpkin_pie_mix_requires_canned_or_baking_category"

    if canonical_key == "cayenne pepper":
        if "cayenne" not in tokens:
            return False, "missing_cayenne_identity"
        reject = tokens & {"cherries", "cherry", "drink", "hummus", "lemonade", "sauce", "truffle", "truffles"}
        if reject:
            return False, "not_cayenne_spice:" + "/".join(sorted(reject))
        if any(term in category for term in ("spice", "seasoning")):
            return True, "cayenne_spice_label"
        return False, "cayenne_requires_spice_category"

    if canonical_key == "lasagna noodles":
        if "lasagna" not in tokens:
            return False, "missing_lasagna_identity"
        reject = tokens & {"bake", "bolognese", "cheese", "chicken", "dinner", "entree", "frozen", "meal", "meat", "prepared", "sauce", "soup", "turkey", "vegetable"}
        if reject:
            return False, "not_plain_lasagna_noodles:" + "/".join(sorted(reject))
        if any(term in category for term in ("noodle", "pasta")):
            return True, "dry_lasagna_noodle_label"
        return False, "lasagna_noodles_require_pasta_category"

    if canonical_key == "firm tofu":
        if "tofu" not in tokens or "firm" not in tokens:
            return False, "missing_firm_tofu_identity"
        reject = tokens & {"dessert", "dip", "noodle", "soup", "spread"}
        if reject:
            return False, "not_plain_firm_tofu:" + "/".join(sorted(reject))
        if any(term in category for term in ("meat", "plant", "tofu", "vegetarian")):
            return True, "firm_tofu_label"
        return False, "firm_tofu_requires_tofu_category"

    if canonical_key == "splenda granular":
        if not (tokens & {"splenda", "sucralose", "sweetener"}):
            return False, "missing_splenda_sucralose_identity"
        if not (tokens & {"granular", "granulated"}):
            return False, "missing_granular_sweetener_identity"
        reject = tokens & {"brown", "cookie", "drink", "ice", "juice", "packet", "soda", "sorbet", "tea"}
        if reject:
            return False, "not_plain_granular_splenda:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "sugar", "sweetener")):
            return True, "granular_splenda_label"
        return False, "splenda_requires_sweetener_category"

    if canonical_key in {"banana", "organic banana", "organic bananas"}:
        desc_tokens = set(desc.split())
        if not (desc_tokens & {"banana", "bananas"}):
            return False, "missing_banana_identity"
        reject = desc_tokens & {
            "bar",
            "bars",
            "boat",
            "bread",
            "cake",
            "can",
            "cereal",
            "chip",
            "chips",
            "chocolate",
            "dehydrated",
            "dried",
            "freeze",
            "frozen",
            "granola",
            "juice",
            "loaf",
            "lotion",
            "muffin",
            "muffins",
            "nectar",
            "oatmeal",
            "peanut",
            "powder",
            "shake",
            "smoothie",
            "slice",
            "sliced",
            "slices",
            "spray",
            "spf",
            "strawberry",
            "sunscreen",
            "trail",
            "yogurt",
        }
        if reject:
            return False, "not_plain_banana:" + "/".join(sorted(reject))
        if canonical_key in {"organic banana", "organic bananas"}:
            if desc_tokens <= {"organic", "banana", "bananas"} and "wholesome snacks" in category:
                return True, "plain_banana_exact_label"
            return False, "organic_bananas_require_exact_plain_label"
        if desc_tokens <= {"organic", "banana", "bananas"} and "wholesome snacks" in category:
            return True, "plain_banana_exact_label"
        if any(term in category for term in ("fruit", "produce", "vegetable")):
            return True, "plain_banana_label"
        if _is_retail_bridge_product(product):
            return True, "plain_banana_retail_label"
        return False, "banana_requires_fresh_produce_category"

    if canonical_key == "cornstarch":
        if "cornstarch" not in tokens and not _contains_phrase(desc, "corn starch"):
            return False, "missing_cornstarch_identity"
        reject = tokens & {"confectioners", "fermented", "hydrolyzed", "powdered", "sugar", "thickener", "thicken"}
        if reject:
            return False, "not_plain_cornstarch:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "corn", "flour")):
            return True, "plain_cornstarch_label"
        return False, "cornstarch_requires_baking_category"

    if canonical_key == "bourbon":
        if "bourbon" not in tokens:
            return False, "missing_bourbon_identity"
        reject = tokens & {"cocoa", "cookie", "cookies", "cream", "mix", "sauce", "torte"}
        if reject:
            return False, "not_plain_bourbon:" + "/".join(sorted(reject))
        if any(term in category for term in ("alcohol", "liquor", "spirits", "whiskey")):
            return True, "bourbon_liquor_label"
        return False, "bourbon_requires_alcohol_category"

    if canonical_key in {"dry sherry", "dry vermouth"}:
        spirit = "sherry" if canonical_key == "dry sherry" else "vermouth"
        if spirit not in tokens:
            return False, f"missing_{spirit}_identity"
        reject = tokens & {"jalapeno", "olive", "olives", "onion", "onions", "pepper", "peppers", "stuffed", "tipsy", "vinegar"}
        if reject:
            return False, f"not_plain_{spirit}:" + "/".join(sorted(reject))
        if canonical_key == "dry sherry" and tokens & {"hot", "spicy"}:
            return False, "not_plain_sherry:hot_or_spicy"
        if "cooking" in tokens or "wine" in tokens or any(term in category for term in ("alcohol", "liqueur", "liquor", "sauce", "spirits", "wine")):
            return True, f"{spirit}_cooking_wine_label"
        return False, f"{spirit}_requires_wine_or_cooking_wine_category"

    if canonical_key in {"red food coloring", "green food coloring"}:
        color = "red" if canonical_key.startswith("red ") else "green"
        if color not in tokens or "food" not in tokens or not (tokens & {"coloring", "colouring", "color"}):
            return False, f"missing_{color}_food_coloring_identity"
        if any(term in category for term in ("baking", "decorations", "dessert", "topping")):
            return True, f"{color}_food_coloring_label"
        return False, "food_coloring_requires_baking_category"

    if canonical_key == "sauerkraut":
        if "sauerkraut" not in tokens:
            return False, "missing_sauerkraut_identity"
        reject = tokens & {"beet", "carrot", "carrots", "dog", "frankfurter", "garlic", "sandwich", "sausage", "turmeric"}
        if reject:
            return False, "not_plain_sauerkraut:" + "/".join(sorted(reject))
        if any(term in category for term in ("canned", "pickle", "relish", "vegetable")):
            return True, "plain_sauerkraut_label"
        return False, "sauerkraut_requires_pickle_or_vegetable_category"

    if canonical_key == "soy milk":
        if not (_contains_phrase(desc, "soy milk") or "soymilk" in tokens):
            return False, "missing_soy_milk_identity"
        reject = tokens & {"chai", "chocolate", "coffee", "creamer", "latte", "mocha", "nog", "powder", "shake", "vanilla"}
        if reject:
            return False, "not_plain_soy_milk:" + "/".join(sorted(reject))
        if any(term in category for term in ("milk", "plant")):
            return True, "plain_soy_milk_label"
        return False, "soy_milk_requires_plant_milk_category"

    if canonical_key in {"almond milk", "oat milk", "coconut milk"}:
        species = canonical_key.split()[0]
        compound = f"{species}milk"
        if not (_contains_phrase(desc, canonical_key) or compound in tokens):
            return False, f"missing_{species}_milk_identity"
        reject = tokens & {
            "beverage",
            "chai",
            "chocolate",
            "coffee",
            "creamer",
            "drink",
            "drinks",
            "latte",
            "mocha",
            "nata",
            "shake",
            "smoothie",
            "tea",
            "vanilla",
            "yogurt",
        }
        if reject:
            return False, f"not_plain_{species}_milk:" + "/".join(sorted(reject))
        other_species = ({"almond", "oat", "soy", "coconut"} - {species}) & tokens
        if other_species:
            return False, f"not_plain_{species}_milk_blend:" + "/".join(sorted(other_species))
        return True, f"plain_{species}_milk_label"

    if canonical_key == "cranberry juice":
        if "cranberry" not in tokens or "juice" not in tokens:
            return False, "missing_cranberry_juice_identity"
        reject = tokens & {"apple", "blend", "blueberry", "cocktail", "grape", "pomegranate", "raspberry", "sauce"}
        if reject:
            return False, "not_plain_cranberry_juice:" + "/".join(sorted(reject))
        if any(term in category for term in ("beverage", "drink", "juice")):
            return True, "cranberry_juice_label"
        return False, "cranberry_juice_requires_juice_category"

    if canonical_key == "puff pastry":
        if "puff" not in tokens or "pastry" not in tokens:
            return False, "missing_puff_pastry_identity"
        reject = tokens & {"bouchees", "cream", "eclair", "mini", "patty", "quiche", "toaster", "twist", "twists"}
        if reject:
            return False, "not_plain_puff_pastry_sheets:" + "/".join(sorted(reject))
        if not (tokens & {"sheet", "sheets", "dough", "pastry"}):
            return False, "missing_puff_pastry_sheet_identity"
        if any(term in category for term in ("bakery", "bread", "crust", "dough", "frozen", "pastry")):
            return True, "puff_pastry_sheet_label"
        return False, "puff_pastry_requires_dough_category"

    if canonical_key == "hazelnut":
        if not (tokens & {"hazelnut", "hazelnuts", "filbert", "filberts"}):
            return False, "missing_hazelnut_identity"
        reject = tokens & {"bar", "butter", "candy", "chocolate", "coffee", "cookie", "cream", "creamer", "ice", "spread", "syrup", "wafer"}
        if reject:
            return False, "not_plain_hazelnuts:" + "/".join(sorted(reject))
        if any(term in category for term in ("nut", "seed", "snack")):
            return True, "plain_hazelnut_label"
        return False, "hazelnut_requires_nut_category"

    if canonical_key == "cream of celery soup":
        if not {"cream", "celery", "soup"} <= tokens:
            return False, "missing_cream_celery_soup_identity"
        reject = tokens & {"chicken", "mushroom", "tripe", "vegetable"}
        if reject:
            return False, "not_cream_of_celery_soup:" + "/".join(sorted(reject))
        if any(term in category for term in ("canned", "condensed", "soup")):
            return True, "cream_of_celery_soup_label"
        return False, "cream_of_celery_requires_soup_category"

    if canonical_key == "cashew":
        if not (tokens & {"cashew", "cashews"}):
            return False, "missing_cashew_identity"
        reject = tokens & {"bar", "bite", "bites", "butter", "candy", "chocolate", "cluster", "clusters", "cookie", "curry", "granola", "honey", "mix", "sauce", "trail"}
        if reject:
            return False, "not_plain_cashews:" + "/".join(sorted(reject))
        if any(term in category for term in ("nut", "seed", "snack")):
            return True, "plain_cashew_label"
        return False, "cashew_requires_nut_category"

    if canonical_key == "ranch dressing":
        if "ranch" not in tokens or "dressing" not in tokens:
            return False, "missing_ranch_dressing_identity"
        reject = tokens & {"bacon", "buffalo", "chipotle", "dip", "dry", "jalapeno", "mix", "packet", "parmesan", "powder"}
        if reject:
            return False, "not_plain_ranch_dressing:" + "/".join(sorted(reject))
        if any(term in category for term in ("dressing", "mayonnaise", "salad")):
            return True, "ranch_dressing_label"
        return False, "ranch_dressing_requires_salad_dressing_category"

    if canonical_key == "cherry pie filling":
        if not {"cherry", "pie"} <= tokens or not (tokens & {"fill", "filling"}):
            return False, "missing_cherry_pie_filling_identity"
        reject = tokens & {"cake", "lite", "low", "reduced", "sugar"}
        if reject:
            return False, "not_regular_cherry_pie_filling:" + "/".join(sorted(reject))
        if any(term in category for term in ("filling", "pastry", "pie", "topping")):
            return True, "cherry_pie_filling_label"
        return False, "cherry_pie_filling_requires_filling_category"

    if canonical_key == "tahini":
        if "tahini" not in tokens:
            return False, "missing_tahini_identity"
        reject = tokens & {"biscuit", "cashew", "chocolate", "cup", "dressing", "hummus", "salad", "sauce"}
        if reject:
            return False, "not_plain_tahini:" + "/".join(sorted(reject))
        if any(term in category for term in ("condiment", "dressing", "ethnic", "mayonnaise", "sauce", "sesame")):
            return True, "tahini_paste_label"
        return False, "tahini_requires_condiment_category"

    if canonical_key == "miracle whip":
        if not {"miracle", "whip"} <= tokens:
            return False, "missing_miracle_whip_identity"
        reject = tokens & {"hot", "spicy"}
        if reject:
            return False, "not_plain_miracle_whip:" + "/".join(sorted(reject))
        if any(term in category for term in ("condiment", "dressing", "mayonnaise", "sauce", "spread")):
            return True, "miracle_whip_label"
        return False, "miracle_whip_requires_condiment_category"

    if canonical_key == "kahlua":
        if "kahlua" not in tokens and not {"coffee", "liqueur"} <= tokens:
            return False, "missing_kahlua_identity"
        reject = tokens & {"chocolate", "creamer", "cream", "powder"}
        if reject:
            return False, "not_plain_kahlua_liqueur:" + "/".join(sorted(reject))
        if any(term in category for term in ("alcohol", "liqueur", "liquor")):
            return True, "coffee_liqueur_label"
        return False, "kahlua_requires_alcohol_category"

    if canonical_key == "sunflower oil":
        if not {"sunflower", "oil"} <= tokens:
            return False, "missing_sunflower_oil_identity"
        reject = tokens & {"blend", "blended", "fish", "flavored", "garlic", "herb", "olive", "oyster", "spread", "tuna"}
        if reject:
            return False, "not_plain_sunflower_oil:" + "/".join(sorted(reject))
        if any(term in category for term in ("cooking", "oil", "oils")):
            return True, "sunflower_oil_label"
        return False, "sunflower_oil_requires_oil_category"

    if canonical_key == "quick oat":
        if not (tokens & {"oat", "oats", "oatmeal"}):
            return False, "missing_quick_oat_identity"
        if not (tokens & {"quick", "minute"}):
            return False, "missing_quick_oat_form"
        reject = tokens & {"bar", "cookie", "flavored", "granola", "instant", "maple", "protein"}
        if reject:
            return False, "not_plain_quick_oats:" + "/".join(sorted(reject))
        if any(term in category for term in ("cereal", "oat")):
            return True, "quick_oats_label"
        return False, "quick_oats_require_cereal_category"

    if canonical_key == "orzo pasta":
        if "orzo" not in tokens:
            return False, "missing_orzo_identity"
        reject = tokens & {"chicken", "kit", "meal", "pilaf", "rice", "salad", "soup", "vegetable"}
        if reject:
            return False, "not_plain_orzo:" + "/".join(sorted(reject))
        if any(term in category for term in ("noodle", "pasta")):
            return True, "orzo_pasta_label"
        return False, "orzo_requires_pasta_category"

    if canonical_key == "bisquick":
        if "bisquick" not in tokens:
            return False, "missing_bisquick_identity"
        reject = tokens & {"biscuit", "buttermilk", "cheese", "complete", "gluten", "heart", "shake"}
        if reject:
            return False, "not_original_bisquick:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "cooking", "mix", "supplies")):
            return True, "bisquick_original_baking_mix_label"
        return False, "bisquick_requires_baking_mix_category"

    if canonical_key == "mini marshmallow":
        if not (tokens & {"marshmallow", "marshmallows"}):
            return False, "missing_marshmallow_identity"
        if not (tokens & {"mini", "miniature"}):
            return False, "missing_mini_marshmallow_identity"
        reject = tokens & {"cereal", "chocolate", "cocoa", "cookie", "hot"}
        if reject:
            return False, "not_plain_mini_marshmallows:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "candy", "marshmallow")):
            return True, "mini_marshmallow_label"
        return False, "mini_marshmallow_requires_candy_category"

    if canonical_key == "marshmallow":
        if not (tokens & {"marshmallow", "marshmallows"}):
            return False, "missing_marshmallow_identity"
        reject = tokens & {"bar", "cereal", "chocolate", "cocoa", "cookie", "creme", "cream", "hot", "mini", "miniature", "syrup", "topping", "treat"}
        if reject:
            return False, "not_plain_marshmallows:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "candy", "marshmallow")):
            return True, "plain_marshmallow_label"
        return False, "marshmallow_requires_candy_category"

    if canonical_key in {"triple sec", "grand marnier"}:
        if canonical_key == "triple sec" and not {"triple", "sec"} <= tokens:
            return False, "missing_triple_sec_identity"
        if canonical_key == "grand marnier" and not {"grand", "marnier"} <= tokens:
            return False, "missing_grand_marnier_identity"
        reject = tokens & {"cranberry", "drink", "mix", "relish", "sauce", "syrup"}
        if reject:
            return False, "not_plain_orange_liqueur:" + "/".join(sorted(reject))
        if any(term in category for term in ("alcohol", "liqueur", "liquor", "spirits")):
            return True, "orange_liqueur_label"
        return False, "orange_liqueur_requires_alcohol_category"

    if canonical_key == "ritz cracker":
        if "ritz" not in tokens:
            return False, "missing_ritz_identity"
        reject = tokens & {"bits", "cheese", "chips", "fudge", "garlic", "peanut", "sandwich", "sour", "toasted", "vegetable"}
        if reject:
            return False, "not_plain_ritz_crackers:" + "/".join(sorted(reject))
        if any(term in category for term in ("biscuit", "cookie", "cracker", "snack")):
            return True, "ritz_cracker_label"
        return False, "ritz_requires_cracker_category"

    if canonical_key == "coconut oil":
        if not {"coconut", "oil"} <= tokens:
            return False, "missing_coconut_oil_identity"
        reject = tokens & {"blend", "butter", "frosting", "spray", "sunflower"}
        if reject:
            return False, "not_plain_coconut_oil:" + "/".join(sorted(reject))
        if any(term in category for term in ("cooking", "oil", "oils")):
            return True, "coconut_oil_label"
        return False, "coconut_oil_requires_oil_category"

    if canonical_key == "pita bread":
        if "pita" not in tokens:
            return False, "missing_pita_identity"
        reject = tokens & {"chip", "chips", "cracker", "crust", "gyro", "kit", "pizza", "sandwich"}
        if reject:
            return False, "not_plain_pita_bread:" + "/".join(sorted(reject))
        if any(term in category for term in ("bread", "buns", "bakery")):
            return True, "pita_bread_label"
        return False, "pita_requires_bread_category"

    if canonical_key == "frozen whipped topping":
        if "whipped" not in tokens or "topping" not in tokens:
            return False, "missing_whipped_topping_identity"
        reject = tokens & {"cake", "cocoa", "coffee", "hazelnut", "hot", "ice", "pancake", "pie", "pumpkin", "sundae"}
        if reject:
            return False, "not_plain_whipped_topping:" + "/".join(sorted(reject))
        if any(term in category for term in ("cream", "decorations", "dessert", "topping")):
            return True, "frozen_whipped_topping_label"
        return False, "whipped_topping_requires_topping_category"

    if canonical_key in {"coriander powder", "cumin powder"}:
        spice = "coriander" if canonical_key.startswith("coriander") else "cumin"
        other = "cumin" if spice == "coriander" else "coriander"
        if spice not in tokens:
            return False, f"missing_{spice}_identity"
        if not (tokens & {"ground", "powder"}):
            return False, f"missing_ground_{spice}_identity"
        if other in tokens:
            return False, f"not_plain_{spice}_powder:{other}"
        reject = tokens & {"chicken", "fajita", "sauce", "strip"}
        if reject:
            return False, f"not_plain_{spice}_powder:" + "/".join(sorted(reject))
        if any(term in category for term in ("spice", "seasoning", "herb")):
            return True, f"{spice}_powder_label"
        return False, f"{spice}_powder_requires_spice_category"

    if canonical_key in {"refrigerated crescent dinner roll", "refrigerated crescent roll", "crescent roll"}:
        if "crescent" not in tokens:
            return False, "missing_crescent_roll_identity"
        reject = tokens & {"almond", "cookie"}
        if reject:
            return False, "not_crescent_roll:" + "/".join(sorted(reject))
        if any(term in category for term in ("bread", "dough", "roll", "biscuit")):
            return True, "crescent_roll_label"
        return False, "crescent_requires_bread_or_dough_category"

    if canonical_key == "sugar substitute":
        if not ({"sugar", "substitute"} <= tokens or tokens & {"sweetener", "sucralose", "stevia", "aspartame", "splenda", "equal"}):
            return False, "missing_sugar_substitute_identity"
        reject = tokens & {"barbecue", "bbq", "coffee", "creamer", "cream", "drink", "liquid", "salt", "sauce", "syrup"}
        if reject:
            return False, "not_plain_sugar_substitute:" + "/".join(sorted(reject))
        if any(term in category for term in ("sugar", "sweetener", "substitute")):
            return True, "sugar_substitute_label"
        return False, "sugar_substitute_requires_sweetener_category"

    if canonical_key in {"colby jack cheese", "colby monterey jack cheese"}:
        if not {"colby", "jack"} <= tokens:
            return False, "missing_colby_jack_identity"
        if canonical_key == "colby monterey jack cheese" and not ("monterey" in tokens or {"colby", "jack"} <= tokens):
            return False, "missing_colby_monterey_jack_identity"
        reject = tokens & {"cracker", "dip", "mac", "popcorn", "sauce", "snack"}
        if reject:
            return False, "not_plain_colby_jack_cheese:" + "/".join(sorted(reject))
        if "cheese" in category:
            return True, "colby_jack_cheese_label"
        return False, "colby_jack_requires_cheese_category"

    if canonical_key == "ranch dressing mix":
        if "ranch" not in tokens:
            return False, "missing_ranch_identity"
        if not (tokens & {"mix", "packet", "seasoning", "dry", "recipe"}):
            return False, "missing_ranch_mix_identity"
        reject = tokens & {"bottled", "buffalo", "chipotle", "dip", "jalapeno", "parmesan", "salsa", "spicy"}
        if reject:
            return False, "not_plain_ranch_dressing_mix:" + "/".join(sorted(reject))
        if any(term in category for term in ("dressing", "marinade", "seasoning", "tenderizer")):
            return True, "ranch_dressing_mix_label"
        return False, "ranch_mix_requires_dressing_or_seasoning_category"

    if canonical_key == "graham cracker crust":
        if not {"graham", "cracker", "crust"} <= tokens:
            return False, "missing_graham_cracker_crust_identity"
        reject = tokens & {"cake", "cheesecake", "filling"}
        if reject:
            return False, "not_plain_graham_cracker_crust:" + "/".join(sorted(reject))
        if any(term in category for term in ("crust", "dough", "pie")):
            return True, "graham_cracker_crust_label"
        return False, "graham_crust_requires_crust_category"

    if canonical_key == "baguette":
        if "baguette" not in tokens:
            return False, "missing_baguette_identity"
        reject = tokens & {"cheese", "dip", "garlic", "herb", "olive", "sandwich", "snack"}
        if reject:
            return False, "not_plain_baguette:" + "/".join(sorted(reject))
        if any(term in category for term in ("bakery", "bread", "dough")):
            return True, "baguette_label"
        return False, "baguette_requires_bread_category"

    if canonical_key == "watercress":
        if "watercress" not in tokens:
            return False, "missing_watercress_identity"
        reject = tokens & {"juice", "pear", "spinach", "vanilla"}
        if reject:
            return False, "not_plain_watercress:" + "/".join(sorted(reject))
        if any(term in category for term in ("fruit", "produce", "vegetable")):
            return True, "fresh_watercress_label"
        return False, "watercress_requires_produce_category"

    if canonical_key == "mini chocolate chip":
        if "chocolate" not in tokens or not (tokens & {"chip", "chips", "morsel", "morsels"}):
            return False, "missing_mini_chocolate_chip_identity"
        if not (tokens & {"mini", "miniature"}):
            return False, "missing_mini_chip_identity"
        reject = tokens & {"bar", "cake", "cookie", "drizzle", "ice", "mug", "sandwich", "white"}
        if reject:
            return False, "not_plain_mini_chocolate_chips:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "chocolate", "dessert", "topping")):
            return True, "mini_chocolate_chip_label"
        return False, "mini_chocolate_chip_requires_baking_category"

    if canonical_key == "lump crabmeat":
        if not (tokens & {"crab", "crabmeat"}):
            return False, "missing_crabmeat_identity"
        reject = tokens & {"cake", "imitation", "roll", "salad", "soup", "stuffed", "stuffing", "surimi", "sushi"}
        if reject:
            return False, "not_plain_lump_crabmeat:" + "/".join(sorted(reject))
        if any(term in category for term in ("fish", "seafood", "shellfish")):
            return True, "lump_crabmeat_label"
        return False, "crabmeat_requires_seafood_category"

    if canonical_key == "sea scallop":
        if not (tokens & {"scallop", "scallops"}):
            return False, "missing_scallop_identity"
        reject = tokens & {"bacon", "breaded", "medley", "potato", "scalloped", "smoked", "squash", "wrapped"}
        if reject:
            return False, "not_plain_scallops:" + "/".join(sorted(reject))
        if any(term in category for term in ("fish", "seafood", "shellfish")):
            return True, "sea_scallop_label"
        return False, "scallop_requires_seafood_category"

    if canonical_key == "golden syrup":
        if "syrup" not in tokens or not (tokens & {"golden", "cane"}):
            return False, "missing_golden_syrup_identity"
        reject = tokens & {"apple", "fruit", "maple", "mandarin", "orange", "peach", "pear", "pineapple"}
        if reject:
            return False, "not_golden_syrup:" + "/".join(sorted(reject))
        if any(term in category for term in ("molasses", "sugar", "syrup")):
            return True, "golden_syrup_label"
        return False, "golden_syrup_requires_syrup_category"

    if canonical_key == "white cake mix":
        if not {"white", "cake"} <= tokens or "mix" not in tokens:
            return False, "missing_white_cake_mix_identity"
        reject = tokens & {"cheddar", "chocolate", "frosting", "red", "scone", "velvet"}
        if reject:
            return False, "not_white_cake_mix:" + "/".join(sorted(reject))
        if any(term in category for term in ("baking", "cake", "cookie", "cupcake")):
            return True, "white_cake_mix_label"
        return False, "white_cake_mix_requires_cake_mix_category"

    if canonical_key == "black eyed pea":
        if not (_contains_phrase(desc, "black eyed") or _contains_phrase(desc, "black-eyed") or tokens & {"cowpea", "cowpeas"}):
            return False, "missing_black_eyed_pea_identity"
        reject = tokens & {"bacon", "green", "snack", "wasabi"}
        if reject:
            return False, "not_plain_black_eyed_peas:" + "/".join(sorted(reject))
        if any(term in category for term in ("bean", "canned", "pea", "vegetable")):
            return True, "black_eyed_pea_label"
        return False, "black_eyed_pea_requires_legume_category"

    if canonical_key == "mixed salad green":
        if not (tokens & {"green", "greens", "lettuce", "spring"}):
            return False, "missing_salad_greens_identity"
        reject = tokens & {"bacon", "cheese", "chicken", "dressing", "egg", "kit", "turkey"}
        if reject:
            return False, "not_plain_salad_greens:" + "/".join(sorted(reject))
        if any(term in category for term in ("fruit", "produce", "vegetable")):
            return True, "mixed_salad_green_label"
        return False, "salad_greens_require_produce_category"

    if canonical_key == "wonton wrapper":
        if "wonton" not in tokens or not (tokens & {"wrapper", "wrappers"}):
            return False, "missing_wonton_wrapper_identity"
        reject = tokens & {"bites", "filled", "mini", "soup"}
        if reject:
            return False, "not_wonton_wrappers:" + "/".join(sorted(reject))
        if any(term in category for term in ("crust", "dough", "wrapper")):
            return True, "wonton_wrapper_label"
        return False, "wonton_wrapper_requires_dough_category"

    if canonical_key == "fettuccine":
        if "fettuccine" not in tokens:
            return False, "missing_fettuccine_identity"
        reject = tokens & {"alfredo", "chicken", "dinner", "meal", "rice", "sauce", "spinach", "stroganoff"}
        if reject:
            return False, "not_plain_fettuccine:" + "/".join(sorted(reject))
        if any(term in category for term in ("noodle", "pasta")):
            return True, "fettuccine_pasta_label"
        return False, "fettuccine_requires_pasta_category"

    if canonical_key == "ground flaxseed":
        if not (tokens & {"flax", "flaxseed", "linaza"}):
            return False, "missing_flaxseed_identity"
        if not (tokens & {"ground", "milled", "meal", "molida"}):
            return False, "missing_ground_flaxseed_identity"
        reject = tokens & {"bar", "cereal", "chia", "chip", "oil", "pumpkin", "sesame", "sunflower"}
        if reject:
            return False, "not_plain_ground_flaxseed:" + "/".join(sorted(reject))
        if any(term in category for term in ("grain", "seed", "spice")):
            return True, "ground_flaxseed_label"
        return False, "ground_flaxseed_requires_seed_category"

    return None


def _accept_sparse_audit_product(product: LabProduct, canonical_key: str) -> tuple[bool, str] | None:
    """Guards discovered by sparse planner purchase audits."""
    tokens = _product_tokens(product)

    if canonical_key in {"peanut butter", "creamy peanut butter", "smooth peanut butter"}:
        if not {"peanut", "butter"} <= tokens:
            return False, "missing_peanut_butter_identity"
        reject = tokens & {
            "bar",
            "bars",
            "candy",
            "cereal",
            "chip",
            "chips",
            "chocolate",
            "cookie",
            "cookies",
            "cracker",
            "crackers",
            "cup",
            "cups",
            "dessert",
            "frozen",
            "honey",
            "ice",
            "powder",
            "powdered",
            "protein",
            "sauce",
            "smoothie",
            "yogurt",
        }
        if reject:
            return False, "not_plain_peanut_butter:" + "/".join(sorted(reject))
        return True, "plain_peanut_butter_label"

    if canonical_key == "light brown sugar":
        if not {"brown", "sugar"} <= tokens:
            return False, "missing_light_brown_sugar_identity"
        reject = tokens & {"candy", "chocolate", "dark", "drink", "free", "substitute", "syrup"}
        if reject:
            return False, "not_light_brown_sugar:" + "/".join(sorted(reject))
        return True, "light_brown_sugar_label"

    if canonical_key == "turbinado sugar":
        if "sugar" not in tokens:
            return False, "missing_turbinado_sugar_identity"
        if not (tokens & {"turbinado", "raw"} or _contains_phrase(_product_text(product), "sugar in the raw")):
            return False, "missing_turbinado_or_raw_sugar_identity"
        reject = tokens & {"candy", "chocolate", "drink", "free", "substitute", "syrup"}
        if reject:
            return False, "not_turbinado_sugar:" + "/".join(sorted(reject))
        return True, "turbinado_sugar_label"

    if canonical_key == "kosher salt":
        if not {"kosher", "salt"} <= tokens:
            return False, "missing_kosher_salt_identity"
        reject = tokens & {"bath", "candy", "chocolate", "epsom", "seasoned", "truffle", "truffles"}
        if reject:
            return False, "not_kosher_salt:" + "/".join(sorted(reject))
        return True, "kosher_salt_label"

    if canonical_key in {"black peppercorn", "black peppercorns", "whole black peppercorn", "whole black peppercorns"}:
        if not (tokens & {"peppercorn", "peppercorns"}):
            return False, "missing_peppercorn_identity"
        if "black" not in tokens and not _contains_phrase(_product_text(product), "black pepper"):
            return False, "missing_black_peppercorn_identity"
        reject = tokens & {
            "blend",
            "chip",
            "chips",
            "cracker",
            "crackers",
            "crisp",
            "medley",
            "filet",
            "loin",
            "pork",
            "rainbow",
            "rub",
            "seasoned",
            "seasoning",
            "szechuan",
            "water",
        }
        if reject:
            return False, "not_whole_black_peppercorns:" + "/".join(sorted(reject))
        return True, "whole_black_peppercorn_label"

    if canonical_key in {"cinnamon stick", "cinnamon sticks"}:
        if "cinnamon" not in tokens or not (tokens & {"stick", "sticks"}):
            return False, "missing_cinnamon_stick_identity"
        reject = tokens & {"candy", "cereal", "creamer", "drink", "ground", "roll", "rolls", "syrup"}
        if reject:
            return False, "not_cinnamon_stick:" + "/".join(sorted(reject))
        return True, "cinnamon_stick_label"

    if canonical_key in {"clove", "cloves", "whole clove", "whole cloves"}:
        if not (tokens & {"clove", "cloves"}):
            return False, "missing_clove_identity"
        reject = tokens & {"blend", "ground", "powder", "rub", "seasoning"}
        if reject:
            return False, "not_whole_clove:" + "/".join(sorted(reject))
        return True, "whole_clove_label"

    if canonical_key in {"italian roll", "italian rolls"}:
        if not (tokens & {"bun", "buns", "hoagie", "roll", "rolls", "sub"}):
            return False, "missing_italian_roll_identity"
        reject = tokens & {
            "burger",
            "cinnamon",
            "dinner",
            "dough",
            "hamburger",
            "hawaiian",
            "mozzarella",
            "onion",
            "sweet",
            "yeasty",
        }
        if reject:
            return False, "not_crusty_sandwich_roll:" + "/".join(sorted(reject))
        if tokens & {"french", "hard", "hoagie", "kaiser", "sandwich", "sausage", "steak", "sub"}:
            return True, "crusty_sandwich_roll_label"
        if "italian" in tokens and (tokens & {"roll", "rolls"}):
            return True, "italian_roll_label"
        return False, "italian_roll_requires_sandwich_roll_form"

    if canonical_key in {"kernel corn", "whole kernel corn"}:
        if "corn" not in tokens:
            return False, "missing_kernel_corn_identity"
        if not (tokens & {"canned", "golden", "kernel", "kernels", "sweet", "whole", "yellow"}):
            return False, "missing_whole_kernel_corn_form"
        reject = tokens & {"bread", "cereal", "chip", "chips", "cream", "creamed", "fire", "popcorn", "roasted", "street", "syrup", "tortilla"}
        if reject:
            return False, "not_whole_kernel_corn:" + "/".join(sorted(reject))
        return True, "whole_kernel_corn_label"

    if canonical_key == "canned corn":
        if "corn" not in tokens or not (tokens & {"can", "canned"}):
            return False, "missing_canned_corn_identity"
        if not (tokens & {"golden", "kernel", "kernels", "sweet", "whole", "yellow"}):
            return False, "missing_canned_whole_kernel_corn_form"
        reject = tokens & {"cream", "creamed", "fire", "mexican", "roasted", "street"}
        if reject:
            return False, "not_plain_canned_corn:" + "/".join(sorted(reject))
        return True, "plain_canned_corn_label"

    if canonical_key in {"canned green bean", "canned green beans"}:
        if not {"green", "beans"} <= tokens:
            return False, "missing_canned_green_bean_identity"
        reject = tokens & {"butter", "fresh", "frozen", "garlic", "herb", "onion", "onions", "roasted", "steamfresh"}
        if reject:
            return False, "not_plain_canned_green_beans:" + "/".join(sorted(reject))
        if tokens & {"can", "canned"} or _contains_phrase(_product_text(product), "canned vegetables"):
            return True, "plain_canned_green_beans_label"
        return False, "canned_green_beans_requires_canned_form"

    if canonical_key == "yellow squash":
        if "squash" not in tokens:
            return False, "missing_yellow_squash_identity"
        if not (tokens & {"crookneck", "straightneck", "summer", "yellow"}):
            return False, "missing_yellow_squash_form"
        reject = tokens & {"garden", "gardening", "heirloom", "packet", "seed", "seeds"}
        if reject:
            return False, "not_yellow_squash_produce:" + "/".join(sorted(reject))
        return True, "plain_yellow_squash_label"

    if canonical_key in {
        "boneless pork chop",
        "boneless pork chops",
        "boneless pork loin chop",
        "boneless pork loin chops",
        "pork chop",
        "pork chops",
        "pork loin chop",
        "pork loin chops",
    }:
        if "pork" not in tokens:
            return False, "missing_pork_chop_identity"
        if not (tokens & {"chop", "chops", "loin"}):
            return False, "missing_pork_chop_form"
        reject = tokens & {
            "barbecue",
            "bbq",
            "breaded",
            "cooked",
            "flavored",
            "fritter",
            "honey",
            "hot",
            "kit",
            "marinated",
            "meal",
            "patty",
            "patties",
            "sauce",
            "seasoned",
            "smoked",
        }
        if reject:
            return False, "not_raw_pork_chop:" + "/".join(sorted(reject))
        return True, "raw_pork_chop_label"

    if canonical_key in {"pork rib", "pork ribs", "pork sparerib", "pork spareribs", "boneless pork ribs"}:
        if "pork" not in tokens:
            return False, "missing_pork_rib_identity"
        rib_terms = {"backrib", "backribs", "rib", "riblet", "riblets", "ribs", "sparerib", "spareribs"}
        if not (tokens & rib_terms or _contains_phrase(_product_text(product), "baby back")):
            return False, "missing_pork_rib_form"
        reject = tokens & {
            "barbecue",
            "bbq",
            "breaded",
            "cooked",
            "flavored",
            "fritter",
            "honey",
            "hot",
            "lloyd",
            "marinated",
            "meal",
            "patty",
            "patties",
            "sauce",
            "seasoned",
            "smoked",
        }
        if reject:
            return False, "not_raw_pork_ribs:" + "/".join(sorted(reject))
        return True, "raw_pork_rib_label"

    if canonical_key in {"italian meatball", "italian meatballs", "meatballs", "frozen meatballs"}:
        if not (tokens & {"meatball", "meatballs"}):
            return False, "missing_meatball_identity"
        reject = tokens & {
            "chicken",
            "meal",
            "meatless",
            "pasta",
            "ravioli",
            "sandwich",
            "soup",
            "turkey",
            "vegetarian",
            "veggie",
            "wing",
            "wings",
        }
        if reject:
            return False, "not_plain_italian_meatballs:" + "/".join(sorted(reject))
        if canonical_key.startswith("italian") and "italian" not in tokens:
            return False, "missing_italian_meatball_form"
        return True, "plain_meatball_label"

    if canonical_key == "beef bologna":
        if not {"beef", "bologna"} <= tokens:
            return False, "missing_beef_bologna_identity"
        reject = tokens & {"cheese", "cracker", "crackers", "sandwich"}
        if reject:
            return False, "not_plain_beef_bologna:" + "/".join(sorted(reject))
        return True, "plain_beef_bologna_label"

    if canonical_key in {"boneless pork roast", "pork roast", "pork loin roast"}:
        if "pork" not in tokens or not (tokens & {"loin", "roast", "shoulder"}):
            return False, "missing_pork_roast_identity"
        reject = tokens & {
            "bacon",
            "barbecue",
            "bbq",
            "chef",
            "chop",
            "chops",
            "cooked",
            "garlic",
            "gravy",
            "ham",
            "herb",
            "kit",
            "lemon",
            "marinated",
            "meal",
            "mesquite",
            "mix",
            "seasoned",
            "seasoning",
            "smoked",
            "steak",
            "steaks",
            "vegetable",
            "vegetables",
        }
        if reject:
            return False, "not_plain_pork_roast:" + "/".join(sorted(reject))
        if _contains_phrase(_product_text(product), "bone in"):
            return False, "not_plain_pork_roast:bone_in"
        return True, "plain_pork_roast_label"

    return None


_AUDIT_CLASS_BY_UPC: dict[str, tuple[str, str, str, str, str, float, str]] | None = None
_AUDIT_CLASS_DB_PATH = "/Users/jamiebarton/Desktop/Hestia/api/data/product_audit_classification.db"

# Canonical -> (list of expected_audit_path_prefixes, forbidden_modifier_tokens).
# Hard-coded for now; STRUCTURED_MATCHER_SPEC Part 5 moves this to a generated
# canonical_retail_bridge table. Prefixes calibrated against ground-truth
# debug dump (commit f49da18): the audit's actual path strings, not guesses.
_CANONICAL_AUDIT_EXPECTATION: dict[str, tuple[list[str], set[str]]] = {
    "macaroni":          (["Pantry > Pasta > Macaroni",
                           "Pantry > Pastas > Macaroni",
                           "Grocery > Pasta > Macaroni"],
                          {"salad", "kit", "dinner", "casserole"}),
    "chicken drumstick": (["Meat & Seafood > Poultry", "Meat & Seafood > Meat > Poultry"],
                          {"breaded", "battered", "seasoned", "tenders", "nuggets", "popcorn", "marinated"}),
    # green onion: audit uses Produce > Vegetables > Onions > Chopped > Green (not "Fresh Vegetables").
    # Accept any path that goes through Onions + Green / Scallion / Spring.
    "green onion":       (["Produce > Vegetables > Onions",
                           "Produce > Onions",
                           "Produce > Fresh Vegetables > Onions"], set()),
    # tomato juice: audit also uses Beverage > Drink > Tomatoes for legit tomato juice.
    # Reject sodas/cocktail-mixers via forbidden modifiers; reject diced tomatoes via path mismatch (canned vegetables path won't match).
    "tomato juice":      (["Beverage > Juice > Tomato",
                           "Beverage > Drink > Tomatoes",
                           "Beverage > Juice"],
                          {"cocktail", "soda", "carbonated", "michelada", "mixer"}),
    # Plain oats / oatmeal. Audit splits cleanly:
    #   Pantry > Cereal > Oats             (87)  plain rolled
    #   Pantry > Grain > Oats > *          (~50) steel cut, instant-no-flavor, whole
    #   Pantry > Grain > Steel Cut Oats    audit's preferred bucket for esha 93119
    # Flavored variants live elsewhere:
    #   Pantry > Cereal > Oatmeal Raisin Cookie / Creme Pies (cookies disguised)
    #   Snack > Cookies > Oatmeal Chocolate Chip
    # canonical_to_esha.csv currently mis-maps `oatmeal` to esha 44533
    # (Muffin, oatmeal), poisoning the bridge — fix in surface dict.
    "oat":               (["Pantry > Cereal > Oats",
                           "Pantry > Grain > Oats",
                           "Pantry > Grain > Steel Cut Oats",
                           "Pantry > Grain > Instant Oats"],
                          {"flavored", "apples", "cinnamon", "maple", "fruit",
                           "variety pack", "raisin cookie", "creme pies",
                           "chocolate chip", "granola", "bran", "cracklin",
                           "peaches", "cream", "strawberry", "honey nut"}),
    "oatmeal":           (["Pantry > Cereal > Oats",
                           "Pantry > Grain > Oats",
                           "Pantry > Grain > Steel Cut Oats",
                           "Pantry > Grain > Instant Oats"],
                          {"flavored", "apples", "cinnamon", "maple", "fruit",
                           "variety pack", "raisin cookie", "creme pies",
                           "chocolate chip", "muffin", "bran", "cracklin",
                           "peaches", "cream", "strawberry", "honey nut"}),
}


def _load_audit_class_by_upc() -> dict[str, tuple[str, str, str, str, str, float, str]]:
    global _AUDIT_CLASS_BY_UPC
    if _AUDIT_CLASS_BY_UPC is not None:
        return _AUDIT_CLASS_BY_UPC
    import sqlite3 as _sql
    out: dict[str, tuple[str, str, str, str, str, float, str]] = {}
    try:
        con = _sql.connect(_AUDIT_CLASS_DB_PATH)
        for upc, cp, var, flv, ftc, ps, conf, method in con.execute(
            "SELECT upc, canonical_path, variant, flavor, form_texture_cut, "
            "processing_storage, audit_confidence, classification_method "
            "FROM product_audit_classification"
        ):
            t = (cp or "", var or "", flv or "", ftc or "", ps or "", float(conf or 0.0), method or "")
            # store under both raw and zero-stripped forms — calculator and cache disagree
            if upc:
                out[str(upc)] = t
                stripped = str(upc).lstrip("0")
                if stripped and stripped != str(upc):
                    out[stripped] = t
        con.close()
    except Exception:
        pass
    _AUDIT_CLASS_BY_UPC = out
    return out


def accept_via_audit(product: LabProduct, canonical: str) -> tuple[bool, str] | None:
    """Audit-driven product accept. Returns:
        (True, reason)  -> accept (audit classification matches expected path)
        (False, reason) -> reject (audit says wrong canonical or has forbidden modifier)
        None            -> fall through to legacy per-canonical rules (no expectation
                           defined for this canonical, or no audit classification for
                           this UPC, or classification_method=='unclassified').
    """
    canonical_key = normalize_key(canonical)
    hard_spec = _CANONICAL_AUDIT_EXPECTATION.get(canonical_key)
    if hard_spec is None:
        return None
    bridge_spec = _load_canonical_retail_bridge().get(canonical_key)
    expected_prefixes: list[str] = []
    forbidden_modifiers: set[str] = set()
    hard_prefixes, hard_forbidden = hard_spec
    if isinstance(hard_prefixes, str):  # back-compat: single string
        hard_prefixes = [hard_prefixes]
    expected_prefixes.extend(hard_prefixes)
    forbidden_modifiers.update(hard_forbidden or set())
    if bridge_spec:
        raw_paths = bridge_spec.get("expected_canonical_paths") or []
        if isinstance(raw_paths, list):
            expected_prefixes.extend(str(p) for p in raw_paths if str(p).strip())
        if bridge_spec.get("expected_canonical_path"):
            expected_prefixes.append(str(bridge_spec["expected_canonical_path"]))
        raw_forbidden = bridge_spec.get("forbidden_modifiers") or []
        if isinstance(raw_forbidden, (list, tuple, set)):
            forbidden_modifiers.update(str(t).strip().lower() for t in raw_forbidden if str(t).strip())
        elif isinstance(raw_forbidden, str):
            forbidden_modifiers.update(t.strip().lower() for t in raw_forbidden.split(",") if t.strip())
    # Deduplicate while preserving the hard guardrail prefixes first.
    expected_prefixes = list(dict.fromkeys(expected_prefixes))
    upc = (product.gtin_upc or "").strip()
    if not upc:
        return None
    classes = _load_audit_class_by_upc()
    cls = classes.get(upc) or classes.get(upc.lstrip("0"))
    title_blob = " ".join([
        product.description or "",
        product.brand_name or "",
        product.category or "",
    ]).lower()
    if not cls or cls[6] == "unclassified":
        # No reliable audit classification. We still apply the title
        # forbidden-modifier check for canonicals with strict expectation
        # rules — otherwise products like Cracklin Oat Bran or
        # Peaches & Cream Instant Oatmeal slip past the legacy chain.
        for mod in forbidden_modifiers:
            if mod and mod in title_blob:
                return False, f"audit_forbidden_modifier_title:{mod}"
        return None
    canonical_path, variant, flavor, ftc, ps, conf, method = cls
    # Forbidden modifiers checked first — kills sodas / cocktail mixers /
    # breaded variants regardless of path. Check both audit fields and title
    # so audit-classified products with the modifier only in the description
    # (e.g. Clamato Michelada labelled under Beverage > Juice) are still cut.
    audit_blob = " ".join([variant or "", flavor or "", ftc or "", ps or "", canonical_path or ""]).lower()
    for mod in forbidden_modifiers:
        if mod and (mod in audit_blob or mod in title_blob):
            return False, f"audit_forbidden_modifier:{mod}"
    # Path prefix match — any of the listed prefixes
    for prefix in expected_prefixes:
        if canonical_path.startswith(prefix):
            return True, f"audit_accept:{canonical_path[:60]}"
    return False, f"audit_path_mismatch:{canonical_path[:60]}"


def _product_acceptance_reason(product: LabProduct, canonical: str) -> tuple[bool, str]:
    # Step 3: audit-driven accept runs FIRST. If the canonical has an expectation
    # row AND the product has an audit classification, this decides. Otherwise,
    # fall through to the legacy per-canonical chain unchanged.
    audit_decision = accept_via_audit(product, canonical)
    if audit_decision is not None:
        return audit_decision

    text = _product_text(product)
    tokens = _product_tokens(product)
    canonical_key = normalize_key(canonical)
    canonical_tokens = set(canonical_key.split()) - {"and", "or", "with", "food", "product"}

    milk_decision = _accept_milk_product(product, canonical_key)
    if milk_decision is not None:
        return milk_decision

    egg_decision = _accept_egg_product(product, canonical_key)
    if egg_decision is not None:
        return egg_decision

    mayonnaise_decision = _accept_mayonnaise_product(product, canonical_key)
    if mayonnaise_decision is not None:
        return mayonnaise_decision

    oil_decision = _accept_oil_product(product, canonical_key)
    if oil_decision is not None:
        return oil_decision

    cocoa_decision = _accept_cocoa_powder_product(product, canonical_key)
    if cocoa_decision is not None:
        return cocoa_decision

    produce_decision = _accept_raw_produce_product(product, canonical_key)
    if produce_decision is not None:
        return produce_decision

    breadcrumb_decision = _accept_breadcrumb_product(product, canonical_key)
    if breadcrumb_decision is not None:
        return breadcrumb_decision

    mint_decision = _accept_fresh_mint_product(product, canonical_key)
    if mint_decision is not None:
        return mint_decision

    hot_sauce_decision = _accept_hot_sauce_product(product, canonical_key)
    if hot_sauce_decision is not None:
        return hot_sauce_decision

    recipe_volume_edge_decision = _accept_recipe_volume_edge_product(product, canonical_key)
    if recipe_volume_edge_decision is not None:
        return recipe_volume_edge_decision

    sparse_audit_decision = _accept_sparse_audit_product(product, canonical_key)
    if sparse_audit_decision is not None:
        return sparse_audit_decision

    batch11_decision = _accept_batch11_product(product, canonical_key)
    if batch11_decision is not None:
        return batch11_decision

    batch12_decision = _accept_batch12_product(product, canonical_key)
    if batch12_decision is not None:
        return batch12_decision

    batch9_decision = _accept_batch9_product(product, canonical_key)
    if batch9_decision is not None:
        return batch9_decision

    batch10_decision = _accept_batch10_product(product, canonical_key)
    if batch10_decision is not None:
        return batch10_decision

    if canonical_key in {"beef stew meat", "boneless beef stew meat", "beef chuck stew meat", "chuck stew meat", "stew meat"}:
        reject = tokens & {
            "armour",
            "can",
            "canned",
            "castleberry",
            "dinty",
            "elk",
            "frozen",
            "gravy",
            "homestyle",
            "kinder",
            "kit",
            "meal",
            "mix",
            "moore",
            "roast",
            "sauce",
            "seasoning",
            "shelf",
            "soup",
            "stable",
        }
        if reject:
            return False, "not_plain_beef_stew_meat:" + "/".join(sorted(reject))
        if not ("beef" in tokens and "stew" in tokens and (tokens & {"boneless", "meat"})):
            return False, "missing_beef_stew_meat_identity"
        return True, "plain_beef_stew_meat_label"

    if canonical_key in {"pork chop", "pork chops"}:
        if not ("pork" in tokens and (tokens & {"chop", "chops"})):
            return False, "missing_pork_chop_identity"
        reject = tokens & {
            "applewood",
            "bacon",
            "bbq",
            "breaded",
            "cheddar",
            "cooked",
            "country",
            "filet",
            "fried",
            "fritter",
            "frozen",
            "garlic",
            "gravy",
            "herb",
            "hickory",
            "marinated",
            "meal",
            "patty",
            "rubbed",
            "seasoned",
            "smoked",
            "stuffed",
        }
        if reject:
            return False, "not_plain_pork_chop:" + "/".join(sorted(reject))
        return True, "plain_pork_chop_label"

    if canonical_key in {"buttermilk", "whole buttermilk"}:
        if "buttermilk" not in tokens:
            return False, "missing_buttermilk_identity"
        reject = tokens & {
            "biscuit",
            "biscuits",
            "bread",
            "dressing",
            "english",
            "mix",
            "muffin",
            "muffins",
            "pancake",
            "pancakes",
            "powder",
            "powdered",
            "ranch",
            "waffle",
            "waffles",
        }
        if reject:
            return False, "not_plain_buttermilk:" + "/".join(sorted(reject))
        return True, "plain_buttermilk_label"

    if canonical_key == "cream cheese":
        if not {"cream", "cheese"} <= tokens:
            return False, "missing_cream_cheese_identity"
        if {"dairy", "free"} <= tokens or {"plant", "based"} <= tokens:
            return False, "not_plain_cream_cheese:plant_or_dairy_free"
        reject = tokens & {
            "blueberry",
            "brown",
            "chive",
            "cinnamon",
            "dip",
            "frosting",
            "garden",
            "honey",
            "jalapeno",
            "onion",
            "pecan",
            "pineapple",
            "salmon",
            "strawberries",
            "strawberry",
            "sugar",
            "vegetable",
            "whipped",
        }
        if reject:
            return False, "not_plain_cream_cheese:" + "/".join(sorted(reject))
        if any(term in _product_category(product) for term in ("cheese", "dairy")) or _is_retail_bridge_product(product):
            return True, "plain_cream_cheese_label"
        return False, "cream_cheese_requires_dairy_category"

    if canonical_key in {"swiss cheese", "provolone cheese"}:
        cheese_identity = "swiss" if canonical_key == "swiss cheese" else "provolone"
        if cheese_identity not in tokens:
            return False, f"missing_{cheese_identity}_cheese_identity"
        reject = tokens & {
            "blend",
            "blends",
            "board",
            "cheddar",
            "dip",
            "mozzarella",
            "quiche",
            "romano",
        }
        if canonical_key == "provolone cheese" and "non" not in tokens:
            reject |= tokens & {"smoke", "smoked"}
        if reject:
            return False, f"not_plain_{cheese_identity}_cheese:" + "/".join(sorted(reject))
        if any(term in _product_category(product) for term in ("cheese", "dairy")) or _is_retail_bridge_product(product):
            return True, f"plain_{cheese_identity}_cheese_label"
        return False, f"{cheese_identity}_cheese_requires_dairy_category"

    if canonical_key == "orange juice":
        if "juice" not in tokens or not (tokens & {"orange", "oranges"}):
            return False, "missing_orange_juice_identity"
        reject = tokens & {"beverage", "cocktail", "cup", "cups", "drink", "gel", "mandarin", "mango", "punch", "segments", "snack"}
        if reject:
            return False, "not_plain_orange_juice:" + "/".join(sorted(reject))
        return True, "plain_orange_juice_label"

    if canonical_key == "garlic":
        if "garlic" not in tokens:
            return False, "missing_garlic_identity"
        reject = tokens & {
            "black", "blend", "bread", "butter", "cauliflower", "chives", "chopped",
            "crushed", "crouton", "diced", "dip", "dressing", "frozen", "herb",
            "mashed", "minced", "mushroom", "mushrooms", "oil", "parmesan", "paste",
            "pea", "peas", "pickled", "potato", "potatoes", "powder", "puree", "salt",
            "sauce", "seasoning", "spread", "stir", "sweet", "uncrooton", "uncrouton",
            "water",
        }
        if reject:
            return False, "not_plain_fresh_garlic:" + "/".join(sorted(reject))
        if any(term in _product_category(product) for term in ("fruit", "produce", "vegetable")) or _is_retail_bridge_product(product):
            return True, "fresh_garlic_label"
        return False, "garlic_requires_fresh_produce_category"

    if canonical_key == "baking soda":
        if not ({"baking", "soda"} <= tokens or {"sodium", "bicarbonate"} <= tokens):
            return False, "missing_baking_soda_identity"
        reject = tokens & {
            "absorber",
            "cleaner",
            "cleaning",
            "deodorizing",
            "fridge",
            "freezer",
            "odor",
            "refrigerator",
        }
        if reject:
            return False, "not_food_baking_soda:" + "/".join(sorted(reject))
        return True, "food_baking_soda_label"

    if canonical_key == "cornmeal":
        if "cornmeal" not in tokens and not {"corn", "meal"} <= tokens:
            return False, "missing_cornmeal_identity"
        reject = tokens & {"breading", "fish", "flour", "hushpuppies", "hushpuppy", "mush"}
        if reject:
            return False, "not_plain_cornmeal:" + "/".join(sorted(reject))
        return True, "plain_cornmeal_label"

    if canonical_key == "italian sausage":
        if not {"italian", "sausage"} <= tokens:
            return False, "missing_italian_sausage_identity"
        reject = tokens & {"chicken", "garlic", "hot", "meatball", "meatballs", "pasta", "pizza", "ravioli", "salami", "sauce", "smoked", "soup", "sweet", "turkey"}
        if reject:
            return False, "not_plain_mild_italian_sausage:" + "/".join(sorted(reject))
        return True, "plain_italian_sausage_label"

    if canonical_key == "pizza sauce":
        if not {"pizza", "sauce"} <= tokens:
            return False, "missing_pizza_sauce_identity"
        reject = tokens & {"meal", "pepperoni", "snack"}
        if reject:
            return False, "not_plain_pizza_sauce:" + "/".join(sorted(reject))
        return True, "plain_pizza_sauce_label"

    if canonical_key == "dry pasta":
        pasta_terms = {
            "bucatini",
            "cavatappi",
            "elbow",
            "farfalle",
            "fettuccine",
            "fusilli",
            "linguine",
            "macaroni",
            "noodle",
            "noodles",
            "pasta",
            "penne",
            "radiatore",
            "rigatoni",
            "rotini",
            "spaghetti",
            "ziti",
        }
        if not (tokens & pasta_terms):
            return False, "missing_dry_pasta_identity"
        reject = tokens & {
            "bruschetta",
            "dinner",
            "kit",
            "meal",
            "salad",
            "sauce",
            "sauces",
            "tomato",
            "tomatoes",
        }
        if reject:
            return False, "not_plain_dry_pasta:" + "/".join(sorted(reject))
        return True, "plain_dry_pasta_label"

    if canonical_key == "monosodium glutamate":
        if "liquid water enhancer" in text or "energy" in tokens or "cranberry" in tokens:
            return False, "water_enhancer_not_msg"
        if "tenderizer" in tokens and "monosodium" not in tokens and "glutamate" not in tokens:
            return False, "tenderizer_not_msg"
        if "monosodium" in tokens and "glutamate" in tokens:
            return True, "contains_monosodium_glutamate"
        if "msg" in tokens or {"m", "s", "g"} <= tokens:
            return True, "contains_msg"
        if ("accent" in text or "ac cent" in text) and ("seasoning" in tokens or "enhancer" in tokens):
            return True, "accent_seasoning_label"
        return False, "missing_msg_identity"

    if canonical_key == "chickpea flour":
        if _reject_combo_product(canonical, product):
            return False, _reject_combo_product(canonical, product)
        pulse_hit = bool(tokens & {"besan", "chickpea", "garbanzo"})
        if pulse_hit and "flour" in tokens:
            return True, "chickpea_garbanzo_besan_flour"
        return False, "missing_chickpea_flour_identity"

    if canonical_key == "pea":
        if _reject_combo_product(canonical, product):
            return False, _reject_combo_product(canonical, product)
        vegetable_extras = tokens & {"bean", "beans", "broccoli", "carrot", "carrots", "chestnut", "chestnuts", "pepper", "peppers", "squash"}
        if vegetable_extras:
            return False, "mixed_vegetable_product:" + "/".join(sorted(vegetable_extras))
        if tokens & {"blackeye", "blackeyed", "cowpea"}:
            return False, "different_pea_type"
        if "pea" in tokens or "peas" in tokens:
            return True, "plain_pea_label"
        return False, "missing_pea_identity"

    if canonical_key == "rice chex":
        if tokens & {"apple", "cinnamon", "corn", "wheat"} and not canonical_tokens & {"apple", "cinnamon", "corn", "wheat"}:
            return False, "flavored_or_mixed_chex"
        if "rice" in tokens and "chex" in tokens:
            return True, "rice_chex_label"
        return False, "missing_rice_chex_identity"

    if canonical_key in {"rum", "spiced rum", "dark rum", "light rum", "white rum"}:
        if not any(term in tokens for term in ("rum", "liquor", "alcohol")):
            return False, "missing_rum_identity"
        if not any(term in tokens for term in ("liquor", "alcohol", "rum")) or not any(
            term in normalize_key(product.category).split() for term in ("liquor", "alcohol", "wine", "spirits")
        ):
            return False, "rum_requires_alcohol_retail_category"
        return True, "rum_alcohol_category"

    if canonical_key == "southern comfort":
        if not _contains_phrase(_product_desc(product), "southern comfort"):
            return False, "missing_southern_comfort_identity"
        if not any(term in tokens for term in ("alcohol", "liquor", "proof", "spirit", "whiskey")):
            return False, "southern_comfort_requires_liquor_identity"
        return True, "southern_comfort_liquor_label"

    if "vinaigrette" in canonical_tokens or "dressing" in canonical_tokens:
        category = normalize_key(product.category)
        if "salad dressing" not in category and "condiment" not in category and "sauce" not in category:
            return False, "dressing_requires_condiment_category"
        if canonical_tokens and not canonical_tokens <= tokens:
            return False, "missing_vinaigrette_identity"
        return True, "vinaigrette_dressing_label"

    if canonical_key == "baking apple":
        combo_reject = _reject_combo_product(canonical, product)
        if combo_reject:
            return False, combo_reject
        if "apple" in tokens or "apples" in tokens:
            return True, "plain_apple_for_baking"
        return False, "missing_apple_identity"

    combo_reject = _reject_combo_product(canonical, product)
    if combo_reject:
        return False, combo_reject
    if canonical_tokens and canonical_tokens <= tokens:
        return True, "contains_required_canonical_terms"
    if _has_phrase(product.description, canonical):
        return True, "contains_canonical_phrase"
    return False, "missing_required_canonical_terms"


def _limit_reviewed_products(products: list[LabProduct], limit: int) -> list[LabProduct]:
    if not any(_is_retail_bridge_product(product) for product in products):
        return products[:limit]
    out: list[LabProduct] = []
    source_counts: dict[str, int] = {}
    for product in products:
        source = product.source or ""
        source_counts[source] = source_counts.get(source, 0)
        if source_counts[source] >= limit:
            continue
        source_counts[source] += 1
        out.append(product)
    return out


_DEBUG_DUMPER_HANDLE = None
_DEBUG_DUMPER_PATH: str | None = None


def _debug_dump_row(row: dict) -> None:
    """Spec Part 1 instrumentation. Emits one JSON row per (canonical, product)
    pair when env RUVS_PRODUCT_DEBUG_PATH is set. Read-only; does not change
    matcher behavior."""
    global _DEBUG_DUMPER_HANDLE, _DEBUG_DUMPER_PATH
    target = os.environ.get("RUVS_PRODUCT_DEBUG_PATH")
    if not target:
        return
    if _DEBUG_DUMPER_PATH != target:
        if _DEBUG_DUMPER_HANDLE is not None:
            try: _DEBUG_DUMPER_HANDLE.close()
            except Exception: pass
        try:
            _DEBUG_DUMPER_HANDLE = open(target, "a", encoding="utf-8")
            _DEBUG_DUMPER_PATH = target
        except Exception:
            _DEBUG_DUMPER_HANDLE = None
            _DEBUG_DUMPER_PATH = None
            return
    try:
        _DEBUG_DUMPER_HANDLE.write(json.dumps(row, default=str) + "\n")
        _DEBUG_DUMPER_HANDLE.flush()
    except Exception:
        pass


def _classify_acceptance_path(reason: str, product: LabProduct) -> str:
    """Bucket a rejection/acceptance reason into one of the spec's
    acceptance_path categories: audit_exact, audit_compatible,
    nutrition_code_match, legacy_branch, legacy_combo_reject,
    unclassified_fallback."""
    if reason.startswith("audit_accept"):
        return "audit_exact" if "audit_accept:" in reason and ":" in reason else "audit_compatible"
    if reason.startswith("audit_path_mismatch") or reason.startswith("audit_forbidden_modifier"):
        return "audit_compatible"
    if reason in ("combo_or_prepared_product", "missing_required_canonical_terms") or "combo" in reason or "prepared" in reason:
        return "legacy_combo_reject"
    if "fallback_token_match" in reason or "missing_required_canonical_terms" in reason:
        return "unclassified_fallback"
    return "legacy_branch"


def _review_products(products: list[LabProduct], canonical: str, limit: int = 25) -> tuple[list[LabProduct], list[LabProduct]]:
    accepted: list[LabProduct] = []
    rejected: list[LabProduct] = []
    debug_on = bool(os.environ.get("RUVS_PRODUCT_DEBUG_PATH"))
    audit_classes = _load_audit_class_by_upc() if debug_on else None
    for product in products:
        ok, reason = _product_acceptance_reason(product, canonical)
        reviewed = LabProduct(
            gtin_upc=product.gtin_upc,
            description=product.description,
            brand_name=product.brand_name,
            category=product.category,
            source=product.source,
            decision="accept" if ok else "reject",
            reason=reason,
        )
        if debug_on:
            cls = audit_classes.get(product.gtin_upc) or audit_classes.get((product.gtin_upc or "").lstrip("0")) if audit_classes else None
            row = {
                "canonical_key": normalize_key(canonical),
                "canonical_name": canonical,
                "product_title": product.description,
                "product_brand": product.brand_name,
                "product_category": product.category,
                "product_source": product.source,
                "product_upc": product.gtin_upc,
                "accepted": ok,
                "rejection_reason": "" if ok else reason,
                "accept_reason": reason if ok else "",
                "acceptance_path": _classify_acceptance_path(reason, product),
            }
            if cls:
                cp, var, flv, ftc, ps, conf, method = cls
                row.update({
                    "product_canonical_path": cp,
                    "product_variant": var,
                    "product_flavor": flv,
                    "product_form_texture_cut": ftc,
                    "product_processing_storage": ps,
                    "audit_confidence": conf,
                    "classification_method": method,
                })
            else:
                row.update({
                    "product_canonical_path": None,
                    "audit_confidence": None,
                    "classification_method": "no_classification",
                })
            _debug_dump_row(row)
        if ok:
            accepted.append(reviewed)
        else:
            rejected.append(reviewed)
    return _limit_reviewed_products(accepted, limit), rejected[:limit]


def _scale(row: dict[str, float], grams: float) -> NutritionEstimate:
    scale = grams / 100.0
    return NutritionEstimate(
        kcal=row.get("kcal", 0.0) * scale,
        protein_g=row.get("protein", 0.0) * scale,
        fat_g=row.get("fat", 0.0) * scale,
        carbs_g=row.get("carbs", 0.0) * scale,
    )


def _row_has_reviewed_nutrition(row: dict[str, str]) -> bool:
    state = (row.get("nutrition_match_state") or "").strip()
    code_type = (row.get("nutrition_code_type") or "").strip()
    if state in {"sr28_match", "fndds_match"}:
        return True
    if code_type in {"sr28_reference_match", "fndds_reference_match"}:
        return True
    if (row.get("esha_code") or "").strip():
        esha = nutrition_for_esha(row["esha_code"])
        return bool(esha and esha.get("tier") == "A_label_median")
    return False


def _contextual_surface_item(item: str, display: str) -> tuple[str, str]:
    item_key = normalize_key(item)
    display_key = normalize_key(display)
    display_tokens = set(display_key.split())
    if item_key == "parsley" and "parsley" in display_tokens and display_tokens & {"chopped", "fresh", "leaves", "leaf"}:
        return "fresh parsley", "display_requires_fresh_parsley"

    if item_key in {"kernel corn", "whole kernel corn"} and display_tokens & {"can", "canned", "cans", "drained"}:
        return "canned corn", "display_requires_canned_corn"

    if item_key in {"green bean", "green beans"} and display_tokens & {"can", "canned", "cans", "drained"}:
        return "canned green beans", "display_requires_canned_green_beans"

    dry_gravy_terms = {"dry", "instant", "mix", "packet", "powder", "granules"}
    if (
        item_key in {"gravy instant beef dry", "gravy beef dry", "instant beef gravy dry"}
        and {"beef", "gravy"} <= display_tokens
        and not (display_tokens & dry_gravy_terms)
    ):
        return "beef gravy", "display_requires_ready_beef_gravy"

    return item, ""


def _resolve_surface(item: str, display: str) -> tuple[dict[str, str] | None, list[str]]:
    path: list[str] = []
    index = _surface_index()
    item, context_reason = _contextual_surface_item(item, display)
    if context_reason:
        path.append(f"context_surface_item:{context_reason}:{item!r}")

    for label, text in (("item", item), ("display", display)):
        key = normalize_key(text)
        if key in SURFACE_NON_INGREDIENT_EXACT:
            path.append(f"non_ingredient_exact:{label}:{text!r}")
            return {
                "canonical_surface": text,
                "canonical_normalized": "",
                "canonical_shopping_item": "",
                "record_type": "non_ingredient",
                "notes": "explicit non-food recipe supply",
            }, path

    for label, text in (("item", item), ("display", display)):
        row = _manual_fndds_row(text)
        if row:
            path.append(f"manual_fndds:{label}:{text!r}->{row['fndds_code']}:{row['fndds_description']}")
            return row, path

    for label, text in (("item", item), ("display", display)):
        key = normalize_key(text)
        if not key:
            continue
        alias = SURFACE_ALIAS_REDIRECTS.get(key)
        if not alias:
            continue
        alias_key = normalize_key(alias)
        row = _best_surface_row(index.get(alias_key, []), alias_key)
        path.append(f"surface_alias:{label}:{text!r}->{alias!r}")
        if row:
            path.append(f"surface_alias_row:{alias!r}->{row.get('canonical_normalized', '')!r}")
            return row, path
        synthetic = _sr28_override_surface_row(alias_key, alias)
        if synthetic:
            path.append(f"surface_alias_sr28_override:{alias!r}->{synthetic['sr28_code']}")
            return synthetic, path

    for label, text in (("item", item), ("display", display)):
        key = normalize_key(text)
        if not key:
            continue
        row = _best_surface_row(index.get(key, []), key)
        if row:
            path.append(f"surface:{label}:{text!r}->{row.get('canonical_normalized', '')!r}")
            return row, path

    for label, text in (("item", item), ("display", display)):
        key = normalize_key(text)
        if not key:
            continue
        alias = SURFACE_ALIAS_REDIRECTS.get(key)
        if not alias:
            continue
        alias_key = normalize_key(alias)
        row = _best_surface_row(index.get(alias_key, []), alias_key)
        path.append(f"surface_alias:{label}:{text!r}->{alias!r}")
        if row:
            path.append(f"surface_alias_row:{alias!r}->{row.get('canonical_normalized', '')!r}")
            return row, path
        synthetic = _sr28_override_surface_row(alias_key, alias)
        if synthetic:
            path.append(f"surface_alias_sr28_override:{alias!r}->{synthetic['sr28_code']}")
            return synthetic, path

    for label, text in (("item", item), ("display", display)):
        key = normalize_key(text)
        if not key:
            continue
        synthetic = _sr28_override_surface_row(key, text)
        if synthetic:
            path.append(f"surface_sr28_override:{label}:{text!r}->{synthetic['sr28_code']}")
            return synthetic, path

    exact, regexes = _load_approved_rules()
    for label, text in (("item", item), ("display", display)):
        key = normalize_key(text)
        if not key:
            continue
        concept_key = exact.get(key)
        if concept_key:
            base = _concept_base(concept_key)
            row = _best_surface_row(index.get(normalize_key(base), []), normalize_key(base))
            path.append(f"approved_exact:{label}:{text!r}->{concept_key!r}")
            if row:
                path.append(f"approved_surface:{base!r}->{row.get('canonical_normalized', '')!r}")
                return row, path
            return {
                "canonical_surface": text,
                "canonical_normalized": base,
                "canonical_shopping_item": base,
                "record_type": "ingredient",
            }, path

    for label, text in (("item", item), ("display", display)):
        if not text:
            continue
        for regex, concept_key, rule_id in regexes:
            if not regex.search(text):
                continue
            expanded_concept_key = _expand_regex_concept_key(regex, concept_key, text)
            base = _concept_base(expanded_concept_key)
            row = _best_surface_row(index.get(normalize_key(base), []), normalize_key(base))
            path.append(f"approved_regex:{label}:{rule_id}:{text!r}->{expanded_concept_key!r}")
            if row:
                path.append(f"approved_surface:{base!r}->{row.get('canonical_normalized', '')!r}")
                return row, path
            return {
                "canonical_surface": text,
                "canonical_normalized": base,
                "canonical_shopping_item": base,
                "record_type": "ingredient",
            }, path

    path.append("nutrition_unknown:no_surface_or_approved_rule")
    return None, path


def _apply_surface_esha_override(
    row: dict[str, str],
    item: str,
    display: str,
    path: list[str],
) -> dict[str, str]:
    keys = {
        normalize_key(item),
        normalize_key(display),
        normalize_key(row.get("canonical_surface", "")),
        normalize_key(row.get("canonical_normalized", "")),
        normalize_key(row.get("canonical_shopping_item", "")),
    }
    display_tokens = set(normalize_key(display).split())
    if (
        keys & {"green bean", "green beans", "fresh green beans"}
        and display_tokens & {"can", "canned", "cans", "drained"}
    ):
        patched = dict(row)
        patched["canonical_shopping_item"] = "canned green beans"
        patched["product_query"] = "canned green beans"
        path.append("surface_context_shopping_override:'green beans'->'canned green beans'")
        row = patched
        keys = {
            normalize_key(item),
            normalize_key(display),
            normalize_key(row.get("canonical_surface", "")),
            normalize_key(row.get("canonical_normalized", "")),
            normalize_key(row.get("canonical_shopping_item", "")),
        }
    for key, (sr28_code, sr28_description, shopping_query, reason) in SURFACE_NO_ESHA_SR28_OVERRIDES.items():
        if key not in keys:
            continue
        patched = dict(row)
        if shopping_query:
            patched["canonical_shopping_item"] = shopping_query
            patched["product_query"] = shopping_query
        patched["nutrition_code"] = f"SR28:{sr28_code}"
        patched["nutrition_code_type"] = "sr28_reference_match"
        patched["nutrition_match_state"] = "sr28_match"
        patched["sr28_code"] = sr28_code
        patched["sr28_description"] = sr28_description
        patched["sr28_match_type"] = "surface_lab_no_esha_sr28_override"
        patched["fndds_code"] = ""
        patched["fndds_description"] = ""
        patched["fndds_match_type"] = ""
        patched["esha_code"] = ""
        patched["esha_description"] = ""
        patched["esha_match_type"] = "reviewed_no_esha_target:surface_lab"
        patched["unmatched_reason"] = reason
        path.append(f"surface_no_esha_sr28_override:{key!r}:{reason}")
        return patched
    for key, reason in SURFACE_NUTRITION_CLEARS.items():
        if key not in keys:
            continue
        patched = dict(row)
        for column in (
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
        ):
            patched[column] = ""
        patched["nutrition_match_state"] = "nutrition_unknown"
        patched["esha_match_type"] = "surface_lab_nutrition_clear"
        path.append(f"surface_nutrition_clear:{key!r}:{reason}")
        return patched
    for key, reason in SURFACE_ESHA_CLEARS.items():
        if key not in keys:
            continue
        path.append(f"surface_esha_clear:{key!r}:{reason}")
        sr28_override = SURFACE_SR28_NUTRITION_OVERRIDES.get(key)
        if not (row.get("esha_code") or "").strip() and not (row.get("esha_description") or "").strip():
            patched = dict(row)
            patched["esha_match_type"] = "surface_lab_clear"
            if sr28_override:
                sr28_code, sr28_description = sr28_override
                patched["nutrition_code"] = f"SR28:{sr28_code}"
                patched["nutrition_code_type"] = "sr28_reference_match"
                patched["nutrition_match_state"] = "sr28_match"
                patched["sr28_code"] = sr28_code
                patched["sr28_description"] = sr28_description
                patched["sr28_match_type"] = "surface_lab_clear_override"
            return patched
        patched = dict(row)
        patched["esha_code"] = ""
        patched["esha_description"] = ""
        patched["esha_match_type"] = "surface_lab_clear"
        if sr28_override:
            sr28_code, sr28_description = sr28_override
            patched["nutrition_code"] = f"SR28:{sr28_code}"
            patched["nutrition_code_type"] = "sr28_reference_match"
            patched["nutrition_match_state"] = "sr28_match"
            patched["sr28_code"] = sr28_code
            patched["sr28_description"] = sr28_description
            patched["sr28_match_type"] = "surface_lab_clear_override"
        return patched
    for key, canonical in SURFACE_CANONICAL_OVERRIDES.items():
        if key not in keys:
            continue
        patched = dict(row)
        patched["canonical_normalized"] = canonical
        patched["canonical_shopping_item"] = canonical
        path.append(f"surface_canonical_override:{key!r}->{canonical!r}")
        row = patched
        break
    for key, shopping_query in SURFACE_SHOPPING_OVERRIDES.items():
        if key not in keys:
            continue
        if normalize_key(row.get("canonical_shopping_item", "")) == "canned green beans" and key in {"green bean", "green beans"}:
            continue
        patched = dict(row)
        patched["canonical_shopping_item"] = shopping_query
        patched["product_query"] = shopping_query
        path.append(f"surface_shopping_override:{key!r}->{shopping_query!r}")
        row = patched
        break
    for key, (code, description) in SURFACE_ESHA_OVERRIDES.items():
        if key not in keys:
            continue
        if (
            (row.get("esha_code") or "").strip() == code
            and (row.get("esha_description") or "").strip() == description
            and key not in SURFACE_ESHA_NUTRITION_PRIORITY
            and key not in SURFACE_SR28_NUTRITION_OVERRIDES
        ):
            return row
        patched = dict(row)
        patched["esha_code"] = code
        patched["esha_description"] = description
        patched["esha_match_type"] = "surface_lab_override"
        if key in SURFACE_ESHA_NUTRITION_PRIORITY:
            patched["nutrition_code"] = f"ESHA:{code}"
            patched["nutrition_code_type"] = "esha_label_median"
            patched["nutrition_match_state"] = "esha_match"
        if key in SURFACE_SR28_NUTRITION_OVERRIDES:
            sr28_code, sr28_description = SURFACE_SR28_NUTRITION_OVERRIDES[key]
            patched["nutrition_code"] = f"SR28:{sr28_code}"
            patched["nutrition_code_type"] = "sr28_reference_match"
            patched["nutrition_match_state"] = "sr28_match"
            patched["sr28_code"] = sr28_code
            patched["sr28_description"] = sr28_description
            patched["sr28_match_type"] = "surface_lab_override"
        path.append(f"surface_esha_override:{key!r}->{code}:{description}")
        return patched
    return row


def _nutrition_from_row(row: dict[str, str], grams: float | None) -> tuple[NutritionEstimate | None, str, NutritionState]:
    if grams is None or grams <= 0:
        return None, "missing_grams", NutritionState.NUTRITION_UNKNOWN

    sr28 = (row.get("sr28_code") or "").strip()
    nutrition_state = (row.get("nutrition_match_state") or "").strip()
    nutrition_code_type = (row.get("nutrition_code_type") or "").strip()
    if sr28 and (nutrition_state == "sr28_match" or nutrition_code_type == "sr28_reference_match"):
        sr28_row = nutrition_for_grams(sr28, grams)
        if sr28_row:
            return NutritionEstimate(
                kcal=sr28_row.get("kcal", 0.0),
                protein_g=sr28_row.get("protein", 0.0),
                fat_g=sr28_row.get("fat", 0.0),
                carbs_g=sr28_row.get("carbs", 0.0),
            ), "sr28_direct", NutritionState.EXACT_USDA_ANCHOR

    fndds = (row.get("fndds_code") or "").strip()
    if fndds and (nutrition_state == "fndds_match" or nutrition_code_type == "fndds_reference_match" or not sr28):
        fndds_row = _load_fndds_per_100g().get(fndds)
        if fndds_row:
            return _scale(fndds_row, grams), "fndds_direct", NutritionState.REVIEWED_LOCAL_LABEL_ANCHOR

    esha_code = (row.get("esha_code") or "").strip()
    if esha_code:
        esha = nutrition_for_esha(esha_code)
        if esha and esha.get("tier") == "A_label_median" and esha.get("kcal") is not None:
            return _scale(esha, grams), "esha_tier_a_label_median", NutritionState.REVIEWED_LOCAL_LABEL_ANCHOR
        if esha and esha.get("tier") == "B_sr28_fndds_proxy" and esha.get("sr28_proxy"):
            proxy = sr28_per_100g(esha["sr28_proxy"])
            if proxy:
                return _scale(proxy, grams), "esha_sr28_proxy", NutritionState.REVIEWED_PROXY

    return None, "nutrition_unknown", NutritionState.NUTRITION_UNKNOWN


def calculate_lab(display: str, item: str = "", grams: float | None = None) -> LabResolution:
    row, path = _resolve_surface(item, display)
    if not row:
        return LabResolution(
            input_item=item,
            input_display=display,
            canonical_name="",
            shopping_canonical="",
            sr28_fdc_id="",
            fndds_code="",
            esha_code="",
            esha_description="",
            nutrition_state=NutritionState.NUTRITION_UNKNOWN.value,
            shopping_state=ShoppingState.SHOPPING_GAP.value,
            grams=grams,
            nutrition_source="nutrition_unknown",
            nutrition=None,
            products=[],
            rejected_products=[],
            path=path,
            notes="",
        )

    if (row.get("record_type") or "") == "non_ingredient":
        return LabResolution(
            input_item=item,
            input_display=display,
            canonical_name="",
            shopping_canonical="",
            sr28_fdc_id="",
            fndds_code="",
            esha_code="",
            esha_description="",
            nutrition_state=NutritionState.NON_FOOD.value,
            shopping_state=ShoppingState.NON_FOOD.value,
            grams=grams,
            nutrition_source="non_ingredient_surface",
            nutrition=None,
            products=[],
            rejected_products=[],
            path=path,
            notes=row.get("notes", ""),
        )

    row = _apply_surface_esha_override(row, item, display, path)
    nutrition, nutrition_source, nutrition_state = _nutrition_from_row(row, grams)
    sr28 = (row.get("sr28_code") or "").strip()
    fndds = (row.get("fndds_code") or "").strip()
    esha_code = (row.get("esha_code") or "").strip()
    shopping_query = (row.get("canonical_shopping_item") or row.get("canonical_normalized") or "").strip()
    nutrition_canonical = (row.get("canonical_normalized") or "").strip()
    prefer_shopping_query = bool(
        shopping_query
        and normalize_key(shopping_query) != normalize_key(nutrition_canonical)
    )
    raw_products: list[LabProduct] = []
    product_path = "shopping_query_override" if prefer_shopping_query else "product_code_tags"
    if esha_code and not prefer_shopping_query:
        reviewed_products = _esha_pack_products(esha_code)
        if reviewed_products and reviewed_products[0].source == "esha_reviewed_lookup":
            raw_products = reviewed_products
            product_path = reviewed_products[0].source
    if shopping_query:
        retail_products = _retail_surface_products(shopping_query)
        if retail_products and not raw_products:
            raw_products = retail_products
            product_path = "retail_surface_bridge"
    if not raw_products and esha_code and not prefer_shopping_query:
        raw_products = _esha_pack_products(esha_code)
        if raw_products:
            product_path = raw_products[0].source
    if not raw_products and not prefer_shopping_query:
        raw_products = [
            LabProduct(
                gtin_upc=p.gtin_upc,
                description=p.description,
                brand_name=p.brand_name,
                category=p.branded_food_category,
                source=p.source,
            )
            for p in match_products(
                sr28 if nutrition_source == "sr28_direct" else "",
                fndds,
                "",
                canonical=shopping_query,
            )[:25]
        ]
    products, rejected_products = _review_products(raw_products, shopping_query)
    if not products:
        if normalize_key(shopping_query) not in TEXT_FALLBACK_BLOCKLIST:
            search_results = [
                LabProduct(
                    gtin_upc=p.gtin_upc,
                    description=p.description,
                    brand_name=p.brand_name,
                    category=p.branded_food_category,
                    source=p.source,
                )
                for p in search_products(shopping_query, limit=25, canonical=shopping_query)
            ]
            if search_results:
                product_path = "fts_search"
                products, rejected_products = _review_products(search_results, shopping_query)
    if not products and shopping_query:
        # Step D (Part 6): audit-path lookup — pull candidate UPCs from
        # product_audit_classification by the canonical's expected_canonical_path
        # (canonical_retail_bridge). Hydrate via master_products. Solves cache-poor
        # canonicals where the existing chain only finds wrong-form candidates
        # (e.g. macaroni cache returns only salads/dinners; audit knows where
        # plain dry pasta lives).
        audit_results = _audit_path_products(shopping_query)
        if audit_results:
            product_path = "audit_path_lookup"
            raw_products = list(audit_results)
            products, rejected_products = _review_products(audit_results, shopping_query)
    if not products and shopping_query:
        api_cache_results = _load_api_cache_products().get(normalize_key(shopping_query), [])
        if api_cache_results:
            product_path = "api_cache_exact"
            # api_cache fallback also counts as a retail-matching attempt — track
            # raw candidates so the path logs accepted/rejected even when
            # _retail_surface_products / match_products both returned empty.
            raw_products = list(api_cache_results)
            products, rejected_products = _review_products(api_cache_results, shopping_query)
    # Step A (Part 4): always log the retail-matching outcome when ANY source
    # was tried, even if all candidates rejected. This is what was missing for
    # canonicals like macaroni: the api_cache fallback returned products, all
    # got combo-rejected, but the public path showed nothing — making it look
    # like retail matching never ran.
    if raw_products or products or rejected_products:
        path.append(f"shopping_products:{product_path}:accepted={len(products)} rejected={len(rejected_products)}")
    shopping_state = (
        ShoppingState.SHOPPING_CANDIDATES_STRONG
        if len(products) >= 3
        else ShoppingState.SHOPPING_CANDIDATES_WEAK
        if products
        else ShoppingState.SHOPPING_GAP
    )
    taxonomy_meta = lookup_taxonomy(
        item=item,
        display=display,
        canonical_name=nutrition_canonical,
        shopping_canonical=shopping_query,
        fndds_code=fndds,
        sr28_fdc_id=sr28,
        esha_code=esha_code,
    )
    if taxonomy_meta.htc_code:
        path.append(
            f"taxonomy_lookup:{taxonomy_meta.taxonomy_source}:"
            f"{taxonomy_meta.htc_code}:{taxonomy_meta.retail_leaf_path}"
        )
    return LabResolution(
        input_item=item,
        input_display=display,
        canonical_name=(row.get("canonical_normalized") or "").strip(),
        shopping_canonical=(row.get("canonical_shopping_item") or row.get("canonical_normalized") or "").strip(),
        sr28_fdc_id=sr28 if nutrition_source == "sr28_direct" else "",
        fndds_code=fndds,
        esha_code=esha_code,
        esha_description=(row.get("esha_description") or "").strip(),
        nutrition_state=nutrition_state.value,
        shopping_state=shopping_state.value,
        grams=grams,
        nutrition_source=nutrition_source,
        nutrition=nutrition,
        products=products,
        rejected_products=rejected_products,
        path=path,
        notes=row.get("notes", ""),
        **metadata_kwargs(taxonomy_meta),
    )


def _current_calculator_result(display: str, item: str, grams: float | None) -> dict:
    from calculator import calculate_line

    current = calculate_line(display=display, item=item, grams_hint=grams)
    return {
        "canonical_name": current.canonical_name,
        "sr28_fdc_id": current.sr28_fdc_id,
        "fndds_code": current.fndds_code,
        "esha_code": current.esha_code,
        "nutrition_state": current.nutrition_state.value,
        "shopping_state": current.shopping_state.value,
        "grams": current.grams,
        "nutrition": asdict(current.nutrition) if current.nutrition else None,
        "product_count": len(current.products or []),
        "canonical_path": current.canonical_path,
        "retail_leaf_path": current.retail_leaf_path,
        "htc_code": current.htc_code,
        "taxonomy_source": current.taxonomy_source,
        "path": current.path,
    }


def _demo_cases() -> list[tuple[str, str, float]]:
    return [
        ("2 cups half-and-half", "half-and-half", 473.0),
        ("1 tsp accent seasoning", "accent seasoning", 4.0),
        ("250 g besan (chickpea flour)", "besan", 250.0),
        ("1 cup garbanzo flour", "garbanzo flour", 92.0),
        ("1 cup rice chex", "rice chex", 28.0),
        ("1 cup butter peas", "butter peas", 100.0),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Experimental read-only calculator for canonical surface work.")
    parser.add_argument("--display", default="")
    parser.add_argument("--item", default="")
    parser.add_argument("--grams", type=float)
    parser.add_argument("--surface-csv", type=Path, help="canonical surface CSV to use for resolution")
    parser.add_argument("--product-esha-map", type=Path, help="product_to_best_esha full-map CSV to use for ESHA product candidates")
    parser.add_argument("--retail-surface-bridge", type=Path, help="retail cache rows mapped to canonical surface rows")
    parser.add_argument("--compare-current", action="store_true")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    configure_data_sources(
        surface_csv=args.surface_csv,
        product_esha_map_csv=args.product_esha_map,
        retail_surface_bridge_csv=args.retail_surface_bridge,
    )

    if args.demo:
        rows = []
        for display, item, grams in _demo_cases():
            lab = calculate_lab(display=display, item=item, grams=grams)
            rows.append(asdict(lab))
        print(json.dumps(rows, indent=2))
        return

    lab = calculate_lab(display=args.display, item=args.item, grams=args.grams)
    out = {"lab": asdict(lab)}
    if args.compare_current:
        out["current"] = _current_calculator_result(args.display, args.item, args.grams)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
