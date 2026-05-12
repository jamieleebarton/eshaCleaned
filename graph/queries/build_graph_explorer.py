"""Build the graph explorer HTML and the embedding suspect CSV.

Run: python3 graph/queries/build_graph_explorer.py
Outputs:
  implementation/output/graph_explorer/index.html
  graph/quarantine/embedding_suspects.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import kuzu
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from embed_nodes import embed_all
from score_suspicion import score_all

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
TEMPLATE = ROOT / "graph" / "queries" / "explorer_template.html"
OUT_DIR = ROOT / "implementation" / "output" / "graph_explorer"
OUT_HTML = OUT_DIR / "index.html"
OUT_CSV = ROOT / "graph" / "quarantine" / "embedding_suspects.csv"


def _drain(result):
    while result.has_next():
        yield result.get_next()


def fetch_products(conn: kuzu.Connection) -> pd.DataFrame:
    """Read the per-product audit row needed for score_all + viewer metadata."""
    q = (
        "MATCH (p:Product)-[:MAPS_TO]->(e:ESHACode)-[:IN_ESHA_CATEGORY]->(ef:ESHACategory) "
        "OPTIONAL MATCH (p)-[:IN_CATEGORY]->(c:ProductCategory) "
        "OPTIONAL MATCH (p)-[:MADE_BY]->(b:Brand) "
        "RETURN p.gtin_upc, p.description, e.code, ef.name, c.name, b.name"
    )
    rows = []
    for gtin, desc, code, family, cat, brand in _drain(conn.execute(q)):
        rows.append({
            "gtin_upc": gtin,
            "description": desc or "",
            "assigned_code": code,
            "esha_family": family or "",
            "category": cat or "",
            "brand": brand or "",
        })
    return pd.DataFrame(rows)


def fetch_node_meta(conn: kuzu.Connection) -> dict[str, dict]:
    """Return a small label/category map for non-Product nodes (for the viewer)."""
    meta: dict[str, dict] = {}
    for code, desc in _drain(conn.execute("MATCH (e:ESHACode) RETURN e.code, e.description")):
        meta[f"ESHACode:{code}"] = {"label": f"{code} {desc or ''}".strip(),
                                     "kind": "ESHACode", "esha_family": "", "category": ""}
    for code, family in _drain(conn.execute(
        "MATCH (e:ESHACode)-[:IN_ESHA_CATEGORY]->(ef:ESHACategory) RETURN e.code, ef.name"
    )):
        if f"ESHACode:{code}" in meta:
            meta[f"ESHACode:{code}"]["esha_family"] = family or ""
    for (name,) in _drain(conn.execute("MATCH (c:ProductCategory) RETURN c.name")):
        meta[f"ProductCategory:{name}"] = {"label": name, "kind": "ProductCategory",
                                            "esha_family": "", "category": name}
    for (name,) in _drain(conn.execute("MATCH (c:ESHACategory) RETURN c.name")):
        meta[f"ESHACategory:{name}"] = {"label": name, "kind": "ESHACategory",
                                         "esha_family": name, "category": ""}
    return meta


def project(embeddings: dict[str, np.ndarray]) -> tuple[list[str], np.ndarray, np.ndarray]:
    ids = sorted(embeddings)
    mat = np.vstack([embeddings[i] for i in ids])
    pca = PCA(n_components=3, random_state=0).fit_transform(mat).astype(np.float32)
    try:
        import umap
        reducer = umap.UMAP(n_components=3, random_state=0, metric="cosine",
                            n_neighbors=15, min_dist=0.1)
        umap_xyz = reducer.fit_transform(mat).astype(np.float32)
    except Exception as exc:
        print(f"warn: UMAP failed ({exc}); falling back to PCA for both views", flush=True)
        umap_xyz = pca

    def normalize(arr):
        arr = arr - arr.mean(axis=0)
        s = max(np.abs(arr).max(), 1e-6)
        return (arr / s).astype(np.float32)

    return ids, normalize(pca), normalize(umap_xyz)


def assemble_data(
    ids: list[str],
    pca_xyz: np.ndarray,
    umap_xyz: np.ndarray,
    products: pd.DataFrame,
    scores: pd.DataFrame,
    node_meta: dict[str, dict],
) -> dict:
    score_by_gtin = scores.set_index("gtin_upc").to_dict("index") if not scores.empty else {}
    products_by_gtin = products.set_index("gtin_upc").to_dict("index") if not products.empty else {}
    nodes = []
    for i, nid in enumerate(ids):
        kind, key = nid.split(":", 1)
        node = {"id": nid, "kind": kind, "label": key,
                "pca": pca_xyz[i].tolist(), "umap": umap_xyz[i].tolist()}
        if kind == "Product":
            p = products_by_gtin.get(key)
            s = score_by_gtin.get(key)
            if p:
                node["label"] = (p["description"] or key)[:80]
                node["category"] = p["category"]
                node["esha_family"] = p["esha_family"]
                node["assigned_esha"] = p["assigned_code"]
                node["brand"] = p["brand"]
            if s:
                node["suspicion"] = round(float(s["suspicion"]), 4)
                node["disagreement_kind"] = s["disagreement_kind"]
                node["top1_code"] = s["top1_code"]
                node["assigned_rank"] = int(s["assigned_rank"])
        else:
            meta = node_meta.get(nid, {})
            node["label"] = meta.get("label", key)
            node["esha_family"] = meta.get("esha_family", "")
            node["category"] = meta.get("category", "")
        nodes.append(node)
    return {"nodes": nodes}


def write_outputs(data: dict, scores: pd.DataFrame, products: pd.DataFrame) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(data, separators=(",", ":"))
    OUT_HTML.write_text(template.replace("__DATA__", payload), encoding="utf-8")
    print(f"wrote {OUT_HTML}", flush=True)

    if scores.empty:
        print("no products to score; skipping suspect CSV", flush=True)
        return

    suspect = scores.merge(products, on="gtin_upc", how="left", suffixes=("", "_p"))
    suspect = suspect.sort_values("suspicion", ascending=False).reset_index(drop=True)
    suspect_out = pd.DataFrame({
        "gtin_upc": suspect["gtin_upc"],
        "fdc_id": "",
        "product_description": suspect["description"],
        "product_category": suspect["category"],
        "brand": suspect["brand"],
        "manufacturer": "",
        "current_esha_code": suspect["assigned_code"],
        "current_esha_description": "",
        "current_esha_category": suspect["esha_family"],
        "score": suspect["suspicion"].round(4),
        "assignment_source": "embedding_suspect",
        "quarantine_reason": suspect["disagreement_kind"],
        "embedding_top1_code": suspect["top1_code"],
        "embedding_assigned_rank": suspect["assigned_rank"],
    })
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    suspect_out.to_csv(OUT_CSV, index=False)
    print(f"wrote {OUT_CSV} ({len(suspect_out):,} rows)", flush=True)


def main() -> None:
    if not GRAPH_DB.exists():
        sys.exit(f"missing kuzu db: {GRAPH_DB} — run graph/ingest/build_kuzu_graph.py first")

    print(f"opening kuzu db at {GRAPH_DB}", flush=True)
    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)

    embeddings = embed_all(conn)
    print(f"embeddings: {len(embeddings):,} nodes", flush=True)

    products = fetch_products(conn)
    print(f"products with MAPS_TO: {len(products):,}", flush=True)

    scores = score_all(embeddings, products)
    print(f"scored {len(scores):,} products", flush=True)

    node_meta = fetch_node_meta(conn)
    ids, pca_xyz, umap_xyz = project(embeddings)
    data = assemble_data(ids, pca_xyz, umap_xyz, products, scores, node_meta)
    write_outputs(data, scores, products)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # local imports for embed_nodes/score_suspicion
    main()
