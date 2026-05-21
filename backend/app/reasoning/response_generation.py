from __future__ import annotations

from backend.app.models import Citation, SearchHit, TroubleshootResponse
from backend.app.response.citation_validation import filter_supported_citations
from backend.app.services.sarvam_client import SarvamClient


GROUNDING_PROMPT = """You are a grounded bike troubleshooting assistant.
Use only the supplied manual excerpts. Do not use outside knowledge.
If the excerpts do not support a claim, do not make that claim.
Return JSON only with:
- issue_summary
- possible_cause
- recommended_action
- safety_warning
- escalation_recommendation
- citations: array of objects with document_name, page_start, page_end, section_title, excerpt

Citation rules:
- Every meaningful claim must be supported by at least one supplied excerpt.
- excerpt must be copied exactly from the supplied manual text.
- If evidence is insufficient, say so plainly instead of speculating.
- Do not add generic mechanical consequences such as "engine damage" unless the supplied excerpt explicitly says that.
- If the retrieved excerpt identifies a warning but does not provide an action, say that the uploaded manual excerpt identifies the warning but does not provide a complete action in the retrieved evidence.
"""


def _context_from_hits(hits: list[SearchHit]) -> str:
    blocks = []
    for hit in hits:
        chunk = hit.chunk
        blocks.append(
            "\n".join(
                [
                    f"[chunk_id={chunk.chunk_id}]",
                    f"document_name={chunk.document_name}",
                    f"pages={chunk.page_start}-{chunk.page_end}",
                    f"section_title={chunk.section_title}",
                    chunk.text,
                ]
            )
        )
    return "\n\n---\n\n".join(blocks)


def _display_query(query: str) -> str:
    marker = "User question:\n"
    if marker in query:
        rest = query.split(marker, 1)[1]
        return rest.split("\n\n", 1)[0].strip()
    return query.strip()


def generate_grounded_response(
    query: str,
    hits: list[SearchHit],
    confidence_score: float,
    confidence_level: str,
    client: SarvamClient,
) -> TroubleshootResponse:
    payload = client.chat_json(
        [
            {"role": "system", "content": GROUNDING_PROMPT},
            {
                "role": "user",
                "content": f"USER QUERY:\n{query}\n\nMANUAL EXCERPTS:\n{_context_from_hits(hits)}",
            },
        ],
        temperature=0.0,
        max_tokens=2200,
        reasoning_effort="low",
    )
    citations = [Citation.model_validate(item) for item in payload.get("citations", [])]
    citations = filter_supported_citations(citations, hits)
    if not citations:
        return build_low_confidence_response(
            confidence_score=min(confidence_score, 0.49),
            clarification_questions=[
                "Can you provide more details or ask with the exact warning/symptom shown in the manual?"
            ],
        )

    return TroubleshootResponse(
        status="success",
        issue_summary=payload.get("issue_summary"),
        possible_cause=payload.get("possible_cause"),
        recommended_action=payload.get("recommended_action"),
        safety_warning=payload.get("safety_warning"),
        escalation_recommendation=payload.get("escalation_recommendation"),
        confidence_score=confidence_score,
        confidence_level=confidence_level,  # type: ignore[arg-type]
        citations=citations,
    )


def build_extractive_response(
    query: str,
    hits: list[SearchHit],
    confidence_score: float,
    confidence_level: str,
    *,
    fallback_reason: str | None = None,
) -> TroubleshootResponse:
    if not hits:
        return build_low_confidence_response(confidence_score, [])

    top = hits[0].chunk
    excerpt = top.text[:700].strip()
    if len(top.text) > 700:
        excerpt += "..."

    return TroubleshootResponse(
        status="success",
        issue_summary=f"Manual-backed result for: {_display_query(query)}",
        possible_cause=(
            "The assistant found relevant manual evidence, but generated a conservative "
            "extractive response instead of inferring beyond the source."
        ),
        recommended_action=(
            "Review the cited manual excerpt and follow only the procedure or checks "
            "explicitly stated there. If the issue is safety-critical or unclear, consult "
            "an authorised service centre."
        ),
        confidence_score=confidence_score,
        confidence_level=confidence_level,  # type: ignore[arg-type]
        citations=[
            Citation(
                document_name=top.document_name,
                page_start=top.page_start,
                page_end=top.page_end,
                section_title=top.section_title,
                excerpt=excerpt,
            )
        ],
        safety_warning=None,
        escalation_recommendation=(
            fallback_reason
            or "Escalate to an authorised service centre if the manual excerpt does not fully resolve the issue."
        ),
    )


def build_low_confidence_response(
    confidence_score: float,
    clarification_questions: list[str],
) -> TroubleshootResponse:
    return TroubleshootResponse(
        status="low_confidence",
        confidence_score=confidence_score,
        confidence_level="low",
        clarification_questions=clarification_questions,
        message=(
            "I could not find enough support in the uploaded manuals to answer "
            "confidently. Please add detail or consult a qualified technician if "
            "the issue is urgent."
        ),
    )
