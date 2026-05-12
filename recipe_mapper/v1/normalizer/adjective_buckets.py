"""Three adjective buckets for recipe ingredient normalization.

Bucket 1 — User-preference facets. Strip from canonical name; store as `claims`.
            User picks at planner runtime via facet toggle.
Bucket 2 — Culinary descriptors (form / processing / preparation). Strip from
            canonical; store as `form_facets` / `processing_facets`.
Bucket 3 — Identity-changing modifiers. KEEP in canonical name — different food.

The classifier walks an ingredient's tokens and routes each into one of these
buckets (or "core" for identity tokens). Multi-word identity-changers must be
detected as phrases BEFORE single-word stripping.
"""

# Bucket 1 — preference facets (stripped from canonical, stored as claims).
# Each maps to a normalized claim flag.
BUCKET_1_PREFERENCE_FACETS: dict[str, str] = {
    # Sourcing / certification
    "organic": "organic",
    "non-gmo": "non_gmo",
    "non gmo": "non_gmo",
    "gmo-free": "non_gmo",
    "fair-trade": "fair_trade",
    "fair trade": "fair_trade",
    "grass-fed": "grass_fed",
    "grass fed": "grass_fed",
    "pasture-raised": "pasture_raised",
    "pasture raised": "pasture_raised",
    "free-range": "cage_free",
    "free range": "cage_free",
    "cage-free": "cage_free",
    "cage free": "cage_free",
    "wild-caught": "wild_caught",
    "wild caught": "wild_caught",
    "all-natural": "natural",
    "all natural": "natural",
    "natural": "natural",
    # Fat / sodium / sugar reductions
    "fat-free": "fat_free",
    "fat free": "fat_free",
    "non-fat": "fat_free",
    "non fat": "fat_free",
    "nonfat": "fat_free",
    "low-fat": "low_fat",
    "low fat": "low_fat",
    "lowfat": "low_fat",
    "reduced-fat": "low_fat",
    "reduced fat": "low_fat",
    "low-sodium": "low_sodium",
    "low sodium": "low_sodium",
    "reduced-sodium": "low_sodium",
    "reduced sodium": "low_sodium",
    "no-salt": "low_sodium",
    "no salt": "low_sodium",
    "no-salt-added": "low_sodium",
    "salt-free": "low_sodium",
    "sugar-free": "sugar_free",
    "sugar free": "sugar_free",
    "no-sugar-added": "sugar_free",
    "no sugar added": "sugar_free",
    "low-sugar": "low_sugar",
    "low sugar": "low_sugar",
    "reduced-sugar": "low_sugar",
    "reduced sugar": "low_sugar",
    "unsweetened": "sugar_free",
    # Diet / allergen
    "vegan": "vegan",
    "plant-based": "vegan",
    "plant based": "vegan",
    "vegetarian": "vegetarian",
    "kosher": "kosher",
    "halal": "halal",
    "gluten-free": "gluten_free",
    "gluten free": "gluten_free",
    "dairy-free": "dairy_free",
    "dairy free": "dairy_free",
    "lactose-free": "dairy_free",
    "lactose free": "dairy_free",
    # Marketing / quality
    "premium": "natural",  # marketing tag, route to natural
    "select": "natural",
    "extra-virgin": "natural",  # for olive oil — but EVOO is identity (Bucket 3)
}

# Bucket 2 — culinary descriptors (form / processing / preparation).
# Map to form / processing / texture facets.
BUCKET_2_CULINARY_FORM: set[str] = {
    "chopped", "minced", "diced", "sliced", "shredded", "grated", "cubed",
    "julienned", "crushed", "cracked", "crumbled", "torn", "halved", "quartered",
    "ground", "milled",
    "whole", "halved", "quartered", "gutted", "boneless", "skinless",
    "large", "medium", "small", "mini", "miniature", "extra-large", "jumbo",
    "thick", "thin", "thinly", "thickly", "finely", "coarsely", "roughly",
}
BUCKET_2_CULINARY_PROCESSING: set[str] = {
    "fresh", "frozen", "canned", "dried", "dehydrated", "pickled", "smoked",
    "cooked", "raw", "boiled", "poached", "pan-fried", "fried", "steamed",
    "blanched", "roasted", "grilled", "broiled", "baked", "toasted",
    "drained", "rinsed", "washed", "patted", "peeled", "seeded", "cored",
    "trimmed", "stemmed", "pitted", "shelled",
    "melted", "softened", "room-temperature", "cold", "warm", "hot",
    "ripe", "unripe", "overripe",
    # NOTE: "green" is intentionally NOT in this set. Color words at the
    # start of an ingredient (green onion, green pepper, green olives,
    # green beans, green chili) usually change identity, not just ripeness.
    # Color-prefixed identities live in BUCKET_3_IDENTITY_PHRASES.
}
# Misc culinary words that aren't identity (often glued onto plain ingredients)
BUCKET_2_NOISE: set[str] = {
    "the", "a", "an", "of", "and", "with", "in", "on", "for", "or", "to",
    "good", "best", "quality", "real", "perfectly", "fully", "lightly", "heavily",
    "shaved",
    # Recipe-instruction words (not ingredient identity)
    "divided", "separated", "to taste", "as needed", "garnish", "for garnish",
    "optional", "to serve", "for serving",
}

