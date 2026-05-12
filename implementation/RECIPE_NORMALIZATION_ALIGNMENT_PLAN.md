# Recipe Normalization Alignment Plan

This is the working agreement for the recipe-normalization prompt/test work.
It is written to keep recipe cleanup, product matching, and nutrition anchoring
separate.

## Current Status

Nebius has been run successfully on the targeted recipe fixture.

Real model output exists at:

- `implementation/output/recipe_normalization_nebius_candidate.jsonl`

Validator findings exist at:

- `implementation/output/recipe_normalization_nebius_candidate_findings.jsonl`

Current live result: 3 validation errors and 9 warnings on the first 9-recipe
targeted run. This is not passing yet.

Current fixture:

- `implementation/output/recipe_normalization_prompt_test_pack.jsonl`
- `implementation/output/recipe_normalization_prompt_test_pack_index.csv`
- 47 recipes
- 98 stressed lines
- 37 case types

Prompt draft:

- `implementation/RECIPE_NORMALIZATION_NEBIUS_PROMPT_DRAFT.md`

Validator:

- `implementation/validate_recipe_normalization_nebius_output.py`

Focused tests:

- `implementation/tests/test_recipe_normalization_prompt_fixtures.py`

Local test command:

```bash
python3 -m unittest implementation.tests.test_recipe_normalization_prompt_fixtures -v
```

Those tests do not prove Nebius follows the prompt. They prove the fixture and
validator are wired.

## Goal Of This Stage

Rewrite recipe ingredient lines and make them matchable.

The recipe LLM should convert messy recipe ingredient lines into cleaned
ingredient rewrites plus structured facts that can be matched later:

- cleaned ingredient rewrite,
- food/product identity,
- alternatives,
- components,
- state/form/storage,
- prep,
- brand removal plus brand meaning,
- section/role context,
- match blockers.

The rewrite is not cosmetic. It is the inspectable normalized ingredient line
that proves the model removed brand/personalization/parser noise while
preserving the facts needed for product matching.

This stage does not choose:

- ESHA code,
- SR28 code,
- FNDDS code,
- UPC/GTIN,
- retail product,
- final nutrition,
- final consumed grams for yield/process ingredients.

## Meaning Of Matchable

`MATCH_READY` means the recipe line is clean enough to send to product matching.
It does not mean nutrition is calculated.

Examples:

- `16-bean mix, dried` -> rewrite `dried 16-bean mix`; matchable identity `16-bean mix`, state `dried`.
- `6 cheese zesty Mexican cheese blend` -> rewrite `zesty Mexican cheese blend`; matchable identity `Mexican cheese blend`, variant/style preserved.
- `coconut milk` -> rewrite `coconut milk`; matchable identity `coconut milk`, not `milk`.
- `cream cheese` -> rewrite `cream cheese`; matchable identity `cream cheese`, not `cheese`.

`EQUIVALENT_ALTERNATIVES_CALC_READY` means the line gives choices, but the
recipe itself treats the options as interchangeable and they share the same
product family, form, role, and quantity.

Examples:

- `7 bean mix or 15 bean mix`

The output must preserve both choices, but it may calculate against the common
umbrella identity, such as `dried mixed bean soup mix`.

`BLOCKED_SELECTION_REQUIRED` means the line gives materially different choices.

Examples:

- `Monterey Jack cheese or Mexican blend cheese`
- `corn flakes, cracker crumbs, or extra cheddar cheese`

The output must contain all choices as matchable alternatives. It must not pick
one unless an explicit equivalent-alternatives policy applies.

The rewrite must also preserve the choice, for example `Monterey Jack cheese
OR Mexican cheese blend`, not a single selected ingredient. For equivalent
alternatives, the rewrite should show both the calculation umbrella and the
allowed choices, for example `dried mixed bean soup mix (7 bean mix OR 15 bean
mix)`.

`BLOCKED_CONTEXT_REQUIRED` means the text lacks identity needed for matching.

Examples:

- bare `100% bran`: cereal vs crude bran is unclear.
- bare `100% fruit juice`: fruit identity is missing unless generic juice is an accepted product-matching policy.

