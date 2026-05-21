from backend.app.models import VisionObservation
from backend.app.reasoning.image_enrichment import (
    enrich_query_with_observation,
    observation_has_signal,
    sanitize_observation,
)


def test_image_enrichment_keeps_observations_not_diagnosis() -> None:
    observation = VisionObservation(
        visible_observations=[
            "white smoke appears near the exhaust",
            "cause is worn piston rings",
        ],
        visible_text=[],
        visible_components=["exhaust"],
        uncertainties=["Image alone cannot confirm the mechanical cause"],
    )
    safe = sanitize_observation(observation)
    assert safe.visible_observations == ["white smoke appears near the exhaust"]
    enriched = enrich_query_with_observation("Why is this happening?", safe)
    assert "white smoke appears near the exhaust" in enriched
    assert "worn piston rings" not in enriched
    assert "Do not diagnose from the image" in enriched


def test_empty_observation_has_no_signal() -> None:
    observation = VisionObservation(
        visible_observations=[],
        visible_text=[],
        visible_components=[],
        uncertainties=["Image is blurry"],
    )
    assert not observation_has_signal(observation)

