#!/usr/bin/env python3
"""V3 — Recipe cost from OUR priced_products_tagged.db (HTC-anchored).

No more Hestia food_packages_final.db. We use:
  recipe_pricing/data/priced_products_tagged.db
    63,670 priced products from our walmart/kroger pulls
    + sr28_fdc_id, fndds_code (already there)
    + htc_code, htc_group, htc_confidence (just added by tag_priced_products_with_htc.py)
    + quality tier + non_food_drop flag

Match logic per recipe ingredient:
  1. Recipe ingredient → HTC code + SR-28 fdc + product noun tokens
  2. Filter priced_products to:
       - same htc_group (Dairy/Spices/etc must match)
       - non_food_drop = 0 (drop hygiene products / e.g. e.l.f. lipstick)
       - quality >= chosen tier (1 = best, 3 = noisier)
       - name tokens overlap with recipe ingredient
       - bonus if sr28_fdc_id matches the recipe's SR-28 fdc
  3. Pick cheapest cents-per-gram product that survives
  4. Full-package: n_pkgs = ceil(grams_needed / package_grams), cost = n × price
"""
from __future__ import annotations

import csv
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
PRICED_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
HERE = Path(__file__).resolve().parent
LINES = HERE / "output" / "recipes_unified.csv"
ING_TAGS = HERE / "output" / "recipe_ingredient_htc_tagged.csv"
ING_SR = HERE / "output" / "ingredient_to_sr28.csv"

WS = re.compile(r"[^a-z0-9 ]+")
STOP = {"the","of","and","with","a","an","to","in","fresh","frozen","raw",
        "ground","whole","large","medium","small","extra","lean","low","fat",
        "free","organic","natural","chopped","diced","minced","sliced",
        "boneless","skinless","grade","brand"}


def toks(s: str) -> set[str]:
    s = WS.sub(" ", (s or "").lower())
    return {t for t in s.split() if len(t) >= 2 and t not in STOP}


def load_priced_by_group() -> dict[str, list[dict]]:
    """Group priced products by htc_group for fast filtering. Uses the
    rebuilt priced_products_v2.db (Walmart-direct + Kroger only, no
    marketplace junk)."""
    con = sqlite3.connect(str(PRICED_DB))
    rows = con.execute("""
        SELECT source, upc, name, brand, grams, cents,
               htc_code, htc_group, marketplace, available
        FROM priced_products
        WHERE marketplace = 0
          AND available = 1
          AND grams > 0 AND cents > 0
          AND htc_group IS NOT NULL
          AND htc_group NOT IN ('0','N')
    """).fetchall()
    out: dict[str, list[dict]] = defaultdict(list)
    for src, upc, name, brand, g, c, hcode, hgrp, mp, avail in rows:
        out[hgrp].append({
            "source": src, "upc": upc, "name": name or "",
            "name_tokens": toks(name or ""),
            "brand": brand or "",
            "grams": float(g), "cents": int(c),
            "cpg": float(c) / float(g) if g else 1e9,
            "sr28": "", "fndds": "",
            "htc": hcode or "", "qual": 1,
        })
    return dict(out)


def load_ingredient_targets() -> dict[str, dict]:
    """Recipe ingredient → {htc_code, htc_group, sr28_fdc, item_tokens}."""
    htc = {}
    with ING_TAGS.open() as f:
        for r in csv.DictReader(f):
            htc[r["item"].lower()] = (r["htc_code"], r["htc_group"])
    sr_map = {}
    with ING_SR.open() as f:
        for r in csv.DictReader(f):
            sr_map[r["item"].lower()] = r.get("fdc_id") or ""
    out = {}
    for item, (code, grp) in htc.items():
        out[item] = {
            "htc_code": code,
            "htc_group": grp,
            "sr28_fdc": sr_map.get(item, ""),
            "item_tokens": toks(item),
        }
    return out


