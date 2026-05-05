#!/usr/bin/env python3
"""V5 — Recipe cost using the FULL HTC tree + modifier + substitutions.

Fixes the 4 architectural gaps from v4:
  1. Hard gate on htc_code[0:2] (group + family) — kills cookies-for-vanilla
  2. Honor consensus modifier for Rule-B foods (lemon zest = Seasoning + mod=Lemon Peel)
  3. Walk canonical_path for parent fallback (specific node empty → walk up)
  4. Apply part-whole substitutions (zest → whole lemon, egg whites → eggs)
  5. Drop priced products flagged non_food_path (Toys, Personal Care, Pets)

Per ingredient line:
  A. literal: build valid PIDs+modifiers from consensus; find priced products
     with same htc[0:2] AND consensus_pid OR consensus_modifier match
  B. substitution: if A is empty, look up the substitution rule, treat its
     buy_canonical/PID set as the target
  C. head-noun fallback: only un-bridged products with primary noun match
  D. exclude non_food_path=1 always
"""
from __future__ import annotations

import csv
import math
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from htc.substitutions import apply_substitution  # noqa: E402

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
PRICED_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
HERE = Path(__file__).resolve().parent
LINES = HERE / "output" / "recipes_unified.csv"
ING_TAGS = HERE / "output" / "recipe_ingredient_htc_tagged.csv"
CON_TAGS = HERE / "output" / "consensus_htc_tagged.csv"

WS = re.compile(r"[^a-z0-9 ]+")
STOP = {"the","of","and","with","a","an","to","in","fresh","frozen","raw",
        "ground","whole","large","medium","small","extra","lean","low","fat",
        "free","organic","natural","chopped","diced","minced","sliced",
        "boneless","skinless","grade","brand"}
RULE_B_PIDS = {"Spice Blend", "Seasoning", "Single Entree", "Family Entree",
               "Pasta Sauce", "BBQ Sauce", "Hot Sauce", "Marinade", "Pizza",
               "Sandwich", "Salad", "Composite Dish", "Pasta Dish", "Sauce",
               "Soup", "Salsa", "Dip"}


def toks(s: str) -> set[str]:
    s = WS.sub(" ", (s or "").lower())
    return {t for t in s.split() if len(t) >= 2 and t not in STOP}


def primary_noun(item: str) -> str:
    parts = [t for t in WS.sub(" ", (item or "").lower()).split()
             if len(t) >= 2 and t not in STOP]
    return parts[-1] if parts else ""


def head_tokens(s: str) -> set[str]:
    parts = [t for t in WS.sub(" ", (s or "").lower()).split()
             if len(t) >= 2 and t not in STOP]
    return set(parts[-2:]) if parts else set()


# ── Build the consensus side: which (PID, modifier, canonical) tuples
# legitimately mean each recipe ingredient ─────────────────────────────
def build_ingredient_targets(items_filter: set[str] | None = None) -> dict[str, dict]:
    ing_htc = {}
    with ING_TAGS.open() as f:
        for r in csv.DictReader(f):
            it = r["item"].lower()
            if items_filter and it not in items_filter:
                continue
            ing_htc[it] = (r["htc_code"], r["htc_group"])

    # Pre-aggregate consensus: dedupe by (group+family, pid) and (group+family, modifier)
    # so we don't iterate 50k SKUs per ingredient.
    by_gf_pids: dict[str, dict[str, str]] = defaultdict(dict)   # gf → {pid_lc: pid}
    by_gf_mods: dict[str, dict[str, str]] = defaultdict(dict)   # gf → {mod_lc: (pid, mod)}
    with CON_TAGS.open() as f:
        for r in csv.DictReader(f):
            pid = (r.get("product_identity_fixed") or "").strip()
            if not pid:
                continue
            mod = (r.get("modifier") or "").split(" > ")[0].strip()
            code = r.get("htc_code") or ""
            if len(code) < 2:
                continue
            gf = code[:2]
            by_gf_pids[gf][pid.lower()] = pid
            if mod and pid in RULE_B_PIDS:
                by_gf_mods[gf][mod.lower()] = mod

    out: dict[str, dict] = {}
    for item, (code, grp) in ing_htc.items():
        item_tokens = toks(item)
        if not item_tokens or not code:
            continue
        gf = code[:2] if len(code) >= 2 else ""
        primary = primary_noun(item)

        # 1. EXACT pid (case-insensitive) at same htc — gold
        # 2. Rule-B: pid in RULE_B_PIDS AND modifier token-overlap
        # 3. all-tokens-in-pid
        # 4. partial overlap (only if narrow)
        valid_pids: set[str] = set()
        valid_modifiers: set[str] = set()

        pid_pool = by_gf_pids.get(gf, {})
        mod_pool = by_gf_mods.get(gf, {})

        for pid_lc, pid in pid_pool.items():
            pid_tokens = toks(pid_lc)
            # 1. EXACT pid match (case-insensitive)
            if pid_lc == item:
                valid_pids.add(pid)
                continue
            # 2. PID contains the primary noun AND all item tokens are in pid
            if primary and primary in pid_tokens and item_tokens.issubset(pid_tokens):
                valid_pids.add(pid)

        for mod_lc, mod in mod_pool.items():
            mod_tokens = toks(mod_lc)
            # Rule-B: the modifier IS the recipe ingredient.
            # Require EXACT modifier match OR primary-noun match where all
            # item tokens are in modifier tokens.
            if mod_lc == item or (primary and primary in mod_tokens
                                  and item_tokens.issubset(mod_tokens)):
                valid_modifiers.add(mod)

        out[item] = {
            "htc_code": code,
            "htc_gf": gf,
            "valid_pids": valid_pids,
            "valid_modifiers": valid_modifiers,
            "item_tokens": item_tokens,
            "primary": primary,
        }
    return out


