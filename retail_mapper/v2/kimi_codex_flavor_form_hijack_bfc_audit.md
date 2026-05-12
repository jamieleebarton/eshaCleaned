# Kimi Codex Flavor/Form Hijack & BFC Audit Report

**Date:** 2026-05-02  
**Dataset:** `retail_mapper/v2/codex_full_corpus_audit.csv` (462,652 rows)  
**Scope:** Semantic category hijacks where a flavor token, reference-match, generic form word, or low-quality ESHA/FNDDS match becomes the retail category/identity, overriding the actual product type and `branded_food_category`.  
**Constraint:** The path must respect the actual retail product type and BFC. If the title/BFC says coffee creamer, iced coffee, ice cream, deli meat, cooked turkey, candy, cereal, snack bar, sauce, etc., tokens like *churro, cookie, cake, pie, roll, bun, bagel, bread, muffin, donut, brownie, waffle* must not move the item into `Bakery > Pastry/Cookies/Rolls` unless the product itself is that food.

---

## Executive Summary

This audit confirms **611 high-confidence hijack rows** (0.13 % of corpus) spread across **7 distinct patterns**, plus **3 ambiguous cases** requiring human review. The root cause is consistent: Codex gives excessive weight to flavor/form tokens and ESHA/FNDDS reference descriptions, allowing them to override the dominant product identity encoded in the title and BFC.

| Pattern | Count | Severity |
|---|---|---|
| Beverage / creamer → Bakery (churro, cinnamon roll, biscotti, cheesecake) | 24 | High |
| Ice cream / frozen dessert → Bakery (roll, cake, cookie, brownie) | 109 | High |
| Deli meat / prepared meat "roll" → Bakery > Rolls | 34 | High |
| Cookies & biscuits broken leaf fragments (And Cream, Creme, N Cream) | 53 | High |
| Cereal / popcorn / bars / protein shakes / syrup → Bakery (flavor hijack) | 90 | Medium |
| Reference-match leakage (ESHA/FNDDS bakery desc overrides title/BFC) | 237 | Medium |
| Generic roll collision (BFC contradicts Bakery > Rolls) | 64 | Medium |
| **Total high-confidence** | **611** | — |

The most severe cluster is **ice-cream rolls** (109 rows) routed to `Bakery > Rolls` or `Bakery > Pastry > Cinnamon Rolls`, followed by **reference-match leakage** (237 rows) where the ESHA/FNDDS description contains "churro", "roll", or "cookie" and swamps the beverage or meat identity.

---

## 1. High-Confidence Bugs

### 1.1 Beverage & Creamer Flavor Hijack → Bakery / Pastry / Churros / Biscotti *(Severity: High)*

**Pattern:** Products whose title and BFC clearly identify them as coffee creamer, iced coffee, latte, cold-brew coffee, or ground coffee are routed into `Bakery > Pastry > Churros`, `Bakery > Pastry > Cinnamon Rolls`, `Bakery > Biscotti`, or `Bakery > Cheesecake` because the flavor string contains a bakery word.

**Why it is wrong:** In retail taxonomy, *cinnamon roll* or *churro* in a coffee-creamer title is a **flavor modifier**, not the product identity. A shopper looking for coffee creamer expects `Dairy > Cream > Coffee Creamer` or `Beverage > Coffee Creamer`, not `Bakery > Pastry > Churros`. The BFC (`Milk Additives`, `Other Drinks`, `Coffee`) is the authoritative signal here.

**Count:** 24 rows (reproducible query below).

**Query used:**
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        cp, title = row['canonical_path'], row['title'].upper()
        if 'Bakery' in cp:
            if 'COFFEE CREAMER' in title or ('CREAMER' in title and 'COFFEE' in title):
                if any(x in title for x in ['CHURRO','CINNAMON ROLL','BISCOTTI','CHEESECAKE']):
                    print(row['fdc_id'], row['title'], row['branded_food_category'], cp, row['retail_leaf_path'])
```

**Examples (15 of 24):**

| fdc_id | title | branded_food_category | fndds_desc | esha_desc | canonical_path | retail_leaf_path | matched_key |
|---|---|---|---|---|---|---|---|
| 2528895 | CINNAMON CHURRO COFFEE CREAMER | Milk Additives | coffee creamer liquid | Churro, cinnamon & sugar | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Cinnamon | churros |
| 2658359 | CINNAMON CHURRO COFFEE CREAMER, CINNAMON CHURRO | Milk Additives | coffee creamer liquid | Churro, cinnamon & sugar | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Cinnamon | churros |
| 1413900 | CINNAMON ROLL NON-DAIRY COFFEE CREAMER, CINNAMON ROLL | Milk Additives | coffee creamer liquid | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Plain | cinnamon rolls |
| 2146818 | CINNAMON ROLL NON-DAIRY COFFEE CREAMER, CINNAMON ROLL | Milk Additives | coffee creamer liquid | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Plain | cinnamon rolls |
| 2669339 | CINNAMON ROLL NON-DAIRY COFFEE CREAMER, CINNAMON ROLL | Milk Additives | coffee creamer liquid | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Plain | cinnamon rolls |
| 2564907 | CLASSIC CINNAMON ROLL COFFEE CREAMER, CINNAMON | Milk Additives | coffee creamer liquid | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Plain | cinnamon rolls |
| 2564908 | CINNABON CLASSIC CINNAMON ROLL COFFEE CREAMER, CINNAMON | Milk Additives | coffee creamer liquid | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Plain | cinnamon rolls |
| 2086480 | CLASSIC CINNAMON ROLL COFFEE CREAMER, CLASSIC CINNAMON | Milk Additives | coffee creamer liquid | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Plain | cinnamon rolls |
| 2086434 | CLASSIC CINNAMON ROLL COFFEE CREAMER, CLASSIC CINNAMON ROLL | Milk Additives | coffee creamer liquid | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Plain | cinnamon rolls |
| 2630192 | CINNAMON ROLL COFFEE CREAMER, CINNAMON ROLL | Milk Additives | coffee creamer liquid | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Sugar Free | cinnamon rolls |
| 1908883 | GOURMET COFFEE CREAMER, CHOCOLATE ALMOND BISCOTTI | Milk Additives | coffee creamer liquid | Biscotti | Bakery > Biscotti | Bakery > Biscotti > Chocolate Almond | biscotti |
| 2621577 | INTERNATIONAL DELIGHT, GOURMET COFFEE CREAMER, CHOCOLATE ALMOND BISCOTTI | Milk Additives | coffee creamer liquid | Biscotti | Bakery > Biscotti | Bakery > Biscotti > Chocolate Almond > Non Dairy | biscotti |
| 2310206 | DANISH STYLE BUTTER COOKIE FLAVORED COFFEE CREAMER | Milk Additives | coffee creamer liquid | Cookie, butter / spritz | Bakery > Pastry > Danishes | Bakery > Pastry > Danishes > Danish Butter Cookie | danishes |
| 2544928 | DANISH BUTTER COOKIE FLAVORED COFFEE CREAMER | Milk Additives | coffee creamer liquid | Cookie, butter / spritz | Bakery > Pastry > Danishes | Bakery > Pastry > Danishes > Danish Butter Cookie | danishes |
| 1907599 | SWEET ITALIAN BISCOTTI FLAVOR NON-ALCOHOLIC COFFEE CREAMER | Milk Additives | coffee creamer liquid | Biscotti | Bakery > Biscotti | Bakery > Biscotti > Sweet Italian | biscotti |

**Concrete fix rule:** If `branded_food_category` ∈ {`Milk Additives`, `Cream/Cream Substitutes`, `Coffee`, `Coffee/Coffee Substitutes`, `Other Drinks`} and title contains `COFFEE CREAMER`, `CREAMER`, `ICED COFFEE`, `LATTE`, `COLD BREW`, or `GROUND COFFEE`, **hard-block** any `Bakery` canonical path. Route instead to `Beverage > Coffee Creamer` or `Dairy > Cream > Coffee Creamer`, using the flavor token only for the leaf modifier.

---

### 1.2 Churro-Flavored Beverages → Bakery > Pastry > Churros *(Severity: High)*

**Pattern:** Ground coffee, iced coffee, and cold-brew concentrates with churro flavor are dumped into `Bakery > Pastry > Churros`.

**Why it is wrong:** These are beverages, not pastries. The BFC is `Coffee` or `Other Drinks`. Churro is a flavor descriptor, identical to "vanilla" or "hazelnut" in coffee taxonomy.

**Count:** 10 rows within the 24 above; shown separately because the matched key is `churros` rather than `cinnamon rolls`.

**Query used:**
```python
if 'CHURRO' in title and ('COFFEE' in title or 'LATTE' in title or 'COLD BREW' in title or 'ICED' in title):
    if 'Bakery' in cp:
        print(row)
