# Consensus Right-Place Audit

Source: `consensus_full_corpus_audit.csv`
Rows: `462,664`
Unique issue FDC ids: `4,503`
High severity + high confidence FDC ids: `1,763`
Deterministic-fix FDC ids: `1,772`

## Structural Metrics

- `unique_fdc_ids`: `462,664`
- `duplicate_fdc_extra_rows`: `0`
- `empty_retail_leaf_path_rows`: `0`
- `invalid_department_rows`: `0`
- `path_defect_rows`: `0`

## Issue Counts

### pickle_bfc_salad_source_conflict

- rows: `1,559`
- severity: `medium`
- confidence: `medium`
- action: `source_conflict_review`
- likely fix: Keep true salads in Meal/Produce salad shelves, but mark the Pickles/Olives BFC as dirty source evidence for these rows.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 374774 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Chicken Caesar | MARKETS OF MEIJER, FRESH CHICKEN CAESAR SALAD |
| 376750 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Cobb Salad > Grilled Chicken Grape Tomatoes Olives Iceberg Lettuce | MARKETS OF MEIJER, COBB SALAD |
| 376765 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Salad Kit > House | MARKETS OF MEIJER, HOUSE SALAD |
| 410589 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Olives > Spanish > Sliced | SPARTAN, SPANISH OLIVES SLICED SALAD |
| 467128 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Chicken Salad > Chinese Ginger Soy | CLASSIC CHINESE CHICKEN SALAD WITH GINGER SOY VINAIGRETTE |
| 467131 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Chef Salad > Ranch | CLASSIC CHEF SALAD WITH RANCH DRESSING |
| 467156 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Chicken Ranch Dressing Cheese Tomato | HOUSE CHICKEN SALAD WITH RANCH DRESSING |
| 467157 | Pickles, Olives, Peppers & Relishes | Meal > Salads > Buffalo Chicken BBQ Ranch | BUFFALO CHICKEN SALAD |

### sandwich_cookie_or_cracker_routed_as_meal_sandwich

- rows: `707`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route sandwich cookies/biscuits to Bakery > Cookies and sandwich crackers to Snack > Crackers; do not use Meal > Sandwiches.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 348017 | Biscuits/Cookies (Shelf Stable) | Meal > Sandwiches > Cookies > Chocolate Sandwich > Sugar Free | KEEBLER PREMIUM COOKIE MEAL BROKEN CHOCOLATE SANDWICH 30LB 1CT |
| 397024 | Cookies & Biscuits | Meal > Sandwiches > Sandwich Cookies > Creme Peanut Butter | SANDWICH CREME PEANUT BUTTER COOKIES |
| 429224 | Cookies & Biscuits | Meal > Sandwiches > Cookies > Sandwich Lemon > Sugar Free | GANDOUR, DABKE, BISCUIT SANDWICHES, LEMON |
| 429225 | Cookies & Biscuits | Meal > Sandwiches > Sandwich Cookies > Bourbon Creams Chocolate | BOLANDS, BOURBON CREAMS SANDWICH BISCUITS, CRUNCHY CHOCLATE |
| 429919 | Cookies & Biscuits | Meal > Sandwiches > Sandwich Cookies > Peanut Butter | JULIE'S, SANDWICH, PEANUT BUTTER |
| 573161 | Crackers & Biscotti | Meal > Sandwiches > Crackers > Cheddar | SANDWICH CRACKERS |
| 573365 | Crackers & Biscotti | Meal > Sandwiches > Crackers > Sandwich | CRACKER SANDWICHES |
| 574013 | Cookies & Biscuits | Meal > Sandwiches > Sandwich Cookies > Fudge Creme | SANDWICH CREME FUDGE COOKIES |

### baking_decoration_or_topping_routed_as_candy

