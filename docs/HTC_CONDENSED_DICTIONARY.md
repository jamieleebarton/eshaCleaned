# HTC Condensed Encoding Dictionary

A compact specification for the Hestia Taxonomy Code (HTC) — an 8-character deterministic food identity encoder. Feed this to an LLM with a product title or ingredient string and it can generate the correct code.

---

## 1. Output Format

8-character string, positions 1–8:

| Pos | Field | Width | Description |
|-----|-------|-------|-------------|
| 1 | Group | 1 | Top-level food domain |
| 2 | Family | 1 | Sub-domain within group |
| 3–4 | Food | 2 | Reserved discriminator (always `00` for now) |
| 5 | Form | 1 | Physical state |
| 6 | Processing | 1 | Preparation state |
| 7 | PType | 1 | Cut / shape / presentation |
| 8 | Check | 1 | Mod-37 check digit |

Alphabet for positions 1–7: **Crockford base32**  
`0123456789ABCDEFGHJKMNPQRSTVWXYZ`  
(Excludes I, L, O, U to avoid visual ambiguity.)

Check digit alphabet (37 chars):  
`0123456789ABCDEFGHJKMNPQRSTVWXYZ*~$=U`

### Check Digit Algorithm
1. Treat each of the first 7 chars as a digit in base-32 (using the Crockford alphabet index).
2. Compute the aggregate value: start at 0, for each char do `value = value * 32 + index(char)`.
3. Check digit = `CHECK_CHARS[value % 37]`.

---

## 2. Group Codes (Position 1)

| Code | Name | Typical Keywords |
|------|------|------------------|
| `1` | Dairy | milk, cheese, yogurt, butter, cream, ice cream |
| `2` | Red Meat | beef, pork, ham, bacon, steak, sausage, lamb, veal |
| `3` | Poultry | chicken, turkey, duck, poultry |
| `4` | Fish / Seafood | fish, salmon, tuna, shrimp, crab, seafood |
| `5` | Eggs | egg, eggs |
| `6` | Vegetables | vegetable, tomato, lettuce, carrot, onion, pepper, broccoli |
| `7` | Fruits | fruit, apple, berry, orange, banana, grape, melon |
| `8` | Grains | bread, pasta, rice, flour, cereal, oats, tortilla |
| `9` | Legumes | bean, beans, lentil, chickpea, hummus, edamame |
| `A` | Nuts & Seeds | nut, nuts, seed, seeds, almond, peanut, walnut, tahini |
| `B` | Oils & Fats | oil, shortening, lard, ghee, cooking spray, suet |
| `C` | Sugars & Sweeteners | sugar, honey, syrup, molasses, stevia, sweetener |
| `D` | Beverages | juice, soda, water, coffee, tea, beer, wine, spirit |
| `E` | Spices / Herbs / Seasonings | spice, herb, salt, pepper, cinnamon, cumin, basil, seasoning |
| `F` | Condiments / Sauces | mayonnaise, ketchup, mustard, dressing, salsa, vinegar, sauce |
| `G` | Baked Goods / Desserts | cookie, cake, pie, pastry, donut, brownie, cracker |
| `H` | Prepared Meals | frozen dinner, pizza, burrito, sandwich, soup, meal kit |
| `J` | Snacks / Candy | chip, pretzel, candy, chocolate, popcorn, granola bar |
| `K` | Supplements | vitamin, supplement, protein powder, nutritional yeast |
| `M` | Baby Food | baby, infant, toddler, formula |
| `N` | Non-Food | toothpick, napkin, soap, wax paper, aluminum foil, cleaner |

### Precedence Rules for Group
- **Spice-seed guard**: "coriander seeds", "cumin seeds", "mustard seeds" are **Spices (E)**, not Nuts/Seeds (A).
- **Oil guard**: "olive oil" is **Oils (B)**, not Vegetables (6).
- **Condiment guard**: "salad dressing", "pickles" are **Condiments (F)**, not Vegetables (6).
- **Poultry deli override**: Turkey/chicken + ham/bacon/sausage/deli/smoked/cured → **Poultry (3)**, not Red Meat (2).
- Non-food patterns short-circuit everything → `N`.

---

## 3. Family Codes (Position 2)

### Dairy (`1`)
| Code | Family |
|------|--------|
| `0` | Milk (default) |
| `1` | Cheese |
| `2` | Yogurt / Kefir |
| `3` | Cream / Half-and-Half / Whipped / Creamer |
| `4` | Butter / Margarine / Ghee |
| `5` | Ice Cream / Gelato / Sorbet / Frozen Yogurt |
| `6` | Sour Cream |
| `7` | Cottage Cheese |
| `8` | Cream Cheese |
| `9` | Whey / Protein |
| `A` | Plant Milk (almond, soy, oat, coconut, cashew) |
| `B` | Condensed / Evaporated Milk |

