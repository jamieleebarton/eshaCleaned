"""HTC full-code composition: bucket + variant hash + claims bitfield.

The htc_full_code is the unique-per-retail_leaf_path identity code. Format:

    ~GFFOPTC-VVVVVV-KKKK
    └─bucket─┘└variant┘└claims┘
    8 char    6 hex    4 hex

  bucket  : the 8-char htc_code (group, family, food_slot, form, proc, ptype, check)
            same as before, with `~` prefix to keep Excel from auto-formatting.
  variant : 6 hex chars (24 bits, 16M values) — deterministic SHA-256 truncation
            of the retail_leaf_path SUFFIX (everything past canonical_path).
            Same retail_leaf_path → same variant. Different rlp → different variant.
            Collision probability for ~36k rlps in one bucket ≈ 0.65 expected
            collisions (birthday). Practically unique.
  claims  : 4 hex chars = 16 bits = 16 binary claim flags. Each bit position
            corresponds to a fixed canonical claim (organic, gluten_free, etc.).
            Lets you regex-search "all organic products" by checking bit 0.

Search examples:
  - All bagels                    : code starts with ~81
  - All organic                   : claims field has bit 0 set ((int(claims,16) & 1) != 0)
  - All organic + gluten-free     : bit 0 AND bit 2 set
  - Specific cinnamon raisin bagel: full code matches exactly

Two-tier matching:
  - Recipe says "bagel"           → join on htc_code (bucket only)
  - Recipe says "cinnamon raisin" → join on first 16 chars (bucket + variant)
  - Recipe says "organic cinnamon": join on full htc_full_code
"""
from __future__ import annotations

import hashlib
import re

# Excel-safe prefix; consistent with htc_code's prefix elsewhere.
PREFIX = "~"

# Canonical claim → bit position. Order is API-stable; never reorder, only append.
CLAIM_BITS: dict[str, int] = {
    # Sourcing (bits 0-3)
    "organic":          0,
    "non_gmo":          1,
    "gluten_free":      2,
    "dairy_free":       3,
    # Diet (bits 4-7)
    "vegan":            4,
    "vegetarian":       5,
    "kosher":           6,
    "halal":            7,
    # Sugar/Fat/Sodium (bits 8-11)
    "sugar_free":       8,
    "low_sugar":        9,
    "low_fat":         10,
    "low_sodium":      11,
    # Other (bits 12-15)
    "high_protein":    12,
    "whole_grain":     13,
    "fair_trade":      14,
    "natural":         15,
}

# Synonyms map any casing/spelling variant into the canonical claim key.
CLAIM_SYNONYMS: dict[str, str] = {
    "organic": "organic",
    "certified_organic": "organic",
    "usda_organic": "organic",
    "non_gmo": "non_gmo",
    "non-gmo": "non_gmo",
    "nongmo": "non_gmo",
    "gmo_free": "non_gmo",
    "gluten_free": "gluten_free",
    "gluten-free": "gluten_free",
    "glutenfree": "gluten_free",
    "no_gluten": "gluten_free",
    "dairy_free": "dairy_free",
    "dairy-free": "dairy_free",
    "lactose_free": "dairy_free",
    "no_dairy": "dairy_free",
    "non_dairy": "dairy_free",
    "vegan": "vegan",
    "plant_based": "vegan",
    "vegetarian": "vegetarian",
    "lacto_ovo_vegetarian": "vegetarian",
    "kosher": "kosher",
    "halal": "halal",
    "sugar_free": "sugar_free",
    "no_sugar": "sugar_free",
    "no_added_sugar": "sugar_free",
    "low_sugar": "low_sugar",
    "reduced_sugar": "low_sugar",
    "low_fat": "low_fat",
    "reduced_fat": "low_fat",
    "fat_free": "low_fat",
    "nonfat": "low_fat",
    "low_sodium": "low_sodium",
    "reduced_sodium": "low_sodium",
    "no_salt": "low_sodium",
    "low_salt": "low_sodium",
    "high_protein": "high_protein",
    "protein_rich": "high_protein",
    "whole_grain": "whole_grain",
    "wholegrain": "whole_grain",
    "whole_wheat": "whole_grain",
    "whole_meal": "whole_grain",
    "fair_trade": "fair_trade",
    "fairtrade": "fair_trade",
    "natural": "natural",
    "all_natural": "natural",
    "100_natural": "natural",
}

