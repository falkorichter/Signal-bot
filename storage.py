"""storage.py — Thread-safe, JSON-backed session persistence.

Every message the bot processes is stored as a :class:`Session` in a JSON
file (``data/sessions.json`` by default).  Sessions survive bot restarts and
are read by the web dashboard.

The store uses an in-process :class:`threading.RLock` for thread safety and
atomic file writes (write-then-rename) to prevent data corruption.
"""

import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR: Path = Path(__file__).parent / "data"
SESSIONS_FILE: Path = DATA_DIR / "sessions.json"


class Session:
    """Represents one complete message-processing pipeline run.

    Fields are populated progressively as the bot works through each pipeline
    step; ``None`` means the step has not yet been reached.
    """

    __slots__ = (
        "id",
        "timestamp",
        "sender",
        "group_id",
        "message_text",
        "is_question",
        "appointments_text",
        "llm_response",
        "final_message",
        "replied",
        "replied_at",
        "error",
    )

    def __init__(
        self,
        sender: str,
        group_id: str,
        message_text: str,
        session_id: Optional[str] = None,
        timestamp: Optional[str] = None,
        is_question: Optional[bool] = None,
        appointments_text: Optional[str] = None,
        llm_response: Optional[str] = None,
        final_message: Optional[str] = None,
        replied: bool = False,
        replied_at: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        self.id: str = session_id or str(uuid.uuid4())
        self.timestamp: str = timestamp or datetime.now(timezone.utc).isoformat()
        self.sender: str = sender
        self.group_id: str = group_id
        self.message_text: str = message_text
        self.is_question: Optional[bool] = is_question
        self.appointments_text: Optional[str] = appointments_text
        self.llm_response: Optional[str] = llm_response
        self.final_message: Optional[str] = final_message
        self.replied: bool = replied
        self.replied_at: Optional[str] = replied_at
        self.error: Optional[str] = error

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(
            session_id=data.get("id"),
            timestamp=data.get("timestamp"),
            sender=data.get("sender", ""),
            group_id=data.get("group_id", ""),
            message_text=data.get("message_text", ""),
            is_question=data.get("is_question"),
            appointments_text=data.get("appointments_text"),
            llm_response=data.get("llm_response"),
            final_message=data.get("final_message"),
            replied=data.get("replied", False),
            replied_at=data.get("replied_at"),
            error=data.get("error"),
        )


class SessionStore:
    """Thread-safe, JSON-backed store for :class:`Session` objects.

    Args:
        sessions_file: Override the default ``data/sessions.json`` path.
                       Useful for testing (pass a :class:`pathlib.Path` to a
                       temporary file).
    """

    def __init__(self, sessions_file: Optional[Path] = None) -> None:
        self._file = Path(sessions_file or SESSIONS_FILE)
        self._lock = threading.RLock()
        self._sessions: Dict[str, Session] = {}
        self._load()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load sessions from disk.  Silently starts fresh on missing/corrupt file."""
        if not self._file.exists():
            logger.info("No sessions file at %s — starting fresh", self._file)
            return
        try:
            raw = self._file.read_text(encoding="utf-8")
            items = json.loads(raw)
            for item in items:
                s = Session.from_dict(item)
                self._sessions[s.id] = s
            logger.info(
                "Loaded %d session(s) from %s", len(self._sessions), self._file
            )
        except json.JSONDecodeError as exc:
            logger.error(
                "Sessions file %s is corrupt: %s — starting fresh", self._file, exc
            )
        except OSError as exc:
            logger.error("Could not read sessions file %s: %s", self._file, exc)

    def _save(self) -> None:
        """Atomically write all sessions to disk (caller must hold self._lock)."""
        self._file.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            [s.to_dict() for s in self._sessions.values()],
            ensure_ascii=False,
            indent=2,
        )
        # Atomic write: temp file in same directory → rename
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=self._file.parent, suffix=".tmp", prefix="sessions_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(content)
                os.replace(tmp_path, self._file)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as exc:
            logger.error("Could not write sessions file %s: %s", self._file, exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_session(
        self, sender: str, group_id: str, message_text: str
    ) -> Session:
        """Create, persist, and return a new :class:`Session`."""
        with self._lock:
            session = Session(
                sender=sender, group_id=group_id, message_text=message_text
            )
            self._sessions[session.id] = session
            self._save()
        return session

    def update_session(self, session_id: str, **kwargs) -> Optional[Session]:
        """Update named fields on an existing session and persist.

        Returns the updated :class:`Session`, or ``None`` if not found.
        Unrecognised field names are logged as warnings and ignored.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                logger.error("update_session: session %s not found", session_id)
                return None
            for key, value in kwargs.items():
                if key in Session.__slots__:
                    setattr(session, key, value)
                else:
                    logger.warning(
                        "update_session: unknown field '%s' — ignored", key
                    )
            self._save()
        return session

    def is_already_replied(self, sender: str, message_text: str) -> bool:
        """Return ``True`` if a reply was already sent for this sender + message.

        Used to prevent duplicate replies when the bot restarts mid-session.
        """
        with self._lock:
            return any(
                s.sender == sender
                and s.message_text == message_text
                and s.replied
                for s in self._sessions.values()
            )

    def get_all_sessions(self) -> List[Session]:
        """Return all sessions sorted newest-first."""
        with self._lock:
            sessions = list(self._sessions.values())
        sessions.sort(key=lambda s: s.timestamp, reverse=True)
        return sessions

    def get_session(self, session_id: str) -> Optional[Session]:
        """Return a :class:`Session` by ID, or ``None`` if not found."""
        with self._lock:
            return self._sessions.get(session_id)
