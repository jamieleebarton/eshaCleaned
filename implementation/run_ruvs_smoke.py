"""Run the full RUVS pipeline on recipe 506745 only. v1 acceptance gate."""
from __future__ import annotations
import argparse
import json
import os
import time
from pathlib import Path

from ruvs.budget import Budget
from ruvs.nebius import NebiusClient
from ruvs.schemas import Packet
from ruvs_packets import ReferenceData, build_packet
from ruvs_verify import verify_line
from ruvs_verdicts import append_verdict, load_verdicts
from ruvs_fix_queue import build_fix_queue
from ruvs_review import review_fix_queue
from ruvs_patches import generate_patches


RECIPE_ID = 506745
OUT_DIR = Path(__file__).parent / "output" / "ruvs" / "smoke_506745"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-usd", type=float, default=0.50)
    args = ap.parse_args()
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        print(json.dumps({"error": "NEBIUS_API_KEY required"}))
        return 2
    budget = Budget(cap_usd=args.budget_usd)
    client = NebiusClient(api_key=api_key)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    packet_path = OUT_DIR / "packets.jsonl"
    verdict_path = OUT_DIR / "verdicts.jsonl"
    queue_path = OUT_DIR / "fix_queue.csv"
    patches_dir = OUT_DIR / "patches"

    packets = _load_506745_lines()
    started = time.time()
    for pkt in packets:
        with packet_path.open("a", encoding="utf-8") as f:
            f.write(pkt.to_json() + "\n")
        v = verify_line(packet=pkt, client=client, run_id="smoke.506745")
        budget.add(float(v.evidence.get("cost_usd") or 0.0))
        append_verdict(v, verdict_path)
        if time.time() - started > 1200:
            print(json.dumps({"error": "smoke timeout (>20 min)"}))
            return 1

    verdicts = load_verdicts(verdict_path)
    build_fix_queue(verdicts, queue_path)
    packets_by_recipe = {RECIPE_ID: packets[0]} if packets else {}
    review_fix_queue(queue_path, client=client, packets_by_recipe=packets_by_recipe, escalate_above=100)
    generate_patches(queue_path, patches_dir)

    print(json.dumps({
        "recipe_id": RECIPE_ID,
        "lines": len(packets),
        "verdicts": len(verdicts),
        "clean": sum(1 for v in verdicts if v.is_clean()),
        "spent_usd": round(budget.spent_usd, 4),
        "elapsed_s": round(time.time() - started, 1),
        "fix_queue": str(queue_path),
        "patches_dir": str(patches_dir),
    }, indent=2))
    return 0


def _load_506745_lines() -> list[Packet]:
    """Load lines from the existing one_recipe_506745 packet artifact and rebuild Packets."""
    src = Path(__file__).parent / "output" / "one_recipe_506745_llm_verification_packet.jsonl"
    if not src.exists():
        return []
    out: list[Packet] = []
    ref = ReferenceData()
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        ing = rec.get("ingredient") or {}
        rname = (rec.get("recipe") or {})
        text = ing.get("original_recipe_text") or ""
        parsed = ing.get("parsed_item") or ""
        if not text or not parsed:
            continue
        out.append(build_packet(
            recipe_id=int(rname.get("recipe_num") or RECIPE_ID),
            line_idx=int(rname.get("line_index") or 0),
            config_bucket="household=4|dietary=none|pattern=3meal",
            recipe_text=text, parsed_item=parsed,
            recipe_grams=float(ing.get("recipe_grams") or 0.0),
            ref=ref,
            config={"household": 4, "dietary": "none", "pattern": "3meal"},
        ))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
