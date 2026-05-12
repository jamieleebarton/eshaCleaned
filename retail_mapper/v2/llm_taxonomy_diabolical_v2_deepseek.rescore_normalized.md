# Re-score diff: llm_taxonomy_diabolical_v2_deepseek.live.jsonl

normalizer=on, core=20/160, exact=20/160

## oat_milk_eggnog
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Beverage > Eggnog"` | `"Beverage > Eggnog"` |
| `product_identity` | `"Eggnog"` | `"Eggnog"` |
| `canonical_path` | `"Beverage > Eggnog > Eggnog"` | `"Beverage > Eggnog > Eggnog"` |
| `variant` | `["oat_milk"]` | `["oat_milk"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `["dairy_free", "plant_based"]` | `["dairy_free", "plant_based"]` |
| `canonical_label` | `"Eggnog (Oat Milk, Dairy Free, Plant Based)"` | `"Eggnog (Oat Milk, Dairy Free, Plant Based)"` |
| `tree_paths` | `["Retail Taxonomy > Beverage > Eggnog > Eggnog", "Retail Taxonomy > Beverage > Eggnog > Eggnog > @variant > oat_milk", "Retail Taxonomy > Beverage > Eggnog > Eggnog > @claims > dairy_free", "Retail Taxonomy > Beverage > Eggnog > Eggnog > @claims > plant_based"]` | `["Retail Taxonomy > Beverage > Eggnog > Eggnog", "Retail Taxonomy > Beverage > Eggnog > Eggnog > @variant > oat_milk", "Retail Taxonomy > Beverage > Eggnog > Eggnog > @claims > dairy_free", "Retail Taxonomy > Beverage > Eggnog > Eggnog > @claims > plant_based"]` |
| `components` | `[]` | `[]` |

---

## almond_milk_eggnog
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Beverage > Eggnog"` | `"Beverage > Eggnog"` |
| `product_identity` | `"Eggnog"` | `"Eggnog"` |
| `canonical_path` | `"Beverage > Eggnog > Eggnog"` | `"Beverage > Eggnog > Eggnog"` |
| `variant` | `["almond_milk"]` | `["almond_milk"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["dairy_free", "plant_based"]` | `["plant_based", "low_fat"]` |
| `canonical_label` * | `"Eggnog (Almond Milk, Dairy Free, Plant Based)"` | `"Eggnog (Almond Milk, Plant Based, Low Fat)"` |
| `tree_paths` * | `["Retail Taxonomy > Beverage > Eggnog > Eggnog", "Retail Taxonomy > Beverage > Eggnog > Eggnog > @variant > almond_milk", "Retail Taxonomy > Beverage > Eggnog > Eggnog > @claims > dairy_free", "Retail Taxonomy > Beverage > Eggnog > Eggnog > @claims > plant_based"]` | `["Retail Taxonomy > Beverage > Eggnog > Eggnog", "Retail Taxonomy > Beverage > Eggnog > Eggnog > @variant > almond_milk", "Retail Taxonomy > Beverage > Eggnog > Eggnog > @claims > plant_based", "Retail Taxonomy > Beverage > Eggnog > Eggnog > @claims > low_fat"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:claims:expected=['dairy_free', 'plant_based']:actual=['plant_based', 'low_fat']`

**exact errors:**
- `mismatch:canonical_label:expected='Eggnog (Almond Milk, Dairy Free, Plant Based)':actual='Eggnog (Almond Milk, Plant Based, Low Fat)'`
- `mismatch:claims:expected=['dairy_free', 'plant_based']:actual=['plant_based', 'low_fat']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Beverage > Eggnog > Eggnog', 'Retail Taxonomy > Beverage > Eggnog > Eggnog > @variant > almond_milk', 'Retail Taxonomy > Beverage > Eggnog > Eggnog > @claims > dairy_free', 'Retail Taxonomy > Beverage > Eggnog > Eggnog > @claims > plant_based']:actual=['Retail Taxonomy > Beverage > Eggnog > Eggnog', 'Retail Taxonomy > Beverage > Eggnog > Eggnog > @variant > almond_milk', 'Retail Taxonomy > Beverage > Eggnog > Eggnog > @claims > plant_based', 'Retail Taxonomy > Beverage > Eggnog > Eggnog > @claims > low_fat']`

---

## blueberry_probiotic_seltzer
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Beverage > Sparkling Water"` | `"Beverage > Sparkling Water"` |
| `product_identity` | `"Sparkling Water"` | `"Sparkling Water"` |
| `canonical_path` | `"Beverage > Sparkling Water > Sparkling Water"` | `"Beverage > Sparkling Water > Sparkling Water"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["blueberry"]` | `["blueberry"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `["probiotic"]` | `["probiotic"]` |
| `canonical_label` | `"Sparkling Water (Blueberry, Probiotic)"` | `"Sparkling Water (Blueberry, Probiotic)"` |
| `tree_paths` | `["Retail Taxonomy > Beverage > Sparkling Water > Sparkling Water", "Retail Taxonomy > Beverage > Sparkling Water > Sparkling Water > @flavor > blueberry", "Retail Taxonomy > Beverage > Sparkling Water > Sparkling Water > @claims > probiotic"]` | `["Retail Taxonomy > Beverage > Sparkling Water > Sparkling Water", "Retail Taxonomy > Beverage > Sparkling Water > Sparkling Water > @flavor > blueberry", "Retail Taxonomy > Beverage > Sparkling Water > Sparkling Water > @claims > probiotic"]` |
| `components` | `[]` | `[]` |

---

## pineapple_turmeric_kombucha
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Beverage > Kombucha"` | `"Beverage > Kombucha"` |
| `product_identity` | `"Kombucha"` | `"Kombucha"` |
| `canonical_path` | `"Beverage > Kombucha > Kombucha"` | `"Beverage > Kombucha > Kombucha"` |
| `variant` * | `[]` | `["turmeric"]` |
| `flavor` * | `["pineapple", "turmeric"]` | `["pineapple"]` |
| `form_texture_cut` * | `[]` | `["sparkling"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["probiotic"]` | `["probiotic", "organic"]` |
| `canonical_label` * | `"Kombucha (Pineapple, Turmeric, Probiotic)"` | `"Kombucha (Turmeric, Pineapple, Sparkling, Probiotic, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Beverage > Kombucha > Kombucha", "Retail Taxonomy > Beverage > Kombucha > Kombucha > @flavor > pineapple", "Retail Taxonomy > Beverage > Kombucha > Kombucha > @flavor > turmeric", "Retail Taxonomy > Beverage > Kombucha > Kombucha > @claims > probiotic"]` | `["Retail Taxonomy > Beverage > Kombucha > Kombucha", "Retail Taxonomy > Beverage > Kombucha > Kombucha > @variant > turmeric", "Retail Taxonomy > Beverage > Kombucha > Kombucha > @flavor > pineapple", "Retail Taxonomy > Beverage > Kombucha > Kombucha > @form_texture_cut > sparkling", "Retail Taxonomy > Beverage > Kombucha > Kombucha > @claims > probiotic", "Retail Taxonomy > Beverage > Kombucha > Kombucha > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['turmeric']`
- `core_mismatch:flavor:expected=['pineapple', 'turmeric']:actual=['pineapple']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['sparkling']`
- `core_mismatch:claims:expected=['probiotic']:actual=['probiotic', 'organic']`

**exact errors:**
- `mismatch:canonical_label:expected='Kombucha (Pineapple, Turmeric, Probiotic)':actual='Kombucha (Turmeric, Pineapple, Sparkling, Probiotic, Organic)'`
- `mismatch:variant:expected=[]:actual=['turmeric']`
- `mismatch:flavor:expected=['pineapple', 'turmeric']:actual=['pineapple']`
- `mismatch:form_texture_cut:expected=[]:actual=['sparkling']`
- `mismatch:claims:expected=['probiotic']:actual=['probiotic', 'organic']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Beverage > Kombucha > Kombucha', 'Retail Taxonomy > Beverage > Kombucha > Kombucha > @flavor > pineapple', 'Retail Taxonomy > Beverage > Kombucha > Kombucha > @flavor > turmeric', 'Retail Taxonomy > Beverage > Kombucha > Kombucha > @claims > probiotic']:actual=['Retail Taxonomy > Beverage > Kombucha > Kombucha', 'Retail Taxonomy > Beverage > Kombucha > Kombucha > @variant > turmeric', 'Retail Taxonomy > Beverage > Kombucha > Kombucha > @flavor > pineapple', 'Retail Taxonomy > Beverage > Kombucha > Kombucha > @form_texture_cut > sparkling', 'Retail Taxonomy > Beverage > Kombucha > Kombucha > @claims > probiotic', 'Retail Taxonomy > Beverage > Kombucha > Kombucha > @claims > organic']`

---

## apple_cider_vinegar_drink_elderberry
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"single"` | `null` |
| `category_path` * | `"Beverage > Functional Drinks"` | `null` |
| `product_identity` * | `"Apple Cider Vinegar Drink"` | `""` |
| `canonical_path` * | `"Beverage > Functional Drinks > Apple Cider Vinegar Drink"` | `""` |
| `variant` | `[]` | `[]` |
| `flavor` * | `["elderberry"]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Apple Cider Vinegar Drink (Elderberry)"` | `""` |
| `tree_paths` * | `["Retail Taxonomy > Beverage > Functional Drinks > Apple Cider Vinegar Drink", "Retail Taxonomy > Beverage > Functional Drinks > Apple Cider Vinegar Drink > @flavor > elderberry"]` | `["Retail Taxonomy > "]` |
| `components` | `[]` | `[]` |

**core errors:**
- `missing_field:fdc_id`
- `missing_field:retail_type`
- `missing_field:category_path`
- `missing_field:confidence`
- `missing_field:mint_required`
- `missing_field:rationale`
- `invalid_retail_type:None`
- `category_path_too_shallow`
- `core_mismatch:retail_type:expected='single':actual=None`
- `core_mismatch:category_path:expected='Beverage > Functional Drinks':actual=None`
- `core_mismatch:product_identity:expected='Apple Cider Vinegar Drink':actual=''`
- `core_mismatch:canonical_path:expected='Beverage > Functional Drinks > Apple Cider Vinegar Drink':actual=''`
- `core_mismatch:flavor:expected=['elderberry']:actual=[]`

**exact errors:**
- `missing_field:fdc_id`
- `missing_field:retail_type`
- `missing_field:category_path`
- `missing_field:confidence`
- `missing_field:mint_required`
- `missing_field:rationale`
- `invalid_retail_type:None`
- `category_path_too_shallow`
- `tree_paths_mismatch`
- `mismatch:retail_type:expected='single':actual=None`
- `mismatch:category_path:expected='Beverage > Functional Drinks':actual=None`
- `mismatch:product_identity:expected='Apple Cider Vinegar Drink':actual=''`
- `mismatch:canonical_path:expected='Beverage > Functional Drinks > Apple Cider Vinegar Drink':actual=''`
- `mismatch:canonical_label:expected='Apple Cider Vinegar Drink (Elderberry)':actual=''`
- `mismatch:flavor:expected=['elderberry']:actual=[]`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Beverage > Functional Drinks > Apple Cider Vinegar Drink', 'Retail Taxonomy > Beverage > Functional Drinks > Apple Cider Vinegar Drink > @flavor > elderberry']:actual=['Retail Taxonomy >']`

---

