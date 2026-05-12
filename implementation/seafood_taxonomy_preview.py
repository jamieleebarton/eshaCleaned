#!/usr/bin/env python3
"""
Seafood-only data-driven taxonomy.

Priority of signals (per user): category → ingredients → title.
- Category is the HARD FILTER (already-applied — only fish/seafood categories included)
- Embedding text built as: INGREDIENTS first, then TITLE, then BRAND.
- Cluster naturally; show what falls out.

Only touches the preview file. vIdentity.csv is NOT modified.
"""
import csv, os, pickle, re, sqlite3, sys
from collections import Counter, defaultdict

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
CANON = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.csv"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"
DB = f"{ROOT}/data/master_products.db"
CACHE_DIR = f"{ROOT}/implementation/.embed_cache"
TREE_EMB = f"{CACHE_DIR}/tree_emb.npy"
TREE_CODES_PKL = f"{CACHE_DIR}/tree_codes.pkl"
OUT_MD = f"{ROOT}/implementation/output/seafood_taxonomy_preview.md"

# Match any category that's clearly fish/seafood/shellfish
SEAFOOD_PAT = re.compile(r"(fish|seafood|shellfish|salmon|tuna|crab|shrimp|lobster|oyster|sushi)", re.I)

STOP = set("""
with and the of to in for by on at from as or an a is are be this that
prepared made mix pack oz fl ounce ounces pound pounds lb each ct count
size family large small medium big jumbo mini package bag box bottle jar
can cup cups piece pieces container kit free added without none new original
ready fresh frozen dry dried cooked raw fried baked grilled whole sliced
diced chopped crushed low high reduced light lite extra plus value my our
their no not real food brand product item items premium quality natural
all variety serving servings flavor flavors flavored containing total
contains made type style classic select selection traditional taste tasty
delicious gourmet artisan fine sweet tangy spicy mild hot bold rich smooth
crispy crunchy soft tender tough thick thin fancy organic gluten authentic
""".split())

def tokens(s):
    if not s: return []
    return [t for t in re.findall(r"[a-z][a-z]+", s.lower()) if len(t) >= 4 and t not in STOP]