# Bucket 3 — identity-changing modifiers. These STAY in the canonical name
# because they describe a fundamentally different food. Detected as multi-word
# phrases BEFORE single-word stripping.
BUCKET_3_IDENTITY_PHRASES: set[str] = {
    # Cream / milk variants
    "heavy cream", "whipping cream", "heavy whipping cream", "half-and-half",
    "half and half", "sour cream", "evaporated milk", "sweetened condensed milk",
    "condensed milk", "buttermilk", "almond milk", "soy milk", "oat milk",
    "coconut milk", "rice milk",
    # Cheese variants (these are different foods culinarily)
    "cream cheese", "cottage cheese", "ricotta cheese", "ricotta",
    "feta cheese", "feta", "mozzarella cheese", "mozzarella",
    "cheddar cheese", "cheddar", "parmesan cheese", "parmesan",
    "swiss cheese", "blue cheese", "goat cheese", "havarti",
    # Sugar / sweetener variants
    "brown sugar", "powdered sugar", "confectioners sugar", "confectioners' sugar",
    "granulated sugar", "cane sugar", "raw sugar", "demerara sugar",
    "muscovado sugar", "turbinado sugar", "coconut sugar",
    "maple syrup", "agave syrup", "agave nectar", "corn syrup", "molasses",
    "brown rice syrup",
    # Flour variants (different gluten/starch behavior)
    "all-purpose flour", "all purpose flour", "bread flour", "cake flour",
    "pastry flour", "self-rising flour", "self rising flour",
    "whole wheat flour", "whole-wheat flour", "almond flour", "coconut flour",
    "rice flour", "tapioca flour", "rye flour", "oat flour",
    # Bread variants
    "whole wheat bread", "whole-wheat bread", "white bread",
    "sourdough bread", "rye bread", "pumpernickel bread", "ciabatta bread",
    "focaccia bread", "naan bread", "pita bread", "french bread",
    # Chocolate variants
    "dark chocolate", "white chocolate", "milk chocolate", "semisweet chocolate",
    "bittersweet chocolate", "unsweetened chocolate", "baking chocolate",
    "chocolate chips", "chocolate squares",
    "cocoa powder", "unsweetened cocoa", "dutch-process cocoa",
    # Spice variants (smoking changes identity)
    "smoked paprika", "sweet paprika", "hot paprika", "spanish paprika",
    "smoked salt", "sea salt", "kosher salt", "table salt", "rock salt",
    "himalayan salt", "pink salt",
    "black pepper", "white pepper", "cayenne pepper", "red pepper",
    "ground cinnamon", "cinnamon stick",
    # Yeast variants (different rising behavior)
    "active dry yeast", "instant yeast", "fresh yeast", "rapid rise yeast",
    # Yogurt variants
    "greek yogurt", "regular yogurt", "plain yogurt",
    # Oil variants — extra virgin olive oil is functionally different from olive oil
    "extra virgin olive oil", "extra-virgin olive oil",
    # Vinegar variants
    "apple cider vinegar", "balsamic vinegar", "white vinegar", "red wine vinegar",
    "white wine vinegar", "rice vinegar", "rice wine vinegar",
    # Soy / asian sauces (different products)
    "soy sauce", "dark soy sauce", "light soy sauce", "tamari",
    "fish sauce", "oyster sauce", "hoisin sauce", "teriyaki sauce",
    # Mustards
    "dijon mustard", "yellow mustard", "stone-ground mustard", "whole-grain mustard",
    # Specific cuts of meat
    "boneless skinless chicken breast", "boneless skinless chicken breasts",
    "chicken thigh", "chicken thighs", "chicken wings", "chicken drumsticks",
    "ground beef", "ground turkey", "ground chicken", "ground pork",
    # Game / specialty meats
    "lamb shank", "lamb chop", "lamb chops", "pork chop", "pork chops",
    "pork tenderloin", "beef tenderloin", "beef brisket",
    # Other
    "rolled oats", "steel-cut oats", "old-fashioned oats", "instant oats",
    "long-grain rice", "short-grain rice", "basmati rice", "jasmine rice",
    "wild rice", "brown rice", "white rice", "arborio rice",
    "graham cracker", "graham crackers",
    "crème de menthe", "crème de cassis", "creme de menthe", "creme de cassis",
}

BUCKET_3_IDENTITY_SINGLE: set[str] = {
    # Single-word identity-changers (only when standalone, not as a modifier)
    # Example: "smoked" alone keeps in canonical only if it's "smoked X" phrase
    # Most identity-changers are phrases, not single words.
}

