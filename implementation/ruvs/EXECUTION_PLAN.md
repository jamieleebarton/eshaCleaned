# EXECUTION PLAN — finish the structured matcher

**Last edit:** 2026-05-02
**Anchor:** `STRUCTURED_MATCHER_SPEC.md` (parts 1–10), `GOAL.md` (active plan).
**Done so far tonight:** spec committed (`c1f0870`), Part 1 instrumentation (`f49da18`), Part 2 partial — multi-prefix + forbidden modifiers (`c639341`).

This is the remaining work, ordered by dependency. Each step is small, independently verifiable, and reversible. No LLM calls. No new agent dispatches. Direct execution.

---

## Step A — Split `surface_esha_override` (Part 4)

**Files:** `esha_audit_bundle/implementation/surface_lab_calculator.py` (around line 4465 / 4699).
**Effort:** S (~30 min). **Risk:** medium (nutrition path). **Reversible:** yes.

**Action:**
1. Read `_apply_surface_esha_override()` and find the early-return that prevents the retail product matcher from running.
2. Refactor so the override can:
   - Set `nutrition_state` and `esha_code` (keep this)
   - Influence `canonical_name` (keep this)
   - Append a path entry like `surface_esha_override:'<canonical>'->...`
   - **Always continue to the retail matcher** — never short-circuit.
3. Keep `SURFACE_ESHA_NUTRITION_PRIORITY` semantics (`macaroni`, `ramen noodles`, `chicken flavored ramen noodles`) intact for nutrition; only change the early-return.

