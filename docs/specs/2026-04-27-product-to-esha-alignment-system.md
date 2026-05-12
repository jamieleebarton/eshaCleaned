# Product → ESHA Alignment System (Design v1)

Date: 2026-04-27
Status: design proposal — not yet implemented

## Problem statement

Map each of 462,646 retail products to:
- exactly one ESHA code (primary), and
- consistent FNDDS + SR28 proxies on the same path

…or label `NEEDS_NEW_CONCEPT` if no acceptable match exists.

Hard constraints (from prior failures, codified):
- **brand_name homogeneity** within any group treated as one product
- **identity-noun match** between product and assigned reference (chicken == chicken, not tuna)
- **form-family match** (cookie != cake, cream != milk, juice != drink)
- **category-lane compatibility** (dairy != snack)

## Why prior approaches failed

| Approach | Failure mode |
|---|---|
| KG-RFT | Coverage low; identity guards correct but no recall mechanism |
| Token clustering (`retail_head_envelope_v7`) | Clean for tight clusters, no signal on long tail |
| Concept-anchor seafood POC | Right shape but applied to one category only |
| Embedding + Leiden + centroid kNN (this attempt) | Embeddings are category-aware, not identity-aware. Centroid kNN collapsed proteins (chicken→tuna) and brand-cohorts (Apple Jacks→all bran). Cluster-centroid is the wrong unit of alignment. |

The lesson: **embeddings are a recall tool, not a precision tool.** They generate candidates; they cannot decide.

## Design principle

> Use embeddings ONLY for top-K candidate generation. Use deterministic rules (identity nouns, form families, category lanes) for the actual decision.

Rules are authoritative. Cosine is a tiebreaker.

## Architecture (six layers)

### L1. Product fact extraction

Use `implementation/output/self_heal/product_facts.csv` directly. It has, per product:
- `identity_terms` — what the product IS (chicken, milk, cookie, sandwich)
- `product_form` — physical/cooking form (fluid, baked, frozen, dry, fresh)
- `product_role` — main / ingredient / condiment / beverage
- `category_lane` — broad bucket (dairy / produce / snack / meat / baked_goods)
- `target_heads` — already-curated likely ESHA leaf terms
- `brand_name`, `branded_food_category`

This already exists for all 462,646 products. Don't rebuild.

### L2. Reference fact catalog

Apply the SAME extraction code path used by `product_facts` to ESHA/FNDDS/SR28. Output:

`reference_facts.csv` — one row per reference entry with `{ref_id, source, raw_text, identity_terms, product_form, category_lane, flavor_terms, embedding_id}`.

Sizes: ESHA 39,691 + FNDDS 10,585 + SR28 7,793 = ~58k rows. One-time build.

### L3. Candidate generation (where embeddings earn their keep)

For each of the 462k products, retrieve **top-20 candidates per source** via FAISS kNN against the per-source embedding indexes (already built). Output: `product_candidates.parquet`, ~462k × 60 = 28M rows.

This is recall-only — bring back anything plausibly close. Precision happens next.

### L4. Identity-gated scoring

For each `(product, candidate)` pair, run **hard gates first**:

```
G1. identity_gate:    product.identity_terms ∩ candidate.identity_terms != ∅
G2. form_gate:        product.product_form ∈ compatible_forms[candidate.product_form]
G3. category_lane:    product.category_lane ∈ compatible_lanes[candidate.category_lane]
```

Any gate failure → candidate rejected. No score, no consideration.

For survivors, compute a **soft score**:

```
score = 0.40 * cosine_sim
      + 0.25 * jaccard(identity_terms)
      + 0.15 * jaccard(form_terms)
      + 0.10 * flavor_agreement
      + 0.10 * lane_alignment_bonus
```

### L5. Best-source reconciliation (per product)

For each product, after gating:
1. Best ESHA = highest-scored ESHA survivor (or none)
2. Best FNDDS = highest-scored FNDDS survivor (or none)
3. Best SR28 = highest-scored SR28 survivor (or none)

Pick the **chosen path** by score, not by source priority:

| Condition | Status |
|---|---|
| Any source ≥ 0.80 | `CONFIDENT`, pick highest of those |
| Any source ≥ 0.65 | `LOW_CONFIDENCE`, pick highest |
| All sources gated out | `IDENTITY_GATE_FAILED` |
| No survivor anywhere | `NEEDS_NEW_CONCEPT` |

ESHA priority returns ONLY as a tiebreaker when sources are within 0.02 of each other.

Importantly: a product can have, say, ESHA gated out but FNDDS confident. We record all three best candidates — we just use the chosen one for assignment. Disagreement between sources is signal, not noise.

### L6. Cluster aggregation (after assignment, not before)