- rows: `572`
- severity: `medium`
- confidence: `medium`
- action: `policy_decision`
- likely fix: Decide whether baking decorations, edible confetti, melts, peels, and dessert toppings stay in Pantry baking/topping shelves even when candy-like.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 375592 | Baking Decorations & Dessert Toppings | Snack > Chocolate Candy > Milk Chocolate | MILK CHOCOLATE FLAKES |
| 453471 | Baking Decorations & Dessert Toppings | Snack > Chocolate Candy > Milk Chocolate | MILK CHOCOLATE FLAKES |
| 553358 | Baking Decorations & Dessert Toppings | Snack > Chocolate Candy > Edible Candle | EDIBLE CHOCOLATE CANDLE |
| 570310 | Baking Decorations & Dessert Toppings | Snack > Candy > Candied Peel > Orange > Diced | DICED ORANGE PEEL |
| 572049 | Baking Decorations & Dessert Toppings | Snack > Chocolate Candy > White | SIXLETS WISPY WHITE CANDY COATED CHOCOLATE FLAVORED CANDY |
| 713444 | Baking Decorations & Dessert Toppings | Snack > Candy > Hard Candy > Peppermint Crunch | PEPPERMINT CRUNCH CANDIES, PEPPERMINT CRUNCH |
| 728380 | Baking Decorations & Dessert Toppings | Snack > Chocolate Candy > Milk Chocolate 30 Cacao | MILK CHOCOLATE 30% CACAO REAL MELTING |
| 729418 | Baking Decorations & Dessert Toppings | Snack > Candy > Hard Candy > Semi Sweet Dark | SEMI-SWEET DARK CHOCOLATE |

### frozen_appetizer_sandwich_not_frozen

- rows: `428`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Keep frozen sandwiches/pockets/sliders under a Frozen sandwich/appetizer shelf.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 372231 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Sandwich > Fish And Cheese | FAST BITES, FISH AND CHEESE SANDWICH |
| 381282 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Sandwich > BBQ Rib | BBQ RIB SANDWICH |
| 381283 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Sandwich > Breaded Chicken Patty | BREADED CHICKEN SANDWICH, BREADED CHICKEN PATTY ON A BUN |
| 396685 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Chicken Sandwich > Plain | PIERRE, DRIVE THRU, CHICKEN SANDWICH |
| 459404 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Pizza Pocket > Pepperoni Mozzarella | STUFFED SANDWICH |
| 496320 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Sandwich > Chicken Buffalo | CHICKEN SANDWICH |
| 510510 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Chicken Sandwich > Breaded Patty | BREADED CHICKEN CLUB SANDWICH |
| 517190 | Frozen Appetizers & Hors D'oeuvres | Meal > Sandwiches > Sandwich > Bacon Peperoncino Cheese | SANDWICH IN SOFT BAKED BREAD |

### soup_chowder_or_bisque_routed_as_seafood

- rows: `341`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route seafood soups, chowders, and bisques to Pantry > Soup/Chowder shelves; keep seafood as variant/component.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 372516 | Canned Soup | Meat & Seafood > Shellfish > Clam > Plain | SNOW'S, NEW ENGLAND CLAM CHOWDER |
| 399983 | Other Soups | Meat & Seafood > Shellfish > Shrimp > Plain | YOUKI, SHRIMP SOUP BASE |
| 404524 | Other Soups | Meat & Seafood > Shellfish > Lobster > Semi Condensed > Light | LOBSTER BISQUE |
| 479975 | Other Soups | Meat & Seafood > Shellfish > Clam > Plain | CLAM CHOWDER |
| 484229 | Other Soups | Meat & Seafood > Shellfish > Clam > Plain | CLAM CHOWDER |
| 617666 | Canned Soup | Meat & Seafood > Shellfish > Clam > New England | NEW ENGLAND STYLE CLAM CHOWDER CHUNKY READY TO SERVE SOUP, NEW ENGLAND STYLE CLAM CHOWDER |
| 686804 | Canned Soup | Meat & Seafood > Shellfish > Clam > New England | NEW ENGLAND STYLE TRADITIONAL CLAM CHOWDER, NEW ENGLAND STYLE |
| 686842 | Canned Soup | Meat & Seafood > Shellfish > Clam > Plain | CHUNKY CLAM CHOWDER SOUP, CLAM CHOWDER |

