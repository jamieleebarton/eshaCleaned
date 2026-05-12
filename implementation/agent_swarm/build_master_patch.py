"""
Build a master patch CSV from superset-upgrade findings across ALL categories.

Usage:
    python3 build_master_patch.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from swarm_worker import load_esha_index, analyze_category

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
PRODUCT_MAP = ROOT / "implementation/output/product_to_best_esha_full_map.vIdentity.csv"
PATCH_CSV = ROOT / "implementation/agent_swarm/master_patch.csv"

def main():
    print("Loading ESHA index...")
    esha_index, esha_desc_index = load_esha_index()
    print(f"  {len(esha_index):,} ESHA codes")

    # Collect all categories
    categories: set[str] = set()
    with open(PRODUCT_MAP, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            cat = r.get("branded_food_category", "").strip()
            if cat:
                categories.add(cat)
    print(f"  {len(categories)} categories")

    all_findings: list[dict] = []
    for i, category in enumerate(sorted(categories), 1):
        result = analyze_category(category, esha_index, esha_desc_index)
        if result["n_findings"]:
            all_findings.extend(result["findings"])
            print(f"  [{i:>3}/{len(categories)}] {category:50s} {result['n_findings']:>4} findings")

    print(f"\nTotal findings across all categories: {len(all_findings)}")

    if all_findings:
        with open(PATCH_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_findings[0].keys()))
            writer.writeheader()
            writer.writerows(all_findings)
        print(f"Master patch written to: {PATCH_CSV}")

if __name__ == "__main__":
    main()
