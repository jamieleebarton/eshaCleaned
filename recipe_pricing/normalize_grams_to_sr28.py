#!/usr/bin/env python3
"""Round 7 — Deterministic gram normalizer using USDA SR28 portion data.

For every line in recipes_unified.csv, look up the row's htc_code in our
htc_to_fdc.csv bridge to get an SR28 fdc_id, then look up the matching
portion in data/sr28_csv/food_portion.csv. Replace grams_resolved with
qty * (portion_grams / portion_amount).

Per the user's directive:
- NO tolerance gate (force every change to exact SR28)
- Apply to ALL units that have an SR28 portion modifier match

Two safety guards:
1. Skip rows with parser-summed text ("plus N more", "for boiling water")
2. Skip absurd jumps (new_g > 5kg AND old_g < new_g/3)

Backs up to recipes_unified.csv.before_round7_grams_normalize (already
created in Phase 0). Atomic temp+rename. Idempotent.

Usage:
  python3 recipe_pricing/normalize_grams_to_sr28.py [--dry-run]
"""
from __future__ import annotations
import argparse, csv, os, re, sys, tempfile
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
HTC_TO_FDC = ROOT / "recipe_pricing" / "htc_to_fdc.csv"
FOOD_PORTION = ROOT / "data" / "sr28_csv" / "food_portion.csv"
LOG = ROOT / "recipe_pricing" / "normalize_grams_log.csv"
REVIEWED_HOUSEHOLD_PORTIONS = ROOT / "recipe_pricing" / "reviewed_household_portions.csv"
REVIEWED_SOURCE = "reviewed_household_portion_normalized"

# Unit-canonical map: input unit string → list of acceptable SR28 modifier
# tokens that match. Each tuple is (canonical_form, base_token_for_startswith).
UNIT_MAP: dict[str, list[str]] = {
    "tsp":      ["tsp", "teaspoon"],
    "teaspoon": ["tsp", "teaspoon"],
    "teaspoons":["tsp", "teaspoon"],
    "tbsp":     ["tbsp", "tablespoon"],
    "tablespoon":["tbsp", "tablespoon"],
    "tablespoons":["tbsp", "tablespoon"],
    "fl_oz":    ["fl_oz", "fl oz", "fluid ounce"],
    "cup":      ["cup"],
    "cups":     ["cup"],
    "head":     ["head"],
    "heads":    ["head"],
    "leaf":     ["leaf"],
    "leaves":   ["leaf"],
    "clove":    ["clove"],
    "cloves":   ["clove"],
    "stalk":    ["stalk"],
    "stalks":   ["stalk"],
    "ear":      ["ear"],
    "ears":     ["ear"],
    "sprig":    ["sprig", "branch"],
    "sprigs":   ["sprig", "branch"],
    "piece":    ["piece"],
    "pieces":   ["piece"],
    "slice":    ["slice"],
    "slices":   ["slice"],
    "stick":    ["stick"],
    "sticks":   ["stick"],
    "each":     ["each"],
    "dash":     ["dash"],
    "dashes":   ["dash"],
    "pint":     ["pint"],
    "pints":    ["pint"],
    "quart":    ["quart"],
    "quarts":   ["quart"],
    "gallon":   ["gallon"],
    "gallons":  ["gallon"],
}

SIZE_MODIFIERS = ("small", "medium", "large", "extra large", "jumbo")

SKIP_PATTERNS = re.compile(
    r"\bplus\s+(?:\d|one|two|three|four|five|six|seven|eight|nine|ten)\b"
    r"|\bfor boiling\b",
    re.I,
)

# Don't re-normalize rows where the quantity itself may have been repaired or
# intentionally clamped. SR28/modal rows are allowed to recompute when bridge
# or portion logic improves.
PRESERVE_GRAMS_SOURCES = {
    "range_lower_bound", "range_clamped_to_blob",
    "text_range_clamped_to_blob",
    "per_pound_parenthetical_fixed",
    "whipped_density_override",
    "temperature_quantity_restored",
    "total_weight_range_restored",
}

