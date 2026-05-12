# Recipe Normalization & Canonical Identity Plan

## Implementation order (do these in this sequence — do not skip ahead)

The work has three foundational stages. Each one depends on the previous being
clean. Doing them out of order means re-doing them later.

### STAGE 1 — Fix fabricated `retail_leaf_path` values (foundation)

**Why first**: Today, compose_retail_leaf_path() synthesizes fake leaves
(`Beverage > Wine > Cabernet Sauvignon`, `Frozen > Vegetables > Peas > Frozen`,
`Meat & Seafood > Poultry > Raw`) when no real FDC retail leaf matches. The
result is **47-67% fabricated rlps across the golden files** (audit run on
2026-05-06):

| File | Total rows | Real | Fabricated |
|---|---:|---:|---:|
| `api_cache_taxonomy_v2.csv` | 70,351 | 47.4% | **52.2% (36,735)** |
| `sr28_fndds_taxonomy_v2.csv` | 18,378 | 32.4% | **67.3% (12,361)** |
| `recipe_ingredient_taxonomy_v2.csv` | 74,623 | 51.1% | **47.7% (35,601)** |

If half the retail leaves are made up, NOTHING downstream can be trusted —
recipe↔retail joins land on fictional paths, the planner can't validate,
and the non-food rerun would produce more fabrications. **Fix the foundation
first.**

The fix:
1. Modify `compose_retail_leaf_path()` to drop the synthesize branch.
2. When no FDC retail leaf matches, fall back to `canonical_path` (real FDC).
3. Re-emit all 5 golden files + bridge.
4. Verify with the same join — fabricated count must be zero.

The variant_hash in `htc_full_code` still distinguishes per-row identity for
the cascade. retail_leaf_path no longer needs to be unique-per-row.

### STAGE 2 — Fix non-food classifications

**Why second**: ~1,087 ingredients are mis-classified as `~N0000009` (Non-Food)
when they're actually food. Fixing them now (before STAGE 3) means the recipe
normalization layer has correct food/non-food classification to lean on.

The fix:
1. LLM rerun on every recipe ingredient currently classified as `~N0000009`.
2. Integrate the LLM output: re-tag each row with corrected canonical_path
   pointing to a REAL retail path (post-STAGE 1).
3. Re-emit golden files.

### STAGE 3 — Recipe normalization (canonical food + facets)

**Why last**: Recipe normalization (vocabulary standardization, adjective
bucketing, code-first identification, retail-backing audit) is the most
intricate layer. It depends on real retail leaves AND correct food/non-food
classification underneath. Doing this before STAGE 1 or 2 means re-doing it.

This is what the rest of the document specifies — the canonical-recipe-with-
runtime-facet-projection architecture, the three adjective buckets, the
synonym standardization, and the seven implementation phases (A-G).

---

## The architectural problem

Today's recipe ingredient strings are facet-laden, ambiguous, and over-specified.
The recipe layer is supposed to be a **clean culinary template** that the
planner projects onto specific products at runtime — but right now the
ingredient text bakes in product attributes, regional vocabulary, recipe-author
quirks, and even instructions ("egg wash" isn't an ingredient — it's a
preparation step).

This document specifies how we normalize the recipe ingredient layer so:

- One recipe template → many personalized realizations (organic / vegan /
  low-sodium / pantry-first / cheapest version) without rewriting the recipe
- Recipe ingredient overlap, pantry carryover, substitutions, gram totals, and
  pricing all become tractable
- Each recipe ingredient pins to a **real retail-backed canonical path** so the
  cascade planner finds Walmart/Kroger products

---

## Three buckets every adjective belongs to

When normalizing a recipe ingredient string, classify each adjective into
exactly one of these buckets:

### Bucket 1 — User preference facets (project at planner runtime)

Strip from the canonical name. Store as `claims` / facet flags on the row.
The planner picks a product matching the user's facet preferences at runtime.

- `organic`, `non-GMO`, `fair-trade`, `grass-fed`, `cage-free`,
  `free-range`, `pasture-raised`
