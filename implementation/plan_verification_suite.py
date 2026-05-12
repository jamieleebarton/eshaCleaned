#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import surface_lab_calculator as lab_sources
from run_recipe_cost_smoke import (
    DEFAULT_RETAIL_BRIDGE_CSV,
    DEFAULT_RECIPES_CSV,
    NO_PURCHASE_KEYS,
    _best_offer,
    _load_retail_offers,
    _parse_shopping_items,
)
from surface_lab_calculator import calculate_lab, configure_data_sources, normalize_key


ROOT = Path(__file__).resolve().parent.parent
IMPLEMENTATION = ROOT / "implementation"
DEFAULT_OUT_DIR = IMPLEMENTATION / "output" / "plan_verification_suite"
FNDDS_MAIN_FOOD_DESC_CSV = ROOT / "data" / "fndds" / "MainFoodDesc16.csv"

DEFAULT_CONFIGS = [
    {"config_id": "walmart_budget_family", "stores": ["walmart"], "mode": "budget", "servings": 4},
    {"config_id": "kroger_budget_family", "stores": ["kroger"], "mode": "budget", "servings": 4},
    {"config_id": "two_store_best_price", "stores": ["walmart", "kroger"], "mode": "best_price", "servings": 4},
    {"config_id": "fresh_heavy_family", "stores": ["walmart", "kroger"], "mode": "fresh_heavy", "servings": 4},
    {"config_id": "pantry_heavy_budget", "stores": ["walmart", "kroger"], "mode": "pantry_heavy", "servings": 4},
    {"config_id": "meat_heavy_family", "stores": ["walmart", "kroger"], "mode": "meat_heavy", "servings": 4},
    {"config_id": "vegetarian_family", "stores": ["walmart", "kroger"], "mode": "vegetarian", "servings": 4},
]

RISK_TERMS = {
    "meat_cut": [
        "ham",
        "ham hock",
        "ham bone",
        "ham steak",
        "pork shoulder",
        "pork butt",
        "pork chop",
        "roast",
        "steak",
        "whole chicken",
        "chicken breast",
        "turkey",
        "deli",
        "lunchmeat",
    ],
    "package_math": [
        "egg",
        "eggs",
        "dozen",
        "count",
        "package",
        "pkg",
        "slice",
        "slices",
        "can",
        "cans",
        "jar",
        "bottle",
    ],
    "form_sensitive": [
        "fresh",
        "frozen",
        "canned",
        "dried",
        "raw",
        "cooked",
        "ground",
        "powder",
        "instant",
        "fat free",
        "low fat",
        "sugar free",
    ],
    "mapper_fragile": [
        "pie filling",
        "pie shell",
        "sandwich cookie",
        "sandwich cooky",
        "cookies",
        "buns",
        "wraps",
        "noodle",
        "pudding",
        "sherbet",
        "doritos",
        "rice a roni",
        "steak sauce",
    ],
}

PREPARED_OR_WRONG_FORM_TOKENS = {
    "bowl",
    "dinner",
    "entree",
    "kit",
    "lunchmeat",
    "meal",
    "nuggets",
    "patty",
    "pizza",
    "salad",
    "sandwich",
    "seasoning",
    "soup",
    "spread",
}

MEAT_TARGET_TOKENS = {"beef", "chicken", "ham", "pork", "steak", "turkey"}


@dataclass(frozen=True)
class SeedRecipe:
    recipe_num: str
    recipe_name: str
    shopping_items: dict[str, float]
    risk_score: int
    risk_terms: list[str]


@dataclass(frozen=True)
class SeedPlan:
    plan_id: str
    config: dict[str, Any]
    recipes: list[SeedRecipe]


@dataclass
class VerificationClaim:
    claim_id: str
    plan_id: str
    config_id: str
    recipe_num: str
    recipe_name: str
    line_index: int
    store: str
    ingredient_label: str
    grams_needed: float
    canonical_name: str
    shopping_canonical: str
    nutrition_key: str
    nutrition_state: str
    nutrition_source: str
    esha_code: str = ""
    esha_description: str = ""
    sr28_fdc_id: str = ""
    fndds_code: str = ""
    fndds_description: str = ""
    shopping_state: str = ""
    product_name: str = ""
    product_upc: str = ""
    package_grams: float = 0.0
    package_price_usd: float = 0.0
    packages_to_buy: int = 0
    checkout_usd: float = 0.0
    used_usd: float = 0.0
    product_search_term: str = ""
    product_canonical_surface: str = ""
    product_canonical_shopping_item: str = ""
    decision_reason: str = ""
    path: list[str] = field(default_factory=list)


