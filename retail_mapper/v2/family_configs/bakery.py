"""Bakery family — bread, rolls, buns, pastry, cake."""
from __future__ import annotations

FAMILY = "Bakery"

GENERIC_TYPE_LABELS = {
    "Bread", "Rolls", "Cake", "Buns", "Pie", "Muffins", "Cupcakes",
    "Brownies", "Doughnuts",
}

# Bread types live under Bread; rolls under Rolls; buns under Buns; etc.
SUB_FAMILY_BY_TYPE: dict[str, str] = {
    # Breads
    **{t: "Bread" for t in [
        "Rye Bread", "Sourdough Bread", "Whole Wheat Bread", "White Bread",
        "Multigrain Bread", "Pumpernickel Bread", "Wheat Bread",
        "Cinnamon Raisin Bread", "Honey Wheat Bread", "Honey Oat Bread",
        "Italian Bread", "French Bread", "Ciabatta", "Brioche",
        "Challah", "Focaccia", "Baguette", "Pita Bread", "Naan",
        "Cornbread", "Banana Bread", "Sweet Bread", "Garlic Bread",
        "Texas Toast", "Soda Bread",
    ]},
    # Rolls
    **{t: "Rolls" for t in [
        "Dinner Rolls", "Brioche Rolls", "Cinnamon Rolls", "Pretzel Rolls",
        "Garlic Rolls", "Sweet Rolls", "Hawaiian Rolls", "Crescent Rolls",
        "Yeast Rolls",
    ]},
    # Buns
    **{t: "Buns" for t in [
        "Hamburger Buns", "Hot Dog Buns", "Slider Buns", "Brioche Buns",
        "Sesame Buns", "Pretzel Buns", "Brat Buns", "Sandwich Buns",
    ]},
    # Pastry
    **{t: "Pastry" for t in [
        "Croissants", "Danishes", "Eclairs", "Churros", "Fritters",
        "Strudel",
    ]},
    # Cake
    **{t: "Cake" for t in [
        "Layer Cake", "Bundt Cake", "Sheet Cake", "Pound Cake",
        "Cheesecake", "Coffee Cake", "Sponge Cake", "Angel Food Cake",
    ]},
    # Snack Cakes
    **{t: "Snack Cakes" for t in [
        "Honey Buns", "Twinkies", "Ho Hos", "Ding Dongs", "Zingers",
    ]},
}

TYPE_KEYWORDS: list[tuple[str, str]] = [
    # ---- Multi-word breads
    ("english muffin",      "English Muffins"),
    ("cinnamon raisin",     "Cinnamon Raisin Bread"),
    ("honey wheat",         "Honey Wheat Bread"),
    ("honey oat",           "Honey Oat Bread"),
    ("whole wheat bread",   "Whole Wheat Bread"),
    ("rye bread",           "Rye Bread"),
    ("sourdough bread",     "Sourdough Bread"),
    ("pumpernickel",        "Pumpernickel Bread"),
    ("white bread",         "White Bread"),
    ("multigrain bread",    "Multigrain Bread"),
    ("italian bread",       "Italian Bread"),
    ("french bread",        "French Bread"),
    ("ciabatta",            "Ciabatta"),
    ("brioche bun",         "Brioche Buns"),
    ("brioche roll",        "Brioche Rolls"),
    ("brioche",             "Brioche"),
    ("challah",             "Challah"),
    ("focaccia",            "Focaccia"),
    ("baguette",            "Baguette"),
    ("pita bread",          "Pita Bread"),
    ("pita",                "Pita Bread"),
    ("naan",                "Naan"),
    ("cornbread",           "Cornbread"),
    ("corn bread",          "Cornbread"),
    ("banana bread",        "Banana Bread"),
    ("garlic bread",        "Garlic Bread"),
    ("texas toast",         "Texas Toast"),
    ("soda bread",          "Soda Bread"),
    ("flatbread",           "Flatbread"),
    ("flat bread",          "Flatbread"),
    ("tortilla",            "Tortillas"),
    ("bagel",               "Bagels"),
    # ---- Buns (multi-word, function-first)
    ("hamburger bun",       "Hamburger Buns"),
    ("hot dog bun",         "Hot Dog Buns"),
    ("slider bun",          "Slider Buns"),
    ("brat bun",            "Brat Buns"),
    ("sesame bun",          "Sesame Buns"),
    ("pretzel bun",         "Pretzel Buns"),
    ("sandwich bun",        "Sandwich Buns"),
    # ---- Rolls
    ("cinnamon roll",       "Cinnamon Rolls"),
    ("dinner roll",         "Dinner Rolls"),
    ("hawaiian roll",       "Hawaiian Rolls"),
    ("crescent roll",       "Crescent Rolls"),
    ("yeast roll",          "Yeast Rolls"),
    ("sweet roll",          "Sweet Rolls"),
    ("garlic roll",         "Garlic Rolls"),
    ("pretzel roll",        "Pretzel Rolls"),
    # ---- Pastry
    ("croissant",           "Croissants"),
    ("danish",              "Danishes"),
    ("eclair",              "Eclairs"),
    ("churro",              "Churros"),
    ("fritter",             "Fritters"),
    ("strudel",             "Strudel"),
    ("biscotti",            "Biscotti"),
    ("scone",               "Scones"),
    ("crouton",             "Croutons"),
    ("breadstick",          "Breadsticks"),
    # ---- Cake
    ("layer cake",          "Layer Cake"),
    ("bundt cake",          "Bundt Cake"),
    ("sheet cake",          "Sheet Cake"),
    ("pound cake",          "Pound Cake"),
    ("cheesecake",          "Cheesecake"),
    ("coffee cake",         "Coffee Cake"),
    ("sponge cake",         "Sponge Cake"),
    ("angel food",          "Angel Food Cake"),
    # ---- Snack Cakes
    ("honey bun",           "Honey Buns"),
    ("twinkie",             "Twinkies"),
    ("ho ho",               "Ho Hos"),
    ("ding dong",           "Ding Dongs"),
    ("zinger",              "Zingers"),
    # ---- Doughnuts
    ("doughnut",            "Doughnuts"),
    ("donut",               "Doughnuts"),
    ("cruller",             "Doughnuts"),
    # ---- Brownies / Cookies
    ("brownie",             "Brownies"),
    ("muffin",              "Muffins"),
    ("cupcake",             "Cupcakes"),
    # ---- Generic fallbacks (last)
    ("rolls",               "Rolls"),
    ("bread",               "Bread"),
    ("cake",                "Cake"),
    ("buns",                "Buns"),
    ("pie",                 "Pie"),
]

TIERS: list[list[tuple[str, str]]] = [
    # Tier 1: grain/style sub-type for bread (where applicable beyond type)
    [
        ("whole wheat",     "Whole Wheat"),
        ("whole grain",     "Whole Grain"),
        ("multigrain",      "Multigrain"),
        ("seven grain",     "Seven Grain"),
        ("12 grain",        "12 Grain"),
        ("9 grain",         "9 Grain"),
        ("rye",             "Rye"),
        ("seedless rye",    "Seedless Rye"),
        ("caraway",         "Caraway"),
        ("seeded",          "Seeded"),
    ],
    # Tier 2: cooking/preparation style
    [
        ("toasted",         "Toasted"),
        ("baked",           "Baked"),
        ("frozen",          "Frozen"),
    ],
    # Tier 3: size/portion
    [
        ("mini",            "Mini"),
        ("jumbo",           "Jumbo"),
        ("petite",          "Petite"),
    ],
]