- `fat-free`, `low-fat`, `non-fat`, `low-sodium`, `low-sugar`, `sugar-free`
- `vegan`, `vegetarian`, `kosher`, `halal`
- `gluten-free`, `dairy-free`, `lactose-free`, `nut-free`
- `whole-grain`, `whole-wheat` (when used as a preference, not when it's a
  different food — see Bucket 3)
- `natural`, `all-natural`, `no-additives`

### Bucket 2 — Culinary / preparation descriptors (form / processing)

Strip from canonical name. Store as `form_texture_cut` / `processing_storage`.
Doesn't change WHAT the food is, just how it's prepared or sold.

- `chopped`, `minced`, `diced`, `sliced`, `shredded`, `grated`, `cubed`,
  `julienned`, `crushed`, `cracked`, `crumbled`, `torn`
- `melted`, `softened`, `room-temperature`, `cold`, `warm`, `hot`
- `cooked`, `raw`, `boiled`, `poached`, `pan-fried`, `steamed`, `blanched`
- `fresh`, `frozen`, `canned`, `dried`, `dehydrated`, `pickled`
- `drained`, `rinsed`, `washed`, `patted`, `peeled`, `seeded`, `cored`,
  `trimmed`, `stemmed`, `pitted`
- `whole`, `halved`, `quartered`, `gutted`, `boneless`, `skinless`
- `large`, `medium`, `small`, `mini`, `miniature`, `extra-large`
- `ripe`, `unripe`, `green`, `overripe`

### Bucket 3 — Identity-changing descriptors (KEEP in canonical name)

These adjectives change the food itself. Different cooking behavior, chemistry,
texture, or culinary identity. Keep in the canonical name as a distinct food.

- `smoked paprika` ≠ `paprika` — different spice
- `sweetened condensed milk` ≠ `milk` — different ingredient
- `evaporated milk` ≠ `milk` — different ingredient
- `self-rising flour` ≠ `flour` — different ingredient (has leavening)
- `bread flour` ≠ `flour` — different protein content
- `cake flour` ≠ `flour` — different protein content
- `whole wheat flour` ≠ `flour` — different ingredient
- `powdered sugar` ≠ `granulated sugar` — different texture/use
- `brown sugar` ≠ `sugar` — different flavor/moisture
- `dark chocolate` ≠ `chocolate` — different cocoa %
- `white chocolate` ≠ `chocolate` — different ingredient
- `heavy cream` ≠ `cream` — different fat content
- `half-and-half` ≠ `cream` — different product
- `active dry yeast` ≠ `instant yeast` — different rising behavior
- `sourdough bread` ≠ `bread` — different fermentation
- `whole wheat bread` ≠ `bread` — different grain
- `Greek yogurt` ≠ `yogurt` — different texture/strain

**The rule of thumb**: if substituting the modified version vs the plain version
would change cooking behavior or recipe outcome, it's Bucket 3 (keep distinct).
If a user can pick either version and the dish still works, it's Bucket 1 or 2.

---

## Standardize vocabulary (synonym collapse)

Recipe authors say the same thing many ways. Collapse synonyms BEFORE bucketing
adjectives. Examples observed:

| Recipe text variants | Canonical |
|---|---|
| `orange peel`, `orange rind` | `orange peel` |
| `lemon peel`, `lemon rind` | `lemon peel` |
| `ice cube`, `ice cubes`, `crushed ice` | `ice` |
| `egg`, `eggs`, `large eggs`, `whole eggs`, `medium eggs`, `fresh eggs`, `raw eggs` | `eggs` |
| `egg yolk`, `egg yolks`, `raw egg yolks` | `egg yolks` (form=yolks) |
| `hardboiled egg`, `hardboiled eggs`, `hard-boiled eggs` | `eggs` (processing=hard-boiled) |
| `bananas`, `ripe bananas`, `unripe bananas` | `bananas` |
| `chicken breast`, `boneless skinless chicken breast`, `boneless skinless chicken breasts` | `chicken breast` (form=boneless skinless) |
| `egg replacer`, `vegan egg substitute` | `egg substitute` (claims=vegan) |
| `lemon zest`, `fresh lemon zest`, `meyer lemon zest` | `lemon` (form=zest, optional variant=meyer) |
| `mixed frozen vegetables`, `frozen mixed vegetables` | `mixed vegetables` (processing=frozen) |
| `frozen meatballs`, `frozen cooked meatballs`, `fully cooked frozen meatballs` | `meatballs` (processing=frozen, optional cooked) |

