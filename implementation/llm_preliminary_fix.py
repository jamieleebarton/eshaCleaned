#!/usr/bin/env python3
"""
Preliminary fix proposals for known dumping-ground ESHA codes.
For each product, asks Llama-3.3-70B to either confirm the current code,
pick a better one from TF-IDF candidates, or say NEEDS_NEW_CONCEPT.
"""
import os, sys, json, urllib.request, urllib.error, sqlite3, csv, time, argparse
import concurrent.futures
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.csv"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"
DB = f"{ROOT}/data/master_products.db"
OUT_DIR = f"{ROOT}/implementation/output"
URL = "https://api.studio.nebius.com/v1/chat/completions"
MODEL = "meta-llama/Llama-3.3-70B-Instruct"
KEY = open(os.path.expanduser("~/.nebius/key")).read().strip()

# Targets: (esha_code, slug)
TARGETS = [
    ("38579", "pasta_macaroni_elbow"),
    ("91074", "candy_corn"),
    ("8361",  "olive_oil_evoo"),
    ("807",   "flavored_water_strawberry_watermelon"),
]

SYSTEM = ("You audit ESHA food-database mappings. Pick the ESHA code that best matches the "
          "product's PRIMARY food identity. If none of the candidates is a good match, "
          "respond with code 'NONE'. Reply only valid JSON.")

def build_tree_index():
    rows = []
    with open(TREE) as f:
        for r in csv.DictReader(f):
            rows.append((r["EshaCode"], r["Description"]))
    descs = [d for _, d in rows]
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3,5), max_features=30000, sublinear_tf=True)
    mat = vec.fit_transform(descs)
    return rows, vec, mat

def topk(rows, vec, mat, query, k=15):
    qv = vec.transform([query])
    s = cosine_similarity(qv, mat)[0]
    idx = np.argpartition(-s, min(k, len(s)-1))[:k]
    idx = idx[np.argsort(-s[idx])]
    return [(rows[i][0], rows[i][1], float(s[i])) for i in idx]

def load_products_for_codes(codes):
    out = defaultdict(list)
    with open(MAP) as f:
        for r in csv.DictReader(f):
            if r["best_esha_code"] in codes:
                out[r["best_esha_code"]].append(r)
    return out

def load_ingredients(fdc_ids):
    con = sqlite3.connect(DB)
    out = {}
    chunk = 500
    for i in range(0, len(fdc_ids), chunk):
        sl = fdc_ids[i:i+chunk]
        ph = ",".join("?"*len(sl))
        for row in con.execute(f"SELECT fdc_id, ingredients FROM products WHERE fdc_id IN ({ph})", sl):
            out[str(row[0])] = row[1] or ""
    con.close()
    return out

def build_prompt(r, ing, candidates):
    cand_lines = "\n".join(f"  [{c}] {d}" for c, d, _ in candidates)
    return f"""PRODUCT: {r['product_description']}
BRAND: {r['brand_name']} ({r['brand_owner']})
CATEGORY: {r['branded_food_category']}
INGREDIENTS: {ing[:350] if ing else '(unavailable)'}

CURRENT ASSIGNED ESHA: [{r['best_esha_code']}] {r['best_esha_description']}

CANDIDATE REPLACEMENT ESHA codes (top by similarity):
{cand_lines}

Audit:
- If the CURRENT code matches the product's primary food identity, reply: {{"verdict":"CORRECT","best_code":"{r['best_esha_code']}","reason":"...","fix_pattern":""}}
- If it's wrong, pick the BEST candidate code (must be one of the codes above).
- If NONE of the candidates fit, set best_code to "NONE".
- "Apple slices with peanut butter" is NOT plain apple slices.
- Cooked ≠ raw. Biscuit ≠ roll. Specific flavor ≠ different flavor.

Reply only valid JSON:
{{"verdict":"CORRECT|WRONG|UNCERTAIN","best_code":"<code or NONE>","mismatch_type":"COMPOSITE_NOT_PLAIN|WRONG_FORM|WRONG_INGREDIENT|MIXED_ITEMS|TOTALLY_DIFFERENT|NONE","reason":"<one sentence>","fix_pattern":"<short generalizable rule, or empty>"}}"""

