# Fixy Done Cleanup Notes

As of `2026-04-27`, Fixy is best used as an evidence layer over the incumbent `vM` product-to-ESHA map, not as a blind replacement.

## Inputs

- `canonical_surface_normalized_with_product_proxies.csv`
  - Matcher truth surface.
  - Used to recover identity nouns and trusted ESHA anchors before fallback scoring.
- `implementation/output/product_to_best_esha_full_map.vM.csv`
  - Current incumbent whole-corpus assignment layer used by graph and cleanup checks.
- `fixy_done/`
  - Reviewed Fixy exports.
  - Contains many rows outside the current `vM` product universe.
- `implementation/output/product_to_best_esha_full_map.vCluster.csv`
  - Cluster projection used as another agreement/disagreement signal.
- `graph/review/*`
  - Structural graph rejects and conflict evidence used by the crosscheck.

## Terms

`out_of_scope` or `out_of_vm_scope` means the Fixy row's `fdc_id` is not present in `product_to_best_esha_full_map.vM.csv`.

That is not an error. It means Fixy reviewed a product that is outside the current whole-corpus map. Those rows are useful for future import coverage, but they should not be counted as current-map failures.

`direct_fdc_match` means the Fixy row joins to `vM` by the same `fdc_id`.

`description_bridge_match` means no direct FDC match was found, but the normalized product description matches a unique Fixy description. This is useful because this project works heavily from unique product strings, and different FDC IDs can still describe the same product. This bridge is powerful but riskier than direct FDC overlap.

`blank` quarantine mode physically removes bad assignments from the output map.

`flag` quarantine mode keeps the assignment in place and writes `fixy_cleanup_*` review columns beside it.

## Recommendation

Use the flagged direct-FDC output as the conservative next candidate:

- `implementation/output/product_to_best_esha_full_map.vFixyFlagged.csv`

Why:

- It keeps calculator coverage usable.
- It applies high-confidence Fixy recoveries/remaps.
- It marks suspicious rows for review instead of silently deleting assignments.

Do not promote the strict blanking files directly to the calculator yet. They are useful truth/review artifacts, but they lower coverage by design.

The description-bridge flagged file is useful as a research layer:

- `implementation/output/product_to_best_esha_full_map.vFixyTextFlagged.csv`

That file extrapolates Fixy evidence across identical normalized product descriptions. Treat it as a candidate layer that needs family sampling before promotion.

## Current Output Summary

All rows start from `358,526` assigned rows in `vM`.

| Output | Mode | Description Bridge | Assigned After | Coverage Delta | Remap/Recovery Rows | Quarantine Rows |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `product_to_best_esha_full_map.vFixy.csv` | blank | no | `339,979` | `-18,547` | `5,095` | `21,541` |
| `product_to_best_esha_full_map.vFixyFlagged.csv` | flag | no | `361,520` | `+2,994` | `5,095` | `21,541` |
| `product_to_best_esha_full_map.vFixyText.csv` | blank | yes | `329,310` | `-29,216` | `9,773` | `36,888` |
| `product_to_best_esha_full_map.vFixyTextFlagged.csv` | flag | yes | `366,198` | `+7,672` | `9,773` | `36,888` |

The coverage drop in the blanking files is expected: those runs remove suspect assignments. The flagged files are the safer operational shape because they preserve coverage while surfacing risk.

## Generated Artifacts

Crosscheck:

- `implementation/output/fixy_done_crosscheck/fixy_done_product_crosscheck.csv`
- `implementation/output/fixy_done_crosscheck/fixy_done_review_queue.csv`
- `implementation/output/fixy_done_crosscheck/fixy_done_code_summary.csv`
- `implementation/output/fixy_done_crosscheck/fixy_done_code_review_queue.csv`
- `implementation/output/fixy_done_crosscheck/fixy_done_crosscheck_summary.json`

Direct-FDC cleanup:

- `implementation/output/product_to_best_esha_full_map.vFixy.csv`
- `implementation/output/product_to_best_esha_full_map.vFixyFlagged.csv`
- `implementation/output/fixy_done_cleanup_diff.csv`
- `implementation/output/fixy_done_flagged_cleanup_diff.csv`
- `implementation/output/fixy_done_high_confidence_remap_proposals.csv`
- `implementation/output/fixy_done_flagged_high_confidence_remap_proposals.csv`
- `implementation/output/fixy_done_quarantine_proposals.csv`
- `implementation/output/fixy_done_flagged_quarantine_proposals.csv`
- `implementation/output/fixy_done_cleanup_summary.json`
- `implementation/output/fixy_done_flagged_cleanup_summary.json`

Description-bridge cleanup:

