from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from provenance_graph import DEFAULT_GRAPH_DB, build_graph


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = ROOT / "implementation" / "output"
REPORT_DIR = OUTPUT_ROOT / "rebuild_reports"


def command_result(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": args,
    }


def add_step(steps: list[dict[str, Any]], name: str, args: list[str]) -> dict[str, Any]:
    result = command_result(args)
    result["step"] = name
    steps.append(result)
    return result


def mark_failed(result: dict[str, Any], message: str) -> dict[str, Any]:
    result["ok"] = False
    stderr = str(result.get("stderr") or "")
    result["stderr"] = (stderr + ("\n" if stderr else "") + message).strip()
    return result


def write_report(report_dir: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    latest = report_dir / "latest.json"
    stamped = report_dir / f"rebuild_{timestamp}.json"
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    latest.write_text(text, encoding="utf-8")
    stamped.write_text(text, encoding="utf-8")
    return latest, stamped


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild the ESHA audit bundle closure artifacts")
    parser.add_argument("--code", action="append", default=[])
    parser.add_argument("--max-products", type=int, default=160)
    parser.add_argument("--product-limit", type=int, default=1000)
    parser.add_argument("--crossref-products", type=int, default=100)
    parser.add_argument("--skip-launch-queue", action="store_true")
    parser.add_argument("--skip-release-blockers", action="store_true")
    parser.add_argument("--skip-provenance", action="store_true")
    parser.add_argument("--skip-lookup", action="store_true")
    parser.add_argument("--skip-rewrite-plan", action="store_true")
    parser.add_argument("--graph-db", type=Path, default=DEFAULT_GRAPH_DB)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args()

    codes = sorted({str(code).strip() for code in args.code if str(code).strip()}, key=lambda value: int(value) if value.isdigit() else 10**9)
    steps: list[dict[str, Any]] = []
    started_at = datetime.now(timezone.utc).isoformat()
    ok = True

    if not args.skip_rewrite_plan:
        rewrite_args = ["python3", "implementation/build_retail_query_rewrite_plan.py"]
        for code in codes:
            rewrite_args.extend(["--code", code])
        if not add_step(steps, "retail_rewrite_plan", rewrite_args)["ok"]:
            ok = False

    if codes:
        for code in codes:
            if not add_step(
                steps,
                f"build_pack:{code}",
                ["python3", "implementation/build_esha_code_query_packs.py", "--code", code, "--max-products", str(args.max_products)],
            )["ok"]:
                ok = False
                break
            if ok and not args.skip_lookup and not add_step(
                steps,
                f"update_assignments:{code}",
                ["python3", "implementation/update_single_esha_product_assignments.py", "--code", code, "--limit", str(args.product_limit)],
            )["ok"]:
                ok = False
                break
            if ok and not add_step(
                steps,
                f"cross_reference:{code}",
                ["python3", "implementation/build_esha_query_cross_reference.py", "--code", code, "--max-products", str(args.crossref_products)],
            )["ok"]:
                ok = False
                break
            matrix_dir = OUTPUT_ROOT / "esha_cleanup_matrix_slices"
            matrix_dir.mkdir(parents=True, exist_ok=True)
            if ok and not add_step(
                steps,
                f"matrix_slice:{code}",
                [
                    "python3",
                    "implementation/build_esha_cleanup_matrix.py",
                    "--code",
                    code,
                    "--out-csv",
                    str(matrix_dir / f"{code}.csv"),
                    "--out-summary",
                    str(matrix_dir / f"{code}.md"),
                ],
            )["ok"]:
                ok = False
                break
    elif not args.skip_lookup:
        if not add_step(steps, "build_lookup", ["python3", "implementation/build_product_esha_lookup.py"])["ok"]:
            ok = False

    if ok and not add_step(
        steps,
        "rebuild_pack_index",
        ["python3", "implementation/build_esha_code_query_packs.py", "--rebuild-index-from-packs"],
    )["ok"]:
        ok = False

    if ok and not args.skip_launch_queue:
        coverage = add_step(steps, "top2500_coverage", ["python3", "implementation/build_top_ingredient_coverage_audit.py"])
        if coverage["ok"] and re.search(r"\brows=0\b", str(coverage.get("stdout") or "")):
            mark_failed(coverage, "top2500 coverage audit produced zero rows")
        if not coverage["ok"]:
            ok = False
        else:
            progress = add_step(steps, "top2500_progress", ["python3", "implementation/build_top2500_cleanup_progress.py"])
            if progress["ok"] and re.search(r"\bprogress_rows=0\b", str(progress.get("stdout") or "")):
                mark_failed(progress, "top2500 cleanup progress produced zero rows")
            if not progress["ok"]:
                ok = False

    if ok and not args.skip_release_blockers:
        if not add_step(steps, "release_blockers", ["python3", "implementation/build_release_blocker_queue.py"])["ok"]:
            ok = False

    provenance_payload: dict[str, Any] | None = None
    if ok and not args.skip_provenance:
        counts = build_graph(args.graph_db)
        provenance_payload = {
            "graph_db": str(args.graph_db),
            "node_count": counts.node_count,
            "edge_count": counts.edge_count,
            "artifact_count": counts.artifact_count,
            "dependency_count": counts.dependency_count,
        }

    payload = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "codes": codes,
        "steps": steps,
        "provenance": provenance_payload,
        "ok": ok and all(step.get("ok") for step in steps),
    }
    latest, stamped = write_report(args.report_dir, payload)
    payload["latest_report"] = str(latest)
    payload["timestamped_report"] = str(stamped)
    latest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stamped.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
