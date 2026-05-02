#!/usr/bin/env python3
"""Unified path canonicalizer.

Single deterministic pipeline that produces consistent top-down paths:
  family > type > variant > flavor > form > processing > unknown > claims

Key features:
  - Comprehensive lexicons (claims, flavors, forms, type-parents)
  - Synonym normalization (Zero Sugar → Sugar Free, Donut → Doughnut, etc.)
  - Singular/plural-aware type-echo elimination (Mixes after Drink Mix → drop)
  - Bucket-based reassembly with fixed top-down order
  - Case-insensitive dedupe

Usage:
    from path_canonicalizer import canonicalize_path
    new_cp = canonicalize_path(['Bakery', 'Pastry', 'Croissants', 'Croissant'])
    # → 'Bakery > Pastry > Croissants'
"""
from __future__ import annotations

import re
from typing import Iterable

# =====================================================================
# LEXICONS (single source of truth)
# =====================================================================

# Synonym normalization: case-insensitive lookup → canonical form
SYNONYM_MAP: dict[str, str] = {
    # Sugar/sweetener claims
    'zero sugar': 'Sugar Free', 'no sugar added': 'Sugar Free',
    'zero calorie': 'Sugar Free', 'sugarfree': 'Sugar Free',
    '0 sugar': 'Sugar Free', '0g sugar': 'Sugar Free',
    'reduced sugar': 'Reduced Sugar',  # keep distinct: still has some sugar
    # Fat claims
    'lowfat': 'Low Fat', 'low-fat': 'Low Fat',
    'skim': 'Fat Free', 'nonfat': 'Fat Free', 'non fat': 'Fat Free',
    'non-fat': 'Fat Free', 'fatfree': 'Fat Free', 'no fat': 'Fat Free',
    'reduced-fat': 'Reduced Fat',
    # Other claim synonyms
    'lite': 'Light',
    'plant-based': 'Plant Based', 'plantbased': 'Plant Based',
    'gluten-free': 'Gluten Free', 'glutenfree': 'Gluten Free', 'no gluten': 'Gluten Free',
    'dairy-free': 'Dairy Free', 'dairyfree': 'Dairy Free', 'non dairy': 'Dairy Free',
    'non-dairy': 'Dairy Free', 'nondairy': 'Dairy Free',
    'lactose-free': 'Lactose Free', 'no lactose': 'Lactose Free',
    'caffeine-free': 'Caffeine Free', 'caffeinefree': 'Caffeine Free',
    'decaffeinated': 'Caffeine Free', 'decaf': 'Caffeine Free', 'no caffeine': 'Caffeine Free',
    'no hfcs': 'No HFCS', 'no high fructose corn syrup': 'No HFCS',
    'grass-fed': 'Grass Fed', 'grassfed': 'Grass Fed',
    'free-range': 'Free Range', 'freerange': 'Free Range',
    'cage-free': 'Cage Free', 'cagefree': 'Cage Free',
    'wild-caught': 'Wild Caught', 'wildcaught': 'Wild Caught',
    'fair-trade': 'Fair Trade', 'fairtrade': 'Fair Trade',
    'all natural': 'Natural', '100% natural': 'Natural', '100 natural': 'Natural',
    'all-natural': 'Natural',
    'whole-wheat': 'Whole Wheat', '100% whole wheat': 'Whole Wheat',
    '100 whole wheat': 'Whole Wheat', '100 percent whole wheat': 'Whole Wheat',
    'whole-grain': 'Whole Grain', '100% whole grain': 'Whole Grain',
    '100 whole grain': 'Whole Grain', 'multigrain': 'Multi Grain',
    'multi-grain': 'Multi Grain',
    'non-gmo': 'Non GMO', 'non gmo': 'Non GMO',
    'old-fashioned': 'Old Fashioned', 'oldfashioned': 'Old Fashioned',
    # Spelling/format
    'donut': 'Doughnut', 'donuts': 'Doughnuts',
    'yoghurt': 'Yogurt', 'yoghurts': 'Yogurts',
    'sour dough': 'Sourdough', 'sour-dough': 'Sourdough',
    'butter milk': 'Buttermilk', 'butter-milk': 'Buttermilk',
    'pop corn': 'Popcorn', 'pop-corn': 'Popcorn',
    'meat loaf': 'Meatloaf', 'meat-loaf': 'Meatloaf',
    'cheese cake': 'Cheesecake', 'cheese-cake': 'Cheesecake',
    'pan cake': 'Pancake', 'pan-cake': 'Pancake',
    # BBQ
    'barbecue': 'BBQ', 'barbeque': 'BBQ', 'bar-b-que': 'BBQ',
    # Synonyms in flavor names
    'cookies and cream': 'Cookies & Cream',
    "cookies n cream": 'Cookies & Cream',
    "cookies 'n cream": 'Cookies & Cream',
    'salt and vinegar': 'Salt & Vinegar',
    'salt n vinegar': 'Salt & Vinegar',
    'mac and cheese': 'Mac & Cheese',
    'macaroni and cheese': 'Mac & Cheese',
    'macaroni & cheese': 'Mac & Cheese',
    'sour cream and onion': 'Sour Cream & Onion',
    'peanut butter and jelly': 'PB&J',
    'pb and j': 'PB&J',
    'peanut butter & jelly': 'PB&J',
    # Form synonyms
    'powder': 'Powdered',
    'powdered milk': 'Powdered',  # context-dependent
}

