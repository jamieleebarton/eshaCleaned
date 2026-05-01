#!/usr/bin/env python3
"""Build the product tree from full_corpus_cleaned.csv.

Reads the cleaned corpus and emits:
  - product_tree.json — nested tree, every node has counts + samples
  - product_tree_nodes.csv — flat node list, one row per node, sortable

Each unique `canonical_path` becomes a leaf. Every prefix becomes an internal
node. Counts roll up: a parent's `n_skus_subtree` is the sum of all leaves
beneath it. `n_skus_at_node` is rows whose canonical_path is exactly this node.

Usage:
    python3 retail_mapper/v2/build_product_tree.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DEFAULT_IN = V2 / "full_corpus_cleaned.csv"
DEFAULT_JSON = V2 / "product_tree.json"
DEFAULT_NODES_CSV = V2 / "product_tree_nodes.csv"

csv.field_size_limit(sys.maxsize)
SAMPLES_PER_NODE = 5
MAX_IDENTITIES_PREVIEW = 20


def main() -> None:
    if not DEFAULT_IN.exists():
        raise SystemExit(f"missing {DEFAULT_IN}")
    print(f"  reading {DEFAULT_IN.name}")

    path_count: Counter = Counter()
    path_identities: dict[str, set] = defaultdict(set)
    path_samples: dict[str, list] = defaultdict(list)

    with DEFAULT_IN.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cp = (row.get("canonical_path") or "").strip()
            if not cp:
                continue
            path_count[cp] += 1
            pid = (row.get("product_identity_fixed") or "").strip()
            if pid:
                path_identities[cp].add(pid)
            if len(path_samples[cp]) < SAMPLES_PER_NODE:
                title = (row.get("title") or "").strip()
                if title and title not in path_samples[cp]:
                    path_samples[cp].append(title)

    print(f"  loaded {sum(path_count.values()):,} SKUs across "
          f"{len(path_count):,} distinct canonical_paths")

    # Build node dict: every prefix of every canonical_path is a node.
    nodes: dict[str, dict] = {}
    for cp, count in path_count.items():
        parts = [p.strip() for p in cp.split(">") if p.strip()]
        for i in range(1, len(parts) + 1):
            prefix = " > ".join(parts[:i])
            if prefix not in nodes:
                nodes[prefix] = {
                    "path": prefix,
                    "name": parts[i - 1],
                    "depth": i,
                    "parent": " > ".join(parts[: i - 1]) if i > 1 else None,
                    "n_skus_at_node": 0,
                    "n_skus_subtree": 0,
                    "identities": set(),
                    "samples": [],
                }
            n = nodes[prefix]
            n["n_skus_subtree"] += count
            n["identities"].update(path_identities[cp])
            for s in path_samples[cp]:
                if len(n["samples"]) < SAMPLES_PER_NODE and s not in n["samples"]:
                    n["samples"].append(s)
        # The full path is itself a node where rows actually land
        nodes[cp]["n_skus_at_node"] += count

    # Build children map for nested rendering
    children_of: dict[str, list[str]] = defaultdict(list)
    for path, node in nodes.items():
        if node["parent"]:
            children_of[node["parent"]].append(path)

    # Mark whether node is leaf (no descendants in the corpus)
    for path, node in nodes.items():
        node["is_leaf"] = len(children_of.get(path, [])) == 0
        node["n_children"] = len(children_of.get(path, []))
        node["n_distinct_identities"] = len(node["identities"])

    # ---- emit nested JSON
    def to_dict(path: str) -> dict:
        n = nodes[path]
        d = {
            "name": n["name"],
            "path": path,
            "depth": n["depth"],
            "is_leaf": n["is_leaf"],
            "n_skus_subtree": n["n_skus_subtree"],
            "n_skus_at_node": n["n_skus_at_node"],
            "n_distinct_identities": n["n_distinct_identities"],
            "sample_identities": sorted(n["identities"])[:MAX_IDENTITIES_PREVIEW],
            "sample_titles": n["samples"][:SAMPLES_PER_NODE],
        }
        kids = sorted(children_of.get(path, []),
                      key=lambda p: -nodes[p]["n_skus_subtree"])
        if kids:
            d["children"] = [to_dict(k) for k in kids]
        return d

    roots = sorted(
        [p for p, n in nodes.items() if n["depth"] == 1],
        key=lambda p: -nodes[p]["n_skus_subtree"],
    )
    tree = {
        "name": "ROOT",
        "n_skus_subtree": sum(path_count.values()),
        "n_distinct_paths": len(path_count),
        "n_distinct_nodes": len(nodes),
        "n_top_levels": len(roots),
        "children": [to_dict(r) for r in roots],
    }
    DEFAULT_JSON.write_text(json.dumps(tree, indent=2))
    print(f"  wrote {DEFAULT_JSON.name} "
          f"({DEFAULT_JSON.stat().st_size / 1024 / 1024:.1f} MB, "
          f"{len(nodes):,} nodes)")

    # ---- emit flat node CSV (one row per node, sortable)
    cols = [
        "path", "depth", "name", "parent",
        "is_leaf", "n_children",
        "n_skus_subtree", "n_skus_at_node",
        "n_distinct_identities",
        "sample_identities", "sample_titles",
    ]
    with DEFAULT_NODES_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        # Sort: by depth, then n_skus desc within depth
        for path in sorted(nodes.keys(),
                           key=lambda p: (nodes[p]["depth"],
                                          -nodes[p]["n_skus_subtree"])):
            n = nodes[path]
            w.writerow({
                "path": path,
                "depth": n["depth"],
                "name": n["name"],
                "parent": n["parent"] or "",
                "is_leaf": int(n["is_leaf"]),
                "n_children": n["n_children"],
                "n_skus_subtree": n["n_skus_subtree"],
                "n_skus_at_node": n["n_skus_at_node"],
                "n_distinct_identities": n["n_distinct_identities"],
                "sample_identities": " | ".join(sorted(n["identities"])[:MAX_IDENTITIES_PREVIEW]),
                "sample_titles": " | ".join(n["samples"][:SAMPLES_PER_NODE]),
            })
    print(f"  wrote {DEFAULT_NODES_CSV.name} ({len(nodes):,} nodes)")

    # ---- summary
    leaves = [n for n in nodes.values() if n["is_leaf"]]
    print()
    print(f"  Tree shape:")
    print(f"    top-levels:   {len(roots)}")
    print(f"    total nodes:  {len(nodes):,}")
    print(f"    leaves:       {len(leaves):,}")
    by_depth: Counter = Counter()
    for n in nodes.values():
        by_depth[n["depth"]] += 1
    for d in sorted(by_depth):
        print(f"    depth {d}:      {by_depth[d]:,}")


if __name__ == "__main__":
    main()
