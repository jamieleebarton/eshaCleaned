from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from resolver_context import DEFAULT_ARTIFACTS
except ModuleNotFoundError:
    from implementation.resolver_context import DEFAULT_ARTIFACTS


READY_BUCKETS = {"nutrition_calculable", "nutrition_ready_no_buy", "intentional_skip"}
STATUS_FULL_READY = "full_calculator_ready"

FIELDS = [
    "recipe_id",
    "title",
    "ingredient_lines",
    "nutrition_ready_lines",
    "product_nutrition_calculable_lines",
    "no_buy_ready_lines",
    "ready_percent",
    "product_calc_percent",
    "status",
    "is_100_percent_calculatable",
    "top_blocker_bucket",
    "blocked_lines",
    "blocker_summary",
    "audit_source_fingerprint",
    "updated_at",
]

READY_ID_FIELDS = ["recipe_id", "title", "ingredient_lines", "status", "audit_source_fingerprint"]
ATTACK_ID_FIELDS = [
    "recipe_id",
    "title",
    "ingredient_lines",
    "ready_percent",
    "top_blocker_bucket",
    "blocked_lines",
    "blocker_summary",
    "audit_source_fingerprint",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator * 100.0, 2)


def audit_source_fingerprint(audit_db: Path, audit_json: Path) -> str:
    """Cheap invalidation fingerprint for the current audit source.

    Hashing the whole SQLite DB is unnecessary for this baseline. The audit JSON
    contains the aggregate metrics and the DB size/mtime changes whenever the
    per-recipe/per-line audit is rebuilt.
    """

    digest = hashlib.sha256()
    for path in [audit_db, audit_json]:
        stat = path.stat()
        digest.update(str(path.resolve()).encode("utf-8"))
        digest.update(str(stat.st_size).encode("utf-8"))
        digest.update(str(int(stat.st_mtime_ns)).encode("utf-8"))
        if path.suffix == ".json":
            digest.update(path.read_bytes())
    return digest.hexdigest()


def classify_recipe(
    ingredient_lines: int,
    nutrition_ready_lines: int,
    product_nutrition_calculable_lines: int,
    blocker_counts: Counter[str],
) -> tuple[str, float, float, str, int, str]:
    ready_percent = pct(nutrition_ready_lines, ingredient_lines)
    product_calc_percent = pct(product_nutrition_calculable_lines, ingredient_lines)
    blocked_lines = sum(blocker_counts.values())
    top_blocker_bucket = ""
    blocker_summary = ""
    if blocker_counts:
        top_blocker_bucket = blocker_counts.most_common(1)[0][0]
        blocker_summary = ";".join(f"{bucket}={count}" for bucket, count in blocker_counts.most_common(8))

    if ingredient_lines > 0 and nutrition_ready_lines >= ingredient_lines and blocked_lines == 0:
        status = STATUS_FULL_READY
    elif ready_percent >= 90:
        status = "partial_90_99"
    elif ready_percent >= 80:
        status = "partial_80_89"
    elif ready_percent >= 50:
        status = "partial_50_79"
    elif ingredient_lines > 0:
        status = "blocked_under_50"
    else:
        status = "source_has_no_ingredient_lines"

    return status, ready_percent, product_calc_percent, top_blocker_bucket, blocked_lines, blocker_summary


def load_blocker_counts(conn: sqlite3.Connection) -> dict[str, Counter[str]]:
    placeholders = ",".join("?" for _ in READY_BUCKETS)
    rows = conn.execute(
        f"""
        SELECT recipe_id, strict_bucket, COUNT(*) AS lines
        FROM ingredient_eval
        WHERE strict_bucket NOT IN ({placeholders})
        GROUP BY recipe_id, strict_bucket
        """,
        tuple(sorted(READY_BUCKETS)),
    )
    blockers: dict[str, Counter[str]] = defaultdict(Counter)
    for recipe_id, strict_bucket, lines in rows:
        blockers[str(recipe_id)][strict_bucket or "unknown"] += int(lines or 0)
    return blockers


