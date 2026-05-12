# Retail Leaf V2 Clean Export

- Main cleaned CSV: `retail_mapper/v2/retail_leaf_v2_enriched_v2.cleaned.csv`
- Main file has one retail path column: `retail_leaf`.
- `provenance` JSON is in the main file; it carries b0/b1/b2/b3/b6/b7/b8 and guard evidence.
- NER spans and POS-derived head fields are in the main file: `ner_spans`, `head_phrase`, `compound_prefix`, `pp_components`, `comma_tail`.
- Parser/axis evidence is in the main file, including parser cut/prep/storage/claims/components and axis parsed tokens.
- LLM-only blobs stay out of main: `title_ngrams_json`, `role_candidates_json`, `llm_evidence_block`.
- Full ingredients stay source-only as `ing_full` in the original enriched file; main keeps `ing_top5` and ingredient categories/source flags.
- Original full enriched source: `retail_mapper/v2/retail_leaf_v2_enriched_v2.csv`
- Column manifest: `retail_mapper/v2/retail_leaf_v2_column_manifest.json`
- Rows: `462,647`
- Columns: `78`
- Size: `788,023,063` bytes
- Missing provenance rows: `1`
- Exact root-only retail leaves: `0`
