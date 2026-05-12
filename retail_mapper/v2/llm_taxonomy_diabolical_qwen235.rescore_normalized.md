# Re-score diff: llm_taxonomy_diabolical_qwen235.live.jsonl

normalizer=on, core=5/17, exact=1/17

## diabolical_gluten_free_chocolate_chip_cookies
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Cookies"` | `"Snack > Cookies"` |
| `product_identity` | `"Cookies"` | `"Cookies"` |
| `canonical_path` | `"Snack > Cookies > Cookies"` | `"Snack > Cookies > Cookies"` |
| `variant` * | `[]` | `["chocolate_chip"]` |
| `flavor` * | `["chocolate_chip"]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `["gluten_free"]` | `["gluten_free"]` |
| `canonical_label` | `"Cookies (Chocolate Chip, Gluten Free)"` | `"Cookies (Chocolate Chip, Gluten Free)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Cookies > Cookies", "Retail Taxonomy > Snack > Cookies > Cookies > @flavor > chocolate_chip", "Retail Taxonomy > Snack > Cookies > Cookies > @claims > gluten_free"]` | `["Retail Taxonomy > Snack > Cookies > Cookies", "Retail Taxonomy > Snack > Cookies > Cookies > @variant > chocolate_chip", "Retail Taxonomy > Snack > Cookies > Cookies > @claims > gluten_free"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['chocolate_chip']`
- `core_mismatch:flavor:expected=['chocolate_chip']:actual=[]`

**exact errors:**
- `mismatch:variant:expected=[]:actual=['chocolate_chip']`
- `mismatch:flavor:expected=['chocolate_chip']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Cookies > Cookies', 'Retail Taxonomy > Snack > Cookies > Cookies > @flavor > chocolate_chip', 'Retail Taxonomy > Snack > Cookies > Cookies > @claims > gluten_free']:actual=['Retail Taxonomy > Snack > Cookies > Cookies', 'Retail Taxonomy > Snack > Cookies > Cookies > @variant > chocolate_chip', 'Retail Taxonomy > Snack > Cookies > Cookies > @claims > gluten_free']`

---

## diabolical_organic_low_sodium_chicken_broth_claim_order
- core: **PASS**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Broth & Stock"` | `"Pantry > Broth & Stock"` |
| `product_identity` | `"Chicken Broth"` | `"Chicken Broth"` |
| `canonical_path` | `"Pantry > Broth & Stock > Chicken Broth"` | `"Pantry > Broth & Stock > Chicken Broth"` |
| `variant` | `[]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `["low_sodium", "organic"]` | `["low_sodium", "organic"]` |
| `canonical_label` | `"Chicken Broth (Low Sodium, Organic)"` | `"Chicken Broth (Low Sodium, Organic)"` |
| `tree_paths` | `["Retail Taxonomy > Pantry > Broth & Stock > Chicken Broth", "Retail Taxonomy > Pantry > Broth & Stock > Chicken Broth > @claims > low_sodium", "Retail Taxonomy > Pantry > Broth & Stock > Chicken Broth > @claims > organic"]` | `["Retail Taxonomy > Pantry > Broth & Stock > Chicken Broth", "Retail Taxonomy > Pantry > Broth & Stock > Chicken Broth > @claims > low_sodium", "Retail Taxonomy > Pantry > Broth & Stock > Chicken Broth > @claims > organic"]` |
| `components` | `[]` | `[]` |

**exact errors:**
- `mismatch:mint_required:expected=True:actual=False`

---

## diabolical_whole_peeled_tomatoes_basil
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Canned Vegetables"` | `"Pantry > Canned Vegetables"` |
| `product_identity` | `"Tomatoes"` | `"Tomatoes"` |
| `canonical_path` | `"Pantry > Canned Vegetables > Tomatoes"` | `"Pantry > Canned Vegetables > Tomatoes"` |
| `variant` * | `[]` | `["whole_peeled"]` |
| `flavor` | `["basil"]` | `["basil"]` |
| `form_texture_cut` * | `["whole_peeled"]` | `[]` |
| `processing_storage` | `["canned"]` | `["canned"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Tomatoes (Basil, Whole Peeled, Canned)"` | `"Tomatoes (Whole Peeled, Basil, Canned)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes", "Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @flavor > basil", "Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @form_texture_cut > whole_peeled", "Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @processing_storage > canned"]` | `["Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes", "Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @variant > whole_peeled", "Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @flavor > basil", "Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @processing_storage > canned"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['whole_peeled']`
- `core_mismatch:form_texture_cut:expected=['whole_peeled']:actual=[]`

**exact errors:**
- `mismatch:canonical_label:expected='Tomatoes (Basil, Whole Peeled, Canned)':actual='Tomatoes (Whole Peeled, Basil, Canned)'`
- `mismatch:variant:expected=[]:actual=['whole_peeled']`
- `mismatch:form_texture_cut:expected=['whole_peeled']:actual=[]`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes', 'Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @flavor > basil', 'Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @form_texture_cut > whole_peeled', 'Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @processing_storage > canned']:actual=['Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes', 'Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @variant > whole_peeled', 'Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @flavor > basil', 'Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @processing_storage > canned']`

---

## diabolical_honey_mustard_pretzel_pieces
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Pretzels"` | `"Snack > Pretzels"` |
| `product_identity` * | `"Pretzels"` | `"Pretzel Pieces"` |
| `canonical_path` * | `"Snack > Pretzels > Pretzels"` | `"Snack > Pretzels > Pretzel Pieces"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["honey_mustard"]` | `["honey_mustard"]` |
| `form_texture_cut` | `["pieces"]` | `["pieces"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Pretzels (Honey Mustard, Pieces)"` | `"Pretzel Pieces (Honey Mustard, Pieces)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Pretzels > Pretzels", "Retail Taxonomy > Snack > Pretzels > Pretzels > @flavor > honey_mustard", "Retail Taxonomy > Snack > Pretzels > Pretzels > @form_texture_cut > pieces"]` | `["Retail Taxonomy > Snack > Pretzels > Pretzel Pieces", "Retail Taxonomy > Snack > Pretzels > Pretzel Pieces > @flavor > honey_mustard", "Retail Taxonomy > Snack > Pretzels > Pretzel Pieces > @form_texture_cut > pieces"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Pretzels':actual='Pretzel Pieces'`
- `core_mismatch:canonical_path:expected='Snack > Pretzels > Pretzels':actual='Snack > Pretzels > Pretzel Pieces'`

**exact errors:**
- `mismatch:product_identity:expected='Pretzels':actual='Pretzel Pieces'`
- `mismatch:canonical_path:expected='Snack > Pretzels > Pretzels':actual='Snack > Pretzels > Pretzel Pieces'`
- `mismatch:canonical_label:expected='Pretzels (Honey Mustard, Pieces)':actual='Pretzel Pieces (Honey Mustard, Pieces)'`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Pretzels > Pretzels', 'Retail Taxonomy > Snack > Pretzels > Pretzels > @flavor > honey_mustard', 'Retail Taxonomy > Snack > Pretzels > Pretzels > @form_texture_cut > pieces']:actual=['Retail Taxonomy > Snack > Pretzels > Pretzel Pieces', 'Retail Taxonomy > Snack > Pretzels > Pretzel Pieces > @flavor > honey_mustard', 'Retail Taxonomy > Snack > Pretzels > Pretzel Pieces > @form_texture_cut > pieces']`

---

## diabolical_everything_bagel_seasoning
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Pantry > Spices & Seasonings"` | `"Pantry > Seasoning & Spices"` |
| `product_identity` * | `"Seasoning"` | `"Seasoning Mix"` |
| `canonical_path` * | `"Pantry > Spices & Seasonings > Seasoning"` | `"Pantry > Seasoning & Spices > Seasoning Mix"` |
| `variant` | `["everything_bagel"]` | `["everything_bagel"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Seasoning (Everything Bagel)"` | `"Seasoning Mix (Everything Bagel)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > everything_bagel"]` | `["Retail Taxonomy > Pantry > Seasoning & Spices > Seasoning Mix", "Retail Taxonomy > Pantry > Seasoning & Spices > Seasoning Mix > @variant > everything_bagel"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Pantry > Spices & Seasonings':actual='Pantry > Seasoning & Spices'`
- `core_mismatch:product_identity:expected='Seasoning':actual='Seasoning Mix'`
- `core_mismatch:canonical_path:expected='Pantry > Spices & Seasonings > Seasoning':actual='Pantry > Seasoning & Spices > Seasoning Mix'`

**exact errors:**
- `mismatch:category_path:expected='Pantry > Spices & Seasonings':actual='Pantry > Seasoning & Spices'`
- `mismatch:product_identity:expected='Seasoning':actual='Seasoning Mix'`
- `mismatch:canonical_path:expected='Pantry > Spices & Seasonings > Seasoning':actual='Pantry > Seasoning & Spices > Seasoning Mix'`
- `mismatch:canonical_label:expected='Seasoning (Everything Bagel)':actual='Seasoning Mix (Everything Bagel)'`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > everything_bagel']:actual=['Retail Taxonomy > Pantry > Seasoning & Spices > Seasoning Mix', 'Retail Taxonomy > Pantry > Seasoning & Spices > Seasoning Mix > @variant > everything_bagel']`

---

## diabolical_gluten_free_almond_flour_tortillas
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Pantry > Tortillas"` | `"Pantry > Baking & Bread"` |
| `product_identity` * | `"Tortillas"` | `"Tortilla"` |
| `canonical_path` * | `"Pantry > Tortillas > Tortillas"` | `"Pantry > Baking & Bread > Tortilla"` |
| `variant` | `["almond_flour"]` | `["almond_flour"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `["gluten_free"]` | `["gluten_free"]` |
| `canonical_label` * | `"Tortillas (Almond Flour, Gluten Free)"` | `"Tortilla (Almond Flour, Gluten Free)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Tortillas > Tortillas", "Retail Taxonomy > Pantry > Tortillas > Tortillas > @variant > almond_flour", "Retail Taxonomy > Pantry > Tortillas > Tortillas > @claims > gluten_free", "Retail Taxonomy > Pantry > Tortillas > Tortillas > @components > almond_flour"]` | `["Retail Taxonomy > Pantry > Baking & Bread > Tortilla", "Retail Taxonomy > Pantry > Baking & Bread > Tortilla > @variant > almond_flour", "Retail Taxonomy > Pantry > Baking & Bread > Tortilla > @claims > gluten_free"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Almond Flour", "processing_storage": [], "role": "ingredient", "variant": []}]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Pantry > Tortillas':actual='Pantry > Baking & Bread'`
- `core_mismatch:product_identity:expected='Tortillas':actual='Tortilla'`
- `core_mismatch:canonical_path:expected='Pantry > Tortillas > Tortillas':actual='Pantry > Baking & Bread > Tortilla'`
- `core_mismatch:component_identities:expected=['almond_flour']:actual=[]`

**exact errors:**
- `mismatch:category_path:expected='Pantry > Tortillas':actual='Pantry > Baking & Bread'`
- `mismatch:product_identity:expected='Tortillas':actual='Tortilla'`
- `mismatch:canonical_path:expected='Pantry > Tortillas > Tortillas':actual='Pantry > Baking & Bread > Tortilla'`
- `mismatch:canonical_label:expected='Tortillas (Almond Flour, Gluten Free)':actual='Tortilla (Almond Flour, Gluten Free)'`
- `mismatch:components:expected=[{'identity': 'Almond Flour', 'role': 'ingredient', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[]`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Tortillas > Tortillas', 'Retail Taxonomy > Pantry > Tortillas > Tortillas > @variant > almond_flour', 'Retail Taxonomy > Pantry > Tortillas > Tortillas > @claims > gluten_free', 'Retail Taxonomy > Pantry > Tortillas > Tortillas > @components > almond_flour']:actual=['Retail Taxonomy > Pantry > Baking & Bread > Tortilla', 'Retail Taxonomy > Pantry > Baking & Bread > Tortilla > @variant > almond_flour', 'Retail Taxonomy > Pantry > Baking & Bread > Tortilla > @claims > gluten_free']`

---

## diabolical_pineapple_coconut_water
- core: **PASS**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Beverage > Coconut Water"` | `"Beverage > Coconut Water"` |
| `product_identity` | `"Coconut Water"` | `"Coconut Water"` |
| `canonical_path` | `"Beverage > Coconut Water > Coconut Water"` | `"Beverage > Coconut Water > Coconut Water"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["pineapple"]` | `["pineapple"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Coconut Water (Pineapple)"` | `"Coconut Water (Pineapple)"` |
| `tree_paths` | `["Retail Taxonomy > Beverage > Coconut Water > Coconut Water", "Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @flavor > pineapple"]` | `["Retail Taxonomy > Beverage > Coconut Water > Coconut Water", "Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @flavor > pineapple"]` |
| `components` | `[]` | `[]` |

**exact errors:**
- `mismatch:mint_required:expected=True:actual=False`

---

## diabolical_spinach_artichoke_dip_components
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Dips & Spreads"` | `"Pantry > Dips & Spreads"` |
| `product_identity` | `"Dip"` | `"Dip"` |
| `canonical_path` | `"Pantry > Dips & Spreads > Dip"` | `"Pantry > Dips & Spreads > Dip"` |
| `variant` | `["spinach_artichoke"]` | `["spinach_artichoke"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Dip (Spinach Artichoke)"` | `"Dip (Spinach Artichoke)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Dips & Spreads > Dip", "Retail Taxonomy > Pantry > Dips & Spreads > Dip > @variant > spinach_artichoke", "Retail Taxonomy > Pantry > Dips & Spreads > Dip > @components > spinach", "Retail Taxonomy > Pantry > Dips & Spreads > Dip > @components > artichoke"]` | `["Retail Taxonomy > Pantry > Dips & Spreads > Dip", "Retail Taxonomy > Pantry > Dips & Spreads > Dip > @variant > spinach_artichoke"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Spinach", "processing_storage": [], "role": "ingredient", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Artichoke", "processing_storage": [], "role": "ingredient", "variant": []}]` | `[]` |

**core errors:**
- `core_mismatch:component_identities:expected=['artichoke', 'spinach']:actual=[]`

**exact errors:**
- `mismatch:components:expected=[{'identity': 'Spinach', 'role': 'ingredient', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Artichoke', 'role': 'ingredient', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[]`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Dips & Spreads > Dip', 'Retail Taxonomy > Pantry > Dips & Spreads > Dip > @variant > spinach_artichoke', 'Retail Taxonomy > Pantry > Dips & Spreads > Dip > @components > spinach', 'Retail Taxonomy > Pantry > Dips & Spreads > Dip > @components > artichoke']:actual=['Retail Taxonomy > Pantry > Dips & Spreads > Dip', 'Retail Taxonomy > Pantry > Dips & Spreads > Dip > @variant > spinach_artichoke']`

---

## diabolical_broccoli_cheddar_soup_not_cheese
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Soup"` | `"Pantry > Soup"` |
| `product_identity` | `"Broccoli Cheddar Soup"` | `"Broccoli Cheddar Soup"` |
| `canonical_path` | `"Pantry > Soup > Broccoli Cheddar Soup"` | `"Pantry > Soup > Broccoli Cheddar Soup"` |
| `variant` | `[]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Broccoli Cheddar Soup"` | `"Broccoli Cheddar Soup"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Soup > Broccoli Cheddar Soup", "Retail Taxonomy > Pantry > Soup > Broccoli Cheddar Soup > @components > broccoli", "Retail Taxonomy > Pantry > Soup > Broccoli Cheddar Soup > @components > cheddar_cheese"]` | `["Retail Taxonomy > Pantry > Soup > Broccoli Cheddar Soup"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Broccoli", "processing_storage": [], "role": "ingredient", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Cheddar Cheese", "processing_storage": [], "role": "ingredient", "variant": []}]` | `[]` |

**core errors:**
- `core_mismatch:component_identities:expected=['broccoli', 'cheddar_cheese']:actual=[]`

**exact errors:**
- `mismatch:components:expected=[{'identity': 'Broccoli', 'role': 'ingredient', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Cheddar Cheese', 'role': 'ingredient', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[]`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Soup > Broccoli Cheddar Soup', 'Retail Taxonomy > Pantry > Soup > Broccoli Cheddar Soup > @components > broccoli', 'Retail Taxonomy > Pantry > Soup > Broccoli Cheddar Soup > @components > cheddar_cheese']:actual=['Retail Taxonomy > Pantry > Soup > Broccoli Cheddar Soup']`

---

## diabolical_pizza_crust_mix_not_pizza
- core: **PASS**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Baking Mixes"` | `"Pantry > Baking Mixes"` |
| `product_identity` | `"Pizza Crust Mix"` | `"Pizza Crust Mix"` |
| `canonical_path` | `"Pantry > Baking Mixes > Pizza Crust Mix"` | `"Pantry > Baking Mixes > Pizza Crust Mix"` |
| `variant` | `[]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `["gluten_free"]` | `["gluten_free"]` |
| `canonical_label` | `"Pizza Crust Mix (Gluten Free)"` | `"Pizza Crust Mix (Gluten Free)"` |
| `tree_paths` | `["Retail Taxonomy > Pantry > Baking Mixes > Pizza Crust Mix", "Retail Taxonomy > Pantry > Baking Mixes > Pizza Crust Mix > @claims > gluten_free"]` | `["Retail Taxonomy > Pantry > Baking Mixes > Pizza Crust Mix", "Retail Taxonomy > Pantry > Baking Mixes > Pizza Crust Mix > @claims > gluten_free"]` |
| `components` | `[]` | `[]` |

**exact errors:**
- `mismatch:mint_required:expected=True:actual=False`

---

## diabolical_protein_parfait_not_cereal
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"composite_dish"` | `"composite_dish"` |
| `category_path` | `"Meal > Composite Dishes"` | `"Meal > Composite Dishes"` |
| `product_identity` * | `"Parfait"` | `"Protein Parfait"` |
| `canonical_path` * | `"Meal > Composite Dishes > Parfait"` | `"Meal > Composite Dishes > Protein Parfait"` |
| `variant` * | `[]` | `["cinnamon_granola_topping", "apple_dices", "coconut_pudding"]` |
| `flavor` | `["cinnamon", "apple", "coconut"]` | `["cinnamon", "apple", "coconut"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `[]` | `["canned"]` |
| `claims` | `["high_protein"]` | `["high_protein"]` |
| `canonical_label` * | `"Parfait (Cinnamon, Apple, Coconut, High Protein)"` | `"Protein Parfait (Cinnamon Granola Topping, Apple Dices, Coconut Pudding, Cinnamon, Apple, Coconut, Canned, High Protein)"` |
| `tree_paths` * | `["Retail Taxonomy > Meal > Composite Dishes > Parfait", "Retail Taxonomy > Meal > Composite Dishes > Parfait > @flavor > cinnamon", "Retail Taxonomy > Meal > Composite Dishes > Parfait > @flavor > apple", "Retail Taxonomy > Meal > Composite Dishes > Parfait > @flavor > coconut", "Retail Taxonomy > Meal > Composite Dishes > Parfait > @claims > high_protein", "Retail Taxonomy > Meal > Composite Dishes > Parfait > @components > granola_topping", "Retail Taxonomy > Meal > Composite Dishes > Parfait > @components > apple", "Retail Taxonomy > Meal > Composite Dishes > Parfait > @components > coconut_pudding"]` | `["Retail Taxonomy > Meal > Composite Dishes > Protein Parfait", "Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @variant > cinnamon_granola_topping", "Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @variant > apple_dices", "Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @variant > coconut_pudding", "Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @flavor > cinnamon", "Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @flavor > apple", "Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @flavor > coconut", "Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @processing_storage > canned", "Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @claims > high_protein", "Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @components > cinnamon_granola_topping", "Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @components > apple_dices_in_sauce", "Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @components > coconut_pudding"]` |
| `components` * | `[{"claims": [], "flavor": ["cinnamon"], "form_texture_cut": [], "identity": "Granola Topping", "processing_storage": [], "role": "topping", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": ["dices"], "identity": "Apple", "processing_storage": ["in_sauce"], "role": "fruit", "variant": []}, {"claims": [], "flavor": ["coconut"], "form_texture_cut": [], "identity": "Coconut Pudding", "processing_storage": [], "role": "base", "variant": []}]` | `[{"claims": [], "flavor": ["cinnamon"], "form_texture_cut": [], "identity": "Cinnamon Granola Topping", "processing_storage": [], "role": "topping", "variant": []}, {"claims": [], "flavor": ["apple"], "form_texture_cut": ["diced"], "identity": "Apple Dices in Sauce", "processing_storage": [], "role": "filling", "variant": []}, {"claims": ["high_protein"], "flavor": ["coconut"], "form_texture_cut": ["pudding"], "identity": "Coconut Pudding", "processing_storage": [], "role": "base", "variant": []}]` |

**core errors:**
- `core_mismatch:product_identity:expected='Parfait':actual='Protein Parfait'`
- `core_mismatch:canonical_path:expected='Meal > Composite Dishes > Parfait':actual='Meal > Composite Dishes > Protein Parfait'`
- `core_mismatch:variant:expected=[]:actual=['cinnamon_granola_topping', 'apple_dices', 'coconut_pudding']`
- `core_mismatch:processing_storage:expected=[]:actual=['canned']`
- `core_mismatch:component_identities:expected=['apple', 'coconut_pudding', 'granola_topping']:actual=['apple_dices_in_sauce', 'cinnamon_granola_topping', 'coconut_pudding']`

**exact errors:**
- `mismatch:product_identity:expected='Parfait':actual='Protein Parfait'`
- `mismatch:canonical_path:expected='Meal > Composite Dishes > Parfait':actual='Meal > Composite Dishes > Protein Parfait'`
- `mismatch:canonical_label:expected='Parfait (Cinnamon, Apple, Coconut, High Protein)':actual='Protein Parfait (Cinnamon Granola Topping, Apple Dices, Coconut Pudding, Cinnamon, Apple, Coconut, Canned, High Protein)'`
- `mismatch:variant:expected=[]:actual=['cinnamon_granola_topping', 'apple_dices', 'coconut_pudding']`
- `mismatch:processing_storage:expected=[]:actual=['canned']`
- `mismatch:components:expected=[{'identity': 'Granola Topping', 'role': 'topping', 'variant': [], 'flavor': ['cinnamon'], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Apple', 'role': 'fruit', 'variant': [], 'flavor': [], 'form_texture_cut': ['dices'], 'processing_storage': ['in_sauce'], 'claims': []}, {'identity': 'Coconut Pudding', 'role': 'base', 'variant': [], 'flavor': ['coconut'], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[{'identity': 'Cinnamon Granola Topping', 'role': 'topping', 'variant': [], 'flavor': ['cinnamon'], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Apple Dices in Sauce', 'role': 'filling', 'variant': [], 'flavor': ['apple'], 'form_texture_cut': ['diced'], 'processing_storage': [], 'claims': []}, {'identity': 'Coconut Pudding', 'role': 'base', 'variant': [], 'flavor': ['coconut'], 'form_texture_cut': ['pudding'], 'processing_storage': [], 'claims': ['high_protein']}]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Meal > Composite Dishes > Parfait', 'Retail Taxonomy > Meal > Composite Dishes > Parfait > @flavor > cinnamon', 'Retail Taxonomy > Meal > Composite Dishes > Parfait > @flavor > apple', 'Retail Taxonomy > Meal > Composite Dishes > Parfait > @flavor > coconut', 'Retail Taxonomy > Meal > Composite Dishes > Parfait > @claims > high_protein', 'Retail Taxonomy > Meal > Composite Dishes > Parfait > @components > granola_topping', 'Retail Taxonomy > Meal > Composite Dishes > Parfait > @components > apple', 'Retail Taxonomy > Meal > Composite Dishes > Parfait > @components > coconut_pudding']:actual=['Retail Taxonomy > Meal > Composite Dishes > Protein Parfait', 'Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @variant > cinnamon_granola_topping', 'Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @variant > apple_dices', 'Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @variant > coconut_pudding', 'Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @flavor > cinnamon', 'Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @flavor > apple', 'Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @flavor > coconut', 'Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @processing_storage > canned', 'Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @claims > high_protein', 'Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @components > cinnamon_granola_topping', 'Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @components > apple_dices_in_sauce', 'Retail Taxonomy > Meal > Composite Dishes > Protein Parfait > @components > coconut_pudding']`

---

## diabolical_chicken_burgers_not_cheese_or_vegetarian
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"single"` | `"composite_dish"` |
| `category_path` | `"Meat & Seafood > Poultry"` | `"Meat & Seafood > Poultry"` |
| `product_identity` | `"Chicken Burgers"` | `"Chicken Burgers"` |
| `canonical_path` | `"Meat & Seafood > Poultry > Chicken Burgers"` | `"Meat & Seafood > Poultry > Chicken Burgers"` |
| `variant` | `["red_pepper_feta"]` | `["red_pepper_feta"]` |
| `flavor` * | `[]` | `["seasoned"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `["seasoned"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Chicken Burgers (Red Pepper Feta, Seasoned)"` | `"Chicken Burgers (Red Pepper Feta, Seasoned, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @variant > red_pepper_feta", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @processing_storage > seasoned"]` | `["Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @variant > red_pepper_feta", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @flavor > seasoned", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @processing_storage > frozen", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @components > chicken", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @components > seasoned_breadcrumbs", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @components > feta_cheese", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @components > red_peppers"]` |
| `components` * | `[]` | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Chicken", "processing_storage": [], "role": "protein", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Seasoned Breadcrumbs", "processing_storage": [], "role": "coating", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Feta Cheese", "processing_storage": [], "role": "cheese", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Red Peppers", "processing_storage": [], "role": "produce", "variant": []}]` |

**core errors:**
- `core_mismatch:retail_type:expected='single':actual='composite_dish'`
- `core_mismatch:flavor:expected=[]:actual=['seasoned']`
- `core_mismatch:processing_storage:expected=['seasoned']:actual=['frozen']`
- `core_mismatch:component_identities:expected=[]:actual=['chicken', 'feta_cheese', 'red_peppers', 'seasoned_breadcrumbs']`

**exact errors:**
- `mismatch:retail_type:expected='single':actual='composite_dish'`
- `mismatch:canonical_label:expected='Chicken Burgers (Red Pepper Feta, Seasoned)':actual='Chicken Burgers (Red Pepper Feta, Seasoned, Frozen)'`
- `mismatch:flavor:expected=[]:actual=['seasoned']`
- `mismatch:processing_storage:expected=['seasoned']:actual=['frozen']`
- `mismatch:components:expected=[]:actual=[{'identity': 'Chicken', 'role': 'protein', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Seasoned Breadcrumbs', 'role': 'coating', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Feta Cheese', 'role': 'cheese', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Red Peppers', 'role': 'produce', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @variant > red_pepper_feta', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @processing_storage > seasoned']:actual=['Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @variant > red_pepper_feta', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @flavor > seasoned', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @processing_storage > frozen', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @components > chicken', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @components > seasoned_breadcrumbs', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @components > feta_cheese', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Burgers > @components > red_peppers']`

---

## diabolical_vague_tuscan_meat_cheese_infer_sandwich
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"composite_dish"` | `"composite_dish"` |
| `category_path` | `"Meal > Sandwiches"` | `"Meal > Sandwiches"` |
| `product_identity` | `"Sandwich"` | `"Sandwich"` |
| `canonical_path` | `"Meal > Sandwiches > Sandwich"` | `"Meal > Sandwiches > Sandwich"` |
| `variant` * | `["tuscan_meat_cheese"]` | `["tuscan", "meat", "cheese", "provolone", "smoked_ham", "mortadella", "tomato"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["french_roll"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Sandwich (Tuscan Meat Cheese)"` | `"Sandwich (Tuscan, Meat, Cheese, Provolone, Smoked Ham, Mortadella, Tomato, French Roll)"` |
| `tree_paths` * | `["Retail Taxonomy > Meal > Sandwiches > Sandwich", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > tuscan_meat_cheese", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > french_roll", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > provolone_cheese", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > smoked_ham", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > mortadella", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > tomato"]` | `["Retail Taxonomy > Meal > Sandwiches > Sandwich", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > tuscan", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > meat", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > cheese", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > provolone", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > smoked_ham", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > mortadella", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > tomato", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @form_texture_cut > french_roll", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > french_roll", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > provolone_cheese", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > smoked_ham", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > mortadella", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > tomato"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "French Roll", "processing_storage": [], "role": "bread", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Provolone Cheese", "processing_storage": [], "role": "cheese", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Smoked Ham", "processing_storage": ["smoked"], "role": "protein", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Mortadella", "processing_storage": [], "role": "protein", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Tomato", "processing_storage": [], "role": "topping", "variant": []}]` | `[{"claims": [], "flavor": [], "form_texture_cut": ["roll"], "identity": "French Roll", "processing_storage": [], "role": "bread", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Provolone Cheese", "processing_storage": [], "role": "cheese", "variant": []}, {"claims": [], "flavor": ["maple", "honey"], "form_texture_cut": [], "identity": "Smoked Ham", "processing_storage": [], "role": "protein", "variant": ["smoked"]}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Mortadella", "processing_storage": [], "role": "protein", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": ["sliced"], "identity": "Tomato", "processing_storage": [], "role": "topping", "variant": []}]` |

**core errors:**
- `core_mismatch:variant:expected=['tuscan_meat_cheese']:actual=['tuscan', 'meat', 'cheese', 'provolone', 'smoked_ham', 'mortadella', 'tomato']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['french_roll']`

**exact errors:**
- `mismatch:canonical_label:expected='Sandwich (Tuscan Meat Cheese)':actual='Sandwich (Tuscan, Meat, Cheese, Provolone, Smoked Ham, Mortadella, Tomato, French Roll)'`
- `mismatch:variant:expected=['tuscan_meat_cheese']:actual=['tuscan', 'meat', 'cheese', 'provolone', 'smoked_ham', 'mortadella', 'tomato']`
- `mismatch:form_texture_cut:expected=[]:actual=['french_roll']`
- `mismatch:components:expected=[{'identity': 'French Roll', 'role': 'bread', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Provolone Cheese', 'role': 'cheese', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Smoked Ham', 'role': 'protein', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': ['smoked'], 'claims': []}, {'identity': 'Mortadella', 'role': 'protein', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Tomato', 'role': 'topping', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[{'identity': 'French Roll', 'role': 'bread', 'variant': [], 'flavor': [], 'form_texture_cut': ['roll'], 'processing_storage': [], 'claims': []}, {'identity': 'Provolone Cheese', 'role': 'cheese', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Smoked Ham', 'role': 'protein', 'variant': ['smoked'], 'flavor': ['maple', 'honey'], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Mortadella', 'role': 'protein', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Tomato', 'role': 'topping', 'variant': [], 'flavor': [], 'form_texture_cut': ['sliced'], 'processing_storage': [], 'claims': []}]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Meal > Sandwiches > Sandwich', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > tuscan_meat_cheese', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > french_roll', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > provolone_cheese', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > smoked_ham', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > mortadella', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > tomato']:actual=['Retail Taxonomy > Meal > Sandwiches > Sandwich', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > tuscan', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > meat', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > cheese', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > provolone', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > smoked_ham', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > mortadella', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > tomato', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @form_texture_cut > french_roll', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > french_roll', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > provolone_cheese', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > smoked_ham', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > mortadella', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > tomato']`

---

## diabolical_hard_aged_cheese_no_unproven_specific_guess
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Dairy > Cheese"` | `"Dairy > Cheese"` |
| `product_identity` | `"Cheese"` | `"Cheese"` |
| `canonical_path` | `"Dairy > Cheese > Cheese"` | `"Dairy > Cheese > Cheese"` |
| `variant` | `["aged"]` | `["aged"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `["hard"]` | `["hard"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Cheese (Aged, Hard)"` | `"Cheese (Aged, Hard)"` |
| `tree_paths` | `["Retail Taxonomy > Dairy > Cheese > Cheese", "Retail Taxonomy > Dairy > Cheese > Cheese > @variant > aged", "Retail Taxonomy > Dairy > Cheese > Cheese > @form_texture_cut > hard"]` | `["Retail Taxonomy > Dairy > Cheese > Cheese", "Retail Taxonomy > Dairy > Cheese > Cheese > @variant > aged", "Retail Taxonomy > Dairy > Cheese > Cheese > @form_texture_cut > hard"]` |
| `components` | `[]` | `[]` |

---

## diabolical_hatch_green_chile_asiago_cheese_crisps
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"single"` | `"composite_dish"` |
| `category_path` | `"Snack > Cheese Crisps"` | `"Snack > Cheese Crisps"` |
| `product_identity` | `"Cheese Crisps"` | `"Cheese Crisps"` |
| `canonical_path` | `"Snack > Cheese Crisps > Cheese Crisps"` | `"Snack > Cheese Crisps > Cheese Crisps"` |
| `variant` | `["asiago"]` | `["asiago"]` |
| `flavor` | `["hatch_green_chile"]` | `["hatch_green_chile"]` |
| `form_texture_cut` * | `[]` | `["crisps"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["100_real"]` |
| `canonical_label` * | `"Cheese Crisps (Asiago, Hatch Green Chile)"` | `"Cheese Crisps (Asiago, Hatch Green Chile, Crisps, 100 Real)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps", "Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @variant > asiago", "Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @flavor > hatch_green_chile"]` | `["Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps", "Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @variant > asiago", "Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @flavor > hatch_green_chile", "Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @form_texture_cut > crisps", "Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @claims > 100_real", "Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @components > smoked_sausage", "Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @components > asiago_cheese"]` |
| `components` * | `[]` | `[{"claims": [], "flavor": ["hatch_green_chile"], "form_texture_cut": ["diced"], "identity": "Smoked Sausage", "processing_storage": ["smoked"], "role": "ingredient", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Asiago Cheese", "processing_storage": ["pasteurized_part_skimmed"], "role": "ingredient", "variant": []}]` |

**core errors:**
- `core_mismatch:retail_type:expected='single':actual='composite_dish'`
- `core_mismatch:form_texture_cut:expected=[]:actual=['crisps']`
- `core_mismatch:claims:expected=[]:actual=['100_real']`
- `core_mismatch:component_identities:expected=[]:actual=['asiago_cheese', 'smoked_sausage']`

**exact errors:**
- `mismatch:retail_type:expected='single':actual='composite_dish'`
- `mismatch:canonical_label:expected='Cheese Crisps (Asiago, Hatch Green Chile)':actual='Cheese Crisps (Asiago, Hatch Green Chile, Crisps, 100 Real)'`
- `mismatch:form_texture_cut:expected=[]:actual=['crisps']`
- `mismatch:claims:expected=[]:actual=['100_real']`
- `mismatch:components:expected=[]:actual=[{'identity': 'Smoked Sausage', 'role': 'ingredient', 'variant': [], 'flavor': ['hatch_green_chile'], 'form_texture_cut': ['diced'], 'processing_storage': ['smoked'], 'claims': []}, {'identity': 'Asiago Cheese', 'role': 'ingredient', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': ['pasteurized_part_skimmed'], 'claims': []}]`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps', 'Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @variant > asiago', 'Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @flavor > hatch_green_chile']:actual=['Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps', 'Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @variant > asiago', 'Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @flavor > hatch_green_chile', 'Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @form_texture_cut > crisps', 'Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @claims > 100_real', 'Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @components > smoked_sausage', 'Retail Taxonomy > Snack > Cheese Crisps > Cheese Crisps > @components > asiago_cheese']`

---

## diabolical_sesame_garlic_chicken_meal_starter
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"meal_kit"` | `"meal_kit"` |
| `category_path` | `"Meal > Meal Starters"` | `"Meal > Meal Starters"` |
| `product_identity` | `"Meal Starter"` | `"Meal Starter"` |
| `canonical_path` | `"Meal > Meal Starters > Meal Starter"` | `"Meal > Meal Starters > Meal Starter"` |
| `variant` * | `["sesame_garlic_chicken"]` | `["sesame_garlic_chicken", "brown_rice", "vegetable"]` |
| `flavor` * | `[]` | `["sesame", "garlic"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `[]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Meal Starter (Sesame Garlic Chicken)"` | `"Meal Starter (Sesame Garlic Chicken, Brown Rice, Vegetable, Sesame, Garlic, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Meal > Meal Starters > Meal Starter", "Retail Taxonomy > Meal > Meal Starters > Meal Starter > @variant > sesame_garlic_chicken", "Retail Taxonomy > Meal > Meal Starters > Meal Starter > @components > chicken"]` | `["Retail Taxonomy > Meal > Meal Starters > Meal Starter", "Retail Taxonomy > Meal > Meal Starters > Meal Starter > @variant > sesame_garlic_chicken", "Retail Taxonomy > Meal > Meal Starters > Meal Starter > @variant > brown_rice", "Retail Taxonomy > Meal > Meal Starters > Meal Starter > @variant > vegetable", "Retail Taxonomy > Meal > Meal Starters > Meal Starter > @flavor > sesame", "Retail Taxonomy > Meal > Meal Starters > Meal Starter > @flavor > garlic", "Retail Taxonomy > Meal > Meal Starters > Meal Starter > @processing_storage > frozen", "Retail Taxonomy > Meal > Meal Starters > Meal Starter > @components > sesame_garlic_chicken_breast_strips", "Retail Taxonomy > Meal > Meal Starters > Meal Starter > @components > rice_noodles"]` |
| `components` * | `[{"claims": [], "flavor": ["sesame_garlic"], "form_texture_cut": [], "identity": "Chicken", "processing_storage": [], "role": "protein", "variant": []}]` | `[{"claims": [], "flavor": ["sesame", "garlic"], "form_texture_cut": ["strips"], "identity": "Sesame Garlic Chicken Breast Strips", "processing_storage": ["pre_cut", "fully_cooked"], "role": "protein", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Rice Noodles", "processing_storage": [], "role": "base", "variant": ["brown_rice"]}]` |

**core errors:**
- `core_mismatch:variant:expected=['sesame_garlic_chicken']:actual=['sesame_garlic_chicken', 'brown_rice', 'vegetable']`
- `core_mismatch:flavor:expected=[]:actual=['sesame', 'garlic']`
- `core_mismatch:processing_storage:expected=[]:actual=['frozen']`
- `core_mismatch:component_identities:expected=['chicken']:actual=['rice_noodles', 'sesame_garlic_chicken_breast_strips']`

**exact errors:**
- `mismatch:canonical_label:expected='Meal Starter (Sesame Garlic Chicken)':actual='Meal Starter (Sesame Garlic Chicken, Brown Rice, Vegetable, Sesame, Garlic, Frozen)'`
- `mismatch:variant:expected=['sesame_garlic_chicken']:actual=['sesame_garlic_chicken', 'brown_rice', 'vegetable']`
- `mismatch:flavor:expected=[]:actual=['sesame', 'garlic']`
- `mismatch:processing_storage:expected=[]:actual=['frozen']`
- `mismatch:components:expected=[{'identity': 'Chicken', 'role': 'protein', 'variant': [], 'flavor': ['sesame_garlic'], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[{'identity': 'Sesame Garlic Chicken Breast Strips', 'role': 'protein', 'variant': [], 'flavor': ['sesame', 'garlic'], 'form_texture_cut': ['strips'], 'processing_storage': ['pre_cut', 'fully_cooked'], 'claims': []}, {'identity': 'Rice Noodles', 'role': 'base', 'variant': ['brown_rice'], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Meal > Meal Starters > Meal Starter', 'Retail Taxonomy > Meal > Meal Starters > Meal Starter > @variant > sesame_garlic_chicken', 'Retail Taxonomy > Meal > Meal Starters > Meal Starter > @components > chicken']:actual=['Retail Taxonomy > Meal > Meal Starters > Meal Starter', 'Retail Taxonomy > Meal > Meal Starters > Meal Starter > @variant > sesame_garlic_chicken', 'Retail Taxonomy > Meal > Meal Starters > Meal Starter > @variant > brown_rice', 'Retail Taxonomy > Meal > Meal Starters > Meal Starter > @variant > vegetable', 'Retail Taxonomy > Meal > Meal Starters > Meal Starter > @flavor > sesame', 'Retail Taxonomy > Meal > Meal Starters > Meal Starter > @flavor > garlic', 'Retail Taxonomy > Meal > Meal Starters > Meal Starter > @processing_storage > frozen', 'Retail Taxonomy > Meal > Meal Starters > Meal Starter > @components > sesame_garlic_chicken_breast_strips', 'Retail Taxonomy > Meal > Meal Starters > Meal Starter > @components > rice_noodles']`

---

## diabolical_chicken_apple_sausage_flatbread_breakfast_sandwich
- core: **PASS**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"composite_dish"` | `"composite_dish"` |
| `category_path` | `"Frozen > Breakfast Sandwiches"` | `"Frozen > Breakfast Sandwiches"` |
| `product_identity` | `"Breakfast Sandwich"` | `"Breakfast Sandwich"` |
| `canonical_path` | `"Frozen > Breakfast Sandwiches > Breakfast Sandwich"` | `"Frozen > Breakfast Sandwiches > Breakfast Sandwich"` |
| `variant` | `["chicken_apple_sausage", "egg_white_cheddar"]` | `["chicken_apple_sausage", "egg_white_cheddar"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `["flatbread"]` | `["flatbread"]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Breakfast Sandwich (Chicken Apple Sausage, Egg White Cheddar, Flatbread, Frozen)"` | `"Breakfast Sandwich (Chicken Apple Sausage, Egg White Cheddar, Flatbread, Frozen)"` |
| `tree_paths` | `["Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @variant > chicken_apple_sausage", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @variant > egg_white_cheddar", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @form_texture_cut > flatbread", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @processing_storage > frozen", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @components > chicken_apple_sausage_patty", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @components > egg_white_patty", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @components > cheddar_cheese", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @components > multi_grain_flatbread"]` | `["Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @variant > chicken_apple_sausage", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @variant > egg_white_cheddar", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @form_texture_cut > flatbread", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @processing_storage > frozen", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @components > chicken_apple_sausage_patty", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @components > egg_white_patty", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @components > cheddar_cheese", "Retail Taxonomy > Frozen > Breakfast Sandwiches > Breakfast Sandwich > @components > multi_grain_flatbread"]` |
| `components` * | `[{"claims": [], "flavor": ["apple"], "form_texture_cut": ["patty"], "identity": "Chicken Apple Sausage Patty", "processing_storage": ["fully_cooked"], "role": "protein", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": ["patty"], "identity": "Egg White Patty", "processing_storage": [], "role": "protein", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Cheddar Cheese", "processing_storage": [], "role": "cheese", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": ["flatbread"], "identity": "Multi-Grain Flatbread", "processing_storage": [], "role": "bread", "variant": []}]` | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Chicken Apple Sausage Patty", "processing_storage": ["fully_cooked"], "role": "protein", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Egg White Patty", "processing_storage": [], "role": "filling", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Cheddar Cheese", "processing_storage": [], "role": "cheese", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": ["flatbread"], "identity": "Multi-Grain Flatbread", "processing_storage": [], "role": "bread", "variant": ["multi_grain"]}]` |

**exact errors:**
- `mismatch:components:expected=[{'identity': 'Chicken Apple Sausage Patty', 'role': 'protein', 'variant': [], 'flavor': ['apple'], 'form_texture_cut': ['patty'], 'processing_storage': ['fully_cooked'], 'claims': []}, {'identity': 'Egg White Patty', 'role': 'protein', 'variant': [], 'flavor': [], 'form_texture_cut': ['patty'], 'processing_storage': [], 'claims': []}, {'identity': 'Cheddar Cheese', 'role': 'cheese', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Multi-Grain Flatbread', 'role': 'bread', 'variant': [], 'flavor': [], 'form_texture_cut': ['flatbread'], 'processing_storage': [], 'claims': []}]:actual=[{'identity': 'Chicken Apple Sausage Patty', 'role': 'protein', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': ['fully_cooked'], 'claims': []}, {'identity': 'Egg White Patty', 'role': 'filling', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Cheddar Cheese', 'role': 'cheese', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Multi-Grain Flatbread', 'role': 'bread', 'variant': ['multi_grain'], 'flavor': [], 'form_texture_cut': ['flatbread'], 'processing_storage': [], 'claims': []}]`
- `mismatch:mint_required:expected=True:actual=False`
