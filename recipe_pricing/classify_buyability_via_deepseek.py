#!/usr/bin/env python3
"""Classify each ingredient line of each recipe in the test pack via DeepSeek.

For each (recipe, line), the model returns:
  - buyability: enum
  - canonical_buy_form: cleanest shopping-list form (or null)
  - base_ingredients: list of upstream ingredients (for derivative/alternation)
  - rationale: short reason

The model SEES title, all ingredient lines, AND recipe steps so it can
distinguish e.g. `lobster shells` derived from "1 whole lobster, cooked"
versus `lobster shells` listed as a from-scratch buy.

Inputs:
  recipe_pricing/buyability_testpack.jsonl  (one recipe per line)

Outputs:
  recipe_pricing/buyability_testpack_results.jsonl  (one recipe per line w/ classifications)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "recipe_pricing" / "buyability_testpack.jsonl"
DEFAULT_OUT = ROOT / "recipe_pricing" / "buyability_testpack_results.jsonl"

MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com/v1/"


SYSTEM = """You are an ingredient resolver for Hestia, a recipe-planning system.

CONTEXT — what we're building:
  Hestia stores recipes as canonical, generic foods (e.g. `mayonnaise`, not
  `Hellmann's fat-free mayonnaise`). At plan time we project the user's own
  preferences (organic, fat-free, vegan, low-sodium, gluten-free, etc.) onto
  each canonical ingredient, look up real Walmart/Kroger products, and
  compute total recipe cost AND total recipe macros (kcal, protein, fat,
  carbs, fiber, sodium, etc.). One canonical recipe → many personalized
  realizations for many users.

  This means every ingredient line must satisfy TWO requirements:
    1. **Purchaseable** — there is a real shopping-list item the user
       can put in cart at a normal grocery (or a clear specialty/derivative
       fallback).
    2. **Calculable** — the canonical_buy_form must be SPECIFIC ENOUGH
       that we can look up grams-per-unit, kcal/100g, fat/100g, and price.
       "noodles" or "cheese" alone is NOT calculable — `rice noodles`,
       `ricotta cheese`, `shredded cheddar` are. Use the recipe context
       (title, cuisine, other ingredients, steps) to RESOLVE ambiguous bare
       nouns into a specific food whenever possible.

We separate adjectives into three buckets at planning time:
  - User-preference facets (claims) — organic, fat-free, low-sodium,
    gluten-free, vegan, kosher, halal, cage-free, grass-fed. These get
    STRIPPED from canonical_buy_form (they project at runtime per user).
  - Culinary form/processing — chopped, sliced, drained, fresh, frozen,
    cooked, raw. These describe prep, NOT identity. They get stripped too
    (recipe steps already capture "chopped").
  - Identity-changing modifiers — smoked paprika ≠ paprika, evaporated
    milk ≠ milk, brown sugar ≠ sugar, light brown sugar ≠ brown sugar,
    extra-virgin olive oil ≠ olive oil. These STAY in canonical_buy_form.

