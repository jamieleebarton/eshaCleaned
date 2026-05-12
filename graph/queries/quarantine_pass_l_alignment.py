"""Pass L — multi-signal alignment quarantine.

For each row in v3 (post Pass H), compute the alignment count between the
assigned ESHA's family and 4 independent signals (title, PC, brand×PC,
ingredient). If the assignment fails the alignment threshold, quarantine the
row so it gets re-routed by Pass D.

Then re-run Pass D + apply (the heal pass uses the same alignment filter
to restrict its candidate pool to families that pass alignment).

Outputs:
  graph/quarantine/needs_remap_l.csv          — rows quarantined by alignment failure
  graph/quarantine/baseline_after_pass_l.json — counts
  Updates MAPS_TO.status='quarantined_alignment_fail' in Kuzu graph
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import kuzu
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
PRODUCTS_DB = ROOT / "data" / "master_products.db"
# Pass L reads from the most recent CSV state. Defaults to v3 (mid-pipeline) but
# falls back to the matcher's raw output if v3 doesn't exist (start-of-cycle).
_V3 = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.v3.csv"
_RAW = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.csv"
V3_CSV = _V3 if _V3.exists() else _RAW
OUT_DIR = ROOT / "graph" / "quarantine"
OUT_NEEDS_REMAP = OUT_DIR / "needs_remap_l.csv"
OUT_BASELINE = OUT_DIR / "baseline_after_pass_l.json"
OUT_DOMINANTS_DIR = ROOT / "graph" / "cache"
OUT_DOMINANTS = OUT_DOMINANTS_DIR / "alignment_dominants.json"

sys.path.insert(0, str(ROOT / "implementation"))
from signal_alignment import (  # noqa: E402
    learn_dominants, compute_ingredient_signals, compute_alignment,
    AlignmentDominants,
)
from match_esha_to_products import tokens_for, detect_family, STOPWORDS  # noqa: E402


def title_family(description: str) -> str | None:
    if not description:
        return None
    toks = [t for t in tokens_for(description) if t and t not in STOPWORDS]
    norm = description.lower()
    try:
        return detect_family(toks, norm)
    except Exception:
        return None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DOMINANTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"loading {V3_CSV.name}", flush=True)
    v3 = pd.read_csv(V3_CSV, dtype=str, keep_default_na=False, low_memory=False)
    print(f"  rows: {len(v3):,}", flush=True)

    # Coalesce brand: prefer brand_name, fall back to brand_owner
    bn = v3["brand_name"].astype(str).str.strip()
    bo = v3["brand_owner"].astype(str).str.strip()
    v3["_brand"] = bn.where(bn != "", bo)

    # Trusted rows for learning dominants — CONSERVATIVE filter:
    # only the matcher's most confident output, never healed rows
    v3["score_num"] = pd.to_numeric(v3["score"], errors="coerce")
    trusted = v3[
        (v3["assignment_source"] == "fallback_category_family")
        & (v3["score_num"] >= 12)
        & (v3["best_esha_code"].astype(str).str.strip() != "")
    ].copy()
    trusted = trusted.rename(columns={"best_esha_family": "family"})
    trusted = trusted[["gtin_upc", "branded_food_category", "_brand", "family"]].rename(columns={"_brand": "brand"})
    print(f"  trusted rows for dominance learning: {len(trusted):,}", flush=True)

    print("learning PC + Brand×PC dominants", flush=True)
    dominants = learn_dominants(trusted)
    print(f"  PC dominants: {len(dominants.pc_dom):,}", flush=True)
    print(f"  Brand×PC dominants: {len(dominants.brand_pc_dom):,}", flush=True)

    print("loading ingredients + computing per-product ingredient signal", flush=True)
    con = sqlite3.connect(str(PRODUCTS_DB))
    fndds_tag = pd.read_sql_query("SELECT gtin_upc FROM product_fndds_tag", con)
    con.close()
    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)
    ing_pairs = conn.execute(
        "MATCH (p:Product)-[:HAS_INGREDIENT]->(i:Ingredient) RETURN p.gtin_upc AS gtin_upc, i.value AS ingredient"
    ).get_as_df()
    print(f"  HAS_INGREDIENT pairs: {len(ing_pairs):,}", flush=True)
    compute_ingredient_signals(ing_pairs, trusted[["gtin_upc", "family"]], dominants)
    print(f"  Ingredient signal per product: {len(dominants.ingredient_dom_per_gtin):,}", flush=True)

    # Persist dominants for heal passes to load
    print(f"saving dominants to {OUT_DOMINANTS.relative_to(ROOT)}", flush=True)
    dominants_json = {
        "pc_dom": dominants.pc_dom,
        "brand_pc_dom": {f"{k[0]}|||{k[1]}": v for k, v in dominants.brand_pc_dom.items()},
        "ingredient_dom_per_gtin": dominants.ingredient_dom_per_gtin,
        "ingredient_share_per_gtin": dominants.ingredient_share_per_gtin,
    }
    OUT_DOMINANTS.write_text(json.dumps(dominants_json, sort_keys=True))

    # Compute alignment for every assigned row
    print("computing alignment for every assigned row (this is the slow part)", flush=True)
    assigned = v3[v3["best_esha_code"].astype(str).str.strip() != ""].copy()
    print(f"  assigned rows: {len(assigned):,}", flush=True)
    assigned["_title_family"] = assigned["product_description"].apply(title_family)

    rows_to_check = assigned.to_dict("records")
    align_results = []
    veto_results = []
    for r in rows_to_check:
        ar = compute_alignment(
            title_family=r["_title_family"],
            branded_food_category=r["branded_food_category"] or None,
            brand=r["_brand"] or None,
            gtin_upc=r["gtin_upc"],
            candidate_family=r["best_esha_family"],
            dominants=dominants,
        )
        align_results.append((ar.agree_count, ar.available_count, "|".join(f"{k}={v}" for k, v in ar.signal_families.items())))

        # Ingredient veto check: if ingredient signal is strong AND incompatible with candidate, REJECT
        ing_fam = dominants.ingredient_dom_per_gtin.get(r["gtin_upc"])
        ing_share = dominants.ingredient_share_per_gtin.get(r["gtin_upc"], 0.0)
        from signal_alignment import _families_compatible as _compat  # type: ignore
        ing_veto_fail = bool(
            ing_fam
            and ing_share >= 0.6
            and not _compat(ing_fam, r["best_esha_family"])
        )
        veto_results.append(ing_veto_fail)

    assigned["_agree"] = [a[0] for a in align_results]
    assigned["_avail"] = [a[1] for a in align_results]
    assigned["_signals"] = [a[2] for a in align_results]
    assigned["_ingredient_veto"] = veto_results

    # Hard gate: ingredient veto trumps everything; otherwise require majority alignment
    align_fail = (
        (assigned["_avail"] >= 2)
        & (
            ((assigned["_avail"] == 4) & (assigned["_agree"] < 3))
            | ((assigned["_avail"] == 3) & (assigned["_agree"] < 2))
            | ((assigned["_avail"] == 2) & (assigned["_agree"] < 2))
        )
    )
    fail = align_fail | assigned["_ingredient_veto"]
    print(f"  ingredient veto failures (ground-truth contradiction): {assigned['_ingredient_veto'].sum():,}", flush=True)
    print(f"  rows passing alignment: {(~fail).sum():,}", flush=True)
    print(f"  rows FAILING alignment (will be quarantined): {fail.sum():,}", flush=True)

    # Distribution of failures
    print("  fail breakdown by available signal count:", flush=True)
    for n in [2, 3, 4]:
        sub = assigned[assigned["_avail"] == n]
        n_fail = (sub.index.isin(assigned[fail].index)).sum()
        print(f"    avail={n}: {n_fail:,} fail / {len(sub):,} total", flush=True)

    failing = assigned[fail].copy()
    failing[
        ["gtin_upc", "product_description", "branded_food_category", "_brand", "best_esha_code",
         "best_esha_description", "best_esha_family", "score", "assignment_source",
         "_title_family", "_agree", "_avail", "_signals", "_ingredient_veto"]
    ].rename(columns={"_brand": "brand", "_title_family": "title_family",
                      "_agree": "agree_count", "_avail": "available_count",
                      "_signals": "signal_breakdown",
                      "_ingredient_veto": "ingredient_veto_fail"}).to_csv(OUT_NEEDS_REMAP, index=False)
    print(f"  wrote {OUT_NEEDS_REMAP.relative_to(ROOT)}", flush=True)

    # Tag the failing rows in graph as quarantined
    print("tagging failing MAPS_TO edges as 'quarantined_alignment_fail'", flush=True)
    if len(failing) > 0:
        gtins_failing = failing["gtin_upc"].drop_duplicates().reset_index(drop=True)
        STAGING = ROOT / "graph" / "db" / "_staging"
        STAGING.mkdir(parents=True, exist_ok=True)
        path = STAGING / "_align_fail_gtins.parquet"
        pd.DataFrame({"gtin_upc": gtins_failing}).to_parquet(path, index=False)
        try:
            conn.execute("DROP TABLE _AlignFailGtin")
        except RuntimeError:
            pass
        conn.execute("CREATE NODE TABLE _AlignFailGtin(gtin_upc STRING, PRIMARY KEY(gtin_upc))")
        conn.execute(f"COPY _AlignFailGtin FROM '{path}'")
        conn.execute(
            """
            MATCH (a:_AlignFailGtin), (p:Product {gtin_upc: a.gtin_upc})-[m:MAPS_TO]->()
            WHERE m.status IS NULL
               OR m.status = 'unverified'
               OR m.status STARTS WITH 'wweia_'
            SET m.status = 'quarantined_alignment_fail'
            """
        )
        path.unlink(missing_ok=True)

    summary = {
        "v3_total": int(len(v3)),
        "assigned": int(len(assigned)),
        "trusted_rows_for_learning": int(len(trusted)),
        "pc_dominants": int(len(dominants.pc_dom)),
        "brand_pc_dominants": int(len(dominants.brand_pc_dom)),
        "ingredient_signals": int(len(dominants.ingredient_dom_per_gtin)),
        "ingredient_veto_failures": int(assigned["_ingredient_veto"].sum()),
        "alignment_failures": int(align_fail.sum()),
        "total_failures": int(fail.sum()),
        "passing": int((~fail).sum()),
    }
    OUT_BASELINE.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
