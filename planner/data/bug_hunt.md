# Wide bug-hunting audit

Sample: 200 recipes. Each may carry multiple flags.

## Flag counts

- **WE_TOO_LOW**: 7
- **WE_TOO_HIGH**: 0
- **HESTIA_ZERO**: 23
- **MANY_PACKAGES**: 1
- **HIGH_SURPLUS**: 8
- **MISSING_LINES**: 3
- **ZERO_COST**: 0


## WE_TOO_LOW — top 5


### 492357 — Best Israeli Hummus
- Hestia: $58.42 | Ours: $7.46 | n_pkg: 3 | surplus: 848g | missing: 1/4
- Flags: WE_TOO_LOW

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 4 cans (15 oz each) garbanzo beans, drained and rinsed | calculate | 1700.0 | (none) | 0 | $0.00 |
| 1 cup prepared tahini | calculate | 256.0 | Krinos Imported Tahini, Velvety Texture, 16 oz Jar, Gro | 454.0 | $5.18 |
| 4 garlic cloves, crushed | calculate | 12.0 | Garlic | 454.0 | $0.79 |
| 1 cup fresh lemon juice | calculate | 244.0 | Kroger® 100% Lemon Juice | 454.0 | $1.49 |
| 1 teaspoon salt | shop_only | 6.0 | Kroger® Salt | 739.0 | $0.79 |
| Paprika, for garnish | shop_only | 1.0 | Great Value Paprika, 2.5 oz | 71.0 | $1.13 |
| Olive oil, for drizzling | shop_only | 15.0 | GEM Extra Virgin Olive Oil for Seasoning and Finishing, | 251.0 | $4.68 |
| Fresh parsley, chopped, for garnish | shop_only | 5.0 | Fresh Parsley, 0.5 oz Clamshell | 14.0 | $1.78 |

### 420713 — Cheesy Pepperoni Popcorn
- Hestia: $63.03 | Ours: $14.49 | n_pkg: 6 | surplus: 1178g | missing: 0/8
- Flags: WE_TOO_LOW

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 12 cups air-popped popcorn | calculate | 120.0 | Jolly Time White Popcorn Kernels, 32 oz. Bag | 907.0 | $2.66 |
| 3/4 cup turkey pepperoni, cut into bite-sized pieces | calculate | 85.0 | Great Value Turkey Pepperoni Slices, 5 oz | 148.0 | $2.92 |
| Olive oil flavored cooking spray, for spraying | shop_only | 5.0 | (none) | 0 | $0.00 |
| 1/4 cup nonfat Parmesan cheese, grated | calculate | 25.0 | Mama Francesca Classic Parmesan Cheese, 8 oz Shaker | 227.0 | $3.44 |
| 2 teaspoons garlic powder | calculate | 6.2 | Great Value Garlic Powder, 3.4 oz | 96.0 | $1.00 |
| 1/4 teaspoon dried oregano | calculate | 0.2 | Great Value Taco Seasoning Mix, Original, 1 oz | 28.0 | $0.48 |
| 1/4 teaspoon dried marjoram | calculate | 0.3 | Great Value Taco Seasoning Mix, Original, 1 oz | 28.0 | $0.48 |
| 1/4 teaspoon dried basil leaves | calculate | 0.2 | Gourmet Garden Lightly Dried Basil | 9.0 | $3.99 |
| 1/8 teaspoon dried sage | calculate | 0.1 | Great Value Taco Seasoning Mix, Original, 1 oz | 28.0 | $0.48 |
| Black pepper, to taste | shop_only | 0.5 | El Guapo Non-GMO Whole Black Pepper, 0.62 oz Bag | 18.0 | $1.48 |