# Pre-normalized lookup: lowercase key with non-alphanumerics squeezed to "_"
_NORMALIZED_SYNONYMS: dict[str, str] = {
    re.sub(r"[^a-z0-9]+", "_", k.lower()).strip("_"): v
    for k, v in CLAIM_SYNONYMS.items()
}


def _norm_token(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")


def claim_bits_from_str(claims_blob: str) -> int:
    """Parse a claims field (pipe/comma-separated string) into a 16-bit mask."""
    if not claims_blob:
        return 0
    bits = 0
    for piece in re.split(r"[|,;]", claims_blob):
        token = _norm_token(piece)
        if not token:
            continue
        canonical = _NORMALIZED_SYNONYMS.get(token)
        if canonical is None:
            # Try sub-tokens (handles "low_fat_dairy_free" → low_fat + dairy_free)
            for chunk in re.split(r"_", token):
                if chunk in _NORMALIZED_SYNONYMS:
                    bits |= 1 << CLAIM_BITS[_NORMALIZED_SYNONYMS[chunk]]
            continue
        bits |= 1 << CLAIM_BITS[canonical]
    return bits


def claim_bits_to_hex(bits: int) -> str:
    """16-bit mask → 4-char uppercase hex (e.g. 0x0005 → '0005')."""
    return f"{bits & 0xFFFF:04X}"


def variant_hash(canonical_path: str, retail_leaf_path: str) -> str:
    """Stable 6-hex hash of the retail_leaf_path suffix (everything past
    canonical_path). Same suffix → same hash. Empty suffix → '000000'."""
    cp = (canonical_path or "").strip()
    rlp = (retail_leaf_path or "").strip()
    if not rlp:
        return "000000"
    if cp and rlp.startswith(cp):
        suffix = rlp[len(cp):].lstrip(" >")
    else:
        suffix = rlp
    if not suffix:
        return "000000"
    # Normalize suffix: lowercase, collapse separators, sort tokens for
    # order-independent hashing. Two rows with the same identity content
    # but different segment order in the path get the same variant hash.
    tokens = sorted(t for t in re.split(r"[\s>_/\-,()&]+", suffix.lower()) if t)
    norm = " ".join(tokens)
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return h[:6].upper()


def compose_full_code(
    htc_code: str,
    canonical_path: str,
    retail_leaf_path: str,
    claims: str,
) -> str:
    """Compose the htc_full_code: ~bucket-VVVVVV-KKKK.

    htc_code may already have the `~` prefix; we keep exactly one prefix.
    """
    bucket = htc_code or ""
    if bucket.startswith(PREFIX):
        bucket_body = bucket[1:]
    else:
        bucket_body = bucket
    if not bucket_body:
        return ""
    variant = variant_hash(canonical_path, retail_leaf_path)
    bits = claim_bits_from_str(claims)
    claims_hex = claim_bits_to_hex(bits)
    return f"{PREFIX}{bucket_body}-{variant}-{claims_hex}"


def parse_full_code(full_code: str) -> dict:
    """Inverse of compose_full_code — split into bucket / variant / claims."""
    s = (full_code or "").strip()
    if s.startswith(PREFIX):
        s = s[1:]
    parts = s.split("-")
    if len(parts) < 3:
        return {"bucket": s, "variant": "", "claims_hex": "", "claim_bits": 0}
    bucket, variant, claims_hex = parts[0], parts[1], parts[2]
    try:
        bits = int(claims_hex, 16)
    except ValueError:
        bits = 0
    return {
        "bucket": PREFIX + bucket,
        "variant": variant,
        "claims_hex": claims_hex,
        "claim_bits": bits,
        "claims": [name for name, bit in CLAIM_BITS.items() if bits & (1 << bit)],
    }
