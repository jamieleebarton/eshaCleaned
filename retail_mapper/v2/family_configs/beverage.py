"""Beverage family — water, soda, juice, tea, coffee, plant milk, energy drinks."""
from __future__ import annotations

FAMILY = "Beverage"

GENERIC_TYPE_LABELS = {
    "Juice", "Tea", "Coffee", "Soda", "Water",
}

SUB_FAMILY_BY_TYPE: dict[str, str] = {
    # Tea
    **{t: "Tea" for t in [
        "Iced Tea", "Green Tea", "Black Tea", "Herbal Tea", "Oolong Tea",
        "Chai", "White Tea", "Matcha", "Rooibos", "Earl Grey",
    ]},
    # Coffee
    **{t: "Coffee" for t in [
        "Cold Brew Coffee", "Hot Coffee", "Espresso", "Drip Coffee",
        "French Press", "Latte", "Cappuccino", "Americano", "Mocha",
        "Instant Coffee",
    ]},
    # Juice
    **{t: "Juice" for t in [
        "Orange Juice", "Apple Juice", "Grape Juice", "Cranberry Juice",
        "Pomegranate Juice", "Grapefruit Juice", "Pineapple Juice",
        "Tomato Juice", "Vegetable Juice", "Carrot Juice", "Beet Juice",
        "Cherry Juice", "Lemon Juice", "Lime Juice", "Coconut Water",
    ]},
    # Carbonated / Soda
    **{t: "Carbonated" for t in [
        "Cola", "Lemon-Lime Soda", "Root Beer", "Ginger Ale", "Cream Soda",
        "Orange Soda", "Grape Soda", "Diet Cola", "Diet Soda",
    ]},
    # Plant Milk
    **{t: "Plant Milk" for t in [
        "Almond Milk", "Oat Milk", "Soy Milk", "Coconut Milk", "Rice Milk",
        "Cashew Milk", "Hemp Milk", "Pea Milk", "Macadamia Milk",
    ]},
    # Energy / Sports
    **{t: "Energy Drinks" for t in ["Energy Drink", "Energy Shot"]},
    **{t: "Sports Drinks" for t in ["Sports Drink", "Electrolyte Drink"]},
    # Protein
    **{t: "Protein Drinks" for t in ["Protein Shake", "Whey Shake"]},
}

TYPE_KEYWORDS: list[tuple[str, str]] = [
    # ---- Plant milks (compound first)
    ("almond milk",         "Almond Milk"),
    ("oat milk",            "Oat Milk"),
    ("soy milk",            "Soy Milk"),
    ("coconut milk",        "Coconut Milk"),
    ("rice milk",           "Rice Milk"),
    ("cashew milk",         "Cashew Milk"),
    ("hemp milk",           "Hemp Milk"),
    ("pea milk",            "Pea Milk"),
    ("macadamia milk",      "Macadamia Milk"),
    # ---- Juices
    ("orange juice",        "Orange Juice"),
    ("apple juice",         "Apple Juice"),
    ("grape juice",         "Grape Juice"),
    ("cranberry juice",     "Cranberry Juice"),
    ("pomegranate",         "Pomegranate Juice"),
    ("grapefruit juice",    "Grapefruit Juice"),
    ("pineapple juice",     "Pineapple Juice"),
    ("tomato juice",        "Tomato Juice"),
    ("vegetable juice",     "Vegetable Juice"),
    ("carrot juice",        "Carrot Juice"),
    ("beet juice",          "Beet Juice"),
    ("cherry juice",        "Cherry Juice"),
    ("lemon juice",         "Lemon Juice"),
    ("lime juice",          "Lime Juice"),
    ("coconut water",       "Coconut Water"),
    # ---- Tea types
    ("iced tea",            "Iced Tea"),
    ("green tea",           "Green Tea"),
    ("black tea",           "Black Tea"),
    ("herbal tea",          "Herbal Tea"),
    ("oolong",              "Oolong Tea"),
    ("white tea",           "White Tea"),
    ("matcha",              "Matcha"),
    ("rooibos",             "Rooibos"),
    ("earl grey",           "Earl Grey"),
    ("chai",                "Chai"),
    # ---- Coffee
    ("cold brew",           "Cold Brew Coffee"),
    ("french press",        "French Press"),
    ("instant coffee",      "Instant Coffee"),
    ("espresso",            "Espresso"),
    ("cappuccino",          "Cappuccino"),
    ("americano",           "Americano"),
    ("latte",               "Latte"),
    ("mocha",               "Mocha"),
    ("drip coffee",         "Drip Coffee"),
    # ---- Soda / carbonated (compound first)
    ("diet cola",           "Diet Cola"),
    ("diet soda",           "Diet Soda"),
    ("lemon-lime soda",     "Lemon-Lime Soda"),
    ("lemon lime soda",     "Lemon-Lime Soda"),
    ("root beer",           "Root Beer"),
    ("ginger ale",          "Ginger Ale"),
    ("cream soda",          "Cream Soda"),
    ("orange soda",         "Orange Soda"),
    ("grape soda",          "Grape Soda"),
    ("cola",                "Cola"),
    ("sparkling water",     "Sparkling Water"),
    ("seltzer",             "Sparkling Water"),
    ("tonic water",         "Tonic Water"),
    ("club soda",            "Club Soda"),
    # ---- Energy / sports / protein
    ("energy shot",         "Energy Shot"),
    ("energy drink",        "Energy Drink"),
    ("sports drink",        "Sports Drink"),
    ("electrolyte drink",   "Electrolyte Drink"),
    ("protein shake",       "Protein Shake"),
    ("whey shake",          "Whey Shake"),
    # ---- Other
    ("kombucha",            "Kombucha"),
    ("lemonade",            "Lemonade"),
    ("smoothie",            "Smoothies"),
    ("hot chocolate",       "Hot Chocolate"),
    ("hot cocoa",            "Hot Chocolate"),
    ("milkshake",            "Milkshake"),
    ("eggnog",               "Eggnog"),
    ("horchata",             "Horchata"),
    ("coffee creamer",      "Coffee Creamer"),
    # ---- Generic fallbacks
    ("juice",               "Juice"),
    ("tea",                 "Tea"),
    ("coffee",              "Coffee"),
    ("soda",                "Soda"),
    ("water",                "Water"),
]

TIERS: list[list[tuple[str, str]]] = [
    # Tier 1: temperature/state
    [
        ("iced",            "Iced"),
        ("hot",             "Hot"),
        ("frozen",          "Frozen"),
    ],
    # Tier 2: sweetness
    [
        ("unsweetened",     "Unsweetened"),
        ("lightly sweetened","Lightly Sweetened"),
        ("sweetened",       "Sweetened"),
        ("sugar free",       "Sugar Free"),
        ("sugar-free",       "Sugar Free"),
        ("diet",            "Diet"),
        ("zero",            "Zero"),
    ],
    # Tier 3: caffeine
    [
        ("decaffeinated",   "Decaf"),
        ("decaf",           "Decaf"),
        ("caffeinated",     "Caffeinated"),
    ],
    # Tier 4: roast (coffee)
    [
        ("dark roast",      "Dark Roast"),
        ("medium roast",    "Medium Roast"),
        ("light roast",     "Light Roast"),
    ],
    # Tier 5: carbonation
    [
        ("sparkling",       "Sparkling"),
        ("still",           "Still"),
    ],
]
