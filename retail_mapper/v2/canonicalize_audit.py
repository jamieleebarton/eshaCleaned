#!/usr/bin/env python3
"""Apply unified canonicalize_path to full_corpus_audit.csv.

Steps:
  1. Read current full_corpus_audit.csv
  2. Canonicalize every SKU's canonical_path AND retail_leaf_path
     (synonym normalization, type-echo strip, fixed top-down ordering)
  3. FNDDS-driven duplicate elimination: same FNDDS code → ONE canonical path
     (per (claims_set, form_set) cluster — preserves legitimate sub-types)
  4. Recover lost leaf detail from full_corpus_enriched.csv where audit's
     canonical_path is shallower AND family root matches
  5. Re-canonicalize after recovery (so appended leaves get proper ordering)
  6. Write full_corpus_audit.csv (atomic via .tmp file)

Verification stats printed after each stage.
"""
from __future__ import annotations

import csv
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from path_canonicalizer import (
    canonicalize_path,
    apply_synonym,
    is_claim,
    SYNONYM_MAP,
    title_case,
)

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
ENRICHED = V2 / "full_corpus_enriched.csv"
NEW_AUDIT = V2 / "full_corpus_audit.csv.canonical"

csv.field_size_limit(sys.maxsize)


def stage1_canonicalize_all(rows: list[dict]) -> int:
    """Apply canonicalize_path to every SKU's canonical_path and retail_leaf_path."""
    print("Stage 1: Canonicalizing all paths...")
    n_changed = 0
    for r in rows:
        for col in ("canonical_path", "retail_leaf_path"):
            v = (r.get(col) or "").strip()
            if not v: continue
            segs = v.split(" > ")
            new_v = canonicalize_path(segs)
            if new_v != v:
                r[col] = new_v
                n_changed += 1
    print(f"  paths canonicalized: {n_changed:,}")
    return n_changed


def stage2_fndds_dedupe(rows: list[dict]) -> int:
    """For each FNDDS code, group SKUs by (claims_set, form_words_set).
    Within each cluster, find the dominant canonical_path; reroute outliers.
    Skip NFS catch-all codes."""
    print("Stage 2: FNDDS-driven duplicate elimination...")

    # Group: fndds_code → cluster_key → list of fdc_ids and their canonical_paths
    # cluster_key = (frozenset of claim segments, frozenset of form/processing segments)
    fndds_clusters: dict[tuple, list[tuple]] = defaultdict(list)

    for r in rows:
        fndds = (r.get("fndds_code") or "").strip()
        desc = (r.get("fndds_desc") or "").strip()
        cp = (r.get("canonical_path") or "").strip()
        if not (fndds and cp): continue
        # Skip NFS catch-all codes
        if "NFS" in desc.upper() or "NS AS TO" in desc.upper(): continue

        segs = cp.split(" > ")
        # Extract claim segments (subset matching CLAIM_WORDS)
        claims = frozenset(s.lower() for s in segs if is_claim(s))
        # Differentiation key: claims + family + 2nd-level type
        type_anchor = (segs[1] if len(segs) >= 2 else "").lower()
        cluster_key = (fndds, claims, segs[0].lower(), type_anchor)
        fndds_clusters[cluster_key].append((r, cp))

    n_rerouted = 0
    for cluster_key, members in fndds_clusters.items():
        if len(members) < 2: continue
        path_counter = Counter(m[1] for m in members)
        if len(path_counter) < 2: continue  # all same path, no duplicates
        dominant_path = path_counter.most_common(1)[0][0]
        for r, cp in members:
            if cp != dominant_path:
                r["canonical_path"] = dominant_path
                # Sync retail_leaf if it was equal to canonical
                if (r.get("retail_leaf_path") or "").strip() == cp:
                    r["retail_leaf_path"] = dominant_path
                n_rerouted += 1
    print(f"  SKUs rerouted to dominant FNDDS path: {n_rerouted:,}")
    return n_rerouted


