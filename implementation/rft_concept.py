"""
RFT — Concept Router (normalized taxonomy on top of SR28+FNDDS+ESHA).

A concept is a token-set, not a head. "Garlic powder" is the concept
{garlic, powder} — one node — even though ESHA stores it as
"Spices, garlic powder", FNDDS as "Garlic, powder", SR28 as "Garlic, ground".

Building blocks (re-uses rft.py vocab):
  - CATEGORY_PREFIXES are stripped from concepts
  - CURATED_CARRIERS (Pillsbury, Kraft, etc.) are stripped
  - VERBOSITY, UNITS, GLOBAL_NOISE, RETAIL_ATTRS_NONROUTING stripped
  - RETAIL_ATTRS_ROUTING kept (frozen/canned/dried/raw discriminate)
  - MODIFIER_TOKENS kept (they discriminate within concept)

Routing:
  surface concept = same extraction
  EXACT       surface concept == leaf concept
  STRONG      surface ⊆ leaf, leaf has 1-2 extra tokens
  WEAK        |surface ∩ leaf| / |surface| >= 0.5
  NEEDS_NEW   otherwise
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rft import (
    ROOT, OUT, PARSED, SURFACE,
    load_rows,
    GLOBAL_NOISE, RETAIL_ATTRS_NONROUTING, RETAIL_ATTRS_ROUTING,
    MODIFIER_TOKENS, UNITS, CURATED_CARRIERS, VERBOSITY, FORM_WORDS,
    SURFACE_MODIFIERS, BRAND_FOOD_ALIASES, SYNONYMS, PLURAL,
    tokens, _normalize, WORD,
)

OUT_C = OUT / "concept"
OUT_C.mkdir(parents=True, exist_ok=True)

# Category prefixes: pure category words that wrap real food identity.
# Example: "Spices, garlic powder" — `spices` is just the cabinet, not the
# food. The food is `garlic powder`. These are stripped during concept
# extraction so concepts collapse across sources that prefix differently.
CATEGORY_PREFIXES = {
    "spice", "spices",
    "seasoning", "seasonings",
    "topping", "toppings",
    "dish", "dishes",
    "meal", "meals",
    "side", "sides",
    "entree", "entrees",
    "course", "courses",
    "babyfood",
    "lunchmeat",
    "snack", "snacks",     # "snack, X" — but "snack mix" stays via tokens
    "vegetable",           # "Vegetable, kale, raw" — kale is the food
    "vegetables",
    "fruit", "fruits",
    "grain", "grains",
    "legume", "legumes",
    "nut", "nuts",         # "Nut, almond" — almond is the food
    "seed", "seeds",       # debatable but usually true
    "herb", "herbs",
    "leaf", "leaves",
    "ingredient", "ingredients",
    "candy", "candies",   # SR28 "Candy, milk chocolate, with almonds" — milk
                          # chocolate + almonds is the actual food, candy is
                          # the category. Surface "milk chocolate almonds"
                          # then matches the concept's tokens exactly.
    "beverage", "beverages",  # SR28/FNDDS "Beverages, carbonated, root beer"
                              # — beverage and carbonated are the category.
    "carbonated",
    "cereal", "cereals",
    "cookies",  # SR28 "Cookies, X" first-frag often is the form prefix
    "snacks",  # SR28 "Snacks, granola bars, X" — snacks is category
}

# Subset of CATEGORY_PREFIXES that act as USAGE/PREPARATION prefixes —
# they don't just label what the food is, they signal a different
# preparation. "Topping, pork" ≠ raw pork; "Snack, X" ≠ standalone X.
# Entries with first_frag entirely in this set are skipped from the
# concept index (they pollute matching with degenerate stubs). Entries
# with first_frag in CATEGORY_PREFIXES \ USAGE_PREFIXES (Spices, Nuts,
# Vegetables…) are kept; their identity falls back to whole-concept tokens.
USAGE_PREFIXES = {
    "topping", "toppings",
    "dish", "dishes",
    "meal", "meals",
    "side", "sides",
    "entree", "entrees",
    "course", "courses",
    "snack", "snacks",
}

# Tokens that get stripped during concept extraction. ONLY the things that
# don't discriminate nutrition: pure noise, brand names, category prefixes,
# units, marketing words. NOT form words (powder/chip/flake DO change food
# identity), NOT modifier tokens (cooked/fried/raw change nutrition).
ROUTING_FACET_RETAIN = {
    # Weak form words: not identity anchors, but useful inside an already
    # matched food family. This keeps "mushroom pieces stems" on the
    # mushroom pieces/stems leaf without letting "pieces" match artichokes.
    "piece", "pieces", "stem", "stems", "pce", "pces",
}

NON_IDENTITY_FACETS = ROUTING_FACET_RETAIN

CONCEPT_STRIP = (
    GLOBAL_NOISE
    | VERBOSITY
    | UNITS
    | CURATED_CARRIERS       # Pillsbury, Kraft, Denny's, etc.
    | CATEGORY_PREFIXES      # Spices, Dish, Topping, etc.
    | (RETAIL_ATTRS_NONROUTING - ROUTING_FACET_RETAIN)
)

# Tokens that act as DESCRIPTORS even when they appear in the first fragment
# of a nutrition description. Stripped during position-identity calculation
# only — they still survive in concept_id and surface tokens. Without this,
# "Hot cocoa with marshmallows" would have identity {hot, cocoa} and surfaces
# like "cocoa with marshmallows" would fail the position filter.
FIRST_FRAG_DESCRIPTORS = (
    MODIFIER_TOKENS
    | FORM_WORDS
    | RETAIL_ATTRS_ROUTING       # frozen, fresh, dried, canned, sliced
    | RETAIL_ATTRS_NONROUTING    # organic, premium, leaves
    | SURFACE_MODIFIERS          # fat, sugar, sodium, blend, flavor
    | {"hot", "cold", "warm", "chilled", "iced", "instant",
       "raw", "cooked", "dry", "wet", "hard"}
)


PHRASE_ALIASES = (
    (re.compile(r"\bapple[\s-]+sauces?\b", re.IGNORECASE), "applesauce"),
    (re.compile(r"\balmondmilk\b", re.IGNORECASE), "almond milk"),
    (re.compile(r"\bcashewmilk\b", re.IGNORECASE), "cashew milk"),
    (re.compile(r"\bcoconutmilk\b", re.IGNORECASE), "coconut milk"),
    (re.compile(r"\bhempmilk\b", re.IGNORECASE), "hemp milk"),
    (re.compile(r"\boatmilk\b", re.IGNORECASE), "oat milk"),
    (re.compile(r"\bricemilk\b", re.IGNORECASE), "rice milk"),
    (re.compile(r"\bsoymilk\b", re.IGNORECASE), "soy milk"),
)

NEGATED_NUTRIENT_PATTERNS = (
    re.compile(r"\bno\s+salt\s+added\b", re.IGNORECASE),
    re.compile(r"\bno\s+added\s+salt\b", re.IGNORECASE),
    re.compile(r"\bwithout\s+salt\b", re.IGNORECASE),
)


def normalize_surface_phrases(text: str) -> str:
    """Normalize multi-token food names before token-set extraction."""
    out = str(text or "")
    for pat in NEGATED_NUTRIENT_PATTERNS:
        out = pat.sub(" ", out)
    for pat, repl in PHRASE_ALIASES:
        out = pat.sub(repl, out)
    return out


def concept_tokens_from_text(text: str, brand_registry: set[str] = None) -> frozenset:
    """Extract the concept token set from any string (leaf desc OR surface)."""
    if brand_registry is None:
        brand_registry = set()
    out = set()
    for t in tokens(normalize_surface_phrases(text)):
        if t in CONCEPT_STRIP:
            continue
        if t in brand_registry:
            continue
        if len(t) <= 1:
            continue
        if t.isdigit():
            continue
        out.add(t)
    if "applesauce" in out:
        # Retail often repeats the flavor family around the compound:
        # "APPLESAUCE, APPLE" or "APPLE CINNAMON APPLE SAUCE".
        # Keep the compound head and remove redundant tokens that otherwise
        # make exact cinnamon/plain applesauce leaves look weak.
        out.discard("apple")
        out.discard("sauce")
        out.difference_update({"cup", "cups", "pouch", "pouches", "case"})
    return frozenset(out)


# ---------------------------------------------------------------------------
# Build the concept index from parsed_unified.csv
# ---------------------------------------------------------------------------

@dataclass
class ConceptNode:
    concept_id: frozenset           # the token set
    canonical_name: str             # representative description (shortest)
    sources: dict[str, list]        # 'sr28'|'fndds'|'esha' -> [(code, desc)]
    identity_tokens: frozenset = frozenset()
        # The subset of concept_id that represents the food identity
        # (e.g. for {dry, mix, sauce, spaghetti}, identity_tokens = {sauce}).
        # Inheritance walks only along subsets that share these.

    @property
    def n_sources(self) -> int:
        return sum(1 for v in self.sources.values() if v)


def build_concept_index() -> dict[frozenset, ConceptNode]:
    rows = load_rows()
    print(f"  loaded {len(rows):,} parsed rows")

    by_concept: dict[frozenset, dict] = defaultdict(
        lambda: {"sr28": [], "fndds": [], "esha": [], "descs": [],
                  "first_frag_tokens": set(), "fallback_frag_tokens": None}
    )
    # Track tokens that appear as the FIRST fragment's last word ("identity
    # head" in the source description). These are the canonical food-class
    # words like sauce, jelly, cheese, milk, soup, dressing.
    head_count: Counter = Counter()
    n_skipped_degenerate = 0

    for row in rows:
        c = concept_tokens_from_text(row.full_desc)
        if not c:
            continue
        # Per-entry identity = tokens from the entry's FIRST FRAGMENT,
        # after stripping CONCEPT_STRIP and descriptor categories.
        # Two flavors of empty-after-strip:
        #   first_raw is in USAGE_PREFIXES (topping, dish, snack, ...)
        #     → entry is degenerate ("Topping, pork" pollutes pork).
        #   first_raw is in TRUE category prefix (Spices, Vegetables, Nut...)
        #     → keep entry, fall back to whole-concept tokens as identity.
        # The split prevents `Topping, pork` from creating a {pork} stub
        # while letting `Spices, garlic powder` create {garlic, powder}.
        first_raw = tokens(row.first_frag)
        first_id = frozenset(
            t for t in first_raw
            if t not in CONCEPT_STRIP
            and t not in FIRST_FRAG_DESCRIPTORS
            and len(t) > 1 and not t.isdigit()
        )
        is_fallback = False
        if not first_id:
            if set(first_raw) & USAGE_PREFIXES:
                n_skipped_degenerate += 1
                continue
            # True-prefix entry (Spices, Nuts, Vegetable…) — fall back to
            # whole-concept tokens so the entry can still be matched.
            # BUT: if the whole-concept tokens are also entirely descriptor
            # / weak-identity (e.g. "Vegetables, fresh" collapses to just
            # `{fresh}`), the entry has no real food identity — skip it.
            if not (c - FIRST_FRAG_DESCRIPTORS - WEAK_IDENTITY):
                n_skipped_degenerate += 1
                continue
            first_id = c
            is_fallback = True
        node = by_concept[c]
        node[row.source].append((row.code, row.full_desc))
        node["descs"].append(row.full_desc)
        if is_fallback:
            # Intersection across fallback entries → core tokens shared by
            # every source description for this concept.  Stops a single
            # "candy, hard, lollipop, lemon" entry from forcing `lemon` into
            # the identity of the generic {lollipop, hard} concept.
            if node["fallback_frag_tokens"] is None:
                node["fallback_frag_tokens"] = set(first_id)
            else:
                node["fallback_frag_tokens"] &= first_id
        else:
            node["first_frag_tokens"] |= first_id
        # First fragment's last token = source's identity head for this row
        if first_raw:
            head_tok = first_raw[-1]
            if head_tok not in CONCEPT_STRIP and len(head_tok) > 1:
                head_count[head_tok] += 1

    # Identity tokens — used by the SURFACE-side hard filter and the
    # surface_has_identity check. Broad on purpose: any non-stripped token
    # that appears in any concept's id is food vocabulary, including
    # second-fragment specifiers like `flatbread`/`granola` that have low
    # head_count. The concept-side drift check uses _HEAD_COUNT separately,
    # so broadening this set doesn't over-trigger drift.
    from rft import PROTECTED_HEADS as PH
    identity_tokens = set(PH) | SURFACE_ONLY_IDENTITY
    for cid in by_concept:
        identity_tokens |= (cid - NON_IDENTITY_FACETS)
    # Stash on a module global for route() to inspect
    global _IDENTITY_TOKENS, _HEAD_COUNT
    _IDENTITY_TOKENS = frozenset(identity_tokens)
    _HEAD_COUNT = head_count

    # Prefer source entries whose original description does NOT start with
    # a carrier word (Babyfood, Lunchmeat, Dish, etc.). When a concept like
    # {cookie} has both "Babyfood, cookies" and "Cookies, shortbread, plain"
    # as SR28 entries, we want the second one as the canonical representative
    # so backtracking returns clean descriptions, not babyfood ones.
    def source_pref(entry):
        code, desc = entry
        first = desc.split(",")[0].strip().lower()
        is_carrier = first in CURATED_CARRIERS
        # tiebreak: shorter descriptions are usually more canonical
        return (is_carrier, len(desc))

    def desc_pref(desc):
        first = desc.split(",")[0].strip().lower()
        # Treat both CURATED_CARRIERS (Babyfood, Pillsbury, ...) AND
        # CATEGORY_PREFIXES (Spice, Topping, Dish, ...) as low-priority
        # prefixes when picking the canonical name.
        is_low = first in CURATED_CARRIERS or first in CATEGORY_PREFIXES
        return (is_low, len(desc), desc)

    concepts: dict[frozenset, ConceptNode] = {}
    for cid, info in by_concept.items():
        # canonical name: prefer non-carrier-prefixed descriptions, then
        # shortest. Stops "babyfood, dinner, macaroni and cheese, strained"
        # appearing as the canonical for the {cheese, dinner, macaroni}
        # concept when a non-babyfood option exists.
        canonical = min(info["descs"], key=desc_pref)
        # Position-based identity: prefer clean first-fragment tokens from
        # entries whose head was a real food word.  If every entry for this
        # concept had a category-prefixed head (candy, vegetables, …), fall
        # back to the intersection of their whole-concept tokens — this
        # strips flavour/brand tokens that only appear in some entries.
        if info["first_frag_tokens"]:
            concept_idents = info["first_frag_tokens"] & cid
        else:
            fb = info.get("fallback_frag_tokens")
            if fb is not None:
                concept_idents = fb & cid
            else:
                concept_idents = set()
        sources = {}
        for k in ("sr28", "fndds", "esha"):
            entries = info.get(k, [])
            if entries:
                entries = sorted(entries, key=source_pref)
            sources[k] = entries
        concepts[cid] = ConceptNode(
            concept_id=cid,
            canonical_name=canonical,
            sources=sources,
            identity_tokens=frozenset(concept_idents),
        )
    if n_skipped_degenerate:
        print(f"  skipped {n_skipped_degenerate:,} degenerate entries "
              f"(first-frag = category-prefix only)")
    return concepts


def build_token_to_concepts(concepts: dict[frozenset, ConceptNode]) -> dict[str, set[frozenset]]:
    """Inverted index: token → set of concept_ids that contain it."""
    idx: dict[str, set[frozenset]] = defaultdict(set)
    for cid in concepts:
        for t in cid:
            idx[t].add(cid)
    return idx


# ---------------------------------------------------------------------------
# Route a surface
# ---------------------------------------------------------------------------

# Populated at build_concept_index time
_IDENTITY_TOKENS: frozenset = frozenset()
_HEAD_COUNT: Counter = Counter()
# Threshold: a token that heads >= this many concepts is a "food-family head"
# and triggers heavy drift penalty when it's an extra.
FOOD_FAMILY_HEAD_THRESHOLD = 30

# ---------------------------------------------------------------------------
# Token role table — surface-side semantics.
# Drift is a surface-vocabulary problem: a token's role depends on which side
# of the surface↔concept comparison it shows up on. These three sets handle
# the asymmetry rather than patching it after-the-fact.
# ---------------------------------------------------------------------------

# Tokens that are IDENTITY when they appear in a SURFACE but DESCRIPTOR when
# they appear as concept-extras. Solves the chicken-fat asymmetry: SR28 says
# "Chicken, broiler, breast, fat removed" (concept-side `fat` is descriptor
# noise) while retail says "fat free milk" (surface-side `fat` constrains
# the match). When `fat` is a surface token, the matched concept must also
# contain it. When `fat` is a concept-extra absent from surface, no drift.
SURFACE_ONLY_IDENTITY = {
    # Macronutrient/quantity discriminators — retail uses these as identity
    "fat", "sugar", "sodium", "salt",
    "calorie", "calories", "carb", "carbs",
    "protein", "fiber", "starch",
    "caffeine",
    # Polarity/level modifiers paired with macronutrients
    "free", "low", "high", "reduced", "no", "non", "added", "removed",
    "lite", "light", "lean",
    # State that surfaces use to discriminate but concepts treat as suffix
    "whole", "skim", "fortified", "enriched", "natural",
    "instant",   # "instant cocoa" vs "cocoa" — surface-side discriminator
    "decaf", "decaffeinated",
}

# Form-words that DO change product identity (a `bar` of X is different from
# X, X powder ≠ X, X chips ≠ X). When concept-extra, treat as drift.
# This is narrower than `FORM_WORDS` because cuts like fillet/slice/cube
# don't change food family — only certain form-suffixes do.
FORM_DRIFT = {
    "bar", "bars",
    "powder", "powders",
    "chip", "chips",
    "flake", "flakes",
    "stick", "sticks",
    "ball", "balls",
    "loaf", "loaves",
    "crumble", "crumbles",
}

# Surface tokens that LOOK like identity (they appear as concept heads
# somewhere in the DB) but on their own don't anchor a specific food.
# When surface_identity ⊆ WEAK_IDENTITY, no real food noun is present —
# cap verdict at WEAK so "mixed herbs" doesn't STRONG-route to "mixed seeds"
# and "fresh" doesn't STRONG-route to "fresh fish".
WEAK_IDENTITY = {
    "mixed", "mix",
    "fine", "fines",
    "plain", "regular", "generic",
    "assorted", "assortment", "variety",
    "homemade",
    "fresh", "dried", "frozen",
    "dry", "raw", "cooked", "ground",
}

# Identity implications: when a surface token is present, treat the surface
# as if it also contains the implied parent category. Used ONLY by the
# position-based concept identity hard filter — lets retail-style surfaces
# ("ham steak", "flatbread", "salmon fillet") match concepts whose first
# fragment is the parent category ("Pork, cured, ham", "Bread, flatbread",
# "Fish, salmon"). Doesn't change actual surface tokens for scoring.
IDENTITY_IMPLICATIONS = {
    # meat parent categories
    "ham": "pork",
    "bacon": "pork",
    "prosciutto": "pork",
    "sausage": "pork",   # mostly pork; cleaning later if needed
    "salami": "pork",
    # bread parent
    "flatbread": "bread",
    "naan": "bread",
    "pita": "bread",
    "tortilla": "bread",
    "bagel": "bread",
    "biscuit": "bread",
    "roll": "bread",
    # fish parent
    "salmon": "fish",
    "tuna": "fish",
    "trout": "fish",
    "cod": "fish",
    "tilapia": "fish",
    "halibut": "fish",
    "snapper": "fish",
    "bass": "fish",
    # shellfish parent
    "shrimp": "shellfish",
    "lobster": "shellfish",
    "crab": "shellfish",
    "scallop": "shellfish",
    "oyster": "shellfish",
    "clam": "shellfish",
    "mussel": "shellfish",
    # cheese family — every variety implies cheese
    "mozzarella": "cheese",
    "cheddar": "cheese",
    "colby": "cheese",
    "gouda": "cheese",
    "queso": "cheese",
    "parmesan": "cheese",
    "ricotta": "cheese",
    "asiago": "cheese",
    "feta": "cheese",
    "swiss": "cheese",
    "brie": "cheese",
    "provolone": "cheese",
    "havarti": "cheese",
    "muenster": "cheese",
    "gruyere": "cheese",
    "camembert": "cheese",
    "cotija": "cheese",
    "manchego": "cheese",
    "mascarpone": "cheese",
    "paneer": "cheese",
    "gorgonzola": "cheese",
    "roquefort": "cheese",
    "fontina": "cheese",
    "neufchatel": "cheese",
    "romano": "cheese",
    # olive varieties
    "kalamata": "olive",
    "manzanilla": "olive",
    "castelvetrano": "olive",
    "cerignola": "olive",
    "picholine": "olive",
    # pepper varieties
    "jalapeno": "pepper",
    "pepperoncini": "pepper",
    "piquillo": "pepper",
    "habanero": "pepper",
    "calabrese": "pepper",
    "poblano": "pepper",
    "serrano": "pepper",
    "anaheim": "pepper",
    # pickle parents
    "gherkin": "pickle",
    "cornichon": "pickle",
    # cookie varieties
    "shortbread": "cookie",
    "snickerdoodle": "cookie",
    "biscotti": "cookie",
    "pizzelle": "cookie",
    "madeleine": "cookie",
    "macaroon": "cookie",
    "meringue": "cookie",
    # frozen dessert varieties — all map to ice cream parent
    "gelato": "ice cream",
    "sherbet": "ice cream",
    "sorbet": "ice cream",
    "popsicle": "ice cream",
    "creamsicle": "ice cream",
    "dreamsicle": "ice cream",
    "drumstick": "ice cream",
    "froyo": "frozen yogurt",
    "fudgsicle": "ice cream",
    "spumoni": "ice cream",
    # candy varieties — every candy form implies candy parent
    "gummy": "candy",
    "gummi": "candy",
    "taffy": "candy",
    "lollipop": "candy",
    "nougat": "candy",
    "licorice": "candy",
    "lozenge": "candy",
    "marshmallow": "candy",
    "truffle": "chocolate",
    "bonbon": "chocolate",
    "ganache": "chocolate",
    "praline": "chocolate",
    "fudge": "chocolate",
    "bark": "chocolate",
    # bread varieties (parent=bread)
    "ciabatta": "bread",
    "focaccia": "bread",
    "baguette": "bread",
    "brioche": "bread",
    "sourdough": "bread",
    "rye": "bread",
    "pumpernickel": "bread",
    "challah": "bread",
    "breadstick": "bread",
    "croissant": "bread",
    "bun": "bread",
    "buns": "bread",
    "bolillo": "bread",
    # cake varieties (parent=cake)
    "cupcake": "cake",
    "cheesecake": "cake",
    "twinkie": "cake",
    "twinkies": "cake",
    "shortcake": "cake",
    # frozen dessert — already had gelato/sorbet/etc.
    "ho ho": "cake",
    # soda parents
    "cola": "soda",
    # dairy sub-types
    "half": "cream",
    # nut/seed varieties — most are already in concepts via CATEGORY_PREFIX
    # fallback, but these help ambiguous surfaces
    "pignoli": "pine nut",
    "pepita": "seed",
    # pasta shapes — every shape implies pasta
    "spaghetti": "pasta",
    "linguine": "pasta",
    "linguini": "pasta",
    "fettuccine": "pasta",
    "fettucini": "pasta",
    "penne": "pasta",
    "rigatoni": "pasta",
    "rotini": "pasta",
    "fusilli": "pasta",
    "farfalle": "pasta",
    "orzo": "pasta",
    "ziti": "pasta",
    "ravioli": "pasta",
    "lasagna": "pasta",
    "gnocchi": "pasta",
    "tortellini": "pasta",
    "manicotti": "pasta",
    "pappardelle": "pasta",
    "tagliatelle": "pasta",
    "cannelloni": "pasta",
    "vermicelli": "pasta",
    "capellini": "pasta",
    "bowtie": "pasta",
    "ditalini": "pasta",
    "gemelli": "pasta",
    "ramen": "noodle",
    "udon": "noodle",
    "soba": "noodle",
    # sausage variants — children imply sausage parent
    "bratwurst": "sausage",
    "kielbasa": "sausage",
    "knockwurst": "sausage",
    "knackwurst": "sausage",
    "andouille": "sausage",
    "chorizo": "sausage",
    "polska": "sausage",
}


def find_ancestor_with_source(target_tokens: frozenset, source: str,
                               concepts: dict, token_idx: dict,
                               identity_tokens: frozenset = frozenset()
                               ) -> "ConceptNode | None":
    """Backtrack along the identity-token leg.

    target = {dry, mix, newburg, sauce} with identity_tokens={sauce}
    For source=sr28: walk subsets that include 'sauce' — find {sauce, mix},
    {sauce}, etc. NOT {mix} (which jumps to a different food family).
    """
    candidate_ids: set[frozenset] = set()
    for t in target_tokens:
        candidate_ids |= token_idx.get(t, set())

    # If we have identity tokens, ONLY walk subsets that share at least one.
    # If target has no identity tokens (rare), allow any subset as fallback.
    require_identity = bool(identity_tokens)

    best = None
    best_size = -1
    for cid in candidate_ids:
        if not cid.issubset(target_tokens):
            continue
        if require_identity and not (cid & identity_tokens):
            continue
        c = concepts[cid]
        prov = c.sources.get(source) or []
        if not prov:
            continue
        if len(cid) > best_size:
            best_size = len(cid)
            best = c
    # Empty fallback only if no identity-respecting ancestor was found
    if best is None and not require_identity:
        if frozenset() in concepts:
            c = concepts[frozenset()]
            if c.sources.get(source):
                return c
    return best


# Composite-joiner pattern. Splits "hummus with flatbread" into ["hummus",
# "flatbread"]; "yogurt & granola" into ["yogurt", "granola"]; etc.
# Whole-surface concept matching runs FIRST in route() — so single-dish
# names like "mac and cheese" (a real FNDDS leaf) never reach the splitter.
COMPOSITE_JOINER = re.compile(r"\s+(?:with|&|\+|and)\s+", re.IGNORECASE)


def _try_composite(surface: str, concepts, token_idx,
                    brand_registry) -> dict | None:
    """Detect a composite product (e.g. 'Hummus with Flatbread').

    Split the original surface on with/and/&/+ and route each piece
    independently (without re-entering composite detection). If 2+ pieces
    each yield EXACT or STRONG, the surface is a composite product —
    return primary + accompaniments. Otherwise None.
    """
    pieces = [p.strip() for p in COMPOSITE_JOINER.split(surface) if p.strip()]
    if len(pieces) < 2:
        return None
    routed: list[tuple[str, dict]] = []
    for p in pieces:
        sub = route(p, concepts, token_idx, brand_registry,
                    _no_composite=True)
        if sub["verdict"] in ("EXACT", "STRONG"):
            routed.append((p, sub))
    if len(routed) < 2:
        return None
    primary = routed[0][1]
    secondary = [r[1] for r in routed[1:]]
    return {
        "pieces": [r[0] for r in routed],
        "primary": primary,
        "secondary": secondary,
    }


def route(surface: str, concepts: dict[frozenset, ConceptNode],
          token_idx: dict[str, set[frozenset]],
          brand_registry: set[str] = None,
          _no_composite: bool = False) -> dict:
    surf = concept_tokens_from_text(surface, brand_registry)
    if not surf:
        return {"verdict": "NO_IDENTITY", "surface_concept": frozenset(),
                "concept": None, "shared": frozenset(),
                "missing": frozenset(), "extra": frozenset()}

    # Tier 1: concepts containing at least 1 surface token, then filter to
    # those that share enough of the surface. Aggressively prune to keep
    # the scoring loop fast at 462k-product scale.
    counter: Counter = Counter()
    for t in surf:
        for cid in token_idx.get(t, ()):
            counter[cid] += 1

    if not counter:
        return {"verdict": "NO_MATCH", "surface_concept": surf,
                "concept": None, "shared": frozenset(),
                "missing": surf, "extra": frozenset()}

    # Min-shared threshold scales with surface size. For surface≤2 require
    # 1 shared (otherwise we lose subset matches). For larger, require ≥2.
    min_shared = 1 if len(surf) <= 2 else 2
    # Also include any concept that's a subset of surface (concept ⊆ surf).
    # These have shared == len(cid). Always relevant.
    candidate_ids = {cid for cid, n in counter.items() if n >= min_shared}
    # Add subset-of-surface concepts even if shared count is below threshold.
    for t in surf:
        for cid in token_idx.get(t, ()):
            if cid.issubset(surf):
                candidate_ids.add(cid)
    # If still empty (no concept shared enough tokens), fall back to all
    # candidates with at least 1 shared token (rare path).
    if not candidate_ids:
        candidate_ids = set(counter.keys())
    if not candidate_ids:
        return {"verdict": "NO_MATCH", "surface_concept": surf,
                "concept": None, "shared": frozenset(),
                "missing": surf, "extra": frozenset(),
                "backtracked": {"sr28": None, "fndds": None, "esha": None}}

    # Three-tier extra classification:
    #   food_family_extras  — tokens that head MANY concepts (salad, pasta,
    #                          cheese, dressing). These mean the matched
    #                          concept is a DIFFERENT food family from what
    #                          the surface asked for. HEAVY penalty.
    #   minor_id_extras     — identity tokens that head a few concepts
    #                          (crescent, manuka). Medium penalty.
    #   facet_extras        — descriptors / modifiers / form / state. Light.
    FACET_EXTRA = (FORM_WORDS | RETAIL_ATTRS_ROUTING | MODIFIER_TOKENS
                   | SURFACE_MODIFIERS | RETAIL_ATTRS_NONROUTING
                   | CATEGORY_PREFIXES | VERBOSITY)

    # If the surface has NO identity-token of its own, drift detection is
    # weaker (we don't know the food family). In that case, treat all
    # identity-extras as minor.
    surface_has_identity = bool(surf & _IDENTITY_TOKENS)

    # Implied parents from surface tokens (flatbread→bread, ham→pork, etc.)
    # When a concept-extra is the implied parent of a surface child, it's
    # NOT food-family drift — it's the genus of the species in surface.
    implied_parents = set()
    for t in surf:
        parent = IDENTITY_IMPLICATIONS.get(t)
        if parent:
            implied_parents.add(parent)

    # Position-based concept identity hard filter: drop candidates whose
    # CONCEPT identity (first-frag tokens) isn't fully present in the
    # surface. Identity implications expand surface for filter purposes
    # only — surface "ham" implies "pork", "flatbread" implies "bread", etc.
    # Lets retail child-tokens match nutrition-DB parent-headed concepts
    # without bloating the surface for scoring.
    surf_for_filter = set(surf)
    for t in surf:
        parent = IDENTITY_IMPLICATIONS.get(t)
        if parent:
            surf_for_filter.add(parent)
    pos_filtered = {
        cid for cid in candidate_ids
        if not concepts[cid].identity_tokens
        or concepts[cid].identity_tokens.issubset(surf_for_filter)
    }
    candidate_ids = pos_filtered

    scored = []
    for cid in candidate_ids:
        shared = surf & cid
        missing = surf - cid
        extra = cid - surf
        cov_surf = len(shared) / len(surf)
        cov_concept = len(shared) / len(cid) if cid else 0

        # Concept-extra classification via the token role table:
        #  facet_extras    — descriptors/modifiers/form (light penalty)
        #  food_family     — identity tokens that signal a different food
        #                    category (heavy penalty)
        #  minor_id_extras — identity tokens that just specialize the food
        #                    (medium penalty)
        # SURFACE_ONLY_IDENTITY tokens are descriptor on concept side, so
        # they fall to facet_extras even when they're identity on surface.
        food_family_extras = set()
        minor_id_extras = set()
        facet_extras = set()
        for t in extra:
            if t in SURFACE_ONLY_IDENTITY:
                # Asymmetric: identity in surface (already enforced via the
                # hard identity filter), descriptor when concept-extra.
                facet_extras.add(t)
            elif t in implied_parents:
                # Concept's extra is the parent category of a surface child
                # (e.g. surface=flatbread, concept-extra=bread). Genus is
                # not drift — surface implied it.
                facet_extras.add(t)
            elif t in FACET_EXTRA and t not in FORM_DRIFT:
                facet_extras.add(t)
            elif t in FORM_DRIFT:
                # Form-words that change product identity (bar, powder, chip)
                food_family_extras.add(t)
            elif (surface_has_identity
                  and _HEAD_COUNT.get(t, 0) >= FOOD_FAMILY_HEAD_THRESHOLD):
                # Concept-side drift: token heads many distinct concepts in
                # the nutrition DB → its presence as an extra signals a
                # different food family. _HEAD_COUNT (not _IDENTITY_TOKENS)
                # is the right discriminator here — many identity tokens
                # are leaf-level specifiers, not food-family heads.
                food_family_extras.add(t)
            else:
                minor_id_extras.add(t)

        # Missing-side penalty: surface tokens NOT in the matched concept.
        # If the missing token is an IDENTITY token (food-class word like
        # macaroni, jelly, dressing), the matched concept is missing the
        # core food → big penalty. Other missing tokens are just under-spec.
        identity_missing = {t for t in missing if t in _IDENTITY_TOKENS}
        descriptor_missing = missing - identity_missing

        score = (cov_surf
                 - 0.55 * len(food_family_extras)   # drift — wrong family
                 - 0.10 * len(minor_id_extras)      # specificity additions
                 - 0.03 * len(facet_extras)         # form/state/descriptor
                 - 0.30 * len(identity_missing)     # surface had a food-token
                                                    #   the concept lacks
                 - 0.02 * len(descriptor_missing))  # surface under-specified

        scored.append({
            "cid": cid, "shared": shared, "missing": missing, "extra": extra,
            "food_family_extras": food_family_extras,
            "minor_id_extras": minor_id_extras,
            "facet_extras": facet_extras,
            "cov_surf": cov_surf, "cov_concept": cov_concept, "score": score,
        })

    # Tiebreak: prefer concepts whose identity tokens overlap with the
    # surface's identity tokens. Resolves "raw honey" picking {honey}
    # over {raw} when both have the same coverage.
    surface_identity = surf & _IDENTITY_TOKENS
    for s in scored:
        s["identity_overlap"] = len(s["cid"] & surface_identity)

    # HARD FILTER for misroute prevention: if the surface contains identity
    # tokens (food-class words like blackberry, puree, milk, salt), the
    # matched concept MUST contain all of them. This prevents "blackberry
    # puree → tomato puree", "fresh blackberry → vegetables, fresh",
    # "salt water → cod, dried, salted, salt removed". If no candidate
    # covers all surface identity tokens, we'll fall back to candidates
    # that cover at least one — verdict will then reflect the gap.
    if surface_identity:
        full_id = [s for s in scored
                   if surface_identity.issubset(s["cid"])]
        if full_id:
            scored = full_id
        else:
            # Fall back to candidates that have at least ONE surface identity
            partial_id = [s for s in scored if s["identity_overlap"] >= 1]
            if partial_id:
                scored = partial_id

    if not scored:
        # Position-based identity filter eliminated every candidate — the
        # nutrition DB has no concept whose identity head is in the surface.
        # Return NEEDS_NEW_CONCEPT, then composite detection still gets a
        # chance below.
        result = {
            "verdict": "NEEDS_NEW_CONCEPT",
            "surface_concept": surf,
            "concept": None,
            "shared": frozenset(),
            "missing": surf,
            "extra": frozenset(),
            "cov_surf": 0.0,
            "cov_concept": 0.0,
            "alternatives": [],
            "backtracked": {"sr28": None, "fndds": None, "esha": None},
            "composite": None,
        }
        if (not _no_composite
                and COMPOSITE_JOINER.search(surface or "")):
            comp = _try_composite(surface, concepts, token_idx, brand_registry)
            if comp:
                primary = comp["primary"]
                sec_list = comp["secondary"]
                result["verdict"] = "COMPOSITE"
                result["concept"] = primary["concept"]
                result["backtracked"] = primary["backtracked"]
                result["composite"] = {
                    "pieces": comp["pieces"],
                    "primary_concept": ("|".join(sorted(primary["concept"].concept_id))
                                        if primary["concept"] else ""),
                    "primary_canonical": (primary["concept"].canonical_name
                                          if primary["concept"] else ""),
                    "secondary": [
                        {
                            "concept": ("|".join(sorted(s["concept"].concept_id))
                                        if s["concept"] else ""),
                            "canonical": (s["concept"].canonical_name
                                          if s["concept"] else ""),
                            "verdict": s["verdict"],
                        }
                        for s in sec_list
                    ],
                }
        return result

    scored.sort(key=lambda x: (-x["score"],
                               len(x["food_family_extras"]),
                               -x["identity_overlap"],   # higher overlap better
                               len(x["minor_id_extras"]),
                               len(x["extra"]),
                               len(x["cid"])))
    best = scored[0]
    cid = best["cid"]
    concept = concepts[cid]

    # Verdict — based on identity match, not raw coverage. Missing-facet
    # tokens (dried, fresh, raw, sliced) and food-family extras (the wrong
    # food category) drive the verdict, not just shared/missing counts.
    best_id_missing = best.get("identity_missing", best["missing"])
    if best.get("identity_missing") is None:
        # fallback for older callers
        best_id_missing = {t for t in best["missing"]
                           if t in _IDENTITY_TOKENS}
    n_id_missing = len(best_id_missing)
    n_ff_extras = len(best["food_family_extras"])
    n_total_missing = len(best["missing"])
    n_total_extras = len(best["extra"])

    if n_total_missing == 0 and n_total_extras == 0:
        verdict = "EXACT"
    elif n_id_missing == 0 and n_ff_extras == 0:
        verdict = "STRONG"
    elif best["cov_surf"] >= 0.5 and n_id_missing <= 1:
        verdict = "WEAK"
    else:
        verdict = "NEEDS_NEW_CONCEPT"

    # Final guard: if the surface had NO identity-class tokens
    # (e.g. "fine herbs" → {fine} after stripping `herbs` as category),
    # we can't be confident in any match — cap at NEEDS_NEW_CONCEPT.
    if not surface_has_identity:
        if verdict in ("EXACT", "STRONG", "WEAK"):
            verdict = "NEEDS_NEW_CONCEPT"
    else:
        # If the surface_identity is ENTIRELY weak-identity tokens (mixed,
        # fine, fresh — words that look like heads but don't anchor a real
        # food), cap at WEAK. Prevents "mixed herbs" → STRONG mixed seeds.
        strong_id = surface_identity - WEAK_IDENTITY
        if not strong_id and verdict in ("EXACT", "STRONG"):
            verdict = "WEAK"

    # Backtrack each source independently. If the matched concept doesn't
    # have a code in some source, walk down the subset chain to find the
    # closest ancestor that does. This is the "tree inheritance" path:
    # new concepts added without codes inherit from their parent.
    backtracked: dict[str, dict] = {}
    for src in ("sr28", "fndds", "esha"):
        own_prov = concept.sources.get(src) or []
        if own_prov:
            code, desc = own_prov[0]
            backtracked[src] = {
                "code": code, "desc": desc,
                "inherited_from": None,
                "level": "exact",
            }
            continue
        # Walk down subsets of the matched concept along the identity leg
        # (so newburg sauce mix doesn't inherit from {mix} → snack mix).
        target = cid
        anc = find_ancestor_with_source(
            target, src, concepts, token_idx,
            identity_tokens=concept.identity_tokens)
        if anc:
            code, desc = anc.sources[src][0]
            backtracked[src] = {
                "code": code, "desc": desc,
                "inherited_from": sorted(anc.concept_id),
                "level": "inherited",
            }
        else:
            backtracked[src] = None

    result = {
        "verdict": verdict,
        "surface_concept": surf,
        "concept": concept,
        "shared": best["shared"],
        "missing": best["missing"],
        "extra": best["extra"],
        "cov_surf": best["cov_surf"],
        "cov_concept": best["cov_concept"],
        "alternatives": scored[1:5],
        "backtracked": backtracked,   # per-source code with inheritance
        "composite": None,
    }

    # Composite detection. Triggers when a joiner is present AND the whole-
    # surface match left an identity token uncovered (or failed entirely).
    # This protects:
    #   "cocoa with marshmallows" → whole-surface STRONG to a real concept
    #     that covers both ids → keep whole, don't decompose.
    #   "hummus with flatbread" → whole-surface STRONG but flatbread is an
    #     uncovered identity → decompose into primary+secondary.
    #   "mac and cheese" → EXACT, never reaches this branch.
    has_joiner = bool(COMPOSITE_JOINER.search(surface or ""))
    needs_composite = (
        not _no_composite
        and has_joiner
        and verdict != "EXACT"
        and (verdict == "NEEDS_NEW_CONCEPT" or len(best_id_missing) > 0)
    )
    if needs_composite:
        comp = _try_composite(surface, concepts, token_idx, brand_registry)
        if comp:
            primary = comp["primary"]
            sec_list = comp["secondary"]
            # Primary drives the per-source codes (the head food). Secondary
            # is recorded but doesn't feed nutrition — recipe substitution
            # should refuse composites for single-ingredient calls.
            result["verdict"] = "COMPOSITE"
            result["concept"] = primary["concept"]
            result["backtracked"] = primary["backtracked"]
            result["composite"] = {
                "pieces": comp["pieces"],
                "primary_concept": ("|".join(sorted(primary["concept"].concept_id))
                                    if primary["concept"] else ""),
                "primary_canonical": (primary["concept"].canonical_name
                                      if primary["concept"] else ""),
                "secondary": [
                    {
                        "concept": ("|".join(sorted(s["concept"].concept_id))
                                    if s["concept"] else ""),
                        "canonical": (s["concept"].canonical_name
                                      if s["concept"] else ""),
                        "verdict": s["verdict"],
                    }
                    for s in sec_list
                ],
            }

    return result


# ---------------------------------------------------------------------------
# Pretty test runner
# ---------------------------------------------------------------------------

def show(label: str, surface: str, concepts, token_idx,
         brand_registry: set[str] = None):
    print(f"\n{'='*70}\n{label}: {surface!r}\n{'='*70}")
    res = route(surface, concepts, token_idx, brand_registry)
    print(f"  surface concept : {sorted(res['surface_concept'])}")
    print(f"  verdict         : {res['verdict']}")
    if res["concept"]:
        c = res["concept"]
        print(f"  matched concept : {sorted(c.concept_id)}")
        print(f"  canonical name  : {c.canonical_name}")
        print(f"  shared / miss / extra: {sorted(res['shared'])} / "
              f"{sorted(res['missing'])} / {sorted(res['extra'])}")
        print(f"  per-source codes (with inherited fallback):")
        bt = res.get("backtracked") or {}
        for src in ("sr28", "fndds", "esha"):
            info = bt.get(src)
            if info is None:
                print(f"    {src:5s}: — (no code in this source, no ancestor either)")
                continue
            tag = "EXACT" if info["level"] == "exact" else \
                  f"INHERITED from {info['inherited_from']}"
            print(f"    {src:5s}: [{info['code']:>10}] {info['desc'][:55]}  ({tag})")


def main():
    print("Building concept index from parsed_unified.csv…")
    concepts = build_concept_index()
    token_idx = build_token_to_concepts(concepts)
    print(f"  {len(concepts):,} unique concepts across "
          f"{len(token_idx):,} index tokens")

    n_3way = sum(1 for c in concepts.values() if c.n_sources == 3)
    n_2way = sum(1 for c in concepts.values() if c.n_sources == 2)
    n_1way = sum(1 for c in concepts.values() if c.n_sources == 1)
    print(f"    3-source: {n_3way:,}   2-source: {n_2way:,}   "
          f"1-source: {n_1way:,}")

    TESTS = [
        "garlic powder",
        "garlic chips",
        "garlic clove",
        "garlic granules",
        "minced garlic",
        "baby arugula leaves",
        "basil leaves",
        "bay leaves",
        "celery leaves",
        "kale leaves",
        "alfalfa sprout seeds",
        "popcorn shrimp",
        "raw shrimp",
        "rock shrimp",
        "alaska king crab meat",
        "alaskan king crabmeat",
        "almond bread",
        "artisan bread",
        "hawaiian sweet bread",
        "bread yeast",
        "pillsbury crescent roll",
        "pillsbury pie crust",
        "100% bran",
        "habanero pepper jelly",
        "tomato ketchup",
        "frozen mango",
        "fat free milk",
        "harris teeter milk",
        "mushroom pieces and stems",
        "center cut reduced fat bacon",
        "chunk light tuna in water",
        "real mayonnaise",
        "sliced almonds",
        "raw almonds",
        "whole almonds",
        "root beer",
        "pink himalayan salt",
        "elbow macaroni",
        "graham cracker crust",
        "boboli pizza crust",
        "twix caramel cookie bars",
        "kraft singles american cheese",
        # Backtracking / inheritance demo
        "mayonnaise",
        "chipotle mayonnaise",
        "lime chipotle mayonnaise",
        "habanero pepper jelly",
        "grape jelly",
        "jelly",
    ]
    for s in TESTS:
        show(s, s, concepts, token_idx)


if __name__ == "__main__":
    main()
