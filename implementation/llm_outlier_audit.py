#!/usr/bin/env python3
"""
Stage 3 — LLM audit on the 13,805 filtered outliers.

Same TF-IDF→Llama-3.3-70B pattern as llm_full_audit.py, but on the
outliers_filtered.csv input (post-embedding-scan and post-false-positive-filter).

Resumable: writes JSONL line-by-line; restart skips already-judged fdc_ids.

Outputs:
  llm_outlier_audit.jsonl        — one JSON per fdc_id
  llm_outlier_audit_progress.log — per-1000-row progress
"""
import argparse, csv, json, os, sys, time, urllib.request, urllib.error, sqlite3
import concurrent.futures
from collections import Counter, defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
INPUT_OUTLIERS = f"{ROOT}/implementation/output/outliers_filtered.csv"
INPUT_MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v2.csv"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"
DB = f"{ROOT}/data/master_products.db"
OUT_JSONL = f"{ROOT}/implementation/output/llm_outlier_audit.jsonl"
PROGRESS_LOG = f"{ROOT}/implementation/output/llm_outlier_audit_progress.log"

URL = "https://api.studio.nebius.com/v1/chat/completions"
MODEL = "meta-llama/Llama-3.3-70B-Instruct"
KEY = open(os.path.expanduser("~/.nebius/key")).read().strip()

SYSTEM = (
    "You audit ESHA food-database mappings. The input has been pre-screened: "
    "the product looks semantically distant from its current cohort. "
    "Pick the ESHA code that best matches the product's PRIMARY food identity. "
    "If the current code is actually right, say CORRECT. "
    "If wrong, pick the best candidate. If no candidate is a clear match, set "
    "best_code to 'NONE' and verdict to UNCERTAIN — do NOT force a poor fit. "
    "Reply only valid JSON."
)

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
    return [(rows[i][0], rows[i][1]) for i in idx]

def load_done_ids(path):
    done = set()
    if not os.path.exists(path): return done
    with open(path) as f:
        for line in f:
            try: done.add(json.loads(line)["fdc_id"])
            except: pass
    return done

def build_prompt(prod_row, ing, candidates):
    cand_lines = "\n".join(f"  [{c}] {d}" for c, d in candidates)
    return f"""PRODUCT: {prod_row['product_description']}
BRAND: {prod_row['brand_name']} ({prod_row['brand_owner']})
CATEGORY: {prod_row['branded_food_category']}
INGREDIENTS: {ing[:350] if ing else '(unavailable)'}

CURRENT ESHA: [{prod_row['best_esha_code']}] {prod_row['best_esha_description']}

CANDIDATE ESHA codes (top by similarity):
{cand_lines}

Audit:
- Product was flagged as semantically distant from its current cohort.
- Verify: does CURRENT code actually match the product's primary food identity?
- If wrong, pick BEST candidate code. Must be one of the codes above.
- If NONE of the candidates is a clearly good match, set best_code to "NONE".

Reply only valid JSON:
{{"verdict":"CORRECT|WRONG|UNCERTAIN","best_code":"<code or NONE>","mismatch_type":"COMPOSITE_NOT_PLAIN|WRONG_FORM|WRONG_INGREDIENT|MIXED_ITEMS|TOTALLY_DIFFERENT|NONE","reason":"<one sentence>","fix_pattern":"<short generalizable rule, or empty>"}}"""

def call_llm(msg, retries=3):
    last = None
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
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last

def judge(prod_row, ing_map, tree_rows, vec, mat, code_to_desc):
    fdc_id = prod_row["fdc_id"]
    ing = ing_map.get(fdc_id, "")
    q = " ".join(filter(None, [prod_row["product_description"], prod_row["brand_name"], ing[:200]])).lower()
    cand = topk(tree_rows, vec, mat, q, k=15)
    cur = prod_row["best_esha_code"]
    if cur and cur not in {c for c,_ in cand}:
        cand.append((cur, code_to_desc.get(cur, prod_row["best_esha_description"])))
    try:
        body = call_llm(build_prompt(prod_row, ing, cand))
        out = json.loads(body["choices"][0]["message"]["content"])
        best = (out.get("best_code") or "").strip()
        return {
            "fdc_id": fdc_id,
            "current_esha_code": cur,
            "current_esha_desc": prod_row["best_esha_description"],
            "rft_verdict": prod_row.get("rft_verdict",""),
            "branded_food_category": prod_row["branded_food_category"],
            "llm_verdict": out.get("verdict",""),
            "mismatch_type": out.get("mismatch_type","NONE"),
            "suggested_code": best,
            "suggested_desc": code_to_desc.get(best, "") if best and best != "NONE" else "",
            "reason": out.get("reason",""),
            "fix_pattern": out.get("fix_pattern",""),
            "tokens_in": body["usage"]["prompt_tokens"],
            "tokens_out": body["usage"]["completion_tokens"],
        }
    except Exception as e:
        return {"fdc_id": fdc_id, "error": f"{type(e).__name__}: {str(e)[:120]}"}

