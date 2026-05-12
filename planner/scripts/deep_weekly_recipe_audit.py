#!/usr/bin/env python3
"""Deep per-week, per-recipe, per-ingredient-line audit.

Reads the 12-week plan output and tears apart every recipe line:
- Is the ingredient being purchased?
- Are the grams plausible for the qty/unit?
- Is the resolved SKU semantically the right food?
- Are there missing ingredients (NO_MATCH)?

Outputs: planner/data/deep_weekly_audit.md  (human readable)
         planner/data/deep_weekly_audit.json (machine readable)
"""
from __future__ import annotations
import csv, json, re, sys
from pathlib import Path
from collections import defaultdict

csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "planner" / "data"
OUT_MD = ROOT / "planner" / "data" / "deep_weekly_audit.md"
OUT_JSON = ROOT / "planner" / "data" / "deep_weekly_audit.json"

PLAN_PATH = Path("/tmp/multi_week_ours_12w_round14c.json")
RECIPES_UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
HTC_TAGGED = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_htc_tagged.csv"
RESOLUTION = DATA / "concept_resolution.json"
INDEX = DATA / "concept_index.json"

# ---- plausible gram heuristics (low, high) by unit regex -----------------
GRAM_RULES = [
    # (regex on display text, expected grams low/high, explanation)
    (r"^\s*1\s+cup\s+(?:of\s+)?(?:all.purpose\s+)?flour", 110, 145, "1 cup flour ≈ 120-130g"),
    (r"^\s*1\s+cup\s+(?:of\s+)?(?:white\s+)?(?:granulated\s+)?sugar", 190, 220, "1 cup sugar ≈ 200g"),
    (r"^\s*1\s+cup\s+(?:of\s+)?(?:brown\s+)?sugar", 200, 240, "1 cup brown sugar ≈ 220g"),
    (r"^\s*1\s+cup\s+(?:of\s+)?milk", 220, 260, "1 cup milk ≈ 244g"),
    (r"^\s*1\s+cup\s+(?:of\s+)?(?:heavy\s+)?cream", 220, 260, "1 cup cream ≈ 240g"),
    (r"^\s*1\s+cup\s+(?:of\s+)?water", 220, 260, "1 cup water ≈ 237g"),
    (r"^\s*1\s+cup\s+(?:of\s+)?(?:dry\s+)?rice", 180, 220, "1 cup dry rice ≈ 200g"),
    (r"^\s*1\s+cup\s+(?:of\s+)?oats", 80, 110, "1 cup oats ≈ 90g"),
    (r"^\s*1\s+cup\s+(?:of\s+)?cheese", 100, 140, "1 cup shredded cheese ≈ 120g"),
    (r"^\s*1\s+cup\s+(?:of\s+)?butter", 220, 240, "1 cup butter ≈ 227g"),
    (r"^\s*1\s+tbsp\s+(?:of\s+)?(?:all.purpose\s+)?flour", 6, 10, "1 tbsp flour ≈ 8g"),
    (r"^\s*1\s+tbsp\s+(?:of\s+)?(?:white\s+)?(?:granulated\s+)?sugar", 12, 16, "1 tbsp sugar ≈ 12.5g"),
    (r"^\s*1\s+tbsp\s+(?:of\s+)?butter", 12, 16, "1 tbsp butter ≈ 14g"),
    (r"^\s*1\s+tbsp\s+(?:of\s+)?oil", 12, 16, "1 tbsp oil ≈ 14g"),
    (r"^\s*1\s+tsp\s+(?:of\s+)?salt", 4, 8, "1 tsp salt ≈ 5.7g"),
    (r"^\s*1\s+tsp\s+(?:of\s+)?(?:vanilla\s+)?extract", 4, 6, "1 tsp extract ≈ 4.3g"),
    (r"^\s*1\s+tsp\s+(?:of\s+)?(?:dried\s+)?(?:ground\s+)?(?:spice|powder|cinnamon|nutmeg|ginger|cumin|paprika|chili|garlic|onion)", 2, 6, "1 tsp ground spice ≈ 2-3g"),
    (r"^\s*1\s+lb\s+(?:of\s+)?", 430, 500, "1 lb ≈ 454g"),
    (r"^\s*2\s+lb\s+(?:of\s+)?", 860, 1000, "2 lb ≈ 907g"),
    (r"^\s*1\s+oz\s+(?:of\s+)?", 25, 32, "1 oz ≈ 28g"),
    (r"^\s*1\s+stick\s+(?:of\s+)?butter", 100, 130, "1 stick butter ≈ 113g"),
    (r"^\s*1\s+egg\b", 45, 65, "1 large egg ≈ 50g"),
    (r"^\s*2\s+eggs?\b", 90, 130, "2 eggs ≈ 100g"),
    (r"^\s*3\s+eggs?\b", 135, 195, "3 eggs ≈ 150g"),
    (r"^\s*1\s+clove\s+(?:of\s+)?garlic", 3, 8, "1 garlic clove ≈ 5g"),
    (r"^\s*2\s+cloves?\s+(?:of\s+)?garlic", 6, 16, "2 garlic cloves ≈ 10g"),
]

