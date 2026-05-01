# DeepSeek-v4-flash classification notes — full corpus run

Live log of what the model gets right vs. what it screws up. Each entry is a real
fdc_id from the running corpus (`full_corpus.live.jsonl`). This is for the
post-run consolidation pass to know what to fix.

Last updated at: 31,772 rows / 462,695 (~6.9%) processed.

---

## ✅ WINS — model handled correctly

### 1. Override of stale ESHA / wrong BFC
The prompt tells the model to verify ESHA + override when title+ingredients
prove different. It's doing this consistently — 66 rows flagged
`esha_mismatch`, 58 flagged `bfc_mismatch`, 12 flagged `identity_override`.
That's ~136 rows where the model caught wrong source data and fixed it.

Example:
- fdc 2455175: `ORIGINAL REAL PANKO`. BFC was wrong (`Bread & Muffin Mixes`),
  model picked identity=`Panko` and flagged `category_mismatch`. ✓

### 2. Compound-noun titles → correct compound identity
- fdc 1962652: `BANANA DARK CHOCOLATE FRUIT BAR` → identity `Fruit Bars`,
  variant `banana_dark_chocolate`. NOT split into bare "Bar" + flavors. ✓
- fdc 2628705: `STRAWBERRY LEMONADE ORGANIC CHIA PREBIOTIC SQUEEZE SNACK`
  → identity `Fruit Snacks`, flavor `strawberry_lemonade`, form `squeeze`,
  claims `[organic, prebiotic]`. Multiple facet sources captured. ✓
- fdc 1035673: `ORIGINAL BAGEL THINS` → identity `Bagel Thins`,
  variant `original`, form `thins`. Recognized "Bagel Thins" as its own
  retail node (different from Bagels). ✓
- fdc 2164374: `ENGLISH MUFFIN STYLE TOASTING BREAD` → identity `Bread`,
  variant `english_muffin_style`. Correctly stayed at Bread (didn't drift
  into English Muffins). ✓

### 3. Form / processing extracted from title
- fdc 2428144: `CUT GREEN BEANS` (BFC=Canned Vegetables) → identity
  `Green Beans`, form `cut`, processing `canned`. ✓
- fdc 1383658: `BLACK BEANS` (BFC=Canned & Bottled Beans) → identity
  `Black Beans`, processing `canned`. ✓
- fdc 1885557: `SOUTHERN-STYLE HUSH PUPPY MIX` → identity `Hush Puppy Mix`,
  variant `southern_style`. Correctly inferred this as a baking mix. ✓
- fdc 2546735: `QUICK CHILI MIX` → identity `Chili Mix`, variant `quick`. ✓

### 4. Apple-named non-fruit correctly NOT classified as plain Apples
- fdc 2619318: `APPLE PIE FILLING` → identity `Pie Filling`, variant `apple`,
  processing `canned`. ✓ (would NOT pull in for "recipe needs apples")
- fdc 2510038: `ORGANIC BANANA CHIPS` → `Banana Chips` (not bananas). ✓

### 5. Snack-pack identification (recipe vs. snack distinction)
- fdc 2571713: `SLICED RED APPLES` (BFC=Pre-Packaged Fruit & Vegetables)
  → identity `Apple Snack Pack`. Correctly differentiates from fresh apples
  for recipe-mapping purposes. ✓
- fdc 2660520, 2081105, 2030076, 2216325 (apple+PB sliced packs) →
  all `Apple Snack Pack`. ✓

### 6. Beef Bologna handled correctly
- fdc 535499: `BEEF BOLOGINA` (typo "BOLOGINA" in title) → identity
  `Bologna`, variant `beef`. Model handled the typo and identified the
  meat product. ✓

---

## ❌ FAILURES — what the model fucks up

