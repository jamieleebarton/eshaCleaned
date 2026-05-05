#!/usr/bin/env python3
"""V4 — Cost calc using consensus PID (not raw Walmart titles).

The fix that ends sunflower-seeds-as-cardamom:
  Match recipe ingredient → consensus PID → priced products with same PID.
  No more matching on Walmart title tokens that are full of marketing noise.

Per recipe ingredient line:
  1. Recipe item → HTC code → set of consensus PIDs that legitimately
     represent that food (via consensus rows where HTC + pid token-overlap).
     For 'cardamom seeds', valid PIDs are {'Cardamom', 'Spice Blend' with
     modifier=Cardamom, ...} — never {'Sunflower Seeds'}.
  2. Filter priced_products to: htc_group matches AND consensus_pid IN
     valid_pids AND marketplace=0 AND available=1.
  3. For priced products NOT bridged to consensus (~80%), apply head-noun
     fallback: recipe item must equal the LAST 1-2 word of product name
     (so 'Sugar' matches 'Granulated Sugar', not 'Sugar Tonic Bottle').
  4. Cheapest cents-per-gram wins; full-package cost.
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
CON_TAGS = HERE / "output" / "consensus_htc_tagged.csv"

WS = re.compile(r"[^a-z0-9 ]+")
STOP = {"the","of","and","with","a","an","to","in","fresh","frozen","raw",
        "ground","whole","large","medium","small","extra","lean","low","fat",
        "free","organic","natural","chopped","diced","minced","sliced",
        "boneless","skinless","grade","brand"}


def toks(s: str) -> set[str]:
    s = WS.sub(" ", (s or "").lower())
    return {t for t in s.split() if len(t) >= 2 and t not in STOP}


def head_tokens(s: str) -> set[str]:
    """Last 2 word-tokens of a product name (the 'head noun')."""
    s = WS.sub(" ", (s or "").lower())
    parts = [t for t in s.split() if len(t) >= 2 and t not in STOP]
    return set(parts[-2:]) if parts else set()


def primary_noun(item: str) -> str:
    """The last meaningful token of a recipe item ('ripe bananas' → 'bananas',
    'lemon juice' → 'juice', 'baking soda' → 'soda'). For ingredients where
    the noun is hidden by adjectives like 'ripe', this is the head we want
    to require in any matched product."""
    parts = [t for t in WS.sub(" ", (item or "").lower()).split()
             if len(t) >= 2 and t not in STOP]
    return parts[-1] if parts else ""


# ── Step 1: build the per-ingredient set of valid consensus PIDs ─────────
def build_ingredient_to_valid_pids() -> dict[str, dict]:
    """For each recipe ingredient, find the set of consensus PIDs that
    legitimately match (via HTC + pid token-overlap)."""
    ing_htc = {}
    with ING_TAGS.open() as f:
        for r in csv.DictReader(f):
            ing_htc[r["item"].lower()] = (r["htc_code"], r["htc_group"])

    by_htc: dict[str, set[str]] = defaultdict(set)
    pid_freq: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    with CON_TAGS.open() as f:
        for r in csv.DictReader(f):
            pid = (r.get("product_identity_fixed") or "").strip()
            if pid:
                by_htc[r["htc_code"]].add(pid)
                pid_freq[r["htc_code"]][pid] += 1

    out: dict[str, dict] = {}
    for item, (code, grp) in ing_htc.items():
        item_tokens = toks(item)
        if not item_tokens or not code:
            continue
        valid_exact = set()
        valid_all = set()
        valid_partial = set()
        for pid in by_htc.get(code, []):
            pid_lc = pid.lower()
            pid_tokens = toks(pid_lc)
            if not pid_tokens:
                continue
            if pid_lc == item:
                valid_exact.add(pid)
            elif item_tokens.issubset(pid_tokens) or pid_tokens.issubset(item_tokens):
                # all recipe tokens appear in pid (or vice-versa for very short pids)
                valid_all.add(pid)
            elif item_tokens & pid_tokens:
                valid_partial.add(pid)
        # tier hierarchy: exact > all-tokens-in > partial overlap
        if valid_exact:
            valid = valid_exact
        elif valid_all:
            valid = valid_all
        else:
            # only fall back to partial if it's narrow (just 1-2 candidates)
            valid = valid_partial if len(valid_partial) <= 2 else set()
        out[item] = {
            "htc_code": code,
            "htc_group": grp,
            "valid_pids": valid,
            "item_tokens": item_tokens,
            "primary_noun": next(iter(reversed(
                [t for t in WS.sub(" ", item.lower()).split()
                 if len(t) >= 2 and t not in STOP])), ""),
        }
    return out


def load_priced_indexed_by_pid() -> tuple[dict, dict]:
    """Load priced_products. Build two indexes:
       - by_pid_group[(consensus_pid_lower, htc_group)] = list of priced products
       - by_group[htc_group] = list (for un-bridged fallback)"""
    con = sqlite3.connect(str(PRICED_DB))
    by_pid_group: dict[tuple, list[dict]] = defaultdict(list)
    by_group: dict[str, list[dict]] = defaultdict(list)
    for r in con.execute("""
        SELECT source, upc, name, brand, grams, cents, htc_code, htc_group,
               consensus_pid, consensus_canonical, bridge_status
        FROM priced_products
        WHERE marketplace = 0 AND available = 1
          AND grams > 0 AND cents > 0
          AND htc_group NOT IN ('0','N')
    """):
        src, upc, name, brand, g, c, hc, hg, cpid, ccan, bs = r
        rec = {
            "source": src, "upc": upc, "name": name or "", "brand": brand or "",
            "name_tokens": toks(name or ""),
            "head_tokens": head_tokens(name or ""),
            "grams": float(g), "cents": int(c),
            "cpg": float(c) / float(g) if g else 1e9,
            "htc": hc or "", "htc_group": hg or "",
            "pid": cpid or "", "canonical": ccan or "",
            "bridged": bs == "bridged",
        }
        by_group[hg].append(rec)
        if cpid:
            by_pid_group[(cpid.lower(), hg)].append(rec)
    return dict(by_pid_group), dict(by_group)


# ── Step 2: pick the best match per ingredient ─────────────────────────
def pick_cheapest(item: str, info: dict, by_pid_group: dict, by_group: dict) -> dict | None:
    grp = info["htc_group"]
    if grp in ("", "0", "N"):
        return None
    item_tokens = info["item_tokens"]
    valid_pids = info["valid_pids"]

    candidates = []
    # Path A: bridged products with matching consensus PID — strongest signal
    seen = set()
    for pid in valid_pids:
        for p in by_pid_group.get((pid.lower(), grp), []):
            seen.add(p["upc"])
            score = 10.0
            candidates.append((score, p))

    # Path B: un-bridged products with head-noun match — runs alongside A
    # so we can compare by cents-per-gram across both populations.
    primary = info.get("primary_noun", "")
    for p in by_group.get(grp, []):
        if p["upc"] in seen:
            continue
        if p["bridged"]:
            # bridged but not in valid_pids — skip; the consensus says NO
            continue
        # The recipe's PRIMARY NOUN must be the product's head noun.
        # Kills: 'ripe bananas' → 'Ripe Avocado' (primary=bananas, not in head),
        #        'lemon juice' → 'Apple Juice Drink' (primary=juice present BUT
        #          we also require lemon/apple to NOT be on a different fruit).
        if primary and primary not in p["head_tokens"]:
            continue
        inter = item_tokens & p["head_tokens"]
        if not inter:
            continue
        # If the recipe has a qualifier (lemon, baking, ripe), require that
        # qualifier appear somewhere in the product name OR the qualifier is a
        # form/state stop-word we already filtered.
        qualifiers = item_tokens - {primary}
        if qualifiers:
            qualifier_in_name = bool(qualifiers & p["name_tokens"])
            if not qualifier_in_name:
                continue
        score = 5.0 + len(inter)
        candidates.append((score, p))

    if not candidates:
        return None
    # Both paths get to compete on cents-per-gram. Bridge bonus survives only
    # as a tiebreaker — the cheapest legitimate package wins.
    candidates.sort(key=lambda x: (x[1]["cpg"], -x[0]))
    return candidates[0][1]


# ── Driver ──────────────────────────────────────────────────────────────
def main() -> int:
    print("loading consensus PID lookup...")
    ing_to_pids = build_ingredient_to_valid_pids()
    print(f"  {len(ing_to_pids):,} recipe ingredients with valid consensus PIDs")
    print("loading priced products (indexed by PID)...")
    by_pid_group, by_group = load_priced_indexed_by_pid()
    n_priced = sum(len(v) for v in by_group.values())
    n_bridged = sum(len(v) for v in by_pid_group.values())
    print(f"  {n_priced:,} priced products  ({n_bridged:,} bridged to consensus PID)")
    print()

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
        print(f"  cost: PID-anchored via consensus, full-package")
        print(f"{'=' * 80}")
        agg: dict[str, dict] = {}
        n_priced_lines = 0
        for L in lines:
            item = L["ingredient_item"].lower()
            grams_raw = L.get("grams_resolved") or ""
            try:
                grams = float(grams_raw) if grams_raw else 0.0
            except ValueError:
                grams = 0.0
            info = ing_to_pids.get(item)
            pkg = pick_cheapest(item, info, by_pid_group, by_group) if info else None
            if not pkg or grams <= 0:
                pids = list(info["valid_pids"])[:3] if info else []
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  pids={pids}  [no priced match]")
                continue
            key = pkg["upc"]
            if key not in agg:
                agg[key] = {"pkg": pkg, "need": 0, "lines": []}
            agg[key]["need"] += grams
            agg[key]["lines"].append((item, grams))
            n_priced_lines += 1

        total_cents = 0
        for key, info in agg.items():
            pkg = info["pkg"]
            need = info["need"]
            n_pkgs = max(1, math.ceil(need / pkg["grams"]))
            line_cost = n_pkgs * pkg["cents"]
            leftover = n_pkgs * pkg["grams"] - need
            total_cents += line_cost
            items_str = " + ".join(f"{it} ({g:.0f}g)" for it, g in info["lines"])
            tag = "★bridged" if pkg["bridged"] else "head-noun"
            print(f"  {items_str[:60]:<60}  need {need:>5.0f}g")
            print(f"      → {n_pkgs}× [{pkg['name'][:40]:<40}] "
                  f"{pkg['grams']:>5.0f}g @ ${pkg['cents']/100:>5.2f}/{pkg['source']:<7} "
                  f"= ${line_cost/100:>6.2f}  [{tag}, pid={pkg['pid'] or '—'}]")

        print(f"  {'─' * 76}")
        print(f"  TOTAL ({n_priced_lines}/{len(lines)} lines priced, {len(agg)} packages): "
              f" ${total_cents/100:>7.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
