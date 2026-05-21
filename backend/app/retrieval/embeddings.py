from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

from backend.app.config import settings


class Embedder(ABC):
    @abstractmethod
    def embed_many(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_one(self, text: str) -> list[float]:
        return self.embed_many([text])[0]


class HashingEmbedder(Embedder):
    """
    Lightweight offline fallback.

    It is not a substitute for a trained semantic model, but it keeps tests and local
    development deterministic when sentence-transformers is not installed.
    """

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = text.lower().split()
        for token in tokens:
            digest = hashlib.sha1(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = -1.0 if digest[4] % 2 else 1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model_name: str = settings.embedding_model) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()


def build_embedder(backend: str) -> Embedder:
    if backend == "sentence-transformers":
        return SentenceTransformerEmbedder()
    return HashingEmbedder()
