# Codex Retail Mapper Audit

Date: 2026-04-28
Workspace: `/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper`
Author: Codex

## Purpose

This file is the audit trail for the Codex pass on the retail mapper. It records
what changed, what was generated, what was verified, and what still needs review.

## Files touched by Codex

### Modified

- `discovery/p1_unassigned_tokens.py`
  - Changed hard-coded root discovery to derive paths from the script location.
  - Added an axis-file snapshot before scanning.
  - Added a post-scan check that exits with code `2` instead of writing stale
    reports if any `axes/*.tsv` file changes while the scan is running.

### Added

- `parsers/title_parser.py`
  - Deterministic Stage 2 title parser.
  - Loads `axes/*.tsv` and `axes/spelling.tsv`.
  - Emits retail axes and a generated `retail_leaf`.
  - Supports `single`, `combo_pack`, and `composite_dish`.
  - CLI modes:
    - `--title "..."` for one-off JSON inspection.
    - `--examples` for regression JSONL examples.
    - `--input ... --output ... [--limit N]` for CSV parsing.

- `parsers/test_title_parser.py`
  - Regression tests for mapper failure cases from `PLAN.md`.

- `discovery/parsed_titles.sample.csv`
  - 1,000-row sample parse from `product_esha_fixy.v6.csv`.

- `codex_retail_mapper_audit.md`
  - This audit file.

## Generated outputs checked

Current P1 discovery summary:

```text
Titles scanned:       462,646
Unique tokens:         28,196
Total token mass:   2,782,604
Mass covered:       2,489,738  (89.5%)
Mass unassigned:      292,866  (10.5%)
Top-500 unassigned mass:    106,164
```

Current top residual tokens are mostly vocabulary-review items rather than
parser blockers:

```text
semi, jalapenos, alternative, cappuccino, fiesta, rising, drizzle, skillet,
flamin, atlantic, stone, color, dipping, decorating, clover
```

Sample parser output stats from `discovery/parsed_titles.sample.csv`:

```text
rows: 1000
retail_type:
  single: 923
  combo_pack: 68
  composite_dish: 9
needs_review: 95
top category_groups:
  Plant-based Milk: 477
  Fruit: 336
  Combo Packs: 68
  Beverages: 58
  Fruit-based Drinks: 15
  Composite Dishes: 9
  Protein Powders: 8
  Nuts & Seeds: 4
```

## Regression coverage

The tests pin these cases:

- `HINT OF PUMPKIN SPICE ALMONDMILK`
  - Expected: `single`, `form=milk`, `category_group=Plant-based Milk`,
    `category=Almond Milk`, `flavor=pumpkin spice`.

- `LEMON GINGER COLD-PRESSED ALMOND JUICE`
  - Expected: `single`, `form=juice`, `primary_food=almond`,
    `category_group=Fruit-based Drinks`, `prep_state=cold pressed`.
  - Important: rejects the almond-milk magnet behavior.

- `ALMOND PROTEIN POWDER, UNFLAVORED`
  - Expected: `form=protein powder`, `category=Almond Protein`,
    leaf under `Protein Powders`.
  - Important: rejects the almond-milk magnet behavior.

- `APPLE NOODLE KUGEL`
  - Expected: `composite_dish`, `dish_type=kugel`.

- `APPLE SLICES WITH PEANUT BUTTER`
  - Expected: `combo_pack`, `pack_format=dipper`,
    components `apple slices` and `peanut butter`.

- `HUMMUS WITH PITA CHIPS`
  - Expected: `combo_pack`, not `composite_dish`.

- `ACAI BLUEBERRY WATERMELON SMOOTHIE WITH CHIA SEEDS`
  - Expected: `single`, `form=smoothie`,
    `flavor_blend=[acai, blueberry, watermelon]`,
    `inclusions=[chia seeds]`.

- `FULLY COOKED BACON`
  - Expected: `single`, `primary_food=bacon`,
    `prep_state=fully cooked`, no review flag.

- `ORIGINAL DAIRY + ALMOND BLEND MILK`
  - Expected: `category_group=Blended Milks`,
    `category=Dairy+Almond`.
  - Important: does not route to plant-based almond milk.

## Verification commands run

```bash
python3 -m unittest parsers/test_title_parser.py
```

Result:

```text
Ran 9 tests in 0.194s
OK
```

```bash
python3 -m py_compile discovery/p1_unassigned_tokens.py parsers/title_parser.py parsers/test_title_parser.py
```

Result: passed with no output.

```bash
python3 discovery/p1_unassigned_tokens.py
```

Result: completed and refreshed discovery outputs. The new concurrency guard did
not detect any axis changes during the final scan.

```bash
python3 parsers/title_parser.py --limit 1000 --output discovery/parsed_titles.sample.csv
```

Result: wrote 1,000 parsed rows.

## How to audit one row

```bash
python3 parsers/title_parser.py --title "LEMON GINGER COLD-PRESSED ALMOND JUICE"
```

Expected key fields:

```json
{
  "retail_type": "single",
  "form": "juice",
  "primary_food": "almond",
  "category_group": "Fruit-based Drinks",
  "retail_leaf": "Beverage > Fruit-based Drinks > Juice > Almond",
  "prep_state": "cold pressed"
}
```

## How to generate the full parser output

```bash
python3 parsers/title_parser.py --output parsed_titles.csv
```

This writes a full 462,646-row parse to `parsed_titles.csv`.

## Known limits

- The parser is deterministic and intentionally shallow. It is good enough to
  establish the Stage 2 contract and block known hot-leaf failures, but it is
  not a complete taxonomy engine yet.
- `retail_leaf` generation is currently heuristic. It should feed the real
  Stage 3 tree builder, not replace it.
- Brand-flavor detection is not implemented yet. Terms like `Chunky Monkey`
  still need `axes/brand_flavors.tsv` and bucket-aware handling.
- Ingredient fallback is not implemented yet. Low-confidence title parses still
  need ingredient voting from `fixy_done`.
- ESHA signature gating is not implemented yet. This pass prepares parser
  output for that gate.
- The sample parse shows `95 / 1000` rows with `needs_review`, mostly from
  missing or ambiguous form/category data. That is expected for the current
  axis coverage but should be tracked as axes improve.

## Suggested next audit step

Run the full parser and produce a distribution report:

```bash
python3 parsers/title_parser.py --output parsed_titles.csv
```

Then summarize:

```bash
python3 -c "import csv,collections; rows=csv.DictReader(open('parsed_titles.csv')); c=collections.Counter(); review=0
for r in rows:
    c[r['retail_type']] += 1
    review += r['needs_review'] != '[]'
print(c)
print('needs_review', review)"
```

That tells us whether the parser is stable enough to feed Stage 3 tree building
or whether the next move should be another axis vocabulary pass.