def build_status_rows(audit_db: Path, audit_json: Path) -> tuple[list[dict[str, str]], dict[str, object]]:
    if not audit_db.exists():
        raise FileNotFoundError(f"Missing audit DB: {audit_db}")
    if not audit_json.exists():
        raise FileNotFoundError(f"Missing audit JSON: {audit_json}")

    source_fingerprint = audit_source_fingerprint(audit_db, audit_json)
    updated_at = now_utc()
    conn = sqlite3.connect(audit_db)
    blocker_counts = load_blocker_counts(conn)

    status_counts: Counter[str] = Counter()
    top_blocker_counts: Counter[str] = Counter()
    rows: list[dict[str, str]] = []
    score_rows = conn.execute(
        """
        SELECT
            recipe_id,
            title,
            ingredient_lines,
            nutrition_ready_lines,
            product_nutrition_calculable_lines,
            no_buy_ready_lines
        FROM recipe_scores
        ORDER BY CAST(recipe_id AS INTEGER), recipe_id
        """
    )
    for (
        recipe_id,
        title,
        ingredient_lines,
        nutrition_ready_lines,
        product_nutrition_calculable_lines,
        no_buy_ready_lines,
    ) in score_rows:
        recipe_id = str(recipe_id)
        ingredient_lines = int(ingredient_lines or 0)
        nutrition_ready_lines = int(nutrition_ready_lines or 0)
        product_nutrition_calculable_lines = int(product_nutrition_calculable_lines or 0)
        no_buy_ready_lines = int(no_buy_ready_lines or 0)
        blockers = blocker_counts.get(recipe_id, Counter())
        status, ready_percent, product_calc_percent, top_bucket, blocked_lines, blocker_summary = classify_recipe(
            ingredient_lines,
            nutrition_ready_lines,
            product_nutrition_calculable_lines,
            blockers,
        )
        status_counts[status] += 1
        if top_bucket:
            top_blocker_counts[top_bucket] += 1
        rows.append(
            {
                "recipe_id": recipe_id,
                "title": title or "",
                "ingredient_lines": str(ingredient_lines),
                "nutrition_ready_lines": str(nutrition_ready_lines),
                "product_nutrition_calculable_lines": str(product_nutrition_calculable_lines),
                "no_buy_ready_lines": str(no_buy_ready_lines),
                "ready_percent": f"{ready_percent:.2f}",
                "product_calc_percent": f"{product_calc_percent:.2f}",
                "status": status,
                "is_100_percent_calculatable": "1" if status == STATUS_FULL_READY else "0",
                "top_blocker_bucket": top_bucket,
                "blocked_lines": str(blocked_lines),
                "blocker_summary": blocker_summary,
                "audit_source_fingerprint": source_fingerprint,
                "updated_at": updated_at,
            }
        )
    conn.close()

    summary = json.loads(audit_json.read_text(encoding="utf-8"))
    summary.update(
        {
            "audit_source_fingerprint": source_fingerprint,
            "generated_at": updated_at,
            "recipe_status_counts": dict(sorted(status_counts.items())),
            "top_blocker_recipe_counts": dict(top_blocker_counts.most_common(25)),
            "ready_recipe_ids_csv": str(DEFAULT_ARTIFACTS.calculator_ready_recipe_ids_csv),
            "attack_recipe_ids_csv": str(DEFAULT_ARTIFACTS.calculator_attack_recipe_ids_csv),
        }
    )
    return rows, summary


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_status_artifacts(
    rows: list[dict[str, str]],
    summary: dict[str, object],
    status_csv: Path,
    ready_ids_csv: Path,
    attack_ids_csv: Path,
    summary_json: Path,
) -> None:
    write_csv(status_csv, FIELDS, rows)
    ready_rows = [
        {field: row[field] for field in READY_ID_FIELDS}
        for row in rows
        if row["status"] == STATUS_FULL_READY
    ]
    attack_rows = [
        {field: row[field] for field in ATTACK_ID_FIELDS}
        for row in rows
        if row["status"] != STATUS_FULL_READY
    ]
    write_csv(ready_ids_csv, READY_ID_FIELDS, ready_rows)
    write_csv(attack_ids_csv, ATTACK_ID_FIELDS, attack_rows)
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_state_db(state_db: Path, rows: list[dict[str, str]], summary: dict[str, object]) -> None:
    state_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state_db)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recipe_calculator_status (
            recipe_id TEXT PRIMARY KEY,
            title TEXT,
            ingredient_lines INTEGER NOT NULL,
            nutrition_ready_lines INTEGER NOT NULL,
            product_nutrition_calculable_lines INTEGER NOT NULL,
            no_buy_ready_lines INTEGER NOT NULL,
            ready_percent REAL NOT NULL,
            product_calc_percent REAL NOT NULL,
            status TEXT NOT NULL,
            is_100_percent_calculatable INTEGER NOT NULL,
            top_blocker_bucket TEXT,
            blocked_lines INTEGER NOT NULL,
            blocker_summary TEXT,
            audit_source_fingerprint TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS calculator_baseline_runs (
            audit_source_fingerprint TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            recipes INTEGER NOT NULL,
            full_calculator_ready_recipes INTEGER NOT NULL,
            attack_recipes INTEGER NOT NULL,
            summary_json TEXT NOT NULL
        )
        """
    )
    conn.execute("DELETE FROM recipe_calculator_status")
    conn.executemany(
        """
        INSERT INTO recipe_calculator_status (
            recipe_id,
            title,
            ingredient_lines,
            nutrition_ready_lines,
            product_nutrition_calculable_lines,
            no_buy_ready_lines,
            ready_percent,
            product_calc_percent,
            status,
            is_100_percent_calculatable,
            top_blocker_bucket,
            blocked_lines,
            blocker_summary,
            audit_source_fingerprint,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["recipe_id"],
                row["title"],
                int(row["ingredient_lines"]),
                int(row["nutrition_ready_lines"]),
                int(row["product_nutrition_calculable_lines"]),
                int(row["no_buy_ready_lines"]),
                float(row["ready_percent"]),
                float(row["product_calc_percent"]),
                row["status"],
                int(row["is_100_percent_calculatable"]),
                row["top_blocker_bucket"],
                int(row["blocked_lines"]),
                row["blocker_summary"],
                row["audit_source_fingerprint"],
                row["updated_at"],
            )
            for row in rows
        ],
    )
    ready_count = sum(1 for row in rows if row["status"] == STATUS_FULL_READY)
    conn.execute(
        """
        INSERT OR REPLACE INTO calculator_baseline_runs (
            audit_source_fingerprint,
            generated_at,
            recipes,
            full_calculator_ready_recipes,
            attack_recipes,
            summary_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(summary["audit_source_fingerprint"]),
            str(summary["generated_at"]),
            len(rows),
            ready_count,
            len(rows) - ready_count,
            json.dumps(summary, sort_keys=True),
        ),
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recipe_calculator_status_status ON recipe_calculator_status(status)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_recipe_calculator_status_top_blocker ON recipe_calculator_status(top_blocker_bucket)"
    )
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the canonical recipe calculator baseline and ready/attack recipe ID lists."
    )
    parser.add_argument("--audit-db", type=Path, default=DEFAULT_ARTIFACTS.recipe_qa_nutrition_audit_db)
    parser.add_argument("--audit-json", type=Path, default=DEFAULT_ARTIFACTS.recipe_qa_nutrition_audit_json)
    parser.add_argument("--state-db", type=Path, default=DEFAULT_ARTIFACTS.funnel_state_db)
    parser.add_argument("--status-csv", type=Path, default=DEFAULT_ARTIFACTS.calculator_recipe_status_csv)
    parser.add_argument("--ready-ids-csv", type=Path, default=DEFAULT_ARTIFACTS.calculator_ready_recipe_ids_csv)
    parser.add_argument("--attack-ids-csv", type=Path, default=DEFAULT_ARTIFACTS.calculator_attack_recipe_ids_csv)
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_ARTIFACTS.calculator_baseline_summary_json)
    args = parser.parse_args()

    rows, summary = build_status_rows(args.audit_db, args.audit_json)
    write_status_artifacts(rows, summary, args.status_csv, args.ready_ids_csv, args.attack_ids_csv, args.summary_json)
    write_state_db(args.state_db, rows, summary)

    ready_count = sum(1 for row in rows if row["status"] == STATUS_FULL_READY)
    print(f"wrote {args.status_csv} ({len(rows):,} recipes)")
    print(f"wrote {args.ready_ids_csv} ({ready_count:,} full-calculator-ready recipes)")
    print(f"wrote {args.attack_ids_csv} ({len(rows) - ready_count:,} attack recipes)")
    print(f"wrote {args.state_db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
