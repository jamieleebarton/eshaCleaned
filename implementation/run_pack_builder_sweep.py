"""Offline sweep that runs every pack through the Nebius contract builder.

No LLM calls. For each pack in ``esha_code_query_pack_index.csv`` the script
parses the ``## Candidate Clean Products`` and ``## Rows To Clean Up`` tables
out of the MD file, synthesises a ``structured_contract`` data-driven from
those GTIN tables, and feeds it through ``nebius_contract_patch_builder``. The
per-pack status goes to a CSV so we can triage which families need Nebius
follow-up vs which land deterministically.

Phase 1 of the cleanup plan; phase 2 (branded-food-category walk) reads this
CSV and decides where to grow coverage by retail aisle.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
IMPL = ROOT / "implementation"
if str(IMPL) not in sys.path:
    sys.path.insert(0, str(IMPL))

from nebius_contract_patch_builder import (  # noqa: E402
    auto_relax_spec,
    evidence_products,
    extract_spec,
    validate_spec,
)

INDEX_CSV = IMPL / "output" / "esha_code_query_pack_index.csv"
OUT_CSV = IMPL / "output" / "pack_builder_sweep.csv"
OUT_SUMMARY = IMPL / "output" / "pack_builder_sweep_summary.md"
CATEGORY_EXCLUDES_JSON = IMPL / "output" / "category_excludes.json"

CANDIDATE_SECTION = "## Candidate Clean Products"
CLEANUP_SECTION = "## Rows To Clean Up"
CATEGORIES_SECTION = "## Categories Returned By Query"

STOP_DESCRIPTION_TOKENS = {
    "and", "or", "the", "with", "for", "of", "a", "an", "to",
    "in", "on", "by", "plus", "size",
}
STOP_INGREDIENT_TOKENS = STOP_DESCRIPTION_TOKENS | {
    "water", "salt", "natural", "flavor", "flavors", "flavoring",
    "citric", "acid", "preservative", "ascorbic",
}


PROMOTE_SIGNALS = {"review", "review_noise"}
FALLBACK_PROMOTE_SIGNALS = {"category_noise", "contract_reject", "semantic_filter_mismatch"}

# Exclude-token safety: short or known-noise tokens to never ship as excludes.
BAD_EXCLUDE_TOKENS = {"el", "compi", "mix", "bar", "nut", "oz", "fl", "lb", "pkg",
                      "and", "the", "for", "with", "of", "to", "in", "on",
                      "a", "an", "is", "it"}

# Opposite-attribute table: when an ESHA description contains the key token,
# auto-add the listed tokens as exclude_description_terms (unless they also
# appear in the pack's candidate descriptions, which would reject valid evidence).
OPPOSITE_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "whole": ("skim", "nonfat", "lowfat"),
    "skim": ("whole",),
    "nonfat": ("whole",),
    "lowfat": ("whole",),
    "chocolate": ("plain",),
    "vanilla": ("chocolate", "strawberry"),
    "strawberry": ("chocolate", "vanilla"),
    "evaporated": ("fresh", "fluid"),
    "condensed": ("fresh", "fluid"),
    "powdered": ("fluid", "fresh", "liquid"),
    "fluid": ("powdered", "dried", "condensed", "evaporated"),
    "dried": ("fresh", "fluid"),
    "fresh": ("frozen", "canned", "dried"),
    "frozen": ("fresh", "canned"),
    "canned": ("fresh", "frozen"),
    "raw": ("cooked", "baked", "fried", "roasted", "grilled", "steamed", "boiled"),
    "cooked": ("raw",),
    "baked": ("raw", "fried"),
    "fried": ("baked", "raw", "steamed", "boiled"),
    "sweetened": ("unsweetened",),
    "unsweetened": ("sweetened",),
    "regular": ("diet", "light"),
    "diet": ("regular",),
    "light": ("regular",),
    "organic": (),
    "original": ("flavored",),
}

# ESHA-description tokens that, when present, MUST be enforced in the contract
# (either required or excluded). Without this guard, the synthesis intersection
# silently drops the discriminator and contracts accept everything in-category.
HIGH_VALUE_ESHA_ATTRIBUTES = {
    # flavors / styles
    "chocolate", "vanilla", "strawberry", "raspberry", "blueberry", "banana",
    "cherry", "peach", "lemon", "lime", "orange", "mocha", "caramel", "mint",
    # state (removed ambiguous: whole, stick, bar, ground)
    "evaporated", "condensed", "sweetened", "unsweetened", "dried", "dehydrated",
    "powdered", "fluid", "instant", "shredded", "sliced",
    "diced", "chopped", "crushed", "puree", "pureed", "minced",
    # cooking
    "raw", "cooked", "baked", "boiled", "steamed", "grilled", "fried", "roasted",
    "smoked", "broiled", "toasted", "blanched",
    # preservation
    "frozen", "canned", "fresh", "refrigerated",
    # nutritional - fat-level discriminators added
    "fortified", "enriched", "organic", "nonfat", "lowfat", "skim", "reduced",
    "fat-free", "sugar-free", "low-sodium", "gluten-free", "dairy-free",
    "kosher", "vegan", "vegetarian",
    "percent", "1 percent", "2 percent", "fat free", "reduced fat",
    # cuts / variety (for meats / cheeses)
    "cheddar", "mozzarella", "swiss", "parmesan", "romano", "asiago", "feta",
    "brie", "gouda", "ricotta", "cottage", "provolone",
    "monterey", "colby",
    "shoulder", "loin", "rib", "shank", "breast", "thigh", "wing",
    "drumstick", "tenderloin", "flank",
    # category-specific identity
    "filling", "topping", "syrup", "concentrate", "powder",
    "shake", "smoothie", "frappuccino", "cappuccino", "latte", "espresso",
    "macchiato", "americano",
    "soda", "diet", "iced",
}


def parse_md_tables(text: str) -> dict[str, list[dict[str, str]]]:
    """Split the pack MD into candidate / cleanup tables.

    Cleanup rows whose ``signal`` is ``review`` or ``review_noise`` represent
    pack-builder uncertainty, not confirmed rejection. Promote them to
    candidates so the contract synthesizer can use them; the validator will
    still reject any that fail category / required-term checks.
    """
    sections: dict[str, list[dict[str, str]]] = {
        "candidate": [],
        "cleanup": [],
        "categories": [],
    }
    current: str | None = None
    header: list[str] | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            if line == CANDIDATE_SECTION:
                current = "candidate"
            elif line == CLEANUP_SECTION:
                current = "cleanup"
            elif line == CATEGORIES_SECTION:
                current = "categories"
            else:
                current = None
            header = None
            continue
        if current is None or not line.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= {"-", ":"} for c in cells if c):
            continue
        if header is None:
            header = [c.strip() for c in cells]
            continue
        if len(cells) != len(header):
            continue
        row = dict(zip(header, cells))
        if current == "cleanup" and row.get("signal", "") in PROMOTE_SIGNALS:
            sections["candidate"].append(row)
        else:
            sections[current].append(row)
    # Fallback: if no candidates at all, promote category_noise rows. These are
    # pack-builder category-mismatch flags, but for a pack with zero clean
    # candidates they're our only data; the validator will still reject any
    # that fail required-term / category checks against the synthesized spec.
    if not sections["candidate"]:
        promoted = [r for r in sections["cleanup"] if r.get("signal", "") in FALLBACK_PROMOTE_SIGNALS]
        if promoted:
            sections["candidate"].extend(promoted)
            sections["cleanup"] = [r for r in sections["cleanup"] if r not in promoted]
    return sections


def normalize_tokens(text: str, stop: set[str]) -> list[str]:
    from match_esha_to_products import tokens_for
    return [t for t in tokens_for(text or "") if t and t not in stop and not t.isdigit()]


def intersect_required(rows: list[dict[str, str]], field: str, stop: set[str]) -> list[str]:
    if not rows:
        return []
    token_sets: list[set[str]] = []
    for row in rows:
        tokens = set(normalize_tokens(row.get(field, ""), stop))
        token_sets.append(tokens)
    if not token_sets:
        return []
    common = set.intersection(*token_sets) if token_sets else set()
    return sorted(common)


def difference_exclude(
    cleanup_rows: list[dict[str, str]],
    candidate_rows: list[dict[str, str]],
    field: str,
    stop: set[str],
) -> list[str]:
    if not cleanup_rows:
        return []
    candidate_tokens: set[str] = set()
    for row in candidate_rows:
        candidate_tokens |= set(normalize_tokens(row.get(field, ""), stop))
    cleanup_counter: Counter[str] = Counter()
    for row in cleanup_rows:
        cleanup_counter.update(set(normalize_tokens(row.get(field, ""), stop)))
    threshold = max(2, len(cleanup_rows) // 3)
    out = [tok for tok, count in cleanup_counter.items() if count >= threshold and tok not in candidate_tokens]
    return sorted(out)


def candidate_categories(rows: Iterable[dict[str, str]]) -> list[str]:
    """Return allowed_categories, requiring each to be supported by enough candidates.

    Prevents a single rogue promoted-from-cleanup product in a wrong category from
    contaminating allowed_categories (e.g., one sponge-cake-like product in a milk
    pack adding "Cakes, Cupcakes, Snack Cakes" to the milk contract's allowed list,
    which then lets cake products leak back in at inference time).
    """
    counts: dict[str, int] = {}
    total = 0
    for row in rows:
        cat = (row.get("category") or "").strip().lower()
        if cat:
            counts[cat] = counts.get(cat, 0) + 1
            total += 1
    if not counts:
        return []
    if total <= 3:
        min_count = 1
    elif total <= 10:
        min_count = 2
    else:
        min_count = max(2, total // 10)
    kept = [cat for cat, n in counts.items() if n >= min_count]
    # Preserve first-seen order for stability
    ordered: list[str] = []
    seen: set[str] = set()
    for row in rows:
        cat = (row.get("category") or "").strip().lower()
        if cat and cat in kept and cat not in seen:
            seen.add(cat)
            ordered.append(cat)
    return ordered


_CATEGORY_EXCLUDES_CACHE: dict[str, dict[str, list[str]]] | None = None


def load_category_excludes() -> dict[str, dict[str, list[str]]]:
    global _CATEGORY_EXCLUDES_CACHE
    if _CATEGORY_EXCLUDES_CACHE is not None:
        return _CATEGORY_EXCLUDES_CACHE
    import json
    if not CATEGORY_EXCLUDES_JSON.exists():
        _CATEGORY_EXCLUDES_CACHE = {}
        return _CATEGORY_EXCLUDES_CACHE
    raw = json.loads(CATEGORY_EXCLUDES_JSON.read_text(encoding="utf-8"))
    _CATEGORY_EXCLUDES_CACHE = {
        cat: {
            "description_excludes": list(entry.get("description_excludes") or []),
            "ingredient_excludes": list(entry.get("ingredient_excludes") or []),
        }
        for cat, entry in raw.items()
    }
    return _CATEGORY_EXCLUDES_CACHE


def merge_category_excludes(
    spec: dict[str, Any],
    tables: dict[str, list[dict[str, str]]],
    top_category: str,
) -> None:
    lookup = load_category_excludes().get(top_category)
    if not lookup:
        return
    cleanup_desc: set[str] = set()
    cleanup_ing: set[str] = set()
    candidate_desc: set[str] = set()
    candidate_ing: set[str] = set()
    for row in tables["cleanup"]:
        cleanup_desc |= set(normalize_tokens(row.get("description", ""), STOP_DESCRIPTION_TOKENS))
        cleanup_ing |= set(normalize_tokens(row.get("ingredients", ""), STOP_INGREDIENT_TOKENS))
    for row in tables["candidate"]:
        candidate_desc |= set(normalize_tokens(row.get("description", ""), STOP_DESCRIPTION_TOKENS))
        candidate_ing |= set(normalize_tokens(row.get("ingredients", ""), STOP_INGREDIENT_TOKENS))

    existing_desc = set(spec["exclude_description_terms"])
    for tok in lookup["description_excludes"]:
        if tok in candidate_desc or tok in existing_desc:
            continue
        if tok in cleanup_desc:
            spec["exclude_description_terms"].append(tok)
            existing_desc.add(tok)
    existing_ing = set(spec["exclude_ingredient_terms"])
    for tok in lookup["ingredient_excludes"]:
        if tok in candidate_ing or tok in existing_ing:
            continue
        if tok in cleanup_ing:
            spec["exclude_ingredient_terms"].append(tok)
            existing_ing.add(tok)


def synth_contract(
    esha_code: str,
    description: str,
    tables: dict[str, list[dict[str, str]]],
    top_category: str = "",
) -> dict[str, Any]:
    candidates = tables["candidate"]
    cleanups = tables["cleanup"]
    allowed = candidate_categories(candidates)
    allowed_set = set(allowed)
    # Prune candidates whose category wasn't kept (outliers dropped above).
    kept_candidates = [
        r for r in candidates
        if not allowed_set or (r.get("category") or "").strip().lower() in allowed_set
    ]
    spec = {
        "esha_code": esha_code,
        "esha_description": description,
        "allowed_categories": allowed,
        "required_description_terms": intersect_required(kept_candidates, "description", STOP_DESCRIPTION_TOKENS),
        "exclude_description_terms": difference_exclude(cleanups, kept_candidates, "description", STOP_DESCRIPTION_TOKENS),
        "required_ingredient_terms": intersect_required(kept_candidates, "ingredients", STOP_INGREDIENT_TOKENS),
        "exclude_ingredient_terms": difference_exclude(cleanups, kept_candidates, "ingredients", STOP_INGREDIENT_TOKENS),
        "accepted_gtins": [r.get("gtin_upc", "") for r in kept_candidates if r.get("gtin_upc")],
        "rejected_gtins": [r.get("gtin_upc", "") for r in cleanups if r.get("gtin_upc")],
    }
    if top_category:
        merge_category_excludes(spec, tables, top_category)
    return spec


def synth_packet(tables: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in (*tables["candidate"], *tables["cleanup"]):
        rows.append({
            "gtin_upc": row.get("gtin_upc", ""),
            "description": row.get("description", ""),
            "category": row.get("category", ""),
            "ingredients": row.get("ingredients", ""),
        })
    return {"product_search": {"rows": rows}}


SIGNAL_FILTER_MIN_CANDIDATES_WITHOUT_GATE = 4
SIGNAL_FILTER_MAX_DROPS_WHEN_THIN = 8
SIGNAL_FILTER_ABSOLUTE_DROP_CEILING = 20


def signal_filter_is_safe(candidate_count: int, dropped_count: int) -> bool:
    """Guard phase-3 loosening against bad candidate sets.

    Packs whose upstream retrieval produced garbage candidates (e.g. jelly beans
    returned for chocolate mint pudding) trigger massive ESHA-signal drops and
    end up with near-empty required terms. Three-condition gate:

    - Hard ceiling: never accept a drop of >20 tokens (legit loosening rarely
      strips that many; something is structurally wrong with the candidates).
    - Small-drop path: if the drop is 8 or fewer tokens, accept regardless of
      candidate count (small trims are low-risk even with one candidate).
    - Thick-evidence path: if we have >=4 candidates, accept drops up to the
      ceiling (the intersection was grounded across multiple products).
    """
    if dropped_count > SIGNAL_FILTER_ABSOLUTE_DROP_CEILING:
        return False
    if dropped_count <= SIGNAL_FILTER_MAX_DROPS_WHEN_THIN:
        return True
    return candidate_count >= SIGNAL_FILTER_MIN_CANDIDATES_WITHOUT_GATE


def scrub_garbage_excludes(spec: dict[str, Any]) -> None:
    """Remove non-semantic or too-generic tokens from exclude lists."""
    def keep(tok: str) -> bool:
        t = (tok or "").strip()
        if not t or len(t) < 3:
            return False
        if t in BAD_EXCLUDE_TOKENS:
            return False
        if t.replace(".", "", 1).isdigit():
            return False
        return True
    spec["exclude_description_terms"] = [t for t in (spec.get("exclude_description_terms") or []) if keep(t)]
    spec["exclude_ingredient_terms"] = [t for t in (spec.get("exclude_ingredient_terms") or []) if keep(t)]


def apply_opposite_excludes(
    spec: dict[str, Any],
    esha_description: str,
    tables: dict[str, list[dict[str, str]]],
) -> list[str]:
    """Add opposite-attribute excludes when the ESHA description has a side.

    Safety: skip any opposite token that appears in candidate descriptions (to
    avoid rejecting the pack's own accepted evidence).
    """
    desc_tokens = set(normalize_tokens(esha_description, STOP_DESCRIPTION_TOKENS))
    candidate_tokens: set[str] = set()
    for crow in tables["candidate"]:
        candidate_tokens |= set(normalize_tokens(crow.get("description", ""), STOP_DESCRIPTION_TOKENS))
    existing = set(spec.get("exclude_description_terms") or [])
    added: list[str] = []
    for side, opposites in OPPOSITE_ATTRIBUTES.items():
        if side not in desc_tokens:
            continue
        for opp in opposites:
            if opp in existing or opp in candidate_tokens or opp in desc_tokens:
                continue
            spec["exclude_description_terms"].append(opp)
            existing.add(opp)
            added.append(opp)
    return added


def enforce_esha_attributes(spec: dict[str, Any], esha_description: str, tables: dict[str, list[dict[str, str]]]) -> dict[str, list[str]]:
    """Force ESHA-description discriminating attributes into the contract.

    For each HIGH_VALUE attribute in the ESHA description that's not already
    enforced: if some candidate has it (in description or ingredients), add it
    as required (description-side preferred, falls back to ingredient-side).
    If zero candidates have it, the contract is built on wrong evidence and
    gets emptied (will be caught downstream as no_identity).

    Returns a dict of {action: [tokens]} for reporting.
    """
    desc_tokens = set(normalize_tokens(esha_description, STOP_DESCRIPTION_TOKENS))
    needed = desc_tokens & HIGH_VALUE_ESHA_ATTRIBUTES
    if not needed:
        return {"added_desc": [], "added_ing": [], "dropped_for": []}
    enforced = (
        set(spec.get("required_description_terms") or [])
        | set(spec.get("required_ingredient_terms") or [])
        | set(spec.get("exclude_description_terms") or [])
        | set(spec.get("exclude_ingredient_terms") or [])
    )
    missing = sorted(needed - enforced)
    added_desc, added_ing, dropped_for = [], [], []
    for tok in missing:
        n_desc = 0
        n_ing = 0
        for crow in tables["candidate"]:
            cd = set(normalize_tokens(crow.get("description", ""), STOP_DESCRIPTION_TOKENS))
            ci = set(normalize_tokens(crow.get("ingredients", ""), STOP_INGREDIENT_TOKENS))
            if tok in cd: n_desc += 1
            if tok in ci: n_ing += 1
        if n_desc == 0 and n_ing == 0:
            spec["required_description_terms"] = []
            spec["required_ingredient_terms"] = []
            dropped_for.append(tok)
            return {"added_desc": added_desc, "added_ing": added_ing, "dropped_for": dropped_for}
        if n_desc >= n_ing:
            spec["required_description_terms"].append(tok)
            added_desc.append(tok)
        else:
            spec["required_ingredient_terms"].append(tok)
            added_ing.append(tok)
    # When we forced new requirements, prune accepted_gtins to those that satisfy them.
    if added_desc or added_ing:
        gtin_to_row = {c.get("gtin_upc", ""): c for c in tables["candidate"] if c.get("gtin_upc")}
        kept = []
        for gtin in spec.get("accepted_gtins") or []:
            row = gtin_to_row.get(gtin)
            if row is None:
                kept.append(gtin)
                continue
            cd = set(normalize_tokens(row.get("description", ""), STOP_DESCRIPTION_TOKENS))
            ci = set(normalize_tokens(row.get("ingredients", ""), STOP_INGREDIENT_TOKENS))
            ok = all(t in cd for t in added_desc) and all(t in ci for t in added_ing)
            if ok:
                kept.append(gtin)
        spec["accepted_gtins"] = kept
    return {"added_desc": added_desc, "added_ing": added_ing, "dropped_for": dropped_for}


def esha_signal_filter(spec: dict[str, Any], esha_description: str) -> list[dict[str, str]]:
    """Drop required terms that aren't in the ESHA description's signal tokens.

    Overfit contracts from thin-candidate packs keep every token from the single
    candidate as required — including incidental descriptors like "sliced" that
    aren't part of the ESHA concept. Filtering to tokens also present in the
    ESHA description preserves concept identity while dropping pack-specific
    noise. Applied after auto_relax, and only kept if the loosened spec still
    passes validation against the pack's own evidence.
    """
    signal_desc = set(normalize_tokens(esha_description, STOP_DESCRIPTION_TOKENS))
    signal_ing = set(normalize_tokens(esha_description, STOP_INGREDIENT_TOKENS))
    dropped: list[dict[str, str]] = []
    kept_desc = []
    for tok in spec["required_description_terms"]:
        if tok in signal_desc:
            kept_desc.append(tok)
        else:
            dropped.append({"field": "required_description_terms", "value": tok})
    kept_ing = []
    for tok in spec["required_ingredient_terms"]:
        if tok in signal_ing:
            kept_ing.append(tok)
        else:
            dropped.append({"field": "required_ingredient_terms", "value": tok})
    spec["required_description_terms"] = kept_desc
    spec["required_ingredient_terms"] = kept_ing
    return dropped


def which_field_failed(failure: dict[str, str]) -> str:
    expected = failure.get("expected") or ""
    actual = failure.get("actual") or ""
    reason = str(failure.get("reason") or "")
    if expected == "reject" and actual == "accept":
        return "excludes_too_loose"
    if "category mismatch" in reason:
        return "allowed_categories"
    if "required term" in reason:
        return "required_description_terms"
    if "required phrase" in reason:
        return "required_description_phrases"
    if "required ingredient term" in reason:
        return "required_ingredient_terms"
    if "required ingredient phrase" in reason:
        return "required_ingredient_phrases"
    if "excluded term" in reason:
        return "exclude_description_terms"
    if "excluded phrase" in reason:
        return "exclude_description_phrases"
    if "excluded ingredient" in reason:
        return "exclude_ingredient_terms"
    return "unknown"


def failure_mode(failures: list[dict[str, str]]) -> str:
    if not failures:
        return ""
    too_loose = sum(1 for f in failures if f.get("expected") == "reject" and f.get("actual") == "accept")
    too_tight = sum(1 for f in failures if f.get("expected") == "accept" and f.get("actual") == "reject")
    if too_loose and not too_tight:
        return "excludes_too_loose"
    if too_tight and not too_loose:
        return "required_too_tight"
    if too_loose and too_tight:
        return "mixed"
    return "other"


def classify_pack(index_row: dict[str, str]) -> dict[str, Any]:
    pack_path = Path(index_row["pack_path"])
    esha_code = index_row["esha_code"]
    description = index_row.get("description") or ""
    family = index_row.get("family") or ""
    top_category = index_row.get("top_category") or ""
    base = {
        "esha_code": esha_code,
        "description": description,
        "family": family,
        "top_category": top_category,
        "candidate_count": 0,
        "cleanup_count": 0,
        "auto_relaxed_count": 0,
        "which_field_did_the_work": "",
        "failing_gtins": "",
        "failure_mode": "",
        "status": "error",
        "reason": "",
    }
    if not pack_path.exists():
        base["reason"] = "pack_file_missing"
        return base
    try:
        text = pack_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        base["reason"] = f"read_error:{type(exc).__name__}"
        return base
    tables = parse_md_tables(text)
    base["candidate_count"] = len(tables["candidate"])
    base["cleanup_count"] = len(tables["cleanup"])
    if not tables["candidate"]:
        base["status"] = "no_candidates"
        base["reason"] = "pack has zero Candidate Clean Products"
        return base

    spec = synth_contract(esha_code, description, tables, top_category=top_category)
    packet = synth_packet(tables)
    final = {"decision": "tighten_current_contract", "structured_contract": spec}

    if not spec["allowed_categories"]:
        base["status"] = "no_identity"
        base["reason"] = "synthesis produced no allowed_categories"
        return base
    has_required = any(spec[f] for f in ("required_description_terms", "required_ingredient_terms"))
    has_excludes = any(spec[f] for f in ("exclude_description_terms", "exclude_ingredient_terms"))
    if not has_required and not has_excludes:
        base["status"] = "no_identity"
        base["reason"] = "synthesis produced no required terms and no excludes"
        return base

    try:
        extracted = extract_spec(packet, final)
    except ValueError as exc:
        base["status"] = "no_identity"
        base["reason"] = f"builder_raised:{exc}"
        return base
    except Exception as exc:
        base["reason"] = f"builder_exception:{type(exc).__name__}:{exc}"
        return base

    auto_relaxed = auto_relax_spec(packet, extracted)
    enforce_result = enforce_esha_attributes(extracted, description, tables)
    if enforce_result["dropped_for"]:
        base["status"] = "no_identity"
        base["reason"] = f"esha_attribute_unsupported_by_candidates:{','.join(enforce_result['dropped_for'])}"
        return base
    apply_opposite_excludes(extracted, description, tables)
    scrub_garbage_excludes(extracted)
    has_required = any(
        extracted[field]
        for field in (
            "required_description_terms",
            "required_description_phrases",
            "required_description_any_terms",
            "required_ingredient_terms",
            "required_ingredient_phrases",
            "required_ingredient_any_terms",
        )
    )
    has_excludes_after_relax = any(
        extracted[field]
        for field in (
            "exclude_description_terms",
            "exclude_description_phrases",
            "exclude_ingredient_terms",
            "exclude_ingredient_phrases",
        )
    )
    base["auto_relaxed_count"] = len(auto_relaxed)
    if not has_required and not has_excludes_after_relax:
        base["status"] = "no_identity"
        base["reason"] = "all required terms pruned and no excludes available"
        return base

    validation = validate_spec(packet, extracted)
    if validation["ok"]:
        base["status"] = "patch_built"
        base["reason"] = "patch_built"
        # Phase-3: try loosening via ESHA-signal filter; only keep if still valid
        saved_desc = list(extracted["required_description_terms"])
        saved_ing = list(extracted["required_ingredient_terms"])
        dropped = esha_signal_filter(extracted, description)
        loosened_identity = any(
            extracted[field]
            for field in (
                "required_description_terms",
                "required_description_phrases",
                "required_description_any_terms",
                "required_ingredient_terms",
                "required_ingredient_phrases",
                "required_ingredient_any_terms",
            )
        )
        if loosened_identity and dropped and signal_filter_is_safe(len(tables["candidate"]), len(dropped)):
            reval = validate_spec(packet, extracted)
            if reval["ok"]:
                base["reason"] = f"patch_built_signal_filtered_dropped_{len(dropped)}"
                base["auto_relaxed_count"] += len(dropped)
            else:
                extracted["required_description_terms"] = saved_desc
                extracted["required_ingredient_terms"] = saved_ing
        else:
            extracted["required_description_terms"] = saved_desc
            extracted["required_ingredient_terms"] = saved_ing
        return base

    failures = validation.get("failures") or []
    # Per-pack rescue for excludes_too_loose: tighten by adding distinctive tokens
    # from leaked GTINs that aren't in the pack's own candidates.
    too_loose = [f for f in failures if f.get("expected") == "reject" and f.get("actual") == "accept"]
    too_tight = [f for f in failures if f.get("expected") == "accept" and f.get("actual") == "reject"]
    if too_loose and not too_tight:
        leak_gtins = {f.get("gtin_upc", "") for f in too_loose}
        cand_desc_tokens: set[str] = set()
        cand_ing_tokens: set[str] = set()
        for crow in tables["candidate"]:
            cand_desc_tokens |= set(normalize_tokens(crow.get("description", ""), STOP_DESCRIPTION_TOKENS))
            cand_ing_tokens |= set(normalize_tokens(crow.get("ingredients", ""), STOP_INGREDIENT_TOKENS))
        leak_desc_counts: Counter[str] = Counter()
        leak_ing_counts: Counter[str] = Counter()
        for crow in tables["cleanup"]:
            if crow.get("gtin_upc", "") not in leak_gtins:
                continue
            leak_desc_counts.update(set(normalize_tokens(crow.get("description", ""), STOP_DESCRIPTION_TOKENS)))
            leak_ing_counts.update(set(normalize_tokens(crow.get("ingredients", ""), STOP_INGREDIENT_TOKENS)))
        leak_count = max(len(leak_gtins), 1)
        threshold = 1
        existing_desc_excl = set(extracted["exclude_description_terms"])
        existing_ing_excl = set(extracted["exclude_ingredient_terms"])
        added_desc, added_ing = [], []
        for tok, n in leak_desc_counts.most_common():
            if n < threshold or tok in cand_desc_tokens or tok in existing_desc_excl:
                continue
            extracted["exclude_description_terms"].append(tok)
            existing_desc_excl.add(tok)
            added_desc.append(tok)
        for tok, n in leak_ing_counts.most_common():
            if n < threshold or tok in cand_ing_tokens or tok in existing_ing_excl:
                continue
            extracted["exclude_ingredient_terms"].append(tok)
            existing_ing_excl.add(tok)
            added_ing.append(tok)
        if added_desc or added_ing:
            reval = validate_spec(packet, extracted)
            if reval["ok"]:
                base["status"] = "patch_built"
                base["reason"] = f"patch_built_pack_excludes_added_{len(added_desc)}desc_{len(added_ing)}ing"
                return base
            # roll back if rescue did not validate
            for tok in added_desc:
                if tok in extracted["exclude_description_terms"]:
                    extracted["exclude_description_terms"].remove(tok)
            for tok in added_ing:
                if tok in extracted["exclude_ingredient_terms"]:
                    extracted["exclude_ingredient_terms"].remove(tok)

    base["status"] = "semantic_validation_failed"
    fields = Counter(which_field_failed(f) for f in failures)
    base["which_field_did_the_work"] = ",".join(sorted(fields))
    base["failure_mode"] = failure_mode(failures)
    base["failing_gtins"] = ",".join(f.get("gtin_upc", "") for f in failures if f.get("gtin_upc"))
    base["reason"] = failures[0].get("reason", "") if failures else "validation_failed_without_specific_failure"
    return base


def run_sweep(limit: int | None, out_csv: Path, out_summary: Path) -> None:
    with INDEX_CSV.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if limit:
        rows = rows[:limit]

    fieldnames = [
        "esha_code", "description", "family", "top_category",
        "candidate_count", "cleanup_count", "status", "failure_mode", "reason",
        "auto_relaxed_count", "which_field_did_the_work", "failing_gtins",
    ]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    status_counter: Counter[str] = Counter()
    family_status: Counter[tuple[str, str]] = Counter()
    retail_status: Counter[tuple[str, str]] = Counter()
    start = time.time()

    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for idx, row in enumerate(rows, start=1):
            record = classify_pack(row)
            writer.writerow(record)
            status_counter[record["status"]] += 1
            family_status[(row.get("family") or "", record["status"])] += 1
            retail_status[(row.get("top_category") or "", record["status"])] += 1
            if idx % 1000 == 0:
                elapsed = time.time() - start
                print(f"  {idx}/{len(rows)} processed in {elapsed:.1f}s", file=sys.stderr)

    elapsed = time.time() - start

    def rel(p: Path) -> str:
        try:
            return str(p.relative_to(ROOT))
        except ValueError:
            return str(p)

    lines: list[str] = [
        "# Pack builder sweep summary",
        "",
        f"- packs processed: {len(rows)}",
        f"- runtime: {elapsed:.1f}s",
        f"- output CSV: {rel(out_csv)}",
        "",
        "## Status counts",
        "",
        "| status | count |",
        "| --- | ---: |",
    ]
    for status, count in status_counter.most_common():
        lines.append(f"| {status} | {count} |")
    lines.extend(["", "## Status by ESHA family", "", "| family | status | count |", "| --- | --- | ---: |"])
    for (family, status), count in sorted(family_status.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {family or '(none)'} | {status} | {count} |")
    lines.extend(["", "## Status by branded food category (top 40)", "", "| branded_food_category | status | count |", "| --- | --- | ---: |"])
    for (category, status), count in sorted(retail_status.items(), key=lambda kv: -kv[1])[:40]:
        lines.append(f"| {category or '(none)'} | {status} | {count} |")
    out_summary.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nwrote {rel(out_csv)}  summary: {rel(out_summary)}")
    print(f"status counts: {dict(status_counter)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline sweep of all ESHA packs through the contract builder")
    parser.add_argument("--limit", type=int, help="Only process first N packs (useful for smoke tests)")
    parser.add_argument("--out-csv", type=Path, default=OUT_CSV)
    parser.add_argument("--out-summary", type=Path, default=OUT_SUMMARY)
    args = parser.parse_args()
    run_sweep(args.limit, args.out_csv, args.out_summary)


if __name__ == "__main__":
    main()
