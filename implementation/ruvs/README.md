# Recipe Universe Verification & Stamping (RUVS) v1

A closed-loop verification pipeline for Hestia recipes. Discovers the bounded set of recipes the planner actually uses, verifies every ingredient line via DeepSeek with live Walmart/Kroger tool-calling, and emits canonical-grouped patches that fix the underlying Hestia data.

**Status:** v1 build shipped 2026-05-01. 43 unit tests passing. Live smoke and one-cell run gated on `NEBIUS_API_KEY`.

## Why this exists

Hestia ships recipes whose ingredient resolution is unreliable in three ways:

1. **Wrong product form.** "1/2 gallon beef gravy" buys "Gravy, instant beef, dry" (a powder mix). "6 lb ham" picks a $2.49 deli ham (per-pound price, sliced form). "Green beans" maps to "green bean almondine" (a prepared dish).
2. **Wrong granularity.** "Mayonnaise" is free to pick chipotle or lime mayo, because Hestia's `food_packages_final.db` only carries `fndds_code` — no `variant`, `flavor`, or `form` constraints.
3. **Wrong gram math.** "1 lb bacon = 52g" is in the data. Head of lettuce is missing average grams. LLMs hallucinate fixes for these every time, so the LLM cannot be the fix — it can only flag.

RUVS verifies each recipe-line against the existing Hestia state, surfaces specific failure modes, and emits structured patches that downstream Hestia migrations apply deterministically.

## How it works (3 phases)

```
Phase A: discover universe
  configs (household × dietary × pattern × pantry) × 50 weeks
  → universe.jsonl: every (recipe_id, config_id, week, slot) the planner picks

Phase B: verify
  for each unique (recipe_id, line_idx, config_bucket):
    build_packet(...)        # inline FNDDS, SR28, ESHA, audit candidates
    verify_line(...)         # DeepSeek + walmart/kroger/flag_grams tools
    append_verdict(...)      # JSONL with dedup
  build_fix_queue(...)       # group by (canonical, facet, patch_type)

Phase C: review + patch + stamp
  review_fix_queue(...)      # LLM-driven, auto-escalate above blast-radius
  generate_patches(...)      # patches/{wishlist,alias,portion,exclusion,recipe_text_edit,audit_correction}/
  → Hestia migrations apply patches deterministically
  → re-verify on patched lines closes the loop
```

## Architecture

```
            Hestia repo                 esha_audit_bundle repo
        +-----------------+         +------------------------------+
        | sparse_cascade  | plans   | ruvs/ + ruvs_*.py            |
        | food_packages   | ------> | A1: ruvs_universe.py         |
        | recipes2.csv    |         | B1: ruvs_packets.py          |
        | fndds_cards     |         | B2: ruvs_verify.py           |
        +-----------------+         | B3: ruvs_verdicts.py         |
                ^                   | B4: ruvs_fix_queue.py        |
                |                   | T2: ruvs_review.py           |
                | patches +         | C1: ruvs_patches.py          |
                | stamps  (read     |                              |
                |  by Hestia at     | reads:                       |
                |  startup)         |   full_corpus_audit.csv      |
                |                   |   esha_cleaned.csv           |
                |                   |   FNDDS, SR28                |
                +------------------ +------------------------------+
```

## Component layout

```
implementation/
├── ruvs/                           # shared package
│   ├── __init__.py
│   ├── schemas.py                  # Packet, LineVerdict, FixRow, Patch + FACETS/enums
│   ├── prompts.py                  # STAMP_SYSTEM_PROMPT, REVIEWER_SYSTEM_PROMPT, builders
│   ├── nebius.py                   # DeepSeek-V3.2-fast client with tool-use + cost
│   ├── budget.py                   # Budget guard (RUVS_BUDGET_USD)
│   └── tools/
│       ├── walmart.py              # walmart_search + WALMART_TOOL_SCHEMA
│       ├── kroger.py               # kroger_search + KROGER_TOOL_SCHEMA
│       └── flag_grams_suspect.py   # flag_grams_suspect (no numeric grams)
│
├── ruvs_universe.py                # A1: discover universe
├── ruvs_packets.py                 # B1: build verification packets
├── ruvs_verify.py                  # B2: DeepSeek caller + tool dispatch + verdict parse
├── ruvs_verdicts.py                # B3: JSONL writer + key-dedup
├── ruvs_fix_queue.py               # B4: canonical-grouped queue
├── ruvs_patches.py                 # C1: approved-only patch emitter
├── ruvs_review.py                  # T2: LLM-driven review with blast-radius escalation
│
├── config_matrix.yaml              # A1 input (cells = household x dietary x pattern x pantry_seed)
│
├── run_ruvs_smoke.py               # acceptance gate: 506745 E2E
└── run_ruvs_cell.py                # acceptance gate: 1 cell x 50 weeks
```

