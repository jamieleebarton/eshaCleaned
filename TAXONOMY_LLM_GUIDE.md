# Hestia Product Taxonomy — LLM Classification Protocol

## Goal
Assign a canonical identity code to any grocery product in 1-4 levels.
Do NOT enumerate every product. Use the rules below to derive the code from the product name.

## Form vs. Identity — Critical Rule

**For single-ingredient staples (rice, beans, plain vegetables, plain fruit, plain meat):**
- The identity code does NOT include form (fresh, frozen, canned, dried).
- Form is a **retail attribute**.
- Example: Frozen white rice = `Pantry > Rice & Grain > White Rice` + `form=Frozen`
- Example: Canned black beans = `Pantry > Beans & Legumes > Black Beans` + `form=Canned`
- Example: Frozen chicken breast = `Meat & Seafood > Poultry > Chicken Breast` + `form=Frozen`

**For prepared foods and composite products:**
- Form IS part of the identity because it changes the product category.
- Example: `Frozen > Single Entrees > Chicken Tikka Masala`
- Example: `Pantry > Canned Vegetables > Green Beans` (canned veg is a distinct prepared category)
- Example: `Frozen > Vegetables > Green Beans` (frozen veg is a distinct prepared category)

**Why the distinction?**
- A recipe calling for "white rice" does not care if it's frozen or dry. It's still white rice.
- A recipe calling for "green beans" MIGHT care if they're canned vs. fresh (different cooking times, salt content). But more importantly, shoppers think of "canned green beans" and "frozen green beans" as distinct product categories.
- A recipe calling for "chicken tikka masala" expects a fully prepared frozen meal, not raw ingredients.

---

## The "Plain" Problem

**Never require a product to be labeled "plain" to be the default.**

- **Default product**: The base form of the food with no distinguishing flavor, cuisine, or functional modifier.
  - Example: "Philadelphia Cream Cheese" → default (no modifier needed)
  - Example: "Kraft Sharp Cheddar" → default (sharpness is a cheese type, not a flavor)
  - Example: "Lay's Classic Potato Chips" → default
- **Variant product**: Has an added flavor, cuisine style, or functional modifier that changes what it is.
  - Example: "Philadelphia Strawberry Cream Cheese" → variant: Strawberry
  - Example: "Lay's BBQ Potato Chips" → variant: Barbecue
  - Example: "Whole Milk" → default. "Chocolate Milk" → variant (different canonical path).

**For recipe matching**: If a recipe asks for "cream cheese," match the default. If it asks for "strawberry cream cheese," match the variant.

---

## Level 1: Domain (11 categories)

Pick ONE based on where the product lives in the store or its primary use:

| Code | Domain | Includes |
|------|--------|----------|
| D | Dairy | Milk, cheese, yogurt, butter, cream, ice cream, eggs |
| P | Pantry | Shelf-stable ingredients, sauces, seasonings, pasta, canned goods, baking supplies, oil, vinegar |
| S | Snack | Ready-to-eat snacks, candy, chips, crackers, nuts, popcorn, jerky, trail mix |
| B | Beverage | Drinks, juices, sodas, water, tea, coffee, sports drinks, alcohol, drink mixes |
| K | Bakery | Bread, bagels, cookies, cakes, pastries, donuts, muffins, pies, tortillas |
| F | Frozen | Frozen meals, vegetables, fruits, desserts, appetizers, pizza, dough |
| M | Meat & Seafood | Raw and prepared meat, poultry, fish, shellfish, deli meats, bacon, sausage |
| L | Meal | Fully prepared meals, pizza, sandwiches, salads, pasta dishes, soups (refrigerated or shelf-stable) |
| R | Produce | Fresh fruits and vegetables, fresh herbs |
| W | Sports & Wellness | Protein powders, supplements, energy gels, electrolyte drinks |
| Y | Baby & Toddler | Infant formula, baby food, toddler snacks |

---

## Level 2: Class (~50 major classes)

Pick the class that best describes the product's form or purpose. If unsure, default to the broader class.

### Dairy (D)
- Milk (fluid, evaporated, condensed, powdered, plant-based milks)
- Cheese (all types: cheddar, mozzarella, cream cheese, cottage cheese, parmesan)
- Yogurt (Greek, regular, drinkable, frozen yogurt)
- Butter & Margarine
- Cream & Half-and-Half
- Ice Cream & Frozen Desserts
- Eggs

