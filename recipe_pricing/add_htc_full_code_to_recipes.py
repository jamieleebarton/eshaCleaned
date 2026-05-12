#!/usr/bin/env python3
"""Add htc_full_code column to recipes_unified.csv.

For each recipe line, compose htc_full_code from:
  bucket  = htc_code (already on the row)
  variant = SHA256[:6] of recipe-side leaf attributes (facet_variant,
            facet_flavor, facet_modifier, facet_form). Produces same
            6-hex hash if a priced SKU has the same descriptors at its
            retail_leaf_path suffix.
  claims  = 4-hex bitfield from facet_claims

Round trip: a recipe asking for "1 cup organic shredded cheddar cheese" gets
  bucket=cheddar's htc_code, variant=hash("shredded"), claims=organic bit
A priced SKU "Great Value Organic Shredded Cheddar 8oz" at canonical_path
"Dairy > Cheese > Cheddar" with retail_leaf_path "...> Shredded" gets
  bucket=cheddar's htc_code, variant=hash("shredded"), claims=organic bit
SAME full_code → exact match.

Backs up CSV. Atomic temp+rename. Idempotent.

Usage:
  python3 recipe_pricing/add_htc_full_code_to_recipes.py [--dry-run]
"""
from __future__ import annotations
import argparse, csv, os, re, sys, tempfile
from collections import Counter
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
BAK = CSV_PATH.with_suffix(".csv.before_round8_full_code")

sys.path.insert(0, str(ROOT / "recipe_mapper" / "v1"))
from htc.full_code import compose_full_code, claim_bits_from_str  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not CSV_PATH.exists():
        print(f"missing {CSV_PATH}", file=sys.stderr); sys.exit(1)
    if not args.dry_run and not BAK.exists():
        print(f"backing up CSV → {BAK.name}", file=sys.stderr)
        import shutil; shutil.copy(str(CSV_PATH), str(BAK))

    rows_seen = 0; n_have_htc = 0; n_with_variant = 0; n_with_claims = 0
    samples = []
    claim_dist: Counter = Counter()

    def compute_full_code(row: dict) -> str:
        nonlocal n_with_variant, n_with_claims
        htc = (row.get("htc_code") or "").strip()
        if not htc: return ""
        cp = (row.get("normalized_canonical_text") or "").strip()
        cp_words = set(re.findall(r"[a-z]+", cp.lower())) if cp else set()
        # Variant input: ONLY facet_form + facet_processing — the
        # descriptors that distinguish SKUs at the same canonical_path
        # (shredded vs sliced cheddar; cooked vs raw rice). facet_variant
        # and facet_flavor often just echo the identity (variant='cheddar'
        # for cheddar cheese), so we skip them to keep the hash zero
        # for plain ingredients that should match plain SKUs.
        variant_parts = []
        for col in ("facet_form", "facet_processing"):
            v = (row.get(col) or "").strip().lower()
            if not v: continue
            v_words = set(re.findall(r"[a-z]+", v))
            # Skip if it just repeats the canonical_path leaf
            if v_words and v_words.issubset(cp_words): continue
            variant_parts.append(v)
        rlp = " > ".join([cp] + variant_parts) if variant_parts else cp
        # Claims
        claims = (row.get("facet_claims") or "").strip()
        if claims: n_with_claims += 1
        if variant_parts: n_with_variant += 1
        for c in claims.replace(",", "|").split("|"):
            c = c.strip()
            if c: claim_dist[c.lower()] += 1
        return compose_full_code(htc, cp, rlp, claims)

    if args.dry_run:
        with CSV_PATH.open() as f:
            r = csv.DictReader(f)
            for row in r:
                rows_seen += 1
                if not row.get("htc_code"): continue
                n_have_htc += 1
                fc = compute_full_code(row)
                if fc and len(samples) < 12 and (row.get("facet_variant") or row.get("facet_claims")):
                    samples.append({
                        "rid": row["recipe_id"], "ing": row.get("ingredient_item",""),
                        "htc": row.get("htc_code",""),
                        "facets": " | ".join(filter(None, [row.get("facet_variant",""), row.get("facet_flavor",""), row.get("facet_modifier",""), row.get("facet_claims","")])),
                        "fc": fc,
                    })
    else:
        out_dir = CSV_PATH.parent
        tmp_fd, tmp_path = tempfile.mkstemp(prefix=".unified_fc_",
                                             suffix=".csv", dir=str(out_dir))
        os.close(tmp_fd)
        try:
            with CSV_PATH.open() as f_in, open(tmp_path, "w", newline="") as f_out:
                r = csv.DictReader(f_in)
                # Insert htc_full_code column at the end
                fieldnames = list(r.fieldnames or [])
                if "htc_full_code" not in fieldnames:
                    fieldnames.append("htc_full_code")
                w = csv.DictWriter(f_out, fieldnames=fieldnames)
                w.writeheader()
                for row in r:
                    rows_seen += 1
                    if row.get("htc_code"):
                        n_have_htc += 1
                        row["htc_full_code"] = compute_full_code(row)
                    else:
                        row["htc_full_code"] = ""
                    w.writerow(row)
            os.replace(tmp_path, CSV_PATH)
        except Exception:
            if os.path.exists(tmp_path): os.remove(tmp_path)
            raise

    print(f"\nrows scanned:         {rows_seen:,}", file=sys.stderr)
    print(f"have htc_code:        {n_have_htc:,}", file=sys.stderr)
    print(f"with facet_variant:   {n_with_variant:,}", file=sys.stderr)
    print(f"with facet_claims:    {n_with_claims:,}", file=sys.stderr)
    print(f"\nClaim distribution (recipe-side):", file=sys.stderr)
    for c, n in claim_dist.most_common(15):
        print(f"  {c:<20}  {n:,}", file=sys.stderr)
    print(f"\nSample full_codes:", file=sys.stderr)
    for s in samples[:10]:
        print(f"  rid={s['rid']:>6}  '{s['ing']}'  facets='{s['facets']}'", file=sys.stderr)
        print(f"     full_code: {s['fc']}", file=sys.stderr)


if __name__ == "__main__":
    main()
