#!/usr/bin/env python3
"""R13.0 — HTC Coverage Audit. The simple end-to-end check.

Concept-key keyed (canonical_path|htc_form) — that's how the planner
indexes recipes. For each concept, verify:
  (a) Volume      — n_recipe_lines + n_recipes that use it
  (b) Determinism — most-common (item,qty,unit) yields a single modal gram
                     covering ≥99% of lines? (else flag drift)
  (c) Bridge      — htc_code → fdc_id → SR28 round-trip
  (d) Pick        — what does the resolver return; cheapest SKU; does it
                     contain a leaf-stem (sanity check)?
  (e) Verdict     — green / yellow / red

Output:
  recipe_pricing/htc_coverage_audit.csv
  recipe_pricing/htc_coverage_summary.txt
"""
from __future__ import annotations
import csv, json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
BRIDGE  = ROOT / "recipe_pricing" / "htc_to_fdc.csv"
RCG = ROOT / "planner" / "data" / "recipe_concept_grams.json"
CR  = ROOT / "planner" / "data" / "concept_resolution.json"
CI  = ROOT / "planner" / "data" / "concept_index.json"

OUT_CSV = ROOT / "recipe_pricing" / "htc_coverage_audit.csv"
OUT_TXT = ROOT / "recipe_pricing" / "htc_coverage_summary.txt"

STOP = {"the","a","an","of","and","or","with","fresh","raw","organic","plain",
        "whole","ground","style","flavor","grade","brand","food","mix"}


def stem(t: str) -> str:
    if len(t) <= 3: return t
    if t.endswith("ies") and len(t) > 4: return t[:-3] + "y"
    if t.endswith("oes") and len(t) > 4: return t[:-2]
    if t.endswith("es")  and len(t) > 3 and not t.endswith("ses"): return t[:-2]
    if t.endswith("s")   and not t.endswith("ss"): return t[:-1]
    return t


def leaf_stems(cp: str) -> set[str]:
    leaf = (cp.split(" > ")[-1] if cp else "").lower()
    return {stem(t) for t in re.findall(r"[a-z]+", leaf)
             if len(t) > 2 and t not in STOP}


def name_has_any_stem(name: str, target_stems: set[str]) -> bool:
    if not name or not target_stems: return False
    nl = name.lower()
    nl = re.sub(r"[^a-z0-9 -]", " ", nl)
    nl_stems = {stem(t) for t in nl.split() if len(t) > 2}
    return bool(target_stems & nl_stems)


def cheapest(packages: list, grams_needed: float = 100):
    if not packages: return None
    best = None; bs = 10**12
    for p in packages:
        g = p.get("grams", 0); c = p.get("cents", 0)
        if g <= 0: continue
        n = max(1, math.ceil(grams_needed / g))
        s = n * c
        if s < bs: bs = s; best = p
    return best


