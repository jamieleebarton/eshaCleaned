"""Export evidence-cluster conflict queues from the Kuzu graph.

This reads the evidence-first graph built by graph/ingest/build_kuzu_graph.py.
It does not remap products. It reports where the incumbent vM assignment is
structurally rejected, scattered across many ESHA codes, weak/no-dominant, or
unassigned at the cluster level.
"""
from __future__ import annotations

import json
from pathlib import Path

import kuzu
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
OUT_DIR = ROOT / "graph" / "review"
OUT_CONFLICTS = OUT_DIR / "evidence_cluster_conflicts_from_graph.csv"
OUT_STRUCTURAL = OUT_DIR / "evidence_cluster_structural_rejects_from_graph.csv"
OUT_SUMMARY = OUT_DIR / "evidence_cluster_conflicts_summary.json"


def query(conn: kuzu.Connection, q: str) -> pd.DataFrame:
    return conn.execute(q).get_as_df()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)

    clusters = query(
        conn,
        """
        MATCH (ic:IngredientCluster)
        WHERE ic.audit_flags <> ''
        RETURN ic.id AS ingredient_cluster_id,
               ic.signature AS ingredient_signature,
               ic.n_products AS n_products,
               ic.category_top_share AS category_top_share,
               ic.current_code_count AS current_code_count,
               ic.current_reject_reason AS current_reject_reason,
               ic.audit_flags AS audit_flags
        ORDER BY ic.n_products DESC, ic.category_top_share DESC
        """,
    )

    current = query(
        conn,
        """
        MATCH (ic:IngredientCluster)-[r:CLUSTER_CURRENT_TOP_ESHA]->(e:ESHACode)-[:HAS_ESHA_HEAD]->(h:ESHAHead)
        WHERE ic.audit_flags <> ''
        RETURN ic.id AS ingredient_cluster_id,
               e.code AS current_top_code,
               e.description AS current_top_description,
               h.name AS current_top_head,
               r.share AS current_code_top_share,
               r.code_count AS current_code_count_from_edge,
               r.reject_reason AS current_reject_reason_from_edge
        """,
    )

    categories = query(
        conn,
        """
        MATCH (ic:IngredientCluster)-[r:CLUSTER_DOMINANT_CATEGORY]->(pc:ProductCategory)
        WHERE ic.audit_flags <> ''
        RETURN ic.id AS ingredient_cluster_id,
               pc.name AS dominant_category,
               r.share AS dominant_category_share
        """,
    )

    brands = query(
        conn,
        """
        MATCH (ic:IngredientCluster)-[r:CLUSTER_DOMINANT_BRAND]->(b:Brand)
        WHERE ic.audit_flags <> ''
        RETURN ic.id AS ingredient_cluster_id,
               b.name AS dominant_brand,
               r.share AS dominant_brand_share
        """,
    )

    lanes = query(
        conn,
        """
        MATCH (ic:IngredientCluster)-[:CLUSTER_HAS_LANE]->(lane:CategoryLane)
        WHERE ic.audit_flags <> ''
        RETURN ic.id AS ingredient_cluster_id,
               lane.name AS dominant_lane
        """,
    )

    forms = query(
        conn,
        """
        MATCH (ic:IngredientCluster)-[:CLUSTER_HAS_FORM]->(form:TitleForm)
        WHERE ic.audit_flags <> ''
        RETURN ic.id AS ingredient_cluster_id,
               form.name AS dominant_form
        """,
    )

    out = clusters
    for frame in (current, categories, brands, lanes, forms):
        if not frame.empty:
            out = out.merge(frame, on="ingredient_cluster_id", how="left")

    out = out.sort_values(["n_products", "category_top_share"], ascending=[False, False])
    structural = out[out["audit_flags"].astype(str).str.contains("current_top_code_structural_reject", regex=False)].copy()

    out.to_csv(OUT_CONFLICTS, index=False)
    structural.to_csv(OUT_STRUCTURAL, index=False)

    total_clusters = int(query(conn, "MATCH (ic:IngredientCluster) RETURN count(ic)").iloc[0, 0])
    total_products = int(query(conn, "MATCH (p:Product) RETURN count(p)").iloc[0, 0])
    total_esha = int(query(conn, "MATCH (e:ESHACode) RETURN count(e)").iloc[0, 0])
    total_cluster_edges = int(query(conn, "MATCH (:Product)-[r:IN_INGREDIENT_CLUSTER]->(:IngredientCluster) RETURN count(r)").iloc[0, 0])

    flags = [
        "current_top_code_structural_reject",
        "same_ingredient_category_maps_to_many_codes",
        "no_dominant_vM_code",
        "cluster_top_unassigned",
    ]
    flag_counts = {
        flag: int(out["audit_flags"].astype(str).str.contains(flag, regex=False).sum())
        for flag in flags
    }
    summary = {
        "graph_db": str(GRAPH_DB),
        "conflicts": str(OUT_CONFLICTS),
        "structural_rejects": str(OUT_STRUCTURAL),
        "total_product_nodes": total_products,
        "total_esha_nodes": total_esha,
        "ingredient_cluster_nodes": total_clusters,
        "product_to_ingredient_cluster_edges": total_cluster_edges,
        "conflict_clusters": int(len(out)),
        "structural_reject_clusters": int(len(structural)),
        "flag_counts": flag_counts,
        "top_structural_rejects": structural.head(25)[
            [
                "n_products",
                "ingredient_signature",
                "dominant_category",
                "current_top_code",
                "current_top_description",
                "current_reject_reason",
                "audit_flags",
            ]
        ].to_dict(orient="records"),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
