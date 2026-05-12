#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from build_recipe_purchase_verification_packet import build_records
from plan_verification_suite import RuleVerifier, VerificationClaim
from run_recipe_cost_smoke import (
    DEFAULT_RECIPE_QA_DB,
    DEFAULT_RECIPES_CSV,
    DEFAULT_RETAIL_BRIDGE_CSV,
    run_smoke,
)
from surface_lab_calculator import normalize_key


ROOT = Path(__file__).resolve().parent.parent
IMPLEMENTATION = ROOT / "implementation"
DEFAULT_Hestia_ROOT = Path("/Users/jamiebarton/Desktop/Hestia")
DEFAULT_OUTPUT_BASE = IMPLEMENTATION / "output" / "sparse_purchase_audit"
DEFAULT_KNOWN_RECIPE_IDS = ("506745",)


@dataclass(frozen=True)
class AuditConfig:
    config_id: str
    stores: list[str]
    scoring_preset: str = "thrifty"
    household_size: int = 4
    daily_calories: float = 2000.0
    daily_protein: float = 75.0
    leftover_target: float = 0.75
    allergen_exclusions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Blocker:
    blocker_id: str
    record_id: str
    plan_id: str
    config_id: str
    recipe_num: str
    recipe_name: str
    line_index: int
    store: str
    decision: str
    issue_type: str
    severity: str
    confidence: float
    reason: str
    suggested_fix: str
    original_recipe_text: str
    parsed_item: str
    normalized_shopping_item: str
    recipe_grams: float
    retail_purchase_grams: float
    nutrition_anchor: str
    shopping_state: str
    selected_product: str = ""
    selected_upc: str = ""
    package_grams: float = 0.0
    packages: int = 0
    checkout_usd: float = 0.0
    evidence: list[str] = field(default_factory=list)


DEFAULT_CONFIGS = [
    AuditConfig("walmart_budget_family", ["walmart"], scoring_preset="thrifty"),
    AuditConfig("kroger_budget_family", ["kroger"], scoring_preset="thrifty"),
    AuditConfig("two_store_best_price", ["walmart", "kroger"], scoring_preset="thrifty"),
    AuditConfig("fresh_heavy_family", ["walmart", "kroger"], scoring_preset="fresh_daily", leftover_target=0.25),
    AuditConfig("meat_heavy_family", ["walmart", "kroger"], scoring_preset="high_protein"),
    AuditConfig(
        "vegetarian_family",
        ["walmart", "kroger"],
        scoring_preset="balanced",
        allergen_exclusions=["beef", "pork", "chicken", "turkey", "fish", "shellfish"],
    ),
]

MEAT_TERMS = {
    "beef",
    "brisket",
    "bratwurst",
    "chicken",
    "hamburger",
    "ham",
    "lamb",
    "meat",
    "pork",
    "steak",
    "turkey",
    "veal",
}
PREPARED_LIQUID_TERMS = {"gravy", "sauce", "stock", "broth"}
DRY_FORM_TERMS = {"dry", "dried", "instant", "mix", "packet", "powder", "powdered"}
LOW_RISK_SEASONING_TERMS = {
    "cajun",
    "garlic",
    "mustard",
    "rub",
    "salt",
    "seasoned",
    "seasoning",
    "spice",
    "spices",
}
HIGH_RISK_TERMS = {
    "brisket",
    "cooked",
    "cookie",
    "cooky",
    "count",
    "dry",
    "egg",
    "gallon",
    "gravy",
    "ham",
    "lamb",
    "leftover",
    "mix",
    "packet",
    "pie filling",
    "stock",
    "veal",
}


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "detach"):
        return _json_ready(value.detach().cpu())
    if hasattr(value, "tolist"):
        return _json_ready(value.tolist())
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return str(value)


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _tokens(text: str) -> set[str]:
    return set(normalize_key(text).split())


def _has_any(text: str, terms: set[str]) -> bool:
    key = normalize_key(text)
    return any(term in key for term in terms)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = asdict(row) if hasattr(row, "__dataclass_fields__") else row
            handle.write(json.dumps(_json_ready(payload), sort_keys=True) + "\n")


def extract_recipe_ids_from_plan_result(result: dict[str, Any]) -> list[str]:
    for key in ("used_recipe_ids", "usedRecipeIds", "recipe_ids", "recipeIds"):
        values = result.get(key)
        if values:
            return _dedupe_recipe_ids(values)
    return _dedupe_recipe_ids(_recipe_ids_from_selections(result.get("selections") or []))


def _recipe_ids_from_selections(selections: list[Any]) -> list[int]:
    recipe_ids: list[int] = []
    for selection in selections:
        if not selection:
            continue
        if not isinstance(selection, (list, tuple)):
            continue
        candidates = [selection[0] if len(selection) > 0 else 0, selection[1] if len(selection) > 1 else 0]
        if len(selection) >= 10:
            candidates.append(selection[2])
        for candidate in candidates:
            recipe_id = _to_int(candidate)
            if recipe_id > 0:
                recipe_ids.append(recipe_id)
    return recipe_ids