### 222377 — Frozen Strawberry Daiquiri
- Hestia: $52.23 | Ours: $6.74 | n_pkg: 5 | surplus: 310g | missing: 0/4
- Flags: WE_TOO_LOW

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| Superfine sugar, for rimming glass (optional) | shop_only | 10.0 | C&H Premium Pure Cane Granulated Sugar, 1 lb Box | 454.0 | $1.92 |
| 1 1/2 ounces light rum | calculate | 44.0 | Malibu Original Coconut Rum | 50.0 | $1.50 |
| 4 strawberries, hulled | calculate | 60.0 | Fresh Strawberries, 8.8 oz Container | 249.0 | $1.76 |
| 1 ounce fresh lime juice | calculate | 30.0 | Concord Foods Lime Juice, No Pulp, from Concentrate 4.5 | 133.0 | $0.98 |
| 1/2 ounce lime cordial (such as Rose's) | calculate | 15.0 | Sonic™ Singles to Go!® Zero-Sugar Cherry Limeade Drink  | 14.0 | $1.25 |
| 1/2 ounce simple syrup | calculate_via_base | 15.0 | C&H Premium Pure Cane Granulated Sugar, 1 lb Box | 454.0 | $1.92 |
| 1 cup ice, crushed | calculate_via_base | 200.0 | (none) | 0 | $0.00 |
| Lime slice, for garnish (optional) | shop_only | 10.0 | Mementa Inc (6 pack) Plain Jackfruit in Brine with Lime | 2381.0 | $11.27 |

### 219014 — Refreshing Purple Grapefruit Cocktail
- Hestia: $56.36 | Ours: $11.02 | n_pkg: 4 | surplus: 3646g | missing: 1/5
- Flags: WE_TOO_LOW

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 3 teaspoons white fine sugar, for rimming | shop_only | 13.8 | C&H Premium Pure Cane Granulated Sugar, 1 lb Box | 454.0 | $1.92 |
| 3 - 4 ice cubes | calculate_via_base | 60.0 | (none) | 0 | $0.00 |
| 1 1/2 ounces ruby red vodka | calculate | 44.0 | Tito's Handmade Vodka | 50.0 | $2.99 |
| 1 ounce blue curacao | calculate | 30.0 | (none) | 0 | $0.00 |
| 3/4 cup cranberry juice | calculate | 180.0 | Kroger® Cranberry Grape Juice Cocktail | 2014.0 | $2.99 |
| 1/4 cup lemon juice | calculate | 61.0 | Italia™ Garden Lemon Juice | 113.0 | $1.25 |
| 1/2 cup pink grapefruit juice | calculate | 115.0 | Ocean Spray® No Sugar Added 100% Grapefruit Juice | 1869.0 | $3.79 |
| 1 slice Meyer lemon, for garnish | shop_only | 10.0 | Wonderful Seedless Lemons | 454.0 | $2.49 |
| 1 slice pink grapefruit, for garnish | shop_only | 15.0 | Kroger® No Sugar Added Red Grapefruit Cup | 200.0 | $1.79 |

### 175271 — Hot Darn! Cocktail Shots
- Hestia: $53.50 | Ours: $10.07 | n_pkg: 5 | surplus: 595g | missing: 0/4
- Flags: WE_TOO_LOW

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 2 ounces rum | calculate | 59.0 | Malibu Original Coconut Rum | 50.0 | $1.50 |
| 2 ounces vodka | calculate | 59.0 | Four Freedoms Vodka Bottle – Smooth Distilled Vodka 40% | 372.0 | $3.99 |
| 1 ounce whiskey | calculate | 30.0 | Southern Comfort Original Whiskey - Whiskey Liquor | 50.0 | $1.00 |
| 4 ounces orange juice | calculate | 118.0 | Simply Pulp Free Orange Juice, 11.5 fl oz Bottle | 340.0 | $2.08 |

## MANY_PACKAGES — top 1


### 240442 — Fresh Spring Rolls with Peanut Sauce
- Hestia: $35.10 | Ours: $56.91 | n_pkg: 21 | surplus: 3089g | missing: 0/15
- Flags: MANY_PACKAGES

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 6 tablespoons creamy peanut butter | calculate | 90.0 | Kroger® Creamy Peanut Butter | 454.0 | $1.79 |
| 3/4 cup hoisin sauce | calculate | 180.0 | Kroger® Hoisin Sauce | 435.0 | $2.89 |
| 1/2 cup fresh lime juice | calculate | 121.0 | Concord Foods Lime Juice, No Pulp, from Concentrate 4.5 | 133.0 | $0.98 |
| 1/2 to 3/4 teaspoon cayenne pepper | calculate | 2.5 | Zatarain's No Artificial Flavors Cayenne Pepper, 3.75 o | 106.0 | $4.36 |
| 1/2 cup scallion, minced | calculate | 50.0 | Green Onions | 454.0 | $0.99 |
| 1/4 cup fresh basil, chopped | calculate | 6.0 | Fresh Basil, 0.5 oz Clamshell | 14.0 | $1.78 |
| 1/4 cup fresh cilantro, chopped | calculate | 4.0 | Fresh Produce, Whole Green Cilantro, 1 Bunch | 71.0 | $0.83 |
| 1/4 cup fresh mint, chopped | calculate | 10.0 | Tic Tac Freshmints On-the-Go Breath Mints Pocket-Sized  | 50.0 | $2.99 |
| 16 ounces seasoned tofu, finely diced | calculate | 454.0 | Cook’s Hickory Ham Steak | 535.0 | $5.00 |
| 3 cups cucumber, peeled, seeded, and finely chopped | calculate | 312.0 | Cucumber | 454.0 | $0.69 |
| 3 cups carrot, peeled and grated | calculate | 300.0 | Great Value Sliced Carrots, 14.5 oz Can | 411.0 | $0.96 |
| 3 cups napa cabbage, finely shredded | calculate | 327.0 | Napa Cabbage | 1361.0 | $7.47 |
| 55 to 60 sheets rice paper, 8 inches in diameter | calculate | 440.0 | (3 pack) Three Ladies Brand Rice Paper Spring Roll Wrap | 1021.0 | $11.94 |
| 4 ounces fresh chives | calculate | 113.0 | Fresh Chives, 0.5 oz Clamshell | 14.0 | $1.78 |
| 4 ounces scallions | calculate | 113.0 | Green Onions | 454.0 | $0.99 |

## HIGH_SURPLUS — top 5


### 139405 — Friar Tuck Cocktail
- Hestia: $31.67 | Ours: $8.30 | n_pkg: 3 | surplus: 6151g | missing: 0/3
- Flags: HIGH_SURPLUS

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 1/2 ounce hazelnut syrup | calculate | 15.0 | Great Value Original Syrup, 24 fl oz | 710.0 | $2.36 |
| 1 ounce lemon juice | calculate | 30.0 | Italia™ Garden Lemon Juice | 113.0 | $1.25 |
| 1 teaspoon grenadine | calculate | 6.7 | Rose's Grenadine Syrup | 5380.0 | $4.69 |
| Soda water, to fill | shop_only | 120.0 | Fresca® Sparkling Soda Water Fridge Pack Cans | 2223.0 | $6.99 |

### 332714 — Wholemeal Buckwheat Bread
- Hestia: $67.09 | Ours: $46.37 | n_pkg: 10 | surplus: 7975g | missing: 4/14
- Flags: HIGH_SURPLUS, MISSING_LINES

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 1/2 cup buckwheat flour | calculate | 85.0 | (none) | 0 | $0.00 |
| 1/2 cup millet flour | calculate | 100.0 | (none) | 0 | $0.00 |
| 3/4 cup quinoa flakes | calculate | 127.5 | (none) | 0 | $0.00 |
| 1/2 cup buckwheat groats | calculate | 85.0 | (10 pack) Sadaf Brand Buckwheat "Kasha", 16 oz, in a Se | 4536.0 | $25.60 |
| 1/2 teaspoon baking soda | calculate | 2.3 | Great Value Baking Soda, 1 lb | 454.0 | $0.92 |
| 1 teaspoon cream of tartar | calculate | 4.0 | Great Value Cream of Tartar, 2.75 oz | 78.0 | $2.54 |
| 1/2 teaspoon baking powder | calculate | 2.5 | Great Value Double Acting Baking Powder, 8.1 oz | 230.0 | $2.12 |
| 2 tablespoons flax seeds, ground | calculate | 14.0 | (none) | 0 | $0.00 |
| 1 teaspoon salt | calculate | 6.0 | Kroger® Salt | 739.0 | $0.79 |
| 1 teaspoon ground ginger | calculate | 1.8 | Private Selection® Ground Ginger Shaker | 41.0 | $4.49 |
| 1/2 teaspoon ground cloves | calculate | 1.1 | Great Value Ground Cloves, 2 oz | 57.0 | $2.27 |
| 1/2 teaspoon ground allspice | calculate | 0.9 | Kroger® Ground Allspice Shaker | 45.0 | $2.99 |
| 3/4 cup rice milk | calculate | 146.2 | Kern's Original Horchata Milk & Rice Drink, 59 Fl. Oz. | 1745.0 | $3.96 |
| 3/4 cup water | calculate | 180.0 | Kroger® Purified Bottle Water | 481.0 | $0.69 |
| 2 tablespoons sunflower seeds (optional) | shop_only | 30.0 | DAVID Sunflower Seeds, Original Flavor, 5.25 oz. | 149.0 | $1.97 |
| 2 tablespoons pumpkin seeds (optional) | shop_only | 30.0 | BIGS Simply Salted Pumpkin Seeds, 5 oz. | 142.0 | $2.46 |

### 393720 — Apple Pie Shooter
- Hestia: $26.51 | Ours: $7.78 | n_pkg: 3 | surplus: 742g | missing: 0/3
- Flags: HIGH_SURPLUS

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 1 ounce apple brandy (2 tablespoons) | calculate | 29.6 | White House Detox Apple Cider Vinegar, 16 fl oz | 473.0 | $3.12 |
| 1 ounce apple cider (2 tablespoons) | calculate | 29.6 | McCormick Apple Cider Finishing Sugar, 3.61 oz Bottle | 102.0 | $3.47 |
| 1 teaspoon whipped cream | calculate | 1.0 | Kroger® Reduced Fat Whipped Topping | 227.0 | $1.19 |
| Pinch of grated nutmeg | shop_only | 0.3 | Great Value Ground Nutmeg, 1.5 oz | 43.0 | $2.46 |

### 226099 — Linguica and Green Beans
- Hestia: $18.78 | Ours: $28.10 | n_pkg: 11 | surplus: 23423g | missing: 0/10
- Flags: HIGH_SURPLUS

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 1 lb fresh green beans, tipped and cut into bite-size pieces | calculate | 454.0 | Fresh Green Beans, Bag (26.5 oz / Bag Est.) | 751.0 | $2.95 |
| 1 small onion, diced | calculate | 120.0 | Jumbo Yellow Onions | 227.0 | $0.44 |
| 2 garlic cloves, minced | calculate | 6.0 | Garlic | 454.0 | $0.79 |
| 1/2 green bell pepper, diced | calculate | 75.0 | Fresh Large Green Bell Pepper | 454.0 | $0.89 |
| 2 potatoes, peeled and diced | calculate | 300.0 | Idahoan® Original Mashed Potatoes | 390.0 | $2.99 |
| 1/2 lb linguica sausage, cut into bite-size pieces | calculate | 227.0 | Bar-s Hot Links Sausage, 3 Lb, 16 Count | 21772.0 | $9.97 |
| 1/2 teaspoon ground allspice | calculate | 0.9 | Kroger® Ground Allspice Shaker | 45.0 | $2.99 |
| 1/8 teaspoon crushed red pepper flakes | calculate | 0.6 | Great Value Crushed Red Pepper, 1.75 oz | 50.0 | $1.44 |
| 1 can (8 oz) tomato sauce | calculate | 227.0 | Great Value Tomato Sauce, 8 oz Can | 227.0 | $0.48 |
| 1 tablespoon olive oil | calculate | 13.5 | GEM Extra Virgin Olive Oil for Seasoning and Finishing, | 251.0 | $4.68 |
| Salt, to taste | shop_only | 2.0 | Kroger® Salt | 739.0 | $0.79 |
| Black pepper, to taste | shop_only | 0.5 | El Guapo Non-GMO Whole Black Pepper, 0.62 oz Bag | 18.0 | $1.48 |

### 391924 — Caipirinha Cocktail
- Hestia: $5.26 | Ours: $13.19 | n_pkg: 2 | surplus: 2759g | missing: 1/3
- Flags: HIGH_SURPLUS

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 2 teaspoons granulated sugar | calculate | 8.4 | C&H Premium Pure Cane Granulated Sugar, 1 lb Box | 454.0 | $1.92 |
| 1 lime, cut into wedges | calculate | 67.0 | Mementa Inc (6 pack) Plain Jackfruit in Brine with Lime | 2381.0 | $11.27 |
| 2 - 2 1/2 ounces cachaça | calculate | 71.0 | (none) | 0 | $0.00 |

## MISSING_LINES — top 3


### 343276 — Chicken Parmesan with Homemade Marinara Sauce
- Hestia: $73.74 | Ours: $30.95 | n_pkg: 13 | surplus: 1729g | missing: 6/17
- Flags: MISSING_LINES

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 2 large boneless skinless chicken breasts, pounded to 1/2-inch thickness | calculate | 680.0 | Marketside Antibiotic-Free Boneless Skinless Chicken Br | 1361.0 | $7.57 |
| 1 package (3 oz) Shake 'n Bake original chicken breading | calculate | 85.0 | (none) | 0 | $0.00 |
| Extra virgin olive oil, for frying and in sauce | calculate | 120.0 | (none) | 0 | $0.00 |
| 1/2 cup freshly grated Parmigiano-Reggiano cheese | calculate | 61.0 | (none) | 0 | $0.00 |
| 1/3 cup minced fresh flat-leaf parsley, for garnish (optional) | calculate | 20.0 | Fresh Parsley, 0.5 oz Clamshell | 14.0 | $1.78 |
| 2 cans (14.5 oz each) Hunt's chunky crushed tomatoes | calculate | 820.0 | (none) | 0 | $0.00 |
| 2 cans (6 oz each) Hunt's tomato paste | calculate | 340.0 | Kroger® Tomato Paste | 340.0 | $1.39 |
| 1 can (14.5 oz) Italian-style stewed tomatoes | calculate | 411.0 | (none) | 0 | $0.00 |
| 6 cloves garlic, sliced in half or thirds | calculate | 18.0 | (none) | 0 | $0.00 |
| 1 teaspoon garlic juice (from jarred garlic) | calculate | 2.8 | Great Value Garlic Powder, 3.4 oz | 96.0 | $1.00 |
| 1 shallot, diced | calculate | 50.0 | Shallots | 45.0 | $0.40 |
| 2 tablespoons dried oregano | calculate | 6.0 | Great Value Oregano Leaves, 0.87 oz | 25.0 | $1.13 |
| 4 tablespoons dried Italian seasoning | calculate | 12.0 | McCormick Italian Seasoning, 1.31 oz Bottle | 37.0 | $5.22 |
| 1 teaspoon dried basil | calculate | 0.7 | Great Value Basil Leaves, 0.8 oz | 23.0 | $1.13 |
| 1 tablespoon Splenda granular (sugar substitute) | calculate | 12.0 | Splenda ZERO Stevia Liquid Zero Calorie Sweetener, 3.38 | 100.0 | $6.88 |
| 1/2 teaspoon salt | calculate | 3.0 | Kroger® Salt | 739.0 | $0.79 |
| 1/2 teaspoon black pepper | calculate | 1.4 | El Guapo Non-GMO Whole Black Pepper, 0.62 oz Bag | 18.0 | $1.48 |

### 332714 — Wholemeal Buckwheat Bread
- Hestia: $67.09 | Ours: $46.37 | n_pkg: 10 | surplus: 7975g | missing: 4/14
- Flags: HIGH_SURPLUS, MISSING_LINES

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 1/2 cup buckwheat flour | calculate | 85.0 | (none) | 0 | $0.00 |
| 1/2 cup millet flour | calculate | 100.0 | (none) | 0 | $0.00 |
| 3/4 cup quinoa flakes | calculate | 127.5 | (none) | 0 | $0.00 |
| 1/2 cup buckwheat groats | calculate | 85.0 | (10 pack) Sadaf Brand Buckwheat "Kasha", 16 oz, in a Se | 4536.0 | $25.60 |
| 1/2 teaspoon baking soda | calculate | 2.3 | Great Value Baking Soda, 1 lb | 454.0 | $0.92 |
| 1 teaspoon cream of tartar | calculate | 4.0 | Great Value Cream of Tartar, 2.75 oz | 78.0 | $2.54 |
| 1/2 teaspoon baking powder | calculate | 2.5 | Great Value Double Acting Baking Powder, 8.1 oz | 230.0 | $2.12 |
| 2 tablespoons flax seeds, ground | calculate | 14.0 | (none) | 0 | $0.00 |
| 1 teaspoon salt | calculate | 6.0 | Kroger® Salt | 739.0 | $0.79 |
| 1 teaspoon ground ginger | calculate | 1.8 | Private Selection® Ground Ginger Shaker | 41.0 | $4.49 |
| 1/2 teaspoon ground cloves | calculate | 1.1 | Great Value Ground Cloves, 2 oz | 57.0 | $2.27 |
| 1/2 teaspoon ground allspice | calculate | 0.9 | Kroger® Ground Allspice Shaker | 45.0 | $2.99 |
| 3/4 cup rice milk | calculate | 146.2 | Kern's Original Horchata Milk & Rice Drink, 59 Fl. Oz. | 1745.0 | $3.96 |
| 3/4 cup water | calculate | 180.0 | Kroger® Purified Bottle Water | 481.0 | $0.69 |
| 2 tablespoons sunflower seeds (optional) | shop_only | 30.0 | DAVID Sunflower Seeds, Original Flavor, 5.25 oz. | 149.0 | $1.97 |
| 2 tablespoons pumpkin seeds (optional) | shop_only | 30.0 | BIGS Simply Salted Pumpkin Seeds, 5 oz. | 142.0 | $2.46 |

### 423664 — Fagito Me Maratho (Stewed Fennel and Onions with Crispy
- Hestia: $33.28 | Ours: $15.21 | n_pkg: 6 | surplus: 1090g | missing: 3/8
- Flags: MISSING_LINES

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 3/4 cup olive oil, divided | calculate | 165.0 | GEM Extra Virgin Olive Oil for Seasoning and Finishing, | 251.0 | $4.68 |
| 4 cups diced stale bread (whole wheat, sourdough, or multigrain) | calculate | 320.0 | (none) | 0 | $0.00 |
| 2 large onions, halved and sliced into thick half-moons | calculate | 400.0 | Jumbo Yellow Onions | 227.0 | $0.44 |
| 4 fennel bulbs, trimmed and sliced | calculate | 800.0 | Fresh Vegetable Medley Blend, 32 oz | 907.0 | $5.98 |
| 1/2 cup sweet white wine | calculate | 17.5 | Vendange Pinot Grigio White Wine, 500ml Carton | 500.0 | $2.98 |
| 1/2 cup water | calculate | 120.0 | Kroger® Purified Bottle Water | 481.0 | $0.69 |
| 1 tablespoon fennel seeds, crushed | calculate | 6.0 | (none) | 0 | $0.00 |
| Salt, to taste | shop_only | 2.0 | Kroger® Salt | 739.0 | $0.79 |
| Black pepper, to taste | shop_only | 0.5 | El Guapo Non-GMO Whole Black Pepper, 0.62 oz Bag | 18.0 | $1.48 |
| 1 cup chopped fennel leaves and tender stalks, plus 2 tablespoons reserved  | calculate | 30.0 | (none) | 0 | $0.00 |

## HESTIA_ZERO — top 5


### 108535 — Easy Whole Wheat Bannock Bread with Dried Fruit and See
- Hestia: $0.00 | Ours: $34.30 | n_pkg: 14 | surplus: 8511g | missing: 0/14
- Flags: HESTIA_ZERO

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 1 cup whole wheat flour | calculate | 120.0 | Kroger® Traditional Whole Wheat Flour | 2268.0 | $2.50 |
| 3/4 cup all-purpose white flour | calculate | 118.5 | Great Value All-Purpose Unbleached Flour, 5 lb Bag | 2268.0 | $1.97 |
| 1 cup wheat bran | calculate | 192.0 | Bob's Red Mill Wheat Bran, 8 oz. | 227.0 | $2.29 |
| 3/4 cup wheat germ | calculate | 144.0 | Kretschmer Original Toasted Wheat Germ, 4g Plant Protei | 340.0 | $4.58 |
| 1 teaspoon salt | calculate | 6.0 | Kroger® Salt | 739.0 | $0.79 |
| 1 teaspoon baking soda | calculate | 4.6 | Great Value Baking Soda, 1 lb | 454.0 | $0.92 |
| 1 teaspoon baking powder | calculate | 5.0 | Great Value Double Acting Baking Powder, 8.1 oz | 230.0 | $2.12 |
| 1/4 cup lard | calculate | 51.2 | John Morrell® Snow Cap Edible Lard | 454.0 | $2.49 |
| 1 1/2 cups buttermilk | calculate | 367.5 | Prairie Farms Bulgarian Style Whole Buttermilk, Half Ga | 1814.0 | $4.79 |
| 2 tablespoons sorghum molasses | calculate | 40.0 | Grandma's Original Molasses, Unsulphured, 12 fl oz Jar | 355.0 | $3.94 |
| 1/2 cup dried currants | calculate | 72.0 | Great Value Sun-Dried Raisins 6 Pack, 6 - 1 oz (28g) Ca | 170.0 | $1.48 |
| 1/2 cup dried cherries | calculate | 80.0 | Great Value Sweetened Dried Cherries, 5 oz | 142.0 | $3.28 |
| 1/2 cup dried shredded coconut | calculate | 46.5 | Kuii Drinks Coconut Milk with Nata de Coco, Original, 2 | 290.0 | $1.18 |
| 1 cup sunflower seeds | calculate | 140.0 | DAVID Sunflower Seeds, Original Flavor, 5.25 oz. | 149.0 | $1.97 |

### 345484 — Cranberry-Hazelnut Biscotti
- Hestia: $0.00 | Ours: $29.76 | n_pkg: 11 | surplus: 4099g | missing: 2/13
- Flags: HESTIA_ZERO

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 4 1/2 cups all-purpose flour | calculate | 562.5 | Great Value All-Purpose Unbleached Flour, 5 lb Bag | 2268.0 | $1.97 |
| 1 teaspoon baking soda | calculate | 4.6 | Great Value Baking Soda, 1 lb | 454.0 | $0.92 |
| 1 teaspoon baking powder | calculate | 5.0 | Great Value Double Acting Baking Powder, 8.1 oz | 230.0 | $2.12 |
| 1/2 teaspoon salt | calculate | 3.0 | Kroger® Salt | 739.0 | $0.79 |
| 2 teaspoons fennel seeds, slightly mashed | calculate | 6.0 | (none) | 0 | $0.00 |
| 2 cups granulated sugar | calculate | 400.0 | C&H Premium Pure Cane Granulated Sugar, 1 lb Box | 454.0 | $1.92 |
| 4 tablespoons unsalted butter, melted and cooled | calculate | 56.8 | Land O Lakes Salted Butter in Half Sticks, 4 Half Stick | 227.0 | $2.68 |
| 5 eggs, beaten | calculate | 250.0 | Kroger® Medium Grade A White Eggs | 626.0 | $1.59 |
| 2 teaspoons vanilla extract | calculate | 8.4 | Watkins Pure Lemon Extract, 2 oz (Liquid, Ambient, Cont | 59.0 | $4.33 |
| 1 orange, zested (about 1 tablespoon) | calculate | 6.0 | (none) | 0 | $0.00 |
| 1 1/2 cups dried cranberries | calculate | 240.0 | Great Value Sweetened Dried Cranberries, 12 oz | 340.0 | $3.54 |
| 1/2 cup hazelnuts, chopped | calculate | 60.0 | Planters Lightly Salted Mixed Nuts with Peanuts, Almond | 292.0 | $7.12 |
| 1/2 cup white chocolate, melted | calculate | 90.0 | M&M's Lemon Merengue Pie White Chocolate Candy - 3.22 o | 91.0 | $2.78 |

### 399699 — Chocolate Chunk Pecan Pie
- Hestia: $0.00 | Ours: $29.39 | n_pkg: 11 | surplus: 5250g | missing: 0/14
- Flags: HESTIA_ZERO

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 1 1/2 cups unbleached all-purpose flour | calculate | 187.5 | Great Value All-Purpose Unbleached Flour, 5 lb Bag | 2268.0 | $1.97 |
| 1 tablespoon dry buttermilk (optional) | shop_only | 7.0 | Kroger® Cultured 1% Lowfat Buttermilk Pint | 485.0 | $1.19 |
| 1/4 teaspoon salt | calculate | 1.5 | Kroger® Salt | 739.0 | $0.79 |
| 1/4 teaspoon baking powder | calculate | 1.2 | Great Value Double Acting Baking Powder, 8.1 oz | 230.0 | $2.12 |
| 3 tablespoons vegetable shortening | calculate | 38.4 | Crisco All-Vegetable Shortening Stick, 6.7oz, 1 Stick | 190.0 | $3.38 |
| 5 tablespoons cold butter | calculate | 71.0 | Land O Lakes Salted Butter in Half Sticks, 4 Half Stick | 227.0 | $2.68 |
| 1 teaspoon white vinegar | calculate | 5.0 | Heinz All Natural Distilled White Vinegar 5% Acidity, 3 | 946.0 | $2.66 |
| 3 to 4 tablespoons ice water | calculate_via_base | 54.0 | (none) | 0 | $0.00 |
| 2 large eggs, room temperature | calculate | 100.0 | Kroger® Medium Grade A White Eggs | 626.0 | $1.59 |
| 1 cup sugar | calculate | 200.0 | C&H Premium Pure Cane Granulated Sugar, 1 lb Box | 454.0 | $1.92 |
| 1/4 teaspoon salt | calculate | 1.5 | Kroger® Salt | 739.0 | $0.79 |
| 1/2 cup unbleached all-purpose flour | calculate | 62.5 | Great Value All-Purpose Unbleached Flour, 5 lb Bag | 2268.0 | $1.97 |
| 1/2 cup butter, melted and cooled | calculate | 113.5 | Land O Lakes Salted Butter in Half Sticks, 4 Half Stick | 227.0 | $2.68 |
| 2 teaspoons vanilla extract | calculate | 8.4 | Watkins Pure Lemon Extract, 2 oz (Liquid, Ambient, Cont | 59.0 | $4.33 |
| 1 1/3 cups bittersweet chocolate, chopped or in chunks | calculate | 227.0 | Snickers Fun Size Chocolate Candy Bars - 2.6 oz (5 pack | 369.0 | $1.47 |
| 2/3 cup pecans, diced and toasted | calculate | 66.0 | Diamond of California Chopped Pecans 8 oz | 227.0 | $6.48 |
| 2/3 cup pecan halves, for topping | shop_only | 70.0 | Planters Lightly Salted Mixed Nuts with Peanuts, Almond | 292.0 | $7.12 |

### 4525 — Brownie Cheesecake
- Hestia: $0.00 | Ours: $28.46 | n_pkg: 15 | surplus: 3734g | missing: 0/13
- Flags: HESTIA_ZERO

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 1 (20 ounce) package fudge brownie mix | calculate | 567.0 | Great Value Fudge Brownie Mix, 18.3 oz Box | 519.0 | $1.24 |
| 1 tablespoon water | calculate | 15.0 | Kroger® Purified Bottle Water | 481.0 | $0.69 |
| 1 teaspoon vegetable oil | calculate | 4.5 | Smart Way™ Vegetable Oil | 435.0 | $1.49 |
| 1 (4 ounce) jar prune baby food | calculate | 113.0 | Gerber 2nd Foods Natural for Baby Wonder Foods Banana B | 113.0 | $1.39 |
| 1 egg white | calculate | 33.0 | Bob Evans Cage Free 100% Liquid Egg Whites, 16 oz | 454.0 | $3.77 |
| Vegetable oil cooking spray, for coating pan | shop_only | 5.0 | (none) | 0 | $0.00 |
| 1 cup nonfat cottage cheese | calculate | 145.0 | Daisy 4% Cottage Cheese with Peach | 172.0 | $1.79 |
| 16 ounces neufchatel cheese, softened | calculate | 454.0 | Heritage Farms American Sliced Cheese | 340.0 | $1.89 |
| 8 ounces fat-free cream cheese, softened | calculate | 227.0 | Kroger® Original Cream Cheese | 454.0 | $3.19 |
| 1 1/2 cups sugar | calculate | 300.0 | C&H Premium Pure Cane Granulated Sugar, 1 lb Box | 454.0 | $1.92 |
| 1 tablespoon vanilla extract | calculate | 13.0 | Watkins Pure Lemon Extract, 2 oz (Liquid, Ambient, Cont | 59.0 | $4.33 |
| 1/4 teaspoon salt | calculate | 1.5 | Kroger® Salt | 739.0 | $0.79 |
| 3 eggs | calculate | 150.0 | Kroger® Medium Grade A White Eggs | 626.0 | $1.59 |
| 1/4 cup semisweet chocolate, mini morsels | calculate | 43.0 | Junior Mints Creamy Mints in Dark Chocolate Eggs Easter | 95.0 | $1.25 |

### 49770 — Beet Jam
- Hestia: $0.00 | Ours: $27.79 | n_pkg: 10 | surplus: 1278g | missing: 0/6
- Flags: HESTIA_ZERO

| ingredient | decision | grams | SKU | pkg_g | $/pkg |
|---|---|---:|---|---:|---:|
| 4 lbs beets, peeled and grated | calculate | 1814.0 | Kroger Whole Beets - 15oz can | 422.0 | $1.09 |
| 3 lbs sugar | calculate | 1361.0 | Smart Way 4lb Granulated Sugar Bag | 1814.0 | $2.49 |
| 2 ounces fresh gingerroot, finely grated | calculate | 57.0 | Dorot® Gardens Frozen Crushed Ginger Cubes | 73.0 | $2.89 |
| 3 lemons, juiced and zested | calculate | 180.0 | Wonderful Seedless Lemons | 454.0 | $2.49 |
| 1⁄2 lb almonds, chopped | calculate | 227.0 | Simple Truth® Sliced Almonds | 340.0 | $6.99 |
| 1⁄2 lb walnuts, chopped | calculate | 227.0 | Hammons Black Walnuts Large Pieces, 12 oz | 355.0 | $7.48 |