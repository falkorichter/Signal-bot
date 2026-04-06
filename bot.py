#!/usr/bin/env python3
"""bot.py -- Signal FAQ Bot main polling loop.

Continuously polls a Signal group via signal-cli, identifies questions,
runs the configured pipeline commands, and sends replies as DMs.

Every message is persisted in data/sessions.json via SessionStore so the
web dashboard can display the full pipeline and the bot never sends duplicate
replies after a restart.

Pipeline per message
--------------------
1. signal-cli receive -> parse envelope
2. QUESTION_CHECK_COMMAND  ($input$) -> "true" / "false"
3. CALENDAR_COMMAND        -> upcoming appointment text
4. LLM_COMMAND             ($input$, $calendar_appointments$) -> answer
5. Wrap answer with i18n greeting prefix + disclaimer suffix
6. signal-cli send -> direct message to the original sender

All step commands are configurable via environment variables; see config.py.

apfel (Apple Intelligence, macOS 26+) example::

    LLM_COMMAND='apfel "$calendar_appointments$ Upcoming appointments. $input$"'
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

from commands import (
    estimate_tokens,
    run_configured_command,
    trim_to_token_budget,
)
from config import (
    BOT_LANGUAGE,
    CALENDAR_COMMAND,
    FAQ_FILE,
    LLM_COMMAND,
    MESSAGE_PREFIX,
    MESSAGE_SUFFIX,
    MONITOR_GROUP,
    POLL_INTERVAL,
    QUESTION_CHECK_COMMAND,
    SIGNAL_NUMBER,
    TOKEN_WINDOW,
)
from i18n import get_message
from storage import Session, SessionStore

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
    """Call signal-cli receive --json and return parsed envelope dicts."""
    cmd = ["signal-cli", "--output", "json", "-u", SIGNAL_NUMBER, "receive"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        logger.error(
            "signal-cli not found -- install it and ensure it is on your PATH"
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
            logger.debug("Skipping non-JSON line: %.80s ... (%s)", line, exc)
    return messages


def send_direct_message(recipient: str, text: str) -> bool:
    """Send a Signal DM via signal-cli. Returns True on success."""
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
        recipient,
        result.returncode,
        result.stderr.strip(),
    )
    return False


# ---------------------------------------------------------------------------
# Envelope parsing
# ---------------------------------------------------------------------------


def extract_message_data(envelope: dict) -> Tuple[str, str, str]:
    """Extract (sender, group_id, message_text) from a signal-cli envelope."""
    inner = envelope.get("envelope", {})
    data_msg = inner.get("dataMessage") or {}
    message_text = (data_msg.get("message") or "").strip()
    sender = (inner.get("source") or inner.get("sourceNumber") or "").strip()
    group_info = data_msg.get("groupInfo") or {}
    group_id = (group_info.get("groupId") or "").strip()
    return sender, group_id, message_text


# ---------------------------------------------------------------------------
# Pipeline step helpers
# ---------------------------------------------------------------------------


def _step_check_question(
    text: str, session_id: str, store: SessionStore
) -> bool:
    """Run QUESTION_CHECK_COMMAND; update and return is_question."""
    try:
        output = run_configured_command(
            QUESTION_CHECK_COMMAND, timeout=60, input=text
        )
        result = output.lower() == "true"
    except RuntimeError as exc:
        logger.error("Question-check command failed: %s", exc)
        result = False
    store.update_session(session_id, is_question=result)
    return result


def _step_fetch_calendar(session_id: str, store: SessionStore) -> str:
    """Run CALENDAR_COMMAND; store and return appointment text."""
    try:
        text = run_configured_command(CALENDAR_COMMAND, timeout=30)
    except RuntimeError as exc:
        logger.error("Calendar command failed: %s", exc)
        text = f"(Could not fetch calendar: {exc})"
    store.update_session(session_id, appointments_text=text)
    return text


def _step_query_llm(
    question: str,
    calendar_text: str,
    session_id: str,
    store: SessionStore,
) -> Optional[str]:
    """Run LLM_COMMAND with token-budget management; store and return answer."""
    # Reserve ~150 overhead tokens + question + answer headroom (~300)
    question_tokens = estimate_tokens(question)
    overhead = 150 + question_tokens + 300
    context_budget = max(50, TOKEN_WINDOW - overhead)

    calendar_tokens = estimate_tokens(calendar_text)
    if calendar_tokens > context_budget:
        calendar_text = trim_to_token_budget(
            calendar_text, context_budget, "calendar"
        )

    # Estimate FAQ size for a richer prompt_tokens figure
    faq_size = 0
    try:
        faq_path = Path(FAQ_FILE)
        if faq_path.exists():
            faq_size = len(faq_path.read_text(encoding="utf-8"))
    except OSError:
        pass

    prompt_tokens_est = overhead + estimate_tokens(calendar_text) + (faq_size // 4)
    store.update_session(
        session_id, prompt_tokens=min(prompt_tokens_est, TOKEN_WINDOW + 500)
    )

    if prompt_tokens_est > TOKEN_WINDOW * 0.90:
        logger.warning(
            "Estimated prompt tokens (%d) approach token window (%d); "
            "response quality may be affected",
            prompt_tokens_est,
            TOKEN_WINDOW,
        )

    try:
        response = run_configured_command(
            LLM_COMMAND,
            timeout=120,
            input=question,
            calendar_appointments=calendar_text,
        )
        if not response:
            raise RuntimeError("LLM command returned empty output")
        store.update_session(
            session_id,
            llm_response=response,
            response_tokens=estimate_tokens(response),
        )
        return response
    except RuntimeError as exc:
        logger.error("LLM command failed: %s", exc)
        store.update_session(session_id, error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Reply builder
# ---------------------------------------------------------------------------


def build_reply(answer: str) -> str:
    """Wrap answer with the configured greeting prefix and disclaimer suffix."""
    prefix = MESSAGE_PREFIX or get_message("message_prefix", BOT_LANGUAGE)
    suffix = MESSAGE_SUFFIX or get_message("message_suffix", BOT_LANGUAGE)
    return prefix + answer + suffix


# ---------------------------------------------------------------------------
# Shared pipeline runner  (used by both the bot loop and the web benchmark)
# ---------------------------------------------------------------------------


def run_pipeline(
    message_text: str,
    sender: str,
    group_id: str,
    store: SessionStore,
    is_test: bool = False,
    send_dm: bool = True,
) -> Session:
    """Run the full FAQ-bot pipeline for a single message.

    Args:
        message_text: The incoming message to process.
        sender:       Signal phone number / identifier of the sender.
        group_id:     Signal group ID (empty for direct messages).
        store:        Session store to persist pipeline state.
        is_test:      When True, marks the session as a benchmark/test run.
        send_dm:      When False, the reply is stored but not sent via
                      signal-cli (useful for web benchmark runs).

    Returns:
        The final Session after all steps complete.
    """
    session = store.create_session(sender, group_id, message_text)
    if is_test:
        store.update_session(session.id, is_test=True)

    logger.info(
        "Pipeline start | session=%s is_test=%s from=%s | %.80s",
        session.id,
        is_test,
        sender,
        message_text,
    )

    try:
        # Step 1 -- Question detection
        if not _step_check_question(message_text, session.id, store):
            logger.info("Session %s -- not a question, done", session.id)
            return store.get_session(session.id)

        logger.info("Session %s -- question confirmed", session.id)

        # Step 2 -- Calendar fetch
        calendar_text = _step_fetch_calendar(session.id, store)

        # Step 3 -- LLM query
        llm_answer = _step_query_llm(
            message_text, calendar_text, session.id, store
        )
        if llm_answer is None:
            error_msg = get_message("error_no_response", BOT_LANGUAGE)
            store.update_session(session.id, final_message=error_msg)
            if send_dm:
                send_direct_message(sender, error_msg)
            return store.get_session(session.id)

        # Step 4 -- Build and send/store reply
        reply = build_reply(llm_answer)
        store.update_session(session.id, final_message=reply)

        if send_dm:
            sent = send_direct_message(sender, reply)
        else:
            sent = True  # benchmark: mark as replied without actual send

        if sent:
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

    return store.get_session(session.id)


# ---------------------------------------------------------------------------
# Envelope processor  (used by the polling loop)
# ---------------------------------------------------------------------------


def process_envelope(envelope: dict, store: SessionStore) -> None:
    """Process one signal-cli envelope through the full FAQ-bot pipeline."""
    sender, group_id, message_text = extract_message_data(envelope)

    if not message_text:
        return
    if MONITOR_GROUP and group_id != MONITOR_GROUP:
        return
    if not sender:
        logger.warning("Could not determine message sender -- skipping envelope")
        return

    if store.is_already_replied(sender, message_text):
        logger.info("Already replied to this message from %s -- skipping", sender)
        return

    run_pipeline(
        message_text=message_text,
        sender=sender,
        group_id=group_id,
        store=store,
        is_test=False,
        send_dm=True,
    )


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
        "Signal FAQ Bot starting -- number=%s, group=%s, poll=%ds",
        SIGNAL_NUMBER,
        MONITOR_GROUP or "(all)",
        POLL_INTERVAL,
    )

    while True:
        try:
            for envelope in receive_messages():
                try:
                    process_envelope(envelope, store)
                except Exception as exc:
                    logger.error(
                        "Unhandled error processing envelope: %s",
                        exc,
                        exc_info=True,
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
