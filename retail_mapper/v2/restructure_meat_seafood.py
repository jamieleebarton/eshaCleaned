#!/usr/bin/env python3
"""Restructure the Meat & Seafood tree into clean top-down hierarchy.

Target structure:
  Meat & Seafood
    ├─ Poultry
    │    ├─ Chicken   (formerly direct 'Chicken' OR 'Chicken Breast/Wings/etc.' compounds)
    │    │    ├─ Breast / Wings / Thigh / Tenders / Nuggets / Whole / Boneless / Breaded / Plant Based
    │    └─ Turkey    (formerly 2nd-level 'Turkey')
    │         ├─ Breast / Ground / Maple Honey / Wings / Thigh / Whole / Sliced / etc.
    ├─ Beef
    ├─ Pork
    ├─ Lamb / Veal
    ├─ Sausage
    │    ├─ Italian / Pork / Beef / Chicken / Turkey / Smoked / Breakfast / Bratwurst /
    │         Chorizo / Kielbasa  (redundant 'Sausage' word stripped)
    ├─ Bacon
    ├─ Ham
    ├─ Charcuterie / Pepperoni / Cold Cuts
    ├─ Deli
    ├─ Seafood
    │    ├─ Salmon / Shrimp / Crab / Tuna / Tilapia / Cod / Lobster /
    │         Scallops / Octopus / Pollock / Calamari (consolidated)
    │    ├─ Fish (smoked, sticks, fillets)
    ├─ Patties & Burgers (kept — distinct prepared product)
    ├─ Tofu / Meat Alternatives
"""
from __future__ import annotations

import csv
import sys
import shutil
from pathlib import Path
csv.field_size_limit(sys.maxsize)
AUDIT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2/full_corpus_audit.csv")
LOG = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2/restructure_meat_seafood_log.csv")

