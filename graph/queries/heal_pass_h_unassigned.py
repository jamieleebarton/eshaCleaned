"""Pass H: graph-based proposal pass for products with NO ESHA assignment.

Pass D heals rows that already have a (bad) MAPS_TO edge by quarantining them
and proposing a replacement. But ~43k products have NO MAPS_TO at all
(assignment_source ends with '_no_match'). Pass D never sees them.

Pass H runs the same agreement-based voting on the unassigned bucket:
  joint (WWEIA, PC) dominant family    weight 1.5
  brand dominant family                weight 1.0
  product_category dominant family     weight 0.6
  WWEIA dominant family                weight 0.3 (LLM-tagged, lowest trust)

Pick best ESHA code in target family via entropy-weighted token overlap.
Apply HIGH + MEDIUM tier proposals to v2 → v3 CSV (filling empty slots only).
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
V2_CSV = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.v2.csv"
V3_CSV = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.v3.csv"
OUT_DIR = ROOT / "graph" / "quarantine"
OUT_PROPOSALS = OUT_DIR / "unassigned_proposals.csv"
OUT_DIFF = OUT_DIR / "applied_diff_h.csv"
OUT_BASELINE = OUT_DIR / "baseline_after_pass_h.json"

WEIGHT_JOINT = 1.5
WEIGHT_BRAND = 1.0
WEIGHT_PC = 0.6
WEIGHT_WWEIA = 0.3
MIN_SUPPORT = 20
JOINT_MIN_SUPPORT = 15

HIGH_JOINT_SHARE = 0.5
HIGH_PROPOSAL_SCORE = 1.0
MEDIUM_VOTE_SCORE = 0.2
MEDIUM_PROPOSAL_SCORE = 0.2

STOPWORDS = {
    "a", "an", "and", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it", "its",
    "of", "on", "or", "the", "to", "with", "without", "no", "not",
    "intl", "international", "style", "type", "plain", "regular", "prepared", "recipe", "fs", "usda",
    "oz", "fl", "lb", "lbs", "ct", "pk", "pkg", "ea", "each", "pack", "count", "container", "containers",
    "size", "sized", "large", "small", "medium", "jumbo", "mini", "big", "little",
}
TOKEN_RE = re.compile(r"[a-z][a-z0-9]+")

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
    print(f"  {len(gtin_wweia):,} products tagged with wweia", flush=True)

    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)

    print("loading current MAPS_TO state from graph (for trusted-rows learning)", flush=True)
    maps = conn.execute(
        """
        MATCH (p:Product)-[m:MAPS_TO]->(e:ESHACode)-[:IN_ESHA_CATEGORY]->(ec:ESHACategory)
        OPTIONAL MATCH (p)-[:IN_CATEGORY]->(pc:ProductCategory)
        OPTIONAL MATCH (p)-[:MADE_BY]->(b:Brand)
        RETURN p.gtin_upc AS gtin_upc,
               p.description AS product_description,
               b.name AS brand,
               pc.name AS product_category,
               ec.name AS current_esha_family,
               m.score AS score,
               m.assignment_source AS assignment_source
        """
    ).get_as_df()
    df = maps.merge(gtin_wweia, on="gtin_upc", how="left")

    trusted = df[
        (df["assignment_source"] == "fallback_category_family")
        & (df["score"] >= 5)
    ]
    print(f"  trusted rows for learning: {len(trusted):,}", flush=True)

    print("learning dominant family per signal", flush=True)
    wweia_dom = dominant_by(["wweia_category"], trusted, MIN_SUPPORT)
    brand_dom = dominant_by(["brand"], trusted, MIN_SUPPORT)
    pc_dom = dominant_by(["product_category"], trusted, MIN_SUPPORT)
    joint_dom = dominant_by(["wweia_category", "product_category"], trusted, JOINT_MIN_SUPPORT)
    print(f"  signals: WWEIA={len(wweia_dom):,}  Brand={len(brand_dom):,}  PC={len(pc_dom):,}  JOINT={len(joint_dom):,}", flush=True)

    print("loading v2 CSV to find unassigned products", flush=True)
    v2 = pd.read_csv(V2_CSV, dtype=str, keep_default_na=False, low_memory=False)
    unassigned = v2[v2["best_esha_code"].astype(str).str.strip() == ""].copy()
    print(f"  unassigned products in v2: {len(unassigned):,}", flush=True)

    print("voting target family per unassigned product", flush=True)
    # Fall back to brand_owner when brand_name is empty (e.g. COFFEE MATE products
    # have brand_name='' but brand_owner='COFFEE MATE'). Without this, those rows
    # have no brand signal and only score from WWEIA — usually below the apply threshold.
    brand_name = unassigned["brand_name"].astype(str).str.strip()
    brand_owner = unassigned["brand_owner"].astype(str).str.strip()
    unassigned = unassigned.copy()
    unassigned["brand"] = brand_name.where(brand_name != "", brand_owner)
    unassigned = unassigned.rename(columns={"branded_food_category": "product_category"})
    unassigned = unassigned.merge(gtin_wweia, on="gtin_upc", how="left")

    unassigned = unassigned.merge(joint_dom.add_prefix("joint_"), left_on=["wweia_category", "product_category"], right_on=["joint_wweia_category", "joint_product_category"], how="left")
    unassigned = unassigned.merge(brand_dom.add_prefix("brand_"), left_on="brand", right_on="brand_brand", how="left")
    unassigned = unassigned.merge(pc_dom.add_prefix("pc_"), left_on="product_category", right_on="pc_product_category", how="left")
    unassigned = unassigned.merge(wweia_dom.add_prefix("wweia_"), left_on="wweia_category", right_on="wweia_wweia_category", how="left")

    def vote_family(row) -> tuple[str | None, float, str]:
        votes: dict[str, float] = {}
        prov: list[str] = []
        for prefix, weight in (("joint_", WEIGHT_JOINT), ("brand_", WEIGHT_BRAND), ("pc_", WEIGHT_PC), ("wweia_", WEIGHT_WWEIA)):
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

    voted = unassigned.apply(vote_family, axis=1, result_type="expand")
    voted.columns = ["target_family", "vote_score", "vote_provenance"]
    unassigned = pd.concat([unassigned.reset_index(drop=True), voted.reset_index(drop=True)], axis=1)

    # Pass L — INGREDIENT VETO override (same as heal_pass_d)
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "implementation"))
    from signal_alignment import best_target_family, load_alignment_dominants_from_cache  # noqa: E402
    from match_esha_to_products import detect_family as _detect_family, tokens_for as _tokens_for, STOPWORDS as _STOPWORDS  # noqa: E402
    align_dominants = load_alignment_dominants_from_cache(ROOT / "graph" / "cache" / "alignment_dominants.json")
    if align_dominants is not None:
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
        for _, r in unassigned.iterrows():
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
        unassigned["target_family"] = new_targets
        print(f"  alignment overrides: {overrides:,} target families switched", flush=True)

    has_target = unassigned["target_family"].notna()
    print(f"  rows with target family: {has_target.sum():,}", flush=True)
    print(f"  rows with JOINT signal:  {unassigned['joint_dominant_family'].notna().sum():,}", flush=True)

    print("loading ESHA codes + token entropy", flush=True)
    codes = conn.execute(
        """
        MATCH (e:ESHACode)-[:IN_ESHA_CATEGORY]->(c:ESHACategory)
        RETURN e.code AS code, e.description AS description, c.name AS family
        """
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
            if not subtype_compatible(ptoks, ctoks, target_family):
                continue
            shared = ptoks & ctoks
            if not shared:
                continue
            matched_score = sum(token_weight.get(tok, 0.5) for tok in shared)
            extra = (ctoks - ptoks) - GENERIC_FILLER_TOKENS
            overspec = 0.35 * sum(token_weight.get(tok, 0.5) for tok in extra)
            overspec = min(overspec, 0.6 * matched_score)
            s = matched_score - overspec
            if s > best_score:
                best_score = s
                best_c = code
                best_d = desc
        return best_c, best_d, max(best_score, 0.0)

    print("picking best ESHA code per unassigned row", flush=True)
    targeted = unassigned[has_target].copy()
    proposals = targeted.apply(lambda r: best_code(r["product_description"], r["target_family"]), axis=1, result_type="expand")
    proposals.columns = ["proposed_esha_code", "proposed_esha_description", "proposal_score"]
    targeted = pd.concat([targeted.reset_index(drop=True), proposals.reset_index(drop=True)], axis=1)
    found = targeted["proposed_esha_code"].notna()
    print(f"  found a proposal:        {found.sum():,}", flush=True)
    print(f"  no token overlap:        {(~found).sum():,}", flush=True)

    targeted["has_joint_signal"] = targeted["joint_dominant_family"].notna()
    out = targeted[
        [
            "gtin_upc", "product_description", "brand", "product_category", "wweia_category",
            "joint_dominant_family", "joint_share", "has_joint_signal",
            "target_family", "vote_score", "vote_provenance",
            "proposed_esha_code", "proposed_esha_description", "proposal_score",
        ]
    ]
    out.to_csv(OUT_PROPOSALS, index=False)
    print(f"  wrote {OUT_PROPOSALS.relative_to(ROOT)}", flush=True)

    print("--- applying HIGH + MEDIUM proposals to v2 -> v3 ---", flush=True)
    out["proposal_score"] = pd.to_numeric(out["proposal_score"], errors="coerce")
    out["joint_share"] = pd.to_numeric(out["joint_share"], errors="coerce")
    out["vote_score"] = pd.to_numeric(out["vote_score"], errors="coerce")

    high_mask = (
        out["has_joint_signal"]
        & (out["joint_share"].fillna(0) >= HIGH_JOINT_SHARE)
        & (out["proposal_score"].fillna(0) >= HIGH_PROPOSAL_SCORE)
        & out["proposed_esha_code"].notna()
    )
    medium_mask = (
        ~high_mask
        & (out["vote_score"].fillna(0) >= MEDIUM_VOTE_SCORE)
        & (out["proposal_score"].fillna(0) >= MEDIUM_PROPOSAL_SCORE)
        & out["proposed_esha_code"].notna()
    )
    out["confidence_tier"] = "low"
    out.loc[high_mask, "confidence_tier"] = "high"
    out.loc[medium_mask, "confidence_tier"] = "medium"
    print("  tier counts:", flush=True)
    print(out["confidence_tier"].value_counts().to_string(), flush=True)

    apply = out[out["confidence_tier"].isin(["high", "medium"])].copy().set_index("gtin_upc")
    print(f"  applying {len(apply):,}", flush=True)

    v2_indexed = v2.set_index("gtin_upc")
    overlap = v2_indexed.index.intersection(apply.index)
    diff_rows = []
    for gtin in overlap:
        proposal = apply.loc[gtin]
        if isinstance(proposal, pd.DataFrame):
            proposal = proposal.iloc[0]
        new_code = str(proposal["proposed_esha_code"]).split(".")[0]
        if not new_code or new_code == "nan":
            continue
        v2_indexed.at[gtin, "best_esha_code"] = new_code
        v2_indexed.at[gtin, "best_esha_description"] = str(proposal["proposed_esha_description"])
        v2_indexed.at[gtin, "best_esha_family"] = str(proposal["target_family"])
        v2_indexed.at[gtin, "assignment_source"] = f"healed_v0.2_h_{proposal['confidence_tier']}"
        diff_rows.append({
            "gtin_upc": gtin,
            "new_esha_code": new_code,
            "new_esha_description": str(proposal["proposed_esha_description"]),
            "new_esha_family": str(proposal["target_family"]),
            "tier": proposal["confidence_tier"],
            "vote_provenance": str(proposal["vote_provenance"]),
        })

    diff_df = pd.DataFrame(diff_rows)
    diff_df.to_csv(OUT_DIFF, index=False)
    print(f"  diff rows written: {len(diff_df):,}  -> {OUT_DIFF.relative_to(ROOT)}", flush=True)

    v3 = v2_indexed.reset_index()
    v3 = v3[v2.columns.tolist()]
    v3.to_csv(V3_CSV, index=False)
    print(f"  wrote {V3_CSV.relative_to(ROOT)}", flush=True)

    summary = {
        "v2_unassigned_input": int(len(unassigned)),
        "with_target_family": int(has_target.sum()),
        "with_joint_signal": int(unassigned["joint_dominant_family"].notna().sum()),
        "proposals_total": int(len(out[out["proposed_esha_code"].notna()])),
        "tier_high": int(high_mask.sum()),
        "tier_medium": int(medium_mask.sum()),
        "tier_low": int(((~high_mask) & (~medium_mask) & out["proposed_esha_code"].notna()).sum()),
        "applied_changes": int(len(diff_df)),
        "v3_total_assignments": int((v3["best_esha_code"].astype(str).str.strip() != "").sum()),
        "v3_unassigned": int((v3["best_esha_code"].astype(str).str.strip() == "").sum()),
    }
    OUT_BASELINE.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
