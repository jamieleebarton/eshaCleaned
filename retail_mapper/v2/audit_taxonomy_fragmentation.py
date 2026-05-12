#!/usr/bin/env python3
"""Audit finalized taxonomy fragmentation.

Finds product identities that still land on more than one canonical shelf after
taxonomy_finalizer.py is applied. This is the report for "there can only be one
path" failures such as:

  Bakery > Cookies > Biscotti
  Bakery > Biscotti
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

from taxonomy_finalizer import finalize_taxonomy_row


REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SRC = V2 / "full_corpus_cleaned.csv"
OUT_SUMMARY = V2 / "taxonomy_fragmentation_report.csv"
OUT_EXAMPLES = V2 / "taxonomy_fragmentation_examples.csv"

csv.field_size_limit(sys.maxsize)


def identity_key(identity: str) -> str:
    return " ".join((identity or "").lower().replace("&", " ").split())


def main() -> None:
    paths_by_identity: dict[str, Counter] = defaultdict(Counter)
    label_by_identity: dict[str, Counter] = defaultdict(Counter)
    examples: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    with SRC.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            finalized = finalize_taxonomy_row(row)
            identity = finalized.product_identity_fixed
            if not identity:
                continue
            key = identity_key(identity)
            path = finalized.canonical_path
            paths_by_identity[key][path] += 1
            label_by_identity[key][identity] += 1
            bucket = (key, path)
            if len(examples[bucket]) < 5:
                examples[bucket].append({
                    "fdc_id": row.get("fdc_id", ""),
                    "title": row.get("title", ""),
                    "branded_food_category": row.get("branded_food_category", ""),
                    "source_category_path_fixed": row.get("category_path_fixed", ""),
                    "source_product_identity_fixed": row.get("product_identity_fixed", ""),
                    "final_category_path_fixed": finalized.category_path_fixed,
                    "final_product_identity_fixed": finalized.product_identity_fixed,
                    "final_canonical_path": finalized.canonical_path,
                    "final_retail_leaf_path": finalized.retail_leaf_path,
                })

    with OUT_SUMMARY.open("w", encoding="utf-8", newline="") as fh:
        fields = [
            "identity_key",
            "identity_label",
            "total_rows",
            "n_canonical_paths",
            "dominant_canonical_path",
            "dominant_rows",
            "second_canonical_path",
            "second_rows",
            "all_paths",
        ]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for key, path_counts in sorted(
            paths_by_identity.items(),
            key=lambda kv: (-sum(kv[1].values()), kv[0]),
        ):
            if len(path_counts) < 2:
                continue
            ranked = path_counts.most_common()
            total = sum(path_counts.values())
            label = label_by_identity[key].most_common(1)[0][0]
            w.writerow({
                "identity_key": key,
                "identity_label": label,
                "total_rows": total,
                "n_canonical_paths": len(path_counts),
                "dominant_canonical_path": ranked[0][0],
                "dominant_rows": ranked[0][1],
                "second_canonical_path": ranked[1][0],
                "second_rows": ranked[1][1],
                "all_paths": " | ".join(f"{path} ({count})" for path, count in ranked),
            })

    with OUT_EXAMPLES.open("w", encoding="utf-8", newline="") as fh:
        fields = [
            "identity_key",
            "canonical_path",
            "fdc_id",
            "title",
            "branded_food_category",
            "source_category_path_fixed",
            "source_product_identity_fixed",
            "final_category_path_fixed",
            "final_product_identity_fixed",
            "final_canonical_path",
            "final_retail_leaf_path",
        ]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        fragmented = {key for key, counts in paths_by_identity.items() if len(counts) > 1}
        for key in sorted(fragmented):
            for path, _count in paths_by_identity[key].most_common():
                for example in examples[(key, path)]:
                    w.writerow({
                        "identity_key": key,
                        "canonical_path": path,
                        **example,
                    })

    print(f"wrote {OUT_SUMMARY}")
    print(f"wrote {OUT_EXAMPLES}")
    print(f"fragmented identities: {sum(1 for counts in paths_by_identity.values() if len(counts) > 1):,}")


if __name__ == "__main__":
    main()
