"""Run RUVS verification against the actual planner's output.

Reads `output/ruvs/real_plan/plan.json` (produced by dump_real_plan.py),
builds substrate-populated packets per (recipe, fndds_code) line,
verifies each via DeepSeek (using inline candidates, no live tool calls
when the substrate is rich), aggregates fix queue, applies T2 review,
emits patches.

This is what should have been the v1 smoke from the start.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

from ruvs.budget import Budget, BudgetExceeded
from ruvs.nebius import NebiusClient
from ruvs.schemas import Packet, ProductCandidate
from ruvs.substrate import (
    load_audit_by_fndds, load_packages_by_fndds, fndds_food_description,
)
from ruvs_verify import verify_line
from ruvs_verdicts import append_verdict, load_verdicts
from ruvs_fix_queue import build_fix_queue
from ruvs_review import review_fix_queue
from ruvs_patches import generate_patches


PLAN_PATH = Path(__file__).parent / "output" / "ruvs" / "real_plan" / "plan.json"
OUT_DIR = Path(__file__).parent / "output" / "ruvs" / "real_plan"


def build_packet_from_substrate(
    *, recipe_id: int, recipe_name: str, fndds_code: str, recipe_grams: float,
    audit_rows: list[dict], walmart_cands: list[ProductCandidate],
    kroger_cands: list[ProductCandidate], food_description: str,
    line_idx: int = 0, config: dict | None = None,
) -> Packet:
    """Build a Packet from pre-loaded substrate (no live retailer calls)."""
    audit_first = audit_rows[0] if audit_rows else {}
    return Packet(
        recipe_id=recipe_id,
        line_idx=line_idx,                             # ingredient index within this recipe
        config_bucket=f"household={config.get('household',4) if config else 4}|dietary=none|pattern=3meal",
        recipe_text=f"{recipe_name}: ingredient fndds {fndds_code} ({food_description}), {recipe_grams:.0f}g needed",
        parsed_item=food_description.lower(),
        recipe_grams=recipe_grams,
        hestia_canonical=food_description,             # the food_description Hestia is treating as canonical
        audit_candidates=audit_rows[:5],
        fndds_desc=food_description,
        sr28_desc=audit_first.get("sr28_code", "") or "",
        esha_desc=audit_first.get("esha_code", "") or "",
        walmart_candidates=walmart_cands[:5],
        kroger_candidates=kroger_cands[:5],
        config=config or {"household": 4, "dietary": "none", "pattern": "3meal"},
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-usd", type=float, default=2.00,
                    help="Hard cap on DeepSeek spend (default $2)")
    ap.add_argument("--max-lines", type=int, default=0,
                    help="Limit number of (recipe, fndds) lines verified (0 = all in plan)")
    ap.add_argument("--recipe", type=int, default=0,
                    help="Only verify this recipe_id (0 = all)")
    args = ap.parse_args()

    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        print(json.dumps({"error": "NEBIUS_API_KEY required"}))
        return 2
    if not PLAN_PATH.exists():
        print(json.dumps({"error": f"plan not found: {PLAN_PATH}. Run dump_real_plan.py first."}))
        return 2

    plan = json.loads(PLAN_PATH.read_text())
    print(f"Loaded plan: ${plan['total_cost_usd']:.2f}, {plan['stats']['n_distinct_recipes']} recipes, "
          f"{plan['stats']['n_distinct_fndds_codes']} fndds codes, "
          f"{plan['stats']['n_ingredient_lines_with_candidates']} candidate-backed lines",
          file=sys.stderr)

    print("Loading substrate...", file=sys.stderr)
    audit_by_fndds = load_audit_by_fndds()
    packages_by_fndds = load_packages_by_fndds()
    food_desc_by_fndds = fndds_food_description()
    print(f"  audit fndds_codes: {len(audit_by_fndds):,}", file=sys.stderr)
    print(f"  packaged fndds_codes: {len(packages_by_fndds):,}", file=sys.stderr)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    packet_path = OUT_DIR / "packets.jsonl"
    verdict_path = OUT_DIR / "verdicts.jsonl"
    queue_path = OUT_DIR / "fix_queue.csv"
    patches_dir = OUT_DIR / "patches"
    # fresh outputs
    for p in (packet_path, verdict_path, queue_path):
        if p.exists(): p.unlink()
    if patches_dir.exists():
        for sub in patches_dir.glob("*"):
            if sub.is_dir():
                for f in sub.glob("*"):
                    f.unlink()
            else:
                sub.unlink()

    budget = Budget(cap_usd=args.budget_usd)
    client = NebiusClient(api_key=api_key)

    started = time.time()
    n_lines = 0
    n_clean = 0
    n_dirty = 0
    packets_by_recipe: dict[int, Packet] = {}
    skipped_no_candidates = 0

    for rid_str, rec in plan["recipes"].items():
        rid = int(rid_str)
        if args.recipe and rid != args.recipe:
            continue
        rname = rec["name"]
        for ing_idx, (fndds_code, ing) in enumerate(rec["ingredients"].items()):
            if args.max_lines and n_lines >= args.max_lines:
                break
            grams = float(ing["grams"])
            audit_rows = audit_by_fndds.get(fndds_code, [])
            packs = packages_by_fndds.get(fndds_code, {"walmart": [], "kroger": []})
            wm_cands = packs.get("walmart", [])
            kr_cands = packs.get("kroger", [])
            if not wm_cands and not kr_cands:
                skipped_no_candidates += 1
                continue
            food_desc = food_desc_by_fndds.get(fndds_code, "")
            pkt = build_packet_from_substrate(
                recipe_id=rid, recipe_name=rname, fndds_code=fndds_code,
                recipe_grams=grams, audit_rows=audit_rows,
                walmart_cands=wm_cands, kroger_cands=kr_cands,
                food_description=food_desc, line_idx=ing_idx,
            )
            with packet_path.open("a", encoding="utf-8") as f:
                f.write(pkt.to_json() + "\n")
            try:
                v = verify_line(packet=pkt, client=client, run_id="real_plan.h4w1")
                budget.add(float(v.evidence.get("cost_usd") or 0.0))
                append_verdict(v, verdict_path)
                if v.is_clean(): n_clean += 1
                else: n_dirty += 1
                packets_by_recipe.setdefault(rid, pkt)
                n_lines += 1
                if n_lines % 10 == 0:
                    print(f"  ...{n_lines} lines, clean={n_clean} dirty={n_dirty} spent=${budget.spent_usd:.4f}",
                          file=sys.stderr)
            except BudgetExceeded as e:
                print(f"BUDGET EXCEEDED at {n_lines} lines: {e}", file=sys.stderr)
                break
        if args.max_lines and n_lines >= args.max_lines:
            break
        if budget.spent_usd >= budget.cap_usd:
            break

    verdicts = load_verdicts(verdict_path)
    build_fix_queue(verdicts, queue_path)
    review_fix_queue(queue_path, client=client, packets_by_recipe=packets_by_recipe, escalate_above=100)
    generate_patches(queue_path, patches_dir)

    summary = {
        "lines_verified": n_lines,
        "lines_clean": n_clean,
        "lines_dirty": n_dirty,
        "skipped_no_candidates": skipped_no_candidates,
        "spent_usd": round(budget.spent_usd, 4),
        "elapsed_s": round(time.time() - started, 1),
        "fix_queue": str(queue_path),
        "patches_dir": str(patches_dir),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