# ---- SKU semantic checks --------------------------------------------------
# (regex on ingredient_item or display, must_contain_tokens, must_not_contain_tokens, explanation)
SKU_RULES = [
    (r"bacon", ["bacon"], ["bits", "flavor", "topping", "chip", "jerky"], "bacon should not be bits/flavor/topping"),
    (r"ground\s+beef", ["ground", "beef"], ["jerky", "chip", "broth", "stew"], "ground beef must be ground beef"),
    (r"whole\s+ham", ["ham"], ["lunch", "deli", "sandwich", "slice"], "whole ham should not be lunchmeat"),
    (r"extra\s+firm\s+tofu", ["firm"], ["silken", "soft"], "extra firm tofu must be firm"),
    (r"silken\s+tofu", ["silken", "soft"], ["firm", "extra firm"], "silken tofu must be soft"),
    (r"olive\s+oil", ["olive"], ["mayonnaise", "topping", "spray"], "olive oil must be olive oil"),
    (r"vegetable\s+oil", ["oil"], ["mayonnaise", "topping", "spray", "olive"], "vegetable oil must be oil, not mayo"),
    (r"butter(?![\w\s]*spray)", ["butter"], ["spray", "flavor", "sauce"], "butter should not be spray or flavor"),
    (r"cheddar", ["cheddar"], [], "cheddar must say cheddar"),
    (r"swiss\s+cheese", ["swiss"], [], "swiss cheese must say swiss"),
    (r"parmesan", ["parmesan"], ["romano", "mixed"], "parmesan should not be mixed"),
    (r"heavy\s+cream", ["heavy", "cream"], ["half", "coffee", "whipped"], "heavy cream should not be half-and-half"),
    (r"half.and.half", ["half"], ["heavy", "whipped"], "half-and-half is not heavy cream"),
    (r"chicken\s+breast", ["chicken", "breast"], ["wing", "thigh", "whole", "broth", "stock"], "chicken breast should not be other cuts"),
    (r"chicken\s+thigh", ["chicken", "thigh"], ["breast", "wing", "whole", "broth"], "chicken thigh should not be other cuts"),
    (r"salmon", ["salmon"], ["tuna", "trout", "mackerel"], "salmon must be salmon"),
    (r"shrimp", ["shrimp"], ["crab", "lobster", "fish"], "shrimp must be shrimp"),
    (r"basil", ["basil"], ["mrs.meyer", "cleaner", "candle"], "basil should not be cleaner/candle"),
    (r"cilantro", ["cilantro"], ["soap"], "cilantro must be cilantro"),
    (r"lemon\s+(?!pepper|juice|extract)", ["lemon"], ["frozen", "drink", "splash", "citrus"], "fresh lemon should not be frozen or drink"),
    (r"lime\s+(?!juice|extract)", ["lime"], ["drink", "splash", "citrus", "soda"], "fresh lime should not be drink/soda"),
    (r"celery", ["celery"], ["salt", "seed", "juice"], "celery should not be salt/seed/juice"),
    (r"jalapeño", ["jalape"], ["pickled", "chip", "snack"], "jalapeño should not be pickled chips"),
    (r"nutmeg", ["nutmeg"], ["all.purpose", "seasoning", "blend"], "nutmeg should not be all-purpose seasoning"),
    (r"cumin", ["cumin"], ["seasoning", "blend", "taco"], "cumin should not be a blend"),
    (r"chili\s+powder", ["chili"], ["sauce", "paste"], "chili powder should not be sauce/paste"),
    (r"hot\s+sauce", ["hot"], ["soda", "drink", "candy"], "hot sauce should not be drink/candy"),
    (r"soy\s+sauce", ["soy"], ["soda", "drink"], "soy sauce should not be drink"),
    (r"rice\s+wine\s+vinegar", ["vinegar"], ["wine", "beverage", "drink"], "rice wine vinegar should not be beverage wine"),
    (r"bread\s+crumbs", ["bread", "crumb"], ["cracker", "chip"], "bread crumbs should not be crackers/chips"),
    (r"elbow\s+macaroni", ["elbow", "macaroni"], ["penne", "rotini", "shell"], "elbow macaroni must be elbow"),
    (r"spaghetti", ["spaghetti"], ["sauce", "meatball", "helper"], "spaghetti should not be sauce/helper"),
    (r"andouille", ["andouille"], ["chorizo", "kielbasa", "bratwurst"], "andouille must be andouille"),
    (r"chorizo", ["chorizo"], ["andouille", "kielbasa"], "chorizo must be chorizo"),
    (r"water\b(?!\s*melon)", ["water"], ["flavor", "sparkling", "mineral", "soda"], "water should be plain water"),
]


