from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from collections import Counter
from pathlib import Path

import build_category_workbench as workbench
import summarize_retail_query_baseline as baseline


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAN_CSV = baseline.DEFAULT_PLAN_CSV
DEFAULT_OUT_ROOT = ROOT / "implementation" / "output" / "category_runs"

STATUS_RANK = {
    "unresolved": 0,
    "uncertain": 1,
    "strong": 2,
}


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def top_category_name(row: dict[str, str]) -> str:
    return workbench.top_category_name(row)


def rows_for_category(rows: list[dict[str, str]], category: str) -> list[dict[str, str]]:
    needle = workbench.normalize_category(category)
    return [row for row in rows if workbench.normalize_category(top_category_name(row)) == needle]


def sorted_codes(rows: list[dict[str, str]]) -> list[str]:
    def sort_key(code: str) -> tuple[int, int | str]:
        return (0, int(code)) if code.isdigit() else (1, code)

    return sorted({str(row["esha_code"]).strip() for row in rows if str(row["esha_code"]).strip()}, key=sort_key)


def run_python(args: list[str]) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def delta_kind(before: dict[str, str], after: dict[str, str]) -> str:
    before_rank = STATUS_RANK.get(before.get("exactness_status", ""), -1)
    after_rank = STATUS_RANK.get(after.get("exactness_status", ""), -1)
    if after_rank > before_rank:
        return "improved"
    if after_rank < before_rank:
        return "regressed"
    query_changed = before.get("recommended_query", "") != after.get("recommended_query", "")
    attempt_changed = before.get("recommended_attempt", "") != after.get("recommended_attempt", "")
    filter_changed = before.get("semantic_filter_terms", "") != after.get("semantic_filter_terms", "")
    if query_changed or attempt_changed or filter_changed:
        return "changed"
    return "unchanged"


