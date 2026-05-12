#!/usr/bin/env python3
"""Audit local sparse-cascade plan purchases against the package database."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "implementation" / "output" / "sparse_cascade_planner"
DEFAULT_PLAN_JSON = OUT_DIR / "local_sparse_plan.12week.fullpurchases.json"
DEFAULT_PACKAGE_DB = OUT_DIR / "food_packages_calculator_native.db"
DEFAULT_INGREDIENT_META = OUT_DIR / "ingredient_meta.json"
DEFAULT_OUT_JSON = OUT_DIR / "local_sparse_plan.12week.purchase_audit.json"
DEFAULT_OUT_MD = OUT_DIR / "local_sparse_plan.12week.purchase_audit.md"

SUSPICIOUS_TITLE_TOKENS = {
    "air",
    "aromatherapy",
    "body",
    "candle",
    "cat",
    "deodorizer",
    "facial",
    "hair",
    "litter",
    "lotion",
    "mouthwash",
    "pet",
    "shampoo",
    "soap",
    "supplement",
    "toothpaste",
    "unisex",
    "wash",
    "wax",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def load_package_rows(db_path: Path) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT fndds_code, food_description, package_weight_grams,
                   walmart_price_cents, kroger_price_cents, source, product_meta
            FROM packages
            ORDER BY fndds_code, package_weight_grams
            """
        ).fetchall()
    for key, description, grams, walmart_cents, kroger_cents, source, product_meta in rows:
        samples = []
        try:
            parsed = json.loads(product_meta or "{}")
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            samples = parsed.get("calculator_native_samples") or []
        out[str(key)].append(
            {
                "ingredient_key": key,
                "description": description or "",
                "grams": float(grams or 0.0),
                "walmart_price_cents": walmart_cents,
                "kroger_price_cents": kroger_cents,
                "source": source or "",
                "samples": samples if isinstance(samples, list) else [],
            }
        )
    return out


def sample_names(rows: list[dict[str, Any]], limit: int = 5) -> list[str]:
    names: list[str] = []
    for row in rows:
        for sample in row.get("samples") or []:
            if not isinstance(sample, dict):
                continue
            name = str(sample.get("name") or "").strip()
            if name and name not in names:
                names.append(name)
            if len(names) >= limit:
                return names
    return names


