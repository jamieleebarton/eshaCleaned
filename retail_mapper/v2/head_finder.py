#!/usr/bin/env python3
"""Stage A2 — extract syntactic head + modifier structure from product titles.

For every product title we compute four spans:
  head_phrase       : the noun phrase the title is ABOUT
                      (rightmost noun-chunk, or ROOT noun, walking the
                      compound chain to capture multi-word heads like
                      "almond nog beverage", "taco meal kit", "sandwich spread")
  compound_prefix   : adjective/compound modifiers attached to the head
                      ("unsweetened", "chocolate", "smoky") — flavor/claim signal
  pp_components     : tokens inside "with ..." / "in ..." / "of ..."
                      prepositional phrases — these are INGREDIENTS/COMPONENTS,
                      not the product itself (combo-kit fix)
  comma_tail        : after the FIRST comma — usually a marketing restatement of
                      the title ("CHOCOLATE ALMONDMILK, CHOCOLATE") which the
                      flat-token parser was double-counting

Run-modes:
  python head_finder.py --probe          # run on hard-pair examples, print
  python head_finder.py --run            # run on parsed_titles_enriched.csv
                                         # → head_phrases.parquet
  python head_finder.py --run --limit N  # smoke test on first N rows
"""
from __future__ import annotations
import argparse, csv, os, re, sys, time
from pathlib import Path

REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
RM   = REPO / "retail_mapper"
V2   = RM / "v2"
CACHE_DIR = V2 / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
INPUT_CSV = RM / "parsed_titles_enriched.csv"
OUT_PARQUET = CACHE_DIR / "head_phrases.parquet"

PP_PREPS = {"with", "in", "of", "for"}

HARD_PAIRS = [
    "BEYOND MEAT TACOS WITH SMOKY CHIPOTLE-LIME MAYO MEAL KIT",
    "Bush's Hot Honey Grillin' Beans 55oz",
    "ALMOND NOG NON-DAIRY BEVERAGE, ALMOND NOG",
    "OAT NOG FLAVORED OATMILK DRINK",
    "Chipotle Aioli",
    "CHIPOTLE MAYO STYLE SANDWICH SPREAD, CHIPOTLE",
    "UNSWEETENED CHOCOLATE ALMONDMILK, UNSWEETENED CHOCOLATE",
    "HOT HONEY GOUDA CHEESE",
    "HINT OF PUMPKIN SPICE FLAVORED ALMONDMILK",
    "CALIFIA FARMS COLD BREW COFFEE WITH ALMONDMILK SALTED CARAMEL",
    "Original Almond Beverage, Original",
    "PUMPKIN SPICE DAIRY FREE ALMONDMILK CREAMER",
    "VANILLA ALMONDMILK YOGURT ALTERNATIVE, VANILLA",
    "STRAWBERRY FLAVORED FRUIT ON THE BOTTOM ALMONDMILK YOGURT",
]

_NLP = None
def _nlp():
    global _NLP
    if _NLP is None:
        import spacy
        _NLP = spacy.load("en_core_web_sm")
    return _NLP

# --- helpers -----------------------------------------------------------------

_PACK_RE = re.compile(
    r"\b(\d+(?:\.\d+)?\s*(?:fl)?\s*(?:oz|ml|l|ct|count|pk|pack|kg|g|lb|lbs))\b"
    r"|\b\d+\s*-\s*\d+(?:fl)?\s*(?:oz|ml|l|ct|pk|pack)\b",
    re.IGNORECASE,
)

def split_comma_tail(text: str) -> tuple[str, str]:
    """Return (main, tail). The tail is everything after the FIRST comma if
    the tail is a near-restatement of the head (typical "X, X" pattern)."""
    if "," not in text: return text, ""
    main, _, tail = text.partition(",")
    main = main.strip(); tail = tail.strip()
    if not tail: return main, ""
    main_tokens = set(re.findall(r"[a-z]+", main.lower()))
    tail_tokens = set(re.findall(r"[a-z]+", tail.lower()))
    if not tail_tokens: return main, ""
    overlap = len(main_tokens & tail_tokens) / max(1, len(tail_tokens))
    if overlap >= 0.6:
        return main, tail
    return text, ""

def strip_pack_format(text: str) -> str:
    return _PACK_RE.sub("", text).strip()

def expand_compound_chain(token):
    """Walk left-children compounds to capture multi-word noun like
    'oatmilk drink' or 'almond nog beverage' or 'taco meal kit'."""
    parts = [token.text]
    seen = {token.i}
    cur = token
    while True:
        comp = next((c for c in cur.lefts if c.dep_ == "compound" and c.i not in seen), None)
        if not comp: break
        parts.insert(0, comp.text)
        seen.add(comp.i); cur = comp
    return " ".join(parts).strip(), seen

def find_head_phrase(doc):
    """Pick the syntactic head of the product title, walking compound chains."""
    if len(doc) == 0:
        return "", set(), []
    # 1) prefer a content noun-chunk that is NOT inside a "with"/"in"/"of" PP
    pp_tokens = set()
    for tok in doc:
        if tok.dep_ == "prep" and tok.text in PP_PREPS:
            for sub in tok.subtree:
                pp_tokens.add(sub.i)
    main_chunks = [c for c in doc.noun_chunks if c.root.i not in pp_tokens]
    chunks = main_chunks or list(doc.noun_chunks)
    head_tok = None
    if chunks:
        # pick the LAST main chunk (English compounds are right-headed)
        head_tok = chunks[-1].root
    # 2) fall back to ROOT
    if head_tok is None or head_tok.pos_ in ("ADP", "VERB", "AUX"):
        root = next((t for t in doc if t.dep_ == "ROOT"), None)
        if root is not None and root.pos_ in ("NOUN", "PROPN"):
            head_tok = root
        else:
            # final fallback: rightmost noun in the doc
            nouns = [t for t in doc if t.pos_ in ("NOUN", "PROPN")]
            head_tok = nouns[-1] if nouns else doc[-1]
    head_phrase, head_idx = expand_compound_chain(head_tok)
    return head_phrase, head_idx, sorted(pp_tokens)

