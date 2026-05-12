#!/usr/bin/env python3
"""Audit v7 calculator coverage over the recipe corpus.

The full recipe file has tens of thousands of unique ingredient surfaces. This
script scores the most frequent surfaces exactly enough to give a meaningful
coverage bound without using the slow nested scan from calculate_recipe_cost_v6.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from calculate_recipe_cost_v6 import (  # noqa: E402
    CONSENSUS_AUDIT,
    LINES,
    PRICED_DB,
    RULE_B_PIDS,
    WS,
    primary_noun,
    toks,
)
from calculate_recipe_cost_v7 import (  # noqa: E402
    EVIDENCE_CSV,
    is_tap_water_item,
    load_priced_products,
    product_concept,
    recipe_product_allowed,
)

HERE = Path(__file__).resolve().parent
OUT_SUMMARY = HERE / "output" / "recipe_cost_v7_coverage_summary.json"
OUT_GAPS = HERE / "output" / "recipe_cost_v7_coverage_gaps.csv"

PROCESS_WORDS = {
    "pickled", "smoked", "scrambled", "fried", "candied", "glazed",
    "stuffed", "breaded", "battered", "marinated", "cured", "deviled",
    "salted", "fermented", "instant",
}
FORM_QUALIFIERS = {
    "seeds", "seed", "leaves", "leaf", "sprig", "sprigs", "bunch",
    "bunches", "threads", "thread", "flakes", "flake", "strips",
    "sticks", "stick", "pieces", "halves", "wedges", "slices", "slice",
    "cubes", "cube", "rounds", "round", "grains",
}


def norm_word(value: str) -> str:
    if value.endswith("ies") and len(value) > 4:
        return value[:-3] + "y"
    if value.endswith("es") and len(value) > 3 and value[-3] in "sxz":
        return value[:-2]
    if value.endswith("s") and len(value) > 2 and not value.endswith("ss"):
        return value[:-1]
    return value


def norm_phrase(value: str) -> str:
    return " ".join(norm_word(part) for part in WS.sub(" ", (value or "").lower()).split())


def count_items(lines_path: Path) -> tuple[Counter[str], int, int]:
    counts: Counter[str] = Counter()
    total = 0
    positive_grams = 0
    with lines_path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            item = (row.get("ingredient_item") or "").strip().lower()
            if not item:
                continue
            total += 1
            try:
                grams = float(row.get("grams_resolved") or 0)
            except ValueError:
                grams = 0.0
            if grams > 0:
                positive_grams += 1
            counts[item] += 1
    return counts, total, positive_grams


def build_fast_concepts(items: set[str], audit_path: Path) -> dict[str, dict[str, object]]:
    info: dict[str, dict[str, object]] = {
        item: {
            "primary": primary_noun(item),
            "item_tokens": toks(item),
            "p1": set(),
            "p2": set(),
            "p3": set(),
        }
        for item in items
    }

    items_by_norm: dict[str, set[str]] = defaultdict(set)
    items_by_primary: dict[str, set[str]] = defaultdict(set)
    for item, value in info.items():
        items_by_norm[item].add(item)
        items_by_norm[norm_phrase(item)].add(item)
        primary = str(value["primary"] or "")
        if primary:
            items_by_primary[primary].add(item)
            items_by_primary[norm_word(primary)].add(item)
    item_token_index: dict[str, set[str]] = defaultdict(set)
    for item, value in info.items():
        for token in value["item_tokens"]:  # type: ignore[union-attr]
            item_token_index[token].add(item)

    with audit_path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            pid = (row.get("product_identity_fixed") or "").strip()
            canonical = (row.get("canonical_path") or "").strip()
            if not pid or not canonical:
                continue

            modifier = (row.get("modifier") or "").strip().split(" > ")[0].strip()
            concept = (canonical, modifier.lower()) if pid in RULE_B_PIDS else (canonical, "")
            pid_lc = pid.lower()
            pid_norm = norm_phrase(pid_lc)
            pid_tokens_list = [
                token for token in WS.sub(" ", pid_lc).split()
                if len(token) >= 2 and token not in {
                    "the", "of", "and", "with", "a", "an", "to", "in",
                    "fresh", "frozen", "raw", "ground", "whole", "large",
                    "medium", "small", "extra", "lean", "low", "fat",
                    "free", "organic", "natural", "chopped", "diced",
                    "minced", "sliced", "boneless", "skinless", "grade",
                    "brand",
                }
            ]
            pid_tokens = set(pid_tokens_list)
            pid_last = pid_tokens_list[-1] if pid_tokens_list else ""
            pid_last_norm = norm_word(pid_last)

            for item in items_by_norm.get(pid_lc, set()) | items_by_norm.get(pid_norm, set()):
                info[item]["p1"].add(concept)  # type: ignore[union-attr]

            p2_candidate_items = items_by_primary.get(pid_last, set()) | items_by_primary.get(pid_last_norm, set())
            if p2_candidate_items:
                for item in p2_candidate_items:
                    value = info[item]
                    primary = str(value["primary"])
                    item_tokens = value["item_tokens"]  # type: ignore[assignment]
                    if (
                        item_tokens.issubset(pid_tokens | {primary})
                        and not (pid_tokens - item_tokens) & PROCESS_WORDS
                    ):
                        value["p2"].add(concept)  # type: ignore[union-attr]

            if pid in RULE_B_PIDS and modifier:
                mod_lc = modifier.lower()
                mod_tokens = toks(mod_lc)
                candidate_items = {mod_lc} if mod_lc in info else set()
                for token in mod_tokens:
                    candidate_items.update(item_token_index.get(token, set()))
                for item in candidate_items:
                    value = info[item]
                    item_tokens = value["item_tokens"]  # type: ignore[assignment]
                    if mod_lc == item:
                        value["p3"].add(concept)  # type: ignore[union-attr]
                    elif mod_tokens and mod_tokens.issubset(item_tokens):
                        leftover = item_tokens - mod_tokens
                        if not leftover or leftover.issubset(FORM_QUALIFIERS):
                            value["p3"].add(concept)  # type: ignore[union-attr]

    out: dict[str, dict[str, object]] = {}
    for item, value in info.items():
        concepts = value["p1"] or value["p2"] or value["p3"]
        out[item] = {"concepts": concepts, "primary": value["primary"]}
    return out


def product_index(products: list[dict]) -> dict[tuple[str, str], list[dict]]:
    by_concept: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for product in products:
        by_concept[product_concept(product)].append(product)
    return by_concept


def pct(part: int | float, whole: int | float) -> float:
    return round((float(part) / float(whole) * 100.0), 2) if whole else 0.0


def audit(args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]]]:
    t0 = time.time()
    item_counts, total_lines, positive_grams_lines = count_items(args.lines)
    top_items = {item for item, _ in item_counts.most_common(args.top_n)}
    top_line_count = sum(item_counts[item] for item in top_items)

    concepts = build_fast_concepts(top_items, args.audit)
    priced_products = load_priced_products(args.priced_db, args.evidence)
    by_product_concept = product_index(priced_products)

    status_counts: Counter[str] = Counter()
    gap_counts: Counter[tuple[str, str]] = Counter()
    safe_lines = 0
    safe_positive_grams_lines = 0
    top_scored_lines = 0
    decision_cache: dict[tuple[str, str, str, str, str], str] = {}

    with args.lines.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            item = (row.get("ingredient_item") or "").strip().lower()
            if not item:
                continue
            if item not in top_items:
                status_counts["tail_not_scored"] += 1
                continue
            top_scored_lines += 1
            try:
                grams = float(row.get("grams_resolved") or 0)
            except ValueError:
                grams = 0.0

            cache_key = (
                item,
                row.get("display") or "",
                row.get("facet_form") or "",
                row.get("facet_processing") or "",
                row.get("facet_modifier") or "",
            )
            status = decision_cache.get(cache_key)
            if status is None:
                if is_tap_water_item(item):
                    status = "safe_tap_water"
                else:
                    item_info = concepts.get(item) or {"concepts": set()}
                    item_concepts = item_info.get("concepts") or set()
                    if not item_concepts:
                        status = "gap_no_tree_concept"
                    else:
                        found = False
                        for concept in item_concepts:
                            for product in by_product_concept.get(concept, []):
                                if recipe_product_allowed(item, row, product):
                                    found = True
                                    break
                            if found:
                                break
                        status = "safe_priced" if found else "gap_no_safe_product"
                decision_cache[cache_key] = status

            if status in {"safe_tap_water", "safe_priced"}:
                safe_lines += 1
                if grams > 0:
                    safe_positive_grams_lines += 1
            status_counts[status] += 1
            if status.startswith("gap_"):
                gap_counts[(item, status)] += 1

    gaps = [
        {"ingredient_item": item, "reason": reason, "line_count": count}
        for (item, reason), count in gap_counts.most_common(args.gap_limit)
    ]
    summary = {
        "top_n_items_scored": args.top_n,
        "elapsed_s": round(time.time() - t0, 1),
        "total_recipe_lines": total_lines,
        "positive_grams_lines": positive_grams_lines,
        "unique_ingredient_items": len(item_counts),
        "top_n_line_count": top_line_count,
        "top_n_line_pct_of_corpus": pct(top_line_count, total_lines),
        "safe_lines_in_scored_head": safe_lines,
        "safe_line_pct_of_scored_head": pct(safe_lines, top_scored_lines),
        "safe_line_lower_bound_pct_of_full_corpus": pct(safe_lines, total_lines),
        "safe_positive_grams_lines_in_scored_head": safe_positive_grams_lines,
        "safe_positive_grams_line_pct_of_scored_head": pct(safe_positive_grams_lines, top_scored_lines),
        "status_counts": dict(status_counts.most_common()),
        "approved_priced_products_loaded": len(priced_products),
        "line_decision_cache_entries": len(decision_cache),
    }
    return summary, gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lines", type=Path, default=LINES)
    parser.add_argument("--audit", type=Path, default=CONSENSUS_AUDIT)
    parser.add_argument("--priced-db", type=Path, default=PRICED_DB)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE_CSV)
    parser.add_argument("--top-n", type=int, default=2500)
    parser.add_argument("--summary-out", type=Path, default=OUT_SUMMARY)
    parser.add_argument("--gaps-out", type=Path, default=OUT_GAPS)
    parser.add_argument("--gap-limit", type=int, default=200)
    args = parser.parse_args()

    summary, gaps = audit(args)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    with args.gaps_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ingredient_item", "reason", "line_count"])
        writer.writeheader()
        writer.writerows(gaps)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"wrote {args.summary_out}")
    print(f"wrote {args.gaps_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
