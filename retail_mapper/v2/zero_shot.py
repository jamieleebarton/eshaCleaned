#!/usr/bin/env python3
"""Stage B4 + B5 — zero-shot classification with DeBERTa-v3-zeroshot-v2.0.

Use modes:
  --probe       : run on a tiny set of hard examples; prints results.
                  Use this to decide whether full-corpus zero-shot is worth it.
  --run         : run on every product in parsed_titles_enriched.csv (slow).
  --run-subset SUBSET_PARQUET
                : run only on the fdc_ids listed in the given parquet
                  (used by reconcile to selectively classify the
                   low-confidence subset).
"""
from __future__ import annotations
import argparse, csv, os, sys, time, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
RM   = REPO / "retail_mapper"
V2   = RM / "v2"
CACHE = V2 / ".cache"; CACHE.mkdir(parents=True, exist_ok=True)
INPUT_CSV = RM / "parsed_titles_enriched.csv"
OUT_PARQUET = CACHE / "zero_shot.parquet"

# small first; use the LARGE one only if probe shows it's worth it
MODEL_NAME = os.environ.get("ZS_MODEL", "MoritzLaurer/deberta-v3-large-zeroshot-v2.0")

# Stage 1: broad supercategory labels (10–20 covering the corpus)
SUPERCATS = [
    "plant-based milk",
    "dairy milk",
    "yogurt",
    "ice cream and frozen dessert",
    "cheese",
    "egg or eggnog",
    "mayonnaise or aioli",
    "salad dressing",
    "condiment, sauce, or spread",
    "honey or syrup or sweetener",
    "coffee or tea",
    "soda or juice or beverage",
    "cereal or granola or oats",
    "snack or chip or cracker",
    "cookie or biscuit",
    "candy or chocolate bar",
    "bread or roll or bun",
    "pasta or noodle",
    "frozen meal or meal kit",
    "soup or stew",
    "meat or seafood (raw, deli, or prepared)",
    "produce (fruit or vegetable, fresh or frozen)",
    "beans, legumes, or canned beans",
    "nuts, seeds, or nut butter",
    "baking ingredient",
    "spice, seasoning, or herb",
    "supplement, protein bar, or shake",
    "baby or toddler food",
    "pet food",
    "alcoholic beverage",
]

