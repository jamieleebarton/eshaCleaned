# Kimi Swarm Audit Report

**Dataset:** `retail_mapper/v2/full_corpus_audit.csv`  
**Rows audited:** 388,793  
**Bug classes found:** 13  

---

## 1. Adjacent redundant words in leaf (314 rows)

Leaf segment repeats the same word consecutively (e.g., Chocolate Chocolate).

**Samples (fdc_id | detail | path/context):**

- `2658109` | Dark Chocolate Chocolate | Beverage > Plant Milk > Almond Milk > Dark Chocolate Chocolate
- `1575644` | Dark Chocolate Chocolate | Beverage > Plant Milk > Almond Milk > Dark Chocolate Chocolate
- `2098223` | Dark Chocolate Chocolate | Beverage > Plant Milk > Almond Milk > Dark Chocolate Chocolate
- `2466742` | Dark Chocolate Chocolate | Beverage > Plant Milk > Almond Milk > Dark Chocolate Chocolate
- `2566532` | Chocolate Chocolate Chip | Bakery > Bagels > Chocolate Chocolate Chip
- `2653066` | Cinnamon Cinnamon Sugar | Bakery > Bagels > Cinnamon Cinnamon Sugar
- `1885155` | Cinnamon Cinnamon Sugar | Bakery > Bagels > Cinnamon Cinnamon Sugar
- `2623258` | Cool Mint Chocolate Chocolate Chip | Snack > Bars > Energy Bars > Cool Mint Chocolate Chocolate Chip
- `2623256` | Mint Chocolate Chocolate Chip | Snack > Bars > Energy Bars > Mint Chocolate Chocolate Chip
- `2179375` | Cool Mint Chocolate Chocolate Chip | Snack > Bars > Energy Bars > Cool Mint Chocolate Chocolate Chip

---

## 2. Canned path but Frozen in title (4 rows)

Title explicitly states FROZEN/FRESHLY FROZEN but path routes to Canned. Processing-state contradiction.

**Samples (fdc_id | detail | path/context):**

- `2410174` | FRESH FROZEN GREEN CUT BEANS | Pantry > Canned Vegetables > Green Beans > Plain
- `2699190` | P.F. Chang's Home Menu Crispy Green Beans, Frozen Appetizers, 24 oz. | Pantry > Canned Vegetables > Green Beans > Plain
- `2699862` | Birds Eye C&W Tiny Whole Green Beans, Frozen Vegetable, 12 OZ | Pantry > Canned Vegetables > Green Beans > Plain
- `2699860` | Birds Eye C&W Petite Whole Green Beans, Frozen Vegetable, 14 OZ | Pantry > Canned Vegetables > Green Beans > Plain

---

## 3. Claims completely absent from retail_leaf_path (22,493 rows)

Claims column lists attributes (e.g., sweetened, organic, dairy_free) but none appear in the leaf path.

**Samples (fdc_id | detail | path/context):**

- `2542320` | dairy_free | Beverage > Plant Milk > Almond Milk > Plain
- `1910683` | pure | Beverage > Plant Milk > Almond Milk > Chocolate
- `2491056` | energy | Beverage > Coffee > Coffee Drink > Almond Milk White Chocolate
- `2615224` | hint | Beverage > Plant Milk > Almond Milk > Pumpkin Spice
- `2062906` | natural | Beverage > Plant Milk > Almond Milk > Plain
- `718122` | iced | Beverage > Plant Milk > Almond Milk > Lemon Chai Spice
- `2210638` | dairy_free | Beverage > Plant Milk > Almond Milk > Holiday Nog
- `2468243` | unflavored | Beverage > Protein Powders > Almond
- `2477248` | natural | Beverage > Protein Drinks > Protein Shake > Vanilla Almond
- `1910684` | pure | Beverage > Plant Milk > Almond Milk > Vanilla

---

## 4. Plant-based alternative routed to Dairy (5 rows)

Title clearly states plant-based/alternative but path lands in Dairy family instead of Beverage/Plant Milk or Pantry.

**Samples (fdc_id | detail | path/context):**

