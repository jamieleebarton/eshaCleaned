"""Frozen family — ice cream, frozen meals, pizza, breakfast, vegetables."""
from __future__ import annotations

FAMILY = "Frozen"

SUB_FAMILY_BY_TYPE: dict[str, str] = {
    # Ice cream family
    **{t: "Ice Cream" for t in [
        "Sherbet", "Sorbet", "Ice Pops", "Ice Cream Bar",
        "Ice Cream Sandwich", "Ice Cream Cone", "Ice Cream Cake",
        "Frozen Yogurt", "Gelato", "Frozen Custard",
    ]},
    # Frozen meals
    **{t: "Single Entrees" for t in [
        "Mac and Cheese", "Lasagna", "Burrito", "Enchiladas", "Chicken Pot Pie",
        "Pot Pie", "Frozen Entree", "TV Dinner", "Stuffed Shells",
    ]},
    # Frozen breakfast
    **{t: "Breakfast" for t in [
        "Breakfast Sandwich", "Breakfast Burrito", "Breakfast Bowl",
        "Breakfast Bake", "Hash Browns", "Omelet Bites", "Waffles",
        "Pancakes", "French Toast", "Crepes",
    ]},
    # Frozen appetizers
    **{t: "Appetizers" for t in [
        "Mozzarella Sticks", "Pizza Rolls", "Egg Rolls", "Spring Rolls",
        "Potato Skins", "Stuffed Mushrooms", "Pigs in a Blanket",
        "Corn Dog", "Wontons",
    ]},
}

TYPE_KEYWORDS: list[tuple[str, str]] = [
    # ---- Ice cream family (compound first)
    ("ice cream sandwich",  "Ice Cream Sandwich"),
    ("ice cream bar",       "Ice Cream Bar"),
    ("ice cream cone",      "Ice Cream Cone"),
    ("ice cream cake",      "Ice Cream Cake"),
    ("frozen yogurt",       "Frozen Yogurt"),
    ("frozen custard",      "Frozen Custard"),
    ("ice pop",             "Ice Pops"),
    ("popsicle",            "Ice Pops"),
    ("sherbet",             "Sherbet"),
    ("sorbet",              "Sorbet"),
    ("gelato",              "Gelato"),
    ("ice cream",           "Ice Cream"),
    # ---- Frozen meals (compound first)
    ("chicken pot pie",     "Chicken Pot Pie"),
    ("pot pie",             "Pot Pie"),
    ("mac and cheese",      "Mac and Cheese"),
    ("lasagna",             "Lasagna"),
    ("stuffed shells",      "Stuffed Shells"),
    ("enchiladas",          "Enchiladas"),
    ("tv dinner",           "TV Dinner"),
    ("frozen entree",       "Frozen Entree"),
    # ---- Breakfast
    ("breakfast sandwich",  "Breakfast Sandwich"),
    ("breakfast burrito",   "Breakfast Burrito"),
    ("breakfast bowl",      "Breakfast Bowl"),
    ("breakfast bake",      "Breakfast Bake"),
    ("hash brown",          "Hash Browns"),
    ("omelet bite",         "Omelet Bites"),
    ("waffle",              "Waffles"),
    ("pancake",             "Pancakes"),
    ("french toast",        "French Toast"),
    ("crepe",               "Crepes"),
    # ---- Appetizers
    ("mozzarella stick",    "Mozzarella Sticks"),
    ("pizza roll",          "Pizza Rolls"),
    ("egg roll",            "Egg Rolls"),
    ("spring roll",         "Spring Rolls"),
    ("potato skin",         "Potato Skins"),
    ("stuffed mushroom",    "Stuffed Mushrooms"),
    ("pigs in a blanket",   "Pigs in a Blanket"),
    ("corn dog",            "Corn Dog"),
    ("wonton",              "Wontons"),
    # ---- Other frozen
    ("burrito",             "Burrito"),
]

TIERS: list[list[tuple[str, str]]] = [
    # Tier 1: dairy base
    [
        ("non-dairy",       "Non-Dairy"),
        ("non dairy",       "Non-Dairy"),
        ("dairy free",      "Dairy Free"),
        ("dairy-free",      "Dairy Free"),
    ],
    # Tier 2: sweetness / fat
    [
        ("low fat",         "Low Fat"),
        ("low-fat",         "Low Fat"),
        ("fat free",        "Fat Free"),
        ("fat-free",        "Fat Free"),
        ("light",           "Light"),
        ("no sugar added",  "No Sugar Added"),
        ("sugar free",      "Sugar Free"),
        ("sugar-free",      "Sugar Free"),
    ],
    # Tier 3: portion size
    [
        ("mini",            "Mini"),
        ("jumbo",           "Jumbo"),
        ("snack size",      "Snack Size"),
    ],
]
