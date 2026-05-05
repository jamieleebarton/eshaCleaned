# Data Dictionary — recipe_mapper/v1/output/

Quick reference for the columns in each output CSV/JSON. All paths relative
to `/Users/jamiebarton/Desktop/esha_audit_bundle/recipe_mapper/v1/output/`.

---

## consensus_htc_tagged.csv  (462,664 rows)

One row per retail SKU in `consensus_full_corpus_audit.csv`, plus the HTC code.

| column | source | description |
|---|---|---|
| fdc_id | consensus | FDA / FDC product ID |
| title | consensus | Raw product title |
| branded_food_category | consensus | Retail BFC string |
| product_identity_fixed | consensus | Audit-fixed identity noun |
| canonical_path | consensus | Audit canonical taxonomy path |
| modifier | consensus | Audit modifier ("Sharp Cheddar > Sliced") |
| fndds_code | consensus | FNDDS food code (composite anchor) |
| sr28_code | consensus | SR-28 NDB number (single-ingredient anchor) |
| **htc_code** | encoder | 8-char HTC code |
| htc_group … htc_ptype | encoder | individual position chars |
| htc_check | encoder | Crockford mod-37 check digit |
| htc_confidence | encoder | 0.2–0.9 (higher = stronger source signal) |
| htc_source | encoder | `category` / `description` / `extra` / `family_fallback` / `non_food` |

---

## recipe_ingredient_items.csv  (74,624 rows)

One row per unique normalized recipe ingredient `item` string.

| column | description |
|---|---|
| item | normalized lowercase ingredient noun (e.g. "ground cardamom") |
| recipe_count | number of recipes referencing this item |
| grams_total | sum of grams across all references |
| sample_displays | up to 5 raw display strings (`||`-joined) |
| sample_recipes | up to 3 sample recipe titles |

---

## recipe_ingredient_htc_tagged.csv  (74,624 rows)

The HTC code per unique ingredient.

| column | description |
|---|---|
| item, recipe_count, grams_total | same as above |
| htc_code … htc_ptype, htc_check | same as encoder columns above |
| htc_confidence | 0.2–0.9 |
| htc_source | `category` (rare for recipes) / `description` / `family_fallback` / `non_food` |

---

## recipe_lines_htc.csv  (4,729,696 rows)

One row per ingredient line in every recipe — i.e. the recipe-level join.

| column | description |
|---|---|
| recipe_id | recipe_qa.db recipe_id |
| recipe_title | clean title |
| ingredient_item | the parsed `item` field from ingredients_json |
| display | the raw display string ("1 1/2 cups whole milk") |
| grams | gram value already in the recipe blob (when present) |
| htc_code … htc_ptype | resolved code |
| htc_source, htc_confidence | as above |
| match_status | `tagged` / `high_conf` / `non_food` / `unresolved_group` / `no_match` |

---

## recipe_htc_coverage_summary.json

Aggregate stats over the 4.7M lines + 491k recipes. Keys:
- `n_recipes`, `n_ingredient_lines`
- `n_lines_with_htc`, `pct_lines_with_htc`
- `n_lines_high_conf`, `pct_lines_high_conf`
- `n_lines_non_food`, `pct_lines_non_food`
- `n_lines_unmatched`
- `n_recipes_fully_high_conf`, `pct_recipes_fully_high_conf`
- `by_group`: dict of group code → count
- `top_codes`: list of [htc_code, count] for the 25 most-common codes

---

## sr28_gram_weights.csv  (9,154 rows)

Primary gram-weight table from SR-28 `food_portion.csv`. Unit name comes from the legacy `modifier` text column (because `measure_unit_id=9999` is "undetermined").

| column | description |
|---|---|
| fdc_id | SR-28 fdc_id |
| ndb_number | SR-28 NDB number (the legacy code) |
| description | from sr_legacy_food food.csv ("Milk, whole, 3.25% milkfat …") |
| unit | normalized: cup, tbsp, tsp, fl_oz, oz, ml, l, g, kg, lb, quart, pint, gallon, dash, pinch, slice, stick, package, serving, piece |
| grams_per_unit_median | median g/unit from observations (typically 1) |
| n_observations | count of underlying food_portion rows |

---

## htc_gram_weights.csv  (9,151 rows)

