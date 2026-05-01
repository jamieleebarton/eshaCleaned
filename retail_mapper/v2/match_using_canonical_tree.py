#!/usr/bin/env python3
"""Match every SKU in full_corpus_cleaned.csv against the existing combined
FNDDS+SR28 canonical tree (Hestia/api/data/fndds_canonical_tree_enriched.json).

This is the right way to do the alignment per the user's intent:
  - The canonical tree already carries curated FNDDS + SR28 + portions for
    11,315 product keys (e.g. "almond coconut > milk", "almond butter > default").
  - Walking each SKU's TITLE through the tree finds the most specific match
    available — granular enough that "almond milk chocolate unsweetened" lands
    on a flavored almond-milk entry if the tree has one, falling back to plain
    almond milk otherwise.
  - ESHA is used only as a fallback for SKUs the canonical tree couldn't place.

Outputs:
  - full_corpus_enriched.csv — every SKU decorated with fndds_code, sr28_code,
    portions_json, esha_code, match_source, match_score
  - product_tree_enriched.csv — the tree leaves with their dominant
    FNDDS/SR28/ESHA assignment + coverage stats

Usage:
    python3 retail_mapper/v2/match_using_canonical_tree.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"

CORPUS = V2 / "full_corpus_cleaned.csv"
NODES_CSV = V2 / "product_tree_nodes.csv"
CANONICAL_TREE = REPO.parent / "Hestia" / "api" / "data" / "fndds_canonical_tree_enriched.json"
ESHA_FILE = REPO / "esha_cleaned.csv"
SR_LEGACY = REPO / "data" / "sr28_csv" / "sr_legacy_food.csv"  # NDB→fdc_id
SR_FOOD   = REPO / "data" / "sr28_csv" / "food.csv"            # fdc_id→description

OUT_SKU = V2 / "full_corpus_enriched.csv"
OUT_TREE = V2 / "product_tree_enriched.csv"

csv.field_size_limit(sys.maxsize)

STOPWORDS = {
    "and","with","the","of","in","on","for","or","to","a","an",
    "no","not","without","added","ns","nfs","nsa","as","is","be","at",
}
# Words that carry product-distinguishing meaning (fat, reduced, organic,
# unsweetened, etc.) MUST stay in the token stream — dropping them silently
# loses specificity and lets a generic key beat the right one.


def stem(t: str) -> str:
    if len(t) < 4: return t
    if t.endswith("ies") and len(t) > 4: return t[:-3] + "y"
    if t.endswith(("ses","xes","zes","ches","shes")): return t[:-2]
    if t.endswith("oes"): return t[:-2]
    if t.endswith("s") and not t.endswith(("ss","us","is")): return t[:-1]
    return t


def tokenize(s: str) -> list[str]:
    text = (s or "").lower()
    # Pre-normalize common compound words so query tokens align with what
    # USDA / canonical-tree descriptions actually use:
    #  - SR28 writes "Babyfood, fruit, banana, junior" — concatenated.
    #  - Retail SKUs write "ALMONDMILK", "OATMILK", "BABYFOOD" without spaces.
    # Normalize both directions to a single split form so they match.
    text = (text
            .replace("babyfood", "baby food")
            .replace("almondmilk", "almond milk")
            .replace("oatmilk", "oat milk")
            .replace("soymilk", "soy milk")
            .replace("ricemilk", "rice milk")
            .replace("coconutmilk", "coconut milk"))
    return [stem(t) for t in re.findall(r"\w+", text)
            if t and t not in STOPWORDS and not t.isdigit()]


# ---- Flatten canonical tree into a searchable list ----
def flatten_canonical_tree(tree: dict) -> list[dict]:
    """Walk the nested keyword tree; emit one record per leaf with full key
    path + codes.

    For parent nodes that have children but no own fndds_code (e.g.
    'almond milk' has 4 child variants but no parent default), synthesize a
    parent entry using the FIRST child's fndds_code. That way generic SKU
    titles ("ORIGINAL ALMOND BEVERAGE") still land on the almond-milk family
    rather than falling to plain 'milk'.
    """
    out: list[dict] = []

    def walk(node, path: list[str]) -> dict | None:
        """Returns the synthesized 'first leaf reached' so parents can adopt it."""
        if not isinstance(node, dict):
            return None
        own_codes = {}
        if "fndds_code" in node or "sr28_code" in node:
            own_codes = {
                "fndds_code": node.get("fndds_code", ""),
                "sr28_code": node.get("sr28_code", ""),
                "portions": node.get("portions") or {},
            }
            out.append({
                "key_tokens": tokenize(" ".join(path)),
                "key_str": " ".join(path),
                "depth": len(path),
                **own_codes,
            })
        first_descendant_codes = own_codes or None
        for k, v in node.items():
            if k in ("fndds_code", "sr28_code", "portions"):
                continue
            child_path = path if k == "default" else path + [k]
            child_codes = walk(v, child_path)
            if first_descendant_codes is None and child_codes:
                first_descendant_codes = child_codes
        # Synthesize a parent entry if the node had no own fndds but has descendants
        if not own_codes and first_descendant_codes and path:
            out.append({
                "key_tokens": tokenize(" ".join(path)),
                "key_str": " ".join(path) + "  (parent-default)",
                "depth": len(path),
                "fndds_code": first_descendant_codes["fndds_code"],
                "sr28_code": first_descendant_codes["sr28_code"],
                "portions": first_descendant_codes.get("portions") or {},
                "is_parent_default": True,
            })
        return first_descendant_codes

    for top, sub in tree.items():
        walk(sub, [top])
    return out


# ---- Build inverted index for fast candidate lookup ----
def build_inv_index(entries: list[dict]) -> dict[str, list[int]]:
    """token → list of entry indices that contain it."""
    inv: dict[str, list[int]] = defaultdict(list)
    for i, e in enumerate(entries):
        for t in set(e["key_tokens"]):
            inv[t].append(i)
    return inv


def match_title(title_tokens: list[str],
                entries: list[dict],
                inv_index: dict[str, list[int]],
                identity_tokens: list[str] | None = None) -> tuple[int, float] | None:
    """Two-tier match with identity bias.

    `identity_tokens` is the LLM-cleaned product identity ("Almond Milk" →
    ["almond", "milk"]). Keys that contain identity tokens get a bonus, so
    "CHOCOLATE ALMOND MILK" with identity "Almond Milk" routes to `almond milk
    chocolate` family rather than tying with `chocolate milk`.

    Tier 1 (strict): all key tokens in title set. Pick highest score.
    Tier 2 (relaxed): if no strict match, partial-overlap with extras-penalty.
    Score in both tiers includes a +0.5 per identity token covered by the key.
    """
    if not title_tokens:
        return None
    title_set = set(title_tokens)
    id_set = set(identity_tokens or [])
    candidates: set[int] = set()
    for t in title_set:
        for idx in inv_index.get(t, ()):
            candidates.add(idx)
    if not candidates:
        return None

    # Hard identity constraint: if the canonical tree HAS entries containing the
    # identity's tokens, restrict candidates to those. This prevents
    # "APPLE CINNAMON BAGELS" with identity=Bagels from routing to the
    # fruit/spice "apple cinnamon" entry — bagel-rooted entries always win
    # when the identity says it's a bagel.
    if id_set:
        id_candidates: set[int] = set()
        for t in id_set:
            for idx in inv_index.get(t, ()):
                id_candidates.add(idx)
        # Only restrict if intersection is non-empty (the identity has at least
        # one match in the canonical tree). If empty, fall through.
        intersect = candidates & id_candidates
        if intersect:
            candidates = intersect

    # Tier 1: strict subset
    strict_idx, strict_score = -1, -1.0
    for idx in candidates:
        e = entries[idx]
        kset = set(e["key_tokens"])
        if not kset:
            continue
        if not kset.issubset(title_set):
            continue
        score = len(kset) + 0.01 * e["depth"]
        # Identity bias: reward keys whose tokens match the identity
        score += 0.5 * len(kset & id_set)
        if score > strict_score:
            strict_score = score
            strict_idx = idx
    if strict_idx >= 0:
        return strict_idx, strict_score

    # Tier 2: relaxed overlap with extras penalty
    best_idx, best_score = -1, -1.0
    for idx in candidates:
        e = entries[idx]
        kset = set(e["key_tokens"])
        if not kset:
            continue
        common = kset & title_set
        if not common:
            continue
        extras = len(kset) - len(common)
        score = len(common) - 0.5 * extras + 0.01 * e["depth"]
        score += 0.5 * len(kset & id_set)
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_idx < 0:
        return None
    return best_idx, best_score


# ---- SR28 loader (full reference, used when canonical tree has no SR28) ----
def load_sr28() -> tuple[list[dict], dict[str, list[int]]]:
    """Build entries from the full SR28 (7,793 rows). Each entry has the NDB
    code (sr28_code) and the description. Indexed for keyword lookup."""
    entries: list[dict] = []
    if not (SR_LEGACY.exists() and SR_FOOD.exists()):
        return entries, {}
    ndb_to_fdc: dict[str, str] = {}
    with SR_LEGACY.open(encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            ndb = (r.get("NDB_number") or "").strip()
            fdc = (r.get("fdc_id") or "").strip()
            if ndb and fdc:
                ndb_to_fdc[ndb] = fdc
    fdc_to_desc: dict[str, str] = {}
    with SR_FOOD.open(encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            fdc = (r.get("fdc_id") or "").strip()
            d = (r.get("description") or "").strip()
            if fdc and d:
                fdc_to_desc[fdc] = d
    for ndb, fdc in ndb_to_fdc.items():
        d = fdc_to_desc.get(fdc, "")
        if d:
            entries.append({
                "key_tokens": tokenize(d),
                "key_str": d,
                "sr28_code": ndb,
            })
    inv: dict[str, list[int]] = defaultdict(list)
    for i, e in enumerate(entries):
        for t in set(e["key_tokens"]):
            inv[t].append(i)
    return entries, inv


def match_sr28(title_tokens: list[str], identity_tokens: list[str],
               entries: list[dict], inv_index: dict[str, list[int]]) -> tuple[int, float] | None:
    """Identity-anchored match against full SR28 descriptions (7,793 entries).

    Scoring rules:
      - +2 per identity token that appears in the SR28 description's tokens
      - +3 if the SR28 description STARTS with the identity word (canonical
        form: 'Biscuits, plain or buttermilk...' beats 'KFC, biscuit')
      - +1 per non-identity title token that overlaps
      - -0.1 per extra description token that doesn't overlap (mild penalty;
        SR28 descriptions are verbose by design and longer ones are usually
        more specific, not noise)
    """
    if not title_tokens:
        return None
    title_set = set(title_tokens)
    id_set = set(identity_tokens or [])
    candidates: set[int] = set()
    for t in title_set:
        for idx in inv_index.get(t, ()):
            candidates.add(idx)
    if not candidates:
        return None
    best_idx, best_score = -1, -1.0
    for idx in candidates:
        e = entries[idx]
        kset = set(e["key_tokens"])
        if not kset:
            continue
        common = kset & title_set
        if not common:
            continue
        id_overlap = len(kset & id_set)
        extras = len(kset) - len(common)
        score = (
            len(common)
            + 2.0 * id_overlap
            - 0.1 * extras
        )
        # Big bonus when description starts with an identity token (canonical form)
        first = e["key_tokens"][0] if e["key_tokens"] else ""
        if first in id_set:
            score += 3.0
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_idx < 0:
        return None
    return best_idx, best_score


# ---- ESHA loader (fallback) ----
def load_esha() -> tuple[list[dict], dict[str, list[int]]]:
    entries: list[dict] = []
    if not ESHA_FILE.exists():
        return entries, {}
    with ESHA_FILE.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("EshaCode") or "").strip()
            desc = (row.get("Description") or "").strip()
            if code and desc:
                entries.append({
                    "key_tokens": tokenize(desc),
                    "key_str": desc,
                    "esha_code": code,
                })
    inv: dict[str, list[int]] = defaultdict(list)
    for i, e in enumerate(entries):
        for t in set(e["key_tokens"]):
            inv[t].append(i)
    return entries, inv


def match_esha(title_tokens: list[str],
               entries: list[dict],
               inv_index: dict[str, list[int]],
               identity_tokens: list[str] | None = None) -> tuple[int, float] | None:
    """Identity-anchored ESHA match.

    ESHA descriptions are verbose ("Bread, white, commercially prepared
    (includes soft bread crumbs)"), so a naive length-penalty makes a 1-token
    match like "Beer" beat the right multi-token match. Use the same scoring
    as match_sr28: heavy identity bonus, mild extras penalty, big bonus when
    description starts with the identity token.
    """
    if not title_tokens:
        return None
    title_set = set(title_tokens)
    id_set = set(identity_tokens or [])
    candidates: set[int] = set()
    for t in title_set:
        for idx in inv_index.get(t, ()):
            candidates.add(idx)
    if not candidates:
        return None
    best_idx, best_score = -1, -1.0
    for idx in candidates:
        e = entries[idx]
        kset = set(e["key_tokens"])
        if not kset:
            continue
        common = kset & title_set
        if not common:
            continue
        id_overlap = len(kset & id_set)
        extras = len(kset) - len(common)
        score = (
            len(common)
            + 2.0 * id_overlap
            - 0.1 * extras
        )
        first = e["key_tokens"][0] if e["key_tokens"] else ""
        if first in id_set:
            score += 3.0
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_idx < 0:
        return None
    return best_idx, best_score


def main() -> None:
    if not CANONICAL_TREE.exists():
        raise SystemExit(f"missing {CANONICAL_TREE}")

    print(f"  loading canonical tree from {CANONICAL_TREE.name}")
    tree = json.loads(CANONICAL_TREE.read_text())
    entries = flatten_canonical_tree(tree)
    print(f"    {len(entries):,} canonical entries flattened")
    inv = build_inv_index(entries)

    print(f"  loading SR28 fallback (full reference)")
    sr28_entries, sr28_inv = load_sr28()
    print(f"    {len(sr28_entries):,} SR28 entries")
    # Build NDB→description map for sanity-checking the canonical tree's SR28
    sr28_desc_by_ndb = {e["sr28_code"]: e["key_str"] for e in sr28_entries}

    print(f"  loading ESHA fallback from {ESHA_FILE.name}")
    esha_entries, esha_inv = load_esha()
    print(f"    {len(esha_entries):,} ESHA entries")

    print(f"  reading {CORPUS.name}")
    sku_count = 0
    canonical_hits = 0
    esha_only_hits = 0
    no_match = 0

    # Track per-leaf assignments for the tree-level rollup
    leaf_to_codes: dict[str, Counter] = defaultdict(Counter)  # canon_key -> (fndds,sr28) Counter
    leaf_to_esha: dict[str, Counter] = defaultdict(Counter)
    leaf_to_total: dict[str, int] = Counter()

    out_cols = [
        "fdc_id","title","branded_food_category",
        "category_path_fixed","product_identity_fixed","canonical_path",
        "variant","flavor","modifier","retail_leaf_path",
        "fndds_code","sr28_code","esha_code","match_source","match_score",
        "portions_json","matched_key",
    ]
    # Plain-token detection — values that mean "baseline, no special variant".
    # Includes marketing adjectives that don't change what the product IS.
    PLAIN_TOKENS = {
        "plain","regular","original","classic","natural",
        "unflavored","unscented","neutral",
        # baseline fortification status — meaningless for retail-recipe matching
        "enriched","unenriched",
        # marketing / style adjectives — describe vibe not product type
        "artisan","rustic","country","homestyle","traditional",
        "gourmet","bakery","style","authentic","old","fashioned",
        "premium","deluxe","fancy","handcrafted","signature","select",
    }
    # Recipe-relevant claims to fold into the modifier. Certification claims
    # like kosher/vegan/non_gmo are deliberately excluded — they don't change
    # the product identity for cooking purposes.
    RELEVANT_CLAIMS = {
        "diet","light","low_fat","fat_free","reduced_fat",
        "sugar_free","no_sugar_added","unsweetened","low_sodium",
        "decaf","decaffeinated","caffeine_free",
        "gluten_free","organic","keto","paleo","whole_grain",
    }
    # Structural form tokens — change WHAT the product is, not just texture.
    # Stuffed breadsticks are a different retail product from plain ones; same
    # for filled pastries, sliced loaves, etc. Texture-only values
    # (soft/crispy/creamy/chunky) are intentionally excluded.
    RELEVANT_FORMS = {
        "stuffed","filled","topped","split","sliced","pre_sliced",
        "twisted","layered","rolled","frosted","glazed",
    }
    def all_facet_values(s: str) -> list[str]:
        if not s: return []
        return [v.strip() for v in s.split("|") if v.strip()]
    def prettify_token(tok: str) -> str:
        return " ".join(w.capitalize() for w in tok.replace("_"," ").split())
    # Identity-synonym pairs so 'burger_buns' modifier matches 'Hamburger Buns'
    # identity, and 'hotdog' modifier matches 'Hot Dog Buns', etc.
    # Pairs can be single-word or multi-word; multi-word forms are matched
    # by checking whether all component words appear in the identity.
    IDENTITY_SYNONYMS = [
        ("hamburger", "burger"),
        ("doughnut",  "donut"),
        ("breadstick","bread stick"),
        ("hot dog",   "hotdog"),
        ("english muffin", "englishmuffin"),
        ("ice cream", "icecream"),
    ]

    def _identity_word_set(identity: str) -> set[str]:
        id_l = identity.lower()
        ws = {stem(w) for w in re.split(r"\W+", id_l) if w}
        for a, b in IDENTITY_SYNONYMS:
            # Each side might be one or many words. Match when ALL component
            # stems appear in the identity's word set, then add stems from the
            # other side AND a concatenated/space-stripped form.
            a_words = [stem(w) for w in a.split() if w]
            b_words = [stem(w) for w in b.split() if w]
            a_in = all(w in ws for w in a_words) if a_words else False
            b_in = all(w in ws for w in b_words) if b_words else False
            if a_in or b_in:
                for w in a_words: ws.add(w)
                for w in b_words: ws.add(w)
                ws.add(stem(a.replace(" ", "")))
                ws.add(stem(b.replace(" ", "")))
        return ws

    def _strip_identity_words(toks: list[str], identity: str) -> list[str]:
        if not identity:
            return list(toks)
        id_words = _identity_word_set(identity)
        out: list[str] = []
        for t in toks:
            words = [w for w in re.split(r"[\s_]+", t) if w]
            kept = [w for w in words if stem(w.lower()) not in id_words]
            if kept:
                out.append("_".join(kept))
        return out

    def _drop_plain_and_dedup(toks: list[str]) -> list[str]:
        toks = [t for t in toks if t.lower() not in PLAIN_TOKENS]
        seen: set[str] = set()
        out: list[str] = []
        for t in toks:
            if t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
        return out

    def _level_to_string(toks: list[str]) -> str:
        """Convert a level's tokens into a single canonical-ordered string.
        Splits all tokens into words, dedupes, sorts alphabetically. So
        'butter_garlic' and 'garlic_butter' both become 'Butter Garlic'."""
        all_words: list[str] = []
        for t in toks:
            for w in re.split(r"[\s_]+", t):
                if w: all_words.append(w.lower())
        # Dedup + alphabetical sort for canonical order
        seen: set[str] = set()
        unique: list[str] = []
        for w in all_words:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        unique.sort()
        return " ".join(prettify_token(w) for w in unique)

    def derive_modifier_levels(variant: str, flavor: str, claims: str = "",
                               form: str = "", identity: str = "") -> list[str]:
        """Hierarchical levels:
          Level 1: variant + flavor (sorted alphabetically for consistency)
          Level 2: claims
          Level 3: structural form
        """
        l1 = _drop_plain_and_dedup(_strip_identity_words(
            all_facet_values(variant) + all_facet_values(flavor), identity))
        l2 = _drop_plain_and_dedup(_strip_identity_words(
            [c for c in all_facet_values(claims) if c.lower() in RELEVANT_CLAIMS],
            identity))
        l3 = _drop_plain_and_dedup(_strip_identity_words(
            [t for t in all_facet_values(form) if t.lower() in RELEVANT_FORMS],
            identity))
        levels: list[str] = []
        if l1: levels.append(_level_to_string(l1))
        if l2: levels.append(_level_to_string(l2))
        if l3: levels.append(_level_to_string(l3))
        if not levels:
            return ["Plain"]
        return levels

    def derive_modifier(variant: str, flavor: str, claims: str = "",
                        form: str = "", identity: str = "") -> str:
        """Backwards-compat single-string view: levels joined by ' > '."""
        return " > ".join(derive_modifier_levels(variant, flavor, claims, form, identity))
    OUT_SKU.parent.mkdir(parents=True, exist_ok=True)
    with CORPUS.open(encoding="utf-8") as src, \
         OUT_SKU.open("w", encoding="utf-8", newline="") as dst:
        rdr = csv.DictReader(src)
        wtr = csv.DictWriter(dst, fieldnames=out_cols)
        wtr.writeheader()
        for row in rdr:
            sku_count += 1
            title = row.get("title", "")
            identity = row.get("product_identity_fixed", "")
            bfc = row.get("branded_food_category", "")
            leaf = row.get("canonical_path", "")
            variant = row.get("variant", "")
            flavor = row.get("flavor", "")
            claims = row.get("claims", "")
            form = row.get("form_texture_cut", "")
            modifier = derive_modifier(variant, flavor, claims, form, identity)
            retail_leaf_path = f"{leaf} > {modifier}" if leaf and modifier else leaf
            leaf_to_total[leaf] += 1

            # Identity tokens are passed separately so the matcher can bias
            # toward keys that include the identity (e.g., "almond milk" wins
            # over "chocolate milk" for an almond-milk SKU).
            # BFC tokens are appended too — they often carry storage/form info
            # ("Crusts & Dough" → adds 'crust','dough') that helps SR28 picks.
            id_toks = tokenize(identity)
            qtoks = list(dict.fromkeys(tokenize(title) + id_toks + tokenize(bfc)))

            fndds_code = sr28_code = esha_code = ""
            match_source = ""
            match_score = 0.0
            portions_json = ""
            matched_key = ""

            # Canonical-tree match first
            res = match_title(qtoks, entries, inv, id_toks)
            if res is not None:
                idx, score = res
                e = entries[idx]
                fndds_code = e["fndds_code"]
                sr28_code = e["sr28_code"]
                portions_json = json.dumps(e["portions"]) if e["portions"] else ""
                matched_key = e["key_str"]
                match_source = "canonical_tree"
                match_score = score
                canonical_hits += 1
                leaf_to_codes[leaf][(fndds_code, sr28_code)] += 1

            # SR28 fallback / sanity check.
            #
            # Two cases:
            #  (a) canonical tree had no SR28 → try a direct title→SR28 match
            #  (b) canonical tree gave an SR28 BUT its description doesn't share
            #      any token with the identity (e.g. biscuit identity →
            #      sr28="Wheat flour" — likely a "underlying ingredient" link
            #      from the canonical-tree curator, not the actual product) →
            #      override with a direct match if a better one exists.
            need_fallback = False
            if not sr28_code:
                need_fallback = True
            elif sr28_code in sr28_desc_by_ndb and id_toks:
                desc_toks = set(tokenize(sr28_desc_by_ndb[sr28_code]))
                if not (set(id_toks) & desc_toks):
                    # Canonical SR28 description has zero overlap with identity
                    # tokens → suspect, try fallback.
                    need_fallback = True
            if need_fallback and sr28_entries:
                sr_res = match_sr28(qtoks, id_toks, sr28_entries, sr28_inv)
                if sr_res is not None:
                    sidx, _sscore = sr_res
                    new_sr = sr28_entries[sidx]["sr28_code"]
                    new_desc = sr28_entries[sidx]["key_str"]
                    new_desc_toks = set(tokenize(new_desc))
                    # Only accept if the new SR28 description shares an identity
                    # token (avoids replacing one bad match with another).
                    if set(id_toks) & new_desc_toks:
                        sr28_code = new_sr

            # ESHA fallback for everything (orthogonal — not just no-canonical)
            esha_res = match_esha(qtoks, esha_entries, esha_inv, id_toks)
            if esha_res is not None:
                eidx, escore = esha_res
                esha_code = esha_entries[eidx]["esha_code"]
                if not match_source:
                    match_source = "esha_only"
                    match_score = escore
                    esha_only_hits += 1
                leaf_to_esha[leaf][esha_code] += 1
            elif not match_source:
                no_match += 1

            wtr.writerow({
                "fdc_id": row.get("fdc_id", ""),
                "title": title,
                "branded_food_category": row.get("branded_food_category", ""),
                "category_path_fixed": row.get("category_path_fixed", ""),
                "product_identity_fixed": identity,
                "canonical_path": leaf,
                "variant": variant,
                "flavor": flavor,
                "modifier": modifier,
                "retail_leaf_path": retail_leaf_path,
                "fndds_code": fndds_code,
                "sr28_code": sr28_code,
                "esha_code": esha_code,
                "match_source": match_source,
                "match_score": f"{match_score:.2f}" if match_score else "",
                "portions_json": portions_json,
                "matched_key": matched_key,
            })
            if sku_count % 50000 == 0:
                print(f"    {sku_count:,} SKUs processed", flush=True)

    print()
    print(f"  wrote {OUT_SKU.name} — {sku_count:,} SKUs")
    print(f"    canonical-tree hits: {canonical_hits:,} ({100*canonical_hits/max(sku_count,1):.0f}%)")
    print(f"    esha-only hits:      {esha_only_hits:,} ({100*esha_only_hits/max(sku_count,1):.0f}%)")
    print(f"    no match:            {no_match:,} ({100*no_match/max(sku_count,1):.0f}%)")

    # ---- Tree-level rollup: dominant FNDDS/SR28/ESHA per leaf
    print(f"\n  building leaf-level rollup -> {OUT_TREE.name}")
    tree_cols = [
        "leaf_path", "n_skus_total", "n_canonical_hits",
        "fndds_dominant", "fndds_dominant_n", "fndds_coverage_pct",
        "sr28_dominant",  "sr28_dominant_n",  "sr28_coverage_pct",
        "esha_dominant",  "esha_dominant_n",  "esha_coverage_pct",
        "fndds_distinct", "sr28_distinct", "esha_distinct",
    ]
    with OUT_TREE.open("w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=tree_cols)
        wtr.writeheader()
        for leaf, total in sorted(leaf_to_total.items(), key=lambda kv: -kv[1]):
            cd = leaf_to_codes.get(leaf, Counter())
            fndds_counts = Counter()
            sr_counts = Counter()
            for (f, s), n in cd.items():
                if f: fndds_counts[f] += n
                if s: sr_counts[s] += n
            f_dom = fndds_counts.most_common(1)[0] if fndds_counts else ("", 0)
            s_dom = sr_counts.most_common(1)[0]    if sr_counts else ("", 0)
            esha_counts = leaf_to_esha.get(leaf, Counter())
            e_dom = esha_counts.most_common(1)[0]   if esha_counts else ("", 0)
            wtr.writerow({
                "leaf_path": leaf,
                "n_skus_total": total,
                "n_canonical_hits": sum(cd.values()),
                "fndds_dominant": f_dom[0],
                "fndds_dominant_n": f_dom[1],
                "fndds_coverage_pct": f"{100*f_dom[1]/max(total,1):.0f}",
                "sr28_dominant": s_dom[0],
                "sr28_dominant_n": s_dom[1],
                "sr28_coverage_pct": f"{100*s_dom[1]/max(total,1):.0f}",
                "esha_dominant": e_dom[0],
                "esha_dominant_n": e_dom[1],
                "esha_coverage_pct": f"{100*e_dom[1]/max(total,1):.0f}",
                "fndds_distinct": len(fndds_counts),
                "sr28_distinct":  len(sr_counts),
                "esha_distinct":  len(esha_counts),
            })
    print(f"    {len(leaf_to_total):,} leaves rolled up")


if __name__ == "__main__":
    main()
