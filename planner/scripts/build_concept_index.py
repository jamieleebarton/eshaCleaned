#!/usr/bin/env python3
"""Build concept_index.json — the correct architecture replacement for
htc_reference.json.

Concept key = (canonical_path, modifier, htc_form_code)

Per concept, store packages[] = up to 20 cheapest distinct UPCs verbatim,
each carrying its OWN consensus_fndds and consensus_sr28 so macros for the
PICKED package come from THAT package's evidence — never pooled across SKUs.

Hard filters:
  - htc_form_code NOT IN ('', '00000000', NULL)
  - consensus_canonical NOT LIKE 'Non-Food%'
  - upc NOT IN priced_products_excluded.csv
"""
from __future__ import annotations
import csv, json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
EXCL = ROOT / "recipe_pricing" / "priced_products_excluded.csv"
BLOCKLIST = ROOT / "recipe_pricing" / "non_food_blocklist.txt"
REJECT_LOG = ROOT / "recipe_pricing" / "non_food_rejected_skus.csv"
OUT = ROOT / "planner" / "data" / "concept_index.json"

MAX_PACKAGES = 20
BAD_HTC_GROUPS = {"0", "N"}

# Household-free recipe ingredients such as tap water are handled on the
# recipe side in planner/household_free.py and never enter the cart/pantry
# tensors. The concept index remains a retail package index only.