# Apply rules in order; each is (old_prefix, new_prefix, mode='exact'|'prefix')
# Most specific first.
RULES: list[tuple[str, str, str]] = [
    # --- POULTRY: Chicken sub-segments lose redundant 'Chicken' word ---
    ("Meat & Seafood > Poultry > Chicken Breast > ",  "Meat & Seafood > Poultry > Chicken > Breast > ", "prefix"),
    ("Meat & Seafood > Poultry > Chicken Breast",     "Meat & Seafood > Poultry > Chicken > Breast",    "exact"),
    ("Meat & Seafood > Poultry > Whole Chicken > ",   "Meat & Seafood > Poultry > Chicken > Whole > ",  "prefix"),
    ("Meat & Seafood > Poultry > Whole Chicken",      "Meat & Seafood > Poultry > Chicken > Whole",     "exact"),
    ("Meat & Seafood > Poultry > Chicken Wings > ",   "Meat & Seafood > Poultry > Chicken > Wings > ",  "prefix"),
    ("Meat & Seafood > Poultry > Chicken Wings",      "Meat & Seafood > Poultry > Chicken > Wings",     "exact"),
    ("Meat & Seafood > Poultry > Chicken Tenders > ", "Meat & Seafood > Poultry > Chicken > Tenders > ","prefix"),
    ("Meat & Seafood > Poultry > Chicken Tenders",    "Meat & Seafood > Poultry > Chicken > Tenders",   "exact"),
    ("Meat & Seafood > Poultry > Chicken Thigh > ",   "Meat & Seafood > Poultry > Chicken > Thighs > ", "prefix"),
    ("Meat & Seafood > Poultry > Chicken Thigh",      "Meat & Seafood > Poultry > Chicken > Thighs",    "exact"),
    ("Meat & Seafood > Poultry > Chicken Thighs > ",  "Meat & Seafood > Poultry > Chicken > Thighs > ", "prefix"),
    ("Meat & Seafood > Poultry > Chicken Thighs",     "Meat & Seafood > Poultry > Chicken > Thighs",    "exact"),
    ("Meat & Seafood > Poultry > Chicken Nuggets > ", "Meat & Seafood > Poultry > Chicken > Nuggets > ","prefix"),
    ("Meat & Seafood > Poultry > Chicken Nuggets",    "Meat & Seafood > Poultry > Chicken > Nuggets",   "exact"),
    ("Meat & Seafood > Poultry > Chicken Drumstick > ","Meat & Seafood > Poultry > Chicken > Drumstick > ","prefix"),
    ("Meat & Seafood > Poultry > Chicken Drumstick",   "Meat & Seafood > Poultry > Chicken > Drumstick",  "exact"),
    ("Meat & Seafood > Poultry > Chicken Patties > ", "Meat & Seafood > Poultry > Chicken > Patties > ","prefix"),
    ("Meat & Seafood > Poultry > Chicken Patties",    "Meat & Seafood > Poultry > Chicken > Patties",   "exact"),
    ("Meat & Seafood > Poultry > Chicken Strips > ",  "Meat & Seafood > Poultry > Chicken > Strips > ", "prefix"),
    ("Meat & Seafood > Poultry > Chicken Strips",     "Meat & Seafood > Poultry > Chicken > Strips",    "exact"),
    ("Meat & Seafood > Poultry > Ground Chicken > ",  "Meat & Seafood > Poultry > Chicken > Ground > ", "prefix"),
    ("Meat & Seafood > Poultry > Ground Chicken",     "Meat & Seafood > Poultry > Chicken > Ground",    "exact"),

    # --- DIRECT 'Chicken' 2nd-level → Poultry > Chicken ---
    ("Meat & Seafood > Chicken > ", "Meat & Seafood > Poultry > Chicken > ", "prefix"),
    ("Meat & Seafood > Chicken",    "Meat & Seafood > Poultry > Chicken",    "exact"),

    # --- TURKEY: 2nd-level 'Turkey' → Poultry > Turkey, strip redundant 'Turkey' word ---
    ("Meat & Seafood > Turkey > Turkey Breast > ", "Meat & Seafood > Poultry > Turkey > Breast > ", "prefix"),
    ("Meat & Seafood > Turkey > Turkey Breast",    "Meat & Seafood > Poultry > Turkey > Breast",    "exact"),
    ("Meat & Seafood > Turkey > Ground Turkey > ", "Meat & Seafood > Poultry > Turkey > Ground > ", "prefix"),
    ("Meat & Seafood > Turkey > Ground Turkey",    "Meat & Seafood > Poultry > Turkey > Ground",    "exact"),
    ("Meat & Seafood > Turkey > Maple Honey Turkey > ", "Meat & Seafood > Poultry > Turkey > Maple Honey > ", "prefix"),
    ("Meat & Seafood > Turkey > Maple Honey Turkey",    "Meat & Seafood > Poultry > Turkey > Maple Honey",    "exact"),
    ("Meat & Seafood > Turkey > Whole Turkey > ", "Meat & Seafood > Poultry > Turkey > Whole > ", "prefix"),
    ("Meat & Seafood > Turkey > Whole Turkey",    "Meat & Seafood > Poultry > Turkey > Whole",    "exact"),
    ("Meat & Seafood > Turkey > Turkey Wings > ", "Meat & Seafood > Poultry > Turkey > Wings > ", "prefix"),
    ("Meat & Seafood > Turkey > Turkey Wings",    "Meat & Seafood > Poultry > Turkey > Wings",    "exact"),
    ("Meat & Seafood > Turkey > Turkey Tenderloin > ", "Meat & Seafood > Poultry > Turkey > Tenderloin > ", "prefix"),
    ("Meat & Seafood > Turkey > Turkey Tenderloin",    "Meat & Seafood > Poultry > Turkey > Tenderloin",    "exact"),
    ("Meat & Seafood > Turkey > Turkey Bacon > ", "Meat & Seafood > Poultry > Turkey > Bacon > ", "prefix"),
    ("Meat & Seafood > Turkey > Turkey Bacon",    "Meat & Seafood > Poultry > Turkey > Bacon",    "exact"),
    ("Meat & Seafood > Turkey > ", "Meat & Seafood > Poultry > Turkey > ", "prefix"),
    ("Meat & Seafood > Turkey",    "Meat & Seafood > Poultry > Turkey",    "exact"),

    # --- DUCK / OTHER POULTRY ---
    ("Meat & Seafood > Duck > ", "Meat & Seafood > Poultry > Duck > ", "prefix"),
    ("Meat & Seafood > Duck",    "Meat & Seafood > Poultry > Duck",    "exact"),
    ("Meat & Seafood > Cornish Hen > ", "Meat & Seafood > Poultry > Cornish Hen > ", "prefix"),
    ("Meat & Seafood > Cornish Hen",    "Meat & Seafood > Poultry > Cornish Hen",    "exact"),

    # --- SAUSAGE: strip redundant 'Sausage' word ---
    ("Meat & Seafood > Sausage > Italian Sausage > ", "Meat & Seafood > Sausage > Italian > ", "prefix"),
    ("Meat & Seafood > Sausage > Italian Sausage",    "Meat & Seafood > Sausage > Italian",    "exact"),
    ("Meat & Seafood > Sausage > Pork Sausage > ",    "Meat & Seafood > Sausage > Pork > ",    "prefix"),
    ("Meat & Seafood > Sausage > Pork Sausage",       "Meat & Seafood > Sausage > Pork",       "exact"),
    ("Meat & Seafood > Sausage > Beef Sausage > ",    "Meat & Seafood > Sausage > Beef > ",    "prefix"),
    ("Meat & Seafood > Sausage > Beef Sausage",       "Meat & Seafood > Sausage > Beef",       "exact"),
    ("Meat & Seafood > Sausage > Chicken Sausage > ", "Meat & Seafood > Sausage > Chicken > ", "prefix"),
    ("Meat & Seafood > Sausage > Chicken Sausage",    "Meat & Seafood > Sausage > Chicken",    "exact"),
    ("Meat & Seafood > Sausage > Turkey Sausage > ",  "Meat & Seafood > Sausage > Turkey > ",  "prefix"),
    ("Meat & Seafood > Sausage > Turkey Sausage",     "Meat & Seafood > Sausage > Turkey",     "exact"),
    ("Meat & Seafood > Sausage > Smoked Sausage > ",  "Meat & Seafood > Sausage > Smoked > ",  "prefix"),
    ("Meat & Seafood > Sausage > Smoked Sausage",     "Meat & Seafood > Sausage > Smoked",     "exact"),
    ("Meat & Seafood > Sausage > Breakfast Sausage > ","Meat & Seafood > Sausage > Breakfast > ","prefix"),
    ("Meat & Seafood > Sausage > Breakfast Sausage",   "Meat & Seafood > Sausage > Breakfast",   "exact"),
    ("Meat & Seafood > Sausage > Polish Sausage > ",  "Meat & Seafood > Sausage > Polish > ",  "prefix"),
    ("Meat & Seafood > Sausage > Polish Sausage",     "Meat & Seafood > Sausage > Polish",     "exact"),
    ("Meat & Seafood > Sausage > Andouille Sausage > ","Meat & Seafood > Sausage > Andouille > ", "prefix"),
    ("Meat & Seafood > Sausage > Andouille Sausage",   "Meat & Seafood > Sausage > Andouille",   "exact"),

    # --- SEAFOOD: consolidate 2nd-level fish/shellfish under Seafood ---
    ("Meat & Seafood > Salmon > ", "Meat & Seafood > Seafood > Salmon > ", "prefix"),
    ("Meat & Seafood > Salmon",    "Meat & Seafood > Seafood > Salmon",    "exact"),
    ("Meat & Seafood > Shrimp > ", "Meat & Seafood > Seafood > Shrimp > ", "prefix"),
    ("Meat & Seafood > Shrimp",    "Meat & Seafood > Seafood > Shrimp",    "exact"),
    ("Meat & Seafood > Crab > ",   "Meat & Seafood > Seafood > Crab > ",   "prefix"),
    ("Meat & Seafood > Crab",      "Meat & Seafood > Seafood > Crab",      "exact"),
    ("Meat & Seafood > Tuna > ",   "Meat & Seafood > Seafood > Tuna > ",   "prefix"),
    ("Meat & Seafood > Tuna",      "Meat & Seafood > Seafood > Tuna",      "exact"),
    # Merge Fish under Seafood (Fish Sticks, Fillets, Smoked Fish all keep their leaf)
    ("Meat & Seafood > Fish > ",   "Meat & Seafood > Seafood > Fish > ",   "prefix"),
    ("Meat & Seafood > Fish",      "Meat & Seafood > Seafood > Fish",      "exact"),

    # --- HAM: redundant 'Ham' word (rare) ---
    ("Meat & Seafood > Ham > Ham Slices > ", "Meat & Seafood > Ham > Sliced > ", "prefix"),
    ("Meat & Seafood > Ham > Ham Slices",    "Meat & Seafood > Ham > Sliced",    "exact"),

    # --- HOTDOG vs HOT DOGS unification ---
    ("Meat & Seafood > Hotdog > ",  "Meat & Seafood > Hot Dogs > ",  "prefix"),
    ("Meat & Seafood > Hotdog",     "Meat & Seafood > Hot Dogs",     "exact"),

    # --- COLD CUTS: 2nd-level → Deli > Cold Cuts ---
    ("Meat & Seafood > Cold Cuts > ", "Meat & Seafood > Deli > Cold Cuts > ", "prefix"),
    ("Meat & Seafood > Cold Cuts",    "Meat & Seafood > Deli > Cold Cuts",    "exact"),

    # --- PEPPERONI: 2nd-level → Charcuterie > Pepperoni ---
    ("Meat & Seafood > Pepperoni > ", "Meat & Seafood > Charcuterie > Pepperoni > ", "prefix"),
    ("Meat & Seafood > Pepperoni",    "Meat & Seafood > Charcuterie > Pepperoni",    "exact"),

    # --- 'Meat' bare 2nd-level + 'Smoked'/'Ground'/'Prepared'/'Processed' as 2nd-level ---
    # These are facets not categories. Move them under Meat & Seafood > Meat (Other) for now.
    ("Meat & Seafood > Smoked > ",  "Meat & Seafood > Meat > Smoked > ",  "prefix"),
    ("Meat & Seafood > Smoked",     "Meat & Seafood > Meat > Smoked",     "exact"),
    ("Meat & Seafood > Ground > ",  "Meat & Seafood > Meat > Ground > ",  "prefix"),
    ("Meat & Seafood > Ground",     "Meat & Seafood > Meat > Ground",     "exact"),
    ("Meat & Seafood > Prepared Meats > ",  "Meat & Seafood > Meat > Prepared > ",  "prefix"),
    ("Meat & Seafood > Prepared Meats",     "Meat & Seafood > Meat > Prepared",     "exact"),
    ("Meat & Seafood > Processed Meats > ", "Meat & Seafood > Meat > Processed > ", "prefix"),
    ("Meat & Seafood > Processed Meats",    "Meat & Seafood > Meat > Processed",    "exact"),
    ("Meat & Seafood > Nuggets > ", "Meat & Seafood > Poultry > Chicken > Nuggets > ", "prefix"),
    ("Meat & Seafood > Nuggets",    "Meat & Seafood > Poultry > Chicken > Nuggets",    "exact"),
]


