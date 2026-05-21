from __future__ import annotations

import json
from typing import Any

import requests
from sarvamai import SarvamAI

from backend.app.config import settings
from backend.app.errors import AppError


class SarvamClient:
    def __init__(self) -> None:
        if not settings.sarvam_api_key:
            raise AppError(
                code="sarvam_not_configured",
                user_message="Sarvam is not configured yet. Please add the API key and try again.",
                status_code=503,
            )
        self.sdk = SarvamAI(api_subscription_key=settings.sarvam_api_key)

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1200,
        reasoning_effort: str = "medium",
    ) -> dict[str, Any]:
        try:
            response = requests.post(
                settings.sarvam_chat_base_url,
                headers={
                    "API-Subscription-Key": settings.sarvam_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.sarvam_chat_model,
                    "messages": messages,
                    "temperature": temperature,
                    "top_p": 1,
                    "max_tokens": max_tokens,
                    "stream": False,
                    "reasoning_effort": reasoning_effort,
                },
                timeout=90,
            )
            response.raise_for_status()
            return response.json()
        except requests.Timeout as exc:
            raise AppError(
                code="sarvam_timeout",
                user_message="Sarvam took too long to respond. I can still try a conservative manual-only fallback.",
                internal_detail=str(exc),
            ) from exc
        except requests.HTTPError as exc:
            raise AppError(
                code="sarvam_http_error",
                user_message="Sarvam could not generate an answer right now. I can still use the retrieved manual excerpts as fallback.",
                internal_detail=str(exc),
            ) from exc
        except (requests.RequestException, ValueError) as exc:
            raise AppError(
                code="sarvam_unavailable",
                user_message="Sarvam is temporarily unavailable. I can still use the retrieved manual excerpts as fallback.",
                internal_detail=str(exc),
            ) from exc

    def chat_text(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        payload = self.chat_completion(messages, **kwargs)
        try:
            choice = payload["choices"][0]
            content = choice["message"].get("content")
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError(
                code="sarvam_bad_response",
                user_message="Sarvam returned an unexpected response. I can still use the retrieved manual excerpts as fallback.",
                internal_detail=str(exc),
            ) from exc
        if content is None:
            raise AppError(
                code="sarvam_empty_response",
                user_message="Sarvam returned no final answer. I can still use the retrieved manual excerpts as fallback.",
                internal_detail=f"finish_reason={choice.get('finish_reason')}",
            )
        return content

    def chat_json(self, messages: list[dict[str, str]], **kwargs: Any) -> dict[str, Any]:
        raw = self.chat_text(messages, **kwargs)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1:
                raise AppError(
                    code="sarvam_invalid_json",
                    user_message="Sarvam returned an answer format I could not verify. I can still use a conservative manual-only fallback.",
                    internal_detail=raw[:500],
                )
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError as exc:
                raise AppError(
                    code="sarvam_invalid_json",
                    user_message="Sarvam returned an answer format I could not verify. I can still use a conservative manual-only fallback.",
                    internal_detail=str(exc),
                ) from exc

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        *,
        filename: str = "question.wav",
        codec: str | None = None,
    ) -> str:
        try:
            response = self.sdk.speech_to_text.transcribe(
                file=(filename, audio_bytes),
                model=settings.sarvam_stt_model,
                mode="transcribe",
                language_code="unknown",
                input_audio_codec=codec or "wav",
            )
        except Exception as exc:  # SDK raises provider-specific exceptions.
            raise AppError(
                code="stt_failed",
                user_message="I could not transcribe that audio right now. Please try again or type the issue manually.",
                status_code=503,
                internal_detail=str(exc),
            ) from exc
        transcript = getattr(response, "transcript", "") or ""
        if not transcript.strip():
            raise AppError(
                code="empty_transcript",
                user_message="I could not detect speech in that audio. Please try a clearer recording or type the issue.",
                status_code=422,
            )
        return transcript
