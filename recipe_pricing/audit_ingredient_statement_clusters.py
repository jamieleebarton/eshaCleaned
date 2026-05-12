#!/usr/bin/env python3
"""Cluster priced_products SKUs by ingredient_statement (FDA label).

Two products with substantially the same top-N ingredients are functionally
the same food, regardless of brand / spelling / canonical_path leaf.

Strategy:
  1. For each Kroger SKU, parse its ingredient_statement from api_cache.db.
  2. Normalize: lowercase, strip punctuation/parentheses, drop standardized
     phrases ('contains 2% or less of'), split on commas, take first 3.
  3. Cluster SKUs by their normalized 3-token signature.
  4. Surface clusters that span ≥ 2 distinct canonical_paths — these are
     the cross-path equivalences (spelling dups, facet leaves, etc.).

Output: alias map CSV that maps each non-canonical path to its canonical
form (= the canonical_path with the most SKUs in the cluster).
"""
from __future__ import annotations
import csv, json, re, sqlite3, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
API_DB = Path("/Users/jamiebarton/Desktop/Hestia/api/data/api_cache.db")
OUT_ALIAS = ROOT / "recipe_pricing" / "canonical_path_aliases.csv"
OUT_CLUSTERS = ROOT / "recipe_pricing" / "ingredient_clusters_audit.csv"


def normalize_ingredients(stmt: str) -> tuple[str, ...]:
    """Return top-3 ingredient tokens from an ingredient_statement."""
    s = (stmt or "").lower().strip()
    if not s: return ()
    # Drop standardized phrases
    for phrase in (
        "contains 2% or less of", "contains less than 2% of",
        "contains less than 1% of", "contains less than 0.5% of",
        "less than 2% of the following", "less than 2%",
        "ingredients:", "ingredients :",
    ):
        s = s.replace(phrase, ",")
    # Strip parentheses content
    s = re.sub(r"\([^)]*\)", "", s)
    # Strip square brackets
    s = re.sub(r"\[[^\]]*\]", "", s)
    # Split on commas, semicolons, periods
    parts = re.split(r"[,;.]+", s)
    cleaned = []
    for p in parts:
        p = re.sub(r"[^a-z0-9 \-]", " ", p).strip()
        p = re.sub(r"\s+", " ", p)
        if not p or len(p) < 2: continue
        # Skip phrases that aren't single ingredients
        if any(skip in p for skip in (
            "may contain", "produced in", "manufactured", "facility",
            "natural flavor", "artificial flavor", "and/or", "plus",
        )):
            continue
        cleaned.append(p)
        if len(cleaned) >= 3: break
    return tuple(cleaned[:3])


def collect_ingredient_statements() -> dict[str, str]:
    """upc → ingredient_statement (best Kroger source, first wins)."""
    out: dict[str, str] = {}
    api = sqlite3.connect(str(API_DB))
    acur = api.cursor()
    acur.execute("SELECT raw_json FROM api_cache WHERE source LIKE 'kroger%'")
    for (j,) in acur.fetchall():
        try: d = json.loads(j)
        except: continue
        items = d if isinstance(d, list) else d.get("items", d.get("data", []))
        if not isinstance(items, list): continue
        for item in items:
            upc = item.get("upc") or item.get("product_meta", {}).get("kroger_upc")
            if not upc or upc in out: continue
            stmt = item.get("product_meta", {}).get("ingredient_statement", "")
            if stmt and len(stmt) > 5:
                out[upc] = stmt
    api.close()
    return out


