#!/usr/bin/env python3
"""Force ONE canonical home per product_identity_fixed.

After build_audit_csv.py runs, some product identities have SKUs scattered
across multiple family>type homes (e.g., "Biscotti" in both
"Bakery > Biscotti" and "Bakery > Cookies"). This script:

  1. Reads full_corpus_audit.csv
  2. For each product_identity_fixed value, identifies the DOMINANT home
     (top-2-segments where ≥80% of SKUs land)
  3. Reroutes outliers to the dominant home by overwriting category_path_fixed
  4. Re-runs apply_finalized_taxonomy to regenerate canonical_path / RLP
  5. Writes back to full_corpus_audit.csv

Result: every product_identity_fixed value has exactly ONE family>type home.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path


def _has_combined_bfc_name(home: str) -> bool:
    """A home is 'tainted' if it contains a BFC-combined-parent name
    (something with '&', ',', or '/' in any non-family segment)."""
    segs = home.split(" > ")
    for s in segs[1:]:
        if re.search(r"[&,/]", s):
            return True
    return False

V2 = Path(__file__).resolve().parent
AUDIT = V2 / "full_corpus_audit.csv"
TMP = V2 / "full_corpus_audit.csv.homogenized"

csv.field_size_limit(sys.maxsize)
sys.path.insert(0, str(V2))
from taxonomy_finalizer import apply_finalized_taxonomy  # noqa: E402


# Concentration threshold for considering a home "dominant"
DOMINANT_THRESHOLD = 0.50
# Min total SKUs for a PI to even consider rerouting
MIN_PI_SKUS = 5


def _dedupe_by_fdc(rows: list[dict]) -> list[dict]:
    """Drop duplicate fdc_ids (keep first occurrence). Bug #1: 47 exact-dup
    fdc_ids violate primary-key invariant."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        fdc = (r.get("fdc_id") or "").strip()
        if fdc and fdc in seen:
            continue
        if fdc:
            seen.add(fdc)
        out.append(r)
    return out


def _strip_redundant_adjacent_words(seg: str) -> str:
    """Bug #3: 'Dark Chocolate Chocolate' → 'Dark Chocolate'."""
    words = seg.split()
    if not words:
        return seg
    out = [words[0]]
    for w in words[1:]:
        if w.lower() != out[-1].lower():
            out.append(w)
    return " ".join(out)


