from __future__ import annotations

from collections import defaultdict

from backend.app.models import EvaluationCase
from backend.app.reasoning.confidence import confidence_level, score_confidence
from backend.app.reasoning.local_guardrails import local_guardrail_decision


def evaluate_core_workflow(cases: list[EvaluationCase], search_fn) -> dict:
    rows = []
    status_hits = 0
    category_totals: dict[str, int] = defaultdict(int)
    category_hits: dict[str, int] = defaultdict(int)

    for case in cases:
        category_totals[case.category] += 1
        local = local_guardrail_decision(case.query)
        if local.decision == "clarification_needed":
            predicted_status = "clarification_needed"
            confidence = 0.0
        elif local.decision == "low_confidence":
            predicted_status = "low_confidence"
            confidence = 0.0
        else:
            hits = search_fn(case.query, top_k=5)
            confidence = score_confidence(hits, local.analysis.ambiguity_level)
            predicted_status = (
                "success" if confidence_level(confidence) != "low" else "low_confidence"
            )

        passed = predicted_status == case.expected_status
        if passed:
            status_hits += 1
            category_hits[case.category] += 1
        rows.append(
            {
                "id": case.id,
                "category": case.category,
                "expected_status": case.expected_status,
                "predicted_status": predicted_status,
                "confidence": round(confidence, 4),
                "passed": passed,
            }
        )

    by_category = {
        category: {
            "accuracy": round(category_hits[category] / max(1, total), 4),
            "passed": category_hits[category],
            "total": total,
        }
        for category, total in sorted(category_totals.items())
    }

    return {
        "workflow_status_accuracy": round(status_hits / max(1, len(cases)), 4),
        "case_count": len(cases),
        "status_accuracy_by_category": by_category,
        "case_results": rows,
    }
