"""Pass D.2: graph-based healing using cross-source AGREEMENT signal.

Single-source signals (WWEIA alone, ProductCategory alone) are each noisy
in their own way. But where two noisy sources INDEPENDENTLY agree, the
combined signal is much stronger than either alone — provided the noise
is independent.

This pass votes on target ESHA family using:

  Joint (WWEIA, ProductCategory) dominant family   — weight 1.5
  Brand dominant family                            — weight 1.0
  ProductCategory dominant family                  — weight 0.6
  WWEIA dominant family                            — weight 0.3 (LLM-tagged, lowest trust)

When (WWEIA, PC) cell has high support and a clear dominant family, that
joint signal carries the day — even if a single source disagrees.

All "dominants" are learned from trusted rows
(assignment_source = 'fallback_category_family' AND score >= 5 AND not quarantined).
"""
from __future__ import annotations

import json
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
OUT_PROPOSALS = OUT_DIR / "healed_proposals_agreement.csv"
OUT_BASELINE = OUT_DIR / "baseline_after_pass_d_agreement.json"

WEIGHT_JOINT = 1.5
WEIGHT_BRAND = 1.0
WEIGHT_PC = 0.6
WEIGHT_WWEIA = 0.3
MIN_SUPPORT = 20
JOINT_MIN_SUPPORT = 15

STOPWORDS = {
    "a", "an", "and", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it", "its",
    "of", "on", "or", "the", "to", "with", "without", "no", "not",
    "intl", "international", "style", "type", "plain", "regular", "prepared", "recipe", "fs", "usda",
    "oz", "fl", "lb", "lbs", "ct", "pk", "pkg", "ea", "each", "pack", "count", "container", "containers",
    "size", "sized", "large", "small", "medium", "jumbo", "mini", "big", "little",
}
TOKEN_RE = re.compile(r"[a-z][a-z0-9]+")

# Compound expansions, mirroring match_esha_to_products.py. Lets "applesauce"
# match "apple sauce" (and vice versa) bidirectionally during token overlap.
COMPOUND_EXPANSIONS = {
    "applesauce": {"apple", "sauce", "applesauce"},
    "almondmilk": {"almond", "milk"},
    "cashewmilk": {"cashew", "milk"},
    "coconutmilk": {"coconut", "milk"},
    "goatcheese": {"goat", "cheese"},
    "hempmilk": {"hemp", "milk"},
    "oatmilk": {"oat", "milk"},
    "ricemilk": {"rice", "milk"},
    "soymilk": {"soy", "milk", "soymilk"},
    "buttermilk": {"butter", "milk", "buttermilk"},
    "cornbread": {"corn", "bread", "cornbread"},
    "sourdough": {"sour", "dough", "sourdough"},
    "shortbread": {"short", "bread", "shortbread"},
    "gingerbread": {"ginger", "bread", "gingerbread"},
    "cheesecake": {"cheese", "cake", "cheesecake"},
    "cupcake": {"cup", "cake", "cupcake"},
    "pancake": {"pan", "cake", "pancake"},
    "shortcake": {"short", "cake", "shortcake"},
    "icecream": {"ice", "cream", "icecream"},
    "icetea": {"ice", "tea", "icetea"},
    "iceberg": {"iceberg"},
}
COMPOUND_GLUE_PAIRS = {
    ("apple", "sauce"): "applesauce",
    ("ice", "cream"): "icecream",
    ("corn", "bread"): "cornbread",
    ("cup", "cake"): "cupcake",
    ("pan", "cake"): "pancake",
    ("short", "cake"): "shortcake",
    ("short", "bread"): "shortbread",
    ("ginger", "bread"): "gingerbread",
    ("cheese", "cake"): "cheesecake",
    ("butter", "milk"): "buttermilk",
    ("soy", "milk"): "soymilk",
    ("almond", "milk"): "almondmilk",
    ("coconut", "milk"): "coconutmilk",
}


