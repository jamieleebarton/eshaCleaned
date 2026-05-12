"""Public entry point for recipe line calculation.

calculate_line(display, item, grams_hint) -> Resolution

Composition:
  non_food lexicon check -> layered_resolver -> portion_resolver -> sr28_nutrition -> product_matcher
"""
from __future__ import annotations
import csv
import re
from pathlib import Path
from schema import Resolution, NutritionEstimate, NutritionState, ShoppingState, TrustLayer, ProductCandidate
from non_food_words import is_non_food
from layered_resolver import LayeredResolver
from portion_resolver import resolve_grams, resolve_grams_generic
from sr28_nutrition import nutrition_for_grams
from esha_nutrition import nutrition_for_esha
from product_matcher import match_products, search_products
from normalizer import _normalize_text
from taxonomy_lookup import lookup_taxonomy, metadata_kwargs

_DEFAULT_RESOLVER: LayeredResolver | None = None
_CANONICAL_PER_100G: dict[str, dict[str, float]] | None = None
_FNDDS_PER_100G: dict[str, dict[str, float]] | None = None
_HOUSEHOLD_RULES: dict[tuple[str, str], float] | None = None
_TO_TASTE: dict[str, float] | None = None
_QTY_POLICIES: list[dict] | None = None
# Manual churn-queue overrides — kept here only for aliases/surface forms
# that don't have their own canonical_to_esha row but should still route
# through the reviewed-card overlay. The general rule (any canonical whose
# ESHA code has a reviewed contract) is enforced dynamically in
# _shopping_lab_overlay_keys() below.
_MANUAL_LAB_OVERLAY_KEYS = {
    "4 to 6 lb ham",
    "4 6 lb ham",
    "bone in ham",
    "boneless ham",
    "cookie pie crust",
    "fat free parmesan",
    "fresh mint",
    "green onion",
    "half ham",
    "ham roast",
    "lemon rind",
    "mint",
    "mint leaves",
    "oreo cookie pie crust",
    "mushroom",
    "mushrooms",
    "scallion",
    "scallions",
    "seedless grape",
    "seedless grapes",
    "southern comfort",
    "granulated sugar",
    "sugar",
    "white wine",
    "dry white wine",
    "dry white vermouth",
    "whole ham",
}


_REVIEWED_OVERLAY_CACHE: frozenset[str] | None = None


def _shopping_lab_overlay_keys() -> frozenset[str]:
    """Canonicals whose ESHA code has a reviewed contract. When a query hits
    one of these, the calculator prefers the reviewed-card result over the
    broad tagged-pricing fallback. Derived at import-time from
    esha_contracts.CONTRACTS + canonical_to_esha.csv so new reviewed modules
    activate automatically without hand-editing this list."""
    global _REVIEWED_OVERLAY_CACHE
    if _REVIEWED_OVERLAY_CACHE is not None:
        return _REVIEWED_OVERLAY_CACHE
    keys: set[str] = set(_MANUAL_LAB_OVERLAY_KEYS)
    try:
        from esha_contracts import CONTRACTS as _REVIEWED_CONTRACTS  # lazy
        reviewed_codes = {str(c).lstrip("0") for c in _REVIEWED_CONTRACTS.keys()}
        import csv as _csv
        from pathlib import Path as _P
        c2e_path = _P(__file__).resolve().parent / "canonical_to_esha.csv"
        if c2e_path.exists():
            for r in _csv.DictReader(c2e_path.open()):
                code = (r.get("esha_code") or "").lstrip("0")
                if code and code in reviewed_codes:
                    name = (r.get("canonical_name") or "").strip().lower()
                    if name:
                        keys.add(name)
    except Exception:
        pass
    _REVIEWED_OVERLAY_CACHE = frozenset(keys)
    return _REVIEWED_OVERLAY_CACHE


# Back-compat name. Anything that used to check _SHOPPING_LAB_OVERLAY_KEYS now
# sees the derived set — the legacy hardcoded membership list is gone.
_SHOPPING_LAB_OVERLAY_KEYS = _shopping_lab_overlay_keys()


def _r() -> LayeredResolver:
    global _DEFAULT_RESOLVER
    if _DEFAULT_RESOLVER is None:
        _DEFAULT_RESOLVER = LayeredResolver()
    return _DEFAULT_RESOLVER


