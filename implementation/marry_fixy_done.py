#!/usr/bin/env python3
"""Marry product_esha_fixy.csv with fixy_done/ ground truth.

Phases:
  1. Trust fixy_done fdc_id->FNDDS truth (overwrite + fill)
  2. Title propagation from fixy_done descriptions (exact-norm + first-3-tokens fallback)
  3. ESHA->FNDDS authority map (route ESHA codes to dominant FNDDS bucket)
  4. (deferred to v7) variant nuance reranking
  5. Residual unmapped output
"""
from __future__ import annotations
import os, csv, re, sys, glob, time
from collections import defaultdict, Counter

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
FIXY_DIR = os.path.join(ROOT, 'fixy_done')
IN_MAIN = os.path.join(ROOT, 'implementation/output/product_esha_fixy.csv')
OUT_DIR = os.path.join(ROOT, 'retail_mapper')
os.makedirs(OUT_DIR, exist_ok=True)

OUT_MAIN = os.path.join(OUT_DIR, 'product_esha_fixy.v6.csv')
OUT_AUTH = os.path.join(OUT_DIR, 'esha_to_fndds_authority.csv')
OUT_LOG  = os.path.join(OUT_DIR, 'fixy_v6_change_log.csv')
OUT_SUM  = os.path.join(OUT_DIR, 'fixy_v6_summary.txt')
OUT_UNM  = os.path.join(OUT_DIR, 'product_esha_fixy.v6.unmapped.csv')

csv.field_size_limit(sys.maxsize)

NORM_RE = re.compile(r'[^a-z0-9 ]+')
SPACE_RE = re.compile(r'\s+')
def norm(s: str) -> str:
    s = (s or '').lower()
    s = NORM_RE.sub(' ', s)
    s = SPACE_RE.sub(' ', s).strip()
    return s

def first_n_tokens(s: str, n: int) -> str:
    toks = s.split()
    return ' '.join(toks[:n])

