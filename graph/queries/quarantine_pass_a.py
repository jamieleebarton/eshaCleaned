"""Pass A: data-derived quarantine of structurally-impossible mappings.

A (ProductCategory, ESHACategory) cell whose mappings are 100% (or near-100%)
weak-fallback is the data telling us no legitimate signal ever put a product
into this cell. Every row in such a cell came through the broken path.

We don't write rules. We mine them from the data:

  IF (ProductCategory, ESHACategory) cell has
       fallback_share >= MIN_FALLBACK_SHARE  AND
       support_count  >= MIN_SUPPORT_COUNT
  THEN every (Product, ESHACode) mapping inside that cell is quarantined.

This:
  - Does NOT touch the main pipeline CSV.
  - Writes a quarantine CSV with full context for review.
  - Updates MAPS_TO.status = 'quarantined' in the graph (reversible: re-run ingest to reset).
  - Re-runs the headline baseline so we can measure the drop.
"""
from __future__ import annotations

import json
from pathlib import Path

import kuzu

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
OUT_DIR = ROOT / "graph" / "quarantine"
OUT_CSV = OUT_DIR / "needs_remap.csv"
OUT_CELLS = OUT_DIR / "quarantined_cells.csv"
OUT_BASELINE = OUT_DIR / "baseline_after_pass_a.json"

MIN_FALLBACK_SHARE = 0.90
MIN_SUPPORT_COUNT = 20


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)

    print("identifying structurally-impossible cells", flush=True)
    cells = conn.execute(
        f"""
        MATCH (pc:ProductCategory)-[oc:OBSERVED_COMPATIBILITY]->(ec:ESHACategory)
        WHERE oc.fallback_share >= {MIN_FALLBACK_SHARE}
          AND oc.support_count >= {MIN_SUPPORT_COUNT}
        RETURN pc.name AS product_category,
               ec.name AS esha_category,
               oc.support_count AS support_count,
               oc.weak_fallback_count AS weak_fallback_count,
               oc.fallback_share AS fallback_share
        ORDER BY oc.support_count DESC
        """
    ).get_as_df()
    print(f"  cells matching thresholds: {len(cells):,}", flush=True)
    if cells.empty:
        print("nothing to quarantine; exiting", flush=True)
        return
    cells.to_csv(OUT_CELLS, index=False)
    print(f"  wrote {OUT_CELLS.relative_to(ROOT)}", flush=True)

    cell_pairs = [
        (row["product_category"], row["esha_category"])
        for _, row in cells.iterrows()
    ]
    print(f"  total support across cells: {int(cells['support_count'].sum()):,}", flush=True)

    print("collecting rows to quarantine", flush=True)
    rows = conn.execute(
        f"""
        MATCH (pc:ProductCategory)-[oc:OBSERVED_COMPATIBILITY]->(ec:ESHACategory)
        WHERE oc.fallback_share >= {MIN_FALLBACK_SHARE}
          AND oc.support_count >= {MIN_SUPPORT_COUNT}
        WITH pc, ec
        MATCH (pc)<-[:IN_CATEGORY]-(p:Product)-[m:MAPS_TO]->(e:ESHACode)-[:IN_ESHA_CATEGORY]->(ec)
        OPTIONAL MATCH (p)-[:MADE_BY]->(b:Brand)
        OPTIONAL MATCH (b)-[:OWNED_BY]->(mfg:Manufacturer)
        RETURN p.gtin_upc AS gtin_upc,
               p.fdc_id AS fdc_id,
               p.description AS product_description,
               pc.name AS product_category,
               b.name AS brand,
               mfg.name AS manufacturer,
               e.code AS current_esha_code,
               e.description AS current_esha_description,
               ec.name AS current_esha_category,
               m.score AS score,
               m.assignment_source AS assignment_source,
               'cell_fallback_share>=0.90 & support>=20' AS quarantine_reason
        """
    ).get_as_df()
    print(f"  rows to quarantine: {len(rows):,}", flush=True)
    rows.to_csv(OUT_CSV, index=False)
    print(f"  wrote {OUT_CSV.relative_to(ROOT)}", flush=True)

    print("tagging MAPS_TO edges in graph (status='quarantined')", flush=True)
    res = conn.execute(
        f"""
        MATCH (pc:ProductCategory)-[oc:OBSERVED_COMPATIBILITY]->(ec:ESHACategory)
        WHERE oc.fallback_share >= {MIN_FALLBACK_SHARE}
          AND oc.support_count >= {MIN_SUPPORT_COUNT}
        WITH pc, ec
        MATCH (pc)<-[:IN_CATEGORY]-(p:Product)-[m:MAPS_TO]->(:ESHACode)-[:IN_ESHA_CATEGORY]->(ec)
        SET m.status = 'quarantined'
        RETURN count(m) AS tagged
        """
    ).get_as_df()
    print(f"  tagged {int(res.iloc[0,0]):,} edges", flush=True)

    print("recomputing baseline after Pass A", flush=True)
    total = int(conn.execute("MATCH ()-[m:MAPS_TO]->() RETURN count(m)").get_as_df().iloc[0, 0])
    quarantined = int(conn.execute(
        "MATCH ()-[m:MAPS_TO]->() WHERE m.status = 'quarantined' RETURN count(m)"
    ).get_as_df().iloc[0, 0])
    weak_remaining = int(conn.execute(
        """
        MATCH ()-[m:MAPS_TO]->()
        WHERE (m.assignment_source = 'fallback_family' OR m.assignment_source = 'fallback_global')
          AND m.status <> 'quarantined'
        RETURN count(m)
        """
    ).get_as_df().iloc[0, 0])
    weak_total = int(conn.execute(
        """
        MATCH ()-[m:MAPS_TO]->()
        WHERE m.assignment_source = 'fallback_family' OR m.assignment_source = 'fallback_global'
        RETURN count(m)
        """
    ).get_as_df().iloc[0, 0])
    summary = {
        "total_maps_to": total,
        "quarantined": quarantined,
        "weak_fallback_total_before_pass_a": weak_total,
        "weak_fallback_remaining_after_pass_a": weak_remaining,
        "weak_fallback_killed_by_pass_a": weak_total - weak_remaining,
        "weak_fallback_share_before": round(weak_total / max(total, 1), 4),
        "weak_fallback_share_after": round(weak_remaining / max(total, 1), 4),
    }
    OUT_BASELINE.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