# Claims (always go at LEAF END of path, sorted alphabetical)
CLAIM_WORDS: frozenset[str] = frozenset({
    'organic', 'natural', 'plant based', 'gluten free', 'dairy free',
    'sugar free', 'fat free', 'low fat', 'reduced fat', 'low sodium',
    'no salt added', 'unsweetened', 'sweetened', 'reduced sugar',
    'low calorie', 'reduced calorie', 'zero calorie', 'diet', 'light',
    'fortified', 'probiotic', 'grass fed', 'free range', 'cage free',
    'wild caught', 'fair trade', 'kosher', 'halal', 'vegan',
    'keto', 'keto friendly', 'paleo', 'whole grain', 'multi grain',
    'whole wheat', 'non gmo', 'no preservatives', 'no artificial flavors',
    'high protein', 'high fiber', 'caffeine free', 'low carb',
    'no hfcs', 'lactose free', 'salted', 'unsalted', 'no fat',
    'no sodium', 'low sugar', 'no salt', 'gourmet', 'imported', 'domestic',
    'reduced sodium', 'less sodium', 'enriched',
})

# Flavors (named flavors)
FLAVOR_WORDS: frozenset[str] = frozenset({
    'strawberry', 'blueberry', 'raspberry', 'blackberry', 'cherry',
    'black cherry', 'wild cherry', 'sour cherry', 'maraschino cherry',
    'vanilla', 'french vanilla', 'vanilla bean', 'tahitian vanilla',
    'chocolate', 'dark chocolate', 'milk chocolate', 'white chocolate',
    'banana', 'peach', 'pineapple', 'mango', 'coconut', 'apple', 'pear', 'plum',
    'lemon', 'lime', 'orange', 'grape', 'pomegranate', 'watermelon', 'melon',
    'cantaloupe', 'honeydew', 'apricot', 'kiwi', 'papaya', 'passion fruit',
    'pumpkin', 'pumpkin spice', 'cinnamon', 'caramel', 'salted caramel',
    'sea salt caramel', 'maple', 'maple brown sugar', 'brown sugar',
    'honey', 'honey mustard', 'mint', 'peppermint', 'spearmint', 'wintergreen',
    'almond', 'hazelnut', 'pistachio', 'walnut', 'pecan', 'cashew', 'macadamia',
    'peanut butter', 'almond butter',  # also TYPES — context disambiguates
    'cookies and cream', 'cookies & cream', 'cookie dough', 'cookies',
    'birthday cake', 'cheesecake', 'pumpkin pie', 'apple pie', 'pecan pie',
    'key lime', 'strawberry banana', 'strawberry kiwi', 'strawberry cheesecake',
    'mixed berry', 'wild berry', 'fruit punch', 'tropical punch',
    'pink lemonade', 'strawberry lemonade', 'cherry limeade',
    'sweet tea', 'iced tea', 'green tea', 'black tea', 'chai',
    'toasted coconut', 'coconut lime',
    'rocky road', 'neapolitan', 'tutti frutti',
    'root beer', 'cola', 'cream soda', 'ginger ale', 'ginger beer',
    'cranberry', 'acai', 'guava', 'lychee', 'tangerine', 'grapefruit',
    'sour apple', 'sour cherry', 'sour watermelon',
    'goldenberry', 'plain', 'original', 'unflavored',
    'cinnamon roll', 'cinnamon sugar',
    'hot', 'medium', 'mild', 'spicy', 'sweet', 'sour', 'tangy', 'spicy sweet',
    'buffalo', 'ranch', 'honey bbq', 'jalapeno',
    'coffee', 'mocha', 'espresso', 'latte', 'cappuccino', 'brown sugar latte',
    'fudge', 'caramel apple', 'rosemary', 'thyme', 'rosemary & thyme',
    'turmeric', 'ginger', 'lavender',
    # Bean flavors / variants in pet/produce contexts
    'red velvet', 'german chocolate', "devil's food", 'yellow', 'white',
    'marble', 'angel food', 'sponge', 'pound', 'funfetti', 'confetti',
    'chocolate chip', 'oatmeal', 'oatmeal raisin', 'oatmeal chocolate chip',
    'snickerdoodle', 'gingerbread', 'ginger snap', 'shortbread', 'butter',
    'sugar', 'sugar cookie',
})

