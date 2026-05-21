from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    sarvam_api_key: str | None = os.getenv("SARVAM_API_KEY")
    sarvam_chat_model: str = os.getenv("SARVAM_CHAT_MODEL", "sarvam-105b")
    sarvam_chat_base_url: str = os.getenv(
        "SARVAM_CHAT_BASE_URL", "https://api.sarvam.ai/v1/chat/completions"
    )
    sarvam_stt_model: str = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
    embedding_backend: str = os.getenv(
        "EMBEDDING_BACKEND", "sentence-transformers"
    )
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    session_ttl_minutes: int = int(os.getenv("SESSION_TTL_MINUTES", "120"))
    vision_api_key: str | None = os.getenv("VISION_API_KEY")
    vision_api_base_url: str = os.getenv(
        "VISION_API_BASE_URL",
        "https://api.fireworks.ai/inference/v1/chat/completions",
    )
    vision_model: str = os.getenv(
        "VISION_MODEL",
        "accounts/fireworks/models/qwen2p5-vl-3b-instruct",
    )
    cors_allowed_origins: str = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:8501",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


settings = Settings()
