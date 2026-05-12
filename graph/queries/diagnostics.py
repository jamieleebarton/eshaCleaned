"""Run v0.1 diagnostic Cypher queries against the Kuzu graph and write CSV reports.

Five reports:
  1. attractor_esha.csv         — ESHA codes receiving products from many ProductCategories
  2. trapdoor_tokens.csv        — Tokens by entropy (data-driven trapdoor signal)
  3. brand_incoherence.csv      — Brands whose SKUs span many ESHA categories
  4. category_incoherence.csv   — PC x EC cells with high fallback_share + support
  5. fallback_concentration.csv — ESHA codes absorbing the most weak fallbacks
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import kuzu
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
OUT_DIR = ROOT / "graph" / "diagnostics"


REPORTS: list[tuple[str, str, str]] = [
    (
        "attractor_esha.csv",
        "ESHA codes receiving products from many distinct ProductCategories. Top of list is structurally suspicious — one ESHA target absorbing semantically incompatible inputs.",
        """
        MATCH (e:ESHACode)<-[:MAPS_TO]-(p:Product)-[:IN_CATEGORY]->(pc:ProductCategory)
        WITH e, count(DISTINCT pc) AS num_distinct_product_categories, count(DISTINCT p) AS total_products
        WHERE num_distinct_product_categories >= 3
        RETURN e.code AS esha_code,
               e.description AS esha_description,
               num_distinct_product_categories,
               total_products
        ORDER BY num_distinct_product_categories DESC, total_products DESC
        LIMIT 200
        """,
    ),
    (
        "trapdoor_tokens.csv",
        "Tokens ranked by entropy across ESHA categories. High entropy = token spans many categories evenly = weak signal that drags products into wrong categories. 'apple' is the canonical trapdoor.",
        """
        MATCH (t:Token)
        WHERE t.doc_count >= 50
        RETURN t.value AS token,
               t.entropy AS entropy,
               t.doc_count AS doc_count,
               t.num_esha_categories AS num_esha_categories
        ORDER BY t.entropy DESC, t.doc_count DESC
        LIMIT 500
        """,
    ),
    (
        "brand_incoherence.csv",
        "Brands whose products span 3+ ESHA categories. A coherent brand should concentrate on one category cluster. Wide spread = either bad mappings or a multi-category brand (e.g. retailer house brand).",
        # Computed in two passes + pandas merge in main(); skip plain Cypher here.
        "",
    ),
    (
        "category_incoherence.csv",
        "ProductCategory x ESHACategory cells where weak fallbacks dominate. These are the structurally-bad cells: a Soda's products should not be landing in a Fresh Fruit ESHA cluster.",
        """
        MATCH (pc:ProductCategory)-[oc:OBSERVED_COMPATIBILITY]->(ec:ESHACategory)
        WHERE oc.support_count >= 50 AND oc.fallback_share >= 0.3
        RETURN pc.name AS product_category,
               ec.name AS esha_category,
               oc.support_count AS support_count,
               oc.weak_fallback_count AS weak_fallback_count,
               oc.fallback_share AS fallback_share
        ORDER BY oc.fallback_share DESC, oc.support_count DESC
        LIMIT 300
        """,
    ),
    (
        "fallback_concentration.csv",
        "ESHA codes ranked by absolute count of weak fallbacks (fallback_family / fallback_global). Pairs with attractor_esha.csv to triangulate the worst targets.",
        """
        MATCH (e:ESHACode)<-[m:MAPS_TO]-(p:Product)
        WHERE m.assignment_source IN ['fallback_family','fallback_global']
        WITH e, count(*) AS weak_fallback_count
        MATCH (e)<-[m2:MAPS_TO]-(:Product)
        WITH e, weak_fallback_count, count(m2) AS total_assignments
        WHERE weak_fallback_count >= 10
        RETURN e.code AS esha_code,
               e.description AS esha_description,
               weak_fallback_count,
               total_assignments,
               (CAST(weak_fallback_count AS DOUBLE) / total_assignments) AS weak_fallback_share
        ORDER BY weak_fallback_count DESC
        LIMIT 200
        """,
    ),
]


def write_report(path: Path, header_note: str, query: str, df: pd.DataFrame) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    note = "# " + header_note.replace("\n", " ")
    src = "# query: " + " ".join(textwrap.dedent(query).split())
    with path.open("w", encoding="utf-8") as fh:
        fh.write(note + "\n")
        fh.write(src + "\n")
        df.to_csv(fh, index=False)


def run_brand_incoherence(conn: kuzu.Connection) -> tuple[pd.DataFrame, str]:
    """Two-pass brand incoherence: spread first, then weak-fallback counts."""
    spread_q = """
        MATCH (b:Brand)<-[:MADE_BY]-(p:Product)-[:MAPS_TO]->(:ESHACode)-[:IN_ESHA_CATEGORY]->(c:ESHACategory)
        WITH b,
             count(DISTINCT c) AS num_esha_categories,
             count(DISTINCT p) AS total_skus
        WHERE num_esha_categories >= 3 AND total_skus >= 10
        RETURN b.name AS brand, num_esha_categories, total_skus
    """
    wf_q = """
        MATCH (b:Brand)<-[:MADE_BY]-(p:Product)-[m:MAPS_TO]->(:ESHACode)
        WHERE m.assignment_source = 'fallback_family' OR m.assignment_source = 'fallback_global'
        RETURN b.name AS brand, count(DISTINCT p) AS weak_fallbacks
    """
    spread = conn.execute(spread_q).get_as_df()
    wf = conn.execute(wf_q).get_as_df()
    merged = spread.merge(wf, on="brand", how="left")
    merged["weak_fallbacks"] = merged["weak_fallbacks"].fillna(0).astype("int64")
    merged["fallback_share"] = merged["weak_fallbacks"] / merged["total_skus"].clip(lower=1)
    merged = merged.sort_values(["num_esha_categories", "total_skus"], ascending=[False, False]).head(300).reset_index(drop=True)
    return merged, spread_q + "\n----\n" + wf_q


def main() -> None:
    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)

    for filename, note, query in REPORTS:
        print(f"running {filename}", flush=True)
        if filename == "brand_incoherence.csv":
            df, query = run_brand_incoherence(conn)
        else:
            res = conn.execute(textwrap.dedent(query).strip())
            df = res.get_as_df()
        path = OUT_DIR / filename
        write_report(path, note, query, df)
        print(f"  rows: {len(df):,}  ->  {path.relative_to(ROOT)}", flush=True)

    print("\ntop 10 attractor ESHA codes:", flush=True)
    df = pd.read_csv(OUT_DIR / "attractor_esha.csv", comment="#")
    for _, row in df.head(10).iterrows():
        print(f"  {row['esha_code']:>6}  {row['esha_description'][:50]:<50}  PCs={row['num_distinct_product_categories']:>3}  total={row['total_products']:>6,}", flush=True)

    print("\ntop 10 trapdoor tokens:", flush=True)
    df = pd.read_csv(OUT_DIR / "trapdoor_tokens.csv", comment="#")
    for _, row in df.head(10).iterrows():
        print(f"  {row['token']:<20} H={row['entropy']:.3f}  docs={int(row['doc_count']):>7,}  cats={int(row['num_esha_categories']):>3}", flush=True)

    print("\ntop 10 incoherent brands:", flush=True)
    df = pd.read_csv(OUT_DIR / "brand_incoherence.csv", comment="#")
    for _, row in df.head(10).iterrows():
        print(f"  {row['brand'][:30]:<30}  cats={row['num_esha_categories']:>3}  skus={row['total_skus']:>5,}  wf%={row['fallback_share']:.1%}", flush=True)

    print("\ntop 10 worst PC×EC cells:", flush=True)
    df = pd.read_csv(OUT_DIR / "category_incoherence.csv", comment="#")
    for _, row in df.head(10).iterrows():
        print(f"  {row['product_category'][:35]:<35} -> {row['esha_category']:<15}  support={row['support_count']:>5,}  wf%={row['fallback_share']:.1%}", flush=True)

    print("\ntop 10 fallback concentration ESHA codes:", flush=True)
    df = pd.read_csv(OUT_DIR / "fallback_concentration.csv", comment="#")
    for _, row in df.head(10).iterrows():
        print(f"  {row['esha_code']:>6}  {row['esha_description'][:45]:<45}  wf={int(row['weak_fallback_count']):>5,}  share={row['weak_fallback_share']:.1%}", flush=True)


if __name__ == "__main__":
    main()
