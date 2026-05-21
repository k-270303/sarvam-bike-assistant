from __future__ import annotations

from backend.app.models import SearchHit


def score_confidence(hits: list[SearchHit], ambiguity_level: float) -> float:
    if not hits:
        return 0.0

    top_score = hits[0].combined_score
    supporting_hits = sum(1 for hit in hits if hit.combined_score >= 0.55)
    lexical_support = max(hit.lexical_score for hit in hits)
    confidence = (
        0.45 * top_score
        + 0.2 * min(1.0, supporting_hits / 3)
        + 0.2 * lexical_support
        + 0.15 * (1 - ambiguity_level)
    )
    return round(max(0.0, min(1.0, confidence)), 4)


def confidence_level(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"