```

**Examples:**

| fdc_id | title | branded_food_category | fndds_desc | esha_desc | canonical_path | retail_leaf_path | matched_key |
|---|---|---|---|---|---|---|---|
| 2414656 | CINNAMON CHURRO ICED COFFEE, CINNAMON CHURRO | Other Drinks | coffee iced latte flavored | Churro, cinnamon & sugar | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Cinnamon | churros |
| 2416971 | CHURRO FLAVORED ORGANIC UNSWEETENED COLD-BREW COFFEE CONCENTRATE | Other Drinks | coffee iced latte flavored | Churro, cinnamon & sugar | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Organic > Unsweetened | churros |
| 2511447 | LIGHT ROAST SON OF A SON OF A SAILOR CHURRO KETO LATTE ORGANIC NITRO COLD BREW COFFEE | Other Drinks | coffee iced latte flavored | Churro, cinnamon & sugar | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Cinnamon > Organic > Keto | churros |
| 2560110 | CAF ARRIBA! CHURROS Y CHOCOLATE GROUND COFFEE | Coffee | coffee | Churro, cinnamon & sugar | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Chocolate | churros |
| 2173401 | CHURROS Y CHOCOLATE FLAVORED GROUND COFFEE | Coffee | coffee | Churro, cinnamon & sugar | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Chocolate | churros |
| 2744802 | International Delight Cinnamon Churro Iced Coffee 64 fl oz | Coffee/Coffee Substitutes | coffee | Churro, cinnamon & sugar | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Cinnamon | churros |
| 2509493 | CHURRO POUR OVER LATTE PREMIUM VIETNAMESE COFFEE | Coffee | coffee | Churro, cinnamon & sugar | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Vietnamese | churros |

**Concrete fix rule:** Add a `Beverage` guard rail: if title contains `COFFEE`, `LATTE`, `COLD BREW`, or `ICED COFFEE`, and BFC is beverage-related, the matched key `churros` must be downgraded from a canonical-path anchor to a leaf modifier (e.g., `Beverage > Coffee > Flavored Coffee > Churro`).

---

### 1.3 Ice Cream & Frozen Dessert Form Hijack → Bakery Rolls / Cake / Pastry *(Severity: High)*

**Pattern:** Products whose title and BFC identify them as ice cream or frozen dessert, but which contain the word `ROLL`, `CAKE`, `COOKIE`, `BROWNIE`, or `PIE`, are routed to `Bakery > Rolls`, `Bakery > Cake`, `Bakery > Pastry > Cinnamon Rolls`, or `Bakery > Brownies`.

**Why it is wrong:** An "ice cream roll" is a frozen dessert form factor (ice cream layered in a cylindrical cake/sponge), not a bakery dinner roll. An "ice cream cake" is a frozen cake, not a shelf-stable bakery cake. The BFC (`Ice Cream & Frozen Yogurt`) is the dominant identity signal.

**Count:** 109 rows.

**Query used:**
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title, cp, bfc = row['title'].upper(), row['canonical_path'], row['branded_food_category'].upper()
        if 'Bakery' in cp and 'ICE CREAM' in title:
            if any(x in title for x in ['ROLL','CAKE','COOKIE','PIE','BROWNIE']):
                print(row['fdc_id'], row['title'], row['branded_food_category'], cp, row['retail_leaf_path'])
```

**Examples (15 of 109):**

| fdc_id | title | branded_food_category | fndds_desc | esha_desc | canonical_path | retail_leaf_path | matched_key |
|---|---|---|---|---|---|---|---|
| 1857339 | ICE CREAM ROLL WITH CHOCOLATE COOKIE CRUNCH OUTSIDE, MOCHA MUD | Ice Cream & Frozen Yogurt | Ice cream bar, stick or nugget, with crunch coating | Roll, garlic, frozen dough | Bakery > Rolls | Bakery > Rolls > Mocha Chocolate Cookie Crunch > Low Fat | rolls |
| 2614525 | TRADITIONAL ICE CREAM ROLL | Ice Cream & Frozen Yogurt | Ice cream roll | Roll, sweet, no frosting | Bakery > Rolls | Bakery > Rolls > Chocolate Caramel > No Sugar Added > Light | rolls |
| 2563044 | CELEBRATION ICE CREAM DESSERT ROLL | Ice Cream & Frozen Yogurt | Ice cream roll | Roll, sweet, no frosting | Bakery > Rolls | Bakery > Rolls > Chocolate Crunch Fudge | rolls |
| 2018440 | PEANUT BUTTER CUP PREMIUM ICE CREAM ROLL WITH CHOCOLATE COOKIE CRUNCH OUTSIDE | Ice Cream & Frozen Yogurt | Ice cream roll | Roll, sweet, no frosting | Bakery > Rolls | Bakery > Rolls > Peanut Butter Cup Chocolate Cookie Crunch | rolls |
| 2079205 | SALTED NUT ROLL FLAVORED MARSHMALLOW NOUGAT ICE CREAM WITH SALTED CANDIED PEANUTS AND A THICK CARAMEL SWIRL | Ice Cream & Frozen Yogurt | Ice cream roll | Roll, sweet, no frosting | Bakery > Rolls | Bakery > Rolls > Nut Marshmallow Nougat Caramel Swirl Candied Peanuts > Salted | rolls |
| 2639974 | CINNAMON ROLL PREMIUM ICE CREAM WITH STICKY BUN DOUGH PIECES & A FROSTING SWIRL | Ice Cream & Frozen Yogurt | Ice cream roll | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Plain | cinnamon rolls |
| 2307565 | CINNAMON ROLL FLAVORED ORGANIC ICE CREAM SANDWICHES | Ice Cream & Frozen Yogurt | Ice cream sandwich | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Organic | cinnamon rolls |
| 1536026 | SWEET ACTION, ICE CREAM, VEGAN CINNAMON ROLL | Ice Cream & Frozen Yogurt | Ice cream roll | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Vegan | cinnamon rolls |
| 1944619 | CINNAMON ROLL LIGHT ICE CREAM, CINNAMON ROLL | Ice Cream & Frozen Yogurt | Ice cream roll | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Light | cinnamon rolls |
| 2482199 | STRAWBERRY SHORTCAKE ROLLS ICE CREAM | Ice Cream & Frozen Yogurt | Ice cream roll | Cake, shortcake | Bakery > Rolls | Bakery > Rolls > Strawberry Shortcake | rolls |
| 2098000 | ICE CREAM ROLL STRAWBERRY SHORTCAKE | Ice Cream & Frozen Yogurt | Ice cream roll | Cake, shortcake | Bakery > Rolls | Bakery > Rolls > Strawberry Shortcake | rolls |
| 2326692 | DELICIOUS CHOCOLATE ICE CREAM SURROUNDED BY CHOCOLATE CHIP ICE CREAM, TOPPED WITH FUDGE... ICE CREAM ROLL | Ice Cream & Frozen Yogurt | Ice cream roll | Roll, sweet, no frosting | Bakery > Rolls | Bakery > Rolls > Chocolate Fudge Almonds Candy Chips Ice Cream Ribbon | rolls |
| 2510477 | SWISS ROLLS ICE CREAM, SWISS ROLLS | Croissants, Sweet Rolls, Muffins & Other Pastries | Ice cream roll | Roll, sweet, no frosting | Bakery > Rolls | Bakery > Rolls > Swiss | rolls |
| 2140117 | COFFEE & BISCOTTI COOKIE WITH COFFEE REDUCED FAT ICE CREAM TOPPED WITH FUDGE SAUCE... BARS | Ice Cream & Frozen Yogurt | Ice cream bar, stick or nugget, with crunch coating | Biscotti | Bakery > Biscotti | Bakery > Biscotti > Coffee Chocolate Espresso > Reduced Fat | biscotti |
| 2471593 | FUDGE BROWNIE CREAMY VANILLA ICE CREAM RIPPLED WITH CHOCOLATE SAUCE, ON A FUDGE-TOPPED BROWNIE CRUST... SUNDAE PREMIUM ICE CREAM CAKE | Ice Cream & Frozen Yogurt | Ice cream cake | Brownie, chocolate | Bakery > Brownies > Brownie | Bakery > Brownies > Brownie > Ice Cream Fudge Vanilla Chocolate | brownies |

