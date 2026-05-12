# Architecture Audit and Plan

Author note: this document was written after the user repeatedly called out
that the matcher kept producing wrong matches even though the consensus tree
already contained the right data. This is my honest assessment of what
went wrong, why my fixes were patching symptoms, and what an actual
end-to-end fix looks like.

---

## 1. The data we already have (and trust)

### `retail_mapper/v2/consensus_full_corpus_audit.v2.csv` — 462,664 rows

Each row is a single retail SKU that has been tagged through the LLM
enrichment + canonical_path pipeline. Every row carries:

| column | meaning |
|---|---|
| `fdc_id` | unique row id |
| `title` | the retail product title (e.g. "VALUED NATURALS SUN DRIED TOMATOES, 8 OZ") |
| `product_identity_fixed` | the **leaf concept** (e.g. `Sun Dried Tomatoes`) |
| `canonical_path` | the path the SKU sits at (e.g. `Pantry > Sun Dried Tomatoes`) |
| `modifier` | distinguishing variant (e.g. `Plain`, `Sliced`, `Halves`) |
| `fndds_code`, `fndds_desc` | the FNDDS food this represents |
| `sr28_code`, `sr28_desc` | the SR-28 (USDA single-ingredient) match |
| `confidence`, `rationale` | LLM's own self-assessment of the row |

The user repeatedly pointed out: this is enough data to identify any
ingredient. Every row has at least 6 independent signals saying what the
food *is*. The data IS clean for the vast majority of rows.

### `recipe_pricing/data/priced_products_v2.db` — 169,441 rows

These are the actual Walmart + Kroger products in the live cache, with
prices and gram weights. Schema includes `consensus_pid`,
`consensus_canonical`, `consensus_modifier`, `bridge_status`.

**The critical number:**