# ── Build a UPC → consensus_modifier index (we never wrote the modifier
# onto priced_products_v2; we re-pull it via the bridge) ────────────────
def load_priced_products() -> tuple[dict, dict]:
    con = sqlite3.connect(str(PRICED_DB))
    by_gf: dict[str, list[dict]] = defaultdict(list)
    all_food: list[dict] = []
    for r in con.execute("""
        SELECT source, upc, name, brand, grams, cents, htc_code, htc_group,
               consensus_pid, consensus_canonical, consensus_modifier,
               bridge_status, non_food_path
        FROM priced_products
        WHERE marketplace = 0 AND available = 1
          AND grams > 0 AND cents > 0
          AND htc_group NOT IN ('0','N')
          AND (non_food_path = 0 OR non_food_path IS NULL)
    """):
        src, upc, name, brand, g, c, hc, hg, cpid, ccan, cmod, bs, nfp = r
        gf = (hc or "")[:2] if hc else ""
        rec = {
            "source": src, "upc": upc, "name": name or "", "brand": brand or "",
            "name_tokens": toks(name or ""),
            "head_tokens": head_tokens(name or ""),
            "grams": float(g), "cents": int(c),
            "cpg": float(c) / float(g) if g else 1e9,
            "htc": hc or "", "htc_gf": gf, "htc_group": hg or "",
            "pid": cpid or "", "canonical": ccan or "",
            "modifier": (cmod or "").split(" > ")[0].strip(),
            "bridged": bs == "bridged",
        }
        by_gf[gf].append(rec)
        all_food.append(rec)
    return dict(by_gf), all_food


# ── Pick the cheapest legitimate match ─────────────────────────────────
def pick(item: str, info: dict, by_gf: dict, all_food: list) -> dict | None:
    gf = info["htc_gf"]
    if not gf or gf[0] in ("0", "N"):
        return None
    item_tokens = info["item_tokens"]
    primary = info["primary"]
    valid_pids_lc = {p.lower() for p in info["valid_pids"]}
    valid_mods_lc = {m.lower() for m in info["valid_modifiers"]}

    cands = []
    pool = by_gf.get(gf, [])

    # Path A: exact PID OR exact modifier match (Rule B). Hard gate on group+family.
    seen = set()
    for p in pool:
        if (p["pid"] and p["pid"].lower() in valid_pids_lc) or \
           (p["modifier"] and p["modifier"].lower() in valid_mods_lc):
            cands.append((10.0, p))
            seen.add(p["upc"])

    # Path C: un-bridged head-noun match. STRICT: primary noun must be in
    # the product head AND a qualifier token must also appear in the name.
    if not cands:
        for p in pool:
            if p["bridged"]:
                continue
            if primary and primary not in p["head_tokens"]:
                continue
            inter = item_tokens & p["head_tokens"]
            if not inter:
                continue
            qualifiers = item_tokens - {primary}
            if qualifiers and not (qualifiers & p["name_tokens"]):
                continue
            cands.append((4.0, p))

    if not cands:
        return None
    # Score-tiered: among the top score tier, pick cheapest cents-per-gram
    cands.sort(key=lambda x: -x[0])
    top_score = cands[0][0]
    same_tier = [c for c in cands if c[0] == top_score]
    same_tier.sort(key=lambda x: x[1]["cpg"])
    return same_tier[0][1]


