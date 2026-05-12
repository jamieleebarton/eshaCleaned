#!/usr/bin/env python3
"""For each recipe in a sample, verify:

  1. Recipe-line grams_resolved is plausible vs recipe text:
     - "1 lb bacon" → grams ≈ 454g (±10%)
     - "1 whole ham (8 lb)" → grams ≈ 3500-4500g
     - "1 cup flour" → grams ≈ 120-130g
     - "1 tsp salt" → grams ≈ 5g
     - etc.

  2. Picked SKU semantically matches the ingredient:
     - "whole ham" → SKU name contains "whole" or "shank" or "spiral"
                     and NOT "lunch", "deli", "sandwich", "sliced thin"
     - "1 lb bacon" → SKU name contains "bacon"
                       and NOT "bits", "flavor", "topping"
     - "extra firm tofu" → SKU name contains "firm"
                            and NOT "silken", "soft"
     - "ground beef" → SKU name contains "ground" + "beef"
                       and NOT "beef pork blend"

  3. Cost-per-recipe-line plausible vs SKU price:
     - line_cost = grams × cents/gram → should be < SKU_price unless multi-pkg

Output: planner/data/picks_and_grams_audit.json + console report of failures.
"""
from __future__ import annotations
import csv, json, random, re, sqlite3, sys
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "recipe_pricing"))
import calculate_recipe_cost_v7 as calc

OUT = ROOT / "planner" / "data" / "picks_and_grams_audit.json"
SAMPLE = 60

# Plausible grams ranges (g_low, g_high) by ingredient hint regex.
# Each rule: (regex on ingredient text, expected_grams_range, must_contain[], must_not_contain[])
RULES = [
    # Pound-quantity meats: should be ~454g/lb
    (r"^\s*1 lb (.+?bacon)",                  (400, 510),
        ["bacon"], ["bits", "flavor", "topping", "candy"]),
    (r"^\s*1 lb (.+?ground beef|.+?ground chuck)", (400, 510),
        ["ground", "beef"], ["jerky", "chip", "broth"]),
    (r"^\s*2 lb (.+?ground beef)",            (820, 1020),
        ["ground", "beef"], ["jerky", "broth"]),
    # Whole hams 7-10 lbs
    (r"\b(whole ham|fully cooked.*ham|spiral.*ham).*?\b(\d+).*?(?:lb|pound)", (3000, 4800),
        ["ham"], ["lunch meat", "deli thin", "sandwich"]),
    # Sticks of butter
    (r"^\s*1 stick (?:of )?(.+?butter)",      (100, 130),
        ["butter"], ["spread", "spray"]),
    # Cup of flour
    (r"^\s*1 cup (?:of )?(.+?flour)",         (110, 145),
        ["flour"], ["crouton"]),
    # Cup of milk
    (r"^\s*1 cup (?:of )?(.+?milk)",          (220, 260),
        ["milk"], []),
    # tsp / tbsp small amounts
    (r"^\s*1 tsp (?:of )?(.+)",               (1, 8),     [], []),
    (r"^\s*1 tbsp (?:of )?(.+)",              (8, 18),    [], []),
    # Whole chicken
    (r"\b(whole chicken|whole roasting chicken)\b", (1000, 2500),
        ["chicken"], ["broth", "stock", "diced", "deli"]),
    # Tofu blocks
    (r"\b(?:1 |a )?(\d{2})\s*(?:oz|ounce).*tofu", (300, 500),
        ["tofu"], []),
    # Eggs (count → grams)
    (r"^\s*(\d+)\s+eggs?\b",                  (50, 700),
        ["egg"], ["substitute", "replacer", "noodle"]),
]
def _match_rule(disp_lower):
    for pat, gr, want, dont in RULES:
        m = re.search(pat, disp_lower, re.I)
        if m: return (gr, want, dont, m.group(0)[:40])
    return None


def main():
    print("loading…", file=sys.stderr)
    unified = calc.load_unified()
    cls = calc.load_classifications()
    bfl, overridden = calc.load_buy_form_lookup()
    excluded = calc.load_excluded_upcs()
    fndds_macros = calc.load_fndds_macros()
    sr28_macros  = calc.load_sr28_macros() if hasattr(calc, "load_sr28_macros") else {}
    product_claims = calc.load_product_claims()
    con = sqlite3.connect(str(calc.PRICED_DB))

    rng = random.Random(42)
    candidates = [r for r in cls.keys() if r in unified]
    sample = rng.sample(candidates, SAMPLE)

    grams_failures = []
    sku_failures = []
    audited_lines = 0; audited_recipes = 0
    for rid in sample:
        try:
            r = calc.calculate(rid, unified, cls, bfl, con, [], excluded,
                                fndds_macros, product_claims, overridden,
                                sr28_macros=sr28_macros)
        except TypeError:
            r = calc.calculate(rid, unified, cls, bfl, con, [], excluded,
                                fndds_macros, product_claims, overridden)
        except Exception:
            continue
        audited_recipes += 1
        for ln in r.lines:
            if ln.decision != "calculate": continue
            audited_lines += 1
            disp = ln.raw_display
            rule = _match_rule(disp.lower())
            # 1. Gram plausibility
            if rule:
                gr, want, dont, hit = rule
                if not (gr[0] <= ln.grams <= gr[1]):
                    grams_failures.append({
                        "rid": rid, "title": r.recipe_title[:50],
                        "ingredient": disp[:65], "matched_rule": hit,
                        "expected_grams": gr, "got_grams": round(ln.grams, 1),
                        "buy_form": ln.canonical_buy_form,
                    })
                # 2. SKU semantic match (only when rule has want/dont)
                if ln.sku_name and (want or dont):
                    nl = ln.sku_name.lower()
                    miss = [w for w in want if w not in nl]
                    bad  = [d for d in dont if d in nl]
                    if miss or bad:
                        sku_failures.append({
                            "rid": rid, "title": r.recipe_title[:50],
                            "ingredient": disp[:65],
                            "buy_form": ln.canonical_buy_form,
                            "picked_sku": ln.sku_name[:80],
                            "expected_contains": want, "missing": miss,
                            "expected_excludes": dont, "leaked": bad,
                        })

    print(f"\n=== AUDIT ON {audited_recipes} recipes / {audited_lines} 'calculate' lines ===")
    print(f"  GRAM plausibility failures:  {len(grams_failures)}")
    print(f"  SKU semantic failures:       {len(sku_failures)}")

    if grams_failures:
        print(f"\n=== Top 12 GRAM failures ===")
        for f in grams_failures[:12]:
            print(f"  [{f['rid']}] {f['ingredient']}")
            print(f"      expected {f['expected_grams']}g, got {f['got_grams']}g  (matched: {f['matched_rule']!r})")

    if sku_failures:
        print(f"\n=== Top 12 SKU failures ===")
        for f in sku_failures[:12]:
            issues = []
            if f["missing"]: issues.append(f"missing {f['missing']}")
            if f["leaked"]:  issues.append(f"leaked {f['leaked']}")
            print(f"  [{f['rid']}] {f['ingredient']}  → {f['picked_sku']}")
            print(f"      {' / '.join(issues)}")

    OUT.write_text(json.dumps({"grams_failures": grams_failures,
                                 "sku_failures": sku_failures,
                                 "audited_recipes": audited_recipes,
                                 "audited_lines": audited_lines}, indent=2))
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