### prepackaged_produce_salad_split_to_meal

- rows: `268`
- severity: `medium`
- confidence: `medium`
- action: `policy_decision`
- likely fix: Decide whether packaged produce salads stay under Produce > Salad Kits/Packaged Salads rather than Meal > Salads.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 539578 | Pre-Packaged Fruit & Vegetables | Meal > Salads > Roasted Pear Radicchio Blue Cheese | ROASTED PEAR & RADICCHIO SALAD WITH BLUE CHEESE |
| 720900 | Pre-Packaged Fruit & Vegetables | Meal > Salads > Croutons > Caesar | ROMAINE LETTUCE, CAESAR DRESSING, SHREDDED CHEESE AND CROUTONS CAESAR SALAD, DRESSING & TOPPINGS KIT, CAESAR SALAD |
| 722780 | Pre-Packaged Fruit & Vegetables | Meal > Salads > Iceberg Lettuce Carrots Red Cabbage | GARDEN SALAD A BLEND OF ICEBERG LETTUCE TOSSED WITH CARROTS AND RED CABBAGE |
| 723168 | Pre-Packaged Fruit & Vegetables | Meal > Salads > Romaine Radicchio Italian | CRUNCHY ROMAINE AND ZESTY RADICCHIO ITALIAN SALAD, CRUNCHY ROMAINE AND ZESTY RADICCHIO |
| 723172 | Pre-Packaged Fruit & Vegetables | Meal > Salads > Romaine Radicchio Italian | CRUNCHY ROMAINE AND ZESTY RADICCHIO ITALIAN SALAD, CRUNCHY ROMAINE AND ZESTY RADICCHIO |
| 1063411 | Pre-Packaged Fruit & Vegetables | Meal > Salads > Croutons > Caesar | CAESAR SALAD ROMAINE LETTUCE, CAESAR DRESSING, SHAVED PARMESAN CHEESE, CROUTONS KIT, CAESAR SALAD |
| 1369845 | Pre-Packaged Fruit & Vegetables | Meal > Salads > Sea Palm Cucumber Sesame | SESAME SEA PALM AND CUCUMBER SALAD |
| 1370079 | Pre-Packaged Fruit & Vegetables | Meal > Salads > Cucumbers > Plain | SALAD CUCUMBER |

### cake_or_cupcake_product_routed_as_cookie

- rows: `173`
- severity: `medium`
- confidence: `review`
- action: `manual_review`
- likely fix: Review cake/cupcake/madeleine/Jaffa rows under Bakery > Cookies; true cakes should move to Bakery > Cakes, cookie-flavored cookies can stay.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 896288 | Cookies & Biscuits | Bakery > Cookies > Chocolate Chip | FRENCH SPONGE CAKES WITH CHOCOLATE CHIPS MINI MADELEINES, FRENCH SPONGE CAKES WITH CHOCOLATE CHIPS |
| 901280 | Cookies & Biscuits | Bakery > Cookies > Jaffa Cakes Raspberry Chocolate | RASPBERRY FLAVORED LIGHT SPONGE COOKIE WITH FRUIT FLAVORED FILLING AND CHOCOLATE TOPPING JAFFA CAKES, RASPBERRY |
| 937482 | Cookies & Biscuits | Bakery > Cookies > Chocolate Chip | CHOCOLATE CHIP COOKIE CAKE, CHOCOLATE CHIP |
| 1153095 | Cookies & Biscuits | Bakery > Cookies > Cupcake Donut | CRAFT A COOKIE CUPCAKE & DONUT |
| 1630288 | Crusts & Dough | Bakery > Cookies > Fudge > Filled | MELTS MOLTEN FUDGE CAKE FILLED COOKIES |
| 1830625 | Cookies & Biscuits | Bakery > Cookies > Madeleines | MOIST AND BUTTERY SOFT WITH A HINT OF SWEETNESS FRENCH INSPIRED MADELEINES |
| 1844289 | Cookies & Biscuits | Bakery > Cookies > Graham Vanilla Cupcake | VANILLA CUPCAKE GRAHAMS BAKED GRAHAM SNACKS, VANILLA CUPCAKE |
| 1878436 | Cookies & Biscuits | Bakery > Cookies > Devils Food Chocolate | DEVIL'S FOOD CHOCOLATE COOKIE CAKES, DEVIL'S FOOD |