def fix(path: str) -> str:
    if not path: return path
    for old, new, mode in RULES:
        if mode == "prefix" and path.startswith(old):
            return new + path[len(old):]
        if mode == "exact" and path == old:
            return new
    return path


def main() -> None:
    tmp = AUDIT.with_suffix(".tmp.csv")
    log_rows: list[dict] = []
    n_changed = 0
    with AUDIT.open(encoding="utf-8", newline="") as fin, \
         tmp.open("w", encoding="utf-8", newline="") as fout:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
        wtr.writeheader()
        for r in rdr:
            old_cp = r.get("canonical_path", "") or ""
            old_rlp = r.get("retail_leaf_path", "") or ""
            new_cp = fix(old_cp); new_rlp = fix(old_rlp)
            if new_cp != old_cp or new_rlp != old_rlp:
                n_changed += 1
                r["canonical_path"] = new_cp
                r["retail_leaf_path"] = new_rlp
                if len(log_rows) < 50000:
                    log_rows.append({
                        "fdc_id": r.get("fdc_id", ""),
                        "old_cp": old_cp, "new_cp": new_cp,
                        "old_rlp": old_rlp, "new_rlp": new_rlp,
                    })
            wtr.writerow(r)
    shutil.move(str(tmp), str(AUDIT))
    print(f"  rows changed: {n_changed:,}")
    if log_rows:
        cols = list(log_rows[0].keys())
        with LOG.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"  wrote {LOG.name}")


if __name__ == "__main__":
    main()
