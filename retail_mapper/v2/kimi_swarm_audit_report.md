# Kimi Swarm Audit Report

**Dataset:** `retail_mapper/v2/full_corpus_audit.csv`  
**Rows audited:** 462,711  
**Bug classes found:** 17  

---

## 1. Duplicate fdc_ids (47 rows)

Same fdc_id appears on multiple rows. Violates primary-key assumption.

**Samples (fdc_id, details):**

- `2317213` | Manuka Hunters Manuka Multiflora Honey 250gm | 2
- `2317246` | Manuka Hunters Manuka Multiflora Honey 500gm | 2
- `2317034` | Angel Food Dairy Free Mozzarella Block Alternative 1.0 Kg | 2
- `2317244` | Spring Blue Goat Gouda Cheese 200g | 2
- `2316901` | Handmade Kulfi Malai Almond 75g | 2
- `2317057` | Angel Food Dairy Free Cheddar Block Alternative 1kg | 2
- `2183203` | Rocket Fuel Sauce 300g | 2
- `2317262` | Plan*t Chick*n Nuggets 250g | 2
- `2183062` | Umi Dried Anchovy Fillet 150g | 2
- `475567` | SPRING ROLL SKIN | 2

---

## 2. Empty retail_leaf_path (42 rows)

retail_leaf_path is blank despite canonical_path being populated. Breaks leaf-path contract.

**Samples (fdc_id, details):**

- `9900002` | BANANAS | Produce > Fruit > Bananas
- `9900003` | RED DELICIOUS APPLES | Produce > Fruit > Apples > Red Delicious
- `9900004` | FUJI APPLES | Produce > Fruit > Apples > Fuji
- `9900005` | GALA APPLES | Produce > Fruit > Apples > Gala
- `9900006` | GRANNY SMITH APPLES | Produce > Fruit > Apples > Granny Smith
- `9900007` | RED ROME APPLES | Produce > Fruit > Apples > Rome
- `9900008` | PINK LADY APPLES | Produce > Fruit > Apples > Pink Lady
- `9900009` | NAVEL ORANGES | Produce > Fruit > Oranges > Navel
- `9900010` | LEMONS | Produce > Fruit > Lemons
- `9900011` | LEMONS | Produce > Fruit > Lemons > Small

---

## 3. Adjacent redundant words in leaf (324 rows)

Leaf segment repeats the same word consecutively (e.g., Chocolate Chocolate).

**Samples (fdc_id, details):**

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

## 4. Canned path but Frozen in title (99 rows)

Title explicitly states FROZEN/FRESHLY FROZEN but path routes to Canned. State contradiction.

**Samples (fdc_id, details):**

- `2239257` | FRESHLY FROZEN CUT GREEN BEANS | Pantry > Canned Vegetables > Green Beans > Plain
- `1385593` | FRESHLY FROZEN CUT GREEN BEANS | Pantry > Canned Vegetables > Green Beans > Plain
- `2071829` | FRESHLY FROZEN CUT GREEN BEANS | Pantry > Canned Vegetables > Green Beans > Plain
- `2427318` | STEAMIN' EASY FRESHLY FROZEN CUT GREEN BEANS | Pantry > Canned Vegetables > Green Beans > Plain
- `1567225` | FRESHLY FROZEN CUT GREEN BEANS | Pantry > Canned Vegetables > Green Beans > Plain
- `2407371` | JUST PICKED AND QUICKLY FROZEN CUT GREEN BEANS | Pantry > Canned Vegetables > Green Beans > Organic
- `2265409` | JUST PICKED AND QUICKLY FROZEN CUT GREEN BEANS | Pantry > Canned Vegetables > Green Beans > Plain
- `2410179` | FRESH FROZEN GREEN BEANS CUT BEANS | Pantry > Canned Vegetables > Green Beans > Plain
- `2410174` | FRESH FROZEN GREEN CUT BEANS | Pantry > Canned Vegetables > Green Beans > Plain
- `1567228` | FRESHLY FROZEN FRENCH CUT GREEN BEANS | Pantry > Canned Vegetables > Green Beans > French Cut

---

## 5. Claims completely absent from retail_leaf_path (35,274 rows)

Claims column lists attributes (e.g., sweetened, organic) but none appear in the leaf path.

**Samples (fdc_id, details):**

