"""
RFT scale run — three-pass corpus router.

Pass 1  PRODUCTS — brand discovery
        Stream all 462k products. Count tokens classified as brand_candidates.
        Seed registry from authoritative brand_owner / brand_name columns.

Pass 2  PRODUCTS — routing with brand registry
        Re-stream products. Pre-strip brand-registry tokens from the input
        before routing. Write full route records, aggregate gap inventory
        and leaf population.

Pass 3  CANONICAL_SURFACE — audit
        Route the 18k curated surfaces through the same taxonomy. Compare
        each row's RFT verdict + ESHA against the curated esha_code.
        Output: agree / disagree / rft_only / curated_only.

Outputs in implementation/output/rft_v2/scale/:
  brand_registry.csv               Confirmed brand vocabulary (ranked)
  full_corpus_routes.csv.gz        One row per product with full traceability
  needs_new_leaf_inventory.csv     Ranked unmet (head, key_facets) needs
  leaf_population.csv              Products + surfaces per leaf — "flavors of X"
  head_population.csv              Products per identity head
  canonical_audit.csv              Per-row audit of canonical_surface
  summary.json                     Headline numbers
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rft import (
    ROOT, OUT, SURFACE,
    load_rows, detect_carriers, build_leaves, build_facet_users,
    route, parse_surface,
    PROTECTED_HEADS, RETAIL_ATTRS, RETAIL_ATTRS_NONROUTING,
    GLOBAL_NOISE, _singular,
    MODIFIER_TOKENS, UNITS, CURATED_CARRIERS, FORM_WORDS,
    VERBOSITY, BRAND_FOOD_ALIASES,
)

csv.field_size_limit(sys.maxsize)

OUT_SCALE = OUT / "scale"
OUT_SCALE.mkdir(parents=True, exist_ok=True)

PROD_MAP_CLEAN = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.vIdentity.csv"
PROD_MAP = PROD_MAP_CLEAN if PROD_MAP_CLEAN.exists() else ROOT / "implementation" / "output" / "product_to_best_esha_full_map.csv"

WORD = re.compile(r"[a-z][a-z0-9'%-]*")

# Threshold: a token must occur in ≥ this many distinct products to be
# confirmed as a brand by frequency. Authoritative tokens from brand_owner /
# brand_name columns are accepted regardless of frequency.
BRAND_FREQ_THRESHOLD = 5


def tokens(s: str) -> list[str]:
    return [_singular(t) for t in WORD.findall(s.lower())]


def strip_known_brand_columns(desc: str, brand_owner: str,
                              brand_name: str) -> str:
    """Remove brand_owner / brand_name strings from the description before
    Pass 1, so the discovery pass doesn't echo them back as candidates."""
    out = desc.lower()
    for b in (brand_owner or "", brand_name or ""):
        b = b.lower().strip()
        if not b:
            continue
        if b in out:
            out = out.replace(b, " ")
    return re.sub(r"\s+", " ", out).strip()


def strip_brand_registry(desc: str, registry: set[str]) -> str:
    """Remove individual brand tokens from a description string."""
    parts = desc.split()
    kept = [p for p in parts if _singular(p.lower().strip(",.")) not in registry]
    return " ".join(kept)


def apply_brand_food_aliases(desc: str, brand_owner: str,
                             brand_name: str) -> tuple[str, list[str]]:
    """If any BRAND_FOOD_ALIASES key matches anywhere in the description or
    brand columns, append its canonical food terms. Substring match,
    case-insensitive.

    Returns (augmented_desc, applied_aliases).
    """
    haystack = " ".join(s for s in (desc, brand_owner, brand_name) if s).lower()
    additions = []
    for key, food in BRAND_FOOD_ALIASES.items():
        if key in haystack:
            additions.append(food)
    if additions:
        desc = desc + " " + " ".join(additions)
    return desc, additions


