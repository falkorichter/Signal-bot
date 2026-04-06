"""Tests for query_llm.py — FAQ loading, prompt building, and LLM querying."""

import json
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from query_llm import build_prompt, fetch_appointments_text, load_faqs, query_llm


# ---------------------------------------------------------------------------
# load_faqs
# ---------------------------------------------------------------------------

class TestLoadFaqs:
    def test_loads_content_from_existing_file(self, tmp_path):
        faq = tmp_path / "faqs.txt"
        faq.write_text("Q: Test?\nA: Yes.", encoding="utf-8")
        result = load_faqs(str(faq))
        assert "Q: Test?" in result
        assert "A: Yes." in result

    def test_returns_notice_for_missing_file(self, tmp_path):
        result = load_faqs(str(tmp_path / "nonexistent.txt"))
        assert "No FAQ data" in result or "not found" in result.lower()

    def test_strips_trailing_whitespace(self, tmp_path):
        faq = tmp_path / "faqs.txt"
        faq.write_text("  Q: A?\nA: B.  \n\n", encoding="utf-8")
        result = load_faqs(str(faq))
        assert not result.endswith("\n")

    def test_unicode_content_preserved(self, tmp_path):
        faq = tmp_path / "faqs.txt"
        faq.write_text("Q: Öffnungszeiten?\nA: Mo–Fr 9–17 Uhr.", encoding="utf-8")
        result = load_faqs(str(faq))
        assert "Öffnungszeiten" in result


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    QUESTION = "What are the opening hours?"
    FAQS = "Q: Hours?\nA: 9-5 weekdays."
    APPTS = "Upcoming appointments:\n- 2099-01-01 at 09:00: Consultation"

    def test_prompt_contains_question(self):
        p = build_prompt(self.QUESTION, self.FAQS, self.APPTS)
        assert self.QUESTION in p

    def test_prompt_contains_faqs(self):
        p = build_prompt(self.QUESTION, self.FAQS, self.APPTS)
        assert self.FAQS in p

    def test_prompt_contains_appointments(self):
        p = build_prompt(self.QUESTION, self.FAQS, self.APPTS)
        assert self.APPTS in p

    def test_prompt_is_string(self):
        p = build_prompt(self.QUESTION, self.FAQS, self.APPTS)
        assert isinstance(p, str)

    def test_prompt_is_non_empty(self):
        p = build_prompt(self.QUESTION, self.FAQS, self.APPTS)
        assert len(p) > 0

    def test_prompt_has_answer_section_header(self):
        p = build_prompt(self.QUESTION, self.FAQS, self.APPTS)
        assert "Answer" in p or "answer" in p

    def test_empty_faqs_does_not_crash(self):
        p = build_prompt(self.QUESTION, "", self.APPTS)
        assert isinstance(p, str)

    def test_empty_appointments_does_not_crash(self):
        p = build_prompt(self.QUESTION, self.FAQS, "")
        assert isinstance(p, str)


# ---------------------------------------------------------------------------
# query_llm
# ---------------------------------------------------------------------------

class TestQueryLlm:
    def _mock_response(self, body: dict):
        """Return a mock context-manager that simulates urllib urlopen."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(body).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_returns_response_text_on_success(self):
        with patch("query_llm.urllib.request.urlopen") as mock_open:
            mock_open.return_value = self._mock_response(
                {"response": "Office hours are 9-5."}
            )
            result = query_llm("What are the hours?")
        assert result == "Office hours are 9-5."

    def test_strips_whitespace_from_response(self):
        with patch("query_llm.urllib.request.urlopen") as mock_open:
            mock_open.return_value = self._mock_response(
                {"response": "  Answer.  "}
            )
            result = query_llm("Q?")
        assert result == "Answer."

    def test_raises_runtime_error_on_url_error(self):
        with patch("query_llm.urllib.request.urlopen") as mock_open:
            mock_open.side_effect = urllib.error.URLError("Connection refused")
            with pytest.raises(RuntimeError, match="connect"):
                query_llm("Q?")

    def test_raises_runtime_error_on_empty_response(self):
        with patch("query_llm.urllib.request.urlopen") as mock_open:
            mock_open.return_value = self._mock_response({"response": ""})
            with pytest.raises(RuntimeError, match="empty"):
                query_llm("Q?")

    def test_raises_runtime_error_when_response_key_missing(self):
        with patch("query_llm.urllib.request.urlopen") as mock_open:
            mock_open.return_value = self._mock_response({})
            with pytest.raises(RuntimeError):
                query_llm("Q?")


# ---------------------------------------------------------------------------
# fetch_appointments_text
# ---------------------------------------------------------------------------

class TestFetchAppointmentsText:
    def test_returns_string(self):
        with patch("query_llm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="- 2099-01-01 at 09:00: Visit\n", stderr=""
            )
            result = fetch_appointments_text()
        assert isinstance(result, str)

    def test_returns_error_notice_on_nonzero_exit(self):
        with patch("query_llm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="Error"
            )
            result = fetch_appointments_text()
        assert "Could not fetch" in result or "error" in result.lower()

    def test_returns_notice_on_timeout(self):
        import subprocess
        with patch("query_llm.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=30)
            result = fetch_appointments_text()
        assert "timed out" in result or "timeout" in result.lower()