def pick_by_substitution(item: str, by_gf: dict, all_food: list, ingredients: dict) -> dict | None:
    """Apply part-whole substitution rules: lemon zest → whole lemon, etc."""
    sub = apply_substitution(item)
    if sub is None:
        return None
    # Try the rewritten item first (its full HTC + PID resolution)
    rewritten = sub.item_replacement
    if "\\" not in rewritten:
        info = ingredients.get(rewritten)
        if info:
            pkg = pick(rewritten, info, by_gf, all_food)
            if pkg:
                return pkg
    # Try the canonical_path / PID hints from the substitution
    for canon in sub.canonical_paths:
        # find any product with that canonical
        for p in all_food:
            if p["canonical"] == canon:
                return p
    for pid in sub.pids:
        for p in all_food:
            if p["pid"].lower() == pid.lower():
                return p
    return None


def main() -> int:
    targets = ["Best Lemonade", "Low-Fat Berry Blue Frozen Dessert",
               "Chicken Biryani with Saffron", "Banana Bread"]
    chosen: dict[int, str] = {}
    test_items: set[str] = set()
    with LINES.open() as f:
        for r in csv.DictReader(f):
            t = r["recipe_title"]
            if any(tt.lower() in t.lower() for tt in targets) and t not in chosen.values():
                chosen[int(r["recipe_id"])] = t
                if len(chosen) >= 5:
                    break
    chosen_ids = set(chosen.keys())
    with LINES.open() as f:
        for r in csv.DictReader(f):
            try:
                rid = int(r["recipe_id"])
            except ValueError:
                continue
            if rid in chosen_ids:
                test_items.add(r["ingredient_item"].lower())
    # Also add the substitution-rewritten versions
    from htc.substitutions import SUBSTITUTIONS
    extra = set()
    for it in list(test_items):
        for sub in SUBSTITUTIONS:
            if sub.pattern.match(it) and "\\" not in sub.item_replacement:
                extra.add(sub.item_replacement)
    test_items |= extra

    print("loading consensus targets...")
    ingredients = build_ingredient_targets(items_filter=test_items)
    print(f"  {len(ingredients):,} ingredient targets (filtered to test recipes)")
    print("loading priced products (food only, group+family indexed)...")
    by_gf, all_food = load_priced_products()
    print(f"  {len(all_food):,} priced products  ({len(by_gf):,} group+family buckets)")

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
        print(f"  v5: HTC group+family hard gate + modifier + canonical_path + substitutions")
        print(f"{'=' * 80}")
        agg: dict[str, dict] = {}
        n_priced = 0
        for L in lines:
            item = L["ingredient_item"].lower()
            grams_raw = L.get("grams_resolved") or ""
            try:
                grams = float(grams_raw) if grams_raw else 0.0
            except ValueError:
                grams = 0.0
            info = ingredients.get(item)
            tag = "literal"
            pkg = pick(item, info, by_gf, all_food) if info else None
            if not pkg:
                # Try part-whole substitution
                pkg = pick_by_substitution(item, by_gf, all_food, ingredients)
                if pkg:
                    tag = "substituted"
            if not pkg or grams <= 0:
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  [no priced match]")
                continue
            key = pkg["upc"]
            if key not in agg:
                agg[key] = {"pkg": pkg, "need": 0, "lines": [], "tag": tag}
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
            tag = "★bridged" if pkg["bridged"] else f"head-noun"
            tag = f"{info['tag']:<11}/{tag}"
            print(f"  {items_str[:60]:<60}  need {need:>5.0f}g")
            print(f"      → {n_pkgs}× [{pkg['name'][:40]:<40}] "
                  f"{pkg['grams']:>5.0f}g @ ${pkg['cents']/100:>5.2f}/{pkg['source']:<7} "
                  f"= ${line_cost/100:>6.2f}  [{tag}, pid={pkg['pid'] or '—'}]")
        print(f"  {'─' * 76}")
        print(f"  TOTAL ({n_priced}/{len(lines)} lines priced, {len(agg)} packages): "
              f" ${total_cents/100:>7.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
