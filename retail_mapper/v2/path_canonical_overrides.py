"""Manual overrides for canonical path-leaf word-orders + repeat-word allowlist.

Hand-edited. The build_path_rewrite_map.py script consults this first; only
when no manual entry exists does it fall back to FNDDS-anchor → title-plurality
→ alphabetical.

Keys are SORTED-TOKEN SIGNATURES: lowercase the leaf, split on whitespace,
sort alphabetically, rejoin with single spaces. So "Garlic Butter" and
"Butter Garlic" both signature to "butter garlic" — both map to the same
canonical "Garlic Butter".

To extend: add a new entry to MANUAL_LEAF_CANONICAL with the sorted-token
signature on the left and the desired display form on the right.
"""
from __future__ import annotations

# sorted-token signature -> canonical leaf form
MANUAL_LEAF_CANONICAL: dict[str, str] = {
    # Compound flavors / styles — natural English order
    "butter garlic":            "Garlic Butter",
    "cinnamon raisin":          "Cinnamon Raisin",
    "raisin sourdough":         "Raisin Sourdough",
    "cinnamon swirl":           "Cinnamon Swirl",
    "honey wheat":              "Honey Wheat",
    "honey oat":                "Honey Oat",
    "oat honey":                "Honey Oat",
    "honey whole wheat":        "Honey Whole Wheat",
    "multigrain whole wheat":   "Whole Wheat Multigrain",
    "kale spinach":             "Spinach & Kale",
    "creamed kale spinach":     "Creamed Spinach & Kale",
    "pasta sauce":              "Pasta with Sauce",
    "broccoli cheddar":         "Broccoli Cheddar",
    "cheddar broccoli":         "Broccoli Cheddar",
    "bacon cheddar":            "Bacon Cheddar",
    "cheddar bacon":            "Bacon Cheddar",
    "cheddar jalapeno":         "Jalapeño Cheddar",
    "jalapeno cheddar":         "Jalapeño Cheddar",
    "garlic herb":              "Garlic & Herb",
    "herb garlic":              "Garlic & Herb",
    "garlic onion":             "Garlic & Onion",
    "onion garlic":             "Garlic & Onion",
    "garlic parmesan":          "Garlic Parmesan",
    "garlic rosemary":          "Rosemary Garlic",
    "lemon pepper":             "Lemon Pepper",
    "pepper lemon":             "Lemon Pepper",
    "salt pepper":              "Salt & Pepper",
    "salt sea":                 "Sea Salt",
    "salt smoked sea":          "Smoked Sea Salt",
    "honey mustard":            "Honey Mustard",
    "mustard honey":            "Honey Mustard",
    "barbecue honey":           "Honey Barbecue",
    "bbq honey":                "Honey BBQ",
    "buffalo ranch":            "Buffalo Ranch",
    "ranch buffalo":            "Buffalo Ranch",
    "chipotle ranch":           "Chipotle Ranch",
    "ranch chipotle":           "Chipotle Ranch",
    "cilantro lime":            "Cilantro Lime",
    "lime cilantro":            "Cilantro Lime",
    "ginger sesame":            "Ginger Sesame",
    "sesame ginger":            "Ginger Sesame",
    "soy ginger":               "Soy Ginger",
    "ginger soy":               "Soy Ginger",
    "teriyaki sesame":          "Sesame Teriyaki",
    "orange chicken":           "Orange Chicken",
    "chicken teriyaki":         "Teriyaki Chicken",
    "teriyaki chicken":         "Teriyaki Chicken",
    "chicken sesame":           "Sesame Chicken",
    "sesame chicken":           "Sesame Chicken",
    "chicken kung pao":         "Kung Pao Chicken",
    "kung pao chicken":         "Kung Pao Chicken",
    "beef broccoli":            "Beef & Broccoli",
    "broccoli beef":            "Beef & Broccoli",
    "chicken parmesan pasta":   "Chicken Parmesan Pasta",
    "chicken parmesan":         "Chicken Parmesan",
    "alfredo chicken":          "Chicken Alfredo",
    "chicken alfredo":          "Chicken Alfredo",
    "alfredo fettuccine":       "Fettuccine Alfredo",
    "fettuccine alfredo":       "Fettuccine Alfredo",
    "marinara cheese":          "Cheese Marinara",
    "basil tomato":             "Tomato Basil",
    "tomato basil":             "Tomato Basil",
    "mozzarella tomato":        "Tomato Mozzarella",
    "mozzarella basil tomato":  "Tomato Basil Mozzarella",
    "feta spinach":             "Spinach & Feta",
    "feta tomato":              "Tomato & Feta",
    "balsamic strawberry":      "Strawberry Balsamic",
    "blueberry maple":          "Blueberry Maple",
    "buttermilk maple":         "Maple Buttermilk",
    "vanilla cinnamon":         "Cinnamon Vanilla",
    "almond chocolate":         "Chocolate Almond",
    "chocolate hazelnut":       "Chocolate Hazelnut",
    "hazelnut chocolate":       "Chocolate Hazelnut",
    "chocolate peanut butter":  "Chocolate Peanut Butter",
    "butter chocolate peanut":  "Chocolate Peanut Butter",
    "banana chocolate":         "Chocolate Banana",
    "banana strawberry":        "Strawberry Banana",
    "berry mixed":              "Mixed Berry",
    "berry triple":             "Triple Berry",
    "blueberry strawberry":     "Strawberry & Blueberry",
    "apple cinnamon":           "Apple Cinnamon",
    "cinnamon apple":           "Apple Cinnamon",
    "caramel apple":            "Caramel Apple",
    "apple caramel":            "Caramel Apple",
    "pumpkin spice":            "Pumpkin Spice",
    "spice pumpkin":            "Pumpkin Spice",
    "everything seasoning":     "Everything Seasoning",
    "rosemary olive oil":       "Rosemary & Olive Oil",
    "oil olive rosemary":       "Rosemary & Olive Oil",
}

