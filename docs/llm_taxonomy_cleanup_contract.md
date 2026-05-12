# LLM Retail Taxonomy Cleanup Contract

This is the exact output shape expected from the LLM cleanup pass.

The LLM does not return a retail path blob. It returns a normalized row record
that deterministic code can compile into a traversible tree.

## Core Shape

```json
{
  "fdc_id": "2606592",
  "retail_type": "composite_dish",
  "category_path": "Meal > Pasta Dishes",
  "product_identity": "Penne Alfredo",
  "canonical_path": "Meal > Pasta Dishes > Penne Alfredo",
  "canonical_label": "Penne Alfredo (Cajun Chicken)",
  "variant": ["cajun_chicken"],
  "flavor": [],
  "form_texture_cut": [],
  "processing_storage": [],
  "claims": [],
  "components": [
    {
      "identity": "Penne Pasta",
      "role": "base",
      "variant": [],
      "flavor": [],
      "form_texture_cut": [],
      "processing_storage": [],
      "claims": []
    },
    {
      "identity": "Alfredo Sauce",
      "role": "sauce",
      "variant": [],
      "flavor": [],
      "form_texture_cut": [],
      "processing_storage": [],
      "claims": []
    },
    {
      "identity": "Chicken Breast",
      "role": "protein",
      "variant": [],
      "flavor": ["cajun"],
      "form_texture_cut": ["diced"],
      "processing_storage": [],
      "claims": []
    }
  ],
  "confidence": 0.9,
  "mint_required": true,
  "review_flags": ["source_identity_conflict"],
  "rationale": "The cart item is a prepared penne alfredo meal; Cajun and diced describe the chicken component, not the pasta dish as a whole.",
  "tree_paths": [
    "Retail Taxonomy > Meal > Pasta Dishes > Penne Alfredo",
    "Retail Taxonomy > Meal > Pasta Dishes > Penne Alfredo > @variant > cajun_chicken",
    "Retail Taxonomy > Meal > Pasta Dishes > Penne Alfredo > @components > penne_pasta",
    "Retail Taxonomy > Meal > Pasta Dishes > Penne Alfredo > @components > alfredo_sauce",
    "Retail Taxonomy > Meal > Pasta Dishes > Penne Alfredo > @components > chicken_breast"
  ]
}
```

## Field Rules

`product_identity` is the thing a shopper is buying. It must be a sane grocery
list item: `Almond Milk`, `Orange Juice`, `Barbecue Sauce`, `Penne Alfredo`,
`Sardines`, `Meal Replacement Bar`.

`category_path` is browse structure only. It excludes product identity and all
facets. It must be at least two levels deep, such as `Beverage > Plant Milk`.

`canonical_path` is always:

```text
category_path > product_identity
```

No flavors, claims, brands, package sizes, cuts, storage states, or `@facet`
nodes go into `canonical_path`.

`canonical_label` is display text:

```text
Product Identity (Variant, Flavor, Form/Texture/Cut, Processing/Storage, Claims)
```

If there are no attributes, it is just `Product Identity`.

## Components

Use `components` when facts apply to part of the item rather than the whole SKU.

Example: `Penne Alfredo Pasta with Diced Cajun-Style Chicken Breast` is not a
`diced` pasta dish. The chicken component is diced.

Top-level:

```json
"product_identity": "Penne Alfredo",
"variant": ["cajun_chicken"],
"form_texture_cut": []
```

Component:

```json
{
  "identity": "Chicken Breast",
  "role": "protein",
  "variant": [],
  "flavor": ["cajun"],
  "form_texture_cut": ["diced"],
  "processing_storage": [],
  "claims": []
}
```

Component identities use Title Case. Component roles and component attributes
use normalized `snake_case`.

For combination meals, the top-level identity should be the meal, not one side:

```json
{
  "retail_type": "combination_meal",
  "category_path": "Meal > Prepared Meals",
  "product_identity": "Meatloaf Meal",
  "variant": ["mashed_potatoes", "corn"],
  "components": [
    {"identity": "Meatloaf", "role": "main", "variant": [], "flavor": [], "form_texture_cut": [], "processing_storage": [], "claims": []},
    {"identity": "Mashed Potatoes", "role": "side", "variant": [], "flavor": [], "form_texture_cut": [], "processing_storage": [], "claims": []},
    {"identity": "Corn", "role": "side", "variant": [], "flavor": [], "form_texture_cut": [], "processing_storage": [], "claims": []}
  ]
}
```

For pizza, sauce and toppings are components or top-level variant summary, not
the product identity:

```json
{
  "category_path": "Meal > Pizza",
  "product_identity": "Pizza",
  "variant": ["alfredo_sauce", "ham", "bacon"],
  "form_texture_cut": ["stuffed_crust"],
  "components": [
    {"identity": "Alfredo Sauce", "role": "sauce", "variant": [], "flavor": [], "form_texture_cut": [], "processing_storage": [], "claims": []},
    {"identity": "Ham", "role": "topping", "variant": [], "flavor": [], "form_texture_cut": [], "processing_storage": [], "claims": []},
    {"identity": "Bacon", "role": "topping", "variant": [], "flavor": [], "form_texture_cut": [], "processing_storage": [], "claims": []}
  ]
}
```

## Attribute Normalization

All attribute arrays use normalized `snake_case` values.

Good:

```json
"claims": ["unsweetened", "organic"]
```

Bad:

```json
"claims": ["Organic", "Unsweetened"]
```

Tree paths keep the `snake_case` value after the facet group:

```text
Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @claims > unsweetened
```

## Claim Order

Claims are not alphabetical. They use a fixed semantic order so labels and tree
facets stay stable.

Order:

1. Allergen/free-from: `gluten_free`, `dairy_free`, `lactose_free`, `nut_free`, `peanut_free`, `tree_nut_free`, `soy_free`, `egg_free`, `caffeine_free`
2. Diet/lifestyle: `vegan`, `vegetarian`, `plant_based`, `keto`, `paleo`, `kosher`, `halal`
3. Sugar/sweetener: `sugar_free`, `zero_sugar`, `no_sugar_added`, `unsweetened`, `reduced_sugar`, `lightly_sweetened`, `sweetened`, `monk_fruit`
4. Sodium/salt: `no_salt_added`, `unsalted`, `salt_free`, `low_sodium`, `reduced_sodium`, `sea_salt`
5. Fat/calorie: `fat_free`, `nonfat`, `low_fat`, `reduced_fat`, `light`, `lite`
6. Functional/nutrition: `high_protein`, `probiotic`, `fortified`, `whole_grain`
7. Sourcing/quality: `organic`, `non_gmo`, `grass_fed`, `pasture_raised`, `free_range`, `cage_free`, `wild_caught`, `sustainable`, `fair_trade`, `extra_virgin`
8. Marketing: `natural`, `all_natural`

Unknown claims sort after known claims alphabetically.

Example:

```json
"flavor": ["chocolate"],
"claims": ["unsweetened", "organic"]
```

Display:

```text
Almond Milk (Chocolate, Unsweetened, Organic)
```

Tree:

```text
Retail Taxonomy > Beverage > Plant Milk > Almond Milk
Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @flavor > chocolate
Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @claims > unsweetened
Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @claims > organic
```

## Hard Failure Rules

Fail the output if:

- A prepared meal routes to a component, such as `Penne Alfredo` becoming `Alfredo Sauce`.
- A component-only property becomes a top-level facet, such as `diced` on `Penne Alfredo` when only the chicken is diced.
- A combination meal has no component structure.
- A product packed in sauce routes to the sauce, such as sardines becoming `Tomato Sauce`.
- A claim is placed in `flavor`, such as `unsweetened` under `@flavor`.
- A claim becomes identity, such as `Light Ice Cream`.
- A physical attribute becomes identity, such as `No Pulp Orange Juice`.
- A pizza-adjacent product routes to pizza, such as `Pizza Sauce` becoming `Pizza`.
- A pizza routes to its sauce, such as `Alfredo Ham & Bacon Pizza` becoming `Alfredo Sauce`.
- Brand or parser false-friend tokens enter the path.