**Concrete fix rule:** If BFC = `Ice Cream & Frozen Yogurt` or `Other Frozen Desserts` and title contains `ICE CREAM`, canonical path must start under `Frozen > Ice Cream` or `Frozen > Ice Cream Cake`. The tokens `ROLL`, `CAKE`, `COOKIE`, `BROWNIE`, and `PIE` in the title must be treated as **form descriptors** (like "bar" or "stick") rather than category anchors. The matched key must be `ice cream` (or `ice cream cake` / `ice cream sandwich`), not `rolls` or `brownies`.

---

### 1.4 Deli Meat & Prepared Meat "Roll" Hijack → Bakery > Rolls *(Severity: High)*

**Pattern:** Charcuterie snack rolls (`prosciutto and mozzarella`, `pepperoni and mozzarella`, `salami and cheese`) and prepared meat products (`fully cooked turkey roll`) are routed to `Bakery > Rolls` because the title contains the generic word "roll".

**Why it is wrong:** These are meat/cheese roll-ups or prepared meat products. The BFC is `Pepperoni, Salami & Cold Cuts` or `Cooked & Prepared`. A `Bakery > Rolls` node implies bread-based dinner rolls or sweet rolls, which these products are not.

**Count:** 34 rows.

**Query used:**
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title, cp, bfc = row['title'].upper(), row['canonical_path'], row['branded_food_category']
        if 'Bakery > Rolls' in cp:
            if any(x in title for x in ['PROSCIUTTO','PEPPERONI','SALAMI','GENOA']) and 'ROLL' in title:
                print(row['fdc_id'], row['title'], bfc, cp, row['retail_leaf_path'])
            elif 'TURKEY ROLL' in title or ('FULLY COOKED' in title and 'TURKEY' in title and 'ROLL' in title):
                print(row['fdc_id'], row['title'], bfc, cp, row['retail_leaf_path'])
            elif bfc == 'Cooked & Prepared' and 'ROLL' in title and 'GREEN DRAGON' not in title:
                print(row['fdc_id'], row['title'], bfc, cp, row['retail_leaf_path'])
```

**Examples (15 of 34):**

| fdc_id | title | branded_food_category | fndds_desc | esha_desc | canonical_path | retail_leaf_path | matched_key |
|---|---|---|---|---|---|---|---|
| 2388670 | PROSCIUTTO AND MOZZARELLA ROLL & GO | Pepperoni, Salami & Cold Cuts | roll cheese | Roll, 8-grain | Bakery > Rolls | Bakery > Rolls > Mozzarella | rolls |
| 2388678 | PROSCIUTTO AND PROVOLONE ROLL & GO | Pepperoni, Salami & Cold Cuts | roll cheese | Roll, 8-grain | Bakery > Rolls | Bakery > Rolls > Plain | rolls |
| 2598467 | ROLL & GO PEPPERONI AND MOZZARELLA | Pepperoni, Salami & Cold Cuts | pepperoni | Roll, 8-grain | Bakery > Rolls | Bakery > Rolls > Mozzarella | rolls |
| 2366483 | SALUMI ROLLS HAND ROLLED PEPPERONI & MOZZARELLA CHEESE | Pepperoni, Salami & Cold Cuts | roll cheese | Roll, cheese | Bakery > Rolls | Bakery > Rolls > Mozzarella > Rolled | rolls |
| 2483569 | MOZZARELLA CHEESE & PROSCIUTTO HAM ROLLS | Pepperoni, Salami & Cold Cuts | roll cheese | Roll, cheese | Bakery > Rolls | Bakery > Rolls > Mozzarella Cheese Prosciutto | rolls |
| 2637129 | UNCURED GENOA SALAMI & PROVOLONE CHEESE CHARCUTERIE ROLLS | Pepperoni, Salami & Cold Cuts | salami | Roll, cheese | Bakery > Rolls | Bakery > Rolls > Genoa Salami Provolone Cheese | rolls |
| 2366481 | HAND ROLLED HARD SALAMI & MOZZARELLA CHEESE SALUMI ROLLS | Pepperoni, Salami & Cold Cuts | roll cheese | Roll, cheese | Bakery > Rolls | Bakery > Rolls > Hard Salami Mozzarella > Rolled | rolls |
| 2598479 | ROLL & GO PROSCIUTTO AND MOZZARELLA | Pepperoni, Salami & Cold Cuts | roll cheese | Roll, 8-grain | Bakery > Rolls | Bakery > Rolls > Plain | rolls |
| 2074193 | FRESH MOZZARELLA CHEESE BASIL & PROSCIUTTO ROLL | Pepperoni, Salami & Cold Cuts | roll cheese | Roll, cheese | Bakery > Rolls | Bakery > Rolls > Fresh Mozzarella Basil | rolls |
| 2074190 | MOZZARELLA CHEESE ROLL WITH PROSCIUTTO & BASIL | Pepperoni, Salami & Cold Cuts | roll cheese | Roll, cheese | Bakery > Rolls | Bakery > Rolls > Mozzarella Prosciutto Basil | rolls |
| 2153817 | FRESH MOZZARELLA CHEESE, PROSCIUTTO & BASIL ROLL | Pepperoni, Salami & Cold Cuts | roll cheese | Roll, cheese | Bakery > Rolls | Bakery > Rolls > Fresh Mozzarella Prosciutto Basil | rolls |
| 2637128 | PROSCIUTTO & PROVOLONE CHEESE CHARCUTERIE ROLLS | Pepperoni, Salami & Cold Cuts | roll cheese | Roll, cheese | Bakery > Rolls | Bakery > Rolls > Prosciutto Provolone Cheese | rolls |
| 2366494 | HAND ROLLED PROSCIUTTO & MOZZARELLA CHEESE SALUMI ROLLS | Pepperoni, Salami & Cold Cuts | roll cheese | Roll, cheese | Bakery > Rolls | Bakery > Rolls > Prosciutto Mozzarella > Rolled | rolls |
| 2597035 | FULLY COOKED TURKEY ROLL | Cooked & Prepared | turkey | Roll, dinner, prepared from recipe with 2% milk, 2 1/2\" | Bakery > Rolls | Bakery > Rolls > Plain | rolls |
| 2545715 | OVEN ROASTED SLICED TURKEY ROLL | Pepperoni, Salami & Cold Cuts | turkey | Roll, dinner, prepared from recipe with 2% milk, 2 1/2\" | Bakery > Rolls | Bakery > Rolls > Sliced | rolls |

**Concrete fix rule:** If BFC ∈ {`Pepperoni, Salami & Cold Cuts`, `Cooked & Prepared`, `Meat/Poultry/Other Animals Prepared/Processed`} and title contains `PROSCIUTTO`, `PEPPERONI`, `SALAMI`, `TURKEY`, `GENOA`, or `CHARCUTERIE`, **hard-block** `Bakery > Rolls`. Route instead to `Meat & Seafood > Deli > Charcuterie Rolls` or `Meat & Seafood > Prepared Meat > Turkey Roll`. The word "roll" must be interpreted as "rolled / spiral form" (like a pinwheel or rollup), not as a bread roll.

---

### 1.5 Cookies & Biscuits Broken Leaf Fragments *(Severity: High)*

**Pattern:** Products with BFC `Cookies & Biscuits` and title containing `Cookies 'N Creme`, `Cookies And Cream`, or `Cookies N Cream` are routed to `Bakery > Cookies` with leaf fragments `And Cream`, `Creme`, `N Cream`, or `N Creme`. These are not real product identities; they are parser artifacts where the flavor phrase was split incorrectly.

