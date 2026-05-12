"""Score every Product → ESHACode mapping using three independent 'views'.

Views:
  text   — embedding of (description + tokens) vs every ESHACode embedding
  graph  — average of nearby Product embeddings (same ProductCategory),
           projected against every ESHACode embedding
  label  — embedding of the assigned ESHACode itself, vs the product embedding

A mapping is suspect when the assigned code is far down the text view's ranking,
or when text + graph agree on a different code than the assigned label.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _stack(embeddings: dict[str, np.ndarray], ids: list[str]) -> np.ndarray:
    return np.vstack([embeddings[i] for i in ids])


def _rank_codes(query_vec: np.ndarray, code_ids: list[str], code_mat: np.ndarray) -> list[tuple[str, float]]:
    sims = code_mat @ query_vec  # cosine since both sides are L2-normalized
    order = np.argsort(-sims)
    return [(code_ids[i].split(":", 1)[1], float(sims[i])) for i in order]


def score_all(
    embeddings: dict[str, np.ndarray],
    products: pd.DataFrame,
    top_k_neighbors: int = 25,
) -> pd.DataFrame:
    """Score one row per product. Required `products` columns:
    gtin_upc, assigned_code, category, description (description unused, kept for context)."""
    code_ids = sorted(k for k in embeddings if k.startswith("ESHACode:"))
    code_mat = _stack(embeddings, code_ids)

    # Group product ids by category so we can compute the graph view efficiently.
    cat_to_pids: dict[str, list[str]] = {}
    for _, r in products.iterrows():
        pid = f"Product:{r['gtin_upc']}"
        if pid in embeddings:
            cat_to_pids.setdefault(r["category"], []).append(pid)

    rows = []
    for _, r in products.iterrows():
        gtin = r["gtin_upc"]
        assigned = r["assigned_code"]
        pid = f"Product:{gtin}"
        if pid not in embeddings:
            continue
        p_vec = embeddings[pid]

        text_ranking = _rank_codes(p_vec, code_ids, code_mat)
        text_top = text_ranking[0]
        text_view_code = text_top[0]

        # graph view: mean of up-to-K cosine-nearest products in same category
        cohort = [q for q in cat_to_pids.get(r["category"], []) if q != pid]
        if cohort:
            cohort_mat = _stack(embeddings, cohort)
            sims = cohort_mat @ p_vec
            keep = np.argsort(-sims)[:top_k_neighbors]
            g_vec = cohort_mat[keep].mean(axis=0)
            g_vec = g_vec / (np.linalg.norm(g_vec) or 1.0)
            graph_view_code = _rank_codes(g_vec, code_ids, code_mat)[0][0]
        else:
            graph_view_code = text_view_code

        # label view: assigned code's vector vs product vector
        assigned_key = f"ESHACode:{assigned}"
        if assigned_key in embeddings:
            label_sim = float(embeddings[assigned_key] @ p_vec)
        else:
            label_sim = 0.0
        label_view_code = assigned

        # Where does the assigned code rank in the text view? 1-indexed.
        try:
            assigned_rank = next(i for i, (c, _) in enumerate(text_ranking, start=1) if c == assigned)
        except StopIteration:
            assigned_rank = len(text_ranking) + 1

        # disagreement kind
        if assigned == text_view_code == graph_view_code:
            kind = "agree"
        elif text_view_code == graph_view_code and text_view_code != assigned:
            kind = "wrong_label"
        elif text_view_code != graph_view_code and (text_view_code == assigned or graph_view_code == assigned):
            kind = "bad_upstream"
        else:
            kind = "garbage"

        # suspicion: 0..1, dominated by assigned_rank, boosted on wrong_label
        rank_score = 1.0 - 1.0 / max(assigned_rank, 1)        # 0 at rank 1, →1 as rank grows
        label_score = max(0.0, 1.0 - label_sim)               # 0 if label hugs product
        kind_boost = {"agree": 0.0, "bad_upstream": 0.15, "wrong_label": 0.35, "garbage": 0.25}[kind]
        suspicion = float(min(1.0, 0.55 * rank_score + 0.20 * label_score + kind_boost))

        rows.append({
            "gtin_upc": gtin,
            "assigned_code": assigned,
            "assigned_rank": assigned_rank,
            "top1_code": text_top[0],
            "top1_score": text_top[1],
            "text_view_code": text_view_code,
            "graph_view_code": graph_view_code,
            "label_view_code": label_view_code,
            "label_view_sim": label_sim,
            "disagreement_kind": kind,
            "suspicion": suspicion,
        })

    return pd.DataFrame(rows)
