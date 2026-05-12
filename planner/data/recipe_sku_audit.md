# Per-recipe SKU audit — what did we pick, was it right?

Flags: WRONG_PATH (sku path mismatch) | OVERSIZED (>10× need + >500g surplus) | PREMIUM (>2× cheapest in path) | TINY_NEED (<5g need) | OK

`grams_blob` = original USDA-derived grams; `grams_resolved` = parsed qty (the one we use).


## 49508 — Snappy Turtles

- **Hestia cached:** $83.35
- **Ours line-attrib:** $6.37  (food-value math, fake)
- **Ours WHOLE CART:** $23.78  (9 packages)

- Flags: TINY_NEED=3, OVERSIZED=1

| ingredient | need g | SKU | path | pkg g | $/pkg | n× | $ | surplus g | flag |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| 15 pecan halves | 75 | Planters Lightly Salted Mixed Nuts with Peanuts, Almond | Snack > Nuts > Mixed Nuts | 292 | $7.12 | 1 | $7.12 | 217 | **OK** |
| 3/4 teaspoon vanilla extract | 3 | Great Value Pure Vanilla Extract, 1 fl oz | Pantry > Baking Extracts > Van | 30 | $4.14 | 1 | $4.14 | 26 | **TINY_NEED** |
| 3 semi-sweet chocolate baking squares, melted | 42 | GHIRARDELLI Intense Dark Chocolate Squares, 72% Cacao,  | Snack > Chocolate Candy > Choc | 116 | $3.98 | 1 | $3.98 | 74 | **OK** |
| 1/2 cup butter, softened | 114 | Land O Lakes Butter with Canola Oil, Spreadable, 8 oz T | Dairy > Butter | 227 | $2.48 | 1 | $2.48 | 113 | **OK** |
| 1/2 cup brown sugar | 110 | Great Value Light Brown Sugar, 32 oz | Pantry > Sweeteners > Sugar >  | 907 | $1.94 | 1 | $1.94 | 797 | **OK** |
| 1 1/2 cups all-purpose flour | 180 | Great Value All-Purpose Enriched Flour, 2 lb Bag | Pantry > Flour | 907 | $1.32 | 1 | $1.32 | 727 | **OK** |
| 1 egg | 50 | Kroger® Large White Eggs | Dairy > Eggs | 59 | $1.09 | 1 | $1.09 | 9 | **OK** |
| 1/4 teaspoon baking soda | 1 | Great Value Baking Soda, 1 lb | Pantry > Baking Additives & Ex | 454 | $0.92 | 1 | $0.92 | 452 | **TINY_NEED** |
| 1/4 teaspoon salt | 2 | Kroger® Salt | Pantry > Spices & Seasonings > | 739 | $0.79 | 1 | $0.79 | 738 | **OVERSIZED,TINY_NEED** |

## 189779 — Smoked Whole Brisket With Burnt Ends

- **Hestia cached:** $227.30
- **Ours line-attrib:** $121.21  (food-value math, fake)
- **Ours WHOLE CART:** $148.56  (18 packages)

- Flags: TINY_NEED=3, OVERSIZED=2

| ingredient | need g | SKU | path | pkg g | $/pkg | n× | $ | surplus g | flag |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| 10 lbs beef brisket, whole | 4536 | Jack Daniel's Seasoned Beef Brisket, Fully Cooked, Read | Meat & Seafood > Beef > Beef B | 567 | $14.97 | 9 | $134.73 | 567 | **OK** |
| 1⁄2 tablespoon coriander seed | 2 | Private Selection® Ground Coriander Seed Shaker | Pantry > Spices & Seasonings > | 36 | $4.49 | 1 | $4.49 | 34 | **TINY_NEED** |
| 1⁄4 cup brown sugar | 55 | Great Value Light Brown Sugar, 32 oz | Pantry > Sweeteners > Sugar >  | 907 | $1.94 | 1 | $1.94 | 852 | **OVERSIZED** |
| 1 tablespoon ground cumin | 6 | Great Value Ground Cumin, 2.5 oz | Pantry > Spices & Seasonings > | 71 | $1.37 | 1 | $1.37 | 65 | **OK** |
| 1 teaspoon oregano (Mexican if available) | 1 | Great Value Oregano Leaves, 0.87 oz | Pantry > Spices & Seasonings > | 25 | $1.13 | 1 | $1.13 | 24 | **TINY_NEED** |
| 2 tablespoons paprika | 14 | Great Value Paprika, 2.5 oz | Pantry > Spices & Seasonings > | 71 | $1.13 | 1 | $1.13 | 57 | **OK** |
| 1 teaspoon garlic powder | 3 | Great Value Garlic Powder, 3.4 oz | Pantry > Spices & Seasonings > | 96 | $1.00 | 1 | $1.00 | 93 | **TINY_NEED** |
| 3 tablespoons Worcestershire sauce | 51 | Great Value Worcestershire Sauce, 10 fl oz | Pantry > Sauces & Salsas > Wor | 296 | $1.00 | 1 | $1.00 | 245 | **OK** |
| 1 tablespoon fresh ground pepper | 7 | El Guapo Non-GMO Ground Black Pepper, 0.62 oz Bag | Pantry > Spices & Seasonings > | 18 | $0.98 | 1 | $0.98 | 11 | **OK** |
| 3 tablespoons kosher salt | 54 | Kroger® Salt | Pantry > Spices & Seasonings > | 739 | $0.79 | 1 | $0.79 | 685 | **OVERSIZED** |

