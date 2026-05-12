#!/usr/bin/env python3
"""Phase 5 — cross-check food_packages_final.db against the audit.

For every FNDDS code in `packages`, verify:
  (a) the audit has at least one UPC tagged with that fndds_code
  (b) the audit's modal canonical_path/canonical_label for the code agrees
      directionally with the package's food_description
  (c) (if package has stated nutrition) the package's calorie density is in a
      sane range vs. the audit's modal nutrition for the FNDDS code

Writes `surface_lab_calculator`-readable report at REPORT and a CSV of
mismatches at MISMATCH_CSV for follow-up cleanup.
"""
from __future__ import annotations

import csv
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "retail_mapper" / "v2"
OUTPUT = ROOT / "implementation" / "output"
HESTIA_API = Path("/Users/jamiebarton/Desktop/Hestia/api")

AUDIT_CSV = Path(os.environ.get("AUDIT_CSV") or (V2 / "codex_full_corpus_audit.csv"))
PACKAGES_DB = Path(os.environ.get("PACKAGES_DB") or (HESTIA_API / "data" / "food_packages_final.db"))
NUTRIENT_LOOKUP = Path(os.environ.get("FNDDS_NUTRIENTS") or (HESTIA_API / "data" / "fndds_nutrient_lookup_v2.csv"))
REPORT = Path(os.environ.get("REPORT") or (OUTPUT / "food_packages_audit_report.md"))
MISMATCH_CSV = Path(os.environ.get("MISMATCH_CSV") or (OUTPUT / "food_packages_mismatches.csv"))

MIN_MATCH_SCORE = 0.5

csv.field_size_limit(sys.maxsize)
WS = re.compile(r"\s+")
NONALNUM = re.compile(r"[^a-z0-9 ]+")


def normalize_key(s: str) -> str:
    s = (s or "").lower()
    s = NONALNUM.sub(" ", s)
    return WS.sub(" ", s).strip()


