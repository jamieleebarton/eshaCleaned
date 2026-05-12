# Hestia Product Identity Coding System

## Design Document

**Date:** 2026-05-02  
**Scope:** Convert 462,664 retail product records into deterministic, recipe-matchable identity codes.  
**Key Insight:** The `canonical_path` column in `full_corpus_audit.csv` already separates retail noise from food identity. We build on it.

---

## 1. Executive Summary

We need a compact identity code for every grocery product so that recipes can be matched to the correct products. The retail data has 177,734 unique shelf-location paths (`retail_leaf_path`), but recipes don't care about flavors, claims, or brands. A recipe calling for "cream cheese" should not match strawberry cream cheese. A recipe calling for "milk" should match whole, 2%, and skim. A recipe calling for "chicken tikka masala" should match exactly that frozen meal, not any random frozen entree.

The solution is a **two-tier identity system**:
- **Tier 1: Identity Code** — what the food IS (recipe matching layer)
- **Tier 2: Retail Variant** — flavor, claim, brand, package size (shopping layer)

The identity code is derived from `canonical_path` (10,252 unique paths) with category-specific rules for when modifiers become part of the code.

**Total compression:** 462,664 products → ~17,600 identity codes → ~26:1 ratio.

---

## 2. The Problem in the Data

### 2.1 Retail Path Explosion

`retail_leaf_path` treats every flavor and claim as a hierarchy node:

```
Bakery > Bagels > Blueberry > Whole Grain > Sliced
Snack > Chips > Potato Chips > Honey BBQ > Reduced Fat
Frozen > Ice Cream > Cherry Amaretto Chocolate Fudge
Dairy > Milk > 2 Percent > Reduced Fat
```

This creates **177,734 unique paths** for 462,664 products. It's perfect for shelf placement but useless for recipe matching.

### 2.2 The Existing Separation

The audit file already contains the separation we need:

| Column | Purpose | Unique Values |
|--------|---------|---------------|
| `retail_leaf_path` | Full retail differentiation | 177,734 |
| `canonical_path` | **Food identity** | **10,252** |
| `product_identity_fixed` | Core identity label | 6,414 |
| `modifier` | Variant trail | 110,344 |
| `flavor` | Flavor attribute | 22,113 |
| `claims` | Claim attributes | 574 |

The canonical path collapses 177k retail variants into 10k recipe-level identities. **The work is mostly done.** We just need to assign compact codes and handle edge cases.

### 2.3 The Edge Cases

Three categories break the simple "canonical path = code" rule:

**A. Too Broad — Flavored Variants**
`Dairy > Cheese > Cream Cheese` covers 933 products. Only 353 are plain. The other 580 are strawberry, blueberry, chive & onion, smoked salmon, etc. A recipe calling for "cream cheese" wants the plain one.

**B. Too Broad — Generic Prepared Foods**
`Frozen > Single Entrees` covers 5,664 products with 3,887 unique modifiers. "Chicken Tikka Masala" and "Fettuccine Alfredo" are completely different meals. They cannot share a code.

**C. Inconsistent — Form vs. Identity**
`Frozen > Vegetables > Green Beans` has form in the path. But `Pantry > Rice` (for frozen rice) does not. We need a clear rule for when fresh/frozen/canned is part of the identity vs. just a storage attribute.

---

## 3. The Three Coding Rules

### Rule A: Canonical Path Only
**For foods where modifiers are retail noise.**

The code is just the canonical path. Modifiers (flavor, claim, brand) are attributes stored separately.

**Applies to:**
- Milk, ice cream, potato chips, bagels, bread, juice, soda
- Raw meat, poultry, fish
- Fresh produce
- Individual spices and named seasoning blends

**Examples:**
| Product | Code | Modifier (attribute) |
|---------|------|---------------------|
| Lay's BBQ Potato Chips | `Snack > Chips > Potato Chips` | flavor=BBQ |
| Horizon Organic Whole Milk | `Dairy > Milk` | fat_level=Whole, claim=Organic |
| Thomas' Blueberry Bagels | `Bakery > Bagels` | flavor=Blueberry |
| Tropicana Orange Juice | `Beverage > Juice > Orange Juice` | (none) |

