#!/usr/bin/env python3
"""R12 — last-line quarantine for residual non-food SKUs still on food paths.

Architecture: the right fix is to move each SKU to its correct canonical_path
and re-encode its HTC fields. Use reclassify_canonical_paths.py whenever the
right destination is knowable, including specific Non-Food paths such as
Household, Pet, Garden, Kitchenware, and Personal Care.

Why this still exists: build_concept_index.py must not price recipes with
non-food SKUs if residual leakage remains. This script catches broad, proven
non-food terms that are still filed at food canonical_paths and:

  1. Loads non_food_blocklist.txt.
  2. Moves only remaining food-path non-food leakage to
     'Non-Food > Misclassified' and consensus_pid to the matched rule label.
  3. Calls reencode_after_reclassify.py so htc_code/htc_form_code/htc_full_code
     align to the new path.

Food SKUs in the wrong aisle, and non-food SKUs with a specific known home,
belong in reclassify_canonical_paths.py, not here.

Idempotent. Backs up DB. Logs to recipe_pricing/quarantine_log.csv.
"""
from __future__ import annotations
import argparse, csv, re, shutil, sqlite3, subprocess, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK = DB.with_suffix(".before_quarantine_blocklisted.db")
LOG = ROOT / "recipe_pricing" / "quarantine_log.csv"
BLOCKLIST_PATH = ROOT / "recipe_pricing" / "non_food_blocklist.txt"
QUARANTINE_PATH = "Non-Food > Misclassified"


def load_blocklist() -> list[str]:
    out = []
    if not BLOCKLIST_PATH.exists(): return out
    for line in BLOCKLIST_PATH.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"): continue
        s = s.lower()
        s = re.sub(r"[^a-z0-9 -]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        if s: out.append(s)
    return out


def normalize(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 -]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _matches(phrase: str, normalized_text: str) -> bool:
    """Both phrase and text get the same normalize() so '100% juice'
    matches '100 juice' after punctuation strip."""
    return normalize(phrase) in normalized_text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-reencode", action="store_true",
                    help="don't auto-call reencode_after_reclassify.py")
    args = ap.parse_args()

    if not DB.exists():
        print(f"missing {DB}", file=sys.stderr); sys.exit(1)
    if not args.dry_run and not BAK.exists():
        print(f"backing up DB → {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))

    blocklist = load_blocklist()
    print(f"loaded {len(blocklist)} blocklist phrases", file=sys.stderr)

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    rows = cur.execute("""
        SELECT rowid, upc, name, brand, consensus_canonical
        FROM priced_products
        WHERE name IS NOT NULL AND consensus_canonical IS NOT NULL
          AND consensus_canonical NOT LIKE 'Non-Food%'
    """).fetchall()
    print(f"scanning {len(rows):,} food-path SKUs…", file=sys.stderr)

    updates = []  # (rule, new_pid, rowid)
    log_rows = []
    rule_counts: Counter = Counter()

    for rowid, upc, name, brand, cp in rows:
        full = f"{name or ''} {brand or ''}"
        nl = normalize(full)
        cp_str = cp or ""
        matched_rule = None
        matched_token = None

        # Universal non-food blocklist only. Food products in the wrong food
        # path must be moved by reclassify_canonical_paths.py.
        for phrase in blocklist:
            if _matches(phrase, nl):
                matched_rule = "non_food_blocklist"
                matched_token = phrase
                break

        if not matched_rule: continue
        rule_counts[matched_rule] += 1
        new_pid = f"quarantine:{matched_token}"[:60]
        updates.append((QUARANTINE_PATH, new_pid, rowid))
        if len(log_rows) < 200:
            log_rows.append({
                "upc": upc, "name": (name or "")[:60],
                "brand": (brand or "")[:30],
                "old_path": cp_str, "rule": matched_rule,
                "matched_token": matched_token,
            })

    print(f"\nSKUs to quarantine: {len(updates):,}", file=sys.stderr)
    print(f"By rule:", file=sys.stderr)
    for k, v in rule_counts.most_common():
        print(f"  {k:<20} {v:>5}", file=sys.stderr)
    if log_rows:
        with LOG.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(log_rows[0].keys()))
            w.writeheader()
            for r in log_rows: w.writerow(r)
        print(f"  → log: {LOG.name}", file=sys.stderr)

    if args.dry_run:
        print("(dry-run; no DB writes)", file=sys.stderr); return

    print(f"\napplying {len(updates):,} quarantine updates…", file=sys.stderr)
    cur.executemany(
        """UPDATE priced_products
           SET consensus_canonical = ?, consensus_pid = ?
           WHERE rowid = ?""",
        updates,
    )
    con.commit()
    con.close()
    print("done.", file=sys.stderr)

    if args.skip_reencode:
        return
    print(f"\nauto re-encoding htc codes for quarantined rows…", file=sys.stderr)
    subprocess.run(
        [sys.executable, str(ROOT / "recipe_pricing" / "reencode_after_reclassify.py")],
        check=True,
    )


if __name__ == "__main__":
    main()