REVIEW_UNIT_ALIASES = {
    "tsp": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tbsp": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "cup": "cup",
    "cups": "cup",
    "leaf": "leaf",
    "leaves": "leaf",
    "slice": "slice",
    "slices": "slice",
    "stick": "stick",
    "sticks": "stick",
    "dash": "dash",
    "dashes": "dash",
    "pint": "pint",
    "pints": "pint",
    "quart": "quart",
    "quarts": "quart",
    "gallon": "gallon",
    "gallons": "gallon",
    "head": "head",
    "heads": "head",
    "clove": "clove",
    "cloves": "clove",
    "stalk": "stalk",
    "stalks": "stalk",
    "ear": "ear",
    "ears": "ear",
    "sprig": "sprig",
    "sprigs": "sprig",
    "piece": "piece",
    "pieces": "piece",
    "each": "each",
    "count": "count",
    "bunch": "bunch",
    "bunches": "bunch",
    "can": "can",
    "cans": "can",
    "jar": "jar",
    "jars": "jar",
    "bottle": "bottle",
    "bottles": "bottle",
    "package": "package",
    "packages": "package",
    "packet": "packet",
    "packets": "packet",
    "envelope": "envelope",
    "envelopes": "envelope",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "ml": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "l": "liter",
    "liter": "liter",
    "liters": "liter",
}

SAFE_WILDCARD_REVIEW_UNITS = {
    # Generic reviewed fallbacks are only safe for trace units. Container units
    # and shape units like head/clove/stalk are too food-dependent; those must
    # be exact item-reviewed rules or SR28 portions.
    "dash", "pinch",
}

STOPWORDS_ING = {
    "the", "a", "an", "of", "and", "or", "with", "fresh", "whole", "raw",
    "organic", "plain", "ground", "dried", "cooked", "mix",
}
STOPWORDS_SR = {
    "raw", "cooked", "with", "without", "added", "prepared", "equal",
    "volume", "water", "canned", "frozen", "ready", "serve", "unit",
}


def normalized_tokens(text: str, stopwords: set[str]) -> set[str]:
    out = set()
    for token in set(re.findall(r"[a-z]+", text.lower())) - stopwords:
        out.add(token)
        if token.endswith("ies") and len(token) > 4:
            out.add(token[:-3] + "y")
        if token.endswith("es") and len(token) > 3:
            out.add(token[:-2])
        if token.endswith("s") and len(token) > 3:
            out.add(token[:-1])
        if token == "breadcrumbs":
            out.update({"bread", "crumb", "crumbs"})
        if token in {"catsup", "ketchup"}:
            out.update({"catsup", "ketchup"})
        if token in {"macaroni", "noodle", "noodles", "pasta"}:
            out.update({"macaroni", "noodle", "noodles", "pasta"})
    return out


def token_overlap_ok(ingredient_name: str, sr_description: str) -> bool:
    if "water" in (ingredient_name or "").lower() and "water" in (sr_description or "").lower():
        return True
    ing_toks = normalized_tokens(ingredient_name, STOPWORDS_ING)
    sr_toks = normalized_tokens(sr_description, STOPWORDS_SR)
    if "powder" in ing_toks and not (
        sr_toks & {"powder", "dry", "spice", "spices", "seed", "seeds"}
    ):
        return False
    if "dry" in ing_toks and not (ing_toks & sr_toks) and not (
        sr_toks & {"powder", "dry", "spice", "spices", "seed", "seeds"}
    ):
        return False
    return not (ing_toks and sr_toks and not (ing_toks & sr_toks))


def canonical_review_unit(unit_raw: str) -> str:
    return REVIEW_UNIT_ALIASES.get((unit_raw or "").strip().lower(), (unit_raw or "").strip().lower())


def load_reviewed_household_portions() -> dict[tuple[str, str], list[dict]]:
    reviewed: dict[tuple[str, str], list[dict]] = defaultdict(list)
    if not REVIEWED_HOUSEHOLD_PORTIONS.exists():
        return reviewed
    with REVIEWED_HOUSEHOLD_PORTIONS.open() as f:
        for row in csv.DictReader(f):
            item = (row.get("item") or "").strip().lower()
            unit = canonical_review_unit(row.get("unit") or "")
            try:
                grams = float(row.get("grams_per_unit") or "")
            except (TypeError, ValueError):
                grams = 0.0
            if not item or not unit or grams <= 0:
                continue
            contains = [
                term.strip().lower()
                for term in (row.get("display_contains") or "").split("|")
                if term.strip()
            ]
            excludes = [
                term.strip().lower()
                for term in (row.get("display_excludes") or "").split("|")
                if term.strip()
            ]
            reviewed[(item, unit)].append({
                "grams": grams,
                "label": row.get("portion_label") or f"reviewed {unit}",
                "contains": contains,
                "excludes": excludes,
            })
    for rules in reviewed.values():
        rules.sort(key=lambda r: (-len(r["contains"]), len(r["excludes"])))
    return reviewed