### Rule B: Modifier IS Identity
**For prepared foods and generic blends where the modifier describes what the food actually is.**

The modifier becomes Level 4 of the code. Different modifiers = different codes.

**Applies to:**
- Frozen single entrees, family entrees, appetizers
- Pizza
- Pre-made sandwiches, salads, pasta dishes
- Generic "seasoning" and "sauce" products (not named blends)
- Generic "dip" and "salsa" products

**Examples:**
| Product | Code |
|---------|------|
| Lean Cuisine Chicken Tikka Masala | `Frozen > Single Entrees > Chicken Tikka Masala` |
| Stouffer's Mac & Cheese | `Frozen > Single Entrees > Mac and Cheese` |
| DiGiorno Pepperoni Pizza | `Frozen > Pizza > Pepperoni` |
| McCormick All Purpose Seasoning | `Pantry > Spices & Seasonings > Seasoning > All Purpose` |
| Ragu Traditional Pasta Sauce | `Pantry > Sauces & Salsas > Pasta Sauce > Traditional` |

### Rule C: Default is Unmarked
**For foods where the plain/unflavored version is the recipe default, but flavored variants exist.**

The code is the canonical path. The **default** product has no flavor modifier (or modifier="Plain"). Recipes requesting the base item match the default. Recipes requesting a specific variant match that modifier.

**Applies to:**
- Cream cheese, cottage cheese
- Some yogurts (when fruit-flavored variants exist)
- Some breads (cinnamon raisin, banana bread)

**Examples:**
| Recipe Request | Match Rule |
|----------------|-----------|
| "cream cheese" | `Dairy > Cheese > Cream Cheese` + default (no modifier, or modifier=Plain) |
| "strawberry cream cheese" | `Dairy > Cheese > Cream Cheese` + modifier=Strawberry |
| "bagels" | `Bakery > Bagels` + default (no modifier, or modifier=Plain) |
| "blueberry bagels" | `Bakery > Bagels` + modifier=Blueberry |

**Important:** We never require a product to be explicitly labeled "plain." The default is defined by the **absence** of a distinguishing modifier.

---

## 4. Form vs. Identity

### The Rule

**Single-ingredient staples:** Form is a retail attribute, NOT part of the code.

| Product | Code | Form Attribute |
|---------|------|----------------|
| Birds Eye Frozen White Rice | `Pantry > Rice & Grain > White Rice` | Frozen |
| Goya Canned Black Beans | `Pantry > Beans & Legumes > Black Beans` | Canned |
| Tyson Frozen Chicken Breast | `Meat & Seafood > Poultry > Chicken Breast` | Frozen |
| Dole Canned Pineapple Chunks | `Produce > Fruit > Pineapple` | Canned |

**Prepared / composite products:** Form IS part of the identity because it changes the product category.

| Product | Code |
|---------|------|
| Del Monte Canned Green Beans | `Pantry > Canned Vegetables > Green Beans` |
| Birds Eye Frozen Green Beans | `Frozen > Vegetables > Green Beans` |
| Stouffer's Frozen Lasagna | `Frozen > Single Entrees > Lasagna` |
| Campbell's Condensed Tomato Soup | `Pantry > Soup > Tomato Soup` |

**Why the distinction?**
- A recipe calling for "white rice" does not care if it's frozen or dry. It's still white rice.
- A recipe calling for "green beans" might care if they're canned vs. fresh (different cooking times, salt content). More importantly, shoppers think of "canned green beans" and "frozen green beans" as distinct product categories.
- A recipe calling for "chicken tikka masala" expects a fully prepared frozen meal, not raw ingredients.

---

## 5. Category Deep Dives

### 5.1 Milk

- **Canonical path:** `Dairy > Milk`
- **Rule:** A
- **Modifiers:** Whole, 2 Percent, 1 Percent, Skim, Fat Free, Low Fat, Organic, Lactose Free, Fortified
- **Recipe matching:** "milk" matches all fat levels. "whole milk" matches `Dairy > Milk` + modifier=Whole.
- **Edge case:** Chocolate milk is `Dairy > Flavored Milk > Chocolate Milk` — its own canonical path because it's nutritionally and functionally distinct from plain milk.

### 5.2 Cream Cheese

