from __future__ import annotations

import re

from backend.app.models import Citation, SearchHit


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def citation_is_supported(citation: Citation, hits: list[SearchHit]) -> bool:
    excerpt = _normalize(citation.excerpt)
    if not excerpt:
        return False
    for hit in hits:
        chunk = hit.chunk
        if citation.document_name != chunk.document_name:
            continue
        if citation.page_start < chunk.page_start or citation.page_end > chunk.page_end:
            continue
        if excerpt in _normalize(chunk.text):
            return True
    return False


def filter_supported_citations(
    citations: list[Citation], hits: list[SearchHit]
) -> list[Citation]:
    return [
        citation
        for citation in citations
        if citation_is_supported(citation, hits)
    ]

