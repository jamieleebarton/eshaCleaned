#!/usr/bin/env python3
"""Build ingredient-only embeddings for the corpus.

Uses sentence-transformers MiniLM (same model as the existing title-based
embeddings) so the spaces are comparable. Encodes the `ingredients_clean`
field (or `ingredients` raw if clean is empty) per fdc_id.

Output:
  retail_mapper/v2/.cache/ingredient_emb.npy   (N × 384)
  retail_mapper/v2/.cache/ingredient_ids.npy   (fdc_id strings, same order)

Skips rows with empty ingredients (~30% of corpus).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DB = REPO / "data" / "master_products.db"
CACHE = V2 / ".cache"
EMB_OUT = CACHE / "ingredient_emb.npy"
IDS_OUT = CACHE / "ingredient_ids.npy"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def main() -> None:
    CACHE.mkdir(exist_ok=True)
    print(f"  loading SentenceTransformer: {MODEL_NAME}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)

    # Pull ingredients per fdc_id from master DB
    print(f"  reading master_products.db ingredients...")
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        SELECT fdc_id, ingredients_clean, ingredients
        FROM products
        WHERE fdc_id IS NOT NULL
          AND (ingredients_clean IS NOT NULL OR ingredients IS NOT NULL)
    """)
    rows: list[tuple[str, str]] = []
    for fdc, ic, ir in c.fetchall():
        text = (ic or ir or "").strip()
        if not text:
            continue
        # Trim to ~600 chars to keep batches fast and prevent outlier-long rows
        rows.append((str(fdc), text[:600]))
    conn.close()
    print(f"  rows with ingredients: {len(rows):,}")

    # Encode in batches
    fdc_ids = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    BATCH = 256
    print(f"  encoding {len(texts):,} ingredient strings (batch {BATCH})...")
    emb = model.encode(
        texts,
        batch_size=BATCH,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    print(f"  embedding shape: {emb.shape}")

    np.save(EMB_OUT, emb.astype(np.float32))
    np.save(IDS_OUT, np.array(fdc_ids, dtype=object), allow_pickle=True)
    print(f"  saved {EMB_OUT.name} + {IDS_OUT.name}")


if __name__ == "__main__":
    main()