def pick_reviewed_portion(
    reviewed: dict[tuple[str, str], list[dict]],
    item_raw: str,
    unit_raw: str,
    display: str,
) -> tuple[float, str] | None:
    item = (item_raw or "").strip().lower()
    unit = canonical_review_unit(unit_raw)
    disp = (display or "").lower()
    for rule in reviewed.get((item, unit), []):
        if rule["contains"] and not all(term in disp for term in rule["contains"]):
            continue
        if rule["excludes"] and any(term in disp for term in rule["excludes"]):
            continue
        return rule["grams"], rule["label"]
    return None


DERIVED_VOLUME_PORTIONS = {
    # SR28 often has one adjacent household volume but not the exact parsed
    # unit. These conversions preserve the SR28 food bridge while avoiding
    # a blob fallback for ordinary volume measures.
    "dash": [("tsp", 1 / 8)],
    "tsp": [("tbsp", 1 / 3), ("fl_oz", 1 / 6)],
    "tbsp": [("tsp", 3), ("fl_oz", 1 / 2)],
    "cup": [("fl_oz", 8)],
    "pint": [("cup", 2), ("fl_oz", 16), ("tbsp", 32)],
    "quart": [("cup", 4), ("fl_oz", 32), ("tbsp", 64)],
    "gallon": [("cup", 16), ("fl_oz", 128)],
}

LIQUID_DERIVED_CUES = {
    "water", "juice", "wine", "beer", "vodka", "tequila", "rum", "whiskey",
    "bourbon", "brandy", "sherry", "vermouth", "liqueur", "milk", "cream",
    "buttermilk", "soda", "broth", "stock", "vinegar", "oil", "sauce",
    "syrup", "extract", "bitters", "smoke", "cider",
}


def allow_fl_oz_derivation(display: str) -> bool:
    words = set(re.findall(r"[a-z]+", (display or "").lower()))
    return bool(words & LIQUID_DERIVED_CUES)


