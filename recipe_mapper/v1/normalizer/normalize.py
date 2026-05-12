"""Recipe ingredient text normalizer.

Pipeline:
  1. apply_synonyms()  — collapse synonyms to canonical text
  2. extract_identity_phrase() — find Bucket 3 identity-changing phrases first
  3. bucket_remaining_tokens() — single-word adjectives go to Bucket 1 / 2 / noise
  4. assemble canonical_text + facets

Output per ingredient:
  {
    "original": "1 cup fat-free organic mayonnaise, drained",
    "canonical_text": "mayonnaise",
    "user_claims": ["fat_free", "organic"],   # Bucket 1
    "form_facets": ["drained"],                # Bucket 2 (form/processing)
    "processing_facets": [],
    "identity_phrase": None,                   # Bucket 3 if matched
    "raw_quantity": "1 cup",
  }

  {
    "original": "smoked paprika",
    "canonical_text": "smoked paprika",        # Bucket 3 — identity preserved
    "user_claims": [],
    "form_facets": [],
    "processing_facets": [],
    "identity_phrase": "smoked paprika",
  }
"""
from __future__ import annotations

import re
from typing import NamedTuple

from .adjective_buckets import (
    BUCKET_1_PREFERENCE_FACETS,
    BUCKET_2_CULINARY_FORM,
    BUCKET_2_CULINARY_PROCESSING,
    BUCKET_2_NOISE,
    BUCKET_3_IDENTITY_PHRASES,
)
from .synonym_map import apply_synonyms


# Quantity prefix — recipes often prepend amounts ("1 cup", "2 tbsp", "a pinch of")
QUANTITY_RE = re.compile(
    r"^(?:about\s+)?"
    r"(?:\d+(?:[.\-/ ]\d+)*\s*"
    r"(?:cups?|tbsps?|tablespoons?|tsps?|teaspoons?|oz|ozs?|ounces?|"
    r"lbs?|pounds?|grams?|g|kg|kilograms?|ml|milliliters?|l|liters?|"
    r"pints?|quarts?|gallons?|fl\.?\s*oz|cans?|jars?|packages?|pkg|pkgs|"
    r"bottles?|boxes?|bags?|envelopes?|sticks?|slices?|cloves?|sprigs?|"
    r"heads?|bunches?|stalks?|ears?|pinches?|dashes?|drops?|handfuls?|"
    r"pieces?|pcs|servings?|sheets?|leaves?|bulbs?|wedges?)\s+(?:of\s+)?"
    r"|"
    r"(?:a|an|some|several|few|many|couple)\s+"
    r"(?:cup|tbsp|tablespoon|tsp|teaspoon|pinch|dash|handful)?\s*(?:of\s+)?"
    r")",
    re.I,
)

PARENS_RE = re.compile(r"\s*\([^)]*\)\s*")  # strip "(2 oz)", "(8 ounces)", etc.

# Percentage tokens — `1%`, `2%`, `100%`. Recipe authors use them as fat-content
# qualifiers for dairy or as marketing labels (`100% fruit pectin`). Strip the
# token; downstream the claim will be inferred from the remaining text if any.
PERCENT_RE = re.compile(r"\s*\b\d+(?:\.\d+)?\s*%\s*")

# Alternation cleanup — recipe authors offer choices like
# "lemon juice or lime juice", "fresh basil or 1 tsp dried", "sugar, optionally honey".
# Resolve deterministically by taking the FIRST option (matches plan: STAGE 3
# "X or Y choices" → pick first option deterministically).
ALTERNATION_RE = re.compile(
    r"\s*(?:,\s*)?\b(?:or|optionally|alternatively|substitute(?:d)?\s+with|"
    r"sub(?:stitute)?\s+with|in\s+place\s+of|substituted?\s+by|"
    r"or\s+substitute|or\s+sub|or\s+use)\b.*$",
    re.I,
)
# Trailing aside markers — em-dash / en-dash explanations after the food name.
# Plain hyphen requires SURROUNDING whitespace so we don't munge "low-fat".
TRAILING_DASH_RE = re.compile(r"\s+(?:[—–]|-(?=\s))\s*[^,]*$")

