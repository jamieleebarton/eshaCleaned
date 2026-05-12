# Retail Taxonomy Semantic Contract

Date: 2026-04-29

## One-Sentence Explanation

We are turning messy retail product titles into a stable, human-shopping taxonomy by separating what the product is from the modifiers, physical state, and claims that describe the product.

## Why This Exists

The current retail paths are inconsistent because the path is trying to do too many jobs at once.

Examples of bad current behavior:

- Some rows end at a top-level bucket like `Bakery`, `Pantry`, or `Snack`. Nobody goes to the store to buy "Bakery".
- Flavor or ingredient words sometimes become the product identity. `Brown Sugar Barbecue Sauce` can get pulled toward `Sugar` even though the shopper is buying barbecue sauce.
- Physical state, claims, flavor, brand-ish words, and category words all get mixed into the same path.
- Similar products fragment into many leaves because each variant becomes its own path.

From `retail_mapper/v2/retail_leaf_v2_enriched_v2.cleaned.csv`:

- About 462k product rows.
- About 98k unique cleaned leaves.
- About 70% of unique leaves are singletons.
- Some cleaned leaves are only one segment, like `Pantry` or `Bakery`.

That is a sign that the taxonomy is absorbing SKU-level detail instead of producing stable shopping concepts.

## The Core Problem

Retail products have several different kinds of meaning:

```text
What am I buying?        -> product identity
What version is it?      -> variant / modifier / flavor
What state is it in?     -> form / texture / cut / processing
What claim does it make? -> dietary / nutrition / marketing filter
```

The current path often flattens all of these into one string. We need to split them.

## What We Are Not Doing

We are not building a nutrition taxonomy. ESHA, FNDDS, and SR28 are nutrition vocabularies. They are useful evidence, but they are not the retail shelf truth.

We are not making `how_is_it_used` a core retail-taxonomy axis right now. Use case may matter later for recipe/substitution logic, but it does not need to define the shopping taxonomy.

We are not making `ingredient` a required universal output axis. Ingredients can be evidence, but most of the time the thing made from the ingredient is already captured by product identity:

```text
orange juice  -> product identity, not product=juice + ingredient=orange
almond milk   -> product identity, not product=milk + ingredient=almond
black beans   -> product identity, not product=beans + color=black
```

Ingredient-like words only matter structurally when they are not the thing being bought:

```text
brown sugar barbecue sauce -> product identity is Barbecue Sauce
hickory smoked bacon       -> product identity is Bacon
chipotle mayo              -> product identity is Mayo / Mayonnaise
```

## The Desired Output

Each product should compile into a semantic product record.

Required shape:

```json
{
  "retail_type": "single",
  "category_path": "Pantry > Beans",
  "base_identity": "Beans",
  "product_identity": "Black Beans",
  "variant": [],
  "flavor": [],
  "form_texture_cut": ["whole"],
  "processing_storage": ["canned"],
  "claims": ["no_salt_added", "organic"],
  "canonical_path": "Pantry > Beans > Black Beans",
  "canonical_label": "Black Beans (Whole, Canned, No Salt Added, Organic)",
  "review_flags": []
}
```

The important distinction:

- `canonical_path` is stable and browsable.
- `canonical_label` is shopper-facing and can include useful modifiers.
- `claims` and other attributes remain structured filters, not path explosions.

## Field Definitions

### `retail_type`

The high-level product shape.

Allowed values:

```text
single
combo_pack
composite_dish
```

For this contract, the priority is `single`. `combo_pack` and `composite_dish` need separate component schemas and should not be forced into the same path logic.

### `category_path`

The shelf/browse bucket. It should usually be two levels:

```text
Beverage > Juice
Beverage > Plant Milk
Pantry > Beans
Pantry > Sauces & Salsas
Bakery > Bread
Dairy > Cheese
Frozen > Ice Cream
```

Invalid as final outputs:

```text
Bakery
Pantry
Snack
Beverage
Other
```

Those are only broad departments. They are not product identities.

### `base_identity`

The plain underlying thing before promoted modifiers.

Examples:

```text
Beans
Milk
Juice
Tomatoes
Mayo
Barbecue Sauce
Bagels
```

This is useful because some product identities include promoted modifiers.

### `product_identity`

The shortest buyable item phrase that answers "What am I buying?"

Examples:

```text
Orange Juice
Almond Milk
Black Beans
Barbecue Sauce
Chipotle Mayo
Diced Tomatoes
Cake Mix
Ice Cream Sandwich
Skim Milk
Diet Soda
Baking Soda
```

