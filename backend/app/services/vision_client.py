from __future__ import annotations

import base64
import json
from abc import ABC, abstractmethod
from typing import Any

import requests
from pydantic import ValidationError

from backend.app.config import settings
from backend.app.errors import AppError
from backend.app.models import VisionObservation


VISION_OBSERVATION_PROMPT = """You inspect motorcycle troubleshooting images.
Your job is ONLY to describe observable facts.

Rules:
- Do not diagnose mechanical causes.
- Do not recommend repairs.
- Do not infer hidden component failures.
- Do not say things like piston rings, valve seals, oil pump failure, etc. unless visible text in the image says that.
- If the image is unclear, say so in uncertainties.
- Return JSON only with:
  visible_observations: string[]
  visible_text: string[]
  visible_components: string[]
  uncertainties: string[]
"""


class VisionClient(ABC):
    @abstractmethod
    def describe_image(
        self, image_bytes: bytes, *, mime_type: str, user_question: str
    ) -> VisionObservation:
        raise NotImplementedError


class OpenAICompatibleVisionClient(VisionClient):
    """Provider-agnostic VLM client for Fireworks/HF/Together-style chat APIs."""

    def __init__(self) -> None:
        if not settings.vision_api_key:
            raise AppError(
                code="vision_not_configured",
                user_message="Image understanding is not configured yet. You can still ask using text.",
                status_code=503,
            )

    def describe_image(
        self, image_bytes: bytes, *, mime_type: str, user_question: str
    ) -> VisionObservation:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{encoded}"
        try:
            response = requests.post(
                settings.vision_api_base_url,
                headers={
                    "Authorization": f"Bearer {settings.vision_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.vision_model,
                    "messages": [
                        {"role": "system", "content": VISION_OBSERVATION_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "User question: "
                                        f"{user_question}\nDescribe only visible facts."
                                    ),
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": data_url},
                                },
                            ],
                        },
                    ],
                    "temperature": 0,
                    "max_tokens": 700,
                },
                timeout=90,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            payload = _parse_json_object(content)
            return VisionObservation.model_validate(payload)
        except requests.Timeout as exc:
            raise AppError(
                code="vision_timeout",
                user_message="Image analysis took too long. Please describe the visible symptom in text, or try the image again.",
                internal_detail=str(exc),
            ) from exc
        except requests.HTTPError as exc:
            raise AppError(
                code="vision_http_error",
                user_message="Image analysis is unavailable right now. You can still continue with text-only troubleshooting.",
                internal_detail=str(exc),
            ) from exc
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            raise AppError(
                code="vision_failed",
                user_message="I could not safely read that image. Please describe the visible symptom in words.",
                internal_detail=str(exc),
            ) from exc


def _parse_json_object(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            raise
        return json.loads(raw[start : end + 1])


def build_vision_client() -> VisionClient:
    return OpenAICompatibleVisionClient()