## 195954 — Caramel Pecan Brownies

- **Hestia cached:** $0.00
- **Ours line-attrib:** $18.10  (food-value math, fake)
- **Ours WHOLE CART:** $29.85  (10 packages)

- Flags: TINY_NEED=1

| ingredient | need g | SKU | path | pkg g | $/pkg | n× | $ | surplus g | flag |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 cup pecans, chopped | 218 | Diamond of California Chopped Pecans 8 oz | Snack > Nuts > Pecans | 227 | $6.48 | 1 | $6.48 | 9 | **OK** |
| 1 (14 oz) bag caramels | 397 | Kraft America's Classic Individually Wrapped Candy Cara | Snack > Candy > Caramel Candy | 312 | $3.22 | 2 | $6.44 | 227 | **OK** |
| 1 teaspoon vanilla extract | 4 | Great Value Pure Vanilla Extract, 1 fl oz | Pantry > Baking Extracts > Van | 30 | $4.14 | 1 | $4.14 | 25 | **TINY_NEED** |
| 4 unsweetened chocolate squares (1 oz each), chopped | 113 | GHIRARDELLI Intense Dark Chocolate Squares, 72% Cacao,  | Snack > Chocolate Candy > Choc | 116 | $3.98 | 1 | $3.98 | 3 | **OK** |
| 3/4 cup margarine | 170 | Land O Lakes Margarine with Vegetable Oil Sticks | Dairy > Butter > Margarine | 454 | $2.49 | 1 | $2.49 | 284 | **OK** |
| 2 cups sugar | 400 | C&H Premium Pure Cane Granulated Sugar, 1 lb Box | Pantry > Sweeteners > Sugar | 454 | $1.92 | 1 | $1.92 | 54 | **OK** |
| 3 eggs | 150 | Kroger® Medium Grade A White Eggs | Dairy > Eggs | 626 | $1.59 | 1 | $1.59 | 476 | **OK** |
| 3 tablespoons milk | 46 | Kroger® Vitamin D Whole Milk 16 fl. oz. Bottle | Dairy > Milk | 490 | $1.49 | 1 | $1.49 | 444 | **OK** |
| 1 cup all-purpose flour | 120 | Great Value All-Purpose Enriched Flour, 2 lb Bag | Pantry > Flour | 907 | $1.32 | 1 | $1.32 | 787 | **OK** |

## 260663 — Blueberry Cobbler

- **Hestia cached:** $75.82
- **Ours line-attrib:** $8.15  (food-value math, fake)
- **Ours WHOLE CART:** $27.42  (14 packages)

- Flags: TINY_NEED=4, OVERSIZED=2

