#!/usr/bin/env python3
"""Hard-pair regression eval for retail_leaf_v2.csv.

Each test case: (title_substring, expected_leaf_substring_or_predicate).
Pass = the matching row's retail_leaf contains the expected substring.

Run after the pipeline finishes:
  python eval.py
"""
from __future__ import annotations
import csv, sys
from pathlib import Path
csv.field_size_limit(sys.maxsize)

OUT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2/retail_leaf_v2.csv")

# (title-fragment, expected-leaf-substring)
CASES = [
    ("UNSWEETENED CHOCOLATE ALMONDMILK",      "Almond Milk > Chocolate Unsweetened"),
    ("HINT OF PUMPKIN SPICE",                  "Pumpkin Spice"),
    ("ORIGINAL ALMOND BEVERAGE",               "Almond Milk"),
    ("CHIPOTLE MAYO STYLE SANDWICH SPREAD",    "Mayo Sandwich Spread"),  # parser path
    ("CHIPOTLE AIOLI",                         "Aioli"),                   # minted
    ("AVOCADO OIL WITH A HINT OF LIME",        "Lime Mayo"),
    ("ORIGINAL ALMOND NOG",                    "Nog"),
    ("OAT NOG FLAVORED OATMILK",               "Nog"),
    ("PUMPKIN SPICE DAIRY FREE ALMONDMILK CR", "Pumpkin Spice"),
    ("HOT HONEY GOUDA CHEESE",                 "Cheese"),
    ("BUSH'S HOT HONEY GRILLIN",               "Beans"),     # minted
    ("BEYOND MEAT TACOS WITH SMOKY",           "Tacos"),     # combo or meal kit
    ("VANILLA ALMONDMILK YOGURT ALTERNATIVE",  "Almond Milk"),
    ("CHUNKY MONKEY",                          ""),                # any non-empty leaf is OK
    ("RED PEPPER HUMMUS",                      "Hummus"),
    ("DRIED APPLES",                           "Apple"),     # minted from category.tsv
    ("EGG NOG",                                "Nog"),
]

def find(title_frag):
    needle = title_frag.upper()
    with open(OUT) as f:
        for r in csv.DictReader(f):
            if needle in (r["title"] or "").upper():
                return r
    return None

def main():
    if not OUT.exists():
        print(f"  {OUT} not found"); return 1
    pass_n = fail_n = 0
    for frag, expect in CASES:
        r = find(frag)
        if not r:
            print(f"  ✗ NOT FOUND     {frag!r}")
            fail_n += 1; continue
        leaf = r.get("retail_leaf","")
        cf   = r.get("confidence","0")
        gap  = r.get("gap_flag","")
        if expect:
            ok = expect.lower() in leaf.lower()
        else:
            ok = bool(leaf) and gap != "True"
        flag = "✓" if ok else "✗"
        print(f"  {flag}  {frag[:35]:35s} → {leaf[:55]!r:60} cf={cf}{' GAP' if gap=='True' else ''}")
        if ok: pass_n += 1
        else:  fail_n += 1
    print(f"\n  {pass_n}/{pass_n+fail_n} passed")
    return 0 if fail_n == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
