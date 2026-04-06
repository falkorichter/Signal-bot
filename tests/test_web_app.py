"""Tests for web_app.py — Flask dashboard API routes."""

import json
from pathlib import Path

import pytest

from storage import Session, SessionStore
from web_app import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    """Flask test client wired to a fresh in-memory session store."""
    store = SessionStore(sessions_file=tmp_path / "sessions.json")
    # Inject sessions for testing
    s1 = store.create_session("+1", "grp", "What are the hours?")
    store.update_session(
        s1.id,
        is_question=True,
        appointments_text="- 2099-01-01 at 09:00: Consult",
        llm_response="We open at 9.",
        final_message="👋 Hello! We open at 9. ⚠️ Disclaimer.",
        replied=True,
        replied_at="2099-01-01T09:01:00+00:00",
    )
    s2 = store.create_session("+2", "grp", "Just saying hi")
    store.update_session(s2.id, is_question=False)

    # Patch the web_app module's _fresh_store to return our controlled store
    with app.test_client() as c:
        import web_app
        original = web_app._fresh_store

        def mock_store():
            return store

        web_app._fresh_store = mock_store
        yield c
        web_app._fresh_store = original


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

class TestDashboardRoute:
    def test_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_returns_html(self, client):
        response = client.get("/")
        assert b"<!DOCTYPE html>" in response.data or b"<html" in response.data

    def test_contains_bot_title(self, client):
        response = client.get("/")
        assert b"Signal FAQ Bot" in response.data


# ---------------------------------------------------------------------------
# GET /api/sessions
# ---------------------------------------------------------------------------

class TestApiSessions:
    def test_returns_200(self, client):
        response = client.get("/api/sessions")
        assert response.status_code == 200

    def test_content_type_is_json(self, client):
        response = client.get("/api/sessions")
        assert "application/json" in response.content_type

    def test_returns_list(self, client):
        data = client.get("/api/sessions").get_json()
        assert isinstance(data, list)

    def test_sessions_count(self, client):
        data = client.get("/api/sessions").get_json()
        assert len(data) == 2

    def test_session_has_required_fields(self, client):
        data = client.get("/api/sessions").get_json()
        required = {"id", "timestamp", "sender", "message_text",
                    "is_question", "replied"}
        for session in data:
            assert required <= set(session.keys())

    def test_newest_session_first(self, client):
        data = client.get("/api/sessions").get_json()
        # +2 was created after +1 (is_question=False is the second one)
        assert data[0]["sender"] == "+2"

    def test_replied_session_has_reply_fields(self, client):
        data = client.get("/api/sessions").get_json()
        replied = next(s for s in data if s["replied"])
        assert replied["llm_response"] == "We open at 9."
        assert replied["final_message"] is not None


# ---------------------------------------------------------------------------
# GET /api/sessions/<id>
# ---------------------------------------------------------------------------

class TestApiSingleSession:
    def test_returns_200_for_existing_session(self, client):
        sessions = client.get("/api/sessions").get_json()
        session_id = sessions[0]["id"]
        response = client.get(f"/api/sessions/{session_id}")
        assert response.status_code == 200

    def test_returns_404_for_unknown_id(self, client):
        response = client.get("/api/sessions/does-not-exist-xyz")
        assert response.status_code == 404

    def test_returned_session_matches_id(self, client):
        sessions = client.get("/api/sessions").get_json()
        session_id = sessions[0]["id"]
        data = client.get(f"/api/sessions/{session_id}").get_json()
        assert data["id"] == session_id


# ---------------------------------------------------------------------------
# GET /api/stats
# ---------------------------------------------------------------------------

class TestApiStats:
    def test_returns_200(self, client):
        assert client.get("/api/stats").status_code == 200

    def test_stats_has_required_keys(self, client):
        data = client.get("/api/stats").get_json()
        required = {"total", "questions", "non_questions", "replied", "errors"}
        assert required <= set(data.keys())

    def test_total_matches_session_count(self, client):
        stats = client.get("/api/stats").get_json()
        sessions = client.get("/api/sessions").get_json()
        assert stats["total"] == len(sessions)

    def test_questions_count_correct(self, client):
        stats = client.get("/api/stats").get_json()
        assert stats["questions"] == 1

    def test_replied_count_correct(self, client):
        stats = client.get("/api/stats").get_json()
        assert stats["replied"] == 1

    def test_non_questions_count_correct(self, client):
        stats = client.get("/api/stats").get_json()
        assert stats["non_questions"] == 1

    def test_errors_zero_when_no_errors(self, client):
        stats = client.get("/api/stats").get_json()
        assert stats["errors"] == 0
