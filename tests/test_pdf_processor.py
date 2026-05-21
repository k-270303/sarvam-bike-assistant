from backend.app.models import ManualPage
from backend.app.retrieval.pdf_processor import page_needs_ocr, select_pages_for_ocr


def test_short_or_empty_pages_need_ocr() -> None:
    assert page_needs_ocr(ManualPage("manual.pdf", 1, ""))
    assert page_needs_ocr(ManualPage("manual.pdf", 2, "tiny"))


def test_text_rich_pages_skip_ocr() -> None:
    text = "Engine overheating troubleshooting procedure. " * 5
    assert not page_needs_ocr(ManualPage("manual.pdf", 3, text))


def test_healthy_documents_only_ocr_blank_pages() -> None:
    rich = ManualPage("manual.pdf", 1, "Troubleshooting procedure. " * 30)
    short_cover = ManualPage("manual.pdf", 2, "Owner Manual")
    blank = ManualPage("manual.pdf", 3, "")
    selected = select_pages_for_ocr([rich, short_cover, blank])
    assert selected == [blank]


def test_poor_documents_ocr_short_pages() -> None:
    pages = [
        ManualPage("manual.pdf", 1, ""),
        ManualPage("manual.pdf", 2, "tiny"),
    ]
    assert select_pages_for_ocr(pages) == pages