# Stage 2: leaf candidates per supercategory.  Used only for top-1 super.
LEAVES = {
    "plant-based milk": [
        "almond milk plain",
        "almond milk vanilla",
        "almond milk chocolate",
        "almond milk unsweetened",
        "almond milk pumpkin spice",
        "almond milk salted caramel",
        "oat milk plain",
        "oat milk vanilla",
        "oat milk chocolate",
        "soy milk plain",
        "soy milk vanilla",
        "soy milk chocolate",
        "coconut milk beverage",
        "cashew milk",
        "rice milk",
        "almond and coconut milk blend",
        "almond eggnog",
        "oat eggnog",
        "soy eggnog",
        "coconut eggnog",
    ],
    "mayonnaise or aioli": [
        "plain mayonnaise",
        "real mayonnaise",
        "light mayonnaise",
        "olive oil mayonnaise",
        "vegan mayonnaise",
        "chipotle mayonnaise",
        "garlic aioli",
        "lime mayonnaise",
        "wasabi mayonnaise",
        "horseradish mayonnaise",
        "sriracha mayonnaise",
        "mango mayonnaise",
    ],
    "salad dressing": [
        "ranch dressing",
        "chipotle ranch dressing",
        "italian dressing",
        "caesar dressing",
        "balsamic vinaigrette",
        "honey mustard dressing",
        "blue cheese dressing",
        "thousand island dressing",
        "french dressing",
        "asian dressing",
    ],
    "yogurt": [
        "greek yogurt plain",
        "greek yogurt vanilla",
        "greek yogurt strawberry",
        "regular yogurt plain",
        "regular yogurt vanilla",
        "regular yogurt fruit on the bottom",
        "kefir",
        "yogurt drink",
        "almond milk yogurt alternative",
        "coconut yogurt alternative",
    ],
    "egg or eggnog": [
        "eggnog dairy",
        "eggnog low fat",
        "almond eggnog",
        "oat eggnog",
        "soy eggnog",
        "coconut eggnog",
        "egg substitute",
        "liquid egg whites",
    ],
    "honey or syrup or sweetener": [
        "honey plain",
        "hot honey",
        "maple syrup",
        "agave",
        "molasses",
        "corn syrup",
        "brown sugar",
        "powdered sugar",
    ],
    "condiment, sauce, or spread": [
        "ketchup",
        "mustard",
        "barbecue sauce",
        "hot sauce",
        "salsa",
        "guacamole",
        "hummus",
        "pesto",
        "tomato sauce",
        "soy sauce",
        "teriyaki sauce",
    ],
    "frozen meal or meal kit": [
        "taco meal kit",
        "burrito meal kit",
        "pasta meal kit",
        "frozen pizza",
        "frozen entree",
        "frozen burrito",
        "frozen taco",
    ],
    "ice cream and frozen dessert": [
        "vanilla ice cream",
        "chocolate ice cream",
        "strawberry ice cream",
        "chunky monkey ice cream",
        "cookie dough ice cream",
        "non-dairy ice cream",
        "sorbet",
        "frozen yogurt",
        "ice cream sandwich",
        "ice cream bar",
    ],
    "cheese": [
        "cheddar cheese",
        "mozzarella cheese",
        "gouda cheese",
        "hot honey gouda cheese",
        "swiss cheese",
        "cream cheese",
        "feta cheese",
        "parmesan cheese",
        "blue cheese",
    ],
}

# Probe set
HARD = [
    ("UNSWEETENED CHOCOLATE ALMONDMILK, UNSWEETENED CHOCOLATE", "almond milk chocolate"),
    ("HINT OF PUMPKIN SPICE FLAVORED ALMONDMILK", "almond milk pumpkin spice"),
    ("ORIGINAL ALMOND BEVERAGE, ORIGINAL", "almond milk plain"),
    ("CHIPOTLE MAYO STYLE SANDWICH SPREAD, CHIPOTLE", "chipotle mayonnaise"),
    ("Chipotle Aioli", "garlic aioli"),
    ("AVOCADO OIL WITH LIME MAYONNAISE DRESSING", "lime mayonnaise"),
    ("ALMOND NOG NON-DAIRY BEVERAGE, ALMOND NOG", "almond eggnog"),
    ("OAT NOG FLAVORED OATMILK DRINK", "oat eggnog"),
    ("PUMPKIN SPICE DAIRY FREE ALMONDMILK CREAMER", "almond milk pumpkin spice"),
    ("HOT HONEY GOUDA CHEESE, HOT HONEY GOUDA", "hot honey gouda cheese"),
    ("Bush's Hot Honey Grillin' Beans 55oz", "beans, legumes, or canned beans"),
    ("BEYOND MEAT TACOS WITH SMOKY CHIPOTLE-LIME MAYO MEAL KIT", "taco meal kit"),
    ("VANILLA ALMONDMILK YOGURT ALTERNATIVE, VANILLA", "almond milk yogurt alternative"),
    ("CHUNKY MONKEY ICE CREAM, CHOCOLATE FUDGE CHUNKS WITH WALNUTS", "chunky monkey ice cream"),
]

_CLF = None
def _clf():
    global _CLF
    if _CLF is not None: return _CLF
    from transformers import pipeline
    import torch
    device = -1
    if torch.backends.mps.is_available(): device = "mps"
    elif torch.cuda.is_available(): device = 0
    print(f"  loading {MODEL_NAME} on device={device}")
    _CLF = pipeline("zero-shot-classification", model=MODEL_NAME, device=device)
    return _CLF

