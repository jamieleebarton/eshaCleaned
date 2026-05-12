#!/usr/bin/env python3
"""Picked-recipe audit v2 — joins our planner's pick simulation with Hestia's
per-line FNDDS attribution and gram totals from FULL_v7.

Adds these columns vs v1:
  hestia_fndds        — Hestia's FNDDS code for the line
  hestia_fndds_desc   — short FNDDS description
  hestia_grams        — Hestia's parsed grams for the same recipe-text line
  gram_ratio          — our_grams / hestia_grams
  hestia_sku          — Hestia's picked SKU at her packages DB
  hestia_spend_$      — Hestia's package spend
  spend_diff_$        — our_total_spend − hestia_spend (positive = we paid more)
  ingredient_text     — raw recipe display text (proves what the recipe asked for)

The v1 audit was structured per-concept (one row per concept_key). Here we
join by ingredient_text (raw recipe text) so the user sees the actual
recipe line being audited.

Also adds a `verdict` column with concrete bug labels:
  WRONG_FORM    — picked SKU is a different food form (spray for liquid)
  WRONG_FLAVOR  — picked SKU has a flavor recipe didn't ask for (jalapeno cheese)
  WRONG_PREP    — picked SKU is prepared/cooked when recipe wants raw
  EXTRACT_LEAK  — Pantry generic with extract htc_form, picked random extract
  GRAM_DIVERGE  — gram_ratio outside [0.5, 2]
  COVERAGE      — no SKU at all (NO_RESOLUTION in v1)
  CONFIRM       — picked SKU looks correct
"""
from __future__ import annotations
import csv, json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
PICKED_JSON = Path("/tmp/multi_week_ours_12w_marjoram.json")
LINES_V7 = ROOT / "planner" / "data" / "recipe_line_comparison_FULL_v7.csv"
RCG_JSON = ROOT / "planner" / "data" / "recipe_concept_grams.json"
CR_JSON = ROOT / "planner" / "data" / "concept_resolution.json"
CI_JSON = ROOT / "planner" / "data" / "concept_index.json"
OUT_LINES = ROOT / "recipe_pricing" / "picked_recipe_audit_v2.csv"
OUT_VERDICTS = ROOT / "recipe_pricing" / "picked_recipe_audit_v2_verdicts.csv"

STOPWORDS = {"the","a","an","of","and","or","with","fresh","whole","raw","organic","plain"}

# Form/flavor token rules — when picked SKU has these tokens AND recipe text doesn't
WRONG_FORM_TOKENS = ("spray", " mix ", "powder", " mush", "ready to serve", "fully cooked",
                      "instant ", "concentrate", "imitation", "imposter")
FLAVOR_TOKENS_AT_CHEESE = ("jalapeno", "habanero", "pepper jack", "smoked",
                            "pepperjack", "chipotle", "smoke flavor")
FLAVOR_TOKENS_AT_OIL = ("garlic", "infused", "spray", "butter flavor")
SEASONED_TOKENS_AT_BREADCRUMBS = ("seasoned", "panko", "italian", "garlic")
PREP_TOKENS_AT_RAW = ("mush", "cooked", "ready to serve", "fully cooked")


def leaf_tokens(canonical_path: str) -> set[str]:
    if not canonical_path: return set()
    leaf = canonical_path.split(" > ")[-1].lower()
    return {t for t in re.findall(r"[a-z]+", leaf) if len(t) > 2 and t not in STOPWORDS}


def total_spend(grams_needed: float, sku_grams: float, sku_cents: int) -> tuple[int, int]:
    if not sku_grams or sku_grams <= 0: return (0, 10**9)
    if grams_needed <= 0: return (1, sku_cents)
    n = max(1, math.ceil(grams_needed / sku_grams))
    return (n, n * sku_cents)


def cheapest_pick(packages: list[dict], grams_needed: float):
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