This field may include a modifier when the unmodified product would not be an acceptable substitute.

Promotion rule:

```text
Promote an attribute into product_identity if a shopper would not accept the unmodified product as a substitute.
```

Examples:

```text
Diet Soda      != Soda
Baking Soda    != Soda
Almond Milk    != Milk
Skim Milk      != Milk for many shoppers
Cake Mix       != Cake
Diced Tomatoes != Whole Tomatoes for cooking
```

But do not promote routine claims or weak marketing:

```text
Organic Ketchup      -> product_identity: Ketchup, claim: organic
Gluten-Free Cookies  -> product_identity may stay Cookies, claim: gluten_free
No Pulp Orange Juice -> product_identity: Orange Juice, form_texture_cut: no_pulp
```

There will be bucket-specific exceptions. The point is to make them explicit, not accidental.

### `variant`

A named version that is not quite flavor, claim, or physical state.

Examples:

```text
original
classic
homestyle
restaurant_style
thin_crust
extra_creamy
```

Use this sparingly. Many "variant" words are noise.

Weak terms that should rarely drive identity:

```text
original
classic
premium
natural
fresh
real
delicious
style
```

### `flavor`

Taste descriptors.

Examples:

```text
chocolate
vanilla
strawberry
chipotle
hickory
brown_sugar
sea_salt_caramel
garlic
ranch
lemon
lime
spicy
```

Flavor should not steal identity.

Bad:

```text
Brown Sugar Barbecue Sauce -> Sugar
Hickory Smoked Bacon       -> Hickory
Chipotle Mayo              -> Chipotle
```

Good:

```text
Brown Sugar Barbecue Sauce -> product_identity: Barbecue Sauce, flavor: brown_sugar
Hickory Smoked Bacon       -> product_identity: Bacon, flavor: hickory, processing_storage: smoked
Chipotle Mayo              -> product_identity: Mayo, flavor: chipotle
```

### `form_texture_cut`

The physical state, texture, cut, or shape.

Examples:

```text
whole
sliced
diced
shredded
ground
chunks
no_pulp
with_pulp
smooth
chunky
thin
thick
mini
sticks
nuggets
powder
liquid
```

This field answers:

```text
What shape/state is the item in?
```

It should matter only if it changes search, cooking, substitution, or purchase choice.

Examples:

```text
Orange Juice (No Pulp)
Diced Tomatoes
Shredded Cheddar Cheese
Sliced Turkey Breast
Ground Beef
Smooth Peanut Butter
Chunky Salsa
```

### `processing_storage`

What was done to it, or how it is stored/sold.

Examples:

```text
canned
frozen
fresh
dried
roasted
smoked
cured
uncured
pasteurized
from_concentrate
not_from_concentrate
cold_pressed
sparkling
instant
ready_to_eat
fully_cooked
raw
```

Some words can be both processing and flavor. Context decides.

Example:

```text
hickory smoked bacon
```

Should produce:

```json
{
  "product_identity": "Bacon",
  "flavor": ["hickory"],
  "processing_storage": ["smoked"]
}
```

### `claims`

Dietary, nutrition, certification, sourcing, or marketing claims.

Claims are filters. They should rarely become the path.

Examples:

```text
organic
gluten_free
dairy_free
vegan
vegetarian
kosher
halal
sugar_free
zero_sugar
no_sugar_added
unsweetened
low_sodium
reduced_sodium
no_salt_added
fat_free
low_fat
reduced_fat
nonfat
caffeine_free
decaf
high_protein
fortified
probiotic
grass_fed
cage_free
wild_caught
non_gmo
```

## Claim Ordering

Claims need a stable order so the same product does not render differently across runs.

Use this order:

```text
1. free_from
2. diet_certification
3. sugar_sweetener
4. sodium_salt
5. fat_calorie
6. functional_nutrition
7. sourcing_production
8. marketing_style
```

### `free_from`

```text
gluten_free
dairy_free
lactose_free
nut_free
peanut_free
tree_nut_free
soy_free
egg_free
fish_free
shellfish_free
caffeine_free
```

### `diet_certification`

```text
vegan
vegetarian
keto
paleo
whole30
kosher
halal
low_fodmap
```

### `sugar_sweetener`

```text
sugar_free
zero_sugar
no_sugar_added
unsweetened
reduced_sugar
lightly_sweetened
sweetened
stevia
monk_fruit
sucralose
```

### `sodium_salt`

