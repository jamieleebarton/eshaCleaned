#!/usr/bin/env python3
"""Line-by-line recipe comparison: OURS vs HESTIA.

For each recipe in the input list, emits a CSV with:
  - recipe_id, recipe_name
  - line_index, ingredient_text (our display)
  - our_grams (grams_resolved from recipes_unified.csv)
  - our_canonical_path, our_htc_code, our_consensus_fndds, our_consensus_sr28
  - our_sku_picked, our_pkg_grams, our_pkg_cents, our_total_spend
  - hestia_fndds_code, fndds_name (from MainFoodDesc.csv), hestia_grams
  - hestia_sku_picked, hestia_pkg_grams, hestia_pkg_cents, hestia_total_spend
  - gram_diff, price_diff

Hestia line ↔ ours-line matching: best-effort by canonical_path keyword
overlap with FNDDS description token. (Both planners may aggregate
differently; this is a diagnostic, not a perfect match.)

Usage:
  python3 recipe_line_comparison.py --rids 309366,49508,492357 --out report.csv
  python3 recipe_line_comparison.py --plan-ours OUR.json --max 30 --out report.csv
"""
from __future__ import annotations
import argparse, ast, csv, json, math, sqlite3, sys, re
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[2]
OURS_DB    = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
HESTIA_DB  = Path("/Users/jamiebarton/Desktop/Hestia/api/data/food_packages_esha_shadow.db")
RECIPES2   = Path("/Users/jamiebarton/Desktop/Hestia/api/data/recipes2.csv")
UNIFIED    = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
TAXONOMY   = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
FNDDS_DESC = Path("/Users/jamiebarton/Desktop/Hestia/api/data/MainFoodDesc.csv")


def load_fndds_desc() -> dict[str, str]:
    """fndds_code → main_food_description"""
    out = {}
    with FNDDS_DESC.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            code = (row.get("Food code") or "").strip()
            desc = (row.get("Main food description") or "").strip()
            if code: out[code] = desc
    return out


def load_taxonomy_lookup() -> dict[str, dict]:
    """ingredient_item.lower() → {canonical_path, modifier, htc_code,
       consensus_fndds, consensus_sr28}"""
    out = {}
    with TAXONOMY.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            t = (row.get("title") or "").strip().lower()
            if not t: continue
            out[t] = {
                "canonical_path": (row.get("canonical_path") or "").strip(),
                "modifier":       (row.get("modifier") or "").strip(),
                "htc_code":       (row.get("htc_code") or "").lstrip("~").strip(),
                "consensus_fndds": "",
                "consensus_sr28":  "",
            }
    return out


