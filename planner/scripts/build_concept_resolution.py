#!/usr/bin/env python3
"""For every recipe-side concept_key, decide which priced concept_key to use.

Resolution tiers (first hit wins):
  1. exact (canonical_path | modifier | htc_form) match in concept_index
  2. drop modifier — same canonical_path + htc_form, any modifier in priced
  3. walk up canonical_path one segment at a time, keep htc_form, ignore modifier
  4. drop canonical_path entirely — htc_form alone (lowest confidence)
  5. NO_MATCH — recipe ingredient has no priced concept

Within tiers 2-4, when multiple priced concept_keys match, pick the one with
the most package SKUs (most stable evidence).

Output: planner/data/concept_resolution.json
        recipe_concept_key → priced_concept_key  (or "NO_MATCH")
        + tier label per resolution
"""
from __future__ import annotations
import json, sys
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / "planner" / "data" / "concept_index.json"
RCG = ROOT / "planner" / "data" / "recipe_concept_grams.json"
SYNS = ROOT / "recipe_pricing" / "leaf_synonyms.csv"
OUT = ROOT / "planner" / "data" / "concept_resolution.json"
MANUAL = ROOT / "recipe_pricing" / "concept_resolution_overrides.csv"
BAD_HTC_GROUPS = {"0", "N"}

# R12 gates — see /Users/jamiebarton/Desktop/esha_audit_bundle/recipe_pricing/feedback_durable_fixes_not_whackamole.md
# Singleton-bucket rejection: any non-exact tier (form_only, parent_form,
# parent_path_only) requires the target priced concept to have at least
# this many distinct SKUs. Below the floor → NO_MATCH instead.
# Why 3: it kills contamination buckets where 1–2 mis-classified SKUs
# (Mrs Meyer's at basil, Magic Man at oil) are the ONLY entries.
SINGLETON_FLOOR = 3

# Top-category invariant: cross-top-cat fallback below alias_exact tier is
# rejected. Recipe asks "Pantry > Broth & Stock > Chicken Broth"; falling
# through to "Meat & Seafood > Poultry > Chicken" (lunchmeat) is wrong.
# Set to True to enforce.
TOP_CAT_INVARIANT = True


def valid_htc_form(htc_form: str) -> bool:
    return bool(htc_form) and htc_form != "00000000" and htc_form[:1] not in BAD_HTC_GROUPS


def _top_cat(p: str) -> str:
    return (p.split(" > ")[0] if p else "")


UNSAFE_PATH_ONLY_CPS = {
    # These are category buckets, not food identities. Same-cp/different-form
    # fallback on them picks whichever priced child happens to live at the
    # broad path (e.g. endive/leafy greens buying Anaheim peppers).
    "Produce > Vegetables",
    "Produce > Fruit",
    "Pantry > Canned Vegetables",
    "Frozen > Vegetables",
}


def _allow_same_cp_path_only(cp: str) -> bool:
    return bool(cp) and cp not in UNSAFE_PATH_ONLY_CPS


