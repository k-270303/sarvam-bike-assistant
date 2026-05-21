from __future__ import annotations

import re
from hashlib import sha1

from backend.app.models import Chunk, ManualPage


HEADING_PATTERNS = [
    re.compile(r"^(?:chapter\s+)?\d+(?:\.\d+)*\s+[A-Z][^\n]{2,}$", re.I),
    re.compile(r"^[A-Z][A-Z\s/&-]{4,}$"),
]


def _looks_like_heading(line: str) -> bool:
    clean = line.strip()
    if len(clean) < 4 or len(clean) > 120:
        return False
    return any(pattern.match(clean) for pattern in HEADING_PATTERNS)


def _stable_chunk_id(document_name: str, page_start: int, text: str) -> str:
    digest = sha1(f"{document_name}:{page_start}:{text}".encode("utf-8")).hexdigest()
    return digest[:16]


def chunk_pages(
    pages: list[ManualPage],
    *,
    max_chars: int = 1200,
    overlap_chars: int = 180,
) -> list[Chunk]:
    """
    Build page-aware chunks while preserving detected section labels when possible.

    This intentionally prefers conservative, readable chunks over aggressive splitting:
    manuals often contain numbered procedures where mid-step splits hurt grounding.
    """
    chunks: list[Chunk] = []
    current_section = "Unlabeled section"

    for page in pages:
        lines = [line.strip() for line in page.text.splitlines() if line.strip()]
        if not lines:
            continue

        for line in lines[:8]:
            if _looks_like_heading(line):
                current_section = line
                break

        text = "\n".join(lines)
        start = 0
        while start < len(text):
            end = min(len(text), start + max_chars)
            if end < len(text):
                sentence_break = text.rfind(". ", start, end)
                newline_break = text.rfind("\n", start, end)
                preferred_break = max(sentence_break, newline_break)
                if preferred_break > start + int(max_chars * 0.6):
                    end = preferred_break + 1

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    Chunk(
                        chunk_id=_stable_chunk_id(
                            page.document_name, page.page_number, chunk_text
                        ),
                        document_name=page.document_name,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        section_title=current_section,
                        text=chunk_text,
                    )
                )

            if end >= len(text):
                break
            start = max(end - overlap_chars, start + 1)

    return chunks
