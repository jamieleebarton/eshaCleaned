"""Snack family — chips, candy, cookies, pretzels, popcorn, bars, nuts."""
from __future__ import annotations

FAMILY = "Snack"

GENERIC_TYPE_LABELS = {
    "Chips", "Crackers", "Candy", "Bars", "Nuts", "Cookies",
    "Popcorn", "Pretzels", "Trail Mix", "Granola", "Rice Cakes",
    "Fruit Snacks",
}

SUB_FAMILY_BY_TYPE: dict[str, str] = {
    # Chips
    **{t: "Chips" for t in [
        "Potato Chips", "Tortilla Chips", "Pita Chips", "Veggie Chips",
        "Bagel Chips", "Pretzel Chips", "Banana Chips", "Plantain Chips",
        "Apple Chips", "Kale Chips", "Bean Chips", "Cassava Chips",
        "Sweet Potato Chips", "Corn Chips", "Rice Chips", "Cheese Chips",
    ]},
    # Candy
    **{t: "Candy" for t in [
        "Chocolate Candy", "Hard Candy", "Gummy Candy", "Caramel",
        "Chocolate Bars", "Truffles", "Lollipops", "Toffee", "Licorice",
        "Mints", "Marshmallows", "Jelly Beans", "Chewy Candy",
        "Sour Candy",
    ]},
    # Bars
    **{t: "Bars" for t in [
        "Granola Bars", "Protein Bars", "Energy Bars", "Cereal Bars",
        "Fruit Bars", "Nutrition Bars", "Meal Replacement Bars",
    ]},
    # Nuts
    **{t: "Nuts" for t in [
        "Almonds", "Cashews", "Peanuts", "Pistachios", "Walnuts",
        "Pecans", "Hazelnuts", "Macadamia Nuts", "Brazil Nuts",
        "Mixed Nuts", "Pine Nuts",
    ]},
    # Crackers
    **{t: "Crackers" for t in [
        "Saltine Crackers", "Cheese Crackers", "Graham Crackers",
        "Wheat Crackers", "Rice Crackers", "Water Crackers",
    ]},
}

TYPE_KEYWORDS: list[tuple[str, str]] = [
    # ---- Chip types (most-specific first)
    ("sweet potato chip",   "Sweet Potato Chips"),
    ("tortilla chip",       "Tortilla Chips"),
    ("potato chip",         "Potato Chips"),
    ("pita chip",           "Pita Chips"),
    ("veggie chip",         "Veggie Chips"),
    ("bagel chip",          "Bagel Chips"),
    ("pretzel chip",        "Pretzel Chips"),
    ("banana chip",         "Banana Chips"),
    ("plantain chip",       "Plantain Chips"),
    ("apple chip",          "Apple Chips"),
    ("kale chip",           "Kale Chips"),
    ("bean chip",           "Bean Chips"),
    ("cassava chip",        "Cassava Chips"),
    ("corn chip",           "Corn Chips"),
    ("rice chip",           "Rice Chips"),
    ("cheese chip",         "Cheese Chips"),
    # ---- Candy
    ("chocolate bar",       "Chocolate Bars"),
    ("chocolate candy",     "Chocolate Candy"),
    ("hard candy",          "Hard Candy"),
    ("gummy",               "Gummy Candy"),
    ("jelly bean",          "Jelly Beans"),
    ("chewy candy",         "Chewy Candy"),
    ("sour candy",          "Sour Candy"),
    ("truffle",             "Truffles"),
    ("lollipop",            "Lollipops"),
    ("licorice",            "Licorice"),
    ("toffee",              "Toffee"),
    ("caramel",             "Caramel"),
    ("mint",                "Mints"),
    ("marshmallow",         "Marshmallows"),
    # ---- Bars
    ("granola bar",         "Granola Bars"),
    ("protein bar",         "Protein Bars"),
    ("energy bar",          "Energy Bars"),
    ("cereal bar",          "Cereal Bars"),
    ("fruit bar",           "Fruit Bars"),
    ("nutrition bar",       "Nutrition Bars"),
    ("meal replacement",    "Meal Replacement Bars"),
    # ---- Nuts
    ("mixed nut",           "Mixed Nuts"),
    ("pine nut",            "Pine Nuts"),
    ("brazil nut",          "Brazil Nuts"),
    ("macadamia",           "Macadamia Nuts"),
    ("almond",              "Almonds"),
    ("cashew",              "Cashews"),
    ("peanut",              "Peanuts"),
    ("pistachio",           "Pistachios"),
    ("walnut",              "Walnuts"),
    ("pecan",               "Pecans"),
    ("hazelnut",            "Hazelnuts"),
    # ---- Crackers
    ("saltine",             "Saltine Crackers"),
    ("cheese cracker",      "Cheese Crackers"),
    ("graham cracker",      "Graham Crackers"),
    ("wheat cracker",       "Wheat Crackers"),
    ("rice cracker",        "Rice Crackers"),
    ("water cracker",       "Water Crackers"),
    # ---- Pretzels
    ("pretzel",             "Pretzels"),
    # ---- Other snacks
    ("popcorn",             "Popcorn"),
    ("trail mix",           "Trail Mix"),
    ("granola",             "Granola"),
    ("rice cake",           "Rice Cakes"),
    ("fruit snack",         "Fruit Snacks"),
    ("cookie",              "Cookies"),
    ("biscotti",            "Biscotti"),
    # ---- Generic fallbacks
    ("chips",               "Chips"),
    ("crackers",             "Crackers"),
    ("candy",                "Candy"),
    ("bars",                 "Bars"),
    ("nuts",                 "Nuts"),
]

TIERS: list[list[tuple[str, str]]] = [
    # Tier 1: cooking style
    [
        ("kettle cooked",   "Kettle Cooked"),
        ("kettle-cooked",   "Kettle Cooked"),
        ("baked",           "Baked"),
        ("fried",           "Fried"),
        ("dry roasted",     "Dry Roasted"),
        ("roasted",         "Roasted"),
        ("toasted",         "Toasted"),
        ("popped",          "Popped"),
        ("puffed",          "Puffed"),
    ],
    # Tier 2: salt/flavor
    [
        ("unsalted",        "Unsalted"),
        ("lightly salted",  "Lightly Salted"),
        ("salted",          "Salted"),
    ],
    # Tier 3: hardness/texture (pretzels)
    [
        ("hard",            "Hard"),
        ("soft",            "Soft"),
    ],
    # Tier 4: size/portion
    [
        ("mini",            "Mini"),
        ("jumbo",           "Jumbo"),
        ("bite",            "Bite Size"),
        ("snack size",      "Snack Size"),
    ],
]
