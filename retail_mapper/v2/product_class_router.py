#!/usr/bin/env python3
"""Product class router: force ONE canonical family+type prefix per known product.

Uses (BFC + FNDDS_code + title-keywords) as input signals. Outputs:
  - canonical_family_type_prefix (e.g. 'Meat & Seafood > Poultry > Chicken > Nuggets')
  - any existing modifier segments are preserved as the leaf

This eliminates duplicate paths like:
  - Sushi in Bakery > Rolls vs Meal > Sushi
  - Chicken Nuggets in Frozen > Appetizers vs Meat & Seafood > Poultry vs Pantry
  - Peanut Butter in Dairy > Butter vs Pantry > Nut Butters
"""
from __future__ import annotations

import re

# =====================================================================
# PRODUCT CLASS RULES
# Priority order: BFC > FNDDS_code > Title keyword
# =====================================================================

# BFC → forced family+type prefix
BFC_FORCED: dict[str, str] = {
    'Sushi': 'Meal > Sushi',
    'Cookies & Biscuits': 'Snack > Cookies',
    'Bread & Buns': 'Bakery > Bread',
    'Cereal': 'Pantry > Cereal',
    'Processed Cereal Products': 'Pantry > Cereal',
    'Pasta by Shape & Type': 'Pantry > Pasta',
    'Cake, Cookie & Cupcake Mixes': 'Pantry > Baking Mixes > Cake Mix',
    'Bread & Muffin Mixes': 'Pantry > Baking Mixes > Bread Mix',
    'Cakes, Cupcakes, Snack Cakes': 'Bakery > Cake',
    'Frozen Pizza': 'Frozen > Pizza',
    'Frozen Vegetables': 'Frozen > Vegetables',
    'Frozen Fruit': 'Frozen > Fruit',
    'Frozen Fish & Seafood': 'Frozen > Prepared Seafood',
    'Frozen Dinners & Entrees': 'Frozen > Single Entrees',
    'Ice Cream & Frozen Yogurt': 'Frozen > Ice Cream',
    "Frozen Appetizers & Hors D'oeuvres": 'Frozen > Appetizers',
    'Frozen Bacon, Sausages & Ribs': 'Frozen > Breakfast',
    'Yogurt': 'Dairy > Yogurt',
    'Cheese': 'Dairy > Cheese',
    'Milk': 'Dairy > Milk',
    'Butter & Spread': 'Dairy > Butter',
    'Cream/Cream Substitutes': 'Dairy > Cream > Coffee Creamer',
    'Eggs': 'Dairy > Eggs',
    'Plant Based Milk': 'Beverage > Plant Milk',
    'Soda': 'Beverage > Soda',
    'Tea & Infusions': 'Beverage > Tea',
    'Coffee': 'Beverage > Coffee',
    'Bottled Water': 'Beverage > Water',
    'Energy & Sports Drinks': 'Beverage > Energy Drinks',
    'Bacon': 'Meat & Seafood > Bacon',
    'Sausages, Hotdogs & Brats': 'Meat & Seafood > Sausage',
    'Pepperoni, Salami & Cold Cuts': 'Meat & Seafood > Charcuterie',
    'Chips, Pretzels & Snacks': 'Snack > Chips',
    'Popcorn, Peanuts, Seeds & Related Snacks': 'Snack > Nuts',
    'Candy': 'Snack > Candy',
    'Chocolate': 'Snack > Candy > Chocolate Candy',
    'Snack, Energy & Granola Bars': 'Snack > Bars',
    'Crackers, Crispbreads & Rice Cakes': 'Snack > Crackers',
    'Salad Dressing & Mayonnaise': 'Pantry > Salad Dressings',
    'Sauces': 'Pantry > Sauces & Salsas > Sauce',
    'Spices & Seasonings': 'Pantry > Spices & Seasonings',
    'Cooking Oils': 'Pantry > Oil',
    'Vinegars': 'Pantry > Vinegar',
    'Olives & Capers': 'Pantry > Olives',
    'Pickles, Olives, Peppers & Relishes': 'Pantry > Pickles',
    'Soups': 'Pantry > Soup',
    'Bouillon & Broth': 'Pantry > Bouillon & Broth',
    'Canned Fruit': 'Pantry > Canned Fruit',
    'Canned Vegetables': 'Pantry > Canned Vegetables',
    'Canned & Bottled Beans': 'Pantry > Canned Vegetables > Beans',
    'Sugar & Sweeteners': 'Pantry > Sweeteners',
    'Honey, Jam, Marmalade & Spreads': 'Pantry > Spreads',
    'Tortillas, Wraps & Pita Bread': 'Bakery > Tortillas',
    'Bagels, Muffins, Doughnuts & Pastries': 'Bakery > Pastry',
    'Pies': 'Bakery > Pie',
    'Vegetables  Prepared/Processed': 'Pantry > Canned Vegetables',
    'Vegetable and Lentil Mixes': 'Pantry > Canned Vegetables > Beans',
}

