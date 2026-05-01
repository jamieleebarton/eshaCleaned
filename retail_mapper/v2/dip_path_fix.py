#!/usr/bin/env python3
"""Quick deterministic fix for dip-titled SKUs stuck at soup/wrong paths.

Rule: if title contains "DIP" as a word AND current path starts with
Pantry > Soup, reroute to Pantry > Dips & Spreads.

Read-only on input; writes a corrections CSV that gets picked up by
build_audit_csv.py via the existing path-describe-corrections layer.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "dip_path_corrections.csv"

csv.field_size_limit(sys.maxsize)

# Word-boundary "dip" match — avoids hitting "DIPPED", "DIPPING" only when
# they aren't actually a dip product
WORD_DIP = re.compile(r"\b(dip)\b", re.I)


def main() -> None:
    n = 0
    out_rows: list[dict] = []
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            t = r.get("title", "") or ""
            cp = r.get("canonical_path", "") or ""
            if not WORD_DIP.search(t):
                continue
            n += 1
            new_path = ""
            # Pattern 1: dip stuck at "Pantry > Soup > French Onion Soup"
            if "Pantry > Soup > French Onion" in cp:
                new_path = "Pantry > Dips & Spreads > French Onion Dip"
            # Pattern 2: dip stuck at flat "Pantry > Soup"
            elif cp == "Pantry > Soup":
                new_path = "Pantry > Dips & Spreads > Dip"
            # Pattern 3: dip & soup mix → keep at Pantry > Mixes
            elif "Pantry > Soup" in cp and "MIX" in t.upper():
                new_path = "Pantry > Mixes > Soup & Dip Mix"
            # Pattern 4: any other dip stuck at "Pantry > Soup > X"
            elif cp.startswith("Pantry > Soup"):
                # extract trailing modifier if any
                tail = cp[len("Pantry > Soup"):].strip(" >")
                # try to use the soup name as a dip variant
                if "Onion" in tail:
                    new_path = "Pantry > Dips & Spreads > Onion Dip"
                else:
                    new_path = "Pantry > Dips & Spreads > Dip"
            # Pattern 5: spinach dip stuck at "Pantry > Canned Vegetables > Spinach"
            elif "SPINACH" in t.upper() and cp.startswith("Pantry > Canned Vegetables > Spinach"):
                new_path = "Pantry > Dips & Spreads > Spinach Dip"
            else:
                continue
            if new_path and new_path != cp:
                out_rows.append({
                    "fdc_id": r.get("fdc_id", ""),
                    "title": t[:80],
                    "old_path": cp,
                    "new_path": new_path,
                    "rationale": "dip-titled-but-wrong-path heuristic",
                    "confidence": "0.95",
                })

    print(f"  scanned dip-titled rows: {n:,}")
    print(f"  proposed fixes:           {len(out_rows):,}")
    if out_rows:
        cols = ["fdc_id", "title", "old_path", "new_path", "rationale", "confidence"]
        with OUT.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(out_rows)
        print(f"  wrote {OUT.name}")
        # Show a few examples
        print()
        print("  Sample fixes:")
        for r in out_rows[:8]:
            print(f"    {r['title']}")
            print(f"      {r['old_path']} → {r['new_path']}")


if __name__ == "__main__":
    main()
