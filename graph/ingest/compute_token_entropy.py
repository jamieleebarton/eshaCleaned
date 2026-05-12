"""Compute Shannon entropy of each Token's distribution across ESHACategory.

High entropy = trapdoor token (spans many categories, weak signal).
Low entropy = informative token (concentrates on few categories, strong signal).

Writes back to Token.entropy / Token.doc_count / Token.num_esha_categories.
"""
from __future__ import annotations

from pathlib import Path

import kuzu
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"


def main() -> None:
    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)

    print("querying (token, esha_category, count) distribution", flush=True)
    res = conn.execute(
        """
        MATCH (p:Product)-[:HAS_TOKEN]->(t:Token),
              (p)-[:MAPS_TO]->(e:ESHACode)-[:IN_ESHA_CATEGORY]->(c:ESHACategory)
        RETURN t.value AS token, c.name AS category, count(*) AS n
        """
    )
    df = res.get_as_df()
    print(f"  ({len(df):,} (token, category) cells)", flush=True)

    if df.empty:
        print("no data", flush=True)
        return

    print("computing entropy", flush=True)

    def entropy(group: pd.DataFrame) -> pd.Series:
        counts = group["n"].to_numpy(dtype=float)
        total = counts.sum()
        if total <= 0:
            return pd.Series({"entropy": 0.0, "doc_count": 0, "num_esha_categories": 0})
        p = counts / total
        # mask zeros to avoid log(0)
        nz = p > 0
        h = float(-(p[nz] * np.log2(p[nz])).sum())
        return pd.Series({"entropy": h, "doc_count": int(total), "num_esha_categories": int(len(group))})

    agg = df.groupby("token", as_index=False).apply(entropy, include_groups=False)
    if "token" not in agg.columns:
        agg = agg.reset_index()
    print(f"  tokens with entropy: {len(agg):,}", flush=True)
    print(f"  top 10 by entropy:", flush=True)
    for _, row in agg.nlargest(10, "entropy").iterrows():
        print(f"    {row['token']:<20} H={row['entropy']:.3f}  docs={int(row['doc_count']):>7,}  cats={int(row['num_esha_categories']):>3}", flush=True)

    print("writing back to Token nodes", flush=True)
    rows = agg[["token", "entropy", "doc_count", "num_esha_categories"]].to_dict("records")
    for row in rows:
        row["entropy"] = float(row["entropy"])
        row["doc_count"] = int(row["doc_count"])
        row["num_esha_categories"] = int(row["num_esha_categories"])

    conn.execute(
        """
        UNWIND $rows AS r
        MATCH (t:Token {value: r.token})
        SET t.entropy = r.entropy,
            t.doc_count = r.doc_count,
            t.num_esha_categories = r.num_esha_categories
        """,
        parameters={"rows": rows},
    )
    print("done", flush=True)


if __name__ == "__main__":
    main()
