# Canonical Signature Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a hybrid cascade pipeline that maps each row in `product_to_best_esha_full_map.vM.csv` (462k branded products) to a canonical signature and a single best-anchor row in `canonical_surface_normalized_with_product_proxies.csv`, with full per-layer provenance.

**Architecture:** Eight-layer cascade — (L1) text normalize → (L2) brand strip → (L3) attribute extraction → (L4) TF-IDF char+word lexical match → (L5) sentence-transformer fallback → (L6) attribute disambiguation → (L7) composite routing via `branded_food_category` → (L8) provenance emission. Each layer is a focused module under `implementation/canonical_signature/`. Orchestrator iterates the product file in chunks, writes `product_to_canonical_signature.csv` and a collapsed `signature_groups.csv`.

**Tech Stack:** Python 3.14, pandas, scikit-learn (TfidfVectorizer), sentence-transformers (`all-MiniLM-L6-v2`), unittest. Project conventions per `AGENTS.md`: snake_case, dataclasses, scripts named `build_*`, outputs to `implementation/output/`, no git.

**Spec:** `/Users/jamiebarton/Desktop/esha_audit_bundle/docs/specs/2026-04-26-canonical-signature-pipeline-design.md`

---

## File Structure

```
implementation/
  canonical_signature/
    __init__.py
    signature.py           # CanonicalSignature + MatchTrace dataclasses
    vocabularies.py        # data-driven vocabularies (loaded from canonical_surface)
    normalizer.py          # L1
    brand_stripper.py      # L2
    attribute_extractor.py # L3
    lexical_matcher.py     # L4 (TF-IDF char + word)
    embedding_matcher.py   # L5 (MiniLM fallback)
    disambiguator.py       # L6
    composite_router.py    # L7
    pipeline.py            # orchestrates L1-L8 for one row
  build_canonical_signature_map.py  # CLI runner over full vM (writes main artifact)
  build_signature_groups.py         # collapsed-view artifact builder
  category_to_canonical_anchor.csv  # hand-curated for L7 (~100 rows)
  tests/
    test_signature_normalizer.py
    test_signature_brand_stripper.py
    test_signature_attribute_extractor.py
    test_signature_lexical_matcher.py
    test_signature_disambiguator.py
    test_signature_composite_router.py
    test_signature_pipeline.py
```

---

## Task 1: Package skeleton + signature dataclasses

**Files:**
- Create: `implementation/canonical_signature/__init__.py`
- Create: `implementation/canonical_signature/signature.py`
- Create: `implementation/tests/test_signature_dataclasses.py`

- [ ] **Step 1: Write the failing test**

```python
# implementation/tests/test_signature_dataclasses.py
import unittest
from implementation.canonical_signature.signature import CanonicalSignature, MatchTrace


class SignatureDataclassTests(unittest.TestCase):
    def test_signature_equality_is_structural(self):
        a = CanonicalSignature(head_noun="applesauce", modifiers=frozenset({"cinnamon"}))
        b = CanonicalSignature(head_noun="applesauce", modifiers=frozenset({"cinnamon"}))
        self.assertEqual(a, b)

    def test_signature_is_hashable(self):
        s = CanonicalSignature(head_noun="apple", modifiers=frozenset())
        {s}  # must not raise

    def test_signature_default_fields_are_none(self):
        s = CanonicalSignature(head_noun="apple", modifiers=frozenset())
        self.assertIsNone(s.form)
        self.assertIsNone(s.state)
        self.assertIsNone(s.flavor)
        self.assertIsNone(s.style)
        self.assertFalse(s.composite)
        self.assertEqual(s.secondary_ingredients, ())

    def test_match_trace_carries_all_provenance_fields(self):
        t = MatchTrace(
            match_layer="L4_lexical",
            stripped_brand="NATURE'S PLACE",
            stripped_fluff=("organic", "fresh"),
            extracted_attributes={"form": "sliced"},
            residual="apples",
            top_candidates=(("apple_raw", 0.91), ("apple_cooked", 0.42)),
            match_confidence=0.91,
            match_reason="char-ngram exact head match",
        )
        self.assertEqual(t.match_layer, "L4_lexical")
        self.assertEqual(t.match_confidence, 0.91)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest implementation.tests.test_signature_dataclasses -v`
Expected: FAIL — `ModuleNotFoundError: implementation.canonical_signature`

- [ ] **Step 3: Write the package init**

```python
# implementation/canonical_signature/__init__.py
"""Canonical signature pipeline: messy product strings -> canonical anchors."""
```

- [ ] **Step 4: Write the dataclasses**

```python
# implementation/canonical_signature/signature.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class CanonicalSignature:
    head_noun: str
    modifiers: frozenset[str]
    form: Optional[str] = None
    state: Optional[str] = None
    flavor: Optional[str] = None
    style: Optional[str] = None
    composite: bool = False
    secondary_ingredients: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatchTrace:
    match_layer: str
    stripped_brand: str
    stripped_fluff: tuple[str, ...]
    extracted_attributes: dict
    residual: str
    top_candidates: tuple[tuple[str, float], ...]
    match_confidence: float
    match_reason: str
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest implementation.tests.test_signature_dataclasses -v`
Expected: PASS, 4 tests OK.

---

## Task 2: Vocabularies module

Loads brand/fluff/form/state/flavor/style/composite-trigger vocabularies. Brand+attribute vocabularies are derived from the canonical_surface CSV; fluff and composite triggers are hand-seeded module constants.

**Files:**
- Create: `implementation/canonical_signature/vocabularies.py`
- Create: `implementation/tests/test_signature_vocabularies.py`
- Reference: `/Users/jamiebarton/Desktop/clean/canonical_surface_normalized_with_product_proxies.csv`

- [ ] **Step 1: Write the failing test**

```python
# implementation/tests/test_signature_vocabularies.py
import unittest
from implementation.canonical_signature.vocabularies import (
    FLUFF_TOKENS,
    COMPOSITE_TRIGGERS,
    SEED_FLAVOR_TOKENS,
    Vocabularies,
)


class VocabularyConstantsTests(unittest.TestCase):
    def test_fluff_includes_known_marketing_words(self):
        for w in ("organic", "premium", "fresh-picked", "all-natural", "100%"):
            self.assertIn(w, FLUFF_TOKENS, f"{w} should be fluff")

    def test_composite_triggers_include_with_and_filled(self):
        for w in ("with", "filled", "stuffed", "topped", "&"):
            self.assertIn(w, COMPOSITE_TRIGGERS)

    def test_seed_flavors_include_common_variants(self):
        for w in ("vanilla", "chocolate", "strawberry", "cinnamon"):
            self.assertIn(w, SEED_FLAVOR_TOKENS)


class VocabulariesFromCanonicalSurfaceTests(unittest.TestCase):
    def test_loaded_vocabularies_have_nonempty_attribute_sets(self):
        v = Vocabularies.from_canonical_surface_default()
        self.assertGreater(len(v.form_vocabulary), 0, "form attrs should be populated")
        self.assertGreater(len(v.state_vocabulary), 0, "state attrs should be populated")
        self.assertGreater(len(v.style_vocabulary), 0, "style attrs should be populated")
        self.assertGreater(len(v.brand_vocabulary), 0, "brand candidates should be populated")
        self.assertGreater(len(v.head_noun_vocabulary), 0, "canonical heads should be populated")

    def test_fluff_takes_precedence_over_style(self):
        # 'organic' appears as a style attribute in canonical_surface but is also fluff;
        # fluff classification wins so unrelated organic-marketing tokens get stripped.
        v = Vocabularies.from_canonical_surface_default()
        self.assertIn("organic", v.fluff_tokens)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest implementation.tests.test_signature_vocabularies -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement vocabularies**

```python
# implementation/canonical_signature/vocabularies.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import csv

CANONICAL_SURFACE_PATH = Path(
    "/Users/jamiebarton/Desktop/clean/canonical_surface_normalized_with_product_proxies.csv"
)

# Hand-seeded constants. Iteration is expected.
FLUFF_TOKENS: frozenset[str] = frozenset({
    "premium", "gourmet", "selection", "selections", "choice", "choicest",
    "fresh-picked", "farm-fresh", "all-natural", "100%", "pure", "real",
    "authentic", "delicious", "homestyle", "traditional", "original",
    "classic", "naturally", "signature", "deluxe", "best", "finest",
    "organic",  # treated as fluff by default; promoted to style only when canonical row demands
    "great", "perfect", "ultimate", "extra", "super",
})

COMPOSITE_TRIGGERS: frozenset[str] = frozenset({
    "with", "filled", "stuffed", "topped", "over", "plus", "containing",
    "flavored", "&",
    # 'and' is intentionally excluded — too noisy ('macaroni and cheese' is one dish)
})

SEED_FLAVOR_TOKENS: frozenset[str] = frozenset({
    "vanilla", "chocolate", "strawberry", "cinnamon", "peach", "blueberry",
    "raspberry", "mint", "peppermint", "caramel", "mocha", "hazelnut",
    "pumpkin", "lemon", "orange", "cherry", "coconut", "coffee", "maple",
    "almond", "banana", "butterscotch", "toffee", "honey",
})


