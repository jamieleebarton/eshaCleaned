"""RFT Swarm — Category Analyzer."""
from __future__ import annotations
import csv, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
PROD_MAP = ROOT / "implementation/output/product_to_best_esha_full_map.vIdentity.csv"
CANONICAL = ROOT / "implementation/output/canonical_surface_normalized_with_product_proxies_CLEANED.csv"
REPORTS = ROOT / "implementation/rft_swarm/reports"
REPORTS.mkdir(parents=True, exist_ok=True)

# Food families: base codes (generic) and variant codes (specific)
KNOWN_FAMILIES = {
    "applesauce": {
        "base": {"35873","3006"},
        "cinnamon": [("46799","applesauce, cinnamon"),("48987","applesauce, with cinnamon")],
        "strawberry": [("46807","applesauce, strawberry")],
        "peach": [("46811","applesauce, peach mango")],
        "blueberry": [("46808","applesauce, blueberry pomegranate")],
        "cherry": [("46809","applesauce, cherry")],
        "unsweetened": [("3006","applesauce, unsweetened, canned")],
        "sweetened": [("46797","applesauce, naturally sweetened")],
    },
    "milk": {
        "base": {"7"},
        "skim": [("8","milk, skim")], "fat": [("8","milk, skim"),("9","milk, low fat")],
        "low": [("9","milk, low fat")], "whole": [("7","milk, whole")],
        "chocolate": [("11","milk, chocolate")], "buttermilk": [("10","milk, buttermilk")],
        "evaporated": [("20952","milk, evaporated")], "condensed": [("20954","milk, sweetened condensed")],
        "goat": [("20955","milk, goat")], "oat": [("36243","milk, oat")],
        "almond": [("36241","milk, almond")], "soy": [("36240","milk, soy")],
        "coconut": [("36242","milk, coconut")],
    },
    "yogurt": {
        "base": {"27372"},
        "vanilla": [("27373","yogurt, vanilla, low fat")],
        "strawberry": [("27374","yogurt, strawberry, low fat")],
        "blueberry": [("27375","yogurt, blueberry, low fat")],
        "peach": [("27376","yogurt, peach, low fat")],
        "greek": [("38605","yogurt, greek, plain, whole milk")],
    },
    "juice": {
        "base": {"3011"},
        "cranberry": [("3017","juice, cranberry")], "orange": [("3020","juice, orange")],
        "grape": [("3019","juice, grape")], "pineapple": [("3023","juice, pineapple")],
        "tomato": [("3031","juice, tomato")], "grapefruit": [("3021","juice, grapefruit")],
    },
}

def slugify(t): return re.sub(r"[^a-z0-9]+","_",t.lower()).strip("_")

def normalize_desc(text):
    text = str(text or "").lower()
    text = re.sub(r"\bapple[\s-]+sauces?\b","applesauce",text)
    return text

def load_canonical():
    idx={}
    with CANONICAL.open(encoding="utf-8",errors="replace") as f:
        for r in csv.DictReader(f):
            s=normalize_desc(r.get("canonical_surface"))
            if s: idx[s]=r
    return idx

def detect_family(d):
    for fam in KNOWN_FAMILIES:
        if fam in d: return fam
    return None

def make_fix(row, proposed_code, proposed_desc, reason, variant_word="", family=""):
    return {
        "gtin_upc": row.get("gtin_upc",""),
        "fdc_id": row.get("fdc_id",""),
        "product_description": row.get("product_description",""),
        "branded_food_category": row.get("branded_food_category",""),
        "current_esha_code": row.get("best_esha_code","").strip(),
        "current_esha_desc": row.get("best_esha_description",""),
        "proposed_esha_code": proposed_code,
        "proposed_esha_desc": proposed_desc,
        "variant_word": variant_word,
        "family": family,
        "reason": reason,
        "rft_verdict": row.get("rft_verdict",""),
        "assignment_source": row.get("assignment_source",""),
    }