### Pantry (P)
- Spices & Seasonings (individual spices, seasoning blends, salt, pepper)
- Sauces & Salsas (pasta sauce, BBQ sauce, hot sauce, salsa, marinades)
- Salad Dressings
- Oil (olive, vegetable, coconut, etc.)
- Vinegar
- Pasta & Noodles
- Rice & Grain
- Cereal & Granola
- Baking Mixes & Flour
- Sweeteners (sugar, honey, syrup, stevia)
- Canned Vegetables
- Canned Fruit
- Beans & Legumes (canned or dried)
- Soup & Broth
- Nuts & Seeds (raw or roasted, not snack mixes)
- Peanut Butter & Nut Butters
- Jam, Jelly & Preserves
- Pickles & Olives
- Bread Crumbs & Croutons

### Snack (S)
- Candy (chocolate, hard candy, gummy, sour, licorice)
- Chips (potato chips, tortilla chips, pita chips, veggie chips)
- Crackers
- Popcorn
- Nuts (snack-packaged nuts: almonds, cashews, peanuts, mixed nuts)
- Trail Mix
- Jerky (beef, turkey, etc.)
- Bars (granola bars, protein bars, energy bars)
- Pretzels
- Cookies (if snack-sized or packaged; bakery cookies go to Bakery)

### Beverage (B)
- Juice (fruit, vegetable, blends)
- Soda & Carbonated
- Sparkling Water
- Tea (iced, hot, bottled)
- Coffee (ground, instant, bottled ready-to-drink)
- Sports & Energy Drinks
- Water (plain, flavored, enhanced)
- Drink Mixes (powdered, liquid concentrates)
- Protein Drinks & Shakes
- Plant Milk (almond, oat, soy, coconut — also see Dairy)
- Alcohol (beer, wine, spirits, malt beverages)

### Bakery (K)
- Bread (sandwich, sourdough, rye, white, wheat, multi-grain)
- Bagels
- Cookies (bakery-style, packaged cookie brands)
- Cake
- Cupcakes
- Pie
- Donuts
- Muffins
- Pastry (croissants, danishes, turnovers)
- Brownies
- Biscotti
- Tortillas (flour, corn)
- Flatbread
- English Muffins
- Naan
- Pita Bread
- Rolls (dinner, Hawaiian)
- Buns (hamburger, hot dog)

### Frozen (F)
- Single Entrees (individual frozen meals: mac & cheese, chicken dishes, pasta meals)
- Family Entrees & Multi-Serve Meals
- Appetizers (egg rolls, sliders, wings, mozzarella sticks, dumplings)
- Pizza
- Vegetables
- Fruit
- Rice & Grains (frozen plain rice, frozen quinoa blends — identity is the grain, form is frozen)
- Beans & Legumes (frozen plain beans)
- Ice Cream & Frozen Desserts
- Frozen Yogurt
- Breakfast (frozen waffles, pancakes, breakfast sandwiches)
- Dough (pie crust, pizza dough, cookie dough)

### Meat & Seafood (M)
- Beef (steaks, roasts, ground, jerky)
- Pork (chops, roasts, bacon, sausage, ham)
- Poultry (chicken, turkey, duck)
- Deli Meat (sliced turkey, ham, roast beef, salami)
- Sausage (links, patties, bratwurst, chorizo)
- Bacon
- Fish (salmon, tuna, cod, tilapia)
- Shellfish (shrimp, crab, lobster, scallops)

### Meal (L)
- Pizza (fresh, refrigerated, ready-to-bake)
- Sandwiches (pre-made, refrigerated)
- Salad (pre-made, kit)
- Pasta Dishes (pre-made mac & cheese, lasagna)
- Soup (refrigerated, ready-to-eat)
- Sushi & Prepared Rolls

### Produce (R)
- Vegetables (fresh, whole, cut, packaged)
- Fruit (fresh, whole, cut, packaged)
- Fresh Herbs (basil, cilantro, parsley, mint)

### Sports & Wellness (W)
- Protein Powder
- Protein Bars (if wellness-branded; snack bars go to Snack)
- Supplements (vitamins, minerals)
- Energy Gels & Chews

### Baby & Toddler (Y)
- Baby Food (purees, pouches)
- Infant Formula
- Toddler Snacks

---

## Level 3: Type

Level 3 is the specific food within the class. Use the product name to determine the type.

### Rule A: Canonical Path Only (L1 > L2 > L3)
For these classes, the type is the full identity. Modifiers are retail attributes (flavor, claim, brand).