# Real product/flavor names that legitimately repeat a word.
# A leaf segment listed here is NOT flagged as a repeated-word issue.
REPEATED_WORD_ALLOWLIST: set[str] = {
    "Mahi Mahi",
    "Half & Half",
    "Half-and-Half",
    "Camu Camu",
    "Camu Camu Powder",
    "Dan Dan",
    "Dan Dan Noodle",
    "Dan Dan Noodles",
    "Couscous Couscous",
    "Tuna Tuna",
    "Pizza Pizza",
    "Bora Bora",
    "Pop Pop",
    "Tutti Frutti",
    "Bok Bok",
    "Bing Bing",
    "Choco Choco",
    "Chow Chow",
    "Agar Agar",
    "Agar Agar Powder",
    "Half & Half Tea & Lemonade",
    "Half & Half Lemonade Iced Tea",
    "Baby Spinach and Baby Kale Mix",
    "Dan Dan Noodle Bowl",
    "Camu Camu Berry Powder",
    # Any segment containing "& " with two halves where word repeats is OK
    # (handled by allowlist check on full segment string).
}

# Tokens that, by themselves, are common qualifier words. When two leaves differ
# ONLY in the position of one of these tokens, the canonical form leads with
# the qualifier-as-adjective. (E.g., "Spicy" always front-loads.)
LEADING_ADJECTIVES: tuple[str, ...] = (
    "spicy", "smoky", "smoked", "roasted", "toasted", "creamy", "crispy",
    "crunchy", "fluffy", "soft", "hard", "mini", "jumbo", "giant", "petite",
    "classic", "original", "traditional", "authentic", "fresh", "raw",
    "frozen", "refrigerated", "shelf-stable", "instant", "quick", "slow",
    "low-fat", "fat-free", "sugar-free", "gluten-free", "dairy-free",
    "organic", "natural", "premium", "select", "deluxe",
)
