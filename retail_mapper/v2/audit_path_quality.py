#!/usr/bin/env python3
"""Surface every path-quality issue in full_corpus_audit.csv.

Issues detected:
  1. Sorted-token duplicate clusters — leaves with same words in different
     orders (e.g., 'Garlic Butter' vs 'Butter Garlic').
  2. Comma-in-segment paths (e.g., 'Pancakes, Waffles, French Toast & Crepes').
  3. Repeated-word leaves (e.g., 'Chocolate Chocolate Chip') — minus the
     allowlist of real product names (Mahi Mahi, Half & Half, …).
  4. Deep paths (≥5 segments).

The script also computes a `suggested_canonical` per duplicate-cluster using
this rule order:
  1. MANUAL_LEAF_CANONICAL — explicit override
  2. FNDDS desc anchor — pick form whose word-order matches an FNDDS desc
  3. Title plurality — most common form across product titles
  4. SKU plurality — fall-back tiebreak by canonical_path SKU count
  5. Alphabetical — final deterministic tiebreak

Output: retail_mapper/v2/path_quality_clusters.csv

Read-only.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SRC = V2 / "full_corpus_audit.csv"
OUT = V2 / "path_quality_clusters.csv"

sys.path.insert(0, str(V2))
from path_canonical_overrides import (  # noqa: E402
    MANUAL_LEAF_CANONICAL,
    REPEATED_WORD_ALLOWLIST,
)

csv.field_size_limit(sys.maxsize)

DEEP_THRESHOLD = 8  # Raised: Option B intentionally chains tier modifiers,
# which legitimately produces 6-7 segment paths (e.g. Dairy > Cheese >
# Mozzarella > Low Moisture > Part Skim > Shredded > Organic). Anything
# >= 8 is suspicious.
WORD_RX = re.compile(r"[A-Za-z0-9&'-]+")
# Connector words ignored when computing the sorted-token signature.
# Without this filter, "Rice and Chicken" / "Chicken and Rice" cluster with
# garbage tokens, and the alpha tiebreak produces nonsense like "and Kale
# Spinach". Connectors are kept in the displayed leaf, just not in the sig.
CONNECTORS = {"and", "or", "the", "of", "in", "with", "&"}


def split_path(p: str) -> list[str]:
    return [s.strip() for s in p.split(">") if s.strip()]


def tokens(seg: str) -> list[str]:
    return [w.lower() for w in WORD_RX.findall(seg)]


def signature(seg: str) -> str:
    """Sorted-token signature. Drops punctuation, lowercases, drops connectors.
    Two leaves with the same signature differ only in word-order (or case).
    """
    return " ".join(sorted(t for t in tokens(seg)
                           if t.lower() not in CONNECTORS))


def has_repeated_word(seg: str) -> bool:
    if seg in REPEATED_WORD_ALLOWLIST:
        return False
    toks = tokens(seg)
    seen: set[str] = set()
    for t in toks:
        if len(t) <= 2:
            continue
        if t in seen:
            return True
        seen.add(t)
    return False


def fndds_word_match_natural(canonical_words: set[str], fndds_desc: str) -> str | None:
    """If FNDDS desc contains all the cluster words, return the desc-implied
    natural word-order. FNDDS uses comma-inverted forms ('Steak, sirloin' →
    real order 'Sirloin Steak'); we re-invert by reading the post-comma chunks
    first, then the pre-comma noun. For comma-less descs we read left-to-right.
    """
    if not fndds_desc:
        return None
    desc_words_all = tokens(fndds_desc)
    if not canonical_words.issubset(set(desc_words_all)):
        return None
    # Split on comma to identify inversion segments.
    if "," in fndds_desc:
        parts = [p.strip() for p in fndds_desc.split(",") if p.strip()]
        # Read in reverse: post-comma modifiers first, then the head noun.
        reordered: list[str] = []
        for part in reversed(parts):
            for w in tokens(part):
                if w in canonical_words and w not in reordered:
                    reordered.append(w)
        if set(reordered) >= canonical_words:
            return " ".join(reordered)
    # No comma: walk left to right.
    first_idx: dict[str, int] = {}
    for i, w in enumerate(desc_words_all):
        if w in canonical_words and w not in first_idx:
            first_idx[w] = i
    return " ".join(sorted(first_idx, key=lambda w: first_idx[w]))


def titlecase_from_signature(words_in_order: list[str]) -> str:
    """Render a list of lowercase words back to Title Case for display."""
    return " ".join(w.capitalize() if w not in {"&", "and", "or"} else w
                    for w in words_in_order)


def main() -> None:
    print(f"  reading {SRC.name}")
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}")

    # Per-leaf-signature: parent_path -> sig -> { variant_form: count }
    # plus FNDDS desc evidence and sample titles per variant.
    cluster_counts: dict[tuple[str, str], Counter] = defaultdict(Counter)
    cluster_fndds: dict[tuple[str, str], Counter] = defaultdict(Counter)
    cluster_titles: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    # Per (parent, sig) -> Counter of (variant_leaf_string -> # titles where
    # that exact leaf phrase appears as a substring, case-insensitive).
    cluster_title_match: dict[tuple[str, str], Counter] = defaultdict(Counter)

    comma_paths: dict[str, int] = defaultdict(int)
    repeat_paths: dict[str, int] = defaultdict(int)
    deep_paths: dict[str, int] = defaultdict(int)
    distinct_paths: set[str] = set()

    n = 0
    with SRC.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cp = (row.get("canonical_path") or "").strip()
            if not cp:
                continue
            n += 1
            distinct_paths.add(cp)
            segs = split_path(cp)
            if not segs:
                continue
            leaf = segs[-1]
            parent = " > ".join(segs[:-1])
            sig = signature(leaf)
            cluster_counts[(parent, sig)][leaf] += 1
            fdesc = (row.get("fndds_desc") or "").strip()
            if fdesc:
                cluster_fndds[(parent, sig)][fdesc] += 1
            title = (row.get("title") or "").strip()
            if title and len(cluster_titles[(parent, sig)][leaf]) < 5:
                cluster_titles[(parent, sig)][leaf].append(title[:80])
            # Title-plurality signal: scan title for the cluster words; if all
            # present, record the in-title order as a candidate canonical.
            # Title support — does the title contain the leaf string verbatim
            # (case-insensitive)? If yes, count this as a vote for that
            # specific leaf form (preserves connectors and casing).
            if title:
                tlow = title.lower()
                if leaf.lower() in tlow:
                    cluster_title_match[(parent, sig)][leaf] += 1
            # Per-segment issue tagging
            for s in segs:
                if "," in s:
                    comma_paths[cp] += 1
                if has_repeated_word(s):
                    repeat_paths[cp] += 1
            if len(segs) >= DEEP_THRESHOLD:
                deep_paths[cp] += 1

    print(f"  scanned {n:,} SKUs, {len(distinct_paths):,} distinct paths")

    # Pick suggested canonical per cluster
    rows_out: list[dict] = []

    n_word_swap = 0
    n_manual = 0
    n_fndds = 0
    n_title = 0
    n_sku = 0
    n_alpha = 0

    for (parent, sig), variants in cluster_counts.items():
        if len(variants) < 2:
            continue  # not a duplicate cluster
        n_word_swap += 1
        cluster_words = set(sig.split())
        suggested = None
        rule = ""

        # 1. Manual override
        if sig in MANUAL_LEAF_CANONICAL:
            suggested = MANUAL_LEAF_CANONICAL[sig]
            rule = "manual"
            n_manual += 1
        # 2. SKU plurality (clear leader, not tied)
        if not suggested:
            counts_sorted = variants.most_common()
            top_form, top_count = counts_sorted[0]
            second_count = counts_sorted[1][1] if len(counts_sorted) > 1 else 0
            if top_count > second_count:
                suggested = top_form
                rule = "sku"
                n_sku += 1
        # 3. Title-plurality (when SKU was tied) — pick the variant whose
        #    leaf string appears literally in the most product titles.
        if not suggested:
            tm = cluster_title_match[(parent, sig)]
            if tm:
                best_form, best_count = tm.most_common(1)[0]
                second = tm.most_common(2)[1][1] if len(tm) > 1 else 0
                if best_count > second:
                    suggested = best_form
                    rule = "title"
                    n_title += 1
        # 4. FNDDS anchor (only if SKU+title both tied/empty). FNDDS desc
        #    uses comma-inverted forms ("Steak, Sirloin") so we treat the
        #    chunk-after-first-comma as a leading modifier when present.
        #    Guard: only accept if the FNDDS-implied order matches one of
        #    the existing variants — otherwise we'd drop connectors.
        if not suggested:
            existing_sigs_to_form: dict[tuple, str] = {}
            for v in variants:
                existing_sigs_to_form[tuple(t for t in tokens(v) if t not in CONNECTORS)] = v
            for fdesc, _ in cluster_fndds[(parent, sig)].most_common():
                ordered = fndds_word_match_natural(cluster_words, fdesc)
                if ordered:
                    key = tuple(ordered.split())
                    if key in existing_sigs_to_form:
                        suggested = existing_sigs_to_form[key]
                        rule = "fndds"
                        n_fndds += 1
                        break
        # 5. Alpha last-resort. Pick the alphabetically-first existing variant
        #    string (case-insensitive). This preserves connectors and casing,
        #    unlike rebuilding from the signature.
        if not suggested:
            suggested = sorted(variants, key=str.lower)[0]
            rule = "alpha"
            n_alpha += 1

        total_skus = sum(variants.values())
        variants_str = " | ".join(f"{v} ({c})" for v, c in variants.most_common())
        fndds_evidence = " | ".join(
            f"{d} ({c})" for d, c in cluster_fndds[(parent, sig)].most_common(3)
        )
        sample_titles = " || ".join(
            t for v in variants for t in cluster_titles[(parent, sig)].get(v, [])[:1]
        )[:300]
        rows_out.append({
            "issue_type": "word_order_swap",
            "parent_path": parent,
            "variant_count": len(variants),
            "total_skus": total_skus,
            "variants_with_counts": variants_str,
            "fndds_desc_evidence": fndds_evidence,
            "sample_titles": sample_titles,
            "suggested_canonical": suggested,
            "resolution_rule": rule,
        })

    # Add comma-leaf and repeat-leaf and deep-path rows
    for cp, count in comma_paths.items():
        rows_out.append({
            "issue_type": "comma_leaf",
            "parent_path": cp,
            "variant_count": 1,
            "total_skus": count,
            "variants_with_counts": cp,
            "fndds_desc_evidence": "",
            "sample_titles": "",
            "suggested_canonical": "",
            "resolution_rule": "manual_required",
        })
    for cp, count in repeat_paths.items():
        rows_out.append({
            "issue_type": "repeated_word_leaf",
            "parent_path": cp,
            "variant_count": 1,
            "total_skus": count,
            "variants_with_counts": cp,
            "fndds_desc_evidence": "",
            "sample_titles": "",
            "suggested_canonical": "",
            "resolution_rule": "manual_required",
        })
    for cp, count in deep_paths.items():
        rows_out.append({
            "issue_type": "deep_path",
            "parent_path": cp,
            "variant_count": 1,
            "total_skus": count,
            "variants_with_counts": cp,
            "fndds_desc_evidence": "",
            "sample_titles": "",
            "suggested_canonical": "",
            "resolution_rule": "manual_required",
        })

    rows_out.sort(key=lambda r: (
        {"word_order_swap": 0, "comma_leaf": 1, "repeated_word_leaf": 2, "deep_path": 3}[r["issue_type"]],
        -r["total_skus"],
    ))

    cols = ["issue_type", "parent_path", "variant_count", "total_skus",
            "variants_with_counts", "fndds_desc_evidence", "sample_titles",
            "suggested_canonical", "resolution_rule"]
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows_out)

    print(f"  wrote {OUT.name} ({len(rows_out):,} rows)")
    print(f"  issues:")
    print(f"    word-order swap clusters: {n_word_swap:,}")
    print(f"      resolved by manual:  {n_manual:,}")
    print(f"      resolved by fndds:   {n_fndds:,}")
    print(f"      resolved by title:   {n_title:,}")
    print(f"      resolved by sku:     {n_sku:,}")
    print(f"      resolved by alpha:   {n_alpha:,}")
    print(f"    comma-leaf paths:         {len(comma_paths):,}")
    print(f"    repeated-word leaves:     {len(repeat_paths):,}")
    print(f"    deep paths (≥{DEEP_THRESHOLD}):       {len(deep_paths):,}")


if __name__ == "__main__":
    main()
