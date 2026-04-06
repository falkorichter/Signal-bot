# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-04-06

### Added
- **Configurable pipeline commands** via environment variables:
  - `QUESTION_CHECK_COMMAND` — shell command to detect questions (`$input$` placeholder)
  - `CALENDAR_COMMAND` — shell command to fetch appointment/calendar data
  - `LLM_COMMAND` — shell command to query the LLM (`$input$`, `$calendar_appointments$` placeholders)
- **`commands.py`** — safe shell runner with `$var$` substitution, double-quote escaping, and env-var export
- **Token-window management** (`TOKEN_WINDOW`, default 4096 for apfel):
  - `estimate_tokens(text)` — rough 1-token-per-4-chars approximation
  - `trim_to_token_budget(text, max_tokens)` — smart word-boundary truncation with warning log
  - Calendar context automatically trimmed when it would overflow the window
- **apfel integration** (Apple Intelligence on-device LLM, macOS 26+):
  - apfel is the default recommended LLM; set `LLM_COMMAND=apfel "$calendar_appointments$ $input$"`
  - Also works with `apfel --serve` (OpenAI-compatible endpoint) or any other local LLM CLI
- **Web benchmark / test panel** — enter any message in the browser and run the full pipeline without sending a real Signal message; session flagged `is_test=true`
- **`/api/benchmark`** (`POST`) — JSON endpoint powering the web test panel
- **`/api/config`** (`GET`) — returns current bot configuration (commands, token window, language, etc.)
- **Token visualisation** in the web dashboard:
  - Live character / estimated-token counter while typing in the benchmark textarea
  - Colour-coded progress bar (green → orange → red) relative to `TOKEN_WINDOW`
  - Per-session token bar in the pipeline view (`prompt_tokens`, `response_tokens`)
- **Config offcanvas drawer** in the web UI — shows all live configuration values
- `is_test`, `prompt_tokens`, `response_tokens` fields added to `Session` / `sessions.json`
- `test_runs` counter added to `/api/stats`
- `query_llm.py` honours `CALENDAR_APPOINTMENTS` env-var (set by `run_configured_command`) to avoid redundant calendar fetches
- Shared `run_pipeline()` function in `bot.py` — used by both the polling loop and the web benchmark
- `tests/test_commands.py` — comprehensive tests for token utilities and shell runner

### Changed
- Bot pipeline steps now use configurable shell commands instead of hard-coded Python function calls
- `process_envelope()` delegates to `run_pipeline()` for cleaner code sharing
- Web dashboard benchmark button shows "Running..." label while disabled (copilot-instructions UI rule)
- `requirements.txt` and `pyproject.toml` reflect Flask as a runtime dependency

## [0.1.0] - 2026-04-06

### Added
- Initial Signal FAQ Bot implementation
- `bot.py` — main polling loop monitoring a Signal group via signal-cli
- `check_question.py` — heuristic question detection (question marks, interrogative words)
- `fetch_appointments.py` — pluggable appointment fetcher (stub implementation)
- `query_llm.py` — ollama LLM query with FAQ + appointment context
- `storage.py` — thread-safe, atomically-written JSON session store with deduplication
- `web_app.py` — Flask dashboard with live auto-refreshing session list
- `templates/index.html` — pipeline visualisation per session (received → question? → appointments → LLM → sent DM)
- `i18n.py` + `locales/{en_US,de,es,fr,ja,pt,zh_CN}.json` — 7-language support for bot messages
- `config.py` — all settings via environment variables with optional `.env` file support
- `faqs.txt` — sample FAQ database
- `.github/copilot-instructions.md` — repository coding standards (versioning, testing, i18n, logging, UI)
- `CONTRIBUTING.md` — contributor guide
- Comprehensive test suite: `tests/test_{check_question,fetch_appointments,query_llm,bot,storage,web_app,i18n}.py`

[Unreleased]: https://github.com/falkorichter/Signal-bot/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/falkorichter/Signal-bot/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/falkorichter/Signal-bot/releases/tag/v0.1.0
