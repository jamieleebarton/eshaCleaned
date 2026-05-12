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
        "boneless","skinless","grade","brand",
        # ripeness/quality words — recipe authors specify them but shoppers
        # just buy the produce. "ripe bananas" → "bananas".
        "ripe","unripe","overripe","green","fully","perfectly",
        # prep state authors mention but don't change what to buy
        "thinly","thickly","finely","coarsely","roughly","lightly","heavily",
        "shaved","grated","crushed","cracked","crumbled","torn",
        "softened","melted","cold","cool","hot","warm","room",
        "peeled","seeded","cored","trimmed","stemmed","pitted",
        "drained","rinsed","washed","dried","patted",
        "halved","quartered","cubed","julienned","ribboned",
        "good","best","quality","premium","real"}
RULE_B_PIDS = {"Spice Blend", "Seasoning", "Single Entree", "Family Entree",
               "Pasta Sauce", "BBQ Sauce", "Hot Sauce", "Marinade", "Pizza",
               "Sandwich", "Salad", "Composite Dish", "Pasta Dish", "Sauce",
               "Soup", "Salsa", "Dip"}

# Name-level reject — applies to ALL priced products regardless of bridge.
# Catches Kroger items with no Walmart categoryPath (e.g. "Kroger Mouthwash
# Powerful Fresh Mint" bridged to nothing but slipped through head-noun) and
# joke/decoration products that bridged to a real food PID
# (e.g. "Easter Cascaron Confetti Eggs" → PID=Eggs).
NON_FOOD_NAME = re.compile(
    r"\b(cascaron|confetti|easter|christmas|halloween|"
    r"mouthwash|toothpaste|deodorant|shampoo|conditioner|soap|lotion|"
    r"listerine|colgate|crest|scope|dental|oral\s*care|"
    r"detergent|laundry|cleaner|cleaning|bleach|"
    r"vitamins?|supplements?|protein\s*(?:powder|shake|drink|bar)|"
    r"pet\s*food|cat\s*food|dog\s*food|bird\s*food|fish\s*food|"
    r"candle|fragrance|perfume|cologne|"
    r"decoration|decorat(?:ive|ion)|toy|gift\s*set)\b",
    re.I,
)

