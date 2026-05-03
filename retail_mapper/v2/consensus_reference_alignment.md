# Consensus Reference Alignment Audit

Source: `consensus_full_corpus_audit.csv`
Rows: `462,664`
Unique issue FDC ids: `28,954`
High severity + high confidence FDC ids: `5,060`
Reference-remap candidate FDC ids: `5,060`
Overlap with right-place issue FDC ids: `361`

## Suspect Reference Fields

- `fndds`: `17,212`
- `sr28`: `11,669`
- `esha`: `5,315`
- `matched_key`: `1,945`

## Issue Counts

### low_token_overlap_reference_review

- rows: `24,562`
- severity: `low`
- confidence: `review`
- action: `manual_review`
- likely fix: Review low-overlap reference mappings, especially parent-default and provisional proxies.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 345974 | fndds: Chocolate milk, made from dry mix with whole milk \| esha: Egg Roll, chicken, with o sauce, frozen | Dairy > Eggs > Plain | BREAK-O-MORN Frozen Eggs Pasteurized Homogenized in Carton, Case |
| 346032 | sr28: Tomato powder | Pantry > Canned Vegetables > Tomatoes > Diced | ANGELA MIA Petite Diced Tomatoes, #10 Can, 6/102 oz., 102 OZ |
| 346079 | sr28: Tomato powder | Pantry > Canned Vegetables > Tomatoes > Chopped | ANGELA MIA Chopped Tomatoes, #10 Can, 6/102 oz., 102 OZ |
| 346091 | sr28: Tomato powder | Pantry > Canned Vegetables > Tomatoes > Plain | ANGELA MIA Whole Peeled Tomatoes, #10 Can, 6/102 oz., 102 OZ |
| 348065 | fndds: Graham crackers | Bakery > Cookies > Crunch Honey | SUNSHINE FS CRUNCH 400OZ 1CT |
| 349491 | sr28: Formulated bar, high fiber, chewy, oats and chocolate | Snack > Bars > Cereal Bars > Cocoa > Organic | ANNIES HMGRWN ORG CRSPY SNCK BARS COCOA |
| 350040 | fndds: Cantaloupe, frozen | Snack > Bites > Reuben | PINT SIZED KTCHN BITES REUBEN |
| 350959 | fndds: Cookie, almond | Bakery > Cookies > Brown Chocolate | Gamesa Emperador Chocolate Cookies 14.34 Ounce Paper Box |

### plant_milk_has_dairy_milk_reference

- rows: `1,029`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Remap plant milks to plant-milk/nut/soy/oat beverage references, not cow milk.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 397932 | sr28: Milk, whole, 3.25% milkfat, without added vitamin A and vitamin D | Beverage > Plant Milk > Coconut Milk > Plain | AROY-D, ORIGINAL COCONUT MILK |
| 411764 | sr28: Milk dessert, frozen, milk-fat free, chocolate | Beverage > Plant Milk > Coconut Milk > Chocolate | SO DELICIOUS DAIRY FREE, COCONUT MILK BEVERAGE, CHOCOLATE |
| 423774 | sr28: Milk and cereal bar | Beverage > Plant Milk > Coconut Milk > Light | LIGHT COCONUT MILK |
| 493842 | sr28: Milk, buttermilk, dried | Beverage > Plant Milk > Coconut Milk > Plain | HT TRADERS, COCONUT MILK |
| 497291 | sr28: Milk, buttermilk, dried | Beverage > Plant Milk > Coconut Milk > Plain | COCONUT MILK |
| 501310 | sr28: Milk, whole, 3.25% milkfat, without added vitamin A and vitamin D | Beverage > Plant Milk > Coconut Milk > No Preservatives | AROY-D, 100% COCONUT MILK, ORIGINAL |
| 504482 | sr28: Milk, buttermilk, dried | Beverage > Plant Milk > Coconut Milk > Pure Chocolate | PURE COCONUT MILK |
| 504499 | sr28: Milk, buttermilk, dried | Beverage > Plant Milk > Coconut Milk > Pure Coffee | PURE COCONUT MILK |

### sandwich_or_filled_bun_has_bread_carrier_reference

