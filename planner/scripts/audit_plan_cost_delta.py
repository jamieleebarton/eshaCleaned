#!/usr/bin/env python3
"""Compare two multi-week plan JSON files by cost drivers."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from htc_groups import protein_source  # noqa: E402


SOURCE_NAMES = {
    -1: "untagged",
    0: "red_meat",
    1: "pork",
    2: "poultry",
    3: "fish",
    4: "eggs",
    5: "legumes_nuts",
}


def _iter_purchases(plan: dict):
    for week in plan.get("weeks", []) or []:
        for row in week.get("ingredient_purchases", []) or []:
            yield row


def _dept(concept_key: str) -> str:
    path = concept_key.split("|", 1)[0]
    return path.split(">", 1)[0].strip() or "(unknown)"


def _agg(plan: dict) -> dict:
    by_dept = defaultdict(float)
    by_source = defaultdict(float)
    by_concept = defaultdict(lambda: {"cost": 0.0, "packages": 0.0, "skus": Counter()})
    by_sku = defaultdict(lambda: {"cost": 0.0, "packages": 0.0, "concepts": Counter()})
    for row in _iter_purchases(plan):
        concept = row.get("concept_key") or ""
        sku = row.get("selected_sku") or "(none)"
        cost = float(row.get("cost") or 0.0)
        packages = float(row.get("n_packages") or 0.0)
        by_dept[_dept(concept)] += cost
        by_source[SOURCE_NAMES.get(protein_source(concept), "unknown")] += cost
        by_concept[concept]["cost"] += cost
        by_concept[concept]["packages"] += packages
        by_concept[concept]["skus"][sku] += 1
        by_sku[sku]["cost"] += cost
        by_sku[sku]["packages"] += packages
        by_sku[sku]["concepts"][concept] += 1
    return {
        "dept": by_dept,
        "source": by_source,
        "concept": by_concept,
        "sku": by_sku,
    }


def _delta_rows(a: dict, b: dict, key_name: str, limit: int) -> list[dict]:
    keys = set(a) | set(b)
    rows = []
    for key in keys:
        aval = a.get(key, 0.0)
        bval = b.get(key, 0.0)
        if isinstance(aval, dict) or isinstance(bval, dict):
            ad = aval if isinstance(aval, dict) else {}
            bd = bval if isinstance(bval, dict) else {}
            ac = float(ad.get("cost", 0.0))
            bc = float(bd.get("cost", 0.0))
            row = {key_name: key, "from": round(ac, 2), "to": round(bc, 2), "delta": round(bc - ac, 2)}
            ap = float(ad.get("packages", 0.0))
            bp = float(bd.get("packages", 0.0))
            row["packages_from"] = round(ap, 2)
            row["packages_to"] = round(bp, 2)
            row["packages_delta"] = round(bp - ap, 2)
            if bd.get("skus"):
                row["top_to_skus"] = bd["skus"].most_common(5)
            if bd.get("concepts"):
                row["top_to_concepts"] = bd["concepts"].most_common(5)
        else:
            ac = float(aval)
            bc = float(bval)
            row = {key_name: key, "from": round(ac, 2), "to": round(bc, 2), "delta": round(bc - ac, 2)}
        rows.append(row)
    rows.sort(key=lambda r: abs(r["delta"]), reverse=True)
    return rows[:limit]


def _summary(plan: dict) -> dict:
    totals = plan.get("totals") or {}
    config = plan.get("config") or {}
    return {
        "avg_weekly_cost": totals.get("avg_weekly_cost"),
        "avg_protein_pct": totals.get("avg_protein_pct"),
        "avg_veg_compliance": totals.get("avg_veg_compliance"),
        "daily_protein_g": config.get("daily_protein_g"),
        "effective_scoring": config.get("effective_scoring"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("from_plan", type=Path)
    parser.add_argument("to_plan", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    a = json.loads(args.from_plan.read_text())
    b = json.loads(args.to_plan.read_text())
    aa = _agg(a)
    bb = _agg(b)
    out = {
        "from_plan": str(args.from_plan),
        "to_plan": str(args.to_plan),
        "from_summary": _summary(a),
        "to_summary": _summary(b),
        "delta": {
            "avg_weekly_cost": round(float((b.get("totals") or {}).get("avg_weekly_cost") or 0.0)
                                     - float((a.get("totals") or {}).get("avg_weekly_cost") or 0.0), 2),
            "avg_protein_pct": round(float((b.get("totals") or {}).get("avg_protein_pct") or 0.0)
                                     - float((a.get("totals") or {}).get("avg_protein_pct") or 0.0), 1),
        },
        "by_department": _delta_rows(aa["dept"], bb["dept"], "department", args.limit),
        "by_protein_source": _delta_rows(aa["source"], bb["source"], "protein_source", args.limit),
        "by_concept": _delta_rows(aa["concept"], bb["concept"], "concept_key", args.limit),
        "by_sku": _delta_rows(aa["sku"], bb["sku"], "sku", args.limit),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))

    print(f"{args.from_plan.name} -> {args.to_plan.name}")
    print(
        f"  avg/week delta ${out['delta']['avg_weekly_cost']:+.2f}, "
        f"protein delta {out['delta']['avg_protein_pct']:+.1f}pp"
    )
    print("  top department deltas:")
    for row in out["by_department"][:8]:
        print(f"    {row['department']:<18} ${row['delta']:+.2f}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