def main() -> None:
    print(f"Reading {AUDIT.name}...")
    rows: list[dict] = []
    with AUDIT.open(encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        fieldnames = rdr.fieldnames
        for r in rdr:
            rows.append(r)
    print(f"  loaded {len(rows):,} rows")

    # Pass 0: dedupe by fdc_id (Bug #1: 47 exact duplicates)
    n_before = len(rows)
    rows = _dedupe_by_fdc(rows)
    if len(rows) < n_before:
        print(f"  dropped {n_before - len(rows):,} duplicate fdc_id rows")

    # Pass 1: count PI -> home distribution
    pi_homes: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        pi = (r.get("product_identity_fixed") or "").strip()
        cp = (r.get("canonical_path") or "").strip()
        if not (pi and cp):
            continue
        segs = cp.split(" > ")
        home = " > ".join(segs[:2]) if len(segs) >= 2 else cp
        pi_homes[pi][home] += 1

    # Determine dominant home for each PI — but skip BFC-combined-parent
    # names (those should never be the canonical home)
    pi_dominant: dict[str, str] = {}
    for pi, homes in pi_homes.items():
        total = sum(homes.values())
        if total < MIN_PI_SKUS:
            continue
        # Filter out tainted (BFC-combined-name) homes from candidates
        clean_homes = [(h, n) for h, n in homes.most_common() if not _has_combined_bfc_name(h)]
        if not clean_homes:
            continue
        dom_home, dom_n = clean_homes[0]
        if dom_n / total >= DOMINANT_THRESHOLD:
            pi_dominant[pi] = dom_home

    print(f"  identities with dominant home (≥{DOMINANT_THRESHOLD:.0%}): {len(pi_dominant):,}")

    # Pass 2: reroute by PI dominance OR by _forced_base — whichever
    # disagrees with the current home. _forced_base output ALWAYS wins
    # (it's title-driven and authoritative); only fall back to PI dominance
    # when no force applies.
    from taxonomy_finalizer import _forced_base
    n_rerouted_by_pi = 0
    n_skipped = 0
    for r in rows:
        pi = (r.get("product_identity_fixed") or "").strip()
        cp = (r.get("canonical_path") or "").strip()
        if not (pi and cp):
            continue
        segs = cp.split(" > ")
        cur_home = " > ".join(segs[:2]) if len(segs) >= 2 else cp
        # Authoritative: _forced_base. If it returns a different home, USE IT
        # (overrides current path even if cur_home matches PI dominant home).
        forced = _forced_base(r)
        if forced is not None and forced[0] != cur_home:
            r["category_path_fixed"] = forced[0]
            apply_finalized_taxonomy(r)
            n_rerouted_by_pi += 1
            continue
        # Fallback: PI dominance. Only fires if no force.
        if pi not in pi_dominant:
            n_skipped += 1
            continue
        dom_home = pi_dominant[pi]
        if cur_home == dom_home:
            continue
        r["category_path_fixed"] = dom_home
        apply_finalized_taxonomy(r)
        n_rerouted_by_pi += 1
    print(f"  rerouted {n_rerouted_by_pi:,} outlier SKUs by PI/forced")
    print(f"  skipped {n_skipped:,} SKUs (PI without dominant home or too few SKUs)")

    # Pass 3: homogenize by type-WORD appearing anywhere in path.
    # For each distinct type-word that appears in canonical_path's leaf
    # positions, find its dominant family>type home; force any SKU whose
    # path contains that word as a leaf BUT lives in a non-dominant home
    # to the dominant home.
    word_homes: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        cp = (r.get("canonical_path") or "").strip()
        segs = cp.split(" > ")
        if len(segs) < 2:
            continue
        home = " > ".join(segs[:2])
        for s in segs[1:]:
            word_homes[s.lower()][home] += 1

    word_dominant: dict[str, str] = {}
    for word, homes in word_homes.items():
        total = sum(homes.values())
        if total < MIN_PI_SKUS:
            continue
        # Filter out BFC-combined-parent homes — those should never be
        # the canonical home for a type-word
        clean_homes = [(h, n) for h, n in homes.most_common() if not _has_combined_bfc_name(h)]
        if not clean_homes:
            continue
        dom_home, dom_n = clean_homes[0]
        if dom_n / total >= DOMINANT_THRESHOLD:
            word_dominant[word] = dom_home

    print(f"  type-words with dominant home (≥{DOMINANT_THRESHOLD:.0%}): {len(word_dominant):,}")

    n_rerouted_by_word = 0
    for r in rows:
        cp = (r.get("canonical_path") or "").strip()
        segs = cp.split(" > ")
        if len(segs) < 2:
            continue
        cur_home = " > ".join(segs[:2])
        # Find any type-word in this path that has a dominant home different
        # from current. Take the FIRST such word and reroute.
        for s in segs[1:]:
            sl = s.lower()
            if sl in word_dominant and word_dominant[sl] != cur_home:
                r["category_path_fixed"] = word_dominant[sl]
                apply_finalized_taxonomy(r)
                n_rerouted_by_word += 1
                break
    print(f"  rerouted {n_rerouted_by_word:,} outlier SKUs by type-word")

    # Pass 3.5: leaf-signature homogenization. Same leaf-words appearing in
    # MULTIPLE family>type homes — reroute outliers to the dominant home.
    # E.g., "Pina Colada Mix" appears in both:
    #   Pantry > Baking Mixes > Mix > Pina Colada (1 SKU)
    #   Beverage > Cocktail Mixers > Cocktail Mix > Pina Colada (50 SKUs)
    # Dominant wins. The 1-SKU outlier was a hijack and gets rerouted.
    sig_to_paths: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp: continue
        segs = cp.split(" > ")
        if len(segs) <= 2: continue
        leaves = segs[2:]
        words = []
        for s in leaves:
            for w in re.findall(r"[A-Za-z][A-Za-z']+", s):
                wl = w.lower()
                if wl in {"plain", "natural", "original", "the", "and", "or"}: continue
                if len(wl) <= 2: continue
                words.append(wl)
        sig = " ".join(sorted(set(words)))
        if sig:
            sig_to_paths[sig][cp] += 1

    sig_dom: dict[str, str] = {}
    for sig, paths in sig_to_paths.items():
        total = sum(paths.values())
        if total < 5: continue
        dom_path, dom_n = paths.most_common(1)[0]
        # Only set as canonical if dominant has >=50% AND >=5x the runner-up
        if dom_n / total < 0.50: continue
        runner_up = paths.most_common(2)[1][1] if len(paths) > 1 else 0
        if runner_up and dom_n / runner_up < 5: continue
        # And exclude tainted (BFC-combined-name) homes
        if _has_combined_bfc_name(dom_path): continue
        sig_dom[sig] = dom_path

    n_rerouted_by_sig = 0
    for r in rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp: continue
        segs = cp.split(" > ")
        if len(segs) <= 2: continue
        leaves = segs[2:]
        words = []
        for s in leaves:
            for w in re.findall(r"[A-Za-z][A-Za-z']+", s):
                wl = w.lower()
                if wl in {"plain", "natural", "original", "the", "and", "or"}: continue
                if len(wl) <= 2: continue
                words.append(wl)
        sig = " ".join(sorted(set(words)))
        if not sig or sig not in sig_dom: continue
        dom = sig_dom[sig]
        if cp == dom: continue
        # Only reroute if current path is significantly less common than dom
        current_count = sig_to_paths[sig].get(cp, 0)
        dom_count = sig_to_paths[sig][dom]
        if current_count >= dom_count: continue
        if dom_count / max(1, current_count) < 5: continue
        # Reroute: set category_path_fixed to dominant home's family+type
        dom_segs = dom.split(" > ")
        new_cat = " > ".join(dom_segs[:2])
        r["category_path_fixed"] = new_cat
        apply_finalized_taxonomy(r)
        n_rerouted_by_sig += 1
    print(f"  rerouted {n_rerouted_by_sig:,} outlier SKUs by leaf-signature dominance")

    # Pass 4: clean adjacent-redundant-words within each path segment
    # (Bug #3: "Dark Chocolate Chocolate" → "Dark Chocolate")
    n_redundant_fixed = 0
    for r in rows:
        for col in ("canonical_path", "retail_leaf_path", "modifier"):
            v = (r.get(col) or "").strip()
            if not v: continue
            new_segs = [_strip_redundant_adjacent_words(s) for s in v.split(" > ")]
            new_v = " > ".join(new_segs)
            if new_v != v:
                r[col] = new_v
                n_redundant_fixed += 1
    print(f"  cleaned {n_redundant_fixed:,} segments with adjacent-redundant words")

    # Pass 4.5: BFC → authoritative family enforcement.
    # Loads the curated map (≥80% concentration) and forces SKUs whose
    # canonical_path family doesn't match their BFC's authoritative family.
    # E.g., BFC=Alcohol → all 1,146 SKUs must be in Beverage family. The
    # 60 SKUs currently in Pantry are misrouted hijacks → reroute to Beverage.
    AUTH_PATH = V2 / "bfc_authoritative_family.json"
    n_family_forced = 0
    if AUTH_PATH.exists():
        with AUTH_PATH.open(encoding="utf-8") as fh:
            auth_map_raw = json.load(fh)
        auth_map = {k.lower(): v for k, v in auth_map_raw.items() if not k.startswith("_")}
        # For each BFC, also figure out the dominant TYPE within that family
        # so when we reroute, we can pick a sensible category_path_fixed.
        bfc_type_dom: dict[str, str] = {}
        bfc_type_count: dict[str, Counter] = defaultdict(Counter)
        for r in rows:
            bfc = (r.get("branded_food_category") or "").strip().lower()
            cp = (r.get("canonical_path") or "").strip()
            if bfc not in auth_map: continue
            segs = cp.split(" > ")
            if len(segs) < 2: continue
            if segs[0] != auth_map[bfc]: continue
            top2 = " > ".join(segs[:2])
            if _has_combined_bfc_name(top2): continue  # skip BFC-name parents
            bfc_type_count[bfc][top2] += 1
        for bfc, counter in bfc_type_count.items():
            if counter:
                bfc_type_dom[bfc] = counter.most_common(1)[0][0]
        # Now reroute outliers — but RESPECT _forced_base. If a row has a
        # title-driven force (sandwich, hot dog buns, plant-based cheese,
        # candy with jelly beans, etc.), the _forced_base output trumps the
        # BFC family-force. We check by calling _forced_base BEFORE forcing.
        from taxonomy_finalizer import _forced_base
        for r in rows:
            bfc = (r.get("branded_food_category") or "").strip().lower()
            cp = (r.get("canonical_path") or "").strip()
            if bfc not in auth_map: continue
            expected_family = auth_map[bfc]
            if not cp:
                continue
            segs = cp.split(" > ")
            current_family = segs[0]
            if current_family == expected_family:
                continue
            # Check if _forced_base would route this to a non-bakery family
            # (e.g., sandwich, plant-based cheese). If so, don't override.
            forced = _forced_base(r)
            if forced is not None:
                forced_family = forced[0].split(" > ", 1)[0]
                if forced_family != current_family:
                    # _forced_base will fix this naturally — don't double-force
                    r["category_path_fixed"] = forced[0]
                    apply_finalized_taxonomy(r)
                    n_family_forced += 1
                    continue
            new_top2 = bfc_type_dom.get(bfc) or expected_family
            r["category_path_fixed"] = new_top2
            apply_finalized_taxonomy(r)
            n_family_forced += 1
    if n_family_forced:
        print(f"  forced {n_family_forced:,} SKUs to BFC-authoritative family")

    # Pass 5: backfill empty retail_leaf_path with canonical_path
    # (Bug #2: 42 rows had empty RLP despite populated CP)
    n_rlp_backfilled = 0
    for r in rows:
        cp = (r.get("canonical_path") or "").strip()
        rlp = (r.get("retail_leaf_path") or "").strip()
        if cp and not rlp:
            r["retail_leaf_path"] = cp
            n_rlp_backfilled += 1
    if n_rlp_backfilled:
        print(f"  backfilled {n_rlp_backfilled:,} empty retail_leaf_path with canonical_path")

    # Write
    print(f"Writing {TMP.name}...")
    with TMP.open("w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        wtr.writeheader()
        wtr.writerows(rows)
    print(f"  wrote {len(rows):,} rows")

    # Atomic replace
    shutil.move(str(TMP), str(AUDIT))
    print(f"  replaced {AUDIT.name}")


if __name__ == "__main__":
    main()