# Form/texture/cut/processing words
FORM_WORDS: frozenset[str] = frozenset({
    'sliced', 'shredded', 'grated', 'cubed', 'whole', 'powdered', 'powder',
    'liquid', 'dry mix', 'crumbled', 'chopped', 'diced', 'crushed',
    'puree', 'strips', 'sticks', 'pearls', 'whipped', 'spreadable',
    'melted', 'frozen', 'refrigerated', 'shelf stable', 'concentrate',
    'concentrated', 'condensed', 'evaporated', 'fresh', 'dried',
    'roasted', 'toasted', 'baked', 'fried', 'grilled', 'breaded',
    'battered', 'smoked', 'cured', 'aged', 'pickled', 'fermented',
    'instant', 'ready to drink', 'ready to eat', 'ready-to-eat',
    'pouch', 'cup', 'snack pack', 'bag', 'jar', 'can', 'box', 'bottle',
    'thin', 'thick', 'crispy', 'crunchy', 'chewy', 'soft', 'soft baked',
    'mini', 'jumbo', 'large', 'small', 'extra large',
    'kettle cooked', 'wavy', 'rippled', 'flat', 'round',
    'no stir', 'stirring',
})

PROCESSING_WORDS: frozenset[str] = frozenset({
    'frozen', 'refrigerated', 'shelf stable', 'fresh',
    'roasted', 'baked', 'fried', 'grilled', 'smoked',
    'powdered', 'liquid', 'concentrate', 'concentrated',
    'condensed', 'evaporated', 'instant',
})

# Note: FORM and PROCESSING overlap — that's intentional. classify_segment
# disambiguates by context.