def call_llm(msg, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(URL, method="POST",
                headers={"Authorization": f"Bearer {KEY}", "Content-Type":"application/json"},
                data=json.dumps({
                    "model": MODEL, "max_tokens": 220, "temperature": 0,
                    "response_format": {"type":"json_object"},
                    "messages":[{"role":"system","content":SYSTEM},
                                {"role":"user","content":msg}]
                }).encode())
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            if attempt == retries - 1: raise
            time.sleep(2 * (attempt + 1))

def judge(r, ing_map, tree_rows, vec, mat, code_to_desc):
    fdc_id = r["fdc_id"]
    ing = ing_map.get(fdc_id, "")
    # Build TF-IDF query: product + brand + ingredients (first part)
    q = " ".join(filter(None, [r["product_description"], r["brand_name"], ing[:200]])).lower()
    cand = topk(tree_rows, vec, mat, q, k=15)
    # Always include current code in case it's not in top-k
    cur = r["best_esha_code"]
    if cur and cur not in {c for c,_,_ in cand}:
        cand.append((cur, code_to_desc.get(cur, r["best_esha_description"]), 0.0))
    try:
        body = call_llm(build_prompt(r, ing, cand))
        out = json.loads(body["choices"][0]["message"]["content"])
        best_code = out.get("best_code","").strip()
        suggested_desc = code_to_desc.get(best_code, "") if best_code and best_code != "NONE" else ""
        return {
            "fdc_id": fdc_id,
            "gtin_upc": r.get("gtin_upc",""),
            "product_description": r["product_description"],
            "brand_name": r["brand_name"],
            "branded_food_category": r["branded_food_category"],
            "current_esha_code": cur,
            "current_esha_desc": r["best_esha_description"],
            "rft_verdict": r["rft_verdict"],
            "llm_verdict": out.get("verdict",""),
            "mismatch_type": out.get("mismatch_type","NONE"),
            "suggested_code": best_code,
            "suggested_desc": suggested_desc,
            "reason": out.get("reason",""),
            "fix_pattern": out.get("fix_pattern",""),
            "tokens_in": body["usage"]["prompt_tokens"],
            "tokens_out": body["usage"]["completion_tokens"],
        }
    except Exception as e:
        return {"fdc_id": fdc_id, "error": f"{type(e).__name__}: {str(e)[:120]}"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=40)
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    args = ap.parse_args()

    print(f"Loading ESHA tree...", flush=True)
    tree_rows, vec, mat = build_tree_index()
    code_to_desc = {c:d for c,d in tree_rows}
    print(f"  {len(tree_rows):,} ESHA codes indexed", flush=True)

    print(f"Loading products in target codes...", flush=True)
    target_codes = {c for c,_ in TARGETS}
    by_code = load_products_for_codes(target_codes)
    for code, slug in TARGETS:
        print(f"  [{code}] {slug}: {len(by_code.get(code, [])):,} products", flush=True)

    all_products = []
    for code, slug in TARGETS:
        rows = by_code.get(code, [])
        if args.limit:
            rows = rows[:args.limit]
        all_products.extend((slug, r) for r in rows)
    print(f"Total to judge: {len(all_products):,}", flush=True)

    print(f"Loading ingredients...", flush=True)
    ing_map = load_ingredients([r["fdc_id"] for _, r in all_products])
    print(f"  ingredients found for {len(ing_map):,}/{len(all_products):,}", flush=True)

    # Run in parallel
    print(f"\nLaunching {args.workers} workers...", flush=True)
    t0 = time.time()
    results = defaultdict(list)
    done = 0
    errs = 0
    tot_in = tot_out = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(judge, r, ing_map, tree_rows, vec, mat, code_to_desc): slug
                for slug, r in all_products}
        for fut in concurrent.futures.as_completed(futs):
            slug = futs[fut]
            res = fut.result()
            results[slug].append(res)
            done += 1
            if "error" in res:
                errs += 1
            else:
                tot_in += res.get("tokens_in",0)
                tot_out += res.get("tokens_out",0)
            if done % 250 == 0 or done == len(all_products):
                el = time.time() - t0
                rate = done / max(el, 0.1)
                eta = (len(all_products) - done) / max(rate, 0.1)
                print(f"  [{done:,}/{len(all_products):,}] {rate:.1f} req/s, errs={errs}, "
                      f"in={tot_in:,} out={tot_out:,}, ETA {eta:.0f}s", flush=True)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s. Total tokens in={tot_in:,} out={tot_out:,}")
    cost = tot_in*0.13/1e6 + tot_out*0.40/1e6
    print(f"Estimated cost: ${cost:.3f}")

    # Write per-code output CSVs
    for code, slug in TARGETS:
        rows = results.get(slug, [])
        if not rows: continue
        fp = f"{OUT_DIR}/preliminary_fix_{code}_{slug}.csv"
        cols = ["fdc_id","gtin_upc","product_description","brand_name","branded_food_category",
                "current_esha_code","current_esha_desc","rft_verdict","llm_verdict",
                "mismatch_type","suggested_code","suggested_desc","reason","fix_pattern",
                "tokens_in","tokens_out","error"]
        with open(fp, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        # Summary
        ok_rows = [r for r in rows if "error" not in r]
        from collections import Counter
        vc = Counter(r["llm_verdict"] for r in ok_rows)
        mc = Counter(r["mismatch_type"] for r in ok_rows if r["llm_verdict"]=="WRONG")
        n_with_suggestion = sum(1 for r in ok_rows if r.get("suggested_code") and r["suggested_code"]!="NONE" and r.get("llm_verdict")=="WRONG")
        n_no_match = sum(1 for r in ok_rows if r.get("suggested_code")=="NONE")
        print(f"\n=== [{code}] {slug} ({len(rows)} products) ===")
        print(f"  Saved: {fp}")
        print(f"  Verdicts: {dict(vc)}")
        print(f"  Mismatch types: {dict(mc)}")
        print(f"  WRONG with suggested replacement: {n_with_suggestion}")
        print(f"  NONE (need new concept): {n_no_match}")

if __name__ == "__main__":
    main()