- `2624212` | CHOCOLATE PLANT-BASED MILK, CHOCOLATE | Dairy > Flavored Milk > Chocolate Milk
- `2688486` | Coffee mate Natural Bliss Peppermint Mocha Flavored Oat Milk Creamer, Plant Based Liquid Coffee Creamer, 32 Fl Oz | Dairy > Cream > Coffee Creamer
- `1980149` | DAIRY FREE CREAMY OATMILK & COCONUTMILK HALF & HALF ALTERNATIVE | Dairy > Cream > Half & Half
- `2604692` | CHOCOLATE PLANT-BASED BARLEYMILK, CHOCOLATE | Dairy > Flavored Milk > Chocolate Milk
- `2568946` | OAT MILK PLANT BASED CHOCOLATE PUDDING, CHOCOLATE | Dairy > Pudding

---

## 5. Small PI groups (<30 SKUs) split across multiple paths (1,101 rows)

One-home-per-PI test uses a 30-SKU dominance threshold; these smaller groups slip through and get split across canonical paths.

**Samples (fdc_id | detail | path/context):**

- `1766233` | Dried Cranberries | Snack > Dried Fruit > Dried Cranberries
- `568483` | Taralli | Snack > Crackers > Taralli
- `356015` | Baby Food | Baby & Toddler > Baby Food
- `2095966` | Cranberries | Snack > Dried Fruit > Cranberries
- `2440625` | Canned Vegetables | Pantry > Canned Vegetables
- `2746364` | Crescent Dough | Pantry > Baking Mixes > Crescent Dough
- `2389719` | Lentils | Pantry > Beans > Lentils
- `2682805` | Puff Pastry | Pantry > Baking Mixes > Puff Pastry
- `2682740` | Pizza Crust | Pantry > Baking Mixes > Pizza Crust
- `1892430` | Chicken and Dumplings | Pantry > Soup > Chicken and Dumplings

---

## 6. Plant/Vegan BFC but animal-derived path (46 rows)

BFC indicates plant/vegan/vegetarian but canonical path routes into meat, beef, chicken, or seafood.

**Samples (fdc_id | detail | path/context):**

- `1983820` | Vegetarian Frozen Meats | Meal > Plant Based > Ground Beef
- `2020583` | Vegetarian Frozen Meats | Meal > Plant Based > Meat Crumbles
- `2599590` | Vegetarian Frozen Meats | Meal > Plant Based > Ground Beef
- `1951257` | Vegetarian Frozen Meats | Meal > Plant Based > Meatballs
- `2414179` | Vegetarian Frozen Meats | Meal > Plant Based > Meatless Crumbles
- `2606619` | Vegetarian Frozen Meats | Meal > Plant Based > Meatballs
- `1869600` | Vegetarian Frozen Meats | Meal > Plant Based > Meatballs
- `2663759` | Vegetarian Frozen Meats | Meal > Plant Based > Crab Cakes
- `2425643` | Vegetarian Frozen Meats | Meal > Plant Based > Crab Cakes
- `1854765` | Vegetarian Frozen Meats | Meal > Plant Based > Chicken Strips

---

## 7. FNDDS code present but description empty (23 rows)

Referential integrity gap: FNDDS code exists but the description field is blank.

**Samples (fdc_id | detail | path/context):**

- `2143277` | 64100000 | RED GRAPEFRUIT IN 100% JUICE, RED GRAPEFRUIT
- `1963060` | 64100000 | RED GRAPEFRUIT IN 100% JUICE, RED GRAPEFRUIT
- `2489735` | 64101000 | CUMBERLAND FARMS, SPARKLING REAL FRUIT JUICE, COCONUT PINEAPPLE, COCONUT PINEAPPLE
- `1458859` | 64100000 | Brisk Fruit Punch Juice Drink 24 Fluid Ounce Can
- `2556642` | 64100000 | WELCH'S 11.5 FL OZ JUICE DRINK - FRUIT PUNCH
- `2556640` | 64100000 | WELCH'S 16 FL OZ JUICE DRINK - FRUIT PUNCH
- `2722534` | 64100000 | WELCH'S 10 FL OZ JUICE DRINK - FRUIT PUNCH (6 PK)
- `2723010` | 64100000 | WELCH'S 16 FL OZ JUICE DRINK - FRUIT PUNCH
- `2556653` | 64100000 | WELCH'S 10 FL OZ JUICE DRINK - FRUIT PUNCH
- `2617027` | 64100120 | ORANGE CARROT JUICE BLEND DRINK, ORANGE; CARROT

