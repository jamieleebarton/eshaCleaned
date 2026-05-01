#!/usr/bin/env python3
"""Find duplicate canonical_paths by FNDDS/SR28 join.

If two SKUs share an FNDDS code but live in different canonical_paths in our
tree, those paths are duplicates. This script surfaces every such cluster.

Outputs:
  - fndds_path_clusters.csv  (one row per fndds_code, sorted by # distinct paths)
  - sr28_path_clusters.csv   (same for SR28 NDB codes)

Read-only. Run after the pipeline produces full_corpus_audit.csv.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SRC = V2 / "full_corpus_audit.csv"
OUT_FNDDS = V2 / "fndds_path_clusters.csv"
OUT_SR28 = V2 / "sr28_path_clusters.csv"

csv.field_size_limit(sys.maxsize)


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}")
    print(f"  reading {SRC.name}")

    fndds_paths: dict[str, Counter] = defaultdict(Counter)
    fndds_descs: dict[str, str] = {}
    fndds_identities: dict[str, Counter] = defaultdict(Counter)
    sr28_paths: dict[str, Counter] = defaultdict(Counter)
    sr28_descs: dict[str, str] = {}
    sr28_identities: dict[str, Counter] = defaultdict(Counter)

    n = 0
    with SRC.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            n += 1
            cp = (row.get("canonical_path") or "").strip()
            pid = (row.get("product_identity_fixed") or "").strip()
            if not cp:
                continue
            f = (row.get("fndds_code") or "").strip()
            s = (row.get("sr28_code") or "").strip()
            fdesc = (row.get("fndds_desc") or "").strip()
            sdesc = (row.get("sr28_desc") or "").strip()
            if f:
                fndds_paths[f][cp] += 1
                fndds_identities[f][pid] += 1
                if f not in fndds_descs and fdesc:
                    fndds_descs[f] = fdesc
            if s:
                sr28_paths[s][cp] += 1
                sr28_identities[s][pid] += 1
                if s not in sr28_descs and sdesc:
                    sr28_descs[s] = sdesc

    print(f"  scanned {n:,} SKUs")
    print(f"  fndds codes: {len(fndds_paths):,}")
    print(f"  sr28 codes:  {len(sr28_paths):,}")

    def emit(out: Path, kind: str, paths: dict, descs: dict, identities: dict) -> None:
        cols = [f"{kind}_code", f"{kind}_desc", "n_distinct_paths",
                "n_distinct_identities", "n_total_skus",
                "paths_with_counts", "identities_with_counts"]
        rows: list[dict] = []
        for code, ps in paths.items():
            ids = identities.get(code, Counter())
            rows.append({
                f"{kind}_code": code,
                f"{kind}_desc": descs.get(code, ""),
                "n_distinct_paths": len(ps),
                "n_distinct_identities": len(ids),
                "n_total_skus": sum(ps.values()),
                "paths_with_counts": " | ".join(
                    f"{p} ({c})" for p, c in ps.most_common()),
                "identities_with_counts": " | ".join(
                    f"{i} ({c})" for i, c in ids.most_common()),
            })
        rows.sort(key=lambda r: (-r["n_distinct_paths"], -r["n_total_skus"]))
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"  wrote {out.name} ({len(rows):,} rows)")
        # Summary: top 20 worst clusters
        print(f"  top 20 {kind} clusters by # distinct paths:")
        for r in rows[:20]:
            print(f"    {r[f'{kind}_code']:>10}  {r['n_distinct_paths']:>3} paths  "
                  f"{r['n_total_skus']:>6} skus  {r[f'{kind}_desc'][:50]}")

    emit(OUT_FNDDS, "fndds", fndds_paths, fndds_descs, fndds_identities)
    print()
    emit(OUT_SR28, "sr28", sr28_paths, sr28_descs, sr28_identities)


if __name__ == "__main__":
    main()
