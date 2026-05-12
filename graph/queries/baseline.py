"""Compute v0.1 baseline metrics. Writes graph/baseline.json.

These numbers are what every later remediation pass tries to drive down.
"""
from __future__ import annotations

import json
from pathlib import Path

import kuzu

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
OUT = ROOT / "graph" / "baseline.json"


def scalar(conn: kuzu.Connection, query: str) -> int:
    df = conn.execute(query).get_as_df()
    if df.empty:
        return 0
    return int(df.iloc[0, 0])


def main() -> None:
    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)

    metrics: dict[str, int | float] = {}

    metrics["total_products"] = scalar(conn, "MATCH (p:Product) RETURN count(p)")
    metrics["total_maps_to_edges"] = scalar(conn, "MATCH ()-[m:MAPS_TO]->() RETURN count(m)")
    metrics["fallback_family"] = scalar(
        conn,
        "MATCH ()-[m:MAPS_TO]->() WHERE m.assignment_source = 'fallback_family' RETURN count(m)",
    )
    metrics["fallback_global"] = scalar(
        conn,
        "MATCH ()-[m:MAPS_TO]->() WHERE m.assignment_source = 'fallback_global' RETURN count(m)",
    )
    metrics["fallback_category"] = scalar(
        conn,
        "MATCH ()-[m:MAPS_TO]->() WHERE m.assignment_source = 'fallback_category' RETURN count(m)",
    )
    metrics["fallback_category_family"] = scalar(
        conn,
        "MATCH ()-[m:MAPS_TO]->() WHERE m.assignment_source = 'fallback_category_family' RETURN count(m)",
    )
    metrics["legacy_best_map"] = scalar(
        conn,
        "MATCH ()-[m:MAPS_TO]->() WHERE m.assignment_source = 'legacy_best_map' RETURN count(m)",
    )
    metrics["weak_fallback_total"] = metrics["fallback_family"] + metrics["fallback_global"]
    metrics["weak_fallback_score_lt_12"] = scalar(
        conn,
        """
        MATCH ()-[m:MAPS_TO]->()
        WHERE (m.assignment_source = 'fallback_family' OR m.assignment_source = 'fallback_global')
          AND m.score < 12
        RETURN count(m)
        """,
    )
    total = max(metrics["total_maps_to_edges"], 1)
    metrics["weak_fallback_share"] = round(metrics["weak_fallback_total"] / total, 4)
    metrics["headline_score_lt_12_share"] = round(metrics["weak_fallback_score_lt_12"] / total, 4)

    metrics["distinct_attractor_esha_3plus_pcs"] = scalar(
        conn,
        """
        MATCH (e:ESHACode)<-[:MAPS_TO]-(:Product)-[:IN_CATEGORY]->(pc:ProductCategory)
        WITH e, count(DISTINCT pc) AS n
        WHERE n >= 3
        RETURN count(e)
        """,
    )

    OUT.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
