#!/usr/bin/env python3
"""Tag Walmart/Kroger API cache products with retail taxonomy identities.

The API cache only has product names plus the query term that found the row.
This pass projects those products into the same curated retail taxonomy used by
``retail_mapper/v2/consensus_full_corpus_audit.csv``. HTC encoding can then use
``canonical_path`` + ``product_identity_fixed`` instead of guessing from a raw
brand-laden title.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recipe_mapper" / "v1"))
sys.path.insert(0, str(ROOT / "retail_mapper" / "v2"))

from htc.encoder import encode, family_from_identity, group_from_canonical_path  # noqa: E402
from htc.food_slots import (  # noqa: E402
    FoodSlotEntry,
    candidate_food_keys,
    default_registry,
    effective_food_name,
    normalize_key,
    primary_modifier,
)

try:  # noqa: E402
    from product_class_router import route_product
except Exception:  # pragma: no cover - script fallback
    route_product = None  # type: ignore[assignment]


DEFAULT_INPUT = ROOT / "recipe_pricing" / "data" / "api_cache_products.csv"
DEFAULT_AUDIT = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
DEFAULT_OUTPUT = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_tagged.csv"
DEFAULT_REVIEW = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_review.csv"

PACKAGE_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?|\d+/\d+)\s*(?:fl\s*)?"
    r"(?:oz|ounce|ounces|lb|lbs|pound|pounds|g|gram|grams|kg|ml|l|liter|liters|"
    r"ct|count|pack|pk|case|each)\b",
    re.I,
)
MARKETING_RE = re.compile(
    r"\b(?:fresh|premium|natural|naturally|classic|original|great value|simple truth|"
    r"private selection|kroger|walmart|big deal|signature|select|organic)\b",
    re.I,
)
COMPOUND_REPLACEMENTS = (
    (re.compile(r"\balmondmilk\b", re.I), "almond milk"),
    (re.compile(r"\bsoymilk\b", re.I), "soy milk"),
    (re.compile(r"\bcashewmilk\b", re.I), "cashew milk"),
    (re.compile(r"\boatmilk\b", re.I), "oat milk"),
    (re.compile(r"\bcoconutmilk\b", re.I), "coconut milk"),
    (re.compile(r"\bplantmilk\b", re.I), "plant milk"),
)
NON_GROCERY_RE = re.compile(
    r"\b(?:concealer|blush|lipstick|lip\s+balm|mascara|eyeliner|foundation|"
    r"face\s+wash|body\s+wash|shampoo|conditioner|deodorant|toothpaste|mouthwash|"
    r"sensodyne|pronamel|denture|retainer\s+cleanser|cleanser\s+tablets?|"
    r"detergent|cleaner|laundry|dishwasher|paper\s+towels?|toilet\s+paper|"
    r"diapers?|cat\s+food|dog\s+food|pet\s+food|puppy|kitten|cat\s+litter|"
    r"clumping\s+litter|\blitter\b|fresh\s+step|clean\s+paws|febreze|"
    r"fragrance\s+oils?|essential\s+oils?|scented\s+oils?|perfume\s+oils?|"
    r"home\s+fragrances?|diffusers?|humidifiers?|aromatherapy|perfume|cologne|"
    r"eau\s+de\s+(?:parfum|toilette)|storage\s+bags?|freezer\s+bags?|ziploc|"
    r"condoms?|stapler|transparent\s+tape|duct\s+tape|incense|body\s+lotion|"
    r"body\s+cream|candle\s+making|soap\s+making|room\s+sprays?|bath\s+bombs?|"
    r"slime|cough\s+drops?|cold\s+medicine|caplets?|softgels?|dietary\s+supplement|"
    r"cleanser|bleach|broom|lure)\b|"
    r"\be\.?\s*l\.?\s*f\.?\b",
    re.I,
)

TAXONOMY_ROUTE_FORCED: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bmicrowave\s+popcorn\b", re.I), "Snack > Popcorn > Microwave Popcorn"),
    (re.compile(r"\bkettle\s+corn\b", re.I), "Snack > Popcorn > Kettle Corn"),
    (re.compile(r"\bcaramel\s+(?:popcorn|corn)\b", re.I), "Snack > Popcorn > Caramel Corn"),
    (re.compile(r"\bpopcorn\b(?!\s*(?:chicken|shrimp|cauliflower))", re.I), "Snack > Popcorn"),
    (re.compile(r"\bcream(?:ed|[- ]style)\s+corn\b", re.I), "Pantry > Canned Vegetables > Creamed Corn"),
    (re.compile(r"\b(?:whole\s+kernel\s+)?sweet\s+corn\b|\b(?:golden|white|yellow)\s+whole\s+kernel\s+corn\b|\bcanned\s+corn\b|\bcorn\b.*\bcan\b", re.I), "Frozen > Vegetables > Corn"),
    (re.compile(r"\b(?:condensed\s+)?french\s+onion\s+soup\b", re.I), "Pantry > Soup > French Onion Soup"),
    (re.compile(r"\bonion\s+soup\s+(?:and\s+)?dip\s+mix\b", re.I), "Pantry > Salad Dressings > Onion Soup and Dip Mix"),
    (re.compile(r"\bbetter\s+than\s+bouillon\b|\bbouillon\b", re.I), "Pantry > Spices & Seasonings > Bouillon"),
    (re.compile(r"\bchicken\s+(?:broth|stock)\b", re.I), "Pantry > Broth & Stock > Chicken Broth"),
    (re.compile(r"\bbeef\s+(?:broth|stock)\b", re.I), "Pantry > Broth & Stock > Beef Broth"),
    (re.compile(r"\bvegetable\s+(?:broth|stock)\b", re.I), "Pantry > Broth & Stock > Vegetable Broth"),
    (re.compile(r"\b(?:egg\s*nog|eggnog)\s+syrup\b", re.I), "Pantry > Sweeteners > Syrup"),
    (re.compile(r"\bchocolate\s+syrup\b", re.I), "Beverage > Hot Cocoa > Chocolate Syrup"),
    (re.compile(r"\bstrawberry\s+(?:flavored\s+)?syrup\b", re.I), "Pantry > Sweeteners > Strawberry Syrup"),
    (re.compile(r"\bhot\s+cocoa\s+mix\b", re.I), "Beverage > Hot Cocoa > Hot Cocoa Mix"),
    (re.compile(r"\bbrownie\s+mix\b", re.I), "Pantry > Baking Mixes > Brownie Mix"),
    (re.compile(r"\bbagels?\b", re.I), "Bakery > Bagels"),
    (re.compile(r"\bgarlic\s+powder\b", re.I), "Pantry > Spices & Seasonings > Garlic Powder"),
    (re.compile(r"\bonion\s+powder\b", re.I), "Pantry > Spices & Seasonings > Onion Powder"),
    (re.compile(r"\bsalmon\b", re.I), "Meat & Seafood > Fish > Salmon"),
    (re.compile(r"\btuna\b", re.I), "Meat & Seafood > Fish > Tuna"),
    (re.compile(r"\bshrimp\b", re.I), "Meat & Seafood > Shellfish > Shrimp"),
    (re.compile(r"\balmond\s*milk\b|\balmondmilk\b", re.I), "Beverage > Plant Milk > Almond Milk"),
    (re.compile(r"\bsoy\s*milk\b|\bsoymilk\b", re.I), "Beverage > Plant Milk > Soy Milk"),
    (re.compile(r"\bcashew\s*milk\b|\bcashewmilk\b", re.I), "Beverage > Plant Milk > Cashew Milk"),
    (re.compile(r"\boat\s*milk\b|\boatmilk\b", re.I), "Beverage > Plant Milk > Oat Milk"),
    (re.compile(r"\bcoconut\s*milk\b|\bcoconutmilk\b", re.I), "Beverage > Plant Milk > Coconut Milk"),
    (re.compile(r"\bplant\s*milk\b|\bnon[- ]dairy\s+milk\b", re.I), "Beverage > Plant Milk"),
)

GENERIC_ALIAS_KEYS = {
    "food",
    "foods",
    "product",
    "products",
    "meal",
    "meals",
    "single entree",
    "family entree",
    "entree",
    "dish",
    "dishes",
    "mix",
    "blend",
    "sauce",
    "seasoning",
    "snack",
    "beverage",
    "drink",
    "fruit",
    "vegetable",
    "vegetables",
    "meat",
    "seafood",
    "dairy",
    "frozen",
    "pantry",
    "bakery",
    "plain",
}


def clean_title(name: str) -> str:
    value = name or ""
    for pattern, replacement in COMPOUND_REPLACEMENTS:
        value = pattern.sub(replacement, value)
    value = PACKAGE_RE.sub(" ", value)
    value = MARKETING_RE.sub(" ", value)
    value = re.sub(r"[\u00ae\u2122]", " ", value)
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" ,;-")
    return value


def normalized(value: str) -> str:
    value = clean_title(value)
    return normalize_key(value)


def path_prefix_matches(path: str, prefix: str) -> bool:
    if not path or not prefix:
        return False
    path_norm = " > ".join(part.strip().lower() for part in path.split(">") if part.strip())
    prefix_norm = " > ".join(part.strip().lower() for part in prefix.split(">") if part.strip())
    return path_norm.startswith(prefix_norm) or prefix_norm.startswith(path_norm)


def top_department(path: str) -> str:
    return (path or "").split(">", 1)[0].strip().lower()


def leaf_keys(path: str) -> set[str]:
    leaf = (path or "").split(">")[-1].strip()
    keys = {normalize_key(leaf)}
    leaf_lc = leaf.lower()
    if leaf_lc.endswith("ies") and len(leaf_lc) > 4:
        keys.add(normalize_key(leaf_lc[:-3] + "y"))
    if leaf_lc.endswith("es") and len(leaf_lc) > 3:
        keys.add(normalize_key(leaf_lc[:-2]))
    if leaf_lc.endswith("s") and len(leaf_lc) > 2:
        keys.add(normalize_key(leaf_lc[:-1]))
    return {key for key in keys if key and not is_generic_alias(key)}


def forced_taxonomy_route(text: str) -> str | None:
    for pattern, path in TAXONOMY_ROUTE_FORCED:
        if pattern.search(text or ""):
            return path
    return None


def is_generic_alias(key: str) -> bool:
    if not key:
        return True
    if key in GENERIC_ALIAS_KEYS:
        return True
    toks = key.split()
    return len(toks) == 1 and (len(toks[0]) < 3 or toks[0] in GENERIC_ALIAS_KEYS)


def candidate_aliases(entry: FoodSlotEntry) -> list[str]:
    values = [entry.food_name, entry.product_identity_fixed]
    if entry.rule == "B" and entry.primary_modifier:
        values.append(f"{entry.primary_modifier} {entry.product_identity_fixed}".strip())
    parts = [part.strip() for part in (entry.canonical_path or "").split(">") if part.strip()]
    if parts:
        values.append(parts[-1])
    if len(parts) >= 2:
        values.append(" ".join(parts[-2:]))

    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if entry.rule == "B":
            keys = [normalize_key(value)]
        else:
            keys = candidate_food_keys(value)
        for key in keys:
            if len(key.split()) > 8:
                continue
            if is_generic_alias(key) or key in seen:
                continue
            seen.add(key)
            out.append(key)
    return out


@dataclass(frozen=True)
class TaxonomyCandidate:
    canonical_path: str
    canonical_label: str
    product_identity_fixed: str
    modifier: str
    retail_leaf_path: str
    food_name: str
    htc_group: str
    htc_family: str
    htc_food: str
    row_count: int
    rule: str


@dataclass
class Match:
    candidate: TaxonomyCandidate
    alias: str
    score: float
    source: str
    reason: str


class RetailTaxonomyIndex:
    def __init__(self, audit_path: Path) -> None:
        self.audit_path = audit_path
        self.alias_index: dict[str, list[TaxonomyCandidate]] = defaultdict(list)
        self.path_index: dict[str, list[TaxonomyCandidate]] = defaultdict(list)
        self.exact_title_index: dict[str, TaxonomyCandidate] = {}
        self.slot_mode_index: dict[tuple[str, str, str, str], dict[str, str]] = {}
        self.max_alias_tokens = 1
        self._build()

    def _build(self) -> None:
        audit_modes = self._load_audit_modes()
        registry = default_registry()

        candidates: list[TaxonomyCandidate] = []
        for entry in registry.entries:
            if entry.htc_group in {"0", ""}:
                continue
            entry_mod = primary_modifier(entry.primary_modifier)
            slot_mod = entry_mod if entry.rule == "B" else ""
            slot_mode = self.slot_mode_index.get((
                entry.product_identity_fixed,
                entry.htc_group,
                entry.htc_family,
                slot_mod,
            ))
            key = (
                entry.canonical_path,
                entry.product_identity_fixed,
                entry_mod,
            )
            fallback_key = (entry.canonical_path, entry.product_identity_fixed, "")
            mode = slot_mode or audit_modes.get(key) or audit_modes.get(fallback_key) or {}
            canonical_path = mode.get("canonical_path") or entry.canonical_path
            modifier = mode.get("modifier") or (entry.primary_modifier if entry.rule == "B" else "")
            leaf = mode.get("retail_leaf_path") or self._leaf_path(canonical_path, modifier)
            label = mode.get("canonical_label") or self._label(entry.product_identity_fixed, modifier)
            candidate = TaxonomyCandidate(
                canonical_path=canonical_path,
                canonical_label=label,
                product_identity_fixed=entry.product_identity_fixed,
                modifier=modifier,
                retail_leaf_path=leaf,
                food_name=entry.food_name,
                htc_group=entry.htc_group,
                htc_family=entry.htc_family,
                htc_food=entry.food_slot,
                row_count=entry.row_count,
                rule=entry.rule,
            )
            candidates.append(candidate)

        for candidate in candidates:
            for alias in candidate_aliases(
                FoodSlotEntry(
                    htc_group=candidate.htc_group,
                    htc_family=candidate.htc_family,
                    food_key=normalize_key(candidate.food_name),
                    food_name=candidate.food_name,
                    food_slot=candidate.htc_food,
                    row_count=candidate.row_count,
                    canonical_path=candidate.canonical_path,
                    product_identity_fixed=candidate.product_identity_fixed,
                    primary_modifier=primary_modifier(candidate.modifier),
                    rule=candidate.rule,
                )
            ):
                self.alias_index[alias].append(candidate)
                self.max_alias_tokens = max(self.max_alias_tokens, len(alias.split()))
            self.path_index[candidate.canonical_path.lower()].append(candidate)

        for rows in self.alias_index.values():
            rows.sort(key=lambda item: (-item.row_count, item.canonical_path, item.food_name))
        for rows in self.path_index.values():
            rows.sort(key=lambda item: (-item.row_count, item.food_name))

    def _load_audit_modes(self) -> dict[tuple[str, str, str], dict[str, str]]:
        grouped: dict[tuple[str, str, str], dict[str, Counter[str] | int]] = {}
        title_hits: dict[str, Counter[tuple[str, str, str]]] = defaultdict(Counter)
        slot_counts: dict[tuple[str, str, str, str], Counter[tuple[str, str, str]]] = defaultdict(Counter)

        with self.audit_path.open(encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                path = (row.get("canonical_path") or "").strip()
                pid = (row.get("product_identity_fixed") or "").strip()
                if not path or not pid:
                    continue
                mod = primary_modifier(row.get("modifier") or "")
                food_name = effective_food_name(path, pid, mod)
                key_mod = mod if food_name != pid else ""
                key = (path, pid, key_mod)
                group = group_from_canonical_path(path, food_name)
                family = family_from_identity(group, f"{path} {pid} {mod} {food_name}", path, food_name=food_name)
                if group:
                    slot_counts[(pid, group, family, key_mod)][key] += 1
                bucket = grouped.setdefault(
                    key,
                    {
                        "count": 0,
                        "modifier": Counter(),
                        "canonical_label": Counter(),
                        "retail_leaf_path": Counter(),
                    },
                )
                bucket["count"] = int(bucket["count"]) + 1
                for field in ("modifier", "canonical_label", "retail_leaf_path"):
                    value = (row.get(field) or "").strip()
                    if value:
                        counter = bucket[field]
                        assert isinstance(counter, Counter)
                        counter[value] += 1
                title_key = normalized(row.get("title") or "")
                if title_key:
                    title_hits[title_key][key] += 1

        modes: dict[tuple[str, str, str], dict[str, str]] = {}
        for key, bucket in grouped.items():
            out: dict[str, str] = {}
            out["canonical_path"] = key[0]
            out["product_identity_fixed"] = key[1]
            out["key_modifier"] = key[2]
            out["row_count"] = str(bucket["count"])
            for field in ("modifier", "canonical_label", "retail_leaf_path"):
                counter = bucket[field]
                assert isinstance(counter, Counter)
                out[field] = counter.most_common(1)[0][0] if counter else ""
            modes[key] = out

        for slot_key, counts in slot_counts.items():
            best_key = counts.most_common(1)[0][0]
            mode = modes.get(best_key)
            if mode:
                self.slot_mode_index[slot_key] = mode

        for title_key, counts in title_hits.items():
            key = counts.most_common(1)[0][0]
            mode = modes.get(key)
            if mode:
                self.exact_title_index[title_key] = TaxonomyCandidate(
                    canonical_path=key[0],
                    canonical_label=mode.get("canonical_label", ""),
                    product_identity_fixed=key[1],
                    modifier=mode.get("modifier", ""),
                    retail_leaf_path=mode.get("retail_leaf_path", ""),
                    food_name=effective_food_name(key[0], key[1], mode.get("modifier", "")),
                    htc_group="",
                    htc_family="",
                    htc_food="",
                    row_count=counts.most_common(1)[0][1],
                    rule="exact_title",
                )
        return modes

    @staticmethod
    def _label(pid: str, modifier: str) -> str:
        mod = primary_modifier(modifier)
        if mod and normalize_key(mod) not in {"plain", "regular", "original", "classic"}:
            return f"{pid} ({mod})"
        return pid

    @staticmethod
    def _leaf_path(path: str, modifier: str) -> str:
        mod = primary_modifier(modifier)
        if mod and normalize_key(mod) not in {"plain", "regular", "original", "classic"}:
            return f"{path} > {mod}"
        return path

    def match(self, name: str, search_term: str) -> Match | None:
        clean = clean_title(name)
        title_key = normalized(clean)
        search_key = normalized(search_term)
        combined_key = normalized(f"{clean} {search_term}")
        forced_route = forced_taxonomy_route(f"{clean} {search_term}")
        route_prefix = forced_route
        if not route_prefix and route_product:
            route_prefix = route_product("", search_term, f"{clean} {search_term}")
        hint = encode(category="", description=clean, extra="", food_name=search_term or clean)

        if NON_GROCERY_RE.search(name or ""):
            return None

        exact = self.exact_title_index.get(title_key)
        if exact:
            return Match(exact, title_key, 1_000.0, "exact_title", "normalized title matched audited retail title")

        matches: dict[tuple[str, str, str, str], Match] = {}
        for alias, alias_source in self._matched_aliases(title_key, search_key, combined_key):
            for candidate in self.alias_index.get(alias, [])[:40]:
                if forced_route and not path_prefix_matches(candidate.canonical_path, forced_route):
                    continue
                score, reason = self._score(candidate, alias, alias_source, title_key, search_key, route_prefix, hint)
                if score < 0:
                    continue
                key = (
                    candidate.canonical_path,
                    candidate.product_identity_fixed,
                    primary_modifier(candidate.modifier),
                    candidate.food_name,
                )
                prev = matches.get(key)
                if prev is None or score > prev.score:
                    matches[key] = Match(candidate, alias, score, alias_source, reason)

        if route_prefix:
            for candidate in self._route_candidates(route_prefix):
                alias = normalize_key(candidate.food_name)
                score, reason = self._score(candidate, alias, "route", title_key, search_key, route_prefix, hint)
                score += 18.0
                key = (
                    candidate.canonical_path,
                    candidate.product_identity_fixed,
                    primary_modifier(candidate.modifier),
                    candidate.food_name,
                )
                prev = matches.get(key)
                if prev is None or score > prev.score:
                    matches[key] = Match(candidate, alias, score, "route", f"route prefix {route_prefix}; {reason}")

        if not matches:
            return None
        valid_matches: list[Match] = []
        for match in matches.values():
            if match.score < 34.0:
                continue
            title_supported = self._title_supports(match.candidate, title_key)
            # Search-only and route-only matches are query leakage unless the
            # product title itself supports the identity candidate.
            if match.source == "search" and (match.score < 62.0 or not title_supported):
                continue
            if match.source == "route" and not title_supported:
                continue
            valid_matches.append(match)
        if not valid_matches:
            return None
        best = max(valid_matches, key=lambda item: (item.score, item.candidate.row_count))
        return best

    def _matched_aliases(self, title_key: str, search_key: str, combined_key: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for key in candidate_food_keys(search_key):
            if key in self.alias_index:
                pair = (key, "search")
                if pair not in seen:
                    seen.add(pair)
                    out.append(pair)
        for key in candidate_food_keys(title_key):
            if key in self.alias_index:
                pair = (key, "title")
                if pair not in seen:
                    seen.add(pair)
                    out.append(pair)

        toks = combined_key.split()
        max_len = min(self.max_alias_tokens, len(toks), 8)
        for size in range(max_len, 0, -1):
            for start in range(0, len(toks) - size + 1):
                key = " ".join(toks[start:start + size])
                if key not in self.alias_index:
                    continue
                source = "title" if key in title_key else "search"
                pair = (key, source)
                if pair not in seen:
                    seen.add(pair)
                    out.append(pair)
        return out

    def _route_candidates(self, route_prefix: str) -> list[TaxonomyCandidate]:
        route_norm = route_prefix.lower()
        route_leaf_keys = leaf_keys(route_prefix)
        rows: list[TaxonomyCandidate] = []
        for path, candidates in self.path_index.items():
            if path.startswith(route_norm) or route_norm.startswith(path):
                for candidate in candidates[:20]:
                    identity_text = normalize_key(
                        f"{candidate.food_name} {candidate.product_identity_fixed} {primary_modifier(candidate.modifier)}"
                    )
                    if route_leaf_keys and not any(key in identity_text for key in route_leaf_keys):
                        continue
                    rows.append(candidate)
        rows.sort(key=lambda item: (-item.row_count, item.food_name))
        return rows[:50]

    def _score(
        self,
        candidate: TaxonomyCandidate,
        alias: str,
        alias_source: str,
        title_key: str,
        search_key: str,
        route_prefix: str | None,
        hint,
    ) -> tuple[float, str]:
        alias_tokens = len(alias.split())
        score = 12.0 * min(alias_tokens, 6) + math.log1p(max(candidate.row_count, 1))
        reason_parts = [f"{alias_source}:{alias}"]

        if alias_source == "title":
            score += 22.0
        elif alias_source == "search":
            score += 12.0
        elif alias_source == "route":
            score += 10.0

        if search_key and alias == search_key:
            score += 24.0
            reason_parts.append("search_exact")
        if title_key and alias in title_key:
            score += 16.0
            reason_parts.append("title_phrase")

        if route_prefix:
            if path_prefix_matches(candidate.canonical_path, route_prefix):
                score += 34.0
                reason_parts.append(f"route={route_prefix}")
            elif top_department(candidate.canonical_path) == top_department(route_prefix):
                score += 5.0
            else:
                score -= 10.0

        if hint.group not in {"", "0", "N"}:
            if candidate.htc_group == hint.group and (not hint.family or candidate.htc_family == hint.family):
                score += 22.0
                reason_parts.append(f"htc_hint={hint.group}{hint.family}")
            elif candidate.htc_group == hint.group:
                score += 10.0
                reason_parts.append(f"htc_group={hint.group}")
            else:
                score -= 8.0

        if is_generic_alias(alias):
            score -= 20.0
        if candidate.rule == "B" and alias_tokens >= 2:
            score += 7.0
        return score, ";".join(reason_parts)

    def _title_supports(self, candidate: TaxonomyCandidate, title_key: str) -> bool:
        if not title_key:
            return False
        support_values = [
            candidate.food_name,
            candidate.product_identity_fixed,
            primary_modifier(candidate.modifier),
        ]
        for value in support_values:
            for key in candidate_food_keys(value):
                if key and key in title_key and not is_generic_alias(key):
                    return True
        return False


def confidence_from_score(score: float) -> float:
    if score >= 120:
        return 0.99
    if score >= 95:
        return 0.94
    if score >= 75:
        return 0.88
    if score >= 55:
        return 0.78
    if score >= 34:
        return 0.64
    return 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--review-limit", type=int, default=5000)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.review_output.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    index = RetailTaxonomyIndex(args.audit)
    print(f"built taxonomy index ({len(index.alias_index):,} aliases, max alias tokens={index.max_alias_tokens})")

    counts: Counter[str] = Counter()
    path_counts: Counter[str] = Counter()
    review_rows: list[dict[str, str]] = []
    rows = 0

    with args.input.open(encoding="utf-8", errors="replace", newline="") as src, args.output.open(
        "w", encoding="utf-8", newline=""
    ) as dst:
        reader = csv.DictReader(src)
        base_fields = list(reader.fieldnames or [])
        extra_fields = [
            "clean_name",
            "canonical_path",
            "canonical_label",
            "product_identity_fixed",
            "modifier",
            "retail_leaf_path",
            "taxonomy_confidence",
            "taxonomy_source",
            "taxonomy_reason",
        ]
        writer = csv.DictWriter(dst, fieldnames=base_fields + [field for field in extra_fields if field not in base_fields])
        writer.writeheader()

        for row in reader:
            rows += 1
            name = row.get("name") or ""
            search = row.get("search_term") or ""
            clean = clean_title(name)
            match = index.match(name, search)
            row["clean_name"] = clean
            if NON_GROCERY_RE.search(name or ""):
                row.update({
                    "canonical_path": "",
                    "canonical_label": "",
                    "product_identity_fixed": "",
                    "modifier": "",
                    "retail_leaf_path": "",
                    "taxonomy_confidence": "1.00",
                    "taxonomy_source": "non_food",
                    "taxonomy_reason": "non-grocery title pattern",
                })
                counts["non_food"] += 1
            elif match:
                candidate = match.candidate
                row.update({
                    "canonical_path": candidate.canonical_path,
                    "canonical_label": candidate.canonical_label,
                    "product_identity_fixed": candidate.product_identity_fixed,
                    "modifier": candidate.modifier,
                    "retail_leaf_path": candidate.retail_leaf_path,
                    "taxonomy_confidence": f"{confidence_from_score(match.score):.2f}",
                    "taxonomy_source": match.source,
                    "taxonomy_reason": match.reason,
                })
                counts[match.source] += 1
                path_counts[candidate.canonical_path] += 1
            else:
                row.update({
                    "canonical_path": "",
                    "canonical_label": "",
                    "product_identity_fixed": "",
                    "modifier": "",
                    "retail_leaf_path": "",
                    "taxonomy_confidence": "0.00",
                    "taxonomy_source": "unresolved",
                    "taxonomy_reason": "no audited identity alias matched title",
                })
                counts["unresolved"] += 1
                if len(review_rows) < args.review_limit:
                    review_rows.append({
                        "source": row.get("source", ""),
                        "upc": row.get("upc", ""),
                        "name": name,
                        "search_term": search,
                        "clean_name": clean,
                        "taxonomy_reason": row["taxonomy_reason"],
                    })
            writer.writerow(row)
            if rows % 50000 == 0:
                print(f"  tagged {rows:,} products", flush=True)

    if review_rows:
        with args.review_output.open("w", encoding="utf-8", newline="") as dst:
            writer = csv.DictWriter(dst, fieldnames=list(review_rows[0]))
            writer.writeheader()
            writer.writerows(review_rows)

    print(f"wrote {args.output} ({rows:,} rows, {time.time() - t0:.1f}s)")
    print("taxonomy sources:", dict(counts.most_common()))
    print("top paths:", dict(path_counts.most_common(20)))
    if review_rows:
        print(f"wrote review sample {args.review_output} ({len(review_rows):,} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