def main():
    t0 = time.time()
    log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

    # ---- Load fixy_done ground truth ----
    log("Loading fixy_done/ ground truth...")
    truth_fid = {}                       # fdc_id -> fndds (first seen wins; we add multi-bucket awareness below)
    truth_fid_multi = defaultdict(set)   # fdc_id -> {fndds}
    truth_desc = {}                      # fndds -> sample description
    title_idx = defaultdict(Counter)     # norm(title) -> Counter[fndds]
    title3_idx = defaultdict(Counter)    # first-3-tokens -> Counter[fndds]
    fndds_files = glob.glob(os.path.join(FIXY_DIR, '*.csv'))
    for fpath in fndds_files:
        fndds_code = os.path.splitext(os.path.basename(fpath))[0]
        with open(fpath, newline='') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                fid = (row.get('fdc_id') or '').strip()
                desc = row.get('description') or ''
                if fid:
                    truth_fid_multi[fid].add(fndds_code)
                    truth_fid.setdefault(fid, fndds_code)
                if fndds_code not in truth_desc:
                    d = row.get('fndds_descripton') or row.get('fndds_description') or ''
                    if d:
                        truth_desc[fndds_code] = d
                nt = norm(desc)
                if nt:
                    title_idx[nt][fndds_code] += 1
                    t3 = first_n_tokens(nt, 3)
                    if t3:
                        title3_idx[t3][fndds_code] += 1
    log(f"  fdc_ids with truth: {len(truth_fid_multi):,}")
    log(f"  FNDDS codes covered: {len(truth_desc):,}")
    log(f"  unique normalized titles: {len(title_idx):,}")

    # ---- Read main file ----
    log("Reading main product_esha_fixy.csv...")
    with open(IN_MAIN, newline='') as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames[:]
        rows = list(reader)
    log(f"  rows: {len(rows):,}, columns: {len(fieldnames)}")

    # Add v6 audit columns
    extra_cols = ['v6_fndds_code', 'v6_fndds_description', 'v6_source', 'v6_changed', 'v6_old_fndds_code', 'v6_authority_override']
    out_fieldnames = fieldnames + [c for c in extra_cols if c not in fieldnames]

    # ---- Phase 1: ground-truth fdc_id ----
    log("Phase 1: applying fixy_done ground truth by fdc_id...")
    p1_overwrite = 0
    p1_fill = 0
    p1_agree = 0
    for r in rows:
        r['v6_fndds_code'] = r.get('fndds_main_code') or ''
        r['v6_fndds_description'] = r.get('fndds_main_description') or ''
        r['v6_source'] = r.get('fixy_match_source') or ''
        r['v6_changed'] = ''
        r['v6_old_fndds_code'] = ''
        r['v6_authority_override'] = ''
        fid = (r.get('fdc_id') or '').strip()
        if not fid or fid not in truth_fid_multi:
            continue
        truth_codes = truth_fid_multi[fid]
        cur = (r.get('fndds_main_code') or '').strip()
        if cur in truth_codes:
            r['v6_source'] = 'fixy_done_truth_agree'
            p1_agree += 1
        else:
            picked = sorted(truth_codes)[0]  # deterministic
            r['v6_old_fndds_code'] = cur
            r['v6_fndds_code'] = picked
            r['v6_fndds_description'] = truth_desc.get(picked, '')
            r['v6_source'] = 'fixy_done_truth_overwrite' if cur else 'fixy_done_truth_fill'
            r['v6_changed'] = '1'
            if cur:
                p1_overwrite += 1
            else:
                p1_fill += 1
    log(f"  agreed: {p1_agree:,}  overwrote: {p1_overwrite:,}  filled: {p1_fill:,}")

    # ---- Phase 2: title propagation ----
    log("Phase 2: title propagation (exact-norm + first-3-tokens)...")
    p2_exact = 0
    p2_fuzzy = 0
    for r in rows:
        if r['v6_source'].startswith('fixy_done_truth'):
            continue
        if r['v6_fndds_code']:
            continue  # already had something; we'll let phase 3 challenge it
        title = norm(r.get('product_description') or '')
        if not title:
            continue
        # Exact
        if title in title_idx:
            counter = title_idx[title]
            top, n = counter.most_common(1)[0]
            total = sum(counter.values())
            if n / total >= 0.6 and n >= 1:
                r['v6_fndds_code'] = top
                r['v6_fndds_description'] = truth_desc.get(top, '')
                r['v6_source'] = 'title_exact'
                r['v6_changed'] = '1'
                p2_exact += 1
                continue
        # First-3-tokens fallback
        t3 = first_n_tokens(title, 3)
        if t3 and t3 in title3_idx:
            counter = title3_idx[t3]
            top, n = counter.most_common(1)[0]
            total = sum(counter.values())
            if total >= 5 and n / total >= 0.7:
                r['v6_fndds_code'] = top
                r['v6_fndds_description'] = truth_desc.get(top, '')
                r['v6_source'] = 'title_fuzzy'
                r['v6_changed'] = '1'
                p2_fuzzy += 1
    log(f"  title_exact: {p2_exact:,}  title_fuzzy: {p2_fuzzy:,}")

    # Backfill: for rows that had a current FNDDS but no truth/title hit, KEEP existing as 'kept_existing'
    p_kept = 0
    for r in rows:
        if not r['v6_source']:
            cur = (r.get('fndds_main_code') or '').strip()
            if cur:
                r['v6_source'] = 'kept_existing'
                p_kept += 1
    log(f"  kept_existing (no truth, no title hit, had prior): {p_kept:,}")

    # ---- Phase 3: ESHA -> FNDDS authority ----
    log("Phase 3: building ESHA->FNDDS authority map...")
    esha_fndds_dist = defaultdict(Counter)
    esha_desc = {}
    # Only count rows whose v6 assignment came from a TRUSTED source (truth or title_exact)
    trusted_sources = {'fixy_done_truth_agree', 'fixy_done_truth_overwrite', 'fixy_done_truth_fill', 'title_exact'}
    for r in rows:
        ec = (r.get('best_esha_code') or '').strip()
        if not ec:
            continue
        if r['v6_source'] in trusted_sources and r['v6_fndds_code']:
            esha_fndds_dist[ec][r['v6_fndds_code']] += 1
            esha_desc.setdefault(ec, r.get('best_esha_description') or '')

    authority = {}  # ec -> (fndds, share, support)
    for ec, ctr in esha_fndds_dist.items():
        total = sum(ctr.values())
        top, n = ctr.most_common(1)[0]
        share = n / total
        if total >= 3 and share >= 0.6:
            authority[ec] = (top, share, total)
    log(f"  authoritative ESHA codes: {len(authority):,} of {len(esha_fndds_dist):,}")

    # Apply authority: for rows assigned via 'kept_existing' or 'title_fuzzy' or where v6_fndds disagrees with authority,
    # AND the row's product title does NOT strongly fit the current bucket, override.
    log("Phase 3 apply: routing ESHA-coded products to authoritative FNDDS bucket...")
    p3_overrides = 0
    for r in rows:
        ec = (r.get('best_esha_code') or '').strip()
        if not ec or ec not in authority:
            continue
        auth_fndds, share, support = authority[ec]
        cur = r['v6_fndds_code']
        if cur == auth_fndds:
            continue
        # Don't override truth-based assignments
        if r['v6_source'].startswith('fixy_done_truth_') or r['v6_source'] == 'title_exact':
            continue
        # Override
        r['v6_old_fndds_code'] = r['v6_old_fndds_code'] or cur
        r['v6_fndds_code'] = auth_fndds
        r['v6_fndds_description'] = truth_desc.get(auth_fndds, '')
        r['v6_authority_override'] = f"{ec}->{auth_fndds} (share={share:.2f}, n={support})"
        r['v6_source'] = (r['v6_source'] + '+esha_authority') if r['v6_source'] else 'esha_authority'
        r['v6_changed'] = '1'
        p3_overrides += 1
    log(f"  authority overrides: {p3_overrides:,}")

    # ---- Write outputs ----
    log("Writing v6 main file...")
    with open(OUT_MAIN, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=out_fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in out_fieldnames})

    log("Writing change log...")
    with open(OUT_LOG, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['fdc_id','gtin_upc','product_description','best_esha_code','best_esha_description',
                    'old_fndds_code','old_fndds_description','new_fndds_code','new_fndds_description',
                    'source','authority_note'])
        for r in rows:
            if r['v6_changed']:
                w.writerow([r.get('fdc_id',''), r.get('gtin_upc',''), r.get('product_description',''),
                            r.get('best_esha_code',''), r.get('best_esha_description',''),
                            r.get('v6_old_fndds_code') or r.get('fndds_main_code',''),
                            r.get('fndds_main_description',''),
                            r['v6_fndds_code'], r['v6_fndds_description'],
                            r['v6_source'], r['v6_authority_override']])

    log("Writing ESHA->FNDDS authority table...")
    with open(OUT_AUTH, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['best_esha_code','best_esha_description','authoritative_fndds_code','fndds_description','share','support_n','runners_up'])
        for ec, (fndds, share, support) in sorted(authority.items()):
            ctr = esha_fndds_dist[ec]
            top3 = ctr.most_common(3)
            runners = '; '.join(f"{c}:{n}" for c, n in top3[1:])
            w.writerow([ec, esha_desc.get(ec,''), fndds, truth_desc.get(fndds,''),
                        f"{share:.3f}", support, runners])

    log("Writing unmapped residual...")
    n_unmapped = 0
    with open(OUT_UNM, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=out_fieldnames)
        w.writeheader()
        for r in rows:
            if not r['v6_fndds_code']:
                w.writerow({k: r.get(k, '') for k in out_fieldnames})
                n_unmapped += 1
    log(f"  unmapped: {n_unmapped:,}")

    # ---- Summary ----
    src_counter = Counter(r['v6_source'] or 'none' for r in rows)
    changed = sum(1 for r in rows if r['v6_changed'])
    have_fndds = sum(1 for r in rows if r['v6_fndds_code'])

    summary = []
    summary.append(f"=== fixy v6 marry summary  ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===")
    summary.append(f"Input rows: {len(rows):,}")
    summary.append(f"Rows with v6 FNDDS assigned: {have_fndds:,}  ({100*have_fndds/len(rows):.1f}%)")
    summary.append(f"Rows changed vs original: {changed:,}  ({100*changed/len(rows):.1f}%)")
    summary.append(f"Unmapped: {n_unmapped:,}")
    summary.append("")
    summary.append("By source:")
    for k, v in src_counter.most_common():
        summary.append(f"  {k:40s}  {v:>10,}")
    summary.append("")
    summary.append(f"Authoritative ESHA codes: {len(authority):,}")
    summary.append(f"Phase 1 overwrites: {p1_overwrite:,}")
    summary.append(f"Phase 1 fills: {p1_fill:,}")
    summary.append(f"Phase 1 agrees: {p1_agree:,}")
    summary.append(f"Phase 2 title_exact: {p2_exact:,}")
    summary.append(f"Phase 2 title_fuzzy: {p2_fuzzy:,}")
    summary.append(f"Phase 3 authority overrides: {p3_overrides:,}")
    summary.append("")
    summary.append("Outputs:")
    summary.append(f"  {OUT_MAIN}")
    summary.append(f"  {OUT_LOG}")
    summary.append(f"  {OUT_AUTH}")
    summary.append(f"  {OUT_UNM}")
    text = '\n'.join(summary)
    with open(OUT_SUM, 'w') as fh:
        fh.write(text + '\n')
    log("DONE")
    print('\n' + text)

if __name__ == '__main__':
    main()
