"""Build the Kuzu knowledge graph from the current whole-corpus product map.

The graph is evidence-first:

* Product rows are observations keyed by product_key (fdc_id when available).
* IngredientCluster nodes are the spine used for healing/audit.
* ESHA codes are reference/candidate targets, not the clustering spine.
* MAPS_TO carries the incumbent vM assignment state.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import kuzu
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB_DIR = ROOT / "graph" / "db" / "kuzu"
STAGING_DIR = ROOT / "graph" / "db" / "_staging"
DEFAULT_SOURCE_CSV = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.vM.csv"
FALLBACK_SOURCE_CSV = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.csv"
ESHA_CSV = ROOT / "esha_cleaned.csv"
INGREDIENT_CLUSTER_MEMBERS = ROOT / "implementation" / "output" / "ingredient_only_cluster_members.csv"
INGREDIENT_CLUSTER_AUDIT = ROOT / "implementation" / "output" / "vm_ingredient_cluster_audit.csv"
RFT_PRODUCT_TO_ESHA = ROOT / "implementation" / "output" / "rft_v2" / "rft_v2_product_to_esha.csv"
RFT_LEAVES = ROOT / "implementation" / "output" / "rft_v2" / "leaves.csv"

STOPWORDS = {
    "a", "an", "and", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it", "its",
    "of", "on", "or", "the", "to", "with", "without", "no", "not",
    "intl", "international", "style", "type", "plain", "regular", "prepared", "recipe", "fs", "usda",
    "oz", "fl", "lb", "lbs", "ct", "pk", "pkg", "ea", "each", "pack", "count", "container", "containers",
    "size", "sized", "large", "small", "medium", "jumbo", "mini", "big", "little",
}

TOKEN_RE = re.compile(r"[a-z][a-z0-9]+")


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    out = []
    for tok in TOKEN_RE.findall(text.lower()):
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        out.append(tok)
    return out


def copy_frame(conn: kuzu.Connection, table: str, frame: pd.DataFrame) -> None:
    if frame.empty:
        print(f"  {table}: empty, skipping", flush=True)
        return
    path = STAGING_DIR / f"{table}.parquet"
    frame.to_parquet(path, index=False)
    conn.execute(f"COPY {table} FROM '{path}'")
    print(f"  {table}: loaded {len(frame):,}", flush=True)


def product_key_frame(df: pd.DataFrame) -> pd.Series:
    fdc = df.get("fdc_id", pd.Series([""] * len(df))).fillna("").astype(str).str.strip()
    gtin = df.get("gtin_upc", pd.Series([""] * len(df))).fillna("").astype(str).str.strip()
    return fdc.where(fdc != "", gtin)


def esha_head(description: object) -> str:
    return str(description or "").split(",", 1)[0].strip()


def load_esha_reference(source_df: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if ESHA_CSV.exists():
        esha = pd.read_csv(ESHA_CSV, dtype=str, keep_default_na=False, low_memory=False)
        if {"EshaCode", "Description"} <= set(esha.columns):
            frames.append(
                esha[["EshaCode", "Description"]].rename(
                    columns={"EshaCode": "code", "Description": "description"}
                )
            )
    assigned = (
        source_df.loc[source_df["best_esha_code"] != "", ["best_esha_code", "best_esha_description"]]
        .rename(columns={"best_esha_code": "code", "best_esha_description": "description"})
    )
    frames.append(assigned)
    out = pd.concat(frames, ignore_index=True)
    out["code"] = out["code"].fillna("").astype(str).str.strip()
    out["description"] = out["description"].fillna("").astype(str).str.strip()
    out = out[out["code"] != ""].drop_duplicates(subset=["code"], keep="first")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_CSV if DEFAULT_SOURCE_CSV.exists() else FALLBACK_SOURCE_CSV)
    parser.add_argument("--ingredient-members", type=Path, default=INGREDIENT_CLUSTER_MEMBERS)
    parser.add_argument("--cluster-audit", type=Path, default=INGREDIENT_CLUSTER_AUDIT)
    parser.add_argument("--rft-routes", type=Path, default=RFT_PRODUCT_TO_ESHA)
    parser.add_argument("--rft-leaves", type=Path, default=RFT_LEAVES)
    args = parser.parse_args()

    if not args.source.exists():
        sys.exit(f"missing source: {args.source}")

    parent = GRAPH_DB_DIR.parent
    parent.mkdir(parents=True, exist_ok=True)
    for sibling in parent.glob(GRAPH_DB_DIR.name + "*"):
        if sibling.is_dir():
            shutil.rmtree(sibling)
        else:
            sibling.unlink()
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    print(f"reading {args.source.name}", flush=True)
    df = pd.read_csv(args.source, dtype=str, keep_default_na=False, low_memory=False)
    print(f"  rows: {len(df):,}", flush=True)

    for col in ["gtin_upc", "fdc_id", "product_description", "branded_food_category",
                "brand_owner", "brand_name", "best_esha_code", "best_esha_description",
                "best_esha_family", "assignment_source"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()

    if "score" not in df.columns:
        df["score"] = 0.0
    if "n_candidates" not in df.columns:
        df["n_candidates"] = 0
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0.0)
    df["n_candidates"] = pd.to_numeric(df["n_candidates"], errors="coerce").fillna(0).astype("int64")
    df["product_key"] = product_key_frame(df)
    df = df[df["product_key"] != ""].copy()

    cluster_members = pd.DataFrame()
    if args.ingredient_members.exists():
        cluster_members = pd.read_csv(args.ingredient_members, dtype=str, keep_default_na=False, low_memory=False)
        cluster_members["product_key"] = product_key_frame(cluster_members)
        for col in ["ingredient_cluster_id", "ingredient_signature"]:
            if col not in cluster_members.columns:
                cluster_members[col] = ""
        cluster_members = cluster_members[
            (cluster_members["product_key"] != "")
            & (cluster_members["ingredient_cluster_id"].astype(str).str.strip() != "")
        ].copy()
        print(f"  ingredient cluster members: {len(cluster_members):,}", flush=True)

    cluster_audit = pd.DataFrame()
    if args.cluster_audit.exists():
        cluster_audit = pd.read_csv(args.cluster_audit, dtype=str, keep_default_na=False, low_memory=False)
        print(f"  ingredient cluster audit rows: {len(cluster_audit):,}", flush=True)

    rft_routes = pd.DataFrame()
    if args.rft_routes.exists():
        rft_routes = pd.read_csv(args.rft_routes, dtype=str, keep_default_na=False, low_memory=False)
        rft_routes["product_key"] = product_key_frame(rft_routes)
        for col in [
            "rft_leaf_id",
            "rft_leaf_canonical",
            "rft_head",
            "rft_status",
            "rft_verdict",
            "rft_score",
            "rft_retail_attrs",
            "rft_brand_stripped",
            "rft_missing_from_leaf",
            "rft_leaf_extra_facets",
            "rft_esha_code",
            "rft_esha_description",
        ]:
            if col not in rft_routes.columns:
                rft_routes[col] = ""
            rft_routes[col] = rft_routes[col].fillna("").astype(str).str.strip()
        rft_routes = rft_routes[rft_routes["product_key"] != ""].copy()
        print(f"  RFT route rows: {len(rft_routes):,}", flush=True)

    rft_leaves = pd.DataFrame()
    if args.rft_leaves.exists():
        rft_leaves = pd.read_csv(args.rft_leaves, dtype=str, keep_default_na=False, low_memory=False)
        for col in ["leaf_id", "head", "canonical_name", "key_facets", "esha_code", "esha_score"]:
            if col not in rft_leaves.columns:
                rft_leaves[col] = ""
            rft_leaves[col] = rft_leaves[col].fillna("").astype(str).str.strip()
        print(f"  RFT leaves: {len(rft_leaves):,}", flush=True)

    print(f"creating db at {GRAPH_DB_DIR}", flush=True)
    db = kuzu.Database(str(GRAPH_DB_DIR))
    conn = kuzu.Connection(db)

    print("creating schema", flush=True)
    for stmt in [
        "CREATE NODE TABLE Product(product_key STRING, gtin_upc STRING, fdc_id STRING, description STRING, PRIMARY KEY (product_key))",
        "CREATE NODE TABLE Brand(name STRING, PRIMARY KEY (name))",
        "CREATE NODE TABLE Manufacturer(name STRING, PRIMARY KEY (name))",
        "CREATE NODE TABLE ProductCategory(name STRING, PRIMARY KEY (name))",
        "CREATE NODE TABLE IngredientCluster(id STRING, signature STRING, n_products INT64, category_top_share DOUBLE, current_code_count INT64, current_reject_reason STRING, audit_flags STRING, PRIMARY KEY (id))",
        "CREATE NODE TABLE CategoryLane(name STRING, PRIMARY KEY (name))",
        "CREATE NODE TABLE TitleForm(name STRING, PRIMARY KEY (name))",
        "CREATE NODE TABLE AssignmentVersion(name STRING, source_csv STRING, ingested_at STRING, PRIMARY KEY (name))",
        "CREATE NODE TABLE Token(value STRING, doc_count INT64 DEFAULT 0, entropy DOUBLE DEFAULT 0.0, num_esha_categories INT64 DEFAULT 0, PRIMARY KEY (value))",
        "CREATE NODE TABLE ESHACode(code STRING, description STRING, PRIMARY KEY (code))",
        "CREATE NODE TABLE ESHAHead(name STRING, PRIMARY KEY (name))",
        "CREATE NODE TABLE ESHACategory(name STRING, PRIMARY KEY (name))",
        "CREATE NODE TABLE RFTHead(name STRING, PRIMARY KEY (name))",
        "CREATE NODE TABLE RFTLeaf(id STRING, head STRING, canonical_name STRING, key_facets STRING, PRIMARY KEY (id))",
        "CREATE REL TABLE MADE_BY(FROM Product TO Brand)",
        "CREATE REL TABLE OWNED_BY(FROM Brand TO Manufacturer)",
        "CREATE REL TABLE IN_CATEGORY(FROM Product TO ProductCategory)",
        "CREATE REL TABLE IN_INGREDIENT_CLUSTER(FROM Product TO IngredientCluster)",
        "CREATE REL TABLE CLUSTER_DOMINANT_CATEGORY(FROM IngredientCluster TO ProductCategory, share DOUBLE)",
        "CREATE REL TABLE CLUSTER_DOMINANT_BRAND(FROM IngredientCluster TO Brand, share DOUBLE)",
        "CREATE REL TABLE CLUSTER_HAS_LANE(FROM IngredientCluster TO CategoryLane)",
        "CREATE REL TABLE CLUSTER_HAS_FORM(FROM IngredientCluster TO TitleForm)",
        "CREATE REL TABLE CLUSTER_CURRENT_TOP_ESHA(FROM IngredientCluster TO ESHACode, share DOUBLE, code_count INT64, reject_reason STRING, audit_flags STRING)",
        "CREATE REL TABLE PRODUCT_IN_ASSIGNMENT_VERSION(FROM Product TO AssignmentVersion)",
        "CREATE REL TABLE HAS_TOKEN(FROM Product TO Token)",
        "CREATE REL TABLE MAPS_TO(FROM Product TO ESHACode, score DOUBLE, assignment_source STRING, n_candidates INT64, status STRING, source STRING, ingested_at STRING)",
        "CREATE REL TABLE IN_ESHA_CATEGORY(FROM ESHACode TO ESHACategory)",
        "CREATE REL TABLE HAS_ESHA_HEAD(FROM ESHACode TO ESHAHead)",
        "CREATE REL TABLE RFT_LEAF_HAS_HEAD(FROM RFTLeaf TO RFTHead)",
        "CREATE REL TABLE PRODUCT_HAS_RFT_HEAD(FROM Product TO RFTHead, status STRING, verdict STRING)",
        "CREATE REL TABLE ROUTES_TO_RFT(FROM Product TO RFTLeaf, status STRING, verdict STRING, score DOUBLE, retail_attrs STRING, brand_stripped STRING, missing_from_leaf STRING, leaf_extra_facets STRING)",
        "CREATE REL TABLE RFT_LEAF_ESHA_PROVENANCE(FROM RFTLeaf TO ESHACode, source STRING, score DOUBLE)",
        "CREATE REL TABLE CATEGORY_DOMINANT_RFT_LEAF(FROM ProductCategory TO RFTLeaf, share DOUBLE, n_products INT64)",
        "CREATE REL TABLE BRAND_DOMINANT_RFT_LEAF(FROM Brand TO RFTLeaf, share DOUBLE, n_products INT64)",
        "CREATE REL TABLE CLUSTER_DOMINANT_RFT_LEAF(FROM IngredientCluster TO RFTLeaf, share DOUBLE, n_products INT64)",
    ]:
        conn.execute(stmt)

    print("preparing node frames", flush=True)
    products_df = (
        df[["product_key", "gtin_upc", "fdc_id", "product_description"]]
        .drop_duplicates(subset=["product_key"])
        .rename(columns={"product_description": "description"})
    )
    brands_df = pd.DataFrame({"name": sorted({n for n in df["brand_name"].tolist() if n})})
    manufacturers_df = pd.DataFrame({"name": sorted({n for n in df["brand_owner"].tolist() if n})})
    categories_df = pd.DataFrame({"name": sorted({n for n in df["branded_food_category"].tolist() if n})})
    esha_codes_df = load_esha_reference(df)
    esha_codes_df["head"] = esha_codes_df["description"].map(esha_head)
    esha_heads_df = pd.DataFrame({"name": sorted({n for n in esha_codes_df["head"].tolist() if n})})
    esha_categories_df = pd.DataFrame({"name": sorted({n for n in df["best_esha_family"].tolist() if n})})

    rft_leaf_nodes = pd.DataFrame(columns=["id", "head", "canonical_name", "key_facets"])
    if not rft_leaves.empty:
        rft_leaf_nodes = rft_leaves[["leaf_id", "head", "canonical_name", "key_facets"]].rename(columns={"leaf_id": "id"})
    if not rft_routes.empty:
        route_leaf_nodes = (
            rft_routes.loc[
                rft_routes["rft_leaf_id"].astype(str) != "",
                ["rft_leaf_id", "rft_head", "rft_leaf_canonical", "rft_leaf_extra_facets"],
            ]
            .rename(
                columns={
                    "rft_leaf_id": "id",
                    "rft_head": "head",
                    "rft_leaf_canonical": "canonical_name",
                    "rft_leaf_extra_facets": "key_facets",
                }
            )
        )
        rft_leaf_nodes = pd.concat([rft_leaf_nodes, route_leaf_nodes], ignore_index=True)
    if not rft_leaf_nodes.empty:
        for col in ["id", "head", "canonical_name", "key_facets"]:
            rft_leaf_nodes[col] = rft_leaf_nodes[col].fillna("").astype(str).str.strip()
        rft_leaf_nodes = rft_leaf_nodes[rft_leaf_nodes["id"] != ""].drop_duplicates("id")
    rft_heads_df = pd.DataFrame({"name": sorted({n for n in rft_leaf_nodes.get("head", pd.Series(dtype=str)).tolist() if n} | {n for n in rft_routes.get("rft_head", pd.Series(dtype=str)).tolist() if n})})

    versions_df = pd.DataFrame(
        {
            "name": ["vM_incumbent" if args.source.name.endswith(".vM.csv") else "current_incumbent"],
            "source_csv": [str(args.source)],
            "ingested_at": [datetime.now(timezone.utc).isoformat()],
        }
    )

    cluster_nodes_df = pd.DataFrame(columns=["id", "signature", "n_products", "category_top_share", "current_code_count", "current_reject_reason", "audit_flags"])
    if not cluster_audit.empty:
        cluster_nodes_df = cluster_audit.rename(
            columns={
                "ingredient_cluster_id": "id",
                "ingredient_signature": "signature",
            }
        ).copy()
        for col in ["id", "signature", "current_reject_reason", "audit_flags"]:
            if col not in cluster_nodes_df.columns:
                cluster_nodes_df[col] = ""
        for col in ["n_products", "current_code_count"]:
            if col not in cluster_nodes_df.columns:
                cluster_nodes_df[col] = 0
            cluster_nodes_df[col] = pd.to_numeric(cluster_nodes_df[col], errors="coerce").fillna(0).astype("int64")
        if "category_top_share" not in cluster_nodes_df.columns:
            cluster_nodes_df["category_top_share"] = 0.0
        cluster_nodes_df["category_top_share"] = pd.to_numeric(cluster_nodes_df["category_top_share"], errors="coerce").fillna(0.0)
        cluster_nodes_df = cluster_nodes_df[
            ["id", "signature", "n_products", "category_top_share", "current_code_count", "current_reject_reason", "audit_flags"]
        ].drop_duplicates("id")
    elif not cluster_members.empty:
        cluster_nodes_df = (
            cluster_members.groupby("ingredient_cluster_id", as_index=False)
            .agg(signature=("ingredient_signature", "first"), n_products=("product_key", "nunique"))
            .rename(columns={"ingredient_cluster_id": "id"})
        )
        cluster_nodes_df["category_top_share"] = 0.0
        cluster_nodes_df["current_code_count"] = 0
        cluster_nodes_df["current_reject_reason"] = ""
        cluster_nodes_df["audit_flags"] = ""

    lanes_df = pd.DataFrame({"name": sorted({n for n in cluster_audit.get("dominant_lane", pd.Series(dtype=str)).tolist() if n})})
    forms_df = pd.DataFrame({"name": sorted({n for n in cluster_audit.get("dominant_form", pd.Series(dtype=str)).tolist() if n})})

    print(f"  Product:         {len(products_df):>10,}", flush=True)
    print(f"  Brand:           {len(brands_df):>10,}", flush=True)
    print(f"  Manufacturer:    {len(manufacturers_df):>10,}", flush=True)
    print(f"  ProductCategory: {len(categories_df):>10,}", flush=True)
    print(f"  ESHACode:        {len(esha_codes_df):>10,}", flush=True)
    print(f"  ESHAHead:        {len(esha_heads_df):>10,}", flush=True)
    print(f"  ESHACategory:    {len(esha_categories_df):>10,}", flush=True)
    print(f"  RFTHead:         {len(rft_heads_df):>10,}", flush=True)
    print(f"  RFTLeaf:         {len(rft_leaf_nodes):>10,}", flush=True)
    print(f"  IngredientCluster:{len(cluster_nodes_df):>9,}", flush=True)
    print(f"  CategoryLane:    {len(lanes_df):>10,}", flush=True)
    print(f"  TitleForm:       {len(forms_df):>10,}", flush=True)

    print("tokenizing", flush=True)
    df["_tokens"] = df["product_description"].apply(tokenize)
    pairs = df[["product_key", "_tokens"]].explode("_tokens").dropna()
    pairs = pairs[pairs["_tokens"].astype(str) != ""].drop_duplicates()
    pairs = pairs.rename(columns={"product_key": "from_id", "_tokens": "to_id"})

    tokens_df = pd.DataFrame({"value": sorted(pairs["to_id"].unique().tolist())})
    tokens_df["doc_count"] = 0
    tokens_df["entropy"] = 0.0
    tokens_df["num_esha_categories"] = 0
    print(f"  Token:           {len(tokens_df):>10,}", flush=True)
    print(f"  HAS_TOKEN:       {len(pairs):>10,}", flush=True)

    print("loading nodes", flush=True)
    copy_frame(conn, "Product", products_df)
    copy_frame(conn, "Brand", brands_df)
    copy_frame(conn, "Manufacturer", manufacturers_df)
    copy_frame(conn, "ProductCategory", categories_df)
    copy_frame(conn, "IngredientCluster", cluster_nodes_df)
    copy_frame(conn, "CategoryLane", lanes_df)
    copy_frame(conn, "TitleForm", forms_df)
    copy_frame(conn, "AssignmentVersion", versions_df)
    copy_frame(conn, "Token", tokens_df)
    copy_frame(conn, "ESHACode", esha_codes_df[["code", "description"]])
    copy_frame(conn, "ESHAHead", esha_heads_df)
    copy_frame(conn, "ESHACategory", esha_categories_df)
    copy_frame(conn, "RFTHead", rft_heads_df)
    copy_frame(conn, "RFTLeaf", rft_leaf_nodes)

    print("preparing edge frames", flush=True)
    ingested_at = datetime.now(timezone.utc).isoformat()

    made_by = df.loc[df["brand_name"] != "", ["product_key", "brand_name"]].drop_duplicates().rename(columns={"product_key": "from_id", "brand_name": "to_id"})
    owned_by = (
        df.loc[(df["brand_name"] != "") & (df["brand_owner"] != ""), ["brand_name", "brand_owner"]]
        .drop_duplicates(subset=["brand_name"])
        .rename(columns={"brand_name": "from_id", "brand_owner": "to_id"})
    )
    in_cat = df.loc[df["branded_food_category"] != "", ["product_key", "branded_food_category"]].drop_duplicates().rename(columns={"product_key": "from_id", "branded_food_category": "to_id"})
    has_tok = pairs

    maps_to = df.loc[df["best_esha_code"] != "", ["product_key", "best_esha_code", "score", "assignment_source", "n_candidates"]].copy()
    maps_to = maps_to.rename(columns={"product_key": "from_id", "best_esha_code": "to_id"})
    maps_to["status"] = "unverified"
    maps_to["source"] = versions_df["name"].iloc[0]
    maps_to["ingested_at"] = ingested_at

    in_esha_cat = (
        df.loc[(df["best_esha_code"] != "") & (df["best_esha_family"] != ""), ["best_esha_code", "best_esha_family"]]
        .drop_duplicates(subset=["best_esha_code"])
        .rename(columns={"best_esha_code": "from_id", "best_esha_family": "to_id"})
    )
    has_esha_head = (
        esha_codes_df.loc[esha_codes_df["head"] != "", ["code", "head"]]
        .drop_duplicates()
        .rename(columns={"code": "from_id", "head": "to_id"})
    )

    known_products = set(products_df["product_key"].astype(str))
    known_brands = set(brands_df["name"].astype(str))
    known_categories = set(categories_df["name"].astype(str))
    known_clusters = set(cluster_nodes_df["id"].astype(str))
    known_rft_leaves = set(rft_leaf_nodes["id"].astype(str)) if not rft_leaf_nodes.empty else set()
    known_rft_heads = set(rft_heads_df["name"].astype(str)) if not rft_heads_df.empty else set()
    known_esha_codes = set(esha_codes_df["code"].astype(str))

    rft_leaf_head = pd.DataFrame(columns=["from_id", "to_id"])
    product_rft_head = pd.DataFrame(columns=["from_id", "to_id", "status", "verdict"])
    routes_to_rft = pd.DataFrame(columns=["from_id", "to_id", "status", "verdict", "score", "retail_attrs", "brand_stripped", "missing_from_leaf", "leaf_extra_facets"])
    rft_leaf_esha = pd.DataFrame(columns=["from_id", "to_id", "source", "score"])
    category_rft = pd.DataFrame(columns=["from_id", "to_id", "share", "n_products"])
    brand_rft = pd.DataFrame(columns=["from_id", "to_id", "share", "n_products"])
    cluster_rft = pd.DataFrame(columns=["from_id", "to_id", "share", "n_products"])
    if known_rft_leaves:
        rft_leaf_head = (
            rft_leaf_nodes.loc[
                (rft_leaf_nodes["head"].astype(str) != "")
                & rft_leaf_nodes["head"].astype(str).isin(known_rft_heads),
                ["id", "head"],
            ]
            .drop_duplicates()
            .rename(columns={"id": "from_id", "head": "to_id"})
        )

    if not rft_routes.empty:
        product_rft_head = (
            rft_routes.loc[
                (rft_routes["product_key"].astype(str).isin(known_products))
                & (rft_routes["rft_head"].astype(str).isin(known_rft_heads)),
                ["product_key", "rft_head", "rft_status", "rft_verdict"],
            ]
            .drop_duplicates()
            .rename(columns={"product_key": "from_id", "rft_head": "to_id", "rft_status": "status", "rft_verdict": "verdict"})
        )

        routes_to_rft = rft_routes.loc[
            (rft_routes["product_key"].astype(str).isin(known_products))
            & (rft_routes["rft_leaf_id"].astype(str).isin(known_rft_leaves)),
            [
                "product_key",
                "rft_leaf_id",
                "rft_status",
                "rft_verdict",
                "rft_score",
                "rft_retail_attrs",
                "rft_brand_stripped",
                "rft_missing_from_leaf",
                "rft_leaf_extra_facets",
            ],
        ].copy()
        routes_to_rft["score"] = pd.to_numeric(routes_to_rft["rft_score"], errors="coerce").fillna(0.0)
        routes_to_rft = routes_to_rft.rename(
            columns={
                "product_key": "from_id",
                "rft_leaf_id": "to_id",
                "rft_status": "status",
                "rft_verdict": "verdict",
                "rft_retail_attrs": "retail_attrs",
                "rft_brand_stripped": "brand_stripped",
                "rft_missing_from_leaf": "missing_from_leaf",
                "rft_leaf_extra_facets": "leaf_extra_facets",
            }
        )[["from_id", "to_id", "status", "verdict", "score", "retail_attrs", "brand_stripped", "missing_from_leaf", "leaf_extra_facets"]]

        route_dims = rft_routes.loc[
            (rft_routes["product_key"].astype(str).isin(known_products))
            & (rft_routes["rft_leaf_id"].astype(str).isin(known_rft_leaves)),
            ["product_key", "rft_leaf_id"],
        ].merge(
            df[["product_key", "branded_food_category", "brand_name"]].drop_duplicates("product_key"),
            on="product_key",
            how="left",
        )

        def dominant_edges(frame: pd.DataFrame, from_col: str, known_from: set[str]) -> pd.DataFrame:
            if frame.empty:
                return pd.DataFrame(columns=["from_id", "to_id", "share", "n_products"])
            scoped = frame[
                frame[from_col].fillna("").astype(str).isin(known_from)
                & frame["rft_leaf_id"].fillna("").astype(str).isin(known_rft_leaves)
            ].copy()
            if scoped.empty:
                return pd.DataFrame(columns=["from_id", "to_id", "share", "n_products"])
            counts = scoped.groupby([from_col, "rft_leaf_id"], as_index=False).agg(n_products=("product_key", "nunique"))
            totals = counts.groupby(from_col, as_index=False).agg(total=("n_products", "sum"))
            counts = counts.merge(totals, on=from_col, how="left")
            counts["share"] = counts["n_products"] / counts["total"].replace(0, pd.NA)
            counts = counts.sort_values([from_col, "n_products", "rft_leaf_id"], ascending=[True, False, True])
            counts = counts.drop_duplicates(from_col)
            return counts.rename(columns={from_col: "from_id", "rft_leaf_id": "to_id"})[["from_id", "to_id", "share", "n_products"]]

        category_rft = dominant_edges(route_dims, "branded_food_category", known_categories)
        brand_rft = dominant_edges(route_dims, "brand_name", known_brands)

    if not rft_leaves.empty:
        rft_leaf_esha = rft_leaves.loc[
            (rft_leaves["leaf_id"].astype(str).isin(known_rft_leaves))
            & (rft_leaves["esha_code"].astype(str).isin(known_esha_codes)),
            ["leaf_id", "esha_code", "esha_score"],
        ].copy()
        rft_leaf_esha["score"] = pd.to_numeric(rft_leaf_esha["esha_score"], errors="coerce").fillna(0.0)
        rft_leaf_esha["source"] = "esha"
        rft_leaf_esha = rft_leaf_esha.rename(columns={"leaf_id": "from_id", "esha_code": "to_id"})[["from_id", "to_id", "source", "score"]]

    version_edges = pd.DataFrame({"from_id": df["product_key"].drop_duplicates(), "to_id": versions_df["name"].iloc[0]})

    in_cluster = pd.DataFrame(columns=["from_id", "to_id"])
    if not cluster_members.empty:
        in_cluster = (
            cluster_members[["product_key", "ingredient_cluster_id"]]
            .drop_duplicates()
            .rename(columns={"product_key": "from_id", "ingredient_cluster_id": "to_id"})
        )
        in_cluster = in_cluster[
            in_cluster["from_id"].astype(str).isin(known_products)
            & in_cluster["to_id"].astype(str).isin(known_clusters)
        ]
        if not rft_routes.empty and known_rft_leaves:
            cluster_dims = in_cluster.rename(columns={"from_id": "product_key", "to_id": "ingredient_cluster_id"}).merge(
                rft_routes[["product_key", "rft_leaf_id"]],
                on="product_key",
                how="inner",
            )
            cluster_rft = dominant_edges(cluster_dims, "ingredient_cluster_id", known_clusters)

    cluster_dom_cat = pd.DataFrame(columns=["from_id", "to_id", "share"])
    cluster_dom_brand = pd.DataFrame(columns=["from_id", "to_id", "share"])
    cluster_lane = pd.DataFrame(columns=["from_id", "to_id"])
    cluster_form = pd.DataFrame(columns=["from_id", "to_id"])
    cluster_current_esha = pd.DataFrame(columns=["from_id", "to_id", "share", "code_count", "reject_reason", "audit_flags"])
    if not cluster_audit.empty:
        cluster_dom_cat = cluster_audit.loc[
            cluster_audit["dominant_category"].astype(str) != "",
            ["ingredient_cluster_id", "dominant_category", "category_top_share"],
        ].copy()
        cluster_dom_cat["share"] = pd.to_numeric(cluster_dom_cat["category_top_share"], errors="coerce").fillna(0.0)
        cluster_dom_cat = cluster_dom_cat.rename(columns={"ingredient_cluster_id": "from_id", "dominant_category": "to_id"})[["from_id", "to_id", "share"]]

        cluster_dom_brand = cluster_audit.loc[
            cluster_audit["dominant_brand"].astype(str) != "",
            ["ingredient_cluster_id", "dominant_brand", "brand_top_share"],
        ].copy()
        cluster_dom_brand["share"] = pd.to_numeric(cluster_dom_brand["brand_top_share"], errors="coerce").fillna(0.0)
        cluster_dom_brand = cluster_dom_brand.rename(columns={"ingredient_cluster_id": "from_id", "dominant_brand": "to_id"})[["from_id", "to_id", "share"]]

        cluster_lane = cluster_audit.loc[
            cluster_audit["dominant_lane"].astype(str) != "",
            ["ingredient_cluster_id", "dominant_lane"],
        ].drop_duplicates().rename(columns={"ingredient_cluster_id": "from_id", "dominant_lane": "to_id"})
        cluster_form = cluster_audit.loc[
            cluster_audit["dominant_form"].astype(str) != "",
            ["ingredient_cluster_id", "dominant_form"],
        ].drop_duplicates().rename(columns={"ingredient_cluster_id": "from_id", "dominant_form": "to_id"})
        cluster_current_esha = cluster_audit.loc[
            cluster_audit["current_top_code"].astype(str) != "",
            ["ingredient_cluster_id", "current_top_code", "current_code_top_share", "current_code_count", "current_reject_reason", "audit_flags"],
        ].copy()
        cluster_current_esha["share"] = pd.to_numeric(cluster_current_esha["current_code_top_share"], errors="coerce").fillna(0.0)
        cluster_current_esha["code_count"] = pd.to_numeric(cluster_current_esha["current_code_count"], errors="coerce").fillna(0).astype("int64")
        cluster_current_esha = cluster_current_esha.rename(
            columns={
                "ingredient_cluster_id": "from_id",
                "current_top_code": "to_id",
                "current_reject_reason": "reject_reason",
            }
        )[["from_id", "to_id", "share", "code_count", "reject_reason", "audit_flags"]]

    print("loading edges", flush=True)
    copy_frame(conn, "MADE_BY", made_by)
    copy_frame(conn, "OWNED_BY", owned_by)
    copy_frame(conn, "IN_CATEGORY", in_cat)
    copy_frame(conn, "IN_INGREDIENT_CLUSTER", in_cluster)
    copy_frame(conn, "CLUSTER_DOMINANT_CATEGORY", cluster_dom_cat)
    copy_frame(conn, "CLUSTER_DOMINANT_BRAND", cluster_dom_brand)
    copy_frame(conn, "CLUSTER_HAS_LANE", cluster_lane)
    copy_frame(conn, "CLUSTER_HAS_FORM", cluster_form)
    copy_frame(conn, "CLUSTER_CURRENT_TOP_ESHA", cluster_current_esha)
    copy_frame(conn, "PRODUCT_IN_ASSIGNMENT_VERSION", version_edges)
    copy_frame(conn, "HAS_TOKEN", has_tok)
    copy_frame(conn, "MAPS_TO", maps_to)
    copy_frame(conn, "IN_ESHA_CATEGORY", in_esha_cat)
    copy_frame(conn, "HAS_ESHA_HEAD", has_esha_head)
    copy_frame(conn, "RFT_LEAF_HAS_HEAD", rft_leaf_head)
    copy_frame(conn, "PRODUCT_HAS_RFT_HEAD", product_rft_head)
    copy_frame(conn, "ROUTES_TO_RFT", routes_to_rft)
    copy_frame(conn, "RFT_LEAF_ESHA_PROVENANCE", rft_leaf_esha)
    copy_frame(conn, "CATEGORY_DOMINANT_RFT_LEAF", category_rft)
    copy_frame(conn, "BRAND_DOMINANT_RFT_LEAF", brand_rft)
    copy_frame(conn, "CLUSTER_DOMINANT_RFT_LEAF", cluster_rft)

    shutil.rmtree(STAGING_DIR, ignore_errors=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