def build_delta_rows(before_rows: list[dict[str, str]], after_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    before_map = {row["esha_code"]: row for row in before_rows}
    after_map = {row["esha_code"]: row for row in after_rows}
    out: list[dict[str, object]] = []
    for code in sorted(set(before_map) | set(after_map), key=lambda value: (0, int(value)) if value.isdigit() else (1, value)):
        before = before_map.get(code, {})
        after = after_map.get(code, {})
        out.append(
            {
                "esha_code": code,
                "description": after.get("description") or before.get("description") or "",
                "family": after.get("family") or before.get("family") or "",
                "delta_kind": delta_kind(before, after),
                "status_before": before.get("exactness_status", ""),
                "status_after": after.get("exactness_status", ""),
                "reason_before": before.get("reason", ""),
                "reason_after": after.get("reason", ""),
                "attempt_before": before.get("recommended_attempt", ""),
                "attempt_after": after.get("recommended_attempt", ""),
                "query_before": before.get("recommended_query", ""),
                "query_after": after.get("recommended_query", ""),
                "exact_product_count_before": before.get("exact_product_count", ""),
                "exact_product_count_after": after.get("exact_product_count", ""),
                "noise_count_before": before.get("noise_count", ""),
                "noise_count_after": after.get("noise_count", ""),
                "top_category_before": top_category_name(before) if before else "",
                "top_category_after": top_category_name(after) if after else "",
            }
        )
    return out


def write_delta_summary(path: Path, category: str, before_rows: list[dict[str, str]], after_rows: list[dict[str, str]], delta_rows: list[dict[str, object]]) -> None:
    before_counts = Counter(row["exactness_status"] for row in before_rows)
    after_counts = Counter(row["exactness_status"] for row in after_rows)
    delta_counts = Counter(str(row["delta_kind"]) for row in delta_rows)
    improved = [row for row in delta_rows if row["delta_kind"] == "improved"][:25]
    regressed = [row for row in delta_rows if row["delta_kind"] == "regressed"][:25]
    changed = [row for row in delta_rows if row["delta_kind"] == "changed"][:25]
    lines = [
        f"# Category Rewrite Delta: {category}",
        "",
        f"- rows: {len(after_rows)}",
        f"- before strong/uncertain/unresolved: {before_counts.get('strong', 0)} / {before_counts.get('uncertain', 0)} / {before_counts.get('unresolved', 0)}",
        f"- after strong/uncertain/unresolved: {after_counts.get('strong', 0)} / {after_counts.get('uncertain', 0)} / {after_counts.get('unresolved', 0)}",
        f"- improved: {delta_counts.get('improved', 0)}",
        f"- regressed: {delta_counts.get('regressed', 0)}",
        f"- changed only: {delta_counts.get('changed', 0)}",
        f"- unchanged: {delta_counts.get('unchanged', 0)}",
        "",
        "## Improved",
        "",
        "| esha_code | before | after | query after | description |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for row in improved:
        lines.append(
            f"| {row['esha_code']} | {row['status_before']} | {row['status_after']} | {row['query_after']} | {row['description']} |"
        )
    lines.extend(
        [
            "",
            "## Regressed",
            "",
            "| esha_code | before | after | query after | description |",
            "| ---: | --- | --- | --- | --- |",
        ]
    )
    for row in regressed:
        lines.append(
            f"| {row['esha_code']} | {row['status_before']} | {row['status_after']} | {row['query_after']} | {row['description']} |"
        )
    lines.extend(
        [
            "",
            "## Changed Without Status Shift",
            "",
            "| esha_code | before attempt | after attempt | before query | after query | description |",
            "| ---: | --- | --- | --- | --- | --- |",
        ]
    )
    for row in changed:
        lines.append(
            f"| {row['esha_code']} | {row['attempt_before']} | {row['attempt_after']} | "
            f"{row['query_before']} | {row['query_after']} | {row['description']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rerun one branded food category and emit before/after deltas")
    parser.add_argument("--category", required=True)
    parser.add_argument("--plan-csv", type=Path, default=DEFAULT_PLAN_CSV)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--progress-every", type=int, default=250)
    parser.add_argument("--rebuild-packs", action="store_true")
    args = parser.parse_args()

    baseline_rows = baseline.load_rows(args.plan_csv)
    category_rows = rows_for_category(baseline_rows, args.category)
    if not category_rows:
        raise SystemExit(f"category_not_found: {args.category}")
    slug = workbench.category_slug(args.category)
    run_dir = args.out_root / slug
    run_dir.mkdir(parents=True, exist_ok=True)

    codes = sorted_codes(category_rows)
    codes_path = run_dir / "codes.txt"
    codes_path.write_text("\n".join(codes) + "\n", encoding="utf-8")
    write_rows(run_dir / "baseline_slice.csv", list(category_rows[0].keys()), category_rows)

    rewrite_plan_csv = run_dir / "rewrite_plan.csv"
    rewrite_plan_summary = run_dir / "rewrite_plan_summary.md"
    family_csv = run_dir / "rewrite_by_family.csv"
    category_csv = run_dir / "rewrite_by_category.csv"
    delta_csv = run_dir / "delta.csv"
    delta_summary = run_dir / "delta_summary.md"

    run_python(
        [
            "implementation/build_retail_query_rewrite_plan.py",
            "--codes-file",
            str(codes_path),
            "--out-csv",
            str(rewrite_plan_csv),
            "--summary-out",
            str(rewrite_plan_summary),
            "--progress-every",
            str(max(0, int(args.progress_every))),
        ]
    )
    run_python(
        [
            "implementation/summarize_retail_query_baseline.py",
            "--plan-csv",
            str(rewrite_plan_csv),
            "--summary-out",
            str(run_dir / "rewrite_baseline_summary.md"),
            "--family-out",
            str(family_csv),
            "--category-out",
            str(category_csv),
        ]
    )
    if args.rebuild_packs:
        run_python(
            [
                "implementation/build_esha_code_query_packs.py",
                "--codes-file",
                str(codes_path),
            ]
        )

    rerun_rows = baseline.load_rows(rewrite_plan_csv)
    delta_rows = build_delta_rows(category_rows, rerun_rows)
    write_rows(
        delta_csv,
        [
            "esha_code",
            "description",
            "family",
            "delta_kind",
            "status_before",
            "status_after",
            "reason_before",
            "reason_after",
            "attempt_before",
            "attempt_after",
            "query_before",
            "query_after",
            "exact_product_count_before",
            "exact_product_count_after",
            "noise_count_before",
            "noise_count_after",
            "top_category_before",
            "top_category_after",
        ],
        delta_rows,
    )
    write_delta_summary(delta_summary, args.category, category_rows, rerun_rows, delta_rows)
    print(
        {
            "category": args.category,
            "rows": len(category_rows),
            "run_dir": str(run_dir),
            "rewrite_plan_csv": str(rewrite_plan_csv),
            "delta_csv": str(delta_csv),
            "delta_summary": str(delta_summary),
            "rebuild_packs": bool(args.rebuild_packs),
        }
    )


if __name__ == "__main__":
    main()