def main():
    print("loading kroger ingredient_statements…", file=sys.stderr)
    upc_stmt = collect_ingredient_statements()
    print(f"  {len(upc_stmt):,} UPCs with statements", file=sys.stderr)

    print("loading priced_products…", file=sys.stderr)
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""SELECT upc, name, consensus_canonical FROM priced_products
        WHERE available=1 AND consensus_canonical IS NOT NULL
          AND consensus_canonical != ''""")
    sku_path: dict[str, tuple[str, str]] = {}
    for upc, name, cp in cur.fetchall():
        if upc not in sku_path: sku_path[upc] = (name or "", cp)

    print("clustering by ingredient signature…", file=sys.stderr)
    clusters: dict[tuple, list[dict]] = defaultdict(list)
    for upc, stmt in upc_stmt.items():
        if upc not in sku_path: continue
        sig = normalize_ingredients(stmt)
        if len(sig) < 2: continue  # need at least 2 tokens for meaningful cluster
        name, cp = sku_path[upc]
        clusters[sig].append({"upc": upc, "name": name[:60], "cp": cp})

    print(f"  {len(clusters):,} distinct ingredient signatures", file=sys.stderr)

    # Surface cross-path clusters
    cross_path_clusters = []
    for sig, members in clusters.items():
        paths = Counter(m["cp"] for m in members)
        if len(paths) < 2 or len(members) < 5: continue  # need ≥5 members ≥2 paths
        # The dominant path is the canonical
        canonical_path = paths.most_common(1)[0][0]
        cross_path_clusters.append({
            "ingredient_sig": " | ".join(sig),
            "n_skus": len(members),
            "n_paths": len(paths),
            "canonical_path": canonical_path,
            "other_paths": "; ".join(p for p, _ in paths.most_common()[1:6]),
            "path_counts": "; ".join(f"{p}({c})" for p, c in paths.most_common()),
        })

    cross_path_clusters.sort(key=lambda c: -c["n_skus"])
    print(f"  cross-path clusters (≥5 members, ≥2 paths): {len(cross_path_clusters)}",
          file=sys.stderr)

    OUT_CLUSTERS.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CLUSTERS.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cross_path_clusters[0].keys()) if cross_path_clusters else [
            "ingredient_sig","n_skus","n_paths","canonical_path","other_paths","path_counts"])
        w.writeheader()
        for r in cross_path_clusters: w.writerow(r)
    print(f"  → {OUT_CLUSTERS}", file=sys.stderr)

    # CONSERVATIVE alias map: only when:
    #   - canonical_path has >= 80% of cluster's SKUs
    #   - non-canonical paths have <= 3 SKUs each (small fragments)
    #   - paths are at the same canonical_path PARENT (siblings only)
    # This catches spelling duplicates and tiny fragments without
    # over-aliasing legitimate-different-food clusters.
    aliases: dict[str, dict] = {}
    for cluster in cross_path_clusters:
        canonical = cluster["canonical_path"]
        canonical_parent = " > ".join(canonical.split(" > ")[:-1])
        # Parse path counts
        path_counts: dict[str, int] = {}
        for entry in cluster["path_counts"].split("; "):
            m = re.match(r"^(.+?)\((\d+)\)$", entry.strip())
            if m: path_counts[m.group(1).strip()] = int(m.group(2))
        canonical_count = path_counts.get(canonical, 0)
        total = sum(path_counts.values())
        if canonical_count / max(1, total) < 0.6: continue
        for path, count in path_counts.items():
            if path == canonical: continue
            if count > 3: continue  # too many to be a fragment
            other_parent = " > ".join(path.split(" > ")[:-1])
            # Allow same-parent (sibling fragments) OR clear spelling dup
            same_parent = (other_parent == canonical_parent)
            spelling_close = path.replace("Chilies","Chiles").replace("Chickpea","Garbanzo Bean") == canonical
            if not (same_parent or spelling_close): continue
            if path not in aliases:
                aliases[path] = {
                    "canonical": canonical,
                    "ingredient_sig": cluster["ingredient_sig"],
                }

    with OUT_ALIAS.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["old_path","new_path","reason","ingredient_sig"])
        w.writeheader()
        for old, info in sorted(aliases.items()):
            w.writerow({"old_path": old, "new_path": info["canonical"],
                         "reason": "ingredient_statement_cluster",
                         "ingredient_sig": info["ingredient_sig"]})
    print(f"  → {OUT_ALIAS}  ({len(aliases)} aliases)", file=sys.stderr)

    print(f"\n=== TOP 20 cross-path clusters by SKU count ===")
    for c in cross_path_clusters[:20]:
        print(f"\n  ingredients: {c['ingredient_sig'][:75]}")
        print(f"  {c['n_skus']} SKUs across {c['n_paths']} paths")
        print(f"  canonical: {c['canonical_path'][:70]}")
        print(f"  paths: {c['path_counts'][:200]}")


if __name__ == "__main__":
    main()
