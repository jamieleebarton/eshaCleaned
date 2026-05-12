# Codex Taxonomy Issue Inventory

Source: `codex_full_corpus_audit.csv`
Issue rows: `9,108`
Unique FDC ids: `8,736`

This report is a concrete failure-pattern inventory, not a broad outlier score.

## Issue Counts

### frozen_storage_department_policy_split

- rows: `4,213`
- severity: `medium`
- confidence: `medium`
- action: `policy_decision`
- likely fix: Choose whether frozen vegetable/fruit BFCs should live under Frozen or under Produce with frozen as storage metadata.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2474112 | Frozen Vegetables | Produce > Vegetables > Vegetable Blend > Corn Black Beans Onions Green Peppers Red | CORN, BLACK BEANS, ONIONS, GREEN PEPPERS, RED PEPPERS FIESTA CORN BLEND |
| 2109861 | Frozen Vegetables | Produce > Vegetables > Black Beans > Plain | BLACK BEANS |
| 1378667 | Frozen Vegetables | Produce > Vegetables > Black Beans > Plain | BLACK BEANS |
| 2160117 | Frozen Vegetables | Produce > Vegetables > Vegetable Blend > Southwest | SOUTHWEST STYLE A BLEND OF BLACK BEANS, CORN, LENTILS, WHOLE GRAINS, RED BELL PEPPERS AND LENTIL ZUCCHINI ORZO PASTA WITH A ZESTY SAUCE POWE |
| 1633848 | Frozen Vegetables | Produce > Vegetables > Vegetable Blend > Carrots Sugar Snap Peas Black Beans Edamame > Sliced | LIGHTLY SAUCED HEALTHY WEIGHT SLICED CARROTS, SUGAR SNAP PEAS, BLACK BEANS AND EDAMAME LIGHTLY TOSSED WITH BUTTER SAUCE, LIGHTLY SAUCED |
| 2426379 | Frozen Vegetables | Produce > Vegetables > Vegetable Blend > Black Barley Chickpeas Cauliflower Green Beans Red Bell Pepper > Organic | BLACK BARLEY, CHICKPEAS, CAULIFLOWER, GREEN BEANS & RED BELL PEPPER POWERED BY PLANTS GRAINS + VEGETABLES + LEGUMES, BLACK BARLEY, CHICKPEAS |
| 2383849 | Frozen Vegetables | Produce > Vegetables > Vegetable Blend > Southwest | THE ULTIMATE SOUTHWEST BLEND PETITE SUPER SWEET CORN, BLACK BEANS, MILD POBLANO CHILIES, RED PEPPERS, ONIONS, THE ULTIMATE SOUTHWEST BLEND |
| 2402165 | Frozen Vegetables | Produce > Vegetables > Vegetable Blend > Organic | ORGANIC TRI-BEAN BLEND DARK RED KIDNEY BEANS, PINTO BEANS & BLACK BEANS |

### pickles_bfc_contains_finished_salads

- rows: `1,011`
- severity: `medium`
- confidence: `medium`
- action: `source_conflict_review`
- likely fix: Review BFC/title conflict. Title says salad; BFC says pickles/olives/peppers/relishes.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2158720 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Chicken Taco Salad > Salsa Tomate Vinaigrette Sour Cream Drizzle | CHICKEN TACO SALAD WITH SALSA TOMATE VINAIGRETTE AND SOUR CREAM DRIZZLE, CHICKEN TACO |
| 2031265 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Spinach Bacon Sweet Onion Dijon Vinaigrette | SPINACH SALAD WITH BACON |
| 1866686 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Beef Jalapeno Ranch | SALAD WITH BEEF, JALAPENO RANCH |
| 2405146 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Beef Jalapeno Ranch | JALAPENO RANCH SALAD WITH BEEF, JALAPENO RANCH |
| 2176097 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Caesar Salad > Plain | TRADITIONAL CAESAR SALAD |
| 2541529 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Carnitas Cotija Cheese Roasted Corn BBQ Ranch | SALAD WITH CARNITAS COTIJA CHEESE & ROASTED CORN, BBQ |
| 1913424 | Pickles, Olives, Peppers & Relishes | Meal > Salads > BBQ Ranch > Chopped | CHOPPED SALAD, BARBECUE RANCH |
| 2065267 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Basil Buttermilk > Chopped | CIAO CHOPPED SALAD |

