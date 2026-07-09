#!/usr/bin/env python3
"""Run the vLLM HTC proof agent across branded/store products.

This runner is intentionally resumable. Each product produces a proof JSON plus
one queue record: either a staged HTC update, a verified-current no-op inside
the proof, or a machine evidence expansion record. It does not write production
tables directly.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from htc_product_auditor_agent import (  # noqa: E402
    DEFAULT_CONSENSUS,
    DEFAULT_PRODUCTS,
    audit_row,
    build_references,
    selected_rows,
)
from htc_single_product_proof_agent import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_OUT_DIR,
    DEFAULT_RECIPES,
    DEFAULT_WORKBENCH_DB,
    proof_key,
    run_product,
)


def proof_path(out_dir: Path, row_number: int, row: dict[str, str]) -> Path:
    return out_dir / f"proof_{proof_key(row_number, row)}.json"


def load_existing_final(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    final = data.get("final")
    return final if isinstance(final, dict) else None


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def compact_event(result: dict[str, Any]) -> dict[str, Any]:
    product = result.get("product") if isinstance(result.get("product"), dict) else {}
    final = result.get("final") if isinstance(result.get("final"), dict) else {}
    return {
        "upc": product.get("upc"),
        "rowid": product.get("rowid"),
        "name": product.get("name"),
        "from_htc_code": product.get("htc_code"),
        "accepted_htc_code": final.get("accepted_htc_code"),
        "verdict": final.get("verdict"),
        "action": final.get("action"),
        "proof": result.get("output"),
        "timing_seconds": result.get("timing_seconds", {}).get("total_model"),
    }


def run_batch(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    refs, inv, df = build_references(args.consensus)
    rows = selected_rows(
        args.products,
        limit=args.limit,
        upcs=set(args.upc),
        rowids=set(args.rowid),
    )

    counts: Counter[str] = Counter()
    started = time.time()
    processed = 0
    skipped = 0
    failures = 0
    events_path = args.out_dir / "runner_events.jsonl"

    for index, (row_number, row) in enumerate(rows, start=1):
        if args.max_processed and processed >= args.max_processed:
            counts["stopped_at_max_processed"] += 1
            break

        out_path = proof_path(args.out_dir, row_number, row)
        if args.resume and not args.force:
            existing = load_existing_final(out_path)
            if existing:
                skipped += 1
                counts[f"skipped_{existing.get('action') or existing.get('verdict') or 'existing'}"] += 1
                continue

        if args.prefilter_updates_only:
            decision = audit_row(row, row_number, refs, inv, df)
            if decision.verifier_verdict not in {"verified_update", "evidence_expansion_update_candidate"}:
                skipped += 1
                counts[f"prefilter_skip_{decision.verifier_verdict}"] += 1
                continue

        try:
            result = run_product(args, refs, inv, df, row_number, row)
        except Exception as exc:  # noqa: BLE001 - batch runner must keep going when requested
            failures += 1
            event = {
                "row_number": row_number,
                "upc": row.get("upc"),
                "rowid": row.get("rowid"),
                "name": row.get("name"),
                "action": "runner_failure",
                "error": repr(exc),
            }
            append_jsonl(events_path, event)
            print(json.dumps(event, sort_keys=True), flush=True)
            if not args.keep_going:
                raise
            continue

        processed += 1
        event = compact_event(result)
        event["row_number"] = row_number
        event["batch_index"] = index
        counts[str(event.get("action") or event.get("verdict") or "unknown")] += 1
        append_jsonl(events_path, event)
        print(json.dumps(event, sort_keys=True), flush=True)

    summary = {
        "schema_version": 1,
        "agent": "htc_vllm_auditor_runner",
        "model_base_url": args.model_base_url,
        "model_name": args.model_name,
        "model_roles": {
            "planner": {
                "base_url": args.planner_model_base_url or args.model_base_url,
                "model": args.planner_model_name or args.model_name,
            },
            "proposer": {
                "base_url": args.proposer_model_base_url or args.model_base_url,
                "model": args.proposer_model_name or args.model_name,
            },
            "auditor": {
                "base_url": args.auditor_model_base_url or args.model_base_url,
                "model": args.auditor_model_name or args.model_name,
            },
            "fixer": {
                "base_url": args.fixer_model_base_url or args.model_base_url,
                "model": args.fixer_model_name or args.model_name,
            },
        },
        "workbench_db": str(args.workbench_db),
        "selected_count": len(rows),
        "processed_count": processed,
        "skipped_count": skipped,
        "failure_count": failures,
        "counts": dict(sorted(counts.items())),
        "production_writes": False,
        "elapsed_seconds": round(time.time() - started, 3),
        "events": str(events_path),
        "staged_updates": str(args.out_dir / "staged_htc_updates.jsonl"),
        "machine_evidence_expansion": str(args.out_dir / "machine_evidence_expansion.jsonl"),
    }
    (args.out_dir / "runner_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consensus", type=Path, default=DEFAULT_CONSENSUS)
    parser.add_argument("--products", type=Path, default=DEFAULT_PRODUCTS)
    parser.add_argument("--recipes", type=Path, default=DEFAULT_RECIPES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--upc", action="append", default=[])
    parser.add_argument("--rowid", action="append", default=[])
    parser.add_argument("--model-base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model-name", default=DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--planner-model-base-url", default="")
    parser.add_argument("--planner-model-name", default="")
    parser.add_argument("--planner-temperature", type=float, default=None)
    parser.add_argument("--proposer-model-base-url", default="")
    parser.add_argument("--proposer-model-name", default="")
    parser.add_argument("--proposer-temperature", type=float, default=None)
    parser.add_argument("--auditor-model-base-url", default="")
    parser.add_argument("--auditor-model-name", default="")
    parser.add_argument("--auditor-temperature", type=float, default=None)
    parser.add_argument("--fixer-model-base-url", default="")
    parser.add_argument("--fixer-model-name", default="")
    parser.add_argument("--fixer-temperature", type=float, default=None)
    parser.add_argument("--workbench-db", type=Path, default=DEFAULT_WORKBENCH_DB)
    parser.add_argument("--no-workbench", action="store_true")
    parser.add_argument("--build-workbench-if-missing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--workbench-recipe-limit", type=int, default=250000)
    parser.add_argument("--no-workbench-fts", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=1000)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--evidence-rounds", type=int, default=1)
    parser.add_argument("--planning-rounds", type=int, default=1)
    parser.add_argument("--max-processed", type=int, default=0)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-going", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--prefilter-updates-only",
        action="store_true",
        help="Use the deterministic prefilter to spend vLLM calls only on likely update candidates.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary = run_batch(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
