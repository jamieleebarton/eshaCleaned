#!/usr/bin/env python3
"""Append audited cheese-variety identities to the HTC food-slot registry.

The base registry is built from ``product_identity_fixed``.  Some cheese rows
were curated as generic ``Cheese`` while the actual shoppable variety lives in
the retail path modifier, FNDDS description, or SR-28 description.  This overlay
adds stable slots for those known varieties without reordering existing codes.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_REGISTRY = HERE / "food_slot_registry.csv"
DEFAULT_AUDIT = REPO / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
DEFAULT_ITEMS = HERE.parent / "output" / "recipe_ingredient_items.csv"

sys.path.insert(0, str(HERE.parent))

from htc.cheese_identities import cheese_identity_from_text, cheese_registry_names  # noqa: E402
from htc.food_slots import CROCKFORD, normalize_key  # noqa: E402


def slot_to_index(slot: str) -> int:
    return CROCKFORD.index(slot[0]) * 32 + CROCKFORD.index(slot[1])


def slot_for_index(index: int) -> str:
    return CROCKFORD[index // 32] + CROCKFORD[index % 32]


def evidence_counts(audit_path: Path, items_path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    if audit_path.exists():
        with audit_path.open(encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                path = row.get("canonical_path") or ""
                pid = row.get("product_identity_fixed") or ""
                if not (path.startswith("Dairy > Cheese") or normalize_key(pid) in {"cheese", "cheddar", "mozzarella", "monterey jack"}):
                    continue
                text = " ".join(
                    row.get(field, "") or ""
                    for field in (
                        "title",
                        "canonical_path",
                        "canonical_label",
                        "product_identity_fixed",
                        "modifier",
                        "retail_leaf_path",
                        "fndds_desc",
                        "sr28_desc",
                    )
                )
                identity = cheese_identity_from_text(text)
                if identity:
                    counts[identity] += 1
    if items_path.exists():
        with items_path.open(encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                item = row.get("item") or ""
                if "cheese" not in item.lower() and not cheese_identity_from_text(item):
                    continue
                identity = cheese_identity_from_text(item)
                if identity:
                    try:
                        counts[identity] += max(1, int(float(row.get("recipe_count") or 1)))
                    except ValueError:
                        counts[identity] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    args = parser.parse_args()

    rows: list[dict[str, str]] = []
    with args.registry.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    if not fieldnames:
        print(f"registry has no header: {args.registry}", file=sys.stderr)
        return 2

    existing = {
        (row.get("htc_group", ""), row.get("htc_family", ""), row.get("food_key", ""))
        for row in rows
    }
    used_slots = {
        row.get("food_slot", "")
        for row in rows
        if row.get("htc_group") == "1" and row.get("htc_family") == "1" and row.get("food_slot")
    }
    next_index = max(slot_to_index(slot) for slot in used_slots if len(slot) == 2) + 1
    counts = evidence_counts(args.audit, args.items)

    added: list[dict[str, str]] = []
    for name in cheese_registry_names():
        key = normalize_key(name)
        if ("1", "1", key) in existing:
            continue
        while slot_for_index(next_index) in used_slots:
            next_index += 1
        slot = slot_for_index(next_index)
        next_index += 1
        used_slots.add(slot)
        existing.add(("1", "1", key))
        row = {
            "htc_group": "1",
            "htc_family": "1",
            "food_key": key,
            "food_name": name,
            "food_slot": slot,
            "row_count": str(max(1, counts.get(name, 0))),
            "canonical_path": f"Dairy > Cheese > {name}",
            "product_identity_fixed": name,
            "primary_modifier": "",
            "rule": "A",
            "source_htc_family": "1",
            "subdivision": "cheese_identity_overlay",
        }
        rows.append(row)
        added.append(row)

    with args.registry.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"registry rows: {len(rows):,}")
    print(f"added cheese identity slots: {len(added):,}")
    for row in added[:80]:
        print(f"  {row['food_slot']} {row['food_name']} rows={row['row_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