### cookie_cracker_sandwich_routed_as_meal

- rows: `730`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Keep sandwich cookies, sandwich cremes, sandwich biscuits, and sandwich crackers on cookie/cracker shelves, not Meal > Sandwiches.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2077623 | Crackers & Biscotti | Meal > Sandwiches > Sandwich > Cinnamon Roll Cinnamon | LANCE, QUICK START BREAKFAST BISCUIT SANDWICHES, CINNAMON ROLL, CINNAMON ROLL |
| 2077638 | Cookies & Biscuits | Meal > Sandwiches > Cookies > Blueberry | LANCE, QUICK STARTS, BREAKFAST BISCUIT SANDWICHES, BLUEBERRY MUFFIN, BLUEBERRY MUFFIN |
| 2100359 | Cookies & Biscuits | Meal > Sandwiches > Sandwich > Cinnamon Roll Cinnamon > Whole Grain | BREAKFAST BISCUITS SANDWICHES, CINNAMON ROLL |
| 2056297 | Crackers & Biscotti | Meal > Sandwiches > Cheese and Crackers Pack > Bacon Cheddar | LANCE, QUICK STARTS, BREAKFAST BISCUIT SANDWICHES, BACON CHEDDAR, BACON CHEDDAR |
| 2018317 | Crackers & Biscotti | Meal > Sandwiches > Breakfast Sandwich > Bacon Cheddar | LANCE, QUICK STARTS, BREAKFAST BISCUIT SANDWICHES, BACON CHEDDAR |
| 429225 | Cookies & Biscuits | Meal > Sandwiches > Cookies > Bourbon Creams Chocolate | BOLANDS, BOURBON CREAMS SANDWICH BISCUITS, CRUNCHY CHOCLATE |
| 2619665 | Cookies & Biscuits | Meal > Sandwiches > Cookies > Pumpkin Cheesecake | PUMPKIN CHEESECAKE SANDWICH CREMES, PUMPKIN CHEESECAKE |
| 2545655 | Cookies & Biscuits | Meal > Sandwiches > Cookies > Pumpkin Spice Cheesecake Sandwich | PUMPKIN SPICE CHEESECAKE SANDWICH CREMES, PUMPKIN SPICE CHEESECAKE |

### baking_decoration_routed_as_snack_candy

- rows: `678`
- severity: `medium`
- confidence: `medium`
- action: `policy_decision`
- likely fix: Decide whether edible decorations, candy melts, baking bars, sprinkles, and dessert toppings should remain Pantry baking decorations even when candy-like.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 1520343 | Baking Decorations & Dessert Toppings | Snack > Candy > Hard Candy > Peppermint | ZITNER'S, PEPPERMINT CREAM |
| 2030465 | Baking Decorations & Dessert Toppings | Snack > Candy > Hard Candy > Cinnamon | KROGER, CINNAMON GEMS DESSERT TOPPINGS |
| 2429462 | Baking Decorations & Dessert Toppings | Snack > Candied Fruit > Cacao Nibs Sweet > Organic | SWEET CHOCOLATE NIBS, CACAO NIBS |
| 1885453 | Baking Decorations & Dessert Toppings | Snack > Candy > Hard Candy > Mint | WILTON, MICKEY MOUSE CLUBHOUSE ICE DECORATIONS |
| 2388649 | Baking Decorations & Dessert Toppings | Snack > Chocolate Candy > Chocolate Bar > Unsweetened | UNSWEETENED CHOCOLATE 100% CACAO BAKING BARS, UNSWEETENED CHOCOLATE |
| 1864310 | Baking Decorations & Dessert Toppings | Snack > Chocolate Candy > Chocolate Bar > Organic > Unsweetened | SUNSPIRE, ORGANIC BAKING BAR, UNSWEETENED CHOCOLATE, UNSWEETENED CHOCOLATE |
| 2404427 | Baking Decorations & Dessert Toppings | Snack > Chocolate Candy > Chocolate Bar > Organic > Unsweetened | 100% CACAO UNSWEETENED CHOCOLATE BAKING BAR, UNSWEETENED CHOCOLATE |
| 2505571 | Baking Decorations & Dessert Toppings | Snack > Chocolate Candy > Chocolate Bar > Organic > Unsweetened | UNSWEETENED CHOCOLATE BAKING BAR, UNSWEETENED CHOCOLATE |