def build_taxonomy():
    print("Loading parsed_unified.csv…", flush=True)
    rows = load_rows()
    print(f"  {len(rows):,} rows")
    print("Detecting carriers…", flush=True)
    carriers_info = detect_carriers(rows)
    carriers = set(carriers_info.keys())
    print(f"  {len(carriers)} carriers")
    print("Building leaves…", flush=True)
    leaves = build_leaves(rows, carriers)
    leaves_by_head: dict[str, list] = defaultdict(list)
    known_heads: set[str] = set()
    known_vocab: set[str] = set()
    for leaf in leaves.values():
        leaves_by_head[leaf.head].append(leaf)
        known_heads.add(leaf.head)
        known_vocab |= leaf.key_facets
    head_leaf_count = {h: len(v) for h, v in leaves_by_head.items()}
    facet_users = build_facet_users(leaves)
    print(f"  {len(leaves):,} leaves across {len(known_heads)} identity heads")
    print(f"  parent-child map: {len(facet_users):,} facet tokens with "
          "head ancestry")
    return (leaves, leaves_by_head, known_heads, known_vocab,
            head_leaf_count, facet_users)


# ---------------------------------------------------------------------------
# Pass 1: brand discovery
# ---------------------------------------------------------------------------

def pass1_brand_discovery(leaves, leaves_by_head, known_heads, known_vocab,
                           hcounts, facet_users) -> tuple[set[str], Counter, Counter]:
    print("\n[Pass 1] Brand discovery over 462k products…", flush=True)
    t0 = time.time()
    brand_freq: Counter = Counter()       # frequency of brand-candidate tokens
    authoritative_brands: Counter = Counter()  # tokens from brand_owner/brand_name
    n = 0
    with PROD_MAP.open(encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            desc = (r.get("product_description") or "").strip()
            if not desc:
                continue
            owner = r.get("brand_owner") or ""
            name = r.get("brand_name") or ""
            for b in (owner, name):
                for t in tokens(b):
                    authoritative_brands[t] += 1
            cleaned = strip_known_brand_columns(desc, owner, name)
            res = route(cleaned, leaves, leaves_by_head, known_heads,
                        known_vocab, hcounts, facet_users)
            for t in res.get("brand_candidates") or []:
                brand_freq[t] += 1
            n += 1
            if n % 50000 == 0:
                print(f"  {n:,} scanned  ({time.time()-t0:.1f}s)", flush=True)
    print(f"  {n:,} products scanned in {time.time()-t0:.1f}s")

    # Build the registry — but EXCLUDE any token that's recognized food
    # language: known heads, key facets, modifiers, units, carriers, retail
    # attrs, global noise. A brand is by definition a token that doesn't
    # appear as nutrition vocabulary anywhere.
    food_vocab = (known_heads | known_vocab | MODIFIER_TOKENS | UNITS
                  | CURATED_CARRIERS | RETAIL_ATTRS | GLOBAL_NOISE
                  | FORM_WORDS | PROTECTED_HEADS | VERBOSITY)

    def _is_brand_safe(t: str) -> bool:
        if not t or len(t) <= 1:
            return False
        if t in food_vocab:
            return False
        if t.isdigit():
            return False
        return True

    confirmed = set()
    for t in authoritative_brands:
        if _is_brand_safe(t):
            confirmed.add(t)
    for t, c in brand_freq.items():
        if c >= BRAND_FREQ_THRESHOLD and _is_brand_safe(t):
            confirmed.add(t)

    n_auth = sum(1 for t in authoritative_brands if _is_brand_safe(t))
    n_freq = sum(1 for t, c in brand_freq.items()
                 if c >= BRAND_FREQ_THRESHOLD and _is_brand_safe(t))
    print(f"  brand registry: {len(confirmed):,} tokens confirmed "
          f"({n_auth:,} authoritative-safe, {n_freq:,} frequency-safe)")
    rejected = [t for t, c in brand_freq.most_common(30)
                if not _is_brand_safe(t)]
    if rejected:
        print(f"  rejected from registry (food vocab): "
              f"{rejected[:10]}{'…' if len(rejected) > 10 else ''}")
    return confirmed, brand_freq, authoritative_brands


def write_brand_registry(confirmed: set[str], brand_freq: Counter,
                         authoritative: Counter):
    p = OUT_SCALE / "brand_registry.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["token", "discovered_freq", "authoritative_count",
                    "in_registry"])
        all_toks = set(brand_freq) | set(authoritative)
        rows = []
        for t in all_toks:
            rows.append([
                t,
                brand_freq.get(t, 0),
                authoritative.get(t, 0),
                "Y" if t in confirmed else "",
            ])
        rows.sort(key=lambda r: -(r[1] + r[2]))
        w.writerows(rows)
    return p


# ---------------------------------------------------------------------------
# Pass 2: route products with brand registry
# ---------------------------------------------------------------------------

