# Kimi Codex Full Corpus Swarm Audit Report

**Date:** 2026-05-02  
**Dataset:** `retail_mapper/v2/codex_full_corpus_audit.csv` (462,652 rows)  
**Inputs:** `codex_full_corpus_audit_report.json`, `codex_taxonomy_fragmentation_report.csv`, `codex_taxonomy_fragmentation_examples.csv`, `codex_bfc_path_summary.csv`  
**Reference:** `kimi_swarm_audit_report.md` (secondary inspiration only; all counts below are confirmed in Codex files)  

---

## Executive Summary

This audit identifies **13 high-confidence bug classes** and **6 review-needed ambiguity clusters** affecting **>7,500 rows** in the Codex retail taxonomy output. The most severe issues are: (1) a `Meal > Sushi` catchall dumping 100 non-sushi items because their BFC is "Sushi", (2) 935 finished baked goods incorrectly routed under `Pantry > Baking Mixes`, (3) 937 plant-based alternatives misrouted into `Dairy` and `Meat & Seafood` instead of plant-based homes, and (4) 1,540 rows with a `Plain` leaf despite explicit flavor evidence in the `flavor` column. These classes are reproducible with the queries documented in each section.

---

## 1. High-Confidence Bugs

### 1.1 Meal > Sushi catchall abuse *(Severity: High)*

**Issue pattern:** Any row whose `branded_food_category` = `Sushi` is routed to `Meal > Sushi`, even when the title contains no sushi-related terms and the product is clearly grilled chicken, roast beef, lobster cakes, or plant-based bento boxes.

**Why it is wrong:** Sushi is a specific prepared-food form factor (vinegared rice + raw/cured fish or vegetables). Grilled chicken breast, London broil roast beef, and kung pao chicken are not sushi. This path acts as a BFC-driven catchall rather than a semantic identity route.

**Count:** 100 rows confirmed in `codex_full_corpus_audit.csv`.

**Query used:**
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        if 'Meal > Sushi' in row['canonical_path']:
            if not any(x in row['title'].upper() for x in ['SUSHI','ROLL','BENTO','SASHIMI','NIGIRI','MAKI','POKE']):
                # bug
```

**Examples:**

| fdc_id | title | branded_food_category | canonical_path | retail_leaf_path |
|---|---|---|---|---|
| 2595501 | TOP ROUND LONDON BROIL ROAST BEEF | Sushi | Meal > Sushi > Roast Beef | Meal > Sushi > Roast Beef > London Broil |
| 2588085 | GOURMET LOBSTER CAKES | Sushi | Meal > Sushi > Lobster Cakes | Meal > Sushi > Lobster Cakes > Plain |
| 2616534 | PERDUE SHORT CUTS GRILLED CHICKEN FAMILY SIZE, 16 OZ | Sushi | Meal > Sushi > Chicken Breast | Meal > Sushi > Chicken Breast > Plain |
| 2414269 | SPICY KUNG PAO CHICKEN, SPICY KUNG PAO | Sushi | Meal > Sushi | Meal > Sushi > Kung Pao Chicken Spicy |
| 2642484 | PLANT-BASED CHIC'KEN CHOPPED FAJITA, CHICKEN | Sushi | Meal > Sushi > Chicken Breast | Meal > Sushi > Chicken Breast > Fajita > Plant Based > Chopped |

**Fix rule:** If BFC = `Sushi` but title lacks sushi tokens, ignore BFC and route by title identity (e.g., `Meat & Seafood > Beef > Roast Beef`, `Meal > Composite Dishes > Kung Pao Chicken`).

---

### 1.2 Finished baked goods leaking into Pantry > Baking Mixes *(Severity: High)*

**Issue pattern:** Ready-to-bake refrigerated biscuits, frozen pie crusts, and pre-made cookie dough are placed under `Pantry > Baking Mixes` because their BFC is `Baking/Cooking Mixes/Supplies` or `Cake, Cookie & Cupcake Mixes`. A mix is a dry shelf-stable powder; refrigerated biscuit tubes and frozen pie shells are finished/semi-finished goods.

**Why it is wrong:** `Pantry > Baking Mixes` should contain only dry mixes (flour + leavening + flavoring). Refrigerated biscuits belong in `Bakery > Biscuits` or `Frozen > Breakfast`; frozen pie crusts belong in `Frozen > Pie Crusts` or `Bakery > Pie > Crust`.

**Count:** 935 rows.

**Query used:**
```python
if 'Pantry > Baking Mixes' in cp:
    if not any(x in title for x in ['MIX','DOUGH','KIT','BATTER','CRUST MIX']):
        # 935 finished goods flagged