### canned_vegetable_routed_to_fresh_produce

- rows: `630`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route Canned Vegetables BFC rows to Pantry canned/pickled vegetable shelves unless title evidence proves fresh produce.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2429353 | Canned Vegetables | Produce > Vegetables > Vegetable Blend > Plain | CLASSIC STYLE VEGETABLE & BEAN BLENDS, CLASSIC STYLE |
| 2429354 | Canned Vegetables | Produce > Vegetables > Vegetable Blend > California | CALIFORNIA STYLE VEGETABLE & BEAN BLENDS, CALIFORNIA STYLE |
| 2572364 | Canned Vegetables | Produce > Vegetables > Vegetable Blend > Carrots Green Beans Sweet Peas Corn Lima | VEGETABLE BLEND CARROTS, GREEN BEANS, SWEET PEAS, CORN AND LIMA BEANS, VEGETABLE BLEND |
| 2429352 | Canned Vegetables | Produce > Vegetables > Vegetable Blend > Mexican | MEXICAN STYLE VEGETABLE & BEAN BLENDS, MEXICAN STYLE |
| 1571102 | Canned Vegetables | Produce > Vegetables > Potatoes > Scalloped Ham Cheddar | SCALLOPED POTATOES |
| 2080081 | Canned Vegetables | Produce > Vegetables > Potatoes > Sweet | YAMS MASHED SWEET POTATO |
| 2632488 | Canned Vegetables | Produce > Vegetables > Potatoes > Sweet Maple | MASHED SWEET POTATOES |
| 2288332 | Canned Vegetables | Produce > Vegetables > Potatoes > Sweet | BAKED SWEET POTATOES |

### nut_seed_butter_routed_to_dairy_butter

- rows: `463`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route nut/seed/granola/oat butters to Pantry nut butter/spread shelves; reserve Dairy > Butter for dairy butter.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 1988878 | Nut & Seed Butters | Dairy > Butter > Granola Chocolate > Gluten Free | CHOCOLATE GRANOLA BUTTER, CHOCOLATE |
| 2643134 | Nut & Seed Butters | Dairy > Butter > Granola Vanilla > Gluten Free | VANILLA GRANOLA BUTTER, VANILLA |
| 2640472 | Nut & Seed Butters | Dairy > Butter > Granola > Gluten Free | ORIGINAL GRANOLA BUTTER, ORIGINAL |
| 1988891 | Nut & Seed Butters | Dairy > Butter > Granola Maple Cinnamon > Gluten Free | ORIGINAL GRANOLA BUTTER, ORIGINAL |
| 1891600 | Nut & Seed Butters | Dairy > Butter > Walnut Butter > Nut Oatmeal Cookie | WALNUT BUTTER, OATMEAL COOKIE |
| 1942263 | Nut & Seed Butters | Dairy > Butter > Walnut Butter > Nut Oatmeal Cookie | OATMEAL COOKIE WALNUT BUTTER, OATMEAL COOKIE |
| 2062089 | Nut & Seed Butters | Dairy > Butter > Mixed Nut Butter > Raisin Pecan Brown Sugar Cinnamon Oat Vanilla Coconut > Gluten Free | EAT YOUR OATMEAL COCONUT BUTTER |
| 1897206 | Nut & Seed Butters | Dairy > Butter > Nut Cashew Chia > Gluten Free > Vegan | LEAF CUISINE, NOT CREAM CHEESE SPREAD, CLASSIC PLAIN, CLASSIC PLAIN |

### frozen_appetizer_routed_to_non_frozen_sandwich