`EXCLUDED` means the line is not an ingredient.

Examples:

- bare `or`,
- dangling `cooked and`,
- skewers,
- foil,
- rocks,
- firewood.

`SECTION_HEADER` means the line is recipe structure, not a consumed ingredient.

Important: section headers are not garbage. `For sauce:` should be excluded as
an ingredient, but it must set section context for following real sauce
ingredients.

Example:

- `For sauce:` -> role `section_header`, section context `sauce`
- following `1 cup tomato sauce` -> real ingredient, section `sauce`, matchable as `tomato sauce`

## What The Prompt Should Fix Now

These are recipe-side failures. The LLM can directly fix or structure them.

1. True alternatives
   - Output an `alternative_group`.
   - If materially different, do not silently choose.
   - If equivalent variants, calculate against a common umbrella identity while preserving the alternatives.
   - Fixture examples: butter/margarine, walnuts/pecans, 7/15 bean mix, Monterey Jack/Mexican blend.

2. Multi-ingredient composites
   - Split real components.
   - Fixture examples: salt and pepper, juice and zest.

3. Display text hides options that parsed item lost
   - Trust the display line over weak parsed `item`.
   - Fixture example: parsed `topping`, display has corn flakes/cracker crumbs/cheddar.

4. Parenthetical examples
   - Preserve examples as evidence, variants, or alternatives.
   - Fixture examples: apples such as Granny Smith, orange liqueur such as Cointreau/Grand Marnier, bone-in chicken pieces such as thighs/drumsticks.

5. Optional/garnish/as-needed/to-taste/serving
   - Role-flag these.
   - Do not treat every line as normal base consumed mass.
   - Ordinary seasoning-to-taste with source grams should calculate using a
     visible default policy; process salt/oil/coating/garnish should not.
   - Fixture examples: garnish herbs, serving rice/bread/salsa, pasta-water salt.

6. Quantity/unit leakage
   - Quantity stays in quantity fields, not `machine_name`.
   - Validator checks this on all candidate output.

7. Missing or unusable quantity
   - Preserve available quantity.
   - If no usable quantity, emit blocker; do not invent.

8. Parser fragments
   - Exclude or block fragments.
   - Fixture examples: `or`, `cooked and`.

9. Section headers and recipe structure
   - Exclude header line as ingredient.
   - Preserve section context for following ingredients.
   - Fixture examples: `For sauce:`, `Topping:`, section-scoped tomato sauce.

10. Non-food/equipment
   - Exclude as non-food.
   - Fixture examples include skewers/foil/rocks/firewood/casing class.

11. Bare category items need context
   - Use recipe title, nearby ingredients, section, and dish context.
   - Fixture examples: cheese, nuts, pasta, oil, pepper, apples.

12. Head-noun normalization is unsafe
   - Preserve compounds.
   - Fixture examples: cream cheese, coconut milk, milk chocolate, peanut butter.

13. Distinct senses share names
   - Preserve sense.
   - Fixture examples: pepper spice vs red pepper vs peppercorn; coriander seed vs cilantro; chili powder vs chile pepper vs prepared chili.

14. Qualifier tuples
   - Preserve form/state/variant tuple.
   - Fixture examples: canned/frozen/whole/creamed corn; dried 16-bean mix; canned pumpkin puree.

15. Dictionary gaps
   - Preserve exact concept.
   - If no product identity exists, emit `needs_new_concept`; do not force generic.

16. Attribute extraction
   - Put brand, prep, state, form, flavor, variant, claims in the correct fields.
   - Validator catches common failures like brand in machine name and quantity in machine name.

17. Percent/purity labels
   - Preserve percent/purity.
   - Fixture examples: Nabisco 100% bran, bare 100% bran, 100% fruit juice, 100% pumpkin, 100% whey protein powder.

18. Prep/state/packaging identity ambiguity
   - Decide whether a word is identity, state, form, prep, packaging, or claim.
   - Examples: canned beans, chopped onion, ground beef, whole wheat.

19. Brand compounds
   - Remove brand from identity but preserve brand meaning when needed.
   - Examples: Nabisco 100% bran -> likely bran cereal; Rotel -> tomatoes with green chiles; Cool Whip -> whipped topping.

