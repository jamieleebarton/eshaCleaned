# OMAD & Single-Person Meal Planning in Hestia

> **Status:** Brainstorm / feasibility analysis  
> **Scope:** Using the existing `planner/` (Hestia) for one-meal-a-day (OMAD) diets within a family context, and for single-person households that eat differently from the family.  
> **Date:** 2026-05-10

---

## 1. What the user is asking for

- **Family context:** Most household members eat breakfast, lunch, and dinner normally.
- **The outlier:** One (or more) people skip breakfast (and possibly lunch) and eat only once per day.
- **The tension:** Can the planner handle a person who needs their **entire daily calorie load in a single meal** while everyone else at the same table eats a normal-sized dinner?
- **Secondary question:** Can a single-person household run the planner at all, and could they toggle "attendance" on/off per meal?

---

## 2. What already works (no code changes required)

### 2.1 Single-person households

`HouseholdConfig.single_person()` already exists. The beam-search planner, dynamic servings, and leftover logic all adapt to household size. `MAX_LEFTOVERS` even doubles for single-person runs.

```python
# From planner/hestia/data_structures.py
class HouseholdConfig:
    @classmethod
    def single_person(cls, calories: float = 2000, protein: float = 50) -> "HouseholdConfig":
        return cls(people=[PersonProfile("Adult", calories, protein)])
```

A true OMAD *single-person* plan is therefore mechanically possible today: define one person, set their meal ratios to `0.0 / 0.0 / 1.0`, and skip all breakfast and lunch slots via `AttendanceSchedule` overrides. The planner will generate 7 dinner slots and try to hit a full week’s calories across only those 7 meals.

### 2.2 Skipping individual meals

`AttendanceSchedule` supports `slot_overrides` that drop `headcount` to zero for any of the 21 weekly slots:

```json
{
  "0": {"headcount": 0, "note": "No breakfast Monday"},
  "1": {"headcount": 0, "note": "No lunch Monday"}
}
```

When `headcount == 0`, the slot calorie target becomes `0.0` and the planner simply does not cook for that slot.

### 2.3 Per-person meal ratios

`PersonProfile` carries `breakfast_ratio`, `lunch_ratio`, `dinner_ratio` (defaults 0.25 / 0.35 / 0.40). These flow into `HouseholdConfig.meal_calories(meal_idx)`, which sums each person’s contribution per meal type.

---

## 3. The hard problem: OMAD inside a family dinner

The friction is **not** attendance or weekly targets. It is **recipe sizing** at the dinner table.

### 3.1 Two calorie-split systems that don’t talk to each other

| Layer | Controls | Default dinner assumption |
|-------|----------|---------------------------|
| `PersonProfile` / `AttendanceSchedule` | Weekly nutrition targets, per-slot calorie budgets | Dinner = 40 % of daily calories |
| `ScoringConfig` / `_compute_dynamic_servings` | How many servings to batch-cook, how big a "serving" feels | Dinner = 30 % of daily calories, main = 70 % of that = **~420 cal per serving** |

If you set the OMAD person to `dinner_ratio = 1.0`, the attendance schedule correctly computes:

```
3 normal eaters × 800 cal  = 2,400 cal
1 OMAD eater    × 2,000 cal = 2,000 cal
─────────────────────────────────────
Total dinner slot target    = 4,400 cal
```

But the recipe engine still sizes dinner mains for `2,000 × 0.30 × 0.70 = 420 cal` per serving. A recipe with 4,200 total calories therefore gets `4,200 / 420 = 10` dynamic servings. At a table of four, each person receives `10 / 4 = 2.5` servings = **1,050 calories**.

That is fine for the normal eaters (they needed ~800). It is **half** of what the OMAD person needs.

### 3.2 Why dynamic servings don’t save us

`_compute_dynamic_servings` in `sparse_cascade.py` normalizes every recipe to a fixed per-person calorie target. It does not know that one chair at the table needs 2.5× the calories of the other chairs. It treats all heads equally.

The result: the planner will pick a recipe, scale it to ~1,050 cal/person, and declare the slot nutritionally satisfied because the **aggregate** calories roughly match the attendance target. But the OMAD person is under-fed.

---

## 4. Brainstormed implementation paths

### Path A: Calorie-consolidation override ("roll skipped meals into dinner")

**Concept:** When a person skips breakfast and lunch, don’t just zero those slots out. Roll the skipped calories forward into the next attended slot (dinner).