### F1. Caramel Apples missing as a node
- fdc 1888316: `PEANUT BUTTER & JELLY APPLE, RED CARAMEL/PEANUT BUTTER CHIPS`
  - Ingredients: Apples, Corn Syrup, Sugar, Condensed Whole Milk, Vegetable
    Shortening + Peanut Butter Flavored Chips
  - Reality: this is a whole CARAMEL APPLE on a stick
  - Model output: bare `Candy` (self-flagged `product_identity_generic`)
  - Normalizer: title has "caramel" → resolves to `Caramel Candy`
  - **Right answer:** identity `Caramel Apples` as its own node, with whole
    apple + caramel coating + PB chips as components
  - **Fix:** add `Caramel Apples` to the canonical taxonomy, normalize all
    "caramel" + "apple" titles to that identity

### F2. Generic-bar fallback when title doesn't name a subtype
- fdc 2424312: `VANILLA PECAN LONE STAR FOOD BARS WITH CINNAMON & CHIA SEEDS`
  - Model output: bare `Bars`
  - Model rationale: "no specific subtype (granola/protein) explicitly stated"
  - **Right answer:** likely `Snack Bars` or `Nutrition Bars` — title says
    "FOOD BARS" which is essentially `Nutrition Bars`
- fdc 2282612: `COCONUT CHIA BARS, COCONUT`
  - BFC: `Snack, Energy & Granola Bars`
  - Model output: bare `Bars`
  - **Right answer:** `Granola Bars` (the BFC literally says granola)
- **Pattern:** when title doesn't include the keyword "protein"/"granola"/
  "energy"/etc. but the BFC clearly does, the model still emits bare `Bars`.
  Should weight BFC more for bar subtype.

### F3. Identity correct but parented to wrong category
- fdc 2555567: `Pillsbury Grands! Flaky Layers Original Biscuits Canned Dough`
  - Identity: `Biscuit Dough` ✓ (correct)
  - Category: `Pantry > Baking Mixes` ✗ (it's not a baking mix; it's a
    refrigerated canned dough)
  - **Right answer:** `Refrigerated > Doughs` or `Refrigerated > Biscuits`
  - **Fix:** post-process re-parent — one entry in the identity→category map
