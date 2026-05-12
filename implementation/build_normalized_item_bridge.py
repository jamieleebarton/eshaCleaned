from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

try:
    from map_recipe_lines_to_concepts import (
        MATCHED_STATUSES,
        approved_rule_for_surface,
        clean_example_surface,
        concept_key_from_parts,
        load_approved_normalization_rules,
        load_dictionary,
        load_supplemental_concepts,
        match_dictionary,
        match_supplemental_concept,
        normalize_surface,
        resolve_approved_rule,
    )
    from registry_fingerprint import registry_fingerprint_id, write_fingerprint_sidecar
    from resolver_context import DEFAULT_ARTIFACTS
except ModuleNotFoundError:
    from implementation.map_recipe_lines_to_concepts import (
        MATCHED_STATUSES,
        approved_rule_for_surface,
        clean_example_surface,
        concept_key_from_parts,
        load_approved_normalization_rules,
        load_dictionary,
        load_supplemental_concepts,
        match_dictionary,
        match_supplemental_concept,
        normalize_surface,
        resolve_approved_rule,
    )
    from implementation.registry_fingerprint import registry_fingerprint_id, write_fingerprint_sidecar
    from implementation.resolver_context import DEFAULT_ARTIFACTS


FIELDS = [
    "normalized_item",
    "occurrence_count",
    "canonical_concept_key",
    "canonical_surface",
    "bridge_status",
    "bridge_source",
    "match_rule_id",
    "trust_level",
    "nutrition_anchor_status",
    "product_contract_status",
    "product_contract_key",
    "review_notes",
    "registry_fingerprint",
]

READY_STATUSES = set(MATCHED_STATUSES) | {"approved_alias_match", "approved_manual_quantity_match"}
ALTERNATIVE_MARKER_RE = re.compile(r"(?:\bor\b|/)")
REVIEWED_PRODUCT_CARD_STATUSES = {"contract_passed"}


def concept_key_from_row(row: dict[str, str] | None) -> str:
    if not row:
        return ""
    return concept_key_from_parts(
        row.get("base_food", ""),
        row.get("variant", ""),
        row.get("form", ""),
        row.get("state", ""),
    )


def canonical_surface_from_key(concept_key: str) -> str:
    parts = (concept_key or "").split("|")
    parts = (parts + ["", "", "", ""])[:4]
    return " ".join(part for part in [parts[1], parts[2], parts[3], parts[0]] if part).strip()


def has_alternative_marker(surface: str) -> bool:
    return bool(ALTERNATIVE_MARKER_RE.search(surface or ""))


def load_product_audit(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    if not path.exists():
        return rows
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            concept_key = (row.get("concept_key") or "").strip()
            if concept_key:
                rows[concept_key] = row
    return rows


def build_reviewed_product_card_routes(product_audit: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    routes: dict[str, dict[str, str]] = {}
    conflicts: set[str] = set()
    for row in product_audit.values():
        if (row.get("audit_status") or row.get("product_status") or "").strip() not in REVIEWED_PRODUCT_CARD_STATUSES:
            continue
        concept_key = (row.get("concept_key") or "").strip()
        if not concept_key or ";" in concept_key:
            continue
        candidates = {
            clean_example_surface(row.get("concept_phrase", "")),
            clean_example_surface(canonical_surface_from_key(concept_key)),
        }
        if concept_key.endswith("|||"):
            candidates.add(clean_example_surface(concept_key[:-3]))
        for candidate in candidates:
            if not candidate:
                continue
            existing = routes.get(candidate)
            if existing is not None and existing.get("concept_key") != concept_key:
                conflicts.add(candidate)
                continue
            routes[candidate] = row
    for candidate in conflicts:
        routes.pop(candidate, None)
    return routes


def load_reviewed_external_catalog(path: Path) -> tuple[set[str], set[str]]:
    if not path.exists():
        return set(), set()
    covered: set[str] = set()
    reviewed_unknown: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row.get("review_status") or "").strip() != "approved":
                continue
            concept_key = (row.get("concept_key") or "").strip()
            if not concept_key:
                continue
            if (row.get("fdc_id") or "").strip():
                covered.add(concept_key)
            else:
                reviewed_unknown.add(concept_key)
    return covered, reviewed_unknown


def load_reviewed_sr28_fallbacks(path: Path) -> set[str]:
    if not path.exists():
        return set()
    covered: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row.get("review_status") or "").strip() != "approved":
                continue
            concept_key = (row.get("concept_key") or "").strip()
            if concept_key:
                covered.add(concept_key)
    return covered