- rows: `982`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Use sandwich/stuffed-bun/prepared-meal references instead of plain bun, roll, bagel, or bread references.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 508726 | matched_key: panini bread | Frozen > Single Entrees > Panini > Chicken Fajita | CHICKEN PANINI |
| 530483 | sr28: Bagels, plain, enriched, with calcium propionate (includes onion, poppy, sesame) \| esha: Bagel, plain, frozen, FS \| matched_key: bagel bagels | Frozen > Appetizers > Plain | BAGEL DOGS |
| 538616 | sr28: Chicken breast, roll, oven-roasted | Frozen > Appetizers > Plain | CHICKEN BREAST FILLETS |
| 672030 | fndds: bagel bites \| esha: Pizza, bagel, cheese & pepperoni, frozen | Meal > Breakfast Sandwiches > Breakfast Sandwich > Cheese Pepperoni | CHEESE & PEPPERONI MINI BAGELS TOPPED WITH CHEESE, PEPPERONI MADE WITH PORK AND CHICKEN ADDED, AND TOMATO SAUCE PIZZA SNACKS, CHEESE & PEPPE |
| 711708 | matched_key: panini bread | Frozen > Appetizers > Panini > Turkey Veggie | TURKEY VEGGIE PANINI, TURKEY VEGGIE |
| 718330 | fndds: bagel bagels \| sr28: Bagels, plain, enriched, with calcium propionate (includes onion, poppy, sesame) \| esha: Bagel, onion, enriched, mini, 2 | Frozen > Appetizers > Onion > Stuffed | MINI STUFFED BAGELS, ONION |
| 718866 | fndds: bagel bagels \| sr28: Bagels, plain, enriched, with calcium propionate (includes onion, poppy, sesame) \| esha: Bagel, Bagelette, frozen, mini, | Frozen > Appetizers > Cream Cheese | THE CLASSIC MINI STUFFED BAGELS, CLASSIC |
| 727090 | esha: Roll, french, classic, frozen \| matched_key: roll | Frozen > Appetizers > Coconut Shrimp Tempura | COCONUT SHRIMP TEMPURA ROLL |

### dip_sauce_seasoning_has_plain_meat_or_seafood_reference

- rows: `966`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Use dip, sauce, seasoning, marinade, or boil references instead of raw/plain protein references.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 372118 | sr28: Chicken, broiler, rotisserie, BBQ, skin | Pantry > Spices & Seasonings > BBQ Rub > Chipotle Lime | CHIPOTLE LIME SEAFOOD & VEGETABLE RUB |
| 373410 | fndds: beef steak cube \| matched_key: beef steak cube | Pantry > Broth & Stock > Bouillon Cubes > Beef | CLOVER VALLEY, BOUILLON CUBES, BEEF |
| 373421 | matched_key: beef steak cube | Pantry > Broth & Stock > Bouillon Cubes > Beef | FRESH FINDS, BOUILLON CUBES, BEEF |
| 391912 | sr28: Snacks, shrimp cracker \| esha: Shrimp, dried | Meat & Seafood > Shellfish > Shrimp > Plain | GINISANG BAGOONG SAUTEED SHRIMP PASTE |
| 391916 | sr28: Snacks, shrimp cracker \| esha: Shrimp, dried | Meat & Seafood > Shellfish > Shrimp > Garlic | KAMAYAN GINISANG BAGOONG SAUTED SHRIMP PASTE |
| 398488 | sr28: Chicken, broiler, rotisserie, BBQ, skin | Pantry > Spices & Seasonings > BBQ Rub > Spicy Harissa | SPICY HARISSA RUB |
| 398529 | sr28: Chicken, broiler, rotisserie, BBQ, skin | Pantry > Spices & Seasonings > BBQ Rub > Latin | LATIN STYLE BBQ RUB |
| 399825 | sr28: DENNY'S, golden fried shrimp \| esha: Shrimp, golden fried | Meat & Seafood > Shellfish > Shrimp > Sweet | GOLDEN HANDS, BAGOONG SAUTEED SHRIMP PASTE, SWEET |

### soup_chowder_has_plain_seafood_or_meat_reference

- rows: `588`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Use soup/chowder/bisque references; keep seafood/meat as variant/component.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 369573 | matched_key: chicken tortilla  (parent-default) | Pantry > Soup > Chicken Tortilla Soup > Plain | CHICKEN TORTILLA SOUP |
| 404524 | sr28: Crustaceans, lobster, northern, cooked, moist heat | Meat & Seafood > Shellfish > Lobster > Semi Condensed > Light | LOBSTER BISQUE |
| 468325 | matched_key: chicken tortilla  (parent-default) | Pantry > Soup > Chicken Tortilla Soup > Plain | CHICKEN TORTILLA SOUP |
| 485750 | matched_key: chicken canned  (parent-default) | Pantry > Soup > Chicken Soup > Plain | CREAM OF CHICKEN CONDENSED SOUP |
| 493650 | matched_key: chicken tortilla  (parent-default) | Pantry > Soup > Chicken Tortilla Soup > Plain | CHICKEN TORTILLA SOUP |
| 560516 | matched_key: chicken canned  (parent-default) | Pantry > Soup > Chicken Soup > Plain | CREAM OF CHICKEN CONDENSED SOUP |
| 593220 | fndds: nachos chicken with beans | Pantry > Soup > Italian Vegetable > Organic | ORGANIC HEARTY ITALIAN VEGETABLE SOUP MADE WITH CHICKEN BONE BROTH |
| 597034 | matched_key: chicken canned  (parent-default) | Pantry > Soup > Chicken Soup > Cream Of | CREAM OF CHICKEN CONDENSED SOUP |