def load_unified_rows(rids: set[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    titles = {}
    with UNIFIED.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            rid = row.get("recipe_id", "")
            if rid not in rids: continue
            try: g = float(row.get("grams_resolved") or 0)
            except: g = 0.0
            t = (row.get("recipe_title") or "").strip()
            if t and rid not in titles: titles[rid] = t
            out.setdefault(rid, []).append({
                "display": row.get("display", "")[:100],
                "ingredient_item": (row.get("ingredient_item") or "").strip().lower(),
                "grams": g,
                "htc_code": (row.get("htc_code") or "").lstrip("~").strip(),
            })
    return out, titles


def load_hestia_recipes(rids: set[str]) -> dict[str, dict]:
    out = {}
    with RECIPES2.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            rid = row.get("recipeNum", "")
            if rid not in rids: continue
            blob = row.get("fndds_grams_dict") or "{}"
            try: d = ast.literal_eval(blob) if isinstance(blob, str) else blob
            except: d = {}
            if not isinstance(d, dict): d = {}
            out[rid] = {
                "name": row.get("recipeName", ""),
                "fndds_grams": {str(k): float(v) for k, v in d.items() if v},
                "total_cost": row.get("total_estimated_cost", ""),
                "total_mass": row.get("total_mass_g", ""),
            }
    return out


def cheapest_total(packages: list[tuple], grams_needed: float):
    if not packages or grams_needed <= 0: return None
    def spend(p):
        c, g = p[0], p[1]
        if g <= 0: return 10**12
        return math.ceil(grams_needed / g) * c
    return min(packages, key=spend)


def preload_our_pools(con: sqlite3.Connection):
    """Returns (by_path_form, by_path) — dicts of pre-fetched pool lists.
    by_path_form: {(canonical_path, htc_form): [(cents, grams, name), ...]}
    by_path:      {canonical_path: [(cents, grams, name), ...]}

    No imposter filtering here — the canonical_path is authoritative.
    The reclassifier (recipe_pricing/reclassify_canonical_paths.py) ensures
    SKUs are at the right path; pepper jack lives at Pepper Jack, not at
    plain Cheese; cooking spray lives at Cooking Spray, not at Vegetable Oil.
    """
    cur = con.cursor()
    cur.execute("""SELECT consensus_canonical, REPLACE(htc_form_code,'~','') AS hf,
        cents, grams, name
        FROM priced_products WHERE available=1 AND grams>0 AND cents>0
        AND consensus_canonical IS NOT NULL AND consensus_canonical != ''""")
    by_path_form: dict = {}
    by_path: dict = {}
    for cp, hf, c, g, n in cur.fetchall():
        rec = (c, g, n or "")
        by_path_form.setdefault((cp, hf), []).append(rec)
        by_path.setdefault(cp, []).append(rec)
    return by_path_form, by_path


def preload_hestia_pools(hes: sqlite3.Connection):
    cur = hes.cursor()
    cur.execute("""SELECT fndds_code, package_weight_grams,
        COALESCE(walmart_price_cents, kroger_price_cents) AS cents,
        food_description FROM packages
        WHERE COALESCE(walmart_price_cents, kroger_price_cents) IS NOT NULL""")
    out: dict = {}
    for fndds, g, c, n in cur.fetchall():
        if not g or not c: continue
        out.setdefault(str(fndds), []).append((c, g, n or ""))
    return out


_PATH_ALIASES: dict[str, str] = {}
def _load_path_aliases() -> dict[str, str]:
    global _PATH_ALIASES
    if _PATH_ALIASES: return _PATH_ALIASES
    p = ROOT / "recipe_pricing" / "canonical_path_aliases.csv"
    if not p.exists(): return {}
    out = {}
    with p.open() as f:
        for row in csv.DictReader(f):
            old = (row.get("old_path") or "").strip()
            new = (row.get("new_path") or "").strip()
            if old and new and old != new:
                out[old] = new
    # Resolve transitive chains
    for k in list(out.keys()):
        seen = {k}
        v = out[k]
        while v in out and v not in seen:
            seen.add(v); v = out[v]
        out[k] = v
    _PATH_ALIASES = out
    return out


def our_pick_mem(by_path_form: dict, by_path: dict, canonical_path: str,
                  htc_form: str, grams_needed: float):
    if not canonical_path or grams_needed <= 0: return None
    # Apply alias map
    aliases = _load_path_aliases()
    if canonical_path in aliases:
        canonical_path = aliases[canonical_path]
    rows = by_path_form.get((canonical_path, htc_form))
    if not rows:
        rows = by_path.get(canonical_path)
    if not rows: return None
    pick = cheapest_total(rows, grams_needed)
    if not pick: return None
    cents, g, name = pick
    return {"name": (name or "")[:60], "pkg_grams": round(g, 0),
            "pkg_cents": cents, "spend": math.ceil(grams_needed / g) * cents,
            "pool": len(rows)}


def hestia_pick_mem(by_fndds: dict, fndds: str, grams_needed: float):
    if not fndds or grams_needed <= 0: return None
    rows = by_fndds.get(fndds)
    if not rows: return None
    pick = cheapest_total(rows, grams_needed)
    if not pick: return None
    cents, g, name = pick
    return {"name": (name or "")[:60], "pkg_grams": round(g, 0),
            "pkg_cents": cents, "spend": math.ceil(grams_needed / g) * cents,
            "pool": len(rows)}


def find_hestia_match(line: dict, fndds_dict: dict[str, float],
                       fndds_desc: dict[str, str]) -> tuple[str, float] | None:
    """Best-effort match an our-side line to a Hestia FNDDS code.
    Use canonical_path leaf token + display token overlap."""
    if not fndds_dict: return None
    nl = line["display"].lower()
    item_tokens = set(re.findall(r"[a-z]+", line["ingredient_item"]))
    best = None; best_score = 0
    for fndds, grams in fndds_dict.items():
        desc = fndds_desc.get(fndds, "").lower()
        if not desc: continue
        desc_tokens = set(re.findall(r"[a-z]+", desc))
        score = len(item_tokens & desc_tokens)
        if score > best_score:
            best = (fndds, grams); best_score = score
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rids", help="comma-separated recipe IDs")
    ap.add_argument("--plan-ours", help="our planner JSON")
    ap.add_argument("--all", action="store_true",
                     help="all recipes that have data on BOTH sides")
    ap.add_argument("--max", type=int, default=0, help="cap recipes (0 = no cap)")
    ap.add_argument("--out", default="planner/data/recipe_line_comparison.csv")
    ap.add_argument("--summary-out", default="planner/data/recipe_line_comparison_summary.csv",
                     help="per-recipe rollup CSV")
    args = ap.parse_args()

    if args.rids:
        rids = set(args.rids.split(","))
    elif args.plan_ours:
        plan = json.load(open(args.plan_ours))
        rids = set()
        for w in plan["weeks"]: rids.update(str(r) for r in w["recipe_ids"])
        if args.max: rids = set(list(rids)[:args.max])
    elif args.all:
        # Pull every recipe id that has a row in BOTH recipes2.csv and recipes_unified.csv
        print("scanning all recipes…", file=sys.stderr)
        rids_unified = set()
        with UNIFIED.open(encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                rid = row.get("recipe_id", "")
                if rid: rids_unified.add(rid)
        rids_hes = set()
        with RECIPES2.open(encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                rid = row.get("recipeNum", "")
                if rid: rids_hes.add(rid)
        rids = rids_unified & rids_hes
        print(f"  unified={len(rids_unified):,}  hestia={len(rids_hes):,}  intersection={len(rids):,}",
              file=sys.stderr)
        if args.max:
            rids = set(list(sorted(rids))[:args.max])
    else:
        ap.error("--rids, --plan-ours, or --all required")

    print(f"comparing {len(rids)} recipes…", file=sys.stderr)
    fndds_desc = load_fndds_desc()
    print(f"  {len(fndds_desc)} FNDDS descriptions", file=sys.stderr)
    taxonomy = load_taxonomy_lookup()
    print(f"  {len(taxonomy)} taxonomy lookups", file=sys.stderr)
    our_recipes, titles = load_unified_rows(rids)
    print(f"  {len(our_recipes)} recipes from unified", file=sys.stderr)
    hes_recipes = load_hestia_recipes(rids)
    print(f"  {len(hes_recipes)} recipes from recipes2", file=sys.stderr)

    print("preloading priced_products into memory…", file=sys.stderr)
    own = sqlite3.connect(str(OURS_DB))
    by_path_form, by_path = preload_our_pools(own)
    own.close()
    print(f"  by_path_form: {len(by_path_form):,} keys; by_path: {len(by_path):,} keys",
          file=sys.stderr)
    print("preloading hestia food_packages into memory…", file=sys.stderr)
    hes = sqlite3.connect(str(HESTIA_DB))
    by_fndds = preload_hestia_pools(hes)
    hes.close()
    print(f"  by_fndds: {len(by_fndds):,} keys", file=sys.stderr)

    # Output CSV
    out_path = ROOT / args.out if not args.out.startswith("/") else Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["recipe_id","recipe_name","line_idx","ingredient_text",
            "our_grams","hestia_fndds","fndds_desc","hestia_grams",
            "gram_diff","gram_ratio",
            "our_canonical_path","our_htc","our_modifier",
            "our_sku","our_pkg_g","our_pkg_$","our_spend",
            "our_pool",
            "hestia_sku","hes_pkg_g","hes_pkg_$","hes_spend","hes_pool",
            "spend_diff"]
    summary_rows: list[dict] = []
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        n_recipes_processed = 0
        for rid in rids:
            our_lines = our_recipes.get(rid, [])
            h = hes_recipes.get(rid, {"name":"","fndds_grams":{}})
            n_recipes_processed += 1
            if n_recipes_processed % 5000 == 0:
                print(f"  {n_recipes_processed:,}/{len(rids):,} processed",
                      file=sys.stderr, flush=True)
            # Per-recipe rollup
            our_total_g = 0.0; hes_total_g = 0.0
            our_total_spend = 0; hes_total_spend = 0
            n_our_lines = 0; n_hes_lines = len(h["fndds_grams"])
            n_our_no_match = 0
            our_pool_sum = 0; hes_pool_sum = 0
            for i, line in enumerate(our_lines):
                tax = taxonomy.get(line["ingredient_item"], {})
                cp = tax.get("canonical_path", "")
                htc = line["htc_code"] or tax.get("htc_code", "")
                modifier = tax.get("modifier", "")
                op = our_pick_mem(by_path_form, by_path, cp, htc, line["grams"]) if cp else None
                # match to hestia line
                match = find_hestia_match(line, h["fndds_grams"], fndds_desc)
                if match:
                    fndds, h_grams = match
                    desc = fndds_desc.get(fndds, "")
                    hp = hestia_pick_mem(by_fndds, fndds, h_grams)
                else:
                    fndds = ""; h_grams = 0; desc = ""; hp = None
                gram_diff = line["grams"] - h_grams
                gram_ratio = (line["grams"] / h_grams) if h_grams > 0 else 0
                spend_diff = (op["spend"] if op else 0) - (hp["spend"] if hp else 0)
                w.writerow({
                    "recipe_id": rid, "recipe_name": (titles.get(rid) or h["name"])[:60],
                    "line_idx": i, "ingredient_text": line["display"],
                    "our_grams": round(line["grams"], 1),
                    "hestia_fndds": fndds, "fndds_desc": desc[:50],
                    "hestia_grams": round(h_grams, 1),
                    "gram_diff": round(gram_diff, 1),
                    "gram_ratio": round(gram_ratio, 2),
                    "our_canonical_path": cp[:50],
                    "our_htc": htc, "our_modifier": modifier[:25],
                    "our_sku": op["name"] if op else "(none)",
                    "our_pkg_g": op["pkg_grams"] if op else 0,
                    "our_pkg_$": round(op["pkg_cents"]/100, 2) if op else 0,
                    "our_spend": round(op["spend"]/100, 2) if op else 0,
                    "our_pool": op["pool"] if op else 0,
                    "hestia_sku": hp["name"] if hp else "(none)",
                    "hes_pkg_g": hp["pkg_grams"] if hp else 0,
                    "hes_pkg_$": round(hp["pkg_cents"]/100, 2) if hp else 0,
                    "hes_spend": round(hp["spend"]/100, 2) if hp else 0,
                    "hes_pool": hp["pool"] if hp else 0,
                    "spend_diff": round(spend_diff/100, 2),
                })
                n_our_lines += 1
                our_total_g += line["grams"]
                hes_total_g += h_grams
                our_total_spend += op["spend"] if op else 0
                hes_total_spend += hp["spend"] if hp else 0
                if not op or op.get("name", "(none)") == "(none)": n_our_no_match += 1
                our_pool_sum += op["pool"] if op else 0
                hes_pool_sum += hp["pool"] if hp else 0
            # Diagnostic flags — easy-to-spot patterns
            flags = []
            gtr = our_total_g / hes_total_g if hes_total_g > 0 else 0
            spend_diff = (our_total_spend - hes_total_spend) / 100
            our_pool_avg = our_pool_sum / max(1, n_our_lines)
            hes_pool_avg = hes_pool_sum / max(1, n_our_lines)
            if gtr > 2.0:               flags.append("GRAMS_2X_HIGH")
            elif 0 < gtr < 0.5:         flags.append("GRAMS_2X_LOW")
            if spend_diff > 10:         flags.append("WE_OVERPRICE")
            elif spend_diff < -10:      flags.append("WE_UNDERPRICE")
            if abs(n_our_lines - n_hes_lines) > 2: flags.append("LINE_COUNT_OFF")
            if n_our_no_match > 0:      flags.append("OUR_NO_MATCH")
            if our_pool_avg > 0 and hes_pool_avg > 0 and our_pool_avg < hes_pool_avg / 3:
                flags.append("POOL_TINY")
            if our_total_spend == 0 and hes_total_spend > 0:
                flags.append("OUR_NO_SPEND")
            # Per-recipe rollup row
            summary_rows.append({
                "recipe_id": rid,
                "recipe_name": (titles.get(rid) or h.get("name", ""))[:60],
                "n_our_lines": n_our_lines,
                "n_hes_lines": n_hes_lines,
                "line_diff": n_our_lines - n_hes_lines,
                "our_total_g": round(our_total_g, 0),
                "hes_total_g": round(hes_total_g, 0),
                "gram_total_diff": round(our_total_g - hes_total_g, 0),
                "gram_total_ratio": round(gtr, 2),
                "our_total_spend": round(our_total_spend / 100, 2),
                "hes_total_spend": round(hes_total_spend / 100, 2),
                "spend_total_diff": round(spend_diff, 2),
                "n_our_no_match": n_our_no_match,
                "our_pool_avg": round(our_pool_avg, 1),
                "hes_pool_avg": round(hes_pool_avg, 1),
                "flags": "|".join(flags),
            })

    # Write per-recipe summary CSV
    sum_path = ROOT / args.summary_out if not args.summary_out.startswith("/") else Path(args.summary_out)
    sum_path.parent.mkdir(parents=True, exist_ok=True)
    if summary_rows:
        with sum_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
            w.writeheader()
            for r in summary_rows: w.writerow(r)

    print(f"\n→ {out_path}  ({n_our_lines:,} lines? maybe more)", file=sys.stderr)
    print(f"→ {sum_path}  ({len(summary_rows):,} per-recipe summary)", file=sys.stderr)


if __name__ == "__main__":
    main()