def main():
    ci = json.loads(CI.read_text())
    rcg = json.loads(RCG.read_text())

    # Index priced concept_keys by (cp, htc_form), htc_form alone, and cp alone
    by_cp_form: dict[tuple, list[str]] = defaultdict(list)
    by_form: dict[str, list[str]] = defaultdict(list)
    by_path: dict[str, list[str]] = defaultdict(list)
    for ck, c in ci.items():
        cp, htc_form = c["canonical_path"], c["htc_form"]
        if not valid_htc_form(htc_form):
            continue
        by_cp_form[(cp, htc_form)].append(ck)
        by_form[htc_form].append(ck)
        by_path[cp].append(ck)

    # Sort each bucket by n_skus_total descending (most evidence first)
    for buckets in (by_cp_form, by_form, by_path):
        for k in buckets:
            buckets[k].sort(key=lambda x: -ci[x]["n_skus_total"])

    priced = set(ci.keys())

    manual_overrides: dict[str, str] = {}
    if MANUAL.exists():
        import csv as _csv
        with MANUAL.open() as f:
            for row in _csv.DictReader(f):
                recipe_key = (row.get("recipe_concept_key") or "").strip()
                priced_key = (row.get("priced_key") or "").strip()
                if recipe_key and priced_key:
                    if priced_key not in priced:
                        print(f"WARNING: manual override target missing: {priced_key}",
                              file=sys.stderr)
                        continue
                    manual_overrides[recipe_key] = priced_key
        print(f"loaded {len(manual_overrides)} manual resolution overrides",
              file=sys.stderr)

    # Collect every recipe-side concept_key
    recipe_freq: Counter = Counter()
    for rid, d in rcg["concept_grams"].items():
        for ck in d: recipe_freq[ck] += 1

    # Load canonical_path alias map (recipe-side path → priced-side path).
    # Curated mapping for cross-category / spelling / synonym fixes.
    aliases: dict[str, str] = {}
    alias_path = ROOT / "recipe_pricing" / "canonical_path_aliases.csv"
    if alias_path.exists():
        import csv as _csv
        with alias_path.open() as f:
            for row in _csv.DictReader(f):
                old = (row.get("old_path") or "").strip()
                new = (row.get("new_path") or "").strip()
                if old and new and old != new:
                    aliases[old] = new
        # Resolve transitive chains
        for k in list(aliases.keys()):
            seen = {k}; v = aliases[k]
            while v in aliases and v not in seen:
                seen.add(v); v = aliases[v]
            aliases[k] = v
        print(f"loaded {len(aliases)} canonical_path aliases", file=sys.stderr)

    import re as _re_g
    STOP_LEAF_G = {"the","a","an","of","and","or","with","fresh","raw","organic","plain","baby"}
    def _recipe_leaf_specific(recipe_cp: str) -> set[str]:
        """Recipe-leaf tokens MINUS the candidate path's own leaf tokens —
        i.e., the SPECIFIC discriminators only, not the generic family token.
        For "Andouille Sausage" walking up to "Sausage", returns {andouille}
        (drops "sausage" because it's the parent's own leaf)."""
        leaf = (recipe_cp.split(" > ")[-1] if recipe_cp else "").lower()
        return {t for t in _re_g.findall(r"[a-z]+", leaf)
                 if len(t) > 2 and t not in STOP_LEAF_G}

    def _path_leaf_tokens(p: str) -> set[str]:
        leaf = (p.split(" > ")[-1] if p else "").lower()
        return {t for t in _re_g.findall(r"[a-z]+", leaf)
                 if len(t) > 2 and t not in STOP_LEAF_G}

    def _sku_pool_contains_specific(c: dict, specific: set[str]) -> bool:
        """At least one SKU in the candidate's package pool must contain a
        recipe-specific token. Used only when cand has its OWN tokens not in
        recipe leaf (true cross-bridge case). For pure parent fallback
        (cand-leaf ⊆ recipe-leaf) we don't need this — recipe is just more
        specific than priced, and the parent SKU is the right substitute."""
        if not specific: return True
        for pkg in c.get("packages", [])[:10]:
            nl = (pkg.get("name","") or "").lower()
            if any(t in nl for t in specific):
                return True
        return False

    # Precompute cp-level aggregate SKU counts. The singleton floor was
    # killing chicken-leg matches because priced has 18 SKUs at "Chicken
    # Leg" cp BUT spread across many htc_forms with n=1 each. cp-level
    # aggregate proves the food family has real depth even when each
    # (cp, htc_form) bucket is small.
    cp_total_skus: dict[str, int] = {}
    for ck, c in ci.items():
        cp_x = c.get("canonical_path", "")
        cp_total_skus[cp_x] = cp_total_skus.get(cp_x, 0) + c.get("n_skus_total", 0)

    def passes_gates(candidate_ck: str, recipe_cp: str,
                     require_specific_sku: bool = False) -> bool:
        """R14b gates: singleton + top-cat + cross-bridge SKU-pool check.

        `require_specific_sku=True` ONLY rejects TRUE cross-bridges where the
        candidate's leaf has tokens that are NOT in the recipe leaf (e.g.,
        recipe=Andouille Sausage, cand=Chorizo Sausage — 'chorizo' is in
        cand but not recipe → cross-bridge → require SKU pool match).

        For pure parent-fallback (cand-leaf is a token-subset of recipe-leaf,
        e.g., recipe=Cumin Seed → cand=Cumin), the candidate IS the
        legitimate substitute and we accept without SKU pool check.
        Otherwise spice forms (whole→ground), herb forms (fresh→dried),
        and most form variations would all NO_MATCH."""
        c = ci.get(candidate_ck)
        if not c: return False
        candidate_cp = c.get("canonical_path", "")
        if candidate_cp in UNSAFE_PATH_ONLY_CPS and candidate_cp != recipe_cp:
            return False
        # Singleton floor: per-(cp, htc_form) is what concept_index splits on,
        # but the meaningful "is this contamination?" check is cp-level
        # aggregate (sum across all htc_forms at this cp). Chicken Leg has
        # n=1 per htc_form but 18 total at cp — that's not contamination.
        cp_total = cp_total_skus.get(c.get("canonical_path",""), 0)
        if cp_total < SINGLETON_FLOOR and c.get("n_skus_total", 0) < SINGLETON_FLOOR:
            return False
        if TOP_CAT_INVARIANT:
            if _top_cat(recipe_cp) and _top_cat(c["canonical_path"]) \
               and _top_cat(recipe_cp) != _top_cat(c["canonical_path"]):
                return False
        if require_specific_sku:
            cand_leaf = _path_leaf_tokens(c["canonical_path"])
            recipe_leaf = _recipe_leaf_specific(recipe_cp)
            extra_in_cand = cand_leaf - recipe_leaf
            # If candidate has NO tokens beyond recipe's own leaf, it's a
            # parent / form-variant / less-specific-but-correct match. Accept.
            if not extra_in_cand:
                return True
            # Otherwise candidate has its OWN distinctive tokens not in
            # recipe — that's a cross-bridge. Require SKU pool to prove the
            # recipe-specific food is actually present.
            specific = recipe_leaf - cand_leaf
            if specific and not _sku_pool_contains_specific(c, specific):
                return False
        return True

    resolution: dict[str, dict] = {}
    counts: Counter = Counter()
    gate_rejections: Counter = Counter()
    for rk, n in recipe_freq.items():
        # NEW SCHEMA: rk = "canonical_path|htc_form" (no modifier)
        cp, htc_form = rk.split("|", 1)
        if cp.startswith("Non-Food") or not valid_htc_form(htc_form):
            resolution[rk] = {"tier": "NO_MATCH", "priced_key": None}
            counts["no_match"] += 1
            continue

        if rk in manual_overrides:
            resolution[rk] = {
                "tier": "manual_override",
                "priced_key": manual_overrides[rk],
            }
            counts["manual_override"] += 1
            continue

        # Apply alias map BEFORE tier resolution. Recipe-side cp may live at
        # a different category than priced-side; alias rewires it.
        # R13 fix: aliased candidates STILL must pass singleton floor + SKU
        # pool check. Without this gate, alias_exact bypasses our gates and
        # contamination buckets win.
        if cp in aliases:
            cp = aliases[cp]
            rk_check = f"{cp}|{htc_form}"
            if rk_check in priced:
                # Gate the alias target — don't accept singleton/cross-cat
                # without the same scrutiny we apply elsewhere
                if passes_gates(rk_check, cp, require_specific_sku=True):
                    resolution[rk] = {"tier": "alias_exact", "priced_key": rk_check}
                    counts["alias_exact"] += 1
                    continue
                else:
                    gate_rejections["alias_exact"] += 1
            # else fall through to existing tiers using the aliased cp

        # Tier 1: exact. Exact (cp, htc_form) match is generally trustworthy
        # but still apply the singleton floor — without it, a contaminated
        # bucket where the only SKU is non-food (Mrs Meyer's at basil exact
        # tier) wins. The non-food blocklist at build_concept_index time
        # already removes most contamination; the singleton floor is the
        # belt-and-suspenders backup.
        # Exact: recipe ck matches priced ck (cp + htc_form both match).
        # NO singleton floor here — exact agreement on htc_form means the
        # food identity is confirmed by the encoder. Mrs-Meyer's-style
        # contamination is handled upstream by the non-food blocklist
        # and quarantine before we get here.
        if rk in priced:
            resolution[rk] = {"tier": "exact", "priced_key": rk}
            counts["exact"] += 1
            continue

        # Tier 2: same path + form, any modifier. cp-aggregate floor.
        if (cp, htc_form) in by_cp_form:
            for cand in by_cp_form[(cp, htc_form)]:
                if (ci[cand].get("n_skus_total", 0) < SINGLETON_FLOOR
                    and cp_total_skus.get(cp, 0) < SINGLETON_FLOOR):
                    gate_rejections["path_form"] += 1
                    continue
                resolution[rk] = {"tier": "path_form", "priced_key": cand}
                counts["path_form"] += 1
                break
            if rk in resolution: continue

        # Tier 2.5 — same-cp-different-form (formerly tier 5 path_only).
        # MOVED EARLIER: when recipe and priced have the same cp but
        # different htc_forms, the food identity is the same (cp leaf
        # confirms it). Prefer this over walking up to parent. Without
        # this, Ground Chicken|300A0004 (recipe) doesn't match Ground
        # Chicken|300A0026 (priced, n=2), then sibling tier kicks in and
        # picks Chicken Breast — but the right SKU was at the same cp
        # all along.
        if _allow_same_cp_path_only(cp) and cp in by_path:
            best_cand = max(by_path[cp],
                            key=lambda c: ci[c].get("n_skus_total", 0),
                            default=None)
            if best_cand and TOP_CAT_INVARIANT and \
               _top_cat(cp) and _top_cat(ci[best_cand]["canonical_path"]) \
               and _top_cat(cp) != _top_cat(ci[best_cand]["canonical_path"]):
                best_cand = None
            if best_cand:
                resolution[rk] = {"tier": "path_only", "priced_key": best_cand}
                counts["path_only"] += 1
                continue

        # Tier 3: walk up the canonical_path — RESTRICTED so that the
        # parent's priced concept must share a leaf token with our
        # recipe-side leaf. Without this guard, "Pantry > Spices > Garlic
        # Powder|E700000=" walks up to "Pantry|E700000=" which has just one
        # SKU "Whole Sesame Seed" — wrong food. Require leaf-overlap to
        # prevent garbage parent matches.
        import re as _re_p
        STOP_LEAF_P = {"the","a","an","of","and","or","with","fresh","raw","organic","plain","baby"}
        def _leaf_tokens_p(p):
            leaf = (p.split(" > ")[-1] if p else "").lower()
            return {t for t in _re_p.findall(r"[a-z]+", leaf)
                     if len(t) > 2 and t not in STOP_LEAF_P}
        recipe_leaf_tokens = _leaf_tokens_p(cp)
        found = None
        if " > " in cp:
            parts = cp.split(" > ")
            for depth in range(len(parts) - 1, 0, -1):
                parent = " > ".join(parts[:depth])
                if (parent, htc_form) in by_cp_form:
                    candidates = by_cp_form[(parent, htc_form)]
                    for cand in candidates:
                        # require_specific_sku on: SKU pool must contain
                        # at least one recipe-specific token (kills
                        # chorizo-for-andouille parent-fallback bug)
                        if not passes_gates(cand, cp, require_specific_sku=True):
                            gate_rejections["parent_form"] += 1
                            continue
                        cand_cp = ci[cand]["canonical_path"]
                        if recipe_leaf_tokens and \
                           not (recipe_leaf_tokens & _leaf_tokens_p(cand_cp)):
                            continue
                        found = ("parent_form", cand)
                        break
                    if found: break
        if found:
            resolution[rk] = {"tier": found[0], "priced_key": found[1]}
            counts[found[0]] += 1
            continue

        # Tier 3.5 — SIBLING_PATH: walk to recipe's parent path and try
        # children. Rank by:
        #   1. Leaf-token overlap COUNT with recipe leaf (highest wins)
        #   2. Tie-break by pool size (more SKUs = more reliable)
        # This stops sibling tier from picking "Great Value Grilled Chicken
        # Breast" for chicken-leg/livers/duck (all overlap on {chicken}=1
        # token, breast has biggest pool). With overlap-count first,
        # "Chicken Leg" matches "Chicken Leg Quarters" (overlap=2) over
        # "Chicken Breast" (overlap=1).
        if " > " in cp:
            parts = cp.split(" > ")
            parent = " > ".join(parts[:-1])
            recipe_leaf_t = _leaf_tokens_p(cp)
            best_sib = None
            best_score = (-1, -1)  # (overlap_count, pool_size)
            for cand_ck, cand_meta in ci.items():
                cand_cp = cand_meta["canonical_path"]
                if not cand_cp.startswith(parent + " > "): continue
                if cand_cp == cp: continue
                if cand_cp.count(" > ") != len(parts) - 1: continue
                if not passes_gates(cand_ck, cp, require_specific_sku=True):
                    gate_rejections["sibling_path"] += 1
                    continue
                cand_leaf_t = _leaf_tokens_p(cand_cp)
                overlap = recipe_leaf_t & cand_leaf_t
                if not overlap: continue
                if cand_meta.get("n_skus_total", 0) < SINGLETON_FLOOR: continue
                score = (len(overlap), cand_meta["n_skus_total"])
                if score > best_score:
                    best_score = score; best_sib = cand_ck
            if best_sib:
                resolution[rk] = {"tier": "sibling_path", "priced_key": best_sib}
                counts["sibling_path"] += 1
                continue

        # Tier 4: htc_form alone — RESTRICTED to require leaf-token overlap.
        # Without this guard, "Produce > Vegetables > Avocado|6018000R" would
        # match "Pantry > Canned Vegetables > Grape Leaves|6018000R" via form
        # alone (avocado→grape-leaves), and "Oregano|E304400U" would match
        # "Bay Leaves|E304400U" (oregano→bay leaves). We require at least
        # one leaf-token match between the recipe's leaf and the priced
        # concept's leaf.
        import re as _re
        STOP_LEAF = {"the","a","an","of","and","or","with","fresh","raw","organic","plain","baby"}
        def _leaf_tokens(p):
            leaf = (p.split(" > ")[-1] if p else "").lower()
            return {t for t in _re.findall(r"[a-z]+", leaf)
                     if len(t) > 2 and t not in STOP_LEAF}

        if htc_form in by_form:
            recipe_leaf_tokens = _leaf_tokens(cp)
            for candidate in by_form[htc_form]:
                # form_only crosses paths — same risk as parent_form. Require
                # SKU pool to contain a recipe-specific token (andouille at
                # parent Sausage must have andouille SKU, not chorizo).
                if not passes_gates(candidate, cp, require_specific_sku=True):
                    gate_rejections["form_only"] += 1
                    continue
                cand_cp = ci[candidate]["canonical_path"]
                cand_leaf_tokens = _leaf_tokens(cand_cp)
                if recipe_leaf_tokens & cand_leaf_tokens:
                    resolution[rk] = {"tier": "form_only",
                                        "priced_key": candidate}
                    counts["form_only"] += 1
                    break
            if rk in resolution:
                continue

        # (Tier 5 path_only was MOVED to tier 2.5 above — same-cp matches
        # are more reliable than walking up to parent.)

        # Tier 6: walk up canonical_path, ignoring form. RESTRICTED with
        # leaf-token guard (mirroring parent_form) and gates. Without the
        # leaf-guard, "Produce > Fruit > Lemons" walks up to "Produce > Fruit"
        # and grabs whichever fruit happens to be cheapest (Red Grapefruit
        # Cup) — wrong food.
        if " > " in cp:
            parts = cp.split(" > ")
            recipe_leaf_tokens_pp = _leaf_tokens(cp)
            for depth in range(len(parts) - 1, 0, -1):
                parent = " > ".join(parts[:depth])
                if parent in by_path:
                    for cand in by_path[parent]:
                        # parent walking — require SKU pool to contain a
                        # recipe-specific token (lemon @ Produce > Fruit
                        # parent must have lemon-named SKU; otherwise
                        # don't fall back to grapefruit cup)
                        if not passes_gates(cand, cp, require_specific_sku=True):
                            gate_rejections["parent_path_only"] += 1
                            continue
                        cand_cp = ci[cand]["canonical_path"]
                        if recipe_leaf_tokens_pp and \
                           not (recipe_leaf_tokens_pp & _leaf_tokens(cand_cp)):
                            continue
                        resolution[rk] = {"tier": "parent_path_only",
                                           "priced_key": cand}
                        counts["parent_path_only"] += 1
                        break
                    if rk in resolution: break
            if rk not in resolution:
                resolution[rk] = {"tier": "NO_MATCH", "priced_key": None}
                counts["no_match"] += 1
        else:
            resolution[rk] = {"tier": "NO_MATCH", "priced_key": None}
            counts["no_match"] += 1

    print("Resolution distribution (over recipe concept_keys):", file=sys.stderr)
    total = sum(counts.values())
    for tier in ("manual_override", "exact", "alias_exact", "path_form", "parent_form", "sibling_path", "form_only", "path_only", "parent_path_only", "no_match"):
        n = counts.get(tier, 0)
        print(f"  {tier:<18}  {n:>6,}  ({n/total*100:>5.1f}%)", file=sys.stderr)
    print(f"  total              {total:>6,}", file=sys.stderr)
    if gate_rejections:
        print(f"\nGate rejections (tier-level singleton/top-cat veto):",
              file=sys.stderr)
        for tier, n in gate_rejections.most_common():
            print(f"  {tier:<18}  {n:>6,}", file=sys.stderr)

    # Also dump priced_key → set of recipe-side leaf tokens for adapter use
    import re
    PATH = ROOT / "planner" / "data" / "priced_to_recipe_leaf.json"
    STOP = {"the","a","an","of","and","or","with","fresh","raw","organic","plain"}
    p2r: dict[str, set[str]] = {}
    for rk, r in resolution.items():
        pk = r.get("priced_key")
        if not pk: continue
        cp = rk.split("|", 1)[0]
        leaf = cp.split(" > ")[-1].lower() if cp else ""
        toks = [w for w in re.findall(r"[a-z]+", leaf) if len(w)>2 and w not in STOP]
        p2r.setdefault(pk, set()).update(toks)
    PATH.write_text(json.dumps({k: sorted(v) for k, v in p2r.items()}))
    print(f"  → {PATH}  ({PATH.stat().st_size/1024/1024:.2f} MB) "
          f"({len(p2r):,} priced concepts with recipe-leaf hints)",
          file=sys.stderr)
    OUT.write_text(json.dumps(resolution))
    print(f"\n→ {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)", file=sys.stderr)


if __name__ == "__main__":
    main()
