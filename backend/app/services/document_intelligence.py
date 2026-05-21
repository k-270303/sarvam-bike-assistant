from __future__ import annotations

import html
import json
import re
import tempfile
import zipfile
from pathlib import Path

from sarvamai import SarvamAI

from backend.app.config import settings
from backend.app.errors import AppError


TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(raw_html: str) -> str:
    no_tags = TAG_RE.sub(" ", raw_html)
    return WHITESPACE_RE.sub(" ", html.unescape(no_tags)).strip()


def _extract_text_from_zip(zip_path: Path) -> str:
    candidates: list[str] = []
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.namelist():
                lower_name = member.lower()
                if lower_name.endswith(".html"):
                    candidates.append(_strip_html(archive.read(member).decode("utf-8")))
                elif lower_name.endswith((".md", ".txt")):
                    candidates.append(archive.read(member).decode("utf-8").strip())
                elif lower_name.endswith(".json"):
                    payload = json.loads(archive.read(member).decode("utf-8"))
                    candidates.append(json.dumps(payload))
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(
            code="ocr_output_unreadable",
            user_message="OCR completed, but I could not read the processed output. Please try another PDF or a clearer scan.",
            status_code=422,
            internal_detail=str(exc),
        ) from exc
    return max(candidates, key=len, default="")


class DocumentIntelligenceClient:
    """Temporary-file bridge around Sarvam's document job API."""

    def __init__(self) -> None:
        if not settings.sarvam_api_key:
            raise AppError(
                code="sarvam_not_configured",
                user_message="OCR is not configured because the Sarvam API key is missing.",
                status_code=503,
            )
        self.client = SarvamAI(api_subscription_key=settings.sarvam_api_key)

    def ocr_pdf_bytes(self, pdf_bytes: bytes, language: str = "en-IN") -> str:
        try:
            with tempfile.TemporaryDirectory(prefix="sarvam-ocr-") as temp_dir:
                temp_path = Path(temp_dir)
                input_pdf = temp_path / "page.pdf"
                output_zip = temp_path / "output.zip"
                input_pdf.write_bytes(pdf_bytes)

                job = self.client.document_intelligence.create_job(
                    language=language,
                    output_format="html",
                )
                job.upload_file(str(input_pdf))
                job.start()
                job.wait_until_complete()
                job.download_output(str(output_zip))
                return _extract_text_from_zip(output_zip)
        except AppError:
            raise
        except Exception as exc:  # SDK raises provider-specific exceptions.
            raise AppError(
                code="ocr_failed",
                user_message="OCR is temporarily unavailable. I will use any text I can extract directly from the PDF.",
                status_code=503,
                internal_detail=str(exc),
            ) from exc
