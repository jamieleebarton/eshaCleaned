#!/usr/bin/env python3
"""Reclassify SKUs to their CORRECT canonical_path.

Architectural principle (no more blocklists/imposter rules):
The HTC code's purpose is to put each SKU in the correct place in the
taxonomy. Where the bridge process misclassified products, we move them
to the right path here, then the planner naturally won't pick them at
wrong concepts.

Each rule: SKUs whose name matches `name_re` AND current consensus_canonical
matches `current_re` get moved to `target_path`.

Backs up DB. Idempotent (won't move SKUs already at target path).
"""
from __future__ import annotations
import argparse, csv, re, shutil, sqlite3, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK = DB.with_suffix(".before_round6_reclassify.db")
LOG = ROOT / "recipe_pricing" / "reclassify_log.csv"


# Each rule: (name_re, current_re_or_exact, target_path, label, consensus_pid)
# `current_re_or_exact` is a regex matched against current consensus_canonical
# `target_path` is what consensus_canonical becomes
# `consensus_pid` is set as the new pid (taxonomy parent)
RULES: list[tuple[str, str, str, str, str]] = [
    # Cheese variants — pepper jack / jalapeno / habanero are all spicy
    # variants that recipes asking for plain "cheese" should not get.
    (r"\bpepper.?jack\b",     r"^Dairy > Cheese$",
        "Dairy > Cheese > Pepper Jack",  "pepper_jack",  "Pepper Jack"),
    (r"\bjalapeno\b.*\bcheese\b|\bjalapeno\b.*\bjack\b",
                                r"^Dairy > Cheese$",
        "Dairy > Cheese > Pepper Jack",  "jalapeno_cheese","Pepper Jack"),
    (r"\bhabanero\b.*\bcheese\b|\bhabanero\b.*\bjack\b",
                                r"^Dairy > Cheese$",
        "Dairy > Cheese > Pepper Jack",  "habanero_cheese","Pepper Jack"),
    (r"\bneufchatel\b|\bneufchâtel\b",
                                r"^Dairy > Cheese(?: > Cream Cheese)?$",
        "Dairy > Cheese > Neufchatel", "neufchatel_cheese", "Neufchatel"),

    # Imitation products — each gets its own path
    (r"\bimitation\b.*\bvanilla\b|\bvanilla\b.*\bimitation\b",
                                r"Pantry > Baking Extracts|Pantry > Spices & Seasonings|^Pantry$|Pantry > Baking Additives",
        "Pantry > Baking Extracts > Imitation Vanilla", "imitation_vanilla", "Imitation Vanilla"),
    (r"\bimitation\b.*\bcheese\b|\bcheese food\b|\bcheese product\b",
                                r"^Dairy > Cheese$",
        "Dairy > Cheese > Imitation Cheese", "imitation_cheese", "Imitation Cheese"),
    (r"\bimitation\b.*\bcrab\b",  r"^Pantry > Canned Seafood > Crabmeat$|^Pantry$",
        "Meal > Salads > Imitation Crab", "imitation_crab", "Imitation Crab"),
    (r"\bimitation\b.*\bbacon\b",  r"^Meat & Seafood > Bacon$",
        "Meat & Seafood > Plant-Based Bacon", "imitation_bacon", "Plant-Based Bacon"),

    # Cooking spray — move from oil paths to existing spray path
    (r"\bcooking spray\b|^[a-z ]*spray\b.*\boil\b|\boil spray\b",
                                r"^Pantry > Oil",
        "Pantry > Cooking Oils > Cooking Spray", "cooking_spray", "Cooking Spray"),

    # "Vegetable Oil Sticks" / "Vegetable Oil Spread Sticks" — these are
    # MARGARINE labeled as oil sticks. Recipe asking "vegetable oil" gets
    # them when they live at the oil path. Move to margarine path.
    (r"vegetable oil sticks|vegetable oil spread",
                                r"^Pantry > Oil",
        "Dairy > Butter > Margarine", "margarine_sticks", "Margarine"),
    (r"\bsmart balance\b.*\bcooking oil blend\b",
                                r"^Pantry > Oil",
        "Dairy > Butter > Margarine", "smart_balance_oil_blend", "Margarine"),

    # "Velveeta Slices" / "Velveeta Original" — pasteurized cheese product
    # that recipe asking for "cheese" should not get unless recipe asks
    # for processed/American cheese variant. Move to Imitation Cheese.
    (r"\bvelveeta\b.*(slices|original|sliced cheese|cheese\b)",
                                r"^Dairy > Cheese$",
        "Dairy > Cheese > Imitation Cheese", "velveeta_plain", "Imitation Cheese"),
    (r"\bcheddar\b.*\b(?:snack sticks?|snack bites?|cheese snacks?)\b|"
     r"\b(?:snack sticks?|snack bites?|cheese snacks?)\b.*\bcheddar\b",
                                r"^Dairy > Cheese > Cheddar$",
        "Dairy > Cheese > Cheddar Snack Cheese", "cheddar_snack_cheese",
        "Cheddar Snack Cheese"),

    # Compound vegetable mixes at single-veg paths — "Peas & Carrots",
    # "Mixed Vegetables" should not be picked when recipe says plain "peas"
    # or plain "carrots". Move to Mixed Vegetables variant path.
    (r"peas\s*(?:&|and)\s*carrots|carrots\s*(?:&|and)\s*peas",
                                r"^Frozen > Vegetables|^Pantry > Canned Vegetables",
        "Pantry > Canned Vegetables > Mixed Vegetables", "peas_and_carrots", "Mixed Vegetables"),
    (r"mixed vegetables|vegetable medley|garden blend",
                                r"^(Frozen > Vegetables > (Peas|Carrots|Beans|Corn|Spinach|Broccoli|Cauliflower|[A-Z][a-z]*[^B][^l][^e][^n][^d])|Pantry > Canned Vegetables > (Peas|Carrots|Beans|Corn|Spinach))",
        "Pantry > Canned Vegetables > Mixed Vegetables", "mixed_veg", "Mixed Vegetables"),

    # Flavored stewed tomatoes ("Italian Recipe Stewed Tomatoes With Basil/Garlic")
    # at plain Tomatoes path — recipes asking "1 can diced tomatoes" should
    # not get the flavored variant. Move to a variant path.
    (r"stewed tomatoes\s+with|italian.?recipe stewed|italian-style stewed",
                                r"^Pantry > Canned Vegetables > Tomatoes$",
        "Pantry > Canned Vegetables > Stewed Tomatoes", "stewed_flavored",
        "Stewed Tomatoes"),
    (r"diced tomatoes\s+with\b|tomatoes with chiles|tomatoes with green chil|fire roasted tomatoes",
                                r"^Pantry > Canned Vegetables > Tomatoes$",
        "Pantry > Canned Vegetables > Diced Tomatoes Flavored", "diced_flavored",
        "Diced Tomatoes Flavored"),

    # Round 11 — surfaced from W5 shopping list audit
    # Mayo at olive oil path (Kraft Mayo with Olive Oil is mayonnaise)
    (r"\bmayo\b.*olive oil|mayonnaise.*olive oil|with olive oil$",
                                r"^Pantry > Oil",
        "Pantry > Sauces & Salsas > Mayonnaise", "mayo_at_oil", "Mayonnaise"),

    # Flavored pork (bell pepper and onion, etc) at plain Pork path
    (r"bell pepper and onion|pepper and onion|seasoned pork|marinated pork",
                                r"^Meat & Seafood > Pork$",
        "Meat & Seafood > Pork > Flavored Pork", "flavored_pork", "Flavored Pork"),
    (r"\bchorizo\b",
                                r"^Meat & Seafood > Pork$",
        "Meat & Seafood > Sausage > Chorizo Sausage", "chorizo_at_generic_pork",
        "Chorizo Sausage"),
    (r"\b(?:pork\s+)?sausage\b|\bsausage roll\b|\bground italian sausage\b",
                                r"^Meat & Seafood > Pork$",
        "Meat & Seafood > Sausage > Pork Sausage", "sausage_at_generic_pork",
        "Pork Sausage"),
    (r"\bham\b",
                                r"^Meat & Seafood > Pork$",
        "Meat & Seafood > Ham", "ham_at_generic_pork", "Ham"),

    # Strawberries & Cream / vanilla cream extract at Crema path
    (r"strawberries.*cream|vanilla.*cream|cream.*extract|extract.*cream",
                                r"^Dairy > Cream > Crema$|^Dairy > Cream$",
        "Pantry > Baking Extracts > Cream Extract", "cream_extract", "Cream Extract"),
    (r"\bsoda\b.*\bcream\b|\bcream\b.*\bsoda\b",
                                r"^Dairy > Cream$",
        "Beverage > Carbonated > Soda > Cream Soda", "cream_soda_at_cream",
        "Cream Soda"),

    # "Corn Cob Bites" / "Corn on the Cob" at peas/carrots/mixed-veg paths
    (r"corn cob|corn on the cob|cob bites",
                                r"^(Frozen > Vegetables > (Peas|Carrots|Peas and Carrots)|Pantry > Canned Vegetables > Mixed)",
        "Frozen > Vegetables > Corn", "corn_at_wrong_veg", "Corn"),

    # Dry cones/cups used to serve ice cream are not frozen ice cream.
    # Keep actual filled ice-cream cups/cones (vanilla/chocolate/sundae/fl oz)
    # at Frozen, but move dry cup/cone packages to the ice-cream-cone path.
    (r"^(?!.*\b(?:vanilla|chocolate|strawberry|sundae|fudge|caramel|birthday|swirl|fl\s*oz)\b)"
     r".*\b(?:jumbo\s+)?ice cream cups\b",
                                r"^Frozen > Ice Cream$",
        "Snack > Ice Cream Cones", "dry_ice_cream_cups", "Ice Cream Cone"),

    # "Saute" / "Stir-Fry" sauces at plain veg paths
    (r"saute brown sugar|stir.?fry sauce|broccoli stir|saute glaze",
                                r"^Produce > Vegetables > [^M]",
        "Pantry > Sauces & Salsas > Stir-Fry Sauce", "saute_sauce", "Stir-Fry Sauce"),

    # Soy / vegan chorizo at frankfurter/sausage paths
    (r"soy chorizo|vegetarian chorizo|vegan chorizo|plant.?based chorizo",
                                r"^Meat & Seafood",
        "Meat & Seafood > Plant-Based", "soy_chorizo", "Plant-Based Meat"),

    # Bouillon at protein paths — bouillon is a flavoring, not protein
    (r"\bbouillon\b|\bstock cube\b|\bbroth seasoning\b",
                                r"^Meat & Seafood",
        "Pantry > Broth & Stock > Bouillon", "bouillon", "Bouillon"),

    # Cornmeal mush — prepared product
    (r"\bcorn ?meal mush\b|\bcornmeal mush\b",
                                r"Cornmeal",
        "Pantry > Prepared > Cornmeal Mush", "cornmeal_mush", "Cornmeal Mush"),

    # Seasoned / panko / italian breadcrumbs at plain Breadcrumbs path
    (r"\bpanko\b",                r"^Pantry > Baking Mixes > Breadcrumbs$",
        "Pantry > Baking Mixes > Panko Breadcrumbs", "panko", "Panko Breadcrumbs"),
    (r"(?:^|[^a-z])(seasoned|italian)[^a-z].*bread ?crumb|bread ?crumb.*(?:seasoned|italian)",
                                r"^Pantry > Baking Mixes > Breadcrumbs$",
        "Pantry > Baking Mixes > Seasoned Breadcrumbs", "seasoned_panko", "Seasoned Breadcrumbs"),

    # Plant-based meat substitutes at meat paths
    (r"\bbeyond meat\b|\bbeyond beef\b|\bbeyond burger\b|\bbeyond sausage\b",
                                r"^Meat & Seafood",
        "Meat & Seafood > Plant-Based", "beyond_meat", "Plant-Based Meat"),
    (r"\bimpossible\b.*(?:meat|burger|beef|sausage)\b",
                                r"^Meat & Seafood",
        "Meat & Seafood > Plant-Based", "impossible_meat", "Plant-Based Meat"),
    (r"\bmorningstar\b.*(?:bacon|sausage|burger|chicken)\b|\bveggie bacon\b|\bmeatless bacon\b",
                                r"^Meat & Seafood",
        "Meat & Seafood > Plant-Based", "morningstar", "Plant-Based Meat"),
    (r"plant.?based|vegan|vegetarian|meat alternative|chik'?n|chick'n|veggie dogs",
                                r"^Meat & Seafood > Poultry",
        "Meat & Seafood > Plant-Based", "plant_based_poultry", "Plant-Based Meat"),

    # Pet treats misfiled as licorice candy because the flavor says licorice.
    (r"\bmanna pro\b.*\bgoat treats?\b|\bgoat treats?\b",
                                r"^Snack > Candy > Licorice$",
        "Non-Food > Pet", "goat_treats_at_licorice", "Pet Food"),

    # Food misroutes found in the recipe→retail bridge audit. These are not
    # quarantine cases: move the SKU to the aisle a shopper would expect.
    (r"fresh .*lemons?|seedless lemons?|wonderful seedless lemons?",
                                r"^Frozen > Frozen Fruit > Lemon",
        "Produce > Fruit > Lemons", "fresh_lemon_at_frozen", "Lemons"),
    (r"fresh .*oranges?|cara cara|navel oranges?",
                                r"^Frozen > Frozen Fruit > Orange",
        "Produce > Fruit > Oranges", "fresh_orange_at_frozen", "Oranges"),
    (r"fresh .*mango|honey mangos?",
                                r"^Frozen > Frozen Fruit > Mango",
        "Produce > Fruit > Mango", "fresh_mango_at_frozen", "Mango"),
    (r"fresh jalape(?:n|ñ)o peppers?|jalape(?:n|ñ)o peppers?.*fresh",
                                r"^$|^Produce > Vegetables(?: > Peppers)?$|^Pantry > Peppers",
        "Produce > Vegetables > Jalapenos", "fresh_jalapeno", "Jalapenos"),
    (r"^(?!.*\bmutti\b)(?:fresh .*tomato(?:es)?|tomato.*vine|grape tomato(?:es)?|cherry tomato(?:es)?|cocktail tomato(?:es)?|green tomato)",
                                r"^$|^Pantry > Canned Vegetables > Tomatoes$",
        "Produce > Vegetables > Tomatoes", "fresh_tomato_at_canned", "Tomatoes"),
    (r"\bmutti\b|whole peeled|crushed tomatoes|stewed tomatoes|diced tomatoes|tomato puree|tomatoes?,.*\bcan\b|canned tomatoes?",
                                r"^Produce > Vegetables > Tomatoes$",
        "Pantry > Canned Vegetables > Tomatoes", "canned_tomato_at_fresh", "Canned Tomatoes"),
    (r"\bshredded\b.*\blettuce\b|\blettuce\b.*\bshredded\b",
                                r"^Produce > Vegetables > Lettuce$",
        "Produce > Vegetables > Shredded Lettuce",
        "shredded_lettuce_at_whole", "Shredded Lettuce"),
    (r"lettuce.*(?:hamburger mix|tomato and onion|salad mix|salad blend|lettuce blend)|(?:hamburger mix|tomato and onion|salad mix|salad blend|lettuce blend).*lettuce",
                                r"^Produce > Vegetables > Lettuce$",
        "Produce > Vegetables > Lettuce Mix",
        "lettuce_mix_at_whole", "Lettuce Mix"),
    (r"banana pepper rings?",
                                r"^Frozen > Vegetables > Peppers$",
        "Pantry > Peppers > Banana Pepper Rings",
        "banana_pepper_rings_at_frozen_peppers", "Banana Pepper Rings"),
    (r"black pepper|white pepper|pepper black|black whole pepper|peppercorn|pepper grinder|pepper refill|ground pepper|pepper shaker",
                                r"^Frozen > Vegetables > Peppers$",
        "Pantry > Spices & Seasonings > Black Pepper",
        "spice_pepper_at_frozen_peppers", "Black Pepper"),
    (r"jalapeno nacho slices|serrano peppers?.*pickled carrots?",
                                r"^Frozen > Vegetables > Peppers$",
        "Pantry > Peppers > Pickled Jalapeno Peppers",
        "pickled_jalapeno_at_frozen_peppers", "Pickled Jalapeno Peppers"),
    (r"fresno chili peppers?",
                                r"^Frozen > Vegetables > Peppers$",
        "Pantry > Peppers > Chili Peppers",
        "fresno_chili_at_frozen_peppers", "Chili Peppers"),
    (r"roasted red pepper|fire roasted sweet red peppers?",
                                r"^Frozen > Vegetables > Peppers$",
        "Pantry > Canned Vegetables > Roasted Red Peppers",
        "roasted_red_pepper_at_frozen_peppers", "Roasted Red Peppers"),

    # Cheese subtype/alternative drift. Gouda at a mozzarella path is still
    # gouda; vegan/dairy-free shreds are cheese alternatives, not standard
    # recipe mozzarella.
    (r"\bgouda\b",               r"^Dairy > (?:Cheese > )?Mozzarella",
        "Dairy > Cheese > Gouda", "gouda_at_mozzarella", "Gouda"),
    (r"\bmozzarella blend\b|\bblend cheese\b",
                                r"^Dairy > Cheese > Mozzarella$",
        "Dairy > Cheese > Cheese Blend", "mozzarella_blend", "Cheese Blend"),
    (r"fat[- ]?free.*\bmozzarella\b|\bmozzarella\b.*fat[- ]?free",
                                r"^Dairy > Cheese > (?:Mozzarella|Shredded Cheese)$",
        "Dairy > Cheese > Mozzarella > Fat-Free Mozzarella",
        "fat_free_mozzarella", "Fat-Free Mozzarella"),
    (r"dairy.?free|plant.?based|vegan",
                                r"^Dairy > Cheese > (?:Mozzarella|Cheddar|Cream Cheese)",
        "Dairy > Cheese > Imitation Cheese", "dairy_free_cheese_alt", "Imitation Cheese"),

    # Canned/shelf-stable chicken was filed as raw chicken breast/chicken.
    # That made raw chicken recipes buy pouches/cans.
    (r"\bcanned\b.*\bchicken\b|\bchunk chicken\b|\bchicken\b.*\b(?:can|pouch)\b|\bpremium white chicken\b|\bkeystone\b.*\bchicken\b",
                                r"^Meat & Seafood > Poultry(?: > Chicken(?: Breast)?)?$",
        "Pantry > Canned Meat > Canned Chicken", "canned_chicken_at_raw", "Canned Chicken"),
    (r"lunch ?meat|deli sliced|deli style sliced|thin sliced lunch",
                                r"^Meat & Seafood > Poultry",
        "Meal > Sandwiches > Lunch Meat", "chicken_lunchmeat", "Lunch Meat"),
    (r"nuggets?|popcorn chicken|dino",
                                r"^Meat & Seafood > Poultry > Chicken Breast$",
        "Meat & Seafood > Nuggets > Chicken Nuggets", "nuggets_at_breast", "Chicken Nuggets"),
    (r"chicken patt(?:y|ies)",
                                r"^Meat & Seafood > Poultry > Chicken Breast$",
        "Meat & Seafood > Poultry > Chicken Patties", "patties_at_breast", "Chicken Patties"),
    (r"chicken strips?|breast strips?|(?:crispy|breaded|fully cooked|frozen).*(?:chicken|breast).*(?:tenders?|tenderloins?)",
                                r"^Meat & Seafood > Poultry > Chicken Breast$",
        "Meat & Seafood > Poultry > Chicken Strips", "strips_at_breast", "Chicken Strips"),
    (r"fully cooked|grilled|roasted|rotisserie|diced|dices|shredded|shortcuts|fajitas?|skewers?|stuffed|with gravy",
                                r"^Meat & Seafood > Poultry > Chicken Breast$",
        "Meal > Meal Starters > Cooked Chicken", "cooked_chicken_at_raw", "Cooked Chicken"),
    (r"fully cooked|ready[ -]?to[ -]?(?:eat|heat)|grilled|roasted|rotisserie|diced|dices|shredded|pulled|seasoned|sauced|cilantro lime|korean bbq|chile verde|sweet chili|barbecue|pollo deshebrado|popcorn chicken|chicken rings",
                                r"^Meat & Seafood > Poultry > Chicken$",
        "Meal > Meal Starters > Cooked Chicken", "prepared_chicken_at_raw", "Cooked Chicken"),
    (r"breaded.*chicken.*fillets?|chicken.*fillets?.*breaded|lightly breaded chicken breast fillets?",
                                r"^Meat & Seafood > Poultry > Chicken Breast$",
        "Meat & Seafood > Poultry > Chicken Strips", "breaded_fillets_at_breast", "Chicken Strips"),

    # Produce/shelf-stable form errors. These are food, just not fresh
    # produce, so move them instead of letting the index drop them.
    (r"\bsmoothie\b",
                                r"^Produce > Vegetables > Greens$",
        "Beverage > Smoothies > Smoothie", "greens_smoothie", "Smoothie"),
    (r"\bjackfruit\b",
                                r"^Produce > Fruit > Limes$",
        "Pantry > Canned Fruit > Jackfruit", "jackfruit_at_limes", "Jackfruit"),
    (r"sabritas.*(?:snacks?|mix)|(?:snacks?|mix).*sabritas",
                                r"^Produce > Fruit > Limes$",
        "Snack > Corn Snacks", "snack_mix_at_limes", "Corn Snacks"),
    (r"honey stinger.*energy chews?",
                                r"^Produce > Fruit > Limes$",
        "Sports & Wellness > Energy Gels", "energy_chews_at_limes", "Energy Gels"),
    (r"cutwater.*margarita",
                                r"^Produce > Fruit > Limes$",
        "Beverage > Cocktails", "cocktail_at_limes", "Cocktail"),
    (r"briannas.*cilantro lime",
                                r"^Produce > Fruit > Limes$",
        "Pantry > Salad Dressings", "dressing_at_limes", "Salad Dressing"),
    (r"pepitas",
                                r"^Produce > Fruit > Limes$",
        "Snack > Nuts & Seeds > Pumpkin Seeds", "pepitas_at_limes", "Pumpkin Seeds"),
    (r"cherr(?:y|ies).*(?:100\s*%.*juice|in juice|can|canned)|(?:can|canned).*cherr",
                                r"^Produce > Fruit > Cherries$",
        "Pantry > Canned Fruit > Cherries", "canned_cherries_at_fresh", "Canned Cherries"),
    (r"(?:can|canned).*sweet potatoes|sweet potatoes.*(?:can|canned|shelf[ -]?stable)",
                                r"^Produce > Vegetables > Sweet Potatoes$",
        "Pantry > Canned Vegetables > Sweet Potatoes", "canned_sweet_potatoes_at_fresh", "Canned Sweet Potatoes"),
    (r"freeze[ -]?dried chives?|dried chives?",
                                r"^Produce > Vegetables > Chives$",
        "Pantry > Spices & Seasonings > Chives", "dried_chives_at_fresh", "Chives"),
    (r"dehydrated|freeze[ -]?dried|dried",
                                r"^Produce > Vegetables > (?:Baby Carrots|Carrots|Cabbage|Potatoes > French Fries)$",
        "Pantry > Dried Vegetables", "dried_vegetables_at_fresh", "Dried Vegetables"),
    (r"^parsley$",
                                r"^Pantry$",
        "Produce > Vegetables > Parsley", "fresh_parsley_at_pantry", "Parsley"),
    (r"parsley.*(?:freeze[ -]?dried|dried)|(?:freeze[ -]?dried|dried).*parsley|parsley flakes?",
                                r"^Pantry$",
        "Pantry > Spices & Seasonings > Parsley Flakes", "dried_parsley_at_pantry", "Parsley Flakes"),
    (r"^cilantro$|fresh .*cilantro|whole green cilantro|organic cilantro",
                                r"^Pantry > Spices & Seasonings > Cilantro$",
        "Produce > Vegetables > Cilantro", "fresh_cilantro_at_pantry", "Cilantro"),
    (r"cilantro.*(?:stir[ -]?in )?paste|(?:stir[ -]?in )?paste.*cilantro",
                                r"^Produce > Vegetables > Cilantro$",
        "Pantry > Spices & Seasonings > Cilantro Paste", "cilantro_paste_at_fresh", "Cilantro Paste"),
    (r"cilantro.*(?:freeze[ -]?dried|dried|shaker|bottle|jar)|(?:freeze[ -]?dried|dried|shaker|bottle|jar).*cilantro",
                                r"^Produce > Vegetables > Cilantro$",
        "Pantry > Spices & Seasonings > Cilantro", "dried_cilantro_at_fresh", "Cilantro"),
    (r"(?:lemon|peppermint|vanilla|coconut|chocolate|caramel|orange).*(?:extract|flavoring)|(?:extract|flavoring).*(?:lemon|peppermint|vanilla|coconut|chocolate|caramel|orange)",
                                r"^Pantry$",
        "Pantry > Baking Extracts", "extract_at_pantry", "Baking Extract"),
    (r"rye flour|rye meal",
                                r"^Pantry$",
        "Pantry > Flour > Rye Flour", "rye_flour_at_pantry", "Rye Flour"),
    (r"natural bran",
                                r"^Pantry$",
        "Pantry > Grain > Bran", "bran_at_pantry", "Bran"),
    (r"chipotle (?:chiles?|chilies).*(?:adobo)|adobo.*chipotle",
                                r"^Pantry$",
        "Pantry > Peppers > Chipotle Peppers in Adobo Sauce", "chipotle_adobo_at_pantry", "Chipotle Peppers in Adobo Sauce"),
    (r"\bcilantro\b",
                                r"^Pantry > Spices & Seasonings > Coriander$",
        "Pantry > Spices & Seasonings > Cilantro", "cilantro_at_coriander", "Cilantro"),

    # Dill herb buckets were polluted by pickle jars and pickle mixes. Pickle
    # products should not be eligible when a recipe asks for dill weed/seed.
    (r"\bpickle\b.*(?:spears?|halves|chips|fresh pack|jar)|(?:spears?|halves|chips).*pickle",
                                r"^Pantry > Spices & Seasonings > Dill$",
        "Pantry > Pickles", "pickles_at_dill", "Pickles"),
    (r"\bpickle\b.*(?:mix|seasoning|canning)|(?:mix|seasoning|canning).*pickle",
                                r"^Pantry > Spices & Seasonings > Dill$",
        "Pantry > Spices & Seasonings > Seasoning", "pickle_mix_at_dill", "Seasoning"),
    (r"\bpopcorn seasoning\b",
                                r"^Pantry > Spices & Seasonings > Dill$",
        "Snack > Popcorn", "popcorn_seasoning_at_dill", "Popcorn"),

    # Butter/ghee spray is cooking spray, not a jar of ghee.
    (r"\bspray\b",
                                r"^Dairy > Butter > Ghee$",
        "Pantry > Cooking Oils > Cooking Spray", "ghee_spray", "Cooking Spray"),
    (r"tri-?color bell peppers?",
                                r"^Produce > Vegetables > Bell Peppers$",
        "Produce > Vegetables > Bell Peppers > Red", "tricolor_bell_peppers_for_red", "Red Bell Peppers"),
    (r"roasted red bell peppers?",
                                r"^Produce > Vegetables > Bell Peppers$",
        "Pantry > Canned Vegetables > Roasted Red Peppers", "roasted_red_peppers_at_fresh", "Roasted Red Peppers"),
    (r"whole new potatoes|sliced potatoes|canned potatoes|potatoes,\s*15 oz|potatoes.*\bcan\b",
                                r"^Produce > Vegetables > Potatoes$",
        "Pantry > Canned Vegetables > Potatoes", "canned_potatoes_at_fresh", "Canned Potatoes"),
    (r"idahoan|instant mashed potatoes|mashed potatoes side dish|mashed potato.*cup",
                                r"^Produce > Vegetables > Potatoes$",
        "Pantry > Instant Mashed Potatoes", "instant_potatoes_at_fresh", "Instant Mashed Potatoes"),
    (r"glazed carrots",
                                r"^Produce > Vegetables > Carrots$",
        "Meal > Prepared Sides > Carrots", "glazed_carrots_at_fresh", "Prepared Carrots"),

    # Beef path contamination. Bones/offal/prepared plant sides should not
    # be the cheapest substitute for generic beef in recipe costing.
    (r"marrow bone|neck bones?|beef bones?",
                                r"^Meat & Seafood > Beef$",
        "Meat & Seafood > Beef > Beef Bones", "beef_bones_at_beef", "Beef Bones"),
    (r"\btripe\b",
                                r"^Meat & Seafood > Beef$",
        "Meat & Seafood > Beef > Beef Tripe", "beef_tripe_at_beef", "Beef Tripe"),
    (r"\btongue\b",
                                r"^Meat & Seafood > Beef$",
        "Meat & Seafood > Beef > Beef Tongue", "beef_tongue_at_beef", "Beef Tongue"),
    (r"oxtails?",
                                r"^Meat & Seafood > Beef$",
        "Meat & Seafood > Beef > Beef Oxtails", "beef_oxtail_at_beef", "Beef Oxtails"),
    (r"ocean mist.*roastables",
                                r"^Meat & Seafood > Beef$",
        "Produce > Vegetables > Vegetable Blend", "produce_roastables_at_beef", "Vegetable Blend"),
    (r"\bnespresso\b|coffee.*pods?|pike place roast|espresso roast",
                                r"^Meat & Seafood > Beef > Roast$",
        "Beverage > Coffee", "coffee_roast_at_beef_roast", "Coffee"),

    # Baby food / toddler products at adult food paths
    (r"\bstage 1\b|\bstage 2\b|\bstage 3\b|\bstage 4\b|\bbaby food\b|\bfor infants?\b|\bfor toddlers?\b|\bbaby snack\b",
                                r"^(?!Baby|Non-Food).+",
        "Baby & Toddler > Baby Food", "baby_food", "Baby Food"),

    # Non-food items
    (r"\blure\b|\bsoftbait\b|\bfishing line\b|\bfly fishing\b|\bhook\b.*\b(?:fish|fishing)\b|\btackle\b",
                                r"^(?!Non-Food).+",
        "Non-Food > Outdoor & Sports", "lure", "Outdoor"),
    (r"^candle\b|\bscented candle\b|\bcandle\b.*\b(?:wax|jar|tin|aromat)\b",
                                r"^(?!Non-Food).+",
        "Non-Food > Household", "candle", "Household"),
    (r"\bdish soap\b|\bliquid dish soap\b|\bhand soap\b|\bbody wash\b|\bbar soap\b",
                                r"^(?!Non-Food).+",
        "Non-Food > Household", "soap", "Household"),
    (r"\bcomet\b.*\bcleaning powder\b|\bcleaning powder\b.*\bcomet\b|\bmultipurpose cleaning powder\b|\ball purpose cleaning powder\b",
                                r"^Non-Food > Misclassified$|^(?!Non-Food).+",
        "Non-Food > Household", "cleaning_powder", "Household"),
    (r"\bceramic mug\b|\bmug with\b|\bdesk top mug\b|\bceramic nonstick\b|\bsauce pan\b|\bdinnerware\b|\bplate set\b|\bbowl set\b",
                                r"^(?!Non-Food).+",
        "Non-Food > Kitchenware", "kitchenware", "Kitchenware"),
    (r"\bcat litter\b|\bdog food\b|\bcat food\b|\bpet food\b|\bpet treat\b|\bbird seed\b|\bwild bird\b|nature'?s song.*suet|high energy suet|peanut treat suet|berry treat suet",
                                r"^(?!Non-Food).+",
        "Non-Food > Pet", "pet_product", "Pet"),
    (r"\bburpee\b.*\bseeds?\b|\bseeds?\b.*\bburpee\b|\bburpee\b",
                                r"^$|^(?!Non-Food).+",
        "Non-Food > Garden", "garden_seed_packet", "Garden"),
    (r"\bshampoo\b|\btoothpaste\b|\bmouthwash\b|\bdenture\b|\bperfume\b|\bcologne\b|\bdeodorant\b",
                                r"^(?!Non-Food).+",
        "Non-Food > Personal Care", "personal_care", "Personal Care"),

    # Single-spice SKUs at generic Spice Blend / Seasoning paths (round-5 F2)
    # Note: only fire when name doesn't have compound-blend hints
]


