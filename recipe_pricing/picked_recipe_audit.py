#!/usr/bin/env python3
"""Picked-recipe audit — for every recipe the planner actually picked over
the 12-week horizon, simulate the package selection per ingredient and emit
a per-line audit row with sanity flags.

Inputs:
  /tmp/multi_week_ours_12w_marjoram.json  — list of picked recipe IDs
  planner/data/recipe_concept_grams.json  — recipe rid → {concept_key: grams}
  planner/data/concept_resolution.json    — recipe concept_key → priced concept_key
  planner/data/concept_index.json         — priced concept_key → packages
  recipe_mapper/v1/output/recipes_unified.csv  — original recipe text per line

Per-line columns:
  recipe_id, recipe_name, ingredient_text, grams, concept_key,
  resolution_tier, priced_concept_key, n_packages_in_pool,
  picked_sku, picked_sku_grams, picked_sku_cents, n_packs_to_buy,
  total_spend, leaf_token_match, flag_count, flags

Per-recipe summary:
  recipe_id, name, n_lines, total_grams, total_spend, n_flagged_lines

Flags emitted on each line:
  TINY_POOL          — concept has ≤2 packages (weak coverage)
  HUGE_GRAMS         — line wants >5kg of one ingredient (likely parser bug)
  HEAVY_PACK_COUNT   — needs >12 packages of the SKU to cover (cost outlier)
  SKU_NAME_OFF       — SKU name doesn't contain any path-leaf token
  RESOLVED_LOSSY     — resolution tier was form_only / parent_path_only
  NO_RESOLUTION      — no priced concept matched at all
  IMPOSTER_TOKEN     — SKU name contains imposter words (blend/imitation/etc.)

Usage:
  python3 recipe_pricing/picked_recipe_audit.py
"""
from __future__ import annotations
import csv, json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
PICKED_JSON = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/Users/jamiebarton/Desktop/esha_audit_bundle/audit_results/multi_week_ours_12w_v11.json")
RCG_JSON = ROOT / "planner" / "data" / "recipe_concept_grams.json"
CR_JSON = ROOT / "planner" / "data" / "concept_resolution.json"
CI_JSON = ROOT / "planner" / "data" / "concept_index.json"
UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
OUT_LINES = ROOT / "recipe_pricing" / "picked_recipe_audit_lines.csv"
OUT_RECIPES = ROOT / "recipe_pricing" / "picked_recipe_audit_recipes.csv"
OUT_FLAGS = ROOT / "recipe_pricing" / "picked_recipe_audit_flags.csv"

STOPWORDS = {"the","a","an","of","and","or","with","fresh","whole",
              "raw","organic","plain"}

IMPOSTER_TOKENS = ("imitation", "blend", "bouillon", "stock cube",
                    "cheese food", "cheese product")


def leaf_tokens(canonical_path: str) -> set[str]:
    if not canonical_path: return set()
    leaf = canonical_path.split(" > ")[-1].lower()
    return {t for t in re.findall(r"[a-z]+", leaf) if len(t) > 2 and t not in STOPWORDS}


def total_spend(grams_needed: float, sku_grams: float, sku_cents: int) -> tuple[int, int]:
    """Return (n_packs, total_cents) — how many whole packages to cover need."""
    if not sku_grams or sku_grams <= 0: return (0, 10**9)
    if grams_needed <= 0: return (1, sku_cents)
    n = max(1, math.ceil(grams_needed / sku_grams))
    return (n, n * sku_cents)


def cheapest_pick(packages: list[dict], grams_needed: float) -> dict | None:
    if not packages: return None
    best = None; best_spend = 10**12
    for p in packages:
        n_packs, spend = total_spend(grams_needed, p.get("grams", 0), p.get("cents", 0))
        if spend < best_spend:
            best_spend = spend
            best = (p, n_packs, spend)
    if not best: return None
    p, n_packs, spend = best
    return {**p, "_n_packs": n_packs, "_total_spend": spend}


