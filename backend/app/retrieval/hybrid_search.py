from __future__ import annotations

import math
from dataclasses import dataclass

from backend.app.config import settings
from backend.app.models import Chunk, SearchHit
from backend.app.retrieval.bm25 import BM25Index
from backend.app.retrieval.embeddings import Embedder, build_embedder
from backend.app.retrieval.query_expansion import expand_query, expansion_token_overlap


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left)) or 1.0
    right_norm = math.sqrt(sum(value * value for value in right)) or 1.0
    return numerator / (left_norm * right_norm)


def _retrieval_text(chunk: Chunk) -> str:
    return f"{chunk.document_name}\n{chunk.section_title}\n{chunk.text}"


def _model_hint_score(model_hints: list[str], chunk: Chunk) -> float:
    if not model_hints:
        return 0.0
    document = chunk.document_name.lower().replace("_", " ").replace("-", " ")
    section = chunk.section_title.lower().replace("_", " ").replace("-", " ")
    haystack = f"{document} {section}"
    return 1.0 if any(hint.lower() in haystack for hint in model_hints) else 0.0


@dataclass
class HybridIndex:
    chunks: list[Chunk]
    lexical: BM25Index
    embeddings: list[list[float]]
    embedder: Embedder

    @classmethod
    def from_chunks(cls, chunks: list[Chunk]) -> "HybridIndex":
        embedder = build_embedder(settings.embedding_backend)
        texts = [_retrieval_text(chunk) for chunk in chunks]
        return cls(
            chunks=chunks,
            lexical=BM25Index(texts),
            embeddings=embedder.embed_many(texts),
            embedder=embedder,
        )

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        expanded = expand_query(query)
        lexical_scores = self.lexical.score(expanded.expanded_text)
        query_embedding = self.embedder.embed_one(expanded.expanded_text)
        semantic_scores = [
            cosine_similarity(query_embedding, embedding)
            for embedding in self.embeddings
        ]

        lexical_max = max(lexical_scores, default=0.0) or 1.0
        semantic_min = min(semantic_scores, default=0.0)
        semantic_max = max(semantic_scores, default=1.0)
        semantic_range = semantic_max - semantic_min or 1.0

        hits: list[SearchHit] = []
        for chunk, lexical_score, semantic_score in zip(
            self.chunks, lexical_scores, semantic_scores
        ):
            lexical_norm = lexical_score / lexical_max
            semantic_norm = (semantic_score - semantic_min) / semantic_range
            retrieval_text = _retrieval_text(chunk)
            expansion_overlap = expansion_token_overlap(expanded, retrieval_text)
            model_boost = _model_hint_score(expanded.model_hints, chunk)
            combined = (
                0.44 * lexical_norm
                + 0.25 * semantic_norm
                + 0.21 * expansion_overlap
                + 0.10 * model_boost
            )
            hits.append(
                SearchHit(
                    chunk=chunk,
                    lexical_score=lexical_norm,
                    semantic_score=semantic_norm,
                    combined_score=min(1.0, combined),
                )
            )

        return sorted(hits, key=lambda hit: hit.combined_score, reverse=True)[:top_k]