**Verification:**
- Re-run calculator on recipe 36094 (Macaroni Pastitsio with Feta Cheese) and recipe 115199 (Affordable Basic Restaurant-Style Tomato and Macaroni Soup).
- The `path` field for the macaroni line must now contain a `shopping_products:` entry (currently absent — that's the bug).
- `accepted` count for macaroni rises from 0 if the cache has any matchable products through the bridge OR through accept_via_audit.
- Even if accept count stays 0 (because cache lacks plain dry macaroni — Step D), the path must show retail matching ran.

**Commit:** `ruvs: Part 4 - ESHA override no longer short-circuits retail matching`

---

## Step B — Generate `canonical_retail_bridge` from the audit (Part 5)

**Files created:**
- `Hestia/api/scripts/build_canonical_retail_bridge.py`
- `Hestia/api/data/canonical_retail_bridge.db`
- `Hestia/api/data/canonical_retail_bridge.report.md`

**Effort:** M (~1.5 hrs). **Risk:** low (additive; surface_lab_calculator reads optionally). **Reversible:** yes (drop the DB).

**Action:**
1. Read `esha_audit_bundle/implementation/canonical_to_esha.csv` (canonical_name → esha_code map; ~18K rows) and `canonical_items.csv` (canonical with fndds_code if present).
2. For each canonical, scan `full_corpus_audit.csv` rows where `esha_code` or `fndds_code` matches.
3. Compute per canonical:
   - `expected_canonical_path` — the most common `canonical_path` (mode); tie-break by `canonical_label` token overlap with the canonical_key.
   - `allowed_variants` — top-N most common `variant` values among matching rows (excluding empty).
   - `allowed_forms` — top-N most common `form_texture_cut` values.
   - `allowed_processing_storage` — top-N most common `processing_storage` values.
   - `forbidden_variants/forms/processing` — left empty; populate via Step C-derived data later.
   - `allow_flavored = false` (default — matches spec's default-prep-state rule).
   - `allow_combo = false` (default).
   - For canonicals where the canonical_key contains "flavored", "spice", "seasoning", "sauce" — set `allow_flavored = true`.
4. Write to a new SQLite at `Hestia/api/data/canonical_retail_bridge.db` with the schema in `STRUCTURED_MATCHER_SPEC.md` Part 5.
5. Spot-check via the report:
   - `macaroni` → `Pantry > Pasta > Macaroni > Plain` (or whatever audit mode is)
   - `chicken drumstick` → `Meat & Seafood > Poultry > Plain > Chicken Drumsticks`
   - `green onion` → `Produce > Vegetables > Onions` (audit's actual form)
   - `tomato juice` → `Beverage > Juice > Tomato`
   - `butter` / `pork butt` / `whole milk` / `cheddar cheese` / `flour` / `tortillas` / `bread` / `lettuce` / `canned corn` — all of the Part 7 test list

**Modify `accept_via_audit`** to read from the new DB instead of the hard-coded `_CANONICAL_AUDIT_EXPECTATION` dict. Keep the dict as fallback for canonicals not in the DB.

**Verification:**
- The 4 sample recipes from Step A still work (chicken drumstick / tomato juice still accept; green onion improves; macaroni unchanged unless cache is fixed).
- The 19 Part 7 test canonicals all have rows in the bridge DB.

**Commit:** `ruvs: Part 5 - generated canonical_retail_bridge from full_corpus_audit`

---

## Step C — Log + demote `_reject_combo_product` (Part 3)

**Files:** `surface_lab_calculator.py` (`_reject_combo_product`, `_product_acceptance_reason`).
**Effort:** M (~45 min). **Risk:** medium (changes default rejection behavior). **Reversible:** yes.

**Action:**
1. Wrap every call to `_reject_combo_product` with an instrumentation hook: log `(canonical, product_title, audit_classification, would_be_decision)` to a dump file when env `RUVS_COMBO_DEBUG_PATH` is set.
2. Inside `_reject_combo_product`, return `False` (i.e., do not reject) when:
   - The product has an audit classification (not `unclassified`), AND
   - `audit_confidence >= 0.50`, AND
   - The audit's `canonical_path` matches the canonical's expected path from the bridge (Step B).
3. Run a debug pass against the universe sweep (no new sweep — use existing `universe_calc.json`).
4. Compare: how many products were `_reject_combo_product`-rejected but had clean audit classifications? Those are the false negatives.
5. Ship the demote when the false-negative count is meaningful and no new false-positives appear.

**Verification:**
- macaroni: products legitimately tagged `Pantry > Pasta > Macaroni > Plain` now accepted even if title contains the word "pasta".
- bread / tortillas: similarly — products correctly classified to bread/tortilla canonical_paths now accepted even if title contains "bread"/"tortilla".
- No regression: products previously rejected by `_reject_combo_product` AND with audit classifications pointing to a different canonical_path stay rejected (as `audit_path_mismatch`).

**Commit:** `ruvs: Part 3 - _reject_combo_product demoted to unclassified-fallback`

---

## Step D — Cache enrichment for cache-poor canonicals (Part 6)

**Files:** `Hestia/api/scripts/enrich_api_cache.py` (new) or extend an existing enrichment script.
**Effort:** S–M (~30–60 min). **Risk:** low (additive to api_cache.db). **Reversible:** yes.

**Action:**
1. Identify canonicals with `accept rate < 10%` AND where the rejection reasons indicate cache-poverty (most candidates are obvious wrong products like "macaroni salad" for the macaroni canonical, "brown sugar oatmeal" for brown sugar).
2. For each, search `master_products.db.products` (FDC) for products with the canonical's expected `branded_food_category` and matching FDC IDs to audit's `Pantry > Pasta > Macaroni > Plain` (or equivalent).
3. Pull those FDC products + their UPCs + descriptions into a new pseudo-cache entry under a key like `{canonical}_fdc_enrichment:25`.
4. Re-run the calculator on the affected recipes. Acceptance count should rise.

**Constraint:** no live API calls. Pull only from `master_products.db` and the existing audit. If a canonical has no FDC products that match its audit path, log it as a cache-coverage gap (input for a future live-search pass).

**Verification:**
- macaroni recipe (36094) accepts > 0 plain dry macaroni products.
- white sugar / brown sugar recipes accept > 0 plain granulated/brown sugar.

**Commit:** `ruvs: Part 6 - api_cache enrichment from master_products.db FDC corpus`

---

## Step E — Test sweep on the 19 required canonicals (Part 7)

**Files:** `Hestia/api/scripts/test_required_canonicals.py` (new).
**Effort:** M (~1 hr). **Risk:** none (read-only). **Reversible:** n/a.

**Action:**
1. For each of the 19 canonicals from spec Part 7:
   - Pick a representative recipe (use `universe_calc.json` to find one that hits this canonical).
   - Run the calculator with `RUVS_PRODUCT_DEBUG_PATH` set.
2. Aggregate per canonical:
   - raw test ingredient
   - resolved canonical
   - expected nutrition codes
   - expected retail path (from bridge DB)
   - candidates found
   - accepted count / rejected count
   - top 5 accepted products with prices
   - top 10 rejection reasons
   - flags: ESHA override fired? retail matching ran? `_reject_combo_product` fired? audit classification used?
3. Output: `Hestia/api/data/required_canonicals_report.md`.

**Verification:** all 10 spec Part 8 win conditions checked off.

**Commit:** `ruvs: Part 7 - 19-canonical test sweep, before/after report`

---

## Step F — Final deliverables (Part 10)

**Files:** `Hestia/api/data/structured_matcher_final_report.md`.
**Effort:** S (~30 min). **Risk:** none (write-only). **Reversible:** n/a.

**Action:**
1. Aggregate everything: Steps A–E results.
2. Bucket remaining failures into the spec's 6 categories:
   - canonical resolution failures (Problem A)
   - no retail candidates (cache miss; survives Step D)
   - unclassified retail products (BM25 below threshold)
   - audit classification conflict
   - package size / grams extraction failure
   - true ambiguous ingredient (LLM territory; deferred)
3. Recommend on `canonical_retail_bridge` adoption (expected: yes).
4. Answer the gating question:

   > Can we now use structured audit classification as the primary product acceptance path and demote `_reject_combo_product()` to unclassified-fallback only?

5. Update `GOAL.md` "State of Work" to reflect everything DONE.

**Commit:** `ruvs: structured matcher final report + GOAL state update`

---

## Total effort

A + B + C + D + E + F ≈ **5 hours** of focused work, no agent dispatch, no LLM calls.

Critical path: A → B → C → E → F. Step D can run after A (independent of B/C).

## Stop points (verify before moving on)

- After A: macaroni line shows retail matching ran (path includes `shopping_products:`).
- After B: bridge has rows for the 19 test canonicals.
- After C: false-negative count from `_reject_combo_product` measurable; demote ships only if safe.
- After D: macaroni and white sugar accept > 0 plain products.
- After E: all 10 win conditions verified.
- After F: report shipped, GOAL updated, hand off.

## What we will NOT do in this plan

- Add more `if canonical_key == "..."` branches.
- Extend any title blocklist.
- Call DeepSeek / Claude / OpenAI / any LLM.
- Live Walmart/Kroger API calls (cache + master_products is enough for tonight).
- Touch nutrition routing through ESHA (Step 7 of FIX_PLAN — owner review first).
- Dispatch background agents for individual steps.