def main():
    print("loading data…", file=sys.stderr)
    rcg = json.loads(RCG_JSON.read_text())["concept_grams"]
    cr = json.loads(CR_JSON.read_text())
    ci = json.loads(CI_JSON.read_text())
    print(f"  {len(rcg):,} recipes in concept_grams", file=sys.stderr)
    print(f"  {len(cr):,} concept resolutions", file=sys.stderr)
    print(f"  {len(ci):,} priced concept_keys", file=sys.stderr)

    # Picked recipes
    pj = json.loads(PICKED_JSON.read_text())
    picked: list[str] = []
    seen: set = set()
    for w in pj.get("weeks", []):
        for x in (w.get("recipe_ids") or []):
            s = str(x)
            if s not in seen:
                seen.add(s); picked.append(s)
    print(f"  {len(picked):,} unique picked recipe IDs", file=sys.stderr)

    # Map rid → recipe_title (and original text per ingredient)
    titles: dict[str, str] = {}
    rid_lines: dict[str, list[dict]] = defaultdict(list)
    pset = set(picked)
    print("loading recipes_unified for picked recipes…", file=sys.stderr)
    rows_seen = 0
    with UNIFIED.open() as f:
        r = csv.DictReader(f)
        for row in r:
            rows_seen += 1
            if rows_seen % 500_000 == 0:
                print(f"  {rows_seen:,} lines processed", file=sys.stderr)
            rid = row.get("recipe_id","")
            if rid not in pset: continue
            titles[rid] = row.get("recipe_title","")
            rid_lines[rid].append({
                "ingredient_item": (row.get("ingredient_item") or "").strip(),
                "display": (row.get("display") or "").strip(),
                "qty": row.get("qty",""),
                "unit": row.get("unit",""),
                "grams_resolved": row.get("grams_resolved",""),
                "htc_code": (row.get("htc_code") or "").strip(),
                "grams_source": row.get("grams_source",""),
            })
    print(f"  {sum(len(v) for v in rid_lines.values()):,} lines for picked recipes", file=sys.stderr)

    # Walk each picked recipe; for each concept the recipe uses, simulate pick
    line_rows = []
    recipe_summary = []
    flag_counts: Counter = Counter()
    flag_recipes: dict[str, set] = defaultdict(set)

    for rid in picked:
        cg = rcg.get(rid, {})
        title = titles.get(rid, "")
        n_lines = 0; total_grams = 0.0; total_cost = 0.0; n_flagged = 0
        for ck, grams in cg.items():
            n_lines += 1
            total_grams += grams
            cp, htc_form = ck.split("|", 1) if "|" in ck else (ck, "")
            res = cr.get(ck, {"tier": "NO_MATCH", "priced_key": None})
            tier = res.get("tier", "NO_MATCH")
            priced_key = res.get("priced_key")
            packages = []
            n_pool = 0
            picked_sku = ""; picked_g = 0; picked_c = 0; n_packs = 0; spend = 0
            leaf_match = False
            flags = []

            if not priced_key:
                flags.append("NO_RESOLUTION")
            else:
                concept = ci.get(priced_key, {})
                packages = concept.get("packages", []) or []
                n_pool = concept.get("n_skus_total", len(packages))
                if n_pool <= 2:
                    flags.append("TINY_POOL")
                pick = cheapest_pick(packages, grams)
                if pick:
                    picked_sku = pick.get("name","")[:60]
                    picked_g = pick.get("grams", 0)
                    picked_c = pick.get("cents", 0)
                    n_packs = pick.get("_n_packs", 0)
                    spend = pick.get("_total_spend", 0)
                    total_cost += spend / 100.0
                    # leaf token match
                    lt = leaf_tokens(cp)
                    nl = picked_sku.lower()
                    leaf_match = bool(lt) and any(t in nl for t in lt)
                    if not leaf_match and lt:
                        flags.append("SKU_NAME_OFF")
                    # imposter token
                    if any(t in nl for t in IMPOSTER_TOKENS):
                        flags.append("IMPOSTER_TOKEN")
                    # heavy pack count
                    if n_packs >= 12:
                        flags.append("HEAVY_PACK_COUNT")

            # gram sanity
            if grams > 5000:
                flags.append("HUGE_GRAMS")
            # lossy resolution
            if tier in ("form_only", "parent_path_only", "path_only"):
                flags.append("RESOLVED_LOSSY")

            if flags: n_flagged += 1
            for fl in flags:
                flag_counts[fl] += 1
                flag_recipes[fl].add(rid)

            line_rows.append({
                "recipe_id": rid,
                "recipe_name": title[:50],
                "concept_key": ck,
                "canonical_path": cp,
                "htc_form": htc_form,
                "grams_needed": round(grams, 1),
                "resolution_tier": tier,
                "priced_concept_key": priced_key or "",
                "n_pool": n_pool,
                "picked_sku": picked_sku,
                "picked_sku_grams": round(picked_g, 1),
                "picked_sku_cents": picked_c,
                "n_packs": n_packs,
                "total_spend_$": round(spend / 100.0, 2),
                "leaf_match": int(leaf_match),
                "flags": "|".join(flags),
            })

        recipe_summary.append({
            "recipe_id": rid,
            "name": title[:60],
            "n_concepts": n_lines,
            "total_grams": round(total_grams, 0),
            "total_spend_$": round(total_cost, 2),
            "n_flagged_lines": n_flagged,
        })

    # Write outputs
    OUT_LINES.parent.mkdir(parents=True, exist_ok=True)
    if line_rows:
        with OUT_LINES.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(line_rows[0].keys()))
            w.writeheader()
            for r in line_rows: w.writerow(r)

    if recipe_summary:
        with OUT_RECIPES.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(recipe_summary[0].keys()))
            w.writeheader()
            for r in sorted(recipe_summary, key=lambda x: -x["n_flagged_lines"]):
                w.writerow(r)

    # Flag rollup
    flag_rows = []
    for fl, n in flag_counts.most_common():
        n_recipes = len(flag_recipes[fl])
        flag_rows.append({"flag": fl, "n_lines": n, "n_recipes": n_recipes})
    if flag_rows:
        with OUT_FLAGS.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(flag_rows[0].keys()))
            w.writeheader()
            for r in flag_rows: w.writerow(r)

    # Print summary
    print(f"\n{len(line_rows):,} ingredient-line audits across {len(picked):,} recipes",
          file=sys.stderr)
    n_flagged_lines = sum(1 for r in line_rows if r["flags"])
    print(f"  flagged lines: {n_flagged_lines:,}  ({n_flagged_lines*100/max(1,len(line_rows)):.1f}%)",
          file=sys.stderr)
    print(f"\nFlag distribution:", file=sys.stderr)
    for r in flag_rows:
        print(f"  {r['flag']:<22}  {r['n_lines']:>4} lines  ({r['n_recipes']:>3} recipes)",
              file=sys.stderr)
    print(f"\n→ {OUT_LINES}", file=sys.stderr)
    print(f"→ {OUT_RECIPES}", file=sys.stderr)
    print(f"→ {OUT_FLAGS}", file=sys.stderr)


if __name__ == "__main__":
    main()
