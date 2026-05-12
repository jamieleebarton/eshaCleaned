#!/usr/bin/env python3
"""Audit BFC alignment at department/category hierarchy levels.

Leaf paths are useful for exact fixes, but too noisy for deciding whether a
branded_food_category is in the wrong part of the store. This audit rolls each
BFC up to:

  depth 1: Department                         e.g. Beverage
  depth 2: Department > Category              e.g. Beverage > Cocktail Mixers
  depth 3: Department > Category > Identity   e.g. Beverage > Cocktail Mixers > Cocktail Mix

It then identifies BFCs with a strong dominant department and writes the rows
outside that department as misplaced candidates.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


V2 = Path(__file__).resolve().parent
DEFAULT_INPUT = V2 / "codex_full_corpus_audit.csv"
DEFAULT_COUNTS = V2 / "codex_bfc_hierarchy_counts.csv"
DEFAULT_HOMES = V2 / "codex_bfc_expected_homes.csv"
DEFAULT_MISPLACED = V2 / "codex_bfc_department_misplaced.csv"
DEFAULT_EXAMPLES = V2 / "codex_bfc_department_misplaced_examples.csv"
DEFAULT_SUMMARY = V2 / "codex_bfc_hierarchy_summary.json"

PATH_SEP = " > "
csv.field_size_limit(sys.maxsize)


def split_path(path: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*>\s*", path or "") if part.strip()]


def prefix(path: str, depth: int) -> str:
    return PATH_SEP.join(split_path(path)[:depth])


def sample_key(bfc: str, depth: int, path_prefix: str) -> tuple[str, int, str]:
    return bfc, depth, path_prefix


def home_status(pct: float, strong: float, medium: float) -> str:
    if pct >= strong:
        return "strong"
    if pct >= medium:
        return "medium"
    return "noisy"


def collect(input_path: Path) -> dict[str, object]:
    bfc_totals: Counter[str] = Counter()
    counts_by_depth: dict[int, dict[str, Counter[str]]] = {
        1: defaultdict(Counter),
        2: defaultdict(Counter),
        3: defaultdict(Counter),
    }
    samples: dict[tuple[str, int, str], list[tuple[str, str, str]]] = defaultdict(list)
    rows_by_bfc: dict[str, list[dict[str, str]]] = defaultdict(list)
    rows = 0

    with input_path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            bfc = (row.get("branded_food_category") or "").strip()
            canonical = (row.get("canonical_path") or "").strip()
            if not bfc or not canonical:
                continue
            bfc_totals[bfc] += 1
            rows_by_bfc[bfc].append({
                "fdc_id": (row.get("fdc_id") or "").strip(),
                "title": (row.get("title") or "").strip(),
                "branded_food_category": bfc,
                "canonical_path": canonical,
                "retail_leaf_path": (row.get("retail_leaf_path") or "").strip(),
                "fndds_desc": (row.get("fndds_desc") or "").strip(),
                "esha_desc": (row.get("esha_desc") or "").strip(),
            })
            for depth in (1, 2, 3):
                path_prefix = prefix(canonical, depth)
                if not path_prefix:
                    continue
                counts_by_depth[depth][bfc][path_prefix] += 1
                key = sample_key(bfc, depth, path_prefix)
                if len(samples[key]) < 3:
                    samples[key].append((
                        (row.get("fdc_id") or "").strip(),
                        (row.get("title") or "").strip(),
                        (row.get("retail_leaf_path") or "").strip(),
                    ))

    return {
        "rows": rows,
        "bfc_totals": bfc_totals,
        "counts_by_depth": counts_by_depth,
        "samples": samples,
        "rows_by_bfc": rows_by_bfc,
    }


def sample_blob(samples: list[tuple[str, str, str]], index: int) -> str:
    return " | ".join(sample[index] for sample in samples if sample[index])


def write_counts(data: dict[str, object], output: Path) -> None:
    bfc_totals: Counter[str] = data["bfc_totals"]  # type: ignore[assignment]
    counts_by_depth: dict[int, dict[str, Counter[str]]] = data["counts_by_depth"]  # type: ignore[assignment]
    samples: dict[tuple[str, int, str], list[tuple[str, str, str]]] = data["samples"]  # type: ignore[assignment]
    fields = [
        "branded_food_category",
        "bfc_rows",
        "depth",
        "rank",
        "path_prefix",
        "rows",
        "pct_of_bfc",
        "sample_fdcs",
        "sample_titles",
        "sample_retail_leaf_paths",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for bfc in sorted(bfc_totals):
            total = bfc_totals[bfc]
            for depth in (1, 2, 3):
                for rank, (path_prefix, count) in enumerate(counts_by_depth[depth][bfc].most_common(), start=1):
                    group_samples = samples[sample_key(bfc, depth, path_prefix)]
                    writer.writerow({
                        "branded_food_category": bfc,
                        "bfc_rows": total,
                        "depth": depth,
                        "rank": rank,
                        "path_prefix": path_prefix,
                        "rows": count,
                        "pct_of_bfc": round(count / total, 5) if total else 0,
                        "sample_fdcs": sample_blob(group_samples, 0),
                        "sample_titles": sample_blob(group_samples, 1),
                        "sample_retail_leaf_paths": sample_blob(group_samples, 2),
                    })


def expected_homes(data: dict[str, object], min_bfc_rows: int) -> list[dict[str, object]]:
    bfc_totals: Counter[str] = data["bfc_totals"]  # type: ignore[assignment]
    counts_by_depth: dict[int, dict[str, Counter[str]]] = data["counts_by_depth"]  # type: ignore[assignment]
    rows: list[dict[str, object]] = []
    for bfc in sorted(bfc_totals):
        total = bfc_totals[bfc]
        if total < min_bfc_rows:
            continue
        dept, dept_count = counts_by_depth[1][bfc].most_common(1)[0]
        top2, top2_count = counts_by_depth[2][bfc].most_common(1)[0]
        top3, top3_count = counts_by_depth[3][bfc].most_common(1)[0]
        dept_pct = dept_count / total
        top2_pct = top2_count / total
        top3_pct = top3_count / total
        rows.append({
            "branded_food_category": bfc,
            "bfc_rows": total,
            "dominant_department": dept,
            "dominant_department_rows": dept_count,
            "dominant_department_pct": round(dept_pct, 5),
            "department_status": home_status(dept_pct, strong=0.80, medium=0.65),
            "dominant_top2": top2,
            "dominant_top2_rows": top2_count,
            "dominant_top2_pct": round(top2_pct, 5),
            "top2_status": home_status(top2_pct, strong=0.65, medium=0.45),
            "dominant_top3": top3,
            "dominant_top3_rows": top3_count,
            "dominant_top3_pct": round(top3_pct, 5),
            "top3_status": home_status(top3_pct, strong=0.45, medium=0.25),
            "department_distribution": " | ".join(
                f"{path} [{count}, {count / total:.1%}]"
                for path, count in counts_by_depth[1][bfc].most_common()
            ),
            "top2_distribution": " | ".join(
                f"{path} [{count}, {count / total:.1%}]"
                for path, count in counts_by_depth[2][bfc].most_common(10)
            ),
        })
    rows.sort(key=lambda row: (
        row["department_status"] != "strong",
        -float(row["dominant_department_pct"]),
        str(row["branded_food_category"]),
    ))
    return rows


def write_expected_homes(rows: list[dict[str, object]], output: Path) -> None:
    fields = [
        "branded_food_category",
        "bfc_rows",
        "dominant_department",
        "dominant_department_rows",
        "dominant_department_pct",
        "department_status",
        "dominant_top2",
        "dominant_top2_rows",
        "dominant_top2_pct",
        "top2_status",
        "dominant_top3",
        "dominant_top3_rows",
        "dominant_top3_pct",
        "top3_status",
        "department_distribution",
        "top2_distribution",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_misplaced(
    data: dict[str, object],
    homes: list[dict[str, object]],
    misplaced_out: Path,
    examples_out: Path,
) -> list[dict[str, object]]:
    rows_by_bfc: dict[str, list[dict[str, str]]] = data["rows_by_bfc"]  # type: ignore[assignment]
    strong_homes = {
        str(row["branded_food_category"]): str(row["dominant_department"])
        for row in homes
        if row["department_status"] == "strong"
    }
    grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for bfc, expected_dept in strong_homes.items():
        for row in rows_by_bfc.get(bfc, []):
            actual_dept = prefix(row["canonical_path"], 1)
            if actual_dept == expected_dept:
                continue
            actual_top2 = prefix(row["canonical_path"], 2)
            key = (bfc, expected_dept, actual_dept, actual_top2)
            grouped[key].append(row)

    summary_rows: list[dict[str, object]] = []
    for (bfc, expected_dept, actual_dept, actual_top2), examples in grouped.items():
        total = len(rows_by_bfc[bfc])
        summary_rows.append({
            "branded_food_category": bfc,
            "bfc_rows": total,
            "expected_department": expected_dept,
            "actual_department": actual_dept,
            "actual_top2": actual_top2,
            "misplaced_rows": len(examples),
            "pct_of_bfc": round(len(examples) / total, 5) if total else 0,
            "sample_fdcs": " | ".join(row["fdc_id"] for row in examples[:5]),
            "sample_titles": " | ".join(row["title"] for row in examples[:5]),
            "sample_retail_leaf_paths": " | ".join(row["retail_leaf_path"] for row in examples[:5]),
        })
    summary_rows.sort(key=lambda row: (-int(row["misplaced_rows"]), str(row["branded_food_category"]), str(row["actual_top2"])))

    summary_fields = [
        "branded_food_category",
        "bfc_rows",
        "expected_department",
        "actual_department",
        "actual_top2",
        "misplaced_rows",
        "pct_of_bfc",
        "sample_fdcs",
        "sample_titles",
        "sample_retail_leaf_paths",
    ]
    with misplaced_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(summary_rows)

    example_fields = [
        "branded_food_category",
        "expected_department",
        "actual_department",
        "fdc_id",
        "title",
        "canonical_path",
        "retail_leaf_path",
        "fndds_desc",
        "esha_desc",
    ]
    with examples_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=example_fields)
        writer.writeheader()
        for (bfc, expected_dept, actual_dept, _actual_top2), examples in sorted(grouped.items()):
            for row in examples[:25]:
                writer.writerow({
                    "branded_food_category": bfc,
                    "expected_department": expected_dept,
                    "actual_department": actual_dept,
                    **row,
                })

    return summary_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--counts-out", type=Path, default=DEFAULT_COUNTS)
    parser.add_argument("--homes-out", type=Path, default=DEFAULT_HOMES)
    parser.add_argument("--misplaced-out", type=Path, default=DEFAULT_MISPLACED)
    parser.add_argument("--examples-out", type=Path, default=DEFAULT_EXAMPLES)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--min-bfc-rows", type=int, default=25)
    args = parser.parse_args()

    data = collect(args.input)
    homes = expected_homes(data, min_bfc_rows=args.min_bfc_rows)
    write_counts(data, args.counts_out)
    write_expected_homes(homes, args.homes_out)
    misplaced = write_misplaced(data, homes, args.misplaced_out, args.examples_out)

    status_counts = Counter(str(row["department_status"]) for row in homes)
    summary = {
        "input": str(args.input),
        "rows": data["rows"],
        "bfcs_with_min_rows": len(homes),
        "department_status_counts": dict(status_counts),
        "misplaced_groups": len(misplaced),
        "misplaced_rows": sum(int(row["misplaced_rows"]) for row in misplaced),
        "top_misplaced_groups": misplaced[:50],
        "outputs": {
            "hierarchy_counts": str(args.counts_out),
            "expected_homes": str(args.homes_out),
            "misplaced": str(args.misplaced_out),
            "examples": str(args.examples_out),
        },
    }
    args.summary_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({
        "rows": data["rows"],
        "bfcs_with_min_rows": len(homes),
        "department_status_counts": dict(status_counts),
        "misplaced_groups": len(misplaced),
        "misplaced_rows": summary["misplaced_rows"],
        "outputs": summary["outputs"],
    }, indent=2))


if __name__ == "__main__":
    main()