# All known TYPE words. This is built dynamically at runtime from
# product_identity_fixed values + manual additions.
DEFAULT_TYPE_PARENTS: frozenset[str] = frozenset({
    # Bakery
    'bread', 'sourdough bread', 'sourdough', 'whole wheat bread',
    'baguette', 'rye bread', 'pita bread', 'focaccia', 'ciabatta',
    'naan', 'flatbread', 'tortilla', 'tortillas', 'wrap', 'wraps',
    'taco shell', 'taco shells', 'tostada', 'tostadas',
    'bagel', 'bagels', 'english muffin', 'english muffins',
    'roll', 'rolls', 'bun', 'buns', 'hot dog bun', 'hot dog buns',
    'hamburger bun', 'hamburger buns', 'dinner roll', 'dinner rolls',
    'crescent roll', 'crescent rolls',
    'cookie', 'cookies', 'cookie dough', 'cookie kit', 'cookie kits',
    'macaron', 'macarons', 'madeleines', 'biscotti', 'biscuit', 'biscuits',
    'wafer', 'wafers', 'shortbread',
    'cake', 'cakes', 'cupcake', 'cupcakes', 'pound cake', 'bundt cake',
    'cheesecake', 'sponge cake', 'angel food cake', 'layer cake',
    'snack cake', 'snack cakes', 'coffee cake',
    'pie', 'pies', 'pie crust', 'tart', 'tarts',
    'doughnut', 'doughnuts', 'donut hole', 'donut holes',
    'muffin', 'muffins', 'scone', 'scones', 'brownie', 'brownies',
    'pastry', 'pastries', 'croissant', 'croissants', 'danish', 'danishes',
    'puff pastry', 'turnover', 'turnovers', 'eclair', 'eclairs',
    'cinnamon roll', 'cinnamon rolls',
    'pizza', 'pizza dough', 'pizza crust', 'breadstick', 'breadsticks',
    'crouton', 'croutons', 'cracker', 'crackers',
    # Dairy
    'milk', 'almond milk', 'soy milk', 'oat milk', 'coconut milk',
    'cashew milk', 'rice milk', 'hazelnut milk', 'macadamia milk',
    'plant milk', 'flavored milk', 'chocolate milk', 'strawberry milk',
    'cheese', 'cheddar', 'mozzarella', 'parmesan', 'provolone', 'feta',
    'ricotta', 'cottage cheese', 'cream cheese', 'goat cheese', 'blue cheese',
    'string cheese', 'swiss', 'gouda', 'asiago', 'burrata', 'manchego',
    'romano', 'havarti', 'gruyere', 'muenster', 'mascarpone', 'monterey jack',
    'pepper jack', 'colby jack', 'cheddar jack', 'mexican blend', 'italian blend',
    'butter', 'salted butter', 'unsalted butter', 'ghee', 'margarine',
    'cream', 'sour cream', 'heavy cream', 'whipping cream', 'half and half',
    'coffee creamer', 'creamer',
    'yogurt', 'yogurts', 'greek yogurt', 'skyr', 'kefir', 'drinkable yogurt',
    'frozen yogurt',
    'pudding', 'puddings', 'custard', 'flan', 'mousse',
    'eggs', 'egg',
    # Meat & Seafood
    'beef', 'pork', 'chicken', 'turkey', 'duck', 'lamb', 'veal', 'goat',
    'bacon', 'ham', 'sausage', 'sausages', 'pepperoni', 'salami',
    'hot dog', 'hot dogs', 'meatball', 'meatballs', 'meatloaf',
    'jerky', 'beef jerky', 'turkey jerky', 'pork jerky',
    'salmon', 'tuna', 'cod', 'tilapia', 'shrimp', 'crab', 'lobster',
    'scallops', 'octopus', 'calamari', 'mahi mahi', 'pollock',
    'fish', 'seafood', 'fish stick', 'fish sticks', 'fish fillet', 'fish fillets',
    'corn dog', 'corn dogs', 'chicken nugget', 'chicken nuggets', 'nuggets',
    'tofu', 'plant based meat', 'meat alternative',
    'patties', 'patty', 'beef patties', 'beef patty', 'veggie burger', 'veggie burgers',
    # Snack
    'candy', 'gummy candy', 'hard candy', 'chocolate candy', 'caramel',
    'lollipop', 'lollipops', 'mints', 'gum', 'bubble gum', 'fruit snack', 'fruit snacks',
    'jelly bean', 'jelly beans', 'marshmallow', 'marshmallows',
    'chip', 'chips', 'potato chips', 'tortilla chips', 'corn chips',
    'pretzel', 'pretzels', 'popcorn', 'puff', 'puffs', 'cheese puff', 'cheese puffs',
    'rice cake', 'rice cakes', 'cheese crisp', 'cheese crisps',
    'bar', 'bars', 'protein bar', 'protein bars', 'granola bar', 'granola bars',
    'energy bar', 'energy bars', 'cereal bar', 'cereal bars', 'nutrition bar',
    'snack bar', 'snack bars',
    'granola', 'trail mix', 'snack mix', 'pork rinds', 'cheese cracker',
    'nut', 'nuts', 'almonds', 'peanuts', 'cashews', 'pistachios', 'walnuts',
    'pecans', 'macadamia nuts', 'mixed nuts',
    # Pantry
    'pasta', 'spaghetti', 'penne', 'macaroni', 'rotini', 'rigatoni',
    'linguine', 'fettuccine', 'lasagna', 'noodle', 'noodles',
    'rice', 'jasmine rice', 'basmati rice', 'brown rice', 'white rice',
    'long grain rice', 'short grain rice', 'wild rice',
    'oats', 'oatmeal', 'instant oats', 'quinoa', 'barley',
    'cereal', 'flake', 'flakes', 'corn flake', 'corn flakes',
    'soup', 'soups', 'chili', 'broth', 'bouillon',
    'sauce', 'sauces', 'pasta sauce', 'tomato sauce', 'hot sauce', 'salsa',
    'ketchup', 'mustard', 'mayonnaise', 'salad dressing', 'salad dressings',
    'vinegar', 'oil', 'olive oil', 'coconut oil', 'avocado oil', 'sesame oil',
    'vegetable oil', 'canola oil',
    'spice', 'spices', 'seasoning', 'seasonings', 'salt', 'pepper',
    'cinnamon', 'paprika', 'oregano', 'basil', 'thyme', 'rosemary',
    'sweetener', 'sweeteners', 'sugar', 'honey', 'maple syrup',
    'jam', 'jelly', 'preserve', 'preserves', 'spread', 'spreads',
    'nut butter', 'nut butters', 'peanut butter', 'almond butter',
    'cashew butter', 'sunflower seed butter', 'hazelnut butter', 'tahini',
    'pickle', 'pickles', 'olive', 'olives', 'relish',
    'beans', 'pinto', 'black bean', 'black beans', 'kidney beans',
    'navy beans', 'lima beans', 'garbanzo beans', 'cannellini beans',
    'baking mix', 'baking mixes', 'cake mix', 'cookie mix', 'brownie mix',
    'muffin mix', 'pancake mix', 'waffle mix', 'biscuit mix', 'bread mix',
    'tortilla mix', 'pie crust mix', 'cornbread mix',
    'baking ingredients', 'flour', 'baking powder', 'baking soda',
    'cocoa powder', 'cake flour', 'pastry flour',
    'gravy', 'gravy mix',
    # Beverage
    'soda', 'cola', 'root beer', 'ginger ale',
    'water', 'sparkling water', 'tonic water',
    'tea', 'iced tea', 'green tea', 'black tea', 'herbal tea',
    'coffee', 'cold brew', 'espresso',
    'juice', 'orange juice', 'apple juice', 'cranberry juice',
    'lemonade', 'limeade',
    'energy drink', 'energy drinks', 'sports drink', 'sports drinks',
    'protein drink', 'protein drinks', 'protein shake', 'kombucha',
    'smoothie', 'smoothies', 'shake', 'mixes', 'mix', 'drink mix',
    'wellness shot', 'wellness shots', 'cocktail mixer', 'cocktail mixers',
    # Frozen
    'ice cream', 'frozen yogurt', 'sorbet', 'gelato', 'sherbet',
    'ice cream sandwich', 'ice cream bar',
    'pizza', 'pizzas',
    'frozen entree', 'frozen entrees', 'tv dinner', 'tv dinners',
    'frozen dinner', 'frozen dinners', 'single entree', 'single entrees',
    'appetizer', 'appetizers', 'frozen appetizer',
    'breakfast sandwich', 'breakfast sandwiches', 'burrito', 'burritos',
    'frozen pop', 'frozen pops', 'pops', 'fruit pop', 'fruit pops',
    'pierogie', 'pierogies', 'dumpling', 'dumplings', 'pot sticker', 'pot stickers',
    # Produce
    'fruit', 'vegetable', 'vegetables', 'salad', 'salads',
    # Meal
    'sandwich', 'sandwiches', 'wrap', 'wraps', 'sushi', 'taco', 'tacos',
    'enchilada', 'enchiladas', 'tamale', 'tamales', 'empanada', 'empanadas',
    'meal starter', 'meal starters', 'lunch kit', 'lunch kits',
    'composite dish', 'composite dishes', 'pasta dish', 'pasta dishes',
    'rice dish', 'rice dishes', 'salad kit', 'salad kits',
})

