from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

try:
    from resolver_context import DEFAULT_ARTIFACTS
except ModuleNotFoundError:
    from implementation.resolver_context import DEFAULT_ARTIFACTS

try:
    from map_recipe_lines_to_concepts import approved_rule_for_surface, load_approved_normalization_rules
except ModuleNotFoundError:
    from implementation.map_recipe_lines_to_concepts import approved_rule_for_surface, load_approved_normalization_rules


QUANTITY_RE = re.compile(
    r"^\s*(?P<quantity>\d+(?:\s+\d+/\d+|/\d+|\.\d+)?|[¼½¾⅓⅔⅛⅜⅝⅞])?\s*"
    r"(?P<unit>cups?|c\.|teaspoons?|tsp\.?|tablespoons?|tbsp\.?|pounds?|lbs?\.?|ounces?|oz\.?|"
    r"grams?|g|kilograms?|kg|milliliters?|ml|liters?|l|cans?|packages?|pkg\.?|boxes?|jars?|"
    r"bottles?|cartons?|slices?|pieces?|whole|large|small|medium|dash|dashes|pinch|pinches)?\s+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NormalizedResolution:
    parsed_quantity: str = ""
    parsed_unit: str = ""
    parsed_food_phrase: str = ""
    item_candidate: str = ""
    candidate_method: str = ""
    candidate_confidence: float = 0.0
    bridge_status: str = "unmatched"
    canonical_concept_key: str = "|||"
    canonical_surface: str = ""
    bridge_source: str = ""
    match_rule_id: str = ""
    trust_level: str = ""
    product_contract_status: str = ""
    product_contract_key: str = ""
    review_notes: str = ""
    registry_fingerprint: str = ""


def normalize_candidate_surface(text: str | None) -> str:
    text = (text or "").lower()
    text = text.replace("&nbsp;", " ").replace("&nbsp", " ")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    text = re.sub(r"\s+", " ", text).strip(" ,;:.")
    return text


def strip_leading_quantity_unit(line: str) -> tuple[str, str, str]:
    surface = normalize_candidate_surface(line)
    quantity = ""
    unit = ""
    match = QUANTITY_RE.match(surface)
    if match:
        quantity = (match.group("quantity") or "").strip()
        unit = (match.group("unit") or "").strip(". ")
        surface = surface[match.end() :].strip(" ,;:.")
    return quantity, unit, surface


def comma_fallback(surface: str) -> str:
    return normalize_candidate_surface(surface.split(",", 1)[0])


class CanonicalIngredientNormalizer:
    def __init__(
        self,
        bridge_csv: Path = DEFAULT_ARTIFACTS.normalized_item_bridge_csv,
        approved_rules_csv: Path = DEFAULT_ARTIFACTS.approved_normalization_rules_csv,
        ner_jsonl: Path | None = None,
    ) -> None:
        self.bridge_rows = self._load_bridge(bridge_csv)
        self.approved_rules = load_approved_normalization_rules(approved_rules_csv)
        self.ner_candidates = self._load_ner_candidates(ner_jsonl)

    def _load_bridge(self, path: Path) -> dict[str, dict[str, str]]:
        rows: dict[str, dict[str, str]] = {}
        if not path.exists():
            return rows
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                key = normalize_candidate_surface(row.get("normalized_item"))
                if key and key not in rows:
                    rows[key] = row
        return rows

    def _load_exact_rules(self, path: Path) -> dict[str, dict[str, str]]:
        rows: dict[str, dict[str, str]] = {}
        if not path.exists():
            return rows
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("status") != "approved":
                    continue
                if row.get("rule_type") != "alias" or row.get("match_type") != "exact":
                    continue
                key = normalize_candidate_surface(row.get("input_surface"))
                concept_key = (row.get("canonical_concept_key") or "").strip()
                if key and concept_key and concept_key != "|||" and ";" not in concept_key:
                    rows[key] = row
        return rows

    def _load_ner_candidates(self, path: Path | None) -> dict[str, str]:
        if path is None or not path.exists():
            return {}
        candidates: dict[str, str] = {}
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                key = normalize_candidate_surface(row.get("normalized_line"))
                candidate = normalize_candidate_surface(row.get("candidate_food_phrase"))
                if key and candidate:
                    candidates[key] = candidate
        return candidates

    def normalize_item_candidate(
        self,
        candidate: str,
        *,
        parsed_quantity: str = "",
        parsed_unit: str = "",
        method_prefix: str = "parsed_surface",
        occurrence_count: int = 0,
    ) -> dict[str, str]:
        surface = normalize_candidate_surface(candidate)
        lookup_surfaces = (surface, comma_fallback(surface))
        for lookup_surface in lookup_surfaces:
            if not lookup_surface:
                continue
            rule = approved_rule_for_surface(lookup_surface, self.approved_rules, include_regex=False)
            if rule and rule.get("rule_type") == "reject":
                return self._dict_from_reject(
                    rule,
                    surface=surface,
                    lookup_surface=lookup_surface,
                    parsed_quantity=parsed_quantity,
                    parsed_unit=parsed_unit,
                    method_prefix=method_prefix,
                )
            if rule and rule.get("rule_type") in {"alias", "manual_quantity"}:
                concept_key = (rule.get("canonical_concept_key") or "").strip()
                if not concept_key or concept_key == "|||" or ";" in concept_key:
                    continue
                return self._dict_from_rule(
                    rule,
                    surface=surface,
                    lookup_surface=lookup_surface,
                    parsed_quantity=parsed_quantity,
                    parsed_unit=parsed_unit,
                    method_prefix=method_prefix,
                )
            if lookup_surface in self.bridge_rows:
                return self._dict_from_bridge(
                    self.bridge_rows[lookup_surface],
                    surface=surface,
                    lookup_surface=lookup_surface,
                    parsed_quantity=parsed_quantity,
                    parsed_unit=parsed_unit,
                    method_prefix=method_prefix,
                )
        for lookup_surface in lookup_surfaces:
            if not lookup_surface:
                continue
            rule = approved_rule_for_surface(lookup_surface, self.approved_rules, include_exact=False)
            if rule and rule.get("rule_type") == "reject":
                return self._dict_from_reject(
                    rule,
                    surface=surface,
                    lookup_surface=lookup_surface,
                    parsed_quantity=parsed_quantity,
                    parsed_unit=parsed_unit,
                    method_prefix=method_prefix,
                )
            if rule and rule.get("rule_type") in {"alias", "manual_quantity"}:
                concept_key = (rule.get("canonical_concept_key") or "").strip()
                if not concept_key or concept_key == "|||" or ";" in concept_key:
                    continue
                return self._dict_from_rule(
                    rule,
                    surface=surface,
                    lookup_surface=lookup_surface,
                    parsed_quantity=parsed_quantity,
                    parsed_unit=parsed_unit,
                    method_prefix=method_prefix,
                )
        return {
            "parsed_quantity": parsed_quantity,
            "parsed_unit": parsed_unit,
            "parsed_food_phrase": surface,
            "item_candidate": surface,
            "candidate_method": f"{method_prefix}_unmatched",
            "candidate_confidence": "0.0",
            "bridge_status": "unmatched",
            "canonical_concept_key": "|||",
            "canonical_surface": "",
            "bridge_source": "",
            "match_rule_id": "",
            "trust_level": "",
            "product_contract_status": "",
            "product_contract_key": "",
            "review_notes": "",
            "registry_fingerprint": "",
        }

    def normalize_line(
        self,
        line: str,
        *,
        item_hint: str | None = None,
        occurrence_count: int = 0,
    ) -> NormalizedResolution:
        quantity, unit, parsed_surface = strip_leading_quantity_unit(line)
        if item_hint:
            hinted = self.normalize_item_candidate(
                item_hint,
                parsed_quantity=quantity,
                parsed_unit=unit,
                method_prefix="item_hint",
                occurrence_count=occurrence_count,
            )
            if hinted["bridge_status"] == "concept_ready":
                return NormalizedResolution(**hinted)
            if hinted["bridge_status"] == "rejected":
                return NormalizedResolution(**hinted)

        parsed = self.normalize_item_candidate(
            parsed_surface,
            parsed_quantity=quantity,
            parsed_unit=unit,
            method_prefix="parsed_surface",
            occurrence_count=occurrence_count,
        )
        if parsed["bridge_status"] == "concept_ready":
            return NormalizedResolution(**parsed)
        if parsed["bridge_status"] == "rejected":
            return NormalizedResolution(**parsed)

        ner_candidate = self.ner_candidates.get(normalize_candidate_surface(line))
        if ner_candidate:
            ner = self.normalize_item_candidate(
                ner_candidate,
                parsed_quantity=quantity,
                parsed_unit=unit,
                method_prefix="hf_ner_candidate",
                occurrence_count=occurrence_count,
            )
            if ner["bridge_status"] == "concept_ready":
                return NormalizedResolution(**ner)
            if ner["bridge_status"] == "rejected":
                return NormalizedResolution(**ner)

        return NormalizedResolution(**parsed)

    def _dict_from_reject(
        self,
        rule: dict[str, str],
        *,
        surface: str,
        lookup_surface: str,
        parsed_quantity: str,
        parsed_unit: str,
        method_prefix: str,
    ) -> dict[str, str]:
        match_type = rule.get("match_type") or "exact"
        return {
            "parsed_quantity": parsed_quantity,
            "parsed_unit": parsed_unit,
            "parsed_food_phrase": surface,
            "item_candidate": lookup_surface,
            "candidate_method": f"{method_prefix}_approved_{match_type}_reject",
            "candidate_confidence": "1.0",
            "bridge_status": "rejected",
            "canonical_concept_key": "|||",
            "canonical_surface": rule.get("canonical_surface") or "non_food",
            "bridge_source": "approved_normalization_reject",
            "match_rule_id": rule.get("rule_id") or "",
            "trust_level": "reviewed_reject",
            "product_contract_status": "contract_passed",
            "product_contract_key": "",
            "review_notes": rule.get("evidence") or "",
            "registry_fingerprint": "",
        }

    def _dict_from_rule(
        self,
        rule: dict[str, str],
        *,
        surface: str,
        lookup_surface: str,
        parsed_quantity: str,
        parsed_unit: str,
        method_prefix: str,
    ) -> dict[str, str]:
        concept_key = (rule.get("canonical_concept_key") or "").strip()
        bridge = self._bridge_by_concept(concept_key)
        match_type = rule.get("match_type") or "exact"
        return {
            "parsed_quantity": parsed_quantity,
            "parsed_unit": parsed_unit,
            "parsed_food_phrase": surface,
            "item_candidate": lookup_surface,
            "candidate_method": f"{method_prefix}_approved_{match_type}_rule",
            "candidate_confidence": "1.0",
            "bridge_status": "concept_ready",
            "canonical_concept_key": concept_key,
            "canonical_surface": rule.get("canonical_surface") or bridge.get("canonical_surface", lookup_surface),
            "bridge_source": "approved_normalization_rules",
            "match_rule_id": rule.get("rule_id", ""),
            "trust_level": "reviewed_rule",
            "product_contract_status": bridge.get("product_contract_status", ""),
            "product_contract_key": bridge.get("product_contract_key", concept_key),
            "review_notes": rule.get("evidence", ""),
            "registry_fingerprint": bridge.get("registry_fingerprint", ""),
        }

    def _dict_from_bridge(
        self,
        row: dict[str, str],
        *,
        surface: str,
        lookup_surface: str,
        parsed_quantity: str,
        parsed_unit: str,
        method_prefix: str,
    ) -> dict[str, str]:
        return {
            "parsed_quantity": parsed_quantity,
            "parsed_unit": parsed_unit,
            "parsed_food_phrase": surface,
            "item_candidate": lookup_surface,
            "candidate_method": f"{method_prefix}_bridge_lookup",
            "candidate_confidence": "1.0",
            "bridge_status": row.get("bridge_status", ""),
            "canonical_concept_key": row.get("canonical_concept_key", ""),
            "canonical_surface": row.get("canonical_surface", ""),
            "bridge_source": row.get("bridge_source", ""),
            "match_rule_id": row.get("match_rule_id", ""),
            "trust_level": row.get("trust_level", ""),
            "product_contract_status": row.get("product_contract_status", ""),
            "product_contract_key": row.get("product_contract_key", ""),
            "review_notes": row.get("review_notes", ""),
            "registry_fingerprint": row.get("registry_fingerprint", ""),
        }

    def _bridge_by_concept(self, concept_key: str) -> dict[str, str]:
        for row in self.bridge_rows.values():
            if row.get("canonical_concept_key") == concept_key:
                return row
        return {}