Same table joined to HTC via the consensus retail bridge.

| column | description |
|---|---|
| htc_code, htc_group | as encoded |
| unit | as above |
| grams_per_unit_median | median across all linked SR-28 codes |
| n_sr_codes | how many SR-28 NDBs back this row |
| sr_codes_sample | up to 10 supporting NDB numbers |

---

## htc_group_default_grams.csv  (259 rows)

Group-level fallback (used when an HTC code has no retail SR-28 link).

| column | description |
|---|---|
| htc_group | one char (1, E, F, …) |
| unit | normalized unit |
| grams_per_unit_median | median across the group |
| n_observations | count |

---

## htc_facet_vocab.json  (2,063 keys)

Per-HTC controlled facet vocabulary mined from consensus columns.

```json
{
  "1000600D": {
    "modifier":     [["Whole", 247], ["Reduced Fat", 760], ...],
    "claims":       [["organic", 593], ["lactose_free", 202], ...],
    "form_texture_cut":   [["dry", 46], ...],
    "processing_storage": [["ultra_pasteurized", 27], ...],
    "flavor":       [["vanilla", 22], ...],
    "variant":      [["whole", 239], ...]
  },
  ...
}
```

Used by `match_recipes_unified.py` to extract structured facets from a recipe's `display` string. Also used at retrieval time to filter products by facet (so "mayonnaise" with no flavor extracted excludes Chipotle Mayo).

---

## htc_facet_vocab_summary.csv  (2,063 rows)

Quick coverage view.

| column | description |
|---|---|
| htc_code | 8-char code |
| n_facet_types | number of facet types populated (max 6) |
| total_facet_values | sum of distinct values across all facets |

---

## recipes_unified.csv  (4,729,696 rows — Phase 6 final output)

**One row per ingredient line, fully resolved.** This is the artifact downstream calculators consume.

| column | description |
|---|---|
| recipe_id, recipe_title, ingredient_item, display | from recipe_qa.db |
| qty | extracted numeric quantity (parsed from display) |
| unit | normalized unit ("cup", "tsp") |
| grams_blob | gram value from the recipe blob (already there for ~99%) |
| grams_resolved | final grams (blob if present, else qty × htc_gram_weights[(code, unit)]) |
| grams_source | `blob` / `htc_level` / `group_default` / `` |
| htc_code, htc_group, htc_confidence | identity + reliability |
| facet_flavor | extracted from display against the HTC's flavor vocab |
| facet_form | from form_texture_cut vocab |
| facet_processing | from processing_storage vocab |
| facet_claims | from claims vocab |
| facet_modifier | from modifier vocab |
| facet_variant | from variant vocab |

Filter to `htc_confidence >= 0.6 AND grams_resolved IS NOT NULL` for fully-calculable lines.

---

## recipes_unified_summary.json  (Phase 6 corpus stats)

- `n_recipes`, `n_lines`
- `pct_with_qty`, `pct_with_unit`, `pct_with_grams_resolved`, `pct_with_facets`
- `facet_hit_counts`: per-facet-type total hits
- `grams_source_counts`: blob vs htc_level vs group_default
- `n_recipes_fully_calculable`, `pct_recipes_fully_calculable`

---

## Older / superseded outputs (kept for diff)

| file | what it was |
|---|---|
| `consensus_tree_nodes.csv` | pre-HTC: deduped consensus nodes (10,525 rows) |
| `identity_registry.json/csv` | pre-HTC: `Domain.Class.Type` codes (33,221 rows) |
| `recipe_ingredient_consensus_match.csv` | pre-HTC: tree-anchored matches |
| `recipe_ingredient_identity_codes.csv` | pre-HTC: dotted-name codes |
| `recipe_ingredient_taxonomy.csv` | pre-HTC: ESHA-anchored kNN |
| `recipe_ingredient_taxonomy_smoke.csv` | pre-HTC: 2k smoke test |
| `recipe_ingredient_fndds.csv` | pre-HTC: FNDDS-only matches |
| `recipe_coverage.csv`, `recipe_coverage_summary.json` | pre-HTC application |
| `recipe_ingredient_lines_coded.csv` | pre-HTC lines (use `recipe_lines_htc.csv` instead) |