def stage3_recover_from_enriched(rows: list[dict]) -> int:
    """For SKUs where canonical_path is shallower than enriched's retail_leaf_path
    AND family roots match, append enriched's extra leaves (then re-canonicalize)."""
    print("Stage 3: Recovering lost leaf detail from enriched.csv...")

    # Load enriched into dict
    enriched_rlp: dict[str, str] = {}
    enriched_cp: dict[str, str] = {}
    with ENRICHED.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fdc = (r.get("fdc_id") or "").strip()
            if fdc:
                enriched_rlp[fdc] = (r.get("retail_leaf_path") or "").strip()
                enriched_cp[fdc] = (r.get("canonical_path") or "").strip()
    print(f"  enriched loaded: {len(enriched_rlp):,} SKUs")

    n_recovered = 0
    for r in rows:
        fdc = (r.get("fdc_id") or "").strip()
        if not fdc: continue

        cur_cp = (r.get("canonical_path") or "").strip()
        if not cur_cp: continue
        cur_segs = cur_cp.split(" > ")
        cur_family = cur_segs[0]

        # Use enriched.retail_leaf_path as source of leaf detail (it had more flavor info)
        e_path = enriched_rlp.get(fdc, "")
        if not e_path: continue
        e_segs = e_path.split(" > ")

        # Only recover if enriched has SAME family AND more depth
        if not e_segs or e_segs[0] != cur_family: continue
        if len(e_segs) <= len(cur_segs): continue

        # Identify candidate leaf words from enriched that aren't in cur
        cur_lower = {s.lower() for s in cur_segs}
        candidates = [s for s in e_segs[1:] if s.lower() not in cur_lower]
        if not candidates: continue

        # Append candidates and re-canonicalize
        new_segs = cur_segs + candidates
        new_cp = canonicalize_path(new_segs)
        if new_cp != cur_cp:
            r["canonical_path"] = new_cp
            if (r.get("retail_leaf_path") or "").strip() == cur_cp:
                r["retail_leaf_path"] = new_cp
            n_recovered += 1
    print(f"  leaves recovered from enriched: {n_recovered:,}")
    return n_recovered


def stage4_recanonicalize(rows: list[dict]) -> int:
    """Final pass: re-canonicalize after recovery so any appended leaves
    are properly ordered and deduped."""
    print("Stage 4: Final re-canonicalization...")
    n_changed = 0
    for r in rows:
        for col in ("canonical_path", "retail_leaf_path"):
            v = (r.get(col) or "").strip()
            if not v: continue
            new_v = canonicalize_path(v.split(" > "))
            if new_v != v:
                r[col] = new_v
                n_changed += 1
    print(f"  paths re-canonicalized: {n_changed:,}")
    return n_changed


def main():
    print("=" * 70)
    print("Path canonicalization + FNDDS dedupe + leaf recovery")
    print("=" * 70)
    t_start = time.time()

    # Read current audit fully into memory
    print(f"\nReading {AUDIT.name}...")
    t0 = time.time()
    with AUDIT.open(encoding="utf-8", newline="") as fh:
        rdr = csv.DictReader(fh)
        fieldnames = rdr.fieldnames
        rows = list(rdr)
    print(f"  loaded {len(rows):,} rows in {time.time()-t0:.0f}s")
    print()

    # Stage 1: canonicalize
    stage1_canonicalize_all(rows)
    print()

    # Stage 2: FNDDS dedupe
    stage2_fndds_dedupe(rows)
    print()

    # Stage 3: recover from enriched
    stage3_recover_from_enriched(rows)
    print()

    # Stage 4: re-canonicalize
    stage4_recanonicalize(rows)
    print()

    # Write
    print(f"Writing {NEW_AUDIT.name}...")
    t0 = time.time()
    with NEW_AUDIT.open("w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        wtr.writeheader()
        wtr.writerows(rows)
    print(f"  wrote {len(rows):,} rows in {time.time()-t0:.0f}s")
    print(f"  size: {NEW_AUDIT.stat().st_size/1024/1024:.1f} MB")
    print()
    print(f"DONE in {time.time()-t_start:.0f}s")
    print(f"Atomic move: mv {NEW_AUDIT} {AUDIT}")


if __name__ == "__main__":
    main()
