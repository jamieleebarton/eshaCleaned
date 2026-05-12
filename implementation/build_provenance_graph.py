from __future__ import annotations

import argparse
import json
from pathlib import Path

from provenance_graph import DEFAULT_GRAPH_DB, build_graph, trace_entity


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or query the derived provenance graph")
    parser.add_argument("--out", type=Path, default=DEFAULT_GRAPH_DB)
    parser.add_argument("--trace-kind", choices=("canonical", "normalized_item", "esha_code", "gtin", "pack", "contract"))
    parser.add_argument("--trace-key")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    if args.trace_kind and args.trace_key:
        payload = trace_entity(args.trace_kind, args.trace_key, db_path=args.out, edge_limit=args.limit)
    else:
        counts = build_graph(args.out)
        payload = {
            "graph_db": str(args.out),
            "node_count": counts.node_count,
            "edge_count": counts.edge_count,
            "artifact_count": counts.artifact_count,
            "dependency_count": counts.dependency_count,
        }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