def find_variant_mismatches(rows,family):
    rules=KNOWN_FAMILIES[family]; fixes=[]
    for row in rows:
        desc=normalize_desc(row.get("product_description",""))
        cur_code=row.get("best_esha_code","").strip()
        cur_desc=row.get("best_esha_description","").lower()
        for variant,targets in rules.items():
            if variant=="base": continue
            if variant in desc and variant not in cur_desc:
                # ONLY fix if current is a base/generic code
                if cur_code not in rules.get("base",set()):
                    continue
                tc,td=targets[0]
                if cur_code!=tc:
                    fixes.append(make_fix(row,tc,td,f"variant_word:{variant}",variant,family))
    return fixes

def find_canonical_mismatches(rows,canon):
    fixes=[]
    for row in rows:
        desc=normalize_desc(row.get("product_description","")).strip()
        if not desc or desc not in canon: continue
        can=canon[desc]; can_code=can.get("esha_code","").strip()
        cur_code=row.get("best_esha_code","").strip()
        if can_code and cur_code and can_code!=cur_code:
            fixes.append(make_fix(row,can_code,can.get("esha_description",""),"exact_canonical_mismatch"))
    return fixes

def analyze_category(category):
    print(f"\n{'='*60}\nAnalyzing: {category}\n{'='*60}")
    canon=load_canonical()
    rows=[]
    with PROD_MAP.open(encoding="utf-8",errors="replace") as f:
        for r in csv.DictReader(f):
            if r.get("branded_food_category","").strip()==category:
                rows.append(r)
    print(f"  Products: {len(rows):,}")
    verdicts=Counter(r.get("rft_verdict","") for r in rows)
    for v,c in verdicts.most_common(): print(f"    {v:20s} {c:>6,}")
    codes=Counter((r.get("best_esha_code"),r.get("best_esha_description")) for r in rows)
    print(f"\n  Top ESHA:")
    for (code,desc),c in codes.most_common(10): print(f"    {c:>6,}  {code:>6}  {desc}")
    all_fixes=[]
    family_rows=defaultdict(list)
    for r in rows:
        fam=detect_family(normalize_desc(r.get("product_description","")))
        if fam: family_rows[fam].append(r)
    for fam,fam_rows in family_rows.items():
        fixes=find_variant_mismatches(fam_rows,fam)
        if fixes: print(f"\n  Family '{fam}' mismatches: {len(fixes)}"); all_fixes.extend(fixes)
    cf=find_canonical_mismatches(rows,canon)
    if cf: print(f"\n  Canonical mismatches: {len(cf)}"); all_fixes.extend(cf)
    needs_new=[r for r in rows if r.get("rft_verdict")=="NEEDS_NEW_CONCEPT"]
    if needs_new:
        print(f"\n  NEEDS_NEW: {len(needs_new)}")
        idents=Counter()
        for r in needs_new: idents[r.get("rft_concept_tokens","").replace("|"," ")]+=1
        for sig,c in idents.most_common(8): print(f"    {c:>5,}  {sig}")
    seen={}
    for fix in all_fixes:
        key=(fix["gtin_upc"].strip(), fix["fdc_id"].strip())
        if key not in seen: seen[key]=fix
    deduped=list(seen.values())
    slug=slugify(category)
    report={"category":category,"n_products":len(rows),"verdict_distribution":dict(verdicts),
        "top_esha_codes":[dict(code=c,desc=d,n=n) for (c,d),n in codes.most_common(10)],
        "n_fixes_proposed":len(deduped),"n_needs_new_concept":len(needs_new)}
    rp=REPORTS/f"{slug}_report.json"
    with open(rp,"w") as f: json.dump(report,f,indent=2)
    if deduped:
        fp=REPORTS/f"{slug}_fixes.csv"
        with open(fp,"w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(deduped[0].keys()))
            w.writeheader(); w.writerows(deduped)
        print(f"\n  Wrote {len(deduped)} fixes -> {fp.name}")
    print(f"  Report -> {rp.name}")
    return report

if __name__=="__main__":
    if len(sys.argv)<2: print("Usage: python3 category_analyzer.py 'Category Name'"); sys.exit(1)
    analyze_category(sys.argv[1])