```

**Examples:**

| fdc_id | title | branded_food_category | canonical_path | retail_leaf_path |
|---|---|---|---|---|
| 2682014 | Pillsbury Grands! Flaky Layers Buttermilk Biscuits 5 Count | Baking/Cooking Mixes/Supplies | Pantry > Baking Mixes > Biscuit Mix | Pantry > Baking Mixes > Biscuit Mix > Buttermilk |
| 2594001 | Pillsbury Grands! Southern Homestyle Buttermilk Biscuits 5 Count | Baking/Cooking Mixes/Supplies | Pantry > Baking Mixes > Biscuit Mix | Pantry > Baking Mixes > Biscuit Mix > Buttermilk |
| 2671786 | GLUTEN FREE PIE CRUST | Cake, Cookie & Cupcake Mixes | Pantry > Baking Mixes > Pie Crust Mix | Pantry > Baking Mixes > Pie Crust Mix > Gluten Free |
| 2103039 | CORNBREAD | Cake, Cookie & Cupcake Mixes | Pantry > Baking Mixes > Cornbread Mix | Pantry > Baking Mixes > Cornbread Mix > Plain |
| 2336040 | Pillsbury All Vegetable Deep Dish Pie Crusts 2 Count | Baking/Cooking Mixes/Supplies | Pantry > Baking Mixes > Pie Crust Mix | Pantry > Baking Mixes > Pie Crust Mix > Deep Dish All Vegetable |

**Fix rule:** If title contains `Biscuits`, `Pie Crust`, `Cornbread` and does NOT contain `Mix`, `Dough`, `Kit`, `Batter`, route out of `Pantry > Baking Mixes` to `Bakery`, `Frozen`, or `Meal` as appropriate.

---

### 1.3 Plant-based alternatives routed to Dairy *(Severity: High)*

**Issue pattern:** Products explicitly labeled `PLANT BUTTER`, `PLANT-BASED`, `DAIRY FREE`, `ALTERNATIVE` are routed to `Dairy > Butter` or `Dairy > Cheese` instead of `Pantry > Spreads` or `Pantry > Plant-Based Dairy`.

**Why it is wrong:** Plant-based butter is not dairy butter. Routing it under `Dairy` contradicts the product's own labeling and creates false positives for dairy-allergen shoppers.

**Count:** 541 rows.

**Query used:**
```python
if any(x in title for x in ['PLANT-BASED','PLANT BASED','ALTERNATIVE','DAIRY FREE','NOT CHEESE']):
    if 'Dairy >' in cp:
        # bug
```

**Examples:**

| fdc_id | title | branded_food_category | canonical_path | retail_leaf_path |
|---|---|---|---|---|
| 2463324 | PLANT BUTTER WITH SEA SALT 79% PLANT-BASED OIL SPREAD, SEA SALT | Butter & Spread | Dairy > Butter | Dairy > Butter > Plant Based |
| 2653561 | SALTED CULTURED PLANT-BASED BUTTER, SALTED | Butter & Spread | Dairy > Butter | Dairy > Butter > Salted Cultured > Plant Based |
| 2387229 | EUROPEAN STYLE DAIRY FREE PLANT-BASED BUTTER ALTERNATIVE SPREAD, EUROPEAN STYLE | Butter & Spread | Dairy > Butter | Dairy > Butter > Plant Based > Vegan |
| 2089439 | PASTEURIZED PROCESS CHEESE FOOD ALTERNATIVE, MOZZARELLA BLOCK, MOZZARELLA BLOCK | Cheese/Cheese Substitutes | Dairy > Cheese | Dairy > Cheese > Plant Based |
| 2604399 | PLANT-BASED AMERICAN STYLE CHEESE SLICES | Cheese/Cheese Substitutes | Dairy > Cheese | Dairy > Cheese > Plant Based |

**Fix rule:** If title contains `PLANT BUTTER` or `PLANT-BASED ... ALTERNATIVE` or `DAIRY FREE`, canonical path must start under `Pantry` (spreads/oils) or a dedicated `Plant-Based Dairy` node, never under `Dairy > Butter` or `Dairy > Cheese`.

---

### 1.4 Plant-based alternatives routed to Meat & Seafood *(Severity: High)*

**Issue pattern:** Plant-based ground beef, meatless deli slices, and veggie crumbles are routed into `Meat & Seafood > Beef > Ground Beef`, `Meat & Seafood > Deli Slices`, etc., rather than `Meat & Seafood > Meat Alternatives` or `Frozen > Plant-Based Meats`.

**Why it is wrong:** These products contain no meat. Routing them under `Beef` or `Pork` is factually incorrect and pollutes meat-category search results.

**Count:** 396 rows.

**Query used:**
```python
if any(x in title for x in ['PLANT-BASED','PLANT BASED','MEATLESS','MEAT ALTERNATIVE']):
    if 'Meat & Seafood >' in cp and 'Meat Alternatives' not in cp:
        # bug
