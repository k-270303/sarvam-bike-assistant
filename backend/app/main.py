from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.errors import AppError, http_error, safe_detail
from backend.app.evaluation.evaluator import evaluate_retrieval
from backend.app.models import (
    ChunkedUploadStartRequest,
    ChunkedUploadStartResponse,
    EvaluationCase,
    IngestResponse,
    ManualPage,
    ManualUploadState,
    SessionCorpus,
    TroubleshootRequest,
)
from backend.app.reasoning.confidence import confidence_level, score_confidence
from backend.app.reasoning.image_enrichment import (
    enrich_query_with_observation,
    observation_has_signal,
    sanitize_observation,
)
from backend.app.reasoning.local_guardrails import local_guardrail_decision
from backend.app.reasoning.response_generation import (
    build_extractive_response,
    build_low_confidence_response,
    generate_grounded_response,
)
from backend.app.retrieval.chunking import chunk_pages
from backend.app.retrieval.hybrid_search import HybridIndex
from backend.app.retrieval.pdf_processor import (
    extract_pdf_pages,
    extract_single_page_pdf,
    select_pages_for_ocr,
)
from backend.app.services.document_intelligence import DocumentIntelligenceClient
from backend.app.services.sarvam_client import SarvamClient
from backend.app.services.session_store import session_store
from backend.app.services.vision_client import build_vision_client


app = FastAPI(title="Bike Troubleshooting Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

CHUNK_SIZE_HINT_BYTES = 3 * 1024 * 1024
MAX_CHUNK_BYTES = 4 * 1024 * 1024


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sessions")
def create_session() -> dict[str, str]:
    session = session_store.create()
    return {"session_id": session.session_id}


@app.post("/sessions/{session_id}/manuals", response_model=IngestResponse)
async def upload_manuals(
    session_id: str,
    files: list[UploadFile] = File(...),
) -> IngestResponse:
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=safe_detail("Session not found", "session_not_found"))
    if not files:
        raise HTTPException(status_code=400, detail=safe_detail("Please upload at least one PDF manual.", "no_files"))

    all_pages = list(session.pages)
    document_names = list(session.documents)
    warnings: list[str] = []

    for uploaded in files:
        if not uploaded.filename or not uploaded.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=safe_detail("Only PDF uploads are supported.", "unsupported_file_type"),
            )
        try:
            pdf_bytes = await uploaded.read()
            pages, file_warnings = _extract_manual_pages(uploaded.filename, pdf_bytes)
            warnings.extend(file_warnings)
            all_pages.extend(pages)
            document_names.append(uploaded.filename)
        except HTTPException:
            raise

    return _rebuild_session_index(
        session,
        warnings,
        pages=all_pages,
        documents=document_names,
    )


@app.post(
    "/sessions/{session_id}/manual-upload/start",
    response_model=ChunkedUploadStartResponse,
)
def start_manual_upload(
    session_id: str,
    request: ChunkedUploadStartRequest,
) -> ChunkedUploadStartResponse:
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=safe_detail("Session not found", "session_not_found"))
    if not request.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=safe_detail("Only PDF uploads are supported.", "unsupported_file_type"),
        )

    upload_id = str(uuid4())
    session.pending_uploads[upload_id] = ManualUploadState(
        upload_id=upload_id,
        filename=request.filename,
        total_chunks=request.total_chunks,
        total_size=request.total_size,
    )
    session_store.save(session)
    return ChunkedUploadStartResponse(
        upload_id=upload_id,
        chunk_size_hint=CHUNK_SIZE_HINT_BYTES,
    )


