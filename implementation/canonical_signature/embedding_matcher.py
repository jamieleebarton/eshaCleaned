from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Sequence
import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class EmbeddingMatcher:
    ids: list[str]
    id_to_idx: dict[str, int]
    embeddings: np.ndarray  # shape (n_corpus, dim), L2-normalized
    model: SentenceTransformer

    @classmethod
    def fit(cls, corpus: Iterable[tuple[str, str]]) -> "EmbeddingMatcher":
        items = list(corpus)
        ids = [i for i, _ in items]
        texts = [t for _, t in items]
        model = SentenceTransformer(MODEL_NAME)
        emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        emb = np.asarray(emb, dtype=np.float32)
        return cls(
            ids=ids,
            id_to_idx={i: idx for idx, i in enumerate(ids)},
            embeddings=emb,
            model=model,
        )

    def rerank(
        self, query: str, candidate_ids: Sequence[str], k: int = 5
    ) -> list[tuple[str, float]]:
        if not query.strip() or not candidate_ids:
            return []
        q = self.model.encode([query], normalize_embeddings=True, show_progress_bar=False)
        q = np.asarray(q, dtype=np.float32)[0]
        idxs = [self.id_to_idx[c] for c in candidate_ids if c in self.id_to_idx]
        if not idxs:
            return []
        sub = self.embeddings[idxs]
        sims = sub @ q  # cosine, since normalized
        order = np.argsort(sims)[::-1][:k]
        return [(candidate_ids[i], float(sims[i])) for i in order]