def suspicious_samples(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for row in rows:
        description = str(row.get("description") or "")
        for sample in row.get("samples") or []:
            if not isinstance(sample, dict):
                continue
            name = str(sample.get("name") or "")
            tokens = {token.lower() for token in name.replace("-", " ").replace("/", " ").split()}
            overlap = sorted(tokens & SUSPICIOUS_TITLE_TOKENS)
            if overlap:
                hits.append(
                    {
                        "description": description,
                        "name": name,
                        "reason": "suspicious_title_tokens:" + ",".join(overlap),
                    }
                )
    return hits


def aggregate_purchases(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    aggregated: dict[str, dict[str, Any]] = {}
    for week in plan.get("weeks") or []:
        week_no = int(week.get("week") or 0)
        for purchase in week.get("top_purchases") or []:
            key = str(purchase.get("ingredient_key") or "")
            if not key:
                continue
            item = aggregated.setdefault(
                key,
                {
                    "ingredient_key": key,
                    "weeks": set(),
                    "packages": 0.0,
                    "grams": 0.0,
                    "cost": 0.0,
                },
            )
            item["weeks"].add(week_no)
            item["packages"] += float(purchase.get("packages") or 0.0)
            item["grams"] += float(purchase.get("grams") or 0.0)
            item["cost"] += float(purchase.get("cost") or 0.0)
    for item in aggregated.values():
        item["weeks"] = sorted(item["weeks"])
        item["packages"] = round(item["packages"], 4)
        item["grams"] = round(item["grams"], 3)
        item["cost"] = round(item["cost"], 2)
    return aggregated


def audit(plan_json: Path, package_db: Path, ingredient_meta: Path) -> dict[str, Any]:
    plan = load_json(plan_json)
    packages_by_key = load_package_rows(package_db)
    meta = load_json(ingredient_meta)
    purchases = aggregate_purchases(plan)

    default_items: list[dict[str, Any]] = []
    store_items: list[dict[str, Any]] = []
    suspicious: list[dict[str, Any]] = []
    total_cost = 0.0
    default_cost = 0.0
    store_cost = 0.0

    for key, item in purchases.items():
        total_cost += item["cost"]
        info = meta.get(key) or {}
        description = (
            info.get("description")
            or info.get("food_description")
            or info.get("esha_description")
            or info.get("sr28_description")
            or info.get("fndds_description")
            or ""
        )
        rows = packages_by_key.get(key) or []
        enriched = {
            **item,
            "description": description,
            "package_rows": len(rows),
            "sample_products": sample_names(rows),
        }
        if rows:
            store_cost += item["cost"]
            store_items.append(enriched)
            for hit in suspicious_samples(rows):
                suspicious.append({"ingredient_key": key, **hit})
        else:
            default_cost += item["cost"]
            default_items.append(enriched)

    default_items.sort(key=lambda row: row["cost"], reverse=True)
    store_items.sort(key=lambda row: row["cost"], reverse=True)
    suspicious.sort(key=lambda row: (row["ingredient_key"], row["name"]))

    return {
        "plan_json": str(plan_json),
        "package_db": str(package_db),
        "weeks": len(plan.get("weeks") or []),
        "meal_count": len(plan.get("meals") or []),
        "purchase_key_count": len(purchases),
        "total_purchase_cost": round(total_cost, 2),
        "store_backed_cost": round(store_cost, 2),
        "default_priced_cost": round(default_cost, 2),
        "store_backed_cost_pct": round(store_cost / total_cost * 100.0, 2) if total_cost else 0.0,
        "default_priced_cost_pct": round(default_cost / total_cost * 100.0, 2) if total_cost else 0.0,
        "store_backed_key_count": len(store_items),
        "default_priced_key_count": len(default_items),
        "top_default_priced": default_items[:30],
        "top_store_backed": store_items[:30],
        "suspicious_store_samples": suspicious[:100],
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Local Sparse Plan Purchase Audit",
        "",
        "## Summary",
        f"- Weeks: {report['weeks']}",
        f"- Meals: {report['meal_count']}",
        f"- Purchase keys: {report['purchase_key_count']}",
        f"- Total purchase cost: ${report['total_purchase_cost']:.2f}",
        f"- Store-backed cost: ${report['store_backed_cost']:.2f} ({report['store_backed_cost_pct']:.2f}%)",
        f"- Default-priced cost: ${report['default_priced_cost']:.2f} ({report['default_priced_cost_pct']:.2f}%)",
        f"- Store-backed keys: {report['store_backed_key_count']}",
        f"- Default-priced keys: {report['default_priced_key_count']}",
        "",
        "## Top Default-Priced Purchases",
    ]
    for row in report["top_default_priced"][:15]:
        lines.append(
            f"- `${row['cost']:.2f}` `{row['ingredient_key']}` {row['description']} "
            f"({row['grams']:.1f}g, weeks {row['weeks']})"
        )
    lines.extend(["", "## Top Store-Backed Purchases"])
    for row in report["top_store_backed"][:15]:
        sample = "; ".join(row["sample_products"][:2])
        lines.append(
            f"- `${row['cost']:.2f}` `{row['ingredient_key']}` {row['description']} "
            f"({row['grams']:.1f}g) -> {sample}"
        )
    lines.extend(["", "## Suspicious Store Samples"])
    if not report["suspicious_store_samples"]:
        lines.append("- None found by title-token scan.")
    else:
        for row in report["suspicious_store_samples"][:20]:
            lines.append(
                f"- `{row['ingredient_key']}` {row['description']}: {row['name']} ({row['reason']})"
            )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", type=Path, default=DEFAULT_PLAN_JSON)
    parser.add_argument("--package-db", type=Path, default=DEFAULT_PACKAGE_DB)
    parser.add_argument("--ingredient-meta", type=Path, default=DEFAULT_INGREDIENT_META)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit(
        plan_json=args.plan_json.expanduser(),
        package_db=args.package_db.expanduser(),
        ingredient_meta=args.ingredient_meta.expanduser(),
    )
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.out_md.write_text(build_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
