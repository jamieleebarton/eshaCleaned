#!/usr/bin/env python3
"""V6 — Use the tree end to end. No gf hard-gate. No cosine. No staple overrides.

Four rules:
  1. Cross-gf concept search. For each recipe ingredient, find every consensus
     row whose product_identity_fixed matches the ingredient's name (exact
     or primary-noun + token-subset), regardless of gf. The match returns the
     full set of (canonical_path, modifier) tuples + the SR-28 + FNDDS codes
     the tree already attached to those rows.

  2. Form axis filter. Recipe blob words like 'leaves', 'fresh', 'sprig',
     'bunch' mean fresh produce → restrict canonicals to start with
     'Produce >'. 'ground', 'dried' → 'Pantry > Spices'. 'frozen' → 'Frozen >'.

  3. SR-28 + FNDDS lookup is direct from the matched consensus rows. No cosine,
     no staple overrides.

  4. Head-noun fallback only when the priced product is unbridged AND the
     recipe primary noun IS the product's head token (not buried). Form must
     also match.
"""
from __future__ import annotations

import csv
import math
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
PRICED_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
HERE = Path(__file__).resolve().parent
LINES = HERE / "output" / "recipes_unified.csv"
CONSENSUS_AUDIT = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.v2.csv"

WS = re.compile(r"[^a-z0-9 ]+")
STOP = {"the","of","and","with","a","an","to","in","fresh","frozen","raw",
        "ground","whole","large","medium","small","extra","lean","low","fat",
        "free","organic","natural","chopped","diced","minced","sliced",
        "boneless","skinless","grade","brand",
        "ripe","unripe","overripe","green","fully","perfectly",
        "thinly","thickly","finely","coarsely","roughly","lightly","heavily",
        "shaved","grated","crushed","cracked","crumbled","torn",
        "softened","melted","cold","cool","hot","warm","room",
        "peeled","seeded","cored","trimmed","stemmed","pitted",
        "drained","rinsed","washed","dried","patted",
        "halved","quartered","cubed","julienned","ribboned",
        "good","best","quality","premium","real"}

# Rule-B PIDs: the modifier IS the leaf concept, not the canonical.
RULE_B_PIDS = {"Spice Blend","Seasoning","Single Entree","Family Entree",
               "Pasta Sauce","BBQ Sauce","Hot Sauce","Marinade","Pizza",
               "Sandwich","Salad","Composite Dish","Pasta Dish","Sauce",
               "Soup","Salsa","Dip"}

# Non-food name reject (catches Listerine / cascaron / etc.)
NON_FOOD_NAME = re.compile(
    r"\b(cascaron|confetti|easter|christmas|halloween|"
    r"mouthwash|toothpaste|deodorant|shampoo|conditioner|soap|lotion|"
    r"listerine|colgate|crest|scope|dental|oral\s*care|"
    r"epsom\s*salt|magnesium\s*soak|bath\s*salt|body\s*soak|"
    r"throat\s*drops?|cough\s*drops?|cough\s*syrup|lozenges?|"
    r"oral\s*anesthetic|sore\s*throat|"
    r"detergent|laundry|cleaner|cleaning|bleach|"
    r"vitamins?|supplements?|protein\s*(?:powder|shake|drink|bar)|"
    r"pet\s*food|cat\s*food|dog\s*food|bird\s*food|fish\s*food|"
    r"candle|fragrance|perfume|cologne|"
    r"decoration|decorat(?:ive|ion)|toy|gift\s*set)\b",
    re.I,
)

