#!/usr/bin/env python3
"""Pilot LLM classifier with consistency guardrails.

Reads NEBIUS_API_KEY from env. For each test row:
  1. Builds the closed-vocabulary leaf set:
       - all existing retail_leaf paths under the row's most-likely supercategory
       - plus 3-5 sibling examples (same current_esha or same BFC)
  2. Sends llm_evidence_block + closed-vocab + few-shot to the LLM.
  3. Asks for JSON: {chosen_leaf, confidence, reasoning, mint_required: bool}
  4. If chosen_leaf isn't in the closed vocab, validates it as a mint candidate
     and runs the same canonicalize_leaf used by the pipeline.
  5. Reports LLM pick vs current pipeline pick.

Run:  NEBIUS_API_KEY='...' python llm_test.py
"""
from __future__ import annotations
import csv, json, os, re, sys, time
import collections
csv.field_size_limit(sys.maxsize)

REPO = "/Users/jamiebarton/Desktop/esha_audit_bundle"
ENRICHED = f"{REPO}/retail_mapper/v2/retail_leaf_v2_enriched_v2.csv"
sys.path.insert(0, f"{REPO}/retail_mapper/v2")
from reconcile import canonicalize_leaf

API_KEY = os.environ.get("NEBIUS_API_KEY", "").strip()
if not API_KEY:
    print("ERROR: NEBIUS_API_KEY not set"); sys.exit(1)

from openai import OpenAI
client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.studio.nebius.com/v1/",
)

MODEL = os.environ.get("NEBIUS_MODEL", "deepseek-ai/DeepSeek-V3-0324-fast")

# --- 1. load enriched data, build sibling/leaf indices ---
print("loading enriched corpus + indices...")
t0 = time.time()
rows_by_fdc = {}
leaves_by_super = collections.defaultdict(collections.Counter)
leaves_by_fndds = collections.defaultdict(collections.Counter)
leaves_by_bfc   = collections.defaultdict(collections.Counter)
sample_rows_by_fndds = collections.defaultdict(list)
with open(ENRICHED) as f:
    for r in csv.DictReader(f):
        fdc = r['fdc_id']
        rows_by_fdc[fdc] = r
        leaf = r['retail_leaf']
        sup = leaf.split(' > ')[0] if leaf else ''
        if leaf and sup:
            leaves_by_super[sup][leaf] += 1
        if r.get('current_esha'):
            leaves_by_fndds[r['current_esha']][leaf] += 1
            if len(sample_rows_by_fndds[r['current_esha']]) < 6:
                sample_rows_by_fndds[r['current_esha']].append((r['title'], leaf))
        if r.get('branded_food_category'):
            leaves_by_bfc[r['branded_food_category']][leaf] += 1
print(f"  {len(rows_by_fdc):,} rows  ({time.time()-t0:.1f}s)")

# --- 2. test row picker (mix of clean/fuzzy cases) ---
TEST_FDCS = [
    '564094',  # BAI Antioxidant Infusion Costa Rica Clementine
]

# --- 3. build prompt for one row ---
SCHEMA = """{
  "chosen_leaf": "<full leaf path, e.g. 'Pantry > Sauces & Salsas > BBQ Sauce'>",
  "confidence": <0.0-1.0>,
  "reasoning": "<one short sentence>",
  "mint_required": <true if not in closed vocab; false otherwise>
}"""