# Path-conditional SKU rejects. (canonical_path prefix or regex,
# tokens-that-disqualify). Applied AFTER the global blocklist; catches
# wrong-form SKUs at otherwise-valid food paths (Citrus Splash drink at
# Limes path, Smoothie at Strawberries path, Lunchmeat at Chicken Broth path).
import re as _re
PATH_CONDITIONAL_REJECT = [
    (_re.compile(r"^Produce > Fruit > "),
        ["juice cocktail", "drink mix", "cocktail mixer", "splash",
         "seltzer", "hard seltzer", "wine cooler", "drink blend",
         "juice blend", "100% juice", "juice", "margarita mixer", "margarita mix",
         "gatorade", "powerade", "sports drink", "energy drink",
         "lemonade mix", "iced tea mix", "smoothie", "soda"]),
    (_re.compile(r"^Produce > Vegetables > "),
        ["juice cocktail", "drink mix", "cocktail mixer", "drink blend",
         "canned", "shelf stable", "shelf-stable", "dehydrated",
         "freeze dried", "dried"]),
    (_re.compile(r"^Frozen > Frozen Fruit > "),
        ["smoothie", "drink", "cocktail", "wine cooler", "drink mix"]),
    (_re.compile(r"^Pantry > Oil(?: >|$)"),
        ["chili sauce", "salsa", "mustard sauce", "salad dressing",
         "soy sauce", "barbecue sauce", "hot sauce", "marinade", "magic man",
         # R13 — Olive Oil bucket had Duke's Olive Oil MAYO at top
         "mayo", "mayonnaise", "ranch dressing", "vinaigrette",
         # R13 — Pantry > Oil generic had Movie Theater Popcorn Topping
         "popcorn", "popcorn topping", "topping oil", "movie theater",
         "lamp oil", "fragrance oil", "essential oil", "massage oil",
         "lip oil", "vitamin e oil", "skin", "hair", "face and body",
         "revlon"]),
    (_re.compile(r"^Pantry > Spices"),
        ["toddler", "baby food", "infant", "puff", "drink mix", "tea bag",
         "complete seasoning", "all purpose spice", "all-purpose spice",
         "all purpose seasoning", "all-purpose seasoning",
         "italian seasoning",
         "cereal", "oatmeal", "granola", "cookie", "snack mix",
         "cinnamon roll", "cinnamon bread", "coffee creamer",
         "flavored coffee", "k-cup", "k cup",
         # Pre-mixed sweet spice blends at the pure-spice path
         "cinnamon sugar", "vanilla sugar", "pumpkin pie spice mix",
         "sugar bottle", "sweetened spice"]),
    (_re.compile(r"^Snack > Candy > Mints$"),
        ["live plant", "seedling", "fertilizer", "potted", "fresh mint plant"]),
    (_re.compile(r"^Pantry > Broth"),
        ["lunchmeat", "jerky", "patty", "nugget", "tender", "wing",
         "breast", "drumstick", "marrow bone", "stock cube"]),
    (_re.compile(r"^Dairy > Cheese(?: >|$)"),
        ["cheese product", "cheese food", "pasteurized recipe",
         "pasteurized prepared", "imitation cheese",
         # Snack-cheese-only SKUs at block-cheese paths
         "babybel", "string cheese", "snack cheese",
         "snack pack", "cheese stick"]),
    # Standard recipe mozzarella should not route to vegan substitutes or
    # another cheese subtype merely because the SKU was misfiled at a
    # mozzarella path.
    (_re.compile(r"^Dairy > Cheese > Mozzarella$"),
        ["dairy free", "dairy-free", "vegan", "plant based", "plant-based",
         "gouda", "cheddar", "mozzarella blend", "blend cheese"]),
    (_re.compile(r"^Dairy > Mozzarella Cheese$"),
        ["dairy free", "dairy-free", "vegan", "plant based", "plant-based",
         "gouda", "cheddar", "mozzarella blend", "blend cheese"]),
    # Cheddar specifically — recipe wants block cheddar to grate; snack
    # cheddar packs are a different product
    (_re.compile(r"^Dairy > Cheese > Cheddar"),
        ["babybel", "string cheese", "snack cheese", "snack pack",
         "cheese stick", "cheese curds", "cheese cube",
         "spray cheese", "cheese wow", "easy cheese", "spreadable cheese",
         "cheese spread", "snack portion", "dip cup",
         # Velveeta is processed cheese product, not real cheddar
         "velveeta", "kraft singles", "american singles"]),
    (_re.compile(r"^Pantry > Sauces .*Aioli$"),
        ["chipotle sauce", "salsa", "hot sauce"]),
    (_re.compile(r"^Pantry > Pasta > Macaroni > Shells$"),
        ["fideo", "spaghetti", "rotini", "fusilli"]),
    (_re.compile(r"^Beverage > Spirits > "),
        ["malt liquor", "ice tea", "iced tea"]),
    (_re.compile(r"^Pantry > Bacon Bits$"),
        ["bac'n", "bac n", "imitation bacon"]),
    (_re.compile(r"^Frozen > Vegetables > Chili$"),
        ["beef chili with beans"]),
    # Sausage subtype isolation — chorizo is NOT andouille is NOT kielbasa.
    # Without these, the cheapest chorizo SKU wins at every sausage variant
    # path because the leaf-overlap guard only checks PATH leaves not SKU
    # names. Each subtype gets its own reject of OTHER subtypes.
    (_re.compile(r"^Meat & Seafood > Sausage > Andouille"),
        ["chorizo", "kielbasa", "italian sausage", "italian style",
         "polish sausage", "bratwurst", "bologna", "frankfurter", "hot dog"]),
    (_re.compile(r"^Meat & Seafood > Sausage > Kielbasa"),
        ["chorizo", "andouille", "italian sausage", "italian style",
         "bratwurst", "bologna", "frankfurter", "hot dog", "salami"]),
    (_re.compile(r"^Meat & Seafood > Sausage > Chorizo"),
        ["andouille", "kielbasa", "italian sausage", "italian style",
         "polish sausage", "bratwurst", "bologna", "frankfurter", "hot dog"]),
    (_re.compile(r"^Meat & Seafood > Sausage > Italian"),
        ["chorizo", "andouille", "kielbasa", "polish sausage",
         "bratwurst", "bologna", "frankfurter", "hot dog"]),
    (_re.compile(r"^Meat & Seafood > Sausage > Bratwurst"),
        ["chorizo", "andouille", "kielbasa", "italian sausage",
         "polish sausage", "bologna", "frankfurter", "hot dog"]),
    (_re.compile(r"^Meat & Seafood > Sausage > Pork Sausage$"),
        ["chorizo con queso", "andouille", "kielbasa", "italian sausage",
         "bologna", "frankfurter", "hot dog", "turkey sausage", "chicken sausage"]),
    # Pasta subtype isolation
    (_re.compile(r"^Pantry > Pasta > Spaghetti"),
        ["macaroni", "shells", "penne", "rigatoni", "fusilli",
         "rotini", "ziti", "elbow", "fideo"]),
    (_re.compile(r"^Pantry > Pasta > Penne"),
        ["spaghetti", "macaroni", "shells", "fusilli", "rotini",
         "ziti", "elbow", "fideo", "linguine", "fettuccine"]),
    (_re.compile(r"^Pantry > Pasta > Macaroni > Shells$"),
        ["spaghetti", "penne", "rigatoni", "fusilli", "rotini",
         "ziti", "elbow", "fideo", "linguine", "fettuccine"]),
    # Bean/legume isolation — kidney is not pinto is not garbanzo
    (_re.compile(r"^Pantry > Beans > Kidney"),
        ["pinto", "garbanzo", "chickpea", "black bean", "navy",
         "great northern", "lima"]),
    (_re.compile(r"^Pantry > Beans > Pinto"),
        ["kidney", "garbanzo", "chickpea", "black bean", "navy",
         "great northern", "lima"]),
    (_re.compile(r"^Pantry > Beans > Black"),
        ["kidney", "garbanzo", "chickpea", "pinto", "navy",
         "great northern", "lima"]),
    # Honey-bun is a pastry but NOT a "pastry shell" — that's a different
    # food (puff-pastry shells for tarts).
    (_re.compile(r"^Bakery > Pastry > Pastry Dough"),
        ["honey bun", "iced bun", "donut", "cinnamon roll", "danish"]),
    (_re.compile(r"^Bakery > Pastry Shells"),
        ["honey bun", "iced bun", "donut", "cinnamon roll", "danish"]),
    # Drink-mix path quarantines
    (_re.compile(r"^Pantry > Flour > Drink Mix"),
        ["walnut", "kool aid", "atole"]),
    # Aioli is mayo-based, not chili sauce
    (_re.compile(r"^Pantry > Sauces & Salsas > Aioli$"),
        ["chili sauce", "thai", "sweet chili", "salsa", "barbecue",
         "soy", "shrimp sauce", "boom boom", "honey mustard", "ranch dressing",
         "yum yum"]),
    # R13: bacon path was returning Lightlife Smart Bacon Plant-Based for
    # plain bacon recipes. Reject vegan/plant-based at meat paths.
    (_re.compile(r"^Meat & Seafood > Bacon"),
        ["plant-based", "plant based", "vegan", "vegetarian bacon",
         "smart bacon", "lightlife", "tempeh", "tofu bacon", "beyond"]),
    (_re.compile(r"^Meat & Seafood > Poultry(?:$| > )"),
        ["unmeat", "plant-based", "plant based", "vegan", "vegetarian",
         "soy chicken", "beyond chicken", "tofu chicken", "meat alternative",
         "chick'n", "veggie dogs", "lunchmeat", "lunch meat",
         "deli sliced", "deli style sliced"]),
    # Raw chicken breast is a staple recipe ingredient. Do not let canned,
    # breaded, fully-cooked, deli, or meal-kit chicken win the same leaf just
    # because it shares "chicken breast" tokens.
    (_re.compile(r"^Meat & Seafood > Poultry > Chicken Breast$"),
        ["canned", "oz can", "pouch", "chunk", "shredded", "fully cooked",
         "nugget", "popcorn", "breaded", "bites", "grilled", "roasted",
         "rotisserie", "diced", "dices", "strips", "skewer", "skewers",
         "fajita", "fajitas", "stuffed", "cordon bleu", "with gravy",
         "shortcuts", "carbonara", "skillet meal", "frozen entree",
         "frozen dinner", "tv dinner", "lunchable", "salad kit"]),
    (_re.compile(r"^Beverage > Juice > Orange Juice"),
        ["splash", "v8 splash", "drink blend", "cocktail mixer", "smoothie"]),
    # R13: dip path needs modifier match — Dean's French Onion Dip was
    # absorbing 83 distinct recipes (bean dip, spinach dip, etc.) at one
    # generic dip concept.
    # Mixed nuts / nuts paths should reject "dessert topping" and ice
    # cream toppings.
    (_re.compile(r"^Snack > Nuts"),
        ["dessert topping", "ice cream topping", "sundae topping",
         "candied", "honey roasted dessert"]),
]