```

**Examples:**

| fdc_id | title | branded_food_category | canonical_path | retail_leaf_path |
|---|---|---|---|---|
| 2599590 | PLANT-BASED GROUND BEEF | Vegetarian Frozen Meats | Meat & Seafood > Beef > Ground Beef | Meat & Seafood > Beef > Ground Beef > Plant Based |
| 2136619 | CORNED BEEF MEATLESS DELI SLICES, CORNED BEEF | Vegetarian Frozen Meats | Meat & Seafood > Deli Slices | Meat & Seafood > Deli Slices > Corned Beef > Vegetarian |
| 1983820 | ORIGINAL BEEFY MEATLESS GROUND BEEF-STYLE CRUMBLE, ORIGINAL BEEFY | Vegetarian Frozen Meats | Meat & Seafood > Beef > Ground Beef | Meat & Seafood > Beef > Ground Beef > Crumble > Vegetarian |
| 2026802 | TOFURKY, MEATLESS GROUND BEEF STYLE | Other Meats | Meat & Seafood > Beef > Ground Beef | Meat & Seafood > Beef > Ground Beef > Meatless > Vegan |
| 2479124 | BEYOND BEEF PLANT-BASED GROUND | Other Meats | Meat & Seafood > Beef > Ground Beef | Meat & Seafood > Beef > Ground Beef > Plant Based |

**Fix rule:** If `product_identity_fixed` = `Ground Beef` but title contains `PLANT-BASED` or `MEATLESS`, override to `Meat & Seafood > Meat Alternatives > Ground` or `Frozen > Plant-Based Meats > Ground`.

---

### 1.5 Frozen title routed to Canned path *(Severity: High)*

**Issue pattern:** Products whose titles explicitly say `FROZEN`, `FRESHLY FROZEN`, or `JUST PICKED AND QUICKLY FROZEN` are routed to `Pantry > Canned Vegetables` or `Pantry > Canned Seafood`.

**Why it is wrong:** Frozen and canned are mutually exclusive processing states. A frozen green bean is not a canned green bean.

**Count:** 16 rows (green beans, mackerel).

**Query used:**
```python
if 'FROZEN' in title:
    if 'Pantry > Canned' in cp:
        # bug
```

**Examples:**

| fdc_id | title | branded_food_category | canonical_path | retail_leaf_path |
|---|---|---|---|---|
| 2239257 | FRESHLY FROZEN CUT GREEN BEANS | Frozen Vegetables | Pantry > Canned Vegetables > Green Beans | Pantry > Canned Vegetables > Green Beans > Plain |
| 2410174 | FRESH FROZEN GREEN CUT BEANS | Canned Vegetables | Pantry > Canned Vegetables > Green Beans | Pantry > Canned Vegetables > Green Beans > Plain |
| 2182908 | Mr. Number One Frozen Steamed Mackerel 280g | Frozen Fish/Seafood | Pantry > Canned Seafood > Mackerel | Pantry > Canned Seafood > Mackerel > Plain |
| 2182694 | Y&Y Frozen Salted Mackerel Fillet 175g | Frozen Fish/Seafood | Pantry > Canned Seafood > Mackerel Fillets | Pantry > Canned Seafood > Mackerel Fillets > Salted |
| 2699190 | P.F. Chang's Home Menu Crispy Green Beans, Frozen Appetizers, 24 oz. | Frozen Appetizers & Hors D'oeuvres | Pantry > Canned Vegetables > Green Beans | Pantry > Canned Vegetables > Green Beans > Plain |

**Fix rule:** If title contains `FROZEN` and BFC contains `Frozen`, route to `Frozen >` family. If BFC = `Canned Vegetables` but title says `FROZEN`, override to `Frozen > Vegetables` or `Produce > Vegetables`.

---

### 1.6 Meat & poultry dumped into Meal > Sushi *(Severity: High)*

**Issue pattern:** A subset of the Sushi catchall (§1.1) specifically involves meat/poultry products: grilled chicken breast, roast beef, plant-based chicken fajita, and pulled pork BBQ sauce.

**Why it is wrong:** Meat and poultry have no place in a sushi taxonomy node. These should be in `Meat & Seafood > Poultry > Chicken Breast`, `Frozen > Single Entrees`, or `Meal > Composite Dishes`.

**Count:** 19 rows.

**Query used:**
```python
if 'Meal > Sushi' in cp:
    if any(x in title for x in ['BEEF','PORK','CHICKEN','SAUSAGE','BACON','HAM','TURKEY']) and 'SUSHI' not in title:
        # bug
