#!/usr/bin/env python3
"""Recipe ingredient -> Hestia identity code matcher (v2).

Wires the IDENTITY_CODING_SYSTEM_DESIGN.md coding system into the matcher.

Pipeline:
  1. Load identity_registry.json (10,525 codes from consensus_full_corpus_audit).
  2. For each registry entry, build a search text:
       "<product_identity_fixed> | <canonical_path tail> | <modal BFC> | <one sample title>"
  3. Embed both the registry texts and recipe ingredient items.
  4. Cosine top-K against the registry.
  5. Apply preference re-rank:
       (a) +0.10 bonus if product_identity_fixed token-equals the stripped query
           (fixes "milk" -> "Milkshake", "butter" -> "Dairy>Cheese>Butter").
       (b) +0.04 bonus if canonical_path's domain matches a query-domain hint
           (e.g. "salt" -> Pantry>Spices, not Snack>Jerky).
  6. Extract modifier signal from the query against the code's known_modifiers
     vocabulary (Rule A: ignored; Rule B/C: appended to compact code).

Output columns:
  item, recipe_count, identity_code, rule, canonical_path,
  product_identity_fixed, modifier, modal_fndds_code, modal_fndds_desc,
  modal_sr28_code, modal_sr28_desc, modal_retail_leaf_path, has_portions,
  similarity, top_k
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_REG = HERE / "output" / "identity_registry.json"
DEFAULT_ITEMS = HERE / "output" / "recipe_ingredient_items.csv"
DEFAULT_OUT = HERE / "output" / "recipe_ingredient_identity_codes.csv"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Tokens that strongly hint a domain. Used for the soft re-rank bonus only.
DOMAIN_HINTS = {
    "salt": "P", "pepper": "P", "cinnamon": "P", "cumin": "P", "paprika": "P",
    "nutmeg": "P", "saffron": "P", "oregano": "P", "thyme": "P", "basil": "P",
    "rosemary": "P", "sage": "P", "turmeric": "P", "ginger": "R",
    "milk": "D", "butter": "D", "cream": "D", "cheese": "D", "yogurt": "D",
    "egg": "D", "eggs": "D",
    "rice": "P", "flour": "P", "sugar": "P", "honey": "P", "syrup": "P",
    "oil": "P", "vinegar": "P",
    "chicken": "M", "beef": "M", "pork": "M", "salmon": "M", "shrimp": "M",
    "tomato": "R", "tomatoes": "R", "onion": "R", "onions": "R",
    "garlic": "R", "carrot": "R", "carrots": "R",
    "blueberries": "R", "strawberries": "R", "raspberries": "R",
    "blackberries": "R", "apples": "R", "lemon": "R", "lemons": "R",
    "lime": "R", "limes": "R",
    "parsley": "R", "cilantro": "R", "mint": "R",
    "soy": "P", "sauce": "P",
}

WS = re.compile(r"\s+")
NONALPHA = re.compile(r"[^a-z0-9]+")


def log(t0: float, m: str) -> None:
    print(f"[{time.time() - t0:6.1f}s] {m}", flush=True)


def l2(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return x / n


def normalize_text(s: str) -> str:
    s = (s or "").lower()
    s = NONALPHA.sub(" ", s).strip()
    return WS.sub(" ", s)


def tokens(s: str) -> set[str]:
    return set(normalize_text(s).split())


def registry_search_text(e: dict) -> str:
    pid = e.get("product_identity_fixed") or ""
    pmod = e.get("primary_modifier") or ""
    cp = e.get("canonical_path") or ""
    bfc = e.get("modal_branded_food_category") or ""
    titles = e.get("sample_titles") or []
    tail = " ".join(cp.split(" > ")[-2:]) if cp else ""
    one_title = titles[0] if titles else ""
    # For Rule B nodes the primary modifier IS the type, so put it FIRST
    # so the embedding represents "Cloves", not "Spice Blend".
    if pmod and (e.get("rule") == "B"):
        head = pmod
    else:
        head = pid
    parts = [head, pid if head != pid else "", tail, bfc, one_title]
    return " | ".join(p for p in parts if p)


def query_domain_hint(q: str) -> str:
    q_tokens = tokens(q)
    for tok in q_tokens:
        if tok in DOMAIN_HINTS:
            return DOMAIN_HINTS[tok]
    return ""


def extract_modifier(q: str, known_modifiers: list[list]) -> str:
    """Pick the longest known modifier (case-insensitive) that occurs in q.
    `known_modifiers` is [[modifier_string, count], ...]."""
    if not known_modifiers:
        return ""
    qn = " " + normalize_text(q) + " "
    best = ""
    for mod, _ in known_modifiers:
        mn = " " + normalize_text(mod) + " "
        if mn.strip() and mn in qn and len(mn) > len(best):
            best = mn
    return best.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", type=Path, default=DEFAULT_REG)
    ap.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--bare-noun-bonus", type=float, default=0.10)
    ap.add_argument("--domain-hint-bonus", type=float, default=0.04)
    args = ap.parse_args()

    t0 = time.time()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    with args.registry.open() as f:
        reg = json.load(f)
    log(t0, f"registry codes: {len(reg):,}")

    items = pd.read_csv(args.items).fillna("")
    if args.limit > 0:
        items = items.head(args.limit).copy()
    log(t0, f"ingredients: {len(items):,}")

    reg_texts = [registry_search_text(e) for e in reg]
    pid_lc = [normalize_text(e.get("product_identity_fixed") or "") for e in reg]
    domain_codes = [e.get("domain_code") or "" for e in reg]

    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(args.model)
    log(t0, "embedding registry")
    reg_emb = l2(m.encode(reg_texts, batch_size=512, show_progress_bar=False,
                          convert_to_numpy=True).astype(np.float32))
    log(t0, "embedding ingredient items")
    ing_emb = l2(m.encode(items["item"].astype(str).tolist(),
                          batch_size=512, show_progress_bar=False,
                          convert_to_numpy=True).astype(np.float32))

    log(t0, "cosine + re-rank")
    sims = ing_emb @ reg_emb.T

    queries = items["item"].astype(str).tolist()
    q_norm = [normalize_text(q) for q in queries]
    q_hints = [query_domain_hint(q) for q in queries]

    # Apply re-rank bonuses (vectorized where possible).
    pid_lc_arr = np.array(pid_lc, dtype=object)
    domain_arr = np.array(domain_codes, dtype=object)

    bonuses = np.zeros_like(sims)
    for i, qn in enumerate(q_norm):
        # bare-noun bonus when product_identity exactly equals the query
        bonuses[i] += (pid_lc_arr == qn).astype(np.float32) * args.bare_noun_bonus
        # domain-hint bonus
        h = q_hints[i]
        if h:
            bonuses[i] += (domain_arr == h).astype(np.float32) * args.domain_hint_bonus

    sims_rr = sims + bonuses
    k = args.top_k
    top_idx = np.argpartition(-sims_rr, kth=min(k, sims_rr.shape[1] - 1), axis=1)[:, :k]
    rs = np.arange(sims_rr.shape[0])[:, None]
    order = np.argsort(-sims_rr[rs, top_idx], axis=1)
    top_idx = top_idx[rs, order]
    top_scores = sims_rr[rs, top_idx]
    base_scores = sims[rs, top_idx]

    out_rows = []
    for i, q in enumerate(queries):
        best = top_idx[i, 0]
        e = reg[best]
        rule = e.get("rule") or "A"
        modifier = ""
        if rule in ("B", "C"):
            modifier = extract_modifier(q, e.get("known_modifiers") or [])
        # Compose final identity code (registry code already has no modifier;
        # we append for B/C only when extracted).
        code = e.get("code") or ""
        if modifier and rule in ("B", "C"):
            from build_identity_registry import to_camel  # type: ignore
            code = code + "." + to_camel(modifier)

        topk = " || ".join(
            f"{reg[top_idx[i,j]]['code']} :: {reg[top_idx[i,j]]['canonical_path']} > "
            f"{reg[top_idx[i,j]]['product_identity_fixed']} :: "
            f"sim={base_scores[i,j]:.3f} (+{top_scores[i,j]-base_scores[i,j]:.2f})"
            for j in range(k)
        )

        row = items.iloc[i].to_dict()
        row.update({
            "identity_code": code,
            "rule": rule,
            "canonical_path": e.get("canonical_path") or "",
            "product_identity_fixed": e.get("product_identity_fixed") or "",
            "modifier": modifier,
            "modal_fndds_code": e.get("modal_fndds_code") or "",
            "modal_fndds_desc": e.get("modal_fndds_desc") or "",
            "modal_sr28_code": e.get("modal_sr28_code") or "",
            "modal_sr28_desc": e.get("modal_sr28_desc") or "",
            "modal_retail_leaf_path": e.get("modal_retail_leaf_path") or "",
            "has_portions": e.get("has_portions") or False,
            "similarity": float(top_scores[i, 0]),
            "base_similarity": float(base_scores[i, 0]),
            "top_k": topk,
        })
        out_rows.append(row)

    df_out = pd.DataFrame(out_rows)
    df_out.to_csv(args.out, index=False, quoting=csv.QUOTE_MINIMAL)
    log(t0, f"wrote {args.out} ({len(df_out):,} rows)")

    s = df_out["similarity"]
    print(f"  median sim={s.median():.3f}  >=0.50={(s>=0.50).mean():.1%}  "
          f">=0.75={(s>=0.75).mean():.1%}  has_portions={df_out['has_portions'].mean():.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
