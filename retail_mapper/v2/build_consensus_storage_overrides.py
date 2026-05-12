#!/usr/bin/env python3
"""Build storage-state taxonomy overrides for fruit and vegetable shelves.

This layer fixes cases where the current path contradicts strong storage
evidence: frozen products sitting under canned shelves, canned fruit sitting
outside Pantry > Canned Fruit, and frozen fruit aliases that split the same
shopper shelf across multiple parents. Ambiguous water-in-ingredients cases go
to review instead of being auto-moved.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping

from taxonomy_finalizer import PATH_SEP, dedupe_segments, normalize_path, split_path


V2 = Path(__file__).resolve().parent
REPO = V2.parents[1]

DEFAULT_AUDIT = V2 / "consensus_full_corpus_audit.csv"
DEFAULT_PRODUCTS_DB = REPO / "data" / "master_products.db"
DEFAULT_ACTIVE_OUT = V2 / "consensus_storage_taxonomy_overrides.csv"
DEFAULT_REVIEW_OUT = V2 / "consensus_storage_taxonomy_review.csv"
DEFAULT_REPORT_OUT = V2 / "consensus_storage_taxonomy_report.json"
DEFAULT_MD_OUT = V2 / "consensus_storage_taxonomy.md"

csv.field_size_limit(sys.maxsize)

ACTIVE_FIELDS = [
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
    "processing_storage",
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
    "processing_storage",
    "issue_family",
    "severity",
    "likely_fix",
    "evidence",
    "notes",
]

FROZEN_RE = re.compile(r"\b(frozen|freezer|steamfresh|steam fresh)\b", re.I)
FREEZE_DRY_RE = re.compile(r"\b(freeze[- ]?dried|freeze[- ]?dry|freeze dried)\b", re.I)
CANNING_LIQUID_RE = re.compile(
    r"\b(in\s+(?:extra\s+light\s+|light\s+)?syrup|in\s+juice|in\s+water|"
    r"water\s*,\s*(?:sugar|salt|citric acid|calcium chloride)|"
    r"(?:light|heavy|extra light)\s+syrup|slightly sweetened water|"
    r"pear juice concentrate|white grape juice concentrate|brine)\b",
    re.I,
)

FRUIT_TERMS = {
    "apple",
    "apples",
    "apricot",
    "apricots",
    "banana",
    "bananas",
    "berries",
    "berry",
    "blackberries",
    "blueberries",
    "cherries",
    "cherry",
    "coconut",
    "cranberries",
    "cranberry",
    "dates",
    "dragon fruit",
    "figs",
    "fruit",
    "grapefruit",
    "grapes",
    "kiwi",
    "lemon",
    "lime",
    "mango",
    "melon",
    "orange",
    "oranges",
    "papaya",
    "peach",
    "peaches",
    "pear",
    "pears",
    "pineapple",
    "plum",
    "raspberries",
    "raspberry",
    "strawberries",
    "strawberry",
    "tropical fruit",
    "watermelon",
}

FROZEN_FRUIT_EXCLUSIONS = {
    "beverage",
    "drink",
    "fruit bar",
    "fruit bars",
    "fruit pop",
    "fruit pops",
    "ice cream",
    "milk",
    "parfait",
    "sherbet",
    "smoothie",
    "sorbet",
    "yogurt",
}
GENERIC_FROZEN_FRUIT_IDENTITIES = {
    "fruit",
    "fruit & fruit juice concentrates",
    "fruit and fruit juice concentrates",
}

CANNED_FRUIT_ACTIVE_PATH_EXCLUSIONS = (
    "Beverage",
    "Dairy",
    "Frozen",
    "Snack",
)


def sort_fdc(row: Mapping[str, str]) -> tuple[int, int | str]:
    value = (row.get("fdc_id") or "").strip()
    return (0, int(value)) if value.isdigit() else (1, value)


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def chunked(values: list[int], size: int = 900) -> Iterable[list[int]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def load_product_context(db_path: Path, fdc_ids: Iterable[str]) -> dict[str, dict[str, str]]:
    numeric_ids = sorted({int(value) for value in fdc_ids if str(value).isdigit()})
    if not numeric_ids or not db_path.exists():
        return {}

    context: dict[str, dict[str, str]] = {}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for batch in chunked(numeric_ids):
            placeholders = ",".join("?" for _ in batch)
            query = (
                "SELECT fdc_id, description, branded_food_category, ingredients, ingredients_clean "
                f"FROM products WHERE fdc_id IN ({placeholders})"
            )
            for record in conn.execute(query, batch):
                fdc = str(record["fdc_id"])
                candidate = {
                    "db_description": record["description"] or "",
                    "db_branded_food_category": record["branded_food_category"] or "",
                    "ingredients": record["ingredients"] or "",
                    "ingredients_clean": record["ingredients_clean"] or "",
                }
                previous = context.get(fdc)
                if previous is None or len(candidate["ingredients_clean"]) > len(previous.get("ingredients_clean", "")):
                    context[fdc] = candidate
    return context


def starts_path(path: str, prefix: str) -> bool:
    normalized = normalize_path(path)
    normalized_prefix = normalize_path(prefix)
    return normalized == normalized_prefix or normalized.startswith(normalized_prefix + PATH_SEP)


def compact_text(*values: str) -> str:
    return " ".join(value for value in values if value).lower()


def row_context(row: Mapping[str, str], product: Mapping[str, str]) -> str:
    return compact_text(
        row.get("title", "") or "",
        row.get("branded_food_category", "") or "",
        row.get("category_path_original", "") or "",
        row.get("category_path_fixed", "") or "",
        row.get("product_identity_fixed", "") or "",
        row.get("canonical_path", "") or "",
        row.get("retail_leaf_path", "") or "",
        row.get("processing_storage", "") or "",
        row.get("fndds_desc", "") or "",
        row.get("sr28_desc", "") or "",
        row.get("esha_desc", "") or "",
        row.get("matched_key", "") or "",
        product.get("db_branded_food_category", "") or "",
        product.get("ingredients", "") or "",
        product.get("ingredients_clean", "") or "",
    )


def frozen_storage_context(row: Mapping[str, str], product: Mapping[str, str]) -> str:
    """Primary storage evidence only, excluding stale reference descriptions."""
    return compact_text(
        row.get("title", "") or "",
        row.get("branded_food_category", "") or "",
        row.get("processing_storage", "") or "",
        product.get("db_description", "") or "",
        product.get("db_branded_food_category", "") or "",
    )


def branded_food_category(row: Mapping[str, str], product: Mapping[str, str]) -> str:
    return row.get("branded_food_category", "") or product.get("db_branded_food_category", "") or ""


def retail_leaf(row: Mapping[str, str]) -> str:
    return normalize_path(row.get("retail_leaf_path", "") or row.get("canonical_path", "") or "")


def has_frozen_evidence(row: Mapping[str, str], product: Mapping[str, str]) -> bool:
    return bool(FROZEN_RE.search(frozen_storage_context(row, product)))


def has_title_or_bfc_frozen_evidence(row: Mapping[str, str], product: Mapping[str, str]) -> bool:
    text = compact_text(
        row.get("title", "") or "",
        row.get("branded_food_category", "") or "",
        product.get("db_description", "") or "",
        product.get("db_branded_food_category", "") or "",
    )
    return bool(FROZEN_RE.search(text))


def has_canning_liquid_evidence(row: Mapping[str, str], product: Mapping[str, str]) -> bool:
    text = row_context(row, product)
    return bool(CANNING_LIQUID_RE.search(text))


def is_freeze_dried(row: Mapping[str, str], product: Mapping[str, str]) -> bool:
    return bool(FREEZE_DRY_RE.search(row_context(row, product)))


def contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def has_fruit_term(value: str) -> bool:
    normalized = value.lower()
    return contains_any(normalized, FRUIT_TERMS)


def clean_identity(identity: str) -> str:
    value = normalize_path(identity).strip()
    for prefix in ("Frozen ", "Canned "):
        if value.lower().startswith(prefix.lower()):
            value = value[len(prefix) :].strip()
    return value or "Unknown Product"


def clean_modifier(parts: list[str], row: Mapping[str, str], identity: str) -> str:
    source_parts = parts if parts else split_path(row.get("modifier", "") or "")
    filtered: list[str] = []
    identity_lower = identity.lower()
    for raw in source_parts:
        part = normalize_path(raw)
        lower = part.lower()
        if not part:
            continue
        if lower in {"frozen", "canned", "fruit", "vegetables", "plain"}:
            continue
        if lower == identity_lower:
            continue
        if identity_lower == "brussels sprouts and bacon bake" and lower.startswith("brussels sprouts with bacon"):
            continue
        if part not in filtered:
            filtered.append(part)
    return PATH_SEP.join(dedupe_segments(filtered))


def override_modifier(value: str) -> str:
    return value if value else "<blank>"


def evidence(row: Mapping[str, str], product: Mapping[str, str], reason: str) -> str:
    ingredients = product.get("ingredients_clean", "") or product.get("ingredients", "") or ""
    pieces = [
        reason,
        f"title={row.get('title', '')}",
        f"bfc={branded_food_category(row, product)}",
        f"path={retail_leaf(row)}",
        f"storage={row.get('processing_storage', '')}",
    ]
    if ingredients:
        pieces.append(f"ingredients={ingredients[:300]}")
    return " | ".join(piece for piece in pieces if piece)


def storage_tokens(value: str) -> list[str]:
    raw_parts = re.split(r"\s*(?:\||,|;)\s*", value or "")
    return [part.strip() for part in raw_parts if part.strip()]


def cleaned_canned_storage(value: str) -> str:
    parts = [part for part in storage_tokens(value) if part.lower() != "frozen"]
    if not any(part.lower() == "canned" for part in parts):
        parts.insert(0, "canned")
    return " | ".join(dict.fromkeys(parts))


def active_override(
    row: Mapping[str, str],
    product: Mapping[str, str],
    *,
    category: str,
    identity: str,
    modifier: str,
    storage: str,
    issue_family: str,
    reason: str,
) -> dict[str, str]:
    identity = clean_identity(identity)
    category = normalize_path(category)
    return {
        "fdc_id": (row.get("fdc_id") or "").strip(),
        "status": "approved",
        "owner": "codex",
        "title": row.get("title", "") or "",
        "branded_food_category": branded_food_category(row, product),
        "current_canonical_path": row.get("canonical_path", "") or "",
        "current_retail_leaf_path": retail_leaf(row),
        "category_path_fixed": category,
        "product_identity_fixed": identity,
        "modifier": override_modifier(modifier),
        "processing_storage": storage,
        "new_canonical_path": category,
        "new_product_identity": identity,
        "issue_family": issue_family,
        "reason": reason,
        "evidence": evidence(row, product, reason),
    }


def storage_facet_override(
    row: Mapping[str, str],
    product: Mapping[str, str],
    *,
    storage: str,
    issue_family: str,
    reason: str,
) -> dict[str, str]:
    return {
        "fdc_id": (row.get("fdc_id") or "").strip(),
        "status": "approved",
        "owner": "codex",
        "title": row.get("title", "") or "",
        "branded_food_category": branded_food_category(row, product),
        "current_canonical_path": row.get("canonical_path", "") or "",
        "current_retail_leaf_path": retail_leaf(row),
        "category_path_fixed": "",
        "product_identity_fixed": "",
        "modifier": "",
        "processing_storage": storage,
        "new_canonical_path": "",
        "new_product_identity": "",
        "issue_family": issue_family,
        "reason": reason,
        "evidence": evidence(row, product, reason),
    }


def review_row(
    row: Mapping[str, str],
    product: Mapping[str, str],
    *,
    issue_family: str,
    severity: str,
    likely_fix: str,
    notes: str,
) -> dict[str, str]:
    return {
        "fdc_id": (row.get("fdc_id") or "").strip(),
        "status": "review",
        "owner": "codex",
        "title": row.get("title", "") or "",
        "branded_food_category": branded_food_category(row, product),
        "current_canonical_path": row.get("canonical_path", "") or "",
        "current_retail_leaf_path": retail_leaf(row),
        "processing_storage": row.get("processing_storage", "") or "",
        "issue_family": issue_family,
        "severity": severity,
        "likely_fix": likely_fix,
        "evidence": evidence(row, product, notes),
        "notes": notes,
    }


def tail_after_prefix(path: str, prefix: str) -> list[str]:
    path_parts = split_path(path)
    prefix_parts = split_path(prefix)
    if path_parts[: len(prefix_parts)] != prefix_parts:
        return []
    return path_parts[len(prefix_parts) :]


def frozen_fruit_alias_override(row: Mapping[str, str], product: Mapping[str, str]) -> dict[str, str] | None:
    leaf = retail_leaf(row)
    if not starts_path(leaf, "Frozen") or starts_path(leaf, "Frozen > Frozen Fruit"):
        return None
    if starts_path(leaf, "Frozen > Vegetables"):
        return None

    parts = split_path(leaf)
    if len(parts) < 2:
        return None
    second = parts[1]
    context = frozen_storage_context(row, product)
    second_lower = second.lower()
    if contains_any(second_lower, FROZEN_FRUIT_EXCLUSIONS) or contains_any(context, {" fruit bar", " fruit pop"}):
        return None

    identity = ""
    modifier_parts: list[str] = []
    if second_lower == "fruit" and len(parts) > 2:
        identity = parts[2]
        modifier_parts = parts[3:]
        if identity.lower() in GENERIC_FROZEN_FRUIT_IDENTITIES and len(parts) > 3:
            identity = parts[3]
            modifier_parts = parts[4:]
    elif second_lower.startswith("frozen ") and has_fruit_term(second):
        identity = clean_identity(second)
        modifier_parts = parts[2:]
    elif "frozen fruit" in context and has_fruit_term(second):
        identity = second
        modifier_parts = parts[2:]
        if identity.lower() in GENERIC_FROZEN_FRUIT_IDENTITIES and len(parts) > 2:
            identity = parts[2]
            modifier_parts = parts[3:]
    else:
        return None

    modifier = clean_modifier(modifier_parts, row, identity)
    return active_override(
        row,
        product,
        category="Frozen > Frozen Fruit",
        identity=identity,
        modifier=modifier,
        storage="frozen",
        issue_family="frozen_fruit_parent_alias_normalization",
        reason="Normalize frozen fruit aliases under the single Frozen > Frozen Fruit shelf.",
    )


def frozen_under_canned_result(
    row: Mapping[str, str], product: Mapping[str, str]
) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    leaf = retail_leaf(row)
    is_canned_fruit_path = starts_path(leaf, "Pantry > Canned Fruit")
    is_canned_veg_path = starts_path(leaf, "Pantry > Canned Vegetables")
    if not is_canned_fruit_path and not is_canned_veg_path:
        return None, None
    if not has_frozen_evidence(row, product):
        return None, None
    bfc = branded_food_category(row, product).lower()
    bfc_says_canned = "canned fruit" in bfc or "canned vegetable" in bfc
    if bfc_says_canned and not has_title_or_bfc_frozen_evidence(row, product):
        return None, None
    if has_canning_liquid_evidence(row, product) and not has_title_or_bfc_frozen_evidence(row, product):
        return None, None

    if is_freeze_dried(row, product):
        return None, review_row(
            row,
            product,
            issue_family="freeze_dried_product_under_canned_shelf_review",
            severity="medium",
            likely_fix="Review whether this belongs under Snack/Pantry dried produce instead of a canned or frozen shelf.",
            notes="Freeze-dried evidence conflicts with the current canned shelf; do not auto-route to frozen.",
        )

    context = frozen_storage_context(row, product)
    if is_canned_fruit_path and contains_any(context, FROZEN_FRUIT_EXCLUSIONS):
        return None, review_row(
            row,
            product,
            issue_family="frozen_fruit_dessert_under_canned_shelf_review",
            severity="high",
            likely_fix="Review for Frozen > Frozen Desserts, Beverage, or Frozen > Frozen Fruit.",
            notes="Frozen evidence is strong, but product form looks like dessert/beverage rather than standalone fruit.",
        )
    if is_canned_veg_path and contains_any(context, {"burger", "burrito", "sandwich", "soup"}):
        return None, review_row(
            row,
            product,
            issue_family="frozen_prepared_food_under_canned_vegetables_review",
            severity="high",
            likely_fix="Review for Frozen meal/appetizer/vegetable side shelf.",
            notes="Frozen evidence is strong, but product form looks prepared rather than a standalone vegetable.",
        )

    prefix = "Pantry > Canned Fruit" if is_canned_fruit_path else "Pantry > Canned Vegetables"
    tail = tail_after_prefix(leaf, prefix)
    identity = tail[0] if tail else row.get("product_identity_fixed", "") or ("Fruit" if is_canned_fruit_path else "Vegetables")
    if is_canned_veg_path:
        identity = refine_frozen_vegetable_identity(row, identity)
    modifier = clean_modifier(tail[1:], row, identity)
    target_category = (
        "Frozen > Frozen Fruit"
        if is_canned_fruit_path
        else target_category_for_frozen_vegetable_path(row, product, identity)
    )
    issue_family = "frozen_product_under_canned_fruit_shelf" if is_canned_fruit_path else "frozen_product_under_canned_vegetable_shelf"
    if is_canned_veg_path and target_category != "Frozen > Vegetables":
        issue_family = "frozen_prepared_product_under_canned_vegetable_shelf"
    return active_override(
        row,
        product,
        category=target_category,
        identity=identity,
        modifier=modifier,
        storage="frozen",
        issue_family=issue_family,
        reason="Frozen evidence contradicts the current canned shelf.",
    ), None


def target_category_for_frozen_vegetable_path(
    row: Mapping[str, str], product: Mapping[str, str], identity: str
) -> str:
    text = compact_text(
        row.get("title", "") or "",
        branded_food_category(row, product),
        retail_leaf(row),
        identity,
    )
    if contains_any(text, {"dumpling", "appetizer", "tempura", "wings", "fries", "tots", "crispy"}):
        return "Frozen > Appetizers"
    if contains_any(text, {"pizza", "flatbread"}):
        return "Frozen > Pizza"
    if "bake" in text:
        return "Frozen > Prepared Sides"
    if contains_any(text, {"pasta", "mac and cheese", "alfredo", "penne", "rotini", "rigatoni"}):
        return "Frozen > Pasta"
    if contains_any(text, {"rice", "risotto", "couscous"}):
        return "Frozen > Rice"
    if contains_any(text, {"meal", "bowl", "entree", "stouffer"}):
        return "Frozen > Single Entrees"
    return "Frozen > Vegetables"


def refine_frozen_vegetable_identity(row: Mapping[str, str], identity: str) -> str:
    title = (row.get("title") or "").lower()
    if identity.lower() == "cheese" and "brussels sprouts" in title and "bacon" in title:
        return "Brussels Sprouts and Bacon Bake"
    return identity


def canned_fruit_identity(row: Mapping[str, str], product: Mapping[str, str]) -> str:
    text = row_context(row, product)
    title = (row.get("title") or "").lower()
    if "fruit cocktail" in text:
        return "Fruit Cocktail"
    if "citrus salad" in text or ("grapefruit" in text and "orange" in text):
        return "Citrus Salad"
    if "mandarin" in text or "orange" in title:
        return "Mandarin Oranges"
    if "grapefruit" in text:
        return "Grapefruit"
    if "peach" in text:
        return "Peaches"
    if "pear" in text:
        return "Pears"
    if "pineapple" in text:
        return "Pineapple"
    return clean_identity(row.get("product_identity_fixed", "") or "Canned Fruit")


def canned_fruit_outside_result(
    row: Mapping[str, str], product: Mapping[str, str]
) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    leaf = retail_leaf(row)
    if starts_path(leaf, "Pantry > Canned Fruit"):
        return None, None

    context = row_context(row, product)
    bfc = branded_food_category(row, product).lower()
    if "canned fruit" not in bfc and "canned fruit" not in context:
        return None, None

    if any(leaf == prefix or leaf.startswith(prefix + PATH_SEP) for prefix in CANNED_FRUIT_ACTIVE_PATH_EXCLUSIONS):
        return None, review_row(
            row,
            product,
            issue_family="canned_fruit_bfc_conflicts_with_current_department_review",
            severity="high",
            likely_fix="Review dirty BFC versus actual Beverage/Frozen/Dairy/Snack product.",
            notes="BFC/liquid evidence says canned fruit, but current department strongly suggests a different product.",
        )
    if not has_canning_liquid_evidence(row, product):
        return None, None
    if contains_any(context, {"frozen", "sherbet", "parfait", "fruit bar", "smoothie", "chia", "coconut milk"}):
        return None, review_row(
            row,
            product,
            issue_family="canned_fruit_dirty_bfc_or_composite_review",
            severity="high",
            likely_fix="Review for dirty BFC or composite meal/dessert instead of auto-moving to canned fruit.",
            notes="Canned-fruit evidence is mixed with dessert, beverage, frozen, or composite-product evidence.",
        )

    identity = canned_fruit_identity(row, product)
    modifier = clean_modifier([], row, identity)
    return active_override(
        row,
        product,
        category="Pantry > Canned Fruit",
        identity=identity,
        modifier=modifier,
        storage="canned",
        issue_family="canned_fruit_outside_canned_shelf",
        reason="Canned fruit BFC plus syrup/juice/water evidence supports Pantry > Canned Fruit.",
    ), None


def stale_frozen_storage_on_canned_shelf(
    row: Mapping[str, str], product: Mapping[str, str]
) -> dict[str, str] | None:
    leaf = retail_leaf(row)
    if not starts_path(leaf, "Pantry > Canned Fruit") and not starts_path(leaf, "Pantry > Canned Vegetables"):
        return None
    current_storage = row.get("processing_storage", "") or ""
    if "frozen" not in {part.lower() for part in storage_tokens(current_storage)}:
        return None
    bfc = branded_food_category(row, product).lower()
    if "canned fruit" not in bfc and "canned vegetable" not in bfc and not has_canning_liquid_evidence(row, product):
        return None
    if has_title_or_bfc_frozen_evidence(row, product):
        return None
    return storage_facet_override(
        row,
        product,
        storage=cleaned_canned_storage(current_storage),
        issue_family="canned_shelf_storage_facet_contains_stale_frozen",
        reason="Canned shelf/BFC evidence wins; remove stale frozen storage facet.",
    )


def produce_canning_liquid_review(row: Mapping[str, str], product: Mapping[str, str]) -> dict[str, str] | None:
    leaf = retail_leaf(row)
    if not starts_path(leaf, "Produce"):
        return None
    if has_frozen_evidence(row, product):
        return None
    if not has_canning_liquid_evidence(row, product):
        return None
    return review_row(
        row,
        product,
        issue_family="produce_path_likely_canned_or_shelf_stable_review",
        severity="medium",
        likely_fix="Review for Pantry > Canned Fruit/Vegetables, but keep Produce if this is fresh-cut produce with treatment liquid or a kit.",
        notes="Water/syrup/brine-style ingredients are an anti-fresh signal, but not safe enough for a blind move.",
    )


def build_storage_overrides(
    rows: list[dict[str, str]], product_context: Mapping[str, Mapping[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]], Counter[str]]:
    active: dict[str, dict[str, str]] = {}
    review: dict[str, dict[str, str]] = {}
    stats: Counter[str] = Counter()

    for row in rows:
        fdc = (row.get("fdc_id") or "").strip()
        product = product_context.get(fdc, {})

        override, review_candidate = frozen_under_canned_result(row, product)
        if override:
            active[fdc] = override
            stats[override["issue_family"]] += 1
            continue
        if review_candidate:
            review[fdc] = review_candidate
            stats[review_candidate["issue_family"]] += 1
            continue

        override = frozen_fruit_alias_override(row, product)
        if override:
            active[fdc] = override
            stats[override["issue_family"]] += 1
            continue

        override, review_candidate = canned_fruit_outside_result(row, product)
        if override:
            active[fdc] = override
            stats[override["issue_family"]] += 1
            continue
        if review_candidate:
            review[fdc] = review_candidate
            stats[review_candidate["issue_family"]] += 1
            continue

        override = stale_frozen_storage_on_canned_shelf(row, product)
        if override:
            active[fdc] = override
            stats[override["issue_family"]] += 1
            continue

        review_candidate = produce_canning_liquid_review(row, product)
        if review_candidate:
            review[fdc] = review_candidate
            stats[review_candidate["issue_family"]] += 1

    active_rows = sorted(active.values(), key=sort_fdc)
    review_rows = sorted(review.values(), key=sort_fdc)
    return active_rows, review_rows, stats


def build_markdown(report: Mapping[str, object]) -> str:
    counts = report["issue_counts"]  # type: ignore[index]
    lines = [
        "# Consensus Storage Taxonomy Overrides",
        "",
        "Approved rows are high-confidence storage contradictions. Review rows are intentionally inert.",
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
    parser.add_argument("--products-db", type=Path, default=DEFAULT_PRODUCTS_DB)
    parser.add_argument("--active-out", type=Path, default=DEFAULT_ACTIVE_OUT)
    parser.add_argument("--review-out", type=Path, default=DEFAULT_REVIEW_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MD_OUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_csv_rows(args.audit)
    product_context = load_product_context(args.products_db, (row.get("fdc_id", "") or "" for row in rows))
    active_rows, review_rows, stats = build_storage_overrides(rows, product_context)

    write_csv(args.active_out, ACTIVE_FIELDS, active_rows)
    write_csv(args.review_out, REVIEW_FIELDS, review_rows)

    report = {
        "sources": {
            "audit": str(args.audit),
            "products_db": str(args.products_db),
        },
        "outputs": {
            "active": str(args.active_out),
            "review": str(args.review_out),
            "report": str(args.report_out),
            "markdown": str(args.markdown_out),
        },
        "approved_rows": len(active_rows),
        "review_rows": len(review_rows),
        "issue_counts": dict(stats.most_common()),
    }
    args.report_out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    args.markdown_out.write_text(build_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
