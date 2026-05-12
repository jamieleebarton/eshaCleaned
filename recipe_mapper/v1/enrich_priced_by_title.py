#!/usr/bin/env python3
"""Deterministic enrichment of priced_products against the consensus tree.

Algorithm (per the user's spec):
  1. Map Walmart category_path_walmart → matching consensus category
     candidates by token overlap on category_path_original/_fixed.
  2. Match priced product title tokens against product_identity_fixed —
     the PID with maximum token overlap that is FULLY contained in the
     title is the leaf. Longer PIDs (more specific) win.
  3. Within rows sharing that PID, score the remaining title tokens
     against modifier / flavor / form_texture_cut / variant /
     processing_storage to pick the most specific consensus row.
  4. Inherit canonical_path / modifier / sr28_code / fndds_code from it.

Indexed by (pid → row indices) for speed: 6.5k unique PIDs, not 462k rows.
"""
from __future__ import annotations
import csv, re, sqlite3, sys, time
from collections import defaultdict, Counter
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
PRICED_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
AUDIT = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.v2.csv"

WS = re.compile(r"[^a-z0-9 ]+")
STOP = {"the","of","and","with","a","an","to","in","on","by","for","from",
        "size","pack","oz","fl","ml","g","kg","lb","lbs","gallon","ct","ea",
        "count","each","piece","pieces","bag","bottle","jar","can",
        "box","case","family","value","new","free","caffeine","sugar","zero"}
NON_FOOD_NAME = re.compile(
    r"\b(cascaron|confetti|easter|christmas|halloween|"
    r"mouthwash|toothpaste|deodorant|shampoo|conditioner|soap|lotion|"
    r"listerine|colgate|crest|scope|dental|oral\s*care|"
    r"epsom\s*salt|magnesium\s*soak|bath\s*salt|body\s*soak|"
    r"throat\s*drops?|cough\s*drops?|cough\s*syrup|lozenges?|"
    r"oral\s*anesthetic|sore\s*throat|"
    r"water\s*softener|softener\s*salt|rust\s*remover|ice\s*melt|"
    r"non.?dairy\s*(?:half|creamer|coffee)|nutpods|"
    r"detergent|laundry|cleaner|cleaning|bleach|"
    r"vitamins?|supplements?|protein\s*(?:powder|shake|drink|bar)|"
    r"pet\s*food|cat\s*food|dog\s*food|bird\s*food|fish\s*food|"
    r"candle|fragrance|perfume|cologne|"
    r"decoration|decorat(?:ive|ion)|toy|gift\s*set)\b",
    re.I,
)


def toks(s: str) -> set[str]:
    return {t for t in WS.sub(" ", (s or "").lower()).split()
            if len(t) >= 2 and t not in STOP}


def cat_toks(path: str) -> set[str]:
    parts = re.split(r"[>/|]", path or "")
    out: set[str] = set()
    for p in parts:
        for t in WS.sub(" ", p.lower()).split():
            if len(t) >= 3 and t not in STOP and t not in {"home","page","food"}:
                out.add(t)
    return out


