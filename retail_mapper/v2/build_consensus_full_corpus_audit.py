#!/usr/bin/env python3
"""Build a best-of-both consensus taxonomy audit CSV.

The consensus starts from full_corpus_audit.csv because that file is unique by
fdc_id. It then adopts a small set of Codex improvements that were verified in
the Codex-vs-full comparison:

* Restore shopper-friendly Pantry subfamily parents.
* Route title-level salads out of dirty pickle/relish BFC rows.
* Route actual churro products to Bakery > Pastry > Churros.

It deliberately keeps the full/Claude side for storage and source-category
cases where that side is better:

* Frozen vegetables/fruits stay in Frozen.
* Pasta Dinners stay in Meal > Pasta Dishes.
* Nut & Seed Butters stay in Pantry > Nut Butters.
* Canned Vegetables stay in Pantry.
* True cookies stay in Bakery > Cookies.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Mapping

from taxonomy_finalizer import path_defects


V2 = Path(__file__).resolve().parent
FULL = V2 / "full_corpus_audit.csv"
CODEX = V2 / "codex_full_corpus_audit.csv"
OUT = V2 / "consensus_full_corpus_audit.csv"
DECISIONS = V2 / "consensus_full_corpus_audit_decisions.csv"
REPORT = V2 / "consensus_full_corpus_audit_report.json"
MD = V2 / "consensus_full_corpus_audit.md"

PATH_SEP = " > "

csv.field_size_limit(sys.maxsize)


TAXONOMY_COLUMNS = [
    "retail_type",
    "category_path_fixed",
    "path_fixer_applied",
    "product_identity_fixed",
    "fixer_applied",
    "canonical_path",
    "canonical_label",
    "variant",
    "flavor",
    "form_texture_cut",
    "processing_storage",
    "claims",
    "components_count",
    "components",
    "confidence",
    "mint_required",
    "review_flags",
    "rationale",
    "modifier",
    "retail_leaf_path",
]

VALID_DEPARTMENTS = {
    "Baby & Toddler",
    "Bakery",
    "Beverage",
    "Dairy",
    "Frozen",
    "Meal",
    "Meat & Seafood",
    "Other",
    "Pantry",
    "Produce",
    "Snack",
    "Sports & Wellness",
}


def split_path(path: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*>\s*", path or "") if part.strip()]


def path_starts(path: str, *prefixes: str) -> bool:
    return any((path or "").startswith(prefix) for prefix in prefixes)


def token_key(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    stemmed: list[str] = []
    for word in words:
        if len(word) > 3 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
            word = word[:-1]
        stemmed.append(word)
    return " ".join(stemmed)


def has_title(row: Mapping[str, str], pattern: str) -> bool:
    return bool(re.search(pattern, row.get("title", "") or "", re.I))


def bfc(row: Mapping[str, str]) -> str:
    return (row.get("branded_food_category") or "").strip()


def row_quality_score(row: Mapping[str, str]) -> tuple[int, int, int, int]:
    return (
        1 if (row.get("retail_leaf_path") or "").strip() else 0,
        1 if (row.get("canonical_path") or "").strip() else 0,
        1 if not path_defects(row) else 0,
        sum(1 for value in row.values() if (value or "").strip()),
    )


def load_unique_by_fdc(path: Path) -> tuple[dict[str, dict[str, str]], Counter[str], list[str]]:
    rows: dict[str, dict[str, str]] = {}
    counts: Counter[str] = Counter()
    fieldnames: list[str] = []
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            fdc = (row.get("fdc_id") or "").strip()
            counts[fdc] += 1
            if fdc not in rows or row_quality_score(row) > row_quality_score(rows[fdc]):
                rows[fdc] = row
    return rows, counts, fieldnames


def full_side_reason(full: Mapping[str, str], codex: Mapping[str, str] | None) -> str:
    if codex is None:
        return "full_only_row"

    full_path = full.get("canonical_path", "") or ""
    codex_path = codex.get("canonical_path", "") or ""
    full_leaf = full.get("retail_leaf_path", "") or ""
    codex_leaf = codex.get("retail_leaf_path", "") or ""
    category = bfc(full)

    if category == "Frozen Vegetables" and path_starts(full_path, "Frozen > Vegetables"):
        return "keep_full:frozen_vegetables_storage_department"
    if "Frozen Fruit" in category and path_starts(full_path, "Frozen"):
        return "keep_full:frozen_fruit_storage_department"
    if category == "Pasta Dinners" and path_starts(full_path, "Meal > Pasta Dishes"):
        return "keep_full:pasta_dinners_are_meal_pasta_dishes"
    if (
        category == "Nut & Seed Butters"
        and path_starts(full_path, "Pantry > Nut Butters")
        and path_starts(codex_path, "Dairy > Butter")
    ):
        return "keep_full:nut_seed_butters_not_dairy_butter"
    if (
        category == "Canned Vegetables"
        and path_starts(full_path, "Pantry")
        and path_starts(codex_path, "Produce > Vegetables")
    ):
        return "keep_full:canned_vegetables_stay_pantry"
    if path_starts(full_leaf, "Bakery > Cookies") and path_starts(codex_leaf, "Snack > Cookies"):
        return "keep_full:true_cookies_stay_bakery"
    return ""


def codex_side_reason(full: Mapping[str, str], codex: Mapping[str, str] | None) -> str:
    if codex is None:
        return ""

    full_path = full.get("canonical_path", "") or ""
    codex_path = codex.get("canonical_path", "") or ""
    full_leaf = full.get("retail_leaf_path", "") or ""
    codex_leaf = codex.get("retail_leaf_path", "") or ""

    if path_starts(full_path, "Pantry >") and path_starts(codex_path, "Pantry > Sauces & Salsas"):
        return "take_codex:restore_sauces_salsas_parent"
    if path_starts(full_path, "Pantry >") and path_starts(codex_path, "Pantry > Spices & Seasonings"):
        return "take_codex:restore_spices_seasonings_parent"
    if path_starts(full_path, "Pantry >") and path_starts(codex_path, "Pantry > Dips & Spreads"):
        return "take_codex:restore_dips_spreads_parent"
    if path_starts(full_path, "Pantry >") and path_starts(codex_path, "Pantry > Broth & Stock"):
        return "take_codex:restore_broth_stock_parent"
    if (
        bfc(full) == "Pickles, Olives, Peppers & Relishes"
        and has_title(full, r"\bsalad\b")
        and path_starts(codex_path, "Meal > Salads")
    ):
        return "take_codex:title_level_salad_over_dirty_pickle_bfc"
    if (
        path_starts(full_leaf, "Bakery > Cookies > Churros")
        and path_starts(codex_leaf, "Bakery > Pastry > Churros")
        and has_title(full, r"\bchurros?\b")
    ):
        return "take_codex:actual_churro_product_not_cookie"
    return ""


def copy_taxonomy(target: dict[str, str], source: Mapping[str, str]) -> None:
    for column in TAXONOMY_COLUMNS:
        if column in source:
            target[column] = source.get(column, "") or ""


def replace_prefix(path: str, old_prefix: str, new_prefix: str) -> str:
    if path == old_prefix:
        return new_prefix
    if path.startswith(old_prefix + PATH_SEP):
        return new_prefix + path[len(old_prefix):]
    return path


def clean_modifier_tail(canonical_path: str, tail: list[str]) -> list[str]:
    canonical_keys = {token_key(part) for part in split_path(canonical_path)}
    cleaned = [part for part in tail if token_key(part) and token_key(part) not in canonical_keys]
    if len(cleaned) > 1:
        cleaned = [part for part in cleaned if token_key(part) != "plain"]
    return cleaned


def clean_row_modifier(row: dict[str, str]) -> None:
    canonical = row.get("canonical_path", "") or ""
    leaf = row.get("retail_leaf_path", "") or ""
    if not canonical or not leaf.startswith(canonical + PATH_SEP):
        return
    tail = split_path(leaf[len(canonical + PATH_SEP):])
    cleaned = clean_modifier_tail(canonical, tail)
    row["modifier"] = PATH_SEP.join(cleaned)
    row["retail_leaf_path"] = PATH_SEP.join([canonical] + cleaned) if cleaned else canonical


def force_route_prefix(row: dict[str, str], old_prefix: str, new_prefix: str) -> None:
    row["category_path_fixed"] = new_prefix
    row["canonical_path"] = replace_prefix(row.get("canonical_path", "") or "", old_prefix, new_prefix)
    row["retail_leaf_path"] = replace_prefix(row.get("retail_leaf_path", "") or "", old_prefix, new_prefix)
    parts = split_path(row.get("canonical_path", "") or "")
    category_parts = split_path(new_prefix)
    if len(parts) > len(category_parts):
        row["product_identity_fixed"] = parts[len(category_parts)]
    if row.get("retail_leaf_path") == row.get("canonical_path"):
        row["modifier"] = ""
    elif (row.get("canonical_path") or "") and (row.get("retail_leaf_path") or "").startswith(row["canonical_path"] + PATH_SEP):
        row["modifier"] = row["retail_leaf_path"][len(row["canonical_path"] + PATH_SEP):]
    clean_row_modifier(row)


def identity_from_title(row: Mapping[str, str]) -> str:
    title = row.get("title", "") or ""
    identity_patterns = [
        (r"\bgreen\s+beans?\b", "Green Beans"),
        (r"\bsweet\s+peas?\b|\bgarden\s+peas?\b|\bpeas?\b", "Peas"),
        (r"\bspinach\b", "Spinach"),
        (r"\bcollard\s+greens?\b", "Collard Greens"),
        (r"\bmustard\s+greens?\b", "Mustard Greens"),
        (r"\bkale\s+greens?\b|\bkale\b", "Kale Greens"),
        (r"\bpotatoes?\b", "Potatoes"),
        (r"\bcorn\b", "Corn"),
        (r"\bbeets?\b", "Beets"),
        (r"\bcarrots?\b", "Carrots"),
        (r"\bokra\b", "Okra"),
        (r"\bsquash\b", "Squash"),
        (r"\byuca\b|\bcassava\b", "Yuca"),
        (r"\bonions?\b", "Onions"),
        (r"\bcabbage\b", "Cabbage"),
        (r"\bsuccotash\b", "Succotash"),
        (r"\bvegetable\s+blend\b|\bmixed\s+vegetables?\b", "Vegetable Blend"),
    ]
    for pattern, identity in identity_patterns:
        if re.search(pattern, title, re.I):
            return identity
    return ""


def force_to_category(row: dict[str, str], new_category: str, *, identity_hint: str = "") -> None:
    source_path = row.get("retail_leaf_path", "") or row.get("canonical_path", "") or ""
    source_parts = split_path(source_path)
    tail = source_parts[2:] if len(source_parts) >= 3 else []
    identity = identity_hint or (tail[0] if tail else row.get("product_identity_fixed", ""))
    identity = identity.strip()
    row["category_path_fixed"] = new_category
    if identity:
        row["product_identity_fixed"] = identity
        row["canonical_path"] = new_category if token_key(identity) in {token_key(part) for part in split_path(new_category)} else f"{new_category}{PATH_SEP}{identity}"
    else:
        row["canonical_path"] = new_category
    remaining_tail = tail[1:] if tail and token_key(tail[0]) == token_key(identity) else tail
    remaining_tail = clean_modifier_tail(row["canonical_path"], remaining_tail)
    row["retail_leaf_path"] = PATH_SEP.join([row["canonical_path"]] + remaining_tail) if remaining_tail else row["canonical_path"]
    row["modifier"] = PATH_SEP.join(remaining_tail)


def consensus_normalization_reason(row: dict[str, str]) -> str:
    category = bfc(row)
    leaf = row.get("retail_leaf_path", "") or ""
    canonical = row.get("canonical_path", "") or ""
    fill_empty = False

    if not leaf and canonical:
        row["retail_leaf_path"] = canonical
        row["modifier"] = ""
        leaf = canonical
        fill_empty = True

    if category == "Canned Vegetables" and not path_starts(leaf, "Pantry"):
        if path_starts(leaf, "Produce > Vegetables"):
            force_route_prefix(row, "Produce > Vegetables", "Pantry > Canned Vegetables")
            identity_hint = identity_from_title(row)
            if identity_hint:
                force_to_category(row, "Pantry > Canned Vegetables", identity_hint=identity_hint)
        else:
            force_to_category(row, "Pantry > Canned Vegetables", identity_hint=identity_from_title(row))
        return "consensus_normalize:canned_vegetables_to_pantry"
    if category == "Frozen Vegetables" and not path_starts(leaf, "Frozen > Vegetables"):
        if path_starts(leaf, "Produce > Vegetables"):
            force_route_prefix(row, "Produce > Vegetables", "Frozen > Vegetables")
        elif path_starts(leaf, "Pantry > Canned Vegetables"):
            force_route_prefix(row, "Pantry > Canned Vegetables", "Frozen > Vegetables")
        else:
            force_to_category(row, "Frozen > Vegetables", identity_hint=identity_from_title(row))
        return "consensus_normalize:frozen_vegetables_to_frozen"
    if "Frozen Fruit" in category and canonical and not path_starts(leaf, "Frozen"):
        if path_starts(leaf, "Produce > Fruit"):
            force_route_prefix(row, "Produce > Fruit", "Frozen > Frozen Fruit")
            return "consensus_normalize:frozen_fruit_to_frozen"
        force_to_category(row, "Frozen > Frozen Fruit")
        return "consensus_normalize:frozen_fruit_to_frozen"
    if category == "Nut & Seed Butters" and path_starts(leaf, "Dairy > Butter"):
        force_route_prefix(row, "Dairy > Butter", "Pantry > Nut Butters")
        return "consensus_normalize:nut_seed_butters_to_pantry"
    if category == "Pasta Dinners" and not path_starts(leaf, "Meal > Pasta Dishes"):
        if path_starts(leaf, "Frozen > Single Entrees"):
            force_route_prefix(row, "Frozen > Single Entrees", "Meal > Pasta Dishes")
        else:
            force_to_category(row, "Meal > Pasta Dishes")
        return "consensus_normalize:pasta_dinners_to_meal_pasta"
    if fill_empty:
        return "consensus_normalize:fill_empty_retail_leaf_path"
    return ""


def repair_path_shape(row: dict[str, str]) -> bool:
    changed = False
    category = row.get("category_path_fixed", "") or ""
    canonical = row.get("canonical_path", "") or ""
    leaf = row.get("retail_leaf_path", "") or ""

    if canonical and category and not (canonical == category or canonical.startswith(category + PATH_SEP)):
        canonical_parts = split_path(canonical)
        if len(canonical_parts) >= 2:
            row["category_path_fixed"] = PATH_SEP.join(canonical_parts[:-1])
            row["product_identity_fixed"] = canonical_parts[-1]
            changed = True

    canonical = row.get("canonical_path", "") or ""
    leaf = row.get("retail_leaf_path", "") or ""
    if canonical and leaf and not (leaf == canonical or leaf.startswith(canonical + PATH_SEP)):
        canonical_depth = len(split_path(canonical))
        leaf_parts = split_path(leaf)
        if len(leaf_parts) >= canonical_depth:
            row["canonical_path"] = PATH_SEP.join(leaf_parts[:canonical_depth])
            canonical_parts = split_path(row["canonical_path"])
            if len(canonical_parts) >= 2:
                row["category_path_fixed"] = PATH_SEP.join(canonical_parts[:-1])
                row["product_identity_fixed"] = canonical_parts[-1]
            changed = True

    clean_row_modifier(row)
    canonical = row.get("canonical_path", "") or ""
    leaf = row.get("retail_leaf_path", "") or ""
    if canonical and leaf == canonical:
        row["modifier"] = ""
    elif canonical and leaf.startswith(canonical + PATH_SEP):
        row["modifier"] = leaf[len(canonical + PATH_SEP):]

    return changed


def has_type_echo(row: Mapping[str, str]) -> bool:
    parts = split_path(row.get("retail_leaf_path", "") or "")
    for part in parts:
        tokens = re.findall(r"[a-z0-9]+", part.lower())
        for i in range(1, len(tokens)):
            if tokens[i] == tokens[i - 1]:
                return True
    return False


def has_bfc_name_leaf(row: Mapping[str, str]) -> bool:
    parts = split_path(row.get("retail_leaf_path", "") or "")
    if not parts:
        return False
    bfc_key = token_key(row.get("branded_food_category", "") or "")
    leaf_key = token_key(parts[-1])
    return bool(bfc_key and leaf_key and (leaf_key == bfc_key or leaf_key in bfc_key.split(" ")))


def quality_metrics(rows: list[dict[str, str]]) -> dict[str, object]:
    fdc_counts = Counter((row.get("fdc_id") or "").strip() for row in rows)
    defects: Counter[str] = Counter()
    empty_rlp = 0
    invalid_family = 0
    type_echo = 0
    bfc_name_leaf = 0

    for row in rows:
        for defect in path_defects(row):
            defects[defect] += 1
        if not (row.get("retail_leaf_path") or "").strip():
            empty_rlp += 1
        department = split_path(row.get("retail_leaf_path", "") or "")
        if department and department[0] not in VALID_DEPARTMENTS:
            invalid_family += 1
        if has_type_echo(row):
            type_echo += 1
        if has_bfc_name_leaf(row):
            bfc_name_leaf += 1

    return {
        "rows": len(rows),
        "unique_fdc_ids": len(fdc_counts),
        "duplicate_fdc_extra_rows": sum(count - 1 for count in fdc_counts.values() if count > 1),
        "type_echo_rows": type_echo,
        "bfc_name_leaf_rows": bfc_name_leaf,
        "empty_retail_leaf_path_rows": empty_rlp,
        "invalid_family_rows": invalid_family,
        "path_defect_rows": sum(defects.values()),
        "path_defects": dict(defects.most_common()),
    }


def main() -> None:
    full_rows, full_counts, full_fieldnames = load_unique_by_fdc(FULL)
    codex_rows, codex_counts, _ = load_unique_by_fdc(CODEX)

    output_fieldnames = list(full_fieldnames)
    for field in ("consensus_source", "consensus_reason"):
        if field not in output_fieldnames:
            output_fieldnames.append(field)

    rows_out: list[dict[str, str]] = []
    decisions: list[dict[str, str]] = []
    reason_counts: Counter[str] = Counter()

    def sort_fdc(value: str) -> tuple[int, int | str]:
        return (0, int(value)) if value.isdigit() else (1, value)

    for fdc in sorted(full_rows, key=sort_fdc):
        full = full_rows[fdc]
        codex = codex_rows.get(fdc)
        out = dict(full)
        source = "full"
        reason = full_side_reason(full, codex) or "keep_full:default"
        codex_reason = ""

        if not reason.startswith("keep_full:") and reason != "full_only_row":
            raise AssertionError(f"unexpected full-side reason {reason!r}")

        if reason == "keep_full:default":
            codex_reason = codex_side_reason(full, codex)
            if codex_reason:
                copy_taxonomy(out, codex or {})
                source = "codex"
                reason = codex_reason

        normalization_reason = consensus_normalization_reason(out)
        if normalization_reason:
            source = "consensus"
            reason = normalization_reason
        if repair_path_shape(out):
            if reason == "keep_full:default":
                source = "consensus"
                reason = "consensus_normalize:repair_path_shape"
            else:
                reason = f"{reason}|repair_path_shape"

        out["consensus_source"] = source
        out["consensus_reason"] = reason
        rows_out.append(out)
        reason_counts[reason] += 1

        if source == "codex" or reason != "keep_full:default":
            decisions.append({
                "fdc_id": fdc,
                "title": full.get("title", ""),
                "branded_food_category": full.get("branded_food_category", ""),
                "consensus_source": source,
                "consensus_reason": reason,
                "full_retail_leaf_path": full.get("retail_leaf_path", ""),
                "codex_retail_leaf_path": (codex or {}).get("retail_leaf_path", ""),
                "consensus_retail_leaf_path": out.get("retail_leaf_path", ""),
            })

    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_out)

    decision_fields = [
        "fdc_id",
        "title",
        "branded_food_category",
        "consensus_source",
        "consensus_reason",
        "full_retail_leaf_path",
        "codex_retail_leaf_path",
        "consensus_retail_leaf_path",
    ]
    with DECISIONS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=decision_fields)
        writer.writeheader()
        writer.writerows(decisions)

    metrics = {
        "full": quality_metrics(list(full_rows.values())),
        "codex_first_occurrence": quality_metrics(list(codex_rows.values())),
        "consensus": quality_metrics(rows_out),
    }
    report = {
        "sources": {
            "full": str(FULL),
            "codex": str(CODEX),
        },
        "outputs": {
            "csv": str(OUT),
            "decisions": str(DECISIONS),
            "report": str(REPORT),
            "markdown": str(MD),
        },
        "input_row_counts": {
            "full_rows": sum(full_counts.values()),
            "full_unique_fdc_ids": len(full_counts),
            "full_duplicate_extra_rows": sum(count - 1 for count in full_counts.values() if count > 1),
            "codex_rows": sum(codex_counts.values()),
            "codex_unique_fdc_ids": len(codex_counts),
            "codex_duplicate_extra_rows": sum(count - 1 for count in codex_counts.values() if count > 1),
            "full_only_fdc_ids": len(set(full_rows) - set(codex_rows)),
            "codex_only_fdc_ids_ignored": len(set(codex_rows) - set(full_rows)),
        },
        "consensus_reason_counts": dict(reason_counts.most_common()),
        "codex_adopted_rows": sum(count for reason, count in reason_counts.items() if reason.startswith("take_codex:")),
        "explicit_full_kept_rows": sum(count for reason, count in reason_counts.items() if reason.startswith("keep_full:") and reason != "keep_full:default"),
        "quality_metrics": metrics,
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# Consensus Full Corpus Audit",
        "",
        f"Rows: `{metrics['consensus']['rows']:,}`",
        f"Unique FDC ids: `{metrics['consensus']['unique_fdc_ids']:,}`",
        f"Duplicate extra rows: `{metrics['consensus']['duplicate_fdc_extra_rows']:,}`",
        f"Path defect rows: `{metrics['consensus']['path_defect_rows']:,}`",
        "",
        "## Adopted From Codex",
        "",
    ]
    for reason, count in reason_counts.most_common():
        if reason.startswith("take_codex:"):
            lines.append(f"- `{reason}`: `{count:,}`")
    lines.extend(["", "## Consensus Normalizations", ""])
    for reason, count in reason_counts.most_common():
        if reason.startswith("consensus_normalize:"):
            lines.append(f"- `{reason}`: `{count:,}`")
    lines.extend(["", "## Explicitly Kept From Full", ""])
    for reason, count in reason_counts.most_common():
        if reason.startswith("keep_full:") and reason != "keep_full:default":
            lines.append(f"- `{reason}`: `{count:,}`")
    lines.extend(["", "## Quality Metrics", ""])
    for label in ("full", "codex_first_occurrence", "consensus"):
        metric = metrics[label]
        lines.append(
            f"- `{label}`: duplicate extra `{metric['duplicate_fdc_extra_rows']}`, "
            f"type echo `{metric['type_echo_rows']}`, BFC-name leaf `{metric['bfc_name_leaf_rows']}`, "
            f"path defects `{metric['path_defect_rows']}`"
        )
    MD.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "rows": metrics["consensus"]["rows"],
        "unique_fdc_ids": metrics["consensus"]["unique_fdc_ids"],
        "duplicate_fdc_extra_rows": metrics["consensus"]["duplicate_fdc_extra_rows"],
        "codex_adopted_rows": report["codex_adopted_rows"],
        "explicit_full_kept_rows": report["explicit_full_kept_rows"],
        "quality_metrics": metrics["consensus"],
        "outputs": report["outputs"],
    }, indent=2))


if __name__ == "__main__":
    main()
