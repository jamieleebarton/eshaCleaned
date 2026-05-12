"""Pass D v3: agreement-based heal with INGREDIENT signal added.

Five voting signals (was four). Ingredient is the new one and it's strong
because it's the most factual: a product can lie about its retail category
but it can't lie about its ingredient label.

  Joint (WWEIA, PC) dominant family    weight 1.5
  Ingredient-implied family            weight 1.2  (NEW)
  Brand dominant family                weight 1.0
  ProductCategory dominant family      weight 0.6
  WWEIA dominant family                weight 0.3

Ingredient family is computed by:
  1. For each Ingredient, find its dominant ESHA family among trusted rows
     (assignment_source = fallback_category_family AND score >= 5).
  2. For each Product, aggregate its ingredients' votes (weighted by ingredient
     dominance share). Pick the winning family.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import kuzu
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
PRODUCTS_DB = ROOT / "data" / "master_products.db"
FNDDS_CSV = ROOT / "data" / "fndds" / "MainFoodDesc16.csv"
OUT_DIR = ROOT / "graph" / "quarantine"
OUT_PROPOSALS = OUT_DIR / "healed_proposals_agreement.csv"  # overwrites prior
OUT_BASELINE = OUT_DIR / "baseline_after_pass_d_v3.json"

WEIGHT_JOINT = 1.5
WEIGHT_INGREDIENT = 1.2
WEIGHT_BRAND_PC = 1.1   # Pass K.5 — per-PC brand dominance, slightly stronger than brand alone
WEIGHT_BRAND = 0.7      # demoted; full brand was too coarse for multi-PC house brands
WEIGHT_PC = 0.6
WEIGHT_WWEIA = 0.3
MIN_SUPPORT = 20
JOINT_MIN_SUPPORT = 15
BRAND_PC_MIN_SUPPORT = 15
INGREDIENT_MIN_SUPPORT = 50

STOPWORDS = {
    "a","an","and","as","at","be","by","for","from","in","into","is","it","its",
    "of","on","or","the","to","with","without","no","not",
    "intl","international","style","type","plain","regular","prepared","recipe","fs","usda",
    "oz","fl","lb","lbs","ct","pk","pkg","ea","each","pack","count","container","containers",
    "size","sized","large","small","medium","jumbo","mini","big","little",
}
TOKEN_RE = re.compile(r"[a-z][a-z0-9]+")
COMPOUND_EXPANSIONS = {
    "applesauce": {"apple", "sauce", "applesauce"},
    "almondmilk": {"almond", "milk"},
    "buttermilk": {"butter", "milk", "buttermilk"},
    "cornbread": {"corn", "bread", "cornbread"},
    "cheesecake": {"cheese", "cake", "cheesecake"},
    "cupcake": {"cup", "cake", "cupcake"},
    "icecream": {"ice", "cream", "icecream"},
}
COMPOUND_GLUE_PAIRS = {
    ("apple", "sauce"): "applesauce",
    ("ice", "cream"): "icecream",
    ("corn", "bread"): "cornbread",
    ("cup", "cake"): "cupcake",
    ("cheese", "cake"): "cheesecake",
    ("butter", "milk"): "buttermilk",
}


def tokenize(text: str) -> set[str]:
    if not text:
        return set()
    raw = [tok for tok in TOKEN_RE.findall(text.lower()) if len(tok) >= 2 and tok not in STOPWORDS]
    out = set(raw)
    for tok in raw:
        if tok in COMPOUND_EXPANSIONS:
            out.update(COMPOUND_EXPANSIONS[tok])
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

    print("loading WWEIA mapping", flush=True)
    con = sqlite3.connect(str(PRODUCTS_DB))
    fndds_tag = pd.read_sql_query("SELECT gtin_upc, fndds_code FROM product_fndds_tag", con)
    con.close()
    fndds_tag["fndds_code"] = fndds_tag["fndds_code"].astype(str).str.strip()
    fndds = pd.read_csv(FNDDS_CSV, dtype=str, keep_default_na=False)
    fndds.columns = [c.strip() for c in fndds.columns]
    fndds = fndds.rename(columns={"Food code": "fndds_code", "WWEIA Category description": "wweia_category"})[["fndds_code", "wweia_category"]].drop_duplicates(subset=["fndds_code"])
    fndds["fndds_code"] = fndds["fndds_code"].astype(str).str.strip()
    gtin_wweia = fndds_tag.merge(fndds, on="fndds_code", how="inner")[["gtin_upc", "wweia_category"]]

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
    df = maps.merge(gtin_wweia, on="gtin_upc", how="left")
    print(f"  rows: {len(df):,}", flush=True)

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
    # Pass K.5 — per-PC brand dominance (e.g. ROUNDY'S × Popcorn,Peanuts,Seeds → nut_seed
    # rather than ROUNDY'S brand-wide which could be anything)
    brand_pc_dom = dominant_by(["brand", "product_category"], trusted, BRAND_PC_MIN_SUPPORT)
    print(f"  signals: WWEIA={len(wweia_dom):,}  Brand={len(brand_dom):,}  PC={len(pc_dom):,}  JOINT={len(joint_dom):,}  Brand×PC={len(brand_pc_dom):,}", flush=True)

    print("computing INGREDIENT signal (this is the new bit)", flush=True)
    ing_pairs = conn.execute(
        "MATCH (p:Product)-[:HAS_INGREDIENT]->(i:Ingredient) RETURN p.gtin_upc AS gtin_upc, i.value AS ingredient"
    ).get_as_df()
    print(f"  HAS_INGREDIENT pairs: {len(ing_pairs):,}", flush=True)

    trusted_basic = trusted[["gtin_upc", "current_esha_family"]]
    ing_trusted = ing_pairs.merge(trusted_basic, on="gtin_upc", how="inner")
    print(f"  ingredient-trusted pairs: {len(ing_trusted):,}", flush=True)

    ingredient_dom = dominant_by(["ingredient"], ing_trusted.rename(columns={}), INGREDIENT_MIN_SUPPORT)
    print(f"  ingredients with confident dominant family: {len(ingredient_dom):,}", flush=True)

    ing_with_dom = ing_pairs.merge(ingredient_dom[["ingredient", "dominant_family", "share"]], on="ingredient", how="left").dropna(subset=["dominant_family"])
    ing_votes = ing_with_dom.groupby(["gtin_upc", "dominant_family"])["share"].sum().reset_index().rename(columns={"share": "vote_weight"})
    ing_totals = ing_votes.groupby("gtin_upc")["vote_weight"].sum().rename("total_vote").reset_index()
    ing_votes = ing_votes.merge(ing_totals, on="gtin_upc")
    ing_signal = ing_votes.sort_values(["gtin_upc", "vote_weight"], ascending=[True, False]).drop_duplicates("gtin_upc", keep="first")
    ing_signal["ingredient_share"] = ing_signal["vote_weight"] / ing_signal["total_vote"].clip(lower=1e-6)
    ing_signal = ing_signal[["gtin_upc", "dominant_family", "ingredient_share"]].rename(columns={"dominant_family": "ingredient_dominant_family"})
    print(f"  products with ingredient signal: {len(ing_signal):,}", flush=True)

    print("voting target family per quarantined row", flush=True)
    quar = df[df["status"].isin(QUARANTINED)].copy()
    print(f"  quarantined rows: {len(quar):,}", flush=True)

    quar = quar.merge(joint_dom.add_prefix("joint_"), left_on=["wweia_category", "product_category"], right_on=["joint_wweia_category", "joint_product_category"], how="left")
    quar = quar.merge(brand_dom.add_prefix("brand_"), left_on="brand", right_on="brand_brand", how="left")
    quar = quar.merge(brand_pc_dom.add_prefix("bpc_"), left_on=["brand", "product_category"], right_on=["bpc_brand", "bpc_product_category"], how="left")
    quar = quar.merge(pc_dom.add_prefix("pc_"), left_on="product_category", right_on="pc_product_category", how="left")
    quar = quar.merge(wweia_dom.add_prefix("wweia_"), left_on="wweia_category", right_on="wweia_wweia_category", how="left")
    quar = quar.merge(ing_signal, on="gtin_upc", how="left")

    def vote_family(row) -> tuple[str | None, float, str]:
        votes: dict[str, float] = {}
        prov: list[str] = []
        for prefix, weight in (("joint_", WEIGHT_JOINT), ("bpc_", WEIGHT_BRAND_PC), ("brand_", WEIGHT_BRAND), ("pc_", WEIGHT_PC), ("wweia_", WEIGHT_WWEIA)):
            f = row.get(f"{prefix}dominant_family")
            s = row.get(f"{prefix}share")
            if isinstance(f, str) and pd.notna(s):
                w = weight * float(s)
                votes[f] = votes.get(f, 0.0) + w
                prov.append(f"{prefix.rstrip('_')}:{f}({w:.2f})")
        # ingredient signal (6th)
        f = row.get("ingredient_dominant_family")
        s = row.get("ingredient_share")
        if isinstance(f, str) and pd.notna(s):
            w = WEIGHT_INGREDIENT * float(s)
            votes[f] = votes.get(f, 0.0) + w
            prov.append(f"ing:{f}({w:.2f})")
        if not votes:
            return None, 0.0, ""
        family, sc = max(votes.items(), key=lambda kv: kv[1])
        return family, sc, " | ".join(prov)

    voted = quar.apply(vote_family, axis=1, result_type="expand")
    voted.columns = ["target_family", "vote_score", "vote_provenance"]
    quar = pd.concat([quar.reset_index(drop=True), voted.reset_index(drop=True)], axis=1)

    # Pass L — INGREDIENT VETO override.
    # If ingredient signal contradicts the voted family, override to ingredient-implied.
    # Ingredients are the closest thing to ground truth — they're regulated label data.
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "implementation"))
    from signal_alignment import best_target_family, load_alignment_dominants_from_cache  # noqa: E402
    from match_esha_to_products import detect_family as _detect_family, tokens_for as _tokens_for, STOPWORDS as _STOPWORDS  # noqa: E402
    align_dominants = load_alignment_dominants_from_cache(ROOT / "graph" / "cache" / "alignment_dominants.json")
    if align_dominants is not None:
        print(f"  loaded alignment dominants: PC={len(align_dominants.pc_dom):,} BrandPC={len(align_dominants.brand_pc_dom):,} Ingredient={len(align_dominants.ingredient_dom_per_gtin):,}", flush=True)

        def _title_family(desc):
            if not desc:
                return None
            try:
                toks = [t for t in _tokens_for(desc) if t and t not in _STOPWORDS]
                return _detect_family(toks, str(desc).lower())
            except Exception:
                return None

        overrides = 0
        new_targets = []
        for _, r in quar.iterrows():
            tf = r["target_family"]
            if not isinstance(tf, str):
                new_targets.append(tf)
                continue
            override = best_target_family(
                tf,
                title_family=_title_family(r["product_description"]),
                branded_food_category=r["product_category"] if isinstance(r["product_category"], str) else None,
                brand=r["brand"] if isinstance(r["brand"], str) else None,
                gtin_upc=r["gtin_upc"],
                dominants=align_dominants,
            )
            if override != tf:
                overrides += 1
            new_targets.append(override)
        quar["target_family"] = new_targets
        print(f"  alignment overrides: {overrides:,} target families switched", flush=True)
    else:
        print("  WARNING: alignment dominants cache not found; running without ingredient veto", flush=True)

    has_target = quar["target_family"].notna()
    print(f"  rows with target family: {has_target.sum():,}", flush=True)
    print(f"  rows with INGREDIENT signal: {quar['ingredient_dominant_family'].notna().sum():,}", flush=True)
    print(f"  rows with JOINT signal:      {quar['joint_dominant_family'].notna().sum():,}", flush=True)

    print("loading ESHA codes + token entropy", flush=True)
    codes = conn.execute(
        "MATCH (e:ESHACode)-[:IN_ESHA_CATEGORY]->(c:ESHACategory) RETURN e.code AS code, e.description AS description, c.name AS family"
    ).get_as_df()
    tokens = conn.execute("MATCH (t:Token) RETURN t.value AS value, t.entropy AS entropy").get_as_df()
    max_entropy = max(float(tokens["entropy"].max() or 1.0), 1e-6)
    token_weight = {row.value: 1.0 - (float(row.entropy or 0.0) / max_entropy) for row in tokens.itertuples()}
    codes["_tokens"] = codes["description"].apply(tokenize)
    codes_by_family: dict[str, pd.DataFrame] = {f: g.reset_index(drop=True) for f, g in codes.groupby("family")}

    # Pass K: import shared subtype + filler helpers from matcher
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "implementation"))
    from match_esha_to_products import subtype_compatible, GENERIC_FILLER_TOKENS  # noqa: E402

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
            # Pass K.3 — subtype gate
            if not subtype_compatible(ptoks, ctoks, target_family):
                continue
            shared = ptoks & ctoks
            if not shared:
                continue
            matched_score = sum(token_weight.get(t, 0.5) for t in shared)
            # Pass K.2 — over-specific attractor penalty: ESHA tokens NOT in product (excluding generic filler)
            extra = (ctoks - ptoks) - GENERIC_FILLER_TOKENS
            overspec = 0.35 * sum(token_weight.get(t, 0.5) for t in extra)
            overspec = min(overspec, 0.6 * matched_score)
            s = matched_score - overspec
            if s > best_score:
                best_score = s
                best_c = code
                best_d = desc
        return best_c, best_d, max(best_score, 0.0)

    print("picking best ESHA code per quarantined row", flush=True)
    targeted = quar[has_target].copy()
    proposals = targeted.apply(lambda r: best_code(r["product_description"], r["target_family"]), axis=1, result_type="expand")
    proposals.columns = ["proposed_esha_code", "proposed_esha_description", "proposal_score"]
    targeted = pd.concat([targeted.reset_index(drop=True), proposals.reset_index(drop=True)], axis=1)
    found = targeted["proposed_esha_code"].notna()
    print(f"  found a proposal: {found.sum():,}", flush=True)

    targeted["has_joint_signal"] = targeted["joint_dominant_family"].notna()
    targeted["has_ingredient_signal"] = targeted["ingredient_dominant_family"].notna()
    out = targeted[
        [
            "gtin_upc", "product_description", "brand", "product_category", "wweia_category",
            "current_esha_code", "current_esha_description", "current_esha_family", "status",
            "joint_dominant_family", "joint_share", "has_joint_signal",
            "ingredient_dominant_family", "ingredient_share", "has_ingredient_signal",
            "target_family", "vote_score", "vote_provenance",
            "proposed_esha_code", "proposed_esha_description", "proposal_score",
        ]
    ]
    out.to_csv(OUT_PROPOSALS, index=False)
    print(f"  wrote {OUT_PROPOSALS.relative_to(ROOT)}", flush=True)

    summary = {
        "quarantined_input": int(len(quar)),
        "with_target_family": int(has_target.sum()),
        "with_joint_signal": int(quar["joint_dominant_family"].notna().sum()),
        "with_ingredient_signal": int(quar["ingredient_dominant_family"].notna().sum()),
        "with_both_joint_and_ingredient": int((quar["joint_dominant_family"].notna() & quar["ingredient_dominant_family"].notna()).sum()),
        "proposals_with_target_code": int(found.sum()),
        "joint_signal_count": int(len(joint_dom)),
        "ingredient_signal_count": int(len(ingredient_dom)),
    }
    OUT_BASELINE.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
