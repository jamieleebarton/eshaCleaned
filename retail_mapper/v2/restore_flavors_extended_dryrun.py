#!/usr/bin/env python3
"""DRY-RUN: extend flavor restoration to more families.

Reports what WOULD change, per family, with 20 samples each. Writes nothing.

Run apply mode with `--apply` flag to actually update the audit.
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
LOG = V2 / "restore_flavors_extended_log.csv"
FNDDS_DESC = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/data/fndds/MainFoodDesc16.csv")

csv.field_size_limit(sys.maxsize)

# Extended target list
TARGET_PARENTS = [
    "Dairy > Yogurt", "Dairy > Milk", "Dairy > Flavored Milk", "Dairy > Pudding",
    "Frozen > Ice Cream", "Frozen > Frozen Yogurt", "Frozen > Sorbet",
    "Snack > Cookies", "Snack > Chips", "Snack > Bars", "Snack > Candy",
    "Snack > Chocolate Candy", "Snack > Granola", "Snack > Crackers",
    "Beverage > Soda", "Beverage > Carbonated", "Beverage > Lemonade",
    "Beverage > Juice", "Beverage > Tea", "Beverage > Sparkling Water",
    "Beverage > Energy Drinks", "Beverage > Sports Drinks",
    "Pantry > Cereal", "Pantry > Sweeteners",
    "Bakery > Cake", "Bakery > Cupcakes", "Bakery > Doughnuts", "Bakery > Brownies",
    "Bakery > Muffins", "Bakery > Pie",
]

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
    "Root Beer", "Cola", "Cream Soda", "Ginger Ale", "Ginger Beer",
    "Cranberry", "Pomegranate", "Acai", "Guava", "Lychee",
    "Sour Apple", "Sour Cherry", "Sour Watermelon",
    "Plain", "Original",
]
KNOWN_FLAVORS = sorted(KNOWN_FLAVORS, key=lambda s: -len(s))
FLAVOR_RX = re.compile(r"\b(" + "|".join(re.escape(f) for f in KNOWN_FLAVORS) + r")\b", re.I)


def extract_flavor(desc: str) -> str | None:
    if not desc: return None
    upper = desc.upper()
    if "NFS" in upper or "NS AS TO" in upper:
        return None
    matches = FLAVOR_RX.findall(desc)
    if not matches: return None
    seen = []
    for m in matches:
        canonical = next((f for f in KNOWN_FLAVORS if f.lower() == m.lower()), m.title())
        if canonical not in seen:
            seen.append(canonical)
    return seen[0] if seen else None


# Family-consistency: if the FNDDS desc starts with a wrong family, reject.
# Maps a flavor's typical FNDDS-desc prefix → the canonical family root the
# SKU should be in. If path's top-2 segments don't match, reject.
FNDDS_FAMILY_GUARDS = [
    # (regex on fndds_desc, expected_family_prefix)
    (re.compile(r"\bsoft drink\b|\bsoda\b|\bcola\b|\bginger ale\b|\bginger beer\b|\broot beer\b", re.I),
     ("Beverage > Soda", "Beverage > Carbonated", "Beverage > Sparkling Water")),
    (re.compile(r"\bjuice\b", re.I), ("Beverage > Juice", "Beverage > Lemonade")),
    (re.compile(r"\btea\b", re.I), ("Beverage > Tea",)),
    (re.compile(r"\byogurt\b", re.I), ("Dairy > Yogurt", "Frozen > Frozen Yogurt")),
    (re.compile(r"\bice cream\b|\bsorbet\b|\bgelato\b", re.I), ("Frozen > Ice Cream", "Frozen > Sorbet")),
    (re.compile(r"\bcookie\b|\bbiscuit\b", re.I), ("Snack > Cookies", "Bakery > Cookies")),
    (re.compile(r"\bcandy\b|\bjelly bean\b|\bgumdrop\b|\bgum\b", re.I), ("Snack > Candy", "Snack > Chocolate Candy")),
    (re.compile(r"\bchocolate\b", re.I), ("Snack > Candy", "Snack > Chocolate Candy", "Bakery > Cake", "Bakery > Brownies", "Frozen > Ice Cream")),
    (re.compile(r"\bsnack bar\b|\benergy bar\b|\bprotein bar\b|\bgranola bar\b|\bcereal bar\b", re.I),
     ("Snack > Bars",)),
    (re.compile(r"\bchips\b|\bpotato chips\b|\btortilla chips\b", re.I), ("Snack > Chips",)),
    (re.compile(r"\bcake\b|\bcupcake\b", re.I), ("Bakery > Cake", "Bakery > Cupcakes")),
    (re.compile(r"\bbrownie\b", re.I), ("Bakery > Brownies",)),
    (re.compile(r"\bdoughnut\b|\bdonut\b", re.I), ("Bakery > Doughnuts",)),
    (re.compile(r"\bmuffin\b", re.I), ("Bakery > Muffins",)),
    (re.compile(r"\bpie\b", re.I), ("Bakery > Pie",)),
    (re.compile(r"\bcereal\b", re.I), ("Pantry > Cereal",)),
    (re.compile(r"\bpudding\b", re.I), ("Dairy > Pudding",)),
    (re.compile(r"\bmilk\b(?!.*chocolate)", re.I), ("Dairy > Milk", "Dairy > Flavored Milk", "Beverage > Plant Milk")),
]


def fndds_family_matches_path(desc: str, path: str) -> bool:
    """Return False if FNDDS desc names a clearly different family than path's top-2 segments."""
    desc_lower = desc.lower()
    for rx, allowed_prefixes in FNDDS_FAMILY_GUARDS:
        if rx.search(desc_lower):
            return any(path.startswith(p) for p in allowed_prefixes)
    # No guard for this desc → allow
    return True