def _canonical_per_100g() -> dict[str, dict[str, float]]:
    """Cached per_100g_* from canonical_items.csv — the FNDDS-derived fallback
    when a canonical has no SR28 code (Hestia's per_100g values for 6K+ rows
    where only FNDDS anchors exist). Guardrail #5 (no invented match) still
    applies: this is a reviewed registry value, not a silent guess."""
    global _CANONICAL_PER_100G
    if _CANONICAL_PER_100G is not None:
        return _CANONICAL_PER_100G
    path = Path(__file__).resolve().parent / "canonical_items.csv"
    out: dict[str, dict[str, float]] = {}
    if path.exists():
        with path.open() as f:
            for r in csv.DictReader(f):
                # Use same normalization the resolver uses so hyphenated
                # canonicals ('all-purpose flour') match resolver output.
                cn = _normalize_text(r.get("canonical_name") or "")
                if not cn:
                    continue
                # Accept per_100g_kcal=0.0 as a valid value — seasonings, salt,
                # water etc. have real zero-kcal profiles. Only skip when the
                # column is empty string (never populated).
                kcal_str = (r.get("per_100g_kcal") or "").strip()
                if kcal_str == "":
                    continue
                try:
                    kcal = float(kcal_str)
                except ValueError:
                    continue
                if kcal < 0:
                    continue
                try:
                    out[cn] = {
                        "kcal": kcal,
                        "protein": float(r.get("per_100g_protein_g") or 0),
                        "fat": float(r.get("per_100g_fat_g") or 0),
                        "carbs": float(r.get("per_100g_carbs_g") or 0),
                    }
                except ValueError:
                    continue
    _CANONICAL_PER_100G = out
    return out


def _fndds_per_100g() -> dict[str, dict[str, float]]:
    """Cached per_100g_* keyed by FNDDS code from data/fndds/fndds_nutrient_lookup.csv.
    Used when the canonical has an FNDDS code but the canonical_items.csv
    per_100g cache was never populated (tree-only seed or Phase 11 skipped it).
    Authoritative USDA FNDDS data; no guessing."""
    global _FNDDS_PER_100G
    if _FNDDS_PER_100G is not None:
        return _FNDDS_PER_100G
    path = Path(__file__).resolve().parent.parent / "data" / "fndds" / "fndds_nutrient_lookup.csv"
    out: dict[str, dict[str, float]] = {}
    if path.exists():
        with path.open() as f:
            for r in csv.DictReader(f):
                code = (r.get("fndds_code") or "").strip()
                if not code:
                    continue
                try:
                    kcal = float(r.get("energy_kcal") or 0)
                except ValueError:
                    kcal = 0.0
                if kcal <= 0:
                    continue
                try:
                    out[code] = {
                        "kcal": kcal,
                        "protein": float(r.get("protein_g") or 0),
                        "fat": float(r.get("fat_g") or 0),
                        "carbs": float(r.get("carbs_g") or 0),
                    }
                except ValueError:
                    continue
    _FNDDS_PER_100G = out
    return out


def _household_rules() -> dict[tuple[str, str], float]:
    """(concept_key, unit) -> grams_per_unit. concept_key may be '*'."""
    global _HOUSEHOLD_RULES
    if _HOUSEHOLD_RULES is not None:
        return _HOUSEHOLD_RULES
    out: dict[tuple[str, str], float] = {}
    active_path = (
        Path(__file__).resolve().parent.parent
        / "recipe_pricing"
        / "reviewed_household_portions.csv"
    )
    if active_path.exists():
        with active_path.open() as f:
            for r in csv.DictReader(f):
                item = (r.get("item") or "").strip().lower()
                unit = _normalize_unit((r.get("unit") or "").strip().lower())
                try:
                    g = float(r.get("grams_per_unit") or 0)
                except ValueError:
                    continue
                if not item or not unit or g <= 0:
                    continue
                if item == "*":
                    out.setdefault(("*", unit), g)
                    continue
                item_keys = {item, _normalize_text(item)}
                if "|" in item:
                    item_keys.add(item)
                for item_key in item_keys:
                    if item_key:
                        concept_key = item_key if "|" in item_key else f"{item_key}|||"
                        out.setdefault((concept_key, unit), g)

    # Compatibility fallback only. The active authority is
    # recipe_pricing/reviewed_household_portions.csv; this legacy file is kept
    # so old calculator fixtures still run in checkouts where the active CSV is
    # absent.
    path = Path(__file__).resolve().parent / "reviewed_household_unit_gram_rules.csv"
    if path.exists():
        with path.open() as f:
            for r in csv.DictReader(f):
                if (r.get("review_status") or "").strip() != "approved":
                    continue
                ck = (r.get("concept_key") or "").strip().lower()
                unit = (r.get("unit") or "").strip().lower()
                try:
                    g = float(r.get("grams_per_unit") or 0)
                except ValueError:
                    continue
                if unit and g > 0 and (ck, unit) not in out:
                    out[(ck, unit)] = g
    _HOUSEHOLD_RULES = out
    return out