def load_excluded_upcs() -> set[str]:
    excl: set[str] = set()
    if EXCL.exists():
        with EXCL.open() as f:
            for row in csv.DictReader(f):
                u = (row.get("upc") or "").strip()
                if u: excl.add(u)
    return excl


def load_blocklist() -> list[str]:
    """Load non-food token phrases from non_food_blocklist.txt.
    Returns lowercase, normalized (single-space) phrases."""
    import re as _re
    out: list[str] = []
    if not BLOCKLIST.exists():
        return out
    for line in BLOCKLIST.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"): continue
        s = s.lower()
        s = _re.sub(r"[^a-z0-9 -]", " ", s)
        s = _re.sub(r"\s+", " ", s).strip()
        if s: out.append(s)
    return out


def name_blocked(name: str, blocklist: list[str]) -> str | None:
    """Return the matched blocklist phrase if name is non-food, else None.
    Substring match after lowercase + punctuation-stripped normalization."""
    if not name: return None
    import re as _re
    nl = name.lower()
    nl = _re.sub(r"[^a-z0-9 -]", " ", nl)
    nl = _re.sub(r"\s+", " ", nl).strip()
    for phrase in blocklist:
        if phrase in nl:
            return phrase
    return None


def _norm(s: str) -> str:
    import re as _re
    s = (s or "").lower()
    s = _re.sub(r"[^a-z0-9 -]", " ", s)
    return _re.sub(r"\s+", " ", s).strip()


