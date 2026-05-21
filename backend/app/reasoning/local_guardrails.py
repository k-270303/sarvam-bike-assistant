from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from backend.app.models import QueryAnalysis


Decision = Literal["continue", "clarification_needed", "low_confidence"]


@dataclass(frozen=True)
class GuardrailDecision:
    decision: Decision
    analysis: QueryAnalysis
    message: str | None = None


UNSUPPORTED_PATTERNS = [
    r"\bmodif(?:y|ication|ications)\b",
    r"\bmake (?:my |the )?bike faster\b",
    r"\bresale\b",
    r"\bprice\b",
    r"\bwhich .*brand .*best\b",
    r"\bbest .*mileage\b",
    r"\baftermarket\b",
    r"\btuning\b",
    r"\bperformance kit\b",
]

AMBIGUOUS_PATTERNS = [
    r"^bike is not starting\.?$",
    r"^bike not starting\.?$",
    r"^my bike is making noise\.?$",
    r"^bike making noise\.?$",
    r"^warning light is on\.?$",
    r"^a warning light is on\.?$",
]

SAFETY_PATTERNS = [
    r"\bbrake.*(?:not stopping|weak|failed|failure|loose)\b",
    r"\bfuel leak\b",
    r"\bsmell(?:s)? petrol\b",
    r"\bsmoke\b",
    r"\bfire\b",
]


def _matches_any(query: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, query, flags=re.I) for pattern in patterns)


def local_guardrail_decision(query: str) -> GuardrailDecision:
    normalized = " ".join(query.strip().split())
    lowered = normalized.lower()

    if _matches_any(lowered, UNSUPPORTED_PATTERNS):
        return GuardrailDecision(
            decision="low_confidence",
            analysis=QueryAnalysis(
                symptom=normalized,
                component=None,
                urgency="low",
                ambiguity_level=0.9,
                clarification_needed=False,
                clarification_questions=[],
            ),
            message=(
                "This appears outside the uploaded manuals' troubleshooting scope. "
                "I can help with manual-backed diagnostics, maintenance checks, and "
                "safety guidance, but not modifications, resale, pricing, or brand comparisons."
            ),
        )

    if _matches_any(lowered, SAFETY_PATTERNS):
        return GuardrailDecision(
            decision="clarification_needed",
            analysis=QueryAnalysis(
                symptom=normalized,
                component="safety-critical system",
                urgency="high",
                ambiguity_level=0.75,
                clarification_needed=True,
                clarification_questions=[
                    "Which bike model/manual should I use for this issue?",
                    "When exactly does this happen, and is the bike safe to keep riding?",
                    "Can you describe the warning light, sound, smell, or visible symptom?",
                ],
            ),
            message=None,
        )

    if _matches_any(lowered, AMBIGUOUS_PATTERNS) or len(lowered.split()) <= 4:
        return GuardrailDecision(
            decision="clarification_needed",
            analysis=QueryAnalysis(
                symptom=normalized,
                component=None,
                urgency="medium",
                ambiguity_level=0.85,
                clarification_needed=True,
                clarification_questions=[
                    "Which bike model are you asking about?",
                    "When does the issue happen: cold start, while riding, braking, or accelerating?",
                    "Are there any warning lights, unusual sounds, smoke, or leaks?",
                ],
            ),
            message=None,
        )

    return GuardrailDecision(
        decision="continue",
        analysis=QueryAnalysis(
            symptom=normalized,
            component=None,
            urgency="low",
            ambiguity_level=0.2,
            clarification_needed=False,
            clarification_questions=[],
        ),
    )

