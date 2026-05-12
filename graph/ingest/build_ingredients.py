"""Pass I (part 1): ingest ingredients_clean from master_products.db into Kuzu.

Adds:
  Ingredient(value, doc_count)        — one node per distinct ingredient token
  HAS_INGREDIENT (Product -> Ingredient) edges

Tokenization is the same regex used elsewhere, with extra ingredient-specific
stopwords (contains, less, than, %, of, ingredients, water — but we KEEP
generic single-word foods because their family signal still matters in
aggregate).

After this script, run compute_ingredient_family_stats.py.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import sys
from pathlib import Path

import kuzu
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
PRODUCTS_DB = ROOT / "data" / "master_products.db"
STAGING_DIR = ROOT / "graph" / "db" / "_staging"

INGREDIENT_STOPWORDS = {
    "ingredients", "ingredient", "contains", "containing", "contain",
    "less", "than", "of", "and", "or", "with", "without",
    "may", "include", "includes", "including",
    "trace", "amount", "amounts", "small",
    "natural", "artificial", "flavor", "flavors", "flavoring", "flavorings",
    "color", "colors", "coloring", "added", "fortified", "enriched",
    "organic", "non", "gmo", "free",
    "the", "a", "an", "to", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it", "its",
    "no", "not", "on", "this", "that", "these", "those",
    "ascorbic", "citric",  # acids — generic preservatives
    "modified", "concentrate", "concentrated",
    "high", "fructose", "low",
    "g", "mg", "mcg", "iu", "kg", "ml",
}
# Pure single-character words and numerics already filtered by the regex.

TOKEN_RE = re.compile(r"[a-z][a-z0-9']+")


def tokenize_ingredients(text: str) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in TOKEN_RE.findall(text.lower()):
        # strip trailing apostrophes
        tok = raw.rstrip("'")
        if len(tok) < 3 or tok in INGREDIENT_STOPWORDS:
            continue
        if tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


def main() -> None:
    print("loading ingredients_clean from master_products.db", flush=True)
    con = sqlite3.connect(str(PRODUCTS_DB))
    df = pd.read_sql_query(
        "SELECT gtin_upc, ingredients_clean FROM products WHERE ingredients_clean IS NOT NULL AND length(ingredients_clean) > 5",
        con,
    )
    con.close()
    print(f"  rows with ingredients: {len(df):,}", flush=True)

    print("tokenizing", flush=True)
    df["_tokens"] = df["ingredients_clean"].astype(str).apply(tokenize_ingredients)
    df["n_ingredients"] = df["_tokens"].apply(len)
    print(f"  median ingredients/product: {df['n_ingredients'].median():.0f}", flush=True)
    print(f"  total (Product, Ingredient) pairs: {df['n_ingredients'].sum():,}", flush=True)

    pairs = df[["gtin_upc", "_tokens"]].explode("_tokens").dropna()
    pairs = pairs[pairs["_tokens"].astype(str) != ""].drop_duplicates()
    pairs = pairs.rename(columns={"gtin_upc": "from_id", "_tokens": "to_id"})
    print(f"  HAS_INGREDIENT edges to insert: {len(pairs):,}", flush=True)

    # distinct Ingredient nodes
    ingredients_df = (
        pairs.groupby("to_id").size().reset_index(name="doc_count").rename(columns={"to_id": "value"})
    )
    print(f"  distinct Ingredients: {len(ingredients_df):,}", flush=True)
    print(f"  top 15 most-frequent ingredients:", flush=True)
    print(ingredients_df.sort_values("doc_count", ascending=False).head(15).to_string(index=False), flush=True)

    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)

    print("creating schema (if not present)", flush=True)
    try:
        conn.execute("DROP TABLE HAS_INGREDIENT")
    except RuntimeError:
        pass
    try:
        conn.execute("DROP TABLE Ingredient")
    except RuntimeError:
        pass
    conn.execute("CREATE NODE TABLE Ingredient(value STRING, doc_count INT64 DEFAULT 0, family_entropy DOUBLE DEFAULT 0.0, num_esha_categories INT64 DEFAULT 0, PRIMARY KEY(value))")
    conn.execute("CREATE REL TABLE HAS_INGREDIENT(FROM Product TO Ingredient)")

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    ingredients_df["family_entropy"] = 0.0
    ingredients_df["num_esha_categories"] = 0
    ingredients_df = ingredients_df[["value", "doc_count", "family_entropy", "num_esha_categories"]]
    ing_path = STAGING_DIR / "Ingredient.parquet"
    ingredients_df.to_parquet(ing_path, index=False)
    conn.execute(f"COPY Ingredient FROM '{ing_path}'")
    print(f"  loaded {len(ingredients_df):,} Ingredient nodes", flush=True)
    ing_path.unlink(missing_ok=True)

    edge_path = STAGING_DIR / "HAS_INGREDIENT.parquet"
    pairs.to_parquet(edge_path, index=False)
    conn.execute(f"COPY HAS_INGREDIENT FROM '{edge_path}'")
    print(f"  loaded {len(pairs):,} HAS_INGREDIENT edges", flush=True)
    edge_path.unlink(missing_ok=True)

    print("done", flush=True)


if __name__ == "__main__":
    main()
