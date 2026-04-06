"""Configuration for the Signal FAQ Bot.

All settings are read from environment variables.
If python-dotenv is installed, a .env file in the project root is loaded first.
"""

import os
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Signal / signal-cli
# ---------------------------------------------------------------------------

#: Phone number the bot account is registered under, e.g. "+1234567890"
SIGNAL_NUMBER: str = os.environ.get("SIGNAL_NUMBER", "")

#: Base64-encoded Signal group ID to monitor.
#: Leave empty to respond to questions from all sources.
MONITOR_GROUP: str = os.environ.get("MONITOR_GROUP", "")

# ---------------------------------------------------------------------------
# Local LLM (ollama)
# ---------------------------------------------------------------------------

#: ollama model to use, e.g. "llama3", "mistral"
LLM_MODEL: str = os.environ.get("LLM_MODEL", "llama3")

#: ollama generate API endpoint
LLM_API_URL: str = os.environ.get(
    "LLM_API_URL", "http://localhost:11434/api/generate"
)

# ---------------------------------------------------------------------------
# FAQ database
# ---------------------------------------------------------------------------

#: Path to the plain-text FAQ file (absolute or relative to the project root)
FAQ_FILE: str = os.environ.get(
    "FAQ_FILE", str(Path(__file__).parent / "faqs.txt")
)

# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------

#: Seconds to wait between signal-cli receive calls
POLL_INTERVAL: int = int(os.environ.get("POLL_INTERVAL", "5"))

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

#: Language used for bot message templates.
#: Must match one of the locale files in locales/.
#: Supported: en_US, de, es, fr, ja, pt, zh_CN
BOT_LANGUAGE: str = os.environ.get("BOT_LANGUAGE", "en_US")

# ---------------------------------------------------------------------------
# Message template overrides (optional, bypasses i18n when set)
# ---------------------------------------------------------------------------

#: If set, replaces the localized greeting/intro prefix entirely.
MESSAGE_PREFIX: str = os.environ.get("MESSAGE_PREFIX", "")

#: If set, replaces the localized disclaimer suffix entirely.
MESSAGE_SUFFIX: str = os.environ.get("MESSAGE_SUFFIX", "")

# ---------------------------------------------------------------------------
# Configurable pipeline commands
# ---------------------------------------------------------------------------
# Each pipeline step is driven by a shell command string.  Use $input$ and
# $calendar_appointments$ as placeholder tokens — they are substituted with
# the live values before the command runs.  Values are also exported as
# upper-cased environment variables (INPUT, CALENDAR_APPOINTMENTS) so
# templates can reference them either way.
#
# apfel examples (macOS 26+, Apple Silicon):
#   LLM_COMMAND=apfel "$calendar_appointments$ Upcoming appointments. $input$"
#   LLM_COMMAND=apfel -s "You are an FAQ bot" "$calendar_appointments$ $input$"
#
# ollama examples:
#   LLM_COMMAND=ollama run llama3 "$calendar_appointments$ $input$"

_PYTHON = sys.executable  # current interpreter path (respects virtualenvs)

#: Shell command that receives the user message (via ``$input$``) and prints
#: "true" or "false" to stdout indicating whether it is a question.
QUESTION_CHECK_COMMAND: str = os.environ.get(
    "QUESTION_CHECK_COMMAND",
    f'"{_PYTHON}" check_question.py "$input$"',
)

#: Shell command that fetches calendar / appointment data and prints it to
#: stdout.  No placeholders are required; output is captured and passed to
#: the LLM command as ``$calendar_appointments$``.
CALENDAR_COMMAND: str = os.environ.get(
    "CALENDAR_COMMAND",
    f'"{_PYTHON}" fetch_appointments.py',
)

#: Shell command that queries the LLM and prints the answer to stdout.
#: Available placeholders: ``$input$`` (user question),
#: ``$calendar_appointments$`` (output of CALENDAR_COMMAND).
LLM_COMMAND: str = os.environ.get(
    "LLM_COMMAND",
    f'"{_PYTHON}" query_llm.py "$input$"',
)

# ---------------------------------------------------------------------------
# Token window
# ---------------------------------------------------------------------------

#: Maximum tokens the LLM accepts in a single request.
#: apfel (Apple Intelligence) has a fixed 4096-token window.
#: Increase this when using a model with a larger context (e.g. 8192, 32768).
TOKEN_WINDOW: int = int(os.environ.get("TOKEN_WINDOW", "4096"))