---

## 8. Cheeseburger in title but absent from path (13 rows)

Title explicitly names cheeseburger but canonical path contains no Burger or Sandwich signal.

**Samples (fdc_id | detail | path/context):**

- `1930426` | CHEESEBURGERS | Frozen > Single Entrees
- `2127323` | MINI CHEESEBURGERS FLAME BROILED BEEF STEAKS WITH AMERICAN CHEESE ON HEARTH BAKED BUNS SANDWICHES, MINI CHEESEBURGERS | Frozen > Appetizers
- `2019176` | SAM'S CHOICE, MINI ANGUS BEEF & BACON CHEESEBURGERS | Frozen > Appetizers
- `2677873` | CHEESE SLIDERS CHEESEBURGERS, CHEESE | Frozen > Appetizers > Sliders
- `1509861` | CHEESE SLIDERS CHEESEBURGERS, CHEESE | Frozen > Appetizers > Sliders
- `2114670` | CHEESE SLIDERS CHEESEBURGERS, CHEESE | Frozen > Appetizers > Sliders
- `1902823` | CHEESE SLIDERS CHEESEBURGERS, CHEESE | Frozen > Appetizers > Sliders
- `2067030` | JALAPENO CHEESE SLIDERS JALAPENO CHEESEBURGERS, JALAPENO CHEESE | Frozen > Appetizers > Sliders
- `2543529` | JALAPENO CHEESE SLIDERS CHEESEBURGERS, JALAPENO CHEESE | Frozen > Appetizers > Sliders
- `2622892` | BACON CHEDDAR CHEESEBURGERS, BACON CHEDDAR CHEESE | Meat & Seafood > Beef > Beef Patties

---

## 9. Frozen path but title starts with Fresh (33 rows)

Product title starts with Fresh but path routes to Frozen. Processing-state contradiction.

**Samples (fdc_id | detail | path/context):**

- `1616483` | FRESH FROZEN BAJA ROASTED CORN, CORN, BLACK BEANS, RED PEPPERS, GREEN PEPPERS, ROASTED ONIONS & GREEN CHILIES CORN BLEND, BAJA ROASTED | Frozen > Vegetables > Vegetable Blend > Baja Roasted
- `2410179` | FRESH FROZEN GREEN BEANS CUT BEANS | Frozen > Vegetables > Green Beans > Plain
- `2410184` | FRESH FROZEN GREEN BEANS WHOLE BEANS | Frozen > Vegetables > Green Beans > Plain
- `2474381` | FRESH FROZEN GREEN BEANS, WAX BEANS & CARROTS | Frozen > Vegetables > Vegetable Blend > Green Beans Wax Carrots
- `356545` | FRESH & EASY, BUTTERMILK PANCAKES | Frozen > Pancakes > Buttermilk
- `356544` | FRESH & EASY, HOMESTYLE WAFFLES | Frozen > Waffles > Plain
- `2546835` | FRESH MINT CHIP PLANT-BASED GELATO, FRESH MINT CHIP | Frozen > Gelato > Mint Chip > Plant Based
- `2472613` | FRESH MINT CHOCOLATE CHIP GELATO, FRESH MINT CHOCOLATE CHIP | Frozen > Gelato > Mint Chip Fresh Chocolate Chip
- `1902432` | FRESH MINT LEAF ICE CREAM WITH BROWN SUGAR & DARK CHOCOLATE CHIPS, DIRTY MINT CHIP | Frozen > Ice Cream > Dark Chocolate Chip Mint Brown Sugar
- `1970204` | FRESH MINT LEAF, BROWN SUGAR & DARK CHOCOLATE CHIP FROZEN DESSERT WITH DOUBLE CHOCOLATE COOKIES SANDWICH, DIRTY MINT CHIP | Frozen > Ice Cream > Mint Chocolate Chip Chocolate

---

## 10. Ice Cream BFC but not Frozen path (950 rows)

