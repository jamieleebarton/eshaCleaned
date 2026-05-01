#!/usr/bin/env python3
"""enrich_v2 — adds the role-tagger layer on top of retail_leaf_v2_enriched.csv.

For every product, generates per-ngram evidence + role_candidates:

  ngram_evidence (JSON):
    "barbeque sauce": {
      "count": 1834, "tfidf": 9.8,
      "in_title": true, "in_ingredients": false,
      "in_bfc": true, "in_esha_desc": true,
      "position": "end", "contains_form_word": "sauce",
      "nearby": ["hickory","brown","sugar"]
    }

  role_candidates (JSON):
    "barbeque sauce": ["possible_product_form","esha_head_match","category_match"]
    "brown sugar":    ["possible_modifier","possible_ingredient"]
    "hickory":        ["possible_modifier"]

  product_form_guess         - the ngram with strongest product-form signal
  modifier_guesses           - pipe-delimited modifier ngrams
  ingredient_guesses         - pipe-delimited tokens that look like ingredient roles
  llm_evidence_block         - compact human-readable summary for LLM prompt

Two passes over the corpus: pass 1 builds ngram document frequency; pass 2
computes per-row evidence + writes output.
"""
from __future__ import annotations
import csv, json, math, re, sys, time
import collections
csv.field_size_limit(sys.maxsize)

REPO = "/Users/jamiebarton/Desktop/esha_audit_bundle"
RM   = f"{REPO}/retail_mapper"
IN_CSV  = f"{RM}/v2/retail_leaf_v2_enriched.csv"
OUT_CSV = f"{RM}/v2/retail_leaf_v2_enriched_v2.csv"

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP = {"and","or","with","of","the","a","an","in","to","for","from","on","as","is","are",
        "less","than","plus","added","also","by","at","be","this","may","not","other","each",
        "per","new","oz","ml","ct","pk","pack","case","fl","g","kg","lb","lbs","count","size"}

def tok(s):
    return [t for t in TOKEN_RE.findall((s or '').lower()) if t not in STOP and len(t) >= 2]

def ngrams(toks, n_min=1, n_max=3):
    out = []
    for n in range(n_min, n_max+1):
        for i in range(len(toks)-n+1):
            out.append(" ".join(toks[i:i+n]))
    return out

# ---- 1. load vocabs ----
print("loading vocabs...")
def load_axis(path):
    s = set()
    try:
        with open(path) as f:
            for line in f:
                if line.startswith("#") or not line.strip(): continue
                t = line.split("\t")[0].strip().lower()
                if len(t) >= 2: s.add(t)
    except FileNotFoundError: pass
    return s

FORM_WORDS = load_axis(f"{RM}/axes/form.tsv")
CATEGORY_WORDS = load_axis(f"{RM}/axes/category.tsv")
FLAVOR_WORDS = load_axis(f"{RM}/axes/flavor_universal.tsv")
DIET_WORDS = load_axis(f"{RM}/axes/diet.tsv")
SWEETENER_WORDS = load_axis(f"{RM}/axes/sweetener.tsv")
STORAGE_WORDS = load_axis(f"{RM}/axes/storage.tsv")
PREP_WORDS = load_axis(f"{RM}/axes/preparation_state.tsv")
CUT_WORDS = load_axis(f"{RM}/axes/cut.tsv")
FAT_WORDS = load_axis(f"{RM}/axes/fat.tsv")

# Strong product-form signals (these are clearly the "what is it" tokens)
STRONG_FORM = {
    "sauce","syrup","butter","cereal","granola","oatmeal","cookie","biscuit","mix","dip",
    "dressing","marinade","glaze","bar","bowl","meal","kit","soup","juice","tea","coffee",
    "cracker","crackers","chip","chips","pasta","rice","beans","flour","sugar","oil",
    "vinegar","milk","cheese","yogurt","ice cream","sandwich","wrap","burrito","pizza",
    "bread","bun","roll","tortilla","muffin","cake","pie","brownie","candy","chocolate",
    "ketchup","mustard","mayo","mayonnaise","aioli","salsa","hummus","pectin","gelatin",
    "honey","molasses","jam","jelly","spread","creamer","powder","drink","beverage",
    "shake","smoothie","nog","eggnog","cocoa","pectin","relish","pickle","olive",
    "bacon","sausage","hot dog","corn dog","nugget","tender","wing","steak","roast",
    "pancake","waffle","french toast","biscotti","scone","croissant","danish",
    "noodle","noodles","macaroni","spaghetti","lasagna","ravioli","gnocchi",
    "egg roll","spring roll","pop tart","fruit snack","trail mix","granola bar","protein bar",
}
# bigrams that should win as product_form when present
STRONG_FORM_BIGRAMS = {bg for bg in STRONG_FORM if " " in bg}
STRONG_FORM_UNIGRAMS = {w for w in STRONG_FORM if " " not in w}

