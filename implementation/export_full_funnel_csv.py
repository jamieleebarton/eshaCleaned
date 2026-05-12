from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DB = ROOT / "implementation" / "output" / "recipe_funnel.db"
DEFAULT_LINES_CSV = ROOT / "implementation" / "output" / "ingredient_lines_full.csv"
DEFAULT_REVIEW_CSV = ROOT / "implementation" / "output" / "ingredient_normalization_review_full.csv"

LEADING_MEASURE_RE = re.compile(
    r"""
    ^\s*
    (?:
        (?:
            (?:
                [\d./⁄¼½¾⅓⅔⅛⅜⅝⅞-]+
                |
                one|two|three|four|five|six|seven|eight|nine|ten|an\b|a\b
            )
            (?:\s+(?:to|-)\s*[\d./⁄¼½¾⅓⅔⅛⅜⅝⅞]+)?
            \s*
            (?:
                tsp|teaspoons?|tbsp|tablespoons?|cups?|c\b|oz|ounces?|lbs?|pounds?|
                grams?|g\b|kg|kilograms?|ml|milliliters?|l|liters?|pints?|quarts?|
                cans?|packages?|pkgs?|sticks?|cloves?|dash|pinch|sprigs?|bunches?|
                slices?|pieces?|large|medium|small
            )\.?
        )
        |
        (?:
            (?:
                [\d./⁄¼½¾⅓⅔⅛⅜⅝⅞]+
                |
                one|two|three|four|five|six|seven|eight|nine|ten|an\b|a\b
            )
            (?:\s+(?:to|-)\s*[\d./⁄¼½¾⅓⅔⅛⅜⅝⅞]+)?
            \s+
        )
    )
    \s*
    """,
    re.IGNORECASE | re.VERBOSE,
)

TRAILING_PREP_RE = re.compile(
    r"""
    (?:,\s*|\s+)
    (?:
        chopped|diced|minced|beaten|softened|melted|drained|rinsed|peeled|
        crushed|ground|to\ taste|as\ needed|divided|sliced|cubed
    )
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def simple_surface_candidate(line: str) -> str:
    text = (line or "").strip().lower()
    text = LEADING_MEASURE_RE.sub("", text, count=1).strip(" ,.-")
    changed = True
    while changed and text:
        new_text = TRAILING_PREP_RE.sub("", text).strip(" ,.-")
        changed = new_text != text
        text = new_text
    text = re.sub(r"\s+", " ", text).strip()
    return text


def top_examples(connection: sqlite3.Connection, normalized_line: str, limit: int = 3) -> list[dict[str, str]]:
    rows = connection.execute(
        """
        SELECT raw_line, title, source, source_recipe_id
        FROM ingredient_line_mentions
        WHERE normalized_line = ?
        LIMIT ?
        """,
        (normalized_line, limit),
    ).fetchall()
    return [
        {
            "raw_line": raw_line,
            "title": title,
            "source": source,
            "source_recipe_id": source_recipe_id,
        }
        for raw_line, title, source, source_recipe_id in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Export full-funnel ingredient line CSVs for normalization review.")
    parser.add_argument("--input-db", type=Path, default=DEFAULT_INPUT_DB)
    parser.add_argument("--lines-csv", type=Path, default=DEFAULT_LINES_CSV)
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV)
    args = parser.parse_args()

    connection = sqlite3.connect(args.input_db)
    try:
        rows = connection.execute(
            """
            SELECT normalized_line, recipe_count, example_raw_line
            FROM ingredient_lines
            ORDER BY recipe_count DESC, normalized_line ASC
            """
        ).fetchall()

        args.lines_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.lines_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["normalized_line", "recipe_count", "example_raw_line"],
            )
            writer.writeheader()
            for normalized_line, recipe_count, example_raw_line in rows:
                writer.writerow(
                    {
                        "normalized_line": normalized_line,
                        "recipe_count": recipe_count,
                        "example_raw_line": example_raw_line,
                    }
                )

        with args.review_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "normalized_line",
                    "recipe_count",
                    "example_raw_line",
                    "simple_surface_candidate",
                    "example_1_raw_line",
                    "example_1_title",
                    "example_1_source",
                    "example_2_raw_line",
                    "example_2_title",
                    "example_2_source",
                    "example_3_raw_line",
                    "example_3_title",
                    "example_3_source",
                    "review_notes",
                ],
            )
            writer.writeheader()
            for normalized_line, recipe_count, example_raw_line in rows:
                examples = top_examples(connection, normalized_line)
                payload = {
                    "normalized_line": normalized_line,
                    "recipe_count": recipe_count,
                    "example_raw_line": example_raw_line,
                    "simple_surface_candidate": simple_surface_candidate(normalized_line),
                    "review_notes": "",
                }
                for index in range(3):
                    example = examples[index] if index < len(examples) else {}
                    payload[f"example_{index + 1}_raw_line"] = example.get("raw_line", "")
                    payload[f"example_{index + 1}_title"] = example.get("title", "")
                    payload[f"example_{index + 1}_source"] = example.get("source", "")
                writer.writerow(payload)

        print(
            json.dumps(
                {
                    "lines_csv": str(args.lines_csv),
                    "review_csv": str(args.review_csv),
                    "row_count": len(rows),
                },
                indent=2,
            )
        )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
