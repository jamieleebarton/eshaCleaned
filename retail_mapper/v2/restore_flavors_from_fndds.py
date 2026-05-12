#!/usr/bin/env python3
"""For SKUs whose path is missing the flavor that FNDDS encodes, append the flavor.

Example: FNDDS 11410025 = 'strawberry yogurt'. SKUs with this code at path
'Dairy > Yogurt > Low Fat' should land at 'Dairy > Yogurt > Low Fat > Strawberry'.

Approach: parse FNDDS description for known flavor words. If the path doesn't
already include that flavor, append it as the leaf segment.

Operates on yogurt + milk + ice cream + pudding (the families where FNDDS-encoded
flavors are most common). Skips bare-FNDDS-NFS codes (no flavor information).
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
LOG = V2 / "restore_flavors_log.csv"
FNDDS_DESC = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/data/fndds/MainFoodDesc16.csv")

csv.field_size_limit(sys.maxsize)

# Family → set of canonical_path roots to operate on
TARGET_PARENTS = [
    "Dairy > Yogurt", "Dairy > Milk", "Dairy > Flavored Milk", "Dairy > Pudding",
    "Frozen > Ice Cream", "Frozen > Frozen Yogurt",
]

# Flavor words we'll extract from FNDDS descriptions
KNOWN_FLAVORS = [
    "Strawberry", "Blueberry", "Raspberry", "Blackberry", "Cherry", "Black Cherry",
    "Vanilla", "Vanilla Bean", "French Vanilla",
    "Chocolate", "Dark Chocolate", "Milk Chocolate", "White Chocolate",
    "Banana", "Peach", "Pineapple", "Mango", "Coconut", "Apple", "Pear", "Plum",
    "Lemon", "Lime", "Orange", "Grape", "Pomegranate", "Watermelon", "Melon",
    "Cantaloupe", "Honeydew", "Apricot", "Kiwi", "Papaya", "Passion Fruit",
    "Pumpkin", "Pumpkin Spice", "Cinnamon", "Caramel", "Maple", "Honey",
    "Coffee", "Espresso", "Mocha", "Latte", "Cappuccino",
    "Mint", "Peppermint", "Spearmint", "Wintergreen",
    "Almond", "Hazelnut", "Pistachio", "Walnut", "Pecan", "Cashew", "Macadamia",
    "Peanut Butter", "Almond Butter",
    "Cookies and Cream", "Cookie Dough", "Cookies",
    "Birthday Cake", "Cheesecake", "Pumpkin Pie", "Apple Pie", "Pecan Pie",
    "Key Lime", "Strawberry Banana", "Strawberry Cheesecake",
    "Toasted Coconut", "Salted Caramel", "Sea Salt Caramel",
    "Rocky Road", "Neapolitan", "Tutti Frutti",
    "Plain", "Original",
]
# Sort longest-first for greedy multi-word match
KNOWN_FLAVORS = sorted(KNOWN_FLAVORS, key=lambda s: -len(s))
FLAVOR_RX = re.compile(r"\b(" + "|".join(re.escape(f) for f in KNOWN_FLAVORS) + r")\b", re.I)


def extract_flavor(desc: str) -> str | None:
    """Pull the dominant flavor word(s) from an FNDDS description."""
    if not desc: return None
    # Reject NFS / NS-AS-TO catch-all codes (no specific flavor)
    upper = desc.upper()
    if "NFS" in upper or "NS AS TO" in upper:
        return None
    matches = FLAVOR_RX.findall(desc)
    if not matches: return None
    # Title-case each match for canonical form
    seen = []
    for m in matches:
        # Find which entry of KNOWN_FLAVORS this matches (case-insensitive)
        canonical = next((f for f in KNOWN_FLAVORS if f.lower() == m.lower()), m.title())
        if canonical not in seen:
            seen.append(canonical)
    return seen[0] if seen else None  # return first found (longest greedy)


def main() -> None:
    # Load FNDDS desc map
    desc_by_code: dict[str, str] = {}
    if FNDDS_DESC.exists():
        with FNDDS_DESC.open(encoding="utf-8") as fh:
            for row in csv.reader(fh):
                if len(row) >= 2 and row[0].strip().isdigit():
                    desc_by_code[row[0].strip()] = row[1].strip()
    print(f"  loaded {len(desc_by_code):,} FNDDS descriptions")

    tmp = AUDIT.with_suffix(".tmp.csv")
    log_rows: list[dict] = []
    n_changed = 0
    n_skipped_no_flavor = 0
    n_skipped_already_has = 0

    with AUDIT.open(encoding="utf-8", newline="") as fin, \
         tmp.open("w", encoding="utf-8", newline="") as fout:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
        wtr.writeheader()
        for r in rdr:
            cp = (r.get("canonical_path") or "").strip()
            if not any(cp.startswith(p) for p in TARGET_PARENTS):
                wtr.writerow(r); continue
            code = (r.get("fndds_code") or "").strip()
            # Prefer the audit-row's own fndds_desc column (newer codes not in MainFoodDesc16)
            desc = (r.get("fndds_desc") or "").strip() or desc_by_code.get(code, "")
            flavor = extract_flavor(desc)
            if not flavor:
                # Try the modifier column too (sometimes has the flavor)
                mod_text = (r.get("modifier") or "")
                flavor = extract_flavor(mod_text) if mod_text else None
            if not flavor:
                n_skipped_no_flavor += 1
                wtr.writerow(r); continue
            # Skip if path already mentions this flavor (case-insensitive segment match)
            cp_lower_segs = {s.lower() for s in cp.split(" > ")}
            if flavor.lower() in cp_lower_segs:
                n_skipped_already_has += 1
                wtr.writerow(r); continue
            # Append flavor as leaf
            old_cp = cp
            old_rlp = (r.get("retail_leaf_path") or "").strip()
            new_cp = old_cp + " > " + flavor
            new_rlp = old_rlp
            # Only update rlp if it doesn't already mention the flavor
            if old_rlp and any(old_rlp.startswith(p) for p in TARGET_PARENTS):
                rlp_lower_segs = {s.lower() for s in old_rlp.split(" > ")}
                if flavor.lower() not in rlp_lower_segs:
                    new_rlp = old_rlp + " > " + flavor
            n_changed += 1
            r["canonical_path"] = new_cp
            r["retail_leaf_path"] = new_rlp
            log_rows.append({
                "fdc_id": r.get("fdc_id", ""),
                "title": (r.get("title", "") or "")[:60],
                "fndds_code": code, "fndds_desc": desc,
                "flavor": flavor,
                "old_cp": old_cp, "new_cp": new_cp,
                "old_rlp": old_rlp, "new_rlp": new_rlp,
            })
            wtr.writerow(r)

    shutil.move(str(tmp), str(AUDIT))
    print(f"  rows updated (flavor appended): {n_changed:,}")
    print(f"  skipped — no flavor in FNDDS  : {n_skipped_no_flavor:,}")
    print(f"  skipped — already has flavor  : {n_skipped_already_has:,}")

    if log_rows:
        cols = list(log_rows[0].keys())
        with LOG.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"  wrote {LOG.name}")

    # Verify the user's 3 examples
    print()
    print("=== verify the 3 cited SKUs ===")
    target = {"1895371", "2467399", "1854046"}
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("fdc_id") in target:
                print(f"  fdc={r['fdc_id']} title=\"{(r.get('title') or '')[:50]}\"")
                print(f"    cp : {r.get('canonical_path','')}")


if __name__ == "__main__":
    main()