```text
no_salt_added
unsalted
salt_free
low_sodium
reduced_sodium
sea_salt
salted
```

### `fat_calorie`

```text
fat_free
nonfat
low_fat
reduced_fat
light
lite
lean
extra_lean
low_calorie
reduced_calorie
```

### `functional_nutrition`

```text
high_protein
protein
probiotic
prebiotic
fortified
enriched
electrolyte
omega_3
fiber
whole_grain
sprouted
decaf
```

### `sourcing_production`

```text
organic
non_gmo
grass_fed
pasture_raised
free_range
cage_free
wild_caught
sustainable
fair_trade
extra_virgin
unrefined
unbleached
```

### `marketing_style`

```text
natural
all_natural
artisan
premium
gourmet
homestyle
authentic
hearty
clean_label
```

Marketing claims should be last and should not decide product identity unless a specific bucket says otherwise.

## Canonical Path Rules

The canonical path should be:

```text
category_path > product_identity
```

Examples:

```text
Beverage > Juice > Orange Juice
Beverage > Plant Milk > Almond Milk
Pantry > Beans > Black Beans
Pantry > Sauces & Salsas > Barbecue Sauce
Bakery > Bread > Bagels
Dairy > Cheese > Shredded Cheddar Cheese
```

The path should not include every attribute.

Bad:

```text
Beverage > Juice > Orange Juice > No Pulp > From Concentrate > Organic
Pantry > Sauces & Salsas > Brown Sugar > BBQ > Sweet > Hickory
Bakery > Vegan > Gluten Free > Apple > Cinnamon > Pie
```

Good:

```text
Beverage > Juice > Orange Juice
Pantry > Sauces & Salsas > Barbecue Sauce
Bakery > Pie > Apple Pie
```

Attributes live in fields.

## Traversible Taxonomy Rules

The row-level semantic CSV is not the taxonomy tree. It is the product assignment table.

The traversible taxonomy should be represented as nodes and edges:

```text
Retail Taxonomy
  Beverage
    Plant Milk
      Almond Milk
        @flavor
          chocolate
          vanilla
        @claims
          unsweetened
          organic
```

The stable browse path stops at product identity:

```text
Beverage > Plant Milk > Almond Milk
```

Facet nodes are filter children, not canonical path segments:

```text
Beverage > Plant Milk > Almond Milk > @flavor > chocolate
Beverage > Plant Milk > Almond Milk > @claims > unsweetened
```

This gives us both:

- a human-browsable product tree
- structured drill-down filters

It avoids fake paths like:

```text
Beverage > Plant Milk > Almond Milk > Chocolate > Unsweetened > Organic
```

That path is tempting, but it explodes the taxonomy and makes every SKU variant look like a category.

The traversible artifacts are:

| Artifact | Purpose |
|---|---|
| `retail_mapper/v2/semantic_product_taxonomy.csv` | Row-level product assignments and extracted attributes. |
| `retail_mapper/v2/semantic_taxonomy_nodes.csv` | All tree nodes: root, departments, categories, product identities, facet groups, facet values. |
| `retail_mapper/v2/semantic_taxonomy_edges.csv` | Parent-child edges between nodes. |
| `retail_mapper/v2/semantic_taxonomy_product_assignments.csv` | Product-to-product-identity node assignments. |
| `retail_mapper/v2/semantic_taxonomy_tree.json` | Nested tree version for UI/explorer use. |
| `retail_mapper/v2/semantic_taxonomy_tree_summary.json` | Counts and top nodes for QA. |

## Canonical Label Rules

The label is the human-readable thing we can show in search, review, or exports.

Build it in this order:

```text
Product Identity (Variant/Flavor, Form/Texture/Cut, Processing/Storage, Claims)
```

Examples:

```text
Orange Juice (No Pulp, From Concentrate)
Almond Milk (Chocolate, Unsweetened, Organic)
Black Beans (Whole, Canned, No Salt Added)
Barbecue Sauce (Brown Sugar)
Mayo (Chipotle)
Tomatoes (Diced, Canned, No Salt Added)
Bagels (Vegan)
Cheddar Cheese (Shredded, Reduced Fat)
```

Do not put brand or package size in the canonical label.

Brand and size are product-level metadata, not taxonomy.

## How To Decide If Something Belongs In Identity

Use these tests:

```text
1. Would a shopper search for this exact thing?
2. Would the unmodified product be an unacceptable substitute?
3. Would a recipe or cooking step fail if this modifier were ignored?
4. Does the modifier prevent a false friend?
```

If yes, promote it to `product_identity` or `canonical_label`.