For your job:
  - canonical_buy_form must correspond to a REAL SKU — a single product
    a shopper could scan at checkout, with a UPC, a price tag, and a
    Nutrition Facts panel. The test is:
      "could you put exactly this thing in your cart and walk out
       of Walmart with it?"
    `nuts` does NOT pass — there is no "nuts" SKU. `walnut halves` passes.
    `cheese` does NOT pass — there is no "cheese" SKU. `shredded cheddar`
    passes. `bread` does NOT pass — there is no generic "bread" SKU.
    `white sandwich bread` passes.

  - Strip preference facets, strip pure form/processing adjectives, KEEP
    identity-changing modifiers, RESOLVE ambiguous bare nouns from RECIPE
    CONTEXT (cuisine, title, dish type, other ingredients, steps).

  - When recipe context allows even a soft inference, MAKE THE CALL.
    Cuisine or dish-type alone is enough — be confident:
      "1 cup nuts, chopped" in an American cake → 'walnuts' (American
        cake/cookie tradition uses walnuts or pecans; pick walnuts.)
        identity_resolved=true
      "1 cup nuts" in baklava → 'pistachios' (Mediterranean pastry tradition)
      "1 cup nuts" in pad thai → 'peanuts' (Thai cuisine cue)
      "1 lb pasta" in beef stroganoff → 'egg noodles' (American comfort food cue)
      "1 lb pasta" in carbonara → 'spaghetti' (Italian classic cue)
      "1 cup cheese, grated" in lasagna → 'mozzarella cheese' (lasagna canonical cheese)
      "1 cup wine" in coq au vin → 'red wine' (French cuisine cue)
      "1 cup vinegar" in American bean salad → 'distilled white vinegar'

  - **DEFAULT ASSUMPTION: every recipe carries enough context to pick a
    specific SKU.** The title alone is usually enough cue. The dish type
    is enough. The cuisine is enough. Other ingredients are enough.
    Cooking method is enough. Combine all of these to make a confident
    call. Examples of what counts as a cue:
      - Title says "Chicken Pepperoni Pasta" → it's American/Italian-American
        pepperoni pasta. Pepperoni pastas are typically penne or rigatoni.
        Pick `penne` (or `rigatoni`) — title is sufficient cue.
      - Recipe is a fruitcake with "wine" — traditional fruitcake uses
        sweet wines (sherry, port, or sweet red). Pick `port wine` or
        `sweet sherry`.
      - Recipe is generic American dessert with "nuts" → walnuts/pecans.
        Pick `walnut halves`.

  - identity_resolved=false should be VERY RARE — reserve it for cases
    where the recipe is so devoid of context (no informative title, no
    dish type cue, no relevant other ingredients, no cuisine signal) that
    ANY confident inference would be a coin flip. If you find yourself
    writing a rationale like "ambiguous; no cuisine cue given" but the
    recipe title is informative, GO BACK and use the title.

  - The shopper has to put SOMETHING in cart. We must commit to a SKU.

  - Two distinct kinds of "bare noun":

    A) FACET-BARE — bareness IS the canonical identity. Variants are
       user-preference facets that get projected at planner runtime
       (organic, low-fat, unsalted, etc.). LEAVE THESE BARE. Do NOT
       bake the user's facet preference into canonical_buy_form.
       Examples (all stay bare):
         milk          (whole/2%/skim/lactose-free are user facets)
         butter        (salted/unsalted is a user facet)
         sugar         (white sugar IS the canonical; brown sugar /
                        powdered sugar are SEPARATE canonical foods)
         oil           (vegetable oil is the implicit canonical;
                        olive oil / coconut oil are SEPARATE canonical
                        foods that the recipe must name explicitly)
         eggs          (large/medium/free-range are user facets)
         salt
         flour         (all-purpose is implicit canonical; bread /
                        cake / whole-wheat / gluten-free are separate)

    B) IDENTITY-BARE — different KINDS are materially different foods
       with different macros, cooking behavior, and prices. Cannot be
       collapsed into one canonical. Try to resolve from recipe context
       (cuisine, title, steps, other ingredients). If you can resolve
       confidently, set identity_resolved=true. If the recipe gives no
       kind hint, leave the bare noun as canonical_buy_form AND set
       identity_resolved=false — DO NOT GUESS A DEFAULT.
       Common identity-bare items:
         bread     (white / whole wheat / sourdough / rye / brioche / ...)
         noodles   (egg / rice / udon / ramen / soba / chow mein / ...)
         pasta     (spaghetti / penne / linguine / fettuccine / ...)
         cheese    (cheddar / mozzarella / parmesan / ricotta / feta / ...)
         rice      (white / brown / jasmine / basmati / arborio / wild / ...)
         broth     (chicken / beef / vegetable / fish / mushroom)
         stock     (same set as broth)
         wine      (red / white / dry / sweet / cooking / specific varietals)
         vinegar   (white / apple cider / red wine / balsamic / rice / ...)
         nuts      (walnuts / pecans / almonds / cashews / mixed)
         beans     (black / pinto / kidney / cannellini / navy / ...)
         greens    (spinach / kale / collard / arugula / romaine / mix)

    For identity-bare items, recipe context examples:
      "noodles" in pad thai → 'rice noodles' (cuisine cue), identity_resolved=true
      "noodles" in beef stroganoff → 'egg noodles' (American cue), identity_resolved=true
      "noodles, cooked" in a generic American casserole → 'egg noodles'
        (the casserole context is enough — pick egg noodles), identity_resolved=true
      "bread, cubed" in French toast → 'white sandwich bread' (dish type cue), identity_resolved=true
      "bread, cubed" in stuffing → 'white sandwich bread' or 'sourdough bread' depending on
        the rest of the recipe, identity_resolved=true
      "cheese, grated" in lasagna → 'mozzarella cheese' (canonical lasagna cheese)
      "cheese, for topping" on a chili → 'shredded cheddar cheese' (American chili cue)
      "1 cup nuts" in a brownie recipe → 'walnut halves' (brownie tradition)
      "1 cup nuts" with TRULY no recipe context (rare) → 'nuts', identity_resolved=false

  - Identity-changing modifiers always STAY in canonical_buy_form:
    smoked paprika ≠ paprika, brown sugar ≠ sugar, evaporated milk ≠ milk,
    extra-virgin olive oil ≠ olive oil, kosher salt is its own identity, etc.

  - Other examples:
    "1 cup fat-free organic mayonnaise" → buy='mayonnaise', identity_resolved=true
    "2 cups smoked paprika"             → buy='smoked paprika', identity_resolved=true
    "1 cup brown sugar"                 → buy='brown sugar', identity_resolved=true
    "1 cup sugar"                       → buy='sugar', identity_resolved=true (facet-bare)
    "1 cup milk"                        → buy='milk', identity_resolved=true (facet-bare)
    "1 cup mixed vegetables" in a stir-fry → buy='frozen stir-fry vegetable blend', identity_resolved=true

