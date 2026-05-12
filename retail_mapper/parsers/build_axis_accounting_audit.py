#!/usr/bin/env python3
"""Audit axis coverage and selection for the retail title parser."""
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, defaultdict

from title_parser import (
    AxisLexicon,
    Match,
    base_normalize,
    clean_duplicate_tail,
    repo_root,
    tokens_for,
)


SUMMARY_FIELDS = ["section", "key", "count", "share"]
TERM_FIELDS = [
    "axis",
    "value",
    "match_rows",
    "selected_rows",
    "unselected_rows",
    "example_fdc_ids",
    "example_titles",
]
TOKEN_FIELDS = ["token", "row_count", "example_fdc_ids", "example_titles"]
ROW_FIELDS = [
    "issue_type",
    "fdc_id",
    "gtin_upc",
    "product_description",
    "branded_food_category",
    "retail_type",
    "supercategory",
    "category_group",
    "category",
    "primary_food",
    "form",
    "flavor",
    "retail_leaf",
    "form_candidates",
    "flavor_candidates",
    "category_candidates",
    "ambiguous_terms",
    "unaccounted_tokens",
    "reason",
]

IGNORED_UNACCOUNTED = {
    "added",
    "all",
    "and",
    "artificial",
    "brand",
    "classic",
    "count",
    "each",
    "flavor",
    "flavored",
    "foods",
    "free",
    "fresh",
    "grade",
    "great",
    "made",
    "natural",
    "net",
    "new",
    "old",
    "original",
    "oz",
    "per",
    "premium",
    "quality",
    "real",
    "style",
    "the",
    "with",
}

GENERIC_FORMS = {"beverage", "drink", "mix", "blend", "mixed", "food"}
BEVERAGE_CONTEXT_FORMS = {"coffee", "tea", "latte", "espresso", "juice", "soda"}
SOLID_FORMS = {
    "bar",
    "bars",
    "bread",
    "breads",
    "brownie",
    "brownies",
    "cake",
    "cakes",
    "candy",
    "candies",
    "cereal",
    "cookie",
    "cookies",
    "crackers",
    "cupcake",
    "cupcakes",
    "gum",
    "mints",
    "muffin",
    "muffins",
    "pancake",
    "pancakes",
    "roll",
    "rolls",
}


def loads_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def selected_values(parsed: dict[str, str]) -> dict[str, set[str]]:
    flavor_values = {parsed.get("flavor", "")}
    flavor_values.update(loads_list(parsed.get("flavor_blend", "")))
    return {
        "CATEGORY": {parsed.get("primary_food", "").lower()},
        "FORM": {parsed.get("form", "").lower()},
        "FLAVOR_UNIVERSAL": {value.lower() for value in flavor_values},
        "CUT": {parsed.get("cut", "").lower()},
        "PREPARATION_STATE": {parsed.get("prep_state", "").lower()},
        "STORAGE": {parsed.get("storage", "").lower()},
        "DISH_TYPE": {parsed.get("dish_type", "").lower()},
        "COMBO_FORMAT": {parsed.get("pack_format", "").lower()},
    }


def match_spans(matches: dict[str, list[Match]]) -> set[int]:
    covered: set[int] = set()
    for axis, axis_matches in matches.items():
        if axis in {"STOPWORD", "BRAND_NOISE"}:
            continue
        for match in axis_matches:
            covered.update(range(match.start, match.end))
    return covered


def significant_unaccounted(tokens: list[str], matches: dict[str, list[Match]]) -> list[str]:
    covered = match_spans(matches)
    out = []
    for idx, token in enumerate(tokens):
        if idx in covered:
            continue
        if token in IGNORED_UNACCOUNTED:
            continue
        if len(token) <= 2 or token.isdigit():
            continue
        out.append(token)
    return out


