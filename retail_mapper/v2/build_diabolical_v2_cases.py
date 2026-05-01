#!/usr/bin/env python3
"""Build the v2 diabolical taxonomy gold set — real-world hard SKUs.

Categories covered (per the user's brief):
  - hybrid beverages (oat milk eggnog, probiotic seltzer, kombucha, drinks-as-shots)
  - dry mixes vs RTD beverages (Crystal Light, hot cocoa, electrolyte powders)
  - compound meals (Newman's skillet kits, Banquet TV dinners, Stouffer's, frozen dinners)
  - pizza variations (every crust + topping: cauliflower, stuffed, deep dish, gluten-free, french bread)
  - trail mix variations (tropical, energy, sweet & salty)
  - retail meat cuts (boneless/bone-in, ground %, chuck/loin/etc.)
  - flavored milks (real flavor vs whole compound noun)
  - milk chocolate vs chocolate milk (subtle word-order ambiguity)
  - vegetables: frozen vs canned vs fresh vs seasoned vs sauced
  - multi-flavor candy (Skittles assorted)
  - spice blends / rubs / combos (Montreal steak, taco, salt+pepper, pumpkin pie)
  - named ice cream flavors (Chunky Monkey: variant not flavor)
  - compound condiments (horseradish aioli, sriracha mayo)
  - multigrain breads (12-grain / 15-grain)
  - fruit/veggie leather snacks (dehydrated, NOT fresh fruit)
  - snack pack combos (apples + caramel, cheese + crackers)

Each case outputs the same JSONL shape llm_taxonomy_diabolical_cases.jsonl
uses, with canonical_path/canonical_label/tree_paths derived from the
record (using the same helpers the scorer uses), so gold is self-consistent.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"

# Import the cleanup module to reuse derivation helpers.
sp = importlib.util.spec_from_file_location("ltc", V2 / "llm_taxonomy_cleanup.py")
ltc = importlib.util.module_from_spec(sp)
sys.modules["ltc"] = ltc
sp.loader.exec_module(ltc)


def case(
    name: str,
    title: str,
    bfc: str,
    *,
    retail_type: str = "single",
    category_path: str,
    product_identity: str,
    variant: list[str] | None = None,
    flavor: list[str] | None = None,
    form_texture_cut: list[str] | None = None,
    processing_storage: list[str] | None = None,
    claims: list[str] | None = None,
    components: list[dict] | None = None,
    confidence: float = 0.92,
    mint_required: bool | None = None,
    review_flags: list[str] | None = None,
    rationale: str = "",
    notes: str = "",
) -> dict:
    """Build one full gold case from a compact spec.

    Auto-derives canonical_path, canonical_label, tree_paths via cleanup helpers.
    Auto-derives mint_required from the canonical hint table when not given.
    """
    fdc_id = "diabolical_v2_" + name
    record = {
        "fdc_id": fdc_id,
        "retail_type": retail_type,
        "category_path": category_path,
        "product_identity": product_identity,
        "variant": variant or [],
        "flavor": flavor or [],
        "form_texture_cut": form_texture_cut or [],
        "processing_storage": processing_storage or [],
        "claims": claims or [],
        "components": components or [],
        "confidence": confidence,
        "review_flags": review_flags or [],
        "rationale": rationale,
    }
    record["canonical_path"] = ltc.build_canonical_path(category_path, product_identity)
    record["canonical_label"] = ltc.build_canonical_label(product_identity, record)

    # mint_required default from the same logic the normalizer uses
    if mint_required is None:
        if product_identity in ltc.MINT_NOT_REQUIRED_IDENTITIES:
            mint_required = False
        elif product_identity in ltc.CANONICAL_CATEGORY_HINTS:
            mint_required = True
        else:
            mint_required = True
    record["mint_required"] = mint_required

    record["tree_paths"] = ltc.build_tree_paths(record)

    # Validator-required: ensure components have all FACET_GROUP keys present
    full_components = []
    for c in record["components"]:
        cc = {
            "identity": c.get("identity", ""),
            "role": c.get("role", "unknown"),
            "variant": c.get("variant", []) or [],
            "flavor": c.get("flavor", []) or [],
            "form_texture_cut": c.get("form_texture_cut", []) or [],
            "processing_storage": c.get("processing_storage", []) or [],
            "claims": c.get("claims", []) or [],
        }
        full_components.append(cc)
    record["components"] = full_components

    return {
        "name": name,
        "source": {"fdc_id": fdc_id, "title": title, "branded_food_category": bfc},
        "expected": record,
        "notes": notes,
    }


def comp(identity: str, role: str = "ingredient", **facets) -> dict:
    """Compact component constructor."""
    return {"identity": identity, "role": role, **facets}


# --------------------------------------------------------------------------
# CATEGORY A: HYBRID / WEIRD BEVERAGES
# --------------------------------------------------------------------------
A_BEVERAGES = [
    case(
        "oat_milk_eggnog",
        "OAT MILK EGG NOG, ORIGINAL",
        "Plant Based Beverages",
        category_path="Beverage > Eggnog",
        product_identity="Eggnog",
        variant=["oat_milk"],
        claims=["dairy_free", "plant_based"],
        rationale="Plant-based eggnog substitute; oat_milk is the SKU variant.",
        notes="Common diabolical: dairy substitute version of a dairy product.",
    ),
    case(
        "almond_milk_eggnog",
        "ALMOND BREEZE ALMONDMILK NOG, HOLIDAY ALMONDMILK NOG",
        "Plant Based Beverages",
        category_path="Beverage > Eggnog",
        product_identity="Eggnog",
        variant=["almond_milk"],
        claims=["dairy_free", "plant_based"],
        rationale="Almond milk version of eggnog.",
    ),
    case(
        "blueberry_probiotic_seltzer",
        "BLUEBERRY PROBIOTIC SPARKLING WATER",
        "Sparkling Water",
        category_path="Beverage > Sparkling Water",
        product_identity="Sparkling Water",
        flavor=["blueberry"],
        claims=["probiotic"],
        rationale="Sparkling water with blueberry flavor and probiotic claim.",
        notes="Probiotic should be a CLAIM, not a variant or flavor.",
    ),
    case(
        "pineapple_turmeric_kombucha",
        "PINEAPPLE TURMERIC KOMBUCHA",
        "Functional Beverages",
        category_path="Beverage > Kombucha",
        product_identity="Kombucha",
        flavor=["pineapple", "turmeric"],
        claims=["probiotic"],
        rationale="Kombucha is its own identity; turmeric+pineapple are flavors.",
    ),
    case(
        "apple_cider_vinegar_drink_elderberry",
        "SPARKLING APPLE CIDER VINEGAR DRINK WITH ELDERBERRY",
        "Functional Beverages",
        category_path="Beverage > Functional Drinks",
        product_identity="Apple Cider Vinegar Drink",
        flavor=["elderberry"],
        rationale="ACV drink with elderberry flavor.",
    ),
    case(
        "chocolate_oat_milk_cold_brew",
        "CHOCOLATE OAT MILK COLD BREW COFFEE",
        "Coffee Drinks",
        category_path="Beverage > Coffee",
        product_identity="Cold Brew Coffee",
        variant=["oat_milk"],
        flavor=["chocolate"],
        claims=["dairy_free", "plant_based"],
        rationale="RTD cold brew coffee with oat milk and chocolate flavor.",
    ),
    case(
        "watermelon_mint_coconut_water",
        "WATERMELON MINT COCONUT WATER",
        "Plant Based Water",
        category_path="Beverage > Coconut Water",
        product_identity="Coconut Water",
        flavor=["watermelon", "mint"],
        rationale="Coconut water with watermelon+mint flavor accents.",
    ),
    case(
        "beet_ginger_lemon_shot",
        "BEET ROOT GINGER LEMON WELLNESS SHOT",
        "Wellness Drinks",
        category_path="Beverage > Wellness Shots",
        product_identity="Wellness Shot",
        flavor=["beet", "ginger", "lemon"],
        form_texture_cut=["shot"],
        rationale="Concentrated wellness shot, not a regular drink size.",
    ),
    case(
        "mushroom_adaptogen_latte_dry_mix",
        "MUSHROOM ADAPTOGEN LATTE DRY MIX, MOCHA",
        "Coffee Mixes",
        category_path="Pantry > Drink Mixes",
        product_identity="Latte Mix",
        variant=["mushroom_adaptogen"],
        flavor=["mocha"],
        form_texture_cut=["powder"],
        rationale="DRY MIX form of a latte; identity must reflect powder form.",
        notes="Critical: DRY MIX is not a beverage; goes in Pantry > Drink Mixes.",
    ),
    case(
        "crystal_light_lemonade_dry_mix",
        "CRYSTAL LIGHT LEMONADE DRINK MIX, LEMONADE",
        "Drink Mixes",
        category_path="Pantry > Drink Mixes",
        product_identity="Lemonade Mix",
        form_texture_cut=["powder"],
        claims=["low_calorie", "sugar_free"],
        rationale="Powdered drink mix, not RTD lemonade.",
    ),
    case(
        "hot_cocoa_dry_mix",
        "HOT COCOA MIX, MILK CHOCOLATE",
        "Hot Cocoa",
        category_path="Pantry > Drink Mixes",
        product_identity="Hot Cocoa Mix",
        flavor=["milk_chocolate"],
        form_texture_cut=["powder"],
        rationale="Powdered hot cocoa mix.",
    ),
    case(
        "gatorade_powder",
        "GATORADE THIRST QUENCHER POWDER, ORANGE",
        "Sports Drinks",
        category_path="Pantry > Drink Mixes",
        product_identity="Sports Drink Mix",
        flavor=["orange"],
        form_texture_cut=["powder"],
        rationale="Powdered sports drink mix vs RTD bottled Gatorade.",
    ),
    case(
        "kefir_strawberry_probiotic",
        "STRAWBERRY KEFIR DRINKABLE PROBIOTIC",
        "Yogurt & Kefir",
        category_path="Dairy > Kefir",
        product_identity="Kefir",
        flavor=["strawberry"],
        claims=["probiotic"],
        rationale="Kefir is its own identity; strawberry is flavor; probiotic claim.",
    ),
    case(
        "matcha_protein_shake",
        "MATCHA GREEN TEA PROTEIN SHAKE, MATCHA",
        "Protein Drinks",
        category_path="Beverage > Protein Drinks",
        product_identity="Protein Shake",
        flavor=["matcha"],
        claims=["high_protein"],
        rationale="RTD protein shake with matcha flavor.",
    ),
]

# --------------------------------------------------------------------------
# CATEGORY B: MILK CHOCOLATE vs CHOCOLATE MILK (word-order trip)
# --------------------------------------------------------------------------
B_CHOCOLATE_AMBIGUITY = [
    case(
        "hersheys_milk_chocolate_bar",
        "HERSHEY'S MILK CHOCOLATE CANDY BAR",
        "Chocolate Candy",
        category_path="Snack > Chocolate Candy",
        product_identity="Chocolate Bar",
        variant=["milk_chocolate"],
        rationale="Milk Chocolate Bar: 'milk_chocolate' is a chocolate type variant, NOT a chocolate-flavored milk.",
        notes="Trip-up: do not classify as Chocolate Milk.",
    ),
    case(
        "nesquik_chocolate_milk_powder",
        "NESQUIK CHOCOLATE MILK POWDER",
        "Drink Mixes",
        category_path="Pantry > Drink Mixes",
        product_identity="Chocolate Milk Mix",
        form_texture_cut=["powder"],
        rationale="Powder you add to milk to make chocolate milk; NOT chocolate-bar milk.",
    ),
    case(
        "hersheys_chocolate_milk_rtd",
        "HERSHEY'S 2% CHOCOLATE MILK",
        "Flavored Milk",
        category_path="Dairy > Flavored Milk",
        product_identity="Chocolate Milk",
        variant=["2_percent"],
        rationale="Compound identity Chocolate Milk; word order matters.",
    ),
    case(
        "dark_chocolate_almond_milk",
        "DARK CHOCOLATE ALMONDMILK",
        "Plant Based Beverages",
        category_path="Beverage > Plant Milk",
        product_identity="Almond Milk",
        flavor=["dark_chocolate"],
        claims=["dairy_free", "plant_based"],
        rationale="Almond Milk with dark_chocolate flavor; identity is the plant milk.",
    ),
    case(
        "ghirardelli_dark_chocolate_squares",
        "GHIRARDELLI DARK CHOCOLATE INTENSE DARK SQUARES",
        "Chocolate Candy",
        category_path="Snack > Chocolate Candy",
        product_identity="Chocolate Squares",
        variant=["dark_chocolate"],
        rationale="Dark Chocolate Squares — variant, not flavor.",
    ),
    case(
        "white_chocolate_macadamia_cookies",
        "WHITE CHOCOLATE MACADAMIA NUT COOKIES",
        "Cookies & Biscuits",
        category_path="Snack > Cookies",
        product_identity="Cookies",
        flavor=["white_chocolate", "macadamia_nut"],
        rationale="Cookies with two flavor accents; white_chocolate stays a flavor here, not the identity.",
    ),
]

# --------------------------------------------------------------------------
# CATEGORY C: PIZZA VARIATIONS
# --------------------------------------------------------------------------
C_PIZZA = [
    case(
        "cauliflower_crust_pepperoni_pizza",
        "CAULIFLOWER CRUST PEPPERONI PIZZA",
        "Frozen Pizza",
        category_path="Frozen > Pizza",
        product_identity="Pizza",
        variant=["pepperoni"],
        form_texture_cut=["cauliflower_crust"],
        processing_storage=["frozen"],
        claims=["gluten_free"],
        rationale="Crust type goes to form_texture_cut; topping is variant.",
    ),
    case(
        "thin_crust_four_cheese_pizza",
        "THIN CRUST FOUR CHEESE PIZZA",
        "Frozen Pizza",
        category_path="Frozen > Pizza",
        product_identity="Pizza",
        variant=["four_cheese"],
        form_texture_cut=["thin_crust"],
        processing_storage=["frozen"],
        rationale="Variant captures the topping/style; crust is form.",
    ),
    case(
        "stuffed_crust_supreme_pizza",
        "STUFFED CRUST SUPREME PIZZA",
        "Frozen Pizza",
        category_path="Frozen > Pizza",
        product_identity="Pizza",
        variant=["supreme"],
        form_texture_cut=["stuffed_crust"],
        processing_storage=["frozen"],
        rationale="Stuffed crust is a form; supreme is the variant.",
    ),
    case(
        "gluten_free_margherita_pizza",
        "GLUTEN FREE MARGHERITA PIZZA",
        "Frozen Pizza",
        category_path="Frozen > Pizza",
        product_identity="Pizza",
        variant=["margherita"],
        processing_storage=["frozen"],
        claims=["gluten_free"],
        rationale="Margherita variant; gluten_free claim from title.",
    ),
    case(
        "detroit_style_deep_dish_pepperoni_pizza",
        "DETROIT STYLE DEEP DISH PEPPERONI PIZZA",
        "Frozen Pizza",
        category_path="Frozen > Pizza",
        product_identity="Pizza",
        variant=["pepperoni"],
        form_texture_cut=["detroit_style", "deep_dish"],
        processing_storage=["frozen"],
        rationale="Detroit style and deep_dish are both form descriptors.",
    ),
    case(
        "french_bread_pepperoni_pizza",
        "FRENCH BREAD PEPPERONI PIZZA",
        "Frozen Pizza",
        category_path="Frozen > Pizza",
        product_identity="French Bread Pizza",
        variant=["pepperoni"],
        processing_storage=["frozen"],
        rationale="French Bread Pizza is its own retail identity, not regular pizza.",
        mint_required=True,
    ),
    case(
        "cauliflower_crust_bbq_chicken_pizza",
        "CAULIFLOWER CRUST BBQ CHICKEN PIZZA",
        "Frozen Pizza",
        category_path="Frozen > Pizza",
        product_identity="Pizza",
        variant=["bbq_chicken"],
        form_texture_cut=["cauliflower_crust"],
        processing_storage=["frozen"],
        claims=["gluten_free"],
        rationale="BBQ Chicken topping; cauliflower crust form.",
    ),
    case(
        "personal_pepperoni_pizza",
        "PERSONAL SIZE PEPPERONI PIZZA",
        "Frozen Pizza",
        category_path="Frozen > Pizza",
        product_identity="Pizza",
        variant=["pepperoni"],
        form_texture_cut=["personal_size"],
        processing_storage=["frozen"],
        rationale="Personal size form descriptor.",
    ),
    case(
        "hot_pocket_pepperoni",
        "HOT POCKETS PEPPERONI PIZZA STUFFED SANDWICH",
        "Frozen Sandwiches",
        category_path="Frozen > Stuffed Sandwiches",
        product_identity="Pizza Pocket",
        variant=["pepperoni"],
        processing_storage=["frozen"],
        rationale="Stuffed-pizza-pocket is its own retail identity, not a pizza.",
        mint_required=True,
        notes="The model often misclassifies as Pizza or Sandwich; gold says Pizza Pocket.",
    ),
    case(
        "frozen_garlic_bread_pizza",
        "GARLIC BREAD PIZZA FROZEN",
        "Frozen Pizza",
        category_path="Frozen > Pizza",
        product_identity="French Bread Pizza",
        variant=["garlic_bread"],
        processing_storage=["frozen"],
        rationale="Garlic bread carrier; treated as French Bread Pizza family.",
    ),
]

# --------------------------------------------------------------------------
# CATEGORY D: COMPOUND MEALS / TV DINNERS / SKILLET KITS
# --------------------------------------------------------------------------
D_MEALS = [
    case(
        "newmans_skillet_meal_chicken_alfredo",
        "NEWMAN'S OWN COMPLETE SKILLET MEAL FOR TWO, CHICKEN FETTUCCINI ALFREDO",
        "Frozen Dinners & Entrees",
        retail_type="meal_kit",
        category_path="Frozen > Skillet Meals",
        product_identity="Skillet Meal",
        variant=["chicken_fettuccini_alfredo"],
        processing_storage=["frozen"],
        components=[
            comp("Chicken", role="protein"),
            comp("Fettuccini Pasta", role="base"),
            comp("Alfredo Sauce", role="sauce"),
        ],
        rationale="Skillet meal kit, not a sauce. Current pipeline incorrectly maps this to Alfredo Sauce.",
        mint_required=True,
        notes="USER-PROVIDED. Real existing fdc 2009076. Critical compound-meal trip.",
    ),
    case(
        "banquet_meatloaf_mashed_potatoes_dinner",
        "BANQUET MEATLOAF AND MASHED POTATOES DINNER",
        "Frozen Dinners & Entrees",
        retail_type="composite_dish",
        category_path="Frozen > TV Dinners",
        product_identity="TV Dinner",
        variant=["meatloaf_mashed_potatoes"],
        processing_storage=["frozen"],
        components=[
            comp("Meatloaf", role="protein"),
            comp("Mashed Potatoes", role="side"),
        ],
        rationale="Frozen TV dinner with named compartments.",
        mint_required=True,
    ),
    case(
        "stouffers_lasagna_meat_sauce",
        "STOUFFER'S LASAGNA WITH MEAT SAUCE",
        "Frozen Dinners & Entrees",
        retail_type="composite_dish",
        category_path="Meal > Pasta Dishes",
        product_identity="Lasagna",
        variant=["meat_sauce"],
        processing_storage=["frozen"],
        rationale="Lasagna is its own dish; meat_sauce variant.",
    ),
    case(
        "marie_callenders_chicken_pot_pie",
        "MARIE CALLENDER'S CHICKEN POT PIE",
        "Frozen Dinners & Entrees",
        retail_type="single",
        category_path="Frozen > Pot Pies",
        product_identity="Pot Pie",
        variant=["chicken"],
        processing_storage=["frozen"],
        rationale="Pot pie is its own identity; chicken is the variant.",
        mint_required=True,
    ),
    case(
        "hungryman_salisbury_steak_dinner",
        "HUNGRY-MAN SALISBURY STEAK DINNER",
        "Frozen Dinners & Entrees",
        retail_type="composite_dish",
        category_path="Frozen > TV Dinners",
        product_identity="TV Dinner",
        variant=["salisbury_steak"],
        processing_storage=["frozen"],
        components=[
            comp("Salisbury Steak", role="protein"),
            comp("Mashed Potatoes", role="side"),
            comp("Brown Gravy", role="sauce"),
        ],
        rationale="Multi-compartment frozen dinner.",
        mint_required=True,
    ),
    case(
        "lean_cuisine_garlic_beef",
        "LEAN CUISINE GARLIC BEEF AND BROCCOLI",
        "Frozen Dinners & Entrees",
        retail_type="single",
        category_path="Frozen > Single Entrees",
        product_identity="Frozen Entree",
        variant=["garlic_beef_and_broccoli"],
        processing_storage=["frozen"],
        claims=["low_calorie"],
        rationale="Single-serve frozen entree; lean_cuisine implies low_calorie.",
        mint_required=True,
    ),
    case(
        "amy_mac_and_cheese_bowl",
        "AMY'S MAC AND CHEESE BOWL ORGANIC",
        "Frozen Dinners & Entrees",
        retail_type="single",
        category_path="Frozen > Single Entrees",
        product_identity="Mac and Cheese",
        processing_storage=["frozen"],
        claims=["organic"],
        rationale="Mac and Cheese is its own identity; organic claim; bowl is packaging not facet.",
    ),
    case(
        "kids_meal_mac_cheese_nuggets_apples",
        "KIDS MEAL MAC AND CHEESE WITH CHICKEN NUGGETS AND APPLES",
        "Frozen Kids Meals",
        retail_type="combination_meal",
        category_path="Frozen > Kids Meals",
        product_identity="Kids Meal",
        processing_storage=["frozen"],
        components=[
            comp("Mac and Cheese", role="main"),
            comp("Chicken Nuggets", role="protein"),
            comp("Apples", role="fruit"),
        ],
        rationale="Multi-component kids meal; combination_meal type.",
        mint_required=True,
    ),
    case(
        "pf_changs_beef_with_broccoli_frozen",
        "P.F. CHANG'S HOME MENU BEEF WITH BROCCOLI FROZEN MEAL",
        "Frozen Dinners & Entrees",
        retail_type="single",
        category_path="Frozen > Asian Meals",
        product_identity="Frozen Entree",
        variant=["beef_with_broccoli"],
        processing_storage=["frozen"],
        rationale="Asian-style frozen entree with named dish variant.",
        mint_required=True,
    ),
    case(
        "stouffers_french_bread_pizza_pepperoni",
        "STOUFFER'S FRENCH BREAD PIZZA, PEPPERONI",
        "Frozen Pizza",
        category_path="Frozen > Pizza",
        product_identity="French Bread Pizza",
        variant=["pepperoni"],
        processing_storage=["frozen"],
        rationale="French bread pizza is a separate retail node from regular pizza.",
        mint_required=True,
    ),
]

# --------------------------------------------------------------------------
# CATEGORY E: TRAIL MIX VARIATIONS
# --------------------------------------------------------------------------
E_TRAIL_MIX = [
    case(
        "tropical_trail_mix",
        "TROPICAL TRAIL MIX, MANGO PINEAPPLE COCONUT ALMONDS",
        "Trail Mix & Snack Mixes",
        category_path="Snack > Trail Mix",
        product_identity="Trail Mix",
        variant=["tropical"],
        rationale="Trail Mix is the identity; tropical is the standard variant naming.",
        mint_required=True,
    ),
    case(
        "energy_trail_mix_pb_raisin_mm",
        "ENERGY TRAIL MIX, PEANUTS RAISINS M&MS",
        "Trail Mix & Snack Mixes",
        category_path="Snack > Trail Mix",
        product_identity="Trail Mix",
        variant=["energy"],
        rationale="Energy variant of trail mix.",
        mint_required=True,
    ),
    case(
        "mixed_nuts_no_peanuts",
        "MIXED NUTS, NO PEANUTS",
        "Snack Nuts",
        category_path="Snack > Nuts",
        product_identity="Mixed Nuts",
        claims=["peanut_free"],
        rationale="Mixed nuts identity; peanut_free is a claim derived from 'no peanuts'.",
        mint_required=True,
    ),
    case(
        "sweet_and_salty_trail_mix",
        "SWEET AND SALTY TRAIL MIX",
        "Trail Mix & Snack Mixes",
        category_path="Snack > Trail Mix",
        product_identity="Trail Mix",
        variant=["sweet_and_salty"],
        rationale="Sweet and salty variant.",
        mint_required=True,
    ),
    case(
        "fruit_and_nut_mix",
        "FRUIT AND NUT MIX, RAISINS ALMONDS CASHEWS",
        "Trail Mix & Snack Mixes",
        category_path="Snack > Trail Mix",
        product_identity="Trail Mix",
        variant=["fruit_and_nut"],
        rationale="Fruit and nut variant of trail mix.",
        mint_required=True,
    ),
]

# --------------------------------------------------------------------------
# CATEGORY F: RETAIL MEAT CUTS
# --------------------------------------------------------------------------
F_MEAT = [
    case(
        "boneless_skinless_chicken_breast",
        "BONELESS SKINLESS CHICKEN BREAST",
        "Poultry, Chicken & Turkey",
        category_path="Meat & Seafood > Poultry",
        product_identity="Chicken Breast",
        form_texture_cut=["boneless", "skinless"],
        rationale="Chicken Breast is the cut; boneless+skinless are form descriptors.",
        mint_required=True,
    ),
    case(
        "bone_in_pork_chops",
        "BONE-IN PORK CHOPS",
        "Pork",
        category_path="Meat & Seafood > Pork",
        product_identity="Pork Chops",
        form_texture_cut=["bone_in"],
        rationale="Pork Chops; bone_in is form.",
        mint_required=True,
    ),
    case(
        "ground_beef_80_20",
        "GROUND BEEF 80/20",
        "Beef",
        category_path="Meat & Seafood > Beef",
        product_identity="Ground Beef",
        variant=["80_20"],
        rationale="Ground Beef; 80/20 fat ratio is the variant.",
        mint_required=True,
    ),
    case(
        "ground_turkey_93_7",
        "GROUND TURKEY 93/7",
        "Poultry, Chicken & Turkey",
        category_path="Meat & Seafood > Poultry",
        product_identity="Ground Turkey",
        variant=["93_7"],
        rationale="Ground turkey lean ratio variant.",
        mint_required=True,
    ),
    case(
        "boneless_pork_ribs",
        "BONELESS COUNTRY STYLE PORK RIBS",
        "Pork",
        category_path="Meat & Seafood > Pork",
        product_identity="Pork Ribs",
        variant=["country_style"],
        form_texture_cut=["boneless"],
        rationale="Pork Ribs; country style is the cut/style variant; boneless is form.",
        mint_required=True,
    ),
    case(
        "skirt_steak",
        "SKIRT STEAK BEEF",
        "Beef",
        category_path="Meat & Seafood > Beef",
        product_identity="Skirt Steak",
        rationale="Skirt Steak is its own cut identity.",
        mint_required=True,
    ),
    case(
        "filet_mignon_beef_tenderloin",
        "FILET MIGNON BEEF TENDERLOIN STEAK",
        "Beef",
        category_path="Meat & Seafood > Beef",
        product_identity="Filet Mignon",
        rationale="Filet mignon is its own retail node; tenderloin is the underlying cut.",
        mint_required=True,
    ),
    case(
        "whole_chicken",
        "WHOLE CHICKEN",
        "Poultry, Chicken & Turkey",
        category_path="Meat & Seafood > Poultry",
        product_identity="Whole Chicken",
        form_texture_cut=["whole"],
        rationale="Whole Chicken; whole is form.",
        mint_required=True,
    ),
    case(
        "chicken_thighs_bone_in_skin_on",
        "CHICKEN THIGHS BONE-IN SKIN-ON",
        "Poultry, Chicken & Turkey",
        category_path="Meat & Seafood > Poultry",
        product_identity="Chicken Thighs",
        form_texture_cut=["bone_in", "skin_on"],
        rationale="Chicken Thighs; bone_in+skin_on are form descriptors.",
        mint_required=True,
    ),
    case(
        "ribeye_steak",
        "RIBEYE STEAK BONE IN",
        "Beef",
        category_path="Meat & Seafood > Beef",
        product_identity="Ribeye Steak",
        form_texture_cut=["bone_in"],
        rationale="Ribeye is the cut identity; bone_in is form.",
        mint_required=True,
    ),
]

# --------------------------------------------------------------------------
# CATEGORY G: FLAVORED MILKS
# --------------------------------------------------------------------------
G_FLAVORED_MILK = [
    case(
        "strawberry_whole_milk",
        "STRAWBERRY WHOLE MILK",
        "Flavored Milk",
        category_path="Dairy > Flavored Milk",
        product_identity="Strawberry Milk",
        variant=["whole"],
        rationale="Strawberry Milk is the compound identity for flavored milk.",
        mint_required=True,
    ),
    case(
        "vanilla_lowfat_milk",
        "VANILLA LOW FAT MILK 1%",
        "Flavored Milk",
        category_path="Dairy > Flavored Milk",
        product_identity="Vanilla Milk",
        variant=["1_percent"],
        claims=["low_fat"],
        rationale="Compound identity Vanilla Milk; 1% variant; low_fat claim.",
        mint_required=True,
    ),
    case(
        "banana_milk",
        "BANANA FLAVORED MILK",
        "Flavored Milk",
        category_path="Dairy > Flavored Milk",
        product_identity="Banana Milk",
        rationale="Compound identity Banana Milk.",
        mint_required=True,
    ),
    case(
        "cookies_and_cream_chocolate_milk",
        "COOKIES AND CREAM CHOCOLATE MILK",
        "Flavored Milk",
        category_path="Dairy > Flavored Milk",
        product_identity="Chocolate Milk",
        flavor=["cookies_and_cream"],
        rationale="Identity is Chocolate Milk; cookies_and_cream is a flavor accent.",
        mint_required=True,
    ),
    case(
        "vanilla_oat_milk",
        "VANILLA OAT MILK ORIGINAL",
        "Plant Based Beverages",
        category_path="Beverage > Plant Milk",
        product_identity="Oat Milk",
        flavor=["vanilla"],
        claims=["dairy_free", "plant_based"],
        rationale="Oat Milk identity; vanilla flavor; dairy_free.",
        mint_required=True,
    ),
]

# --------------------------------------------------------------------------
# CATEGORY H: VEGETABLES — frozen vs canned vs fresh vs seasoned
# --------------------------------------------------------------------------
H_VEGETABLES = [
    case(
        "frozen_broccoli_florets_plain",
        "FROZEN BROCCOLI FLORETS",
        "Frozen Vegetables",
        category_path="Frozen > Vegetables",
        product_identity="Broccoli",
        form_texture_cut=["florets"],
        processing_storage=["frozen"],
        rationale="Plain frozen broccoli — no sauce, no seasoning.",
        mint_required=True,
    ),
    case(
        "fresh_broccoli_crowns",
        "FRESH BROCCOLI CROWNS",
        "Pre-Packaged Fruit & Vegetables",
        category_path="Produce > Vegetables",
        product_identity="Broccoli",
        form_texture_cut=["crowns"],
        rationale="Fresh produce broccoli; crowns is the form/cut.",
        mint_required=True,
    ),
    case(
        "canned_green_beans_plain",
        "CANNED CUT GREEN BEANS",
        "Canned Vegetables",
        category_path="Pantry > Canned Vegetables",
        product_identity="Green Beans",
        form_texture_cut=["cut"],
        processing_storage=["canned"],
        rationale="Plain canned green beans, no seasoning.",
        mint_required=True,
    ),
    case(
        "seasoned_green_beans_canned",
        "SEASONED GREEN BEANS WITH BACON",
        "Canned Vegetables",
        category_path="Pantry > Canned Vegetables",
        product_identity="Green Beans",
        variant=["seasoned"],
        processing_storage=["canned"],
        components=[comp("Bacon", role="ingredient")],
        rationale="Seasoned variant with bacon ingredient component.",
        mint_required=True,
    ),
    case(
        "italian_style_frozen_veggies",
        "ITALIAN STYLE FROZEN VEGETABLE BLEND",
        "Frozen Vegetables",
        category_path="Frozen > Vegetables",
        product_identity="Vegetable Blend",
        variant=["italian_style"],
        processing_storage=["frozen"],
        rationale="Mixed-vegetable blend identity; italian_style variant.",
        mint_required=True,
    ),
    case(
        "steamfresh_broccoli_cheese_sauce",
        "STEAMFRESH BROCCOLI WITH CHEESE SAUCE",
        "Frozen Vegetables",
        retail_type="composite_dish",
        category_path="Frozen > Prepared Vegetables",
        product_identity="Broccoli with Cheese Sauce",
        processing_storage=["frozen"],
        components=[
            comp("Broccoli", role="ingredient"),
            comp("Cheese Sauce", role="sauce"),
        ],
        rationale="Composite vegetable dish, NOT plain broccoli.",
        mint_required=True,
    ),
    case(
        "canned_diced_tomatoes_italian_seasoning",
        "CANNED DICED TOMATOES WITH ITALIAN SEASONING",
        "Canned Vegetables",
        category_path="Pantry > Canned Vegetables",
        product_identity="Tomatoes",
        flavor=["italian_seasoning"],
        form_texture_cut=["diced"],
        processing_storage=["canned"],
        rationale="Tomatoes identity; italian_seasoning is flavor accent.",
    ),
    case(
        "frozen_peas_plain",
        "FROZEN GREEN PEAS",
        "Frozen Vegetables",
        category_path="Frozen > Vegetables",
        product_identity="Peas",
        processing_storage=["frozen"],
        rationale="Plain frozen peas.",
        mint_required=True,
    ),
    case(
        "fresh_baby_carrots",
        "FRESH BABY CARROTS PEELED",
        "Pre-Packaged Fruit & Vegetables",
        category_path="Produce > Vegetables",
        product_identity="Baby Carrots",
        form_texture_cut=["peeled"],
        rationale="Baby Carrots cut; peeled form.",
        mint_required=True,
    ),
    case(
        "frozen_seasoned_potatoes",
        "FROZEN SEASONED DICED POTATOES",
        "Frozen Vegetables",
        category_path="Frozen > Vegetables",
        product_identity="Potatoes",
        variant=["seasoned"],
        form_texture_cut=["diced"],
        processing_storage=["frozen"],
        rationale="Seasoned variant of frozen diced potatoes.",
    ),
]

# --------------------------------------------------------------------------
# CATEGORY I: MULTI-FLAVOR CANDY
# --------------------------------------------------------------------------
I_CANDY = [
    case(
        "skittles_original_assorted",
        "SKITTLES ORIGINAL FRUIT CANDY, WATERMELON GRAPE STRAWBERRY LEMON ORANGE",
        "Non Chocolate Candy",
        category_path="Snack > Candy",
        product_identity="Fruit Candy",
        variant=["assorted_fruit"],
        rationale="Multi-flavor pack; aggregate as 'assorted_fruit' variant rather than listing 5 flavors.",
    ),
    case(
        "starburst_original_4flavor",
        "STARBURST ORIGINAL FRUIT CHEWS, STRAWBERRY ORANGE LEMON CHERRY",
        "Non Chocolate Candy",
        category_path="Snack > Candy",
        product_identity="Fruit Chews",
        variant=["assorted_fruit"],
        rationale="Multi-flavor fruit chews; assorted variant.",
    ),
    case(
        "sour_patch_kids_assorted",
        "SOUR PATCH KIDS ORIGINAL ASSORTED",
        "Non Chocolate Candy",
        category_path="Snack > Candy",
        product_identity="Sour Candy",
        variant=["assorted"],
        rationale="Sour candy; assorted variant.",
    ),
    case(
        "lifesavers_5flavor",
        "LIFE SAVERS 5 FLAVORS HARD CANDY",
        "Non Chocolate Candy",
        category_path="Snack > Candy",
        product_identity="Hard Candy",
        variant=["assorted"],
        rationale="Hard candy; assorted variant.",
    ),
    case(
        "jelly_belly_50_flavors",
        "JELLY BELLY 50 ASSORTED FLAVORS JELLY BEANS",
        "Non Chocolate Candy",
        category_path="Snack > Candy",
        product_identity="Jelly Beans",
        variant=["assorted"],
        rationale="Jelly beans; assorted variant rather than listing 50 flavors.",
    ),
    case(
        "mm_peanut_chocolate",
        "M&M'S PEANUT CHOCOLATE CANDY",
        "Chocolate Candy",
        category_path="Snack > Chocolate Candy",
        product_identity="Chocolate Candy",
        variant=["peanut"],
        rationale="M&Ms peanut variant.",
    ),
]

# --------------------------------------------------------------------------
# CATEGORY J: SPICE BLENDS / RUBS / COMBOS
# --------------------------------------------------------------------------
J_SPICES = [
    case(
        "montreal_steak_seasoning",
        "MCCORMICK GRILL MATES MONTREAL STEAK SEASONING",
        "Seasoning Mixes, Salts, Marinades & Tenderizers",
        category_path="Pantry > Spices & Seasonings",
        product_identity="Seasoning",
        variant=["montreal_steak"],
        rationale="Seasoning identity; Montreal Steak is the named blend variant.",
    ),
    case(
        "salt_and_pepper_combo",
        "SALT AND PEPPER GRINDER COMBO",
        "Salt & Pepper",
        category_path="Pantry > Spices & Seasonings",
        product_identity="Salt and Pepper",
        rationale="Compound identity Salt and Pepper; not just one or the other.",
        mint_required=True,
    ),
    case(
        "taco_seasoning_mix",
        "TACO SEASONING MIX",
        "Seasoning Mixes, Salts, Marinades & Tenderizers",
        category_path="Pantry > Spices & Seasonings",
        product_identity="Seasoning",
        variant=["taco"],
        rationale="Seasoning identity; taco is the named-blend variant.",
    ),
    case(
        "italian_herb_blend",
        "ITALIAN HERB BLEND SEASONING",
        "Seasoning Mixes, Salts, Marinades & Tenderizers",
        category_path="Pantry > Spices & Seasonings",
        product_identity="Seasoning",
        variant=["italian_herb"],
        rationale="Italian herb blend variant.",
    ),
    case(
        "lemon_pepper_seasoning",
        "LEMON PEPPER SEASONING",
        "Seasoning Mixes, Salts, Marinades & Tenderizers",
        category_path="Pantry > Spices & Seasonings",
        product_identity="Seasoning",
        variant=["lemon_pepper"],
        rationale="Lemon pepper variant.",
    ),
    case(
        "memphis_bbq_rub",
        "MEMPHIS BBQ DRY RUB",
        "Seasoning Mixes, Salts, Marinades & Tenderizers",
        category_path="Pantry > Spices & Seasonings",
        product_identity="BBQ Rub",
        variant=["memphis"],
        rationale="BBQ Rub identity; Memphis style variant.",
        mint_required=True,
    ),
    case(
        "cajun_blackening_seasoning",
        "CAJUN BLACKENING SEASONING",
        "Seasoning Mixes, Salts, Marinades & Tenderizers",
        category_path="Pantry > Spices & Seasonings",
        product_identity="Seasoning",
        variant=["cajun_blackening"],
        rationale="Cajun blackening variant.",
    ),
    case(
        "pumpkin_pie_spice",
        "PUMPKIN PIE SPICE BLEND",
        "Seasoning Mixes, Salts, Marinades & Tenderizers",
        category_path="Pantry > Spices & Seasonings",
        product_identity="Spice Blend",
        variant=["pumpkin_pie"],
        rationale="Spice Blend identity; pumpkin_pie variant.",
        mint_required=True,
    ),
    case(
        "curry_powder",
        "MADRAS CURRY POWDER",
        "Seasoning Mixes, Salts, Marinades & Tenderizers",
        category_path="Pantry > Spices & Seasonings",
        product_identity="Curry Powder",
        variant=["madras"],
        rationale="Curry Powder identity; madras variant.",
        mint_required=True,
    ),
    case(
        "chicken_seasoning",
        "CHICKEN SEASONING",
        "Seasoning Mixes, Salts, Marinades & Tenderizers",
        category_path="Pantry > Spices & Seasonings",
        product_identity="Seasoning",
        variant=["chicken"],
        rationale="Chicken seasoning is a named-blend variant of Seasoning.",
    ),
]

# --------------------------------------------------------------------------
# CATEGORY K: NAMED ICE CREAM FLAVORS (Chunky Monkey trip)
# --------------------------------------------------------------------------
K_ICE_CREAM = [
    case(
        "ben_jerry_chunky_monkey",
        "BEN & JERRY'S CHUNKY MONKEY ICE CREAM",
        "Ice Cream & Frozen Yogurt",
        category_path="Frozen > Ice Cream",
        product_identity="Ice Cream",
        variant=["chunky_monkey"],
        rationale="Named blend like Chunky Monkey is a VARIANT, not a flavor token. (Title flavor accents like banana would still be a flavor.)",
        mint_required=True,
        notes="Critical: do NOT split chunky_monkey into separate flavor tokens.",
    ),
    case(
        "ben_jerry_cherry_garcia",
        "BEN & JERRY'S CHERRY GARCIA ICE CREAM",
        "Ice Cream & Frozen Yogurt",
        category_path="Frozen > Ice Cream",
        product_identity="Ice Cream",
        variant=["cherry_garcia"],
        rationale="Cherry Garcia is the named blend variant.",
        mint_required=True,
    ),
    case(
        "ben_jerry_half_baked",
        "BEN & JERRY'S HALF BAKED ICE CREAM",
        "Ice Cream & Frozen Yogurt",
        category_path="Frozen > Ice Cream",
        product_identity="Ice Cream",
        variant=["half_baked"],
        rationale="Half Baked named blend variant.",
        mint_required=True,
    ),
    case(
        "haagen_dazs_vanilla_swiss_almond",
        "HAAGEN-DAZS VANILLA SWISS ALMOND ICE CREAM",
        "Ice Cream & Frozen Yogurt",
        category_path="Frozen > Ice Cream",
        product_identity="Ice Cream",
        variant=["vanilla_swiss_almond"],
        rationale="Vanilla Swiss Almond named blend variant.",
        mint_required=True,
    ),
    case(
        "talenti_sea_salt_caramel_gelato",
        "TALENTI SEA SALT CARAMEL GELATO",
        "Ice Cream & Frozen Yogurt",
        category_path="Frozen > Gelato",
        product_identity="Gelato",
        flavor=["sea_salt_caramel"],
        rationale="Gelato identity; sea_salt_caramel is a flavor.",
        mint_required=True,
    ),
    case(
        "vanilla_ice_cream_plain",
        "VANILLA ICE CREAM",
        "Ice Cream & Frozen Yogurt",
        category_path="Frozen > Ice Cream",
        product_identity="Ice Cream",
        flavor=["vanilla"],
        rationale="Plain vanilla ice cream — vanilla IS a flavor here, not a named blend.",
        mint_required=False,
    ),
]

# --------------------------------------------------------------------------
# CATEGORY L: COMPOUND CONDIMENTS
# --------------------------------------------------------------------------
L_CONDIMENTS = [
    case(
        "horseradish_aioli_sauce",
        "HORSERADISH AIOLI SAUCE",
        "Sauces, Marinades & Dressings",
        category_path="Pantry > Sauces & Salsas",
        product_identity="Aioli",
        flavor=["horseradish"],
        rationale="Aioli identity with horseradish flavor accent.",
        mint_required=True,
    ),
    case(
        "sriracha_mayo",
        "SRIRACHA MAYO",
        "Sauces, Marinades & Dressings",
        category_path="Pantry > Sauces & Salsas",
        product_identity="Mayonnaise",
        flavor=["sriracha"],
        rationale="Mayonnaise base with sriracha flavor accent.",
    ),
    case(
        "honey_mustard_dressing",
        "HONEY MUSTARD SALAD DRESSING",
        "Salad Dressings",
        category_path="Pantry > Salad Dressings",
        product_identity="Salad Dressing",
        flavor=["honey_mustard"],
        rationale="Salad Dressing identity; honey_mustard flavor.",
    ),
    case(
        "chipotle_ranch_dressing",
        "CHIPOTLE RANCH DRESSING",
        "Salad Dressings",
        category_path="Pantry > Salad Dressings",
        product_identity="Ranch Dressing",
        flavor=["chipotle"],
        rationale="Ranch Dressing identity; chipotle flavor.",
        mint_required=True,
    ),
    case(
        "garlic_herb_butter",
        "GARLIC HERB COMPOUND BUTTER",
        "Butter",
        category_path="Dairy > Butter",
        product_identity="Butter",
        variant=["compound"],
        flavor=["garlic_herb"],
        rationale="Butter identity; compound variant; garlic_herb flavor.",
    ),
]

# --------------------------------------------------------------------------
# CATEGORY M: MULTIGRAIN BREADS
# --------------------------------------------------------------------------
M_BREADS = [
    case(
        "12_grain_bread",
        "12 GRAIN BREAD",
        "Breads & Buns",
        category_path="Bakery > Bread",
        product_identity="Bread",
        variant=["12_grain"],
        rationale="Bread identity; 12_grain variant.",
    ),
    case(
        "15_grain_bread",
        "15 GRAIN BREAD",
        "Breads & Buns",
        category_path="Bakery > Bread",
        product_identity="Bread",
        variant=["15_grain"],
        rationale="Bread identity; 15_grain variant.",
    ),
    case(
        "whole_wheat_sourdough",
        "WHOLE WHEAT SOURDOUGH BREAD",
        "Breads & Buns",
        category_path="Bakery > Bread",
        product_identity="Sourdough Bread",
        variant=["whole_wheat"],
        rationale="Sourdough Bread identity; whole_wheat variant.",
        mint_required=True,
    ),
    case(
        "multi_seed_sandwich_bread",
        "MULTI-SEED SANDWICH BREAD",
        "Breads & Buns",
        category_path="Bakery > Bread",
        product_identity="Bread",
        variant=["multi_seed"],
        form_texture_cut=["sandwich"],
        rationale="Bread identity; multi_seed variant; sandwich form.",
    ),
    case(
        "sprouted_grain_bread",
        "SPROUTED GRAIN BREAD",
        "Breads & Buns",
        category_path="Bakery > Bread",
        product_identity="Bread",
        variant=["sprouted_grain"],
        rationale="Sprouted grain variant of bread.",
    ),
    case(
        "ezekiel_4_9_sprouted_bread",
        "EZEKIEL 4:9 SPROUTED WHOLE GRAIN BREAD",
        "Breads & Buns",
        category_path="Bakery > Bread",
        product_identity="Bread",
        variant=["sprouted_whole_grain"],
        claims=["whole_grain"],
        rationale="Brand-name aside, identity is Bread with sprouted_whole_grain variant.",
    ),
]

# --------------------------------------------------------------------------
# CATEGORY N: FRUIT/VEGGIE SNACK STRIPS (dehydrated, NOT fresh fruit)
# --------------------------------------------------------------------------
N_FRUIT_LEATHER = [
    case(
        "sweet_potato_apple_spice_strips",
        "SWEET POTATO APPLE + SPICES FRUIT AND VEGGIE STRIPS",
        "Wholesome Snacks",
        category_path="Snack > Fruit Leather",
        product_identity="Fruit and Veggie Strips",
        flavor=["sweet_potato", "apple", "spices"],
        form_texture_cut=["strips"],
        rationale="Dehydrated fruit/veggie snack strips, NOT fresh apples. Current pipeline maps to Apples; gold says Fruit Leather family.",
        mint_required=True,
        notes="USER-PROVIDED. Real fdc 2174477.",
    ),
    case(
        "fruit_leather_strawberry",
        "STRAWBERRY FRUIT LEATHER",
        "Wholesome Snacks",
        category_path="Snack > Fruit Leather",
        product_identity="Fruit Leather",
        flavor=["strawberry"],
        rationale="Fruit Leather identity; strawberry flavor.",
        mint_required=True,
    ),
    case(
        "freeze_dried_apple_chips",
        "FREEZE-DRIED APPLE CHIPS",
        "Wholesome Snacks",
        category_path="Snack > Dried Fruit",
        product_identity="Apple Chips",
        processing_storage=["freeze_dried"],
        rationale="Apple Chips identity; freeze_dried processing.",
        mint_required=True,
    ),
    case(
        "veggie_straws",
        "VEGGIE STRAWS, ORIGINAL",
        "Chips, Pretzels & Snacks",
        category_path="Snack > Veggie Snacks",
        product_identity="Veggie Straws",
        rationale="Veggie Straws snack, not actual vegetables.",
        mint_required=True,
    ),
]

# --------------------------------------------------------------------------
# CATEGORY O: SNACK PACK COMBOS
# --------------------------------------------------------------------------
O_SNACK_PACKS = [
    case(
        "peeled_apples_butterscotch_dip",
        "PEELED APPLES, BUTTERSCOTCH",
        "Pre-Packaged Fruit & Vegetables",
        retail_type="combo_pack",
        category_path="Produce > Snack Packs",
        product_identity="Apple Snack Pack",
        form_texture_cut=["peeled"],
        components=[
            comp("Apples", role="fruit", form_texture_cut=["peeled", "sliced"]),
            comp("Butterscotch Dip", role="sauce"),
        ],
        rationale="Multi-component snack pack: peeled apple slices with butterscotch dipping sauce. NOT plain apples.",
        mint_required=True,
        notes="USER-PROVIDED. Real fdc 1902454.",
    ),
    case(
        "apples_caramel_snack_pack",
        "APPLES AND CARAMEL DIPPING SAUCE",
        "Pre-Packaged Fruit & Vegetables",
        retail_type="combo_pack",
        category_path="Produce > Snack Packs",
        product_identity="Apple Snack Pack",
        components=[
            comp("Apples", role="fruit"),
            comp("Caramel Dip", role="sauce"),
        ],
        rationale="Apples + caramel dip snack pack.",
        mint_required=True,
    ),
    case(
        "cheese_crackers_snack_pack",
        "CHEESE AND CRACKERS SNACK PACK",
        "Snack Crackers",
        retail_type="combo_pack",
        category_path="Snack > Snack Packs",
        product_identity="Cheese and Crackers Pack",
        components=[
            comp("Cheese", role="cheese"),
            comp("Crackers", role="ingredient"),
        ],
        rationale="Cheese + crackers combo snack.",
        mint_required=True,
    ),
    case(
        "lunchable_pizza",
        "LUNCHABLES PIZZA WITH PEPPERONI",
        "Refrigerated Lunch Kits",
        retail_type="combo_pack",
        category_path="Refrigerated > Lunch Kits",
        product_identity="Lunch Kit",
        variant=["pizza_with_pepperoni"],
        components=[
            comp("Pizza Crusts", role="ingredient"),
            comp("Pizza Sauce", role="sauce"),
            comp("Mozzarella Cheese", role="cheese"),
            comp("Pepperoni", role="protein"),
        ],
        rationale="Lunchables-style assemble-it-yourself lunch kit.",
        mint_required=True,
    ),
]

# --------------------------------------------------------------------------
# CATEGORY P: MISCATEGORIZED-AS-FRUIT (apple-named items that aren't apples)
# --------------------------------------------------------------------------
P_NOT_FRUIT = [
    case(
        "culinary_crisps_apple_oat_crunch",
        "CULINARY CRISPS, APPLE OAT CRUNCH",
        "Crackers & Biscotti",
        category_path="Snack > Crackers",
        product_identity="Flatbread Crisps",
        flavor=["apple", "oat"],
        form_texture_cut=["crunch"],
        rationale="Flatbread crackers / culinary crisps, NOT fresh apples. Real fdc 2438029 currently mapped to Apples.",
        mint_required=True,
        notes="USER-PROVIDED. Title leads with 'Apple' but it's a cracker product.",
    ),
    case(
        "apple_pie_filling_canned",
        "CANNED APPLE PIE FILLING",
        "Pie Fillings",
        category_path="Pantry > Pie Fillings",
        product_identity="Pie Filling",
        flavor=["apple"],
        processing_storage=["canned"],
        rationale="Canned pie filling, not fresh fruit.",
        mint_required=True,
    ),
    case(
        "apple_butter",
        "APPLE BUTTER, ORIGINAL",
        "Jams, Jellies & Spreads",
        category_path="Pantry > Spreads",
        product_identity="Apple Butter",
        rationale="Apple Butter is a spread, not a butter and not an apple.",
        mint_required=True,
    ),
    case(
        "apple_juice_concentrate",
        "FROZEN APPLE JUICE CONCENTRATE",
        "Juices & Beverages",
        category_path="Frozen > Juice Concentrate",
        product_identity="Juice Concentrate",
        flavor=["apple"],
        processing_storage=["frozen", "from_concentrate"],
        rationale="Frozen juice concentrate; flavor=apple, not fresh apples.",
        mint_required=True,
    ),
    case(
        "applesauce_unsweetened",
        "UNSWEETENED APPLESAUCE",
        "Applesauce",
        category_path="Pantry > Applesauce",
        product_identity="Applesauce",
        claims=["unsweetened"],
        rationale="Applesauce is its own retail identity, not fresh apples.",
        mint_required=True,
    ),
]

# --------------------------------------------------------------------------
# CATEGORY Q: CAKES vs CUPCAKES vs SPECIFIC CAKE TYPES
# --------------------------------------------------------------------------
Q_CAKES = [
    case(
        "vanilla_cupcakes_six_pack",
        "VANILLA CUPCAKES, 6 PACK",
        "Cakes, Cupcakes, Snack Cakes",
        category_path="Bakery > Cupcakes",
        product_identity="Cupcakes",
        flavor=["vanilla"],
        rationale="Cupcakes is its own identity, distinct from Cake. Vanilla flavor.",
        mint_required=True,
    ),
    case(
        "chocolate_cupcakes_buttercream",
        "CHOCOLATE CUPCAKES WITH BUTTERCREAM FROSTING",
        "Cakes, Cupcakes, Snack Cakes",
        category_path="Bakery > Cupcakes",
        product_identity="Cupcakes",
        flavor=["chocolate"],
        components=[comp("Buttercream Frosting", role="topping")],
        rationale="Cupcakes identity; chocolate flavor; buttercream frosting as a component.",
        mint_required=True,
    ),
    case(
        "sour_cream_pound_cake",
        "SOUR CREAM POUND CAKE",
        "Cakes, Cupcakes, Snack Cakes",
        category_path="Bakery > Cake",
        product_identity="Pound Cake",
        variant=["sour_cream"],
        rationale="Pound Cake identity (specific cake type); sour_cream is the variant. NOT 'sour' flavor.",
        mint_required=True,
        notes="USER-PROVIDED. Real fdc 2057081 'SOUR CREME CAKE' is currently mapped as Cake with flavor=sour. Gold says it's a sour cream pound cake variant.",
    ),
    case(
        "chocolate_layer_cake",
        "CHOCOLATE LAYER CAKE",
        "Cakes, Cupcakes, Snack Cakes",
        category_path="Bakery > Cake",
        product_identity="Cake",
        variant=["chocolate", "layer"],
        rationale="Cake identity; chocolate+layer variants.",
    ),
    case(
        "carrot_cake_with_cream_cheese_frosting",
        "CARROT CAKE WITH CREAM CHEESE FROSTING",
        "Cakes, Cupcakes, Snack Cakes",
        category_path="Bakery > Cake",
        product_identity="Carrot Cake",
        components=[comp("Cream Cheese Frosting", role="topping")],
        rationale="Carrot Cake is its own retail identity (specific cake type).",
        mint_required=True,
    ),
    case(
        "snack_cake_oatmeal_creme_pie",
        "OATMEAL CREME PIE SNACK CAKES",
        "Cakes, Cupcakes, Snack Cakes",
        category_path="Snack > Snack Cakes",
        product_identity="Snack Cakes",
        variant=["oatmeal_creme_pie"],
        rationale="Snack Cakes identity (Little Debbie style); oatmeal_creme_pie variant.",
        mint_required=True,
    ),
    case(
        "angel_food_cake",
        "ANGEL FOOD CAKE",
        "Cakes, Cupcakes, Snack Cakes",
        category_path="Bakery > Cake",
        product_identity="Angel Food Cake",
        rationale="Angel Food Cake is its own retail node.",
        mint_required=True,
    ),
    case(
        "muffins_blueberry",
        "BLUEBERRY MUFFINS, 4 PACK",
        "Muffins",
        category_path="Bakery > Muffins",
        product_identity="Muffins",
        flavor=["blueberry"],
        rationale="Muffins (NOT Cupcakes, NOT Cake) — separate identity.",
    ),
]

# --------------------------------------------------------------------------
# CATEGORY R: BARS — must consolidate to a small identity set!
# Test: do NOT let the model proliferate "Strawberry Bar", "Chocolate Bar",
# "Peanut Butter Bar", "Honey Almond Bar"... All variations should land on
# ~6 identities (Granola Bars, Protein Bars, Energy Bars, Cereal Bars,
# Fruit Bars, Breakfast Bars, Kids Bars).
# --------------------------------------------------------------------------
R_BARS = [
    case("kind_dark_chocolate_nut_bar",
        "KIND DARK CHOCOLATE NUTS AND SEA SALT BAR",
        "Snack & Granola Bars",
        category_path="Snack > Bars", product_identity="Granola Bars",
        flavor=["dark_chocolate"], variant=["nuts_sea_salt"],
        rationale="KIND bars consolidate to Granola Bars identity; flavor+variant capture variation."),
    case("clif_bar_chocolate_chip",
        "CLIF BAR CHOCOLATE CHIP ENERGY BAR",
        "Snack & Granola Bars",
        category_path="Snack > Bars", product_identity="Energy Bars",
        flavor=["chocolate_chip"],
        rationale="Energy Bars identity; chocolate_chip flavor."),
    case("rxbar_chocolate_sea_salt",
        "RXBAR PROTEIN BAR, CHOCOLATE SEA SALT",
        "Protein & Meal Replacement",
        category_path="Snack > Bars", product_identity="Protein Bars",
        flavor=["chocolate_sea_salt"], claims=["high_protein"],
        rationale="Protein Bars identity; flavor accent."),
    case("nature_valley_oats_honey_granola_bar",
        "NATURE VALLEY OATS N HONEY CRUNCHY GRANOLA BARS",
        "Snack & Granola Bars",
        category_path="Snack > Bars", product_identity="Granola Bars",
        flavor=["oats_honey"], form_texture_cut=["crunchy"],
        rationale="Nature Valley → Granola Bars; flavor accent + crunchy form."),
    case("quaker_chewy_chocolate_chip_bar",
        "QUAKER CHEWY CHOCOLATE CHIP GRANOLA BAR",
        "Snack & Granola Bars",
        category_path="Snack > Bars", product_identity="Granola Bars",
        flavor=["chocolate_chip"], form_texture_cut=["chewy"],
        rationale="Granola Bars; chewy form."),
    case("nutrigrain_strawberry_cereal_bar",
        "NUTRI-GRAIN STRAWBERRY CEREAL BAR",
        "Snack & Granola Bars",
        category_path="Snack > Bars", product_identity="Cereal Bars",
        flavor=["strawberry"],
        rationale="Cereal Bars identity (NOT Granola Bars); strawberry."),
    case("kelloggs_pop_tart_toaster_pastry",
        "KELLOGG'S FROSTED STRAWBERRY POP-TARTS",
        "Toaster Pastries",
        category_path="Bakery > Toaster Pastries", product_identity="Toaster Pastries",
        flavor=["strawberry"], variant=["frosted"],
        rationale="Pop-Tarts are Toaster Pastries (their own category), NOT Breakfast Bars.",
        notes="USER-CORRECTED: Pop-Tarts = Toaster Pastries identity."),
    case("larabar_apple_pie",
        "LARABAR APPLE PIE FRUIT AND NUT BAR",
        "Snack & Granola Bars",
        category_path="Snack > Bars", product_identity="Fruit Bars",
        flavor=["apple_pie"],
        rationale="Fruit Bars identity (fruit & nut, no oats); apple_pie flavor."),
    case("perfect_bar_peanut_butter",
        "PERFECT BAR PEANUT BUTTER REFRIGERATED PROTEIN BAR",
        "Protein & Meal Replacement",
        category_path="Snack > Bars", product_identity="Protein Bars",
        flavor=["peanut_butter"], claims=["high_protein"],
        rationale="Protein Bars; refrigerated is incidental, not a facet."),
    case("quest_chocolate_chip_cookie_dough_bar",
        "QUEST CHOCOLATE CHIP COOKIE DOUGH PROTEIN BAR",
        "Protein & Meal Replacement",
        category_path="Snack > Bars", product_identity="Protein Bars",
        flavor=["chocolate_chip_cookie_dough"], claims=["high_protein"],
        rationale="Protein Bars; long flavor compound stays as one token."),
    case("annies_bunny_grahams_chocolate_chip",
        "ANNIE'S CHOCOLATE CHIP CHEWY GRANOLA BARS",
        "Snack & Granola Bars",
        category_path="Snack > Bars", product_identity="Granola Bars",
        flavor=["chocolate_chip"], form_texture_cut=["chewy"], claims=["organic"],
        rationale="Granola Bars; chocolate_chip flavor; chewy form; organic claim."),
    case("kind_kids_chocolate_chip_bar",
        "KIND KIDS CHOCOLATE CHIP GRANOLA BARS",
        "Snack & Granola Bars",
        category_path="Snack > Bars", product_identity="Kids Bars",
        flavor=["chocolate_chip"],
        rationale="Kids Bars identity (NOT Granola Bars); kids-targeted SKU."),
    case("zbar_oatmeal_chocolate_chip",
        "CLIF KID Z BAR OATMEAL CHOCOLATE CHIP",
        "Snack & Granola Bars",
        category_path="Snack > Bars", product_identity="Kids Bars",
        flavor=["oatmeal_chocolate_chip"],
        rationale="Kids Bars identity; flavor compound."),
    case("luna_lemon_zest_bar",
        "LUNA LEMON ZEST WHOLE NUTRITION BAR",
        "Snack & Granola Bars",
        category_path="Snack > Bars", product_identity="Granola Bars",
        flavor=["lemon_zest"],
        rationale="Granola Bars; lemon_zest flavor.",
        notes="Luna isn't strictly a granola bar but the ingredients/format match."),
    case("met_rx_meal_replacement_bar",
        "MET-RX BIG 100 MEAL REPLACEMENT BAR, CHOCOLATE FUDGE",
        "Protein & Meal Replacement",
        category_path="Snack > Bars", product_identity="Meal Replacement Bars",
        flavor=["chocolate_fudge"], claims=["high_protein"],
        rationale="Meal Replacement Bars identity (distinct from Protein Bars)."),
    case("special_k_protein_bar_chocolatey_chip",
        "SPECIAL K PROTEIN MEAL BAR CHOCOLATEY CHIP",
        "Protein & Meal Replacement",
        category_path="Snack > Bars", product_identity="Protein Bars",
        flavor=["chocolatey_chip"], claims=["high_protein"],
        rationale="Protein Bars identity."),
    case("snickers_almond_candy_bar",
        "SNICKERS ALMOND CHOCOLATE CANDY BAR",
        "Chocolate Candy",
        category_path="Snack > Chocolate Candy", product_identity="Candy Bar",
        variant=["almond"],
        rationale="Snickers Almond is a candy bar (chocolate candy domain), not a granola/protein bar."),
    case("twix_caramel_cookie_bar",
        "TWIX CARAMEL COOKIE CHOCOLATE BAR",
        "Chocolate Candy",
        category_path="Snack > Chocolate Candy", product_identity="Candy Bar",
        variant=["caramel_cookie"],
        rationale="Twix is a candy bar."),
    case("kit_kat_wafer_bar",
        "KIT KAT WAFER BAR",
        "Chocolate Candy",
        category_path="Snack > Chocolate Candy", product_identity="Candy Bar",
        variant=["wafer"],
        rationale="Kit Kat is a candy bar (with wafer variant)."),
    case("oatmeal_breakfast_bar",
        "QUAKER OATMEAL TO GO BREAKFAST BARS, BROWN SUGAR CINNAMON",
        "Snack & Granola Bars",
        category_path="Snack > Bars", product_identity="Breakfast Bars",
        flavor=["brown_sugar_cinnamon"],
        rationale="Breakfast Bars identity."),
    case("fruit_bar_strawberry_real_fruit",
        "REAL FRUIT STRAWBERRY FRUIT BAR",
        "Snack & Granola Bars",
        category_path="Snack > Bars", product_identity="Fruit Bars",
        flavor=["strawberry"],
        rationale="Fruit Bars identity; strawberry."),
]

# --------------------------------------------------------------------------
# CATEGORY S: GRANOLA — many flavors, ONE identity (Granola)
# --------------------------------------------------------------------------
S_GRANOLA = [
    case("nature_valley_oats_honey_granola",
        "NATURE VALLEY OATS HONEY GRANOLA",
        "Cereals",
        category_path="Snack > Granola", product_identity="Granola",
        flavor=["oats_honey"],
        rationale="Granola identity; flavor accent."),
    case("kind_dark_chocolate_granola",
        "KIND DARK CHOCOLATE GRANOLA CLUSTERS",
        "Cereals",
        category_path="Snack > Granola", product_identity="Granola",
        flavor=["dark_chocolate"], form_texture_cut=["clusters"],
        rationale="Granola; flavor + clusters form."),
    case("bear_naked_vanilla_almond_granola",
        "BEAR NAKED VANILLA ALMOND GRANOLA",
        "Cereals",
        category_path="Snack > Granola", product_identity="Granola",
        flavor=["vanilla_almond"],
        rationale="Granola; vanilla_almond flavor compound."),
    case("purely_elizabeth_pumpkin_fig_granola",
        "PURELY ELIZABETH PUMPKIN FIG GRANOLA, ANCIENT GRAIN",
        "Cereals",
        category_path="Snack > Granola", product_identity="Granola",
        flavor=["pumpkin_fig"], variant=["ancient_grain"],
        rationale="Granola; ancient_grain variant; pumpkin_fig flavor."),
    case("granola_paleo_blueberry",
        "PALEO BLUEBERRY GRANOLA",
        "Cereals",
        category_path="Snack > Granola", product_identity="Granola",
        flavor=["blueberry"], claims=["paleo"],
        rationale="Granola; blueberry flavor; paleo claim."),
    case("granola_keto_cinnamon",
        "KETO CINNAMON GRAIN-FREE GRANOLA",
        "Cereals",
        category_path="Snack > Granola", product_identity="Granola",
        flavor=["cinnamon"], variant=["grain_free"], claims=["keto"],
        rationale="Granola; cinnamon flavor; grain_free variant; keto claim."),
    case("granola_coconut_almond",
        "COCONUT ALMOND GRANOLA",
        "Cereals",
        category_path="Snack > Granola", product_identity="Granola",
        flavor=["coconut_almond"],
        rationale="Granola; coconut_almond flavor."),
]

# --------------------------------------------------------------------------
# CATEGORY T: TRAIL MIX EXPANSION — more variations all -> Trail Mix
# --------------------------------------------------------------------------
U_JUICE = [
    case("apple_juice_from_concentrate_rtd",
        "APPLE JUICE MADE FROM CONCENTRATE, 64 FL OZ",
        "Juices & Beverages",
        category_path="Beverage > Juice", product_identity="Juice",
        flavor=["apple"], processing_storage=["from_concentrate"],
        rationale="RTD apple juice reconstituted from concentrate. Identity is Juice; from_concentrate is a processing marker. NOT the same as frozen Juice Concentrate.",
        notes="Distinct from apple_juice_concentrate (the frozen tube)."),
    case("orange_juice_not_from_concentrate",
        "100% PURE ORANGE JUICE, NOT FROM CONCENTRATE",
        "Juices & Beverages",
        category_path="Beverage > Juice", product_identity="Juice",
        flavor=["orange"], claims=["natural"],
        rationale="RTD orange juice; not_from_concentrate is implicit (no processing marker)."),
    case("frozen_orange_juice_concentrate",
        "FROZEN ORANGE JUICE CONCENTRATE",
        "Juices & Beverages",
        category_path="Frozen > Juice Concentrate", product_identity="Juice Concentrate",
        flavor=["orange"], processing_storage=["frozen"],
        rationale="The frozen tube of concentrate, NOT a RTD juice. Distinct identity."),
]


T_TRAIL_MIX_MORE = [
    case("trail_mix_omega3",
        "OMEGA-3 TRAIL MIX, WALNUTS PUMPKIN SEEDS",
        "Trail Mix & Snack Mixes",
        category_path="Snack > Trail Mix", product_identity="Trail Mix",
        variant=["omega_3"],
        rationale="Trail Mix; omega_3 variant."),
    case("trail_mix_hiking",
        "HIKING TRAIL MIX, ALMONDS CASHEWS PEANUTS",
        "Trail Mix & Snack Mixes",
        category_path="Snack > Trail Mix", product_identity="Trail Mix",
        variant=["hiking"],
        rationale="Trail Mix; hiking variant."),
    case("trail_mix_kids_school_safe",
        "KIDS SCHOOL SAFE TRAIL MIX, SUNFLOWER SEEDS RAISINS",
        "Trail Mix & Snack Mixes",
        category_path="Snack > Trail Mix", product_identity="Trail Mix",
        variant=["kids_school_safe"], claims=["nut_free"],
        rationale="Trail Mix; school_safe variant; nut_free claim."),
    case("trail_mix_chocolate_lovers",
        "CHOCOLATE LOVERS TRAIL MIX, MIXED CHOCOLATE",
        "Trail Mix & Snack Mixes",
        category_path="Snack > Trail Mix", product_identity="Trail Mix",
        variant=["chocolate_lovers"], flavor=["chocolate"],
        rationale="Trail Mix; chocolate_lovers variant + chocolate flavor."),
    case("trail_mix_organic_raw_almond_cashew",
        "ORGANIC RAW TRAIL MIX, ALMONDS CASHEWS",
        "Trail Mix & Snack Mixes",
        category_path="Snack > Trail Mix", product_identity="Trail Mix",
        variant=["raw"], claims=["organic"],
        rationale="Trail Mix; raw variant; organic claim."),
]

# --------------------------------------------------------------------------
# Aggregate
# --------------------------------------------------------------------------
ALL_CASES = (
    A_BEVERAGES + B_CHOCOLATE_AMBIGUITY + C_PIZZA + D_MEALS + E_TRAIL_MIX
    + F_MEAT + G_FLAVORED_MILK + H_VEGETABLES + I_CANDY + J_SPICES
    + K_ICE_CREAM + L_CONDIMENTS + M_BREADS + N_FRUIT_LEATHER + O_SNACK_PACKS
    + P_NOT_FRUIT + Q_CAKES + R_BARS + S_GRANOLA + T_TRAIL_MIX_MORE + U_JUICE
)


def main() -> None:
    out_path = V2 / "llm_taxonomy_diabolical_v2_cases.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for c in ALL_CASES:
            # Validator-friendly: tree_paths and canonical_label may have to
            # be regenerated in case earlier helper-call ordering missed them.
            ec = c["expected"]
            ec["canonical_path"] = ltc.build_canonical_path(ec["category_path"], ec["product_identity"])
            ec["canonical_label"] = ltc.build_canonical_label(ec["product_identity"], ec)
            ec["tree_paths"] = ltc.build_tree_paths(ec)
            fh.write(json.dumps(c, sort_keys=True) + "\n")

    print(f"wrote {len(ALL_CASES)} cases -> {out_path}")
    by_cat = {}
    for c in ALL_CASES:
        cat = c["name"].split("_")[0]
        by_cat[cat] = by_cat.get(cat, 0) + 1
    print(f"\nBy category prefix: {dict(sorted(by_cat.items()))}")

    # Run the gold validator from cleanup.py to ensure self-consistency
    print("\nValidating gold cases...")
    failures = ltc.validate_gold(out_path)
    if failures:
        print(f"!! {failures} validation failure(s)")
        raise SystemExit(1)
    print(f"All {len(ALL_CASES)} cases validate clean.")


if __name__ == "__main__":
    main()