You receive a recipe (title, ingredient lines, and cooking steps), classify
EACH ingredient line and return the cleanest, most calculable shopping-list
form for it.

For each ingredient line, choose ONE buyability label:

  buyable
      A NORMAL MAINSTREAM grocery store (Walmart, Kroger, Target, Whole
      Foods, Trader Joe's) sells this exact thing. The shopper can put it
      on the shopping list and walk out of a typical supermarket with it.
      Examples: "frozen corn", "ketchup", "chicken breast", "lemon juice",
      "white wine vinegar".

      NOT buyable just because some specialty market or fishmonger MIGHT
      have it (e.g., bare lobster shells, fish heads, raw bones, animal
      organs not commonly stocked) — those are 'specialty' or 'unbuyable'.

  derivative
      Made from other ingredients DURING THIS recipe. Examples: "egg wash"
      (made from eggs already in the recipe), "simple syrup" (made from sugar
      and water), "lobster shells" (a byproduct of cooking the whole lobster
      that appears earlier in the ingredients), "reserved pasta water",
      "browned butter". Mark base_ingredients with the upstream items they
      come from. Look at the steps to confirm.

  alternation
      The author offered "X or Y or Z". Apply this priority order to pick
      canonical_buy_form:
        1. First, eliminate any option that is NOT acquireable (not sold
           in any store, not a derivative, not a specialty market item).
        2. Among the remaining options, prefer mainstream-buyable over
           specialty.
        3. Among mainstream-buyable options, pick the FIRST listed.
      base_ingredients lists the OTHER options that were offered — do NOT
      include the chosen one.
      Examples:
        "lemon juice or lime juice" → buy='lemon juice', base=['lime juice']
        "crawfish or shrimp"        → buy='crawfish', base=['shrimp']
        "fresh or frozen blueberries" → buy='fresh blueberries', base=['frozen blueberries']
        "lobster shells or chicken thighs" (shells unbuyable, thighs buyable)
            → buy='chicken thighs', base=['lobster shells']
      If NONE of the options are acquireable, do NOT use alternation —
      classify as 'unbuyable' instead.

  unbuyable
      The ingredient cannot be acquired from a mainstream grocery, AND
      cannot be derived from any earlier ingredient in this recipe.
      Mainstream grocery is Walmart/Kroger/Target — NOT specialty
      fishmongers, ethnic markets, or "your friend the chef." If a typical
      Walmart shopper has no realistic path to this ingredient, flag it.
      canonical_buy_form null, base_ingredients may list what was offered.
      Examples:
        "uncooked lobster shells or cooked lobster shells" (recipe has no
            upstream whole lobster) — bare shells are not on any normal
            grocery shelf; user has no path to acquire them.
        "fresh deer liver" (recipe has no upstream deer) — not at any
            mainstream grocery, not a recipe byproduct.
      We surface these so the planner can flag the recipe as
      un-fulfillable rather than guess.

  specialty
      Real food but NOT at a typical supermarket — needs a specialty market
      (e.g. "lobster roe", "live maine lobsters", "duck fat", "yuzu").
      canonical_buy_form may be null OR the closest mainstream equivalent.

  nonsense
      Author quirk that doesn't define a single ingredient
      (e.g. "turkey, chicken, veal, or lobster"). canonical_buy_form null.

For canonical_buy_form:
  - Resolve ambiguous bare nouns using recipe context. If the recipe is pad
    thai and an ingredient line says "noodles", canonical_buy_form is
    "rice noodles". If the recipe is lasagna and a line says "cheese", pick
    the specific cheese the steps describe (e.g. "ricotta cheese").
  - Strip brand prefixes (Hellmann's mayonnaise → mayonnaise) UNLESS the
    brand is the identity (Tabasco sauce stays).
  - Translate regional vocab (courgette → zucchini, aubergine → eggplant).
  - For "1% milk", "2% milk", "unsalted butter": the canonical_buy_form
    is the form a shopper would actually pick off the shelf (those exact
    forms; do NOT generalize to "milk" / "butter").
  - For derivative items, canonical_buy_form is null.

For the `usage` field — orthogonal to buyability — classify how the
ingredient is used in this recipe. The planner uses this to decide whether
to count the ingredient toward total macros/cost or to skip the calculation:

  core
      Standard recipe ingredient that counts toward calculation. The
      author specified a real quantity that is part of the dish. Default.

  garnish
      "for garnish", "for serving", "for topping", "for sprinkling",
      "for decoration", "to drizzle on top". Identify and shop, but
      do NOT calculate macros/cost precisely (the quantity is
      decorative/flexible).
      Examples:
        "Cilantro, snipped fresh, for garnish"
        "Lime wedges, for serving"
        "Parmesan, for sprinkling"
        "Olive oil, for drizzling"

  to_taste
      "salt to taste", "pepper as needed", "oil for frying", "flour
      for dusting". Quantity is undefined or method-dependent. Identify
      but skip quantity calculation.
      Examples:
        "Salt, to taste"
        "Vegetable oil, for frying"
        "All-purpose flour, for dusting work surface"

  optional
      Author marked the ingredient with "(optional)". The user may skip
      it; planner should surface as a choice.
      Examples:
        "1 tablespoon cumin (optional)"
        "Salmon caviar, for topping (optional)" → usage='optional'
            (the (optional) takes precedence over "for topping")

Output JSON ONLY in the schema:
{
  "classifications": [
    {
      "line_index": <int>,
      "buyability": "buyable" | "derivative" | "alternation" | "specialty" | "unbuyable" | "nonsense",
      "canonical_buy_form": <string or null>,
      "identity_resolved": <bool — true if canonical_buy_form is specific
                            enough to calculate macros (or is a facet-bare
                            canonical like 'milk'/'sugar'/'butter');
                            false if the bare noun is identity-ambiguous
                            (bread/noodles/cheese/rice with no cue)>,
      "base_ingredients": [<string>, ...],
      "usage": "core" | "garnish" | "to_taste" | "optional",
      "rationale": "<≤ 20 words>"
    }
  ]
}

Return EXACTLY one classification per ingredient line, in the original line_index order.
"""


def build_user_message(recipe: dict) -> str:
    lines = [f"Recipe: {recipe['title']}", "", "Ingredients:"]
    for ing in recipe["ingredients"]:
        lines.append(f"  [{ing['line_index']}] {ing['display']}  (item: {ing['item']})")
    lines += ["", "Steps:"]
    for i, step in enumerate(recipe["steps"]):
        lines.append(f"  {i+1}. {step}")
    return "\n".join(lines)


async def classify_one(client: AsyncOpenAI, sem: asyncio.Semaphore,
                       recipe: dict, max_retries: int = 4) -> dict:
    """Classify one recipe with exponential-backoff retries on transient
    failures (rate limits, timeouts, connection errors, malformed JSON)."""
    async with sem:
        last_err = None
        for attempt in range(max_retries):
            try:
                resp = await client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": build_user_message(recipe)},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    max_tokens=4000,
                    timeout=120,
                )
                raw = resp.choices[0].message.content or "{}"
                data = json.loads(raw)
                cls = data.get("classifications", [])
                # Sanity: should be a list, ideally with one entry per ingredient
                if not isinstance(cls, list):
                    raise ValueError(f"classifications not a list: {type(cls)}")
                return {**recipe, "classifications": cls, "error": None}
            except Exception as exc:
                last_err = str(exc)
                if attempt < max_retries - 1:
                    backoff = 2 ** attempt + (attempt * 0.5)
                    await asyncio.sleep(backoff)
        return {**recipe, "classifications": [], "error": last_err}


async def main_async(args) -> int:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY not set")

    # Resume: skip recipes already classified in the output file
    already_done: set = set()
    if args.output.exists() and args.resume:
        with args.output.open() as f:
            for line in f:
                try:
                    already_done.add(json.loads(line).get("recipe_id"))
                except Exception:
                    pass
        print(f"resume: {len(already_done):,} recipes already classified", file=sys.stderr)

    recipes = []
    with args.input.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("recipe_id") in already_done:
                continue
            recipes.append(r)
    print(f"to classify: {len(recipes):,} recipes", file=sys.stderr)
    if not recipes:
        return 0

    client = AsyncOpenAI(api_key=api_key, base_url=BASE_URL)
    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.time()
    tasks = [classify_one(client, sem, r) for r in recipes]
    done = 0
    n_err = 0
    mode = "a" if args.resume else "w"
    with args.output.open(mode) as f:
        for coro in asyncio.as_completed(tasks):
            result = await coro
            done += 1
            if result.get("error"):
                n_err += 1
            f.write(json.dumps(result) + "\n")
            f.flush()
            if done % 250 == 0 or done == len(recipes):
                rate = done / max(time.time() - t0, 1)
                eta = (len(recipes) - done) / max(rate, 0.01) / 60
                print(f"  {done:>7,}/{len(recipes):,} "
                      f"({rate:.1f}/s, errors={n_err}, ETA {eta:.0f}min)",
                      file=sys.stderr)

    print(f"\ndone in {(time.time()-t0)/60:.1f}min; errors: {n_err}", file=sys.stderr)
    print(f"  → {args.output}", file=sys.stderr)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=DEFAULT_IN)
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--resume", action="store_true",
                   help="skip recipes already in output (append mode)")
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