The synonym map is a curated dictionary that runs FIRST in the normalization
pipeline. Some synonyms come from intuition (peel = rind), others from
data-driven collapse (cluster ingredients with same canonical+facets after
normalization).

---

## Identify items by existing htc_code first; LLM only when ambiguous

We've spent significant time building the htc_code system. Many recipe
ingredients can be identified WITHOUT re-asking the LLM, because we already
have a code that points to the species/identity.

**Identification cascade per recipe ingredient:**

1. **Exact synonym map hit** — if the ingredient text matches a known
   synonym (orange peel → orange peel canonical), use the canonical's known
   htc_code. No LLM needed.

2. **Existing htc_code in our golden files** — if `recipe_ingredient_htc_tagged.csv`
   already has this exact item with a non-zero, non-`~N0000009` htc_code, trust
   it. The code points to a real food bucket; we just need to verify the path
   is retail-backed.

3. **Code-implied identity** — if we know that `~41BN000P` = rainbow trout in
   FDC, then ANY recipe ingredient at that code is rainbow trout. We can build
   a `htc_code → canonical_identity` map from FDC and reverse-resolve recipes
   without LLM.

4. **Adjective-bucketed normalization** — strip Bucket 1 / 2 adjectives, keep
   Bucket 3 adjectives. The remaining stem is the canonical food. Look up its
   htc_code from FDC; if found, use it.

5. **LLM fallback** — only for ingredients we genuinely can't identify by
   the above. The LLM gets the cleaned canonical (no Bucket 1/2 adjectives,
   no recipe-author noise) plus the FDC retail tree as context.

This dramatically cuts LLM calls. Most recipe ingredients are common foods that
already have a code somewhere in the system.

---

## Pin only to retail-backed canonical paths

Every recipe ingredient's `canonical_path` must be a real FDC retail path with
actual Walmart/Kroger products at it (or its parent). This is non-negotiable
because the planner joins recipe ↔ retail on path/code.

**Rules:**

- If the LLM emitted a path that's not in FDC retail, walk UP the LLM's path
  to find a real retail parent. Don't add synthetic anchors that have no
  retail products behind them.
- If the recipe is over-specific (`'00' strong flour`), pin to parent
  (`Pantry > Flour`) with `variant=strong` capturing specificity.
- If the recipe ingredient genuinely doesn't exist in retail (sake, persimmons,
  rabbit, edible flowers), keep a synthetic anchor as a placeholder — but the
  planner will return no-match for these and the user must handle out-of-band.
- Substitution rules handle items like `lemon zest` (no retail product, but
  whole lemons exist) — recipe pins to `Produce > Fruit > Lemons` with
  `variant=peel` and the planner buys the whole fruit.

### The same rule applies to `retail_leaf_path` — no synthesized retail leaves

This is currently violated. `compose_retail_leaf_path()` synthesizes a fake
retail_leaf_path when no FDC retail leaf matches the row's facets. Example:

```
title:            curly italian parsley
canonical_path:   Produce > Vegetables > Parsley            ← real FDC ✓
retail_leaf_path: Produce > Vegetables > Parsley > Curly Italian   ← FABRICATED ✗
leaf_source:      synthesized
```

`Produce > Vegetables > Parsley > Curly Italian` does NOT exist in FDC and no
Walmart/Kroger product is at that path. The planner can't find a match for the
strict identity match, so it falls to bucket — but the recipe row LOOKS like
it has a specific retail leaf. That's misleading and breaks the integrity rule.

