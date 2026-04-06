"""Tests for commands.py — token utilities and shell command runner."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from commands import (
    _escape_for_dquote,
    estimate_tokens,
    run_configured_command,
    trim_to_token_budget,
)


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------

class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_four_chars_is_one_token(self):
        assert estimate_tokens("abcd") == 1

    def test_eight_chars_is_two_tokens(self):
        assert estimate_tokens("abcdefgh") == 2

    def test_large_text(self):
        text = "a" * 4096
        assert estimate_tokens(text) == 1024

    def test_non_negative(self):
        assert estimate_tokens("x") >= 0

    def test_unicode_counts_by_char(self):
        # "日本語" is 3 chars — each char counted as 1
        assert estimate_tokens("日本語1") == 1


# ---------------------------------------------------------------------------
# trim_to_token_budget
# ---------------------------------------------------------------------------

class TestTrimToTokenBudget:
    def test_no_trim_needed(self):
        text = "Hello world"
        result = trim_to_token_budget(text, 100)
        assert result == text

    def test_trims_long_text(self):
        text = "a" * 400   # 100 tokens
        result = trim_to_token_budget(text, 50)
        assert len(result) <= 200 + 5  # small slack for word-boundary search

    def test_zero_budget_returns_empty(self):
        result = trim_to_token_budget("hello world", 0)
        assert result == ""

    def test_exact_budget_no_trim(self):
        text = "a" * 40  # exactly 10 tokens
        assert trim_to_token_budget(text, 10) == text

    def test_prefers_word_boundary(self):
        # 80-char text with a space near the cut point
        text = ("word " * 20).rstrip()   # 100 chars = 25 tokens
        result = trim_to_token_budget(text, 10)  # budget = 40 chars
        assert not result.endswith(" ")  # should not end mid-word

    def test_logs_warning_when_trimming(self, caplog):
        import logging
        text = "x" * 400
        with caplog.at_level(logging.WARNING, logger="commands"):
            trim_to_token_budget(text, 10, label="test-label")
        assert "test-label" in caplog.text or "Trimmed" in caplog.text


# ---------------------------------------------------------------------------
# _escape_for_dquote
# ---------------------------------------------------------------------------

class TestEscapeForDquote:
    def test_plain_text_unchanged(self):
        assert _escape_for_dquote("hello world") == "hello world"

    def test_escapes_backslash(self):
        assert _escape_for_dquote("a\\b") == "a\\\\b"

    def test_escapes_double_quote(self):
        assert _escape_for_dquote('say "hi"') == 'say \\"hi\\"'

    def test_escapes_dollar(self):
        assert _escape_for_dquote("$HOME") == "\\$HOME"

    def test_escapes_backtick(self):
        assert _escape_for_dquote("`cmd`") == "\\`cmd\\`"

    def test_combined(self):
        result = _escape_for_dquote('$"\\`')
        assert result == '\\$\\"\\\\\\`'


# ---------------------------------------------------------------------------
# run_configured_command
# ---------------------------------------------------------------------------

class TestRunConfiguredCommand:
    def _mock(self, stdout="output", returncode=0, stderr=""):
        return MagicMock(stdout=stdout, returncode=returncode, stderr=stderr)

    # ── Basic execution ──────────────────────────────────────────────────────

    def test_returns_stdout_on_success(self):
        with patch("commands.subprocess.run") as mock_run:
            mock_run.return_value = self._mock(stdout="  answer  ")
            result = run_configured_command("echo test")
        assert result == "answer"

    def test_substitutes_input_placeholder(self):
        captured = {}
        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return self._mock(stdout="true")
        with patch("commands.subprocess.run", side_effect=fake_run):
            run_configured_command('echo "$input$"', input="hello world")
        assert "hello world" in captured["cmd"]

    def test_substitutes_calendar_appointments_placeholder(self):
        captured = {}
        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return self._mock(stdout="ok")
        with patch("commands.subprocess.run", side_effect=fake_run):
            run_configured_command(
                'apfel "$calendar_appointments$ $input$"',
                input="Question?",
                calendar_appointments="2099-01-01: Consult",
            )
        assert "2099-01-01: Consult" in captured["cmd"]
        assert "Question?" in captured["cmd"]

    def test_exports_env_vars(self):
        captured = {}
        def fake_run(cmd, **kw):
            captured["env"] = kw.get("env", {})
            return self._mock(stdout="ok")
        with patch("commands.subprocess.run", side_effect=fake_run):
            run_configured_command("echo", input="hello", calendar_appointments="cal")
        assert captured["env"].get("INPUT") == "hello"
        assert captured["env"].get("CALENDAR_APPOINTMENTS") == "cal"

    def test_shell_true(self):
        captured = {}
        def fake_run(cmd, **kw):
            captured["shell"] = kw.get("shell")
            return self._mock(stdout="ok")
        with patch("commands.subprocess.run", side_effect=fake_run):
            run_configured_command("echo hi")
        assert captured["shell"] is True

    def test_strips_whitespace_from_output(self):
        with patch("commands.subprocess.run") as m:
            m.return_value = self._mock(stdout="\n  result  \n")
            assert run_configured_command("echo") == "result"

    # ── Error handling ───────────────────────────────────────────────────────

    def test_raises_on_empty_template(self):
        with pytest.raises(RuntimeError, match="empty"):
            run_configured_command("")

    def test_raises_on_whitespace_template(self):
        with pytest.raises(RuntimeError, match="empty"):
            run_configured_command("   ")

    def test_raises_on_nonzero_exit(self):
        with patch("commands.subprocess.run") as m:
            m.return_value = self._mock(returncode=1, stderr="oops")
            with pytest.raises(RuntimeError, match="exited 1"):
                run_configured_command("false")

    def test_raises_on_timeout(self):
        with patch("commands.subprocess.run") as m:
            m.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=5)
            with pytest.raises(RuntimeError, match="timed out"):
                run_configured_command("sleep 10", timeout=5)

    def test_raises_on_os_error(self):
        with patch("commands.subprocess.run") as m:
            m.side_effect = OSError("Permission denied")
            with pytest.raises(RuntimeError, match="OS error"):
                run_configured_command("restricted-cmd")

    # ── Security: special characters in values ───────────────────────────────

    def test_double_quote_in_value_is_escaped(self):
        captured = {}
        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return self._mock(stdout="ok")
        with patch("commands.subprocess.run", side_effect=fake_run):
            run_configured_command('echo "$input$"', input='say "hello"')
        # The injected double-quote must be escaped
        assert '\\"' in captured["cmd"]
        assert '"hello"' not in captured["cmd"].replace('\\"', "")

    def test_dollar_in_value_is_escaped(self):
        captured = {}
        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return self._mock(stdout="ok")
        with patch("commands.subprocess.run", side_effect=fake_run):
            run_configured_command('echo "$input$"', input="$HOME")
        assert "\\$HOME" in captured["cmd"]

    # ── Unsubstituted placeholder warning ────────────────────────────────────

    def test_warns_about_unsubstituted_placeholders(self, caplog):
        import logging
        def fake_run(cmd, **kw):
            return self._mock(stdout="ok")
        with patch("commands.subprocess.run", side_effect=fake_run):
            with caplog.at_level(logging.WARNING, logger="commands"):
                run_configured_command("echo $missing_var$")
        assert "missing_var" in caplog.text or "Unsubstituted" in caplog.text

    # ── Timeout parameter forwarded ──────────────────────────────────────────

    def test_timeout_forwarded_to_subprocess(self):
        captured = {}
        def fake_run(cmd, **kw):
            captured["timeout"] = kw.get("timeout")
            return self._mock(stdout="ok")
        with patch("commands.subprocess.run", side_effect=fake_run):
            run_configured_command("echo", timeout=77)
        assert captured["timeout"] == 77