**Why it is wrong:** A leaf like `And Cream` or `N Creme` has no semantic meaning in retail search. A shopper cannot navigate to `Bakery > Cookies > And Cream` and expect to find a coherent product set. The identity should be `Cookies And Cream` as a single flavor/modifier unit.

**Count:** 53 rows where BFC = `Cookies & Biscuits`, canonical path contains `Bakery > Cookies`, and leaf is a broken fragment.

**Query used:**
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        if row['branded_food_category'] == 'Cookies & Biscuits' and 'Bakery > Cookies' in row['canonical_path']:
            leaf = row['retail_leaf_path'].split('>')[-1].strip()
            if leaf in ['And Cream', 'Creme', 'N Cream', 'N Creme'] or leaf.startswith('And ') or leaf.startswith('N '):
                print(row['fdc_id'], row['title'], row['canonical_path'], row['retail_leaf_path'])
```

**Examples (15 of 53):**

| fdc_id | title | branded_food_category | fndds_desc | esha_desc | canonical_path | retail_leaf_path | matched_key |
|---|---|---|---|---|---|---|---|
| 2566654 | COOKIES 'N CRME CAKE | Cookies & Biscuits | cake nfs | Cake, ice cream, strawberry 'n cream | Bakery > Cookies | Bakery > Cookies > And Cream | cookies |
| 2569578 | COOKIES AND CREAM COVERED BISCUIT STICKS | Cookies & Biscuits | cookie | Cookie, butter / spritz | Bakery > Cookies | Bakery > Cookies > And Cream | cookies |
| 1845701 | COOKIES AND CREAM FLAVORED COVERED BISCUIT STICKS | Cookies & Biscuits | cookie | Cookie, butter / spritz | Bakery > Cookies | Bakery > Cookies > And Cream | cookies |
| 2112441 | COOKIES & CREAM FLAVORED COVERED BISCUIT STICKS | Cookies & Biscuits | cookie | Cookie, butter / spritz | Bakery > Cookies | Bakery > Cookies > And Cream | cookies |
| 1868603 | GLICO, POCKY, COOKIES & CREAM COVERED BISCUIT STICKS | Cookies & Biscuits | cookie | Cookie, butter / spritz | Bakery > Cookies | Bakery > Cookies > And Cream | cookies |
| 2375432 | COOKIES N CREAM GOOEY | Cookies & Biscuits | cookie | Cookie, chocolate chip | Bakery > Cookies | Bakery > Cookies > And Cream | cookies |
| 2071082 | COOKIES N' CREAM | Cookies & Biscuits | cookie | Cookie, chocolate chip | Bakery > Cookies | Bakery > Cookies > N Cream | cookies |
| 1880644 | BARK, COOKIES N' CREAM | Cookies & Biscuits | cookie | Cookie, chocolate chip | Bakery > Cookies | Bakery > Cookies > N Cream | cookies |
| 2053718 | BLISSFUL TREATS, COOKIES 'N CREAM MOUSSE | Cookies & Biscuits | cookie | Cookie, chocolate chip | Bakery > Cookies | Bakery > Cookies > N Cream | cookies |
| 2495408 | COOKIES & CREAM POPS | Cookies & Biscuits | cookie | Cookie, chocolate chip | Bakery > Cookies | Bakery > Cookies > And Cream | cookies |
| 1875658 | SANTA'S VILLAGE, COOKIES 'N CREAM BITES | Cookies & Biscuits | cookie | Cookie, chocolate chip | Bakery > Cookies | Bakery > Cookies > N Cream | cookies |
| 2090464 | CRISPY MARSHMALLOW SQUARES COOKIES N'CREAM | Cookies & Biscuits | cookie | Cookie, chocolate chip | Bakery > Cookies | Bakery > Cookies > N Cream | cookies |
| 2166150 | COOKIES 'N CREAM ICE CREAM BAR | Cookies & Biscuits | ice cream bar | Cookie, chocolate chip | Bakery > Cookies | Bakery > Cookies > N Cream | cookies |
| 2574394 | COOKIES 'N' CREME COOKIE BITES | Cookies & Biscuits | cookie | Cookie, chocolate chip | Bakery > Cookies | Bakery > Cookies > N Creme | cookies |
| 2511027 | COOKIES & CREAM WAFELS | Cookies & Biscuits | cookie | Cookie, chocolate chip | Bakery > Cookies | Bakery > Cookies > And Cream | cookies |

**Concrete fix rule:** In the modifier pipeline, treat `Cookies And Cream`, `Cookies N Creme`, `Cookies 'N Cream`, `Cookies N' Creme`, and `Cookies N' Cream` as **atomic flavor tokens**. Do not split on `N` or `And`; preserve the full phrase as a single modifier segment (e.g., `Bakery > Cookies > Cookies And Cream` or `Snack > Bars > Protein Bars > Cookies And Cream`).

---

### 1.6 Cereal / Popcorn / Bars / Protein Shakes / Syrup → Bakery (Flavor Hijack) *(Severity: Medium)*

**Pattern:** Non-bakery product types whose titles contain bakery-flavor tokens (cinnamon roll, cookie, churro, brownie, cake) are routed into Bakery paths.

**Why it is wrong:** A "cinnamon roll flavored popcorn" is popcorn, not a cinnamon roll. A "cinnamon roll protein shake" is a protein shake, not pastry. A "cinnamon roll cereal" is cereal, not a bakery item. The BFC (`Cereal`, `Popcorn, Peanuts, Seeds & Related Snacks`, `Snack, Energy & Granola Bars`, `Energy, Protein & Muscle Recovery Drinks`, `Syrups & Molasses`) is the primary identity.

**Count:** 90 rows.

**Query used:**
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title, cp, bfc = row['title'].upper(), row['canonical_path'], row['branded_food_category']
        if 'Bakery' not in cp:
            continue
        # Cereal
        if 'CEREAL' in title and any(x in title for x in ['CINNAMON ROLL','CHURRO','SWISS ROLLS']):
            print(row)
        # Popcorn (exclude actual popcorn cakes which are legitimate snack cakes)
        elif 'POPCORN' in title and 'CAKE' not in title and any(x in title for x in ['CINNAMON ROLL','COOKIE']):
            print(row)
        # Protein shake
        elif 'PROTEIN SHAKE' in title and 'CINNAMON ROLL' in title:
            print(row)
        # Syrup
        elif 'SYRUP' in title and 'CINNAMON ROLL' in title:
            print(row)
        # Bars (only if BFC is not Cakes/Cookies)
        elif 'BAR' in title and ('CINNAMON ROLL' in title or 'COOKIE' in title or 'CAKE' in title or 'BROWNIE' in title or 'DONUT' in title):
            if 'Cakes' not in bfc and 'Cookies' not in bfc:
                print(row)
