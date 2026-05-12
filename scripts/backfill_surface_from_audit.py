#!/usr/bin/env python3
"""Phase 2 — backfill the surface table to maximum tier-A coverage.

Strategy (apply in order, first hit wins):

  1. Trust existing FNDDS: if the surface row already has a non-empty
     `fndds_code` and food_packages_final.db has a row for that code, promote
     to fndds_match.

  2. Audit-modal-by-canonical-label: if any of the surface row's canonical
     keys match an audit canonical_label/path-leaf, take the audit's modal
     FNDDS code (or SR28 fallback).

  3. Audit-modal-by-ESHA-pivot: if the surface row has an `esha_code`, look
     up the audit's modal FNDDS for that ESHA code and write it in.

The audit is `codex_full_corpus_audit.csv` — 462K UPC rows, each tagged with
`canonical_path`, `canonical_label`, `fndds_code`, `sr28_code`, `esha_code`.
Match scores below 0.5 are excluded.
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
CLEAN = Path("/Users/jamiebarton/Desktop/clean")
OUTPUT = ROOT / "implementation" / "output"
HESTIA_API = Path("/Users/jamiebarton/Desktop/Hestia/api")

AUDIT_CSV = Path(os.environ.get("AUDIT_CSV") or (V2 / "codex_full_corpus_audit.csv"))
SURFACE_CSV = Path(os.environ.get("SURFACE_CSV") or (CLEAN / "canonical_surface_normalized_with_product_proxies_rft_cleaned.csv"))
SURFACE_OUT = Path(os.environ.get("SURFACE_OUT") or (CLEAN / "canonical_surface_audit_backfilled.csv"))
REPORT_OUT = Path(os.environ.get("REPORT_OUT") or (OUTPUT / "surface_backfill_report.md"))
PACKAGES_DB = Path(os.environ.get("PACKAGES_DB") or (HESTIA_API / "data" / "food_packages_final.db"))

MIN_MATCH_SCORE = 0.5

csv.field_size_limit(sys.maxsize)

WS = re.compile(r"\s+")
NONALNUM = re.compile(r"[^a-z0-9 ]+")
PARENS = re.compile(r"\([^)]*\)")


def normalize_key(s: str) -> str:
    s = (s or "").lower()
    s = PARENS.sub(" ", s)
    s = NONALNUM.sub(" ", s)
    return WS.sub(" ", s).strip()


def audit_keys_from_row(row: dict) -> list[str]:
    label = row.get("canonical_label") or ""
    path = row.get("canonical_path") or ""
    keys: list[str] = []
    seen: set[str] = set()
    def add(s: str) -> None:
        k = normalize_key(s)
        if k and k not in seen:
            seen.add(k)
            keys.append(k)
    add(label)
    if "(" in label:
        add(label.split("(", 1)[0])
    if ">" in path:
        add(path.rsplit(">", 1)[-1])
    return keys


def best_modal(counter: Counter) -> tuple[str, str] | None:
    if not counter:
        return None
    (code, desc), _ = counter.most_common(1)[0]
    if not code:
        return None
    return code, desc


def load_packages_fndds() -> set[str]:
    if not PACKAGES_DB.exists():
        return set()
    out: set[str] = set()
    with sqlite3.connect(PACKAGES_DB) as conn:
        for (code,) in conn.execute("SELECT DISTINCT fndds_code FROM packages"):
            if code:
                out.add(str(code).strip())
    return out


def main() -> None:
    print(f"  loading packages DB: {PACKAGES_DB.name}")
    packages_fndds = load_packages_fndds()
    print(f"  packages: {len(packages_fndds):,} distinct FNDDS codes with prices")

    print(f"  reading audit: {AUDIT_CSV.name}")
    fndds_by_label: dict[str, Counter] = defaultdict(Counter)
    sr28_by_label: dict[str, Counter] = defaultdict(Counter)
    fndds_by_esha: dict[str, Counter] = defaultdict(Counter)

    with AUDIT_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                score = float(row.get("match_score") or 0)
            except ValueError:
                score = 0.0
            if score < MIN_MATCH_SCORE:
                continue
            keys = audit_keys_from_row(row)
            f_code = (row.get("fndds_code") or "").strip()
            f_desc = (row.get("fndds_desc") or "").strip()
            s_code = (row.get("sr28_code") or "").strip()
            s_desc = (row.get("sr28_desc") or "").strip()
            e_code = (row.get("esha_code") or "").strip()
            for k in keys:
                if f_code:
                    fndds_by_label[k][(f_code, f_desc)] += 1
                if s_code:
                    sr28_by_label[k][(s_code, s_desc)] += 1
            if e_code and f_code:
                fndds_by_esha[e_code][(f_code, f_desc)] += 1

    print(f"  audit labels: {len(fndds_by_label):,}")
    print(f"  audit ESHA→FNDDS pairs: {len(fndds_by_esha):,}")

    print(f"  reading surface: {SURFACE_CSV.name}")
    with SURFACE_CSV.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        surface_rows = list(reader)
    print(f"  surface: {len(surface_rows):,} rows")

    stats = Counter()
    examples: list[tuple[str, str, str, str]] = []  # (canon, strategy, code_type, code)

    for row in surface_rows:
        state = (row.get("nutrition_match_state") or "").strip()
        if state in {"sr28_match", "fndds_match"}:
            stats["already_tier_a"] += 1
            continue
        if state == "non_ingredient":
            stats["non_ingredient_skip"] += 1
            continue

        canon = (row.get("canonical_normalized") or row.get("canonical_surface") or "").strip()
        existing_fndds = (row.get("fndds_code") or "").strip()
        existing_sr28 = (row.get("sr28_code") or "").strip()
        existing_esha = (row.get("esha_code") or "").strip()

        # Strategy 1: existing FNDDS code is in food_packages_final.db
        if existing_fndds and existing_fndds in packages_fndds:
            row["nutrition_match_state"] = "fndds_match"
            row["fndds_match_type"] = row.get("fndds_match_type") or "trust_existing_packaged"
            stats["s1_trust_existing_packaged"] += 1
            stats["promoted"] += 1
            examples.append((canon, "trust_existing_packaged", "fndds", existing_fndds))
            continue

        # Strategy 2: audit modal by canonical label
        keys: list[str] = []
        seen: set[str] = set()
        for field in ("canonical_normalized", "canonical_shopping_item", "canonical_surface", "family_base"):
            k = normalize_key(row.get(field) or "")
            if k and k not in seen:
                seen.add(k)
                keys.append(k)

        f_pair = None
        s_pair = None
        for k in keys:
            if f_pair is None:
                m = best_modal(fndds_by_label.get(k, Counter()))
                if m and (not packages_fndds or m[0] in packages_fndds):
                    f_pair = m
            if s_pair is None:
                s_pair = best_modal(sr28_by_label.get(k, Counter()))
            if f_pair and s_pair:
                break

        if f_pair:
            f_code, f_desc = f_pair
            # Fill only — never overwrite an existing curated FNDDS code.
            # The audit modal trends toward generic canonical_label codes which
            # lose ingredient specificity (e.g. "pork shoulder" → "pork").
            if not existing_fndds:
                row["fndds_code"] = f_code
                if f_desc:
                    row["fndds_description"] = f_desc
                row["fndds_match_type"] = "audit_modal_label"
                stats["s2_audit_filled"] += 1
            else:
                stats["s2_kept_existing"] += 1
            row["nutrition_match_state"] = "fndds_match"
            stats["s2_audit_modal_label"] += 1
            stats["promoted"] += 1
            examples.append((canon, "audit_modal_label", "fndds", row["fndds_code"]))
            continue

        # Strategy 3: pivot via ESHA code through audit (fill-only)
        if existing_esha and existing_esha in fndds_by_esha:
            m = best_modal(fndds_by_esha[existing_esha])
            if m and (not packages_fndds or m[0] in packages_fndds):
                f_code, f_desc = m
                # Fill only — never overwrite curated FNDDS.
                if not existing_fndds:
                    row["fndds_code"] = f_code
                    if f_desc:
                        row["fndds_description"] = f_desc
                    row["fndds_match_type"] = "audit_esha_pivot"
                    stats["s3_filled"] += 1
                else:
                    stats["s3_kept_existing"] += 1
                row["nutrition_match_state"] = "fndds_match"
                stats["s3_audit_esha_pivot"] += 1
                stats["promoted"] += 1
                examples.append((canon, "audit_esha_pivot", "fndds", row["fndds_code"]))
                continue

        # Strategy 4: SR28 fallback (existing or audit modal)
        if existing_sr28:
            row["nutrition_match_state"] = "sr28_match"
            stats["s4_trust_existing_sr28"] += 1
            stats["promoted"] += 1
            examples.append((canon, "trust_existing_sr28", "sr28", existing_sr28))
            continue
        if s_pair:
            s_code, s_desc = s_pair
            row["sr28_code"] = s_code
            if s_desc:
                row["sr28_description"] = s_desc
            row["sr28_match_type"] = "audit_modal_label"
            row["nutrition_match_state"] = "sr28_match"
            stats["s4_audit_modal_sr28"] += 1
            stats["promoted"] += 1
            examples.append((canon, "audit_modal_sr28", "sr28", s_code))
            continue

        # Strategy 5: existing FNDDS, even if not in packages DB (best effort)
        if existing_fndds:
            row["nutrition_match_state"] = "fndds_match"
            row["fndds_match_type"] = row.get("fndds_match_type") or "trust_existing_unpackaged"
            stats["s5_trust_existing_fndds"] += 1
            stats["promoted"] += 1
            examples.append((canon, "trust_existing_unpackaged", "fndds", existing_fndds))
            continue

        stats["unmatched"] += 1

    print(f"  writing backfilled surface CSV → {SURFACE_OUT}")
    SURFACE_OUT.parent.mkdir(parents=True, exist_ok=True)
    with SURFACE_OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(surface_rows)

    print(f"  writing report → {REPORT_OUT}")
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    not_already_a = len(surface_rows) - stats['already_tier_a'] - stats['non_ingredient_skip']
    coverage_pct = (stats['promoted'] / not_already_a * 100) if not_already_a else 0

    lines = [
        "# Surface Audit-Backfill Report",
        "",
        f"- audit: `{AUDIT_CSV.name}`",
        f"- packages DB: `{PACKAGES_DB.name}` ({len(packages_fndds):,} distinct FNDDS codes with prices)",
        f"- surface in: `{SURFACE_CSV.name}` ({len(surface_rows):,} rows)",
        f"- surface out: `{SURFACE_OUT}`",
        "",
        "## Outcome",
        "",
        f"- already tier-A: **{stats['already_tier_a']:,}**",
        f"- non_ingredient (skipped): {stats['non_ingredient_skip']:,}",
        f"- promoted by this run: **{stats['promoted']:,} / {not_already_a:,}** ({coverage_pct:.1f}%)",
        f"- still unmatched: {stats['unmatched']:,}",
        "",
        "### Strategy breakdown",
        "",
        f"- S1 trust existing FNDDS in packages DB: {stats['s1_trust_existing_packaged']:,}",
        f"- S2 audit modal by canonical label: {stats['s2_audit_modal_label']:,}",
        f"- S3 audit ESHA→FNDDS pivot: {stats['s3_audit_esha_pivot']:,}",
        f"- S4 trust existing SR28: {stats['s4_trust_existing_sr28']:,}",
        f"- S4 audit modal SR28: {stats['s4_audit_modal_sr28']:,}",
        f"- S5 trust existing FNDDS (no package): {stats['s5_trust_existing_fndds']:,}",
        "",
        "## Examples (first 30)",
        "",
        "| canonical | strategy | code_type | code |",
        "|---|---|---|---|",
    ]
    for canon, strat, ctype, code in examples[:30]:
        lines.append(f"| `{canon}` | {strat} | {ctype} | `{code}` |")
    REPORT_OUT.write_text("\n".join(lines) + "\n")

    print(f"  promoted: {stats['promoted']:,} / {not_already_a:,} ({coverage_pct:.1f}%)")
    print(f"  unmatched: {stats['unmatched']:,}")


if __name__ == "__main__":
    main()