# Form keywords from the recipe blob → canonical-prefix constraint.
# If the recipe explicitly says "leaves" / "fresh" / "sprig" / "bunch", we
# require the canonical to start with "Produce >". And so on.
FORM_PRIORITY = [
    # (regex on recipe blob, allowed canonical prefixes)
    (re.compile(r"\b(leaves?|sprigs?|bunches?|bunch|fresh\s+\w+|whole\s+\w+\s+leaves)\b", re.I),
     ("Produce >",)),
    (re.compile(r"\b(ground|powder|powdered|dried|dry)\b", re.I),
     ("Pantry >",)),
    (re.compile(r"\bfrozen\b", re.I),
     ("Frozen >",)),
    (re.compile(r"\bcanned\b|\bcan\b", re.I),
     ("Pantry >",)),
]

SAFFRON_CAP_GRAMS = 0.7  # SR-28: 1 tsp saffron = 0.7 g; recipes saying tbsp are wrong

# Brand/marketing tokens to ignore when computing noise score on the food-name
# zone. These don't compete with the recipe ingredient — they're packaging.
BRAND_NOISE = {"great","value","kroger","simple","truth","marketside",
               "produce","foods","food","brand","store","walmart",
               "farms","family","size","pack","oz","gram","grams",
               "100","50","75","2","3","4","5","6","8","10","12","15","16","20",
               "select","choice","premium","gourmet","authentic","traditional",
               "100%","99%","real","pure","natural","authentic",
               # Color/grade/cage descriptors that don't change food identity
               "white","brown","yellow","red","green","jumbo","medium","small",
               "extra","grade","cage","cage-free","free","range","organic",
               "kosher","sea","light","heavy","thick","thin"}


def toks(s: str) -> set[str]:
    s = WS.sub(" ", (s or "").lower())
    return {t for t in s.split() if len(t) >= 2 and t not in STOP}


def primary_noun(item: str) -> str:
    parts = [t for t in WS.sub(" ", (item or "").lower()).split()
             if len(t) >= 2 and t not in STOP]
    return parts[-1] if parts else ""


def head_tokens(s: str, n: int = 2) -> set[str]:
    parts = [t for t in WS.sub(" ", (s or "").lower()).split()
             if len(t) >= 2 and t not in STOP]
    return set(parts[-n:]) if parts else set()


def name_zone(s: str) -> set[str]:
    # Tokens BEFORE the first comma — that's the food-name part of a typical
    # retail label ("Fresh Organic Mint, 0.5 oz Clamshell" → {fresh,organic,
    # mint}). Avoids head_tokens picking up "oz Clamshell" instead of "Mint".
    pre = (s or "").split(",")[0]
    return {t for t in WS.sub(" ", pre.lower()).split()
            if len(t) >= 2 and t not in STOP}


def form_constraint(blob: str) -> tuple[str, ...] | None:
    for pat, prefixes in FORM_PRIORITY:
        if pat.search(blob or ""):
            return prefixes
    return None