- `implementation/output/product_to_best_esha_full_map.vFixyText.csv`
- `implementation/output/product_to_best_esha_full_map.vFixyTextFlagged.csv`
- `implementation/output/fixy_done_text_cleanup_diff.csv`
- `implementation/output/fixy_done_text_flagged_cleanup_diff.csv`
- `implementation/output/fixy_done_text_high_confidence_remap_proposals.csv`
- `implementation/output/fixy_done_text_flagged_high_confidence_remap_proposals.csv`
- `implementation/output/fixy_done_text_quarantine_proposals.csv`
- `implementation/output/fixy_done_text_flagged_quarantine_proposals.csv`
- `implementation/output/fixy_done_description_bridge_matches.csv`
- `implementation/output/fixy_done_text_flagged_description_bridge_matches.csv`
- `implementation/output/fixy_done_text_cleanup_summary.json`
- `implementation/output/fixy_done_text_flagged_cleanup_summary.json`

## Rerun Commands

Build the Fixy crosscheck:

```bash
python3 implementation/build_fixy_done_crosscheck.py
```

Build the conservative flagged candidate:

```bash
python3 implementation/apply_fixy_done_cleanup.py \
  --quarantine-mode flag \
  --output-map implementation/output/product_to_best_esha_full_map.vFixyFlagged.csv \
  --diff implementation/output/fixy_done_flagged_cleanup_diff.csv \
  --remaps implementation/output/fixy_done_flagged_high_confidence_remap_proposals.csv \
  --quarantine implementation/output/fixy_done_flagged_quarantine_proposals.csv \
  --summary implementation/output/fixy_done_flagged_cleanup_summary.json
```

Build the description-bridge flagged candidate:

```bash
python3 implementation/apply_fixy_done_cleanup.py \
  --use-description-bridge \
  --quarantine-mode flag \
  --output-map implementation/output/product_to_best_esha_full_map.vFixyTextFlagged.csv \
  --diff implementation/output/fixy_done_text_flagged_cleanup_diff.csv \
  --remaps implementation/output/fixy_done_text_flagged_high_confidence_remap_proposals.csv \
  --quarantine implementation/output/fixy_done_text_flagged_quarantine_proposals.csv \
  --summary implementation/output/fixy_done_text_flagged_cleanup_summary.json \
  --bridge-report implementation/output/fixy_done_text_flagged_description_bridge_matches.csv
```

Build the strict direct-FDC quarantine map:

```bash
python3 implementation/apply_fixy_done_cleanup.py
```

Build the strict description-bridge quarantine map:

```bash
python3 implementation/apply_fixy_done_cleanup.py \
  --use-description-bridge \
  --output-map implementation/output/product_to_best_esha_full_map.vFixyText.csv \
  --diff implementation/output/fixy_done_text_cleanup_diff.csv \
  --remaps implementation/output/fixy_done_text_high_confidence_remap_proposals.csv \
  --quarantine implementation/output/fixy_done_text_quarantine_proposals.csv \
  --summary implementation/output/fixy_done_text_cleanup_summary.json \
  --bridge-report implementation/output/fixy_done_description_bridge_matches.csv
```

## Review Workflow

Start with:

- `implementation/output/fixy_done_flagged_quarantine_proposals.csv`
- `implementation/output/fixy_done_flagged_high_confidence_remap_proposals.csv`

Use the direct-FDC queue first because it is grounded in exact product IDs.

Then sample:

- `implementation/output/fixy_done_text_flagged_quarantine_proposals.csv`
- `implementation/output/fixy_done_text_flagged_high_confidence_remap_proposals.csv`

Use the description bridge to find repeated string-level problems, not as automatic truth.

The biggest cleanup families still showing up are:

- milk subtypes and dairy variants
- produce leaf specificity and salad kits
- jelly, preserves, and pepper-jelly routing
- candy, cookies, ice cream, chips, snacks, and other broad fallback families
- multi-category ESHA codes that should not win without identity overlap

## Calculator Note

The surface lab calculator reads the canonical surface registry directly. The Fixy cleanup maps are whole-corpus assignment layers and should be promoted deliberately.

Recommended promotion order:

1. Keep `vM` as the incumbent truth baseline.
2. Evaluate `vFixyFlagged` as the next operational candidate.
3. Use `fixy_cleanup_action = fixy_done_identity_quarantine_flag` rows to drive family-specific fixes.
4. Only consider `vFixyTextFlagged` after sampling description-bridge rows by family.
5. Avoid promoting blanking maps unless the goal is a strict review corpus instead of calculator coverage.

## Verification

Focused verification run:

```bash
python3 -m py_compile implementation/build_fixy_done_crosscheck.py implementation/apply_fixy_done_cleanup.py
python3 -m unittest discover -s implementation/tests -p 'test_build_product_to_best_esha_full_map.py'
```

The focused whole-map regression passed. The full test suite showed existing unrelated failures and stalled, so it was not treated as signal for this Fixy cleanup change.
