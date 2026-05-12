"""Pass A.2: score-cap quarantine.

Score is itself a structural signal. Normal matcher scores are 9-12+; rows
with score < SCORE_CAP got accepted by accident (e.g. the HERSHEY'S milk
chocolate bar mapped to ESHA 16454 'Almond Milk, chocolate' at score 0.75
via legacy_best_map).

This catches the bad-but-confident-looking-source rows that Pass A missed.
"""
from __future__ import annotations

import json
from pathlib import Path

import kuzu

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DB = ROOT / "graph" / "db" / "kuzu"
OUT_DIR = ROOT / "graph" / "quarantine"
OUT_CSV = OUT_DIR / "low_score_candidates.csv"
OUT_BASELINE = OUT_DIR / "baseline_after_pass_a2.json"

SCORE_CAP = 8.0


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db = kuzu.Database(str(GRAPH_DB))
    conn = kuzu.Connection(db)

    print(f"finding rows with score < {SCORE_CAP} (status not yet quarantined)", flush=True)
    rows = conn.execute(
        f"""
        MATCH (p:Product)-[m:MAPS_TO]->(e:ESHACode)
        WHERE m.score < {SCORE_CAP}
          AND (m.status IS NULL OR m.status <> 'quarantined')
        WITH p, m, e
        MATCH (e)-[:IN_ESHA_CATEGORY]->(ec:ESHACategory)
        OPTIONAL MATCH (p)-[:IN_CATEGORY]->(pc:ProductCategory)
        OPTIONAL MATCH (p)-[:MADE_BY]->(b:Brand)
        RETURN p.gtin_upc AS gtin_upc,
               p.fdc_id AS fdc_id,
               p.description AS product_description,
               pc.name AS product_category,
               b.name AS brand,
               e.code AS current_esha_code,
               e.description AS current_esha_description,
               ec.name AS current_esha_category,
               m.score AS score,
               m.assignment_source AS assignment_source,
               'score<{SCORE_CAP}' AS quarantine_reason
        ORDER BY m.score
        """
    ).get_as_df()
    print(f"  candidates: {len(rows):,}", flush=True)
    if rows.empty:
        print("nothing to quarantine; exiting", flush=True)
        return
    rows.to_csv(OUT_CSV, index=False)
    print(f"  wrote {OUT_CSV.relative_to(ROOT)}", flush=True)

    print("score histogram of candidates:", flush=True)
    print(rows["score"].describe().to_string(), flush=True)
    print("assignment_source breakdown:", flush=True)
    print(rows["assignment_source"].value_counts().to_string(), flush=True)

    print("tagging MAPS_TO edges in graph (status='quarantined_low_score')", flush=True)
    conn.execute(
        f"""
        MATCH (p:Product)-[m:MAPS_TO]->()
        WHERE m.score < {SCORE_CAP}
          AND (m.status IS NULL OR m.status <> 'quarantined')
        SET m.status = 'quarantined_low_score'
        """
    )

    total = int(conn.execute("MATCH ()-[m:MAPS_TO]->() RETURN count(m)").get_as_df().iloc[0, 0])
    quarantined_total = int(conn.execute(
        "MATCH ()-[m:MAPS_TO]->() WHERE m.status STARTS WITH 'quarantined' RETURN count(m)"
    ).get_as_df().iloc[0, 0])
    quarantined_low_score = int(conn.execute(
        "MATCH ()-[m:MAPS_TO]->() WHERE m.status = 'quarantined_low_score' RETURN count(m)"
    ).get_as_df().iloc[0, 0])
    quarantined_pass_a = int(conn.execute(
        "MATCH ()-[m:MAPS_TO]->() WHERE m.status = 'quarantined' RETURN count(m)"
    ).get_as_df().iloc[0, 0])
    summary = {
        "score_cap": SCORE_CAP,
        "total_maps_to": total,
        "quarantined_pass_a_cell_rot": quarantined_pass_a,
        "quarantined_pass_a2_low_score": quarantined_low_score,
        "quarantined_total_after_a2": quarantined_total,
        "trusted_remaining": total - quarantined_total,
        "quarantined_share": round(quarantined_total / max(total, 1), 4),
    }
    OUT_BASELINE.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