def log(msg, fp):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(fp, "a") as f: f.write(line + "\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=50)
    args = ap.parse_args()

    log("=== outlier audit run ===", PROGRESS_LOG)
    log(f"input outliers: {INPUT_OUTLIERS}", PROGRESS_LOG)

    log("Loading ESHA tree...", PROGRESS_LOG)
    tree_rows, vec, mat = build_tree_index()
    code_to_desc = {c:d for c,d in tree_rows}
    log(f"  {len(tree_rows):,} ESHA codes indexed", PROGRESS_LOG)

    log("Loading map (for full product info)...", PROGRESS_LOG)
    products = {}
    with open(INPUT_MAP) as f:
        for r in csv.DictReader(f):
            products[r["fdc_id"]] = r
    log(f"  {len(products):,} products in map", PROGRESS_LOG)

    log("Resume check...", PROGRESS_LOG)
    done_ids = load_done_ids(OUT_JSONL)
    log(f"  {len(done_ids):,} fdc_ids already judged — skipping", PROGRESS_LOG)

    log("Reading outlier list...", PROGRESS_LOG)
    todo = []
    with open(INPUT_OUTLIERS) as f:
        for r in csv.DictReader(f):
            if r["fdc_id"] in done_ids: continue
            p = products.get(r["fdc_id"])
            if not p: continue
            todo.append(p)
    log(f"  {len(todo):,} products to audit", PROGRESS_LOG)
    if not todo:
        log("Nothing to do.", PROGRESS_LOG); return

    log("Loading ingredients...", PROGRESS_LOG)
    ids = [r["fdc_id"] for r in todo]
    ing_map = {}
    con = sqlite3.connect(DB)
    chunk = 1000
    for i in range(0, len(ids), chunk):
        sl = ids[i:i+chunk]
        ph = ",".join("?"*len(sl))
        for row in con.execute(f"SELECT fdc_id, ingredients FROM products WHERE fdc_id IN ({ph})", sl):
            ing_map[str(row[0])] = row[1] or ""
    con.close()
    log(f"  ingredients: {len(ing_map):,}/{len(todo):,}", PROGRESS_LOG)

    log(f"Launching {args.workers} workers...", PROGRESS_LOG)
    t0 = time.time()
    out_f = open(OUT_JSONL, "a")
    done = errs = tot_in = tot_out = 0
    LOG_EVERY = 500
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(judge, r, ing_map, tree_rows, vec, mat, code_to_desc): r["fdc_id"] for r in todo}
        for fut in concurrent.futures.as_completed(futs):
            res = fut.result()
            out_f.write(json.dumps(res) + "\n")
            done += 1
            if "error" in res: errs += 1
            else:
                tot_in += res.get("tokens_in", 0)
                tot_out += res.get("tokens_out", 0)
            if done % LOG_EVERY == 0 or done == len(todo):
                out_f.flush()
                el = time.time() - t0
                rate = done / max(el, 0.1)
                eta_s = (len(todo) - done) / max(rate, 0.1)
                cost = tot_in * 0.13 / 1e6 + tot_out * 0.40 / 1e6
                log(f"  [{done:,}/{len(todo):,}] {rate:.1f} req/s, errs={errs}, "
                    f"in={tot_in:,} out={tot_out:,}, ${cost:.2f}, ETA {eta_s/60:.1f}min", PROGRESS_LOG)
    out_f.close()
    el = time.time() - t0
    cost = tot_in * 0.13 / 1e6 + tot_out * 0.40 / 1e6
    log(f"\nDone in {el/60:.1f} min. Final cost: ${cost:.2f}. Errors: {errs}", PROGRESS_LOG)

if __name__ == "__main__":
    main()