### nut_butter_has_dairy_butter_reference

- rows: `430`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Use nut/seed butter or spread references; reserve dairy butter references for dairy butter.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 399883 | sr28: Butter, salted \| esha: Butter | Pantry > Nut Butters > Peanut Chocolate | LILY'S, PEANUT SPREAD, CHOCOLATE |
| 415215 | sr28: Butter, salted | Pantry > Nut Butters > Peanut Coconut > Organic | EARTH BALANCE, CREAMY SPREAD, COCONUT & PEANUT |
| 453986 | sr28: Butter, salted \| esha: Butter, sweet cream, unsalted | Pantry > Nut Butters > Pistachio | CREAM OF PISTACHIO |
| 453988 | sr28: Butter, salted \| esha: Butter, sweet cream, unsalted | Pantry > Nut Butters > Vanilla Almond | CREAM OF ALMONDS |
| 454403 | sr28: Butter, salted \| esha: Butter | Pantry > Nut Butters > Peanut Ghana Taste | GHANA TASTE PEANUT PASTE |
| 467663 | sr28: Butter, salted | Pantry > Nut Butters > Hazelnut Butter > Chocolate | CHOCOLATY REAL HAZELNUT BUTTER |
| 467664 | sr28: Butter, salted | Pantry > Nut Butters > Hazelnut Butter > Plain | CRUNCHY REAL HAZELNUT BUTTER |
| 532906 | sr28: Butter, salted \| esha: Butter | Pantry > Nut Butters > Cocoa Coconut Almond | COCOA + COCONUT ON-THE-GO SNACK PACKS |

### cracker_has_bakery_carrier_reference

- rows: `300`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Use cracker references instead of buns, rolls, cakes, or plain cookies.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 359367 | esha: Cookies, Generation Max, M&M's, FS \| matched_key: cookies &  (parent-default) | Snack > Crackers > Vanilla | VAINILLA CRACKERS |
| 506095 | esha: Cookies, Generation Max, M&M's, FS \| matched_key: cookies &  (parent-default) | Snack > Crackers > Graham Cracker Sticks > Fudge | KEEBLER, FUDGE GRAHAMS CRACKERS |
| 518289 | fndds: Cookie, animal \| esha: Cookies, Generation Max, M&M's, FS \| matched_key: cookies &  (parent-default) | Snack > Crackers > Animal Crackers > Plain | ZOO ANIMAL CRACKERS |
| 592501 | fndds: Cookie, biscotti \| esha: Cookies, Generation Max, M&M's, FS \| matched_key: cookies &  (parent-default) | Snack > Crackers > Cookies > Anise Almond | ANISE ALMOND |
| 603695 | fndds: Cookie, animal \| esha: Cookies, Generation Max, M&M's, FS \| matched_key: cookies &  (parent-default) | Snack > Crackers > Animal Crackers > Plain | ZOO ANIMAL CRACKERS |
| 664164 | fndds: Cookie, animal \| esha: Cookies, Generation Max, M&M's, FS \| matched_key: cookies &  (parent-default) | Snack > Crackers > Animal | NABISCO, BARNUM'S ANIMALS CRACKERS |
| 751028 | esha: Cookies, Generation Max, M&M's, FS \| matched_key: cookies &  (parent-default) | Snack > Crackers > Graham Cinnamon | KEEBLER KBLR LICENSED CRACKERS DISNEY FROZEN 38OZ |
| 751040 | esha: Cookies, Generation Max, M&M's, FS \| matched_key: cookies &  (parent-default) | Snack > Crackers > Graham Honey | Keebler Grahams Crackers Elf Original 11oz |

### beverage_or_creamer_has_bakery_flour_reference

- rows: `230`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Remap beverage/coffee/creamer rows to coffee, creamer, or drink references; keep bakery words only as flavor.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 385878 | matched_key: cake mix nfs | Beverage > Flavored Drinks > Latte Mix > Cappuccino Coffee Cocoa | CAPPUCCINO DRINK MIX |
| 385879 | matched_key: cake mix nfs | Beverage > Flavored Drinks > Latte Mix > Cappuccino Coffee Cocoa | CAPPUCCINO DRINK MIX |
| 385880 | matched_key: toffee pudding cake mix | Beverage > Flavored Drinks > Latte Mix > English Toffee | HILLS BROS, CAPPUCCINO DRINK MIX, ENGLISH TOFFEE |
| 417607 | matched_key: cake mix nfs | Beverage > Flavored Drinks > Latte Mix > Cappuccino | CAPPUCCINO DRINK MIX |
| 559513 | matched_key: creme cake mix | Beverage > Flavored Drinks > Latte Mix > Cappuccino | CREME CAPPUCCINO |
| 915218 | matched_key: spice cake mix | Beverage > Flavored Drinks > Latte Mix > Turmeric Spice > Organic | ORGANIC SPICES, TURMERIC LATTE SPICE MIX |
| 1052517 | matched_key: caramel cake mix | Beverage > Flavored Drinks > Latte Mix > Vanilla Caramel | VANILLA CARAMEL LATTE CAFE-STYLE BEVERAGE MIX, VANILLA CARAMEL LATTE |
| 1063109 | matched_key: cake mix nfs | Beverage > Flavored Drinks > Latte Mix > Turmeric Saffron > Probiotic | TURMERIC LATTE WITH SAFFRON AND PROBIOTICS, TURMERIC |

