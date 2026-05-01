#!/usr/bin/env python3
"""Stage A3 — extract food entities from product titles using Dizex/FoodBaseBERT-NER.

Key fixes vs the earlier subword-fragment bug:
  - aggregation_strategy="first" instead of "simple"
  - we use the entity span's char offsets to slice the ORIGINAL string
    (so `##` subword artifacts never leak into the output)
  - lowercase before sending (Dizex was trained that way)

Output schema (parquet):
  fdc_id, title, food_spans  (pipe-delimited list)

Modes:
  python ner_extract.py --probe
  python ner_extract.py --run [--limit N]
"""
from __future__ import annotations
import argparse, csv, os, sys, time, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
RM   = REPO / "retail_mapper"
V2   = RM / "v2"
CACHE_DIR = V2 / ".cache"; CACHE_DIR.mkdir(parents=True, exist_ok=True)
INPUT_CSV = RM / "parsed_titles_enriched.csv"
OUT_PARQUET = CACHE_DIR / "ner_spans.parquet"

MODEL_NAME = "Dizex/FoodBaseBERT-NER"
HARD = [
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
    "PUMPKIN SPICE DAIRY FREE ALMONDMILK CREAMER",
    "VANILLA ALMONDMILK YOGURT ALTERNATIVE, VANILLA",
    "STRAWBERRY FLAVORED FRUIT ON THE BOTTOM ALMONDMILK YOGURT",
    "CHUNKY MONKEY ICE CREAM, CHOCOLATE FUDGE CHUNKS WITH WALNUTS",
    "RED PEPPER HUMMUS WITH FLATBREAD",
]

_PIPE = None
def _pipe():
    """Lazy load the NER pipeline."""
    global _PIPE
    if _PIPE is not None: return _PIPE
    from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
    import torch
    device = -1
    if torch.backends.mps.is_available(): device = "mps"
    elif torch.cuda.is_available(): device = 0
    print(f"  loading {MODEL_NAME} on device={device}")
    tok = AutoTokenizer.from_pretrained(MODEL_NAME)
    mdl = AutoModelForTokenClassification.from_pretrained(MODEL_NAME)
    _PIPE = pipeline(
        "ner", model=mdl, tokenizer=tok,
        aggregation_strategy="first",
        device=device,
    )
    return _PIPE

def extract_spans(text: str) -> list[str]:
    """Return cleaned multi-word food spans for a single title."""
    if not text: return []
    lc = text.lower()
    ents = _pipe()(lc)
    out = []
    for e in ents:
        # use offsets to slice from the original (lowercased) string
        s, t = int(e.get("start", 0)), int(e.get("end", 0))
        if t > s and t <= len(lc):
            span = lc[s:t]
        else:
            span = (e.get("word") or "").replace("##", "")
        # normalize
        span = span.strip(" -,.\"'")
        # collapse internal whitespace
        span = " ".join(span.split())
        if len(span) >= 3 and not span.startswith("#"):
            out.append(span)
    # dedupe preserving order
    seen = set(); deduped = []
    for s in out:
        if s not in seen: seen.add(s); deduped.append(s)
    return deduped

def extract_spans_batch(texts: list[str]) -> list[list[str]]:
    """Batched version. Lowercases inside."""
    lc = [t.lower() for t in texts]
    res = _pipe()(lc, batch_size=32)
    # transformers returns list[list[ent]] for list input
    if not res: return [[] for _ in texts]
    if isinstance(res[0], dict):  # single sentence form? wrap
        res = [res]
    out = []
    for txt, ents in zip(lc, res):
        spans = []
        for e in ents:
            s, t = int(e.get("start", 0)), int(e.get("end", 0))
            if t > s and t <= len(txt):
                span = txt[s:t]
            else:
                span = (e.get("word") or "").replace("##", "")
            span = " ".join(span.strip(" -,.\"'").split())
            if len(span) >= 3 and not span.startswith("#"):
                spans.append(span)
        seen = set(); ded = []
        for s in spans:
            if s not in seen: seen.add(s); ded.append(s)
        out.append(ded)
    return out

# --- modes -------------------------------------------------------------------

def probe():
    print("loading model...")
    _pipe()
    print("---")
    spans = extract_spans_batch(HARD)
    for t, s in zip(HARD, spans):
        print(f"{t!r}")
        print(f"   spans: {s}")
        print()

def run(limit: int | None = None):
    import pyarrow as pa, pyarrow.parquet as pq
    csv.field_size_limit(sys.maxsize)
    titles, fdcs = [], []
    with open(INPUT_CSV, errors='replace') as f:
        for r in csv.DictReader(f):
            titles.append(r.get("product_description") or "")
            fdcs.append(r.get("fdc_id") or "")
            if limit and len(titles) >= limit: break
    print(f"  {len(titles)} titles")
    _pipe()
    BATCH = 64
    rows = []
    t0 = time.time()
    for i in range(0, len(titles), BATCH):
        batch = titles[i:i+BATCH]
        spans_batch = extract_spans_batch(batch)
        for j, sps in enumerate(spans_batch):
            rows.append({
                "fdc_id":     fdcs[i+j],
                "title":      titles[i+j],
                "food_spans": "|".join(sps),
            })
        if (i + BATCH) % 5000 < BATCH:
            el = time.time() - t0
            n = i + BATCH
            print(f"  {n:>7}  ({el/60:.1f}m, {n/el:.0f}/s)", flush=True)
    el = time.time() - t0
    print(f"  done {len(rows)} ({el/60:.1f}m)")
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, OUT_PARQUET, compression="zstd")
    print(f"wrote {OUT_PARQUET}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--probe", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    a = p.parse_args()
    if a.probe: probe()
    elif a.run: run(a.limit)
    else: p.print_help()

if __name__ == "__main__":
    main()