If no, keep it as an attribute.

Examples:

| Product title | Product identity | Attribute handling |
|---|---|---|
| No Pulp Orange Juice | Orange Juice | `form_texture_cut: no_pulp` |
| Sugar-Free Orange Juice | Orange Juice | `claims: sugar_free` |
| Fat-Free Orange Juice | Orange Juice | probably ignore or low-value claim |
| Diet Soda | Diet Soda | promote because Soda is not equivalent |
| Baking Soda | Baking Soda | promote to avoid Beverage > Soda |
| Almond Milk | Almond Milk | promote because Milk is not equivalent |
| Organic Ketchup | Ketchup | `claims: organic` |
| Brown Sugar BBQ Sauce | Barbecue Sauce | `flavor: brown_sugar` |
| Hickory Smoked Bacon | Bacon | `flavor: hickory`, `processing_storage: smoked` |
| Diced Tomatoes | Diced Tomatoes or Tomatoes | bucket-specific, but always keep `form_texture_cut: diced` |
| Cake Mix | Cake Mix | promote because Cake is not equivalent |

## Relationship To Current Files

### `retail_mapper/v2/retail_leaf_v2_enriched_v2.csv`

This is the strongest input for LLM-style evidence. It contains:

- `llm_evidence_block`
- `title_ngrams_json`
- `role_candidates_json`
- `product_form_guess`
- `modifier_guesses`
- `ingredient_guesses`
- sibling and modal-supercategory checks
- ingredient summaries

This file has the evidence needed to decide product identity and attributes.

### `retail_mapper/v2/retail_leaf_v2_enriched_v2.cleaned.csv`

This is the cleaned current output. It contains:

- `clean_retail_leaf`
- `parser_retail_type`
- `parser_supercategory`
- `parser_category_group`
- `parser_category`
- `parser_primary_food`
- `parser_form`
- `parser_flavor`
- review flags

This file is useful, but its `clean_retail_leaf` should not be treated as final truth.

### `retail_mapper/parsed_titles_with_ingredients.csv`

This has the richer upstream parser shape:

- `retail_type`
- `supercategory`
- `category_group`
- `category`
- `primary_food`
- `form`
- `cut`
- `prep_state`
- `storage`
- `flavor`
- `flavor_blend`
- `inclusions`
- `claims`
- `dish_type`
- `pack_format`
- `components`
- ingredient fields

This is close to the semantic record we want, but it needs normalization and stricter output rules.

### `implementation/output/taxonomy_paths_cleaned.csv`

This is the newer 569-head taxonomy:

- `category_path`
- `head`
- `filter_axes`
- `product_count`

This is the best candidate source for stable `category_path > product_identity` pairs.

### `implementation/taxonomy_v3/head_dict.py`

This is the deterministic head dictionary. It already encodes important promotion rules:

- `Baking Soda` beats `Soda`.
- `Diet Soda` beats `Soda`.
- `Almond Milk` beats `Milk`.
- `Ice Cream Sandwich` beats `Ice Cream`.
- `Extra Virgin Olive Oil` beats `Olive Oil`.

This should be treated as the starting point for deterministic identity assignment.

### `retail_mapper/axes/*.tsv`

These are vocabulary lists for attributes:

- `form.tsv`
- `cut.tsv`
- `preparation_state.tsv`
- `storage.tsv`
- `flavor_universal.tsv`
- `diet.tsv`
- `fat.tsv`
- `sweetener.tsv`
- `sodium.tsv`
- `audience.tsv`
- `color.tsv`
- `cuisine.tsv`

These should feed deterministic attribute extraction.

## LLM Role

The LLM should not own the taxonomy.

The LLM should only help when deterministic evidence is ambiguous.

Good LLM task:

```text
Given the title, ingredients, current path, parser fields, and candidate heads,
return the semantic product record.
```

Bad LLM task:

```text
Invent a retail taxonomy path from scratch.
```

The deterministic compiler should own:

- allowed field names
- claim normalization
- claim order
- path construction
- invalid-output checks
- whether a proposed identity already exists
- whether a new head must be minted

The LLM can suggest:

- product identity
- which tokens are modifiers
- whether a modifier should be promoted
- whether a row needs review

## Desired LLM Output Shape

If we use an LLM, ask for strict JSON like this:

