#!/usr/bin/env python3
"""Audit v8 recipe pricing coverage with resolver/equivalence layers.

This is intentionally an audit, not a silent calculator change. It measures
coverage after adding the PricingConceptResolver and safe product-concept
equivalences on top of the v7 adjudicated evidence layer.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_recipe_cost_v7_coverage import (  # noqa: E402
    build_fast_concepts,
    count_items,
    pct,
)
from calculate_recipe_cost_v6 import CONSENSUS_AUDIT, LINES, PRICED_DB  # noqa: E402
from calculate_recipe_cost_v7 import (  # noqa: E402
    APPROVED_TAXONOMY_STATUSES,
    EVIDENCE_CSV,
    is_tap_water_item,
    load_priced_products,
    product_concept,
    recipe_product_allowed,
)
from pricing_concept_resolver import (  # noqa: E402
    PricingConceptResolver,
    product_passes_gate,
)

HERE = Path(__file__).resolve().parent
OUT_SUMMARY = HERE / "output" / "recipe_cost_v8_coverage_summary.json"
OUT_GAPS = HERE / "output" / "recipe_cost_v8_coverage_gaps.csv"
RESCUE_STATUSES = {"quarantine_identity", "quarantine_low_score", "quarantine_close_runner"}
RESCUE_MIN_SCORE = 30.0


def load_rescue_products(db_path: Path, evidence_path: Path) -> list[dict]:
    """Load strict rescue candidates from non-approved evidence rows.

    These rows are not accepted by themselves. decide_line only uses them when
    the resolver returned a non-empty ProductGate and that gate passes the
    product title/category. This keeps the rescue layer deterministic and
    reviewable instead of lowering v7 thresholds globally.
    """
    evidence: dict[int, dict[str, str]] = {}
    with evidence_path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            status = row.get("taxonomy_status") or ""
            if status in APPROVED_TAXONOMY_STATUSES or status not in RESCUE_STATUSES:
                continue
            if (row.get("hard_vetoes") or "").strip():
                continue
            if not row.get("proposed_canonical"):
                continue
            try:
                score = float(row.get("total_score") or 0)
                rowid = int(row.get("rowid") or 0)
            except ValueError:
                continue
            if not rowid or score < RESCUE_MIN_SCORE:
                continue
            evidence[rowid] = row

    if not evidence:
        return []

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    rowids = sorted(evidence)
    out: list[dict] = []
    for i in range(0, len(rowids), 900):
        chunk = rowids[i:i + 900]
        marks = ",".join("?" for _ in chunk)
        sql = f"""
            SELECT rowid, source, upc, name, brand, grams, cents,
                   htc_code, htc_group, category_path, category_path_walmart
            FROM priced_products
            WHERE rowid IN ({marks})
              AND marketplace = 0 AND available = 1
              AND grams > 0 AND cents > 0
        """
        for row in con.execute(sql, chunk):
            ev = evidence[int(row["rowid"])]
            modifier = (ev.get("proposed_modifier") or "").split(" > ")[0].strip()
            out.append({
                "rowid": int(row["rowid"]),
                "source": row["source"] or "",
                "upc": row["upc"] or f"rowid:{row['rowid']}",
                "name": row["name"] or "",
                "brand": row["brand"] or "",
                "grams": float(row["grams"]),
                "cents": int(row["cents"]),
                "cpg": int(row["cents"]) / float(row["grams"]),
                "htc": row["htc_code"] or "",
                "htc_group": row["htc_group"] or "",
                "category_path": row["category_path"] or "",
                "category_path_walmart": row["category_path_walmart"] or "",
                "pid": ev.get("proposed_pid") or "",
                "canonical": ev.get("proposed_canonical") or "",
                "modifier": modifier,
                "taxonomy_status": ev.get("taxonomy_status") or "",
                "nutrition_status": ev.get("nutrition_status") or "",
                "evidence_score": float(ev.get("total_score") or 0),
                "offer_layer": "rescue_candidate",
            })
    return out


def product_index(products: list[dict]) -> dict[tuple[str, str], list[dict]]:
    by_concept: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for product in products:
        by_concept[product_concept(product)].append(product)
    return by_concept


def concept_label(concept: tuple[str, str]) -> str:
    canonical, modifier = concept
    return f"{canonical} [{modifier}]" if modifier else canonical


def decide_line(
    item: str,
    row: dict,
    resolver: PricingConceptResolver,
    fast_concepts: dict[str, dict[str, object]],
    by_product_concept: dict[tuple[str, str], list[dict]],
) -> tuple[str, str, str]:
    if is_tap_water_item(item):
        return "safe_tap_water", "tap_water", ""

    fallback = (fast_concepts.get(item) or {}).get("concepts") or set()
    resolved = resolver.resolve(item, fallback_concepts=fallback)  # type: ignore[arg-type]
    if not resolved.concepts:
        if resolved.nutrition_anchor:
            return "gap_no_shopping_concept", resolved.source, resolved.nutrition_anchor
        return "gap_no_tree_concept", resolved.source, ""

    match_concepts = resolved.match_concepts(include_equivalents=True)
    any_offer = False
    any_missing_gate_skipped = False
    any_recipe_allowed = False
    any_gate_allowed = False
    for concept in match_concepts:
        products = by_product_concept.get(concept, [])
        if products:
            any_offer = True
        for product in products:
            if product.get("offer_layer") == "rescue_candidate" and not any((
                resolved.product_gate.required_all,
                resolved.product_gate.required_any,
                resolved.product_gate.forbidden,
                resolved.product_gate.required_path_any,
                resolved.product_gate.forbidden_path,
            )):
                any_missing_gate_skipped = True
                continue
            if not recipe_product_allowed(item, row, product):
                continue
            any_recipe_allowed = True
            if not product_passes_gate(resolved, product):
                continue
            any_gate_allowed = True
            layer = "resolver" if resolved.source != "legacy_fast_concepts" else "v7_evidence"
            if concept not in resolved.concepts:
                layer = f"{layer}+safe_equivalence"
            if product.get("offer_layer") == "rescue_candidate":
                layer = f"{layer}+rescue_offer"
            return "safe_priced", layer, concept_label(concept)

    if not any_offer:
        return "gap_no_safe_offer", resolved.source, "|".join(concept_label(c) for c in sorted(match_concepts))
    if any_missing_gate_skipped and not any_recipe_allowed:
        return "gap_blocked_by_missing_product_gate", resolved.source, "|".join(concept_label(c) for c in sorted(match_concepts))
    if not any_recipe_allowed:
        return "gap_blocked_by_recipe_gate", resolved.source, "|".join(concept_label(c) for c in sorted(match_concepts))
    if not any_gate_allowed:
        return "gap_blocked_by_product_gate", resolved.source, "|".join(concept_label(c) for c in sorted(match_concepts))
    return "gap_no_safe_offer", resolved.source, "|".join(concept_label(c) for c in sorted(match_concepts))


def audit(args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]]]:
    t0 = time.time()
    item_counts, total_lines, positive_grams_lines = count_items(args.lines)
    top_items = {item for item, _ in item_counts.most_common(args.top_n)}
    top_line_count = sum(item_counts[item] for item in top_items)

    fast_concepts = build_fast_concepts(top_items, args.audit)
    resolver = PricingConceptResolver()
    approved_products = load_priced_products(args.priced_db, args.evidence)
    rescue_products = load_rescue_products(args.priced_db, args.evidence) if args.rescue_evidence else []
    priced_products = approved_products + rescue_products
    by_product_concept = product_index(priced_products)

    status_counts: Counter[str] = Counter()
    layer_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    gap_counts: Counter[tuple[str, str, str, str]] = Counter()
    safe_lines = 0
    safe_positive_grams_lines = 0
    top_scored_lines = 0
    decision_cache: dict[tuple[str, str, str, str, str], tuple[str, str, str]] = {}

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
            decision = decision_cache.get(cache_key)
            if decision is None:
                decision = decide_line(item, row, resolver, fast_concepts, by_product_concept)
                decision_cache[cache_key] = decision
            status, layer_or_source, detail = decision

            if status in {"safe_tap_water", "safe_priced"}:
                safe_lines += 1
                if grams > 0:
                    safe_positive_grams_lines += 1
                layer_counts[layer_or_source] += 1
            elif status.startswith("gap_"):
                gap_counts[(item, status, layer_or_source, detail)] += 1
                source_counts[layer_or_source] += 1
            status_counts[status] += 1

    gaps = [
        {
            "ingredient_item": item,
            "reason": reason,
            "resolver_source": source,
            "detail": detail,
            "line_count": count,
        }
        for (item, reason, source, detail), count in gap_counts.most_common(args.gap_limit)
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
        "safe_layer_counts": dict(layer_counts.most_common()),
        "gap_resolver_source_counts": dict(source_counts.most_common()),
        "approved_priced_products_loaded": len(approved_products),
        "rescue_candidate_products_loaded": len(rescue_products),
        "priced_products_loaded_total": len(priced_products),
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
    parser.add_argument("--gap-limit", type=int, default=300)
    parser.add_argument("--no-rescue-evidence", dest="rescue_evidence", action="store_false")
    parser.set_defaults(rescue_evidence=True)
    args = parser.parse_args()

    summary, gaps = audit(args)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    with args.gaps_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ingredient_item", "reason", "resolver_source", "detail", "line_count"],
        )
        writer.writeheader()
        writer.writerows(gaps)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"wrote {args.summary_out}")
    print(f"wrote {args.gaps_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