@app.post("/sessions/{session_id}/manual-upload/{upload_id}/chunk")
async def upload_manual_chunk(
    session_id: str,
    upload_id: str,
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
):
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=safe_detail("Session not found", "session_not_found"))

    upload = session.pending_uploads.get(upload_id)
    if not upload:
        raise HTTPException(
            status_code=404,
            detail=safe_detail("Upload session not found. Please retry the manual upload.", "upload_not_found"),
        )
    if chunk_index < 0 or chunk_index >= upload.total_chunks:
        raise HTTPException(
            status_code=400,
            detail=safe_detail("Invalid upload chunk index.", "invalid_chunk_index"),
        )

    chunk_bytes = await chunk.read()
    if len(chunk_bytes) > MAX_CHUNK_BYTES:
        raise HTTPException(
            status_code=413,
            detail=safe_detail(
                "This upload chunk is too large. Please retry with the latest app version.",
                "chunk_too_large",
            ),
        )

    upload.chunks[chunk_index] = chunk_bytes
    received_chunks = len(upload.chunks)

    if received_chunks < upload.total_chunks:
        session_store.save(session)
        return {
            "status": "partial",
            "received_chunks": received_chunks,
            "total_chunks": upload.total_chunks,
        }

    missing = sorted(set(range(upload.total_chunks)) - set(upload.chunks))
    if missing:
        session_store.save(session)
        return {
            "status": "partial",
            "received_chunks": received_chunks,
            "total_chunks": upload.total_chunks,
            "missing_chunks": missing,
        }

    pdf_bytes = b"".join(upload.chunks[index] for index in range(upload.total_chunks))
    if len(pdf_bytes) != upload.total_size:
        session.pending_uploads.pop(upload_id, None)
        session_store.save(session)
        raise HTTPException(
            status_code=400,
            detail=safe_detail(
                "The uploaded manual chunks did not match the original file size. Please retry the upload.",
                "chunk_size_mismatch",
            ),
        )

    session.pending_uploads.pop(upload_id, None)
    pages, warnings = _extract_manual_pages(upload.filename, pdf_bytes)
    return _rebuild_session_index(
        session,
        warnings,
        pages=[*session.pages, *pages],
        documents=[*session.documents, upload.filename],
    )


def _extract_manual_pages(filename: str, pdf_bytes: bytes) -> tuple[list[ManualPage], list[str]]:
    warnings: list[str] = []
    try:
        pages = extract_pdf_pages(filename, pdf_bytes)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=safe_detail(
                f"I could not read {filename}. Please upload a valid, uncorrupted PDF manual.",
                "pdf_unreadable",
            ),
        ) from exc

    pages_requiring_ocr = select_pages_for_ocr(pages)
    if pages_requiring_ocr:
        try:
            ocr_client = DocumentIntelligenceClient()
            for page in pages_requiring_ocr:
                try:
                    ocr_text = ocr_client.ocr_pdf_bytes(
                        extract_single_page_pdf(pdf_bytes, page.page_number)
                    )
                    if ocr_text:
                        page.text = ocr_text
                except AppError as exc:
                    warnings.append(exc.user_message)
                    break
        except AppError as exc:
            warnings.append(exc.user_message)

    return pages, warnings


def _rebuild_session_index(
    session: SessionCorpus,
    warnings: list[str],
    *,
    pages: list[ManualPage] | None = None,
    documents: list[str] | None = None,
) -> IngestResponse:
    next_pages = pages if pages is not None else session.pages
    next_documents = documents if documents is not None else session.documents
    chunks = chunk_pages(next_pages)
    if not chunks:
        raise HTTPException(
            status_code=422,
            detail=safe_detail(
                "I could not extract usable text from the uploaded manuals. If these are scanned PDFs, please try clearer scans or retry OCR later.",
                "no_extractable_text",
            ),
        )

    try:
        index = HybridIndex.from_chunks(chunks)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=safe_detail(
                "I processed the manuals, but indexing failed. Please try again in a moment.",
                "indexing_failed",
            ),
        ) from exc

    session.documents = next_documents
    session.pages = next_pages
    session.chunks = chunks
    session.lexical_index = index
    session_store.save(session)
    return IngestResponse(
        session_id=session.session_id,
        documents=session.documents,
        pages_processed=len(session.pages),
        chunks_indexed=len(session.chunks),
        warnings=sorted(set(warnings)),
    )


