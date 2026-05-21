from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4

from backend.app.config import settings
from backend.app.models import SessionCorpus


class SessionStore:
    """In-memory session store. Uploaded manuals never persist beyond process memory."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionCorpus] = {}
        self._lock = RLock()

    def create(self) -> SessionCorpus:
        now = datetime.now(timezone.utc)
        session = SessionCorpus(
            session_id=str(uuid4()),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> SessionCorpus | None:
        self.prune_expired()
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.updated_at = datetime.now(timezone.utc)
            return session

    def save(self, session: SessionCorpus) -> None:
        session.updated_at = datetime.now(timezone.utc)
        with self._lock:
            self._sessions[session.session_id] = session

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def prune_expired(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=settings.session_ttl_minutes
        )
        with self._lock:
            expired = [
                session_id
                for session_id, session in self._sessions.items()
                if session.updated_at < cutoff
            ]
            for session_id in expired:
                self._sessions.pop(session_id, None)


session_store = SessionStore()