### dip_salsa_or_cocktail_sauce_routed_as_seafood

- rows: `84`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route crab/shrimp/clam dips and cocktail sauces to Pantry > Dips & Spreads or Pantry > Sauces & Salsas.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 604224 | Dips & Salsa | Meat & Seafood > Shellfish > Crab > Cream Cheese Cheddar | CRAB DIP |
| 1389998 | Dips & Salsa | Meat & Seafood > Shellfish > Shrimp > Plain | SHRIMP & COCKTAIL SAUCE |
| 1401111 | Dips & Salsa | Meat & Seafood > Shellfish > Crab > Smoky Bacon | SMOKY BACON CRAB DIP, SMOKY BACON CRAB |
| 1588099 | Dips & Salsa | Meat & Seafood > Shellfish > Clam > Plain | CREAMY CLAM DIP |
| 1590686 | Dips & Salsa | Meat & Seafood > Fish > Salmon > Smoked | KROGER, SMOKED SALMON DIP |
| 1855165 | Dips & Salsa | Meat & Seafood > Shellfish > Shrimp > Oyster | TRY ME, OYSTER & SHRIMP SAUCE |
| 1886223 | Dips & Salsa | Meat & Seafood > Shellfish > Crab > Plain | DIP & SPREAD, SEAFOOD CRAB |
| 1886273 | Dips & Salsa | Meat & Seafood > Fish > Tuna > Smoked | GOURMET SMOKED TUNA DIP |

### pickle_sandwich_slices_routed_as_meal_sandwich

- rows: `83`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route sandwich slices/bread-and-butter slices to Pantry pickle/relish shelves.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 559588 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Deli Sandwich Slices Garlic | DELI-STYLE SANDWICH SLICES |
| 597002 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Bread And Butter Sandwich Slice | BREAD & BUTTER SANDWICH SLICES |
| 622292 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Dill > Kosher | KOSHER DILL SANDWICH SLICES, KOSHER DILL |
| 1404028 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Dill > Kosher | KOSHER DILL SANDWICH SLICES |
| 1405082 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Bread And Butter Sandwich Slice | BREAD & BUTTER SANDWICH SLICES |
| 1468097 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Bread And Butter > Sliced | BREAD & BUTTER SANDWICH SLICES, BREAD & BUTTER |
| 1469585 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Bread And Butter Sweet | SWEET BREAD & BUTTER SANDWICH SLICES, SWEET BREAD & BUTTER |
| 1469586 | Pickles, Olives, Peppers & Relishes | Meal > Sandwiches > Pickles > Dill > Kosher | KOSHER DILL SANDWICH SLICES, KOSHER DILL |

### salad_topping_routed_as_finished_salad

