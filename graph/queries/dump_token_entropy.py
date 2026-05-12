"""Dump Token.entropy from the Kuzu graph to a CSV the matcher can read.

The matcher (build_product_to_best_esha_full_map.py) doesn't import kuzu;
this hand-off file keeps the matcher's deps clean.
"""
from __future__ import annotations

from pathlib import Path

import kuzu

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
OUT = ROOT / "data" / "token_entropy.csv"


def main() -> None:
    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)
    df = conn.execute(
        """
        MATCH (t:Token)
        RETURN t.value AS token, t.entropy AS entropy, t.doc_count AS doc_count, t.num_esha_categories AS num_esha_categories
        """
    ).get_as_df()
    print(f"  tokens: {len(df):,}", flush=True)
    print(f"  max entropy: {df['entropy'].max():.4f}", flush=True)
    df.to_csv(OUT, index=False)
    print(f"  wrote {OUT.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