| ingredient | need g | SKU | path | pkg g | $/pkg | n× | $ | surplus g | flag |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| 6 cups fresh blueberries | 888 | Kroger® Frozen Blueberries | Frozen > Frozen Fruit > Bluebe | 454 | $2.99 | 2 | $5.98 | 19 | **OK** |
| 1/2 teaspoon vanilla | 2 | Great Value Pure Vanilla Extract, 1 fl oz | Pantry > Baking Extracts > Van | 30 | $4.14 | 1 | $4.14 | 27 | **TINY_NEED** |
| 4 tablespoons melted butter | 57 | Land O Lakes Butter with Canola Oil, Spreadable, 8 oz T | Dairy > Butter | 227 | $2.48 | 1 | $2.48 | 170 | **OK** |
| 2 tablespoons stone ground cornmeal | 16 | Juana Pre-Cooked White Corn Meal for arepas 2.2 Lb. | Pantry > Grain > Meal > Corn M | 998 | $2.28 | 1 | $2.28 | 982 | **OVERSIZED** |
| 2 teaspoons baking powder | 8 | Great Value Double Acting Baking Powder, 8.1 oz | Pantry > Baking Extracts > Bak | 230 | $2.12 | 1 | $2.12 | 222 | **OK** |
| 1/2 cup sugar | 158 | C&H Premium Pure Cane Granulated Sugar, 1 lb Box | Pantry > Sweeteners > Sugar | 454 | $1.92 | 1 | $1.92 | 295 | **OK** |
| 1 tablespoon cornstarch | 8 | Maizena Unflavored Corn Starch Powder, 14.1 oz Regular  | Pantry > Flour > Corn Starch | 400 | $1.78 | 1 | $1.78 | 392 | **OK** |
| 1 cup flour | 120 | Great Value All-Purpose Enriched Flour, 2 lb Bag | Pantry > Flour | 907 | $1.32 | 1 | $1.32 | 787 | **OK** |
| Pinch cinnamon | 1 | Smart Way™ Ground Cinnamon | Pantry > Spices & Seasonings > | 54 | $1.25 | 1 | $1.25 | 54 | **TINY_NEED** |
| 1 tablespoon lemon juice | 15 | Italia™ Garden Lemon Juice | Beverage > Juice > Lemon Juice | 113 | $1.25 | 1 | $1.25 | 98 | **OK** |
| 1/3 cup buttermilk | 82 | Kroger® Cultured 1% Lowfat Buttermilk Pint | Dairy > Buttermilk | 485 | $1.19 | 1 | $1.19 | 404 | **OK** |
| 1/4 teaspoon baking soda | 1 | Great Value Baking Soda, 1 lb | Pantry > Baking Additives & Ex | 454 | $0.92 | 1 | $0.92 | 452 | **TINY_NEED** |
| 1/4 teaspoon salt | 2 | Kroger® Salt | Pantry > Spices & Seasonings > | 739 | $0.79 | 1 | $0.79 | 738 | **OVERSIZED,TINY_NEED** |

## 342529 — Banana Nut Bread

- **Hestia cached:** $0.00
- **Ours line-attrib:** $5.23  (food-value math, fake)
- **Ours WHOLE CART:** $30.78  (12 packages)

- Flags: TINY_NEED=4, OVERSIZED=1

| ingredient | need g | SKU | path | pkg g | $/pkg | n× | $ | surplus g | flag |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| 1/2 cup walnuts, chopped | 62 | Hammons Black Walnuts Large Pieces, 12 oz | Snack > Nuts > Walnuts | 355 | $7.48 | 1 | $7.48 | 292 | **OK** |
| 1 teaspoon vanilla extract | 4 | Great Value Pure Vanilla Extract, 1 fl oz | Pantry > Baking Extracts > Van | 30 | $4.14 | 1 | $4.14 | 25 | **TINY_NEED** |
| 1/2 cup chocolate chips | 85 | Kroger® Semi Sweet Mini Chocolate Chips | Pantry > Chocolate Chips | 340 | $2.99 | 1 | $2.99 | 255 | **OK** |
| 1/2 cup margarine | 113 | Land O Lakes Margarine with Vegetable Oil Sticks | Dairy > Butter > Margarine | 454 | $2.49 | 1 | $2.49 | 341 | **OK** |
| 1/2 teaspoon ground nutmeg | 1 | Great Value Ground Nutmeg, 1.5 oz | Pantry > Spices & Seasonings > | 43 | $2.46 | 1 | $2.46 | 41 | **TINY_NEED** |
| 2 cups all-purpose flour | 240 | Kroger® Bleached All Purpose Flour | Pantry | 2268 | $2.39 | 1 | $2.39 | 2028 | **OK** |
| 1 1/2 teaspoons baking powder | 6 | Great Value Double Acting Baking Powder, 8.1 oz | Pantry > Baking Extracts > Bak | 230 | $2.12 | 1 | $2.12 | 224 | **OK** |
| 1 1/3 cups granulated sugar | 267 | C&H Premium Pure Cane Granulated Sugar, 1 lb Box | Pantry > Sweeteners > Sugar | 454 | $1.92 | 1 | $1.92 | 187 | **OK** |
| 2 large eggs | 100 | Kroger® Medium Grade A White Eggs | Dairy > Eggs | 626 | $1.59 | 1 | $1.59 | 526 | **OK** |
| 1/4 cup milk | 61 | Kroger® Vitamin D Whole Milk 16 fl. oz. Bottle | Dairy > Milk | 490 | $1.49 | 1 | $1.49 | 429 | **OK** |
| 1 teaspoon baking soda | 5 | Great Value Baking Soda, 1 lb | Pantry > Baking Additives & Ex | 454 | $0.92 | 1 | $0.92 | 449 | **TINY_NEED** |
| 1/2 teaspoon salt | 3 | Kroger® Salt | Pantry > Spices & Seasonings > | 739 | $0.79 | 1 | $0.79 | 736 | **OVERSIZED,TINY_NEED** |

