#!/usr/bin/env python3
"""Deep recipe inspector — per-line verdict tagger.

For each recipe in the inspection set, walks every ingredient line and
tags it with one of these verdicts:

  gram_bug       — our_grams vs hestia_grams differ by >2x; our value
                    is implausible relative to recipe text
  identity_bug   — our_canonical_path family ≠ hestia_fndds family
                    (the shrimp→olive oil class of bug)
  form_bug       — picked SKU is wrong form for what recipe asks
                    (dry packet for liquid recipe; mix for sauce; etc.)
  multipack_bug  — recipe wants single can/jar but SKU is N-pack
  coverage_gap   — our_sku == "(none)" — no SKU at all
  synonym_gap    — our path is unknown / tiny pool but Hestia's is rich
                    (mung dal, brand names, etc.)
  brand_proper   — ingredient text starts with a brand name
                    (Grand Marnier, Maggi, etc.)
  accept         — line looks fine; Hestia probably wrong if anything

Inspection set:
  1. ALL recipes flagged OFF_2X_HIGH in audit_cal_reconstruction_v3.csv
  2. Sample of 500 recipes flagged OFF_2X_LOW
  3. ALL 258 picked recipes from /tmp/multi_week_ours_12w_round2.json

Outputs:
  recipe_pricing/deep_inspector_lines.csv     — one row per (recipe, line) with verdict
  recipe_pricing/deep_inspector_rollup.csv    — verdict counts + top patterns
"""
from __future__ import annotations
import csv, json, random, sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
LINES_CSV = ROOT / "planner" / "data" / "recipe_line_comparison_FULL_v6.csv"
A3_CSV = ROOT / "recipe_pricing" / "audit_cal_reconstruction_v3.csv"
PICKED_JSON = Path("/tmp/multi_week_ours_12w_round2.json")
OUT_LINES = ROOT / "recipe_pricing" / "deep_inspector_lines.csv"
OUT_ROLLUP = ROOT / "recipe_pricing" / "deep_inspector_rollup.csv"

random.seed(42)

# Form-mismatch tokens
DRY_MIX_TOKENS = (" mix", " packet", " sachet", " powder", "instant ",
                   "seasoning packet", "bouillon", "stock cube",
                   " base", " granule", " granules")
LIQUID_RECIPE_TOKENS = ("gravy", "broth", "stock", "sauce", "dressing",
                         "soup", "syrup", "milk", "cream", "juice",
                         "wine", "vinegar", "oil")
# Recipe-text proper-noun heuristic: brand if first token is capitalized
# AND not a known generic
GENERIC_LEADERS = {"Salt", "Pepper", "Sugar", "Flour", "Water", "Oil", "Butter",
                    "Cream", "Milk", "Eggs", "Egg", "Garlic", "Onion", "Onions",
                    "Lemon", "Lime", "Parsley", "Cilantro", "Basil", "Mint",
                    "Olive", "Vegetable", "Soy", "Worcestershire", "Tabasco",
                    "Bay", "Black", "White", "Red", "Yellow", "Green", "Brown",
                    # Cooking adjectives (not brands)
                    "Toasted", "Fresh", "Cooked", "Roasted", "Grilled", "Sliced",
                    "Chopped", "Diced", "Minced", "Ground", "Whole", "Frozen",
                    "Canned", "Dried", "Pickled", "Smoked", "Boiled", "Steamed",
                    "Baked", "Fried", "Raw", "Mashed", "Crushed", "Shredded",
                    "Grated", "Peeled", "Trimmed", "Halved", "Quartered",
                    "Hot", "Cold", "Warm", "Soft", "Hard", "Firm", "Ripe", "Unripe",
                    "Light", "Dark", "Heavy", "Plain", "Sweet", "Sour", "Spicy",
                    "Large", "Medium", "Small", "Mini", "Extra", "Super",
                    "Italian", "Mexican", "Asian", "American", "French", "Greek",
                    "Spanish", "Indian", "Thai", "Chinese", "Japanese", "Korean",
                    "Optional", "Additional", "About", "Approximately", "Maybe"}


