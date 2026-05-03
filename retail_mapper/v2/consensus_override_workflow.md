# Consensus Override Workflow

Use `consensus_full_corpus_audit.csv` as the read-only integration base.
Do not edit the generated consensus CSV by hand.

## Ownership

- Codex owns `consensus_reference_overrides.csv` and the reference remap todo queue.
- Claude owns `consensus_taxonomy_overrides.csv` and the right-place taxonomy todo queue.
- Source-category conflicts go through `consensus_source_conflicts.csv` and should be reviewed as shared decisions.

## Apply Contract

- Todo files are inert work queues.
- Active override files are applied only when `status` is `approved`, `apply`, or `accepted`.
- Blank cells mean no change. Use `<blank>` when a field must be intentionally cleared.
- Running `python3 retail_mapper/v2/apply_consensus_overrides.py` writes `consensus_full_corpus_audit.v2.csv` plus a field-level decision log.

## Queue Counts

- `taxonomy_todo_rows`: `2916`
- `reference_todo_rows`: `5082`
- `source_conflict_todo_rows`: `1589`
- `taxonomy_active_created`: `False`
- `reference_active_created`: `False`
- `source_conflict_active_created`: `False`

## First Pass Priority

1. Approve or reject the high-confidence reference remap rows where a proxy reference is clearly wrong.
2. Approve deterministic taxonomy rows only when the proposed path is a true shopper shelf, not a title-token echo.
3. Keep source BFC corrections separate from taxonomy/reference fixes unless the corrected source category is needed by a downstream rule.