@dataclass
class VerificationVerdict:
    claim_id: str
    decision: str
    issue_type: str
    severity: str
    confidence: float
    reason: str
    suggested_fix: str = ""
    verifier: str = "rules"
    evidence: list[str] = field(default_factory=list)


def _json_default(value: Any) -> Any:
    if hasattr(value, "__dict__"):
        return asdict(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _load_fndds_descriptions(path: Path = FNDDS_MAIN_FOOD_DESC_CSV) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle):
            code = (row.get("Food code") or row.get("fndds_code") or "").strip()
            desc = (row.get("Main food description") or row.get("description") or "").strip()
            if code and desc:
                out[code] = desc
    return out


def _safe_literal_dict(raw: str) -> dict[str, float]:
    try:
        parsed = ast.literal_eval(raw or "{}")
    except (SyntaxError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in parsed.items():
        try:
            grams = float(value)
        except (TypeError, ValueError):
            continue
        if grams > 0:
            out[str(key)] = grams
    return out


def recipe_risk_terms(recipe_name: str, shopping_items: dict[str, float]) -> tuple[int, list[str]]:
    text = normalize_key(" ".join([recipe_name, *shopping_items.keys()]))
    hits: list[str] = []
    score = 0
    for family, terms in RISK_TERMS.items():
        for term in terms:
            if normalize_key(term) in text:
                hits.append(f"{family}:{term}")
                score += 4 if family in {"meat_cut", "mapper_fragile"} else 2
    for label, grams in shopping_items.items():
        key = normalize_key(label)
        if grams >= 1000:
            hits.append(f"large_grams:{label}")
            score += 2
        if grams <= 2 and any(token in key for token in ("spice", "powder", "salt", "pepper")):
            hits.append(f"tiny_spice:{label}")
            score += 1
    return score, sorted(set(hits))


def load_seed_recipe_candidates(recipes_csv: Path) -> list[SeedRecipe]:
    candidates: list[SeedRecipe] = []
    with recipes_csv.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle):
            recipe_num = (row.get("recipeNum") or row.get("recipe_num") or "").strip()
            recipe_name = (row.get("recipeName") or row.get("recipe_name") or "").strip()
            shopping_items = _safe_literal_dict(row.get("shopping_items_dict") or "")
            if not recipe_num or not shopping_items:
                continue
            risk_score, terms = recipe_risk_terms(recipe_name, shopping_items)
            candidates.append(
                SeedRecipe(
                    recipe_num=recipe_num,
                    recipe_name=recipe_name,
                    shopping_items=shopping_items,
                    risk_score=risk_score,
                    risk_terms=terms,
                )
            )
    return candidates