class Normalized(NamedTuple):
    original: str
    canonical_text: str
    user_claims: list[str]
    form_facets: list[str]
    processing_facets: list[str]
    identity_phrase: str | None
    raw_quantity: str


def _strip_quantity_and_parens(text: str) -> tuple[str, str]:
    """Pull off any leading quantity expression and parenthetical asides.
    Returns (stripped_text, raw_quantity_string)."""
    raw_qty = ""
    m = QUANTITY_RE.match(text)
    if m:
        raw_qty = m.group(0).strip()
        text = text[m.end():]
    text = PARENS_RE.sub(" ", text)
    text = PERCENT_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;-")
    return text, raw_qty


def _resolve_alternation(text: str) -> str:
    """Pick the first option when the author offered alternatives.
    'lemon juice or lime juice' → 'lemon juice'.
    'fresh basil, optionally dried' → 'fresh basil'.
    'butter — or use margarine' → 'butter'.

    Per RECIPE_NORMALIZATION_PLAN.md STAGE 3:
      'X or Y choices' → pick FIRST option deterministically.
    """
    if not text:
        return text
    text = ALTERNATION_RE.sub("", text)
    text = TRAILING_DASH_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" ,;-")


def _normalize_hyphens(s: str) -> str:
    """Convert hyphens to spaces for matching purposes — `extra-virgin olive oil`
    should be treated identically to `extra virgin olive oil`."""
    return re.sub(r"-", " ", s)


def _find_identity_phrase(text: str) -> str | None:
    """Return the longest Bucket 3 identity phrase present in the text.
    Match must be a contiguous substring. Hyphen-insensitive."""
    text_norm = _normalize_hyphens(text.lower())
    best = None
    best_len = 0
    for phrase in BUCKET_3_IDENTITY_PHRASES:
        phrase_norm = _normalize_hyphens(phrase)
        if phrase_norm in text_norm:
            if len(phrase_norm) > best_len:
                best = phrase  # return original (with hyphens) for canonical preservation
                best_len = len(phrase_norm)
    return best


def _bucket_token(tok: str) -> tuple[str, str]:
    """Classify a token. Returns (bucket_name, value).
    bucket_name ∈ {claim, form, processing, noise, core}.
    For 'claim', value is the canonical claim flag.
    For others, value is the original token (lowercased).
    """
    t = tok.lower().strip()
    if not t:
        return ("noise", "")
    if t in BUCKET_1_PREFERENCE_FACETS:
        return ("claim", BUCKET_1_PREFERENCE_FACETS[t])
    if t in BUCKET_2_CULINARY_FORM:
        return ("form", t)
    if t in BUCKET_2_CULINARY_PROCESSING:
        return ("processing", t)
    if t in BUCKET_2_NOISE:
        return ("noise", t)
    return ("core", t)


