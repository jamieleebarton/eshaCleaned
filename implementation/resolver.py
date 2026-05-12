from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import registries


ROOT = Path(__file__).resolve().parent.parent
FNDDDS_PATH = ROOT / "data" / "fndds" / "MainFoodDesc16.csv"
SR28_PATH = ROOT / "data" / "sr28_csv" / "food.csv"
PRODUCT_DB_PATH = ROOT / "data" / "master_products.db"


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    value = text.lower().strip()
    value = value.replace("’", "'").replace("–", "-").replace("—", "-")
    value = value.replace("-", " ")
    value = " ".join(value.split())
    if value.endswith("es") and value[:-2] in registries.EXACT_USDA_ANCHORS:
        return value[:-2]
    if value.endswith("s") and value[:-1] in registries.EXACT_USDA_ANCHORS:
        return value[:-1]
    return value


@dataclass
class ProductCandidate:
    gtin_upc: str | None
    description: str
    brand_owner: str | None
    brand_name: str | None
    category: str
    serving_size: float | None
    serving_size_unit: str | None
    calories: float | None
    protein_g: float | None
    fat_g: float | None
    carbs_g: float | None
    sodium_mg: float | None
    accepted: bool
    reason: str
    score: float


@dataclass
class Resolution:
    input_item: str
    normalized_item: str
    canonical_item: str
    nutrition_state: str
    shopping_state: str
    source_system: str | None
    source_code: str | None
    description: str | None
    note: str | None
    alias_evidence: str | None
    proxy_target: dict[str, Any] | None
    local_label_anchor: str | None
    accepted_products: list[ProductCandidate]
    rejected_examples: list[ProductCandidate]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["accepted_products"] = [asdict(row) for row in self.accepted_products]
        payload["rejected_examples"] = [asdict(row) for row in self.rejected_examples]
        return payload


class RegistryValidationError(RuntimeError):
    pass


