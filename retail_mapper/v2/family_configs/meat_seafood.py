"""Meat & Seafood family — beef, pork, poultry, seafood, sausage, bacon, deli."""
from __future__ import annotations

FAMILY = "Meat & Seafood"

GENERIC_TYPE_LABELS = {
    "Beef", "Pork", "Chicken", "Turkey", "Sausage", "Steak",
    "Bacon", "Ham", "Meatballs",
}

SUB_FAMILY_BY_TYPE: dict[str, str] = {
    # Beef cuts
    **{t: "Beef" for t in [
        "Ground Beef", "Steak", "Roast Beef", "Brisket", "Ribs",
        "Sirloin Steak", "Ribeye Steak", "T-Bone Steak", "Filet Mignon",
        "Flank Steak", "Skirt Steak", "Strip Steak", "Tenderloin",
        "Chuck Roast", "Top Round", "Bottom Round", "Eye of Round",
        "Stew Meat", "Beef Tips",
    ]},
    # Pork
    **{t: "Pork" for t in [
        "Pork Chops", "Pork Loin", "Pork Tenderloin", "Pork Ribs",
        "Pork Shoulder", "Pork Belly", "Ground Pork", "Pork Sausage",
    ]},
    # Poultry / Chicken
    **{t: "Poultry" for t in [
        "Chicken Breast", "Chicken Thigh", "Chicken Wings", "Chicken Drumsticks",
        "Whole Chicken", "Ground Chicken", "Chicken Tenders", "Chicken Nuggets",
    ]},
    # Turkey
    **{t: "Turkey" for t in [
        "Turkey Breast", "Ground Turkey", "Turkey Tenderloin",
        "Turkey Wings", "Turkey Drumsticks", "Whole Turkey",
    ]},
    # Sausage types
    **{t: "Sausage" for t in [
        "Italian Sausage", "Polish Sausage", "Smoked Sausage", "Bratwurst",
        "Chorizo", "Andouille", "Kielbasa", "Breakfast Sausage",
        "Chicken Sausage", "Turkey Sausage", "Beef Sausage",
        "Summer Sausage", "Pork Sausage",
    ]},
    # Seafood (excluding compound forms which sit under their own parent)
    **{t: "Seafood" for t in [
        "Tuna", "Cod", "Tilapia", "Halibut", "Mahi Mahi", "Catfish",
        "Trout", "Sea Bass", "Sole", "Pollock", "Haddock", "Snapper",
        "Sardines", "Anchovies", "Mackerel",
        "Lobster", "Scallops", "Mussels", "Clams", "Oysters",
        "Calamari", "Octopus", "Squid",
        "Fish Cakes",
    ]},
    # Crab — only compound forms get the Crab parent.
    # Plain "Crab" stays a top-level type at "Meat & Seafood > Crab".
    **{t: "Crab" for t in ["Crab Cakes", "Crab Meat", "Imitation Crab"]},
    # Salmon — same: only compounds. Plain Salmon at "Meat & Seafood > Salmon".
    **{t: "Salmon" for t in ["Salmon Cakes", "Lox"]},
    # Charcuterie / Deli
    **{t: "Deli" for t in [
        "Pastrami", "Corned Beef", "Liverwurst", "Pâté",
    ]},
    **{t: "Charcuterie" for t in [
        "Salami", "Prosciutto", "Capicola", "Mortadella", "Soppressata",
        "Speck", "Bresaola",
    ]},
}