def is_dry_mix_form_bug(recipe_text: str, sku_name: str, our_grams: float,
                          our_pkg_g: float) -> bool:
    """Recipe asks for liquid (broth/sauce/etc) but SKU is a dry packet."""
    rl = (recipe_text or "").lower()
    sl = (sku_name or "").lower()
    # Recipe text must contain a liquid-recipe noun
    if not any(t in rl for t in LIQUID_RECIPE_TOKENS):
        return False
    # SKU name must contain a dry-mix token
    if not any(t in sl for t in DRY_MIX_TOKENS):
        return False
    # And the recipe needs more grams than the SKU pack delivers
    if our_grams >= 100 and our_pkg_g and our_pkg_g < 50:
        return True
    return False


def is_identity_bug(our_path: str, hes_fndds: str, ingredient_text: str) -> bool:
    """Our path's top-level category disagrees with hestia_fndds family,
    AND the recipe text doesn't contain the path's leaf word (a hard mismatch).

    e.g., recipe says "shrimp" but our path is "Pantry > Oil > Olive Oil" —
    the leaf "olive oil" doesn't appear in "shrimp" → real identity bug.
    Whereas "tomato juice" with our path "Beverage > Juice > Tomato Juice"
    has "tomato" + "juice" both in the recipe text → not a bug, just a
    categorization style difference between us & Hestia.
    """
    if not our_path or not hes_fndds or len(hes_fndds) < 2: return False
    fam = hes_fndds[:2]
    top = (our_path.split(" > ")[0] if our_path else "").lower()
    leaf = (our_path.split(" > ")[-1] if our_path else "").lower()
    text = (ingredient_text or "").lower()

    # Soft check: does any leaf token appear in recipe text?
    leaf_tokens = [t for t in leaf.split() if len(t) > 2]
    leaf_in_text = any(t in text for t in leaf_tokens) if leaf_tokens else False
    if leaf_in_text:
        return False  # path leaf is named in recipe → no identity bug

    # Same logic as before, but only fire when leaf-token is missing from text
    if fam in ("11","12","13","14"):
        return "dairy" not in top
    if fam in ("21","22","23","24","25","26","27","28"):
        return ("meat" not in top and "seafood" not in top)
    if fam in ("31","32","33","34"):
        return "dairy" not in top and "egg" not in top
    if fam in ("41","42","43"):
        return ("pantry" not in top and "snack" not in top
                and "produce" not in top)
    if fam in ("50","51","52","53","54","55","56","57","58","59"):
        return "pantry" not in top and "bakery" not in top
    if fam in ("61","62","63","64","65","66","67"):
        return ("produce" not in top and "frozen" not in top
                and "snack" not in top and "pantry" not in top)
    if fam in ("71","72","73","74","75","76","77","78"):
        return ("produce" not in top and "frozen" not in top
                and "pantry" not in top)
    if fam in ("81","82","83","89"):
        return ("pantry" not in top and "dairy" not in top)
    return False


def is_pool_poisoned(our_path: str, our_sku: str, our_pool: int) -> bool:
    """Pool is tiny (<=3 SKUs) AND the picked SKU's name doesn't contain any
    leaf token of the canonical_path. e.g., "Dairy > Mozzarella" pool=1 with
    only SKU = "Smoked Gouda" → bridge classification poisoned the pool."""
    if not our_path or not our_sku or our_pool > 3 or our_pool < 1: return False
    leaf = our_path.split(" > ")[-1].lower()
    leaf_tokens = [t for t in leaf.split() if len(t) > 2]
    if not leaf_tokens: return False
    sku_lower = our_sku.lower()
    return not any(t in sku_lower for t in leaf_tokens)


def is_brand_proper(text: str) -> bool:
    """Heuristic: first token is capitalized and not generic."""
    if not text: return False
    first = text.lstrip().split(" ")[0].rstrip(",.!?")
    if not first: return False
    if not first[:1].isupper(): return False
    if first in GENERIC_LEADERS: return False
    # All-caps short tokens probably aren't brands
    if first.isupper() and len(first) <= 3: return False
    # Check if any common cooking word follows immediately — 'Italian seasoning' ≠ brand
    return True


