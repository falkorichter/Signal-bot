"""Tests for storage.py — thread-safe JSON session persistence."""

import json
import threading
import time
from pathlib import Path

import pytest

from storage import Session, SessionStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    """A fresh SessionStore backed by a temp directory."""
    return SessionStore(sessions_file=tmp_path / "sessions.json")


@pytest.fixture
def sessions_file(tmp_path):
    return tmp_path / "sessions.json"


# ---------------------------------------------------------------------------
# Session serialisation
# ---------------------------------------------------------------------------

class TestSessionSerialisation:
    def test_to_dict_contains_all_fields(self):
        s = Session(sender="+1", group_id="g1", message_text="Hello")
        d = s.to_dict()
        for field in Session.__slots__:
            assert field in d

    def test_from_dict_roundtrip(self):
        s = Session(
            sender="+1234567890",
            group_id="grp",
            message_text="Test message",
            is_question=True,
            appointments_text="Appointments...",
            llm_response="Answer.",
            final_message="👋 Answer.",
            replied=True,
            replied_at="2099-01-01T00:00:00+00:00",
            error=None,
        )
        d = s.to_dict()
        s2 = Session.from_dict(d)
        assert s2.sender == s.sender
        assert s2.group_id == s.group_id
        assert s2.message_text == s.message_text
        assert s2.is_question == s.is_question
        assert s2.replied == s.replied
        assert s2.replied_at == s.replied_at
        assert s2.error == s.error

    def test_id_preserved_through_serialisation(self):
        s = Session(sender="+1", group_id="", message_text="Hi")
        s2 = Session.from_dict(s.to_dict())
        assert s2.id == s.id

    def test_auto_generated_id_is_unique(self):
        ids = {Session(sender="+1", group_id="", message_text="x").id for _ in range(20)}
        assert len(ids) == 20

    def test_from_dict_with_missing_optional_fields(self):
        s = Session.from_dict({"sender": "+1", "group_id": "", "message_text": "Hi"})
        assert s.is_question is None
        assert s.replied is False
        assert s.error is None


# ---------------------------------------------------------------------------
# SessionStore — basic CRUD
# ---------------------------------------------------------------------------

class TestSessionStoreCRUD:
    def test_create_session_returns_session(self, store):
        s = store.create_session("+1", "g", "Hello?")
        assert s.sender == "+1"
        assert s.message_text == "Hello?"

    def test_created_session_has_id(self, store):
        s = store.create_session("+1", "g", "Hi")
        assert s.id and len(s.id) > 0

    def test_get_session_returns_created(self, store):
        s = store.create_session("+1", "g", "Test")
        fetched = store.get_session(s.id)
        assert fetched is not None
        assert fetched.id == s.id

    def test_get_session_returns_none_for_unknown_id(self, store):
        assert store.get_session("does-not-exist") is None

    def test_update_session_modifies_field(self, store):
        s = store.create_session("+1", "g", "Q?")
        store.update_session(s.id, is_question=True)
        updated = store.get_session(s.id)
        assert updated.is_question is True

    def test_update_session_multiple_fields(self, store):
        s = store.create_session("+1", "g", "Q?")
        store.update_session(
            s.id,
            is_question=True,
            llm_response="Answer",
            replied=True,
        )
        updated = store.get_session(s.id)
        assert updated.is_question is True
        assert updated.llm_response == "Answer"
        assert updated.replied is True

    def test_update_session_unknown_field_logs_warning(self, store, caplog):
        import logging
        s = store.create_session("+1", "g", "Q?")
        with caplog.at_level(logging.WARNING, logger="storage"):
            store.update_session(s.id, nonexistent_field="value")
        assert "nonexistent_field" in caplog.text

    def test_update_session_nonexistent_id_returns_none(self, store):
        result = store.update_session("bad-id", is_question=True)
        assert result is None

    def test_get_all_sessions_newest_first(self, store):
        store.create_session("+1", "g", "First")
        time.sleep(0.01)
        store.create_session("+2", "g", "Second")
        sessions = store.get_all_sessions()
        assert sessions[0].message_text == "Second"
        assert sessions[1].message_text == "First"


# ---------------------------------------------------------------------------
# Persistence (reload from disk)
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_sessions_survive_reload(self, tmp_path):
        f = tmp_path / "sessions.json"
        store1 = SessionStore(f)
        s = store1.create_session("+1", "g", "Persistent?")
        store1.update_session(s.id, is_question=True, replied=True)

        store2 = SessionStore(f)
        reloaded = store2.get_session(s.id)
        assert reloaded is not None
        assert reloaded.is_question is True
        assert reloaded.replied is True

    def test_fresh_store_with_no_file(self, tmp_path):
        store = SessionStore(tmp_path / "new.json")
        assert store.get_all_sessions() == []

    def test_corrupt_file_handled_gracefully(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("NOT JSON {{{{", encoding="utf-8")
        store = SessionStore(f)
        assert store.get_all_sessions() == []

    def test_file_written_after_create(self, tmp_path):
        f = tmp_path / "sessions.json"
        store = SessionStore(f)
        store.create_session("+1", "g", "Hi")
        assert f.exists()
        data = json.loads(f.read_text(encoding="utf-8"))
        assert len(data) == 1

    def test_file_written_after_update(self, tmp_path):
        f = tmp_path / "sessions.json"
        store = SessionStore(f)
        s = store.create_session("+1", "g", "Q?")
        store.update_session(s.id, is_question=True)
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data[0]["is_question"] is True


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_is_already_replied_true_when_replied(self, store):
        s = store.create_session("+1", "g", "Same message")
        store.update_session(s.id, replied=True)
        assert store.is_already_replied("+1", "Same message") is True

    def test_is_already_replied_false_when_not_replied(self, store):
        store.create_session("+1", "g", "Same message")
        assert store.is_already_replied("+1", "Same message") is False

    def test_is_already_replied_false_for_different_sender(self, store):
        s = store.create_session("+1", "g", "Same message")
        store.update_session(s.id, replied=True)
        assert store.is_already_replied("+2", "Same message") is False

    def test_is_already_replied_false_for_different_message(self, store):
        s = store.create_session("+1", "g", "First message")
        store.update_session(s.id, replied=True)
        assert store.is_already_replied("+1", "Different message") is False

    def test_no_duplicate_reply_across_restarts(self, tmp_path):
        f = tmp_path / "sessions.json"
        store1 = SessionStore(f)
        s = store1.create_session("+1", "g", "Duplicate?")
        store1.update_session(s.id, replied=True)

        store2 = SessionStore(f)
        assert store2.is_already_replied("+1", "Duplicate?") is True


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_creates_do_not_corrupt(self, store):
        errors = []

        def create_many():
            try:
                for i in range(10):
                    store.create_session("+1", "g", f"Message {i}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=create_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        assert len(store.get_all_sessions()) == 50