def pick_cheapest(item: str, info: dict, by_group: dict) -> dict | None:
    """Find the cheapest priced-product whose:
       - htc_group matches the ingredient's group
       - name has token overlap with the ingredient
       - bonus if sr28 matches our resolved SR-28 fdc
       Returns the single best (cheapest CPG that passed filters)."""
    grp = info["htc_group"]
    if grp in ("", "0", "N"):
        return None
    pool = by_group.get(grp, [])
    if not pool:
        return None
    item_tokens = info["item_tokens"]
    target_sr = info["sr28_fdc"]
    candidates = []
    for p in pool:
        inter = item_tokens & p["name_tokens"]
        if not inter:
            continue
        # sr28 exact match is the strongest signal
        sr_match_bonus = 5.0 if (target_sr and p["sr28"] == target_sr) else 0.0
        # quality tier 1 = best, 3 = noisier; flip so higher = better
        qual_bonus = max(0, 4 - p["qual"])
        score = (
            len(inter) * 1.0
            + sr_match_bonus
            + qual_bonus * 0.5
            - 0.0001 * p["cpg"]    # tie-break cheaper
        )
        candidates.append((score, p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    # require positive top score (otherwise it's just garbage overlap)
    if candidates[0][0] <= 0.5:
        return None
    # of the top-3 by score, pick the cheapest CPG
    top = sorted(candidates[:3], key=lambda x: x[1]["cpg"])
    return top[0][1]


def main() -> int:
    print("loading our priced_products db...")
    by_group = load_priced_by_group()
    print(f"  {sum(len(v) for v in by_group.values()):,} priced products "
          f"across {len(by_group):,} HTC groups (food only)")
    print("loading recipe ingredient targets...")
    ing = load_ingredient_targets()
    print(f"  {len(ing):,} ingredient targets")

    targets = ["Best Lemonade", "Low-Fat Berry Blue Frozen Dessert",
               "Chicken Biryani with Saffron", "Banana Bread"]
    chosen: dict[int, str] = {}
    with LINES.open() as f:
        for r in csv.DictReader(f):
            t = r["recipe_title"]
            if any(tt.lower() in t.lower() for tt in targets) and t not in chosen.values():
                chosen[int(r["recipe_id"])] = t
                if len(chosen) >= 5:
                    break

    by_recipe: dict[int, list] = defaultdict(list)
    with LINES.open() as f:
        for r in csv.DictReader(f):
            try:
                rid = int(r["recipe_id"])
            except ValueError:
                continue
            if rid in chosen:
                by_recipe[rid].append(r)

    for rid, title in chosen.items():
        lines = by_recipe.get(rid, [])
        print(f"\n{'=' * 80}")
        print(f"  RECIPE #{rid}: {title}  ({len(lines)} lines)")
        print(f"  using OUR priced_products_tagged.db (HTC-filtered)")
        print(f"{'=' * 80}")
        # aggregate per pkg upc
        agg: dict[str, dict] = {}
        n_priced = 0
        for L in lines:
            item = L["ingredient_item"].lower()
            grams_raw = L.get("grams_resolved") or ""
            try:
                grams = float(grams_raw) if grams_raw else 0.0
            except ValueError:
                grams = 0.0
            info = ing.get(item)
            pkg = pick_cheapest(item, info, by_group) if info else None
            if not pkg or grams <= 0:
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  [no priced match]")
                continue
            key = pkg["upc"]
            if key not in agg:
                agg[key] = {"pkg": pkg, "need": 0, "lines": []}
            agg[key]["need"] += grams
            agg[key]["lines"].append((item, grams))
            n_priced += 1

        total_cents = 0
        for key, info in agg.items():
            pkg = info["pkg"]
            need = info["need"]
            n_pkgs = max(1, math.ceil(need / pkg["grams"]))
            line_cost = n_pkgs * pkg["cents"]
            leftover = n_pkgs * pkg["grams"] - need
            total_cents += line_cost
            items_str = " + ".join(f"{it} ({g:.0f}g)" for it, g in info["lines"])
            print(f"  {items_str[:60]:<60}  need {need:>5.0f}g")
            print(f"      → {n_pkgs}× [{pkg['name'][:40]:<40}] "
                  f"{pkg['grams']:>5.0f}g @ ${pkg['cents']/100:>5.2f}/{pkg['source']:<7} "
                  f"= ${line_cost/100:>6.2f}  (+{leftover:.0f}g leftover)")

        print(f"  {'─' * 76}")
        print(f"  TOTAL ({n_priced}/{len(lines)} lines priced, {len(agg)} packages):  "
              f"${total_cents/100:>7.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