# Words that SHOULD be a 2nd-level family-anchor — when we see them as
# segment 2, they're a real family-sub-category, not a flavor.
FAMILY_SUB_CATEGORIES: frozenset[str] = frozenset({
    'cookies', 'cake', 'cake mix', 'cookie mix', 'pasta', 'rice', 'cereal',
    'soup', 'sauces & salsas', 'spices & seasonings', 'oil', 'vinegar',
    'olives', 'pickles', 'baking mixes', 'baking ingredients', 'sweeteners',
    'spreads', 'nut butters', 'beans', 'canned vegetables', 'canned fruit',
    'side dish mixes', 'coating & breading', 'gravy',
    'milk', 'cheese', 'yogurt', 'butter', 'cream', 'pudding', 'eggs',
    'flavored milk', 'mousse', 'sour cream',
    'bread', 'cake', 'cookies', 'pastry', 'pies', 'tortillas', 'rolls',
    'buns', 'bagels', 'doughnuts', 'muffins', 'brownies', 'flatbread',
    'breadsticks', 'biscotti', 'pizza crust', 'cookie dough', 'cookie kits',
    'savory pastries', 'crackers', 'biscuits',
    'beef', 'pork', 'chicken', 'turkey', 'lamb', 'veal', 'goat', 'duck',
    'poultry', 'bacon', 'ham', 'sausage', 'pepperoni', 'salami', 'charcuterie',
    'deli', 'meat', 'meatballs', 'meat alternatives', 'tofu', 'patties & burgers',
    'hot dogs', 'jerky', 'seafood', 'fish', 'shrimp', 'salmon', 'tuna', 'crab',
    'candy', 'chocolate candy', 'cookies', 'crackers', 'chips', 'pretzels',
    'popcorn', 'nuts', 'bars', 'jerky', 'fruit snacks', 'puffs', 'mixes',
    'snack mix', 'trail mix', 'gum', 'dried fruit', 'sticks', 'rice cakes',
    'cheese crisps', 'pork rinds', 'snacks',
    'soda', 'water', 'sparkling water', 'tea', 'coffee', 'juice', 'lemonade',
    'energy drinks', 'sports drinks', 'protein drinks', 'plant milk',
    'kombucha', 'smoothies', 'mixes', 'fruit drinks', 'functional drinks',
    'wellness shots', 'mixers',
    'ice cream', 'frozen yogurt', 'sorbet', 'pizza', 'single entrees',
    'breakfast', 'appetizers', 'desserts', 'fruit', 'vegetables',
    'prepared seafood', 'frozen pops', 'pops', 'patties & burgers',
    'fruit', 'vegetables', 'salad mixes', 'salad kits', 'herbs',
    'salads', 'pasta dishes', 'sandwiches', 'pizza', 'meal starters',
    'lunch kits', 'composite dishes', 'tacos', 'wraps', 'sushi',
    'baby food', 'fruit snacks', 'fortifiers',
})


