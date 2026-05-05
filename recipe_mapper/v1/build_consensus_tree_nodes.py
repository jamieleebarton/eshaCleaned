#!/usr/bin/env python3
"""Reduce consensus_full_corpus_audit.csv (462K SKUs) to unique tree nodes.

A tree node = (canonical_path, product_identity_fixed). We aggregate the
modal FNDDS/SR28 codes, count SKUs per node, sample a few SKU titles so the
embedding has more signal than identity alone, and keep portions_json from
the most-common-with-portions SKU.

Output: recipe_mapper/v1/output/consensus_tree_nodes.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IN = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
DEFAULT_OUT = Path(__file__).resolve().parent / "output" / "consensus_tree_nodes.csv"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--samples", type=int, default=5,
                    help="sample SKU titles per node")
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    # accumulators per (canonical_path, product_identity_fixed)
    sku_n: Counter[tuple[str, str]] = Counter()
    fndds_codes: dict[tuple, Counter] = defaultdict(Counter)
    fndds_descs: dict[tuple, dict[str, str]] = defaultdict(dict)
    sr28_codes:  dict[tuple, Counter] = defaultdict(Counter)
    sr28_descs:  dict[tuple, dict[str, str]] = defaultdict(dict)
    bfc_modes:   dict[tuple, Counter] = defaultdict(Counter)
    flavors:     dict[tuple, Counter] = defaultdict(Counter)
    forms:       dict[tuple, Counter] = defaultdict(Counter)
    titles:      dict[tuple, list[str]] = defaultdict(list)
    portions:    dict[tuple, str] = {}
    leaf_paths:  dict[tuple, Counter] = defaultdict(Counter)

    n = 0
    with args.inp.open() as f:
        r = csv.DictReader(f)
        for row in r:
            n += 1
            cp = (row.get("canonical_path") or "").strip()
            pid = (row.get("product_identity_fixed") or "").strip()
            if not cp or not pid:
                continue
            key = (cp, pid)
            sku_n[key] += 1
            fc = (row.get("fndds_code") or "").strip()
            if fc:
                fndds_codes[key][fc] += 1
                fndds_descs[key].setdefault(fc, (row.get("fndds_desc") or "").strip())
            sc = (row.get("sr28_code") or "").strip()
            if sc:
                sr28_codes[key][sc] += 1
                sr28_descs[key].setdefault(sc, (row.get("sr28_desc") or "").strip())
            bfc = (row.get("branded_food_category") or "").strip()
            if bfc:
                bfc_modes[key][bfc] += 1
            fv = (row.get("flavor") or "").strip()
            if fv:
                flavors[key][fv] += 1
            fm = (row.get("form_texture_cut") or "").strip()
            if fm:
                forms[key][fm] += 1
            lp = (row.get("retail_leaf_path") or "").strip()
            if lp:
                leaf_paths[key][lp] += 1
            tit = (row.get("title") or "").strip()
            if tit and len(titles[key]) < args.samples and tit not in titles[key]:
                titles[key].append(tit)
            pj = (row.get("portions_json") or "").strip()
            if pj and key not in portions:
                portions[key] = pj

    print(f"scanned {n:,} SKUs")
    print(f"unique nodes: {len(sku_n):,}")

    def top(c: Counter, k: int = 1) -> str:
        if not c: return ""
        return c.most_common(1)[0][0]

    rows_out = []
    for (cp, pid), nsku in sku_n.most_common():
        rows_out.append({
            "canonical_path": cp,
            "product_identity_fixed": pid,
            "sku_count": nsku,
            "modal_branded_food_category": top(bfc_modes[(cp, pid)]),
            "modal_fndds_code": top(fndds_codes[(cp, pid)]),
            "modal_fndds_desc": fndds_descs[(cp, pid)].get(top(fndds_codes[(cp, pid)]), ""),
            "modal_sr28_code": top(sr28_codes[(cp, pid)]),
            "modal_sr28_desc": sr28_descs[(cp, pid)].get(top(sr28_codes[(cp, pid)]), ""),
            "modal_retail_leaf_path": top(leaf_paths[(cp, pid)]),
            "top_flavors": " | ".join(k for k, _ in flavors[(cp, pid)].most_common(5)),
            "top_forms":   " | ".join(k for k, _ in forms[(cp, pid)].most_common(5)),
            "sample_titles": " || ".join(titles[(cp, pid)]),
            "portions_json": portions.get((cp, pid), ""),
            "has_portions": bool(portions.get((cp, pid))),
            "has_fndds": bool(top(fndds_codes[(cp, pid)])),
            "has_sr28":  bool(top(sr28_codes[(cp, pid)])),
        })

    cols = list(rows_out[0].keys())
    with args.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows_out)
    print(f"wrote {args.out} ({len(rows_out):,} nodes)")

    # quick coverage line
    n_fndds = sum(1 for r in rows_out if r["has_fndds"])
    n_sr28  = sum(1 for r in rows_out if r["has_sr28"])
    n_port  = sum(1 for r in rows_out if r["has_portions"])
    print(f"  has_fndds={n_fndds:,}  has_sr28={n_sr28:,}  has_portions={n_port:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
