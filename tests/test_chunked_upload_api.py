from fastapi.testclient import TestClient

from backend.app import main
from backend.app.main import app
from backend.app.models import ManualPage


client = TestClient(app)


def test_chunked_manual_upload_reassembles_and_indexes(monkeypatch) -> None:
    expected_pdf_bytes = b"abcdef"

    def fake_extract_pdf_pages(filename: str, pdf_bytes: bytes) -> list[ManualPage]:
        assert filename == "large-manual.pdf"
        assert pdf_bytes == expected_pdf_bytes
        return [
            ManualPage(
                document_name=filename,
                page_number=1,
                text="Engine troubleshooting inspection procedure. " * 20,
            )
        ]

    class DummyIndex:
        pass

    monkeypatch.setattr("backend.app.main.extract_pdf_pages", fake_extract_pdf_pages)
    monkeypatch.setattr("backend.app.main.select_pages_for_ocr", lambda pages: [])
    monkeypatch.setattr(main.HybridIndex, "from_chunks", classmethod(lambda cls, chunks: DummyIndex()))

    session_id = client.post("/sessions").json()["session_id"]
    start_response = client.post(
        f"/sessions/{session_id}/manual-upload/start",
        json={
            "filename": "large-manual.pdf",
            "total_chunks": 2,
            "total_size": len(expected_pdf_bytes),
        },
    )
    assert start_response.status_code == 200
    upload_id = start_response.json()["upload_id"]

    first_chunk = client.post(
        f"/sessions/{session_id}/manual-upload/{upload_id}/chunk",
        data={"chunk_index": "0"},
        files={"chunk": ("large-manual.pdf.part-0", b"abc", "application/octet-stream")},
    )
    assert first_chunk.status_code == 200
    assert first_chunk.json()["status"] == "partial"

    final_chunk = client.post(
        f"/sessions/{session_id}/manual-upload/{upload_id}/chunk",
        data={"chunk_index": "1"},
        files={"chunk": ("large-manual.pdf.part-1", b"def", "application/octet-stream")},
    )
    assert final_chunk.status_code == 200
    payload = final_chunk.json()
    assert payload["documents"] == ["large-manual.pdf"]
    assert payload["pages_processed"] == 1
    assert payload["chunks_indexed"] >= 1
