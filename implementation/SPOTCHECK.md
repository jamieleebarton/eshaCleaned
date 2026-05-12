# SPOTCHECK — category_first_route v1

**Run:** 2026-04-27, on baseline `vIdentity` (the file the prior
`primary_identity_fix` 183k pass operated on too — see ARCHITECTURE.md for
why we re-ran from baseline rather than stacking on top).

## Headline numbers

| Bucket                                    | Count   |
| ----------------------------------------- | ------- |
| Total products in vIdentity               | 462,646 |
| `category_ok` (gate satisfied, untouched) | 356,794 |
| `needs_reroute` (gate failed)             | 106,205 |
| → rerouted by this pass                   | 18,823  |
| → flagged as new-leaf proposal            | 87,029  |

The router only rewrote ~4% of the file. The remaining 19% of mismatched
products are honest "tree gap" calls — there is no good destination in the
existing ESHA tree for them, so we did NOT force-fit. They live in
`category_first_new_leaves.csv`.

Outputs:
- `implementation/output/product_to_best_esha_full_map.vIdentity.csv` — edited in place
- `implementation/output/category_first_changelog.csv` — 18,823 rows, audit trail
- `implementation/output/category_first_new_leaves.csv` — 87,029 rows, tree gaps

## 20 random reroutes — honest grading

Sampled with `random.seed(42)` from the changelog. Verdicts are mine; some
are debatable.

| #  | Product                                          | New ESHA                                     | Verdict |
|----|--------------------------------------------------|----------------------------------------------|---------|
| 1  | KOREAN BARBECUE FIRE-GRILLED PORK JERKY          | Pork Skins, barbecue flavor                  | partial |
| 2  | Kellogg's Nutri-Grain Cereal Bars Raspberry      | Cereal, Muesli, with raspberries & hazelnuts | wrong   |
| 3  | CALAVO GUACAMOLE CALIENTE SPICY                  | Guacamole, spicy                             | correct |
| 4  | INDIVIDUAL SUPREME PIZZA                         | Pizza, snack, supreme, frozen                | correct |
| 5  | BLUEBERRY MUFFIN TOASTERS CEREAL                 | Cereal, Blueberry Muffin Tops                | correct |
| 6  | STEAK FRIES HOT CHILI CHEESE CORN & POTATO SNACK | French Fries, oven crinkle cut salt & pepper | wrong   |
| 7  | SALISBURY STEAK ROASTED PATTIES                  | Salisbury Steak, beef, patty, cooked, FS     | correct |
| 8  | BACON AND CHEESE GOURMET CHICKEN BURGERS         | Chicken, breast, patty, spicy, frozen        | partial |
| 9  | PORK TENDERLOIN SMOKED BACON                     | Bacon, cured, naturally hardwood smoked      | correct |
| 10 | WHEY PROTEIN STRAWBERRY POWDER                   | Protein, whey, vanilla, powder, scoop        | partial |
| 11 | Old El Paso Stand 'n Stuff Taco Shells Dinner Kit| Taco, chicken, crunchy                       | wrong   |
| 12 | WELCH'S 59 FL OZ FRUIT JUICE — CONCORD GRAPE     | Drink, cranberry harvest, 50% juice          | wrong   |
| 13 | KOSHER DILL HALVES                               | Pickles Dill, kosher                         | correct |
| 14 | FANCY PURE CLOVER HONEY                          | Honey, clover                                | correct |
| 15 | CHICKEN SALAD SANDWICH ON SWEET DARK BREAD       | Sandwich, chicken salad melt                 | correct |
| 16 | CHILE VERDE PORK IN GREEN SAUCE                  | Pork & Beans, with sweet sauce, canned       | wrong   |
| 17 | Sun-Maid California Sun-Dried Raisins            | Raisins, seedless, small box                 | correct |
| 18 | RICOTTA CHEESE CHERRY TOMATO PASTA SAUCE         | Sauce, pasta, tomato basil & cheese, jar     | correct |
| 19 | SWEET POTATO FRIES                               | French Fries, sweet potato, waffle cut       | correct |
| 20 | COFFEE GREEK YOGURT                              | Frozen Yogurt, coffee, low fat               | partial |

**Score:** 10 correct, 4 partial, 6 wrong.
**Strict precision:** 10/20 = 50%.
**Loose precision (correct + partial):** 14/20 = 70%.

## Where the failures come from

| Failure mode                   | Examples       | Why                                                                                          |
|--------------------------------|----------------|----------------------------------------------------------------------------------------------|
| Bar → cereal flavor cousin     | #2             | "Cereal/Muesli Bars" cluster has too few real bar leaves; closest match is a dry cereal      |
| Tightly named brand snack lost | #6             | "Steak Fries" snack chip product doesn't exist in tree; "fries" tokens overran               |
| Kit/dinner-mix specificity     | #11            | Taco shell *kit* found a chicken-taco recipe leaf instead of a shells-only leaf              |
| Grape→cranberry juice          | #12            | "Cranberry" leaked into evidence via inherited fields. (Could tighten: ignore old code description.) |
| Flavor mismatch within category| #10, #20       | Strawberry whey → vanilla whey, fresh yogurt → frozen yogurt. Tree lacks the exact flavor leaf |
| Cuisine-specific pork dish     | #16            | "Chile Verde" has no leaf at all                                                             |

