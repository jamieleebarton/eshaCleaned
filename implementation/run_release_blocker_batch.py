"""End-to-end driver: release_blocker_queue -> tool worker -> staged patch -> human review.

Non-negotiables:
  - Never auto-applies to reviewed_*.py; every patch goes to the review dir
  - After each patch staged, re-runs the calculator correctness fixture
  - If fixture breaks, stops and flags the blocker
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "implementation" / "output" / "release_blocker_queue.csv"
REVIEW_DIR = ROOT / "implementation" / "output" / "release_blocker_review_queue"
FIXTURE = "implementation.tests.test_calculator_correctness"


def load_blockers(limit: int) -> list[dict[str, str]]:
    with QUEUE.open() as fh:
        rows = list(csv.DictReader(fh))
    return rows[:limit]


def run_fixture() -> dict:
    r = subprocess.run(
        [sys.executable, "-m", "unittest", FIXTURE],
        cwd=str(ROOT),
        capture_output=True,
        timeout=180,
    )
    tail = r.stderr.decode()[-600:]
    failures = 0
    errors = 0
    tests_run = None
    m = re.search(r"Ran (\d+) tests", tail)
    if m:
        tests_run = int(m.group(1))
    m = re.search(r"failures=(\d+)", tail)
    if m:
        failures = int(m.group(1))
    m = re.search(r"errors=(\d+)", tail)
    if m:
        errors = int(m.group(1))
    return {
        "returncode": r.returncode,
        "tests_run": tests_run,
        "failures": failures,
        "errors": errors,
        "tail": tail,
    }


def safe_slug(item: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", item).strip("_") or "blocker"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--dry-run", action="store_true",
                   help="Print the plan + fixture state; do NOT call Nebius or stage patches.")
    p.add_argument("--audit-api", default="http://127.0.0.1:8765")
    p.add_argument("--max-card-chars", type=int, default=10000,
                   help="Trim ESHA card markdown sent to the agent. 10000 fits Qwen3-32B's 40960-token context.")
    p.add_argument("--max-tokens", type=int, default=3500,
                   help="Output token budget. 3500 leaves room for ~35K input tokens in Qwen3-32B.")
    args = p.parse_args()

    blockers = load_blockers(args.limit)
    plan = {
        "mode": "dry-run" if args.dry_run else "live",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "audit_api": args.audit_api,
        "limit": args.limit,
        "blockers": [
            {
                "rank": b.get("rank"),
                "normalized_item": b.get("normalized_item"),
                "esha_code": b.get("esha_code"),
                "impact_score": b.get("impact_score"),
                "blocker_reason": b.get("blocker_reason"),
            }
            for b in blockers
        ],
    }

    fixture_entry = run_fixture()
    plan["fixture_entry_state"] = {
        "tests_run": fixture_entry["tests_run"],
        "failures": fixture_entry["failures"],
        "errors": fixture_entry["errors"],
        "returncode": fixture_entry["returncode"],
    }

    if args.dry_run:
        json.dump(plan, sys.stdout, indent=2)
        return

    # Live mode
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    baseline_failures = fixture_entry["failures"]
    results = []
    for b in blockers:
        code = (b.get("esha_code") or "").strip()
        item = (b.get("normalized_item") or "").strip()
        if not code:
            results.append({"normalized_item": item, "status": "skipped_no_code"})
            continue
        bundle_dir = REVIEW_DIR / safe_slug(item)
        bundle_dir.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            [sys.executable, "implementation/nebius_esha_tool_worker.py",
             "--audit-api", args.audit_api,
             "--esha-code", code,
             "--out-dir", str(bundle_dir),
             "--max-card-chars", str(args.max_card_chars),
             "--max-tokens", str(args.max_tokens)],
            cwd=str(ROOT),
            capture_output=True,
            timeout=600,
            env={**os.environ},
        )
        results.append({
            "normalized_item": item,
            "esha_code": code,
            "bundle_dir": str(bundle_dir),
            "worker_returncode": r.returncode,
            "worker_stderr_tail": r.stderr.decode()[-400:],
        })
        fx = run_fixture()
        if fx["failures"] > baseline_failures or fx["errors"] > 0:
            plan["stopped_on"] = item
            plan["stop_reason"] = "fixture regression"
            plan["fixture_exit_state"] = {
                "tests_run": fx["tests_run"],
                "failures": fx["failures"],
                "errors": fx["errors"],
            }
            plan["results"] = results
            json.dump(plan, sys.stdout, indent=2)
            sys.exit(2)
    plan["results"] = results
    final_fx = run_fixture()
    plan["fixture_exit_state"] = {
        "tests_run": final_fx["tests_run"],
        "failures": final_fx["failures"],
        "errors": final_fx["errors"],
    }
    json.dump(plan, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