### Red Meat (`2`)
| Code | Family |
|------|--------|
| `0` | Beef / Steak |
| `1` | Pork (not ham/bacon/sausage) |
| `2` | Lamb |
| `3` | Veal |
| `4` | Cured / Deli / Ham / Bacon / Sausage / Pepperoni / Salami / Hot Dog |
| `5` | Game / Venison / Bison / Rabbit / Wild Boar |
| `6` | Offal / Liver / Kidney / Tongue / Tripe |

### Poultry (`3`)
| Code | Family |
|------|--------|
| `0` | Chicken |
| `1` | Turkey |
| `2` | Duck |

### Vegetables (`6`)
| Code | Family |
|------|--------|
| `0` | Leafy Greens (spinach, kale, lettuce, arugula, chard) |
| `1` | Root Vegetables (carrot, potato, beet, turnip, sweet potato, radish) |
| `2` | Brassicas (broccoli, cauliflower, cabbage, brussels, bok choy) |
| `3` | Beans & Peas (green bean, snap pea, snow pea, edamame) |
| `4` | Squash / Gourd (zucchini, pumpkin, squash) |
| `5` | Alliums (onion, garlic, leek, shallot, scallion, chive) |
| `6` | Peppers / Chiles (jalapeño, habanero, bell pepper, chili) |
| `7` | Tomatoes / Tomatillo |
| `8` | Corn |
| `9` | Mushrooms |
| `A` | Other Vegetables (celery, asparagus, cucumber, eggplant, okra, artichoke) |

### Fruits (`7`)
| Code | Family |
|------|--------|
| `0` | Pome (apple, pear, quince) |
| `1` | Banana / Plantain |
| `2` | Citrus (orange, lemon, lime, grapefruit, tangerine) |
| `3` | Berries (strawberry, blueberry, raspberry, cranberry) |
| `4` | Grapes / Raisins / Currants |
| `5` | Melons (watermelon, cantaloupe, honeydew) |
| `6` | Stone Fruits (peach, plum, cherry, apricot, nectarine) |
| `7` | Tropical (mango, pineapple, kiwi, papaya, guava, passion fruit) |
| `8` | Pomegranate / Fig / Date |
| `9` | Avocado / Coconut |

### Grains (`8`)
| Code | Family |
|------|--------|
| `0` | Bread / Bun / Roll / Crouton / Breadcrumb |
| `1` | Bagel |
| `2` | Flatbread / Tortilla / Wrap / Pita / Naan / Lavash |
| `3` | Pasta / Noodle / Macaroni / Spaghetti / Ramen / Dumpling Skin |
| `4` | Rice |
| `5` | Oats / Oatmeal |
| `6` | Cereal / Granola / Muesli |
| `7` | Flour / Baking Mix / Cornstarch / Wheat Germ / Semolina |
| `8` | Ancient / Other Grains (quinoa, couscous, barley, bulgur, farro, grits) |
| `9` | Pastry / Dough / Pie Crust / Pizza Dough / Phyllo / Wonton Wrapper |
| `A` | Ladyfinger / Sponge Cake / Biscotti |