def main():
    print("Loading map and filtering to seafood/fish categories...", flush=True)
    rows = []
    cats_seen = Counter()
    with open(CANON) as f:
        for r in csv.DictReader(f):
            cat = r.get("branded_food_category","")
            if SEAFOOD_PAT.search(cat or ""):
                rows.append(r)
                cats_seen[cat] += 1
    print(f"  {len(rows):,} seafood rows, across {len(cats_seen)} branded categories")
    print("\nCategories included:")
    for c, n in cats_seen.most_common():
        print(f"  {n:>6,}  {c}")

    if not rows:
        print("No rows. Aborting.")
        return

    # Pull ingredients
    print("\nLoading ingredients from master_products.db...", flush=True)
    con = sqlite3.connect(DB)
    ids = [r["fdc_id"] for r in rows]
    ing_map = {}
    chunk = 1000
    for i in range(0, len(ids), chunk):
        sl = ids[i:i+chunk]
        ph = ",".join("?"*len(sl))
        for fid, ing in con.execute(f"SELECT fdc_id, ingredients FROM products WHERE fdc_id IN ({ph})", sl):
            ing_map[str(fid)] = (ing or "").strip()
    con.close()
    have_ing = sum(1 for r in rows if ing_map.get(r["fdc_id"]))
    print(f"  ingredients found for {have_ing:,}/{len(rows):,}")

    # Build embedding text — INGREDIENTS first, then title, then brand
    print("\nBuilding embedding text (ingredients > title > brand)...", flush=True)
    embed_texts = []
    for r in rows:
        ing = ing_map.get(r["fdc_id"], "")[:400]
        title = r.get("product_description","")
        brand = r.get("brand_name","")
        # Heavy weight on ingredients by leading with them; pad with title for products
        # without ingredients
        text = " ".join(filter(None, [ing, title, brand])).strip()
        embed_texts.append(text or title or "unknown")

    # Embed with sentence-transformers (only this slice — fast)
    print("Embedding (sentence-transformers MiniLM-L6-v2)...", flush=True)
    from sentence_transformers import SentenceTransformer
    import numpy as np
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
    sub = model.encode(embed_texts, batch_size=256, show_progress_bar=True,
                       convert_to_numpy=True, normalize_embeddings=True)
    print(f"  embeddings shape: {sub.shape}")

    # Cluster within ALL seafood — let groups form naturally across categories
    # since they're all "fish & seafood" anyway
    print("\nClustering (HDBSCAN, min_cluster_size=5)...", flush=True)
    from sklearn.cluster import HDBSCAN
    clusterer = HDBSCAN(min_cluster_size=5, min_samples=3, metric="cosine", copy=True)
    labels = clusterer.fit_predict(sub.astype(np.float64))
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = (labels == -1).sum()
    print(f"  → {n_clusters:,} natural clusters, {n_noise:,} unclustered")

    # Tree alignment
    tree_emb = np.load(TREE_EMB)
    with open(TREE_CODES_PKL, "rb") as f: tree_codes = pickle.load(f)
    code_to_desc = {c: d for c, d in tree_codes}
    code_list = [c for c, _ in tree_codes]

    # Group clusters and describe each
    cluster_to_idxs = defaultdict(list)
    for i, lbl in enumerate(labels):
        if lbl == -1: continue
        cluster_to_idxs[lbl].append(i)
    cl_sorted = sorted(cluster_to_idxs.items(), key=lambda kv: -len(kv[1]))

    out = []
    out.append(f"# Seafood data-driven taxonomy preview\n\n")
    out.append(f"**Signal priority used: category (hard filter) → ingredients → title.**\n\n")
    out.append(f"- Products in seafood/fish/shellfish categories: **{len(rows):,}**\n")
    out.append(f"- Natural clusters formed: **{n_clusters:,}**\n")
    out.append(f"- Unclustered (noise): {n_noise:,}\n\n")
    out.append(f"## Categories included\n\n")
    for c, n in cats_seen.most_common():
        out.append(f"- {n:,} — {c}\n")
    out.append("\n---\n\n")

    out.append(f"## Top {min(40, n_clusters)} clusters by size\n\n")
    for lbl, members in cl_sorted[:40]:
        member_descs = [rows[i]["product_description"] for i in members]
        member_ings = [ing_map.get(rows[i]["fdc_id"], "")[:200] for i in members]
        # Common content tokens across the cluster (title + ingredients combined)
        token_freq = Counter()
        for d, ing in zip(member_descs, member_ings):
            for t in set(tokens(d) + tokens(ing)): token_freq[t] += 1
        n = len(members)
        top = [t for t, c in token_freq.most_common(15) if c >= max(2, n*0.3)]
        canonical = ", ".join(top[:6]) or "(no common name)"

        # Closest tree code
        centroid = sub[members].mean(axis=0)
        centroid /= (np.linalg.norm(centroid) + 1e-12)
        sims = tree_emb @ centroid
        top_tree_idx = int(np.argsort(-sims)[:5][0])
        top_code = code_list[top_tree_idx]
        top_desc = code_to_desc[top_code]
        top_sim = float(sims[top_tree_idx])

        cur_codes = Counter(rows[i]["best_esha_code"] for i in members)
        # Get current desc
        cur_summary_pieces = []
        for c, ck in cur_codes.most_common(3):
            d = next((rows[i]["best_esha_description"] for i in members if rows[i]["best_esha_code"]==c), "")
            cur_summary_pieces.append(f"[{c}]×{ck} {d[:40]}")
        cur_summary = " · ".join(cur_summary_pieces)

        out.append(f"### Cluster {lbl}: **{canonical}** (n={n})\n")
        out.append(f"- closest ESHA tree: **[{top_code}] {top_desc}** (sim={top_sim:.3f})")
        if top_sim < 0.55:
            out.append("  ← **TREE GAP CANDIDATE**\n")
        else:
            out.append("\n")
        out.append(f"- currently routed: {cur_summary}\n")
        out.append("- sample products:\n")
        for i in members[:5]:
            r = rows[i]
            ing_short = (ing_map.get(r["fdc_id"], "") or "(no ingredients)")[:90]
            out.append(f"  - {r['product_description'][:65]} *(brand: {r['brand_name'][:20]})*\n")
            out.append(f"    ingredients: {ing_short}\n")
        out.append("\n")

    with open(OUT_MD, "w") as f: f.writelines(out)
    print(f"\nWrote {OUT_MD}")

if __name__ == "__main__":
    main()