def path_conditional_reject(name: str, cp: str) -> str | None:
    """If canonical_path matches one of the PATH_CONDITIONAL_REJECT patterns
    AND SKU name contains a disqualifying token for that path, return the
    matched token. Both name and phrase are normalized identically so '100%
    juice' matches '100 juice' after punctuation stripping."""
    if not name or not cp: return None
    nl = _norm(name)
    for pat, toks in PATH_CONDITIONAL_REJECT:
        if pat.match(cp):
            for t in toks:
                if _norm(t) in nl:
                    return t
    return None


LEAF_STOP = {
    "the", "a", "an", "of", "and", "or", "with", "fresh", "raw",
    "organic", "plain", "style", "flavor", "flavored", "natural",
}
GENERIC_LEAF_TOKENS = {
    "meat", "seafood", "poultry", "produce", "vegetables", "vegetable",
    "fruit", "fruits", "pantry", "dairy", "snack", "meal", "frozen",
    "beverage", "food", "foods",
}


def _stem_token(token: str) -> str:
    if len(token) <= 3:
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("oes") and len(token) > 4:
        return token[:-2]
    if token.endswith("es") and len(token) > 3 and not token.endswith("ses"):
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _word_tokens(value: str) -> list[str]:
    return [
        _stem_token(t)
        for t in _re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(t) > 2 and t not in LEAF_STOP
    ]


def leaf_identity_reject(name: str, cp: str) -> str | None:
    """Reject SKUs whose title does not carry the path leaf identity.

    This catches contaminated exact buckets such as "Dairy > Mozzarella
    Cheese" containing smoked gouda. It intentionally ignores very generic
    department leaves, and it accepts compact compound matches so
    "bread crumbs" satisfies "Breadcrumbs".
    """
    if not name or not cp or " > " not in cp:
        return None
    leaf = cp.split(" > ")[-1]
    leaf_tokens = [
        t for t in _word_tokens(leaf)
        if t not in GENERIC_LEAF_TOKENS
    ]
    if not leaf_tokens:
        return None
    name_tokens = set(_word_tokens(name))
    leaf_compact = "".join(leaf_tokens)
    name_compact = "".join(_word_tokens(name))
    if leaf_compact and leaf_compact in name_compact:
        return None
    missing = [t for t in leaf_tokens if t not in name_tokens]
    if missing:
        return "leaf_token:" + ",".join(missing)
    return None


