#!/usr/bin/env python3
"""Side-by-side cleanup audit: every unique ingredient_item from
ingredient_full_audit.csv, joined to its cleaned form from the
buyability classifier output (per-item modal aggregation).

For each item shows:
  - original raw item text (what recipes write)
  - recipe_count (how often it appears)
  - cleaned canonical_buy_form (what we'll shop for)
  - dominant_buyability (buyable / derivative / alternation / specialty / unbuyable / nonsense)
  - dominant_pct (how unanimous the classifier was)
  - identity_resolved_pct (how often the classifier committed to a SKU)
  - context_dependent flag (set if the cleanup varies by recipe — for those, planner uses per-line lookup, not modal)
  - top_buy_forms (the alternative cleaned forms seen)
  - status: "cleaned" / "not_yet_classified" (if classifier hasn't reached this item yet)

Output:
  recipe_pricing/ingredient_cleanup_audit.csv
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
AUDIT_IN = ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_full_audit.csv"
# Read from CLEANED file (post-process applied) when it exists, else raw.
CLEANED = ROOT / "recipe_pricing" / "buyability_classifications_cleaned.jsonl"
RAW = ROOT / "recipe_pricing" / "buyability_classifications.jsonl"
CLS_JSONL = CLEANED if CLEANED.exists() else RAW
OUT = ROOT / "recipe_pricing" / "ingredient_cleanup_audit.csv"


def main() -> int:
    # Aggregate classifier output per item: track buy_form distribution +
    # identity_resolved tallies. We don't reuse buyability_per_item.csv
    # because we need identity_resolved (the existing aggregator drops it).
    item_buyability: defaultdict[str, Counter] = defaultdict(Counter)
    item_buy_forms: defaultdict[str, Counter] = defaultdict(Counter)
    item_resolved: defaultdict[str, Counter] = defaultdict(lambda: Counter({"yes": 0, "no": 0}))
    item_recipes: defaultdict[str, set] = defaultdict(set)

    print(f"reading classifications from {CLS_JSONL.name}", file=sys.stderr)
    n_records = 0
    with CLS_JSONL.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_records += 1
            ings = {ing["line_index"]: ing for ing in r.get("ingredients", [])
                    if isinstance(ing, dict)}
            for c in r.get("classifications", []):
                idx = c.get("line_index")
                if idx is None:
                    continue
                ing = ings.get(idx, {})
                raw_item = (ing.get("item") or "").lower().strip()
                if not raw_item:
                    continue
                bu = c.get("buyability") or ""
                bf = (c.get("canonical_buy_form") or "").strip()
                rs = c.get("identity_resolved")
                item_buyability[raw_item][bu] += 1
                if bf:
                    item_buy_forms[raw_item][bf] += 1
                item_resolved[raw_item]["yes" if rs else "no"] += 1
                item_recipes[raw_item].add(r.get("recipe_id"))
            if n_records % 100_000 == 0:
                print(f"  read {n_records:,} recipes", file=sys.stderr)
    print(f"  total recipes read: {n_records:,}", file=sys.stderr)

    # Read the full ingredient list — every unique item
    print(f"reading master ingredient list from {AUDIT_IN.name}", file=sys.stderr)
    rows_out = []
    with AUDIT_IN.open() as f:
        for row in csv.DictReader(f):
            item = (row.get("item") or "").lower().strip()
            recipe_count_audit = int(row.get("recipe_count", "0") or 0)
            if not item:
                continue

            bc = item_buyability.get(item)
            if not bc:
                rows_out.append({
                    "item": item,
                    "recipe_count": recipe_count_audit,
                    "cleaned_canonical_buy_form": "",
                    "dominant_buyability": "",
                    "dominant_pct": "",
                    "identity_resolved_pct": "",
                    "is_context_dependent": "",
                    "top_buy_forms": "",
                    "modes_seen": "",
                    "status": "not_yet_classified",
                })
                continue

            total = sum(bc.values())
            dom_b, dom_n = bc.most_common(1)[0]
            dom_pct = dom_n / total
            modes = sorted(bc.keys())
            ctx = "1" if (len(modes) > 1 and dom_pct < 0.85) else ""
            forms = item_buy_forms.get(item, Counter())
            top_forms = " | ".join(f"{f}({n})" for f, n in forms.most_common(3))
            dom_form = forms.most_common(1)[0][0] if forms else ""
            res = item_resolved.get(item, Counter())
            res_total = res["yes"] + res["no"]
            res_pct = (res["yes"] / res_total) if res_total else 0
            rows_out.append({
                "item": item,
                "recipe_count": recipe_count_audit,
                "cleaned_canonical_buy_form": dom_form,
                "dominant_buyability": dom_b,
                "dominant_pct": f"{dom_pct:.0%}",
                "identity_resolved_pct": f"{res_pct:.0%}",
                "is_context_dependent": ctx,
                "top_buy_forms": top_forms,
                "modes_seen": " | ".join(modes),
                "status": "cleaned",
            })

    # Sort: cleaned items first by recipe_count desc, then not_yet
    rows_out.sort(key=lambda r: (r["status"] != "cleaned", -r["recipe_count"]))

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "item", "recipe_count",
            "cleaned_canonical_buy_form",
            "dominant_buyability", "dominant_pct",
            "identity_resolved_pct",
            "is_context_dependent",
            "top_buy_forms", "modes_seen",
            "status",
        ])
        w.writeheader()
        w.writerows(rows_out)

    n_cleaned = sum(1 for r in rows_out if r["status"] == "cleaned")
    n_pending = sum(1 for r in rows_out if r["status"] == "not_yet_classified")
    n_changed = sum(1 for r in rows_out
                    if r["status"] == "cleaned"
                    and r["cleaned_canonical_buy_form"]
                    and r["cleaned_canonical_buy_form"].lower() != r["item"])
    print(f"\ntotal items in audit: {len(rows_out):,}", file=sys.stderr)
    print(f"  cleaned:             {n_cleaned:,}", file=sys.stderr)
    print(f"    └ form changed:    {n_changed:,}  (renamed by classifier)", file=sys.stderr)
    print(f"    └ form unchanged:  {n_cleaned - n_changed:,}  (raw item already a SKU)", file=sys.stderr)
    print(f"  not_yet_classified:  {n_pending:,}  (classifier still running)", file=sys.stderr)
    print(f"\n  → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
