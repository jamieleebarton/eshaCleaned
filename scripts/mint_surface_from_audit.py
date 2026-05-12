#!/usr/bin/env python3
"""Phase 3 — mint surface rows for audit canonical_labels not in the curated table.

Reads the Phase-2 backfilled surface CSV. For each distinct audit
canonical_label (and path-leaf) NOT already keyed in surface, mint a new row
with FNDDS+SR28 codes from the audit's modal vote. New rows are appended;
existing curated rows are NEVER overwritten.

Reads:
  AUDIT_CSV     — codex_full_corpus_audit.csv
  SURFACE_IN    — clean/canonical_surface_audit_backfilled.csv
  PACKAGES_DB   — Hestia/api/data/food_packages_final.db (only mint canonicals
                  whose modal FNDDS exists in packages, so we don't add dead
                  rows the calculator can't price)

Writes:
  SURFACE_OUT   — clean/canonical_surface_audit_full.csv
  REPORT        — implementation/output/surface_mint_report.md
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
SURFACE_IN = Path(os.environ.get("SURFACE_IN") or (CLEAN / "canonical_surface_audit_backfilled.csv"))
SURFACE_OUT = Path(os.environ.get("SURFACE_OUT") or (CLEAN / "canonical_surface_audit_full.csv"))
REPORT_OUT = Path(os.environ.get("REPORT") or (OUTPUT / "surface_mint_report.md"))
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
    packages_fndds = load_packages_fndds()
    print(f"  packages: {len(packages_fndds):,} distinct FNDDS codes with prices")

    print(f"  reading surface (Phase 2 output): {SURFACE_IN.name}")
    with SURFACE_IN.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        surface_rows = list(reader)
    print(f"  surface: {len(surface_rows):,} rows")

    surface_keys: set[str] = set()
    for row in surface_rows:
        for field in ("canonical_normalized", "canonical_shopping_item", "canonical_surface", "family_base"):
            k = normalize_key(row.get(field) or "")
            if k:
                surface_keys.add(k)
    print(f"  surface covered keys: {len(surface_keys):,}")

    print(f"  reading audit: {AUDIT_CSV.name}")
    label_to_canon: dict[str, str] = {}  # normalized → display
    fndds_by_label: dict[str, Counter] = defaultdict(Counter)
    sr28_by_label: dict[str, Counter] = defaultdict(Counter)
    esha_by_label: dict[str, Counter] = defaultdict(Counter)
    path_by_label: dict[str, str] = {}

    with AUDIT_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                score = float(row.get("match_score") or 0)
            except ValueError:
                score = 0.0
            if score < MIN_MATCH_SCORE:
                continue
            label = (row.get("canonical_label") or "").strip()
            path = (row.get("canonical_path") or "").strip()
            if not label and ">" in path:
                label = path.rsplit(">", 1)[-1].strip()
            if not label:
                continue
            key = normalize_key(label)
            if not key:
                continue
            if key not in label_to_canon:
                label_to_canon[key] = label
                path_by_label[key] = path
            f_code = (row.get("fndds_code") or "").strip()
            f_desc = (row.get("fndds_desc") or "").strip()
            s_code = (row.get("sr28_code") or "").strip()
            s_desc = (row.get("sr28_desc") or "").strip()
            e_code = (row.get("esha_code") or "").strip()
            e_desc = (row.get("esha_desc") or "").strip()
            if f_code:
                fndds_by_label[key][(f_code, f_desc)] += 1
            if s_code:
                sr28_by_label[key][(s_code, s_desc)] += 1
            if e_code:
                esha_by_label[key][(e_code, e_desc)] += 1

    print(f"  audit canonicals: {len(label_to_canon):,}")

    minted = 0
    skipped_no_packaged_fndds = 0
    skipped_already_in_surface = 0
    new_rows: list[dict[str, str]] = []

    blank_template = {f: "" for f in fieldnames}

    for key, display in sorted(label_to_canon.items()):
        if key in surface_keys:
            skipped_already_in_surface += 1
            continue
        f_pair = best_modal(fndds_by_label.get(key, Counter()))
        s_pair = best_modal(sr28_by_label.get(key, Counter()))
        e_pair = best_modal(esha_by_label.get(key, Counter()))

        # Require either a packaged FNDDS or an SR28 code; otherwise this
        # canonical can't be priced or have nutrition resolved usefully.
        f_packaged = f_pair and (not packages_fndds or f_pair[0] in packages_fndds)
        if not (f_packaged or s_pair):
            skipped_no_packaged_fndds += 1
            continue

        new = dict(blank_template)
        new["canonical_surface"] = display
        new["canonical_normalized"] = key
        new["canonical_shopping_item"] = display
        new["family_base"] = display.lower()
        new["record_type"] = "ingredient"
        path = path_by_label.get(key, "")
        if path:
            new["product_query"] = path

        if f_packaged:
            f_code, f_desc = f_pair
            new["fndds_code"] = f_code
            new["fndds_description"] = f_desc
            new["fndds_match_type"] = "audit_modal_minted"
            new["nutrition_match_state"] = "fndds_match"
        elif s_pair:
            s_code, s_desc = s_pair
            new["sr28_code"] = s_code
            new["sr28_description"] = s_desc
            new["sr28_match_type"] = "audit_modal_minted"
            new["nutrition_match_state"] = "sr28_match"

        if s_pair and not new.get("sr28_code"):
            s_code, s_desc = s_pair
            new["sr28_code"] = s_code
            new["sr28_description"] = s_desc
            new["sr28_match_type"] = "audit_modal_minted"
        if e_pair and not new.get("esha_code"):
            e_code, e_desc = e_pair
            new["esha_code"] = e_code
            new["esha_description"] = e_desc

        new["notes"] = "minted from codex_full_corpus_audit.csv"
        new_rows.append(new)
        minted += 1

    print(f"  minted: {minted:,}")
    print(f"  skipped (already in surface): {skipped_already_in_surface:,}")
    print(f"  skipped (no packaged FNDDS or SR28): {skipped_no_packaged_fndds:,}")

    out_rows = surface_rows + new_rows
    print(f"  writing combined surface: {len(out_rows):,} rows → {SURFACE_OUT.name}")
    with SURFACE_OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Surface Mint Report",
        "",
        f"- audit: `{AUDIT_CSV.name}` ({len(label_to_canon):,} canonicals)",
        f"- surface in: `{SURFACE_IN.name}` ({len(surface_rows):,} rows)",
        f"- surface out: `{SURFACE_OUT.name}` ({len(out_rows):,} rows)",
        f"- packages DB: `{PACKAGES_DB.name}` ({len(packages_fndds):,} priced FNDDS codes)",
        "",
        "## Outcome",
        "",
        f"- minted new rows: **{minted:,}**",
        f"- skipped (already covered): {skipped_already_in_surface:,}",
        f"- skipped (no packaged FNDDS or SR28): {skipped_no_packaged_fndds:,}",
        "",
        "## Examples (first 30 minted)",
        "",
        "| canonical | path | fndds | sr28 |",
        "|---|---|---|---|",
    ]
    for r in new_rows[:30]:
        lines.append(
            f"| `{r['canonical_normalized']}` | {r.get('product_query','')} | `{r.get('fndds_code','')}` | `{r.get('sr28_code','')}` |"
        )
    REPORT_OUT.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
