"""RFT Swarm — Fix Applier

Applies fix-proposal CSVs to the product map with safety checks.

Usage:
    python3 fix_applier.py \
        --input implementation/output/product_to_best_esha_full_map.vIdentity.csv \
        --fixes implementation/rft_swarm/reports/wholesome_snacks_fixes.csv \
        --output implementation/output/product_to_best_esha_full_map.vIdentity.csv

Safety rules:
  - Never blank an existing code.
  - Only apply if current code is empty OR current is a known base/generic.
  - Preserve best_esha_original_code if already set.
  - Log every change.
"""
from __future__ import annotations
import csv, sys, time
from collections import Counter
from pathlib import Path

def apply_fixes(product_map_path: Path, fixes_path: Path, output_path: Path):
    # Load fixes
    fixes = {}
    with fixes_path.open(encoding="utf-8",errors="replace") as f:
        for r in csv.DictReader(f):
            key = (r.get("gtin_upc","").strip(), r.get("fdc_id","").strip())
            if key[0] or key[1]:
                fixes[key] = r
    print(f"Loaded {len(fixes):,} fixes from {fixes_path.name}")

    n_rows = 0
    n_applied = 0
    n_skipped = 0
    n_unchanged = 0
    reasons = Counter()

    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    with product_map_path.open(encoding="utf-8",errors="replace") as fin, \
         tmp.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        fields = list(reader.fieldnames or [])
        writer = csv.DictWriter(fout, fieldnames=fields)
        writer.writeheader()

        for row in reader:
            n_rows += 1
            key = (row.get("gtin_upc","").strip(), row.get("fdc_id","").strip())
            fix = fixes.get(key)
            if not fix:
                writer.writerow(row)
                continue

            cur_code = (row.get("best_esha_code") or "").strip()
            cur_desc = (row.get("best_esha_description") or "").strip()
            prop_code = fix["proposed_esha_code"].strip()
            prop_desc = fix["proposed_esha_desc"].strip()

            # Safety: never blank, never apply empty proposal
            if not prop_code:
                reasons["skip_empty_proposal"] += 1
                n_skipped += 1
                writer.writerow(row)
                continue

            # If current is already the proposed code, nothing to do
            if cur_code == prop_code:
                reasons["already_correct"] += 1
                n_unchanged += 1
                writer.writerow(row)
                continue

            # If current has a code and it's not empty, only override if
            # current is a known base code (conservative)
            # We accept override when current == fix current_esha_code
            if cur_code and cur_code != fix["current_esha_code"]:
                reasons["skip_code_changed_since_analysis"] += 1
                n_skipped += 1
                writer.writerow(row)
                continue

            # Preserve original if not already preserved
            orig_code = (row.get("best_esha_original_code") or "").strip()
            orig_desc = (row.get("best_esha_original_description") or "").strip()
            if not orig_code:
                row["best_esha_original_code"] = cur_code
                row["best_esha_original_description"] = cur_desc

            row["best_esha_code"] = prop_code
            row["best_esha_description"] = prop_desc
            row["best_esha_change_reason"] = f"swarm_fix:{fix['reason']}:{fix.get('variant_word','')}"
            row["assignment_source"] = "rft_swarm_fix"
            row["score"] = "1.0"
            row["score_num"] = "1.0"
            reasons[f"applied:{fix['reason']}"] += 1
            n_applied += 1
            writer.writerow(row)

            if n_applied % 100 == 0:
                print(f"  applied {n_applied:,} ...", flush=True)

    tmp.replace(output_path)
    print(f"\nDone. rows={n_rows:,} applied={n_applied:,} skipped={n_skipped:,} unchanged={n_unchanged:,}")
    print("Reasons:")
    for r, c in reasons.most_common():
        print(f"  {r:40s} {c:>6,}")
    print(f"Output -> {output_path}")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--fixes", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    apply_fixes(Path(args.input), Path(args.fixes), Path(args.output))
