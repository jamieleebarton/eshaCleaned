# Canonical Signature Pipeline — Design

**Date:** 2026-04-26
**Status:** Draft, awaiting user review
**Approach:** Hybrid cascade (rules → lexical → embedding → attribute disambiguation → composite routing)

---

## 1. Problem

Branded product descriptions in `product_to_best_esha_full_map.vM.csv` (462k rows) are noisy free-text:

```
NATURE'S PLACE, ORGANIC APPLES
GOLDENS FRESH SLICED APPLES
MADHAVA, RAW ORGANIC AGAVE NECTAR
CHAR-SIU MANAPUA STEAMED BUN WITH ROAST SWEET PORK FILLING
```

Each string mixes brand, marketing fluff, form, flavor variant, head noun, and sometimes composite/multi-ingredient signals. The current `best_esha_*` assignment is unreliable because the matcher is fed raw strings and has no structured way to:

- distinguish *cinnamon* applesauce from plain applesauce,
- collapse a bazillion brand variants of "agave nectar" onto one anchor,
- recognize that `CHAR-SIU MANAPUA ... WITH ROAST PORK FILLING` is a composite that should not be forced under a single ingredient row.

## 2. Goal

Produce a deterministic, auditable mapping from each product row to a **canonical signature** and a single best-anchor row in `canonical_surface_normalized_with_product_proxies.csv` (18k rows). Each match carries a per-layer trace so disagreements are debuggable.

**Non-goals:** rebuilding the canonical surface; nutrition recomputation; any changes to FNDDS/SR28/ESHA reference codes.

## 3. Inputs

- `/Users/jamiebarton/Desktop/clean/canonical_surface_normalized_with_product_proxies.csv` — 18,379 rows. Columns of interest: `canonical_surface`, `canonical_normalized`, `family_base`, `prep_attributes`, `form_attributes`, `state_attributes`, `style_attributes`, `packaging_attributes`, `brand_candidate`, `sr28_code`, `fndds_code`, `esha_code`, `*_description`.
- `/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/product_to_best_esha_full_map.vM.csv` — 462,647 rows. Columns of interest: `gtin_upc`, `fdc_id`, `product_description`, `branded_food_category`, `brand_owner`, `brand_name`, current `best_esha_code/description/head/family`, `score`, `assignment_source`.

## 4. The Canonical Signature

Every product gets reduced to a tuple:

```
signature = (
    head_noun,            # primary food noun, lemma form: "applesauce", "ice_cream", "agave_nectar"
    modifiers: frozenset, # qualifying tokens that change identity: {"cinnamon"}, {"strawberry"}
    form: str | None,     # "sliced", "whole", "liquid", "crushed"
    state: str | None,    # "raw", "cooked", "frozen", "dried"
    flavor: str | None,   # broken out of modifiers when applicable for facet matching
    style: str | None,    # "organic" only when it maps to a distinct canonical row, else dropped
    composite: bool,      # true if multi-ingredient signal detected
    secondary_ingredients: list[str]  # only populated when composite=true
)
```

Two products with the same signature ARE the same thing. The "tree" view is a `GROUP BY head_noun → modifier_set` over signatures — emergent, not modeled separately.

## 5. Pipeline

### L1 — Normalize
Lowercase, NFKD unicode, strip punctuation except commas (commas carry brand-prefix signal), expand abbreviations (`org.` → `organic`, `w/` → `with`, `&` → `and` only when not adjacent to single-letter tokens).

### L2 — Strip brand
Two passes:
1. **Deterministic:** if `brand_name` or `brand_owner` from the row appears as a token-prefix of the description, strip it. The `BRAND, REAL DESCRIPTION` comma pattern is the strongest signal.
2. **Heuristic:** known-brand vocabulary built from the empirical distribution of `brand_name` values, applied when (1) misses (private label, missing brand fields).

Output: `description_no_brand`.

### L3 — Strip marketing fluff & extract attributes
Pull tokens off `description_no_brand` into the structured attribute columns mirroring the canonical surface schema. Vocabulary lists drive each:

- **Drop entirely** (no canonical impact): `premium`, `gourmet`, `selection`, `choice`, `fresh-picked`, `farm-fresh`, `all-natural`, `100%`, `pure`, `real`, `authentic`.
- **Keep as `state`:** `raw`, `cooked`, `roasted`, `dried`, `frozen`, `canned`, `fresh`.
- **Keep as `form`:** `sliced`, `diced`, `whole`, `chopped`, `crushed`, `ground`, `liquid`, `powder`.
- **Keep as `style`:** `organic`, `kosher`, `halal`, `non-gmo` — *only when a corresponding canonical row exists*; otherwise drop. Decision made per-token by checking presence in canonical surface's `style_attributes` distribution.
- **Keep as `packaging`:** `packets`, `tray`, `cup`, `bag`, `bottle`.
- **Keep as `flavor`:** any token from a `flavor_vocabulary` set built from canonical surface variants (`cinnamon`, `vanilla`, `chocolate`, `strawberry`, `mint`, `peach`, …).

What remains after extraction is the **residual noun phrase**. The rightmost noun-like token of the residual is the **head noun candidate**.

### L4 — Lexical match
Match `residual` against `canonical_surface.canonical_normalized` using two TF-IDF vectorizers in parallel, both pre-built once and cached:

- **Char n-grams (3–5)** — handles `applesauce ≈ apple sauce ≈ apple-sauce` naturally.
- **Word n-grams (1–3)** — handles phrase order and multi-word heads.

