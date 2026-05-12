# Taxonomy Rebuild — 2026-04-29

## Problem

The original `taxonomy_paths_cleaned.csv` was the output of bottom-up clustering applied
to retail product titles. It produced 43,887 leaf paths with three structural failures
that made it unusable for findability:

1. **Form/prep words used as path nodes.** `Bakery > Batter > Donut`,
   `Pantry > Mixes > Mix > Brazilian` — `Batter` and `Mix` are forms, not categories.
2. **Cross-root contamination.** `Bakery > Batter > Meat & Seafood Shrimp`,
   `Pantry > Chili > Jeanbaton Mayonnaise` — clustering glued tokens from one root
   under another root.
3. **Same product fragmented across roots.** Ice cream lived under
   Dairy, Frozen, Snack, Bakery, and Beverage simultaneously. Mayo lived under
   Pantry/Condiments, Pantry/Oil, Pantry/Chili, Produce/Cabbage, Meal/Composite Dishes.

Result: a search for `milk` returned strawberry-cream-flavored milk; a search for
`olive oil` returned truffle oil; `diet soda` was indistinguishable from `baking soda`.

## What we built

A **head-dictionary classifier** that maps every product description to a single
canonical bucket of the form `(category_path, head)`.

- **`category_path`** — shallow 2-level breadcrumb (e.g. `Pantry > Oils & Vinegars`).
- **`head`** — atomic, findable product noun (e.g. `Truffle Oil`, `Diet Soda`,
  `Almond Milk`, `Whole Milk`).
- **`filter_axes`** — list of dimensions that further differentiate products within
  the head (flavor, brand, size, fat, organic, etc.).

Heads are designed so a search matches what the user actually wants:
`milk` returns plain dairy milk only; `truffle oil` ≠ `olive oil`; `diet soda` ≠
`baking soda`; `strawberry milk` is its own head, not a flavor of `Milk`.

## Architecture

The classifier is a **priority-ordered list of regex patterns** against the
lowercased product description.

```
ENTRY = (head, category_path, patterns[], excludes[], filter_axes[])
```

Match algorithm: walk entries in order. First entry whose `patterns` matches AND
whose `excludes` does NOT match wins. No match → "Unclassified".

**Why ordered, not lookup:** more-specific entries must beat generic ones.
- `Diet Soda` must match before `Soda`
- `Baking Soda` must match before `Diet Soda` and `Soda`
- `Almond Milk` must match before `Milk`
- `Extra Virgin Olive Oil` must match before `Olive Oil`
- `Ice Cream Sandwich` must match before `Ice Cream`

**Why excludes:** a pattern like `\bsoda\b` catches "BAKING SODA"; the exclude
`\bbaking\b` filters those out. Excludes are essential when the head noun has
ambiguous siblings (cream soda, ice cream soda, club soda).

## Files

| Path | Purpose |
|---|---|
| `implementation/taxonomy_v3/head_dict.py` | The 618-entry head dictionary. Edit here to add patterns. |
| `implementation/output/taxonomy_paths_cleaned.csv` | The taxonomy: 569 unique `(path, head)` rows + filter_axes + product_count. |
| `implementation/output/taxonomy_paths_cleaned.csv.bak` | Backup of the original cluster-based file. |
| `implementation/output/taxonomy_paths_cleaned.csv.v2bak` | Backup after rule-based first attempt (1,893 rows). |
| `implementation/output/taxonomy_paths_cleaned.csv.v3bak` | Backup after dictionary v3.0 (456 rows, 80.8% coverage). |
| `implementation/output/taxonomy_paths_cleaned.csv.v3.1bak` | Backup after dictionary v3.1 (541 rows, 86.3%). |
| `implementation/output/taxonomy_paths_cleaned.csv.v3.2bak` | Backup after dictionary v3.2 (569 rows, 86.8%). |
| `retail_mapper/parsed_titles_with_ingredients.csv` | Source: 462,646 products with parsed columns. |

## Source data

`parsed_titles_with_ingredients.csv` (462,646 rows) has the columns the upstream
parser extracted: `primary_food, form, flavor, claims (JSON), dish_type, prep_state,
storage, brand_name, ingredients, allergens, etc.`

The classifier matches on `product_description` (the raw retail title) rather than
the parsed columns. Reason: the parsed columns have meaningful gaps —
22,416 products (5%) have empty `primary_food`; 25,391 products got dumped into a
junk `Combo Packs` category upstream; "BAKING SODA" gets `primary_food=soda`.

Description text is messy but **complete**. Patterns are easier to debug.

## Coverage

| Version | Coverage | Buckets | Notes |
|---|---|---|---|
| v0 (cluster) | n/a | 43,887 leaves | Original — broken in 3 ways |
| v1 (rule cleanup) | n/a | 45,459 paths | Form-word stripping + ancestor materialization |
| v2 (column elifs) | 100% | 1,893 buckets | Used parsed columns; respected upstream errors |
| v3.0 (dict) | 80.8% | 456 buckets | First real description-pattern classifier |
| v3.1 (fixes) | 86.3% | 541 buckets | Fixed milk-chocolate, peanut-butter-vs-plant-butter, gummi-spelling |
| v3.2 (current) | 86.8% | 569 buckets | + bacon/franks/baking mix/breadcrumbs/shallots/etc. |