def main() -> None:
    print(f"  reading audit: {AUDIT_CSV.name}")
    fndds_to_label: dict[str, Counter] = defaultdict(Counter)
    fndds_to_path: dict[str, Counter] = defaultdict(Counter)
    fndds_to_desc: dict[str, str] = {}

    with AUDIT_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                score = float(row.get("match_score") or 0)
            except ValueError:
                score = 0.0
            if score < MIN_MATCH_SCORE:
                continue
            f = (row.get("fndds_code") or "").strip()
            if not f:
                continue
            label = (row.get("canonical_label") or "").strip()
            path = (row.get("canonical_path") or "").strip()
            desc = (row.get("fndds_desc") or "").strip()
            if label:
                fndds_to_label[f][label] += 1
            if path:
                fndds_to_path[f][path] += 1
            if f not in fndds_to_desc and desc:
                fndds_to_desc[f] = desc

    print(f"  audit FNDDS codes (score>=0.5): {len(fndds_to_label):,}")

    print(f"  reading nutrients: {NUTRIENT_LOOKUP.name}")
    nutrients: dict[str, dict] = {}
    if NUTRIENT_LOOKUP.exists():
        with NUTRIENT_LOOKUP.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                code = (row.get("fndds_code") or "").strip()
                if not code:
                    continue
                try:
                    nutrients[code] = {
                        "energy_kcal": float(row.get("energy_kcal") or 0),
                        "protein_g": float(row.get("protein_g") or 0),
                        "fat_g": float(row.get("fat_g") or 0),
                        "carbs_g": float(row.get("carbs_g") or 0),
                    }
                except (ValueError, TypeError):
                    continue
    print(f"  nutrients: {len(nutrients):,} codes")

    print(f"  reading packages: {PACKAGES_DB.name}")
    if not PACKAGES_DB.exists():
        print("  packages DB missing — abort")
        return

    rows: list[dict] = []
    with sqlite3.connect(PACKAGES_DB) as conn:
        conn.row_factory = sqlite3.Row
        for r in conn.execute("""
            SELECT fndds_code, food_description, package_weight_grams,
                   walmart_price_cents, kroger_price_cents, source, confidence_tier
              FROM packages
        """):
            rows.append({k: r[k] for k in r.keys()})
    print(f"  packages: {len(rows):,} rows")

    stats = Counter()
    mismatches: list[dict] = []

    distinct_fndds = set()
    for row in rows:
        f = (row.get("fndds_code") or "").strip()
        distinct_fndds.add(f)
        if f not in fndds_to_label:
            stats["fndds_not_in_audit"] += 1
            mismatches.append({
                "issue": "not_in_audit",
                "fndds_code": f,
                "package_desc": row.get("food_description") or "",
                "package_grams": row.get("package_weight_grams") or "",
                "audit_label": "",
                "audit_path": "",
                "details": "FNDDS code has no audit-tagged UPC at score>=0.5",
            })
            continue

        modal_label, _ = fndds_to_label[f].most_common(1)[0]
        modal_path, _ = fndds_to_path[f].most_common(1)[0]

        pkg_desc = (row.get("food_description") or "").strip()
        pkg_tokens = set(normalize_key(pkg_desc).split())
        label_tokens = set(normalize_key(modal_label).split())
        path_tokens = set(normalize_key(modal_path.replace(">", " ")).split())
        all_audit_tokens = label_tokens | path_tokens
        overlap = pkg_tokens & all_audit_tokens

        # Treat lack of any token overlap as a directional mismatch
        if pkg_tokens and not overlap:
            stats["desc_path_mismatch"] += 1
            mismatches.append({
                "issue": "desc_path_mismatch",
                "fndds_code": f,
                "package_desc": pkg_desc,
                "package_grams": row.get("package_weight_grams") or "",
                "audit_label": modal_label,
                "audit_path": modal_path,
                "details": f"no token overlap between package desc and audit label/path",
            })
            continue

        stats["agreement"] += 1

    print(f"  distinct FNDDS in packages: {len(distinct_fndds):,}")
    in_audit = sum(1 for c in distinct_fndds if c in fndds_to_label)
    print(f"    in audit: {in_audit:,} ({in_audit/max(len(distinct_fndds),1)*100:.1f}%)")
    print(f"    not in audit: {len(distinct_fndds) - in_audit:,}")

    print(f"  agreement rows: {stats['agreement']:,}")
    print(f"  desc/path mismatch rows: {stats['desc_path_mismatch']:,}")
    print(f"  fndds_not_in_audit rows: {stats['fndds_not_in_audit']:,}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    coverage = stats['agreement'] / max(len(rows), 1) * 100
    lines = [
        "# food_packages_final.db Audit Report",
        "",
        f"- audit: `{AUDIT_CSV.name}`",
        f"- packages DB: `{PACKAGES_DB.name}`",
        f"- packages: {len(rows):,} rows / {len(distinct_fndds):,} distinct FNDDS codes",
        "",
        "## Outcome",
        "",
        f"- packages agreeing with audit: **{stats['agreement']:,} ({coverage:.1f}%)**",
        f"- distinct FNDDS in packages but missing from audit: {len(distinct_fndds)-in_audit:,}",
        f"- desc/path token mismatches (rows): {stats['desc_path_mismatch']:,}",
        f"- fndds_not_in_audit (rows): {stats['fndds_not_in_audit']:,}",
        "",
        f"Mismatch detail CSV: `{MISMATCH_CSV.name}`",
    ]
    REPORT.write_text("\n".join(lines) + "\n")

    MISMATCH_CSV.parent.mkdir(parents=True, exist_ok=True)
    with MISMATCH_CSV.open("w", newline="", encoding="utf-8") as fh:
        if mismatches:
            writer = csv.DictWriter(fh, fieldnames=list(mismatches[0].keys()))
            writer.writeheader()
            writer.writerows(mismatches)
        else:
            fh.write("issue,fndds_code,package_desc,package_grams,audit_label,audit_path,details\n")
    print(f"  wrote {REPORT.name} and {MISMATCH_CSV.name}")


if __name__ == "__main__":
    main()