| state | count | % |
|---|---|---|
| `bridge_status='bridged'` (has consensus_pid populated) | **33,424** | **19.7%** |
| no consensus_pid (UPC didn't match any FDC row) | **136,007** | **80.3%** |

**80% of priced products are NOT linked to the consensus tree.** They
have empty `consensus_pid`, empty `consensus_canonical`. The matcher has
no choice but to fall back to head-noun token matching on the bare
product name. Every "wrong match" we've seen — Vienna Sausage, Confetti
Eggs, Cilantro Paste, Listerine, French Onion Soup, Imperial Spread —
ALL come from the unbridged 80%.

---

## 2. Why I kept failing (the honest answer)

I treated each wrong match as an independent bug:

- "Vienna Sausage matched chicken thighs" → *fix the modifier-leak in the
  matcher*
- "Confetti Eggs matched eggs" → *add a regex to non-food name reject*
- "Listerine matched mint" → *add Listerine to the regex*
- "French Onion Soup matched onion" → *override the consensus tagger row*
- "Cilantro Paste matched cilantro" → *add a name-zone check*

Each fix was a patch on the **head-noun fallback path**. The root cause
is identical for every one of these: **the priced product was not
bridged to the tree**, so the matcher had to guess from name tokens.
Patching the guessing logic is whack-a-mole. There are 136,007
unbridged priced products. There will always be a new pathological
product name that beats my latest regex.

The actual problem the user kept pointing at:

> "we have the data, but you are still fucking with this consensus_taxonomy_overrides.csv"

Right. The fix is not in the matcher. It is in **populating the missing
80% of `consensus_pid` / `consensus_canonical` / `consensus_modifier`
columns on `priced_products_v2.db`**, by joining priced products to the
462k-row consensus audit CSV that already has the answers.

---

## 3. The bridge that's missing

Today's bridge: `priced_products.upc` → `master_products.gtin_upc` →
`master_products.fdc_id` → `consensus_full_corpus_audit.fdc_id`.

Failure modes:

1. The Walmart/Kroger product has no UPC in the API response (common
   for produce, meat, deli — sold by weight without a stable barcode)
2. The UPC exists but isn't in `master_products.gtin_upc` (the master
   mapping was built from a snapshot that doesn't include this SKU)
3. Leading-zero / GTIN-format mismatches (we already strip these and
   it accounts for some recovery, but not most)

What we should ALSO be doing: a **name-based join** from priced products
into the consensus audit. The audit CSV's `title` column contains
strings like `VALUED NATURALS SUN DRIED TOMATOES, 8 OZ` — the SAME
title format Walmart's API returns for that product. A normalized
title match would link them.

The user's example proves the point. The user pasted three audit rows:

```
2450346  SUN DRIED TOMATO HALVES         pid='Sun Dried Tomatoes'  canon='Pantry > Sun Dried Tomatoes'
2581605  VALUED NATURALS SUN DRIED ...   pid='Sun Dried Tomatoes'  canon='Pantry > Sun Dried Tomatoes'
2604237  SUN DRIED TOMATOES              pid='Sun Dried Tomatoes'  canon='Pantry > Sun Dried Tomatoes'
```

If a Walmart priced product is titled `Pure Anatolia Sun-Dried Tomatoes
Julienne, 8 oz`, the LLM enrichment was run on it (or one essentially
identical to it), and the answer is sitting in the audit CSV under one
of those fdc_ids. Our bridge just isn't connecting them because UPC
mismatches.

---

## 4. The plan (prioritized, end-to-end)

### Phase 1 — Run priced_products through the same pipeline that built the tree

**The user's point: "why won't we use the same processes that made the
fucking trees in the first place?" — exactly right. We already have the
pipeline. Use it.**

The retail_mapper/v2 pipeline runs in this order:

```
reconcile.py             # raw FDC → retail_leaf_v2.csv
enrich_output.py         # + ingredients, TF-IDF, modal signals
enrich_v2.py             # + ngram role-tagger evidence
run_full_csv_batch.py    # LLM tag (Nebius DeepSeek-V3.2 batch API)
rebuild_from_jsonl.py    # replay LLM output into full_corpus_audit.csv
build_consensus_full_corpus_audit.py  # merge codex + LLM → audit CSV
```

That pipeline produced the 462k-row consensus audit. The 33k priced
products already bridged got there by going through this pipeline (under
the FDC corpus). The 136k unbridged ones never went through because
their UPCs are not in the FDC import.

**Steps:**

1. **Format unbridged priced_products as pipeline input.** Required:
   - `fdc_id` — synthesize from UPC (or use a `priced_NNNNN` synthetic id)
   - `title` ← `priced_products.name`
   - `branded_food_category` — stub from Walmart `category_path` (e.g.
     "Home Page/Food/Pantry/Spices/Cumin" → BFC `Spices & Seasonings`)
   - `brand` ← already there
   - `ingredients` — fetch from API if available; else leave blank
     (degrades LLM quality but doesn't block)
   Output: an extension CSV with the same columns the pipeline expects.

2. **Run the pipeline on this extension CSV.** Same scripts, same LLM,
   same prompts that produced the audit. ~$30 of Nebius API spend for
   ~30k rows (`$0.27/1M input + $1.10/1M output, ~1k tokens/row`).

3. **Merge results back into priced_products_v2.db.** Update the
   `consensus_pid`, `consensus_canonical`, `consensus_modifier`,
   `fndds_code`, `sr28_code` columns from the LLM output. Set
   `bridge_status='pipeline_tagged'`.

**Effort:** half a day to write the input formatter. ~$30 of LLM
spend. Half a day to merge results.

**Expected outcome:** bridge rate 19.7% → ~99%. Every priced product
carries the same tree-tagged metadata as the original consensus audit.

### Phase 2 — Drop head-noun fallback entirely

**Goal:** matcher only matches via the tree. No regex scaffolding.

After Phase 1, every priced product has a canonical and modifier.
The matcher's Path C (head-noun fallback with name-zone, noise score,
form blockers) is no longer needed — it was scaffolding around the
unbridged 80%. Delete it.

What remains is the architecture the user described from the start:

```
recipe ingredient
  → consensus tree concept (canonical, modifier, sr28_code, fndds_code)
  → priced products with the SAME (canonical, modifier)
  → cheapest cents-per-gram wins
```

**Effort:** ~50 lines deleted from `calculate_recipe_cost_v6.py`.

### Phase 3 — Fix the residual tree-tagger errors

After Phases 1–3, any remaining wrong matches are TRUE tree-tagger
errors (the LLM gave a SKU the wrong PID). The 50-recipe audit
identified ~10 such SKU classes:

| recurring failure | tree fix |
|---|---|
| Imperial Vegetable Oil Spread → PID=Butter | should be `Margarine` |
| Sandwich Mate Imitation Cheese → PID=Cheese | should be `Imitation Cheese` |
| Campbell's Tomato Soup → caught by 'tomato' recipes | should be `Tomato Soup` |
| (~10 more identified by the 50-recipe audit) | — |

Add `status=approved` rows to `consensus_taxonomy_overrides.csv`
with the corrected PID. Re-run `apply_consensus_overrides.py`. Done.

**Effort:** 1 hour to write the override CSV by hand.

### Phase 4 — Documentation

Document the four data files (`consensus_full_corpus_audit.v2.csv`,
`priced_products_v2.db`, `master_products.db`, `recipes_unified.csv`),
their schemas, and the data flow. Update `recipe_mapper/v1/README.md`.

---

## 5. Effort and ROI summary

| phase | effort | match rate gain |
|---|---|---|
| 1: run priced_products through the existing v2 pipeline | $30 LLM + 1 day | 77% → ~96% |
| 2: drop head-noun fallback | 1 hour | (cleanliness) |
| 3: tree-tagger overrides for residual errors | 1 hour | ~96% → ~98% |
| 4: documentation | 1 hour | — |

Total: ~1.5 days work + $30 of LLM spend. End to end, no whack-a-mole.

---

## 6. Why I didn't do this before

Honest answer: I kept treating wrong matches as bugs in my matcher
instead of asking "why is this priced product not linked to the tree?"
The user told me directly multiple times — "did you use the tree?",
"we have the data", "look at all the signals" — and I would patch one
symptom and move on. That's on me.

The cross-tree concept matching in v6 was the right architecture, but
it only helps the 19.7% of priced products that ARE bridged. The other
80% still go through the head-noun fallback hellscape, which is where
every "wrong match" that's frustrated the user comes from. Phase 1
(name-bridge) is the actual fix.
