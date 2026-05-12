"""The 30-surface correctness fixture.

For each surface we name:
  expected_canonical   — the nutrition canonical the resolver MUST produce
  expected_state       — the nutrition trust state (exact/proxy/unknown)
  expected_product_re  — regex that the Walmart example product MUST match

This is the compaction-proof checkpoint. If one case fails, the failure
message names the surface + expected vs got, so "the calculator is broken"
stops being hand-wavy and becomes a specific, fixable line.

Runs under Tier 0 preflight. Add new cases whenever a regression is caught
in the wild — that's how the fixture grows into a real correctness gate.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from calculator import calculate_line  # noqa: E402
from schema import NutritionState, TrustLayer  # noqa: E402
from price_resolver import cpg_for_codes  # noqa: E402


# Each case: (surface, expected_canonical, expected_nutrition_state,
#            expected_product_regex_or_None, expected_product_forbidden_regex_or_None)
# expected_product_regex is what the Walmart example MUST match.
# expected_product_forbidden_regex is a pattern the example MUST NOT match.
# Either can be None to skip that check (when the code is correct but products are unavailable).
CASES: list[tuple[str, str, NutritionState, str | None, str | None]] = [
    # --- Foods with direct SR28 anchors (EXACT) -----------------------------
    ("butter",            "butter",            NutritionState.EXACT_USDA_ANCHOR,
        r"\bbutter\b",            r"\b(buttermint|sunbutter|beef|stock)\b"),
    ("salt",              "salt",              NutritionState.EXACT_USDA_ANCHOR,
        r"\bsalt\b",              r"\b(peanut|roasted)\b"),
    ("sugar",             "granulated sugar",  NutritionState.EXACT_USDA_ANCHOR,
        r"\bsugar\b",             r"\b(cinnamon|strawberr)\b"),
    # flour resolves to the explicit all-purpose canonical (more specific than generic "flour")
    ("flour",             "all purpose flour", NutritionState.EXACT_USDA_ANCHOR,
        r"\bflour\b",             None),
    ("milk",              "milk",              NutritionState.EXACT_USDA_ANCHOR,
        r"\bmilk\b",              r"\b(duds|chocolate)\b"),
    ("chicken breast",    "chicken breast",    NutritionState.EXACT_USDA_ANCHOR,
        r"\bchicken breast\b",    None),
    ("ground turkey",     "ground turkey",     NutritionState.EXACT_USDA_ANCHOR,
        r"\bground turkey\b",     None),
    ("bacon",             "bacon",             NutritionState.EXACT_USDA_ANCHOR,
        r"\bbacon\b",             r"\b(veggie|vegetarian|morningstar)\b"),
    ("parmesan cheese",   "parmesan cheese",   NutritionState.EXACT_USDA_ANCHOR,
        r"\bparmesan\b",          None),
    ("peanut butter",     "peanut butter",     NutritionState.EXACT_USDA_ANCHOR,
        r"\bpeanut butter\b",     r"\bsunflower\b"),
    ("baking powder",     "baking powder",     NutritionState.EXACT_USDA_ANCHOR,
        r"\bbaking powder\b",     None),
    ("olive oil",         "olive oil",         NutritionState.EXACT_USDA_ANCHOR,
        r"\bolive oil\b",         r"\b(tuna|fish|sardine)\b"),
    # black pepper is a reviewed proxy: default pantry pepper when the recipe
    # doesn't specify a more specific form.
    ("black pepper",      "black pepper",      NutritionState.REVIEWED_PROXY,
        # TODO tag-quality: generic 'pepper' canonical still catches orange/
        # cayenne/white pepper products. Needs per-variety canonical rows.
        r"\bpepper\b",            r"\b(lemon|sauce)\b"),
    ("heavy cream",       "heavy cream",       NutritionState.EXACT_USDA_ANCHOR,
        # TODO tag-quality: generic 'cream' canonical still catches bakewell/
        # cream-cheese/cream-of-X products. Needs distinct canonicals for
        # each cream variety in canonical_items.
        r"\bcream\b",             r"\b(cake|cheesecake|soup|cheese)\b"),
    ("almond milk",       "almond milk",       NutritionState.EXACT_USDA_ANCHOR,
        r"\balmond milk\b",       r"\b(flour|flavored almonds)\b"),
    ("coconut milk",      "coconut milk",      NutritionState.EXACT_USDA_ANCHOR,
        r"\bcoconut milk\b",      r"\b(shredded|chip|bar|sugar)\b"),
    ("strawberries",      "strawberry",        NutritionState.EXACT_USDA_ANCHOR,
        r"\bstrawberr",           r"\b(dressing|yogurt|shortcake|pastries|strudel)\b"),
    ("cucumber",          "cucumber",          NutritionState.EXACT_USDA_ANCHOR,
        r"\bcucumber\b",          r"\b(dressing|ranch|face|deodorant)\b"),
    ("lettuce",           "lettuce",           NutritionState.EXACT_USDA_ANCHOR,
        r"\blettuce\b",           r"\bseed\b"),
    # baby carrots: canonical_items now has 'baby carrot' → SR28 168568
    ("baby carrots",      "baby carrot",       NutritionState.EXACT_USDA_ANCHOR,
        r"\bbaby carrot",         r"\bseed\b"),
    # --- Foods that are legitimately REVIEWED_PROXY ------------------------
    # egg has been intentionally proxied by Hestia to "Egg, whole, raw, fresh"
    ("egg",               "egg",               NutritionState.REVIEWED_PROXY,
        r"\begg", None),
    # --- Foods that used to lie as exact, now correctly REVIEWED_PROXY -----
    # beef stock: remapped 2026-04-19 from the butter SR28 173410 (the lie
    # earlier) to 172883 (Soup, stock, beef, home-prepared) with review_status
    # =approved. Now emits EXACT, can shop real beef stock products.
    ("beef stock",        "beef stock",        NutritionState.EXACT_USDA_ANCHOR,
        None, r"\bbutter\b"),
    # acai extract: still auto-batched proxy — Esha tags it to label products
    ("acai extract",      "acai extract",      NutritionState.REVIEWED_LOCAL_LABEL_ANCHOR,
        None, None),
    # --- Canonicals with collisions we haven't fixed yet ------------------
    # These are documented as open items. When the collision is resolved
    # (distinct SR28 codes for whole vs deli ham, brown vs white rice, etc.),
    # the assertions below tighten.
    # whole ham: resolver returns 'ham' canonical (167872 pork cured roasted,
    # distinct from deli sliced 173864). Product must be real ham, NOT lunchmeat.
    ("whole ham",         "ham",               NutritionState.EXACT_USDA_ANCHOR,
        r"\bham\b",               r"\blunchmeat\b"),
    # deli ham: correctly maps to sliced ham 173864 — product IS lunchmeat.
    ("deli ham",          "deli ham",          NutritionState.EXACT_USDA_ANCHOR,
        r"\b(ham|lunchmeat)\b",   None),
    # Rice varieties resolve to their specific canonicals — WIN
    ("brown rice",        "brown rice",        NutritionState.EXACT_USDA_ANCHOR,
        r"\bbrown rice\b",        None),
    ("white rice",        "white rice",        NutritionState.EXACT_USDA_ANCHOR,
        r"\brice\b",              r"\bbrown\b"),
    # basmati/jasmine have no distinct SR28 — honest REVIEWED_PROXY to white
    ("basmati rice",      "basmati rice",      NutritionState.REVIEWED_PROXY,
        None, None),
    # --- Pinned compositional regressions (never head-flip) ---------------
    ("butter peas",       "butter peas",       NutritionState.REVIEWED_PROXY,
        r"\bpea", r"\bbutter\b"),  # Must NOT resolve or shop as butter
    ("vanilla extract",   "vanilla extract",   NutritionState.EXACT_USDA_ANCHOR,
        r"\b(vanilla|extract)\b",   None),

    # === Phase 3 expansion 2026-04-19: 70 more surfaces ===================
    # Dairy varieties
    ("whole milk",        "whole milk",        NutritionState.EXACT_USDA_ANCHOR, None, None),
    ("skim milk",         "skim milk",         NutritionState.EXACT_USDA_ANCHOR, None, None),
    # half and half is a real dairy ingredient; keep it out of parser-artifact cleanup.
    ("half and half",     "half and half",     NutritionState.EXACT_USDA_ANCHOR, None, None),
    ("sour cream",        "sour cream",        NutritionState.EXACT_USDA_ANCHOR, r"\bsour cream\b", None),
    ("cream cheese",      "cream cheese",      NutritionState.EXACT_USDA_ANCHOR, r"\bcream cheese\b", None),
    ("cottage cheese",    "cottage cheese",    NutritionState.EXACT_USDA_ANCHOR, r"\bcottage cheese\b", None),
    ("mozzarella cheese", "mozzarella cheese", NutritionState.EXACT_USDA_ANCHOR, r"\bmozzarella\b", None),
    ("ricotta cheese",    "ricotta cheese",    NutritionState.EXACT_USDA_ANCHOR, r"\bricotta\b", None),
    ("yogurt",            "yogurt",            NutritionState.EXACT_USDA_ANCHOR, r"\byogurt\b", None),
    ("greek yogurt",      "greek yogurt",      NutritionState.EXACT_USDA_ANCHOR, r"\bgreek yogurt\b", None),

    # Meat cuts
    ("ground beef",       "ground beef",       NutritionState.EXACT_USDA_ANCHOR, r"\bground beef\b", r"\bvegetarian\b"),
    ("lean ground beef",  "lean ground beef",  NutritionState.EXACT_USDA_ANCHOR, r"\bground beef\b", None),
    ("pork chop",         "pork chop",         NutritionState.EXACT_USDA_ANCHOR, None, None),
    ("pork tenderloin",   "pork tenderloin",   NutritionState.EXACT_USDA_ANCHOR, None, None),
    ("chicken thigh",     "chicken thigh",     NutritionState.EXACT_USDA_ANCHOR, r"\bchicken thigh\b", None),
    ("chicken wing",      "chicken wing",      NutritionState.EXACT_USDA_ANCHOR, None, None),
    ("salmon",            "salmon",            NutritionState.EXACT_USDA_ANCHOR, r"\bsalmon\b", None),
    ("shrimp",            "shrimp",            NutritionState.EXACT_USDA_ANCHOR, r"\bshrimp\b", None),
    ("tuna",              "tuna",              NutritionState.EXACT_USDA_ANCHOR, r"\btuna\b", None),

    # Grains / pasta / bread
    ("pasta",             "pasta",             NutritionState.EXACT_USDA_ANCHOR, r"\bpasta\b", None),
    ("spaghetti",         "spaghetti",         NutritionState.REVIEWED_LOCAL_LABEL_ANCHOR, None, None),
    ("bread",             "bread",             NutritionState.EXACT_USDA_ANCHOR, r"\bbread\b", None),
    ("tortilla",          "tortilla",          NutritionState.REVIEWED_PROXY, None, None),
    ("oats",              "oat",               NutritionState.EXACT_USDA_ANCHOR, None, None),
    ("quinoa",            "quinoa",            NutritionState.EXACT_USDA_ANCHOR, r"\bquinoa\b", None),
    ("couscous",          "couscous",          NutritionState.EXACT_USDA_ANCHOR, None, None),

    # Spices / condiments
    ("cinnamon",          "cinnamon",          NutritionState.EXACT_USDA_ANCHOR, r"\bcinnamon\b", r"\bsugar\b"),
    ("paprika",           "paprika",           NutritionState.EXACT_USDA_ANCHOR, None, None),
    ("cumin",             "cumin",             NutritionState.REVIEWED_PROXY, None, None),
    ("oregano",           "oregano",           NutritionState.EXACT_USDA_ANCHOR, None, None),
    ("basil",             "basil",             NutritionState.EXACT_USDA_ANCHOR, r"\bbasil\b", None),
    ("thyme",             "thyme",             NutritionState.EXACT_USDA_ANCHOR, None, None),
    ("rosemary",          "rosemary",          NutritionState.EXACT_USDA_ANCHOR, None, None),
    ("soy sauce",         "soy sauce",         NutritionState.EXACT_USDA_ANCHOR, r"\bsoy sauce\b", None),
    ("worcestershire sauce", "worcestershire sauce", NutritionState.EXACT_USDA_ANCHOR, r"\bworcestershire\b", None),
    ("ketchup",           "ketchup",           NutritionState.EXACT_USDA_ANCHOR, r"\bketchup\b", None),
    ("mustard",           "mustard",           NutritionState.EXACT_USDA_ANCHOR, r"\bmustard\b", None),
    # Plain mayonnaise MUST NOT be flavored/reduced-fat/vegan/olive-oil mayo —
    # each of those is its own ESHA card. This pins the tightened 8046 contract.
    ("mayonnaise",        "mayonnaise",        NutritionState.EXACT_USDA_ANCHOR,
        r"\bmayo",
        r"\b(chipotle|lime|serrano|sriracha|wasabi|habanero|jalapeno|pesto|truffle|"
        r"ketchup|ranch|aioli|avocado|light|lite|low[\s-]?fat|fat[\s-]?free|"
        r"reduced|olive[\s-]?oil|vegan|plant[\s-]?based|non[\s-]?dairy|imitation)\b"),
    # Plain cheddar cheese MUST NOT be a blend, jack/swiss/mozzarella mix, or
    # a non-dairy imitation. This pins the tightened 33342 contract.
    ("cheddar cheese",    "cheddar cheese",    NutritionState.EXACT_USDA_ANCHOR,
        r"\bcheddar\b",
        r"\b(jack|monterey|colby|swiss|parmesan|mozzarella|provolone|gouda|"
        r"cashew|vegan|plant[\s-]?based|non[\s-]?dairy|imitation|blend|trio|tray|platter)\b"),
    ("honey",             "honey",             NutritionState.EXACT_USDA_ANCHOR, r"\bhoney\b", r"\bham\b"),

    # Produce
    ("apple",             "apple",             NutritionState.EXACT_USDA_ANCHOR, r"\bapple", r"\bpie\b"),
    ("banana",            "banana",            NutritionState.EXACT_USDA_ANCHOR, r"\bbanana", None),
    ("orange",            "orange",            NutritionState.EXACT_USDA_ANCHOR, r"\borange", None),
    ("lemon",             "lemon",             NutritionState.EXACT_USDA_ANCHOR, r"\blemon", None),
    ("avocado",           "avocado",           NutritionState.EXACT_USDA_ANCHOR, r"\bavocado", None),
    ("broccoli",          "broccoli",          NutritionState.EXACT_USDA_ANCHOR, r"\bbroccoli\b", None),
    ("spinach",           "spinach",           NutritionState.EXACT_USDA_ANCHOR, r"\bspinach\b", None),
    ("celery",            "celery",            NutritionState.EXACT_USDA_ANCHOR, r"\bcelery\b", None),
    ("ginger",            "ginger",            NutritionState.EXACT_USDA_ANCHOR, r"\bginger\b", None),

    # Beverages
    ("orange juice",      "orange juice",      NutritionState.EXACT_USDA_ANCHOR, r"\borange juice\b", None),
    ("coffee",            "coffee",            NutritionState.EXACT_USDA_ANCHOR, r"\bcoffee\b", None),
    ("tea",               "tea",               NutritionState.EXACT_USDA_ANCHOR, None, None),

    # Nuts / legumes — canonical rows may not exist for all; accept
    # whatever the resolver honestly returns (including NUTRITION_UNKNOWN
    # when no canonical exists).
    ("walnuts",           "walnut",            NutritionState.EXACT_USDA_ANCHOR, r"\bwalnut", None),
    ("cashews",           "cashew",            NutritionState.EXACT_USDA_ANCHOR, r"\bcashew", None),
    ("pistachios",        "pistachio",         NutritionState.EXACT_USDA_ANCHOR, r"\bpistachio", None),
    ("chickpeas",         "chickpea",          NutritionState.EXACT_USDA_ANCHOR, None, None),
    ("lentils",           "lentil",            NutritionState.EXACT_USDA_ANCHOR, None, None),

    # Remapped SR28 codes from today's shop_gap drain
    ("potato",            "potato",            NutritionState.EXACT_USDA_ANCHOR, r"\bpotato", r"\b(chip|snack|burrito)\b"),
    ("black beans",       "black bean",        NutritionState.EXACT_USDA_ANCHOR, None, None),
    ("green beans",       "green bean",        NutritionState.EXACT_USDA_ANCHOR, None, None),

    # Shop_gap drain additions (proxies added today)
    ("chocolate chips",   "chocolate chips",   NutritionState.REVIEWED_LOCAL_LABEL_ANCHOR, None, None),
    ("black olive",       "black olive",       NutritionState.EXACT_USDA_ANCHOR, r"\bolive", None),
    ("vegetable stock",   "vegetable stock",   NutritionState.REVIEWED_LOCAL_LABEL_ANCHOR, None, None),

    # Pseudo-foods that should honestly return NUTRITION_UNKNOWN
    ("xyzzy unicorn flake", None,              NutritionState.NUTRITION_UNKNOWN, None, None),
]


class CalculatorCorrectnessFixture(unittest.TestCase):
    """One test method per surface so a failure names the exact surface."""

    maxDiff = None


def _make_case(surface, expected_canonical, expected_state,
                product_re, forbidden_re):
    def test(self):
        r = calculate_line(display="1 cup " + surface, item=surface)
        if expected_canonical is None:
            # Compositional-ban case: resolver must not produce a canonical.
            # It can emit either "" or anything that is NOT the banned target,
            # but the state must be NUTRITION_UNKNOWN.
            self.assertEqual(r.nutrition_state, expected_state,
                             f"{surface!r}: state={r.nutrition_state.name}, "
                             f"canonical={r.canonical_name!r}")
            return
        self.assertEqual(r.canonical_name, expected_canonical,
                         f"{surface!r}: canonical mismatch — got {r.canonical_name!r}")
        self.assertEqual(r.nutrition_state, expected_state,
                         f"{surface!r}: state — expected {expected_state.name}, "
                         f"got {r.nutrition_state.name}")
        if product_re is None and forbidden_re is None:
            return
        # Shopping joins use the shopping-side codes (empty when proxy is auto-batched).
        # Pass the resolved canonical so products tagged to a different canonical
        # under the same SR28 code are filtered out.
        cpg = cpg_for_codes(r.shopping_sr28_fdc_id, r.shopping_fndds_code,
                             canonical=r.canonical_name or "")
        w = cpg.get("walmart") or {}
        example = (w.get("example") or "").lower()
        if product_re and example:
            self.assertRegex(example, product_re,
                             f"{surface!r}: walmart example {example!r} "
                             f"does not match expected /{product_re}/")
        if forbidden_re and example:
            self.assertNotRegex(example, forbidden_re,
                                f"{surface!r}: walmart example {example!r} "
                                f"matches forbidden /{forbidden_re}/")
    test.__name__ = "test_" + re.sub(r"[^a-z0-9]+", "_", surface.lower()).strip("_")
    return test


for _c in CASES:
    _m = _make_case(*_c)
    setattr(CalculatorCorrectnessFixture, _m.__name__, _m)


class ProxyShoppingIsolationTests(unittest.TestCase):
    """Nutrition proxies MUST NOT drive shopping. An auto-batched proxy's
    SR28 code points at an unrelated food — shopping through that code would
    serve the wrong product. Memory rule: never collapse nutrition proxy with
    shopping match."""

    def test_beef_stock_now_resolves_via_real_sr28(self):
        r = calculate_line(display="1 cup beef stock", item="beef stock")
        # After 2026-04-19 remap, beef stock has its own SR28 (172883 —
        # Soup, stock, beef, home-prepared). No longer a butter proxy.
        self.assertEqual(r.sr28_fdc_id, "172883",
                         "beef stock must route to 172883 (real beef stock), not 173410 (butter)")
        self.assertEqual(r.shopping_sr28_fdc_id, "172883",
                         "beef stock shopping sr28 must match nutrition sr28 (not proxy isolation)")

    def test_acai_extract_nutrition_proxies_but_shopping_is_gap(self):
        r = calculate_line(display="1 tsp acai extract", item="acai extract")
        self.assertIn(r.nutrition_state,
                      (NutritionState.REVIEWED_LOCAL_LABEL_ANCHOR,
                       NutritionState.REVIEWED_PROXY))
        self.assertEqual(r.shopping_sr28_fdc_id, "")
        self.assertEqual(cpg_for_codes(r.shopping_sr28_fdc_id, r.shopping_fndds_code), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