def pick_portion(
    portions: list[dict],
    unit_raw: str,
    display: str,
    allow_derived: bool = True,
) -> tuple[float, str] | None:
    """portions = [{'amount':1,'modifier':'cup','gram_weight':244,...}, ...].
    Returns (grams_per_unit, modifier_label) or None.

    Priority:
      1. size_match: display has "small/medium/large" + portion modifier matches that size
      2. exact: amount=1 AND modifier == unit_canonical (e.g., "cup")
      3. starts_with: amount=1 AND modifier starts with unit_canonical + " " or "," (e.g., "cup, packed")
      4. tie-breaker: pick the modifier whose tail-tokens overlap most with display words
      5. NO match → None (skip the row)
    """
    unit = (unit_raw or "").strip().lower()
    disp = (display or "").lower()
    candidates = UNIT_MAP.get(unit)
    if not candidates:
        return None

    size_hint = None
    for sz in SIZE_MODIFIERS:
        if sz in disp: size_hint = sz; break

    # Processed-state words. We use these for *priority* (tie-breaker), not
    # as a hard filter, so plain "1 cup heavy cream" can still match the
    # "cup, fluid (yields 2 cups whipped)" entry (which mentions "whipped"
    # only as a yield-clarifier).
    PROCESSED_MODS = ("whipped", "cooked", "packed", "sliced", "chopped",
                       "shredded", "diced", "crushed", "minced", "ground",
                       "sifted")

    matched = []
    for p in portions:
        mod = (p.get("modifier") or "").strip().lower()
        try: amt = float(p.get("amount") or 0)
        except: amt = 0
        try: gw = float(p.get("gram_weight") or 0)
        except: gw = 0
        if amt <= 0 or gw <= 0 or not mod: continue
        # Reject sized portions when display has no matching size hint
        sized = any(s in mod for s in ("small", "large", "jumbo", "extra large"))
        if sized and not (size_hint and size_hint in mod):
            continue
        # Token match
        match_via = None
        for tok in candidates:
            if mod == tok or mod.startswith(tok + " ") or mod.startswith(tok + ","):
                match_via = tok; break
        if match_via is None: continue
        # Determine if this is a "primary processed" form — modifier starts
        # with "X, processed" (e.g. "cup, whipped"). Yield clarifiers in
        # parentheses don't count.
        primary_proc = None
        for pw in PROCESSED_MODS:
            # match "cup, whipped" / "cup whipped" but NOT "cup, fluid (yields 2 cups whipped)"
            stripped = mod.split("(")[0].strip()
            if re.search(rf"\b{re.escape(pw)}\b", stripped):
                primary_proc = pw; break
        # Disqualify primary-processed modifiers when display doesn't mention the state
        primary_proc_mentioned = bool(primary_proc and primary_proc in disp)
        if primary_proc == "shredded" and re.search(r"\b(?:grated|grate)\b", disp):
            primary_proc_mentioned = True
        primary_proc_disqualified = bool(primary_proc and not primary_proc_mentioned)
        matched.append({
            "amt": amt, "gw": gw, "mod": mod,
            "size_match": bool(size_hint and size_hint in mod),
            "amt_is_one": amt == 1.0,
            "primary_proc_disqualified": primary_proc_disqualified,
        })

    if not matched:
        if allow_derived:
            for base_unit, factor in DERIVED_VOLUME_PORTIONS.get(unit, []):
                if base_unit == "fl_oz" and not allow_fl_oz_derivation(display):
                    continue
                base = pick_portion(portions, base_unit, display, allow_derived=False)
                if base is None:
                    continue
                gpu, label = base
                return (gpu * factor, f"derived {unit} from {label}")
        return None

    # 1. Size-matched first
    sized_opts = [m for m in matched if m["size_match"]]
    if sized_opts:
        m = sized_opts[0]
        return (m["gw"] / m["amt"], m["mod"])

    # Recipe shorthand "black pepper" means ground pepper unless the display
    # explicitly asks for whole peppercorns.
    if "pepper" in disp and not re.search(r"\b(?:whole|peppercorns?)\b", disp):
        ground_opts = [m for m in matched if "ground" in m["mod"] and m["amt_is_one"]]
        if ground_opts:
            m = sorted(ground_opts, key=lambda m: len(m["mod"]))[0]
            return (m["gw"] / m["amt"], m["mod"])

    # Recipe shorthand "brown sugar" conventionally means packed brown sugar.
    # SR28 also has unpacked/brownulated portions, but those should only win
    # when the recipe text says so.
    if re.search(r"\bbrown\b", disp) and re.search(r"\bsugar\b", disp) and \
       not re.search(r"\b(?:unpacked|brownulated)\b", disp):
        packed_opts = [
            m for m in matched
            if "packed" in m["mod"] and "unpacked" not in m["mod"] and m["amt_is_one"]
        ]
        if packed_opts:
            m = sorted(packed_opts, key=lambda m: len(m["mod"]))[0]
            return (m["gw"] / m["amt"], m["mod"])

    if unit in {"slice", "slices"} and "cheese" in disp and not re.search(r"\boz\b|ounce", disp):
        cheese_slice_opts = [
            m for m in matched
            if "slice" in m["mod"] and "3/4 oz" in m["mod"] and m["amt_is_one"]
        ]
        if cheese_slice_opts:
            m = cheese_slice_opts[0]
            return (m["gw"] / m["amt"], m["mod"])

    # 2. Filter out primary-processed disqualified options (unless ALL options
    # are disqualified, in which case we have no choice)
    non_proc = [m for m in matched if not m["primary_proc_disqualified"]]
    if not non_proc and re.search(r"\b(?:whole|peppercorns?)\b", disp):
        return None
    pool = non_proc if non_proc else matched

    # 3. Prefer amt=1
    one_opts = [m for m in pool if m["amt_is_one"]]
    pool = one_opts if one_opts else pool

    if len(pool) == 1:
        m = pool[0]
        return (m["gw"] / m["amt"], m["mod"])

    # 4. Tie-break by display word overlap with modifier tail. Treat common
    # recipe prep words as equivalent to SR28's coarser portion labels.
    disp_words = set(re.findall(r"[a-z]+", disp))
    if disp_words & {"chop", "chopped", "dice", "diced", "mince", "minced"}:
        disp_words.add("chopped")
    if disp_words & {"slice", "sliced", "strip", "strips", "julienne", "julienned"}:
        disp_words.update({"sliced", "strips"})
    if disp_words & {"grate", "grated", "shred", "shredded"}:
        disp_words.update({"grated", "shredded"})
    def overlap_score(m):
        mod_tail_words = set(re.findall(r"[a-z]+", m["mod"]))
        mod_tail_words -= set(candidates)
        return len(mod_tail_words & disp_words)
    pool_scored = sorted(pool, key=lambda m: (-overlap_score(m), len(m["mod"])))
    m = pool_scored[0]
    return (m["gw"] / m["amt"], m["mod"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # Load htc → (fdc, sr_description) bridge — fallback when ingredient_item
    # isn't directly in the per-name bridge.
    print("loading htc_to_fdc bridge…", file=sys.stderr)
    htc_to_fdc: dict[str, tuple[str, str]] = {}
    with HTC_TO_FDC.open() as f:
        r = csv.DictReader(f)
        for row in r:
            htc = (row.get("htc_code") or "").strip()
            fdc = (row.get("fdc_id") or "").strip()
            desc = (row.get("sr_description") or "").strip()
            if htc and fdc:
                htc_to_fdc[htc] = (fdc, desc)
    print(f"  {len(htc_to_fdc):,} htc → fdc mappings", file=sys.stderr)

    # Load ingredient_item → fdc directly — primary lookup. This avoids the
    # "iceberg lettuce → Red Leaf" bug where multiple specific lettuces share
    # one htc and the dominant-vote bridge picks generic "lettuce".
    print("loading ingredient_to_sr28 (per-name bridge)…", file=sys.stderr)
    ING_TO_SR28 = ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_to_sr28.csv"
    OVERRIDES = ROOT / "recipe_pricing" / "ingredient_fdc_overrides.csv"
    item_to_fdc: dict[str, tuple[str, str]] = {}
    with ING_TO_SR28.open() as f:
        r = csv.DictReader(f)
        for row in r:
            it = (row.get("item") or "").lower().strip()
            fdc = (row.get("fdc_id") or "").strip()
            desc = (row.get("sr_description") or "").strip()
            if it and fdc:
                item_to_fdc[it] = (fdc, desc)
    if OVERRIDES.exists():
        with OVERRIDES.open() as f:
            r = csv.DictReader(f)
            for row in r:
                it = (row.get("item") or "").lower().strip()
                fdc = (row.get("fdc_id") or "").strip()
                desc = (row.get("sr_description") or "").strip()
                if it and fdc:
                    item_to_fdc[it] = (fdc, desc)
    print(f"  {len(item_to_fdc):,} item → fdc mappings", file=sys.stderr)

    # Load SR28 portions per fdc_id
    print("loading SR28 food_portion…", file=sys.stderr)
    fdc_portions: dict[str, list[dict]] = defaultdict(list)
    with FOOD_PORTION.open() as f:
        r = csv.DictReader(f)
        for row in r:
            fdc = (row.get("fdc_id") or "").strip()
            if not fdc: continue
            fdc_portions[fdc].append(row)
    print(f"  {sum(len(v) for v in fdc_portions.values()):,} portion rows across "
          f"{len(fdc_portions):,} fdc_ids", file=sys.stderr)

    print("loading reviewed household portions…", file=sys.stderr)
    reviewed_portions = load_reviewed_household_portions()
    print(f"  {sum(len(v) for v in reviewed_portions.values()):,} reviewed rules across "
          f"{len(reviewed_portions):,} item/unit keys", file=sys.stderr)

    # Walk recipes_unified, decide changes
    rows_seen = 0; matched_fdc = 0; matched_portion = 0; skipped_skip = 0
    skipped_absurd = 0; changed = 0
    samples = []
    by_pattern = defaultdict(lambda: {"count": 0, "old_total": 0.0, "new_total": 0.0})

    def process(row, write_w=None):
        nonlocal rows_seen, matched_fdc, matched_portion, skipped_skip
        nonlocal skipped_absurd, changed
        rows_seen += 1
        if rows_seen % 500_000 == 0:
            print(f"  {rows_seen:,} lines processed", file=sys.stderr)
        try: qty = float(row.get("qty") or 0)
        except: qty = 0
        if qty <= 0:
            if write_w: write_w.writerow(row)
            return
        disp = row.get("display") or ""
        if SKIP_PATTERNS.search(disp):
            skipped_skip += 1
            if write_w: write_w.writerow(row)
            return
        # Preserve previously-corrected grams (round 2/4/5 fixes are
        # authoritative; their qty may be wrong from upstream so recomputing
        # via qty × SR28 would regress them).
        gs = (row.get("grams_source") or "").strip()
        if gs in PRESERVE_GRAMS_SOURCES:
            if write_w: write_w.writerow(row)
            return
        ing_name = (row.get("ingredient_item") or "").lower().strip()
        unit = (row.get("unit") or "").strip().lower()
        if not unit:
            portion = (
                pick_reviewed_portion(reviewed_portions, ing_name, "count", disp)
                or pick_reviewed_portion(reviewed_portions, ing_name, "each", disp)
            )
            if portion is None:
                if write_w: write_w.writerow(row)
                return
            matched_portion += 1
            gpu, plabel = portion
            new_g = qty * gpu
            try: old_g = float(row.get("grams_resolved") or 0)
            except: old_g = 0
            if abs(new_g - old_g) < 0.01:
                if write_w: write_w.writerow(row)
                return
            changed += 1
            by_pattern[(ing_name, "count", plabel)]["count"] += 1
            by_pattern[(ing_name, "count", plabel)]["old_total"] += old_g
            by_pattern[(ing_name, "count", plabel)]["new_total"] += new_g
            if len(samples) < 25:
                samples.append({
                    "rid": row.get("recipe_id"),
                    "display": disp[:80],
                    "old": old_g,
                    "new": new_g,
                    "portion": plabel,
                })
            row["grams_resolved"] = f"{new_g:.2f}"
            row["grams_source"] = REVIEWED_SOURCE
            if write_w: write_w.writerow(row)
            return
        # PRIMARY: per-ingredient-name bridge (more specific). Falls back to
        # htc-dominant bridge only when item isn't in the per-name table.
        reviewed_portion = pick_reviewed_portion(reviewed_portions, ing_name, unit, disp)
        unit_key = canonical_review_unit(unit)
        wildcard_reviewed_portion = (
            pick_reviewed_portion(reviewed_portions, "*", unit, disp)
            if unit_key in SAFE_WILDCARD_REVIEW_UNITS else None
        )
        fallback_reviewed_portion = reviewed_portion or wildcard_reviewed_portion
        bridge_ent = item_to_fdc.get(ing_name)
        if not bridge_ent:
            htc = (row.get("htc_code") or "").strip()
            bridge_ent = htc_to_fdc.get(htc)
        if not bridge_ent:
            portion = fallback_reviewed_portion
            source_label = REVIEWED_SOURCE
        else:
            fdc, sr_desc = bridge_ent
            # Name-similarity safety check — skip the row when the recipe's
            # ingredient_item shares no meaningful tokens with the bridged
            # SR28 description. Catches mis-bridges like
            # "vegetable broth → Fish broth" before they regress grams. Exact
            # reviewed household portions may still apply because those rules
            # are item-scoped and audited separately.
            if not token_overlap_ok(ing_name, sr_desc):
                portion = fallback_reviewed_portion
                source_label = REVIEWED_SOURCE
            elif reviewed_portion is not None:
                # Reviewed household rules are HUMAN-CURATED and should win
                # over SR28 bulk-portion data, which is noisy for count-style
                # units like 'head/leaf/bunch/sprig'. SR28 is the fallback.
                portion = reviewed_portion
                source_label = REVIEWED_SOURCE
            else:
                matched_fdc += 1
                portions = fdc_portions.get(fdc)
                if portions:
                    source_label = "usda_sr28_normalized"
                    portion = pick_portion(portions, unit, disp)
                    if portion is None and wildcard_reviewed_portion is not None:
                        portion = wildcard_reviewed_portion
                        source_label = REVIEWED_SOURCE
                else:
                    source_label = REVIEWED_SOURCE
                    portion = wildcard_reviewed_portion
        if portion is None:
            if write_w: write_w.writerow(row)
            return
        matched_portion += 1
        gpu, plabel = portion
        new_g = qty * gpu
        try: old_g = float(row.get("grams_resolved") or 0)
        except: old_g = 0
        if new_g > 5000 and (old_g <= 0 or old_g < new_g / 3):
            skipped_absurd += 1
            if write_w: write_w.writerow(row)
            return
        if abs(new_g - old_g) < 0.01:
            if write_w: write_w.writerow(row)
            return
        changed += 1
        ing = (row.get("ingredient_item") or "").lower()
        key = (ing, unit, plabel)
        by_pattern[key]["count"] += 1
        by_pattern[key]["old_total"] += old_g
        by_pattern[key]["new_total"] += new_g
        if len(samples) < 25:
            samples.append({
                "rid": row['recipe_id'],
                "display": disp[:55],
                "old": old_g, "new": new_g, "portion": plabel,
            })
        if write_w:
            row["grams_resolved"] = f"{new_g:.2f}"
            row["grams_source"] = source_label
            write_w.writerow(row)

    if args.dry_run:
        with RECIPES.open() as f:
            r = csv.DictReader(f)
            for row in r:
                process(row, None)
    else:
        out_dir = RECIPES.parent
        tmp_fd, tmp_path = tempfile.mkstemp(prefix=".unified_norm_",
                                             suffix=".csv", dir=str(out_dir))
        os.close(tmp_fd)
        try:
            with RECIPES.open() as f_in, open(tmp_path, "w", newline="") as f_out:
                r = csv.DictReader(f_in)
                w = csv.DictWriter(f_out, fieldnames=r.fieldnames)
                w.writeheader()
                for row in r: process(row, w)
            os.replace(tmp_path, RECIPES)
        except Exception:
            if os.path.exists(tmp_path): os.remove(tmp_path)
            raise

    print(f"\nrows scanned:               {rows_seen:,}", file=sys.stderr)
    print(f"matched fdc via htc:        {matched_fdc:,}", file=sys.stderr)
    print(f"matched portion:            {matched_portion:,}", file=sys.stderr)
    print(f"skipped (skip-pattern):     {skipped_skip:,}", file=sys.stderr)
    print(f"skipped (absurd-jump):      {skipped_absurd:,}", file=sys.stderr)
    print(f"changed:                    {changed:,}", file=sys.stderr)

    print(f"\nTop change patterns (count: avg_old → avg_new):", file=sys.stderr)
    sorted_pat = sorted(by_pattern.items(), key=lambda kv: -kv[1]["count"])
    for (ing, unit, plabel), d in sorted_pat[:25]:
        avg_old = d['old_total'] / d['count']
        avg_new = d['new_total'] / d['count']
        print(f"  {d['count']:>5}× '{ing[:25]:<25}' [{unit:<6}] '{plabel[:30]:<30}': "
              f"{avg_old:>5.0f}g → {avg_new:>5.0f}g", file=sys.stderr)
    print(f"\nSample changes:", file=sys.stderr)
    for s in samples[:15]:
        print(f"  rid={s['rid']:>6} '{s['display']}'  {s['old']:.0f}g → {s['new']:.0f}g  ({s['portion']})",
              file=sys.stderr)

    # Write log
    if not args.dry_run:
        with LOG.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["ingredient", "unit", "portion",
                                                "n", "avg_old_g", "avg_new_g"])
            w.writeheader()
            for (ing, unit, plabel), d in sorted_pat:
                w.writerow({
                    "ingredient": ing, "unit": unit, "portion": plabel,
                    "n": d["count"],
                    "avg_old_g": round(d["old_total"]/d["count"], 1),
                    "avg_new_g": round(d["new_total"]/d["count"], 1),
                })
        print(f"\n→ log written to {LOG}", file=sys.stderr)


if __name__ == "__main__":
    main()