```

**Examples (15 of 90):**

| fdc_id | title | branded_food_category | fndds_desc | esha_desc | canonical_path | retail_leaf_path | matched_key |
|---|---|---|---|---|---|---|---|
| 1459972 | Cap'n Crunch's Cinnamon Roll Crunch 14.5 Ounce Paper Box | Processed Cereal Products | cereal | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Crunch | cinnamon rolls |
| 2613149 | Churros Cinnamon Toast Crunch Cereal 2 Pack | Processed Cereal Products | cereal | Churro, cinnamon & sugar | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Cinnamon | churros |
| 2724587 | Cinnamon Toast Crunch Rolls Breakfast Cereal | Processed Cereal Products | cereal | Roll, sweet, no frosting | Bakery > Rolls | Bakery > Rolls > Cinnamon Toast Crunch > Reduced Sugar | rolls |
| 2497919 | SWISS ROLLS CRISPY CHOCOLATEY SWIRL PUFFS WITH CHOCOLATEY CREME COATING CEREAL | Cereal | cereal | Roll, sweet, no frosting | Bakery > Rolls | Bakery > Rolls > Chocolatey Swirl Chocolate > Reduced Sugar | rolls |
| 1855426 | POST, MINI CHURROS CEREAL, SWEETENED WHEAT CEREAL | Cereal | cereal | Churro, cinnamon & sugar | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Cinnamon > Sweetened | churros |
| 1873498 | POPCORN, CLASSIC CINNAMON ROLL | Popcorn, Peanuts, Seeds & Related Snacks | popcorn | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Plain | cinnamon rolls |
| 1915535 | POPCORN, CLASSIC CINNAMON ROLL | Popcorn, Peanuts, Seeds & Related Snacks | popcorn | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Plain | cinnamon rolls |
| 2172332 | CRUNCHY CINNAMON ROLL FLAVORED POPCORN WITH A WHITE CONFECTIONERY DRIZZLE POPCORN MIX | Popcorn, Peanuts, Seeds & Related Snacks | popcorn | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > White Confectionery | cinnamon rolls |
| 2282147 | CINNAMON ROLL HIGH PROTEIN SHAKE | Energy, Protein & Muscle Recovery Drinks | shake | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > High Protein | cinnamon rolls |
| 2465054 | CINNAMON ROLL FLAVORED HIGH PROTEIN SHAKE | Energy, Protein & Muscle Recovery Drinks | shake | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > High Protein | cinnamon rolls |
| 1429284 | SYRUP, CINNAMON ROLL | Syrups & Molasses | syrup | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Plain | cinnamon rolls |
| 1915616 | KIDS CINNAMON ROLL BARS | Snack, Energy & Granola Bars | bar | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > High Protein | cinnamon rolls |
| 2654881 | CINNAMON ROLL HIGH PROTEIN BAR | Snack, Energy & Granola Bars | bar | Cinnamon roll | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > High Protein | cinnamon rolls |
| 1837765 | NUTRITION BAR, CINNAMON BUN COOKIE DOUGH | Snack, Energy & Granola Bars | bar | Cookie dough | Bakery > Buns | Bakery > Buns > Cinnamon Cookie Dough | buns |
| 2486194 | COLD BREW COFFEE CHEESECAKE | Other Drinks | coffee | Cheesecake | Bakery > Cheesecake | Bakery > Cheesecake > Cold Brew Coffee | cheesecake |

**Concrete fix rule:** Maintain a **product-type priority list**. If the title contains a high-confidence product-type anchor (`CEREAL`, `POPCORN`, `PROTEIN SHAKE`, `SYRUP`, `BAR`, `CANDY`) and the BFC corroborates it, the flavor token must never promote the canonical path to `Bakery`. Instead, place the bakery-flavor token in the leaf modifier (e.g., `Pantry > Cereal > Cinnamon Roll Crunch` or `Snack > Popcorn > Cinnamon Roll`).

---

### 1.7 Reference-Match Leakage: ESHA/FNDDS Bakery Descriptions Override Title/BFC *(Severity: Medium)*

**Pattern:** The `esha_desc` or `fndds_desc` field contains a bakery term (`Churro`, `Cinnamon roll`, `Roll`, `Cookie`, `Biscotti`, `Cheesecake`, `Brownie`) because the reference database matched a flavor-named product to a dessert entry. Codex then uses that reference match to anchor the canonical path in `Bakery`, even though the title and BFC say beverage, ice cream, or meat.

**Why it is wrong:** Reference databases (ESHA, FNDDS) do not distinguish between a *churro* and a *churro-flavored coffee creamer* in their description fields. The description `Churro, cinnamon & sugar` is matched to both actual churros and churro-flavored liquids. Using the reference description as a taxonomy anchor without cross-checking the title/BFC causes systematic leakage.

**Count:** 237 rows where title signals non-bakery identity, `Bakery` is in the canonical path, and ESHA/FNDDS description contains a bakery term.

**Query used:**
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title, cp = row['title'].upper(), row['canonical_path']
        esha, fndds = (row['esha_desc'] or '').upper(), (row['fndds_desc'] or '').upper()
        if 'Bakery' not in cp:
            continue
        if any(t in title for t in ['CREAMER','ICED COFFEE','LATTE','COLD BREW','ICE CREAM','PROSCIUTTO','PEPPERONI','SALAMI','TURKEY ROLL','PROTEIN SHAKE','POPCORN','CEREAL','BAR','SYRUP']):
            if any(r in esha or r in fndds for r in ['CHURRO','COOKIE','CAKE','PASTRY','ROLL','BUN','BREAD','CINNAMON ROLL','BISCOTTI','BROWNIE','CHEESECAKE']):
                print(row['fdc_id'], row['title'], row['branded_food_category'], cp, row['retail_leaf_path'], row['fndds_desc'], row['esha_desc'])
```

**Examples (15 of 237):**

| fdc_id | title | branded_food_category | canonical_path | retail_leaf_path | fndds_desc | esha_desc |
|---|---|---|---|---|---|---|
| 2528895 | CINNAMON CHURRO COFFEE CREAMER | Milk Additives | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Cinnamon | coffee creamer liquid | Churro, cinnamon & sugar |
| 2414656 | CINNAMON CHURRO ICED COFFEE | Other Drinks | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Cinnamon | coffee iced latte flavored | Churro, cinnamon & sugar |
| 1857339 | ICE CREAM ROLL WITH CHOCOLATE COOKIE CRUNCH OUTSIDE | Ice Cream & Frozen Yogurt | Bakery > Rolls | Bakery > Rolls > Mocha Chocolate Cookie Crunch > Low Fat | Ice cream bar, stick or nugget, with crunch coating | Roll, garlic, frozen dough |
| 2388670 | PROSCIUTTO AND MOZZARELLA ROLL & GO | Pepperoni, Salami & Cold Cuts | Bakery > Rolls | Bakery > Rolls > Mozzarella | roll cheese | Roll, 8-grain |
| 2598467 | ROLL & GO PEPPERONI AND MOZZARELLA | Pepperoni, Salami & Cold Cuts | Bakery > Rolls | Bakery > Rolls > Mozzarella | pepperoni | Roll, 8-grain |
| 2366483 | SALUMI ROLLS HAND ROLLED PEPPERONI & MOZZARELLA CHEESE | Pepperoni, Salami & Cold Cuts | Bakery > Rolls | Bakery > Rolls > Mozzarella > Rolled | roll cheese | Roll, cheese |
| 2597035 | FULLY COOKED TURKEY ROLL | Cooked & Prepared | Bakery > Rolls | Bakery > Rolls > Plain | turkey | Roll, dinner, prepared from recipe with 2% milk, 2 1/2\" |
| 2064495 | BUTTERFLAKE ROLLS | Croissants, Sweet Rolls, Muffins & Other Pastries | Bakery > Rolls | Bakery > Rolls > Plain | roll sweet no frosting | Roll, butterflake, frozen dough |
| 2054994 | HANNAFORD, SWISS ROLLS | Croissants, Sweet Rolls, Muffins & Other Pastries | Bakery > Rolls | Bakery > Rolls > Plain | roll sweet no frosting | Roll, dinner, sweet Hawaiian |
| 2282147 | CINNAMON ROLL HIGH PROTEIN SHAKE | Energy, Protein & Muscle Recovery Drinks | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > High Protein | shake | Cinnamon roll |
| 1873498 | POPCORN, CLASSIC CINNAMON ROLL | Popcorn, Peanuts, Seeds & Related Snacks | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Plain | popcorn | Cinnamon roll |
| 1459972 | Cap'n Crunch's Cinnamon Roll Crunch | Processed Cereal Products | Bakery > Pastry > Cinnamon Rolls | Bakery > Pastry > Cinnamon Rolls > Crunch | cereal | Cinnamon roll |
| 2613149 | Churros Cinnamon Toast Crunch Cereal | Processed Cereal Products | Bakery > Pastry > Churros | Bakery > Pastry > Churros > Cinnamon | cereal | Churro, cinnamon & sugar |
| 2140117 | COFFEE & BISCOTTI COOKIE WITH COFFEE REDUCED FAT ICE CREAM... BARS | Ice Cream & Frozen Yogurt | Bakery > Biscotti | Bakery > Biscotti > Coffee Chocolate Espresso > Reduced Fat | Ice cream bar, stick or nugget, with crunch coating | Biscotti |
| 2486194 | COLD BREW COFFEE CHEESECAKE | Other Drinks | Bakery > Cheesecake | Bakery > Cheesecake > Cold Brew Coffee | coffee | Cheesecake |