def main():
    print("loading data…", file=sys.stderr)
    cr = json.loads(CR.read_text())
    ci = json.loads(CI.read_text())
    rcg = json.loads(RCG.read_text())["concept_grams"]

    # 1) Recipe volume per concept_key
    n_recipes_per_ck: Counter = Counter()
    grams_per_ck: Counter = Counter()
    for rid, d in rcg.items():
        for ck, g in d.items():
            n_recipes_per_ck[ck] += 1
            grams_per_ck[ck] += g
    print(f"  concept_keys recipes use: {len(n_recipes_per_ck):,}", file=sys.stderr)

    # 2) Bridge round-trip — htc_form_code → fdc → sr_desc
    bridge: dict = {}
    with BRIDGE.open() as f:
        for row in csv.DictReader(f):
            h = (row.get("htc_code") or "").strip()
            if h: bridge[h] = {
                "fdc_id": row.get("fdc_id",""),
                "sr_description": row.get("sr_description","")[:50],
            }

    # 3) Per-concept gram determinism. Walk recipes_unified, group by
    #    (cp, htc_form) → (item, qty, unit) → grams. We use the htc_code
    #    column from recipes_unified. The htc_form derived from htc_form_code
    #    column. cp NOT in recipes_unified — pull from concept_index by
    #    matching htc_code as htc_form (best we have).
    print("  scanning recipes_unified for determinism…", file=sys.stderr)
    # Map cp candidate from htc_code → set of cps observed in recipes
    htc_code_to_cps: dict = defaultdict(Counter)
    grams_by_tuple: dict = defaultdict(Counter)
    htc_top_tuple: dict = defaultdict(Counter)
    htc_top_item: dict = defaultdict(Counter)
    with RECIPES.open() as f:
        for n_rows, row in enumerate(csv.DictReader(f)):
            if n_rows % 1000000 == 0 and n_rows:
                print(f"    {n_rows:,} rows…", file=sys.stderr)
            h = (row.get("htc_code") or "").strip().lstrip("~")
            if not h: continue
            try: q = float(row.get("qty") or 0)
            except: continue
            try: g = float(row.get("grams_resolved") or 0)
            except: continue
            u = (row.get("unit") or "").lower().strip()
            item = (row.get("ingredient_item") or "").lower().strip()
            htc_top_item[h][item] += 1
            if q > 0 and g > 0 and u:
                grams_by_tuple[(item, q, u)][round(g, 1)] += 1
                htc_top_tuple[h][(item, q, u)] += 1

    # 4) For each concept_key, gather verdict
    rows = []
    for ck, n_recs in sorted(n_recipes_per_ck.items(), key=lambda kv: -kv[1]):
        cp, _, htc_form = ck.partition("|")
        # The concept's htc_form IS the htc_form_code; the bridge is keyed
        # on htc_form_code (htc_code in bridge file is actually the form
        # code with form bits stripped — let's just look up htc_form in
        # bridge directly).
        b = bridge.get(htc_form, {})
        bridge_ok = bool(b.get("fdc_id"))
        sr_desc = b.get("sr_description", "")

        # Top item from recipes_unified for this htc_form
        top_item = ""
        if htc_form in htc_top_item:
            top_item = htc_top_item[htc_form].most_common(1)[0][0]

        # Modal (item, qty, unit) for determinism
        if htc_form in htc_top_tuple and htc_top_tuple[htc_form]:
            (m_item, m_qty, m_unit), m_count = htc_top_tuple[htc_form].most_common(1)[0]
            mg = grams_by_tuple[(m_item, m_qty, m_unit)]
            modal_g, modal_c = mg.most_common(1)[0]
            sum_g = sum(mg.values())
            modal_pct = modal_c / sum_g if sum_g else 0
            n_distinct_g = len(mg)
        else:
            m_item, m_qty, m_unit = top_item, 0, ""
            modal_g, modal_pct, n_distinct_g = 0, 0, 0

        gram_ok = (n_distinct_g <= 1) or (modal_pct >= 0.99)

        # Resolver pick
        res = cr.get(ck, {})
        tier = res.get("tier", "NO_MATCH")
        priced_key = res.get("priced_key") or ""
        priced_cp = ci.get(priced_key, {}).get("canonical_path", "") if priced_key else ""
        pkg = cheapest(ci.get(priced_key, {}).get("packages", [])) if priced_key else None
        sku_name = (pkg.get("name","") or "")[:60] if pkg else ""
        sku_grams = pkg.get("grams", 0) if pkg else 0
        sku_cents = pkg.get("cents", 0) if pkg else 0

        # SKU sanity — leaf-stem in cheapest pick
        target_stems = leaf_stems(cp)
        sku_ok = name_has_any_stem(sku_name, target_stems)

        # Verdict
        verdict = "GREEN"
        reasons = []
        if not bridge_ok:
            verdict = "YELLOW"; reasons.append("no_bridge")
        if m_qty and not gram_ok:
            verdict = "RED" if verdict == "GREEN" else "RED"
            reasons.append(f"gram_drift({n_distinct_g}distinct,modal={modal_pct:.0%})")
        if not sku_name:
            verdict = "RED"; reasons.append(f"NO_PICK({tier})")
        elif not sku_ok:
            verdict = "RED"; reasons.append("sku_leaf_miss")

        rows.append({
            "concept_key": ck,
            "n_recipes": n_recs,
            "total_g_demand": int(grams_per_ck[ck]),
            "top_item": m_item,
            "modal_qty_unit": f"{m_qty} {m_unit}" if m_qty else "",
            "modal_g": modal_g,
            "modal_pct": f"{modal_pct:.0%}",
            "n_distinct_g": n_distinct_g,
            "bridge_fdc": b.get("fdc_id",""),
            "bridge_sr_desc": sr_desc,
            "tier": tier,
            "priced_cp": priced_cp,
            "cheapest_sku": sku_name,
            "sku_grams": int(sku_grams),
            "sku_cents": sku_cents,
            "sku_ok": sku_ok,
            "verdict": verdict,
            "reasons": "|".join(reasons),
        })

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows: w.writerow(r)

    # Summary
    total = len(rows)
    total_recs = sum(r["n_recipes"] for r in rows)
    by_v: Counter = Counter()
    by_v_recs: Counter = Counter()
    for r in rows:
        by_v[r["verdict"]] += 1
        by_v_recs[r["verdict"]] += r["n_recipes"]

    txt = []
    txt.append(f"# HTC Concept-Key Coverage Audit\n")
    txt.append(f"Total recipe-side concepts: {total:,}")
    txt.append(f"Total recipe-uses: {total_recs:,}")
    txt.append(f"\nVerdict (by concepts / by recipe-use volume):")
    for v in ("GREEN","YELLOW","RED"):
        n = by_v[v]; nr = by_v_recs[v]
        pct_n = n/total*100 if total else 0
        pct_r = nr/total_recs*100 if total_recs else 0
        txt.append(f"  {v:6s}  {n:>5,} concepts ({pct_n:5.1f}%)  "
                   f"{nr:>10,} recipe-uses ({pct_r:5.1f}%)")

    reds = sorted([r for r in rows if r["verdict"]=="RED"],
                  key=lambda r: -r["n_recipes"])
    txt.append(f"\nTop 30 RED by recipe-impact:")
    for r in reds[:30]:
        ck = r["concept_key"]
        cp = ck.split("|")[0]
        txt.append(f"  [{r['n_recipes']:>5}] '{cp[:35]:<35}' tier={r['tier']:<18s} "
                   f"→ '{r['cheapest_sku'][:34]:<34}' :: {r['reasons']}")

    yells = sorted([r for r in rows if r["verdict"]=="YELLOW"],
                   key=lambda r: -r["n_recipes"])
    txt.append(f"\nTop 20 YELLOW by recipe-impact:")
    for r in yells[:20]:
        ck = r["concept_key"]
        cp = ck.split("|")[0]
        txt.append(f"  [{r['n_recipes']:>5}] '{cp[:35]:<35}' :: {r['reasons']}")

    greens = sorted([r for r in rows if r["verdict"]=="GREEN"],
                    key=lambda r: -r["n_recipes"])
    txt.append(f"\nTop 15 GREEN (proof of working end-to-end):")
    for r in greens[:15]:
        ck = r["concept_key"]
        cp = ck.split("|")[0]
        gram_str = f"{r['modal_qty_unit']}={r['modal_g']}g" if r["modal_qty_unit"] else ""
        txt.append(f"  [{r['n_recipes']:>5}] '{cp[:30]:<30}' {gram_str:<22} → "
                   f"'{r['cheapest_sku'][:30]:<30}' (${r['sku_cents']/100:.2f})")

    OUT_TXT.write_text("\n".join(txt))
    print("\n" + "\n".join(txt[:8]), file=sys.stderr)
    print(f"\n→ {OUT_CSV}\n→ {OUT_TXT}", file=sys.stderr)


if __name__ == "__main__":
    main()
