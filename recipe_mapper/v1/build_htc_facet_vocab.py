#!/usr/bin/env python3
"""P5 — Build per-HTC facet vocabularies from consensus columns.

For each htc_code, mine the consensus columns (flavor, form_texture_cut,
processing_storage, claims, modifier, variant) and emit the top-N values
with counts. This is the controlled vocabulary the matcher uses to extract
structured facets from a recipe ingredient `display` string.

Inputs:
  consensus_full_corpus_audit.csv (for the full facet columns)
  consensus_htc_tagged.csv         (for fdc_id → htc_code)

Output:
  htc_facet_vocab.json
  htc_facet_vocab_summary.csv
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
HERE = Path(__file__).resolve().parent
DEFAULT_AUDIT = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
DEFAULT_TAGGED = HERE / "output" / "consensus_htc_tagged.csv"
OUT_JSON = HERE / "output" / "htc_facet_vocab.json"
OUT_SUMMARY = HERE / "output" / "htc_facet_vocab_summary.csv"

FACETS = ["flavor", "form_texture_cut", "processing_storage",
          "claims", "modifier", "variant"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--tagged", type=Path, default=DEFAULT_TAGGED)
    ap.add_argument("--top-n", type=int, default=30)
    ap.add_argument("--min-count", type=int, default=2)
    args = ap.parse_args()

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] reading htc tags: {args.tagged.name}")
    fdc_to_htc: dict[str, str] = {}
    with args.tagged.open() as f:
        r = csv.DictReader(f)
        for row in r:
            fdc = (row.get("fdc_id") or "").strip()
            code = (row.get("htc_code") or "").strip()
            if fdc and code:
                fdc_to_htc[fdc] = code
    print(f"  {len(fdc_to_htc):,} fdc→htc mappings")

    print(f"[2/3] mining facets from audit: {args.audit.name}")
    # facet_counters[htc_code][facet_name] = Counter
    facets: dict[str, dict[str, Counter]] = defaultdict(
        lambda: {f: Counter() for f in FACETS}
    )
    n_rows = 0
    n_with_htc = 0
    with args.audit.open() as f:
        r = csv.DictReader(f)
        for row in r:
            n_rows += 1
            fdc = (row.get("fdc_id") or "").strip()
            code = fdc_to_htc.get(fdc)
            if not code:
                continue
            n_with_htc += 1
            for fac in FACETS:
                v = (row.get(fac) or "").strip()
                if not v:
                    continue
                # split multi-valued cells (modifier uses ' > ', flavor uses ' | ')
                if ">" in v or "|" in v:
                    parts = []
                    for chunk in v.replace(">", "|").split("|"):
                        c = chunk.strip()
                        if c:
                            parts.append(c)
                    for p in parts:
                        facets[code][fac][p] += 1
                else:
                    facets[code][fac][v] += 1
            if n_rows % 100000 == 0:
                print(f"  {n_rows:,} rows", flush=True)
    print(f"  {n_rows:,} rows  with_htc={n_with_htc:,}  unique_htcs={len(facets):,}")

    print(f"[3/3] writing vocab")
    out: dict[str, dict[str, list[list]]] = {}
    summary_rows: list[list] = []
    for code, fac_dict in facets.items():
        clean: dict[str, list[list]] = {}
        for fac, ctr in fac_dict.items():
            top = [(v, n) for v, n in ctr.most_common(args.top_n) if n >= args.min_count]
            if top:
                clean[fac] = top
        if clean:
            out[code] = clean
            n_facets = sum(len(v) for v in clean.values())
            summary_rows.append([code, len(clean), n_facets])

    with OUT_JSON.open("w") as f:
        json.dump(out, f, indent=2)
    with OUT_SUMMARY.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["htc_code", "n_facet_types", "total_facet_values"])
        for row in sorted(summary_rows, key=lambda r: -r[2]):
            w.writerow(row)

    print(f"  -> {OUT_JSON} ({len(out):,} HTC codes with facets)")
    print(f"  -> {OUT_SUMMARY}")

    # Sample probes
    print()
    print("=== facet probes ===")
    probes = [
        ("D000600$", "milk-ish water/coffee blend"),
        ("E0000006", "Salt, generic"),
        ("F0000004", "Hot sauce / sriracha"),
        ("F000000$", "Mayonnaise"),
        ("1000600D", "Whole milk"),
    ]
    for code, label in probes:
        v = out.get(code)
        if not v:
            print(f"  {code} ({label}): [no facets]")
            continue
        print(f"  {code} ({label}):")
        for fac in FACETS:
            if fac in v:
                top5 = " | ".join(f"{val}({n})" for val, n in v[fac][:5])
                print(f"    {fac}: {top5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
