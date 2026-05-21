from __future__ import annotations

from backend.app.models import VisionObservation


DIAGNOSTIC_LANGUAGE = [
    "piston ring",
    "valve seal",
    "oil pump",
    "head gasket",
    "carburetor failure",
    "fuel injector failure",
    "replace",
    "repair",
    "cause is",
    "caused by",
    "diagnosis",
]


def sanitize_observation(observation: VisionObservation) -> VisionObservation:
    def keep_safe(items: list[str]) -> list[str]:
        safe = []
        for item in items:
            lowered = item.lower()
            if any(term in lowered for term in DIAGNOSTIC_LANGUAGE):
                continue
            safe.append(item)
        return safe

    return VisionObservation(
        visible_observations=keep_safe(observation.visible_observations),
        visible_text=keep_safe(observation.visible_text),
        visible_components=keep_safe(observation.visible_components),
        uncertainties=observation.uncertainties,
    )


def observation_has_signal(observation: VisionObservation) -> bool:
    return bool(
        observation.visible_observations
        or observation.visible_text
        or observation.visible_components
    )


def enrich_query_with_observation(
    user_question: str, observation: VisionObservation
) -> str:
    safe = sanitize_observation(observation)
    parts = [f"User question:\n{user_question}"]
    if safe.visible_observations:
        parts.append("Image observations:\n- " + "\n- ".join(safe.visible_observations))
    if safe.visible_text:
        parts.append("Visible text in image:\n- " + "\n- ".join(safe.visible_text))
    if safe.visible_components:
        parts.append("Visible components:\n- " + "\n- ".join(safe.visible_components))
    if safe.uncertainties:
        parts.append("Vision uncertainty:\n- " + "\n- ".join(safe.uncertainties))
    parts.append(
        "Important: use these image observations only as retrieval hints. "
        "Do not diagnose from the image. Answer only from uploaded manuals."
    )
    return "\n\n".join(parts)

