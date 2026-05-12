#!/usr/bin/env python3
"""Re-encode every row in priced_products_v2.db with the current htc encoder.

The DB has stale htc_code / htc_form_code values from an earlier encoder
run. The current encoder distinguishes plain cheddar from pepper jack
(food slots 01 vs 08), oils from cooking spray, etc. — but those
distinctions never made it into the stored codes. As a result:

  - Plain Cheddar, Pepper Jack, and Mozzarella all share htc_form `110Q0005`
    even though the live encoder gives them 1101004N, 1108001Z, 11000093.
  - Vegetable oils and cooking sprays collide at `B00W600V` even though
    sprays should be at `B000000A`.

We re-encode each SKU using:
  category    = consensus_canonical (so the path informs group/family)
  description = name (so the SKU's distinguishing tokens hit form rules)
  food_name   = consensus_canonical leaf
  canonical_path = consensus_canonical

and store:
  htc_code      ← identity_mode=True   (positions 5-7 zeroed)
  htc_form_code ← identity_mode=False  (form-aware)

Backs up DB. Idempotent.

Usage:
  python3 recipe_pricing/retag_priced_products_v2.py [--dry-run] [--limit N]
"""
from __future__ import annotations
import argparse, shutil, sqlite3, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK = DB.with_suffix(".before_round5_retag.db")

sys.path.insert(0, str(ROOT / "recipe_mapper" / "v1"))
from htc.encoder import encode  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0,
                     help="Cap rows scanned (0 = no cap)")
    ap.add_argument("--sample-changes", type=int, default=15,
                     help="Print this many before/after samples")
    args = ap.parse_args()

    if not DB.exists():
        print(f"missing {DB}", file=sys.stderr); sys.exit(1)

    if not args.dry_run and not BAK.exists():
        print(f"backing up DB → {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    rows = cur.execute("""
        SELECT rowid, name, brand, consensus_canonical,
               htc_code, htc_form_code
        FROM priced_products
        WHERE consensus_canonical IS NOT NULL
          AND consensus_canonical != ''
          AND name IS NOT NULL AND name != ''
    """).fetchall()
    print(f"scanning {len(rows):,} rows…", file=sys.stderr)

    n_seen = 0; n_changed_id = 0; n_changed_form = 0
    samples = []
    by_pattern: Counter = Counter()
    updates = []   # (rowid, new_htc_code, new_htc_form_code)

    for rowid, name, brand, cp, old_id, old_form in rows:
        n_seen += 1
        if args.limit and n_seen > args.limit: break
        # Compute fresh codes
        leaf = (cp or "").split(" > ")[-1]
        try:
            h_id = encode("", description=name or "", food_name=leaf,
                           canonical_path=cp or "", identity_mode=True)
            h_form = encode("", description=name or "", food_name=leaf,
                             canonical_path=cp or "", identity_mode=False)
        except Exception as e:
            continue
        new_id = h_id.code
        new_form = h_form.code
        # Note current DB stores htc_code with possible leading "~"; we store
        # the fresh code as-is (encoder doesn't emit "~"). Strip "~" from old
        # for comparison.
        old_id_stripped = (old_id or "").lstrip("~")
        old_form_stripped = (old_form or "").lstrip("~")
        changed_id = (new_id != old_id_stripped)
        changed_form = (new_form != old_form_stripped)
        if changed_id: n_changed_id += 1
        if changed_form: n_changed_form += 1
        if changed_id or changed_form:
            updates.append((rowid, new_id, new_form))
            by_pattern[(cp[:30] if cp else "", old_form_stripped, new_form)] += 1
            if len(samples) < args.sample_changes:
                samples.append({
                    "name": (name or "")[:50],
                    "path": (cp or "")[:40],
                    "old_id": old_id_stripped, "new_id": new_id,
                    "old_form": old_form_stripped, "new_form": new_form,
                })

    print(f"  rows scanned:        {n_seen:,}", file=sys.stderr)
    print(f"  htc_code changes:    {n_changed_id:,}", file=sys.stderr)
    print(f"  htc_form_code chgs:  {n_changed_form:,}", file=sys.stderr)
    print(f"\nSample changes:", file=sys.stderr)
    for s in samples:
        print(f"  '{s['name']}' @ '{s['path']}'", file=sys.stderr)
        print(f"     id:   {s['old_id']} → {s['new_id']}", file=sys.stderr)
        print(f"     form: {s['old_form']} → {s['new_form']}", file=sys.stderr)
    print(f"\nTop change patterns (path, old_form → new_form, count):", file=sys.stderr)
    for (path, old_f, new_f), n in by_pattern.most_common(15):
        print(f"  {path:<32}  {old_f} → {new_f}  ({n})", file=sys.stderr)

    if args.dry_run:
        print(f"\n(dry-run; no changes written)", file=sys.stderr)
        return

    print(f"\napplying {len(updates):,} updates…", file=sys.stderr)
    cur.executemany(
        "UPDATE priced_products SET htc_code = ?, htc_form_code = ? WHERE rowid = ?",
        [(nid, nf, rid) for rid, nid, nf in updates],
    )
    con.commit()
    print(f"done. backup at {BAK.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