# =====================================================================
# PLURALIZATION HELPERS
# =====================================================================

# Irregular plurals
IRREGULAR_PLURALS: dict[str, str] = {
    'children': 'child', 'feet': 'foot', 'teeth': 'tooth', 'mice': 'mouse',
    'leaves': 'leaf', 'loaves': 'loaf', 'knives': 'knife', 'wives': 'wife',
    'lives': 'life', 'wolves': 'wolf', 'patties': 'patty',
    'cookies': 'cookie', 'macarons': 'macaron', 'biscotti': 'biscotti',
    'tortillas': 'tortilla',
    # Don't normalize: tomatoes, potatoes (they ARE the plural form retail uses)
}


def normalize_plural(word: str) -> str:
    """Return the singular stem of word. Conservative: only obvious suffixes."""
    if not word: return word
    w = word.lower().strip()
    if w in IRREGULAR_PLURALS:
        return IRREGULAR_PLURALS[w]
    # Multi-word: pluralize/singularize last word only
    if ' ' in w:
        parts = w.rsplit(' ', 1)
        return parts[0] + ' ' + normalize_plural(parts[1])
    # Suffix-based (conservative: only -s and -es when stem looks valid)
    if w.endswith('ies') and len(w) > 4:
        return w[:-3] + 'y'
    if w.endswith('xes') or w.endswith('ches') or w.endswith('shes') or w.endswith('sses'):
        return w[:-2]
    if w.endswith('es') and len(w) > 3 and w[-3] in 'sxz':
        return w[:-2]
    if w.endswith('s') and not w.endswith('ss') and len(w) > 3:
        return w[:-1]
    return w


def equivalent_words(a: str, b: str) -> bool:
    """Check if two words are equivalent (plural/singular form of same root)."""
    if not a or not b: return False
    if a.lower() == b.lower(): return True
    return normalize_plural(a) == normalize_plural(b)


# =====================================================================
# SEGMENT-LEVEL HELPERS
# =====================================================================

def title_case(s: str) -> str:
    """Convert snake_case_or_words to Title Case Words."""
    if not s: return s
    cleaned = s.replace('_', ' ').strip()
    # Lowercase certain conjunctions
    parts = cleaned.split()
    out = []
    for i, w in enumerate(parts):
        if i > 0 and w.lower() in {'and', 'or', 'of', 'with', 'in', 'on', 'a', 'an', 'the', 'for', 'to'}:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower() if len(w) > 1 else w.upper())
    return ' '.join(out)


