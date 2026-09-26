"""Pure-Python BM25 (Okapi). Drop-in for rank_bm25.BM25Okapi's `get_scores`, without numpy
(which added 68 MB to every serverless deployment)."""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence


class BM25Okapi:
    def __init__(self, corpus: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75, epsilon: float = 0.25):
        self.k1, self.b, self.epsilon = k1, b, epsilon
        self.docs = [Counter(d) for d in corpus]
        self.doc_len = [len(d) for d in corpus]
        self.n = len(corpus)
        self.avgdl = (sum(self.doc_len) / self.n) if self.n else 0.0
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(d.keys())
        self.idf: dict[str, float] = {}
        neg = []
        total = 0.0
        for term, freq in df.items():
            idf = math.log((self.n - freq + 0.5) / (freq + 0.5))
            self.idf[term] = idf
            total += idf
            if idf < 0:
                neg.append(term)
        avg_idf = (total / len(self.idf)) if self.idf else 0.0
        for term in neg:  # rank_bm25 floors negative idf at epsilon * average idf
            self.idf[term] = self.epsilon * avg_idf

    def get_scores(self, query: Iterable[str]) -> list[float]:
        scores = [0.0] * self.n
        if not self.n:
            return scores
        for term in query:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, d in enumerate(self.docs):
                f = d.get(term, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                scores[i] += idf * (f * (self.k1 + 1)) / denom
        return scores

    def get_top_n(self, query: Iterable[str], documents: Sequence, n: int = 5):
        scores = self.get_scores(query)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n]
        return [documents[i] for i in order]
