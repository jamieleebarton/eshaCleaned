#!/usr/bin/env python3
"""Re-encode every recipe-line's htc_code with the current encoder.

The htc_code in recipes_unified.csv was set by an older encoder run.
We re-encode each unique (ingredient_item, canonical_path) combination
through the current encoder so recipe-side codes match priced-side
codes (which were re-tagged in round 5).

Also recomputes htc_full_code per row using new htc_code + facets.

Backs up CSV. Atomic temp+rename.

Usage:
  python3 recipe_pricing/retag_recipes_unified.py [--dry-run]
"""
from __future__ import annotations
import argparse, csv, os, re, shutil, sys, tempfile
from collections import Counter
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
BAK = CSV_PATH.with_suffix(".csv.before_round8_retag_recipes")

sys.path.insert(0, str(ROOT / "recipe_mapper" / "v1"))
from htc.encoder import encode  # noqa: E402
from htc.full_code import compose_full_code  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not CSV_PATH.exists():
        print(f"missing {CSV_PATH}", file=sys.stderr); sys.exit(1)
    if not args.dry_run and not BAK.exists():
        print(f"backing up CSV → {BAK.name}", file=sys.stderr)
        shutil.copy(str(CSV_PATH), str(BAK))

    # Cache encoder results per (ingredient_item, canonical_path) — encoder
    # is deterministic, so 1 call per unique tuple is enough.
    cache: dict[tuple[str, str], str] = {}

    def get_htc(ing: str, cp: str) -> str:
        key = (ing, cp)
        if key in cache: return cache[key]
        if not ing:
            cache[key] = ""
            return ""
        try:
            h = encode("", description=ing, food_name=ing,
                        canonical_path=cp, identity_mode=True)
            cache[key] = h.code
        except Exception:
            cache[key] = ""
        return cache[key]

    rows_seen = 0; n_updated = 0; n_full_updated = 0; n_unchanged = 0
    samples = []
    transitions: Counter = Counter()

    if args.dry_run:
        with CSV_PATH.open() as f:
            r = csv.DictReader(f)
            for row in r:
                rows_seen += 1
                ing = (row.get("ingredient_item") or "").strip()
                if not ing: continue
                cp = (row.get("normalized_canonical_text") or "").strip()
                old = (row.get("htc_code") or "").strip().lstrip("~")
                new = get_htc(ing, cp)
                if not new: continue
                new_full = ""
                if new:
                    cp_words = set(re.findall(r"[a-z]+", cp.lower())) if cp else set()
                    variant_parts = []
                    for col in ("facet_form", "facet_processing"):
                        v = (row.get(col) or "").strip().lower()
                        if not v:
                            continue
                        v_words = set(re.findall(r"[a-z]+", v))
                        if v_words and v_words.issubset(cp_words):
                            continue
                        variant_parts.append(v)
                    rlp = " > ".join([cp] + variant_parts) if variant_parts else cp
                    claims = (row.get("facet_claims") or "").strip()
                    new_full = compose_full_code(new, cp, rlp, claims)
                if new != old:
                    n_updated += 1
                    transitions[(old, new)] += 1
                    if len(samples) < 12:
                        samples.append({"ing": ing, "old": old, "new": new})
                elif new_full and new_full != (row.get("htc_full_code") or ""):
                    n_full_updated += 1
                else:
                    n_unchanged += 1
        print(f"\nrows seen: {rows_seen:,}", file=sys.stderr)
        print(f"unique cache entries: {len(cache):,}", file=sys.stderr)
        print(f"htc_code changes: {n_updated:,}", file=sys.stderr)
        print(f"htc_full_code-only changes: {n_full_updated:,}", file=sys.stderr)
        print(f"unchanged: {n_unchanged:,}", file=sys.stderr)
        print(f"\nTop transitions:", file=sys.stderr)
        for (old, new), n in transitions.most_common(15):
            print(f"  {n:>5}  {old} → {new}", file=sys.stderr)
        print(f"\nSamples:", file=sys.stderr)
        for s in samples:
            print(f"  '{s['ing']}'  {s['old']} → {s['new']}", file=sys.stderr)
        return

    out_dir = CSV_PATH.parent
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".unified_retag_",
                                         suffix=".csv", dir=str(out_dir))
    os.close(tmp_fd)
    try:
        with CSV_PATH.open() as f_in, open(tmp_path, "w", newline="") as f_out:
            r = csv.DictReader(f_in)
            fieldnames = list(r.fieldnames or [])
            w = csv.DictWriter(f_out, fieldnames=fieldnames)
            w.writeheader()
            for row in r:
                rows_seen += 1
                ing = (row.get("ingredient_item") or "").strip()
                cp = (row.get("normalized_canonical_text") or "").strip()
                if ing:
                    new = get_htc(ing, cp)
                    if new:
                        old = (row.get("htc_code") or "").strip().lstrip("~")
                        cp_words = set(re.findall(r"[a-z]+", cp.lower())) if cp else set()
                        variant_parts = []
                        for col in ("facet_form", "facet_processing"):
                            v = (row.get(col) or "").strip().lower()
                            if not v: continue
                            v_words = set(re.findall(r"[a-z]+", v))
                            if v_words and v_words.issubset(cp_words): continue
                            variant_parts.append(v)
                        rlp = " > ".join([cp] + variant_parts) if variant_parts else cp
                        claims = (row.get("facet_claims") or "").strip()
                        new_full = compose_full_code(new, cp, rlp, claims)
                        if new != old:
                            n_updated += 1
                            row["htc_code"] = new
                        if new_full != (row.get("htc_full_code") or ""):
                            n_full_updated += 1
                            row["htc_full_code"] = new_full
                w.writerow(row)
        os.replace(tmp_path, CSV_PATH)
    except Exception:
        if os.path.exists(tmp_path): os.remove(tmp_path)
        raise

    print(f"\nrows seen: {rows_seen:,}", file=sys.stderr)
    print(f"unique cache entries: {len(cache):,}", file=sys.stderr)
    print(f"htc_code changes: {n_updated:,}", file=sys.stderr)
    print(f"htc_full_code changes: {n_full_updated:,}", file=sys.stderr)
    print(f"  backup: {BAK.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