# ── Build ingredient → tree concept set ─────────────────────────────────
# For each ingredient we collect:
#   concepts:      set of (canonical_path, modifier_lc_or_empty)
#   sr28_codes:    set of fdc_ids the tree pinned for this concept
#   fndds_codes:   set of fndds_codes the tree pinned for this concept
def build_concepts(items_filter: set[str]) -> dict[str, dict]:
    # Three priority tiers: P1 = exact PID match, P2 = primary noun is the
    # PID's last token + item ⊂ pid, P3 = Rule-B modifier match. We collect
    # each tier separately and only the highest non-empty tier becomes the
    # ingredient's concept set. Process-word check filters Pickled/Smoked/
    # Scrambled etc. variants when the recipe didn't ask for them.
    out: dict[str, dict] = {it: {
        "p1_concepts": set(), "p1_sr28": set(), "p1_fndds": set(),
        "p2_concepts": set(), "p2_sr28": set(), "p2_fndds": set(),
        "p3_concepts": set(), "p3_sr28": set(), "p3_fndds": set(),
        "primary": primary_noun(it),
        "item_tokens": toks(it),
    } for it in items_filter}

    PROCESS_WORDS = {"pickled","smoked","scrambled","fried","candied","glazed",
                     "stuffed","breaded","battered","marinated","cured",
                     "deviled","salted","fermented","instant"}
    FORM_QUALIFIERS = {"seeds","seed","leaves","leaf","sprig","sprigs",
                       "bunch","bunches","threads","thread","flakes","flake",
                       "strips","sticks","stick","pieces","halves","wedges",
                       "slices","slice","cubes","cube","rounds","round","grains"}

    def norm(s: str) -> str:
        # Singular/plural normalisation for matching: strip trailing 's' from
        # nouns ('onion'/'onions' → 'onion'). Avoids "onion" missing PID='Onions'.
        if s.endswith("ies") and len(s) > 4:
            return s[:-3] + "y"
        if s.endswith("es") and len(s) > 3 and s[-3] in "sxz":
            return s[:-2]
        if s.endswith("s") and len(s) > 2 and not s.endswith("ss"):
            return s[:-1]
        return s

    with CONSENSUS_AUDIT.open() as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            pid = (r.get("product_identity_fixed") or "").strip()
            if not pid: continue
            canon = (r.get("canonical_path") or "").strip()
            if not canon: continue
            mod = (r.get("modifier") or "").strip().split(" > ")[0].strip()
            sr28 = (r.get("sr28_code") or "").strip()
            fndds = (r.get("fndds_code") or "").strip()
            pid_lc = pid.lower()
            pid_tokens_list = [t for t in WS.sub(" ", pid_lc).split()
                               if len(t) >= 2 and t not in STOP]
            pid_tokens = set(pid_tokens_list)
            pid_last = pid_tokens_list[-1] if pid_tokens_list else ""

            for it, info in out.items():
                primary = info["primary"]
                item_tokens = info["item_tokens"]
                concept = (canon, mod.lower()) if pid in RULE_B_PIDS else (canon, "")

                tier = None
                # P1: exact PID match (with singular/plural normalisation)
                if pid_lc == it or norm(pid_lc) == norm(it):
                    tier = "p1"
                # P2: primary noun is PID's last token; remaining tokens come
                # from the recipe; no process word leaks in (rejects 'eggs'
                # → 'Pickled Eggs').
                elif (primary and (primary == pid_last or norm(primary) == norm(pid_last))
                      and item_tokens.issubset(pid_tokens | {primary})
                      and not (pid_tokens - item_tokens) & PROCESS_WORDS):
                    tier = "p2"
                elif pid in RULE_B_PIDS and mod:
                    mod_lc = mod.lower()
                    mod_toks = toks(mod_lc)
                    if mod_lc == it:
                        tier = "p3"
                    elif mod_toks and mod_toks.issubset(item_tokens):
                        # Mod is a strict subset of item. Allow when the
                        # leftover tokens are pure form qualifiers
                        # ('cardamom seeds' minus 'cardamom' = {seeds}
                        # ⊆ form qualifiers) but reject when leftover is
                        # a real noun ('plain yogurt' minus 'plain' =
                        # {yogurt} which is NOT a form qualifier).
                        leftover = item_tokens - mod_toks
                        if not leftover or leftover.issubset(FORM_QUALIFIERS):
                            tier = "p3"

                if not tier: continue
                info[f"{tier}_concepts"].add(concept)
                if sr28 and sr28 != "0": info[f"{tier}_sr28"].add(sr28)
                if fndds and fndds != "0": info[f"{tier}_fndds"].add(fndds)

    # Collapse to highest non-empty tier
    final: dict[str, dict] = {}
    for it, info in out.items():
        for tier in ("p1", "p2", "p3"):
            if info[f"{tier}_concepts"]:
                final[it] = {
                    "concepts":    info[f"{tier}_concepts"],
                    "sr28_codes":  info[f"{tier}_sr28"],
                    "fndds_codes": info[f"{tier}_fndds"],
                    "primary":     info["primary"],
                    "item_tokens": info["item_tokens"],
                    "tier":        tier,
                }
                break
        else:
            final[it] = {
                "concepts": set(), "sr28_codes": set(), "fndds_codes": set(),
                "primary": info["primary"], "item_tokens": info["item_tokens"],
                "tier": None,
            }
    return final