def ambiguous_terms(matches: dict[str, list[Match]]) -> list[str]:
    by_span_value: dict[tuple[int, int, str], set[str]] = defaultdict(set)
    for axis, axis_matches in matches.items():
        if axis in {"STOPWORD", "BRAND_NOISE"}:
            continue
        for match in axis_matches:
            by_span_value[(match.start, match.end, match.value)].add(axis)
    terms = []
    for (_, _, value), axes in by_span_value.items():
        if len(axes) > 1:
            terms.append(f"{value}:{'|'.join(sorted(axes))}")
    return sorted(set(terms))


def add_examples(
    examples: dict[tuple[str, str], list[tuple[str, str]]],
    key: tuple[str, str],
    fdc_id: str,
    title: str,
    limit: int = 4,
) -> None:
    if len(examples[key]) < limit:
        examples[key].append((fdc_id, title))


def add_token_example(
    examples: dict[str, list[tuple[str, str]]],
    token: str,
    fdc_id: str,
    title: str,
    limit: int = 4,
) -> None:
    if len(examples[token]) < limit:
        examples[token].append((fdc_id, title))


def row_issue(
    parsed: dict[str, str],
    form_candidates: list[str],
    flavor_candidates: list[str],
    category_candidates: list[str],
    ambiguous: list[str],
    unaccounted: list[str],
) -> tuple[str, str] | None:
    form = parsed.get("form", "")
    primary = parsed.get("primary_food", "")
    category_group = parsed.get("category_group", "")
    retail_type = parsed.get("retail_type", "")

    if retail_type == "single" and not form:
        return "missing_selected_form", "Single item has no selected form."
    if retail_type == "single" and not primary and category_group not in {"Other", ""}:
        return "missing_selected_primary_food", "Single item has category routing but no primary_food."
    if form in GENERIC_FORMS and len(set(form_candidates) - {form}) >= 1:
        return "generic_form_with_specific_form_candidate", "Parser selected a generic form while other form candidates were present."
    if form in BEVERAGE_CONTEXT_FORMS and set(form_candidates) & SOLID_FORMS:
        return "beverage_context_form_over_solid_form", "Parser selected beverage/flavor context as form while solid product form was present."
    if len(unaccounted) >= 4:
        return "unaccounted_title_tokens", "Four or more significant title tokens were not covered by any non-stopword axis."
    if len(ambiguous) >= 4:
        return "many_axis_ambiguous_terms", "Several terms matched multiple axes; row needs role-selection review."
    return None


