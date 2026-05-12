#!/usr/bin/env python3
"""Audit data-layer LLM misroutes.

Two outputs:

1. **Review log** (`data_layer_misroute_audit.csv`)
   Surfaces every recipe-ingredient row whose canonical_path looks wrong vs.
   what its title implies. Hand-curate from this — DO NOT auto-apply.

2. **Safe override file** (`data_layer_misroute_overrides.csv`)
   Only emits overrides for the narrow class we can fix mechanically:
   "Spice Blend" generic leaf when the title names a specific spice/herb.
   E.g. `ground ginger` at `Pantry > Spices & Seasonings > Spice Blend`
   → `Pantry > Spices & Seasonings > Ginger`.

The flag categories in the review log:

  - spice_blend_too_generic   title names a specific spice; leaf is "Spice Blend"
  - fresh_outside_produce     `fresh X` not under Produce
  - dried_inside_produce      `dried X` filed under Produce (should be Pantry/Snack)
  - leaf_disagrees_top        same normalized canonical found at multiple top
                              containers (Produce + Pantry + Snack); flagged for review

Voting heuristics deliberately removed — they were unsafe because the LLM
majority-misroutes and would direct fixes the wrong way.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
TAX = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
AUDIT_IN = ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_full_audit.csv"
UNIVERSE = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
OUT_OVERRIDES = ROOT / "recipe_pricing" / "data_layer_misroute_overrides.csv"
OUT_REVIEW = ROOT / "recipe_pricing" / "data_layer_misroute_audit.csv"

# Aliases for spice leaves whose "natural" name is missing from FDC universe.
# Map "what we'd write" → "what FDC actually has".
SPICE_ALIASES = {
    "Pantry > Spices & Seasonings > Red Pepper Flakes": "Pantry > Spices & Seasonings > Crushed Red Pepper",
    "Pantry > Spices & Seasonings > Dry Mustard": "Pantry > Spices & Seasonings > Mustard Powder",
    "Pantry > Spices & Seasonings > Coriander": "Pantry > Spices & Seasonings > Coriander Seed",
}

MIN_RC = 5  # only surface rows with ≥5 recipe references

PREFIX_RE = re.compile(
    r"^(fresh|raw|minced|chopped|diced|sliced|grated|shredded|"
    r"ground|dried|powdered|flaked|crushed|"
    r"frozen|canned|jarred|pickled)\s+(.+)$",
    re.I,
)
FRESH_PREFIXES  = {"fresh", "raw", "minced", "chopped", "diced", "sliced", "grated", "shredded"}
SPICE_PREFIXES  = {"ground", "dried", "powdered", "flaked", "crushed"}


def title_to_regex(title: str) -> str:
    t = title.strip().lower()
    if not t:
        return ""
    return f"^{re.escape(t)}s?$"


def main() -> int:
    # Load FDC retail universe — proposed paths MUST exist here, otherwise
    # cleanup_llm_output's parent-strip will collapse them to the parent.
    universe: set[str] = set()
    with UNIVERSE.open() as f:
        for row in csv.DictReader(f):
            cp = (row.get("canonical_path") or "").strip()
            if cp:
                universe.add(cp)

    counts: dict[str, int] = {}
    with AUDIT_IN.open() as f:
        for row in csv.DictReader(f):
            counts[row["item"].lower()] = int(row.get("recipe_count", "0") or 0)

    rows: list[dict] = []
    with TAX.open() as f:
        for row in csv.DictReader(f):
            title = (row.get("title") or "").strip().lower()
            cp = (row.get("canonical_path") or "").strip()
            nc = (row.get("normalized_canonical_text") or "").strip().lower()
            if not title or not cp:
                continue
            rows.append({
                "title": title,
                "cp": cp,
                "nc": nc,
                "rc": counts.get(title, 0),
            })

    # Index leaf-noun → set of distinct top containers seen
    leaf_top_seen: defaultdict[str, set[str]] = defaultdict(set)
    leaf_paths: defaultdict[str, Counter] = defaultdict(Counter)
    for r in rows:
        m = PREFIX_RE.match(r["title"])
        leaf = m.group(2) if m else r["title"]
        top = r["cp"].split(" > ", 1)[0]
        leaf_top_seen[leaf].add(top)
        leaf_paths[leaf][r["cp"]] += r["rc"]

    flagged: list[dict] = []

    for r in rows:
        if r["rc"] < MIN_RC:
            continue
        title = r["title"]
        cp = r["cp"]
        m = PREFIX_RE.match(title)
        prefix = m.group(1).lower() if m else ""
        leaf = m.group(2).lower() if m else title
        top = cp.split(" > ", 1)[0]
        leaf_node = cp.split(" > ")[-1] if " > " in cp else cp

        # Category 1 — "Spice Blend" generic leaf when title names a specific spice
        if leaf_node == "Spice Blend" and cp.startswith("Pantry > Spices"):
            specific = leaf.title()
            proposed = f"Pantry > Spices & Seasonings > {specific}"
            proposed = SPICE_ALIASES.get(proposed, proposed)
            # Only emit override if proposed path actually exists in FDC universe
            if proposed != cp and proposed in universe:
                flagged.append({
                    "category": "spice_blend_too_generic",
                    "title": title,
                    "current_canonical_path": cp,
                    "proposed_canonical_path": proposed,
                    "recipe_count": r["rc"],
                    "safe_to_apply": "yes",
                })
                continue
            elif proposed != cp:
                # Proposed leaf doesn't exist in FDC — flag for review only
                flagged.append({
                    "category": "spice_blend_too_generic_no_fdc_leaf",
                    "title": title,
                    "current_canonical_path": cp,
                    "proposed_canonical_path": proposed,
                    "recipe_count": r["rc"],
                    "safe_to_apply": "review",
                })
                continue

        # Category 2 — `fresh <X>` not under Produce, but X has a Produce path
        if prefix in FRESH_PREFIXES:
            if top != "Produce":
                produce_paths = [
                    p for p in leaf_paths[leaf]
                    if p.startswith("Produce > ") and p in universe
                ]
                if produce_paths:
                    proposed = max(produce_paths, key=lambda p: leaf_paths[leaf][p])
                    flagged.append({
                        "category": "fresh_outside_produce",
                        "title": title,
                        "current_canonical_path": cp,
                        "proposed_canonical_path": proposed,
                        "recipe_count": r["rc"],
                        "safe_to_apply": "yes",
                    })
                    continue

        # Category 3 — `dried <X>` filed under Produce
        if prefix in SPICE_PREFIXES and top == "Produce":
            alt_paths = [
                p for p in leaf_paths[leaf]
                if (p.startswith("Pantry > Spices") or p.startswith("Snack > Dried"))
                and p in universe
            ]
            if alt_paths:
                proposed = max(alt_paths, key=lambda p: leaf_paths[leaf][p])
                flagged.append({
                    "category": "dried_inside_produce",
                    "title": title,
                    "current_canonical_path": cp,
                    "proposed_canonical_path": proposed,
                    "recipe_count": r["rc"],
                    "safe_to_apply": "yes",
                })
                continue

        # Category 4 — same leaf appears across ≥3 top containers (high confusion)
        if len(leaf_top_seen[leaf]) >= 3:
            flagged.append({
                "category": "leaf_disagrees_top",
                "title": title,
                "current_canonical_path": cp,
                "proposed_canonical_path": "",
                "recipe_count": r["rc"],
                "safe_to_apply": "review",
            })

    flagged.sort(key=lambda r: (-r["recipe_count"], r["category"]))

    OUT_REVIEW.parent.mkdir(parents=True, exist_ok=True)
    with OUT_REVIEW.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "category", "title", "current_canonical_path",
            "proposed_canonical_path", "recipe_count", "safe_to_apply",
        ])
        w.writeheader()
        w.writerows(flagged)

    # Override file: only the spice_blend_too_generic class (safe to mass-apply)
    safe = [r for r in flagged if r["safe_to_apply"] == "yes"]
    rules = []
    seen = set()
    for r in safe:
        pat = title_to_regex(r["title"])
        if not pat or pat in seen:
            continue
        seen.add(pat)
        leaf_label = r["proposed_canonical_path"].split(" > ")[-1]
        rules.append({
            "pattern": pat,
            "canonical_path": r["proposed_canonical_path"],
            "canonical_label": leaf_label,
            "product_identity_fixed": leaf_label,
            "modifier": "",
            "note": f"data-layer fix: {r['category']} (rc={r['recipe_count']})",
        })

    with OUT_OVERRIDES.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "pattern", "canonical_path", "canonical_label",
            "product_identity_fixed", "modifier", "note",
        ])
        w.writeheader()
        w.writerows(rules)

    by_cat: Counter[str] = Counter(r["category"] for r in flagged)
    print(f"Total flagged: {len(flagged):,}", file=sys.stderr)
    for cat, n in by_cat.most_common():
        print(f"  {cat:<28} {n:>5}", file=sys.stderr)
    print(f"\nSafe-to-apply overrides: {len(rules):,}", file=sys.stderr)
    print(f"  → {OUT_OVERRIDES}", file=sys.stderr)
    print(f"  → {OUT_REVIEW} (full review log)", file=sys.stderr)
    print(f"\nTop 25 spice_blend_too_generic:", file=sys.stderr)
    sb = [r for r in flagged if r["category"] == "spice_blend_too_generic"][:25]
    for r in sb:
        print(f"  [{r['recipe_count']:>5}] {r['title']:<32} → {r['proposed_canonical_path']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