- fdc 2024496: `FRESH SELECTIONS, VEGGIE TRAY WITH APPLES`
  - Identity: `Apple Snack Pack` (stretchy — it's a veggie tray with apples)
  - **Right answer:** `Veggie Tray` or `Snack Pack` parent

### F4. Disagreement on debatable composite items
- `CHEESECAKE BAR, STRAWBERRY` → `Cookie Bars` (could argue Dessert Bars)
- `100% JUICE, DICED APPLES` → `Applesauce` (could argue Canned Apples /
  Diced Apples In Juice)
- These aren't straight errors — they're judgment calls. Worth a list of
  "things the model classifies one way that you might want differently"
  to feed the consolidation pass.

### F5. Noise tokens cluttering variant/claims
- `enriched` shows up as variant on 303 Bread rows AND as claim on 328
  Bread rows. It's marketing/regulatory noise, not a meaningful subtype.
  Most enriched flour bread is just white bread — shopper saying "get me
  bread" doesn't care if it's enriched.
- **Fix:** drop `enriched` from variant and claims for Bread identity.
  Consolidation script: just remove it post-run.
- Watch for similar noise tokens (e.g., `bleached`, `fortified`,
  `unbleached`) that might also be filed inconsistently.

### F7. Magnetic-attractor identities from hint table (CRITICAL pattern)

Every "specific X" identity I baked into the hint table acted as a magnetic
attractor — when the model encountered a related-but-different SKU and
the hint table didn't have its specific node, it forced the SKU into the
nearest hint identity and demoted the real product type to flavor/variant.

The model literally explained this in its own rationales (see fdc 2594474):
> "Product is banana chips, but canonical hint table maps 'Apple Chips'
>  to Snack > Dried Fruit. Using Apple Chips as the closest canonical."

**Confirmed magnetic-attractor identities and damage:**

| identity | suspect rows | total rows | suspect % | what got swept in |
| --- | --- | --- | --- | --- |
| Mixed Nuts | 8,893 | 9,892 | 90% | Almonds (2527), Peanuts (1875), Cashews (1713), Pecans (837), Walnuts (597), Pistachios (473), Macadamia (261), Pine Nuts (130), Brazil Nuts (83) |
| Barbecue Sauce | ~2,747 | 3,452 | 80% | Chipotle Sauce, Worcestershire Sauce, Steak Sauce, Cocktail Sauce, generic "Sauce" SKUs |
| Bark | ~571 | 892 | 64% | Brownie Brittle / Brownie Bark (47), chocolate covered banana chips, truffle bars, brownie bites, "Birthday Cake Bark" |
| Apple Chips | 116 | 401 | 29% | Banana Chips (43), Mango Chips (24), Strawberry (17), Peach (8), Apricot, Sweet Potato, Pineapple, Veggie |
| Apple Snack Pack | 50 | 329 | 15% | Carrot snack packs (18), Cantaloupe Cup (5), Grape, Watermelon, Mango, Veggie packs |
| Broccoli with Cheese Sauce | 36 | 173 | 21% | Cauliflower (18) — Buffalo Cauliflower, Battered Cauliflower w/ Cheese; Brussels Sprouts; Spinach Artichoke Dip; Butternut Squash Veggie Cakes; Honey Glazed Carrots; Birds Eye Creamy Spinach |
| Butter | ~2,549 | 4,121 | ~62% | Peanut Butter (1549), Almond Butter (545), Cashew Butter (115), Sunflower Butter (98), Ghee (51), Mixed Nut Butter (41), Cookie Butter (32 — Speculoos, not butter), Hazelnut/Nutella (31), Compound Butter (25), Macadamia (20), Pecan (20), Walnut (19), Tahini (3) |
| Cake | ~1,500 | 5,872 | ~26% | Cake Mix (577 — wrong category, should be Pantry > Baking Mixes), Doughnut (404), Brownie (303), Cheesecake (290), Pie (226), Danish (195), Cinnamon Rolls (64), Cupcakes (35 — exists in hint as separate identity!), Muffins (16 — same), Fish Cake (14), Rice Cake (14), Pancake (13), Crab Cake (11), Sweet Rolls (4), Croissant (1). Bundt Cake (138), Coffee Cake (138), Layer Cake (92), Tea Cake (28), Birthday Cake (35) are LEGIT cake subtypes — keep. |
| Candied Fruit | ~860 | 927 | ~93% | Cake Decorations (123), Candied Ginger (61), Dried Fruit (31), Edible Confetti / Sprinkles (13), Real candied fruit/peel (10), Maraschino Cherries (3). PLUS 686 random non-candied-fruit SKUs swept in: Boston Baked Beans, Mexican mango candy, Date Rolls, Guava Paste, Crystallized Ginger Sliced, Ginger Candy Bites. Magnet is so broad almost nothing in it is right. |
| Cream | ~19 | 196 | ~10% | Half and Half (6 — promote to own identity), Coffee Creamer (8 — already exists as 1584-row identity, inconsistent use), Sour Cream (1), Cooking Cream (1), Dessert Topping (2), Non-Dairy Cream (1). Most Cream rows ARE legitimate heavy cream. |
| Cookies | ~410 | 14,664 | ~3% (graham/animal crackers only — most cookie rows are legit) | Graham Crackers (217 — these are NOT cookies, they're crackers), Animal Crackers (193). Non-magnet "should be own identity" candidates: Sandwich Cookies (~960 between sandwich+chocolate_sandwich+oreo variants), Macaroons (137), Wafer Cookies (255), Ginger Snaps (82), Biscotti (26), Pizzelles (21), Madeleines (17), Fortune Cookies (16), Macarons (14 — French, distinct from Macaroons). |
| Fruit and Veggie Strips | ~14 | 70 | ~20% | Apple/Fruit Crisps (7), Smoothie Blend (2), Puffs (1), Sticks (1), Chips (1), Bites (4). Sub-magnet of the "fruit snack" attractor family. |
| Ice Cream | TBD | 12,393 | TBD | Confirmed: pulls in Popsicles ("Pops"), Probiotic Pops, Plant-Based Oatmilk Pops. Could also be pulling in Sherbet/Sorbet, Gelato, Frozen Yogurt — needs full audit. |
| Jelly | small | small | path duplication | Two category paths used for same identity: `Pantry > Spreads > Jelly` and `Pantry > Jelly > Jelly`. Plus Royal Jelly (supplement) magnet-pulled into Jelly. |
| Dip / Hummus fragmentation (F8) | ~407 | 1,442 hummus SKUs | ~28% | 1,442 SKUs containing "hummus" in title scattered across 40+ identities: 1035 → Hummus (correct); 223 → Dip (Dip magnet!); 34 → Snack Pack; 22 → Chips; 18 → Cheese & Crackers Pack; 15 → Lunch Kit; 12 → Crackers; 12 → Crisps; 11 → Salad Dressing; etc. |
| Cream-family fragmentation (F8) | many | ~1,200 | many spellings | Cream (196), Heavy Cream (65), Heavy Whipping Cream (110), Whipping Cream (51), Whipped Cream (133), Light Cream (42), Sour Cream (562), Cultured Cream (11), Cream Substitute (8), Coffee Cream (3), Table Cream (4) — multiple distinct identities for what's mostly the same family. Heavy Cream + Heavy Whipping Cream + Whipping Cream are basically synonyms. |
| Half-and-Half spelling (F8) | many | 442 | 3 spellings | `Half & Half` (389), `Half and Half` (52), `Half-and-Half` (1) — three spellings of same identity. |
| Creamer family (F8) | many | ~1,710 | 9 spellings | Coffee Creamer (1584, main), Creamer (109), Oat Milk Creamer (7), Liquid Creamer (5), Non-Dairy Creamer (5), Almond Coconut Creamer (1), Almond Milk Creamer (2), Milk Creamer (1), Oat Creamer (2), Plant Milk Creamer (1) — same product class fragmented across 9+ identities. |

**Total confirmed wrong rows from these 5 magnets: ~12,000+** (~2.5% of corpus).
There are likely more magnets I haven't yet audited.

**Why my crude "lonely-hint" audit was unreliable:** it flagged identities
with high "suspect %" based on "title doesn't contain natural keyword."
But many cases (Hard Candy 92%, Salad Dressing 89%, Frozen Entree 95%)
were AUDIT FALSE POSITIVES — Hard Candy SKUs legitimately have titles
like "Atomic Fireballs" without the word "hard"; Salad Dressing SKUs say
"Ranch" or "Vinaigrette." Need a smarter audit that uses real title
keyword analysis per identity, OR human review.

**Post-run cleanup plan (no LLM re-call):**
For each confirmed magnet, write a fixer that maps "if identity is X AND
title doesn't contain X's natural keyword, look at title for [list of
better-fit identities] and reassign." See `cleanup_full_corpus.py`.

**Re-run option (cheaper than expected):**
For magnets where the LLM truly needs to reconsider (because flavor +
variant + form aren't easily inverted from a title), we can re-run JUST
those ~12K rows with a STRIPPED prompt (drop the magnet identities from
the hint table). Estimated cost: ~$2 total. Open-vocabulary mode worked
beautifully for things like Baklava — model would pick the right
specific identity if not constrained.

### F6. Singular/plural consolidation
- `hamburger_buns` (278) and `hamburger_bun` (173) are the same thing.
  `multigrain` (166) and `multi_grain` (75) are the same thing.
- **Fix:** post-run pass collapses these via case-folding + token
  normalization (no LLM needed).

### F8. Identity fragmentation (same product → multiple identities)
The opposite problem from magnets — when the hint table doesn't have a
canonical anchor, the model uses inconsistent spellings of the identity:

- **Creamer family** (~136 rows split across 6+ identities):
  - `Coffee Creamer` 1,584 (main, correct)
  - `Creamer` 109
  - `Oat Milk Creamer` 7
  - `Liquid Creamer` 5
  - `Non-Dairy Creamer` 5
  - `Half & Half` 7 (creamer-named SKUs landing here)
  - `Cream` 3
  - **Fix:** consolidate to `Coffee Creamer` (or split: dairy → Coffee Creamer,
    non-dairy → Plant-Based Creamer).

- **Half and Half family** (~440 rows split across 3 spellings):
  - `Half & Half` 385  (ampersand)
  - `Half and Half` 51 (the word "and")
  - `Cream` 4
  - **Fix:** pick one canonical spelling and collapse.

- **Sandwich Cookies family** (cookies investigation, F7):
  - sandwich variant 540 + chocolate_sandwich 312 + oreo 107 = ~960 rows
    that arguably should be promoted to `Sandwich Cookies` identity.

- Watch for the same pattern on other identities. Audit rule: identities
  whose names differ only by spelling/punctuation/article should collapse.

---

## OBSERVATIONS — patterns to watch for in the rest of the run

1. **Self-flagged 1.4%** of rows — these are the triage list. ~6,500 expected
   for full 462K.
2. **Bare-generic 0.2%** — small but real. The normalizer's title-keyword
   resolver catches most.
3. **Wrong-but-confident** — unknown rate. Need post-run random spot-check
   sample (~200 rows) reviewed by you to estimate.
4. **Compound-noun titles work** — model handles "Bagel Thins", "English
   Muffin Style Bread" etc. correctly when the compound is the whole
   shopper-facing name.
5. **BFC alone insufficient** — when title doesn't include subtype keyword
   the model falls back to bare. The BFC should be weighted more heavily.
6. **Identity-correct, category-wrong** is its own bucket — fixable post-run
   without touching the LLM output.

---

## F9. Jerky path fragmentation (user-flagged 2026-04-30)

**Identity side is mostly fine** — Beef Jerky 1,383 / Turkey Jerky 109 /
Pork Jerky 24 / Salmon Jerky 18 / Mushroom Jerky 12 / Chicken Jerky 9 etc.
are legitimately different products. The problem is **path fragmentation**:

| path                                  | rows  |
|---------------------------------------|-------|
| Snack > Jerky                         | 1,617 |
| Snack > Meat Snacks                   |   145 |
| Snack > Jerky & Meat Snacks           |     8 |
| Meat & Seafood > Beef                 |    17 |
| Meat & Seafood > Jerky                |     5 |
| Meat & Seafood > Jerky & Meat Snacks  |     3 |

Same product class scattered across 6 path variants. Also a `Jerky` (225)
bare identity that should resolve to the meat-typed identity from title.

**Fix:** post-run remap → all jerky paths collapse to `Snack > Jerky`;
bare `Jerky` identity gets meat-typed via title regex (beef|turkey|pork|
salmon|chicken|bacon|mushroom|coconut|beet|soy|vegan).

## F10. Juice path fragmentation (user-flagged 2026-04-30)

**Massive path inconsistency**, ~8,900 rows across 3 near-duplicate paths:

| path                                       | rows  |
|--------------------------------------------|-------|
| Beverage > Fruit-based Drinks > Juice      | 3,491 |
| Beverage > Fruit-based Drinks              | 3,378 |
| Beverage > Juice                           | 2,027 |
| Beverage > Fruit-based Drinks > Juice > Sugar | 82 |
| Beverage > Fruit-based Drinks > Juice > Orange | 54 |

271 distinct juice identities total (~11,645 rows). Many are legitimately
distinct (Orange Juice / Apple Juice / Grape Juice etc.) but the path tree
is inconsistent.

**Fix:** post-run remap → unify all juice products under one canonical
path (e.g. `Beverage > Juice > <fruit-or-blend>`). Drop the `Fruit-based
Drinks` middle node — it's a synonym for juice category.

Also: 1,015 juice-titled SKUs landed in `Pantry > Canned Vegetables`
(tomato juice, vegetable juice that ships shelf-stable). Need to decide
whether to keep them there (form-correct) or move to Beverage > Juice
(category-correct). User call.

## F11. Canned-fruit dumped in Canned Vegetables (user-flagged 2026-04-30)

**2,657 SKUs** where BFC explicitly says `Canned Fruit` were classified
under `Pantry > Canned Vegetables`. Zero rows go the other direction.

The model is using `Canned Vegetables` as a generic canned-anything bucket:
- `Pantry > Canned Vegetables`: 16,284
- `Pantry > Canned Fruit`: 265  (way too few)

Includes obvious cases like FRIED APPLES, SLICED APPLES, APPLE SLICES IN
WATER, CINNAMON APPLES IN A SUGAR AND CINNAMON SAUCE — all marked `bfc=
Canned Fruit` and pid=Applesauce/Apples but routed to Canned Vegetables.

Also the cherry/grape/lemon mixed fruit example: identity=Mixed Fruit,
bfc=Canned Fruit → path=Canned Vegetables.

**Fix:** post-run remap. If BFC contains "Canned Fruit" OR identity is in
{Applesauce, Apples, Mixed Fruit, Peaches, Pears, Pineapple, Mandarin
Oranges, Fruit Cocktail, Cranberry Sauce, ...} → path = `Pantry > Canned
Fruit`.

## F12. Canned seafood path fragmentation

Same product, three paths:
- `Pantry > Canned Seafood`: 1,358
- `Pantry > Canned Fish & Seafood`: 855
- `Pantry > Canned Tuna`: 135  (too narrow — should be `Canned Seafood >
  Tuna` or just consolidated)

Also: `Pantry > Canned & Jarred Vegetables` (42) vs main `Canned
Vegetables` (16,284); `Pantry > Canned & Jarred` (123) is a generic
dumping ground.

**Fix:** post-run path collapse to one canonical canned-* tree.

## F13. Pizza Crust Mix magnet (user-flagged 2026-04-30)

**554 total Pizza Crust Mix rows; 167 (30%) have no "pizza" or "crust" in
the title.** Generic baking-mix bucket when BFC is "Flours & Corn Meal"
and the model can't pin down a specific identity.

Sweep includes:
- WHITE FLOUR TORTILLA MIX (multiple, incl. 3x QUAKER HARINA PREPARADA)
- WHOLE WHEAT FLATBREAD MIX, ITALIAN HERB FLATBREAD MIX
- FOCACCIA GLUTEN FREE MIX
- BUTTERMILK CORN MEAL MIX
- MEYER LEMON GLUTEN FREE BAR MIX
- ORGANIC BLUEBERRY BLISS PROTEIN BAR MIX
- PALEO CARAMEL VANILLA BLONDIE MIX
- ROASTED TOMATO BASIL SEASONED COATING MIX
- ITALIAN HERB & PARMESAN CRUNCHY PANKO SEASONED COATING MIX
- STRAWBERRY HUSHPUPPY DESSERT MIX
- PAKORA/BHAJIA RECIPE MIX FOR LENTIL FRITTERS
- ONION RING MIX
- RAVA IDLI MIX
- PRETZEL, CRESCENTS DOUGH
- LEMON POPPYSEED MUFFIN & BREAD MIX (3x)

The model self-flagged most of these (`mint_required=TRUE`,
`review_flags=title_mismatch`) and picked Pizza Crust Mix as "closest
match" even when title clearly says Tortilla / Flatbread / Coating.

**Fix:** post-run remap. If pid=Pizza Crust Mix AND title lacks
(pizza|crust|dough) → re-pid via title regex:
- tortilla → Tortilla Mix
- flatbread → Flatbread Mix
- focaccia → Focaccia Mix
- coating mix → Seasoned Coating Mix
- bar mix → Baking Mix (or specific: Blondie Mix / Brownie Mix)
- muffin/bread mix → Baking Mix
- hushpuppy → Hushpuppy Mix
- pakora|bhajia|idli → Indian Snack Mix
- pretzel → Pretzel Mix
- corn meal mix → Cornbread Mix
- everything else → generic Baking Mix

## F14. Hummus full audit (user-flagged 2026-04-30, expanded from F8 frag note)

Full corpus: **1,442 hummus-titled SKUs across 48 identities.**

| identity                   | rows  | notes                                       |
|----------------------------|-------|---------------------------------------------|
| Hummus                     | 1,035 | the dip — correct                           |
| Dip                        |   221 | dessert/chocolate hummus → s/b Hummus       |
| Snack Pack                 |    34 | composite (hummus + veggies + pita)         |
| Snack Packs                |     4 | pluralization split with above              |
| Chips                      |    22 | hummus-flavored chips                       |
| Cheese and Crackers Pack   |    18 | hummus + crackers kit                       |
| Lunch Kit                  |    15 | hummus + protein lunch combo                |
| Crackers / Crisps          |    24 | hummus-flavored bakery snacks               |
| Salad Dressing             |    11 | plant-based hummus dressing                 |
| Pretzels / Pita Chips / .. |   ~12 | hummus-flavored variants                    |
| Pizza                      |     3 | hummus pizza, ok                            |
| 1-off identities (~12)     |   ~15 | "Hummus and Chips", "Hummus Bites", "Vegetable Tray with Hummus", "Carrots with Hummus", "Hummus and Flatbread Pack" — should collapse |

**Path fragmentation (6 paths for the same dip)**:
- `Pantry > Dips & Spreads` 1,244 (correct)
- `Snack > Snack Packs` 50, `Produce > Snack Packs` 18 (same category, two paths)
- `Snack > Chips` 37, `Snack > Crackers` 19, `Snack > Crisps` 7
- `Meal > Composite Dishes` 19
- `Pantry > Salad Dressings` 11

**Why some of this is correct, not a bug**: a hummus-flavored chip isn't
a substitute for hummus dip in a recipe. Form-based identity is right.
But when *searching* for "all hummus products" you miss them. The
`components` field (e.g. `Hummus | Flat Bread | Carrot | Zucchini |
Radish` on the user's snack-pack example) carries the info — needs to be
indexed alongside identity for retrieval.

**Fix:**
1. Collapse `Snack Pack` + `Snack Packs` (pluralization).
2. One-off identities ("Hummus and Chips", "Hummus Bites", etc.) → nearest canonical.
3. Dessert/chocolate `Dip` rows where title has "hummus" → re-pid to `Hummus`.
4. Path canonicalization: hummus-as-dip → `Pantry > Dips & Spreads`;
   hummus-flavored snacks stay in `Snack > {Chips,Crackers,Crisps,...}`.
5. Build a `contains_ingredient` index from `components` so "find all
   products containing hummus" returns all 1,442 regardless of identity.

## F15. Soda magnet (user-flagged 2026-04-30)

**5,160 Soda identity rows; 892 (17%) have no soda-keyword in title.**
Breakdown of the misclassified 892:

| actual product type | rows  |
|---------------------|-------|
| LEMONADE            |   134 |
| LIMEADE             |    10 |
| JUICE               |    37 |
| ENERGY drink        |    24 |
| SPARKLING (water/drink) | 25 |
| WATER               |    10 |
| PUNCH               |    10 |
| BEER (craft soda)   |    33 |
| TEA, COFFEE, CIDER, MILK | 8 |
| (other, no obvious keyword) | 357 |

**Smoking gun on user's example (fdc 2484057, ACAI BERRY GUAVA SPARKLING
FRENCH LEMONADE):** the model literally rationalized:
> "'French Lemonade' is a marketing term, not a distinct identity."

Because BFC said `Soda` and the FNDDS reference said `Soda, kiwi berry`,
the model overrode the title's "LEMONADE" word. The model has a working
`Lemonade` identity (981 rows) — this is pure source-data contamination,
not a missing bucket.

**Fix:** post-run remap. If pid=Soda AND title contains LEMONADE → pid=Lemonade.
Same pattern: LIMEADE → Limeade, ENERGY → Energy Drink, PUNCH → Fruit Punch,
SPARKLING WATER → Sparkling Water, JUICE → Juice (with fruit-typing).

Same magnet pattern as F11 (Canned Vegetables catch-all): when BFC is a
broad bucket, it overrides title evidence. Need a defensive rule
post-run: if title has a stronger product-type keyword than BFC, trust
the title.

## F16. Sparkling Water magnet (user-flagged 2026-04-30)

**5,146 Sparkling Water identity rows; 295 (5.7%) have no
sparkling/carbonated/seltzer/fizz/bubbly/tonic keyword in title.**

User's example (fdc 2124690, "NATURAL SPRING WATER, ZESTY LIME"): no
sparkling indicator in title. Model rationalized "CO2 indicates
sparkling" — but CO2 was not in the passed ingredients (model
hallucinated the rationale).

Confirmed contamination types:
- Plain flavored still water → Sparkling Water (`CONCORD GRAPE WATER
  BEVERAGE`, `RASPBERRY SPRING WATER BEVERAGE`, `WATER DRINK, STRAWBERRY
  LEMONADE`, `AGUA, ZERO CALORIES WATER + ELECTROLYTES`)
- Energy/functional waters (`ENERGY WATER INFUSED WITH BLACK RASPBERRY`)
- Lemonades (`TRADITIONAL VICTORIAN LEMONADE`, `ITALIAN LEMONADE SPRING
  WATER`, `ORGANIC ELDERFLOWER LEMONADE SOFT DRINK`)
- Frozen pops (`BLUE RASPBERRY +CAFFEINE ICE`, `BLACK RASPBERRY VITA ICE`)
- Garbage (`FUDGE CHEESECAKE` — needs full investigation, likely typo SKU)

**Fix:** post-run remap. If pid=Sparkling Water AND title lacks
(sparkling|carbonated|seltzer|fizz|bubbl|tonic|effervesc|CO2):
- title has lemonade → Lemonade
- title has "ICE" + caffeine → Frozen Pop / Energy Ice
- title has "energy water" / "electrolyte" → Functional Water /
  Electrolyte Water
- title has "spring water" or "mineral water" + flavor only → Flavored
  Water (still)
- title has just "water beverage" + fruit → Flavored Water

## F17. Oat-grain identity + path fragmentation (user-flagged 2026-04-30)

**2,108 oat-as-grain SKUs across 7 identities and 15 paths.** Same
product class scattered everywhere.

**Identity fragmentation (6 forms, all dry oats):**
| identity        | rows  |
|-----------------|-------|
| Oatmeal         | 1,295 |
| Oats            |   210 |
| Steel Cut Oats  |    75 |
| Rolled Oats     |    53 |
| Instant Oatmeal |    34 |
| Overnight Oats  |    30 |
| Hot Cereal      |   171 (mixed; some are oats, some not) |

**Path fragmentation — same identity at multiple paths:**
Oatmeal lives at:
- `Pantry > Hot Cereal` (1,209)
- `Pantry > Hot Cereal > Oatmeal` (21)
- `Pantry > Hot Cereal > Oatmeal > Oats` (9)
- `Pantry > Cereal` (28)
- `Pantry > Grain > Oats` (10)

Steel Cut Oats lives at:
- `Pantry > Grain > Oats > Hot` (50)
- `Pantry > Grain > Oats` (18)
- `Pantry > Hot Cereal` (3)
- `Pantry > Cereal` (2)

Same product, 5 paths. The model is generating ad-hoc tree branches
rather than committing to one canonical path.

**Fix:**
1. Path canonicalization → all oat-grain identities → `Pantry > Grain > Oats`.
2. Identity consolidation strategy (user call): keep them split for
   form-correctness (Steel Cut ≠ Rolled ≠ Instant) but ensure they all
   share the parent path. Variant field already captures the form
   (quick_cook, whole_grain, steel_cut, rolled, instant).
3. `Hot Cereal` → re-pid: title regex (oat|oatmeal|grits|farina|cream of wheat|wheat berries) → typed identity; otherwise leave as Hot Cereal.

This is the same pattern as F10 (Juice path frag) and F12 (Canned
Seafood frag). The model has no global path-tree commitment.
