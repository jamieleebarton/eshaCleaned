#!/usr/bin/env python3
"""Stage D — recursive leaf minting.

For every gap_flag=TRUE row in retail_leaf_v2.csv:
  1. construct a candidate leaf path from head_phrase + compound_prefix + NER spans
  2. validate by counting other gap rows that would map to the same minted leaf
  3. keep mints with member_count ≥ 3 (configurable)
  4. emit:
       - retail_leaf_v2.csv updated in place: gap rows get retail_leaf=minted path,
         confidence=0.55, sources_agreed=1, with mint marker in provenance
       - axes/_proposed.tsv: tokens proposed for vocab inclusion
       - gap_audit.csv: singleton mints (count<3) for human review
"""
from __future__ import annotations
import argparse, csv, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
RM   = REPO / "retail_mapper"
V2   = RM / "v2"
CACHE = V2 / ".cache"
RECONCILED = V2 / "retail_leaf_v2.csv"
PROPOSED   = V2 / "_proposed_tokens.tsv"
GAP_AUDIT  = V2 / "gap_audit.csv"
csv.field_size_limit(sys.maxsize)

# --- minimal vocab for path construction --------------------------------------
SUPER = {
    "almondmilk":"Beverage", "almond milk":"Beverage", "almond beverage":"Beverage",
    "oatmilk":"Beverage", "oat milk":"Beverage", "oat drink":"Beverage",
    "soymilk":"Beverage", "soy milk":"Beverage",
    "coconut milk":"Beverage", "cashew milk":"Beverage", "rice milk":"Beverage",
    "milk":"Dairy",
    "yogurt":"Dairy", "kefir":"Dairy", "cheese":"Dairy", "cream cheese":"Dairy",
    "ice cream":"Frozen", "gelato":"Frozen", "sorbet":"Frozen", "frozen yogurt":"Frozen",
    "mayonnaise":"Pantry", "mayo":"Pantry", "aioli":"Pantry",
    "ketchup":"Pantry", "mustard":"Pantry", "honey":"Pantry", "syrup":"Pantry",
    "ranch":"Pantry", "dressing":"Pantry", "vinaigrette":"Pantry",
    "salsa":"Pantry", "sauce":"Pantry", "spread":"Pantry",
    "bread":"Pantry", "bun":"Pantry", "tortilla":"Pantry",
    "cookie":"Snack", "cracker":"Snack", "chip":"Snack", "popcorn":"Snack",
    "candy":"Snack", "chocolate bar":"Snack", "granola bar":"Snack",
    "cereal":"Pantry", "granola":"Pantry", "oatmeal":"Pantry",
    "coffee":"Beverage", "tea":"Beverage", "soda":"Beverage", "juice":"Beverage",
    "eggnog":"Beverage", "nog":"Beverage",
    "soup":"Pantry", "stew":"Pantry", "chili":"Pantry",
    "pasta":"Pantry", "noodles":"Pantry",
    "rice":"Pantry",
    "beans":"Pantry", "lentils":"Pantry",
    "pizza":"Frozen", "burrito":"Frozen", "taco":"Frozen", "meal kit":"Frozen",
    "beef":"Meat & Seafood", "pork":"Meat & Seafood", "chicken":"Meat & Seafood",
    "fish":"Meat & Seafood", "salmon":"Meat & Seafood", "tuna":"Meat & Seafood",
    "egg":"Dairy", "eggs":"Dairy",
    "fruit":"Produce", "vegetable":"Produce",
    "almond":"Snack", "cashew":"Snack", "peanut":"Snack", "walnut":"Snack",
    "peanut butter":"Pantry", "almond butter":"Pantry", "nut butter":"Pantry",
}
GROUP_HINTS = {
    "Beverage": {
        ("almondmilk","almond milk","almond beverage"): "Plant-based Milk > Almond",
        ("oatmilk","oat milk","oat drink"): "Plant-based Milk > Oat",
        ("soymilk","soy milk"): "Plant-based Milk > Soy",
        ("coconut milk",): "Plant-based Milk > Coconut",
        ("cashew milk",): "Plant-based Milk > Cashew",
        ("rice milk",): "Plant-based Milk > Rice",
        ("eggnog","nog"): "Eggnog",
        ("coffee",): "Coffee",
        ("tea",): "Tea",
        ("juice",): "Juice",
        ("soda",): "Soda",
    },
    "Dairy": {
        ("milk",): "Milk",
        ("yogurt",): "Yogurt",
        ("kefir",): "Kefir",
        ("cheese",): "Cheese",
        ("cream cheese",): "Cream Cheese",
    },
    "Frozen": {
        ("ice cream","gelato"): "Ice Cream",
        ("sorbet",): "Sorbet",
        ("frozen yogurt",): "Frozen Yogurt",
        ("pizza",): "Pizza",
        ("taco","burrito","meal kit"): "Meal Kit",
    },
    "Pantry": {
        ("mayonnaise","mayo"): "Condiment > Mayonnaise",
        ("aioli",): "Condiment > Aioli",
        ("ketchup",): "Condiment > Ketchup",
        ("mustard",): "Condiment > Mustard",
        ("honey",): "Sweetener > Honey",
        ("syrup",): "Sweetener > Syrup",
        ("ranch",): "Salad Dressing > Ranch",
        ("dressing","vinaigrette"): "Salad Dressing",
        ("salsa",): "Condiment > Salsa",
        ("sauce",): "Condiment > Sauce",
        ("spread",): "Condiment > Spread",
        ("peanut butter","almond butter","nut butter"): "Spreads > Nut Butter",
        ("bread","bun","tortilla"): "Bread",
        ("cereal","granola","oatmeal"): "Breakfast Cereal",
        ("pasta","noodles"): "Pasta",
        ("rice",): "Rice",
        ("beans","lentils"): "Legumes",
        ("soup","stew","chili"): "Soup",
    },
}

