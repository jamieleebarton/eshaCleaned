#!/usr/bin/env python3
"""Fail a plan JSON if actual cart purchases contain known bad SKU classes.

This scans weeks[*].ingredient_purchases[*], not simulated recipe audit rows.
It is intentionally conservative for contextual failures: a jarred jalapeno is
bad for a fresh-jalapeno concept but can be valid for a pickled-jalapeno concept.

Usage:
  python3 recipe_pricing/verify_plan_bad_skus.py /tmp/plan.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "recipe_pricing" / "plan_bad_sku_hits.csv"

GLOBAL_BANNED_TERMS = [
    "mozzarella blend",
    "smart balance",
    "strawberry applesauce",
    "fat-free mozzarella",
    "revlon",
    "lip oil",
    "vitamin e oil",
    "canned chicken",
    "breyers",
    "nature's song",
    "natures song",
    "bird food",
    "bird seed",
    "wild bird",
    "bird suet",
    "burpee",
    "ceramic",
    "mug",
    "sauce pan",
    "drink pouch",
    "icee slush",
]

CONCEPT_BANNED_TERMS = [
    {
        "concept_re": r"^produce > vegetables > jalapenos\b",
        "terms": ["pickled", "jarred", "sliced jalapeno", "la costena", "costena"],
        "reason": "fresh_jalapeno_picked_preserved_or_jarred",
    },
    {
        "concept_re": r"chicken breast",
        "terms": ["canned", "starkist", "chunk chicken", "pouch", "chicken salad",
                  "deli", "lunchmeat", "lunch meat"],
        "reason": "raw_chicken_breast_picked_canned_or_deli",
    },
    {
        "concept_re": r"pantry > oil",
        "terms": ["smart balance", "margarine", "spread"],
        "reason": "oil_concept_picked_spread_or_margarine",
    },
    {
        "concept_re": r"mozzarella",
        "terms": ["mozzarella blend", "fat-free mozzarella"],
        "reason": "plain_mozzarella_picked_wrong_mozzarella_form",
    },
]


def norm(text: str | None) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_term(haystack: str, term: str) -> bool:
    needle = norm(term)
    if not needle:
        return False
    return f" {needle} " in f" {haystack} "


def iter_purchases(plan: dict):
    for week in plan.get("weeks", []) or []:
        week_no = week.get("week", "")
        for idx, purchase in enumerate(week.get("ingredient_purchases", []) or [], start=1):
            yield week_no, idx, purchase


def find_hits(plan: dict) -> list[dict]:
    hits: list[dict] = []
    for week_no, idx, purchase in iter_purchases(plan):
        sku = purchase.get("selected_sku", "") or ""
        sku_norm = norm(sku)
        concept = purchase.get("concept_key", "") or ""
        concept_norm = norm(concept)

        for term in GLOBAL_BANNED_TERMS:
            if contains_term(sku_norm, term):
                hits.append({
                    "week": week_no,
                    "purchase_index": idx,
                    "concept_key": concept,
                    "selected_sku": sku,
                    "term": term,
                    "reason": "global_banned_term",
                })

        for rule in CONCEPT_BANNED_TERMS:
            if not re.search(rule["concept_re"], concept_norm):
                continue
            for term in rule["terms"]:
                if contains_term(sku_norm, term):
                    hits.append({
                        "week": week_no,
                        "purchase_index": idx,
                        "concept_key": concept,
                        "selected_sku": sku,
                        "term": term,
                        "reason": rule["reason"],
                    })

    return hits


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan_json", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    plan = json.loads(args.plan_json.read_text())
    hits = find_hits(plan)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if hits:
        with args.out.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(hits[0].keys()))
            writer.writeheader()
            writer.writerows(hits)
    elif args.out.exists():
        args.out.unlink()

    print(f"plan: {args.plan_json}", file=sys.stderr)
    print(f"purchase rows scanned: {sum(1 for _ in iter_purchases(plan)):,}", file=sys.stderr)
    print(f"bad SKU hits: {len(hits):,}", file=sys.stderr)
    if hits:
        print(f"hits written to: {args.out}", file=sys.stderr)
        for hit in hits[:20]:
            print(
                f"  week {hit['week']} {hit['term']} -> "
                f"{hit['selected_sku'][:80]} [{hit['concept_key']}]",
                file=sys.stderr,
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