Combined score = `0.6 * cosine_char + 0.4 * cosine_word`. Top-5 candidates retained.

### L5 — Embedding fallback
If best L4 score < `LEXICAL_THRESHOLD` (start at 0.55, tune empirically), embed the residual with `sentence-transformers/all-MiniLM-L6-v2` and re-rank the top-50 lexical candidates by embedding cosine. Catches `frozen dessert ≈ ice cream`, `bell pepper ≈ sweet pepper`.

### L6 — Attribute disambiguation
Among the top candidates remaining after L4/L5, pick the one whose canonical attribute columns best match the product's extracted attributes. Scoring: `+1` per matching attribute, `-0.5` per mismatching attribute, `0` for missing. Tie-break by lexical score.

This is the layer that separates *cinnamon applesauce* from *applesauce* and *vanilla ice cream* from *chocolate ice cream* — the head matches multiple canonical rows; attribute overlap picks the right one.

### L7 — Composite routing
Trigger words on the (pre-strip) description: `with`, `and`, `&`, `filled`, `stuffed`, `topped`, `over`, `&`, `plus`, `containing`. Multi-noun heuristic: ≥2 distinct canonical head-nouns detected in residual.

When triggered:
1. **Try `branded_food_category` lookup** against a `category_to_canonical_anchor` table (built once, hand-curated for the top ~100 categories that cover the long-tail composites — bao, sandwiches, soups, prepared salads, frozen meals).
2. If category maps to an anchor, use it. Confidence `composite_via_category`.
3. If no category mapping, set `composite=true`, populate `secondary_ingredients` with detected head-nouns, leave `canonical_anchor=NULL`. Confidence `composite_unresolved`. These get reviewed in a follow-up pass — out of scope for this design.

### L8 — Provenance
Every output row carries:

```
match_layer: "L4_lexical" | "L5_embedding" | "L6_disambiguated" | "L7_category" | "L7_unresolved"
stripped_brand: str
stripped_fluff: list[str]
extracted_attributes: dict
residual: str
top_candidates: list[(canonical_id, score)]   # top 3
match_confidence: float in [0, 1]
match_reason: human-readable one-liner
```

That's the audit trail. No black-box matches.

## 6. Output Schema

New artifact: `/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/product_to_canonical_signature.csv`.

Columns:

| column | source |
|---|---|
| `gtin_upc`, `fdc_id`, `product_description`, `branded_food_category`, `brand_name` | passthrough from input |
| `signature_head_noun` | L3 output |
| `signature_modifiers` | L3 output (semicolon-joined) |
| `signature_form`, `signature_state`, `signature_flavor`, `signature_style` | L3 output |
| `composite` | bool, L7 |
| `secondary_ingredients` | semicolon-joined, L7 |
| `canonical_surface` | matched row's `canonical_surface` value |
| `canonical_normalized` | matched row's `canonical_normalized` value |
| `sr28_code`, `fndds_code`, `esha_code` | inherited from matched canonical row |
| `match_layer`, `match_confidence`, `match_reason` | L8 |
| `stripped_brand`, `stripped_fluff`, `extracted_attributes_json`, `residual` | L8 (debug columns) |
| `top_candidates_json` | L8 |
| `prev_best_esha_code`, `prev_score` | passthrough for diffing against current vM assignment |
| `assignment_changed` | bool: did this disagree with vM's prior assignment? |

A second artifact, `signature_groups.csv`, is the implicit "tree view": one row per unique `(signature_head_noun, signature_modifiers, signature_form, signature_state, signature_flavor)` tuple, with `product_count`, `representative_descriptions[5]`, `canonical_anchor`. This is what the user browses to verify "yes, all 47 of these collapsed correctly onto agave nectar."

## 7. Validation / Acceptance

Before shipping:

1. **Spot-check sample.** Random 200 products + the user's 14 hand-picked examples → manual eyeball, target ≥95% correct.
2. **Composite recall.** Of products containing `with`/`&`/`filled`, ≥80% should be flagged `composite=true`.
3. **Collapse ratio.** Number of unique signatures should be ≪ number of unique product descriptions; report the ratio per `family_base` so we can see e.g. "47 agave nectar variants collapsed to 2 signatures."
4. **Diff vs vM.** `assignment_changed=true` rate should be substantial (the existing assignments are known to be unreliable) but not chaotic; spot-check 100 changed assignments to confirm changes are improvements.
5. **Coverage.** ≥90% of non-composite products should reach an anchor with `match_confidence ≥ 0.5`.

## 8. Open Questions / Deliberate Deferrals

- **Vocabulary lists** (fluff, form, state, flavor) start hand-seeded from inspection of the canonical surface attribute columns. They will need iteration. First pass: derive from frequency analysis of canonical_surface attribute columns + a small manual seed.
- **Composite category map** — top-100 categories will be hand-curated as part of build. The long tail of composites stays unresolved until a follow-up pass.
- **Embedding cost** — 462k products is fine to embed once and cache (~30min on CPU, faster with MPS on macOS). Canonical surface (18k) trivial.
- **Reproducibility** — pipeline is a single Python module with deterministic outputs given fixed vocabulary lists and embedding model version. Pin both.

## 9. Out of Scope

- Re-scoring or recomputing nutrition values
- Modifying `canonical_surface_normalized_with_product_proxies.csv`
- Resolving composites flagged as `composite_unresolved` (separate workstream)
- UI / browse interface for `signature_groups.csv` (just a CSV)
