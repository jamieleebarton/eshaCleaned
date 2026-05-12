# Plan — Marry product_esha_fixy.csv with fixy_done/ ground truth

## What I actually found (vs what we assumed)

`fixy_done/` is **5,203 CSVs, one per FNDDS code, 1,034,537 curated fdc_id→FNDDS assignments**. This is ground truth.

Audit of `product_esha_fixy.csv` (462,646 rows) against that truth:

| Bucket | Rows | % |
|---|---|---|
| fdc_id in ground truth, **agrees** with current fndds | 127,847 | 27.6% |
| fdc_id in ground truth, **disagrees** | 874 | 0.2% |
| fdc_id in ground truth, **no fndds assigned** | 65,993 | 14.3% |
| fdc_id **NOT** in ground truth | 267,932 | 57.9% |

**Disagreements are tiny — and they're mostly minor sibling-code drift** (e.g. "Apple chips" 62101300 vs 62101102, both correct).

**The user's pain points (almond→soy, apple→honey) are NOT product-level errors. They live at the ESHA-code ↔ FNDDS-bucket level inside `esha_fixy_unique_categories.csv`** — one ESHA code (14480 almond milk, 3000 apple) is being mapped to multiple wrong FNDDS codes through bad `fixy_category` bucketing.

There are also **104,444 unique product titles**, 99.9% of which map to a single current FNDDS — strong signal that title-based propagation will work.

---

## Phases

### Phase 1 — Trust the ground truth (instant ~67K wins)
For every product where `fdc_id` exists in `fixy_done/`:
- Overwrite `fndds_main_code` with the truth FNDDS (filename of fixy_done CSV).
- Fixes 874 disagreements + 65,993 unassigned + locks 127K agreements.
- Output column: `fixy_match_source = "fixy_done_truth"`.

### Phase 2 — Title propagation from fixy_done (target the 268K unknowns)
- Build normalized-title index from `fixy_done/*/description`: `norm(title) → FNDDS code` (with confidence = within-FNDDS frequency).
- For each product in main file lacking fdc_id ground truth:
  - Normalize `product_description`.
  - Look up exact title match → assign FNDDS with `fixy_match_source = "title_exact"`.
  - For near-matches (token-set ratio ≥ 0.9 + same first 2 tokens), assign with `"title_fuzzy"`.
- Brand_name remains a hard constraint (memory): never override brand-specific products with a generic title match.

### Phase 3 — Fix the ESHA↔FNDDS bridge (the user's actual complaint)
After Phase 1+2, for each `best_esha_code`:
- Compute distribution of FNDDS codes across all its products.
- The **dominant FNDDS** becomes the authoritative bucket for that ESHA code.
- For ESHA codes where `fixy_category` puts a product in a DIFFERENT bucket than the dominant (e.g. ESHA 3000 "Apple, fresh" appearing under "Honey", "Sport Drinks" categories):
  - Move product to dominant FNDDS.
  - OR, if the product title strongly matches the alternate bucket (e.g. apple juice → 64104010), keep the alternate but flag as "split-identity".
- Output sidecar: `esha_to_fndds_authority.csv` showing the canonical ESHA→FNDDS map.

### Phase 4 — Variant nuance ("chipotle mayo" case)
Within an FNDDS bucket, where multiple ESHA codes are candidates, score by token overlap between `product_description` and `best_esha_description`. Already largely working — only re-rank where current pick has zero shared tokens.

### Phase 5 — Audit residual
Anything still without an FNDDS after 1–4 → `product_esha_fixy.unmapped.csv` for human review.

---

## Outputs
- `product_esha_fixy.v6.csv` — corrected mapping
- `esha_to_fndds_authority.csv` — canonical ESHA→FNDDS table
- `fixy_v6_change_log.csv` — every change with before/after/reason
- `fixy_v6_summary.txt` — counts per phase

## Order of work
1. Implement Phase 1 (1 script, 5 min runtime). Show counts before continuing.
2. Implement Phase 2. Show counts.
3. Implement Phase 3 — this is the real work. Validate against user's stated bad examples (almond milk, apple, chipotle mayo) before broad apply.
4. Phase 4 + 5.

No phase modifies the source files; each writes a new versioned output. Nothing else is mid-run.
