# Config Matrix Notes

Superseded note: the first matrix run in this directory is invalid.

The invalid run used a synthetic free water package that still entered pantry
inventory. That caused ~975kg of pantry carryover and distorted planner
selection, producing the false `$1,345.81` baseline.

Correct handling is now in `planner/build_concept_tensor_cache.py`: household
water/ice lines are ignored before building the ingredient tensor, so they do
not create purchase rows, package choices, or pantry carryover.

| Config | Total | Weekly | Person/day | Protein | Veg | Unique recipes | Repeats | Cart audit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 4p 2000 cal thrifty, 75% leftovers | $1,007.08 | $83.92 | $3.00 | 12.7% | 43.3% | 248 | 43 | 0 blank SKU, 0 bad SKU, 0 water/ice purchases |
| 5p 2000 cal thrifty, 75% leftovers | $1,444.20 | $120.35 | $3.44 | 12.3% | 45.4% | 243 | 40 | 0 blank SKU, 0 bad SKU |
| 2p 1800 cal budget, 75% leftovers | $563.01 | $46.92 | $3.35 | 11.6% | 25.2% | 200 | 49 | 0 blank SKU, 0 bad SKU |
| 2p 2200 cal balanced, 75% leftovers | $650.49 | $54.21 | $3.87 | 10.9% | 40.4% | 202 | 35 | 0 blank SKU, 0 bad SKU |
| 5p 2400 cal high_protein, 75% leftovers | $2,670.13 | $222.51 | $6.36 | 23.2% | 41.2% | 226 | 52 | 0 blank SKU, 0 bad SKU |

## Read

The corrected baseline is close to the prior V10 number. The 35% increase was
not a real grocery-price movement; it was caused by water incorrectly entering
pantry inventory as a fake free package.

If exact item names were hidden, these totals would mostly pass a smell test:

- The corrected 4p thrifty baseline lands at $3.00/person/day.
- Five-person plans are cheaper per person than four/two-person plans, which matches package sharing.
- High-protein at 2400 cal lands at $6.36/person/day, which is directionally right because it buys more meat/protein.

## Remaining Concerns

- `balanced` is not nutritionally balanced in this run: only 10.9% protein at a 20% configured protein setting.
- `budget` is cheap but nutritionally weak: 11.6% protein and 25.2% veg compliance.
- `high_protein` responds correctly but still undershoots a 25% target at 23.2%.
- The planner cache counts drifted between runs: some runs loaded 2,642 ingredients / 363,540 recipes, later runs loaded 2,644 ingredients / 365,749 recipes. That needs a reproducibility audit.
- Remaining package flags are mostly audit-parser limitations on produce/count displays, plus a few expensive spices/herbs. No sampled flag showed an obvious wrong-food SKU after the StarKist verifier false positive was fixed.

## Artifacts

- `p4_2000_thrifty_l75_nowater.json`
- `p5_2000_thrifty_l75.json`
- `p2_1800_budget_l75.json`
- `p2_2200_balanced_l75.json`
- `p5_2400_high_protein_l75.json`
- Matching `*.audit.json` files contain package flags, cheapest package lines, high package prices, and bad-SKU checks.