- rows: `428`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route frozen breakfast/appetizer sandwich forms under Frozen, not generic Meal > Sandwiches.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2630458 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Breakfast Sandwich > Blueberry Pancake Sausage Egg Cheese | BLUEBERRY GRILLED CAKE SAUSAGE, EGG AND CHEESE SANDWICHES, BLUEBERRY |
| 2630455 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Breakfast Sandwich > Griddle Pancakes Egg Cheese Sausage Maple | SWEET MAPLE GRIDDLE PANCAKES, EGG WITH CHEESE & SAUSAGE SANDWICHES, SWEET MAPLE |
| 2037997 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Breakfast Sandwich > Sausage Egg Cheese | SAUSAGE, EGG & CHEESE ON PANCAKES GRIDDLECAKE SANDWICHES, SAUSAGE, EGG & CHEESE |
| 2581430 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Breakfast Sandwich > Maple Pancakes Sausage | MAPLE PANCAKES & SAUSAGE GRIDDLE CAKE SANDWICHES, MAPLE PANCAKES & SAUSAGE |
| 2581345 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Breakfast Sandwich > Sausage Egg Cheese Maple | SAUSAGE, EGG AND CHEESE MAPLE GRIDDLE CAKE SANDWICHES, SAUSAGE, EGG AND CHEESE |
| 2623955 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Breakfast Sandwich > Maple Griddle Cake Sausage Egg Cheese | MAPLE GRIDDLE CAKE SAUSAGE, EGG AND CHEESE SANDWICHES, MAPLE |
| 2153598 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Breakfast Sandwich > Italian Sausage Crumble Creamy Chao Cheese | ITALIAN SAUSAGE CRUMBLE & CREAMY CHAO CHEESE PANCAKE SANDWICH, ITALIAN SAUSAGE CRUMBLE & CREAMY CHAO CHEESE |
| 2157750 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Sandwich > Triple Cheese > Stuffed | TRIPLE CHEESE STIX CREAMY THREE-CHEESE BLEND STUFFED INTO A CRISPY CRUST SANDWICHES, TRIPLE CHEESE STIX |

### frozen_vegetable_routed_to_canned_pantry

- rows: `356`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route Frozen Vegetables rows away from Pantry > Canned Vegetables; use a frozen vegetable shelf or an explicit frozen-storage policy.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2631492 | Frozen Vegetables | Pantry > Canned Vegetables > Green Beans > French Cut | FRENCH CUT GREEN BEANS |
| 2615578 | Frozen Vegetables | Pantry > Canned Vegetables > Green Beans > Plain | CUT GREEN BEANS |
| 2616956 | Frozen Vegetables | Pantry > Canned Vegetables > Green Beans > Plain | CUT GREEN BEANS |
| 2631511 | Frozen Vegetables | Pantry > Canned Vegetables > Green Beans > Plain | STEAM-IN-BAG CLASSIC VEGETABLES CUT GREEN BEANS |
| 2565782 | Frozen Vegetables | Pantry > Canned Vegetables > Green Beans > French > Organic | ORGANIC BABY FRENCH BEANS HARICOT VERT |
| 2032173 | Frozen Vegetables | Pantry > Canned Vegetables > Green Beans > Plain | CUT GREEN BEANS |
| 2031701 | Frozen Vegetables | Pantry > Canned Vegetables > Green Beans > Plain | KROGER, CUT GREEN BEANS |
| 2037010 | Frozen Vegetables | Pantry > Canned Vegetables > Green Beans > Plain | WHITE ROSE, CUT GREEN BEANS |

### soup_or_chowder_routed_as_seafood