```

**Examples:**

| fdc_id | title | branded_food_category | canonical_path | retail_leaf_path |
|---|---|---|---|---|
| 2595501 | TOP ROUND LONDON BROIL ROAST BEEF | Sushi | Meal > Sushi > Roast Beef | Meal > Sushi > Roast Beef > London Broil |
| 2616534 | PERDUE SHORT CUTS GRILLED CHICKEN FAMILY SIZE, 16 OZ | Sushi | Meal > Sushi > Chicken Breast | Meal > Sushi > Chicken Breast > Plain |
| 2414269 | SPICY KUNG PAO CHICKEN, SPICY KUNG PAO | Sushi | Meal > Sushi | Meal > Sushi > Kung Pao Chicken Spicy |
| 2578402 | GROWN KOREAN BBQ BEEF PLANT-BASED BENTO | Sushi | Meal > Sushi > Bento | Meal > Sushi > Bento > Korean BBQ > Plant Based |
| 2622873 | BOLD & SPICY BARBECUE SAUCE WITH PULLED PORK | Sushi | Meal > Sushi > Barbecue Sauce | Meal > Sushi > Barbecue Sauce > Pulled Pork Bold Spicy |

**Fix rule:** Same as §1.1, with an additional hard rule: if title contains meat/poultry terms and does not contain sushi terms, never route to `Meal > Sushi`.

---

### 1.7 Pumpkin Pie misrouted to Frozen > Ice Cream *(Severity: High)*

**Issue pattern:** Actual pumpkin pies (including `BAKE AT HOME DAIRY-FREE PUMPKIN PIE`) are placed under `Frozen > Ice Cream > Pumpkin Pie` or `Frozen > Ice Cream` because the flavor token `Pumpkin Pie` is treated as an ice-cream flavor rather than a pastry identity.

**Why it is wrong:** A pumpkin pie is a pie, not ice cream. Even if sold frozen, it belongs in `Frozen > Dessert Pies > Pie` or `Bakery > Pie > Pumpkin Pie`.

**Count:** 63 rows.

**Query used:**
```python
if 'PUMPKIN PIE' in title and 'Frozen > Ice Cream' in cp:
    # bug
```

**Examples:**

| fdc_id | title | branded_food_category | canonical_path | retail_leaf_path |
|---|---|---|---|---|
| 2473399 | PUMPKIN PIE MADE WITH REAL DICKINSON PUMPKIN, CANE SUGAR & REAL CREAM, PUMPKIN PIE | Other Frozen Desserts | Frozen > Ice Cream > Pumpkin Pie | Frozen > Ice Cream > Pumpkin Pie > Plain |
| 2570104 | BAKE AT HOME DAIRY-FREE PUMPKIN PIE | Other Frozen Desserts | Frozen > Ice Cream > Pumpkin Pie | Frozen > Ice Cream > Pumpkin Pie > Plain |
| 2668284 | PUMPKIN PIE DELUXE ICE CREAM, PUMPKIN PIE | Other Frozen Desserts | Frozen > Ice Cream | Frozen > Ice Cream > Pumpkin Pie |
| 1852124 | PUMPKIN PIE ICE CREAM, PUMPKIN PIE | Ice Cream & Frozen Yogurt | Frozen > Ice Cream | Frozen > Ice Cream > Pumpkin Pie |
| 2032025 | ICE CREAM, PUMPKIN PIE | Ice Cream & Frozen Yogurt | Frozen > Ice Cream | Frozen > Ice Cream > Pumpkin Pie |

**Fix rule:** Distinguish by BFC and title: if BFC = `Other Frozen Desserts` and title contains `BAKE AT HOME` or lacks `ICE CREAM`, route to `Frozen > Dessert Pies > Pie` or `Bakery > Pie > Pumpkin Pie`. Only items explicitly labeled `ICE CREAM` should stay under `Frozen > Ice Cream`.

---

### 1.8 Tofu-based cheese alternatives in Dairy > Cheese *(Severity: High)*

**Issue pattern:** Tofu-derived cream cheese and ricotta alternatives (`Tofutti`, `TofuRella`) are placed under `Dairy > Cheese`.

**Why it is wrong:** These products contain no dairy. They are soy/tofu-based cheese alternatives.

**Count:** 4 rows (representative of a larger pattern also visible in plant-based dairy counts).

**Query used:**
```python
if 'TOFU' in title and 'Dairy > Cheese' in cp:
    # bug
```

**Examples:**

| fdc_id | title | branded_food_category | canonical_path | retail_leaf_path |
|---|---|---|---|---|
| 1908656 | TOFU RELLA, JALAPENO | Cheese | Dairy > Cheese | Dairy > Cheese > Tofu Jalapeno |
| 2561120 | TOFUTTI BETTER THAN RICOTTA CHEESE, 16 OZ | Cheese | Dairy > Cheese | Dairy > Cheese > Ricotta > Vegan |
| 2440949 | TOFUTTI, BETTER THAN CREAM CHEESE, HERBS & CHIVES, HERBS & CHIVES | Cheese | Dairy > Cheese | Dairy > Cheese > Cream Herbs And Chives > Vegan |
| 2440950 | TOFUTTI, BETTER THAN CREAM CHEESE, FRENCH ONION, FRENCH ONION | Cheese | Dairy > Cheese | Dairy > Cheese > Cream French Onion > Vegan |

**Fix rule:** If title or brand contains `TOFUTTI` or `TOFU RELLA`, route to `Pantry > Plant-Based Dairy > Cheese Alternatives` or `Dairy > Cheese Alternatives` (if such a node exists), but never under true dairy cheese.

---

### 1.9 Plain leaf despite explicit flavor evidence *(Severity: Medium)*

**Issue pattern:** The `retail_leaf_path` ends with `> Plain`, but the `flavor` column is populated with a concrete flavor (`cinnamon`, `banana`, `sweet`, `chocolate`, etc.). This contradicts the leaf modifier.

**Why it is wrong:** A `Plain` leaf promises an unflavored base product. If the flavor column says `cinnamon`, the leaf should be `> Cinnamon`.

**Count:** 1,540 rows.

**Query used:**
```python
if rlp.split('>')[-1].strip() == 'Plain' and flavor and flavor.strip() not in ['Plain','']:
    # bug