- rows: `71`
- severity: `medium`
- confidence: `medium`
- action: `policy_fix_candidate`
- likely fix: Route salad toppers, tortilla strips, croutons, nuts, and dressing add-ins to Pantry/Snack topping shelves, not Meal > Salads.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 1382499 | Salad Dressing & Mayonnaise | Meal > Salads > Salad Topping > Southwest | SOUTHWEST SALAD TOPPINS |
| 1505048 | Salad Dressing & Mayonnaise | Meal > Salads > Salad Topping > Caesar Roasted Garlic | ROASTED GARLIC CAESAR SALAD TOPPINS |
| 1853876 | Salad Dressing & Mayonnaise | Meal > Salads > Crackers > Garlic Cheese Sesame | ORIGINAL TRENTON CRACKERS, SESAME SALAD NUGGETS, GARLIC 'N CHEESE, GARLIC 'N CHEESE |
| 1869786 | Salad Dressing & Mayonnaise | Meal > Salads > Tortilla Chips > Tri Color | SPARTAN, TORTILLA STRIPS, CRUNCHY SALAD TOPPINGS, TRI-COLOR |
| 1870361 | Salad Dressing & Mayonnaise | Meal > Salads > Salad Topper > Cranberry Almond | CRANBERRIES & SLICED ALMONDS SALAD TOPPER |
| 1872233 | Salad Dressing & Mayonnaise | Meal > Salads > Salad Topper > Cranberry Walnut > Glazed | CRANBERRIES & GLAZED WALNUTS SALAD TOPPER |
| 1892330 | Salad Dressing & Mayonnaise | Meal > Salads > Salad Topper > Dried Cranberries Honey Toasted Almonds | DRIED CRANBERRIES & HONEY TOASTED ALMONDS SALAD TOPPER, DRIED CRANBERRIES & HONEY TOASTED ALMONDS |
| 1893889 | Salad Dressing & Mayonnaise | Meal > Salads > Salad Topping > Roasted Sunflower Seeds Bacon Onion Bell Pepper | ORIGINAL ROASTED SUNFLOWER SEEDS WITH ONION & BELL PEPPER SEASONING BACON FLAVORED SALAD TOPPINGS BITS, ORIGINAL |

### seasoning_marinade_routed_as_meat_or_seafood

- rows: `67`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route seafood rubs, boils, pastes, and marinades to Pantry > Spices & Seasonings or sauces/marinades.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 451794 | Seasoning Mixes, Salts, Marinades & Tenderizers | Meat & Seafood > Fish > Salmon > Plain | BRITISH COLUMBIA SALMON RUB |
| 1501496 | Seasoning Mixes, Salts, Marinades & Tenderizers | Meat & Seafood > Shellfish > Crab > Bean Oil | POR KWAN, CRAB PASTE WITH BEAN OIL |
| 1777994 | Seasoning Mixes, Salts, Marinades & Tenderizers | Meat & Seafood > Shellfish > Shrimp > Crawfish Crab Boil | CRAWFISH SHRIMP CRAB BOIL |
| 1852247 | Seasoning Mixes, Salts, Marinades & Tenderizers | Meat & Seafood > Fish > Cod > Lemon Pepper | OLDE CAPE COD, MARINADE, LEMON PEPPER, LEMON PEPPER |
| 1852248 | Seasoning Mixes, Salts, Marinades & Tenderizers | Meat & Seafood > Fish > Cod > Teriyaki Pineapple | OLDE CAPE COD, MARINADE, TERIYAKI WITH PINEAPPLE, TERIYAKI WITH PINEAPPLE |
| 1888164 | Seasoning Mixes, Salts, Marinades & Tenderizers | Meat & Seafood > Shellfish > Crab > Plain | CRAB SEASONING |
| 1888821 | Seasoning Mixes, Salts, Marinades & Tenderizers | Meat & Seafood > Shellfish > Shrimp > Crawfish Crab Boil | CRAWFISH SHRIMP & CRAB BOIL SEASONING, CRAWFISH SHRIMP & CRAB BOIL |
| 1892279 | Seasoning Mixes, Salts, Marinades & Tenderizers | Meat & Seafood > Shellfish > Shrimp > Barbecued | BARBECUED SHRIMP SAUCE MIX, BARBECUED SHRIMP |

### salad_kit_not_on_produce_salad_kit_shelf