def extract(text: str) -> dict:
    """Run on a single title. Returns dict with the four spans + meta."""
    raw = text or ""
    main, comma_tail = split_comma_tail(raw)
    main = strip_pack_format(main)
    doc = _nlp()(main.lower())

    head_phrase, head_idx, pp_token_idxs = find_head_phrase(doc)

    # compound_prefix: NOUN/ADJ tokens to the LEFT of the head that aren't pp_tokens
    if head_idx:
        head_min = min(head_idx)
        prefix_tokens = [
            t.text for t in doc
            if t.i < head_min
            and t.i not in pp_token_idxs
            and t.pos_ in ("ADJ", "NOUN", "PROPN")
            and not t.is_stop
        ]
    else:
        prefix_tokens = []
    compound_prefix = " ".join(prefix_tokens).strip()

    # pp_components grouped per preposition
    pp_components = []
    for prep_tok in doc:
        if prep_tok.dep_ == "prep" and prep_tok.text in PP_PREPS:
            phrase = " ".join(c.text for c in prep_tok.subtree if c.i != prep_tok.i)
            phrase = re.sub(r"\s+", " ", phrase).strip(" -,.")
            if phrase:
                pp_components.append({"prep": prep_tok.text, "phrase": phrase})

    return {
        "title":           raw,
        "main":            main,
        "comma_tail":      comma_tail,
        "head_phrase":     head_phrase,
        "compound_prefix": compound_prefix,
        "pp_components":   pp_components,
        "head_idx":        sorted(head_idx),
    }

# --- modes -------------------------------------------------------------------

def probe():
    print(f"loading spaCy en_core_web_sm...")
    _nlp()
    print(f"---")
    for t in HARD_PAIRS:
        out = extract(t)
        pps = "; ".join(f"{p['prep']}: {p['phrase']!r}" for p in out["pp_components"]) or "(none)"
        print(f"{t!r}")
        print(f"   head        : {out['head_phrase']!r}")
        print(f"   prefix      : {out['compound_prefix']!r}")
        print(f"   pp          : {pps}")
        print(f"   comma_tail  : {out['comma_tail']!r}")
        print()

def run(limit: int | None = None):
    """Run on every product in parsed_titles_enriched.csv, write parquet."""
    import pyarrow as pa, pyarrow.parquet as pq
    import json as _json
    csv.field_size_limit(sys.maxsize)
    print(f"loading spaCy ..."); nlp = _nlp()
    print(f"reading {INPUT_CSV}")
    titles, fdcs = [], []
    with open(INPUT_CSV, errors='replace') as f:
        for r in csv.DictReader(f):
            titles.append(r.get("product_description") or "")
            fdcs.append(r.get("fdc_id") or "")
            if limit and len(titles) >= limit: break
    print(f"  {len(titles)} titles")

    # tokenize+parse via nlp.pipe for speed; lowercase first
    t0 = time.time()
    rows = []
    BATCH = 256
    for i, doc in enumerate(nlp.pipe(
        ((strip_pack_format(split_comma_tail(t)[0])).lower() for t in titles),
        batch_size=BATCH, n_process=1
    )):
        raw = titles[i]
        _, comma_tail = split_comma_tail(raw)
        head_phrase, head_idx, pp_token_idxs = find_head_phrase(doc)
        if head_idx:
            head_min = min(head_idx)
            prefix_tokens = [
                t.text for t in doc
                if t.i < head_min and t.i not in pp_token_idxs
                and t.pos_ in ("ADJ", "NOUN", "PROPN") and not t.is_stop
            ]
        else:
            prefix_tokens = []
        pp_components = []
        for prep_tok in doc:
            if prep_tok.dep_ == "prep" and prep_tok.text in PP_PREPS:
                phrase = " ".join(c.text for c in prep_tok.subtree if c.i != prep_tok.i)
                phrase = re.sub(r"\s+", " ", phrase).strip(" -,.")
                if phrase:
                    pp_components.append(f"{prep_tok.text}:{phrase}")
        rows.append({
            "fdc_id":          fdcs[i],
            "title":           raw,
            "head_phrase":     head_phrase,
            "compound_prefix": " ".join(prefix_tokens),
            "pp_components":   "|".join(pp_components),
            "comma_tail":      comma_tail,
        })
        if (i + 1) % 25_000 == 0:
            el = time.time() - t0
            print(f"  {i+1:>7}  ({el/60:.1f}m, {(i+1)/el:.0f}/s)")
    el = time.time() - t0
    print(f"  done {len(rows)} ({el/60:.1f}m)")

    table = pa.Table.from_pylist(rows)
    pq.write_table(table, OUT_PARQUET, compression="zstd")
    print(f"wrote {OUT_PARQUET}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--probe", action="store_true")
    p.add_argument("--run",   action="store_true")
    p.add_argument("--limit", type=int, default=None)
    a = p.parse_args()
    if a.probe: probe()
    elif a.run: run(a.limit)
    else: p.print_help()

if __name__ == "__main__":
    main()
