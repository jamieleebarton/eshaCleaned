# HTC — Hestia Taxonomy Code (8-char alphanumeric positional)

Reference spec for the food identity code used by `recipe_mapper/v1/`.
Origin: `/Users/jamiebarton/Desktop/Esha/` (`build_htc_registry.py`,
`POSITIONAL_CODE_SYSTEMS_ANALYSIS.md`).

## Format

```
position:  1       2       3-4     5       6           7       8
           group   family  food    form    processing  ptype   check
           [0-K]   [0-9]   [00-99] [0-C]   [0-B]       [0-F]   crockford
```

Total capacity ≈ **34⁷ × 37 ≈ 1.94 × 10¹¹** distinct codes (vastly oversized for food).
Excluded characters: `I L O U` (visual-confusion with `1 0`, except `U` is reused for the check character set).

## Position 1 — Group (21 values)

| code | group |
|---|---|
| 0 | Unclassified |
| 1 | Dairy |
| 2 | Red Meat |
| 3 | Poultry |
| 4 | Fish & Seafood |
| 5 | Eggs |
| 6 | Vegetables |
| 7 | Fruits |
| 8 | Grains & Cereals |
| 9 | Legumes & Pulses |
| A | Nuts & Seeds |
| B | Oils & Fats |
| C | Sugars & Sweeteners |
| D | Beverages |
| E | Spices, Herbs & Seasonings |
| F | Condiments & Sauces |
| G | Baked Goods |
| H | Prepared & Mixed Dishes |
| J | Snack Foods |
| K | Supplements |
| M | Baby & Infant |
| N | Non-food *(extension; props, supplies, cleaners)* |

## Position 2 — Family (per-group, 0–F space)

Family rules live in `htc/encoder.py FAMILY_RULES`. A short tour:

- Dairy(1): 0=Milk, 1=Cheese, 2=Yogurt, 3=Cream, 4=Butter, 5=Ice cream, 6=Sour cream, 7=Cottage, 8=Cream cheese, A=Plant-based, B=Condensed/evaporated
- Spices(E): 0=Salt, 1=Pepper, 2=Cinnamon/Clove/Cardamom-style, 3=Herbs (basil/parsley/mint), 4=Cumin/Paprika/Curry, 5=Extracts/flavorings, 6=Seasoning blends, 7=Powders/seeds, 8=Leavening/binders, 9=Cocoa, B=Salt-adjacent (MSG/asafoetida)
- Condiments(F): 0=Mayo, 1=Ketchup, 2=Mustard, 3=BBQ, 4=Hot sauce, 5=Soy/teriyaki, 6=Salsa/guac, 7=Salad dressing, 8=Pasta sauce/gravy, 9=Pickles/olives/miso, A=Jam/jelly, B=Vinegar
- Grains(8): 0=Bread, 1=Bagel, 2=Tortilla/wrap, 3=Pasta, 4=Rice, 5=Oat, 6=Cereal, 7=Flour/starch, 8=Other grains/hominy/tater, 9=Pastry dough, A=Sponge cake/biscotti

(The full list is in `htc/encoder.py`.)

## Positions 3–4 — Food (00 reserved)

Currently always `00`. Reserved for a future SR-28-anchored discriminator that distinguishes specific foods within (group, family, form, processing, ptype). Until populated, two foods that share the other 5 positions (e.g. table salt vs sea salt with the same prep) get the same code; they differ in the **facet envelope** (modifier=Kosher, claims=sea_salt, etc.).

## Position 5 — Form (13 values)

| code | form |
|---|---|
| 0 | Unspecified |
| 1 | Fresh / Refrigerated |
| 2 | Frozen |
| 3 | Canned / Jarred |
| 4 | Dried / Dehydrated |
| 5 | Powdered |
| 6 | Liquid |
| 7 | Concentrated / Paste |
| 8 | Smoked |
| 9 | Pickled / Brined |
| A | Freeze-dried |
| B | Vacuum-sealed |
| C | Shelf-stable |

## Position 6 — Processing (12 values)

| code | processing |
|---|---|
| 0 | Unspecified |
| 1 | Raw / Unprocessed |
| 2 | Minimally Processed |
| 3 | Cooked / Heat-treated |
| 4 | Cured / Aged |
| 5 | Fermented |
| 6 | Ready-to-eat |
| 7 | Ready-to-cook |
| 8 | Marinated / Seasoned |
| 9 | Breaded / Battered |
| A | Fortified / Enriched |
| B | Ultra-processed |

## Position 7 — Product type (16 values)

| code | ptype |
|---|---|
| 0 | Whole / Unspecified |
| 1 | Sliced / Deli |
| 2 | Ground / Minced |
| 3 | Steak / Fillet |
| 4 | Block / Chunk |
| 5 | Shredded / Grated |
| 6 | Spread |
| 7 | Crumbled |
| 8 | Cubed / Diced |
| 9 | Stick / String |
| A | Wedge |
| B | Log / Wheel |
| C | Patty |
| D | Strip / Tender |
| E | Snack-size / Mini |
| F | Squeezable / Tube |

## Position 8 — Check digit

Crockford mod-37 over positions 1–7 using the alphabet `0-9 + A-Z (excl I L O U) + * ~ $ = U`.

```python
def crockford_check(code_7: str) -> str:
    val = 0
    for ch in code_7:
        idx = "0123456789ABCDEFGHJKMNPQRSTVWXYZ".index(ch.upper())
        val = val * 32 + idx
    return ("0123456789ABCDEFGHJKMNPQRSTVWXYZ" + "*~$=U")[val % 37]
```

## Reading examples

| code | decode |
|---|---|
| `1000600D` | Dairy / Milk family / generic / Liquid / Unspecified processing / Whole | check=D → Whole milk |
| `E0000006` | Spices / Salt family / generic / Unspecified form / Unspecified proc / Whole | check=6 → Plain salt |
| `B000600C` | Oils / generic family / Liquid / Unspecified proc / Whole | check=C → Generic cooking oil |
| `1000000B` | Dairy / Milk-default family / Unspecified form/proc/ptype | check=B → Butter, salted |
| `2000612N` | Red Meat / Beef family / Liquid (raw) / Raw / Ground | check=N → Ground beef, raw |
| `3000610Y` | Poultry / Chicken family / Liquid / Raw / Whole | check=Y → Raw chicken broiler |
| `8000130R` | Grains / Bread family / Fresh form / Cooked proc / Whole | check=R → Hominy, canned, white |
| `A000330P` | Nuts & Seeds / generic / Canned / Cooked / Whole | check=P → Pumpkin seed kernels, roasted |

## What the code does and doesn't carry

**In-code (positional):** group, family, form, processing, product type — the *identity* axes.

**Out-of-code (facet envelope):** flavor, brand, claims, retail variant, retail-shelf path, gram-conversion table, FNDDS food code, SR-28 NDB number(s).

This split is deliberate. The 8-char code stays human-scannable and dimensionally stable; everything else is a structured attribute on the side. (See `output/htc_facet_vocab.json` for the per-code controlled vocabularies.)
