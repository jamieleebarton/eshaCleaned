"""Top-down path normalizer with chained sub-type levels.

Goal: turn any retail canonical_path + product title + form/claim facets
into a strict top-down hierarchical path:

  <Top-Level> > <Sub-Family> > <Type> > <Tier-1> > <Tier-2> > ...
              [> <Form>] [> <Claim-A> > <Claim-B> ...]

The structural part (Type, Tiers) is driven by per-family config modules
in retail_mapper/v2/family_configs/*. The form-and-claims part is appended
deterministically from the row's facet columns: form first, then claims
sorted alphabetically.

Multiple tiers chain. A SKU titled "Low Moisture Part Skim Mozzarella" hits
tier-1 (moisture) AND tier-2 (milk-fat), producing
"Dairy > Cheese > Mozzarella > Low Moisture > Part Skim".

Usage:
    from path_normalizer import normalize_path
    new_path = normalize_path(
        canonical_path="Dairy > Cheese > Mozzarella > Part Skim",
        title="LOW MOISTURE PART SKIM MOZZARELLA SHREDDED",
        form_facet="shredded",
        claims_facet="organic",
    )
    # -> "Dairy > Cheese > Mozzarella > Low Moisture > Part Skim > Shredded > Organic"
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

V2 = Path(__file__).resolve().parent
sys.path.insert(0, str(V2))


def _load_family_configs() -> dict:
    """Auto-discover family configs in retail_mapper/v2/family_configs/."""
    out: dict = {}
    pkg_path = V2 / "family_configs"
    if not pkg_path.exists():
        return out
    for finder, name, ispkg in pkgutil.iter_modules([str(pkg_path)]):
        if name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"family_configs.{name}")
        except Exception as e:
            print(f"  WARN: could not load family_configs.{name}: {e}",
                  file=sys.stderr)
            continue
        family_name = getattr(mod, "FAMILY", None)
        if family_name:
            out[family_name] = mod
    return out


_CONFIGS = _load_family_configs()


# Cross-family escape: when a row's title has UNAMBIGUOUS evidence of being
# a different family than its current path, override the family before the
# family-specific normalizer runs.
#
# Each entry: ("substring", "Target Family"). Title-substring is checked
# case-insensitively, and only fires when the substring is at a word
# boundary (so "salt" doesn't match "asalted").
#
# Order: most-specific first.
_CROSS_FAMILY_ESCAPES: list[tuple[str, str]] = [
    # Salt products misrouted to Snack > Candy > Truffles via "truffle salt"
    # FNDDS bait. Cross-family escape only fires if title contains the
    # specific salt phrase AND lacks a competing snack-product word
    # (see _SNACK_BLOCKERS below).
    ("himalayan pink salt", "Pantry"),
    ("himalayan black salt","Pantry"),
    ("himalayan crystal salt","Pantry"),
    ("himalayan rock salt", "Pantry"),
    ("himalayan salt",      "Pantry"),
    ("pink himalayan",      "Pantry"),
    ("black himalayan",     "Pantry"),
    ("sea salt grinder",    "Pantry"),
    ("kosher salt",         "Pantry"),
    ("celtic salt",         "Pantry"),
    ("hawaiian salt",       "Pantry"),
    ("fleur de sel",        "Pantry"),
    ("flaky salt",          "Pantry"),
    ("rock salt",           "Pantry"),
    ("iodized salt",        "Pantry"),
    ("garlic salt",         "Pantry"),
    ("onion salt",          "Pantry"),
    ("seasoned salt",       "Pantry"),
    ("table salt",          "Pantry"),
    # Bouillon/broth/base misrouted to Seasoning
    ("bouillon cube",       "Pantry"),
    ("bouillon",            "Pantry"),
    ("broth base",          "Pantry"),
    ("soup base",           "Pantry"),
    ("demi glace",          "Pantry"),
    ("demi-glace",          "Pantry"),
    ("chicken base",        "Pantry"),
    ("beef base",           "Pantry"),
    ("ham base",            "Pantry"),
    ("pork base",           "Pantry"),
    ("turkey base",         "Pantry"),
    ("clam base",           "Pantry"),
    ("shrimp base",         "Pantry"),
    ("vegetable base",      "Pantry"),
    ("fish base",           "Pantry"),
]

# Words that indicate the product is itself a snack/bakery/etc., not the
# salt/seasoning the cross-family escape would otherwise grab. If any of
# these is in the title, the salt match is treated as a FLAVOR signal,
# and the row stays in its original family.
_SNACK_BLOCKERS: tuple[str, ...] = (
    "chip", "chips", "crisp", "crisps", "popcorn", "pretzel", "pretzels",
    "cracker", "crackers", "nut", "nuts", "almond", "cashew", "peanut",
    "pistachio", "walnut", "pecan", "trail mix", "granola", "bar", "bars",
    "cookie", "cookies", "biscotti", "rice cake", "veggie straw",
    "veggie chip", "puff", "puffs", "bite", "bites",
    "jerky", "stick", "sticks", "rod", "rods", "twist", "twists",
    "chocolate", "candy", "truffle", "caramel", "fudge",
    "popcorn", "pita chip", "tortilla chip",
    "fries", "fry",
)


def _cross_family_escape(title: str, current_family: str) -> str | None:
    """If the title contains a strong cross-family signal, return the target
    family name. Otherwise None.

    Guard: if the title also contains a snack/bakery noun, the salt phrase
    is being used as a FLAVOR descriptor, not the product. Don't escape.
    """
    tlow = title.lower()
    for substr, target_family in _CROSS_FAMILY_ESCAPES:
        if substr not in tlow:
            continue
        if current_family == target_family:
            continue
        # Snack-product blocker: title says "Himalayan Pink Salt CHIPS"?
        # That's a flavored chip, not a salt. Don't escape.
        if any(b in tlow for b in _SNACK_BLOCKERS):
            return None
        return target_family
    return None


def _detect_first(haystack: str, candidates: list[tuple[str, str]]) -> str | None:
    """Return the canonical label for the first keyword that appears in the
    haystack (case-insensitive), or None. Candidates list order matters —
    put more-specific keywords first.
    """
    h = haystack.lower()
    for kw, label in candidates:
        if kw in h:
            return label
    return None


def _detect_most_specific(
    title: str,
    path: str,
    candidates: list[tuple[str, str]],
    generic_labels: set[str] | None = None,
) -> str | None:
    """Type detection priority:
       1. Title specific match (any non-generic keyword found in title)
       2. Path specific match (any non-generic keyword found in path)
       3. Title generic match (last-resort family-level fallback in title)
       4. Path generic match (same, in path)

    A "specific" keyword is one whose canonical label is not in
    `generic_labels`. Generic labels are family-level fallbacks like
    "Candy", "Soup", "Sauce" that should only fire when no specific
    sub-type matched anywhere.

    Within each pass we take the FIRST matching keyword (the candidates
    list is ordered most-specific first per family config).
    """
    generic_labels = generic_labels or set()
    title_l = title.lower()
    path_l = path.lower()

    # Pass 1: title specific
    for kw, label in candidates:
        if label in generic_labels:
            continue
        if kw in title_l:
            return label
    # Pass 2: path specific
    for kw, label in candidates:
        if label in generic_labels:
            continue
        if kw in path_l:
            return label
    # Pass 3: title generic (fall-back family label)
    for kw, label in candidates:
        if label not in generic_labels:
            continue
        if kw in title_l:
            return label
    # Pass 4: path generic
    for kw, label in candidates:
        if label not in generic_labels:
            continue
        if kw in path_l:
            return label
    return None


def _format_claim(raw: str) -> str:
    """Normalize a raw claim token (e.g., 'gluten_free' or 'low-fat') into a
    Title Case display form (e.g., 'Gluten Free')."""
    s = raw.strip().replace("_", " ").replace("-", " ").strip()
    if not s:
        return ""
    # Title case but keep small words readable
    return " ".join(w.capitalize() for w in s.split())


# Form values that indicate a WRAPPING / COMPOSITE product, not a form of
# the type itself. When seen, the form is dropped from the path (it pollutes
# the type hierarchy: "Chicken > Phyllo Dough" doesn't make sense — phyllo
# is the wrapper, not the chicken's form).
_WRAPPER_FORMS = {
    "phyllo", "phyllo dough", "puff pastry", "pastry shell", "pastry",
    "wonton", "wonton wrapper", "spring roll wrapper", "egg roll wrapper",
    "taco shell", "tortilla wrap", "filo", "filo dough", "dough wrap",
    "crust",
}


def normalize_path(
    canonical_path: str,
    title: str = "",
    form_facet: str = "",
    claims_facet: str = "",
) -> str:
    """Normalize a single canonical_path. If the family is unknown or the
    type can't be detected, return the path unchanged.

    Detection priority: TITLE wins over PATH. The path may already encode
    a wrong modifier ("Part Skim" lingering from an earlier pass) — the
    title is the source-of-truth for current product attributes. Only when
    the title is empty/silent do we fall back to the path.
    """
    if not canonical_path:
        return canonical_path
    parts = [p.strip() for p in canonical_path.split(">") if p.strip()]
    if not parts:
        return canonical_path

    family = parts[0]

    # Cross-family escape: title may force a different family.
    # E.g., "HIMALAYAN PINK SALT" wrongly routed to Snack > Candy > Truffles
    # via FNDDS bait should escape back to Pantry.
    target = _cross_family_escape(title or "", family)
    if target:
        family = target

    cfg = _CONFIGS.get(family)
    if cfg is None:
        return canonical_path  # unknown family — leave alone

    title_h = title or ""
    path_h = canonical_path or ""

    # 1. Identify TYPE. Title-specific wins; falls back to path-specific;
    #    then to generic family-level types as last resort.
    type_kws = getattr(cfg, "TYPE_KEYWORDS", [])
    generics = set(getattr(cfg, "GENERIC_TYPE_LABELS", set()))
    type_label = _detect_most_specific(title_h, path_h, type_kws, generics)
    if type_label is None:
        return canonical_path  # no type detected — leave alone

    # 2. Identify SUB-FAMILY parent
    sub_family = getattr(cfg, "SUB_FAMILY_BY_TYPE", {}).get(type_label)

    # 3. Iterate TIERS — title first, path as fallback per-tier.
    tier_labels: list[str] = []
    type_kw_lower = type_label.lower()
    for tier in getattr(cfg, "TIERS", []):
        # Filter out tier keywords that overlap the type itself (e.g.,
        # "whole milk" tier keyword shouldn't fire when type IS "Whole Milk").
        filtered = [(kw, lbl) for kw, lbl in tier
                    if kw not in type_kw_lower and lbl != type_label]
        match = _detect_first(title_h, filtered)
        if match is None:
            match = _detect_first(path_h, filtered)
        if match:
            tier_labels.append(match)

    # 4. Assemble structural part
    out_parts = [family]
    if sub_family:
        out_parts.append(sub_family)
    out_parts.append(type_label)
    out_parts.extend(tier_labels)

    # 5. Append FORM facet — may have multiple values pipe/comma-separated.
    #    Split, format each, deduplicate, sort alphabetically, append.
    #    Skip wrapper/pastry forms which pollute meat/produce paths
    #    (e.g., "Chicken > Phyllo Dough" — phyllo isn't a form of chicken).
    if form_facet:
        raw = [r for r in form_facet.replace("|", ",").split(",")]
        formatted = sorted({c for r in raw if (c := _format_claim(r))})
        for f in formatted:
            if f.lower() in _WRAPPER_FORMS:
                continue
            if f not in out_parts:
                out_parts.append(f)

    # 6. Append CLAIMS facet — same treatment as form, alphabetized.
    if claims_facet:
        raw_claims = [c for c in claims_facet.replace("|", ",").split(",")]
        formatted = sorted({c2 for c in raw_claims if (c2 := _format_claim(c))})
        for c in formatted:
            if c not in out_parts:
                out_parts.append(c)

    return " > ".join(out_parts)


def normalize_self_test() -> None:
    """Quick smoke-test against known cases."""
    cases = [
        # (input_path, title, form, claims, expected_output)
        ("Dairy > Cheese",
         "LOW MOISTURE PART SKIM MOZZARELLA SHREDDED",
         "shredded", "organic",
         "Dairy > Cheese > Mozzarella > Low Moisture > Part Skim > Shredded > Organic"),
        ("Dairy > Cheese > Mozzarella > Part Skim",
         "WHOLE MILK MOZZARELLA",
         "", "",
         "Dairy > Cheese > Mozzarella > Whole Milk"),
        ("Dairy > Aged Cheddar",
         "EXTRA SHARP AGED CHEDDAR CHEESE",
         "", "organic",
         "Dairy > Cheese > Cheddar > Extra Sharp > Aged > Organic"),
        ("Dairy > Cheese > Cheddar > Sharp",
         "SHARP CHEDDAR CHEESE BLOCK",
         "block", "",
         "Dairy > Cheese > Cheddar > Sharp > Block"),
        ("Dairy > Cheese > Cheddar > Sharp",
         "SMOKED SHARP CHEDDAR",
         "", "organic,gluten_free",
         "Dairy > Cheese > Cheddar > Sharp > Smoked > Gluten Free > Organic"),
        ("Snack > Pretzels",
         "HARD PRETZELS, ORGANIC",
         "", "organic",
         "Snack > Pretzels > Hard > Organic"),
        ("Bakery > Bread",
         "ARTISAN SOURDOUGH BREAD, SLICED",
         "sliced", "",
         "Bakery > Bread > Sourdough Bread > Sliced"),
        ("Meat & Seafood > Sausage",
         "ITALIAN SAUSAGE, SMOKED, BONELESS",
         "", "",
         "Meat & Seafood > Sausage > Italian Sausage > Smoked > Boneless"),
    ]
    print("=== normalize_path self-test ===")
    n_pass = n_fail = 0
    for inp, title, form, claims, expected in cases:
        got = normalize_path(inp, title, form, claims)
        ok = got == expected
        n_pass += int(ok)
        n_fail += int(not ok)
        flag = "OK " if ok else "FAIL"
        print(f"  [{flag}] in={inp!r} title={title[:50]!r}")
        print(f"           got={got!r}")
        if not ok:
            print(f"           exp={expected!r}")
    print(f"  {n_pass} pass, {n_fail} fail")


if __name__ == "__main__":
    normalize_self_test()