**Where to touch:**
- `AttendanceSchedule._apply_overrides()` — add a `consolidate_skipped: true` flag.
- When processing overrides, accumulate skipped calories/protein into the nearest later slot for that person.

**Pros:**
- Keeps the attendance metaphor intact.
- The dinner slot target naturally becomes 4,400+ calories.

**Cons:**
- Does not fix recipe sizing. The `ScoringConfig` layer still targets 420-cal servings, so the planner will still pick recipes that deliver ~1,050 cal/person and think it is done.
- Requires coordination with `ScoringConfig` to avoid a mismatch between "slot needs 4,400 cal" and "recipe sized for 2,400 cal."

**Verdict:** Needs a companion change in `ScoringConfig` to be useful.

---

### Path B: Per-person portion multiplier (recommended)

**Concept:** Add `portion_multiplier: float = 1.0` to `PersonProfile`. At dinner the OMAD person has `portion_multiplier = 2.5`. The attendance schedule stops using a naive `headcount / household_size` ratio and instead **sums each present person’s individual calorie need**.

**Where to touch:**
1. `PersonProfile` — add `portion_multiplier: float = 1.0`.
2. `HouseholdConfig.meal_calories(meal_idx)` — already sums per-person; no change needed if `PersonProfile.meal_calories()` respects the multiplier.
3. `AttendanceSchedule._apply_overrides()` — currently:
   ```python
   ratio = headcount / self.household.size
   cal_target = self.household.meal_calories(meal_idx) * ratio
   ```
   Replace with:
   ```python
   cal_target = sum(p.meal_calories(meal_idx) * p.portion_multiplier
                    for p in present_people)
   ```
4. `ScoringConfig` — optionally add `meal_cal_split_override: Dict[int, float]` so that when dinner targets are anomalously high, the recipe engine sizes mains for 1,000+ cal instead of 420.

**Pros:**
- Minimal conceptual weight. A "multiplier" is easy to explain in UI copy.
- Works for any partial-attendance scenario (e.g., a teenager who eats double portions, a toddler who eats half).
- Keeps the existing 21-slot structure untouched.

**Cons:**
- Still requires `ScoringConfig` awareness if you want the recipe engine to pick *bigger* recipes rather than just *more servings* of normal-sized recipes.

**Verdict:** Best balance of power and simplicity.

---

### Path C: Dual-plan merge

**Concept:** Run the planner twice:
- Plan 1: 3-person family, normal 21-slot week.
- Plan 2: 1-person OMAD, 7-slot week (only dinners, each slot target = 2,000 cal).
- Merge the two shopping lists and pantry states.

**Where to touch:**
- A new wrapper script that runs two `SparseCascadePlanningSession`s and concatenates outputs.
- Pantry deduplication logic so that shared ingredients (e.g., rice, oil) are not double-purchased.

**Pros:**
- Zero changes to core planner math. The OMAD plan gets its own `ScoringConfig` with `meal_cal_split_dinner = 1.0`.
- Very safe; no risk of breaking existing family plans.

**Cons:**
- Leftover pools are separate. The OMAD person cannot eat family leftovers, and vice versa.
- Merge logic is non-trivial (shared pantry, shared cooldowns, deduplicated grocery list).
- Does not reflect the reality of *one* dinner being cooked in *one* pot.

**Verdict:** Good for a prototype, bad for long-term UX.

---

### Path D: OMAD plate template

**Concept:** Create a new meal type (or template) called `omd_dinner` that is structurally "breakfast + lunch + dinner" combined — a large main, two substantial sides, and a fruit/dairy component. The person still eats at slot 2/5/8/etc. (dinner time), but the template allows a much larger plate.

**Where to touch:**
- `planner/assets/plate_templates_v2/dinner.json` — add `omd_dinner` templates.
- `ScoringConfig` — add an `omd_mode: bool` that relaxes `max_one_starchy_side`, raises calorie ceilings, and disables the "this recipe is too big" filter.

**Pros:**
- Very explicit. The plan output literally says "OMAD plate" so there is no confusion.
- Template constraints keep the meal nutritionally balanced even at 2,000 calories.

**Cons:**
- Requires template authoring (non-trivial).
- Does not solve the dynamic-servings sizing issue by itself; the recipe engine still needs to know to target ~1,400-cal mains instead of 420-cal mains.

**Verdict:** Complementary to Path B, not a replacement.

---

### Path E: High-leftover "grazing" model (not true OMAD)