## 260962 — Brown Sugar Honey Butter

- **Hestia cached:** $18.11
- **Ours line-attrib:** $1.60  (food-value math, fake)
- **Ours WHOLE CART:** $9.61  (4 packages)

- Flags: OVERSIZED=1, TINY_NEED=1

| ingredient | need g | SKU | path | pkg g | $/pkg | n× | $ | surplus g | flag |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 tablespoon honey | 21 | Great Value Honey, 12 oz Plastic Bear | Pantry > Sweeteners > Honey | 340 | $3.94 | 1 | $3.94 | 319 | **OK** |
| 1/2 cup butter, softened | 114 | Land O Lakes Butter with Canola Oil, Spreadable, 8 oz T | Dairy > Butter | 227 | $2.48 | 1 | $2.48 | 113 | **OK** |
| 1/8 cup brown sugar | 28 | Great Value Light Brown Sugar, 32 oz | Pantry > Sweeteners > Sugar >  | 907 | $1.94 | 1 | $1.94 | 880 | **OVERSIZED** |
| 1 teaspoon cinnamon | 3 | Smart Way™ Ground Cinnamon | Pantry > Spices & Seasonings > | 54 | $1.25 | 1 | $1.25 | 52 | **TINY_NEED** |

## 3344 — Penne Piperade

- **Hestia cached:** $94.19
- **Ours line-attrib:** $6.02  (food-value math, fake)
- **Ours WHOLE CART:** $21.73  (11 packages)

- Flags: TINY_NEED=1

| ingredient | need g | SKU | path | pkg g | $/pkg | n× | $ | surplus g | flag |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 tablespoon extra virgin olive oil | 14 | Pompeian Bold Spanish Extra Virgin Olive Oil - 16 fl oz | Pantry > Oil > Extra Virgin Ol | 473 | $7.38 | 1 | $7.38 | 460 | **OK** |
| 3 thin slices prosciutto, cut into bite-size pieces | 43 | Marketside Sliced Prosciutto, 3 oz | Meat & Seafood > Prosciutto | 85 | $4.24 | 1 | $4.24 | 42 | **OK** |
| 1 yellow bell pepper, cored, seeded, and cut into penne-size | 150 | Fresh Yellow Bell Pepper | Produce > Vegetables > Bell Pe | 454 | $1.69 | 1 | $1.69 | 304 | **OK** |
| 1 red bell pepper, cored, seeded, and cut into penne-size pi | 150 | Fresh Red Hothouse Bell Pepper | Produce > Vegetables > Bell Pe | 454 | $1.59 | 1 | $1.59 | 304 | **OK** |
| 4 cups penne | 400 | Great Value Whole Wheat Penne, 16 oz | Pantry > Pasta > Penne | 454 | $1.43 | 1 | $1.43 | 54 | **OK** |
| 1/2 cup flat leaf parsley, chopped | 30 | Parsley | Produce > Vegetables > Parsley | 454 | $1.19 | 1 | $1.19 | 424 | **OK** |
| 1 teaspoon hot paprika | 2 | Great Value Paprika, 2.5 oz | Pantry > Spices & Seasonings > | 71 | $1.13 | 1 | $1.13 | 69 | **TINY_NEED** |
| 2 large tomatoes, finely chopped, with juices | 300 | Great Value Petite Diced Tomatoes in Tomato Juice, 14.5 | Pantry > Canned Vegetables > T | 411 | $0.96 | 1 | $0.96 | 111 | **OK** |
| 1 green bell pepper, cored, seeded, and cut into penne-size  | 150 | Fresh Large Green Bell Pepper | Produce > Vegetables > Bell Pe | 454 | $0.89 | 1 | $0.89 | 304 | **OK** |
| 3 cloves garlic, thinly sliced | 9 | Garlic | Produce > Vegetables > Garlic | 454 | $0.79 | 1 | $0.79 | 445 | **OK** |
| 1 medium onion, thinly sliced | 110 | Jumbo Yellow Onions | Produce > Vegetables > Onions | 227 | $0.44 | 1 | $0.44 | 117 | **OK** |

