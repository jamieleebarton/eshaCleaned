#!/usr/bin/env python3
"""End-to-end cleanup of the DeepSeek 145k run.

Pipeline:

    1. Load LLM JSONL output (one record per fdc_id).
    2. Load input CSV (title + source/_corpus per fdc_id).
    3. Load canonical-path universe from consensus_full_corpus_audit.csv
       (10,416 paths — the source of truth).
    4. Apply title-pattern overrides FIRST (curated rules for known LLM
       mistakes — salad kits, infant formula, single-spice "Spice Blend",
       powdered milk, etc.).
    5. For rows not overridden, normalize the LLM's canonical_path onto the
       universe:
           a. exact match (after singular/lowercase normalize)
           b. token-set fuzzy match
           c. embed-kNN against the cached tree_emb (residual)
       Anything that doesn't match at >=0.85 cosine flags for review.
    6. Derive HTC parts from the normalized path:
           group  = group_from_canonical_path(canonical_path, label)
           family = family_from_identity(group, text, path, food_name=label)
           food   = food_slot_registry.lookup(group, family, effective_name)
       New foods that don't exist in the registry are appended (deterministic
       batch update).
    7. Emit final per-corpus tagged CSVs:
           recipe_pricing/output/api_cache_htc_tagged.csv
           recipe_mapper/v1/output/recipe_ingredient_htc_tagged.csv
       Each row has the same shape as the existing files: htc_code,
       htc_group, htc_family, htc_food, htc_form, htc_processing, htc_ptype,
       htc_check, htc_confidence, htc_source.
    8. Write a review queue (cleanup_review_queue.csv) of rows whose path
       didn't match anything and whose embed-kNN was below threshold.

Usage:
    python3 recipe_pricing/cleanup_llm_output.py
        --jsonl recipe_pricing/data/full_llm_run.live.jsonl
        --input recipe_pricing/data/full_llm_input.csv
        --overrides recipe_pricing/walmart_kroger_overrides.csv  # optional
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "recipe_mapper" / "v1"
V2 = ROOT / "retail_mapper" / "v2"

sys.path.insert(0, str(V1))
sys.path.insert(0, str(V2))
from htc.encoder import (  # noqa: E402
    code_from_parts,
    family_from_identity,
    group_from_canonical_path,
)
try:
    from product_identity_canonical_map import PRODUCT_IDENTITY_CANONICAL_PATH_MAP  # noqa: E402
except ImportError:
    PRODUCT_IDENTITY_CANONICAL_PATH_MAP = {}
from htc.full_code import compose_full_code  # noqa: E402

# Tolerant lookup index: case-insensitive + singular/plural variants share a key.
# Built lazily on first use to avoid touching module load order.
_PID_LOOKUP_CACHE: dict[str, str] | None = None

# Title-token → set of (canonical_path, depth) for specific FDC identities.
# Lets us deepen a shallow canonical_path (Dairy > Cheese) when the title
# contains a token like "havarti" that maps to a specific FDC sub-leaf
# (Dairy > Cheese > Havarti), provided the deeper path is a strict descendant.
_DEEP_IDENTITY_INDEX: dict[str, list[tuple[str, str, int]]] | None = None


def _build_deep_identity_index() -> dict[str, list[tuple[str, str, int]]]:
    """token -> [(specific_identity, canonical_path, depth), ...] sorted by depth desc."""
    out: defaultdict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for pid, path in PRODUCT_IDENTITY_CANONICAL_PATH_MAP.items():
        depth = path.count(" > ") + 1
        if depth < 3:
            continue
        # Tokenize the identity name; require all-token-match for specificity
        ident_tokens = [t.strip().lower() for t in re.split(r"[\s_/\-]+", pid) if t.strip()]
        if not ident_tokens:
            continue
        # Index under the FIRST distinctive token (cheddar/havarti/mozzarella).
        # Multi-word identities (Cinnamon Swirl Bread) get matched only when
        # all their tokens are present in the title — see resolve_deep_identity.
        for tok in ident_tokens:
            if len(tok) < 3:  # skip "ap", "or"
                continue
            out[tok].append((pid, path, depth))
    # Sort each token's hits by depth desc so deepest wins
    for tok in out:
        out[tok].sort(key=lambda x: -x[2])
    return out


def resolve_deep_identity(title: str, current_path: str) -> str | None:
    """If the title contains tokens for a more specific FDC identity that's a
    strict descendant of `current_path`, return that deeper canonical_path.
    Otherwise None. Word-boundary matching only — "creamy" does NOT match "cream".
    """
    global _DEEP_IDENTITY_INDEX
    if _DEEP_IDENTITY_INDEX is None:
        _DEEP_IDENTITY_INDEX = _build_deep_identity_index()
    if not title or not current_path:
        return None
    title_tokens = {t.strip().lower() for t in re.split(r"[\s_/\-,()&]+", title) if t.strip()}

    best_path: str | None = None
    best_depth = current_path.count(" > ") + 1
    for tok in title_tokens:
        for ident, path, depth in _DEEP_IDENTITY_INDEX.get(tok, []):
            if depth <= best_depth:
                continue
            if not path.startswith(current_path + " > "):
                continue
            # ALL identity tokens (≥ 3 chars) must appear as whole words in the title
            ident_tokens = [it for it in re.split(r"[\s_/\-]+", ident.lower()) if len(it) >= 3]
            if not all(it in title_tokens for it in ident_tokens):
                continue
            best_path = path
            best_depth = depth
    return best_path


def _build_pid_lookup() -> dict[str, str]:
    out: dict[str, str] = {}
    for pid, path in PRODUCT_IDENTITY_CANONICAL_PATH_MAP.items():
        for key in _pid_variants(pid):
            out.setdefault(key, path)
    return out


def _pid_variants(pid: str) -> list[str]:
    """Lowercase + simple plural / singular flips."""
    p = pid.strip().lower()
    if not p:
        return []
    variants = {p}
    if p.endswith("ies") and len(p) > 3:
        variants.add(p[:-3] + "y")
    elif p.endswith("es") and len(p) > 2:
        variants.add(p[:-2])
        variants.add(p[:-1])
    elif p.endswith("s") and len(p) > 1:
        variants.add(p[:-1])
    else:
        variants.add(p + "s")
        variants.add(p + "es")
    return list(variants)


def lookup_identity_path(pid: str) -> str | None:
    global _PID_LOOKUP_CACHE
    if _PID_LOOKUP_CACHE is None:
        _PID_LOOKUP_CACHE = _build_pid_lookup()
    if not pid:
        return None
    for key in _pid_variants(pid):
        hit = _PID_LOOKUP_CACHE.get(key)
        if hit:
            return hit
    return None
from htc.food_slots import (  # noqa: E402
    CROCKFORD,
    RESERVED_SLOT,
    default_registry,
    effective_food_name,
    is_rule_b,
    normalize_key,
    primary_modifier,
)

DEFAULT_JSONL = ROOT / "recipe_pricing" / "data" / "full_llm_run.live.jsonl"
DEFAULT_INPUT = ROOT / "recipe_pricing" / "data" / "full_llm_input.csv"
DEFAULT_AUDIT = V2 / "consensus_full_corpus_audit.csv"
DEFAULT_OVERRIDES = ROOT / "recipe_pricing" / "walmart_kroger_overrides.csv"
DEFAULT_PATH_REWRITES = ROOT / "recipe_pricing" / "walmart_kroger_path_rewrites.csv"
DEFAULT_EXPAND_REWRITES = ROOT / "recipe_pricing" / "expand_fdc_rewrites.csv"
DEFAULT_REVIEW = ROOT / "recipe_pricing" / "output" / "cleanup_review_queue.csv"

# Final-stage catch-all: any row whose final canonical_path can't be made FDC-valid
# even after parent-strip retry routes here. The Non-Food > Other anchor is added
# to FDC by retail_mapper/v2/append_synthetic_anchors.py.
NON_FOOD_OTHER = "Non-Food > Other"

# Excel-safe prefix for htc_code/htc_sku_code so values like "100E0000" don't
# get auto-rendered as scientific notation when opened in Excel.
HTC_CODE_PREFIX = "~"
# Distinct output paths so we don't overwrite the legacy regex-encoder
# outputs (api_cache_htc_tagged.csv / recipe_ingredient_htc_tagged.csv).
# The legacy pipeline coexists until we cut over downstream readers.
DEFAULT_API_OUT = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
DEFAULT_ING_OUT = V1 / "output" / "recipe_ingredient_taxonomy_v2.csv"
DEFAULT_SUMMARY = ROOT / "recipe_pricing" / "output" / "cleanup_summary.json"


def load_input(path: Path) -> dict[str, dict]:
    """fdc_id -> input row (title, source, _corpus, etc.)."""
    out: dict[str, dict] = {}
    with path.open() as f:
        for row in csv.DictReader(f):
            out[row["fdc_id"]] = row
    return out


def load_llm_records(path: Path) -> dict[str, dict]:
    """fdc_id -> parsed LLM record (canonical_path, label, facets, ...)."""
    out: dict[str, dict] = {}
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            fid = d.get("fdc_id") or d.get("custom_id") or ""
            rec = d.get("record") or {}
            if isinstance(rec, dict):
                out[fid] = rec
    return out


# Words that aren't identity carriers — drop from token sets so input
# {greek, plain, honey, vanilla} matches FDC {greek, honey, vanilla}.
_RETAIL_LEAF_DROP_TOKENS = {
    "plain", "regular", "default", "the", "a", "an", "of", "and", "with",
    "in", "on", "for", "or", "to", "&",
}


def _normalize_facet_tokens(*facet_blobs: str) -> frozenset[str]:
    """Tokenize and normalize a row's modifier facets into a comparable set."""
    out: set[str] = set()
    for blob in facet_blobs:
        if not blob:
            continue
        # Pipe-separated lists or space-separated
        for piece in re.split(r"[|,]", str(blob)):
            for tok in re.split(r"[\s_/\-]+", piece.strip()):
                tok = tok.strip().lower()
                if tok and tok not in _RETAIL_LEAF_DROP_TOKENS:
                    out.add(tok)
    return frozenset(out)