## Verdict schema

DeepSeek emits a per-line verdict with seven facets. Each facet is an enum (validated at the Python layer in `LineVerdict.__post_init__`):

| Facet | Allowed values |
|---|---|
| `canonical_correct` | `ok`, `wrong`, `ambiguous` |
| `form_correct` | `ok`, `wrong_form`, `n/a` |
| `granularity_correct` | `ok`, `too_specific`, `too_generic` |
| `grams_plausible` | `ok`, `suspect` |
| `cook_state_handled` | `ok`, `wrong_state`, `n/a` |
| `package_math_sane` | `ok`, `suspect` |
| `ambiguity_flagged` | `none`, `range`, `or_option`, `generic_term` |

`is_clean()` returns true iff all facets are at their "passing" values (per `CLEAN_VALUES`).

## Patch types

DeepSeek's `fix_proposed.patch_type` selects one of:

| Patch type | Delta shape | Applied to |
|---|---|---|
| `wishlist` | `{deny_form, require_form, deny_flavor, deny_processing}` | Hestia package selector |
| `alias` | `{add_aliases: [...]}` | Recipe-side resolver |
| `portion` | `{hint: "..."}` (LLM does NOT propose numeric grams) | `food_packages_final.db` portion data |
| `exclusion` | `{reason: "..."}` | Recipe pool exclusion |
| `recipe_text_edit` | `{suggested_text, reason}` | Recipe text rewrite |
| `audit_correction` | `{fdc_id, wrong_canonical_label, suggested_canonical_label}` | `full_corpus_audit.csv` |

## Critical contracts (load-bearing rules)

### 1. Default-prep-state rule

When a recipe names an ingredient with no modifier ("chicken", "shrimp", "beef", "potatoes", "broccoli", "rice"), the default expected form is **raw, plain, unseasoned, unprocessed**. DeepSeek must reject any product whose title or processing implies:

- breaded / battered / breaded_and_seasoned
- seasoned / marinated / flavored / pre_seasoned
- pre_cooked / ready_to_eat / microwave_ready
- breaded_strips / popcorn / nuggets / tenders (when recipe says "chicken")
- corned / cured / smoked (when recipe says "beef" or "pork")
- in_sauce / in_cheese_sauce / glazed (when recipe says a vegetable name)

unless the recipe text contains the matching modifier.

This rule is encoded in `STAMP_SYSTEM_PROMPT` (in `ruvs/prompts.py`) and tested by golden fixture `breaded_default_state.json`.

### 2. No-numeric-grams rule

LLMs hallucinate gram values every time. DeepSeek **never** computes or proposes numeric grams. If the recipe's gram math looks wrong vs retailer evidence, DeepSeek calls `flag_grams_suspect(reason)` with a free-text reason only. Data fixes are deterministic downstream — patches use retailer evidence (Walmart/Kroger pkg sizes) to fix actual numbers.

The `flag_grams_suspect` tool schema explicitly forbids any numeric input; tested by `test_flag_schema_takes_only_reason`.

### 3. Canonical-grouped patches

The fix queue groups by `(canonical, facet, patch_type)`, not by recipe. "wrong_form: beef gravy" surfaces once with the affected-recipe count, not 47 times. Patches fix the canonical; affected recipes regression-stamp afterward.

### 4. Stamp lifecycle

When a patch lands that changes a canonical or portion the line touched, all stamps for affected lines are marked `invalidated`. The next verify pass re-stamps. **Regression rule:** a patch cannot ship if it would invalidate a previously-stamped line into a `wrong_*` state without a follow-up patch queued. (Stamp invalidation is v2 logic; v1 produces verdicts but does not enforce ship-gate.)

## Review gate (3 tiers)

| Tier | Reviewer | When |
|---|---|---|
| **T1 Auto-approve** (v2) | Deterministic rule | 2+ stamps agree, low-risk patch type, ≤10 recipes affected |
| **T2 LLM review** (v1) | Reviewer LLM (different model from stamping) | Stamps disagree, canonical used by >10 recipes, or any canonical_label change |
| **T3 Jamie review** | Jamie | LLM escalates, blast-radius >100, or `ambiguous_serious` |

v1 routes through T2 (LLM) and escalates to T3. Same-model self-review is forbidden.

## Running

### Prerequisites

```bash
export NEBIUS_API_KEY=sk-...                     # required
export WALMART_API_KEY=...                       # optional - returns [] without
export KROGER_ACCESS_TOKEN=...                   # optional - returns [] without
export RUVS_BUDGET_USD=50                        # optional, default 50
```

