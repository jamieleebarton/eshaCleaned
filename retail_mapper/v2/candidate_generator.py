#!/usr/bin/env python3
"""Stage B — gather all 8 candidate-generators per product into one parquet.

Reads (whichever caches exist; missing ones are skipped gracefully):
  - parsed_titles_enriched.csv  (B1 parser, B8 ingredient FNDDS)
  - funnel_product_path.csv     (B7 funnel L2 leaf)
  - .cache/head_phrases.parquet (A2 — provides input for B2 head-locked re-parse, executed by reconcile)
  - .cache/ner_spans.parquet    (A3 — input for B3)
  - .cache/embed_knn.parquet    (B6)
  - .cache/zero_shot.parquet    (B4 + B5)   ← optional, only available after stage runs

Writes:
  .cache/candidates.parquet  one row per product with columns:
    fdc_id, title,
    b1_leaf, b1_confidence, b1_review,
    b6_top_codes, b6_top_descs, b6_top_scores,
    b7_l1_label, b7_sub_leaf_label, b7_other,
    b8_top_fndds_code, b8_top_fndds_desc, b8_top_score, b8_top3,
    head_phrase, compound_prefix, pp_components, comma_tail,    # from A2
    ner_spans,                                                  # from A3
    zs_super, zs_super_score, zs_leaf, zs_leaf_score             # from B4/B5 (if cached)
"""
from __future__ import annotations
import argparse, csv, os, sys, time
from pathlib import Path

REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
RM   = REPO / "retail_mapper"
V2   = RM / "v2"
CACHE = V2 / ".cache"
OUT_PARQUET = CACHE / "candidates.parquet"
csv.field_size_limit(sys.maxsize)

def _read_parquet(path: Path):
    if not path.exists(): return {}
    import pyarrow.parquet as pq
    tbl = pq.read_table(path)
    return tbl.to_pylist()

# ---- axis fingerprinting ----
AXIS_FILES = {
    "cut":        "cut.tsv",
    "storage":    "storage.tsv",
    "prep_state": "preparation_state.tsv",
    "sweetener":  "sweetener.tsv",
    "fat":        "fat.tsv",
    "sodium":     "sodium.tsv",
    "diet":       "diet.tsv",
    "audience":   "audience.tsv",
    "dish_type":  "dish_type.tsv",
    "combo":      "combo_format.tsv",
    "flavor":     "flavor_universal.tsv",
    "color":      "color.tsv",
    "cuisine":    "cuisine.tsv",
    "form":       "form.tsv",
}
def _load_axes(rm: Path):
    """Load each axis as a set of tokens. Multi-word tokens are kept as-is and
    matched substring-wise."""
    axes = {}
    for k, fn in AXIS_FILES.items():
        path = rm / "axes" / fn
        toks = set()
        if not path.exists(): continue
        with open(path) as f:
            for line in f:
                if line.startswith("#") or not line.strip(): continue
                t = line.split("\t")[0].strip().lower()
                if len(t) >= 2:
                    toks.add(t)
        axes[k] = toks
    return axes

def fingerprint(text: str, axes: dict) -> dict[str, list[str]]:
    """Return a multi-axis match dict: axis -> list of matched tokens."""
    t = (text or "").lower()
    out = {}
    for axis, toks in axes.items():
        # for multi-word tokens, do substring match; for single words, word-boundary match
        hits = []
        for tok in toks:
            if " " in tok or "-" in tok:
                if tok in t: hits.append(tok)
            else:
                if f" {tok} " in f" {t} ": hits.append(tok)
        if hits: out[axis] = hits
    return out

# characteristic-ingredient signatures: small handcrafted bumps.
# These are INTENTIONALLY tight — false positives leak into nog/baked-beans
# leaves on protein powders, peas, etc.
ING_SIG_BOOSTS = {
    # real eggnog needs cinnamon AND nutmeg co-occurring
    "nog": [
        (("nutmeg", "egg"), 1.5),
        (("nutmeg", "cinnamon"), 1.0),
    ],
    # baked beans need molasses or brown sugar AND tomato — together
    "baked beans": [
        (("molasses", "tomato"), 1.0),
        (("brown sugar", "tomato sauce"), 0.8),
    ],
}
def ingredient_signature(ing_text: str) -> dict[str, float]:
    """Return small set of category boosts based on ingredient signatures."""
    if not ing_text: return {}
    t = ing_text.lower()
    boosts = {}
    for cat, rules in ING_SIG_BOOSTS.items():
        for required, score in rules:
            if all(r in t for r in required):
                boosts[cat] = max(boosts.get(cat, 0), score)
                break
    return boosts

def index_by_fdc(rows, key="fdc_id"):
    out = {}
    for r in rows:
        k = str(r.get(key, ""))
        if k: out[k] = r
    return out