20. LLM contamination
   - Do not echo display text.
   - Do not invent SKUs.
   - Do not leak quantity/prep into machine identity.
   - Validator checks fake SKU, display echo, brand leaks, and quantity leaks.

27. Generic token magnets
   - Avoid unsafe generic matches from words like apple, milk, cream, sauce, bread, fresh, whole, baby.
   - Prompt and validator cover this through head-noun, context, and shared-sense tests.

32. Layered architecture
   - Recipe output should be raw line -> structured matchable facts.
   - Do not shortcut from raw text/head noun directly to ESHA.

## What The Prompt Can Only Flag

These can appear at recipe stage, but the prompt cannot finish them alone.

14. Missing qualifier tuple approval
   - Prompt preserves tuple.
   - Downstream rules decide if tuple is approved.

15. Concepts not in dictionary
   - Prompt emits exact concept or `needs_new_concept`.
   - Dictionary/product layer must add or map it.

16. Attribute extraction gaps
   - Prompt can output fields.
   - Validator/audits must catch systematic column errors.

23. Unsafe proxies
   - Prompt must not pick proxy truth.
   - It preserves identity and uncertainty so proxy review can happen later.

24. Missing leaves
   - Prompt can say `needs_new_concept`.
   - Taxonomy work must create/approve the leaf.

## Downstream, Not Recipe-Prompt Work

These are real blockers for recipe calculation, but this prompt does not solve
them.

21. ESHA/SR28/FNDDS coverage incomplete
   - Recipe prompt preserves identity only.
   - Nutrition anchor layer handles coverage.

22. Existing nutrition-code disagreements
   - Not recipe normalization.
   - Needs nutrition-code audit.

23. Proxy safety
   - Not recipe normalization.
   - Needs proxy review/contract.

24. Missing leaves
   - Not directly recipe normalization.
   - Needs taxonomy/product concept work.

25. Product matching failure layer
   - Recipe prompt produces matchable identity.
   - Product matcher must find product/canonical/nutrition candidate.

26. ESHA is not retail taxonomy
   - Recipe prompt should not normalize directly to ESHA.
   - It should normalize to retail/product identity facts.

28. Embeddings/clusters used too early
   - Not prompt work.
   - Candidate recall only, not final truth.

29. Coverage mistaken for correctness
   - Not prompt work.
   - Needs metrics/reporting discipline.

30. Review queues not closed loops
   - Not prompt work.
   - Needs durable rule ingestion.

31. Reducer/scratch phase sprawl
   - Not prompt work.
   - Needs pipeline consolidation.

## Current Test Coverage

The fixture currently covers:

- true alternatives,
- component splits,
- display-hidden choices,
- parenthetical examples,
- optional/garnish/to-taste/as-needed/serving lines,
- quantity leakage checks,
- quantity ranges,
- parser fragments,
- section headers and section-scoped ingredients,
- non-food/equipment,
- bare category context,
- head-noun traps,
- shared-name senses,
- qualifier/state/form preservation,
- percent/purity labels,
- prep/state/packaging ambiguity,
- brand compounds,
- LLM contamination checks,
- generic token magnets.

This is a representative stress fixture, not proof of full-corpus success.

## Nebius Run Protocol

Do not run the full corpus.

First run only the targeted fixture source:

- `implementation/output/recipe_normalization_nebius_target_source.jsonl`

The command should write real model output to:

- `implementation/output/recipe_normalization_nebius_candidate.jsonl`

And validator findings to:

- `implementation/output/recipe_normalization_nebius_candidate_findings.jsonl`

After the run:

1. Show the real output file exists.
2. Show validator counts.
3. Inspect failures line by line.
4. Patch prompt or validator.
5. Re-run the small fixture.
6. Only then consider broader samples.

## Non-Negotiable Honesty Rule

Do not call local fixture tests “Nebius results.”

Do not imply model behavior has been tested until
`recipe_normalization_nebius_candidate.jsonl` exists from a real Nebius call.

Do not call a line fixed just because the prompt mentions it. It is fixed only
when the model output passes validator checks and manual inspection for that
failure class.
