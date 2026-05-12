# Recipe Normalization Working Contract

This document is the current contract for the recipe-normalization prompt work.
It exists to prevent scope drift and false claims about what has been run.

## Goal

Make recipe ingredient lines matchable.

The recipe LLM should turn messy recipe ingredient lines into structured facts
that can later be matched against the product/canonical/nutrition layer.

This stage does not choose ESHA, SR28, FNDDS, UPCs, retail products, or final
nutrition values.

## The Exact Problem

Recipes fail to calculate when recipe lines cannot be reliably matched to a
food/product identity or when the line pretends to be a normal consumed
ingredient but is not.

The prompt is meant to fix recipe-side matchability failures:

- preserve alternatives instead of silently choosing one,
- split true multi-food lines,
- remove brands while preserving brand meaning,
- preserve product-like blend identities such as `16-bean mix`,
- preserve form/state/storage such as fresh, frozen, canned, dried, bone-in,
- preserve compound identities such as `cream cheese` and `coconut milk`,
- use recipe context for ambiguous bare terms,
- preserve percent/purity labels such as `100% bran`,
- exclude parser junk and section headers,
- role-flag process and non-base ingredients such as frying oil, dredging flour,
  pasta-water salt, garnish, and serving sides.

The prompt cannot fix downstream failures:

- missing ESHA leaves,
- SR28/FNDDS gaps,
- wrong ESHA codes,
- unsafe product proxies,
- product nutrition missing,
- review queues not closing the loop,
- duplicated scratch implementations.

For those downstream problems, the recipe LLM should only preserve the clean
matchable identity so the next layer can match it or fail honestly.

## Definitions

`MATCH_READY` means the recipe line is clean enough to send to product matching.
It does not mean nutrition has been calculated.

`BLOCKED_SELECTION_REQUIRED` means the recipe contains alternatives such as
`butter or margarine` or `7 bean mix or 15 bean mix`. The output should contain
all options. A later policy/user selection must choose one.

`BLOCKED_CONTEXT_REQUIRED` means the line lacks identity needed for matching,
such as bare `100% bran` or `100% fruit juice`.

`EXCLUDED` means the line is not a food ingredient, such as `or`, `For sauce:`,
foil, skewers, or other equipment/structure.

`ROLE_FLAGGED` means the food is matchable but must not be treated as a normal
fully consumed ingredient later. Examples: oil for frying, flour for dusting,
salt for pasta water, parsley for garnish.

## What Has Actually Been Done

Created/expanded the real recipe fixture:

- `implementation/output/recipe_normalization_prompt_test_pack.jsonl`
- `implementation/output/recipe_normalization_prompt_test_pack_index.csv`

Current fixture size:

- 47 recipes
- 97 stressed lines
- 36 failure case types

Created the prompt draft:

- `implementation/RECIPE_NORMALIZATION_NEBIUS_PROMPT_DRAFT.md`

Created the validator:

- `implementation/validate_recipe_normalization_nebius_output.py`

Created fixture/unit tests:

- `implementation/tests/test_recipe_normalization_prompt_fixtures.py`

Created scope/expectation docs:

- `implementation/output/recipe_normalization_failure_coverage_matrix.md`
- `implementation/output/recipe_normalization_matchability_expectations.md`

## What Has Not Been Done

Nebius has not been run for this recipe-normalization prompt.

There is no real Nebius candidate output yet.

These files do not currently exist as real Nebius results:

- `implementation/output/recipe_normalization_nebius_candidate.jsonl`
- `implementation/output/recipe_normalization_nebius_candidate_findings.jsonl`

Any validator output previously discussed was from a deliberately bad local
fake candidate, not from Nebius.

## What "Tests Passed" Means

Only local tests were run.

The command was:

```bash
python3 -m unittest implementation.tests.test_recipe_normalization_prompt_fixtures -v
```

Those tests verify:

- the fixture contains required failure cases,
- the validator catches a deliberately bad local candidate,
- blend/mix identities are rejected if collapsed to single foods.

These tests do not prove the prompt works with Nebius.

They only prove the local fixture and validator are wired.

## What The Nebius Test Must Do Next

When an API key is available, run a small sample only:

```bash
python3 implementation/run_recipe_normalization_nebius_sample.py --limit 5 --validate
```

Expected real outputs:

- `implementation/output/recipe_normalization_nebius_candidate.jsonl`
- `implementation/output/recipe_normalization_nebius_candidate_findings.jsonl`

After that run, inspect the actual model output line by line. Any model failure
must become a hard validator rule or a fixture addition. Do not scale to the
full recipe corpus until the fixture passes.

## Current Honest Status

The work is at the prompt-and-test-harness stage.

It is not proven against Nebius yet.

The current fixture covers the major recipe-side failure classes from the
research, but one fixture pass is not enough to trust a full-corpus run. The
next required step is a real Nebius sample run and direct review of its JSONL
output.
