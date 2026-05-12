#!/usr/bin/env python3
"""Re-process consensus_taxonomy.csv with a fixed agreement metric.

For each product:
  - canonical_leaf = v6_fndds_description (or v6_esha_description fallback)
  - For each other signal, compute token-overlap with canonical_leaf
  - support_count = # of signals sharing ≥2 content tokens with canonical
  - confidence = high (≥4 support), medium (2-3), low (<2)
  - leaf_with_facets = canonical_leaf + ' [' + parser_form + '|' + parser_flavor + '|' + parser_cut + ']'
"""
from __future__ import annotations
import os, sys, csv, re, time
from collections import Counter

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
RM   = os.path.join(ROOT, 'retail_mapper')
IN   = os.path.join(RM, 'consensus_taxonomy.csv')
OUT_MAIN = os.path.join(RM, 'consensus_taxonomy_v2.csv')
OUT_HIGH = os.path.join(RM, 'consensus_taxonomy_v2_high_confidence.csv')
OUT_LOW  = os.path.join(RM, 'consensus_taxonomy_v2_audit.csv')
OUT_SUMM = os.path.join(RM, 'consensus_taxonomy_v2_summary.txt')

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

WORD_RE = re.compile(r'[a-z][a-z0-9]+')
NOISE = {'and','of','the','a','with','to','from','for','no','non','organic','natural',
         'flavor','flavors','original','classic','new','family','size','large','small',
         'mini','pack','count','oz','fl','lb','lbs','contains','less','than','enriched',
         'filtered','assorted','plain','sweetened','unsweetened','reduced','low','high',
         'fat','sugar','salt','free','added','style','prepared','as','to','type','nfs',
         'ns','fs','ns,','to','is','it','flavor,','from','jamie','grade','only','very'}
def content_tokens(s: str) -> set[str]:
    return {t for t in WORD_RE.findall((s or '').lower()) if t not in NOISE and len(t) > 2}

def overlap(a: str, b: str) -> int:
    return len(content_tokens(a) & content_tokens(b))

log(f"Reading {IN}...")
n_total = 0
n_high = n_med = n_low = 0
support_dist = Counter()
super_dist = Counter()
canonical_source_dist = Counter()

with open(IN, newline='') as src, \
     open(OUT_MAIN, 'w', newline='') as out_main, \
     open(OUT_HIGH, 'w', newline='') as out_high, \
     open(OUT_LOW, 'w', newline='') as out_low:
    reader = csv.DictReader(src)
    in_cols = reader.fieldnames[:]
    new_cols = ['canonical_leaf','canonical_source','support_count','support_signals',
                'leaf_with_facets','confidence_v2']
    out_cols = in_cols + new_cols
    main_w = csv.DictWriter(out_main, fieldnames=out_cols); main_w.writeheader()
    high_w = csv.DictWriter(out_high, fieldnames=out_cols); high_w.writeheader()
    low_w  = csv.DictWriter(out_low,  fieldnames=out_cols); low_w.writeheader()

    for r in reader:
        n_total += 1
        # Canonical leaf preference: v6 fndds (curated truth) > v6 esha > funnel tree > parser leaf > embed > ingredient
        canonical = ''
        canonical_source = ''
        for src_label, val in [
            ('v6_fndds', r.get('S1_v6_fndds_desc','')),
            ('v6_esha',  r.get('S2_v6_esha_desc','')),
            ('funnel_tree', r.get('S6_funnel_tree_label','')),
            ('parser', r.get('S11b_parser_retail_leaf','')),
            ('embed', r.get('S12_embed_top_esha_desc','')),
            ('ingredient', r.get('S13_ingredient_top_fndds_desc','')),
        ]:
            if val and val.strip():
                canonical = val; canonical_source = src_label; break
        canonical_source_dist[canonical_source] += 1

        # Count signals that SUPPORT canonical (share >=2 content tokens)
        sigs_to_check = [
            ('v6_fndds', r.get('S1_v6_fndds_desc','')),
            ('v6_esha',  r.get('S2_v6_esha_desc','')),
            ('funnel',   r.get('S6_funnel_tree_label','')),
            ('parser',   r.get('S11b_parser_retail_leaf','')),
            ('embed',    r.get('S12_embed_top_esha_desc','')),
            ('ingredient', r.get('S13_ingredient_top_fndds_desc','')),
        ]
        support = []
        opposed = []
        for name, val in sigs_to_check:
            if not val or name == canonical_source: continue
            ov = overlap(canonical, val)
            if ov >= 2: support.append(name)
            elif overlap(canonical, val) == 1 and len(content_tokens(val)) >= 2: support.append(name+'?')
            elif val.strip(): opposed.append(name)
        support_count = sum(1 for s in support if not s.endswith('?'))
        support_signals = '|'.join(support)

        # Build leaf_with_facets
        facets = []
        if r.get('S10_parser_form'): facets.append(r['S10_parser_form'])
        if r.get('S11_parser_flavor'): facets.append(r['S11_parser_flavor'])
        # try other facets from parsed_titles via inference (form/flavor are in there)
        leaf_with_facets = canonical
        if facets:
            leaf_with_facets += ' [' + '|'.join(f for f in facets if f) + ']'

        # Confidence
        if support_count >= 3: conf = 'high'; n_high += 1
        elif support_count >= 1: conf = 'medium'; n_med += 1
        else: conf = 'low'; n_low += 1
        support_dist[support_count] += 1
        super_dist[r.get('consensus_supercategory','')] += 1

        new_vals = {
            'canonical_leaf': canonical,
            'canonical_source': canonical_source,
            'support_count': support_count,
            'support_signals': support_signals,
            'leaf_with_facets': leaf_with_facets,
            'confidence_v2': conf,
        }
        out = {**r, **new_vals}
        main_w.writerow(out)
        if conf == 'high':
            high_w.writerow(out)
        elif conf == 'low':
            low_w.writerow(out)

        if n_total % 100000 == 0:
            log(f"  ...{n_total:,}")

log("DONE")
log(f"\nTotal: {n_total:,}")
log(f"Confidence v2:  high={n_high:,} ({100*n_high/n_total:.1f}%)  medium={n_med:,} ({100*n_med/n_total:.1f}%)  low={n_low:,} ({100*n_low/n_total:.1f}%)")
log(f"\nSupport count distribution (# signals supporting canonical leaf):")
for k in sorted(support_dist):
    log(f"  {k}: {support_dist[k]:,}")
log(f"\nCanonical leaf source:")
for s, c in canonical_source_dist.most_common():
    log(f"  {s}: {c:,}")
log(f"\nFiles:\n  {OUT_MAIN}\n  {OUT_HIGH}\n  {OUT_LOW}")

with open(OUT_SUMM, 'w') as fh:
    fh.write(f"=== consensus_taxonomy_v2  ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===\n\n")
    fh.write(f"Total products: {n_total:,}\n")
    fh.write(f"Confidence v2:  high={n_high:,} ({100*n_high/n_total:.1f}%)  medium={n_med:,} ({100*n_med/n_total:.1f}%)  low={n_low:,} ({100*n_low/n_total:.1f}%)\n\n")
    fh.write("Support count (# signals supporting canonical leaf):\n")
    for k in sorted(support_dist):
        fh.write(f"  {k}: {support_dist[k]:,}\n")
    fh.write("\nCanonical leaf source:\n")
    for s, c in canonical_source_dist.most_common():
        fh.write(f"  {s}: {c:,}\n")
    fh.write("\nConsensus supercategory distribution:\n")
    for s, c in super_dist.most_common(30):
        fh.write(f"  {c:>8,}  {s}\n")
