"""HTC (Hestia Taxonomy Code) 8-character positional encoder.

Ported from /Users/jamiebarton/Desktop/Esha/build_htc_registry.py and
tag_products_htc_v2.py — same rules, same Crockford check digit, same
position semantics. Adapted to consume our consensus columns instead of
Hestia's master_products.db schema.

Code layout:
  pos1: group       (single char from CROCKFORD)
  pos2: family      (single char from CROCKFORD; '0' if not detectable)
  pos3-4: food      (deterministic identity slot from food_slot_registry.csv)
  pos5: form        (neutral in join-code mode; facets live in output fields)
  pos6: processing  (neutral in join-code mode; facets live in output fields)
  pos7: ptype       (neutral in join-code mode; facets live in output fields)
  pos8: check       (Crockford mod-37 check digit)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

try:  # package import
    from .food_slots import default_registry, prepared_family_from_path
except ImportError:  # script import via sys.path
    from htc.food_slots import default_registry, prepared_family_from_path  # type: ignore

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # 32 chars (no I L O U)
CHECK_CHARS = CROCKFORD + "*~$=U"  # 37 total for mod-37 check

# Non-food items that recipes occasionally list (props, cleaners, supplies).
# These are correctly unresolved (group=N) — distinct from "we missed it".
NON_FOOD_PATTERNS = re.compile(
    r"\balum\b|\bborax\b|\blye\b|toothpick|cloth napkin|paper napkin|cloth serviette|paper serviette|"
    r"paper cup|paper bag|brown paper|paper baking cup|cupcake liner|muffin liner|beeswax|paraffin wax|"
    r"glycerin|glycerine|epsom salt|ammonia|rubbing alcohol|witch hazel|"
    r"hydrogen peroxide|liquid dish soap|liquid dishwashing soap|dish detergent|dish soap|dishwashing|"
    r"toothpaste|mouthwash|sensodyne|pronamel|denture|denture cleanser|retainer cleanser|cleanser tablets|"
    r"cat litter|clumping litter|\blitter\b|fresh step|clean paws|febreze|gain original scent|"
    r"fragrance oils?|essential oils?|scented oils?|perfume oils?|home fragrances?|diffusers?|"
    r"humidifiers?|aromatherapy|"
    r"paper towel|wax paper|waxed paper|parchment paper|aluminum foil|tin foil|"
    r"plastic wrap|saran wrap|edible (?:silver|gold) foil|edible glitter(?!.*sugar)|"
    r"silver cachous|silver dragee|gold leaf decoration|24k gold|gold flake|gold fleck|"
    r"skewer|cooking string|kitchen twine|kitchen string|cooking twine|^string$|^cotton kitchen string$|"
    r"castile soap|bleach\b|^glitter$|"
    r"adhesive tape|beading wire|gauge wire|airtight glass jar|airtight container|"
    r"all.purpose white glue|^white glue$|liquid soap|all.natural liquid soap|"
    r"activated charcoal(?!\s*tablet)|active starter|active sourdough starter|sourdough starter|"
    r"\badd.in\b|\badd.ins\b|additional liquid|^water$(?=\s*for|\s*as)|"
    r"african violets|agrimony|"
    r"^acid blend$|tartaric acid blend|"
    r"\baccent\b(?!\s*flavor)|^aji.no.moto$|^ajinomoto$|"
    r"\bcedar plank\b|wooden stick|popsicle stick|toothpick|oven cooking bag|"
    r"^ribbon$|^twine$|food coloring(?!\s*paste)|gel food color|"
    r"\bdecorative\b|decorative cand",
    re.I,
)


def crockford_check(code_7: str) -> str:
    val = 0
    for ch in code_7:
        idx = CROCKFORD.index(ch.upper()) if ch.upper() in CROCKFORD else 0
        val = val * 32 + idx
    return CHECK_CHARS[val % 37]


def code_from_parts(group: str, family: str, food: str, form: str = "0",
                    processing: str = "0", ptype: str = "0") -> str:
    code_7 = f"{group or '0'}{family or '0'}{food or '00'}{form or '0'}{processing or '0'}{ptype or '0'}"
    return code_7 + crockford_check(code_7)


def group_from_canonical_path(canonical_path: str, identity: str = "") -> str:
    """Path-first group resolver for curated retail taxonomy rows."""
    path = " ".join(re.findall(r"[a-z0-9]+", (canonical_path or "").lower()))
    blob = f"{path} {' '.join(re.findall(r'[a-z0-9]+', (identity or '').lower()))}"
    if not path:
        return ""
    if path.startswith("baby toddler"):
        return "M"
    if re.search(r"\beggs?\b", blob) and not re.search(r"\b(egg noodle|egg roll|easter)\b", blob):
        return "5"
    if path.startswith("dairy"):
        return "1"
    # Plant Milk lives at "Beverage > Plant Milk > X" in the curated retail
    # tree, but recipes ("almond milk", "soy milk", "oat milk") land in
    # group 1 (Dairy) family A via the family rules. Route the path-side to
    # the same group so retail and recipe ingredients share codes.
    if "plant milk" in path or path.startswith("beverage plant milk"):
        return "1"
    if (
        path.startswith("frozen ice cream")
        or re.search(r"\b(ice cream|gelato|sorbet|sherbet|frozen yogurt|ice pop|popsicle)\b", blob)
    ):
        return "1"
    if path.startswith("frozen breakfast") or re.search(r"\b(waffles?|pancakes?)\b", blob):
        return "8"
    if path.startswith("meal"):
        return "H"
    if path.startswith("pantry soup") or re.search(r"\b(soup|chili|stew|bisque|chowder)\b", path):
        return "H"
    if path.startswith("produce vegetables") or path.startswith("frozen vegetables") or "canned vegetables" in path:
        return "6"
    if path.startswith("produce fruit") or "frozen fruit" in path or "canned fruit" in path:
        return "7"
    if path.startswith("snack dried fruit") or "dried fruit" in path:
        if "chocolate candy" not in path and "candy" not in path:
            return "7"
    if path.startswith("meat seafood"):
        # Strip the "meat seafood" prefix before looking for sub-category words
        # — otherwise the prefix itself would route every Meat & Seafood row
        # to Fish via the bare "seafood" token.
        rest = path[len("meat seafood"):].strip()
        if "poultry" in rest or re.search(r"\b(chicken|turkey|duck)\b", blob):
            return "3"
        if (
            "seafood" in rest or "shellfish" in rest
            or re.search(r"\b(fish|shrimp|salmon|tuna|crab|lobster|shellfish|squid|scallop|oyster|clam|mussel)\b", blob)
        ):
            return "4"
        return "2"
    if path.startswith("pantry spices") or "spices seasonings" in path or "baking extracts" in path:
        return "E"

    # Segment-aware keyword matches. Substring-anywhere matches lit up false
    # positives like "Sugar Snap Peas" (matches "sugar"), "Coconut Oil Spread"
    # (matches "oil"), "Bean Sprouts" under Produce > Vegetables (matches
    # "bean"). Restrict to LEAF or PENULTIMATE-segment matches so "sugar"
    # routes to group C only when it's the food's actual identity, not a
    # modifier in an unrelated path.
    _segs = [s.strip().lower() for s in (canonical_path or "").split(" > ") if s.strip()]
    _leaf = _segs[-1] if _segs else ""
    _penult = _segs[-2] if len(_segs) >= 2 else ""
    _leaf_tokens = set(_leaf.split())
    _last_two = " > ".join(_segs[-2:])

    # Oil (group B) — leaf must be an oil, or path is in Pantry > Oil family
    if (("oil" in _leaf_tokens or _leaf.endswith(" oil"))
            or _penult == "oil" or _penult == "oils"
            or path.startswith("pantry oil") or "oils vinegars" in path):
        return "B"

    # Sweeteners (group C) — leaf is sugar/honey/syrup, or under Sweeteners
    if (_leaf in {"sugar", "brown sugar", "powdered sugar", "granulated sugar",
                  "cane sugar", "white sugar", "raw sugar", "demerara sugar",
                  "muscovado sugar", "turbinado sugar", "coconut sugar",
                  "honey", "maple syrup", "agave", "molasses", "stevia",
                  "saccharin", "sucralose", "splenda"}
            or _leaf.endswith(" sugar") or _leaf.endswith(" syrup") or _leaf.endswith(" honey")
            or _penult in {"sugar", "sweetener", "sweeteners", "honey", "syrup"}
            or path.startswith("pantry sweetener")):
        return "C"

    # Sauces / condiments (group F) — leaf is a sauce/dressing/dip/etc.
    SAUCE_LEAF_TOKENS = {"sauce", "salsa", "dressing", "vinaigrette", "ketchup",
                         "mustard", "mayonnaise", "mayo", "relish", "marinade",
                         "dip", "spread", "aioli", "tahini", "guacamole",
                         "hummus", "tapenade"}
    if (_leaf_tokens & SAUCE_LEAF_TOKENS
            or _penult in {"sauces", "salsas", "dressings", "condiments",
                            "pickles", "dips", "spreads", "olives"}
            or _leaf.endswith(" sauce") or _leaf.endswith(" dressing") or _leaf.endswith(" dip")
            or path.startswith("pantry sauces") or path.startswith("pantry condiments")
            or path.startswith("pantry dips") or path.startswith("pantry pickles")
            or path.startswith("pantry olives")):
        return "F"

    # Legumes (group 9) — leaf is a bean/legume identity, or under Beans/Legumes
    if (_leaf in {"beans", "legumes", "lentils", "chickpeas", "black beans",
                  "kidney beans", "pinto beans", "navy beans", "lima beans",
                  "edamame", "split peas", "soybeans"}
            or _penult in {"beans", "legumes"}
            or _leaf.endswith(" beans") or _leaf.endswith(" lentils")
            or path.startswith("pantry beans") or path.startswith("pantry legumes")):
        return "9"

    # Bakery/grain group 8 — leaf is bread/bagel/pasta/rice/cereal/flour
    GRAIN_LEAF_TOKENS = {"bread", "bagel", "tortilla", "pasta", "rice",
                         "grain", "grains", "cereal", "flour", "noodles",
                         "couscous", "quinoa", "barley", "oats", "oatmeal"}
    if (_leaf_tokens & GRAIN_LEAF_TOKENS
            or _penult in {"bread", "breads", "pasta", "rice", "rice & grains",
                            "rice grains", "grains", "grain", "cereal", "cereals",
                            "flour", "flours", "noodles", "tortillas", "bagels"}
            or _leaf.endswith(" bread") or _leaf.endswith(" pasta")
            or _leaf.endswith(" flour") or _leaf.endswith(" rice")
            or path.startswith("pantry pasta") or path.startswith("pantry rice")
            or path.startswith("pantry cereal") or path.startswith("pantry flour")
            or path.startswith("pantry grain") or path.startswith("pantry grains")):
        return "8"
    if path.startswith("bakery"):
        return "G"
    if path.startswith("beverage"):
        return "D"
    if path.startswith("frozen"):
        if re.search(r"\b(appetizers?|entrees?|meals?|dinners?|pizza|pot pie)\b", path):
            return "H"
        identity_group, _ = _group_from_family_match(identity)
        if identity_group != "0":
            return identity_group
        return "H"
    if "prepared" in path:
        return "H"
    if path.startswith("snack"):
        if "nuts" in path or "seeds" in path or re.search(r"\b(almond|peanut|cashew|walnut|pecan)\b", blob):
            return "A"
        return "J"
    if path.startswith("sports wellness"):
        return "K"
    if "baking mix" in path or "frosting" in path or "cake mix" in path:
        return "8"  # baking precursors → Bakery/grain group
    # Path-first catchall: when canonical_path is depth ≥ 2 and starts with a
    # known top-level, use the top-level's default group BEFORE letting the
    # identity_text fallback below override it. This prevents "Pillsbury Butter
    # Cake Mix" at canonical_path `Pantry > Baking Mixes > Cake Mix` from being
    # routed to Dairy because product_identity_fixed = "Butter".
    parts = [p.strip() for p in (canonical_path or "").split(" > ") if p.strip()]
    if len(parts) >= 2:
        TOP_LEVEL_DEFAULTS = {
            "pantry": "J", "snack": "J", "bakery": "G",
            "produce": "7", "beverage": "D", "frozen": "H",
            "dairy": "1", "meal": "H", "non-food": "N",
            "baby & toddler": "M",
        }
        top = parts[0].lower()
        if top in TOP_LEVEL_DEFAULTS:
            return TOP_LEVEL_DEFAULTS[top]
    # Identity fallback fires only for shallow / unknown canonical_path values.
    identity_group = _match_first(GROUP_RULES, identity)
    if identity_group != "0":
        return identity_group
    identity_group, _ = _group_from_family_match(identity)
    if identity_group != "0":
        return identity_group
    return ""


def family_from_identity(group: str, text: str, canonical_path: str = "",
                         food_name: str = "") -> str:
    if group == "H":
        return prepared_family_from_path(canonical_path, text)
    if group == "1" and re.search(
        r"\b(ice cream|frozen yogurt|gelato|sorbet|sherbet|popsicles?|frozen dessert)\b",
        text or "",
        re.I,
    ):
        return "5"
    # Tier 1: canonical_path first. The LLM's chosen bucket is the most
    # reliable signal — "Pillsbury Butter Cake Mix" at canonical_path
    # `Pantry > Baking Mixes > Cake Mix` matches the Cake Mix family, NOT
    # the Butter family even though product_identity_fixed = "Butter".
    for pattern, code in FAMILY_RULES.get(group, []):
        if pattern.search(canonical_path or ""):
            return code
    # Tier 2: food_name fallback. When canonical_path is silent on family
    # (e.g., generic "Pantry"), use product_identity_fixed. Plain "butter"
    # at canonical_path "Pantry" still resolves to butter family here.
    if food_name:
        for pattern, code in FAMILY_RULES.get(group, []):
            if pattern.search(food_name):
                return code
    # Tier 3: text fallback (canonical_label or identity_text).
    for pattern, code in FAMILY_RULES.get(group, []):
        if pattern.search(text or ""):
            return code
    return "0"


# ── Group rules: regex over BFC + title combined ─────────────────────────
GROUP_RULES: list[tuple[re.Pattern, str]] = [
    # ─────────────────────────────────────────────────────────────────────
    # Phase 2 fixes (2026-05-09) — TOP-PRIORITY recipe-side guards.
    # Each item-class below was misrouted by a downstream broad-noun rule
    # (chicken/beef/milk/onion/red-pepper/almond/bean/soda/rum). These guards
    # MUST fire first. See PHASE_0_RESULTS.md and ENCODER_ARCHITECTURE.md.
    # ─────────────────────────────────────────────────────────────────────
    # Broth/stock/bouillon — Pantry (J). "chicken broth" was wrongly Poultry.
    (re.compile(r"\b(?:chicken|beef|veg(?:etable)?|veggie|fish|seafood|bone|turkey|miso|dashi|mushroom|onion|ham|pork|lamb)?\s*(?:broth|stock|consomm[eé])\b|\bbouillon\b", re.I), "J"),
    # Baking soda/powder/bicarbonate — Pantry (J). "baking soda" was Beverage.
    (re.compile(r"\b(?:baking\s+(?:soda|powder)|bicarbonate(?:\s+of\s+soda)?|active\s+dry\s+yeast|instant\s+yeast|fresh\s+yeast)\b", re.I), "J"),
    # Extracts/essences/flavorings — Spices/Extracts (E). "almond extract"
    # was Nuts; "rum extract" was Beverage; "vanilla bean" was Legumes.
    (re.compile(r"\b(?:almond|rum|maple|peppermint|mint|coconut|lemon|orange|caramel|chocolate|coffee|brandy|hazelnut|raspberry|strawberry|banana|butter|anise|pineapple|pistachio|walnut|pecan|amaretto|champagne|sherry|root\s*beer)\s+(?:extract|essence|flavoring|flavour)\b|\bvanilla\s+(?:extract|essence|flavoring|flavour|pod|bean(?:s)?|bean\s+paste)\b", re.I), "E"),
    # Chocolate chips / butterscotch chips / peanut-butter chips — Pantry (J).
    # "milk chocolate chips" was Dairy via "milk".
    (re.compile(r"\b(?:milk|white|dark|semi[\s-]?sweet|bittersweet|mini|miniature|premium)?\s*chocolate\s+chips?\b|\bbutterscotch\s+chips?\b|\bcinnamon\s+chips?\b|\bpeanut\s+butter\s+chips?\b", re.I), "J"),
    # Coconut in dried/flake/shred forms — Pantry (J). "sweetened flaked
    # coconut" was Dairy via family-fallback.
    (re.compile(r"\b(?:flaked|shredded|desiccated|sweetened\s+flaked|sweetened\s+shredded|toasted|unsweetened\s+shredded)\s+coconut\b|\bcoconut\s+(?:flakes?|shreds?)\b", re.I), "J"),
    # Ground red pepper / cayenne / crushed red pepper — Spices (E).
    # "ground red pepper" was Vegetables via bell-pepper rule.
    (re.compile(r"\b(?:ground\s+red\s+pepper|cayenne(?:\s+pepper)?|crushed\s+red\s+pepper(?:\s+flakes)?|red\s+pepper\s+flakes?)\b", re.I), "E"),
    # Dried/dehydrated onion flakes/powder/granules — Spices (E), not veg.
    (re.compile(r"\b(?:dried|dehydrated|minced|granulated|toasted)\s+onion(?:\s+(?:flakes?|powder|granules?|bits?|minced))?\b|\bonion\s+flakes?\b", re.I), "E"),
    # Sauerkraut — Pantry > Sauerkraut (J), NOT Vegetable Spread fallback.
    (re.compile(r"\bsauerkraut\b", re.I), "J"),
    # Butter beans — group 9 (Legumes), NOT group 1 (Dairy butter rule).
    (re.compile(r"\bbutter\s+beans?\b|\bbutterbean\b", re.I), "9"),
    # Garlic/onion salt — group E (Spices), NOT group 6 (Vegetables garlic/onion rule).
    (re.compile(r"\b(?:garlic|onion|celery|seasoned)\s+salt\b", re.I), "E"),
    # Onion soup mix / dry onion soup — group J (Pantry mixes), NOT vegetable.
    (re.compile(r"\bonion\s+soup\s+mix\b|\bdry\s+onion\s+soup\b", re.I), "J"),
    # Pimiento(s) — group 6 (Vegetables/Canned Vegetables), NOT family-fallback to F.
    (re.compile(r"\bpimiento(?:s|es)?\b", re.I), "6"),
    # Mace (the spice, not macadamia/macaroni) — group E (Spices) explicitly.
    (re.compile(r"\bmace\b(?!.*(?:racing|ster))", re.I), "E"),
    # ─────────────────────────────────────────────────────────────────────
    # Dairy (1)
    (re.compile(r"milk|dairy|lactose", re.I), "1"),
    (re.compile(r"cheese(?!\s*(?:cake|sauce))", re.I), "1"),
    (re.compile(r"yogurt|yoghurt|kefir", re.I), "1"),
    (re.compile(r"\bcream\s+of\s+tartar\b", re.I), "E"),
    (re.compile(r"\b(?:peanut|almond|cashew|sunflower|seed|nut)\s+butter\b|\btahini\b", re.I), "A"),
    (re.compile(r"\bbutter\b(?!\s*(?:scotch|finger|nut))|margarine", re.I), "1"),
    (re.compile(r"\bcream\b(?!\s*(?:of|style))|whipped topping|coffee creamer", re.I), "1"),
    (re.compile(r"ice cream|frozen yogurt|frozen dessert|gelato|sorbet|sherbet|popsicle", re.I), "1"),
    (re.compile(r"sour cream|cottage cheese|cream cheese", re.I), "1"),
    # Recipe-side precedence guards. These must fire before the spice rules
    # below, otherwise "garlic cloves" becomes clove spice and "bell pepper"
    # becomes peppercorn.
    (re.compile(r"\b(?:garlic|onion)\s+powder\b", re.I), "E"),
    (re.compile(r"\bgarlic(?:\s+cloves?)?\b|\bonions?\b|\bshallots?\b|\bleeks?\b|\bscallions?\b|\bchives?\b", re.I), "6"),
    (re.compile(r"\b(?:baby\s+)?(?:spinach|kale|lettuce|arugula|greens|chard|collards?|watercress|romaine|iceberg|radicchio|escarole)\b", re.I), "6"),
    (re.compile(r"\b(?:baby\s+)?carrots?\b|\bpotatoes?\b|\bsweet potatoes?\b|\byams?\b|\bbeets?\b|\bturnips?\b|\bradishes?\b|\bparsnips?\b", re.I), "6"),
    (re.compile(r"\b(?:red pepper flakes?|crushed red pepper|chili flakes?|chile flakes?)\b", re.I), "E"),
    (re.compile(r"\b(?:red|green|yellow|orange|sweet|bell)\s+peppers?\b|\bbell peppers?\b|\bjalape(?:n|ñ)o(?:s)?\b|\bpoblanos?\b|\bserranos?\b|\bhabaneros?\b", re.I), "6"),
    # Spice prefix guard — "ground cinnamon", "ground ginger", "ground cumin"
    # would otherwise hit Red Meat's "ground" pattern. Catch them here first.
    (re.compile(r"\bground\s+(cinnamon|ginger|cumin|coriander|nutmeg|allspice|cardamom|cloves?|mace|turmeric|black pepper|white pepper|paprika|mustard seed|fennel|caraway)\b", re.I), "E"),
    # Spice-seed guard — "cardamom seeds", "coriander seeds", "cumin seeds"
    # are SPICES, not Nuts & Seeds. Catch them before the seeds-as-nuts rule.
    (re.compile(r"\b(cardamom|coriander|cumin|fennel|caraway|anise|dill|mustard|poppy|sesame|nigella|fenugreek|celery)\s+seeds?\b", re.I), "E"),
    # Phase 2 broth/baking/extract/coconut/sauerkraut guards — see top-of-list block.
    # Red Meat (2)
    (re.compile(r"\bbeef\b|\bsteak\b|\bjerky\b", re.I), "2"),
    (re.compile(r"\bpork\b(?!.*rind)|\bham\b|\bbacon\b", re.I), "2"),
    (re.compile(r"\blamb\b|\bveal\b|\bbison\b|\bvenison\b", re.I), "2"),
    (re.compile(r"pepperoni|salami|cold cut|deli meat|lunch meat|luncheon meat|luncheon loaf|hot\s*dog|sausage|brat|frank|potted meat|canned meat|breakfast patt", re.I), "2"),
    (re.compile(r"\bother meats?\b|\bmeat\b(?!\s*(?:less|alternative|free|substitute))|antelope|elk\b|wild game|exotic meat|frozen patty|frozen patties|burger pattie?s?|\bburgers?\b|wagyu|angus", re.I), "2"),
    # Poultry (3)
    (re.compile(r"chicken|turkey|poultry|duck\b|goose\b|quail|pheasant|cornish hen|game bird|squab|guinea fowl|dove\b|grouse|partridge|woodcock", re.I), "3"),
    # Fish (4)
    (re.compile(r"\bfish\b|\bseafood\b|\bshrimp\b|\bprawns?\b|\bcrab(?:meat| meat)?\b|\bcrabs\b|\blobsters?\b|\btuna\b|\bsalmon\b|\btilapia\b|\bclams?\b|\boysters?\b|\bmussels?\b|\banchov|\bcod\b|\bhalibut\b|\bhaddock\b|\btrout\b|\bsnapper\b|\bgrouper\b|\bmahi\b|\bswordfish\b|\bsardines?\b|\bherring\b|\bmackerel\b|\bcatfish\b|\bsquid\b|\bcalamari\b|\bscallops?\b|\bcrawfish\b|\bcrayfish\b|\bmonkfish\b|\boctopus\b|\bflounder\b|\bsole\b|\bpollock\b|\bperch\b|\bbass\b|\bbluefish\b|\bskate\b|\bsmelt\b|\bwhiting\b|\bwhitefish\b|\bcarp\b|\beel\b|\bsturgeon\b|\bcaviar\b|\broe\b|\bbasa\b|\bwalleye\b|\bpike\b|\bbarramundi\b|\bbranzino\b|\bdorade\b|\bjohn dory\b|\bred drum\b|\btarpon\b|\babalone\b|\bcuttlefish\b|\bconch\b|\bbonito\b|\bsurimi\b|\bimitation crab\b|\bkrab\b|\bkrab stick\b|\blox\b|\bgravlax\b|\bsmoked salmon\b|\bkombu\b|\bwakame\b|\bnori\b|\bhijiki\b|\bdashi konbu\b", re.I), "4"),
    # Eggs (5)
    (re.compile(r"\begg\b|\beggs\b|egg substitute", re.I), "5"),
    # Oils (B) — BEFORE vegetables so "olive oil" doesn't fall to "olive"
    (re.compile(r"\boil\b|\boils\b|cooking oil|vegetable oil|olive oil|shortening|lard|cooking spray|suet|tallow|schmaltz|ghee|drippings|copha|coconut cream concentrate", re.I), "B"),
    # Condiments (F) — BEFORE Vegetables so "salad dressing" doesn't grab a
    # mayonnaise/ketchup BFC, and "Pickles, Olives, Peppers & Relishes"
    # doesn't grab condiment SKUs.
    (re.compile(r"mayonnaise|\bmayo\b|ketchup|catsup|mustard|bbq|barbecue sauce|salad dressing|vinaigrette|hot sauce|sriracha|tabasco|soy sauce|teriyaki|tamari|fish sauce|worcester|hoisin|pasta sauce|marinara|alfredo sauce|pizza sauce|pesto|tomato sauce|cocktail sauce|tartar sauce|steak sauce|relish|pickle|salsa(?!\s*verde\s*flavored)|chutney|jam|jelly|preserve|marmalade|fruit spread|olives|other condiments|condiment|\bglaze\b|balsamic condiment|\bvinegar\b", re.I), "F"),
    # Vegetables (6)
    (re.compile(r"vegetable|veggie|tomato(?:es)?$|canned vegetable|frozen vegetable|fresh vegetable|salad(?:\s|$)|slaw|coleslaw", re.I), "6"),
    # Fruits (7)
    (re.compile(r"\bfruit\b|canned fruit|frozen fruit|dried fruit|applesauce|cranberr", re.I), "7"),
    # Grains (8)
    (re.compile(r"bread|bun|roll|bagel|tortilla|wrap|pita|naan|muffin|english muffin", re.I), "8"),
    (re.compile(r"pasta(?:\s|$)|noodle|macaroni|spaghetti|ramen|rice(?:\s|$)|grain|quinoa|couscous|oat", re.I), "8"),
    (re.compile(r"cereal|pancake|waffle|flour|baking mix|cake mix|cookie mix|cornmeal|stuffing", re.I), "8"),
    # Legumes (9)
    (re.compile(r"\b(?:chili|chile|cayenne|paprika|mustard|cumin|coriander)\s+powder\b", re.I), "E"),
    (re.compile(r"\bbean\b|\bbeans\b|lentil|chickpea|hummus|\bchili\b(?!\s+peppers?)|\bdal\b|\bdaal\b|channa|garbanzo|black-eyed|cowpea|mung|fava|navy bean|pinto|kidney bean|cannellini|adzuki|edamame|split pea|black bean|falafel", re.I), "9"),
    # Nuts & Seeds (A)
    (re.compile(r"\bnut\b|\bnuts\b|\bseed\b|\bseeds\b|peanut|almond|cashew|walnut|pecan|pistachio|hazelnut|filbert|brazil nut|macadamia|chestnut|pine nut|trail mix|nut butter|tahini|linseed|flaxseed|hemp seed|hemp heart|pumpkin seed|sunflower seed|chia seed|nutmeats|candlenut|kola nut|coco lopez|cream of coconut", re.I), "A"),
    # Sugars (C)
    (re.compile(r"sugar|sweetener|honey|syrup|molasses|agave|stevia|truvia|splenda|aspartame|saccharin|erythritol|xylitol|monk fruit|sucanat|jaggery|panela|piloncillo|rapadura|black treacle|treacle|golden syrup|sweet n low|sweet 'n low|sweet'n low|nutrasweet|equal\b|fructose|dextrose|glucose|maltose|invert sugar|coconut sugar|date sugar|barbados sugar|demerara|muscovado", re.I), "C"),
    # Spices (E) — match BEFORE Beverages so "rosemary"/"ginger" don't leak.
    # Catches the most common spice nouns explicitly so a recipe ingredient
    # string like "ginger root" or "dried rosemary" lands in E without
    # falling to family_fallback (which is slower and less specific).
    (re.compile(r"\brosemary\b|\bthyme\b|\boregano\b|\bbasil\b|\bsage\b|\bdill\b|\btarragon\b|\bmarjoram\b|\bparsley\b|\bcilantro\b|\bmint\b|\bmace\b|\bclove(?:s)?\b|\bcardamom\b|\bnutmeg\b|\ballspice\b|\bsaffron\b|\bcumin\b|\bcoriander\b|\bpaprika\b|\bturmeric\b|\bginger\b|\bgingerroot\b|garam masala|chili powder|curry powder|fennel seed|poppy seed|caraway|fenugreek|sumac|chat masala|sambhar|advieh|asafoetida|peppercorn|sea salt|kosher salt|table salt|fleur de sel", re.I), "E"),
    # Beverages (D) — alcohol, liqueurs, branded liqueurs, ice, espresso
    (re.compile(r"juice|nectar|drink|soda|water(?:\s|$)|coffee|espresso|tea(?:\s|$)|lemonade|cocktail|beer|wine|spirit|kombucha|energy drink|\brum\b|whiskey|whisky|vodka|gin\b|sherry|brandy|liqueur|champagne|sake|tequila|bourbon|cognac|vermouth|cider|\bice\b|ice cube|eggnog|kahlua|grand marnier|triple sec|grenadine|amaretto|baileys|frangelico|chambord|campari|aperol|prosecco|riesling|chardonnay|merlot|cabernet|pinot|rose|sangria|mead|stout|porter|ale\b|lager|guinness|coca.cola|\bcoke\b|diet cola|pepsi|sprite|seven.up|7.up|mountain dew|root beer|southern comfort|limoncello|angostura|bitters|ruby port|tawny port|creme de menthe|creme de cacao|creme de banane|crème|sour mix|simple syrup|tonic|seltzer|club soda|ginger ale|mineral water|sparkling water|kahlúa|sambuca|curaçao|curacao|chartreuse|drambuie|absinthe|jagermeister|jägermeister|schnapps|bloody mary mix|margarita mix|daiquiri mix|mojito mix|piña colada|pina colada|everclear|grain alcohol|moonshine|zinfandel|chianti|malbec|tempranillo|sauvignon|gewurztraminer|gewürztraminer|scotch\b|single malt|irish whiskey|rye whiskey|dark rum|light rum|spiced rum|white rum|gold rum|cachaça|cachaca|mezcal|pisco|grappa|aquavit|akvavit|slivovitz|raki|ouzo|arak|soju|baijiu|shochu|creme de noyaux|crème de noyaux|frangelico|midori|chambord|maraschino liqueur|cointreau|galliano|disaronno|benedictine|chartreuse|tia maria|amaro|fernet|aperitif|\balcohol\b|electrolyte solution|electrolyte drink|sports drink|pedialyte|gatorade|powerade|kirsch|kirschwasser|calvados|pernod|marsala|madeira|sangiovese|merlot|riesling|chardonnay|prosecco|cava|cremant|crémant|advocaat|aguardiente|chicha|horchata|jus\b|punch\b|pop\b|151.proof|grain.proof|7.up|seven up|cola\b|root beer|cream soda|orangeade|colada|piña|frappe|shake\b|smoothie|protein shake|\bmirin\b|cooking sake|shaoxing|huangjiu|soju|baijiu|chablis|burgundy|champagne|armagnac|bacardi|licor 43|creme de cassis|crème de cassis|liquor\b|hard liquor|distilled\s|cordial\b|aperol|campari\b|mezcal|raki", re.I), "D"),
    # Spices (E)
    (re.compile(r"spice|herb|seasoning|salt(?:\s|$)|pepper(?:corn)?(?:\s|$)|cinnamon|vanilla|extract|flavoring", re.I), "E"),
    # Condiments (F)
    (re.compile(r"sauce|ketchup|mustard|bbq|mayonnaise|mayo|dressing|salsa|dip|relish|pickle|olive|spread|jam|jelly|preserve|gravy|marinade|teriyaki|hot sauce|sriracha|vinegar", re.I), "F"),
    # Baked Goods (G)
    (re.compile(r"cookie|biscuit|cake|pie|pastry|croissant|sweet roll|donut|doughnut|brownie|scone|biscotti|crepe|crepes|eclair|strudel|turnover|danish|tart\b|cobbler|crumble|toaster pastry|toaster pastries|pop.?tart|fillo|filo cup|phyllo cup|calzone|empanada|sweet bakery|savoury bakery|savory bakery|crust|crescent|paratha|naan|arepa|tortilla shell|taco shell|pita pocket|focaccia|pancake|waffle|gingersnap|shortbread|macaron|macaroon|madeleine|financier|profiterole|cannol[oi]", re.I), "G"),
    (re.compile(r"baking decoration|dessert topping|frosting|icing|sprinkle|decorating gel|edible glitter sugar|fondant|gum paste|royal icing", re.I), "G"),
    # Prepared (H)
    (re.compile(r"frozen dinner|frozen entree|frozen appetizer|frozen meal|frozen pizza|refrigerated meal|frozen prepared", re.I), "H"),
    (re.compile(r"canned meal|prepared meal|deli(?:\s|$)|soup(?:\s|$)|other soup|pizza(?:\s|$)|burrito|taco|sandwich|wrap", re.I), "H"),
    (re.compile(r"ready to eat|meal kit|entree|side dish|meal starter|tostada|sushi|gazpacho|minestrone|chowder|bisque|stew\b|gumbo|pho\b|ramen soup|mexican dinner|skillet meal|kids meal|tv dinner|combination meal|stuffed nachos|nachos|antipasto|gyro|carnitas|barbacoa|al pastor|kebab|kabob|shawarma|falafel meal|dough based|pull.apart|tamale|enchilada|empanada filling|sloppy joe|manwich", re.I), "H"),
    (re.compile(r"meat alternative|meatless|meat free|meat substitute|seitan|tempeh|vegan burger|veggie burger|plant.based meat|tofu burger|chik'?n|turk'?y|vegetarian frozen|buffalo wing|corn dog|patties|patty|grillers|fakon", re.I), "H"),
    (re.compile(r"michelada|bloody mary mix|cooking mix|gravy mix", re.I), "H"),
    # Snacks (J)
    (re.compile(r"chip|pretzel|snack|candy|chocolate|gum\b|granola bar|protein bar|energy bar|popcorn|pork rind|marshmallow|fruit snack|fruit roll|gummy|gummies|red.hot|red hots|hard candy|caramel|toffee|fudge|brittle|nougat|licorice|lollipop|sucker|jelly bean|twinkie|ho.ho|ding dong|moon pie|whoopie|cupcake snack|wafer cookie|graham cracker|hershey|smarties|maltesers|ovaltine|kit kat|snickers|mars bar|milky way|reese|m&m|skittle|starburst|tootsie|gobstopper|laffy taffy|airhead|jolly rancher|sesame stick|frito|cheeto|dorito|tostito|sun chip|lay's|ruffles|cape cod|kettle chip|cachou|gumdrop|after eight|after dinner mint|andes mint|peppermint patty|york patty|peeps|necco|nerds|junior mints|dots\b|raisinets|whoppers|milk dud|sugar.free candy|marzipan|halva|rock candy", re.I), "J"),
    (re.compile(r"gelatin|pudding|jello|jell.o", re.I), "J"),
    (re.compile(r"food coloring|food color|sprinkles|jimmies", re.I), "J"),
    # Supplements (K)
    (re.compile(r"vitamin|supplement|protein powder|nutritional|spirulina|chlorella|moringa|ashwagandha|maca powder|bee pollen|royal jelly|propolis|colostrum|collagen powder|brewer'?s yeast|nutritional yeast|calcium powder|magnesium powder|mineral powder|bone meal|\bminerals\b", re.I), "K"),
    # Baby (M)
    (re.compile(r"baby|infant|toddler|formula", re.I), "M"),
]

# ── Form rules ───────────────────────────────────────────────────────────
FORM_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"frozen", re.I), "2"),
    (re.compile(r"canned|jarred|bottled", re.I), "3"),
    (re.compile(r"dried|dehydrated|dry\b", re.I), "4"),
    (re.compile(r"powder|powdered|instant|mix(?:es)?$", re.I), "5"),
    (re.compile(r"juice|drink|soda|water|milk|cream|liquid|oil|vinegar|sauce|broth", re.I), "6"),
    (re.compile(r"fresh|refrigerat|pre-packaged|salad", re.I), "1"),
    (re.compile(r"smoked|cured", re.I), "8"),
    (re.compile(r"pickle", re.I), "9"),
]

# ── Family rules per group ───────────────────────────────────────────────
FAMILY_RULES: dict[str, list[tuple[re.Pattern, str]]] = {
    "1": [  # Dairy
        (re.compile(r"cheese|cheez|cheddar|crema\b|cooking creme|cooking cream|creme fraiche|crème fraîche|ricotta|curds|paneer|halloumi|haloumi|mascarpone|feta|brie|camembert|gouda|gruyere|gruy[eè]re|edam|provolone|mozzarella|asiago|fontina|roquefort|stilton|gorgonzola|manchego|pecorino|parmesan|romano|burrata|chèvre|chevre|cojita|cotija|monterey jack|colby|havarti|munster|muenster|swiss cheese|jarlsberg|bocconcini|queso fresco|queso oaxaca|queso blanco|queso panela|asadero|chihuahua cheese|requesón|labneh|labne|skyr|crème caramel|panna cotta|flan(?!\s*pan)|fromage frais|fromage blanc|quark\b|khoya|mawa\b", re.I), "1"),
        (re.compile(r"yogurt|yoghurt|kefir", re.I), "2"),
        (re.compile(r"\bcream\b(?!\s*(?:cheese|of|style|tartar))|half.*half|whipped|creamer|topping|cool whip|dream whip|dulce de leche", re.I), "3"),
        (re.compile(r"\bbutter\b|margarine|ghee|\boleo\b|crisco", re.I), "4"),
        (re.compile(r"ice cream|frozen yogurt|gelato|sorbet|sherbet|popsicle|frozen dessert", re.I), "5"),
        (re.compile(r"sour cream", re.I), "6"),
        (re.compile(r"cottage cheese", re.I), "7"),
        (re.compile(r"cream cheese", re.I), "8"),
        (re.compile(r"whey|protein", re.I), "9"),
        (re.compile(r"almond|soy|oat|coconut|rice\s*milk|cashew|plant.based|non.dairy|tofu", re.I), "A"),
        (re.compile(r"condensed|evaporated", re.I), "B"),
        (re.compile(r"milk", re.I), "0"),
    ],
    "2": [  # Red Meat
        (re.compile(r"beef|steak|chuck|brisket|short rib|tri.?tip|sirloin|ribeye|rib eye|filet mignon|flank|skirt|round steak|round\b|oxtail|tenderloin|round roast|rump|prime rib|standing rib|crown roast|london broil|7.bone|pot roast|mutton|goat\s*meat", re.I), "0"),
        (re.compile(r"pork(?!.*(?:ham|bacon|sausage|pepperoni|salami|hot\s*dog|frank|brat))|spareribs|baby back rib|country.style rib|pork rib|carnitas|porchetta", re.I), "1"),
        (re.compile(r"lamb", re.I), "2"),
        (re.compile(r"veal", re.I), "3"),
        (re.compile(r"ham|bacon|sausage|pepperoni|salami|cold cut|hot\s*dog|frank|brat|chorizo|deli|pancetta|prosciutto|guanciale|mortadella|capicola|spam\b|corned beef|pastrami|kielbasa|bologna|liverwurst|braunschweiger|head cheese|meatball|meatloaf|tasso|andouille|merguez|nduja", re.I), "4"),
        (re.compile(r"venison|bison|elk|\bgame\b|frog'?s? leg|escargot|snail|alligator|kangaroo|wild boar|rabbit|hare\b|squirrel|opossum|antelope", re.I), "5"),
        (re.compile(r"\bliver\b|\bkidney(?!\s*bean)\b|tongue|tripe|sweetbread|gizzard|heart\b|brain\b|marrow|offal|pig'?s? feet|trotter|hock|head cheese", re.I), "6"),
    ],
    "3": [  # Poultry
        (re.compile(r"chicken", re.I), "0"),
        (re.compile(r"turkey", re.I), "1"),
        (re.compile(r"duck", re.I), "2"),
    ],
    "6": [  # Vegetables
        (re.compile(r"spinach|kale|lettuce|arugula|greens|chard|collard|watercress|endive|romaine|iceberg|radicchio|escarole|frisee|frisée|mesclun|rocket|mâche|mache|mizuna|tatsoi|alfalfa", re.I), "0"),
        (re.compile(r"carrot|potato|beet|turnip|sweet potato|yam|radish|parsnip|rutabaga|swede\b|jicama|kohlrabi|celeriac|kumara|yucca|cassava|taro|daikon|burdock", re.I), "1"),
        (re.compile(r"broccoli|cauliflower|cabbage|brussels|bok choy|pak choi|pak choy|kohlrabi|napa|rapini|broccoli rabe|broccolini|chinese broccoli|gai lan|choy sum|yu choy", re.I), "2"),
        (re.compile(r"green bean|snap bean|string bean|wax bean|haricot vert|haricots verts|edamame|snow pea|sugar snap|\bpea(?:s)?\b", re.I), "3"),
        (re.compile(r"squash|zucchini|pumpkin|gourd|courgette", re.I), "4"),
        (re.compile(r"onion|garlic|leek|shallot|scallion|chive", re.I), "5"),
        (re.compile(r"pepper(?!corn|oni)|chili|chile|chilies|jalape|habanero|serrano|poblano|chipotle|cayenne|aji amarillo|aji panca|aji yellow|ají amarillo|ají panca|ajies dulces|guajillo|pasilla|ancho|fresno|shishito|piquillo|peperoncino", re.I), "6"),
        (re.compile(r"tomato|tomatillo|rotel|passata|pico de gallo", re.I), "7"),
        (re.compile(r"corn(?!\s*(?:starch|syrup|bread|chip|flake|dog|meal|muffin))", re.I), "8"),
        (re.compile(r"mushroom|portobello|shiitake|cremini|chanterelle", re.I), "9"),
        (re.compile(r"celery|fennel|asparagus|artichoke|cucumber|eggplant|aubergine|okra|caper|gherkin|water chestnut|bamboo shoot|sprout|hearts of palm|palm heart|capsicum|nopale|cactus|fiddlehead|kelp|nori|seaweed|wakame|hijiki|purslane|chayote|jicama|salsify|samphire|ramps|veg.all|veg all|vegetable mix|mixed vegetable", re.I), "A"),
    ],
    "7": [  # Fruits
        (re.compile(r"apple|pear|quince|rhubarb|ackee", re.I), "0"),
        (re.compile(r"banana|plantain", re.I), "1"),
        (re.compile(r"orange|mandarin|tangerine|clementine|grapefruit|lemon|lime|citrus|kumquat|yuzu|citron|bergamot|blood orange|cara cara|satsuma|pomelo|ugli", re.I), "2"),
        (re.compile(r"berry|berries|strawberr|blueberr|raspberr|blackberr|cranberr|mulberr|gooseberr|boysenberr|lingonberr|elderberr|huckleberr|açaí|acai", re.I), "3"),
        (re.compile(r"grape|raisin|currant|sultana", re.I), "4"),
        (re.compile(r"melon|watermelon|cantaloupe|honeydew|casaba", re.I), "5"),
        (re.compile(r"peach|nectarine|plum|apricot|cherry|cherries|prune", re.I), "6"),
        (re.compile(r"mango|papaya|pineapple|kiwi|guava|passion|lychee|rambutan|durian|jackfruit|dragon fruit|starfruit|persimmon", re.I), "7"),
        (re.compile(r"pomegranate|fig|date", re.I), "8"),
        (re.compile(r"avocado|coconut", re.I), "9"),
    ],
    "8": [  # Grains
        (re.compile(r"bread|bun|roll|crouton|breadcrumb|panko|baguette|focaccia|brioche|challah|ciabatta|rye|pumpernickel|sourdough|panettone|stollen|fruitcake|wheat chex|chex\b|toasted oats|cheerios|cornflake|corn flake|rice krispie|frosted flake|bran flake|bran bud|all.bran|100% bran|natural bran|shredded wheat|wheat flake|french loaf|italian loaf|toast\b", re.I), "0"),
        (re.compile(r"bagel", re.I), "1"),
        (re.compile(r"tortilla|wrap|pita|naan|lavash|matzo|matzah", re.I), "2"),
        (re.compile(r"pasta|noodle|macaroni|spaghetti|ramen|linguine|fettuccine|penne|rigatoni|rotini|orzo|lasagna|gnocchi|udon|soba|vermicelli|tagliatelle|pappardelle|tortellini|ravioli|cavatappi|farfalle|ziti|cellophane|manicotti|cannelloni|wonton|dumpling skin|spring roll|gyoza|pierogi|ditalini|fusilli|elbows|shells|orecchiette|capellini|bucatini|rigate|tubetti|conchiglie", re.I), "3"),
        (re.compile(r"rice", re.I), "4"),
        (re.compile(r"oat|oatmeal", re.I), "5"),
        (re.compile(r"cereal|granola|muesli", re.I), "6"),
        (re.compile(r"flour|baking mix|wheat germ|wheat bran|cornstarch|wheat gluten|gluten flour|\bgluten\b|tapioca|tapioca starch|tapioca pearls|tapioca flour|natural bran|semolina|durum|matzo meal|cake meal|masa harina|masa\b|graham|cornmeal|polenta meal|lecithin|liquid glucose|glucose syrup|\bfarina\b|cracked wheat|cream of wheat|cream of rice|acorn meal", re.I), "7"),
        (re.compile(r"quinoa|couscous|barley|millet|farro|bulgur|polenta|grits|amaranth|buckwheat|kasha|hominy|teff|spelt|kamut|wheat berry|hash brown|tater tot|french fries|french fry|home fries|potato wedges|sorghum|\bmilo\b|psyllium|chia|flax|sago\b|\bbesan\b|gram flour|tef|emmer|einkorn|spelt berry|rye berry|crostini|pastina", re.I), "8"),
        (re.compile(r"phyllo|filo|puff pastry|pastry dough|pie crust|pizza dough|biscuit dough|crescent roll|vol.au.vent|tart shell|empanada dough|wonton skin|spring roll wrapper|egg roll wrapper|rice paper", re.I), "9"),
        (re.compile(r"ladyfinger|sponge cake|biscotti", re.I), "A"),
    ],
    "D": [  # Beverages
        # Family 0: generic beverages (default fall-through)
        (re.compile(r"\bjuice\b|nectar|fruit drink|fruit punch|lemonade|limeade|orangeade", re.I), "1"),
        (re.compile(r"\bsoda\b|cola\b|cream soda|root beer|ginger ale|tonic|club soda|seltzer|sparkling water|carbonated", re.I), "2"),
        (re.compile(r"\bcoffee\b|espresso|cappuccino|latte|mocha|frappe|frappuccino|americano|macchiato|cold brew", re.I), "3"),
        (re.compile(r"\btea\b|chai|matcha|kombucha|iced tea", re.I), "4"),
        (re.compile(r"\bwater\b|spring water|mineral water|distilled water|electrolyte|hydration|alkaline water", re.I), "5"),
        (re.compile(r"energy drink|sports drink|gatorade|powerade|red bull|monster|rockstar|protein drink|protein shake|meal replacement|smoothie", re.I), "6"),
        (re.compile(r"plant milk|almond milk|soy milk|oat milk|coconut milk|cashew milk|rice milk|hemp milk|pea milk|pistachio milk", re.I), "7"),
        (re.compile(r"wine\b|sangria|vermouth|riesling|chardonnay|pinot|cabernet|merlot|zinfandel|chianti|malbec|sauvignon|champagne|prosecco|cava|rose wine|red wine|white wine|sparkling wine", re.I), "8"),
        (re.compile(r"beer|ale\b|lager|stout|porter|guinness|ipa\b|pilsner|hefeweizen|cider|hard seltzer", re.I), "9"),
        (re.compile(r"vodka|whiskey|whisky|bourbon|rum|gin\b|tequila|mezcal|brandy|cognac|scotch|sake|spirit|liquor|liqueur|cocktail|kahlua|amaretto|baileys|jagermeister|absinthe|grappa", re.I), "A"),
        (re.compile(r"cocktail mix|bloody mary mix|margarita mix|daiquiri mix|mojito mix|simple syrup|grenadine|bitters|tonic|sour mix", re.I), "B"),
    ],
    "E": [  # Spices, Herbs & Seasonings
        (re.compile(r"\bsalt\b|fleur de sel|kosher salt|sea salt|table salt|pickling salt|curing salt|smoked salt", re.I), "0"),
        (re.compile(r"\bpepper(?:corn)?\b", re.I), "1"),
        (re.compile(r"cinnamon|nutmeg|allspice|clove|cardamom|\bmace\b|anise|saffron|fenugreek|sumac|juniper|star anise", re.I), "2"),
        (re.compile(r"basil|oregano|thyme|rosemary|parsley|cilantro|\bmint\b|sage|dill|tarragon|marjoram|bay leaf|bay leaves|lemongrass|chervil|epazote|verbena|herbes|savory|lavender|borage|sorrel|file powder|filé|gumbo file|kaffir lime|hibiscus|chamomile|rose hip|rosehip|elderflower|jasmine flower|nettle|aloe vera|lovage|truffle|black truffle|white truffle|nasturtium|calendula|edible flower|violet flower|rose petal|squash blossom|dried lily|lily bud|kasuri methi|methi leaves|fenugreek leaves|culantro|shiso|pandan|curry leaves|kaffir|holy basil", re.I), "3"),
        (re.compile(r"cumin|coriander|paprika|turmeric|chili powder|curry|garam masala|\bginger\b|gingerroot|wasabi|harissa|ras el hanout|galangal|horseradish|fennel pollen|korma paste|tikka paste|tandoori paste|masala paste|rendang paste|laksa paste|tom yum|red curry paste|green curry paste|panang paste|massaman|advieh|ajwain|\bhing\b|asafoetida|achar masala|amchur|kala namak", re.I), "4"),
        (re.compile(r"vanilla|extract|flavoring|essence|zest|imitation maple|imitation flavor|maple flavor|almond flavor|rum flavor|brandy flavor|butter flavor|coconut flavor|peppermint flavor|mesquite powder|mesquite seasoning|liquid smoke flavor", re.I), "5"),
        # Family 7 (specific spice powders/seeds) MUST come BEFORE family 6
        # (generic seasoning|spice blend) so a canonical_path like
        # "Pantry > Spices & Seasonings > Onion Powder" matches the specific
        # rule first instead of being collapsed into Spice Blend by the
        # "seasoning" token in "Spices & Seasonings" parent path.
        (re.compile(r"garlic powder|onion powder|celery seed|fennel seed|caraway|poppy seed|sesame seed|mustard seed|nigella", re.I), "7"),
        (re.compile(r"seasoning|spice blend|\brub\b|spice mix|adobo|jerk|cajun|creole|italian seasoning|herbes de provence|chinese five|old bay|meat tenderizer|liquid amino|bragg's amino|coconut amino|chat masala|chaat masala|sambhar|sambar powder|achiote|annatto|sazon|tajin|za'atar|zaatar|dukkah|berbere|baharat|dough enhancer|dough conditioner", re.I), "6"),
        (re.compile(r"baking soda|baking powder|yeast|cream of tartar|xanthan|cornstarch|arrowroot|pectin|gelatin sheets|agar|fish sauce powder|custard powder|custard\b|pudding mix|meringue powder|bisquick|cake mix|brownie mix|muffin mix|biscuit mix|pancake mix|pizza crust mix|bread mix|tartaric acid|citric acid|cream of tartar|potassium bitartrate|ascorbic acid|saltpeter|niter|nitrite|nitrate", re.I), "8"),
        (re.compile(r"\bcocoa\b|cocoa powder|chocolate powder|carob|cacao", re.I), "9"),
        (re.compile(r"liquid smoke|\bmsg\b|monosodium|asafoetida|sumac|amchur|kala namak|black salt", re.I), "B"),
    ],
    "F": [  # Condiments
        (re.compile(r"mayonnaise|mayo\b|aioli|ali.oli|miracle whip|sandwich spread", re.I), "0"),
        (re.compile(r"ketchup|catsup", re.I), "1"),
        (re.compile(r"mustard", re.I), "2"),
        (re.compile(r"bbq|barbecue", re.I), "3"),
        (re.compile(r"hot sauce|sriracha|tabasco|harissa|sambal|gochujang|chili paste|chile paste|chili crisp|chili oil", re.I), "4"),
        (re.compile(r"soy sauce|teriyaki|tamari|fish sauce|worcester|hoisin|oyster sauce|ponzu|shoyu|aloha shoyu|ketjap manis|kecap manis|sweet soy", re.I), "5"),
        (re.compile(r"salsa|guacamole|pico de gallo", re.I), "6"),
        (re.compile(r"salad dressing|vinaigrette|ranch|italian dressing|caesar|tzatziki|tahini", re.I), "7"),
        (re.compile(r"pasta sauce|marinara|alfredo|pesto|pizza sauce|tomato sauce|demi.?glace|béchamel|bechamel|hollandaise|velouté|veloute|mole|gravy|au jus|stock|broth|consomm[eé]|dashi|kitchen bouquet|bouillon|bouquet garni", re.I), "8"),
        (re.compile(r"pickle|relish|olive|sauerkraut|kimchi|capers|pimiento|pimento|chutney|gherkin|miso|gochujang|doubanjiang|nuoc cham|nam pla|giardiniera|tapenade|kalamata", re.I), "9"),
        (re.compile(r"jam|jelly|preserve|marmalade|fruit spread|mincemeat|apple butter|pumpkin butter|cookie butter|lemon curd|nutella|chocolate spread|hazelnut spread|vegemite|marmite|achar|ajvar|alcaparrado", re.I), "A"),
        (re.compile(r"vinegar|balsamic glaze|balsamic reduction", re.I), "B"),
    ],
}

# ── Processing rules ─────────────────────────────────────────────────────
PROC_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\braw\b|\buncooked\b|\bunseasoned\b", re.I), "1"),
    (re.compile(r"\bcooked\b|\broasted\b|\bbaked\b|\bgrilled\b|\bfried\b|\bboiled\b", re.I), "3"),
    (re.compile(r"\bsmoked\b|\bcured\b|\baged\b|\bdry.?aged\b", re.I), "4"),
    (re.compile(r"\bfermented\b|\bcultured\b|\bprobiotic\b", re.I), "5"),
    (re.compile(r"\bready to eat\b|\bfully cooked\b|\bpre.?cooked\b|\bheat.*serve\b", re.I), "6"),
    (re.compile(r"\bready to cook\b|\boven ready\b", re.I), "7"),
    (re.compile(r"\bseasoned\b|\bmarinated\b|\bflavored\b|\bteriyaki\b|\bbbq\b", re.I), "8"),
    (re.compile(r"\bbreaded\b|\bbattered\b|\bcrust\b|\bpanko\b", re.I), "9"),
    (re.compile(r"\bfortified\b|\benriched\b|\bvitamin\b", re.I), "A"),
]

# ── Product type rules ───────────────────────────────────────────────────
PTYPE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bground\b|\bminced\b", re.I), "2"),
    (re.compile(r"\bsliced\b|\bdeli\s|\bshaved\b|\bthin.?cut\b", re.I), "1"),
    (re.compile(r"\bsteak\b|\bfillet\b|\bchop\b|\bcutlet\b|\bloin\b", re.I), "3"),
    (re.compile(r"\bshredded\b|\bgrated\b", re.I), "5"),
    (re.compile(r"\bcrumbl", re.I), "7"),
    (re.compile(r"\bcubed?\b|\bdiced\b", re.I), "8"),
    (re.compile(r"\bpatty\b|\bpatties\b|\bburger\b", re.I), "C"),
    (re.compile(r"\bstrip\b|\btender\b|\bnugget\b|\bfinger\b", re.I), "D"),
    (re.compile(r"\bspread\b", re.I), "6"),
    (re.compile(r"\bblock\b|\bchunk\b", re.I), "4"),
    (re.compile(r"\bstick\b|\bstring\b", re.I), "9"),
    (re.compile(r"\bwedge\b", re.I), "A"),
    (re.compile(r"\bwhole\b", re.I), "0"),
]


def _match_first(rules: list[tuple[re.Pattern, str]], text: str) -> str:
    for pattern, code in rules:
        if pattern.search(text or ""):
            return code
    return "0"


_SIMPLE_FRESH_TOMATO_ITEMS = {
    "tomato",
    "tomatoes",
    "roma tomato",
    "roma tomatoes",
    "plum tomato",
    "plum tomatoes",
    "cherry tomato",
    "cherry tomatoes",
    "grape tomato",
    "grape tomatoes",
}

_TOMATO_NON_FRESH_RE = re.compile(
    r"\b(?:can|cans|canned|jarred|bottled|paste|sauce|puree|purée|passata|"
    r"juice|soup|ketchup|catsup|salsa|marinara|pasta\s+sauce|pizza\s+sauce|"
    r"sun\s*dried|sun-dried|dried|dehydrated|crushed|stewed|whole\s+peeled|"
    r"rotel|tomatoes?\s+with\s+green\s+chil(?:e|i)s?)\b",
    re.I,
)
_TOMATO_FRESH_HINT_RE = re.compile(
    r"\b(?:fresh|ripe|raw|roma|plum|cherry|grape|beefsteak|heirloom|campari|"
    r"vine|small|medium|large|sliced|chopped|diced|quartered|seeded|peeled|"
    r"cored)\b",
    re.I,
)
_TOMATO_COUNT_RE = re.compile(
    r"\b\d+(?:\s+\d+/\d+|/\d+)?\s+(?:(?:small|medium|large|ripe|fresh)\s+)?"
    r"(?:(?:roma|plum|cherry|grape|beefsteak|heirloom|campari)\s+)?tomato(?:es)?\b",
    re.I,
)


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _looks_like_fresh_tomato_text(
    *,
    combined: str,
    canonical_path: str,
    food_name: str,
) -> bool:
    path_norm = _norm_key(canonical_path)
    if (
        "canned vegetables tomatoes" in path_norm
        or path_norm.startswith("pantry canned vegetables")
        or path_norm.startswith("pantry sauces")
        or path_norm.startswith("pantry condiments")
        or "tomato sauce" in path_norm
        or "tomato paste" in path_norm
    ):
        return False
    if _TOMATO_NON_FRESH_RE.search(combined):
        return False
    item_norm = _norm_key(food_name)
    if path_norm.startswith("produce vegetables tomatoes"):
        return True
    if item_norm not in _SIMPLE_FRESH_TOMATO_ITEMS:
        return False
    return bool(_TOMATO_COUNT_RE.search(combined) or _TOMATO_FRESH_HINT_RE.search(combined))


def _is_fresh_tomato_intent(
    *,
    group: str,
    family: str,
    combined: str,
    canonical_path: str,
    food_name: str,
) -> bool:
    """Return True when the ingredient asks for fresh whole tomatoes.

    This is an HTC rule, not a planner SKU blocklist. It lets recipe-side
    "1 tomato, sliced" and "Roma tomatoes, chopped" share the same form code
    as retail fresh tomato packages while keeping canned/sauce/paste tomatoes
    in their own codes.
    """
    if group != "6" or family != "7":
        return False
    return _looks_like_fresh_tomato_text(
        combined=combined,
        canonical_path=canonical_path,
        food_name=food_name,
    )


@dataclass(frozen=True)
class HTC:
    code: str          # 8 chars
    group: str
    family: str
    food: str          # 2 chars from food_slot_registry.csv, or '00' unresolved
    form: str
    processing: str
    ptype: str
    check: str
    confidence: float
    source: str        # which input fed the group: 'category' / 'description' / 'unresolved'

    @property
    def code_7(self) -> str:
        return self.code[:7]


def _group_from_family_match(text: str) -> tuple[str, str]:
    """Walk every group's family rules; if one fires, the group is implied.

    Recipe ingredients ("garlic", "parsley", "paprika") don't match the
    coarse GROUP_RULES regex but DO match a family-rule pattern. Use that
    as a fallback so the encoder can resolve raw ingredient nouns without
    a BFC hint.
    """
    if not text:
        return "0", "0"
    for group, rules in FAMILY_RULES.items():
        for pattern, family_code in rules:
            if pattern.search(text):
                return group, family_code
    return "0", "0"


def encode(
    category: str,
    description: str = "",
    extra: str = "",
    *,
    food_name: str = "",
    canonical_path: str = "",
    modifier: str = "",
    identity_mode: bool = True,
) -> HTC:
    """Encode an 8-char HTC code from any combination of category + description.

    Both retail products and recipe ingredients flow through this same encoder.
    For retail: category=BFC, description=title, extra=product_identity_fixed
    For recipes: category=resolved_food_category, description=item, extra=display

    In identity_mode (the default), positions 5-7 are neutralized so
    ``htc_code`` can be used as the recipe-to-retail join key.  The caller can
    still mine form/processing/type from the source row facets.
    """
    cat = (category or "").strip()
    desc = (description or "").strip()
    ext = (extra or "").strip()
    cname = (canonical_path or "").strip()
    fname = (food_name or "").strip()
    mod = (modifier or "").strip()
    combined = f"{cat} {desc} {ext} {fname} {mod}"
    path_group = group_from_canonical_path(cname, fname or desc or ext)

    # Non-food short-circuit: cleaners, supplies, props
    if NON_FOOD_PATTERNS.search(combined) and not (
        cname and path_group and path_group not in {"0", "N"}
    ):
        code = code_from_parts("N", "0", "00")
        return HTC(
            code=code, group="N", family="0", food="00",
            form="0", processing="0", ptype="0", check=code[-1],
            confidence=1.0, source="non_food",
        )

    # Poultry-precedence override: fires when the food is *explicitly* a
    # poultry deli/cured product. Two trigger paths:
    #   (a) retail-side: deli/cured-cuts BFC + poultry word in title
    #   (b) recipe-side: poultry word AND a cured-meat word in the same string
    # Catches "turkey breast", "deli turkey", "turkey ham", "chicken bacon",
    # "smoked turkey breast", etc. — keeps them out of Red Meat.
    cat_lc = cat.lower()
    txt = f"{desc} {ext}"
    is_deli_bfc = bool(re.search(
        r"pepperoni|salami|cold cut|deli|lunch meat|sausage|hot ?dog|frank|brat|bacon",
        cat_lc, re.I,
    ))
    poultry_in_title = bool(re.search(
        r"\b(turkey|chicken|duck|goose|cornish hen|pheasant)\b",
        txt, re.I,
    ))
    poultry_cured_compound = bool(poultry_in_title and re.search(
        r"\b(ham|bacon|sausage|salami|pepperoni|cold cut|lunch meat|deli|"
        r"smoked|cured|sliced|breast|thigh|wing|leg|drumstick|whole|ground|"
        r"roast|jerky|frank|brat)\b",
        txt, re.I,
    ))
    allow_poultry_override = not cname or path_group in {"2", "3"}
    if allow_poultry_override and ((is_deli_bfc and poultry_in_title) or poultry_cured_compound):
        # Determine family/ptype using the existing family rules for poultry,
        # but feed the regular form/processing/ptype routine to detect
        # ground/sliced/smoked.
        group = "3"
        family = "0"
        for pattern, code in FAMILY_RULES.get("3", []):
            if pattern.search(combined):
                family = code
                break
        form = _match_first(FORM_RULES, cat)
        if form == "0":
            form = _match_first(FORM_RULES, combined)
        proc = _match_first(PROC_RULES, combined)
        ptype = _match_first(PTYPE_RULES, combined)
        # Smoked/cured deli adjust: form=8 (smoked) processing=4 (cured)
        if "smoked" in combined.lower():
            form = "8"
        if any(w in combined.lower() for w in ("deli", "lunch meat",
                                               "luncheon", "sliced")) \
                and ptype == "0":
            ptype = "1"
        identity_text = fname or desc or ext
        registry = default_registry()
        # Poultry-deli override is a confident assertion — we know it's poultry,
        # so don't let lookup_any drag the group elsewhere.
        entry = registry.lookup(group, family, identity_text)
        if entry:
            group = entry.htc_group
            family = entry.htc_family
            food = entry.food_slot
        else:
            food = "00"
        code_form, code_proc, code_ptype = ("0", "0", "0") if identity_mode else (form, proc, ptype)
        code = code_from_parts(group, family, food, code_form, code_proc, code_ptype)
        return HTC(
            code=code, group=group, family=family, food=food,
            form=code_form, processing=code_proc, ptype=code_ptype, check=code[-1],
            confidence=0.85, source="poultry_deli_override",
        )

    explicit_group_hint = ""
    if re.search(r"\bpizza\s+(dough|crust|shell)\b", combined, re.I):
        explicit_group_hint = "8"
    elif re.search(r"\bpizza\s+(sauce|seasoning)\b", combined, re.I):
        explicit_group_hint = "F"
    elif re.search(r"\bpizzas?\b", combined, re.I):
        explicit_group_hint = "H"
    elif _looks_like_fresh_tomato_text(
        combined=combined,
        canonical_path=cname,
        food_name=fname,
    ):
        explicit_group_hint = "6"

    prepared_hint = ""
    if explicit_group_hint == "H":
        prepared_hint = "H"

    # Group: category first, then description, then extra, then family fallback
    group = path_group or explicit_group_hint or prepared_hint or _match_first(GROUP_RULES, cat)
    confidence = 0.9
    source = "canonical_path" if path_group else "description" if explicit_group_hint else "category"
    if group == "0":
        group = _match_first(GROUP_RULES, desc)
        confidence = 0.6 if group != "0" else 0.2
        source = "description" if group != "0" else "unresolved"
    if group == "0":
        group = _match_first(GROUP_RULES, ext)
        if group != "0":
            confidence = 0.5
            source = "extra"
    # FAMILY-RULE FALLBACK: covers raw ingredient nouns (garlic, parsley, …).
    # This is actually a STRONGER signal than loose GROUP_RULES because it
    # directly matches a specific food noun (garlic, basil, paprika), so its
    # confidence is high.
    family_from_fallback = "0"
    if group == "0":
        group, family_from_fallback = _group_from_family_match(combined)
        if group != "0":
            confidence = 0.70
            source = "family_fallback"

    # Form: category strongest
    form = _match_first(FORM_RULES, cat)
    if form == "0":
        form = _match_first(FORM_RULES, combined)

    # Family: per-group rules over combined text. If we already learned the
    # family from the family-fallback path above, use it.
    identity_text = " ".join(part for part in (fname, mod, desc, ext) if part).strip()
    family = family_from_identity(group, identity_text, cname, food_name=fname) if cname or fname else family_from_fallback
    if family == "0":
        family = family_from_fallback
    if family == "0":
        for pattern, code in FAMILY_RULES.get(group, []):
            if pattern.search(combined):
                family = code
                break

    # Processing & ptype: from description
    proc = _match_first(PROC_RULES, combined)
    ptype = _match_first(PTYPE_RULES, combined)

    registry_lookup_text = fname or desc or ext
    if _is_fresh_tomato_intent(
        group=group,
        family=family,
        combined=combined,
        canonical_path=cname,
        food_name=fname,
    ):
        # Recipe prep words ("sliced", "diced", "chopped") describe what the
        # user will do to a fresh tomato, not the package form to buy.
        family = "7"
        form = "1"
        proc = "0"
        ptype = "0"
        registry_lookup_text = "tomato"

    registry = default_registry()
    entry = registry.lookup(group, family, registry_lookup_text)
    if not entry and group == "0":
        # Only fall back to the cross-group lookup when our own group inference
        # came up empty. Otherwise the bucket-free lookup can drag a correctly
        # routed ingredient (e.g. "ground nutmeg" -> group E spices) into a
        # noise entry that happens to share a generic token (e.g. "Grounds"
        # in group H prepared meals).
        entry = registry.lookup_any(registry_lookup_text)
    if entry:
        group = entry.htc_group
        family = entry.htc_family
        food = entry.food_slot
    else:
        food = "00"
    code_form, code_proc, code_ptype = ("0", "0", "0") if identity_mode else (form, proc, ptype)
    code = code_from_parts(group, family, food, code_form, code_proc, code_ptype)
    return HTC(
        code=code,
        group=group, family=family, food=food,
        form=code_form, processing=code_proc, ptype=code_ptype,
        check=code[-1], confidence=confidence, source=source,
    )