def load_plan(path: Path):
    return json.loads(path.read_text())


def load_recipes_unified(path: Path):
    """recipe_id -> list of row dicts"""
    by_rid = defaultdict(list)
    with path.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            by_rid[row["recipe_id"]].append(row)
    return by_rid


def load_item_to_canonical(path: Path) -> dict:
    """ingredient_item -> canonical_path from htc_tagged."""
    out = {}
    with path.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            out[row["item"]] = row.get("canonical_path", "")
    return out


def load_resolution(path: Path):
    return json.loads(path.read_text())


def load_index(path: Path):
    return json.loads(path.read_text())


def check_grams(display: str, grams: float):
    """Return (ok, expected_range, explanation) or None if no rule matches."""
    dl = display.lower()
    for pat, low, high, expl in GRAM_RULES:
        if re.search(pat, dl, re.I):
            if low <= grams <= high:
                return True, (low, high), expl
            else:
                return False, (low, high), expl
    return None


def check_sku(display: str, item: str, sku_name: str):
    """Return list of (ok, explanation) or empty if no rule matches."""
    if not sku_name:
        return []
    text = f"{display} {item}".lower()
    issues = []
    for pat, want, dont, expl in SKU_RULES:
        if re.search(pat, text, re.I):
            nl = sku_name.lower()
            miss = [w for w in want if w not in nl]
            bad = [d for d in dont if d in nl]
            if miss or bad:
                issues.append((False, expl, miss, bad))
            else:
                issues.append((True, expl, [], []))
    return issues


def get_resolution_for_line(row: dict, resolution: dict, item_to_cp: dict):
    """Build concept key from row and look up resolution."""
    item = row.get("ingredient_item", "")
    cp = item_to_cp.get(item, "")
    hfc = row.get("htc_code", "")
    # Try exact
    ck = f"{cp}|{hfc}"
    if ck in resolution:
        return resolution[ck]
    # Fallback: htc_form
    hfc2 = row.get("htc_form", "")
    if hfc2 and hfc2 != hfc:
        ck2 = f"{cp}|{hfc2}"
        if ck2 in resolution:
            return resolution[ck2]
    return None


