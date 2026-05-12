#!/usr/bin/env python3
"""Find sibling path segments that are synonyms (same meaning, different words).

For each parent (top-2 segments) we collect every direct child segment used,
then flag pairs that match one of three signals:

  1. KNOWN synonyms (curated dictionary) — HIGH confidence
  2. Hyphen / spelling variants (Non-fat / Nonfat / Non fat) — HIGH confidence
  3. Same FNDDS code dominantly maps to BOTH siblings — MEDIUM confidence

Output: retail_mapper/v2/synonym_candidates.csv with columns:
  parent | seg_a | n_skus_a | seg_b | n_skus_b | confidence | reason | recommended_canonical

The detector also handles segment-pairs at deeper levels (e.g. 4th-segment).
Apply step (--apply) reads the same CSV and rewrites the smaller-count
segment to the recommended canonical. This is read-only by default.
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "synonym_candidates.csv"
LOG = V2 / "apply_synonyms_log.csv"

csv.field_size_limit(sys.maxsize)

# Known-synonym groups. First entry of each group is the CANONICAL form.
# All other entries get rewritten to that canonical when --apply is used.
KNOWN_SYNONYM_GROUPS: list[list[str]] = [
    ["Light", "Lite"],
    ["Crispy", "Crunchy", "Crisp"],
    ["Whole Wheat", "100% Whole Wheat", "100 Whole Wheat", "100 Percent Whole Wheat"],
    ["Whole Grain", "100% Whole Grain", "100 Whole Grain", "100 Percent Whole Grain"],
    ["Creamed", "Cream Style", "Cream-Style"],
    ["Extra Sharp", "X Sharp", "Xsharp"],
    ["Low Fat", "Lowfat", "Low-Fat"],
    ["Fat Free", "Fatfree", "Fat-Free", "Skim", "Nonfat", "Non Fat", "Non-Fat", "No Fat"],
    ["Reduced Fat", "Reduced-Fat"],
    ["Sugar Free", "Sugar-Free", "Sugarfree", "No Sugar", "0 Sugar"],
    ["Zero Sugar", "0 Sugar", "No Sugar Added", "0g Sugar"],
    ["Gluten Free", "Gluten-Free", "Glutenfree", "No Gluten"],
    ["Dairy Free", "Dairy-Free", "Dairyfree", "Non Dairy", "Non-Dairy", "Nondairy"],
    ["Lactose Free", "Lactose-Free", "No Lactose"],
    ["Caffeine Free", "Caffeine-Free", "Caffeinefree", "Decaffeinated", "Decaf"],
    ["Plant Based", "Plant-Based", "Plantbased"],
    ["Grass Fed", "Grass-Fed", "Grassfed"],
    ["Free Range", "Free-Range", "Freerange"],
    ["Cage Free", "Cage-Free", "Cagefree"],
    ["Wild Caught", "Wild-Caught", "Wildcaught"],
    # REMOVED: Original/Plain/Unflavored — different concepts in food context
    ["Natural", "All Natural", "100% Natural", "100 Natural"],
    # REMOVED: No Sugar Added vs Unsweetened — NSA has natural sugars, Unsweetened doesn't
    ["No Sugar Added", "No Added Sugar"],
    ["Carbonated", "Sparkling", "Fizzy"],
    ["Smoothie", "Smoothies"],
    ["Frosting", "Icing"],
    ["Doughnut", "Donut"],
    ["Yogurt", "Yoghurt"],
    ["Cookies and Cream", "Cookies & Cream", "Cookies N Cream", "Cookies 'N Cream"],
    ["Salt and Vinegar", "Salt & Vinegar", "Salt N Vinegar"],
    ["Peanut Butter and Jelly", "Peanut Butter & Jelly", "PB&J", "PB and J"],
    ["Mac and Cheese", "Mac & Cheese", "Macaroni and Cheese", "Macaroni & Cheese"],
    ["Sour Cream and Onion", "Sour Cream & Onion"],
    ["Hot and Spicy", "Hot & Spicy"],
    ["Sweet and Salty", "Sweet & Salty"],
    ["Sweet and Spicy", "Sweet & Spicy"],
    ["Garlic and Herb", "Garlic & Herb"],
    ["Salt and Pepper", "Salt & Pepper"],
    # REMOVED: Traditional from this group — Traditional sometimes means a different flavor
    ["Old Fashioned", "Old-Fashioned", "Oldfashioned"],
    ["Buttermilk", "Butter Milk"],  # one-word vs two-word
    ["100% Juice", "All Juice", "Pure Juice"],
    ["Concentrated", "Concentrate", "From Concentrate"],
    ["Ultra Filtered", "Ultra-Filtered", "Ultrafiltered", "UF"],
    ["No Salt Added", "No-Salt-Added", "Unsalted", "Salt Free"],
    ["Reduced Sodium", "Low Sodium", "Less Sodium"],  # arguable
    ["BBQ", "Barbecue", "Barbeque", "Bar-B-Que"],
    ["Tex-Mex", "Tex Mex", "TexMex"],
    # REMOVED: Mini from this group — Mini ≠ Bite Size (different size concepts)
    ["Bite Size", "Bite-Size", "Bitesize", "Bites"],
    ["Mini", "Minis", "Mini Size"],
]

# Build lookup: any-form-lower → (canonical, group_index)
SYNONYM_LOOKUP: dict[str, tuple[str, int]] = {}
for i, group in enumerate(KNOWN_SYNONYM_GROUPS):
    canonical = group[0]
    for variant in group:
        SYNONYM_LOOKUP[variant.lower()] = (canonical, i)


def main(apply_mode: bool, only_high_confidence: bool) -> None:
    # Map (parent_path, depth) -> Counter(child_segment)
    parent_children: dict[tuple[str, int], Counter] = defaultdict(Counter)
    # For provenance: parent + child → set(full paths)
    parent_child_paths: dict[tuple[str, int, str], list[str]] = defaultdict(list)
    # Same-FNDDS-cross-sibling tracking: (parent, fndds) -> Counter(child)
    parent_fndds_children: dict[tuple[str, str], Counter] = defaultdict(Counter)

    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            for col in ("canonical_path", "retail_leaf_path"):
                v = (r.get(col) or "").strip()
                if not v: continue
                segs = v.split(" > ")
                # Walk every (parent, child) at every depth ≥ 2
                for depth in range(2, len(segs)):
                    parent = " > ".join(segs[:depth])
                    child = segs[depth]
                    parent_children[(parent, depth)][child] += 1
                    if len(parent_child_paths[(parent, depth, child)]) < 5:
                        parent_child_paths[(parent, depth, child)].append(v)
                    fndds = (r.get("fndds_code") or "").strip()
                    if fndds:
                        parent_fndds_children[(parent, fndds)][child] += 1

    # Detect synonym pairs
    candidates: list[dict] = []
    for (parent, depth), child_counter in parent_children.items():
        if len(child_counter) < 2: continue
        children = list(child_counter.keys())
        # Group by canonical synonym
        by_canonical: dict[str, list[str]] = defaultdict(list)
        for c in children:
            entry = SYNONYM_LOOKUP.get(c.lower())
            if entry:
                canonical, _ = entry
                by_canonical[canonical].append(c)
        # Flag groups with 2+ siblings sharing canonical
        for canonical, siblings in by_canonical.items():
            if len(siblings) < 2: continue
            siblings_sorted = sorted(siblings, key=lambda c: -child_counter[c])
            keep = siblings_sorted[0]
            if keep.lower() != canonical.lower():
                # The most-populated variant isn't the canonical form;
                # we still rewrite to canonical for consistency
                pass
            for other in siblings_sorted[1:]:
                candidates.append({
                    "parent": parent,
                    "depth": depth,
                    "seg_a": keep,
                    "n_skus_a": child_counter[keep],
                    "seg_b": other,
                    "n_skus_b": child_counter[other],
                    "confidence": "HIGH",
                    "reason": "known-synonym",
                    "recommended_canonical": canonical,
                    "sample_a": parent_child_paths[(parent, depth, keep)][0],
                    "sample_b": parent_child_paths[(parent, depth, other)][0],
                })

    # Same-FNDDS evidence: pairs of children that BOTH receive a lot of SKUs
    # for the same FNDDS code. (medium-confidence data signal)
    for (parent, fndds), child_counter in parent_fndds_children.items():
        if len(child_counter) < 2: continue
        if sum(child_counter.values()) < 10: continue
        siblings = child_counter.most_common()
        top, top_n = siblings[0]
        for other, other_n in siblings[1:]:
            if other_n < 5: break
            # Already flagged as known synonym → skip
            entry_top = SYNONYM_LOOKUP.get(top.lower())
            entry_oth = SYNONYM_LOOKUP.get(other.lower())
            if entry_top and entry_oth and entry_top[1] == entry_oth[1]:
                continue
            # Don't flag clearly-different concepts (e.g., Cheddar vs Mozzarella)
            # Filter: at least one child should be a tail facet or string variant
            if len(top.split()) > 3 or len(other.split()) > 3:
                continue
            candidates.append({
                "parent": parent,
                "depth": -1,
                "seg_a": top,
                "n_skus_a": top_n,
                "seg_b": other,
                "n_skus_b": other_n,
                "confidence": "MEDIUM",
                "reason": f"same-fndds-{fndds}",
                "recommended_canonical": top,
                "sample_a": "",
                "sample_b": "",
            })

    # Dedupe (parent, seg_a, seg_b) keeping highest-confidence
    seen: dict[tuple[str, str, str], dict] = {}
    rank = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
    for c in candidates:
        a, b = sorted([c["seg_a"], c["seg_b"]])
        k = (c["parent"], a, b)
        if k not in seen or rank[c["confidence"]] > rank[seen[k]["confidence"]]:
            seen[k] = c
    candidates = list(seen.values())
    candidates.sort(key=lambda r: (-rank[r["confidence"]], -(r["n_skus_a"] + r["n_skus_b"])))

    cols = ["parent", "depth", "seg_a", "n_skus_a", "seg_b", "n_skus_b",
            "confidence", "reason", "recommended_canonical",
            "sample_a", "sample_b"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(candidates)

    n_high = sum(1 for c in candidates if c["confidence"] == "HIGH")
    n_med = sum(1 for c in candidates if c["confidence"] == "MEDIUM")
    print(f"  candidates total: {len(candidates):,}")
    print(f"    HIGH (known-synonym): {n_high:,}")
    print(f"    MEDIUM (same-fndds) : {n_med:,}")
    print(f"  wrote {OUT.name}")
    print()
    print("=" * 90)
    print("TOP 30 HIGH-CONFIDENCE SYNONYM PAIRS")
    print("=" * 90)
    for c in [x for x in candidates if x["confidence"] == "HIGH"][:30]:
        print(f"\n  parent='{c['parent']}'  depth={c['depth']}")
        print(f"    a={c['seg_a']:<22} ({c['n_skus_a']:>4} SKUs)")
        print(f"    b={c['seg_b']:<22} ({c['n_skus_b']:>4} SKUs)")
        print(f"    → unify to: {c['recommended_canonical']}")
        print(f"    sample_b: {c['sample_b']}")

    if not apply_mode:
        return

    # APPLY: rewrite per row, only HIGH-confidence rules
    print()
    print("=" * 90)
    print(f"APPLYING {n_high} HIGH-CONFIDENCE rewrites...")
    print("=" * 90)

    # Build rewrite map: (parent, depth, old_seg) → new_seg
    rewrite: dict[tuple[str, int, str], str] = {}
    for c in candidates:
        if c["confidence"] != "HIGH": continue
        canonical = c["recommended_canonical"]
        for seg in (c["seg_a"], c["seg_b"]):
            if seg.lower() == canonical.lower(): continue
            rewrite[(c["parent"], c["depth"], seg)] = canonical

    tmp = AUDIT.with_suffix(".tmp.csv")
    log_rows: list[dict] = []
    n_rows_changed = 0
    with AUDIT.open(encoding="utf-8", newline="") as fin, \
         tmp.open("w", encoding="utf-8", newline="") as fout:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
        wtr.writeheader()
        for r in rdr:
            old_cp = r.get("canonical_path", "") or ""
            old_rlp = r.get("retail_leaf_path", "") or ""
            new_cp = apply_rewrite(old_cp, rewrite)
            new_rlp = apply_rewrite(old_rlp, rewrite)
            if new_cp != old_cp or new_rlp != old_rlp:
                n_rows_changed += 1
                r["canonical_path"] = new_cp
                r["retail_leaf_path"] = new_rlp
                if len(log_rows) < 20000:
                    log_rows.append({
                        "fdc_id": r.get("fdc_id", ""),
                        "old_cp": old_cp, "new_cp": new_cp,
                        "old_rlp": old_rlp, "new_rlp": new_rlp,
                    })
            wtr.writerow(r)
    shutil.move(str(tmp), str(AUDIT))
    print(f"  rows changed: {n_rows_changed:,}")
    if log_rows:
        cols = list(log_rows[0].keys())
        with LOG.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"  wrote {LOG.name}")


def apply_rewrite(path: str, rewrite: dict) -> str:
    if not path: return path
    segs = path.split(" > ")
    new_segs = list(segs)
    for depth in range(2, len(segs)):
        parent = " > ".join(new_segs[:depth])
        old_seg = new_segs[depth]
        canonical = rewrite.get((parent, depth, old_seg))
        if canonical:
            new_segs[depth] = canonical
    # Dedupe consecutive
    out = []
    for s in new_segs:
        if not out or out[-1].lower() != s.lower():
            out.append(s)
    return " > ".join(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Apply HIGH-confidence rewrites")
    p.add_argument("--medium", action="store_true", help="Also include MEDIUM in apply (default: HIGH only)")
    args = p.parse_args()
    main(args.apply, only_high_confidence=not args.medium)
