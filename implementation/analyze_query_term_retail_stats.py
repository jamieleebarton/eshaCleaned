from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
INDEX_CSV = ROOT / "implementation" / "output" / "esha_code_query_pack_index.csv"
OUT_DIR = ROOT / "implementation" / "output"
TERM_STATS_CSV = OUT_DIR / "query_term_retail_stats.csv"
CARD_CANDIDATES_CSV = OUT_DIR / "query_term_drop_candidates.csv"
SUMMARY_MD = OUT_DIR / "query_term_retail_stats_summary.md"


def metric_from_lines(lines: list[str], label: str) -> str:
    prefix = f"- {label}:"
    for line in lines:
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def parse_markdown_table(lines: list[str], heading: str) -> list[dict[str, str]]:
    in_section = False
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    for line in lines:
        if line == heading:
            in_section = True
            header = None
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not header:
            header = cells
            continue
        if all(cell.startswith("---") or cell == "" for cell in cells):
            continue
        if header and len(cells) >= len(header):
            rows.append({header[idx]: cells[idx] for idx in range(len(header))})
    return rows


def parse_term_stats(raw: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for part in raw.split(" | "):
        part = part.strip()
        if not part:
            continue
        pieces = part.split(":")
        if len(pieces) != 4:
            continue
        term, bucket, retail_count, idf = pieces
        try:
            count = int(retail_count)
            idf_value = float(idf)
        except ValueError:
            continue
        out[term] = {"bucket": bucket, "retail_count": count, "idf": idf_value}
    return out


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def load_pack_index(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def parse_pack(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    hard_terms = [term.strip() for term in metric_from_lines(lines, "esha_required_terms_from_description").split("|") if term.strip()]
    selected_attempt = metric_from_lines(lines, "selected_query_attempt")
    query_term_stats = parse_term_stats(metric_from_lines(lines, "weighted_query_term_stats"))
    attempts = {
        row.get("attempt", ""): {
            "query": row.get("query", ""),
            "total_matches": safe_int(row.get("total_matches")),
            "error": row.get("error", ""),
        }
        for row in parse_markdown_table(lines, "## Query Attempts")
        if row.get("attempt")
    }
    return {
        "hard_terms": hard_terms,
        "selected_attempt": selected_attempt,
        "query_term_stats": query_term_stats,
        "attempts": attempts,
    }


def summarize_term_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    retail_counts = [row["retail_count"] for row in rows if row["retail_count"] is not None]
    idfs = [row["idf"] for row in rows if row["idf"] is not None]
    strict_zero = sum(1 for row in rows if row["strict_matches"] == 0)
    rescue_from_zero = sum(1 for row in rows if row["drop_rescued_from_zero"])
    selected_drop = sum(1 for row in rows if row["selected_drop"])
    families = Counter(row["family"] for row in rows if row["family"])
    buckets = Counter(row["bucket"] for row in rows if row["bucket"])
    rescue_gains = [row["drop_gain"] for row in rows if row["drop_rescued_from_zero"]]
    return {
        "cards_with_term": len(rows),
        "families": " | ".join(f"{family}:{count}" for family, count in families.most_common(8)),
        "bucket_modes": " | ".join(f"{bucket}:{count}" for bucket, count in buckets.most_common(4)),
        "median_retail_count": int(statistics.median(retail_counts)) if retail_counts else 0,
        "mean_retail_count": round(statistics.mean(retail_counts), 2) if retail_counts else 0.0,
        "max_retail_count": max(retail_counts) if retail_counts else 0,
        "mean_idf": round(statistics.mean(idfs), 2) if idfs else 0.0,
        "strict_zero_count": strict_zero,
        "drop_attempt_count": sum(1 for row in rows if row["drop_matches"] is not None),
        "drop_rescue_count": rescue_from_zero,
        "selected_drop_count": selected_drop,
        "avg_rescue_gain": round(statistics.mean(rescue_gains), 2) if rescue_gains else 0.0,
        "max_rescue_gain": max(rescue_gains) if rescue_gains else 0,
        "rescue_rate": round(rescue_from_zero / len(rows), 3) if rows else 0.0,
        "selected_drop_rate": round(selected_drop / len(rows), 3) if rows else 0.0,
    }


def candidate_action(row: dict[str, Any]) -> str:
    if row["drop_rescued_from_zero"] and row["retail_count"] <= 100:
        return "demote_from_query"
    if row["selected_drop"]:
        return "builder_already_drops"
    if row["strict_matches"] == 0 and row["drop_matches"] == 0:
        return "still_dead_after_drop"
    return ""


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_outputs(index_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    per_term_rows: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    card_candidates: list[dict[str, Any]] = []
    for row in index_rows:
        pack_path = Path(row["pack_path"])
        if not pack_path.exists():
            continue
        parsed = parse_pack(pack_path)
        attempts = parsed["attempts"]
        strict_matches = attempts.get("strict", {}).get("total_matches", 0)
        selected_attempt = parsed["selected_attempt"]
        for term in parsed["hard_terms"]:
            stat = parsed["query_term_stats"].get(term, {})
            drop_label = f"drop_one_core_term:{term}"
            drop_matches = attempts.get(drop_label, {}).get("total_matches")
            drop_gain = (drop_matches - strict_matches) if drop_matches is not None else 0
            entry = {
                "esha_code": row["esha_code"],
                "description": row["description"],
                "family": row["family"],
                "term": term,
                "bucket": stat.get("bucket", ""),
                "retail_count": stat.get("retail_count", 0),
                "idf": stat.get("idf", 0.0),
                "strict_matches": strict_matches,
                "drop_matches": drop_matches if drop_matches is not None else "",
                "drop_gain": drop_gain,
                "selected_attempt": selected_attempt,
                "selected_drop": selected_attempt == drop_label,
                "drop_rescued_from_zero": strict_matches == 0 and (drop_matches or 0) > 0,
            }
            per_term_rows[term].append(entry)
            action = candidate_action(entry)
            if action:
                card_candidates.append(
                    {
                        **entry,
                        "candidate_action": action,
                        "pack_path": row["pack_path"],
                    }
                )
    aggregate_rows: list[dict[str, Any]] = []
    for term, rows in per_term_rows.items():
        aggregate_rows.append(
            {
                "term": term,
                **summarize_term_rows(rows),
            }
        )
    aggregate_rows.sort(
        key=lambda row: (
            -safe_int(row["drop_rescue_count"]),
            -float(row["selected_drop_rate"]),
            safe_int(row["median_retail_count"]),
            row["term"],
        )
    )
    card_candidates.sort(
        key=lambda row: (
            {"demote_from_query": 0, "builder_already_drops": 1, "still_dead_after_drop": 2}.get(row["candidate_action"], 9),
            safe_int(row["retail_count"]),
            -safe_int(row["drop_gain"]),
            row["term"],
            safe_int(row["esha_code"]),
        )
    )
    return aggregate_rows, card_candidates


def write_summary(path: Path, term_rows: list[dict[str, Any]], card_rows: list[dict[str, Any]], limit: int) -> None:
    top_rescue = term_rows[:limit]
    top_candidates = card_rows[:limit]
    lines = [
        "# Query Term Retail Stats",
        "",
        f"- terms analyzed: {len(term_rows)}",
        f"- card/term candidate rows: {len(card_rows)}",
        "",
        "## Top Terms To Demote",
        "",
        "| term | cards | median retail count | strict zero | drop rescues | selected drop | families |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in top_rescue:
        lines.append(
            f"| {row['term']} | {row['cards_with_term']} | {row['median_retail_count']} | "
            f"{row['strict_zero_count']} | {row['drop_rescue_count']} | {row['selected_drop_count']} | {row['families']} |"
        )
    lines.extend(
        [
            "",
            "## Card-Level Candidates",
            "",
            "| action | esha_code | term | strict | drop | retail count | description |",
            "| --- | ---: | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in top_candidates:
        lines.append(
            f"| {row['candidate_action']} | {row['esha_code']} | {row['term']} | {row['strict_matches']} | "
            f"{row['drop_matches']} | {row['retail_count']} | {row['description']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze ESHA query terms against retail pack retrieval results")
    parser.add_argument("--index", type=Path, default=INDEX_CSV)
    parser.add_argument("--term-stats-out", type=Path, default=TERM_STATS_CSV)
    parser.add_argument("--card-candidates-out", type=Path, default=CARD_CANDIDATES_CSV)
    parser.add_argument("--summary-out", type=Path, default=SUMMARY_MD)
    parser.add_argument("--summary-limit", type=int, default=50)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    index_rows = load_pack_index(args.index)
    term_rows, card_rows = build_outputs(index_rows)
    write_csv(
        args.term_stats_out,
        [
            "term",
            "cards_with_term",
            "families",
            "bucket_modes",
            "median_retail_count",
            "mean_retail_count",
            "max_retail_count",
            "mean_idf",
            "strict_zero_count",
            "drop_attempt_count",
            "drop_rescue_count",
            "selected_drop_count",
            "avg_rescue_gain",
            "max_rescue_gain",
            "rescue_rate",
            "selected_drop_rate",
        ],
        term_rows,
    )
    write_csv(
        args.card_candidates_out,
        [
            "candidate_action",
            "esha_code",
            "description",
            "family",
            "term",
            "bucket",
            "retail_count",
            "idf",
            "strict_matches",
            "drop_matches",
            "drop_gain",
            "selected_attempt",
            "selected_drop",
            "drop_rescued_from_zero",
            "pack_path",
        ],
        card_rows,
    )
    write_summary(args.summary_out, term_rows, card_rows, args.summary_limit)
    print(
        f"wrote {len(term_rows)} term rows -> {args.term_stats_out}\n"
        f"wrote {len(card_rows)} card candidates -> {args.card_candidates_out}\n"
        f"wrote summary -> {args.summary_out}"
    )


if __name__ == "__main__":
    main()
