#!/usr/bin/env python3
"""V2 lookup: priced_products is the AUTHORITY for canonical_path per
identity. The calculator queries priced_products at runtime, so the lookup
must agree with priced_products.

Resolution order (priority high → low):
  1. Manual override (`buy_form_path_overrides.csv`)
  2. priced_products: consensus_pid == canonical_buy_form (case + plural)
  3. priced_products: canonical_label match
  4. api_cache: product_identity_fixed match
  5. recipe_ingredient_taxonomy: title match
  6. unresolved

For each canonical_buy_form we count products at each candidate canonical_path
across ALL sources, but PREFER paths where priced_products has the most
matching products (since the calculator queries priced_products).

Output:
  recipe_pricing/buy_form_to_canonical_path.csv  (replaces v1)
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
API = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
RECIPE_TAX = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
CLEANED_CLS = ROOT / "recipe_pricing" / "buyability_classifications_cleaned.jsonl"
OVERRIDES = ROOT / "recipe_pricing" / "buy_form_path_overrides.csv"
OUT = ROOT / "recipe_pricing" / "buy_form_to_canonical_path.csv"


def normalize(s: str) -> str:
    return (s or "").lower().strip()


def singularize(s: str) -> str:
    if s.endswith("s") and not s.endswith("ss") and len(s) > 3:
        return s[:-1]
    return s


def main() -> int:
    # 1. Load all unique canonical_buy_form values from cleaned classifier
    print("loading canonical_buy_form values...", file=sys.stderr)
    buy_forms: Counter = Counter()
    with CLEANED_CLS.open() as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            for c in r.get("classifications", []):
                bf = (c.get("canonical_buy_form") or "").strip()
                if bf:
                    buy_forms[normalize(bf)] += 1
    print(f"  {len(buy_forms):,} unique buy_forms", file=sys.stderr)

    # 2. Build PRIMARY index from priced_products: pid → list of (path, n)
    print("indexing priced_products...", file=sys.stderr)
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""
        SELECT consensus_pid, consensus_canonical, COUNT(*) FROM priced_products
        WHERE consensus_pid IS NOT NULL AND consensus_pid != ''
          AND consensus_canonical IS NOT NULL AND consensus_canonical != ''
          AND available = 1 AND grams > 0 AND cents > 0
        GROUP BY consensus_pid, consensus_canonical
    """)
    pp_pid_paths: defaultdict[str, Counter] = defaultdict(Counter)
    for pid, cp, n in cur.fetchall():
        pp_pid_paths[normalize(pid)][cp] += n
    print(f"  {len(pp_pid_paths):,} unique pids in priced_products", file=sys.stderr)

    # Also: priced_products by canonical_label
    cur.execute("""
        SELECT canonical_label, consensus_canonical, COUNT(*) FROM priced_products
        WHERE canonical_label IS NOT NULL AND canonical_label != ''
          AND consensus_canonical IS NOT NULL AND consensus_canonical != ''
          AND available = 1 AND grams > 0 AND cents > 0
        GROUP BY canonical_label, consensus_canonical
    """)
    pp_label_paths: defaultdict[str, Counter] = defaultdict(Counter)
    for lbl, cp, n in cur.fetchall():
        pp_label_paths[normalize(lbl)][cp] += n
    print(f"  {len(pp_label_paths):,} unique labels in priced_products", file=sys.stderr)

    # 3. SECONDARY: api_cache pif index
    print("indexing api_cache...", file=sys.stderr)
    api_pif: defaultdict[str, Counter] = defaultdict(Counter)
    with API.open() as f:
        for row in csv.DictReader(f):
            pif = normalize(row.get("product_identity_fixed", ""))
            cp = (row.get("canonical_path") or "").strip()
            if pif and cp:
                api_pif[pif][cp] += 1
    print(f"  {len(api_pif):,} unique pifs in api_cache", file=sys.stderr)

    # 4. TERTIARY: recipe_ingredient_taxonomy title index
    print("indexing recipe_ingredient_taxonomy...", file=sys.stderr)
    title_idx: defaultdict[str, Counter] = defaultdict(Counter)
    with RECIPE_TAX.open() as f:
        for row in csv.DictReader(f):
            t = normalize(row.get("title", ""))
            cp = (row.get("canonical_path") or "").strip()
            if t and cp:
                title_idx[t][cp] += 1
    print(f"  {len(title_idx):,} unique titles in recipe_ingredient_taxonomy", file=sys.stderr)

    # 5. Load manual overrides (highest priority)
    overrides: dict[str, str] = {}
    if OVERRIDES.exists():
        with OVERRIDES.open() as f:
            for row in csv.DictReader(f):
                bf = normalize(row.get("canonical_buy_form", ""))
                cp = (row.get("canonical_path") or "").strip()
                if bf and cp:
                    overrides[bf] = cp
    print(f"  {len(overrides):,} manual overrides", file=sys.stderr)

    # 6a. Build CANONICAL_PATH token index from priced_products with
    #    INVERTED INDEX for fast lookup. token → list of (path_idx).
    print("indexing priced_products canonical_paths by token (inverted)...", file=sys.stderr)
    SOFT_TOK = {"the","a","an","of","and","or","with","for","fresh","whole","raw"}
    cur.execute("""
        SELECT consensus_canonical, COUNT(*)
        FROM priced_products
        WHERE consensus_canonical IS NOT NULL AND consensus_canonical != ''
          AND available = 1 AND grams > 0 AND cents > 0
          AND consensus_canonical NOT LIKE 'Non-Food%'
        GROUP BY consensus_canonical
    """)
    paths_list: list[tuple[str, int, int]] = []  # (path, n_products, n_tokens)
    inverted: defaultdict[str, set[int]] = defaultdict(set)
    for cp, n in cur.fetchall():
        toks = set()
        for seg in cp.split(" > "):
            for w in re.sub(r"[^\w\s]", "", seg.lower()).split():
                if w in SOFT_TOK or len(w) <= 2:
                    continue
                if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
                    w = w[:-1]
                toks.add(w)
        if not toks:
            continue
        idx = len(paths_list)
        paths_list.append((cp, n, len(toks)))
        for t in toks:
            inverted[t].add(idx)
    print(f"  {len(paths_list):,} paths, {len(inverted):,} unique tokens", file=sys.stderr)

    def path_token_lookup(bf: str) -> tuple[str, int]:
        """Find canonical_path whose token set CONTAINS all noun words of bf.
        Inverted-index intersection; very fast."""
        bf_norm = bf.lower().replace("-", " ")
        words = set()
        for w in re.sub(r"[^\w\s]", "", bf_norm).split():
            if w in SOFT_TOK or len(w) <= 2:
                continue
            if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
                w = w[:-1]
            words.add(w)
        if not words:
            return "", 0
        # Intersect inverted-index sets for each token
        sets_list = [inverted.get(w, set()) for w in words]
        if not sets_list or not all(sets_list):
            return "", 0
        # Start with smallest set for efficiency
        sets_list.sort(key=len)
        candidates_idx = sets_list[0]
        for s in sets_list[1:]:
            candidates_idx = candidates_idx & s
            if not candidates_idx:
                return "", 0
        # Convert to path tuples; prefer longer path (more specific) then more products
        candidates = [paths_list[i] for i in candidates_idx]
        candidates.sort(key=lambda x: (-x[2], -x[1]))
        return candidates[0][0], candidates[0][1]

    # 6b. NAME-substring fallback: search priced_products product NAMES
    #    when path-token doesn't match.
    def name_substring_lookup(bf: str) -> tuple[str, int]:
        """Return (canonical_path, n_matches) for the dominant path where
        priced_products has products whose name contains all noun words
        of bf."""
        SOFT = {"the","a","an","of","and","or","with","for","fresh","whole","raw"}
        words = [w for w in bf.split() if w and w not in SOFT and len(w) > 2]
        if not words:
            return "", 0
        # Build SQL with all word LIKEs
        where = " AND ".join("LOWER(name) LIKE '%' || ? || '%'" for _ in words)
        sql = f"""
            SELECT consensus_canonical, COUNT(*) FROM priced_products
            WHERE {where}
              AND available = 1 AND grams > 0 AND cents > 0
              AND consensus_canonical NOT LIKE 'Non-Food%'
              AND consensus_canonical != ''
            GROUP BY consensus_canonical
            ORDER BY 2 DESC LIMIT 5
        """
        cur.execute(sql, words)
        rows = cur.fetchall()
        if not rows:
            return "", 0
        # Prefer food-category top
        FOOD_TOPS = ("Pantry", "Produce", "Dairy", "Frozen", "Bakery",
                      "Beverage", "Snack", "Meat & Seafood", "Meal",
                      "Sports & Wellness")
        for cp, n in rows:
            if any(cp.startswith(t) for t in FOOD_TOPS):
                return cp, n
        return rows[0][0], rows[0][1]

    # 7. Resolve each buy_form
    def lookup(bf: str) -> tuple[str, str]:
        """Return (canonical_path, source). Empty path = unresolved."""
        # Highest: manual override
        if bf in overrides:
            return overrides[bf], "override"
        # Try direct + singular + plural across each source
        for variant_func, variant_label in [
            (lambda s: s, ""),
            (singularize, "_singular"),
            (lambda s: s + "s" if not s.endswith("s") else s, "_plural"),
        ]:
            v = variant_func(bf)
            if v != bf and variant_label == "":
                continue
            # priced_products PID match (highest authority)
            if v in pp_pid_paths:
                cp_counts = pp_pid_paths[v]
                if cp_counts:
                    cp = cp_counts.most_common(1)[0][0]
                    return cp, "priced_pid" + variant_label
            # priced_products LABEL match
            if v in pp_label_paths:
                cp_counts = pp_label_paths[v]
                if cp_counts:
                    cp = cp_counts.most_common(1)[0][0]
                    return cp, "priced_label" + variant_label
            # api_cache PIF
            if v in api_pif:
                cp_counts = api_pif[v]
                if cp_counts:
                    cp = cp_counts.most_common(1)[0][0]
                    return cp, "api_pif" + variant_label
        # PATH-TOKEN match: only run if buy_form has 2-4 specific noun words
        # (otherwise too generic or too specific). Cached per buy_form.
        bf_words = [w for w in bf.lower().replace("-"," ").split()
                    if w not in {"the","a","an","of","and","or","with","for","fresh","whole","raw"}
                    and len(w) > 2]
        if 2 <= len(bf_words) <= 4:
            cp_token, n = path_token_lookup(bf)
            if cp_token and n >= 3:
                return cp_token, "path_token"
        # Last resort: recipe_title
        if bf in title_idx:
            cp_counts = title_idx[bf]
            if cp_counts:
                cp = cp_counts.most_common(1)[0][0]
                return cp, "recipe_title"
        return "", "unresolved"

    rows_out = []
    sources: Counter = Counter()
    print(f"resolving {len(buy_forms):,} buy_forms...", file=sys.stderr, flush=True)
    n_done = 0
    for bf, recipe_count in buy_forms.most_common():
        cp, source = lookup(bf)
        sources[source] += 1
        rows_out.append({
            "canonical_buy_form": bf,
            "canonical_path": cp,
            "source": source,
            "buy_form_recipe_count": recipe_count,
        })
        n_done += 1
        if n_done % 5000 == 0:
            print(f"  {n_done:,}/{len(buy_forms):,}", file=sys.stderr, flush=True)

    # Sort: unresolved first by recipe_count (most painful gaps), then resolved
    rows_out.sort(key=lambda r: (r["canonical_path"] != "", -r["buy_form_recipe_count"]))

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "canonical_buy_form", "canonical_path", "source",
            "buy_form_recipe_count",
        ])
        w.writeheader()
        w.writerows(rows_out)

    print(f"\nresolution sources:", file=sys.stderr)
    for src, n in sources.most_common():
        print(f"  {src:<28} {n:>6,}", file=sys.stderr)
    print(f"\n  → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