def _to_taste_defaults() -> dict[str, float]:
    """concept_key -> default grams for to-taste lines."""
    global _TO_TASTE
    if _TO_TASTE is not None:
        return _TO_TASTE
    out: dict[str, float] = {}
    path = Path(__file__).resolve().parent / "reviewed_to_taste_defaults.csv"
    if path.exists():
        with path.open() as f:
            for r in csv.DictReader(f):
                ck = (r.get("concept_key") or "").strip().lower()
                try:
                    g = float(r.get("default_grams") or 0)
                except ValueError:
                    continue
                if ck and g > 0:
                    out[ck] = g
    _TO_TASTE = out
    return out


def _qty_policies() -> list[dict]:
    """Reviewed quantity policies for lines with missing or non-numeric qty."""
    global _QTY_POLICIES
    if _QTY_POLICIES is not None:
        return _QTY_POLICIES
    out: list[dict] = []
    path = Path(__file__).resolve().parent / "reviewed_quantity_policies.csv"
    if path.exists():
        with path.open() as f:
            for r in csv.DictReader(f):
                if (r.get("review_status") or "").strip() != "approved":
                    continue
                if (r.get("action") or "").strip() != "apply_default":
                    continue
                ck = (r.get("concept_key") or "").strip().lower()
                inc = (r.get("include_regex") or "").strip()
                try:
                    g = float(r.get("default_grams") or 0)
                except ValueError:
                    continue
                if not ck or g <= 0:
                    continue
                try:
                    rx = re.compile(inc) if inc else None
                except re.error:
                    rx = None
                out.append({"concept_key": ck, "regex": rx, "grams": g})
    _QTY_POLICIES = out
    return out


_UNIT_SINGULAR = {
    "eggs": "egg", "cloves": "clove", "leaves": "leaf", "sticks": "stick",
    "onions": "onion", "tomatoes": "tomato", "apples": "apple",
    "bananas": "banana", "lemons": "lemon", "limes": "lime",
    "oranges": "orange", "potatoes": "potato", "carrots": "carrot",
    "slices": "slice", "pieces": "piece", "sprigs": "sprig",
    "cups": "cup", "tablespoons": "tbsp", "tablespoon": "tbsp",
    "teaspoons": "tsp", "teaspoon": "tsp", "ounces": "oz", "ounce": "oz",
    "pounds": "lb", "pound": "lb", "grams": "g", "gram": "g",
    "kilograms": "kg", "kilogram": "kg", "liters": "l", "liter": "l",
    "milliliters": "ml", "milliliter": "ml",
    "packages": "package", "packets": "packet", "cans": "can", "jars": "jar",
    "boxes": "box", "bags": "bag", "heads": "head", "bunches": "bunch",
    "breasts": "breast", "fillets": "fillet", "thighs": "thigh",
    "bay": "leaf",
}


def _normalize_unit(unit: str) -> str:
    u = (unit or "").strip().lower()
    return _UNIT_SINGULAR.get(u, u)


_KNOWN_MEASUREMENT_UNITS = {
    "g", "kg", "mg", "oz", "lb", "lbs", "ml", "l", "cc",
    "cup", "cups", "tbsp", "tsp", "tablespoon", "tablespoons", "teaspoon", "teaspoons",
    "pint", "pt", "quart", "qt", "gallon", "gal", "fl",
    "can", "cans", "jar", "jars", "package", "packages", "packet", "packets",
    "bag", "bags", "box", "boxes", "bottle", "bottles", "tub", "tubs", "container",
    "slice", "slices", "piece", "pieces", "sprig", "sprigs", "pinch", "dash",
    "head", "heads", "bunch", "bunches", "stalk", "stalks", "clove", "cloves",
    "leaf", "leaves", "stick", "sticks", "sheet", "sheets", "strip", "strips",
    "each", "count", "ea", "pc", "pcs", "handful", "scoop", "drop", "drops",
}


