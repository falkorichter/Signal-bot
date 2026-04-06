"""Tests for web_app.py -- Flask dashboard API routes."""

import json
from unittest.mock import patch

import pytest

from storage import Session, SessionStore
from web_app import app


@pytest.fixture
def store_and_client(tmp_path):
    store = SessionStore(sessions_file=tmp_path / "sessions.json")

    s1 = store.create_session("+1", "grp", "What are the hours?")
    store.update_session(
        s1.id,
        is_question=True,
        appointments_text="- 2099-01-01 at 09:00: Consult",
        llm_response="We open at 9.",
        final_message="Hello! We open at 9.",
        replied=True,
        replied_at="2099-01-01T09:01:00+00:00",
        prompt_tokens=120,
        response_tokens=12,
    )
    s2 = store.create_session("+2", "grp", "Just saying hi")
    store.update_session(s2.id, is_question=False)

    s3 = store.create_session("benchmark-ui", "", "Test question?")
    store.update_session(s3.id, is_test=True, is_question=True,
                         llm_response="Test answer", replied=True)

    import web_app
    original = web_app._fresh_store

    def mock_store():
        return store

    web_app._fresh_store = mock_store

    with app.test_client() as c:
        yield store, c

    web_app._fresh_store = original


@pytest.fixture
def client(store_and_client):
    _, c = store_and_client
    return c


@pytest.fixture
def store(store_and_client):
    s, _ = store_and_client
    return s


class TestDashboardRoute:
    def test_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_returns_html(self, client):
        data = client.get("/").data
        assert b"<!DOCTYPE html>" in data or b"<html" in data

    def test_contains_bot_title(self, client):
        assert b"Signal FAQ Bot" in client.get("/").data

    def test_contains_benchmark_panel(self, client):
        data = client.get("/").data
        assert b"benchmark" in data.lower() or b"Test" in data


class TestApiSessions:
    def test_returns_200(self, client):
        assert client.get("/api/sessions").status_code == 200

    def test_content_type_is_json(self, client):
        assert "application/json" in client.get("/api/sessions").content_type

    def test_returns_list(self, client):
        assert isinstance(client.get("/api/sessions").get_json(), list)

    def test_sessions_count(self, client):
        assert len(client.get("/api/sessions").get_json()) == 3

    def test_session_has_required_fields(self, client):
        required = {"id", "timestamp", "sender", "message_text",
                    "is_question", "replied", "is_test",
                    "prompt_tokens", "response_tokens"}
        for session in client.get("/api/sessions").get_json():
            assert required <= set(session.keys())

    def test_replied_session_has_reply_fields(self, client):
        data = client.get("/api/sessions").get_json()
        replied = next(s for s in data if s["replied"] and not s["is_test"])
        assert replied["llm_response"] == "We open at 9."
        assert replied["prompt_tokens"] == 120
        assert replied["response_tokens"] == 12

    def test_test_session_flagged(self, client):
        data = client.get("/api/sessions").get_json()
        assert any(s["is_test"] for s in data)


class TestApiSingleSession:
    def test_returns_200_for_existing(self, client):
        sessions = client.get("/api/sessions").get_json()
        sid = sessions[0]["id"]
        assert client.get(f"/api/sessions/{sid}").status_code == 200

    def test_returns_404_for_unknown(self, client):
        assert client.get("/api/sessions/does-not-exist-xyz").status_code == 404

    def test_returned_session_matches_id(self, client):
        sessions = client.get("/api/sessions").get_json()
        sid = sessions[0]["id"]
        data = client.get(f"/api/sessions/{sid}").get_json()
        assert data["id"] == sid


class TestApiStats:
    def test_returns_200(self, client):
        assert client.get("/api/stats").status_code == 200

    def test_has_required_keys(self, client):
        required = {"total", "questions", "non_questions", "replied",
                    "errors", "test_runs"}
        assert required <= set(client.get("/api/stats").get_json().keys())

    def test_total_matches_session_count(self, client):
        stats = client.get("/api/stats").get_json()
        sessions = client.get("/api/sessions").get_json()
        assert stats["total"] == len(sessions)

    def test_test_runs_counted(self, client):
        assert client.get("/api/stats").get_json()["test_runs"] == 1

    def test_errors_zero(self, client):
        assert client.get("/api/stats").get_json()["errors"] == 0

    def test_questions_count_correct(self, client):
        stats = client.get("/api/stats").get_json()
        assert stats["questions"] == 2

    def test_non_questions_count_correct(self, client):
        stats = client.get("/api/stats").get_json()
        assert stats["non_questions"] == 1

    def test_replied_count_correct(self, client):
        stats = client.get("/api/stats").get_json()
        assert stats["replied"] == 2


class TestApiConfig:
    def test_returns_200(self, client):
        assert client.get("/api/config").status_code == 200

    def test_has_required_keys(self, client):
        required = {"token_window", "llm_command", "calendar_command",
                    "question_check_command", "bot_language"}
        data = client.get("/api/config").get_json()
        assert required <= set(data.keys())

    def test_token_window_is_integer(self, client):
        data = client.get("/api/config").get_json()
        assert isinstance(data["token_window"], int)
        assert data["token_window"] > 0


class TestApiBenchmark:
    def test_returns_400_for_missing_message(self, client):
        resp = client.post("/api/benchmark",
                           data=json.dumps({}),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_returns_400_for_empty_message(self, client):
        resp = client.post("/api/benchmark",
                           data=json.dumps({"message": "   "}),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_returns_200_on_success(self, client, store):
        with patch("bot.run_configured_command", return_value="false"), \
             patch("bot.send_direct_message", return_value=True):
            resp = client.post(
                "/api/benchmark",
                data=json.dumps({"message": "Is this a test?"}),
                content_type="application/json",
            )
        assert resp.status_code == 200

    def test_session_flagged_as_test(self, client, store):
        with patch("bot.run_configured_command", return_value="false"):
            resp = client.post(
                "/api/benchmark",
                data=json.dumps({"message": "Test message"}),
                content_type="application/json",
            )
        assert resp.get_json()["is_test"] is True

    def test_no_real_signal_dm_sent(self, client, store):
        sides = ["true", "Calendar text", "The answer."]
        with patch("bot.run_configured_command", side_effect=sides), \
             patch("bot.send_direct_message") as mock_send:
            client.post(
                "/api/benchmark",
                data=json.dumps({"message": "What time is it?"}),
                content_type="application/json",
            )
        mock_send.assert_not_called()

    def test_returns_session_with_pipeline_fields(self, client, store):
        sides = ["true", "Cal text", "Answer here."]
        with patch("bot.run_configured_command", side_effect=sides):
            resp = client.post(
                "/api/benchmark",
                data=json.dumps({"message": "What?"}),
                content_type="application/json",
            )
        data = resp.get_json()
        assert data["is_question"] is True
        assert data["llm_response"] == "Answer here."
        assert data["replied"] is True

    def test_sender_is_benchmark_ui(self, client, store):
        with patch("bot.run_configured_command", return_value="false"):
            resp = client.post(
                "/api/benchmark",
                data=json.dumps({"message": "Hello"}),
                content_type="application/json",
            )
        assert resp.get_json()["sender"] == "benchmark-ui"
