from backend.app.models import Chunk, SearchHit
from backend.app.reasoning.confidence import confidence_level, score_confidence


def test_low_confidence_without_hits() -> None:
    assert score_confidence([], ambiguity_level=0.2) == 0.0
    assert confidence_level(0.0) == "low"


def test_confidence_rises_with_support() -> None:
    chunk = Chunk(
        chunk_id="a",
        document_name="manual.pdf",
        page_start=1,
        page_end=1,
        section_title="Troubleshooting",
        text="Check the battery terminals.",
    )
    hits = [
        SearchHit(chunk=chunk, lexical_score=1.0, semantic_score=0.9, combined_score=0.9),
        SearchHit(chunk=chunk, lexical_score=0.8, semantic_score=0.7, combined_score=0.8),
        SearchHit(chunk=chunk, lexical_score=0.7, semantic_score=0.7, combined_score=0.7),
    ]
    assert score_confidence(hits, ambiguity_level=0.1) >= 0.75