def run(limit: int | None = None):
    # ---- load all sources ----
    parsed_path = RM / "parsed_titles_enriched.csv"
    funnel_path = RM / "funnel_product_path.csv"
    audit_path  = REPO / "implementation" / "output" / "product_esha_fixy.csv"  # BFC + FNDDS authority
    ing_dir     = REPO / "fixy_done"   # raw ingredient strings

    print(f"reading {parsed_path}")
    parsed = []
    with open(parsed_path, errors='replace') as f:
        for r in csv.DictReader(f):
            parsed.append(r)
            if limit and len(parsed) >= limit: break
    print(f"  {len(parsed)} parsed rows")

    print(f"reading {funnel_path}")
    funnel_idx = {}
    with open(funnel_path, errors='replace') as f:
        for r in csv.DictReader(f):
            fdc = r.get('fdc_id') or ''
            if fdc: funnel_idx[fdc] = r

    # NEW: pull BFC + fndds authority from the fixy audit (the file actually has these)
    print(f"reading {audit_path}  (BFC + fndds authority)")
    audit_idx = {}
    with open(audit_path, errors='replace') as f:
        for r in csv.DictReader(f):
            fdc = r.get('fdc_id') or ''
            if fdc and fdc not in audit_idx:
                audit_idx[fdc] = {
                    "branded_food_category": r.get("branded_food_category") or "",
                    "fndds_main_code":       r.get("fndds_main_code") or "",
                    "fndds_main_description": r.get("fndds_main_description") or "",
                    "best_esha_code":        r.get("best_esha_code") or "",
                    "best_esha_description": r.get("best_esha_description") or "",
                }
    print(f"  {len(audit_idx)} BFC/fndds rows")

    # NEW: pull ingredient text from parsed_titles_with_ingredients.csv
    # (99.5% coverage vs ~42% from fixy_done). Also pulls ingredient categories
    # and the structured has_* flags that the previous file built.
    print(f"reading parsed_titles_with_ingredients.csv (99.5% ingredient coverage)...")
    pti_path = RM / "parsed_titles_with_ingredients.csv"
    ing_idx = {}
    if pti_path.exists():
        with open(pti_path, errors='replace') as f:
            for r in csv.DictReader(f):
                fdc = r.get('fdc_id') or ''
                if not fdc: continue
                ing_idx[fdc] = {
                    "ing_full":        (r.get('ing_full') or '').lower(),
                    "ing_top5":        (r.get('ing_top5') or '').lower(),
                    "ing_categories":  (r.get('ing_categories') or '').lower(),
                    "protein_source":  (r.get('protein_source') or '').lower(),
                    "dairy_source":    (r.get('dairy_source') or '').lower(),
                    "grain_source":    (r.get('grain_source') or '').lower(),
                    "sweetener_source":(r.get('sweetener_source') or '').lower(),
                    "oil_source":      (r.get('oil_source') or '').lower(),
                    "has_cocoa":       (r.get('has_cocoa') or '').lower() in ('true','y','yes','1'),
                    "has_batter":      (r.get('has_batter') or '').lower() in ('true','y','yes','1'),
                    "has_hot_dog":     (r.get('has_hot_dog') or '').lower() in ('true','y','yes','1'),
                    "has_breading":    (r.get('has_breading') or '').lower() in ('true','y','yes','1'),
                }
    else:
        # fallback to fixy_done (lower coverage)
        import glob
        needed_fdcs = {r.get('fdc_id') or '' for r in parsed}
        for path in glob.glob(str(ing_dir / "*.csv")):
            n = os.path.basename(path)
            if n.startswith("_") or not n.split(".")[0].isdigit(): continue
            with open(path, errors='replace') as f:
                for r in csv.DictReader(f):
                    fdc = r.get('fdc_id') or ''
                    if fdc in needed_fdcs and fdc not in ing_idx:
                        ing_idx[fdc] = {"ing_full": (r.get('ingredients') or '').lower()}
    print(f"  {len(ing_idx):,} ingredient records loaded")

    head_idx = index_by_fdc(_read_parquet(CACHE / "head_phrases.parquet"))
    ner_idx  = index_by_fdc(_read_parquet(CACHE / "ner_spans.parquet"))
    knn_idx  = index_by_fdc(_read_parquet(CACHE / "embed_knn.parquet"))
    zs_idx   = index_by_fdc(_read_parquet(CACHE / "zero_shot.parquet"))
    print(f"  caches loaded — head:{len(head_idx)} ner:{len(ner_idx)} knn:{len(knn_idx)} zs:{len(zs_idx)}")

    # load axis vocabularies once
    AXES = _load_axes(RM)
    print(f"  axes loaded: " + ", ".join(f"{k}:{len(v)}" for k, v in AXES.items()))

    # ---- merge ----
    rows = []
    t0 = time.time()
    for r in parsed:
        fdc = r.get('fdc_id') or ''
        h  = head_idx.get(fdc, {})
        n  = ner_idx.get(fdc, {})
        k  = knn_idx.get(fdc, {})
        z  = zs_idx.get(fdc, {})
        fl = funnel_idx.get(fdc, {})
        au = audit_idx.get(fdc, {})
        ing_record = ing_idx.get(fdc, {}) if isinstance(ing_idx.get(fdc), dict) else {"ing_full": ing_idx.get(fdc, "")}
        ing_text = ing_record.get("ing_full", "") or ""
        ing_categories = ing_record.get("ing_categories", "") or ""
        # Build comprehensive text bundle for fingerprinting
        title = r.get("product_description") or ""
        head_phrase = h.get("head_phrase") or ""
        compound_prefix = h.get("compound_prefix") or ""
        ner_spans = n.get("food_spans") or ""
        full_text = " ".join(filter(None, [
            title, head_phrase, compound_prefix,
            ner_spans.replace("|", " "),
            ing_text,                                # raw ingredients!
        ])).lower()

        # axis fingerprint and ingredient signature
        fp = fingerprint(full_text, AXES)
        ing_sig = ingredient_signature(ing_text)

        rows.append({
            "fdc_id":        fdc,
            "gtin_upc":      r.get("gtin_upc") or "",
            "title":         title,
            # B0 — branded food category (from audit, NOT from parsed_titles_enriched)
            "branded_food_category": au.get("branded_food_category") or "",
            "fndds_main_code":       au.get("fndds_main_code") or "",
            "fndds_main_description":au.get("fndds_main_description") or "",
            "current_esha":          au.get("best_esha_code") or "",
            "current_esha_desc":     au.get("best_esha_description") or "",
            # B1 parser
            "b1_leaf":       r.get("retail_leaf") or "",
            "b1_confidence": float(r.get("confidence") or 0),
            "b1_review":     r.get("needs_review") or "",
            "b1_supercat":   r.get("supercategory") or "",
            "b1_catgrp":     r.get("category_group") or "",
            "b1_category":   r.get("category") or "",
            "b1_form":       r.get("form") or "",
            "b1_flavor":     r.get("flavor") or "",
            # B6 embed kNN
            "b6_top_codes":  k.get("top_codes") or "",
            "b6_top_descs":  k.get("top_descs") or "",
            "b6_top_scores": k.get("top_scores") or "",
            # B7 funnel
            "b7_l1_label":         fl.get("l1_tree_label") or "",
            "b7_sub_leaf_label":   fl.get("sub_leaf_label") or "",
            "b7_other":            (fl.get("sub_leaf_label") or "").lower() == "other",
            # B8 ingredient FNDDS top-1
            "b8_top_fndds_code": r.get("ing_top1_fndds") or "",
            "b8_top_fndds_desc": r.get("ing_top1_desc") or "",
            "b8_top_score":      float(r.get("ing_top1_score") or 0) if r.get("ing_top1_score") else 0.0,
            "b8_top3":           r.get("ing_top3") or "",
            "b8_agrees_v6":      r.get("ing_agrees_v6") or "",
            # B9 — ingredient-signature characteristic boosts (json)
            "b9_ing_sig":     ";".join(f"{k}:{v}" for k, v in ing_sig.items()),
            # A2 head-finder
            "head_phrase":     head_phrase,
            "compound_prefix": compound_prefix,
            "pp_components":   h.get("pp_components") or "",
            "comma_tail":      h.get("comma_tail") or "",
            # A3 NER
            "ner_spans":       ner_spans,
            # B4/B5 zero-shot (optional)
            "zs_super":        z.get("zs_super") or "",
            "zs_super_score":  float(z.get("zs_super_score") or 0) if z.get("zs_super_score") else 0.0,
            "zs_leaf":         z.get("zs_leaf") or "",
            "zs_leaf_score":   float(z.get("zs_leaf_score") or 0) if z.get("zs_leaf_score") else 0.0,
            # AXIS FINGERPRINT (B-axis) — pipe-delimited per axis
            "fp_form":      "|".join(fp.get("form", [])),
            "fp_cut":       "|".join(fp.get("cut", [])),
            "fp_storage":   "|".join(fp.get("storage", [])),
            "fp_prep":      "|".join(fp.get("prep_state", [])),
            "fp_sweetener": "|".join(fp.get("sweetener", [])),
            "fp_fat":       "|".join(fp.get("fat", [])),
            "fp_sodium":    "|".join(fp.get("sodium", [])),
            "fp_diet":      "|".join(fp.get("diet", [])),
            "fp_audience":  "|".join(fp.get("audience", [])),
            "fp_dish_type": "|".join(fp.get("dish_type", [])),
            "fp_combo":     "|".join(fp.get("combo", [])),
            "fp_flavor":    "|".join(fp.get("flavor", [])),
            "fp_color":     "|".join(fp.get("color", [])),
            "fp_cuisine":   "|".join(fp.get("cuisine", [])),
            # raw ingredients tail (truncated for parquet size sanity)
            "ingredients":  ing_text[:400],
        })
    print(f"  merged {len(rows)} ({time.time()-t0:.1f}s)")

    import pyarrow as pa, pyarrow.parquet as pq
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, OUT_PARQUET, compression="zstd")
    print(f"wrote {OUT_PARQUET}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    a = p.parse_args()
    if a.run: run(a.limit)
    else: p.print_help()

if __name__ == "__main__":
    main()