### Spices / Herbs (`E`)
| Code | Family |
|------|--------|
| `0` | Salt (table, kosher, sea, fleur de sel, pickling, curing) |
| `1` | Pepper / Peppercorn |
| `2` | Warm Spices (cinnamon, nutmeg, allspice, clove, cardamom, mace, anise, saffron) |
| `3` | Herbs (basil, oregano, thyme, rosemary, parsley, cilantro, mint, sage, dill, bay leaf, lemongrass) |
| `4` | Exotic / Blended Spices (cumin, coriander, paprika, turmeric, chili powder, curry, ginger, garam masala, wasabi, horseradish) |
| `5` | Extracts / Flavorings (vanilla, almond extract, maple flavor, lemon zest, essence) |
| `6` | Seasoning Blends / Rubs (Italian seasoning, Cajun, Creole, adobo, jerk, Old Bay, za'atar, chaat masala) |
| `7` | Powdered Alliums / Seeds (garlic powder, onion powder, celery seed, fennel seed, poppy seed, sesame seed, mustard seed) |
| `8` | Baking Chemicals (baking soda, baking powder, yeast, cream of tartar, xanthan, cornstarch, pectin, gelatin, agar) |
| `9` | Cocoa / Cacao / Carob / Chocolate Powder |
| `B` | Umami / Specialty (liquid smoke, MSG, asafoetida/hing, sumac, amchur, kala namak/black salt) |

### Condiments (`F`)
| Code | Family |
|------|--------|
| `0` | Mayonnaise / Aioli / Miracle Whip |
| `1` | Ketchup / Catsup |
| `2` | Mustard |
| `3` | BBQ / Barbecue |
| `4` | Hot Sauce / Sriracha / Tabasco / Harissa / Chili Crisp / Gochujang |
| `5` | Asian Sauces (soy sauce, teriyaki, tamari, fish sauce, hoisin, oyster sauce, ponzu, Worcestershire) |
| `6` | Salsa / Guacamole / Pico de Gallo |
| `7` | Salad Dressing / Vinaigrette / Ranch / Caesar / Tzatziki / Tahini |
| `8` | Pasta / Cooking Sauce (marinara, alfredo, pesto, pizza sauce, gravy, stock, broth, demi-glace, dashi, bouillon) |
| `9` | Pickled / Fermented (pickle, relish, olive, sauerkraut, kimchi, capers, miso, tapenade) |
| `A` | Jams / Spreads / Preserves / Marmalade / Fruit Spread / Apple Butter / Nutella / Lemon Curd |
| `B` | Vinegar / Balsamic Glaze / Balsamic Reduction |

---

## 4. Form Codes (Position 5)

| Code | Meaning | Trigger Words |
|------|---------|---------------|
| `1` | Fresh / Refrigerated | fresh, refrigerated, pre-packaged, salad |
| `2` | Frozen | frozen |
| `3` | Canned / Jarred / Bottled | canned, jarred, bottled |
| `4` | Dried / Dehydrated | dried, dehydrated, dry |
| `5` | Powder / Instant / Mix | powder, powdered, instant, mix |
| `6` | Liquid | juice, drink, soda, water, milk, cream, liquid, oil, vinegar, sauce, broth |
| `8` | Smoked / Cured | smoked, cured |
| `9` | Pickled | pickle |
| `0` | Not detectable | default |

---

## 5. Processing Codes (Position 6)

| Code | Meaning | Trigger Words |
|------|---------|---------------|
| `1` | Raw / Uncooked | raw, uncooked, unseasoned |
| `3` | Cooked | cooked, roasted, baked, grilled, fried, boiled |
| `4` | Smoked / Cured / Aged | smoked, cured, aged, dry-aged |
| `5` | Fermented / Cultured | fermented, cultured, probiotic |
| `6` | Ready-to-Eat / Pre-cooked | ready to eat, fully cooked, pre-cooked, heat and serve |
| `7` | Ready-to-Cook | ready to cook, oven ready |
| `8` | Seasoned / Marinated / Flavored | seasoned, marinated, flavored, teriyaki, bbq |
| `9` | Breaded / Battered | breaded, battered, crust, panko |
| `A` | Fortified / Enriched | fortified, enriched, vitamin |
| `0` | Not detectable | default |

---

## 6. Product Type / Cut Codes (Position 7)

| Code | Meaning | Trigger Words |
|------|---------|---------------|
| `0` | Whole | whole |
| `1` | Sliced / Deli-cut / Shaved / Thin-cut | sliced, deli, shaved, thin-cut |
| `2` | Ground / Minced | ground, minced |
| `3` | Steak / Fillet / Chop / Cutlet / Loin | steak, fillet, chop, cutlet, loin |
| `4` | Block / Chunk | block, chunk |
| `5` | Shredded / Grated | shredded, grated |
| `6` | Spread | spread |
| `7` | Crumbled | crumble |
| `8` | Cubed / Diced | cubed, diced |
| `9` | Stick / String | stick, string |
| `A` | Wedge | wedge |
| `C` | Patty / Burger | patty, patties, burger |
| `D` | Strip / Tender / Nugget / Finger | strip, tender, nugget, finger |

---

## 7. Worked Examples

### Example A: "1/4 cup whole milk"
1. **Extract qty/unit**: qty=0.25, unit=cup, residual="whole milk"
2. **Group**: "milk" → Dairy → `1`
3. **Family**: "milk" (not cheese, yogurt, cream, etc.) → Milk → `0`
4. **Food**: `00`
5. **Form**: "milk" matches liquid → `6`
6. **Processing**: nothing → `0`
7. **PType**: nothing → `0`
8. **code_7** = `1` + `0` + `00` + `6` + `0` + `0` = `1006000`
9. **Check digit**: mod37 of base32(`1006000`) → compute → `?`
10. **Final**: `1006000?`

### Example B: "WHITE AMERICAN CHEESE SLICES"
1. **Group**: "cheese" → Dairy → `1`
2. **Family**: "cheese" → Cheese → `1`
3. **Food**: `00`
4. **Form**: no frozen/canned/dried/powder/liquid/fresh → `0`
5. **Processing**: nothing → `0`
6. **PType**: "slices" → Sliced → `1`
7. **code_7** = `1` + `1` + `00` + `0` + `0` + `1` = `1100001`
8. **Check digit**: mod37 → `?`
9. **Final**: `1100001?`

### Example C: "chipotle mayonnaise"
1. **Group**: "mayonnaise" → Condiments → `F`
2. **Family**: "mayonnaise" → Mayonnaise → `0`
3. **Food**: `00`
4. **Form**: no form word → `0`
5. **Processing**: "chipotle" implies flavored → `8` (seasoned/flavored)
6. **PType**: nothing → `0`
7. **code_7** = `F` + `0` + `00` + `0` + `8` + `0` = `F000080`
8. **Check digit**: mod37 → `?`
9. **Final**: `F000080?`

### Example D: "ground beef"
1. **Group**: "beef" → Red Meat → `2`
2. **Family**: "beef" → Beef → `0`
3. **Food**: `00`
4. **Form**: no form word → `0`
5. **Processing**: nothing → `0`
6. **PType**: "ground" → Ground/Minced → `2`
7. **code_7** = `2` + `0` + `00` + `0` + `0` + `2` = `2000002`
8. **Check digit**: mod37 → `?`
9. **Final**: `2000002?`

### Example E: "Kroger® Ground Cumin Shaker"
1. **Group**: "cumin" → Spices → `E` (spice-seed guard: cumin is a spice, not a nut)
2. **Family**: "cumin" → Exotic/Blended Spices → `4`
3. **Food**: `00`
4. **Form**: "ground" + spice context → Powder → `5` (or interpret as ground powder)
   *Note: for spices, "ground" usually means powder form → `5`*
5. **Processing**: nothing → `0`
6. **PType**: nothing → `0`
7. **code_7** = `E` + `4` + `00` + `5` + `0` + `0` = `E400500`
8. **Check digit**: mod37 → `?`
9. **Final**: `E400500?`

### Example F: "toothpick"
1. **Non-food check**: "toothpick" is explicitly non-food
2. **Short-circuit**: `N0000000`
3. **Check digit**: mod37(`N000000`) → compute
4. **Final**: `N000000?`

---

## 8. API Prompt Template

Paste this into your LLM call, then append the product/ingredient string:

```
You are an HTC encoder. Given a food product title or recipe ingredient, output an 8-character Hestia Taxonomy Code using this exact procedure:

STEP 1: If the item is clearly non-food (cleaning supplies, paper goods, candles, soap, pet food, cosmetics, decorations), output code N0000000 and stop.

STEP 2: Determine Group (pos 1) using the Group table. Apply these guards in order:
- Spice-seeds (coriander/cumin/fennel/mustard/poppy/sesame seeds) are Group E, not A.
- "Olive oil" and similar oils are Group B, not 6.
- "Salad dressing", "pickles", "olives", "relish" are Group F, not 6.
- Turkey/chicken + ham/bacon/sausage/deli/smoked/cured → Group 3, not 2.

STEP 3: Determine Family (pos 2) using the Family table for that Group.

STEP 4: Food (pos 3-4) is always 00.

STEP 5: Determine Form (pos 5). For spices, "ground" usually means powder (5). For meats, "frozen" overrides other forms.

STEP 6: Determine Processing (pos 6). "Chipotle", "garlic", "rosemary" in a sauce/condiment implies flavored/seasoned (8). "Smoked" salmon is smoked/cured (4).

STEP 7: Determine PType (pos 7). Only the most specific cut word counts.

STEP 8: Compute check digit: treat first 7 chars as base-32 digits using Crockford alphabet "0123456789ABCDEFGHJKMNPQRSTVWXYZ". Aggregate = (((((d1*32+d2)*32+d3)*32+d4)*32+d5)*32+d6)*32+d7. Check = CHECK_CHARS[Aggregate % 37] where CHECK_CHARS = "0123456789ABCDEFGHJKMNPQRSTVWXYZ*~$=U".

STEP 9: Output ONLY the 8-character code, no explanation.

Now encode: "{{PRODUCT_OR_INGREDIENT_STRING}}"
```

---

*Total size: ~200 lines. Enough for an LLM to classify any grocery product or recipe ingredient deterministically.*
