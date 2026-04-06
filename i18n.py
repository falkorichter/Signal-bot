"""Internationalization (i18n) support for the Signal FAQ Bot.

Usage::

    from i18n import get_message
    text = get_message("message_prefix")          # uses BOT_LANGUAGE from config
    text = get_message("message_prefix", "de")    # explicit language override
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

LOCALES_DIR: Path = Path(__file__).parent / "locales"

SUPPORTED_LANGUAGES = ["en_US", "de", "es", "fr", "ja", "pt", "zh_CN"]
DEFAULT_LANGUAGE = "en_US"

# In-memory cache: lang -> {key: value}
_cache: dict = {}


def _load_locale(lang: str) -> dict:
    """Load and cache a locale JSON file.  Returns an empty dict on error."""
    if lang in _cache:
        return _cache[lang]

    path = LOCALES_DIR / f"{lang}.json"
    try:
        _cache[lang] = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.error("Locale file not found: %s", path)
        _cache[lang] = {}
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in locale file %s: %s", path, exc)
        _cache[lang] = {}
    return _cache[lang]


def get_message(key: str, lang: Optional[str] = None) -> str:
    """Return the localized string for *key* in the requested *lang*.

    Falls back to ``en_US`` when the key is absent in the requested language.
    Returns a placeholder string ``[key]`` if the key is missing everywhere.

    Args:
        key:  Locale key, e.g. ``"message_prefix"``.
        lang: BCP-47-style language code, e.g. ``"de"`` or ``"en_US"``.
              Defaults to ``BOT_LANGUAGE`` from :mod:`config`.
    """
    if lang is None:
        from config import BOT_LANGUAGE  # deferred to avoid circular import
        lang = BOT_LANGUAGE

    locale_data = _load_locale(lang)
    if key in locale_data:
        return locale_data[key]

    if lang != DEFAULT_LANGUAGE:
        logger.debug(
            "Key '%s' not found in '%s', falling back to '%s'",
            key, lang, DEFAULT_LANGUAGE,
        )
        default_data = _load_locale(DEFAULT_LANGUAGE)
        if key in default_data:
            return default_data[key]

    logger.warning("Message key '%s' not found in any locale", key)
    return f"[{key}]"
