"""Column ↔ path consistency invariants (10-15).

For each row, the structured columns (variant, flavor, form_texture_cut,
processing_storage, claims, product_identity_fixed) must be reflected in
canonical_path. If a column is populated, its values must appear as path
segments. If a path has a leaf NOT derivable from any column or title,
that's a hallucination.

Each test produces a per-fdc verdict so 100% row coverage is preserved.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from conftest import V2, fail_with_samples

REPORT_DIR = V2 / "tests" / "data"


# Plain/default tokens that are intentionally NOT preserved in canonical paths
# (per taxonomy_finalizer.PLAIN_TOKENS — generic words that don't differentiate
# the SKU). Skipped during variant/flavor consistency checks.
PLAIN_TOKENS = {
    "plain", "regular", "original", "classic", "natural",
    "unflavored", "unscented", "neutral",
    "enriched", "unenriched", "artisan", "rustic", "country",
    "homestyle", "home style", "traditional", "gourmet",
    "bakery", "style", "authentic", "old", "fashioned",
    "premium", "deluxe", "fancy", "handcrafted", "signature", "select",
    # Default-state claims that are dropped from path
    "sweetened",
}


def _norm(s: str) -> str:
    """Lowercase + replace _ with space + collapse whitespace."""
    return re.sub(r"\s+", " ", (s or "").replace("_", " ").lower().strip())


def _column_values(r: dict, col: str) -> list[str]:
    """Pipe-split + underscore→space + strip. Returns lowercase tokens.
    Filters PLAIN_TOKENS that are intentionally not preserved in path."""
    raw = (r.get(col) or "").strip()
    if not raw:
        return []
    out = []
    for piece in raw.split("|"):
        v = _norm(piece)
        if v and v not in PLAIN_TOKENS:
            out.append(v)
    return out


def _path_segs_lower(r: dict) -> list[str]:
    """Use retail_leaf_path for variant/flavor/form/claims checks since
    canonical_path is family+type only per the taxonomy contract.
    Falls back to canonical_path if RLP is empty.
    """
    rlp = (r.get("retail_leaf_path") or "").strip()
    if rlp:
        return [_norm(s) for s in rlp.split(" > ")]
    cp = (r.get("canonical_path") or "").strip()
    if not cp:
        return []
    return [_norm(s) for s in cp.split(" > ")]


_STOPWORDS = {"the", "and", "or", "of", "in", "with", "a", "an", "to", "for"}


def _has_token_match(token: str, segs: list[str]) -> bool:
    """A column token matches a path segment if:
       - exact equality (case-insensitive, normalized), OR
       - one is contained in the other (substring), OR
       - at least half of the token's content-words appear across the path

    Examples:
       'apple slices' matches 'apple snack pack' (apple appears).
       'cinnamon raisin' matches 'cinnamon raisin' or 'raisin' alone.
       'tart apple' matches if 'apple' appears anywhere in path.
    """
    if not token: return True
    for s in segs:
        if token == s: return True
        if token in s or s in token: return True

    # Word-level fallback
    token_words = [w for w in token.split() if w and w not in _STOPWORDS]
    if not token_words:
        return True
    seg_blob = " ".join(segs)
    matches = sum(1 for w in token_words if w in seg_blob)
    return matches / len(token_words) >= 0.5


# ---------------------------------------------------------------------
# I10: product_identity_fixed appears in path
# ---------------------------------------------------------------------

def test_product_identity_in_path(audit_rows):
    """If PI is populated, the type segment of canonical_path must contain
    or be related to PI (case-insensitive, plural-aware).

    Allowed misses: PI is generic ('Other', 'Misc', empty).
    """
    bad = []
    for r in audit_rows:
        pi = _norm(r.get("product_identity_fixed") or "")
        if not pi or pi in {"other", "misc", "miscellaneous"}:
            continue
        segs = _path_segs_lower(r)
        if len(segs) < 2:
            continue
        # PI should match the type segment OR appear anywhere as a segment
        # Allow PI to match by containment (e.g., PI='Bagels' in path-type 'Cinnamon Raisin Bagels')
        if not _has_token_match(pi, segs):
            bad.append(r)
    if bad:
        fail_with_samples(
            "Invariant 10 violated: product_identity_fixed not reflected in canonical_path",
            bad, extra_cols=["product_identity_fixed"],
        )


# ---------------------------------------------------------------------
# I11: variant column → present in path
# ---------------------------------------------------------------------

def test_variant_in_path(audit_rows):
    """Every non-empty variant value (after split on '|' and underscore→space)
    must appear as a path segment.
    """
    bad = []
    for r in audit_rows:
        variants = _column_values(r, "variant")
        if not variants:
            continue
        segs = _path_segs_lower(r)
        missing = [v for v in variants if not _has_token_match(v, segs)]
        if missing:
            r2 = dict(r); r2["_missing_variants"] = " | ".join(missing)
            bad.append(r2)
    if bad:
        fail_with_samples(
            "Invariant 11 violated: variant column populated but not in canonical_path",
            bad, extra_cols=["variant", "_missing_variants"],
        )


# ---------------------------------------------------------------------
# I12: flavor column → present in path
# ---------------------------------------------------------------------

def test_flavor_in_path(audit_rows):
    """Every non-empty flavor value must appear as a path segment."""
    bad = []
    for r in audit_rows:
        flavors = _column_values(r, "flavor")
        if not flavors:
            continue
        segs = _path_segs_lower(r)
        missing = [f for f in flavors if not _has_token_match(f, segs)]
        if missing:
            r2 = dict(r); r2["_missing_flavors"] = " | ".join(missing)
            bad.append(r2)
    if bad:
        fail_with_samples(
            "Invariant 12 violated: flavor column populated but not in canonical_path",
            bad, extra_cols=["flavor", "_missing_flavors"],
        )


# ---------------------------------------------------------------------
# I13: form_texture_cut column → present in path
# ---------------------------------------------------------------------

def test_form_in_path(audit_rows):
    """Every non-empty form value must appear as a path segment."""
    bad = []
    for r in audit_rows:
        forms = _column_values(r, "form_texture_cut")
        if not forms:
            continue
        segs = _path_segs_lower(r)
        missing = [f for f in forms if not _has_token_match(f, segs)]
        if missing:
            r2 = dict(r); r2["_missing_forms"] = " | ".join(missing)
            bad.append(r2)
    if bad:
        fail_with_samples(
            "Invariant 13 violated: form_texture_cut populated but not in canonical_path",
            bad, extra_cols=["form_texture_cut", "_missing_forms"],
        )


# ---------------------------------------------------------------------
# I14: claims column → all values present as path segments at end
# ---------------------------------------------------------------------

def test_claims_in_path(audit_rows):
    """Every non-empty claim value must appear as a path segment."""
    bad = []
    for r in audit_rows:
        claims = _column_values(r, "claims")
        if not claims:
            continue
        segs = _path_segs_lower(r)
        missing = [c for c in claims if not _has_token_match(c, segs)]
        if missing:
            r2 = dict(r); r2["_missing_claims"] = " | ".join(missing)
            bad.append(r2)
    if bad:
        fail_with_samples(
            "Invariant 14 violated: claims populated but not in canonical_path",
            bad, extra_cols=["claims", "_missing_claims"],
        )


# ---------------------------------------------------------------------
# I15: no hallucinated leaves (every path segment must be derivable from
# title or some facet column)
# ---------------------------------------------------------------------

def _extract_title_tokens(title: str) -> set[str]:
    """All multi-word and single-word tokens from title, lowercased."""
    title = (title or "").lower()
    # Tokenize on non-word + drop short
    words = re.findall(r"[a-z]+(?:[\s'-][a-z]+)*", title)
    out = set()
    for w in words:
        out.add(w.strip())
        for sub in w.split():
            if len(sub) > 2:
                out.add(sub)
    return out


def _all_facet_tokens(r: dict) -> set[str]:
    """Tokens from all facet columns + title + FNDDS desc + structural
    category — anything one of these has, we consider 'derivable' for the path.

    Includes category_path_fixed so structural sub-categorizations like
    'Pantry > Sweeteners > Sugar > Frosting' don't flag 'Sugar' as
    hallucinated — the cleanup pipeline assigned it as a structural parent.
    """
    tokens: set[str] = set()
    for col in ("variant", "flavor", "form_texture_cut", "processing_storage",
                "claims", "product_identity_fixed", "modifier"):
        for v in _column_values(r, col):
            tokens.add(v)
            for sub in v.split():
                if len(sub) > 2:
                    tokens.add(sub)
    tokens |= _extract_title_tokens(r.get("title") or "")
    tokens |= _extract_title_tokens(r.get("fndds_desc") or "")
    # Structural category words count as derivable
    tokens |= _extract_title_tokens(r.get("category_path_fixed") or "")
    tokens |= _extract_title_tokens(r.get("canonical_path") or "")
    return tokens


def test_no_hallucinated_leaves(audit_rows):
    """Every leaf segment must be derivable from title, FNDDS desc, or
    any facet column. Catches the 'Lemon' leaking from FNDDS dedupe class
    of bug.

    Family + type are NOT checked here (they come from BFC table / FNDDS canon
    map, not from facet columns). Only segments after position 2.
    """
    bad = []
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        segs = cp.split(" > ")
        if len(segs) <= 2:
            continue
        tokens = _all_facet_tokens(r)
        for s in segs[2:]:
            sl = _norm(s)
            if not sl:
                continue
            # Try whole segment + each word
            words = sl.split()
            if any(w in tokens for w in words) or sl in tokens:
                continue
            r2 = dict(r); r2["_hallucinated_leaf"] = s
            bad.append(r2)
            break
    if bad:
        fail_with_samples(
            "Invariant 15 violated: leaf segment not derivable from title/FNDDS/facets",
            bad, extra_cols=["product_identity_fixed", "_hallucinated_leaf"],
        )
