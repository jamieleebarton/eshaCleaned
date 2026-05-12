"""Collapse product_to_canonical_signature.csv into per-signature group rows."""
from __future__ import annotations
import argparse
import csv
from collections import defaultdict
from pathlib import Path

DEFAULT_INPUT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/"
                     "product_to_canonical_signature.csv")
DEFAULT_OUTPUT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/"
                     "signature_groups.csv")

KEY_FIELDS = ("signature_head_noun", "signature_modifiers", "signature_form",
              "signature_state", "signature_flavor", "signature_style", "composite")

OUTPUT_FIELDS = list(KEY_FIELDS) + [
    "product_count", "canonical_anchor_id", "esha_code",
    "representative_descriptions",
    "mean_match_confidence",
]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    groups: dict[tuple, list[dict]] = defaultdict(list)
    with args.input.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = tuple(row[k] for k in KEY_FIELDS)
            groups[key].append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for key, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            n = len(rows)
            anchors = [r["canonical_anchor_id"] for r in rows if r["canonical_anchor_id"]]
            anchor = max(set(anchors), key=anchors.count) if anchors else ""
            esha_codes = [r["esha_code"] for r in rows if r["esha_code"]]
            esha = max(set(esha_codes), key=esha_codes.count) if esha_codes else ""
            reps = [r["product_description"] for r in rows[:5]]
            mean_conf = (sum(float(r["match_confidence"]) for r in rows) / n) if n else 0.0
            writer.writerow({
                **dict(zip(KEY_FIELDS, key)),
                "product_count": n,
                "canonical_anchor_id": anchor,
                "esha_code": esha,
                "representative_descriptions": " || ".join(reps),
                "mean_match_confidence": f"{mean_conf:.4f}",
            })
    print(f"Wrote {args.output} with {len(groups)} unique signatures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
