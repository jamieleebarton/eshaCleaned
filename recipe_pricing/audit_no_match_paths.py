#!/usr/bin/env python3
"""Mine the recipe_line_comparison_50k.csv for no_match paths and auto-
generate alias candidates from priced_products.

Output: recipe_pricing/no_match_alias_candidates.csv with rows
  recipe_path, alt_path, n_skus_at_alt, n_failing_lines, confidence

Confidence:
  high   — same word-stem + ASCII fold + same parent OR a strict synonym
  medium — leaf token matches in same word family
  low    — different leaf token; likely needs picker fallback, not alias
"""
from __future__ import annotations
import csv, re, sqlite3, sys, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
LINES_CSV = ROOT / "planner" / "data" / "recipe_line_comparison_50k.csv"
DB        = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT       = ROOT / "recipe_pricing" / "no_match_alias_candidates.csv"


def ascii_fold(s: str) -> str:
    """Normalize unicode (Jalapeño → Jalapeno)."""
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def lemma(token: str) -> str:
    """Crude singular form."""
    t = token.strip()
    if t.endswith("ies") and len(t) > 3: return t[:-3] + "y"
    if t.endswith("es") and len(t) > 3: return t[:-2]
    if t.endswith("s") and len(t) > 2 and not t.endswith("ss"): return t[:-1]
    return t


def normalize_leaf(leaf: str) -> set[str]:
    """Extract food-identity tokens from a path leaf."""
    s = ascii_fold(leaf).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    tokens = [lemma(t) for t in s.split() if len(t) > 2]
    # Drop pure facets / adjectives that aren't food identity
    drop = {"plain","whole","fresh","frozen","canned","dried","mild",
            "hot","medium","organic","large","small","baby","jumbo",
            "ground","sliced","chopped","diced","crushed","minced",
            "the","of","and","or","with","for","red","green","yellow","white"}
    return set(t for t in tokens if t not in drop)


def main():
    print(f"loading no_match lines from {LINES_CSV.name}…", file=sys.stderr)
    fail_counts: Counter = Counter()
    with LINES_CSV.open() as f:
        for row in csv.DictReader(f):
            if row["our_sku"] != "(none)": continue
            cp = (row.get("our_canonical_path") or "").strip()
            if not cp: continue
            fail_counts[cp] += 1
    print(f"  {len(fail_counts):,} distinct failing canonical_paths", file=sys.stderr)
    print(f"  {sum(fail_counts.values()):,} total no_match lines", file=sys.stderr)

    # Index priced_products by canonical_path with SKU counts and food-token set
    print("indexing priced_products…", file=sys.stderr)
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""SELECT consensus_canonical, COUNT(DISTINCT upc)
        FROM priced_products WHERE available=1
          AND consensus_canonical IS NOT NULL AND consensus_canonical != ''
        GROUP BY consensus_canonical""")
    path_skus: dict[str, int] = {cp: n for cp, n in cur.fetchall()}
    print(f"  {len(path_skus):,} priced canonical_paths", file=sys.stderr)

    # Build leaf-token → list of (path, sku_count) for every priced path
    leaf_index: dict[frozenset, list[tuple[str, int]]] = defaultdict(list)
    for cp, n in path_skus.items():
        if n == 0: continue
        leaf = cp.split(" > ")[-1]
        toks = normalize_leaf(leaf)
        if not toks: continue
        leaf_index[frozenset(toks)].append((cp, n))

    candidates = []
    for recipe_path, n_fail in fail_counts.most_common():
        own_sku_count = path_skus.get(recipe_path, 0)
        if own_sku_count > 0: continue  # path is fine, must be picker filter
        recipe_leaf = recipe_path.split(" > ")[-1]
        recipe_toks = normalize_leaf(recipe_leaf)
        if not recipe_toks: continue
        # Find best alternative: priced path whose leaf tokens overlap
        best_alt = None; best_score = 0
        # First pass: exact token-set match
        if frozenset(recipe_toks) in leaf_index:
            for alt_path, alt_n in leaf_index[frozenset(recipe_toks)]:
                if alt_path == recipe_path: continue
                if alt_n > best_score:
                    best_alt = alt_path; best_score = alt_n
        confidence = "high" if best_alt else None
        # Second pass: superset/subset
        if not best_alt:
            for tok_set, alts in leaf_index.items():
                # Strong overlap: recipe_toks ⊂ tok_set OR tok_set ⊂ recipe_toks
                if not (recipe_toks <= tok_set or tok_set <= recipe_toks):
                    continue
                if not (recipe_toks & tok_set): continue
                for alt_path, alt_n in alts:
                    if alt_path == recipe_path: continue
                    if alt_n > best_score:
                        best_alt = alt_path; best_score = alt_n
                        confidence = "medium"
        # Third pass: any token overlap (low confidence)
        if not best_alt:
            for tok_set, alts in leaf_index.items():
                if not (recipe_toks & tok_set): continue
                # Only use if shared ≥1 token AND sets are similar size
                shared = recipe_toks & tok_set
                if len(shared) < min(len(recipe_toks), len(tok_set)): continue
                for alt_path, alt_n in alts:
                    if alt_path == recipe_path: continue
                    if alt_n > best_score:
                        best_alt = alt_path; best_score = alt_n
                        confidence = "low"
        if not best_alt: continue
        candidates.append({
            "recipe_path": recipe_path,
            "alt_path": best_alt,
            "n_skus_at_alt": best_score,
            "n_failing_lines": n_fail,
            "confidence": confidence,
            "recipe_leaf_tokens": "|".join(sorted(recipe_toks)),
            "alt_leaf_tokens": "|".join(sorted(normalize_leaf(best_alt.split(" > ")[-1]))),
        })

    candidates.sort(key=lambda c: -c["n_failing_lines"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(candidates[0].keys()) if candidates else
            ["recipe_path","alt_path","n_skus_at_alt","n_failing_lines","confidence",
             "recipe_leaf_tokens","alt_leaf_tokens"])
        w.writeheader()
        for c in candidates: w.writerow(c)
    print(f"\nwrote {len(candidates)} alias candidates → {OUT}", file=sys.stderr)

    by_conf = Counter(c["confidence"] for c in candidates)
    print(f"\nconfidence breakdown:", file=sys.stderr)
    for conf in ("high","medium","low"):
        n_paths = by_conf.get(conf, 0)
        n_lines = sum(c["n_failing_lines"] for c in candidates if c["confidence"] == conf)
        print(f"  {conf:<8}  {n_paths:>4} candidates, {n_lines:,} failing lines",
              file=sys.stderr)

    print(f"\n=== TOP 25 candidates by failing line count ===")
    for c in candidates[:25]:
        print(f"  {c['confidence']:<6}  +{c['n_failing_lines']:>4} lines  "
              f"{c['recipe_path'][:50]:<50} → {c['alt_path'][:50]} (n={c['n_skus_at_alt']})")


if __name__ == "__main__":
    main()