```json
{
  "retail_type": "single",
  "category_path": "Pantry > Sauces & Salsas",
  "base_identity": "Barbecue Sauce",
  "product_identity": "Barbecue Sauce",
  "variant": [],
  "flavor": ["brown_sugar"],
  "form_texture_cut": [],
  "processing_storage": [],
  "claims": [],
  "canonical_path": "Pantry > Sauces & Salsas > Barbecue Sauce",
  "canonical_label": "Barbecue Sauce (Brown Sugar)",
  "mint_required": false,
  "review_flags": []
}
```

Rules for the LLM:

- Do not include brand names.
- Do not include package size.
- Do not output only a department like `Bakery`.
- Choose what the product is, not what it tastes like.
- Ingredient words are evidence, not identity, unless they define the actual product.
- Claims are filters unless explicitly promoted by the product class.
- Return normalized snake_case attribute values.

## Deterministic Compiler Plan

The next practical implementation should be a deterministic compiler:

### Step 1: Load evidence

Join or consume fields from:

- `retail_leaf_v2_enriched_v2.csv`
- `retail_leaf_v2_enriched_v2.cleaned.csv`
- `parsed_titles_with_ingredients.csv`
- `taxonomy_paths_cleaned.csv`
- `head_dict.py`
- `axes/*.tsv`

### Step 2: Determine `retail_type`

Use upstream parser:

```text
single
combo_pack
composite_dish
```

For now, compile `single` rows first. Mark the others for separate handling.

### Step 3: Determine product identity

Use priority:

```text
1. Exact/high-priority head_dict match
2. Existing 569-head taxonomy match
3. Strong title form phrase
4. BFC + title agreement
5. ESHA/current description as weak evidence
6. Parser primary/form as weak evidence
```

Reject outputs that are too shallow or category-only.

### Step 4: Extract attributes

Use axis vocabularies and context:

```text
flavor_universal.tsv      -> flavor
cut.tsv                   -> form_texture_cut
preparation_state.tsv     -> processing_storage or form_texture_cut
storage.tsv               -> processing_storage
diet.tsv                  -> claims
fat.tsv                   -> claims
sweetener.tsv             -> claims
sodium.tsv                -> claims
audience.tsv              -> claims or review-only
```

### Step 5: Normalize claims

Convert noisy variants to canonical claim values.

Examples:

```text
gluten free, gluten-free, gf -> gluten_free
non fat, nonfat              -> nonfat
fat free, fat-free           -> fat_free
zero sugar                   -> zero_sugar
no sugar added               -> no_sugar_added
low sodium                   -> low_sodium
reduced sodium               -> reduced_sodium
no salt added                -> no_salt_added
non gmo, non-gmo             -> non_gmo
```

### Step 6: Build path and label

```text
canonical_path = category_path + " > " + product_identity
canonical_label = product_identity + ordered attributes
```

### Step 7: Emit review flags

Rows should be reviewed when:

```text
identity_missing
category_path_missing
path_too_shallow
top_level_only
modifier_used_as_identity
ingredient_used_as_identity
brand_used_as_identity
size_used_as_identity
evidence_conflict
parser_needs_review
low_confidence
combo_pack_unhandled
composite_dish_unhandled
mint_required
```

## Concrete Examples

### Unsweetened Chocolate Organic Almond Milk

Input:

```text
UNSWEETENED CHOCOLATE ORGANIC ALMONDMILK
```

Output:

```json
{
  "retail_type": "single",
  "category_path": "Beverage > Plant Milk",
  "base_identity": "Almond Milk",
  "product_identity": "Almond Milk",
  "flavor": ["chocolate"],
  "form_texture_cut": [],
  "processing_storage": [],
  "claims": ["unsweetened", "organic"],
  "canonical_path": "Beverage > Plant Milk > Almond Milk",
  "canonical_label": "Almond Milk (Chocolate, Unsweetened, Organic)"
}
```

### No Pulp Orange Juice From Concentrate

Input:

```text
NO PULP 100% ORANGE JUICE FROM CONCENTRATE
```

Output:

```json
{
  "retail_type": "single",
  "category_path": "Beverage > Juice",
  "base_identity": "Orange Juice",
  "product_identity": "Orange Juice",
  "flavor": [],
  "form_texture_cut": ["no_pulp"],
  "processing_storage": ["from_concentrate"],
  "claims": [],
  "canonical_path": "Beverage > Juice > Orange Juice",
  "canonical_label": "Orange Juice (No Pulp, From Concentrate)"
}
```

### No Salt Added Black Beans

Input:

```text
NO SALT ADDED BLACK BEANS
```

Current bad output seen in data:

```text
Pantry
```

Desired output:

