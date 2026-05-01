#!/usr/bin/env python3
"""Build the path-only input file for DeepSeek structural normalization.

Reads `full_corpus_audit.csv`, extracts every UNIQUE canonical_path, groups
by top-level family (Dairy / Frozen / Snack / etc), and writes one JSONL
batch per family. The LLM gets path strings — no SKUs, no titles, no samples.

Why path-only: the structural fixes (Aged Cheddar → Cheddar > Aged, bottom-up
leaves → top-down hierarchy, splitting flat buckets like "Dairy > Cheese"
into typed children) are pure string transforms. They don't depend on what
products sit at the path. Stripping the SKU evidence drops token cost ~90%
and makes the output more deterministic.

Output:
  - retail_mapper/v2/deepseek_input.jsonl  — one batch per top-level family.
    Each line: {"family": "Dairy", "paths": ["Dairy > Cheese > ...", ...]}

Usage:
    python3 retail_mapper/v2/build_deepseek_input.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SRC = V2 / "full_corpus_audit.csv"
OUT_JSONL = V2 / "deepseek_input.jsonl"

csv.field_size_limit(sys.maxsize)

# Send paths in batches grouped by top-level family. The LLM benefits from
# seeing all paths in a family at once (it can spot the "Cheddar appears in
# 7 different leaf shapes" pattern). One JSONL line per family.


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}")
    print(f"  reading {SRC.name}")

    paths: set[str] = set()
    with SRC.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cp = (row.get("canonical_path") or "").strip()
            if cp:
                paths.add(cp)

    print(f"  unique paths: {len(paths):,}")

    # Group by top-level family
    by_family: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        family = p.split(" > ", 1)[0].strip() if " > " in p else p
        by_family[family].append(p)

    # Sort each family's paths so the LLM sees structure
    for family in by_family:
        by_family[family].sort()

    print(f"  top-level families: {len(by_family):,}")
    for family in sorted(by_family, key=lambda f: -len(by_family[f])):
        print(f"    {family:30s}  {len(by_family[family]):>4} paths")

    with OUT_JSONL.open("w", encoding="utf-8") as fh:
        for family in sorted(by_family):
            fh.write(json.dumps({
                "family": family,
                "paths": by_family[family],
            }, ensure_ascii=False) + "\n")
    print(f"  wrote {OUT_JSONL.name}")


if __name__ == "__main__":
    main()
