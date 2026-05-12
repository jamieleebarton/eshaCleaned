from __future__ import annotations

import argparse
from pathlib import Path

import build_category_workbench as workbench
import run_category_rewrite_pass as category_run
import summarize_retail_query_baseline as baseline


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAN_CSV = baseline.DEFAULT_PLAN_CSV
DEFAULT_OUT_ROOT = ROOT / "implementation" / "output" / "uncategorized_runs"


def rows_for_uncategorized_family(rows: list[dict[str, str]], family: str) -> list[dict[str, str]]:
    family_norm = family.strip().casefold()
    return [
        row
        for row in rows
        if workbench.top_category_name(row) == "Uncategorized"
        and str(row.get("family") or "").strip().casefold() == family_norm
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Rerun one Uncategorized family and emit before/after deltas")
    parser.add_argument("--family", required=True)
    parser.add_argument("--plan-csv", type=Path, default=DEFAULT_PLAN_CSV)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--progress-every", type=int, default=500)
    parser.add_argument("--rebuild-packs", action="store_true")
    args = parser.parse_args()

    baseline_rows = baseline.load_rows(args.plan_csv)
    family_rows = rows_for_uncategorized_family(baseline_rows, args.family)
    if not family_rows:
        raise SystemExit(f"uncategorized_family_not_found: {args.family}")

    slug = workbench.category_slug(args.family)
    run_dir = args.out_root / slug
    run_dir.mkdir(parents=True, exist_ok=True)

    codes = category_run.sorted_codes(family_rows)
    codes_path = run_dir / "codes.txt"
    codes_path.write_text("\n".join(codes) + "\n", encoding="utf-8")
    category_run.write_rows(run_dir / "baseline_slice.csv", list(family_rows[0].keys()), family_rows)

    rewrite_plan_csv = run_dir / "rewrite_plan.csv"
    rewrite_plan_summary = run_dir / "rewrite_plan_summary.md"
    family_csv = run_dir / "rewrite_by_family.csv"
    category_csv = run_dir / "rewrite_by_category.csv"
    delta_csv = run_dir / "delta.csv"
    delta_summary = run_dir / "delta_summary.md"

    category_run.run_python(
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
    category_run.run_python(
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
        category_run.run_python(
            [
                "implementation/build_esha_code_query_packs.py",
                "--codes-file",
                str(codes_path),
            ]
        )

    rerun_rows = baseline.load_rows(rewrite_plan_csv)
    delta_rows = category_run.build_delta_rows(family_rows, rerun_rows)
    category_run.write_rows(
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
    category_run.write_delta_summary(
        delta_summary,
        f"Uncategorized / {args.family}",
        family_rows,
        rerun_rows,
        delta_rows,
    )
    print(
        {
            "family": args.family,
            "rows": len(family_rows),
            "run_dir": str(run_dir),
            "rewrite_plan_csv": str(rewrite_plan_csv),
            "delta_csv": str(delta_csv),
            "delta_summary": str(delta_summary),
            "rebuild_packs": bool(args.rebuild_packs),
        }
    )


if __name__ == "__main__":
    main()
