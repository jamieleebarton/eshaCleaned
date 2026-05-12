"""Pass D: graph-based healing of quarantined rows.

Quarantine identifies what's wrong. Pass D figures out where each row should
actually go by letting every other signal in the graph vote.

For each quarantined Product:
  1. Collect target-family votes from:
       - WWEIA dominant family for this product's WWEIA (weight 1.0)
       - Brand dominant family from trusted rows (weight 0.8)
       - ProductCategory dominant family from trusted rows (weight 0.6)
  2. Pick the target family with the highest summed weight.
  3. Within that family, score every ESHA code by entropy-weighted token
     overlap with the product description. Pick the top one.
  4. Write a healed_proposals.csv with full provenance.

This is advisory — does NOT modify the original CSV or auto-apply edges.
The user reviews the proposals before applying.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path

import kuzu
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
PRODUCTS_DB = ROOT / "data" / "master_products.db"
FNDDS_CSV = ROOT / "data" / "fndds" / "MainFoodDesc16.csv"
OUT_DIR = ROOT / "graph" / "quarantine"
OUT_PROPOSALS = OUT_DIR / "healed_proposals_structural.csv"
OUT_BASELINE = OUT_DIR / "baseline_after_pass_d.json"

# WWEIA disabled: 81% of FNDDS tags came from llm_reclassified, so WWEIA-via-FNDDS
# is itself an LLM-tagged signal and not safe to lean on as ground truth.
# Healing leans only on corpus-derived signals: brand consistency + product-category
# consistency (both learned from the matcher's most-confident output rows).
WEIGHT_WWEIA = 0.0
WEIGHT_BRAND = 1.0
WEIGHT_CATEGORY = 1.0
MIN_SUPPORT = 20

STOPWORDS = {
    "a", "an", "and", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it", "its",
    "of", "on", "or", "the", "to", "with", "without", "no", "not",
    "intl", "international", "style", "type", "plain", "regular", "prepared", "recipe", "fs", "usda",
    "oz", "fl", "lb", "lbs", "ct", "pk", "pkg", "ea", "each", "pack", "count", "container", "containers",
    "size", "sized", "large", "small", "medium", "jumbo", "mini", "big", "little",
}
TOKEN_RE = re.compile(r"[a-z][a-z0-9]+")


def tokenize(text: str) -> set[str]:
    if not text:
        return set()
    return {tok for tok in TOKEN_RE.findall(text.lower()) if len(tok) >= 2 and tok not in STOPWORDS}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("loading WWEIA mapping (gtin -> wweia)", flush=True)
    con = sqlite3.connect(str(PRODUCTS_DB))
    fndds_tag = pd.read_sql_query("SELECT gtin_upc, fndds_code FROM product_fndds_tag", con)
    con.close()
    fndds_tag["fndds_code"] = fndds_tag["fndds_code"].astype(str).str.strip()
    fndds = pd.read_csv(FNDDS_CSV, dtype=str, keep_default_na=False)
    fndds.columns = [c.strip() for c in fndds.columns]
    fndds = fndds.rename(columns={
        "Food code": "fndds_code",
        "WWEIA Category description": "wweia_category",
    })[["fndds_code", "wweia_category"]].drop_duplicates(subset=["fndds_code"])
    fndds["fndds_code"] = fndds["fndds_code"].astype(str).str.strip()
    gtin_wweia = fndds_tag.merge(fndds, on="fndds_code", how="inner")[["gtin_upc", "wweia_category"]]
    print(f"  gtin->wweia rows: {len(gtin_wweia):,}", flush=True)

    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)

    print("loading current MAPS_TO state from graph", flush=True)
    maps = conn.execute(
        """
        MATCH (p:Product)-[m:MAPS_TO]->(e:ESHACode)-[:IN_ESHA_CATEGORY]->(ec:ESHACategory)
        OPTIONAL MATCH (p)-[:IN_CATEGORY]->(pc:ProductCategory)
        OPTIONAL MATCH (p)-[:MADE_BY]->(b:Brand)
        RETURN p.gtin_upc AS gtin_upc,
               p.description AS product_description,
               b.name AS brand,
               pc.name AS product_category,
               e.code AS current_esha_code,
               e.description AS current_esha_description,
               ec.name AS current_esha_family,
               m.score AS score,
               m.assignment_source AS assignment_source,
               m.status AS status
        """
    ).get_as_df()
    print(f"  rows: {len(maps):,}", flush=True)

    df = maps.merge(gtin_wweia, on="gtin_upc", how="left")

    QUARANTINED_STATUSES = ("quarantined", "quarantined_low_score", "quarantined_wweia_disagreement")

    print("computing dominant family per signal (from trusted rows only)", flush=True)
    trusted = df[
        (df["assignment_source"] == "fallback_category_family")
        & (df["score"] >= 5)
        & (~df["status"].isin(QUARANTINED_STATUSES))
    ]
    print(f"  trusted rows: {len(trusted):,}", flush=True)

    def dominant_by(group_col: str, src: pd.DataFrame) -> pd.DataFrame:
        g = src.dropna(subset=[group_col])
        cells = g.groupby([group_col, "current_esha_family"]).size().reset_index(name="n")
        totals = cells.groupby(group_col)["n"].sum().rename("total")
        cells = cells.merge(totals, on=group_col)
        dom = cells.sort_values([group_col, "n"], ascending=[True, False]).drop_duplicates(group_col, keep="first")
        dom["share"] = dom["n"] / dom["total"]
        return dom[dom["total"] >= MIN_SUPPORT][[group_col, "current_esha_family", "share"]].rename(
            columns={"current_esha_family": "dominant_family"}
        )

    wweia_dom = dominant_by("wweia_category", trusted)
    brand_dom = dominant_by("brand", trusted)
    pc_dom = dominant_by("product_category", trusted)
    print(f"  WWEIA->family signals:           {len(wweia_dom):,}", flush=True)
    print(f"  Brand->family signals:           {len(brand_dom):,}", flush=True)
    print(f"  ProductCategory->family signals: {len(pc_dom):,}", flush=True)

    # ---- Build per-product target family vote ----
    print("voting target family per quarantined row", flush=True)
    quar = df[df["status"].isin(QUARANTINED_STATUSES)].copy()
    print(f"  quarantined rows: {len(quar):,}", flush=True)

    quar = quar.merge(wweia_dom.add_prefix("wweia_"), left_on="wweia_category", right_on="wweia_wweia_category", how="left")
    quar = quar.merge(brand_dom.add_prefix("brand_"), left_on="brand", right_on="brand_brand", how="left")
    quar = quar.merge(pc_dom.add_prefix("pc_"), left_on="product_category", right_on="pc_product_category", how="left")

    def vote_family(row) -> tuple[str | None, float, list[str]]:
        votes: dict[str, float] = {}
        provenance: list[str] = []
        if isinstance(row.get("wweia_dominant_family"), str):
            f = row["wweia_dominant_family"]
            w = WEIGHT_WWEIA * float(row.get("wweia_share") or 0)
            votes[f] = votes.get(f, 0.0) + w
            provenance.append(f"wweia:{f}({w:.2f})")
        if isinstance(row.get("brand_dominant_family"), str):
            f = row["brand_dominant_family"]
            w = WEIGHT_BRAND * float(row.get("brand_share") or 0)
            votes[f] = votes.get(f, 0.0) + w
            provenance.append(f"brand:{f}({w:.2f})")
        if isinstance(row.get("pc_dominant_family"), str):
            f = row["pc_dominant_family"]
            w = WEIGHT_CATEGORY * float(row.get("pc_share") or 0)
            votes[f] = votes.get(f, 0.0) + w
            provenance.append(f"pc:{f}({w:.2f})")
        if not votes:
            return None, 0.0, []
        family, score = max(votes.items(), key=lambda kv: kv[1])
        return family, score, provenance

    print("  scoring votes...", flush=True)
    voted = quar.apply(vote_family, axis=1, result_type="expand")
    voted.columns = ["target_family", "vote_score", "vote_provenance"]
    quar = pd.concat([quar.reset_index(drop=True), voted.reset_index(drop=True)], axis=1)
    has_target = quar["target_family"].notna()
    print(f"  rows with target family: {has_target.sum():,}", flush=True)
    print(f"  rows without signal:     {(~has_target).sum():,}", flush=True)

    # ---- Pick best ESHA code in target family using entropy-weighted token overlap ----
    print("loading ESHA codes + token entropy from graph", flush=True)
    codes = conn.execute(
        """
        MATCH (e:ESHACode)-[:IN_ESHA_CATEGORY]->(c:ESHACategory)
        RETURN e.code AS code, e.description AS description, c.name AS family
        """
    ).get_as_df()
    print(f"  codes: {len(codes):,}", flush=True)
    tokens = conn.execute(
        "MATCH (t:Token) RETURN t.value AS value, t.entropy AS entropy"
    ).get_as_df()
    max_entropy = max(float(tokens["entropy"].max() or 1.0), 1e-6)
    token_weight = {row.value: 1.0 - (float(row.entropy or 0.0) / max_entropy) for row in tokens.itertuples()}

    print("  preparing per-family code-token index", flush=True)
    codes["_tokens"] = codes["description"].apply(tokenize)
    codes_by_family: dict[str, pd.DataFrame] = {f: g.reset_index(drop=True) for f, g in codes.groupby("family")}

    def best_code(product_desc: str, target_family: str) -> tuple[str | None, str | None, float]:
        if not target_family or target_family not in codes_by_family:
            return None, None, 0.0
        ptoks = tokenize(product_desc)
        if not ptoks:
            return None, None, 0.0
        family_codes = codes_by_family[target_family]
        best_score = -1.0
        best_code = None
        best_desc = None
        for code, desc, ctoks in zip(family_codes["code"], family_codes["description"], family_codes["_tokens"]):
            shared = ptoks & ctoks
            if not shared:
                continue
            s = sum(token_weight.get(tok, 0.5) for tok in shared)
            if s > best_score:
                best_score = s
                best_code = code
                best_desc = desc
        return best_code, best_desc, max(best_score, 0.0)

    print("computing best ESHA code per quarantined row (this is the slow part)", flush=True)
    targeted = quar[has_target].copy()
    proposals = targeted.apply(
        lambda r: best_code(r["product_description"], r["target_family"]),
        axis=1,
        result_type="expand",
    )
    proposals.columns = ["proposed_esha_code", "proposed_esha_description", "proposal_score"]
    targeted = pd.concat([targeted.reset_index(drop=True), proposals.reset_index(drop=True)], axis=1)

    found = targeted["proposed_esha_code"].notna()
    print(f"  found a proposal:        {found.sum():,}", flush=True)
    print(f"  no token overlap in family: {(~found).sum():,}", flush=True)

    out = targeted[
        [
            "gtin_upc",
            "product_description",
            "brand",
            "product_category",
            "wweia_category",
            "current_esha_code",
            "current_esha_description",
            "current_esha_family",
            "status",
            "target_family",
            "vote_score",
            "vote_provenance",
            "proposed_esha_code",
            "proposed_esha_description",
            "proposal_score",
        ]
    ]
    out["vote_provenance"] = out["vote_provenance"].apply(lambda v: " | ".join(v) if isinstance(v, list) else "")
    out.to_csv(OUT_PROPOSALS, index=False)
    print(f"  wrote {OUT_PROPOSALS.relative_to(ROOT)}", flush=True)

    summary = {
        "quarantined_input":              int(len(quar)),
        "quarantined_with_target_family": int(has_target.sum()),
        "quarantined_proposed":           int(found.sum()),
        "quarantined_unhealable":         int(len(quar) - found.sum()),
        "wweia_signal_rows":              int(quar["wweia_dominant_family"].notna().sum()),
        "brand_signal_rows":              int(quar["brand_dominant_family"].notna().sum()),
        "category_signal_rows":           int(quar["pc_dominant_family"].notna().sum()),
    }
    OUT_BASELINE.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
