"""Deterministic food-slot registry helpers for HTC codes.

The HTC join key is intentionally identity-stable:

    group | family | food_slot | 0 | 0 | 0 | check

Form, processing, ptype, flavor, and claims stay as separate facets.  That
keeps recipe "garlic" joinable to retail garlic rows even when the retail SKU
is fresh, minced, peeled, or otherwise more specific.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:  # pragma: no cover - script/package dual-use
    from .cheese_identities import cheese_identity_from_text
except Exception:  # pragma: no cover
    from htc.cheese_identities import cheese_identity_from_text  # type: ignore

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
RESERVED_SLOT = "00"

HERE = Path(__file__).resolve().parent
DEFAULT_REGISTRY = HERE / "food_slot_registry.csv"

RULE_B_PREFIXES = (
    "Frozen > Single Entrees",
    "Frozen > Family Entrees",
    "Frozen > Appetizers",
    "Frozen > Pizza",
    "Meal > Sandwiches",
    "Meal > Salads",
    "Meal > Pasta Dishes",
    "Meal > Composite Dishes",
    "Meal > Sushi",
    "Pantry > Spices & Seasonings > Seasoning",
    "Pantry > Sauces & Salsas > Pasta Sauce",
    "Pantry > Sauces & Salsas > BBQ Sauce",
    "Pantry > Soup",
    "Pantry > Dips",
    "Pantry > Salsa",
)

RULE_B_PIDS = {
    "Spice Blend", "Seasoning", "Single Entree", "Family Entree",
    "Entree", "Pasta Sauce", "BBQ Sauce", "Hot Sauce", "Marinade",
    "Pizza", "Sandwich", "Salad", "Composite Dish", "Pasta Dish",
    "Sauce", "Soup", "Salsa", "Dip",
}

PLAIN_MODIFIERS = {"", "plain", "regular", "original", "classic", "natural"}

# Tokens that are CLAIMS or PROCESSING/FORM facets per HTC_SPEC.md, NOT food
# identity. The encoder used to accept these as `flavor`/`variant` and
# concatenate them into food_name → minted distinct food_slots for what is
# the SAME food (Buttermilk lowfat ≠ Buttermilk cultured ≠ Buttermilk whole
# all share canonical_path "Dairy > Buttermilk" and SHOULD share one bucket).
#
# Per spec:
#   - fat content (whole/skim/lowfat/etc)  → claims_hex bit 10 (low_fat)
#   - sugar/sodium claims                   → claims_hex bits 8–11
#   - dietary claims (organic, gluten_free) → claims_hex bits 0–7
#   - cultured/fermented/pasteurized        → htc_code position 6 (processing)
#   - fortified/enriched                    → htc_code position 6 (processing)
#
# These belong OUT of the food_slot identity. _primary_flavor() drops them.
CLAIMS_TOKENS = {
    # Fat content
    "lowfat", "low fat", "whole", "skim", "fat free", "fatfree",
    "non fat", "nonfat", "reduced fat", "1 percent", "2 percent",
    "1%", "2%", "0%", "full fat",
    # Lactose
    "lactose free", "lactose-free", "lactose_free",
    # Sugar
    "sugar free", "no sugar", "no added sugar", "reduced sugar",
    # Fortified / enriched
    "fortified", "enriched", "vitamin d", "calcium fortified",
    # Sodium
    "low sodium", "reduced sodium", "no salt added",
    # Diet/sourcing claims
    "organic", "non gmo", "non-gmo", "gluten free", "kosher", "halal",
    "vegan", "vegetarian",
    # Cultured / Fermented (processing, not identity)
    "cultured", "fermented", "pasteurized", "ultra filtered",
}

CHEESE_CONTEXT_PIDS = {
    "cheese",
    "cheddar",
    "mozzarella",
    "monterey jack",
    "cottage cheese",
    "cream cheese",
    "parmesan",
    "swiss",
    "goat cheese",
    "gouda",
    "feta",
    "provolone",
    "ricotta",
    "blue cheese",
    "brie",
    "havarti",
    "romano",
}

TOKEN_RE = re.compile(r"[a-z0-9]+")

WEAK_PREFIX_TOKENS = {
    "fresh", "frozen", "canned", "dried", "dry", "ground", "minced",
    "chopped", "diced", "sliced", "shredded", "grated", "whole",
    "organic", "natural", "premium", "plain", "regular", "original",
    "classic", "raw", "cooked", "roasted", "baked", "grilled",
    "low", "reduced", "fat", "free", "nonfat", "skim", "whole",
}

TRAILING_GENERIC_DROP = {
    # Generic class nouns. When a multi-token food name ends in one of these,
    # the leading words carry the specific identity (e.g. "sharp cheddar
    # cheese" -> Cheddar, "italian sausage" -> Italian Sausage). We use this
    # set both as a trim hint in compact_item_key and as a guard so the bare
    # trailing token is tried LAST in candidate generation — it's the
    # fallback when no specific match exists, never a shadow of one.
    "cheese", "sausage", "bread", "flour", "rice",
    "sugar", "salt", "vinegar", "sauce", "seasoning",
    "oil", "milk", "butter", "extract", "syrup",
    "jam", "jelly", "spread", "pasta", "noodle", "noodles",
    "soup", "yogurt", "yoghurt", "cream",
    "bean", "beans", "nuts", "nut",
    "powder", "paste",
}

# Tokens that are pure noise inside Walmart/Kroger product names. Survive the
# title cleaner because they aren't packaging units (oz/lb) or marketing
# adjectives. Stripped during candidate generation only — they still appear in
# the original title.
STOPWORD_TOKENS = {
    # connectives / structural
    "the", "of", "and", "a", "an", "with", "in", "for", "to", "by", "or",
    "from", "on", "at",
    # packaging that escaped the cleaner regex
    "per", "case", "pack", "packs", "box", "boxes", "ct", "count", "ea",
    "each", "bag", "bags", "bottle", "bottles", "jar", "jars", "tub",
    "tubs", "tube", "tubes", "container", "containers", "carton", "cartons",
    "tray", "trays", "stick", "sticks", "shaker", "single", "individually",
    "wrapped", "package", "packaging",
    # generic descriptors with no identity content
    "delicious", "great", "amazing", "wonderful", "real", "true",
    "all", "extra", "super", "ultra", "best",
    "flavor", "flavored", "flavour", "style", "blend",
    "value", "select", "selection", "quality",
    "size", "family", "personal",
}

# Synonym map: surface form -> canonical token used in the registry. Applied
# during normalize_key so lookups for "scallion" find the "Green Onions" slot.
SYNONYM_ALIASES = {
    "scallion": "green onion",
    "scallions": "green onion",
    "spring onion": "green onion",
    "spring onions": "green onion",
    "cilantro": "coriander leaves",
    "rocket": "arugula",
    "courgette": "zucchini",
    "aubergine": "eggplant",
    "bell pepper": "pepper",
    "capsicum": "pepper",
    "garbanzo": "chickpea",
    "garbanzos": "chickpea",
    "garbanzo bean": "chickpea",
    "garbanzo beans": "chickpea",
    "confectioners sugar": "powdered sugar",
    "confectioner sugar": "powdered sugar",
    "icing sugar": "powdered sugar",
    "caster sugar": "sugar",
    "kosher salt": "salt",
    "sea salt": "salt",
    "table salt": "salt",
    "fine salt": "salt",
    "coarse salt": "salt",
    "iodized salt": "salt",
    "crabmeat": "crab",
    "crab meat": "crab",
    "soymilk": "soy milk",
    "almondmilk": "almond milk",
    "oatmilk": "oat milk",
    "cashewmilk": "cashew milk",
    "coconutmilk": "coconut milk",
    "vanilla": "vanilla extract",
    "cool whip": "whipped topping",
    "dream whip": "whipped topping",
    "reddi wip": "whipped topping",
    "reddi whip": "whipped topping",
}

PREPARED_FAMILY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bpizza\b", re.I), "1"),
    (re.compile(r"\b(sandwich|wrap|burrito|taco|quesadilla|enchilada)\b", re.I), "2"),
    (re.compile(r"\b(soup|chili|stew|bisque|chowder|broth)\b", re.I), "3"),
    (re.compile(r"\bsalad\b", re.I), "4"),
    (re.compile(r"\b(pasta|spaghetti|lasagna|macaroni|noodle|ravioli)\b", re.I), "5"),
    (re.compile(r"\b(appetizer|side|snack|wings?|nuggets?|fries|potatoes)\b", re.I), "6"),
    (re.compile(r"\b(breakfast|waffle|pancake)\b", re.I), "7"),
    (re.compile(r"\b(sushi|asian|thai|indian|chinese|teriyaki|curry)\b", re.I), "8"),
    (re.compile(r"\b(kit|starter|meal starter)\b", re.I), "9"),
    (re.compile(r"\b(plant based|meatless|vegetarian|vegan)\b", re.I), "A"),
)


def singular_word(value: str) -> str:
    if value in {"chilies", "chillis", "chiles"}:
        return "chili"
    # -oes plurals where the singular ends in -o. Without this, "tomatoes"
    # would lose just the trailing 's' and land at the bogus root "tomatoe".
    if value in {
        "tomatoes", "potatoes", "mangoes", "avocadoes",
        "burritoes", "tornadoes", "volcanoes", "embargoes",
        "cargoes", "echoes", "heroes", "mosquitoes",
        "buffaloes", "haloes",
    }:
        return value[:-2]
    if value.endswith("ies") and len(value) > 4:
        return value[:-3] + "y"
    if value.endswith("es") and len(value) > 3 and value[-3] in "sxz":
        return value[:-2]
    if value.endswith("s") and len(value) > 2 and not value.endswith(("ss", "us", "is")):
        return value[:-1]
    return value


def normalize_key(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(singular_word(tok) for tok in TOKEN_RE.findall(folded.lower()))


def apply_synonyms(key: str) -> str:
    """Map a normalized key to its canonical synonym (lookup-time only)."""
    if not key:
        return key
    for alias, canon in SYNONYM_ALIASES.items():
        if " " in alias and alias in key:
            key = key.replace(alias, canon)
    return " ".join(SYNONYM_ALIASES.get(tok, tok) for tok in key.split())


def compact_item_key(value: str) -> str:
    toks = [tok for tok in normalize_key(value).split() if tok not in WEAK_PREFIX_TOKENS]
    while len(toks) > 1 and toks[-1] in TRAILING_GENERIC_DROP:
        toks.pop()
    return " ".join(toks)


def primary_modifier(modifier: str) -> str:
    return (modifier or "").split(" > ", 1)[0].strip()


def is_rule_b(canonical_path: str, product_identity: str) -> bool:
    if product_identity in RULE_B_PIDS:
        return True
    return any((canonical_path or "").startswith(prefix) for prefix in RULE_B_PREFIXES)


_CLAIMS_TOKENS_NORM = {normalize_key(t) for t in CLAIMS_TOKENS}


def _primary_flavor(flavor) -> str:
    """Pull the first meaningful flavor token from a string or list.

    Drops PLAIN_MODIFIERS (no identity content) and CLAIMS_TOKENS (out-of-code
    facets per HTC_SPEC.md — these belong in claims_hex / variant_hash, not in
    the food_slot identity). True flavor variants like 'chocolate', 'vanilla',
    'sharp', 'hickory' pass through.
    """
    if not flavor:
        return ""
    if isinstance(flavor, list):
        flavor = flavor[0] if flavor else ""
    s = str(flavor).strip()
    if not s:
        return ""
    nk = normalize_key(s)
    if nk in PLAIN_MODIFIERS:
        return ""
    if nk in _CLAIMS_TOKENS_NORM:
        return ""
    # Take only the first flavor when " | " separated (e.g. "chocolate | vanilla")
    first = s.split(" | ")[0].split("|")[0].strip()
    # Re-check after splitting (the first piece could itself be a claim)
    if normalize_key(first) in _CLAIMS_TOKENS_NORM:
        return ""
    return first


def effective_food_name(
    canonical_path: str,
    product_identity: str,
    modifier: str = "",
    evidence_text: str = "",
    flavor: str | list = "",
) -> str:
    """Return the identity name that should receive a food slot.

    Slot identity is granular by design — every recipe-distinguishable food
    gets its own slot. That means:
      - Rule A: pid + primary flavor when flavor is present
        (chocolate pudding ≠ vanilla pudding ≠ coconut pudding)
      - Rule B: pid + primary modifier (the modifier IS the dish name)
      - Rule C / no flavor: bare pid

    Recipe ingredient "chocolate pudding" and FDC retail product
    "Snack Pack Chocolate Pudding" both resolve to food_name="Pudding
    Chocolate", which mints the same slot, so they share an htc_code.
    A different-flavor product gets a different slot.
    """
    pid = (product_identity or "").strip()
    mod = primary_modifier(modifier)
    pid_key = normalize_key(pid)
    cheese_context = (canonical_path or "").startswith("Dairy > Cheese") or pid_key in CHEESE_CONTEXT_PIDS
    if cheese_context:
        evidence_chunks = [chunk.strip() for chunk in (evidence_text or "").split("||") if chunk.strip()]
        for text in (*evidence_chunks, mod, pid, canonical_path):
            promoted = cheese_identity_from_text(text)
            if promoted and normalize_key(promoted) != "cheese":
                return promoted
    if is_rule_b(canonical_path, pid) and mod and normalize_key(mod) not in PLAIN_MODIFIERS:
        # Rule B: modifier carries identity; flavor doesn't get appended
        # (the modifier already names the specific dish).
        return f"{pid} {mod}".strip()

    # Rule A: append flavor to pid for granular slot identity.
    primary_flavor = _primary_flavor(flavor)
    if pid and primary_flavor and normalize_key(primary_flavor) != pid_key:
        # Avoid double-naming when the pid already contains the flavor
        # (e.g. pid="Chocolate Milk" and flavor="chocolate" → just "Chocolate Milk")
        if primary_flavor.lower() not in pid.lower():
            return f"{pid} {primary_flavor}".strip()
    return pid or mod


def prepared_family_from_path(canonical_path: str, identity_name: str = "") -> str:
    blob = f"{canonical_path} {identity_name}"
    for pattern, code in PREPARED_FAMILY_PATTERNS:
        if pattern.search(blob):
            return code
    return "0"


@dataclass(frozen=True)
class FoodSlotEntry:
    htc_group: str
    htc_family: str
    food_key: str
    food_name: str
    food_slot: str
    row_count: int
    canonical_path: str = ""
    product_identity_fixed: str = ""
    primary_modifier: str = ""
    rule: str = "A"
    source_htc_family: str = ""
    subdivision: str = ""


class FoodSlotRegistry:
    def __init__(self, entries: list[FoodSlotEntry]) -> None:
        self.entries = entries
        self.by_bucket_key: dict[tuple[str, str, str], FoodSlotEntry] = {}
        self.by_food_key: dict[str, list[FoodSlotEntry]] = {}
        for entry in entries:
            self.by_bucket_key[(entry.htc_group, entry.htc_family, entry.food_key)] = entry
            self.by_food_key.setdefault(entry.food_key, []).append(entry)
        for rows in self.by_food_key.values():
            rows.sort(key=lambda e: (-e.row_count, e.htc_group, e.htc_family, e.food_name))

    @classmethod
    def load(cls, path: Path = DEFAULT_REGISTRY) -> "FoodSlotRegistry":
        if not path.exists():
            return cls([])
        entries: list[FoodSlotEntry] = []
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                entries.append(
                    FoodSlotEntry(
                        htc_group=row.get("htc_group", ""),
                        htc_family=row.get("htc_family", ""),
                        food_key=row.get("food_key") or normalize_key(row.get("food_name", "")),
                        food_name=row.get("food_name", ""),
                        food_slot=row.get("food_slot", RESERVED_SLOT),
                        row_count=int(float(row.get("row_count") or 0)),
                        canonical_path=row.get("canonical_path", ""),
                        product_identity_fixed=row.get("product_identity_fixed", ""),
                        primary_modifier=row.get("primary_modifier", ""),
                        rule=row.get("rule", "A"),
                        source_htc_family=row.get("source_htc_family") or row.get("htc_family", ""),
                        subdivision=row.get("subdivision", ""),
                    )
                )
        return cls(entries)

    def lookup(self, group: str, family: str, food_name: str) -> FoodSlotEntry | None:
        keys = candidate_food_keys(food_name)
        # Pass 1: try every candidate against the SPECIFIC (group, family).
        # The leading specific noun wins over the trailing class word here.
        for key in keys:
            entry = self.by_bucket_key.get((group, family, key))
            if entry:
                return entry
        # Pass 2: try every candidate against (group, "0") only. We never
        # cross into a different non-zero family — that used to drag plant
        # milks (1, A) into regular Milk (1, 0) just because the food_key
        # bare-matched a generic entry.
        if family != "0":
            for key in keys:
                entry = self.by_bucket_key.get((group, "0", key))
                if entry:
                    return entry
        # Pass 3: by_food_key lookup, but ONLY return entries whose family
        # matches what was requested. No silent family override.
        for key in keys:
            for entry in self.by_food_key.get(key, []):
                if entry.htc_group != group:
                    continue
                if entry.htc_family == family or entry.source_htc_family == family:
                    return entry
        return None

    def lookup_any(self, food_name: str) -> FoodSlotEntry | None:
        for key in candidate_food_keys(food_name):
            rows = self.by_food_key.get(key, [])
            for row in rows:
                if row.htc_group != "0":
                    return row
        return None


def candidate_food_keys(food_name: str) -> list[str]:
    raw = normalize_key(food_name)
    compact = compact_item_key(food_name)
    candidates = [raw, compact]
    cheese_identity = cheese_identity_from_text(food_name)
    if cheese_identity:
        candidates.append(normalize_key(cheese_identity))
    # Add synonym-mapped variants of the raw and compact keys so a lookup for
    # "scallion" also tries "green onion" against the registry.
    syn_raw = apply_synonyms(raw)
    if syn_raw and syn_raw != raw:
        candidates.append(syn_raw)
        candidates.extend(
            tok for tok in syn_raw.split()
            if tok not in WEAK_PREFIX_TOKENS and tok not in TRAILING_GENERIC_DROP
        )
    syn_compact = apply_synonyms(compact)
    if syn_compact and syn_compact != compact:
        candidates.append(syn_compact)
        candidates.extend(
            tok for tok in syn_compact.split()
            if tok not in WEAK_PREFIX_TOKENS and tok not in TRAILING_GENERIC_DROP
        )
    raw_toks = raw.split()

    # Strip stopwords and digit tokens — leaves only content words.
    clean_toks = [
        tok for tok in raw_toks
        if tok not in STOPWORD_TOKENS and not tok.isdigit()
    ]
    if clean_toks and " ".join(clean_toks) != raw:
        candidates.append(" ".join(clean_toks))

    # Progressive trims and individual tokens. The cleaned token list is the
    # source so brand-y leading words and trailing packaging junk fall away
    # together. The order matters and is the difference between
    # "sharp cheddar cheese" -> Cheddar (slot 02) and "sharp cheddar cheese"
    # -> generic Cheese (slot 01).
    #
    #   1. Right-trim: keeps the leading noun (specific food) — for compound
    #      English food names, the specific usually leads, the class trails.
    #      Try "sharp cheddar" / "sharp" before any single-token candidate.
    #   2. Left-trim: keeps trailing tokens, but ONLY multi-token results.
    #      A single-token trailing generic ("cheese", "sausage", "oil") would
    #      shadow any specific match; we add it as a final fallback below.
    #   3. Compact (drop weak descriptors).
    #   4. Individual content tokens (leading order).
    #   5. Final fallback: the trailing single token, even if generic. This
    #      lets "merguez sausage" still resolve to Sausage when no Merguez
    #      entry exists, but only AFTER every more-specific candidate has
    #      been tried.
    toks = clean_toks if clean_toks else raw_toks
    if len(toks) > 1:
        for end in range(len(toks) - 1, 0, -1):
            candidates.append(" ".join(toks[:end]))
        for start in range(1, len(toks) - 1):
            candidates.append(" ".join(toks[start:]))
        if toks[-1] == "mix" and len(toks) > 2:
            candidates.append(" ".join(toks[:-1]))
        candidates.append(" ".join(tok for tok in toks if tok not in WEAK_PREFIX_TOKENS))
        # Individual content tokens — drop weak prefixes and generic class
        # nouns so they don't fire before a specific match.
        for tok in toks:
            if tok not in WEAK_PREFIX_TOKENS and tok not in TRAILING_GENERIC_DROP:
                candidates.append(tok)
        # Final fallback: the trailing single token.
        candidates.append(toks[-1])
    out: list[str] = []
    seen: set[str] = set()
    for cand in candidates:
        cand = cand.strip()
        if cand and cand not in seen:
            seen.add(cand)
            out.append(cand)
    return out


@lru_cache(maxsize=1)
def default_registry() -> FoodSlotRegistry:
    return FoodSlotRegistry.load()
