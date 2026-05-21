from __future__ import annotations

from backend.app.models import QueryAnalysis
from backend.app.reasoning.local_guardrails import local_guardrail_decision
from backend.app.services.sarvam_client import SarvamClient


QUERY_ANALYSIS_PROMPT = """You analyze a bike troubleshooting query before retrieval.
Return JSON only with:
- symptom: short phrase
- component: short phrase or null
- urgency: low, medium, or high
- ambiguity_level: number from 0 to 1
- clarification_needed: boolean
- clarification_questions: array of at most 3 concise questions

Guidelines:
- Ask clarifying questions when the query is too vague to retrieve against a manual.
- Do not answer the troubleshooting question.
- Treat safety-critical symptoms such as brake failure, fire, fuel leaks, or loss of control as high urgency.
"""


def understand_query(query: str, client: SarvamClient) -> QueryAnalysis:
    local = local_guardrail_decision(query)
    if local.decision != "continue":
        return local.analysis

    payload = client.chat_json(
        [
            {"role": "system", "content": QUERY_ANALYSIS_PROMPT},
            {"role": "user", "content": query},
        ],
        temperature=0.0,
        max_tokens=500,
    )
    return QueryAnalysis.model_validate(payload)
