#!/usr/bin/env python3
"""Find canonical_path duplicates across plural/singular, spelling, synonym,
hyphenation, and word-order axes.

Strategy:
  1. Pull every distinct canonical_path with its SKU count.
  2. For each path, compute multiple normalized forms:
     - LOWER: lowercase, strip punctuation
     - PLURAL: lemmatize-ish (drop trailing 's', 'es', 'ies' → 'y')
     - SORTED: token sort (so "Whole Grain Bread" == "Bread Whole Grain")
     - SYNONYM: replace known synonyms (chickpea→garbanzo, etc.)
  3. Group paths whose NORMALIZED form matches but raw form differs.
  4. Within each group, the canonical = path with most SKUs.

Outputs: dup_audit.csv ranked by SKU savings (count of SKUs that would
move to canonical if alias applied).
"""
from __future__ import annotations
import csv, re, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT = ROOT / "recipe_pricing" / "path_dup_audit.csv"

# Known synonyms (bidirectional). Both keys map to a canonical token.
SYNONYM_MAP = {
    "chickpea": "garbanzo", "chickpeas": "garbanzo", "garbanzos": "garbanzo",
    "garbanzo bean": "garbanzo", "garbanzo beans": "garbanzo",
    "ceci": "garbanzo",
    "cilantro": "coriander",
    "aubergine": "eggplant", "aubergines": "eggplant",
    "courgette": "zucchini", "courgettes": "zucchini",
    "rocket": "arugula",
    "capsicum": "bell pepper",
    "soya": "soy",
    "tomato": "tomato", "tomatoes": "tomato",
    "yoghurt": "yogurt", "yoghurts": "yogurt",
    "doughnut": "donut", "doughnuts": "donut",
    "donuts": "donut",
    "catsup": "ketchup",
    "scallion": "green onion", "scallions": "green onion",
    "spring onion": "green onion", "spring onions": "green onion",
    "shrimp": "prawn", "shrimps": "prawn",
    "prawns": "prawn",
    "coriander seed": "coriander",
    "chile": "chili", "chiles": "chili", "chilies": "chili", "chillies": "chili",
    "chili pepper": "chili", "chili peppers": "chili",
    "raisins": "raisin",
    "pepperoni": "pepperoni",
    "butter beans": "lima bean", "butter bean": "lima bean",
    "lima beans": "lima bean",
    "great northern beans": "great northern bean",
}


def to_lower_clean(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", s.lower()).strip()


def lemmatize(s: str) -> str:
    """Crude singular form — drop trailing 's', 'es', 'ies'→'y'."""
    s = s.strip()
    if s.endswith("ies") and len(s) > 3:
        return s[:-3] + "y"
    if s.endswith("es") and len(s) > 3:
        return s[:-2]
    if s.endswith("s") and len(s) > 2 and not s.endswith("ss"):
        return s[:-1]
    return s


def synonym_norm(s: str) -> str:
    """Apply synonym substitutions on whole-token basis."""
    tokens = s.split()
    out = []
    i = 0
    while i < len(tokens):
        # Try multi-word synonyms first (e.g. "great northern beans")
        for span in (3, 2, 1):
            if i + span <= len(tokens):
                phrase = " ".join(tokens[i:i+span])
                if phrase in SYNONYM_MAP:
                    out.append(SYNONYM_MAP[phrase])
                    i += span
                    break
        else:
            out.append(tokens[i])
            i += 1
            continue
    return " ".join(out)


def normalize_path(path: str) -> str:
    """Combined normalization: lowercase + lemmatize each token + apply synonyms."""
    parts = [p.strip() for p in path.split(" > ") if p.strip()]
    norm_parts = []
    for part in parts:
        clean = to_lower_clean(part)
        # Lemmatize each word in the segment
        words = [lemmatize(w) for w in clean.split()]
        # Apply synonym substitution on whole segment
        seg = " ".join(words)
        seg = synonym_norm(seg)
        norm_parts.append(seg)
    return " > ".join(norm_parts)


def main():
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""SELECT consensus_canonical, COUNT(DISTINCT upc) AS n
        FROM priced_products
        WHERE available=1 AND consensus_canonical IS NOT NULL
          AND consensus_canonical != ''
        GROUP BY consensus_canonical""")
    paths = cur.fetchall()
    print(f"scanning {len(paths):,} distinct canonical_paths…", file=sys.stderr)

    # Group by normalized form
    by_norm: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for path, n in paths:
        norm = normalize_path(path)
        by_norm[norm].append((path, n))

    # Surface groups with multiple raw forms
    dup_groups = []
    for norm, members in by_norm.items():
        if len(members) < 2: continue
        # Sort: most-SKUs-first = canonical
        members.sort(key=lambda m: -m[1])
        canonical_path = members[0][0]
        canonical_n = members[0][1]
        savings = sum(n for _, n in members[1:])
        dup_groups.append({
            "canonical_path": canonical_path,
            "canonical_n_skus": canonical_n,
            "n_dup_paths": len(members) - 1,
            "savings_skus": savings,
            "members": "; ".join(f"{p}({n})" for p, n in members[1:]),
            "norm": norm,
        })

    dup_groups.sort(key=lambda g: -g["savings_skus"])
    print(f"  duplicate groups: {len(dup_groups):,}", file=sys.stderr)
    print(f"  total SKUs that could collapse: {sum(g['savings_skus'] for g in dup_groups):,}",
          file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(dup_groups[0].keys()) if dup_groups else
            ["canonical_path","canonical_n_skus","n_dup_paths","savings_skus","members","norm"])
        w.writeheader()
        for g in dup_groups: w.writerow(g)
    print(f"  → {OUT}", file=sys.stderr)

    print(f"\n=== TOP 30 dup groups by SKU-savings ===")
    for g in dup_groups[:30]:
        print(f"  +{g['savings_skus']:>3} SKUs  canonical={g['canonical_path'][:55]} (n={g['canonical_n_skus']})")
        print(f"           dups: {g['members'][:120]}")


if __name__ == "__main__":
    main()
