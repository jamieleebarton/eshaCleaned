#!/usr/bin/env python3
"""V2 — Recipe COST with full-package pricing AND HTC-quality-filtered packages.

Fixes the v1 problems:
  1. Full-package model: you buy whole packages, leftover is leftover.
  2. HTC sanity-filter: only accept Hestia packages whose `food_description`
     token-overlaps with the recipe ingredient AND whose FNDDS code matches
     a SKU in our consensus that has the same HTC + product_identity_fixed.
     This kills the "lemon zest → Fruit Cup", "ice cube → Crumb Cake Mix",
     "butter → Peanut Butter" mis-tags from Hestia's package db.

Per ingredient line:
  1. recipe item → HTC code → list of valid FNDDS codes (from consensus SKUs
     with same HTC + pid)
  2. find Hestia packages with one of those FNDDS AND descriptions whose
     tokens overlap with the recipe ingredient
  3. pick the cheapest-per-gram package that satisfies (1) + (2)
  4. n_packages = ceil(grams_needed / package_weight_g)
  5. line_cost = n_packages * package_price
  6. leftover_g = (n_packages * pkg_g) - grams_needed
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
HESTIA_PKG = Path("/Users/jamiebarton/Desktop/Hestia/api/data/food_packages_final.db")
HERE = Path(__file__).resolve().parent
LINES = HERE / "output" / "recipes_unified.csv"
ING_TAGS = HERE / "output" / "recipe_ingredient_htc_tagged.csv"
CON_TAGS = HERE / "output" / "consensus_htc_tagged.csv"

WS = re.compile(r"[^a-z0-9 ]+")
STOP = {"the","of","and","with","a","an","to","in","fresh","frozen","raw",
        "ground","whole","large","medium","small","extra","lean","low","fat",
        "free","organic","natural","chopped","diced","minced","sliced",
        "boneless","skinless"}


def toks(s: str) -> set[str]:
    s = WS.sub(" ", (s or "").lower())
    return {t for t in s.split() if len(t) >= 2 and t not in STOP}


def load_packages_by_fndds() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    con = sqlite3.connect(str(HESTIA_PKG))
    cur = con.execute("""
      SELECT fndds_code, food_description, package_weight_grams,
             walmart_price_cents, kroger_price_cents
      FROM packages
      WHERE package_weight_grams > 0
        AND (walmart_price_cents IS NOT NULL OR kroger_price_cents IS NOT NULL)
    """)
    for fc, desc, w, wp, kp in cur:
        for cents, store in [(wp, "walmart"), (kp, "kroger")]:
            if not cents:
                continue
            out[fc].append({
                "fndds": fc,
                "desc": desc or "",
                "desc_tokens": toks(desc or ""),
                "weight_g": float(w),
                "cents": int(cents),
                "store": store,
                "per_g_cents": int(cents) / float(w),
            })
    return dict(out)


def build_ingredient_to_valid_fndds() -> dict[str, dict]:
    """For each recipe ingredient:
      - get HTC + SR-28 description (the SR desc is the gold-standard label)
      - get valid FNDDS codes from consensus SKUs sharing HTC + matching pid
    Returns dict with htc, sr_desc tokens, and valid_fndds set.
    """
    ing_htc = {}
    with ING_TAGS.open() as f:
        for r in csv.DictReader(f):
            ing_htc[r["item"].lower()] = r["htc_code"]

    # Pull SR-28 description for each item (this is the clean canonical name)
    ing_sr_desc: dict[str, str] = {}
    sr_csv = HERE / "output" / "ingredient_to_sr28.csv"
    with sr_csv.open() as f:
        for r in csv.DictReader(f):
            ing_sr_desc[r["item"].lower()] = r.get("sr_description", "")

    by_htc: dict[str, list] = defaultdict(list)
    with CON_TAGS.open() as f:
        for r in csv.DictReader(f):
            pid = (r.get("product_identity_fixed") or "").strip()
            if not pid:
                continue
            by_htc[r["htc_code"]].append({
                "fndds": (r.get("fndds_code") or "").strip(),
                "pid": pid,
                "pid_tokens": toks(pid),
            })

    out: dict[str, dict] = {}
    for item, code in ing_htc.items():
        item_tokens = toks(item)
        sr_desc = ing_sr_desc.get(item, "")
        # Use SR description as the gold-standard match target; fall back to item.
        target_tokens = toks(sr_desc) if sr_desc else item_tokens
        # Add the recipe item tokens as a backup (helps when SR desc is too generic)
        target_tokens = target_tokens | item_tokens
        if not target_tokens or not code:
            continue
        skus = by_htc.get(code, [])
        valid_fndds = Counter()
        for s in skus:
            if not s["fndds"]:
                continue
            inter = item_tokens & s["pid_tokens"]
            if inter:
                weight = 5 if s["pid"].lower() == item else 1
                valid_fndds[s["fndds"]] += weight
        if valid_fndds:
            out[item] = {
                "htc": code,
                "valid_fndds": dict(valid_fndds.most_common(10)),
                "match_tokens": target_tokens,    # for matching Hestia pkg descs
                "item_tokens": item_tokens,
                "sr_desc": sr_desc,
            }
    return out


def pick_best_package(item: str, ing_info: dict, packages_by_fndds: dict) -> dict | None:
    """Pick the cheapest-per-gram package that:
      (a) has FNDDS in the valid set for this ingredient
      (b) package description must contain at least one ITEM token (the
          actual recipe word, e.g. 'butter' / 'cinnamon' / 'sugar' / 'soda')
      (c) penalty for package descriptions whose tokens conflict
          (e.g. 'nut butter' or 'diet cream soda' when the recipe just says
          'butter' or 'baking soda')
    """
    candidates = []
    item_tokens = ing_info["item_tokens"]
    bad_qualifiers = {
        "nut", "nuts", "peanut", "almond", "cashew",   # filters Nut Butter when looking for butter
        "diet", "cream", "lite", "zero",                # filters Diet Cream Soda for baking soda
        "ice",                                           # filters Ice Cream when looking for cream
        "soda",                                          # filters Diet Cream Soda for baking soda specifically
        "soup", "stew",                                  # filters Onion Soup for onion
        "drink", "drinks", "punch",                      # filters drinks when looking for water
        "ade", "lemonade",                               # filters Lemonade for lemon juice
        "candy", "chocolate", "frosting",                # filters candy when looking for staples
        "butter",                                        # ambiguous; only allow if it's IN the query
        "smoked", "honey", "garlic", "parmesan",         # only allow if the query qualifies
        "truffle",                                       # filters truffle salt when query is salt
        "frozen",                                        # filters frozen-prepared form
        "sandwich", "fruit",                             # broad descriptors
    }
    for fndds, weight in ing_info["valid_fndds"].items():
        for pkg in packages_by_fndds.get(fndds, []):
            # Strict: at least one item-token must be in pkg description
            inter = item_tokens & pkg["desc_tokens"]
            if not inter:
                continue
            # Penalize spurious-qualifier tokens that aren't in the recipe item
            spurious = sum(1 for t in pkg["desc_tokens"]
                           if t in bad_qualifiers and t not in item_tokens)
            score = (
                weight
                + len(inter) * 1.0
                - spurious * 1.5
                - 0.001 * pkg["per_g_cents"]
            )
            candidates.append((score, pkg))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    # only return if best score is positive (otherwise mismatch is too noisy)
    if candidates[0][0] <= 0:
        return None
    return candidates[0][1]


def main() -> int:
    print("loading packages...")
    packages_by_fndds = load_packages_by_fndds()
    print(f"  {sum(len(v) for v in packages_by_fndds.values()):,} package-prices")
    print("building ingredient → valid FNDDS map (via HTC + pid)...")
    ing_to_fndds = build_ingredient_to_valid_fndds()
    print(f"  {len(ing_to_fndds):,} ingredient strings have valid FNDDS")

    targets = ["Best Lemonade", "Low-Fat Berry Blue Frozen Dessert",
               "Chicken Biryani with Saffron", "Banana Bread"]
    chosen_titles = {}
    with LINES.open() as f:
        for r in csv.DictReader(f):
            t = r["recipe_title"]
            if any(tt.lower() in t.lower() for tt in targets) and t not in chosen_titles.values():
                rid = int(r["recipe_id"])
                chosen_titles[rid] = t
                if len(chosen_titles) >= 5:
                    break

    by_recipe: dict[int, list] = defaultdict(list)
    with LINES.open() as f:
        for r in csv.DictReader(f):
            try:
                rid = int(r["recipe_id"])
            except ValueError:
                continue
            if rid in chosen_titles:
                by_recipe[rid].append(r)

    for rid, title in chosen_titles.items():
        lines = by_recipe.get(rid, [])
        print(f"\n{'=' * 80}")
        print(f"  RECIPE #{rid}: {title}  ({len(lines)} lines)")
        print(f"  cost model: FULL-PACKAGE, HTC-filtered")
        print(f"{'=' * 80}")
        total_cents = 0
        n_priced = 0
        n_fallback = 0
        # Aggregate grams needed per package SKU (so we don't rebuy per line)
        by_pkg_key: dict[tuple, dict] = {}
        for L in lines:
            item = L["ingredient_item"].lower()
            grams_raw = L.get("grams_resolved") or ""
            try:
                grams = float(grams_raw) if grams_raw else 0.0
            except ValueError:
                grams = 0.0
            ing_info = ing_to_fndds.get(item)
            pkg = pick_best_package(item, ing_info, packages_by_fndds) if ing_info else None
            if not pkg or grams <= 0:
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  [no priced match]")
                continue
            key = (pkg["fndds"], round(pkg["weight_g"]), pkg["store"])
            if key not in by_pkg_key:
                by_pkg_key[key] = {
                    "pkg": pkg,
                    "grams_needed": 0,
                    "lines": [],
                }
            by_pkg_key[key]["grams_needed"] += grams
            by_pkg_key[key]["lines"].append((item, grams))
            n_priced += 1

        # Now compute full-package cost per unique pkg
        for key, info in by_pkg_key.items():
            pkg = info["pkg"]
            need_g = info["grams_needed"]
            n_pkgs = max(1, math.ceil(need_g / pkg["weight_g"]))
            line_cost = n_pkgs * pkg["cents"]
            leftover = n_pkgs * pkg["weight_g"] - need_g
            total_cents += line_cost
            items_str = " + ".join(f"{it} ({g:.0f}g)" for it, g in info["lines"])
            print(f"  {items_str[:55]:<55}  need {need_g:>5.0f}g")
            print(f"      → {n_pkgs}× [{pkg['desc'][:30]:<30}] "
                  f"{pkg['weight_g']:>5.0f}g @ ${pkg['cents']/100:>4.2f}/{pkg['store']:<7} "
                  f"= ${line_cost/100:>6.2f}  (+{leftover:.0f}g leftover)")

        print(f"  {'─' * 76}")
        print(f"  TOTAL ({n_priced}/{len(lines)} lines priced, {len(by_pkg_key)} packages bought):"
              f"  ${total_cents/100:>7.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
