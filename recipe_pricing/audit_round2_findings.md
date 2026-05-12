# Round-2 audit findings

5 audits ran on the post-round-1 corpus (489K recipes, $77.61/wk planner baseline).

## Summary table

| Audit | Result | Action |
|---|---|---|
| **A1** Unit conversions | 100 (ingredient, unit) pairs outside ±20% tolerance — most are Hestia's portion table being wrong (oats, salad greens, cream) NOT us. **One real OUR bug: whipped cream.** | Fix whipped cream; spot-check 2-3 borderline cases |
| **A2** Empty grams | 58 silently-zeroed lines across 4.7M (0.001%). Effectively clean. | Accept |
| **A3** Cal reconstruction | **63,896 OFF_2X_LOW + 2,671 OFF_2X_HIGH**. Top recipes are absurd (30 kg of ground beef, 30 kg of butter). Same parenthetical-grams bug as round 1, broader triggers. | **Generalize the gram fix** |
| **A4** Food groups | 47.5% dominant-group agreement. **The audit's HTC→group mapping is incomplete** (fruits collapsed into vegetables; eggs missing; etc.). | Refine the mapping; re-run |
| **A5** FNDDS code agreement | **99.0% family-level, 92.9% exact match.** Hestia's per-recipe FNDDS attribution is reliable as ground truth. | Accept |

---

## A3 — the big one (calorie reconstruction)

**Pattern:** `grams_source == "range_lower_bound"` + `grams_resolved` is many times `grams_blob`. Last round we patched the "(N per pound)" variant for 87 recipes. The full pattern is broader:

- `"1 lb ground beef (80-85% lean)"` → qty=80, unit=lb, grams=80×453=36,320 g (true: 454g)
- `"3/4 lb butter, softened to 65–70°F"` → qty=65, grams=29,466 g (true: 340g)
- `"2/3 cup water (110 to 115 degrees F)"` → qty=110, grams=26,070 g (true: 158g)
- `"1 cup hot water (110-120°F)"` → qty=110, grams=26,400 g (true: 240g)
- `"1 1/2 cups fresh lime juice (about 8–10 limes)"` → qty=8, grams=1,920 g (true: 360g)
- `"1 lb ground beef (15–22% fat)"` → qty=15, grams=6,810 g (true: 454g)

In every case, **`grams_blob` already has the correct value**. The fix is identical to last round, just with a more general predicate.

**Scope:** ~1,417 lines in `recipes_unified.csv` have `grams_resolved > grams_blob × 5` with `grams_source == "range_lower_bound"`. ~95% of A3's `OFF_2X_HIGH` recipes will resolve once we patch these.

**Proposed fix:** generalize `fix_per_pound_parenthetical_grams.py` to a broader predicate. Drop the per-pound regex, just check `range_lower_bound` + ratio threshold.

---

## A1 — unit conversions

Top divergences ranked by gram-delta-kg total:

| Ingredient | Unit | n | our g/cup | hes g/cup | Verdict |
|---|---|---|---|---|---|
| rolled oats | cup | 2683 | ~85 | ~240 | **We're right** (dry oats ≈ 80g/cup; FNDDS treats it as cooked) |
| oatmeal | cup | 1228 | ~85 | ~240 | Same — depends on intent. Most recipes mean dry. |
| rhubarb | cup | 773 | ~117 | ~240 | Marginal. 1 cup chopped rhubarb ≈ 122g; we're closer. |
| milk | cup | 36305 | 240 | 244 | Tiny — accept |
| brown sugar | cup | 22547 | 200 | 220 | Tiny — accept |
| **whipped cream** | cup | **495** | **240** | **40** | **WE'RE WRONG** — whipped cream is mostly air, ~40g/cup |
| light cream | cup | 1018 | 240 | 135 | We're right (cream is liquid at ~240g/cup) |
| mixed salad greens | cup | 207 | 30 | 135 | **We're right** (raw greens) |
| coleslaw mix | cup | 231 | 65 | 220 | We're right |
| ice / ice cubes | cup | 1658 | ~150 | ~240 | Both wrong-ish (ice is ~120g/cup); minor |

**Real OUR bug count: 1 ingredient (whipped cream, 495 lines)**. Everything else is either a tie or a Hestia-portion-table bug we don't need to chase.

**Proposed fix:** override `whipped cream` → 40g/cup in our parser table (1 line of data).

---

## A4 — food groups

47.5% agreement is alarming, but **the audit's HTC→group mapping is the problem**, not the data. Specifically:

- Fruits collapsed into vegetables (HTC `60-69` is vegetables, but USDA fruits also start with `6x` — overlap).
- Eggs not separately mapped.
- Sugar/condiments mapped to "other" but Hestia maps some sugars under fats.

The samples confirm:
- `"Brown Bag Apple Salad"` → we say vegetables, Hestia says protein. Apple is a fruit; calling it veg is the audit's bug.
- `"Anzac Biscuits"` → we say dairy, Hestia says grains. Biscuits should be grains; our audit weighs the butter heavier than the flour.

**Proposed action:** re-run A4 with a refined HTC→group mapping (or import Hestia's `_classify_fndds_code` from `sparse_cascade.py` as ground truth). **Defer to round 3** — not a real data bug, just a meta-bug in the audit.

---

## A5 — FNDDS agreement

**99% family-level agreement, 92.9% exact-code agreement.** Top disagreements are within-family (e.g. `94303339` table salt vs `94302047` salt — both family `94`). This validates Hestia's FNDDS attribution as a reasonable ground truth for our work.

A few cross-family disagreements exist (e.g. `kosher salt, to taste` → Hestia attributes `64401057` vinegar instead of family `94`), but they're rare and Hestia-internal — not our bugs.

**Action:** accept.

---

## Recommended Phase 2 fix list

| # | Fix | Effort | Expected impact |
|---|---|---|---|
| **F1** | Generalize parenthetical-grams patch to all `range_lower_bound > 5×blob` cases | small | ~1,400 lines patched, ~2,500 recipes drop OFF_2X_HIGH flag, possible $/wk drop in regression |
| **F2** | Add `whipped cream` → 40g/cup override | tiny | 495 lines corrected (low cost-impact but identity-correct) |
| **F3** | Defer A4 (audit-side fix, not data fix) | n/a | n/a |

After applying F1+F2 → re-emit chain → re-run A3 + 12wk regression.