def classify_super(texts, batch=8):
    """Stage 1: classify every text into one of SUPERCATS."""
    clf = _clf()
    out = clf(texts, candidate_labels=SUPERCATS, batch_size=batch, multi_label=False)
    if isinstance(out, dict): out = [out]
    return [(o["labels"][0], float(o["scores"][0])) for o in out]

def classify_leaf(text, supercat):
    """Stage 2: classify into leaves under that super, if we have any defined."""
    leaves = LEAVES.get(supercat)
    if not leaves: return ("", 0.0)
    o = _clf()(text, candidate_labels=leaves, multi_label=False)
    return (o["labels"][0], float(o["scores"][0]))

# --- modes -------------------------------------------------------------------

def probe():
    print("loading model...")
    _clf()
    print("---")
    titles = [t for t, _ in HARD]
    expected = [e for _, e in HARD]
    t0 = time.time()
    supers = classify_super(titles)
    print(f"  stage1 (supercategory) done in {time.time()-t0:.1f}s")
    leaves = []
    t0 = time.time()
    for tt, (s, sc) in zip(titles, supers):
        lf, lc = classify_leaf(tt, s)
        leaves.append((lf, lc))
    print(f"  stage2 (leaf) done in {time.time()-t0:.1f}s")
    print()
    correct_super = correct_leaf = 0
    for tt, exp, (s, sc), (lf, lc) in zip(titles, expected, supers, leaves):
        leaf_ok = "✓" if lf == exp else "✗"
        super_ok = exp.split(",")[0].split(" or ")[0].split(" plain")[0]  # crude
        print(f"{tt[:55]:55s}")
        print(f"   super: {s!r}  ({sc:.3f})")
        print(f"   leaf : {lf!r}  ({lc:.3f})   expected: {exp!r}   {leaf_ok}")
        if lf == exp: correct_leaf += 1
    print(f"\nleaf accuracy: {correct_leaf}/{len(HARD)}")

def run(limit: int | None = None, subset: str | None = None):
    """Full-corpus zero-shot. SLOW."""
    import pyarrow as pa, pyarrow.parquet as pq
    csv.field_size_limit(sys.maxsize)
    titles, fdcs = [], []
    keep = None
    if subset:
        tbl = pq.read_table(subset)
        keep = set(str(x) for x in tbl["fdc_id"].to_pylist())
        print(f"  restricting to subset of {len(keep)} fdc_ids")
    with open(INPUT_CSV, errors='replace') as f:
        for r in csv.DictReader(f):
            fdc = r.get("fdc_id") or ""
            if keep is not None and fdc not in keep: continue
            titles.append(r.get("product_description") or "")
            fdcs.append(fdc)
            if limit and len(titles) >= limit: break
    print(f"  classifying {len(titles)} products")
    _clf()
    BATCH = 8
    rows = []
    t0 = time.time()
    for i in range(0, len(titles), BATCH):
        b = titles[i:i+BATCH]
        sup = classify_super(b, batch=len(b))
        for j, (s, sc) in enumerate(sup):
            tt = titles[i+j]
            lf, lc = classify_leaf(tt, s)
            rows.append({
                "fdc_id":         fdcs[i+j],
                "title":          tt,
                "zs_super":       s,
                "zs_super_score": sc,
                "zs_leaf":        lf,
                "zs_leaf_score":  lc,
            })
        if (i + BATCH) % 200 < BATCH:
            el = time.time() - t0
            done = i + BATCH
            eta = (len(titles) - done) / max(1, done/el) / 60
            print(f"  {done:>6}/{len(titles)}  ({el/60:.1f}m, eta {eta:.0f}m)", flush=True)
    el = time.time() - t0
    print(f"  done {len(rows)} ({el/60:.1f}m)")
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, OUT_PARQUET, compression="zstd")
    print(f"wrote {OUT_PARQUET}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--probe", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--subset", type=str, default=None)
    a = p.parse_args()
    if a.probe: probe()
    elif a.run: run(a.limit, a.subset)
    else: p.print_help()

if __name__ == "__main__":
    main()
