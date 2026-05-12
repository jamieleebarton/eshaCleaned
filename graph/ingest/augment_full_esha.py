"""Augment the Kuzu graph with all ESHA codes from esha_cleaned.csv.

build_kuzu_graph.py only ingests ESHA codes that the matcher mapped products
to (~20.5k of ~26.2k). Any code the matcher *missed entirely* is invisible to
the heal passes — including correct ones like 3006 'Applesauce, unsweetened,
canned'.

This script:
  1. Reads esha_cleaned.csv directly.
  2. Runs match_esha_to_products.profile_for() to detect family for each.
  3. Upserts the missing ESHA code nodes + IN_ESHA_CATEGORY edges.

After running, the graph has all 26k+ codes and the heal passes can pick them.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import kuzu
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
ESHA_CSV = ROOT / "esha_cleaned.csv"
STAGING_DIR = ROOT / "graph" / "db" / "_staging"

sys.path.insert(0, str(ROOT / "implementation"))
import match_esha_to_products as matcher  # noqa: E402


def main() -> None:
    if not ESHA_CSV.exists():
        sys.exit(f"missing {ESHA_CSV}")
    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    print(f"loading {ESHA_CSV.name}", flush=True)
    raw = pd.read_csv(ESHA_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    print(f"  source rows: {len(raw):,}", flush=True)

    print("computing family per code via profile_for", flush=True)
    rows = []
    skipped = 0
    for _, r in raw.iterrows():
        row_dict = {k: (r[k] if k in r else "") for k in raw.columns}
        if "EshaCode" not in row_dict and "Code" in row_dict:
            row_dict["EshaCode"] = row_dict.get("Code", "")
        profile = matcher.profile_for(row_dict)
        if not profile.code or profile.skip_reason:
            skipped += 1
            continue
        rows.append({
            "code": profile.code.strip(),
            "description": profile.description,
            "family": profile.family,
        })
    df = pd.DataFrame(rows).drop_duplicates(subset=["code"])
    print(f"  usable codes: {len(df):,}  (skipped: {skipped:,})", flush=True)

    print("checking which codes already exist in graph", flush=True)
    existing = conn.execute("MATCH (e:ESHACode) RETURN e.code AS code").get_as_df()
    existing_set = set(existing["code"].astype(str).str.strip())
    print(f"  already in graph: {len(existing_set):,}", flush=True)

    new_codes = df[~df["code"].isin(existing_set)].copy()
    print(f"  to add:           {len(new_codes):,}", flush=True)
    if new_codes.empty:
        print("nothing to add", flush=True)
        return

    print("checking ESHACategory nodes", flush=True)
    existing_cats = conn.execute("MATCH (c:ESHACategory) RETURN c.name AS name").get_as_df()
    existing_cats_set = set(existing_cats["name"].astype(str))
    new_families = sorted(set(new_codes["family"].dropna().astype(str)) - existing_cats_set - {""})
    if new_families:
        print(f"  new ESHACategory nodes to add: {len(new_families):,}", flush=True)
        cat_df = pd.DataFrame({"name": new_families})
        cat_path = STAGING_DIR / "_aug_ESHACategory.parquet"
        cat_df.to_parquet(cat_path, index=False)
        conn.execute(f"COPY ESHACategory FROM '{cat_path}'")
        cat_path.unlink(missing_ok=True)

    print("inserting new ESHACode nodes", flush=True)
    code_df = new_codes[["code", "description"]].copy()
    code_path = STAGING_DIR / "_aug_ESHACode.parquet"
    code_df.to_parquet(code_path, index=False)
    conn.execute(f"COPY ESHACode FROM '{code_path}'")
    code_path.unlink(missing_ok=True)

    print("inserting IN_ESHA_CATEGORY edges", flush=True)
    edge_df = new_codes.loc[new_codes["family"].astype(str) != "", ["code", "family"]].rename(columns={"code": "from_id", "family": "to_id"})
    edge_path = STAGING_DIR / "_aug_IN_ESHA_CATEGORY.parquet"
    edge_df.to_parquet(edge_path, index=False)
    conn.execute(f"COPY IN_ESHA_CATEGORY FROM '{edge_path}'")
    edge_path.unlink(missing_ok=True)

    print("inserting Token nodes for new ESHA descriptions", flush=True)
    import re
    TOKEN_RE = re.compile(r"[a-z][a-z0-9]+")
    STOPWORDS = {"a","an","and","as","at","be","by","for","from","in","into","is","it","of","on","or","the","to","with","without","no","not"}
    token_set: set[str] = set()
    for desc in new_codes["description"].astype(str):
        for tok in TOKEN_RE.findall(desc.lower()):
            if len(tok) >= 2 and tok not in STOPWORDS:
                token_set.add(tok)
    existing_toks = set(conn.execute("MATCH (t:Token) RETURN t.value AS value").get_as_df()["value"])
    new_toks = sorted(token_set - existing_toks)
    print(f"  new Token nodes: {len(new_toks):,}", flush=True)
    if new_toks:
        tok_df = pd.DataFrame({"value": new_toks, "doc_count": 0, "entropy": 0.0, "num_esha_categories": 0})
        tok_path = STAGING_DIR / "_aug_Token.parquet"
        tok_df.to_parquet(tok_path, index=False)
        conn.execute(f"COPY Token FROM '{tok_path}'")
        tok_path.unlink(missing_ok=True)

    final_codes = conn.execute("MATCH (e:ESHACode) RETURN count(e) AS n").get_as_df().iloc[0, 0]
    final_cats = conn.execute("MATCH (c:ESHACategory) RETURN count(c) AS n").get_as_df().iloc[0, 0]
    final_iec = conn.execute("MATCH ()-[e:IN_ESHA_CATEGORY]->() RETURN count(e) AS n").get_as_df().iloc[0, 0]
    print(f"final: ESHACode={final_codes:,}, ESHACategory={final_cats:,}, IN_ESHA_CATEGORY={final_iec:,}", flush=True)


if __name__ == "__main__":
    main()
