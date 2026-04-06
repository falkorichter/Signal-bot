#!/usr/bin/env python3
"""bot.py — Signal FAQ Bot main polling loop.

Continuously polls a Signal group via signal-cli, identifies questions,
queries a local LLM (ollama) for answers, and sends replies as DMs.

Every message processed is persisted as a :class:`~storage.Session` in
``data/sessions.json`` so that:

* The web dashboard (``web_app.py``) can display the full pipeline.
* The bot never sends duplicate replies after a restart.

Pipeline per message
--------------------
1. signal-cli receive → parse envelope
2. check_question.py heuristic → is it a question?
3. fetch_appointments.py → upcoming appointment data
4. ollama LLM → generate answer from FAQ + appointments
5. Wrap answer with i18n greeting prefix + disclaimer suffix
6. signal-cli send → direct message to the original sender
"""

import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from check_question import is_question_heuristic
from config import (
    BOT_LANGUAGE,
    MESSAGE_PREFIX,
    MESSAGE_SUFFIX,
    MONITOR_GROUP,
    POLL_INTERVAL,
    SIGNAL_NUMBER,
)
from fetch_appointments import fetch_appointments, format_appointments
from i18n import get_message
from query_llm import build_prompt, load_faqs
from query_llm import query_llm as _query_llm
from storage import SessionStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# signal-cli helpers
# ---------------------------------------------------------------------------


