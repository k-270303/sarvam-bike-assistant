from backend.app.models import ManualPage
from backend.app.retrieval.chunking import chunk_pages


def test_chunking_preserves_page_metadata() -> None:
    chunks = chunk_pages(
        [
            ManualPage(
                document_name="manual.pdf",
                page_number=7,
                text="3.2 TROUBLESHOOTING\nEngine does not start. Check battery terminals.",
            )
        ],
        max_chars=80,
    )
    assert chunks
    assert chunks[0].document_name == "manual.pdf"
    assert chunks[0].page_start == 7
    assert chunks[0].section_title == "3.2 TROUBLESHOOTING"