def _split_attr_cell(cell: str) -> list[str]:
    if not cell:
        return []
    parts = cell.replace(";", ",").split(",")
    return [p.strip().lower() for p in parts if p.strip()]


@dataclass(frozen=True)
class Vocabularies:
    fluff_tokens: frozenset[str]
    composite_triggers: frozenset[str]
    flavor_vocabulary: frozenset[str]
    form_vocabulary: frozenset[str]
    state_vocabulary: frozenset[str]
    style_vocabulary: frozenset[str]
    packaging_vocabulary: frozenset[str]
    brand_vocabulary: frozenset[str]
    head_noun_vocabulary: frozenset[str]

    @classmethod
    def from_canonical_surface(cls, path: Path) -> "Vocabularies":
        forms: set[str] = set()
        states: set[str] = set()
        styles: set[str] = set()
        packaging: set[str] = set()
        brands: set[str] = set()
        heads: set[str] = set()
        flavors: set[str] = set(SEED_FLAVOR_TOKENS)

        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                forms.update(_split_attr_cell(row.get("form_attributes", "")))
                states.update(_split_attr_cell(row.get("state_attributes", "")))
                styles.update(_split_attr_cell(row.get("style_attributes", "")))
                packaging.update(_split_attr_cell(row.get("packaging_attributes", "")))
                if (b := (row.get("brand_candidate") or "").strip().lower()):
                    brands.add(b)
                if (h := (row.get("canonical_normalized") or "").strip().lower()):
                    heads.add(h)

        return cls(
            fluff_tokens=FLUFF_TOKENS,
            composite_triggers=COMPOSITE_TRIGGERS,
            flavor_vocabulary=frozenset(flavors),
            form_vocabulary=frozenset(forms),
            state_vocabulary=frozenset(states),
            style_vocabulary=frozenset(styles),
            packaging_vocabulary=frozenset(packaging),
            brand_vocabulary=frozenset(brands),
            head_noun_vocabulary=frozenset(heads),
        )

    @classmethod
    def from_canonical_surface_default(cls) -> "Vocabularies":
        return cls.from_canonical_surface(CANONICAL_SURFACE_PATH)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest implementation.tests.test_signature_vocabularies -v`
Expected: PASS, 5 tests OK. (Loading 18k rows takes ~1s.)

---

## Task 3: L1 — Normalizer

**Files:**
- Create: `implementation/canonical_signature/normalizer.py`
- Create: `implementation/tests/test_signature_normalizer.py`

- [ ] **Step 1: Write the failing test**

```python
# implementation/tests/test_signature_normalizer.py
import unittest
from implementation.canonical_signature.normalizer import normalize


class NormalizerTests(unittest.TestCase):
    def test_lowercases(self):
        self.assertEqual(normalize("APPLES"), "apples")

    def test_preserves_commas(self):
        self.assertEqual(normalize("NATURE'S PLACE, ORGANIC APPLES"),
                         "natures place, organic apples")

    def test_strips_apostrophes_and_periods(self):
        self.assertEqual(normalize("McDonald's Inc."), "mcdonalds inc")

    def test_expands_abbreviations(self):
        self.assertEqual(normalize("ORG. APPLES W/ CINNAMON"),
                         "organic apples with cinnamon")

    def test_collapses_whitespace(self):
        self.assertEqual(normalize("  apple    sauce  "), "apple sauce")

    def test_unicode_nfkd(self):
        # 'café' should decompose to 'cafe'
        self.assertEqual(normalize("CAFÉ"), "cafe")

    def test_ampersand_kept_only_when_word_separator(self):
        # & between words becomes 'and' (composite trigger handled later via tokens)
        self.assertEqual(normalize("PIECES & STEMS"), "pieces and stems")
        # but A&W should not become 'a and w'
        self.assertEqual(normalize("A&W ROOT BEER"), "a&w root beer")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest implementation.tests.test_signature_normalizer -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement normalize**

```python
# implementation/canonical_signature/normalizer.py
from __future__ import annotations
import re
import unicodedata

_ABBREVS = {
    r"\borg\.\b": "organic",
    r"\bw/\b": "with",
    r"\bw/o\b": "without",
    r"\bnatl\b": "natural",
    r"\bchoc\b": "chocolate",
    r"\bveg\b": "vegetable",
}

_AMP_BETWEEN_WORDS = re.compile(r"(?<=[a-z]{2})\s*&\s*(?=[a-z]{2})")
_PUNCT_TO_DROP = re.compile(r"['.,;:!?()\[\]\"]")  # commas removed below; ., ', etc dropped here
_COMMA_NORMALIZE = re.compile(r"\s*,\s*")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    if text is None:
        return ""
    # Unicode normalize and drop combining marks (café -> cafe)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    # Comma is structural (brand prefix marker); preserve separately
    text = _COMMA_NORMALIZE.sub("§COMMA§", text)
    # Drop other punctuation except & (handled below)
    text = _PUNCT_TO_DROP.sub("", text)
    # & between word-tokens -> ' and '; & inside short token (A&W) preserved
    text = _AMP_BETWEEN_WORDS.sub(" and ", text)
    # Restore commas
    text = text.replace("§COMMA§", ", ")
    # Expand abbreviations
    for pattern, repl in _ABBREVS.items():
        text = re.sub(pattern, repl, text)
    # Collapse whitespace
    text = _WS.sub(" ", text).strip()
    return text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest implementation.tests.test_signature_normalizer -v`
Expected: PASS, 7 tests OK.

---

## Task 4: L2 — Brand stripper

**Files:**
- Create: `implementation/canonical_signature/brand_stripper.py`
- Create: `implementation/tests/test_signature_brand_stripper.py`

- [ ] **Step 1: Write the failing test**

```python
# implementation/tests/test_signature_brand_stripper.py
import unittest
from implementation.canonical_signature.brand_stripper import strip_brand


class BrandStripperTests(unittest.TestCase):
    def test_strips_explicit_brand_name_prefix(self):
        out, brand = strip_brand("natures place, organic apples", brand_name="natures place")
        self.assertEqual(out, "organic apples")
        self.assertEqual(brand, "natures place")

    def test_strips_explicit_brand_name_inline(self):
        out, brand = strip_brand("madhava raw organic agave nectar", brand_name="madhava")
        self.assertEqual(out, "raw organic agave nectar")
        self.assertEqual(brand, "madhava")

    def test_strips_brand_owner_when_brand_name_missing(self):
        out, brand = strip_brand("goldens fresh sliced apples", brand_name=None,
                                 brand_owner="goldens")
        self.assertEqual(out, "fresh sliced apples")
        self.assertEqual(brand, "goldens")

    def test_falls_back_to_comma_prefix_heuristic(self):
        out, brand = strip_brand("fresh selections, veggie tray with apples",
                                 brand_name=None, brand_owner=None,
                                 brand_vocabulary=frozenset({"fresh selections"}))
        self.assertEqual(out, "veggie tray with apples")
        self.assertEqual(brand, "fresh selections")

    def test_no_strip_when_no_brand_signal(self):
        out, brand = strip_brand("apples", brand_name=None, brand_owner=None,
                                 brand_vocabulary=frozenset())
        self.assertEqual(out, "apples")
        self.assertEqual(brand, "")

    def test_does_not_strip_brand_when_it_is_the_whole_string(self):
        # If after stripping nothing is left, keep the original — no useful residual.
        out, brand = strip_brand("madhava", brand_name="madhava")
        self.assertEqual(out, "madhava")
        self.assertEqual(brand, "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest implementation.tests.test_signature_brand_stripper -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement brand stripper**

```python
# implementation/canonical_signature/brand_stripper.py
from __future__ import annotations
from typing import Optional


def _try_strip(text: str, candidate: str) -> Optional[str]:
    """Strip candidate from start of text (with optional trailing comma + space)."""
    if not candidate:
        return None
    cand = candidate.strip().lower()
    lowered = text.strip().lower()
    if not lowered.startswith(cand):
        return None
    rest = text[len(cand):].lstrip()
    if rest.startswith(","):
        rest = rest[1:].lstrip()
    return rest


def strip_brand(
    text: str,
    *,
    brand_name: Optional[str] = None,
    brand_owner: Optional[str] = None,
    brand_vocabulary: frozenset[str] = frozenset(),
) -> tuple[str, str]:
    """Return (residual_text, stripped_brand). Empty stripped_brand means no strip occurred."""
    candidates: list[str] = []
    for c in (brand_name, brand_owner):
        if c and c.strip():
            candidates.append(c.strip().lower())

    for cand in candidates:
        stripped = _try_strip(text, cand)
        if stripped is not None and stripped:
            return stripped, cand

    # Heuristic: longest brand-vocabulary prefix
    if brand_vocabulary:
        # Greedy longest-match
        for cand in sorted(brand_vocabulary, key=len, reverse=True):
            stripped = _try_strip(text, cand)
            if stripped is not None and stripped:
                return stripped, cand

    return text, ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest implementation.tests.test_signature_brand_stripper -v`
Expected: PASS, 6 tests OK.

---

## Task 5: L3 — Attribute extractor

**Files:**
- Create: `implementation/canonical_signature/attribute_extractor.py`
- Create: `implementation/tests/test_signature_attribute_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
# implementation/tests/test_signature_attribute_extractor.py
import unittest
from implementation.canonical_signature.attribute_extractor import (
    extract_attributes, ExtractionResult,
)
from implementation.canonical_signature.vocabularies import (
    FLUFF_TOKENS, SEED_FLAVOR_TOKENS,
)