- **Canonical path:** `Dairy > Cheese > Cream Cheese`
- **Rule:** C
- **Modifiers:** 195 unique. Top ones: Plain (353), Strawberry (56), Garden Vegetable (30), Chive Onion (28), Light (26), Fat Free (17), Blueberry (16), Pumpkin Spice (14)
- **Recipe matching:** "cream cheese" → default (no modifier or Plain). "strawberry cream cheese" → modifier=Strawberry.
- **Important:** The 580 non-plain variants are spreads, not recipe ingredients. The system must exclude them by default.

### 5.3 Bagels

- **Canonical path:** `Bakery > Bagels`
- **Rule:** A
- **Modifiers:** Plain (114), Cinnamon Raisin (78), Everything (73), Blueberry (57), Onion (41), Sesame (24), Whole Wheat (21)
- **Recipe matching:** "bagels" matches all flavors. The system may prefer Plain if available, but any flavor is acceptable.

### 5.4 Potato Chips

- **Canonical path:** `Snack > Chips > Potato Chips`
- **Rule:** A
- **Modifiers:** Plain (523), Barbecue (260), Jalapeno (163), Lightly Salted (71), Dill Pickle (64), Honey BBQ (33)
- **Recipe matching:** "potato chips" matches all flavors. "barbecue potato chips" matches `Snack > Chips > Potato Chips` + flavor=Barbecue.

### 5.5 Ice Cream

- **Canonical path:** `Frozen > Ice Cream`
- **Rule:** A
- **Modifiers/flavors:** Vanilla (6,182), Chocolate (6,122), Strawberry (5,534), Cinnamon (3,096), Lemon (2,709), Chocolate Chip (2,562)
- **Recipe matching:** "ice cream" matches all flavors. "vanilla ice cream" matches `Frozen > Ice Cream` + flavor=Vanilla.
- **Important:** One identity code covers 10,911 products. Flavor is purely an attribute.

### 5.6 Cheese (Hard/Block)

- **Canonical paths:** `Dairy > Cheese > Cheddar`, `Dairy > Cheese > Mozzarella`, `Dairy > Cheese > Parmesan`
- **Rule:** A (with nuance)
- **Modifiers:** Sharp, Mild, Shredded, Sliced, Block, Aged, Smoked
- **Recipe matching:** "cheddar" matches all sharpness levels. "sharp cheddar" matches `Dairy > Cheese > Cheddar` + modifier=Sharp.
- **Important:** Unlike cream cheese, cheddar variants (sharp, mild, extra sharp) are still "cheddar" — they're not flavored spreads. The sharpness is a quality grade, not a flavor variant.

### 5.7 Frozen Single Entrees

- **Canonical path:** `Frozen > Single Entrees`
- **Rule:** B
- **Modifiers:** 3,887 unique dish names
- **Recipe matching:** Each dish name is its own code.
- **Examples:** `Frozen > Single Entrees > Chicken Tikka Masala`, `Frozen > Single Entrees > Fettuccine Alfredo`, `Frozen > Single Entrees > Mac and Cheese`
- **Important:** No recipe says "add a frozen single entree." Recipes specify the dish. The code must reflect that.

### 5.8 Spices & Seasonings

- **Canonical paths:** `Pantry > Spices & Seasonings > [Named Blend]` (Rule A), `Pantry > Spices & Seasonings > Seasoning > [Modifier]` (Rule B)
- **Named blends (Rule A):** Taco Seasoning, Italian Seasoning, Cajun Seasoning, Jerk Seasoning, Steak Seasoning, Fajita Seasoning
- **Generic seasoning (Rule B):** `Pantry > Spices & Seasonings > Seasoning > All Purpose`, `Pantry > Spices & Seasonings > Seasoning > Chicken`
- **Compression:** 9,464 products → 265 canonical paths. The "one gram difference = new spice" problem is solved by canonical grouping.

### 5.9 Seasoning (Generic) — The Exception

`Pantry > Seasoning` is a massive catch-all with 3,862 products and 2,110 modifiers. The modifiers ARE the identity:

| Modifier | Identity |
|----------|----------|
| All Purpose | Generic all-purpose seasoning |
| Chicken | Chicken seasoning |
| Beef Stew | Beef stew seasoning |
| Garlic Herb | Garlic herb seasoning |
| Seafood | Seafood seasoning |

