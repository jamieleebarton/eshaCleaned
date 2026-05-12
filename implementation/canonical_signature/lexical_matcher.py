from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

CHAR_WEIGHT = 0.6
WORD_WEIGHT = 0.4


@dataclass
class LexicalMatcher:
    ids: list[str]
    char_vec: TfidfVectorizer
    word_vec: TfidfVectorizer
    char_matrix: object
    word_matrix: object

    @classmethod
    def fit(cls, corpus: Iterable[tuple[str, str]]) -> "LexicalMatcher":
        items = list(corpus)
        ids = [i for i, _ in items]
        texts = [t for _, t in items]
        char_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
        word_vec = TfidfVectorizer(analyzer="word", ngram_range=(1, 3))
        char_matrix = char_vec.fit_transform(texts)
        word_matrix = word_vec.fit_transform(texts)
        return cls(ids=ids, char_vec=char_vec, word_vec=word_vec,
                   char_matrix=char_matrix, word_matrix=word_matrix)

    def match(self, query: str, k: int = 5) -> list[tuple[str, float]]:
        if not query.strip():
            return []
        cq = self.char_vec.transform([query])
        wq = self.word_vec.transform([query])
        char_sim = cosine_similarity(cq, self.char_matrix)[0]
        word_sim = cosine_similarity(wq, self.word_matrix)[0]
        combined = CHAR_WEIGHT * char_sim + WORD_WEIGHT * word_sim
        if k >= len(combined):
            top_idx = np.argsort(combined)[::-1]
        else:
            top_idx = np.argpartition(combined, -k)[-k:]
            top_idx = top_idx[np.argsort(combined[top_idx])[::-1]]
        return [(self.ids[i], float(combined[i])) for i in top_idx]