def main() -> int:
    root = repo_root()
    parser = argparse.ArgumentParser(description="Build form/flavor/category accounting audit CSVs.")
    parser.add_argument("--input", default=os.path.join(root, "product_esha_fixy.v6.csv"))
    parser.add_argument("--parsed", default=os.path.join(root, "codex_parsed_titles_audit.csv"))
    parser.add_argument("--summary", default=os.path.join(root, "codex_axis_accounting_summary.csv"))
    parser.add_argument("--terms", default=os.path.join(root, "codex_axis_term_accounting.csv"))
    parser.add_argument("--tokens", default=os.path.join(root, "codex_axis_unaccounted_tokens.csv"))
    parser.add_argument("--rows", default=os.path.join(root, "codex_axis_selection_review.csv"))
    args = parser.parse_args()

    lexicon = AxisLexicon(root)
    summary: Counter[tuple[str, str]] = Counter()
    term_matches: Counter[tuple[str, str]] = Counter()
    term_selected: Counter[tuple[str, str]] = Counter()
    term_examples: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    token_rows: Counter[str] = Counter()
    token_examples: dict[str, list[tuple[str, str]]] = defaultdict(list)

    with (
        open(args.input, newline="") as source_fh,
        open(args.parsed, newline="") as parsed_fh,
        open(args.rows, "w", newline="") as rows_fh,
    ):
        source_reader = csv.DictReader(source_fh)
        parsed_reader = csv.DictReader(parsed_fh)
        row_writer = csv.DictWriter(rows_fh, fieldnames=ROW_FIELDS)
        row_writer.writeheader()
        for source, parsed in zip(source_reader, parsed_reader):
            summary[("total", "rows")] += 1
            title = source.get("product_description", "")
            fdc_id = source.get("fdc_id", "")
            tokens = tokens_for(lexicon.normalize(clean_duplicate_tail(title)))
            matches = lexicon.all_matches(tokens)
            selected = selected_values(parsed)

            row_seen_terms: set[tuple[str, str]] = set()
            for axis, axis_matches in matches.items():
                if axis.startswith("__"):
                    continue
                for match in axis_matches:
                    key = (axis, match.value)
                    row_seen_terms.add(key)
                    add_examples(term_examples, key, fdc_id, title)
            for key in row_seen_terms:
                term_matches[key] += 1
                axis, value = key
                if value.lower() in selected.get(axis, set()):
                    term_selected[key] += 1

            unaccounted = significant_unaccounted(tokens, matches)
            for token in set(unaccounted):
                token_rows[token] += 1
                add_token_example(token_examples, token, fdc_id, title)

            form_candidates = sorted({match.value for match in matches.get("FORM", [])})
            flavor_candidates = sorted({match.value for match in matches.get("FLAVOR_UNIVERSAL", [])})
            category_candidates = sorted(
                {match.value for match in matches.get("CATEGORY", []) if match.value}
            )
            ambiguous = ambiguous_terms(matches)
            issue = row_issue(parsed, form_candidates, flavor_candidates, category_candidates, ambiguous, unaccounted)
            if issue:
                issue_type, reason = issue
                summary[("row_issue", issue_type)] += 1
                row_writer.writerow(
                    {
                        "issue_type": issue_type,
                        "fdc_id": fdc_id,
                        "gtin_upc": source.get("gtin_upc", ""),
                        "product_description": title,
                        "branded_food_category": source.get("branded_food_category", ""),
                        "retail_type": parsed.get("retail_type", ""),
                        "supercategory": parsed.get("supercategory", ""),
                        "category_group": parsed.get("category_group", ""),
                        "category": parsed.get("category", ""),
                        "primary_food": parsed.get("primary_food", ""),
                        "form": parsed.get("form", ""),
                        "flavor": parsed.get("flavor", ""),
                        "retail_leaf": parsed.get("retail_leaf", ""),
                        "form_candidates": json.dumps(form_candidates, separators=(",", ":")),
                        "flavor_candidates": json.dumps(flavor_candidates, separators=(",", ":")),
                        "category_candidates": json.dumps(category_candidates, separators=(",", ":")),
                        "ambiguous_terms": json.dumps(ambiguous, separators=(",", ":")),
                        "unaccounted_tokens": json.dumps(unaccounted, separators=(",", ":")),
                        "reason": reason,
                    }
                )

    with open(args.terms, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=TERM_FIELDS)
        writer.writeheader()
        for (axis, value), count in sorted(term_matches.items(), key=lambda item: (-item[1], item[0])):
            examples = term_examples[(axis, value)]
            selected_count = term_selected[(axis, value)]
            writer.writerow(
                {
                    "axis": axis,
                    "value": value,
                    "match_rows": count,
                    "selected_rows": selected_count,
                    "unselected_rows": count - selected_count,
                    "example_fdc_ids": " | ".join(fdc for fdc, _ in examples),
                    "example_titles": " || ".join(title for _, title in examples),
                }
            )

    with open(args.tokens, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=TOKEN_FIELDS)
        writer.writeheader()
        for token, count in token_rows.most_common():
            examples = token_examples[token]
            writer.writerow(
                {
                    "token": token,
                    "row_count": count,
                    "example_fdc_ids": " | ".join(fdc for fdc, _ in examples),
                    "example_titles": " || ".join(title for _, title in examples),
                }
            )

    total = summary[("total", "rows")]
    with open(args.summary, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for (section, key), count in sorted(summary.items(), key=lambda item: (item[0][0], -item[1], item[0][1])):
            denom = total if section in {"total", "row_issue"} else count
            writer.writerow(
                {
                    "section": section,
                    "key": key,
                    "count": count,
                    "share": f"{count / denom if denom else 0:.6f}",
                }
            )

    print(f"Wrote axis accounting audit to {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
