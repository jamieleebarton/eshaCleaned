#!/usr/bin/env python3
"""Surface duplicate / equivalent canonical_paths in the FDC tree using the
LLM-classified outputs as votes.

Three signals:

  A. Same htc_code, multiple distinct canonical_paths
     -> The FDC tree has multiple paths that resolve to the same identity
        bucket. Strong dedup candidate.

  B. Same canonical_label across different canonical_paths
     -> Same food name but two different parents in the tree. Naming drift.

  C. Same llm_canonical_path mapped to multiple FDC paths
     -> The LLM consistently emits one path but our fuzzy matcher chose
        different FDC homes for it. Either the LLM is right and FDC has
        redundancy, or the matcher is splitting them.

Output: recipe_pricing/output/canonical_path_dedup_candidates.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
DEFAULT_ING = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
DEFAULT_OUT = ROOT / "recipe_pricing" / "output" / "canonical_path_dedup_candidates.csv"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", type=Path, default=DEFAULT_API)
    ap.add_argument("--ing", type=Path, default=DEFAULT_ING)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    rows: list[dict] = []
    for p in (args.api, args.ing):
        if not p.exists():
            continue
        with p.open() as f:
            for r in csv.DictReader(f):
                rows.append(r)

    if not rows:
        print("no rows found", file=sys.stderr)
        return 1

    print(f"loaded {len(rows):,} tagged rows", file=sys.stderr)

    # Signal A: same htc_code -> distinct canonical_paths
    code_to_paths: dict[str, Counter] = defaultdict(Counter)
    code_to_titles: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        code = r["htc_code"]
        path = r["canonical_path"]
        if code and path:
            code_to_paths[code][path] += 1
            if len(code_to_titles[code]) < 3:
                code_to_titles[code].append(r["title"])

    # Signal B: same canonical_label -> distinct canonical_paths
    label_to_paths: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        label = r.get("canonical_label", "").strip()
        path = r.get("canonical_path", "").strip()
        if label and path:
            label_to_paths[label][path] += 1

    # Signal C: same llm_canonical_path -> distinct FDC canonical_paths
    llm_to_paths: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        llm = r.get("llm_canonical_path", "").strip()
        path = r.get("canonical_path", "").strip()
        if llm and path and llm != path:
            llm_to_paths[llm][path] += 1

    # Emit dedup candidate report.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_rows: list[dict] = []

    # Signal A rows
    for code, paths in code_to_paths.items():
        if len(paths) <= 1:
            continue
        ranked = paths.most_common()
        out_rows.append({
            "signal": "A_same_htc_code",
            "key": code,
            "n_distinct_paths": len(paths),
            "total_rows": sum(paths.values()),
            "candidate_paths": " || ".join(f"{p} ({c})" for p, c in ranked),
            "sample_titles": " || ".join(code_to_titles.get(code, [])),
        })

    # Signal B rows (only label collisions where labels look like the same food)
    for label, paths in label_to_paths.items():
        if len(paths) <= 1:
            continue
        ranked = paths.most_common()
        out_rows.append({
            "signal": "B_same_label",
            "key": label,
            "n_distinct_paths": len(paths),
            "total_rows": sum(paths.values()),
            "candidate_paths": " || ".join(f"{p} ({c})" for p, c in ranked),
            "sample_titles": "",
        })

    # Signal C
    for llm, paths in llm_to_paths.items():
        if len(paths) <= 1:
            continue
        ranked = paths.most_common()
        out_rows.append({
            "signal": "C_same_llm_path",
            "key": llm,
            "n_distinct_paths": len(paths),
            "total_rows": sum(paths.values()),
            "candidate_paths": " || ".join(f"{p} ({c})" for p, c in ranked),
            "sample_titles": "",
        })

    out_rows.sort(key=lambda r: (-r["total_rows"], -r["n_distinct_paths"]))

    cols = ["signal", "key", "n_distinct_paths", "total_rows",
            "candidate_paths", "sample_titles"]
    with args.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)

    print(f"wrote {len(out_rows):,} dedup candidate rows -> {args.out}")
    by_signal = Counter(r["signal"] for r in out_rows)
    for s, n in by_signal.most_common():
        print(f"  {s}: {n:,}")

    # Top 15 strongest candidates by total_rows
    print("\nTop 15 strongest dedup candidates:")
    for r in out_rows[:15]:
        print(f"  [{r['signal']}] key={r['key']!r} n={r['n_distinct_paths']} rows={r['total_rows']}")
        print(f"    -> {r['candidate_paths'][:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