# ── Load priced products. NO gf bucketing — single flat list. ───────────
def load_priced() -> list[dict]:
    con = sqlite3.connect(str(PRICED_DB))
    out: list[dict] = []
    for r in con.execute("""
        SELECT source, upc, name, brand, grams, cents,
               consensus_pid, consensus_canonical, consensus_modifier,
               bridge_status, non_food_path, htc_code, htc_group
        FROM priced_products
        WHERE marketplace = 0 AND available = 1
          AND grams > 0 AND cents > 0
          AND (non_food_path = 0 OR non_food_path IS NULL)
    """):
        src, upc, name, brand, g, c, cpid, ccan, cmod, bs, nfp, hc, hg = r
        if name and NON_FOOD_NAME.search(name):
            continue
        out.append({
            "source": src, "upc": upc, "name": name or "", "brand": brand or "",
            "name_tokens": toks(name or ""),
            "head_tokens": head_tokens(name or "", 2),
            "name_zone": name_zone(name or ""),
            "first_token": (name or "").split()[0].lower() if name else "",
            "grams": float(g), "cents": int(c),
            "cpg": float(c) / float(g) if g else 1e9,
            "htc_group": hg or "",
            "pid": cpid or "", "canonical": ccan or "",
            "modifier": (cmod or "").split(" > ")[0].strip(),
            "bridged": (bs == "bridged"),
        })
    return out


# ── Pick the cheapest priced product for an ingredient ─────────────────
def pick(item: str, blob: str, info: dict, all_priced: list[dict]) -> dict | None:
    if not info or (not info["concepts"] and not info["primary"]):
        return None
    primary = info["primary"]
    concepts = info["concepts"]
    form_prefixes = form_constraint(blob)

    def form_ok(canon: str) -> bool:
        if not form_prefixes:
            return True
        return any(canon.startswith(p) for p in form_prefixes)

    cands_a: list[dict] = []        # tree-concept matches
    cands_c: list[tuple[int, dict]] = []  # head-noun (noise, pkg)

    item_tokens = info["item_tokens"]
    qualifiers = item_tokens - {primary}

    for p in all_priced:
        # Tree concept match (Path A). Match on (canonical, modifier).
        if p["canonical"]:
            mod_for_concept = p["modifier"].lower() if p["pid"] in RULE_B_PIDS else ""
            concept = (p["canonical"], mod_for_concept)
            if concept in concepts and form_ok(p["canonical"]):
                cands_a.append(p)
                continue

        # Head-noun fallback (Path C) — strict.
        if p["bridged"]:
            continue
        if not primary or len(primary) < 3:
            continue
        if primary not in p["name_zone"]:
            continue
        if qualifiers and not (qualifiers & p["name_zone"]):
            continue
        # If the recipe has a form constraint, require name to honor it.
        if form_prefixes:
            name_lc = p["name"].lower()
            produce_blockers = ("dried","powder","powdered","paste","sauce",
                                "dip","seasoning","jar","cookie","cookies",
                                "cake","cakes","muffin","candy","candies",
                                "fudge","chocolate","gum","mint candy",
                                "ice cream","gelato","frosting","syrup",
                                "lozenge","mints","sparkling","punch","cocktail",
                                "extract","flavored","beverage")
            if "Produce >" in form_prefixes and any(w in name_lc for w in produce_blockers):
                continue
            if "Pantry >" in form_prefixes and "fresh" in name_lc and "produce" in name_lc:
                continue
        # Noise = name-zone tokens that are NOT recipe tokens AND NOT brand
        # noise. Topo Chico Sabores Lime with Mint Extra: zone has 'topo'
        # 'chico' 'sabores' 'lime' 'extra' as noise → 5; rejected vs Fresh
        # Organic Mint with noise 0.
        noise = p["name_zone"] - item_tokens - BRAND_NOISE
        if len(noise) > 2:
            continue
        cands_c.append((len(noise), p))

    if cands_a:
        cands_a.sort(key=lambda p: p["cpg"])
        return cands_a[0]
    if cands_c:
        # Rank by (noise, cpg) — prefer cleanest match, break ties by price
        cands_c.sort(key=lambda x: (x[0], x[1]["cpg"]))
        return cands_c[0][1]
    return None


