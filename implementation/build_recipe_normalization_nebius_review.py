#!/usr/bin/env python3
"""Build human-review tables from Nebius recipe-normalization output."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / "implementation" / "output" / "recipe_normalization_nebius_candidate.jsonl"
DEFAULT_FINDINGS = ROOT / "implementation" / "output" / "recipe_normalization_nebius_candidate_findings.jsonl"
DEFAULT_CSV = ROOT / "implementation" / "output" / "recipe_normalization_nebius_rewrite_review.csv"
DEFAULT_MD = ROOT / "implementation" / "output" / "recipe_normalization_nebius_rewrite_review.md"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def short(value: Any, limit: int = 140) -> str:
    value_text = text(value).replace("\n", " ").strip()
    if len(value_text) <= limit:
        return value_text
    return value_text[: limit - 3].rstrip() + "..."


def finding_map(findings: list[dict[str, Any]]) -> dict[tuple[str, str], list[str]]:
    out: dict[tuple[str, str], list[str]] = {}
    for finding in findings:
        key = (text(finding.get("recipe_id")), text(finding.get("line_index")))
        label = f"{finding.get('severity')}:{finding.get('code')}"
        out.setdefault(key, []).append(label)
    return out


def rows_from_candidate(candidate_rows: list[dict[str, Any]], findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    findings_by_line = finding_map(findings)
    out: list[dict[str, str]] = []
    for recipe in candidate_rows:
        recipe_id = text(recipe.get("recipe_id"))
        title = text(recipe.get("title"))
        ingredients = recipe.get("ingredients") if isinstance(recipe.get("ingredients"), list) else []
        for ingredient in ingredients:
            if not isinstance(ingredient, dict):
                continue
            normalized = ingredient.get("normalized") if isinstance(ingredient.get("normalized"), dict) else {}
            matchability = ingredient.get("matchability") if isinstance(ingredient.get("matchability"), dict) else {}
            consumption = ingredient.get("consumption") if isinstance(ingredient.get("consumption"), dict) else {}
            line_index = text(ingredient.get("line_index"))
            line_findings = findings_by_line.get((recipe_id, line_index), [])
            out.append(
                {
                    "recipe_id": recipe_id,
                    "title": title,
                    "line_index": line_index,
                    "original_display": text(ingredient.get("original_display")),
                    "original_item": text(ingredient.get("original_item")),
                    "rewritten_ingredient": text(ingredient.get("rewritten_ingredient")),
                    "machine_name": text(normalized.get("machine_name")),
                    "product_identity": text(normalized.get("product_identity")),
                    "section": text(ingredient.get("section")),
                    "role": text(ingredient.get("role")),
                    "match_status": text(matchability.get("status")),
                    "consumption_policy": text(consumption.get("consumption_policy")),
                    "calculation_status": text(consumption.get("calculation_status")),
                    "match_blockers": text(matchability.get("match_blockers")),
                    "consumption_blockers": text(consumption.get("blockers")),
                    "findings": "; ".join(line_findings),
                }
            )
    return out


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "recipe_id",
        "title",
        "line_index",
        "original_display",
        "original_item",
        "rewritten_ingredient",
        "machine_name",
        "product_identity",
        "section",
        "role",
        "match_status",
        "consumption_policy",
        "calculation_status",
        "match_blockers",
        "consumption_blockers",
        "findings",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def md_escape(value: str) -> str:
    return value.replace("|", "\\|")


def write_markdown(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("# Nebius Recipe Ingredient Rewrite Review\n\n")
        f.write("| Recipe | Line | Original | Rewritten | Role | Match | Calc | Findings |\n")
        f.write("|---|---:|---|---|---|---|---|---|\n")
        for row in rows:
            f.write(
                "| {recipe} | {line} | {original} | {rewritten} | {role} | {match} | {calc} | {findings} |\n".format(
                    recipe=md_escape(short(row["recipe_id"], 20)),
                    line=md_escape(short(row["line_index"], 8)),
                    original=md_escape(short(row["original_display"])),
                    rewritten=md_escape(short(row["rewritten_ingredient"])),
                    role=md_escape(short(row["role"], 32)),
                    match=md_escape(short(row["match_status"], 32)),
                    calc=md_escape(short(row["calculation_status"], 32)),
                    findings=md_escape(short(row["findings"], 80)),
                )
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--findings", type=Path, default=DEFAULT_FINDINGS)
    parser.add_argument("--csv-out", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    rows = rows_from_candidate(load_jsonl(args.candidate), load_jsonl(args.findings))
    write_csv(args.csv_out, rows)
    write_markdown(args.md_out, rows)
    print(json.dumps({"rows": len(rows), "csv": str(args.csv_out), "markdown": str(args.md_out)}, indent=2))


if __name__ == "__main__":
    main()