## 193084 — Classic Turkey Gravy from Pan Juices

- **Hestia cached:** $48.96
- **Ours line-attrib:** $2.17  (food-value math, fake)
- **Ours WHOLE CART:** $14.00  (7 packages)

- Flags: OVERSIZED=3, TINY_NEED=1

| ingredient | need g | SKU | path | pkg g | $/pkg | n× | $ | surplus g | flag |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| 1/4 cup dry white wine | 59 | Gallo Dry Vermouth | Beverage > Wine | 1420 | $6.99 | 1 | $6.99 | 1361 | **OVERSIZED** |
| 4 tablespoons unsalted butter | 57 | Land O Lakes Butter with Canola Oil, Spreadable, 8 oz T | Dairy > Butter | 227 | $2.48 | 1 | $2.48 | 170 | **OK** |
| 5 cups turkey broth or chicken broth | 675 | Great Value Chicken Broth, 14.5 oz (Shelf-Stable) | Pantry > Broth & Stock > Chick | 429 | $0.72 | 2 | $1.44 | 183 | **OK** |
| 1/2 cup all-purpose flour | 60 | Great Value All-Purpose Enriched Flour, 2 lb Bag | Pantry > Flour | 907 | $1.32 | 1 | $1.32 | 847 | **OVERSIZED** |
| 1/4 teaspoon black pepper | 1 | El Guapo Non-GMO Ground Black Pepper, 0.62 oz Bag | Pantry > Spices & Seasonings > | 18 | $0.98 | 1 | $0.98 | 17 | **TINY_NEED** |
| 1 teaspoon kosher salt | 6 | Kroger® Salt | Pantry > Spices & Seasonings > | 739 | $0.79 | 1 | $0.79 | 733 | **OVERSIZED** |

## 149279 — Almond Sugar Cookies with Cranberries (Craisins)

- **Hestia cached:** $0.00
- **Ours line-attrib:** $14.73  (food-value math, fake)
- **Ours WHOLE CART:** $31.98  (12 packages)

- Flags: TINY_NEED=3

| ingredient | need g | SKU | path | pkg g | $/pkg | n× | $ | surplus g | flag |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 1/2 cups slivered almonds | 162 | Planters Lightly Salted Mixed Nuts with Peanuts, Almond | Snack > Nuts > Mixed Nuts | 292 | $7.12 | 1 | $7.12 | 130 | **OK** |
| 1 (12 oz) package cherry-flavored craisins | 340 | Ocean Spray® Cherry Craisins® | Snack > Dried Fruit > Dried Cr | 172 | $2.69 | 2 | $5.38 | 5 | **OK** |
| 1 teaspoon vanilla extract | 4 | Great Value Pure Vanilla Extract, 1 fl oz | Pantry > Baking Extracts > Van | 30 | $4.14 | 1 | $4.14 | 25 | **TINY_NEED** |
| 1 1/2 teaspoons almond extract | 6 | Great Value Pure Almond Extract, 2 fl oz | Pantry > Baking Extracts > Alm | 59 | $3.00 | 1 | $3.00 | 53 | **OK** |
| 1/2 cup margarine | 113 | Land O Lakes Margarine with Vegetable Oil Sticks | Dairy > Butter > Margarine | 454 | $2.49 | 1 | $2.49 | 341 | **OK** |
| 1/2 cup butter | 114 | Land O Lakes Butter with Canola Oil, Spreadable, 8 oz T | Dairy > Butter | 227 | $2.48 | 1 | $2.48 | 113 | **OK** |
| 1/2 teaspoon baking powder | 2 | Great Value Double Acting Baking Powder, 8.1 oz | Pantry > Baking Extracts > Bak | 230 | $2.12 | 1 | $2.12 | 228 | **TINY_NEED** |
| 1 1/2 cups sugar | 300 | C&H Premium Pure Cane Granulated Sugar, 1 lb Box | Pantry > Sweeteners > Sugar | 454 | $1.92 | 1 | $1.92 | 154 | **OK** |
| 2 3/4 cups all-purpose flour | 330 | Great Value All-Purpose Enriched Flour, 2 lb Bag | Pantry > Flour | 907 | $1.32 | 1 | $1.32 | 577 | **OK** |
| 1 egg | 50 | Kroger® Large White Eggs | Dairy > Eggs | 59 | $1.09 | 1 | $1.09 | 9 | **OK** |
| 1 teaspoon baking soda | 5 | Great Value Baking Soda, 1 lb | Pantry > Baking Additives & Ex | 454 | $0.92 | 1 | $0.92 | 449 | **TINY_NEED** |