def _path_suffix_tokens(canonical_path: str, retail_leaf_path: str) -> frozenset[str]:
    """Tokens of retail_leaf_path that come AFTER the canonical_path prefix."""
    rlp = retail_leaf_path.strip()
    cp = canonical_path.strip()
    if cp and rlp.startswith(cp):
        suffix = rlp[len(cp):].lstrip(" >")
    else:
        suffix = rlp
    if not suffix:
        return frozenset()
    out: set[str] = set()
    for tok in re.split(r"[\s>_/\-]+", suffix):
        tok = tok.strip().lower()
        if tok and tok not in _RETAIL_LEAF_DROP_TOKENS:
            out.add(tok)
    return frozenset(out)


def load_retail_leaf_index(audit_path: Path) -> dict[str, list[tuple[str, frozenset[str]]]]:
    """canonical_path -> [(retail_leaf_path, suffix_token_set), ...].

    Each FDC retail_leaf_path becomes a candidate keyed by its parent
    canonical_path. Lookups score by token-set agreement on the SUFFIX
    (the modifier-segments past the canonical_path prefix).
    """
    by_cp: defaultdict[str, dict[str, frozenset[str]]] = defaultdict(dict)
    with audit_path.open() as f:
        for row in csv.DictReader(f):
            cp = (row.get("canonical_path") or "").strip()
            rlp = (row.get("retail_leaf_path") or "").strip()
            if not cp or not rlp:
                continue
            if rlp not in by_cp[cp]:
                by_cp[cp][rlp] = _path_suffix_tokens(cp, rlp)
    out: dict[str, list[tuple[str, frozenset[str]]]] = {}
    for cp, rlps in by_cp.items():
        out[cp] = list(rlps.items())
    return out