- rows: `327`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route clam/crab/lobster chowders and seafood soups to soup/chowder shelves; keep seafood as a variant/component.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2051944 | Other Soups | Meat & Seafood > Shellfish > Clam > Plain | WHOLE FOODS MARKET, CLAM CHOWDER |
| 2386507 | Other Soups | Meat & Seafood > Shellfish > Clam > Plain | COASTAL STYLE CLAM CHOWDER, COASTAL STYLE CLAM |
| 2023165 | Other Soups | Meat & Seafood > Shellfish > Clam > Plain | CLAM CHOWDER SOUP |
| 2121796 | Other Soups | Meat & Seafood > Shellfish > Clam > Plain | CLAM CHOWDER |
| 1902735 | Canned Soup | Meat & Seafood > Shellfish > Clam > Plain | CLAM CHOWDER |
| 2014537 | Other Soups | Meat & Seafood > Fish > Salmon > Wild > Smoked | SEABEAR WILD SALMON, SMOKED SALMON CHOWDER |
| 1630475 | Canned Soup | Meat & Seafood > Shellfish > Clam > Plain | CLAM CHOWDER |
| 2150388 | Canned Soup | Meat & Seafood > Shellfish > Clam > New England | NEWENGLANDSTYLE CLAM CHOWDER, NEWENGLANDSTYLE |

### pickles_relishes_routed_as_sandwich

- rows: `93`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route sandwich stuffers, bread-and-butter pickles, olives, peppers, and relishes to Pantry pickle/relish shelves.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2151240 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Sandwich > Honey Ham Turkey Cream Cheese | COMBO PINWHEEL PLATTER |
| 2413604 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Bread And Butter Sandwich Slice | BREAD & BUTTER SANDWICH STUFFERS, BREAD & BUTTER |
| 2559957 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Bread And Butter Sweet | OLD-FASHIONED SWEET BREAD & BUTTER SANDWICH STUFFERS |
| 2023133 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Bread And Butter > No Sugar Added | BREAD & BUTTER NO SUGAR ADDED SANDWICH STUFFERS, BREAD & BUTTER |
| 2269661 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Bread Butter Sweet | BREAD & BUTTER OLD-FASHIONED SWEET SANDWICH STUFFERS, BREAD & BUTTER |
| 2028438 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Bread And Butter Sweet | BREAD & BUTTER OLD-FASHIONED SWEET SANDWICH STUFFERS, BREAD & BUTTER |
| 2024995 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Bread And Butter Sandwich Slice | BREAD & BUTTER SANDWICH SLIMS |
| 1853939 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Bread Butter | BREAD & BUTTER SANDWICHES SLICES |

### dip_or_salsa_routed_as_seafood

- rows: `74`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route crab/shrimp/artichoke dips to Pantry > Dips & Spreads or Pantry > Dips & Salsa; seafood belongs as a variant/component.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2096584 | Dips & Salsa | Meat & Seafood > Shellfish > Crab > Jalapeno | JALAPENO SEAFOOD CRAB DIP |
| 2396853 | Dips & Salsa | Meat & Seafood > Shellfish > Shrimp > Spicy | SPICY SHRIMP DIP, SPICY |
| 2424060 | Dips & Salsa | Meat & Seafood > Shellfish > Crab > Artichoke Jalapeno | ARTICHOKE JALAPENO CRAB DIP, ARTICHOKE JALAPENO |
| 1945645 | Dips & Salsa | Meat & Seafood > Shellfish > Crab > Flamin Hot Buffalo | REGGIE'S SEAFOOD CRAB DIP, FLAMIN' HOT BUFFALO |
| 2485407 | Dips & Salsa | Meat & Seafood > Shellfish > Crab > Jalapeno | JALAPENO MICROWAVABLE CRAB DIP, JALAPENO |
| 1899460 | Dips & Salsa | Meat & Seafood > Shellfish > Shrimp > Jalapeno Cheese | JALAPENO CHEESE AND SHRIMP DIP |
| 2052619 | Dips & Salsa | Meat & Seafood > Shellfish > Crab > Jalapeno | KIERAN'S, JALAPENO CRAB DIP |
| 2302938 | Dips & Salsa | Meat & Seafood > Shellfish > Crab > Green Onion | CRAB & GREEN ONION DIP, CRAB & GREEN ONION |

### salad_kit_policy_split