These should be treated as Rule B: the modifier becomes part of the code.

---

## 6. The LLM Matching Architecture

### The Problem with Open-Ended LLM Classification

If you ask an LLM to read a product title and "figure out the code," it will hallucinate. Different runs produce different strings. Cryptic titles like `SFS BIG DADDY'S FIESTADA BF STF SAND WG IW` get decoded inconsistently.

**The fix: Constrained matching, not open-ended generation.**

### The Pipeline

```
Product Title + Branded Food Category
    ↓
[Step 1] Clean & Normalize
    - Expand abbreviations (BF→Beef, STF→Stuffed, SAND→Sandwich)
    - Remove weights, counts, sizes
    - Lowercase, strip punctuation
    ↓
[Step 2] Score Against Known Registry
    - Signal 1: Branded food category → candidate L1/L2
    - Signal 2: Keyword overlap with canonical path aliases
    - Signal 3: Modifier match against known vocabulary
    - Signal 4: Fuzzy match against example product titles
    ↓
[Step 3] Generate Top 3 Candidates
    ↓
[Step 4] LLM Multiple-Choice Selection
    - LLM sees the product + top 3 options
    - Picks A, B, or C
    - If none match → flags as UNKNOWN
    ↓
[Step 5] Output Compact Code + Attributes
```

### The Registry

The registry is built from the audit file:

```python
CANONICAL_REGISTRY = {
    "Meal > Sandwiches > Sandwich": {
        "code": "L.Sandwich",
        "rule": "B",
        "known_modifiers": ["Beef Cheddar Mozzarella", "Turkey Club", ...],
        "known_bfc": ["Sandwiches/Filled Rolls/Wraps"],
        "example_titles": [
            "SFS BIG DADDY'S FIESTADA BF STF SAND WG IW...",
            ...
        ],
        "aliases": ["sub", "hoagie", "grinder", "wrap"]
    },
    "Dairy > Cheese > Cream Cheese": {
        "code": "D.Cheese.CreamCheese",
        "rule": "C",
        "default_modifier": "Plain",
        "flavor_blocklist": ["Strawberry", "Blueberry", "Pumpkin Spice", ...],
        "known_modifiers": ["Plain", "Strawberry", "Chive Onion", ...],
        ...
    },
    ...
}
```

### Why This Works

- **Deterministic:** The LLM picks from a finite list. It cannot invent "Beef Stuffed Sandwich" if that's not in the registry.
- **Auditable:** Every code assignment can be traced to a specific registry entry.
- **Correctable:** If the LLM picks wrong, we add more example titles to the registry entry.
- **Scalable:** New products are matched against known signatures. Truly new products (not in the registry) get flagged for human review.

---

## 7. Compact Code Format

For database storage and API usage, canonical paths can be compressed:

```
Domain.Class.Type[.Modifier]
```

**Examples:**
| Canonical Path | Compact Code |
|----------------|-------------|
| `Dairy > Milk` | `D.Milk` |
| `Dairy > Cheese > Cream Cheese` | `D.Cheese.CreamCheese` |
| `Dairy > Cheese > Cream Cheese > Strawberry` | `D.Cheese.CreamCheese.Strawberry` |
| `Snack > Chips > Potato Chips` | `S.Chips.PotatoChips` |
| `Frozen > Single Entrees > Chicken Tikka Masala` | `F.Entrees.ChickenTikkaMasala` |
| `Pantry > Spices & Seasonings > Taco Seasoning` | `P.Spices.TacoSeasoning` |
| `Bakery > Bagels` | `K.Bagels` |

The compact code is not user-facing. It's the internal routing key for recipe matching.

---

## 8. Recipe Matching Logic

### Basic Rules

