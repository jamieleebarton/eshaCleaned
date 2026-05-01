#!/usr/bin/env python3
"""Pass 2 of the two-pass design: apply DeepSeek's proposed paths to the audit.

Reads:
  - retail_mapper/v2/path_describe_decisions.jsonl
  - retail_mapper/v2/full_corpus_audit.csv

For each fdc_id with a Pass-1 decision, override the canonical_path. Skip
when DeepSeek's path is identical to current OR confidence < threshold.

Writes a corrections CSV that build_audit_csv.py can pick up like the FNDDS
corrections layer:
  - retail_mapper/v2/path_describe_corrections.csv

The audit-build step (build_audit_csv.py) already has a path-rewrite layer;
we'll wire the new corrections through there as a final stage.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DECISIONS = V2 / "path_describe_decisions.jsonl"
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "path_describe_corrections.csv"

CONF_THRESHOLD = 0.70

csv.field_size_limit(sys.maxsize)


def main() -> None:
    if not DECISIONS.exists():
        raise SystemExit(f"missing {DECISIONS}")

    # Load DeepSeek decisions
    decisions: dict[str, dict] = {}
    with DECISIONS.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                fdc = d.get("fdc_id", "")
                if fdc:
                    decisions[fdc] = d
            except Exception:
                pass
    print(f"  Pass-1 decisions: {len(decisions):,}")

    # Stream audit and pair up
    n = 0; n_changed = 0; n_skipped_low_conf = 0; n_skipped_same = 0
    out_rows: list[dict] = []
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fdc = r.get("fdc_id", "")
            if fdc not in decisions:
                continue
            n += 1
            d = decisions[fdc]
            new_path = (d.get("canonical_path") or "").strip()
            conf = float(d.get("confidence", 0))
            if not new_path:
                continue
            if conf < CONF_THRESHOLD:
                n_skipped_low_conf += 1
                continue
            current = (r.get("canonical_path") or "").strip()
            if new_path == current:
                n_skipped_same += 1
                continue
            n_changed += 1
            out_rows.append({
                "fdc_id": fdc,
                "title": r.get("title", "")[:120],
                "old_path": current,
                "new_path": new_path,
                "rationale": d.get("rationale", "")[:200],
                "confidence": f"{conf:.2f}",
            })

    cols = ["fdc_id", "title", "old_path", "new_path", "rationale", "confidence"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        # Sort by confidence ascending so iffy ones are easy to spot
        out_rows.sort(key=lambda x: float(x["confidence"]))
        w.writerows(out_rows)

    print(f"  paired with audit: {n:,}")
    print(f"  corrections proposed: {n_changed:,}")
    print(f"    skipped (low conf < {CONF_THRESHOLD}): {n_skipped_low_conf:,}")
    print(f"    skipped (same as current):              {n_skipped_same:,}")
    print(f"  wrote {OUT.name}")


if __name__ == "__main__":
    main()