def normalize_ingredient(text: str) -> Normalized:
    if not text:
        return Normalized("", "", [], [], [], None, "")
    original = text
    # 1. Pull quantity + parens
    text, raw_qty = _strip_quantity_and_parens(text)
    # 1.5. Resolve "X or Y" alternations — keep first option only
    text = _resolve_alternation(text)
    # 2. Synonym replacement
    text = apply_synonyms(text)
    # 3. Identity phrase detection (Bucket 3 — preserve all phrase tokens)
    identity = _find_identity_phrase(text)
    # 4. Multi-word Bucket 1 phrases — sub them out as claims, BUT
    # don't strip tokens that are part of the Bucket 3 identity phrase
    # ("extra-virgin" is Bucket 1, but inside "extra virgin olive oil"
    # which is Bucket 3 — Bucket 3 wins).
    user_claims: list[str] = []
    multi_word_b1 = sorted(
        (k for k in BUCKET_1_PREFERENCE_FACETS if " " in k or "-" in k),
        key=lambda x: -len(x),
    )
    text_lower = text.lower()
    identity_lower = _normalize_hyphens(identity).lower() if identity else ""
    for phrase in multi_word_b1:
        phrase_norm = _normalize_hyphens(phrase)
        # Skip if this Bucket 1 phrase's tokens overlap the Bucket 3 phrase
        if identity_lower and phrase_norm in identity_lower:
            continue
        if phrase in text_lower:
            user_claims.append(BUCKET_1_PREFERENCE_FACETS[phrase])
            text_lower = text_lower.replace(phrase, " ")
    text = re.sub(r"\s+", " ", text_lower).strip(" ,;-")
    # 4b. Tokenize the working text and figure out which tokens belong to the
    # Bucket 3 identity phrase. Those tokens MUST be preserved in canonical
    # regardless of what bucket they'd otherwise fall into ("smoked paprika":
    # "smoked" would normally be Bucket 2 processing, but as part of the
    # identity phrase it stays in canonical). Hyphen-insensitive matching:
    # tokens are compared by their hyphen-stripped form.
    def _strip_hyphen(tok: str) -> str:
        return tok.replace("-", "").replace(" ", "")

    raw_tokens = re.findall(r"[a-z0-9'\-]+", text)
    tokens = [t.replace("-", " ") for t in raw_tokens]  # split hyphen-words
    # flatten back to single-word tokens
    flat_tokens: list[str] = []
    for t in tokens:
        flat_tokens.extend(t.split())
    tokens = flat_tokens
    identity_token_indices: set[int] = set()
    if identity:
        ident_tokens_raw = re.findall(r"[a-z0-9'\-]+", _normalize_hyphens(identity))
        ident_tokens: list[str] = []
        for t in ident_tokens_raw:
            ident_tokens.extend(t.split())
        for i in range(len(tokens) - len(ident_tokens) + 1):
            if tokens[i:i + len(ident_tokens)] == ident_tokens:
                identity_token_indices = set(range(i, i + len(ident_tokens)))
                break
    # 5. Walk tokens — bucket each. Tokens inside the identity phrase always
    # go to core (preserved). Tokens outside get classified normally.
    form_facets: list[str] = []
    processing_facets: list[str] = []
    core_tokens: list[str] = []
    for idx, tok in enumerate(tokens):
        if idx in identity_token_indices:
            core_tokens.append(tok)
            continue
        bucket, value = _bucket_token(tok)
        if bucket == "claim":
            user_claims.append(value)
        elif bucket == "form":
            form_facets.append(value)
        elif bucket == "processing":
            processing_facets.append(value)
        elif bucket == "noise":
            pass  # drop
        else:
            core_tokens.append(value)
    # 6. Canonical = all preserved core tokens (identity-phrase tokens included)
    canonical_text = " ".join(core_tokens).strip()
    # Dedupe claims and facets
    user_claims = sorted(set(user_claims))
    form_facets = sorted(set(form_facets))
    processing_facets = sorted(set(processing_facets))
    return Normalized(
        original=original,
        canonical_text=canonical_text,
        user_claims=user_claims,
        form_facets=form_facets,
        processing_facets=processing_facets,
        identity_phrase=identity,
        raw_quantity=raw_qty,
    )


# Quick CLI smoke test
if __name__ == "__main__":
    tests = [
        "1 cup fat-free organic mayonnaise",
        "2 tbsp extra virgin olive oil",
        "smoked paprika",
        "evaporated milk",
        "boneless skinless chicken breast",
        "free-range eggs",
        "raw lobster meat",
        "frozen assorted vegetables",
        "ground cinnamon",
        "drained canned tomatoes",
        "1/2 cup whole-grain bread crumbs, toasted",
        "8 ounces dark chocolate, chopped",
        "fresh thyme",
        "kaffir lime leaves",
        "low-sodium soy sauce",
        "'00' strong flour",
        "100% fruit pectin",
        "Pillsbury crescent roll dough",
        "Greek yogurt",
        "ripe bananas",
        "orange rind",
        "ice cubes",
    ]
    for t in tests:
        r = normalize_ingredient(t)
        print(f"\n  {t!r}")
        print(f"    canonical: {r.canonical_text!r}")
        if r.identity_phrase:    print(f"    identity:  {r.identity_phrase!r}")
        if r.user_claims:        print(f"    claims:    {r.user_claims}")
        if r.form_facets:        print(f"    form:      {r.form_facets}")
        if r.processing_facets:  print(f"    processing:{r.processing_facets}")
        if r.raw_quantity:       print(f"    qty:       {r.raw_quantity!r}")
