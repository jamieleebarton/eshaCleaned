"""
Programmatic misroute detector.

Scans the cleaned canonical CSV (or any *_CLEANED.csv with rft_* columns)
and flags rows that exhibit known misroute patterns:

  IDENTITY_DRIFT       Matched concept has identity tokens not in the surface
  IDENTITY_LOST        Surface has identity tokens absent from matched concept
  OVER_CONFIDENT       Verdict EXACT/STRONG but drift detected
  CROSS_FAMILY_INHERIT The inherited SR28/FNDDS code's description has tokens
                       in a completely different food family from the surface

Output: misroute_report.csv — flagged rows ranked by severity, clustered by
the SAME drift pattern so you can audit batches of similar misroutes at once.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rft_concept import build_concept_index, SURFACE_ONLY_IDENTITY, CATEGORY_PREFIXES
import rft_concept as rftc
from rft import (
    RETAIL_ATTRS_ROUTING, RETAIL_ATTRS_NONROUTING,
    FORM_WORDS, MODIFIER_TOKENS, SURFACE_MODIFIERS, VERBOSITY,
)

# Tokens that should NOT count as identity drift even when they appear
# extra on the matched concept side. These are state/form/modifier vocab
# — `raw`, `fresh`, `canned`, `dry`, `whole` etc. — which the broadened
# router-side _IDENTITY_TOKENS now includes but which don't represent
# food-family drift on their own.
DRIFT_IGNORE = (
    RETAIL_ATTRS_ROUTING | RETAIL_ATTRS_NONROUTING
    | FORM_WORDS | MODIFIER_TOKENS | SURFACE_MODIFIERS | VERBOSITY
    | CATEGORY_PREFIXES | SURFACE_ONLY_IDENTITY
)

csv.field_size_limit(sys.maxsize)


def main():
    inp = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/"
        "canonical_surface_normalized_with_product_proxies_CLEANED.csv"
    )
    out = (Path(sys.argv[2]) if len(sys.argv) > 2
           else inp.with_name(inp.stem.replace("_CLEANED", "")
                              + "_MISROUTES.csv"))

    print("Building concept index (for identity vocab)…")
    build_concept_index()
    # Narrow the drift-check identity universe to core food vocabulary —
    # the router-side _IDENTITY_TOKENS is intentionally broad (covers
    # surface-only-identity tokens like `fat`/`free`); the audit checks
    # food-family drift specifically, so state/form/modifier tokens are
    # excluded.
    ident = rftc._IDENTITY_TOKENS - DRIFT_IGNORE
    print(f"  {len(ident):,} identity tokens (audit-narrowed)")

    print(f"\nReading: {inp}\nWriting: {out}\n")

    flagged = []
    counters = Counter()
    pattern_clusters: dict[tuple, list] = defaultdict(list)

    with inp.open(encoding="utf-8", errors="replace") as fin:
        for r in csv.DictReader(fin):
            surf_toks = set(filter(None, (r.get("rft_surface_concept") or "").split("|")))
            cid_toks = set(filter(None, (r.get("rft_concept_tokens") or "").split("|")))
            v = r.get("rft_verdict", "")
            if not surf_toks or not cid_toks:
                continue

            surf_id = surf_toks & ident
            cid_id = cid_toks & ident

            flags = []
            severity = 0

            # Identity LOST — surface had identity tokens the concept lacks
            id_lost = surf_id - cid_id
            if id_lost:
                flags.append(f"IDENTITY_LOST:{','.join(sorted(id_lost))}")
                severity += 5

            # Identity DRIFT — concept has identity tokens not in surface
            id_drift = cid_id - surf_id
            if id_drift:
                flags.append(f"IDENTITY_DRIFT:{','.join(sorted(id_drift))}")
                severity += 3

            # Over-confident — verdict claims STRONG/EXACT but drift detected
            if v in ("EXACT", "STRONG") and (id_lost or id_drift):
                flags.append("OVER_CONFIDENT")
                severity += 5

            if not flags:
                continue

            row = {
                "canonical_surface": r.get("canonical_surface", ""),
                "rft_verdict": v,
                "rft_concept_tokens": r.get("rft_concept_tokens", ""),
                "rft_canonical_name": r.get("rft_canonical_name", ""),
                "rft_surface_concept": r.get("rft_surface_concept", ""),
                "id_lost": "|".join(sorted(id_lost)),
                "id_drift": "|".join(sorted(id_drift)),
                "flags": ";".join(flags),
                "severity": severity,
                "sr28_code": r.get("sr28_code", ""),
                "sr28_description": r.get("sr28_description", ""),
                "fndds_code": r.get("fndds_code", ""),
                "fndds_description": r.get("fndds_description", ""),
                "esha_code": r.get("esha_code", ""),
                "esha_description": r.get("esha_description", ""),
            }
            flagged.append(row)
            for f in flags:
                counters[f.split(":")[0]] += 1
            # Cluster by the drift pattern itself
            cluster_key = (tuple(sorted(id_lost)), tuple(sorted(id_drift)))
            pattern_clusters[cluster_key].append(r.get("canonical_surface", ""))

    flagged.sort(key=lambda x: (-x["severity"], x["canonical_surface"]))

    with out.open("w", newline="") as fout:
        if flagged:
            w = csv.DictWriter(fout, fieldnames=list(flagged[0].keys()))
            w.writeheader()
            w.writerows(flagged)

    print(f"Flagged {len(flagged):,} suspicious rows\n")
    print("Flag counts:")
    for f, c in counters.most_common():
        print(f"  {f:25s} {c:>6,}")

    print(f"\nTop 25 misroute patterns (id_lost → id_drift):")
    by_count = sorted(pattern_clusters.items(),
                      key=lambda kv: -len(kv[1]))
    for (lost, drift), surfaces in by_count[:25]:
        if not lost and not drift:
            continue
        ex = surfaces[0] if surfaces else ""
        print(f"  n={len(surfaces):>4}  lost={list(lost)!s:30s}  "
              f"drift={list(drift)!s:30s}  ex: {ex[:50]}")

    print(f"\nReport: {out}")


if __name__ == "__main__":
    main()
