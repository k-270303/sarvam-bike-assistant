from __future__ import annotations

from dataclasses import asdict
import re
from typing import Any

from backend.app.models import EvaluationCase, SearchHit


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _case_terms_pass(case: EvaluationCase, hits: list[SearchHit], k: int) -> bool:
    text = _normalize(" ".join(result.chunk.text for result in hits[:k]))
    required_terms = all(_normalize(term) in text for term in case.expected_terms)
    any_terms = (
        not case.expected_any_terms
        or any(_normalize(term) in text for term in case.expected_any_terms)
    )
    return required_terms and any_terms


def _first_matching_rank(case: EvaluationCase, hits: list[SearchHit]) -> int | None:
    for index in range(1, len(hits) + 1):
        if _case_terms_pass(case, hits, index):
            return index
    return None


def _document_hit(case: EvaluationCase, hits: list[SearchHit], k: int) -> bool:
    if not case.expected_document_names:
        return False
    top_documents = {result.chunk.document_name for result in hits[:k]}
    return any(name in top_documents for name in case.expected_document_names)


def evaluate_retrieval(
    cases: list[EvaluationCase],
    search_fn,
) -> dict[str, float]:
    if not cases:
        return {
            "retrieval_accuracy_at_1": 0.0,
            "retrieval_accuracy_at_3": 0.0,
            "retrieval_accuracy_at_5": 0.0,
            "retrieval_mrr_at_5": 0.0,
            "document_accuracy_at_1": 0.0,
            "document_accuracy_at_5": 0.0,
            "supported_case_count": 0.0,
        }

    supported_cases = [case for case in cases if case.expected_status == "success"]
    hits_at_1 = 0
    hits_at_3 = 0
    hits_at_5 = 0
    reciprocal_rank_sum = 0.0
    document_hits_at_1 = 0
    document_hits_at_5 = 0

    for case in supported_cases:
        results: list[SearchHit] = search_fn(case.query, top_k=5)
        if _case_terms_pass(case, results, 1):
            hits_at_1 += 1
        if _case_terms_pass(case, results, 3):
            hits_at_3 += 1
        if _case_terms_pass(case, results, 5):
            hits_at_5 += 1
        first_rank = _first_matching_rank(case, results)
        if first_rank is not None and first_rank <= 5:
            reciprocal_rank_sum += 1 / first_rank
        if _document_hit(case, results, 1):
            document_hits_at_1 += 1
        if _document_hit(case, results, 5):
            document_hits_at_5 += 1

    denominator = max(1, len(supported_cases))
    return {
        "retrieval_accuracy_at_1": round(hits_at_1 / denominator, 4),
        "retrieval_accuracy_at_3": round(hits_at_3 / denominator, 4),
        "retrieval_accuracy_at_5": round(hits_at_5 / denominator, 4),
        "retrieval_mrr_at_5": round(reciprocal_rank_sum / denominator, 4),
        "document_accuracy_at_1": round(document_hits_at_1 / denominator, 4),
        "document_accuracy_at_5": round(document_hits_at_5 / denominator, 4),
        "supported_case_count": float(len(supported_cases)),
    }


def evaluate_retrieval_cases(
    cases: list[EvaluationCase],
    search_fn,
) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        if case.expected_status != "success":
            continue
        results: list[SearchHit] = search_fn(case.query, top_k=5)
        first_rank = _first_matching_rank(case, results)
        top_5_documents = [result.chunk.document_name for result in results]
        rows.append(
            {
                "id": case.id,
                "category": case.category,
                "pass_at_1": _case_terms_pass(case, results, 1),
                "pass_at_3": _case_terms_pass(case, results, 3),
                "pass_at_5": _case_terms_pass(case, results, 5),
                "first_matching_rank": first_rank,
                "document_hit_at_1": _document_hit(case, results, 1),
                "document_hit_at_5": _document_hit(case, results, 5),
                "top_5_documents": top_5_documents,
                "top_1_section": results[0].chunk.section_title if results else None,
                "top_1_score": round(results[0].combined_score, 4) if results else 0.0,
            }
        )
    return rows


def serialize_hits(hits: list[SearchHit]) -> list[dict]:
    rows = []
    for hit in hits:
        row = asdict(hit)
        rows.append(row)
    return rows
