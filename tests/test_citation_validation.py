from backend.app.models import Chunk, Citation, SearchHit
from backend.app.response.citation_validation import citation_is_supported


def test_citation_must_be_exactly_supported_by_retrieved_chunk() -> None:
    chunk = Chunk(
        chunk_id="1",
        document_name="manual.pdf",
        page_start=3,
        page_end=3,
        section_title="Oil",
        text="Low Oil Pressure Indicator: It glows when engine oil pressure is low.",
    )
    hit = SearchHit(chunk=chunk, lexical_score=1, semantic_score=1, combined_score=1)
    valid = Citation(
        document_name="manual.pdf",
        page_start=3,
        page_end=3,
        section_title="Oil",
        excerpt="It glows when engine oil pressure is low.",
    )
    invalid = Citation(
        document_name="manual.pdf",
        page_start=3,
        page_end=3,
        section_title="Oil",
        excerpt="It means the oil pump has failed.",
    )
    assert citation_is_supported(valid, [hit])
    assert not citation_is_supported(invalid, [hit])

