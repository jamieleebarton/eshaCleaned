#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import self_heal_common as sh


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
DEFAULT_MAP = (
    OUT_DIR / "product_to_best_esha_full_map.vSelf.csv"
    if (OUT_DIR / "product_to_best_esha_full_map.vSelf.csv").exists()
    else OUT_DIR / "product_to_best_esha_full_map.csv"
)
DEFAULT_OUT_DIR = OUT_DIR / "esha_category_outliers_vSelf"


def clean_code(value: object) -> str:
    return str(value or "").split(".", 1)[0].strip()


def clean_category(value: object) -> str:
    text = str(value or "").strip()
    return text if text and text.lower() != "nan" else "<missing>"


def join_counts(values: Iterable[str], limit: int = 8) -> str:
    counts = Counter(v for v in values if v)
    return " | ".join(f"{k}:{v}" for k, v in counts.most_common(limit))


def row_facts(row: dict[str, str]) -> dict[str, object]:
    desc = str(row.get("product_description") or "")
    category = str(row.get("branded_food_category") or "")
    title_tokens = set(sh.ingredient_clusters.title_tokens(desc))
    lane = sh.category_lane_for(desc, category, title_tokens)
    form = sh.product_form_for(desc, category, lane, title_tokens)
    role = sh.role_for(desc, lane, form, title_tokens)
    target_heads = sh.target_heads_for(lane, form, role, title_tokens)
    assigned_desc = str(row.get("best_esha_description") or "")
    assigned_head = str(row.get("best_esha_head") or "") or sh.esha_head(assigned_desc)

    hard_reasons: list[str] = []
    if target_heads and not sh.head_compatible(target_heads, assigned_head):
        hard_reasons.append(f"target_head_mismatch:{assigned_head}->allowed:{'|'.join(target_heads)}")

    category_ok, category_reason = sh.policy.category_allows_head(
        category=category,
        product_description=desc,
        title_tokens=title_tokens,
        candidate_head=assigned_head,
    )
    if not category_ok:
        hard_reasons.append(category_reason)

    narrow_reason = sh.policy.narrow_head_requires_title_support(assigned_head, title_tokens, desc)
    if narrow_reason:
        hard_reasons.append(narrow_reason)

    evidence = set(title_tokens)
    for form_reason in (
        sh.sauce_form_mismatch_reason(form, assigned_desc),
        sh.water_flavor_mismatch_reason(lane, evidence, assigned_desc),
        sh.soup_form_mismatch_reason(form, evidence, assigned_desc),
        sh.tomato_form_mismatch_reason(form, evidence, assigned_desc),
        sh.brownie_form_mismatch_reason(form, assigned_desc),
    ):
        if form_reason:
            hard_reasons.append(form_reason)

    return {
        "category_clean": clean_category(category),
        "computed_lane": lane,
        "computed_form": form,
        "computed_role": role,
        "computed_target_heads": "|".join(target_heads),
        "assigned_head": assigned_head,
        "title_tokens": " ".join(sorted(title_tokens)),
        "hard_reasons": hard_reasons,
    }


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_workbench(args: argparse.Namespace) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    with args.input_map.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for i, row in enumerate(reader, start=1):
            if args.limit and i > args.limit:
                break
            code = clean_code(row.get("best_esha_code"))
            if not code:
                continue
            facts = row_facts(row)
            rows.append(
                {
                    **{k: row.get(k, "") for k in reader.fieldnames or []},
                    **facts,
                    "best_esha_code": code,
                    "hard_category_outlier": "1" if facts["hard_reasons"] else "0",
                    "hard_category_reasons": " | ".join(facts["hard_reasons"]),
                }
            )

    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[str(row["best_esha_code"])].append(row)

    outlier_rows: list[dict[str, object]] = []
    hard_rows: list[dict[str, object]] = []
    code_rows: list[dict[str, object]] = []

    for code, group in groups.items():
        lane_counts = Counter(str(r.get("computed_lane", "")) for r in group)
        category_counts = Counter(str(r.get("category_clean", "")) for r in group)
        form_counts = Counter(str(r.get("computed_form", "")) for r in group)
        dominant_lane, dominant_lane_count = lane_counts.most_common(1)[0]
        dominant_category, dominant_category_count = category_counts.most_common(1)[0]
        size = len(group)
        dominant_lane_share = dominant_lane_count / size if size else 0.0
        dominant_category_share = dominant_category_count / size if size else 0.0

        hard_count = sum(1 for r in group if r["hard_category_outlier"] == "1")
        soft_count = 0
        for row in group:
            soft_reasons: list[str] = []
            if (
                size >= args.min_code_size
                and dominant_lane_share >= args.min_dominant_lane_share
                and row.get("computed_lane") != dominant_lane
            ):
                soft_reasons.append(f"minority_lane_in_code:{row.get('computed_lane')}!=dominant:{dominant_lane}")
            if (
                size >= args.min_code_size
                and dominant_category_share >= args.min_dominant_category_share
                and row.get("category_clean") != dominant_category
            ):
                soft_reasons.append(
                    f"minority_category_in_code:{row.get('category_clean')}!=dominant:{dominant_category}"
                )
            if soft_reasons:
                soft_count += 1

            if row["hard_category_outlier"] == "1" or soft_reasons:
                out = {
                    **row,
                    "soft_category_outlier": "1" if soft_reasons else "0",
                    "soft_category_reasons": " | ".join(soft_reasons),
                    "code_product_count": size,
                    "code_dominant_lane": dominant_lane,
                    "code_dominant_lane_share": round(dominant_lane_share, 6),
                    "code_dominant_category": dominant_category,
                    "code_dominant_category_share": round(dominant_category_share, 6),
                    "code_lane_counts": join_counts([str(r.get("computed_lane", "")) for r in group], 12),
                    "code_form_counts": join_counts([str(r.get("computed_form", "")) for r in group], 12),
                    "code_category_counts": join_counts([str(r.get("category_clean", "")) for r in group], 12),
                }
                outlier_rows.append(out)
                if row["hard_category_outlier"] == "1":
                    hard_rows.append(out)

        first = group[0]
        reason_counts = Counter()
        for row in group:
            for reason in str(row.get("hard_category_reasons", "")).split(" | "):
                if reason:
                    reason_counts[reason] += 1
        code_rows.append(
            {
                "best_esha_code": code,
                "best_esha_description": first.get("best_esha_description", ""),
                "assigned_head": first.get("assigned_head", ""),
                "product_count": size,
                "hard_outlier_count": hard_count,
                "hard_outlier_share": round(hard_count / size if size else 0.0, 6),
                "soft_outlier_count": soft_count,
                "soft_outlier_share": round(soft_count / size if size else 0.0, 6),
                "dominant_lane": dominant_lane,
                "dominant_lane_share": round(dominant_lane_share, 6),
                "dominant_category": dominant_category,
                "dominant_category_share": round(dominant_category_share, 6),
                "lane_count": len(lane_counts),
                "category_count": len(category_counts),
                "form_count": len(form_counts),
                "top_hard_reasons": " | ".join(f"{k}:{v}" for k, v in reason_counts.most_common(8)),
                "lane_counts": " | ".join(f"{k}:{v}" for k, v in lane_counts.most_common(12)),
                "form_counts": " | ".join(f"{k}:{v}" for k, v in form_counts.most_common(12)),
                "category_counts": " | ".join(f"{k}:{v}" for k, v in category_counts.most_common(12)),
                "sample_hard_outliers": " || ".join(
                    str(r.get("product_description", ""))
                    for r in group
                    if r["hard_category_outlier"] == "1"
                )[:1200],
            }
        )

    code_rows.sort(
        key=lambda r: (
            int(r["hard_outlier_count"]),
            float(r["hard_outlier_share"]),
            int(r["soft_outlier_count"]),
            int(r["product_count"]),
        ),
        reverse=True,
    )
    outlier_rows.sort(
        key=lambda r: (
            int(r.get("hard_category_outlier", "0")),
            int(r.get("code_product_count", 0)),
            str(r.get("best_esha_code", "")),
        ),
        reverse=True,
    )
    hard_rows.sort(key=lambda r: (int(r.get("code_product_count", 0)), str(r.get("best_esha_code", ""))), reverse=True)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outlier_path = args.output_dir / "category_outlier_rows.csv"
    hard_path = args.output_dir / "hard_category_outlier_rows.csv"
    code_path = args.output_dir / "category_outlier_code_rollup.csv"
    summary_path = args.output_dir / "category_outlier_summary.json"
    md_path = args.output_dir / "category_outlier_summary.md"

    row_fields = [
        "gtin_upc",
        "fdc_id",
        "product_description",
        "branded_food_category",
        "brand_owner",
        "brand_name",
        "best_esha_code",
        "best_esha_description",
        "assigned_head",
        "best_esha_family",
        "assignment_source",
        "self_heal_status",
        "self_heal_reason",
        "category_clean",
        "computed_lane",
        "computed_form",
        "computed_target_heads",
        "hard_category_outlier",
        "hard_category_reasons",
        "soft_category_outlier",
        "soft_category_reasons",
        "code_product_count",
        "code_dominant_lane",
        "code_dominant_lane_share",
        "code_dominant_category",
        "code_dominant_category_share",
        "code_lane_counts",
        "code_form_counts",
        "code_category_counts",
    ]
    code_fields = [
        "best_esha_code",
        "best_esha_description",
        "assigned_head",
        "product_count",
        "hard_outlier_count",
        "hard_outlier_share",
        "soft_outlier_count",
        "soft_outlier_share",
        "dominant_lane",
        "dominant_lane_share",
        "dominant_category",
        "dominant_category_share",
        "lane_count",
        "category_count",
        "form_count",
        "top_hard_reasons",
        "lane_counts",
        "form_counts",
        "category_counts",
        "sample_hard_outliers",
    ]
    write_csv(outlier_path, outlier_rows, row_fields)
    write_csv(hard_path, hard_rows, row_fields)
    write_csv(code_path, code_rows, code_fields)

    hard_reason_counts = Counter()
    for row in hard_rows:
        for reason in str(row.get("hard_category_reasons", "")).split(" | "):
            if reason:
                hard_reason_counts[reason] += 1
    summary = {
        "input_map": str(args.input_map),
        "assigned_rows_scanned": len(rows),
        "outlier_rows": len(outlier_rows),
        "hard_outlier_rows": len(hard_rows),
        "codes_scanned": len(code_rows),
        "codes_with_hard_outliers": sum(1 for r in code_rows if int(r["hard_outlier_count"]) > 0),
        "codes_with_soft_outliers": sum(1 for r in code_rows if int(r["soft_outlier_count"]) > 0),
        "top_hard_reasons": hard_reason_counts.most_common(30),
        "top_codes": [
            {
                "best_esha_code": r["best_esha_code"],
                "best_esha_description": r["best_esha_description"],
                "product_count": r["product_count"],
                "hard_outlier_count": r["hard_outlier_count"],
                "soft_outlier_count": r["soft_outlier_count"],
                "dominant_lane": r["dominant_lane"],
                "top_hard_reasons": r["top_hard_reasons"],
            }
            for r in code_rows[:40]
        ],
        "outputs": {
            "outlier_rows": str(outlier_path),
            "hard_outlier_rows": str(hard_path),
            "code_rollup": str(code_path),
            "summary_md": str(md_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# ESHA Category Outlier Workbench\n\n",
        f"- Input map: `{args.input_map}`\n",
        f"- Assigned rows scanned: **{len(rows):,}**\n",
        f"- Hard category outlier rows: **{len(hard_rows):,}**\n",
        f"- Soft cohort/category outlier rows: **{len(outlier_rows) - len(hard_rows):,}**\n",
        f"- Codes with hard outliers: **{summary['codes_with_hard_outliers']:,}**\n\n",
        "Hard outliers are rows where the product category/form target heads reject the assigned ESHA head. "
        "Soft outliers are minority category/lane rows inside an otherwise coherent ESHA-code cohort.\n\n",
        "## Top Codes\n\n",
        "| code | description | products | hard | soft | dominant lane | top hard reasons |\n",
        "|---|---|---:|---:|---:|---|---|\n",
    ]
    for row in code_rows[:60]:
        if int(row["hard_outlier_count"]) <= 0 and int(row["soft_outlier_count"]) <= 0:
            continue
        desc = str(row["best_esha_description"]).replace("|", " ")[:80]
        reasons = str(row["top_hard_reasons"]).replace("|", "/")[:120]
        lines.append(
            f"| {row['best_esha_code']} | {desc} | {int(row['product_count']):,} | "
            f"{int(row['hard_outlier_count']):,} | {int(row['soft_outlier_count']):,} | "
            f"{row['dominant_lane']} | {reasons} |\n"
        )
    lines.extend(
        [
            "\n## Top Hard Reasons\n\n",
            "| reason | rows |\n",
            "|---|---:|\n",
        ]
    )
    for reason, count in hard_reason_counts.most_common(40):
        lines.append(f"| {reason.replace('|', '/')} | {count:,} |\n")
    md_path.write_text("".join(lines), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ESHA-code category outlier review artifacts.")
    parser.add_argument("--input-map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-code-size", type=int, default=10)
    parser.add_argument("--min-dominant-lane-share", type=float, default=0.70)
    parser.add_argument("--min-dominant-category-share", type=float, default=0.85)
    args = parser.parse_args()
    print(json.dumps(build_workbench(args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