def main() -> int:
    targets = ["Best Lemonade", "Low-Fat Berry Blue Frozen Dessert",
               "Chicken Biryani with Saffron", "Banana Bread"]
    chosen: dict[int, str] = {}
    test_items: set[str] = set()
    test_blobs: dict[str, str] = {}

    with LINES.open() as f:
        for r in csv.DictReader(f):
            t = r["recipe_title"]
            if any(tt.lower() in t.lower() for tt in targets) and t not in chosen.values():
                chosen[int(r["recipe_id"])] = t
                if len(chosen) >= 5:
                    break
    chosen_ids = set(chosen.keys())
    by_recipe: dict[int, list] = defaultdict(list)
    with LINES.open() as f:
        for r in csv.DictReader(f):
            try:
                rid = int(r["recipe_id"])
            except ValueError:
                continue
            if rid in chosen_ids:
                by_recipe[rid].append(r)
                it = r["ingredient_item"].lower()
                test_items.add(it)
                # Use the disp blob from the first occurrence
                test_blobs.setdefault(it, r.get("display") or "")

    print(f"loading consensus tree concepts for {len(test_items)} ingredients...")
    concepts = build_concepts(test_items)
    n_with = sum(1 for v in concepts.values() if v["concepts"])
    print(f"  {n_with}/{len(concepts)} ingredients have ≥1 tree concept")
    print(f"loading priced products (food only)...")
    all_priced = load_priced()
    print(f"  {len(all_priced):,} priced products")

    for rid, title in chosen.items():
        lines = by_recipe.get(rid, [])
        print(f"\n{'=' * 80}")
        print(f"  RECIPE #{rid}: {title}  ({len(lines)} lines)")
        print(f"  v6: cross-gf tree concepts | form filter | direct SR-28")
        print(f"{'=' * 80}")
        agg: dict[str, dict] = {}
        n_priced = 0
        for L in lines:
            item = L["ingredient_item"].lower()
            blob = L.get("display") or ""
            grams_raw = L.get("grams_resolved") or ""
            try:
                grams = float(grams_raw) if grams_raw else 0.0
            except ValueError:
                grams = 0.0
            if "saffron" in item and grams > SAFFRON_CAP_GRAMS:
                grams = SAFFRON_CAP_GRAMS

            info = concepts.get(item)
            pkg = pick(item, blob, info, all_priced) if info else None

            if not pkg or grams <= 0:
                sr28 = ", ".join(sorted(info["sr28_codes"])) if info and info["sr28_codes"] else "—"
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  [no priced match]  sr28={sr28}")
                continue

            key = pkg["upc"]
            if key not in agg:
                agg[key] = {"pkg": pkg, "need": 0, "lines": []}
            agg[key]["need"] += grams
            agg[key]["lines"].append((item, grams))
            n_priced += 1

        total_cents = 0
        for key, ag in agg.items():
            pkg = ag["pkg"]
            need = ag["need"]
            n_pkgs = max(1, math.ceil(need / pkg["grams"]))
            line_cost = n_pkgs * pkg["cents"]
            total_cents += line_cost
            items_str = " + ".join(f"{it} ({g:.0f}g)" for it, g in ag["lines"])
            tag = "★bridged" if pkg["bridged"] else "head-noun"
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