def main(dry_run: bool = True) -> int:
    t0 = time.time()
    print("loading consensus audit (one pass)...")
    # PID-level rollup: each unique PID gets a list of (axis_tokens, cat_tokens,
    # canonical, modifier, sr28, fndds) for its rows.
    pid_tokens_cache: dict[str, frozenset[str]] = {}
    pid_rows: dict[str, list[dict]] = defaultdict(list)

    with AUDIT.open() as f:
        for r in csv.DictReader(f):
            pid = (r.get("product_identity_fixed") or "").strip()
            canon = (r.get("canonical_path") or "").strip()
            if not pid or not canon:
                continue
            pid_lc = pid.lower()
            if pid_lc not in pid_tokens_cache:
                pid_tokens_cache[pid_lc] = frozenset(toks(pid_lc))
            row = {
                "pid": pid,
                "canonical": canon,
                "modifier": (r.get("modifier") or "").split(" > ")[0].strip(),
                "axis_tokens": toks(" ".join([
                    r.get("modifier") or "", r.get("flavor") or "",
                    r.get("form_texture_cut") or "", r.get("variant") or "",
                    r.get("processing_storage") or ""])),
                "cat_tokens": cat_toks(
                    r.get("category_path_fixed") or r.get("category_path_original") or ""),
                "sr28": (r.get("sr28_code") or "").strip(),
                "fndds": (r.get("fndds_code") or "").strip(),
            }
            pid_rows[pid_lc].append(row)
    print(f"  {sum(len(v) for v in pid_rows.values()):,} rows  →  "
          f"{len(pid_rows):,} unique PIDs in {time.time()-t0:.1f}s")

    # Pre-rank PIDs by token-length descending so longer (more specific) PIDs
    # are preferred when iterating
    pid_order = sorted(pid_tokens_cache.items(),
                       key=lambda kv: (-len(kv[1]), kv[0]))

    # Build the set of LAST-tokens-of-PIDs (what makes something a leaf
    # category, not just a flavor word). 'soda' is here because PID='Soda';
    # 'pop' is NOT here even though it appears inside 'Pop Tarts'.
    PID_LAST_TOKENS: set[str] = set()
    for pid_lc in pid_tokens_cache:
        last = pid_lc.split()[-1] if pid_lc else ""
        if last:
            PID_LAST_TOKENS.add(last)
    print(f"  PID last-token vocabulary: {len(PID_LAST_TOKENS):,} tokens")

    print("scanning priced_products (unbridged + LLM-mistagged)...")
    con = sqlite3.connect(str(PRICED_DB))
    con.row_factory = sqlite3.Row
    # Two pools:
    # 1. Truly unbridged rows (consensus_pid empty)
    # 2. Bridged rows where the existing PID's primary token isn't in the
    #    title — strong signal of LLM hallucination (Imperial Spread→Butter,
    #    Easter Eggs→Eggs, etc.)
    priced = list(con.execute("""
        SELECT rowid, name, category_path_walmart, category_path,
               consensus_pid AS existing_pid, bridge_status
        FROM priced_products
        WHERE non_food_path = 0 AND marketplace = 0 AND available = 1
          AND grams > 0 AND cents > 0
    """))
    candidates = []
    for r in priced:
        existing = (r["existing_pid"] or "").strip()
        if not existing:
            candidates.append(r)
            continue
        # Bridged row — keep ONLY if existing PID's primary token appears in title
        existing_toks = toks(existing)
        if not existing_toks:
            candidates.append(r)
            continue
        title_set = toks(r["name"] or "")
        if not (existing_toks & title_set):
            # Existing PID has zero tokens in title — likely hallucination
            candidates.append(r)
    priced = candidates
    print(f"  {len(priced):,} candidates (unbridged + suspect-bridged)")

    matched = no_match = nonfood = 0
    samples: list[dict] = []
    updates: list[tuple] = []

    t1 = time.time()
    for idx, p in enumerate(priced):
        if idx and idx % 20000 == 0:
            print(f"  ...{idx:,} processed  ({time.time()-t1:.1f}s, matched={matched:,})")

        name = p["name"] or ""
        if NON_FOOD_NAME.search(name):
            nonfood += 1; continue
        title_tok = toks(name)
        if not title_tok:
            no_match += 1; continue
        wm_cat_tok = cat_toks(p["category_path_walmart"] or p["category_path"] or "")

        # Get the title's TYPE token = the LAST title token that's also in the
        # PID vocabulary (i.e. a real food/product noun, not packaging or
        # brand). Walk right-to-left, skip numbers and unknown words.
        # "Lemon Lime Soda Pop, 12 fl oz, 12 Pack Cans" → 'soda' (soda is in
        # PID vocab; pop/cans/12 are not). "Apple Juice 64 fl oz" → 'juice'.
        title_token_list = [t for t in WS.sub(" ", name.lower()).split()
                            if len(t) >= 2 and t not in STOP]
        # For each title position, find the longest *contiguous* title
        # substring ending at that position that exactly matches a PID.
        # Pick the anchor with the longest contiguous match.
        # "Imperial Vegetable Oil Spread Sticks":
        #   pos sticks: contiguous match 'sticks' (1 tok)
        #   pos spread: contiguous match 'vegetable oil spread' (3 tok) ← winner
        # "Lemon Lime Mango Peach Soda Pop":
        #   pos pop:  no contiguous match
        #   pos soda: 'soda' (1 tok) ← winner
        #   pos peach: 'mango peach' or 'peach' — shorter
        # "Armour Chicken Vienna Sausage":
        #   pos sausage: 'vienna sausage' (2 tok contiguous) ← winner
        #     (NOT 'chicken sausage' — those tokens aren't contiguous)
        anchored_candidates: list[tuple[int, int, str]] = []
        for end_i in range(len(title_token_list)):
            end_tok = title_token_list[end_i]
            if end_tok.isdigit() or end_tok not in PID_LAST_TOKENS:
                continue
            # Try contiguous spans ending at end_i, longest first
            for span_len in range(min(end_i + 1, 5), 0, -1):
                start_i = end_i - span_len + 1
                span_toks = title_token_list[start_i:end_i + 1]
                # Skip if span contains stop-like fillers
                span_lc = " ".join(span_toks)
                if span_lc in pid_tokens_cache:
                    anchored_candidates.append((span_len, end_i, span_lc))
                    break
        best_pid_lc = None
        if anchored_candidates:
            # Longest contiguous wins; tiebreak by rightmost (later category)
            anchored_candidates.sort(key=lambda x: (-x[0], -x[1]))
            best_pid_lc = anchored_candidates[0][2]
        # Pass 2: longest-PID-subset fallback (current behavior).
        if best_pid_lc is None:
            for pid_lc, ptokens in pid_order:
                if not ptokens:
                    continue
                if ptokens.issubset(title_tok):
                    best_pid_lc = pid_lc
                    break
        if best_pid_lc is None:
            no_match += 1; continue

        # Step 3: among rows sharing this PID, pick the one whose axis tokens
        # match the title best, with category overlap as tiebreak.
        candidates = pid_rows[best_pid_lc]
        best_score = (-1, -1)
        best_row = candidates[0]
        for r in candidates:
            axis_overlap = len(r["axis_tokens"] & title_tok)
            cat_overlap = len(r["cat_tokens"] & wm_cat_tok)
            score = (axis_overlap, cat_overlap)
            if score > best_score:
                best_score = score
                best_row = r

        matched += 1
        updates.append((best_row["pid"], best_row["canonical"],
                        best_row["modifier"], best_row["sr28"],
                        best_row["fndds"], "title_match", p["rowid"]))
        if len(samples) < 30:
            samples.append({
                "title": name[:55],
                "pid": best_row["pid"],
                "canonical": best_row["canonical"],
                "modifier": best_row["modifier"],
                "score": best_score,
            })

    print(f"\n  matched: {matched:,}")
    print(f"  no PID match: {no_match:,}")
    print(f"  non-food rejected: {nonfood:,}")
    print(f"  bridge rate after: {(33424 + matched)/169441*100:.1f}%")
    print(f"  total time: {time.time()-t0:.1f}s")
    print()
    print("=== samples ===")
    for s in samples:
        print(f"  {s['title']:<57}  pid={s['pid']:<22}  mod={s['modifier'][:14]:<14}  "
              f"canon={s['canonical']}")

    if dry_run:
        print("\n[DRY RUN] not writing. Pass --apply to commit.")
        return 0

    cur = con.cursor()
    cur.executemany("""
        UPDATE priced_products SET
            consensus_pid = ?, consensus_canonical = ?, consensus_modifier = ?,
            consensus_sr28 = COALESCE(NULLIF(?, ''), consensus_sr28),
            consensus_fndds = COALESCE(NULLIF(?, ''), consensus_fndds),
            bridge_status = ?
        WHERE rowid = ?
    """, updates)
    con.commit()
    print(f"\n  applied {cur.rowcount:,} updates to priced_products")
    return 0


if __name__ == "__main__":
    dry = "--apply" not in sys.argv
    sys.exit(main(dry_run=dry))