def pass2_route_products(leaves, leaves_by_head, known_heads, known_vocab,
                          hcounts, facet_users, brand_registry: set[str]):
    print("\n[Pass 2] Routing 462k products with brand registry…", flush=True)
    t0 = time.time()

    routes_path = OUT_SCALE / "full_corpus_routes.csv.gz"
    f_out = gzip.open(routes_path, "wt", newline="")
    writer = csv.writer(f_out)
    writer.writerow([
        "gtin_upc", "fdc_id", "input_cleaned", "input_raw",
        "verdict", "head", "routing_tokens", "retail_attrs",
        "stripped_brands", "brand_candidates_remaining",
        "leaf_id", "leaf_canonical", "leaf_key_facets",
        "sr28_code", "sr28_desc",
        "fndds_code", "fndds_desc",
        "esha_code", "esha_desc",
        "missing_from_leaf", "leaf_extra_facets",
        "current_esha", "current_esha_desc", "current_score",
    ])

    verdict_total: Counter = Counter()
    needs_new_leaf_sigs: Counter = Counter()
    needs_new_leaf_examples: dict = defaultdict(list)
    leaf_pop: Counter = Counter()
    head_pop: Counter = Counter()
    n = 0
    with PROD_MAP.open(encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            desc = (r.get("product_description") or "").strip()
            if not desc:
                continue
            owner = r.get("brand_owner") or ""
            name = r.get("brand_name") or ""
            # Step A: brand→food alias expansion BEFORE stripping. If
            # "Crisco" → append "shortening" so the food signal survives
            # the subsequent brand strip.
            augmented, applied_aliases = apply_brand_food_aliases(desc, owner, name)
            cleaned = strip_known_brand_columns(augmented, owner, name)
            stripped = strip_brand_registry(cleaned, brand_registry)
            # Track which brands we removed
            cleaned_toks = set(tokens(cleaned))
            stripped_toks = set(tokens(stripped))
            removed_brands = sorted(cleaned_toks - stripped_toks)

            res = route(stripped, leaves, leaves_by_head, known_heads,
                        known_vocab, hcounts, facet_users)
            v = res["verdict"]
            verdict_total[v] += 1
            head_used = res["parsed"]["head"] or ""
            head_pop[head_used] += 1

            leaf = res.get("leaf")
            mm = res.get("match_meta") or {}
            psc = res.get("per_source_closest") or {}
            sr = psc.get("sr28") or {}
            fn = psc.get("fndds") or {}
            es = psc.get("esha") or {}

            if leaf:
                leaf_pop[leaf.leaf_id] += 1

            if v == "NEEDS_NEW_LEAF":
                rtoks = res["parsed"]["routing_tokens"]
                bc = set(res.get("brand_candidates") or [])
                sig_toks = sorted(t for t in rtoks
                                  if t not in bc and t in known_vocab)
                sig = (head_used, "|".join(sig_toks))
                needs_new_leaf_sigs[sig] += 1
                if len(needs_new_leaf_examples[sig]) < 3:
                    needs_new_leaf_examples[sig].append(desc)

            writer.writerow([
                r.get("gtin_upc", ""), r.get("fdc_id", ""),
                stripped, desc,
                v, head_used,
                "|".join(sorted(res["parsed"]["routing_tokens"])),
                "|".join(res["parsed"]["retail_attrs"]),
                "|".join(removed_brands),
                "|".join(res.get("brand_candidates") or []),
                leaf.leaf_id if leaf else "",
                leaf.canonical_name if leaf else "",
                "|".join(sorted(leaf.key_facets)) if leaf else "",
                sr.get("code", ""), sr.get("desc", ""),
                fn.get("code", ""), fn.get("desc", ""),
                es.get("code", ""), es.get("desc", ""),
                "|".join(sorted(mm.get("missing", []) or [])),
                "|".join(sorted(mm.get("leaf_extra", []) or [])),
                r.get("best_esha_code", ""),
                (r.get("best_esha_description") or "").strip().lower(),
                r.get("score_num", ""),
            ])

            n += 1
            if n % 50000 == 0:
                print(f"  {n:,} routed  ({time.time()-t0:.1f}s)", flush=True)
    f_out.close()
    print(f"  {n:,} products routed in {time.time()-t0:.1f}s")

    return {
        "n_products": n,
        "verdict_total": verdict_total,
        "needs_new_leaf_sigs": needs_new_leaf_sigs,
        "needs_new_leaf_examples": needs_new_leaf_examples,
        "leaf_pop": leaf_pop,
        "head_pop": head_pop,
        "routes_path": routes_path,
    }


# ---------------------------------------------------------------------------
# Pass 3: audit canonical_surface
# ---------------------------------------------------------------------------

def pass3_audit_canonical(leaves, leaves_by_head, known_heads, known_vocab,
                           hcounts, facet_users, brand_registry: set[str]):
    print("\n[Pass 3] Auditing canonical_surface (18k)…", flush=True)
    t0 = time.time()
    audit_path = OUT_SCALE / "canonical_audit.csv"
    f = audit_path.open("w", newline="")
    w = csv.writer(f)
    w.writerow([
        "surface", "current_esha", "current_desc",
        "rft_verdict", "rft_head",
        "rft_leaf_canonical", "rft_esha_code", "rft_esha_desc",
        "rft_sr28_code", "rft_fndds_code",
        "agreement", "missing_from_leaf",
    ])
    audit_counter = Counter()
    n = 0
    with SURFACE.open(encoding="utf-8", errors="replace") as f_in:
        for r in csv.DictReader(f_in):
            surf = (r.get("canonical_surface") or "").strip().lower()
            if not surf:
                continue
            stripped = strip_brand_registry(surf, brand_registry)
            res = route(stripped, leaves, leaves_by_head, known_heads,
                        known_vocab, hcounts, facet_users)
            cur_esha = (r.get("esha_code") or "").strip()
            cur_desc = (r.get("esha_description") or "").strip().lower()

            leaf = res.get("leaf")
            psc = res.get("per_source_closest") or {}
            es = psc.get("esha") or {}
            sr = psc.get("sr28") or {}
            fn = psc.get("fndds") or {}
            rft_esha = es.get("code", "")
            rft_desc = es.get("desc", "")

            # Agreement classification
            if cur_esha and rft_esha:
                if cur_esha == rft_esha:
                    agreement = "AGREE"
                else:
                    agreement = "DISAGREE"
            elif cur_esha and not rft_esha:
                agreement = "CURATED_ONLY"
            elif rft_esha and not cur_esha:
                agreement = "RFT_ONLY"
            else:
                agreement = "BOTH_EMPTY"
            audit_counter[agreement] += 1

            mm = res.get("match_meta") or {}
            w.writerow([
                surf, cur_esha, cur_desc,
                res["verdict"], res["parsed"]["head"] or "",
                leaf.canonical_name if leaf else "",
                rft_esha, rft_desc,
                sr.get("code", ""), fn.get("code", ""),
                agreement,
                "|".join(sorted(mm.get("missing", []) or [])),
            ])
            n += 1
    f.close()
    print(f"  {n:,} canonical surfaces audited in {time.time()-t0:.1f}s")
    return n, audit_counter, audit_path


# ---------------------------------------------------------------------------
# Aggregate writers
# ---------------------------------------------------------------------------

def write_inventory(needs_new_leaf_sigs: Counter,
                    needs_new_leaf_examples: dict, leaves):
    p = OUT_SCALE / "needs_new_leaf_inventory.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["head", "routing_signature", "n_products",
                    "example_1", "example_2", "example_3"])
        for (head, sig), n in needs_new_leaf_sigs.most_common():
            ex = needs_new_leaf_examples[(head, sig)]
            w.writerow([head, sig, n] + ex + [""] * (3 - len(ex)))
    return p


