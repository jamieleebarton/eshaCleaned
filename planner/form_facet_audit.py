"""Line-aware form/facet checks for planner purchases.

The planner buys packages by aggregated concept key.  This module joins a plan
back to recipe lines so high-risk recipe intent such as "blueberry bagels",
"ham steak", "head lettuce", or "raw chicken breast" is not lost behind a
generic concept-level SKU.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def norm(text: str | None) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has_any(text: str | None, terms: list[str] | tuple[str, ...] | set[str]) -> bool:
    hay = f" {norm(text)} "
    return any(f" {norm(term)} " in hay for term in terms if norm(term))


def all_package_names(purchase_row: dict) -> list[str]:
    packages = purchase_row.get("selected_packages") or []
    names = [pkg.get("name", "") for pkg in packages if pkg.get("name")]
    if names:
        return names
    sku = purchase_row.get("selected_sku", "")
    return [sku] if sku else []


def pound_quantities(display: str) -> list[float]:
    text = unicodedata.normalize("NFKC", display or "").replace("⁄", "/")
    values: list[float] = []
    pattern = re.compile(
        r"(?<![\d/])(?:(\d+)\s+)?"
        r"(?:(\d+)\s*/\s*(\d+)|(\d+(?:\.\d+)?))\s*"
        r"(?:lb|lbs|pound|pounds)\b",
        re.I,
    )
    for m in pattern.finditer(text):
        whole = float(m.group(1) or 0)
        if m.group(2) and m.group(3):
            denom = float(m.group(3))
            if denom:
                values.append(whole + float(m.group(2)) / denom)
        elif m.group(4):
            values.append(float(m.group(4)))
    return values


def total_weight_range_grams(display: str) -> tuple[float, float] | None:
    text = unicodedata.normalize("NFKC", display or "").replace("⁄", "/")
    pattern = re.compile(
        r"\b(?:about|approximately|approx\.?|around)?\s*"
        r"(\d+(?:\.\d+)?)\s*(?:to|[-–—])\s*(\d+(?:\.\d+)?)\s*"
        r"(lb|lbs|pound|pounds|oz|ounce|ounces|kg|kilogram|kilograms|g|gram|grams)\s+total\b",
        re.I,
    )
    m = pattern.search(text)
    if not m:
        return None
    low = float(m.group(1))
    high = float(m.group(2))
    unit = m.group(3).lower()
    factor = 453.592
    if unit in {"oz", "ounce", "ounces"}:
        factor = 28.3495
    elif unit in {"kg", "kilogram", "kilograms"}:
        factor = 1000.0
    elif unit in {"g", "gram", "grams"}:
        factor = 1.0
    return min(low, high) * factor, max(low, high) * factor


@dataclass(frozen=True)
class Finding:
    issue_type: str
    severity: str
    message: str
    expected: str
    actual: str


def gram_bridge_findings(line: dict) -> list[Finding]:
    """Find obvious recipe-side gram bridge drift for high-signal patterns."""
    out: list[Finding] = []
    display = line.get("display", "") or ""
    item_text = norm(line.get("ingredient_item", ""))
    text = norm(f"{display} {line.get('ingredient_item', '')}")
    try:
        grams = float(line.get("grams_resolved") or line.get("grams") or 0)
    except (TypeError, ValueError):
        grams = 0.0
    try:
        qty = float(line.get("qty") or 0)
    except (TypeError, ValueError):
        qty = 0.0
    unit = norm(line.get("unit", ""))

    head_unit = unit in {"", "head", "heads"}
    explicit_head_qty = bool(
        re.search(r"\b\d+(?:\.\d+)?\s+(?:small|medium|large)?\s*heads?\s+lettuce\b", norm(display))
    )
    if (
        "lettuce" in text
        and "head" in text
        and (head_unit or explicit_head_qty)
        and grams
        and not (250 <= grams <= 900)
    ):
        out.append(Finding(
            "bad_grams",
            "blocker",
            "Head lettuce line has implausible grams.",
            "head lettuce roughly 250-900g",
            f"{grams:g}g",
        ))

    if unit in {"lb", "lbs", "pound", "pounds"} and grams > 0:
        pound_qtys = pound_quantities(display)
        candidate_qtys = pound_qtys or ([qty] if qty > 0 else [])
        expected_values = [q * 453.592 for q in candidate_qtys if q > 0]
        if expected_values and not any(
            abs(grams - expected) <= max(75.0, expected * 0.18)
            for expected in expected_values
        ):
            expected = expected_values[0]
            out.append(Finding(
                "bad_grams",
                "blocker",
                "Pound quantity drifted away from lb-to-gram bridge.",
                f"{expected:.0f}g +/-18%",
                f"{grams:g}g",
            ))

    range_total = total_weight_range_grams(display)
    if range_total and grams > 0:
        low, high = range_total
        if not (low * 0.85 <= grams <= high * 1.15):
            out.append(Finding(
                "bad_grams",
                "blocker",
                "Total weight range drifted away from displayed total pounds/ounces.",
                f"{low:.0f}-{high:.0f}g from display range",
                f"{grams:g}g",
            ))

    if unit in {"tsp", "teaspoon", "teaspoons"} and qty > 0 and has_any(item_text, {"salt"}) and grams > 0:
        expected_low = 4.0 * qty
        expected_high = 7.5 * qty
        if not (expected_low <= grams <= expected_high):
            out.append(Finding(
                "bad_grams",
                "warning",
                "Salt teaspoon grams outside expected household bridge range.",
                f"{expected_low:.1f}-{expected_high:.1f}g",
                f"{grams:g}g",
            ))

    return out


def line_sku_findings(line: dict, priced_concept_key: str, package_names: list[str]) -> list[Finding]:
    """Compare recipe-line intent against actual selected package names."""
    out: list[Finding] = []
    text = norm(" ".join([
        line.get("display", ""),
        line.get("ingredient_item", ""),
        line.get("facet_flavor", ""),
        line.get("facet_form", ""),
        line.get("facet_processing", ""),
        line.get("facet_claims", ""),
        line.get("normalized_form_facets", ""),
        line.get("normalized_processing_facets", ""),
        line.get("normalized_identity_phrase", ""),
    ]))
    sku_text = norm(" ".join(package_names))
    intended_concept_key = line.get("recipe_concept_key") or priced_concept_key
    cp = intended_concept_key.split("|", 1)[0]
    cp_norm = norm(cp)
    package_label = " | ".join(package_names)

    out.extend(concept_sku_class_findings(intended_concept_key, package_names, text))

    if "bagel" in cp_norm and "blueberry" in text:
        if not has_any(sku_text, {"blueberry"}):
            out.append(Finding(
                "wrong_facet",
                "blocker",
                "Blueberry bagel intent did not reach selected bagel package.",
                "selected package contains blueberry",
                package_label,
            ))

    if "ham" in cp_norm:
        product_is_lunch_kit = has_any(
            sku_text,
            {"lunchmaker", "lunchmakers", "lunch maker", "lunch kit", "snack kit", "smalls"},
        )
        target_allows_lunch_kit = has_any(
            text,
            {"lunchmaker", "lunch maker", "lunch kit", "snack kit"},
        )
        product_is_deli = has_any(
            sku_text,
            {
                "lunch meat", "lunchmeat", "deli", "thin sliced",
                "ultra thin", "sandwich sliced", "sliced lunch",
            },
        )
        target_allows_deli = has_any(
            text,
            {
                "deli ham", "lunch meat", "lunchmeat", "thin sliced ham",
                "sliced ham", "ham slices", "slices ham", "sandwich ham",
                "chopped ham", "diced ham", "cubed ham",
            },
        )
        if re.search(r"\bslices?\s+(?:[a-z0-9]+\s+){0,3}ham\b|\bham\s+slices?\b", text):
            target_allows_deli = True
        target_wants_cut = has_any(
            text,
            {
                "ham steak", "whole ham", "spiral ham", "bone in ham",
                "ham roast", "ham hock", "picnic ham", "shank ham",
            },
        )
        if product_is_lunch_kit and not target_allows_lunch_kit:
            out.append(Finding(
                "wrong_form",
                "blocker",
                "Ham recipe line selected a lunch/snack kit instead of ham.",
                "standalone ham product, or route LunchMaker-style products to lunch kits",
                package_label,
            ))
        if product_is_deli and (target_wants_cut or not target_allows_deli):
            out.append(Finding(
                "wrong_form",
                "blocker",
                "Ham recipe line selected deli/lunchmeat-style ham.",
                "ham cut/steak/roast product, or route deli ham to lunch meat",
                package_label,
            ))

    if "corned beef" in cp_norm:
        product_is_lunch_meat = has_any(
            sku_text,
            {
                "lunch meat", "lunchmeat", "deli", "thin sliced",
                "ultra thin", "sandwich sliced", "sliced lunch",
            },
        )
        target_allows_lunch_meat = has_any(
            text,
            {
                "deli corned beef", "thinly sliced corned beef",
                "sliced cooked corned beef", "sliced corned beef",
                "corned beef lunch meat", "corned beef lunchmeat",
            },
        )
        if product_is_lunch_meat and not target_allows_lunch_meat:
            out.append(Finding(
                "wrong_form",
                "blocker",
                "Corned beef recipe line selected deli/lunchmeat-style corned beef.",
                "canned/whole corned beef, or route deli corned beef to lunch meat",
                package_label,
            ))

    if "chicken breast" in cp_norm:
        bad_chicken_forms = {
            "canned", "pouch", "chunk chicken", "chicken salad", "lunch meat",
            "lunchmeat", "deli", "nugget", "breaded", "fully cooked",
            "rotisserie", "grilled strips",
        }
        if has_any(sku_text, bad_chicken_forms):
            out.append(Finding(
                "wrong_form",
                "blocker",
                "Raw chicken breast selected a prepared/canned/deli form.",
                "raw chicken breast package",
                package_label,
            ))

    if has_any(text, {"lean pork", "diced pork", "pork strips"}) and has_any(
        sku_text,
        {"sausage", "chorizo", "ham", "bacon"},
    ):
        out.append(Finding(
            "wrong_form",
            "blocker",
            "Plain lean/diced pork line selected sausage/ham/bacon.",
            "fresh pork stew meat, pork loin, or similar plain pork cut",
            package_label,
        ))

    if has_any(text, {"chorizo"}) and package_names and not has_any(sku_text, {"chorizo"}):
        out.append(Finding(
            "wrong_form",
            "blocker",
            "Chorizo recipe line selected a non-chorizo sausage.",
            "chorizo sausage",
            package_label,
        ))

    if "lettuce" in cp_norm and (
        "head" in text
        or has_any(text, {"lettuce leaf", "lettuce leaves"})
    ):
        if has_any(sku_text, {"shredded", "salad kit", "chopped salad", "lettuce blend", "bag"}):
            out.append(Finding(
                "wrong_form",
                "blocker",
                "Whole/leaf lettuce line selected shredded/bagged lettuce.",
                "whole/head lettuce package",
                package_label,
            ))

    return out


def concept_sku_class_findings(
    concept_key: str,
    package_names: list[str],
    line_text: str = "",
) -> list[Finding]:
    """Catch product-class contradictions visible from concept path + SKU.

    These checks are audit gates only. The fix for a hit should be to move the
    SKU to its correct canonical path/HTC code, or repair the recipe concept
    route, not to hide it inside picker logic.
    """
    out: list[Finding] = []
    cp = concept_key.split("|", 1)[0]
    cp_norm = norm(cp)
    sku_text = norm(" ".join(package_names))
    line_norm = norm(line_text)
    actual = " | ".join(package_names)

    def add(message: str, expected: str) -> None:
        out.append(Finding("wrong_class", "blocker", message, expected, actual))

    if (
        "cheddar" in cp_norm
        and "snack cheese" not in cp_norm
        and has_any(sku_text, {"snack sticks", "snack bites", "cheese snack"})
    ):
        if not has_any(line_norm, {"snack sticks", "snack bites", "cheese sticks", "cheese snack"}):
            add("Cheddar concept selected snack/bite cheese packaging.", "standard cheddar block/slice/shred package")

    if "baby carrots" in cp_norm and has_any(
        sku_text,
        {"peas carrots", "peas and carrots", "canned", "cups", "4 oz cups"},
    ):
        add("Fresh baby carrot concept selected canned/mixed carrots.", "fresh baby carrots")

    if cp_norm.startswith("pantry oil vegetable oil") and has_any(
        sku_text,
        {"margarine", "spread", "oil sticks", "vegetable oil sticks", "veg oil sticks"},
    ):
        add("Liquid vegetable oil concept selected margarine/spread sticks.", "bottled liquid vegetable oil")

    if "brown sugar" in cp_norm and has_any(sku_text, {"agave", "nectar", "honey", "syrup"}):
        add("Brown sugar concept selected liquid sweetener.", "brown sugar")

    if cp_norm in {"dairy cream", "dairy cream creme fraiche"} and has_any(
        sku_text,
        {"finishing sugar", "sugar", "sprinkles"},
    ):
        add("Cream concept selected sugar/decorator product.", "cream or creme fraiche")

    if "avocado" in cp_norm and not has_any(sku_text, {"avocado", "avocados"}):
        add("Avocado concept selected non-avocado product.", "fresh or prepared avocado")

    if "bacon" in cp_norm and has_any(
        sku_text,
        {"veggie", "meatless", "plant based", "plant based", "vegetarian", "smart bacon"},
    ):
        add("Bacon concept selected plant-based/meatless bacon.", "pork bacon unless recipe asks plant-based")

    if cp_norm == "meat seafood pork" and has_any(sku_text, {"sausage", "chorizo", "ham"}):
        add("Generic pork concept selected sausage/chorizo/ham.", "plain pork cut or route SKU to the specific pork subtype")

    if "chorizo" in cp_norm and package_names and not has_any(sku_text, {"chorizo"}):
        add("Chorizo concept selected non-chorizo sausage.", "chorizo sausage")

    if "oregano" in cp_norm and (has_any(sku_text, {"bay leaves", "bay leaf"}) or not has_any(sku_text, {"oregano"})):
        add("Oregano concept selected a different herb/spice.", "oregano")

    if "limes" in cp_norm and has_any(
        sku_text,
        {"juice cocktail", "citrus splash", "splash", "drink", "soda", "seltzer"},
    ):
        add("Fresh lime concept selected beverage/juice product.", "fresh limes")

    if "hot pepper sauce" in cp_norm and has_any(sku_text, {"hollandaise"}):
        add("Hot pepper sauce concept selected hollandaise sauce mix.", "hot pepper sauce")

    if "pierog" in cp_norm and has_any(
        sku_text,
        {"mashed potatoes", "instant potatoes", "complete potatoes", "potatoes pouch"},
    ):
        add("Pierogy concept selected potato mix instead of filled pierogies.", "frozen pierogies")

    if cp_norm.startswith("frozen ice cream") and has_any(sku_text, {"ice cream cups"}) and not has_any(
        sku_text,
        {"vanilla", "chocolate", "strawberry", "sundae", "fudge", "caramel", "fl oz"},
    ):
        add("Frozen ice cream concept selected dry ice-cream cups/cones.", "actual frozen ice cream")

    return out
