# Contributing to Signal FAQ Bot

Thank you for contributing! Please read these guidelines before opening a PR.

---

## Repository Standards (from `.github/copilot-instructions.md`)

All standards below are enforced for every PR — including AI-assisted ones.
The canonical source is `.github/copilot-instructions.md`; this file is a
human-friendly summary.

---

## 1. Getting Started

```bash
# 1. Clone
git clone https://github.com/falkorichter/Signal-bot.git
cd Signal-bot

# 2. Install runtime + dev dependencies
pip install -e ".[dev]"
pip install Flask  # runtime dependency

# 3. Copy and configure environment
cp .env.example .env
# Edit .env: set SIGNAL_NUMBER, optionally CALENDAR_COMMAND / LLM_COMMAND

# 4. Run tests
pytest

# 5. Start the bot (one terminal)
python bot.py

# 6. Start the web dashboard (another terminal)
python web_app.py
# Open http://localhost:5000/
```

---

## 2. Versioning

We use **Semantic Versioning** — bump `version` in `pyproject.toml` with
every commit that touches non-Markdown files:

| Change type | Bump |
|-------------|------|
| Breaking API change | MAJOR (`1.0.0`) |
| New backward-compatible feature | MINOR (`0.2.0`) |
| Bug fix | PATCH (`0.2.1`) |

---

## 3. Changelog

Add an entry to `CHANGELOG.md` under `[Unreleased]` for every PR using one
of the standard categories: `Added`, `Changed`, `Fixed`, `Removed`,
`Security`, `Deprecated`.

---

## 4. Tests

- One test file per source module in `tests/` (e.g. `tests/test_bot.py` only
  covers `bot.py`).
- Mock all external calls (signal-cli, shell commands, HTTP) — tests must run
  offline.
- Run the full suite with `pytest` before pushing.

---

## 5. Pipeline Commands

All three pipeline steps are configurable via environment variables:

| Variable | Default | Description |
|---|---|---|
| `QUESTION_CHECK_COMMAND` | `python check_question.py "$input$"` | Detect questions; must print `true` or `false` |
| `CALENDAR_COMMAND` | `python fetch_appointments.py` | Fetch upcoming appointments |
| `LLM_COMMAND` | `python query_llm.py "$input$"` | Query LLM; `$calendar_appointments$` also available |

**apfel** (Apple Intelligence, macOS 26+, 4096-token window):
```bash
LLM_COMMAND='apfel "$calendar_appointments$ These are the next appointments. $input$"'
TOKEN_WINDOW=4096
```

**ollama** (any platform):
```bash
LLM_COMMAND='ollama run llama3 "$calendar_appointments$ $input$"'
TOKEN_WINDOW=8192  # adjust per model
```

---

## 6. Internationalization

- All user-facing strings must use `i18n.get_message(key)` — never hard-code text.
- When adding a new locale key, add it to **all** 7 locale files:
  `en_US`, `de`, `es`, `fr`, `ja`, `pt`, `zh_CN`.
- Tests in `tests/test_i18n.py` enforce completeness.

---

## 7. Logging

- Use `logging.getLogger(__name__)` — never bare `print()` in library code.
- All errors must be logged: `logger.error(...)` or `logger.exception(...)`.

---

## 8. Web UI Rules

- **Never disable a button silently.** Change the label to explain why
  (e.g. `"⏳ Running pipeline…"`) when it is temporarily disabled.
- Token-window progress bars must update immediately as the user types.

---

## 9. Documentation

- **Update `README.md`** with any feature or configuration change.
- **Update the Development Metadata table** in `README.md` with every PR.
- **Add a screenshot** to the PR description whenever the change has a
  visible effect (UI, CLI output, bot messages).

---

## 10. AI / LLM Tools

Document any AI tools used in the **Development Metadata** table of `README.md`.