- `2242391` | sweetened | Beverage > Plant Milk > Almond Milk > Plain
- `2620669` | sweetened | Beverage > Plant Milk > Almond Milk > Plain
- `2500386` | sweetened | Beverage > Plant Milk > Almond Milk > Plain
- `2500397` | sweetened | Beverage > Plant Milk > Almond Milk > Plain
- `2482797` | sweetened | Beverage > Plant Milk > Almond Milk > Plain
- `2500399` | sweetened | Beverage > Plant Milk > Almond Milk > Plain
- `2621133` | sweetened | Beverage > Plant Milk > Almond Milk > Plain
- `2466729` | sweetened | Beverage > Plant Milk > Almond Milk > Plain
- `1898281` | sweetened | Beverage > Plant Milk > Almond Milk > Plain
- `2469263` | reduced_sugar | Beverage > Plant Milk > Almond Milk > Plain

---

## 6. Plant-based alternative routed to Dairy (410 rows)

Title clearly states plant-based/alternative but path lands in Dairy family instead of Beverage/Plant Milk or Pantry.

**Samples (fdc_id, details):**

- `2089440` | PASTEURIZED PROCESS CHEESE FOOD ALTERNATIVE, MOZZARELLA, MOZZARELLA | Dairy > Cheese
- `2089439` | PASTEURIZED PROCESS CHEESE FOOD ALTERNATIVE, MOZZARELLA BLOCK, MOZZARELLA BLOCK | Dairy > Cheese
- `2012124` | PASTEURIZED PROCESS CHEESE FOOD ALTERNATIVE, CHEDDAR & PEPPER JACK SHREDS, CHEDDAR & PEPPER JACK SHREDS | Dairy > Cheese
- `2012123` | PASTEURIZED PROCESS CHEESE FOOD ALTERNATIVE, CHEDDAR SLICES, CHEDDAR SLICES | Dairy > Cheese
- `2093490` | FOLLOW YOUR HEART, AMERICAN STYLE CHEESE ALTERNATIVE | Dairy > Cheese
- `2014354` | FOLLOW YOUR HEART, AMERICAN STYLE CHEESE ALTERNATIVE | Dairy > Cheese
- `2388282` | AMERICAN STYLE PLANT-BASED SLICED CHEESE, AMERICAN STYLE | Dairy > Cheese
- `2607234` | PLANT-BASED AMERICAN CHEESE | Dairy > Cheese
- `2588965` | AMERICAN STYLE PLANT BASED SLICES NOT CHEESE | Dairy > Cheese
- `2604399` | PLANT-BASED AMERICAN STYLE CHEESE SLICES | Dairy > Cheese

---

## 7. BFC=Cheese but routed to Bakery (non-cheesecake) (43 rows)

Branded food category is Cheese but canonical path puts it in Bakery (Danish blue cheese in Pastry, etc.).

**Samples (fdc_id, details):**

- `2308869` | CREAM CHEESE KING CAKE, CREAM CHEESE | Bakery > Cake
- `1967090` | DANISH BRIE CHEESE, DANISH BRIE | Bakery > Pastry > Danishes
- `2597856` | TRADITIONAL DANISH FLAVOR BLUE CHEESE | Bakery > Pastry > Danishes
- `2373480` | DANISH BLUE CHEESE, DANISH BLUE | Bakery > Pastry > Danishes
- `2093620` | DANISH BLUE CHEESE | Bakery > Pastry > Danishes
- `2428502` | DANABLU DANISH BLUE CHEESE 50%, DANISH BLUE | Bakery > Pastry > Danishes
- `2407903` | DANISH BLUE CHEESE, DANISH BLUE | Bakery > Pastry > Danishes
- `2384499` | SALTY & SHARP FLAVORED DANISH BLUE CHEESE, SALTY & SHARP | Bakery > Pastry > Danishes
- `1858127` | DANISH BLUE CHEESE | Bakery > Pastry > Danishes
- `374089` | MEIJER, KING'S CHOICE, DANISH BLUE CHEESE | Bakery > Pastry > Danishes

---

## 8. Small PI groups (<30 SKUs) split across multiple paths (285 rows)

One-home-per-PI test uses a 30-SKU dominance threshold; these smaller groups slip through and get split.

**Samples (fdc_id, details):**

- `Canned Vegetables` | 15 | 2
- `Lupin Beans` | 2 | 2
- `Pizza Crust` | 17 | 2
- `Blinis` | 4 | 3
- `Mix` | 10 | 2
- `Rice Bowl` | 14 | 2
- `Bananas` | 15 | 2
- `Banana Powder` | 3 | 2
- `Mushroom Powder` | 8 | 4
- `Bean Soup Mix` | 4 | 2