### vegetable_or_potato_side_has_baking_mix_proxy_reference

- rows: `156`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Use vegetable, canned/frozen vegetable, or packaged potato side references instead of flour/starch/baking mix proxies.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 349570 | esha: Potato Mix, starch with baking powder, low protein, wheat free | Pantry > Packaged Sides > Potatoes > Hashbrown Onion | BTY CRK POTATO MIX HASHBR WTH ONIONS |
| 357445 | esha: Potato Mix, starch with baking powder, low protein, wheat free | Pantry > Packaged Sides > Potatoes > Scalloped Cheddar | CLOVER VALLEY, SCALLOPED POTATOES |
| 359716 | esha: Potato Mix, starch with baking powder, low protein, wheat free | Pantry > Packaged Sides > Potatoes > Au Gratin | AU GRATIN POTATOES |
| 570007 | esha: Potato Mix, starch with baking powder, low protein, wheat free | Pantry > Packaged Sides > Potatoes > Mashed | MASHED POTATOES |
| 603370 | esha: Potato Mix, starch with baking powder, low protein, wheat free | Pantry > Packaged Sides > Potatoes > Rosti | BRATFERTIG ROSTI, BRATFERTIG |
| 639486 | esha: Potato Mix, starch with baking powder, low protein, wheat free | Pantry > Packaged Sides > Potatoes > Mashed Buttery | BUTTERY MASHED POTATOES, BUTTERY |
| 934562 | esha: Potato Mix, starch with baking powder, low protein, wheat free | Pantry > Packaged Sides > Potatoes > Au Gratin Rich Creamy Cheese Sauce | AU GRATIN POTATO CLASSICS IN A RICH & CREAMY CHEESE SAUCE, AU GRATIN |
| 1368526 | esha: Potato Mix, starch with baking powder, low protein, wheat free | Pantry > Packaged Sides > Potatoes > Mashed | MASHED POTATOES |

### cookie_cracker_has_meal_sandwich_reference

- rows: `141`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Use cookie/cracker references for sandwich cookies/crackers, not prepared sandwich references.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 397842 | sr28: Rolls, hamburger or hotdog, plain | Bakery > Cookies > Banana Coconut | VIRGIN COCO, COCONUT COOKIE ROLLS, BANANA |
| 429239 | sr28: Rolls, hamburger or hotdog, plain | Bakery > Rolls > Vanilla | VIVELI, WAFER ROLLS WITH DELICIOUS VANILLA CREAM FILLING |
| 429869 | sr28: Rolls, hamburger or hotdog, plain | Bakery > Rolls > Wafer Vanilla | VIVELI, TWIST, WAFER ROLLS, VANILLA |
| 429870 | sr28: Rolls, hamburger or hotdog, plain | Bakery > Rolls > Strawberry | VIVELI, WAFER ROLLS WITH A DELICIOUS STRAWBERRY CREAM FILLING |
| 719096 | sr28: Rolls, hamburger or hotdog, plain | Bakery > Rolls > Vanilla Sugar Wafer > Sugar Free | ROLL BREAK WAFER |
| 719312 | sr28: Rolls, hamburger or hotdog, plain | Bakery > Rolls > Sugar Wafer Strawberry | ROLL BREAK, STRAWBERRY |
| 731548 | sr28: Rolls, hamburger or hotdog, plain | Bakery > Rolls > Chocolate Hazelnut > Filled | CHOCOLATE HAZELNUT CREME FILLED WAFER ROLLS |
| 731922 | sr28: Rolls, hamburger or hotdog, plain | Bakery > Rolls > Chocolate Fudge Creme | CHOCOLATE FUDGE CREME FILLED WAFER ROLLS |

### meat_or_charcuterie_roll_has_bakery_roll_reference