def _title_case(token: str) -> str:
    """Token → Title Case for synthesis (greek_style → Greek Style)."""
    parts = re.split(r"[\s_/\-]+", token)
    return " ".join(p.capitalize() for p in parts if p)


def compose_retail_leaf_path(
    canonical_path: str,
    facet_tokens: frozenset[str],
    leaf_index: dict[str, list[tuple[str, frozenset[str]]]],
) -> tuple[str, str]:
    """Pick the FDC retail_leaf_path whose suffix tokens best match the row's
    facet tokens, scoped to the same canonical_path.

    NEVER synthesizes a fake retail_leaf_path. When no FDC retail leaf matches,
    falls back to canonical_path (which is itself a real FDC path). This rule
    is non-negotiable — the planner must trust that every retail_leaf_path is
    a real retail location with real Walmart/Kroger products at it (or its
    ancestors). The variant_hash in htc_full_code captures per-row identity for
    cross-corpus joins; retail_leaf_path doesn't need to be unique-per-row.

    Returns (retail_leaf_path, source) where source ∈ {fdc_exact, fdc_subset,
    fdc_superset, fdc_jaccard, canonical_only}.
    """
    if not facet_tokens:
        return canonical_path, "canonical_only"

    candidates = leaf_index.get(canonical_path) or []
    best_subset: tuple[str, int] | None = None
    best_superset: tuple[str, int] | None = None
    best_jaccard: tuple[str, float] | None = None

    for rlp, suffix in candidates:
        if not suffix:
            continue
        if suffix == facet_tokens:
            return rlp, "fdc_exact"
        if suffix.issubset(facet_tokens):
            score = len(suffix)
            if best_subset is None or score > best_subset[1]:
                best_subset = (rlp, score)
        if facet_tokens.issubset(suffix):
            score = len(suffix)
            if best_superset is None or score < best_superset[1]:
                best_superset = (rlp, score)
        union = len(suffix | facet_tokens)
        if union:
            j = len(suffix & facet_tokens) / union
            if best_jaccard is None or j > best_jaccard[1]:
                best_jaccard = (rlp, j)

    if best_subset and best_subset[1] >= len(facet_tokens) * 0.6:
        return best_subset[0], "fdc_subset"
    if best_superset:
        return best_superset[0], "fdc_superset"
    if best_jaccard and best_jaccard[1] >= 0.5:
        return best_jaccard[0], "fdc_jaccard"

    # No FDC retail leaf matches — fall back to canonical_path (real FDC),
    # NOT a synthesized fabrication.
    return canonical_path, "canonical_only"


def load_canonical_universe(path: Path) -> tuple[set[str], dict[str, str]]:
    """Return (canonical_paths_set, canonical_label_universe by_path)."""
    paths: set[str] = set()
    label_by_path: dict[str, Counter] = defaultdict(Counter)
    with path.open() as f:
        for row in csv.DictReader(f):
            cp = (row.get("canonical_path") or "").strip()
            if cp:
                paths.add(cp)
                label = (row.get("canonical_label") or "").strip()
                if label:
                    label_by_path[cp][label] += 1
    canonical_label = {p: c.most_common(1)[0][0] for p, c in label_by_path.items()}
    return paths, canonical_label