- rows: `38`
- severity: `medium`
- confidence: `medium`
- action: `policy_decision`
- likely fix: Decide whether all salad kits belong under Produce > Salad Kits or whether protein/meal kits belong under Meal > Salad Kits.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2548306 | Lunch Snacks & Combinations | Meal > Salads > Lunch Kit > Chunk White Chicken | CHUNK WHITE PREMIUM CHICKEN SALAD KIT, CHUNK WHITE |
| 2548330 | Lunch Snacks & Combinations | Meal > Salads > Lunch Kit > Chunk White Chicken | CHUNK WHITE PREMIUM CHICKEN SALAD KIT, CHUNK WHITE |
| 2651634 | Pickles, Olives, Peppers & Relishes | Meal > Salad Kits > Avocado Ranch | AVOCADO RANCH SALAD KIT |
| 2075314 | Pickles, Olives, Peppers & Relishes | Meal > Salad Kits > Classics | CREATIVE CLASSICS SALAD KIT |
| 2583715 | Pickles, Olives, Peppers & Relishes | Meal > Salad Kits > Spicy Southwest | SPICY SOUTHWEST SALAD KIT |
| 2156157 | Salad Dressing & Mayonnaise | Meal > Salad Kits > Orange Vinaigrette Bleu Cheese | ORANGE VINAIGRETTE & BLEU CALIFORNIA ARTISAN DRESSING! BABY GREENS SALAD KIT, ORANGE VINAIGRETTE & BLEU |
| 2277997 | Pickles, Olives, Peppers & Relishes | Meal > Salad Kits > Chicken Bacon Ranch | GARDEN SALAD WITH CHICKEN & BACON SALAD KIT, CHICKEN & BACON |
| 2092161 | Deli Salads | Meal > Salad Kits > Bleu Cheese Cherry Balsamic Vinaigrette Apple Walnut | APPLE, CHEESE & WALNUT SALAD KIT, APPLE, CHEESE & WALNUT |

### biscotti_fragmentation_residual

- rows: `20`
- severity: `low`
- confidence: `review`
- action: `manual_review`
- likely fix: Verify whether non-Bakery > Biscotti rows are true biscotti products or flavor inclusions in ice cream/sandwiches.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2071163 | Cereal | Snack > Granola > Chocolate Chunk Hazelnut Biscotti | CHOCOLATE CHUNK HAZELNUT BISCOTTI GRANOLA |
| 2439130 | Other Snacks | Snack > Biscotti > Sugar | CLEMENTE BISCOTTIFICIO, ORIGINAL SUGAR TARALLI, BISCOTIFICIO, BISCOTIFICIO |
| 2439133 | Other Snacks | Snack > Biscotti > Plain | CLEMENTE BISCOTTIFICIO, ORIGINAL TARALLI |
| 2439134 | Other Snacks | Snack > Biscotti > Taralli Lemon Sugar | CLEMENTE BISCOTTIFICIO, ORIGINAL LEMON SUGAR TARALLI |
| 2560104 | Coffee | Beverage > Coffee > Ground Coffee > Chocolate Raspberry Biscotti | INDULGENT BLENDS CHOCOLATE RASPBERRY BISCOTTI GROUND COFFEE, CHOCOLATE; RASPBERRY |
| 2288810 | Crackers & Biscotti | Meal > Sandwiches > Biscotti > Apricot | BUTTERFLY PASTRIES, SANDWICH BISCOTTI, APRICOT, APRICOT |
| 2157271 | Crackers & Biscotti | Meal > Sandwiches > Biscotti > Sandwich Raspberry | BUTTERFLY PASTRIES, SANDWICH BISCOTTI, RASPBERRY, RASPBERRY |
| 1908883 | Milk Additives | Beverage > Coffee Creamer > Chocolate Almond Biscotti | GOURMET COFFEE CREAMER, CHOCOLATE ALMOND BISCOTTI |

### ice_cream_bfc_title_conflict_non_frozen