_CANONICAL_NAMES_CACHE: list[str] | None = None


def _load_canonical_name_set() -> list[str]:
    """Load canonical_items.csv canonical_names sorted by token count desc for longest-match."""
    global _CANONICAL_NAMES_CACHE
    if _CANONICAL_NAMES_CACHE is not None:
        return _CANONICAL_NAMES_CACHE
    import csv as _csv
    path = Path(__file__).resolve().parent / "canonical_items.csv"
    names: list[str] = []
    if path.exists():
        with path.open() as f:
            for r in _csv.DictReader(f):
                n = (r.get("canonical_name") or "").strip()
                if n and (r.get("per_100g_kcal") or "").strip():
                    names.append(n)
    # longest (by words) first so "pasta sauce" wins over "sauce"
    names.sort(key=lambda s: (-len(s.split()), -len(s)))
    _CANONICAL_NAMES_CACHE = names
    return names


def _substring_canonical_fallback(text: str) -> str | None:
    """Find the longest canonical_name that appears as a whole-word substring of `text`."""
    if not text:
        return None
    low = text.lower()
    for n in _load_canonical_name_set():
        # whole-word match (avoids "pea" matching inside "peach")
        pat = r"\b" + re.escape(n.lower()) + r"\b"
        if re.search(pat, low):
            return n
    return None


def _household_grams(concept_key: str, unit: str, display_l: str) -> float | None:
    rules = _household_rules()
    u = _normalize_unit(unit)
    # Build candidate concept_keys: the concept itself, its plural form
    # (resolver singular-folds "oats" → "oat" but rules may be keyed "oats|||"),
    # and the "*" wildcard.
    candidates = [concept_key]
    if concept_key and concept_key.endswith("|||"):
        base = concept_key[:-3]
        # plural variants
        if base and not base.endswith("s"):
            candidates.append(base + "s|||")
        if base.endswith("y"):
            candidates.append(base[:-1] + "ies|||")
        # head-noun fallback: "rolled oat" → "oat", "steel cut oats" → "oats"
        # Rule for the base ingredient (oat/oats) often applies to modified
        # variants (rolled oats, quick oats, steel-cut oats, etc.)
        parts = base.split()
        if len(parts) > 1:
            head = parts[-1]
            candidates.append(head + "|||")
            if not head.endswith("s"):
                candidates.append(head + "s|||")
    candidates.append("*")
    for ck in candidates:
        if (ck, u) in rules:
            return rules[(ck, u)]
    # Count-like fallback: if unit matches the canonical's first word
    # (e.g. "eggs" → canonical "egg"), treat as count.
    first_word = concept_key.split("|")[0].split()[0] if concept_key else ""
    if first_word and (u == first_word or u == first_word + "s"):
        if (concept_key, "count") in rules:
            return rules[(concept_key, "count")]
    # "each" / "count" sometimes comes from "1 egg" direct.
    if u in ("each", "count") and (concept_key, "count") in rules:
        return rules[(concept_key, "count")]
    # NEW 2026-04-22: if parser extracted a non-unit word as `unit`
    # (e.g. "4 boneless skinless chicken breasts" → unit="boneless"),
    # it's clearly not a measurement unit. Fall back to count.
    if u and u not in _KNOWN_MEASUREMENT_UNITS:
        if (concept_key, "count") in rules:
            return rules[(concept_key, "count")]
        # last resort: generic wildcard count rule (usually '*, count, 30g')
        if ("*", "count") in rules:
            return rules[("*", "count")]
    return None


_MIXED_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s*/\s*(\d+)\s*(?P<unit>[a-zA-Z]+)\b")
_FRAC_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*(?P<unit>[a-zA-Z]+)\b")
_RANGE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?P<unit>[a-zA-Z]+)\b")
_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?P<unit>[a-zA-Z]+)\b")