# canonical flavor / claim tokens we want as the leaf-tail
KNOWN_FLAVORS = {
    "vanilla","chocolate","strawberry","banana","mango","blueberry","raspberry",
    "chipotle","sriracha","wasabi","horseradish","garlic","lime","lemon","mint",
    "honey","maple","caramel","cinnamon","pumpkin spice","pumpkin","matcha","mocha",
    "salted caramel","peanut butter","cookies and cream","cookie dough",
    "hot honey","plain","original","unflavored","light","unsweetened","sweetened",
    "low fat","nonfat","whole milk","reduced fat","fat free","dairy free",
    "non-dairy","vegan","organic","gluten free",
    "smoky","spicy","hot","cold","oat nog","almond nog","soy nog","coconut nog",
    "olive oil","extra virgin","sea salt","kosher",
    "french vanilla","vanilla bean","dark chocolate","milk chocolate",
    "white chocolate","double chocolate","triple chocolate",
    "fudge","fudge chunk",
}

# Fall back to axes/category.tsv for ANY product whose head doesn't match SUPER
def _load_cat_tsv():
    out = {}
    for line in open(REPO / "retail_mapper" / "axes" / "category.tsv"):
        if line.startswith("#") or not line.strip(): continue
        p = line.rstrip("\n").split("\t")
        if len(p) >= 3: out[p[0].strip().lower()] = (p[1].strip(), p[2].strip())
    return out

_CAT_TSV = None
def cat_tsv():
    global _CAT_TSV
    if _CAT_TSV is None: _CAT_TSV = _load_cat_tsv()
    return _CAT_TSV

def _resolve_pipe(option_str: str, context: str) -> str:
    if "|" not in option_str: return option_str
    options = [o.strip() for o in option_str.split("|") if o.strip()]
    if not options: return option_str
    ctx = (context or "").lower()
    best, bs = options[0], -1
    for opt in options:
        sc = sum(1 for t in opt.lower().replace("-"," ").split() if t in ctx)
        if sc > bs: best, bs = opt, sc
    return best

