# Audit invariant tests

Comprehensive tests for `full_corpus_audit.csv`. Run after every regeneration.

## Run

```bash
cd retail_mapper/v2
pytest tests/ -v                    # all tests
pytest tests/test_known_paths.py    # golden SKU spot checks
pytest tests/test_path_invariants.py -k "type_present"   # single invariant
pytest tests/ -x                    # stop on first failure
pytest tests/ --co -q               # list all tests without running
```

## Test files (in priority order)

| File | Invariants | Speed |
|---|---|---|
| `test_known_paths.py` | Golden SKUs that historically broke (Alabama Roll, Bagels, Oat Milk, Jelly Beans, etc.) — must always be correct | <1s |
| `test_path_invariants.py` | Per-row path structure (1-9): valid family, type present, no duplicates, no echo, no underscores, top-down order | ~5s |
| `test_column_consistency.py` | Column ↔ path consistency (10-15): PI in path, variant/flavor/form/claims present, no hallucinated leaves | ~10s |
| `test_bfc_allow_list.py` | (25) Each BFC has curated allowed-path prefixes. Pizza→{Frozen>Pizza, Meal>Pizza}, Cheese→{Dairy>Cheese}, etc. | ~5s |
| `test_categories.py` | One test per BFC (top 80) — verifies the BFC's SKUs concentrate in the allowed paths | ~10s |
| `test_cross_row.py` | (16-20) Same fndds_code → same family+type; same PI → ONE family; non-empty paths | ~10s |
| `test_special_cases.py` | (21-24) Plant milks have specific type; sandwiches don't have wrong nut butter; no concat leaves; NFS exclusion | ~5s |
| `test_claims_sanity.py` | No `Sugar Free > Sugar`, `Vegan > Beef`, `Organic > Conventional`, etc. | ~5s |

## Data files

- `data/bfc_allowed_paths.json` — curated BFC → list of allowed family+type prefixes
- `data/known_good_skus.json` — golden SKUs (fdc_id → expected canonical_path) for spot checks
- `data/family_children.json` — each family's allowed type segments

## Conventions

- Tests load `full_corpus_audit.csv` once per session via `conftest.py` fixture.
- Failing tests must print sample violating SKUs (fdc_id, title, current path, expected) — never fail with a bare assert.
- Tests are FAST. The full audit is 462k rows; tests should complete in seconds.
- One pytest function per invariant. If an invariant has many sub-cases, parametrize.
- Cap violation reports to 20 samples per failing test to avoid context flood.
