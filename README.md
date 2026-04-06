# Signal FAQ Bot

[![Version](https://img.shields.io/badge/version-0.2.0-blue)](CHANGELOG.md)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)](https://python.org)

A Signal messenger bot that monitors a group channel, detects questions, and
automatically answers them using a local LLM -- with a live web dashboard and
a built-in benchmark panel.

## Features

| Feature | Details |
|---------|---------|
| Signal group monitoring | Polls via signal-cli |
| Question detection | Configurable shell command (`QUESTION_CHECK_COMMAND`) |
| Calendar / appointments | Configurable shell command (`CALENDAR_COMMAND`) |
| Local LLM | Configurable shell command (`LLM_COMMAND`) -- works with apfel, ollama, or any CLI |
| Token management | Auto-truncation to fit `TOKEN_WINDOW` (4096 for apfel) |
| 7-language i18n | en_US, de, es, fr, ja, pt, zh_CN |
| Deduplication | Never replies twice to the same message, even after restart |
| Persistent sessions | All pipeline runs saved to `data/sessions.json` |
| Web dashboard | Live pipeline view, stats, config drawer |
| Benchmark panel | Test any message in the browser -- no Signal needed |
| Token visualisation | Per-session prompt/response bar vs. token-window limit |

## Architecture

```
Signal group
    |  (signal-cli receive)
    v
bot.py -- run_pipeline() ------------------------------------------------+
    |                                                                     |
    +-- QUESTION_CHECK_COMMAND ($input$)  ->  "true" / "false"           |
    +-- CALENDAR_COMMAND                  ->  appointment text            |
    +-- LLM_COMMAND ($input$, $calendar_appointments$)  ->  answer       |
    +-- signal-cli send  ->  DM to sender                                 |
                                                                          |
storage.py  (data/sessions.json) <----------------------------------------+
    |
    +-- web_app.py  (Flask dashboard on :5000)
           +-- GET  /                  -- live dashboard (auto-refresh 5 s)
           +-- GET  /api/sessions      -- all sessions JSON
           +-- GET  /api/sessions/<id> -- single session
           +-- GET  /api/stats         -- aggregate counts
           +-- GET  /api/config        -- current config
           +-- POST /api/benchmark     -- run pipeline from web UI
```

## Prerequisites

| Dependency | Purpose |
|------------|---------|
| Python 3.8+ | Runtime |
| signal-cli | Signal protocol |
| Flask (`pip install Flask`) | Web dashboard |
| A local LLM (see below) | Answering questions |

### apfel (macOS 26+, Apple Silicon -- Apple Intelligence on-device)

```bash
brew tap Arthur-Ficial/tap && brew install apfel
```

```bash
LLM_COMMAND='apfel "$calendar_appointments$ These are upcoming appointments. Answer: $input$"'
TOKEN_WINDOW=4096
```

apfel uses Apple's on-device Foundation Model (4096-token context, no API key, no cloud).

### ollama (any platform)

```bash
brew install ollama && ollama pull llama3
```

```bash
LLM_COMMAND='ollama run llama3 "$calendar_appointments$ $input$"'
TOKEN_WINDOW=8192
```

## Quick Start

```bash
git clone https://github.com/falkorichter/Signal-bot.git
cd Signal-bot
pip install Flask
cp .env.example .env   # edit: set SIGNAL_NUMBER at minimum

# Register bot number (first time)
signal-cli -u +YOUR_NUMBER register
signal-cli -u +YOUR_NUMBER verify CODE

python bot.py          # terminal 1
python web_app.py      # terminal 2 -- open http://localhost:5000/
```

## Configuration

All settings are environment variables (or `.env` file entries).

### Required

| Variable | Example |
|----------|---------|
| `SIGNAL_NUMBER` | `+1234567890` |

### Pipeline commands

| Variable | Default | Placeholders |
|----------|---------|--------------|
| `QUESTION_CHECK_COMMAND` | `python check_question.py "$input$"` | `$input$` |
| `CALENDAR_COMMAND` | `python fetch_appointments.py` | -- |
| `LLM_COMMAND` | `python query_llm.py "$input$"` | `$input$`, `$calendar_appointments$` |

Placeholders are shell-escaped and substituted before the command runs.
Values are also exported as env-vars: `INPUT`, `CALENDAR_APPOINTMENTS`.

### Other settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MONITOR_GROUP` | `""` | Base64 Signal group ID (empty = all sources) |
| `TOKEN_WINDOW` | `4096` | LLM context window tokens (4096 for apfel) |
| `BOT_LANGUAGE` | `en_US` | `en_US`, `de`, `es`, `fr`, `ja`, `pt`, `zh_CN` |
| `FAQ_FILE` | `faqs.txt` | Path to FAQ text file |
| `POLL_INTERVAL` | `5` | Seconds between signal-cli receive calls |
| `MESSAGE_PREFIX` | `""` | Override i18n greeting (empty = use locale file) |
| `MESSAGE_SUFFIX` | `""` | Override i18n disclaimer (empty = use locale file) |

## Web Dashboard

Open `http://localhost:5000/` after starting `python web_app.py`.

### Benchmark / Test panel

Type any question in the **Test / Benchmark** box and click **Run Pipeline**.
The full pipeline runs immediately and the result appears inline with the
complete pipeline visualised. No real Signal message is sent.

### Token visualisation

- **While typing**: live character count + estimated token count + colour bar
- **Per session**: prompt and response token bars in the pipeline view
- Colours: green < 70% -- orange < 90% -- red >= 90% of TOKEN_WINDOW

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```

254 tests, one file per source module (safe for parallel PRs):

| Test file | Covers |
|-----------|--------|
| `tests/test_commands.py` | Token utils + shell runner |
| `tests/test_check_question.py` | Question detection |
| `tests/test_fetch_appointments.py` | Appointment fetching |
| `tests/test_query_llm.py` | FAQ loading, prompts, LLM client |
| `tests/test_bot.py` | Envelope parsing, pipeline, dedup |
| `tests/test_storage.py` | Session CRUD, persistence, threads |
| `tests/test_web_app.py` | All API endpoints incl. benchmark |
| `tests/test_i18n.py` | All 7 locale files, fallback, cache |

## Project Structure

```
Signal-bot/
+-- bot.py                  Main polling loop + run_pipeline()
+-- check_question.py       Heuristic question detector (standalone command)
+-- commands.py             Shell runner: $var$ substitution + token utils
+-- config.py               All env-var configuration
+-- fetch_appointments.py   Calendar fetcher stub (standalone command)
+-- i18n.py                 Locale loader
+-- query_llm.py            ollama LLM client (standalone command)
+-- storage.py              Thread-safe JSON session store
+-- web_app.py              Flask dashboard + benchmark API
+-- faqs.txt                Sample FAQ database
+-- locales/                7 language files
+-- templates/index.html    Dashboard UI (Bootstrap 5)
+-- data/                   Runtime: sessions.json (git-ignored)
+-- tests/                  One file per source module
+-- .env.example            Configuration template
+-- pyproject.toml          Project metadata + pytest config
+-- CHANGELOG.md            Keep a Changelog format
+-- CONTRIBUTING.md         Contribution guide
```

## Development Metadata

| Field | Value |
|-------|-------|
| Version | 0.2.0 |
| Last updated | 2026-04-06 |
| AI tools used | GitHub Copilot (code generation), apfel / Apple Intelligence (on-device LLM, macOS 26+), ollama (local LLM runtime) |
| Test count | 254 |
| Languages supported | en_US, de, es, fr, ja, pt, zh_CN |

## License

MIT