## Promotion rule (when an attribute becomes part of the head)

The single rule that drove the design:

> An attribute becomes part of the **head** if the user wouldn't accept the
> unmodified product as a substitute. Otherwise it stays as a **filter attribute**.

Worked examples:

| Attribute | Promote to head | Stay as filter |
|---|---|---|
| Diet/Sugar | `Diet Soda` ≠ Soda; `Sugar-Free Cookies` ≠ Cookies | `Organic` (just sourcing) |
| Plant base | `Almond Milk` ≠ Milk; `Oat Milk` ≠ Milk | — |
| Fat level (dairy) | `Whole Milk`, `2% Milk`, `Skim Milk` — that's how people shop | — |
| Form | `Ice Cream Bar` ≠ scoopable Ice Cream; `Cake Mix` ≠ Cake | — |
| Flavor | `Strawberry Milk` ≠ Milk (default is plain) | Vanilla/Chocolate Ice Cream — neither is "default" |
| Cuisine | Rarely | Usually filter |
| Brand, Size | Never | Always |

## Findability tests (current state)

| Search | Returns | Doesn't return |
|---|---|---|
| `milk` | Whole/Reduced/Low-Fat/Skim/Buttermilk/Goat (dairy) | Almond/Oat/Soy (separate Plant Milk path), Strawberry/Vanilla/Chocolate (separate Flavored Milk path) |
| `oil` | Olive, Extra Virgin Olive, Truffle, Coconut, Avocado, Sesame, Canola, Vegetable, Sunflower, Walnut, MCT, Flaxseed, Cooking Spray, etc. — each its own head | — |
| `truffle oil` | 1 head, 21 products | Olive oil, chocolate truffles |
| `diet soda` | 1 head, 620 products | Baking soda, club soda, cream soda |
| `baking soda` | 1 head, 82 products in Pantry > Baking | Beverage > Soda |
| `strawberry milk` | 1 head, 11 products in Dairy > Flavored Milk | Plain Milk |
| `almond milk` | 1 head, 812 products in Beverage > Plant Milk | Plain Milk |
| `ice cream` | 10 heads: scoopable, Light, Cone, Sundae, Cake, Sandwich, Bar, Non-Dairy, Popsicle, Mix | each is a distinct shopping bucket |
| `mayonnaise` | 3 heads: Mayo / Light / Vegan | (was 80 paths in v0) |
| `gummy` | 1 head, 3,953 products (catches both "gummy" and "gummi" spellings) | — |
| `cake` | 13 heads: Cake, Cupcake, Cheesecake, Cake Mix, Pound, Bundt, Angel Food, Pop, Frosting, Filling, Coffee Cake, Ice Cream Cake | Pancakes, Rice Cakes |

## How to add a new head

1. Find what's missing. The leftover unclassified pile is best inspected by
   running `head_dict.py` against the source CSV and dumping non-matches.
2. Add an entry to `head_dict.py`. Three things:
   - Decide priority: P1 if it must beat a generic head, P2 for normal, P3 for cleanup.
   - Patterns: regex against lowercased description with `re.I`. Use `\b` word
     boundaries. Prefer multi-word patterns over single-word to avoid false hits.
   - Excludes: every false positive you see when sampling matches.
3. Re-run the classifier (about 60 seconds for 462K products).
4. Validate findability: search for the new head, search for adjacent heads, make
   sure they don't leak.

## Known limitations

1. **13.2% of products (~61K) are still unclassified.** The remaining tail is
   long: every additional pattern nets 0.05–0.2pp coverage. Two paths to push
   higher:
   - Manual: skim the unclassified pile, add ~50 more patterns → ~92%.
   - LLM: send unclassified products through a cheap model with the 569-head
     vocabulary as a constrained label set → ~99%, ~$30–60 in API.

2. **Some heads are still too generic.** `Sauce` (9,399), `Cookie` (11,500),
   `Cheese` (7,745), `Chocolate` (16,216) need further subtype splitting if you
   want browsable subcategories rather than a flat head with many products.

3. **The classifier is description-only.** It doesn't use ingredient lists,
   nutrition data, or brand metadata. For products where the description is
   ambiguous (e.g. an obscure regional brand), the classifier has nothing to fall
   back on.

4. **Only top-line buckets are validated.** Per-bucket sanity checks would
   require sampling 20 products per head and confirming the assignment is
   correct. Hasn't been done at scale; spot checks pass.

5. **Filter axes are declared, not enforced.** Each row says which dimensions
   apply (`flavor|brand|size|organic`) but the file doesn't carry the per-product
   attribute values. Those live on the products themselves.

## What's NOT in scope

- Brand normalization (still product-level).
- Per-product attribute extraction (already in `parsed_titles_with_ingredients.csv`).
- Mapping retail products to ESHA / FNDDS / SR28 entries (separate concern,
  handled by the upstream `fixy_done` pipeline).
- The taxonomy is for shopping/findability. ESHA's faceted descriptions
  (`Beef, chuck, raw, select, 0" trim`) are a separate vocabulary for nutrition
  matching, not browsing.
