"""Pass C: WWEIA truth-signal quarantine + rescue.

WWEIA is USDA's gold-standard food categorization. Joining
  Product (gtin)  ->  product_fndds_tag (gtin -> fndds_code)
                  ->  MainFoodDesc16    (fndds_code -> wweia category)
gives us an authoritative outside category for ~461k products.

Algorithm (no hand-written rules):
  1. For each WWEIA category, find its dominant ESHA family among 'trusted'
     rows (assignment_source = 'fallback_category_family' AND score >= 5).
     This is the data telling us 'when the matcher is at its most confident,
     this WWEIA category lands here'.
  2. For every product, compare its current esha_family to its WWEIA's
     dominant family.
  3. DISAGREEMENT  -> quarantine (status = 'quarantined_wweia_disagreement')
  4. AGREEMENT (and was previously quarantined_low_score) -> RESCUE
     (status = 'wweia_validated_low_score')

Net effect: WWEIA overrides the score cap. False positives from Pass A.2
get rescued, real disagreements get caught regardless of source/score.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import kuzu
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
PRODUCTS_DB = ROOT / "data" / "master_products.db"
FNDDS_CSV = ROOT / "data" / "fndds" / "MainFoodDesc16.csv"
OUT_DIR = ROOT / "graph" / "quarantine"
OUT_DISAGREE = OUT_DIR / "wweia_disagreements.csv"
OUT_RESCUE = OUT_DIR / "wweia_rescued_low_score.csv"
OUT_BASELINE = OUT_DIR / "baseline_after_pass_c.json"
OUT_WWEIA_MAP = OUT_DIR / "wweia_dominant_esha_family.csv"

MIN_TRUSTED_SUPPORT = 20  # WWEIA cell needs at least this many trusted rows to seed a dominant family


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("loading product_fndds_tag from master_products.db", flush=True)
    con = sqlite3.connect(str(PRODUCTS_DB))
    fndds_tag = pd.read_sql_query(
        "SELECT gtin_upc, fndds_code FROM product_fndds_tag",
        con,
    )
    con.close()
    fndds_tag["fndds_code"] = fndds_tag["fndds_code"].astype(str).str.strip()
    print(f"  product_fndds_tag rows: {len(fndds_tag):,}", flush=True)

    print(f"loading FNDDS taxonomy from {FNDDS_CSV.name}", flush=True)
    fndds = pd.read_csv(FNDDS_CSV, dtype=str, keep_default_na=False)
    fndds.columns = [c.strip() for c in fndds.columns]
    fndds = fndds.rename(columns={
        "Food code": "fndds_code",
        "Main food description": "fndds_description",
        "WWEIA Category code": "wweia_code",
        "WWEIA Category description": "wweia_category",
    })
    fndds = fndds[["fndds_code", "fndds_description", "wweia_code", "wweia_category"]]
    fndds["fndds_code"] = fndds["fndds_code"].astype(str).str.strip()
    fndds = fndds.drop_duplicates(subset=["fndds_code"])
    print(f"  fndds rows: {len(fndds):,}", flush=True)

    print("joining gtin -> wweia_category", flush=True)
    gtin_wweia = fndds_tag.merge(fndds, on="fndds_code", how="inner")
    print(f"  gtin->wweia rows: {len(gtin_wweia):,}", flush=True)

    print("loading current MAPS_TO state from graph", flush=True)
    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)
    maps = conn.execute(
        """
        MATCH (p:Product)-[m:MAPS_TO]->(e:ESHACode)-[:IN_ESHA_CATEGORY]->(ec:ESHACategory)
        RETURN p.gtin_upc AS gtin_upc,
               e.code AS current_esha_code,
               e.description AS current_esha_description,
               ec.name AS current_esha_family,
               m.score AS score,
               m.assignment_source AS assignment_source,
               m.status AS status
        """
    ).get_as_df()
    print(f"  maps_to rows: {len(maps):,}", flush=True)

    df = maps.merge(gtin_wweia, on="gtin_upc", how="left")
    matched = df["wweia_category"].notna()
    print(f"  rows with wweia: {matched.sum():,}  ({matched.mean():.1%})", flush=True)

    print("learning dominant ESHA family per WWEIA category from trusted rows", flush=True)
    trusted = df[
        (df["assignment_source"] == "fallback_category_family")
        & (df["score"] >= 5)
        & df["wweia_category"].notna()
    ]
    print(f"  trusted rows: {len(trusted):,}", flush=True)

    by_wweia = trusted.groupby(["wweia_category", "current_esha_family"]).size().reset_index(name="n")
    totals = by_wweia.groupby("wweia_category")["n"].sum().rename("total")
    by_wweia = by_wweia.merge(totals, on="wweia_category")
    dominant = by_wweia.sort_values(["wweia_category", "n"], ascending=[True, False]).drop_duplicates(subset=["wweia_category"], keep="first")
    dominant["dominance_share"] = dominant["n"] / dominant["total"]
    dominant = dominant[dominant["total"] >= MIN_TRUSTED_SUPPORT]
    dominant = dominant[["wweia_category", "current_esha_family", "n", "total", "dominance_share"]].rename(
        columns={"current_esha_family": "dominant_esha_family", "n": "dominant_count", "total": "trusted_total"}
    )
    dominant.to_csv(OUT_WWEIA_MAP, index=False)
    print(f"  WWEIA categories with confident dominant family: {len(dominant):,}", flush=True)
    print(f"  wrote {OUT_WWEIA_MAP.relative_to(ROOT)}", flush=True)

    print("scoring every row against its WWEIA's dominant family", flush=True)
    scored = df.merge(dominant[["wweia_category", "dominant_esha_family", "dominance_share"]], on="wweia_category", how="left")

    has_truth = scored["dominant_esha_family"].notna()
    disagree_mask = has_truth & (scored["current_esha_family"] != scored["dominant_esha_family"])
    agree_mask = has_truth & (scored["current_esha_family"] == scored["dominant_esha_family"])
    print(f"  rows with WWEIA truth signal: {has_truth.sum():,}", flush=True)
    print(f"  agree with WWEIA dominant:    {agree_mask.sum():,}", flush=True)
    print(f"  disagree with WWEIA dominant: {disagree_mask.sum():,}", flush=True)

    disagreements = scored[disagree_mask].copy()
    disagreements["quarantine_reason"] = "wweia_disagreement"
    disagreements.to_csv(OUT_DISAGREE, index=False)
    print(f"  wrote {OUT_DISAGREE.relative_to(ROOT)}", flush=True)

    rescues = scored[agree_mask & (scored["status"] == "quarantined_low_score")].copy()
    rescues["rescue_reason"] = "wweia_agrees_low_score"
    rescues.to_csv(OUT_RESCUE, index=False)
    print(f"  rows to rescue: {len(rescues):,}", flush=True)
    print(f"  wrote {OUT_RESCUE.relative_to(ROOT)}", flush=True)

    print("applying disagreement quarantine to graph", flush=True)
    if len(disagreements) > 0:
        gtin_to_disagree = disagreements[["gtin_upc"]].drop_duplicates().reset_index(drop=True)
        gtin_to_disagree["__t"] = 1
        path = OUT_DIR / "_tmp_disagree_gtins.parquet"
        gtin_to_disagree.to_parquet(path, index=False)
        try:
            conn.execute("DROP TABLE _DisagreeGtin")
        except RuntimeError:
            pass
        conn.execute("CREATE NODE TABLE _DisagreeGtin(gtin_upc STRING, __t INT64, PRIMARY KEY(gtin_upc))")
        conn.execute(f"COPY _DisagreeGtin FROM '{path}'")
        conn.execute(
            """
            MATCH (d:_DisagreeGtin), (p:Product {gtin_upc: d.gtin_upc})-[m:MAPS_TO]->()
            WHERE m.status IS NULL
               OR m.status = 'unverified'
               OR m.status = 'quarantined_low_score'
            SET m.status = 'quarantined_wweia_disagreement'
            """
        )
        path.unlink(missing_ok=True)

    print("applying WWEIA rescues (un-quarantine low-score where WWEIA agrees)", flush=True)
    if len(rescues) > 0:
        gtin_to_rescue = rescues[["gtin_upc"]].drop_duplicates().reset_index(drop=True)
        path = OUT_DIR / "_tmp_rescue_gtins.parquet"
        gtin_to_rescue.to_parquet(path, index=False)
        try:
            conn.execute("DROP TABLE _RescueGtin")
        except RuntimeError:
            pass
        conn.execute("CREATE NODE TABLE _RescueGtin(gtin_upc STRING, PRIMARY KEY(gtin_upc))")
        conn.execute(f"COPY _RescueGtin FROM '{path}'")
        conn.execute(
            """
            MATCH (r:_RescueGtin), (p:Product {gtin_upc: r.gtin_upc})-[m:MAPS_TO]->()
            WHERE m.status = 'quarantined_low_score'
            SET m.status = 'wweia_validated_low_score'
            """
        )
        path.unlink(missing_ok=True)

    print("recomputing baseline", flush=True)
    def cnt(q: str) -> int:
        return int(conn.execute(q).get_as_df().iloc[0, 0])

    summary = {
        "total_maps_to":                       cnt("MATCH ()-[m:MAPS_TO]->() RETURN count(m)"),
        "quarantined_pass_a_cell_rot":          cnt("MATCH ()-[m:MAPS_TO]->() WHERE m.status = 'quarantined' RETURN count(m)"),
        "quarantined_pass_a2_low_score":        cnt("MATCH ()-[m:MAPS_TO]->() WHERE m.status = 'quarantined_low_score' RETURN count(m)"),
        "quarantined_pass_c_wweia_disagree":    cnt("MATCH ()-[m:MAPS_TO]->() WHERE m.status = 'quarantined_wweia_disagreement' RETURN count(m)"),
        "rescued_pass_c_wweia_validated":       cnt("MATCH ()-[m:MAPS_TO]->() WHERE m.status = 'wweia_validated_low_score' RETURN count(m)"),
    }
    summary["quarantined_total"] = (
        summary["quarantined_pass_a_cell_rot"]
        + summary["quarantined_pass_a2_low_score"]
        + summary["quarantined_pass_c_wweia_disagree"]
    )
    summary["trusted_remaining"] = summary["total_maps_to"] - summary["quarantined_total"]
    summary["quarantined_share"] = round(summary["quarantined_total"] / max(summary["total_maps_to"], 1), 4)
    OUT_BASELINE.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