def _dedupe_recipe_ids(values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        recipe_id = str(_to_int(value))
        if recipe_id != "0" and recipe_id not in seen:
            out.append(recipe_id)
            seen.add(recipe_id)
    return out


def serialize_selections(selections: list[Any]) -> list[dict[str, Any]]:
    meal_types = ["breakfast", "lunch", "dinner"]
    out: list[dict[str, Any]] = []
    for index, selection in enumerate(selections or []):
        if not isinstance(selection, (list, tuple)) or len(selection) < 5:
            continue
        if len(selection) >= 10:
            main_id, side_id, side2_id, main_name, side_name, side2_name, meal_cost = selection[:7]
        else:
            main_id, side_id, main_name, side_name, meal_cost = selection[:5]
            side2_id, side2_name = 0, ""
        out.append(
            {
                "slot": index,
                "day": index // 3 + 1,
                "meal": meal_types[index % 3],
                "main_recipe_id": _to_int(main_id),
                "side_recipe_id": _to_int(side_id),
                "side2_recipe_id": _to_int(side2_id),
                "main_name": str(main_name or ""),
                "side_name": str(side_name or ""),
                "side2_name": str(side2_name or ""),
                "meal_cost": _to_float(meal_cost),
            }
        )
    return out


def _import_hestia(hestia_root: Path) -> dict[str, Any]:
    api_path = hestia_root / "api"
    if not api_path.exists():
        raise FileNotFoundError(f"Hestia API path not found: {api_path}")
    api_path_str = str(api_path)
    if api_path_str not in sys.path:
        sys.path.insert(0, api_path_str)

    import torch
    from hestia.data_structures import AttendanceSchedule, HouseholdConfig, PackageIndex, PersonProfile
    from hestia.scoring_config import ScoringConfig
    from hestia.sparse_cascade import SparseCascadePlanner, SparseRecipeDatabase

    return {
        "torch": torch,
        "AttendanceSchedule": AttendanceSchedule,
        "HouseholdConfig": HouseholdConfig,
        "PackageIndex": PackageIndex,
        "PersonProfile": PersonProfile,
        "ScoringConfig": ScoringConfig,
        "SparseCascadePlanner": SparseCascadePlanner,
        "SparseRecipeDatabase": SparseRecipeDatabase,
    }


def _choose_device(torch: Any, requested: str) -> Any:
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _scoring_config(scoring_cls: Any, config: AuditConfig) -> Any:
    preset = config.scoring_preset
    if preset == "budget":
        return scoring_cls.budget()
    if preset == "balanced":
        return scoring_cls.balanced()
    if preset == "fresh_daily":
        return scoring_cls.fresh_daily()
    if preset == "high_protein":
        return scoring_cls.high_protein(25.0)
    return scoring_cls.thrifty()


def run_sparse_cascade_plans(
    *,
    hestia_root: Path,
    configs: list[AuditConfig],
    weeks: int,
    planner_k: int,
    device_name: str,
    verbose: bool,
) -> list[dict[str, Any]]:
    hestia = _import_hestia(hestia_root)
    torch = hestia["torch"]
    device = _choose_device(torch, device_name)

    recipe_db = hestia["SparseRecipeDatabase"].from_cache(device)
    package_index = hestia["PackageIndex"]()
    package_index.build_gpu_tensors(recipe_db.ingredient_index, device)

    plan_runs: list[dict[str, Any]] = []
    for config in configs:
        people = [
            hestia["PersonProfile"](f"Person {index + 1}", config.daily_calories, config.daily_protein)
            for index in range(config.household_size)
        ]
        household = hestia["HouseholdConfig"](people=people)
        schedule = hestia["AttendanceSchedule"](household)
        scoring_config = _scoring_config(hestia["ScoringConfig"], config)
        planner = hestia["SparseCascadePlanner"](
            recipe_db=recipe_db,
            package_index=package_index,
            device=device,
            attendance_schedule=schedule,
            scoring_config=scoring_config,
            weekly_calories=config.daily_calories * config.household_size * 7,
            weekly_protein=config.daily_protein * config.household_size * 7,
            leftover_target=config.leftover_target,
            allergen_exclusions=config.allergen_exclusions,
            K=planner_k,
            verbose=verbose,
        )
        session = planner.start_session()
        for week in range(1, weeks + 1):
            started = time.time()
            result = session.plan_next_week()
            elapsed = time.time() - started
            recipe_ids = extract_recipe_ids_from_plan_result(result)
            plan_id = f"sparse_{config.config_id}_w{week:02d}"
            plan_runs.append(
                {
                    "plan_id": plan_id,
                    "source": "sparse_cascade",
                    "config_id": config.config_id,
                    "stores": config.stores,
                    "week": week,
                    "used_recipe_ids": recipe_ids,
                    "recipe_count": len(recipe_ids),
                    "total_cost": _to_float(result.get("total_cost")),
                    "cal_compliance": _to_float(result.get("cal_compliance")),
                    "prot_compliance": _to_float(result.get("prot_compliance")),
                    "elapsed_seconds": elapsed,
                    "planner_elapsed_seconds": _to_float(result.get("elapsed_seconds")),
                    "pantry_flow": _json_ready(result.get("pantry_flow") or {}),
                    "leftover_stats": _json_ready(result.get("leftover_stats") or {}),
                    "selections": serialize_selections(result.get("selections") or []),
                }
            )
    return plan_runs


def recipe_smoke_plan(recipe_ids: list[str]) -> dict[str, Any]:
    return {
        "plan_id": "recipe_smoke_known_blockers",
        "source": "recipe_smoke",
        "config_id": "recipe_smoke",
        "stores": ["walmart", "kroger"],
        "week": 0,
        "used_recipe_ids": _dedupe_recipe_ids(recipe_ids),
        "recipe_count": len(_dedupe_recipe_ids(recipe_ids)),
        "total_cost": 0.0,
        "cal_compliance": 0.0,
        "prot_compliance": 0.0,
        "elapsed_seconds": 0.0,
        "selections": [],
    }


def collect_recipe_ids(plan_runs: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for plan in plan_runs:
        ids.extend(str(recipe_id) for recipe_id in plan.get("used_recipe_ids") or [])
    return _dedupe_recipe_ids(ids)


def build_purchase_records(
    *,
    plan_runs: list[dict[str, Any]],
    report: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    base_records = build_records(report)
    records_by_recipe: dict[str, list[dict[str, Any]]] = {}
    for record in base_records:
        recipe_num = str(record.get("recipe", {}).get("recipe_num") or "")
        records_by_recipe.setdefault(recipe_num, []).append(record)

    out: list[dict[str, Any]] = []
    missing_by_plan: dict[str, list[str]] = {}
    for plan in plan_runs:
        plan_id = str(plan.get("plan_id") or "")
        missing: list[str] = []
        for recipe_id in plan.get("used_recipe_ids") or []:
            recipe_records = records_by_recipe.get(str(recipe_id))
            if not recipe_records:
                missing.append(str(recipe_id))
                continue
            for base_record in recipe_records:
                record = json.loads(json.dumps(base_record))
                source_record_id = str(record.get("record_id") or "")
                record["source_record_id"] = source_record_id
                record["record_id"] = f"{plan_id}:{source_record_id}"
                record["plan"] = {
                    "plan_id": plan_id,
                    "source": plan.get("source") or "",
                    "config_id": plan.get("config_id") or "",
                    "stores": plan.get("stores") or ["walmart", "kroger"],
                    "week": plan.get("week", 0),
                }
                out.append(record)
        if missing:
            missing_by_plan[plan_id] = missing
    return out, missing_by_plan


def _nutrition_anchor_text(record: dict[str, Any]) -> str:
    anchor = record.get("calculator", {}).get("nutrition_anchor") or {}
    source = str(anchor.get("source") or "")
    code = str(anchor.get("code") or "")
    desc = str(anchor.get("description") or "")
    if source and code:
        return f"{source}:{code} {desc}".strip()
    return ""


def _line_store_checks(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(check.get("store") or ""): check
        for check in record.get("store_checks") or []
        if isinstance(check, dict)
    }


def _selected_product(check: dict[str, Any] | None) -> dict[str, Any]:
    selected = (check or {}).get("selected")
    return selected if isinstance(selected, dict) else {}


def issue_bucket(blocker: Blocker) -> str:
    if blocker.issue_type == "bad_recipe_or_unshoppable":
        return "recipe_scrub"
    if blocker.issue_type == "seasoning_nutrition_gap":
        return "low_risk_nutrition_gap"
    if blocker.issue_type in {"catalog_gap", "shopping_gap"}:
        return "store_or_catalog_gap"
    if blocker.issue_type == "wrong_form_candidate" and blocker.store == "recipe":
        return "source_normalization_warning"
    if blocker.issue_type == "wrong_form" and "Bologna roll target" in blocker.reason:
        return "manual_substitution_or_scrub"
    if blocker.issue_type in {
        "bad_package_math",
        "nutrition_missing_or_wrong_anchor",
        "wrong_fndds",
        "wrong_form",
        "wrong_store_item",
    }:
        return "hard_cart_blocker"
    if blocker.issue_type == "wrong_form_candidate":
        return "hard_cart_blocker"
    return "needs_review"


def is_hard_cart_blocker(blocker: Blocker) -> bool:
    return issue_bucket(blocker) == "hard_cart_blocker"


def _audit_verdict_severity(record: dict[str, Any], verdict: Any) -> tuple[str, str]:
    recipe = record.get("recipe") or {}
    ingredient = record.get("ingredient") or {}
    original = normalize_key(str(ingredient.get("original_recipe_text") or ""))
    recipe_text = normalize_key(" ".join([str(recipe.get("recipe_name") or ""), original]))
    if (
        verdict.issue_type == "wrong_form"
        and "bologna" in recipe_text
        and "roll" in recipe_text
        and "Bologna roll target" in verdict.reason
    ):
        return "needs_human", "warning"
    return verdict.decision, verdict.severity


def _is_low_risk_seasoning_nutrition_gap(
    *,
    original_tokens: set[str],
    target_tokens: set[str],
    retail_purchase_grams: float,
) -> bool:
    tokens = original_tokens | target_tokens
    if not (tokens & LOW_RISK_SEASONING_TERMS):
        return False
    if tokens & {"beverage", "drink", "kool", "koolaid", "oatmeal"}:
        return False
    return retail_purchase_grams <= 120.0


def _blocker(
    *,
    record: dict[str, Any],
    store: str,
    decision: str,
    issue_type: str,
    severity: str,
    confidence: float,
    reason: str,
    suggested_fix: str,
    evidence: list[str] | None = None,
) -> Blocker:
    plan = record.get("plan") or {}
    recipe = record.get("recipe") or {}
    ingredient = record.get("ingredient") or {}
    calculator = record.get("calculator") or {}
    selected = _selected_product(_line_store_checks(record).get(store))
    blocker_id = f"{record.get('record_id')}:{store}:{issue_type}"
    return Blocker(
        blocker_id=blocker_id,
        record_id=str(record.get("record_id") or ""),
        plan_id=str(plan.get("plan_id") or ""),
        config_id=str(plan.get("config_id") or ""),
        recipe_num=str(recipe.get("recipe_num") or ""),
        recipe_name=str(recipe.get("recipe_name") or ""),
        line_index=_to_int(recipe.get("line_index")),
        store=store,
        decision=decision,
        issue_type=issue_type,
        severity=severity,
        confidence=confidence,
        reason=reason,
        suggested_fix=suggested_fix,
        original_recipe_text=str(ingredient.get("original_recipe_text") or ""),
        parsed_item=str(ingredient.get("parsed_item") or ""),
        normalized_shopping_item=str(ingredient.get("normalized_shopping_item") or ""),
        recipe_grams=_to_float(ingredient.get("recipe_grams")),
        retail_purchase_grams=_to_float(ingredient.get("retail_purchase_grams")),
        nutrition_anchor=_nutrition_anchor_text(record),
        shopping_state=str(calculator.get("shopping_state") or ""),
        selected_product=str(selected.get("name") or ""),
        selected_upc=str(selected.get("upc") or ""),
        package_grams=_to_float(selected.get("package_grams")),
        packages=_to_int(selected.get("packages")),
        checkout_usd=_to_float(selected.get("checkout_usd")),
        evidence=evidence or [],
    )


def _claim_from_record(record: dict[str, Any], store: str, check: dict[str, Any]) -> VerificationClaim:
    recipe = record.get("recipe") or {}
    ingredient = record.get("ingredient") or {}
    calculator = record.get("calculator") or {}
    selected = _selected_product(check)
    nutrition_anchor = calculator.get("nutrition_anchor") or {}
    source = str(nutrition_anchor.get("source") or "")
    code = str(nutrition_anchor.get("code") or "")
    nutrition_key = f"{source}:{code}" if source and code else ""
    return VerificationClaim(
        claim_id=f"{record.get('record_id')}:{store}",
        plan_id=str((record.get("plan") or {}).get("plan_id") or ""),
        config_id=str((record.get("plan") or {}).get("config_id") or ""),
        recipe_num=str(recipe.get("recipe_num") or ""),
        recipe_name=str(recipe.get("recipe_name") or ""),
        line_index=_to_int(recipe.get("line_index")),
        store=store,
        ingredient_label=str(ingredient.get("original_recipe_text") or ingredient.get("parsed_item") or ""),
        grams_needed=_to_float(ingredient.get("retail_purchase_grams") or ingredient.get("recipe_grams")),
        canonical_name=str(calculator.get("canonical_name") or ""),
        shopping_canonical=str(calculator.get("shopping_canonical") or ""),
        nutrition_key=nutrition_key,
        nutrition_state=str(calculator.get("nutrition_state") or ""),
        nutrition_source=str(calculator.get("nutrition_source") or ""),
        esha_code=str(calculator.get("esha_code") or ""),
        esha_description=str(calculator.get("esha_description") or ""),
        sr28_fdc_id=str(calculator.get("sr28_fdc_id") or ""),
        fndds_code=str(calculator.get("fndds_code") or ""),
        fndds_description=str(nutrition_anchor.get("description") or calculator.get("esha_description") or ""),
        shopping_state=str(calculator.get("shopping_state") or ""),
        product_name=str(selected.get("name") or ""),
        product_upc=str(selected.get("upc") or ""),
        package_grams=_to_float(selected.get("package_grams")),
        package_price_usd=_to_float(selected.get("package_usd")),
        packages_to_buy=_to_int(selected.get("packages")),
        checkout_usd=_to_float(selected.get("checkout_usd")),
        used_usd=_to_float(selected.get("used_usd")),
        product_search_term=str(selected.get("search_term") or ""),
        product_canonical_surface=str(selected.get("canonical_surface") or ""),
        product_canonical_shopping_item=str(selected.get("canonical_shopping_item") or ""),
        decision_reason=str(selected.get("decision_reason") or ""),
        path=[str(item) for item in calculator.get("path") or []],
    )


def classify_record_blockers(record: dict[str, Any], verifier: RuleVerifier | None = None) -> list[Blocker]:
    verifier = verifier or RuleVerifier()
    blockers: list[Blocker] = []
    plan = record.get("plan") or {}
    stores = [str(store) for store in (plan.get("stores") or ["walmart", "kroger"])]
    ingredient = record.get("ingredient") or {}
    calculator = record.get("calculator") or {}
    original = str(ingredient.get("original_recipe_text") or "")
    parsed = str(ingredient.get("parsed_item") or "")
    normalized = str(ingredient.get("normalized_shopping_item") or "")
    target = " ".join([original, parsed, str(calculator.get("shopping_canonical") or calculator.get("canonical_name") or "")])
    target_key = normalize_key(target)
    normalized_key = normalize_key(normalized)
    original_tokens = _tokens(original)
    target_tokens = _tokens(target)
    shopping_state = str(calculator.get("shopping_state") or "")
    nutrition_state = str(calculator.get("nutrition_state") or "")
    retail_purchase_grams = _to_float(ingredient.get("retail_purchase_grams") or ingredient.get("recipe_grams"))

    if (
        _has_any(target_key, PREPARED_LIQUID_TERMS)
        and _has_any(normalized_key, DRY_FORM_TERMS)
        and not (original_tokens & DRY_FORM_TERMS)
    ):
        blockers.append(
            _blocker(
                record=record,
                store="recipe",
                decision="needs_human",
                issue_type="wrong_form_candidate",
                severity="warning",
                confidence=0.92,
                reason="Normalized shopping item is dry/instant, but the original recipe asks for a prepared liquid ingredient.",
                suggested_fix="Repair the normalized recipe item to the prepared/liquid form.",
                evidence=[original, normalized],
            )
        )

    if (
        "gallon" in original_tokens or "gallons" in original_tokens
    ) and target_tokens & MEAT_TERMS and not (target_tokens & PREPARED_LIQUID_TERMS):
        blockers.append(
            _blocker(
                record=record,
                store="recipe",
                decision="needs_human",
                issue_type="bad_recipe_or_unshoppable",
                severity="warning",
                confidence=0.88,
                reason="Recipe measures meat by volume, which is fragile for grocery conversion and customer buying.",
                suggested_fix="Review recipe quantity normalization or scrub the recipe if no defensible retail conversion exists.",
                evidence=[original, parsed],
            )
        )

    if shopping_state in {"not_purchased", "non_food"} or nutrition_state == "non_food":
        return blockers

    nutrition_anchor = _nutrition_anchor_text(record)
    nutrition_missing = not nutrition_anchor or nutrition_state == "nutrition_unknown"
    if nutrition_missing:
        if _is_low_risk_seasoning_nutrition_gap(
            original_tokens=original_tokens,
            target_tokens=target_tokens,
            retail_purchase_grams=retail_purchase_grams,
        ):
            blockers.append(
                _blocker(
                    record=record,
                    store="nutrition",
                    decision="needs_human",
                    issue_type="seasoning_nutrition_gap",
                    severity="warning",
                    confidence=0.85,
                    reason="Low-quantity seasoning has no verified nutrition anchor; this is not a customer cart blocker.",
                    suggested_fix="Add a reviewed seasoning nutrition proxy, but do not block customer purchase validation on this line.",
                    evidence=[original, nutrition_state],
                )
            )
        else:
            blockers.append(
                _blocker(
                    record=record,
                    store="nutrition",
                    decision="reject",
                    issue_type="nutrition_missing_or_wrong_anchor",
                    severity="blocker",
                    confidence=1.0,
                    reason="Ingredient has no verified nutrition anchor.",
                    suggested_fix="Add or repair ESHA/SR28/FNDDS nutrition mapping.",
                    evidence=[original, nutrition_state],
                )
            )

    checks = _line_store_checks(record)
    any_selected = any(_selected_product(check) for check in checks.values())

    for store in stores:
        check = checks.get(store) or {"store": store, "selected": None, "status": "missing"}
        selected = _selected_product(check)
        if shopping_state == "shopping_gap":
            blockers.append(
                _blocker(
                    record=record,
                    store=store,
                    decision="needs_human",
                    issue_type="shopping_gap",
                    severity="warning",
                    confidence=1.0,
                    reason="Calculator could not find a reasonable shopping candidate.",
                    suggested_fix="Repair product lookup, add a store bridge item, or mark the recipe unshoppable for this store.",
                    evidence=[original, str(calculator.get("shopping_canonical") or "")],
                )
            )
            continue

        if not selected:
            blockers.append(
                _blocker(
                    record=record,
                    store=store,
                    decision="needs_human",
                    issue_type="catalog_gap",
                    severity="warning",
                    confidence=0.95,
                    reason="No priced item was selected for this store.",
                    suggested_fix="Repair this store's retail bridge or route the plan to a store with coverage.",
                    evidence=[original, store],
                )
            )
            continue

        if nutrition_missing:
            continue

        product_key = normalize_key(str(selected.get("name") or ""))
        if (
            _has_any(target_key, PREPARED_LIQUID_TERMS)
            and _has_any(product_key, DRY_FORM_TERMS)
            and not (original_tokens & DRY_FORM_TERMS)
        ):
            blockers.append(
                _blocker(
                    record=record,
                    store=store,
                    decision="reject",
                    issue_type="wrong_form_candidate",
                    severity="blocker",
                    confidence=0.99,
                    reason="Prepared liquid ingredient is matched to a dry mix/powder/packet product.",
                    suggested_fix="Block dry mix products unless the original ingredient explicitly asks for dry mix.",
                    evidence=[original, str(selected.get("name") or "")],
                )
            )
            continue

        verdict = verifier.verify(_claim_from_record(record, store, check))
        if verdict.decision != "accept":
            decision, severity = _audit_verdict_severity(record, verdict)
            blockers.append(
                _blocker(
                    record=record,
                    store=store,
                    decision=decision,
                    issue_type=verdict.issue_type,
                    severity=severity,
                    confidence=verdict.confidence,
                    reason=verdict.reason,
                    suggested_fix=verdict.suggested_fix,
                    evidence=verdict.evidence,
                )
            )
    return blockers


def classify_records(records: list[dict[str, Any]]) -> list[Blocker]:
    verifier = RuleVerifier()
    blockers: list[Blocker] = []
    for record in records:
        blockers.extend(classify_record_blockers(record, verifier=verifier))
    return blockers


def write_blocker_queue(path: Path, blockers: list[Blocker]) -> None:
    fields = list(Blocker.__dataclass_fields__.keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for blocker in blockers:
            row = asdict(blocker)
            row["evidence"] = json.dumps(row["evidence"], sort_keys=True)
            writer.writerow(row)


def write_recipe_action_queue(path: Path, blockers: list[Blocker]) -> None:
    fields = [
        "recipe_num",
        "recipe_name",
        "action",
        "issue_count",
        "issue_types",
        "stores",
        "example_ingredients",
        "reason",
    ]
    by_recipe: dict[tuple[str, str], list[Blocker]] = {}
    for blocker in blockers:
        by_recipe.setdefault((blocker.recipe_num, blocker.recipe_name), []).append(blocker)
    rows: list[dict[str, str]] = []
    for (recipe_num, recipe_name), recipe_blockers in sorted(by_recipe.items()):
        buckets = {issue_bucket(blocker) for blocker in recipe_blockers}
        issue_types = sorted({blocker.issue_type for blocker in recipe_blockers})
        stores = sorted({blocker.store for blocker in recipe_blockers if blocker.store not in {"recipe", "nutrition"}})
        examples = []
        for blocker in recipe_blockers:
            if blocker.original_recipe_text and blocker.original_recipe_text not in examples:
                examples.append(blocker.original_recipe_text)
        if "hard_cart_blocker" in buckets:
            action = "fix_cart_blocker"
            reason = "Selected item, nutrition anchor, or package math is unsafe."
        elif "recipe_scrub" in buckets:
            action = "scrub_or_repair_recipe"
            reason = "Recipe text has non-defensible grocery conversion, such as meat measured by volume."
        elif "manual_substitution_or_scrub" in buckets:
            action = "manual_substitution_or_scrub"
            reason = "Recipe requires a retail form that the store candidates do not provide."
        elif "store_or_catalog_gap" in buckets:
            action = "route_store_or_seed_catalog"
            reason = "Ingredient has no priced item for at least one requested store."
        elif "source_normalization_warning" in buckets:
            action = "repair_source_normalization"
            reason = "Source normalized item disagrees with original recipe text, but selected products may still be safe."
        elif "low_risk_nutrition_gap" in buckets:
            action = "add_optional_nutrition_proxy"
            reason = "Low-quantity seasoning needs a reviewed nutrition proxy, but it is not a cart blocker."
        else:
            action = "review"
            reason = "Issue needs review but is not classified as a hard cart blocker."
        rows.append(
            {
                "recipe_num": recipe_num,
                "recipe_name": recipe_name,
                "action": action,
                "issue_count": str(len(recipe_blockers)),
                "issue_types": ";".join(issue_types),
                "stores": ";".join(stores),
                "example_ingredients": " | ".join(examples[:5]),
                "reason": reason,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _record_hash(record: dict[str, Any]) -> str:
    payload = {
        "recipe": record.get("recipe"),
        "ingredient": record.get("ingredient"),
        "calculator": record.get("calculator"),
        "store_checks": record.get("store_checks"),
        "accepted_examples": record.get("accepted_examples"),
        "rejected_examples": record.get("rejected_examples"),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def select_deepseek_candidates(
    records: list[dict[str, Any]],
    blockers: list[Blocker],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    blocked_record_ids = {blocker.record_id for blocker in blockers}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(record: dict[str, Any]) -> None:
        record_id = str(record.get("record_id") or "")
        if record_id and record_id not in seen:
            selected.append(record)
            seen.add(record_id)

    for record in records:
        if str(record.get("record_id") or "") in blocked_record_ids:
            add(record)
    for record in records:
        text = json.dumps(
            {
                "ingredient": record.get("ingredient"),
                "calculator": record.get("calculator"),
                "store_checks": record.get("store_checks"),
                "rejected_examples": record.get("rejected_examples"),
            },
            sort_keys=True,
        )
        if _has_any(text, HIGH_RISK_TERMS):
            add(record)
    return selected[:limit] if limit > 0 else selected


def _load_deepseek_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    cache: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = str(row.get("cache_key") or "")
            if key:
                cache[key] = row
    return cache


def _append_deepseek_cache(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_ready(row), sort_keys=True) + "\n")


def verify_with_deepseek(
    records: list[dict[str, Any]],
    *,
    cache_path: Path,
    out_path: Path,
    model: str,
    base_url: str,
    timeout_s: int,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY is required when --mode uses DeepSeek")
    base_url = base_url.rstrip("/")
    cache = _load_deepseek_cache(cache_path)
    verdicts: list[dict[str, Any]] = []
    for record in records:
        cache_key = _record_hash(record)
        if cache_key in cache:
            cached = dict(cache[cache_key])
            cached["cache_hit"] = True
            cached["record_id"] = record.get("record_id")
            verdicts.append(cached)
            continue
        payload = {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You verify grocery purchases for recipe meal plans. Compare original recipe text, "
                        "calculator target, nutrition anchor, store products, package math, accepted examples, "
                        "and rejected examples. Return strict JSON with keys: decision accept|reject|needs_review, "
                        "issue_type ok|wrong_target|wrong_nutrition|wrong_store_item|wrong_form|shopping_gap|"
                        "bad_grams|bad_package_math|bad_recipe_or_unshoppable|catalog_gap, confidence 0-1, "
                        "reason, fix. Be conservative and ground every reason in the provided fields."
                    ),
                },
                {"role": "user", "content": json.dumps(_json_ready(record), sort_keys=True)},
            ],
        }
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        verdict = json.loads(content)
        row = {
            "cache_key": cache_key,
            "record_id": record.get("record_id"),
            "verifier": "deepseek",
            "model": model,
            "cache_hit": False,
            "verdict": verdict,
        }
        cache[cache_key] = row
        verdicts.append(row)
        _append_deepseek_cache(cache_path, row)
    _write_jsonl(out_path, verdicts)
    return verdicts


def summarize_run(
    *,
    out_dir: Path,
    plan_runs: list[dict[str, Any]],
    purchase_records: list[dict[str, Any]],
    blockers: list[Blocker],
    missing_by_plan: dict[str, list[str]],
    deepseek_candidates: list[dict[str, Any]],
    deepseek_verdicts: list[dict[str, Any]],
) -> dict[str, Any]:
    issue_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    bucket_counts: dict[str, int] = {}
    hard_blockers = [blocker for blocker in blockers if is_hard_cart_blocker(blocker)]
    hard_issue_counts: dict[str, int] = {}
    for blocker in blockers:
        issue_counts[blocker.issue_type] = issue_counts.get(blocker.issue_type, 0) + 1
        severity_counts[blocker.severity] = severity_counts.get(blocker.severity, 0) + 1
        bucket = issue_bucket(blocker)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    for blocker in hard_blockers:
        hard_issue_counts[blocker.issue_type] = hard_issue_counts.get(blocker.issue_type, 0) + 1
    return {
        "out_dir": str(out_dir),
        "plans": len(plan_runs),
        "sparse_plans": sum(1 for plan in plan_runs if plan.get("source") == "sparse_cascade"),
        "unique_plan_recipes": len(set(collect_recipe_ids(plan_runs))),
        "purchase_lines": len(purchase_records),
        "blockers": len(hard_blockers),
        "total_issues": len(blockers),
        "move_on_issues": len(blockers) - len(hard_blockers),
        "issue_counts": issue_counts,
        "hard_issue_counts": hard_issue_counts,
        "bucket_counts": bucket_counts,
        "severity_counts": severity_counts,
        "missing_recipes_by_plan": missing_by_plan,
        "deepseek_candidates": len(deepseek_candidates),
        "deepseek_verdicts": len(deepseek_verdicts),
    }


def write_summary_markdown(path: Path, summary: dict[str, Any], blockers: list[Blocker]) -> None:
    hard_blockers = [blocker for blocker in blockers if is_hard_cart_blocker(blocker)]
    triage = [blocker for blocker in blockers if not is_hard_cart_blocker(blocker)]
    lines = [
        "# Sparse Purchase Audit",
        "",
        f"- plans: `{summary['plans']}`",
        f"- sparse plans: `{summary['sparse_plans']}`",
        f"- unique plan recipes: `{summary['unique_plan_recipes']}`",
        f"- purchase lines: `{summary['purchase_lines']}`",
        f"- hard cart blockers: `{summary['blockers']}`",
        f"- triage / move-on issues: `{summary['move_on_issues']}`",
        f"- total issues: `{summary['total_issues']}`",
        f"- deepseek candidates: `{summary['deepseek_candidates']}`",
        f"- deepseek verdicts: `{summary['deepseek_verdicts']}`",
        "",
        "## Issue Counts",
        "",
    ]
    for issue, count in sorted(summary["issue_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{issue}`: {count}")
    lines.extend(["", "## Bucket Counts", ""])
    for bucket, count in sorted(summary["bucket_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{bucket}`: {count}")
    lines.extend(["", "## Hard Cart Blockers", ""])
    if not hard_blockers:
        lines.append("- none")
    for blocker in hard_blockers[:30]:
        lines.append(
            f"- `{blocker.issue_type}` `{blocker.recipe_num}` `{blocker.original_recipe_text}` "
            f"[{blocker.store}] -> `{blocker.selected_product or 'no product'}`: {blocker.reason}"
        )
    lines.extend(["", "## Triage / Move-On Issues", ""])
    if not triage:
        lines.append("- none")
    for blocker in triage[:30]:
        lines.append(
            f"- `{issue_bucket(blocker)}` `{blocker.issue_type}` `{blocker.recipe_num}` `{blocker.original_recipe_text}` "
            f"[{blocker.store}] -> `{blocker.selected_product or 'no product'}`: {blocker.reason}"
        )
    if summary["missing_recipes_by_plan"]:
        lines.extend(["", "## Missing Recipe Reports", ""])
        for plan_id, recipe_ids in summary["missing_recipes_by_plan"].items():
            lines.append(f"- `{plan_id}`: {', '.join(recipe_ids[:25])}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _select_configs(config_ids: list[str] | None, max_configs: int) -> list[AuditConfig]:
    configs = DEFAULT_CONFIGS
    if config_ids:
        wanted = set(config_ids)
        configs = [config for config in configs if config.config_id in wanted]
        missing = sorted(wanted - {config.config_id for config in configs})
        if missing:
            raise ValueError(f"Unknown config_id(s): {', '.join(missing)}")
    if max_configs > 0:
        configs = configs[:max_configs]
    return configs


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Sparse Cascade plans and audit the resulting grocery purchases.")
    parser.add_argument("--hestia-root", type=Path, default=DEFAULT_Hestia_ROOT)
    parser.add_argument("--recipes-csv", type=Path, default=DEFAULT_RECIPES_CSV)
    parser.add_argument("--recipe-qa-db", type=Path, default=DEFAULT_RECIPE_QA_DB)
    parser.add_argument("--retail-bridge-csv", type=Path, default=DEFAULT_RETAIL_BRIDGE_CSV)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--config-id", action="append", dest="config_ids")
    parser.add_argument("--max-configs", type=int, default=1)
    parser.add_argument("--weeks", type=int, default=1)
    parser.add_argument("--planner-k", type=int, default=20)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--include-recipe-id", action="append", dest="include_recipe_ids")
    parser.add_argument("--no-known-recipe-smoke", action="store_true")
    parser.add_argument("--skip-sparse", action="store_true")
    parser.add_argument("--buy-water", action="store_true")
    parser.add_argument("--mode", choices=["rules", "deepseek", "both"], default="rules")
    parser.add_argument("--deepseek-limit", type=int, default=100)
    parser.add_argument("--deepseek-model", default="deepseek-chat")
    parser.add_argument("--deepseek-base-url", default="https://api.deepseek.com")
    parser.add_argument("--deepseek-timeout-s", type=int, default=60)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir or (DEFAULT_OUTPUT_BASE / run_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    include_recipe_ids = list(args.include_recipe_ids or [])
    if not args.no_known_recipe_smoke:
        include_recipe_ids = list(DEFAULT_KNOWN_RECIPE_IDS) + include_recipe_ids
    include_recipe_ids = _dedupe_recipe_ids(include_recipe_ids)

    plan_runs: list[dict[str, Any]] = []
    if include_recipe_ids:
        plan_runs.append(recipe_smoke_plan(include_recipe_ids))
    if not args.skip_sparse:
        configs = _select_configs(args.config_ids, args.max_configs)
        plan_runs.extend(
            run_sparse_cascade_plans(
                hestia_root=args.hestia_root,
                configs=configs,
                weeks=max(1, args.weeks),
                planner_k=args.planner_k,
                device_name=args.device,
                verbose=args.verbose,
            )
        )
    if not plan_runs:
        raise SystemExit("No plan runs requested. Remove --skip-sparse or include at least one recipe id.")

    recipe_ids = collect_recipe_ids(plan_runs)
    if not recipe_ids:
        raise SystemExit("No recipe IDs were produced by the requested plan runs.")

    report = run_smoke(
        recipes_csv=args.recipes_csv,
        recipe_qa_db=args.recipe_qa_db,
        surface_csv=None,
        product_esha_map_csv=None,
        retail_bridge_csv=args.retail_bridge_csv,
        recipe_ids=recipe_ids,
        max_recipes=len(recipe_ids),
        buy_water=args.buy_water,
    )
    purchase_records, missing_by_plan = build_purchase_records(plan_runs=plan_runs, report=report)
    issues = classify_records(purchase_records)
    hard_blockers = [blocker for blocker in issues if is_hard_cart_blocker(blocker)]
    triage_issues = [blocker for blocker in issues if not is_hard_cart_blocker(blocker)]

    _write_jsonl(out_dir / "plan_runs.jsonl", plan_runs)
    _write_json(out_dir / "recipe_purchase_report.json", report)
    _write_jsonl(out_dir / "recipe_purchase_reports.jsonl", report.get("recipes") or [])
    _write_jsonl(out_dir / "purchase_lines.jsonl", purchase_records)
    _write_jsonl(out_dir / "verification_packets.jsonl", purchase_records)
    write_blocker_queue(out_dir / "issue_queue.csv", issues)
    write_blocker_queue(out_dir / "blocker_queue.csv", hard_blockers)
    write_blocker_queue(out_dir / "triage_queue.csv", triage_issues)
    write_recipe_action_queue(out_dir / "recipe_action_queue.csv", issues)

    deepseek_candidates: list[dict[str, Any]] = []
    deepseek_verdicts: list[dict[str, Any]] = []
    if args.mode in {"deepseek", "both"}:
        deepseek_candidates = select_deepseek_candidates(purchase_records, hard_blockers, limit=args.deepseek_limit)
        _write_jsonl(out_dir / "deepseek_candidates.jsonl", deepseek_candidates)
        deepseek_verdicts = verify_with_deepseek(
            deepseek_candidates,
            cache_path=DEFAULT_OUTPUT_BASE / "deepseek_cache.jsonl",
            out_path=out_dir / "deepseek_verdicts.jsonl",
            model=args.deepseek_model,
            base_url=args.deepseek_base_url,
            timeout_s=args.deepseek_timeout_s,
        )
    elif args.mode == "rules":
        deepseek_candidates = select_deepseek_candidates(purchase_records, hard_blockers, limit=args.deepseek_limit)
        _write_jsonl(out_dir / "deepseek_candidates.dryrun.jsonl", deepseek_candidates)

    summary = summarize_run(
        out_dir=out_dir,
        plan_runs=plan_runs,
        purchase_records=purchase_records,
        blockers=issues,
        missing_by_plan=missing_by_plan,
        deepseek_candidates=deepseek_candidates,
        deepseek_verdicts=deepseek_verdicts,
    )
    _write_json(out_dir / "summary.json", summary)
    write_summary_markdown(out_dir / "summary.md", summary, issues)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
