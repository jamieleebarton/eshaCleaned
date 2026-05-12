from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BRIDGE_CSV = ROOT / "implementation" / "output" / "normalized_item_concept_bridge.csv"
BRIDGE_SUMMARY_JSON = ROOT / "implementation" / "output" / "normalized_item_concept_bridge_summary.json"
LINE_SUMMARY_JSON = ROOT / "implementation" / "output" / "recipe_line_to_concept_full_summary.json"
CANONICAL_CSV = ROOT / "implementation" / "output" / "canonical_surface_normalized_with_product_proxies_CLEANED.csv"
PROCESS_EVAL_CSV = ROOT / "implementation" / "output" / "canonical_surface_esha_process_eval.csv"
WRONGNESS_CSV = ROOT / "implementation" / "output" / "canonical_surface_wrongness_audit_rows.csv"
CLEANUP_QUEUE_CSV = ROOT / "implementation" / "output" / "canonical_surface_esha_cleanup_queue.csv"
INGREDIENT_CARD_CSV = ROOT / "implementation" / "output" / "ingredient_card_candidates_ge10.csv"
OUT_CSV = ROOT / "implementation" / "output" / "top2500_ingredient_coverage_audit.csv"
OUT_HOLES_CSV = ROOT / "implementation" / "output" / "top2500_ingredient_coverage_holes.csv"
OUT_MD = ROOT / "implementation" / "output" / "top2500_ingredient_coverage_summary.md"


FIELDS = [
    "rank",
    "normalized_item",
    "occurrence_count",
    "cumulative_occurrences",
    "cumulative_percent_of_bridge",
    "cumulative_percent_of_full_lines",
    "canonical_surface",
    "canonical_concept_key",
    "bridge_status",
    "bridge_source",
    "trust_level",
    "product_contract_status",
    "product_contract_key",
    "canonical_row_status",
    "canonical_row_count",
    "selected_canonical_surface",
    "selected_canonical_normalized",
    "selected_family_base",
    "esha_code",
    "esha_description",
    "esha_match_type",
    "esha_backing_status",
    "pack_total_product_matches",
    "pack_candidate_clean_rows",
    "pack_cleanup_rows",
    "pack_path",
    "process_audit_flags",
    "wrongness_priority",
    "wrongness_batch",
    "wrongness_issue_type",
    "wrongness_suggested_esha_code",
    "wrongness_suggested_esha_description",
    "cleanup_priority",
    "cleanup_action",
    "cleanup_mechanism",
    "cleanup_recommended",
    "ingredient_card_status",
    "ingredient_card_occurrences",
    "ingredient_card_surfaces",
    "issue_priority",
    "issue_class",
    "issue_flags",
    "recommended_action",
]

NO_ESHA_SURFACE_OVERRIDES = {
    "canning salt": "No exact ESHA canning salt row; use SR28 salt nutrition and exact canning-salt shopping products.",
    "pickling salt": "No exact ESHA pickling salt row; use SR28 salt nutrition and exact pickling-salt shopping products.",
    "canning and pickling salt": "No exact ESHA canning/pickling salt row; use SR28 salt nutrition and exact canning/pickling shopping products.",
}


PRIORITY_SCORE = {"P1": 3, "P2": 2, "P3": 1, "OK": 0}
WRONGNESS_PRIORITY_SCORE = {"P1": 3, "P2": 2, "P3": 1, "": 0}

REQUIRED_INPUT_LABELS = {
    "bridge_csv": "normalized-item concept bridge CSV",
    "bridge_summary_json": "normalized-item bridge summary JSON",
    "line_summary_json": "recipe-line summary JSON",
    "canonical_csv": "canonical surface CSV",
    "process_eval_csv": "canonical surface process-eval CSV",
    "wrongness_csv": "canonical surface wrongness CSV",
    "cleanup_queue_csv": "canonical surface cleanup queue CSV",
    "ingredient_card_csv": "ingredient card candidates CSV",
}


