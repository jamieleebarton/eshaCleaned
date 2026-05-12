#!/usr/bin/env python3
"""For every recipe ingredient currently routed to Non-Food (~N0000009), look
at DeepSeek's original `llm_canonical_path` (already in the v2 row). If the
LLM thought it was food, walk the LLM's path up the ancestor tree to find a
real FDC retail path. Generate title-pattern overrides to redirect.

We don't need to call the LLM again — DeepSeek's output is preserved in the
v2 taxonomy's `llm_canonical_path` column. The cleanup pipeline previously
discarded it when the path wasn't in FDC; we now recover it.

Output: recipe_pricing/non_food_recovery_overrides.csv with title-regex →
real-FDC-path mappings ready to append to walmart_kroger_overrides.csv.
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
TAX = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
AUDIT = ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_full_audit.csv"
FDC = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
OVERRIDES = ROOT / "recipe_pricing" / "walmart_kroger_overrides.csv"
OUT = ROOT / "recipe_pricing" / "non_food_recovery_overrides.csv"

# True non-food keywords — paths/titles that DeepSeek correctly identified as
# non-food should stay as non-food. We don't try to recover these.
TRUE_NON_FOOD_PATH_PREFIXES = (
    "non-food", "personal care", "household", "beauty",
    "health & beauty", "kitchen & dining", "office",
    "automotive", "lawn & garden", "floral", "hardware",
    "tools", "electronics", "clothing", "apparel",
    "sports & wellness > personal care", "bath & body",
    "kitchen supplies", "kitchen tools", "household supplies",
    "foil & wrap", "baking supplies",  # parchment paper, foil, etc.
    "non-food > other > frozen",  # decorative ice
)
TRUE_NON_FOOD_TITLE_PATTERNS = re.compile(
    r"\b(toothpicks?|skewers?|foil|wax paper|parchment paper|kitchen string|"
    r"napkins?|popsicle sticks?|paraffin wax|beeswax|glycerin[e]?|"
    r"hydrogen peroxide|epsom salts?|aloe vera gel|baking cups?|baby oil|"
    r"shea butter|petroleum jelly|essential oil|tea tree|rubbing alcohol|"
    r"oven cooking bags?|chocolate transfer sheets?|coffee filters?|"
    r"cooking spray|mason jars?|cellophane|heating pad)\b",
    re.I,
)


def load_fdc_paths() -> tuple[set[str], set[str]]:
    """Returns (real_canonical_paths, synth_anchor_paths)."""
    real = set()
    synth = set()
    with FDC.open() as f:
        for row in csv.DictReader(f):
            cp = (row.get("canonical_path") or "").strip()
            if not cp:
                continue
            if (row.get("consensus_source") or "").strip() == "synthetic_taxonomy_anchor":
                synth.add(cp)
            else:
                real.add(cp)
    return real, synth


# LLM path prefixes → FDC equivalent prefixes. The LLM uses category names
# that aren't in FDC (Seafood, Liqueurs, Herbs, etc.); these rewrite the LLM
# path so the walk-up can find a real FDC ancestor.
LLM_PREFIX_REWRITES: list[tuple[str, str]] = [
    ("Meat & Seafood > Seafood",                 "Meat & Seafood > Fish"),
    ("Meat & Seafood > Game",                    "Meat & Seafood > Game Meats"),
    ("Beverage > Liqueurs",                      "Beverage > Spirits > Liqueur"),
    ("Beverage > Alcoholic Beverages",           "Beverage > Spirits > Liqueur"),
    ("Beverage > Wine & Champagne",              "Beverage > Wine"),
    ("Beverage > Alcohol",                       "Beverage > Spirits > Liqueur"),
    ("Produce > Herbs",                          "Pantry > Spices & Seasonings"),
    ("Produce > Herbs & Greens",                 "Pantry > Spices & Seasonings"),
    ("Cereal > Breakfast Cereals",               "Pantry > Cereal"),
    ("Cereal",                                   "Pantry > Cereal"),
    ("Refrigerated > Pie Crusts & Pastry Dough", "Bakery > Pastry"),
    ("Refrigerated",                             "Pantry"),
    ("Frozen > Appetizers & Snacks",             "Frozen"),
]


def apply_prefix_rewrites(llm_path: str) -> str:
    for old, new in LLM_PREFIX_REWRITES:
        if llm_path.startswith(old):
            return new + llm_path[len(old):]
    return llm_path


def closest_real_path(llm_path: str, real_paths: set[str], synth_paths: set[str]) -> str:
    """Walk the LLM's path up to find a real FDC canonical_path. Applies LLM
    prefix rewrites first. Returns '' if nothing on the lineage exists."""
    if not llm_path:
        return ""
    rewritten = apply_prefix_rewrites(llm_path)
    parts = [p.strip() for p in rewritten.split(" > ") if p.strip()]
    while parts:
        candidate = " > ".join(parts)
        if candidate in real_paths or candidate in synth_paths:
            return candidate
        parts.pop()
    return ""


def title_to_regex(title: str) -> str:
    t = title.strip().lower()
    if not t:
        return ""
    if t.endswith("s") and len(t) > 4 and not t.endswith("ss"):
        stem = t[:-1]
        return f"^{re.escape(stem)}s?$"
    return f"^{re.escape(t)}s?$"


def main() -> int:
    real_paths, synth_paths = load_fdc_paths()
    print(f"FDC real paths: {len(real_paths):,}", file=sys.stderr)
    print(f"FDC synth paths: {len(synth_paths):,}", file=sys.stderr)

    counts: dict[str, int] = {}
    with AUDIT.open() as f:
        for row in csv.DictReader(f):
            counts[row["item"].lower()] = int(row.get("recipe_count", "0") or 0)

    recoverable: list[dict] = []
    truly_non_food: list[dict] = []
    cant_recover: list[dict] = []

    with TAX.open() as f:
        for row in csv.DictReader(f):
            if row.get("htc_group", "") != "N":
                continue
            title = (row.get("title") or "").strip()
            llm_cp = (row.get("llm_canonical_path") or "").strip()

            # If DeepSeek (or our cleanup) put it in a true non-food category,
            # leave it alone.
            if any(llm_cp.lower().startswith(pre) for pre in TRUE_NON_FOOD_PATH_PREFIXES) \
                    or TRUE_NON_FOOD_TITLE_PATTERNS.search(title):
                truly_non_food.append({
                    "title": title, "llm_canonical_path": llm_cp,
                    "recipe_count": counts.get(title.lower(), 0),
                })
                continue

            # Try to recover by walking the LLM path up to a real FDC path
            recovered = closest_real_path(llm_cp, real_paths, synth_paths)
            if recovered:
                recoverable.append({
                    "title": title, "llm_canonical_path": llm_cp,
                    "recovered_path": recovered,
                    "recipe_count": counts.get(title.lower(), 0),
                })
            else:
                cant_recover.append({
                    "title": title, "llm_canonical_path": llm_cp,
                    "recipe_count": counts.get(title.lower(), 0),
                })

    print(f"\nNon-food classification recovery:", file=sys.stderr)
    print(f"  recoverable (walk to real FDC):       {len(recoverable):,}", file=sys.stderr)
    print(f"  truly non-food (correct already):    {len(truly_non_food):,}", file=sys.stderr)
    print(f"  can't recover (no real FDC ancestor): {len(cant_recover):,}", file=sys.stderr)

    # Write override rules for recoverable rows
    recoverable.sort(key=lambda r: -r["recipe_count"])
    rules: list[dict] = []
    seen_patterns: set[str] = set()
    for r in recoverable:
        pattern = title_to_regex(r["title"])
        if not pattern or pattern in seen_patterns:
            continue
        seen_patterns.add(pattern)
        # Use the leaf segment of the recovered path as identity
        leaf = r["recovered_path"].split(" > ")[-1] if " > " in r["recovered_path"] else r["recovered_path"]
        rules.append({
            "pattern": pattern,
            "canonical_path": r["recovered_path"],
            "canonical_label": leaf,
            "product_identity_fixed": leaf,
            "modifier": "",
            "note": f"non-food recovery via llm_canonical_path (rc={r['recipe_count']})",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "pattern", "canonical_path", "canonical_label",
            "product_identity_fixed", "modifier", "note",
        ])
        w.writeheader()
        w.writerows(rules)
    print(f"  wrote {len(rules):,} recovery overrides → {OUT}", file=sys.stderr)

    # Also report top can't-recover items
    cant_recover.sort(key=lambda r: -r["recipe_count"])
    if cant_recover:
        print(f"\n  top 15 can't-recover (LLM path has no real FDC ancestor):", file=sys.stderr)
        for r in cant_recover[:15]:
            print(f"    [{r['recipe_count']:>5}] {r['title']:<32} llm: {r['llm_canonical_path']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