def apply_synonym(seg: str) -> str:
    """Apply SYNONYM_MAP to segment (case-insensitive lookup)."""
    if not seg: return seg
    canonical = SYNONYM_MAP.get(seg.lower().strip())
    return canonical if canonical else seg


def is_claim(seg: str) -> bool:
    return seg.lower().strip() in CLAIM_WORDS


def is_flavor(seg: str) -> bool:
    return seg.lower().strip() in FLAVOR_WORDS


def is_form(seg: str) -> bool:
    s = seg.lower().strip()
    return s in FORM_WORDS or s in PROCESSING_WORDS


def is_type(seg: str) -> bool:
    s = seg.lower().strip()
    return s in DEFAULT_TYPE_PARENTS or s in FAMILY_SUB_CATEGORIES


# =====================================================================
# TYPE-ECHO ELIMINATION
# =====================================================================

def strip_type_echo(segs: list[str]) -> list[str]:
    """Remove segments that are singular/plural duplicates of another type
    segment (any direction). Drops the LESS specific (shorter / single-word)
    segment when both exist.

    Examples:
      ['Bakery','Pastry','Croissants','Croissant'] → ['Bakery','Pastry','Croissants']
      ['Beverage','Drink Mix','Mixes','Orange'] → ['Beverage','Drink Mix','Orange']
      ['Pantry','Mixes','Drink Mix','Orange'] → ['Pantry','Drink Mix','Orange']
      ['Snack','Bars','Granola Bars','Crispy'] → ['Snack','Granola Bars','Crispy']
      ['Bakery','Cake','Pound Cake','Lemon'] → ['Bakery','Pound Cake','Lemon']
    """
    if not segs: return segs

    # Family is always preserved at index 0
    family = segs[0]
    rest = segs[1:]
    if not rest: return [family]

    # Identify segments that get dropped: any word X where a more-specific
    # segment Y exists in the same path such that Y's last word equals X
    # (singular/plural-aware). The MORE SPECIFIC one wins.
    keep = [True] * len(rest)
    for i, a in enumerate(rest):
        if not keep[i]: continue
        a_norm = normalize_plural(a)
        a_words = a.lower().split()
        for j, b in enumerate(rest):
            if i == j or not keep[j]: continue
            b_words = b.lower().split()
            # Direct singular/plural duplicate (same word count, same root)
            if len(a_words) == len(b_words) and equivalent_words(a, b):
                # Drop the latter occurrence (preserve order)
                if j > i: keep[j] = False
                continue
            # Subsumption: a is single-word, b ends with same word (b is multi-word)
            if len(a_words) == 1 and len(b_words) >= 2:
                b_last = b_words[-1]
                if normalize_plural(b_last) == a_norm:
                    # b is more specific (e.g. 'Drink Mix' vs 'Mixes', 'Pound Cake' vs 'Cake')
                    keep[i] = False
                    break

    out = [family] + [r for r, k in zip(rest, keep) if k]
    return out


# =====================================================================
# SEGMENT CLASSIFIER
# =====================================================================

def classify_segment(seg: str, position: int = -1) -> str:
    """Return one of: TYPE, VARIANT, FLAVOR, FORM, PROCESSING, CLAIM, UNKNOWN.

    position: 0=family (always TYPE/FAMILY), 1=type-anchor, etc.
    """
    if not seg: return 'UNKNOWN'
    s = seg.lower().strip()
    # Position-aware: very early segments are family/type anchors
    if position <= 1: return 'TYPE'
    if is_claim(s): return 'CLAIM'
    if is_form(s) and s not in CLAIM_WORDS: return 'FORM'
    if is_flavor(s): return 'FLAVOR'
    if is_type(s): return 'TYPE'
    return 'UNKNOWN'


# =====================================================================
# DEDUPE
# =====================================================================

def dedupe_preserve_order(segs: Iterable[str]) -> list[str]:
    """Drop case-insensitive duplicate segments preserving order.
    Also drops singular/plural duplicates.
    """
    seen_lower: set[str] = set()
    seen_singular: set[str] = set()
    out: list[str] = []
    for s in segs:
        if not s: continue
        sl = s.lower()
        ss = normalize_plural(s)
        if sl in seen_lower: continue
        if ss in seen_singular and ss != sl: continue  # singular/plural dup
        seen_lower.add(sl)
        seen_singular.add(ss)
        out.append(s)
    return out


