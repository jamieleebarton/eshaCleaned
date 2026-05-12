#!/usr/bin/env python3
"""P1 — Unassigned-token discovery.

Loads all axis seed TSVs, tokenizes every product title (after applying
spelling merges), and emits:
  discovery/unassigned_tokens.csv  — every token NOT in any seed, ranked by frequency,
                                     with sample titles + top branded_food_categories
  discovery/coverage_summary.txt   — coverage % per axis, total mass covered, residual
  discovery/unassigned_2grams.csv  — high-frequency 2-grams not covered by axis 2-grams
"""
from __future__ import annotations
import os, csv, sys, re, time
from collections import Counter, defaultdict

RM   = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ROOT = os.path.dirname(RM)
AX   = os.path.join(RM, 'axes')
OUT  = os.path.join(RM, 'discovery')
os.makedirs(OUT, exist_ok=True)

IN_MAIN = os.path.join(RM, 'product_esha_fixy.v6.csv')

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

# ---- load axis TSVs ----
def load_tokens(path: str, col: int = 0) -> set[str]:
    if not os.path.exists(path):
        return set()
    out = set()
    with open(path, newline='') as fh:
        for line in fh:
            line = line.rstrip('\n')
            if not line or line.startswith('#'): continue
            parts = line.split('\t')
            if len(parts) > col:
                tok = parts[col].strip().lower()
                if tok:
                    out.add(tok)
    return out

axis_files = {
    'FORM':              'form.tsv',
    'CUT':               'cut.tsv',
    'STORAGE':           'storage.tsv',
    'PREPARATION_STATE': 'preparation_state.tsv',
    'SWEETENER':         'sweetener.tsv',
    'FAT':               'fat.tsv',
    'SODIUM':            'sodium.tsv',
    'DIET':              'diet.tsv',
    'AUDIENCE':          'audience.tsv',
    'DISH_TYPE':         'dish_type.tsv',
    'COMBO_FORMAT':      'combo_format.tsv',
    'FLAVOR_UNIVERSAL':  'flavor_universal.tsv',
    'CATEGORY':          'category.tsv',
    'COLOR':             'color.tsv',
    'CUISINE':           'cuisine.tsv',
    'BRAND_NOISE':       'brand_noise.tsv',
    'STOPWORD':          'stopwords.tsv',
}

def axis_paths() -> list[str]:
    paths = {os.path.join(AX, f) for f in axis_files.values()}
    paths.add(os.path.join(AX, 'spelling.tsv'))
    return sorted(paths)

def snapshot_axis_files() -> dict[str, int | None]:
    snap: dict[str, int | None] = {}
    for path in axis_paths():
        try:
            snap[path] = os.stat(path).st_mtime_ns
        except FileNotFoundError:
            snap[path] = None
    return snap

def changed_axis_files(before: dict[str, int | None], after: dict[str, int | None]) -> list[str]:
    changed: list[str] = []
    for path in sorted(set(before) | set(after)):
        if before.get(path) != after.get(path):
            changed.append(os.path.basename(path))
    return changed

axis_snapshot = snapshot_axis_files()
axis_tokens: dict[str, set[str]] = {}
for ax, f in axis_files.items():
    axis_tokens[ax] = load_tokens(os.path.join(AX, f))
    log(f"  {ax:18s} {len(axis_tokens[ax]):>6,} tokens")

# Reverse map: token -> first axis that claims it
TOKEN_AXIS: dict[str, str] = {}
PRIORITY = [
    'STOPWORD','BRAND_NOISE','STORAGE','PREPARATION_STATE','CUT','DISH_TYPE','COMBO_FORMAT',
    'SWEETENER','FAT','SODIUM','DIET','AUDIENCE','COLOR','CUISINE',
    'FORM','CATEGORY','FLAVOR_UNIVERSAL'
]
for ax in PRIORITY:
    for t in axis_tokens[ax]:
        TOKEN_AXIS.setdefault(t, ax)

# Spelling merges
spelling_pairs: list[tuple[str,str]] = []
sp_path = os.path.join(AX, 'spelling.tsv')
with open(sp_path) as fh:
    for line in fh:
        line = line.rstrip('\n')
        if not line or line.startswith('#'): continue
        parts = line.split('\t')
        if len(parts) >= 2 and parts[0].strip() and parts[1].strip():
            spelling_pairs.append((parts[0].strip().lower(), parts[1].strip().lower()))
spelling_pairs.sort(key=lambda kv: -len(kv[0]))
log(f"  spelling merges: {len(spelling_pairs)}")

WORD_RE = re.compile(r"[a-z][a-z0-9]+")
NONALPHA_RE = re.compile(r"[^a-z0-9 ]+")

def normalize_title(s: str) -> str:
    s = (s or '').lower()
    s = NONALPHA_RE.sub(' ', s)
    s = re.sub(r"\s+", " ", s).strip()
    # Use word-boundary regex so "unsweet" doesn't eat "unsweetened"
    for src, dst in spelling_pairs:
        s = re.sub(rf"\b{re.escape(src)}\b", dst, s)
    return s

# ---- scan corpus ----
log("Scanning corpus...")
freq = Counter()
two_freq = Counter()
title_count = 0
sample_titles: dict[str, list[str]] = defaultdict(list)
top_cat: dict[str, Counter] = defaultdict(Counter)
two_sample: dict[tuple[str,str], list[str]] = defaultdict(list)

axis_mass = Counter()
total_mass = 0

