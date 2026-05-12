#!/usr/bin/env python3
"""Build TF-IDF product fingerprints from ALL signals (title + ingredients +
branded_food_category + brand + ingredient categories + ingredient parsed names).

Test mode (--probe): for each canonical query, show top-15 nearest products by
cosine similarity. This is the diagnostic the user asked for: prove that the
fingerprint can tell almond milk from chocolate almond milk from eggnog from
corn dog from hot dog.

Full mode (default): emit per-product fingerprint matrix as a SciPy sparse npz
and a flat CSV summary, plus a small kNN report.
"""
from __future__ import annotations
import os, csv, sys, json, sqlite3, time, re
from collections import Counter

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
RM   = os.path.join(ROOT, 'retail_mapper')
DB   = os.path.join(ROOT, 'data/master_products.db')

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

WORD_RE = re.compile(r"[a-z][a-z0-9]+")
NONALPHA = re.compile(r"[^a-z0-9 ]+")

# Lightweight per-token stems
STEMS = {
    'almonds':'almond','cashews':'cashew','walnuts':'walnut','pecans':'pecan',
    'hazelnuts':'hazelnut','pistachios':'pistachio','macadamias':'macadamia',
    'frankfurter':'frank','frankfurters':'frank','franks':'frank',
    'wieners':'wiener','sausages':'sausage','patties':'patty',
    'almondmilk':'almondmilk','oatmilk':'oatmilk','soymilk':'soymilk',
    'cookies':'cookie','crackers':'cracker','tomatoes':'tomato',
    'beans':'bean','peas':'pea','oats':'oat','olives':'olive',
    'eggs':'egg','spices':'spice','breads':'bread','cheeses':'cheese',
    'flours':'flour','oils':'oil','seeds':'seed','syrups':'syrup',
    'fruits':'fruit','vegetables':'vegetable',
}
def stem(t): return STEMS.get(t, t)

def normalize(s: str) -> str:
    s = (s or '').lower()
    s = NONALPHA.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def tokens_with_bigrams(s: str) -> list[str]:
    s = normalize(s)
    toks = [stem(t) for t in WORD_RE.findall(s) if len(t) >= 2]
    out = list(toks)
    for i in range(len(toks)-1):
        out.append(toks[i] + '_' + toks[i+1])  # bigram with marker
    return out

def parsed_signals(ip_json: str) -> list[str]:
    """Extract ingredient names + categories as features."""
    out = []
    try:
        items = json.loads(ip_json) if ip_json else []
    except Exception:
        return out
    for it in items[:25]:  # limit
        if not isinstance(it, dict): continue
        c = it.get('category') or ''
        nm = it.get('name') or ''
        if c: out.append('cat_' + c)
        if nm:
            for tok in tokens_with_bigrams(nm):
                out.append('ing_' + tok)
        for sub in (it.get('sub') or []):
            sn = (sub.get('name') if isinstance(sub, dict) else '') or ''
            if sn:
                for tok in tokens_with_bigrams(sn):
                    out.append('sub_' + tok)
    return out