def write_leaf_population(leaf_pop: Counter, leaves):
    p = OUT_SCALE / "leaf_population.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["leaf_id", "head", "canonical_name", "key_facets",
                    "n_products",
                    "sr28_code", "fndds_code", "esha_code"])
        rows = []
        for lid, n in leaf_pop.items():
            leaf = leaves.get(lid)
            if not leaf:
                continue
            rows.append([
                lid, leaf.head, leaf.canonical_name,
                "|".join(sorted(leaf.key_facets)), n,
                leaf.sources["sr28"].code if "sr28" in leaf.sources else "",
                leaf.sources["fndds"].code if "fndds" in leaf.sources else "",
                leaf.sources["esha"].code if "esha" in leaf.sources else "",
            ])
        rows.sort(key=lambda r: -r[4])
        w.writerows(rows)
    return p


def write_head_population(head_pop: Counter):
    p = OUT_SCALE / "head_population.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["head", "n_products"])
        for h, n in head_pop.most_common():
            w.writerow([h, n])
    return p


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    (leaves, leaves_by_head, known_heads, known_vocab,
     hcounts, facet_users) = build_taxonomy()

    # Pass 1
    confirmed, brand_freq, authoritative = pass1_brand_discovery(
        leaves, leaves_by_head, known_heads, known_vocab, hcounts, facet_users)
    write_brand_registry(confirmed, brand_freq, authoritative)

    # Pass 2
    p2 = pass2_route_products(leaves, leaves_by_head, known_heads,
                              known_vocab, hcounts, facet_users, confirmed)
    write_inventory(p2["needs_new_leaf_sigs"],
                    p2["needs_new_leaf_examples"], leaves)
    write_leaf_population(p2["leaf_pop"], leaves)
    write_head_population(p2["head_pop"])

    # Pass 3
    n_canon, audit_counter, audit_path = pass3_audit_canonical(
        leaves, leaves_by_head, known_heads, known_vocab, hcounts,
        facet_users, confirmed)

    # Summary
    summary = {
        "n_products": p2["n_products"],
        "n_canonical_surfaces": n_canon,
        "n_brand_registry": len(confirmed),
        "verdict_mix_products": dict(p2["verdict_total"]),
        "canonical_audit": dict(audit_counter),
        "leaves_with_products": len(p2["leaf_pop"]),
        "n_distinct_needs_new_leaf": len(p2["needs_new_leaf_sigs"]),
        "top_15_needs_new_leaf": [
            {"head": h, "sig": s, "n": n,
             "examples": p2["needs_new_leaf_examples"][(h, s)]}
            for (h, s), n in p2["needs_new_leaf_sigs"].most_common(15)
        ],
        "top_15_populated_leaves": [
            {
                "leaf_id": lid,
                "canonical": leaves[lid].canonical_name,
                "head": leaves[lid].head,
                "n_products": p2["leaf_pop"][lid],
            }
            for lid, _ in p2["leaf_pop"].most_common(15) if lid in leaves
        ],
        "top_30_brands_by_freq": [
            (t, brand_freq.get(t, 0))
            for t, _ in brand_freq.most_common(30)
        ],
        "top_30_authoritative_brand_tokens": authoritative.most_common(30),
    }
    (OUT_SCALE / "summary.json").write_text(json.dumps(summary, indent=2))

    # Headlines
    print("\n" + "=" * 70)
    print("HEADLINE")
    print("=" * 70)
    n = p2["n_products"]
    print(f"\nPRODUCT VERDICT MIX  (out of {n:,}):")
    for v, c in p2["verdict_total"].most_common():
        print(f"  {v:20s} {c:>8,}  ({100*c/n:5.1f}%)")
    print(f"\nCANONICAL_SURFACE AUDIT  (out of {n_canon:,}):")
    for v, c in audit_counter.most_common():
        print(f"  {v:20s} {c:>8,}  ({100*c/n_canon:5.1f}%)")

    print(f"\nTOP 15 NEEDS_NEW_LEAF GAPS (sorted by product count):")
    for (h, s), c in p2["needs_new_leaf_sigs"].most_common(15):
        ex = p2["needs_new_leaf_examples"][(h, s)][0]
        print(f"  {c:>6,}  head={h!r:18s}  sig={s!r:30s}  ex: {ex[:50]}")

    print(f"\nTOP 15 POPULATED LEAVES (where products land):")
    for lid, c in p2["leaf_pop"].most_common(15):
        leaf = leaves.get(lid)
        if leaf:
            srcs = ",".join(s for s in ("sr28","fndds","esha")
                            if s in leaf.sources)
            print(f"  {c:>6,}  {leaf.canonical_name[:55]:55s}"
                  f"  head={leaf.head:14s}  src={srcs}")

    print(f"\nTOP 15 BRAND CANDIDATES (frequency-discovered):")
    for t, c in brand_freq.most_common(15):
        confirm = "✓" if t in confirmed else " "
        print(f"  {confirm}  {c:>6,}  {t}")

    print(f"\nFiles written to {OUT_SCALE.relative_to(ROOT)}/:")
    for p in OUT_SCALE.iterdir():
        print(f"  {p.name}")


if __name__ == "__main__":
    main()