def find_super(text: str) -> tuple[str,str,str]:
    """Return (super, group_path, key_token). Try SUPER (with group hints) first,
    then fall back to axes/category.tsv (804 tokens). Resolve pipe-separated
    context-dependent fields against `text`."""
    t = (text or "").lower()
    best_super = best_grp = best_key = ""
    best_score = -1
    for key, sup in SUPER.items():
        if key in t:
            pos = t.rfind(key)
            score = len(key) * 1000 + pos
            if score > best_score:
                best_score = score; best_super = sup; best_key = key
    if best_super:
        for keys, label in GROUP_HINTS.get(best_super, {}).items():
            if best_key in keys: best_grp = label; break
        if not best_grp: best_grp = best_key.title()
        return (best_super, best_grp, best_key)
    # fallback: walk axes/category.tsv (with pipe resolution)
    cat = cat_tsv()
    for key, (sup, grp) in cat.items():
        if key in t:
            pos = t.rfind(key)
            score = len(key) * 1000 + pos
            if score > best_score:
                best_score = score; best_super = sup; best_grp = grp; best_key = key
    if best_super:
        return (
            _resolve_pipe(best_super, t),
            _resolve_pipe(best_grp, t) or best_key.title(),
            best_key,
        )
    return ("","","")

_SUPERSCORE = {}

def find_flavor(text: str, head_token: str) -> str:
    t = (text or "").lower()
    hits = []
    for fl in KNOWN_FLAVORS:
        if fl in t and fl != head_token:
            hits.append(fl)
    # prefer longest, take first
    hits.sort(key=lambda x: -len(x))
    return hits[0].title() if hits else ""

def mint_path(title: str, head: str, prefix: str, ner: str) -> tuple[str, str]:
    """Return (leaf_path, dominant_token). dominant_token used to bucket gaps.

    Composition strategy:
      super > group > head_token > [storage-state] > [compound modifier]

    The compound modifier is built by collecting EVERY known flavor / modifier
    that appears in (title + head + prefix + ner), title-cased and joined.
    This preserves "Lemon Beet" instead of dropping to just "Lemon".
    """
    text = " ".join(filter(None, [title, head, prefix, ner.replace("|", " ")]))
    sup, grp, head_tok = find_super(text)
    if not sup:
        return ("", "")
    text_lc = text.lower()

    # 1) gather ALL flavor/modifier matches (longest-first to handle multi-word)
    flav_matches = []
    for f in sorted(KNOWN_FLAVORS, key=lambda x: -len(x)):
        if f in text_lc and f != head_tok:
            # check this flavor isn't a substring of an already-collected one
            if not any(f in m or m in f for m in flav_matches):
                flav_matches.append(f)
    # storage/form qualifier
    storage_words = ("freeze dried","dried","fresh","frozen","canned","powdered","roasted","smoked","dehydrated")
    storage = ""
    for s in storage_words:
        if s in text_lc: storage = s.title(); break

    # 2) build path
    parts = [sup, grp] if grp and grp.lower() != sup.lower() else [sup]
    head_title = head_tok.title() if head_tok else ""
    if head_title and head_title.lower() not in (sup.lower(), grp.lower() if grp else ""):
        parts.append(head_title)
    if storage and (not flav_matches or storage.lower() != flav_matches[0]):
        parts.append(storage)
    # 3) compound modifier: join up to 3 flavor matches in title order
    if flav_matches:
        # order them by appearance in the text so "Lemon Beet" not "Beet Lemon"
        ordered = sorted(set(flav_matches[:5]), key=lambda f: text_lc.find(f))
        # drop generic flavors when a specific one is present
        specific = [f for f in ordered if f not in ("plain","original","flavored","unflavored")]
        chosen = (specific or ordered)[:3]
        compound = " ".join(c.title() for c in chosen)
        if compound and compound.lower() not in [p.lower() for p in parts]:
            parts.append(compound)
    leaf = " > ".join([p for p in parts if p])
    return (leaf, head_tok)

