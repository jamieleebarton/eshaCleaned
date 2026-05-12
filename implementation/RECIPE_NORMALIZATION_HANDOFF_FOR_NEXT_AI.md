# Recipe Normalization Handoff For Next AI

## Correction

The recipe-normalization stage is not primarily the nutrition calculation stage.
The first job is to rewrite recipe ingredient lines into clean, matchable,
structured food identities that can be aligned to the product/retail taxonomy.
Nutrition grams and final consumed-mass calculation come after matching, with
explicit deterministic policies.

Do not jump from raw recipe text directly to ESHA/SR28/FNDDS. Do not make a
nutrition-code selection in this stage.

## Stage 1: Recipe Rewrite / Matchability

Input:

- recipe title
- full ingredient display lines
- parsed item, if available
- parser grams, if available
- surrounding ingredient context
- section headers and recipe structure

Output:

- `original_display`: unchanged original text
- `rewritten_ingredient`: clean visible ingredient line suitable for matching
- `machine_name` / `product_identity`: no quantity, no brand-only name, no prep
  junk
- state/form fields: fresh, frozen, canned, dried, shredded, chopped, bone-in,
  seed, powder, puree, blend, etc.
- prep fields separate from identity: chopped, drained, rinsed, soaked, sliced
- role fields: consumed, component group, alternative group, process medium,
  process coating, cooking water, garnish, serving accompaniment, optional,
  non-food, section header
- alternatives/components explicitly represented
- blockers only where the item cannot be made matchable without a user choice or
  missing concept

This stage must make the ingredient matchable. It should not leave easy recipe
rewrite problems hidden for a later nutrition stage.

## Stage 2: Product / Canonical Matching

After recipe rewrite, match `product_identity` plus attributes against the retail
taxonomy/product corpus. The relevant product-side target fields are from
`retail_mapper/v2/full_corpus.csv`:

- `retail_type`
- `category_path`
- `product_identity`
- `canonical_path`
- `canonical_label`
- `variant`
- `flavor`
- `form_texture_cut`
- `processing_storage`
- `claims`
- `components`

This is where `16-bean mix`, `7 bean mix`, `15 bean mix`, `3-cheese blend`,
`Mexican cheese blend`, `canned corn`, `frozen corn`, etc. become matchable
against products/canonical paths.

## Stage 3: Calculation

Only after the ingredient is matchable do we apply calculation policy:

- edible yield
- cooking loss/retention
- range midpoint
- sodium absorption
- frying oil uptake
- coating/dusting retention
- garnish/optional/serving defaults
- removed aromatics

The calculator may preserve `raw_calculation_status`, but the cleaned recipe
rewrite should already be matchable.

## Specific Expected Behavior

| Original | Correct Recipe Rewrite | Matchable? | Calculation Later |
|---|---|---:|---|
| `1 to 3 teaspoons Worcestershire sauce` | `2 teaspoons Worcestershire sauce` using midpoint policy, with original range preserved in metadata | yes | midpoint grams later |
| `1 bag (about 16 oz) 7 bean mix or 15 bean mix` | `1 bag (about 16 oz) dried mixed bean soup mix (7 bean mix OR 15 bean mix)` | yes | use parser/source grams unless product match changes package basis |
| `16-bean mix, dried` | `dried 16-bean soup mix` | yes | after product/canonical match |
| `Monterey Jack cheese or Mexican blend cheese` | preserve both alternatives | no | user/product selection required |
| `Crushed corn flakes, cracker crumbs, or extra cheddar cheese` | preserve three topping alternatives | no | user/product selection required |
| `1 ham bone` | `ham bone with meat scraps` and `bone/yield policy required` | yes | edible yield later |
| `1 bay leaf` | `bay leaf` with removed-aromatic retention flag | yes | zero or retention policy later |
| `1 hot chili pepper or 1 dried chili` | preserve both forms under chili pepper seasoning alternative | yes for matching if policy accepts equivalent seasoning role | source grams/default later |
| `Salt, to taste` | `salt` with to-taste seasoning flag | yes | default sodium/grams policy later |
| `Oil, for frying` | `oil` with process-medium role | yes | uptake policy later, not full source grams |
| `Flour, for dusting` | `flour` with process-coating role | yes | retention policy later, not full source grams |
| `For sauce:` | section header, not ingredient | excluded | none |
| `1 cup 100% fruit juice` with no fruit context | `100% fruit juice` with fruit identity unresolved | no | needs context or generic-juice policy |
| context-resolved juice, e.g. recipe is orange punch and nearby lines say orange | `100% orange juice` | yes | after match |

## Key Rule

If the LLM can resolve the food identity from recipe context, it must resolve it
in the recipe rewrite. If it cannot resolve the identity, it must block with the
exact missing choice. It should not pretend calculation solved an identity that
was never made matchable.