**Concept:** The person skips breakfast and lunch slots via attendance, but the family dinner is batch-cooked aggressively (`leftover_pct_target = 0.9`). The person eats leftovers from the fridge for their skipped meals.

**Where to touch:**
- Attendance overrides only.
- Possibly add a `force_leftover_consumption` rule that auto-fills skipped slots from the leftover pool.

**Pros:**
- Closest to how real families actually handle this ("there’s chili in the fridge, eat that").
- No need to supersize dinner.

**Cons:**
- Not actually OMAD. The person is eating 2–3 times per day, just not at the table with the family.
- Leftovers are tracked as aggregate servings, not assigned to individuals. The planner might consume leftovers at lunch instead of breakfast, or not at all.

**Verdict:** Useful feature, but it is a different product promise than OMAD.

---

## 5. The simplest viable MVP

If we wanted to ship something tomorrow, the minimal viable change is:

1. **Add `portion_multiplier` to `PersonProfile`.**
2. **Fix `AttendanceSchedule` to sum individual targets when `people` is specified.**
3. **Add a `meal_cal_override` dict to `ScoringConfig`** so that specific slots can use custom `meal_cal_split` values.

Example config for a 4-person household with one OMAD member:

```python
household = HouseholdConfig(people=[
    PersonProfile("Adult A", 2000, 50),
    PersonProfile("Adult B", 2000, 50),
    PersonProfile("Child",  1800, 40),
    PersonProfile("OMAD",   2000, 50,
                  breakfast_ratio=0.0,
                  lunch_ratio=0.0,
                  dinner_ratio=1.0,
                  portion_multiplier=2.5),  # Needs 2×+ calories at dinner
])

# Attendance: OMAD excluded from B/L, included at dinner
overrides = {
    **{s: {"people": ["Adult A", "Adult B", "Child"]} for s in BREAKFAST_SLOTS + LUNCH_SLOTS},
    # Dinner uses default (everyone present)
}

config = ScoringConfig.balanced(
    meal_cal_override={slot: 0.80 for slot in DINNER_SLOTS}  # Size dinner mains for ~1,600 cal
)
```

This would not be perfect — the recipe engine would still average across all four eaters — but it would get dramatically closer than the status quo.

---

## 6. Open questions

1. **Does the user want *true* OMAD (one 2,000-cal meal) or *skipping breakfast* (eat leftovers later)?** These are different engineering problems.
2. **Is this for a configurable UI toggle, or a one-off research script?** If it is UI-facing, `portion_multiplier` is a better abstraction than `meal_cal_override` because it maps to a human concept ("I eat more / less").
3. **How should nutrition compliance be reported?** If one person gets 200 % of daily fat at dinner and 0 % at breakfast, the weekly aggregate still looks fine, but the daily distribution is spiky. Do we care?
4. **Leftover math:** If dinner is now 4,400 calories and 4 people eat, there may be zero leftovers. Does the OMAD person *want* leftovers, or is the entire point that dinner is the only meal?

---

## 7. Related files in the repo

| File | Relevance |
|------|-----------|
| `planner/hestia/data_structures.py` | `PersonProfile`, `HouseholdConfig`, `AttendanceSchedule`, `SlotAttendance` |
| `planner/hestia/scoring_config.py` | `ScoringConfig`, `get_slot_cal_target()`, `meal_cal_split_*` |
| `planner/hestia/sparse_cascade.py` | `_compute_dynamic_servings()`, candidate filtering, nutrition scoring |
| `planner/hestia/plate_builder.py` | `PlateBuilder`, template constraints |
| `planner/assets/plate_templates_v2/` | JSON templates defining what a valid breakfast/lunch/dinner looks like |
| `planner/scripts/run_htc_week.py` | Entry point for running a single week; good place to test overrides |

---

## 8. Next step recommendation

If the team wants to pursue this, the **fastest path to a working demo** is:

1. Create a branch.
2. Add `portion_multiplier` to `PersonProfile` and update `AttendanceSchedule._apply_overrides()` to sum present-people calories instead of using `headcount / household_size`.
3. Write a smoke-test script in `planner/scripts/` that runs a 4-person household with one OMAD member and prints the per-slot calorie targets.
4. Verify that dinner slot targets are ~4,400 cal and that the planner does not immediately crash.
5. Only then decide whether `ScoringConfig` needs a `meal_cal_override` or whether the existing dynamic-servings math is "close enough."

This is a low-risk, high-information first move.