**The fix**: drop the synthesize fallback. When no FDC retail leaf matches,
fall back to the canonical_path (which IS a real retail path). The
htc_full_code's variant_hash still captures the specific identity for
cross-corpus joins; the retail_leaf_path doesn't need to be the unique-string
carrier.

After the fix:

```
title:            curly italian parsley
canonical_path:   Produce > Vegetables > Parsley
retail_leaf_path: Produce > Vegetables > Parsley   ← falls back to canonical
leaf_source:      canonical_only
htc_full_code:    ~XXXX...-VVVVVV-KKKK  ← variant hash still distinguishes
```

The cascade still works:
- Tier 1 (htc_full_code) match: only products with same variant tokens
- Tier 2 (htc_code) match: any parsley product
- Tier 3 (canonical_path) match: any product at Produce > Vegetables > Parsley

No fake retail leaves are written into the data. **retail_leaf_path is either
a real FDC retail leaf OR the canonical_path (also real FDC) — never synthesized.**

---

## Recipe-context disambiguation (the "frozen assorted vegetables" problem)

Some recipe ingredient strings are genuinely under-specified at the ingredient
text level — but the recipe's broader context disambiguates them.

**Examples:**

- `frozen assorted vegetables` — could be Classic Mix, Stir-Fry Blend,
  California Blend, Italian Blend, Soup Mix, Asian Mix, Fiesta Blend, etc.
  Walmart sells each as a distinct retail product. We don't know which one
  the recipe needs from the ingredient string alone.
- `mixed berries` — could be a strawberry/blueberry/raspberry blend (American)
  or a different mix (depends on recipe).
- `cooking wine` — could be red, white, marsala, sherry depending on the dish.
- `nuts` — could be almonds, walnuts, mixed nuts, pecans depending on context.

**The disambiguation signals (in order of confidence):**

1. **Recipe title** — "California Stir-Fry with Chicken" → frozen vegetables
   are likely the California blend or stir-fry blend.
2. **Other ingredients in the recipe** — if the recipe has soy sauce, sesame
   oil, ginger, and rice → "frozen assorted vegetables" is a stir-fry blend.
   If the recipe has Italian herbs, parmesan, tomato sauce → Italian blend.
3. **Cooking instructions / steps** — "stir-fry the frozen vegetables" →
   stir-fry blend. "Roast with olive oil" → roasting vegetables (broccoli/
   cauliflower mix or similar).
4. **Recipe cuisine tag** — recipes already have cuisine metadata (Italian,
   Asian, Mexican, etc.) which biases the choice.
5. **Recipe category** — soup recipe → soup mix; salad recipe → salad blend.

**Implementation** (Phase E in the pipeline):

For ambiguous ingredients (a small curated set: `frozen assorted vegetables`,
`mixed vegetables`, `cooking wine`, `nuts`, `cheese` (when used generically),
`pasta` (generic), etc.), build a context-aware resolver that:

1. Pulls the recipe's full text (title + instructions + other ingredients).
2. Sends to DeepSeek with a prompt like:
   > Recipe: {title}
   > Ingredients: {full ingredient list}
   > Instructions: {first 3 steps}
   > One ingredient says "frozen assorted vegetables". Given the recipe
   > context, which retail product is most likely intended?
   > Options: California Blend, Stir-Fry Blend, Italian Blend, Soup Mix,
   > Classic Mix, Broccoli & Cauliflower, etc.
3. The LLM's answer becomes a per-recipe override that pins THIS recipe's
   "frozen assorted vegetables" to the specific retail product (e.g., California Blend
   for this recipe, Stir-Fry Blend for that recipe).
4. Cache the resolution per (recipe_id, ingredient_text) so the same recipe
   always gets the same disambiguation.

**This means recipe ingredients aren't always 1-to-1 with a canonical food**:
the same string can resolve differently across recipes based on context. That's
fine — what matters is each (recipe, ingredient) pair pins to a real retail
product.

