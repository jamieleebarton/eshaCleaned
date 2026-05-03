#!/usr/bin/env python3
"""Apply DeepSeek's misroute decisions to full_corpus_audit.csv.

Reads:
  retail_mapper/v2/deepseek_misroute_decisions.jsonl

Builds an fdc_id → (family, type) override map (expanded across all
_member_fdcs of each group). Writes:

  retail_mapper/v2/deepseek_misroute_overrides.json
    Map: fdc_id → {family, type, confidence}

Then patches homogenize_audit.py to load and apply these as a Pass 0
(highest-priority override). After running this script, re-run:

  python3 build_audit_csv.py
  python3 homogenize_audit.py

The overrides will take effect.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

V2 = Path(__file__).resolve().parent
DECISIONS = V2 / "deepseek_misroute_decisions.jsonl"
OVERRIDES = V2 / "deepseek_misroute_overrides.json"


def main() -> None:
    if not DECISIONS.exists():
        print(f"missing {DECISIONS}", file=sys.stderr)
        sys.exit(1)

    overrides: dict[str, dict] = {}
    n_decisions = 0
    n_skipped_low = 0
    n_skipped_err = 0
    with DECISIONS.open() as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_decisions += 1
            if "error" in d:
                n_skipped_err += 1
                continue
            decision = d.get("decision") or {}
            family = decision.get("family")
            type_seg = decision.get("type")
            confidence = decision.get("confidence", "medium")
            if not (family and type_seg):
                continue
            # Skip low-confidence — we don't want to make things worse
            if confidence == "low":
                n_skipped_low += 1
                continue
            # Apply to all members of this group
            members = d.get("_member_fdcs") or [d.get("fdc_id")]
            for fdc in members:
                if not fdc:
                    continue
                # Don't overwrite an existing override (first-write wins)
                if fdc in overrides:
                    continue
                overrides[fdc] = {
                    "family": family,
                    "type": type_seg,
                    "confidence": confidence,
                }

    OVERRIDES.write_text(json.dumps(overrides, indent=1, sort_keys=True))
    print(f"Decisions parsed: {n_decisions:,}")
    print(f"  skipped errors:        {n_skipped_err:,}")
    print(f"  skipped low-confidence:{n_skipped_low:,}")
    print(f"  fdc overrides built:   {len(overrides):,}")
    print(f"Wrote {OVERRIDES}")


if __name__ == "__main__":
    main()
