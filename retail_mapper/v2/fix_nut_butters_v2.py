#!/usr/bin/env python3
"""Round 2: catch the nut/seed butters my first pass missed.

Cases handled this round:
  - Seed butters (Pumpkin Seed, Watermelon Seed, Sacha Inchi)
  - Soy Nut Butter / Soy Butter
  - Chickpea Butter
  - Paths where 'Butter' was stripped: 'Dairy > Butter > Nut [...]', 'Dairy > Butter > Seed [...]', 'Dairy > Butter > Mixed Nut [...]'

Plus non-nut-butter mis-routings under Dairy > Butter:
  - Cookie Butter (Speculoos) → Pantry > Spreads > Cookie Butter
  - Cocoa Butter / Cacao Butter → Pantry > Baking > Cocoa Butter
  - Coconut Oil / Flaxseed Oil → Pantry > Oil > {Coconut|Flaxseed} Oil

Operates on full_corpus_audit.csv in place. Updates BOTH canonical_path
and retail_leaf_path. Logs every change to fix_nut_butters_v2_log.csv.
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
LOG = V2 / "fix_nut_butters_v2_log.csv"

csv.field_size_limit(sys.maxsize)

# (regex on title+rlp blob, canonical-leaf, target-tree)
RULES: list[tuple[re.Pattern, str, str]] = [
    # --- seed butters ---
    (re.compile(r"\bpumpkin\s*seed[\s-]*butter\b", re.I),               "Pumpkin Seed Butter",      "Pantry > Nut Butters"),
    (re.compile(r"\bwatermelon\s*seed[\s-]*butter\b", re.I),            "Watermelon Seed Butter",   "Pantry > Nut Butters"),
    (re.compile(r"\bsacha\s*inchi[\s-]*butter\b", re.I),                "Sacha Inchi Butter",       "Pantry > Nut Butters"),
    # --- soy / chickpea ---
    (re.compile(r"\bsoy(\s*nut)?[\s-]*butter\b", re.I),                 "Soy Nut Butter",           "Pantry > Nut Butters"),
    (re.compile(r"\bchickpea[\s-]*butter\b", re.I),                     "Chickpea Butter",          "Pantry > Nut Butters"),
    # --- non-nut wrong-tree items ---
    (re.compile(r"\bcookie[\s-]*butter\b|\bspeculoos\b", re.I),         "Cookie Butter",            "Pantry > Spreads"),
    (re.compile(r"\bcocoa[\s-]*butter\b|\bcacao[\s-]*butter\b", re.I),  "Cocoa Butter",             "Pantry > Baking"),
    (re.compile(r"\bcoconut[\s-]*oil\b", re.I),                         "Coconut Oil",              "Pantry > Oil"),
    (re.compile(r"\bflax(seed)?\s*oil\b", re.I),                        "Flaxseed Oil",             "Pantry > Oil"),
]

# Path-shape rules: when title doesn't say "X butter" but the rlp segment indicates a
# nut/seed butter that lost its "Butter" word.
RLP_SEGMENT_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^Pumpkin\s+Seed\b", re.I),         "Pumpkin Seed Butter"),
    (re.compile(r"^Watermelon\s+Seed\b", re.I),      "Watermelon Seed Butter"),
    (re.compile(r"^Seed\s+Watermelon\b", re.I),      "Watermelon Seed Butter"),
    (re.compile(r"^Sacha\s+Inchi\b", re.I),          "Sacha Inchi Butter"),
    (re.compile(r"^(Mixed\s+)?Nut\b", re.I),         "Mixed Nut Butter"),
    (re.compile(r"^Seed\b", re.I),                   "Seed Butter"),
    (re.compile(r"^Soy\b", re.I),                    "Soy Nut Butter"),
    (re.compile(r"^Chickpea\b", re.I),               "Chickpea Butter"),
    (re.compile(r"^Cocoa\s+Butter\b", re.I),         "Cocoa Butter"),
    (re.compile(r"^Cacao\b", re.I),                  "Cocoa Butter"),
    (re.compile(r"^Coconut\s+Oil\b", re.I),          "Coconut Oil"),
    (re.compile(r"^Flax(seed)?\s+Oil\b", re.I),      "Flaxseed Oil"),
    (re.compile(r"^Cookie\s+Butter\b", re.I),        "Cookie Butter"),
]

# leaf → tree-prefix lookup (built from RULES)
LEAF_TO_TREE: dict[str, str] = {leaf: tree for _, leaf, tree in RULES}
LEAF_TO_TREE.update({
    "Seed Butter":            "Pantry > Nut Butters",
    "Pumpkin Seed Butter":    "Pantry > Nut Butters",
    "Watermelon Seed Butter": "Pantry > Nut Butters",
    "Sacha Inchi Butter":     "Pantry > Nut Butters",
    "Mixed Nut Butter":       "Pantry > Nut Butters",
    "Soy Nut Butter":         "Pantry > Nut Butters",
    "Chickpea Butter":        "Pantry > Nut Butters",
    "Cocoa Butter":           "Pantry > Baking",
    "Coconut Oil":            "Pantry > Oil",
    "Flaxseed Oil":           "Pantry > Oil",
    "Cookie Butter":          "Pantry > Spreads",
})


def detect(title: str, rlp: str) -> tuple[str, str] | None:
    """Returns (leaf, tree) or None."""
    blob = f"{title}  {rlp}"
    for rx, leaf, tree in RULES:
        if rx.search(blob):
            return leaf, tree
    # Fall back to RLP segment 3 inspection
    segs = rlp.split(" > ")
    if len(segs) >= 3 and segs[0] == "Dairy" and segs[1] == "Butter":
        third = segs[2]
        for rx, leaf in RLP_SEGMENT_RULES:
            if rx.match(third):
                return leaf, LEAF_TO_TREE[leaf]
    return None


def build_paths(leaf: str, tree: str, old_rlp: str) -> tuple[str, str]:
    new_canonical = f"{tree} > {leaf}"
    segs = old_rlp.split(" > ")
    tail: list[str] = []
    if len(segs) >= 3 and segs[0] == "Dairy" and segs[1] == "Butter":
        # Drop the redundant 3rd segment if it echoes the leaf
        third_lower = segs[2].lower()
        leaf_lower = leaf.lower()
        # Crude redundancy check: if any meaningful word from the leaf is in the 3rd segment, drop it
        leaf_tokens = set(re.findall(r"[a-z]+", leaf_lower))
        third_tokens = set(re.findall(r"[a-z]+", third_lower))
        if leaf_tokens & third_tokens:
            tail = segs[3:]
        else:
            tail = segs[2:]
    new_rlp = new_canonical + (" > " + " > ".join(tail) if tail else "")
    # Dedupe consecutive segments
    final = []
    for s in new_rlp.split(" > "):
        if not final or final[-1].lower() != s.lower():
            final.append(s)
    return new_canonical, " > ".join(final)


def main() -> None:
    tmp = AUDIT.with_suffix(".fixing.csv")
    log_rows: list[dict] = []
    leaf_counts: dict[str, int] = defaultdict(int)
    n_total = 0
    n_changed = 0

    with AUDIT.open(encoding="utf-8", newline="") as fin, \
         tmp.open("w", encoding="utf-8", newline="") as fout:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
        wtr.writeheader()
        for r in rdr:
            n_total += 1
            rlp = r.get("retail_leaf_path", "") or ""
            cp = r.get("canonical_path", "") or ""
            title = r.get("title", "") or ""

            if not rlp.startswith("Dairy > Butter"):
                wtr.writerow(r)
                continue

            hit = detect(title, rlp)
            if hit is None:
                wtr.writerow(r)
                continue

            leaf, tree = hit
            new_cp, new_rlp = build_paths(leaf, tree, rlp)
            if new_cp == cp and new_rlp == rlp:
                wtr.writerow(r)
                continue

            n_changed += 1
            leaf_counts[leaf] += 1
            log_rows.append({
                "fdc_id": r.get("fdc_id", ""),
                "title": title[:60],
                "leaf": leaf, "tree": tree,
                "old_canonical": cp, "new_canonical": new_cp,
                "old_retail_leaf": rlp, "new_retail_leaf": new_rlp,
            })
            r["canonical_path"] = new_cp
            r["retail_leaf_path"] = new_rlp
            wtr.writerow(r)

    shutil.move(str(tmp), str(AUDIT))
    print(f"  total rows scanned: {n_total:,}")
    print(f"  rows updated      : {n_changed:,}")
    print(f"  per leaf:")
    for leaf in sorted(leaf_counts, key=lambda k: -leaf_counts[k]):
        print(f"    {leaf:<28} {leaf_counts[leaf]:>5}")

    if log_rows:
        cols = list(log_rows[0].keys())
        with LOG.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"  wrote {LOG.name}")


if __name__ == "__main__":
    main()
