#!/usr/bin/env python3
"""Build taxonomy overrides for mutually exclusive shape nodes.

The first target is dry pasta by shape. Rows such as
Pantry > Pasta > Macaroni > Shells > Orzo stack sibling shapes into one path.
This builder collapses those rows back to Pantry > Pasta and puts the actual
shape into product_identity_fixed.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping

from taxonomy_finalizer import PATH_SEP, dedupe_segments, normalize_path, split_path


V2 = Path(__file__).resolve().parent
DEFAULT_AUDIT = V2 / "consensus_full_corpus_audit.csv"
DEFAULT_ACTIVE_OUT = V2 / "consensus_shape_taxonomy_overrides.csv"
DEFAULT_REVIEW_OUT = V2 / "consensus_shape_taxonomy_review.csv"
DEFAULT_REPORT_OUT = V2 / "consensus_shape_taxonomy_report.json"
DEFAULT_MD_OUT = V2 / "consensus_shape_taxonomy.md"

csv.field_size_limit(sys.maxsize)

FIELDS = [
    "fdc_id",
    "status",
    "owner",
    "title",
    "branded_food_category",
    "current_canonical_path",
    "current_retail_leaf_path",
    "category_path_fixed",
    "product_identity_fixed",
    "modifier",
    "new_canonical_path",
    "new_product_identity",
    "issue_family",
    "reason",
    "evidence",
]

REVIEW_FIELDS = [
    "fdc_id",
    "status",
    "owner",
    "title",
    "branded_food_category",
    "current_canonical_path",
    "current_retail_leaf_path",
    "issue_family",
    "likely_fix",
    "evidence",
]

PASTA_SHAPE_PATTERNS: list[tuple[str, str, tuple[str, ...]]] = [
    (r"\bacini\s+di\s+pepe\b", "Acini Di Pepe", ("acini di pepe",)),
    (r"\bangel\s+hair\b", "Angel Hair Pasta", ("angel hair",)),
    (r"\bbow[- ]?ties?\b|\bfarfalle\b", "Farfalle", ("bow tie", "bow-ties", "farfalle")),
    (r"\bcalamarata\b", "Calamarata", ("calamarata",)),
    (r"\bcampanelle\b", "Campanelle", ("campanelle",)),
    (r"\bcasarecce\b", "Casarecce", ("casarecce",)),
    (r"\bcavatappi\b", "Cavatappi", ("cavatappi",)),
    (r"\bcellentani\b", "Cellentani", ("cellentani",)),
    (r"\bconchiglie\b|\b(sea)?shells?\b|\blumachine\b|\blumaconi\b", "Shells", ("shells", "seashells", "conchiglie", "lumachine", "lumaconi")),
    (r"\bditalini\b", "Ditalini", ("ditalini",)),
    (r"\bditali\b", "Ditali", ("ditali",)),
    (r"\belbows?\b|\belbow\s+macaroni\b", "Elbow Macaroni", ("elbow", "elbows", "elbow macaroni")),
    (r"\bfettuccine\b|\bfettuccini\b", "Fettuccine", ("fettuccine", "fettuccini")),
    (r"\bfilini\b", "Filini", ("filini",)),
    (r"\blasagn[ae]\b", "Lasagna", ("lasagna", "lasagne")),
    (r"\blinguine\b|\blinguini\b", "Linguine", ("linguine", "linguini")),
    (r"\bmostaccioli\b", "Mostaccioli", ("mostaccioli",)),
    (r"\borecchiette\b", "Orecchiette", ("orecchiette",)),
    (r"\borzi\b|\borzo\b|\bsemi\s+di\s+orzo\b", "Orzo", ("orzo", "orzi", "semi di orzo")),
    (r"\bpenne\b", "Penne", ("penne",)),
    (r"\bradiatore\b", "Radiatore", ("radiatore",)),
    (r"\brigatoni\b", "Rigatoni", ("rigatoni",)),
    (r"\brotelle\b|\bwagon\s+wheels?\b", "Rotelle", ("rotelle", "wagon wheels", "wagon wheel")),
    (r"\brotini\b", "Rotini", ("rotini",)),
    (r"\bspaghetti\b", "Spaghetti", ("spaghetti",)),
    (r"\bstelline\b", "Stelline", ("stelline",)),
    (r"\btagliatelle\b", "Tagliatelle", ("tagliatelle",)),
    (r"\btortiglioni\b", "Tortiglioni", ("tortiglioni",)),
    (r"\btrottole\b", "Trottole", ("trottole",)),
    (r"\btubettini\b", "Tubettini", ("tubettini",)),
    (r"\bvermicelli\b", "Vermicelli", ("vermicelli",)),
    (r"\bziti\b", "Ziti", ("ziti",)),
    (r"\bzucchette\b", "Zucchette", ("zucchette",)),
]

IDENTITY_ALIASES = {
    "acini di pepe": {"acini", "acini di pepe"},
    "angel hair pasta": {"angel hair", "angel hair pasta"},
    "elbow macaroni": {"elbow", "elbows", "elbow macaroni", "large elbow"},
    "farfalle": {"farfalle", "bow tie", "bow ties", "bow-ties"},
    "rotelle": {"rotelle", "wagon wheel", "wagon wheels"},
    "shells": {"shell", "shells", "seashells", "conchiglie"},
}

GENERIC_MODIFIERS = {
    "plain",
    "pasta",
    "macaroni",
    "macaroni product",
    "dry",
    "enriched",
    "durum wheat",
    "durum wheat semolina",
    "semolina",
}
GENERIC_MODIFIER_WORDS = {
    word
    for modifier in GENERIC_MODIFIERS
    for word in normalize_path(modifier).lower().split()
}


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sort_fdc(row: Mapping[str, str]) -> tuple[int, int | str]:
    value = (row.get("fdc_id") or "").strip()
    return (0, int(value)) if value.isdigit() else (1, value)


def text_from_fields(row: Mapping[str, str], fields: Iterable[str]) -> str:
    return " ".join(
        row.get(field, "") or ""
        for field in fields
        if row.get(field, "") or ""
    ).lower()


def row_text(row: Mapping[str, str]) -> str:
    return text_from_fields(
        row,
        [
            "title",
            "product_identity_fixed",
            "canonical_label",
            "variant",
            "form_texture_cut",
            "modifier",
            "fndds_desc",
            "sr28_desc",
            "esha_desc",
            "matched_key",
        ],
    )


def primary_pasta_text(row: Mapping[str, str]) -> str:
    return text_from_fields(
        row,
        [
            "title",
            "product_identity_fixed",
            "canonical_label",
            "variant",
            "form_texture_cut",
            "modifier",
        ],
    )


def reference_pasta_text(row: Mapping[str, str]) -> str:
    return text_from_fields(
        row,
        [
            "fndds_desc",
            "sr28_desc",
            "esha_desc",
            "matched_key",
        ],
    )


def starts_path(path: str, prefix: str) -> bool:
    path = normalize_path(path)
    prefix = normalize_path(prefix)
    return path == prefix or path.startswith(prefix + PATH_SEP)


def is_pasta_shape_stack(row: Mapping[str, str]) -> bool:
    leaf = normalize_path(row.get("retail_leaf_path", "") or row.get("canonical_path", "") or "")
    canonical = normalize_path(row.get("canonical_path", "") or "")
    bad_prefixes = [
        "Pantry > Pasta > Macaroni > Shells",
        "Pantry > Pasta > Spaghetti > Linguine",
    ]
    return any(starts_path(leaf, prefix) or starts_path(canonical, prefix) for prefix in bad_prefixes)


def detect_pasta_identity(row: Mapping[str, str]) -> tuple[str, set[str]]:
    title = (row.get("title") or "").lower()
    for pattern, identity, aliases in PASTA_SHAPE_PATTERNS:
        if re.search(pattern, title, re.I):
            return identity, {alias.lower() for alias in aliases}
    current = (row.get("product_identity_fixed") or "").strip()
    if current and current.lower() not in {"pasta", "unknown product"}:
        return current, {current.lower()}
    return "Macaroni", {"macaroni"}


def normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def clean_modifier(row: Mapping[str, str], identity: str, aliases: set[str]) -> str:
    identity_aliases = {normalize_token(identity), *{normalize_token(alias) for alias in aliases}}
    identity_aliases.update(IDENTITY_ALIASES.get(identity.lower(), set()))
    identity_aliases = {normalize_token(value) for value in identity_aliases if value}

    kept: list[str] = []
    for part in split_path(row.get("modifier", "") or ""):
        cleaned = normalize_path(part)
        token = normalize_token(cleaned)
        if not token:
            continue
        if token in identity_aliases or token in GENERIC_MODIFIERS:
            continue
        if modifier_part_is_identity_or_generic(token, identity_aliases):
            continue
        if cleaned not in kept:
            kept.append(cleaned)
    return PATH_SEP.join(dedupe_segments(kept)) if kept else "<blank>"


def modifier_part_is_identity_or_generic(token: str, identity_aliases: set[str]) -> bool:
    for alias in identity_aliases:
        if not alias or alias not in token:
            continue
        remainder = token.replace(alias, " ")
        words = {word for word in remainder.split() if word}
        if not words or words <= GENERIC_MODIFIER_WORDS:
            return True
    return False


def build_override(row: Mapping[str, str]) -> dict[str, str] | None:
    if not is_pasta_shape_stack(row):
        return None
    identity, aliases = detect_pasta_identity(row)
    modifier = clean_modifier(row, identity, aliases)
    return {
        "fdc_id": row.get("fdc_id", "") or "",
        "status": "approved",
        "owner": "codex",
        "title": row.get("title", "") or "",
        "branded_food_category": row.get("branded_food_category", "") or "",
        "current_canonical_path": row.get("canonical_path", "") or "",
        "current_retail_leaf_path": row.get("retail_leaf_path", "") or "",
        "category_path_fixed": "Pantry > Pasta",
        "product_identity_fixed": identity,
        "modifier": modifier,
        "new_canonical_path": "Pantry > Pasta",
        "new_product_identity": identity,
        "issue_family": "pasta_shape_sibling_stack",
        "reason": "Pasta shapes are sibling identities; do not nest Macaroni > Shells > another shape.",
        "evidence": (
            f"title={row.get('title', '')} | current_path={row.get('retail_leaf_path', '')} | "
            f"detected_identity={identity}"
        ),
    }


def build(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]], Counter[str]]:
    active: list[dict[str, str]] = []
    review: list[dict[str, str]] = []
    stats: Counter[str] = Counter()
    for row in rows:
        override = build_override(row)
        if override is None:
            continue
        active.append(override)
        stats[override["issue_family"]] += 1
    active.sort(key=sort_fdc)
    return active, review, stats


def build_markdown(report: Mapping[str, object]) -> str:
    counts = report["issue_counts"]  # type: ignore[index]
    lines = [
        "# Consensus Shape Taxonomy Overrides",
        "",
        "Approved rows collapse mutually exclusive shape stacks into one canonical shape identity.",
        "",
        f"Approved overrides: `{report['approved_rows']:,}`",
        f"Review rows: `{report['review_rows']:,}`",
        "",
        "## Issue Counts",
        "",
    ]
    for key, value in sorted(counts.items()):  # type: ignore[union-attr]
        lines.append(f"- `{key}`: `{value:,}`")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--active-out", type=Path, default=DEFAULT_ACTIVE_OUT)
    parser.add_argument("--review-out", type=Path, default=DEFAULT_REVIEW_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MD_OUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    active, review, stats = build(load_rows(args.audit))
    write_csv(args.active_out, FIELDS, active)
    write_csv(args.review_out, REVIEW_FIELDS, review)
    report = {
        "sources": {"audit": str(args.audit)},
        "outputs": {
            "active": str(args.active_out),
            "review": str(args.review_out),
            "report": str(args.report_out),
            "markdown": str(args.markdown_out),
        },
        "approved_rows": len(active),
        "review_rows": len(review),
        "issue_counts": dict(stats.most_common()),
    }
    args.report_out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    args.markdown_out.write_text(build_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
