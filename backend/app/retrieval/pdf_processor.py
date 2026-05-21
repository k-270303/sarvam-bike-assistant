from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader, PdfWriter

from backend.app.models import ManualPage


def extract_pdf_pages(document_name: str, pdf_bytes: bytes) -> list[ManualPage]:
    """Extract page text without persisting the uploaded PDF to disk."""
    reader = PdfReader(BytesIO(pdf_bytes))
    pages: list[ManualPage] = []
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        pages.append(
            ManualPage(
                document_name=document_name,
                page_number=index,
                text=text,
            )
        )
    return pages


def text_extraction_quality(pages: list[ManualPage]) -> float:
    if not pages:
        return 0.0
    non_empty = [page for page in pages if page.text.strip()]
    if not non_empty:
        return 0.0
    average_chars = sum(len(page.text) for page in non_empty) / len(pages)
    non_empty_ratio = len(non_empty) / len(pages)
    return min(1.0, (average_chars / 500.0) * 0.5 + non_empty_ratio * 0.5)


def page_needs_ocr(page: ManualPage, min_chars: int = 80) -> bool:
    normalized = " ".join(page.text.split())
    return len(normalized) < min_chars


def select_pages_for_ocr(pages: list[ManualPage]) -> list[ManualPage]:
    """
    Be conservative when a document already extracts well.

    - For generally healthy PDFs, only blank pages trigger OCR.
    - For poor extraction overall, short pages also trigger OCR because they are more
      likely to be scanned text pages that pypdf could not read.
    """
    if text_extraction_quality(pages) >= 0.6:
        return [page for page in pages if page_needs_ocr(page, min_chars=1)]
    return [page for page in pages if page_needs_ocr(page)]


def extract_single_page_pdf(pdf_bytes: bytes, page_number: int) -> bytes:
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.add_page(reader.pages[page_number - 1])
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
