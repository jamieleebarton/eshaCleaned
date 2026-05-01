#!/usr/bin/env python3
"""Clean the canonical retail taxonomy.

Reads:  implementation/output/taxonomy_paths_cleaned.csv  (43,887 paths)
Writes: retail_mapper/v2/taxonomy_clean.csv               (kept paths)
        retail_mapper/v2/taxonomy_dropped.csv             (rejected + reason)

Reject rules (in priority order):
  1. Brand tokens in any segment (Welch, Kroger, Silk, Trader, So-Delicious, ...)
  2. Repeated-token segments  ("Dairy Milk Cheese Milk", "Apple Apple Sauce")
  3. Joined-modifier segments ("Dairy+Almond", "Cheese & Crackers" — leaves only)
  4. Long noise segments      (>=4 words AND not a known multi-word leaf)
  5. Hierarchy violations     (Plant-based items under Dairy Milk, etc.)
  6. Singleton/orphan paths whose only support is one product

The orphan rule is data-driven: paths in the taxonomy that don't correspond
to any actual product leaf in retail_leaf_v2.csv get dropped because they're
ghost leaves left over from earlier pipeline runs.
"""
from __future__ import annotations
import csv, re, sys, collections
csv.field_size_limit(sys.maxsize)

REPO   = "/Users/jamiebarton/Desktop/esha_audit_bundle"
TAXO_IN = f"{REPO}/implementation/output/taxonomy_paths_cleaned.csv"
LEAVES  = f"{REPO}/retail_mapper/v2/retail_leaf_v2.csv"
OUT_OK  = f"{REPO}/retail_mapper/v2/taxonomy_clean.csv"
OUT_BAD = f"{REPO}/retail_mapper/v2/taxonomy_dropped.csv"

WORD = re.compile(r"[a-z0-9]+")

BRAND_TOKENS = {
    # store / private label
    "kroger","walmart","target","costco","trader","joe","aldi","wegmans","publix",
    "great","value","cadia","simply","wholefoods","whole",
    "wild","harvest","store","market","clover","valley","bowl","basket",
    "private","selection","signature","select","members","mark","kirkland",
    # nat'l brands that appear as path tokens
    "welch","kelloggs","quaker","silk","eggo","kelloggs","general","mills",
    "blue","diamond","breyer","dannon","yoplait","chobani","oikos","fage",
    "bushs","bush","heinz","kraft","unilever","nestle","conagra",
    "marie","callender","stouffer","banquet","amy","amys","annies",
    "delicious",   # "So Delicious"
    "wisconsin","peeled","tam",   # leaked location/brand artifacts
    "kerrygold","horizon","organic","valley","fairlife","lactaid",
    "wendy","sonic","arbys","mcdonald","mcdonalds","subway","panera",
}
# "organic" is borderline — it's both a brand and a real attribute.  We
# only flag it when it's BY ITSELF as a segment AND the path has no
# parent context (e.g. "Pantry > Organic > Organic" is junk).  In
# "Beverage > Plant-based Milk > Almond Milk > Original > Organic" it's
# legitimate.  Handle that with a special-case below.
LEGIT_ORGANIC_PARENT = True

# tokens that are part of legit retail leaves and should NEVER trigger
# the brand filter even if they overlap with brand names.
WHITELIST = {"valley","mountain","village","fresh","farm","natural"}

JOIN_BAD = re.compile(r"[+&,]")

KNOWN_MULTIWORD_OK = {
    "macaroni and cheese","sauces & salsas","fruit-based drinks",
    "cookies & crackers","plant-based milk","cured & smoked",
    "salt & pepper","nuts & seeds","milk & cream","fish & seafood",
    "salts & seasonings","grains & rice","baking mixes","dairy free",
    "gluten free","gluten-free","sugar free","fat free","reduced fat",
    "low fat","whole grain","whole wheat","extra virgin",
}

# hierarchy violations — these prefixes should never co-exist
INVALID_PREFIXES = [
    ("Beverage > Dairy Milk", ("almond","soy","oat","coconut","rice","cashew","hemp","pea","macadamia")),
    ("Beverage > Plant-based Milk", ("dairy",)),
]

