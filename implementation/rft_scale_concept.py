"""
RFT scale run — concept-based router on full product corpus.

Three passes:
  1. Brand discovery — collect frequent tokens not in food vocab → brand registry
  2. Concept routing — route every product, write per-source codes (own + inherited)
  3. Canonical-surface audit — same router applied to the curated bridge file

Outputs (under implementation/output/rft_concept/):
  brand_registry.csv             confirmed brand vocabulary
  product_routes.csv.gz          one row per product, full traceability
  needs_new_concept_inventory.csv  gap signatures ranked by product count
  concept_population.csv         products per concept
  canonical_audit.csv            18k canonical rows agree/disagree/gap
  summary.json                   headline numbers
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rft import (
    ROOT, OUT, SURFACE,
    BRAND_FOOD_ALIASES, GLOBAL_NOISE, _singular,
    MODIFIER_TOKENS, UNITS, CURATED_CARRIERS, FORM_WORDS,
    VERBOSITY, RETAIL_ATTRS, RETAIL_ATTRS_NONROUTING, PROTECTED_HEADS,
    tokens as rft_tokens,
)
from rft_concept import (
    build_concept_index, build_token_to_concepts, route,
    concept_tokens_from_text, CATEGORY_PREFIXES,
)
import rft_concept as rftc

csv.field_size_limit(sys.maxsize)

OUT_C = OUT / "rft_concept"
OUT_C.mkdir(parents=True, exist_ok=True)
PROD_MAP = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.csv"

WORD = re.compile(r"[a-z][a-z0-9'%-]*")
BRAND_FREQ_THRESHOLD = 5


def strip_known_brand_columns(desc: str, brand_owner: str, brand_name: str) -> str:
    out = desc.lower()
    for b in (brand_owner or "", brand_name or ""):
        b = b.lower().strip()
        if b and b in out:
            out = out.replace(b, " ")
    return re.sub(r"\s+", " ", out).strip()


def strip_brand_registry(desc: str, registry: set[str]) -> str:
    parts = desc.split()
    kept = [p for p in parts
            if _singular(p.lower().strip(",.")) not in registry]
    return " ".join(kept)


def apply_brand_food_aliases(desc: str, brand_owner: str,
                             brand_name: str) -> tuple[str, list[str]]:
    haystack = " ".join(s for s in (desc, brand_owner, brand_name) if s).lower()
    additions = []
    for key, food in BRAND_FOOD_ALIASES.items():
        if key in haystack:
            additions.append(food)
    if additions:
        desc = desc + " " + " ".join(additions)
    return desc, additions


def apply_category_route_hints(desc: str, category: str) -> tuple[str, list[str]]:
    """Append conservative category-derived routing facts.

    These are not identity nouns. They are state/form hints that retail
    descriptions often omit but branded_food_category supplies reliably.
    """
    category_norm = (category or "").lower()
    desc_norm = desc.lower()
    additions: list[str] = []
    if "canned" in category_norm and "canned" not in desc_norm:
        additions.append("canned")
    if "frozen" in category_norm and "frozen" not in desc_norm:
        additions.append("frozen")
    if additions:
        desc = desc + " " + " ".join(additions)
    return desc, additions


# ---------------------------------------------------------------------------
# Pass 1: brand discovery
# ---------------------------------------------------------------------------

def pass1_brand_discovery(concepts, token_idx, food_vocab) -> tuple[set[str], Counter, Counter]:
    print("\n[Pass 1] Brand discovery over 462k products…", flush=True)
    t0 = time.time()
    brand_freq: Counter = Counter()
    authoritative: Counter = Counter()
    n = 0
    with PROD_MAP.open(encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            desc = (r.get("product_description") or "").strip()
            if not desc:
                continue
            owner = r.get("brand_owner") or ""
            name = r.get("brand_name") or ""
            for b in (owner, name):
                for t in rft_tokens(b):
                    authoritative[t] += 1
            cleaned = strip_known_brand_columns(desc, owner, name)
            # Tokens that aren't in any food vocab are brand candidates
            for t in rft_tokens(cleaned):
                if t in food_vocab or len(t) <= 1 or t.isdigit():
                    continue
                brand_freq[t] += 1
            n += 1
            if n % 50000 == 0:
                print(f"  {n:,} scanned  ({time.time()-t0:.1f}s)", flush=True)
    print(f"  {n:,} products scanned in {time.time()-t0:.1f}s")

    def is_safe_brand(t: str) -> bool:
        if not t or len(t) <= 1 or t.isdigit():
            return False
        if t in food_vocab:
            return False
        return True

    confirmed = set()
    for t in authoritative:
        if is_safe_brand(t):
            confirmed.add(t)
    for t, c in brand_freq.items():
        if c >= BRAND_FREQ_THRESHOLD and is_safe_brand(t):
            confirmed.add(t)
    print(f"  brand registry: {len(confirmed):,} tokens confirmed")
    return confirmed, brand_freq, authoritative


# ---------------------------------------------------------------------------
# Pass 2: concept routing on all products
# ---------------------------------------------------------------------------

def pass2_route_products(concepts, token_idx, brand_registry):
    print("\n[Pass 2] Routing 462k products via concept router…", flush=True)
    t0 = time.time()
    # Cache: route once per unique surface concept token-set.
    # 462k products → ~50k unique concepts after brand strip; ~9× speedup.
    cache: dict = {}

    def route_cached(stripped: str):
        surf = concept_tokens_from_text(stripped, brand_registry)
        if surf in cache:
            return cache[surf]
        res = route(stripped, concepts, token_idx, brand_registry)
        cache[surf] = res
        return res

    routes_path = OUT_C / "product_routes.csv.gz"
    tmp_csv_path = routes_path.with_name(routes_path.name.removesuffix(".gz") + ".tmp")
    tmp_routes_path = routes_path.with_suffix(routes_path.suffix + ".tmp")
    f_out = tmp_csv_path.open("w", newline="")
    writer = csv.writer(f_out)
    writer.writerow([
        "gtin_upc", "fdc_id",
        "product_description", "cleaned_description",
        "verdict",
        "surface_concept", "matched_concept", "canonical_name",
        "shared", "missing", "extra",
        "brand_food_aliases_applied",
        "composite_pieces", "composite_secondary",
        "sr28_code", "sr28_desc", "sr28_level", "sr28_inherited_from",
        "fndds_code", "fndds_desc", "fndds_level", "fndds_inherited_from",
        "esha_code", "esha_desc", "esha_level", "esha_inherited_from",
        "old_esha_code", "old_esha_description", "old_score",
    ])

    verdict_total: Counter = Counter()
    needs_sigs: Counter = Counter()
    needs_examples: dict = defaultdict(list)
    concept_pop: Counter = Counter()
    n = 0

    with PROD_MAP.open(encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            desc = (r.get("product_description") or "").strip()
            if not desc:
                continue
            owner = r.get("brand_owner") or ""
            name = r.get("brand_name") or ""
            augmented, aliases = apply_brand_food_aliases(desc, owner, name)
            augmented, category_hints = apply_category_route_hints(
                augmented, r.get("branded_food_category") or "")
            cleaned = strip_known_brand_columns(augmented, owner, name)
            stripped = strip_brand_registry(cleaned, brand_registry)

            res = route_cached(stripped)
            v = res["verdict"]
            verdict_total[v] += 1

            c = res.get("concept")
            bt = res.get("backtracked") or {}
            sr = bt.get("sr28") or {}
            fn = bt.get("fndds") or {}
            es = bt.get("esha") or {}

            if c:
                concept_pop[tuple(sorted(c.concept_id))] += 1

            if v in ("NEEDS_NEW_CONCEPT", "NO_MATCH"):
                surf = res.get("surface_concept") or frozenset()
                idents = tuple(sorted(t for t in surf if t in rftc._IDENTITY_TOKENS))
                if idents:
                    needs_sigs[idents] += 1
                    if len(needs_examples[idents]) < 3:
                        needs_examples[idents].append(desc)

            comp = res.get("composite") or None
            comp_pieces = (" | ".join(comp.get("pieces", []))
                           if comp else "")
            comp_secondary = (
                " | ".join(s.get("canonical", "")
                           for s in comp.get("secondary", []))
                if comp else "")
            writer.writerow([
                r.get("gtin_upc",""), r.get("fdc_id",""),
                desc, stripped,
                v,
                "|".join(sorted(res.get("surface_concept") or [])),
                "|".join(sorted(c.concept_id)) if c else "",
                c.canonical_name if c else "",
                "|".join(sorted(res.get("shared") or [])),
                "|".join(sorted(res.get("missing") or [])),
                "|".join(sorted(res.get("extra") or [])),
                " | ".join(aliases + category_hints),
                comp_pieces, comp_secondary,
                sr.get("code",""), sr.get("desc",""),
                sr.get("level",""),
                "|".join(sr.get("inherited_from") or []) if sr.get("inherited_from") else "",
                fn.get("code",""), fn.get("desc",""),
                fn.get("level",""),
                "|".join(fn.get("inherited_from") or []) if fn.get("inherited_from") else "",
                es.get("code",""), es.get("desc",""),
                es.get("level",""),
                "|".join(es.get("inherited_from") or []) if es.get("inherited_from") else "",
                r.get("best_esha_code",""),
                (r.get("best_esha_description") or "").strip().lower(),
                r.get("score_num",""),
            ])
            n += 1
            if n % 50000 == 0:
                print(f"  {n:,} routed  ({time.time()-t0:.1f}s)", flush=True)

    f_out.close()
    with tmp_routes_path.open("wb") as fout:
        subprocess.run(["gzip", "-c", str(tmp_csv_path)], stdout=fout, check=True)
    with gzip.open(tmp_routes_path, "rt", encoding="utf-8", errors="replace") as check:
        for _ in check:
            pass
    tmp_routes_path.replace(routes_path)
    tmp_csv_path.unlink(missing_ok=True)
    print(f"  {n:,} products routed in {time.time()-t0:.1f}s")
    return {
        "n": n,
        "verdict_total": verdict_total,
        "needs_sigs": needs_sigs,
        "needs_examples": needs_examples,
        "concept_pop": concept_pop,
        "routes_path": routes_path,
    }


# ---------------------------------------------------------------------------
# Pass 3: canonical surface audit
# ---------------------------------------------------------------------------

def pass3_audit(concepts, token_idx, brand_registry):
    print("\n[Pass 3] Auditing canonical_surface…", flush=True)
    t0 = time.time()
    audit_path = OUT_C / "canonical_audit.csv"
    audit = Counter()
    n = 0
    with SURFACE.open(encoding="utf-8", errors="replace") as fin, \
         audit_path.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        w = csv.writer(fout)
        w.writerow([
            "canonical_surface", "current_esha", "current_desc",
            "rft_verdict", "rft_concept", "rft_canonical_name",
            "rft_sr28_code", "rft_fndds_code", "rft_esha_code",
            "esha_audit",
        ])
        for r in reader:
            surf = (r.get("canonical_surface") or "").strip().lower()
            if not surf:
                continue
            stripped = strip_brand_registry(surf, brand_registry)
            res = route(stripped, concepts, token_idx, brand_registry)
            v = res["verdict"]
            c = res.get("concept")
            bt = res.get("backtracked") or {}
            sr_c = (bt.get("sr28") or {}).get("code","")
            fn_c = (bt.get("fndds") or {}).get("code","")
            es_c = (bt.get("esha") or {}).get("code","")
            cur_esha = (r.get("esha_code") or "").strip()
            cur_desc = (r.get("esha_description") or "").strip().lower()
            if cur_esha and es_c:
                a = "AGREE" if cur_esha == es_c else "DISAGREE"
            elif cur_esha:
                a = "ORIG_ONLY"
            elif es_c:
                a = "RFT_FILL"
            else:
                a = "BOTH_EMPTY"
            audit[a] += 1
            w.writerow([
                surf, cur_esha, cur_desc,
                v,
                "|".join(sorted(c.concept_id)) if c else "",
                c.canonical_name if c else "",
                sr_c, fn_c, es_c,
                a,
            ])
            n += 1
    print(f"  {n:,} canonical surfaces audited in {time.time()-t0:.1f}s")
    return n, audit


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Building concept index…")
    concepts = build_concept_index()
    token_idx = build_token_to_concepts(concepts)
    n_3way = sum(1 for c in concepts.values() if c.n_sources == 3)
    n_2way = sum(1 for c in concepts.values() if c.n_sources == 2)
    print(f"  {len(concepts):,} concepts  3-source={n_3way:,}  "
          f"2-source={n_2way:,}")

    # Food vocab for brand discovery (anything that's nutrition language)
    known_concept_tokens = set()
    for cid in concepts:
        known_concept_tokens |= cid
    food_vocab = (known_concept_tokens
                  | rftc._IDENTITY_TOKENS
                  | GLOBAL_NOISE | VERBOSITY | UNITS
                  | CURATED_CARRIERS | RETAIL_ATTRS | PROTECTED_HEADS
                  | FORM_WORDS | MODIFIER_TOKENS | CATEGORY_PREFIXES
                  | RETAIL_ATTRS_NONROUTING)

    # Pass 1
    confirmed, brand_freq, auth = pass1_brand_discovery(
        concepts, token_idx, food_vocab)
    brand_path = OUT_C / "brand_registry.csv"
    with brand_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["token", "discovered_freq", "authoritative_count", "in_registry"])
        all_t = set(brand_freq) | set(auth)
        rows = sorted(all_t, key=lambda t: -(brand_freq[t] + auth[t]))
        for t in rows:
            w.writerow([t, brand_freq[t], auth[t], "Y" if t in confirmed else ""])

    # Pass 2
    p2 = pass2_route_products(concepts, token_idx, confirmed)

    # Inventory
    inv_path = OUT_C / "needs_new_concept_inventory.csv"
    with inv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["identity_tokens", "n_products",
                    "example_1", "example_2", "example_3"])
        for idents, n in p2["needs_sigs"].most_common():
            ex = p2["needs_examples"][idents]
            w.writerow(["|".join(idents), n] + ex + [""] * (3 - len(ex)))

    # Concept population
    pop_path = OUT_C / "concept_population.csv"
    with pop_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["concept_tokens", "canonical_name", "n_products",
                    "n_sources", "sr28_code", "fndds_code", "esha_code"])
        for cid, n in p2["concept_pop"].most_common():
            cs = frozenset(cid)
            c = concepts.get(cs)
            if not c:
                continue
            w.writerow([
                "|".join(cid), c.canonical_name, n, c.n_sources,
                (c.sources.get("sr28") or [("","")])[0][0],
                (c.sources.get("fndds") or [("","")])[0][0],
                (c.sources.get("esha") or [("","")])[0][0],
            ])

    # Pass 3
    n_canon, audit = pass3_audit(concepts, token_idx, confirmed)

    # Summary
    summary = {
        "n_products": p2["n"],
        "n_canonical": n_canon,
        "n_concepts": len(concepts),
        "n_brand_tokens": len(confirmed),
        "verdict_mix": dict(p2["verdict_total"]),
        "canonical_audit": dict(audit),
        "n_distinct_gap_identities": len(p2["needs_sigs"]),
        "top_15_gaps": [
            {"identity": "|".join(idents), "n": n,
             "examples": p2["needs_examples"][idents]}
            for idents, n in p2["needs_sigs"].most_common(15)
        ],
        "top_15_concepts": [
            {"concept": "|".join(cid), "canonical": concepts[frozenset(cid)].canonical_name,
             "n_products": n, "n_sources": concepts[frozenset(cid)].n_sources}
            for cid, n in p2["concept_pop"].most_common(15)
            if frozenset(cid) in concepts
        ],
    }
    (OUT_C / "summary.json").write_text(json.dumps(summary, indent=2))

    # Headline
    n = p2["n"]
    print(f"\n{'='*70}\nHEADLINE  ({n:,} products)\n{'='*70}")
    print(f"\nVerdict mix:")
    for v, c in p2["verdict_total"].most_common():
        print(f"  {v:20s} {c:>8,}  ({100*c/n:5.1f}%)")
    print(f"\nCanonical surface audit (esha) — {n_canon:,} rows:")
    for k, c in audit.most_common():
        print(f"  {k:14s} {c:>6,}")
    print(f"\nTop 12 NEEDS_NEW gaps (by product count):")
    for idents, c in p2["needs_sigs"].most_common(12):
        ex = p2["needs_examples"][idents][0]
        print(f"  {c:>6,}  identity={list(idents)!s:35s}  ex: {ex[:60]}")
    print(f"\nTop 12 most-populated concepts:")
    for cid, c in p2["concept_pop"].most_common(12):
        cs = frozenset(cid)
        if cs not in concepts:
            continue
        cn = concepts[cs]
        print(f"  {c:>6,}  src={cn.n_sources}  {cn.canonical_name[:55]}  facets={list(cid)[:5]}")
    print(f"\nFiles in {OUT_C.relative_to(ROOT)}/:")
    for p in OUT_C.iterdir():
        print(f"  {p.name}")


if __name__ == "__main__":
    main()