def get_sku_for_resolution(res: dict, index: dict):
    """Given resolution result, return first package from concept_index."""
    if not res:
        return None
    pk = res.get("priced_key")
    if not pk or pk not in index:
        return None
    pkgs = index[pk].get("packages", [])
    if not pkgs:
        return None
    return pkgs[0]


def main():
    print("Loading data…", file=sys.stderr)
    plan = load_plan(PLAN_PATH)
    recipes = load_recipes_unified(RECIPES_UNIFIED)
    item_to_cp = load_item_to_canonical(HTC_TAGGED)
    resolution = load_resolution(RESOLUTION)
    index = load_index(INDEX)

    weeks = plan.get("weeks", [])
    all_issues = []

    md = ["# Deep Weekly Recipe Audit\n"]
    md.append(f"Plan: {PLAN_PATH.name} | {plan.get('config', {})}\n")
    md.append(f"Total weeks: {len(weeks)} | Unique recipes: {plan['totals']['total_unique_recipes']}\n")

    total_lines_audited = 0
    total_no_match = 0
    total_gram_fail = 0
    total_sku_fail = 0
    total_missing_sku = 0

    for wk in weeks:
        wn = wk["week"]
        md.append(f"\n---\n\n## Week {wn} — ${wk['cost']:.2f} amortized · {wk['n_recipes']} recipes\n")
        md.append("### Recipes:\n")
        for rid in wk.get("recipe_ids", []):
            name = ""
            for n in wk.get("recipe_names", []):
                if n.startswith(f"r{rid}:") or n.startswith(f"r{rid} "):
                    name = n
                    break
            if not name:
                name = f"r{rid}"
            md.append(f"- {name}\n")

        week_issues = []
        week_lines = 0
        week_no_match = 0
        week_gram_fail = 0
        week_sku_fail = 0
        week_missing = 0

        for rid in wk.get("recipe_ids", []):
            rid_str = str(rid)
            lines = recipes.get(rid_str, [])
            if not lines:
                continue
            title = lines[0].get("recipe_title", "")
            recipe_issues = []

            for row in lines:
                week_lines += 1
                total_lines_audited += 1
                display = row.get("display", "")
                item = row.get("ingredient_item", "")
                qty = row.get("qty", "")
                unit = row.get("unit", "")
                grams = row.get("grams_resolved", "")
                try:
                    grams_f = float(grams) if grams else 0.0
                except ValueError:
                    grams_f = 0.0

                res = get_resolution_for_line(row, resolution, item_to_cp)
                sku = get_sku_for_resolution(res, index) if res else None
                sku_name = sku.get("name", "") if sku else ""

                issues_on_line = []

                # 1. NO_MATCH / missing SKU
                if not res:
                    issues_on_line.append(("NO_MATCH", "Concept has no resolution entry"))
                    week_no_match += 1
                    total_no_match += 1
                elif res.get("tier") == "no_match":
                    issues_on_line.append(("NO_MATCH", f"Resolution tier = no_match (priced_key={res.get('priced_key')})"))
                    week_no_match += 1
                    total_no_match += 1
                elif not sku:
                    issues_on_line.append(("MISSING_SKU", f"Resolved to {res.get('priced_key')!r} but no packages in index"))
                    week_missing += 1
                    total_missing_sku += 1

                # 2. Gram plausibility
                if grams_f > 0:
                    gram_check = check_grams(display, grams_f)
                    if gram_check is not None:
                        ok, (low, high), expl = gram_check
                        if not ok:
                            issues_on_line.append(("GRAM_FAIL", f"{expl}: expected {low}-{high}g, got {grams_f:.1f}g"))
                            week_gram_fail += 1
                            total_gram_fail += 1
                else:
                    issues_on_line.append(("ZERO_GRAMS", "grams_resolved is 0 or empty"))

                # 3. SKU semantic match
                if sku_name:
                    sku_checks = check_sku(display, item, sku_name)
                    for ok, expl, miss, bad in sku_checks:
                        if not ok:
                            detail = expl
                            if miss:
                                detail += f" (missing tokens: {miss})"
                            if bad:
                                detail += f" (forbidden tokens: {bad})"
                            issues_on_line.append(("SKU_FAIL", detail))
                            week_sku_fail += 1
                            total_sku_fail += 1

                if issues_on_line:
                    recipe_issues.append({
                        "display": display,
                        "item": item,
                        "qty": qty,
                        "unit": unit,
                        "grams": grams_f,
                        "resolution_tier": res.get("tier") if res else None,
                        "priced_key": res.get("priced_key") if res else None,
                        "sku_name": sku_name,
                        "issues": issues_on_line,
                    })

            if recipe_issues:
                week_issues.append({
                    "recipe_id": rid,
                    "title": title,
                    "lines": recipe_issues,
                })

        # Week summary in markdown
        md.append(f"\n**Audit:** {week_lines} lines scanned | "
                    f"{week_no_match} NO_MATCH | {week_missing} missing SKU | "
                    f"{week_gram_fail} gram failures | {week_sku_fail} SKU mismatches\n")

        if week_issues:
            md.append("\n### ⚠️ Flagged recipes\n\n")
            for ri in week_issues:
                md.append(f"#### r{ri['recipe_id']} — {ri['title']}\n")
                md.append("| ingredient | qty | unit | grams | tier | SKU | flags |\n")
                md.append("|---|---|---|---|---|---|---|\n")
                for ln in ri["lines"]:
                    flags = "; ".join(f"**{t}**: {d}" for t, d in ln["issues"])
                    md.append(f"| {ln['display'][:55]} | {ln['qty']} | {ln['unit']} | {ln['grams']:.1f} | "
                               f"{ln['resolution_tier'] or '—'} | {ln['sku_name'][:40] or '—'} | {flags} |\n")
                md.append("\n")
        else:
            md.append("\n✅ No flagged lines this week.\n")

        all_issues.append({
            "week": wn,
            "lines_scanned": week_lines,
            "no_match": week_no_match,
            "missing_sku": week_missing,
            "gram_failures": week_gram_fail,
            "sku_failures": week_sku_fail,
            "flagged_recipes": week_issues,
        })

    # Global summary
    # Insert summary right after the header
    md.insert(3, f"\n## Summary\n")
    md.insert(4, f"- **Total lines audited:** {total_lines_audited}\n")
    md.insert(5, f"- **NO_MATCH:** {total_no_match} ({100*total_no_match/max(1,total_lines_audited):.1f}%)\n")
    md.insert(6, f"- **Missing SKU (resolved but no package):** {total_missing_sku}\n")
    md.insert(7, f"- **Gram plausibility failures:** {total_gram_fail}\n")
    md.insert(8, f"- **SKU semantic failures:** {total_sku_fail}\n")

    OUT_MD.write_text("".join(md))
    OUT_JSON.write_text(json.dumps({
        "plan": plan.get("config"),
        "totals": {
            "lines_audited": total_lines_audited,
            "no_match": total_no_match,
            "missing_sku": total_missing_sku,
            "gram_failures": total_gram_fail,
            "sku_failures": total_sku_fail,
        },
        "weeks": all_issues,
    }, indent=2))

    print(f"\n=== DEEP WEEKLY AUDIT COMPLETE ===")
    print(f"  Lines audited:      {total_lines_audited}")
    print(f"  NO_MATCH:           {total_no_match} ({100*total_no_match/max(1,total_lines_audited):.1f}%)")
    print(f"  Missing SKU:        {total_missing_sku}")
    print(f"  Gram failures:      {total_gram_fail}")
    print(f"  SKU mismatches:     {total_sku_fail}")
    print(f"\n→ {OUT_MD}")
    print(f"→ {OUT_JSON}")


if __name__ == "__main__":
    main()