TYPE_KEYWORDS: list[tuple[str, str]] = [
    # ---- Specific beef cuts (multi-word first)
    ("eye of round",        "Eye of Round"),
    ("filet mignon",        "Filet Mignon"),
    ("ribeye steak",        "Ribeye Steak"),
    ("ribeye",              "Ribeye Steak"),
    ("sirloin steak",       "Sirloin Steak"),
    ("t-bone steak",        "T-Bone Steak"),
    ("t-bone",              "T-Bone Steak"),
    ("flank steak",         "Flank Steak"),
    ("skirt steak",         "Skirt Steak"),
    ("strip steak",         "Strip Steak"),
    ("chuck roast",         "Chuck Roast"),
    ("top round",           "Top Round"),
    ("bottom round",        "Bottom Round"),
    ("ground beef",         "Ground Beef"),
    ("roast beef",          "Roast Beef"),
    ("beef tips",           "Beef Tips"),
    ("stew meat",           "Stew Meat"),
    ("brisket",             "Brisket"),
    ("tenderloin",          "Tenderloin"),
    # ---- Pork cuts
    ("pork chop",           "Pork Chops"),
    ("pork loin",           "Pork Loin"),
    ("pork tenderloin",     "Pork Tenderloin"),
    ("pork rib",            "Pork Ribs"),
    ("pork shoulder",       "Pork Shoulder"),
    ("pork belly",          "Pork Belly"),
    ("ground pork",         "Ground Pork"),
    # ---- Chicken parts
    ("chicken breast",      "Chicken Breast"),
    ("chicken thigh",       "Chicken Thigh"),
    ("chicken wing",        "Chicken Wings"),
    ("chicken drumstick",   "Chicken Drumsticks"),
    ("chicken tender",      "Chicken Tenders"),
    ("chicken nugget",      "Chicken Nuggets"),
    ("ground chicken",      "Ground Chicken"),
    ("whole chicken",       "Whole Chicken"),
    # ---- Turkey
    ("turkey breast",       "Turkey Breast"),
    ("ground turkey",       "Ground Turkey"),
    ("turkey tenderloin",   "Turkey Tenderloin"),
    ("turkey wing",         "Turkey Wings"),
    ("turkey drumstick",    "Turkey Drumsticks"),
    ("whole turkey",        "Whole Turkey"),
    # ---- Sausage types (compound first)
    ("italian sausage",     "Italian Sausage"),
    ("polish sausage",      "Polish Sausage"),
    ("smoked sausage",      "Smoked Sausage"),
    ("breakfast sausage",   "Breakfast Sausage"),
    ("chicken sausage",     "Chicken Sausage"),
    ("turkey sausage",      "Turkey Sausage"),
    ("beef sausage",        "Beef Sausage"),
    ("pork sausage",        "Pork Sausage"),
    ("summer sausage",      "Summer Sausage"),
    ("bratwurst",           "Bratwurst"),
    ("chorizo",             "Chorizo"),
    ("andouille",           "Andouille"),
    ("kielbasa",            "Kielbasa"),
    # ---- Seafood (compound first)
    ("mahi mahi",           "Mahi Mahi"),
    ("sea bass",            "Sea Bass"),
    ("crab cake",           "Crab Cakes"),
    ("fish cake",           "Fish Cakes"),
    ("salmon cake",         "Salmon Cakes"),
    ("tuna",                "Tuna"),
    ("cod",                 "Cod"),
    ("tilapia",             "Tilapia"),
    ("halibut",             "Halibut"),
    ("catfish",             "Catfish"),
    ("trout",               "Trout"),
    ("sole",                "Sole"),
    ("pollock",             "Pollock"),
    ("haddock",             "Haddock"),
    ("snapper",             "Snapper"),
    ("sardine",             "Sardines"),
    ("anchovy",             "Anchovies"),
    ("mackerel",            "Mackerel"),
    ("salmon",              "Salmon"),
    ("crab",                "Crab"),
    ("lobster",             "Lobster"),
    ("scallop",             "Scallops"),
    ("mussel",              "Mussels"),
    ("clam",                "Clams"),
    ("oyster",              "Oysters"),
    ("calamari",            "Calamari"),
    ("octopus",             "Octopus"),
    ("squid",               "Squid"),
    ("shrimp",              "Shrimp"),
    # ---- Charcuterie / deli
    ("pastrami",            "Pastrami"),
    ("corned beef",         "Corned Beef"),
    ("liverwurst",          "Liverwurst"),
    ("pâté",                "Pâté"),
    ("pate",                "Pâté"),
    ("salami",              "Salami"),
    ("prosciutto",          "Prosciutto"),
    ("capicola",            "Capicola"),
    ("mortadella",          "Mortadella"),
    ("soppressata",         "Soppressata"),
    ("speck",               "Speck"),
    ("bresaola",            "Bresaola"),
    # ---- Bacon / ham (no further breakdown for now)
    ("bacon",               "Bacon"),
    ("ham",                 "Ham"),
    ("meatball",            "Meatballs"),
    # ---- Generic fallbacks
    ("steak",               "Steak"),
    ("sausage",             "Sausage"),
    ("pork",                "Pork"),
    ("beef",                "Beef"),
    ("chicken",             "Chicken"),
    ("turkey",              "Turkey"),
]

TIERS: list[list[tuple[str, str]]] = [
    # Tier 1: PREP STATE — most-important recipe-relevance distinguisher.
    # Default (no match here) = raw/cooking ingredient — what a recipe wants
    # when it says "1 lb chicken breast" or "5 lb ham". Markers below apply
    # when the product is NOT the cooking ingredient.
    [
        ("breaded",         "Breaded"),
        ("crispy",          "Breaded"),
        ("crunchy",         "Breaded"),
        ("battered",        "Breaded"),
        ("breading",        "Breaded"),
        ("nugget",          "Breaded"),
        ("popcorn chicken", "Breaded"),
        ("tender",          "Breaded"),
        ("crispy strip",    "Breaded"),
        ("jerky",           "Jerky"),
        ("snack stick",     "Snack Stick"),
        ("snack bite",      "Snack Stick"),
        ("meat stick",      "Snack Stick"),
        ("deli style",      "Deli"),
        ("deli sliced",     "Deli"),
        ("luncheon",        "Deli"),
        ("lunch meat",      "Deli"),
        ("luncheon meat",   "Deli"),
        ("spiral cut",      "Spiral Cut"),
        ("spiral sliced",   "Spiral Cut"),
        ("spiral",          "Spiral Cut"),
    ],
    # Tier 2: cure/preparation
    [
        ("uncured",         "Uncured"),
        ("cured",           "Cured"),
        ("smoked",          "Smoked"),
        ("dry-aged",        "Dry-Aged"),
        ("dry aged",        "Dry-Aged"),
        ("wet-aged",        "Wet-Aged"),
    ],
    # Tier 3: bone/skin
    [
        ("boneless",        "Boneless"),
        ("bone-in",         "Bone-In"),
        ("bone in",         "Bone-In"),
        ("skinless",        "Skinless"),
        ("skin-on",         "Skin-On"),
    ],
    # Tier 4: cut style
    [
        ("ground",          "Ground"),
        ("sliced",          "Sliced"),
        ("diced",           "Diced"),
        ("cubed",           "Cubed"),
        ("shredded",        "Shredded"),
        ("whole",           "Whole"),
    ],
    # Tier 5: storage state (ONLY if explicit in title — facets handle most)
    [
        ("frozen",          "Frozen"),
        ("fresh",           "Fresh"),
    ],
]