def classify_line(row: dict) -> tuple[str, str]:
    """Return (verdict, evidence)."""
    try: og = float(row.get("our_grams") or 0)
    except: og = 0
    try: hg = float(row.get("hestia_grams") or 0)
    except: hg = 0
    try: ratio = float(row.get("gram_ratio") or 0)
    except: ratio = 0
    try: opg = float(row.get("our_pkg_g") or 0)
    except: opg = 0
    our_sku = row.get("our_sku","") or ""
    our_path = row.get("our_canonical_path","") or ""
    text = row.get("ingredient_text","") or ""
    hes_fndds = row.get("hestia_fndds","") or ""
    hes_sku = row.get("hestia_sku","") or ""

    # 1. coverage_gap — no SKU
    if our_sku in ("(none)", ""):
        if hes_sku and hes_sku != "(none)":
            return "coverage_gap", f"hes_has_sku={hes_sku[:40]}"
        return "coverage_gap", "no_sku_either_side"

    # 2. identity_bug — top-level category mismatch (skip when no path or no fndds)
    if our_path and hes_fndds and hes_fndds != "0":
        if is_identity_bug(our_path, hes_fndds, text):
            return "identity_bug", f"our_path={our_path[:40]} vs hes_fam={hes_fndds[:2]} text='{text[:30]}'"

    # 2b. pool_poisoned — tiny pool with no leaf-matching SKU (e.g.
    # mozzarella path with only smoked gouda SKU)
    try: pool = int(row.get("our_pool") or 0)
    except: pool = 0
    if is_pool_poisoned(our_path, our_sku, pool):
        return "pool_poisoned", f"path={our_path[:40]} sku={our_sku[:40]} pool={pool}"

    # 3. gram_diverge — large gram disagreement; we don't know who's right
    # but flag for manual review. Sub-cases:
    #   - our_implausible: our_grams > 3kg for a single line (likely bug)
    #   - hes_implausible: hes_grams > 3kg or our < 0.2× hes (likely Hestia bug)
    if og > 0 and hg > 0:
        if og > 3000 and ratio > 5:
            return "gram_bug_ours", f"our={og:.0f}g hes={hg:.0f}g (our likely wrong)"
        if hg > 3000 and ratio < 0.2:
            return "gram_bug_hes", f"our={og:.0f}g hes={hg:.0f}g (hes likely wrong)"
        if ratio > 5.0 or (0 < ratio < 0.2):
            return "gram_diverge", f"our={og:.0f}g hes={hg:.0f}g ratio={ratio:.2f}"

    # 4. form_bug — dry mix for liquid recipe
    if is_dry_mix_form_bug(text, our_sku, og, opg):
        return "form_bug", f"sku={our_sku[:40]} pkg={opg:.0f}g for {og:.0f}g need"

    # 5. multipack_bug — SKU name suggests N-pack but recipe wants 1
    sl = our_sku.lower()
    if any(t in sl for t in (" 12 pack", " 24 pack", " case of ", " (12 ct", " (24 ct")):
        # Check whether recipe wanted single
        if any(t in (text or "").lower() for t in ("1 can", "1 jar", "1 bottle", "one can", "single can")):
            return "multipack_bug", f"sku={our_sku[:40]}"

    # 6. synonym_gap — our path is generic / pool tiny but Hestia has a real fndds
    if hes_fndds and hes_fndds != "0" and pool > 0 and pool <= 3:
        return "synonym_gap", f"our_path={our_path[:40]} pool={pool}"

    # 7. brand_proper
    if is_brand_proper(text):
        return "brand_proper", f"text={text[:40]}"

    # 8. accept
    return "accept", ""