Group products by signature `(identity_terms_tuple, product_form, brand_name)`. Within each cluster:
- modal assignment + modal_pct (% of cluster products who got same anchor)
- disagreement examples (the minority assignments)
- cluster_status: `CONSISTENT` if modal_pct ≥ 0.90, else `MIXED_REVIEW`

Clusters are an *output*, not a step in the decision. We don't average cluster centroids and ask one question — we ask 462k questions and count the answers.

## Outputs

```
product_to_anchor_v2.csv
  gtin_upc, fdc_id, description, brand_name,
  identity_terms, product_form, category_lane,
  esha_code, esha_label, esha_score, esha_gate_status,
  fndds_code, fndds_label, fndds_score, fndds_gate_status,
  sr28_code, sr28_label, sr28_score, sr28_gate_status,
  chosen_source, chosen_code, chosen_label, final_score,
  status   ← CONFIDENT | LOW_CONFIDENCE | NEEDS_NEW_CONCEPT | IDENTITY_GATE_FAILED

cluster_signatures_v2.csv
  cluster_signature, n_products, modal_assignment, modal_pct,
  disagreement_count, disagreement_examples, cluster_status

needs_new_concept_v2.csv  ← the "vocabulary gap" queue, by category lane
review_queue_v2.csv       ← LOW_CONFIDENCE + IDENTITY_GATE_FAILED, sorted by n_products
```

## Data prerequisites (validate before building)

1. **`self_heal/product_facts.csv`** — must be fresh. Has 462,646 rows as of 2026-04-27 20:33. Confirmed.
2. **Form-compatibility table** — encoded in `vKG_RFT` rejection rules. Need to extract into a single YAML.
3. **Category-lane compatibility table** — likely the same source.
4. **Identity-noun lexicon** — does this exist as a clean list anywhere? If not, scope adds ~half a day.

## Failure cases this fixes

| Prior failure | How v2 catches it |
|---|---|
| CHICKEN SALAD → ESHA "albacore tuna" | identity_gate: product `{chicken,salad}` vs candidate `{tuna,salad}` — REJECTED |
| Apple Jacks → ESHA "all bran" | identity_gate: `{apple}` vs `{bran}` — REJECTED |
| HALF & HALF → SR28 "Apricots, canned" (0.57) | score < 0.65 → NEEDS_NEW_CONCEPT |
| GRACE EVAPORATED FILLED MILK → ESHA "carnation evaporated" | best-source picks FNDDS "Milk filled with vegetable oil" instead |
| Eggnog → ESHA "agglomerated extra grade milk" | gates out (`eggnog` ∉ candidate's identity terms); SR28 "Eggnog-flavor mix powder" wins |
| Cookie/cake leakage | form_gate (cookie family != cake family) |

## What v2 does NOT solve

- Identity nouns missing from the lexicon (niche ingredients, ethnic foods) — fall through to NEEDS_NEW_CONCEPT. Maintainable lexicon expansion needed.
- ESHA leaves that are too coarse (e.g., "all bran" being the only Kellogg's-shaped ESHA item) — that's a vocabulary-gap problem, not an alignment problem. Surfaces in NEEDS_NEW_CONCEPT.

## Implementation phasing (proposal — for review, not action)

| Phase | Output | Time |
|---|---|---|
| P0. Validate `product_facts.csv` freshness, locate form/identity tables | go/no-go | 15 min |
| P1. Build `reference_facts.csv` | ~58k rows, one-time | 1–2 hr |
| P2. Per-source kNN candidate generation (k=20) | `product_candidates.parquet` | 10 min using cached embeddings |
| P3. Identity-gated scoring + reconciliation | `product_to_anchor_v2.csv` | 30 min |
| P4. Cluster aggregation + audit | review queues | 15 min |
| P5. Audit pass (same audit script as v1) | confirms identity-mismatch rate ≈ 0 | 5 min |

## Decision points for you (the user)

1. **Lexicon source** — does a curated identity-noun list exist in the repo, or do I scope building one from `product_facts.identity_terms` distinct values?
2. **Form-compatibility table** — same question. The rules are in `vKG_RFT` source code; do you want them lifted as-is or rewritten?
3. **Threshold values** — 0.80 confident / 0.65 low-confidence are starting guesses. Will calibrate after first run.
4. **Scope** — full corpus run, or known-bad-cases-only smoke test first?

## What I will NOT do without sign-off

- Re-embed (we have the cache)
- Re-cluster
- Touch `product_to_best_esha_full_map.csv` or other live whole-corpus maps
- Promise "this version will work"

The design above explicitly maps every known-bad case from your hand-found list to a specific gate or threshold. If a case here would still slip through, that's a design bug — tell me before we build.
