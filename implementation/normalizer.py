"""Canonical-item normalizer.

Mirrors Hestia's ingredient_matcher mechanism
(/Users/jamiebarton/Desktop/Hestia/api/app/services/ingredient_matcher.py):

  1. Normalize text       (lowercase, hyphens -> spaces, strip non-alnum, collapse ws)
  2. Candidate generation (full, stemmed, strip descriptors, stripped+stemmed, tail-n)
  3. Exact alias lookup   (canonical_items + canonical_aliases)
  4. Longest-substring match over canonical keys (longest wins)
  5. Fail closed -> None  (caller routes to nutrition_unknown)

No regex head-noun fallback, no last-word-wins. Compositional phrases
('peanut butter', 'coffee beans', 'butter peas') are distinguished because
canonical keys are stored atomically and the longest match beats shorter
substring matches.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANONICAL_ITEMS_CSV = ROOT / 'canonical_items.csv'
CANONICAL_ALIASES_CSV = ROOT / 'canonical_aliases.csv'  # optional, may not exist yet

_WS = re.compile(r'\s+')
_NON_ALNUM = re.compile(r'[^a-z0-9\s]')

# Hestia's BASE_FOOD_STRIP_WORDS — descriptors removed during candidate generation
# These are prep/form words that don't change what the food IS.
STRIP_WORDS = frozenset({
    'boneless', 'diced', 'extra', 'fat-free', 'fresh', 'frozen', 'ground',
    'large', 'lean', 'less', 'light', 'low', 'medium', 'minced', 'part',
    'raw', 'reduced', 'shredded', 'skinless', 'sliced', 'small', 'thinly',
    'virgin', 'whole', 'chopped', 'grated', 'crushed', 'thick', 'thin',
    'organic', 'natural', 'crunchy', 'smooth', 'creamy',
    'softened', 'melted', 'warm', 'cold', 'hot', 'room temperature',
    'unsalted', 'salted', 'unsweetened', 'sweetened',
})

# Hestia's FORM_SPECIFIC_WORDS — applied during alias index building
# (drop trailing form words when generating aliases)
FORM_SPECIFIC_WORDS = frozenset({
    'canned', 'frozen', 'cooked', 'sauteed', 'boiled', 'baked', 'roasted',
    'dehydrated', 'dried', 'freeze-dried', 'condensed', 'toasted',
    'steamed', 'stewed', 'fried',
})

# Plural folding: common -es/-s stripping tried anchored (only if singular is canonical)
def _singularize(word: str) -> str | None:
    if len(word) < 3: return None
    if word.endswith('ies') and len(word) > 4:
        return word[:-3] + 'y'
    if word.endswith('ches') or word.endswith('shes') or word.endswith('xes') or word.endswith('sses'):
        return word[:-2]
    if word.endswith('es') and len(word) > 4 and word[-3] not in 'aeiou':
        return word[:-2]
    if word.endswith('s') and not word.endswith('ss') and len(word) > 3:
        return word[:-1]
    return None


def _normalize_text(s: str) -> str:
    """Hestia's _normalize_lookup_text: lowercase, hyphens->spaces,
    strip non-alnum, collapse whitespace."""
    if not s: return ''
    s = s.lower()
    s = s.replace('-', ' ').replace('_', ' ').replace('/', ' ')
    s = _NON_ALNUM.sub(' ', s)
    s = _WS.sub(' ', s.strip())
    return s


@dataclass
class NormalizerResult:
    canonical: str | None
    confidence: str  # 'exact' | 'alias' | 'stripped' | 'substring' | 'stemmed' | 'tail'
    matched_candidate: str
    path: list[str]


class Normalizer:
    """Loads canonical_items.csv + canonical_aliases.csv and provides
    normalize(text) -> NormalizerResult."""

    def __init__(self,
                 items_csv: Path = CANONICAL_ITEMS_CSV,
                 aliases_csv: Path = CANONICAL_ALIASES_CSV):
        self._canonical: dict[str, str] = {}            # normalized_name -> canonical_name (self-map)
        self._alias_to_canonical: dict[str, str] = {}   # surface -> canonical_name
        self._canonical_sorted_by_len: list[tuple[int, str]] = []
        self._load(items_csv, aliases_csv)

    def _load(self, items_csv: Path, aliases_csv: Path) -> None:
        if items_csv.exists():
            with items_csv.open(newline='') as f:
                for row in csv.DictReader(f):
                    cn = _normalize_text(row['canonical_name'])
                    if not cn: continue
                    self._canonical[cn] = cn
                    # Auto-generate form-stripped aliases
                    tokens = cn.split()
                    while tokens and tokens[-1] in FORM_SPECIFIC_WORDS:
                        tokens = tokens[:-1]
                        stripped = ' '.join(tokens)
                        if stripped and stripped not in self._alias_to_canonical:
                            self._alias_to_canonical[stripped] = cn
        if aliases_csv.exists():
            with aliases_csv.open(newline='') as f:
                for row in csv.DictReader(f):
                    surface = _normalize_text(row.get('surface', ''))
                    canonical = _normalize_text(row.get('canonical_name', ''))
                    if surface and canonical:
                        self._alias_to_canonical[surface] = canonical
        # Precompute length-sorted canonical keys (longest first) for substring match
        self._canonical_sorted_by_len = sorted(
            ((len(k), k) for k in self._canonical),
            key=lambda x: -x[0]
        )

    def _generate_candidates(self, text: str) -> list[tuple[str, str]]:
        """Generate (candidate, confidence_label) tuples in priority order.

        Conservative by design: no tail-unigram, no tail-bigram. A novel
        multi-word phrase without a canonical hit after stripping and
        stemming returns None (fail closed) and lets the layered resolver
        fall through to reviewed anchors. This prevents compositional
        errors like 'garlic in oil -> oil' or 'butter peas -> butter'.
        """
        if not text: return []
        t = _normalize_text(text)
        out: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add(c: str, label: str) -> None:
            if c and c not in seen:
                out.append((c, label)); seen.add(c)

        # 1. Full normalized input
        add(t, 'exact')

        tokens = t.split()

        # 2. Plural-fold last token on full input
        if tokens:
            sing = _singularize(tokens[-1])
            if sing:
                add(' '.join(tokens[:-1] + [sing]), 'stemmed')

        # 3. STRIP_WORDS removed (descriptor stripping)
        stripped = [tk for tk in tokens if tk not in STRIP_WORDS]
        if stripped and stripped != tokens:
            add(' '.join(stripped), 'stripped')
            # 4. Stripped + stemmed
            sing = _singularize(stripped[-1])
            if sing:
                add(' '.join(stripped[:-1] + [sing]), 'stripped_stemmed')

        # 5. FORM_SPECIFIC_WORDS trimmed from the tail
        base = list(stripped) if stripped else list(tokens)
        while base and base[-1] in FORM_SPECIFIC_WORDS:
            base = base[:-1]
        if base and base != (stripped or tokens):
            add(' '.join(base), 'form_stripped')
            sing = _singularize(base[-1])
            if sing:
                add(' '.join(base[:-1] + [sing]), 'form_stripped_stemmed')

        # 6. Final fallback: just the head token if it's the only meaningful word
        #    ONLY if stripping reduced to a single token (prevents "butter peas -> butter")
        if len(stripped) == 1:
            add(stripped[0], 'single_head')

        return out

    def _exact_lookup(self, candidate: str) -> str | None:
        if candidate in self._canonical:
            return self._canonical[candidate]
        if candidate in self._alias_to_canonical:
            return self._alias_to_canonical[candidate]
        return None

    def normalize(self, text: str) -> NormalizerResult:
        """Returns NormalizerResult with canonical or None.

        Fail-closed discipline: every candidate must exact-match a canonical
        key or alias. No substring fallback, no last-word regex. If no
        candidate hits, returns None — the layered resolver picks it up.
        """
        path: list[str] = []
        if not text:
            return NormalizerResult(None, 'empty', '', path)
        t = _normalize_text(text)
        path.append(f"normalized={t!r}")
        cands = self._generate_candidates(text)
        path.append(f"candidates={[c for c,_ in cands]}")

        for c, label in cands:
            hit = self._exact_lookup(c)
            if hit:
                return NormalizerResult(hit, label, c,
                                        path + [f"{label}: {c!r} -> {hit!r}"])
        return NormalizerResult(None, 'unknown', '', path + ['no_match'])


# Module-level convenience instance (lazy).
_DEFAULT: Normalizer | None = None

def get_normalizer() -> Normalizer:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Normalizer()
    return _DEFAULT


def normalize_to_canonical(text: str) -> str | None:
    return get_normalizer().normalize(text).canonical
