"""Tests for bot.py -- envelope parsing, pipeline logic, and message handling.

All external calls (signal-cli, shell commands) are mocked.
"""

import json
import subprocess
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import bot
from bot import (
    build_reply,
    extract_message_data,
    process_envelope,
    receive_messages,
    run_pipeline,
    send_direct_message,
)
from storage import SessionStore


@pytest.fixture
def store(tmp_path):
    return SessionStore(sessions_file=tmp_path / "sessions.json")


def _envelope(sender="+1234567890", group_id="grp123", message_text="Hello?",
              include_data_message=True):
    data_msg = {"message": message_text}
    if group_id:
        data_msg["groupInfo"] = {"groupId": group_id}
    return {
        "envelope": {
            "source": sender,
            "dataMessage": data_msg if include_data_message else None,
        }
    }


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
        assert sender == group_id == text == ""

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


class TestReceiveMessages:
    def test_parses_json_lines(self):
        envelope = _envelope()
        with patch("bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=json.dumps(envelope) + "\n", stderr=""
            )
            result = receive_messages()
        assert len(result) == 1
        assert result[0] == envelope

    def test_skips_blank_lines(self):
        envelope = _envelope()
        with patch("bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="\n" + json.dumps(envelope) + "\n\n", stderr=""
            )
            result = receive_messages()
        assert len(result) == 1

    def test_skips_non_json_lines(self):
        with patch("bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="not-json\n", stderr=""
            )
            assert receive_messages() == []

    def test_returns_empty_on_file_not_found(self):
        with patch("bot.subprocess.run", side_effect=FileNotFoundError):
            assert receive_messages() == []

    def test_returns_empty_on_timeout(self):
        with patch("bot.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="x", timeout=30)):
            assert receive_messages() == []


class TestSendDirectMessage:
    def test_returns_true_on_success(self):
        with patch("bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert send_direct_message("+1", "Hi!") is True

    def test_returns_false_on_nonzero_exit(self):
        with patch("bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Send failed")
            assert send_direct_message("+1", "Hi!") is False

    def test_returns_false_on_file_not_found(self):
        with patch("bot.subprocess.run", side_effect=FileNotFoundError):
            assert send_direct_message("+1", "Hi!") is False

    def test_returns_false_on_timeout(self):
        with patch("bot.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="x", timeout=30)):
            assert send_direct_message("+1", "Hi!") is False


class TestBuildReply:
    def test_reply_contains_answer(self):
        assert "The office opens at 9." in build_reply("The office opens at 9.")

    def test_reply_uses_prefix_override(self):
        with patch("bot.MESSAGE_PREFIX", "BEFORE "), patch("bot.MESSAGE_SUFFIX", ""):
            reply = build_reply("Answer")
        assert reply.startswith("BEFORE ")

    def test_reply_uses_suffix_override(self):
        with patch("bot.MESSAGE_PREFIX", ""), patch("bot.MESSAGE_SUFFIX", " AFTER"):
            reply = build_reply("Middle")
        assert reply.endswith(" AFTER")

    def test_falls_back_to_i18n_when_overrides_empty(self):
        with patch("bot.MESSAGE_PREFIX", ""), patch("bot.MESSAGE_SUFFIX", ""):
            reply = build_reply("Answer")
        assert "Answer" in reply
        assert len(reply) > len("Answer")


class TestRunPipeline:
    def test_not_a_question_session_created_not_replied(self, store):
        with patch("bot.run_configured_command", return_value="false"), \
             patch("bot.send_direct_message", return_value=True):
            session = run_pipeline("Hi there", "+1", "grp", store)

        assert session.is_question is False
        assert session.replied is False
        assert len(store.get_all_sessions()) == 1

    def test_question_full_pipeline_marks_replied(self, store):
        sides = ["true", "Appointments: none", "We open at 9."]
        with patch("bot.run_configured_command", side_effect=sides), \
             patch("bot.send_direct_message", return_value=True):
            session = run_pipeline("What are the hours?", "+1", "grp", store)

        assert session.is_question is True
        assert session.appointments_text == "Appointments: none"
        assert session.llm_response == "We open at 9."
        assert session.replied is True

    def test_is_test_flag_stored(self, store):
        with patch("bot.run_configured_command", return_value="false"):
            session = run_pipeline("Test msg", "benchmark-ui", "", store, is_test=True)
        assert session.is_test is True

    def test_no_dm_sent_when_send_dm_false(self, store):
        sides = ["true", "Cal", "Answer"]
        with patch("bot.run_configured_command", side_effect=sides), \
             patch("bot.send_direct_message") as mock_send:
            run_pipeline("Q?", "+1", "grp", store, send_dm=False)
        mock_send.assert_not_called()

    def test_session_still_marked_replied_when_send_dm_false(self, store):
        sides = ["true", "Cal", "Answer"]
        with patch("bot.run_configured_command", side_effect=sides):
            session = run_pipeline("Q?", "+1", "grp", store, send_dm=False)
        assert session.replied is True

    def test_llm_failure_stores_error(self, store):
        calls = [0]

        def side_effect(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                return "true"
            elif calls[0] == 2:
                return "Calendar text"
            else:
                raise RuntimeError("LLM down")

        with patch("bot.run_configured_command", side_effect=side_effect), \
             patch("bot.send_direct_message", return_value=True):
            session = run_pipeline("What?", "+1", "grp", store)

        assert session.error is not None

    def test_prompt_tokens_stored(self, store):
        sides = ["true", "Cal text", "Answer"]
        with patch("bot.run_configured_command", side_effect=sides), \
             patch("bot.send_direct_message", return_value=True):
            session = run_pipeline("Q?", "+1", "grp", store)
        assert session.prompt_tokens is not None
        assert isinstance(session.prompt_tokens, int)

    def test_response_tokens_stored(self, store):
        sides = ["true", "Cal text", "The answer is here."]
        with patch("bot.run_configured_command", side_effect=sides), \
             patch("bot.send_direct_message", return_value=True):
            session = run_pipeline("Q?", "+1", "grp", store)
        assert session.response_tokens is not None
        assert session.response_tokens > 0


class TestProcessEnvelope:
    def test_ignores_envelope_without_message(self, store):
        env = _envelope(include_data_message=False)
        with patch("bot.MONITOR_GROUP", ""):
            process_envelope(env, store)
        assert store.get_all_sessions() == []

    def test_ignores_wrong_group_when_monitor_group_set(self, store):
        env = _envelope(group_id="wrong-group", message_text="Q?")
        with patch("bot.MONITOR_GROUP", "correct-group"):
            process_envelope(env, store)
        assert store.get_all_sessions() == []

    def test_ignores_envelope_without_sender(self, store):
        env = {"envelope": {"dataMessage": {"message": "Q?"}}}
        with patch("bot.MONITOR_GROUP", ""):
            process_envelope(env, store)
        assert store.get_all_sessions() == []

    def test_deduplication_skips_already_replied(self, store):
        env = _envelope(sender="+1", message_text="Same question?")
        s = store.create_session("+1", "grp123", "Same question?")
        store.update_session(s.id, replied=True)

        with patch("bot.MONITOR_GROUP", ""), \
             patch("bot.run_configured_command") as mock_cmd:
            process_envelope(env, store)
            mock_cmd.assert_not_called()

        assert len(store.get_all_sessions()) == 1