@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)) -> dict[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail=safe_detail("Audio file is required.", "audio_required"))
    suffix = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "wav"
    codec_map = {
        "wav": "wav",
        "mp3": "mp3",
        "m4a": "x-m4a",
        "aac": "aac",
        "ogg": "ogg",
        "flac": "flac",
        "webm": "webm",
    }
    try:
        client = SarvamClient()
        transcript = client.transcribe_audio(
            await file.read(),
            filename=file.filename,
            codec=codec_map.get(suffix, "wav"),
        )
        return {"transcript": transcript}
    except AppError as exc:
        raise http_error(exc) from exc


@app.post("/troubleshoot")
def troubleshoot(request: TroubleshootRequest):
    return _run_troubleshoot(request.session_id, request.query)


@app.post("/troubleshoot/image")
async def troubleshoot_with_image(
    session_id: str = Form(...),
    query: str = Form(...),
    image: UploadFile = File(...),
):
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=safe_detail("Upload must be an image.", "unsupported_image_type"))
    try:
        vision_client = build_vision_client()
        observation = vision_client.describe_image(
            await image.read(),
            mime_type=image.content_type,
            user_question=query,
        )
        observation = sanitize_observation(observation)
    except AppError as exc:
        text_only = _run_troubleshoot(session_id, query)
        payload = text_only.model_dump() if isinstance(text_only, BaseModel) else dict(text_only)
        payload["vision_warning"] = exc.user_message
        return payload

    if not observation_has_signal(observation):
        return {
            "status": "clarification_needed",
            "confidence_score": 0.0,
            "confidence_level": "low",
            "clarification_questions": [
                "The image did not provide clear observable troubleshooting details. Can you describe the visible symptom in words?",
                "Which bike model/manual should I use for this issue?",
            ],
            "vision_observation": observation.model_dump(),
        }

    enriched_query = enrich_query_with_observation(query, observation)
    response = _run_troubleshoot(session_id, enriched_query)
    payload = response.model_dump() if isinstance(response, BaseModel) else dict(response)
    payload["vision_observation"] = observation.model_dump()
    payload["enriched_query"] = enriched_query
    return payload


def _run_troubleshoot(session_id: str, query: str):
    session = session_store.get(session_id)
    if not session or not session.lexical_index:
        raise HTTPException(
            status_code=404,
            detail=safe_detail("Please upload and process at least one manual before asking a question.", "manuals_not_indexed"),
        )

    local = local_guardrail_decision(query)
    if local.decision == "low_confidence":
        return {
            "status": "low_confidence",
            "confidence_score": 0.0,
            "confidence_level": "low",
            "message": local.message,
            "clarification_questions": [],
        }
    if local.decision == "clarification_needed":
        return {
            "status": "clarification_needed",
            "confidence_score": 0.0,
            "confidence_level": "low",
            "clarification_questions": local.analysis.clarification_questions,
        }

    analysis = local.analysis

    index: HybridIndex = session.lexical_index  # type: ignore[assignment]
    try:
        hits = index.search(query, top_k=5)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=safe_detail(
                "I had trouble searching the uploaded manuals. Please try again in a moment.",
                "retrieval_failed",
            ),
        ) from exc

    confidence = score_confidence(hits, analysis.ambiguity_level)
    level = confidence_level(confidence)
    if level == "low":
        return build_low_confidence_response(
            confidence, analysis.clarification_questions
        )

    try:
        client = SarvamClient()
        return generate_grounded_response(
            query,
            hits,
            confidence,
            level,
            client,
        )
    except Exception:
        return build_extractive_response(
            query,
            hits,
            confidence,
            level,
            fallback_reason=(
                "Sarvam response generation was unavailable, so this is a conservative "
                "extractive fallback using only retrieved manual text."
            ),
        )


@app.post("/sessions/{session_id}/evaluate")
def evaluate(session_id: str, cases: list[EvaluationCase]) -> dict[str, float]:
    session = session_store.get(session_id)
    if not session or not session.lexical_index:
        raise HTTPException(
            status_code=404,
            detail=safe_detail("Session has no indexed manuals.", "manuals_not_indexed"),
        )
    index: HybridIndex = session.lexical_index  # type: ignore[assignment]
    return evaluate_retrieval(cases, index.search)