Branded food category indicates ice cream, frozen yogurt, or gelato but canonical path is not Frozen family.

**Samples (fdc_id | detail | path/context):**

- `2195389` | GRAHAM SLAM GRAHAM FLAVORED ICE CREAM WITH GRAHAM CRACKER SWIRL AND HONEYCOMB CANDIES, GRAHAM SLAM | Snack > Crackers
- `2150411` | S'MORES GRAHAM CRACKER FROZEN DAIRY DESSERT DIPPED IN A CHOCOLATEY COATING WITH A BURST OF MARSHMALLOW SWIRL IN THE MIDDLE POPS, S'MORES | Snack > Crackers
- `2158421` | S'MORES GRAHAM CRACKER FROZEN DAIRY DESSERT DIPPED IN A CHOCOLATEY COATING WITH A BURST OF MARSHMALLOW SWIRL IN THE MIDDLE POPS, S'MORES | Snack > Crackers
- `2504111` | BANANA GRAHAM BANANA PUDDING PREMIUM ICE CREAM WITH CRUSHED GRAHAM CRACKER SWIRLS, BANANA GRAHAM | Snack > Crackers
- `2544694` | CINNABON CINNAMON ROLL FLAVOR, CINNAMON SWIRL AND DOUGH PIECES FROZEN DAIRY DESSERT, CINNABON | Bakery > Pastry > Cinnamon Rolls
- `2581240` | CHURRAY FOR CHURROS! BUTTERY CINNAMON ICE CREAM WITH CHURRO PIECES & CRUNCHY CINNAMON SWIRLS, CHURRAY FOR CHURROS! | Bakery > Pastry > Churros
- `1832515` | FRESH FRUIT NANCE, FRUIT | Produce > Fresh > Ice Cream
- `2639974` | CINNAMON ROLL PREMIUM ICE CREAM WITH STICKY BUN DOUGH PIECES & A FROSTING SWIRL, CINNAMON ROLL | Bakery > Pastry > Cinnamon Rolls
- `2152567` | BIRTHDAY CAKE SUNDAE FLAVORED BIRTHDAY CAKE ICE CREAM WITH A BLUE FROSTING SWIRL AND SPRINKLES ICE CREAM CUPS, BIRTHDAY CAKE SUNDAE | Snack > Ice Cream Cones
- `2285544` | BIRTHDAY PARTY BIRTHDAY CAKE FLAVORED REDUCED FAT ICE CREAM WITH A THICK INNER SWIRL OF BLUE FROSTING COVERED WITH WHITE CONFECTIONARY COATING AND COLORFUL CONFETTI SPRINKLES ALL INSIDE A CRUNCHY SUGAR CONE, BIRTHDAY PARTY | Snack > Ice Cream Cones > Sugar Cones

---

## 11. Soup in title but not in Soup/Broth/Chili/Meal path (315 rows)

Title names soup (excluding mixes, bases, croutons, breads) but canonical path lacks Soup, Broth, Chili, or Meal segment.

**Samples (fdc_id | detail | path/context):**

- `2611736` | SOUTHWEST-STYLE BLACK BEAN SOUP, SOUTHWEST-STYLE BLACK BEAN | Pantry > Beans > Black Beans
- `2431605` | BLACK BEAN SOUP | Pantry > Beans > Black Beans
- `2431607` | BLACK BEAN SOUP | Pantry > Beans > Black Beans
- `2431601` | BLACK BEAN SOUP | Pantry > Beans > Black Beans
- `2339569` | GREAT NORTHERN BEAN SOUP | Pantry > Beans > Great Northern Beans
- `2388260` | TURMERIC CAULIFLOWER SOUP, TURMERIC CAULIFLOWER | Snack > Veggie Snacks > Veggie Straws
- `2388262` | MORINGA GREEN PEA SOUP, MORINGA GREEN PEA | Snack > Veggie Snacks > Veggie Straws
- `2023165` | CLAM CHOWDER SOUP | Meat & Seafood > Shellfish > Clam
- `1646065` | CLAM CHOWDER SOUP, CLAM CHOWDER | Meat & Seafood > Shellfish > Clam
- `2023163` | CLAM CHOWDER SOUP | Meat & Seafood > Shellfish > Clam