def _strip_qty_unit_prefix(s: str) -> str:
    """Strip a leading '<qty> <unit> ' prefix from an ingredient string.

    Used when the `item` field contains the full 'display' text (qty + unit + name)
    rather than the normalised name.
    """
    if not s:
        return s
    norm = s.replace("\u2044", "/")
    norm = re.sub(r"(\d)([\u00BC-\u00BE\u2153-\u215E])", r"\1 \2", norm)
    norm = (norm.replace("\u00BD", "1/2").replace("\u00BC", "1/4")
                 .replace("\u00BE", "3/4").replace("\u2153", "1/3")
                 .replace("\u2154", "2/3").replace("\u215B", "1/8")
                 .replace("\u215C", "3/8").replace("\u215D", "5/8")
                 .replace("\u215E", "7/8"))
    _SECONDARY_UNIT_WORDS = (
        "packet", "packets", "package", "packages", "can", "cans", "jar", "jars",
        "box", "boxes", "bag", "bags", "bottle", "bottles", "tub", "tubs",
        "container", "containers", "envelope", "envelopes", "stick", "sticks",
        "head", "heads", "bunch", "bunches", "loaf", "loaves", "pinch", "dash",
    )

    def _strip_trailing_unit_words(rem: str) -> str:
        # repeatedly strip leading secondary-unit words: "packet X" -> "X"
        for _ in range(3):
            mm = re.match(r"^([a-z]+)\s+(.+)$", rem, re.IGNORECASE)
            if mm and mm.group(1).lower() in _SECONDARY_UNIT_WORDS:
                rem = mm.group(2).strip()
            else:
                break
        return rem

    for rx in (_MIXED_RE, _FRAC_RE, _RANGE_RE, _NUM_RE):
        m = rx.match(norm)
        if m:
            remainder = norm[m.end():].strip()
            remainder = re.sub(r"^\([^)]*\)\s*", "", remainder).strip()
            remainder = _strip_trailing_unit_words(remainder)
            return remainder or s

    # Fallback: "<qty> (<note>) <unit> <rest>" pattern — qty then parenthetical
    # then unit word. Covers "1 (8oz) tub cool whip" / "1 (.25 oz) packet yeast".
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*\([^)]*\)\s*(.+)$", norm)
    if m:
        remainder = m.group(2).strip()
        remainder = _strip_trailing_unit_words(remainder)
        return remainder or s

    return s


def _parse_qty_unit(display: str) -> tuple[float | None, str]:
    if not display:
        return None, ""
    s = display.replace("\u2044", "/")
    s = re.sub(r"(\d)([\u00BC-\u00BE\u2153-\u215E])", r"\1 \2", s)
    s = (s.replace("\u00BD", "1/2").replace("\u00BC", "1/4")
          .replace("\u00BE", "3/4").replace("\u2153", "1/3")
          .replace("\u2154", "2/3").replace("\u215B", "1/8")
          .replace("\u215C", "3/8").replace("\u215D", "5/8")
          .replace("\u215E", "7/8"))
    m = _MIXED_RE.match(s)
    if m:
        try:
            qty = float(m.group(1)) + float(m.group(2)) / float(m.group(3))
            return qty, m.group("unit").lower()
        except Exception:
            return None, ""
    m = _FRAC_RE.match(s)
    if m:
        try:
            qty = float(m.group(1)) / float(m.group(2))
            return qty, m.group("unit").lower()
        except Exception:
            return None, ""
    m = _RANGE_RE.match(s)
    if m:
        try:
            qty = (float(m.group(1)) + float(m.group(2))) / 2
            return qty, m.group("unit").lower()
        except Exception:
            return None, ""
    m = _NUM_RE.match(s)
    if m:
        try:
            return float(m.group(1)), m.group("unit").lower()
        except Exception:
            return None, ""
    # Fallback: "N (X unit) ..." — pull qty+unit from INSIDE the parenthetical.
    # e.g. "1 (8 oz) tub cool whip" -> qty=8, unit='oz'
    #      "1 (.25 oz) packet active dry yeast" -> qty=0.25, unit='oz'
    m = re.match(r"^\s*\d+(?:\.\d+)?\s*\(\s*(\.?\d+(?:\.\d+)?)\s*([a-zA-Z]+)\b", s)
    if m:
        try:
            qty_s = m.group(1)
            if qty_s.startswith("."):
                qty_s = "0" + qty_s
            return float(qty_s), m.group(2).lower()
        except Exception:
            return None, ""
    return None, ""


_OVERRIDES: dict[tuple[str, str], str] | None = None


