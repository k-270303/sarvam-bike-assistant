from __future__ import annotations

import math
import re
from collections import Counter


TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


class BM25Index:
    """Tiny dependency-free BM25 implementation suitable for session-local corpora."""

    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.documents = [tokenize(document) for document in documents]
        self.doc_freqs = [Counter(document) for document in self.documents]
        self.doc_lengths = [len(document) for document in self.documents]
        self.avg_doc_length = sum(self.doc_lengths) / max(1, len(self.doc_lengths))
        self.term_document_counts: Counter[str] = Counter()
        for document in self.documents:
            self.term_document_counts.update(set(document))
        self.document_count = len(self.documents)

    def score(self, query: str) -> list[float]:
        query_terms = tokenize(query)
        scores: list[float] = []
        for index, frequencies in enumerate(self.doc_freqs):
            doc_len = self.doc_lengths[index]
            score = 0.0
            for term in query_terms:
                if term not in frequencies:
                    continue
                df = self.term_document_counts[term]
                idf = math.log(1 + (self.document_count - df + 0.5) / (df + 0.5))
                tf = frequencies[term]
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * doc_len / max(self.avg_doc_length, 1)
                )
                score += idf * (tf * (self.k1 + 1)) / denominator
            scores.append(score)
        return scores

