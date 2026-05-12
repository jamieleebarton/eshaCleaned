#!/usr/bin/env python3
"""Print buyability test-pack results in a human-readable form for review."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "recipe_pricing" / "buyability_testpack_results.jsonl"


def main() -> int:
    by_signal: dict[str, list[dict]] = {}
    with RESULTS.open() as f:
        for line in f:
            r = json.loads(line)
            by_signal.setdefault(r["signal_label"], []).append(r)

    for label, recipes in by_signal.items():
        print(f"\n{'='*80}")
        print(f"SIGNAL: {label}")
        print('='*80)
        for r in recipes:
            print(f"\n>> [{r['recipe_id']}] {r['title']}")
            cls_by_idx = {c["line_index"]: c for c in r.get("classifications", [])}
            for ing in r["ingredients"]:
                idx = ing["line_index"]
                c = cls_by_idx.get(idx, {})
                bu = c.get("buyability", "?")
                bf = c.get("canonical_buy_form")
                bi = c.get("base_ingredients") or []
                us = c.get("usage", "?")
                rat = c.get("rationale", "")
                bf_s = repr(bf) if bf else "—"
                bi_s = ", ".join(bi) if bi else ""
                print(f"  [{idx:>2}] {ing['display'][:60]:<62}")
                print(f"        item={ing['item']!r}")
                print(f"        → buy={bu}  use={us}  form={bf_s}")
                if bi_s: print(f"        base=[{bi_s}]")
                if rat:  print(f"        ({rat})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