def classify(text: str, our_path: str, sku_name: str, hestia_grams: float,
              our_grams: float, tier: str) -> tuple[str, str]:
    """Return (verdict, evidence)."""
    nl = sku_name.lower()
    tl = text.lower()
    cp = our_path.lower()

    if not sku_name or sku_name == "(none)":
        return "COVERAGE", "no SKU at all"

    # Wrong form: spray for oil, etc.
    if "spray" in nl and "oil" in cp and "spray" not in tl:
        return "WRONG_FORM", "picked spray when recipe wants liquid oil"
    if "mix" in nl and "mix" not in tl and our_grams > 50:
        return "WRONG_FORM", "picked dry mix when recipe wants larger quantity"
    if any(t in nl for t in PREP_TOKENS_AT_RAW) and "mush" in nl and "mush" not in tl:
        return "WRONG_PREP", "picked prepared mush when recipe wants raw"

    # Wrong flavor at cheese path
    if "cheese" in cp:
        for t in FLAVOR_TOKENS_AT_CHEESE:
            if t in nl and t not in tl:
                return "WRONG_FLAVOR", f"picked {t} cheese, recipe didn't ask"

    # Seasoned at breadcrumbs
    if "breadcrumb" in cp:
        for t in SEASONED_TOKENS_AT_BREADCRUMBS:
            if t in nl and t not in tl:
                return "WRONG_FLAVOR", f"picked {t} breadcrumbs, recipe wants plain"

    # Extract leak — generic Pantry path picking specific extract
    if cp.strip() == "pantry" and "extract" in nl and "extract" not in tl:
        return "EXTRACT_LEAK", "generic Pantry path picked random extract"

    # Gram divergence
    if our_grams > 0 and hestia_grams > 0:
        ratio = our_grams / hestia_grams
        if ratio > 2.0 or ratio < 0.5:
            return "GRAM_DIVERGE", f"our={our_grams:.0f}g hes={hestia_grams:.0f}g"

    return "CONFIRM", ""


