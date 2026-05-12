"""Recipe ingredient text synonym map — collapses synonyms to one canonical
form before adjective bucketing runs.

Single source of truth: the LEFT side is what recipe authors write; the RIGHT
side is the canonical form. Applied via word-boundary regex on the ingredient
text BEFORE any other normalization step.

Also handles accent stripping (é→e, ñ→n, ü→u, etc.) so accented variants
match their plain-ASCII forms in Bucket 3.
"""
import re
import unicodedata


def _strip_accents(s: str) -> str:
    """Map é→e, ñ→n, ü→u, etc. without dropping the underlying letter."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if not unicodedata.combining(c)
    )

# Direct text replacements (word-boundary, case-insensitive).
# Order matters: longer multi-word patterns first to avoid partial matches.
SYNONYM_PAIRS: list[tuple[str, str]] = [
    # Citrus zest/peel/rind — the user specifically called this out
    (r"\borange rind\b",  "orange peel"),
    (r"\blemon rind\b",   "lemon peel"),
    (r"\blime rind\b",    "lime peel"),
    (r"\borange zest\b",  "orange peel"),  # zest and peel are essentially the same culinary thing
    (r"\blemon zest\b",   "lemon peel"),
    (r"\blime zest\b",    "lime peel"),

    # Ice variants (collapse to "ice")
    (r"\bice cubes?\b",   "ice"),
    (r"\bcrushed ice\b",  "ice"),
    (r"\bcracked ice\b",  "ice"),

    # Egg variants — most surface differences map to "eggs"
    (r"\b(?:large|medium|small|xl|extra[- ]large|jumbo)\s+eggs?\b", "eggs"),
    (r"\bwhole eggs?\b",  "eggs"),
    (r"\bfresh eggs?\b",  "eggs"),
    (r"\braw eggs?\b",    "eggs"),
    (r"\begg yolk\b",     "egg yolks"),  # singular → plural canonical
    (r"\begg white\b",    "egg whites"),
    (r"\bhard[- ]?boiled eggs?\b",   "hard-boiled eggs"),
    (r"\bsoft[- ]?boiled eggs?\b",   "soft-boiled eggs"),
    (r"\bscrambled eggs?\b",         "scrambled eggs"),
    (r"\bpoached eggs?\b",           "poached eggs"),

    # Egg products that are functionally the same
    (r"\begg replacer\b",         "egg substitute"),
    (r"\bvegan egg substitute\b", "egg substitute"),

    # Brand/marketing prefix stripping (when the brand is irrelevant to identity)
    (r"\bpillsbury\s+",       ""),  # Pillsbury Crescent Roll Dough → Crescent Roll Dough
    (r"\bkraft\s+",           ""),
    (r"\bgreat value\s+",     ""),
    (r"\bkroger\s+",          ""),
    (r"\bbetty crocker\s+",   ""),
    (r"\bgeneral mills\s+",   ""),

    # Common spelling variants
    (r"\bcrème\b",        "creme"),  # accent-stripping for crème de X
    (r"\bcafé\b",         "cafe"),
    (r"\bjalapeño\b",     "jalapeno"),
    (r"\bpurée\b",        "puree"),
    (r"\bfilet\b",        "fillet"),  # filet → fillet (American spelling)

    # Common chicken variants — collapse to canonical
    (r"\bboneless,?\s*skinless\s+chicken\s+breasts?\b",
        "boneless skinless chicken breast"),
    (r"\bskinless,?\s*boneless\s+chicken\s+breasts?\b",
        "boneless skinless chicken breast"),

    # Plural of common patterns
    (r"\b'00'\s+strong\s+flours?\b", "strong flour"),  # collapse '00'
    (r"\b00\s+strong\s+flours?\b",   "strong flour"),

    # Common typos / abbreviations
    (r"\bw/\b",           "with"),
    (r"\bn'\b",           "and"),
    (r"\&",               "and"),
]

_COMPILED = [(re.compile(p, re.I), r) for p, r in SYNONYM_PAIRS]


def apply_synonyms(text: str) -> str:
    """Apply all synonym substitutions to the ingredient text. Idempotent
    (running twice produces the same result). Accent-stripping runs first
    so `filé` matches `file`, `crème` matches `creme`, `jalapeño` → `jalapeno`."""
    if not text:
        return text
    out = _strip_accents(text.lower())
    for pat, repl in _COMPILED:
        out = pat.sub(repl, out)
    out = re.sub(r"\s+", " ", out).strip()
    return out