**Applies to:**
- Dairy: Milk, Cheese (except cream cheese/cottage cheese — see Rule C), Yogurt (plain/Greek), Butter, Ice Cream
- Pantry: Salt, individual Spices (cumin, paprika, oregano), Oil, Vinegar, Pasta, Rice, Peanut Butter, Jam
- Snack: Potato Chips, Tortilla Chips, Popcorn, Pretzels, most Candy, Crackers, Nuts
- Beverage: Juice, Soda, Sparkling Water, Tea, Coffee, Plant Milk
- Bakery: Bread, Bagels, Cookies, Cake, Donuts, Muffins, Tortillas
- Meat & Seafood: Beef, Pork, Chicken, Fish, Bacon, Sausage (raw), Deli Meat
- Produce: all

**Examples:**
- "Tropicana Orange Juice" → `Beverage > Juice > Orange Juice`
- "Lay's BBQ Potato Chips" → `Snack > Chips > Potato Chips` (BBQ is a modifier, not part of code)
- "Wonder Bread Whole Wheat" → `Bakery > Bread > Bread` (Whole Wheat is a modifier)
- "Kraft Sharp Cheddar" → `Dairy > Cheese > Cheddar` (Sharp is a modifier)

### Rule B: Modifier IS Identity (L1 > L2 > L3 > L4)
For prepared foods and named blends, the modifier describes what the food actually IS. Different modifiers are different codes.

**Applies to:**
- Frozen: Single Entrees, Family Entrees, Appetizers, Pizza
- Meal: Pizza, Sandwiches, Salads, Pasta Dishes, Soup, Sushi
- Pantry: Seasoning (when generic), Spice Blend (when generic), Sauce (when generic), Dip, Salsa, Soup, Broth
- Snack: Bars (protein/granola/energy when the type is the bar formula), Jerky (when flavor defines the product)

**Examples:**
- "Stouffer's Mac & Cheese" → `Frozen > Single Entrees > Mac and Cheese`
- "TGI Friday's Chicken Tikka Masala" → `Frozen > Single Entrees > Chicken Tikka Masala`
- "Old El Paso Taco Seasoning" → `Pantry > Spices & Seasonings > Taco Seasoning`
- "McCormick Italian Seasoning" → `Pantry > Spices & Seasonings > Italian Seasoning`
- "Kraft Ranch Dressing" → `Pantry > Salad Dressings > Ranch`

**Special case — Generic Seasoning/Sauce:**
If the product is generic "seasoning" or "sauce" without a named cuisine/style, the modifier becomes Level 4:
- "McCormick All Purpose Seasoning" → `Pantry > Spices & Seasonings > Seasoning > All Purpose`
- "McCormick Chicken Seasoning" → `Pantry > Spices & Seasonings > Seasoning > Chicken`
- "Ragu Traditional Pasta Sauce" → `Pantry > Sauces & Salsas > Pasta Sauce > Traditional`

### Rule C: Default is Unmarked (L1 > L2 > L3, default has no modifier)
For foods where flavored variants exist but the recipe almost always wants the unmarked/default version.

**Applies to:**
- Dairy: Cream Cheese, Cottage Cheese
- Pantry: some spreads (honey butter, fruit butters)
- Bakery: some breads (cinnamon raisin, banana bread — when the flavor is the identity)

**Recipe matching logic:**
- Recipe "cream cheese" → `Dairy > Cheese > Cream Cheese` + prefer NO modifier or modifier=Plain
- Recipe "strawberry cream cheese" → `Dairy > Cheese > Cream Cheese` + modifier=Strawberry
- Recipe "bagel" → `Bakery > Bagels` + prefer NO modifier or modifier=Plain
- Recipe "blueberry bagel" → `Bakery > Bagels` + modifier=Blueberry

---

## Decision Flowchart for the LLM

```
1. What is the primary domain? → L1
2. What is the class/form? → L2
3. Is this a prepared food / named blend / specific dish?
   YES → Does it have a specific dish/cuisine/blend name?
      YES → Use dish name as L3 (or L4 if generic class)
      NO → Use product type as L3, modifier as L4
   NO → Use product type as L3
4. Does the product have a flavor/cuisine modifier that changes its identity?
   YES AND Rule B/C applies → Include modifier in code
   NO OR Rule A applies → Modifier is an attribute, not part of code
5. Is the product the "default" unmarked version?
   YES → Code ends at L3 (or L3 with no modifier)
   NO → Append distinguishing modifier
```

---

## Quick Reference: Rule by Class

