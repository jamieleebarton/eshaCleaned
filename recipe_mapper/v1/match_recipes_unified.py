#!/usr/bin/env python3
"""P6 — Unified recipe matcher: HTC + facets + grams.

For each ingredient line in recipe_qa.db:
  1. Lookup HTC code from the ingredient-tagging table.
  2. Extract qty + unit from `display` string.
  3. Resolve grams from htc_gram_weights (with group fallback) when the recipe
     blob doesn't already carry a gram value.
  4. Extract structured facets from `display` against the per-HTC vocab
     (flavor / form / processing / claim / modifier / variant).
  5. Emit one structured row per ingredient line.

Outputs:
  recipes_unified.csv
  recipes_unified_summary.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from htc.qty_units import extract_qty_unit  # noqa: E402

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "recipe_qa.db"
HERE = Path(__file__).resolve().parent
DEFAULT_TAGS = HERE / "output" / "recipe_ingredient_htc_tagged.csv"
DEFAULT_GRAMS = HERE / "output" / "htc_gram_weights.csv"
DEFAULT_GROUP_GRAMS = HERE / "output" / "htc_group_default_grams.csv"
DEFAULT_VOCAB = HERE / "output" / "htc_facet_vocab.json"
OUT_CSV = HERE / "output" / "recipes_unified.csv"
OUT_SUMMARY = HERE / "output" / "recipes_unified_summary.json"

WS = re.compile(r"\s+")


def normalize_item(s: str) -> str:
    return WS.sub(" ", (s or "").strip().lower())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-recipes", type=int, default=0)
    ap.add_argument("--top-codes-only", type=int, default=0,
                    help="If >0, only resolve facets for this many top codes (speed)")
    args = ap.parse_args()

    t0 = time.time()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    print(f"[{time.time()-t0:6.1f}s] loading HTC ingredient tags")
    htc_lookup: dict[str, dict] = {}
    with DEFAULT_TAGS.open() as f:
        r = csv.DictReader(f)
        for row in r:
            htc_lookup[normalize_item(row["item"])] = {
                "htc_code": row["htc_code"],
                "htc_group": row["htc_group"],
                "htc_confidence": float(row["htc_confidence"]),
            }
    print(f"  {len(htc_lookup):,} item→htc mappings")

    print(f"[{time.time()-t0:6.1f}s] loading gram weights")
    grams_table: dict[tuple[str, str], float] = {}
    with DEFAULT_GRAMS.open() as f:
        r = csv.DictReader(f)
        for row in r:
            grams_table[(row["htc_code"], row["unit"])] = float(row["grams_per_unit_median"])
    grams_group: dict[tuple[str, str], float] = {}
    with DEFAULT_GROUP_GRAMS.open() as f:
        r = csv.DictReader(f)
        for row in r:
            grams_group[(row["htc_group"], row["unit"])] = float(row["grams_per_unit_median"])
    print(f"  htc-level: {len(grams_table):,}  group-level: {len(grams_group):,}")

    print(f"[{time.time()-t0:6.1f}s] loading facet vocab")
    with DEFAULT_VOCAB.open() as f:
        vocab_raw: dict = json.load(f)
    # Pre-compile ONE alternation regex per (htc_code, facet) for ~30x speedup.
    # Values sorted longest-first so "extra virgin" beats "virgin",
    # "honey bbq" beats "honey", etc.
    vocab_re: dict[str, dict[str, "re.Pattern"]] = {}
    n_patterns = 0
    for code, fac_dict in vocab_raw.items():
        clean: dict[str, "re.Pattern"] = {}
        for fac, items in fac_dict.items():
            vals = sorted(
                {str(v).lower() for v, _ in items if v},
                key=len, reverse=True,
            )
            if not vals:
                continue
            # word-boundary-ish so "vanilla" doesn't fire inside "vanillaroma"
            pat = re.compile(
                r"(?<![A-Za-z])("
                + "|".join(re.escape(v) for v in vals)
                + r")(?![A-Za-z])"
            )
            clean[fac] = pat
            n_patterns += 1
        if clean:
            vocab_re[code] = clean
    print(f"  {len(vocab_re):,} codes  {n_patterns:,} pre-compiled facet patterns")

    print(f"[{time.time()-t0:6.1f}s] streaming recipes")
    con = sqlite3.connect(str(DB))
    sql = """SELECT recipe_id, COALESCE(clean_title, recipe_name) AS title, ingredients_json
             FROM recipe_verdicts
             WHERE ingredients_json IS NOT NULL AND ingredients_json != ''"""
    if args.limit_recipes > 0:
        sql += f" LIMIT {args.limit_recipes}"

    out = OUT_CSV.open("w", newline="")
    w = csv.writer(out)
    w.writerow([
        "recipe_id", "recipe_title", "ingredient_item", "display",
        "qty", "unit", "grams_blob", "grams_resolved", "grams_source",
        "htc_code", "htc_group", "htc_confidence",
        "facet_flavor", "facet_form", "facet_processing", "facet_claims",
        "facet_modifier", "facet_variant",
    ])

    n_rec = n_lines = 0
    n_with_qty = n_with_unit = n_with_grams_resolved = 0
    n_with_facets = 0
    facet_hit_counts: Counter[str] = Counter()
    grams_source_counts: Counter[str] = Counter()
    n_recipes_full = 0

    for rid, title, blob in con.execute(sql):
        n_rec += 1
        try:
            items = json.loads(blob)
        except Exception:
            continue
        if not isinstance(items, list):
            continue

        rec_ok = 0
        rec_total = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            n_lines += 1
            rec_total += 1
            raw = it.get("item") or ""
            disp = it.get("display") or ""
            grams_blob_raw = it.get("grams")
            try:
                grams_blob = float(grams_blob_raw) if grams_blob_raw not in (None, "", 0) else None
            except (TypeError, ValueError):
                grams_blob = None
            key = normalize_item(raw)
            entry = htc_lookup.get(key, {})
            code = entry.get("htc_code", "")
            grp = entry.get("htc_group", "")
            conf = entry.get("htc_confidence", 0.0)

            # qty / unit
            qty, unit, residual = extract_qty_unit(disp)
            if qty:
                n_with_qty += 1
            if unit:
                n_with_unit += 1

            # grams resolution priority:
            # 1. grams from blob (already there)
            # 2. htc-level lookup with qty+unit
            # 3. group-level fallback
            grams_resolved = grams_blob
            grams_source = "blob" if grams_blob is not None else ""
            if grams_resolved is None and qty and unit and code:
                gpu = grams_table.get((code, unit))
                if gpu is None and grp:
                    gpu = grams_group.get((grp, unit))
                    if gpu:
                        grams_source = "group_default"
                else:
                    grams_source = "htc_level"
                if gpu:
                    grams_resolved = qty * gpu
            if grams_resolved is not None:
                n_with_grams_resolved += 1
                grams_source_counts[grams_source] += 1

            # facet extraction — single pre-compiled regex per (code, facet)
            facet_hits: dict[str, str] = {}
            disp_lc = disp.lower()
            patterns = vocab_re.get(code)
            if patterns:
                for fac, pat in patterns.items():
                    m = pat.search(disp_lc)
                    if m:
                        facet_hits[fac] = m.group(1)
                        facet_hit_counts[fac] += 1
                if facet_hits:
                    n_with_facets += 1

            # success criterion: HTC + grams_resolved
            if code and code[0] not in ("0", "N") and grams_resolved is not None and conf >= 0.6:
                rec_ok += 1

            w.writerow([
                rid, title, raw, disp,
                qty if qty else "", unit if unit else "",
                grams_blob if grams_blob is not None else "",
                f"{grams_resolved:.2f}" if grams_resolved is not None else "",
                grams_source,
                code, grp, f"{conf:.2f}" if conf else "",
                facet_hits.get("flavor", ""),
                facet_hits.get("form_texture_cut", ""),
                facet_hits.get("processing_storage", ""),
                facet_hits.get("claims", ""),
                facet_hits.get("modifier", ""),
                facet_hits.get("variant", ""),
            ])

        if rec_total and rec_ok == rec_total:
            n_recipes_full += 1
        if n_rec % 50000 == 0:
            print(f"[{time.time()-t0:6.1f}s] {n_rec:,} recipes processed", flush=True)

    out.close()

    summary = {
        "n_recipes": n_rec,
        "n_lines": n_lines,
        "pct_with_qty": round(n_with_qty / n_lines, 4) if n_lines else 0,
        "pct_with_unit": round(n_with_unit / n_lines, 4) if n_lines else 0,
        "pct_with_grams_resolved": round(n_with_grams_resolved / n_lines, 4) if n_lines else 0,
        "pct_with_facets": round(n_with_facets / n_lines, 4) if n_lines else 0,
        "facet_hit_counts": dict(facet_hit_counts),
        "grams_source_counts": dict(grams_source_counts),
        "n_recipes_fully_calculable": n_recipes_full,
        "pct_recipes_fully_calculable": round(n_recipes_full / n_rec, 4) if n_rec else 0,
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2))

    print()
    print(f"recipes:             {n_rec:,}")
    print(f"lines:               {n_lines:,}")
    print(f"  with qty:          {n_with_qty:,}  ({summary['pct_with_qty']:.1%})")
    print(f"  with unit:         {n_with_unit:,}  ({summary['pct_with_unit']:.1%})")
    print(f"  with grams:        {n_with_grams_resolved:,}  ({summary['pct_with_grams_resolved']:.1%})")
    print(f"    blob:            {grams_source_counts.get('blob', 0):,}")
    print(f"    htc_level:       {grams_source_counts.get('htc_level', 0):,}")
    print(f"    group_default:   {grams_source_counts.get('group_default', 0):,}")
    print(f"  with any facet:    {n_with_facets:,}  ({summary['pct_with_facets']:.1%})")
    print(f"facet hit counts:    {dict(facet_hit_counts)}")
    print(f"recipes fully calc:  {n_recipes_full:,}  ({summary['pct_recipes_fully_calculable']:.1%})")
    print(f"  -> {OUT_CSV}")
    print(f"  -> {OUT_SUMMARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