def receive_messages() -> List[dict]:
    """Call ``signal-cli receive --json`` and return parsed envelope dicts."""
    cmd = ["signal-cli", "--output", "json", "-u", SIGNAL_NUMBER, "receive"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        logger.error(
            "signal-cli not found — install it and ensure it is on your PATH"
        )
        return []
    except subprocess.TimeoutExpired:
        logger.warning("signal-cli receive timed out")
        return []
    except Exception as exc:
        logger.error("Unexpected error running signal-cli receive: %s", exc)
        return []

    if result.returncode != 0 and result.stderr:
        logger.warning("signal-cli receive stderr: %s", result.stderr.strip())

    messages: List[dict] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError as exc:
            logger.debug("Skipping non-JSON line: %.80s … (%s)", line, exc)
    return messages


def send_direct_message(recipient: str, text: str) -> bool:
    """Send a Signal DM via signal-cli.  Returns ``True`` on success."""
    cmd = ["signal-cli", "-u", SIGNAL_NUMBER, "send", "-m", text, recipient]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        logger.error("signal-cli not found while sending DM to %s", recipient)
        return False
    except subprocess.TimeoutExpired:
        logger.error("Timeout sending DM to %s", recipient)
        return False
    except Exception as exc:
        logger.error("Unexpected error sending DM to %s: %s", recipient, exc)
        return False

    if result.returncode == 0:
        logger.info("DM sent to %s", recipient)
        return True

    logger.error(
        "Failed to send DM to %s (exit %d): %s",
        recipient, result.returncode, result.stderr.strip(),
    )
    return False


# ---------------------------------------------------------------------------
# Envelope parsing
# ---------------------------------------------------------------------------


def extract_message_data(envelope: dict) -> Tuple[str, str, str]:
    """Extract ``(sender, group_id, message_text)`` from a signal-cli envelope.

    Returns empty strings for any field that is absent or null.
    """
    inner = envelope.get("envelope", {})
    data_msg = inner.get("dataMessage") or {}
    message_text = (data_msg.get("message") or "").strip()
    sender = (inner.get("source") or inner.get("sourceNumber") or "").strip()
    group_info = data_msg.get("groupInfo") or {}
    group_id = (group_info.get("groupId") or "").strip()
    return sender, group_id, message_text


# ---------------------------------------------------------------------------
# Pipeline steps (each updates the session store immediately)
# ---------------------------------------------------------------------------


def _step_check_question(
    text: str, session_id: str, store: SessionStore
) -> bool:
    result = is_question_heuristic(text)
    store.update_session(session_id, is_question=result)
    return result


def _step_fetch_appointments(session_id: str, store: SessionStore) -> str:
    try:
        appts = fetch_appointments()
        text = format_appointments(appts)
    except Exception as exc:
        logger.error("Error fetching appointments: %s", exc)
        text = f"(Could not fetch appointments: {exc})"
    store.update_session(session_id, appointments_text=text)
    return text


def _step_query_llm(
    question: str,
    appointments_text: str,
    session_id: str,
    store: SessionStore,
) -> Optional[str]:
    faqs = load_faqs()
    prompt = build_prompt(question, faqs, appointments_text)
    try:
        response = _query_llm(prompt)
        store.update_session(session_id, llm_response=response)
        return response
    except RuntimeError as exc:
        logger.error("LLM query failed: %s", exc)
        store.update_session(session_id, error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Reply builder
# ---------------------------------------------------------------------------


def build_reply(answer: str) -> str:
    """Wrap *answer* with the configured greeting prefix and disclaimer suffix."""
    prefix = MESSAGE_PREFIX or get_message("message_prefix", BOT_LANGUAGE)
    suffix = MESSAGE_SUFFIX or get_message("message_suffix", BOT_LANGUAGE)
    return prefix + answer + suffix


# ---------------------------------------------------------------------------
# Main envelope processor
# ---------------------------------------------------------------------------


def process_envelope(envelope: dict, store: SessionStore) -> None:
    """Process one signal-cli envelope through the full FAQ-bot pipeline."""
    sender, group_id, message_text = extract_message_data(envelope)

    if not message_text:
        return

    # Only process messages from the configured group (if set)
    if MONITOR_GROUP and group_id != MONITOR_GROUP:
        return

    if not sender:
        logger.warning("Could not determine message sender — skipping envelope")
        return

    # Deduplication: skip if we already replied to this exact message
    if store.is_already_replied(sender, message_text):
        logger.info(
            "Already replied to this message from %s — skipping", sender
        )
        return

    session = store.create_session(sender, group_id, message_text)
    logger.info(
        "Session %s | from %s (group=%s) | %.80s",
        session.id, sender, group_id or "(direct)", message_text,
    )

    try:
        # ── Step 1: Question detection ──────────────────────────────────
        if not _step_check_question(message_text, session.id, store):
            logger.info("Session %s — not a question, done", session.id)
            return

        logger.info("Session %s — identified as a question", session.id)

        # ── Step 2: Fetch appointments ───────────────────────────────────
        appointments_text = _step_fetch_appointments(session.id, store)

        # ── Step 3: Query LLM ────────────────────────────────────────────
        llm_answer = _step_query_llm(
            message_text, appointments_text, session.id, store
        )
        if llm_answer is None:
            error_msg = get_message("error_no_response", BOT_LANGUAGE)
            store.update_session(session.id, final_message=error_msg)
            send_direct_message(sender, error_msg)
            return

        # ── Step 4: Send DM ──────────────────────────────────────────────
        reply = build_reply(llm_answer)
        store.update_session(session.id, final_message=reply)

        if send_direct_message(sender, reply):
            store.update_session(
                session.id,
                replied=True,
                replied_at=datetime.now(timezone.utc).isoformat(),
            )

    except Exception as exc:
        logger.error(
            "Unhandled error in session %s: %s", session.id, exc, exc_info=True
        )
        store.update_session(session.id, error=str(exc))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the bot polling loop."""
    if not SIGNAL_NUMBER:
        logger.error(
            "SIGNAL_NUMBER is not set. "
            "Configure it via the SIGNAL_NUMBER environment variable or .env file."
        )
        sys.exit(1)

    store = SessionStore()

    logger.info(
        "Signal FAQ Bot starting — number=%s, group=%s, poll=%ds",
        SIGNAL_NUMBER, MONITOR_GROUP or "(all)", POLL_INTERVAL,
    )

    while True:
        try:
            for envelope in receive_messages():
                try:
                    process_envelope(envelope, store)
                except Exception as exc:
                    logger.error(
                        "Unhandled error processing envelope: %s",
                        exc, exc_info=True,
                    )
        except KeyboardInterrupt:
            logger.info("Shutting down (KeyboardInterrupt)")
            break
        except Exception as exc:
            logger.error(
                "Unhandled error in main loop: %s", exc, exc_info=True
            )

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
