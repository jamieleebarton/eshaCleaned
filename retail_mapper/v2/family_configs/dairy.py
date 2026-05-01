"""Dairy family — primarily cheese, but also milk, yogurt, butter, cream.

Path shape: <Dairy> > <Type-Parent> > <Type> > <Tier-1> > <Tier-2> > ...

For Cheese: Type-Parent="Cheese", Tiers in order = moisture / milk-fat / age /
color/style. Tiers are independent and chain — a SKU titled "Low Moisture Part
Skim Mozzarella" hits BOTH tier-0 (moisture) and tier-1 (milk-fat), producing
"Dairy > Cheese > Mozzarella > Low Moisture > Part Skim".
"""
from __future__ import annotations

FAMILY = "Dairy"

GENERIC_TYPE_LABELS = {
    "Yogurt", "Butter", "Margarine", "Ghee", "Milk",
}

# Sub-family parent inserted between the family and the type.
# E.g., a Cheddar SKU lands at "Dairy > Cheese > Cheddar > ..."
# A Whole Milk SKU lands at "Dairy > Milk > Whole Milk".
SUB_FAMILY_BY_TYPE: dict[str, str] = {
    # Cheeses
    **{t: "Cheese" for t in [
        "Cheddar", "Mozzarella", "Provolone", "Swiss", "Gouda", "Feta",
        "Brie", "Camembert", "Ricotta", "American", "Colby", "Muenster",
        "Havarti", "Manchego", "Halloumi", "Mascarpone", "Gorgonzola",
        "Roquefort", "Stilton", "Limburger", "Burrata", "Fontina", "Gruyère",
        "Emmental", "Paneer", "Parmesan", "Romano", "Asiago",
        "Pepper Jack", "Monterey Jack", "Colby Jack", "Jack",
        "Queso Fresco", "Queso Blanco", "Queso Quesadilla", "Queso",
        "Cotija", "Oaxaca",
        "Cream Cheese", "Cottage Cheese", "Goat Cheese", "Blue Cheese",
        "String Cheese",
    ]},
    # Milks
    **{t: "Milk" for t in ["Whole Milk", "2% Milk", "1% Milk", "Skim Milk",
                            "Buttermilk", "Lactose Free Milk"]},
    # Yogurt
    **{t: "Yogurt" for t in ["Greek Yogurt", "Regular Yogurt", "Skyr",
                              "Kefir", "Yogurt"]},
    # Butter / cream
    **{t: "Butter" for t in ["Butter", "Margarine", "Ghee"]},
    **{t: "Cream" for t in ["Heavy Cream", "Whipping Cream", "Sour Cream",
                             "Half & Half"]},
}

