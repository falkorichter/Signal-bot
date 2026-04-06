#!/usr/bin/env python3
"""query_llm.py — Answer a question using a local LLM (ollama) with FAQ and appointment context.

Usage::

    python query_llm.py "What are the available appointments?"

Prints the LLM's answer to stdout.  Exits non-zero on failure.

Dependencies:
- ollama must be running locally (``ollama serve``).
- The model specified by ``LLM_MODEL`` must be pulled (``ollama pull llama3``).
"""

import json
import logging
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# Ensure the project root is importable when run as a standalone script
sys.path.insert(0, str(Path(__file__).parent))

from config import FAQ_FILE, LLM_API_URL, LLM_MODEL

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FAQ loading
# ---------------------------------------------------------------------------


def load_faqs(faq_file: Optional[str] = None) -> str:
    """Return the contents of the FAQ file as a string.

    Args:
        faq_file: Optional override path. Defaults to :data:`config.FAQ_FILE`.

    Returns:
        The FAQ text, or a notice string when the file is missing.
    """
    path = Path(faq_file or FAQ_FILE)
    if not path.is_absolute():
        # Resolve relative to the project root (this file's directory)
        path = Path(__file__).parent / path

    if not path.exists():
        logger.warning("FAQ file not found at %s — proceeding without FAQs", path)
        return "(No FAQ data available)"

    try:
        content = path.read_text(encoding="utf-8").strip()
        logger.debug("Loaded %d characters from FAQ file %s", len(content), path)
        return content
    except OSError as exc:
        logger.error("Could not read FAQ file %s: %s", path, exc)
        return "(FAQ file could not be read)"


# ---------------------------------------------------------------------------
# Appointment context
# ---------------------------------------------------------------------------


def fetch_appointments_text() -> str:
    """Return appointment text, checking ``CALENDAR_APPOINTMENTS`` env-var first.

    When the bot pipeline pre-fetches the calendar via ``CALENDAR_COMMAND`` and
    exports the result as ``CALENDAR_APPOINTMENTS``, this function uses that
    value directly — avoiding a redundant second fetch when ``query_llm.py`` is
    called as the default ``LLM_COMMAND``.
    """
    env_calendar = os.environ.get("CALENDAR_APPOINTMENTS", "").strip()
    if env_calendar:
        logger.debug("Using CALENDAR_APPOINTMENTS from environment")
        return env_calendar

    script = Path(__file__).parent / "fetch_appointments.py"
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error(
                "fetch_appointments.py exited %d: %s",
                result.returncode,
                result.stderr.strip(),
            )
            return "(Could not fetch appointment data)"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.error("fetch_appointments.py timed out")
        return "(Appointment fetch timed out)"
    except Exception as exc:
        logger.error("Unexpected error running fetch_appointments.py: %s", exc)
        return "(Error fetching appointments)"


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_prompt(question: str, faqs: str, appointments: str) -> str:
    """Compose the LLM prompt from the question, FAQ text, and appointment data.

    Args:
        question:     The user's question.
        faqs:         The full FAQ text.
        appointments: Formatted upcoming-appointments text.

    Returns:
        A complete prompt string ready to send to the LLM.
    """
    return (
        "You are a helpful FAQ bot. Answer the user's question concisely and "
        "accurately based only on the FAQ information and upcoming appointments "
        "provided below.\n"
        "If the answer cannot be found in the provided context, say so politely "
        "and suggest contacting the office directly.\n\n"
        f"=== FAQs ===\n{faqs}\n\n"
        f"=== Upcoming Appointments ===\n{appointments}\n\n"
        f"=== User Question ===\n{question}\n\n"
        "=== Your Answer ==="
    )


# ---------------------------------------------------------------------------
# LLM query
# ---------------------------------------------------------------------------


def query_llm(prompt: str) -> str:
    """Send *prompt* to the ollama generate API and return the response text.

    Args:
        prompt: The full prompt string.

    Returns:
        The generated text from the LLM.

    Raises:
        RuntimeError: When the API call fails or returns an unexpected response.
    """
    payload = json.dumps(
        {"model": LLM_MODEL, "prompt": prompt, "stream": False}
    ).encode("utf-8")

    req = urllib.request.Request(
        LLM_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
            text = data.get("response", "").strip()
            if not text:
                raise RuntimeError("LLM returned an empty response")
            logger.debug("LLM response (%d chars) received", len(text))
            return text
    except urllib.error.URLError as exc:
        logger.error("Cannot reach LLM at %s: %s", LLM_API_URL, exc)
        raise RuntimeError(
            f"Could not connect to LLM at {LLM_API_URL}. "
            f"Is ollama running? Error: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if len(sys.argv) < 2:
        logger.error("Usage: query_llm.py <question>")
        print("Usage: query_llm.py <question>", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    faqs = load_faqs()
    appointments = fetch_appointments_text()
    prompt = build_prompt(question, faqs, appointments)

    try:
        answer = query_llm(prompt)
        print(answer)
    except RuntimeError as exc:
        logger.error("LLM query failed: %s", exc)
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
