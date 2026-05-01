"""T2 LLM review of fix_queue.csv. Updates review_status in place."""
from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import Any

from ruvs.nebius import NebiusClient
from ruvs.prompts import build_review_messages
from ruvs.schemas import Packet


def review_fix_queue(
    queue_path: Path, *, client: NebiusClient,
    packets_by_recipe: dict[int, Packet],
    escalate_above: int = 100,
) -> None:
    rows = list(csv.DictReader(queue_path.open(encoding="utf-8")))
    headers = list(rows[0].keys()) if rows else []
    for r in rows:
        if r.get("review_status") != "pending":
            continue
        affected = int(r.get("affected_recipes_count") or "0")
        if affected > escalate_above:
            r["review_status"] = "escalated"
            continue
        sample_ids = json.loads(r.get("affected_recipes_sample") or "[]")
        sample_packet = packets_by_recipe.get(sample_ids[0]) if sample_ids else None
        verdict_dict = {"facets": {r["facet"]: "wrong_form" if r["facet"] == "form_correct" else "wrong"},
                        "rationale": "from queue"}
        fix_dict = {"patch_type": r["proposed_patch_type"], "canonical": r["canonical"],
                    "delta": json.loads(r["delta_merged"])}
        if sample_packet is not None:
            messages = build_review_messages(sample_packet, verdict_dict, fix_dict)
        else:
            messages = [
                {"role": "system", "content": "You are reviewing a proposed canonical fix without recipe packet context."},
                {"role": "user", "content": json.dumps({"verdict": verdict_dict, "fix": fix_dict})},
            ]
        result = client.chat(messages=messages, tools=[])
        try:
            d = json.loads(_strip(result.content))
            decision = d.get("decision", "escalate")
        except Exception:
            decision = "escalate"
        # Normalize to past-tense status values used elsewhere.
        r["review_status"] = {
            "approve": "approved",
            "reject": "rejected",
            "escalate": "escalated",
        }.get(decision, "escalated")
    with queue_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _strip(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0]
    return s.strip()