def norm(value: str) -> str:
    text = str(value or "")
    repairs = {
        "√©": "e",
        "√±": "n",
        "√¢": "a",
        "√¨": "i",
        "√º": "u",
        "√°": "a",
        "√®": "e",
    }
    for old, new in repairs.items():
        text = text.replace(old, new)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower().replace("|", " ")).split())
    return normalized.replace("semi sweet", "semisweet")


def int_value(value: str) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def pct(part: int, total: int) -> str:
    if not total:
        return "0.000"
    return f"{part / total * 100:.3f}"


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def missing_required_inputs(args: argparse.Namespace) -> list[str]:
    missing: list[str] = []
    for field, label in REQUIRED_INPUT_LABELS.items():
        path = getattr(args, field)
        if not Path(path).exists():
            missing.append(f"{field}:{label}:{path}")
    return missing


def validate_required_inputs(args: argparse.Namespace) -> None:
    missing = missing_required_inputs(args)
    if missing:
        details = ", ".join(missing)
        raise FileNotFoundError(
            "top2500 ingredient coverage audit requires populated upstream artifacts; "
            f"missing {len(missing)} input(s): {details}"
        )


def write_csv(rows: list[dict[str, str]], path: Path, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def index_many(rows: list[dict[str, str]], *fields: str) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        for field in fields:
            key = norm(row.get(field, ""))
            if key:
                out.setdefault(key, []).append(row)
    return out


def index_one_best(rows: list[dict[str, str]], *fields: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        for field in fields:
            key = norm(row.get(field, ""))
            if key and key not in out:
                out[key] = row
    return out


def has_reviewed_or_reference_target(row: dict[str, str]) -> bool:
    if not row:
        return False
    if row.get("record_type") == "non_ingredient":
        return False
    if row.get("esha_code"):
        return True
    if row.get("esha_match_type", "").startswith("reviewed_no_esha_target"):
        return True
    return False


def has_reviewed_top2500_target(row: dict[str, str]) -> bool:
    return row.get("esha_match_type", "").startswith(("reviewed_top2500", "reviewed_no_esha_target"))


def priority_best(rows: list[dict[str, str]], *fields: str) -> dict[str, dict[str, str]]:
    if not fields:
        fields = ("canonical_surface", "canonical_normalized")
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        for field in fields:
            key = norm(row.get(field, ""))
            if not key:
                continue
            old = out.get(key)
            if old is None or WRONGNESS_PRIORITY_SCORE.get(row.get("priority", ""), 0) > WRONGNESS_PRIORITY_SCORE.get(old.get("priority", ""), 0):
                out[key] = row
    return out


def select_canonical_row(
    bridge_row: dict[str, str],
    canonical_by_surface: dict[str, list[dict[str, str]]],
    canonical_by_any: dict[str, list[dict[str, str]]],
) -> tuple[str, list[dict[str, str]], dict[str, str]]:
    canonical_surface = norm(bridge_row.get("canonical_surface", ""))
    normalized_item = norm(bridge_row.get("normalized_item", ""))
    exact = canonical_by_surface.get(canonical_surface, [])
    normalized_exact = canonical_by_surface.get(normalized_item, [])
    if exact and normalized_exact and normalized_item != canonical_surface:
        exact_selected = exact[0]
        normalized_selected = normalized_exact[0]
        if has_reviewed_top2500_target(normalized_selected):
            return "normalized_item_exact_override", normalized_exact, normalized_selected
        if not has_reviewed_or_reference_target(exact_selected) and has_reviewed_or_reference_target(normalized_selected):
            return "normalized_item_exact_override", normalized_exact, normalized_selected
    if exact:
        return "exact_surface", exact, exact[0]
    candidates = canonical_by_any.get(canonical_surface, [])
    if candidates:
        return "normalized_or_shopping_match", candidates, candidates[0]
    candidates = canonical_by_any.get(normalized_item, [])
    if candidates:
        return "normalized_item_match", candidates, candidates[0]
    return "missing", [], {}


def best_process_row(
    selected: dict[str, str],
    process_by_surface: dict[str, dict[str, str]],
    process_by_normalized: dict[str, dict[str, str]],
) -> dict[str, str]:
    if not selected:
        return {}
    return (
        process_by_surface.get(norm(selected.get("canonical_surface", "")))
        or process_by_normalized.get(norm(selected.get("canonical_normalized", "")))
        or {}
    )


def apply_no_esha_surface_override(selected: dict[str, str]) -> dict[str, str]:
    if not selected:
        return selected
    keys = {
        norm(selected.get("canonical_surface", "")),
        norm(selected.get("canonical_normalized", "")),
        norm(selected.get("canonical_shopping_item", "")),
    }
    hit = next((key for key in keys if key in NO_ESHA_SURFACE_OVERRIDES), "")
    if not hit:
        return selected
    patched = dict(selected)
    patched["esha_code"] = ""
    patched["esha_description"] = ""
    patched["esha_match_type"] = "reviewed_no_esha_target:top2500_surface_override"
    patched["unmatched_reason"] = NO_ESHA_SURFACE_OVERRIDES[hit]
    return patched


def issue_for(row: dict[str, str]) -> tuple[str, str, list[str], str]:
    flags: list[str] = []
    bridge_status = row["bridge_status"]
    bridge_source = row["bridge_source"]
    trust_level = row["trust_level"]
    contract_status = row["product_contract_status"]
    esha_code = row["esha_code"]
    backing = row["esha_backing_status"]
    clean_rows = int_value(row["pack_candidate_clean_rows"])
    cleanup_rows = int_value(row["pack_cleanup_rows"])
    explicit_no_esha_target = row["esha_match_type"].startswith("reviewed_no_esha_target")
    reviewed_assignment = row["esha_match_type"].startswith("reviewed_top2500")
    reviewed_assignment_ready = reviewed_assignment and contract_status in {"contract_passed", "external_catalog_covered"}
    reviewed_catalog_gap = reviewed_assignment_ready and clean_rows == 0 and cleanup_rows > 0
    reviewed_unknown_terminal = reviewed_assignment and contract_status == "reviewed_nutrition_unknown"
    reviewed_external_catalog = reviewed_assignment and (
        contract_status == "external_catalog_covered" or "external_catalog" in row["esha_match_type"]
    )
    explicit_split = bridge_status == "component_split" and bridge_source == "approved_split_match" and trust_level == "reviewed_rule"
    explicit_alternative = (
        bridge_status == "true_alternative_options"
        and bridge_source == "approved_alternative_match"
        and trust_level == "reviewed_rule"
    )
    explicit_manual_review = bridge_status == "manual_food_required" and bridge_source == "approved_reject" and trust_level == "reviewed_rule"

    if bridge_status not in {"concept_ready", "non_food_skip"}:
        flags.append(f"bridge_status:{bridge_status}")
    if contract_status in {"contract_failed", "product_contract_unknown", "reviewed_nutrition_unknown", "stale_normalization_artifact", ""}:
        flags.append(f"product_contract:{contract_status or 'blank'}")
    if row["canonical_row_status"] == "missing":
        flags.append("canonical_row_missing")
    if bridge_status == "concept_ready" and not esha_code:
        flags.append("esha_missing")
    if explicit_no_esha_target:
        flags.append("reviewed_no_esha_target")
    if row["wrongness_batch"]:
        flags.append(f"wrongness:{row['wrongness_batch']}")
    if row["cleanup_action"]:
        flags.append(f"md_cleanup:{row['cleanup_action']}")
    if backing in {"row_esha_cleanup_only", "row_esha_zero_product_matches"}:
        flags.append(f"esha_backing:{backing}")
    if clean_rows == 0 and cleanup_rows > 0:
        flags.append("md_pack_zero_clean_rows")
    if "very_broad_esha_query" in row["process_audit_flags"]:
        flags.append("md_pack_broad_query")

    if explicit_split:
        return "P3", "explicit_component_split", flags, "Reviewed split. Keep the split contract explicit and do not force a single ingredient identity."
    if explicit_alternative:
        return "P3", "explicit_alternative_options", flags, "Reviewed alternatives. Do not silently choose one option."
    if explicit_manual_review:
        return "P3", "explicit_manual_food_required", flags, "Reviewed hold. Keep this ingredient explicit until recipe context specifies the food."
    if bridge_status == "non_food_skip":
        return "P3", "explicit_non_food_skip", flags, "Reviewed non-food or equipment item. Keep it out of nutrition and shopping."
    if bridge_status not in {"concept_ready", "non_food_skip"}:
        return "P1", "ingredient_concept_not_ready", flags, "Review the normalized ingredient concept before touching ESHA or products."
    if contract_status == "contract_failed":
        return "P1", "product_contract_failed", flags, "Fix the product contract for this top ingredient."
    if row["canonical_row_status"] == "missing":
        return "P1", "canonical_surface_missing", flags, "Add or review the canonical surface row, then rerun ESHA assignment."
    if explicit_no_esha_target:
        return "P3", "explicit_no_esha_target", flags, "No exact ESHA source row found; keep SR28/FNDDS or product proxy backing explicit."
    if bridge_status == "concept_ready" and not esha_code:
        return "P1", "esha_missing_for_top_ingredient", flags, "Find a reviewed ESHA/SR28/FNDDS target or explicitly keep ESHA blank."
    if reviewed_external_catalog:
        flags.append("reviewed_external_catalog_shopping")
        return (
            "P3",
            "external_catalog_covered",
            flags,
            "Reviewed nutrition/code assignment. Shopping must use an external catalog or a reviewed retail product, not the ESHA product pack.",
        )
    if reviewed_unknown_terminal:
        flags.append("reviewed_nutrition_unknown_terminal")
        return (
            "P3",
            "reviewed_nutrition_unknown",
            flags,
            "Reviewed code assignment with no trustworthy nutrition/product backing. Keep it terminal until a real source is added.",
        )
    if contract_status in {"product_contract_unknown", "reviewed_nutrition_unknown", "stale_normalization_artifact", ""}:
        return "P2", "product_contract_not_ready", flags, "Review the product contract or mark the nutrition/shopping state explicitly."
    if reviewed_catalog_gap:
        flags.append("reviewed_code_contract_no_clean_local_product")
        return (
            "P3",
            "reviewed_local_product_catalog_gap",
            flags,
            "Reviewed code and contract. Keep the assignment, but fill shopping from an external catalog or a reviewed retail product.",
        )
    if row["wrongness_priority"] == "P1" and not reviewed_assignment_ready:
        return "P2", "esha_assignment_suspicious_high", flags, "Audit this ingredient's current ESHA assignment before trusting downstream products."
    if row["wrongness_batch"] and not reviewed_assignment_ready:
        return "P2", "esha_assignment_suspicious", flags, "Use the wrongness row and product probe to decide apply, clear, or hold."
    reviewed_broad_pack = (
        row["cleanup_action"] == "tighten_broad_esha_query"
        and contract_status == "contract_passed"
        and clean_rows > 0
    )
    if reviewed_broad_pack:
        flags.append("reviewed_broad_pack_filtered_by_contract")
    if (
        row["cleanup_action"]
        and not reviewed_broad_pack
        and not reviewed_assignment_ready
        or backing in {"row_esha_cleanup_only", "row_esha_zero_product_matches"}
        or (clean_rows == 0 and cleanup_rows > 0)
    ):
        return "P2", "md_card_or_query_gap", flags, "Open the ESHA card and fix categories/query/noise before changing canonical rows."
    if "md_pack_broad_query" in flags:
        return "P3", "md_card_broad_query_warning", flags, "Spot-check the ESHA card; it has products but the query is broad."
    if contract_status == "external_catalog_covered":
        return "P3", "external_catalog_covered", flags, "Likely acceptable, but verify shopping/nutrition separation if this becomes launch critical."
    return "OK", "ok", flags, "No top-level issue from this audit."


def build(args: argparse.Namespace) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    validate_required_inputs(args)
    bridge_rows = load_csv(args.bridge_csv)
    if not bridge_rows:
        raise ValueError(
            "top2500 ingredient coverage audit cannot run with an empty normalized-item bridge; "
            f"source={args.bridge_csv}"
        )
    bridge_rows.sort(key=lambda row: (-int_value(row.get("occurrence_count", "0")), row.get("normalized_item", "")))
    canonical_rows = load_csv(args.canonical_csv)
    process_rows = load_csv(args.process_eval_csv)
    wrongness_rows = load_csv(args.wrongness_csv)
    cleanup_rows = load_csv(args.cleanup_queue_csv)
    card_rows = load_csv(args.ingredient_card_csv)

    canonical_by_surface = index_many(canonical_rows, "canonical_surface")
    canonical_by_any = index_many(canonical_rows, "canonical_surface", "canonical_normalized", "canonical_shopping_item")
    process_by_surface = index_one_best(process_rows, "canonical_surface")
    process_by_normalized = index_one_best(process_rows, "canonical_normalized", "canonical_shopping_item")
    wrongness_by_surface = priority_best(wrongness_rows, "canonical_surface")
    wrongness_by_any = priority_best(wrongness_rows, "canonical_surface", "canonical_normalized")
    cleanup_by_surface = index_one_best(cleanup_rows, "canonical_surface")
    cleanup_by_any = index_one_best(cleanup_rows, "canonical_surface", "canonical_normalized", "canonical_shopping_item")
    card_by_key = {row.get("concept_key", ""): row for row in card_rows if row.get("concept_key")}

    bridge_summary = load_json(args.bridge_summary_json)
    line_summary = load_json(args.line_summary_json)
    bridge_total = int(bridge_summary.get("total_occurrences") or sum(int_value(row.get("occurrence_count", "0")) for row in bridge_rows))
    full_line_total = int(line_summary.get("total_occurrences") or bridge_total)

    top_rows = bridge_rows[: args.limit]
    cumulative = 0
    output_rows: list[dict[str, str]] = []
    for rank, bridge in enumerate(top_rows, 1):
        occ = int_value(bridge.get("occurrence_count", "0"))
        cumulative += occ
        canonical_status, canonical_matches, selected = select_canonical_row(bridge, canonical_by_surface, canonical_by_any)
        selected = apply_no_esha_surface_override(selected)
        process = best_process_row(selected, process_by_surface, process_by_normalized)
        lookup_key = norm(selected.get("canonical_surface") or bridge.get("canonical_surface") or bridge.get("normalized_item"))
        if canonical_status == "exact_surface":
            wrongness = wrongness_by_surface.get(lookup_key, {})
            cleanup = cleanup_by_surface.get(lookup_key, {})
        else:
            wrongness = wrongness_by_surface.get(lookup_key) or wrongness_by_any.get(lookup_key, {})
            cleanup = cleanup_by_surface.get(lookup_key) or cleanup_by_any.get(lookup_key, {})
        card = card_by_key.get(bridge.get("canonical_concept_key", ""), {})
        canonical_count = len(canonical_matches)

        row = {
            "rank": str(rank),
            "normalized_item": bridge.get("normalized_item", ""),
            "occurrence_count": str(occ),
            "cumulative_occurrences": str(cumulative),
            "cumulative_percent_of_bridge": pct(cumulative, bridge_total),
            "cumulative_percent_of_full_lines": pct(cumulative, full_line_total),
            "canonical_surface": bridge.get("canonical_surface", ""),
            "canonical_concept_key": bridge.get("canonical_concept_key", ""),
            "bridge_status": bridge.get("bridge_status", ""),
            "bridge_source": bridge.get("bridge_source", ""),
            "trust_level": bridge.get("trust_level", ""),
            "product_contract_status": bridge.get("product_contract_status", ""),
            "product_contract_key": bridge.get("product_contract_key", ""),
            "canonical_row_status": canonical_status,
            "canonical_row_count": str(canonical_count),
            "selected_canonical_surface": selected.get("canonical_surface", ""),
            "selected_canonical_normalized": selected.get("canonical_normalized", ""),
            "selected_family_base": selected.get("family_base", ""),
            "esha_code": selected.get("esha_code", ""),
            "esha_description": selected.get("esha_description", ""),
            "esha_match_type": selected.get("esha_match_type", ""),
            "esha_backing_status": process.get("esha_product_backing_status", ""),
            "pack_total_product_matches": process.get("pack_total_product_matches", ""),
            "pack_candidate_clean_rows": process.get("pack_candidate_clean_rows", ""),
            "pack_cleanup_rows": process.get("pack_cleanup_rows", ""),
            "pack_path": process.get("pack_path", ""),
            "process_audit_flags": process.get("audit_flags", ""),
            "wrongness_priority": wrongness.get("priority", ""),
            "wrongness_batch": wrongness.get("batch", ""),
            "wrongness_issue_type": wrongness.get("issue_type", ""),
            "wrongness_suggested_esha_code": wrongness.get("suggested_esha_code", ""),
            "wrongness_suggested_esha_description": wrongness.get("suggested_esha_description", ""),
            "cleanup_priority": cleanup.get("priority", ""),
            "cleanup_action": cleanup.get("action", ""),
            "cleanup_mechanism": cleanup.get("cleanup_mechanism", ""),
            "cleanup_recommended": cleanup.get("recommended_cleanup", ""),
            "ingredient_card_status": "present" if card else "missing",
            "ingredient_card_occurrences": card.get("occurrences", ""),
            "ingredient_card_surfaces": card.get("surfaces", ""),
            "issue_priority": "",
            "issue_class": "",
            "issue_flags": "",
            "recommended_action": "",
        }
        issue_priority, issue_class, flags, action = issue_for(row)
        row["issue_priority"] = issue_priority
        row["issue_class"] = issue_class
        row["issue_flags"] = " | ".join(flags)
        row["recommended_action"] = action
        output_rows.append(row)

    holes = [row for row in output_rows if row["issue_priority"] != "OK"]
    holes.sort(
        key=lambda row: (
            -PRIORITY_SCORE.get(row["issue_priority"], 0),
            -int_value(row["occurrence_count"]),
            row["normalized_item"],
        )
    )

    issue_counts = Counter(row["issue_class"] for row in output_rows)
    issue_occurrences = Counter()
    priority_counts = Counter(row["issue_priority"] for row in output_rows)
    priority_occurrences = Counter()
    bridge_counts = Counter(row["bridge_status"] for row in output_rows)
    contract_counts = Counter(row["product_contract_status"] for row in output_rows)
    for row in output_rows:
        occ = int_value(row["occurrence_count"])
        issue_occurrences[row["issue_class"]] += occ
        priority_occurrences[row["issue_priority"]] += occ

    needed_for_99 = ""
    running = 0
    for idx, row in enumerate(bridge_rows, 1):
        running += int_value(row.get("occurrence_count", "0"))
        if bridge_total and running / bridge_total >= 0.99:
            needed_for_99 = str(idx)
            break

    lines = [
        "# Top 2500 Ingredient Coverage Audit",
        "",
        "This audit starts from recipe ingredient occurrence, not product rows. It joins high-frequency normalized ingredients to the current concept bridge, canonical ESHA row, ESHA product pack, wrongness audit, cleanup queue, and ingredient-card rollup.",
        "",
        "## Coverage",
        "",
        f"- audited_top_n: {len(output_rows)}",
        f"- top_{len(output_rows)}_occurrences: {cumulative:,}",
        f"- bridge_total_occurrences: {bridge_total:,}",
        f"- full_line_total_occurrences: {full_line_total:,}",
        f"- top_{len(output_rows)}_percent_of_bridge: {pct(cumulative, bridge_total)}%",
        f"- top_{len(output_rows)}_percent_of_full_lines: {pct(cumulative, full_line_total)}%",
        f"- normalized_items_needed_for_99_percent_of_bridge: {needed_for_99}",
        "",
        "## Priority Counts",
        "",
        "| priority | rows | occurrences |",
        "| --- | ---: | ---: |",
    ]
    for priority in ("P1", "P2", "P3", "OK"):
        lines.append(f"| {priority} | {priority_counts.get(priority, 0)} | {priority_occurrences.get(priority, 0):,} |")

    lines.extend(["", "## Issue Classes", "", "| rows | occurrences | issue_class |", "| ---: | ---: | --- |"])
    for issue, count in issue_counts.most_common():
        lines.append(f"| {count} | {issue_occurrences[issue]:,} | {issue} |")

    lines.extend(["", "## Bridge Status", "", "| rows | status |", "| ---: | --- |"])
    for status, count in bridge_counts.most_common():
        lines.append(f"| {count} | {status or '(blank)'} |")

    lines.extend(["", "## Product Contract Status", "", "| rows | status |", "| ---: | --- |"])
    for status, count in contract_counts.most_common():
        lines.append(f"| {count} | {status or '(blank)'} |")

    lines.extend(
        [
            "",
            "## Top Holes",
            "",
            "| priority | occurrences | ingredient | issue_class | ESHA | action |",
            "| --- | ---: | --- | --- | --- | --- |",
        ]
    )
    for row in holes[:80]:
        esha = " ".join(part for part in [row["esha_code"], row["esha_description"]] if part).replace("|", "/")
        lines.append(
            f"| {row['issue_priority']} | {int_value(row['occurrence_count']):,} | "
            f"{row['normalized_item'].replace('|', '/')} | {row['issue_class']} | {esha or '(blank)'} | "
            f"{row['recommended_action'].replace('|', '/')} |"
        )

    lines.extend(
        [
            "",
            "## Read",
            "",
            "- `OK` means this audit did not find a top-level bridge/product/ESHA/card warning; it does not mean nutrition is fully manually verified.",
            "- `P1` means fix before trusting the ingredient at launch scale.",
            "- `P2` means likely real work, usually ESHA assignment, product contract, or `.md` card cleanup.",
            "- `P3` means watchlist: often external catalog coverage or broad `.md` query warnings.",
        ]
    )
    return output_rows, holes, lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=2500)
    parser.add_argument("--bridge-csv", type=Path, default=BRIDGE_CSV)
    parser.add_argument("--bridge-summary-json", type=Path, default=BRIDGE_SUMMARY_JSON)
    parser.add_argument("--line-summary-json", type=Path, default=LINE_SUMMARY_JSON)
    parser.add_argument("--canonical-csv", type=Path, default=CANONICAL_CSV)
    parser.add_argument("--process-eval-csv", type=Path, default=PROCESS_EVAL_CSV)
    parser.add_argument("--wrongness-csv", type=Path, default=WRONGNESS_CSV)
    parser.add_argument("--cleanup-queue-csv", type=Path, default=CLEANUP_QUEUE_CSV)
    parser.add_argument("--ingredient-card-csv", type=Path, default=INGREDIENT_CARD_CSV)
    parser.add_argument("--out-csv", type=Path, default=OUT_CSV)
    parser.add_argument("--out-holes-csv", type=Path, default=OUT_HOLES_CSV)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()

    rows, holes, lines = build(args)
    write_csv(rows, args.out_csv, FIELDS)
    write_csv(holes, args.out_holes_csv, FIELDS)
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(rows)} holes={len(holes)} out_csv={args.out_csv} out_holes={args.out_holes_csv} out_md={args.out_md}")


if __name__ == "__main__":
    main()