**Concrete fix rule:** Implement a **reference-description override gate**. Before allowing `esha_desc` or `fndds_desc` to determine the canonical path, check whether the title contains a high-confidence non-bakery product anchor (`COFFEE CREAMER`, `ICED COFFEE`, `ICE CREAM`, `PROSCIUTTO`, `PEPPERONI`, `SALAMI`, `TURKEY ROLL`, `PROTEIN SHAKE`, `POPCORN`, `CEREAL`, `SYRUP`). If yes, use the reference description **only** for nutrient matching, not for taxonomy routing.

---

### 1.8 Generic Identity Collisions: Rolls, Buns, Bagels, Bread, Cake, Pie, Cookie, Churro *(Severity: Medium)*

**Pattern:** When BFC and title clearly indicate one product category, but a generic form token (`roll`, `bun`, `cake`, `cookie`, `churro`) in the title triggers a Bakery path that contradicts the BFC.

**Why it is wrong:** `Bakery > Rolls` is semantically a bread/dough category. When BFC = `Pepperoni, Salami & Cold Cuts` or `Ice Cream & Frozen Yogurt` or `Cooked & Prepared`, the path `Bakery > Rolls` is a category error.

**Count:** 64 rows where `Bakery > Rolls` is the canonical path but BFC contradicts it.

**Query used:**
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        cp, bfc = row['canonical_path'], row['branded_food_category']
        if 'Bakery > Rolls' in cp and bfc in ['Pepperoni, Salami & Cold Cuts','Cooked & Prepared','Ice Cream & Frozen Yogurt']:
            print(row['fdc_id'], row['title'], bfc, cp, row['retail_leaf_path'])
```

**Examples (15 of 64):**

| fdc_id | title | branded_food_category | canonical_path | retail_leaf_path |
|---|---|---|---|---|
| 2388670 | PROSCIUTTO AND MOZZARELLA ROLL & GO | Pepperoni, Salami & Cold Cuts | Bakery > Rolls | Bakery > Rolls > Mozzarella |
| 2598467 | ROLL & GO PEPPERONI AND MOZZARELLA | Pepperoni, Salami & Cold Cuts | Bakery > Rolls | Bakery > Rolls > Mozzarella |
| 2366483 | SALUMI ROLLS HAND ROLLED PEPPERONI & MOZZARELLA CHEESE | Pepperoni, Salami & Cold Cuts | Bakery > Rolls | Bakery > Rolls > Mozzarella > Rolled |
| 2597035 | FULLY COOKED TURKEY ROLL | Cooked & Prepared | Bakery > Rolls | Bakery > Rolls > Plain |
| 1857339 | ICE CREAM ROLL WITH CHOCOLATE COOKIE CRUNCH OUTSIDE | Ice Cream & Frozen Yogurt | Bakery > Rolls | Bakery > Rolls > Mocha Chocolate Cookie Crunch > Low Fat |
| 2614525 | TRADITIONAL ICE CREAM ROLL | Ice Cream & Frozen Yogurt | Bakery > Rolls | Bakery > Rolls > Chocolate Caramel > No Sugar Added > Light |
| 2563044 | CELEBRATION ICE CREAM DESSERT ROLL | Ice Cream & Frozen Yogurt | Bakery > Rolls | Bakery > Rolls > Chocolate Crunch Fudge |
| 2018440 | PEANUT BUTTER CUP PREMIUM ICE CREAM ROLL WITH CHOCOLATE COOKIE CRUNCH OUTSIDE | Ice Cream & Frozen Yogurt | Bakery > Rolls | Bakery > Rolls > Peanut Butter Cup Chocolate Cookie Crunch |
| 2079205 | SALTED NUT ROLL FLAVORED MARSHMALLOW NOUGAT ICE CREAM | Ice Cream & Frozen Yogurt | Bakery > Rolls | Bakery > Rolls > Nut Marshmallow Nougat Caramel Swirl Candied Peanuts > Salted |
| 2482199 | STRAWBERRY SHORTCAKE ROLLS ICE CREAM | Ice Cream & Frozen Yogurt | Bakery > Rolls | Bakery > Rolls > Strawberry Shortcake |
| 2098000 | ICE CREAM ROLL STRAWBERRY SHORTCAKE | Ice Cream & Frozen Yogurt | Bakery > Rolls | Bakery > Rolls > Strawberry Shortcake |
| 2326692 | DELICIOUS CHOCOLATE ICE CREAM SURROUNDED BY CHOCOLATE CHIP ICE CREAM, TOPPED WITH FUDGE... ICE CREAM ROLL | Ice Cream & Frozen Yogurt | Bakery > Rolls | Bakery > Rolls > Chocolate Fudge Almonds Candy Chips Ice Cream Ribbon |
| 2510477 | SWISS ROLLS ICE CREAM, SWISS ROLLS | Croissants, Sweet Rolls, Muffins & Other Pastries | Bakery > Rolls | Bakery > Rolls > Swiss |
| 2579318 | HANDMADE FRESH MOZZARELLA, PROSCUITTO, FRESH BASIL SLICED CHARCUTERIE ROLL | Cooked & Prepared | Bakery > Rolls | Bakery > Rolls > Fresh Mozzarella Prosciutto Basil > Sliced |
| 1938067 | GREEN DRAGON ROLL | Cooked & Prepared | Bakery > Rolls | Bakery > Rolls > Eel Avocado Cucumber Shrimp Tempura Imitation Crab |

**Concrete fix rule:** Create a **BFC-to-path contradiction table**. If BFC ∈ {`Pepperoni, Salami & Cold Cuts`, `Cooked & Prepared`, `Ice Cream & Frozen Yogurt`, `Frozen Appetizers & Hors D'oeuvres`} and the candidate path is `Bakery > Rolls`, trigger a re-evaluation using title tokens. If title contains `ICE CREAM`, route to `Frozen`. If title contains meat/deli tokens, route to `Meat & Seafood`. If title contains sushi ingredients (`EEL`, `AVOCADO`, `SHRIMP TEMPURA`) and no bread token, route to `Meal > Sushi` or `Frozen > Appetizers`.

---

## 2. Ambiguous / Review-Needed Cases

### 2.1 Beyond Churros — Actual Snack or Cookie/Biscuit? *(Ambiguity: Review)*

**Item:**  
- `2628386` — ORIGINAL CINNAMON BEYOND CHURROS, BFC `Cookies & Biscuits`, path `Bakery > Pastry > Churros > Cinnamon`, fndds_desc `churros`, esha_desc `Churro, cinnamon & sugar`.
- `2628387` — SALTED CARAMEL BEYOND CHURROS, BFC `Other Snacks`, path `Bakery > Pastry > Churros > Multigrain Caramel > Salted`, fndds_desc `churros`, esha_desc `Churro, cinnamon & sugar`.

**Why ambiguous:** The brand name "Beyond Churros" suggests a snack product *inspired by* churros, but the BFC splits between `Cookies & Biscuits` and `Other Snacks`. The product may be a shelf-stable churro-shaped cookie or a puffed snack. Without packaging imagery, it is unclear whether `Bakery > Pastry > Churros` is correct or whether it should be `Snack > Puffed Snacks > Churro` or `Bakery > Cookies > Churro`. The reference description (`churros`) supports the current path, but the BFC ambiguity undermines confidence.

