#!/usr/bin/env python3
"""
Full LLM audit of product_to_best_esha_full_map.vIdentity.fixed_v1.csv (462,646 rows).

For each product:
  1. Build top-15 candidate ESHA codes via TF-IDF over the canonical tree
     (using product_description + brand + first 200 chars of ingredients).
  2. Always include the currently-assigned code as a candidate.
  3. Ask Llama-3.3-70B: CORRECT, WRONG, or UNCERTAIN. If WRONG, pick the
     best candidate code or "NONE" if nothing fits.
  4. If no candidate is a clear match, the model is instructed to prefer
     UNCERTAIN/NONE rather than force-fitting.

Resumable: writes JSONL line-by-line; on restart, reads existing output and
skips fdc_ids already judged.

Outputs:
  - implementation/output/llm_full_audit.jsonl     (one JSON record per fdc_id)
  - implementation/output/llm_full_audit_progress.log

POST-RUN PLAN (executed after this finishes):
  Phase A: aggregate wrongs by current_esha_code → identify top 20 dumping
           grounds (>50% wrong) for tree-expansion priority.
  Phase B: apply HIGH-CONFIDENCE fixes (verdict=WRONG, suggested in tree, not
           NONE) → vIdentity.fixed_v2.csv with audit trail in
           best_esha_original_code/_description/_change_reason.
  Phase C: produce dumping_grounds_report.csv (per-code mismatch density,
           common destinations, common patterns) for human triage.
  Phase D: queue UNCERTAIN + WRONG-with-NONE for either manual review or a
           targeted thinking-model second pass on borderline-only.
"""
import argparse, csv, json, os, sys, time, urllib.request, urllib.error, sqlite3
import concurrent.futures
from collections import defaultdict, Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
INPUT_MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v1.csv"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"
DB = f"{ROOT}/data/master_products.db"
OUT_DIR = f"{ROOT}/implementation/output"
OUT_JSONL = f"{OUT_DIR}/llm_full_audit.jsonl"
PROGRESS_LOG = f"{OUT_DIR}/llm_full_audit_progress.log"

URL = "https://api.studio.nebius.com/v1/chat/completions"
MODEL = "meta-llama/Llama-3.3-70B-Instruct"
KEY = open(os.path.expanduser("~/.nebius/key")).read().strip()

SYSTEM = (
    "You audit ESHA food-database mappings. Pick the ESHA code that best matches "
    "the product's PRIMARY food identity. If the current code is right, say CORRECT. "
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
    if not os.path.exists(path):
        return done
    with open(path) as f:
        for line in f:
            try:
                done.add(json.loads(line)["fdc_id"])
            except Exception:
                pass
    return done

def build_prompt(r, ing, candidates):
    cand_lines = "\n".join(f"  [{c}] {d}" for c, d in candidates)
    return f"""PRODUCT: {r['product_description']}
BRAND: {r['brand_name']} ({r['brand_owner']})
CATEGORY: {r['branded_food_category']}
INGREDIENTS: {ing[:350] if ing else '(unavailable)'}

CURRENT ESHA: [{r['best_esha_code']}] {r['best_esha_description']}

CANDIDATE ESHA codes (top by similarity to product):
{cand_lines}

Audit:
- "Apple slices with peanut butter" is NOT plain apple slices.
- Cooked/glazed/dried ≠ raw/fresh. Biscuit ≠ roll. Wrong flavor = WRONG.
- If the current code is approximately right (just slightly more/less specific), say UNCERTAIN.
- If WRONG, pick the BEST candidate code (must be one of the codes above).
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

def judge(r, ing_map, tree_rows, vec, mat, code_to_desc):
    fdc_id = r["fdc_id"]
    ing = ing_map.get(fdc_id, "")
    q = " ".join(filter(None, [r["product_description"], r["brand_name"], ing[:200]])).lower()
    cand = topk(tree_rows, vec, mat, q, k=15)
    cur = r["best_esha_code"]
    if cur and cur not in {c for c,_ in cand}:
        cand.append((cur, code_to_desc.get(cur, r["best_esha_description"])))
    try:
        body = call_llm(build_prompt(r, ing, cand))
        out = json.loads(body["choices"][0]["message"]["content"])
        best = (out.get("best_code") or "").strip()
        return {
            "fdc_id": fdc_id,
            "current_esha_code": cur,
            "current_esha_desc": r["best_esha_description"],
            "rft_verdict": r["rft_verdict"],
            "branded_food_category": r["branded_food_category"],
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
    with open(fp, "a") as f:
        f.write(line + "\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=40)
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    args = ap.parse_args()

    log("=== full audit run ===", PROGRESS_LOG)
    log(f"input: {INPUT_MAP}", PROGRESS_LOG)
    log(f"output: {OUT_JSONL}", PROGRESS_LOG)
    log(f"model: {MODEL}", PROGRESS_LOG)

    log("Loading ESHA tree...", PROGRESS_LOG)
    tree_rows, vec, mat = build_tree_index()
    code_to_desc = {c:d for c,d in tree_rows}
    log(f"  {len(tree_rows):,} ESHA codes indexed", PROGRESS_LOG)

    log("Loading existing audit results (resume)...", PROGRESS_LOG)
    done_ids = load_done_ids(OUT_JSONL)
    log(f"  {len(done_ids):,} fdc_ids already judged — will skip", PROGRESS_LOG)

    log("Reading input map...", PROGRESS_LOG)
    todo = []
    with open(INPUT_MAP) as f:
        for r in csv.DictReader(f):
            if r["fdc_id"] in done_ids: continue
            todo.append(r)
    if args.limit:
        todo = todo[:args.limit]
    log(f"  {len(todo):,} products to judge", PROGRESS_LOG)

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
    done = 0
    errs = 0
    tot_in = tot_out = 0
    LOG_EVERY = 1000

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(judge, r, ing_map, tree_rows, vec, mat, code_to_desc): r["fdc_id"]
                for r in todo}
        for fut in concurrent.futures.as_completed(futs):
            res = fut.result()
            out_f.write(json.dumps(res) + "\n")
            done += 1
            if "error" in res:
                errs += 1
            else:
                tot_in += res.get("tokens_in", 0)
                tot_out += res.get("tokens_out", 0)
            if done % LOG_EVERY == 0 or done == len(todo):
                out_f.flush()
                el = time.time() - t0
                rate = done / max(el, 0.1)
                remaining = len(todo) - done
                eta_s = remaining / max(rate, 0.1)
                cost = tot_in * 0.13 / 1e6 + tot_out * 0.40 / 1e6
                log(f"  [{done:,}/{len(todo):,}] {rate:.1f} req/s, errs={errs}, "
                    f"in={tot_in:,} out={tot_out:,}, ${cost:.2f}, ETA {eta_s/60:.1f}min",
                    PROGRESS_LOG)
    out_f.close()
    el = time.time() - t0
    cost = tot_in * 0.13 / 1e6 + tot_out * 0.40 / 1e6
    log(f"\nDone in {el/60:.1f} min. Final cost: ${cost:.2f}. Errors: {errs}", PROGRESS_LOG)
    log(f"Output: {OUT_JSONL}", PROGRESS_LOG)

if __name__ == "__main__":
    main()