class MitigationResolver:
    def __init__(self, product_db_path: Path = PRODUCT_DB_PATH) -> None:
        self.product_db_path = Path(product_db_path)
        self.fndds_codes = self._load_codes(FNDDDS_PATH, "food_code")
        self.sr28_codes = self._load_codes(SR28_PATH, "fdc_id")
        self._validate_registries()

    def _load_codes(self, csv_path: Path, code_field: str) -> dict[str, dict[str, str]]:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise RegistryValidationError(f"{csv_path} has no header row")
            field_lookup = {name.strip().lower().replace(" ", "_"): name for name in reader.fieldnames}
            real_field = field_lookup.get(code_field.lower())
            if real_field is None:
                raise RegistryValidationError(
                    f"{csv_path} missing code field {code_field!r}; headers={reader.fieldnames!r}"
                )
            return {row[real_field]: row for row in reader}

    def _validate_registries(self) -> None:
        errors: list[str] = []
        for item, entry in registries.EXACT_USDA_ANCHORS.items():
            system = entry["system"]
            code = entry["code"]
            if system == "FNDDS" and code not in self.fndds_codes:
                errors.append(f"{item}: missing FNDDS code {code}")
            if system == "SR28" and code not in self.sr28_codes:
                errors.append(f"{item}: missing SR28 code {code}")
        for item, entry in registries.REVIEWED_PROXIES.items():
            system = entry["target_system"]
            code = entry["target_code"]
            if system == "FNDDS" and code not in self.fndds_codes:
                errors.append(f"{item}: missing proxy FNDDS code {code}")
            if system == "SR28" and code not in self.sr28_codes:
                errors.append(f"{item}: missing proxy SR28 code {code}")
        if errors:
            raise RegistryValidationError("\n".join(errors))

    def resolve(self, item: str, display: str = "", grams: float | None = None) -> Resolution:
        normalized_item = normalize_text(item)
        display_norm = normalize_text(display) or normalized_item
        canonical_item, alias_evidence = self._resolve_alias(normalized_item)

        if self._is_non_food(canonical_item, grams):
            return self._finalize(
                input_item=item,
                normalized_item=normalized_item,
                canonical_item=canonical_item,
                nutrition_state="non_food",
                shopping_state="non_food",
                source_system=None,
                source_code=None,
                description=None,
                note="non-food ingredient/supply",
                alias_evidence=alias_evidence,
                proxy_target=None,
                local_label_anchor=None,
                product_rule_id=None,
            )

        exact_entry = self._exact_entry(canonical_item, display_norm)
        if exact_entry:
            return self._finalize(
                input_item=item,
                normalized_item=normalized_item,
                canonical_item=canonical_item,
                nutrition_state="exact_usda_anchor",
                shopping_state="shopping_candidates_strong",
                source_system=exact_entry["system"],
                source_code=exact_entry["code"],
                description=exact_entry["description"],
                note=None,
                alias_evidence=alias_evidence,
                proxy_target=None,
                local_label_anchor=None,
                product_rule_id=exact_entry.get("product_rule"),
            )

        if canonical_item in registries.REVIEWED_LOCAL_LABEL_ANCHORS:
            entry = registries.REVIEWED_LOCAL_LABEL_ANCHORS[canonical_item]
            return self._finalize(
                input_item=item,
                normalized_item=normalized_item,
                canonical_item=canonical_item,
                nutrition_state="reviewed_local_label_anchor",
                shopping_state="shopping_candidates_strong",
                source_system="LOCAL_LABEL",
                source_code=None,
                description=entry["nutrition_basis"],
                note=entry["review_notes"],
                alias_evidence=alias_evidence,
                proxy_target=None,
                local_label_anchor=entry["anchor_name"],
                product_rule_id=entry["product_rule"],
            )

        if canonical_item in registries.REVIEWED_PROXIES:
            entry = registries.REVIEWED_PROXIES[canonical_item]
            return self._finalize(
                input_item=item,
                normalized_item=normalized_item,
                canonical_item=canonical_item,
                nutrition_state="reviewed_proxy",
                shopping_state="shopping_candidates_strong",
                source_system=entry["target_system"],
                source_code=entry["target_code"],
                description=entry["target_description"],
                note=f"approximate via {entry['proxy_class']}",
                alias_evidence=alias_evidence,
                proxy_target=entry,
                local_label_anchor=None,
                product_rule_id=entry["product_rule"],
            )

        if canonical_item in registries.SHOPPING_ONLY_ITEMS:
            entry = registries.SHOPPING_ONLY_ITEMS[canonical_item]
            return self._finalize(
                input_item=item,
                normalized_item=normalized_item,
                canonical_item=canonical_item,
                nutrition_state="nutrition_unknown",
                shopping_state="shopping_candidates_strong",
                source_system=None,
                source_code=None,
                description=None,
                note=entry["reason"],
                alias_evidence=alias_evidence,
                proxy_target=None,
                local_label_anchor=None,
                product_rule_id=entry["product_rule"],
            )

        note = "quantity known food but no reviewed nutrition source" if (grams == 0 and not self._is_non_food(canonical_item, grams)) else "no reviewed nutrition source"
        return self._finalize(
            input_item=item,
            normalized_item=normalized_item,
            canonical_item=canonical_item,
            nutrition_state="nutrition_unknown",
            shopping_state="shopping_gap",
            source_system=None,
            source_code=None,
            description=None,
            note=note,
            alias_evidence=alias_evidence,
            proxy_target=None,
            local_label_anchor=None,
            product_rule_id=None,
        )

    def _resolve_alias(self, normalized_item: str) -> tuple[str, str | None]:
        alias = registries.ALIASES.get(normalized_item)
        if not alias:
            return normalized_item, None
        return alias["canonical"], alias["evidence"]

    def _is_non_food(self, canonical_item: str, grams: float | None) -> bool:
        tokens = set(canonical_item.split())
        if grams != 0:
            return False
        return any(token in registries.NON_FOOD_TOKENS for token in tokens)

    def _exact_entry(self, canonical_item: str, display_norm: str) -> dict[str, Any] | None:
        base = registries.EXACT_USDA_ANCHORS.get(canonical_item)
        if not base:
            return None
        variant_rules = registries.DISPLAY_VARIANTS.get(canonical_item, [])
        for rule in variant_rules:
            if any(term in display_norm for term in rule["contains_any"]):
                variant = dict(base)
                variant["system"] = rule["system"]
                variant["code"] = rule["code"]
                variant["description"] = rule["description"]
                if "product_rule" in rule:
                    variant["product_rule"] = rule["product_rule"]
                return variant
        return base

    def _finalize(
        self,
        *,
        input_item: str,
        normalized_item: str,
        canonical_item: str,
        nutrition_state: str,
        shopping_state: str,
        source_system: str | None,
        source_code: str | None,
        description: str | None,
        note: str | None,
        alias_evidence: str | None,
        proxy_target: dict[str, Any] | None,
        local_label_anchor: str | None,
        product_rule_id: str | None,
    ) -> Resolution:
        accepted: list[ProductCandidate] = []
        rejected: list[ProductCandidate] = []
        if product_rule_id:
            accepted, rejected = self.retrieve_products(product_rule_id)
            if not accepted and shopping_state == "shopping_candidates_strong":
                shopping_state = "shopping_gap"
        return Resolution(
            input_item=input_item,
            normalized_item=normalized_item,
            canonical_item=canonical_item,
            nutrition_state=nutrition_state,
            shopping_state=shopping_state,
            source_system=source_system,
            source_code=source_code,
            description=description,
            note=note,
            alias_evidence=alias_evidence,
            proxy_target=proxy_target,
            local_label_anchor=local_label_anchor,
            accepted_products=accepted,
            rejected_examples=rejected[:5],
        )

    def retrieve_products(self, rule_id: str, limit: int = 100) -> tuple[list[ProductCandidate], list[ProductCandidate]]:
        rule = registries.PRODUCT_RULES[rule_id]
        rows = self._fts_query(rule["query"], limit=limit)
        accepted: list[ProductCandidate] = []
        rejected: list[ProductCandidate] = []
        for row in rows:
            candidate = self._score_product(rule, row)
            if candidate.accepted:
                accepted.append(candidate)
            else:
                rejected.append(candidate)
        accepted.sort(key=lambda item: (-item.score, item.description))
        rejected.sort(key=lambda item: (-item.score, item.description))
        return accepted[:5], rejected[:10]

    def _fts_query(self, phrase: str, limit: int = 100) -> list[dict[str, Any]]:
        query = f'"{phrase}"'
        sql = """
            SELECT
                gtin_upc,
                description,
                brand_owner,
                brand_name,
                branded_food_category,
                serving_size,
                serving_size_unit,
                calories,
                protein_g,
                fat_g,
                carbs_g,
                sodium_mg
            FROM products
            WHERE rowid IN (
                SELECT rowid FROM products_fts WHERE products_fts MATCH ?
            )
            LIMIT ?
        """
        conn = sqlite3.connect(self.product_db_path)
        conn.row_factory = sqlite3.Row
        try:
            return [
                {
                    "gtin_upc": row["gtin_upc"],
                    "description": row["description"] or "",
                    "brand_owner": row["brand_owner"],
                    "brand_name": row["brand_name"],
                    "category": row["branded_food_category"] or "",
                    "serving_size": row["serving_size"],
                    "serving_size_unit": row["serving_size_unit"],
                    "calories": row["calories"],
                    "protein_g": row["protein_g"],
                    "fat_g": row["fat_g"],
                    "carbs_g": row["carbs_g"],
                    "sodium_mg": row["sodium_mg"],
                }
                for row in conn.execute(sql, (query, limit))
            ]
        finally:
            conn.close()

    def _score_product(
        self,
        rule: dict[str, Any],
        row: dict[str, Any],
    ) -> ProductCandidate:
        description = row["description"]
        category = row["category"]
        calories = row["calories"]
        description_norm = normalize_text(description)
        category_norm = category or ""
        category_ok = True
        if rule.get("allowed_categories"):
            category_ok = category_norm in rule["allowed_categories"]
        if not category_ok:
            return ProductCandidate(
                row["gtin_upc"],
                description,
                row["brand_owner"],
                row["brand_name"],
                category,
                row["serving_size"],
                row["serving_size_unit"],
                calories,
                row["protein_g"],
                row["fat_g"],
                row["carbs_g"],
                row["sodium_mg"],
                False,
                f"category_reject:{category_norm}",
                0.0,
            )

        for token in rule.get("forbidden_tokens", []):
            if token in description_norm:
                return ProductCandidate(
                    row["gtin_upc"],
                    description,
                    row["brand_owner"],
                    row["brand_name"],
                    category,
                    row["serving_size"],
                    row["serving_size_unit"],
                    calories,
                    row["protein_g"],
                    row["fat_g"],
                    row["carbs_g"],
                    row["sodium_mg"],
                    False,
                    f"forbidden_token:{token}",
                    0.0,
                )

        brand_norm = normalize_text(" ".join(part for part in [row["brand_owner"], row["brand_name"]] if part))
        for token in rule.get("forbidden_brand_tokens", []):
            if token in brand_norm:
                return ProductCandidate(
                    row["gtin_upc"],
                    description,
                    row["brand_owner"],
                    row["brand_name"],
                    category,
                    row["serving_size"],
                    row["serving_size_unit"],
                    calories,
                    row["protein_g"],
                    row["fat_g"],
                    row["carbs_g"],
                    row["sodium_mg"],
                    False,
                    f"forbidden_brand_token:{token}",
                    0.0,
                )

        required_all = rule.get("required_all", [])
        if required_all and not all(token in description_norm for token in required_all):
            return ProductCandidate(
                row["gtin_upc"],
                description,
                row["brand_owner"],
                row["brand_name"],
                category,
                row["serving_size"],
                row["serving_size_unit"],
                calories,
                row["protein_g"],
                row["fat_g"],
                row["carbs_g"],
                row["sodium_mg"],
                False,
                "missing_required_all",
                0.0,
            )

        required_any = rule.get("required_any", [])
        if required_any and not any(token in description_norm for token in required_any):
            return ProductCandidate(
                row["gtin_upc"],
                description,
                row["brand_owner"],
                row["brand_name"],
                category,
                row["serving_size"],
                row["serving_size_unit"],
                calories,
                row["protein_g"],
                row["fat_g"],
                row["carbs_g"],
                row["sodium_mg"],
                False,
                "missing_required_any",
                0.0,
            )

        score = 1.0
        query_norm = normalize_text(rule["query"])
        if description_norm == query_norm:
            score += 1.25
        elif description_norm.startswith(query_norm):
            score += 1.0
        preferred_any = rule.get("preferred_any", [])
        if preferred_any and any(token in description_norm for token in preferred_any):
            score += 0.75
        if category_norm in rule.get("allowed_categories", []):
            score += 0.5
        return ProductCandidate(
            row["gtin_upc"],
            description,
            row["brand_owner"],
            row["brand_name"],
            category,
            row["serving_size"],
            row["serving_size_unit"],
            calories,
            row["protein_g"],
            row["fat_g"],
            row["carbs_g"],
            row["sodium_mg"],
            True,
            "accepted",
            score,
        )


def resolution_to_json(resolution: Resolution) -> str:
    return json.dumps(resolution.to_dict(), indent=2, ensure_ascii=False)