with open(IN_MAIN, newline='') as fh:
    reader = csv.DictReader(fh)
    for r in reader:
        title_count += 1
        raw = r.get('product_description') or ''
        cat = (r.get('branded_food_category') or '').strip()
        norm = normalize_title(raw)
        toks = [t for t in WORD_RE.findall(norm) if len(t) >= 2]
        for t in toks:
            freq[t] += 1
            ax = TOKEN_AXIS.get(t)
            if ax:
                axis_mass[ax] += 1
            else:
                if len(sample_titles[t]) < 5:
                    sample_titles[t].append(raw[:90])
                top_cat[t][cat] += 1
            total_mass += 1
        for i in range(len(toks)-1):
            bg = (toks[i], toks[i+1])
            two_freq[bg] += 1
            if not (TOKEN_AXIS.get(bg[0]) and TOKEN_AXIS.get(bg[1])):
                if len(two_sample[bg]) < 3:
                    two_sample[bg].append(raw[:90])

log(f"Titles: {title_count:,}  unique tokens: {len(freq):,}  total token mass: {total_mass:,}")

changed_axes = changed_axis_files(axis_snapshot, snapshot_axis_files())
if changed_axes:
    log("Axis files changed during scan; refusing to write stale discovery outputs.")
    log("Changed files: " + ", ".join(changed_axes))
    log("Rerun after axis edits settle.")
    sys.exit(2)

# ---- per-axis coverage report ----
log("Writing coverage_summary.txt...")
covered = sum(axis_mass.values())
unassigned_mass = total_mass - covered
top_unassigned_mass = 0
unassigned_freq = Counter({t:n for t,n in freq.items() if t not in TOKEN_AXIS})

# Strip pure noise: tokens that are 2 chars and only occur in numeric-size context — already in stopwords.
# Compute top-token mass
top_unassigned_mass = sum(n for _, n in unassigned_freq.most_common(500))

with open(os.path.join(OUT, 'coverage_summary.txt'), 'w') as fh:
    fh.write(f"=== P1 token coverage  ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
    fh.write(f"Titles scanned:    {title_count:>10,}\n")
    fh.write(f"Unique tokens:     {len(freq):>10,}\n")
    fh.write(f"Total token mass:  {total_mass:>10,}\n")
    fh.write(f"Mass covered:      {covered:>10,}  ({100*covered/total_mass:.1f}%)\n")
    fh.write(f"Mass unassigned:   {unassigned_mass:>10,}  ({100*unassigned_mass/total_mass:.1f}%)\n")
    fh.write(f"Top-500 unassigned mass: {top_unassigned_mass:>10,}\n")
    fh.write("\n--- Per-axis mass ---\n")
    for ax, n in axis_mass.most_common():
        fh.write(f"  {ax:>18s}  {n:>10,}  ({100*n/total_mass:.1f}%)\n")
    fh.write("\n--- Top 30 unassigned tokens (head sample) ---\n")
    for t, n in unassigned_freq.most_common(30):
        cats = top_cat[t].most_common(2)
        cat_str = '; '.join(f"{c}={cn}" for c, cn in cats) if cats else ''
        fh.write(f"  {n:>7,}  {t:<24s}  cats: {cat_str}\n")

# ---- emit unassigned_tokens.csv ----
log("Writing unassigned_tokens.csv...")
proposed = []
# Heuristic axis-suggestion based on prefix/suffix patterns + co-occurring tokens
SUGGEST_HINT = [
    (re.compile(r'free$'),  'DIET (compound — likely _-free)'),
    (re.compile(r'less$'),  'DIET (compound — _less)'),
    (re.compile(r'flavored?$'), 'FLAVOR'),
    (re.compile(r'(ed|ing)$'), 'PREPARATION_STATE/CUT (verb-form)'),
]
def suggest_axis(t: str, n: int) -> str:
    for pat, label in SUGGEST_HINT:
        if pat.search(t):
            return label
    return ''

with open(os.path.join(OUT, 'unassigned_tokens.csv'), 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['rank','token','frequency','suggested_axis','top_categories','sample_titles'])
    for rank, (t, n) in enumerate(unassigned_freq.most_common(2000), 1):
        cats = top_cat[t].most_common(3)
        cats_str = ' | '.join(f"{c}={cn}" for c, cn in cats)
        samples = ' || '.join(sample_titles[t][:3])
        w.writerow([rank, t, n, suggest_axis(t, n), cats_str, samples])

# ---- emit unassigned_2grams.csv (top 1000) ----
log("Writing unassigned_2grams.csv...")
unassigned_two = [(bg, n) for bg, n in two_freq.most_common(5000)
                  if not (TOKEN_AXIS.get(bg[0]) == 'STOPWORD' and TOKEN_AXIS.get(bg[1]) == 'STOPWORD')
                  and (bg[0] not in TOKEN_AXIS or bg[1] not in TOKEN_AXIS)]
with open(os.path.join(OUT, 'unassigned_2grams.csv'), 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['rank','token1','token2','frequency','axis_token1','axis_token2','sample_titles'])
    for rank, (bg, n) in enumerate(unassigned_two[:1000], 1):
        w.writerow([rank, bg[0], bg[1], n,
                    TOKEN_AXIS.get(bg[0],''), TOKEN_AXIS.get(bg[1],''),
                    ' || '.join(two_sample[bg][:2])])

# ---- emit per-axis token list (so user can see what's already claimed) ----
log("Writing axis_token_dump.csv...")
with open(os.path.join(OUT, 'axis_token_dump.csv'), 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['axis','token','frequency'])
    for ax in PRIORITY:
        for t in sorted(axis_tokens[ax]):
            w.writerow([ax, t, freq.get(t, 0)])

log("DONE")
