#!/usr/bin/env python3
"""Align LLM-generated HTC codes + item descriptions to nutrition database keys.

Reads a CSV/JSONL of LLM-discovered items (with HTC codes, modifiers, flavors)
and marries them to canonical nutrition entries from canonical_items.csv.

Input columns (CSV or JSONL):
    item              raw product/ingredient string
    htc_code          8-char HTC code (optional but recommended)
    htc_group         1-char group (optional)
    htc_family        1-char family (optional)
    modifier          variant/modifier discovered by LLM (optional)
    flavor            flavor discovered by LLM (optional)

Output columns:
    item, htc_code, matched_canonical, ingredient_key, key_type,
    confidence, modifier, flavor, per_100g_kcal, per_100g_protein_g,
    per_100g_fat_g, per_100g_carbs_g

Usage:
    python3 implementation/align_llm_htc_to_nutrition.py \
        --input llm_discovered_items.jsonl \
        --output aligned_nutrition.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Try rapidfuzz for better performance; fall back to difflib
try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except Exception:  # noqa: BLE001
    from difflib import get_close_matches
    HAS_RAPIDFUZZ = False


ROOT = Path(__file__).resolve().parent.parent
CANONICAL_ITEMS_CSV = ROOT / "implementation" / "canonical_items.csv"

# Weak tokens to strip during normalization
WEAK_TOKENS = {
    "a", "an", "and", "with", "without", "for", "from", "fresh", "raw",
    "cooked", "prepared", "regular", "plain", "original", "natural", "organic",
    "generic", "nfs", "nsv", "type", "large", "medium", "small",
}


@dataclass(frozen=True)
class CanonicalEntry:
    canonical_name: str
    sr28_code: str
    sr28_description: str
    fndds_code: str
    fndds_description: str
    esha_code: str
    esha_description: str
    per_100g_kcal: float | None
    per_100g_protein_g: float | None
    per_100g_fat_g: float | None
    per_100g_carbs_g: float | None
    review_status: str
    source: str


@dataclass
class AlignmentResult:
    item: str
    htc_code: str
    matched_canonical: str
    ingredient_key: str
    key_type: str
    confidence: float
    modifier: str
    flavor: str
    per_100g_kcal: float | None
    per_100g_protein_g: float | None
    per_100g_fat_g: float | None
    per_100g_carbs_g: float | None
    match_method: str


def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    tokens = [t for t in s.split() if t not in WEAK_TOKENS and len(t) > 1]
    return " ".join(tokens)


def strip_qty_unit(text: str) -> str:
    """Remove leading quantity patterns like '1/4 cup', '2 tablespoons', etc."""
    # mixed number + unit
    text = re.sub(
        r"^\s*(?:\d+\s+\d+/\d+|\d+/\d+|\d*\.\d+|\d+)\s*"
        r"(?:cups?|cup\.|tbsp\.?|tbs\.?|tsp\.?|ts\.?|tablespoons?|teaspoons?|"
        r"ounces?|oz\.|fl\.?\s*oz\.?|pounds?|lbs?\.?|grams?|g\b|kg|ml|l\b|"
        r"quarts?|qts?\.?|pints?|pts?\.?|gallons?|gal\.?|packages?|pkg\.?|"
        r"slices?|sticks?|cloves?|sprigs?|bunches?|cans?|bottles?|jars?|heads?|"
        r"ears?|stalks?|leaves?|dash(?:es)?|pinch(?:es)?|servings?)\s+",
        "",
        text,
        flags=re.I,
    )
    return text.strip(", ")


def load_canonical_items(path: Path) -> list[CanonicalEntry]:
    entries: list[CanonicalEntry] = []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            def _f(key: str) -> float | None:
                v = (row.get(key) or "").strip()
                try:
                    return float(v) if v else None
                except ValueError:
                    return None

            entries.append(
                CanonicalEntry(
                    canonical_name=(row.get("canonical_name") or "").strip().lower(),
                    sr28_code=(row.get("sr28_ndb") or "").strip(),
                    sr28_description=(row.get("sr28_description") or "").strip(),
                    fndds_code=(row.get("fndds_code") or "").strip(),
                    fndds_description=(row.get("fndds_description") or "").strip(),
                    esha_code=(row.get("esha_code") or "").strip(),
                    esha_description=(row.get("esha_description") or "").strip(),
                    per_100g_kcal=_f("per_100g_kcal"),
                    per_100g_protein_g=_f("per_100g_protein_g"),
                    per_100g_fat_g=_f("per_100g_fat_g"),
                    per_100g_carbs_g=_f("per_100g_carbs_g"),
                    review_status=(row.get("review_status") or "").strip(),
                    source=(row.get("source") or "").strip(),
                )
            )
    return entries


def build_indexes(entries: list[CanonicalEntry]) -> dict[str, Any]:
    """Build lookup indexes for fast matching."""
    by_name: dict[str, CanonicalEntry] = {}
    by_sr28: dict[str, CanonicalEntry] = {}
    by_fndds: dict[str, CanonicalEntry] = {}
    by_esha: dict[str, CanonicalEntry] = {}
    all_names: list[str] = []

    for e in entries:
        if e.canonical_name:
            by_name[e.canonical_name] = e
            all_names.append(e.canonical_name)
        if e.sr28_code:
            by_sr28[e.sr28_code] = e
        if e.fndds_code:
            by_fndds[e.fndds_code] = e
        if e.esha_code:
            by_esha[e.esha_code] = e

    return {
        "by_name": by_name,
        "by_sr28": by_sr28,
        "by_fndds": by_fndds,
        "by_esha": by_esha,
        "all_names": all_names,
    }


def score_match(item_norm: str, candidate: CanonicalEntry) -> tuple[float, str]:
    """Return (score, method) for how well candidate matches item_norm."""
    cname = candidate.canonical_name

    # Exact match
    if item_norm == cname:
        return 1.0, "exact"

    # Substring containment (bidirectional)
    if item_norm in cname or cname in item_norm:
        # Length ratio as confidence
        ratio = min(len(item_norm), len(cname)) / max(len(item_norm), len(cname))
        return 0.7 + (ratio * 0.25), "substring"

    # Token overlap
    item_tokens = set(item_norm.split())
    cand_tokens = set(cname.split())
    if item_tokens and cand_tokens:
        overlap = len(item_tokens & cand_tokens)
        union = len(item_tokens | cand_tokens)
        if union > 0:
            jaccard = overlap / union
            if jaccard >= 0.5:
                return 0.5 + (jaccard * 0.2), "token_overlap"

    return 0.0, "none"


def fuzzy_find_best(
    item_norm: str,
    indexes: dict[str, Any],
    top_n: int = 10,
) -> tuple[CanonicalEntry | None, float, str]:
    """Find best matching canonical entry for item_norm."""
    # Try exact / substring first
    best_score = 0.0
    best_entry: CanonicalEntry | None = None
    best_method = "none"

    for name, entry in indexes["by_name"].items():
        score, method = score_match(item_norm, entry)
        if score > best_score:
            best_score = score
            best_entry = entry
            best_method = method

    if best_score >= 0.85:
        return best_entry, best_score, best_method

    # Fuzzy fallback
    if HAS_RAPIDFUZZ:
        results = process.extract(
            item_norm,
            indexes["all_names"],
            scorer=fuzz.partial_ratio,
            limit=top_n,
        )
        for name, score, _idx in results:
            if score > best_score * 100:
                entry = indexes["by_name"][name]
                best_score = score / 100.0
                best_entry = entry
                best_method = "fuzzy_rapidfuzz"
    else:
        matches = get_close_matches(
            item_norm,
            indexes["all_names"],
            n=top_n,
            cutoff=0.6,
        )
        for name in matches:
            entry = indexes["by_name"][name]
            score, method = score_match(item_norm, entry)
            if score > best_score:
                best_score = score
                best_entry = entry
                best_method = "fuzzy_difflib"

    return best_entry, best_score, best_method


def pick_ingredient_key(entry: CanonicalEntry) -> tuple[str, str]:
    """Return (key, key_type) prioritizing ESHA > SR28 > FNDDS."""
    if entry.esha_code:
        return f"ESHA:{entry.esha_code}", "esha"
    if entry.sr28_code:
        return f"SR28:{entry.sr28_code}", "sr28"
    if entry.fndds_code:
        return f"FNDDS:{entry.fndds_code}", "fndds"
    return "", "none"


def align_item(
    row: dict[str, str],
    indexes: dict[str, Any],
) -> AlignmentResult:
    item = (row.get("item") or "").strip()
    htc_code = (row.get("htc_code") or "").strip()
    modifier = (row.get("modifier") or "").strip()
    flavor = (row.get("flavor") or "").strip()

    # Strip quantity/unit from recipe-style inputs
    item_clean = strip_qty_unit(item)
    item_norm = normalize(item_clean)

    best_entry, score, method = fuzzy_find_best(item_norm, indexes)

    if best_entry is None:
        return AlignmentResult(
            item=item,
            htc_code=htc_code,
            matched_canonical="",
            ingredient_key="",
            key_type="unresolved",
            confidence=0.0,
            modifier=modifier,
            flavor=flavor,
            per_100g_kcal=None,
            per_100g_protein_g=None,
            per_100g_fat_g=None,
            per_100g_carbs_g=None,
            match_method="none",
        )

    key, key_type = pick_ingredient_key(best_entry)
    return AlignmentResult(
        item=item,
        htc_code=htc_code,
        matched_canonical=best_entry.canonical_name,
        ingredient_key=key,
        key_type=key_type,
        confidence=round(score, 4),
        modifier=modifier,
        flavor=flavor,
        per_100g_kcal=best_entry.per_100g_kcal,
        per_100g_protein_g=best_entry.per_100g_protein_g,
        per_100g_fat_g=best_entry.per_100g_fat_g,
        per_100g_carbs_g=best_entry.per_100g_carbs_g,
        match_method=method,
    )


def read_input(path: Path) -> list[dict[str, str]]:
    suffix = path.suffix.lower()
    rows: list[dict[str, str]] = []
    if suffix == ".jsonl":
        with path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    else:
        # Assume CSV
        with path.open(newline="") as f:
            rows = list(csv.DictReader(f))
    return rows


def write_output(path: Path, results: list[AlignmentResult]) -> None:
    fieldnames = [
        "item", "htc_code", "matched_canonical", "ingredient_key", "key_type",
        "confidence", "modifier", "flavor", "per_100g_kcal", "per_100g_protein_g",
        "per_100g_fat_g", "per_100g_carbs_g", "match_method",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "item": r.item,
                "htc_code": r.htc_code,
                "matched_canonical": r.matched_canonical,
                "ingredient_key": r.ingredient_key,
                "key_type": r.key_type,
                "confidence": r.confidence,
                "modifier": r.modifier,
                "flavor": r.flavor,
                "per_100g_kcal": r.per_100g_kcal,
                "per_100g_protein_g": r.per_100g_protein_g,
                "per_100g_fat_g": r.per_100g_fat_g,
                "per_100g_carbs_g": r.per_100g_carbs_g,
                "match_method": r.match_method,
            })


def main() -> int:
    ap = argparse.ArgumentParser(description="Align LLM HTC outputs to nutrition DB keys")
    ap.add_argument("--input", type=Path, required=True, help="Input CSV or JSONL of LLM-discovered items")
    ap.add_argument("--output", type=Path, required=True, help="Output CSV of aligned nutrition keys")
    ap.add_argument("--canonical-items", type=Path, default=CANONICAL_ITEMS_CSV,
                    help="Path to canonical_items.csv")
    args = ap.parse_args()

    if not args.canonical_items.exists():
        print(f"ERROR: canonical_items.csv not found at {args.canonical_items}", file=sys.stderr)
        return 1

    print(f"Loading canonical items from {args.canonical_items} ...")
    entries = load_canonical_items(args.canonical_items)
    indexes = build_indexes(entries)
    print(f"  Indexed {len(entries):,} entries")

    print(f"Reading LLM output from {args.input} ...")
    rows = read_input(args.input)
    print(f"  {len(rows):,} items to align")

    results: list[AlignmentResult] = []
    unresolved = 0
    for i, row in enumerate(rows, 1):
        result = align_item(row, indexes)
        results.append(result)
        if not result.ingredient_key:
            unresolved += 1
        if i % 1000 == 0:
            print(f"  processed {i:,} ...")

    write_output(args.output, results)
    resolved = len(results) - unresolved
    print(f"\nDone. {resolved:,}/{len(results):,} resolved ({resolved/len(results):.1%})")
    print(f"Output written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