The Walmart public endpoint (`api.walmartlabs.com/v1/search`) is deprecated; live calls return `[]`. Kroger should work with a valid OAuth token. Without retailer keys, DeepSeek operates only on the inline FNDDS/SR28/ESHA reference data in the packet.

### Smoke test (506745 only)

```bash
cd /Users/jamiebarton/Desktop/esha_audit_bundle/implementation
python3 run_ruvs_smoke.py --budget-usd 0.50
```

Loads ingredient lines from the existing `output/one_recipe_506745_llm_verification_packet.jsonl`, runs each through B1 → B2 → B3 → B4 → T2 → C1, and emits results to `output/ruvs/smoke_506745/`.

**v1 acceptance signal:** the beef-gravy line MUST surface in `fix_queue.csv` with `proposed_patch_type=wishlist` and a `delta_merged.deny_form` containing `dry` and/or `instant`. Hard cap: $0.50, 5 minutes.

### One config-cell run (50 weeks)

```bash
python3 run_ruvs_cell.py --cell-id solo_default --budget-usd 50.00
```

**v1 status:** the recipe-line iterator (`_iter_recipe_lines`) is a placeholder. The runner ships with the structure complete (universe → packets → verdicts → queue → review → patches), but until the recipe loader is wired, no recipes flow through. See "v1 gaps" below.

### Tests

```bash
cd /Users/jamiebarton/Desktop/esha_audit_bundle/implementation

# RUVS-only suite (43 tests, 1 skipped)
pytest tests/test_ruvs_smoke.py tests/test_ruvs_schemas.py tests/test_ruvs_tools_walmart.py \
       tests/test_ruvs_tools_kroger.py tests/test_ruvs_tools_flag.py tests/test_ruvs_prompts.py \
       tests/test_ruvs_nebius.py tests/test_ruvs_budget.py tests/test_ruvs_packets.py \
       tests/test_ruvs_verify.py tests/test_ruvs_verdicts.py tests/test_ruvs_fix_queue.py \
       tests/test_ruvs_patches.py tests/test_ruvs_review.py tests/test_ruvs_universe.py \
       tests/test_ruvs_golden_fixtures.py -v

# With NEBIUS_API_KEY set: also runs the live smoke
NEBIUS_API_KEY=sk-... pytest tests/test_ruvs_smoke.py -v
```

## Golden recipe fixtures

`tests/ruvs_golden/` contains 8 hand-curated `{packet, expected_facets, expected_fix_proposed}` fixtures covering known bug classes:

| Fixture | Bug class |
|---|---|
| `506745_booyah.json` | dry-vs-liquid (1/2 gallon beef gravy → dry mix) |
| `breaded_default_state.json` | recipe says "chicken breast", retailer offers breaded |
| `green_bean_almondine.json` | Hestia maps "green beans" → "Green bean almondine" (wrong canonical) |
| `one_lb_bacon_grams.json` | recipe_grams=52 for 1 lb bacon (suspect grams) |
| `butter_or_margarine.json` | or-option ambiguity |
| `peppers_range.json` | range ambiguity ("6-8 jalapeno peppers") |
| `generic_cheese.json` | too-generic ("1 cup shredded cheese") |
| `all_clean_baseline.json` | clean line that should stamp first try |

These are the source-of-truth for "what verification should produce" and feed regression tests as v1 evolves.

## Cost model

DeepSeek-V3.2-fast pricing (per 1M tokens):
- Cache hit: $0.0028
- Cache miss: $0.14
- Output: $0.28

`Budget` enforces `RUVS_BUDGET_USD` cap; raises `BudgetExceeded` past the cap. `MessageResult.cost_usd` populated automatically from the API's `usage` field.

A typical line verification: ~5K input + 1K output tokens ≈ $0.001 if all cache miss. 18 lines on 506745 ≈ $0.018. The $0.50 smoke cap is generous (~28x headroom).

A typical config-cell (1 household × 50 weeks ≈ 350 plate-meals × ~5-10 lines each) ≈ 4-6K line stamps × $0.001 ≈ $4-6 per cell. The $50 cap fits 8-12 cells.

## v1 gaps (deferred to v2)

These are explicitly out of scope for v1 and documented in the implementation plan:

