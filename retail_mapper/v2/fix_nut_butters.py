#!/usr/bin/env python3
"""Move nut butters out of Dairy > Butter into Pantry > Nut Butters.

Problem: nut butters (peanut, almond, cashew, sunflower, hazelnut, macadamia,
pecan, walnut, pistachio, mixed nut, tahini) are trapped under Dairy > Butter
in BOTH canonical_path and retail_leaf_path. ~2,486 SKUs.

Detection: a SKU is a nut-butter when retail_leaf_path starts with
'Dairy > Butter' AND title or retail_leaf_path mentions a nut-butter word.

Fix:
  - canonical_path  → Pantry > Nut Butters > {Nut} Butter
  - retail_leaf_path → Pantry > Nut Butters > {Nut} Butter > {original tail}
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
LOG = V2 / "fix_nut_butters_log.csv"

csv.field_size_limit(sys.maxsize)

# Order matters — most-specific first. Each entry: (regex on title+rlp, canonical-leaf segment)
NUT_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\btahini\b", re.I),                                "Tahini"),
    (re.compile(r"\bpeanut[\s-]*butter\b", re.I),                    "Peanut Butter"),
    (re.compile(r"\balmond[\s-]*butter\b", re.I),                    "Almond Butter"),
    (re.compile(r"\bcashew[\s-]*butter\b", re.I),                    "Cashew Butter"),
    (re.compile(r"\bsunflower(?:\s+seed)?[\s-]*butter\b", re.I),     "Sunflower Seed Butter"),
    (re.compile(r"\bhazelnut[\s-]*butter\b", re.I),                  "Hazelnut Butter"),
    (re.compile(r"\bmacadamia[\s-]*butter\b", re.I),                 "Macadamia Butter"),
    (re.compile(r"\bpecan[\s-]*butter\b", re.I),                     "Pecan Butter"),
    (re.compile(r"\bwalnut[\s-]*butter\b", re.I),                    "Walnut Butter"),
    (re.compile(r"\bpistachio[\s-]*butter\b", re.I),                 "Pistachio Butter"),
    (re.compile(r"\bmixed[\s-]*nut[\s-]*butter\b", re.I),            "Mixed Nut Butter"),
    (re.compile(r"\bnut\s*(?:and|&)\s*seed\s*butter\b", re.I),       "Nut and Seed Butter"),
    # bare "Almond Spread" / "Cashew Spread" lookalike fallback
    (re.compile(r"\b(peanut|almond|cashew|hazelnut)\b", re.I),       "FALLBACK"),  # filled at runtime
]

NUT_TOKEN_TO_LEAF = {
    "peanut":   "Peanut Butter",
    "almond":   "Almond Butter",
    "cashew":   "Cashew Butter",
    "hazelnut": "Hazelnut Butter",
    "sunflower":"Sunflower Seed Butter",
    "macadamia":"Macadamia Butter",
    "pecan":    "Pecan Butter",
    "walnut":   "Walnut Butter",
    "pistachio":"Pistachio Butter",
}


def detect_nut(title: str, rlp: str) -> str | None:
    """Return the canonical nut-butter leaf, or None if not a nut butter."""
    blob = f"{title}  {rlp}"
    # Try explicit "X butter" patterns first
    for rx, leaf in NUT_RULES[:-1]:  # skip fallback
        if rx.search(blob):
            return leaf
    # Fallback: bare nut name in retail_leaf_path AT THE 3RD SEGMENT
    # (e.g., "Dairy > Butter > Almond" — the "Almond" segment IS the implicit "Almond Butter")
    segs = rlp.split(" > ")
    if len(segs) >= 3 and segs[0] == "Dairy" and segs[1] == "Butter":
        third = segs[2].lower()
        for tok, leaf in NUT_TOKEN_TO_LEAF.items():
            if tok in third.split():
                return leaf
    return None


def build_new_paths(nut_leaf: str, old_rlp: str) -> tuple[str, str]:
    """Returns (new_canonical_path, new_retail_leaf_path).

    Strip 'Dairy > Butter' prefix, drop any redundant nut name in the tail.
    """
    new_canonical = f"Pantry > Nut Butters > {nut_leaf}"

    # Build retail leaf path: keep meaningful tail segments after stripping the nut header
    segs = old_rlp.split(" > ")
    # tail = everything after 'Dairy > Butter > {nut-named segment}'
    tail: list[str] = []
    if len(segs) >= 3 and segs[0] == "Dairy" and segs[1] == "Butter":
        # Drop the 3rd segment if it's the nut-name segment (e.g. "Almond Butter" or "Almond")
        third = segs[2]
        if third.lower() in (
            nut_leaf.lower(),
            nut_leaf.lower().replace(" butter", ""),  # bare "Almond"
            nut_leaf.lower().replace(" seed butter", ""),  # bare "Sunflower"
        ):
            tail = segs[3:]
        else:
            tail = segs[2:]
    new_rlp = new_canonical + (" > " + " > ".join(tail) if tail else "")

    # De-duplicate consecutive segments
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

            # Only consider SKUs trapped under Dairy > Butter (RLP)
            if not rlp.startswith("Dairy > Butter"):
                wtr.writerow(r)
                continue

            nut_leaf = detect_nut(title, rlp)
            if nut_leaf is None:
                wtr.writerow(r)
                continue

            new_cp, new_rlp = build_new_paths(nut_leaf, rlp)

            # Defensive: don't write the same value
            if new_cp == cp and new_rlp == rlp:
                wtr.writerow(r)
                continue

            n_changed += 1
            leaf_counts[nut_leaf] += 1
            log_rows.append({
                "fdc_id": r.get("fdc_id", ""),
                "title": title[:60],
                "nut_leaf": nut_leaf,
                "old_canonical": cp,
                "new_canonical": new_cp,
                "old_retail_leaf": rlp,
                "new_retail_leaf": new_rlp,
            })
            r["canonical_path"] = new_cp
            r["retail_leaf_path"] = new_rlp
            wtr.writerow(r)

    shutil.move(str(tmp), str(AUDIT))
    print(f"  total rows scanned: {n_total:,}")
    print(f"  rows updated      : {n_changed:,}")
    print(f"  per nut-butter type:")
    for leaf in sorted(leaf_counts, key=lambda k: -leaf_counts[k]):
        print(f"    {leaf:<25} {leaf_counts[leaf]:>5}")

    if log_rows:
        cols = list(log_rows[0].keys())
        with LOG.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"  wrote {LOG.name}")


if __name__ == "__main__":
    main()