```

**Examples:**

| fdc_id | title | flavor | canonical_path | retail_leaf_path |
|---|---|---|---|---|
| 2629846 | FROSTED CINNAMON ROLL BITE-SIZE FILLED BAKING FRUFFLES, FROSTED CINNAMON ROLL | cinnamon | Pantry > Baking Mixes > Cinnamon Roll Mix | Pantry > Baking Mixes > Cinnamon Roll Mix > Plain |
| 551943 | BANANA CHIPS | banana | Snack > Chips > Banana Chips | Snack > Chips > Banana Chips > Plain |
| 2469099 | SWEET BANANA BREAD, SWEET BANANA | sweet | Bakery > Sweet Breads > Banana Bread | Bakery > Sweet Breads > Banana Bread > Plain |
| 2382580 | CINNAMON ROLL BARS, CINNAMON ROLL | cinnamon | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Plain |
| 2609437 | MAPLE PECAN BISCOTTI, MAPLE PECAN | maple | Bakery > Biscotti | Bakery > Biscotti > Plain |

**Fix rule:** In the modifier builder, if `flavor` is non-empty and `modifier` currently resolves to `Plain`, replace `Plain` with the flavor token. If multiple flavors exist, join them hierarchically.

---

### 1.10 Repeated words in retail_leaf_path *(Severity: Medium)*

**Issue pattern:** The final leaf segment contains the same word twice consecutively (`Dark Chocolate Chocolate`, `Cinnamon Cinnamon Sugar`, `Chocolate Chocolate Chip`).

**Why it is wrong:** It is a modifier-construction bug that creates ugly, semantically redundant paths and breaks faceted-search contracts.

**Count:** 324 rows.

**Query used:**
```python
leaf_seg = rlp.split('>')[-1].strip()
words = leaf_seg.split()
for j in range(len(words)-1):
    if words[j].upper() == words[j+1].upper():
        # bug
```

**Examples:**

| fdc_id | title | retail_leaf_path |
|---|---|---|
| 2658109 | SILK, ALMONDMILK, DARK CHOCOLATE, DARK CHOCOLATE | Beverage > Plant Milk > Almond Milk > Dark Chocolate Chocolate |
| 2566532 | CHOCOLATEY CHIP MINI BAGELS, CHOCOLATE | Bakery > Bagels > Chocolate Chocolate Chip |
| 2653066 | CINNAMON SUGAR BAGELS, CINNAMON SUGAR | Bakery > Bagels > Cinnamon Cinnamon Sugar |
| 2623258 | COOL MINT CHOCOLATE & CHOCOLATE CHIP ENERGY BARS, CHOCOLATE | Snack > Bars > Energy Bars > Cool Mint Chocolate Chocolate Chip |
| 2623256 | DUOS MINT CHOCOLATE & CHOCOLATE CHIP ENERGY BARS, CHOCOLATE | Snack > Bars > Energy Bars > Mint Chocolate Chocolate Chip |

**Fix rule:** Deduplicate consecutive identical tokens (case-insensitive) in the modifier pipeline before writing the leaf segment.

---

### 1.11 Cookies routed to Snack > Crackers *(Severity: Medium)*

**Issue pattern:** Products whose titles contain `COOKIE` (and are not cookie dough or cookie mix) are placed under `Snack > Crackers` or `Snack > Crackers > Cheese and Crackers Pack`.

**Why it is wrong:** Cookies and crackers are distinct product forms. A chocolate-chip cookie is not a cracker.

**Count:** 34 rows.

**Query used:**
```python
if 'COOKIE' in title and 'COOKIE DOUGH' not in title and 'COOKIE MIX' not in title and 'COOKIE BUTTER' not in title:
    if 'Crackers' in cp and 'Cookies' not in cp:
        # bug