def select_seed_recipes(candidates: list[SeedRecipe], max_recipes: int) -> list[SeedRecipe]:
    if max_recipes <= 0 or len(candidates) <= max_recipes:
        return candidates
    risky_target = max(1, int(max_recipes * 0.75))
    ranked = sorted(candidates, key=lambda row: (-row.risk_score, row.recipe_num))
    selected: list[SeedRecipe] = []
    seen: set[str] = set()
    for recipe in ranked:
        if recipe.risk_score <= 0 and len(selected) >= risky_target:
            break
        selected.append(recipe)
        seen.add(recipe.recipe_num)
        if len(selected) >= risky_target:
            break
    remaining = [row for row in candidates if row.recipe_num not in seen]
    if remaining:
        stride = max(1, len(remaining) // max(1, max_recipes - len(selected)))
        for index in range(0, len(remaining), stride):
            selected.append(remaining[index])
            if len(selected) >= max_recipes:
                break
    return selected[:max_recipes]


def build_seed_plans(
    recipes: list[SeedRecipe],
    *,
    recipes_per_plan: int,
    configs: list[dict[str, Any]] | None = None,
) -> list[SeedPlan]:
    configs = configs or DEFAULT_CONFIGS
    if recipes_per_plan <= 0:
        raise ValueError("recipes_per_plan must be positive")
    plans: list[SeedPlan] = []
    for plan_index, start in enumerate(range(0, len(recipes), recipes_per_plan), start=1):
        config = configs[(plan_index - 1) % len(configs)]
        chunk = recipes[start : start + recipes_per_plan]
        plan_id = f"seed_{plan_index:04d}_{config['config_id']}"
        plans.append(SeedPlan(plan_id=plan_id, config=dict(config), recipes=chunk))
    return plans


def _nutrition_key(lab: dict[str, Any]) -> str:
    if lab.get("esha_code"):
        return f"ESHA:{lab['esha_code']}"
    if lab.get("sr28_fdc_id"):
        return f"SR28:{lab['sr28_fdc_id']}"
    if lab.get("fndds_code"):
        return f"FNDDS:{lab['fndds_code']}"
    return ""


def _is_no_purchase(label: str, lab: dict[str, Any], buy_water: bool) -> bool:
    if buy_water:
        return False
    keys = {
        normalize_key(label),
        normalize_key(lab.get("shopping_canonical") or ""),
        normalize_key(lab.get("canonical_name") or ""),
    }
    return bool(keys & NO_PURCHASE_KEYS)


def _claim_from_line(
    *,
    plan: SeedPlan,
    recipe: SeedRecipe,
    line_index: int,
    store: str,
    label: str,
    grams: float,
    lab: dict[str, Any],
    offer: dict[str, Any] | None,
    fndds_desc: dict[str, str],
) -> VerificationClaim:
    fndds_code = str(lab.get("fndds_code") or "")
    product_name = str((offer or {}).get("name") or "")
    package_grams = float((offer or {}).get("package_grams") or 0.0)
    claim_id = "|".join(
        [
            plan.plan_id,
            recipe.recipe_num,
            str(line_index),
            store,
            normalize_key(label).replace(" ", "_")[:80],
        ]
    )
    return VerificationClaim(
        claim_id=claim_id,
        plan_id=plan.plan_id,
        config_id=str(plan.config.get("config_id") or ""),
        recipe_num=recipe.recipe_num,
        recipe_name=recipe.recipe_name,
        line_index=line_index,
        store=store,
        ingredient_label=label,
        grams_needed=grams,
        canonical_name=str(lab.get("canonical_name") or ""),
        shopping_canonical=str(lab.get("shopping_canonical") or ""),
        nutrition_key=_nutrition_key(lab),
        nutrition_state=str(lab.get("nutrition_state") or ""),
        nutrition_source=str(lab.get("nutrition_source") or ""),
        esha_code=str(lab.get("esha_code") or ""),
        esha_description=str(lab.get("esha_description") or ""),
        sr28_fdc_id=str(lab.get("sr28_fdc_id") or ""),
        fndds_code=fndds_code,
        fndds_description=fndds_desc.get(fndds_code, ""),
        shopping_state=str(lab.get("shopping_state") or ""),
        product_name=product_name,
        product_upc=str((offer or {}).get("upc") or ""),
        package_grams=package_grams,
        package_price_usd=float((offer or {}).get("package_usd") or 0.0),
        packages_to_buy=int((offer or {}).get("packages") or 0),
        checkout_usd=float((offer or {}).get("checkout_usd") or 0.0),
        used_usd=float((offer or {}).get("used_usd") or 0.0),
        product_search_term=str((offer or {}).get("search_term") or ""),
        product_canonical_surface=str((offer or {}).get("canonical_surface") or ""),
        product_canonical_shopping_item=str((offer or {}).get("canonical_shopping_item") or ""),
        decision_reason=str((offer or {}).get("decision_reason") or ""),
        path=list(lab.get("path") or []),
    )


def extract_claims(
    plans: list[SeedPlan],
    *,
    retail_bridge_csv: Path,
    surface_csv: Path | None = None,
    product_esha_map_csv: Path | None = None,
    buy_water: bool = False,
) -> list[VerificationClaim]:
    configure_data_sources(
        surface_csv=surface_csv,
        product_esha_map_csv=product_esha_map_csv,
        retail_surface_bridge_csv=retail_bridge_csv,
    )
    offers = _load_retail_offers(retail_bridge_csv)
    fndds_desc = _load_fndds_descriptions()
    claims: list[VerificationClaim] = []
    for plan in plans:
        stores = [str(store) for store in plan.config.get("stores", ["walmart", "kroger"])]
        for recipe in plan.recipes:
            for line_index, (label, grams) in enumerate(recipe.shopping_items.items(), start=1):
                lab = asdict_safe(calculate_lab(display=label, item=label, grams=grams))
                if _is_no_purchase(label, lab, buy_water):
                    continue
                products = lab.get("products") or []
                if not products:
                    claims.append(
                        _claim_from_line(
                            plan=plan,
                            recipe=recipe,
                            line_index=line_index,
                            store="no_store",
                            label=label,
                            grams=grams,
                            lab=lab,
                            offer=None,
                            fndds_desc=fndds_desc,
                        )
                    )
                    continue
                for store in stores:
                    offer = _best_offer(products, offers, store, grams)
                    claims.append(
                        _claim_from_line(
                            plan=plan,
                            recipe=recipe,
                            line_index=line_index,
                            store=store,
                            label=label,
                            grams=grams,
                            lab=lab,
                            offer=offer,
                            fndds_desc=fndds_desc,
                        )
                    )
    return claims


def asdict_safe(value: Any) -> dict[str, Any]:
    data = asdict(value)
    nutrition = data.get("nutrition")
    if nutrition is not None and not isinstance(nutrition, dict):
        data["nutrition"] = asdict(nutrition)
    products = []
    for product in data.get("products") or []:
        products.append(product if isinstance(product, dict) else asdict(product))
    data["products"] = products
    rejected = []
    for product in data.get("rejected_products") or []:
        rejected.append(product if isinstance(product, dict) else asdict(product))
    data["rejected_products"] = rejected
    return data


def _tokens(text: str) -> set[str]:
    return set(normalize_key(text).split())


def _has_any(text: str, phrases: set[str] | list[str] | tuple[str, ...]) -> bool:
    norm = f" {normalize_key(text)} "
    return any(f" {normalize_key(phrase)} " in norm for phrase in phrases)


def _target_text(claim: VerificationClaim) -> str:
    return " ".join([claim.ingredient_label, claim.canonical_name, claim.shopping_canonical])


def _product_text(claim: VerificationClaim) -> str:
    return " ".join([claim.product_name, claim.product_search_term, claim.product_canonical_surface])


class RuleVerifier:
    verifier_name = "rules"

    def verify(self, claim: VerificationClaim) -> VerificationVerdict:
        blockers = self._blockers(claim)
        if blockers:
            issue_type, severity, confidence, reason, suggested_fix, evidence = blockers[0]
            return VerificationVerdict(
                claim_id=claim.claim_id,
                decision="reject" if severity == "blocker" else "needs_human",
                issue_type=issue_type,
                severity=severity,
                confidence=confidence,
                reason=reason,
                suggested_fix=suggested_fix,
                verifier=self.verifier_name,
                evidence=evidence,
            )
        warnings = self._warnings(claim)
        if warnings:
            issue_type, severity, confidence, reason, suggested_fix, evidence = warnings[0]
            return VerificationVerdict(
                claim_id=claim.claim_id,
                decision="needs_human",
                issue_type=issue_type,
                severity=severity,
                confidence=confidence,
                reason=reason,
                suggested_fix=suggested_fix,
                verifier=self.verifier_name,
                evidence=evidence,
            )
        return VerificationVerdict(
            claim_id=claim.claim_id,
            decision="accept",
            issue_type="ok",
            severity="info",
            confidence=0.95,
            reason="No deterministic blocker found.",
            verifier=self.verifier_name,
            evidence=[],
        )

    def _blockers(self, claim: VerificationClaim) -> list[tuple[str, str, float, str, str, list[str]]]:
        out: list[tuple[str, str, float, str, str, list[str]]] = []
        target = _target_text(claim)
        target_key = normalize_key(target)
        product = _product_text(claim)
        product_key = normalize_key(product)
        fndds_desc = normalize_key(claim.fndds_description)
        nutrition_desc = normalize_key(" ".join([claim.fndds_description, claim.esha_description]))

        if not claim.nutrition_key or claim.nutrition_state == "nutrition_unknown":
            out.append(
                (
                    "nutrition_missing",
                    "blocker",
                    1.0,
                    "Ingredient has no verified nutrition anchor.",
                    "Add or repair ESHA/SR28/FNDDS nutrition mapping.",
                    [claim.ingredient_label, claim.nutrition_state, claim.nutrition_source],
                )
            )

        if claim.store != "no_store" and not claim.product_name:
            out.append(
                (
                    "store_item_missing",
                    "blocker",
                    1.0,
                    "No priced store item was selected for this purchasable ingredient.",
                    "Repair retail bridge or product query for the shopping canonical.",
                    [claim.shopping_canonical, claim.store],
                )
            )

        if claim.store == "no_store" or claim.shopping_state == "shopping_gap":
            out.append(
                (
                    "shopping_gap",
                    "blocker",
                    1.0,
                    "Calculator could not find a shopping candidate.",
                    "Repair product lookup or mark the item as intentionally not purchased.",
                    [claim.ingredient_label, claim.shopping_canonical, claim.shopping_state],
                )
            )

        if "pie filling" in target_key and "pie shell" in nutrition_desc:
            out.append(
                (
                    "wrong_fndds",
                    "blocker",
                    1.0,
                    "Pie filling is anchored to a pie shell code.",
                    "Use a pie filling FNDDS/ESHA anchor, not a crust/shell anchor.",
                    [claim.ingredient_label, claim.nutrition_key, claim.fndds_description, claim.esha_description],
                )
            )

        if {"cookie", "cookies", "cooky"} & _tokens(target_key) and "ice cream" in nutrition_desc:
            out.append(
                (
                    "wrong_fndds",
                    "blocker",
                    1.0,
                    "Cookie ingredient is anchored to ice cream.",
                    "Use a cookie FNDDS/ESHA anchor.",
                    [claim.ingredient_label, claim.nutrition_key, claim.fndds_description, claim.esha_description],
                )
            )

        if "milk" in _tokens(target_key) and not ({"almond", "oat", "soy", "coconut"} & _tokens(target_key)):
            plant_terms = {"almond", "cashew", "coconut", "oat", "pea", "rice", "soy"}
            if plant_terms & _tokens(product_key):
                out.append(
                    (
                        "wrong_store_item",
                        "blocker",
                        0.98,
                        "Cow milk target is matched to a plant/species milk product.",
                        "Use a dairy milk product or preserve the plant-milk subtype in the recipe target.",
                        [claim.ingredient_label, claim.product_name],
                    )
                )

        if "chicken breast" in target_key and _has_any(product_key, ["lunchmeat", "lunch meat", "deli", "nuggets"]):
            out.append(
                (
                    "wrong_form",
                    "blocker",
                    0.99,
                    "Raw chicken breast target is matched to lunchmeat/deli/prepared chicken.",
                    "Use raw chicken breast products only.",
                    [claim.ingredient_label, claim.product_name],
                )
            )

        ham_target_allows_deli = False
        if "ham" in _tokens(target_key):
            target_wants_whole = _has_any(
                target_key,
                ["ham leg", "ham hock", "ham bone", "bone in ham", "spiral ham", "whole ham", "ham steak", "picnic ham"],
            )
            product_is_deli = _has_any(product_key, ["deli", "lunchmeat", "lunch meat", "sliced ham", "thin sliced"])
            ham_target_allows_deli = _has_any(
                target_key,
                [
                    "chopped ham",
                    "deli ham",
                    "diced ham",
                    "ham chopped",
                    "ham diced",
                    "lunch meat",
                    "lunchmeat",
                    "slice ham",
                    "sliced ham",
                    "slices ham",
                    "thin ham",
                    "wafer thin ham",
                ],
            )
            if target_wants_whole and product_is_deli and not ham_target_allows_deli:
                out.append(
                    (
                        "wrong_form",
                        "blocker",
                        0.99,
                        "Whole/cut ham target is matched to deli or sliced ham.",
                        "Preserve ham cut/form and block deli ham for whole ham targets.",
                        [claim.ingredient_label, claim.product_name],
                    )
                )

        if "bologna" in _tokens(target_key):
            target_wants_roll = _has_any(target_key, ["roll all beef bologna", "roll beef bologna", "roll bologna"])
            product_is_sliced = _has_any(product_key, ["deli", "lunch meat", "lunchmeat", "sliced", "thin sliced"])
            if target_wants_roll and product_is_sliced:
                out.append(
                    (
                        "wrong_form",
                        "blocker",
                        0.99,
                        "Bologna roll target is matched to deli or sliced bologna.",
                        "Use a whole/bulk bologna roll or scrub the recipe if only sliced packages are available.",
                        [claim.ingredient_label, claim.product_name],
                    )
                )

        target_tokens = _tokens(target_key)
        product_tokens = _tokens(product_key)
        if target_tokens & MEAT_TARGET_TOKENS and "seasoning" in product_tokens and "seasoning" not in target_tokens:
            out.append(
                (
                    "wrong_store_item",
                    "blocker",
                    0.99,
                    "Meat target is matched to a seasoning product.",
                    "Block seasoning/mix products unless the recipe ingredient is a seasoning.",
                    [claim.ingredient_label, claim.product_name],
                )
            )

        if target_tokens & MEAT_TARGET_TOKENS:
            prepared_hits = sorted((product_tokens & PREPARED_OR_WRONG_FORM_TOKENS) - target_tokens)
            allowed = {"sandwich"} if "sandwich" in target_tokens else set()
            if "ham" in target_tokens and ham_target_allows_deli:
                allowed.add("lunchmeat")
            prepared_hits = [hit for hit in prepared_hits if hit not in allowed]
            if prepared_hits and not ({"raw", "fresh"} & product_tokens):
                out.append(
                    (
                        "wrong_form",
                        "blocker",
                        0.90,
                        "Meat target appears matched to prepared/composite product.",
                        "Use raw/cut meat products unless the recipe explicitly asks for prepared form.",
                        [claim.ingredient_label, claim.product_name, ",".join(prepared_hits)],
                    )
                )

        if "egg" in target_tokens or "eggs" in target_tokens:
            if claim.package_grams >= 2000 and _has_any(product_key, ["count", "dozen", "eggs"]):
                out.append(
                    (
                        "bad_package_math",
                        "blocker",
                        1.0,
                        "Egg count package appears parsed as kilograms/grams per count instead of carton weight.",
                        "Normalize shell egg cartons to count * 50g.",
                        [claim.product_name, f"package_grams={claim.package_grams:g}"],
                    )
                )

        if claim.package_grams < claim.grams_needed / 100 and claim.grams_needed >= 500:
            out.append(
                (
                    "bad_package_math",
                    "blocker",
                    0.85,
                    "Package grams are implausibly tiny relative to required recipe grams.",
                    "Re-check package size parsing and unit conversion.",
                    [claim.ingredient_label, claim.product_name, f"needed={claim.grams_needed:g}", f"package={claim.package_grams:g}"],
                )
            )

        if fndds_desc and _has_any(target_key, ["pie filling"]) and "pie fill" not in fndds_desc:
            out.append(
                (
                    "wrong_fndds",
                    "blocker",
                    0.90,
                    "Pie filling target has a non-filling FNDDS description.",
                    "Use a pie filling FNDDS code.",
                    [claim.ingredient_label, claim.fndds_code, claim.fndds_description],
                )
            )

        return out

    def _warnings(self, claim: VerificationClaim) -> list[tuple[str, str, float, str, str, list[str]]]:
        out: list[tuple[str, str, float, str, str, list[str]]] = []
        target_key = normalize_key(_target_text(claim))
        product_key = normalize_key(_product_text(claim))

        if claim.product_name and claim.package_grams <= 0:
            out.append(
                (
                    "bad_package_math",
                    "warning",
                    0.75,
                    "Selected product has no usable package grams.",
                    "Fix package size parsing.",
                    [claim.product_name],
                )
            )
        if claim.product_name and claim.packages_to_buy >= 12 and claim.grams_needed < claim.package_grams * 1.5:
            out.append(
                (
                    "bad_package_math",
                    "warning",
                    0.70,
                    "Package count to buy is unexpectedly high.",
                    "Check needed grams and package grams.",
                    [claim.ingredient_label, claim.product_name, f"packages={claim.packages_to_buy}"],
                )
            )
        if "fresh" in _tokens(target_key) and "frozen" in _tokens(product_key):
            out.append(
                (
                    "wrong_form",
                    "warning",
                    0.75,
                    "Fresh target is matched to frozen product.",
                    "Verify whether frozen substitution is acceptable for this recipe.",
                    [claim.ingredient_label, claim.product_name],
                )
            )
        return out


class DeepSeekVerifier:
    verifier_name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        timeout_s: int = 60,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is required for --mode deepseek")

    def verify(self, claim: VerificationClaim) -> VerificationVerdict:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": json.dumps(asdict(claim), sort_keys=True)},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        verdict = json.loads(content)
        return VerificationVerdict(
            claim_id=claim.claim_id,
            decision=str(verdict.get("decision") or "needs_human"),
            issue_type=str(verdict.get("issue_type") or "unknown"),
            severity=str(verdict.get("severity") or "warning"),
            confidence=float(verdict.get("confidence") or 0.0),
            reason=str(verdict.get("reason") or ""),
            suggested_fix=str(verdict.get("suggested_fix") or ""),
            verifier=self.verifier_name,
            evidence=[str(item) for item in verdict.get("evidence") or []],
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You verify grocery purchase claims for a recipe planner. "
            "A claim connects a recipe ingredient, grams needed, nutrition code, and chosen store product. "
            "Reject if the product or nutrition anchor is the wrong food, wrong form, wrong subtype, non-food, "
            "prepared meal when raw ingredient is needed, deli/lunchmeat when a whole cut is needed, or package math is implausible. "
            "Return strict JSON with keys: decision accept|reject|needs_human, issue_type "
            "wrong_food|wrong_form|wrong_fndds|wrong_store_item|bad_grams|bad_package_math|nutrition_missing|shopping_gap|ok, "
            "severity blocker|warning|info, confidence number 0-1, reason, suggested_fix, evidence array. "
            "Be conservative: use needs_human for ambiguous substitutions."
        )


def write_jsonl(path: Path, rows: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = asdict(row) if hasattr(row, "__dataclass_fields__") else row
            handle.write(json.dumps(payload, sort_keys=True, default=_json_default) + "\n")


def write_fix_queue(path: Path, claims: dict[str, VerificationClaim], verdicts: list[VerificationVerdict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "claim_id",
        "decision",
        "issue_type",
        "severity",
        "confidence",
        "reason",
        "suggested_fix",
        "recipe_num",
        "recipe_name",
        "ingredient_label",
        "grams_needed",
        "nutrition_key",
        "fndds_description",
        "store",
        "product_name",
        "package_grams",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for verdict in verdicts:
            if verdict.decision == "accept":
                continue
            claim = claims[verdict.claim_id]
            writer.writerow(
                {
                    "claim_id": verdict.claim_id,
                    "decision": verdict.decision,
                    "issue_type": verdict.issue_type,
                    "severity": verdict.severity,
                    "confidence": f"{verdict.confidence:.2f}",
                    "reason": verdict.reason,
                    "suggested_fix": verdict.suggested_fix,
                    "recipe_num": claim.recipe_num,
                    "recipe_name": claim.recipe_name,
                    "ingredient_label": claim.ingredient_label,
                    "grams_needed": f"{claim.grams_needed:.4f}",
                    "nutrition_key": claim.nutrition_key,
                    "fndds_description": claim.fndds_description,
                    "store": claim.store,
                    "product_name": claim.product_name,
                    "package_grams": f"{claim.package_grams:.4f}",
                }
            )


def summarize(
    *,
    plans: list[SeedPlan],
    claims: list[VerificationClaim],
    claims_by_id: dict[str, VerificationClaim],
    verdicts: list[VerificationVerdict],
    out_dir: Path,
) -> dict[str, Any]:
    verdict_counts = Counter(v.decision for v in verdicts)
    issue_counts = Counter(v.issue_type for v in verdicts if v.decision != "accept")
    severity_counts = Counter(v.severity for v in verdicts if v.decision != "accept")
    blocked_recipe_nums = {
        claims_by_id[v.claim_id].recipe_num
        for v in verdicts
        if v.decision == "reject" and v.claim_id in claims_by_id
    }
    return {
        "plans": len(plans),
        "recipes": sum(len(plan.recipes) for plan in plans),
        "unique_recipes": len({recipe.recipe_num for plan in plans for recipe in plan.recipes}),
        "claims": len(claims),
        "verdict_counts": dict(verdict_counts),
        "issue_counts": dict(issue_counts),
        "severity_counts": dict(severity_counts),
        "blocked_recipes": len(blocked_recipe_nums),
        "out_dir": str(out_dir),
    }


def write_markdown_summary(path: Path, summary: dict[str, Any], verdicts: list[VerificationVerdict], claims: dict[str, VerificationClaim]) -> None:
    lines = [
        "# Plan Verification Suite",
        "",
        f"- plans: `{summary['plans']}`",
        f"- unique recipes: `{summary['unique_recipes']}`",
        f"- claims: `{summary['claims']}`",
        f"- blocked recipes: `{summary['blocked_recipes']}`",
        "",
        "## Verdicts",
        "",
    ]
    for key, value in sorted(summary["verdict_counts"].items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Top Issues", ""])
    for key, value in sorted(summary["issue_counts"].items(), key=lambda item: (-item[1], item[0]))[:20]:
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Sample Blockers", ""])
    sample_count = 0
    for verdict in verdicts:
        if verdict.decision == "accept":
            continue
        claim = claims.get(verdict.claim_id)
        if not claim:
            continue
        lines.append(
            f"- `{verdict.issue_type}` {claim.recipe_num} `{claim.ingredient_label}` -> "
            f"`{claim.product_name or claim.nutrition_key or 'no product'}`: {verdict.reason}"
        )
        sample_count += 1
        if sample_count >= 25:
            break
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


claims_by_id: dict[str, VerificationClaim] = {}


def run_suite(
    *,
    recipes_csv: Path,
    retail_bridge_csv: Path,
    out_dir: Path,
    max_recipes: int,
    recipes_per_plan: int,
    surface_csv: Path | None,
    product_esha_map_csv: Path | None,
    mode: str,
    deepseek_model: str,
    deepseek_limit: int,
    buy_water: bool,
    fail_on_reject: bool,
) -> dict[str, Any]:
    candidates = load_seed_recipe_candidates(recipes_csv)
    selected = select_seed_recipes(candidates, max_recipes)
    plans = build_seed_plans(selected, recipes_per_plan=recipes_per_plan)
    claims = extract_claims(
        plans,
        retail_bridge_csv=retail_bridge_csv,
        surface_csv=surface_csv,
        product_esha_map_csv=product_esha_map_csv,
        buy_water=buy_water,
    )
    global claims_by_id
    claims_by_id = {claim.claim_id: claim for claim in claims}

    verdicts: list[VerificationVerdict] = []
    if mode in {"rules", "both"}:
        rule_verifier = RuleVerifier()
        verdicts.extend(rule_verifier.verify(claim) for claim in claims)
    if mode in {"deepseek", "both"}:
        deepseek = DeepSeekVerifier(model=deepseek_model)
        deepseek_claims = claims if deepseek_limit <= 0 else claims[:deepseek_limit]
        verdicts.extend(deepseek.verify(claim) for claim in deepseek_claims)
        time.sleep(0.1)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "seed_plans.jsonl", plans)
    write_jsonl(out_dir / "verification_claims.jsonl", claims)
    write_jsonl(out_dir / "verification_verdicts.jsonl", verdicts)
    write_fix_queue(out_dir / "fix_queue.csv", claims_by_id, verdicts)
    summary = summarize(plans=plans, claims=claims, claims_by_id=claims_by_id, verdicts=verdicts, out_dir=out_dir)
    summary.update(
        {
            "recipes_csv": str(recipes_csv),
            "retail_bridge_csv": str(retail_bridge_csv),
            "surface_csv": str(lab_sources.SURFACE_CSV),
            "product_esha_map_csv": str(lab_sources.PRODUCT_ESHA_MAP_CSV),
            "mode": mode,
        }
    )
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown_summary(out_dir / "summary.md", summary, verdicts, claims_by_id)
    if fail_on_reject and summary["verdict_counts"].get("reject", 0):
        raise SystemExit(2)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and verify seeded recipe-plan purchase claims.")
    parser.add_argument("--recipes-csv", type=Path, default=DEFAULT_RECIPES_CSV)
    parser.add_argument("--retail-bridge-csv", type=Path, default=DEFAULT_RETAIL_BRIDGE_CSV)
    parser.add_argument("--surface-csv", type=Path)
    parser.add_argument("--product-esha-map", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-recipes", type=int, default=1500)
    parser.add_argument("--recipes-per-plan", type=int, default=12)
    parser.add_argument("--mode", choices=["rules", "deepseek", "both"], default="rules")
    parser.add_argument("--deepseek-model", default="deepseek-v4-flash")
    parser.add_argument("--deepseek-limit", type=int, default=0, help="0 means no limit when DeepSeek is enabled")
    parser.add_argument("--buy-water", action="store_true")
    parser.add_argument("--fail-on-reject", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run_suite(
        recipes_csv=args.recipes_csv.expanduser(),
        retail_bridge_csv=args.retail_bridge_csv.expanduser(),
        out_dir=args.out_dir.expanduser(),
        max_recipes=args.max_recipes,
        recipes_per_plan=args.recipes_per_plan,
        surface_csv=args.surface_csv.expanduser() if args.surface_csv else None,
        product_esha_map_csv=args.product_esha_map.expanduser() if args.product_esha_map else None,
        mode=args.mode,
        deepseek_model=args.deepseek_model,
        deepseek_limit=args.deepseek_limit,
        buy_water=args.buy_water,
        fail_on_reject=args.fail_on_reject,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
