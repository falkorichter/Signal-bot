"""Tests for check_question.py — question-detection heuristic.

Each test exercises a single aspect of is_question_heuristic so that
changes to the detection logic show up as targeted failures.
"""

import pytest

from check_question import is_question_heuristic


# ---------------------------------------------------------------------------
# Question mark detection
# ---------------------------------------------------------------------------

class TestQuestionMarkDetection:
    def test_explicit_question_mark(self):
        assert is_question_heuristic("Is this a question?") is True

    def test_question_mark_mid_sentence(self):
        assert is_question_heuristic("Hello? Can you help me") is True

    def test_multiple_question_marks(self):
        assert is_question_heuristic("What?? When??") is True

    def test_question_mark_only(self):
        assert is_question_heuristic("?") is True


# ---------------------------------------------------------------------------
# Interrogative-word detection (no question mark)
# ---------------------------------------------------------------------------

class TestInterrogativeWords:
    @pytest.mark.parametrize("text", [
        "What are the opening hours",
        "Where is the office located",
        "When is the next appointment",
        "Who can I contact",
        "Why is the office closed",
        "How do I book",
        "Which room should I go to",
        "Whose appointment is this",
        "Whom should I speak to",
    ])
    def test_wh_words(self, text):
        assert is_question_heuristic(text) is True

    @pytest.mark.parametrize("text", [
        "Can I bring a guest",
        "Could you help me",
        "Would it be possible to reschedule",
        "Should I bring documents",
        "Will there be parking",
        "Shall we proceed",
    ])
    def test_modal_verbs(self, text):
        assert is_question_heuristic(text) is True

    @pytest.mark.parametrize("text", [
        "Is the office open",
        "Are appointments available",
        "Was the meeting cancelled",
        "Were you informed",
        "Do I need to register",
        "Does the office open on Saturdays",
        "Did you receive my form",
        "Has the time changed",
        "Have you confirmed",
        "Had the slot been taken",
        "Am I on the list",
    ])
    def test_auxiliary_verbs(self, text):
        assert is_question_heuristic(text) is True

    def test_question_word_with_trailing_punctuation(self):
        # "what:" should strip the colon before matching
        assert is_question_heuristic("what: is the address") is True


# ---------------------------------------------------------------------------
# Non-questions
# ---------------------------------------------------------------------------

class TestNonQuestions:
    def test_plain_statement(self):
        assert is_question_heuristic("Please send me information about the clinic") is False

    def test_greeting(self):
        assert is_question_heuristic("Hello, good morning!") is False

    def test_exclamation(self):
        assert is_question_heuristic("Thank you very much!") is False

    def test_indirect_question_no_marker(self):
        # Starts with "I" — not a question word
        assert is_question_heuristic("I was wondering if you can help me") is False

    def test_statement_about_wondering(self):
        assert is_question_heuristic("I wonder about the opening times") is False

    def test_empty_string(self):
        assert is_question_heuristic("") is False

    def test_whitespace_only(self):
        assert is_question_heuristic("   ") is False

    def test_number_only(self):
        assert is_question_heuristic("12345") is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_uppercase_question_word(self):
        assert is_question_heuristic("WHAT is the address") is True

    def test_mixed_case_question_word(self):
        assert is_question_heuristic("How CAN I book") is True

    def test_leading_whitespace(self):
        assert is_question_heuristic("  Where is the office?") is True

    def test_single_word_question_word(self):
        assert is_question_heuristic("why") is True

    def test_single_word_non_question(self):
        assert is_question_heuristic("hello") is False