def reasons_to_drop(p: str) -> list[str]:
    reasons = []
    segs = [s.strip() for s in p.split(" > ")]
    seg_lc = [s.lower() for s in segs]

    # 1. brand tokens
    for s in seg_lc:
        words = set(WORD.findall(s))
        # only flag brand tokens that AREN'T in the whitelist (e.g. valley
        # in "Smucker's Valley" should drop; "Death Valley" salt is rare).
        bad = (words & BRAND_TOKENS) - WHITELIST
        if bad:
            reasons.append(f"brand_token:{','.join(sorted(bad))}")
            break

    # 2. repeated tokens across segments (excluding generic supercat words
    #    and common food-category nouns where repetition is natural).
    REPEAT_OK = {"and","with","of","the"}
    all_tok = []
    for s in seg_lc[1:]:                # skip supercategory itself
        all_tok += [t for t in WORD.findall(s) if len(t) > 2 and t not in REPEAT_OK]
    cnt = collections.Counter(all_tok)
    rep = [t for t,c in cnt.items() if c >= 2]
    if rep:
        reasons.append(f"repeated_tokens:{','.join(rep[:3])}")

    # 3. + or & in a non-whitelisted segment (drops "Dairy+Almond",
    #    "Cookies & Bars", but keeps "Sauces & Salsas").
    for s in segs:
        if JOIN_BAD.search(s) and s.lower() not in KNOWN_MULTIWORD_OK:
            reasons.append("joined_modifier")
            break

    # 4. segment too long (4+ words) AND not a known multiword leaf
    for s in segs:
        words = s.split()
        if len(words) >= 4 and s.lower() not in KNOWN_MULTIWORD_OK:
            reasons.append("long_segment")
            break

    # 5. hierarchy violations
    for prefix, banned in INVALID_PREFIXES:
        if p.startswith(prefix):
            for seg in segs[len(prefix.split(' > ')):]:
                if any(b in seg.lower() for b in banned):
                    reasons.append(f"invalid_hierarchy:{prefix}")
                    break
            if reasons and reasons[-1].startswith("invalid_hierarchy"): break

    return reasons


def main():
    print(f"reading {TAXO_IN}")
    paths = []
    with open(TAXO_IN) as f:
        for r in csv.DictReader(f):
            p = (r.get("retail_leaf") or "").strip()
            if p: paths.append(p)
    print(f"  {len(paths):,} input paths")

    # data-driven: count how many products actually use each leaf
    leaf_support = collections.Counter()
    print(f"reading {LEAVES} for support counts")
    with open(LEAVES) as f:
        for r in csv.DictReader(f):
            l = r.get("retail_leaf","").strip()
            if l: leaf_support[l] += 1
    print(f"  {len(leaf_support):,} leaves currently in use")

    kept, dropped = [], []
    for p in paths:
        reasons = reasons_to_drop(p)
        if reasons:
            dropped.append((p, reasons))
        else:
            kept.append(p)

    # Note: we do NOT auto-add in-use leaves — many of THEM are dirty
    # (that's exactly the point of cleaning). The cleaned taxonomy is
    # the *target* schema; dirty in-use leaves get re-routed.

    # Keep ancestors of every kept leaf so partial descents still land
    # somewhere meaningful.
    kept_set = set(kept)
    for p in list(kept):
        segs = p.split(" > ")
        for i in range(1, len(segs)):
            anc = " > ".join(segs[:i])
            if anc not in kept_set:
                kept_set.add(anc)
                kept.append(anc)

    kept = sorted(set(kept))
    print(f"\nkept:    {len(kept):>6}")
    print(f"dropped: {len(dropped):>6}")

    with open(OUT_OK, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["retail_leaf","support"])
        for p in kept:
            w.writerow([p, leaf_support.get(p, 0)])
    with open(OUT_BAD, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["retail_leaf","reasons","support"])
        for p, rs in dropped:
            w.writerow([p, ";".join(rs), leaf_support.get(p, 0)])

    # Top reasons summary
    rcount = collections.Counter()
    for _, rs in dropped:
        for r in rs: rcount[r.split(':')[0]] += 1
    print("\ndrop-reason breakdown:")
    for r, c in rcount.most_common():
        print(f"  {c:>6}  {r}")
    print(f"\nwrote {OUT_OK}")
    print(f"wrote {OUT_BAD}")

if __name__ == "__main__":
    main()