| Class | Rule | Notes |
|-------|------|-------|
| Milk | A | Fat level is modifier |
| Cheese (cheddar, mozzarella, etc.) | A | Sharpness/age is modifier |
| Cream Cheese | C | Flavor variants exist; default is unmarked |
| Yogurt | A/C | Plain/Greek are types; fruit flavors are modifiers |
| Ice Cream | A | All flavors are modifiers |
| Potato Chips | A | All flavors are modifiers |
| Tortilla Chips | A | All flavors are modifiers |
| Bagels | A | Flavors are modifiers |
| Bread | A | Whole wheat, sourdough are modifiers |
| Single Entrees | B | Dish name IS the code |
| Appetizers | B | Dish name IS the code |
| Frozen Pizza | B | Topping style IS the code |
| Seasoning (named) | B | Italian, Cajun, Taco are types |
| Seasoning (generic) | B | All Purpose, Chicken are L4 modifiers |
| Sauce (named) | B | Pasta sauce, BBQ sauce are types |
| Sauce (generic) | B | Marinara, Alfredo are L4 modifiers |
| Juice | A | Flavor is modifier |
| Soda | A | Flavor is modifier |
| Plant Milk | A | Plain, vanilla are modifiers |
| Deli Meat | A | Turkey, ham are types; sliced is modifier |
| Bacon | A | Applewood, thick-cut are modifiers |
| Sausage (raw) | A | Italian, breakfast are types |
| Beef | A | Ground, steak, roast are modifiers |
| Chicken | A | Breast, thigh, wing are modifiers |
| Fresh Vegetables | A | Cut/style is modifier |
| Fresh Fruit | A | Cut/style is modifier |

---

## Examples

| Product Name | Code | Rule | Reasoning |
|--------------|------|------|-----------|
| Philadelphia Cream Cheese | `Dairy > Cheese > Cream Cheese` | C | Default, no modifier |
| Philadelphia Strawberry Cream Cheese | `Dairy > Cheese > Cream Cheese > Strawberry` | C | Flavor variant |
| Land O'Lakes Butter | `Dairy > Butter & Margarine > Butter` | A | No distinguishing modifier |
| Horizon Organic Whole Milk | `Dairy > Milk > Milk` | A | Whole is modifier |
| Stouffer's Mac & Cheese | `Frozen > Single Entrees > Mac and Cheese` | B | Dish name is identity |
| Lean Cuisine Chicken Tikka Masala | `Frozen > Single Entrees > Chicken Tikka Masala` | B | Dish name is identity |
| DiGiorno Pepperoni Pizza | `Frozen > Pizza > Pepperoni` | B | Topping is identity |
| Lay's Classic Potato Chips | `Snack > Chips > Potato Chips` | A | Classic = default |
| Lay's BBQ Potato Chips | `Snack > Chips > Potato Chips` | A | BBQ is flavor modifier |
| Thomas' Plain Bagels | `Bakery > Bagels > Bagels` | A | Plain = default |
| Thomas' Blueberry Bagels | `Bakery > Bagels > Bagels` | A | Blueberry is flavor modifier |
| McCormick Taco Seasoning | `Pantry > Spices & Seasonings > Taco Seasoning` | B | Named blend |
| McCormick All Purpose Seasoning | `Pantry > Spices & Seasonings > Seasoning > All Purpose` | B | Generic + modifier |
| Tropicana Orange Juice | `Beverage > Juice > Orange Juice` | A | Type is orange |
| Diet Coke | `Beverage > Soda & Carbonated > Cola` | A | Diet is modifier |
| Almond Breeze Unsweetened Vanilla Almond Milk | `Beverage > Plant Milk > Almond Milk` | A | Vanilla + unsweetened are modifiers |
| Hebrew National Beef Franks | `Meat & Seafood > Sausage > Hot Dogs` | A | Beef is modifier |
| Applegate Uncured Bacon | `Meat & Seafood > Bacon > Bacon` | A | Uncured is modifier |
| Fresh Express Caesar Salad Kit | `Meal > Salad > Caesar` | B | Named salad type |
| Bananas | `Produce > Fruit > Bananas` | A | Single ingredient |
| Baby Spinach | `Produce > Vegetables > Spinach` | A | Baby is modifier |
| Birds Eye Frozen White Rice | `Pantry > Rice & Grain > White Rice` | A | Identity is white rice. Frozen is form attribute. |
| Goya Canned Black Beans | `Pantry > Beans & Legumes > Black Beans` | A | Identity is black beans. Canned is form attribute. |
| Tyson Frozen Chicken Breast | `Meat & Seafood > Poultry > Chicken Breast` | A | Identity is chicken breast. Frozen is form attribute. |
| Del Monte Canned Green Beans | `Pantry > Canned Vegetables > Green Beans` | B | Canned vegetables are a distinct prepared category. |
| Birds Eye Frozen Green Beans | `Frozen > Vegetables > Green Beans` | B | Frozen vegetables are a distinct prepared category. |