- rows: `73`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Use meat, poultry, or charcuterie roll references; do not map to bread rolls/buns.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 407937 | sr28: Rolls, pumpernickel \| esha: Roll, 8-grain | Meat & Seafood > Charcuterie > Charcuterie Rolls > Plain | PORK ROLL |
| 1507749 | sr28: Rolls, dinner, plain, commercially prepared (includes brown-and-serve) \| esha: Roll, cheese \| matched_key: roll cheese | Meat & Seafood > Charcuterie > Charcuterie Rolls > Ham Swiss American Cheese > Smoked | SMITHFIELD, READY, SNACK, GO!, SMOKED HAM & SWISS AMERICAN CHEESE |
| 1855033 | sr28: Rolls, dinner, plain, commercially prepared (includes brown-and-serve) \| esha: Roll, dinner, prepared from recipe with 2% milk, 2 1/2" | Meat & Seafood > Charcuterie > Charcuterie Rolls > Tangy | SHOPRITE, HICKORY SMOKED PORK ROLL, TANGY, TANGY |
| 1855034 | sr28: Rolls, pumpernickel \| esha: Roll, 8-grain | Meat & Seafood > Charcuterie > Charcuterie Rolls > Hickory | SHOPRITE, PORK ROLL, HICKORY SMOKED, HICKORY SMOKED |
| 1927859 | sr28: SUBWAY, cold cut sub on white bread with lettuce and tomato | Meat & Seafood > Charcuterie > Charcuterie Rolls > Prosciutto Mozzarella > Rolled | PROSCIUTTO PANINO THIN SLICED MOZZARELLA ROLLED WITH PROSCIUTTO |
| 1931409 | sr28: Rolls, pumpernickel \| esha: Roll, 8-grain | Meat & Seafood > Charcuterie > Charcuterie Rolls > Uncured | PORK ROLL |
| 1938067 | fndds: Sushi roll, eel \| sr28: Rolls, hamburger or hotdog, plain \| esha: Roll, dinner, prepared from recipe with 2% milk, 2 1/2" \| matched_key: rol | Meat & Seafood > Charcuterie > Charcuterie Rolls > Eel Avocado Cucumber Shrimp Tempura Imitation Crab | GREEN DRAGON ROLL |
| 1941019 | fndds: roll cheese \| sr28: Rolls, dinner, plain, commercially prepared (includes brown-and-serve) \| esha: Roll, cheese \| matched_key: roll cheese | Meat & Seafood > Charcuterie > Charcuterie Rolls > Pepperoni Cheese | ROLL, PEPPERONI & CHEESE |

### salad_kit_has_component_reference

- rows: `71`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Use salad-kit/salad references instead of croutons, dressing, lettuce, cheese, or topping references.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 737306 | fndds: croutons \| sr28: Croutons, seasoned \| esha: Croutons, cheese garlic, classic cut \| matched_key: croutons | Produce > Salad Kits > Caesar | ROMAINE LETTUCE, CAESAR DRESSING, SHREDDED CHEESE AND CROUTONS CAESAR SALAD KIT |
| 937340 | fndds: croutons \| sr28: Croutons, seasoned \| esha: Croutons, cheese garlic, classic cut \| matched_key: croutons | Produce > Salad Kits > Caesar | ROMAINE LETTUCE, CAESAR DRESSING, SHREDDED CHEESE AND CROUTONS CAESAR SALAD KIT |
| 2140184 | sr28: Croutons, seasoned \| esha: Croutons \| matched_key: croutons | Produce > Salad Kits > Honey Dijon | BABY SPINACH, RED CHARD, CARROTS, HONEY DIJON DRESSING, UNCURED BACON CRUMBLES AND CORNBREAD CROUTONS SALAD KIT, SPINACH & BACON |
| 2142412 | sr28: Croutons, seasoned \| esha: Croutons, onion & garlic, classic cut \| matched_key: croutons | Produce > Salad Kits > Roasted Garlic > Chopped | ROASTED GARLIC CHOPPED ROMAINE, SHREDDED BROCCOLI, RED CABBAGE, HERB CROUTON CRUMBLE, CELERY, SMOKED WHITE CHEDDAR CHEESE, GREEN ONION, PARS |
| 2147215 | sr28: Croutons, seasoned \| esha: Croutons, garlic parmesan \| matched_key: croutons | Produce > Salad Kits > Kale Caesar | KALE CAESAR KALE, SHAVED HARD GRATING PARMESAN CHEESE, GARLIC BRIOCHE CROUTONS WITH CAESAR DRESSING SALAD KIT, KALE CAESAR |
| 2174174 | sr28: Croutons, seasoned \| esha: Croutons, garlic parmesan \| matched_key: croutons | Produce > Salad Kits > Caesar > Chopped | CAESAR ROMAINE LETTUCE, CRUMBLED GARLIC CROUTONS, SHREDDED PARMESAN CHEESE AND CAESAR DRESSING CHOPPED SALAD KIT, CAESAR |
| 2176061 | sr28: Croutons, seasoned \| esha: Croutons, cracked pepper & parmesan, generous cut \| matched_key: croutons | Produce > Salad Kits > Bacon Caesar Black Pepper | BACON CAESAR ROMAINE LETTUCE, CAESAR ROMANO DRESSING, SEASONED HERB CROUTONS, SHAVED PARMESAN CHEESE, UNCURED BACON AND BLACK PEPPER SALAD K |
| 2178642 | sr28: Croutons, seasoned \| esha: Croutons, garlic parmesan \| matched_key: croutons | Produce > Salad Kits > Caesar > Chopped | ULTIMATE CAESAR CHOPPED ROMAINE, CROUTONS, SHAVED PARMESAN CHEESE AND CAESAR SEASONING WITH CREAMY CAESAR DRESSING SALAD KIT, ULTIMATE CAESA |

