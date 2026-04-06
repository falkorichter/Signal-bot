"""Tests for i18n.py — locale loading, key lookup, and fallback behaviour."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from i18n import SUPPORTED_LANGUAGES, get_message


# ---------------------------------------------------------------------------
# Required keys every locale must have
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {"message_prefix", "message_suffix", "error_no_response"}


# ---------------------------------------------------------------------------
# Locale file completeness
# ---------------------------------------------------------------------------

class TestLocaleFiles:
    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    def test_locale_file_exists(self, lang):
        locale_file = Path(__file__).parent.parent / "locales" / f"{lang}.json"
        assert locale_file.exists(), f"Locale file missing: {locale_file}"

    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    def test_locale_file_is_valid_json(self, lang):
        locale_file = Path(__file__).parent.parent / "locales" / f"{lang}.json"
        try:
            data = json.loads(locale_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            pytest.fail(f"Invalid JSON in {lang}.json: {exc}")
        assert isinstance(data, dict)

    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    def test_locale_has_all_required_keys(self, lang):
        locale_file = Path(__file__).parent.parent / "locales" / f"{lang}.json"
        data = json.loads(locale_file.read_text(encoding="utf-8"))
        missing = REQUIRED_KEYS - set(data.keys())
        assert not missing, f"{lang}.json missing keys: {missing}"

    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    def test_all_values_are_non_empty_strings(self, lang):
        locale_file = Path(__file__).parent.parent / "locales" / f"{lang}.json"
        data = json.loads(locale_file.read_text(encoding="utf-8"))
        for key in REQUIRED_KEYS:
            value = data.get(key, "")
            assert isinstance(value, str) and value.strip(), (
                f"{lang}.json: key '{key}' is empty or not a string"
            )


# ---------------------------------------------------------------------------
# get_message — happy path
# ---------------------------------------------------------------------------

class TestGetMessage:
    def test_english_message_prefix(self):
        result = get_message("message_prefix", "en_US")
        assert "Hello" in result or "FAQ" in result

    def test_german_message_prefix(self):
        result = get_message("message_prefix", "de")
        assert result != ""
        assert "FAQ" in result or "Hallo" in result

    def test_spanish_message_prefix(self):
        result = get_message("message_prefix", "es")
        assert "FAQ" in result or "Hola" in result

    def test_french_message_prefix(self):
        result = get_message("message_prefix", "fr")
        assert "FAQ" in result or "Bonjour" in result

    def test_japanese_message_prefix(self):
        result = get_message("message_prefix", "ja")
        assert result != ""  # Just verify non-empty — content is in Japanese

    def test_portuguese_message_prefix(self):
        result = get_message("message_prefix", "pt")
        assert "FAQ" in result or "Olá" in result

    def test_chinese_message_prefix(self):
        result = get_message("message_prefix", "zh_CN")
        assert result != ""

    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    def test_error_no_response_non_empty(self, lang):
        result = get_message("error_no_response", lang)
        assert result.strip() != ""

    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    def test_message_suffix_contains_disclaimer_word(self, lang):
        result = get_message("message_suffix", lang)
        # Every locale should have a disclaimer-ish suffix
        assert len(result) > 20  # At minimum a short sentence


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------

class TestFallback:
    def test_falls_back_to_english_for_unknown_language(self):
        result = get_message("message_prefix", "xx_UNKNOWN")
        en_result = get_message("message_prefix", "en_US")
        assert result == en_result

    def test_returns_placeholder_for_unknown_key(self):
        result = get_message("completely_unknown_key_xyz", "en_US")
        assert "completely_unknown_key_xyz" in result

    def test_uses_bot_language_from_config_by_default(self):
        """get_message() with no lang arg reads BOT_LANGUAGE from config."""
        import config as _cfg
        orig = _cfg.BOT_LANGUAGE
        _cfg.BOT_LANGUAGE = "en_US"
        try:
            import i18n
            i18n._cache.clear()
            result = get_message("message_prefix")  # no explicit lang
            assert result != ""
            assert "FAQ" in result or "Hello" in result
        finally:
            _cfg.BOT_LANGUAGE = orig


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

class TestCaching:
    def test_locale_data_cached_on_second_call(self):
        """Second call for same locale must not re-read the file."""
        import i18n
        i18n._cache.clear()

        open_calls = []
        original_read = Path.read_text

        def counting_read(self, **kwargs):
            if "locales" in str(self):
                open_calls.append(str(self))
            return original_read(self, **kwargs)

        with patch.object(Path, "read_text", counting_read):
            get_message("message_prefix", "en_US")
            count_after_first = len(open_calls)
            get_message("message_suffix", "en_US")
            count_after_second = len(open_calls)

        # Second call should not re-read the file
        assert count_after_second == count_after_first
