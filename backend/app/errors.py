from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


@dataclass(frozen=True)
class AppError(Exception):
    """User-safe application error.

    `internal_detail` is intentionally not returned to clients. It is useful while
    debugging locally but keeps the product UX non-technical.
    """

    code: str
    user_message: str
    status_code: int = 503
    internal_detail: str | None = None

    def __str__(self) -> str:
        return self.internal_detail or self.user_message


def http_error(error: AppError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={
            "code": error.code,
            "message": error.user_message,
        },
    )


def safe_detail(message: str, code: str = "request_failed") -> dict[str, Any]:
    return {"code": code, "message": message}