# ---- 2. pass 1: document frequency over titles ----
print("pass 1 — building ngram document frequency...")
t0 = time.time()
df = collections.Counter()
n_docs = 0
with open(IN_CSV) as f:
    for r in csv.DictReader(f):
        n_docs += 1
        seen = set(ngrams(tok(r['title']), 1, 3))
        for g in seen: df[g] += 1
print(f"  {n_docs:,} docs, {len(df):,} unique ngrams, {time.time()-t0:.1f}s")
idf = {g: math.log(n_docs / (1 + c)) for g, c in df.items()}

# ---- 3. pass 2: per-row evidence + role_candidates ----
print("\npass 2 — emitting role-tagged enrichment...")
t0 = time.time()

def role_candidates_for(g, evidence):
    """Apply heuristic rules to assign role candidates to one ngram."""
    roles = []
    has_form = evidence.get("contains_form_word")
    if has_form and has_form in STRONG_FORM:
        roles.append("possible_product_form")
    elif g in STRONG_FORM:
        roles.append("possible_product_form")
    if evidence.get("in_esha_head_segment"):
        roles.append("esha_head_match")
    if evidence.get("in_bfc"):
        roles.append("category_match")
    if evidence.get("in_ingredients") and "possible_product_form" not in roles:
        roles.append("possible_ingredient")
    if g in FLAVOR_WORDS or any(w in FLAVOR_WORDS for w in g.split()):
        roles.append("possible_modifier")
    if g in DIET_WORDS:
        roles.append("possible_diet_claim")
    if g in SWEETENER_WORDS:
        roles.append("possible_sweetener_claim")
    if g in STORAGE_WORDS:
        roles.append("possible_storage")
    if g in PREP_WORDS:
        roles.append("possible_prep")
    if g in CUT_WORDS:
        roles.append("possible_cut")
    if g in FAT_WORDS:
        roles.append("possible_fat_claim")
    if evidence.get("position") == "end" and "possible_product_form" not in roles:
        # rightmost ngrams are more likely to be the head
        if g in CATEGORY_WORDS:
            roles.append("possible_product_form")
    return list(dict.fromkeys(roles)) or ["unknown"]

def position_in(toks, ngram_tokens):
    """Return start/middle/end for where the ngram first appears."""
    if not toks: return "none"
    if not ngram_tokens: return "none"
    n = len(ngram_tokens)
    for i in range(len(toks)-n+1):
        if toks[i:i+n] == ngram_tokens:
            if i == 0: return "start"
            if i + n == len(toks): return "end"
            return "middle"
    return "none"