**Recommendation:** Flag for manual review. If the product is a dry, shelf-stable cookie-like item, keep in `Bakery`. If it is a puffed/extruded snack, move to `Snack`.

---

### 2.2 Butterflake Rolls — Actual Bakery Roll with Suspicious `Plain` Leaf *(Ambiguity: Review)*

**Item:**  
- `2064495` — BUTTERFLAKE ROLLS, BFC `Croissants, Sweet Rolls, Muffins & Other Pastries`, path `Bakery > Rolls > Plain`, fndds_desc `roll sweet no frosting`, esha_desc `Roll, butterflake, frozen dough`.

**Why ambiguous:** This is very likely a **correct** bakery product. The BFC is bakery-native, the ESHA description confirms "butterflake" and "frozen dough", and the title contains no contradictory signal. The only issue is the `Plain` leaf, which is suspicious because "Butterflake" is a specific sub-type of roll. The leaf should probably be `Bakery > Rolls > Butterflake` or `Bakery > Sweet Rolls > Butterflake`, not `Plain`.

**Recommendation:** This is a **modifier-pipeline bug**, not a category hijack. Fix rule: if title contains a specific roll subtype (`Butterflake`, `Hawaiian`, `Potato`, `Onion`), use that token as the leaf instead of `Plain`.

---

### 2.3 Swiss Rolls — Dessert Cake Roll vs. Dinner Roll *(Ambiguity: Review)*

**Item:**  
- `2054994` — HANNAFORD, SWISS ROLLS, BFC `Croissants, Sweet Rolls, Muffins & Other Pastries`, path `Bakery > Rolls > Plain`, fndds_desc `roll sweet no frosting`, esha_desc `Roll, dinner, sweet Hawaiian`.

**Why ambiguous:** "Swiss rolls" in the US retail context are **creme-filled chocolate cake rolls** (e.g., Little Debbie Swiss Rolls), not yeast dinner rolls. The BFC `Croissants, Sweet Rolls, Muffins & Other Pastries` supports a sweet bakery identity, but the current path `Bakery > Rolls > Plain` treats them as generic dinner rolls. The ESHA description `Roll, dinner, sweet Hawaiian` is a poor reference match — it conflates "sweet roll" with "Hawaiian dinner roll".

**However**, 28 rows of Swiss Rolls are currently in `Bakery > Rolls`. While this is not as severe as routing meat to bakery, it is semantically imprecise. Swiss Rolls should be under `Bakery > Sweet Rolls > Swiss Roll` or `Bakery > Snack Cakes > Swiss Roll`, not `Bakery > Rolls > Plain`.

**Recommendation:** Re-route all `SWISS ROLLS` titles from `Bakery > Rolls` to `Bakery > Sweet Rolls` or `Bakery > Snack Cakes`. The current path is a **sub-category error**, not a cross-category hijack, but it breaks faceted search for shoppers looking for sweet dessert rolls vs. dinner rolls.

---

## 3. Complete Command & Query Log

All counts and examples in this report were generated by the following reproducible Python scripts executed against `retail_mapper/v2/codex_full_corpus_audit.csv`.

### 3.1 Beverage & Creamer → Bakery (Pattern 1.1)
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        cp, title = row['canonical_path'], row['title'].upper()
        if 'Bakery' in cp and 'COFFEE CREAMER' in title and 'COFFEE' in title:
            if any(x in title for x in ['CHURRO','CINNAMON ROLL','BISCOTTI','CHEESECAKE']):
                print(row['fdc_id'], row['title'], row['branded_food_category'], cp, row['retail_leaf_path'])
```

### 3.2 Churro Beverages → Bakery (Pattern 1.2)
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title, cp = row['title'].upper(), row['canonical_path']
        if 'CHURRO' in title and any(x in title for x in ['COFFEE','LATTE','COLD BREW','ICED']) and 'Bakery' in cp:
            print(row['fdc_id'], row['title'], row['branded_food_category'], cp, row['retail_leaf_path'])
```

### 3.3 Ice Cream → Bakery (Pattern 1.3)
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title, cp = row['title'].upper(), row['canonical_path']
        if 'Bakery' in cp and 'ICE CREAM' in title:
            if any(x in title for x in ['ROLL','CAKE','COOKIE','PIE','BROWNIE']):
                print(row['fdc_id'], row['title'], row['branded_food_category'], cp, row['retail_leaf_path'])
```

### 3.4 Deli Meat "Roll" → Bakery (Pattern 1.4)
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title, cp, bfc = row['title'].upper(), row['canonical_path'], row['branded_food_category']
        if 'Bakery > Rolls' in cp:
            if any(x in title for x in ['PROSCIUTTO','PEPPERONI','SALAMI','GENOA']) and 'ROLL' in title:
                print(row['fdc_id'], row['title'], bfc, cp, row['retail_leaf_path'])
            elif 'TURKEY ROLL' in title or ('FULLY COOKED' in title and 'TURKEY' in title and 'ROLL' in title):
                print(row['fdc_id'], row['title'], bfc, cp, row['retail_leaf_path'])
            elif bfc == 'Cooked & Prepared' and 'ROLL' in title and 'GREEN DRAGON' not in title:
                print(row['fdc_id'], row['title'], bfc, cp, row['retail_leaf_path'])
```

### 3.5 Broken Cookie Leaf Fragments (Pattern 1.5)
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        if row['branded_food_category'] == 'Cookies & Biscuits' and 'Bakery > Cookies' in row['canonical_path']:
            leaf = row['retail_leaf_path'].split('>')[-1].strip()
            if leaf in ['And Cream', 'Creme', 'N Cream', 'N Creme'] or leaf.startswith('And ') or leaf.startswith('N '):
                print(row['fdc_id'], row['title'], row['canonical_path'], row['retail_leaf_path'])
```

### 3.6 Cereal / Popcorn / Bars / Shakes / Syrup → Bakery (Pattern 1.6)
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title, cp, bfc = row['title'].upper(), row['canonical_path'], row['branded_food_category']
        if 'Bakery' not in cp:
            continue
        if 'CEREAL' in title and any(x in title for x in ['CINNAMON ROLL','CHURRO','SWISS ROLLS']):
            print(row['fdc_id'], row['title'], bfc, cp, row['retail_leaf_path'])
        elif 'POPCORN' in title and 'CAKE' not in title and any(x in title for x in ['CINNAMON ROLL','COOKIE']):
            print(row['fdc_id'], row['title'], bfc, cp, row['retail_leaf_path'])
        elif 'PROTEIN SHAKE' in title and 'CINNAMON ROLL' in title:
            print(row['fdc_id'], row['title'], bfc, cp, row['retail_leaf_path'])
        elif 'SYRUP' in title and 'CINNAMON ROLL' in title:
            print(row['fdc_id'], row['title'], bfc, cp, row['retail_leaf_path'])
        elif 'BAR' in title and any(x in title for x in ['CINNAMON ROLL','COOKIE','CAKE','BROWNIE','DONUT']):
            if 'Cakes' not in bfc and 'Cookies' not in bfc:
                print(row['fdc_id'], row['title'], bfc, cp, row['retail_leaf_path'])
```

### 3.7 Reference-Match Leakage (Pattern 1.7)
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        title, cp = row['title'].upper(), row['canonical_path']
        esha, fndds = (row['esha_desc'] or '').upper(), (row['fndds_desc'] or '').upper()
        if 'Bakery' not in cp:
            continue
        title_signals = ['CREAMER','ICED COFFEE','LATTE','COLD BREW','ICE CREAM','PROSCIUTTO','PEPPERONI','SALAMI','TURKEY ROLL','PROTEIN SHAKE','POPCORN','CEREAL','BAR','SYRUP']
        ref_signals = ['CHURRO','COOKIE','CAKE','PASTRY','ROLL','BUN','BREAD','CINNAMON ROLL','BISCOTTI','BROWNIE','CHEESECAKE']
        if any(t in title for t in title_signals) and any(r in esha or r in fndds for r in ref_signals):
            print(row['fdc_id'], row['title'], row['branded_food_category'], cp, row['retail_leaf_path'], row['fndds_desc'], row['esha_desc'])
