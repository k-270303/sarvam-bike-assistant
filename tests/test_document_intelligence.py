from pathlib import Path
from zipfile import ZipFile

from backend.app.services.document_intelligence import _extract_text_from_zip


def test_extract_text_from_html_zip(tmp_path: Path) -> None:
    archive_path = tmp_path / "output.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("page.html", "<html><body><h1>Engine</h1><p>Check oil level.</p></body></html>")
    assert _extract_text_from_zip(archive_path) == "Engine Check oil level."
