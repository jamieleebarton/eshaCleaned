#!/usr/bin/env python3
"""Match every leaf of product_tree.json to FNDDS / SR28 / ESHA candidates.

For each leaf node (and meaningful internal node), builds a query from the
leaf name + 1-2 parent segments, scores every reference description by
IDF-weighted token overlap, and emits the top-3 candidates per source.

Reference data:
  FNDDS:  data/fndds/MainFoodDesc16.csv  (Food code, Main food description)
  SR28:   data/fndds/FNDDSSRLinks.csv    (unique SR code, SR description)
  ESHA:   esha_cleaned.csv               (EshaCode, Description)

Output:
  retail_mapper/v2/product_tree_matched.csv
    one row per leaf node with primary + top-3 candidates per source

Usage:
    python3 retail_mapper/v2/match_tree_to_references.py
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
TREE_JSON = V2 / "product_tree.json"
NODES_CSV = V2 / "product_tree_nodes.csv"

FNDDS_FILE = REPO / "data" / "fndds" / "MainFoodDesc16.csv"
SR_LINKS_FILE = REPO / "data" / "fndds" / "FNDDSSRLinks.csv"
ESHA_FILE = REPO / "esha_cleaned.csv"

OUT_CSV = V2 / "product_tree_matched.csv"

csv.field_size_limit(sys.maxsize)

# Only true stopwords — words that never carry product meaning.
# Words like "drink", "snack", "mix" are kept; their IDF weights handle them.
STOPWORDS = {
    "and", "with", "the", "of", "in", "on", "for", "or", "to", "a", "an",
    "no", "not", "without", "added",
    "ns", "nfs", "nsa",   # USDA shorthand for "not specified"
    "as", "is", "be", "at",
}

# These belong to OUR taxonomy tops, not specific food info — strip them from queries
TOP_LEVEL_WORDS = {
    "pantry", "snack", "beverage", "dairy", "frozen", "bakery",
    "meat", "seafood", "meal", "produce", "sports", "wellness",
    "baby", "toddler",
}


def stem(t: str) -> str:
    """Crude singularizer: drinks→drink, vegetables→vegetable, potatoes→potato.
    Conservative — only strips trailing s/es when safe."""
    if len(t) < 4: return t
    if t.endswith("ies") and len(t) > 4:
        return t[:-3] + "y"
    if t.endswith("ses") or t.endswith("xes") or t.endswith("zes") or t.endswith("ches") or t.endswith("shes"):
        return t[:-2]
    if t.endswith("oes"):
        return t[:-2]
    if t.endswith("s") and not t.endswith("ss") and not t.endswith("us") and not t.endswith("is"):
        return t[:-1]
    return t


def tokenize(s: str) -> list[str]:
    return [stem(t) for t in re.findall(r"\w+", (s or "").lower())
            if t and t not in STOPWORDS and not t.isdigit()]


def query_tokens_for_leaf(path: str, identity: str) -> list[str]:
    """Build a query from leaf name + 1-2 parent segments. Strip top-level words."""
    parts = [p.strip() for p in path.split(">") if p.strip()]
    # Use last 2 segments + identity (which is usually the last segment, but
    # also include in case the leaf name and identity differ)
    relevant = parts[-2:] if len(parts) >= 2 else parts
    txt = " ".join(relevant + [identity or ""])
    toks = tokenize(txt)
    # Also drop top-level words (Pantry, Snack, etc.) — they're our tree's
    # invention, not in USDA descriptions.
    return [t for t in toks if t not in TOP_LEVEL_WORDS]


# ---- reference loaders
def load_fndds() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not FNDDS_FILE.exists():
        print(f"  WARN: {FNDDS_FILE} missing", file=sys.stderr)
        return out
    with FNDDS_FILE.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("Food code") or "").strip()
            desc = (row.get("Main food description") or "").strip()
            wweia = (row.get("WWEIA Category description") or "").strip()
            if code and desc:
                # Combine main description + WWEIA category for richer matching
                blob = f"{desc} {wweia}".strip()
                out[code] = {"desc": desc, "wweia": wweia, "blob": blob}
    return out


def load_sr28() -> dict[str, dict]:
    """Pull unique (SR code, SR description) pairs from FNDDSSRLinks."""
    out: dict[str, dict] = {}
    if not SR_LINKS_FILE.exists():
        print(f"  WARN: {SR_LINKS_FILE} missing", file=sys.stderr)
        return out
    with SR_LINKS_FILE.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("SR code") or "").strip()
            desc = (row.get("SR description") or "").strip()
            if code and desc and code not in out:
                out[code] = {"desc": desc, "blob": desc}
    return out


def load_esha() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not ESHA_FILE.exists():
        print(f"  WARN: {ESHA_FILE} missing", file=sys.stderr)
        return out
    with ESHA_FILE.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("EshaCode") or "").strip()
            desc = (row.get("Description") or "").strip()
            if code and desc:
                out[code] = {"desc": desc, "blob": desc}
    return out


# ---- IDF index
def build_index(refs: dict[str, dict]) -> tuple[dict, dict, dict]:
    """Tokenize each reference, build inverted index + IDF weights."""
    doc_tokens: dict[str, set] = {}
    df: Counter = Counter()
    inv_index: dict[str, set] = defaultdict(set)
    for code, ref in refs.items():
        toks = set(tokenize(ref["blob"]))
        if not toks: continue
        doc_tokens[code] = toks
        for t in toks:
            df[t] += 1
            inv_index[t].add(code)
    n_docs = max(len(doc_tokens), 1)
    idf = {t: math.log(1 + n_docs / max(df[t], 1)) for t in df}
    return doc_tokens, idf, inv_index


def match_query(query_toks: list[str],
                doc_tokens: dict[str, set],
                idf: dict[str, float],
                inv_index: dict[str, set],
                top_k: int = 3) -> list[tuple[str, float]]:
    if not query_toks:
        return []
    q_unique = set(query_toks)
    # Gather candidates: any doc that shares at least one query token
    candidates: set = set()
    for t in q_unique:
        candidates.update(inv_index.get(t, ()))
    if not candidates:
        return []
    # Score each candidate
    # Use BM25-style scoring: rewards rare-token overlap, penalizes long docs.
    # Plus a "coverage" bonus when the query is mostly contained in the doc.
    scored: list[tuple[str, float]] = []
    avg_dl = sum(len(t) for t in doc_tokens.values()) / max(len(doc_tokens), 1)
    k1, b = 1.5, 0.75
    for code in candidates:
        dtoks = doc_tokens[code]
        common = q_unique & dtoks
        if not common:
            continue
        dl = len(dtoks)
        # BM25 sum
        s = 0.0
        for t in common:
            tf = 1  # we have sets, so term frequency in doc is 1
            num = tf * (k1 + 1)
            den = tf + k1 * (1 - b + b * dl / max(avg_dl, 1))
            s += idf.get(t, 0.0) * num / den
        # Strong query-coverage bonus: if all query tokens are in the doc, big boost
        coverage = len(common) / len(q_unique)
        s *= (0.5 + 1.5 * coverage)  # ranges 0.5x..2.0x
        scored.append((code, s))
    scored.sort(key=lambda kv: -kv[1])
    return scored[:top_k]


def fmt_match(matches: list[tuple[str, float]],
              refs: dict[str, dict]) -> tuple[str, str, float, str]:
    """Return (primary_code, primary_desc, primary_score, candidate_blob)."""
    if not matches:
        return "", "", 0.0, ""
    primary_code, primary_score = matches[0]
    primary_desc = refs[primary_code]["desc"]
    blob = " | ".join(
        f"{c}:{refs[c]['desc'][:50]} ({s:.2f})"
        for c, s in matches
    )
    return primary_code, primary_desc, primary_score, blob


def main() -> None:
    print("  loading reference databases...")
    fndds = load_fndds()
    sr28 = load_sr28()
    esha = load_esha()
    print(f"    FNDDS:  {len(fndds):,}")
    print(f"    SR28:   {len(sr28):,}")
    print(f"    ESHA:   {len(esha):,}")

    print("  building IDF indices...")
    fndds_dt, fndds_idf, fndds_idx = build_index(fndds)
    sr_dt, sr_idf, sr_idx = build_index(sr28)
    esha_dt, esha_idf, esha_idx = build_index(esha)

    print(f"  reading {NODES_CSV.name}")
    leaves: list[dict] = []
    with NODES_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if int(row["is_leaf"]) == 1:
                leaves.append(row)
    print(f"  {len(leaves):,} leaves to match")

    cols = [
        "leaf_path", "leaf_name", "n_skus_subtree", "n_distinct_identities",
        "sample_identities",
        "fndds_code", "fndds_desc", "fndds_score", "fndds_top3",
        "sr28_code", "sr28_desc", "sr28_score", "sr28_top3",
        "esha_code", "esha_desc", "esha_score", "esha_top3",
    ]
    n_with_fndds = n_with_sr28 = n_with_esha = 0
    matches_total = 0
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for i, leaf in enumerate(leaves, 1):
            path = leaf["path"]
            # Use the leaf's name as identity proxy
            identity = leaf["name"]
            qtoks = query_tokens_for_leaf(path, identity)
            f_match = match_query(qtoks, fndds_dt, fndds_idf, fndds_idx)
            s_match = match_query(qtoks, sr_dt, sr_idf, sr_idx)
            e_match = match_query(qtoks, esha_dt, esha_idf, esha_idx)

            f_code, f_desc, f_score, f_top = fmt_match(f_match, fndds)
            s_code, s_desc, s_score, s_top = fmt_match(s_match, sr28)
            e_code, e_desc, e_score, e_top = fmt_match(e_match, esha)

            if f_code: n_with_fndds += 1
            if s_code: n_with_sr28 += 1
            if e_code: n_with_esha += 1
            matches_total += 1

            w.writerow({
                "leaf_path": path,
                "leaf_name": leaf["name"],
                "n_skus_subtree": leaf["n_skus_subtree"],
                "n_distinct_identities": leaf["n_distinct_identities"],
                "sample_identities": leaf["sample_identities"],
                "fndds_code": f_code,
                "fndds_desc": f_desc,
                "fndds_score": f"{f_score:.3f}" if f_score else "",
                "fndds_top3": f_top,
                "sr28_code": s_code,
                "sr28_desc": s_desc,
                "sr28_score": f"{s_score:.3f}" if s_score else "",
                "sr28_top3": s_top,
                "esha_code": e_code,
                "esha_desc": e_desc,
                "esha_score": f"{e_score:.3f}" if e_score else "",
                "esha_top3": e_top,
            })
            if i % 1000 == 0:
                print(f"    {i:,} / {len(leaves):,}", flush=True)

    print()
    print(f"  wrote {OUT_CSV.name} ({len(leaves):,} leaves)")
    print(f"  coverage:")
    print(f"    FNDDS:  {n_with_fndds:,} ({100*n_with_fndds/max(matches_total,1):.0f}%)")
    print(f"    SR28:   {n_with_sr28:,} ({100*n_with_sr28/max(matches_total,1):.0f}%)")
    print(f"    ESHA:   {n_with_esha:,} ({100*n_with_esha/max(matches_total,1):.0f}%)")


if __name__ == "__main__":
    main()