with open(IN_CSV) as fin, open(OUT_CSV, 'w', newline='') as fout:
    reader = csv.DictReader(fin)
    out_cols = list(reader.fieldnames) + [
        "title_ngrams_json",
        "role_candidates_json",
        "product_form_guess",
        "modifier_guesses",
        "ingredient_guesses",
        "form_word_in_title",
        "form_word_in_esha",
        "form_word_in_bfc",
        "llm_evidence_block",
    ]
    w = csv.DictWriter(fout, fieldnames=out_cols)
    w.writeheader()
    n_written = 0
    for r in reader:
        title = r['title'] or ''
        bfc   = (r.get('branded_food_category') or '').lower()
        cur_d = (r.get('current_esha_desc') or '').lower()
        ing_t = (r.get('ing_full') or '').lower()
        cur_d_head = cur_d.split(",")[0].strip() if cur_d else ""

        title_toks = tok(title)
        title_ngrams = ngrams(title_toks, 1, 3)
        # de-dupe (preserve first-seen order)
        seen_ng = list(dict.fromkeys(title_ngrams))

        # check form-word presence
        form_in_title = next((w for w in STRONG_FORM if w in title.lower()), "")
        form_in_esha  = next((w for w in STRONG_FORM if w in cur_d), "")
        form_in_bfc   = next((w for w in STRONG_FORM if w in bfc), "")

        ng_ev = {}     # ngram → evidence dict
        ng_roles = {}  # ngram → list of roles
        for g in seen_ng:
            g_toks = g.split()
            g_lower = g.lower()
            # which form-word does this ngram contain?
            contains_form = ""
            for fw in STRONG_FORM:
                if fw in g_lower or g_lower in fw:
                    contains_form = fw; break
                if g_lower == fw: contains_form = fw; break
            evidence = {
                "count":  df.get(g, 0),
                "tfidf":  round(title_ngrams.count(g) * idf.get(g, 0), 3),
                "in_title": True,
                "in_ingredients": (g in ing_t) if ing_t else False,
                "in_bfc": (g in bfc) if bfc else False,
                "in_esha_desc": (g in cur_d) if cur_d else False,
                "in_esha_head_segment": (g in cur_d_head) if cur_d_head else False,
                "position": position_in(title_toks, g_toks),
                "contains_form_word": contains_form,
            }
            ng_ev[g] = evidence
            ng_roles[g] = role_candidates_for(g, evidence)

        # pick best product_form_guess: highest tfidf among ngrams with possible_product_form
        form_candidates = [g for g, roles in ng_roles.items() if "possible_product_form" in roles]
        if form_candidates:
            # prefer end-position + bigram + esha_head_match
            def form_score(g):
                ev = ng_ev[g]
                s = 0.0
                if ev["position"] == "end": s += 2
                if " " in g: s += 1.5         # bigrams beat unigrams
                if g in STRONG_FORM_BIGRAMS: s += 2
                if ev["in_esha_head_segment"]: s += 2
                if ev["in_bfc"]: s += 1
                s += ev["tfidf"] / 10.0
                return s
            form_candidates.sort(key=lambda g: -form_score(g))
            product_form_guess = form_candidates[0]
        else:
            product_form_guess = ""

        modifier_guesses = [g for g, roles in ng_roles.items()
                            if ("possible_modifier" in roles or "possible_diet_claim" in roles)
                            and g != product_form_guess]
        ingredient_guesses = [g for g, roles in ng_roles.items()
                              if "possible_ingredient" in roles and g != product_form_guess]

        # build LLM evidence block — readable, compact
        llm_block_lines = [
            f"PRODUCT: {title}",
            f"BRAND: {r.get('brand_owner','')} / {r.get('brand_name','')}",
            f"RETAILER CATEGORY (BFC): {r.get('branded_food_category','')}",
            f"AUDIT ESHA DESCRIPTION: {r.get('current_esha_desc','')}",
            f"INGREDIENTS (top5): {r.get('ing_top5','')}",
            f"PROPOSED LEAF: {r.get('retail_leaf','')}  (cf={r.get('confidence','')})",
            f"PRODUCT FORM GUESS: {product_form_guess or '(none)'}",
            f"MODIFIER GUESSES: {' | '.join(modifier_guesses[:5]) or '(none)'}",
            f"INGREDIENT GUESSES: {' | '.join(ingredient_guesses[:5]) or '(none)'}",
            f"FORM WORD IN TITLE: {form_in_title or '(none)'}",
            f"FORM WORD IN ESHA: {form_in_esha or '(none)'}",
            f"FORM WORD IN BFC:  {form_in_bfc or '(none)'}",
            f"FNDDS-MODAL-SUPER: {r.get('fndds_modal_super','')} ({'match' if r.get('fndds_super_match')=='TRUE' else 'mismatch'})",
            f"BFC-MODAL-SUPER:   {r.get('bfc_modal_super','')} ({'match' if r.get('bfc_super_match')=='TRUE' else 'mismatch'})",
            f"BRAND-MODAL-SUPER: {r.get('brand_modal_super','')} ({'match' if r.get('brand_super_match')=='TRUE' else 'mismatch'})",
            f"SIBLINGS: same_leaf={r.get('siblings_same_leaf','0')} same_super={r.get('siblings_same_super','0')} total={r.get('siblings_total','0')}",
        ]
        llm_evidence_block = "\n".join(llm_block_lines)

        out = dict(r)
        out.update({
            "title_ngrams_json":  json.dumps(ng_ev, separators=(',', ':')),
            "role_candidates_json": json.dumps(ng_roles, separators=(',', ':')),
            "product_form_guess": product_form_guess,
            "modifier_guesses":   " | ".join(modifier_guesses[:6]),
            "ingredient_guesses": " | ".join(ingredient_guesses[:6]),
            "form_word_in_title": form_in_title,
            "form_word_in_esha":  form_in_esha,
            "form_word_in_bfc":   form_in_bfc,
            "llm_evidence_block": llm_evidence_block,
        })
        w.writerow(out)
        n_written += 1
        if n_written % 50000 == 0:
            print(f"  {n_written:>7,}  ({(time.time()-t0)/60:.1f}m)")

print(f"\nwrote {OUT_CSV}  ({n_written} rows, {(time.time()-t0)/60:.1f}m)")