### frozen_ice_cream_has_bakery_roll_reference

- rows: `45`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Use frozen dessert references for ice cream rolls/bars; do not map to bread rolls or dough.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 483361 | fndds: pudding bread \| sr28: Bread, paratha, whole wheat, commercially prepared, frozen \| esha: Bread Pudding, chocolate, frozen \| matched_key: pud | Frozen > Ice Cream > Bread Pudding > Plain | HOT BREAD PUDDING |
| 905490 | fndds: cake jelly roll | Frozen > Ice Cream > Semifreddo > Wild Berries Strawberry | DELICIOUS SEMIFREDDO ON A BED OF SOFT SPONGE CAKE AND COVERED WITH WILD BERRIES AND STRAWBERRY JELLY, WILD BERRIES |
| 1388931 | sr28: Cinnamon buns, frosted (includes honey buns) \| matched_key: roll sweet cinnamon bun no frosting | Frozen > Frozen Yogurt > Cinnamon Bun Caramel > Light | CINNAMON BUN CINNAMON CARAMEL FLAVORED LIGHT ICE CREAM WITH CINNAMON BUN PIECES |
| 1536026 | sr28: Rolls, dinner, sweet \| esha: Sweet Roll, cinnamon, cream cheese, frozen, 4.75 ounce, FS | Frozen > Ice Cream > Cinnamon > Vegan | SWEET ACTION, ICE CREAM, VEGAN CINNAMON ROLL |
| 1831521 | sr28: Cookies, sugar, refrigerated dough | Frozen > Ice Cream > Pink > Frosted | FROSTED PINK SUGAR COOKIES, FROSTED |
| 1851541 | sr28: Rolls, hamburger or hotdog, plain \| esha: Roll, garlic, frozen dough \| matched_key: roll | Frozen > Ice Cream > Spiced Pumpkin Roll | YUENGLINGS, ICE CREAM, SPICED PUMPKIN ROLL, SPICED PUMPKIN ROLL |
| 1857339 | sr28: Rolls, hamburger or hotdog, plain \| esha: Roll, garlic, frozen dough \| matched_key: roll | Frozen > Ice Cream > Mocha Chocolate Cookie Crunch > Low Fat | ICE CREAM ROLL WITH CHOCOLATE COOKIE CRUNCH OUTSIDE, MOCHA MUD |
| 1865134 | sr28: Rolls, hamburger or hotdog, plain \| esha: Roll, dinner, country potato \| matched_key: roll | Frozen > Ice Cream Cakes > Vanilla Chocolate > Light | DEAN'S, COUNTRY FRESH, ICE CREAM CAKE ROLL, VANILLA, CHOCOLATE, VANILLA, CHOCOLATE |

### tortilla_has_cookie_cracker_or_bun_reference

- rows: `29`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Use tortilla/taco-shell/wrap references instead of cookie, cracker, or bun references.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 520089 | sr28: Cracker, meal | Meal > Fillo Wraps > Feta | FETA FILLO WRAPS |
| 1377102 | sr28: Cinnamon buns, frosted (includes honey buns) | Bakery > Tortillas > Corn | SLIDER CORN TORTILLAS |
| 1514873 | sr28: Rice cake, cracker (include hain mini rice cakes) | Frozen > Appetizers > Chicken Ranchero | CHICKEN RANCHERO MINI WRAPS |
| 1606456 | esha: Pastry, toaster, chocolate chip cookie dough | Bakery > Toaster Pastries > Veggie > Organic | ORGANIC VEGGIE WRAPS |
| 1633677 | sr28: Cracker, meal | Meal > Meal Starters > Beef Rice Black Beans | OLD EL PASO, TORTILLA STUFFERS |
| 1893547 | sr28: Cracker, meal | Frozen > Appetizers > Seasoned Chicken | SEASONED CHICKEN FOR LETTUCE WRAPS |
| 1933269 | sr28: Cinnamon buns, frosted (includes honey buns) | Meal > Sandwiches > Wrap Sandwich > Turkey Provolone Sliders | WRAPS & SANDWICHES, TURKEY PROVOLONE SLIDERS WITH APPLES |
| 1967188 | fndds: crackers \| sr28: Crackers, standard snack-type, regular \| esha: Cracker, snack, Goya \| matched_key: crackers | Snack > Crackers > Ranch | RANCH BAKED TORTILLA SNACKS, RANCH |

### candy_has_frozen_dessert_reference