# Single-spice routing for the Spice Blend / Seasoning paths
SPICE_RECLASSIFY = {
    "cumin":      "Pantry > Spices & Seasonings > Cumin",
    "oregano":    "Pantry > Spices & Seasonings > Oregano",
    "marjoram":   "Pantry > Spices & Seasonings > Marjoram",
    "paprika":    "Pantry > Spices & Seasonings > Paprika",
    "thyme":      "Pantry > Spices & Seasonings > Thyme",
    "basil":      "Pantry > Spices & Seasonings > Basil",
    "sage":       "Pantry > Spices & Seasonings > Sage",
    "rosemary":   "Pantry > Spices & Seasonings > Rosemary",
    "tarragon":   "Pantry > Spices & Seasonings > Tarragon",
    "dill":       "Pantry > Spices & Seasonings > Dill",
    "coriander":  "Pantry > Spices & Seasonings > Coriander",
    "fennel":     "Pantry > Spices & Seasonings > Fennel",
    "cardamom":   "Pantry > Spices & Seasonings > Cardamom",
    "saffron":    "Pantry > Spices & Seasonings > Saffron",
    "cloves":     "Pantry > Spices & Seasonings > Cloves",
    "nutmeg":     "Pantry > Spices & Seasonings > Nutmeg",
    "allspice":   "Pantry > Spices & Seasonings > Allspice",
    "ginger":     "Pantry > Spices & Seasonings > Ginger",
    "cinnamon":   "Pantry > Spices & Seasonings > Cinnamon",
    "turmeric":   "Pantry > Spices & Seasonings > Turmeric",
    "anise":      "Pantry > Spices & Seasonings > Anise",
    "caraway":    "Pantry > Spices & Seasonings > Caraway",
    "bay leaf":   "Pantry > Spices & Seasonings > Bay Leaf",
    "bay leaves": "Pantry > Spices & Seasonings > Bay Leaf",
}
SPICE_BLEND_PATHS = {
    "Pantry > Spices & Seasonings > Spice Blend",
    "Pantry > Spices & Seasonings > Seasoning",
}
COMPOUND_BLEND_TOKENS = (
    " blend", "all-purpose", "italian seasoning", "taco seasoning",
    "chili seasoning", "fajita seasoning", "poultry seasoning",
    "five spice", "garam masala", "curry powder", "everything bagel",
    "cajun", "creole", "ranch", "dressing",
    " with ", " and ", " salt", " sea salt", "seasoning mix",
    "rub", "marinade", "spice mix", "barbecue", "bbq",
    "annatto", "sazon", "adobo", "jerk", "pickle",
    "popcorn seasoning",
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not DB.exists():
        print(f"missing {DB}", file=sys.stderr); sys.exit(1)
    if not args.dry_run and not BAK.exists():
        print(f"backing up DB → {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    rows = cur.execute("""
        SELECT rowid, name, consensus_canonical, consensus_pid
        FROM priced_products
        WHERE name IS NOT NULL AND name != ''
          AND consensus_canonical IS NOT NULL
    """).fetchall()
    print(f"scanning {len(rows):,} rows…", file=sys.stderr)

    # Compile rules
    compiled_rules = []
    for nre, cre, tgt, label, pid in RULES:
        compiled_rules.append((re.compile(nre, re.I), re.compile(cre, re.I), tgt, label, pid))

    rule_counts: Counter = Counter()
    by_target: Counter = Counter()
    log_rows = []   # (label, old_path, new_path, name)
    updates = []   # (new_cp, new_pid, rowid)

    for rowid, name, cp, pid in rows:
        nl = (name or "").lower()
        new_cp = None; new_pid = None; matched_label = None

        # 1. Spice reclassifier (only at Spice Blend / Seasoning paths)
        if cp in SPICE_BLEND_PATHS:
            if not any(t in nl for t in COMPOUND_BLEND_TOKENS):
                # match longest spice key first
                for spice in sorted(SPICE_RECLASSIFY, key=len, reverse=True):
                    if spice in nl:
                        new_cp = SPICE_RECLASSIFY[spice]
                        new_pid = spice.title()
                        matched_label = "spice_reclassify"
                        break

        # 2. General rules
        if not new_cp:
            for nre, cre, tgt, label, new_pid_val in compiled_rules:
                if nre.search(nl) and cre.search(cp or ""):
                    new_cp = tgt
                    new_pid = new_pid_val
                    matched_label = label
                    break

        if new_cp and new_cp != cp:
            updates.append((new_cp, new_pid, rowid))
            rule_counts[matched_label] += 1
            by_target[new_cp] += 1
            if len(log_rows) < 60:
                log_rows.append({
                    "label": matched_label, "old_path": cp, "new_path": new_cp,
                    "name": (name or "")[:60],
                })

    print(f"\nrows scanned: {len(rows):,}", file=sys.stderr)
    print(f"reclassifications proposed: {len(updates):,}", file=sys.stderr)
    print(f"\nBy rule:", file=sys.stderr)
    for label, n in rule_counts.most_common():
        print(f"  {label:<22}  {n:>5}", file=sys.stderr)
    print(f"\nTop target paths (count of inbound SKUs):", file=sys.stderr)
    for tgt, n in by_target.most_common(15):
        print(f"  {n:>5}  {tgt}", file=sys.stderr)
    print(f"\nSample reclassifications:", file=sys.stderr)
    for r in log_rows[:25]:
        print(f"  [{r['label']:<18}] '{r['name']}' :  {r['old_path']} → {r['new_path']}",
              file=sys.stderr)

    LOG.write_text(
        "label,old_path,new_path,name\n" +
        "\n".join(f'"{r["label"]}","{r["old_path"]}","{r["new_path"]}","{r["name"]}"'
                   for r in log_rows)
    )

    if args.dry_run:
        print(f"\n(dry-run; no changes written)", file=sys.stderr)
        return

    print(f"\napplying {len(updates):,} updates…", file=sys.stderr)
    cur.executemany(
        """UPDATE priced_products
           SET consensus_canonical = ?, consensus_pid = ?
           WHERE rowid = ?""",
        updates,
    )
    con.commit()
    con.close()
    print(f"done. log → {LOG.name}, backup → {BAK.name}", file=sys.stderr)

    # Auto re-encode htc_code/htc_form_code/htc_full_code for the moved SKUs.
    # Skipping this leaves stale codes filed at the new path — the bug we caught.
    print(f"\nauto re-encoding htc codes for moved rows…", file=sys.stderr)
    import subprocess
    subprocess.run(
        [sys.executable, str(ROOT / "recipe_pricing" / "reencode_after_reclassify.py")],
        check=True,
    )


if __name__ == "__main__":
    main()