---

## 12. Juice BFC but wrong family (20 rows)

Branded food category indicates Juice but canonical path routes to Snack, Meal, or other non-beverage family.

**Samples (fdc_id | detail | path/context):**

- `2579689` | FRUIT & VEGGIE BLENDS, FRUIT 'N GREENS | Snack > Fruit Leather > Fruit and Veggie Strips
- `2663516` | BERRY BLISS ACAI BOWL, BERRY BLISS | Meal > Bowls > Acai Bowl
- `2395454` | BREADFRUIT TOSTONES, BREADFRUIT | Snack > Veggie Snacks > Tostones
- `2675571` | CRISPY GREEN CRISPY FRUIT 100% FREEZE-DRIED MANGO, 0.63 OZ, 4 COUNT | Snack > Dried Fruit
- `2541918` | MANGO SWIRLED WITH CHAMOY SAUCE PREMIUM FROZEN FRUIT BAR, MANGO | Snack > Bars > Fruit Bars
- `1911379` | FRUIT & VEGGIE BARS, TANGERINE MEDLEY | Snack > Bars > Fruit Bars
- `2658426` | CRISPY GREEN CRISPY FRUIT 100% FREEZE-DRIED PEAR, 0.53 OZ, 4 COUNT | Snack > Dried Fruit > Dried Fruit Chips
- `2591674` | DRAGON FRUIT BLEND WITH COCONUT FLAKES SMOOTHIE BOWL, DRAGON FRUIT; COCONUT | Snack > Smoothie Bowls
- `2675554` | CRISPY GREEN CRISPY FRUIT 100% FREEZE-DRIED PINEAPPLE, 0.63 OZ, 4 COUNT | Snack > Dried Fruit
- `2675576` | CRISPY GREEN CRISPY FRUIT 100% FREEZE-DRIED TANGERINE, 0.42 OZ | Snack > Dried Fruit > Dried Fruit Chips

---

## 13. Canonical path exceeds 3 segments (5,438 rows)

canonical_path contract specifies family > type only (2 segments), yet 4+ segments appear (e.g., brand names or redundant nesting).

**Samples (fdc_id | detail | path/context):**

- `2740742` | Pantry > Sweeteners > Sugar > Frosting | Vanilla Dunkaroos 6 Count
- `2740717` | Pantry > Sweeteners > Sugar > Frosting | Vanilla DunkAroos 12 Count
- `2502438` | Pantry > Pickled > Pickles > Banana Peppers | MILD BANANA PEPPER RINGS, MILD BANANA PEPPER
- `2194021` | Pantry > Pickled > Pickles > Banana Peppers | MILD BANANA PEPPER CHUNKS, MILD BANANA
- `2520000` | Pantry > Pasta > Noodles > Beef Noodle | CHEF BOYARDEE Microwaveable Mini Beef, 14.25 OZ
- `2284323` | Bakery > Bread > Dough > Biscuit Dough | BISCUIT DOUGH
- `2091943` | Bakery > Bread > Dough > Biscuit Dough | SOUTHERN STYLE BISCUITS DOUGH
- `2650639` | Bakery > Bread > Dough > Biscuit Dough | Pillsbury Frozen Buttermilk Biscuit Dough 36 Count
- `2682538` | Bakery > Bread > Dough > Biscuit Dough | Pillsbury EZ Split Southern Style Biscuit Dough
- `2682472` | Bakery > Bread > Dough > Biscuit Dough | Pillsbury Whole Grain Rich Biscuit Dough

---


# Summary

This audit discovered **13 distinct bug classes** affecting **30,755 rows** in the 388,793-SKU corpus. Key themes include: (1) referential integrity gaps (empty FNDDS descriptions), (2) path/title contradictions (Canned vs Frozen, plant-based products in Dairy, cheeseburgers in Appetizers), (3) BFC/path family mismatches (ice cream in Snack, juice in Dried Fruit), (4) structural path issues (redundant leaf words, missing claim segments, overly deep canonical paths), and (5) taxonomy consistency failures below the existing 30-SKU one-home-per-PI threshold. These classes are not covered by the current 295 pytest invariants and represent actionable cleanup targets.
