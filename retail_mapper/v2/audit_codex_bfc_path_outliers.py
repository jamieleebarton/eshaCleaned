#!/usr/bin/env python3
"""Audit BFC/path co-occurrence outliers in Codex's full corpus output.

This is intentionally read-only against codex_full_corpus_audit.csv. It builds
the count table Jamie asked for, then ranks suspicious BFC/path pairs where a
branded_food_category is mostly concentrated somewhere else or where the same
BFC + leaf/modifier has a more common canonical home.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


V2 = Path(__file__).resolve().parent
DEFAULT_INPUT = V2 / "codex_full_corpus_audit.csv"
DEFAULT_COUNTS = V2 / "codex_bfc_retail_leaf_counts.csv"
DEFAULT_OUTLIERS = V2 / "codex_bfc_path_outliers.csv"
DEFAULT_EXAMPLES = V2 / "codex_bfc_path_outlier_examples.csv"
DEFAULT_SUMMARY = V2 / "codex_bfc_path_outlier_summary.json"

PATH_SEP = " > "
GENERIC_LEAF_KEYS = {
    "",
    "plain",
    "original",
    "classic",
    "natural",
    "regular",
    "assorted",
    "variety",
    "mix",
}

csv.field_size_limit(sys.maxsize)


def split_path(path: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*>\s*", path or "") if part.strip()]


def token_key(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    stemmed: list[str] = []
    for word in words:
        if len(word) > 3 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
            word = word[:-1]
        stemmed.append(word)
    return " ".join(stemmed)


def path_prefix(path: str, depth: int) -> str:
    return PATH_SEP.join(split_path(path)[:depth])


def modifier_path(row: dict[str, str]) -> str:
    modifier = (row.get("modifier") or "").strip()
    if modifier:
        return modifier
    canonical = (row.get("canonical_path") or "").strip()
    retail_leaf = (row.get("retail_leaf_path") or "").strip()
    if canonical and retail_leaf.startswith(canonical + PATH_SEP):
        return retail_leaf[len(canonical + PATH_SEP):]
    parts = split_path(retail_leaf)
    return parts[-1] if parts else ""


def leaf_signature(row: dict[str, str]) -> str:
    """A within-BFC comparison key based on the final leaf/modifier.

    We deliberately use the modifier/leaf instead of the full canonical path,
    so cases like:
      Pantry > Baking Mixes > Mix > Pina Colada
      Beverage > Cocktail Mixers > Cocktail Mix > Pina Colada
    can compete inside the same BFC.
    """
    modifier = modifier_path(row)
    key = token_key(modifier)
    if key in GENERIC_LEAF_KEYS:
        parts = split_path(row.get("retail_leaf_path") or "")
        key = token_key(parts[-1] if parts else "")
    return key


def sample_blob(samples: Iterable[tuple[str, str]], idx: int) -> str:
    return " | ".join(sample[idx] for sample in samples if sample[idx])


def collect(input_path: Path) -> dict[str, object]:
    bfc_totals: Counter[str] = Counter()
    bfc_prefix2_counts: dict[str, Counter[str]] = defaultdict(Counter)
    bfc_path_counts: dict[tuple[str, str, str], int] = Counter()
    bfc_path_samples: dict[tuple[str, str, str], list[tuple[str, str]]] = defaultdict(list)
    leaf_home_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    leaf_total_counts: Counter[tuple[str, str]] = Counter()
    path_total_counts: Counter[str] = Counter()
    row_examples: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    rows = 0

    with input_path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows += 1
            bfc = (row.get("branded_food_category") or "").strip()
            canonical = (row.get("canonical_path") or "").strip()
            retail_leaf = (row.get("retail_leaf_path") or "").strip()
            if not bfc or not canonical or not retail_leaf:
                continue
            prefix2 = path_prefix(canonical, 2)
            leaf_sig = leaf_signature(row)
            key = (bfc, canonical, retail_leaf)

            bfc_totals[bfc] += 1
            bfc_prefix2_counts[bfc][prefix2] += 1
            bfc_path_counts[key] += 1
            path_total_counts[canonical] += 1
            if leaf_sig:
                leaf_home_counts[(bfc, leaf_sig)][canonical] += 1
                leaf_total_counts[(bfc, leaf_sig)] += 1
            if len(bfc_path_samples[key]) < 3:
                bfc_path_samples[key].append((
                    (row.get("fdc_id") or "").strip(),
                    (row.get("title") or "").strip(),
                ))
            if len(row_examples[key]) < 8:
                row_examples[key].append({
                    "fdc_id": (row.get("fdc_id") or "").strip(),
                    "title": (row.get("title") or "").strip(),
                    "branded_food_category": bfc,
                    "canonical_path": canonical,
                    "retail_leaf_path": retail_leaf,
                    "modifier": modifier_path(row),
                    "fndds_desc": (row.get("fndds_desc") or "").strip(),
                    "esha_desc": (row.get("esha_desc") or "").strip(),
                })

    return {
        "rows": rows,
        "bfc_totals": bfc_totals,
        "bfc_prefix2_counts": bfc_prefix2_counts,
        "bfc_path_counts": bfc_path_counts,
        "bfc_path_samples": bfc_path_samples,
        "leaf_home_counts": leaf_home_counts,
        "leaf_total_counts": leaf_total_counts,
        "path_total_counts": path_total_counts,
        "row_examples": row_examples,
    }


def dominant_prefixes(path_counts: Counter[str], total: int) -> set[str]:
    if not path_counts or not total:
        return set()
    ranked = path_counts.most_common()
    allowed: set[str] = set()
    cumulative = 0
    for idx, (prefix, count) in enumerate(ranked):
        pct = count / total
        if idx == 0 or pct >= 0.10 or (idx < 3 and pct >= 0.05):
            allowed.add(prefix)
            cumulative += count
            continue
        if idx >= 3 and cumulative / total >= 0.80:
            break
    return allowed


def build_outliers(data: dict[str, object], min_bfc_rows: int, min_leaf_rows: int) -> list[dict[str, object]]:
    bfc_totals: Counter[str] = data["bfc_totals"]  # type: ignore[assignment]
    bfc_prefix2_counts: dict[str, Counter[str]] = data["bfc_prefix2_counts"]  # type: ignore[assignment]
    bfc_path_counts: dict[tuple[str, str, str], int] = data["bfc_path_counts"]  # type: ignore[assignment]
    bfc_path_samples: dict[tuple[str, str, str], list[tuple[str, str]]] = data["bfc_path_samples"]  # type: ignore[assignment]
    leaf_home_counts: dict[tuple[str, str], Counter[str]] = data["leaf_home_counts"]  # type: ignore[assignment]
    leaf_total_counts: Counter[tuple[str, str]] = data["leaf_total_counts"]  # type: ignore[assignment]
    path_total_counts: Counter[str] = data["path_total_counts"]  # type: ignore[assignment]

    allowed_by_bfc = {
        bfc: dominant_prefixes(prefix_counts, bfc_totals[bfc])
        for bfc, prefix_counts in bfc_prefix2_counts.items()
    }
    outliers: list[dict[str, object]] = []

    for (bfc, canonical, retail_leaf), count in bfc_path_counts.items():
        total = bfc_totals[bfc]
        if total < min_bfc_rows:
            continue

        prefix2 = path_prefix(canonical, 2)
        path_pct = count / total
        issues: list[str] = []
        severity = 0.0
        allowed = allowed_by_bfc.get(bfc, set())
        dominant_text = " | ".join(
            f"{prefix} [{prefix_count}]"
            for prefix, prefix_count in bfc_prefix2_counts[bfc].most_common(5)
        )

        if allowed and prefix2 not in allowed and (count <= 10 or path_pct <= 0.025):
            issues.append("bfc_minor_destination")
            top_prefix_count = bfc_prefix2_counts[bfc].most_common(1)[0][1]
            severity += top_prefix_count / max(1, count)

        leaf_sig = token_key(modifier_path({
            "modifier": retail_leaf[len(canonical + PATH_SEP):] if retail_leaf.startswith(canonical + PATH_SEP) else "",
            "retail_leaf_path": retail_leaf,
        }))
        if not leaf_sig or leaf_sig in GENERIC_LEAF_KEYS:
            leaf_sig = token_key(split_path(retail_leaf)[-1] if split_path(retail_leaf) else "")
        suggested_path = ""
        suggested_count = 0
        suggested_pct = 0.0
        leaf_rows = leaf_total_counts.get((bfc, leaf_sig), 0)
        if leaf_sig and leaf_rows >= min_leaf_rows:
            ranked_leaf = leaf_home_counts[(bfc, leaf_sig)].most_common()
            if ranked_leaf:
                suggested_path, suggested_count = ranked_leaf[0]
                suggested_pct = suggested_count / leaf_rows
                if canonical != suggested_path and suggested_pct >= 0.50:
                    same_prefix2 = path_prefix(canonical, 2) == path_prefix(suggested_path, 2)
                    ancestor_relation = (
                        canonical.startswith(suggested_path + PATH_SEP)
                        or suggested_path.startswith(canonical + PATH_SEP)
                    )
                    if same_prefix2 or ancestor_relation:
                        continue
                    ratio = suggested_count / max(1, count)
                    if ratio >= 3:
                        issues.append("same_bfc_same_leaf_dominant_elsewhere")
                        severity += ratio * 5

        if not issues:
            continue

        samples = bfc_path_samples[(bfc, canonical, retail_leaf)]
        outliers.append({
            "severity_score": round(severity, 3),
            "issue_types": "|".join(issues),
            "branded_food_category": bfc,
            "bfc_rows": total,
            "bfc_dominant_prefixes": dominant_text,
            "current_canonical_path": canonical,
            "current_retail_leaf_path": retail_leaf,
            "path_rows_in_bfc": count,
            "path_pct_in_bfc": round(path_pct, 5),
            "path_total_rows": path_total_counts[canonical],
            "current_prefix2": prefix2,
            "leaf_signature": leaf_sig,
            "leaf_rows_in_bfc": leaf_rows,
            "suggested_dominant_path_for_leaf": suggested_path,
            "suggested_dominant_path_rows_for_leaf": suggested_count,
            "suggested_dominant_path_pct_for_leaf": round(suggested_pct, 5) if suggested_pct else "",
            "sample_fdcs": sample_blob(samples, 0),
            "sample_titles": sample_blob(samples, 1),
        })

    outliers.sort(key=lambda row: (-float(row["severity_score"]), str(row["branded_food_category"]), str(row["current_retail_leaf_path"])))
    return outliers


def write_counts(data: dict[str, object], output: Path) -> None:
    bfc_totals: Counter[str] = data["bfc_totals"]  # type: ignore[assignment]
    bfc_path_counts: dict[tuple[str, str, str], int] = data["bfc_path_counts"]  # type: ignore[assignment]
    bfc_path_samples: dict[tuple[str, str, str], list[tuple[str, str]]] = data["bfc_path_samples"]  # type: ignore[assignment]

    fields = [
        "branded_food_category",
        "bfc_rows",
        "canonical_path",
        "retail_leaf_path",
        "rows",
        "pct_of_bfc",
        "sample_fdcs",
        "sample_titles",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for (bfc, canonical, retail_leaf), count in sorted(
            bfc_path_counts.items(),
            key=lambda item: (item[0][0], -item[1], item[0][2]),
        ):
            samples = bfc_path_samples[(bfc, canonical, retail_leaf)]
            writer.writerow({
                "branded_food_category": bfc,
                "bfc_rows": bfc_totals[bfc],
                "canonical_path": canonical,
                "retail_leaf_path": retail_leaf,
                "rows": count,
                "pct_of_bfc": round(count / bfc_totals[bfc], 5) if bfc_totals[bfc] else 0,
                "sample_fdcs": sample_blob(samples, 0),
                "sample_titles": sample_blob(samples, 1),
            })


def write_outliers(outliers: list[dict[str, object]], output: Path) -> None:
    fields = [
        "severity_score",
        "issue_types",
        "branded_food_category",
        "bfc_rows",
        "bfc_dominant_prefixes",
        "current_canonical_path",
        "current_retail_leaf_path",
        "path_rows_in_bfc",
        "path_pct_in_bfc",
        "path_total_rows",
        "current_prefix2",
        "leaf_signature",
        "leaf_rows_in_bfc",
        "suggested_dominant_path_for_leaf",
        "suggested_dominant_path_rows_for_leaf",
        "suggested_dominant_path_pct_for_leaf",
        "sample_fdcs",
        "sample_titles",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(outliers)


def write_examples(outliers: list[dict[str, object]], data: dict[str, object], output: Path) -> None:
    row_examples: dict[tuple[str, str, str], list[dict[str, str]]] = data["row_examples"]  # type: ignore[assignment]
    fields = [
        "issue_types",
        "severity_score",
        "fdc_id",
        "title",
        "branded_food_category",
        "canonical_path",
        "retail_leaf_path",
        "modifier",
        "fndds_desc",
        "esha_desc",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for outlier in outliers:
            key = (
                str(outlier["branded_food_category"]),
                str(outlier["current_canonical_path"]),
                str(outlier["current_retail_leaf_path"]),
            )
            for example in row_examples.get(key, []):
                writer.writerow({
                    "issue_types": outlier["issue_types"],
                    "severity_score": outlier["severity_score"],
                    **example,
                })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--counts-out", type=Path, default=DEFAULT_COUNTS)
    parser.add_argument("--outliers-out", type=Path, default=DEFAULT_OUTLIERS)
    parser.add_argument("--examples-out", type=Path, default=DEFAULT_EXAMPLES)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--min-bfc-rows", type=int, default=25)
    parser.add_argument("--min-leaf-rows", type=int, default=4)
    args = parser.parse_args()

    data = collect(args.input)
    outliers = build_outliers(data, min_bfc_rows=args.min_bfc_rows, min_leaf_rows=args.min_leaf_rows)
    write_counts(data, args.counts_out)
    write_outliers(outliers, args.outliers_out)
    write_examples(outliers, data, args.examples_out)

    bfc_totals: Counter[str] = data["bfc_totals"]  # type: ignore[assignment]
    summary = {
        "input": str(args.input),
        "rows": data["rows"],
        "bfcs": len(bfc_totals),
        "retail_leaf_count_rows": sum(1 for _ in data["bfc_path_counts"]),  # type: ignore[arg-type]
        "outlier_path_rows": len(outliers),
        "issue_type_counts": dict(Counter(
            issue
            for row in outliers
            for issue in str(row["issue_types"]).split("|")
            if issue
        )),
        "top_outliers": outliers[:25],
        "outputs": {
            "counts": str(args.counts_out),
            "outliers": str(args.outliers_out),
            "examples": str(args.examples_out),
        },
    }
    args.summary_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps({
        "rows": data["rows"],
        "bfcs": len(bfc_totals),
        "retail_leaf_count_rows": summary["retail_leaf_count_rows"],
        "outlier_path_rows": len(outliers),
        "outputs": summary["outputs"],
    }, indent=2))


if __name__ == "__main__":
    main()
