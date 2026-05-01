#!/usr/bin/env python3
"""Build traversible taxonomy artifacts from semantic product assignments.

``semantic_product_taxonomy.csv`` is row-level: one record per SKU. This script
turns those assignments into a browseable graph/tree:

    Root
      Beverage
        Plant Milk
          Almond Milk
            flavor
              chocolate
            claims
              unsweetened
              organic

Facet values are children for traversal/filtering, but they do not become part
of the canonical product path. That keeps the browse tree stable while still
allowing users or downstream code to drill into variants.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


csv.field_size_limit(sys.maxsize)

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"

DEFAULT_INPUT = V2 / "semantic_product_taxonomy.csv"
DEFAULT_NODES = V2 / "semantic_taxonomy_nodes.csv"
DEFAULT_EDGES = V2 / "semantic_taxonomy_edges.csv"
DEFAULT_ASSIGNMENTS = V2 / "semantic_taxonomy_product_assignments.csv"
DEFAULT_TREE = V2 / "semantic_taxonomy_tree.json"
DEFAULT_SUMMARY = V2 / "semantic_taxonomy_tree_summary.json"

FACET_GROUPS = [
    "variant",
    "flavor",
    "form_texture_cut",
    "processing_storage",
    "claims",
]

NODE_TYPE_ORDER = {
    "root": 0,
    "department": 1,
    "category": 2,
    "product_identity": 3,
    "facet_group": 4,
    "facet_value": 5,
}

ASSIGNMENT_FIELDS = [
    "fdc_id",
    "gtin_upc",
    "title",
    "node_id",
    "canonical_path",
    "canonical_label",
    "retail_type",
    "review_flags",
    "attributes_json",
]

NODE_FIELDS = [
    "node_id",
    "parent_id",
    "node_type",
    "name",
    "path",
    "depth",
    "product_count",
    "clean_product_count",
    "review_product_count",
    "child_count",
    "facet_group",
    "facet_value",
    "sample_fdc_ids",
]

EDGE_FIELDS = [
    "parent_id",
    "child_id",
    "edge_type",
    "parent_type",
    "child_type",
]


@dataclass
class Node:
    node_id: str
    node_type: str
    name: str
    path: str
    parent_id: str = ""
    depth: int = 0
    product_count: int = 0
    clean_product_count: int = 0
    review_product_count: int = 0
    facet_group: str = ""
    facet_value: str = ""
    sample_fdc_ids: list[str] = field(default_factory=list)


def ascii_fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")


def slug(value: str) -> str:
    value = ascii_fold(value).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "blank"


def stable_node_id(node_type: str, path: str) -> str:
    base = f"{node_type}:{slug(path)}"
    digest = hashlib.sha1(f"{node_type}:{path}".encode("utf-8")).hexdigest()[:10]
    if len(base) > 90:
        base = base[:90].rstrip("-")
    return f"{base}:{digest}"


def split_path(path: str) -> list[str]:
    return [part.strip() for part in (path or "").split(">") if part.strip()]


def split_cell(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(" | ") if part.strip()]


def display_group(value: str) -> str:
    return value


def node_key(node_type: str, path: str) -> tuple[str, str]:
    return node_type, path


def ensure_node(
    nodes: dict[tuple[str, str], Node],
    edges: set[tuple[str, str]],
    node_type: str,
    name: str,
    path: str,
    parent: Node | None,
    facet_group: str = "",
    facet_value: str = "",
) -> Node:
    key = node_key(node_type, path)
    if key not in nodes:
        node = Node(
            node_id=stable_node_id(node_type, path),
            node_type=node_type,
            name=name,
            path=path,
            parent_id=parent.node_id if parent else "",
            depth=0 if parent is None else parent.depth + 1,
            facet_group=facet_group,
            facet_value=facet_value,
        )
        nodes[key] = node
    node = nodes[key]
    if parent is not None:
        edges.add((parent.node_id, node.node_id))
    return node


def touch(node: Node, is_review: bool, fdc_id: str) -> None:
    node.product_count += 1
    if is_review:
        node.review_product_count += 1
    else:
        node.clean_product_count += 1
    if fdc_id and len(node.sample_fdc_ids) < 5:
        node.sample_fdc_ids.append(fdc_id)


def iter_taxonomy_nodes(
    row: dict[str, str],
    nodes: dict[tuple[str, str], Node],
    edges: set[tuple[str, str]],
) -> tuple[list[Node], Node | None]:
    root = ensure_node(nodes, edges, "root", "Retail Taxonomy", "Retail Taxonomy", None)
    path_parts = split_path(row.get("canonical_path", ""))
    if len(path_parts) < 2:
        return [root], None

    touched = [root]
    parent = root
    for idx, part in enumerate(path_parts[:-1]):
        path = " > ".join(path_parts[: idx + 1])
        node_type = "department" if idx == 0 else "category"
        parent = ensure_node(nodes, edges, node_type, part, path, parent)
        touched.append(parent)

    product_path = " > ".join(path_parts)
    product = ensure_node(nodes, edges, "product_identity", path_parts[-1], product_path, parent)
    touched.append(product)
    return touched, product


def iter_facet_nodes(
    row: dict[str, str],
    nodes: dict[tuple[str, str], Node],
    edges: set[tuple[str, str]],
    product: Node,
) -> list[Node]:
    touched: list[Node] = []
    for group in FACET_GROUPS:
        values = split_cell(row.get(group, ""))
        if not values:
            continue
        group_path = f"{product.path} > @{group}"
        group_node = ensure_node(
            nodes,
            edges,
            "facet_group",
            display_group(group),
            group_path,
            product,
            facet_group=group,
        )
        touched.append(group_node)
        for value in values:
            value_path = f"{group_path} > {value}"
            value_node = ensure_node(
                nodes,
                edges,
                "facet_value",
                value,
                value_path,
                group_node,
                facet_group=group,
                facet_value=value,
            )
            touched.append(value_node)
    return touched


def build_from_rows(rows: Iterable[dict[str, str]]) -> tuple[dict[tuple[str, str], Node], set[tuple[str, str]], list[dict[str, str]]]:
    nodes: dict[tuple[str, str], Node] = {}
    edges: set[tuple[str, str]] = set()
    assignments: list[dict[str, str]] = []

    for row in rows:
        is_review = bool(row.get("review_flags"))
        fdc_id = row.get("fdc_id", "")
        taxonomy_nodes, product = iter_taxonomy_nodes(row, nodes, edges)
        for node in taxonomy_nodes:
            touch(node, is_review, fdc_id)
        if product is not None:
            for node in iter_facet_nodes(row, nodes, edges, product):
                touch(node, is_review, fdc_id)
            assignments.append(
                {
                    "fdc_id": fdc_id,
                    "gtin_upc": row.get("gtin_upc", ""),
                    "title": row.get("title", ""),
                    "node_id": product.node_id,
                    "canonical_path": row.get("canonical_path", ""),
                    "canonical_label": row.get("canonical_label", ""),
                    "retail_type": row.get("retail_type", ""),
                    "review_flags": row.get("review_flags", ""),
                    "attributes_json": row.get("attributes_json", ""),
                }
            )
    return nodes, edges, assignments


def child_counts(nodes: dict[tuple[str, str], Node], edges: set[tuple[str, str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for parent_id, _child_id in edges:
        counts[parent_id] += 1
    return counts


def write_nodes(path: Path, nodes: dict[tuple[str, str], Node], edges: set[tuple[str, str]]) -> None:
    counts = child_counts(nodes, edges)
    ordered = sorted(
        nodes.values(),
        key=lambda node: (
            node.depth,
            NODE_TYPE_ORDER.get(node.node_type, 99),
            node.path,
        ),
    )
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=NODE_FIELDS)
        writer.writeheader()
        for node in ordered:
            writer.writerow(
                {
                    "node_id": node.node_id,
                    "parent_id": node.parent_id,
                    "node_type": node.node_type,
                    "name": node.name,
                    "path": node.path,
                    "depth": node.depth,
                    "product_count": node.product_count,
                    "clean_product_count": node.clean_product_count,
                    "review_product_count": node.review_product_count,
                    "child_count": counts[node.node_id],
                    "facet_group": node.facet_group,
                    "facet_value": node.facet_value,
                    "sample_fdc_ids": " | ".join(node.sample_fdc_ids),
                }
            )


def write_edges(path: Path, nodes: dict[tuple[str, str], Node], edges: set[tuple[str, str]]) -> None:
    by_id = {node.node_id: node for node in nodes.values()}
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EDGE_FIELDS)
        writer.writeheader()
        for parent_id, child_id in sorted(edges):
            parent = by_id[parent_id]
            child = by_id[child_id]
            writer.writerow(
                {
                    "parent_id": parent_id,
                    "child_id": child_id,
                    "edge_type": "contains",
                    "parent_type": parent.node_type,
                    "child_type": child.node_type,
                }
            )


def write_assignments(path: Path, assignments: list[dict[str, str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ASSIGNMENT_FIELDS)
        writer.writeheader()
        writer.writerows(assignments)


def build_tree_json(nodes: dict[tuple[str, str], Node], edges: set[tuple[str, str]]) -> dict[str, object]:
    by_id = {node.node_id: node for node in nodes.values()}
    children: dict[str, list[str]] = defaultdict(list)
    for parent_id, child_id in edges:
        children[parent_id].append(child_id)

    def sort_key(node_id: str) -> tuple[int, int, str]:
        node = by_id[node_id]
        return (
            NODE_TYPE_ORDER.get(node.node_type, 99),
            -node.product_count,
            node.name,
        )

    def convert(node_id: str) -> dict[str, object]:
        node = by_id[node_id]
        child_ids = sorted(children.get(node_id, []), key=sort_key)
        out: dict[str, object] = {
            "id": node.node_id,
            "type": node.node_type,
            "name": node.name,
            "path": node.path,
            "product_count": node.product_count,
            "clean_product_count": node.clean_product_count,
            "review_product_count": node.review_product_count,
        }
        if node.facet_group:
            out["facet_group"] = node.facet_group
        if node.facet_value:
            out["facet_value"] = node.facet_value
        if node.sample_fdc_ids:
            out["sample_fdc_ids"] = node.sample_fdc_ids
        if child_ids:
            out["children"] = [convert(child_id) for child_id in child_ids]
        return out

    root = next(node for node in nodes.values() if node.node_type == "root")
    return convert(root.node_id)


def summary(nodes: dict[tuple[str, str], Node], edges: set[tuple[str, str]], assignments: list[dict[str, str]]) -> dict[str, object]:
    type_counts = Counter(node.node_type for node in nodes.values())
    root = next(node for node in nodes.values() if node.node_type == "root")
    product_nodes = [node for node in nodes.values() if node.node_type == "product_identity"]
    facet_values = [node for node in nodes.values() if node.node_type == "facet_value"]
    return {
        "assignment_rows": len(assignments),
        "root_product_count": root.product_count,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_type_counts": dict(type_counts),
        "product_identity_nodes": len(product_nodes),
        "facet_value_nodes": len(facet_values),
        "top_product_identity_nodes": [
            {"path": node.path, "product_count": node.product_count}
            for node in sorted(product_nodes, key=lambda item: (-item.product_count, item.path))[:30]
        ],
        "top_facet_value_nodes": [
            {
                "path": node.path,
                "facet_group": node.facet_group,
                "facet_value": node.facet_value,
                "product_count": node.product_count,
            }
            for node in sorted(facet_values, key=lambda item: (-item.product_count, item.path))[:30]
        ],
    }


def build(args: argparse.Namespace) -> None:
    print(f"reading {args.input}", flush=True)
    with args.input.open(newline="", errors="replace") as handle:
        rows = list(csv.DictReader(handle))

    print(f"building tree from {len(rows):,} assignments", flush=True)
    nodes, edges, assignments = build_from_rows(rows)

    args.nodes.parent.mkdir(parents=True, exist_ok=True)
    write_nodes(args.nodes, nodes, edges)
    write_edges(args.edges, nodes, edges)
    write_assignments(args.assignments, assignments)
    args.tree.write_text(json.dumps(build_tree_json(nodes, edges), indent=2, sort_keys=True) + "\n")
    args.summary.write_text(json.dumps(summary(nodes, edges, assignments), indent=2, sort_keys=True) + "\n")

    print(f"wrote {args.nodes}", flush=True)
    print(f"wrote {args.edges}", flush=True)
    print(f"wrote {args.assignments}", flush=True)
    print(f"wrote {args.tree}", flush=True)
    print(f"wrote {args.summary}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build traversible semantic taxonomy tree artifacts.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--nodes", type=Path, default=DEFAULT_NODES)
    parser.add_argument("--edges", type=Path, default=DEFAULT_EDGES)
    parser.add_argument("--assignments", type=Path, default=DEFAULT_ASSIGNMENTS)
    parser.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


if __name__ == "__main__":
    build(parse_args())