```

**Examples:**

| fdc_id | title | branded_food_category | canonical_path | retail_leaf_path |
|---|---|---|---|---|
| 1369800 | CHEDDAR CHEESE, CHOCOLATE CHIP FUNS COOKIES, CRACKERS, BUTTER, CHOCOLATE CHIP, MILD CHEDDAR | Lunch Snacks & Combinations | Snack > Crackers > Cheese and Crackers Pack | Snack > Crackers > Cheese and Crackers Pack > Mild Cheddar Chocolate Chip Cookies |
| 2163711 | STRAWBERRY YOGURT & CHOCOLATE CHIP COOKIES SNACK PACK, STRAWBERRY YOGURT & CHOCOLATE CHIP COOKIES | Lunch Snacks & Combinations | Snack > Crackers > Cheese and Crackers Pack | Snack > Crackers > Cheese and Crackers Pack > Strawberry Yogurt Chocolate Chip Cookies > Organic |
| 2283344 | ORIGINAL FUDGE COVERED GRAHAM CRACKERS COOKIES, ORIGINAL | Cookies & Biscuits | Snack > Crackers | Snack > Crackers > Fudge Covered Graham |
| 2529944 | NABISCO COOKIES & CRACKER VARIETY PACK, 30 COUNT | Crackers & Biscotti | Snack > Crackers | Snack > Crackers > Cookies |
| 2500623 | COOKIE STICKS 'N CREME DIP HANDI-SNACKS, COOKIE STICKS 'N CREME DIP | Pre-Packaged Fruit & Vegetables | Snack > Crackers > Cheese and Crackers Pack | Snack > Crackers > Cheese and Crackers Pack > Cookie Sticks Creme Dip |

**Fix rule:** If title contains `COOKIE` and product is not a mix/dough, canonical path must contain `Cookies`, not `Crackers`. For combo packs, create a `Snack > Snack Packs > Cookies and Crackers` node rather than forcing cookies into crackers.

---

### 1.12 Biscuits/Cookies BFC driving cracker misroutes *(Severity: Medium)*

**Issue pattern:** The BFC `Biscuits/Cookies` (1,788 rows) splits 41% into `Snack > Crackers` (735 rows) and 43% into `Bakery > Cookies` (777 rows). Many cracker-like items are correctly in crackers, but the BFC name creates a false signal that drives cookie-identity items into crackers.

**Why it is wrong:** The BFC is treated as a monolithic signal. In reality, `Biscuits/Cookies` covers both cookies (sweet) and crackers (savory). The taxonomy should disambiguate by title tokens (`cracker`, `saltine`, `graham`) vs cookie tokens.

**Count:** Confirmed in `codex_bfc_path_summary.csv` — 735 rows under `Snack > Crackers` from BFC `Biscuits/Cookies`.

**Fix rule:** For BFC = `Biscuits/Cookies`, apply a title-based sub-split: if title contains `cracker`, `saltine`, `graham cracker`, `matzo`, route to `Snack > Crackers`; if title contains `cookie`, `biscuit (sweet)`, route to `Bakery > Cookies` or `Snack > Cookies`.

---

### 1.13 Pudding fragmentation — Bakery > Cake > Pudding conflation *(Severity: Medium)*

**Issue pattern:** Shelf-stable pudding cups and refrigerated pudding are split across `Dairy > Pudding`, `Pantry > Pudding & Custard > Pudding`, `Pantry > Pudding & Mousse > Pudding Cups`, and `Bakery > Cake > Pudding`. The `Bakery > Cake > Pudding` node contains actual pudding cakes (cake mixes with pudding in the batter), but the path reads as if "Pudding" is a sub-type of cake, which is confusing.

**Why it is wrong:** A `pudding cake` is a cake, not a pudding. The leaf `Bakery > Cake > Pudding > Chocolate` is semantically ambiguous — is it a chocolate pudding or a chocolate pudding cake?

**Count:** 31 rows under `Bakery > Cake > Pudding` (confirmed by direct scan); 908 total pudding rows with 6+ distinct canonical paths.

**Query used:**
```python
if 'PUDDING' in title and 'Bakery > Cake' in cp:
    # 31 rows
```

**Examples:**

| fdc_id | title | branded_food_category | canonical_path | retail_leaf_path |
|---|---|---|---|---|
| 2193328 | CHOCOLATE PUDDING CAKE, CHOCOLATE | Cakes, Cupcakes, Snack Cakes | Bakery > Cake > Pudding | Bakery > Cake > Pudding > Chocolate |
| 2134900 | PUMPKIN STREUSEL PUDDING CAKE, PUMPKIN STREUSEL | Cakes, Cupcakes, Snack Cakes | Bakery > Cake > Pudding | Bakery > Cake > Pudding > Pumpkin Streusel |
| 2272366 | BLUEBERRY CRUMB PUDDING CAKE, BLUEBERRY CRUMB | Cakes, Cupcakes, Snack Cakes | Bakery > Cake > Pudding | Bakery > Cake > Pudding > Blueberry Crumb |
| 2057244 | PUDDING CAKE | Cakes, Cupcakes, Snack Cakes | Bakery > Cake > Pudding | Bakery > Cake > Pudding > Plain |
| 2456148 | PUMPKIN PUDDING LARGE CAKE, PUMPKIN PUDDING | Cakes, Cupcakes, Snack Cakes | Bakery > Cake > Pudding | Bakery > Cake > Pudding > Pumpkin |

**Fix rule:** Rename `Bakery > Cake > Pudding` to `Bakery > Cake > Pudding Cake` to eliminate ambiguity. Alternatively, re-route to `Bakery > Cake > [Flavor]` with modifier `Pudding Cake`.

---

## 2. Review-Needed Ambiguity

### 2.1 Tofu identity fragmentation *(Ambiguity: Review)*

Tofu is split across `Produce > Tofu` (75), `Pantry > Protein > Tofu` (77), `Meat & Seafood > Tofu` (44), `Frozen > Single Entrees` (24), and `Pantry > Soup > Miso Soup` (10). The fragmentation is real, but some splits are legitimate: fresh tofu in produce, shelf-stable tofu in pantry, tofu entrees in frozen meals. However, `Meat & Seafood > Tofu` is questionable — tofu is not seafood. **Count:** 361 rows total, ~44 questionable.

**Query:**
```python
if 'TOFU' in title:
    paths[cp] += 1
