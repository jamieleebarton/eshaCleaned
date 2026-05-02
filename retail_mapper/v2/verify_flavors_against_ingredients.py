#!/usr/bin/env python3
"""Catch LLM-hallucinated flavors by checking ingredients.

For each row with a `flavor` value, check each flavor word against the
ingredients string. If the flavor word doesn't appear in ingredients,
strip it. Update `flavor`, `modifier`, `retail_leaf_path`, and
`canonical_label` to drop the stripped flavor.

Output: rewrites full_corpus_audit.csv in place + writes
retail_mapper/v2/flavor_strip_log.csv (audit trail of every strip).

Whitelist: a few flavor words that don't always appear literally in
ingredients ("vanilla" might be "natural flavors", "citrus" → various
acids). Conservative: strip only when COMPLETELY absent.
"""
from __future__ import annotations

import csv
import re
import sqlite3
import sys
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
AUDIT = V2 / "full_corpus_audit.csv"
DB = REPO / "data" / "master_products.db"
LOG = V2 / "flavor_strip_log.csv"

csv.field_size_limit(sys.maxsize)

# Flavors that we explicitly verify against ingredients. Add ones we know
# are commonly hallucinated. Each entry maps the flavor token (as it
# appears in flavor column) to a regex that matches its presence in
# ingredients. Only rows whose ingredients FAIL the regex get the flavor
# stripped.
FLAVOR_INGREDIENT_RX: dict[str, re.Pattern] = {
    "lime":          re.compile(r"\blime\b|lemon-lime|lemon lime", re.I),
    "lemon":         re.compile(r"\blemon\b", re.I),
    "orange":        re.compile(r"\borange\b", re.I),
    "cherry":        re.compile(r"\bcherr(y|ies)\b", re.I),
    "strawberry":    re.compile(r"\bstrawberr(y|ies)\b", re.I),
    "blueberry":     re.compile(r"\bblueberr(y|ies)\b", re.I),
    "raspberry":     re.compile(r"\braspberr(y|ies)\b", re.I),
    "grape":         re.compile(r"\bgrape\b", re.I),
    "mango":         re.compile(r"\bmango(es|s)?\b", re.I),
    "pineapple":     re.compile(r"\bpineapple\b", re.I),
    "peach":         re.compile(r"\bpeach(es)?\b", re.I),
    "watermelon":    re.compile(r"\bwatermelon\b", re.I),
    "apple":         re.compile(r"\bapple\b|cider", re.I),
    "banana":        re.compile(r"\bbanana(s)?\b", re.I),
    "coconut":       re.compile(r"\bcoconut\b", re.I),
    "almond":        re.compile(r"\balmond(s)?\b", re.I),
    "peanut":        re.compile(r"\bpeanut(s)?\b", re.I),
    "ginger":        re.compile(r"\bginger\b", re.I),
    "cinnamon":      re.compile(r"\bcinnamon\b", re.I),
    "pumpkin":       re.compile(r"\bpumpkin\b", re.I),
    "honey":         re.compile(r"\bhoney\b", re.I),
    "maple":         re.compile(r"\bmaple\b", re.I),
    "caramel":       re.compile(r"\bcaramel\b", re.I),
    "chocolate":     re.compile(r"\bchocolat\w*|\bcocoa\b|cacao", re.I),
}


def main() -> None:
    # Load ingredients per fdc_id
    print("  loading ingredients from master DB...")
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    ing_by_fdc: dict[str, str] = {}
    c.execute("SELECT fdc_id, ingredients_clean, ingredients FROM products")
    for fdc, ic, ir in c.fetchall():
        ing_by_fdc[str(fdc)] = (ic or ir or "")
    conn.close()
    print(f"  ingredients indexed: {len(ing_by_fdc):,}")

    tmp = AUDIT.with_suffix(".verifying.csv")
    log_rows: list[dict] = []
    n_total = 0
    n_changed = 0
    n_stripped_total = 0

    with AUDIT.open(encoding="utf-8", newline="") as fin, \
         tmp.open("w", encoding="utf-8", newline="") as fout:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
        wtr.writeheader()
        for r in rdr:
            n_total += 1
            fdc = r.get("fdc_id", "")
            flav = (r.get("flavor", "") or "").strip()
            if not flav:
                wtr.writerow(r)
                continue
            ing = ing_by_fdc.get(fdc, "")
            if not ing:
                wtr.writerow(r)
                continue
            # Split flavor by | or ,
            parts = re.split(r"[|,]", flav)
            kept: list[str] = []
            stripped: list[str] = []
            for p in parts:
                p = p.strip().lower()
                if not p:
                    continue
                if p in FLAVOR_INGREDIENT_RX:
                    if FLAVOR_INGREDIENT_RX[p].search(ing):
                        kept.append(p)
                    else:
                        stripped.append(p)
                else:
                    kept.append(p)
            if not stripped:
                wtr.writerow(r)
                continue
            n_changed += 1
            n_stripped_total += len(stripped)
            new_flavor = " | ".join(kept)
            r["flavor"] = new_flavor
            # Rebuild modifier from variant + (verified) flavor + form facets
            # Conservatively: just rewrite modifier by removing each stripped
            # flavor as a Title-Cased token.
            mod = r.get("modifier", "") or ""
            for s in stripped:
                title = s.title()
                # Drop "Title > " prefix, " > Title" suffix, or " > Title >"
                mod = re.sub(rf"^\s*{re.escape(title)}\s*>\s*", "", mod)
                mod = re.sub(rf"\s*>\s*{re.escape(title)}\s*$", "", mod)
                mod = re.sub(rf"\s*>\s*{re.escape(title)}\s*>\s*", " > ", mod)
                mod = re.sub(rf"^\s*{re.escape(title)}\s*$", "", mod)
            r["modifier"] = mod
            # Same on retail_leaf_path
            rlp = r.get("retail_leaf_path", "") or ""
            for s in stripped:
                title = s.title()
                rlp = re.sub(rf"\s*>\s*{re.escape(title)}\s*", " > ", rlp)
                rlp = re.sub(rf"\s*>\s*{re.escape(title)}$", "", rlp)
            r["retail_leaf_path"] = re.sub(r"\s*>\s*$", "", rlp.strip())
            # And canonical_label parens
            cl = r.get("canonical_label", "") or ""
            for s in stripped:
                title = s.title()
                cl = re.sub(rf"\(\s*{re.escape(title)}\s*,\s*", "(", cl)
                cl = re.sub(rf",\s*{re.escape(title)}\s*\)", ")", cl)
                cl = re.sub(rf"\(\s*{re.escape(title)}\s*\)", "", cl)
            r["canonical_label"] = cl.strip()
            wtr.writerow(r)
            log_rows.append({
                "fdc_id": fdc,
                "title": (r.get("title", "") or "")[:60],
                "stripped_flavors": ",".join(stripped),
                "kept_flavors": ",".join(kept),
                "ingredients_snippet": ing[:120],
            })

    shutil.move(str(tmp), str(AUDIT))
    print(f"  total rows: {n_total:,}")
    print(f"  rows with flavor changes: {n_changed:,}")
    print(f"  total false-flavor strips: {n_stripped_total:,}")

    # Emit log
    if log_rows:
        cols = list(log_rows[0].keys())
        with LOG.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"  wrote {LOG.name}")


if __name__ == "__main__":
    main()
