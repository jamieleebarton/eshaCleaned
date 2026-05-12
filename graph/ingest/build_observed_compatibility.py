"""Build observed compatibility edges: ProductCategory -> ESHACategory.

Each edge carries support_count + weak_fallback_share. DESCRIPTIVE, not prescriptive.
This captures what the (rotten) pipeline actually did, marked verified=false.

A cell with high support_count + high fallback_share = structurally suspicious.
"""
from __future__ import annotations

from pathlib import Path

import kuzu
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
STAGING_DIR = ROOT / "graph" / "db" / "_staging"

# "Weak" fallback paths — no category match was available, so the matcher
# fell through to family-only or global. These are the structurally suspect rows.
WEAK_FALLBACK_SOURCES = {"fallback_family", "fallback_global"}


def main() -> None:
    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)

    print("creating OBSERVED_COMPATIBILITY rel table", flush=True)
    try:
        conn.execute("DROP TABLE OBSERVED_COMPATIBILITY")
    except RuntimeError:
        pass
    conn.execute(
        """
        CREATE REL TABLE OBSERVED_COMPATIBILITY(
          FROM ProductCategory TO ESHACategory,
          support_count INT64,
          weak_fallback_count INT64,
          fallback_share DOUBLE,
          verified BOOLEAN
        )
        """
    )

    print("aggregating cells", flush=True)
    res = conn.execute(
        """
        MATCH (pc:ProductCategory)<-[:IN_CATEGORY]-(p:Product)-[m:MAPS_TO]->(e:ESHACode)-[:IN_ESHA_CATEGORY]->(ec:ESHACategory)
        RETURN pc.name AS pc_name,
               ec.name AS ec_name,
               count(*) AS support_count,
               sum(CASE WHEN m.assignment_source IN ['fallback_family','fallback_global'] THEN 1 ELSE 0 END) AS weak_fallback_count
        """
    )
    df = res.get_as_df()
    df["fallback_share"] = df["weak_fallback_count"] / df["support_count"].clip(lower=1)
    df["verified"] = False
    print(f"  cells: {len(df):,}", flush=True)
    print(f"  total support: {df['support_count'].sum():,}", flush=True)
    print(f"  weak fallbacks: {df['weak_fallback_count'].sum():,} ({df['weak_fallback_count'].sum()/max(df['support_count'].sum(),1):.1%})", flush=True)

    print("writing OBSERVED_COMPATIBILITY edges", flush=True)
    edges = df.rename(columns={"pc_name": "from_id", "ec_name": "to_id"})[
        ["from_id", "to_id", "support_count", "weak_fallback_count", "fallback_share", "verified"]
    ]
    edges["support_count"] = edges["support_count"].astype("int64")
    edges["weak_fallback_count"] = edges["weak_fallback_count"].astype("int64")
    edges["fallback_share"] = edges["fallback_share"].astype(float)
    edges["verified"] = edges["verified"].astype(bool)

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    path = STAGING_DIR / "OBSERVED_COMPATIBILITY.parquet"
    edges.to_parquet(path, index=False)
    conn.execute(f"COPY OBSERVED_COMPATIBILITY FROM '{path}'")
    print(f"  loaded {len(edges):,} edges", flush=True)

    path.unlink(missing_ok=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
