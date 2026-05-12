#!/usr/bin/env python3
"""Validate Nebius recipe-normalization output against prompt stress fixtures.

The validator is intentionally conservative. It does not prove a model output
is globally correct; it catches the failure modes that would make a recipe
normalization pass unsafe to run over the full corpus.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "implementation" / "output" / "recipe_normalization_prompt_test_pack.jsonl"

VALID_ROLES = {
    "consumed",
    "component_group",
    "alternative_group",
    "process_medium",
    "process_coating",
    "process_cooking_water",
    "garnish",
    "serving_accompaniment",
    "optional",
    "non_food",
    "section_header",
    "unknown",
}

VALID_STATUSES = {"CALCULATION_READY", "BLOCKED", "EXCLUDED"}

BRAND_TERMS = {
    "rotel",
    "cool whip",
    "philadelphia",
    "jell-o",
    "jello",
    "ritz",
    "kraft",
    "oscar mayer",
    "lipton",
    "campbell",
    "campbell's",
    "lawry",
    "lawry's",
    "tony chachere",
    "splenda",
    "crisco",
    "velveeta",
    "ragu",
    "nabisco",
    "gold standard",
}

QUANTITY_RE = re.compile(
    r"(^|\b)(?:\d+(?:\.\d+)?|\d+\s*/\s*\d+|\d+\s+\d+\s*/\s*\d+)\s*"
    r"(?:lb|lbs|pound|pounds|oz|ounce|ounces|g|gram|grams|kg|cup|cups|tbsp|tsp|teaspoon|tablespoon|can|cans|package|pkg)\b",
    re.I,
)
SKU_RE = re.compile(r"\b(?:sku|upc|gtin)\s*[:#]?\s*\d+\b", re.I)


@dataclass
class Finding:
    recipe_id: str
    line_index: str
    severity: str
    code: str
    message: str


def norm_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def norm_tokens(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [norm_text(v).lower() for v in value if norm_text(v)]
    text = norm_text(value)
    if not text:
        return []
    return [part.strip().lower() for part in re.split(r"[|;,]", text) if part.strip()]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(obj, dict):
                raise SystemExit(f"{path}:{line_no}: expected JSON object")
            rows.append(obj)
    return rows


def by_recipe(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        rid = norm_text(row.get("recipe_id"))
        if not rid:
            raise SystemExit("candidate/source row missing recipe_id")
        out[rid] = row
    return out


def candidate_ingredients(candidate: dict[str, Any]) -> dict[int, dict[str, Any]]:
    ingredients = candidate.get("ingredients")
    if not isinstance(ingredients, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for ing in ingredients:
        if not isinstance(ing, dict):
            continue
        try:
            idx = int(ing.get("line_index"))
        except (TypeError, ValueError):
            continue
        out[idx] = ing
    return out


def add(findings: list[Finding], recipe_id: Any, line_index: Any, severity: str, code: str, message: str) -> None:
    findings.append(Finding(norm_text(recipe_id), norm_text(line_index), severity, code, message))


def status(ing: dict[str, Any]) -> str:
    return norm_text((ing.get("consumption") or {}).get("calculation_status"))


def match_status(ing: dict[str, Any]) -> str:
    return norm_text((ing.get("matchability") or {}).get("status"))


def policy(ing: dict[str, Any]) -> str:
    return norm_text((ing.get("consumption") or {}).get("consumption_policy"))


def role(ing: dict[str, Any]) -> str:
    return norm_text(ing.get("role"))


def normalized(ing: dict[str, Any]) -> dict[str, Any]:
    value = ing.get("normalized")
    return value if isinstance(value, dict) else {}


def machine_name(ing: dict[str, Any]) -> str:
    return norm_text(normalized(ing).get("machine_name")).lower()


def rewritten_ingredient(ing: dict[str, Any]) -> str:
    return norm_text(ing.get("rewritten_ingredient")).lower()


def source_grams(ing: dict[str, Any]) -> float | None:
    value = (ing.get("quantity") or {}).get("source_grams", ing.get("source_grams"))
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def consumed_grams(ing: dict[str, Any]) -> float | None:
    value = (ing.get("consumption") or {}).get("consumed_grams")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def has_component(ing: dict[str, Any], *needles: str) -> bool:
    text = json.dumps(ing.get("components", []), ensure_ascii=False).lower()
    return all(needle.lower() in text for needle in needles)


def has_alternatives(ing: dict[str, Any]) -> bool:
    alternatives = ing.get("alternatives")
    return isinstance(alternatives, list) and len(alternatives) >= 2


def object_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).lower()


def normalized_object_text(ing: dict[str, Any]) -> str:
    return object_text(
        {
            "rewritten_ingredient": ing.get("rewritten_ingredient"),
            "normalized": ing.get("normalized"),
            "components": ing.get("components"),
            "alternatives": ing.get("alternatives"),
            "consumption": ing.get("consumption"),
        }
    )


def has_any_text(text: str, *needles: str) -> bool:
    return any(needle.lower() in text for needle in needles)


def require_blocked_unless_policy(
    findings: list[Finding],
    recipe_id: Any,
    line_index: Any,
    ing: dict[str, Any],
    expected_role: str,
    expected_policy: str,
    code: str,
) -> None:
    if role(ing) != expected_role:
        add(findings, recipe_id, line_index, "error", f"{code}_role", f"expected role {expected_role}, got {role(ing)!r}")
    if status(ing) == "CALCULATION_READY" and policy(ing) == "all_input":
        add(findings, recipe_id, line_index, "error", f"{code}_all_input", "process/role line was marked all-input calculation-ready")
    if status(ing) not in {"BLOCKED", "EXCLUDED"} and policy(ing) == expected_policy:
        add(findings, recipe_id, line_index, "warning", f"{code}_status", f"{expected_policy} should usually block or exclude")
    if policy(ing) not in {expected_policy, "excluded_optional", "excluded_non_food"}:
        add(findings, recipe_id, line_index, "error", f"{code}_policy", f"expected policy {expected_policy}, got {policy(ing)!r}")


def check_general(findings: list[Finding], recipe_id: Any, ing: dict[str, Any]) -> None:
    line_index = ing.get("line_index", "?")
    r = role(ing)
    if r not in VALID_ROLES:
        add(findings, recipe_id, line_index, "error", "invalid_role", f"invalid role {r!r}")
    s = status(ing)
    if s not in VALID_STATUSES:
        add(findings, recipe_id, line_index, "error", "invalid_status", f"invalid calculation_status {s!r}")

    m = machine_name(ing)
    rewrite = rewritten_ingredient(ing)
    if r not in {"non_food", "section_header", "unknown"} and s != "EXCLUDED" and not rewrite:
        add(findings, recipe_id, line_index, "error", "missing_rewritten_ingredient", "real ingredient is missing rewritten_ingredient")
    if SKU_RE.search(m):
        add(findings, recipe_id, line_index, "error", "fake_sku", "machine_name contains SKU/UPC/GTIN-like text")
    if SKU_RE.search(rewrite):
        add(findings, recipe_id, line_index, "error", "fake_sku_rewrite", "rewritten_ingredient contains SKU/UPC/GTIN-like text")
    if QUANTITY_RE.search(m):
        add(findings, recipe_id, line_index, "error", "quantity_in_machine_name", "machine_name contains quantity/unit text")
    for brand in BRAND_TERMS:
        if re.search(rf"\b{re.escape(brand)}\b", m):
            add(findings, recipe_id, line_index, "error", "brand_in_machine_name", f"brand term remains in machine_name: {brand}")
        if rewrite and re.search(rf"\b{re.escape(brand)}\b", rewrite):
            add(findings, recipe_id, line_index, "error", "brand_in_rewritten_ingredient", f"brand term remains in rewritten_ingredient: {brand}")

    original = norm_text(ing.get("original_display")).lower()
    if m and original:
        stripped = re.sub(r"[^a-z0-9 ]+", " ", original)
        stripped = re.sub(
            r"\b\d+(?:\.\d+)?|\b(?:cup|cups|teaspoon|tablespoon|tbsp|tsp|ounce|ounces|oz|lb|lbs|pound|pounds|can|package|pkg)\b",
            " ",
            stripped,
        )
        stripped = re.sub(r"\s+", " ", stripped).strip()
        stripped_tokens = stripped.split()
        echo_terms = {
            "about",
            "chopped",
            "cooked",
            "drained",
            "for",
            "optional",
            "prepared",
            "rinsed",
            "soaked",
            "taste",
            "to",
            "with",
        }
        if len(stripped) >= 12 and len(stripped_tokens) > 2 and m == stripped and echo_terms.intersection(stripped_tokens):
            add(findings, recipe_id, line_index, "warning", "display_echo", "machine_name appears to be display text with quantities stripped")


def check_case(findings: list[Finding], recipe_id: Any, stress: dict[str, Any], ing: dict[str, Any]) -> None:
    case = norm_text(stress.get("case"))
    line_index = stress.get("line_index", "?")
    n = normalized(ing)
    m = machine_name(ing)
    pol = policy(ing)
    stat = status(ing)
    display = norm_text(stress.get("display")).lower()
    item = norm_text(stress.get("item")).lower()
    all_text = normalized_object_text(ing)

    if case == "oil_for_frying":
        require_blocked_unless_policy(findings, recipe_id, line_index, ing, "process_medium", "uptake_policy_required", case)
        sg = source_grams(ing)
        cg = consumed_grams(ing)
        if sg is not None and cg is not None and abs(cg - sg) < 0.001:
            add(findings, recipe_id, line_index, "error", "oil_full_consumed", "frying oil consumed_grams equals source_grams")
    elif case == "flour_for_dusting_dredging":
        require_blocked_unless_policy(findings, recipe_id, line_index, ing, "process_coating", "retention_policy_required", case)
    elif case == "salt_for_water":
        require_blocked_unless_policy(findings, recipe_id, line_index, ing, "process_cooking_water", "sodium_absorption_policy_required", case)
    elif case == "herb_garnish":
        if role(ing) not in {"garnish", "optional"}:
            add(findings, recipe_id, line_index, "error", "garnish_role", f"expected garnish/optional role, got {role(ing)!r}")
        if stat == "CALCULATION_READY" and pol == "all_input":
            add(findings, recipe_id, line_index, "warning", "garnish_all_input", "garnish marked as all-input calculation-ready")
    elif case == "serving_accompaniment":
        require_blocked_unless_policy(findings, recipe_id, line_index, ing, "serving_accompaniment", "serving_selection_required", case)
    elif case == "non_food_equipment":
        if role(ing) != "non_food":
            add(findings, recipe_id, line_index, "error", "non_food_role", f"expected non_food, got {role(ing)!r}")
        if stat != "EXCLUDED" or pol != "excluded_non_food":
            add(findings, recipe_id, line_index, "error", "non_food_exclusion", "non-food/equipment must be excluded_non_food/EXCLUDED")
    elif case == "true_alternative_bean_mix":
        if role(ing) != "alternative_group" and not has_alternatives(ing):
            add(findings, recipe_id, line_index, "error", "alternative_missing", "bean mix alternatives must be preserved")
        if not has_any_text(all_text, "7 bean", "7-bean") or not has_any_text(all_text, "15 bean", "15-bean"):
            add(findings, recipe_id, line_index, "error", "bean_mix_alternatives_lost", "7 bean mix and 15 bean mix alternatives were not both preserved")
        if not has_any_text(all_text, "bean mix", "mixed bean", "bean soup mix"):
            add(findings, recipe_id, line_index, "error", "bean_mix_identity_lost", "bean mix umbrella identity was not preserved")
        if match_status(ing) != "MATCH_READY":
            add(findings, recipe_id, line_index, "error", "bean_mix_not_match_ready", f"equivalent bean mix alternatives should be match-ready, got {match_status(ing)!r}")
        if stat != "CALCULATION_READY":
            add(findings, recipe_id, line_index, "error", "bean_mix_equivalent_not_selected", "7/15 bean mix should calculate through equivalent-alternatives policy")
        if pol != "equivalent_alternatives_policy_applied":
            add(findings, recipe_id, line_index, "error", "bean_mix_equivalent_policy_missing", f"expected equivalent_alternatives_policy_applied, got {pol!r}")
    elif case.startswith("true_alternative"):
        if role(ing) != "alternative_group" and not has_alternatives(ing):
            add(findings, recipe_id, line_index, "error", "alternative_missing", "true alternative must be role=alternative_group or have 2+ alternatives")
        if stat == "CALCULATION_READY" and pol == "all_input":
            add(findings, recipe_id, line_index, "error", "alternative_silently_chosen", "alternative line marked calculation-ready as all-input")
    elif case == "salt_and_pepper_component":
        if role(ing) != "component_group" and not has_component(ing, "salt", "pepper"):
            add(findings, recipe_id, line_index, "error", "salt_pepper_not_split", "salt and pepper must be split into components")
    elif case == "citrus_juice_zest_split":
        if role(ing) != "component_group" and not (has_component(ing, "juice") and has_component(ing, "zest")):
            add(findings, recipe_id, line_index, "error", "citrus_not_split", "citrus juice/zest line must be split into components")
    elif case == "quantity_range":
        q = ing.get("quantity") if isinstance(ing.get("quantity"), dict) else {}
        if q.get("range_low") is None and q.get("range_high") is None and q.get("range_policy") not in {"source_grams", "blocked"}:
            add(findings, recipe_id, line_index, "warning", "range_not_preserved", "quantity range was not represented")
    elif case == "ham_large_quantity":
        if "ham" not in m:
            add(findings, recipe_id, line_index, "error", "ham_identity", "ham line did not preserve ham identity")
        if QUANTITY_RE.search(m):
            add(findings, recipe_id, line_index, "error", "ham_quantity_in_name", "ham quantity leaked into machine_name")
    elif case == "apple_baking_context":
        variants = norm_tokens(n.get("variant"))
        culinary_use = norm_text(n.get("culinary_use")).lower()
        if not variants and "baking" not in culinary_use and "tart" not in culinary_use and "cooking" not in culinary_use:
            add(findings, recipe_id, line_index, "error", "apple_context_lost", "apple variety/culinary use was not preserved")
    elif case == "corn_storage_state":
        if "corn" not in (norm_text(n.get("product_identity")).lower() + " " + m):
            add(findings, recipe_id, line_index, "error", "corn_identity", "corn identity not preserved")
        storage = " ".join(norm_tokens(n.get("processing_storage")) + norm_tokens(n.get("form_texture_cut")))
        display = norm_text(stress.get("display")).lower()
        for token in ("fresh", "frozen", "canned", "creamed", "whole"):
            if token in display and token not in storage and token not in m:
                add(findings, recipe_id, line_index, "error", "corn_state_lost", f"corn state/form token lost: {token}")
    elif case == "brand_cleanup":
        display = norm_text(stress.get("display")).lower()
        if any(brand in display for brand in BRAND_TERMS):
            removed = norm_tokens(n.get("brand_removed"))
            if not removed:
                add(findings, recipe_id, line_index, "warning", "brand_not_recorded", "brand appears in display but brand_removed is empty")
    elif case in {"generic_cheese_context", "generic_nuts_context", "generic_pasta_context"}:
        specific_cues = {
            "generic_cheese_context": ["swiss", "parmesan", "mozzarella", "velveeta", "ricotta", "fontina", "feta", "cream cheese"],
            "generic_nuts_context": ["walnut", "pecan", "almond", "peanut", "cashew"],
            "generic_pasta_context": ["penne", "bow tie", "macaroni", "spaghetti", "fettuccine", "linguine"],
        }[case]
        if any(cue in display for cue in specific_cues) and m in {"cheese", "nuts", "nut", "pasta"}:
            add(findings, recipe_id, line_index, "error", "bare_category_regression", "specific display collapsed to bare category")
    elif case in {"percent_purity_bran_brand", "percent_purity_bran_ambiguous", "percent_purity_pumpkin"}:
        if "100" in display and "100" not in all_text:
            add(findings, recipe_id, line_index, "error", "percent_purity_lost", "100%/purity label was not preserved")
        if "bran" in display and "bran" not in (m + " " + norm_text(n.get("product_identity")).lower() + " " + rewritten_ingredient(ing)):
            add(findings, recipe_id, line_index, "error", "bran_identity_lost", "bran identity was not preserved")
        if case == "percent_purity_bran_ambiguous" and stat == "CALCULATION_READY" and pol == "all_input":
            add(findings, recipe_id, line_index, "error", "ambiguous_bran_ready", "bare 100% bran cannot be calculation-ready without cereal/crude-bran context")
        if "pumpkin" in display and "pumpkin" not in (m + " " + norm_text(n.get("product_identity")).lower()):
            add(findings, recipe_id, line_index, "error", "pumpkin_identity_lost", "pumpkin identity was not preserved")
    elif case == "percent_purity_fruit_juice_unknown":
        if "100" not in all_text:
            add(findings, recipe_id, line_index, "error", "percent_purity_lost", "100% juice claim was not preserved")
        if "juice" not in (m + " " + norm_text(n.get("product_identity")).lower() + " " + rewritten_ingredient(ing)):
            add(findings, recipe_id, line_index, "error", "juice_identity_lost", "juice identity was not preserved")
        if stat == "CALCULATION_READY" and pol == "all_input":
            add(findings, recipe_id, line_index, "error", "unknown_fruit_juice_ready", "100% fruit juice without fruit identity cannot be calculation-ready")
    elif case == "protein_powder_percent_flavor":
        if not has_any_text(m + " " + norm_text(n.get("product_identity")).lower(), "protein powder", "protein shake"):
            add(findings, recipe_id, line_index, "error", "protein_powder_identity_lost", "protein powder identity was not preserved")
        if "100" in display and "100" not in all_text:
            add(findings, recipe_id, line_index, "error", "protein_percent_lost", "100% whey/isolate-style claim was not preserved")
        if has_any_text(display, "chocolate", "vanilla", "strawberry") and not has_any_text(all_text, "chocolate", "vanilla", "strawberry"):
            add(findings, recipe_id, line_index, "error", "protein_flavor_lost", "protein powder flavor was not preserved")
    elif case == "parser_fragment":
        if role(ing) not in {"unknown", "section_header", "non_food"}:
            add(findings, recipe_id, line_index, "error", "parser_fragment_role", f"parser fragment must not be consumed, got {role(ing)!r}")
        if stat == "CALCULATION_READY" or pol == "all_input":
            add(findings, recipe_id, line_index, "error", "parser_fragment_ready", "parser fragment was marked calculation-ready/all-input")
    elif case == "section_header":
        if role(ing) not in {"section_header", "unknown", "non_food"}:
            add(findings, recipe_id, line_index, "error", "section_header_role", f"section header must not be consumed, got {role(ing)!r}")
        if stat == "CALCULATION_READY" or pol == "all_input":
            add(findings, recipe_id, line_index, "error", "section_header_ready", "section header was marked calculation-ready/all-input")
    elif case == "section_scoped_ingredient":
        if role(ing) == "section_header":
            add(findings, recipe_id, line_index, "error", "section_ingredient_lost", "real ingredient after section header was treated as a header")
        if "tomato sauce" not in (m + " " + norm_text(n.get("product_identity")).lower()):
            add(findings, recipe_id, line_index, "error", "section_ingredient_identity_lost", "section-scoped ingredient identity was not preserved")
        section = norm_text(ing.get("section")).lower()
        if "sauce" not in section:
            add(findings, recipe_id, line_index, "warning", "section_context_lost", "ingredient after For sauce header did not preserve section=sauce")
    elif case == "shared_sense_pepper":
        if "red pepper" in display or "green pepper" in display or "bell pepper" in display:
            if m in {"pepper", "black pepper", "white pepper"} or "black pepper" in all_text:
                add(findings, recipe_id, line_index, "error", "pepper_sense_wrong", "produce pepper was normalized as pepper spice")
            if not has_any_text(all_text, "red pepper", "green pepper", "bell pepper", "chile pepper", "chili pepper"):
                add(findings, recipe_id, line_index, "warning", "pepper_sense_weak", "produce pepper sense was not explicit")
        if "black pepper" in display or "white pepper" in display or "peppercorn" in display:
            if "bell pepper" in all_text or m in {"pepper", "red pepper", "green pepper"}:
                add(findings, recipe_id, line_index, "error", "pepper_sense_wrong", "pepper spice was normalized as produce pepper or bare pepper")
            if "peppercorn" in display and "peppercorn" not in all_text:
                add(findings, recipe_id, line_index, "warning", "peppercorn_form_lost", "peppercorn form was not preserved")
    elif case == "shared_sense_coriander":
        if "seed" in display and not has_any_text(all_text, "coriander seed", "seed"):
            add(findings, recipe_id, line_index, "error", "coriander_seed_lost", "coriander seed sense was not preserved")
        if "cilantro" in display and not has_any_text(all_text, "cilantro", "coriander leaf"):
            add(findings, recipe_id, line_index, "error", "cilantro_leaf_lost", "cilantro/coriander leaf sense was not preserved")
        if "cilantro" in display and "seed" in all_text:
            add(findings, recipe_id, line_index, "error", "coriander_sense_wrong", "cilantro leaf was normalized as coriander seed")
    elif case == "shared_sense_chili":
        if "powder" in display and not has_any_text(all_text, "chili powder", "chile powder"):
            add(findings, recipe_id, line_index, "error", "chili_powder_lost", "chili powder sense was not preserved")
        elif "pepper" in display and not has_any_text(all_text, "chili pepper", "chile pepper", "green chili pepper", "green chile pepper"):
            add(findings, recipe_id, line_index, "error", "chile_pepper_lost", "chile pepper produce sense was not preserved")
        elif "prepared chili" in display and not has_any_text(all_text, "prepared chili", "chili dish", "chili con carne", "stew"):
            add(findings, recipe_id, line_index, "warning", "prepared_chili_weak", "prepared chili dish sense was not explicit")
    elif case == "head_noun_trap":
        compounds = {
            "coconut milk": {"bad": {"milk", "coconut"}},
            "cream cheese": {"bad": {"cheese", "cream"}},
            "milk chocolate": {"bad": {"milk", "chocolate"}},
            "peanut butter": {"bad": {"butter", "peanuts", "peanut"}},
        }
        for phrase, config in compounds.items():
            if phrase in display or phrase in item:
                if phrase not in all_text:
                    add(findings, recipe_id, line_index, "error", "head_noun_compound_lost", f"{phrase} compound identity was not preserved")
                if m in config["bad"]:
                    add(findings, recipe_id, line_index, "error", "head_noun_collapse", f"{phrase} collapsed to head noun {m!r}")
    elif case == "parenthetical_examples":
        expected_terms = []
        if "cointreau" in display or "grand marnier" in display:
            expected_terms.extend(["cointreau", "grand marnier"])
            if m and m not in {"orange liqueur", "liqueur"} and ("cointreau" in m or "grand marnier" in m):
                add(findings, recipe_id, line_index, "error", "parenthetical_brand_as_identity", "brand example became machine identity")
        if "thighs" in display or "drumsticks" in display:
            expected_terms.extend(["thigh", "drumstick"])
        missing = [term for term in expected_terms if term not in all_text]
        if missing:
            add(findings, recipe_id, line_index, "error", "parenthetical_examples_lost", f"parenthetical examples not preserved: {', '.join(missing)}")
    elif case == "bone_in_yield":
        if has_any_text(display, "bone-in", "bone in") and not has_any_text(all_text, "bone-in", "bone_in", "bone in"):
            add(findings, recipe_id, line_index, "error", "bone_in_lost", "bone-in state was not preserved")
        if stat == "CALCULATION_READY" and pol == "all_input":
            add(findings, recipe_id, line_index, "error", "bone_in_all_input", "bone-in item was marked all-input calculation-ready without yield policy")
        sg = source_grams(ing)
        cg = consumed_grams(ing)
        if sg is not None and cg is not None and abs(cg - sg) < 0.001:
            add(findings, recipe_id, line_index, "error", "bone_in_full_consumed", "bone-in consumed_grams equals source_grams")
    elif case == "parsed_item_hides_display_options":
        if m == "topping" or norm_text(n.get("product_identity")).lower() == "topping":
            add(findings, recipe_id, line_index, "error", "display_options_hidden_by_item", "parsed item 'topping' hid real display foods")
        if not has_alternatives(ing) and not has_component(ing, "corn") and not has_component(ing, "cracker") and "cheddar" not in all_text:
            add(findings, recipe_id, line_index, "error", "display_options_not_preserved", "display options were not preserved as alternatives/components")
    elif case == "blend_identity_preservation":
        if has_any_text(display, "cheese blend", "mexican blend", "four-cheese", "6 cheese", "six cheese"):
            if m in {"cheese", "cheddar cheese", "monterey jack cheese"}:
                add(findings, recipe_id, line_index, "error", "blend_collapsed_to_single_food", "cheese blend collapsed to a single/generic cheese")
            if not has_any_text(all_text, "blend", "3-cheese", "three-cheese", "6 cheese", "six cheese", "mexican"):
                add(findings, recipe_id, line_index, "error", "blend_identity_lost", "cheese blend identity was not preserved")
        if has_any_text(display, "bean mix", "bean soup mix", "16-bean", "15-bean", "7 bean", "mixed beans"):
            if has_any_text(m, "pinto", "kidney", "black bean") and not has_any_text(all_text, "mix", "blend", "composition"):
                add(findings, recipe_id, line_index, "error", "bean_mix_proxy_single_bean", "bean mix collapsed to a single bean proxy")
            if not has_any_text(all_text, "mix", "blend", "16-bean", "15 bean", "7 bean", "bean soup"):
                add(findings, recipe_id, line_index, "error", "bean_mix_identity_lost", "bean mix identity was not preserved")


def validate(source_rows: list[dict[str, Any]], candidate_rows: list[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []
    candidates = by_recipe(candidate_rows)
    for source in source_rows:
        recipe_id = source.get("recipe_id")
        rid = norm_text(recipe_id)
        candidate = candidates.get(rid)
        if candidate is None:
            add(findings, recipe_id, "*", "error", "missing_recipe", "candidate output missing recipe")
            continue
        c_ingredients = candidate_ingredients(candidate)
        for ing in c_ingredients.values():
            check_general(findings, recipe_id, ing)
        for stress in source.get("stress_lines", []):
            line_index = stress.get("line_index")
            try:
                idx = int(line_index)
            except (TypeError, ValueError):
                continue
            ing = c_ingredients.get(idx)
            if ing is None:
                add(findings, recipe_id, line_index, "error", "missing_line", "candidate output missing stress line")
                continue
            check_case(findings, recipe_id, stress, ing)
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--candidate", type=Path, required=True, help="Nebius output JSONL, one recipe object per line")
    parser.add_argument("--out", type=Path, help="Optional findings JSONL path")
    args = parser.parse_args()

    findings = validate(load_jsonl(args.source), load_jsonl(args.candidate))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as f:
            for finding in findings:
                f.write(json.dumps(finding.__dict__, ensure_ascii=False) + "\n")

    errors = sum(1 for finding in findings if finding.severity == "error")
    warnings = sum(1 for finding in findings if finding.severity == "warning")
    print(json.dumps({"errors": errors, "warnings": warnings, "findings": len(findings)}, indent=2))
    for finding in findings[:50]:
        print(f"{finding.severity}\t{finding.recipe_id}\t{finding.line_index}\t{finding.code}\t{finding.message}")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
