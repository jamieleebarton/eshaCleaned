# Consensus Full Corpus Audit v2

Generated from `consensus_full_corpus_audit.csv` plus approved override layers.

Rows: `462,664`
Unique FDC ids: `462,664`
Duplicate extra rows: `0`
Empty retail leaf rows: `0`
Path defect rows: `0`

## Override Stats

- `source_conflict:legacy_schema_mapped`: `1,559`
- `source_conflict:loaded`: `1,559`
- `source_conflict:skipped_status:blank`: `1,559`
- `taxonomy:applied`: `1,893`
- `taxonomy:changed_fields`: `12,833`
- `taxonomy:loaded`: `1,893`

## Workflow

- Only rows with `status` in `approved`, `apply`, or `accepted` are applied by default.
- Blank override cells mean no change. Use `<blank>` to intentionally clear a field.
- Reviewer todo queues are separate from active override files.