# Title keyword -> canonical type name. Order: most-specific (multi-word)
# first; the matcher picks the FIRST hit, so longer phrases win.
TYPE_KEYWORDS: list[tuple[str, str]] = [
    # ---- ALL CHEESE types FIRST (cheese wins over milk when both words
    # appear in title — "Whole Milk Mozzarella" → Mozzarella, not Whole Milk).
    # Multi-word cheeses
    ("cream cheese",        "Cream Cheese"),
    ("cottage cheese",      "Cottage Cheese"),
    ("goat cheese",         "Goat Cheese"),
    ("blue cheese",         "Blue Cheese"),
    ("string cheese",       "String Cheese"),
    ("cheese stick",        "String Cheese"),
    ("pepper jack",         "Pepper Jack"),
    ("monterey jack",       "Monterey Jack"),
    ("colby jack",          "Colby Jack"),
    ("queso fresco",        "Queso Fresco"),
    ("queso blanco",        "Queso Blanco"),
    ("queso quesadilla",    "Queso Quesadilla"),
    ("cojita",              "Cotija"),
    ("cotija",              "Cotija"),
    ("oaxaca",              "Oaxaca"),
    ("parmigiano",          "Parmesan"),
    # Single-word cheeses
    ("parmesan",            "Parmesan"),
    ("romano",              "Romano"),
    ("asiago",              "Asiago"),
    ("cheddar",             "Cheddar"),
    ("mozzarella",          "Mozzarella"),
    ("provolone",           "Provolone"),
    ("swiss",               "Swiss"),
    ("gouda",               "Gouda"),
    ("feta",                "Feta"),
    ("brie",                "Brie"),
    ("camembert",           "Camembert"),
    ("ricotta",             "Ricotta"),
    ("american",            "American"),
    ("colby",               "Colby"),
    ("muenster",            "Muenster"),
    ("munster",             "Muenster"),
    ("havarti",             "Havarti"),
    ("manchego",            "Manchego"),
    ("halloumi",            "Halloumi"),
    ("mascarpone",          "Mascarpone"),
    ("gorgonzola",          "Gorgonzola"),
    ("roquefort",           "Roquefort"),
    ("stilton",             "Stilton"),
    ("limburger",           "Limburger"),
    ("burrata",             "Burrata"),
    ("fontina",             "Fontina"),
    ("gruyere",             "Gruyère"),
    ("gruyère",             "Gruyère"),
    ("emmentaler",          "Emmental"),
    ("emmental",            "Emmental"),
    ("paneer",              "Paneer"),
    ("queso",               "Queso"),
    # "jack" is last cheese so multi-word jacks win
    ("jack",                "Jack"),

    # ---- NON-cheese dairy (only matches if no cheese above matched).
    # Multi-word
    ("greek yogurt",        "Greek Yogurt"),
    ("whole milk",          "Whole Milk"),
    ("skim milk",           "Skim Milk"),
    ("2% milk",             "2% Milk"),
    ("1% milk",             "1% Milk"),
    ("lactose free",        "Lactose Free Milk"),
    ("heavy cream",         "Heavy Cream"),
    ("whipping cream",      "Whipping Cream"),
    ("sour cream",          "Sour Cream"),
    ("half & half",         "Half & Half"),
    ("half and half",       "Half & Half"),
    ("half-and-half",       "Half & Half"),
    # Single-word
    ("buttermilk",          "Buttermilk"),
    ("kefir",               "Kefir"),
    ("skyr",                "Skyr"),
    ("yogurt",              "Yogurt"),
    ("butter",              "Butter"),
    ("margarine",           "Margarine"),
    ("ghee",                "Ghee"),
    ("milk",                "Milk"),
]

# Sub-type tiers, applied IN ORDER. Each tier is a list of (keyword, label).
# Multiple tiers can match the same SKU and chain in the path.
# Within a tier, only the FIRST match wins (longer keywords first to avoid
# "low moisture" being shadowed by "low" → something else).
TIERS: list[list[tuple[str, str]]] = [
    # Tier 1: moisture (mozzarella, queso fresco, etc.)
    [
        ("low moisture",    "Low Moisture"),
        ("high moisture",   "High Moisture"),
        ("fresh",           "Fresh"),
    ],
    # Tier 2: milk-fat content
    [
        ("part skim",       "Part Skim"),
        ("part-skim",       "Part Skim"),
        ("whole milk",      "Whole Milk"),
        ("skim",            "Skim"),
        ("2%",              "2%"),
        ("1%",              "1%"),
    ],
    # Tier 3: sharpness (independent of aging length)
    [
        ("extra sharp",     "Extra Sharp"),
        ("extra-sharp",     "Extra Sharp"),
        ("extra mild",      "Extra Mild"),
        ("extra-mild",      "Extra Mild"),
        ("sharp",           "Sharp"),
        ("mild",            "Mild"),
        ("medium",          "Medium"),
    ],
    # Tier 4: aging length
    [
        ("vintage",         "Vintage"),
        ("aged",            "Aged"),
    ],
    # Tier 5: color / style
    [
        ("smoked",          "Smoked"),
        ("yellow",          "Yellow"),
        ("white",            "White"),
    ],
]
