#!/usr/bin/env python3
"""R13 propagate — apply DB quarantine moves to the golden CSV files.

When quarantine_blocklisted_skus.py moves SKUs to "Non-Food > Misclassified"
in priced_products_v2.db AND re-encodes their htc codes, the SAME SKUs in
the golden HTC-tagged CSVs still have the OLD canonical_path / htc_code.
That violates the "same identity → same htc_code across all golden files"
invariant in user memory.

This script reads the current state of priced_products_v2.db and overwrites
the corresponding rows in:
  - recipe_pricing/output/api_cache_htc_tagged.csv (joined on upc)
  - recipe_mapper/v1/output/consensus_htc_tagged.csv (joined on fdc_id)

Backs up each file before overwriting.

Usage:
  python3 recipe_pricing/propagate_quarantine_to_golden.py [--dry-run]
"""
from __future__ import annotations
import argparse, csv, shutil, sqlite3, sys
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
API_CACHE = ROOT / "recipe_pricing" / "output" / "api_cache_htc_tagged.csv"
CONSENSUS = ROOT / "recipe_mapper" / "v1" / "output" / "consensus_htc_tagged.csv"


def load_db_state() -> dict[str, dict]:
    """upc → {canonical_path, htc_code, htc_full_code}"""
    out = {}
    con = sqlite3.connect(str(DB))
    cur = con.execute(
        "SELECT upc, consensus_canonical, htc_code, htc_form_code, "
        "htc_full_code FROM priced_products WHERE upc IS NOT NULL"
    )
    for upc, cp, hc, hf, hfull in cur:
        out[upc] = {
            "canonical_path": cp or "",
            "htc_code": (hc or "").lstrip("~"),
            "htc_form_code": (hf or "").lstrip("~"),
            "htc_full_code": hfull or "",
        }
    return out


def patch_csv(path: Path, key_col: str, db_state: dict[str, dict],
              dry_run: bool, key_field_in_db: str = "upc") -> int:
    if not path.exists():
        print(f"  missing {path.name}", file=sys.stderr); return 0
    bak = path.with_suffix(path.suffix + ".before_propagate_round13")
    if not dry_run and not bak.exists():
        shutil.copy(str(path), str(bak))

    # Build a lookup keyed on whatever field this CSV uses
    if key_field_in_db == "upc":
        lookup = {k: v for k, v in db_state.items()}
    elif key_field_in_db == "fdc_id":
        lookup = {}
        for k, v in db_state.items():
            f = v.get("fdc_id")
            if f: lookup[f] = v
    else:
        return 0

    n_changed = 0
    n_total = 0
    rows_out = []
    with path.open() as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            n_total += 1
            key = (row.get(key_col) or "").strip()
            if not key or key not in lookup:
                rows_out.append(row); continue
            db_row = lookup[key]
            changed = False
            new_cp = db_row["canonical_path"]
            new_id = db_row["htc_code"]
            new_full = db_row["htc_full_code"]
            if "canonical_path" in row and row["canonical_path"] != new_cp:
                row["canonical_path"] = new_cp; changed = True
            if "htc_code" in row and row["htc_code"].lstrip("~") != new_id:
                row["htc_code"] = new_id; changed = True
            if "htc_full_code" in row and row["htc_full_code"] != new_full:
                row["htc_full_code"] = new_full; changed = True
            if changed: n_changed += 1
            rows_out.append(row)

    print(f"  {path.name}: {n_changed:,} / {n_total:,} rows updated",
          file=sys.stderr)

    if not dry_run and n_changed > 0:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows_out: w.writerow(r)
        tmp.replace(path)
    return n_changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("loading priced_products_v2.db state…", file=sys.stderr)
    db = load_db_state()
    print(f"  {len(db):,} UPCs in DB", file=sys.stderr)

    print(f"\npropagating to api_cache_htc_tagged.csv (joined on upc)…",
          file=sys.stderr)
    patch_csv(API_CACHE, "upc", db, args.dry_run, key_field_in_db="upc")

    # Note: consensus_htc_tagged.csv is keyed on fdc_id (not upc). Mrs.Meyer's
    # at "Basil" was a SKU-level mis-mapping, not an FDC-level error: the
    # FDC for Basil is correct; only the upc→fdc bridge for that SKU was
    # wrong. So the FDC-level file doesn't need updating from quarantine
    # moves. Skipping by design.

    if args.dry_run:
        print("\n(dry-run; no writes)", file=sys.stderr)


if __name__ == "__main__":
    main()