# Saffron-tablespoon defense — recipe sources sometimes specify "1 tbsp
# saffron threads" which is ~2-3 g, far above the realistic max for a
# single recipe. SR-28 (FDC 170934) lists 1 tsp saffron = 0.7 g; a real
# "pinch" is ~1/16 tsp ≈ 0.04 g. Cap at 1 tsp regardless of source claim.
SAFFRON_CAP_GRAMS = 0.7


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
            ing_htc[it] = (
                r["htc_code"],
                r["htc_group"],
                r.get("htc_full_code", ""),
                r.get("retail_leaf_path", ""),
                r.get("canonical_path", ""),
            )

    # Pre-aggregate consensus into (gf, pid_lc) → set of canonical_paths and
    # (gf, mod_lc) → set of canonical_paths. Canonical path is the source of
    # truth — the tree was built to produce these. Match on path, not PID.
    by_gf_pids: dict[str, dict[str, str]] = defaultdict(dict)
    by_gf_mods: dict[str, dict[str, str]] = defaultdict(dict)
    pid_to_canonicals: dict[tuple[str, str], set[str]] = defaultdict(set)
    mod_to_canonicals: dict[tuple[str, str], set[str]] = defaultdict(set)
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
            canonical = (r.get("canonical_path") or "").strip()
            by_gf_pids[gf][pid.lower()] = pid
            if canonical:
                pid_to_canonicals[(gf, pid.lower())].add(canonical)
            if mod and pid in RULE_B_PIDS:
                by_gf_mods[gf][mod.lower()] = mod
                if canonical:
                    mod_to_canonicals[(gf, mod.lower())].add(canonical)

    out: dict[str, dict] = {}
    for item, ing_data in ing_htc.items():
        code, grp, full_code, rlp, canonical = ing_data
        item_tokens = toks(item)
        if not item_tokens or not code:
            continue
        # htc_code may be `~GFFOPTC` (with prefix) — strip for gf extraction
        bare = code.lstrip("~")
        gf = bare[:2] if len(bare) >= 2 else ""
        primary = primary_noun(item)

        # 1. EXACT pid (case-insensitive) at same htc — gold
        # 2. Rule-B: pid in RULE_B_PIDS AND modifier token-overlap
        # 3. all-tokens-in-pid
        # 4. partial overlap (only if narrow)
        # Concept = (canonical_path, modifier_or_empty). For Rule-B PIDs the
        # modifier IS the leaf (Spice Blend > Cardamom). For non-Rule-B the
        # canonical already carries the leaf and we ignore mod.
        valid_concepts: set[tuple[str, str]] = set()

        pid_pool = by_gf_pids.get(gf, {})
        mod_pool = by_gf_mods.get(gf, {})

        for pid_lc, pid in pid_pool.items():
            pid_tokens = toks(pid_lc)
            matched = False
            if pid_lc == item:
                matched = True
            elif primary and primary in pid_tokens and item_tokens.issubset(pid_tokens):
                matched = True
            if matched:
                # Non-Rule-B: pair canonical with empty modifier.
                # Rule-B (e.g. ingredient is exactly 'sauce'): pair with all mods.
                for canon in pid_to_canonicals.get((gf, pid_lc), set()):
                    if pid in RULE_B_PIDS:
                        # Recipe asks for 'sauce' generically — match any mod.
                        valid_concepts.add((canon, "*"))
                    else:
                        valid_concepts.add((canon, ""))

        for mod_lc, mod in mod_pool.items():
            mod_tokens = toks(mod_lc)
            # Modifier matches the ingredient ONLY if the modifier IS the
            # ingredient or a strict subset. We do NOT loosen this to "primary
            # noun overlap" — that's what made 'cilantro' leak into Rule-B
            # Sauce > 'Cilantro Lime'. For 'cardamom seeds' (mod='Cardamom') the
            # subset rule still passes; for 'cilantro' (mod='Cilantro Lime') it
            # correctly fails.
            if mod_lc == item or (mod_tokens and mod_tokens.issubset(item_tokens)):
                for canon in mod_to_canonicals.get((gf, mod_lc), set()):
                    valid_concepts.add((canon, mod_lc))

        out[item] = {
            "htc_code": code,
            "htc_full_code": full_code,
            "rlp": rlp,
            "canonical": canonical,
            "htc_gf": gf,
            "valid_concepts": valid_concepts,
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
               bridge_status, non_food_path,
               htc_full_code, retail_leaf_path
        FROM priced_products
        WHERE marketplace = 0 AND available = 1
          AND grams > 0 AND cents > 0
          AND htc_group NOT IN ('0','N')
          AND (non_food_path = 0 OR non_food_path IS NULL)
    """):
        src, upc, name, brand, g, c, hc, hg, cpid, ccan, cmod, bs, nfp, hfc, rlp = r
        # Name-level non-food reject (catches Kroger items with no Walmart
        # categoryPath, and joke/decoration products that mis-bridged to a
        # real food PID via the consensus tagger)
        if name and NON_FOOD_NAME.search(name):
            continue
        # Strip the `~` Excel-safe prefix when computing the (group, family) bucket.
        bare = (hc or "").lstrip("~")
        gf = bare[:2] if bare else ""
        rec = {
            "source": src, "upc": upc, "name": name or "", "brand": brand or "",
            "name_tokens": toks(name or ""),
            "head_tokens": head_tokens(name or ""),
            "grams": float(g), "cents": int(c),
            "cpg": float(c) / float(g) if g else 1e9,
            "htc": hc or "", "htc_gf": gf, "htc_group": hg or "",
            "htc_full": hfc or "",
            "rlp": rlp or "",
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
    valid_concepts = info["valid_concepts"]

    cands = []
    pool = by_gf.get(gf, [])
    seen = set()

    # Strict-then-relaxed cascade. Higher-tier hits get higher score and win
    # over wider matches. Within a tier, cheapest cents-per-gram wins.
    recipe_full = info.get("htc_full_code", "")
    recipe_htc = info.get("htc_code", "")
    recipe_canonical = info.get("canonical", "")

    # Tier 1 (12.0): htc_full_code exact match — same retail_leaf_path AND claims.
    #                "organic cheddar" matches only organic cheddar walmart products.
    if recipe_full and "-" in recipe_full:
        for p in pool:
            if p.get("htc_full") and p["htc_full"] == recipe_full:
                cands.append((12.0, p))
                seen.add(p["upc"])

    # Tier 2 (9.0): htc_code bucket match — same food_slot identity, possibly
    #               different variant or claims. "lime seltzer" matches all
    #               lime sparkling-water buckets; "butter" matches all butter
    #               (any sub-identity).
    if recipe_htc:
        for p in pool:
            if p["upc"] in seen:
                continue
            if p.get("htc") == recipe_htc:
                cands.append((9.0, p))
                seen.add(p["upc"])

    # Tier 3 (10.0 → keep existing concept matching as a parallel high-trust tier).
    # Concept = (canonical_path, modifier) for Rule-B PIDs, else (canonical_path, '').
    for p in pool:
        if p["upc"] in seen:
            continue
        if not p["canonical"]:
            continue
        product_concept_strict = (p["canonical"], p["modifier"].lower() if p["pid"] in RULE_B_PIDS else "")
        product_concept_wild = (p["canonical"], "*")
        if product_concept_strict in valid_concepts or product_concept_wild in valid_concepts:
            cands.append((10.0, p))
            seen.add(p["upc"])

    # Tier 4 (6.0): canonical_path direct match — recipe's canonical agrees
    #               with product's canonical. Catches cases where concept
    #               tuples didn't fire because the modifier rules were narrow.
    if recipe_canonical and not cands:
        for p in pool:
            if p["upc"] in seen:
                continue
            if p["canonical"] == recipe_canonical:
                cands.append((6.0, p))
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
            # Saffron-data sanity cap: 1 tbsp saffron threads in source data
            # is a recipe error (real biryani uses a pinch); cap at 1 g
            if "saffron" in item and grams > SAFFRON_CAP_GRAMS:
                grams = SAFFRON_CAP_GRAMS
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