# "X of Y" compound food names — the "of" is critical to identity.
# These extend BUCKET_3_IDENTITY_PHRASES.
BUCKET_3_IDENTITY_PHRASES |= {
    "cream of tartar", "cream of mushroom", "cream of chicken",
    "cream of celery", "cream of mushroom soup", "cream of chicken soup",
    "cream of celery soup", "cream of broccoli soup", "cream of asparagus soup",
    "cream of potato soup", "cream of wheat",
    "hearts of palm", "hearts of romaine",
    "stick of butter", "stick of celery",
}

# Hot sauces and similar specific sauces (not soy/teriyaki etc which were already added)
BUCKET_3_IDENTITY_PHRASES |= {
    "hot sauce", "hot pepper sauce", "tabasco sauce", "tabasco",
    "sriracha", "sriracha sauce", "buffalo sauce", "buffalo wing sauce",
    "chili sauce", "chili garlic sauce", "sweet chili sauce",
    "chipotle sauce", "barbecue sauce", "bbq sauce",
    "worcestershire sauce", "steak sauce", "a1 sauce",
    "marinara sauce", "pasta sauce", "tomato sauce", "pizza sauce",
    "alfredo sauce", "pesto sauce", "pesto",
    "cocktail sauce", "tartar sauce", "horseradish sauce",
    "ranch dressing", "italian dressing", "caesar dressing",
    "blue cheese dressing", "thousand island dressing", "vinaigrette",
    "dijon mustard", "yellow mustard", "honey mustard", "stone-ground mustard",
}

# Pizza/composite specific items
BUCKET_3_IDENTITY_PHRASES |= {
    "italian sausage", "italian sausages", "italian seasoning",
    "italian plum tomatoes", "italian dressing", "italian bread",
    "italian herbs", "italian parsley",
    "scotch bonnet", "scotch bonnet pepper",
    "ham bone", "soup bone", "bay leaf", "bay leaves",
    "garam masala", "five spice", "chinese five spice", "old bay",
    "old bay seasoning", "lawry's seasoned salt", "seasoned salt",
    "fines herbes", "herbs de provence", "herbes de provence",
    "ras el hanout", "berbere", "za'atar", "zaatar",
    "chinese rice wine", "shaoxing wine", "mirin",
    "pomegranate molasses", "tamarind paste", "tamarind concentrate",
    "miso paste", "white miso", "red miso", "yellow miso",
    "creme fraiche", "crème fraîche", "mascarpone", "mascarpone cheese",
    "queso fresco", "queso blanco", "manchego cheese", "manchego",
    "asiago cheese", "asiago", "fontina cheese", "gruyere cheese", "gruyere",
}

# Color-prefixed identity phrases — color changes the food's identity
# (green pepper ≠ pepper, green onion ≠ onion, green beans ≠ beans).
# These extend BUCKET_3_IDENTITY_PHRASES.
BUCKET_3_IDENTITY_PHRASES |= {
    # Onions / scallions
    "green onion", "green onions", "yellow onion", "yellow onions",
    "white onion", "white onions", "red onion", "red onions",
    "spring onion", "spring onions", "scallion", "scallions",
    # Peppers (vegetables, distinct from pepper-the-spice)
    "green pepper", "green peppers", "red pepper", "red peppers",
    "yellow pepper", "yellow peppers", "orange pepper", "orange peppers",
    "green bell pepper", "green bell peppers", "red bell pepper",
    "red bell peppers", "yellow bell pepper", "yellow bell peppers",
    "orange bell pepper", "orange bell peppers", "bell pepper", "bell peppers",
    "jalapeno", "jalapenos", "jalapeño", "jalapeños",
    "serrano pepper", "serrano peppers", "habanero", "habaneros",
    "poblano", "poblanos", "anaheim pepper", "chipotle pepper",
    # Spice peppers (already in there but make explicit)
    "black pepper", "white pepper", "cayenne pepper", "ground pepper",
    "red pepper flakes", "crushed red pepper", "crushed red pepper flakes",
    # Chilies
    "green chili", "green chilies", "red chili", "red chilies",
    "green chili pepper", "green chili peppers",
    "red chili pepper", "red chili peppers",
    "hot chili pepper", "hot chili peppers",
    # Olives
    "green olives", "ripe olives", "black olives", "kalamata olives",
    "spanish olives", "stuffed olives",
    # Beans (different species/varieties — colors mark identity)
    "green beans", "wax beans", "yellow beans",
    "white beans", "black beans", "kidney beans", "red kidney beans",
    "pinto beans", "navy beans", "lima beans", "cannellini beans",
    "garbanzo beans", "chickpeas", "fava beans", "black-eyed peas",
    "great northern beans", "adzuki beans", "edamame", "soybeans",
    # Lentils
    "red lentils", "green lentils", "brown lentils", "black lentils",
    "yellow lentils", "french lentils",
    # Cabbages
    "green cabbage", "red cabbage", "purple cabbage", "savoy cabbage",
    "napa cabbage", "chinese cabbage",
    # Apples
    "green apple", "green apples", "red apple", "red apples",
    "granny smith apples", "fuji apples", "gala apples", "honeycrisp apples",
}