def load_path_rewrites(path: Path) -> dict[str, str]:
    """LLM-emitted canonical_path -> target canonical_path. Applied AFTER
    title-pattern overrides but BEFORE the fuzzy matcher, so a rewrite
    redirects the LLM's exact emission onto the FDC tree's canonical path.

    Accepts two column-naming conventions:
      * walmart_kroger_path_rewrites.csv : old_canonical_path, new_canonical_path
      * expand_fdc_rewrites.csv          : old_path, new_path
    """
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    with path.open() as f:
        for row in csv.DictReader(f):
            old = (row.get("old_canonical_path") or row.get("old_path") or "").strip()
            new = (row.get("new_canonical_path") or row.get("new_path") or "").strip()
            if old and new:
                out[old] = new
    return out


def merge_path_rewrites(*paths: Path) -> dict[str, str]:
    """Load and union multiple rewrite CSVs. Later files win on conflict."""
    merged: dict[str, str] = {}
    for p in paths:
        merged.update(load_path_rewrites(p))
    return merged


def load_overrides(path: Path) -> list[dict]:
    """Title-pattern overrides. Each row:
        pattern,canonical_path,canonical_label,product_identity_fixed,modifier,note
    `pattern` is a case-insensitive regex against the input title.
    """
    if not path.exists():
        return []
    rules: list[dict] = []
    with path.open() as f:
        for row in csv.DictReader(f):
            pat = row.get("pattern", "").strip()
            cp = row.get("canonical_path", "").strip()
            if not pat or not cp:
                continue
            try:
                rules.append({
                    "regex": re.compile(pat, re.I),
                    "canonical_path": cp,
                    "canonical_label": row.get("canonical_label", "").strip() or "",
                    "product_identity_fixed": row.get("product_identity_fixed", "").strip() or "",
                    "modifier": row.get("modifier", "").strip() or "",
                    "note": row.get("note", "").strip() or "",
                })
            except re.error:
                pass
    return rules


def path_tokens(path: str) -> tuple[str, ...]:
    """Normalize a canonical_path for fuzzy comparison."""
    parts = [p.strip().lower() for p in (path or "").split(">") if p.strip()]
    return tuple(normalize_key(p) for p in parts)


def fuzzy_match_path(llm_path: str, universe_index: dict,
                     universe_path_set: set | None = None) -> tuple[str, float]:
    """Try exact and token-set fuzzy match against the universe index.

    Returns (matched_canonical_path, confidence) — confidence in [0, 1.0].
    """
    if not llm_path:
        return "", 0.0
    llm_toks = path_tokens(llm_path)
    if not llm_toks:
        return "", 0.0

    # 1. Exact tuple match (case-folded singular)
    if llm_toks in universe_index:
        return universe_index[llm_toks], 1.0

    # 2. Same leaf token (last segment) and parent overlap
    leaf = llm_toks[-1]
    candidates = []
    for toks, cp in universe_index.items():
        if not toks:
            continue
        if toks[-1] != leaf:
            continue
        # Score by number of leading-token matches
        common = sum(1 for a, b in zip(llm_toks, toks) if a == b)
        candidates.append((common, len(toks), cp))
    if candidates:
        candidates.sort(key=lambda x: (-x[0], abs(len(llm_toks) - x[1])))
        score = candidates[0][0] / max(len(llm_toks), 1)
        return candidates[0][2], min(0.85, 0.5 + score * 0.4)

    # 3. Parent fallback — when LLM emits "Group > Family > Specific Leaf"
    # and the specific leaf doesn't exist in FDC, but the parent does.
    # Drop the leaf and try the parent path. The leaf gets preserved as
    # the variant/modifier on the row, the canonical_path lands at a
    # real FDC home. Catches ~thousands of SR28/FNDDS specific cuts and
    # niche foods.
    if universe_path_set is not None and len(llm_toks) > 1:
        parent_path = " > ".join(p.strip() for p in llm_path.split(">")[:-1])
        parent_path = parent_path.strip()
        if parent_path:
            parent_toks = path_tokens(parent_path)
            if parent_toks in universe_index:
                return universe_index[parent_toks], 0.70
            # Try grandparent if parent also missing
            if len(parent_toks) > 1:
                gp = " > ".join(p.strip() for p in parent_path.split(">")[:-1]).strip()
                if gp:
                    gp_toks = path_tokens(gp)
                    if gp_toks in universe_index:
                        return universe_index[gp_toks], 0.60

    # 4. Containment (any segment matches the leaf)
    for toks, cp in universe_index.items():
        if leaf in toks:
            return cp, 0.55

    return "", 0.0