- rows: `13`
- severity: `medium`
- confidence: `medium`
- action: `source_conflict_review`
- likely fix: Review BFC/title conflict; do not blindly force to Frozen when title says yogurt, cheese, dried fruit, soft drink, or cereal.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 1926628 | Ice Cream & Frozen Yogurt | Dairy > Yogurt > Greek Blueberry > Organic > Fat Free | STONYFIELD, OIKOS, ORGANIC NONFAT GREEK YOGURT, BLUEBERRY, BLUEBERRY |
| 2438448 | Ice Cream & Frozen Yogurt | Snack > Fruit Snacks > Strawberry Banana > Organic | ORGANIC FROZEN FRUIT SNACK TUBES, STRAWBANANA DELIGHT |
| 1042037 | Ice Cream & Frozen Yogurt | Dairy > Cheese > Triple Creme | TRIPLE CREME - SOFT RIPENED CHEESE, TRIPLE CREME |
| 2675575 | Ice Cream & Frozen Yogurt | Snack > Dried Fruit > Apple Chips > Plain | CRISPY GREEN CRISPY FRUIT 100% FREEZE-DRIED APPLE, 0.53 OZ, 4 COUNT |
| 2658427 | Ice Cream & Frozen Yogurt | Snack > Dried Fruit > Tangerine | CRISPY GREEN CRISPY FRUIT 100% FREEZE-DRIED TANGERINE, 0.42 OZ, 4 COUNT |
| 2185623 | Ice Cream & Frozen Yogurt | Dairy > Yogurt > Strawberry Pomegranate > Grass Fed | DREAMING COW, GRASS-FED CREAM TOP YOGURT, STRAWBERRY POMEGRANATE, STRAWBERRY POMEGRANATE |
| 889560 | Ice Cream & Frozen Yogurt | Beverage > Soft Drinks > Fruit | POCKIN FRUITS SOFT DRINK |
| 1890660 | Ice Cream & Frozen Yogurt | Snack > Fruit Snacks > Blue Mahalo > Organic | ORGANIC FRUIT SNACK, BLUE MAHALO |

### salad_kit_not_on_salad_kit_shelf

- rows: `12`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route title-level salad kits to Produce > Salad Kits or the chosen Meal > Salad Kits policy shelf, not ingredient/component shelves.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2548306 | Lunch Snacks & Combinations | Meal > Salads > Lunch Kit > Chunk White Chicken | CHUNK WHITE PREMIUM CHICKEN SALAD KIT, CHUNK WHITE |
| 2548330 | Lunch Snacks & Combinations | Meal > Salads > Lunch Kit > Chunk White Chicken | CHUNK WHITE PREMIUM CHICKEN SALAD KIT, CHUNK WHITE |
| 2413955 | Pickles, Olives, Peppers & Relishes | Bakery > Croutons > Kale Caesar | KALE CAESAR ROMAINE & KALE LETTUCE BLEND, GRAPE TOMATOES, PARMESAN CHEESE, SEASONED CROUTONS, CARROTS WITH CAESAR DRESSING SALAD KIT, KALE C |
| 2661491 | Deli Salads | Bakery > Croutons > Quinoa Black Beans Mango Vinaigrette Plantain Caribbean > Vegan > Chopped | VEGAN CARIBBEAN-STYLE CRUNCH WITH QUINOA & BLACK BEANS RED & WHITE QUINOA WITH BLACK BEANS, GREEN LEAF LETTUCE, BROCCOLI STALK, RED & SAVOY  |
| 2493118 | Prepared Subs & Sandwiches | Meal > Lunch Kits > Tuna Salad | BUMBLE BEE SNACK ON THE RUN! TUNA SALAD KIT WITH CRACKERS, 3.5 OZ |
| 2655287 | Deli Salads | Meal > Lunch Kits > Tuna Salad > Wild Caught | DELI STYLE WILD CAUGHT LUNCH-TO-GO TUNA SALAD KIT, DELI STYLE |
| 2533176 | Entrees, Sides & Small Meals | Meal > Lunch Kits > Tuna Salad > Fat Free | FAT-FREE WITH WHEAT CRACKERS TUNA SALAD KIT |
| 2276978 | Pickles, Olives, Peppers & Relishes | Bakery > Flatbread > Cranberry Walnut Balsamic Vinaigrette | CRANBERRY WALNUT SPRING MIX, FETA CHEESE, HERB SEASONED FLATBREAD STRIPS, DRIED CRANBERRIES & WALNUTS WITH BALSAMIC VINAIGRETTE DRESSING SAL |

### ice_cream_title_left_under_bakery

