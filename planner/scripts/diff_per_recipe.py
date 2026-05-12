#!/usr/bin/env python3
"""For each of N random recipes, compare per-recipe values:

  HESTIA SIDE: pulled directly from recipes2.csv columns (FNDDS-derived):
    food_groups.vegetables_g, food_groups.fruit_g, food_groups.dairy_g,
    food_groups.grains_g, food_groups.protein_g
    calories_total_kcal, protein_total_g, fat_total_g, carbs_total_g

  OUR-DERIVED SIDE: computed via the OLD canonical_path heuristic from
  concept_index + recipe_concept_grams. (This is the heuristic we ABANDONED
  by overlaying recipes2.csv. Diffing here exposes how broken it was.)

Output: ranked list of recipes by absolute |Hestia - Ours| veg diff.
"""
from __future__ import annotations
import csv, json, random, sys
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[2]
RECIPES2 = Path("/Users/jamiebarton/Desktop/Hestia/api/data/recipes2.csv")
CI       = json.loads((ROOT/"planner"/"data"/"concept_index.json").read_text())
RCG      = json.loads((ROOT/"planner"/"data"/"recipe_concept_grams.json").read_text())
RES      = json.loads((ROOT/"planner"/"data"/"concept_resolution.json").read_text())

OUT = ROOT / "planner" / "data" / "per_recipe_diff.json"
SAMPLE = 300


def hestia_values(rid: int) -> dict | None:
    """Pull per-recipe FNDDS-derived values from recipes2.csv. (Slow scan but
    fine for 300 sample.)"""
    target = str(rid)
    with RECIPES2.open(encoding="utf-8", errors="replace") as f:
        r = csv.DictReader(f)
        for row in r:
            if (row.get("recipeNum") or "").strip() != target: continue
            def f0(k):
                v = row.get(k, "")
                try: return float(v) if v else 0.0
                except: return 0.0
            return {
                "rid": rid,
                "title": row.get("recipeName",""),
                "veg_g":     f0("food_groups.vegetables_g"),
                "fruit_g":   f0("food_groups.fruit_g"),
                "dairy_g":   f0("food_groups.dairy_g"),
                "grain_g":   f0("food_groups.grains_g"),
                "prot_g":    f0("food_groups.protein_g"),
                "kcal":      f0("calories_total_kcal"),
                "protein":   f0("protein_total_g"),
                "fat":       f0("fat_total_g"),
                "carb":      f0("carbs_total_g"),
                "fiber":     f0("fiber"),
                "sodium":    f0("sodium_total_mg") or f0("sodium"),
                "total_mass":f0("total_mass_g") or f0("totalMass"),
            }
    return None


def ours_derived(rid: int) -> dict:
    """Compute the same fields using ONLY our concept_index + concept_grams,
    via the canonical_path heuristic (the broken one we abandoned)."""
    grams = RCG.get("concept_grams", {}).get(str(rid), {})
    veg_g = fruit_g = dairy_g = grain_g = prot_g = 0.0
    kcal = prot = fat = carb = fiber = sodium = total_mass = 0.0
    for rk, g in grams.items():
        # Resolve recipe concept_key → priced concept_key
        r = RES.get(rk, {})
        pk = r.get("priced_key")
        c = CI.get(pk) if pk else None
        cp_low = (c["canonical_path"].lower() if c else rk.split("|",2)[0].lower())
        if "produce" in cp_low and ("vegetable" in cp_low or "salad" in cp_low or "herb" in cp_low):
            veg_g += g
        elif "produce" in cp_low and "fruit" in cp_low:
            fruit_g += g
        elif "dairy" in cp_low: dairy_g += g
        elif ("bakery" in cp_low or "flour" in cp_low or "rice" in cp_low or
               "pasta" in cp_low or "grain" in cp_low or "cereal" in cp_low): grain_g += g
        elif "meat" in cp_low or "seafood" in cp_low or "egg" in cp_low or "bean" in cp_low:
            prot_g += g
        total_mass += g
        if c and c["packages"]:
            pkg = c["packages"][0]
            cpg = pkg["cents"] / pkg["grams"]
            # No macro derivation here — would need to pull FNDDS/SR28 lookups
    return {
        "veg_g": veg_g, "fruit_g": fruit_g, "dairy_g": dairy_g,
        "grain_g": grain_g, "prot_g": prot_g, "total_mass": total_mass,
    }


def main():
    rng = random.Random(7)
    rids = rng.sample(list(int(x) for x in RCG["concept_grams"].keys()), SAMPLE)
    rows = []
    for rid in rids:
        h = hestia_values(rid)
        if not h: continue
        o = ours_derived(rid)
        rows.append({
            "rid": rid,
            "title": h["title"],
            "hestia_veg":   h["veg_g"],
            "ours_veg":     round(o["veg_g"],1),
            "veg_diff":     round(o["veg_g"] - h["veg_g"], 1),
            "hestia_fruit": h["fruit_g"],
            "ours_fruit":   round(o["fruit_g"],1),
            "fruit_diff":   round(o["fruit_g"] - h["fruit_g"], 1),
            "hestia_grain": h["grain_g"],
            "ours_grain":   round(o["grain_g"],1),
            "hestia_prot":  h["prot_g"],
            "ours_prot":    round(o["prot_g"],1),
            "hestia_mass":  h["total_mass"],
            "ours_mass":    round(o["total_mass"],1),
        })
    rows.sort(key=lambda r: -abs(r["veg_diff"]))

    print(f"{SAMPLE} recipes diffed (showing biggest veg discrepancies)")
    print(f"{'rid':<8} {'title':<35} {'hestia_v':>8} {'our_v':>7} {'diff':>7} | {'h_mass':>7} {'o_mass':>7}")
    over = 0; under = 0; equal = 0
    for r in rows[:30]:
        print(f"  {r['rid']:<6} {r['title'][:33]:<35} {r['hestia_veg']:>8.0f} {r['ours_veg']:>7.0f} {r['veg_diff']:>+7.0f} | {r['hestia_mass']:>7.0f} {r['ours_mass']:>7.0f}")
    for r in rows:
        if abs(r["veg_diff"]) < 5: equal += 1
        elif r["veg_diff"] > 0: over += 1
        else: under += 1

    print(f"\nover-counted by ours:  {over}")
    print(f"under-counted by ours: {under}")
    print(f"effectively equal:     {equal}")

    OUT.write_text(json.dumps(rows, indent=2))
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