FORM_TOKEN_TO_CODE = {
    "fresh": "1", "refrigerated": "1",
    "frozen": "2",
    "canned": "3", "jarred": "3", "bottled": "3",
    "dried": "4", "dehydrated": "4", "dry": "4",
    "powder": "5", "powdered": "5", "instant": "5", "mix": "5",
    "liquid": "6", "juice": "6", "drink": "6", "syrup": "6",
    "smoked": "8", "cured": "8",
    "pickled": "9", "pickle": "9",
}
PROC_TOKEN_TO_CODE = {
    "raw": "1", "uncooked": "1",
    "cooked": "3", "roasted": "3", "baked": "3", "grilled": "3", "fried": "3", "boiled": "3",
    "smoked": "4", "cured": "4", "aged": "4",
    "fermented": "5", "cultured": "5",
    "ready_to_eat": "6", "fully_cooked": "6", "pre_cooked": "6",
    "ready_to_cook": "7",
    "seasoned": "8", "marinated": "8", "flavored": "8", "teriyaki": "8", "bbq": "8",
    "breaded": "9", "battered": "9",
    "fortified": "A", "enriched": "A",
}
PTYPE_TOKEN_TO_CODE = {
    "whole": "0",
    "sliced": "1", "shaved": "1",
    "ground": "2", "minced": "2",
    "fillet": "3", "chop": "3", "cutlet": "3", "loin": "3",
    "block": "4", "chunk": "4",
    "shredded": "5", "grated": "5",
    "spread": "6",
    "crumbled": "7",
    "cubed": "8", "diced": "8",
    "stick": "9", "string": "9",
    "wedge": "A",
    "patty": "C", "burger": "C",
    "strip": "D", "tender": "D", "nugget": "D",
}


def _first_facet_code(values, mapping: dict, default: str = "0") -> str:
    """Pick the first facet token whose value maps to a positional code."""
    if not values:
        return default
    if isinstance(values, str):
        values = [values]
    for v in values:
        key = (v or "").strip().lower().replace(" ", "_")
        if key in mapping:
            return mapping[key]
    return default


NON_FOOD_PATH_PREFIXES = (
    "Non-Food",
    "Household",
    "Personal Care",
    "Pet",
    "Office Supplies",
    "Kitchen & Dining",
    "Baking & Cooking Supplies",
    "Health & Wellness",
    "Cleaning",
    "Other > Non-Food",
)


def is_non_food_path(canonical_path: str) -> bool:
    if not canonical_path:
        return False
    head = canonical_path.split(" > ")[0].strip()
    return any(canonical_path.startswith(p) for p in NON_FOOD_PATH_PREFIXES) or head in NON_FOOD_PATH_PREFIXES


def _has_value(v) -> bool:
    if v is None: return False
    if isinstance(v, list): return any(x for x in v if x)
    return bool(str(v).strip())


