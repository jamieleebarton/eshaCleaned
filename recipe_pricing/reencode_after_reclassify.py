#!/usr/bin/env python3
"""Re-encode htc_code / htc_form_code / htc_full_code for every SKU whose
canonical_path was recently changed by the reclassifier.

When reclassify_canonical_paths.py moves a SKU's consensus_canonical
(e.g., 'Kraft Mayo with Olive Oil' from `Pantry > Oil` to
`Pantry > Sauces & Salsas > Mayonnaise`), the htc_code that was originally
encoded with the OLD canonical_path stays stuck. This script re-runs the
current encoder for every SKU and updates htc_code/htc_form_code/
htc_full_code to match the SKU's CURRENT canonical_path.

Idempotent. Backs up DB.

Usage:
  python3 recipe_pricing/reencode_after_reclassify.py [--dry-run]
"""
from __future__ import annotations
import argparse, shutil, sqlite3, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK = DB.with_suffix(".before_reencode_after_reclassify.db")

sys.path.insert(0, str(ROOT / "recipe_mapper" / "v1"))
from htc.encoder import encode  # noqa: E402
from htc.full_code import compose_full_code  # noqa: E402

# Same name-claim heuristic we used in populate_htc_full_code.py
NAME_CLAIM_KEYS = {
    "organic":     "organic", "non gmo": "non_gmo", "non-gmo": "non_gmo",
    "gluten free": "gluten_free", "gluten-free": "gluten_free",
    "dairy free":  "dairy_free", "dairy-free": "dairy_free",
    "vegan":       "vegan", "vegetarian": "vegetarian",
    "kosher":      "kosher", "halal": "halal",
    "sugar free":  "sugar_free", "sugar-free": "sugar_free",
    "low fat":     "low_fat", "fat free": "low_fat",
    "low sodium":  "low_sodium", "high protein": "high_protein",
    "whole grain": "whole_grain", "whole wheat": "whole_grain",
    "fair trade":  "fair_trade", "natural": "natural",
}


def claims_from_name(name: str) -> str:
    nl = (name or "").lower()
    found = set()
    for kw, claim in NAME_CLAIM_KEYS.items():
        if kw in nl: found.add(claim)
    return "|".join(sorted(found))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not DB.exists():
        print(f"missing {DB}", file=sys.stderr); sys.exit(1)
    if not args.dry_run and not BAK.exists():
        print(f"backing up DB → {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    rows = cur.execute("""
        SELECT rowid, name, consensus_canonical, retail_leaf_path,
               htc_code, htc_form_code, htc_full_code
        FROM priced_products
        WHERE name IS NOT NULL AND consensus_canonical IS NOT NULL
          AND consensus_canonical != ''
    """).fetchall()
    print(f"scanning {len(rows):,} rows…", file=sys.stderr)

    # Cache encoder output per (name, canonical_path) — enc is deterministic
    cache: dict[tuple[str, str], tuple[str, str]] = {}

    def get_codes(name: str, cp: str) -> tuple[str, str]:
        key = (name, cp)
        if key in cache: return cache[key]
        leaf = cp.split(" > ")[-1] if cp else ""
        try:
            h_id = encode("", description=name, food_name=leaf,
                           canonical_path=cp, identity_mode=True)
            h_form = encode("", description=name, food_name=leaf,
                             canonical_path=cp, identity_mode=False)
            cache[key] = (h_id.code, h_form.code)
        except Exception:
            cache[key] = ("", "")
        return cache[key]

    n_changed_id = 0; n_changed_form = 0; n_changed_full = 0
    samples = []
    transitions: Counter = Counter()
    updates = []   # (htc_code, htc_form_code, htc_full_code, rowid)

    for rowid, name, cp, rlp, old_id, old_form, old_full in rows:
        new_id, new_form = get_codes(name or "", cp or "")
        if not new_id: continue
        # htc_full_code recomputed from new bucket
        claims = claims_from_name(name or "")
        new_full = compose_full_code(new_id, cp or "", rlp or cp or "", claims)
        old_id_strip = (old_id or "").lstrip("~")
        old_form_strip = (old_form or "").lstrip("~")
        if (new_id == old_id_strip and new_form == old_form_strip
                and new_full == (old_full or "")):
            continue
        if new_id != old_id_strip: n_changed_id += 1
        if new_form != old_form_strip: n_changed_form += 1
        if new_full != (old_full or ""): n_changed_full += 1
        updates.append((new_id, new_form, new_full, rowid))
        if old_id_strip and new_id != old_id_strip:
            transitions[(old_id_strip, new_id)] += 1
        if len(samples) < 12:
            samples.append({
                "name": (name or "")[:50],
                "cp": (cp or "")[:40],
                "old_id": old_id_strip, "new_id": new_id,
                "old_form": old_form_strip, "new_form": new_form,
            })

    print(f"\nrows scanned: {len(rows):,}", file=sys.stderr)
    print(f"htc_code changes:      {n_changed_id:,}", file=sys.stderr)
    print(f"htc_form_code changes: {n_changed_form:,}", file=sys.stderr)
    print(f"htc_full_code changes: {n_changed_full:,}", file=sys.stderr)
    print(f"\nTop bucket transitions:", file=sys.stderr)
    for (old, new), n in transitions.most_common(15):
        print(f"  {n:>5}  {old} → {new}", file=sys.stderr)
    print(f"\nSample re-encodings:", file=sys.stderr)
    for s in samples:
        print(f"  '{s['name']}' @ '{s['cp']}'", file=sys.stderr)
        print(f"     id:   {s['old_id']} → {s['new_id']}", file=sys.stderr)
        print(f"     form: {s['old_form']} → {s['new_form']}", file=sys.stderr)

    if args.dry_run:
        print(f"\n(dry-run; no updates written)", file=sys.stderr)
        return

    print(f"\napplying {len(updates):,} updates…", file=sys.stderr)
    cur.executemany(
        """UPDATE priced_products
           SET htc_code = ?, htc_form_code = ?, htc_full_code = ?
           WHERE rowid = ?""",
        updates,
    )
    con.commit()
    print("done.", file=sys.stderr)


if __name__ == "__main__":
    main()