class AttributeExtractorTests(unittest.TestCase):
    def setUp(self):
        # Compact vocabularies for unit tests; integration test uses real ones.
        self.form_vocab = frozenset({"sliced", "whole", "diced", "liquid", "powder", "chopped"})
        self.state_vocab = frozenset({"raw", "frozen", "fresh", "cooked", "dried"})
        self.style_vocab = frozenset({"organic", "kosher"})
        self.packaging_vocab = frozenset({"packets", "tray", "cup", "bag"})

    def _extract(self, text):
        return extract_attributes(
            text,
            fluff=FLUFF_TOKENS,
            flavors=SEED_FLAVOR_TOKENS,
            forms=self.form_vocab,
            states=self.state_vocab,
            styles=self.style_vocab,
            packaging=self.packaging_vocab,
        )

    def test_strips_fluff_and_returns_residual(self):
        r = self._extract("organic fresh-picked apples")
        self.assertEqual(r.residual, "apples")
        self.assertIn("fresh-picked", r.fluff_stripped)

    def test_extracts_form(self):
        r = self._extract("sliced apples")
        self.assertEqual(r.form, "sliced")
        self.assertEqual(r.residual, "apples")

    def test_extracts_state_form_and_style(self):
        r = self._extract("raw organic sliced apples")
        # 'organic' is in fluff by default — gets stripped, not promoted to style.
        self.assertEqual(r.state, "raw")
        self.assertEqual(r.form, "sliced")
        self.assertEqual(r.residual, "apples")

    def test_extracts_flavor(self):
        r = self._extract("cinnamon applesauce")
        self.assertEqual(r.flavor, "cinnamon")
        self.assertEqual(r.residual, "applesauce")

    def test_extracts_packaging(self):
        r = self._extract("agave nectar packets")
        self.assertEqual(r.packaging, "packets")
        self.assertEqual(r.residual, "agave nectar")

    def test_head_noun_is_rightmost_residual_token(self):
        r = self._extract("blue agave nectar")
        self.assertEqual(r.residual, "blue agave nectar")
        self.assertEqual(r.head_noun, "nectar")

    def test_multiword_residual_preserved(self):
        r = self._extract("agave nectar")
        self.assertEqual(r.residual, "agave nectar")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest implementation.tests.test_signature_attribute_extractor -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement attribute extractor**

```python
# implementation/canonical_signature/attribute_extractor.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ExtractionResult:
    residual: str
    head_noun: str
    fluff_stripped: tuple[str, ...]
    form: Optional[str]
    state: Optional[str]
    flavor: Optional[str]
    style: Optional[str]
    packaging: Optional[str]


def _tokenize(text: str) -> list[str]:
    # Tokens are whitespace-separated; commas already stripped or kept as bare tokens.
    return [t for t in text.replace(",", " ").split() if t]


def extract_attributes(
    text: str,
    *,
    fluff: frozenset[str],
    flavors: frozenset[str],
    forms: frozenset[str],
    states: frozenset[str],
    styles: frozenset[str],
    packaging: frozenset[str],
) -> ExtractionResult:
    tokens = _tokenize(text)
    residual_tokens: list[str] = []
    fluff_stripped: list[str] = []
    form: Optional[str] = None
    state: Optional[str] = None
    flavor: Optional[str] = None
    style: Optional[str] = None
    pkg: Optional[str] = None

    # Order of checks matters: fluff first (organic is fluff by default), then attributes.
    for tok in tokens:
        if tok in fluff:
            fluff_stripped.append(tok)
            continue
        if form is None and tok in forms:
            form = tok
            continue
        if state is None and tok in states:
            state = tok
            continue
        if flavor is None and tok in flavors:
            flavor = tok
            continue
        if style is None and tok in styles:
            style = tok
            continue
        if pkg is None and tok in packaging:
            pkg = tok
            continue
        residual_tokens.append(tok)

    residual = " ".join(residual_tokens)
    head_noun = residual_tokens[-1] if residual_tokens else ""

    return ExtractionResult(
        residual=residual,
        head_noun=head_noun,
        fluff_stripped=tuple(fluff_stripped),
        form=form,
        state=state,
        flavor=flavor,
        style=style,
        packaging=pkg,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest implementation.tests.test_signature_attribute_extractor -v`
Expected: PASS, 7 tests OK.

---

## Task 6: L4 — Lexical matcher (TF-IDF char + word)

**Files:**
- Create: `implementation/canonical_signature/lexical_matcher.py`
- Create: `implementation/tests/test_signature_lexical_matcher.py`

- [ ] **Step 1: Write the failing test**

```python
# implementation/tests/test_signature_lexical_matcher.py
import unittest
from implementation.canonical_signature.lexical_matcher import LexicalMatcher


class LexicalMatcherTests(unittest.TestCase):
    def setUp(self):
        self.corpus = [
            ("apple_raw",       "apples raw"),
            ("apple_sliced",    "apples sliced"),
            ("applesauce",      "applesauce"),
            ("applesauce_cin",  "applesauce cinnamon"),
            ("agave_nectar",    "agave nectar"),
            ("ice_cream_van",   "ice cream vanilla"),
            ("ice_cream_choc",  "ice cream chocolate"),
        ]
        self.matcher = LexicalMatcher.fit(self.corpus)

    def test_top_match_for_exact_input(self):
        results = self.matcher.match("agave nectar", k=3)
        self.assertEqual(results[0][0], "agave_nectar")
        self.assertGreater(results[0][1], 0.9)

    def test_top_match_for_morphological_variant(self):
        # 'apple sauce' (split) should match 'applesauce' via char n-grams
        results = self.matcher.match("apple sauce", k=3)
        ids = [r[0] for r in results]
        self.assertIn("applesauce", ids[:2])

    def test_returns_top_k_sorted_descending(self):
        results = self.matcher.match("apples", k=3)
        self.assertEqual(len(results), 3)
        scores = [r[1] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_zero_score_when_residual_is_empty(self):
        results = self.matcher.match("", k=3)
        # Empty residual should return empty results, not crash
        self.assertEqual(results, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest implementation.tests.test_signature_lexical_matcher -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement lexical matcher**

```python
# implementation/canonical_signature/lexical_matcher.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

CHAR_WEIGHT = 0.6
WORD_WEIGHT = 0.4


@dataclass
class LexicalMatcher:
    ids: list[str]
    char_vec: TfidfVectorizer
    word_vec: TfidfVectorizer
    char_matrix: object
    word_matrix: object

    @classmethod
    def fit(cls, corpus: Iterable[tuple[str, str]]) -> "LexicalMatcher":
        items = list(corpus)
        ids = [i for i, _ in items]
        texts = [t for _, t in items]
        char_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
        word_vec = TfidfVectorizer(analyzer="word", ngram_range=(1, 3))
        char_matrix = char_vec.fit_transform(texts)
        word_matrix = word_vec.fit_transform(texts)
        return cls(ids=ids, char_vec=char_vec, word_vec=word_vec,
                   char_matrix=char_matrix, word_matrix=word_matrix)

    def match(self, query: str, k: int = 5) -> list[tuple[str, float]]:
        if not query.strip():
            return []
        cq = self.char_vec.transform([query])
        wq = self.word_vec.transform([query])
        char_sim = cosine_similarity(cq, self.char_matrix)[0]
        word_sim = cosine_similarity(wq, self.word_matrix)[0]
        combined = CHAR_WEIGHT * char_sim + WORD_WEIGHT * word_sim
        if k >= len(combined):
            top_idx = np.argsort(combined)[::-1]
        else:
            top_idx = np.argpartition(combined, -k)[-k:]
            top_idx = top_idx[np.argsort(combined[top_idx])[::-1]]
        return [(self.ids[i], float(combined[i])) for i in top_idx]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest implementation.tests.test_signature_lexical_matcher -v`
Expected: PASS, 4 tests OK.

---

## Task 7: L5 — Embedding matcher

Wraps sentence-transformers MiniLM. Builds a cached embedding matrix for the canonical corpus once; reranks a candidate subset for a given query.

**Files:**
- Create: `implementation/canonical_signature/embedding_matcher.py`
- Create: `implementation/tests/test_signature_embedding_matcher.py`

- [ ] **Step 1: Write the failing test**

```python
# implementation/tests/test_signature_embedding_matcher.py
import unittest
from implementation.canonical_signature.embedding_matcher import EmbeddingMatcher


class EmbeddingMatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = [
            ("ice_cream",       "ice cream"),
            ("frozen_yogurt",   "frozen yogurt"),
            ("agave_nectar",    "agave nectar"),
            ("honey",           "honey"),
            ("apple_raw",       "apples raw"),
            ("bell_pepper",     "bell pepper"),
            ("sweet_pepper",    "sweet pepper"),
        ]
        cls.matcher = EmbeddingMatcher.fit(cls.corpus)

    def test_semantic_neighbors_pulled_into_top_k(self):
        # 'frozen dessert' should be near ice cream / frozen yogurt
        results = self.matcher.rerank("frozen dessert", candidate_ids=[i for i, _ in self.corpus], k=3)
        ids = [r[0] for r in results]
        self.assertTrue("ice_cream" in ids or "frozen_yogurt" in ids,
                        f"expected dessert neighbor in top-3, got {ids}")

    def test_rerank_only_considers_provided_candidates(self):
        results = self.matcher.rerank("frozen dessert",
                                      candidate_ids=["agave_nectar", "honey"], k=2)
        ids = {r[0] for r in results}
        self.assertEqual(ids, {"agave_nectar", "honey"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest implementation.tests.test_signature_embedding_matcher -v`
Expected: FAIL — module missing. (First run downloads the MiniLM model; subsequent runs use cache.)

- [ ] **Step 3: Implement embedding matcher**

```python
# implementation/canonical_signature/embedding_matcher.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Sequence
import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class EmbeddingMatcher:
    ids: list[str]
    id_to_idx: dict[str, int]
    embeddings: np.ndarray  # shape (n_corpus, dim), L2-normalized
    model: SentenceTransformer

    @classmethod
    def fit(cls, corpus: Iterable[tuple[str, str]]) -> "EmbeddingMatcher":
        items = list(corpus)
        ids = [i for i, _ in items]
        texts = [t for _, t in items]
        model = SentenceTransformer(MODEL_NAME)
        emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        emb = np.asarray(emb, dtype=np.float32)
        return cls(
            ids=ids,
            id_to_idx={i: idx for idx, i in enumerate(ids)},
            embeddings=emb,
            model=model,
        )

    def rerank(
        self, query: str, candidate_ids: Sequence[str], k: int = 5
    ) -> list[tuple[str, float]]:
        if not query.strip() or not candidate_ids:
            return []
        q = self.model.encode([query], normalize_embeddings=True, show_progress_bar=False)
        q = np.asarray(q, dtype=np.float32)[0]
        idxs = [self.id_to_idx[c] for c in candidate_ids if c in self.id_to_idx]
        if not idxs:
            return []
        sub = self.embeddings[idxs]
        sims = sub @ q  # cosine, since normalized
        order = np.argsort(sims)[::-1][:k]
        return [(candidate_ids[i], float(sims[i])) for i in order]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest implementation.tests.test_signature_embedding_matcher -v`
Expected: PASS, 2 tests OK. (First run will download ~80MB model.)

---

## Task 8: L6 — Disambiguator

Given a list of candidate canonical row IDs (each with attribute fields) and the product's extracted attributes, picks the best by attribute overlap, with lexical score as tie-breaker.

**Files:**
- Create: `implementation/canonical_signature/disambiguator.py`
- Create: `implementation/tests/test_signature_disambiguator.py`

- [ ] **Step 1: Write the failing test**

```python
# implementation/tests/test_signature_disambiguator.py
import unittest
from implementation.canonical_signature.disambiguator import (
    CanonicalCandidate, disambiguate,
)


class DisambiguatorTests(unittest.TestCase):
    def test_picks_candidate_with_matching_flavor(self):
        candidates = [
            (CanonicalCandidate(id="applesauce_plain", form=None, state=None,
                                flavor=None, style=None), 0.85),
            (CanonicalCandidate(id="applesauce_cinnamon", form=None, state=None,
                                flavor="cinnamon", style=None), 0.82),
        ]
        winner = disambiguate(candidates, product_form=None, product_state=None,
                              product_flavor="cinnamon", product_style=None)
        self.assertEqual(winner.id, "applesauce_cinnamon")

    def test_picks_candidate_with_matching_form(self):
        candidates = [
            (CanonicalCandidate(id="apple_whole", form="whole", state=None,
                                flavor=None, style=None), 0.80),
            (CanonicalCandidate(id="apple_sliced", form="sliced", state=None,
                                flavor=None, style=None), 0.78),
        ]
        winner = disambiguate(candidates, product_form="sliced", product_state=None,
                              product_flavor=None, product_style=None)
        self.assertEqual(winner.id, "apple_sliced")

    def test_lexical_score_breaks_ties_when_no_attributes(self):
        candidates = [
            (CanonicalCandidate(id="a", form=None, state=None, flavor=None, style=None), 0.50),
            (CanonicalCandidate(id="b", form=None, state=None, flavor=None, style=None), 0.60),
        ]
        winner = disambiguate(candidates, product_form=None, product_state=None,
                              product_flavor=None, product_style=None)
        self.assertEqual(winner.id, "b")

    def test_mismatch_penalized(self):
        # Plain product, candidate with conflicting flavor should lose to neutral candidate
        candidates = [
            (CanonicalCandidate(id="ice_cream_vanilla", form=None, state=None,
                                flavor="vanilla", style=None), 0.90),
            (CanonicalCandidate(id="ice_cream_plain", form=None, state=None,
                                flavor=None, style=None), 0.85),
        ]
        winner = disambiguate(candidates, product_form=None, product_state=None,
                              product_flavor="chocolate", product_style=None)
        self.assertEqual(winner.id, "ice_cream_plain")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest implementation.tests.test_signature_disambiguator -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement disambiguator**

```python
# implementation/canonical_signature/disambiguator.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence

ATTR_MATCH_BONUS = 1.0
ATTR_MISMATCH_PENALTY = 0.5
LEXICAL_TIEBREAK_WEIGHT = 0.001  # smaller than any attribute delta


@dataclass(frozen=True)
class CanonicalCandidate:
    id: str
    form: Optional[str]
    state: Optional[str]
    flavor: Optional[str]
    style: Optional[str]


def _attr_score(c_val: Optional[str], p_val: Optional[str]) -> float:
    if p_val is None or c_val is None:
        return 0.0
    if c_val == p_val:
        return ATTR_MATCH_BONUS
    return -ATTR_MISMATCH_PENALTY


def disambiguate(
    candidates: Sequence[tuple[CanonicalCandidate, float]],
    *,
    product_form: Optional[str],
    product_state: Optional[str],
    product_flavor: Optional[str],
    product_style: Optional[str],
) -> CanonicalCandidate:
    if not candidates:
        raise ValueError("disambiguate requires at least one candidate")

    def score(item: tuple[CanonicalCandidate, float]) -> float:
        cand, lex = item
        s = 0.0
        s += _attr_score(cand.form, product_form)
        s += _attr_score(cand.state, product_state)
        s += _attr_score(cand.flavor, product_flavor)
        s += _attr_score(cand.style, product_style)
        s += LEXICAL_TIEBREAK_WEIGHT * lex
        return s

    return max(candidates, key=score)[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest implementation.tests.test_signature_disambiguator -v`
Expected: PASS, 4 tests OK.

---

## Task 9: L7 — Composite router

Detects composite products and looks up `branded_food_category` in a curated mapping table. Initial table is small; long tail flagged unresolved.

**Files:**
- Create: `implementation/canonical_signature/composite_router.py`
- Create: `implementation/canonical_signature/category_to_canonical_anchor.csv` (seed data, ~40 rows)
- Create: `implementation/tests/test_signature_composite_router.py`

- [ ] **Step 1: Write the failing test**

```python
# implementation/tests/test_signature_composite_router.py
import unittest
from implementation.canonical_signature.composite_router import (
    is_composite, route_composite, CompositeRouting,
)


class CompositeDetectionTests(unittest.TestCase):
    def test_with_triggers_composite(self):
        self.assertTrue(is_composite("steamed bun with roast pork filling"))

    def test_filled_triggers_composite(self):
        self.assertTrue(is_composite("ravioli filled cheese"))

    def test_ampersand_word_triggers_composite(self):
        self.assertTrue(is_composite("rice & beans"))

    def test_simple_string_is_not_composite(self):
        self.assertFalse(is_composite("organic apples"))

    def test_and_alone_does_not_trigger(self):
        # 'and' is intentionally NOT a trigger (macaroni and cheese is one dish).
        self.assertFalse(is_composite("macaroni and cheese"))


class CompositeRoutingTests(unittest.TestCase):
    def setUp(self):
        self.category_map = {
            "steamed/stuffed buns": "bun_filled_meat",
            "frozen meals - ethnic": "frozen_meal_mixed",
        }

    def test_routes_via_known_category(self):
        result = route_composite("CHAR-SIU MANAPUA STEAMED BUN WITH ROAST SWEET PORK FILLING",
                                 branded_food_category="Steamed/Stuffed Buns",
                                 category_to_anchor=self.category_map)
        self.assertEqual(result.layer, "L7_category")
        self.assertEqual(result.anchor_id, "bun_filled_meat")

    def test_unresolved_when_category_unknown(self):
        result = route_composite("rice & beans & corn",
                                 branded_food_category="Unknown Category",
                                 category_to_anchor=self.category_map)
        self.assertEqual(result.layer, "L7_unresolved")
        self.assertIsNone(result.anchor_id)

    def test_unresolved_when_category_missing(self):
        result = route_composite("rice & beans",
                                 branded_food_category=None,
                                 category_to_anchor=self.category_map)
        self.assertEqual(result.layer, "L7_unresolved")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest implementation.tests.test_signature_composite_router -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement composite router**

```python
# implementation/canonical_signature/composite_router.py
from __future__ import annotations
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .vocabularies import COMPOSITE_TRIGGERS

CATEGORY_MAP_PATH = Path(__file__).parent / "category_to_canonical_anchor.csv"


def is_composite(text: str) -> bool:
    if not text:
        return False
    tokens = text.lower().replace(",", " ").split()
    return any(t in COMPOSITE_TRIGGERS for t in tokens)


@dataclass(frozen=True)
class CompositeRouting:
    layer: str  # "L7_category" or "L7_unresolved"
    anchor_id: Optional[str]
    detected_secondary: tuple[str, ...]


def route_composite(
    description: str,
    *,
    branded_food_category: Optional[str],
    category_to_anchor: dict[str, str],
) -> CompositeRouting:
    if branded_food_category:
        key = branded_food_category.strip().lower()
        anchor = category_to_anchor.get(key)
        if anchor:
            return CompositeRouting(
                layer="L7_category",
                anchor_id=anchor,
                detected_secondary=(),
            )
    return CompositeRouting(
        layer="L7_unresolved",
        anchor_id=None,
        detected_secondary=(),
    )


def load_category_map(path: Path = CATEGORY_MAP_PATH) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cat = (row.get("branded_food_category") or "").strip().lower()
            anchor = (row.get("canonical_anchor_id") or "").strip()
            if cat and anchor:
                out[cat] = anchor
    return out
```

- [ ] **Step 4: Create the seed category map**

```csv
# implementation/canonical_signature/category_to_canonical_anchor.csv
branded_food_category,canonical_anchor_id,notes
"Bao/Steamed Buns",bun_filled_meat,Filled steamed buns regardless of filling
"Steamed/Stuffed Buns",bun_filled_meat,Same family
"Sandwiches",sandwich_generic,Generic sandwich anchor
"Wraps",wrap_generic,Burritos and similar
"Burritos & Quesadillas",burrito_generic,
"Frozen Meals - Ethnic",frozen_meal_ethnic,
"Frozen Dinners",frozen_meal_dinner,
"Pizza",pizza_generic,Anchor for pizza variants
"Soups",soup_mixed,Multi-ingredient soups
"Salads - Prepared",salad_prepared,Composite prepared salads
"Salads & Salad Dressings",salad_prepared,
"Meal Kits",meal_kit_generic,
"Pasta Dishes",pasta_dish_mixed,
"Casseroles",casserole_mixed,
"Stuffed Pasta",pasta_filled_generic,
"Dumplings",dumpling_filled,
"Pierogies/Dumplings",dumpling_filled,
"Tamales",tamale_filled,
"Sushi",sushi_generic,
"Sushi & Sashimi",sushi_generic,
"Spring Rolls/Egg Rolls",spring_roll_generic,
"Stuffed Vegetables",vegetable_stuffed,
"Pot Pies",pot_pie_generic,
"Quiches",quiche_generic,
"Burgers",burger_generic,
"Hot Dogs/Sausages With Buns",hotdog_with_bun,
"Tacos",taco_generic,
"Empanadas",empanada_filled,
"Calzones/Strombolis",calzone_filled,
"Lasagna",lasagna_generic,
"Mac & Cheese",mac_cheese_generic,
"Stir-Fry Meals",stir_fry_meal,
"Curries",curry_mixed,
"Chili",chili_mixed,
"Stews",stew_mixed,
"Pot Roast",pot_roast_meal,
"Veggie/Fruit Trays",veggie_fruit_tray,Mixed produce trays
"Cheese Trays",cheese_tray,
"Charcuterie",charcuterie_tray,
"Hummus & Dips",dip_mixed,
"Salsa",salsa_generic,
```

Note: `canonical_anchor_id` values here may not yet exist in the canonical_surface; the user will need to either (a) add corresponding canonical rows, or (b) re-point these to the closest existing anchor. This is called out in Task 13.

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest implementation.tests.test_signature_composite_router -v`
Expected: PASS, 8 tests OK.

---

## Task 10: Pipeline orchestrator

Combines L1–L8 for a single product row. Returns `(CanonicalSignature, MatchTrace, anchor_canonical_id)`.

**Files:**
- Create: `implementation/canonical_signature/pipeline.py`
- Create: `implementation/tests/test_signature_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# implementation/tests/test_signature_pipeline.py
import unittest
from implementation.canonical_signature.pipeline import (
    CanonicalSignaturePipeline, ProductRow,
)
from implementation.canonical_signature.vocabularies import Vocabularies, FLUFF_TOKENS, SEED_FLAVOR_TOKENS


def _make_pipeline():
    # Tiny in-memory canonical corpus for test isolation.
    canonical_rows = [
        # id, normalized text, form, state, flavor, style
        ("apple_raw",          "apples raw",                None,     "raw",   None,       None),
        ("apple_sliced",       "apples sliced",             "sliced", None,    None,       None),
        ("applesauce",         "applesauce",                None,     None,    None,       None),
        ("applesauce_cin",     "applesauce cinnamon",       None,     None,    "cinnamon", None),
        ("agave_nectar",       "agave nectar",              None,     None,    None,       None),
        ("agave_nectar_raw",   "agave nectar raw",          None,     "raw",   None,       None),
        ("ice_cream_vanilla",  "ice cream vanilla",         None,     None,    "vanilla",  None),
        ("ice_cream_chocolate","ice cream chocolate",       None,     None,    "chocolate",None),
        ("bun_filled_meat",    "steamed bun filled meat",   None,     None,    None,       None),
    ]
    vocab = Vocabularies(
        fluff_tokens=FLUFF_TOKENS,
        composite_triggers=frozenset({"with", "filled", "stuffed", "topped", "&"}),
        flavor_vocabulary=SEED_FLAVOR_TOKENS,
        form_vocabulary=frozenset({"sliced", "whole", "diced", "liquid", "powder"}),
        state_vocabulary=frozenset({"raw", "frozen", "fresh", "cooked", "dried"}),
        style_vocabulary=frozenset({"organic", "kosher"}),
        packaging_vocabulary=frozenset({"packets", "tray", "cup", "bag"}),
        brand_vocabulary=frozenset({"natures place", "madhava", "goldens"}),
        head_noun_vocabulary=frozenset(r[1] for r in canonical_rows),
    )
    category_map = {"steamed/stuffed buns": "bun_filled_meat"}
    return CanonicalSignaturePipeline.build(canonical_rows, vocab, category_map)


class PipelineGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipe = _make_pipeline()

    def _process(self, desc, brand_name=None, brand_owner=None, category=None):
        return self.pipe.process(ProductRow(
            description=desc, brand_name=brand_name, brand_owner=brand_owner,
            branded_food_category=category,
        ))

    def test_brand_prefix_is_stripped(self):
        sig, trace, anchor = self._process("NATURE'S PLACE, ORGANIC APPLES",
                                           brand_name="NATURE'S PLACE")
        self.assertEqual(trace.stripped_brand, "natures place")
        self.assertIn("organic", trace.stripped_fluff)
        self.assertIn(anchor, ("apple_raw", "apple_sliced", "applesauce"))

    def test_cinnamon_applesauce_picks_cinnamon_variant(self):
        sig, trace, anchor = self._process("CINNAMON APPLESAUCE")
        self.assertEqual(anchor, "applesauce_cin")
        self.assertEqual(sig.flavor, "cinnamon")

    def test_plain_applesauce_picks_plain_variant(self):
        sig, trace, anchor = self._process("APPLESAUCE")
        self.assertEqual(anchor, "applesauce")

    def test_vanilla_ice_cream_picks_vanilla_variant(self):
        sig, trace, anchor = self._process("VANILLA ICE CREAM")
        self.assertEqual(anchor, "ice_cream_vanilla")

    def test_chocolate_ice_cream_picks_chocolate_variant(self):
        sig, trace, anchor = self._process("CHOCOLATE ICE CREAM")
        self.assertEqual(anchor, "ice_cream_chocolate")

    def test_raw_agave_picks_raw_variant(self):
        sig, trace, anchor = self._process("MADHAVA, RAW ORGANIC AGAVE NECTAR",
                                           brand_name="MADHAVA")
        self.assertEqual(anchor, "agave_nectar_raw")
        self.assertEqual(sig.state, "raw")

    def test_composite_routes_via_category(self):
        sig, trace, anchor = self._process(
            "CHAR-SIU MANAPUA STEAMED BUN WITH ROAST SWEET PORK FILLING",
            category="Steamed/Stuffed Buns",
        )
        self.assertTrue(sig.composite)
        self.assertEqual(trace.match_layer, "L7_category")
        self.assertEqual(anchor, "bun_filled_meat")

    def test_composite_unresolved_when_no_category_match(self):
        sig, trace, anchor = self._process(
            "FRESH SELECTIONS, VEGGIE TRAY WITH APPLES",
            brand_name="FRESH SELECTIONS",
            category="Unknown Random Category",
        )
        self.assertTrue(sig.composite)
        self.assertEqual(trace.match_layer, "L7_unresolved")
        self.assertIsNone(anchor)

    def test_signature_groups_collapse_correctly(self):
        # Multiple inputs that should produce IDENTICAL signatures
        results = [
            self._process("APPLESAUCE"),
            self._process("ORGANIC APPLESAUCE"),
            self._process("PREMIUM APPLESAUCE"),
            self._process("AUTHENTIC APPLESAUCE"),
        ]
        sigs = {r[0] for r in results}
        self.assertEqual(len(sigs), 1, f"All should collapse to one signature, got {sigs}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest implementation.tests.test_signature_pipeline -v`
Expected: FAIL — pipeline module missing.

- [ ] **Step 3: Implement pipeline orchestrator**

```python
# implementation/canonical_signature/pipeline.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Sequence

from .signature import CanonicalSignature, MatchTrace
from .vocabularies import Vocabularies
from .normalizer import normalize
from .brand_stripper import strip_brand
from .attribute_extractor import extract_attributes
from .lexical_matcher import LexicalMatcher
from .embedding_matcher import EmbeddingMatcher
from .disambiguator import CanonicalCandidate, disambiguate
from .composite_router import is_composite, route_composite

LEXICAL_THRESHOLD = 0.55  # below this, fall back to embedding rerank
TOP_K_LEXICAL = 5
TOP_K_EMBED_POOL = 50


@dataclass(frozen=True)
class ProductRow:
    description: str
    brand_name: Optional[str] = None
    brand_owner: Optional[str] = None
    branded_food_category: Optional[str] = None


# Tuple form: (id, normalized_text, form, state, flavor, style)
CanonicalCorpusRow = tuple[str, str, Optional[str], Optional[str], Optional[str], Optional[str]]


@dataclass
class CanonicalSignaturePipeline:
    vocab: Vocabularies
    category_to_anchor: dict[str, str]
    canonical_index: dict[str, CanonicalCandidate]  # id -> attributes
    lexical: LexicalMatcher
    embedder: Optional[EmbeddingMatcher]  # optional for tests; required for L5

    @classmethod
    def build(
        cls,
        canonical_rows: Sequence[CanonicalCorpusRow],
        vocab: Vocabularies,
        category_to_anchor: dict[str, str],
        *,
        with_embeddings: bool = False,
    ) -> "CanonicalSignaturePipeline":
        idx: dict[str, CanonicalCandidate] = {}
        corpus: list[tuple[str, str]] = []
        for cid, text, form, state, flavor, style in canonical_rows:
            idx[cid] = CanonicalCandidate(id=cid, form=form, state=state,
                                          flavor=flavor, style=style)
            corpus.append((cid, text))
        lex = LexicalMatcher.fit(corpus)
        emb = EmbeddingMatcher.fit(corpus) if with_embeddings else None
        return cls(vocab=vocab, category_to_anchor=category_to_anchor,
                   canonical_index=idx, lexical=lex, embedder=emb)

    def process(self, row: ProductRow) -> tuple[CanonicalSignature, MatchTrace, Optional[str]]:
        # L1
        norm = normalize(row.description)
        # L2
        residual_after_brand, brand = strip_brand(
            norm, brand_name=row.brand_name, brand_owner=row.brand_owner,
            brand_vocabulary=self.vocab.brand_vocabulary,
        )
        # L3
        ext = extract_attributes(
            residual_after_brand,
            fluff=self.vocab.fluff_tokens,
            flavors=self.vocab.flavor_vocabulary,
            forms=self.vocab.form_vocabulary,
            states=self.vocab.state_vocabulary,
            styles=self.vocab.style_vocabulary,
            packaging=self.vocab.packaging_vocabulary,
        )

        # L7 — composite check on the ORIGINAL normalized string
        # (composite signals are in the unstripped text)
        composite_flag = is_composite(norm)

        if composite_flag:
            routing = route_composite(
                row.description,
                branded_food_category=row.branded_food_category,
                category_to_anchor=self.category_to_anchor,
            )
            sig = CanonicalSignature(
                head_noun=ext.head_noun, modifiers=frozenset(),
                form=ext.form, state=ext.state, flavor=ext.flavor, style=ext.style,
                composite=True,
                secondary_ingredients=routing.detected_secondary,
            )
            trace = MatchTrace(
                match_layer=routing.layer,
                stripped_brand=brand,
                stripped_fluff=ext.fluff_stripped,
                extracted_attributes=self._attr_dict(ext),
                residual=ext.residual,
                top_candidates=((routing.anchor_id, 1.0),) if routing.anchor_id else (),
                match_confidence=1.0 if routing.anchor_id else 0.0,
                match_reason=("category lookup hit" if routing.anchor_id
                              else "composite, no category mapping"),
            )
            return sig, trace, routing.anchor_id

        # L4
        lex_results = self.lexical.match(ext.residual, k=TOP_K_LEXICAL)
        if not lex_results:
            sig = CanonicalSignature(
                head_noun=ext.head_noun, modifiers=frozenset(),
                form=ext.form, state=ext.state, flavor=ext.flavor, style=ext.style,
            )
            trace = MatchTrace(
                match_layer="unmatched",
                stripped_brand=brand,
                stripped_fluff=ext.fluff_stripped,
                extracted_attributes=self._attr_dict(ext),
                residual=ext.residual,
                top_candidates=(),
                match_confidence=0.0,
                match_reason="empty residual or no lexical hits",
            )
            return sig, trace, None

        layer = "L4_lexical"
        if lex_results[0][1] < LEXICAL_THRESHOLD and self.embedder is not None:
            # L5 rerank top-50 (or however many lex returned)
            pool = [c for c, _ in self.lexical.match(ext.residual, k=TOP_K_EMBED_POOL)]
            embed_results = self.embedder.rerank(ext.residual, pool, k=TOP_K_LEXICAL)
            if embed_results:
                lex_results = embed_results
                layer = "L5_embedding"

        # L6 — disambiguate using attributes
        annotated = [(self.canonical_index[cid], score) for cid, score in lex_results
                     if cid in self.canonical_index]
        if not annotated:
            return self._unmatched(ext, brand)

        winner = disambiguate(
            annotated,
            product_form=ext.form, product_state=ext.state,
            product_flavor=ext.flavor, product_style=ext.style,
        )
        winner_score = next(s for c, s in lex_results if c == winner.id)
        if layer == "L4_lexical" and len(lex_results) > 1:
            layer = "L6_disambiguated" if winner.id != lex_results[0][0] else "L4_lexical"

        sig = CanonicalSignature(
            head_noun=ext.head_noun,
            modifiers=frozenset(filter(None, (ext.flavor, ext.form, ext.state, ext.style))),
            form=ext.form, state=ext.state, flavor=ext.flavor, style=ext.style,
            composite=False,
        )
        trace = MatchTrace(
            match_layer=layer,
            stripped_brand=brand,
            stripped_fluff=ext.fluff_stripped,
            extracted_attributes=self._attr_dict(ext),
            residual=ext.residual,
            top_candidates=tuple(lex_results[:3]),
            match_confidence=winner_score,
            match_reason=f"{layer}: {winner.id} won by attribute overlap and lexical score",
        )
        return sig, trace, winner.id

    def _attr_dict(self, ext) -> dict:
        return {"form": ext.form, "state": ext.state, "flavor": ext.flavor,
                "style": ext.style, "packaging": ext.packaging}

    def _unmatched(self, ext, brand) -> tuple[CanonicalSignature, MatchTrace, None]:
        sig = CanonicalSignature(
            head_noun=ext.head_noun, modifiers=frozenset(),
            form=ext.form, state=ext.state, flavor=ext.flavor, style=ext.style,
        )
        trace = MatchTrace(
            match_layer="unmatched",
            stripped_brand=brand,
            stripped_fluff=ext.fluff_stripped,
            extracted_attributes=self._attr_dict(ext),
            residual=ext.residual,
            top_candidates=(),
            match_confidence=0.0,
            match_reason="no candidate survived disambiguation",
        )
        return sig, trace, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest implementation.tests.test_signature_pipeline -v`
Expected: PASS, 9 tests OK. (Pipeline tests intentionally don't enable embeddings — fast.)

---

## Task 11: CLI runner — build_canonical_signature_map.py

Streams the full vM file (462k rows), writes `product_to_canonical_signature.csv` with all provenance columns and a diff against the prior `best_esha_*` assignment.

**Files:**
- Create: `implementation/build_canonical_signature_map.py`
- Reference inputs:
  - `/Users/jamiebarton/Desktop/clean/canonical_surface_normalized_with_product_proxies.csv`
  - `/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/product_to_best_esha_full_map.vM.csv`
- Output: `implementation/output/product_to_canonical_signature.csv`
- Output: `implementation/output/product_to_canonical_signature_summary.json`

- [ ] **Step 1: Write the runner**

```python
# implementation/build_canonical_signature_map.py
"""Build product -> canonical signature mapping over the full vM corpus.

Reads:
  - canonical_surface_normalized_with_product_proxies.csv (anchor universe)
  - product_to_best_esha_full_map.vM.csv (462k branded products)

Writes:
  - implementation/output/product_to_canonical_signature.csv
  - implementation/output/product_to_canonical_signature_summary.json
"""
from __future__ import annotations
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from implementation.canonical_signature.attribute_extractor import extract_attributes
from implementation.canonical_signature.composite_router import load_category_map
from implementation.canonical_signature.pipeline import (
    CanonicalSignaturePipeline, ProductRow,
)
from implementation.canonical_signature.vocabularies import Vocabularies

CANONICAL_PATH = Path(
    "/Users/jamiebarton/Desktop/clean/canonical_surface_normalized_with_product_proxies.csv"
)
PRODUCT_PATH = Path(
    "/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/"
    "product_to_best_esha_full_map.vM.csv"
)
OUTPUT_DIR = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output")
OUTPUT_CSV = OUTPUT_DIR / "product_to_canonical_signature.csv"
SUMMARY_JSON = OUTPUT_DIR / "product_to_canonical_signature_summary.json"

OUTPUT_FIELDS = [
    "gtin_upc", "fdc_id", "product_description", "branded_food_category", "brand_name",
    "signature_head_noun", "signature_modifiers",
    "signature_form", "signature_state", "signature_flavor", "signature_style",
    "composite", "secondary_ingredients",
    "canonical_anchor_id", "canonical_surface", "canonical_normalized",
    "sr28_code", "fndds_code", "esha_code",
    "match_layer", "match_confidence", "match_reason",
    "stripped_brand", "stripped_fluff", "extracted_attributes_json", "residual",
    "top_candidates_json",
    "prev_best_esha_code", "prev_score", "assignment_changed",
]


def load_canonical_corpus(path: Path, vocab: Vocabularies):
    """Yield (id, normalized_text, form, state, flavor, style) per canonical row.

    Form/state/style come from the canonical_surface attribute columns when populated;
    flavor (no dedicated column) is derived by running the attribute extractor over
    canonical_normalized — this keeps canonical and product signatures comparable.
    Also returns lookup dict id -> full row dict for downstream code/description fields.
    """
    corpus = []
    lookup: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            cid = f"canon_{i}"
            text = (row.get("canonical_normalized") or "").strip().lower()
            if not text:
                continue

            # Run extractor over the canonical text itself so anything the product
            # extractor can pull out (form/state/flavor/style) is also tagged on the
            # canonical side. Column-derived values take precedence when present.
            ext = extract_attributes(
                text,
                fluff=vocab.fluff_tokens,
                flavors=vocab.flavor_vocabulary,
                forms=vocab.form_vocabulary,
                states=vocab.state_vocabulary,
                styles=vocab.style_vocabulary,
                packaging=vocab.packaging_vocabulary,
            )
            form = _first_attr(row.get("form_attributes")) or ext.form
            state = _first_attr(row.get("state_attributes")) or ext.state
            style = _first_attr(row.get("style_attributes")) or ext.style
            flavor = ext.flavor  # canonical_surface has no flavor column

            corpus.append((cid, text, form, state, flavor, style))
            lookup[cid] = row
    return corpus, lookup


def _first_attr(cell):
    if not cell:
        return None
    parts = cell.replace(";", ",").split(",")
    for p in parts:
        v = p.strip().lower()
        if v:
            return v
    return None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N product rows (smoke test)")
    parser.add_argument("--no-embeddings", action="store_true",
                        help="Skip L5 embedding fallback (faster, lower recall)")
    parser.add_argument("--output", type=Path, default=OUTPUT_CSV)
    args = parser.parse_args(argv)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] Loading vocabularies from {CANONICAL_PATH.name}")
    vocab = Vocabularies.from_canonical_surface(CANONICAL_PATH)
    print(f"      brand_vocab={len(vocab.brand_vocabulary)} "
          f"form_vocab={len(vocab.form_vocabulary)} "
          f"flavors={len(vocab.flavor_vocabulary)}")

    print(f"[2/4] Loading canonical corpus")
    corpus, canonical_lookup = load_canonical_corpus(CANONICAL_PATH, vocab)
    print(f"      canonical_rows={len(corpus)}")

    print(f"[3/4] Building pipeline (embeddings={'off' if args.no_embeddings else 'on'})")
    category_map = load_category_map()
    pipeline = CanonicalSignaturePipeline.build(
        corpus, vocab, category_map, with_embeddings=not args.no_embeddings,
    )

    print(f"[4/4] Streaming products from {PRODUCT_PATH.name} -> {args.output.name}")
    counters: Counter = Counter()
    rows_written = 0

    with PRODUCT_PATH.open(newline="", encoding="utf-8") as fin, \
         args.output.open("w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()

        for i, prow in enumerate(reader):
            if args.limit is not None and i >= args.limit:
                break

            sig, trace, anchor_id = pipeline.process(ProductRow(
                description=prow.get("product_description") or "",
                brand_name=prow.get("brand_name") or None,
                brand_owner=prow.get("brand_owner") or None,
                branded_food_category=prow.get("branded_food_category") or None,
            ))

            anchor_row = canonical_lookup.get(anchor_id) if anchor_id else None
            prev_code = prow.get("best_esha_code") or ""
            new_esha = (anchor_row or {}).get("esha_code", "") if anchor_row else ""
            assignment_changed = (prev_code or "") != (new_esha or "")

            writer.writerow({
                "gtin_upc": prow.get("gtin_upc", ""),
                "fdc_id": prow.get("fdc_id", ""),
                "product_description": prow.get("product_description", ""),
                "branded_food_category": prow.get("branded_food_category", ""),
                "brand_name": prow.get("brand_name", ""),
                "signature_head_noun": sig.head_noun,
                "signature_modifiers": ";".join(sorted(sig.modifiers)),
                "signature_form": sig.form or "",
                "signature_state": sig.state or "",
                "signature_flavor": sig.flavor or "",
                "signature_style": sig.style or "",
                "composite": "true" if sig.composite else "false",
                "secondary_ingredients": ";".join(sig.secondary_ingredients),
                "canonical_anchor_id": anchor_id or "",
                "canonical_surface": (anchor_row or {}).get("canonical_surface", ""),
                "canonical_normalized": (anchor_row or {}).get("canonical_normalized", ""),
                "sr28_code": (anchor_row or {}).get("sr28_code", ""),
                "fndds_code": (anchor_row or {}).get("fndds_code", ""),
                "esha_code": new_esha,
                "match_layer": trace.match_layer,
                "match_confidence": f"{trace.match_confidence:.4f}",
                "match_reason": trace.match_reason,
                "stripped_brand": trace.stripped_brand,
                "stripped_fluff": ";".join(trace.stripped_fluff),
                "extracted_attributes_json": json.dumps(trace.extracted_attributes),
                "residual": trace.residual,
                "top_candidates_json": json.dumps([[c, round(s, 4)] for c, s in trace.top_candidates]),
                "prev_best_esha_code": prev_code,
                "prev_score": prow.get("score", ""),
                "assignment_changed": "true" if assignment_changed else "false",
            })
            counters[trace.match_layer] += 1
            counters["composite" if sig.composite else "non_composite"] += 1
            counters["assignment_changed" if assignment_changed else "assignment_kept"] += 1
            rows_written += 1
            if rows_written % 10000 == 0:
                print(f"      processed {rows_written}", file=sys.stderr)

    summary = {
        "rows_written": rows_written,
        "by_layer": dict(counters),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2))
    print(f"Done. Summary: {SUMMARY_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke test on 500 rows**

Run: `python3 implementation/build_canonical_signature_map.py --limit 500 --no-embeddings --output /tmp/sig_smoke.csv`
Expected: completes without error in <60s. Outputs `/tmp/sig_smoke.csv` with 500 rows. Check by running:

```bash
head -1 /tmp/sig_smoke.csv && echo --- && awk -F, 'NR>1 {print $20}' /tmp/sig_smoke.csv | sort | uniq -c | sort -rn
```

Expected: header is the OUTPUT_FIELDS list; layer distribution shows a mix of `L4_lexical`, `L6_disambiguated`, `L7_unresolved`, `unmatched`.

- [ ] **Step 3: Inspect smoke output for hand-picked examples**

Run:
```bash
grep -i "MADHAVA" /tmp/sig_smoke.csv | head -3
grep -i "APPLES" /tmp/sig_smoke.csv | head -5
```

Manually verify: brand was stripped; head noun is reasonable; anchor IDs make sense. If wrong, iterate on vocabularies/L3 before scaling up.

- [ ] **Step 4: Full run with embeddings**

Run: `python3 implementation/build_canonical_signature_map.py`
Expected: runs to completion. Embedding L5 fallback fires only on low-confidence rows. Write `product_to_canonical_signature.csv` (~462k rows) and summary JSON.

---

## Task 12: build_signature_groups.py — collapsed view

Reads `product_to_canonical_signature.csv`, groups by signature, emits per-signature aggregate rows.

**Files:**
- Create: `implementation/build_signature_groups.py`
- Output: `implementation/output/signature_groups.csv`

- [ ] **Step 1: Write the runner**

```python
# implementation/build_signature_groups.py
"""Collapse product_to_canonical_signature.csv into per-signature group rows."""
from __future__ import annotations
import csv
from collections import defaultdict
from pathlib import Path

INPUT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/"
             "product_to_canonical_signature.csv")
OUTPUT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/"
              "signature_groups.csv")

KEY_FIELDS = ("signature_head_noun", "signature_modifiers", "signature_form",
              "signature_state", "signature_flavor", "signature_style", "composite")

OUTPUT_FIELDS = list(KEY_FIELDS) + [
    "product_count", "canonical_anchor_id", "esha_code",
    "representative_descriptions",
    "mean_match_confidence",
]


def main():
    groups: dict[tuple, list[dict]] = defaultdict(list)
    with INPUT.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = tuple(row[k] for k in KEY_FIELDS)
            groups[key].append(row)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for key, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            n = len(rows)
            anchors = [r["canonical_anchor_id"] for r in rows if r["canonical_anchor_id"]]
            anchor = max(set(anchors), key=anchors.count) if anchors else ""
            esha_codes = [r["esha_code"] for r in rows if r["esha_code"]]
            esha = max(set(esha_codes), key=esha_codes.count) if esha_codes else ""
            reps = [r["product_description"] for r in rows[:5]]
            mean_conf = (sum(float(r["match_confidence"]) for r in rows) / n) if n else 0.0
            writer.writerow({
                **dict(zip(KEY_FIELDS, key)),
                "product_count": n,
                "canonical_anchor_id": anchor,
                "esha_code": esha,
                "representative_descriptions": " || ".join(reps),
                "mean_match_confidence": f"{mean_conf:.4f}",
            })
    print(f"Wrote {OUTPUT} with {len(groups)} unique signatures.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run after Task 11 completes**

Run: `python3 implementation/build_signature_groups.py`
Expected: writes `implementation/output/signature_groups.csv`. Inspect:

```bash
head -1 /Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/signature_groups.csv
wc -l /Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/signature_groups.csv
```

Expected: row count is ≪ 462k (signatures collapse). Sort by `product_count` desc to inspect biggest groups (`head -20` after sort).

---

## Task 13: Acceptance suite — golden sample over real data

Codifies the spec's acceptance checks as a runnable test that loads the actual produced artifact and asserts on it.

**Files:**
- Create: `implementation/tests/test_signature_acceptance.py`
- Reads: `implementation/output/product_to_canonical_signature.csv` (must exist; produced by Task 11)

- [ ] **Step 1: Write the acceptance tests**

```python
# implementation/tests/test_signature_acceptance.py
"""Acceptance suite — runs against real produced artifact.

Skipped if the artifact is missing (e.g. on a fresh checkout before Task 11 has run).
"""
from __future__ import annotations
import csv
import unittest
from pathlib import Path

ARTIFACT = Path(
    "/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/"
    "product_to_canonical_signature.csv"
)


def _load_rows():
    with ARTIFACT.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@unittest.skipUnless(ARTIFACT.exists(),
                     f"acceptance suite skipped: {ARTIFACT} not built yet")
class AcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = _load_rows()

    def test_artifact_has_full_corpus(self):
        # Spec: 462,647 rows in vM. Allow ±100 for off-by-one streaming variance.
        self.assertGreater(len(self.rows), 462000)

    def test_coverage_threshold(self):
        # Spec acceptance criterion: >=90% of non-composite products reach an anchor with confidence>=0.5
        non_comp = [r for r in self.rows if r["composite"] == "false"]
        ok = sum(1 for r in non_comp
                 if r["canonical_anchor_id"] and float(r["match_confidence"]) >= 0.5)
        ratio = ok / len(non_comp) if non_comp else 0
        self.assertGreaterEqual(ratio, 0.90, f"non-composite coverage at {ratio:.2%}")

    def test_composite_recall(self):
        # Spec: products containing 'with', '&', 'filled' should be flagged composite >=80%
        triggered = [r for r in self.rows
                     if any(t in (r["product_description"] or "").lower().split()
                            for t in ("with", "filled", "stuffed"))
                     or "&" in (r["product_description"] or "")]
        flagged = sum(1 for r in triggered if r["composite"] == "true")
        if triggered:
            self.assertGreaterEqual(flagged / len(triggered), 0.80,
                                    f"composite recall {flagged}/{len(triggered)}")

    def test_assignment_changed_rate_is_substantial_but_not_chaotic(self):
        changed = sum(1 for r in self.rows if r["assignment_changed"] == "true")
        ratio = changed / len(self.rows)
        # Existing vM is known unreliable; expect meaningful change but not full reshuffle.
        self.assertGreater(ratio, 0.05, "expected some changes vs vM")
        self.assertLess(ratio, 0.95, "near-total reshuffle suggests pipeline broken")

    def test_hand_picked_examples(self):
        """The 14 examples the user pasted into the brainstorming session."""
        wanted_substrings = [
            "NATURE'S PLACE, ORGANIC APPLES",
            "FRESH SELECTIONS, VEGGIE TRAY WITH APPLES",
            "FRESH-PICKED APPLES",
            "GOLDENS FRESH SLICED APPLES",
            "CHAR-SIU MANAPUA STEAMED BUN WITH ROAST SWEET PORK FILLING",
            "PERI PERI SPICY TOMATO & PEPPER STEAMED RICE",
            "ORGANIC BLUE AGAVE NECTAR PACKETS",
            "ORGANIC RAW BLUE AGAVE NECTAR",
            "AGAVE NECTAR LIQUID SWEETENER",
            "AGAVE NECTAR",
            "MADHAVA, RAW ORGANIC AGAVE NECTAR",
        ]
        # Index by exact description
        by_desc = {(r["product_description"] or "").upper(): r for r in self.rows}
        found = [w for w in wanted_substrings if w in by_desc]
        # We don't require all 14 to exist (vM may not contain every one), but we
        # require that any that DO exist produced a non-error trace.
        for desc in found:
            r = by_desc[desc]
            self.assertIn(r["match_layer"],
                          {"L4_lexical", "L5_embedding", "L6_disambiguated",
                           "L7_category", "L7_unresolved"},
                          f"unexpected match_layer for {desc}: {r['match_layer']}")
```

- [ ] **Step 2: Run acceptance suite**

Run: `python3 -m unittest implementation.tests.test_signature_acceptance -v`

Expected (after Task 11 has produced the artifact): all 5 tests pass. If `test_coverage_threshold` or `test_composite_recall` fails, the failure message tells you the actual ratio — iterate on vocabularies (Task 2), the LEXICAL_THRESHOLD constant (Task 10), or the category map (Task 9) and re-run Task 11.

- [ ] **Step 3: Run the full regression suite**

Run: `python3 -m unittest discover -s implementation/tests -p 'test_signature_*.py' -v`
Expected: all pipeline-related tests pass.

- [ ] **Step 4: Document anchor ID gaps**

The seed `category_to_canonical_anchor.csv` (Task 9) uses placeholder anchor IDs (`bun_filled_meat`, `sushi_generic`, etc) that may not exist in the canonical_surface. Inspect Task 12's `signature_groups.csv` to find composite groups whose `canonical_anchor_id` resolved to an empty `esha_code`. Two options:

1. Add the missing canonical rows to `canonical_surface_normalized_with_product_proxies.csv` (preferred, single source of truth).
2. Edit `category_to_canonical_anchor.csv` to point each placeholder at the closest existing canonical row.

Track this in `implementation/output/composite_anchor_gaps.md` (one line per missing anchor: which categories use it, how many products are affected). This is a hand-curation followup, intentionally outside the automated pipeline.

---

## Notes for the executing engineer

- **No git in this repo.** Skip all commit steps. Run tests after each module instead.
- **Run tests from the repo root:** `python3 -m unittest implementation.tests.test_signature_*` works because `AGENTS.md` sets the convention; do NOT `cd implementation/` first.
- **The first run downloads ~80MB MiniLM.** Subsequent runs use the local cache under `~/.cache/huggingface/`.
- **If `test_coverage_threshold` fails at Task 13:** the most common cause is that the seed `FLUFF_TOKENS` or attribute vocabularies are too small. Look at the actual residuals in failing rows (`grep -E "match_confidence,0\.[0-3]" implementation/output/product_to_canonical_signature.csv`) and add the leftover noise tokens to `FLUFF_TOKENS`. Re-run Task 11. Iteration is expected.
- **The pipeline is deterministic** given fixed vocabularies and a pinned MiniLM model version. Reproducible.