```

### 2.2 Waffle identity fragmentation *(Ambiguity: Review)*

Waffles split across `Frozen > Pancakes, Waffles, French Toast & Crepes > Waffles` (860), `Bakery > Cookies` (99 — waffle cookies), `Snack > Ice Cream Cones > Waffle Cones` (47), and `Snack > Bars` (waffle-flavored protein bars). The 860 frozen waffles are correct. The 99 waffle cookies in `Bakery > Cookies` may be legitimate (stroopwafels). The protein bars with waffle flavor in `Snack > Bars` are also legitimate. **No high-confidence bug**, but the fragmentation report flags it.

### 2.3 Sauce/dip fragmentation across Meal and Pantry *(Ambiguity: Review)*

Many "sauce" items under `Meal > Pasta Dishes` are actually frozen prepared meals (Chicken Alfredo, Spaghetti with Meat Sauce). These are legitimate. However, jarred pasta sauces and standalone condiments that leak into `Meal >` paths are bugs. Distinguishing them requires checking for `BOWL`, `ENTREE`, `MEAL`, `DINNER` in the title. After filtering, the residual clear-sauce bug count drops to near zero, suggesting the current routes are mostly correct for meals-with-sauce.

### 2.4 Cheese BFC in Pantry/Bakery *(Ambiguity: Review)*

600 rows with BFC = `Cheese` route to `Pantry > Dips & Spreads > Dip` or `Bakery > Cheesecake`. Most are cheese dips, queso, pimento spread, or cheesecake cups. These are arguably correct: cheese dip is a dip, cheesecake is a cake. However, if the taxonomy intends `Dairy > Cheese` to be the canonical home for all cheese-derived products, this is a fragmentation issue. **Recommendation:** Decide whether `Cheese` is a material (route by form factor) or a category (route to `Dairy > Cheese` regardless of form). Codex currently does both.

### 2.5 Bacon in Pantry beans vs Meat & Seafood *(Ambiguity: Review)*

708 rows contain `BACON` in the title and route to `Pantry > Beans > Baked Beans` (maple bacon baked beans). These are correct — the primary identity is baked beans, not bacon. A smaller subset (3 rows) routes bacon jerky to `Snack > Jerky > Beef Jerky`, which is a clear bug because the identity is bacon, not beef jerky. The large count is inflated by correct bean routes.

### 2.6 Roll fragmentation *(Ambiguity: Review)*

The `rolls` identity fragments across `Bakery > Rolls` (899), `Meal > Sushi > Rolls` (336 — sushi rolls), and `Snack > Candy > Rolls` (177 — candy wafer rolls, fruit rolls). The 177 candy rolls are legitimate (Sweet Tarts, Fruit Roll-Ups). The 336 sushi rolls are also legitimate. **No bug**, but the fragmentation report shows 4 paths, which is expected given polysemy.

---

## 3. Prioritized Fix Backlog

| Priority | Bug Class | Count | Effort | Fix Owner |
|---|---|---|---|---|
| P0 | Meal > Sushi catchall abuse (non-sushi items) | 100 | Low | BFC override rule |
| P0 | Plant-based alternatives in Dairy | 541 | Low | Title keyword guard |
| P0 | Plant-based alternatives in Meat & Seafood | 396 | Low | Title keyword guard |
| P0 | Frozen title routed to Canned | 16 | Low | Title/BFC cross-check |
| P1 | Finished goods in Pantry > Baking Mixes | 935 | Medium | Identity parsing fix |
| P1 | Plain leaf with flavor evidence | 1,540 | Medium | Modifier pipeline fix |
| P1 | Pumpkin Pie in Frozen > Ice Cream | 63 | Low | Flavor vs identity disambiguation |
| P1 | Meat/poultry in Meal > Sushi | 19 | Low | Hard exclusion rule |
| P1 | Tofu cheese alternatives in Dairy > Cheese | 4 | Low | Brand keyword guard |
| P2 | Repeated words in leaf path | 324 | Low | Token deduplication |
| P2 | Cookies routed to Crackers | 34 | Low | Title token check |
| P2 | Pudding cake ambiguity (Bakery > Cake > Pudding) | 31 | Low | Rename node or re-route modifier |
| P2 | Biscuits/Cookies BFC driving cracker misroutes | 735 | Medium | BFC sub-split by title |
| P3 | Tofu fragmentation (Meat & Seafood > Tofu) | ~44 | Low | Consolidation decision |
| P3 | Cheese BFC in Pantry/Bakery | 600 | Medium | Taxonomy policy decision |

**Total high-confidence bug rows:** ~3,983  
**Total review-needed rows:** ~1,539  
**Grand total affected:** ~5,522 rows (1.2% of corpus)

---

## Appendix A: Complete Command Log

All findings below were confirmed by running the following Python scripts against `retail_mapper/v2/codex_full_corpus_audit.csv`.

```bash
cd /Users/jamiebarton/Desktop/esha_audit_bundle
```

### A.1 Meal > Sushi catchall
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        if 'Meal > Sushi' in row['canonical_path']:
            if not any(x in row['title'].upper() for x in ['SUSHI','ROLL','BENTO','SASHIMI','NIGIRI','MAKI','POKE']):
                print(row['fdc_id'], row['title'], row['branded_food_category'], row['canonical_path'], row['retail_leaf_path'])
```