def _load_overrides() -> dict[tuple[str, str], str]:
    """Load Codex's 10k recipe-specific ambiguous→specific overrides."""
    global _OVERRIDES
    if _OVERRIDES is not None:
        return _OVERRIDES
    path = Path(__file__).resolve().parent / "output" / "recipe_ingredient_overrides_approved.csv"
    out: dict[tuple[str, str], str] = {}
    if path.exists():
        with path.open() as f:
            for r in csv.DictReader(f):
                rid = (r.get("recipe_id") or "").strip()
                item = (r.get("ambiguous_item") or "").strip().lower()
                specific = (r.get("llm_specific_product") or "").strip()
                if rid and item and specific:
                    out[(rid, item)] = specific
    _OVERRIDES = out
    return out


def calculate_line(display: str, item: str = "", grams_hint: float | None = None,
                   recipe_id: str | int | None = None) -> Resolution:
    # 1. Non-food gate
    text_for_lex = item or display
    if is_non_food(text_for_lex):
        return Resolution(
            canonical_name="", sr28_fdc_id="", fndds_code="", pseudo_code="",
            nutrition_state=NutritionState.NON_FOOD,
            shopping_state=ShoppingState.NON_FOOD,
            trust_layer=TrustLayer.L8_NUTRITION_UNKNOWN,
            grams=None, alternatives=[], path=[f"non_food: {text_for_lex!r}"],
        )

    # 1.5. Recipe-specific override (Codex's 3-model-agreement overrides)
    override_applied = None
    if recipe_id is not None and item:
        key = (str(recipe_id), item.strip().lower())
        specific = _load_overrides().get(key)
        if specific:
            override_applied = f"{item} → {specific}"
            item = specific

    # 2. Layered resolver -> canonical + codes
    # If `item` still carries the qty+unit prefix (common when recipe_qa.db
    # has string ingredients rather than dicts), strip it so the resolver's
    # canonical lookup sees the ingredient name, not '1 cup fresh strawberries'.
    resolver_item = _strip_qty_unit_prefix(item) if item else item
    res = _r().resolve(item=resolver_item, display=display)
    if override_applied:
        res.path.append(f"override: {override_applied}")
    if res.trust_state == "non_food":
        return Resolution(
            canonical_name="", sr28_fdc_id="", fndds_code="", pseudo_code="",
            nutrition_state=NutritionState.NON_FOOD,
            shopping_state=ShoppingState.NON_FOOD,
            trust_layer=TrustLayer.L8_NUTRITION_UNKNOWN,
            grams=None, alternatives=[], path=res.path,
        )
    if res.canonical_name is None or res.canonical_name == "":
        # 2026-04-22 last-resort: substring fallback against canonical_items head words.
        # Handles long-tail phrases like 'white cheddar popcorn' → 'popcorn',
        # 'hot italian chicken sausage' → 'sausage', 'canned pasta sauce' → 'pasta sauce'.
        fallback = _substring_canonical_fallback(resolver_item or display)
        if fallback:
            res2 = _r().resolve(item=fallback, display=fallback)
            if res2.canonical_name:
                res = res2
                res.path.append(f"substring_fallback: {fallback!r}")
        if res.canonical_name is None or res.canonical_name == "":
            return Resolution(
                canonical_name="", sr28_fdc_id="", fndds_code="", pseudo_code="",
                nutrition_state=NutritionState.NUTRITION_UNKNOWN,
                shopping_state=ShoppingState.SHOPPING_GAP,
                trust_layer=TrustLayer.L8_NUTRITION_UNKNOWN,
                grams=None, alternatives=[], path=res.path,
            )

    # 3. Grams — SR28 food_portion first, generic water-density fallback, then
    # reviewed household_unit_gram_rules (count + per-concept units), finally
    # reviewed quantity_policies / to_taste_defaults for zero-qty lines.
    grams: float | None = grams_hint
    concept_key = f"{res.canonical_name}|||" if res.canonical_name else ""
    display_l = (display or "").lower()
    if grams is None:
        qty, unit = _parse_qty_unit(display)
        if qty is not None and unit:
            # Priority order: human-reviewed > SR28 food_portion > generic water density.
            # Human-reviewed household rules beat SR28 because SR28 cup values
            # sometimes refer to cooked form while recipes mean dry form
            # (e.g. oats: SR28 cup=156g cooked, recipe cup=80g dry rolled).
            gpu = _household_grams(concept_key, unit, display_l)
            if gpu is not None:
                grams = qty * gpu
            if grams is None:
                grams = resolve_grams(
                    sr28_fdc_id=res.sr28_fdc_id, fndds_code=res.fndds_code,
                    pseudo_code="", qty=qty, unit=unit,
                )
            if grams is None:
                grams = resolve_grams_generic(qty, unit)
        # Zero-qty lines: quantity_policies (pinch/dash/sprinkling/to taste)
        if grams is None and concept_key:
            for pol in _qty_policies():
                if pol["concept_key"] != concept_key:
                    continue
                rx = pol["regex"]
                if rx is None or rx.search(display):
                    grams = pol["grams"]
                    break
        # "to taste" catch-all
        if grams is None and concept_key and "to taste" in display_l:
            g = _to_taste_defaults().get(concept_key)
            if g is not None:
                grams = g
        # Bare-name fallback (2026-04-22): when display is just the ingredient name
        # with no numeric qty (e.g. "active dry yeast" or "cinnamon stick"),
        # assume qty=1 and use the concept's count rule if one exists.
        if grams is None and concept_key and qty is None:
            count_g = _household_grams(concept_key, "count", display_l)
            if count_g is not None:
                grams = count_g

    # 4. Nutrition source priority (per CLAUDE.md):
    # a) SR28 direct when canonical is a clean exact anchor (not proxy)
    # b) Esha Tier A label median — preferred for proxy-unreviewed canonicals
    #    (avoids serving misleading proxy nutrition; label medians are real)
    # c) SR28 proxy as fallback (carries REVIEWED_PROXY label)
    # d) canonical per_100g cache, FNDDS
    nut_obj: NutritionEstimate | None = None
    nut_via = ""
    if grams is not None:
        # Auto-batched proxy canonicals only: prefer Esha Tier A label median
        # over the polluted proxy SR28. Approved proxies (human-reviewed)
        # stay on SR28 so their REVIEWED_PROXY label reflects canonical trust.
        if res.proxy_unreviewed and res.esha_code:
            esha = nutrition_for_esha(res.esha_code)
            if esha and esha.get("tier") == "A_label_median" and esha.get("kcal") is not None:
                scale = grams / 100.0
                nut_obj = NutritionEstimate(
                    kcal=(esha.get("kcal") or 0.0) * scale,
                    protein_g=(esha.get("protein") or 0.0) * scale,
                    fat_g=(esha.get("fat") or 0.0) * scale,
                    carbs_g=(esha.get("carbs") or 0.0) * scale,
                )
                nut_via = "esha_tier_a_label_median"
        if nut_obj is None and res.sr28_fdc_id:
            d = nutrition_for_grams(res.sr28_fdc_id, grams)
            if d:
                nut_obj = NutritionEstimate(
                    kcal=d.get("kcal", 0.0), protein_g=d.get("protein", 0.0),
                    fat_g=d.get("fat", 0.0), carbs_g=d.get("carbs", 0.0),
                )
                nut_via = "sr28_direct"
        if nut_obj is None and res.canonical_name:
            row = _canonical_per_100g().get(_normalize_text(res.canonical_name))
            if row:
                scale = grams / 100.0
                nut_obj = NutritionEstimate(
                    kcal=row["kcal"] * scale,
                    protein_g=row["protein"] * scale,
                    fat_g=row["fat"] * scale,
                    carbs_g=row["carbs"] * scale,
                )
                nut_via = "canonical_per_100g_cache"
        if nut_obj is None and res.fndds_code:
            row = _fndds_per_100g().get(res.fndds_code.strip())
            if row:
                scale = grams / 100.0
                nut_obj = NutritionEstimate(
                    kcal=row["kcal"] * scale,
                    protein_g=row["protein"] * scale,
                    fat_g=row["fat"] * scale,
                    carbs_g=row["carbs"] * scale,
                )
                nut_via = "fndds_nutrient_lookup"

    # 5. Products
    shopping_canonical = res.shopping_canonical or res.canonical_name
    path = list(res.path)
    overlay_keys = {
        _normalize_text(display),
        _normalize_text(item),
        _normalize_text(shopping_canonical),
    }
    if overlay_keys & _SHOPPING_LAB_OVERLAY_KEYS:
        from surface_lab_calculator import calculate_lab

        lab = calculate_lab(display=display, item=item, grams=grams)
        shopping_canonical = lab.shopping_canonical or shopping_canonical
        products = [
            ProductCandidate(
                gtin_upc=p.gtin_upc,
                description=p.description,
                brand_name=p.brand_name,
                branded_food_category=p.category,
                source=p.source,
            )
            for p in lab.products
        ]
        path.append(f"shopping_lab_overlay:{shopping_canonical!r}:accepted={len(products)}")
    else:
        products = match_products(
            sr28_fdc_id=res.sr28_fdc_id,
            fndds_code=res.fndds_code,
            pseudo_code="",
            canonical=shopping_canonical,
        )
        if not products and shopping_canonical:
            products = search_products(shopping_canonical, limit=25, canonical=shopping_canonical)
            if products:
                path.append(f"shopping_fts_fallback:{shopping_canonical!r}:accepted={len(products)}")

    # 6. States — nutrition_state honors res.trust_state and proxy_unreviewed
    # so REVIEWED_PROXY canonicals don't get EXACT labels. CLAUDE.md rule 6.
    if not nut_obj:
        nutr_state = NutritionState.NUTRITION_UNKNOWN
    elif nut_via == "esha_tier_a_label_median":
        nutr_state = NutritionState.REVIEWED_LOCAL_LABEL_ANCHOR
    elif nut_via == "canonical_per_100g_cache":
        nutr_state = NutritionState.REVIEWED_LOCAL_LABEL_ANCHOR
    elif res.proxy_unreviewed or res.trust_state in (
        "reviewed_proxy", "sr28_fallback", "external_catalog"
    ):
        nutr_state = NutritionState.REVIEWED_PROXY
    elif nut_via == "sr28_direct":
        nutr_state = NutritionState.EXACT_USDA_ANCHOR
    else:
        nutr_state = NutritionState.REVIEWED_LOCAL_LABEL_ANCHOR

    # Shopping codes — mirror nutrition unless the proxy is auto-batched
    # (polluted SR28/FNDDS that no cook would shop against). CLAUDE.md
    # rule: proxy_unreviewed zeros shopping codes.
    if res.proxy_unreviewed:
        shop_sr28 = ""
        shop_fndds = ""
    else:
        shop_sr28 = res.sr28_fdc_id
        shop_fndds = res.fndds_code

    shop_state = (
        ShoppingState.SHOPPING_CANDIDATES_STRONG if len(products) >= 5
        else ShoppingState.SHOPPING_CANDIDATES_WEAK if products
        else ShoppingState.SHOPPING_GAP
    )
    taxonomy_meta = lookup_taxonomy(
        item=item,
        display=display,
        canonical_name=res.canonical_name or "",
        shopping_canonical=shopping_canonical or "",
        fndds_code=res.fndds_code or "",
        sr28_fdc_id=res.sr28_fdc_id or "",
        esha_code=res.esha_code or "",
    )
    if taxonomy_meta.htc_code:
        path.append(
            f"taxonomy_lookup:{taxonomy_meta.taxonomy_source}:"
            f"{taxonomy_meta.htc_code}:{taxonomy_meta.retail_leaf_path}"
        )

    layer_map = {
        "canonical_hit": TrustLayer.L1_CANONICAL,
        "canonical_alias_hit": TrustLayer.L2_CANONICAL_ALIAS,
        "canonical_display_hit": TrustLayer.L2_CANONICAL_ALIAS,
        "canonical_line_hit": TrustLayer.L3_CANONICAL_STRIPPED,
        "reviewed_proxy": TrustLayer.L4_REVIEWED_PROXY,
        "sr28_fallback": TrustLayer.L5_SR28_FALLBACK,
        "external_catalog": TrustLayer.L6_EXTERNAL_CATALOG,
    }
    trust_layer = layer_map.get(res.trust_state, TrustLayer.L1_CANONICAL)

    return Resolution(
        canonical_name=res.canonical_name,
        sr28_fdc_id=res.sr28_fdc_id, fndds_code=res.fndds_code, pseudo_code="",
        nutrition_state=nutr_state, shopping_state=shop_state,
        trust_layer=trust_layer,
        grams=grams, alternatives=[], path=path,
        nutrition=nut_obj, products=products,
        shopping_canonical=shopping_canonical,
        shopping_sr28_fdc_id=shop_sr28,
        shopping_fndds_code=shop_fndds,
        esha_code=res.esha_code,
        **metadata_kwargs(taxonomy_meta),
    )