## LLM Role

The LLM resolves messy conflicts. Deterministic code validates shape, ordering,
normalization, and tree paths. If the LLM returns a plausible answer in the
wrong shape, it still fails.

## Test Workflow

Do not keep reworking rows the model already understands. Score outputs at two
levels:

1. Core pass: the model got the shopper-facing identity, retail type,
   category path, top-level facets, claims, and component identities right.
2. Exact pass: the output exactly matches the gold record, including label text,
   component roles/details/order, `mint_required`, and tree path order.

Core pass rows can be persisted as semantically solved and moved out of the
active prompt-tuning loop. Exact failures still matter, but many are compiler
problems rather than adjudication problems. `canonical_label`, `canonical_path`,
and `tree_paths` should be deterministically regenerated downstream from the
semantic fields.

Example: the live DeepSeek run for the flatbread breakfast sandwich reached a
core pass after prompt tuning:

- `product_identity`: `Breakfast Sandwich`
- `category_path`: `Frozen > Breakfast Sandwiches`
- `variant`: `chicken_apple_sausage`, `egg_white_cheddar`
- `form_texture_cut`: `flatbread`
- `processing_storage`: `frozen`
- no inherited `low_calorie` claim from the stale ESHA mapping

Its exact failure was label/component formatting. That should not send the row
back through broad identity prompt work.

## Model Selection

Model choice is part of the test matrix. Do not assume one model is best. Run
the same hard cases against cheaper candidates first and compare core/exact
scores.

Current default candidates avoid the high-cost Qwen 397B class. The first cheap
flatbread probe showed:

- `deepseek-ai/DeepSeek-V3.2` was the best cheap candidate on core taxonomy.
- `Qwen/Qwen3-30B-A3B-Instruct-2507` inherited a stale ESHA `low_calorie` claim.
- `Qwen/Qwen3-32B`, Nemotron Nano, and Kimi did not reliably return parseable
  JSON in that probe.
- Several fast endpoints returned Nebius `503`, so availability must be tracked
  separately from taxonomy quality.

Current DeepSeek 17-case diabolical run:

```text
core_passed: 2
core_failed: 15
exact_passed: 0
exact_failed: 17
```

Core passes:

- `diabolical_gluten_free_chocolate_chip_cookies`
- `diabolical_chicken_apple_sausage_flatbread_breakfast_sandwich`

Major failure buckets:

- Claim order: `organic`, `low_sodium` came back in the wrong order.
- Compound form normalization: `whole_peeled` came back as `whole`, `peeled`.
- Product identity granularity: `Pretzels` vs `Pretzel Pieces`, `Seasoning` vs
  `Seasoning Blend`, `Broccoli Cheddar Soup` vs `Soup`.
- Category routing: `Meal > Sandwiches` became `Deli & Prepared > Sandwiches`;
  `Pantry > Tortillas` became `Bakery > Tortillas & Wraps`.
- Over-modeling default states: model added `shelf_stable`, `canned`, `frozen`,
  `fully_cooked`, `crisps`, or `mix` even when those should not be top-level
  facets.
- Component omissions: dip/soup/tortilla component identities were missing.
- Component leakage: parfait/apple/chicken burger component traits leaked to
  top-level facets.

That means the next improvement should be a controlled normalizer/compiler plus
more canonical routing/compound-token rules, not simply a bigger model.

## Category Routing

A traversible taxonomy needs canonical category routing. If the prompt only asks
for a category, models invent plausible paths like `Frozen > Prepared Meals`.
The prompt therefore includes category hints for known identities, such as:

```text
Breakfast Sandwich: Frozen > Breakfast Sandwiches
Meal Starter: Meal > Meal Starters
Cheese Crisps: Snack > Cheese Crisps
Parfait: Meal > Composite Dishes
Pizza Crust Mix: Pantry > Baking Mixes
```

As coverage grows, this should become a controlled lookup table used by the
compiler, not a permanently growing wall of prompt examples.