```json
{
  "retail_type": "single",
  "category_path": "Pantry > Beans",
  "base_identity": "Beans",
  "product_identity": "Black Beans",
  "flavor": [],
  "form_texture_cut": ["whole"],
  "processing_storage": ["canned"],
  "claims": ["no_salt_added"],
  "canonical_path": "Pantry > Beans > Black Beans",
  "canonical_label": "Black Beans (Whole, Canned, No Salt Added)"
}
```

### Brown Sugar Barbecue Sauce

Input:

```text
BROWN SUGAR BARBECUE SAUCE
```

Wrong:

```text
Pantry > Sweeteners > Sugar
```

Desired:

```json
{
  "retail_type": "single",
  "category_path": "Pantry > Sauces & Salsas",
  "base_identity": "Barbecue Sauce",
  "product_identity": "Barbecue Sauce",
  "flavor": ["brown_sugar"],
  "form_texture_cut": [],
  "processing_storage": [],
  "claims": [],
  "canonical_path": "Pantry > Sauces & Salsas > Barbecue Sauce",
  "canonical_label": "Barbecue Sauce (Brown Sugar)"
}
```

### Chipotle Mayo

Input:

```text
CHIPOTLE MAYO
```

Desired:

```json
{
  "retail_type": "single",
  "category_path": "Pantry > Condiments",
  "base_identity": "Mayo",
  "product_identity": "Mayo",
  "flavor": ["chipotle"],
  "form_texture_cut": [],
  "processing_storage": [],
  "claims": [],
  "canonical_path": "Pantry > Condiments > Mayo",
  "canonical_label": "Mayo (Chipotle)"
}
```

### Vegan Bagels

Input:

```text
VEGAN BAGELS
```

Wrong:

```text
Bakery
```

Desired:

```json
{
  "retail_type": "single",
  "category_path": "Bakery > Bread",
  "base_identity": "Bagels",
  "product_identity": "Bagels",
  "flavor": [],
  "form_texture_cut": [],
  "processing_storage": [],
  "claims": ["vegan"],
  "canonical_path": "Bakery > Bread > Bagels",
  "canonical_label": "Bagels (Vegan)"
}
```

### Queso Blanco With Diced Tomatoes

Input:

```text
QUESO BLANCO A DELICIOUS BLEND OF WHITE CHEDDAR CHEESE. DICED TOMATOES, ROASTED GREEN CHILES AND SPICES
```

The row has ESHA evidence for diced canned tomatoes, but the retail product is queso/cheese dip.

Desired behavior:

```json
{
  "retail_type": "single",
  "category_path": "Dairy > Cheese",
  "base_identity": "Queso",
  "product_identity": "Queso",
  "flavor": ["green_chile"],
  "form_texture_cut": [],
  "processing_storage": [],
  "claims": [],
  "canonical_path": "Dairy > Cheese > Queso",
  "canonical_label": "Queso (Green Chile)",
  "review_flags": ["esha_identity_conflict"]
}
```

This shows why ESHA should be evidence, not final retail truth.

## Quality Gates

A good run should satisfy:

```text
No final paths with only one segment.
No final paths ending in broad departments like Bakery or Pantry.
No brand names in product_identity.
No package sizes in product_identity.
No obvious flavor-only identities for products that have a clear form.
No ingredient-only identities when the title contains a clear product form.
Claims are normalized and ordered.
Canonical labels are stable across runs.
```

Track these metrics:

```text
percent_path_too_shallow
percent_identity_missing
percent_mint_required
percent_review_flags
unique_canonical_paths
singleton_canonical_path_rate
top identity conflicts
top claim values
top unhandled modifiers
```

The singleton rate should drop substantially compared with the current 98k-leaf output.

## How To Explain This To Someone New

We are not trying to make a giant tree where every product variant is a leaf.

We are trying to produce:

```text
stable product identity + structured attributes
```

Instead of:

```text
Beverage > Juice > Orange > No Pulp > From Concentrate > Organic
```

We want:

```json
{
  "canonical_path": "Beverage > Juice > Orange Juice",
  "form_texture_cut": ["no_pulp"],
  "processing_storage": ["from_concentrate"],
  "claims": ["organic"]
}
```

That gives us a taxonomy humans can browse, plus attributes machines can filter, search, and validate.

The taxonomy should answer:

```text
What is the shopper buying?
```

The attributes should answer:

```text
Which version is it?
What state is it in?
What claims does it make?
```

If we keep those separate, the system stays clean.

If we mix them, the taxonomy becomes a junk drawer.