---

## 9. Plant/Vegan BFC but animal-derived path (279 rows)

BFC indicates plant/vegan/vegetarian but canonical path routes into meat, beef, chicken, or seafood.

**Samples (fdc_id, details):**

- `1983820` | Vegetarian Frozen Meats | Meat & Seafood > Beef > Ground Beef
- `2020583` | Vegetarian Frozen Meats | Meat & Seafood > Meat Alternatives > Meat Crumbles
- `2136619` | Vegetarian Frozen Meats | Meat & Seafood > Deli Slices
- `2599590` | Vegetarian Frozen Meats | Meat & Seafood > Beef > Ground Beef
- `1951257` | Vegetarian Frozen Meats | Meat & Seafood > Meatballs
- `2414179` | Vegetarian Frozen Meats | Meat & Seafood > Meat Alternatives > Meatless Crumbles
- `2606619` | Vegetarian Frozen Meats | Meat & Seafood > Meatballs
- `1869600` | Vegetarian Frozen Meats | Meat & Seafood > Meatballs
- `2663759` | Vegetarian Frozen Meats | Meat & Seafood > Shellfish > Crab
- `2425643` | Vegetarian Frozen Meats | Meat & Seafood > Shellfish > Crab

---

## 10. FNDDS code present but description empty (23 rows)

Referential integrity gap: FNDDS code exists but the description field is blank.

**Samples (fdc_id, details):**

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

## 11. Cheeseburger in title but absent from path (21 rows)

Title explicitly names cheeseburger but canonical path contains no Burger, Sandwich, or Entree signal.

**Samples (fdc_id, details):**

- `1930426` | CHEESEBURGERS | Frozen > Single Entrees
- `2127323` | MINI CHEESEBURGERS FLAME BROILED BEEF STEAKS WITH AMERICAN CHEESE ON HEARTH BAKED BUNS SANDWICHES, MINI CHEESEBURGERS | Frozen > Appetizers
- `2019176` | SAM'S CHOICE, MINI ANGUS BEEF & BACON CHEESEBURGERS | Frozen > Appetizers
- `2127319` | FLAME-BROILED CHEESEBURGERS BEEF PATTY WITH CHEESE ON A BUN SANDWICHES, BEEF | Meal > Sandwiches > Sandwich
- `2064746` | SLIDERS MINI CHEESEBURGERS | Frozen > Single Entrees > Slider Sandwich
- `2677873` | CHEESE SLIDERS CHEESEBURGERS, CHEESE | Frozen > Appetizers > Sliders
- `1509861` | CHEESE SLIDERS CHEESEBURGERS, CHEESE | Frozen > Appetizers > Sliders
- `2114670` | CHEESE SLIDERS CHEESEBURGERS, CHEESE | Frozen > Appetizers > Sliders
- `1902823` | CHEESE SLIDERS CHEESEBURGERS, CHEESE | Frozen > Appetizers > Sliders
- `2067030` | JALAPENO CHEESE SLIDERS JALAPENO CHEESEBURGERS, JALAPENO CHEESE | Frozen > Appetizers > Sliders

---

## 12. Same produce title routed to non-Produce family (1 rows)

Basic produce titles (APPLES, BANANAS, ORANGES) appear in both Produce and Beverage/Pantry families.

**Samples (fdc_id, details):**

- `APPLES` | 19 | {'Beverage', 'Produce'}

---

## 13. Hot dog in title but not in Meat/Sausage path (151 rows)

Title is a hot dog product (excluding buns/beans) but path lacks Meat, Sausage, or Hotdog segment.

**Samples (fdc_id, details):**

- `2284732` | 100% WHOLE WHEAT HOT DOG ROLLS, WHOLE WHEAT | Meal > Sandwiches > Hot Dog
- `1895494` | 100% NATURAL WHEAT HOT DOG ROLL | Meal > Sandwiches > Hot Dog
- `2052010` | WHOLE FOODS MARKET, POTATO HOT DOG | Meal > Sandwiches > Hot Dog
- `2100184` | POTATO HOT DOG | Meal > Sandwiches > Hot Dog
- `2488892` | HOT DOG, POTATO | Meal > Sandwiches > Hot Dog
- `2615144` | ENRICHED HOT DOG ROLLS | Meal > Sandwiches > Hot Dog
- `1892283` | HOT DOG ROLLS | Meal > Sandwiches > Hot Dog
- `2316804` | ORGANIC WHEAT HOT DOG ROLLS, WHEAT | Meal > Sandwiches > Hot Dog
- `2497666` | HOT DOG ROLLS | Meal > Sandwiches > Hot Dog
- `2487210` | HOT DOG ENRICHED ROLLS | Meal > Sandwiches > Hot Dog