| Recipe Says | Match Query |
|-------------|-------------|
| "milk" | `D.Milk` (any modifier) |
| "whole milk" | `D.Milk` + modifier=Whole |
| "cream cheese" | `D.Cheese.CreamCheese` + default modifier |
| "strawberry cream cheese" | `D.Cheese.CreamCheese` + modifier=Strawberry |
| "potato chips" | `S.Chips.PotatoChips` (any modifier) |
| "barbecue potato chips" | `S.Chips.PotatoChips` + flavor=Barbecue |
| "bagels" | `K.Bagels` (any modifier, prefer default) |
| "blueberry bagels" | `K.Bagels` + modifier=Blueberry |
| "chicken tikka masala" | `F.Entrees.ChickenTikkaMasala` (exact match) |
| "cheddar cheese" | `D.Cheese.Cheddar` (any sharpness) |
| "sharp cheddar" | `D.Cheese.Cheddar` + modifier=Sharp |
| "salt" | `P.Spices.Salt` (any type: kosher, sea, iodized) |
| "kosher salt" | `P.Spices.Salt` + modifier=Kosher |

### Preference Ranking

When multiple products match a recipe ingredient, rank by:

1. **Exact match** (code + modifier both match)
2. **Default match** (code matches, no modifier specified on product)
3. **Flavor-acceptable match** (code matches, flavor is reasonable substitution)
4. **Form-appropriate match** (code matches, form is appropriate for recipe context)

---

## 9. Implementation Plan

### Phase 1: Build the Registry (1-2 days)
- Extract all unique `canonical_path` values from `full_corpus_audit.csv`
- Assign Rule A/B/C to each path
- Build modifier vocabulary per path
- Generate compact codes
- Output: `canonical_registry.json`

### Phase 2: Clean the Modifiers (1-2 days)
- Deduplicate modifier strings (e.g., "Chive Onion" vs "Onion Chive")
- Normalize flavor names (e.g., "BBQ" → "Barbecue")
- Build flavor blocklists for Rule C categories
- Output: `modifier_vocabulary.json`

### Phase 3: Build the Matching Pipeline (2-3 days)
- Title cleaning and abbreviation expansion
- Keyword extraction
- Scoring algorithm against registry
- LLM constrained selection (top-3 multiple choice)
- Output: `product_coder.py`

### Phase 4: Test & Iterate (ongoing)
- Run pipeline against audit file products
- Compare generated codes to existing `canonical_path` + `modifier`
- Measure accuracy, fix registry gaps
- Output: `coding_accuracy_report.json`

---

## 10. Files and References

| File | Location | Description |
|------|----------|-------------|
| `full_corpus_audit.csv` | `retail_mapper/v2/` | Source data with canonical paths |
| `TAXONOMY_LLM_GUIDE.md` | This folder | Compact LLM classification protocol (~340 lines) |
| `IDENTITY_CODING_SYSTEM_DESIGN.md` | This folder | This document |
| `build_htc_registry.py` | `../Esha/` | Hestia Taxonomy Code bootstrap script |
| `esha_concept_resolver.py` | `../Esha/` | Existing recipe ingredient resolver |
| `concept_models.py` | `../Esha/` | Data models: ConceptCard, EshaIntent, ShoppingProfile |

---

## 11. Open Questions

1. **Greek Yogurt:** Is it `Dairy > Yogurt > Greek Yogurt` (separate path) or `Dairy > Yogurt` + modifier=Greek? The audit data has both.
2. **Sourdough Bread:** Is it `Bakery > Bread > Sourdough Bread` (separate path) or `Bakery > Bread` + modifier=Sourdough? Some recipes say "bread," others say "sourdough."
3. **Sharp Cheddar:** The audit treats sharpness as a modifier. Is that correct for recipe matching, or should Sharp/Mild/Extra Sharp be separate codes?
4. **Frozen Rice:** Should `Pantry > Rice & Grain > White Rice` + form=Frozen be the code, or do we need `Frozen > Rice & Grains > White Rice`?

These decisions need to be made per-category and encoded in the registry policy table.

---

## 12. Summary

The retail data has 177k paths but recipes only need ~17k identities. The audit file's `canonical_path` already did 90% of the work. What's left is:

1. **Assign rules** (A/B/C) to each canonical path
2. **Build the registry** with known modifiers and example products
3. **Implement constrained matching** so the LLM picks from known options instead of inventing codes
4. **Generate compact codes** for internal use
5. **Match recipes** using code + modifier logic

The system is deterministic, auditable, and correctable. It solves the "plain" problem, the "frozen rice" problem, and the "strawberry cream cheese" problem in one framework.