- rows: `48`
- severity: `high`
- confidence: `medium`
- action: `policy_fix_candidate`
- likely fix: Adopt one salad-kit home, preferably Produce > Salad Kits for produce BFC rows and a deliberate Meal variant only when policy says so.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 484122 | Pickles, Olives, Peppers & Relishes | Pantry > Pickles > Salad Kit > Kale Honey Citrus | KALE KRUNCH SALAD KIT |
| 484123 | Pickles, Olives, Peppers & Relishes | Pantry > Pickles > Salad Kit > Caesar | CAESAR SALAD KIT |
| 510951 | Pickles, Olives, Peppers & Relishes | Pantry > Pickles > Meal Starter > Asparagus Shallot Lemon | CHOPPED ASPARAGUS SALAD KIT |
| 1031151 | Pasta Dinners | Meal > Pasta Dishes > Pasta Salad Kit > Ranch Bacon | RANCH AND BACON PASTA SALAD KIT, RANCH AND BACON |
| 1063529 | Pasta Dinners | Meal > Pasta Dishes > Pasta Salad Kit > Creamy Parmesan | CREAMY PARMESAN PASTA SALAD KIT, CREAMY PARMESAN |
| 1570918 | Pickles, Olives, Peppers & Relishes | Pantry > Pickles > Salad Kit > Chicken Caesar | CHICKEN CAESAR SALAD KIT |
| 1859674 | Pickles, Olives, Peppers & Relishes | Pantry > Pickles > Salad Kit > Turkey Bacon Chef | SALAD KIT, TURKEY & BACON CHEF |
| 1893985 | Pickles, Olives, Peppers & Relishes | Pantry > Pickles > Salad Kit > Grilled Chicken Sweet Onion Dijon | SALAD KIT WITH GRILLED CHICKEN |

### cheese_slices_routed_as_meal_sandwich

- rows: `48`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route sandwich slices and processed cheese food to Dairy > Cheese, not Meal > Sandwiches.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 1369049 | Cheese | Meal > Sandwiches > Cheese > Swiss | SWISS FLAVORED IMITATION PASTEURIZED PROCESS CHEESE FOOD SANDWICH SLICES |
| 1502874 | Cheese | Meal > Sandwiches > Cheese > American | WHITE AMERICAN FLAVORED IMITATION PASTEURIZED PROCESS CHEESE FOOD SANDWICH SLICES |
| 1542537 | Cheese | Meal > Sandwiches > Cheese > American Imitation Processed | AMERICAN SANDWICH SLICES IMITATION PROCESS CHEESE FOOD |
| 1897673 | Cheese | Meal > Sandwiches > Cheese > Processed Jalapeno | PASTEURIZED PROCESSED SANDWICH SLICES, JALAPENO |
| 1897692 | Cheese | Meal > Sandwiches > Cheese > Sandwich Slices > Sliced | SLICES SANDWICH |
| 1897994 | Cheese | Meal > Sandwiches > Cheese > Sandwich Slices > Sliced | SANDWICH CHEESE SLICES |
| 1904922 | Cheese | Meal > Sandwiches > American Cheese > Plain | SANDWICH SLICES, AMERICAN |
| 1910173 | Cheese | Meal > Sandwiches > Cheese > Imitation Pasteurized Processed | SANDWICH SLICES IMITATION PASTEURIZED PROCESSED CHEESE PRODUCT SINGLES |

### candy_bfc_routed_outside_snack_candy

