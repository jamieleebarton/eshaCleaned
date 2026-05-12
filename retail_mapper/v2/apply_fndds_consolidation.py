#!/usr/bin/env python3
"""Drive cross-family consolidation from the FNDDS-spread report.

For every FNDDS code that spans paths in MULTIPLE top-level families:
  - If one family holds >=70% of SKUs → that's the dominant home
  - For each non-dominant SKU, propose moving it to the dominant family
  - The proposed new path tries to preserve the SKU's specific leaf

Skip: NFS/NS-AS-TO codes (catch-all FNDDS codes), or codes where the
non-dominant family has >=20 SKUs (means it's likely a real distinction).

Two-step: first run --dry to see proposed moves per FNDDS code, then --apply.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
PROPOSAL = V2 / "fndds_consolidation_proposal.csv"
LOG = V2 / "fndds_consolidation_apply_log.csv"

csv.field_size_limit(sys.maxsize)

DOMINANCE_THRESHOLD = 0.70   # canonical family must hold ≥70% of SKUs
MAX_NON_DOMINANT_SKUS = 20    # if non-dom family has >20 SKUs, treat as legit distinct
NFS_MARKERS = ("NFS", "NS AS TO", "NS,", " NS ")


def main(apply_mode: bool) -> None:
    code_to_paths: dict[str, Counter] = defaultdict(Counter)
    code_desc: dict[str, str] = {}
    rows_by_fndds: dict[str, list[str]] = defaultdict(list)  # store fdc_id list

    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            code = (r.get("fndds_code") or "").strip()
            cp = (r.get("canonical_path") or "").strip()
            if not (code and cp): continue
            code_to_paths[code][cp] += 1
            code_desc.setdefault(code, (r.get("fndds_desc") or "").strip())
            rows_by_fndds[code].append(r.get("fdc_id", ""))

    proposals: list[dict] = []
    rewrite_map: dict[str, str] = {}  # old_canonical_path → new_canonical_path

    n_codes_total = len(code_to_paths)
    n_codes_proposed = 0

    for code, path_counter in code_to_paths.items():
        if len(path_counter) < 2: continue
        desc = code_desc.get(code, "")
        if any(m in desc.upper() for m in NFS_MARKERS):
            continue  # NFS catch-all — skip
        # Group by top-level family
        by_family: dict[str, int] = defaultdict(int)
        family_paths: dict[str, Counter] = defaultdict(Counter)
        for path, n in path_counter.items():
            family = path.split(" > ")[0]
            by_family[family] += n
            family_paths[family][path] += n
        if len(by_family) < 2: continue
        total = sum(by_family.values())
        # Find dominant family
        dom_family, dom_n = max(by_family.items(), key=lambda kv: kv[1])
        if dom_n / total < DOMINANCE_THRESHOLD: continue
        # All other families are candidates for migration
        for fam, n in by_family.items():
            if fam == dom_family: continue
            if n > MAX_NON_DOMINANT_SKUS: continue  # too many — likely real distinction
            # The dominant canonical path: the most-common path in the dom family
            dom_canonical = family_paths[dom_family].most_common(1)[0][0]
            for path, path_n in family_paths[fam].most_common():
                proposals.append({
                    "fndds_code": code, "fndds_desc": desc,
                    "old_path": path, "old_skus": path_n,
                    "new_path": dom_canonical,
                    "dominant_family": dom_family,
                    "dominant_skus": dom_n, "total_skus": total,
                })
                rewrite_map[path] = dom_canonical
        n_codes_proposed += 1

    proposals.sort(key=lambda r: -r["old_skus"])
    cols = ["fndds_code", "fndds_desc", "old_path", "old_skus", "new_path",
            "dominant_family", "dominant_skus", "total_skus"]
    with PROPOSAL.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(proposals)

    print(f"  FNDDS codes scanned    : {n_codes_total:,}")
    print(f"  codes with proposals   : {n_codes_proposed:,}")
    print(f"  total reroute proposals: {len(proposals):,}")
    print(f"  total SKUs affected    : {sum(p['old_skus'] for p in proposals):,}")
    print(f"  wrote {PROPOSAL.name}")
    print()
    print("=" * 90)
    print("TOP 20 FNDDS-DRIVEN CONSOLIDATION PROPOSALS")
    print("=" * 90)
    for p in proposals[:20]:
        print(f"\n  fndds={p['fndds_code']}  \"{p['fndds_desc'][:55]}\"  ({p['old_skus']} SKUs to move)")
        print(f"    OLD: {p['old_path']}")
        print(f"    NEW: {p['new_path']}")
        print(f"    (dominant '{p['dominant_family']}' family holds {p['dominant_skus']}/{p['total_skus']} of this code)")

    if not apply_mode:
        return

    # APPLY
    print()
    print("=" * 90)
    print(f"APPLYING {len(rewrite_map):,} path rewrites...")
    print("=" * 90)
    tmp = AUDIT.with_suffix(".tmp.csv")
    log_rows: list[dict] = []
    n_changed = 0
    with AUDIT.open(encoding="utf-8", newline="") as fin, \
         tmp.open("w", encoding="utf-8", newline="") as fout:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
        wtr.writeheader()
        for r in rdr:
            old_cp = (r.get("canonical_path") or "")
            old_rlp = (r.get("retail_leaf_path") or "")
            new_cp = rewrite_map.get(old_cp, old_cp)
            new_rlp = rewrite_map.get(old_rlp, old_rlp)
            if new_cp != old_cp or new_rlp != old_rlp:
                n_changed += 1
                r["canonical_path"] = new_cp
                r["retail_leaf_path"] = new_rlp
                if len(log_rows) < 30000:
                    log_rows.append({
                        "fdc_id": r.get("fdc_id", ""),
                        "old_cp": old_cp, "new_cp": new_cp,
                        "old_rlp": old_rlp, "new_rlp": new_rlp,
                    })
            wtr.writerow(r)
    shutil.move(str(tmp), str(AUDIT))
    print(f"  rows changed: {n_changed:,}")
    if log_rows:
        cols = list(log_rows[0].keys())
        with LOG.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"  wrote {LOG.name}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    main(args.apply)