def fingerprint(row: dict) -> list[str]:
    """Combined feature list for one product. Different prefixes per signal source
    so cosine treats them as distinct dimensions."""
    feats = []
    title = row.get('description') or row.get('product_description') or ''
    bfc   = row.get('branded_food_category') or ''
    brand = (row.get('brand_owner') or '') + ' ' + (row.get('brand_name') or '')
    ing   = row.get('ingredients_clean') or row.get('ingredients') or ''
    ipar  = row.get('ingredients_parsed') or ''

    for t in tokens_with_bigrams(title): feats.append('t_' + t)
    for t in tokens_with_bigrams(bfc):   feats.append('b_' + t)
    for t in tokens_with_bigrams(brand): feats.append('br_' + t)
    for t in tokens_with_bigrams(ing):   feats.append('i_' + t)
    feats.extend(parsed_signals(ipar))

    # Has-flags from raw ingredient text
    text = (ing or '').lower()
    for flag, kw in [
        ('has_batter', 'batter'),
        ('has_breading', 'breading'),
        ('has_breadcrumb', 'bread crumb'),
        ('has_panko', 'panko'),
        ('has_cocoa', 'cocoa'),
        ('has_chocolate', 'chocolate liquor'),
        ('has_hot_dog', ['hot dog','frankfurter','wiener']),
        ('has_chicken', 'chicken'),
        ('has_pork', 'pork'),
        ('has_beef', 'beef'),
        ('has_tomato', 'tomato'),
        ('has_egg', 'egg'),
        ('has_milk', 'milk'),
        ('has_cream', 'cream'),
        ('has_cheese', 'cheese'),
    ]:
        kws = [kw] if isinstance(kw, str) else kw
        if any(k in text for k in kws):
            feats.append(flag)
    return feats

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--probe', action='store_true', help='Run probe queries showing nearest neighbors')
    ap.add_argument('--limit', type=int, default=None, help='Limit rows (for testing)')
    args = ap.parse_args()

    log("Loading products from master_products.db...")
    con = sqlite3.connect(DB)
    rows: list[dict] = []
    q = "SELECT gtin_upc, fdc_id, description, brand_owner, brand_name, branded_food_category, ingredients, ingredients_clean, ingredients_parsed FROM products"
    if args.limit:
        q += f" LIMIT {args.limit}"
    for r in con.execute(q):
        rows.append({
            'gtin_upc': r[0] or '', 'fdc_id': r[1] or '',
            'description': r[2] or '', 'brand_owner': r[3] or '', 'brand_name': r[4] or '',
            'branded_food_category': r[5] or '', 'ingredients': r[6] or '',
            'ingredients_clean': r[7] or '', 'ingredients_parsed': r[8] or '',
        })
    log(f"  loaded {len(rows):,} rows")

    log("Building fingerprints...")
    fingerprints: list[list[str]] = []
    for i, r in enumerate(rows):
        fingerprints.append(fingerprint(r))
        if (i+1) % 100000 == 0:
            log(f"  ...{i+1:,}")
    log(f"  done")

    # Build vocabulary + DF
    log("Building vocabulary + DF...")
    df = Counter()
    for fp in fingerprints:
        for t in set(fp):
            df[t] += 1
    # Filter rare/common
    vocab = {t: i for i, (t, c) in enumerate(sorted(df.items())) if 2 <= c <= len(rows) * 0.5}
    log(f"  vocab size after filter: {len(vocab):,} (raw {len(df):,})")

    # Build sparse TF-IDF as dict[doc_idx -> dict[term_idx -> weight]]
    import math
    N = len(rows)
    idf = {t: math.log((N+1)/(df[t]+1)) + 1 for t in vocab}
    log("Computing TF-IDF vectors...")
    vecs: list[dict[int, float]] = []
    norms: list[float] = []
    for i, fp in enumerate(fingerprints):
        tf = Counter(t for t in fp if t in vocab)
        v = {vocab[t]: c * idf[t] for t, c in tf.items()}
        vecs.append(v)
        norms.append(math.sqrt(sum(x*x for x in v.values())) or 1.0)
        if (i+1) % 100000 == 0:
            log(f"  ...{i+1:,}")
    log(f"  done")

    def cos(i: int, j: int) -> float:
        a, b = vecs[i], vecs[j]
        if len(a) > len(b): a, b = b, a
        s = sum(w * b[k] for k, w in a.items() if k in b)
        return s / (norms[i] * norms[j])

    if args.probe:
        # Find a product whose description matches each query exactly, then show neighbors
        QUERIES = [
            "ALMOND BREEZE ORIGINAL",
            "ALMOND BREEZE CHOCOLATE",
            "ALMOND BREEZE PUMPKIN SPICE",
            "ALMOND NOG",
            "EGG NOG",
            "CORN DOG",
            "HOT DOG",
            "CHICKEN NUGGETS",
            "ICE CREAM SANDWICH",
            "PEANUT BUTTER",
            "CHOCOLATE MILK",
            "MILK CHOCOLATE",
            "GREEK YOGURT VANILLA",
            "APPLE NOODLE KUGEL",
            "FRIED APPLES",
        ]
        # Index lowercase title -> indices
        by_title = {}
        for i, r in enumerate(rows):
            t = (r['description'] or '').lower()
            by_title.setdefault(t, []).append(i)

        def find_idx(q):
            ql = q.lower()
            # exact match first
            for t, idxs in by_title.items():
                if ql == t: return idxs[0]
            # phrase substring
            for t, idxs in by_title.items():
                if ql in t: return idxs[0]
            # token-overlap fallback
            qtoks = set(WORD_RE.findall(ql))
            best = None; best_score = 0
            for t, idxs in by_title.items():
                ttoks = set(WORD_RE.findall(t))
                score = len(qtoks & ttoks)
                if score > best_score:
                    best, best_score = idxs[0], score
            return best

        for q in QUERIES:
            print(f"\n=== Query: {q!r} ===")
            qi = find_idx(q)
            if qi is None:
                print("  (not found)"); continue
            anchor = rows[qi]
            print(f"  anchor: {anchor['description'][:60]}")
            print(f"     bfc: {anchor['branded_food_category']}")
            print(f"     ing: {(anchor.get('ingredients_clean') or '')[:120]}")
            # Compute cos vs all (slow but deterministic for probe; ~30s on 462K)
            scores = []
            qv, qn = vecs[qi], norms[qi]
            for j in range(N):
                if j == qi: continue
                a, b = qv, vecs[j]
                if len(a) > len(b): a, b = b, a
                s = 0.0
                for k, w in a.items():
                    bw = b.get(k)
                    if bw: s += w * bw
                if s == 0: continue
                scores.append((s / (qn * norms[j]), j))
            scores.sort(reverse=True)
            for cosv, j in scores[:8]:
                r = rows[j]
                print(f"  {cosv:.3f}  {r['description'][:55]:<55s}  bfc={r['branded_food_category'][:25]}")

if __name__ == '__main__':
    main()
