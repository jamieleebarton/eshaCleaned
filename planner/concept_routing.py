"""Shared recipe-line concept routing helpers.

The planner builder and the line-level audit must make the same decision:
recipe display text -> HTC form code -> priced product concept. Keeping that
logic here prevents audit/build drift.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "recipe_mapper" / "v1"))
from htc.encoder import encode  # noqa: E402

from planner.line_identity_overrides import line_canonical_path_override

HTC_TAGGED = ROOT / "recipe_mapper" / "v1" / "output" / "consensus_htc_tagged.csv"
V2 = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
OVERRIDES = ROOT / "recipe_pricing" / "htc_cp_overrides.csv"
CONCEPT_INDEX = ROOT / "planner" / "data" / "concept_index.json"

BAD_HTC_GROUPS = {"0", "N"}
RAW_TOPS = {
    "Pantry",
    "Produce",
    "Dairy",
    "Meat & Seafood",
    "Bakery",
    "Frozen",
    "Beverage",
    "Meal",
}


def valid_htc_form(htc_form: str) -> bool:
    return bool(htc_form) and htc_form != "00000000" and htc_form[:1] not in BAD_HTC_GROUPS


def specific_recipe_path(path: str) -> bool:
    path = (path or "").strip()
    return bool(path) and " > " in path and not path.startswith("Non-Food")


def load_htc_to_path(path: Path = HTC_TAGGED) -> dict[str, str]:
    """Build a conservative identity-HTC -> canonical_path fallback map."""
    htc_cp_counts: dict[str, Counter] = {}
    with path.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            htc = (row.get("htc_code") or "").strip().lstrip("~")
            cp = (row.get("canonical_path") or "").strip()
            if not htc or not cp or cp == "Pantry" or cp.startswith("Non-Food"):
                continue
            htc_cp_counts.setdefault(htc, Counter())[cp] += 1

    out: dict[str, str] = {}
    min_fdc_agree = 2
    for htc, counter in htc_cp_counts.items():
        raw = [(cp, n) for cp, n in counter.items() if cp.split(" > ")[0] in RAW_TOPS]
        candidates = raw or list(counter.items())
        candidates.sort(key=lambda item: -item[1])
        cp, count = candidates[0]
        if count >= min_fdc_agree:
            out[htc] = cp
    return out


def load_title_maps(path: Path = V2) -> tuple[dict[str, str], dict[str, str]]:
    title_to_path: dict[str, str] = {}
    title_to_mod: dict[str, str] = {}
    with path.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            title = (row.get("title") or "").strip().lower()
            cp = (row.get("canonical_path") or "").strip()
            mod = (row.get("modifier") or "").strip()
            if not title:
                continue
            if cp:
                title_to_path[title] = cp
            title_to_mod[title] = mod or "Plain"
    return title_to_path, title_to_mod


def load_item_overrides(path: Path = OVERRIDES) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            item = (row.get("item") or "").strip().lower()
            cp = (row.get("canonical_path") or "").strip()
            if item and cp:
                out[item] = cp
    return out


def load_form_path_authority(path: Path = CONCEPT_INDEX) -> dict[str, str]:
    """Build an HTC-form -> canonical_path authority from priced concepts.

    This is the structural coupling the planner should use before falling
    back to stale recipe taxonomy columns. A form code only wins when priced
    products overwhelmingly agree on one real food path.
    """
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    counts: dict[str, Counter] = {}
    for ck, meta in data.items():
        htc = (meta.get("htc_form") or "").strip().lstrip("~")
        cp = (meta.get("canonical_path") or "").strip()
        if not htc and "|" in ck:
            _, htc = ck.rsplit("|", 1)
        if not cp and "|" in ck:
            cp, _ = ck.rsplit("|", 1)
        if not valid_htc_form(htc) or not cp or cp.startswith("Non-Food"):
            continue
        top = cp.split(" > ")[0] if cp else ""
        if top not in RAW_TOPS:
            continue
        try:
            n_skus = int(meta.get("n_skus_total") or 0)
        except (TypeError, ValueError):
            n_skus = 0
        if n_skus <= 0:
            n_skus = len(meta.get("packages") or [])
        if n_skus <= 0:
            continue
        counts.setdefault(htc, Counter())[cp] += n_skus

    out: dict[str, str] = {}
    for htc, counter in counts.items():
        ranked = counter.most_common()
        top_cp, top_n = ranked[0]
        second_n = ranked[1][1] if len(ranked) > 1 else 0
        if top_n < 2:
            continue
        if second_n and top_n < second_n * 2:
            continue
        out[htc] = top_cp
    return out


def encode_recipe_intent_htc(
    item: str,
    display: str,
    cache: dict[tuple[str, str], str],
) -> str:
    item = (item or "").strip().lower()
    display = (display or "").strip()
    if not item and not display:
        return ""
    key = (item, display.lower())
    if key not in cache:
        try:
            cache[key] = encode(
                "",
                description=display or item,
                extra=item,
                food_name=item,
                canonical_path="",
                identity_mode=False,
            ).code
        except Exception:
            cache[key] = ""
    encoded = cache[key]
    return encoded if valid_htc_form(encoded) else ""


def encode_recipe_line_htc(
    item: str,
    display: str,
    canonical_path: str,
    fallback_htc: str,
    cache: dict[tuple[str, str, str], str],
) -> str:
    item = (item or "").strip().lower()
    display = (display or "").strip()
    canonical_path = (canonical_path or "").strip()
    fallback_htc = (fallback_htc or "").strip().lstrip("~")
    if item and canonical_path:
        key = (item, display.lower(), canonical_path)
        if key not in cache:
            try:
                cache[key] = encode(
                    "",
                    description=display or item,
                    extra=item,
                    food_name=item,
                    canonical_path=canonical_path,
                    identity_mode=False,
                ).code
            except Exception:
                cache[key] = ""
        encoded = cache[key]
        if valid_htc_form(encoded):
            return encoded
    return fallback_htc


def choose_recipe_canonical_path(
    *,
    item: str,
    display: str,
    source_htc: str,
    title_path: str,
    item_overrides: dict[str, str],
    htc_to_path: dict[str, str],
    form_path_authority: dict[str, str],
    intent_cache: dict[tuple[str, str], str],
) -> str:
    item = (item or "").strip().lower()
    display = display or ""
    source_htc = (source_htc or "").strip().lstrip("~")
    title_path = (title_path or "").strip()

    line_override = line_canonical_path_override(item, display)
    if line_override:
        return line_override
    if item in item_overrides:
        return item_overrides[item]

    intent_htc = encode_recipe_intent_htc(item, display, intent_cache)
    intent_path = form_path_authority.get(intent_htc, "")
    if intent_path:
        return intent_path

    return (
        (title_path if specific_recipe_path(title_path) else "")
        or htc_to_path.get(source_htc, "")
        or title_path
    )