def main():
    excl = load_excluded_upcs()
    blocklist = load_blocklist()
    print(f"loaded {len(excl):,} excluded upcs", file=sys.stderr)
    print(f"loaded {len(blocklist):,} non-food blocklist phrases", file=sys.stderr)
    rejections: list[dict] = []

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""
        SELECT upc, name, brand, cents, grams, cpg, size_display,
               REPLACE(htc_form_code, '~', '') AS htc_form,
               consensus_canonical, consensus_modifier,
               consensus_fndds, consensus_sr28, consensus_pid
        FROM priced_products
        WHERE available = 1
          AND grams > 0 AND cents > 0
          AND htc_form_code IS NOT NULL
          AND htc_form_code NOT IN ('', '00000000')
          AND consensus_canonical IS NOT NULL
          AND consensus_canonical != ''
          AND consensus_canonical NOT LIKE 'Non-Food%'
    """)

    # No NAME_BLOCKLIST and no IMPOSTER_RULES — those were band-aids for
    # miscategorized SKUs. The reclassifier (recipe_pricing/reclassify_canonical_paths.py)
    # moves SKUs to their CORRECT canonical_path so the planner naturally
    # never picks pepper jack at the plain Cheese path, cooking spray at the
    # Vegetable Oil path, baby food at adult-recipe paths, etc. Trust the
    # canonical_path; that's its job.

    n_total = 0; n_excluded = 0; n_skipped_zero = 0; n_blocked = 0
    by_concept: dict[str, list] = defaultdict(list)
    seen_upc_per_concept: dict[str, set] = defaultdict(set)

    for row in cur.fetchall():
        n_total += 1
        upc, name, brand, cents, grams, cpg, size_disp, htc_form, cp, mod, fndds, sr28, pid = row
        if upc in excl:
            n_excluded += 1; continue
        if not htc_form or htc_form == "00000000" or htc_form[:1] in BAD_HTC_GROUPS:
            n_skipped_zero += 1; continue
        # SKU sanity gate — reject non-food products that the LLM classifier
        # placed at food canonical_paths (Mrs Meyer's at basil, Bonnie Plants
        # at mints, Magic Man Chili Plant-Based at oil, etc.). Brand-aware
        # via combined name+brand check.
        full_name_brand = f"{name or ''} {brand or ''}"
        blocked_phrase = name_blocked(full_name_brand, blocklist)
        if blocked_phrase:
            n_blocked += 1
            rejections.append({
                "upc": upc, "name": (name or "")[:80], "brand": (brand or "")[:40],
                "canonical_path": cp or "", "matched_phrase": blocked_phrase,
                "rule": "non_food_blocklist",
            })
            continue
        # Path-conditional SKU reject — Citrus Splash at Limes, Smoothie at
        # Strawberries, Lunchmeat at Chicken Broth, Magic Man Chili at Oil.
        cond = path_conditional_reject(name or "", cp or "")
        if cond:
            n_blocked += 1
            rejections.append({
                "upc": upc, "name": (name or "")[:80], "brand": (brand or "")[:40],
                "canonical_path": cp or "", "matched_phrase": cond,
                "rule": "path_conditional",
            })
            continue
        # NEW SCHEMA: concept_key = (canonical_path | htc_form). Modifier is
        # NOT a partition dimension — it's a per-package attribute used by
        # the picker for ranking within the pool. HTC + canonical_path
        # already encode food identity (evap milk has different htc than fresh,
        # almond flour has different htc than wheat). Modifier was over-
        # splitting same-identity SKUs (Plain milk vs Whole milk vs 1% milk
        # all have same htc=10016A0Q — same product class, was 8 mini-pools).
        modifier = (mod or "").strip() or "Plain"
        cp = (cp or "").strip()
        concept_key = f"{cp}|{htc_form}"
        # Dedupe by upc within concept (priced_products has duplicate rows per source)
        if upc in seen_upc_per_concept[concept_key]: continue
        seen_upc_per_concept[concept_key].add(upc)
        by_concept[concept_key].append({
            "upc": upc,
            "name": name or "",
            "brand": brand or "",
            "cents": int(cents),
            "grams": float(grams),
            "cpg": float(cpg) if cpg else float(cents)/float(grams),
            "size_display": size_disp or "",
            "modifier": modifier,  # ranking attribute, not partitioning
            "consensus_fndds": (fndds or "").strip(),
            "consensus_sr28":  (sr28  or "").strip(),
            "consensus_pid":   (pid   or "").strip(),
        })

    print(f"  scanned: {n_total:,} rows", file=sys.stderr)
    print(f"  excluded by UPC: {n_excluded:,}", file=sys.stderr)
    print(f"  skipped 00000000: {n_skipped_zero:,}", file=sys.stderr)
    print(f"  rejected by non-food blocklist: {n_blocked:,}", file=sys.stderr)
    print(f"  distinct concepts: {len(by_concept):,}", file=sys.stderr)
    if rejections:
        with REJECT_LOG.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rejections[0].keys()))
            w.writeheader()
            for r in rejections: w.writerow(r)
        print(f"  → rejection log: {REJECT_LOG.name}", file=sys.stderr)

    # Sort packages by:
    #   1. name contains all canonical_path-leaf tokens (descending: more = better)
    #   2. cpg ASC (cheaper = better)
    # This pushes "Whole Milk" SKUs above "Skim Milk" SKUs at the
    # Dairy > Milk path, so the cheapest pick still has the right form.
    import re
    STOP = {"the","a","an","of","and","or","with","fresh","whole","raw","organic","plain"}
    # Flavor/variant tokens. If a SKU name contains one of these AND the
    # token is NOT in the pool's leaf, rank it behind plain products for the
    # same pool. This fixes equal-price ties such as Mott's Strawberry
    # Applesauce beating plain applesauce without deleting valid variant SKUs
    # from the evidence.
    VARIANT_TOKENS = {
        # flavor adjectives
        "strawberry", "mango", "peach", "cinnamon", "banana", "berry",
        "blueberry", "cherry", "raspberry", "assorted", "variety",
        "flavored", "flavour", "pumpkin", "vanilla", "chocolate",
        "caramel", "honey", "lemonade", "passionfruit", "orange",
        "grape", "cocoa", "sweetened", "applewood", "smoked", "smoke",
        "lemon", "lime", "garlic", "rosemary", "thyme", "basil",
        "jalapeno", "spicy", "ranch", "parmesan", "asiago", "pesto",
        "olive", "fiesta", "italian style", "mexican style", "buffalo",
        "barbecue", "bbq", "salt and vinegar", "salt vinegar",
        # cross-food contamination tokens
        "blend", "mixed", "imitation", "substitute", "alternative",
    }
    def leaf_tokens(cp: str) -> list[str]:
        leaf = cp.split(" > ")[-1].lower() if cp else ""
        # KEEP "whole" in leaf — it's a discriminator for milk/chicken/etc.
        return [w for w in re.findall(r"[a-z]+", leaf) if len(w) > 2]
    out: dict[str, dict] = {}
    for ck, pkgs in by_concept.items():
        cp, htc_form = ck.split("|", 1)
        leaf_toks = leaf_tokens(cp)
        leaf_set = set(leaf_toks)
        def variant_count(p):
            nl = p["name"].lower()
            # Variants only count if they're NOT in the pool's leaf (so a
            # "Strawberry" SKU is plain at the Strawberry leaf, but flavored
            # at the Applesauce leaf).
            return sum(1 for t in VARIANT_TOKENS if t in nl and t not in leaf_set)
        def rank(p):
            nl = p["name"].lower()
            n_match = sum(1 for t in leaf_toks if t in nl)
            return (-n_match, variant_count(p), p["cpg"])
        pkgs.sort(key=rank)
        out[ck] = {
            "canonical_path": cp,
            "htc_form": htc_form,
            "leaf_tokens": leaf_toks,
            "n_skus_total": len(pkgs),
            "packages": pkgs[:MAX_PACKAGES],
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        json.dump(out, f)
    print(f"\n→ {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)", file=sys.stderr)
    print(f"  {len(out):,} concept_keys, "
          f"{sum(len(c['packages']) for c in out.values()):,} package rows",
          file=sys.stderr)


if __name__ == "__main__":
    main()