# =====================================================================
# UNIFIED CANONICALIZER (THE ENTRY POINT)
# =====================================================================

def canonicalize_path(segs_in: list[str]) -> str:
    """Single canonicalization pipeline.

    Input: list of path segments (e.g., ['Bakery', 'Pastry', 'Croissants', 'Croissant']).
    Output: canonical path string with fixed top-down order:
        family > type > variant > flavor > form > processing > unknown > claims (alpha)
    """
    if not segs_in or len(segs_in) < 2: return ' > '.join(segs_in or [])

    # 1. Apply synonym map element-wise
    segs = [apply_synonym(s) for s in segs_in]

    # 2. Strip type-echo (singular/plural-aware)
    segs = strip_type_echo(segs)

    # 3. Always preserve family (segs[0]) and type-anchor (segs[1]) at front
    family = segs[0]
    type_anchor = segs[1] if len(segs) >= 2 else ''
    rest = segs[2:] if len(segs) > 2 else []

    # 4. Classify each remaining segment
    buckets: dict[str, list[str]] = {
        'TYPE': [], 'VARIANT': [], 'FLAVOR': [], 'FORM': [],
        'PROCESSING': [], 'UNKNOWN': [], 'CLAIM': [],
    }
    for i, s in enumerate(rest):
        cat = classify_segment(s, position=i + 2)
        buckets[cat].append(s)

    # 5. Sort within sortable buckets (alpha)
    for b in ('CLAIM',):  # only claims sorted (flavor order may matter for compound flavors)
        buckets[b] = sorted(set(buckets[b]), key=str.lower)

    # 6. Reassemble: TYPE→VARIANT→FLAVOR→FORM→PROCESSING→UNKNOWN→CLAIM
    ordered = (
        [family, type_anchor] +
        buckets['TYPE'] + buckets['VARIANT'] + buckets['FLAVOR'] +
        buckets['FORM'] + buckets['PROCESSING'] +
        buckets['UNKNOWN'] + buckets['CLAIM']
    )
    ordered = [s for s in ordered if s]  # remove empties

    # 7. Final dedupe (case-insensitive + singular/plural)
    return ' > '.join(dedupe_preserve_order(ordered))


# =====================================================================
# Self-test
# =====================================================================
if __name__ == '__main__':
    tests = [
        # (input segments, expected output)
        (['Bakery', 'Pastry', 'Croissants', 'Croissant'],
         'Bakery > Pastry > Croissants'),
        (['Beverage', 'Drink Mix', 'Mixes', 'Orange'],
         'Beverage > Drink Mix > Orange'),
        (['Pantry', 'Mixes', 'Drink Mix', 'Orange'],
         'Pantry > Drink Mix > Orange'),  # backward elimination
        (['Beverage', 'Drink Mix', 'Sweetened', 'Mixes', 'Tropical Punch'],
         'Beverage > Drink Mix > Tropical Punch > Sweetened'),
        (['Beverage', 'Drink Mix', 'Sugar Free', 'Zero Sugar', 'Mixes', 'Grape & Strawberry'],
         'Beverage > Drink Mix > Grape & Strawberry > Sugar Free'),
        (['Pantry', 'Nut Butters', 'Organic', 'Almond Butter'],
         'Pantry > Nut Butters > Almond Butter > Organic'),
        (['Snack', 'Bars', 'Granola Bars', 'Crispy', 'Honey'],
         'Snack > Granola Bars > Honey > Crispy'),  # Bars subsumed by Granola Bars
        (['Bakery', 'Doughnuts', 'Donut'],
         'Bakery > Doughnuts'),
        (['Frozen', 'Pizza', 'Vegetarian', 'Flatbread'],
         'Frozen > Pizza > Flatbread > Vegetarian'),
        (['Bakery', 'Cake', 'Pound Cake', 'Lemon'],
         'Bakery > Pound Cake > Lemon'),  # Cake subsumed by Pound Cake
    ]
    print("Self-test results:")
    failures = 0
    for inp, expected in tests:
        actual = canonicalize_path(inp)
        ok = actual == expected
        if not ok: failures += 1
        print(f"  {'✓' if ok else '✗'} {inp}")
        print(f"     → {actual}")
        if not ok:
            print(f"     expected: {expected}")
    print(f"\n  {len(tests) - failures}/{len(tests)} tests passed")