1. **Cell runner recipe loader** (`run_ruvs_cell.py::_iter_recipe_lines`). Currently returns empty iterator. Needs to:
   - Load `recipes2.csv` from `/Users/jamiebarton/Desktop/Hestia/api/data/recipes2.csv`.
   - Parse each recipe's ingredient list (Hestia has parsing logic in `api/scripts/deepseek_plate_template_experiment.py`).
   - Build a `Packet` per line with proper `ReferenceData` loaded from FNDDS cards, ESHA, full_corpus_audit, and the current Hestia canonical for that ingredient.
   - Per `feedback_always_full_state.md`: thread `pantry_ttl`, `pantry_frozen`, `historical_banned_ids` through to keep planner state consistent.

2. **Universe runner real mode** (`ruvs_universe.py::_run_one_cell`). The placeholder call to `sparse_cascade.SparseCascadePlanner.from_defaults().plan(...)` does NOT match Hestia's actual API. The real signature is `start_session(initial_pantry).plan_next_week()` looped per week. Stub mode works for unit tests; real mode needs proper construction (recipe DB load, tensor cache, household profiles).

3. **Walmart endpoint replacement.** `api.walmartlabs.com/v1/search` was sunset around 2020. Need BlueCart, SerpApi, or the official Walmart Affiliate API as a replacement. Until then, `walmart_search` returns `[]` and DeepSeek operates without live Walmart data.

4. **Cross-check stamping (B5)** — second-model triple-stamp for high-confidence verdicts. v2.

5. **T1 auto-approve gate** — deterministic auto-approve for low-risk, high-agreement patches. v1 routes everything through T2 LLM review. v2.

6. **Ship gate enforcement** — `ship_gate.py` filters Hestia's planner pool to stamped recipes only. v1 produces `would_be_excluded.csv` instead. v2 wires the actual filter.

7. **stamps.db (SQLite)** — v1 writes JSONL; v2 migrates to SQLite once schema is stable.

## References

- **Spec:** `/Users/jamiebarton/Desktop/Hestia/docs/superpowers/specs/2026-05-01-recipe-universe-verification-stamping-design.md`
- **Implementation plan:** `/Users/jamiebarton/Desktop/Hestia/docs/superpowers/plans/2026-05-01-ruvs-v1-implementation.md`
- **Source verification packet (506745):** `implementation/output/one_recipe_506745_llm_verification_packet.jsonl`
- **Wishlist substrate:** `retail_mapper/v2/full_corpus_audit.csv` (462,712 rows, prior-trusted, verified per-canonical at runtime)
- **Hestia entry points:**
  - `Hestia/api/hestia/sparse_cascade.py` (planner, called by A1)
  - `Hestia/api/data/food_packages_final.db` (target of `patches/wishlist` and `patches/portions`)
  - `Hestia/api/data/recipes2.csv` (recipe corpus, source for cell runner)
  - `Hestia/api/scripts/deepseek_plate_template_experiment.py` (existing Nebius client, pattern reused by `ruvs/nebius.py`)

## Commit history (v1 build)

```
f286c1a ruvs: cell runner for v1 acceptance (1 cell x 50 weeks)
068e6e0 ruvs: smoke runner for 506745 + acceptance test (gated on NEBIUS_API_KEY)
88fd4e2 ruvs: golden recipe fixtures (8 cases incl 506745, default-prep-state, ambiguity)
7f9a955 ruvs: A1 universe_runner with stub mode and starter config matrix
e2e86c6 ruvs: T2 reviewer with auto-escalate above blast-radius threshold
709c833 ruvs: C1 patch_generator, approved-only emission
21b6ccd ruvs: B4 fix_queue_builder, canonical-grouped + ranked
5c51251 ruvs: B3 verdict_writer with key-based JSONL dedup
dca04b9 ruvs: B2 deepseek_caller with tool dispatch, JSON verdict parse, tool-loop cap
2103ed2 ruvs: packet_builder - clean lookup helper, fixture matches real audit shape
9703678 ruvs: B1 packet_builder with mocked retailer tests
9d33a4b ruvs: nebius - None-safe usage, Budget tests, body-omission tests
0eabbbd ruvs: nebius DeepSeek client with tool-use, cost estimation, and Budget guard
806e87c ruvs: prompts - document recipe_text_edit patch delta
f5c0ca7 ruvs: stamp + reviewer prompts encoding default-prep-state and no-grams rules
3eaf5a1 ruvs: flag_grams_suspect tool (no numeric grams allowed)
fcb03a3 ruvs: tool wrappers - catch ValueError, parity description, no-token test
2476262 ruvs: walmart and kroger tool wrappers with mocked-http tests
b8b7292 ruvs: schemas (Packet, LineVerdict, FixRow, Patch) with facet enum validation
47cbd72 ruvs: add empty conftest.py so pytest discovers ruvs/ from implementation/
5481934 ruvs: package skeleton and smoke harness
1e6b52a init: gitignore for esha_audit_bundle
```