---

## Recipe ambiguity removal

Some recipes have author quirks that produce nonsense ingredient strings:

- **"X or Y" choices** — `mashed potatoes or egg noodles` → recipe author gave
  user a choice between two foods. Don't try to canonicalize as a single food;
  split into two ingredient candidates and let the planner / user pick. Or
  pick the FIRST option deterministically.
- **Composite descriptors that aren't a real food** — `fresh cheese-filled
  egg tortellini` → may not exist as a single retail SKU. Resolve to the
  closest real product (`tortellini`, claims/variant=cheese-filled).
- **Recipe instructions, not ingredients** — `egg wash` is made FROM eggs,
  it's not bought. Either resolve to `eggs` (the buy ingredient) or flag as
  `instruction-only`. Same for `egg substitute` made at home from
  flax/applesauce — recipe ingredient is what you BUY.

---

## Concrete bugs observed (to be fixed)

Categorized by failure mode:

### Mis-routed at family fallback (frozen meatballs ≠ vegetables)

```
frozen meatballs            ~6000000X    Frozen > Vegetables > Meatballs   ← wrong
frozen cooked meatballs     ~6000000X    Frozen > Vegetables > Meatballs
frozen italian meatballs    ~6000000X    Frozen > Vegetables > Meatballs
fully cooked frozen meatballs ~6000000X  Frozen > Vegetables > Meatballs
```

Encoder family-fallback put meatballs under Frozen > Vegetables. Real path is
`Frozen > Meatballs` or `Meat & Seafood > Meatballs`.

### Mis-routed at family fallback (italian-style salad leaves ≠ Italian Style)

```
italian-style salad leaves  ~6000000X    Produce > Vegetables > Italian Style
```

Generic "Italian Style" is the LLM's noise. Should canonicalize to
`Produce > Salad Greens` or `Produce > Vegetables > Salad Mix`.

### Over-genericized (vegetable mixes lose retail specificity)

```
frozen stew vegetables               Frozen > Vegetables > Vegetable Blend
frozen broccoli and cauliflower      Frozen > Vegetables > Vegetable Blend
frozen stir-fry mixed vegetables     Frozen > Vegetables > Vegetable Blend
```

All flattened to "Vegetable Blend". Walmart actually has more specific paths
(`Frozen > Vegetables > Stir Fry Vegetables`, `Frozen > Vegetables >
Broccoli & Cauliflower`). We should preserve specificity that retail
distinguishes.

### Over-specified (free-range eggs unnecessarily distinct)

```
free-range eggs    ~5004000U-F26DC9-0000   Dairy > Eggs > Free Range
```

`free-range` is a Bucket 1 user-preference facet. Should normalize to
`canonical=eggs`, `claims=free_range`. Recipe shouldn't depend on free-range
to function — user can toggle that preference.

### Duplicate identities (egg replacer ≠ vegan egg substitute should match)

```
egg replacer          ~502Z000M    Pantry > Baking Mixes > Egg Replacer
vegan egg substitute  ~500G000G    Dairy > Eggs > Egg Substitute > Vegan
```

These are functionally identical products. Should canonicalize to one
identity (`egg substitute`, claims=vegan).

### Genuine non-food remaining

```
rubbing alcohol, petroleum jelly, baby oil, shea butter, parchment paper,
skewers, aluminum foil, parchment cups, paraffin wax, beeswax, glycerin,
hydrogen peroxide
```

These stay in `Non-Food`. Some sub-route to `Non-Food > Kitchen & Dining`
(tools) vs `Non-Food > Personal Care` (lotions, soaps) vs `Non-Food > Other`
(everything else).

---

## Implementation phases

### Phase A — Identify by code (no LLM)

1. Build `htc_code → canonical_identity` map from FDC consensus_full_corpus_audit.
   For each `htc_code`, the dominant `product_identity_fixed` is the canonical name.
2. For every recipe ingredient with a known htc_code, look up the canonical
   identity. If the ingredient text matches the canonical (after stripping
   Bucket 1/2 adjectives), confirm and move on.
3. Output: `recipe_ingredient_resolved_by_code.csv` with the matched identity,
   stripped adjectives moved to claims/form columns, and confirmation.

### Phase B — Vocabulary standardization

1. Build curated synonym map (peel↔rind, ice variants, egg variants, etc.).
2. Apply synonym map to recipe ingredient text BEFORE bucketing.
3. After synonym collapse, identify duplicates that now share the same
   canonical+facets. These collapse into a single recipe row reference.

### Phase C — Adjective bucketing

1. Build dictionaries for each adjective bucket.
2. For each recipe ingredient, parse adjectives and bucket them.
3. Strip Bucket 1/2 adjectives from canonical name; keep Bucket 3.
4. Move Bucket 1 adjectives to `claims` field; Bucket 2 to
   `form_texture_cut` / `processing_storage`.

### Phase D — Non-food rerun (LLM)

1. Send all ingredients currently in `~N` (Non-Food) bucket back to DeepSeek
   with the FDC retail tree + identity hints.
2. The LLM's job: classify each as food (and which retail path) or genuine
   non-food.
3. Integrate the LLM output: re-tag the recipe ingredients with corrected
   canonical_path / identity / facets.

### Phase E — Genuine ambiguity LLM round (small)

1. For recipe ingredients that survived Phase A-C without resolution
   (true vocabulary gaps the system can't identify), send to DeepSeek.
2. Provide the FDC retail tree, the existing htc_code universe, and the
   adjective bucket rules as context.
3. The LLM picks the best canonical + facets, pinning to a real retail path.

### Phase F — Retail-backing audit

1. For every recipe ingredient's resolved canonical_path, verify there's at
   least one real Walmart/Kroger product at that path.
2. If not, walk up the path tree until we find retail.
3. If no retail anywhere on the lineage, mark the ingredient as
   `no_retail_match` — the planner returns nothing for these, and the user is
   told this ingredient must be sourced manually.

### Phase G — Re-emit golden files

The five golden files all have to agree:
- `consensus_full_corpus_audit.csv`
- `consensus_htc_tagged.csv`
- `recipe_ingredient_htc_tagged.csv`
- `recipe_ingredient_taxonomy_v2.csv`
- `api_cache_taxonomy_v2.csv`
plus `ingredient_full_audit.csv`, `sr28_fndds_taxonomy_v2.csv`, and
`priced_products_v2.db`.

---

## Verification

After all phases:

1. Zero recipe ingredients in `~N0000009` that are actually food.
2. Every recipe canonical_path is retail-backed (real FDC retail OR substitution
   rule routes to a retail-backed parent).
3. Synonym duplicates collapse — `egg yolk` and `egg yolks` and `raw egg yolks`
   all share one identity row, with form=yolk.
4. Bucket 1 adjectives don't appear in canonical names. Spot-checks:
   `organic carrots` canonical=`carrots`, claims=`organic`.
5. Bucket 3 adjectives DO appear in canonical names. Spot-checks:
   `smoked paprika` canonical=`smoked paprika` (NOT `paprika` + claims=smoked).
6. Cross-corpus htc_codes agree across all 5 golden files.
7. Top 50 recipe ingredients all find ≥ 1 Walmart product via the cascade
   (full_code → htc_code → canonical_path).

---

## Out of scope (this round)

- The cascade planner (`calculate_recipe_cost_v5.py`) — the planner runs
  AFTER this normalization is done; today it's downstream of the data layer.
- Substitution rules (zest → whole fruit, etc.) — those exist; we'll integrate
  them with the normalization layer but the substitution logic itself is a
  different file (`recipe_mapper/v1/htc/substitutions.py`).
- Recipe-level personalization (organic mode, vegan mode, etc.) — that's the
  USER layer. This document is about the RECIPE layer's identity normalization.