def derive_htc(canonical_path: str, canonical_label: str, modifier: str,
               product_identity: str, registry,
               form: list | str = None, processing: list | str = None,
               ptype: list | str = None,
               flavor: list | str = None,
               variant: list | str = None) -> dict:
    """Derive group/family/food_slot + full SKU code from canonical_path + facets.

    Returns BOTH the identity-only join code (positions 5-7 = 0) and the
    full SKU code (positions 5-7 populated from form/processing/ptype). The
    join code is the recipe<->retail equality key; the SKU code identifies
    the specific shoppable variant.
    """
    # Non-food short-circuit: paths that the LLM tagged as Non-Food /
    # Household / Personal Care / Pet / Office Supplies / Kitchen & Dining
    # don't represent edible foods. Route to group N regardless of any
    # other inference. This catches dish soap, bleach, paper cups, mason
    # jars, lotion, cat food, glue, scissors, etc.
    if is_non_food_path(canonical_path):
        code = code_from_parts("N", "0", "00")
        return {
            "htc_code": HTC_CODE_PREFIX + code,
            "htc_sku_code": HTC_CODE_PREFIX + code,
            "htc_group": "N", "htc_family": "0", "htc_food": "00",
            "htc_form": "0", "htc_processing": "0", "htc_ptype": "0",
            "htc_check": code[-1],
        }

    identity_text = canonical_label or product_identity or ""
    group = group_from_canonical_path(canonical_path, identity_text)
    if not group:
        group = "0"
    family = family_from_identity(group, identity_text, canonical_path,
                                  food_name=identity_text or product_identity)
    # Pass canonical_label as evidence_text so the cheese-context branch
    # can extract specific cheese types from "Cheese (Cheddar)" labels.
    # When flavor is empty, fall back to variant — the LLM sometimes
    # puts identity-discriminating tokens (chocolate_fudge, butterscotch,
    # cheddar) in variant instead of flavor.
    discriminator = flavor if _has_value(flavor) else variant
    food_name = effective_food_name(
        canonical_path,
        product_identity or canonical_label,
        modifier,
        evidence_text=canonical_label or "",
        flavor=discriminator,
    )
    entry = registry.lookup(group, family, food_name)
    if entry:
        food_slot = entry.food_slot
        if entry.htc_group == group:
            family = entry.htc_family
    else:
        food_slot = RESERVED_SLOT

    htc_form = _first_facet_code(form, FORM_TOKEN_TO_CODE)
    htc_proc = _first_facet_code(processing, PROC_TOKEN_TO_CODE)
    htc_ptype = _first_facet_code(ptype, PTYPE_TOKEN_TO_CODE)

    join_code = code_from_parts(group, family, food_slot)
    sku_code = code_from_parts(group, family, food_slot, htc_form, htc_proc, htc_ptype)
    return {
        # ~prefix keeps Excel from auto-formatting "100E0000" as scientific notation.
        "htc_code": HTC_CODE_PREFIX + join_code,    # identity-only join code (form/proc/ptype = 0)
        "htc_sku_code": HTC_CODE_PREFIX + sku_code, # full variant code with form/proc/ptype
        "htc_group": group,
        "htc_family": family,
        "htc_food": food_slot,
        "htc_form": htc_form,
        "htc_processing": htc_proc,
        "htc_ptype": htc_ptype,
        "htc_check": join_code[-1],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    ap.add_argument("--path-rewrites", type=Path, default=DEFAULT_PATH_REWRITES)
    ap.add_argument("--expand-rewrites", type=Path, default=DEFAULT_EXPAND_REWRITES,
                    help="Additional FDC-only rewrites (out-of-FDC paths → FDC paths).")
    ap.add_argument("--review-out", type=Path, default=DEFAULT_REVIEW)
    ap.add_argument("--api-out", type=Path, default=DEFAULT_API_OUT)
    ap.add_argument("--ing-out", type=Path, default=DEFAULT_ING_OUT)
    ap.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    args = ap.parse_args()

    print(f"loading input ({args.input}) ...", file=sys.stderr)
    inp = load_input(args.input)
    print(f"  {len(inp):,} input rows", file=sys.stderr)

    print(f"loading LLM records ({args.jsonl}) ...", file=sys.stderr)
    llm = load_llm_records(args.jsonl)
    print(f"  {len(llm):,} LLM records", file=sys.stderr)

    print(f"loading canonical-path universe ({args.audit}) ...", file=sys.stderr)
    universe, canonical_label_by_path = load_canonical_universe(args.audit)
    universe_index = {path_tokens(cp): cp for cp in universe}
    print(f"  {len(universe):,} canonical paths", file=sys.stderr)

    print(f"loading retail_leaf_path index ({args.audit}) ...", file=sys.stderr)
    retail_leaf_index = load_retail_leaf_index(args.audit)
    n_leaves = sum(len(v) for v in retail_leaf_index.values())
    print(f"  {n_leaves:,} retail_leaf_paths under {len(retail_leaf_index):,} canonical paths",
          file=sys.stderr)

    print(f"loading overrides ({args.overrides}) ...", file=sys.stderr)
    overrides = load_overrides(args.overrides)
    print(f"  {len(overrides):,} override rules", file=sys.stderr)

    print(f"loading path rewrites ({args.path_rewrites}) ...", file=sys.stderr)
    path_rewrites = merge_path_rewrites(args.path_rewrites, args.expand_rewrites)
    print(f"  {len(path_rewrites):,} path-rewrite rules"
          f" (incl. {sum(1 for _ in args.expand_rewrites.open()) - 1 if args.expand_rewrites.exists() else 0}"
          f" from {args.expand_rewrites.name})", file=sys.stderr)

    registry = default_registry()
    args.api_out.parent.mkdir(parents=True, exist_ok=True)
    args.ing_out.parent.mkdir(parents=True, exist_ok=True)
    args.review_out.parent.mkdir(parents=True, exist_ok=True)

    api_rows: list[dict] = []
    ing_rows: list[dict] = []
    review_rows: list[dict] = []

    stats = Counter()
    by_match_method = Counter()

    def _facet_to_str(v) -> str:
        if v is None:
            return ""
        if isinstance(v, list):
            return " | ".join(str(x).strip() for x in v if str(x).strip())
        return str(v).strip()

    for fid, rec in llm.items():
        src = inp.get(fid, {})
        title = src.get("title", "")
        corpus = src.get("_corpus", "")
        source = src.get("source", "")

        # Pull all the facets the LLM produced. These are the "retail-path
        # equivalents" — what the FDC consensus audit stores in variant,
        # flavor, form_texture_cut, processing_storage, claims, modifier.
        llm_path = (rec.get("canonical_path") or "").strip()
        canonical_label = (rec.get("canonical_label") or "").strip()
        product_identity = (rec.get("product_identity") or "").strip()
        retail_type = (rec.get("retail_type") or "").strip()
        variant = rec.get("variant") or []
        flavor = rec.get("flavor") or []
        form_texture_cut = rec.get("form_texture_cut") or []
        processing_storage = rec.get("processing_storage") or []
        claims = rec.get("claims") or []
        components = rec.get("components") or []
        modifier_raw = rec.get("modifier") or ""
        review_flags = rec.get("review_flags") or []
        rationale = rec.get("rationale") or ""
        confidence = rec.get("confidence", 0.0)
        modifier = primary_modifier(modifier_raw) if isinstance(modifier_raw, str) else ""

        # 1. Title-pattern override wins (corrects systematic LLM mistakes).
        canonical_path = ""
        match_method = ""
        match_conf = 0.0
        for rule in overrides:
            if rule["regex"].search(title):
                canonical_path = rule["canonical_path"]
                if rule["canonical_label"]:
                    canonical_label = rule["canonical_label"]
                if rule["product_identity_fixed"]:
                    product_identity = rule["product_identity_fixed"]
                if rule["modifier"]:
                    modifier = rule["modifier"]
                match_method = "override"
                match_conf = 1.0
                break

        # 1.5. Path-rewrite layer: if the LLM emitted exactly an old_path
        # we have a rewrite for, redirect to the new_path before the
        # fuzzy matcher sees it. Captures systematic LLM mistakes
        # (cookies under Trail Mix, salad dressing under Plant Based
        # Cheese, cereal under Beverage > Protein Drinks).
        if not canonical_path:
            rewritten = path_rewrites.get(llm_path)
            if rewritten:
                canonical_path = rewritten
                match_method = "path_rewrite"
                match_conf = 1.0

        # 1.7. Identity-driven routing. The LLM's product_identity_fixed is
        # the most reliable signal. For each identity, FDC has a clear
        # dominant canonical_path (e.g. Bagels → Bakery > Bagels in 939/944
        # rows). Force routing here BEFORE fuzzy matching, so we don't snap
        # correctly-identified ingredients to junk paths produced by lone
        # misclassified FDC rows. Tolerant lookup handles singular/plural
        # mismatches (LLM emits 'Bagel' for FDC's 'Bagels').
        if not canonical_path and product_identity:
            mapped = lookup_identity_path(product_identity)
            if mapped and mapped in universe:
                canonical_path = mapped
                match_method = "identity_map"
                match_conf = 0.99

        # 1.8. Title-driven deepening. When pid was generic (Cheese, Bread,
        # Cookies) and the title carries a more specific identity (Havarti,
        # Cinnamon Swirl, Chocolate Chip), promote the row to the deeper
        # FDC canonical_path — provided that deeper path is a strict descendant
        # of the current one (so "Cheddar Goldfish Crackers" doesn't snap from
        # Snack > Crackers to Dairy > Cheese > Cheddar).
        if canonical_path and canonical_path in universe and title:
            deeper = resolve_deep_identity(title, canonical_path)
            if deeper and deeper in universe:
                canonical_path = deeper
                match_method = "identity_deepened"
                match_conf = 0.97

        # 2. Otherwise normalize LLM path against the canonical-path universe.
        if not canonical_path:
            matched, conf = fuzzy_match_path(llm_path, universe_index, universe)
            if matched:
                canonical_path = matched
                match_method = "exact" if conf >= 0.99 else "fuzzy"
                match_conf = conf
            else:
                canonical_path = llm_path
                match_method = "unmatched"
                match_conf = 0.0

        # 2.5. Post-fuzzy path rewrite: if the matcher routed us to a known-
        # bad FDC path (existing redundancy in the tree), rewrite to the
        # canonical target. Catches cases like Snack > Chips > Cookies ->
        # Snack > Cookies > Cookies, Pantry > Plant Based Cheese > Salad
        # Dressing -> Pantry > Salad Dressings > Salad Dressing.
        post_rewrite = path_rewrites.get(canonical_path)
        if post_rewrite:
            canonical_path = post_rewrite
            match_method = "path_rewrite"
            match_conf = 1.0

        # 2.75. FDC-constraint enforcement. Every output row's canonical_path
        # MUST be in the FDC universe. If we still aren't, try parent-strip
        # once (drop the leaf); if even the parent isn't in FDC, route to
        # the Non-Food > Other catch-all so the row is at least FDC-valid.
        if canonical_path and canonical_path not in universe:
            parts = [s.strip() for s in canonical_path.split(" > ") if s.strip()]
            snapped = False
            while len(parts) > 1:
                parts.pop()
                candidate = " > ".join(parts)
                if candidate in universe:
                    canonical_path = candidate
                    match_method = "fdc_parent_strip"
                    match_conf = 0.5
                    snapped = True
                    stats["enforce_parent_strip"] += 1
                    break
            if not snapped:
                canonical_path = NON_FOOD_OTHER
                match_method = "fdc_catchall"
                match_conf = 0.1
                stats["enforce_catchall"] += 1

        if not canonical_path:
            stats["no_path"] += 1
            continue

        # 3. Derive HTC parts (both identity-only join code and full SKU code).
        # Flavor is part of identity per user's design (chocolate pudding ≠
        # vanilla pudding ≠ coconut pudding get distinct codes). Pass variant
        # too — LLM sometimes puts the flavor-equivalent token in variant
        # (chocolate_fudge, butterscotch, cheddar) instead of flavor.
        htc = derive_htc(
            canonical_path=canonical_path,
            canonical_label=canonical_label,
            modifier=modifier or modifier_raw,
            product_identity=product_identity,
            registry=registry,
            form=form_texture_cut,
            processing=processing_storage,
            ptype=form_texture_cut,
            flavor=flavor,
            variant=variant,
        )
        by_match_method[match_method] += 1

        # Compose retail_leaf_path from facets — walks the FDC retail tree
        # under canonical_path using the row's modifier tokens. Even when
        # the LLM's canonical_path was wrong (we already corrected it via
        # identity_map), the LLM's facet extraction is reliable.
        facet_tokens = _normalize_facet_tokens(
            _facet_to_str(variant),
            _facet_to_str(flavor),
            _facet_to_str(form_texture_cut),
            _facet_to_str(processing_storage),
            _facet_to_str(claims),
            _facet_to_str(modifier_raw),
        )
        retail_leaf_path, retail_leaf_source = compose_retail_leaf_path(
            canonical_path, facet_tokens, retail_leaf_index
        )
        stats[f"retail_leaf_{retail_leaf_source}"] += 1

        # Full identity code: ~bucket-VVVVVV-KKKK
        # Each unique retail_leaf_path → unique variant hash.
        # Claims encoded as searchable bitfield.
        htc_full_code = compose_full_code(
            htc.get("htc_code", ""),
            canonical_path,
            retail_leaf_path,
            _facet_to_str(claims),
        )

        out_row = {
            "fdc_id": fid,
            "title": title,
            "source": source,
            "corpus": corpus,
            "retail_type": retail_type,
            # Identity layer
            "canonical_path": canonical_path,
            "retail_leaf_path": retail_leaf_path,
            "retail_leaf_source": retail_leaf_source,
            "canonical_label": canonical_label,
            "product_identity_fixed": product_identity,
            # Facet layer (the "retail path" decomposition)
            "variant": _facet_to_str(variant),
            "flavor": _facet_to_str(flavor),
            "form_texture_cut": _facet_to_str(form_texture_cut),
            "processing_storage": _facet_to_str(processing_storage),
            "claims": _facet_to_str(claims),
            "modifier": _facet_to_str(modifier_raw),
            "components_count": len(components) if isinstance(components, list) else 0,
            "components": json.dumps(components, sort_keys=True) if components else "",
            # HTC layer (codes derived from the identity + facets)
            **htc,
            "htc_full_code": htc_full_code,
            # Provenance
            "match_method": match_method,
            "match_confidence": f"{match_conf:.2f}",
            "llm_canonical_path": llm_path,
            "llm_confidence": f"{float(confidence) if isinstance(confidence,(int,float)) else 0:.2f}",
            "llm_review_flags": _facet_to_str(review_flags),
            "llm_rationale": rationale,
            "htc_confidence": f"{0.95 if match_method == 'override' else (0.90 if match_method == 'exact' else (0.75 if match_method == 'fuzzy' else 0.40)):.2f}",
            "htc_source": match_method,
        }

        if corpus == "recipe_ingredient":
            ing_rows.append(out_row)
        else:
            api_rows.append(out_row)

        if match_method == "unmatched" or htc["htc_food"] == RESERVED_SLOT:
            review_rows.append(out_row)

        stats["total"] += 1

    # Write outputs — schema mirrors consensus_full_corpus_audit.csv so every
    # facet from the LLM is preserved alongside the HTC codes.
    full_cols = [
        # ID + provenance
        "fdc_id", "source", "corpus", "title", "retail_type",
        # Identity layer
        "canonical_path", "retail_leaf_path", "retail_leaf_source",
        "canonical_label", "product_identity_fixed",
        # Facet decomposition (this is the "retail path" content the user wants kept)
        "variant", "flavor", "form_texture_cut", "processing_storage",
        "claims", "modifier", "components_count", "components",
        # HTC codes (identity-only join + full SKU + unique-per-rlp full code)
        "htc_code", "htc_sku_code", "htc_full_code",
        "htc_group", "htc_family", "htc_food",
        "htc_form", "htc_processing", "htc_ptype", "htc_check",
        # LLM provenance
        "llm_canonical_path", "llm_confidence", "llm_review_flags", "llm_rationale",
        # Match provenance
        "match_method", "match_confidence",
        "htc_confidence", "htc_source",
    ]

    print(f"writing api cache tagged ({args.api_out}) — {len(api_rows):,} rows ...", file=sys.stderr)
    with args.api_out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=full_cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(api_rows)

    print(f"writing ingredient tagged ({args.ing_out}) — {len(ing_rows):,} rows ...", file=sys.stderr)
    with args.ing_out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=full_cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(ing_rows)

    print(f"writing review queue ({args.review_out}) — {len(review_rows):,} rows ...", file=sys.stderr)
    with args.review_out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=full_cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(review_rows)

    summary = {
        "total_rows": stats["total"],
        "api_rows": len(api_rows),
        "ingredient_rows": len(ing_rows),
        "review_rows": len(review_rows),
        "match_methods": dict(by_match_method),
    }
    with args.summary_out.open("w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
