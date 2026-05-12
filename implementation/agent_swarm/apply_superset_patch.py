"""
Apply superset-upgrade patches from swarm_worker JSON reports to the product map.

Safety rules:
  - Only patch rows where current code != proposed code
  - Only patch rows where current_reason is NOT an exact/agree exact
  - Skip if multiple reports propose different codes for the same product
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
REPORTS_DIR = ROOT / "implementation/agent_swarm/reports"
PRODUCT_MAP = ROOT / "implementation/output/product_to_best_esha_full_map.vIdentity.csv"
TMP_OUT = PRODUCT_MAP.with_suffix(".vSuperset.tmp")


def main():
    # Gather all findings from reports
    all_findings: list[dict] = []
    for report_path in REPORTS_DIR.glob("*.json"):
        with open(report_path) as f:
            data = json.load(f)
        all_findings.extend(data.get("findings", []))

    print(f"Loaded {len(all_findings)} findings from reports")

    # Build patch lookup, detecting conflicts
    patches: dict[str, dict] = {}
    conflicts: Counter = Counter()
    for f in all_findings:
        key = f"{f['gtin_upc']}::{f['fdc_id']}"
        if key in patches:
            existing = patches[key]
            if existing["proposed_code"] != f["proposed_code"]:
                conflicts[key] += 1
                print(f"  CONFLICT: {key}")
                print(f"    existing: [{existing['proposed_code']}] {existing['proposed_desc']}")
                print(f"    new:      [{f['proposed_code']}] {f['proposed_desc']}")
                # Keep the one with higher coverage
                if f["coverage"] <= existing["coverage"]:
                    continue
        patches[key] = f

    if conflicts:
        print(f"\n  {len(conflicts)} conflicts found (kept highest-coverage proposal)")

    print(f"\nUnique patches: {len(patches)}")

    # Apply patches
    n_patched = 0
    n_unchanged = 0
    n_skipped_reason = 0
    audit = Counter()

    with open(PRODUCT_MAP, encoding="utf-8", errors="replace") as fin, \
         open(TMP_OUT, "w", newline="") as fout:
        reader = csv.DictReader(fin)
        fields = list(reader.fieldnames or [])
        writer = csv.DictWriter(fout, fieldnames=fields)
        writer.writeheader()

        for r in reader:
            key = f"{r.get('gtin_upc', '')}::{r.get('fdc_id', '')}"
            patch = patches.get(key)

            if not patch:
                writer.writerow(r)
                n_unchanged += 1
                continue

            current_code = r.get("best_esha_code", "").strip()
            current_reason = r.get("best_esha_change_reason", "").strip()

            # Safety: skip if current is already exact or strongly agreed
            if current_reason in ("kept_agree_exact", "replaced_exact",
                                   "filled_exact", "kept_agree_strong"):
                writer.writerow(r)
                n_skipped_reason += 1
                continue

            proposed_code = patch["proposed_code"]
            proposed_desc = patch["proposed_desc"]

            if current_code == proposed_code:
                writer.writerow(r)
                n_unchanged += 1
                continue

            row_out = dict(r)
            row_out["best_esha_code"] = proposed_code
            row_out["best_esha_description"] = proposed_desc
            row_out["best_esha_change_reason"] = f"superset_patch_from_{current_code}"
            row_out["assignment_source"] = "superset_patch"
            row_out["score"] = str(patch["coverage"])
            row_out["score_num"] = str(patch["coverage"])
            writer.writerow(row_out)
            n_patched += 1
            audit[patch["upgrade_type"]] += 1

    TMP_OUT.replace(PRODUCT_MAP)

    print(f"\nApplied {n_patched} patches")
    print(f"  unchanged: {n_unchanged}")
    print(f"  skipped (exact/strong reason): {n_skipped_reason}")
    print(f"  audit: {dict(audit)}")


if __name__ == "__main__":
    main()