def product_status_for(
    concept_key: str,
    product_audit: dict[str, dict[str, str]],
    reviewed_nutrition_covered: set[str],
    reviewed_nutrition_unknown: set[str],
) -> tuple[str, str, str]:
    if not concept_key or ";" in concept_key:
        return "", "", ""
    row = product_audit.get(concept_key)
    if not row:
        if concept_key in reviewed_nutrition_covered:
            return "external_catalog_covered", concept_key, "product_contract_not_ready"
        if concept_key in reviewed_nutrition_unknown:
            return "reviewed_nutrition_unknown", concept_key, "product_contract_not_ready"
        return "product_contract_unknown", concept_key, "nutrition_anchor_unknown"
    audit_status = row.get("audit_status", "") or row.get("product_status", "")
    contract_key = row.get("concept_key", "") or concept_key
    if audit_status == "contract_passed":
        nutrition_status = "product_contract_passed"
    elif row.get("policy") == "no_buy":
        nutrition_status = "no_buy"
    else:
        nutrition_status = "product_contract_not_ready"
    return audit_status, contract_key, nutrition_status


class NormalizedItemBridgeResolver:
    def __init__(
        self,
        dictionary_csv: Path,
        supplemental_csv: Path,
        approved_rules_csv: Path,
        product_audit_csv: Path,
    ) -> None:
        self.qualified, self.bases, self.aliases = load_dictionary(dictionary_csv)
        self.supplemental_aliases = load_supplemental_concepts(supplemental_csv)
        self.approved_rules = load_approved_normalization_rules(approved_rules_csv)
        self.product_audit = load_product_audit(product_audit_csv)
        self.product_card_routes = build_reviewed_product_card_routes(self.product_audit)
        external_covered, external_unknown = load_reviewed_external_catalog(
            DEFAULT_ARTIFACTS.reviewed_external_catalog_items_csv
        )
        self.reviewed_nutrition_covered = external_covered | load_reviewed_sr28_fallbacks(
            DEFAULT_ARTIFACTS.reviewed_sr28_nutrition_fallbacks_csv
        )
        self.reviewed_nutrition_unknown = external_unknown
        self.registry_id = registry_fingerprint_id()

    def finish_row(
        self,
        *,
        normalized_item: str,
        occurrence_count: int,
        canonical_concept_key: str,
        canonical_surface: str,
        bridge_status: str,
        bridge_source: str,
        match_rule_id: str = "",
        trust_level: str = "",
        review_notes: str = "",
    ) -> dict[str, str]:
        product_contract_status, product_contract_key, nutrition_anchor_status = product_status_for(
            canonical_concept_key,
            self.product_audit,
            self.reviewed_nutrition_covered,
            self.reviewed_nutrition_unknown,
        )
        return {
            "normalized_item": normalized_item,
            "occurrence_count": str(occurrence_count),
            "canonical_concept_key": canonical_concept_key,
            "canonical_surface": canonical_surface or canonical_surface_from_key(canonical_concept_key),
            "bridge_status": bridge_status,
            "bridge_source": bridge_source,
            "match_rule_id": match_rule_id,
            "trust_level": trust_level,
            "nutrition_anchor_status": nutrition_anchor_status,
            "product_contract_status": product_contract_status,
            "product_contract_key": product_contract_key,
            "review_notes": review_notes,
            "registry_fingerprint": self.registry_id,
        }

    def resolve(self, normalized_item: str, occurrence_count: int = 0) -> dict[str, str]:
        item = clean_example_surface(normalized_item)
        if not item:
            return self.finish_row(
                normalized_item=normalized_item,
                occurrence_count=occurrence_count,
                canonical_concept_key="",
                canonical_surface="",
                bridge_status="manual_food_required",
                bridge_source="empty_item",
                trust_level="manual",
                review_notes="empty normalized item",
            )

        product_card_route = self.product_card_routes.get(item)
        if product_card_route is not None:
            concept_key = product_card_route.get("concept_key", "")
            return self.finish_row(
                normalized_item=item,
                occurrence_count=occurrence_count,
                canonical_concept_key=concept_key,
                canonical_surface=product_card_route.get("concept_phrase", "") or canonical_surface_from_key(concept_key),
                bridge_status="concept_ready",
                bridge_source="reviewed_product_card_route",
                match_rule_id=product_card_route.get("contract_id", ""),
                trust_level="reviewed_md_product_card",
                review_notes=f"product contract audit: {product_card_route.get('audit_status', '')}",
            )

        approved_rule = approved_rule_for_surface(item, self.approved_rules)
        if approved_rule is not None:
            rule_type = approved_rule.get("rule_type", "")
            rule_id = approved_rule.get("rule_id", "")
            if rule_type == "alternative" and not has_alternative_marker(item):
                approved_rule = None
                rule_type = ""
                rule_id = ""
        if approved_rule is not None:
            if rule_type in {"alias", "manual_quantity"}:
                normalized, review_reason, status, reason, _dictionary_row = resolve_approved_rule(approved_rule)
                concept_key = concept_key_from_row(normalized)
                return self.finish_row(
                    normalized_item=item,
                    occurrence_count=occurrence_count,
                    canonical_concept_key=concept_key,
                    canonical_surface=approved_rule.get("canonical_surface", "") or canonical_surface_from_key(concept_key),
                    bridge_status="concept_ready",
                    bridge_source=status,
                    match_rule_id=rule_id,
                    trust_level="reviewed_rule",
                    review_notes=reason or review_reason,
                )
            if rule_type == "alternative":
                components = ";".join(part.strip() for part in (approved_rule.get("components") or "").split(";") if part.strip())
                return self.finish_row(
                    normalized_item=item,
                    occurrence_count=occurrence_count,
                    canonical_concept_key=components,
                    canonical_surface=approved_rule.get("canonical_surface", ""),
                    bridge_status="true_alternative_options",
                    bridge_source="approved_alternative_match",
                    match_rule_id=rule_id,
                    trust_level="reviewed_rule",
                    review_notes="approved alternatives; do not silently choose one",
                )
            if rule_type == "split":
                components = ";".join(part.strip() for part in (approved_rule.get("components") or "").split(";") if part.strip())
                return self.finish_row(
                    normalized_item=item,
                    occurrence_count=occurrence_count,
                    canonical_concept_key=components,
                    canonical_surface=approved_rule.get("canonical_surface", ""),
                    bridge_status="component_split",
                    bridge_source="approved_split_match",
                    match_rule_id=rule_id,
                    trust_level="reviewed_rule",
                    review_notes="approved split; downstream quantity allocation may still be required",
                )
            if rule_type == "reject":
                reason = approved_rule.get("canonical_surface") or "approved reject"
                status = "non_food_skip" if "non_food" in reason or "section" in reason else "manual_food_required"
                return self.finish_row(
                    normalized_item=item,
                    occurrence_count=occurrence_count,
                    canonical_concept_key="",
                    canonical_surface=reason,
                    bridge_status=status,
                    bridge_source="approved_reject",
                    match_rule_id=rule_id,
                    trust_level="reviewed_rule",
                    review_notes=reason,
                )
            if rule_type == "manual":
                reason = approved_rule.get("canonical_surface") or "approved manual"
                return self.finish_row(
                    normalized_item=item,
                    occurrence_count=occurrence_count,
                    canonical_concept_key="",
                    canonical_surface=reason,
                    bridge_status="manual_food_required",
                    bridge_source="approved_manual",
                    match_rule_id=rule_id,
                    trust_level="reviewed_rule",
                    review_notes=reason,
                )

        normalized, review_reason = normalize_surface(item)
        supplemental_status, supplemental_row, supplemental_reason = match_supplemental_concept(
            item,
            normalized,
            self.supplemental_aliases,
        )
        if supplemental_row is not None and supplemental_status in READY_STATUSES:
            concept_key = concept_key_from_parts(supplemental_row.get("canonical_concept", ""))
            return self.finish_row(
                normalized_item=item,
                occurrence_count=occurrence_count,
                canonical_concept_key=concept_key,
                canonical_surface=supplemental_row.get("canonical_concept", ""),
                bridge_status="concept_ready",
                bridge_source=supplemental_status,
                trust_level=supplemental_row.get("trust_state", "supplemental"),
                review_notes=supplemental_reason,
            )

        status, dictionary_row, reason = match_dictionary(
            normalized,
            review_reason,
            self.qualified,
            self.bases,
            self.aliases,
            item,
        )
        if dictionary_row is not None and status in READY_STATUSES:
            concept_key = concept_key_from_row(dictionary_row)
            return self.finish_row(
                normalized_item=item,
                occurrence_count=occurrence_count,
                canonical_concept_key=concept_key,
                canonical_surface=canonical_surface_from_key(concept_key),
                bridge_status="concept_ready",
                bridge_source=status,
                trust_level="dictionary",
                review_notes=reason,
            )

        if "section_header" in reason:
            bridge_status = "non_food_skip"
        elif "non_food" in reason:
            bridge_status = "non_food_skip"
        elif "composite_or" in reason or "composite_or" in review_reason:
            bridge_status = "true_alternative_options"
        elif "composite_and" in reason or "composite_and" in review_reason:
            bridge_status = "component_split"
        elif status == "base_only_match":
            bridge_status = "needs_concept_review"
        else:
            bridge_status = "needs_concept_review"

        return self.finish_row(
            normalized_item=item,
            occurrence_count=occurrence_count,
            canonical_concept_key="",
            canonical_surface="",
            bridge_status=bridge_status,
            bridge_source=status,
            trust_level="unresolved",
            review_notes="; ".join(part for part in [reason, review_reason] if part),
        )