## chocolate_oat_milk_cold_brew
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Beverage > Coffee"` | `"Beverage > Coffee"` |
| `product_identity` | `"Cold Brew Coffee"` | `"Cold Brew Coffee"` |
| `canonical_path` | `"Beverage > Coffee > Cold Brew Coffee"` | `"Beverage > Coffee > Cold Brew Coffee"` |
| `variant` | `["oat_milk"]` | `["oat_milk"]` |
| `flavor` * | `["chocolate"]` | `["dark_chocolate", "chocolate"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `[]` | `["chilled"]` |
| `claims` | `["dairy_free", "plant_based"]` | `["dairy_free", "plant_based"]` |
| `canonical_label` * | `"Cold Brew Coffee (Oat Milk, Chocolate, Dairy Free, Plant Based)"` | `"Cold Brew Coffee (Oat Milk, Dark Chocolate, Chocolate, Chilled, Dairy Free, Plant Based)"` |
| `tree_paths` * | `["Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee", "Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @variant > oat_milk", "Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @flavor > chocolate", "Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @claims > dairy_free", "Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @claims > plant_based"]` | `["Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee", "Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @variant > oat_milk", "Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @flavor > dark_chocolate", "Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @flavor > chocolate", "Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @processing_storage > chilled", "Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @claims > dairy_free", "Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @claims > plant_based", "Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @components > oat_milk"]` |
| `components` * | `[]` | `[{"claims": ["dairy_free", "plant_based"], "flavor": [], "form_texture_cut": [], "identity": "Oat Milk", "processing_storage": [], "role": "ingredient", "variant": []}]` |

**core errors:**
- `core_mismatch:flavor:expected=['chocolate']:actual=['dark_chocolate', 'chocolate']`
- `core_mismatch:processing_storage:expected=[]:actual=['chilled']`
- `core_mismatch:component_identities:expected=[]:actual=['oat_milk']`

**exact errors:**
- `mismatch:canonical_label:expected='Cold Brew Coffee (Oat Milk, Chocolate, Dairy Free, Plant Based)':actual='Cold Brew Coffee (Oat Milk, Dark Chocolate, Chocolate, Chilled, Dairy Free, Plant Based)'`
- `mismatch:flavor:expected=['chocolate']:actual=['dark_chocolate', 'chocolate']`
- `mismatch:processing_storage:expected=[]:actual=['chilled']`
- `mismatch:components:expected=[]:actual=[{'identity': 'Oat Milk', 'role': 'ingredient', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': ['dairy_free', 'plant_based']}]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee', 'Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @variant > oat_milk', 'Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @flavor > chocolate', 'Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @claims > dairy_free', 'Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @claims > plant_based']:actual=['Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee', 'Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @variant > oat_milk', 'Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @flavor > dark_chocolate', 'Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @flavor > chocolate', 'Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @processing_storage > chilled', 'Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @claims > dairy_free', 'Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @claims > plant_based', 'Retail Taxonomy > Beverage > Coffee > Cold Brew Coffee > @components > oat_milk']`

---

## watermelon_mint_coconut_water
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Beverage > Coconut Water"` | `"Beverage > Coconut Water"` |
| `product_identity` | `"Coconut Water"` | `"Coconut Water"` |
| `canonical_path` | `"Beverage > Coconut Water > Coconut Water"` | `"Beverage > Coconut Water > Coconut Water"` |
| `variant` * | `[]` | `["sparkling"]` |
| `flavor` | `["watermelon", "mint"]` | `["watermelon", "mint"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["organic"]` |
| `canonical_label` * | `"Coconut Water (Watermelon, Mint)"` | `"Coconut Water (Sparkling, Watermelon, Mint, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Beverage > Coconut Water > Coconut Water", "Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @flavor > watermelon", "Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @flavor > mint"]` | `["Retail Taxonomy > Beverage > Coconut Water > Coconut Water", "Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @variant > sparkling", "Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @flavor > watermelon", "Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @flavor > mint", "Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['sparkling']`
- `core_mismatch:claims:expected=[]:actual=['organic']`

**exact errors:**
- `mismatch:canonical_label:expected='Coconut Water (Watermelon, Mint)':actual='Coconut Water (Sparkling, Watermelon, Mint, Organic)'`
- `mismatch:variant:expected=[]:actual=['sparkling']`
- `mismatch:claims:expected=[]:actual=['organic']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Beverage > Coconut Water > Coconut Water', 'Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @flavor > watermelon', 'Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @flavor > mint']:actual=['Retail Taxonomy > Beverage > Coconut Water > Coconut Water', 'Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @variant > sparkling', 'Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @flavor > watermelon', 'Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @flavor > mint', 'Retail Taxonomy > Beverage > Coconut Water > Coconut Water > @claims > organic']`

---

## beet_ginger_lemon_shot
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Beverage > Wellness Shots"` | `"Beverage > Wellness Shots"` |
| `product_identity` | `"Wellness Shot"` | `"Wellness Shot"` |
| `canonical_path` | `"Beverage > Wellness Shots > Wellness Shot"` | `"Beverage > Wellness Shots > Wellness Shot"` |
| `variant` * | `[]` | `["beet_ginger_lemon"]` |
| `flavor` | `["beet", "ginger", "lemon"]` | `["beet", "ginger", "lemon"]` |
| `form_texture_cut` * | `["shot"]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["probiotic"]` |
| `canonical_label` * | `"Wellness Shot (Beet, Ginger, Lemon, Shot)"` | `"Wellness Shot (Beet Ginger Lemon, Beet, Ginger, Lemon, Probiotic)"` |
| `tree_paths` * | `["Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot", "Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @flavor > beet", "Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @flavor > ginger", "Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @flavor > lemon", "Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @form_texture_cut > shot"]` | `["Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot", "Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @variant > beet_ginger_lemon", "Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @flavor > beet", "Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @flavor > ginger", "Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @flavor > lemon", "Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @claims > probiotic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['beet_ginger_lemon']`
- `core_mismatch:form_texture_cut:expected=['shot']:actual=[]`
- `core_mismatch:claims:expected=[]:actual=['probiotic']`

**exact errors:**
- `mismatch:canonical_label:expected='Wellness Shot (Beet, Ginger, Lemon, Shot)':actual='Wellness Shot (Beet Ginger Lemon, Beet, Ginger, Lemon, Probiotic)'`
- `mismatch:variant:expected=[]:actual=['beet_ginger_lemon']`
- `mismatch:form_texture_cut:expected=['shot']:actual=[]`
- `mismatch:claims:expected=[]:actual=['probiotic']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot', 'Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @flavor > beet', 'Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @flavor > ginger', 'Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @flavor > lemon', 'Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @form_texture_cut > shot']:actual=['Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot', 'Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @variant > beet_ginger_lemon', 'Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @flavor > beet', 'Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @flavor > ginger', 'Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @flavor > lemon', 'Retail Taxonomy > Beverage > Wellness Shots > Wellness Shot > @claims > probiotic']`

---

## mushroom_adaptogen_latte_dry_mix
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Drink Mixes"` | `"Pantry > Drink Mixes"` |
| `product_identity` | `"Latte Mix"` | `"Latte Mix"` |
| `canonical_path` | `"Pantry > Drink Mixes > Latte Mix"` | `"Pantry > Drink Mixes > Latte Mix"` |
| `variant` * | `["mushroom_adaptogen"]` | `["mushroom_adaptogen", "mocha"]` |
| `flavor` | `["mocha"]` | `["mocha"]` |
| `form_texture_cut` | `["powder"]` | `["powder"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["organic"]` |
| `canonical_label` * | `"Latte Mix (Mushroom Adaptogen, Mocha, Powder)"` | `"Latte Mix (Mushroom Adaptogen, Mocha, Mocha, Powder, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Drink Mixes > Latte Mix", "Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @variant > mushroom_adaptogen", "Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @flavor > mocha", "Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @form_texture_cut > powder"]` | `["Retail Taxonomy > Pantry > Drink Mixes > Latte Mix", "Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @variant > mushroom_adaptogen", "Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @variant > mocha", "Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @flavor > mocha", "Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @form_texture_cut > powder", "Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['mushroom_adaptogen']:actual=['mushroom_adaptogen', 'mocha']`
- `core_mismatch:claims:expected=[]:actual=['organic']`

**exact errors:**
- `mismatch:canonical_label:expected='Latte Mix (Mushroom Adaptogen, Mocha, Powder)':actual='Latte Mix (Mushroom Adaptogen, Mocha, Mocha, Powder, Organic)'`
- `mismatch:variant:expected=['mushroom_adaptogen']:actual=['mushroom_adaptogen', 'mocha']`
- `mismatch:claims:expected=[]:actual=['organic']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Drink Mixes > Latte Mix', 'Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @variant > mushroom_adaptogen', 'Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @flavor > mocha', 'Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @form_texture_cut > powder']:actual=['Retail Taxonomy > Pantry > Drink Mixes > Latte Mix', 'Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @variant > mushroom_adaptogen', 'Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @variant > mocha', 'Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @flavor > mocha', 'Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @form_texture_cut > powder', 'Retail Taxonomy > Pantry > Drink Mixes > Latte Mix > @claims > organic']`

---

## crystal_light_lemonade_dry_mix
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Drink Mixes"` | `"Pantry > Drink Mixes"` |
| `product_identity` * | `"Lemonade Mix"` | `"Drink Mix"` |
| `canonical_path` * | `"Pantry > Drink Mixes > Lemonade Mix"` | `"Pantry > Drink Mixes > Drink Mix"` |
| `variant` * | `[]` | `["lemonade"]` |
| `flavor` * | `[]` | `["lemonade"]` |
| `form_texture_cut` * | `["powder"]` | `["powdered"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["low_calorie", "sugar_free"]` | `[]` |
| `canonical_label` * | `"Lemonade Mix (Powder, Low Calorie, Sugar Free)"` | `"Drink Mix (Lemonade, Lemonade, Powdered)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Drink Mixes > Lemonade Mix", "Retail Taxonomy > Pantry > Drink Mixes > Lemonade Mix > @form_texture_cut > powder", "Retail Taxonomy > Pantry > Drink Mixes > Lemonade Mix > @claims > low_calorie", "Retail Taxonomy > Pantry > Drink Mixes > Lemonade Mix > @claims > sugar_free"]` | `["Retail Taxonomy > Pantry > Drink Mixes > Drink Mix", "Retail Taxonomy > Pantry > Drink Mixes > Drink Mix > @variant > lemonade", "Retail Taxonomy > Pantry > Drink Mixes > Drink Mix > @flavor > lemonade", "Retail Taxonomy > Pantry > Drink Mixes > Drink Mix > @form_texture_cut > powdered"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Lemonade Mix':actual='Drink Mix'`
- `core_mismatch:canonical_path:expected='Pantry > Drink Mixes > Lemonade Mix':actual='Pantry > Drink Mixes > Drink Mix'`
- `core_mismatch:variant:expected=[]:actual=['lemonade']`
- `core_mismatch:flavor:expected=[]:actual=['lemonade']`
- `core_mismatch:form_texture_cut:expected=['powder']:actual=['powdered']`
- `core_mismatch:claims:expected=['low_calorie', 'sugar_free']:actual=[]`

**exact errors:**
- `mismatch:product_identity:expected='Lemonade Mix':actual='Drink Mix'`
- `mismatch:canonical_path:expected='Pantry > Drink Mixes > Lemonade Mix':actual='Pantry > Drink Mixes > Drink Mix'`
- `mismatch:canonical_label:expected='Lemonade Mix (Powder, Low Calorie, Sugar Free)':actual='Drink Mix (Lemonade, Lemonade, Powdered)'`
- `mismatch:variant:expected=[]:actual=['lemonade']`
- `mismatch:flavor:expected=[]:actual=['lemonade']`
- `mismatch:form_texture_cut:expected=['powder']:actual=['powdered']`
- `mismatch:claims:expected=['low_calorie', 'sugar_free']:actual=[]`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Drink Mixes > Lemonade Mix', 'Retail Taxonomy > Pantry > Drink Mixes > Lemonade Mix > @form_texture_cut > powder', 'Retail Taxonomy > Pantry > Drink Mixes > Lemonade Mix > @claims > low_calorie', 'Retail Taxonomy > Pantry > Drink Mixes > Lemonade Mix > @claims > sugar_free']:actual=['Retail Taxonomy > Pantry > Drink Mixes > Drink Mix', 'Retail Taxonomy > Pantry > Drink Mixes > Drink Mix > @variant > lemonade', 'Retail Taxonomy > Pantry > Drink Mixes > Drink Mix > @flavor > lemonade', 'Retail Taxonomy > Pantry > Drink Mixes > Drink Mix > @form_texture_cut > powdered']`

---

## hot_cocoa_dry_mix
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"single"` | `"pantry"` |
| `category_path` | `"Pantry > Drink Mixes"` | `"Pantry > Drink Mixes"` |
| `product_identity` | `"Hot Cocoa Mix"` | `"Hot Cocoa Mix"` |
| `canonical_path` | `"Pantry > Drink Mixes > Hot Cocoa Mix"` | `"Pantry > Drink Mixes > Hot Cocoa Mix"` |
| `variant` * | `[]` | `["milk_chocolate", "marshmallow"]` |
| `flavor` * | `["milk_chocolate"]` | `["chocolate"]` |
| `form_texture_cut` * | `["powder"]` | `["dry_mix"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Hot Cocoa Mix (Milk Chocolate, Powder)"` | `"Hot Cocoa Mix (Milk Chocolate, Marshmallow, Chocolate, Dry Mix)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix", "Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix > @flavor > milk_chocolate", "Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix > @form_texture_cut > powder"]` | `["Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix", "Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix > @variant > milk_chocolate", "Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix > @variant > marshmallow", "Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix > @flavor > chocolate", "Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix > @form_texture_cut > dry_mix"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `invalid_retail_type:pantry`
- `core_mismatch:retail_type:expected='single':actual='pantry'`
- `core_mismatch:variant:expected=[]:actual=['milk_chocolate', 'marshmallow']`
- `core_mismatch:flavor:expected=['milk_chocolate']:actual=['chocolate']`
- `core_mismatch:form_texture_cut:expected=['powder']:actual=['dry_mix']`

**exact errors:**
- `invalid_retail_type:pantry`
- `mismatch:retail_type:expected='single':actual='pantry'`
- `mismatch:canonical_label:expected='Hot Cocoa Mix (Milk Chocolate, Powder)':actual='Hot Cocoa Mix (Milk Chocolate, Marshmallow, Chocolate, Dry Mix)'`
- `mismatch:variant:expected=[]:actual=['milk_chocolate', 'marshmallow']`
- `mismatch:flavor:expected=['milk_chocolate']:actual=['chocolate']`
- `mismatch:form_texture_cut:expected=['powder']:actual=['dry_mix']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix', 'Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix > @flavor > milk_chocolate', 'Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix > @form_texture_cut > powder']:actual=['Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix', 'Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix > @variant > milk_chocolate', 'Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix > @variant > marshmallow', 'Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix > @flavor > chocolate', 'Retail Taxonomy > Pantry > Drink Mixes > Hot Cocoa Mix > @form_texture_cut > dry_mix']`

---

## gatorade_powder
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Drink Mixes"` | `"Pantry > Drink Mixes"` |
| `product_identity` | `"Sports Drink Mix"` | `"Sports Drink Mix"` |
| `canonical_path` | `"Pantry > Drink Mixes > Sports Drink Mix"` | `"Pantry > Drink Mixes > Sports Drink Mix"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["orange"]` | `["orange"]` |
| `form_texture_cut` | `["powder"]` | `["powder"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["electrolytes"]` |
| `canonical_label` * | `"Sports Drink Mix (Orange, Powder)"` | `"Sports Drink Mix (Orange, Powder, Electrolytes)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix", "Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix > @flavor > orange", "Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix > @form_texture_cut > powder"]` | `["Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix", "Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix > @flavor > orange", "Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix > @form_texture_cut > powder", "Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix > @claims > electrolytes"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:claims:expected=[]:actual=['electrolytes']`

**exact errors:**
- `mismatch:canonical_label:expected='Sports Drink Mix (Orange, Powder)':actual='Sports Drink Mix (Orange, Powder, Electrolytes)'`
- `mismatch:claims:expected=[]:actual=['electrolytes']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix', 'Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix > @flavor > orange', 'Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix > @form_texture_cut > powder']:actual=['Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix', 'Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix > @flavor > orange', 'Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix > @form_texture_cut > powder', 'Retail Taxonomy > Pantry > Drink Mixes > Sports Drink Mix > @claims > electrolytes']`

---

## kefir_strawberry_probiotic
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Dairy > Kefir"` | `"Dairy > Kefir"` |
| `product_identity` | `"Kefir"` | `"Kefir"` |
| `canonical_path` | `"Dairy > Kefir > Kefir"` | `"Dairy > Kefir > Kefir"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["strawberry"]` | `["strawberry"]` |
| `form_texture_cut` * | `[]` | `["drinkable"]` |
| `processing_storage` * | `[]` | `["refrigerated"]` |
| `claims` | `["probiotic"]` | `["probiotic"]` |
| `canonical_label` * | `"Kefir (Strawberry, Probiotic)"` | `"Kefir (Strawberry, Drinkable, Refrigerated, Probiotic)"` |
| `tree_paths` * | `["Retail Taxonomy > Dairy > Kefir > Kefir", "Retail Taxonomy > Dairy > Kefir > Kefir > @flavor > strawberry", "Retail Taxonomy > Dairy > Kefir > Kefir > @claims > probiotic"]` | `["Retail Taxonomy > Dairy > Kefir > Kefir", "Retail Taxonomy > Dairy > Kefir > Kefir > @flavor > strawberry", "Retail Taxonomy > Dairy > Kefir > Kefir > @form_texture_cut > drinkable", "Retail Taxonomy > Dairy > Kefir > Kefir > @processing_storage > refrigerated", "Retail Taxonomy > Dairy > Kefir > Kefir > @claims > probiotic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:form_texture_cut:expected=[]:actual=['drinkable']`
- `core_mismatch:processing_storage:expected=[]:actual=['refrigerated']`

**exact errors:**
- `mismatch:canonical_label:expected='Kefir (Strawberry, Probiotic)':actual='Kefir (Strawberry, Drinkable, Refrigerated, Probiotic)'`
- `mismatch:form_texture_cut:expected=[]:actual=['drinkable']`
- `mismatch:processing_storage:expected=[]:actual=['refrigerated']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Dairy > Kefir > Kefir', 'Retail Taxonomy > Dairy > Kefir > Kefir > @flavor > strawberry', 'Retail Taxonomy > Dairy > Kefir > Kefir > @claims > probiotic']:actual=['Retail Taxonomy > Dairy > Kefir > Kefir', 'Retail Taxonomy > Dairy > Kefir > Kefir > @flavor > strawberry', 'Retail Taxonomy > Dairy > Kefir > Kefir > @form_texture_cut > drinkable', 'Retail Taxonomy > Dairy > Kefir > Kefir > @processing_storage > refrigerated', 'Retail Taxonomy > Dairy > Kefir > Kefir > @claims > probiotic']`

---

## matcha_protein_shake
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Beverage > Protein Drinks"` | `"Beverage > Protein Drinks"` |
| `product_identity` | `"Protein Shake"` | `"Protein Shake"` |
| `canonical_path` | `"Beverage > Protein Drinks > Protein Shake"` | `"Beverage > Protein Drinks > Protein Shake"` |
| `variant` * | `[]` | `["matcha"]` |
| `flavor` * | `["matcha"]` | `["coconut"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["high_protein"]` | `["high_protein", "fortified", "grass_fed"]` |
| `canonical_label` * | `"Protein Shake (Matcha, High Protein)"` | `"Protein Shake (Matcha, Coconut, High Protein, Fortified, Grass Fed)"` |
| `tree_paths` * | `["Retail Taxonomy > Beverage > Protein Drinks > Protein Shake", "Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @flavor > matcha", "Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @claims > high_protein"]` | `["Retail Taxonomy > Beverage > Protein Drinks > Protein Shake", "Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @variant > matcha", "Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @flavor > coconut", "Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @claims > high_protein", "Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @claims > fortified", "Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @claims > grass_fed"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['matcha']`
- `core_mismatch:flavor:expected=['matcha']:actual=['coconut']`
- `core_mismatch:claims:expected=['high_protein']:actual=['high_protein', 'fortified', 'grass_fed']`

**exact errors:**
- `mismatch:canonical_label:expected='Protein Shake (Matcha, High Protein)':actual='Protein Shake (Matcha, Coconut, High Protein, Fortified, Grass Fed)'`
- `mismatch:variant:expected=[]:actual=['matcha']`
- `mismatch:flavor:expected=['matcha']:actual=['coconut']`
- `mismatch:claims:expected=['high_protein']:actual=['high_protein', 'fortified', 'grass_fed']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Beverage > Protein Drinks > Protein Shake', 'Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @flavor > matcha', 'Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @claims > high_protein']:actual=['Retail Taxonomy > Beverage > Protein Drinks > Protein Shake', 'Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @variant > matcha', 'Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @flavor > coconut', 'Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @claims > high_protein', 'Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @claims > fortified', 'Retail Taxonomy > Beverage > Protein Drinks > Protein Shake > @claims > grass_fed']`

---

## hersheys_milk_chocolate_bar
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Chocolate Candy"` | `"Snack > Chocolate Candy"` |
| `product_identity` | `"Chocolate Bar"` | `"Chocolate Bar"` |
| `canonical_path` | `"Snack > Chocolate Candy > Chocolate Bar"` | `"Snack > Chocolate Candy > Chocolate Bar"` |
| `variant` | `["milk_chocolate"]` | `["milk_chocolate"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Chocolate Bar (Milk Chocolate)"` | `"Chocolate Bar (Milk Chocolate)"` |
| `tree_paths` | `["Retail Taxonomy > Snack > Chocolate Candy > Chocolate Bar", "Retail Taxonomy > Snack > Chocolate Candy > Chocolate Bar > @variant > milk_chocolate"]` | `["Retail Taxonomy > Snack > Chocolate Candy > Chocolate Bar", "Retail Taxonomy > Snack > Chocolate Candy > Chocolate Bar > @variant > milk_chocolate"]` |
| `components` | `[]` | `[]` |

---

## nesquik_chocolate_milk_powder
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Drink Mixes"` | `"Pantry > Drink Mixes"` |
| `product_identity` | `"Chocolate Milk Mix"` | `"Chocolate Milk Mix"` |
| `canonical_path` | `"Pantry > Drink Mixes > Chocolate Milk Mix"` | `"Pantry > Drink Mixes > Chocolate Milk Mix"` |
| `variant` * | `[]` | `["powdered"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `["powder"]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Chocolate Milk Mix (Powder)"` | `"Chocolate Milk Mix (Powdered)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Drink Mixes > Chocolate Milk Mix", "Retail Taxonomy > Pantry > Drink Mixes > Chocolate Milk Mix > @form_texture_cut > powder"]` | `["Retail Taxonomy > Pantry > Drink Mixes > Chocolate Milk Mix", "Retail Taxonomy > Pantry > Drink Mixes > Chocolate Milk Mix > @variant > powdered"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['powdered']`
- `core_mismatch:form_texture_cut:expected=['powder']:actual=[]`

**exact errors:**
- `mismatch:canonical_label:expected='Chocolate Milk Mix (Powder)':actual='Chocolate Milk Mix (Powdered)'`
- `mismatch:variant:expected=[]:actual=['powdered']`
- `mismatch:form_texture_cut:expected=['powder']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Drink Mixes > Chocolate Milk Mix', 'Retail Taxonomy > Pantry > Drink Mixes > Chocolate Milk Mix > @form_texture_cut > powder']:actual=['Retail Taxonomy > Pantry > Drink Mixes > Chocolate Milk Mix', 'Retail Taxonomy > Pantry > Drink Mixes > Chocolate Milk Mix > @variant > powdered']`

---

## hersheys_chocolate_milk_rtd
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Dairy > Flavored Milk"` | `"Dairy > Flavored Milk"` |
| `product_identity` | `"Chocolate Milk"` | `"Chocolate Milk"` |
| `canonical_path` | `"Dairy > Flavored Milk > Chocolate Milk"` | `"Dairy > Flavored Milk > Chocolate Milk"` |
| `variant` * | `["2_percent"]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `[]` | `["refrigerated"]` |
| `claims` * | `[]` | `["reduced_fat"]` |
| `canonical_label` * | `"Chocolate Milk (2 Percent)"` | `"Chocolate Milk (Refrigerated, Reduced Fat)"` |
| `tree_paths` * | `["Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk", "Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk > @variant > 2_percent"]` | `["Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk", "Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk > @processing_storage > refrigerated", "Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk > @claims > reduced_fat"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['2_percent']:actual=[]`
- `core_mismatch:processing_storage:expected=[]:actual=['refrigerated']`
- `core_mismatch:claims:expected=[]:actual=['reduced_fat']`

**exact errors:**
- `mismatch:canonical_label:expected='Chocolate Milk (2 Percent)':actual='Chocolate Milk (Refrigerated, Reduced Fat)'`
- `mismatch:variant:expected=['2_percent']:actual=[]`
- `mismatch:processing_storage:expected=[]:actual=['refrigerated']`
- `mismatch:claims:expected=[]:actual=['reduced_fat']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk', 'Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk > @variant > 2_percent']:actual=['Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk', 'Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk > @processing_storage > refrigerated', 'Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk > @claims > reduced_fat']`

---

## dark_chocolate_almond_milk
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Beverage > Plant Milk"` | `"Beverage > Plant Milk"` |
| `product_identity` | `"Almond Milk"` | `"Almond Milk"` |
| `canonical_path` | `"Beverage > Plant Milk > Almond Milk"` | `"Beverage > Plant Milk > Almond Milk"` |
| `variant` * | `[]` | `["dark_chocolate"]` |
| `flavor` * | `["dark_chocolate"]` | `["chocolate"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["dairy_free", "plant_based"]` | `["fortified"]` |
| `canonical_label` * | `"Almond Milk (Dark Chocolate, Dairy Free, Plant Based)"` | `"Almond Milk (Dark Chocolate, Chocolate, Fortified)"` |
| `tree_paths` * | `["Retail Taxonomy > Beverage > Plant Milk > Almond Milk", "Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @flavor > dark_chocolate", "Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @claims > dairy_free", "Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @claims > plant_based"]` | `["Retail Taxonomy > Beverage > Plant Milk > Almond Milk", "Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @variant > dark_chocolate", "Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @flavor > chocolate", "Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @claims > fortified"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['dark_chocolate']`
- `core_mismatch:flavor:expected=['dark_chocolate']:actual=['chocolate']`
- `core_mismatch:claims:expected=['dairy_free', 'plant_based']:actual=['fortified']`

**exact errors:**
- `mismatch:canonical_label:expected='Almond Milk (Dark Chocolate, Dairy Free, Plant Based)':actual='Almond Milk (Dark Chocolate, Chocolate, Fortified)'`
- `mismatch:variant:expected=[]:actual=['dark_chocolate']`
- `mismatch:flavor:expected=['dark_chocolate']:actual=['chocolate']`
- `mismatch:claims:expected=['dairy_free', 'plant_based']:actual=['fortified']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Beverage > Plant Milk > Almond Milk', 'Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @flavor > dark_chocolate', 'Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @claims > dairy_free', 'Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @claims > plant_based']:actual=['Retail Taxonomy > Beverage > Plant Milk > Almond Milk', 'Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @variant > dark_chocolate', 'Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @flavor > chocolate', 'Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @claims > fortified']`

---

## ghirardelli_dark_chocolate_squares
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Snack > Chocolate Candy"` | `"Pantry > Chocolate & Candy > Chocolate"` |
| `product_identity` * | `"Chocolate Squares"` | `"Chocolate"` |
| `canonical_path` * | `"Snack > Chocolate Candy > Chocolate Squares"` | `"Pantry > Chocolate & Candy > Chocolate > Chocolate"` |
| `variant` * | `["dark_chocolate"]` | `["dark"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["squares"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Chocolate Squares (Dark Chocolate)"` | `"Chocolate (Dark, Squares)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Chocolate Candy > Chocolate Squares", "Retail Taxonomy > Snack > Chocolate Candy > Chocolate Squares > @variant > dark_chocolate"]` | `["Retail Taxonomy > Pantry > Chocolate & Candy > Chocolate > Chocolate", "Retail Taxonomy > Pantry > Chocolate & Candy > Chocolate > Chocolate > @variant > dark", "Retail Taxonomy > Pantry > Chocolate & Candy > Chocolate > Chocolate > @form_texture_cut > squares"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Snack > Chocolate Candy':actual='Pantry > Chocolate & Candy > Chocolate'`
- `core_mismatch:product_identity:expected='Chocolate Squares':actual='Chocolate'`
- `core_mismatch:canonical_path:expected='Snack > Chocolate Candy > Chocolate Squares':actual='Pantry > Chocolate & Candy > Chocolate > Chocolate'`
- `core_mismatch:variant:expected=['dark_chocolate']:actual=['dark']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['squares']`

**exact errors:**
- `mismatch:category_path:expected='Snack > Chocolate Candy':actual='Pantry > Chocolate & Candy > Chocolate'`
- `mismatch:product_identity:expected='Chocolate Squares':actual='Chocolate'`
- `mismatch:canonical_path:expected='Snack > Chocolate Candy > Chocolate Squares':actual='Pantry > Chocolate & Candy > Chocolate > Chocolate'`
- `mismatch:canonical_label:expected='Chocolate Squares (Dark Chocolate)':actual='Chocolate (Dark, Squares)'`
- `mismatch:variant:expected=['dark_chocolate']:actual=['dark']`
- `mismatch:form_texture_cut:expected=[]:actual=['squares']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Chocolate Candy > Chocolate Squares', 'Retail Taxonomy > Snack > Chocolate Candy > Chocolate Squares > @variant > dark_chocolate']:actual=['Retail Taxonomy > Pantry > Chocolate & Candy > Chocolate > Chocolate', 'Retail Taxonomy > Pantry > Chocolate & Candy > Chocolate > Chocolate > @variant > dark', 'Retail Taxonomy > Pantry > Chocolate & Candy > Chocolate > Chocolate > @form_texture_cut > squares']`

---

## white_chocolate_macadamia_cookies
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Cookies"` | `"Snack > Cookies"` |
| `product_identity` | `"Cookies"` | `"Cookies"` |
| `canonical_path` | `"Snack > Cookies > Cookies"` | `"Snack > Cookies > Cookies"` |
| `variant` * | `[]` | `["white_chocolate_macadamia_nut"]` |
| `flavor` * | `["white_chocolate", "macadamia_nut"]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["gluten_free", "high_protein"]` |
| `canonical_label` * | `"Cookies (White Chocolate, Macadamia Nut)"` | `"Cookies (White Chocolate Macadamia Nut, Gluten Free, High Protein)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Cookies > Cookies", "Retail Taxonomy > Snack > Cookies > Cookies > @flavor > white_chocolate", "Retail Taxonomy > Snack > Cookies > Cookies > @flavor > macadamia_nut"]` | `["Retail Taxonomy > Snack > Cookies > Cookies", "Retail Taxonomy > Snack > Cookies > Cookies > @variant > white_chocolate_macadamia_nut", "Retail Taxonomy > Snack > Cookies > Cookies > @claims > gluten_free", "Retail Taxonomy > Snack > Cookies > Cookies > @claims > high_protein"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['white_chocolate_macadamia_nut']`
- `core_mismatch:flavor:expected=['white_chocolate', 'macadamia_nut']:actual=[]`
- `core_mismatch:claims:expected=[]:actual=['gluten_free', 'high_protein']`

**exact errors:**
- `mismatch:canonical_label:expected='Cookies (White Chocolate, Macadamia Nut)':actual='Cookies (White Chocolate Macadamia Nut, Gluten Free, High Protein)'`
- `mismatch:variant:expected=[]:actual=['white_chocolate_macadamia_nut']`
- `mismatch:flavor:expected=['white_chocolate', 'macadamia_nut']:actual=[]`
- `mismatch:claims:expected=[]:actual=['gluten_free', 'high_protein']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Cookies > Cookies', 'Retail Taxonomy > Snack > Cookies > Cookies > @flavor > white_chocolate', 'Retail Taxonomy > Snack > Cookies > Cookies > @flavor > macadamia_nut']:actual=['Retail Taxonomy > Snack > Cookies > Cookies', 'Retail Taxonomy > Snack > Cookies > Cookies > @variant > white_chocolate_macadamia_nut', 'Retail Taxonomy > Snack > Cookies > Cookies > @claims > gluten_free', 'Retail Taxonomy > Snack > Cookies > Cookies > @claims > high_protein']`

---

## cauliflower_crust_pepperoni_pizza
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Frozen > Pizza"` | `"Meal > Pizza"` |
| `product_identity` | `"Pizza"` | `"Pizza"` |
| `canonical_path` * | `"Frozen > Pizza > Pizza"` | `"Meal > Pizza > Pizza"` |
| `variant` * | `["pepperoni"]` | `["pepperoni", "cauliflower_crust"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `["cauliflower_crust"]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` * | `["gluten_free"]` | `[]` |
| `canonical_label` * | `"Pizza (Pepperoni, Cauliflower Crust, Frozen, Gluten Free)"` | `"Pizza (Pepperoni, Cauliflower Crust, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Pizza > Pizza", "Retail Taxonomy > Frozen > Pizza > Pizza > @variant > pepperoni", "Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > cauliflower_crust", "Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen", "Retail Taxonomy > Frozen > Pizza > Pizza > @claims > gluten_free"]` | `["Retail Taxonomy > Meal > Pizza > Pizza", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > pepperoni", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > cauliflower_crust", "Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen", "Retail Taxonomy > Meal > Pizza > Pizza > @components > cauliflower_crust"]` |
| `components` * | `[]` | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Cauliflower Crust", "processing_storage": [], "role": "base", "variant": []}]` |

**core errors:**
- `core_mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `core_mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `core_mismatch:variant:expected=['pepperoni']:actual=['pepperoni', 'cauliflower_crust']`
- `core_mismatch:form_texture_cut:expected=['cauliflower_crust']:actual=[]`
- `core_mismatch:claims:expected=['gluten_free']:actual=[]`
- `core_mismatch:component_identities:expected=[]:actual=['cauliflower_crust']`

**exact errors:**
- `mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `mismatch:canonical_label:expected='Pizza (Pepperoni, Cauliflower Crust, Frozen, Gluten Free)':actual='Pizza (Pepperoni, Cauliflower Crust, Frozen)'`
- `mismatch:variant:expected=['pepperoni']:actual=['pepperoni', 'cauliflower_crust']`
- `mismatch:form_texture_cut:expected=['cauliflower_crust']:actual=[]`
- `mismatch:claims:expected=['gluten_free']:actual=[]`
- `mismatch:components:expected=[]:actual=[{'identity': 'Cauliflower Crust', 'role': 'base', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Pizza > Pizza', 'Retail Taxonomy > Frozen > Pizza > Pizza > @variant > pepperoni', 'Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > cauliflower_crust', 'Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Pizza > Pizza > @claims > gluten_free']:actual=['Retail Taxonomy > Meal > Pizza > Pizza', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > pepperoni', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > cauliflower_crust', 'Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen', 'Retail Taxonomy > Meal > Pizza > Pizza > @components > cauliflower_crust']`

---

## thin_crust_four_cheese_pizza
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Frozen > Pizza"` | `"Meal > Pizza"` |
| `product_identity` | `"Pizza"` | `"Pizza"` |
| `canonical_path` * | `"Frozen > Pizza > Pizza"` | `"Meal > Pizza > Pizza"` |
| `variant` * | `["four_cheese"]` | `["four_cheese", "thin_crust"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `["thin_crust"]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` * | `[]` | `["gluten_free"]` |
| `canonical_label` * | `"Pizza (Four Cheese, Thin Crust, Frozen)"` | `"Pizza (Four Cheese, Thin Crust, Frozen, Gluten Free)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Pizza > Pizza", "Retail Taxonomy > Frozen > Pizza > Pizza > @variant > four_cheese", "Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > thin_crust", "Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen"]` | `["Retail Taxonomy > Meal > Pizza > Pizza", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > four_cheese", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > thin_crust", "Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen", "Retail Taxonomy > Meal > Pizza > Pizza > @claims > gluten_free"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `core_mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `core_mismatch:variant:expected=['four_cheese']:actual=['four_cheese', 'thin_crust']`
- `core_mismatch:form_texture_cut:expected=['thin_crust']:actual=[]`
- `core_mismatch:claims:expected=[]:actual=['gluten_free']`

**exact errors:**
- `mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `mismatch:canonical_label:expected='Pizza (Four Cheese, Thin Crust, Frozen)':actual='Pizza (Four Cheese, Thin Crust, Frozen, Gluten Free)'`
- `mismatch:variant:expected=['four_cheese']:actual=['four_cheese', 'thin_crust']`
- `mismatch:form_texture_cut:expected=['thin_crust']:actual=[]`
- `mismatch:claims:expected=[]:actual=['gluten_free']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Pizza > Pizza', 'Retail Taxonomy > Frozen > Pizza > Pizza > @variant > four_cheese', 'Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > thin_crust', 'Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen']:actual=['Retail Taxonomy > Meal > Pizza > Pizza', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > four_cheese', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > thin_crust', 'Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen', 'Retail Taxonomy > Meal > Pizza > Pizza > @claims > gluten_free']`

---

## stuffed_crust_supreme_pizza
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Frozen > Pizza"` | `"Meal > Pizza"` |
| `product_identity` | `"Pizza"` | `"Pizza"` |
| `canonical_path` * | `"Frozen > Pizza > Pizza"` | `"Meal > Pizza > Pizza"` |
| `variant` * | `["supreme"]` | `["supreme", "stuffed_crust"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `["stuffed_crust"]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Pizza (Supreme, Stuffed Crust, Frozen)"` | `"Pizza (Supreme, Stuffed Crust, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Pizza > Pizza", "Retail Taxonomy > Frozen > Pizza > Pizza > @variant > supreme", "Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > stuffed_crust", "Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen"]` | `["Retail Taxonomy > Meal > Pizza > Pizza", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > supreme", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > stuffed_crust", "Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `core_mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `core_mismatch:variant:expected=['supreme']:actual=['supreme', 'stuffed_crust']`
- `core_mismatch:form_texture_cut:expected=['stuffed_crust']:actual=[]`

**exact errors:**
- `mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `mismatch:variant:expected=['supreme']:actual=['supreme', 'stuffed_crust']`
- `mismatch:form_texture_cut:expected=['stuffed_crust']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Pizza > Pizza', 'Retail Taxonomy > Frozen > Pizza > Pizza > @variant > supreme', 'Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > stuffed_crust', 'Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen']:actual=['Retail Taxonomy > Meal > Pizza > Pizza', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > supreme', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > stuffed_crust', 'Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen']`

---

## gluten_free_margherita_pizza
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Frozen > Pizza"` | `"Meal > Pizza"` |
| `product_identity` | `"Pizza"` | `"Pizza"` |
| `canonical_path` * | `"Frozen > Pizza > Pizza"` | `"Meal > Pizza > Pizza"` |
| `variant` | `["margherita"]` | `["margherita"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` * | `["gluten_free"]` | `["gluten_free", "organic"]` |
| `canonical_label` * | `"Pizza (Margherita, Frozen, Gluten Free)"` | `"Pizza (Margherita, Frozen, Gluten Free, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Pizza > Pizza", "Retail Taxonomy > Frozen > Pizza > Pizza > @variant > margherita", "Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen", "Retail Taxonomy > Frozen > Pizza > Pizza > @claims > gluten_free"]` | `["Retail Taxonomy > Meal > Pizza > Pizza", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > margherita", "Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen", "Retail Taxonomy > Meal > Pizza > Pizza > @claims > gluten_free", "Retail Taxonomy > Meal > Pizza > Pizza > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `core_mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `core_mismatch:claims:expected=['gluten_free']:actual=['gluten_free', 'organic']`

**exact errors:**
- `mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `mismatch:canonical_label:expected='Pizza (Margherita, Frozen, Gluten Free)':actual='Pizza (Margherita, Frozen, Gluten Free, Organic)'`
- `mismatch:claims:expected=['gluten_free']:actual=['gluten_free', 'organic']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Pizza > Pizza', 'Retail Taxonomy > Frozen > Pizza > Pizza > @variant > margherita', 'Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Pizza > Pizza > @claims > gluten_free']:actual=['Retail Taxonomy > Meal > Pizza > Pizza', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > margherita', 'Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen', 'Retail Taxonomy > Meal > Pizza > Pizza > @claims > gluten_free', 'Retail Taxonomy > Meal > Pizza > Pizza > @claims > organic']`

---

## detroit_style_deep_dish_pepperoni_pizza
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Frozen > Pizza"` | `"Meal > Pizza"` |
| `product_identity` | `"Pizza"` | `"Pizza"` |
| `canonical_path` * | `"Frozen > Pizza > Pizza"` | `"Meal > Pizza > Pizza"` |
| `variant` * | `["pepperoni"]` | `["detroit_style", "deep_dish", "pepperoni"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `["detroit_style", "deep_dish"]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Pizza (Pepperoni, Detroit Style, Deep Dish, Frozen)"` | `"Pizza (Detroit Style, Deep Dish, Pepperoni, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Pizza > Pizza", "Retail Taxonomy > Frozen > Pizza > Pizza > @variant > pepperoni", "Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > detroit_style", "Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > deep_dish", "Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen"]` | `["Retail Taxonomy > Meal > Pizza > Pizza", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > detroit_style", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > deep_dish", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > pepperoni", "Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `core_mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `core_mismatch:variant:expected=['pepperoni']:actual=['detroit_style', 'deep_dish', 'pepperoni']`
- `core_mismatch:form_texture_cut:expected=['detroit_style', 'deep_dish']:actual=[]`

**exact errors:**
- `mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `mismatch:canonical_label:expected='Pizza (Pepperoni, Detroit Style, Deep Dish, Frozen)':actual='Pizza (Detroit Style, Deep Dish, Pepperoni, Frozen)'`
- `mismatch:variant:expected=['pepperoni']:actual=['detroit_style', 'deep_dish', 'pepperoni']`
- `mismatch:form_texture_cut:expected=['detroit_style', 'deep_dish']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Pizza > Pizza', 'Retail Taxonomy > Frozen > Pizza > Pizza > @variant > pepperoni', 'Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > detroit_style', 'Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > deep_dish', 'Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen']:actual=['Retail Taxonomy > Meal > Pizza > Pizza', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > detroit_style', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > deep_dish', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > pepperoni', 'Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen']`

---

## french_bread_pepperoni_pizza
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Pizza"` | `"Frozen > Pizza"` |
| `product_identity` | `"French Bread Pizza"` | `"French Bread Pizza"` |
| `canonical_path` | `"Frozen > Pizza > French Bread Pizza"` | `"Frozen > Pizza > French Bread Pizza"` |
| `variant` | `["pepperoni"]` | `["pepperoni"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"French Bread Pizza (Pepperoni, Frozen)"` | `"French Bread Pizza (Pepperoni, Frozen)"` |
| `tree_paths` | `["Retail Taxonomy > Frozen > Pizza > French Bread Pizza", "Retail Taxonomy > Frozen > Pizza > French Bread Pizza > @variant > pepperoni", "Retail Taxonomy > Frozen > Pizza > French Bread Pizza > @processing_storage > frozen"]` | `["Retail Taxonomy > Frozen > Pizza > French Bread Pizza", "Retail Taxonomy > Frozen > Pizza > French Bread Pizza > @variant > pepperoni", "Retail Taxonomy > Frozen > Pizza > French Bread Pizza > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

---

## cauliflower_crust_bbq_chicken_pizza
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Frozen > Pizza"` | `"Meal > Pizza"` |
| `product_identity` | `"Pizza"` | `"Pizza"` |
| `canonical_path` * | `"Frozen > Pizza > Pizza"` | `"Meal > Pizza > Pizza"` |
| `variant` * | `["bbq_chicken"]` | `["cauliflower_crust", "bbq_chicken"]` |
| `flavor` * | `[]` | `["bbq"]` |
| `form_texture_cut` * | `["cauliflower_crust"]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` * | `["gluten_free"]` | `[]` |
| `canonical_label` * | `"Pizza (BBQ Chicken, Cauliflower Crust, Frozen, Gluten Free)"` | `"Pizza (Cauliflower Crust, BBQ Chicken, BBQ, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Pizza > Pizza", "Retail Taxonomy > Frozen > Pizza > Pizza > @variant > bbq_chicken", "Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > cauliflower_crust", "Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen", "Retail Taxonomy > Frozen > Pizza > Pizza > @claims > gluten_free"]` | `["Retail Taxonomy > Meal > Pizza > Pizza", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > cauliflower_crust", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > bbq_chicken", "Retail Taxonomy > Meal > Pizza > Pizza > @flavor > bbq", "Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen", "Retail Taxonomy > Meal > Pizza > Pizza > @components > cauliflower_crust"]` |
| `components` * | `[]` | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Cauliflower Crust", "processing_storage": [], "role": "base", "variant": []}]` |

**core errors:**
- `core_mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `core_mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `core_mismatch:variant:expected=['bbq_chicken']:actual=['cauliflower_crust', 'bbq_chicken']`
- `core_mismatch:flavor:expected=[]:actual=['bbq']`
- `core_mismatch:form_texture_cut:expected=['cauliflower_crust']:actual=[]`
- `core_mismatch:claims:expected=['gluten_free']:actual=[]`
- `core_mismatch:component_identities:expected=[]:actual=['cauliflower_crust']`

**exact errors:**
- `mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `mismatch:canonical_label:expected='Pizza (BBQ Chicken, Cauliflower Crust, Frozen, Gluten Free)':actual='Pizza (Cauliflower Crust, BBQ Chicken, BBQ, Frozen)'`
- `mismatch:variant:expected=['bbq_chicken']:actual=['cauliflower_crust', 'bbq_chicken']`
- `mismatch:flavor:expected=[]:actual=['bbq']`
- `mismatch:form_texture_cut:expected=['cauliflower_crust']:actual=[]`
- `mismatch:claims:expected=['gluten_free']:actual=[]`
- `mismatch:components:expected=[]:actual=[{'identity': 'Cauliflower Crust', 'role': 'base', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Pizza > Pizza', 'Retail Taxonomy > Frozen > Pizza > Pizza > @variant > bbq_chicken', 'Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > cauliflower_crust', 'Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Pizza > Pizza > @claims > gluten_free']:actual=['Retail Taxonomy > Meal > Pizza > Pizza', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > cauliflower_crust', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > bbq_chicken', 'Retail Taxonomy > Meal > Pizza > Pizza > @flavor > bbq', 'Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen', 'Retail Taxonomy > Meal > Pizza > Pizza > @components > cauliflower_crust']`

---

## personal_pepperoni_pizza
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Frozen > Pizza"` | `"Meal > Pizza"` |
| `product_identity` | `"Pizza"` | `"Pizza"` |
| `canonical_path` * | `"Frozen > Pizza > Pizza"` | `"Meal > Pizza > Pizza"` |
| `variant` * | `["pepperoni"]` | `["pepperoni", "personal_size"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `["personal_size"]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Pizza (Pepperoni, Personal Size, Frozen)"` | `"Pizza (Pepperoni, Personal Size, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Pizza > Pizza", "Retail Taxonomy > Frozen > Pizza > Pizza > @variant > pepperoni", "Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > personal_size", "Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen"]` | `["Retail Taxonomy > Meal > Pizza > Pizza", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > pepperoni", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > personal_size", "Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `core_mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `core_mismatch:variant:expected=['pepperoni']:actual=['pepperoni', 'personal_size']`
- `core_mismatch:form_texture_cut:expected=['personal_size']:actual=[]`

**exact errors:**
- `mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `mismatch:canonical_path:expected='Frozen > Pizza > Pizza':actual='Meal > Pizza > Pizza'`
- `mismatch:variant:expected=['pepperoni']:actual=['pepperoni', 'personal_size']`
- `mismatch:form_texture_cut:expected=['personal_size']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Pizza > Pizza', 'Retail Taxonomy > Frozen > Pizza > Pizza > @variant > pepperoni', 'Retail Taxonomy > Frozen > Pizza > Pizza > @form_texture_cut > personal_size', 'Retail Taxonomy > Frozen > Pizza > Pizza > @processing_storage > frozen']:actual=['Retail Taxonomy > Meal > Pizza > Pizza', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > pepperoni', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > personal_size', 'Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen']`

---

## hot_pocket_pepperoni
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"single"` | `"composite_dish"` |
| `category_path` * | `"Frozen > Stuffed Sandwiches"` | `"Meal > Sandwiches"` |
| `product_identity` * | `"Pizza Pocket"` | `"Sandwich"` |
| `canonical_path` * | `"Frozen > Stuffed Sandwiches > Pizza Pocket"` | `"Meal > Sandwiches > Sandwich"` |
| `variant` * | `["pepperoni"]` | `["stuffed", "pepperoni_pizza"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["stuffed"]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Pizza Pocket (Pepperoni, Frozen)"` | `"Sandwich (Stuffed, Pepperoni Pizza, Stuffed, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Stuffed Sandwiches > Pizza Pocket", "Retail Taxonomy > Frozen > Stuffed Sandwiches > Pizza Pocket > @variant > pepperoni", "Retail Taxonomy > Frozen > Stuffed Sandwiches > Pizza Pocket > @processing_storage > frozen"]` | `["Retail Taxonomy > Meal > Sandwiches > Sandwich", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > stuffed", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > pepperoni_pizza", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @form_texture_cut > stuffed", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @processing_storage > frozen", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > pepperoni", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > mozzarella_cheese", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > tomato_sauce", "Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > pizza_dough"]` |
| `components` * | `[]` | `[{"claims": [], "flavor": [], "form_texture_cut": ["sliced"], "identity": "Pepperoni", "processing_storage": [], "role": "protein", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": ["shredded"], "identity": "Mozzarella Cheese", "processing_storage": [], "role": "cheese", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Tomato Sauce", "processing_storage": [], "role": "sauce", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": ["pocket"], "identity": "Pizza Dough", "processing_storage": [], "role": "bread", "variant": []}]` |

**core errors:**
- `core_mismatch:retail_type:expected='single':actual='composite_dish'`
- `core_mismatch:category_path:expected='Frozen > Stuffed Sandwiches':actual='Meal > Sandwiches'`
- `core_mismatch:product_identity:expected='Pizza Pocket':actual='Sandwich'`
- `core_mismatch:canonical_path:expected='Frozen > Stuffed Sandwiches > Pizza Pocket':actual='Meal > Sandwiches > Sandwich'`
- `core_mismatch:variant:expected=['pepperoni']:actual=['stuffed', 'pepperoni_pizza']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['stuffed']`
- `core_mismatch:component_identities:expected=[]:actual=['mozzarella_cheese', 'pepperoni', 'pizza_dough', 'tomato_sauce']`

**exact errors:**
- `mismatch:retail_type:expected='single':actual='composite_dish'`
- `mismatch:category_path:expected='Frozen > Stuffed Sandwiches':actual='Meal > Sandwiches'`
- `mismatch:product_identity:expected='Pizza Pocket':actual='Sandwich'`
- `mismatch:canonical_path:expected='Frozen > Stuffed Sandwiches > Pizza Pocket':actual='Meal > Sandwiches > Sandwich'`
- `mismatch:canonical_label:expected='Pizza Pocket (Pepperoni, Frozen)':actual='Sandwich (Stuffed, Pepperoni Pizza, Stuffed, Frozen)'`
- `mismatch:variant:expected=['pepperoni']:actual=['stuffed', 'pepperoni_pizza']`
- `mismatch:form_texture_cut:expected=[]:actual=['stuffed']`
- `mismatch:components:expected=[]:actual=[{'identity': 'Pepperoni', 'role': 'protein', 'variant': [], 'flavor': [], 'form_texture_cut': ['sliced'], 'processing_storage': [], 'claims': []}, {'identity': 'Mozzarella Cheese', 'role': 'cheese', 'variant': [], 'flavor': [], 'form_texture_cut': ['shredded'], 'processing_storage': [], 'claims': []}, {'identity': 'Tomato Sauce', 'role': 'sauce', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Pizza Dough', 'role': 'bread', 'variant': [], 'flavor': [], 'form_texture_cut': ['pocket'], 'processing_storage': [], 'claims': []}]`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Stuffed Sandwiches > Pizza Pocket', 'Retail Taxonomy > Frozen > Stuffed Sandwiches > Pizza Pocket > @variant > pepperoni', 'Retail Taxonomy > Frozen > Stuffed Sandwiches > Pizza Pocket > @processing_storage > frozen']:actual=['Retail Taxonomy > Meal > Sandwiches > Sandwich', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > stuffed', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @variant > pepperoni_pizza', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @form_texture_cut > stuffed', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @processing_storage > frozen', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > pepperoni', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > mozzarella_cheese', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > tomato_sauce', 'Retail Taxonomy > Meal > Sandwiches > Sandwich > @components > pizza_dough']`

---

## frozen_garlic_bread_pizza
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Frozen > Pizza"` | `"Meal > Pizza"` |
| `product_identity` * | `"French Bread Pizza"` | `"Pizza"` |
| `canonical_path` * | `"Frozen > Pizza > French Bread Pizza"` | `"Meal > Pizza > Pizza"` |
| `variant` | `["garlic_bread"]` | `["garlic_bread"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"French Bread Pizza (Garlic Bread, Frozen)"` | `"Pizza (Garlic Bread, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Pizza > French Bread Pizza", "Retail Taxonomy > Frozen > Pizza > French Bread Pizza > @variant > garlic_bread", "Retail Taxonomy > Frozen > Pizza > French Bread Pizza > @processing_storage > frozen"]` | `["Retail Taxonomy > Meal > Pizza > Pizza", "Retail Taxonomy > Meal > Pizza > Pizza > @variant > garlic_bread", "Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `core_mismatch:product_identity:expected='French Bread Pizza':actual='Pizza'`
- `core_mismatch:canonical_path:expected='Frozen > Pizza > French Bread Pizza':actual='Meal > Pizza > Pizza'`

**exact errors:**
- `mismatch:category_path:expected='Frozen > Pizza':actual='Meal > Pizza'`
- `mismatch:product_identity:expected='French Bread Pizza':actual='Pizza'`
- `mismatch:canonical_path:expected='Frozen > Pizza > French Bread Pizza':actual='Meal > Pizza > Pizza'`
- `mismatch:canonical_label:expected='French Bread Pizza (Garlic Bread, Frozen)':actual='Pizza (Garlic Bread, Frozen)'`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Pizza > French Bread Pizza', 'Retail Taxonomy > Frozen > Pizza > French Bread Pizza > @variant > garlic_bread', 'Retail Taxonomy > Frozen > Pizza > French Bread Pizza > @processing_storage > frozen']:actual=['Retail Taxonomy > Meal > Pizza > Pizza', 'Retail Taxonomy > Meal > Pizza > Pizza > @variant > garlic_bread', 'Retail Taxonomy > Meal > Pizza > Pizza > @processing_storage > frozen']`

---

## newmans_skillet_meal_chicken_alfredo
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"meal_kit"` | `"single"` |
| `category_path` | `"Frozen > Skillet Meals"` | `"Frozen > Skillet Meals"` |
| `product_identity` | `"Skillet Meal"` | `"Skillet Meal"` |
| `canonical_path` | `"Frozen > Skillet Meals > Skillet Meal"` | `"Frozen > Skillet Meals > Skillet Meal"` |
| `variant` * | `["chicken_fettuccini_alfredo"]` | `["chicken_fettuccine_alfredo"]` |
| `flavor` * | `[]` | `["alfredo"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Skillet Meal (Chicken Fettuccini Alfredo, Frozen)"` | `"Skillet Meal (Chicken Fettuccine Alfredo, Alfredo, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal", "Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @variant > chicken_fettuccini_alfredo", "Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @processing_storage > frozen", "Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @components > chicken", "Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @components > fettuccini_pasta", "Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @components > alfredo_sauce"]` | `["Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal", "Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @variant > chicken_fettuccine_alfredo", "Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @flavor > alfredo", "Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @processing_storage > frozen"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Chicken", "processing_storage": [], "role": "protein", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Fettuccini Pasta", "processing_storage": [], "role": "base", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Alfredo Sauce", "processing_storage": [], "role": "sauce", "variant": []}]` | `[]` |

**core errors:**
- `core_mismatch:retail_type:expected='meal_kit':actual='single'`
- `core_mismatch:variant:expected=['chicken_fettuccini_alfredo']:actual=['chicken_fettuccine_alfredo']`
- `core_mismatch:flavor:expected=[]:actual=['alfredo']`
- `core_mismatch:component_identities:expected=['alfredo_sauce', 'chicken', 'fettuccini_pasta']:actual=[]`

**exact errors:**
- `mismatch:retail_type:expected='meal_kit':actual='single'`
- `mismatch:canonical_label:expected='Skillet Meal (Chicken Fettuccini Alfredo, Frozen)':actual='Skillet Meal (Chicken Fettuccine Alfredo, Alfredo, Frozen)'`
- `mismatch:variant:expected=['chicken_fettuccini_alfredo']:actual=['chicken_fettuccine_alfredo']`
- `mismatch:flavor:expected=[]:actual=['alfredo']`
- `mismatch:components:expected=[{'identity': 'Chicken', 'role': 'protein', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Fettuccini Pasta', 'role': 'base', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Alfredo Sauce', 'role': 'sauce', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal', 'Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @variant > chicken_fettuccini_alfredo', 'Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @components > chicken', 'Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @components > fettuccini_pasta', 'Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @components > alfredo_sauce']:actual=['Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal', 'Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @variant > chicken_fettuccine_alfredo', 'Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @flavor > alfredo', 'Retail Taxonomy > Frozen > Skillet Meals > Skillet Meal > @processing_storage > frozen']`

---

## banquet_meatloaf_mashed_potatoes_dinner
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"composite_dish"` | `"single"` |
| `category_path` | `"Frozen > TV Dinners"` | `"Frozen > TV Dinners"` |
| `product_identity` | `"TV Dinner"` | `"TV Dinner"` |
| `canonical_path` | `"Frozen > TV Dinners > TV Dinner"` | `"Frozen > TV Dinners > TV Dinner"` |
| `variant` | `["meatloaf_mashed_potatoes"]` | `["meatloaf_mashed_potatoes"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"TV Dinner (Meatloaf Mashed Potatoes, Frozen)"` | `"TV Dinner (Meatloaf Mashed Potatoes, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > TV Dinners > TV Dinner", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > meatloaf_mashed_potatoes", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @processing_storage > frozen", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > meatloaf", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > mashed_potatoes"]` | `["Retail Taxonomy > Frozen > TV Dinners > TV Dinner", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > meatloaf_mashed_potatoes", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @processing_storage > frozen"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Meatloaf", "processing_storage": [], "role": "protein", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Mashed Potatoes", "processing_storage": [], "role": "side", "variant": []}]` | `[]` |

**core errors:**
- `core_mismatch:retail_type:expected='composite_dish':actual='single'`
- `core_mismatch:component_identities:expected=['mashed_potatoes', 'meatloaf']:actual=[]`

**exact errors:**
- `mismatch:retail_type:expected='composite_dish':actual='single'`
- `mismatch:components:expected=[{'identity': 'Meatloaf', 'role': 'protein', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Mashed Potatoes', 'role': 'side', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > TV Dinners > TV Dinner', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > meatloaf_mashed_potatoes', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @processing_storage > frozen', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > meatloaf', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > mashed_potatoes']:actual=['Retail Taxonomy > Frozen > TV Dinners > TV Dinner', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > meatloaf_mashed_potatoes', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @processing_storage > frozen']`

---

## stouffers_lasagna_meat_sauce
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"composite_dish"` | `"single"` |
| `category_path` | `"Meal > Pasta Dishes"` | `"Meal > Pasta Dishes"` |
| `product_identity` | `"Lasagna"` | `"Lasagna"` |
| `canonical_path` | `"Meal > Pasta Dishes > Lasagna"` | `"Meal > Pasta Dishes > Lasagna"` |
| `variant` | `["meat_sauce"]` | `["meat_sauce"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Lasagna (Meat Sauce, Frozen)"` | `"Lasagna (Meat Sauce, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Meal > Pasta Dishes > Lasagna", "Retail Taxonomy > Meal > Pasta Dishes > Lasagna > @variant > meat_sauce", "Retail Taxonomy > Meal > Pasta Dishes > Lasagna > @processing_storage > frozen"]` | `["Retail Taxonomy > Meal > Pasta Dishes > Lasagna", "Retail Taxonomy > Meal > Pasta Dishes > Lasagna > @variant > meat_sauce", "Retail Taxonomy > Meal > Pasta Dishes > Lasagna > @processing_storage > frozen", "Retail Taxonomy > Meal > Pasta Dishes > Lasagna > @components > meat_sauce"]` |
| `components` * | `[]` | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Meat Sauce", "processing_storage": ["frozen"], "role": "sauce", "variant": []}]` |

**core errors:**
- `core_mismatch:retail_type:expected='composite_dish':actual='single'`
- `core_mismatch:component_identities:expected=[]:actual=['meat_sauce']`

**exact errors:**
- `mismatch:retail_type:expected='composite_dish':actual='single'`
- `mismatch:components:expected=[]:actual=[{'identity': 'Meat Sauce', 'role': 'sauce', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': ['frozen'], 'claims': []}]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Meal > Pasta Dishes > Lasagna', 'Retail Taxonomy > Meal > Pasta Dishes > Lasagna > @variant > meat_sauce', 'Retail Taxonomy > Meal > Pasta Dishes > Lasagna > @processing_storage > frozen']:actual=['Retail Taxonomy > Meal > Pasta Dishes > Lasagna', 'Retail Taxonomy > Meal > Pasta Dishes > Lasagna > @variant > meat_sauce', 'Retail Taxonomy > Meal > Pasta Dishes > Lasagna > @processing_storage > frozen', 'Retail Taxonomy > Meal > Pasta Dishes > Lasagna > @components > meat_sauce']`

---

## marie_callenders_chicken_pot_pie
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Pot Pies"` | `"Frozen > Pot Pies"` |
| `product_identity` | `"Pot Pie"` | `"Pot Pie"` |
| `canonical_path` | `"Frozen > Pot Pies > Pot Pie"` | `"Frozen > Pot Pies > Pot Pie"` |
| `variant` | `["chicken"]` | `["chicken"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Pot Pie (Chicken, Frozen)"` | `"Pot Pie (Chicken, Frozen)"` |
| `tree_paths` | `["Retail Taxonomy > Frozen > Pot Pies > Pot Pie", "Retail Taxonomy > Frozen > Pot Pies > Pot Pie > @variant > chicken", "Retail Taxonomy > Frozen > Pot Pies > Pot Pie > @processing_storage > frozen"]` | `["Retail Taxonomy > Frozen > Pot Pies > Pot Pie", "Retail Taxonomy > Frozen > Pot Pies > Pot Pie > @variant > chicken", "Retail Taxonomy > Frozen > Pot Pies > Pot Pie > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

---

## hungryman_salisbury_steak_dinner
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"composite_dish"` | `"frozen_meal"` |
| `category_path` | `"Frozen > TV Dinners"` | `"Frozen > TV Dinners"` |
| `product_identity` | `"TV Dinner"` | `"TV Dinner"` |
| `canonical_path` | `"Frozen > TV Dinners > TV Dinner"` | `"Frozen > TV Dinners > TV Dinner"` |
| `variant` * | `["salisbury_steak"]` | `["salisbury_steak", "mashed_potatoes", "corn", "brownie"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"TV Dinner (Salisbury Steak, Frozen)"` | `"TV Dinner (Salisbury Steak, Mashed Potatoes, Corn, Brownie, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > TV Dinners > TV Dinner", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > salisbury_steak", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @processing_storage > frozen", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > salisbury_steak", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > mashed_potatoes", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > brown_gravy"]` | `["Retail Taxonomy > Frozen > TV Dinners > TV Dinner", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > salisbury_steak", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > mashed_potatoes", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > corn", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > brownie", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @processing_storage > frozen", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > salisbury_steak", "Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > mashed_potatoes"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Salisbury Steak", "processing_storage": [], "role": "protein", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Mashed Potatoes", "processing_storage": [], "role": "side", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Brown Gravy", "processing_storage": [], "role": "sauce", "variant": []}]` | `[{"claims": [], "flavor": [], "form_texture_cut": ["patty"], "identity": "Salisbury Steak", "processing_storage": ["cooked"], "role": "main", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": ["creamy"], "identity": "Mashed Potatoes", "processing_storage": [], "role": "side", "variant": []}]` |

**core errors:**
- `invalid_retail_type:frozen_meal`
- `core_mismatch:retail_type:expected='composite_dish':actual='frozen_meal'`
- `core_mismatch:variant:expected=['salisbury_steak']:actual=['salisbury_steak', 'mashed_potatoes', 'corn', 'brownie']`
- `core_mismatch:component_identities:expected=['brown_gravy', 'mashed_potatoes', 'salisbury_steak']:actual=['mashed_potatoes', 'salisbury_steak']`

**exact errors:**
- `invalid_retail_type:frozen_meal`
- `mismatch:retail_type:expected='composite_dish':actual='frozen_meal'`
- `mismatch:canonical_label:expected='TV Dinner (Salisbury Steak, Frozen)':actual='TV Dinner (Salisbury Steak, Mashed Potatoes, Corn, Brownie, Frozen)'`
- `mismatch:variant:expected=['salisbury_steak']:actual=['salisbury_steak', 'mashed_potatoes', 'corn', 'brownie']`
- `mismatch:components:expected=[{'identity': 'Salisbury Steak', 'role': 'protein', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Mashed Potatoes', 'role': 'side', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Brown Gravy', 'role': 'sauce', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[{'identity': 'Salisbury Steak', 'role': 'main', 'variant': [], 'flavor': [], 'form_texture_cut': ['patty'], 'processing_storage': ['cooked'], 'claims': []}, {'identity': 'Mashed Potatoes', 'role': 'side', 'variant': [], 'flavor': [], 'form_texture_cut': ['creamy'], 'processing_storage': [], 'claims': []}]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > TV Dinners > TV Dinner', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > salisbury_steak', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @processing_storage > frozen', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > salisbury_steak', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > mashed_potatoes', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > brown_gravy']:actual=['Retail Taxonomy > Frozen > TV Dinners > TV Dinner', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > salisbury_steak', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > mashed_potatoes', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > corn', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @variant > brownie', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @processing_storage > frozen', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > salisbury_steak', 'Retail Taxonomy > Frozen > TV Dinners > TV Dinner > @components > mashed_potatoes']`

---

## lean_cuisine_garlic_beef
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Single Entrees"` | `"Frozen > Single Entrees"` |
| `product_identity` | `"Frozen Entree"` | `"Frozen Entree"` |
| `canonical_path` | `"Frozen > Single Entrees > Frozen Entree"` | `"Frozen > Single Entrees > Frozen Entree"` |
| `variant` * | `["garlic_beef_and_broccoli"]` | `["beef_and_broccoli"]` |
| `flavor` * | `[]` | `["garlic"]` |
| `form_texture_cut` * | `[]` | `["bowl"]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` * | `["low_calorie"]` | `[]` |
| `canonical_label` * | `"Frozen Entree (Garlic Beef And Broccoli, Frozen, Low Calorie)"` | `"Frozen Entree (Beef And Broccoli, Garlic, Bowl, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Single Entrees > Frozen Entree", "Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @variant > garlic_beef_and_broccoli", "Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @processing_storage > frozen", "Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @claims > low_calorie"]` | `["Retail Taxonomy > Frozen > Single Entrees > Frozen Entree", "Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @variant > beef_and_broccoli", "Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @flavor > garlic", "Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @form_texture_cut > bowl", "Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['garlic_beef_and_broccoli']:actual=['beef_and_broccoli']`
- `core_mismatch:flavor:expected=[]:actual=['garlic']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['bowl']`
- `core_mismatch:claims:expected=['low_calorie']:actual=[]`

**exact errors:**
- `mismatch:canonical_label:expected='Frozen Entree (Garlic Beef And Broccoli, Frozen, Low Calorie)':actual='Frozen Entree (Beef And Broccoli, Garlic, Bowl, Frozen)'`
- `mismatch:variant:expected=['garlic_beef_and_broccoli']:actual=['beef_and_broccoli']`
- `mismatch:flavor:expected=[]:actual=['garlic']`
- `mismatch:form_texture_cut:expected=[]:actual=['bowl']`
- `mismatch:claims:expected=['low_calorie']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Single Entrees > Frozen Entree', 'Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @variant > garlic_beef_and_broccoli', 'Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @claims > low_calorie']:actual=['Retail Taxonomy > Frozen > Single Entrees > Frozen Entree', 'Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @variant > beef_and_broccoli', 'Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @flavor > garlic', 'Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @form_texture_cut > bowl', 'Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @processing_storage > frozen']`

---

## amy_mac_and_cheese_bowl
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Single Entrees"` | `"Frozen > Single Entrees"` |
| `product_identity` | `"Mac and Cheese"` | `"Mac and Cheese"` |
| `canonical_path` | `"Frozen > Single Entrees > Mac and Cheese"` | `"Frozen > Single Entrees > Mac and Cheese"` |
| `variant` * | `[]` | `["pork", "bbq"]` |
| `flavor` * | `[]` | `["bbq", "smoke"]` |
| `form_texture_cut` * | `[]` | `["bowl"]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `["organic"]` | `["organic"]` |
| `canonical_label` * | `"Mac and Cheese (Frozen, Organic)"` | `"Mac and Cheese (Pork, BBQ, BBQ, Smoke, Bowl, Frozen, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese", "Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @processing_storage > frozen", "Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @claims > organic"]` | `["Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese", "Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @variant > pork", "Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @variant > bbq", "Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @flavor > bbq", "Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @flavor > smoke", "Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @form_texture_cut > bowl", "Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @processing_storage > frozen", "Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['pork', 'bbq']`
- `core_mismatch:flavor:expected=[]:actual=['bbq', 'smoke']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['bowl']`

**exact errors:**
- `mismatch:canonical_label:expected='Mac and Cheese (Frozen, Organic)':actual='Mac and Cheese (Pork, BBQ, BBQ, Smoke, Bowl, Frozen, Organic)'`
- `mismatch:variant:expected=[]:actual=['pork', 'bbq']`
- `mismatch:flavor:expected=[]:actual=['bbq', 'smoke']`
- `mismatch:form_texture_cut:expected=[]:actual=['bowl']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese', 'Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @claims > organic']:actual=['Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese', 'Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @variant > pork', 'Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @variant > bbq', 'Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @flavor > bbq', 'Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @flavor > smoke', 'Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @form_texture_cut > bowl', 'Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Single Entrees > Mac and Cheese > @claims > organic']`

---

## kids_meal_mac_cheese_nuggets_apples
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"combination_meal"` | `"composite_dish"` |
| `category_path` | `"Frozen > Kids Meals"` | `"Frozen > Kids Meals"` |
| `product_identity` | `"Kids Meal"` | `"Kids Meal"` |
| `canonical_path` | `"Frozen > Kids Meals > Kids Meal"` | `"Frozen > Kids Meals > Kids Meal"` |
| `variant` * | `[]` | `["mac_and_cheese", "chicken_nuggets", "apples"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Kids Meal (Frozen)"` | `"Kids Meal (Mac And Cheese, Chicken Nuggets, Apples, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Kids Meals > Kids Meal", "Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @processing_storage > frozen", "Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @components > mac_and_cheese", "Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @components > chicken_nuggets", "Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @components > apples"]` | `["Retail Taxonomy > Frozen > Kids Meals > Kids Meal", "Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @variant > mac_and_cheese", "Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @variant > chicken_nuggets", "Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @variant > apples", "Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @processing_storage > frozen", "Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @components > macaroni_and_cheese", "Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @components > chicken_nuggets"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Mac and Cheese", "processing_storage": [], "role": "main", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Chicken Nuggets", "processing_storage": [], "role": "protein", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Apples", "processing_storage": [], "role": "fruit", "variant": []}]` | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Macaroni and Cheese", "processing_storage": [], "role": "main", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": ["breaded"], "identity": "Chicken Nuggets", "processing_storage": ["fully_cooked"], "role": "protein", "variant": []}]` |

**core errors:**
- `core_mismatch:retail_type:expected='combination_meal':actual='composite_dish'`
- `core_mismatch:variant:expected=[]:actual=['mac_and_cheese', 'chicken_nuggets', 'apples']`
- `core_mismatch:component_identities:expected=['apples', 'chicken_nuggets', 'mac_and_cheese']:actual=['chicken_nuggets', 'macaroni_and_cheese']`

**exact errors:**
- `mismatch:retail_type:expected='combination_meal':actual='composite_dish'`
- `mismatch:canonical_label:expected='Kids Meal (Frozen)':actual='Kids Meal (Mac And Cheese, Chicken Nuggets, Apples, Frozen)'`
- `mismatch:variant:expected=[]:actual=['mac_and_cheese', 'chicken_nuggets', 'apples']`
- `mismatch:components:expected=[{'identity': 'Mac and Cheese', 'role': 'main', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Chicken Nuggets', 'role': 'protein', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Apples', 'role': 'fruit', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[{'identity': 'Macaroni and Cheese', 'role': 'main', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Chicken Nuggets', 'role': 'protein', 'variant': [], 'flavor': [], 'form_texture_cut': ['breaded'], 'processing_storage': ['fully_cooked'], 'claims': []}]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Kids Meals > Kids Meal', 'Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @components > mac_and_cheese', 'Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @components > chicken_nuggets', 'Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @components > apples']:actual=['Retail Taxonomy > Frozen > Kids Meals > Kids Meal', 'Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @variant > mac_and_cheese', 'Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @variant > chicken_nuggets', 'Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @variant > apples', 'Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @components > macaroni_and_cheese', 'Retail Taxonomy > Frozen > Kids Meals > Kids Meal > @components > chicken_nuggets']`

---

## pf_changs_beef_with_broccoli_frozen
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Frozen > Asian Meals"` | `"Frozen > Single Entrees"` |
| `product_identity` | `"Frozen Entree"` | `"Frozen Entree"` |
| `canonical_path` * | `"Frozen > Asian Meals > Frozen Entree"` | `"Frozen > Single Entrees > Frozen Entree"` |
| `variant` | `["beef_with_broccoli"]` | `["beef_with_broccoli"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["bowl"]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Frozen Entree (Beef With Broccoli, Frozen)"` | `"Frozen Entree (Beef With Broccoli, Bowl, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Asian Meals > Frozen Entree", "Retail Taxonomy > Frozen > Asian Meals > Frozen Entree > @variant > beef_with_broccoli", "Retail Taxonomy > Frozen > Asian Meals > Frozen Entree > @processing_storage > frozen"]` | `["Retail Taxonomy > Frozen > Single Entrees > Frozen Entree", "Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @variant > beef_with_broccoli", "Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @form_texture_cut > bowl", "Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Frozen > Asian Meals':actual='Frozen > Single Entrees'`
- `core_mismatch:canonical_path:expected='Frozen > Asian Meals > Frozen Entree':actual='Frozen > Single Entrees > Frozen Entree'`
- `core_mismatch:form_texture_cut:expected=[]:actual=['bowl']`

**exact errors:**
- `mismatch:category_path:expected='Frozen > Asian Meals':actual='Frozen > Single Entrees'`
- `mismatch:canonical_path:expected='Frozen > Asian Meals > Frozen Entree':actual='Frozen > Single Entrees > Frozen Entree'`
- `mismatch:canonical_label:expected='Frozen Entree (Beef With Broccoli, Frozen)':actual='Frozen Entree (Beef With Broccoli, Bowl, Frozen)'`
- `mismatch:form_texture_cut:expected=[]:actual=['bowl']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Asian Meals > Frozen Entree', 'Retail Taxonomy > Frozen > Asian Meals > Frozen Entree > @variant > beef_with_broccoli', 'Retail Taxonomy > Frozen > Asian Meals > Frozen Entree > @processing_storage > frozen']:actual=['Retail Taxonomy > Frozen > Single Entrees > Frozen Entree', 'Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @variant > beef_with_broccoli', 'Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @form_texture_cut > bowl', 'Retail Taxonomy > Frozen > Single Entrees > Frozen Entree > @processing_storage > frozen']`

---

## stouffers_french_bread_pizza_pepperoni
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Pizza"` | `"Frozen > Pizza"` |
| `product_identity` | `"French Bread Pizza"` | `"French Bread Pizza"` |
| `canonical_path` | `"Frozen > Pizza > French Bread Pizza"` | `"Frozen > Pizza > French Bread Pizza"` |
| `variant` | `["pepperoni"]` | `["pepperoni"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"French Bread Pizza (Pepperoni, Frozen)"` | `"French Bread Pizza (Pepperoni, Frozen)"` |
| `tree_paths` | `["Retail Taxonomy > Frozen > Pizza > French Bread Pizza", "Retail Taxonomy > Frozen > Pizza > French Bread Pizza > @variant > pepperoni", "Retail Taxonomy > Frozen > Pizza > French Bread Pizza > @processing_storage > frozen"]` | `["Retail Taxonomy > Frozen > Pizza > French Bread Pizza", "Retail Taxonomy > Frozen > Pizza > French Bread Pizza > @variant > pepperoni", "Retail Taxonomy > Frozen > Pizza > French Bread Pizza > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

---

## tropical_trail_mix
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Trail Mix"` | `"Snack > Trail Mix"` |
| `product_identity` | `"Trail Mix"` | `"Trail Mix"` |
| `canonical_path` | `"Snack > Trail Mix > Trail Mix"` | `"Snack > Trail Mix > Trail Mix"` |
| `variant` * | `["tropical"]` | `["tropical", "almonds"]` |
| `flavor` * | `[]` | `["mango", "pineapple", "coconut"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Trail Mix (Tropical)"` | `"Trail Mix (Tropical, Almonds, Mango, Pineapple, Coconut)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > tropical"]` | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > tropical", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > almonds", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > mango", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > pineapple", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > coconut"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['tropical']:actual=['tropical', 'almonds']`
- `core_mismatch:flavor:expected=[]:actual=['mango', 'pineapple', 'coconut']`

**exact errors:**
- `mismatch:canonical_label:expected='Trail Mix (Tropical)':actual='Trail Mix (Tropical, Almonds, Mango, Pineapple, Coconut)'`
- `mismatch:variant:expected=['tropical']:actual=['tropical', 'almonds']`
- `mismatch:flavor:expected=[]:actual=['mango', 'pineapple', 'coconut']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > tropical']:actual=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > tropical', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > almonds', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > mango', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > pineapple', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > coconut']`

---

## energy_trail_mix_pb_raisin_mm
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Trail Mix"` | `"Snack > Trail Mix"` |
| `product_identity` | `"Trail Mix"` | `"Trail Mix"` |
| `canonical_path` | `"Snack > Trail Mix > Trail Mix"` | `"Snack > Trail Mix > Trail Mix"` |
| `variant` * | `["energy"]` | `["peanut", "raisin", "m_and_m_s"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["high_protein", "organic"]` |
| `canonical_label` * | `"Trail Mix (Energy)"` | `"Trail Mix (Peanut, Raisin, M And M S, High Protein, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > energy"]` | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > peanut", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > raisin", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > m_and_m_s", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > high_protein", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['energy']:actual=['peanut', 'raisin', 'm_and_m_s']`
- `core_mismatch:claims:expected=[]:actual=['high_protein', 'organic']`

**exact errors:**
- `mismatch:canonical_label:expected='Trail Mix (Energy)':actual='Trail Mix (Peanut, Raisin, M And M S, High Protein, Organic)'`
- `mismatch:variant:expected=['energy']:actual=['peanut', 'raisin', 'm_and_m_s']`
- `mismatch:claims:expected=[]:actual=['high_protein', 'organic']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > energy']:actual=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > peanut', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > raisin', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > m_and_m_s', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > high_protein', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > organic']`

---

## mixed_nuts_no_peanuts
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Nuts"` | `"Snack > Nuts"` |
| `product_identity` | `"Mixed Nuts"` | `"Mixed Nuts"` |
| `canonical_path` | `"Snack > Nuts > Mixed Nuts"` | `"Snack > Nuts > Mixed Nuts"` |
| `variant` * | `[]` | `["no_peanuts"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["dry_roasted"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["peanut_free"]` | `[]` |
| `canonical_label` * | `"Mixed Nuts (Peanut Free)"` | `"Mixed Nuts (No Peanuts, Dry Roasted)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Nuts > Mixed Nuts", "Retail Taxonomy > Snack > Nuts > Mixed Nuts > @claims > peanut_free"]` | `["Retail Taxonomy > Snack > Nuts > Mixed Nuts", "Retail Taxonomy > Snack > Nuts > Mixed Nuts > @variant > no_peanuts", "Retail Taxonomy > Snack > Nuts > Mixed Nuts > @form_texture_cut > dry_roasted"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['no_peanuts']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['dry_roasted']`
- `core_mismatch:claims:expected=['peanut_free']:actual=[]`

**exact errors:**
- `mismatch:canonical_label:expected='Mixed Nuts (Peanut Free)':actual='Mixed Nuts (No Peanuts, Dry Roasted)'`
- `mismatch:variant:expected=[]:actual=['no_peanuts']`
- `mismatch:form_texture_cut:expected=[]:actual=['dry_roasted']`
- `mismatch:claims:expected=['peanut_free']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Nuts > Mixed Nuts', 'Retail Taxonomy > Snack > Nuts > Mixed Nuts > @claims > peanut_free']:actual=['Retail Taxonomy > Snack > Nuts > Mixed Nuts', 'Retail Taxonomy > Snack > Nuts > Mixed Nuts > @variant > no_peanuts', 'Retail Taxonomy > Snack > Nuts > Mixed Nuts > @form_texture_cut > dry_roasted']`

---

## sweet_and_salty_trail_mix
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Trail Mix"` | `"Snack > Trail Mix"` |
| `product_identity` | `"Trail Mix"` | `"Trail Mix"` |
| `canonical_path` | `"Snack > Trail Mix > Trail Mix"` | `"Snack > Trail Mix > Trail Mix"` |
| `variant` * | `["sweet_and_salty"]` | `[]` |
| `flavor` * | `[]` | `["sweet", "salty"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Trail Mix (Sweet And Salty)"` | `"Trail Mix (Sweet, Salty)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > sweet_and_salty"]` | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > sweet", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > salty"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['sweet_and_salty']:actual=[]`
- `core_mismatch:flavor:expected=[]:actual=['sweet', 'salty']`

**exact errors:**
- `mismatch:canonical_label:expected='Trail Mix (Sweet And Salty)':actual='Trail Mix (Sweet, Salty)'`
- `mismatch:variant:expected=['sweet_and_salty']:actual=[]`
- `mismatch:flavor:expected=[]:actual=['sweet', 'salty']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > sweet_and_salty']:actual=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > sweet', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > salty']`

---

## fruit_and_nut_mix
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Trail Mix"` | `"Snack > Trail Mix"` |
| `product_identity` | `"Trail Mix"` | `"Trail Mix"` |
| `canonical_path` | `"Snack > Trail Mix > Trail Mix"` | `"Snack > Trail Mix > Trail Mix"` |
| `variant` * | `["fruit_and_nut"]` | `["fruit_nut", "super_berry"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Trail Mix (Fruit And Nut)"` | `"Trail Mix (Fruit Nut, Super Berry)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > fruit_and_nut"]` | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > fruit_nut", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > super_berry"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['fruit_and_nut']:actual=['fruit_nut', 'super_berry']`

**exact errors:**
- `mismatch:canonical_label:expected='Trail Mix (Fruit And Nut)':actual='Trail Mix (Fruit Nut, Super Berry)'`
- `mismatch:variant:expected=['fruit_and_nut']:actual=['fruit_nut', 'super_berry']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > fruit_and_nut']:actual=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > fruit_nut', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > super_berry']`

---

## boneless_skinless_chicken_breast
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Meat & Seafood > Poultry"` | `"Meat & Seafood > Poultry"` |
| `product_identity` | `"Chicken Breast"` | `"Chicken Breast"` |
| `canonical_path` | `"Meat & Seafood > Poultry > Chicken Breast"` | `"Meat & Seafood > Poultry > Chicken Breast"` |
| `variant` | `[]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `["boneless", "skinless"]` | `["fillet", "boneless", "skinless"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Chicken Breast (Boneless, Skinless)"` | `"Chicken Breast (Fillet, Boneless, Skinless)"` |
| `tree_paths` * | `["Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast > @form_texture_cut > boneless", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast > @form_texture_cut > skinless"]` | `["Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast > @form_texture_cut > fillet", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast > @form_texture_cut > boneless", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast > @form_texture_cut > skinless"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:form_texture_cut:expected=['boneless', 'skinless']:actual=['fillet', 'boneless', 'skinless']`

**exact errors:**
- `mismatch:canonical_label:expected='Chicken Breast (Boneless, Skinless)':actual='Chicken Breast (Fillet, Boneless, Skinless)'`
- `mismatch:form_texture_cut:expected=['boneless', 'skinless']:actual=['fillet', 'boneless', 'skinless']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast > @form_texture_cut > boneless', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast > @form_texture_cut > skinless']:actual=['Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast > @form_texture_cut > fillet', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast > @form_texture_cut > boneless', 'Retail Taxonomy > Meat & Seafood > Poultry > Chicken Breast > @form_texture_cut > skinless']`

---

## bone_in_pork_chops
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Meat & Seafood > Pork"` | `"Meat & Seafood > Pork"` |
| `product_identity` | `"Pork Chops"` | `"Pork Chops"` |
| `canonical_path` | `"Meat & Seafood > Pork > Pork Chops"` | `"Meat & Seafood > Pork > Pork Chops"` |
| `variant` | `[]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `["bone_in"]` | `["chop", "bone_in"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Pork Chops (Bone In)"` | `"Pork Chops (Chop, Bone In)"` |
| `tree_paths` * | `["Retail Taxonomy > Meat & Seafood > Pork > Pork Chops", "Retail Taxonomy > Meat & Seafood > Pork > Pork Chops > @form_texture_cut > bone_in"]` | `["Retail Taxonomy > Meat & Seafood > Pork > Pork Chops", "Retail Taxonomy > Meat & Seafood > Pork > Pork Chops > @form_texture_cut > chop", "Retail Taxonomy > Meat & Seafood > Pork > Pork Chops > @form_texture_cut > bone_in"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:form_texture_cut:expected=['bone_in']:actual=['chop', 'bone_in']`

**exact errors:**
- `mismatch:canonical_label:expected='Pork Chops (Bone In)':actual='Pork Chops (Chop, Bone In)'`
- `mismatch:form_texture_cut:expected=['bone_in']:actual=['chop', 'bone_in']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Meat & Seafood > Pork > Pork Chops', 'Retail Taxonomy > Meat & Seafood > Pork > Pork Chops > @form_texture_cut > bone_in']:actual=['Retail Taxonomy > Meat & Seafood > Pork > Pork Chops', 'Retail Taxonomy > Meat & Seafood > Pork > Pork Chops > @form_texture_cut > chop', 'Retail Taxonomy > Meat & Seafood > Pork > Pork Chops > @form_texture_cut > bone_in']`

---

## ground_beef_80_20
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Meat & Seafood > Beef"` | `"Meat & Seafood > Beef"` |
| `product_identity` | `"Ground Beef"` | `"Ground Beef"` |
| `canonical_path` | `"Meat & Seafood > Beef > Ground Beef"` | `"Meat & Seafood > Beef > Ground Beef"` |
| `variant` | `["80_20"]` | `["80_20"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Ground Beef (80 20)"` | `"Ground Beef (80 20)"` |
| `tree_paths` | `["Retail Taxonomy > Meat & Seafood > Beef > Ground Beef", "Retail Taxonomy > Meat & Seafood > Beef > Ground Beef > @variant > 80_20"]` | `["Retail Taxonomy > Meat & Seafood > Beef > Ground Beef", "Retail Taxonomy > Meat & Seafood > Beef > Ground Beef > @variant > 80_20"]` |
| `components` | `[]` | `[]` |

---

## ground_turkey_93_7
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Meat & Seafood > Poultry"` | `"Meat & Seafood > Poultry"` |
| `product_identity` | `"Ground Turkey"` | `"Ground Turkey"` |
| `canonical_path` | `"Meat & Seafood > Poultry > Ground Turkey"` | `"Meat & Seafood > Poultry > Ground Turkey"` |
| `variant` | `["93_7"]` | `["93_7"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `[]` | `["raw"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Ground Turkey (93 7)"` | `"Ground Turkey (93 7, Raw)"` |
| `tree_paths` * | `["Retail Taxonomy > Meat & Seafood > Poultry > Ground Turkey", "Retail Taxonomy > Meat & Seafood > Poultry > Ground Turkey > @variant > 93_7"]` | `["Retail Taxonomy > Meat & Seafood > Poultry > Ground Turkey", "Retail Taxonomy > Meat & Seafood > Poultry > Ground Turkey > @variant > 93_7", "Retail Taxonomy > Meat & Seafood > Poultry > Ground Turkey > @processing_storage > raw"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:processing_storage:expected=[]:actual=['raw']`

**exact errors:**
- `mismatch:canonical_label:expected='Ground Turkey (93 7)':actual='Ground Turkey (93 7, Raw)'`
- `mismatch:processing_storage:expected=[]:actual=['raw']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Meat & Seafood > Poultry > Ground Turkey', 'Retail Taxonomy > Meat & Seafood > Poultry > Ground Turkey > @variant > 93_7']:actual=['Retail Taxonomy > Meat & Seafood > Poultry > Ground Turkey', 'Retail Taxonomy > Meat & Seafood > Poultry > Ground Turkey > @variant > 93_7', 'Retail Taxonomy > Meat & Seafood > Poultry > Ground Turkey > @processing_storage > raw']`

---

## boneless_pork_ribs
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Meat & Seafood > Pork"` | `"Meat & Seafood > Pork"` |
| `product_identity` | `"Pork Ribs"` | `"Pork Ribs"` |
| `canonical_path` | `"Meat & Seafood > Pork > Pork Ribs"` | `"Meat & Seafood > Pork > Pork Ribs"` |
| `variant` | `["country_style"]` | `["country_style"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `["boneless"]` | `["boneless"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["organic"]` |
| `canonical_label` * | `"Pork Ribs (Country Style, Boneless)"` | `"Pork Ribs (Country Style, Boneless, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs", "Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs > @variant > country_style", "Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs > @form_texture_cut > boneless"]` | `["Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs", "Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs > @variant > country_style", "Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs > @form_texture_cut > boneless", "Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:claims:expected=[]:actual=['organic']`

**exact errors:**
- `mismatch:canonical_label:expected='Pork Ribs (Country Style, Boneless)':actual='Pork Ribs (Country Style, Boneless, Organic)'`
- `mismatch:claims:expected=[]:actual=['organic']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs', 'Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs > @variant > country_style', 'Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs > @form_texture_cut > boneless']:actual=['Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs', 'Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs > @variant > country_style', 'Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs > @form_texture_cut > boneless', 'Retail Taxonomy > Meat & Seafood > Pork > Pork Ribs > @claims > organic']`

---

## skirt_steak
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Meat & Seafood > Beef"` | `"Meat & Seafood > Beef"` |
| `product_identity` | `"Skirt Steak"` | `"Skirt Steak"` |
| `canonical_path` | `"Meat & Seafood > Beef > Skirt Steak"` | `"Meat & Seafood > Beef > Skirt Steak"` |
| `variant` * | `[]` | `["angus"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["grilled"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Skirt Steak"` | `"Skirt Steak (Angus, Grilled)"` |
| `tree_paths` * | `["Retail Taxonomy > Meat & Seafood > Beef > Skirt Steak"]` | `["Retail Taxonomy > Meat & Seafood > Beef > Skirt Steak", "Retail Taxonomy > Meat & Seafood > Beef > Skirt Steak > @variant > angus", "Retail Taxonomy > Meat & Seafood > Beef > Skirt Steak > @form_texture_cut > grilled"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['angus']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['grilled']`

**exact errors:**
- `mismatch:canonical_label:expected='Skirt Steak':actual='Skirt Steak (Angus, Grilled)'`
- `mismatch:variant:expected=[]:actual=['angus']`
- `mismatch:form_texture_cut:expected=[]:actual=['grilled']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Meat & Seafood > Beef > Skirt Steak']:actual=['Retail Taxonomy > Meat & Seafood > Beef > Skirt Steak', 'Retail Taxonomy > Meat & Seafood > Beef > Skirt Steak > @variant > angus', 'Retail Taxonomy > Meat & Seafood > Beef > Skirt Steak > @form_texture_cut > grilled']`

---

## filet_mignon_beef_tenderloin
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Meat & Seafood > Beef"` | `"Meat & Seafood > Beef"` |
| `product_identity` * | `"Filet Mignon"` | `"Beef Steak"` |
| `canonical_path` * | `"Meat & Seafood > Beef > Filet Mignon"` | `"Meat & Seafood > Beef > Beef Steak"` |
| `variant` * | `[]` | `["filet_mignon", "tenderloin"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Filet Mignon"` | `"Beef Steak (Filet Mignon, Tenderloin)"` |
| `tree_paths` * | `["Retail Taxonomy > Meat & Seafood > Beef > Filet Mignon"]` | `["Retail Taxonomy > Meat & Seafood > Beef > Beef Steak", "Retail Taxonomy > Meat & Seafood > Beef > Beef Steak > @variant > filet_mignon", "Retail Taxonomy > Meat & Seafood > Beef > Beef Steak > @variant > tenderloin"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Filet Mignon':actual='Beef Steak'`
- `core_mismatch:canonical_path:expected='Meat & Seafood > Beef > Filet Mignon':actual='Meat & Seafood > Beef > Beef Steak'`
- `core_mismatch:variant:expected=[]:actual=['filet_mignon', 'tenderloin']`

**exact errors:**
- `mismatch:product_identity:expected='Filet Mignon':actual='Beef Steak'`
- `mismatch:canonical_path:expected='Meat & Seafood > Beef > Filet Mignon':actual='Meat & Seafood > Beef > Beef Steak'`
- `mismatch:canonical_label:expected='Filet Mignon':actual='Beef Steak (Filet Mignon, Tenderloin)'`
- `mismatch:variant:expected=[]:actual=['filet_mignon', 'tenderloin']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Meat & Seafood > Beef > Filet Mignon']:actual=['Retail Taxonomy > Meat & Seafood > Beef > Beef Steak', 'Retail Taxonomy > Meat & Seafood > Beef > Beef Steak > @variant > filet_mignon', 'Retail Taxonomy > Meat & Seafood > Beef > Beef Steak > @variant > tenderloin']`

---

## whole_chicken
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Meat & Seafood > Poultry"` | `"Meat & Seafood > Poultry"` |
| `product_identity` | `"Whole Chicken"` | `"Whole Chicken"` |
| `canonical_path` | `"Meat & Seafood > Poultry > Whole Chicken"` | `"Meat & Seafood > Poultry > Whole Chicken"` |
| `variant` * | `[]` | `["young"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `["whole"]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["organic"]` |
| `canonical_label` * | `"Whole Chicken (Whole)"` | `"Whole Chicken (Young, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Meat & Seafood > Poultry > Whole Chicken", "Retail Taxonomy > Meat & Seafood > Poultry > Whole Chicken > @form_texture_cut > whole"]` | `["Retail Taxonomy > Meat & Seafood > Poultry > Whole Chicken", "Retail Taxonomy > Meat & Seafood > Poultry > Whole Chicken > @variant > young", "Retail Taxonomy > Meat & Seafood > Poultry > Whole Chicken > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['young']`
- `core_mismatch:form_texture_cut:expected=['whole']:actual=[]`
- `core_mismatch:claims:expected=[]:actual=['organic']`

**exact errors:**
- `mismatch:canonical_label:expected='Whole Chicken (Whole)':actual='Whole Chicken (Young, Organic)'`
- `mismatch:variant:expected=[]:actual=['young']`
- `mismatch:form_texture_cut:expected=['whole']:actual=[]`
- `mismatch:claims:expected=[]:actual=['organic']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Meat & Seafood > Poultry > Whole Chicken', 'Retail Taxonomy > Meat & Seafood > Poultry > Whole Chicken > @form_texture_cut > whole']:actual=['Retail Taxonomy > Meat & Seafood > Poultry > Whole Chicken', 'Retail Taxonomy > Meat & Seafood > Poultry > Whole Chicken > @variant > young', 'Retail Taxonomy > Meat & Seafood > Poultry > Whole Chicken > @claims > organic']`

---

## chicken_thighs_bone_in_skin_on
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Meat & Seafood > Poultry"` | `"Meat & Seafood > Poultry"` |
| `product_identity` | `"Chicken Thighs"` | `"Chicken Thighs"` |
| `canonical_path` | `"Meat & Seafood > Poultry > Chicken Thighs"` | `"Meat & Seafood > Poultry > Chicken Thighs"` |
| `variant` | `[]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `["bone_in", "skin_on"]` | `["bone_in", "skin_on"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Chicken Thighs (Bone In, Skin On)"` | `"Chicken Thighs (Bone In, Skin On)"` |
| `tree_paths` | `["Retail Taxonomy > Meat & Seafood > Poultry > Chicken Thighs", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Thighs > @form_texture_cut > bone_in", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Thighs > @form_texture_cut > skin_on"]` | `["Retail Taxonomy > Meat & Seafood > Poultry > Chicken Thighs", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Thighs > @form_texture_cut > bone_in", "Retail Taxonomy > Meat & Seafood > Poultry > Chicken Thighs > @form_texture_cut > skin_on"]` |
| `components` | `[]` | `[]` |

---

## ribeye_steak
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Meat & Seafood > Beef"` | `"Meat & Seafood > Beef"` |
| `product_identity` | `"Ribeye Steak"` | `"Ribeye Steak"` |
| `canonical_path` | `"Meat & Seafood > Beef > Ribeye Steak"` | `"Meat & Seafood > Beef > Ribeye Steak"` |
| `variant` | `[]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `["bone_in"]` | `["bone_in"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["organic"]` |
| `canonical_label` * | `"Ribeye Steak (Bone In)"` | `"Ribeye Steak (Bone In, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Meat & Seafood > Beef > Ribeye Steak", "Retail Taxonomy > Meat & Seafood > Beef > Ribeye Steak > @form_texture_cut > bone_in"]` | `["Retail Taxonomy > Meat & Seafood > Beef > Ribeye Steak", "Retail Taxonomy > Meat & Seafood > Beef > Ribeye Steak > @form_texture_cut > bone_in", "Retail Taxonomy > Meat & Seafood > Beef > Ribeye Steak > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:claims:expected=[]:actual=['organic']`

**exact errors:**
- `mismatch:canonical_label:expected='Ribeye Steak (Bone In)':actual='Ribeye Steak (Bone In, Organic)'`
- `mismatch:claims:expected=[]:actual=['organic']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Meat & Seafood > Beef > Ribeye Steak', 'Retail Taxonomy > Meat & Seafood > Beef > Ribeye Steak > @form_texture_cut > bone_in']:actual=['Retail Taxonomy > Meat & Seafood > Beef > Ribeye Steak', 'Retail Taxonomy > Meat & Seafood > Beef > Ribeye Steak > @form_texture_cut > bone_in', 'Retail Taxonomy > Meat & Seafood > Beef > Ribeye Steak > @claims > organic']`

---

## strawberry_whole_milk
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Dairy > Flavored Milk"` | `"Beverage > Plant Milk"` |
| `product_identity` * | `"Strawberry Milk"` | `"Coconut Milk Drink"` |
| `canonical_path` * | `"Dairy > Flavored Milk > Strawberry Milk"` | `"Beverage > Plant Milk > Coconut Milk Drink"` |
| `variant` * | `["whole"]` | `[]` |
| `flavor` * | `[]` | `["strawberry"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Strawberry Milk (Whole)"` | `"Coconut Milk Drink (Strawberry)"` |
| `tree_paths` * | `["Retail Taxonomy > Dairy > Flavored Milk > Strawberry Milk", "Retail Taxonomy > Dairy > Flavored Milk > Strawberry Milk > @variant > whole"]` | `["Retail Taxonomy > Beverage > Plant Milk > Coconut Milk Drink", "Retail Taxonomy > Beverage > Plant Milk > Coconut Milk Drink > @flavor > strawberry"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Dairy > Flavored Milk':actual='Beverage > Plant Milk'`
- `core_mismatch:product_identity:expected='Strawberry Milk':actual='Coconut Milk Drink'`
- `core_mismatch:canonical_path:expected='Dairy > Flavored Milk > Strawberry Milk':actual='Beverage > Plant Milk > Coconut Milk Drink'`
- `core_mismatch:variant:expected=['whole']:actual=[]`
- `core_mismatch:flavor:expected=[]:actual=['strawberry']`

**exact errors:**
- `mismatch:category_path:expected='Dairy > Flavored Milk':actual='Beverage > Plant Milk'`
- `mismatch:product_identity:expected='Strawberry Milk':actual='Coconut Milk Drink'`
- `mismatch:canonical_path:expected='Dairy > Flavored Milk > Strawberry Milk':actual='Beverage > Plant Milk > Coconut Milk Drink'`
- `mismatch:canonical_label:expected='Strawberry Milk (Whole)':actual='Coconut Milk Drink (Strawberry)'`
- `mismatch:variant:expected=['whole']:actual=[]`
- `mismatch:flavor:expected=[]:actual=['strawberry']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Dairy > Flavored Milk > Strawberry Milk', 'Retail Taxonomy > Dairy > Flavored Milk > Strawberry Milk > @variant > whole']:actual=['Retail Taxonomy > Beverage > Plant Milk > Coconut Milk Drink', 'Retail Taxonomy > Beverage > Plant Milk > Coconut Milk Drink > @flavor > strawberry']`

---

## vanilla_lowfat_milk
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Dairy > Flavored Milk"` | `"Beverage > Dairy Milk"` |
| `product_identity` * | `"Vanilla Milk"` | `"Milk"` |
| `canonical_path` * | `"Dairy > Flavored Milk > Vanilla Milk"` | `"Beverage > Dairy Milk > Milk"` |
| `variant` * | `["1_percent"]` | `[]` |
| `flavor` * | `[]` | `["vanilla"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["low_fat"]` | `["low_fat", "organic"]` |
| `canonical_label` * | `"Vanilla Milk (1 Percent, Low Fat)"` | `"Milk (Vanilla, Low Fat, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Dairy > Flavored Milk > Vanilla Milk", "Retail Taxonomy > Dairy > Flavored Milk > Vanilla Milk > @variant > 1_percent", "Retail Taxonomy > Dairy > Flavored Milk > Vanilla Milk > @claims > low_fat"]` | `["Retail Taxonomy > Beverage > Dairy Milk > Milk", "Retail Taxonomy > Beverage > Dairy Milk > Milk > @flavor > vanilla", "Retail Taxonomy > Beverage > Dairy Milk > Milk > @claims > low_fat", "Retail Taxonomy > Beverage > Dairy Milk > Milk > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Dairy > Flavored Milk':actual='Beverage > Dairy Milk'`
- `core_mismatch:product_identity:expected='Vanilla Milk':actual='Milk'`
- `core_mismatch:canonical_path:expected='Dairy > Flavored Milk > Vanilla Milk':actual='Beverage > Dairy Milk > Milk'`
- `core_mismatch:variant:expected=['1_percent']:actual=[]`
- `core_mismatch:flavor:expected=[]:actual=['vanilla']`
- `core_mismatch:claims:expected=['low_fat']:actual=['low_fat', 'organic']`

**exact errors:**
- `mismatch:category_path:expected='Dairy > Flavored Milk':actual='Beverage > Dairy Milk'`
- `mismatch:product_identity:expected='Vanilla Milk':actual='Milk'`
- `mismatch:canonical_path:expected='Dairy > Flavored Milk > Vanilla Milk':actual='Beverage > Dairy Milk > Milk'`
- `mismatch:canonical_label:expected='Vanilla Milk (1 Percent, Low Fat)':actual='Milk (Vanilla, Low Fat, Organic)'`
- `mismatch:variant:expected=['1_percent']:actual=[]`
- `mismatch:flavor:expected=[]:actual=['vanilla']`
- `mismatch:claims:expected=['low_fat']:actual=['low_fat', 'organic']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Dairy > Flavored Milk > Vanilla Milk', 'Retail Taxonomy > Dairy > Flavored Milk > Vanilla Milk > @variant > 1_percent', 'Retail Taxonomy > Dairy > Flavored Milk > Vanilla Milk > @claims > low_fat']:actual=['Retail Taxonomy > Beverage > Dairy Milk > Milk', 'Retail Taxonomy > Beverage > Dairy Milk > Milk > @flavor > vanilla', 'Retail Taxonomy > Beverage > Dairy Milk > Milk > @claims > low_fat', 'Retail Taxonomy > Beverage > Dairy Milk > Milk > @claims > organic']`

---

## banana_milk
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Dairy > Flavored Milk"` | `"Beverage > Plant Milk"` |
| `product_identity` * | `"Banana Milk"` | `"Plant Milk"` |
| `canonical_path` * | `"Dairy > Flavored Milk > Banana Milk"` | `"Beverage > Plant Milk > Plant Milk"` |
| `variant` * | `[]` | `["banana"]` |
| `flavor` * | `[]` | `["chocolate"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["organic"]` |
| `canonical_label` * | `"Banana Milk"` | `"Plant Milk (Banana, Chocolate, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Dairy > Flavored Milk > Banana Milk"]` | `["Retail Taxonomy > Beverage > Plant Milk > Plant Milk", "Retail Taxonomy > Beverage > Plant Milk > Plant Milk > @variant > banana", "Retail Taxonomy > Beverage > Plant Milk > Plant Milk > @flavor > chocolate", "Retail Taxonomy > Beverage > Plant Milk > Plant Milk > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Dairy > Flavored Milk':actual='Beverage > Plant Milk'`
- `core_mismatch:product_identity:expected='Banana Milk':actual='Plant Milk'`
- `core_mismatch:canonical_path:expected='Dairy > Flavored Milk > Banana Milk':actual='Beverage > Plant Milk > Plant Milk'`
- `core_mismatch:variant:expected=[]:actual=['banana']`
- `core_mismatch:flavor:expected=[]:actual=['chocolate']`
- `core_mismatch:claims:expected=[]:actual=['organic']`

**exact errors:**
- `mismatch:category_path:expected='Dairy > Flavored Milk':actual='Beverage > Plant Milk'`
- `mismatch:product_identity:expected='Banana Milk':actual='Plant Milk'`
- `mismatch:canonical_path:expected='Dairy > Flavored Milk > Banana Milk':actual='Beverage > Plant Milk > Plant Milk'`
- `mismatch:canonical_label:expected='Banana Milk':actual='Plant Milk (Banana, Chocolate, Organic)'`
- `mismatch:variant:expected=[]:actual=['banana']`
- `mismatch:flavor:expected=[]:actual=['chocolate']`
- `mismatch:claims:expected=[]:actual=['organic']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Dairy > Flavored Milk > Banana Milk']:actual=['Retail Taxonomy > Beverage > Plant Milk > Plant Milk', 'Retail Taxonomy > Beverage > Plant Milk > Plant Milk > @variant > banana', 'Retail Taxonomy > Beverage > Plant Milk > Plant Milk > @flavor > chocolate', 'Retail Taxonomy > Beverage > Plant Milk > Plant Milk > @claims > organic']`

---

## cookies_and_cream_chocolate_milk
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Dairy > Flavored Milk"` | `"Dairy > Flavored Milk"` |
| `product_identity` | `"Chocolate Milk"` | `"Chocolate Milk"` |
| `canonical_path` | `"Dairy > Flavored Milk > Chocolate Milk"` | `"Dairy > Flavored Milk > Chocolate Milk"` |
| `variant` * | `[]` | `["cookies_and_cream"]` |
| `flavor` * | `["cookies_and_cream"]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Chocolate Milk (Cookies And Cream)"` | `"Chocolate Milk (Cookies And Cream)"` |
| `tree_paths` * | `["Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk", "Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk > @flavor > cookies_and_cream"]` | `["Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk", "Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk > @variant > cookies_and_cream"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['cookies_and_cream']`
- `core_mismatch:flavor:expected=['cookies_and_cream']:actual=[]`

**exact errors:**
- `mismatch:variant:expected=[]:actual=['cookies_and_cream']`
- `mismatch:flavor:expected=['cookies_and_cream']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk', 'Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk > @flavor > cookies_and_cream']:actual=['Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk', 'Retail Taxonomy > Dairy > Flavored Milk > Chocolate Milk > @variant > cookies_and_cream']`

---

## vanilla_oat_milk
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Beverage > Plant Milk"` | `"Beverage > Plant Milk"` |
| `product_identity` | `"Oat Milk"` | `"Oat Milk"` |
| `canonical_path` | `"Beverage > Plant Milk > Oat Milk"` | `"Beverage > Plant Milk > Oat Milk"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["vanilla"]` | `["vanilla"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["dairy_free", "plant_based"]` | `[]` |
| `canonical_label` * | `"Oat Milk (Vanilla, Dairy Free, Plant Based)"` | `"Oat Milk (Vanilla)"` |
| `tree_paths` * | `["Retail Taxonomy > Beverage > Plant Milk > Oat Milk", "Retail Taxonomy > Beverage > Plant Milk > Oat Milk > @flavor > vanilla", "Retail Taxonomy > Beverage > Plant Milk > Oat Milk > @claims > dairy_free", "Retail Taxonomy > Beverage > Plant Milk > Oat Milk > @claims > plant_based"]` | `["Retail Taxonomy > Beverage > Plant Milk > Oat Milk", "Retail Taxonomy > Beverage > Plant Milk > Oat Milk > @flavor > vanilla"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:claims:expected=['dairy_free', 'plant_based']:actual=[]`

**exact errors:**
- `mismatch:canonical_label:expected='Oat Milk (Vanilla, Dairy Free, Plant Based)':actual='Oat Milk (Vanilla)'`
- `mismatch:claims:expected=['dairy_free', 'plant_based']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Beverage > Plant Milk > Oat Milk', 'Retail Taxonomy > Beverage > Plant Milk > Oat Milk > @flavor > vanilla', 'Retail Taxonomy > Beverage > Plant Milk > Oat Milk > @claims > dairy_free', 'Retail Taxonomy > Beverage > Plant Milk > Oat Milk > @claims > plant_based']:actual=['Retail Taxonomy > Beverage > Plant Milk > Oat Milk', 'Retail Taxonomy > Beverage > Plant Milk > Oat Milk > @flavor > vanilla']`

---

## frozen_broccoli_florets_plain
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Frozen > Vegetables"` | `"Produce > Vegetables"` |
| `product_identity` | `"Broccoli"` | `"Broccoli"` |
| `canonical_path` * | `"Frozen > Vegetables > Broccoli"` | `"Produce > Vegetables > Broccoli"` |
| `variant` * | `[]` | `["florets"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `["florets"]` | `["florets"]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Broccoli (Florets, Frozen)"` | `"Broccoli (Florets, Florets, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Vegetables > Broccoli", "Retail Taxonomy > Frozen > Vegetables > Broccoli > @form_texture_cut > florets", "Retail Taxonomy > Frozen > Vegetables > Broccoli > @processing_storage > frozen"]` | `["Retail Taxonomy > Produce > Vegetables > Broccoli", "Retail Taxonomy > Produce > Vegetables > Broccoli > @variant > florets", "Retail Taxonomy > Produce > Vegetables > Broccoli > @form_texture_cut > florets", "Retail Taxonomy > Produce > Vegetables > Broccoli > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Frozen > Vegetables':actual='Produce > Vegetables'`
- `core_mismatch:canonical_path:expected='Frozen > Vegetables > Broccoli':actual='Produce > Vegetables > Broccoli'`
- `core_mismatch:variant:expected=[]:actual=['florets']`

**exact errors:**
- `mismatch:category_path:expected='Frozen > Vegetables':actual='Produce > Vegetables'`
- `mismatch:canonical_path:expected='Frozen > Vegetables > Broccoli':actual='Produce > Vegetables > Broccoli'`
- `mismatch:canonical_label:expected='Broccoli (Florets, Frozen)':actual='Broccoli (Florets, Florets, Frozen)'`
- `mismatch:variant:expected=[]:actual=['florets']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Vegetables > Broccoli', 'Retail Taxonomy > Frozen > Vegetables > Broccoli > @form_texture_cut > florets', 'Retail Taxonomy > Frozen > Vegetables > Broccoli > @processing_storage > frozen']:actual=['Retail Taxonomy > Produce > Vegetables > Broccoli', 'Retail Taxonomy > Produce > Vegetables > Broccoli > @variant > florets', 'Retail Taxonomy > Produce > Vegetables > Broccoli > @form_texture_cut > florets', 'Retail Taxonomy > Produce > Vegetables > Broccoli > @processing_storage > frozen']`

---

## fresh_broccoli_crowns
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Produce > Vegetables"` | `"Produce > Vegetables"` |
| `product_identity` | `"Broccoli"` | `"Broccoli"` |
| `canonical_path` | `"Produce > Vegetables > Broccoli"` | `"Produce > Vegetables > Broccoli"` |
| `variant` * | `[]` | `["crowns"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `["crowns"]` | `["fresh"]` |
| `processing_storage` * | `[]` | `["fresh"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Broccoli (Crowns)"` | `"Broccoli (Crowns, Fresh, Fresh)"` |
| `tree_paths` * | `["Retail Taxonomy > Produce > Vegetables > Broccoli", "Retail Taxonomy > Produce > Vegetables > Broccoli > @form_texture_cut > crowns"]` | `["Retail Taxonomy > Produce > Vegetables > Broccoli", "Retail Taxonomy > Produce > Vegetables > Broccoli > @variant > crowns", "Retail Taxonomy > Produce > Vegetables > Broccoli > @form_texture_cut > fresh", "Retail Taxonomy > Produce > Vegetables > Broccoli > @processing_storage > fresh"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['crowns']`
- `core_mismatch:form_texture_cut:expected=['crowns']:actual=['fresh']`
- `core_mismatch:processing_storage:expected=[]:actual=['fresh']`

**exact errors:**
- `mismatch:canonical_label:expected='Broccoli (Crowns)':actual='Broccoli (Crowns, Fresh, Fresh)'`
- `mismatch:variant:expected=[]:actual=['crowns']`
- `mismatch:form_texture_cut:expected=['crowns']:actual=['fresh']`
- `mismatch:processing_storage:expected=[]:actual=['fresh']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Produce > Vegetables > Broccoli', 'Retail Taxonomy > Produce > Vegetables > Broccoli > @form_texture_cut > crowns']:actual=['Retail Taxonomy > Produce > Vegetables > Broccoli', 'Retail Taxonomy > Produce > Vegetables > Broccoli > @variant > crowns', 'Retail Taxonomy > Produce > Vegetables > Broccoli > @form_texture_cut > fresh', 'Retail Taxonomy > Produce > Vegetables > Broccoli > @processing_storage > fresh']`

---

## canned_green_beans_plain
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Canned Vegetables"` | `"Pantry > Canned Vegetables"` |
| `product_identity` | `"Green Beans"` | `"Green Beans"` |
| `canonical_path` | `"Pantry > Canned Vegetables > Green Beans"` | `"Pantry > Canned Vegetables > Green Beans"` |
| `variant` * | `[]` | `["cut"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `["cut"]` | `["cut"]` |
| `processing_storage` | `["canned"]` | `["canned"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Green Beans (Cut, Canned)"` | `"Green Beans (Cut, Cut, Canned)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Canned Vegetables > Green Beans", "Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @form_texture_cut > cut", "Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @processing_storage > canned"]` | `["Retail Taxonomy > Pantry > Canned Vegetables > Green Beans", "Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @variant > cut", "Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @form_texture_cut > cut", "Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @processing_storage > canned"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['cut']`

**exact errors:**
- `mismatch:canonical_label:expected='Green Beans (Cut, Canned)':actual='Green Beans (Cut, Cut, Canned)'`
- `mismatch:variant:expected=[]:actual=['cut']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Canned Vegetables > Green Beans', 'Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @form_texture_cut > cut', 'Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @processing_storage > canned']:actual=['Retail Taxonomy > Pantry > Canned Vegetables > Green Beans', 'Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @variant > cut', 'Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @form_texture_cut > cut', 'Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @processing_storage > canned']`

---

## seasoned_green_beans_canned
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Canned Vegetables"` | `"Pantry > Canned Vegetables"` |
| `product_identity` | `"Green Beans"` | `"Green Beans"` |
| `canonical_path` | `"Pantry > Canned Vegetables > Green Beans"` | `"Pantry > Canned Vegetables > Green Beans"` |
| `variant` * | `["seasoned"]` | `["with_bacon"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["cut"]` |
| `processing_storage` * | `["canned"]` | `["canned", "seasoned"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Green Beans (Seasoned, Canned)"` | `"Green Beans (With Bacon, Cut, Canned, Seasoned)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Canned Vegetables > Green Beans", "Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @variant > seasoned", "Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @processing_storage > canned", "Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @components > bacon"]` | `["Retail Taxonomy > Pantry > Canned Vegetables > Green Beans", "Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @variant > with_bacon", "Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @form_texture_cut > cut", "Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @processing_storage > canned", "Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @processing_storage > seasoned"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Bacon", "processing_storage": [], "role": "ingredient", "variant": []}]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['seasoned']:actual=['with_bacon']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['cut']`
- `core_mismatch:processing_storage:expected=['canned']:actual=['canned', 'seasoned']`
- `core_mismatch:component_identities:expected=['bacon']:actual=[]`

**exact errors:**
- `mismatch:canonical_label:expected='Green Beans (Seasoned, Canned)':actual='Green Beans (With Bacon, Cut, Canned, Seasoned)'`
- `mismatch:variant:expected=['seasoned']:actual=['with_bacon']`
- `mismatch:form_texture_cut:expected=[]:actual=['cut']`
- `mismatch:processing_storage:expected=['canned']:actual=['canned', 'seasoned']`
- `mismatch:components:expected=[{'identity': 'Bacon', 'role': 'ingredient', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Canned Vegetables > Green Beans', 'Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @variant > seasoned', 'Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @processing_storage > canned', 'Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @components > bacon']:actual=['Retail Taxonomy > Pantry > Canned Vegetables > Green Beans', 'Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @variant > with_bacon', 'Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @form_texture_cut > cut', 'Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @processing_storage > canned', 'Retail Taxonomy > Pantry > Canned Vegetables > Green Beans > @processing_storage > seasoned']`

---

## italian_style_frozen_veggies
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Vegetables"` | `"Frozen > Vegetables"` |
| `product_identity` | `"Vegetable Blend"` | `"Vegetable Blend"` |
| `canonical_path` | `"Frozen > Vegetables > Vegetable Blend"` | `"Frozen > Vegetables > Vegetable Blend"` |
| `variant` | `["italian_style"]` | `["italian_style"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Vegetable Blend (Italian Style, Frozen)"` | `"Vegetable Blend (Italian Style, Frozen)"` |
| `tree_paths` | `["Retail Taxonomy > Frozen > Vegetables > Vegetable Blend", "Retail Taxonomy > Frozen > Vegetables > Vegetable Blend > @variant > italian_style", "Retail Taxonomy > Frozen > Vegetables > Vegetable Blend > @processing_storage > frozen"]` | `["Retail Taxonomy > Frozen > Vegetables > Vegetable Blend", "Retail Taxonomy > Frozen > Vegetables > Vegetable Blend > @variant > italian_style", "Retail Taxonomy > Frozen > Vegetables > Vegetable Blend > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

---

## steamfresh_broccoli_cheese_sauce
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"composite_dish"` | `"single"` |
| `category_path` | `"Frozen > Prepared Vegetables"` | `"Frozen > Prepared Vegetables"` |
| `product_identity` | `"Broccoli with Cheese Sauce"` | `"Broccoli with Cheese Sauce"` |
| `canonical_path` | `"Frozen > Prepared Vegetables > Broccoli with Cheese Sauce"` | `"Frozen > Prepared Vegetables > Broccoli with Cheese Sauce"` |
| `variant` | `[]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Broccoli with Cheese Sauce (Frozen)"` | `"Broccoli with Cheese Sauce (Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Prepared Vegetables > Broccoli with Cheese Sauce", "Retail Taxonomy > Frozen > Prepared Vegetables > Broccoli with Cheese Sauce > @processing_storage > frozen", "Retail Taxonomy > Frozen > Prepared Vegetables > Broccoli with Cheese Sauce > @components > broccoli", "Retail Taxonomy > Frozen > Prepared Vegetables > Broccoli with Cheese Sauce > @components > cheese_sauce"]` | `["Retail Taxonomy > Frozen > Prepared Vegetables > Broccoli with Cheese Sauce", "Retail Taxonomy > Frozen > Prepared Vegetables > Broccoli with Cheese Sauce > @processing_storage > frozen"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Broccoli", "processing_storage": [], "role": "ingredient", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Cheese Sauce", "processing_storage": [], "role": "sauce", "variant": []}]` | `[]` |

**core errors:**
- `core_mismatch:retail_type:expected='composite_dish':actual='single'`
- `core_mismatch:component_identities:expected=['broccoli', 'cheese_sauce']:actual=[]`

**exact errors:**
- `mismatch:retail_type:expected='composite_dish':actual='single'`
- `mismatch:components:expected=[{'identity': 'Broccoli', 'role': 'ingredient', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Cheese Sauce', 'role': 'sauce', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Prepared Vegetables > Broccoli with Cheese Sauce', 'Retail Taxonomy > Frozen > Prepared Vegetables > Broccoli with Cheese Sauce > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Prepared Vegetables > Broccoli with Cheese Sauce > @components > broccoli', 'Retail Taxonomy > Frozen > Prepared Vegetables > Broccoli with Cheese Sauce > @components > cheese_sauce']:actual=['Retail Taxonomy > Frozen > Prepared Vegetables > Broccoli with Cheese Sauce', 'Retail Taxonomy > Frozen > Prepared Vegetables > Broccoli with Cheese Sauce > @processing_storage > frozen']`

---

## canned_diced_tomatoes_italian_seasoning
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Canned Vegetables"` | `"Pantry > Canned Vegetables"` |
| `product_identity` | `"Tomatoes"` | `"Tomatoes"` |
| `canonical_path` | `"Pantry > Canned Vegetables > Tomatoes"` | `"Pantry > Canned Vegetables > Tomatoes"` |
| `variant` | `[]` | `[]` |
| `flavor` * | `["italian_seasoning"]` | `["italian_herbs"]` |
| `form_texture_cut` | `["diced"]` | `["diced"]` |
| `processing_storage` | `["canned"]` | `["canned"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Tomatoes (Italian Seasoning, Diced, Canned)"` | `"Tomatoes (Italian Herbs, Diced, Canned)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes", "Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @flavor > italian_seasoning", "Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @form_texture_cut > diced", "Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @processing_storage > canned"]` | `["Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes", "Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @flavor > italian_herbs", "Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @form_texture_cut > diced", "Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @processing_storage > canned"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:flavor:expected=['italian_seasoning']:actual=['italian_herbs']`

**exact errors:**
- `mismatch:canonical_label:expected='Tomatoes (Italian Seasoning, Diced, Canned)':actual='Tomatoes (Italian Herbs, Diced, Canned)'`
- `mismatch:flavor:expected=['italian_seasoning']:actual=['italian_herbs']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes', 'Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @flavor > italian_seasoning', 'Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @form_texture_cut > diced', 'Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @processing_storage > canned']:actual=['Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes', 'Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @flavor > italian_herbs', 'Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @form_texture_cut > diced', 'Retail Taxonomy > Pantry > Canned Vegetables > Tomatoes > @processing_storage > canned']`

---

## frozen_peas_plain
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Vegetables"` | `"Frozen > Vegetables"` |
| `product_identity` | `"Peas"` | `"Peas"` |
| `canonical_path` | `"Frozen > Vegetables > Peas"` | `"Frozen > Vegetables > Peas"` |
| `variant` * | `[]` | `["green"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Peas (Frozen)"` | `"Peas (Green, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Vegetables > Peas", "Retail Taxonomy > Frozen > Vegetables > Peas > @processing_storage > frozen"]` | `["Retail Taxonomy > Frozen > Vegetables > Peas", "Retail Taxonomy > Frozen > Vegetables > Peas > @variant > green", "Retail Taxonomy > Frozen > Vegetables > Peas > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['green']`

**exact errors:**
- `mismatch:canonical_label:expected='Peas (Frozen)':actual='Peas (Green, Frozen)'`
- `mismatch:variant:expected=[]:actual=['green']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Vegetables > Peas', 'Retail Taxonomy > Frozen > Vegetables > Peas > @processing_storage > frozen']:actual=['Retail Taxonomy > Frozen > Vegetables > Peas', 'Retail Taxonomy > Frozen > Vegetables > Peas > @variant > green', 'Retail Taxonomy > Frozen > Vegetables > Peas > @processing_storage > frozen']`

---

## fresh_baby_carrots
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Produce > Vegetables"` | `"Produce > Vegetables"` |
| `product_identity` | `"Baby Carrots"` | `"Baby Carrots"` |
| `canonical_path` | `"Produce > Vegetables > Baby Carrots"` | `"Produce > Vegetables > Baby Carrots"` |
| `variant` * | `[]` | `["peeled"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `["peeled"]` | `["crinkle_cut"]` |
| `processing_storage` * | `[]` | `["fresh"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Baby Carrots (Peeled)"` | `"Baby Carrots (Peeled, Crinkle Cut, Fresh)"` |
| `tree_paths` * | `["Retail Taxonomy > Produce > Vegetables > Baby Carrots", "Retail Taxonomy > Produce > Vegetables > Baby Carrots > @form_texture_cut > peeled"]` | `["Retail Taxonomy > Produce > Vegetables > Baby Carrots", "Retail Taxonomy > Produce > Vegetables > Baby Carrots > @variant > peeled", "Retail Taxonomy > Produce > Vegetables > Baby Carrots > @form_texture_cut > crinkle_cut", "Retail Taxonomy > Produce > Vegetables > Baby Carrots > @processing_storage > fresh"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['peeled']`
- `core_mismatch:form_texture_cut:expected=['peeled']:actual=['crinkle_cut']`
- `core_mismatch:processing_storage:expected=[]:actual=['fresh']`

**exact errors:**
- `mismatch:canonical_label:expected='Baby Carrots (Peeled)':actual='Baby Carrots (Peeled, Crinkle Cut, Fresh)'`
- `mismatch:variant:expected=[]:actual=['peeled']`
- `mismatch:form_texture_cut:expected=['peeled']:actual=['crinkle_cut']`
- `mismatch:processing_storage:expected=[]:actual=['fresh']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Produce > Vegetables > Baby Carrots', 'Retail Taxonomy > Produce > Vegetables > Baby Carrots > @form_texture_cut > peeled']:actual=['Retail Taxonomy > Produce > Vegetables > Baby Carrots', 'Retail Taxonomy > Produce > Vegetables > Baby Carrots > @variant > peeled', 'Retail Taxonomy > Produce > Vegetables > Baby Carrots > @form_texture_cut > crinkle_cut', 'Retail Taxonomy > Produce > Vegetables > Baby Carrots > @processing_storage > fresh']`

---

## frozen_seasoned_potatoes
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Vegetables"` | `"Frozen > Vegetables"` |
| `product_identity` * | `"Potatoes"` | `"Vegetable Blend"` |
| `canonical_path` * | `"Frozen > Vegetables > Potatoes"` | `"Frozen > Vegetables > Vegetable Blend"` |
| `variant` * | `["seasoned"]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `["diced"]` | `["diced"]` |
| `processing_storage` * | `["frozen"]` | `["frozen", "seasoned"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Potatoes (Seasoned, Diced, Frozen)"` | `"Vegetable Blend (Diced, Frozen, Seasoned)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Vegetables > Potatoes", "Retail Taxonomy > Frozen > Vegetables > Potatoes > @variant > seasoned", "Retail Taxonomy > Frozen > Vegetables > Potatoes > @form_texture_cut > diced", "Retail Taxonomy > Frozen > Vegetables > Potatoes > @processing_storage > frozen"]` | `["Retail Taxonomy > Frozen > Vegetables > Vegetable Blend", "Retail Taxonomy > Frozen > Vegetables > Vegetable Blend > @form_texture_cut > diced", "Retail Taxonomy > Frozen > Vegetables > Vegetable Blend > @processing_storage > frozen", "Retail Taxonomy > Frozen > Vegetables > Vegetable Blend > @processing_storage > seasoned"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Potatoes':actual='Vegetable Blend'`
- `core_mismatch:canonical_path:expected='Frozen > Vegetables > Potatoes':actual='Frozen > Vegetables > Vegetable Blend'`
- `core_mismatch:variant:expected=['seasoned']:actual=[]`
- `core_mismatch:processing_storage:expected=['frozen']:actual=['frozen', 'seasoned']`

**exact errors:**
- `mismatch:product_identity:expected='Potatoes':actual='Vegetable Blend'`
- `mismatch:canonical_path:expected='Frozen > Vegetables > Potatoes':actual='Frozen > Vegetables > Vegetable Blend'`
- `mismatch:canonical_label:expected='Potatoes (Seasoned, Diced, Frozen)':actual='Vegetable Blend (Diced, Frozen, Seasoned)'`
- `mismatch:variant:expected=['seasoned']:actual=[]`
- `mismatch:processing_storage:expected=['frozen']:actual=['frozen', 'seasoned']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Vegetables > Potatoes', 'Retail Taxonomy > Frozen > Vegetables > Potatoes > @variant > seasoned', 'Retail Taxonomy > Frozen > Vegetables > Potatoes > @form_texture_cut > diced', 'Retail Taxonomy > Frozen > Vegetables > Potatoes > @processing_storage > frozen']:actual=['Retail Taxonomy > Frozen > Vegetables > Vegetable Blend', 'Retail Taxonomy > Frozen > Vegetables > Vegetable Blend > @form_texture_cut > diced', 'Retail Taxonomy > Frozen > Vegetables > Vegetable Blend > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Vegetables > Vegetable Blend > @processing_storage > seasoned']`

---

## skittles_original_assorted
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Candy"` | `"Snack > Candy"` |
| `product_identity` | `"Fruit Candy"` | `"Fruit Candy"` |
| `canonical_path` | `"Snack > Candy > Fruit Candy"` | `"Snack > Candy > Fruit Candy"` |
| `variant` * | `["assorted_fruit"]` | `["assorted"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Fruit Candy (Assorted Fruit)"` | `"Fruit Candy (Assorted)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Candy > Fruit Candy", "Retail Taxonomy > Snack > Candy > Fruit Candy > @variant > assorted_fruit"]` | `["Retail Taxonomy > Snack > Candy > Fruit Candy", "Retail Taxonomy > Snack > Candy > Fruit Candy > @variant > assorted"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['assorted_fruit']:actual=['assorted']`

**exact errors:**
- `mismatch:canonical_label:expected='Fruit Candy (Assorted Fruit)':actual='Fruit Candy (Assorted)'`
- `mismatch:variant:expected=['assorted_fruit']:actual=['assorted']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Candy > Fruit Candy', 'Retail Taxonomy > Snack > Candy > Fruit Candy > @variant > assorted_fruit']:actual=['Retail Taxonomy > Snack > Candy > Fruit Candy', 'Retail Taxonomy > Snack > Candy > Fruit Candy > @variant > assorted']`

---

## starburst_original_4flavor
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Candy"` | `"Snack > Candy"` |
| `product_identity` * | `"Fruit Chews"` | `"Fruit Candy"` |
| `canonical_path` * | `"Snack > Candy > Fruit Chews"` | `"Snack > Candy > Fruit Candy"` |
| `variant` * | `["assorted_fruit"]` | `[]` |
| `flavor` * | `[]` | `["strawberry", "orange", "lemon", "cherry"]` |
| `form_texture_cut` * | `[]` | `["chews"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Fruit Chews (Assorted Fruit)"` | `"Fruit Candy (Strawberry, Orange, Lemon, Cherry, Chews)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Candy > Fruit Chews", "Retail Taxonomy > Snack > Candy > Fruit Chews > @variant > assorted_fruit"]` | `["Retail Taxonomy > Snack > Candy > Fruit Candy", "Retail Taxonomy > Snack > Candy > Fruit Candy > @flavor > strawberry", "Retail Taxonomy > Snack > Candy > Fruit Candy > @flavor > orange", "Retail Taxonomy > Snack > Candy > Fruit Candy > @flavor > lemon", "Retail Taxonomy > Snack > Candy > Fruit Candy > @flavor > cherry", "Retail Taxonomy > Snack > Candy > Fruit Candy > @form_texture_cut > chews"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Fruit Chews':actual='Fruit Candy'`
- `core_mismatch:canonical_path:expected='Snack > Candy > Fruit Chews':actual='Snack > Candy > Fruit Candy'`
- `core_mismatch:variant:expected=['assorted_fruit']:actual=[]`
- `core_mismatch:flavor:expected=[]:actual=['strawberry', 'orange', 'lemon', 'cherry']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['chews']`

**exact errors:**
- `mismatch:product_identity:expected='Fruit Chews':actual='Fruit Candy'`
- `mismatch:canonical_path:expected='Snack > Candy > Fruit Chews':actual='Snack > Candy > Fruit Candy'`
- `mismatch:canonical_label:expected='Fruit Chews (Assorted Fruit)':actual='Fruit Candy (Strawberry, Orange, Lemon, Cherry, Chews)'`
- `mismatch:variant:expected=['assorted_fruit']:actual=[]`
- `mismatch:flavor:expected=[]:actual=['strawberry', 'orange', 'lemon', 'cherry']`
- `mismatch:form_texture_cut:expected=[]:actual=['chews']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Candy > Fruit Chews', 'Retail Taxonomy > Snack > Candy > Fruit Chews > @variant > assorted_fruit']:actual=['Retail Taxonomy > Snack > Candy > Fruit Candy', 'Retail Taxonomy > Snack > Candy > Fruit Candy > @flavor > strawberry', 'Retail Taxonomy > Snack > Candy > Fruit Candy > @flavor > orange', 'Retail Taxonomy > Snack > Candy > Fruit Candy > @flavor > lemon', 'Retail Taxonomy > Snack > Candy > Fruit Candy > @flavor > cherry', 'Retail Taxonomy > Snack > Candy > Fruit Candy > @form_texture_cut > chews']`

---

## sour_patch_kids_assorted
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Candy"` | `"Snack > Candy"` |
| `product_identity` | `"Sour Candy"` | `"Sour Candy"` |
| `canonical_path` | `"Snack > Candy > Sour Candy"` | `"Snack > Candy > Sour Candy"` |
| `variant` * | `["assorted"]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["assorted"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["sugar_free"]` |
| `canonical_label` * | `"Sour Candy (Assorted)"` | `"Sour Candy (Assorted, Sugar Free)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Candy > Sour Candy", "Retail Taxonomy > Snack > Candy > Sour Candy > @variant > assorted"]` | `["Retail Taxonomy > Snack > Candy > Sour Candy", "Retail Taxonomy > Snack > Candy > Sour Candy > @form_texture_cut > assorted", "Retail Taxonomy > Snack > Candy > Sour Candy > @claims > sugar_free"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['assorted']:actual=[]`
- `core_mismatch:form_texture_cut:expected=[]:actual=['assorted']`
- `core_mismatch:claims:expected=[]:actual=['sugar_free']`

**exact errors:**
- `mismatch:canonical_label:expected='Sour Candy (Assorted)':actual='Sour Candy (Assorted, Sugar Free)'`
- `mismatch:variant:expected=['assorted']:actual=[]`
- `mismatch:form_texture_cut:expected=[]:actual=['assorted']`
- `mismatch:claims:expected=[]:actual=['sugar_free']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Candy > Sour Candy', 'Retail Taxonomy > Snack > Candy > Sour Candy > @variant > assorted']:actual=['Retail Taxonomy > Snack > Candy > Sour Candy', 'Retail Taxonomy > Snack > Candy > Sour Candy > @form_texture_cut > assorted', 'Retail Taxonomy > Snack > Candy > Sour Candy > @claims > sugar_free']`

---

## lifesavers_5flavor
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Candy"` | `"Snack > Candy"` |
| `product_identity` | `"Hard Candy"` | `"Hard Candy"` |
| `canonical_path` | `"Snack > Candy > Hard Candy"` | `"Snack > Candy > Hard Candy"` |
| `variant` * | `["assorted"]` | `["5_flavor"]` |
| `flavor` * | `[]` | `["assorted_fruit"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Hard Candy (Assorted)"` | `"Hard Candy (5 Flavor, Assorted Fruit)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Candy > Hard Candy", "Retail Taxonomy > Snack > Candy > Hard Candy > @variant > assorted"]` | `["Retail Taxonomy > Snack > Candy > Hard Candy", "Retail Taxonomy > Snack > Candy > Hard Candy > @variant > 5_flavor", "Retail Taxonomy > Snack > Candy > Hard Candy > @flavor > assorted_fruit"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['assorted']:actual=['5_flavor']`
- `core_mismatch:flavor:expected=[]:actual=['assorted_fruit']`

**exact errors:**
- `mismatch:canonical_label:expected='Hard Candy (Assorted)':actual='Hard Candy (5 Flavor, Assorted Fruit)'`
- `mismatch:variant:expected=['assorted']:actual=['5_flavor']`
- `mismatch:flavor:expected=[]:actual=['assorted_fruit']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Candy > Hard Candy', 'Retail Taxonomy > Snack > Candy > Hard Candy > @variant > assorted']:actual=['Retail Taxonomy > Snack > Candy > Hard Candy', 'Retail Taxonomy > Snack > Candy > Hard Candy > @variant > 5_flavor', 'Retail Taxonomy > Snack > Candy > Hard Candy > @flavor > assorted_fruit']`

---

## jelly_belly_50_flavors
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Candy"` | `"Snack > Candy"` |
| `product_identity` | `"Jelly Beans"` | `"Jelly Beans"` |
| `canonical_path` | `"Snack > Candy > Jelly Beans"` | `"Snack > Candy > Jelly Beans"` |
| `variant` * | `["assorted"]` | `["assorted_flavors"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["jelly_bean"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Jelly Beans (Assorted)"` | `"Jelly Beans (Assorted Flavors, Jelly Bean)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Candy > Jelly Beans", "Retail Taxonomy > Snack > Candy > Jelly Beans > @variant > assorted"]` | `["Retail Taxonomy > Snack > Candy > Jelly Beans", "Retail Taxonomy > Snack > Candy > Jelly Beans > @variant > assorted_flavors", "Retail Taxonomy > Snack > Candy > Jelly Beans > @form_texture_cut > jelly_bean"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['assorted']:actual=['assorted_flavors']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['jelly_bean']`

**exact errors:**
- `mismatch:canonical_label:expected='Jelly Beans (Assorted)':actual='Jelly Beans (Assorted Flavors, Jelly Bean)'`
- `mismatch:variant:expected=['assorted']:actual=['assorted_flavors']`
- `mismatch:form_texture_cut:expected=[]:actual=['jelly_bean']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Candy > Jelly Beans', 'Retail Taxonomy > Snack > Candy > Jelly Beans > @variant > assorted']:actual=['Retail Taxonomy > Snack > Candy > Jelly Beans', 'Retail Taxonomy > Snack > Candy > Jelly Beans > @variant > assorted_flavors', 'Retail Taxonomy > Snack > Candy > Jelly Beans > @form_texture_cut > jelly_bean']`

---

## mm_peanut_chocolate
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Snack > Chocolate Candy"` | `"Pantry > Candy"` |
| `product_identity` * | `"Chocolate Candy"` | `"Candy"` |
| `canonical_path` * | `"Snack > Chocolate Candy > Chocolate Candy"` | `"Pantry > Candy > Candy"` |
| `variant` * | `["peanut"]` | `["milk_chocolate", "peanut"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Chocolate Candy (Peanut)"` | `"Candy (Milk Chocolate, Peanut)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Chocolate Candy > Chocolate Candy", "Retail Taxonomy > Snack > Chocolate Candy > Chocolate Candy > @variant > peanut"]` | `["Retail Taxonomy > Pantry > Candy > Candy", "Retail Taxonomy > Pantry > Candy > Candy > @variant > milk_chocolate", "Retail Taxonomy > Pantry > Candy > Candy > @variant > peanut"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Snack > Chocolate Candy':actual='Pantry > Candy'`
- `core_mismatch:product_identity:expected='Chocolate Candy':actual='Candy'`
- `core_mismatch:canonical_path:expected='Snack > Chocolate Candy > Chocolate Candy':actual='Pantry > Candy > Candy'`
- `core_mismatch:variant:expected=['peanut']:actual=['milk_chocolate', 'peanut']`

**exact errors:**
- `mismatch:category_path:expected='Snack > Chocolate Candy':actual='Pantry > Candy'`
- `mismatch:product_identity:expected='Chocolate Candy':actual='Candy'`
- `mismatch:canonical_path:expected='Snack > Chocolate Candy > Chocolate Candy':actual='Pantry > Candy > Candy'`
- `mismatch:canonical_label:expected='Chocolate Candy (Peanut)':actual='Candy (Milk Chocolate, Peanut)'`
- `mismatch:variant:expected=['peanut']:actual=['milk_chocolate', 'peanut']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Chocolate Candy > Chocolate Candy', 'Retail Taxonomy > Snack > Chocolate Candy > Chocolate Candy > @variant > peanut']:actual=['Retail Taxonomy > Pantry > Candy > Candy', 'Retail Taxonomy > Pantry > Candy > Candy > @variant > milk_chocolate', 'Retail Taxonomy > Pantry > Candy > Candy > @variant > peanut']`

---

## montreal_steak_seasoning
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Spices & Seasonings"` | `"Pantry > Spices & Seasonings"` |
| `product_identity` | `"Seasoning"` | `"Seasoning"` |
| `canonical_path` | `"Pantry > Spices & Seasonings > Seasoning"` | `"Pantry > Spices & Seasonings > Seasoning"` |
| `variant` | `["montreal_steak"]` | `["montreal_steak"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Seasoning (Montreal Steak)"` | `"Seasoning (Montreal Steak)"` |
| `tree_paths` | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > montreal_steak"]` | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > montreal_steak"]` |
| `components` | `[]` | `[]` |

---

## salt_and_pepper_combo
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"single"` | `"pantry"` |
| `category_path` | `"Pantry > Spices & Seasonings"` | `"Pantry > Spices & Seasonings"` |
| `product_identity` * | `"Salt and Pepper"` | `"Seasoning"` |
| `canonical_path` * | `"Pantry > Spices & Seasonings > Salt and Pepper"` | `"Pantry > Spices & Seasonings > Seasoning"` |
| `variant` * | `[]` | `["garlic_pepper", "chili"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["ground"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["organic"]` |
| `canonical_label` * | `"Salt and Pepper"` | `"Seasoning (Garlic Pepper, Chili, Ground, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Spices & Seasonings > Salt and Pepper"]` | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > garlic_pepper", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > chili", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @form_texture_cut > ground", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `invalid_retail_type:pantry`
- `core_mismatch:retail_type:expected='single':actual='pantry'`
- `core_mismatch:product_identity:expected='Salt and Pepper':actual='Seasoning'`
- `core_mismatch:canonical_path:expected='Pantry > Spices & Seasonings > Salt and Pepper':actual='Pantry > Spices & Seasonings > Seasoning'`
- `core_mismatch:variant:expected=[]:actual=['garlic_pepper', 'chili']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['ground']`
- `core_mismatch:claims:expected=[]:actual=['organic']`

**exact errors:**
- `invalid_retail_type:pantry`
- `mismatch:retail_type:expected='single':actual='pantry'`
- `mismatch:product_identity:expected='Salt and Pepper':actual='Seasoning'`
- `mismatch:canonical_path:expected='Pantry > Spices & Seasonings > Salt and Pepper':actual='Pantry > Spices & Seasonings > Seasoning'`
- `mismatch:canonical_label:expected='Salt and Pepper':actual='Seasoning (Garlic Pepper, Chili, Ground, Organic)'`
- `mismatch:variant:expected=[]:actual=['garlic_pepper', 'chili']`
- `mismatch:form_texture_cut:expected=[]:actual=['ground']`
- `mismatch:claims:expected=[]:actual=['organic']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Spices & Seasonings > Salt and Pepper']:actual=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > garlic_pepper', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > chili', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @form_texture_cut > ground', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @claims > organic']`

---

## taco_seasoning_mix
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Spices & Seasonings"` | `"Pantry > Spices & Seasonings"` |
| `product_identity` | `"Seasoning"` | `"Seasoning"` |
| `canonical_path` | `"Pantry > Spices & Seasonings > Seasoning"` | `"Pantry > Spices & Seasonings > Seasoning"` |
| `variant` | `["taco"]` | `["taco"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["powdered", "dry_mix"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Seasoning (Taco)"` | `"Seasoning (Taco, Powdered, Dry Mix)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > taco"]` | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > taco", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @form_texture_cut > powdered", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @form_texture_cut > dry_mix"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:form_texture_cut:expected=[]:actual=['powdered', 'dry_mix']`

**exact errors:**
- `mismatch:canonical_label:expected='Seasoning (Taco)':actual='Seasoning (Taco, Powdered, Dry Mix)'`
- `mismatch:form_texture_cut:expected=[]:actual=['powdered', 'dry_mix']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > taco']:actual=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > taco', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @form_texture_cut > powdered', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @form_texture_cut > dry_mix']`

---

## italian_herb_blend
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Spices & Seasonings"` | `"Pantry > Spices & Seasonings"` |
| `product_identity` | `"Seasoning"` | `"Seasoning"` |
| `canonical_path` | `"Pantry > Spices & Seasonings > Seasoning"` | `"Pantry > Spices & Seasonings > Seasoning"` |
| `variant` * | `["italian_herb"]` | `["italian_herb_blend"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["ground"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Seasoning (Italian Herb)"` | `"Seasoning (Italian Herb Blend, Ground)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > italian_herb"]` | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > italian_herb_blend", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @form_texture_cut > ground"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['italian_herb']:actual=['italian_herb_blend']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['ground']`

**exact errors:**
- `mismatch:canonical_label:expected='Seasoning (Italian Herb)':actual='Seasoning (Italian Herb Blend, Ground)'`
- `mismatch:variant:expected=['italian_herb']:actual=['italian_herb_blend']`
- `mismatch:form_texture_cut:expected=[]:actual=['ground']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > italian_herb']:actual=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > italian_herb_blend', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @form_texture_cut > ground']`

---

## lemon_pepper_seasoning
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Spices & Seasonings"` | `"Pantry > Spices & Seasonings"` |
| `product_identity` | `"Seasoning"` | `"Seasoning"` |
| `canonical_path` | `"Pantry > Spices & Seasonings > Seasoning"` | `"Pantry > Spices & Seasonings > Seasoning"` |
| `variant` | `["lemon_pepper"]` | `["lemon_pepper"]` |
| `flavor` * | `[]` | `["garlic"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Seasoning (Lemon Pepper)"` | `"Seasoning (Lemon Pepper, Garlic)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > lemon_pepper"]` | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > lemon_pepper", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @flavor > garlic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:flavor:expected=[]:actual=['garlic']`

**exact errors:**
- `mismatch:canonical_label:expected='Seasoning (Lemon Pepper)':actual='Seasoning (Lemon Pepper, Garlic)'`
- `mismatch:flavor:expected=[]:actual=['garlic']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > lemon_pepper']:actual=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > lemon_pepper', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @flavor > garlic']`

---

## memphis_bbq_rub
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Spices & Seasonings"` | `"Pantry > Spices & Seasonings"` |
| `product_identity` * | `"BBQ Rub"` | `"Seasoning"` |
| `canonical_path` * | `"Pantry > Spices & Seasonings > BBQ Rub"` | `"Pantry > Spices & Seasonings > Seasoning"` |
| `variant` * | `["memphis"]` | `["memphis_bbq", "dry_rub"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"BBQ Rub (Memphis)"` | `"Seasoning (Memphis BBQ, Dry Rub)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Spices & Seasonings > BBQ Rub", "Retail Taxonomy > Pantry > Spices & Seasonings > BBQ Rub > @variant > memphis"]` | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > memphis_bbq", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > dry_rub"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='BBQ Rub':actual='Seasoning'`
- `core_mismatch:canonical_path:expected='Pantry > Spices & Seasonings > BBQ Rub':actual='Pantry > Spices & Seasonings > Seasoning'`
- `core_mismatch:variant:expected=['memphis']:actual=['memphis_bbq', 'dry_rub']`

**exact errors:**
- `mismatch:product_identity:expected='BBQ Rub':actual='Seasoning'`
- `mismatch:canonical_path:expected='Pantry > Spices & Seasonings > BBQ Rub':actual='Pantry > Spices & Seasonings > Seasoning'`
- `mismatch:canonical_label:expected='BBQ Rub (Memphis)':actual='Seasoning (Memphis BBQ, Dry Rub)'`
- `mismatch:variant:expected=['memphis']:actual=['memphis_bbq', 'dry_rub']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Spices & Seasonings > BBQ Rub', 'Retail Taxonomy > Pantry > Spices & Seasonings > BBQ Rub > @variant > memphis']:actual=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > memphis_bbq', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > dry_rub']`

---

## cajun_blackening_seasoning
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Spices & Seasonings"` | `"Pantry > Spices & Seasonings"` |
| `product_identity` | `"Seasoning"` | `"Seasoning"` |
| `canonical_path` | `"Pantry > Spices & Seasonings > Seasoning"` | `"Pantry > Spices & Seasonings > Seasoning"` |
| `variant` * | `["cajun_blackening"]` | `["cajun", "blackened"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Seasoning (Cajun Blackening)"` | `"Seasoning (Cajun, Blackened)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > cajun_blackening"]` | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > cajun", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > blackened"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['cajun_blackening']:actual=['cajun', 'blackened']`

**exact errors:**
- `mismatch:canonical_label:expected='Seasoning (Cajun Blackening)':actual='Seasoning (Cajun, Blackened)'`
- `mismatch:variant:expected=['cajun_blackening']:actual=['cajun', 'blackened']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > cajun_blackening']:actual=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > cajun', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > blackened']`

---

## pumpkin_pie_spice
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Spices & Seasonings"` | `"Pantry > Spices & Seasonings"` |
| `product_identity` * | `"Spice Blend"` | `"Seasoning"` |
| `canonical_path` * | `"Pantry > Spices & Seasonings > Spice Blend"` | `"Pantry > Spices & Seasonings > Seasoning"` |
| `variant` * | `["pumpkin_pie"]` | `["pumpkin_pie_spice"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Spice Blend (Pumpkin Pie)"` | `"Seasoning (Pumpkin Pie Spice)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Spices & Seasonings > Spice Blend", "Retail Taxonomy > Pantry > Spices & Seasonings > Spice Blend > @variant > pumpkin_pie"]` | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > pumpkin_pie_spice"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Spice Blend':actual='Seasoning'`
- `core_mismatch:canonical_path:expected='Pantry > Spices & Seasonings > Spice Blend':actual='Pantry > Spices & Seasonings > Seasoning'`
- `core_mismatch:variant:expected=['pumpkin_pie']:actual=['pumpkin_pie_spice']`

**exact errors:**
- `mismatch:product_identity:expected='Spice Blend':actual='Seasoning'`
- `mismatch:canonical_path:expected='Pantry > Spices & Seasonings > Spice Blend':actual='Pantry > Spices & Seasonings > Seasoning'`
- `mismatch:canonical_label:expected='Spice Blend (Pumpkin Pie)':actual='Seasoning (Pumpkin Pie Spice)'`
- `mismatch:variant:expected=['pumpkin_pie']:actual=['pumpkin_pie_spice']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Spices & Seasonings > Spice Blend', 'Retail Taxonomy > Pantry > Spices & Seasonings > Spice Blend > @variant > pumpkin_pie']:actual=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > pumpkin_pie_spice']`

---

## curry_powder
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Spices & Seasonings"` | `"Pantry > Spices & Seasonings"` |
| `product_identity` * | `"Curry Powder"` | `"Seasoning"` |
| `canonical_path` * | `"Pantry > Spices & Seasonings > Curry Powder"` | `"Pantry > Spices & Seasonings > Seasoning"` |
| `variant` * | `["madras"]` | `["madras_curry"]` |
| `flavor` * | `[]` | `["mild"]` |
| `form_texture_cut` * | `[]` | `["powder"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Curry Powder (Madras)"` | `"Seasoning (Madras Curry, Mild, Powder)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Spices & Seasonings > Curry Powder", "Retail Taxonomy > Pantry > Spices & Seasonings > Curry Powder > @variant > madras"]` | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > madras_curry", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @flavor > mild", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @form_texture_cut > powder"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Curry Powder':actual='Seasoning'`
- `core_mismatch:canonical_path:expected='Pantry > Spices & Seasonings > Curry Powder':actual='Pantry > Spices & Seasonings > Seasoning'`
- `core_mismatch:variant:expected=['madras']:actual=['madras_curry']`
- `core_mismatch:flavor:expected=[]:actual=['mild']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['powder']`

**exact errors:**
- `mismatch:product_identity:expected='Curry Powder':actual='Seasoning'`
- `mismatch:canonical_path:expected='Pantry > Spices & Seasonings > Curry Powder':actual='Pantry > Spices & Seasonings > Seasoning'`
- `mismatch:canonical_label:expected='Curry Powder (Madras)':actual='Seasoning (Madras Curry, Mild, Powder)'`
- `mismatch:variant:expected=['madras']:actual=['madras_curry']`
- `mismatch:flavor:expected=[]:actual=['mild']`
- `mismatch:form_texture_cut:expected=[]:actual=['powder']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Spices & Seasonings > Curry Powder', 'Retail Taxonomy > Pantry > Spices & Seasonings > Curry Powder > @variant > madras']:actual=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > madras_curry', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @flavor > mild', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @form_texture_cut > powder']`

---

## chicken_seasoning
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Spices & Seasonings"` | `"Pantry > Spices & Seasonings"` |
| `product_identity` | `"Seasoning"` | `"Seasoning"` |
| `canonical_path` | `"Pantry > Spices & Seasonings > Seasoning"` | `"Pantry > Spices & Seasonings > Seasoning"` |
| `variant` * | `["chicken"]` | `["caribbean_jerk", "chicken"]` |
| `flavor` * | `[]` | `["jerk"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Seasoning (Chicken)"` | `"Seasoning (Caribbean Jerk, Chicken, Jerk)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > chicken"]` | `["Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > caribbean_jerk", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > chicken", "Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @flavor > jerk"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['chicken']:actual=['caribbean_jerk', 'chicken']`
- `core_mismatch:flavor:expected=[]:actual=['jerk']`

**exact errors:**
- `mismatch:canonical_label:expected='Seasoning (Chicken)':actual='Seasoning (Caribbean Jerk, Chicken, Jerk)'`
- `mismatch:variant:expected=['chicken']:actual=['caribbean_jerk', 'chicken']`
- `mismatch:flavor:expected=[]:actual=['jerk']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > chicken']:actual=['Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > caribbean_jerk', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @variant > chicken', 'Retail Taxonomy > Pantry > Spices & Seasonings > Seasoning > @flavor > jerk']`

---

## ben_jerry_chunky_monkey
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Ice Cream"` | `"Frozen > Ice Cream"` |
| `product_identity` | `"Ice Cream"` | `"Ice Cream"` |
| `canonical_path` | `"Frozen > Ice Cream > Ice Cream"` | `"Frozen > Ice Cream > Ice Cream"` |
| `variant` | `["chunky_monkey"]` | `["chunky_monkey"]` |
| `flavor` * | `[]` | `["banana", "chocolate", "walnut"]` |
| `form_texture_cut` * | `[]` | `["chunky"]` |
| `processing_storage` * | `[]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Ice Cream (Chunky Monkey)"` | `"Ice Cream (Chunky Monkey, Banana, Chocolate, Walnut, Chunky, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Ice Cream > Ice Cream", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @variant > chunky_monkey"]` | `["Retail Taxonomy > Frozen > Ice Cream > Ice Cream", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @variant > chunky_monkey", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > banana", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > chocolate", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > walnut", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @form_texture_cut > chunky", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:flavor:expected=[]:actual=['banana', 'chocolate', 'walnut']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['chunky']`
- `core_mismatch:processing_storage:expected=[]:actual=['frozen']`

**exact errors:**
- `mismatch:canonical_label:expected='Ice Cream (Chunky Monkey)':actual='Ice Cream (Chunky Monkey, Banana, Chocolate, Walnut, Chunky, Frozen)'`
- `mismatch:flavor:expected=[]:actual=['banana', 'chocolate', 'walnut']`
- `mismatch:form_texture_cut:expected=[]:actual=['chunky']`
- `mismatch:processing_storage:expected=[]:actual=['frozen']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Ice Cream > Ice Cream', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @variant > chunky_monkey']:actual=['Retail Taxonomy > Frozen > Ice Cream > Ice Cream', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @variant > chunky_monkey', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > banana', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > chocolate', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > walnut', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @form_texture_cut > chunky', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @processing_storage > frozen']`

---

## ben_jerry_cherry_garcia
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Ice Cream"` | `"Frozen > Ice Cream"` |
| `product_identity` | `"Ice Cream"` | `"Ice Cream"` |
| `canonical_path` | `"Frozen > Ice Cream > Ice Cream"` | `"Frozen > Ice Cream > Ice Cream"` |
| `variant` | `["cherry_garcia"]` | `["cherry_garcia"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `[]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Ice Cream (Cherry Garcia)"` | `"Ice Cream (Cherry Garcia, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Ice Cream > Ice Cream", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @variant > cherry_garcia"]` | `["Retail Taxonomy > Frozen > Ice Cream > Ice Cream", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @variant > cherry_garcia", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:processing_storage:expected=[]:actual=['frozen']`

**exact errors:**
- `mismatch:canonical_label:expected='Ice Cream (Cherry Garcia)':actual='Ice Cream (Cherry Garcia, Frozen)'`
- `mismatch:processing_storage:expected=[]:actual=['frozen']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Ice Cream > Ice Cream', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @variant > cherry_garcia']:actual=['Retail Taxonomy > Frozen > Ice Cream > Ice Cream', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @variant > cherry_garcia', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @processing_storage > frozen']`

---

## ben_jerry_half_baked
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Ice Cream"` | `"Frozen > Ice Cream"` |
| `product_identity` | `"Ice Cream"` | `"Ice Cream"` |
| `canonical_path` | `"Frozen > Ice Cream > Ice Cream"` | `"Frozen > Ice Cream > Ice Cream"` |
| `variant` * | `["half_baked"]` | `[]` |
| `flavor` * | `[]` | `["chocolate", "vanilla"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `[]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Ice Cream (Half Baked)"` | `"Ice Cream (Chocolate, Vanilla, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Ice Cream > Ice Cream", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @variant > half_baked"]` | `["Retail Taxonomy > Frozen > Ice Cream > Ice Cream", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > chocolate", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > vanilla", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['half_baked']:actual=[]`
- `core_mismatch:flavor:expected=[]:actual=['chocolate', 'vanilla']`
- `core_mismatch:processing_storage:expected=[]:actual=['frozen']`

**exact errors:**
- `mismatch:canonical_label:expected='Ice Cream (Half Baked)':actual='Ice Cream (Chocolate, Vanilla, Frozen)'`
- `mismatch:variant:expected=['half_baked']:actual=[]`
- `mismatch:flavor:expected=[]:actual=['chocolate', 'vanilla']`
- `mismatch:processing_storage:expected=[]:actual=['frozen']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Ice Cream > Ice Cream', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @variant > half_baked']:actual=['Retail Taxonomy > Frozen > Ice Cream > Ice Cream', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > chocolate', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > vanilla', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @processing_storage > frozen']`

---

## haagen_dazs_vanilla_swiss_almond
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Ice Cream"` | `"Frozen > Ice Cream"` |
| `product_identity` | `"Ice Cream"` | `"Ice Cream"` |
| `canonical_path` | `"Frozen > Ice Cream > Ice Cream"` | `"Frozen > Ice Cream > Ice Cream"` |
| `variant` * | `["vanilla_swiss_almond"]` | `[]` |
| `flavor` * | `[]` | `["vanilla", "almond"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `[]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Ice Cream (Vanilla Swiss Almond)"` | `"Ice Cream (Vanilla, Almond, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Ice Cream > Ice Cream", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @variant > vanilla_swiss_almond"]` | `["Retail Taxonomy > Frozen > Ice Cream > Ice Cream", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > vanilla", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > almond", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['vanilla_swiss_almond']:actual=[]`
- `core_mismatch:flavor:expected=[]:actual=['vanilla', 'almond']`
- `core_mismatch:processing_storage:expected=[]:actual=['frozen']`

**exact errors:**
- `mismatch:canonical_label:expected='Ice Cream (Vanilla Swiss Almond)':actual='Ice Cream (Vanilla, Almond, Frozen)'`
- `mismatch:variant:expected=['vanilla_swiss_almond']:actual=[]`
- `mismatch:flavor:expected=[]:actual=['vanilla', 'almond']`
- `mismatch:processing_storage:expected=[]:actual=['frozen']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Ice Cream > Ice Cream', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @variant > vanilla_swiss_almond']:actual=['Retail Taxonomy > Frozen > Ice Cream > Ice Cream', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > vanilla', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > almond', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @processing_storage > frozen']`

---

## talenti_sea_salt_caramel_gelato
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Gelato"` | `"Frozen > Gelato"` |
| `product_identity` | `"Gelato"` | `"Gelato"` |
| `canonical_path` | `"Frozen > Gelato > Gelato"` | `"Frozen > Gelato > Gelato"` |
| `variant` * | `[]` | `["sea_salt_caramel"]` |
| `flavor` * | `["sea_salt_caramel"]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `[]` | `["frozen"]` |
| `claims` * | `[]` | `["no_sugar_added", "light"]` |
| `canonical_label` * | `"Gelato (Sea Salt Caramel)"` | `"Gelato (Sea Salt Caramel, Frozen, No Sugar Added, Light)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Gelato > Gelato", "Retail Taxonomy > Frozen > Gelato > Gelato > @flavor > sea_salt_caramel"]` | `["Retail Taxonomy > Frozen > Gelato > Gelato", "Retail Taxonomy > Frozen > Gelato > Gelato > @variant > sea_salt_caramel", "Retail Taxonomy > Frozen > Gelato > Gelato > @processing_storage > frozen", "Retail Taxonomy > Frozen > Gelato > Gelato > @claims > no_sugar_added", "Retail Taxonomy > Frozen > Gelato > Gelato > @claims > light"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['sea_salt_caramel']`
- `core_mismatch:flavor:expected=['sea_salt_caramel']:actual=[]`
- `core_mismatch:processing_storage:expected=[]:actual=['frozen']`
- `core_mismatch:claims:expected=[]:actual=['no_sugar_added', 'light']`

**exact errors:**
- `mismatch:canonical_label:expected='Gelato (Sea Salt Caramel)':actual='Gelato (Sea Salt Caramel, Frozen, No Sugar Added, Light)'`
- `mismatch:variant:expected=[]:actual=['sea_salt_caramel']`
- `mismatch:flavor:expected=['sea_salt_caramel']:actual=[]`
- `mismatch:processing_storage:expected=[]:actual=['frozen']`
- `mismatch:claims:expected=[]:actual=['no_sugar_added', 'light']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Gelato > Gelato', 'Retail Taxonomy > Frozen > Gelato > Gelato > @flavor > sea_salt_caramel']:actual=['Retail Taxonomy > Frozen > Gelato > Gelato', 'Retail Taxonomy > Frozen > Gelato > Gelato > @variant > sea_salt_caramel', 'Retail Taxonomy > Frozen > Gelato > Gelato > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Gelato > Gelato > @claims > no_sugar_added', 'Retail Taxonomy > Frozen > Gelato > Gelato > @claims > light']`

---

## vanilla_ice_cream_plain
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Ice Cream"` | `"Frozen > Ice Cream"` |
| `product_identity` | `"Ice Cream"` | `"Ice Cream"` |
| `canonical_path` | `"Frozen > Ice Cream > Ice Cream"` | `"Frozen > Ice Cream > Ice Cream"` |
| `variant` | `[]` | `[]` |
| `flavor` * | `["vanilla"]` | `["chocolate", "vanilla"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `[]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Ice Cream (Vanilla)"` | `"Ice Cream (Chocolate, Vanilla, Frozen)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Ice Cream > Ice Cream", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > vanilla"]` | `["Retail Taxonomy > Frozen > Ice Cream > Ice Cream", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > chocolate", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > vanilla", "Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:flavor:expected=['vanilla']:actual=['chocolate', 'vanilla']`
- `core_mismatch:processing_storage:expected=[]:actual=['frozen']`

**exact errors:**
- `mismatch:canonical_label:expected='Ice Cream (Vanilla)':actual='Ice Cream (Chocolate, Vanilla, Frozen)'`
- `mismatch:flavor:expected=['vanilla']:actual=['chocolate', 'vanilla']`
- `mismatch:processing_storage:expected=[]:actual=['frozen']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Ice Cream > Ice Cream', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > vanilla']:actual=['Retail Taxonomy > Frozen > Ice Cream > Ice Cream', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > chocolate', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @flavor > vanilla', 'Retail Taxonomy > Frozen > Ice Cream > Ice Cream > @processing_storage > frozen']`

---

## horseradish_aioli_sauce
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Sauces & Salsas"` | `"Pantry > Sauces & Salsas"` |
| `product_identity` | `"Aioli"` | `"Aioli"` |
| `canonical_path` | `"Pantry > Sauces & Salsas > Aioli"` | `"Pantry > Sauces & Salsas > Aioli"` |
| `variant` * | `[]` | `["horseradish"]` |
| `flavor` * | `["horseradish"]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Aioli (Horseradish)"` | `"Aioli (Horseradish)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Sauces & Salsas > Aioli", "Retail Taxonomy > Pantry > Sauces & Salsas > Aioli > @flavor > horseradish"]` | `["Retail Taxonomy > Pantry > Sauces & Salsas > Aioli", "Retail Taxonomy > Pantry > Sauces & Salsas > Aioli > @variant > horseradish"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['horseradish']`
- `core_mismatch:flavor:expected=['horseradish']:actual=[]`

**exact errors:**
- `mismatch:variant:expected=[]:actual=['horseradish']`
- `mismatch:flavor:expected=['horseradish']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Sauces & Salsas > Aioli', 'Retail Taxonomy > Pantry > Sauces & Salsas > Aioli > @flavor > horseradish']:actual=['Retail Taxonomy > Pantry > Sauces & Salsas > Aioli', 'Retail Taxonomy > Pantry > Sauces & Salsas > Aioli > @variant > horseradish']`

---

## sriracha_mayo
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Sauces & Salsas"` | `"Pantry > Sauces & Salsas"` |
| `product_identity` | `"Mayonnaise"` | `"Mayonnaise"` |
| `canonical_path` | `"Pantry > Sauces & Salsas > Mayonnaise"` | `"Pantry > Sauces & Salsas > Mayonnaise"` |
| `variant` * | `[]` | `["sriracha"]` |
| `flavor` | `["sriracha"]` | `["sriracha"]` |
| `form_texture_cut` * | `[]` | `["spreadable"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Mayonnaise (Sriracha)"` | `"Mayonnaise (Sriracha, Sriracha, Spreadable)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Sauces & Salsas > Mayonnaise", "Retail Taxonomy > Pantry > Sauces & Salsas > Mayonnaise > @flavor > sriracha"]` | `["Retail Taxonomy > Pantry > Sauces & Salsas > Mayonnaise", "Retail Taxonomy > Pantry > Sauces & Salsas > Mayonnaise > @variant > sriracha", "Retail Taxonomy > Pantry > Sauces & Salsas > Mayonnaise > @flavor > sriracha", "Retail Taxonomy > Pantry > Sauces & Salsas > Mayonnaise > @form_texture_cut > spreadable"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['sriracha']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['spreadable']`

**exact errors:**
- `mismatch:canonical_label:expected='Mayonnaise (Sriracha)':actual='Mayonnaise (Sriracha, Sriracha, Spreadable)'`
- `mismatch:variant:expected=[]:actual=['sriracha']`
- `mismatch:form_texture_cut:expected=[]:actual=['spreadable']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Sauces & Salsas > Mayonnaise', 'Retail Taxonomy > Pantry > Sauces & Salsas > Mayonnaise > @flavor > sriracha']:actual=['Retail Taxonomy > Pantry > Sauces & Salsas > Mayonnaise', 'Retail Taxonomy > Pantry > Sauces & Salsas > Mayonnaise > @variant > sriracha', 'Retail Taxonomy > Pantry > Sauces & Salsas > Mayonnaise > @flavor > sriracha', 'Retail Taxonomy > Pantry > Sauces & Salsas > Mayonnaise > @form_texture_cut > spreadable']`

---

## honey_mustard_dressing
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"single"` | `"shelf_stable"` |
| `category_path` | `"Pantry > Salad Dressings"` | `"Pantry > Salad Dressings"` |
| `product_identity` | `"Salad Dressing"` | `"Salad Dressing"` |
| `canonical_path` | `"Pantry > Salad Dressings > Salad Dressing"` | `"Pantry > Salad Dressings > Salad Dressing"` |
| `variant` * | `[]` | `["honey_mustard"]` |
| `flavor` * | `["honey_mustard"]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Salad Dressing (Honey Mustard)"` | `"Salad Dressing (Honey Mustard)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing", "Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing > @flavor > honey_mustard"]` | `["Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing", "Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing > @variant > honey_mustard"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `invalid_retail_type:shelf_stable`
- `core_mismatch:retail_type:expected='single':actual='shelf_stable'`
- `core_mismatch:variant:expected=[]:actual=['honey_mustard']`
- `core_mismatch:flavor:expected=['honey_mustard']:actual=[]`

**exact errors:**
- `invalid_retail_type:shelf_stable`
- `mismatch:retail_type:expected='single':actual='shelf_stable'`
- `mismatch:variant:expected=[]:actual=['honey_mustard']`
- `mismatch:flavor:expected=['honey_mustard']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing', 'Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing > @flavor > honey_mustard']:actual=['Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing', 'Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing > @variant > honey_mustard']`

---

## chipotle_ranch_dressing
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Salad Dressings"` | `"Pantry > Salad Dressings"` |
| `product_identity` * | `"Ranch Dressing"` | `"Salad Dressing"` |
| `canonical_path` * | `"Pantry > Salad Dressings > Ranch Dressing"` | `"Pantry > Salad Dressings > Salad Dressing"` |
| `variant` * | `[]` | `["ranch"]` |
| `flavor` | `["chipotle"]` | `["chipotle"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Ranch Dressing (Chipotle)"` | `"Salad Dressing (Ranch, Chipotle)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Salad Dressings > Ranch Dressing", "Retail Taxonomy > Pantry > Salad Dressings > Ranch Dressing > @flavor > chipotle"]` | `["Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing", "Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing > @variant > ranch", "Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing > @flavor > chipotle"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Ranch Dressing':actual='Salad Dressing'`
- `core_mismatch:canonical_path:expected='Pantry > Salad Dressings > Ranch Dressing':actual='Pantry > Salad Dressings > Salad Dressing'`
- `core_mismatch:variant:expected=[]:actual=['ranch']`

**exact errors:**
- `mismatch:product_identity:expected='Ranch Dressing':actual='Salad Dressing'`
- `mismatch:canonical_path:expected='Pantry > Salad Dressings > Ranch Dressing':actual='Pantry > Salad Dressings > Salad Dressing'`
- `mismatch:canonical_label:expected='Ranch Dressing (Chipotle)':actual='Salad Dressing (Ranch, Chipotle)'`
- `mismatch:variant:expected=[]:actual=['ranch']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Salad Dressings > Ranch Dressing', 'Retail Taxonomy > Pantry > Salad Dressings > Ranch Dressing > @flavor > chipotle']:actual=['Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing', 'Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing > @variant > ranch', 'Retail Taxonomy > Pantry > Salad Dressings > Salad Dressing > @flavor > chipotle']`

---

## garlic_herb_butter
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Dairy > Butter"` | `"Dairy > Butter"` |
| `product_identity` | `"Butter"` | `"Butter"` |
| `canonical_path` | `"Dairy > Butter > Butter"` | `"Dairy > Butter > Butter"` |
| `variant` * | `["compound"]` | `["garlic_herb", "clarified"]` |
| `flavor` * | `["garlic_herb"]` | `["garlic", "herb"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Butter (Compound, Garlic Herb)"` | `"Butter (Garlic Herb, Clarified, Garlic, Herb)"` |
| `tree_paths` * | `["Retail Taxonomy > Dairy > Butter > Butter", "Retail Taxonomy > Dairy > Butter > Butter > @variant > compound", "Retail Taxonomy > Dairy > Butter > Butter > @flavor > garlic_herb"]` | `["Retail Taxonomy > Dairy > Butter > Butter", "Retail Taxonomy > Dairy > Butter > Butter > @variant > garlic_herb", "Retail Taxonomy > Dairy > Butter > Butter > @variant > clarified", "Retail Taxonomy > Dairy > Butter > Butter > @flavor > garlic", "Retail Taxonomy > Dairy > Butter > Butter > @flavor > herb"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['compound']:actual=['garlic_herb', 'clarified']`
- `core_mismatch:flavor:expected=['garlic_herb']:actual=['garlic', 'herb']`

**exact errors:**
- `mismatch:canonical_label:expected='Butter (Compound, Garlic Herb)':actual='Butter (Garlic Herb, Clarified, Garlic, Herb)'`
- `mismatch:variant:expected=['compound']:actual=['garlic_herb', 'clarified']`
- `mismatch:flavor:expected=['garlic_herb']:actual=['garlic', 'herb']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Dairy > Butter > Butter', 'Retail Taxonomy > Dairy > Butter > Butter > @variant > compound', 'Retail Taxonomy > Dairy > Butter > Butter > @flavor > garlic_herb']:actual=['Retail Taxonomy > Dairy > Butter > Butter', 'Retail Taxonomy > Dairy > Butter > Butter > @variant > garlic_herb', 'Retail Taxonomy > Dairy > Butter > Butter > @variant > clarified', 'Retail Taxonomy > Dairy > Butter > Butter > @flavor > garlic', 'Retail Taxonomy > Dairy > Butter > Butter > @flavor > herb']`

---

## 12_grain_bread
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Bread"` | `"Bakery > Bread"` |
| `product_identity` | `"Bread"` | `"Bread"` |
| `canonical_path` | `"Bakery > Bread > Bread"` | `"Bakery > Bread > Bread"` |
| `variant` * | `["12_grain"]` | `["12_grain", "multigrain"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["whole_grain", "multigrain"]` |
| `canonical_label` * | `"Bread (12 Grain)"` | `"Bread (12 Grain, Multigrain, Whole Grain, Multigrain)"` |
| `tree_paths` * | `["Retail Taxonomy > Bakery > Bread > Bread", "Retail Taxonomy > Bakery > Bread > Bread > @variant > 12_grain"]` | `["Retail Taxonomy > Bakery > Bread > Bread", "Retail Taxonomy > Bakery > Bread > Bread > @variant > 12_grain", "Retail Taxonomy > Bakery > Bread > Bread > @variant > multigrain", "Retail Taxonomy > Bakery > Bread > Bread > @claims > whole_grain", "Retail Taxonomy > Bakery > Bread > Bread > @claims > multigrain"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['12_grain']:actual=['12_grain', 'multigrain']`
- `core_mismatch:claims:expected=[]:actual=['whole_grain', 'multigrain']`

**exact errors:**
- `mismatch:canonical_label:expected='Bread (12 Grain)':actual='Bread (12 Grain, Multigrain, Whole Grain, Multigrain)'`
- `mismatch:variant:expected=['12_grain']:actual=['12_grain', 'multigrain']`
- `mismatch:claims:expected=[]:actual=['whole_grain', 'multigrain']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Bakery > Bread > Bread', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > 12_grain']:actual=['Retail Taxonomy > Bakery > Bread > Bread', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > 12_grain', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > multigrain', 'Retail Taxonomy > Bakery > Bread > Bread > @claims > whole_grain', 'Retail Taxonomy > Bakery > Bread > Bread > @claims > multigrain']`

---

## 15_grain_bread
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Bread"` | `"Bakery > Bread"` |
| `product_identity` | `"Bread"` | `"Bread"` |
| `canonical_path` | `"Bakery > Bread > Bread"` | `"Bakery > Bread > Bread"` |
| `variant` * | `["15_grain"]` | `["multigrain", "seeds"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["whole_grain"]` |
| `canonical_label` * | `"Bread (15 Grain)"` | `"Bread (Multigrain, Seeds, Whole Grain)"` |
| `tree_paths` * | `["Retail Taxonomy > Bakery > Bread > Bread", "Retail Taxonomy > Bakery > Bread > Bread > @variant > 15_grain"]` | `["Retail Taxonomy > Bakery > Bread > Bread", "Retail Taxonomy > Bakery > Bread > Bread > @variant > multigrain", "Retail Taxonomy > Bakery > Bread > Bread > @variant > seeds", "Retail Taxonomy > Bakery > Bread > Bread > @claims > whole_grain"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['15_grain']:actual=['multigrain', 'seeds']`
- `core_mismatch:claims:expected=[]:actual=['whole_grain']`

**exact errors:**
- `mismatch:canonical_label:expected='Bread (15 Grain)':actual='Bread (Multigrain, Seeds, Whole Grain)'`
- `mismatch:variant:expected=['15_grain']:actual=['multigrain', 'seeds']`
- `mismatch:claims:expected=[]:actual=['whole_grain']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Bakery > Bread > Bread', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > 15_grain']:actual=['Retail Taxonomy > Bakery > Bread > Bread', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > multigrain', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > seeds', 'Retail Taxonomy > Bakery > Bread > Bread > @claims > whole_grain']`

---

## whole_wheat_sourdough
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Bread"` | `"Bakery > Bread"` |
| `product_identity` * | `"Sourdough Bread"` | `"Bread"` |
| `canonical_path` * | `"Bakery > Bread > Sourdough Bread"` | `"Bakery > Bread > Bread"` |
| `variant` * | `["whole_wheat"]` | `["whole_wheat", "artisan"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["baguette"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Sourdough Bread (Whole Wheat)"` | `"Bread (Whole Wheat, Artisan, Baguette)"` |
| `tree_paths` * | `["Retail Taxonomy > Bakery > Bread > Sourdough Bread", "Retail Taxonomy > Bakery > Bread > Sourdough Bread > @variant > whole_wheat"]` | `["Retail Taxonomy > Bakery > Bread > Bread", "Retail Taxonomy > Bakery > Bread > Bread > @variant > whole_wheat", "Retail Taxonomy > Bakery > Bread > Bread > @variant > artisan", "Retail Taxonomy > Bakery > Bread > Bread > @form_texture_cut > baguette"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Sourdough Bread':actual='Bread'`
- `core_mismatch:canonical_path:expected='Bakery > Bread > Sourdough Bread':actual='Bakery > Bread > Bread'`
- `core_mismatch:variant:expected=['whole_wheat']:actual=['whole_wheat', 'artisan']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['baguette']`

**exact errors:**
- `mismatch:product_identity:expected='Sourdough Bread':actual='Bread'`
- `mismatch:canonical_path:expected='Bakery > Bread > Sourdough Bread':actual='Bakery > Bread > Bread'`
- `mismatch:canonical_label:expected='Sourdough Bread (Whole Wheat)':actual='Bread (Whole Wheat, Artisan, Baguette)'`
- `mismatch:variant:expected=['whole_wheat']:actual=['whole_wheat', 'artisan']`
- `mismatch:form_texture_cut:expected=[]:actual=['baguette']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Bakery > Bread > Sourdough Bread', 'Retail Taxonomy > Bakery > Bread > Sourdough Bread > @variant > whole_wheat']:actual=['Retail Taxonomy > Bakery > Bread > Bread', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > whole_wheat', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > artisan', 'Retail Taxonomy > Bakery > Bread > Bread > @form_texture_cut > baguette']`

---

## multi_seed_sandwich_bread
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Bread"` | `"Bakery > Bread"` |
| `product_identity` | `"Bread"` | `"Bread"` |
| `canonical_path` | `"Bakery > Bread > Bread"` | `"Bakery > Bread > Bread"` |
| `variant` * | `["multi_seed"]` | `["multi_seed", "sandwich"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `["sandwich"]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["keto"]` |
| `canonical_label` * | `"Bread (Multi Seed, Sandwich)"` | `"Bread (Multi Seed, Sandwich, Keto)"` |
| `tree_paths` * | `["Retail Taxonomy > Bakery > Bread > Bread", "Retail Taxonomy > Bakery > Bread > Bread > @variant > multi_seed", "Retail Taxonomy > Bakery > Bread > Bread > @form_texture_cut > sandwich"]` | `["Retail Taxonomy > Bakery > Bread > Bread", "Retail Taxonomy > Bakery > Bread > Bread > @variant > multi_seed", "Retail Taxonomy > Bakery > Bread > Bread > @variant > sandwich", "Retail Taxonomy > Bakery > Bread > Bread > @claims > keto"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['multi_seed']:actual=['multi_seed', 'sandwich']`
- `core_mismatch:form_texture_cut:expected=['sandwich']:actual=[]`
- `core_mismatch:claims:expected=[]:actual=['keto']`

**exact errors:**
- `mismatch:canonical_label:expected='Bread (Multi Seed, Sandwich)':actual='Bread (Multi Seed, Sandwich, Keto)'`
- `mismatch:variant:expected=['multi_seed']:actual=['multi_seed', 'sandwich']`
- `mismatch:form_texture_cut:expected=['sandwich']:actual=[]`
- `mismatch:claims:expected=[]:actual=['keto']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Bakery > Bread > Bread', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > multi_seed', 'Retail Taxonomy > Bakery > Bread > Bread > @form_texture_cut > sandwich']:actual=['Retail Taxonomy > Bakery > Bread > Bread', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > multi_seed', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > sandwich', 'Retail Taxonomy > Bakery > Bread > Bread > @claims > keto']`

---

## sprouted_grain_bread
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Bread"` | `"Bakery > Bread"` |
| `product_identity` | `"Bread"` | `"Bread"` |
| `canonical_path` | `"Bakery > Bread > Bread"` | `"Bakery > Bread > Bread"` |
| `variant` | `["sprouted_grain"]` | `["sprouted_grain"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["whole_grain", "sprouted"]` |
| `canonical_label` * | `"Bread (Sprouted Grain)"` | `"Bread (Sprouted Grain, Whole Grain, Sprouted)"` |
| `tree_paths` * | `["Retail Taxonomy > Bakery > Bread > Bread", "Retail Taxonomy > Bakery > Bread > Bread > @variant > sprouted_grain"]` | `["Retail Taxonomy > Bakery > Bread > Bread", "Retail Taxonomy > Bakery > Bread > Bread > @variant > sprouted_grain", "Retail Taxonomy > Bakery > Bread > Bread > @claims > whole_grain", "Retail Taxonomy > Bakery > Bread > Bread > @claims > sprouted"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:claims:expected=[]:actual=['whole_grain', 'sprouted']`

**exact errors:**
- `mismatch:canonical_label:expected='Bread (Sprouted Grain)':actual='Bread (Sprouted Grain, Whole Grain, Sprouted)'`
- `mismatch:claims:expected=[]:actual=['whole_grain', 'sprouted']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Bakery > Bread > Bread', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > sprouted_grain']:actual=['Retail Taxonomy > Bakery > Bread > Bread', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > sprouted_grain', 'Retail Taxonomy > Bakery > Bread > Bread > @claims > whole_grain', 'Retail Taxonomy > Bakery > Bread > Bread > @claims > sprouted']`

---

## ezekiel_4_9_sprouted_bread
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Bread"` | `"Bakery > Bread"` |
| `product_identity` | `"Bread"` | `"Bread"` |
| `canonical_path` | `"Bakery > Bread > Bread"` | `"Bakery > Bread > Bread"` |
| `variant` * | `["sprouted_whole_grain"]` | `["sprouted_grain"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["loaf"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["whole_grain"]` | `["whole_grain", "organic", "sprouted"]` |
| `canonical_label` * | `"Bread (Sprouted Whole Grain, Whole Grain)"` | `"Bread (Sprouted Grain, Loaf, Whole Grain, Organic, Sprouted)"` |
| `tree_paths` * | `["Retail Taxonomy > Bakery > Bread > Bread", "Retail Taxonomy > Bakery > Bread > Bread > @variant > sprouted_whole_grain", "Retail Taxonomy > Bakery > Bread > Bread > @claims > whole_grain"]` | `["Retail Taxonomy > Bakery > Bread > Bread", "Retail Taxonomy > Bakery > Bread > Bread > @variant > sprouted_grain", "Retail Taxonomy > Bakery > Bread > Bread > @form_texture_cut > loaf", "Retail Taxonomy > Bakery > Bread > Bread > @claims > whole_grain", "Retail Taxonomy > Bakery > Bread > Bread > @claims > organic", "Retail Taxonomy > Bakery > Bread > Bread > @claims > sprouted"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['sprouted_whole_grain']:actual=['sprouted_grain']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['loaf']`
- `core_mismatch:claims:expected=['whole_grain']:actual=['whole_grain', 'organic', 'sprouted']`

**exact errors:**
- `mismatch:canonical_label:expected='Bread (Sprouted Whole Grain, Whole Grain)':actual='Bread (Sprouted Grain, Loaf, Whole Grain, Organic, Sprouted)'`
- `mismatch:variant:expected=['sprouted_whole_grain']:actual=['sprouted_grain']`
- `mismatch:form_texture_cut:expected=[]:actual=['loaf']`
- `mismatch:claims:expected=['whole_grain']:actual=['whole_grain', 'organic', 'sprouted']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Bakery > Bread > Bread', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > sprouted_whole_grain', 'Retail Taxonomy > Bakery > Bread > Bread > @claims > whole_grain']:actual=['Retail Taxonomy > Bakery > Bread > Bread', 'Retail Taxonomy > Bakery > Bread > Bread > @variant > sprouted_grain', 'Retail Taxonomy > Bakery > Bread > Bread > @form_texture_cut > loaf', 'Retail Taxonomy > Bakery > Bread > Bread > @claims > whole_grain', 'Retail Taxonomy > Bakery > Bread > Bread > @claims > organic', 'Retail Taxonomy > Bakery > Bread > Bread > @claims > sprouted']`

---

## sweet_potato_apple_spice_strips
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Fruit Leather"` | `"Snack > Fruit Leather"` |
| `product_identity` | `"Fruit and Veggie Strips"` | `"Fruit and Veggie Strips"` |
| `canonical_path` | `"Snack > Fruit Leather > Fruit and Veggie Strips"` | `"Snack > Fruit Leather > Fruit and Veggie Strips"` |
| `variant` * | `[]` | `["sweet_potato_apple_spice"]` |
| `flavor` * | `["sweet_potato", "apple", "spices"]` | `[]` |
| `form_texture_cut` * | `["strips"]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["no_sugar_added", "organic"]` |
| `canonical_label` * | `"Fruit and Veggie Strips (Sweet Potato, Apple, Spices, Strips)"` | `"Fruit and Veggie Strips (Sweet Potato Apple Spice, No Sugar Added, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips", "Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @flavor > sweet_potato", "Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @flavor > apple", "Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @flavor > spices", "Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @form_texture_cut > strips"]` | `["Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips", "Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @variant > sweet_potato_apple_spice", "Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @claims > no_sugar_added", "Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['sweet_potato_apple_spice']`
- `core_mismatch:flavor:expected=['sweet_potato', 'apple', 'spices']:actual=[]`
- `core_mismatch:form_texture_cut:expected=['strips']:actual=[]`
- `core_mismatch:claims:expected=[]:actual=['no_sugar_added', 'organic']`

**exact errors:**
- `mismatch:canonical_label:expected='Fruit and Veggie Strips (Sweet Potato, Apple, Spices, Strips)':actual='Fruit and Veggie Strips (Sweet Potato Apple Spice, No Sugar Added, Organic)'`
- `mismatch:variant:expected=[]:actual=['sweet_potato_apple_spice']`
- `mismatch:flavor:expected=['sweet_potato', 'apple', 'spices']:actual=[]`
- `mismatch:form_texture_cut:expected=['strips']:actual=[]`
- `mismatch:claims:expected=[]:actual=['no_sugar_added', 'organic']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips', 'Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @flavor > sweet_potato', 'Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @flavor > apple', 'Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @flavor > spices', 'Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @form_texture_cut > strips']:actual=['Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips', 'Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @variant > sweet_potato_apple_spice', 'Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @claims > no_sugar_added', 'Retail Taxonomy > Snack > Fruit Leather > Fruit and Veggie Strips > @claims > organic']`

---

## fruit_leather_strawberry
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Fruit Leather"` | `"Snack > Fruit Leather"` |
| `product_identity` | `"Fruit Leather"` | `"Fruit Leather"` |
| `canonical_path` | `"Snack > Fruit Leather > Fruit Leather"` | `"Snack > Fruit Leather > Fruit Leather"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["strawberry"]` | `["strawberry"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Fruit Leather (Strawberry)"` | `"Fruit Leather (Strawberry)"` |
| `tree_paths` | `["Retail Taxonomy > Snack > Fruit Leather > Fruit Leather", "Retail Taxonomy > Snack > Fruit Leather > Fruit Leather > @flavor > strawberry"]` | `["Retail Taxonomy > Snack > Fruit Leather > Fruit Leather", "Retail Taxonomy > Snack > Fruit Leather > Fruit Leather > @flavor > strawberry"]` |
| `components` | `[]` | `[]` |

---

## freeze_dried_apple_chips
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Dried Fruit"` | `"Snack > Dried Fruit"` |
| `product_identity` | `"Apple Chips"` | `"Apple Chips"` |
| `canonical_path` | `"Snack > Dried Fruit > Apple Chips"` | `"Snack > Dried Fruit > Apple Chips"` |
| `variant` | `[]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["freeze_dried"]` |
| `processing_storage` * | `["freeze_dried"]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Apple Chips (Freeze Dried)"` | `"Apple Chips (Freeze Dried)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Dried Fruit > Apple Chips", "Retail Taxonomy > Snack > Dried Fruit > Apple Chips > @processing_storage > freeze_dried"]` | `["Retail Taxonomy > Snack > Dried Fruit > Apple Chips", "Retail Taxonomy > Snack > Dried Fruit > Apple Chips > @form_texture_cut > freeze_dried"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:form_texture_cut:expected=[]:actual=['freeze_dried']`
- `core_mismatch:processing_storage:expected=['freeze_dried']:actual=[]`

**exact errors:**
- `mismatch:form_texture_cut:expected=[]:actual=['freeze_dried']`
- `mismatch:processing_storage:expected=['freeze_dried']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Dried Fruit > Apple Chips', 'Retail Taxonomy > Snack > Dried Fruit > Apple Chips > @processing_storage > freeze_dried']:actual=['Retail Taxonomy > Snack > Dried Fruit > Apple Chips', 'Retail Taxonomy > Snack > Dried Fruit > Apple Chips > @form_texture_cut > freeze_dried']`

---

## veggie_straws
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Veggie Snacks"` | `"Snack > Veggie Snacks"` |
| `product_identity` | `"Veggie Straws"` | `"Veggie Straws"` |
| `canonical_path` | `"Snack > Veggie Snacks > Veggie Straws"` | `"Snack > Veggie Snacks > Veggie Straws"` |
| `variant` | `[]` | `[]` |
| `flavor` * | `[]` | `["salt", "vinegar"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Veggie Straws"` | `"Veggie Straws (Salt, Vinegar)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Veggie Snacks > Veggie Straws"]` | `["Retail Taxonomy > Snack > Veggie Snacks > Veggie Straws", "Retail Taxonomy > Snack > Veggie Snacks > Veggie Straws > @flavor > salt", "Retail Taxonomy > Snack > Veggie Snacks > Veggie Straws > @flavor > vinegar"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:flavor:expected=[]:actual=['salt', 'vinegar']`

**exact errors:**
- `mismatch:canonical_label:expected='Veggie Straws':actual='Veggie Straws (Salt, Vinegar)'`
- `mismatch:flavor:expected=[]:actual=['salt', 'vinegar']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Veggie Snacks > Veggie Straws']:actual=['Retail Taxonomy > Snack > Veggie Snacks > Veggie Straws', 'Retail Taxonomy > Snack > Veggie Snacks > Veggie Straws > @flavor > salt', 'Retail Taxonomy > Snack > Veggie Snacks > Veggie Straws > @flavor > vinegar']`

---

## peeled_apples_butterscotch_dip
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"combo_pack"` | `"single"` |
| `category_path` | `"Produce > Snack Packs"` | `"Produce > Snack Packs"` |
| `product_identity` * | `"Apple Snack Pack"` | `"Apple"` |
| `canonical_path` * | `"Produce > Snack Packs > Apple Snack Pack"` | `"Produce > Snack Packs > Apple"` |
| `variant` * | `[]` | `["peeled"]` |
| `flavor` * | `[]` | `["butterscotch"]` |
| `form_texture_cut` * | `["peeled"]` | `["sliced"]` |
| `processing_storage` * | `[]` | `["fresh"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Apple Snack Pack (Peeled)"` | `"Apple (Peeled, Butterscotch, Sliced, Fresh)"` |
| `tree_paths` * | `["Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack", "Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @form_texture_cut > peeled", "Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @components > apples", "Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @components > butterscotch_dip"]` | `["Retail Taxonomy > Produce > Snack Packs > Apple", "Retail Taxonomy > Produce > Snack Packs > Apple > @variant > peeled", "Retail Taxonomy > Produce > Snack Packs > Apple > @flavor > butterscotch", "Retail Taxonomy > Produce > Snack Packs > Apple > @form_texture_cut > sliced", "Retail Taxonomy > Produce > Snack Packs > Apple > @processing_storage > fresh"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": ["peeled", "sliced"], "identity": "Apples", "processing_storage": [], "role": "fruit", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Butterscotch Dip", "processing_storage": [], "role": "sauce", "variant": []}]` | `[]` |

**core errors:**
- `core_mismatch:retail_type:expected='combo_pack':actual='single'`
- `core_mismatch:product_identity:expected='Apple Snack Pack':actual='Apple'`
- `core_mismatch:canonical_path:expected='Produce > Snack Packs > Apple Snack Pack':actual='Produce > Snack Packs > Apple'`
- `core_mismatch:variant:expected=[]:actual=['peeled']`
- `core_mismatch:flavor:expected=[]:actual=['butterscotch']`
- `core_mismatch:form_texture_cut:expected=['peeled']:actual=['sliced']`
- `core_mismatch:processing_storage:expected=[]:actual=['fresh']`
- `core_mismatch:component_identities:expected=['apples', 'butterscotch_dip']:actual=[]`

**exact errors:**
- `mismatch:retail_type:expected='combo_pack':actual='single'`
- `mismatch:product_identity:expected='Apple Snack Pack':actual='Apple'`
- `mismatch:canonical_path:expected='Produce > Snack Packs > Apple Snack Pack':actual='Produce > Snack Packs > Apple'`
- `mismatch:canonical_label:expected='Apple Snack Pack (Peeled)':actual='Apple (Peeled, Butterscotch, Sliced, Fresh)'`
- `mismatch:variant:expected=[]:actual=['peeled']`
- `mismatch:flavor:expected=[]:actual=['butterscotch']`
- `mismatch:form_texture_cut:expected=['peeled']:actual=['sliced']`
- `mismatch:processing_storage:expected=[]:actual=['fresh']`
- `mismatch:components:expected=[{'identity': 'Apples', 'role': 'fruit', 'variant': [], 'flavor': [], 'form_texture_cut': ['peeled', 'sliced'], 'processing_storage': [], 'claims': []}, {'identity': 'Butterscotch Dip', 'role': 'sauce', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[]`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack', 'Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @form_texture_cut > peeled', 'Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @components > apples', 'Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @components > butterscotch_dip']:actual=['Retail Taxonomy > Produce > Snack Packs > Apple', 'Retail Taxonomy > Produce > Snack Packs > Apple > @variant > peeled', 'Retail Taxonomy > Produce > Snack Packs > Apple > @flavor > butterscotch', 'Retail Taxonomy > Produce > Snack Packs > Apple > @form_texture_cut > sliced', 'Retail Taxonomy > Produce > Snack Packs > Apple > @processing_storage > fresh']`

---

## apples_caramel_snack_pack
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"combo_pack"` | `"single"` |
| `category_path` | `"Produce > Snack Packs"` | `"Produce > Snack Packs"` |
| `product_identity` | `"Apple Snack Pack"` | `"Apple Snack Pack"` |
| `canonical_path` | `"Produce > Snack Packs > Apple Snack Pack"` | `"Produce > Snack Packs > Apple Snack Pack"` |
| `variant` * | `[]` | `["with_caramel_dip"]` |
| `flavor` * | `[]` | `["caramel"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Apple Snack Pack"` | `"Apple Snack Pack (With Caramel Dip, Caramel)"` |
| `tree_paths` * | `["Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack", "Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @components > apples", "Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @components > caramel_dip"]` | `["Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack", "Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @variant > with_caramel_dip", "Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @flavor > caramel"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Apples", "processing_storage": [], "role": "fruit", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Caramel Dip", "processing_storage": [], "role": "sauce", "variant": []}]` | `[]` |

**core errors:**
- `core_mismatch:retail_type:expected='combo_pack':actual='single'`
- `core_mismatch:variant:expected=[]:actual=['with_caramel_dip']`
- `core_mismatch:flavor:expected=[]:actual=['caramel']`
- `core_mismatch:component_identities:expected=['apples', 'caramel_dip']:actual=[]`

**exact errors:**
- `mismatch:retail_type:expected='combo_pack':actual='single'`
- `mismatch:canonical_label:expected='Apple Snack Pack':actual='Apple Snack Pack (With Caramel Dip, Caramel)'`
- `mismatch:variant:expected=[]:actual=['with_caramel_dip']`
- `mismatch:flavor:expected=[]:actual=['caramel']`
- `mismatch:components:expected=[{'identity': 'Apples', 'role': 'fruit', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Caramel Dip', 'role': 'sauce', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack', 'Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @components > apples', 'Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @components > caramel_dip']:actual=['Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack', 'Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @variant > with_caramel_dip', 'Retail Taxonomy > Produce > Snack Packs > Apple Snack Pack > @flavor > caramel']`

---

## cheese_crackers_snack_pack
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"combo_pack"` | `"single"` |
| `category_path` * | `"Snack > Snack Packs"` | `"Dairy > Cheese"` |
| `product_identity` * | `"Cheese and Crackers Pack"` | `"Cheese"` |
| `canonical_path` * | `"Snack > Snack Packs > Cheese and Crackers Pack"` | `"Dairy > Cheese > Cheese"` |
| `variant` * | `[]` | `["crackers_and", "pepperoni", "colby_jack_cheese_cubes", "crostini_crackers"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["cubed", "crisp"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Cheese and Crackers Pack"` | `"Cheese (Crackers And, Pepperoni, Colby Jack Cheese Cubes, Crostini Crackers, Cubed, Crisp)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Snack Packs > Cheese and Crackers Pack", "Retail Taxonomy > Snack > Snack Packs > Cheese and Crackers Pack > @components > cheese", "Retail Taxonomy > Snack > Snack Packs > Cheese and Crackers Pack > @components > crackers"]` | `["Retail Taxonomy > Dairy > Cheese > Cheese", "Retail Taxonomy > Dairy > Cheese > Cheese > @variant > crackers_and", "Retail Taxonomy > Dairy > Cheese > Cheese > @variant > pepperoni", "Retail Taxonomy > Dairy > Cheese > Cheese > @variant > colby_jack_cheese_cubes", "Retail Taxonomy > Dairy > Cheese > Cheese > @variant > crostini_crackers", "Retail Taxonomy > Dairy > Cheese > Cheese > @form_texture_cut > cubed", "Retail Taxonomy > Dairy > Cheese > Cheese > @form_texture_cut > crisp"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Cheese", "processing_storage": [], "role": "cheese", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Crackers", "processing_storage": [], "role": "ingredient", "variant": []}]` | `[]` |

**core errors:**
- `core_mismatch:retail_type:expected='combo_pack':actual='single'`
- `core_mismatch:category_path:expected='Snack > Snack Packs':actual='Dairy > Cheese'`
- `core_mismatch:product_identity:expected='Cheese and Crackers Pack':actual='Cheese'`
- `core_mismatch:canonical_path:expected='Snack > Snack Packs > Cheese and Crackers Pack':actual='Dairy > Cheese > Cheese'`
- `core_mismatch:variant:expected=[]:actual=['crackers_and', 'pepperoni', 'colby_jack_cheese_cubes', 'crostini_crackers']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['cubed', 'crisp']`
- `core_mismatch:component_identities:expected=['cheese', 'crackers']:actual=[]`

**exact errors:**
- `mismatch:retail_type:expected='combo_pack':actual='single'`
- `mismatch:category_path:expected='Snack > Snack Packs':actual='Dairy > Cheese'`
- `mismatch:product_identity:expected='Cheese and Crackers Pack':actual='Cheese'`
- `mismatch:canonical_path:expected='Snack > Snack Packs > Cheese and Crackers Pack':actual='Dairy > Cheese > Cheese'`
- `mismatch:canonical_label:expected='Cheese and Crackers Pack':actual='Cheese (Crackers And, Pepperoni, Colby Jack Cheese Cubes, Crostini Crackers, Cubed, Crisp)'`
- `mismatch:variant:expected=[]:actual=['crackers_and', 'pepperoni', 'colby_jack_cheese_cubes', 'crostini_crackers']`
- `mismatch:form_texture_cut:expected=[]:actual=['cubed', 'crisp']`
- `mismatch:components:expected=[{'identity': 'Cheese', 'role': 'cheese', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Crackers', 'role': 'ingredient', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[]`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Snack Packs > Cheese and Crackers Pack', 'Retail Taxonomy > Snack > Snack Packs > Cheese and Crackers Pack > @components > cheese', 'Retail Taxonomy > Snack > Snack Packs > Cheese and Crackers Pack > @components > crackers']:actual=['Retail Taxonomy > Dairy > Cheese > Cheese', 'Retail Taxonomy > Dairy > Cheese > Cheese > @variant > crackers_and', 'Retail Taxonomy > Dairy > Cheese > Cheese > @variant > pepperoni', 'Retail Taxonomy > Dairy > Cheese > Cheese > @variant > colby_jack_cheese_cubes', 'Retail Taxonomy > Dairy > Cheese > Cheese > @variant > crostini_crackers', 'Retail Taxonomy > Dairy > Cheese > Cheese > @form_texture_cut > cubed', 'Retail Taxonomy > Dairy > Cheese > Cheese > @form_texture_cut > crisp']`

---

## lunchable_pizza
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"combo_pack"` | `"meal_kit"` |
| `category_path` | `"Refrigerated > Lunch Kits"` | `"Refrigerated > Lunch Kits"` |
| `product_identity` | `"Lunch Kit"` | `"Lunch Kit"` |
| `canonical_path` | `"Refrigerated > Lunch Kits > Lunch Kit"` | `"Refrigerated > Lunch Kits > Lunch Kit"` |
| `variant` * | `["pizza_with_pepperoni"]` | `["pepperoni_pizza"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `[]` | `["refrigerated"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Lunch Kit (Pizza With Pepperoni)"` | `"Lunch Kit (Pepperoni Pizza, Refrigerated)"` |
| `tree_paths` * | `["Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit", "Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @variant > pizza_with_pepperoni", "Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > pizza_crusts", "Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > pizza_sauce", "Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > mozzarella_cheese", "Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > pepperoni"]` | `["Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit", "Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @variant > pepperoni_pizza", "Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @processing_storage > refrigerated", "Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > pizza_crust", "Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > pizza_sauce", "Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > mozzarella_cheese", "Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > pepperoni", "Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > fruit_drink"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Pizza Crusts", "processing_storage": [], "role": "ingredient", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Pizza Sauce", "processing_storage": [], "role": "sauce", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Mozzarella Cheese", "processing_storage": [], "role": "cheese", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Pepperoni", "processing_storage": [], "role": "protein", "variant": []}]` | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Pizza Crust", "processing_storage": [], "role": "base", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Pizza Sauce", "processing_storage": [], "role": "sauce", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": ["shredded"], "identity": "Mozzarella Cheese", "processing_storage": [], "role": "cheese", "variant": []}, {"claims": [], "flavor": [], "form_texture_cut": ["sliced"], "identity": "Pepperoni", "processing_storage": [], "role": "topping", "variant": []}, {"claims": [], "flavor": ["mixed_fruit"], "form_texture_cut": [], "identity": "Fruit Drink", "processing_storage": [], "role": "beverage", "variant": []}]` |

**core errors:**
- `core_mismatch:retail_type:expected='combo_pack':actual='meal_kit'`
- `core_mismatch:variant:expected=['pizza_with_pepperoni']:actual=['pepperoni_pizza']`
- `core_mismatch:processing_storage:expected=[]:actual=['refrigerated']`
- `core_mismatch:component_identities:expected=['mozzarella_cheese', 'pepperoni', 'pizza_crusts', 'pizza_sauce']:actual=['fruit_drink', 'mozzarella_cheese', 'pepperoni', 'pizza_crust', 'pizza_sauce']`

**exact errors:**
- `mismatch:retail_type:expected='combo_pack':actual='meal_kit'`
- `mismatch:canonical_label:expected='Lunch Kit (Pizza With Pepperoni)':actual='Lunch Kit (Pepperoni Pizza, Refrigerated)'`
- `mismatch:variant:expected=['pizza_with_pepperoni']:actual=['pepperoni_pizza']`
- `mismatch:processing_storage:expected=[]:actual=['refrigerated']`
- `mismatch:components:expected=[{'identity': 'Pizza Crusts', 'role': 'ingredient', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Pizza Sauce', 'role': 'sauce', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Mozzarella Cheese', 'role': 'cheese', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Pepperoni', 'role': 'protein', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[{'identity': 'Pizza Crust', 'role': 'base', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Pizza Sauce', 'role': 'sauce', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}, {'identity': 'Mozzarella Cheese', 'role': 'cheese', 'variant': [], 'flavor': [], 'form_texture_cut': ['shredded'], 'processing_storage': [], 'claims': []}, {'identity': 'Pepperoni', 'role': 'topping', 'variant': [], 'flavor': [], 'form_texture_cut': ['sliced'], 'processing_storage': [], 'claims': []}, {'identity': 'Fruit Drink', 'role': 'beverage', 'variant': [], 'flavor': ['mixed_fruit'], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit', 'Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @variant > pizza_with_pepperoni', 'Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > pizza_crusts', 'Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > pizza_sauce', 'Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > mozzarella_cheese', 'Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > pepperoni']:actual=['Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit', 'Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @variant > pepperoni_pizza', 'Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @processing_storage > refrigerated', 'Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > pizza_crust', 'Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > pizza_sauce', 'Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > mozzarella_cheese', 'Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > pepperoni', 'Retail Taxonomy > Refrigerated > Lunch Kits > Lunch Kit > @components > fruit_drink']`

---

## culinary_crisps_apple_oat_crunch
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Crackers"` | `"Snack > Crackers"` |
| `product_identity` * | `"Flatbread Crisps"` | `"Cracker"` |
| `canonical_path` * | `"Snack > Crackers > Flatbread Crisps"` | `"Snack > Crackers > Cracker"` |
| `variant` * | `[]` | `["apple_oat_crunch"]` |
| `flavor` * | `["apple", "oat"]` | `[]` |
| `form_texture_cut` * | `["crunch"]` | `["crisp", "crispy"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["whole_grain", "organic"]` |
| `canonical_label` * | `"Flatbread Crisps (Apple, Oat, Crunch)"` | `"Cracker (Apple Oat Crunch, Crisp, Crispy, Whole Grain, Organic)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Crackers > Flatbread Crisps", "Retail Taxonomy > Snack > Crackers > Flatbread Crisps > @flavor > apple", "Retail Taxonomy > Snack > Crackers > Flatbread Crisps > @flavor > oat", "Retail Taxonomy > Snack > Crackers > Flatbread Crisps > @form_texture_cut > crunch"]` | `["Retail Taxonomy > Snack > Crackers > Cracker", "Retail Taxonomy > Snack > Crackers > Cracker > @variant > apple_oat_crunch", "Retail Taxonomy > Snack > Crackers > Cracker > @form_texture_cut > crisp", "Retail Taxonomy > Snack > Crackers > Cracker > @form_texture_cut > crispy", "Retail Taxonomy > Snack > Crackers > Cracker > @claims > whole_grain", "Retail Taxonomy > Snack > Crackers > Cracker > @claims > organic"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Flatbread Crisps':actual='Cracker'`
- `core_mismatch:canonical_path:expected='Snack > Crackers > Flatbread Crisps':actual='Snack > Crackers > Cracker'`
- `core_mismatch:variant:expected=[]:actual=['apple_oat_crunch']`
- `core_mismatch:flavor:expected=['apple', 'oat']:actual=[]`
- `core_mismatch:form_texture_cut:expected=['crunch']:actual=['crisp', 'crispy']`
- `core_mismatch:claims:expected=[]:actual=['whole_grain', 'organic']`

**exact errors:**
- `mismatch:product_identity:expected='Flatbread Crisps':actual='Cracker'`
- `mismatch:canonical_path:expected='Snack > Crackers > Flatbread Crisps':actual='Snack > Crackers > Cracker'`
- `mismatch:canonical_label:expected='Flatbread Crisps (Apple, Oat, Crunch)':actual='Cracker (Apple Oat Crunch, Crisp, Crispy, Whole Grain, Organic)'`
- `mismatch:variant:expected=[]:actual=['apple_oat_crunch']`
- `mismatch:flavor:expected=['apple', 'oat']:actual=[]`
- `mismatch:form_texture_cut:expected=['crunch']:actual=['crisp', 'crispy']`
- `mismatch:claims:expected=[]:actual=['whole_grain', 'organic']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Crackers > Flatbread Crisps', 'Retail Taxonomy > Snack > Crackers > Flatbread Crisps > @flavor > apple', 'Retail Taxonomy > Snack > Crackers > Flatbread Crisps > @flavor > oat', 'Retail Taxonomy > Snack > Crackers > Flatbread Crisps > @form_texture_cut > crunch']:actual=['Retail Taxonomy > Snack > Crackers > Cracker', 'Retail Taxonomy > Snack > Crackers > Cracker > @variant > apple_oat_crunch', 'Retail Taxonomy > Snack > Crackers > Cracker > @form_texture_cut > crisp', 'Retail Taxonomy > Snack > Crackers > Cracker > @form_texture_cut > crispy', 'Retail Taxonomy > Snack > Crackers > Cracker > @claims > whole_grain', 'Retail Taxonomy > Snack > Crackers > Cracker > @claims > organic']`

---

## apple_pie_filling_canned
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Pie Fillings"` | `"Pantry > Pie Fillings"` |
| `product_identity` | `"Pie Filling"` | `"Pie Filling"` |
| `canonical_path` | `"Pantry > Pie Fillings > Pie Filling"` | `"Pantry > Pie Fillings > Pie Filling"` |
| `variant` | `[]` | `[]` |
| `flavor` * | `["apple"]` | `["cinnamon", "apple"]` |
| `form_texture_cut` * | `[]` | `["sliced"]` |
| `processing_storage` | `["canned"]` | `["canned"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Pie Filling (Apple, Canned)"` | `"Pie Filling (Cinnamon, Apple, Sliced, Canned)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Pie Fillings > Pie Filling", "Retail Taxonomy > Pantry > Pie Fillings > Pie Filling > @flavor > apple", "Retail Taxonomy > Pantry > Pie Fillings > Pie Filling > @processing_storage > canned"]` | `["Retail Taxonomy > Pantry > Pie Fillings > Pie Filling", "Retail Taxonomy > Pantry > Pie Fillings > Pie Filling > @flavor > cinnamon", "Retail Taxonomy > Pantry > Pie Fillings > Pie Filling > @flavor > apple", "Retail Taxonomy > Pantry > Pie Fillings > Pie Filling > @form_texture_cut > sliced", "Retail Taxonomy > Pantry > Pie Fillings > Pie Filling > @processing_storage > canned"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:flavor:expected=['apple']:actual=['cinnamon', 'apple']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['sliced']`

**exact errors:**
- `mismatch:canonical_label:expected='Pie Filling (Apple, Canned)':actual='Pie Filling (Cinnamon, Apple, Sliced, Canned)'`
- `mismatch:flavor:expected=['apple']:actual=['cinnamon', 'apple']`
- `mismatch:form_texture_cut:expected=[]:actual=['sliced']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Pie Fillings > Pie Filling', 'Retail Taxonomy > Pantry > Pie Fillings > Pie Filling > @flavor > apple', 'Retail Taxonomy > Pantry > Pie Fillings > Pie Filling > @processing_storage > canned']:actual=['Retail Taxonomy > Pantry > Pie Fillings > Pie Filling', 'Retail Taxonomy > Pantry > Pie Fillings > Pie Filling > @flavor > cinnamon', 'Retail Taxonomy > Pantry > Pie Fillings > Pie Filling > @flavor > apple', 'Retail Taxonomy > Pantry > Pie Fillings > Pie Filling > @form_texture_cut > sliced', 'Retail Taxonomy > Pantry > Pie Fillings > Pie Filling > @processing_storage > canned']`

---

## apple_butter
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Spreads"` | `"Pantry > Spreads"` |
| `product_identity` | `"Apple Butter"` | `"Apple Butter"` |
| `canonical_path` | `"Pantry > Spreads > Apple Butter"` | `"Pantry > Spreads > Apple Butter"` |
| `variant` | `[]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["spreadable"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Apple Butter"` | `"Apple Butter (Spreadable)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Spreads > Apple Butter"]` | `["Retail Taxonomy > Pantry > Spreads > Apple Butter", "Retail Taxonomy > Pantry > Spreads > Apple Butter > @form_texture_cut > spreadable"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:form_texture_cut:expected=[]:actual=['spreadable']`

**exact errors:**
- `mismatch:canonical_label:expected='Apple Butter':actual='Apple Butter (Spreadable)'`
- `mismatch:form_texture_cut:expected=[]:actual=['spreadable']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Spreads > Apple Butter']:actual=['Retail Taxonomy > Pantry > Spreads > Apple Butter', 'Retail Taxonomy > Pantry > Spreads > Apple Butter > @form_texture_cut > spreadable']`

---

## apple_juice_concentrate
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` * | `"single"` | `"shelf_stable"` |
| `category_path` | `"Frozen > Juice Concentrate"` | `"Frozen > Juice Concentrate"` |
| `product_identity` | `"Juice Concentrate"` | `"Juice Concentrate"` |
| `canonical_path` | `"Frozen > Juice Concentrate > Juice Concentrate"` | `"Frozen > Juice Concentrate > Juice Concentrate"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["apple"]` | `["apple"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `["frozen", "from_concentrate"]` | `["frozen"]` |
| `claims` * | `[]` | `["light", "from_concentrate"]` |
| `canonical_label` * | `"Juice Concentrate (Apple, Frozen, From Concentrate)"` | `"Juice Concentrate (Apple, Frozen, Light, From Concentrate)"` |
| `tree_paths` * | `["Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate", "Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @flavor > apple", "Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @processing_storage > frozen", "Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @processing_storage > from_concentrate"]` | `["Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate", "Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @flavor > apple", "Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @processing_storage > frozen", "Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @claims > light", "Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @claims > from_concentrate"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `invalid_retail_type:shelf_stable`
- `core_mismatch:retail_type:expected='single':actual='shelf_stable'`
- `core_mismatch:processing_storage:expected=['frozen', 'from_concentrate']:actual=['frozen']`
- `core_mismatch:claims:expected=[]:actual=['light', 'from_concentrate']`

**exact errors:**
- `invalid_retail_type:shelf_stable`
- `mismatch:retail_type:expected='single':actual='shelf_stable'`
- `mismatch:canonical_label:expected='Juice Concentrate (Apple, Frozen, From Concentrate)':actual='Juice Concentrate (Apple, Frozen, Light, From Concentrate)'`
- `mismatch:processing_storage:expected=['frozen', 'from_concentrate']:actual=['frozen']`
- `mismatch:claims:expected=[]:actual=['light', 'from_concentrate']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate', 'Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @flavor > apple', 'Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @processing_storage > from_concentrate']:actual=['Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate', 'Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @flavor > apple', 'Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @processing_storage > frozen', 'Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @claims > light', 'Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @claims > from_concentrate']`

---

## applesauce_unsweetened
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Pantry > Applesauce"` | `"Pantry > Applesauce"` |
| `product_identity` | `"Applesauce"` | `"Applesauce"` |
| `canonical_path` | `"Pantry > Applesauce > Applesauce"` | `"Pantry > Applesauce > Applesauce"` |
| `variant` | `[]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["unsweetened"]` | `["no_sugar_added", "unsweetened", "vitamin_c_fortified"]` |
| `canonical_label` * | `"Applesauce (Unsweetened)"` | `"Applesauce (No Sugar Added, Unsweetened, Vitamin C Fortified)"` |
| `tree_paths` * | `["Retail Taxonomy > Pantry > Applesauce > Applesauce", "Retail Taxonomy > Pantry > Applesauce > Applesauce > @claims > unsweetened"]` | `["Retail Taxonomy > Pantry > Applesauce > Applesauce", "Retail Taxonomy > Pantry > Applesauce > Applesauce > @claims > no_sugar_added", "Retail Taxonomy > Pantry > Applesauce > Applesauce > @claims > unsweetened", "Retail Taxonomy > Pantry > Applesauce > Applesauce > @claims > vitamin_c_fortified"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:claims:expected=['unsweetened']:actual=['no_sugar_added', 'unsweetened', 'vitamin_c_fortified']`

**exact errors:**
- `mismatch:canonical_label:expected='Applesauce (Unsweetened)':actual='Applesauce (No Sugar Added, Unsweetened, Vitamin C Fortified)'`
- `mismatch:claims:expected=['unsweetened']:actual=['no_sugar_added', 'unsweetened', 'vitamin_c_fortified']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Pantry > Applesauce > Applesauce', 'Retail Taxonomy > Pantry > Applesauce > Applesauce > @claims > unsweetened']:actual=['Retail Taxonomy > Pantry > Applesauce > Applesauce', 'Retail Taxonomy > Pantry > Applesauce > Applesauce > @claims > no_sugar_added', 'Retail Taxonomy > Pantry > Applesauce > Applesauce > @claims > unsweetened', 'Retail Taxonomy > Pantry > Applesauce > Applesauce > @claims > vitamin_c_fortified']`

---

## vanilla_cupcakes_six_pack
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Cupcakes"` | `"Bakery > Cupcakes"` |
| `product_identity` | `"Cupcakes"` | `"Cupcakes"` |
| `canonical_path` | `"Bakery > Cupcakes > Cupcakes"` | `"Bakery > Cupcakes > Cupcakes"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["vanilla"]` | `["vanilla"]` |
| `form_texture_cut` * | `[]` | `["mini"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Cupcakes (Vanilla)"` | `"Cupcakes (Vanilla, Mini)"` |
| `tree_paths` * | `["Retail Taxonomy > Bakery > Cupcakes > Cupcakes", "Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @flavor > vanilla"]` | `["Retail Taxonomy > Bakery > Cupcakes > Cupcakes", "Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @flavor > vanilla", "Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @form_texture_cut > mini"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:form_texture_cut:expected=[]:actual=['mini']`

**exact errors:**
- `mismatch:canonical_label:expected='Cupcakes (Vanilla)':actual='Cupcakes (Vanilla, Mini)'`
- `mismatch:form_texture_cut:expected=[]:actual=['mini']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Bakery > Cupcakes > Cupcakes', 'Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @flavor > vanilla']:actual=['Retail Taxonomy > Bakery > Cupcakes > Cupcakes', 'Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @flavor > vanilla', 'Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @form_texture_cut > mini']`

---

## chocolate_cupcakes_buttercream
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Cupcakes"` | `"Bakery > Cupcakes"` |
| `product_identity` | `"Cupcakes"` | `"Cupcakes"` |
| `canonical_path` | `"Bakery > Cupcakes > Cupcakes"` | `"Bakery > Cupcakes > Cupcakes"` |
| `variant` * | `[]` | `["buttercream_frosting"]` |
| `flavor` | `["chocolate"]` | `["chocolate"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Cupcakes (Chocolate)"` | `"Cupcakes (Buttercream Frosting, Chocolate)"` |
| `tree_paths` * | `["Retail Taxonomy > Bakery > Cupcakes > Cupcakes", "Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @flavor > chocolate", "Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @components > buttercream_frosting"]` | `["Retail Taxonomy > Bakery > Cupcakes > Cupcakes", "Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @variant > buttercream_frosting", "Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @flavor > chocolate"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Buttercream Frosting", "processing_storage": [], "role": "topping", "variant": []}]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['buttercream_frosting']`
- `core_mismatch:component_identities:expected=['buttercream_frosting']:actual=[]`

**exact errors:**
- `mismatch:canonical_label:expected='Cupcakes (Chocolate)':actual='Cupcakes (Buttercream Frosting, Chocolate)'`
- `mismatch:variant:expected=[]:actual=['buttercream_frosting']`
- `mismatch:components:expected=[{'identity': 'Buttercream Frosting', 'role': 'topping', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[]`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Bakery > Cupcakes > Cupcakes', 'Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @flavor > chocolate', 'Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @components > buttercream_frosting']:actual=['Retail Taxonomy > Bakery > Cupcakes > Cupcakes', 'Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @variant > buttercream_frosting', 'Retail Taxonomy > Bakery > Cupcakes > Cupcakes > @flavor > chocolate']`

---

## sour_cream_pound_cake
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Cake"` | `"Bakery > Cake"` |
| `product_identity` * | `"Pound Cake"` | `"Cake"` |
| `canonical_path` * | `"Bakery > Cake > Pound Cake"` | `"Bakery > Cake > Cake"` |
| `variant` * | `["sour_cream"]` | `["sour_cream", "pound_cake"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Pound Cake (Sour Cream)"` | `"Cake (Sour Cream, Pound Cake)"` |
| `tree_paths` * | `["Retail Taxonomy > Bakery > Cake > Pound Cake", "Retail Taxonomy > Bakery > Cake > Pound Cake > @variant > sour_cream"]` | `["Retail Taxonomy > Bakery > Cake > Cake", "Retail Taxonomy > Bakery > Cake > Cake > @variant > sour_cream", "Retail Taxonomy > Bakery > Cake > Cake > @variant > pound_cake"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Pound Cake':actual='Cake'`
- `core_mismatch:canonical_path:expected='Bakery > Cake > Pound Cake':actual='Bakery > Cake > Cake'`
- `core_mismatch:variant:expected=['sour_cream']:actual=['sour_cream', 'pound_cake']`

**exact errors:**
- `mismatch:product_identity:expected='Pound Cake':actual='Cake'`
- `mismatch:canonical_path:expected='Bakery > Cake > Pound Cake':actual='Bakery > Cake > Cake'`
- `mismatch:canonical_label:expected='Pound Cake (Sour Cream)':actual='Cake (Sour Cream, Pound Cake)'`
- `mismatch:variant:expected=['sour_cream']:actual=['sour_cream', 'pound_cake']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Bakery > Cake > Pound Cake', 'Retail Taxonomy > Bakery > Cake > Pound Cake > @variant > sour_cream']:actual=['Retail Taxonomy > Bakery > Cake > Cake', 'Retail Taxonomy > Bakery > Cake > Cake > @variant > sour_cream', 'Retail Taxonomy > Bakery > Cake > Cake > @variant > pound_cake']`

---

## chocolate_layer_cake
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Cake"` | `"Bakery > Cake"` |
| `product_identity` | `"Cake"` | `"Cake"` |
| `canonical_path` | `"Bakery > Cake > Cake"` | `"Bakery > Cake > Cake"` |
| `variant` * | `["chocolate", "layer"]` | `["layer"]` |
| `flavor` * | `[]` | `["chocolate"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Cake (Chocolate, Layer)"` | `"Cake (Layer, Chocolate)"` |
| `tree_paths` * | `["Retail Taxonomy > Bakery > Cake > Cake", "Retail Taxonomy > Bakery > Cake > Cake > @variant > chocolate", "Retail Taxonomy > Bakery > Cake > Cake > @variant > layer"]` | `["Retail Taxonomy > Bakery > Cake > Cake", "Retail Taxonomy > Bakery > Cake > Cake > @variant > layer", "Retail Taxonomy > Bakery > Cake > Cake > @flavor > chocolate"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['chocolate', 'layer']:actual=['layer']`
- `core_mismatch:flavor:expected=[]:actual=['chocolate']`

**exact errors:**
- `mismatch:canonical_label:expected='Cake (Chocolate, Layer)':actual='Cake (Layer, Chocolate)'`
- `mismatch:variant:expected=['chocolate', 'layer']:actual=['layer']`
- `mismatch:flavor:expected=[]:actual=['chocolate']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Bakery > Cake > Cake', 'Retail Taxonomy > Bakery > Cake > Cake > @variant > chocolate', 'Retail Taxonomy > Bakery > Cake > Cake > @variant > layer']:actual=['Retail Taxonomy > Bakery > Cake > Cake', 'Retail Taxonomy > Bakery > Cake > Cake > @variant > layer', 'Retail Taxonomy > Bakery > Cake > Cake > @flavor > chocolate']`

---

## carrot_cake_with_cream_cheese_frosting
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Cake"` | `"Bakery > Cake"` |
| `product_identity` | `"Carrot Cake"` | `"Carrot Cake"` |
| `canonical_path` | `"Bakery > Cake > Carrot Cake"` | `"Bakery > Cake > Carrot Cake"` |
| `variant` * | `[]` | `["cream_cheese_frosting"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` * | `[]` | `["layer_cake"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Carrot Cake"` | `"Carrot Cake (Cream Cheese Frosting, Layer Cake)"` |
| `tree_paths` * | `["Retail Taxonomy > Bakery > Cake > Carrot Cake", "Retail Taxonomy > Bakery > Cake > Carrot Cake > @components > cream_cheese_frosting"]` | `["Retail Taxonomy > Bakery > Cake > Carrot Cake", "Retail Taxonomy > Bakery > Cake > Carrot Cake > @variant > cream_cheese_frosting", "Retail Taxonomy > Bakery > Cake > Carrot Cake > @form_texture_cut > layer_cake", "Retail Taxonomy > Bakery > Cake > Carrot Cake > @components > cream_cheese_frosting"]` |
| `components` * | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Cream Cheese Frosting", "processing_storage": [], "role": "topping", "variant": []}]` | `[{"claims": [], "flavor": [], "form_texture_cut": [], "identity": "Cream Cheese Frosting", "processing_storage": [], "role": "frosting", "variant": []}]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['cream_cheese_frosting']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['layer_cake']`

**exact errors:**
- `mismatch:canonical_label:expected='Carrot Cake':actual='Carrot Cake (Cream Cheese Frosting, Layer Cake)'`
- `mismatch:variant:expected=[]:actual=['cream_cheese_frosting']`
- `mismatch:form_texture_cut:expected=[]:actual=['layer_cake']`
- `mismatch:components:expected=[{'identity': 'Cream Cheese Frosting', 'role': 'topping', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]:actual=[{'identity': 'Cream Cheese Frosting', 'role': 'frosting', 'variant': [], 'flavor': [], 'form_texture_cut': [], 'processing_storage': [], 'claims': []}]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Bakery > Cake > Carrot Cake', 'Retail Taxonomy > Bakery > Cake > Carrot Cake > @components > cream_cheese_frosting']:actual=['Retail Taxonomy > Bakery > Cake > Carrot Cake', 'Retail Taxonomy > Bakery > Cake > Carrot Cake > @variant > cream_cheese_frosting', 'Retail Taxonomy > Bakery > Cake > Carrot Cake > @form_texture_cut > layer_cake', 'Retail Taxonomy > Bakery > Cake > Carrot Cake > @components > cream_cheese_frosting']`

---

## snack_cake_oatmeal_creme_pie
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` * | `"Snack > Snack Cakes"` | `"Bakery > Cake"` |
| `product_identity` * | `"Snack Cakes"` | `"Cake"` |
| `canonical_path` * | `"Snack > Snack Cakes > Snack Cakes"` | `"Bakery > Cake > Cake"` |
| `variant` * | `["oatmeal_creme_pie"]` | `["snack", "oatmeal_creme_pie"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["high_protein"]` |
| `canonical_label` * | `"Snack Cakes (Oatmeal Creme Pie)"` | `"Cake (Snack, Oatmeal Creme Pie, High Protein)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Snack Cakes > Snack Cakes", "Retail Taxonomy > Snack > Snack Cakes > Snack Cakes > @variant > oatmeal_creme_pie"]` | `["Retail Taxonomy > Bakery > Cake > Cake", "Retail Taxonomy > Bakery > Cake > Cake > @variant > snack", "Retail Taxonomy > Bakery > Cake > Cake > @variant > oatmeal_creme_pie", "Retail Taxonomy > Bakery > Cake > Cake > @claims > high_protein"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:category_path:expected='Snack > Snack Cakes':actual='Bakery > Cake'`
- `core_mismatch:product_identity:expected='Snack Cakes':actual='Cake'`
- `core_mismatch:canonical_path:expected='Snack > Snack Cakes > Snack Cakes':actual='Bakery > Cake > Cake'`
- `core_mismatch:variant:expected=['oatmeal_creme_pie']:actual=['snack', 'oatmeal_creme_pie']`
- `core_mismatch:claims:expected=[]:actual=['high_protein']`

**exact errors:**
- `mismatch:category_path:expected='Snack > Snack Cakes':actual='Bakery > Cake'`
- `mismatch:product_identity:expected='Snack Cakes':actual='Cake'`
- `mismatch:canonical_path:expected='Snack > Snack Cakes > Snack Cakes':actual='Bakery > Cake > Cake'`
- `mismatch:canonical_label:expected='Snack Cakes (Oatmeal Creme Pie)':actual='Cake (Snack, Oatmeal Creme Pie, High Protein)'`
- `mismatch:variant:expected=['oatmeal_creme_pie']:actual=['snack', 'oatmeal_creme_pie']`
- `mismatch:claims:expected=[]:actual=['high_protein']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Snack Cakes > Snack Cakes', 'Retail Taxonomy > Snack > Snack Cakes > Snack Cakes > @variant > oatmeal_creme_pie']:actual=['Retail Taxonomy > Bakery > Cake > Cake', 'Retail Taxonomy > Bakery > Cake > Cake > @variant > snack', 'Retail Taxonomy > Bakery > Cake > Cake > @variant > oatmeal_creme_pie', 'Retail Taxonomy > Bakery > Cake > Cake > @claims > high_protein']`

---

## angel_food_cake
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Cake"` | `"Bakery > Cake"` |
| `product_identity` | `"Angel Food Cake"` | `"Angel Food Cake"` |
| `canonical_path` | `"Bakery > Cake > Angel Food Cake"` | `"Bakery > Cake > Angel Food Cake"` |
| `variant` | `[]` | `[]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Angel Food Cake"` | `"Angel Food Cake"` |
| `tree_paths` | `["Retail Taxonomy > Bakery > Cake > Angel Food Cake"]` | `["Retail Taxonomy > Bakery > Cake > Angel Food Cake"]` |
| `components` | `[]` | `[]` |

---

## muffins_blueberry
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Muffins"` | `"Bakery > Muffins"` |
| `product_identity` | `"Muffins"` | `"Muffins"` |
| `canonical_path` | `"Bakery > Muffins > Muffins"` | `"Bakery > Muffins > Muffins"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["blueberry"]` | `["blueberry"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Muffins (Blueberry)"` | `"Muffins (Blueberry)"` |
| `tree_paths` | `["Retail Taxonomy > Bakery > Muffins > Muffins", "Retail Taxonomy > Bakery > Muffins > Muffins > @flavor > blueberry"]` | `["Retail Taxonomy > Bakery > Muffins > Muffins", "Retail Taxonomy > Bakery > Muffins > Muffins > @flavor > blueberry"]` |
| `components` | `[]` | `[]` |

---

## kind_dark_chocolate_nut_bar
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` | `"Granola Bars"` | `"Granola Bars"` |
| `canonical_path` | `"Snack > Bars > Granola Bars"` | `"Snack > Bars > Granola Bars"` |
| `variant` * | `["nuts_sea_salt"]` | `["nuts"]` |
| `flavor` | `["dark_chocolate"]` | `["dark_chocolate"]` |
| `form_texture_cut` * | `[]` | `["chewy"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["sea_salt"]` |
| `canonical_label` * | `"Granola Bars (Nuts Sea Salt, Dark Chocolate)"` | `"Granola Bars (Nuts, Dark Chocolate, Chewy, Sea Salt)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Granola Bars", "Retail Taxonomy > Snack > Bars > Granola Bars > @variant > nuts_sea_salt", "Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > dark_chocolate"]` | `["Retail Taxonomy > Snack > Bars > Granola Bars", "Retail Taxonomy > Snack > Bars > Granola Bars > @variant > nuts", "Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > dark_chocolate", "Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > chewy", "Retail Taxonomy > Snack > Bars > Granola Bars > @claims > sea_salt"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['nuts_sea_salt']:actual=['nuts']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['chewy']`
- `core_mismatch:claims:expected=[]:actual=['sea_salt']`

**exact errors:**
- `mismatch:canonical_label:expected='Granola Bars (Nuts Sea Salt, Dark Chocolate)':actual='Granola Bars (Nuts, Dark Chocolate, Chewy, Sea Salt)'`
- `mismatch:variant:expected=['nuts_sea_salt']:actual=['nuts']`
- `mismatch:form_texture_cut:expected=[]:actual=['chewy']`
- `mismatch:claims:expected=[]:actual=['sea_salt']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Granola Bars', 'Retail Taxonomy > Snack > Bars > Granola Bars > @variant > nuts_sea_salt', 'Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > dark_chocolate']:actual=['Retail Taxonomy > Snack > Bars > Granola Bars', 'Retail Taxonomy > Snack > Bars > Granola Bars > @variant > nuts', 'Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > dark_chocolate', 'Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > chewy', 'Retail Taxonomy > Snack > Bars > Granola Bars > @claims > sea_salt']`

---

## clif_bar_chocolate_chip
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` | `"Energy Bars"` | `"Energy Bars"` |
| `canonical_path` | `"Snack > Bars > Energy Bars"` | `"Snack > Bars > Energy Bars"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["chocolate_chip"]` | `["chocolate_chip"]` |
| `form_texture_cut` * | `[]` | `["chewy"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Energy Bars (Chocolate Chip)"` | `"Energy Bars (Chocolate Chip, Chewy)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Energy Bars", "Retail Taxonomy > Snack > Bars > Energy Bars > @flavor > chocolate_chip"]` | `["Retail Taxonomy > Snack > Bars > Energy Bars", "Retail Taxonomy > Snack > Bars > Energy Bars > @flavor > chocolate_chip", "Retail Taxonomy > Snack > Bars > Energy Bars > @form_texture_cut > chewy"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:form_texture_cut:expected=[]:actual=['chewy']`

**exact errors:**
- `mismatch:canonical_label:expected='Energy Bars (Chocolate Chip)':actual='Energy Bars (Chocolate Chip, Chewy)'`
- `mismatch:form_texture_cut:expected=[]:actual=['chewy']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Energy Bars', 'Retail Taxonomy > Snack > Bars > Energy Bars > @flavor > chocolate_chip']:actual=['Retail Taxonomy > Snack > Bars > Energy Bars', 'Retail Taxonomy > Snack > Bars > Energy Bars > @flavor > chocolate_chip', 'Retail Taxonomy > Snack > Bars > Energy Bars > @form_texture_cut > chewy']`

---

## rxbar_chocolate_sea_salt
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` | `"Protein Bars"` | `"Protein Bars"` |
| `canonical_path` | `"Snack > Bars > Protein Bars"` | `"Snack > Bars > Protein Bars"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["chocolate_sea_salt"]` | `["chocolate_sea_salt"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `["high_protein"]` | `["high_protein"]` |
| `canonical_label` | `"Protein Bars (Chocolate Sea Salt, High Protein)"` | `"Protein Bars (Chocolate Sea Salt, High Protein)"` |
| `tree_paths` | `["Retail Taxonomy > Snack > Bars > Protein Bars", "Retail Taxonomy > Snack > Bars > Protein Bars > @flavor > chocolate_sea_salt", "Retail Taxonomy > Snack > Bars > Protein Bars > @claims > high_protein"]` | `["Retail Taxonomy > Snack > Bars > Protein Bars", "Retail Taxonomy > Snack > Bars > Protein Bars > @flavor > chocolate_sea_salt", "Retail Taxonomy > Snack > Bars > Protein Bars > @claims > high_protein"]` |
| `components` | `[]` | `[]` |

---

## nature_valley_oats_honey_granola_bar
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` | `"Granola Bars"` | `"Granola Bars"` |
| `canonical_path` | `"Snack > Bars > Granola Bars"` | `"Snack > Bars > Granola Bars"` |
| `variant` * | `[]` | `["oats_honey"]` |
| `flavor` * | `["oats_honey"]` | `[]` |
| `form_texture_cut` | `["crunchy"]` | `["crunchy"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Granola Bars (Oats Honey, Crunchy)"` | `"Granola Bars (Oats Honey, Crunchy)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Granola Bars", "Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > oats_honey", "Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > crunchy"]` | `["Retail Taxonomy > Snack > Bars > Granola Bars", "Retail Taxonomy > Snack > Bars > Granola Bars > @variant > oats_honey", "Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > crunchy"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['oats_honey']`
- `core_mismatch:flavor:expected=['oats_honey']:actual=[]`

**exact errors:**
- `mismatch:variant:expected=[]:actual=['oats_honey']`
- `mismatch:flavor:expected=['oats_honey']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Granola Bars', 'Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > oats_honey', 'Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > crunchy']:actual=['Retail Taxonomy > Snack > Bars > Granola Bars', 'Retail Taxonomy > Snack > Bars > Granola Bars > @variant > oats_honey', 'Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > crunchy']`

---

## quaker_chewy_chocolate_chip_bar
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` | `"Granola Bars"` | `"Granola Bars"` |
| `canonical_path` | `"Snack > Bars > Granola Bars"` | `"Snack > Bars > Granola Bars"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["chocolate_chip"]` | `["chocolate_chip"]` |
| `form_texture_cut` | `["chewy"]` | `["chewy"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Granola Bars (Chocolate Chip, Chewy)"` | `"Granola Bars (Chocolate Chip, Chewy)"` |
| `tree_paths` | `["Retail Taxonomy > Snack > Bars > Granola Bars", "Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > chocolate_chip", "Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > chewy"]` | `["Retail Taxonomy > Snack > Bars > Granola Bars", "Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > chocolate_chip", "Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > chewy"]` |
| `components` | `[]` | `[]` |

---

## nutrigrain_strawberry_cereal_bar
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` * | `"Cereal Bars"` | `"Cereal Bar"` |
| `canonical_path` * | `"Snack > Bars > Cereal Bars"` | `"Snack > Bars > Cereal Bar"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["strawberry"]` | `["strawberry"]` |
| `form_texture_cut` * | `[]` | `["chewy"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Cereal Bars (Strawberry)"` | `"Cereal Bar (Strawberry, Chewy)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Cereal Bars", "Retail Taxonomy > Snack > Bars > Cereal Bars > @flavor > strawberry"]` | `["Retail Taxonomy > Snack > Bars > Cereal Bar", "Retail Taxonomy > Snack > Bars > Cereal Bar > @flavor > strawberry", "Retail Taxonomy > Snack > Bars > Cereal Bar > @form_texture_cut > chewy"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Cereal Bars':actual='Cereal Bar'`
- `core_mismatch:canonical_path:expected='Snack > Bars > Cereal Bars':actual='Snack > Bars > Cereal Bar'`
- `core_mismatch:form_texture_cut:expected=[]:actual=['chewy']`

**exact errors:**
- `mismatch:product_identity:expected='Cereal Bars':actual='Cereal Bar'`
- `mismatch:canonical_path:expected='Snack > Bars > Cereal Bars':actual='Snack > Bars > Cereal Bar'`
- `mismatch:canonical_label:expected='Cereal Bars (Strawberry)':actual='Cereal Bar (Strawberry, Chewy)'`
- `mismatch:form_texture_cut:expected=[]:actual=['chewy']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Cereal Bars', 'Retail Taxonomy > Snack > Bars > Cereal Bars > @flavor > strawberry']:actual=['Retail Taxonomy > Snack > Bars > Cereal Bar', 'Retail Taxonomy > Snack > Bars > Cereal Bar > @flavor > strawberry', 'Retail Taxonomy > Snack > Bars > Cereal Bar > @form_texture_cut > chewy']`

---

## kelloggs_pop_tart_toaster_pastry
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Bakery > Toaster Pastries"` | `"Bakery > Toaster Pastries"` |
| `product_identity` | `"Toaster Pastries"` | `"Toaster Pastries"` |
| `canonical_path` | `"Bakery > Toaster Pastries > Toaster Pastries"` | `"Bakery > Toaster Pastries > Toaster Pastries"` |
| `variant` | `["frosted"]` | `["frosted"]` |
| `flavor` | `["strawberry"]` | `["strawberry"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Toaster Pastries (Frosted, Strawberry)"` | `"Toaster Pastries (Frosted, Strawberry)"` |
| `tree_paths` | `["Retail Taxonomy > Bakery > Toaster Pastries > Toaster Pastries", "Retail Taxonomy > Bakery > Toaster Pastries > Toaster Pastries > @variant > frosted", "Retail Taxonomy > Bakery > Toaster Pastries > Toaster Pastries > @flavor > strawberry"]` | `["Retail Taxonomy > Bakery > Toaster Pastries > Toaster Pastries", "Retail Taxonomy > Bakery > Toaster Pastries > Toaster Pastries > @variant > frosted", "Retail Taxonomy > Bakery > Toaster Pastries > Toaster Pastries > @flavor > strawberry"]` |
| `components` | `[]` | `[]` |

---

## larabar_apple_pie
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` * | `"Fruit Bars"` | `"Fruit & Nut Bar"` |
| `canonical_path` * | `"Snack > Bars > Fruit Bars"` | `"Snack > Bars > Fruit & Nut Bar"` |
| `variant` | `[]` | `[]` |
| `flavor` * | `["apple_pie"]` | `["apple_cinnamon"]` |
| `form_texture_cut` * | `[]` | `["chewy"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["gluten_free", "dairy_free", "vegan", "non_gmo", "no_added_sugar"]` |
| `canonical_label` * | `"Fruit Bars (Apple Pie)"` | `"Fruit & Nut Bar (Apple Cinnamon, Chewy, Gluten Free, Dairy Free, Vegan, Non Gmo, No Added Sugar)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Fruit Bars", "Retail Taxonomy > Snack > Bars > Fruit Bars > @flavor > apple_pie"]` | `["Retail Taxonomy > Snack > Bars > Fruit & Nut Bar", "Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @flavor > apple_cinnamon", "Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @form_texture_cut > chewy", "Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @claims > gluten_free", "Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @claims > dairy_free", "Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @claims > vegan", "Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @claims > non_gmo", "Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @claims > no_added_sugar"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Fruit Bars':actual='Fruit & Nut Bar'`
- `core_mismatch:canonical_path:expected='Snack > Bars > Fruit Bars':actual='Snack > Bars > Fruit & Nut Bar'`
- `core_mismatch:flavor:expected=['apple_pie']:actual=['apple_cinnamon']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['chewy']`
- `core_mismatch:claims:expected=[]:actual=['gluten_free', 'dairy_free', 'vegan', 'non_gmo', 'no_added_sugar']`

**exact errors:**
- `mismatch:product_identity:expected='Fruit Bars':actual='Fruit & Nut Bar'`
- `mismatch:canonical_path:expected='Snack > Bars > Fruit Bars':actual='Snack > Bars > Fruit & Nut Bar'`
- `mismatch:canonical_label:expected='Fruit Bars (Apple Pie)':actual='Fruit & Nut Bar (Apple Cinnamon, Chewy, Gluten Free, Dairy Free, Vegan, Non Gmo, No Added Sugar)'`
- `mismatch:flavor:expected=['apple_pie']:actual=['apple_cinnamon']`
- `mismatch:form_texture_cut:expected=[]:actual=['chewy']`
- `mismatch:claims:expected=[]:actual=['gluten_free', 'dairy_free', 'vegan', 'non_gmo', 'no_added_sugar']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Fruit Bars', 'Retail Taxonomy > Snack > Bars > Fruit Bars > @flavor > apple_pie']:actual=['Retail Taxonomy > Snack > Bars > Fruit & Nut Bar', 'Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @flavor > apple_cinnamon', 'Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @form_texture_cut > chewy', 'Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @claims > gluten_free', 'Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @claims > dairy_free', 'Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @claims > vegan', 'Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @claims > non_gmo', 'Retail Taxonomy > Snack > Bars > Fruit & Nut Bar > @claims > no_added_sugar']`

---

## perfect_bar_peanut_butter
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` | `"Protein Bars"` | `"Protein Bars"` |
| `canonical_path` | `"Snack > Bars > Protein Bars"` | `"Snack > Bars > Protein Bars"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["peanut_butter"]` | `["peanut_butter"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` * | `[]` | `["refrigerated"]` |
| `claims` | `["high_protein"]` | `["high_protein"]` |
| `canonical_label` * | `"Protein Bars (Peanut Butter, High Protein)"` | `"Protein Bars (Peanut Butter, Refrigerated, High Protein)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Protein Bars", "Retail Taxonomy > Snack > Bars > Protein Bars > @flavor > peanut_butter", "Retail Taxonomy > Snack > Bars > Protein Bars > @claims > high_protein"]` | `["Retail Taxonomy > Snack > Bars > Protein Bars", "Retail Taxonomy > Snack > Bars > Protein Bars > @flavor > peanut_butter", "Retail Taxonomy > Snack > Bars > Protein Bars > @processing_storage > refrigerated", "Retail Taxonomy > Snack > Bars > Protein Bars > @claims > high_protein"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:processing_storage:expected=[]:actual=['refrigerated']`

**exact errors:**
- `mismatch:canonical_label:expected='Protein Bars (Peanut Butter, High Protein)':actual='Protein Bars (Peanut Butter, Refrigerated, High Protein)'`
- `mismatch:processing_storage:expected=[]:actual=['refrigerated']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Protein Bars', 'Retail Taxonomy > Snack > Bars > Protein Bars > @flavor > peanut_butter', 'Retail Taxonomy > Snack > Bars > Protein Bars > @claims > high_protein']:actual=['Retail Taxonomy > Snack > Bars > Protein Bars', 'Retail Taxonomy > Snack > Bars > Protein Bars > @flavor > peanut_butter', 'Retail Taxonomy > Snack > Bars > Protein Bars > @processing_storage > refrigerated', 'Retail Taxonomy > Snack > Bars > Protein Bars > @claims > high_protein']`

---

## quest_chocolate_chip_cookie_dough_bar
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` | `"Protein Bars"` | `"Protein Bars"` |
| `canonical_path` | `"Snack > Bars > Protein Bars"` | `"Snack > Bars > Protein Bars"` |
| `variant` * | `[]` | `["chocolate_chip_cookie_dough"]` |
| `flavor` | `["chocolate_chip_cookie_dough"]` | `["chocolate_chip_cookie_dough"]` |
| `form_texture_cut` * | `[]` | `["chewy"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `["high_protein"]` | `["high_protein"]` |
| `canonical_label` * | `"Protein Bars (Chocolate Chip Cookie Dough, High Protein)"` | `"Protein Bars (Chocolate Chip Cookie Dough, Chocolate Chip Cookie Dough, Chewy, High Protein)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Protein Bars", "Retail Taxonomy > Snack > Bars > Protein Bars > @flavor > chocolate_chip_cookie_dough", "Retail Taxonomy > Snack > Bars > Protein Bars > @claims > high_protein"]` | `["Retail Taxonomy > Snack > Bars > Protein Bars", "Retail Taxonomy > Snack > Bars > Protein Bars > @variant > chocolate_chip_cookie_dough", "Retail Taxonomy > Snack > Bars > Protein Bars > @flavor > chocolate_chip_cookie_dough", "Retail Taxonomy > Snack > Bars > Protein Bars > @form_texture_cut > chewy", "Retail Taxonomy > Snack > Bars > Protein Bars > @claims > high_protein"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['chocolate_chip_cookie_dough']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['chewy']`

**exact errors:**
- `mismatch:canonical_label:expected='Protein Bars (Chocolate Chip Cookie Dough, High Protein)':actual='Protein Bars (Chocolate Chip Cookie Dough, Chocolate Chip Cookie Dough, Chewy, High Protein)'`
- `mismatch:variant:expected=[]:actual=['chocolate_chip_cookie_dough']`
- `mismatch:form_texture_cut:expected=[]:actual=['chewy']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Protein Bars', 'Retail Taxonomy > Snack > Bars > Protein Bars > @flavor > chocolate_chip_cookie_dough', 'Retail Taxonomy > Snack > Bars > Protein Bars > @claims > high_protein']:actual=['Retail Taxonomy > Snack > Bars > Protein Bars', 'Retail Taxonomy > Snack > Bars > Protein Bars > @variant > chocolate_chip_cookie_dough', 'Retail Taxonomy > Snack > Bars > Protein Bars > @flavor > chocolate_chip_cookie_dough', 'Retail Taxonomy > Snack > Bars > Protein Bars > @form_texture_cut > chewy', 'Retail Taxonomy > Snack > Bars > Protein Bars > @claims > high_protein']`

---

## annies_bunny_grahams_chocolate_chip
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` | `"Granola Bars"` | `"Granola Bars"` |
| `canonical_path` | `"Snack > Bars > Granola Bars"` | `"Snack > Bars > Granola Bars"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["chocolate_chip"]` | `["chocolate_chip"]` |
| `form_texture_cut` | `["chewy"]` | `["chewy"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["organic"]` | `[]` |
| `canonical_label` * | `"Granola Bars (Chocolate Chip, Chewy, Organic)"` | `"Granola Bars (Chocolate Chip, Chewy)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Granola Bars", "Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > chocolate_chip", "Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > chewy", "Retail Taxonomy > Snack > Bars > Granola Bars > @claims > organic"]` | `["Retail Taxonomy > Snack > Bars > Granola Bars", "Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > chocolate_chip", "Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > chewy"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:claims:expected=['organic']:actual=[]`

**exact errors:**
- `mismatch:canonical_label:expected='Granola Bars (Chocolate Chip, Chewy, Organic)':actual='Granola Bars (Chocolate Chip, Chewy)'`
- `mismatch:claims:expected=['organic']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Granola Bars', 'Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > chocolate_chip', 'Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > chewy', 'Retail Taxonomy > Snack > Bars > Granola Bars > @claims > organic']:actual=['Retail Taxonomy > Snack > Bars > Granola Bars', 'Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > chocolate_chip', 'Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > chewy']`

---

## kind_kids_chocolate_chip_bar
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` * | `"Kids Bars"` | `"Granola Bars"` |
| `canonical_path` * | `"Snack > Bars > Kids Bars"` | `"Snack > Bars > Granola Bars"` |
| `variant` * | `[]` | `["kids"]` |
| `flavor` | `["chocolate_chip"]` | `["chocolate_chip"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Kids Bars (Chocolate Chip)"` | `"Granola Bars (Kids, Chocolate Chip)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Kids Bars", "Retail Taxonomy > Snack > Bars > Kids Bars > @flavor > chocolate_chip"]` | `["Retail Taxonomy > Snack > Bars > Granola Bars", "Retail Taxonomy > Snack > Bars > Granola Bars > @variant > kids", "Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > chocolate_chip"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Kids Bars':actual='Granola Bars'`
- `core_mismatch:canonical_path:expected='Snack > Bars > Kids Bars':actual='Snack > Bars > Granola Bars'`
- `core_mismatch:variant:expected=[]:actual=['kids']`

**exact errors:**
- `mismatch:product_identity:expected='Kids Bars':actual='Granola Bars'`
- `mismatch:canonical_path:expected='Snack > Bars > Kids Bars':actual='Snack > Bars > Granola Bars'`
- `mismatch:canonical_label:expected='Kids Bars (Chocolate Chip)':actual='Granola Bars (Kids, Chocolate Chip)'`
- `mismatch:variant:expected=[]:actual=['kids']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Kids Bars', 'Retail Taxonomy > Snack > Bars > Kids Bars > @flavor > chocolate_chip']:actual=['Retail Taxonomy > Snack > Bars > Granola Bars', 'Retail Taxonomy > Snack > Bars > Granola Bars > @variant > kids', 'Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > chocolate_chip']`

---

## zbar_oatmeal_chocolate_chip
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` * | `"Kids Bars"` | `"Granola Bars"` |
| `canonical_path` * | `"Snack > Bars > Kids Bars"` | `"Snack > Bars > Granola Bars"` |
| `variant` * | `[]` | `["oatmeal_chocolate_chip"]` |
| `flavor` * | `["oatmeal_chocolate_chip"]` | `["chocolate_chip"]` |
| `form_texture_cut` * | `[]` | `["chewy"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Kids Bars (Oatmeal Chocolate Chip)"` | `"Granola Bars (Oatmeal Chocolate Chip, Chocolate Chip, Chewy)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Kids Bars", "Retail Taxonomy > Snack > Bars > Kids Bars > @flavor > oatmeal_chocolate_chip"]` | `["Retail Taxonomy > Snack > Bars > Granola Bars", "Retail Taxonomy > Snack > Bars > Granola Bars > @variant > oatmeal_chocolate_chip", "Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > chocolate_chip", "Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > chewy"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Kids Bars':actual='Granola Bars'`
- `core_mismatch:canonical_path:expected='Snack > Bars > Kids Bars':actual='Snack > Bars > Granola Bars'`
- `core_mismatch:variant:expected=[]:actual=['oatmeal_chocolate_chip']`
- `core_mismatch:flavor:expected=['oatmeal_chocolate_chip']:actual=['chocolate_chip']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['chewy']`

**exact errors:**
- `mismatch:product_identity:expected='Kids Bars':actual='Granola Bars'`
- `mismatch:canonical_path:expected='Snack > Bars > Kids Bars':actual='Snack > Bars > Granola Bars'`
- `mismatch:canonical_label:expected='Kids Bars (Oatmeal Chocolate Chip)':actual='Granola Bars (Oatmeal Chocolate Chip, Chocolate Chip, Chewy)'`
- `mismatch:variant:expected=[]:actual=['oatmeal_chocolate_chip']`
- `mismatch:flavor:expected=['oatmeal_chocolate_chip']:actual=['chocolate_chip']`
- `mismatch:form_texture_cut:expected=[]:actual=['chewy']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Kids Bars', 'Retail Taxonomy > Snack > Bars > Kids Bars > @flavor > oatmeal_chocolate_chip']:actual=['Retail Taxonomy > Snack > Bars > Granola Bars', 'Retail Taxonomy > Snack > Bars > Granola Bars > @variant > oatmeal_chocolate_chip', 'Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > chocolate_chip', 'Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > chewy']`

---

## luna_lemon_zest_bar
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` | `"Granola Bars"` | `"Granola Bars"` |
| `canonical_path` | `"Snack > Bars > Granola Bars"` | `"Snack > Bars > Granola Bars"` |
| `variant` * | `[]` | `["whole_nutrition"]` |
| `flavor` | `["lemon_zest"]` | `["lemon_zest"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Granola Bars (Lemon Zest)"` | `"Granola Bars (Whole Nutrition, Lemon Zest)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Granola Bars", "Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > lemon_zest"]` | `["Retail Taxonomy > Snack > Bars > Granola Bars", "Retail Taxonomy > Snack > Bars > Granola Bars > @variant > whole_nutrition", "Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > lemon_zest"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=[]:actual=['whole_nutrition']`

**exact errors:**
- `mismatch:canonical_label:expected='Granola Bars (Lemon Zest)':actual='Granola Bars (Whole Nutrition, Lemon Zest)'`
- `mismatch:variant:expected=[]:actual=['whole_nutrition']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Granola Bars', 'Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > lemon_zest']:actual=['Retail Taxonomy > Snack > Bars > Granola Bars', 'Retail Taxonomy > Snack > Bars > Granola Bars > @variant > whole_nutrition', 'Retail Taxonomy > Snack > Bars > Granola Bars > @flavor > lemon_zest']`

---

## met_rx_meal_replacement_bar
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` * | `"Meal Replacement Bars"` | `"Meal Replacement Bar"` |
| `canonical_path` * | `"Snack > Bars > Meal Replacement Bars"` | `"Snack > Bars > Meal Replacement Bar"` |
| `variant` * | `[]` | `["chocolate_fudge"]` |
| `flavor` * | `["chocolate_fudge"]` | `[]` |
| `form_texture_cut` * | `[]` | `["chewy"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["high_protein"]` | `["high_protein", "meal_replacement"]` |
| `canonical_label` * | `"Meal Replacement Bars (Chocolate Fudge, High Protein)"` | `"Meal Replacement Bar (Chocolate Fudge, Chewy, High Protein, Meal Replacement)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Meal Replacement Bars", "Retail Taxonomy > Snack > Bars > Meal Replacement Bars > @flavor > chocolate_fudge", "Retail Taxonomy > Snack > Bars > Meal Replacement Bars > @claims > high_protein"]` | `["Retail Taxonomy > Snack > Bars > Meal Replacement Bar", "Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @variant > chocolate_fudge", "Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @form_texture_cut > chewy", "Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @claims > high_protein", "Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @claims > meal_replacement"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Meal Replacement Bars':actual='Meal Replacement Bar'`
- `core_mismatch:canonical_path:expected='Snack > Bars > Meal Replacement Bars':actual='Snack > Bars > Meal Replacement Bar'`
- `core_mismatch:variant:expected=[]:actual=['chocolate_fudge']`
- `core_mismatch:flavor:expected=['chocolate_fudge']:actual=[]`
- `core_mismatch:form_texture_cut:expected=[]:actual=['chewy']`
- `core_mismatch:claims:expected=['high_protein']:actual=['high_protein', 'meal_replacement']`

**exact errors:**
- `mismatch:product_identity:expected='Meal Replacement Bars':actual='Meal Replacement Bar'`
- `mismatch:canonical_path:expected='Snack > Bars > Meal Replacement Bars':actual='Snack > Bars > Meal Replacement Bar'`
- `mismatch:canonical_label:expected='Meal Replacement Bars (Chocolate Fudge, High Protein)':actual='Meal Replacement Bar (Chocolate Fudge, Chewy, High Protein, Meal Replacement)'`
- `mismatch:variant:expected=[]:actual=['chocolate_fudge']`
- `mismatch:flavor:expected=['chocolate_fudge']:actual=[]`
- `mismatch:form_texture_cut:expected=[]:actual=['chewy']`
- `mismatch:claims:expected=['high_protein']:actual=['high_protein', 'meal_replacement']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Meal Replacement Bars', 'Retail Taxonomy > Snack > Bars > Meal Replacement Bars > @flavor > chocolate_fudge', 'Retail Taxonomy > Snack > Bars > Meal Replacement Bars > @claims > high_protein']:actual=['Retail Taxonomy > Snack > Bars > Meal Replacement Bar', 'Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @variant > chocolate_fudge', 'Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @form_texture_cut > chewy', 'Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @claims > high_protein', 'Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @claims > meal_replacement']`

---

## special_k_protein_bar_chocolatey_chip
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` * | `"Protein Bars"` | `"Meal Replacement Bar"` |
| `canonical_path` * | `"Snack > Bars > Protein Bars"` | `"Snack > Bars > Meal Replacement Bar"` |
| `variant` | `[]` | `[]` |
| `flavor` * | `["chocolatey_chip"]` | `["chocolate", "chocolate_chip"]` |
| `form_texture_cut` * | `[]` | `["chewy"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `["high_protein"]` | `["high_protein"]` |
| `canonical_label` * | `"Protein Bars (Chocolatey Chip, High Protein)"` | `"Meal Replacement Bar (Chocolate, Chocolate Chip, Chewy, High Protein)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Protein Bars", "Retail Taxonomy > Snack > Bars > Protein Bars > @flavor > chocolatey_chip", "Retail Taxonomy > Snack > Bars > Protein Bars > @claims > high_protein"]` | `["Retail Taxonomy > Snack > Bars > Meal Replacement Bar", "Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @flavor > chocolate", "Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @flavor > chocolate_chip", "Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @form_texture_cut > chewy", "Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @claims > high_protein"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Protein Bars':actual='Meal Replacement Bar'`
- `core_mismatch:canonical_path:expected='Snack > Bars > Protein Bars':actual='Snack > Bars > Meal Replacement Bar'`
- `core_mismatch:flavor:expected=['chocolatey_chip']:actual=['chocolate', 'chocolate_chip']`
- `core_mismatch:form_texture_cut:expected=[]:actual=['chewy']`

**exact errors:**
- `mismatch:product_identity:expected='Protein Bars':actual='Meal Replacement Bar'`
- `mismatch:canonical_path:expected='Snack > Bars > Protein Bars':actual='Snack > Bars > Meal Replacement Bar'`
- `mismatch:canonical_label:expected='Protein Bars (Chocolatey Chip, High Protein)':actual='Meal Replacement Bar (Chocolate, Chocolate Chip, Chewy, High Protein)'`
- `mismatch:flavor:expected=['chocolatey_chip']:actual=['chocolate', 'chocolate_chip']`
- `mismatch:form_texture_cut:expected=[]:actual=['chewy']`
- `mismatch:mint_required:expected=True:actual=False`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Protein Bars', 'Retail Taxonomy > Snack > Bars > Protein Bars > @flavor > chocolatey_chip', 'Retail Taxonomy > Snack > Bars > Protein Bars > @claims > high_protein']:actual=['Retail Taxonomy > Snack > Bars > Meal Replacement Bar', 'Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @flavor > chocolate', 'Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @flavor > chocolate_chip', 'Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @form_texture_cut > chewy', 'Retail Taxonomy > Snack > Bars > Meal Replacement Bar > @claims > high_protein']`

---

## snickers_almond_candy_bar
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Chocolate Candy"` | `"Snack > Chocolate Candy"` |
| `product_identity` | `"Candy Bar"` | `"Candy Bar"` |
| `canonical_path` | `"Snack > Chocolate Candy > Candy Bar"` | `"Snack > Chocolate Candy > Candy Bar"` |
| `variant` * | `["almond"]` | `[]` |
| `flavor` * | `[]` | `["chocolate", "almond"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Candy Bar (Almond)"` | `"Candy Bar (Chocolate, Almond)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Chocolate Candy > Candy Bar", "Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @variant > almond"]` | `["Retail Taxonomy > Snack > Chocolate Candy > Candy Bar", "Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @flavor > chocolate", "Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @flavor > almond"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['almond']:actual=[]`
- `core_mismatch:flavor:expected=[]:actual=['chocolate', 'almond']`

**exact errors:**
- `mismatch:canonical_label:expected='Candy Bar (Almond)':actual='Candy Bar (Chocolate, Almond)'`
- `mismatch:variant:expected=['almond']:actual=[]`
- `mismatch:flavor:expected=[]:actual=['chocolate', 'almond']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Chocolate Candy > Candy Bar', 'Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @variant > almond']:actual=['Retail Taxonomy > Snack > Chocolate Candy > Candy Bar', 'Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @flavor > chocolate', 'Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @flavor > almond']`

---

## twix_caramel_cookie_bar
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Chocolate Candy"` | `"Snack > Chocolate Candy"` |
| `product_identity` | `"Candy Bar"` | `"Candy Bar"` |
| `canonical_path` | `"Snack > Chocolate Candy > Candy Bar"` | `"Snack > Chocolate Candy > Candy Bar"` |
| `variant` * | `["caramel_cookie"]` | `["cookie"]` |
| `flavor` * | `[]` | `["chocolate", "caramel"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Candy Bar (Caramel Cookie)"` | `"Candy Bar (Cookie, Chocolate, Caramel)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Chocolate Candy > Candy Bar", "Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @variant > caramel_cookie"]` | `["Retail Taxonomy > Snack > Chocolate Candy > Candy Bar", "Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @variant > cookie", "Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @flavor > chocolate", "Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @flavor > caramel"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['caramel_cookie']:actual=['cookie']`
- `core_mismatch:flavor:expected=[]:actual=['chocolate', 'caramel']`

**exact errors:**
- `mismatch:canonical_label:expected='Candy Bar (Caramel Cookie)':actual='Candy Bar (Cookie, Chocolate, Caramel)'`
- `mismatch:variant:expected=['caramel_cookie']:actual=['cookie']`
- `mismatch:flavor:expected=[]:actual=['chocolate', 'caramel']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Chocolate Candy > Candy Bar', 'Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @variant > caramel_cookie']:actual=['Retail Taxonomy > Snack > Chocolate Candy > Candy Bar', 'Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @variant > cookie', 'Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @flavor > chocolate', 'Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @flavor > caramel']`

---

## kit_kat_wafer_bar
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Chocolate Candy"` | `"Snack > Chocolate Candy"` |
| `product_identity` | `"Candy Bar"` | `"Candy Bar"` |
| `canonical_path` | `"Snack > Chocolate Candy > Candy Bar"` | `"Snack > Chocolate Candy > Candy Bar"` |
| `variant` | `["wafer"]` | `["wafer"]` |
| `flavor` * | `[]` | `["chocolate"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Candy Bar (Wafer)"` | `"Candy Bar (Wafer, Chocolate)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Chocolate Candy > Candy Bar", "Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @variant > wafer"]` | `["Retail Taxonomy > Snack > Chocolate Candy > Candy Bar", "Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @variant > wafer", "Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @flavor > chocolate"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:flavor:expected=[]:actual=['chocolate']`

**exact errors:**
- `mismatch:canonical_label:expected='Candy Bar (Wafer)':actual='Candy Bar (Wafer, Chocolate)'`
- `mismatch:flavor:expected=[]:actual=['chocolate']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Chocolate Candy > Candy Bar', 'Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @variant > wafer']:actual=['Retail Taxonomy > Snack > Chocolate Candy > Candy Bar', 'Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @variant > wafer', 'Retail Taxonomy > Snack > Chocolate Candy > Candy Bar > @flavor > chocolate']`

---

## oatmeal_breakfast_bar
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` * | `"Breakfast Bars"` | `"Granola Bars"` |
| `canonical_path` * | `"Snack > Bars > Breakfast Bars"` | `"Snack > Bars > Granola Bars"` |
| `variant` * | `[]` | `["brown_sugar_cinnamon"]` |
| `flavor` * | `["brown_sugar_cinnamon"]` | `[]` |
| `form_texture_cut` * | `[]` | `["chewy"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Breakfast Bars (Brown Sugar Cinnamon)"` | `"Granola Bars (Brown Sugar Cinnamon, Chewy)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Breakfast Bars", "Retail Taxonomy > Snack > Bars > Breakfast Bars > @flavor > brown_sugar_cinnamon"]` | `["Retail Taxonomy > Snack > Bars > Granola Bars", "Retail Taxonomy > Snack > Bars > Granola Bars > @variant > brown_sugar_cinnamon", "Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > chewy"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Breakfast Bars':actual='Granola Bars'`
- `core_mismatch:canonical_path:expected='Snack > Bars > Breakfast Bars':actual='Snack > Bars > Granola Bars'`
- `core_mismatch:variant:expected=[]:actual=['brown_sugar_cinnamon']`
- `core_mismatch:flavor:expected=['brown_sugar_cinnamon']:actual=[]`
- `core_mismatch:form_texture_cut:expected=[]:actual=['chewy']`

**exact errors:**
- `mismatch:product_identity:expected='Breakfast Bars':actual='Granola Bars'`
- `mismatch:canonical_path:expected='Snack > Bars > Breakfast Bars':actual='Snack > Bars > Granola Bars'`
- `mismatch:canonical_label:expected='Breakfast Bars (Brown Sugar Cinnamon)':actual='Granola Bars (Brown Sugar Cinnamon, Chewy)'`
- `mismatch:variant:expected=[]:actual=['brown_sugar_cinnamon']`
- `mismatch:flavor:expected=['brown_sugar_cinnamon']:actual=[]`
- `mismatch:form_texture_cut:expected=[]:actual=['chewy']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Breakfast Bars', 'Retail Taxonomy > Snack > Bars > Breakfast Bars > @flavor > brown_sugar_cinnamon']:actual=['Retail Taxonomy > Snack > Bars > Granola Bars', 'Retail Taxonomy > Snack > Bars > Granola Bars > @variant > brown_sugar_cinnamon', 'Retail Taxonomy > Snack > Bars > Granola Bars > @form_texture_cut > chewy']`

---

## fruit_bar_strawberry_real_fruit
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Bars"` | `"Snack > Bars"` |
| `product_identity` | `"Fruit Bars"` | `"Fruit Bars"` |
| `canonical_path` | `"Snack > Bars > Fruit Bars"` | `"Snack > Bars > Fruit Bars"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["strawberry"]` | `["strawberry"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["real_fruit"]` |
| `canonical_label` * | `"Fruit Bars (Strawberry)"` | `"Fruit Bars (Strawberry, Real Fruit)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Bars > Fruit Bars", "Retail Taxonomy > Snack > Bars > Fruit Bars > @flavor > strawberry"]` | `["Retail Taxonomy > Snack > Bars > Fruit Bars", "Retail Taxonomy > Snack > Bars > Fruit Bars > @flavor > strawberry", "Retail Taxonomy > Snack > Bars > Fruit Bars > @claims > real_fruit"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:claims:expected=[]:actual=['real_fruit']`

**exact errors:**
- `mismatch:canonical_label:expected='Fruit Bars (Strawberry)':actual='Fruit Bars (Strawberry, Real Fruit)'`
- `mismatch:claims:expected=[]:actual=['real_fruit']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Bars > Fruit Bars', 'Retail Taxonomy > Snack > Bars > Fruit Bars > @flavor > strawberry']:actual=['Retail Taxonomy > Snack > Bars > Fruit Bars', 'Retail Taxonomy > Snack > Bars > Fruit Bars > @flavor > strawberry', 'Retail Taxonomy > Snack > Bars > Fruit Bars > @claims > real_fruit']`

---

## nature_valley_oats_honey_granola
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Granola"` | `"Snack > Granola"` |
| `product_identity` | `"Granola"` | `"Granola"` |
| `canonical_path` | `"Snack > Granola > Granola"` | `"Snack > Granola > Granola"` |
| `variant` | `[]` | `[]` |
| `flavor` * | `["oats_honey"]` | `["honey"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Granola (Oats Honey)"` | `"Granola (Honey)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @flavor > oats_honey"]` | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @flavor > honey"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:flavor:expected=['oats_honey']:actual=['honey']`

**exact errors:**
- `mismatch:canonical_label:expected='Granola (Oats Honey)':actual='Granola (Honey)'`
- `mismatch:flavor:expected=['oats_honey']:actual=['honey']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Granola > Granola', 'Retail Taxonomy > Snack > Granola > Granola > @flavor > oats_honey']:actual=['Retail Taxonomy > Snack > Granola > Granola', 'Retail Taxonomy > Snack > Granola > Granola > @flavor > honey']`

---

## kind_dark_chocolate_granola
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Granola"` | `"Snack > Granola"` |
| `product_identity` | `"Granola"` | `"Granola"` |
| `canonical_path` | `"Snack > Granola > Granola"` | `"Snack > Granola > Granola"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["dark_chocolate"]` | `["dark_chocolate"]` |
| `form_texture_cut` | `["clusters"]` | `["clusters"]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Granola (Dark Chocolate, Clusters)"` | `"Granola (Dark Chocolate, Clusters)"` |
| `tree_paths` | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @flavor > dark_chocolate", "Retail Taxonomy > Snack > Granola > Granola > @form_texture_cut > clusters"]` | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @flavor > dark_chocolate", "Retail Taxonomy > Snack > Granola > Granola > @form_texture_cut > clusters"]` |
| `components` | `[]` | `[]` |

---

## bear_naked_vanilla_almond_granola
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Granola"` | `"Snack > Granola"` |
| `product_identity` | `"Granola"` | `"Granola"` |
| `canonical_path` | `"Snack > Granola > Granola"` | `"Snack > Granola > Granola"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["vanilla_almond"]` | `["vanilla_almond"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Granola (Vanilla Almond)"` | `"Granola (Vanilla Almond)"` |
| `tree_paths` | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @flavor > vanilla_almond"]` | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @flavor > vanilla_almond"]` |
| `components` | `[]` | `[]` |

---

## purely_elizabeth_pumpkin_fig_granola
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Granola"` | `"Snack > Granola"` |
| `product_identity` | `"Granola"` | `"Granola"` |
| `canonical_path` | `"Snack > Granola > Granola"` | `"Snack > Granola > Granola"` |
| `variant` | `["ancient_grain"]` | `["ancient_grain"]` |
| `flavor` * | `["pumpkin_fig"]` | `["pumpkin", "fig"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Granola (Ancient Grain, Pumpkin Fig)"` | `"Granola (Ancient Grain, Pumpkin, Fig)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @variant > ancient_grain", "Retail Taxonomy > Snack > Granola > Granola > @flavor > pumpkin_fig"]` | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @variant > ancient_grain", "Retail Taxonomy > Snack > Granola > Granola > @flavor > pumpkin", "Retail Taxonomy > Snack > Granola > Granola > @flavor > fig"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:flavor:expected=['pumpkin_fig']:actual=['pumpkin', 'fig']`

**exact errors:**
- `mismatch:canonical_label:expected='Granola (Ancient Grain, Pumpkin Fig)':actual='Granola (Ancient Grain, Pumpkin, Fig)'`
- `mismatch:flavor:expected=['pumpkin_fig']:actual=['pumpkin', 'fig']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Granola > Granola', 'Retail Taxonomy > Snack > Granola > Granola > @variant > ancient_grain', 'Retail Taxonomy > Snack > Granola > Granola > @flavor > pumpkin_fig']:actual=['Retail Taxonomy > Snack > Granola > Granola', 'Retail Taxonomy > Snack > Granola > Granola > @variant > ancient_grain', 'Retail Taxonomy > Snack > Granola > Granola > @flavor > pumpkin', 'Retail Taxonomy > Snack > Granola > Granola > @flavor > fig']`

---

## granola_paleo_blueberry
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Granola"` | `"Snack > Granola"` |
| `product_identity` | `"Granola"` | `"Granola"` |
| `canonical_path` | `"Snack > Granola > Granola"` | `"Snack > Granola > Granola"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["blueberry"]` | `["blueberry"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `["paleo"]` | `["paleo"]` |
| `canonical_label` | `"Granola (Blueberry, Paleo)"` | `"Granola (Blueberry, Paleo)"` |
| `tree_paths` | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @flavor > blueberry", "Retail Taxonomy > Snack > Granola > Granola > @claims > paleo"]` | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @flavor > blueberry", "Retail Taxonomy > Snack > Granola > Granola > @claims > paleo"]` |
| `components` | `[]` | `[]` |

---

## granola_keto_cinnamon
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Granola"` | `"Snack > Granola"` |
| `product_identity` | `"Granola"` | `"Granola"` |
| `canonical_path` | `"Snack > Granola > Granola"` | `"Snack > Granola > Granola"` |
| `variant` | `["grain_free"]` | `["grain_free"]` |
| `flavor` | `["cinnamon"]` | `["cinnamon"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["keto"]` | `["keto", "grain_free"]` |
| `canonical_label` * | `"Granola (Grain Free, Cinnamon, Keto)"` | `"Granola (Grain Free, Cinnamon, Keto, Grain Free)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @variant > grain_free", "Retail Taxonomy > Snack > Granola > Granola > @flavor > cinnamon", "Retail Taxonomy > Snack > Granola > Granola > @claims > keto"]` | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @variant > grain_free", "Retail Taxonomy > Snack > Granola > Granola > @flavor > cinnamon", "Retail Taxonomy > Snack > Granola > Granola > @claims > keto", "Retail Taxonomy > Snack > Granola > Granola > @claims > grain_free"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:claims:expected=['keto']:actual=['keto', 'grain_free']`

**exact errors:**
- `mismatch:canonical_label:expected='Granola (Grain Free, Cinnamon, Keto)':actual='Granola (Grain Free, Cinnamon, Keto, Grain Free)'`
- `mismatch:claims:expected=['keto']:actual=['keto', 'grain_free']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Granola > Granola', 'Retail Taxonomy > Snack > Granola > Granola > @variant > grain_free', 'Retail Taxonomy > Snack > Granola > Granola > @flavor > cinnamon', 'Retail Taxonomy > Snack > Granola > Granola > @claims > keto']:actual=['Retail Taxonomy > Snack > Granola > Granola', 'Retail Taxonomy > Snack > Granola > Granola > @variant > grain_free', 'Retail Taxonomy > Snack > Granola > Granola > @flavor > cinnamon', 'Retail Taxonomy > Snack > Granola > Granola > @claims > keto', 'Retail Taxonomy > Snack > Granola > Granola > @claims > grain_free']`

---

## granola_coconut_almond
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Granola"` | `"Snack > Granola"` |
| `product_identity` | `"Granola"` | `"Granola"` |
| `canonical_path` | `"Snack > Granola > Granola"` | `"Snack > Granola > Granola"` |
| `variant` | `[]` | `[]` |
| `flavor` * | `["coconut_almond"]` | `["coconut", "almond"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Granola (Coconut Almond)"` | `"Granola (Coconut, Almond)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @flavor > coconut_almond"]` | `["Retail Taxonomy > Snack > Granola > Granola", "Retail Taxonomy > Snack > Granola > Granola > @flavor > coconut", "Retail Taxonomy > Snack > Granola > Granola > @flavor > almond"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:flavor:expected=['coconut_almond']:actual=['coconut', 'almond']`

**exact errors:**
- `mismatch:canonical_label:expected='Granola (Coconut Almond)':actual='Granola (Coconut, Almond)'`
- `mismatch:flavor:expected=['coconut_almond']:actual=['coconut', 'almond']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Granola > Granola', 'Retail Taxonomy > Snack > Granola > Granola > @flavor > coconut_almond']:actual=['Retail Taxonomy > Snack > Granola > Granola', 'Retail Taxonomy > Snack > Granola > Granola > @flavor > coconut', 'Retail Taxonomy > Snack > Granola > Granola > @flavor > almond']`

---

## trail_mix_omega3
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Trail Mix"` | `"Snack > Trail Mix"` |
| `product_identity` | `"Trail Mix"` | `"Trail Mix"` |
| `canonical_path` | `"Snack > Trail Mix > Trail Mix"` | `"Snack > Trail Mix > Trail Mix"` |
| `variant` * | `["omega_3"]` | `["omega_3", "walnut_pumpkin"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `[]` | `["high_omega_3"]` |
| `canonical_label` * | `"Trail Mix (Omega 3)"` | `"Trail Mix (Omega 3, Walnut Pumpkin, High Omega 3)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > omega_3"]` | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > omega_3", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > walnut_pumpkin", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > high_omega_3"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['omega_3']:actual=['omega_3', 'walnut_pumpkin']`
- `core_mismatch:claims:expected=[]:actual=['high_omega_3']`

**exact errors:**
- `mismatch:canonical_label:expected='Trail Mix (Omega 3)':actual='Trail Mix (Omega 3, Walnut Pumpkin, High Omega 3)'`
- `mismatch:variant:expected=['omega_3']:actual=['omega_3', 'walnut_pumpkin']`
- `mismatch:claims:expected=[]:actual=['high_omega_3']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > omega_3']:actual=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > omega_3', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > walnut_pumpkin', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > high_omega_3']`

---

## trail_mix_hiking
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Trail Mix"` | `"Snack > Trail Mix"` |
| `product_identity` | `"Trail Mix"` | `"Trail Mix"` |
| `canonical_path` | `"Snack > Trail Mix > Trail Mix"` | `"Snack > Trail Mix > Trail Mix"` |
| `variant` * | `["hiking"]` | `["almonds_cashews_peanuts"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Trail Mix (Hiking)"` | `"Trail Mix (Almonds Cashews Peanuts)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > hiking"]` | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > almonds_cashews_peanuts"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['hiking']:actual=['almonds_cashews_peanuts']`

**exact errors:**
- `mismatch:canonical_label:expected='Trail Mix (Hiking)':actual='Trail Mix (Almonds Cashews Peanuts)'`
- `mismatch:variant:expected=['hiking']:actual=['almonds_cashews_peanuts']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > hiking']:actual=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > almonds_cashews_peanuts']`

---

## trail_mix_kids_school_safe
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Trail Mix"` | `"Snack > Trail Mix"` |
| `product_identity` | `"Trail Mix"` | `"Trail Mix"` |
| `canonical_path` | `"Snack > Trail Mix > Trail Mix"` | `"Snack > Trail Mix > Trail Mix"` |
| `variant` * | `["kids_school_safe"]` | `["sunflower_seeds_raisins"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["nut_free"]` | `["nut_free", "school_safe"]` |
| `canonical_label` * | `"Trail Mix (Kids School Safe, Nut Free)"` | `"Trail Mix (Sunflower Seeds Raisins, Nut Free, School Safe)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > kids_school_safe", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > nut_free"]` | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > sunflower_seeds_raisins", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > nut_free", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > school_safe"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['kids_school_safe']:actual=['sunflower_seeds_raisins']`
- `core_mismatch:claims:expected=['nut_free']:actual=['nut_free', 'school_safe']`

**exact errors:**
- `mismatch:canonical_label:expected='Trail Mix (Kids School Safe, Nut Free)':actual='Trail Mix (Sunflower Seeds Raisins, Nut Free, School Safe)'`
- `mismatch:variant:expected=['kids_school_safe']:actual=['sunflower_seeds_raisins']`
- `mismatch:claims:expected=['nut_free']:actual=['nut_free', 'school_safe']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > kids_school_safe', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > nut_free']:actual=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > sunflower_seeds_raisins', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > nut_free', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > school_safe']`

---

## trail_mix_chocolate_lovers
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Trail Mix"` | `"Snack > Trail Mix"` |
| `product_identity` | `"Trail Mix"` | `"Trail Mix"` |
| `canonical_path` | `"Snack > Trail Mix > Trail Mix"` | `"Snack > Trail Mix > Trail Mix"` |
| `variant` * | `["chocolate_lovers"]` | `["chocolate_lovers", "mixed_chocolate"]` |
| `flavor` | `["chocolate"]` | `["chocolate"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Trail Mix (Chocolate Lovers, Chocolate)"` | `"Trail Mix (Chocolate Lovers, Mixed Chocolate, Chocolate)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > chocolate_lovers", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > chocolate"]` | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > chocolate_lovers", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > mixed_chocolate", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > chocolate"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['chocolate_lovers']:actual=['chocolate_lovers', 'mixed_chocolate']`

**exact errors:**
- `mismatch:canonical_label:expected='Trail Mix (Chocolate Lovers, Chocolate)':actual='Trail Mix (Chocolate Lovers, Mixed Chocolate, Chocolate)'`
- `mismatch:variant:expected=['chocolate_lovers']:actual=['chocolate_lovers', 'mixed_chocolate']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > chocolate_lovers', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > chocolate']:actual=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > chocolate_lovers', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > mixed_chocolate', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @flavor > chocolate']`

---

## trail_mix_organic_raw_almond_cashew
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Snack > Trail Mix"` | `"Snack > Trail Mix"` |
| `product_identity` | `"Trail Mix"` | `"Trail Mix"` |
| `canonical_path` | `"Snack > Trail Mix > Trail Mix"` | `"Snack > Trail Mix > Trail Mix"` |
| `variant` * | `["raw"]` | `["almonds_cashews"]` |
| `flavor` | `[]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["organic"]` | `["organic", "raw"]` |
| `canonical_label` * | `"Trail Mix (Raw, Organic)"` | `"Trail Mix (Almonds Cashews, Organic, Raw)"` |
| `tree_paths` * | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > raw", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > organic"]` | `["Retail Taxonomy > Snack > Trail Mix > Trail Mix", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > almonds_cashews", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > organic", "Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > raw"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:variant:expected=['raw']:actual=['almonds_cashews']`
- `core_mismatch:claims:expected=['organic']:actual=['organic', 'raw']`

**exact errors:**
- `mismatch:canonical_label:expected='Trail Mix (Raw, Organic)':actual='Trail Mix (Almonds Cashews, Organic, Raw)'`
- `mismatch:variant:expected=['raw']:actual=['almonds_cashews']`
- `mismatch:claims:expected=['organic']:actual=['organic', 'raw']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > raw', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > organic']:actual=['Retail Taxonomy > Snack > Trail Mix > Trail Mix', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @variant > almonds_cashews', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > organic', 'Retail Taxonomy > Snack > Trail Mix > Trail Mix > @claims > raw']`

---

## apple_juice_from_concentrate_rtd
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Beverage > Juice"` | `"Beverage > Juice"` |
| `product_identity` * | `"Juice"` | `"Apple Juice"` |
| `canonical_path` * | `"Beverage > Juice > Juice"` | `"Beverage > Juice > Apple Juice"` |
| `variant` | `[]` | `[]` |
| `flavor` * | `["apple"]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["from_concentrate"]` | `["from_concentrate"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` * | `"Juice (Apple, From Concentrate)"` | `"Apple Juice (From Concentrate)"` |
| `tree_paths` * | `["Retail Taxonomy > Beverage > Juice > Juice", "Retail Taxonomy > Beverage > Juice > Juice > @flavor > apple", "Retail Taxonomy > Beverage > Juice > Juice > @processing_storage > from_concentrate"]` | `["Retail Taxonomy > Beverage > Juice > Apple Juice", "Retail Taxonomy > Beverage > Juice > Apple Juice > @processing_storage > from_concentrate"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Juice':actual='Apple Juice'`
- `core_mismatch:canonical_path:expected='Beverage > Juice > Juice':actual='Beverage > Juice > Apple Juice'`
- `core_mismatch:flavor:expected=['apple']:actual=[]`

**exact errors:**
- `mismatch:product_identity:expected='Juice':actual='Apple Juice'`
- `mismatch:canonical_path:expected='Beverage > Juice > Juice':actual='Beverage > Juice > Apple Juice'`
- `mismatch:canonical_label:expected='Juice (Apple, From Concentrate)':actual='Apple Juice (From Concentrate)'`
- `mismatch:flavor:expected=['apple']:actual=[]`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Beverage > Juice > Juice', 'Retail Taxonomy > Beverage > Juice > Juice > @flavor > apple', 'Retail Taxonomy > Beverage > Juice > Juice > @processing_storage > from_concentrate']:actual=['Retail Taxonomy > Beverage > Juice > Apple Juice', 'Retail Taxonomy > Beverage > Juice > Apple Juice > @processing_storage > from_concentrate']`

---

## orange_juice_not_from_concentrate
- core: **FAIL**
- exact: **FAIL**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Beverage > Juice"` | `"Beverage > Juice"` |
| `product_identity` * | `"Juice"` | `"Orange Juice"` |
| `canonical_path` * | `"Beverage > Juice > Juice"` | `"Beverage > Juice > Orange Juice"` |
| `variant` * | `[]` | `["not_from_concentrate"]` |
| `flavor` * | `["orange"]` | `[]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `[]` | `[]` |
| `claims` * | `["natural"]` | `["100_percent_juice"]` |
| `canonical_label` * | `"Juice (Orange, Natural)"` | `"Orange Juice (Not From Concentrate, 100 Percent Juice)"` |
| `tree_paths` * | `["Retail Taxonomy > Beverage > Juice > Juice", "Retail Taxonomy > Beverage > Juice > Juice > @flavor > orange", "Retail Taxonomy > Beverage > Juice > Juice > @claims > natural"]` | `["Retail Taxonomy > Beverage > Juice > Orange Juice", "Retail Taxonomy > Beverage > Juice > Orange Juice > @variant > not_from_concentrate", "Retail Taxonomy > Beverage > Juice > Orange Juice > @claims > 100_percent_juice"]` |
| `components` | `[]` | `[]` |

**core errors:**
- `core_mismatch:product_identity:expected='Juice':actual='Orange Juice'`
- `core_mismatch:canonical_path:expected='Beverage > Juice > Juice':actual='Beverage > Juice > Orange Juice'`
- `core_mismatch:variant:expected=[]:actual=['not_from_concentrate']`
- `core_mismatch:flavor:expected=['orange']:actual=[]`
- `core_mismatch:claims:expected=['natural']:actual=['100_percent_juice']`

**exact errors:**
- `mismatch:product_identity:expected='Juice':actual='Orange Juice'`
- `mismatch:canonical_path:expected='Beverage > Juice > Juice':actual='Beverage > Juice > Orange Juice'`
- `mismatch:canonical_label:expected='Juice (Orange, Natural)':actual='Orange Juice (Not From Concentrate, 100 Percent Juice)'`
- `mismatch:variant:expected=[]:actual=['not_from_concentrate']`
- `mismatch:flavor:expected=['orange']:actual=[]`
- `mismatch:claims:expected=['natural']:actual=['100_percent_juice']`
- `mismatch:tree_paths:expected=['Retail Taxonomy > Beverage > Juice > Juice', 'Retail Taxonomy > Beverage > Juice > Juice > @flavor > orange', 'Retail Taxonomy > Beverage > Juice > Juice > @claims > natural']:actual=['Retail Taxonomy > Beverage > Juice > Orange Juice', 'Retail Taxonomy > Beverage > Juice > Orange Juice > @variant > not_from_concentrate', 'Retail Taxonomy > Beverage > Juice > Orange Juice > @claims > 100_percent_juice']`

---

## frozen_orange_juice_concentrate
- core: **PASS**
- exact: **PASS**

| field | expected | actual |
|-------|----------|--------|
| `retail_type` | `"single"` | `"single"` |
| `category_path` | `"Frozen > Juice Concentrate"` | `"Frozen > Juice Concentrate"` |
| `product_identity` | `"Juice Concentrate"` | `"Juice Concentrate"` |
| `canonical_path` | `"Frozen > Juice Concentrate > Juice Concentrate"` | `"Frozen > Juice Concentrate > Juice Concentrate"` |
| `variant` | `[]` | `[]` |
| `flavor` | `["orange"]` | `["orange"]` |
| `form_texture_cut` | `[]` | `[]` |
| `processing_storage` | `["frozen"]` | `["frozen"]` |
| `claims` | `[]` | `[]` |
| `canonical_label` | `"Juice Concentrate (Orange, Frozen)"` | `"Juice Concentrate (Orange, Frozen)"` |
| `tree_paths` | `["Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate", "Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @flavor > orange", "Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @processing_storage > frozen"]` | `["Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate", "Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @flavor > orange", "Retail Taxonomy > Frozen > Juice Concentrate > Juice Concentrate > @processing_storage > frozen"]` |
| `components` | `[]` | `[]` |