- rows: `28`
- severity: `medium`
- confidence: `medium`
- action: `source_conflict_review`
- likely fix: Review whether the BFC is dirty or whether ice cream/cracker/sandwich words hijacked true candy.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 1022425 | Candy | Snack > Crackers > Plain | CHOCOLATE CRACKER, CHOCOLATE |
| 1451927 | Candy | Snack > Crackers > S Mores Milk Chocolate Marshmallow Graham | S'MORES MARSHMALLOW & GRAHAM CRACKER COVERED IN OUR CREAMY MILK CHOCOLATE, S'MORES MARSHMALLOW & GRAHAM CRACKER |
| 1620063 | Candy | Frozen > Ice Cream Bars > Peanut Caramel Chocolate Peanut Butter | ICE CREAM BARS |
| 1866189 | Candy | Frozen > Ice Cream > Milk Chocolate Peanut Butter | PEANUT BUTTER ICE CREAM CUP, EGGS, MILK CHOCOLATE COATING |
| 1876948 | Candy | Frozen > Ice Cream > Mint Chocolate Chip Dark Chocolate | RUSSELL STOVER, MINT CHOCOLATE CHIP IN DARK CHOCOLATE, ICE CREAM, ICE CREAM |
| 1877309 | Candy | Meal > Sandwiches > Chocolate Candy > Milk Chocolate Peanut Butter Raspberry | MILK CHOCOLATE, PEANUT BUTTER & JELLY SANDWICH |
| 1881714 | Candy | Frozen > Ice Cream > Vanilla Bean | RUSSELL STOVER, FREEZE-IT CANDY BARS, VANILLA BEAN ICE CREAM, VANILLA BEAN ICE CREAM |
| 1890863 | Candy | Frozen > Ice Cream > Cotton Candy | COTTON CANDY, ICE CREAM |

### ice_cream_title_left_under_bakery_review

- rows: `10`
- severity: `low`
- confidence: `review`
- action: `manual_review`
- likely fix: Review residual ice-cream-title rows under Bakery; many are cookie flavors, but true frozen desserts should move to Frozen.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 762728 | Biscuits/Cookies | Bakery > Cookies > Oreo Sandwich Chocolate Mint | OREO SANDWICH COOKIES ICE CREAM BROWNIES 1X3 OZ |
| 1457658 | Biscuits/Cookies | Bakery > Cookies > Rocky Road Chocolate Chip | NABISCO CHIPS AHOY! COOKIES CHEWY ICE CREAM CREATIONS ROCKY ROAD1X9.500 OZ |
| 1457953 | Biscuits/Cookies | Bakery > Cookies > Mocha Chocolate Chip | NABISCO CHIPS AHOY! COOKIES CHEWY ICE CREAM CREATIONS MOCHA1X9.500 OZ |
| 1458982 | Biscuits/Cookies | Bakery > Cookies > Sandwich Chocolate Creamsicle | NABISCO OREO SANDWICH COOKIES CHOCOLATE CREAMSICLE ICE CREAM 1X15.250 OZ |
| 1955431 | Croissants, Sweet Rolls, Muffins & Other Pastries | Bakery > Toaster Pastries > Ice Cream Sundae | ICE CREAM SUNDAE FROSTED TOASTER TARTS PASTRIES, ICE CREAM SUNDAE |
| 2070392 | Cakes, Cupcakes, Snack Cakes | Bakery > Cake > Ice Cream Cone White | WHITE ICE CREAM CONE CAKE |
| 2461132 | Croissants, Sweet Rolls, Muffins & Other Pastries | Bakery > Toaster Pastries > Ice Cream Sundae > Frosted | FROSTED ICE CREAM SUNDAE FLAVORED TOASTER PASTRIES, FROSTED ICE CREAM SUNDAE |
| 2577550 | Cookies & Biscuits | Bakery > Cookies > Vanilla Ice Cream | VANILLA ICE CREAM COOKIES, VANILLA |

### mexican_dinner_mix_left_in_baking_mixes

