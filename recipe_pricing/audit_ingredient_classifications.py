#!/usr/bin/env python3
"""Audit recipe ingredient classifications and propose fixes.

Scans recipe_ingredient_taxonomy_v2.csv for likely misroutes:
  - sibling_switch  : title contains a token that maps to a SIBLING FDC leaf under
                      the same top-level (e.g. "naan breads" at Bakery > Bread →
                      Bakery > Naan; "pillsbury crescent roll" at Bakery > Bread
                      → Bakery > Crescent Roll Dough)
  - deeper_leaf     : title carries a more specific identity that's a strict
                      descendant of the current path
  - unresolved      : htc_code is the all-zero unresolved sentinel
  - generic_at_parent: row landed at a top-level/depth-2 path (Pantry, Bakery >
                      Bread, Dairy > Cheese) and title implies something more
                      specific

Output: recipe_pricing/output/ingredient_classification_audit.csv
Sorted by recipe_count desc so high-impact rows surface first.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SRC = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
ING_TAX = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
ING_AUDIT = ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_full_audit.csv"
OUT = ROOT / "recipe_pricing" / "output" / "ingredient_classification_audit.csv"

UNRESOLVED_CODE = "~00000000"

# Tokens that describe form/cut/quality, not identity. Drop from candidate
# matching so "naan breads" matches Naan (not breads).
NOISE_TOKENS = {
    "the", "a", "an", "of", "and", "with", "in", "on", "for", "or", "to", "&",
    "fresh", "raw", "cooked", "frozen", "dried", "low", "high", "non", "no",
    "premium", "select", "original", "natural", "all", "extra", "pure",
    "bread", "breads", "type", "style", "kind", "variety", "regular",
    "whole", "half", "small", "medium", "large", "mini", "miniature",
}


def tokens_of(s: str) -> list[str]:
    if not s:
        return []
    return [t for t in re.split(r"[\s_/\-,()&]+", s.lower()) if t]


def _norm_token(t: str) -> str:
    return t.strip().lower()


def main() -> int:
    # 1. Build FDC index: each canonical_path with its leaf's content-token set.
    # Match rule: a candidate leaf is acceptable for a row IFF
    #   (a) candidate.content_tokens ⊆ title.content_tokens   (strict subset)
    #   (b) at least 1 content token in common (no empty matches)
    #   (c) the proposed path is under the same top-level group as current.
    # This kills the false-positive class where a single shared token
    # ("ground" or "diced") drags an unrelated leaf in.
    fdc_paths: set[str] = set()
    fdc_leaf_tokens: dict[str, frozenset[str]] = {}
    with AUDIT_SRC.open() as f:
        for row in csv.DictReader(f):
            cp = (row.get("canonical_path") or "").strip()
            if not cp:
                continue
            fdc_paths.add(cp)
            leaf = cp.split(" > ")[-1].lower()
            content = frozenset(t for t in tokens_of(leaf) if t not in NOISE_TOKENS)
            if content:
                fdc_leaf_tokens[cp] = content
    print(f"FDC paths: {len(fdc_paths):,}", file=sys.stderr)
    print(f"FDC leaves with content tokens: {len(fdc_leaf_tokens):,}", file=sys.stderr)

    # Index by top-level for fast filtering
    by_top_level: defaultdict[str, list[tuple[str, frozenset[str]]]] = defaultdict(list)
    for cp, toks in fdc_leaf_tokens.items():
        top = cp.split(" > ")[0]
        by_top_level[top].append((cp, toks))

    # 2. Pull recipe meta (recipe_count) for sorting
    recipe_meta: dict[str, dict] = {}
    if ING_AUDIT.exists():
        with ING_AUDIT.open() as f:
            for row in csv.DictReader(f):
                key = row.get("item", "").strip().lower()
                if key:
                    recipe_meta[key] = row

    # 3. Walk the recipe ingredient taxonomy
    flagged: list[dict] = []
    with ING_TAX.open() as f:
        for row in csv.DictReader(f):
            title = (row.get("title") or "").strip()
            cp = (row.get("canonical_path") or "").strip()
            htc = (row.get("htc_code") or "").strip()
            pid = (row.get("product_identity_fixed") or "").strip()
            if not title:
                continue
            meta = recipe_meta.get(title.lower(), {})
            recipe_count = int(meta.get("recipe_count", 0) or 0)

            # Reasons to flag
            reasons = []
            proposed_paths: list[tuple[str, str]] = []  # (proposed, evidence)

            # A. Unresolved
            if htc == UNRESOLVED_CODE:
                reasons.append("unresolved")

            # B. Find FDC leaf whose content tokens are a SUBSET of title's content tokens.
            # The most specific (max tokens matched) under same top-level wins.
            cp_top = cp.split(" > ")[0] if cp else ""
            title_content = frozenset(t for t in tokens_of(title) if t not in NOISE_TOKENS)
            current_leaf_content = fdc_leaf_tokens.get(cp, frozenset())

            best: tuple[str, frozenset[str], int] | None = None  # (path, tokens, depth)
            for cand_path, cand_toks in by_top_level.get(cp_top, []):
                if cand_path == cp:
                    continue
                # (a) candidate's content tokens must all appear in title (no
                #     hallucinated identity tokens)
                if not cand_toks.issubset(title_content):
                    continue
                # (b) candidate must be STRICTLY more specific than current leaf —
                #     a strict superset of the current leaf's content tokens.
                #     This prevents demoting "Parmesan" to "Cheese" or
                #     "Olive Oil" to "Oil".
                if not cand_toks > current_leaf_content:
                    continue
                cand_depth = cand_path.count(" > ") + 1
                key = (len(cand_toks), cand_depth)
                if best is None or key > (len(best[1]), best[2]):
                    best = (cand_path, cand_toks, cand_depth)

            if best:
                cand_path, cand_toks, cand_depth = best
                cur_depth = cp.count(" > ") + 1
                if cand_path.startswith(cp + " > "):
                    proposed_paths.append((cand_path, f"deeper_leaf:'{','.join(sorted(cand_toks))}'"))
                else:
                    proposed_paths.append((cand_path, f"sibling_switch:'{','.join(sorted(cand_toks))}'"))

            # C. Generic-at-parent: cp is depth ≤ 2 AND title has > 1 specific token
            depth = cp.count(" > ") + 1 if cp else 0
            if depth <= 2 and not proposed_paths and not reasons:
                if len(title_content) >= 2:
                    reasons.append("generic_at_parent_no_match")

            if proposed_paths:
                reasons.extend(p[1] for p in proposed_paths)

            if reasons:
                flagged.append({
                    "title": title,
                    "recipe_count": recipe_count,
                    "current_canonical_path": cp,
                    "current_htc_code": htc,
                    "current_product_identity_fixed": pid,
                    "proposed_canonical_path": proposed_paths[0][0] if proposed_paths else "",
                    "alt_proposed_canonical_path": proposed_paths[1][0] if len(proposed_paths) > 1 else "",
                    "reasons": " | ".join(reasons),
                    "decision": "",  # user fills: accept | reject | propose:<path>
                })

    flagged.sort(key=lambda r: -int(r["recipe_count"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "title", "recipe_count",
            "current_canonical_path", "current_htc_code", "current_product_identity_fixed",
            "proposed_canonical_path", "alt_proposed_canonical_path",
            "reasons", "decision",
        ])
        w.writeheader()
        w.writerows(flagged)

    # Summary
    from collections import Counter
    by_reason = Counter()
    for r in flagged:
        for reason in r["reasons"].split(" | "):
            by_reason[reason.split(":")[0]] += 1
    print(f"\nFlagged: {len(flagged):,} ingredients")
    print(f"  covering {sum(int(r['recipe_count']) for r in flagged):,} recipe references")
    print(f"  → {OUT}")
    print("\nBy reason:")
    for reason, count in by_reason.most_common():
        print(f"  {reason:<32} {count:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