def run(min_members: int = 3):
    print(f"reading {RECONCILED}")
    rows = list(csv.DictReader(open(RECONCILED)))
    gaps = [r for r in rows if r.get("gap_flag") == "True"]
    print(f"  {len(rows)} rows, {len(gaps)} gap candidates")

    # mint per-row
    mint_buckets: dict[str, list[int]] = defaultdict(list)
    minted_paths: dict[int, tuple[str, str]] = {}
    proposed_tokens: Counter = Counter()
    skipped_has_b1 = 0
    for i, r in enumerate(rows):
        if r.get("gap_flag") != "True": continue
        # GUARD: don't replace rows that already have a valid leaf from any
        # signal. Only mint when retail_leaf is empty or 'Other > Unclassified'.
        existing = r.get("retail_leaf", "") or ""
        if existing and "Other > Unclassified" not in existing and len(existing) > 12:
            skipped_has_b1 += 1
            continue
        mc_raw = r.get("mint_candidate") or "{}"
        try: mc = json.loads(mc_raw)
        except Exception: mc = {}
        head = mc.get("head_phrase","")
        prefix = mc.get("compound_prefix","")
        ner = mc.get("ner","")
        path, tok = mint_path(r["title"], head, prefix, ner)
        if path and tok:
            mint_buckets[path].append(i)
            minted_paths[i] = (path, tok)
            proposed_tokens[tok] += 1
    print(f"  guarded: {skipped_has_b1} rows kept their existing leaf (no mint override)")

    keepers = {p for p, idxs in mint_buckets.items() if len(idxs) >= min_members}
    print(f"  minted {len(mint_buckets)} unique leaf candidates")
    print(f"  keepers (members≥{min_members}): {len(keepers)}")

    # update rows in-place
    n_applied = 0
    n_singleton = 0
    audit = []
    for i, r in enumerate(rows):
        if i not in minted_paths: continue
        path, tok = minted_paths[i]
        members = len(mint_buckets[path])
        if path in keepers:
            r["retail_leaf"] = path
            r["confidence"] = "0.55"
            r["sources_agreed"] = "1"
            r["gap_flag"] = "False"
            prov = json.loads(r.get("provenance") or "{}")
            prov["minted"] = {"path": path, "head_token": tok, "members": members}
            r["provenance"] = json.dumps(prov)
            n_applied += 1
        else:
            n_singleton += 1
            audit.append({
                "fdc_id": r["fdc_id"],
                "title": r["title"],
                "minted_path": path,
                "head_token": tok,
                "members": members,
                "branded_food_category": r.get("branded_food_category",""),
            })

    # write back
    print(f"  applied to {n_applied} rows; {n_singleton} singletons sent to gap_audit.csv")
    with open(RECONCILED, "w", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    if audit:
        with open(GAP_AUDIT, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(audit[0].keys()))
            w.writeheader(); w.writerows(audit)
        print(f"  wrote {GAP_AUDIT}")
    if proposed_tokens:
        with open(PROPOSED, "w") as f:
            f.write("#token\tcount\tsuggested_axis\n")
            for tok, n in proposed_tokens.most_common(500):
                if n < 3: continue
                axis = "category.tsv" if tok in SUPER else "form.tsv"
                f.write(f"{tok}\t{n}\t{axis}\n")
        print(f"  wrote {PROPOSED} (top tokens, count≥3)")

    # final summary
    high_conf = sum(1 for r in rows if float(r.get("confidence") or 0) >= 0.5)
    gaps_left = sum(1 for r in rows if r.get("gap_flag") == "True")
    print(f"\nfinal:  high_conf {high_conf}/{len(rows)} ({100*high_conf/len(rows):.1f}%)")
    print(f"        unmapped gaps {gaps_left} ({100*gaps_left/len(rows):.1f}%)")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", action="store_true")
    p.add_argument("--min-members", type=int, default=3)
    a = p.parse_args()
    if a.run: run(a.min_members)
    else: p.print_help()

if __name__ == "__main__":
    main()
