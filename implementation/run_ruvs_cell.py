"""Run RUVS pipeline for ONE config-matrix cell over 50 weeks. v1 final acceptance."""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

from ruvs.budget import Budget, BudgetExceeded
from ruvs.nebius import NebiusClient
from ruvs.schemas import Packet
from ruvs_universe import discover_universe
from ruvs_packets import ReferenceData, build_packet
from ruvs_verify import verify_line
from ruvs_verdicts import append_verdict, load_verdicts
from ruvs_fix_queue import build_fix_queue
from ruvs_review import review_fix_queue
from ruvs_patches import generate_patches


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell-id", required=True)
    ap.add_argument("--config", default="config_matrix.yaml")
    ap.add_argument("--budget-usd", type=float, default=50.0)
    args = ap.parse_args()
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        print(json.dumps({"error": "NEBIUS_API_KEY required"}))
        return 2

    out_root = Path(__file__).parent / "output" / "ruvs" / f"cell_{args.cell_id}"
    out_root.mkdir(parents=True, exist_ok=True)
    universe_path = out_root / "universe.jsonl"
    discover_universe(Path(args.config), universe_path)

    cell_rows = [
        r for r in (json.loads(line) for line in universe_path.read_text().splitlines() if line.strip())
        if r["config_id"] == args.cell_id
    ]
    print(f"cell={args.cell_id} universe_rows={len(cell_rows)}", file=sys.stderr)

    budget = Budget(cap_usd=args.budget_usd)
    client = NebiusClient(api_key=api_key)
    verdict_path = out_root / "verdicts.jsonl"
    started = time.time()
    seen_lines: set[tuple[int, int]] = set()
    ref = ReferenceData()
    for row in cell_rows:
        rid = row["recipe_id"]
        for line_idx, pkt in _iter_recipe_lines(rid, ref, args.cell_id):
            key = (rid, line_idx)
            if key in seen_lines:
                continue
            seen_lines.add(key)
            try:
                v = verify_line(packet=pkt, client=client, run_id=f"cell.{args.cell_id}")
                budget.add(float(v.evidence.get("cost_usd") or 0.0))
                append_verdict(v, verdict_path)
            except BudgetExceeded as e:
                print(f"BUDGET EXCEEDED: {e}", file=sys.stderr)
                break

    verdicts = load_verdicts(verdict_path)
    queue_path = out_root / "fix_queue.csv"
    build_fix_queue(verdicts, queue_path)
    review_fix_queue(queue_path, client=client, packets_by_recipe={}, escalate_above=100)
    generate_patches(queue_path, out_root / "patches")
    print(json.dumps({
        "cell": args.cell_id, "lines_verified": len(seen_lines),
        "verdicts": len(verdicts), "clean": sum(1 for v in verdicts if v.is_clean()),
        "spent_usd": round(budget.spent_usd, 4), "elapsed_s": round(time.time() - started, 1),
    }, indent=2))
    return 0


def _iter_recipe_lines(recipe_id: int, ref: ReferenceData, config_id: str):
    """Yield (line_idx, Packet) tuples for one recipe.

    PLACEHOLDER for v1. Real implementation needs to:
    1. Load `recipes2.csv` from Hestia (`/Users/jamiebarton/Desktop/Hestia/api/data/recipes2.csv`).
    2. Parse the recipe's ingredient list (Hestia has parsing logic in `api/scripts/deepseek_plate_template_experiment.py`).
    3. For each line, build a Packet via `build_packet(...)` with proper ReferenceData
       loaded from FNDDS cards, ESHA, full_corpus_audit, and current Hestia canonical.
    4. Thread household/dietary/pattern from cell config through to the Packet.

    Returns empty iterator in v1, which means the cell runner exercises only the
    aggregation pipeline (fix_queue/review/patches) on whatever verdicts exist
    from prior smoke runs. v2 fills this in.
    """
    sys.path.insert(0, "/Users/jamiebarton/Desktop/Hestia/api")
    return iter([])


if __name__ == "__main__":
    raise SystemExit(main())