- rows: `10`
- severity: `medium`
- confidence: `review`
- action: `manual_review`
- likely fix: Decide whether each is a true bakery flavor product or a frozen dessert missed by rules.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2070392 | Cakes, Cupcakes, Snack Cakes | Bakery > Cake > Ice Cream Cone White | WHITE ICE CREAM CONE CAKE |
| 1457658 | Biscuits/Cookies | Bakery > Cookies > Rocky Road Chocolate Chip | NABISCO CHIPS AHOY! COOKIES CHEWY ICE CREAM CREATIONS ROCKY ROAD1X9.500 OZ |
| 1457953 | Biscuits/Cookies | Bakery > Cookies > Mocha Chocolate Chip | NABISCO CHIPS AHOY! COOKIES CHEWY ICE CREAM CREATIONS MOCHA1X9.500 OZ |
| 1458982 | Biscuits/Cookies | Bakery > Cookies > Sandwich Chocolate Creamsicle | NABISCO OREO SANDWICH COOKIES CHOCOLATE CREAMSICLE ICE CREAM 1X15.250 OZ |
| 762728 | Biscuits/Cookies | Bakery > Cookies > Oreo Sandwich Chocolate Mint | OREO SANDWICH COOKIES ICE CREAM BROWNIES 1X3 OZ |
| 2678339 | Cookies & Biscuits | Bakery > Cookies > Sugar Cookie Decorating Kit | ICE CREAM CONE SUGAR COOKIE DECORATING KIT, ICE CREAM CONE SUGAR |
| 2577550 | Cookies & Biscuits | Bakery > Cookies > Vanilla Ice Cream | VANILLA ICE CREAM COOKIES, VANILLA |
| 2577564 | Cookies & Biscuits | Bakery > Cookies > Vanilla | VANILLA FLAVORED ICE CREAM COOKIES, VANILLA |

### alcohol_bfc_not_beverage

- rows: `10`
- severity: `medium`
- confidence: `medium`
- action: `source_conflict_review`
- likely fix: Review whether BFC is dirty or whether cocktail/drink context should force Beverage.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2278665 | Alcohol | Meat & Seafood > Shellfish > Shrimp > Red Chili Pepper | SHRIMP MICHEVASO, SHRIMP |
| 2273820 | Alcohol | Snack > Candy > Hard Candy > Tequila Sunrise | TEQUILA SUNRISE |
| 2534810 | Alcohol | Sports & Wellness > Sports Nutrition > Maltodextrin Powder > Plain | UNFLAVORED MALTODEXTRIN POWDER |
| 2625975 | Alcohol | Sports & Wellness > Protein Powders > Ashwagandha Powder > Organic | PURE & NATURAL ASHWAGANDHA POWDER |
| 2538066 | Alcohol | Sports & Wellness > Supplements > Fiber Supplement > Plain | ON THE GO POWDER FOR DIGESTIVE HEALTH PREBIOTIC FIBER SUPPLEMENT |
| 2214867 | Alcohol | Snack > Chocolate Candy > Milk | HOLLOW MILK CHOCOLATE |
| 2316111 | Alcohol | Pantry > Spices & Seasonings > Seasoning > Lime Chili Pepper | CLASICO SEASONING WITH LIME, LIME |
| 2451968 | Alcohol | Pantry > Sauces & Salsas > Horseradish Sauce > Plain | HORSERADISH |

### biscotti_product_not_single_biscotti_shelf

- rows: `2`
- severity: `medium`
- confidence: `high`
- action: `normalization_fix_candidate`
- likely fix: Route true biscotti/biscottini products to the one canonical biscotti shelf; keep biscotti flavor-only rows in the host product category.

| fdc_id | BFC | current path | title |
|---|---|---|---|
| 2288810 | Crackers & Biscotti | Meal > Sandwiches > Biscotti > Apricot | BUTTERFLY PASTRIES, SANDWICH BISCOTTI, APRICOT, APRICOT |
| 2157271 | Crackers & Biscotti | Meal > Sandwiches > Biscotti > Sandwich Raspberry | BUTTERFLY PASTRIES, SANDWICH BISCOTTI, RASPBERRY, RASPBERRY |