- rows: `9`
- severity: `high`
- confidence: `medium`
- action: `deterministic_fix_candidate`
- likely fix: Route Mexican dinner/meal products to meal kits, tortillas, beans, sides, or other Mexican pantry shelves instead of Baking Mixes.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 1467522 | Mexican Dinner Mixes | Pantry > Baking Mixes > Muffin Mix > Yellow Corn | FOOD CLUB, AUTHENTIC YELLOW CORN |
| 1973366 | Mexican Dinner Mixes | Pantry > Baking Mixes > Baking Mix > Plant Powered > High Protein | PLANT POWERED PROTEIN |
| 2080853 | Mexican Dinner Mixes | Pantry > Baking Mixes > Baking Mix > Estilo Casero | ESTILO CASERO |
| 2091329 | Mexican Dinner Mixes | Pantry > Baking Mixes > Baking Mix > Plain | MINI TORTITAS |
| 2299336 | Mexican Dinner Mixes | Pantry > Baking Mixes > Baking Mix > Yellow Corn | YELLOW CORN GRIDDLE CAKE, YELLOW CORN |
| 2299415 | Mexican Dinner Mixes | Pantry > Baking Mixes > Pancake Mix > Sweet Corn | SWEET CORN GRIDDLE CAKE, SWEET CORN |
| 2299416 | Mexican Dinner Mixes | Pantry > Baking Mixes > Pancake Mix > White Corn | WHITE CORN GRIDDLE CAKE, WHITE CORN |
| 2404603 | Mexican Dinner Mixes | Pantry > Baking Mixes > Egg White Wraps > Italian | ITALIAN STYLE EGG WHITE WRAPS, ITALIAN STYLE |

### cracker_title_still_under_bakery_cookies

- rows: `4`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route obvious cracker rows still under Bakery > Cookies to Snack > Crackers.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 349033 | Biscuits/Cookies (Shelf Stable) | Bakery > Cookies > Cheese Crisps > Cheddar > Organic | ANNIES BKD SNCK CRCKRS CHDR SQUARES |
| 349233 | Biscuits/Cookies (Shelf Stable) | Bakery > Cookies > Cheese Crisps > Cheddar | ANNIES BUNNIES BKD SNCK CRCKRS CHDR |
| 349247 | Biscuits/Cookies (Shelf Stable) | Bakery > Cookies > Cheese Crisps > Cheddar > Organic | ANNIES BUNNIES BKD SNCK CRCKRS CHDR |
| 349294 | Biscuits/Cookies (Shelf Stable) | Bakery > Cookies > Cheese Crisps > Cheddar > Organic | ANNIES BUNNIES BKD SNCK CRCKRS XCHSY CHDR |

### biscotti_product_routed_as_meal_sandwich

- rows: `2`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route sandwich biscotti products to Bakery > Biscotti, not Meal > Sandwiches.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 2157271 | Crackers & Biscotti | Meal > Sandwiches > Biscotti > Sandwich Raspberry | BUTTERFLY PASTRIES, SANDWICH BISCOTTI, RASPBERRY, RASPBERRY |
| 2288810 | Crackers & Biscotti | Meal > Sandwiches > Biscotti > Apricot | BUTTERFLY PASTRIES, SANDWICH BISCOTTI, APRICOT, APRICOT |

### alcohol_bfc_routed_outside_beverage

- rows: `1`
- severity: `high`
- confidence: `medium`
- action: `source_conflict_review`
- likely fix: Review the row; Alcohol BFC should usually resolve to Beverage/cocktail mixer territory unless BFC is dirty.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 2278665 | Alcohol | Meat & Seafood > Shellfish > Shrimp > Red Chili Pepper | SHRIMP MICHEVASO, SHRIMP |

### beverage_bfc_left_in_baking_mixes

- rows: `1`
- severity: `high`
- confidence: `medium`
- action: `source_conflict_review`
- likely fix: Review BFC/title conflict; drink mixes belong in Beverage unless the title is truly a cake/baking mix.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 2506953 | Powdered Drinks | Pantry > Baking Mixes > Cake Mix > Hot Cocoa | HOT COCOA CAKE MIX, HOT COCOA |

### prepared_sandwich_routed_to_bakery_carrier

- rows: `1`
- severity: `high`
- confidence: `high`
- action: `deterministic_fix_candidate`
- likely fix: Route prepared hot dogs/subs/sandwiches to Meal > Sandwiches; keep bun/roll as a form/component.

| fdc_id | BFC | path | title |
|---|---|---|---|
| 2524016 | Prepared Subs & Sandwiches | Bakery > Buns > Hot Dog Buns > Sweet Hawaiian | SWEET HAWAIIAN BREAD WRAPPED ROLL'D HOT DOG, SWEET HAWAIIAN |