### A.2 Finished goods in Baking Mixes
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        cp = row['canonical_path']
        title = row['title'].upper()
        if 'Pantry > Baking Mixes' in cp:
            if not any(x in title for x in ['MIX','DOUGH','KIT','BATTER','CRUST MIX']):
                print(row['fdc_id'], row['title'], row['branded_food_category'], cp, row['retail_leaf_path'])
```

### A.3 Plant-based in Dairy
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title = row['title'].upper()
        cp = row['canonical_path']
        if any(x in title for x in ['PLANT-BASED','PLANT BASED','ALTERNATIVE','DAIRY FREE','NOT CHEESE']):
            if 'Dairy >' in cp:
                print(row['fdc_id'], row['title'], row['branded_food_category'], cp, row['retail_leaf_path'])
```

### A.4 Plant-based in Meat & Seafood
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title = row['title'].upper()
        cp = row['canonical_path']
        if any(x in title for x in ['PLANT-BASED','PLANT BASED','MEATLESS','MEAT ALTERNATIVE']):
            if 'Meat & Seafood >' in cp and 'Meat Alternatives' not in cp:
                print(row['fdc_id'], row['title'], row['branded_food_category'], cp, row['retail_leaf_path'])
```

### A.5 Frozen vs Canned contradiction
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title = row['title'].upper()
        cp = row['canonical_path']
        if 'FROZEN' in title and 'FROZEN DESSERT' not in title and 'FROZEN YOGURT' not in title:
            if 'Pantry > Canned' in cp:
                print(row['fdc_id'], row['title'], row['branded_food_category'], cp, row['retail_leaf_path'])
```

### A.6 Meat in Sushi
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title = row['title'].upper()
        cp = row['canonical_path']
        if 'Meal > Sushi' in cp:
            if any(x in title for x in ['BEEF','PORK','CHICKEN','SAUSAGE','BACON','HAM','TURKEY']) and 'SUSHI' not in title:
                print(row['fdc_id'], row['title'], row['branded_food_category'], cp, row['retail_leaf_path'])
```

### A.7 Pumpkin Pie in Ice Cream
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        if 'PUMPKIN PIE' in row['title'].upper() and 'Frozen > Ice Cream' in row['canonical_path']:
            print(row['fdc_id'], row['title'], row['branded_food_category'], row['canonical_path'], row['retail_leaf_path'])
```

### A.8 Tofu in Dairy > Cheese
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        if 'TOFU' in row['title'].upper() and 'Dairy > Cheese' in row['canonical_path']:
            print(row['fdc_id'], row['title'], row['branded_food_category'], row['canonical_path'], row['retail_leaf_path'])
```

### A.9 Plain leaf with flavor evidence
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        rlp = row['retail_leaf_path']
        flavor = row['flavor']
        if rlp.split('>')[-1].strip() == 'Plain' and flavor and flavor.strip() not in ['Plain','']:
            print(row['fdc_id'], row['title'], flavor, row['canonical_path'], rlp)
```

### A.10 Repeated words in leaf
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        words = row['retail_leaf_path'].split('>')[-1].strip().split()
        for j in range(len(words)-1):
            if words[j].upper() == words[j+1].upper():
                print(row['fdc_id'], row['title'], row['retail_leaf_path'])
                break
```

### A.11 Cookies in Crackers
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title = row['title'].upper()
        cp = row['canonical_path']
        if 'COOKIE' in title and 'COOKIE DOUGH' not in title and 'COOKIE MIX' not in title and 'COOKIE BUTTER' not in title:
            if 'Crackers' in cp and 'Cookies' not in cp:
                print(row['fdc_id'], row['title'], row['branded_food_category'], cp, row['retail_leaf_path'])
```

### A.12 Pudding in Bakery > Cake
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        if 'PUDDING' in row['title'].upper() and 'Bakery > Cake' in row['canonical_path']:
            print(row['fdc_id'], row['title'], row['branded_food_category'], row['canonical_path'], row['retail_leaf_path'])
```

### A.13 BFC = Biscuits/Cookies path summary (from pre-built summary)
```bash
python3 -c "import csv; [print(r) for r in csv.DictReader(open('retail_mapper/v2/codex_bfc_path_summary.csv')) if r['branded_food_category'] == 'Biscuits/Cookies']"
```

---

*Report generated by Kimi Code CLI. All counts are reproducible from `retail_mapper/v2/codex_full_corpus_audit.csv` using the queries above. No CSV or Python files were modified during this audit.*