---

## 14. Frozen path but title starts with Fresh (19 rows)

Product title starts with Fresh but path routes to Frozen. Processing-state contradiction.

**Samples (fdc_id, details):**

- `356545` | FRESH & EASY, BUTTERMILK PANCAKES | Frozen > Pancakes > Buttermilk
- `356544` | FRESH & EASY, HOMESTYLE WAFFLES | Frozen > Waffles > Plain
- `1832515` | FRESH FRUIT NANCE, FRUIT | Frozen > Ice Cream > Cherry > No Sugar Added > Reduced Fat
- `2546835` | FRESH MINT CHIP PLANT-BASED GELATO, FRESH MINT CHIP | Frozen > Gelato > Mint Chip > Plant Based
- `2472613` | FRESH MINT CHOCOLATE CHIP GELATO, FRESH MINT CHOCOLATE CHIP | Frozen > Gelato > Mint Chip Fresh Chocolate Chip
- `1902432` | FRESH MINT LEAF ICE CREAM WITH BROWN SUGAR & DARK CHOCOLATE CHIPS, DIRTY MINT CHIP | Frozen > Ice Cream > Dark Chocolate Chip Mint Brown Sugar
- `1970204` | FRESH MINT LEAF, BROWN SUGAR & DARK CHOCOLATE CHIP FROZEN DESSERT WITH DOUBLE CHOCOLATE COOKIES SANDWICH, DIRTY MINT CHIP | Frozen > Ice Cream > Mint Chocolate Chip Chocolate
- `2373832` | FRESH MINT WITH CHOCOLATE PIECES GELATO, FRESH MINT WITH CHOCOLATE | Frozen > Gelato > Mint Chocolate
- `2008322` | FRESH FOODS MARKET, ICE CREAM CAKE WITH BROKEN COOKIE PIECES | Frozen > Ice Cream > Cookie Vanilla
- `2152116` | FRESH MINT CHIP WITH DARK CHOCOLATE COOKIE PLANT-BASED COOKIE SANDWICH, FRESH MINT CHIP | Frozen > Ice Cream > Mint Chip Chocolate > Plant Based

---

## 15. SR28 code present but description empty (0 rows)

SR28 code exists but description field is blank.

**Samples (fdc_id, details):**


---

## 16. ESHA code present but description empty (0 rows)

ESHA code exists but description field is blank.

**Samples (fdc_id, details):**


---

## 17. Modifier=Plain but title contains clear flavor (1,901 rows)

Modifier column says Plain but title includes Chocolate, Vanilla, Strawberry, etc.

**Samples (fdc_id, details):**

- `2629846` | FROSTED CINNAMON ROLL BITE-SIZE FILLED BAKING FRUFFLES, FROSTED CINNAMON ROLL | Plain
- `2382580` | CINNAMON ROLL BARS, CINNAMON ROLL | Plain
- `2381420` | CINNAMON ROLL BARS, CINNAMON ROLL | Plain
- `2387541` | CINNAMON ROLL BAR, CINNAMON ROLL | Plain
- `1837866` | CINNAMON ROLL BARS, CINNAMON | Plain
- `1837845` | NUTRITION BAR, CINNAMON ROLL | Plain
- `2077623` | LANCE, QUICK START BREAKFAST BISCUIT SANDWICHES, CINNAMON ROLL, CINNAMON ROLL | Plain
- `1939993` | GARLIC BREAD, CLASSIC | Plain
- `2691390` | Pepperidge Farm Bakery Specialty Breads Traditional Garlic Bread, 10 Ounces, Pack of 12 | Plain
- `2464779` | BANANA CHOCOLATE LOAF, BANANA CHOCOLATE | Plain

---


# Summary

This audit discovered **17 distinct bug classes** affecting **38,919 rows** in the 462,711-SKU corpus. Key themes include: (1) referential integrity gaps (duplicate fdc_ids, empty code descriptions), (2) path/title contradictions (Canned vs Frozen, plant-based products in Dairy, cheese in Bakery), (3) structural path issues (empty leaf paths, redundant words, missing claim segments), and (4) taxonomy consistency failures below the existing 30-SKU one-home-per-PI threshold. These classes are not covered by the current 295 pytest invariants and represent actionable cleanup targets.
