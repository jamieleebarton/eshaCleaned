#!/usr/bin/env python3
"""Audit protein-source supply in concept artifacts and selected plans."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from htc_groups import protein_source  # noqa: E402


DATA = ROOT / "data"
SOURCE_NAMES = {
    -1: "untagged",
    0: "red_meat",
    1: "pork",
    2: "poultry",
    3: "fish",
    4: "eggs",
    5: "legumes_nuts",
}


def _pctiles(values: list[float]) -> dict:
    if not values:
        return {"median": 0.0, "p75": 0.0, "p90": 0.0}
    values = sorted(values)
    def pick(q: float) -> float:
        idx = min(len(values) - 1, max(0, round((len(values) - 1) * q)))
        return round(values[idx], 1)
    return {
        "median": round(statistics.median(values), 1),
        "p75": pick(0.75),
        "p90": pick(0.90),
    }


def audit_recipe_supply(cache_path: Path) -> dict:
    cache = torch.load(cache_path, map_location="cpu")
    src = cache["protein_source"]
    nutr = cache["nutrition"].float()
    cal = nutr[:, 0]
    protein_g = nutr[:, 1]
    prot_pct = torch.where(cal > 0, protein_g * 4.0 / cal * 100.0, torch.zeros_like(cal))

    out: dict[str, dict] = {}
    for code, name in SOURCE_NAMES.items():
        mask = src == code
        vals = prot_pct[mask].tolist()
        out[name] = {
            "recipes": int(mask.sum().item()),
            "protein_pct": _pctiles([float(v) for v in vals if v > 0]),
            "recipes_ge_15pct": int(((prot_pct >= 15) & mask).sum().item()),
            "recipes_ge_20pct": int(((prot_pct >= 20) & mask).sum().item()),
            "recipes_ge_25pct": int(((prot_pct >= 25) & mask).sum().item()),
        }
    out["total"] = {"recipes": int(src.numel())}
    return out


def audit_package_supply(concept_index_path: Path) -> dict:
    ci = json.loads(concept_index_path.read_text())
    buckets: dict[int, dict] = defaultdict(lambda: {
        "concepts": 0,
        "packages": 0,
        "cheapest_packages": [],
        "canonical_examples": Counter(),
    })

    for ck, concept in ci.items():
        code = protein_source(ck)
        b = buckets[code]
        b["concepts"] += 1
        packages = [
            p for p in concept.get("packages", [])
            if float(p.get("grams") or 0) > 0 and int(p.get("cents") or 0) > 0
        ]
        b["packages"] += len(packages)
        cp = ck.split("|", 1)[0]
        b["canonical_examples"][cp] += len(packages)
        for pkg in packages:
            grams = float(pkg.get("grams") or 0)
            cents = int(pkg.get("cents") or 0)
            b["cheapest_packages"].append({
                "concept_key": ck,
                "name": pkg.get("name", ""),
                "grams": round(grams, 1),
                "cents": cents,
                "cpg": round(cents / grams, 4),
                "display": pkg.get("size_display", ""),
            })

    out: dict[str, dict] = {}
    for code, b in sorted(buckets.items()):
        name = SOURCE_NAMES.get(code, str(code))
        cheapest = sorted(b["cheapest_packages"], key=lambda r: r["cpg"])[:12]
        examples = b["canonical_examples"].most_common(12)
        out[name] = {
            "concepts": b["concepts"],
            "packages": b["packages"],
            "top_canonical_paths_by_packages": examples,
            "cheapest_packages": cheapest,
        }
    return out


def audit_plan(plan_path: Path) -> dict:
    plan = json.loads(plan_path.read_text())
    buckets: dict[int, dict] = defaultdict(lambda: {
        "purchase_rows": 0,
        "packages": 0.0,
        "grams": 0.0,
        "cost": 0.0,
        "examples": Counter(),
    })
    for week in plan.get("weeks", []):
        for row in week.get("ingredient_purchases", []) or []:
            code = protein_source(row.get("concept_key", ""))
            b = buckets[code]
            b["purchase_rows"] += 1
            b["packages"] += float(row.get("n_packages") or 0)
            b["grams"] += float(row.get("purchased_grams") or 0)
            b["cost"] += float(row.get("cost") or 0)
            sku = row.get("selected_sku") or ""
            if sku:
                b["examples"][sku] += 1

    out: dict[str, dict] = {}
    for code, b in sorted(buckets.items()):
        name = SOURCE_NAMES.get(code, str(code))
        out[name] = {
            "purchase_rows": b["purchase_rows"],
            "packages": round(b["packages"], 2),
            "grams": round(b["grams"], 1),
            "cost": round(b["cost"], 2),
            "top_skus": b["examples"].most_common(10),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-json", type=Path)
    parser.add_argument("--out", type=Path, default=DATA / "protein_supply_audit.json")
    args = parser.parse_args()

    summary = {
        "recipe_supply": audit_recipe_supply(DATA / "tensor_cache" / "recipe_db_tensors.pt"),
        "package_supply": audit_package_supply(DATA / "concept_index.json"),
    }
    if args.plan_json:
        summary["plan"] = str(args.plan_json)
        summary["plan_purchase_mix"] = audit_plan(args.plan_json)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2))

    rs = summary["recipe_supply"]
    ps = summary["package_supply"]
    print("recipe protein-source counts:")
    for name in ["red_meat", "pork", "poultry", "fish", "eggs", "legumes_nuts", "untagged"]:
        print(f"  {name:12s} {rs.get(name, {}).get('recipes', 0):>7,}")
    print("package protein-source buckets:")
    for name in ["red_meat", "pork", "poultry", "fish", "eggs", "legumes_nuts"]:
        row = ps.get(name, {})
        print(
            f"  {name:12s} concepts={row.get('concepts', 0):>4} "
            f"packages={row.get('packages', 0):>5}"
        )
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