# Title keyword → forced family+type prefix (used when BFC alone is ambiguous)
TITLE_FORCED: list[tuple[re.Pattern, str]] = [
    # Sushi takes priority over generic ROLL
    (re.compile(r"\b(sushi|sashimi|nigiri|maki|temaki)\b", re.I), 'Meal > Sushi'),
    (re.compile(r"\b(?:california|alabama|florida|spicy tuna|salmon avocado|philadelphia|dragon|rainbow)\s+roll(?:s)?\b", re.I), 'Meal > Sushi'),

    # Chicken nuggets — multiple BFCs send these to wrong places
    (re.compile(r"\bchicken\s+nugget(s)?\b", re.I), 'Meat & Seafood > Poultry > Chicken > Nuggets'),
    (re.compile(r"\bdino(saur)?\s*(?:shaped\s*)?(?:chicken\s*)?nugget", re.I), 'Meat & Seafood > Poultry > Chicken > Nuggets'),

    # Nut butters
    (re.compile(r"\b(?:creamy|crunchy|smooth)?\s*peanut\s*butter\b(?!.*sandwich)", re.I), 'Pantry > Nut Butters > Peanut Butter'),
    (re.compile(r"\balmond\s*butter\b(?!.*sandwich)", re.I), 'Pantry > Nut Butters > Almond Butter'),
    (re.compile(r"\bcashew\s*butter\b(?!.*sandwich)", re.I), 'Pantry > Nut Butters > Cashew Butter'),
    (re.compile(r"\bsunflower(?:\s+seed)?\s*butter\b(?!.*sandwich)", re.I), 'Pantry > Nut Butters > Sunflower Seed Butter'),
    (re.compile(r"\bhazelnut\s*butter\b(?!.*sandwich)", re.I), 'Pantry > Nut Butters > Hazelnut Butter'),
    (re.compile(r"\btahini\b(?!.*sandwich)", re.I), 'Pantry > Nut Butters > Tahini'),

    # Meatloaf
    (re.compile(r"\bmeat\s*loaf\b", re.I), 'Frozen > Single Entrees > Meatloaf'),

    # Cookie Dough (raw)
    (re.compile(r"\b(?:refrigerated|raw|edible)\s*cookie\s*dough\b", re.I), 'Bakery > Cookie Dough'),
    (re.compile(r"\bcookie\s*dough\b(?!.*ice cream|.*cookies?\b)", re.I), 'Bakery > Cookie Dough'),

    # Jerky
    (re.compile(r"\bbeef\s*jerky\b", re.I), 'Snack > Jerky > Beef'),
    (re.compile(r"\bturkey\s*jerky\b", re.I), 'Snack > Jerky > Turkey'),
    (re.compile(r"\bpork\s*jerky\b", re.I), 'Snack > Jerky > Pork'),
    (re.compile(r"\b(?:slim jim|jack link|chomps|krave|country archer|oberto|epic provisions|mission meats|stryve|biltong)\b", re.I), 'Snack > Jerky > Beef'),

    # Corn dogs
    (re.compile(r"\bcorn\s*dogs?\b", re.I), 'Frozen > Appetizers > Corn Dog'),

    # Granola bars (nut bars are different)
    (re.compile(r"\bgranola\s*bars?\b", re.I), 'Snack > Bars > Granola'),
    (re.compile(r"\bprotein\s*bars?\b", re.I), 'Snack > Bars > Protein'),
    (re.compile(r"\benergy\s*bars?\b", re.I), 'Snack > Bars > Energy'),

    # Pop products
    (re.compile(r"\bfrozen\s*pops?\b|\bfruit\s*pops?\b|\bsmoothie\s*pops?\b|\bkombucha\s*pops?\b|\bpickle\s*pops?\b", re.I), 'Frozen > Pops'),

    # Ice cream specific products
    (re.compile(r"\bice\s*cream\s*sandwich(es)?\b", re.I), 'Frozen > Ice Cream > Sandwich'),
    (re.compile(r"\bice\s*cream\s*bars?\b", re.I), 'Frozen > Ice Cream > Bar'),
    (re.compile(r"\bice\s*cream\s*cones?\b", re.I), 'Frozen > Ice Cream > Cone'),

    # Bread types
    (re.compile(r"\bsourdough\s*bread\b|\bsourdough(?:\s+loaf)?\b", re.I), 'Bakery > Bread > Sourdough'),
    (re.compile(r"\bbaguette(s)?\b", re.I), 'Bakery > Bread > Baguette'),
    (re.compile(r"\brye\s*bread\b", re.I), 'Bakery > Bread > Rye'),
    (re.compile(r"\bpita\s*bread\b", re.I), 'Bakery > Bread > Pita'),

    # Doughnuts
    (re.compile(r"\b(?:doughnuts?|donuts?)\b", re.I), 'Bakery > Doughnuts'),

    # Specific cookies
    (re.compile(r"\bmacarons?\b", re.I), 'Snack > Cookies > Macarons'),
    (re.compile(r"\bmadeleines?\b", re.I), 'Snack > Cookies > Madeleines'),
    (re.compile(r"\bginger\s*snaps?\b", re.I), 'Snack > Cookies > Ginger Snap'),
    (re.compile(r"\boatmeal\s*(?:raisin\s*)?cookie", re.I), 'Snack > Cookies > Oatmeal'),

    # Pound cake
    (re.compile(r"\bpound\s*cakes?\b", re.I), 'Bakery > Cake > Pound Cake'),
    (re.compile(r"\bbundt\s*cakes?\b", re.I), 'Bakery > Cake > Bundt Cake'),
    (re.compile(r"\bcheesecakes?\b", re.I), 'Bakery > Cake > Cheesecake'),

    # Croissants
    (re.compile(r"\bcroissants?\b", re.I), 'Bakery > Pastry > Croissants'),

    # Tortillas/wraps
    (re.compile(r"\btortillas?\b", re.I), 'Bakery > Tortillas'),

    # Mac & cheese
    (re.compile(r"\bmac(?:aroni)?\s*(?:and|&|n\'?)\s*cheese\b", re.I), 'Meal > Pasta Dishes > Mac & Cheese'),

    # Sandwiches with specific identifiers
    (re.compile(r"\bbreakfast\s*sandwich(es)?\b", re.I), 'Frozen > Breakfast > Breakfast Sandwich'),

    # Yogurt sub-types
    (re.compile(r"\bgreek\s*yogurt\b", re.I), 'Dairy > Yogurt > Greek'),
    (re.compile(r"\bskyr\b", re.I), 'Dairy > Yogurt > Skyr'),
    (re.compile(r"\bkefir\b", re.I), 'Dairy > Yogurt > Kefir'),

    # Cheese sub-types
    (re.compile(r"\bcheddar\s*cheese\b|\b(?:sharp|mild|extra sharp|medium)\s*cheddar\b", re.I), 'Dairy > Cheese > Cheddar'),
    (re.compile(r"\bmozzarella\b", re.I), 'Dairy > Cheese > Mozzarella'),
    (re.compile(r"\bparmesan\b", re.I), 'Dairy > Cheese > Parmesan'),
    (re.compile(r"\bricotta\b", re.I), 'Dairy > Cheese > Ricotta'),
    (re.compile(r"\bcottage\s*cheese\b", re.I), 'Dairy > Cheese > Cottage'),
    (re.compile(r"\bcream\s*cheese\b", re.I), 'Dairy > Cheese > Cream Cheese'),
    (re.compile(r"\bgoat\s*cheese\b", re.I), 'Dairy > Cheese > Goat Cheese'),
    (re.compile(r"\bblue\s*cheese\b", re.I), 'Dairy > Cheese > Blue Cheese'),
    (re.compile(r"\bswiss\s*cheese\b", re.I), 'Dairy > Cheese > Swiss'),
    (re.compile(r"\bfeta\b", re.I), 'Dairy > Cheese > Feta'),
    (re.compile(r"\bprovolone\b", re.I), 'Dairy > Cheese > Provolone'),
    (re.compile(r"\bmonterey\s*jack\b", re.I), 'Dairy > Cheese > Monterey Jack'),
    (re.compile(r"\bpepper\s*jack\b", re.I), 'Dairy > Cheese > Pepper Jack'),

    # Coffee creamer
    (re.compile(r"\bcoffee\s*creamer\b", re.I), 'Dairy > Cream > Coffee Creamer'),

    # Hot dogs
    (re.compile(r"\bhot\s*dogs?\b|\bfranks?\b(?!\s+furt)", re.I), 'Meat & Seafood > Hot Dogs'),

    # Pepperoni (charcuterie not pizza)
    (re.compile(r"\bpepperoni\b(?!.*pizza)", re.I), 'Meat & Seafood > Charcuterie > Pepperoni'),

    # Pinto Beans, Black Beans, etc
    (re.compile(r"\bpinto\s*beans?\b", re.I), 'Pantry > Canned Vegetables > Beans > Pinto'),
    (re.compile(r"\bblack\s*beans?\b", re.I), 'Pantry > Canned Vegetables > Beans > Black'),
    (re.compile(r"\bkidney\s*beans?\b", re.I), 'Pantry > Canned Vegetables > Beans > Kidney'),
    (re.compile(r"\bgarbanzo\s*beans?\b|\bchickpeas?\b", re.I), 'Pantry > Canned Vegetables > Beans > Garbanzo'),
    (re.compile(r"\bgreat\s*northern\s*beans?\b", re.I), 'Pantry > Canned Vegetables > Beans > Great Northern'),
    (re.compile(r"\blima\s*beans?\b", re.I), 'Pantry > Canned Vegetables > Beans > Lima'),
    (re.compile(r"\bnavy\s*beans?\b", re.I), 'Pantry > Canned Vegetables > Beans > Navy'),
    (re.compile(r"\bcannellini\s*beans?\b", re.I), 'Pantry > Canned Vegetables > Beans > Cannellini'),

    # Tomato Sauce vs Tomatoes
    (re.compile(r"\btomato\s*sauce\b", re.I), 'Pantry > Sauces & Salsas > Tomato Sauce'),
    (re.compile(r"\btomato\s*paste\b", re.I), 'Pantry > Canned Vegetables > Tomato Paste'),

    # Applesauce
    (re.compile(r"\bapplesauce\b|\bapple\s*sauce\b", re.I), 'Pantry > Canned Fruit > Applesauce'),
]


def route_product(bfc: str, fndds_desc: str, title: str) -> str | None:
    """Return forced family+type prefix, or None if no rule matches.
    Title rules take priority over BFC (more specific signal)."""
    title_str = title or ''
    for rx, prefix in TITLE_FORCED:
        if rx.search(title_str):
            return prefix
    bfc = (bfc or '').strip()
    if bfc in BFC_FORCED:
        return BFC_FORCED[bfc]
    return None
