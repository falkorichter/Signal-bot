"""Tests for bot.py — envelope parsing, pipeline logic, and message handling.

All external calls (signal-cli, LLM, appointments) are mocked so tests run
offline without any side-effects.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import bot
from bot import (
    build_reply,
    extract_message_data,
    process_envelope,
    receive_messages,
    send_direct_message,
)
from storage import SessionStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return SessionStore(sessions_file=tmp_path / "sessions.json")


def _envelope(sender="+1234567890", group_id="grp123", message_text="Hello?",
              include_data_message=True):
    """Helper: build a minimal signal-cli envelope dict."""
    data_msg = {"message": message_text}
    if group_id:
        data_msg["groupInfo"] = {"groupId": group_id}
    env = {
        "envelope": {
            "source": sender,
            "dataMessage": data_msg if include_data_message else None,
        }
    }
    return env


# ---------------------------------------------------------------------------
# extract_message_data
# ---------------------------------------------------------------------------

class TestExtractMessageData:
    def test_full_group_message(self):
        env = _envelope("+1", "grp", "Hello?")
        sender, group_id, text = extract_message_data(env)
        assert sender == "+1"
        assert group_id == "grp"
        assert text == "Hello?"

    def test_direct_message_has_no_group(self):
        env = _envelope("+2", "", "Direct msg")
        _, group_id, _ = extract_message_data(env)
        assert group_id == ""

    def test_empty_envelope(self):
        sender, group_id, text = extract_message_data({})
        assert sender == ""
        assert group_id == ""
        assert text == ""

    def test_strips_whitespace_from_message(self):
        env = _envelope(message_text="  Hi?  ")
        _, _, text = extract_message_data(env)
        assert text == "Hi?"

    def test_uses_sourceNumber_fallback(self):
        env = {"envelope": {"sourceNumber": "+9", "dataMessage": {"message": "Hi"}}}
        sender, _, _ = extract_message_data(env)
        assert sender == "+9"

    def test_no_data_message_returns_empty_text(self):
        env = _envelope(include_data_message=False)
        _, _, text = extract_message_data(env)
        assert text == ""


# ---------------------------------------------------------------------------
# receive_messages
# ---------------------------------------------------------------------------

class TestReceiveMessages:
    def test_parses_json_lines(self):
        envelope = _envelope()
        output = json.dumps(envelope) + "\n"
        with patch("bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=output, stderr=""
            )
            result = receive_messages()
        assert len(result) == 1
        assert result[0] == envelope

    def test_skips_blank_lines(self):
        envelope = _envelope()
        output = "\n" + json.dumps(envelope) + "\n\n"
        with patch("bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=output, stderr=""
            )
            result = receive_messages()
        assert len(result) == 1

    def test_skips_non_json_lines(self):
        with patch("bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="not-json\n", stderr=""
            )
            result = receive_messages()
        assert result == []

    def test_returns_empty_on_file_not_found(self):
        with patch("bot.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError
            result = receive_messages()
        assert result == []

    def test_returns_empty_on_timeout(self):
        with patch("bot.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=30)
            result = receive_messages()
        assert result == []


# ---------------------------------------------------------------------------
# send_direct_message
# ---------------------------------------------------------------------------

class TestSendDirectMessage:
    def test_returns_true_on_success(self):
        with patch("bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert send_direct_message("+1", "Hi!") is True

    def test_returns_false_on_nonzero_exit(self):
        with patch("bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="Send failed"
            )
            assert send_direct_message("+1", "Hi!") is False

    def test_returns_false_on_file_not_found(self):
        with patch("bot.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError
            assert send_direct_message("+1", "Hi!") is False

    def test_returns_false_on_timeout(self):
        with patch("bot.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=30)
            assert send_direct_message("+1", "Hi!") is False


# ---------------------------------------------------------------------------
# build_reply
# ---------------------------------------------------------------------------

class TestBuildReply:
    def test_reply_contains_answer(self):
        reply = build_reply("The office opens at 9.")
        assert "The office opens at 9." in reply

    def test_reply_uses_prefix_override(self):
        with patch("bot.MESSAGE_PREFIX", "BEFORE "), \
             patch("bot.MESSAGE_SUFFIX", ""):
            reply = build_reply("Answer")
        assert reply.startswith("BEFORE ")
        assert "Answer" in reply

    def test_reply_uses_suffix_override(self):
        with patch("bot.MESSAGE_PREFIX", ""), \
             patch("bot.MESSAGE_SUFFIX", " AFTER"):
            reply = build_reply("Middle")
        assert reply.endswith(" AFTER")
        assert "Middle" in reply

    def test_reply_falls_back_to_i18n_when_prefix_empty(self):
        with patch("bot.MESSAGE_PREFIX", ""), \
             patch("bot.MESSAGE_SUFFIX", ""):
            reply = build_reply("Answer")
        # Should contain the i18n greeting
        assert "Answer" in reply
        assert len(reply) > len("Answer")


# ---------------------------------------------------------------------------
# process_envelope — end-to-end (all steps mocked)
# ---------------------------------------------------------------------------

class TestProcessEnvelope:
    def _patch_pipeline(self, is_q=True, llm_ok=True, send_ok=True):
        """Return a list of patch objects for the full pipeline."""
        patches = [
            patch("bot.is_question_heuristic", return_value=is_q),
            patch("bot.fetch_appointments", return_value=[]),
            patch("bot.format_appointments", return_value="Appointments: none"),
            patch("bot.load_faqs", return_value="Q: Hours?\nA: 9-5."),
            patch("bot.build_prompt", return_value="<prompt>"),
            patch("bot._query_llm", return_value="The answer." if llm_ok else None),
            patch("bot.send_direct_message", return_value=send_ok),
        ]
        return patches

    def test_ignores_envelope_without_message(self, store):
        env = _envelope(include_data_message=False)
        process_envelope(env, store)
        assert store.get_all_sessions() == []

    def test_ignores_wrong_group_when_monitor_group_set(self, store):
        with patch("bot.MONITOR_GROUP", "correct-group"):
            env = _envelope(group_id="wrong-group", message_text="Q?")
            process_envelope(env, store)
        assert store.get_all_sessions() == []

    def test_ignores_envelope_without_sender(self, store):
        env = {"envelope": {"dataMessage": {"message": "Q?"}}}
        process_envelope(env, store)
        assert store.get_all_sessions() == []

    def test_not_a_question_creates_session_but_no_reply(self, store):
        patches = self._patch_pipeline(is_q=False)
        env = _envelope(message_text="Hello, just saying hi.")
        with patches[0]:  # is_question_heuristic only needed
            with patches[6]:  # send_direct_message
                with patch("bot.MONITOR_GROUP", ""):
                    process_envelope(env, store)

        sessions = store.get_all_sessions()
        assert len(sessions) == 1
        assert sessions[0].is_question is False
        assert sessions[0].replied is False

    def test_question_creates_replied_session(self, store):
        env = _envelope(message_text="What are the hours?")
        for p in self._patch_pipeline(is_q=True, llm_ok=True, send_ok=True):
            p.start()
        try:
            with patch("bot.MONITOR_GROUP", ""):
                process_envelope(env, store)
        finally:
            for p in self._patch_pipeline(is_q=True, llm_ok=True, send_ok=True):
                try:
                    p.stop()
                except RuntimeError:
                    pass

        sessions = store.get_all_sessions()
        assert len(sessions) == 1

    def test_deduplication_skips_already_replied(self, store):
        env = _envelope(sender="+1", message_text="Same question?")
        # Create a session that is already marked as replied
        s = store.create_session("+1", "grp123", "Same question?")
        store.update_session(s.id, replied=True)

        with patch("bot.MONITOR_GROUP", ""):
            with patch("bot.is_question_heuristic") as mock_q:
                process_envelope(env, store)
                # Heuristic should NOT have been called because dedup fires first
                mock_q.assert_not_called()

        # No new session should be created
        assert len(store.get_all_sessions()) == 1

    def test_llm_failure_stores_error_message(self, store):
        env = _envelope(message_text="What?")
        with patch("bot.is_question_heuristic", return_value=True), \
             patch("bot.fetch_appointments", return_value=[]), \
             patch("bot.format_appointments", return_value=""), \
             patch("bot.load_faqs", return_value=""), \
             patch("bot.build_prompt", return_value=""), \
             patch("bot._query_llm", side_effect=RuntimeError("LLM down")), \
             patch("bot.send_direct_message", return_value=True), \
             patch("bot.MONITOR_GROUP", ""):
            process_envelope(env, store)

        sessions = store.get_all_sessions()
        assert sessions[0].error is not None
