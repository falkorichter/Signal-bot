# GitHub Copilot Instructions for Signal-bot

These instructions apply to every pull request and every AI-assisted code change in this repository.

---

## 1. Documentation

- **Always update and validate the README** when you add, change, or remove any feature or configuration.
- **Update the Development Metadata table** in `README.md` with every PR (version, date, AI tools used).
- Keep `CONTRIBUTING.md` in sync with any new conventions added here.
- Add a **screenshot or terminal-output demo** to the pull request description whenever the change has any visible effect (UI, CLI output, bot messages, etc.).

---

## 2. Versioning

Use **Semantic Versioning** (<https://semver.org/>). The authoritative version lives in `pyproject.toml` under `[project] version`.

| Increment | When |
|-----------|------|
| **MAJOR** | Incompatible API changes |
| **MINOR** | New backward-compatible functionality |
| **PATCH** | Backward-compatible bug fixes |

**Bump the version in `pyproject.toml` with every commit that touches non-Markdown files.**  
Markdown-only commits (README edits, CHANGELOG entries, comment changes) do not require a version bump.

---

## 3. Changelog

Maintain `CHANGELOG.md` following **Keep a Changelog v1.1.0** (<https://keepachangelog.com/en/1.1.0/>).

- Add entries to the `[Unreleased]` section using the categories: `Added`, `Changed`, `Fixed`, `Removed`, `Security`, `Deprecated`.
- Use `YYYY-MM-DD` dates for releases.
- Include GitHub comparison links for every versioned section.
- Entries must be concise but descriptive enough for users to understand the impact.

---

## 4. Testing

- Write **comprehensive tests** for every new feature or bug fix.
- Place tests in the `tests/` directory.
- **One test file per source module** (e.g., `tests/test_bot.py` covers `bot.py` only) so that parallel pull requests editing different modules do not conflict.
- Use `pytest` as the test runner; configure it in `pyproject.toml`.
- Mock all external calls (signal-cli, ollama, file I/O) so tests run offline and without side-effects.
- Verify there are no external code conflicts (dependency versions, import cycles) before merging.

Run tests with:
```bash
pip install -e ".[dev]"
pytest
```

---

## 5. Internationalization (i18n)

- **Localize all user-facing strings** — do not hard-code message text in Python source files; use `i18n.get_message(key)` instead.
- When adding a **new locale key**, add it to **all** supported locale files:
  - `locales/en_US.json` (source of truth)
  - `locales/de.json` (German)
  - `locales/es.json` (Spanish)
  - `locales/fr.json` (French)
  - `locales/ja.json` (Japanese)
  - `locales/pt.json` (Portuguese)
  - `locales/zh_CN.json` (Simplified Chinese)
- For any future frontend/settings UI, add a **language selector** that lets users pick from the supported languages list.

---

## 6. Error Handling & Logging

- **Log all errors to the console** using the standard `logging` module.
- Use `logger.error(...)` for recoverable errors, `logger.exception(...)` when you want the full traceback.
- Never silently swallow exceptions — always log them.
- Prefer structured log messages: `logger.error("Failed to do X: %s", err)`.

---

## 7. UI / UX (current and future)

- **Never disable a button silently.** If a button must be disabled, show a tooltip or inline hint explaining why (e.g., "Waiting for signal-cli to connect…").
- Keep the language selector accessible in the settings panel whenever a settings UI exists.

---

## 8. AI / LLM Tool Transparency

- **Document which AI/LLM tools were used** in the Development Metadata table of `README.md` for every PR.
- Disclose model names and versions where relevant (e.g., `GitHub Copilot`, `ollama/llama3`).
- The runtime LLM (ollama) is part of the product; its model is configurable via `LLM_MODEL`.

---

## 9. Code Style

- Python 3.8+ compatible syntax (`from typing import Optional, List, ...`).
- Use `logging` for all diagnostic output — no bare `print()` statements in library code.
- Follow PEP 8; use `black` and `isort` when available.
- Keep functions focused; each script (`check_question.py`, `query_llm.py`, etc.) must be runnable as a standalone command.
