# Evidence-Cluster Knowledge Graph

This graph is evidence-first. ESHA codes are reference/candidate targets, not
the clustering spine.

## Spine

Product rows are observations. Ingredient clusters are the spine.

```text
Product -> IngredientCluster
Product -> ProductCategory
Product -> Brand -> Manufacturer
Product -> ESHACode        current incumbent vM assignment only
IngredientCluster -> dominant ProductCategory
IngredientCluster -> dominant Brand
IngredientCluster -> CategoryLane
IngredientCluster -> TitleForm
IngredientCluster -> current top ESHACode with audit flags
ESHACode -> ESHAHead
```

## Current Build

The current Kuzu graph is built from:

```text
implementation/output/product_to_best_esha_full_map.vM.csv
implementation/output/ingredient_only_cluster_members.csv
implementation/output/vm_ingredient_cluster_audit.csv
esha_cleaned.csv
```

Build command:

```bash
.venv/bin/python graph/ingest/build_kuzu_graph.py --source implementation/output/product_to_best_esha_full_map.vM.csv
```

## Current Reports

Graph conflict queue:

```bash
.venv/bin/python graph/queries/evidence_cluster_conflicts.py
```

Outputs:

```text
graph/review/evidence_cluster_conflicts_from_graph.csv
graph/review/evidence_cluster_structural_rejects_from_graph.csv
graph/review/evidence_cluster_conflicts_summary.json
```

Safe quarantine projection:

```bash
python3 implementation/apply_vm_cluster_structural_quarantine.py
```

Outputs:

```text
implementation/output/product_to_best_esha_full_map.vM_cluster_quarantine.csv
implementation/output/vm_cluster_structural_quarantine_diff.csv
implementation/output/vm_cluster_structural_quarantine_summary.json
```

## Rules

- Do not use `product_to_best_esha_full_map.vCluster.csv` as truth.
- Do not use ESHA title overlap as the first clustering signal.
- Do not force replacements just because a candidate scores higher.
- Keep `vM` as the incumbent until a cluster-level hard gate rejects it.
- Exact ingredient clusters are not always final leaves; cheese, dry pasta,
  water, soda, honey, nuts, and other broad ingredients need title/category/brand
  sub-splitting before replacement.
- Structural rejects may be quarantined safely; replacement requires a separate
  high-confidence proposal pass.