def main():
    # Load OFF_2X recipe ID sets
    high_rids: list[str] = []
    low_rids: list[str] = []
    print("loading A3 v3 OFF_2X recipes…", file=sys.stderr)
    with A3_CSV.open() as f:
        r = csv.DictReader(f)
        for row in r:
            flags = row.get("flags","")
            rid = row.get("recipe_id","")
            if "OFF_2X_HIGH" in flags: high_rids.append(rid)
            elif "OFF_2X_LOW" in flags: low_rids.append(rid)
    print(f"  OFF_2X_HIGH: {len(high_rids):,}", file=sys.stderr)
    print(f"  OFF_2X_LOW:  {len(low_rids):,}", file=sys.stderr)

    # Sample OFF_2X_LOW
    sampled_low = random.sample(low_rids, min(500, len(low_rids)))

    # Load picked rids
    picked_rids: list[str] = []
    if PICKED_JSON.exists():
        d = json.loads(PICKED_JSON.read_text())
        seen: set = set()
        for w in d.get("weeks", []):
            for x in (w.get("recipe_ids") or []):
                s = str(x)
                if s not in seen:
                    seen.add(s); picked_rids.append(s)
        print(f"  picked: {len(picked_rids):,}", file=sys.stderr)

    target_rids = set(high_rids) | set(sampled_low) | set(picked_rids)
    print(f"  total target recipes: {len(target_rids):,}", file=sys.stderr)

    # Walk FULL_v6, emit verdicts for lines belonging to target_rids
    print("\nwalking FULL_v6 line CSV…", file=sys.stderr)
    out_rows = []
    rows_seen = 0; rows_in = 0
    set_label_high = set(high_rids)
    set_label_low = set(sampled_low)
    set_label_picked = set(picked_rids)
    with LINES_CSV.open() as f:
        r = csv.DictReader(f)
        for row in r:
            rows_seen += 1
            if rows_seen % 500_000 == 0:
                print(f"  {rows_seen:,} lines processed", file=sys.stderr)
            rid = row.get("recipe_id","")
            if rid not in target_rids: continue
            rows_in += 1
            verdict, evidence = classify_line(row)
            labels = []
            if rid in set_label_high:   labels.append("OFF_2X_HIGH")
            if rid in set_label_low:    labels.append("OFF_2X_LOW")
            if rid in set_label_picked: labels.append("PICKED")
            out_rows.append({
                "recipe_id": rid,
                "recipe_name": row.get("recipe_name","")[:50],
                "line_idx": row.get("line_idx",""),
                "labels": "|".join(labels),
                "ingredient_text": row.get("ingredient_text","")[:80],
                "our_grams": row.get("our_grams",""),
                "hestia_grams": row.get("hestia_grams",""),
                "gram_ratio": row.get("gram_ratio",""),
                "our_canonical_path": row.get("our_canonical_path","")[:50],
                "hestia_fndds": row.get("hestia_fndds",""),
                "fndds_desc": row.get("fndds_desc","")[:30],
                "our_sku": (row.get("our_sku","") or "")[:50],
                "our_pkg_g": row.get("our_pkg_g",""),
                "our_pool": row.get("our_pool",""),
                "verdict": verdict,
                "evidence": evidence,
            })

    print(f"\n{rows_in:,} lines emitted across {len(target_rids):,} recipes",
          file=sys.stderr)

    OUT_LINES.parent.mkdir(parents=True, exist_ok=True)
    if out_rows:
        with OUT_LINES.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            for r in out_rows: w.writerow(r)
    print(f"→ {OUT_LINES}", file=sys.stderr)

    # Rollup: count per (verdict, label group)
    by_verdict: Counter = Counter()
    by_verdict_picked: Counter = Counter()
    by_path_per_verdict: dict[str, Counter] = defaultdict(Counter)
    samples_per_verdict: dict[str, list] = defaultdict(list)
    for row in out_rows:
        v = row["verdict"]
        by_verdict[v] += 1
        if "PICKED" in row["labels"]:
            by_verdict_picked[v] += 1
        if v != "accept":
            path = row["our_canonical_path"]
            by_path_per_verdict[v][path] += 1
            if len(samples_per_verdict[v]) < 8:
                samples_per_verdict[v].append(
                    f"r{row['recipe_id']} '{row['ingredient_text'][:40]}' → {row['evidence']}")

    print(f"\nVerdict distribution:", file=sys.stderr)
    for v, n in by_verdict.most_common():
        np = by_verdict_picked.get(v, 0)
        print(f"  {v:<16}  {n:>6,}  (in picked: {np:>4,})", file=sys.stderr)

    rollup_rows = []
    for v in by_verdict:
        if v == "accept": continue
        for path, n in by_path_per_verdict[v].most_common(5):
            rollup_rows.append({
                "verdict": v,
                "canonical_path": path,
                "n_lines": n,
                "sample": samples_per_verdict[v][0] if samples_per_verdict[v] else "",
            })
    if rollup_rows:
        with OUT_ROLLUP.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rollup_rows[0].keys()))
            w.writeheader()
            for r in rollup_rows: w.writerow(r)
    print(f"→ {OUT_ROLLUP}  ({len(rollup_rows)} rollup rows)", file=sys.stderr)


if __name__ == "__main__":
    main()
