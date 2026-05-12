#!/usr/bin/env python3
"""
Stage 1 + Stage 2 — filter false positives + cluster real outliers.

Stage 1 (filter):
  Drop rows from embed_outliers.csv where sim_to_tree_description >= 0.5.
  Rationale: those products match the ESHA description directly; they were
  flagged because the cohort was noisy, not because the product is wrong.

Stage 2 (cluster):
  Group remaining outliers by (current_esha_code, branded_food_category).
  Big clusters = bulk-fix opportunities. Singletons = individual cases.

Outputs:
  outliers_filtered.csv          — outliers worth fixing (post-filter)
  outlier_clusters.csv           — clusters with size + sample products
  filter_cluster_summary.md      — human-readable rollup
"""
import csv
from collections import Counter, defaultdict

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
SRC = f"{ROOT}/implementation/output/embed_outliers.csv"
OUT_FILTERED = f"{ROOT}/implementation/output/outliers_filtered.csv"
OUT_CLUSTERS = f"{ROOT}/implementation/output/outlier_clusters.csv"
OUT_SUMMARY = f"{ROOT}/implementation/output/filter_cluster_summary.md"

TREE_SIM_DROP = 0.5  # if product matches its ESHA tree description this well, it's not a real outlier

def main():
    rows = list(csv.DictReader(open(SRC)))
    print(f"Loaded {len(rows):,} outlier candidates")

    # Stage 1: filter
    filtered = []
    dropped_tree_sim = 0
    for r in rows:
        sim_tree = r.get("sim_to_tree_description","")
        try:
            sim_tree = float(sim_tree) if sim_tree else 0.0
        except ValueError:
            sim_tree = 0.0
        if sim_tree >= TREE_SIM_DROP:
            dropped_tree_sim += 1
            continue
        filtered.append(r)

    print(f"Stage 1 — false-positive filter:")
    print(f"  dropped (sim_tree >= {TREE_SIM_DROP}): {dropped_tree_sim:,}")
    print(f"  remaining real outliers:                {len(filtered):,}")

    with open(OUT_FILTERED, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys(), extrasaction="ignore")
        w.writeheader()
        for r in filtered: w.writerow(r)
    print(f"  wrote {OUT_FILTERED}")

    # Stage 2: cluster by (current_esha_code, branded_food_category)
    clusters = defaultdict(list)
    for r in filtered:
        key = (r["esha_code"], r["branded_food_category"])
        clusters[key].append(r)
    cluster_list = sorted(clusters.items(), key=lambda kv: -len(kv[1]))

    print(f"\nStage 2 — pattern cluster:")
    print(f"  unique (current_code, category) clusters: {len(cluster_list):,}")
    big = [(k,v) for k,v in cluster_list if len(v) >= 5]
    print(f"  clusters with N>=5 (bulk-fix candidates): {len(big):,}")
    singletons = [(k,v) for k,v in cluster_list if len(v) == 1]
    print(f"  singletons:                                {len(singletons):,}")

    # Write cluster CSV: one row per cluster, with sample fdc_ids
    with open(OUT_CLUSTERS, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["esha_code","esha_desc","category","cluster_size",
                    "median_zscore","median_outlier_score",
                    "sample_products","sample_fdc_ids"])
        for (code, cat), items in cluster_list:
            zs = sorted(float(r["centroid_zscore"]) for r in items)
            sc = sorted(float(r["outlier_score"]) for r in items)
            sample_p = " | ".join(r["product_description"][:50] for r in items[:3])
            sample_i = " | ".join(r["fdc_id"] for r in items[:5])
            w.writerow([code, items[0]["esha_desc"], cat, len(items),
                       round(zs[len(zs)//2], 2), round(sc[len(sc)//2], 2),
                       sample_p, sample_i])
    print(f"  wrote {OUT_CLUSTERS}")

    # Summary
    with open(OUT_SUMMARY, "w") as f:
        f.write(f"# Outlier filter + cluster summary\n\n")
        f.write(f"## Stage 1 — false-positive filter\n\n")
        f.write(f"- Outlier candidates from embedding scan: **{len(rows):,}**\n")
        f.write(f"- Dropped where sim_to_tree_description >= {TREE_SIM_DROP}: **{dropped_tree_sim:,}**\n")
        f.write(f"- **Real outliers remaining: {len(filtered):,}**\n\n")
        f.write(f"## Stage 2 — pattern cluster\n\n")
        f.write(f"- Unique (current_code, category) groups: **{len(cluster_list):,}**\n")
        f.write(f"- Bulk-fix clusters (N>=5):                 **{len(big):,}**\n")
        f.write(f"- Singletons:                               **{len(singletons):,}**\n\n")
        f.write(f"### Top 25 bulk-fix clusters\n\n")
        f.write("| size | code | description | category | sample product |\n|---:|---|---|---|---|\n")
        for (code, cat), items in big[:25]:
            sample = items[0]["product_description"][:55]
            f.write(f"| {len(items):,} | {code} | {items[0]['esha_desc'][:50]} | {cat[:30]} | {sample} |\n")
    print(f"  wrote {OUT_SUMMARY}")

    # Print top clusters to console
    print(f"\n=== Top 15 bulk-fix clusters ===")
    for (code, cat), items in big[:15]:
        print(f"  {len(items):>4} | [{code}] {items[0]['esha_desc'][:45]:<45} | {cat[:30]} | {items[0]['product_description'][:50]}")

if __name__ == "__main__":
    main()
