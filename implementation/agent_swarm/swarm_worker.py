"""
Swarm worker — analyze a batch of branded_food_categories and produce a
misassignment report.

Usage:
    python3 swarm_worker.py "Candy" "Cheese" "Ice Cream & Frozen Yogurt"
"""

from __future__ import annotations

import csv
import sys
import json
import re
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
PRODUCT_MAP = ROOT / "implementation/output/product_to_best_esha_full_map.vIdentity.csv"
CANONICAL_SURFACE = ROOT / "implementation/output/canonical_surface_normalized_with_product_proxies_CLEANED.csv"
REPORTS_DIR = ROOT / "implementation/agent_swarm/reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

WORD = re.compile(r"[a-z][a-z0-9'%-]*")

def tokens(s: str) -> list[str]:
    return WORD.findall(s.lower())


def load_esha_index() -> tuple[dict[str, set[str]], dict[str, str]]:
    """Load the BEST (shortest) ESHA description per code and tokenize it.
    Do NOT union tokens across multiple descriptions for the same code —
    that creates false supersets (e.g. code 16858 has both 'baking chocolate'
    and 'bar, chocolate', so its union falsely appears as a superset of
    'baking chocolate, bittersweet, chunks').
    """
    desc_idx: dict[str, str] = {}
    with open(CANONICAL_SURFACE, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            code = r.get("esha_code", "").strip()
            desc = r.get("esha_description", "").strip()
            if code and desc:
                # Keep the shortest description as the canonical one
                if code not in desc_idx or len(desc) < len(desc_idx[code]):
                    desc_idx[code] = desc

    # Tokenize only the canonical (shortest) description per code
    idx: dict[str, set[str]] = {}
    for code, desc in desc_idx.items():
        idx[code] = set(tokens(desc))
    return idx, desc_idx


def load_category_products(category: str) -> list[dict]:
    products = []
    with open(PRODUCT_MAP, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            if r.get("branded_food_category", "").strip() == category:
                products.append(r)
    return products


def analyze_category(category: str, esha_index: dict, esha_desc_index: dict) -> dict:
    products = load_category_products(category)
    if not products:
        return {"category": category, "n_products": 0, "verdict_distribution": {},
                "reason_distribution": {}, "n_findings": 0, "findings": []}

    # Build reverse token index
    token_to_codes: dict[str, set[str]] = defaultdict(set)
    for code, toks in esha_index.items():
        for t in toks:
            token_to_codes[t].add(code)

    findings: list[dict] = []
    verdict_counts = Counter()
    reason_counts = Counter()

    for r in products:
        verdict_counts[r.get("rft_verdict", "")] += 1
        reason_counts[r.get("best_esha_change_reason", "")] += 1

    for r in products:
        desc = r.get("product_description", "").strip()
        if not desc:
            continue

        current_code = r.get("best_esha_code", "").strip()
        current_desc = r.get("best_esha_description", "").strip()
        current_reason = r.get("best_esha_change_reason", "").strip()
        verdict = r.get("rft_verdict", "").strip()

        # Skip if already exact or strong with good reason
        if current_reason.startswith("replaced_exact") or current_reason.startswith("filled_exact"):
            continue
        if current_reason.startswith("kept_agree_exact"):
            continue

        prod_toks = set(tokens(desc))
        if not prod_toks:
            continue

        # Score all ESHA codes by Jaccard-ish overlap
        code_scores: Counter = Counter()
        for t in prod_toks:
            for code in token_to_codes.get(t, []):
                code_scores[code] += 1

        if not code_scores:
            continue

        ranked = []
        # Use the product map's own description for current tokens when
        # available — it reflects the actual assignment better than the
        # canonical surface's shortest description (which can be a generic
        # stub like "chips" or "taco" for a multi-desc code).
        current_toks = set(tokens(current_desc)) if current_desc else esha_index.get(current_code, set())
        for code, shared in code_scores.most_common(100):
            esha_toks = esha_index.get(code, set())
            if not esha_toks:
                continue
            # Coverage of product tokens
            cov = len(prod_toks & esha_toks) / max(1, len(prod_toks))
            if cov < 0.4:
                continue
            # Specificity: extra tokens in ESHA beyond product
            extra = len(esha_toks - prod_toks)
            # Is this a strict superset of current assignment?
            is_superset = bool(current_toks) and current_toks < esha_toks
            ranked.append((code, cov, extra, shared, esha_toks, is_superset))

        if not ranked:
            continue

        # Sort: highest coverage, then superset, then fewest extras
        ranked.sort(key=lambda x: (-x[1], -int(x[5]), x[2], -x[3]))
        best_code, best_cov, best_extra, best_shared, best_toks, is_superset = ranked[0]

        if best_code == current_code:
            continue

        best_desc = esha_desc_index.get(best_code, "")
        current_desc_short = current_desc[:60] if current_desc else ""
        best_desc_short = best_desc[:60] if best_desc else ""

        # Strict upgrade filter — ONLY superset upgrades.
        # The proposed code's tokens must be a strict superset of the current
        # code's tokens, AND the extra tokens must appear in the product
        # description.  E.g.:
        #   product: "SWEETENED DRIED CRANBERRIES"
        #   current: {cranberries, dried}  -> "Cranberries, dried"
        #   proposed: {cranberries, dried, sweetened} -> "Cranberries, dried, sweetened"
        #   extra: {sweetened}  -> present in product  -> VALID
        #
        # Invalid example:
        #   product: "CLASSIC APPLESAUCE"
        #   current: {applesauce} -> "Applesauce"
        #   proposed: {applesauce, cinnamon} -> "applesauce, cinnamon"
        #   extra: {cinnamon} -> NOT in product -> INVALID

        extra_vs_current = best_toks - current_toks if current_toks else best_toks
        product_has_extras = extra_vs_current.issubset(prod_toks)

        if not (is_superset and best_cov >= 0.5 and product_has_extras):
            continue

        # Guard: the distinguishing tokens must be real food descriptors,
        # not generic marketing words.
        marketing_words = {"original", "naturally", "natural", "classic",
                           "premium", "select", "gourmet", "homestyle",
                           "traditional", "family", "favorite", "style",
                           "chunky", "smooth", "creamy", "crunchy"}
        real_extras = extra_vs_current - marketing_words
        if not real_extras:
            continue

        upgrade_type = "superset"

        findings.append({
            "gtin_upc": r.get("gtin_upc", ""),
            "fdc_id": r.get("fdc_id", ""),
            "product_description": desc,
            "current_code": current_code,
            "current_desc": current_desc_short,
            "current_reason": current_reason,
            "current_verdict": verdict,
            "proposed_code": best_code,
            "proposed_desc": best_desc_short,
            "coverage": round(best_cov, 3),
            "shared_tokens": "|".join(sorted(prod_toks & best_toks)),
            "missing_tokens": "|".join(sorted(prod_toks - best_toks)),
            "extra_tokens": "|".join(sorted(best_toks - prod_toks)),
            "upgrade_type": upgrade_type,
        })

    return {
        "category": category,
        "n_products": len(products),
        "verdict_distribution": dict(verdict_counts),
        "reason_distribution": dict(reason_counts),
        "n_findings": len(findings),
        "findings": findings,
    }


def main():
    categories = sys.argv[1:]
    if not categories:
        print("Usage: python3 swarm_worker.py <category1> [category2] ...")
        sys.exit(1)

    print(f"Loading ESHA index...")
    esha_index, esha_desc_index = load_esha_index()
    print(f"  {len(esha_index):,} ESHA codes")

    for category in categories:
        print(f"\nAnalyzing: {category}")
        result = analyze_category(category, esha_index, esha_desc_index)
        print(f"  {result['n_products']:,} products, {result['n_findings']} findings")

        safe_name = category.replace("/", "_").replace(" ", "_")
        out_path = REPORTS_DIR / f"{safe_name}.json"
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"  Report: {out_path}")


if __name__ == "__main__":
    main()