def tokenize(text: str) -> set[str]:
    if not text:
        return set()
    raw = [tok for tok in TOKEN_RE.findall(text.lower()) if len(tok) >= 2 and tok not in STOPWORDS]
    out = set(raw)
    for tok in raw:
        if tok in COMPOUND_EXPANSIONS:
            out.update(COMPOUND_EXPANSIONS[tok])
    # also glue adjacent pairs like "apple sauce" -> "applesauce"
    for i in range(len(raw) - 1):
        glued = COMPOUND_GLUE_PAIRS.get((raw[i], raw[i + 1]))
        if glued:
            out.add(glued)
    return out


def dominant_by(group_cols: list[str], src: pd.DataFrame, min_support: int) -> pd.DataFrame:
    g = src.dropna(subset=group_cols)
    cells = g.groupby(group_cols + ["current_esha_family"]).size().reset_index(name="n")
    totals = cells.groupby(group_cols)["n"].sum().rename("total").reset_index()
    cells = cells.merge(totals, on=group_cols)
    dom = cells.sort_values(group_cols + ["n"], ascending=[True] * len(group_cols) + [False]).drop_duplicates(group_cols, keep="first")
    dom = dom[dom["total"] >= min_support].copy()
    dom["share"] = dom["n"] / dom["total"]
    return dom[group_cols + ["current_esha_family", "share", "total"]].rename(columns={"current_esha_family": "dominant_family"})


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("loading gtin -> wweia mapping", flush=True)
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
    print(f"  {len(gtin_wweia):,} products tagged with wweia", flush=True)

    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)

    print("loading current MAPS_TO state", flush=True)
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
    print(f"  {len(maps):,} maps_to rows", flush=True)
    df = maps.merge(gtin_wweia, on="gtin_upc", how="left")

    QUARANTINED = ("quarantined", "quarantined_low_score", "quarantined_wweia_disagreement")

    trusted = df[
        (df["assignment_source"] == "fallback_category_family")
        & (df["score"] >= 5)
        & (~df["status"].isin(QUARANTINED))
    ]
    print(f"  trusted rows: {len(trusted):,}", flush=True)

    print("learning dominant family per signal", flush=True)
    wweia_dom = dominant_by(["wweia_category"], trusted, MIN_SUPPORT)
    brand_dom = dominant_by(["brand"], trusted, MIN_SUPPORT)
    pc_dom = dominant_by(["product_category"], trusted, MIN_SUPPORT)
    joint_dom = dominant_by(["wweia_category", "product_category"], trusted, JOINT_MIN_SUPPORT)
    print(f"  WWEIA-only signals:           {len(wweia_dom):,}", flush=True)
    print(f"  Brand-only signals:           {len(brand_dom):,}", flush=True)
    print(f"  ProductCategory-only signals: {len(pc_dom):,}", flush=True)
    print(f"  JOINT (WWEIA x PC) signals:   {len(joint_dom):,}  (min support {JOINT_MIN_SUPPORT})", flush=True)

    print("voting target family per quarantined row", flush=True)
    quar = df[df["status"].isin(QUARANTINED)].copy()
    print(f"  quarantined rows: {len(quar):,}", flush=True)

    quar = quar.merge(joint_dom.add_prefix("joint_"), left_on=["wweia_category", "product_category"], right_on=["joint_wweia_category", "joint_product_category"], how="left")
    quar = quar.merge(brand_dom.add_prefix("brand_"), left_on="brand", right_on="brand_brand", how="left")
    quar = quar.merge(pc_dom.add_prefix("pc_"), left_on="product_category", right_on="pc_product_category", how="left")
    quar = quar.merge(wweia_dom.add_prefix("wweia_"), left_on="wweia_category", right_on="wweia_wweia_category", how="left")

    def vote_family(row) -> tuple[str | None, float, str]:
        votes: dict[str, float] = {}
        prov: list[str] = []
        for prefix, weight in (
            ("joint_", WEIGHT_JOINT),
            ("brand_", WEIGHT_BRAND),
            ("pc_", WEIGHT_PC),
            ("wweia_", WEIGHT_WWEIA),
        ):
            f = row.get(f"{prefix}dominant_family")
            s = row.get(f"{prefix}share")
            if isinstance(f, str) and pd.notna(s):
                w = weight * float(s)
                votes[f] = votes.get(f, 0.0) + w
                prov.append(f"{prefix.rstrip('_')}:{f}({w:.2f})")
        if not votes:
            return None, 0.0, ""
        family, sc = max(votes.items(), key=lambda kv: kv[1])
        return family, sc, " | ".join(prov)

    voted = quar.apply(vote_family, axis=1, result_type="expand")
    voted.columns = ["target_family", "vote_score", "vote_provenance"]
    quar = pd.concat([quar.reset_index(drop=True), voted.reset_index(drop=True)], axis=1)
    has_target = quar["target_family"].notna()
    print(f"  rows with target family: {has_target.sum():,}", flush=True)
    print(f"  rows with JOINT signal:  {quar['joint_dominant_family'].notna().sum():,}", flush=True)

    print("loading ESHA codes + token entropy", flush=True)
    codes = conn.execute(
        """
        MATCH (e:ESHACode)-[:IN_ESHA_CATEGORY]->(c:ESHACategory)
        RETURN e.code AS code, e.description AS description, c.name AS family
        """
    ).get_as_df()
    tokens = conn.execute(
        "MATCH (t:Token) RETURN t.value AS value, t.entropy AS entropy"
    ).get_as_df()
    max_entropy = max(float(tokens["entropy"].max() or 1.0), 1e-6)
    token_weight = {row.value: 1.0 - (float(row.entropy or 0.0) / max_entropy) for row in tokens.itertuples()}
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
        best_c = None
        best_d = None
        for code, desc, ctoks in zip(family_codes["code"], family_codes["description"], family_codes["_tokens"]):
            shared = ptoks & ctoks
            if not shared:
                continue
            s = sum(token_weight.get(tok, 0.5) for tok in shared)
            if s > best_score:
                best_score = s
                best_c = code
                best_d = desc
        return best_c, best_d, max(best_score, 0.0)

    print("picking best ESHA code per quarantined row", flush=True)
    targeted = quar[has_target].copy()
    proposals = targeted.apply(
        lambda r: best_code(r["product_description"], r["target_family"]),
        axis=1,
        result_type="expand",
    )
    proposals.columns = ["proposed_esha_code", "proposed_esha_description", "proposal_score"]
    targeted = pd.concat([targeted.reset_index(drop=True), proposals.reset_index(drop=True)], axis=1)
    found = targeted["proposed_esha_code"].notna()
    print(f"  found a proposal:                  {found.sum():,}", flush=True)
    print(f"  no token overlap in target family: {(~found).sum():,}", flush=True)

    targeted["has_joint_signal"] = targeted["joint_dominant_family"].notna()
    out = targeted[
        [
            "gtin_upc", "product_description", "brand", "product_category", "wweia_category",
            "current_esha_code", "current_esha_description", "current_esha_family", "status",
            "joint_dominant_family", "joint_share", "has_joint_signal",
            "target_family", "vote_score", "vote_provenance",
            "proposed_esha_code", "proposed_esha_description", "proposal_score",
        ]
    ]
    out.to_csv(OUT_PROPOSALS, index=False)
    print(f"  wrote {OUT_PROPOSALS.relative_to(ROOT)}", flush=True)

    summary = {
        "quarantined_input": int(len(quar)),
        "quarantined_with_target_family": int(has_target.sum()),
        "quarantined_with_joint_signal": int(quar["joint_dominant_family"].notna().sum()),
        "quarantined_proposed": int(found.sum()),
        "quarantined_unhealable": int(len(quar) - found.sum()),
        "joint_signal_count": int(len(joint_dom)),
        "single_source_wweia_signal_count": int(len(wweia_dom)),
        "single_source_brand_signal_count": int(len(brand_dom)),
        "single_source_pc_signal_count": int(len(pc_dom)),
    }
    OUT_BASELINE.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
