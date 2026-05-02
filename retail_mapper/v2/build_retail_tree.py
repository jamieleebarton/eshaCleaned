#!/usr/bin/env python3
"""Build the retail-ready product tree.

The previous product_tree.json stops at `Bakery > Bagels`, but retail use
requires going deeper — `Bakery > Bagels > Plain`, `Bakery > Bagels > Blueberry`,
`Bakery > Bagels > Everything` — so a recipe asking for "bagels" can pick the
plain default and avoid the flavored variants.

This script reads full_corpus_enriched.csv (which already carries variant +
flavor + canonical_label), folds those facets into the path as a new leaf
level, and emits:

  - retail_tree.json          — nested tree with the new modifier level
  - retail_tree_nodes.csv     — flat node list, sortable
  - retail_tree_leaves.csv    — one row per FINAL leaf, with SKU count and
                                dominant FNDDS/SR28/ESHA. This is the retail
                                lookup table — for "bagel" → Plain bagel
                                product, FNDDS code, SR28 code.

Modifier extraction rules:
  1. Use the first non-empty `variant` value (variants are structural:
     plain / everything / cinnamon_raisin / whole_wheat).
  2. If no variant, use the first non-empty `flavor` value (blueberry,
     chocolate_chip, etc.).
  3. If neither, the modifier is "Plain" — the implicit default.
  4. Variants/flavors that mean "the regular kind" (plain, regular, original,
     classic) all collapse to "Plain" so a recipe lookup hits one bucket.

Usage:
    python3 retail_mapper/v2/build_retail_tree.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from taxonomy_finalizer import finalize_taxonomy_row

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
CLEAN_SRC = V2 / "full_corpus_cleaned.csv"   # has variant + flavor + canonical_label
ENRICH_SRC = V2 / "full_corpus_enriched.csv" # has fndds_code + sr28_code + esha_code
OUT_JSON = V2 / "retail_tree.json"
OUT_NODES = V2 / "retail_tree_nodes.csv"
OUT_LEAVES = V2 / "retail_tree_leaves.csv"

csv.field_size_limit(sys.maxsize)

# Variant/flavor values that mean "no special modifier — this is the regular
# version a recipe would want by default."
PLAIN_TOKENS = {
    "plain", "regular", "original", "classic", "natural",
    "unflavored", "unscented", "neutral",
    "enriched", "unenriched",
    "artisan", "rustic", "country", "homestyle", "traditional",
    "gourmet", "bakery", "style", "authentic", "old", "fashioned",
    "premium", "deluxe", "fancy", "handcrafted", "signature", "select",
}


def prettify(token: str) -> str:
    """plain → Plain; cinnamon_raisin → Cinnamon Raisin; whole_wheat → Whole Wheat."""
    if not token:
        return ""
    return " ".join(w.capitalize() for w in token.replace("_", " ").split())


def first_facet_value(s: str) -> str:
    """Take the first pipe-separated value from a facet column."""
    if not s:
        return ""
    return s.split("|")[0].strip()


RELEVANT_CLAIMS = {
    "diet","light","low_fat","fat_free","reduced_fat",
    "sugar_free","no_sugar_added","unsweetened","low_sodium",
    "decaf","decaffeinated","caffeine_free",
    "gluten_free","organic","keto","paleo","whole_grain",
}
RELEVANT_FORMS = {
    "stuffed","filled","topped","split","sliced","pre_sliced",
    "twisted","layered","rolled","frosted","glazed",
}


def all_facet_values(s: str) -> list[str]:
    if not s: return []
    return [v.strip() for v in s.split("|") if v.strip()]


def _drop_plain_dedup(toks: list[str]) -> list[str]:
    toks = [t for t in toks if t.lower() not in PLAIN_TOKENS]
    seen: set[str] = set()
    out: list[str] = []
    for t in toks:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def derive_modifier(variant: str, flavor: str, claims: str = "", form: str = "") -> str:
    """Returns a '>'-separated multi-level modifier string. The caller appends
    this to the base path so each level becomes its own tree node.
      Level 1: variant + flavor (style/taste)
      Level 2: claims (organic, gluten free, diet)
      Level 3: structural form (stuffed, sliced)
    e.g. variant='honey_wheat', claims='organic' → 'Honey Wheat > Organic'
    """
    l1 = _drop_plain_dedup(all_facet_values(variant) + all_facet_values(flavor))
    l2 = _drop_plain_dedup(
        [c for c in all_facet_values(claims) if c.lower() in RELEVANT_CLAIMS])
    l3 = _drop_plain_dedup(
        [t for t in all_facet_values(form) if t.lower() in RELEVANT_FORMS])
    levels: list[str] = []
    if l1: levels.append(" ".join(prettify(t) for t in l1))
    if l2: levels.append(" ".join(prettify(t) for t in l2))
    if l3: levels.append(" ".join(prettify(t) for t in l3))
    return " > ".join(levels) if levels else "Plain"


def main() -> None:
    if not CLEAN_SRC.exists() or not ENRICH_SRC.exists():
        raise SystemExit(f"missing {CLEAN_SRC} or {ENRICH_SRC}")

    # Pass 1: read enriched CSV, index FNDDS/SR28/ESHA by fdc_id
    print(f"  indexing {ENRICH_SRC.name}")
    codes_by_fdc: dict[str, tuple[str, str, str]] = {}
    with ENRICH_SRC.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fdc = (r.get("fdc_id") or "").strip()
            if fdc:
                codes_by_fdc[fdc] = (
                    (r.get("fndds_code") or "").strip(),
                    (r.get("sr28_code") or "").strip(),
                    (r.get("esha_code") or "").strip(),
                )
    print(f"    indexed codes for {len(codes_by_fdc):,} fdc_ids")

    print(f"  reading {CLEAN_SRC.name}")

    # leaf_path = canonical_path + " > " + modifier
    leaf_count: Counter = Counter()
    leaf_fndds: dict[str, Counter] = defaultdict(Counter)
    leaf_sr28: dict[str, Counter] = defaultdict(Counter)
    leaf_esha: dict[str, Counter] = defaultdict(Counter)
    leaf_samples: dict[str, list] = defaultdict(list)
    leaf_modifier: dict[str, str] = {}
    leaf_base_path: dict[str, str] = {}
    leaf_identity: dict[str, str] = {}

    n_rows = 0
    with CLEAN_SRC.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            n_rows += 1
            fdc = (row.get("fdc_id") or "").strip()
            finalized = finalize_taxonomy_row(row)
            base_path = finalized.canonical_path
            identity = finalized.product_identity_fixed
            if not base_path or not identity:
                continue
            mod = finalized.modifier
            leaf_path = finalized.retail_leaf_path
            leaf_count[leaf_path] += 1
            leaf_modifier[leaf_path] = mod
            leaf_base_path[leaf_path] = base_path
            leaf_identity[leaf_path] = identity

            f_code, s_code, e_code = codes_by_fdc.get(fdc, ("", "", ""))
            if f_code: leaf_fndds[leaf_path][f_code] += 1
            if s_code: leaf_sr28[leaf_path][s_code] += 1
            if e_code: leaf_esha[leaf_path][e_code] += 1
            if len(leaf_samples[leaf_path]) < 5:
                title = (row.get("title") or "").strip()
                if title and title not in leaf_samples[leaf_path]:
                    leaf_samples[leaf_path].append(title)

    print(f"  read {n_rows:,} SKUs into {len(leaf_count):,} retail leaves")

    # Build node tree from all leaf paths
    nodes: dict[str, dict] = {}
    for leaf_path, count in leaf_count.items():
        parts = [p.strip() for p in leaf_path.split(">") if p.strip()]
        for i in range(1, len(parts) + 1):
            prefix = " > ".join(parts[:i])
            if prefix not in nodes:
                nodes[prefix] = {
                    "path": prefix,
                    "name": parts[i - 1],
                    "depth": i,
                    "parent": " > ".join(parts[: i - 1]) if i > 1 else None,
                    "n_skus_subtree": 0,
                    "n_skus_at_node": 0,
                }
            nodes[prefix]["n_skus_subtree"] += count
        nodes[leaf_path]["n_skus_at_node"] += count

    children_of: dict[str, list[str]] = defaultdict(list)
    for path, node in nodes.items():
        if node["parent"]:
            children_of[node["parent"]].append(path)
    for path, node in nodes.items():
        node["is_leaf"] = len(children_of.get(path, [])) == 0
        node["n_children"] = len(children_of.get(path, []))

    # ---- emit nested JSON
    def to_dict(path: str) -> dict:
        n = nodes[path]
        d = {
            "name": n["name"],
            "path": path,
            "depth": n["depth"],
            "is_leaf": n["is_leaf"],
            "n_skus_subtree": n["n_skus_subtree"],
            "n_skus_at_node": n["n_skus_at_node"],
        }
        if n["is_leaf"]:
            d["modifier"] = leaf_modifier.get(path, "")
            d["base_identity"] = leaf_identity.get(path, "")
            f_dom = leaf_fndds[path].most_common(1)
            s_dom = leaf_sr28[path].most_common(1)
            e_dom = leaf_esha[path].most_common(1)
            if f_dom:
                d["fndds_dominant"] = f_dom[0][0]
                d["fndds_dominant_pct"] = round(100*f_dom[0][1]/n["n_skus_at_node"])
            if s_dom:
                d["sr28_dominant"] = s_dom[0][0]
                d["sr28_dominant_pct"] = round(100*s_dom[0][1]/n["n_skus_at_node"])
            if e_dom:
                d["esha_dominant"] = e_dom[0][0]
                d["esha_dominant_pct"] = round(100*e_dom[0][1]/n["n_skus_at_node"])
            d["sample_titles"] = leaf_samples[path][:5]
        kids = sorted(children_of.get(path, []),
                      key=lambda p: -nodes[p]["n_skus_subtree"])
        if kids:
            d["children"] = [to_dict(k) for k in kids]
        return d

    roots = sorted(
        [p for p, n in nodes.items() if n["depth"] == 1],
        key=lambda p: -nodes[p]["n_skus_subtree"],
    )
    tree = {
        "name": "ROOT",
        "n_skus_subtree": sum(leaf_count.values()),
        "n_distinct_leaves": len(leaf_count),
        "n_total_nodes": len(nodes),
        "children": [to_dict(r) for r in roots],
    }
    OUT_JSON.write_text(json.dumps(tree, indent=2))
    print(f"  wrote {OUT_JSON.name} "
          f"({OUT_JSON.stat().st_size / 1024 / 1024:.1f} MB, {len(nodes):,} nodes)")

    # ---- emit flat node list
    cols = ["path","depth","name","parent","is_leaf","n_children",
            "n_skus_subtree","n_skus_at_node"]
    with OUT_NODES.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for path in sorted(nodes.keys(),
                           key=lambda p: (nodes[p]["depth"],
                                          -nodes[p]["n_skus_subtree"])):
            n = nodes[path]
            w.writerow({
                "path": path,
                "depth": n["depth"],
                "name": n["name"],
                "parent": n["parent"] or "",
                "is_leaf": int(n["is_leaf"]),
                "n_children": n["n_children"],
                "n_skus_subtree": n["n_skus_subtree"],
                "n_skus_at_node": n["n_skus_at_node"],
            })
    print(f"  wrote {OUT_NODES.name} ({len(nodes):,} nodes)")

    # ---- emit leaves CSV (the retail lookup table)
    leaf_cols = [
        "leaf_path","base_identity","modifier",
        "n_skus","fndds_dominant","fndds_dominant_pct",
        "sr28_dominant","sr28_dominant_pct",
        "esha_dominant","esha_dominant_pct",
        "sample_titles",
    ]
    with OUT_LEAVES.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=leaf_cols)
        w.writeheader()
        for leaf_path in sorted(leaf_count.keys(),
                                key=lambda p: -leaf_count[p]):
            n = leaf_count[leaf_path]
            f_dom = leaf_fndds[leaf_path].most_common(1)
            s_dom = leaf_sr28[leaf_path].most_common(1)
            e_dom = leaf_esha[leaf_path].most_common(1)
            w.writerow({
                "leaf_path": leaf_path,
                "base_identity": leaf_identity.get(leaf_path, ""),
                "modifier": leaf_modifier.get(leaf_path, ""),
                "n_skus": n,
                "fndds_dominant": f_dom[0][0] if f_dom else "",
                "fndds_dominant_pct": round(100*f_dom[0][1]/n) if f_dom else 0,
                "sr28_dominant": s_dom[0][0] if s_dom else "",
                "sr28_dominant_pct": round(100*s_dom[0][1]/n) if s_dom else 0,
                "esha_dominant": e_dom[0][0] if e_dom else "",
                "esha_dominant_pct": round(100*e_dom[0][1]/n) if e_dom else 0,
                "sample_titles": " | ".join(leaf_samples[leaf_path][:3]),
            })
    print(f"  wrote {OUT_LEAVES.name} ({len(leaf_count):,} retail leaves)")

    # ---- summary
    plain_leaves = [p for p, m in leaf_modifier.items() if m == "Plain"]
    print()
    print(f"  Tree shape:")
    print(f"    top-levels:        {len(roots)}")
    print(f"    total nodes:       {len(nodes):,}")
    print(f"    retail leaves:     {len(leaf_count):,}")
    print(f"    'Plain' leaves:    {len(plain_leaves):,}")
    by_depth: Counter = Counter()
    for n in nodes.values():
        by_depth[n["depth"]] += 1
    for d in sorted(by_depth):
        print(f"    depth {d}:           {by_depth[d]:,}")


if __name__ == "__main__":
    main()