def flavor_substring_in_path(flavor: str, path: str) -> bool:
    """Return True if flavor word appears as substring in any path segment.
    'Lemon' inside 'Lemonade' → True."""
    flavor_lower = flavor.lower()
    for seg in path.split(" > "):
        if flavor_lower in seg.lower():
            return True
    return False


def flavor_headword_already_in_path(flavor: str, path: str) -> bool:
    """Skip if the flavor's headword (rightmost word) is already a segment.
    'Milk Chocolate' → headword 'chocolate'. If path has 'Chocolate' segment → skip.
    """
    words = flavor.lower().split()
    if not words: return False
    headword = words[-1]
    path_segs_lower = {s.lower() for s in path.split(" > ")}
    # If only one word in flavor, the substring check already handled this
    if len(words) == 1: return False
    return headword in path_segs_lower


def main(apply_mode: bool) -> None:
    desc_by_code: dict[str, str] = {}
    if FNDDS_DESC.exists():
        with FNDDS_DESC.open(encoding="utf-8") as fh:
            for row in csv.reader(fh):
                if len(row) >= 2 and row[0].strip().isdigit():
                    desc_by_code[row[0].strip()] = row[1].strip()
    print(f"  loaded {len(desc_by_code):,} FNDDS descriptions")
    print(f"  mode: {'APPLY' if apply_mode else 'DRY-RUN'}")

    # Buckets per parent
    proposed: dict[str, list[dict]] = defaultdict(list)
    n_total = 0
    n_skipped_already = 0
    n_skipped_no_flavor = 0

    if apply_mode:
        tmp = AUDIT.with_suffix(".tmp.csv")
        fout = tmp.open("w", encoding="utf-8", newline="")
    else:
        fout = None
    log_rows: list[dict] = []

    with AUDIT.open(encoding="utf-8", newline="") as fin:
        rdr = csv.DictReader(fin)
        wtr = None
        if fout:
            wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
            wtr.writeheader()
        for r in rdr:
            n_total += 1
            cp = (r.get("canonical_path") or "").strip()
            matched_parent = next((p for p in TARGET_PARENTS if cp.startswith(p)), None)
            if not matched_parent:
                if wtr: wtr.writerow(r)
                continue
            code = (r.get("fndds_code") or "").strip()
            desc = (r.get("fndds_desc") or "").strip() or desc_by_code.get(code, "")
            # Family-consistency guard: if FNDDS desc names a different family, skip
            if desc and not fndds_family_matches_path(desc, cp):
                n_skipped_no_flavor += 1
                if wtr: wtr.writerow(r)
                continue
            flavor = extract_flavor(desc)
            # NOTE: removed modifier-fallback (caused false-positive flavors)
            if not flavor:
                n_skipped_no_flavor += 1
                if wtr: wtr.writerow(r)
                continue
            # Substring check: 'Lemon' inside 'Lemonade' should skip
            if flavor_substring_in_path(flavor, cp):
                n_skipped_already += 1
                if wtr: wtr.writerow(r)
                continue
            # Headword check: 'Milk Chocolate' when 'Chocolate' is already a parent → skip
            if flavor_headword_already_in_path(flavor, cp):
                n_skipped_already += 1
                if wtr: wtr.writerow(r)
                continue
            # TITLE-EVIDENCE check: flavor must also appear in the title
            # (independent confirmation; defends against bad FNDDS codes)
            title = (r.get("title") or "").lower()
            flavor_words = flavor.lower().split()
            # Require ALL flavor words present in title (handles "Milk Chocolate", "Salted Caramel", etc.)
            if not all(re.search(rf"\b{re.escape(w)}\b", title) for w in flavor_words):
                n_skipped_no_flavor += 1
                if wtr: wtr.writerow(r)
                continue
            old_cp = cp
            old_rlp = (r.get("retail_leaf_path") or "").strip()
            new_cp = old_cp + " > " + flavor
            new_rlp = old_rlp
            if old_rlp.startswith(matched_parent):
                rlp_lower = {s.lower() for s in old_rlp.split(" > ")}
                if flavor.lower() not in rlp_lower:
                    new_rlp = old_rlp + " > " + flavor
            proposed[matched_parent].append({
                "fdc_id": r.get("fdc_id", ""),
                "title": (r.get("title", "") or "")[:60],
                "fndds_code": code, "fndds_desc": desc,
                "flavor": flavor,
                "old_cp": old_cp, "new_cp": new_cp,
            })
            if apply_mode:
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
            if wtr: wtr.writerow(r)

    if fout:
        fout.close()
        shutil.move(str(tmp), str(AUDIT))
        if log_rows:
            cols = list(log_rows[0].keys())
            with LOG.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=cols)
                w.writeheader()
                w.writerows(log_rows)
            print(f"  wrote {LOG.name}")

    n_proposed = sum(len(v) for v in proposed.values())
    print(f"\n  rows scanned                : {n_total:,}")
    print(f"  proposed flavor appends     : {n_proposed:,}")
    print(f"  skipped — already had flavor: {n_skipped_already:,}")
    print(f"  skipped — no flavor in FNDDS: {n_skipped_no_flavor:,}")
    print()
    print(f"  Per family proposed counts:")
    for parent in sorted(proposed, key=lambda k: -len(proposed[k])):
        print(f"    {parent:<35} {len(proposed[parent]):>5}")

    print()
    print("=" * 90)
    print(f"DRY-RUN SAMPLES — 10 per family (showing what WOULD be appended)")
    print("=" * 90)
    for parent in sorted(proposed, key=lambda k: -len(proposed[k])):
        rows = proposed[parent]
        if not rows: continue
        print(f"\n  --- {parent}  ({len(rows)} proposed) ---")
        for r in rows[:10]:
            print(f"    fdc={r['fdc_id']:>10}  flavor={r['flavor']:<22}  fndds=({r['fndds_desc'][:50]})")
            print(f"      OLD: {r['old_cp']}")
            print(f"      NEW: {r['new_cp']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Actually write changes (default is dry-run)")
    args = p.parse_args()
    main(args.apply)