## 168229 — Roast Sirloin of Beef with Au Jus

- **Hestia cached:** $155.20
- **Ours line-attrib:** $205.87  (food-value math, fake)
- **Ours WHOLE CART:** $214.12  (18 packages)

- Flags: all OK

| ingredient | need g | SKU | path | pkg g | $/pkg | n× | $ | surplus g | flag |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| 20 lbs boneless sirloin roast (butt cut) | 9072 | Boneless Stew Beef Family Pack | Meat & Seafood > Beef | 1021 | $22.48 | 9 | $202.32 | 113 | **OK** |
| 1 quart beef stock or water (for roasting) | 960 | Swanson 100% Natural Beef Stock, 48 oz Carton | Pantry > Broth & Stock > Beef  | 1361 | $4.42 | 1 | $4.42 | 401 | **OK** |
| 1 pint beef stock (for au jus) | 480 | Swanson 100% Natural Beef Stock, 32 oz Carton | Pantry > Broth & Stock > Beef  | 907 | $2.92 | 1 | $2.92 | 427 | **OK** |
| 1 tablespoon black pepper | 7 | El Guapo Non-GMO Ground Black Pepper, 0.62 oz Bag | Pantry > Spices & Seasonings > | 18 | $0.98 | 1 | $0.98 | 11 | **OK** |
| 1 1/2 cups onions, roughly chopped | 240 | Jumbo Yellow Onions | Produce > Vegetables > Onions | 227 | $0.44 | 2 | $0.88 | 214 | **OK** |
| 1/3 cup salt | 97 | Kroger® Salt | Pantry > Spices & Seasonings > | 739 | $0.79 | 1 | $0.79 | 642 | **OK** |
| 2 garlic cloves, minced | 6 | Garlic | Produce > Vegetables > Garlic | 454 | $0.79 | 1 | $0.79 | 448 | **OK** |
| 4 ounces carrots, roughly chopped | 113 | Kroger No Salt Added Sliced Carrots - 8.25oz can | Pantry > Canned Vegetables > C | 231 | $0.69 | 1 | $0.69 | 118 | **OK** |
| 4 ounces celery, roughly chopped | 113 | Celery Sticks | Produce > Vegetables > Celery | 454 | $0.33 | 1 | $0.33 | 341 | **OK** |


## Summary

| rid | title | Hestia | Ours line | Ours whole | n_pkg | wrong_path | oversized | premium | tiny |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 49508 | Snappy Turtles | $83.35 | $6.37 | $23.78 | 9 | 0 | 1 | 0 | 3 |
| 189779 | Smoked Whole Brisket With Burnt End | $227.30 | $121.21 | $148.56 | 18 | 0 | 2 | 0 | 3 |
| 195954 | Caramel Pecan Brownies | $0.00 | $18.10 | $29.85 | 10 | 0 | 0 | 0 | 1 |
| 260663 | Blueberry Cobbler | $75.82 | $8.15 | $27.42 | 14 | 0 | 2 | 0 | 4 |
| 342529 | Banana Nut Bread | $0.00 | $5.23 | $30.78 | 12 | 0 | 1 | 0 | 4 |
| 260962 | Brown Sugar Honey Butter | $18.11 | $1.60 | $9.61 | 4 | 0 | 1 | 0 | 1 |
| 3344 | Penne Piperade | $94.19 | $6.02 | $21.73 | 11 | 0 | 0 | 0 | 1 |
| 193084 | Classic Turkey Gravy from Pan Juice | $48.96 | $2.17 | $14.00 | 7 | 0 | 3 | 0 | 1 |
| 149279 | Almond Sugar Cookies with Cranberri | $0.00 | $14.73 | $31.98 | 12 | 0 | 0 | 0 | 3 |
| 168229 | Roast Sirloin of Beef with Au Jus | $155.20 | $205.87 | $214.12 | 18 | 0 | 0 | 0 | 0 |

### Aggregate flag totals

- OK: 66
- WRONG_PATH: 0
- OVERSIZED: 10
- PREMIUM: 0
- TINY_NEED: 21