- rows: `22`
- severity: `medium`
- confidence: `medium`
- action: `source_or_reference_review`
- likely fix: Review whether the BFC/path is dirty or whether the reference should be candy/chocolate instead of ice cream.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 429894 | fndds: cookies & cream ice cream | Snack > Chocolate Candy > Cookies > Stripes Honey | LUXURY BAKERY, CHOCOLATE STRIPES, HONEY |
| 603356 | fndds: cookies & cream ice cream | Snack > Chocolate Candy > Cookies > Milk Chocolate Cinnamon | CINNAMON COOKIES MILK CHOCOLATE, CINNAMON COOKIES |
| 771074 | fndds: cookies & cream ice cream | Snack > Chocolate Candy > Cookies > Oreo Creme | MILKA CHOCOLATE OREO COOKIES AND CREME 100 GR |
| 1863692 | esha: Ice Cream, caramel turtle truffle, reduced fat, with o added sugar | Snack > Chocolate Candy > Truffle > Pecan Caramel | ORIGINAL PECAN THE ORIGINAL CARAMEL NUT CLUSTER TURTLES, ORIGINAL PECAN |
| 1890863 | fndds: ice cream \| matched_key: ice cream | Frozen > Ice Cream > Cotton Candy | COTTON CANDY, ICE CREAM |
| 1899038 | esha: Ice Cream, caramel turtle truffle, reduced fat, with o added sugar | Snack > Chocolate Candy > Truffle > Pecans Sea Salt Caramel | TURTLES TRUFFLES, SEA SALT CARAMEL |
| 1913270 | fndds: ice pop | Snack > Candy > Frozen Tube > Wild Cherry | ICEY TUBE, WILD CHERRY |
| 2045596 | esha: Ice Cream, pecan praline | Snack > Candy > Pralines > Habanero Pecan | HABANERO PECAN PRALINES |

### ice_cream_cone_has_baking_mix_or_cookie_reference

- rows: `22`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Use ice-cream-cone references, not baking mix or cookie references.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 1459791 | fndds: Cookie, sugar wafer \| sr28: Cookies, Marie biscuit \| esha: Cookies, Generation Max, M&M's, FS \| matched_key: cookies &  (parent-default) | Snack > Ice Cream Cones > Sugar Cones > Plain | NABISCO COMET CUPS SUGAR CONES 1X5.25 OZ |
| 2124166 | esha: Ice Cream, Cookie & cream, Oreo | Frozen > Ice Cream Cones > Oreo Cookies > No Sugar Added > Light | OREO COOKIES & CREAM FLAVORED LIGHT ICE CREAM CONE WITH OREO COOKIE CRUNCH, OREO |
| 2172746 | sr28: Cookies, graham crackers, chocolate-coated \| esha: Cookies, Generation Max, M&M's, FS \| matched_key: cookies &  (parent-default) | Snack > Ice Cream Cones > Waffle Cones > Cookies And Cream | COOKIES & CREAM WAFFLE CONE CUPS, COOKIES & CREAM |
| 2215818 | sr28: Cookies, sugar, refrigerated dough \| esha: Cookies, Generation Max, M&M's, FS \| matched_key: cookies &  (parent-default) | Snack > Ice Cream Cones > Sugar Cones > Oreo Pieces | OREO PIECES SUGAR CONES COOKIE, OREO PIECES |
| 2269298 | esha: Ice Cream, chocolate chip cookie dough, light | Frozen > Ice Cream Cones > Chocolate Chip Cookie Dough > Light | CHOCOLATE CHIP COOKIE DOUGH LIGHT ICE CREAM CONES, CHOCOLATE CHIP COOKIE DOUGH |
| 2467289 | esha: Ice Cream, mint chocolate cookie | Frozen > Ice Cream Cones > Chocolate Butter Cookie | CHOCOLATE BUTTER COOKIE ICE CREAM CONE, CHOCOLATE BUTTER COOKIE |
| 2481410 | sr28: Cookies, graham crackers, chocolate-coated \| esha: Cookies, Generation Max, M&M's, FS \| matched_key: cookies &  (parent-default) | Snack > Ice Cream Cones > Waffle Cones > White Chocolate | WHITE CHOCOLATE FLAVOR WAFFLE CONE SNACKES, WHITE CHOCOLATE |
| 2490197 | esha: Ice Cream, chocolate chip cookie dough | Frozen > Ice Cream Cones > Chocolate Chip Cookie Dough Chocolate Brownie Vanilla | O'CHUNKA CHOCOLATE RICH AND CHUNKY CHOCOLATE CHIP COOKIE DOUGH MIXED WITH SUPER VELVETY CHOCOLATE BROWNIE DOUGH, NESTLED IN VANILLA ICE CREA |

### cheese_has_meal_sandwich_reference

