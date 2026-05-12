#!/usr/bin/env python3
"""P1 — Tag the consensus retail corpus with HTC codes.

Reads retail_mapper/v2/consensus_full_corpus_audit.csv (462k SKUs) and runs
the ported HTC v2 tagger over each row using
  category = branded_food_category
  description = title
  extra = product_identity_fixed + ' ' + modifier

Emits one row per SKU with the 8-char code + position breakdown.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from htc.encoder import encode  # noqa: E402
from htc.food_slots import effective_food_name  # noqa: E402
from htc.full_code import compose_full_code  # noqa: E402

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IN = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
DEFAULT_OUT = Path(__file__).resolve().parent / "output" / "consensus_htc_tagged.csv"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    n = tagged = unresolved = 0
    by_group: dict[str, int] = {}

    with args.inp.open() as f, args.out.open("w", newline="") as g:
        r = csv.DictReader(f)
        w = csv.writer(g)
        w.writerow([
            "fdc_id", "title", "branded_food_category",
            "product_identity_fixed", "canonical_path", "retail_leaf_path", "modifier",
            "fndds_code", "sr28_code",
            "htc_code", "htc_full_code",
            "htc_group", "htc_family", "htc_food",
            "htc_form", "htc_processing", "htc_ptype", "htc_check",
            "htc_confidence", "htc_source",
        ])
        for row in r:
            n += 1
            bfc = row.get("branded_food_category") or ""
            title = row.get("title") or ""
            pid = row.get("product_identity_fixed") or ""
            mod = row.get("modifier") or ""
            canonical_path = row.get("canonical_path", "")
            flavor_or_variant = row.get("flavor", "") or row.get("variant", "")
            food_name = effective_food_name(
                canonical_path,
                pid,
                mod,
                " || ".join(
                    row.get(field, "") or ""
                    for field in ("title", "canonical_label", "retail_leaf_path", "fndds_desc", "sr28_desc")
                ),
                flavor=flavor_or_variant,
            )
            h = encode(
                category=bfc,
                description=title,
                extra="",
                food_name=food_name,
                canonical_path=canonical_path,
                modifier=mod,
            )
            if h.group != "0":
                tagged += 1
            else:
                unresolved += 1
            by_group[h.group] = by_group.get(h.group, 0) + 1
            htc_code = "~" + h.code
            rlp = row.get("retail_leaf_path", "")
            full = compose_full_code(htc_code, canonical_path, rlp,
                                     row.get("claims", "") or mod)
            w.writerow([
                row.get("fdc_id", ""), title, bfc, pid,
                canonical_path, rlp, mod,
                row.get("fndds_code", ""), row.get("sr28_code", ""),
                htc_code, full,
                h.group, h.family, h.food,
                h.form, h.processing, h.ptype, h.check,
                f"{h.confidence:.2f}", h.source,
            ])
            if n % 100000 == 0:
                print(f"[{time.time()-t0:6.1f}s] {n:,} rows  tagged={tagged:,}  "
                      f"unresolved={unresolved:,}", flush=True)

    print()
    print(f"total rows:      {n:,}")
    print(f"tagged:          {tagged:,}  ({tagged/n:.1%})")
    print(f"unresolved:      {unresolved:,}  ({unresolved/n:.1%})")
    print(f"by group:")
    for g_, c in sorted(by_group.items(), key=lambda kv: -kv[1]):
        print(f"  {g_}: {c:>7,}")
    print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