def load_review_items(path: Path) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            item = (row.get("normalized_item") or "").strip()
            if not item:
                continue
            rows.append((item, int(row.get("item_count") or 0)))
    return rows


def write_db(path: Path, rows: list[dict[str, str]]) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE normalized_item_bridge (
                normalized_item TEXT PRIMARY KEY,
                occurrence_count INTEGER NOT NULL,
                canonical_concept_key TEXT NOT NULL,
                canonical_surface TEXT NOT NULL,
                bridge_status TEXT NOT NULL,
                bridge_source TEXT NOT NULL,
                match_rule_id TEXT NOT NULL,
                trust_level TEXT NOT NULL,
                nutrition_anchor_status TEXT NOT NULL,
                product_contract_status TEXT NOT NULL,
                product_contract_key TEXT NOT NULL,
                review_notes TEXT NOT NULL,
                registry_fingerprint TEXT NOT NULL
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO normalized_item_bridge VALUES (
                :normalized_item,
                :occurrence_count,
                :canonical_concept_key,
                :canonical_surface,
                :bridge_status,
                :bridge_source,
                :match_rule_id,
                :trust_level,
                :nutrition_anchor_status,
                :product_contract_status,
                :product_contract_key,
                :review_notes,
                :registry_fingerprint
            )
            """,
            rows,
        )
        conn.execute("CREATE INDEX idx_normalized_item_bridge_status ON normalized_item_bridge(bridge_status)")
        conn.execute("CREATE INDEX idx_normalized_item_bridge_concept ON normalized_item_bridge(canonical_concept_key)")
        conn.commit()
    finally:
        conn.close()


def build_bridge(args: argparse.Namespace) -> dict[str, object]:
    resolver = NormalizedItemBridgeResolver(
        args.dictionary_csv,
        args.supplemental_csv,
        args.approved_rules_csv,
        args.product_audit_csv,
    )
    input_rows = load_review_items(args.input_csv)
    bridge_rows = [resolver.resolve(item, count) for item, count in input_rows]

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(bridge_rows)
    write_db(args.output_db, bridge_rows)
    write_fingerprint_sidecar(args.output_csv)
    write_fingerprint_sidecar(args.output_db)

    status_rows = Counter(row["bridge_status"] for row in bridge_rows)
    status_occurrences = Counter()
    source_rows = Counter(row["bridge_source"] for row in bridge_rows)
    for row in bridge_rows:
        status_occurrences[row["bridge_status"]] += int(row["occurrence_count"] or 0)
    concept_ready_rows = status_rows["concept_ready"]
    concept_ready_occurrences = status_occurrences["concept_ready"]
    total_occurrences = sum(int(row["occurrence_count"] or 0) for row in bridge_rows)
    summary = {
        "input_csv": str(args.input_csv),
        "output_csv": str(args.output_csv),
        "output_db": str(args.output_db),
        "registry_fingerprint": registry_fingerprint_id(),
        "rows": len(bridge_rows),
        "total_occurrences": total_occurrences,
        "concept_ready_rows": concept_ready_rows,
        "concept_ready_row_percent": round(concept_ready_rows / len(bridge_rows) * 100, 2) if bridge_rows else 0.0,
        "concept_ready_occurrences": concept_ready_occurrences,
        "concept_ready_occurrence_percent": round(concept_ready_occurrences / total_occurrences * 100, 2)
        if total_occurrences
        else 0.0,
        "status_rows": dict(status_rows),
        "status_occurrences": dict(status_occurrences),
        "source_rows": dict(source_rows),
    }
    args.summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Build normalized item -> concept bridge from the reviewed 9K item layer.")
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_ARTIFACTS.recipeqa_item_review_ge10_csv)
    parser.add_argument("--dictionary-csv", type=Path, default=DEFAULT_ARTIFACTS.dictionary_csv)
    parser.add_argument("--supplemental-csv", type=Path, default=DEFAULT_ARTIFACTS.supplemental_concepts_csv)
    parser.add_argument("--approved-rules-csv", type=Path, default=DEFAULT_ARTIFACTS.approved_normalization_rules_csv)
    parser.add_argument("--product-audit-csv", type=Path, default=DEFAULT_ARTIFACTS.product_contract_audit_csv)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_ARTIFACTS.normalized_item_bridge_csv)
    parser.add_argument("--output-db", type=Path, default=DEFAULT_ARTIFACTS.normalized_item_bridge_db)
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_ARTIFACTS.normalized_item_bridge_summary_json)
    args = parser.parse_args()

    summary = build_bridge(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