The system is consistently honest: when it gets the head-noun and category
right, the win is precise (e.g. honey, raisins, pasta sauce, dill pickles,
salisbury steak). When the tree lacks the right leaf, it picks a near-miss
in the same cluster — that's the price of NOT flagging more aggressively.
The user-set anti-goal was force-fitting; we still fit 18,823. About half
of those are good fits, the other half are "near-miss with same head". I
recommend the user treat the changelog as a **review queue**, not an
auto-applied fix.

## Tree gaps — categories most starved for new leaves

These 20 categories generated the most new-leaf proposals. They are where
the ESHA tree is most under-built relative to the FDC product universe:

| Count  | Category                                         |
|--------|--------------------------------------------------|
| 3,313  | Popcorn, Peanuts, Seeds & Related Snacks         |
| 3,234  | Candy                                            |
| 2,897  | Other Snacks                                     |
| 2,328  | Chocolate                                        |
| 2,099  | Other Deli                                       |
| 1,912  | Snack, Energy & Granola Bars                     |
| 1,885  | Dips & Salsa                                     |
| 1,803  | Pickles, Olives, Peppers & Relishes              |
| 1,713  | Ice Cream & Frozen Yogurt                        |
| 1,666  | Other Drinks                                     |
| 1,649  | Chips, Pretzels & Snacks                         |
| 1,621  | Cereal                                           |
| 1,610  | Pre-Packaged Fruit & Vegetables                  |
| 1,594  | Baking Decorations & Dessert Toppings            |
| 1,568  | Cookies & Biscuits                               |
| 1,556  | Seasoning Mixes, Salts, Marinades & Tenderizers  |
| 1,538  | Cakes, Cupcakes, Snack Cakes                     |
| 1,485  | Frozen Appetizers & Hors D'oeuvres               |
| 1,236  | Frozen Dinners & Entrees                         |
| 1,188  | Water                                            |

Specific concept gaps worth surfacing (by inspecting new_leaves.csv):
- Asian fermented vegetables (kimchi, sauerkraut variants — 79+ products)
- Boba / pearl tea drinks
- Flavored sparkling waters by specific flavor
- Plant-based sausages / vegetarian-meat (we have *some* leaves but not
  many; product names like "Veggie Sausage Patties" routed badly because
  the tree's vegetarian-meat leaves are sparse)
- Specialty / regional candy varieties (mochi, halva, marzipan)
- "Family meal kits" combining multiple components
- "Stuffed chicken" and "stuffed seafood" variants
- Dairy-free frozen dessert flavors (almond-milk, coconut-milk based)

## Known limitations and a honest caveat about the prior pass

1. **Cohort-vs-description divergence.** Some ESHA codes have descriptions
   that flatly contradict their cohort majority. Example: code 37026
   "Lunchmeat Loaf, pickle & pepper" has a cohort majority of
   "Pickles, Olives, Peppers & Relishes" with 99.9% share — because 1,175
   *kimchi* products were dumped onto it upstream. My category gate
   considers this code "category-OK" for kimchi products, so it does NOT
   re-route them. To fix this we'd need a tree-integrity pass that flags
   codes where the description-implied category disagrees with the
   cohort-majority category. That is a separate pass and was out of scope.
   46 of the 138 kimchi products in this dataset still point at 37026
   for this reason.

2. **Croutons vs Breadsticks.** Both routed to "Breads & Buns" cluster, so
   the category gate cannot distinguish them. Intra-cluster errors like
   this require a more granular tree taxonomy or a separate "form check"
   pass.

3. **Hand-curated cluster map is incomplete.** 86 clusters cover all
   high-volume categories, but tail categories (e.g. niche supplements)
   collapse to singletons. Singletons mean their products will mostly
   land in the new_leaves file. That's the desired behavior under the
   "be honest, don't force-fit" rule.

4. **Replacing the prior pass.** Per ARCHITECTURE.md, I reverted vIdentity
   to baseline before running so my output is not stacked on top of
   `primary_identity_fix`'s 183k changes (which the user described as
   based on "OLD soft-category logic"). The auditor agent reviewing that
   prior pass concurrently can compare its findings against my changelog
   to see the disagreement set.

## My honest verdict

This pass is a **net improvement** — it makes ~19k changes that are 50–70%
correct, against the alternative of zero changes (where 100k+ products
would still be in known-bad categories). But it is **not a finished
product**. The strict-precision number means 1 in 2 changes is wrong or
weak in the worst light. The right way to use this is:

1. Treat `category_first_changelog.csv` as a review queue, not an
   auto-merge.
2. Use `category_first_new_leaves.csv` to drive ESHA tree expansion —
   the categories listed above are where new leaves are most needed.
3. Run a separate **tree-integrity pass** to detect codes whose
   description disagrees with their cohort majority (the kimchi/loaf
   problem). That will unlock the next batch of fixes.
4. Do not run this script repeatedly without resetting to baseline —
   each run shifts cohort majorities slightly, and the system was
   designed to compute cohorts from baseline once.
