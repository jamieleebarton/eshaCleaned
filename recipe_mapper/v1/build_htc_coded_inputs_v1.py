#!/usr/bin/env python3
"""Build explicit HTC-coded recipe and store-product input artifacts.

This is the clean boundary the calculator should consume:

* recipe ingredients have raw HTC plus tree-derived HTC/concept fields
* Walmart/Kroger products have raw HTC plus tree-derived HTC/concept fields

No learned contracts are read here.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from htc_tree_core_v1 import (  # noqa: E402
    decode_htc,
    food_slot_modifier_from_text,
    group_from_tree_path,
    htc_from_tree_identity,
    identity_tokens,
    normalize_key,
    normalize_surface,
    path_bonus_for_group,
    primary_identity_token,
    recipe_group_hint,
    sku_count_bonus,
)

csv.field_size_limit(sys.maxsize)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT_DIR = HERE / "output"

DEFAULT_INGREDIENT_HTC = OUT_DIR / "recipe_ingredient_htc_tagged.csv"
DEFAULT_RECIPE_TAXONOMY = OUT_DIR / "recipe_ingredient_taxonomy_v2.csv"
DEFAULT_REGISTRY = OUT_DIR / "identity_registry.json"
DEFAULT_PRICED_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
DEFAULT_PRODUCT_EVIDENCE = OUT_DIR / "priced_product_evidence_v1.csv"
DEFAULT_API_TAXONOMY = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"

OUT_RECIPE = OUT_DIR / "htc_coded_recipe_ingredients_v1.csv"
OUT_PRODUCTS = OUT_DIR / "htc_coded_store_products_v1.csv"
OUT_SUMMARY = OUT_DIR / "htc_coded_inputs_v1_summary.json"

TAP_WATER_KEYS = {"water", "fresh water", "tap water", "plain water", "ice", "ice cube", "ice cubes"}
INHERENT_DRIED_FRUIT_RE = re.compile(
    r"\b(raisins?|currants?|prunes?|dates?|sultanas?|dried\s+(?:apricots?|figs?|cherries?|cranberries?|mango(?:es)?|pineapples?|blueberries?))\b",
    re.I,
)

FRESH_PEPPER_PATTERNS = (
    (re.compile(r"\bfresh\b.*\bjalap[eñ]no peppers?\b"), "Jalapeno Peppers"),
    (re.compile(r"\bfresh\b.*\bserrano peppers?\b"), "Serrano Peppers"),
    (re.compile(r"\bfresh\b.*\bpoblano peppers?\b"), "Poblano Peppers"),
    (re.compile(r"\bfresh\b.*\bananaheim peppers?\b"), "Anaheim Peppers"),
    (re.compile(r"\bfresh\b.*\bhabanero peppers?\b"), "Habanero Peppers"),
    (re.compile(r"\bfresh\b.*\b(chili|chile) peppers?\b"), "Chili Peppers"),
)

FRESH_PRODUCE_TITLE_PATTERNS = (
    (re.compile(r"\bgreen bell peppers?\b"), "Green Bell Peppers", "Produce > Vegetables > Bell Peppers > Green"),
    (re.compile(r"\bred bell peppers?\b"), "Red Bell Peppers", "Produce > Vegetables > Bell Peppers > Red"),
    (re.compile(r"\byellow bell peppers?\b"), "Yellow Bell Peppers", "Produce > Vegetables > Bell Peppers > Yellow"),
    (re.compile(r"\borange bell peppers?\b"), "Orange Bell Peppers", "Produce > Vegetables > Bell Peppers > Orange"),
    (re.compile(r"\bbell peppers?\b"), "Bell Peppers", "Produce > Vegetables > Bell Peppers"),
    (re.compile(r"\bgreen onions?\b|\bscallions?\b"), "Green Onions", "Produce > Vegetables > Green Onions"),
    (re.compile(r"\btomato(?:es)?\b"), "Tomatoes", "Produce > Vegetables > Tomatoes"),
    (re.compile(r"\bpotato(?:es)?\b"), "Potatoes", "Produce > Vegetables > Potatoes"),
    (re.compile(r"\bavocados?\b"), "Avocado", "Produce > Fruit > Avocado"),
    (re.compile(r"\bbananas?\b"), "Bananas", "Produce > Fruit > Bananas"),
    (re.compile(r"\blemons?\b"), "Lemons", "Produce > Fruit > Lemons"),
    (re.compile(r"\blimes?\b"), "Limes", "Produce > Fruit > Limes"),
    (re.compile(r"\bparsley\b"), "Parsley", "Produce > Herbs > Parsley"),
    (re.compile(r"\bcilantro\b"), "Cilantro", "Produce > Herbs > Cilantro"),
    (re.compile(r"\bmint\b"), "Mint", "Produce > Herbs > Mint"),
    (re.compile(r"\bbasil\b"), "Basil", "Produce > Herbs > Basil"),
    (re.compile(r"\bthyme\b"), "Thyme", "Produce > Herbs > Thyme"),
    (re.compile(r"\brosemary\b"), "Rosemary", "Produce > Herbs > Rosemary"),
    (re.compile(r"\bdill\b"), "Dill", "Produce > Herbs > Dill"),
    (re.compile(r"\bsage\b"), "Sage", "Produce > Herbs > Sage"),
    (re.compile(r"\boregano\b"), "Oregano", "Produce > Herbs > Oregano"),
    (re.compile(r"\bginger\b"), "Ginger", "Produce > Vegetables > Ginger"),
)

NON_FOOD_CATEGORY_RE = re.compile(
    r"\b(beauty|body\s+wash|conditioner|cosmetic|garden|hair|household|lipstick|"
    r"home\s+improvement|live\s+plants?|lotion|patio|personal\s+care|plumbing|"
    r"shampoo|soap|toothpaste|water\s+filtration|water\s+softener)\b",
    re.I,
)
SHELL_EGG_PROCESS_RE = re.compile(
    r"\b(candy|chocolate|easter|hard[-\s]*boiled|hard[-\s]*cooked|liquid|mix|"
    r"noodle|pickled|powder|scramble|scrambled|substitute|vegan)\b",
    re.I,
)
FOODISH_CATEGORY_RE = re.compile(
    r"\b(baking|breakfast|dairy|eggs?|food|fresh\s+produce|natural\s+organic|"
    r"pantry|produce|spices?|seasonings?)\b",
    re.I,
)
NON_SPICE_PRODUCT_RE = re.compile(
    r"\b(beverage|coffee|drink|immune|sleep|smoothie|supplement|tea)\b",
    re.I,
)
PRODUCT_SPICE_TITLE_RULES = (
    (re.compile(r"\bcardamom\b", re.I), "Spice Blend", "Pantry > Spices & Seasonings > Spice Blend", "Cardamom"),
    (re.compile(r"\bmace\b", re.I), "Spice Blend", "Pantry > Spices & Seasonings > Spice Blend", "Mace"),
    (re.compile(r"\bcumin\b.*\bseeds?\b|\bseeds?\b.*\bcumin\b", re.I), "Cumin Seed", "Pantry > Spices & Seasonings > Cumin Seed", ""),
    (re.compile(r"\bcoriander\b.*\bseeds?\b|\bseeds?\b.*\bcoriander\b", re.I), "Coriander Seed", "Pantry > Spices & Seasonings > Coriander Seed", ""),
    (re.compile(r"\bpoppy\b.*\bseeds?\b|\bseeds?\b.*\bpoppy\b", re.I), "Poppy Seeds", "Pantry > Spices & Seasonings > Poppy Seeds", ""),
    (re.compile(r"\bsaffron\b", re.I), "Spice Blend", "Pantry > Spices & Seasonings > Spice Blend", "Saffron"),
)
RECIPE_SPICE_MODIFIER_RULES = (
    (re.compile(r"\bmace\b", re.I), "Mace"),
)


@dataclass(frozen=True)
class RegistryNode:
    code: str
    rule: str
    canonical_path: str
    product_identity: str
    modifier: str
    identity_text: str
    identity_key: str
    identity_terms: frozenset[str]
    primary: str
    sku_count: int
    modal_fndds_code: str
    modal_fndds_desc: str
    modal_sr28_code: str
    modal_sr28_desc: str
    modal_retail_leaf_path: str
    htc_code: str
    htc_group: str
    htc_family: str


@dataclass(frozen=True)
class TaxonomyRow:
    title: str
    source: str
    fdc_id: str
    canonical_path: str
    canonical_label: str
    product_identity: str
    modifier: str
    htc_code: str
    htc_group: str
    htc_family: str
    htc_food: str
    match_method: str
    match_confidence: str


def intish(value: object) -> int:
    try:
        return int(float(str(value or "0")))
    except ValueError:
        return 0


def floatish(value: object) -> float:
    try:
        return float(str(value or "0"))
    except ValueError:
        return 0.0


def title_key(value: object) -> str:
    return normalize_surface(str(value or ""))


def upc_key(value: object) -> str:
    return re.sub(r"[^0-9a-z]+", "", str(value or "").lower()).lstrip("0")


def load_taxonomy_rows(path: Path) -> list[TaxonomyRow]:
    if not path.exists():
        return []
    rows: list[TaxonomyRow] = []
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            title = (row.get("title") or "").strip()
            canonical = (row.get("canonical_path") or "").strip()
            pid = (row.get("product_identity_fixed") or "").strip()
            htc_code = (row.get("htc_code") or "").strip()
            if not title or not htc_code:
                continue
            rows.append(TaxonomyRow(
                title=title,
                source=(row.get("source") or "").strip(),
                fdc_id=(row.get("fdc_id") or "").strip(),
                canonical_path=canonical,
                canonical_label=(row.get("canonical_label") or "").strip(),
                product_identity=pid,
                modifier=(row.get("modifier") or "").strip(),
                htc_code=htc_code,
                htc_group=(row.get("htc_group") or "").strip(),
                htc_family=(row.get("htc_family") or "").strip(),
                htc_food=(row.get("htc_food") or "").strip(),
                match_method=(row.get("match_method") or "").strip(),
                match_confidence=(row.get("match_confidence") or "").strip(),
            ))
    return rows


def load_recipe_taxonomy(path: Path) -> dict[str, TaxonomyRow]:
    out: dict[str, TaxonomyRow] = {}
    for row in load_taxonomy_rows(path):
        out.setdefault(title_key(row.title), row)
    return out


def load_api_taxonomy(path: Path) -> tuple[dict[tuple[str, str], TaxonomyRow], dict[tuple[str, str], TaxonomyRow]]:
    by_upc: dict[tuple[str, str], TaxonomyRow] = {}
    by_title: dict[tuple[str, str], TaxonomyRow] = {}
    for row in load_taxonomy_rows(path):
        source = row.source.lower()
        if not source:
            continue
        by_title.setdefault((source, title_key(row.title)), row)
        fdc_suffix = row.fdc_id.split("-", 1)[-1]
        fdc_upc = upc_key(fdc_suffix)
        if fdc_upc and not fdc_upc.startswith("n"):
            by_upc.setdefault((source, fdc_upc), row)
    return by_upc, by_title


def lookup_api_taxonomy(
    row: sqlite3.Row,
    by_upc: dict[tuple[str, str], TaxonomyRow],
    by_title: dict[tuple[str, str], TaxonomyRow],
) -> TaxonomyRow | None:
    source = str(row["source"] or "").lower()
    if not source:
        return None
    key = upc_key(row["upc"])
    if key:
        found = by_upc.get((source, key))
        if found:
            return found
    return by_title.get((source, title_key(row["name"])))


def taxonomy_modifier(tax: TaxonomyRow) -> str:
    if tax.modifier:
        return tax.modifier.replace("_", " ").replace("|", " ").strip()
    match = re.search(r"\(([^)]+)\)", tax.canonical_label or "")
    if match:
        return " ".join(match.group(1).replace(",", " ").replace("|", " ").split())
    return ""


def taxonomy_htc(tax: TaxonomyRow, source: str):
    return decode_htc(tax.htc_code, floatish(tax.match_confidence) or 0.95, source)


def product_modifier_with_slot_text(
    row: sqlite3.Row,
    tree_pid: str,
    tree_canonical: str,
    tree_modifier: str,
) -> str:
    inferred = food_slot_modifier_from_text(tree_canonical, tree_pid, row["name"] or "")
    if not inferred:
        return tree_modifier
    if not tree_modifier:
        return inferred
    existing_key = normalize_key(tree_modifier)
    inferred_key = normalize_key(inferred)
    if existing_key in {"flavored", "natural", "naturally flavored", "original", "plain"}:
        return inferred
    if existing_key and f" {existing_key} " in f" {inferred_key} ":
        return inferred
    return tree_modifier


def fresh_recipe_path_override(item: str, tax: TaxonomyRow) -> tuple[str, str] | None:
    item_lc = normalize_surface(item)
    path_lc = normalize_surface(tax.canonical_path)
    if re.search(r"\b(tomatoes?|tomato)\b", item_lc) and not re.search(r"\b(canned|paste|puree|sauce|dried|sun dried)\b", item_lc):
        if not path_lc.startswith("produce "):
            return "Tomatoes", "Produce > Vegetables > Tomatoes"
    return None


def load_registry(path: Path) -> tuple[list[RegistryNode], dict[str, list[int]], dict[str, list[int]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    nodes: list[RegistryNode] = []
    exact: dict[str, list[int]] = defaultdict(list)
    by_token: dict[str, list[int]] = defaultdict(list)

    for entry in raw:
        rule = str(entry.get("rule") or "A")
        pid = str(entry.get("product_identity_fixed") or "").strip()
        modifier = str(entry.get("primary_modifier") or "").strip()
        canonical = str(entry.get("canonical_path") or "").strip()
        if not pid or not canonical:
            continue
        identity_text = modifier if rule in {"B", "C"} and modifier else pid
        key = normalize_key(identity_text)
        terms = frozenset(identity_tokens(identity_text))
        if not terms:
            continue
        htc = htc_from_tree_identity(canonical, pid, modifier, confidence=0.95, source="registry_tree")
        node = RegistryNode(
            code=str(entry.get("code") or ""),
            rule=rule,
            canonical_path=canonical,
            product_identity=pid,
            modifier=modifier if rule in {"B", "C"} else "",
            identity_text=identity_text,
            identity_key=key,
            identity_terms=terms,
            primary=primary_identity_token(identity_text),
            sku_count=intish(entry.get("sku_count")),
            modal_fndds_code=str(entry.get("modal_fndds_code") or ""),
            modal_fndds_desc=str(entry.get("modal_fndds_desc") or ""),
            modal_sr28_code=str(entry.get("modal_sr28_code") or ""),
            modal_sr28_desc=str(entry.get("modal_sr28_desc") or ""),
            modal_retail_leaf_path=str(entry.get("modal_retail_leaf_path") or ""),
            htc_code=htc.code,
            htc_group=htc.group,
            htc_family=htc.family,
        )
        idx = len(nodes)
        nodes.append(node)
        exact[key].append(idx)
        for term in terms:
            by_token[term].append(idx)
    return nodes, exact, by_token


def score_node(
    *,
    item_group: str,
    item_family: str,
    item_key: str,
    item_terms: set[str],
    primary: str,
    item_lc: str,
    node: RegistryNode,
) -> float:
    if not item_terms:
        return -999.0

    overlap = item_terms & set(node.identity_terms)
    if not overlap:
        return -999.0

    if item_group and node.htc_group != item_group:
        return -999.0
    if (
        item_group
        and item_family
        and item_family != "0"
        and node.htc_family not in {"", "0", item_family}
    ):
        return -999.0
    path_lc = normalize_surface(node.canonical_path)
    item_is_plain_fresh_produce = (
        item_group in {"6", "7"}
        and not any(term in item_lc for term in ("frozen", "canned", "dried", "dry", "paste", "sauce", "puree", "juice"))
        and not INHERENT_DRIED_FRUIT_RE.search(item_lc)
    )
    if item_is_plain_fresh_produce and not path_lc.startswith("produce"):
        return -999.0

    if (
        item_group == "E"
        and item_family == "3"
        and any(term in item_lc for term in ("fresh", "sprig", "bunch"))
        and "herb" not in path_lc
        and not path_lc.startswith("produce")
        and not (
            path_lc.startswith("pantry spices seasonings")
            and primary
            and primary in node.identity_terms
            and normalize_key(node.product_identity) not in {"seasoning", "spice blend"}
        )
    ):
        return -999.0

    score = 0.0
    if node.identity_key == item_key:
        score += 110.0
    elif node.identity_key.replace(" ", "") == item_key.replace(" ", ""):
        score += 95.0
    if item_terms <= set(node.identity_terms):
        score += 45.0
    if set(node.identity_terms) <= item_terms:
        score += 35.0
    if primary and primary == node.primary:
        score += 25.0
    score += 12.0 * len(overlap)
    score += 35.0 * (len(overlap) / max(1, len(item_terms | set(node.identity_terms))))
    if "chili" in item_terms and "chili" not in node.identity_terms:
        score -= 90.0

    if item_group:
        score += 55.0
        if item_family and item_family != "0" and node.htc_family == item_family:
            score += 22.0
        elif item_family and item_family != "0" and node.htc_family not in {"", "0"}:
            score -= 8.0
        score += path_bonus_for_group(item_group, node.canonical_path)

    if item_group in {"6", "7"} and not any(term in item_lc for term in ("frozen", "canned", "dried", "dry")):
        if path_lc.startswith("produce"):
            score += 60.0
        elif path_lc.startswith("frozen") or "canned" in path_lc:
            score -= 25.0

    if item_group == "E" and "fresh" in item_lc:
        if "herb" in path_lc or path_lc.startswith("produce"):
            score += 60.0
        elif "spices seasonings seasoning" in path_lc:
            score -= 220.0

    if (
        item_group == "E"
        and item_family == "3"
        and normalize_key(node.product_identity) == "seasoning"
        and node.modifier
    ):
        score -= 180.0

    if item_group == "E" and item_family == "5":
        if "extract" in node.identity_terms:
            score += 120.0
        if ({"bean", "paste"} & set(node.identity_terms)) and not ({"bean", "paste"} & item_terms):
            score -= 80.0
        if "baking extracts" in path_lc:
            score += 220.0
        if "vanilla bean" in path_lc:
            score += 120.0
        if normalize_key(node.product_identity) in {"dip", "seasoning", "spice blend"} and node.modifier:
            score -= 180.0

    if "ground" in item_lc and item_group == "E" and "spices seasonings" in path_lc:
        score += 15.0
    if "fresh" in item_lc and ("candy" in path_lc or "gum" in path_lc):
        score -= 80.0

    score += sku_count_bonus(node.sku_count)
    return score


def resolve_recipe_node(
    item: str,
    row: dict[str, str],
    nodes: list[RegistryNode],
    exact: dict[str, list[int]],
    by_token: dict[str, list[int]],
) -> tuple[RegistryNode | None, float, str]:
    key = normalize_key(item)
    if key in TAP_WATER_KEYS:
        return None, 999.0, "tap_water"

    raw = decode_htc(row.get("htc_code") or "", floatish(row.get("htc_confidence")), "recipe_raw")
    item_group = recipe_group_hint(item, raw.group)
    item_family = raw.family
    if item_group != raw.group:
        item_family = "0"
    if item_group == "6" and re.search(
        r"\b(chili|chile|bell|jalapeno|serrano|poblano|habanero|anaheim|fresno|green|red|yellow|orange)\s+peppers?\b",
        normalize_surface(item),
    ):
        item_family = "6"
    item_terms = identity_tokens(item)
    primary = primary_identity_token(item)
    item_lc = normalize_surface(item)

    candidate_ids: set[int] = set(exact.get(key, ()))
    for term in item_terms:
        bucket = by_token.get(term, ())
        candidate_ids.update(bucket[:1500])
    if not candidate_ids:
        return None, 0.0, "no_candidate"

    best: tuple[float, RegistryNode | None] = (-999.0, None)
    for idx in candidate_ids:
        node = nodes[idx]
        score = score_node(
            item_group=item_group,
            item_family=item_family,
            item_key=key,
            item_terms=item_terms,
            primary=primary,
            item_lc=item_lc,
            node=node,
        )
        if score > best[0]:
            best = (score, node)

    score, node = best
    if node is None:
        return None, 0.0, "no_candidate"
    if score < 80.0:
        return None, score, "below_threshold"
    return node, score, "resolved"


def recipe_tree_override(item: str, row: dict[str, str]) -> tuple[str, str, str, str] | None:
    raw = decode_htc(row.get("htc_code") or "", floatish(row.get("htc_confidence")), "recipe_raw")
    item_group = recipe_group_hint(item, raw.group)
    item_lc = normalize_surface(item)
    if item_group == "E":
        for pattern, modifier in RECIPE_SPICE_MODIFIER_RULES:
            if pattern.search(item_lc):
                return (
                    "Spice Blend",
                    "Pantry > Spices & Seasonings > Spice Blend",
                    modifier,
                    "recipe_spice_title_tree",
                )
    return None


def load_product_evidence(path: Path) -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = {}
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            rowid = intish(row.get("rowid"))
            if rowid:
                out[rowid] = row
    return out


def product_tree_override(row: sqlite3.Row, evidence: dict[str, str] | None) -> tuple[str, str, str, str, str] | None:
    title_lc = normalize_surface(row["name"] or "")
    category_lc = normalize_surface(" ".join([
        row["category_path"] or "",
        row["category_path_walmart"] or "",
    ]))
    status = (evidence or {}).get("taxonomy_status") or row["bridge_status"] or ""
    if NON_FOOD_CATEGORY_RE.search(category_lc):
        return None

    if "produce" in category_lc or "fresh" in title_lc:
        for pattern, inferred_pid in FRESH_PEPPER_PATTERNS:
            if pattern.search(title_lc):
                return inferred_pid, f"Produce > Vegetables > {inferred_pid}", "", status, "api_cache_fresh_produce_title"
        if not re.search(r"\b(seasoning|mix|sauce|salsa|paste|juice|drink|candy|chips?|snack|frozen|canned|jar)\b", title_lc):
            for pattern, inferred_pid, inferred_canonical in FRESH_PRODUCE_TITLE_PATTERNS:
                if pattern.search(title_lc):
                    return inferred_pid, inferred_canonical, "", status, "api_cache_fresh_produce_title"

    if re.search(r"\beggs?\b", title_lc) and not SHELL_EGG_PROCESS_RE.search(title_lc):
        if re.search(r"\b(egg|eggs|dairy|breakfast)\b", category_lc):
            return "Eggs", "Dairy > Eggs", "", status, "api_cache_shell_egg_title"

    if re.search(r"\bghee\b", title_lc):
        if FOODISH_CATEGORY_RE.search(category_lc) or row["htc_group"] in {"1", "B"}:
            return "Ghee", "Pantry > Oil > Ghee", "", status, "api_cache_ghee_title"

    if (
        row["htc_group"] == "E"
        and FOODISH_CATEGORY_RE.search(category_lc)
        and not NON_SPICE_PRODUCT_RE.search(f"{category_lc} {title_lc}")
    ):
        for pattern, pid, canonical, modifier in PRODUCT_SPICE_TITLE_RULES:
            if pattern.search(title_lc):
                return pid, canonical, modifier, status, "api_cache_spice_title"
    return None


def is_retail_non_food_category(row: sqlite3.Row) -> bool:
    category_lc = normalize_surface(" ".join([
        row["category_path"] or "",
        row["category_path_walmart"] or "",
    ]))
    return bool(NON_FOOD_CATEGORY_RE.search(category_lc))


def chosen_product_tree(row: sqlite3.Row, evidence: dict[str, str] | None) -> tuple[str, str, str, str, str]:
    if evidence:
        status = evidence.get("taxonomy_status") or ""
        proposed_pid = (evidence.get("proposed_pid") or "").strip()
        proposed_canonical = (evidence.get("proposed_canonical") or "").strip()
        proposed_modifier = (evidence.get("proposed_modifier") or "").strip().split(" > ")[0].strip()
        hard_vetoes = evidence.get("hard_vetoes") or ""
        title_lc = normalize_surface(row["name"] or "")
        if (
            normalize_key(proposed_pid) == "egg white"
            and "white egg" in title_lc
            and "egg white" not in title_lc
        ):
            return "Eggs", "Dairy > Eggs", "", status, "white_shell_egg_correction"
        if status.startswith("reject"):
            return "", "", "", status, "evidence_reject"
        if "non_food" in hard_vetoes:
            return "", "", "", status, "evidence_reject"
    override = product_tree_override(row, evidence)
    if override:
        return override
    if evidence:
        status = evidence.get("taxonomy_status") or ""
        proposed_pid = (evidence.get("proposed_pid") or "").strip()
        proposed_canonical = (evidence.get("proposed_canonical") or "").strip()
        proposed_modifier = (evidence.get("proposed_modifier") or "").strip().split(" > ")[0].strip()
        hard_vetoes = evidence.get("hard_vetoes") or ""
        if (
            proposed_pid
            and proposed_canonical
            and not status.startswith("quarantine")
            and "non_food" not in hard_vetoes
        ):
            return proposed_pid, proposed_canonical, proposed_modifier, status, "priced_product_evidence"

    pid = (row["consensus_pid"] or "").strip()
    canonical = (row["consensus_canonical"] or "").strip()
    modifier = (row["consensus_modifier"] or "").strip().split(" > ")[0].strip()
    if pid and canonical:
        return pid, canonical, modifier, row["bridge_status"] or "", "priced_db_consensus"
    title_lc = normalize_surface(row["name"] or "")
    category_lc = normalize_surface(" ".join([
        row["category_path"] or "",
        row["category_path_walmart"] or "",
    ]))
    if "produce" in category_lc or "fresh" in title_lc:
        for pattern, inferred_pid in FRESH_PEPPER_PATTERNS:
            if pattern.search(title_lc):
                return inferred_pid, f"Produce > Vegetables > {inferred_pid}", "", row["bridge_status"] or "", "raw_fresh_produce_title"
        if not re.search(r"\b(seasoning|mix|sauce|salsa|paste|juice|drink|candy|chips?|snack|frozen|canned|jar)\b", title_lc):
            for pattern, inferred_pid, inferred_canonical in FRESH_PRODUCE_TITLE_PATTERNS:
                if pattern.search(title_lc):
                    return inferred_pid, inferred_canonical, "", row["bridge_status"] or "", "raw_fresh_produce_title"
    return "", "", "", row["bridge_status"] or "", "raw_product_only"


def build_recipe_artifact(args: argparse.Namespace) -> tuple[list[dict[str, str]], dict[str, object]]:
    t0 = time.time()
    nodes, exact, by_token = load_registry(args.registry)
    recipe_taxonomy = load_recipe_taxonomy(args.recipe_taxonomy)
    for token, ids in list(by_token.items()):
        ids.sort(key=lambda idx: nodes[idx].sku_count, reverse=True)
    rows: list[dict[str, str]] = []
    status_counts: Counter[str] = Counter()
    group_counts: Counter[str] = Counter()

    with args.ingredients.open(encoding="utf-8", errors="replace", newline="") as handle:
        for i, row in enumerate(csv.DictReader(handle), 1):
            item = (row.get("item") or "").strip()
            raw = decode_htc(row.get("htc_code") or "", floatish(row.get("htc_confidence")), row.get("htc_source") or "")
            tax = recipe_taxonomy.get(title_key(item))

            if normalize_key(item) in TAP_WATER_KEYS:
                tree_htc = raw
                tree_pid = "Tap Water"
                tree_canonical = "__TAP_WATER__"
                tree_modifier = ""
                tree_code = "__TAP_WATER__"
                score = 999.0
                status = "tap_water"
                modal_fndds_code = modal_fndds_desc = modal_sr28_code = modal_sr28_desc = modal_leaf = ""
            elif tax and tax.product_identity and tax.canonical_path:
                tree_pid = tax.product_identity
                tree_canonical = tax.canonical_path
                tree_modifier = taxonomy_modifier(tax)
                tree_htc = taxonomy_htc(tax, "recipe_taxonomy_v2")
                score = floatish(tax.match_confidence) * 100.0
                status = "recipe_taxonomy_v2"
                fresh_override = fresh_recipe_path_override(item, tax)
                if fresh_override:
                    tree_pid, tree_canonical = fresh_override
                    status = "recipe_taxonomy_v2_fresh_override"
                tree_code = tax.fdc_id or tax.match_method or "recipe_taxonomy_v2"
                modal_fndds_code = modal_fndds_desc = modal_sr28_code = modal_sr28_desc = modal_leaf = ""
            else:
                node, score, status = resolve_recipe_node(item, row, nodes, exact, by_token)
                override = recipe_tree_override(item, row)

                if override and not node:
                    tree_pid, tree_canonical, tree_modifier, override_status = override
                    tree_htc = htc_from_tree_identity(
                        tree_canonical,
                        tree_pid,
                        tree_modifier,
                        raw_code=raw.code,
                        confidence=0.95,
                        source="recipe_title_tree",
                    )
                    status = override_status
                    tree_code = override_status
                    modal_fndds_code = modal_fndds_desc = modal_sr28_code = modal_sr28_desc = modal_leaf = ""
                elif node:
                    tree_htc = htc_from_tree_identity(
                        node.canonical_path,
                        node.product_identity,
                        node.modifier,
                        raw_code=raw.code,
                        confidence=0.95,
                        source="recipe_registry_tree",
                    )
                    tree_pid = node.product_identity
                    tree_canonical = node.canonical_path
                    tree_modifier = node.modifier
                    tree_code = node.code
                    modal_fndds_code = node.modal_fndds_code
                    modal_fndds_desc = node.modal_fndds_desc
                    modal_sr28_code = node.modal_sr28_code
                    modal_sr28_desc = node.modal_sr28_desc
                    modal_leaf = node.modal_retail_leaf_path
                elif status == "tap_water":
                    tree_htc = raw
                    tree_pid = "Tap Water"
                    tree_canonical = "__TAP_WATER__"
                    tree_modifier = ""
                    tree_code = "__TAP_WATER__"
                    modal_fndds_code = modal_fndds_desc = modal_sr28_code = modal_sr28_desc = modal_leaf = ""
                else:
                    tree_htc = raw
                    tree_pid = tree_canonical = tree_modifier = tree_code = ""
                    modal_fndds_code = modal_fndds_desc = modal_sr28_code = modal_sr28_desc = modal_leaf = ""

            status_counts[status] += 1

            group_counts[tree_htc.group] += 1
            rows.append({
                "ingredient_item": item,
                "recipe_count": row.get("recipe_count") or "",
                "grams_total": row.get("grams_total") or "",
                "raw_htc_code": raw.code,
                "raw_htc_group": raw.group,
                "raw_htc_family": raw.family,
                "raw_htc_form": raw.form,
                "raw_htc_processing": raw.processing,
                "raw_htc_ptype": raw.ptype,
                "raw_htc_confidence": f"{raw.confidence:.2f}" if raw.confidence else row.get("htc_confidence", ""),
                "raw_htc_source": raw.source or row.get("htc_source", ""),
                "tree_status": status,
                "tree_score": f"{score:.1f}",
                "identity_code": tree_code,
                "tree_product_identity": tree_pid,
                "tree_canonical_path": tree_canonical,
                "tree_modifier": tree_modifier,
                "tree_retail_leaf_path": modal_leaf,
                "tree_fndds_code": modal_fndds_code,
                "tree_fndds_desc": modal_fndds_desc,
                "tree_sr28_code": modal_sr28_code,
                "tree_sr28_desc": modal_sr28_desc,
                "htc_code": tree_htc.code,
                "htc_group": tree_htc.group,
                "htc_family": tree_htc.family,
                "htc_food": tree_htc.food,
                "htc_form": tree_htc.form,
                "htc_processing": tree_htc.processing,
                "htc_ptype": tree_htc.ptype,
                "htc_check": tree_htc.check,
                "htc_confidence": f"{tree_htc.confidence:.2f}",
                "htc_source": tree_htc.source,
            })
            if i % 5000 == 0:
                print(f"  recipe ingredients coded: {i:,}", flush=True)

    args.recipe_out.parent.mkdir(parents=True, exist_ok=True)
    with args.recipe_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "rows": len(rows),
        "tree_status_counts": dict(status_counts.most_common()),
        "htc_group_counts": dict(group_counts.most_common()),
        "elapsed_s": round(time.time() - t0, 1),
    }
    return rows, summary


def build_product_artifact(args: argparse.Namespace) -> tuple[list[dict[str, str]], dict[str, object]]:
    t0 = time.time()
    evidence = load_product_evidence(args.product_evidence)
    tax_by_upc, tax_by_title = load_api_taxonomy(args.api_taxonomy)
    con = sqlite3.connect(str(args.priced_db))
    con.row_factory = sqlite3.Row
    rows: list[dict[str, str]] = []
    source_counts: Counter[str] = Counter()
    authority_counts: Counter[str] = Counter()
    group_counts: Counter[str] = Counter()

    sql = """
        SELECT rowid, source, upc, name, brand, grams, cents, cpg, size_display,
               category_path, category_path_walmart, seller, marketplace,
               fulfilled_walmart, available, stock, search_term,
               htc_code, htc_group, htc_confidence,
               consensus_pid, consensus_canonical, consensus_modifier,
               consensus_flavor, bridge_status, non_food_path
        FROM priced_products
        WHERE grams > 0 AND cents > 0
    """
    for row in con.execute(sql):
        rowid = int(row["rowid"])
        ev = evidence.get(rowid)
        raw = decode_htc(row["htc_code"] or "", floatish(row["htc_confidence"]), "priced_db_raw")
        tax = lookup_api_taxonomy(row, tax_by_upc, tax_by_title)
        title_category_override = product_tree_override(row, ev)
        non_food_out = intish(row["non_food_path"])

        if is_retail_non_food_category(row):
            tree_pid = tree_canonical = tree_modifier = ""
            taxonomy_status = "retail_non_food_category"
            authority = "retail_non_food_category"
            tree_htc = decode_htc("N0000000", 1.0, "retail_non_food_category")
            non_food_out = 1
        elif title_category_override and title_category_override[4] == "api_cache_fresh_produce_title":
            tree_pid, tree_canonical, tree_modifier, taxonomy_status, authority = title_category_override
            tree_htc = (
                taxonomy_htc(tax, "api_taxonomy_v2")
                if tax and tax.htc_code
                else htc_from_tree_identity(
                    tree_canonical,
                    tree_pid,
                    tree_modifier,
                    raw_code=raw.code,
                    confidence=0.95,
                    source="product_tree_identity",
                )
            )
            non_food_out = 0
        elif tax and tax.product_identity and tax.canonical_path:
            tree_pid = tax.product_identity
            tree_canonical = tax.canonical_path
            tree_modifier = taxonomy_modifier(tax)
            taxonomy_status = tax.match_method or "api_taxonomy_v2"
            authority = "api_taxonomy_v2"
            tree_htc = taxonomy_htc(tax, "api_taxonomy_v2")
            non_food_out = 1 if tree_htc.group == "N" or tree_canonical.startswith("Non-Food") else 0
        else:
            tree_pid, tree_canonical, tree_modifier, taxonomy_status, authority = chosen_product_tree(row, ev)
            tree_modifier = product_modifier_with_slot_text(row, tree_pid, tree_canonical, tree_modifier)
            non_food_out = intish(row["non_food_path"])
            if tree_pid and tree_canonical and non_food_out == 0:
                tree_htc = htc_from_tree_identity(
                    tree_canonical,
                    tree_pid,
                    tree_modifier,
                    raw_code=raw.code,
                    confidence=0.95,
                    source="product_tree_identity",
                )
            elif non_food_out == 1 or authority == "evidence_reject":
                tree_htc = decode_htc("N0000000", 1.0, "non_food_or_rejected")
            else:
                tree_htc = raw

        source_counts[str(row["source"] or "")] += 1
        authority_counts[authority] += 1
        group_counts[tree_htc.group] += 1
        rows.append({
            "source": row["source"] or "",
            "rowid": str(rowid),
            "upc": row["upc"] or "",
            "name": row["name"] or "",
            "brand": row["brand"] or "",
            "grams": f"{float(row['grams']):.6g}",
            "cents": str(int(row["cents"])),
            "cpg": f"{float(row['cents']) / float(row['grams']):.8f}",
            "size_display": row["size_display"] or "",
            "category_path": row["category_path"] or "",
            "category_path_walmart": row["category_path_walmart"] or "",
            "seller": row["seller"] or "",
            "marketplace": str(intish(row["marketplace"])),
            "fulfilled_walmart": str(intish(row["fulfilled_walmart"])),
            "available": str(intish(row["available"])),
            "stock": row["stock"] or "",
            "search_term": row["search_term"] or "",
            "raw_htc_code": raw.code,
            "raw_htc_group": raw.group,
            "raw_htc_family": raw.family,
            "raw_htc_confidence": f"{raw.confidence:.2f}",
            "tree_authority": authority,
            "taxonomy_status": taxonomy_status,
            "tree_product_identity": tree_pid,
            "tree_canonical_path": tree_canonical,
            "tree_modifier": tree_modifier,
            "tree_path_group": group_from_tree_path(tree_canonical, tree_pid),
            "htc_code": tree_htc.code,
            "htc_group": tree_htc.group,
            "htc_family": tree_htc.family,
            "htc_food": tree_htc.food,
            "htc_form": tree_htc.form,
            "htc_processing": tree_htc.processing,
            "htc_ptype": tree_htc.ptype,
            "htc_check": tree_htc.check,
            "htc_confidence": f"{tree_htc.confidence:.2f}",
            "htc_source": tree_htc.source,
            "non_food_path": str(non_food_out),
        })

    args.products_out.parent.mkdir(parents=True, exist_ok=True)
    with args.products_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "rows": len(rows),
        "source_counts": dict(source_counts.most_common()),
        "tree_authority_counts": dict(authority_counts.most_common()),
        "htc_group_counts": dict(group_counts.most_common()),
        "elapsed_s": round(time.time() - t0, 1),
    }
    return rows, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingredients", type=Path, default=DEFAULT_INGREDIENT_HTC)
    parser.add_argument("--recipe-taxonomy", type=Path, default=DEFAULT_RECIPE_TAXONOMY)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--priced-db", type=Path, default=DEFAULT_PRICED_DB)
    parser.add_argument("--product-evidence", type=Path, default=DEFAULT_PRODUCT_EVIDENCE)
    parser.add_argument("--api-taxonomy", type=Path, default=DEFAULT_API_TAXONOMY)
    parser.add_argument("--recipe-out", type=Path, default=OUT_RECIPE)
    parser.add_argument("--products-out", type=Path, default=OUT_PRODUCTS)
    parser.add_argument("--summary-out", type=Path, default=OUT_SUMMARY)
    args = parser.parse_args()

    print(f"building recipe HTC/tree artifact -> {args.recipe_out}", flush=True)
    _, recipe_summary = build_recipe_artifact(args)
    print(json.dumps(recipe_summary, indent=2, sort_keys=True), flush=True)

    print(f"building store product HTC/tree artifact -> {args.products_out}", flush=True)
    _, product_summary = build_product_artifact(args)
    print(json.dumps(product_summary, indent=2, sort_keys=True), flush=True)

    summary = {
        "recipe": recipe_summary,
        "products": product_summary,
        "inputs": {
            "ingredients": str(args.ingredients),
            "recipe_taxonomy": str(args.recipe_taxonomy),
            "registry": str(args.registry),
            "priced_db": str(args.priced_db),
            "product_evidence": str(args.product_evidence),
            "api_taxonomy": str(args.api_taxonomy),
        },
        "outputs": {
            "recipe": str(args.recipe_out),
            "products": str(args.products_out),
        },
    }
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {args.summary_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
