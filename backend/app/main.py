from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.errors import AppError, http_error, safe_detail
from backend.app.evaluation.evaluator import evaluate_retrieval
from backend.app.models import EvaluationCase, IngestResponse, TroubleshootRequest
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
            pages = extract_pdf_pages(uploaded.filename, pdf_bytes)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=safe_detail(
                    f"I could not read {uploaded.filename}. Please upload a valid, uncorrupted PDF manual.",
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

        all_pages.extend(pages)
        document_names.append(uploaded.filename)

    chunks = chunk_pages(all_pages)
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

    session.documents = document_names
    session.pages = all_pages
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
