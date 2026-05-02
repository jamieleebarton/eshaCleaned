#!/usr/bin/env python3
"""Consolidate cosmetic path duplicates directly in full_corpus_audit.csv.

Rules:
  - "Pre Sliced" / "Pre-Sliced" / "Presliced" → "Sliced"
  - If both ".. > Sliced > Pre Sliced" appears, collapse to ".. > Sliced"
  - Same for any alias map below — extend as needed.

Read-only: just rewrites canonical_path column in-place.
"""
from __future__ import annotations

import csv
import re
import sys
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
AUDIT = V2 / "full_corpus_audit.csv"

csv.field_size_limit(sys.maxsize)

# Cosmetic-equivalence aliases — left side becomes right side everywhere
# they appear as a path segment (case-insensitive match on segment text).
SEGMENT_ALIASES: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bpre[\s-]?sliced\b', re.I), "Sliced"),
    (re.compile(r'\bpre[\s-]?sliced bagels\b', re.I), "Sliced"),
    (re.compile(r'\bpre[\s-]?cooked\b', re.I), "Cooked"),
    (re.compile(r'\bready[\s-]?to[\s-]?eat\b', re.I), "Ready to Eat"),
]

# Whole-grain-style redundancies. When the parent already implies whole-grain,
# a "Whole Grain" child is noise — drop it. Same for multigrain when parent is
# specific (12 Grain, 9 Grain, etc.).
# Set of segments that already imply "whole grain"
WG_PARENT_NAMES = {
    "whole wheat", "whole grain", "12 grain", "9 grain", "7 grain",
    "five grain", "multigrain", "seven grain", "nine grain",
    "5 grain", "ten grain", "10 grain",
}
# Set of "redundant child" segments to drop when parent implies whole-grain
WG_REDUNDANT_CHILDREN = {"whole grain", "multigrain", "whole wheat"}


def consolidate(path: str) -> str:
    if not path:
        return path
    segs = [s.strip() for s in path.split(">") if s.strip()]
    # First pass: cosmetic alias replacement
    pass1: list[str] = []
    for seg in segs:
        new_seg = seg
        for pat, repl in SEGMENT_ALIASES:
            if pat.fullmatch(new_seg) or pat.search(new_seg):
                new_seg = pat.sub(repl, new_seg).strip()
        pass1.append(new_seg)

    # Second pass: drop whole-grain-redundant children
    # AND drop leaves that just repeat the parent
    pass2: list[str] = []
    for seg in pass1:
        seg_lower = seg.lower()
        # Rule A: if parent already implies whole-grain and this seg is
        # a redundant whole-grain marker, drop it.
        if pass2 and pass2[-1].lower() in WG_PARENT_NAMES \
           and seg_lower in WG_REDUNDANT_CHILDREN:
            continue
        # Rule B was too aggressive — it stripped legitimate compound names
        # like "Candy Corn" → "Corn" and "Pasta Salad" → "Salad". Disabled.
        # The WG-redundant-children rule (Rule A above) is targeted enough.
        # Rule C: drop immediate duplicate
        if pass2 and pass2[-1].lower() == seg_lower:
            continue
        pass2.append(seg)
    return " > ".join(pass2)


def main() -> None:
    if not AUDIT.exists():
        raise SystemExit(f"missing {AUDIT}")

    tmp = AUDIT.with_suffix(".consolidating.csv")
    n_total = 0
    n_changed = 0
    changed_examples: list[tuple[str, str, str]] = []
    with AUDIT.open(encoding="utf-8", newline="") as fin, \
         tmp.open("w", encoding="utf-8", newline="") as fout:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
        wtr.writeheader()
        for r in rdr:
            n_total += 1
            old = r.get("canonical_path", "")
            new = consolidate(old)
            if new != old:
                n_changed += 1
                if len(changed_examples) < 8:
                    changed_examples.append((r.get("title", "")[:50], old, new))
                r["canonical_path"] = new
            wtr.writerow(r)

    # Atomic replace
    shutil.move(str(tmp), str(AUDIT))
    print(f"  rows scanned: {n_total:,}")
    print(f"  rows changed: {n_changed:,}")
    print()
    print("=== Sample consolidations ===")
    for title, old, new in changed_examples:
        print(f"  {title}")
        print(f"    OLD: {old}")
        print(f"    NEW: {new}")


if __name__ == "__main__":
    main()
