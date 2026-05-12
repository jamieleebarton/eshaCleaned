#!/usr/bin/env python3
"""Build the deterministic HTC food-slot registry.

The registry activates positions 3-4 of the 8-char HTC code.  It is built
from the curated retail audit, not from runtime encounters, so code assignment
is reproducible:

    (htc_group, htc_family, food_key) -> 2-char Crockford food_slot

The emitted HTC join code neutralizes form/processing/ptype; those are facets,
not the identity key.  For generic Rule B products (Entree, Seasoning, Soup,
Pizza, etc.), the primary modifier is promoted into the food name so
`Entree Chicken Alfredo` and `Entree Beef Teriyaki` do not collapse.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
V1 = HERE.parent
REPO = V1.parent.parent
V2 = REPO / "retail_mapper" / "v2"

sys.path.insert(0, str(V1))

from htc.encoder import FAMILY_RULES, family_from_identity, group_from_canonical_path  # noqa: E402
from htc.food_slots import (  # noqa: E402
    CROCKFORD,
    RESERVED_SLOT,
    effective_food_name,
    is_rule_b,
    normalize_key,
    primary_modifier,
)

DEFAULT_AUDIT = V2 / "consensus_full_corpus_audit.csv"
DEFAULT_REGISTRY = HERE / "food_slot_registry.csv"
DEFAULT_SUBDIVISIONS = HERE / "family_subdivisions.csv"
DEFAULT_REPORT = HERE / "food_slot_registry_report.json"

MAX_SLOTS = 32 * 32
OVERFLOW_THRESHOLD = 900


def slot_for_index(idx: int) -> str:
    if idx < 1 or idx >= MAX_SLOTS:
        raise ValueError(f"slot index {idx} out of range [1, {MAX_SLOTS - 1}]")
    return CROCKFORD[idx // 32] + CROCKFORD[idx % 32]


def fallback_group_family(food_name: str, canonical_path: str) -> tuple[str, str]:
    group = group_from_canonical_path(canonical_path, food_name)
    if not group:
        # Last-resort family scan for odd rows under generic paths.
        for candidate_group, rules in FAMILY_RULES.items():
            for pattern, family_code in rules:
                if pattern.search(food_name):
                    return candidate_group, family_code
        return "0", "0"
    return group, family_from_identity(group, food_name, canonical_path)


def bucket_summary(bucket: tuple[str, str], ranked: list[tuple[str, int]]) -> dict[str, object]:
    return {
        "bucket": list(bucket),
        "distinct_foods": len(ranked),
        "total_rows": sum(count for _, count in ranked),
        "top_foods": [{"food_name": name, "rows": count} for name, count in ranked[:25]],
    }


def next_available_family(group: str, used_families: set[str]) -> str:
    for candidate in CROCKFORD:
        if candidate not in used_families:
            used_families.add(candidate)
            return candidate
    raise RuntimeError(f"no free HTC family slots left for group {group}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--subdivisions", type=Path, default=DEFAULT_SUBDIVISIONS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    csv.field_size_limit(sys.maxsize)
    if not args.audit.exists():
        print(f"missing audit: {args.audit}", file=sys.stderr)
        return 2

    # (group, family) -> effective food name -> row count
    buckets: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    examples: dict[tuple[str, str, str], dict[str, str]] = {}
    rows_scanned = 0
    blank_identity_rows = 0

    with args.audit.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            rows_scanned += 1
            canonical_path = (row.get("canonical_path") or "").strip()
            pid = (row.get("product_identity_fixed") or "").strip()
            modifier = (row.get("modifier") or "").strip()
            if not pid:
                blank_identity_rows += 1
                continue
            # Use flavor when present, otherwise fall back to variant.
            # FDC retail occasionally stores the discriminator token
            # (sharp_cheddar, chocolate_fudge, butterscotch) in variant.
            flavor_or_variant = row.get("flavor", "") or row.get("variant", "")
            food_name = effective_food_name(
                canonical_path,
                pid,
                modifier,
                " || ".join(
                    row.get(field, "") or ""
                    for field in ("title", "canonical_label", "retail_leaf_path", "fndds_desc", "sr28_desc")
                ),
                flavor=flavor_or_variant,
            )
            food_key = normalize_key(food_name)
            if not food_key:
                blank_identity_rows += 1
                continue
            group, family = fallback_group_family(food_name, canonical_path)
            key = (group, family)
            buckets[key][food_name] += 1
            examples.setdefault(
                (group, family, food_name),
                {
                    "canonical_path": canonical_path,
                    "product_identity_fixed": pid,
                    "primary_modifier": primary_modifier(modifier),
                    "rule": "B" if is_rule_b(canonical_path, pid) else "A",
                },
            )

    # Split genuinely high-cardinality families into deterministic spare
    # family slots.  The registry remains the source of truth, so the encoder
    # can promote a looked-up food into its assigned overflow family.
    used_families_by_group: dict[str, set[str]] = defaultdict(set)
    for group, family in buckets:
        used_families_by_group[group].add(family)

    assigned_buckets: dict[
        tuple[str, str],
        list[tuple[str, int, tuple[str, str], int]],
    ] = defaultdict(list)
    pre_subdivision_overflow: list[dict[str, object]] = []
    subdivision_rows: list[dict[str, str | int]] = []

    for bucket in sorted(buckets):
        group, family = bucket
        foods = buckets[bucket]
        ranked = sorted(foods.items(), key=lambda kv: (-kv[1], normalize_key(kv[0]), kv[0]))
        if len(ranked) <= OVERFLOW_THRESHOLD:
            for food_name, count in ranked:
                assigned_buckets[bucket].append((food_name, count, bucket, 0))
            continue

        pre_subdivision_overflow.append(bucket_summary(bucket, ranked))
        for chunk_index, start in enumerate(range(0, len(ranked), OVERFLOW_THRESHOLD)):
            chunk = ranked[start:start + OVERFLOW_THRESHOLD]
            target_family = family if chunk_index == 0 else next_available_family(
                group,
                used_families_by_group[group],
            )
            for food_name, count in chunk:
                assigned_buckets[(group, target_family)].append((food_name, count, bucket, chunk_index))
            subdivision_rows.append({
                "parent_group": group,
                "parent_family": family,
                "sub_family_code": target_family,
                "sub_family_name": f"{group}{family} rank chunk {chunk_index + 1}",
                "canonical_path_pattern": "*",
                "rank_start": start + 1,
                "rank_end": start + len(chunk),
                "distinct_foods": len(chunk),
                "total_rows": sum(count for _, count in chunk),
                "reason": "overflow_subdivision",
            })

    registry_rows: list[dict[str, str | int]] = []
    overflow: list[dict[str, object]] = []
    largest_buckets: list[dict[str, object]] = []

    for bucket in sorted(assigned_buckets):
        ranked_items = sorted(
            assigned_buckets[bucket],
            key=lambda item: (-item[1], normalize_key(item[0]), item[0]),
        )
        if len(ranked_items) > OVERFLOW_THRESHOLD:
            overflow.append(bucket_summary(bucket, [(name, count) for name, count, _, _ in ranked_items]))
        for idx, (food_name, count, source_bucket, chunk_index) in enumerate(ranked_items, start=1):
            if idx >= MAX_SLOTS:
                continue
            group, family = bucket
            source_group, source_family = source_bucket
            ex = examples[(source_group, source_family, food_name)]
            registry_rows.append({
                "htc_group": group,
                "htc_family": family,
                "food_key": normalize_key(food_name),
                "food_name": food_name,
                "food_slot": slot_for_index(idx),
                "row_count": count,
                "canonical_path": ex["canonical_path"],
                "product_identity_fixed": ex["product_identity_fixed"],
                "primary_modifier": ex["primary_modifier"],
                "rule": ex["rule"],
                "source_htc_family": source_family,
                "subdivision": "source" if chunk_index == 0 else "overflow",
            })
        largest_buckets.append({
            "bucket": list(bucket),
            "distinct_foods": len(ranked_items),
            "total_rows": sum(count for _, count, _, _ in ranked_items),
        })

    largest_buckets.sort(key=lambda item: (-int(item["distinct_foods"]), -int(item["total_rows"])))

    args.registry.parent.mkdir(parents=True, exist_ok=True)
    with args.registry.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "htc_group", "htc_family", "food_key", "food_name", "food_slot",
            "row_count", "canonical_path", "product_identity_fixed",
            "primary_modifier", "rule", "source_htc_family", "subdivision",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(registry_rows)

    with args.subdivisions.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "parent_group", "parent_family", "sub_family_code", "sub_family_name",
            "canonical_path_pattern", "rank_start", "rank_end", "distinct_foods",
            "total_rows", "reason",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(subdivision_rows)

    report = {
        "rows_scanned": rows_scanned,
        "blank_identity_rows": blank_identity_rows,
        "source_bucket_count": len(buckets),
        "assigned_bucket_count": len(assigned_buckets),
        "registry_entries": len(registry_rows),
        "max_slots": MAX_SLOTS,
        "reserved_slot": RESERVED_SLOT,
        "overflow_threshold": OVERFLOW_THRESHOLD,
        "pre_subdivision_overflow_buckets": pre_subdivision_overflow,
        "subdivision_count": len(subdivision_rows),
        "subdivisions": subdivision_rows,
        "overflow_buckets": overflow,
        "largest_buckets_by_distinct_foods": largest_buckets[:40],
        "outputs": {
            "registry": str(args.registry),
            "subdivisions": str(args.subdivisions),
            "report": str(args.report),
        },
    }
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({
        "rows_scanned": rows_scanned,
        "registry_entries": len(registry_rows),
        "source_bucket_count": len(buckets),
        "assigned_bucket_count": len(assigned_buckets),
        "subdivision_count": len(subdivision_rows),
        "overflow_buckets": len(overflow),
        "registry": str(args.registry),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
