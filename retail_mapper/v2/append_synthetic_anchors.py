#!/usr/bin/env python3
"""Append synthetic taxonomy anchors into consensus_full_corpus_audit.csv.

Reads retail_mapper/v2/synthetic_taxonomy_anchors.csv (8 cols) and appends
each row to consensus_full_corpus_audit.csv with all 37 columns populated:
identity columns from the anchor CSV, everything else blank.

Idempotent: rows with `fdc_id` starting with `SYNTH:` are removed first,
so re-running picks up edits to the anchor list cleanly.
"""
from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

V2 = Path(__file__).resolve().parent
AUDIT = V2 / "consensus_full_corpus_audit.csv"
ANCHORS = V2 / "synthetic_taxonomy_anchors.csv"
TMP = AUDIT.with_suffix(".csv.tmp")


def main() -> int:
    if not AUDIT.exists():
        print(f"missing audit: {AUDIT}", file=sys.stderr)
        return 2
    if not ANCHORS.exists():
        print(f"missing anchors: {ANCHORS}", file=sys.stderr)
        return 2

    # Load anchors
    anchors = []
    with ANCHORS.open(newline="") as f:
        for row in csv.DictReader(f):
            anchors.append(row)
    print(f"anchors to append: {len(anchors)}", file=sys.stderr)

    # Stream audit; drop any prior SYNTH: rows; append all anchors at end.
    with AUDIT.open(newline="") as fin, TMP.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        fieldnames = reader.fieldnames or []
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        kept = 0
        dropped = 0
        for row in reader:
            fid = row.get("fdc_id", "") or ""
            if fid.startswith("SYNTH:"):
                dropped += 1
                continue
            writer.writerow(row)
            kept += 1

        # Now append anchors with all fieldnames populated
        appended = 0
        for a in anchors:
            row = {col: "" for col in fieldnames}
            row["fdc_id"] = a["fdc_id"]
            row["title"] = a["title"]
            row["branded_food_category"] = a.get("branded_food_category", "")
            row["canonical_path"] = a["canonical_path"]
            row["canonical_label"] = a["canonical_label"]
            row["product_identity_fixed"] = a["product_identity_fixed"]
            row["consensus_source"] = a["consensus_source"]
            row["consensus_reason"] = a.get("note", "")
            # Confidence at 1.0 since we explicitly authored these
            if "confidence" in fieldnames:
                row["confidence"] = "1.0"
            writer.writerow(row)
            appended += 1

    shutil.move(str(TMP), str(AUDIT))
    print(f"  kept existing rows : {kept:,}", file=sys.stderr)
    print(f"  dropped prior SYNTH: {dropped:,}", file=sys.stderr)
    print(f"  appended new SYNTH : {appended:,}", file=sys.stderr)
    print(f"  → {AUDIT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