def main():
    print("loading data…", file=sys.stderr)
    rcg = json.loads(RCG_JSON.read_text())["concept_grams"]
    cr = json.loads(CR_JSON.read_text())
    ci = json.loads(CI_JSON.read_text())

    pj = json.loads(PICKED_JSON.read_text())
    picked: list[str] = []
    seen: set = set()
    for w in pj.get("weeks", []):
        for x in (w.get("recipe_ids") or []):
            s = str(x)
            if s not in seen:
                seen.add(s); picked.append(s)
    pset = set(picked)
    print(f"  {len(picked):,} picked recipes", file=sys.stderr)

    # Load FULL_v7 line CSV for the picked recipes
    print("loading FULL_v7 line data…", file=sys.stderr)
    line_data: dict[str, list[dict]] = defaultdict(list)
    with LINES_V7.open() as f:
        r = csv.DictReader(f)
        for row in r:
            rid = row.get("recipe_id","")
            if rid in pset:
                line_data[rid].append(row)
    n_lines = sum(len(v) for v in line_data.values())
    print(f"  {n_lines:,} lines for picked recipes from FULL_v7", file=sys.stderr)

    # Per-line audit: each row in line_data gets simulated picker output
    out_rows = []
    verdict_counts: Counter = Counter()
    verdict_recipes: dict[str, set] = defaultdict(set)
    verdict_samples: dict[str, list] = defaultdict(list)

    for rid in picked:
        title = ""
        for ln in line_data.get(rid, []):
            title = ln.get("recipe_name","")
            text = ln.get("ingredient_text","")
            try: og = float(ln.get("our_grams") or 0)
            except: og = 0
            try: hg = float(ln.get("hestia_grams") or 0)
            except: hg = 0
            our_path = ln.get("our_canonical_path","") or ""
            hes_fndds = ln.get("hestia_fndds","") or ""
            fndds_desc = ln.get("fndds_desc","") or ""
            hes_sku = ln.get("hestia_sku","") or ""
            try: hes_spend = float(ln.get("hes_spend") or 0)
            except: hes_spend = 0

            # Resolve to priced concept_key via concept_grams (the planner's actual data flow)
            # concept_grams stores grams keyed by recipe-side concept_key; need to find
            # the matching one for THIS line. Since we don't have htc_form on the line
            # CSV, we use the canonical_path + the recipe's overall concept_grams
            cg = rcg.get(rid, {})
            # Find a concept_key whose canonical_path matches our_path
            ck_match = None
            for ck in cg:
                if ck.split("|", 1)[0] == our_path:
                    ck_match = ck; break
            if ck_match is None:
                # No matching concept — skip simulation
                tier = "NO_CONCEPT"
                priced_key = ""
                picked_sku = ""
                picked_g = 0; picked_c = 0; n_packs = 0; spend = 0
            else:
                res = cr.get(ck_match, {})
                tier = res.get("tier", "NO_MATCH")
                priced_key = res.get("priced_key") or ""
                if priced_key and priced_key in ci:
                    pkgs = ci[priced_key].get("packages", []) or []
                    pick = cheapest_pick(pkgs, og)
                    if pick:
                        picked_sku = pick.get("name","")[:60]
                        picked_g = pick.get("grams", 0)
                        picked_c = pick.get("cents", 0)
                        n_packs = pick.get("_n_packs", 0)
                        spend = pick.get("_total_spend", 0)
                    else:
                        picked_sku = ""; picked_g = 0; picked_c = 0; n_packs = 0; spend = 0
                else:
                    picked_sku = ""; picked_g = 0; picked_c = 0; n_packs = 0; spend = 0

            verdict, evidence = classify(text, our_path, picked_sku, hg, og, tier)
            verdict_counts[verdict] += 1
            verdict_recipes[verdict].add(rid)
            if verdict != "CONFIRM" and len(verdict_samples[verdict]) < 12:
                verdict_samples[verdict].append(
                    f"r{rid} '{text[:50]}' → {picked_sku[:40]} ({evidence})")

            out_rows.append({
                "recipe_id": rid,
                "recipe_name": title[:50],
                "ingredient_text": text[:80],
                "our_grams": round(og, 0),
                "hestia_grams": round(hg, 0),
                "gram_ratio": round(og/hg, 2) if hg > 0 else 0,
                "our_canonical_path": our_path[:50],
                "hestia_fndds": hes_fndds,
                "hestia_fndds_desc": fndds_desc[:30],
                "resolution_tier": tier,
                "priced_concept_key": priced_key[:60],
                "picked_sku": picked_sku,
                "picked_sku_grams": round(picked_g, 0),
                "n_packs": n_packs,
                "our_spend_$": round(spend / 100.0, 2),
                "hestia_sku": hes_sku[:40],
                "hestia_spend_$": round(hes_spend, 2),
                "spend_diff_$": round((spend / 100.0) - hes_spend, 2),
                "verdict": verdict,
                "evidence": evidence,
            })

    OUT_LINES.parent.mkdir(parents=True, exist_ok=True)
    if out_rows:
        with OUT_LINES.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            for r in out_rows: w.writerow(r)

    # Verdict rollup
    verd_rows = []
    print(f"\n{len(out_rows):,} line audits across {len(picked):,} picked recipes", file=sys.stderr)
    print(f"\nVerdict distribution:", file=sys.stderr)
    for v, n in verdict_counts.most_common():
        nr = len(verdict_recipes[v])
        print(f"  {v:<14}  {n:>5} lines  ({nr:>3} recipes)", file=sys.stderr)
        verd_rows.append({"verdict": v, "n_lines": n, "n_recipes": nr,
                           "samples": " | ".join(verdict_samples[v][:5])})

    if verd_rows:
        with OUT_VERDICTS.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(verd_rows[0].keys()))
            w.writeheader()
            for r in verd_rows: w.writerow(r)

    print(f"\n→ {OUT_LINES}", file=sys.stderr)
    print(f"→ {OUT_VERDICTS}", file=sys.stderr)


if __name__ == "__main__":
    main()