def build_prompt(row):
    fdc = row['fdc_id']
    bfc = row.get('branded_food_category', '')
    cur_esha = row.get('current_esha','')
    # closed vocabulary: top leaves from siblings (same FNDDS) + same BFC + same super
    closed = collections.Counter()
    if cur_esha:
        closed.update(leaves_by_fndds.get(cur_esha, {}))
    if bfc:
        closed.update(leaves_by_bfc.get(bfc, {}))
    proposed_super = (row.get('retail_leaf','').split(' > ') or [''])[0]
    if proposed_super:
        # cap so prompt isn't enormous
        for k, v in leaves_by_super.get(proposed_super, {}).most_common(40):
            closed[k] += v
    closed_top = [k for k, _ in closed.most_common(30)]

    # few-shot from same FNDDS
    samples = sample_rows_by_fndds.get(cur_esha, [])

    sys_msg = (
        "You categorize retail food products into a retail-shelf taxonomy. "
        "RULES:\n"
        "1. Choose the category for what the product IS, not the flavors or ingredients in it. "
        "Product form (e.g. 'sauce', 'cereal', 'butter', 'pie') beats flavor (e.g. 'brown sugar', 'maple', 'hickory').\n"
        "2. NEVER include brand names in the leaf path. Strip 'Marie Callender', 'Kellogg', 'Quaker', "
        "'Silk', 'Eggo', 'So Delicious', 'Wild Harvest', etc. The leaf describes the product TYPE, not the brand.\n"
        "3. Prefer leaves that already exist in the closed vocabulary. Only set mint_required=true "
        "and propose a new leaf when no existing leaf captures the actual product type.\n"
        "4. New leaf paths must follow the existing pattern: 'Supercategory > Category > Modifier'. "
        "Re-use existing supercategories from the vocab — never invent a new top-level supercategory. "
        "When minting, pick a meaningful modifier (e.g. 'Lime Mayo' belongs in 'Pantry > Condiment > Mayonnaise > Lime', "
        "'Almond Nog' belongs in 'Beverage > Plant-based Nog > Almond', "
        "'Hot Honey Gouda' belongs in 'Dairy > Cheese > Gouda > Hot Honey').\n"
        "5. Singular form for the rightmost segment. No packaging tokens (oz, ml, ct, pack, count).\n"
        "6. Maximum 5 segments. Drop redundant adjacent segments.\n"
        "7. Output strict JSON matching the schema. Nothing else.\n"
        f"\nSCHEMA:\n{SCHEMA}\n"
    )
    user_msg = (
        f"=== EVIDENCE ===\n{row.get('llm_evidence_block','')}\n\n"
        f"=== CLOSED VOCABULARY (top 30 candidate leaves; PREFER these) ===\n"
        + "\n".join(f"  - {l}" for l in closed_top) + "\n\n"
        f"=== FEW-SHOT (other products with same audit ESHA={cur_esha}) ===\n"
        + ("\n".join(f"  '{t[:60]}' → {l}" for t, l in samples[:5]) if samples else "  (no siblings)")
        + "\n\nRespond with the JSON object only."
    )
    return sys_msg, user_msg

def llm_classify(row):
    sys_msg, user_msg = build_prompt(row)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.0,
        max_tokens=400,
    )
    raw = resp.choices[0].message.content.strip()
    # extract JSON blob
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        return {"raw": raw, "error": "no JSON found"}
    try:
        out = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"raw": raw, "error": f"json parse: {e}"}
    # canonicalize the chosen leaf
    if out.get("chosen_leaf"):
        out["chosen_leaf_canonical"] = canonicalize_leaf(out["chosen_leaf"], (row.get('title') or '').lower())
    return out

# --- 4. run on test set ---
print(f"\nmodel: {MODEL}")
print(f"running on {len(TEST_FDCS)} test products...\n")
results = []
for fdc in TEST_FDCS:
    r = rows_by_fdc.get(fdc)
    if not r: continue
    print(f"=== fdc={fdc}  {r['title'][:55]!r} ===")
    print(f"  current pipeline leaf: {r['retail_leaf']!r}  cf={r['confidence']}")
    try:
        out = llm_classify(r)
    except Exception as e:
        out = {"error": str(e)}
    if "error" in out:
        print(f"  LLM error: {out['error']}")
        if out.get("raw"): print(f"     raw: {out['raw'][:200]!r}")
    else:
        chosen = out.get('chosen_leaf_canonical') or out.get('chosen_leaf','')
        print(f"  LLM pick:               {chosen!r}")
        print(f"     mint_required={out.get('mint_required')}  conf={out.get('confidence')}")
        print(f"     reason: {out.get('reasoning','')[:120]}")
        agree = chosen == r['retail_leaf']
        print(f"     agreement: {'YES' if agree else 'NO'}")
    results.append({"fdc": fdc, "title": r['title'], "pipeline": r['retail_leaf'], "llm": out})
    print()

# summary
agree_count = sum(1 for x in results if not x['llm'].get('error') and (x['llm'].get('chosen_leaf_canonical') or x['llm'].get('chosen_leaf','')) == x['pipeline'])
mint_count  = sum(1 for x in results if not x['llm'].get('error') and x['llm'].get('mint_required'))
err_count   = sum(1 for x in results if x['llm'].get('error'))
print(f"--- summary ---")
print(f"  total: {len(results)}")
print(f"  agree with pipeline: {agree_count}")
print(f"  LLM proposed mint:   {mint_count}")
print(f"  LLM errors:          {err_count}")
