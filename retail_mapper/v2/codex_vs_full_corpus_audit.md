# Codex vs full_corpus_audit

Full rows: `462,664`
Codex rows: `462,652`
Compared rows: `462,605`
Exact path rows: `394,412`
Path disagreement rows: `68,299`

## Disagreement Types

- `category_change`: `44,839`
- `department_change`: `20,452`
- `identity_change_same_category`: `1,912`
- `leaf_modifier_only`: `545`
- `category_change_same_identity`: `292`
- `canonicalizer_shape_only`: `153`
- `missing_from_codex`: `59`
- `missing_from_full`: `47`

## Field Diffs

- `retail_leaf_path`: `67,860`
- `canonical_path`: `67,315`
- `category_path_fixed`: `65,624`
- `product_identity_fixed`: `3,567`
- `modifier`: `2,409`

## Top Department Moves

- `Pantry` -> `Pantry`: `37,925`
- `Frozen` -> `Produce`: `4,108`
- `Beverage` -> `Beverage`: `2,794`
- `Pantry` -> `Meal`: `1,882`
- `Meal` -> `Frozen`: `1,728`
- `Snack` -> `Snack`: `1,646`
- `Frozen` -> `Frozen`: `1,413`
- `Meal` -> `Meal`: `1,319`
- `Bakery` -> `Snack`: `1,232`
- `Meat & Seafood` -> `Meat & Seafood`: `1,204`
- `Pantry` -> `Produce`: `1,046`
- `Dairy` -> `Pantry`: `983`
- `Dairy` -> `Beverage`: `958`
- `Dairy` -> `Dairy`: `608`
- `Pantry` -> `Dairy`: `580`

## Top Category Moves

- `Frozen > Vegetables` -> `Produce > Vegetables`: `3,960`
- `Pantry > Seasoning` -> `Pantry > Spices & Seasonings`: `3,862`
- `Pantry > Salsa` -> `Pantry > Sauces & Salsas`: `3,427`
- `Pantry > Sauce` -> `Pantry > Sauces & Salsas`: `3,258`
- `Pantry > Dip` -> `Pantry > Dips & Spreads`: `2,390`
- `Pantry > Pasta Sauce` -> `Pantry > Sauces & Salsas`: `2,120`
- `Pantry > Barbecue Sauce` -> `Pantry > Sauces & Salsas`: `1,856`
- `Beverage > Flavored Drinks` -> `Beverage > Mixes`: `1,569`
- `Pantry > Hot Sauce` -> `Pantry > Sauces & Salsas`: `1,195`
- `Meal > Pasta Dishes` -> `Frozen > Single Entrees`: `1,163`
- `Pantry > Pickles` -> `Meal > Salads`: `1,011`
- `Pantry > Spice Blend` -> `Pantry > Spices & Seasonings`: `961`
- `Pantry > Chicken Broth` -> `Pantry > Broth & Stock`: `952`
- `Pantry > Mayonnaise` -> `Pantry > Sauces & Salsas`: `929`
- `Pantry > Salt` -> `Pantry > Spices & Seasonings`: `821`
- `Meal > Sandwiches` -> `Meal > Sandwiches`: `803`
- `Frozen > Waffles` -> `Frozen > Pancakes, Waffles, French Toast & Crepes`: `789`
- `Pantry > BBQ Rub` -> `Pantry > Spices & Seasonings`: `688`
- `Pantry > Marinade` -> `Pantry > Sauces & Salsas`: `673`
- `Pantry > Marinara Sauce` -> `Pantry > Sauces & Salsas`: `633`