- rows: `20`
- severity: `high`
- confidence: `high`
- action: `reference_remap_candidate`
- likely fix: Use cheese references for cheese slices; sandwich is only a use/form cue.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 1847029 | fndds: turkey sandwich on white \| sr28: Sandwich spread, meatless \| esha: Sandwich, turkey breast, with flatbread, 6" \| matched_key: turkey sandwic | Dairy > Cheese > Sandwich Platter > Turkey Breast Havarti | PINWHEEL PLATTER WITH TURKEY BREAST & HAVARTI CHEESE, TURKEY BREAST & HAVARTI CHEESE |
| 1952225 | esha: Seasoning, tofu burger, dry mix | Dairy > Cheese > Burger Mix-Ins > Spicy Jalapeno Pepper Jack | SPICY JALAPENOS PLUS PEPPER JACK CHEESE BURGER MIX-INS, SPICY JALAPENOS PLUS PEPPER JACK CHEESE |
| 2064419 | sr28: Sandwich spread, meatless | Dairy > Cheese > Sandwich > Ham Provolone Mortadella Tomato > Smoked | TUSCAN MEAT & CHEESE |
| 2072721 | sr28: Sandwich spread, meatless | Dairy > Cheese > Sandwich > Prosciutto Provolone | PROSCIUTTO PROVOLONE CHEESE & TARALLI BREAD |
| 2133303 | fndds: tomato sandwich on white \| esha: Sandwich, cold cut combo, with wheat, 6" \| matched_key: tomato sandwich  (parent-default) | Dairy > Cheese > Soup and Sandwich Combo > Tomato Apple Cheddar Grilled | HOMEMADE TOMATO SOUP WITH APPLE CHEDDAR GRILLED CHEESE |
| 2135546 | sr28: Sandwich spread, meatless | Dairy > Cheese > Egg Scrambles > White Cheddar Swiss Monterey Jack | THREE CHEESE REAL EGG WHITES, CHEDDAR, SWISS & MONTEREY JACK CHEESES SIMPLE SCRAMBLES, THREE CHEESE |
| 2143299 | sr28: Sandwich spread, meatless | Dairy > Cheese > Sandwich > Pepperoni Provolone | PEPPERONI, PROVOLONE CHEESE & TARALLI BREAD |
| 2188824 | esha: Sandwich, chicken, oven roasted, with flatbread, 6" | Dairy > Cheese > Flatbread > Roasted Mushrooms Onions Asiago | FLATBREAD WITH ROASTED MUSHROOMS, ONIONS, AND ASIAGO CHEESE |

### pie_crust_or_shell_has_finished_pie_reference

- rows: `13`
- severity: `medium`
- confidence: `medium`
- action: `reference_review_candidate`
- likely fix: Use pie crust/shell references; finished pie references are only acceptable when no crust/shell proxy exists.

| fdc_id | suspect refs | path | title |
|---|---|---|---|
| 541853 | fndds: chocolate pie | Pantry > Baking Mixes > Pie Crust Mix > Chocolate | SERVE OVER HOT BISCUITS OR MAKE AN OLD FASHIONED CHOCOLATE PIE |
| 1402290 | esha: Ice Cream, pumpkin pie | Frozen > Ice Cream > Pumpkin Cinnamon Graham | PUMP AND CIRCUMSTANCE PUMPKIN ICE CREAM WITH CINNAMON GRAHAM RIBBON AND PIE CRUST PIECES |
| 1636393 | fndds: Pie, lemon meringue | Pantry > Baking Mixes > Pie Crust Mix > Lemon | LEMON FLAVOR MERINGUE PIE DESSERT, LEMON |
| 2132942 | esha: Ice Cream, pumpkin pie | Frozen > Ice Cream > Pumpkin Pie Cinnamon Graham | PUMPKIN PIE ICE CREAM WITH CINNAMON GRAHAM RIBBON & PIE CRUST PIECES, PUMPKIN PIE |
| 2447511 | esha: Ice Cream, pumpkin pie | Frozen > Ice Cream > Pumpkin Pie Cinnamon | PUMPKIN PIE MADE WITH REAL PUMPKIN PUREE, CINNAMON & PIE CRUST PIECES ICE CREAM, PUMPKIN PIE |
| 2451708 | esha: Ice Cream, pumpkin pie | Frozen > Ice Cream > Pumpkin Pie Cinnamon Nutmeg | PUMPKIN PIE BITS OF PIE CRUST, FINE-GROUND CINNAMON AND NUTMEG, PUMPKIN ICE CREAM, PUMPKIN PIE |
| 2455607 | esha: Ice Cream, pumpkin pie | Frozen > Ice Cream > Blackberry Crumble Ripple Pie Crust Pieces | BLACKBERRY CRUMBLE BLACKBERRY ICE CREAM WITH PIE CRUST PIECES AND BLACKBERRY RIPPLE, BLACKBERRY CRUMBLE |
| 2465601 | sr28: Pie fillings, apple, canned \| esha: Pie, snack, apple, hot, baked | Bakery > Cake > Apple Pie > Cinnamon | HOT APPLE PIE DICED APPLES, CINNAMON AND SUGAR TUCKED INTO A CRISPY PIE CRUST HOT SNACKS, HOT APPLE PIE |