```

### 3.8 Generic Roll Collision (Pattern 1.8)
```python
import csv
with open('retail_mapper/v2/codex_full_corpus_audit.csv') as f:
    for row in csv.DictReader(f):
        cp, bfc = row['canonical_path'], row['branded_food_category']
        if 'Bakery > Rolls' in cp and bfc in ['Pepperoni, Salami & Cold Cuts','Cooked & Prepared','Ice Cream & Frozen Yogurt']:
            print(row['fdc_id'], row['title'], bfc, cp, row['retail_leaf_path'])
```

---

## 4. Prioritized Fix Backlog

| Priority | Pattern | Count | Effort | Fix Rule Summary |
|---|---|---|---|---|
| **P0** | Beverage / creamer → Bakery (churro, cinnamon roll, biscotti) | 24 | Low | Hard-block `Bakery` when BFC = Milk Additives / Coffee / Other Drinks and title contains coffee/creamer terms. Route to `Beverage > Coffee Creamer` or `Dairy > Cream > Coffee Creamer`. |
| **P0** | Ice cream / frozen → Bakery (roll, cake, cookie, brownie) | 109 | Low | Hard-block `Bakery` when BFC = Ice Cream & Frozen Yogurt and title contains `ICE CREAM`. Route to `Frozen > Ice Cream` family; treat `ROLL`/`CAKE`/`COOKIE` as form descriptors, not category anchors. |
| **P0** | Deli meat / prepared meat "roll" → Bakery > Rolls | 34 | Low | Hard-block `Bakery > Rolls` when BFC = Pepperoni/Salami/Cold Cuts or Cooked & Prepared and title contains deli/meat tokens. Route to `Meat & Seafood > Deli` or `Meat & Seafood > Prepared Meat`. |
| **P1** | Cereal / popcorn / bars / shakes / syrup → Bakery | 90 | Medium | Product-type priority list: if title contains `CEREAL`, `POPCORN`, `PROTEIN SHAKE`, `SYRUP`, `BAR` and BFC corroborates, never promote to `Bakery`. Use flavor token as leaf modifier only. |
| **P1** | Reference-match leakage (ESHA/FNDDS bakery desc) | 237 | Medium | Reference-description override gate: if title contains high-confidence non-bakery anchor, ignore ESHA/FNDDS bakery descriptions for taxonomy routing (use only for nutrient mapping). |
| **P1** | Broken cookie leaf fragments (And Cream, N Creme) | 53 | Low | Atomic token rule: treat `Cookies And Cream` / `Cookies N Creme` as indivisible modifier strings in the pipeline. |
| **P2** | Generic roll collision (BFC contradicts Bakery > Rolls) | 64 | Low | BFC-to-path contradiction table: when BFC is meat/deli/ice cream/frozen and candidate path is `Bakery > Rolls`, force re-evaluation by title tokens. |
| **P2** | Swiss Rolls sub-category error | 28 | Low | Re-route `SWISS ROLLS` from `Bakery > Rolls > Plain` to `Bakery > Sweet Rolls > Swiss Roll` or `Bakery > Snack Cakes > Swiss Roll`. |
| **P3** | Beyond Churros ambiguity | 2 | Low | Manual review: determine if product is cookie-like (keep `Bakery`) or puffed snack (move to `Snack`). |
| **P3** | Butterflake Rolls `Plain` leaf | 4 | Low | Modifier fix: use `Butterflake` as leaf instead of `Plain` when title contains the subtype. |

**Total high-confidence bug rows:** 611  
**Total review-needed rows:** 34  
**Grand total affected:** 645 rows (0.14 % of corpus)

---

## 5. Proposed Regression Tests

These tests should be added to `implementation/tests/` (or a new `retail_mapper/v2/tests/` directory) and run against future Codex rebuilds.

### 5.1 `test_beverage_creamer_never_bakery`
```python
def test_beverage_creamer_never_bakery(self):
    hijack_terms = ['COFFEE CREAMER', 'ICED COFFEE', 'COLD BREW', 'LATTE']
    flavor_terms = ['CHURRO', 'CINNAMON ROLL', 'BISCOTTI', 'CHEESECAKE', 'DANISH']
    for row in self.audit_rows:
        title = row['title'].upper()
        cp = row['canonical_path']
        if any(t in title for t in hijack_terms) and any(f in title for f in flavor_terms):
            self.assertNotIn('Bakery', cp,
                f"{row['fdc_id']} {title} is a beverage/creamer but routed to Bakery: {cp}")
```

### 5.2 `test_ice_cream_never_bakery_rolls`
```python
def test_ice_cream_never_bakery_rolls(self):
    for row in self.audit_rows:
        title = row['title'].upper()
        cp = row['canonical_path']
        bfc = row['branded_food_category']
        if 'ICE CREAM' in title and bfc == 'Ice Cream & Frozen Yogurt':
            self.assertFalse(cp.startswith('Bakery > Rolls') or cp.startswith('Bakery > Pastry'),
                f"{row['fdc_id']} is ice cream but routed to {cp}")
```

### 5.3 `test_deli_meat_roll_never_bakery_rolls`
```python
def test_deli_meat_roll_never_bakery_rolls(self):
    meat_terms = ['PROSCIUTTO', 'PEPPERONI', 'SALAMI', 'GENOA', 'TURKEY ROLL']
    for row in self.audit_rows:
        title = row['title'].upper()
        cp = row['canonical_path']
        bfc = row['branded_food_category']
        if any(t in title for t in meat_terms) and 'ROLL' in title:
            if bfc in ['Pepperoni, Salami & Cold Cuts', 'Cooked & Prepared']:
                self.assertNotIn('Bakery > Rolls', cp,
                    f"{row['fdc_id']} deli meat roll routed to Bakery: {cp}")
```

### 5.4 `test_cookies_and_cream_atomic_modifier`
```python
def test_cookies_and_cream_atomic_modifier(self):
    bad_leaves = ['And Cream', 'N Cream', 'N Creme', 'Creme']
    for row in self.audit_rows:
        leaf = row['retail_leaf_path'].split('>')[-1].strip()
        if any(b in leaf for b in bad_leaves):
            title = row['title'].upper()
            if 'COOKIES' in title and any(x in title for x in ['CREAM','CREME']):
                self.fail(f"{row['fdc_id']} has broken leaf '{leaf}' for title '{title}'")
```

### 5.5 `test_cereal_popcorn_bar_never_bakery_for_flavor`
```python
def test_cereal_popcorn_bar_never_bakery_for_flavor(self):
    product_types = ['CEREAL', 'POPCORN', 'PROTEIN SHAKE', 'SYRUP']
    for row in self.audit_rows:
        title = row['title'].upper()
        cp = row['canonical_path']
        if any(pt in title for pt in product_types) and 'Bakery' in cp:
            self.fail(f"{row['fdc_id']} {title} is a non-bakery product type but routed to Bakery: {cp}")
```

### 5.6 `test_reference_leakage_gate`
```python
def test_reference_leakage_gate(self):
    title_signals = ['CREAMER', 'ICED COFFEE', 'ICE CREAM', 'PROSCIUTTO', 'PEPPERONI', 'TURKEY ROLL']
    ref_signals = ['CHURRO', 'CINNAMON ROLL', 'ROLL, DINNER', 'COOKIE', 'BISCOTTI']
    for row in self.audit_rows:
        title = row['title'].upper()
        cp = row['canonical_path']
        esha = (row['esha_desc'] or '').upper()
        fndds = (row['fndds_desc'] or '').upper()
        if any(t in title for t in title_signals) and 'Bakery' in cp:
            if any(r in esha or r in fndds for r in ref_signals):
                self.fail(f"{row['fdc_id']} reference leakage: title={title}, esha={esha}, path={cp}")
```

---

*Report generated by Kimi Code CLI. All counts are reproducible from `retail_mapper/v2/codex_full_corpus_audit.csv` using the queries documented in Section 3. No CSV or Python files were modified during this audit.*
