"""Build text strings per node and embed them with sentence-transformers.

Caches vectors on disk keyed by (model_name, content hash) so reruns are cheap.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

import kuzu
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "graph" / "cache" / "node_embeddings.npz"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _drain(result) -> Iterable[list]:
    while result.has_next():
        yield result.get_next()


def build_node_texts(conn: kuzu.Connection) -> dict[str, str]:
    """Return {node_id: text} for every Product, ESHACode, ProductCategory, ESHACategory.

    node_id format: '<NodeKind>:<primary_key>'.
    Product text = description + space-joined token values from HAS_TOKEN edges.
    ESHACode text = code + ' ' + description.
    Category texts = the name itself.
    """
    texts: dict[str, str] = {}

    q_products = (
        "MATCH (p:Product) "
        "OPTIONAL MATCH (p)-[:HAS_TOKEN]->(t:Token) "
        "RETURN p.gtin_upc, p.description, COLLECT(t.value) AS tokens"
    )
    for gtin, desc, tokens in _drain(conn.execute(q_products)):
        if isinstance(tokens, list):
            joined_tokens = " ".join(t for t in tokens if t)
        else:
            joined_tokens = (tokens or "")
        text = (desc or "").strip()
        if joined_tokens:
            text = (text + " " + joined_tokens).strip()
        if text:
            texts[f"Product:{gtin}"] = text

    for code, desc in _drain(conn.execute("MATCH (e:ESHACode) RETURN e.code, e.description")):
        text = f"{code} {desc or ''}".strip()
        if text:
            texts[f"ESHACode:{code}"] = text

    for (name,) in _drain(conn.execute("MATCH (c:ProductCategory) RETURN c.name")):
        if name:
            texts[f"ProductCategory:{name}"] = name

    for (name,) in _drain(conn.execute("MATCH (c:ESHACategory) RETURN c.name")):
        if name:
            texts[f"ESHACategory:{name}"] = name

    return texts


def _content_hash(model_name: str, texts: dict[str, str]) -> str:
    h = hashlib.sha256()
    h.update(model_name.encode("utf-8"))
    for key in sorted(texts):
        h.update(b"\x1f")
        h.update(key.encode("utf-8"))
        h.update(b"\x1e")
        h.update(texts[key].encode("utf-8"))
    return h.hexdigest()


def embed_all(
    conn: kuzu.Connection,
    model_name: str = DEFAULT_MODEL,
    cache_path: Path = CACHE_PATH,
) -> dict[str, np.ndarray]:
    """Return {node_id: vector}. Loads from cache when (model, texts) unchanged."""
    texts = build_node_texts(conn)
    digest = _content_hash(model_name, texts)

    if cache_path.exists():
        cached = np.load(cache_path, allow_pickle=False)
        if str(cached.get("digest", np.array("", dtype="<U1"))) == digest:
            ids = list(cached["ids"])
            vecs = cached["vectors"]
            return {ids[i]: vecs[i] for i in range(len(ids))}

    from sentence_transformers import SentenceTransformer  # lazy: heavy import
    model = SentenceTransformer(model_name)
    ids = sorted(texts)
    print(f"embedding {len(ids):,} nodes with {model_name}", flush=True)
    vectors = model.encode(
        [texts[i] for i in ids],
        batch_size=128,
        show_progress_bar=True,
        normalize_embeddings=True,
    ).astype(np.float32)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        cache_path,
        ids=np.array(ids),
        vectors=vectors,
        digest=np.array(digest),
    )
    return {ids[i]: vectors[i] for i in range(len(ids))}
