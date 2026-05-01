# Diabolical Taxonomy — Test Harness

Workflow for the iterative test session. Cost-aware: re-score is local
(zero API spend); only `--run-live` hits the model.

## What changed in this round

- **Fixture map**: `fixture_real_evidence_map.json` maps each synthetic
  `*_fixture` fdc_id to a real CSV row (cookies, broth, tomatoes, pretzels,
  seasoning, tortillas, coconut water, dip, soup, pizza-crust mix). The packet
  builder now grafts `ing_full`, `ing_top5`, n-grams, role candidates, and
  `llm_evidence_block` from the real row while keeping the fixture title/BFC.
  Build a request file and confirm with: `--build-requests` (it prints
  `(N cases, M with grafted evidence)`).
- **Deterministic normalizer** in `llm_taxonomy_cleanup.py` (`normalize_record`):
  - Sorts `claims` by `CLAIM_ORDER`.
  - Merges compound facet tokens (`whole`+`peeled` → `whole_peeled`).
  - Moves known-form tokens out of variant into `form_texture_cut`.
  - Strips evidence-gated junk (`canned`, `frozen`, `shelf_stable`, `mix`,
    `blend`, `crisps`, …) when not in title/BFC/product_form/esha_desc.
  - Identity decorator strip (`Pretzel Pieces` → `Pretzels`,
    `Seasoning Blend` → `Seasoning`, `Seasoning Mix` → `Seasoning`).
  - Identity prefix demote (`Protein Parfait` → `Parfait`, variant += `protein`).
  - Identity promotion from variant (`Soup` + variant `broccoli_cheddar`
    → `Broccoli Cheddar Soup`).
  - Reclassifies known-flavor tokens from variant → flavor.
  - Drops facet values already encoded in identity (`Cheese Crisps` no longer
    has form_texture=['crisps']).
  - Force-routes `category_path` from `product_identity` via expanded
    `CANONICAL_CATEGORY_HINTS` (now includes Pretzels, Seasoning, Tortillas).
  - Sets `retail_type=meal_kit` for *Starter*/*Kit* identities.
  - **Always regenerates `canonical_label` and `tree_paths`** from the
    final facets, so format-only failures disappear.

## Current scores (no API spend, just normalizer)

| label | core | exact |
| --- | --- | --- |
| DeepSeek raw | 2/17 | 0/17 |
| DeepSeek+norm | 9/17 | 2/17 |
| Qwen raw | 5/17 | 1/17 |
| Qwen+norm | 9/17 | 3/17 |

Remaining failures are mostly real semantic issues that need either richer
evidence (the new graft does this) or prompt tightening:
- components missing (tortillas needs `Almond Flour`; soup needs
  `Broccoli`+`Cheddar Cheese`; dip needs `Spinach`+`Artichoke`)
- variant explosion in deeply-composite items (parfait, cheese-crisps,
  meal-starter)
- specific cheese form vs variant (`hard` belongs in form, not variant)

## Run the live DeepSeek call with real evidence

The requests file with grafted real evidence is already built:
`llm_taxonomy_diabolical_real_evidence_requests.jsonl` (17 cases, 10 grafted).

Inline the API key with the existing pattern, then:

```
stty -echo; read -r NEBIUS_API_KEY; stty echo; export NEBIUS_API_KEY
python3 retail_mapper/v2/llm_taxonomy_cleanup.py \
  --gold retail_mapper/v2/llm_taxonomy_diabolical_cases.jsonl \
  --requests-out retail_mapper/v2/llm_taxonomy_diabolical_real_evidence_requests.jsonl \
  --outputs-out retail_mapper/v2/llm_taxonomy_diabolical_deepseek_real_evidence.live.jsonl \
  --model deepseek-ai/DeepSeek-V3.2 \
  --build-requests --run-live --pause-seconds 0.4 --retry-attempts 4
```

Cost estimate (per Codex's earlier numbers, ~3.5K input × ~0.32K output per case):
**~$0.015 for the 17-case run on DeepSeek-V3.2.**

Then re-score with normalizer:

```
python3 retail_mapper/v2/llm_taxonomy_cleanup.py \
  --gold retail_mapper/v2/llm_taxonomy_diabolical_cases.jsonl \
  --rescore retail_mapper/v2/llm_taxonomy_diabolical_deepseek_real_evidence.live.jsonl \
  --apply-normalizer \
  --rescore-out retail_mapper/v2/llm_taxonomy_diabolical_deepseek_real_evidence.rescore.json \
  --diff-out   retail_mapper/v2/llm_taxonomy_diabolical_deepseek_real_evidence.rescore.md
```

## Iterative loop (no API spend per iteration)

After every prompt or normalizer change:

```
# 1) Re-score every existing live JSONL against the latest normalizer
python3 retail_mapper/v2/llm_taxonomy_cleanup.py \
  --gold retail_mapper/v2/llm_taxonomy_diabolical_cases.jsonl \
  --rescore retail_mapper/v2/llm_taxonomy_diabolical_deepseek_real_evidence.live.jsonl \
  --apply-normalizer \
  --rescore-out retail_mapper/v2/llm_taxonomy_diabolical_deepseek_real_evidence.rescore.json \
  --diff-out   retail_mapper/v2/llm_taxonomy_diabolical_deepseek_real_evidence.rescore.md

# 2) Side-by-side compare across all flavors
python3 retail_mapper/v2/taxonomy_compare.py \
  --pair "DeepSeek raw=retail_mapper/v2/llm_taxonomy_diabolical_deepseek.rescore_baseline.json" \
  --pair "DeepSeek+norm=retail_mapper/v2/llm_taxonomy_diabolical_deepseek.rescore_normalized.json" \
  --pair "DeepSeek+real+norm=retail_mapper/v2/llm_taxonomy_diabolical_deepseek_real_evidence.rescore.json" \
  --pair "Qwen+norm=retail_mapper/v2/llm_taxonomy_diabolical_qwen235.rescore_normalized.json" \
  --out retail_mapper/v2/taxonomy_compare.md
```

The diff `.md` shows expected-vs-actual per case so you can pinpoint which
cell flips on each tweak.

## CLI flags added

| flag | purpose |
| --- | --- |
| `--fixture-map PATH` | Override fixture→real fdc map JSON. Default: `fixture_real_evidence_map.json`. |
| `--no-fixture-map` | Disable evidence grafting (raw gold sources only). |
| `--apply-normalizer` | Run `normalize_record` on records before scoring. |
| `--rescore PATH` | Re-score an existing live JSONL (no API call). |
| `--rescore-out PATH` | Where to write the JSON summary (default `<rescore>.rescore.json`). |
| `--diff-out PATH` | Markdown side-by-side per-case diff. |
| `--summary-out PATH` | Plain-text PASS/FAIL list. |
