#!/usr/bin/env python3
"""Compare Codex's rebuilt taxonomy audit against full_corpus_audit.csv."""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


V2 = Path(__file__).resolve().parent
CODEX = V2 / "codex_full_corpus_audit.csv"
FULL = V2 / "full_corpus_audit.csv"
OUT_DISAGREE = V2 / "codex_vs_full_corpus_audit_disagreements.csv"
OUT_PAIRS = V2 / "codex_vs_full_corpus_audit_top_pairs.csv"
OUT_SUMMARY = V2 / "codex_vs_full_corpus_audit_summary.json"
OUT_MD = V2 / "codex_vs_full_corpus_audit.md"

PATH_SEP = " > "

csv.field_size_limit(sys.maxsize)


COMPARE_COLUMNS = [
    "category_path_fixed",
    "product_identity_fixed",
    "canonical_path",
    "modifier",
    "retail_leaf_path",
]


def split_path(path: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*>\s*", path or "") if part.strip()]


def prefix(path: str, depth: int) -> str:
    return PATH_SEP.join(split_path(path)[:depth])


def normalize_text(value: str) -> str:
    return " ".join((value or "").split())


def load_rows(path: Path) -> dict[tuple[str, int], dict[str, str]]:
    rows: dict[tuple[str, int], dict[str, str]] = {}
    counts: Counter[str] = Counter()
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            fdc = (row.get("fdc_id") or "").strip()
            counts[fdc] += 1
            rows[(fdc, counts[fdc])] = row
    return rows


def classify(full: dict[str, str], codex: dict[str, str]) -> str:
    full_canonical = normalize_text(full.get("canonical_path", ""))
    codex_canonical = normalize_text(codex.get("canonical_path", ""))
    full_leaf = normalize_text(full.get("retail_leaf_path", ""))
    codex_leaf = normalize_text(codex.get("retail_leaf_path", ""))
    full_category = normalize_text(full.get("category_path_fixed", ""))
    codex_category = normalize_text(codex.get("category_path_fixed", ""))
    full_identity = normalize_text(full.get("product_identity_fixed", ""))
    codex_identity = normalize_text(codex.get("product_identity_fixed", ""))

    if full_canonical == codex_canonical and full_leaf != codex_leaf:
        return "leaf_modifier_only"
    if full_category == codex_category and full_identity == codex_identity:
        return "canonicalizer_shape_only"
    if prefix(full_canonical, 1) != prefix(codex_canonical, 1):
        return "department_change"
    if prefix(full_canonical, 2) != prefix(codex_canonical, 2):
        return "category_change"
    if full_identity != codex_identity and prefix(full_canonical, 2) == prefix(codex_canonical, 2):
        return "identity_change_same_category"
    if full_category != codex_category and full_identity == codex_identity:
        return "category_change_same_identity"
    return "same_department_deeper_change"


def disagreement_row(
    key: tuple[str, int],
    full: dict[str, str] | None,
    codex: dict[str, str] | None,
) -> dict[str, str]:
    source = full or codex or {}
    kind = "missing_from_codex" if codex is None else "missing_from_full"
    if full is not None and codex is not None:
        kind = classify(full, codex)
    return {
        "compare_kind": kind,
        "fdc_id": key[0],
        "occurrence": str(key[1]),
        "title": source.get("title", ""),
        "branded_food_category": source.get("branded_food_category", ""),
        "full_category_path": (full or {}).get("category_path_fixed", ""),
        "codex_category_path": (codex or {}).get("category_path_fixed", ""),
        "full_product_identity": (full or {}).get("product_identity_fixed", ""),
        "codex_product_identity": (codex or {}).get("product_identity_fixed", ""),
        "full_canonical_path": (full or {}).get("canonical_path", ""),
        "codex_canonical_path": (codex or {}).get("canonical_path", ""),
        "full_modifier": (full or {}).get("modifier", ""),
        "codex_modifier": (codex or {}).get("modifier", ""),
        "full_retail_leaf_path": (full or {}).get("retail_leaf_path", ""),
        "codex_retail_leaf_path": (codex or {}).get("retail_leaf_path", ""),
        "fndds_desc": source.get("fndds_desc", ""),
        "sr28_desc": source.get("sr28_desc", ""),
        "esha_desc": source.get("esha_desc", ""),
        "matched_key": source.get("matched_key", ""),
    }


def main() -> None:
    full_rows = load_rows(FULL)
    codex_rows = load_rows(CODEX)
    def sort_key(item: tuple[str, int]) -> tuple[int, int | str, int]:
        fdc, occurrence = item
        return (0, int(fdc), occurrence) if fdc.isdigit() else (1, fdc, occurrence)

    all_keys = sorted(set(full_rows) | set(codex_rows), key=sort_key)

    field_diffs: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    dept_pairs: Counter[tuple[str, str]] = Counter()
    top2_pairs: Counter[tuple[str, str]] = Counter()
    canonical_pairs: Counter[tuple[str, str]] = Counter()
    bfc_kind_counts: Counter[tuple[str, str]] = Counter()
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    disagreement_rows: list[dict[str, str]] = []
    compared = 0
    exact_all = 0
    exact_paths = 0

    for key in all_keys:
        full = full_rows.get(key)
        codex = codex_rows.get(key)
        if full is not None and codex is not None:
            compared += 1
            if all(normalize_text(full.get(col, "")) == normalize_text(codex.get(col, "")) for col in COMPARE_COLUMNS):
                exact_paths += 1
                if all(normalize_text(full.get(col, "")) == normalize_text(codex.get(col, "")) for col in full.keys() & codex.keys()):
                    exact_all += 1
                continue
            for col in COMPARE_COLUMNS:
                if normalize_text(full.get(col, "")) != normalize_text(codex.get(col, "")):
                    field_diffs[col] += 1

        out = disagreement_row(key, full, codex)
        disagreement_rows.append(out)
        kind_counts[out["compare_kind"]] += 1
        bfc_kind_counts[(out["branded_food_category"], out["compare_kind"])] += 1
        if len(examples[out["compare_kind"]]) < 10:
            examples[out["compare_kind"]].append(out)

        full_canonical = out["full_canonical_path"]
        codex_canonical = out["codex_canonical_path"]
        if full_canonical or codex_canonical:
            dept_pairs[(prefix(full_canonical, 1), prefix(codex_canonical, 1))] += 1
            top2_pairs[(prefix(full_canonical, 2), prefix(codex_canonical, 2))] += 1
            canonical_pairs[(full_canonical, codex_canonical)] += 1

    fields = list(disagreement_rows[0].keys()) if disagreement_rows else [
        "compare_kind",
        "fdc_id",
        "occurrence",
        "title",
        "branded_food_category",
        "full_category_path",
        "codex_category_path",
        "full_product_identity",
        "codex_product_identity",
        "full_canonical_path",
        "codex_canonical_path",
        "full_modifier",
        "codex_modifier",
        "full_retail_leaf_path",
        "codex_retail_leaf_path",
        "fndds_desc",
        "sr28_desc",
        "esha_desc",
        "matched_key",
    ]
    with OUT_DISAGREE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(disagreement_rows)

    pair_fields = [
        "pair_type",
        "rows",
        "full_path",
        "codex_path",
        "sample_compare_kind",
    ]
    with OUT_PAIRS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=pair_fields)
        writer.writeheader()
        for pair_type, pairs in (
            ("department", dept_pairs),
            ("top2", top2_pairs),
            ("canonical", canonical_pairs),
        ):
            for (full_path, codex_path), count in pairs.most_common(250):
                writer.writerow({
                    "pair_type": pair_type,
                    "rows": count,
                    "full_path": full_path,
                    "codex_path": codex_path,
                    "sample_compare_kind": "",
                })

    summary = {
        "full_source": str(FULL),
        "codex_source": str(CODEX),
        "full_rows": len(full_rows),
        "codex_rows": len(codex_rows),
        "compared_rows": compared,
        "exact_path_rows": exact_paths,
        "path_disagreement_rows": len(disagreement_rows),
        "exact_all_common_columns_rows": exact_all,
        "kind_counts": dict(kind_counts.most_common()),
        "field_diff_counts": dict(field_diffs.most_common()),
        "top_department_pairs": [
            {"full_department": full_path, "codex_department": codex_path, "rows": count}
            for (full_path, codex_path), count in dept_pairs.most_common(25)
        ],
        "top_top2_pairs": [
            {"full_top2": full_path, "codex_top2": codex_path, "rows": count}
            for (full_path, codex_path), count in top2_pairs.most_common(25)
        ],
        "top_canonical_pairs": [
            {"full_canonical_path": full_path, "codex_canonical_path": codex_path, "rows": count}
            for (full_path, codex_path), count in canonical_pairs.most_common(25)
        ],
        "top_bfc_kind_pairs": [
            {"branded_food_category": bfc, "compare_kind": kind, "rows": count}
            for (bfc, kind), count in bfc_kind_counts.most_common(50)
        ],
        "examples": examples,
        "outputs": {
            "disagreements": str(OUT_DISAGREE),
            "top_pairs": str(OUT_PAIRS),
            "summary": str(OUT_SUMMARY),
            "markdown": str(OUT_MD),
        },
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# Codex vs full_corpus_audit",
        "",
        f"Full rows: `{len(full_rows):,}`",
        f"Codex rows: `{len(codex_rows):,}`",
        f"Compared rows: `{compared:,}`",
        f"Exact path rows: `{exact_paths:,}`",
        f"Path disagreement rows: `{len(disagreement_rows):,}`",
        "",
        "## Disagreement Types",
        "",
    ]
    for kind, count in kind_counts.most_common():
        lines.append(f"- `{kind}`: `{count:,}`")
    lines.extend(["", "## Field Diffs", ""])
    for field, count in field_diffs.most_common():
        lines.append(f"- `{field}`: `{count:,}`")
    lines.extend(["", "## Top Department Moves", ""])
    for (full_path, codex_path), count in dept_pairs.most_common(15):
        lines.append(f"- `{full_path}` -> `{codex_path}`: `{count:,}`")
    lines.extend(["", "## Top Category Moves", ""])
    for (full_path, codex_path), count in top2_pairs.most_common(20):
        lines.append(f"- `{full_path}` -> `{codex_path}`: `{count:,}`")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "full_rows": len(full_rows),
        "codex_rows": len(codex_rows),
        "compared_rows": compared,
        "exact_path_rows": exact_paths,
        "path_disagreement_rows": len(disagreement_rows),
        "kind_counts": dict(kind_counts.most_common(10)),
        "field_diff_counts": dict(field_diffs.most_common()),
        "outputs": summary["outputs"],
    }, indent=2))


if __name__ == "__main__":
    main()
